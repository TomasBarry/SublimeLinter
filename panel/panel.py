import html
import os
import sublime
import sublime_plugin
import copy


from ..lint.const import PLUGIN_NAME, WARN_ERR
from ..lint import util, persist


PANEL_NAME = "sublime_linter_panel"
OUTPUT_PANEL_SETTINGS = {
    "auto_indent": False,
    "draw_indent_guides": False,
    "draw_white_space": "None",
    "gutter": False,
    "is_widget": True,
    "line_numbers": False,
    "margin": 3,
    "match_brackets": False,
    "scroll_past_end": False,
    "tab_size": 4,
    "translate_tabs_to_spaces": False,
    "word_wrap": False
}


UNDERLINE_FLAGS = (sublime.DRAW_SQUIGGLY_UNDERLINE
                   | sublime.DRAW_NO_OUTLINE
                   | sublime.DRAW_NO_FILL
                   | sublime.DRAW_EMPTY_AS_OVERWRITE)

BOX_FLAGS = sublime.DRAW_NO_FILL | sublime.DRAW_EMPTY_AS_OVERWRITE


def dedupe_views(errors):
    if len(errors) == 1:
        return errors
    else:
        return {
            vid: dic
            for vid, dic in errors.items()
            if sublime.View(vid).is_primary()
        }


def get_file_path(vid):
    return sublime.View(vid).file_name()


def get_common_parent(paths):
    """
    Get the common parent directory of multiple paths.
    Python 3.5+ includes os.path.commonpath which does this, however Sublime
    currently embeds Python 3.3.
    """
    return os.path.commonprefix([path + '/' for path in paths]).rstrip('/')


def create_path_dict(x):
    abs_dict = {vid: get_file_path(vid) for vid in x}

    if len(abs_dict) == 1:
        for vid, path in abs_dict.items():
            base_dir, file_name = os.path.split(path)
            rel_paths = {vid: file_name}
    else:
        base_dir = get_common_parent(abs_dict.values())

        rel_paths = {
            vid: os.path.relpath(abs_path, base_dir)
            for vid, abs_path in abs_dict.items()
        }

    return rel_paths, base_dir or ""


def create_panel(window):
    panel = window.create_output_panel(PANEL_NAME)
    settings = panel.settings()
    for key, value in OUTPUT_PANEL_SETTINGS.items():
        settings.set(key, value)

    panel.settings().set("result_file_regex", r"^\s*(\S*\.\w+)\s*(\d*)")
    panel.settings().set("result_line_regex", r"(^\s*\d+)")

    syntax_path = "Packages/SublimeLinter/panel/panel.sublime-syntax"
    panel.assign_syntax(syntax_path)
    # Call create_output_panel a second time after assigning the above
    # settings, so that it'll be picked up as a result buffer
    # see: Packages/Default/exec.py#L228-L230
    return window.create_output_panel(PANEL_NAME)


def get_panel(window):
    return window.find_output_panel(PANEL_NAME)


def ensure_panel(window: sublime.Window):
    return get_panel(window) or create_panel(window)


def filter_errors(window, errors):
    vids = [v.id() for v in window.views()]
    return {vid: d for vid, d in errors.items() if vid in vids}


def format_header(f_path):
    return "{}".format(f_path)  # TODO: better using phantom + icon?


def format_row(lineno, err_type, dic):
    lineno = int(lineno) + 1  # if lineno else lineno
    tmpl = "{LINENO:>6}   {start:>6}:{end:<10}   {ERR_TYPE:<0}{linter:<15}{code:<6}{msg:>10}"
    return tmpl.format(LINENO=lineno, ERR_TYPE=err_type, **dic)


def fill_panel(window, types=None, codes=None, linter=None, update=False):

    errors = persist.errors.data.copy()
    if not errors:
        return

    errors = filter_errors(window, errors)
    errors = dedupe_views(errors)
    # base_dir = util.get_project_path(window)
    path_dict, base_dir = create_path_dict(errors)

    assert window, "missing window!"

    panel = ensure_panel(window)
    assert panel, "must have a panel now!"

    settings = panel.settings()
    settings.set("result_base_dir", base_dir)

    if update:
        panel.run_command("sublime_linter_panel_clear")
        types = settings.get("types")
        codes = settings.get("codes")
        linter = settings.get("linter")
    else:
        settings.set("types", types)
        settings.set("codes", codes)
        settings.set("linter", linter)

    panel.set_read_only(False)
    to_render = []
    for vid, view_dict in errors.items():
        to_render.append(format_header(path_dict[vid]))

        for lineno, line_dict in sorted(view_dict["line_dicts"].items()):
            for err_type in WARN_ERR:
                if types and err_type not in types:
                    continue
                err_dict = line_dict.get(err_type)
                if not err_dict:
                    continue
                items = sorted(err_dict, key=lambda k: k['start'])

                for item in items:
                    # new filter function
                    if linter and item['linter'] not in linter:
                        continue

                    if codes and item['code'] not in codes:
                        continue

                    line_msg = format_row(lineno, err_type, item)
                    to_render.append(line_msg)

        to_render.append("\n")  # empty lines between views

    panel.run_command("sublime_linter_panel_update", {
                      "characters": "\n".join(to_render)})
    panel.set_read_only(True)
