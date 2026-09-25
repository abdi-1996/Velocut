from pathlib import Path

p = Path('VeloCutAI/patch_v047_clean_ui.py')
s = p.read_text()
old = '''# Remove the top bar and separate playback row. Preview becomes the complete top area.
old_stack = 'ZStack{Color(uiColor:.systemGroupedBackground).ignoresSafeArea();VStack(spacing:0){topBar;preview.frame(height:min(335,max(215,root.size.height*0.34)));playback;if let target=curveTarget{CurveEditorPanel(model:model,target:target,onClose:{curveTarget=nil}).frame(maxHeight:.infinity)}else{timeline.frame(maxHeight:.infinity)};bottomBar}.frame(width:root.size.width,height:root.size.height,alignment:.top)}'
new_stack = 'ZStack{Color(uiColor:.systemGroupedBackground).ignoresSafeArea();VStack(spacing:0){preview.frame(height:min(390,max(255,root.size.height*0.42))).ignoresSafeArea(edges:.top);if let target=curveTarget{CurveEditorPanel(model:model,target:target,onClose:{curveTarget=nil}).frame(maxHeight:.infinity)}else{timeline.frame(maxHeight:.infinity)};bottomBar}.frame(width:root.size.width,height:root.size.height,alignment:.top)}'
if old_stack not in s:
    raise RuntimeError('v0.4.6 editor stack not found')
s = s.replace(old_stack, new_stack, 1)
'''
new = '''# Remove the top bar and separate playback row. Preview becomes the complete top area.
# Work independently of earlier layout patches: remove the two body references,
# then resize the first Preview frame we find.
if 'topBar;' not in s:
    raise RuntimeError('topBar body reference not found')
s = s.replace('topBar;', '', 1)
if 'playback;' not in s:
    raise RuntimeError('playback body reference not found')
s = s.replace('playback;', '', 1)
s, count = re.subn(
    r'preview\\.frame\\(height:min\\(.*?root\\.size\\.height\\*0\\.[0-9]+\\)\\)\\)',
    'preview.frame(height:min(390,max(255,root.size.height*0.42))).ignoresSafeArea(edges:.top)',
    s,
    count=1
)
if count != 1:
    raise RuntimeError('Preview height expression not found')
'''
if old not in s:
    raise RuntimeError('Old v0.4.7 stack matcher source not found')
s = s.replace(old, new, 1)

# Earlier patches reformat these Swift blocks, so do not depend on blank lines.
s = s.replace(
    "re.compile(r'    private var preview:some View\\{.*?\\n\\n    private var playback:', re.S)",
    "re.compile(r'    private var preview:some View\\s*\\{.*?    private var playback:', re.S)"
)
s = s.replace(
    "re.compile(r'struct CurveEditorPanel:View \\{.*?\\n\\}\\n\\nstruct InspectorSheet:View', re.S)",
    "re.compile(r'struct CurveEditorPanel:View\\s*\\{.*?struct InspectorSheet:View', re.S)"
)
s = s.replace(
    "re.compile(r'    private var speed:some View\\{.*?\\n    private var audio:', re.S)",
    "re.compile(r'    private var speed:some View\\s*\\{.*?    private var audio:', re.S)"
)

p.write_text(s)
print('Relaxed v0.4.7 editor body, Preview and Curve matchers')
