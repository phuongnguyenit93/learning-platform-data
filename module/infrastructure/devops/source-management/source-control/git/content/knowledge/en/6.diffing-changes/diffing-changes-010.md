# Comparing Binary Files and Using git difftool

Git manages file contents as blobs, meaning sequences of bytes. When generating a diff, Git must decide whether the content can be read as text or should be treated as binary data. For text files, Git normally displays added, removed, and modified lines. For images, PDFs, archives, fonts, or executables, a line-based diff usually makes no sense. In those cases, you need to know how to inspect metadata, generate binary patches, or open both versions in an appropriate comparison tool.

This lesson covers how Git detects binary files, useful diff commands when content cannot be displayed as text, how to create and apply binary patches, how to configure text conversion to compare textual representations of files, and how to use git difftool to launch external tools. The goal is to choose the right comparison method for each data type and understand exactly what the tool is showing you.

## 1. How Does Git Store Binary Files?

Git does not have a separate object type called a binary file. A file's contents—whether source code, a PNG image, a PDF, or a ZIP archive—are all stored in blobs as bytes. Trees record the path name, file mode, and object ID pointing to that blob.

The distinction between text and binary primarily affects how Git generates and displays diffs:

- For text content, Git can compare line by line and generate human-readable patches.
- For binary content, Git normally avoids attempting to interpret bytes as lines of text.
- For certain binary formats, specialized tools can extract metadata or convert contents into text to aid review.

For example, a repository may contain:

~~~text
design/
  logo.png
  architecture.pdf
assets/
  product-demo.mp4
  icon-font.woff2
release/
  application.zip
~~~

These files are still stored and versioned by Git like any other file. The difference lies in how changes are inspected and reviewed.

## 2. How Git Detects Binary Content

Git typically uses heuristics to detect content containing NUL bytes or byte sequences unsuitable for text. Beyond heuristics, a repository can explicitly declare attributes per pattern in `.gitattributes`.

Example:

~~~gitattributes
# Text files
*.java text
*.md text
*.yml text

# Binary files
*.png binary
*.jpg binary
*.pdf binary
*.zip binary
*.woff2 binary
*.mp4 binary
~~~

The binary attribute macro is equivalent to disabling standard text, diff, and merge processing for paths matching the pattern. This keeps Git from attempting to generate line diffs for files unsuited to text comparison.

Check which attributes apply:

~~~bash
git check-attr -a -- design/logo.png
git check-attr -a -- architecture.pdf
~~~

This command shows the attributes Git resolves for a path. If you want to inspect the configuration source and rules in files, open the relevant .gitattributes files from the root down to subdirectories.

Key points to remember:

- Attributes apply by path and can be declared across multiple .gitattributes files.
- Rules in subdirectories can supplement or override rules from parent directories.
- Rules appearing later in a file can change the outcome for matching patterns.
- Attributes do not alter bytes already stored in commits; they change how Git processes paths in relevant operations.

## 3. Viewing Default Diffs of Binary Files

Suppose you replaced the logo image and want to view the change:

~~~bash
git diff -- design/logo.png
~~~

If Git identifies the file as binary, output normally reports that the two versions differ instead of showing changed lines:

~~~text
Binary files a/design/logo.png and b/design/logo.png differ
~~~

This is not an error. Git is reporting that the blob contents differ but cannot be meaningfully represented as a line diff.

For a staged file, view changes against HEAD:

~~~bash
git diff --cached -- design/logo.png
~~~

Between two commits:

~~~bash
git diff v1.2.0 v1.3.0 -- design/logo.png
~~~

These commands answer whether the file changed, but they do not visually show which region of an image changed, which PDF page differs, or which archive entries were added.

## 4. Using Statistics and Metadata When Content Cannot Be Read

When a binary diff cannot display content, you can still inspect the scope of changes.

### 4.1. Per-File Statistics

~~~bash
git diff --stat HEAD~1 HEAD
git diff --stat -- design/
~~~

Output shows which files changed and the relative size of changes. For binary files, Git cannot count added/removed lines in the usual way.

### 4.2. Machine-Readable Statistics

~~~bash
git diff --numstat HEAD~1 HEAD
~~~

For binary files, the two line-count columns are typically shown as dashes:

~~~text
-       -       design/logo.png
~~~

The dashes mean Git does not provide added and removed line counts for that file.

### 4.3. Viewing Path Names and Statuses

~~~bash
git diff --name-status HEAD~1 HEAD
~~~

Common statuses:

| Symbol | Meaning |
|---|---|
| A | Added file |
| M | Modified file |
| D | Deleted file |
| R | Renamed |
| C | Copied |
| T | Type or mode change |

### 4.4. Viewing Metadata Changes

~~~bash
git diff --summary HEAD~1 HEAD
git diff --raw HEAD~1 HEAD
~~~

Summary can show created, deleted, renamed, or mode-changed files. Raw output shows old/new modes, old/new object IDs, and change statuses. This information is helpful when reviewing binary assets or investigating why a file is marked as changed.

## 5. Distinguishing Content Changes from Metadata Changes

A file can appear changed because its content bytes changed, or because its mode or path changed.

Examples:

- An image re-exported with identical visuals but different EXIF metadata or embedded timestamps.
- A PDF regenerated with the same visible content but different metadata, IDs, or object ordering.
- An executable file whose executable bit changed.
- An asset renamed without changing its bytes.
- An archive repackaged with different entry ordering or timestamps.

Use the following commands to investigate:

~~~bash
git diff --summary BASE..HEAD
git diff --raw BASE..HEAD
git diff --name-status BASE..HEAD
~~~

If a file was renamed, Git usually detects renames based on content similarity; a filename change does not necessarily mean the blob changed. You can inspect rename details with:

~~~bash
git diff --summary -M BASE..HEAD
git diff --name-status -M BASE..HEAD
~~~

If you need to check a file's object ID at each commit:

~~~bash
git rev-parse 'BASE:design/logo.png'
git rev-parse 'HEAD:design/logo.png'
~~~

If the object IDs match, both snapshots reference the exact same blob. If they differ, the stored content bytes differ, even if the image looks visually identical.

## 6. Why You Should Not Force Every Binary File into a Text Diff

Git supports the --text (or -a) option to treat all files as text:

~~~bash
git diff --text -- path/to/archive.zip
~~~

This option is useful when a file is actually text but Git misclassified it, or when inspecting structured text-like data. However, for images, videos, archives, or executables, the output can contain control bytes, unprintable characters, or massive amounts of data.

Avoid using --text as a routine way to review binaries because:

- Output can be unreadable or corrupt terminal rendering.
- Lines have no meaningful correspondence to the file format's structure.
- Line diffs cannot explain visual or internal logical changes in the file.
- It can produce huge logs and patches.

If you need to force Git to treat a file as text, first confirm the format is genuinely text and consider declaring an appropriate text attribute. Do not change attributes of binary formats just to suppress the "Binary files differ" message.

## 7. Creating Binary Patches with git diff --binary

The default diff for a binary file normally only states that the files differ. If you need to package binary changes into a patch to transfer to another repository, use --binary:

~~~bash
git diff --binary BASE HEAD -- design/logo.png > logo-change.patch
~~~

The --binary option instructs Git to generate a binary patch representation that can be applied with git apply. For text changes in the same patch, Git still generates standard text diffs.

Verify the patch before applying:

~~~bash
git apply --stat logo-change.patch
git apply --check logo-change.patch
~~~

If the check succeeds and you want to apply it:

~~~bash
git apply logo-change.patch
~~~

Notes:

- A binary patch stores the data needed to reconstruct the target version; patch size can be large.
- The patch must be applied on a state matching the base from which it was created.
- --check only verifies applicability; it does not validate the meaning of the file contents.
- git apply updates the working tree from the patch; it does not create a commit automatically.
- If the patch contains unexpected paths or out-of-scope changes, read its stats and inspect contents before applying.

To create a patch for all tracked changes between two commits:

~~~bash
git diff --binary BASE HEAD > release-assets.patch
~~~

To apply it in the target repository:

~~~bash
git apply --check release-assets.patch
git apply release-assets.patch
~~~

After applying, verify again:

~~~bash
git status --short
git diff --stat
~~~

Do not send patches over public channels if they contain binary assets, internal data, or restricted content.

## 8. When Do You Need Specialized Comparison Tools?

There is no single display format suitable for every binary file. Choose a tool based on the format and the review question:

| File Type | Common Questions | Appropriate Tool |
|---|---|---|
| PNG/JPEG/rasterized SVG images | Which pixels, regions, or dimensions changed? | Image diff, overlay, side-by-side viewer |
| PDF | Which pages changed, text or layout? | PDF compare or page-by-page renderer |
| DOCX/ODT | How did text, tables, and document structure change? | Office document compare or text conversion |
| ZIP/JAR | Which entries were added, deleted, or replaced? | Archive listing, checksums, and binary viewer |
| Fonts | Which glyphs, font tables, or metadata changed? | Font inspection tool |
| Audio/video | Did media content, codec, duration, or metadata change? | Media inspector or format-specific diff tool |
| Executables | Which bytes, sections, symbols, or dependencies changed? | Hex diff, binary analysis, and package inspection |

A tool can show that two files differ, yet it does not prove the change is correct. For example, pixel differences between two images could be a valid design update or an export bug; review against product requirements.

## 9. What Is git difftool?

git difftool is Git's integration interface for external diff programs. Instead of printing a diff to the terminal, Git prepares both versions of the file and invokes the configured tool to display them.

Difftool uses the exact same comparison-endpoint syntax as git diff:

| Command | Two Sides Compared |
|---|---|
| git difftool -- file | Index and working tree |
| git difftool --cached -- file | HEAD and index |
| git difftool A B -- file | Tree of A and tree of B |
| git difftool A..B -- file | Snapshot A and snapshot B |
| git difftool --dir-diff A B -- folder/ | Two directory trees within the specified scope |

Difftool only assists with viewing and comparing. It does not create commits, perform merges, or resolve conflicts. When you need to resolve merge conflicts, look into git mergetool and dedicated conflict-resolution workflows.

## 10. Viewing Diff Tools Supported by Git

Run:

~~~bash
git difftool --tool-help
~~~

Git lists the tool names that the current installation knows how to invoke. The actual list depends on your operating system, installed programs, and Git configuration.

Common tools:

- vimdiff: side-by-side comparison inside Vim.
- meld: graphical interface for comparing two or more files.
- kdiff3: comparison and merge assistance.
- bc: Beyond Compare interface on supported environments.
- opendiff: FileMerge tool on macOS.
- p4merge: Perforce's visual merge and diff tool.
- winmerge: WinMerge tool when Git is configured to invoke it.

Available tool names can vary across Git versions. Use the exact name shown by --tool-help rather than assuming every tool is pre-installed.

## 11. Selecting a Tool for a Single Comparison

You can specify a tool directly without changing default configuration:

~~~bash
git difftool --tool=meld HEAD~1 HEAD -- design/logo.png
~~~

This example tells Git to open Meld to compare the logo file between two commits.

Compare unstaged changes in the working tree:

~~~bash
git difftool --tool=meld -- design/logo.png
~~~

Compare staged content against HEAD:

~~~bash
git difftool --cached --tool=meld -- design/logo.png
~~~

Compare an entire asset directory:

~~~bash
git difftool --dir-diff --tool=meld HEAD~1 HEAD -- design/
~~~

The --dir-diff option tells Git to set up a directory-level comparison. The chosen tool must support directory comparison to display properly. If the tool only supports file-by-file comparison, run difftool on individual files or let Git open changed files sequentially.

## 12. Configuring a Default Tool for a Repository

If you frequently use the same tool, you can configure it in the current repository:

~~~bash
git config --local diff.tool meld
~~~

Then invoke:

~~~bash
git difftool HEAD~1 HEAD -- design/logo.png
~~~

Git uses the configured tool whenever no --tool option specifies another tool.

You can control whether Git prompts for confirmation before opening each file:

~~~bash
git config --local difftool.prompt false
~~~

When prompt is disabled, Git launches the tool without asking before every file. If you want to keep prompting, unset that local configuration:

~~~bash
git config --local --unset difftool.prompt
~~~

Inspect configuration along with its source:

~~~bash
git config --show-origin --show-scope --get diff.tool
git config --show-origin --show-scope --get difftool.prompt
~~~

A --local configuration applies only to the current repository. If you want a default across all of your repositories, you can use --global, keeping in mind that it affects other projects as well.

## 13. Configuring a Custom difftool Command

If your tool is not in the built-in tool list, Git lets you declare a custom command. For example, a hypothetical program named binary-viewer that takes two file paths:

~~~bash
git config --local diff.tool binaryviewer
git config --local difftool.binaryviewer.cmd 'binary-viewer "$LOCAL" "$REMOTE"'
~~~

Then:

~~~bash
git difftool --tool=binaryviewer -- path/to/file.bin
~~~

In a custom command:

- $LOCAL is the path to the local-side file version in the comparison.
- $REMOTE is the path to the other-side version.
- Git creates appropriate temporary files for the invoked tool.
- The command must follow the shell syntax of the environment running Git.

The names LOCAL and REMOTE follow difftool conventions; they do not necessarily mean the local working tree and a remote Git server. They simply represent the two sides of the active comparison.

If you want to test a command without saving configuration:

~~~bash
git difftool --extcmd='binary-viewer' -- path/to/file.bin
~~~

The --extcmd option asks Git to invoke an external program using the supported mechanism for that single run. Check the help documentation of your Git version if the custom command needs multiple arguments or special path quoting.

Never put commands from untrusted sources into diff configuration. A difftool runs with your current account's permissions; only configure executables you installed and verified.

## 14. Using textconv for Binary Files Convertible to Text

Some binary formats can be converted into useful textual representations. Examples:

- PDFs can have text extracted page by page.
- Images can have metadata extracted such as dimensions, camera info, or color profiles.
- Office documents can be converted to text or XML structure for review.
- Archives can have entry names, checksums, and sizes listed.

Git supports text conversion drivers (*textconv*). A driver receives a file's content and outputs a text representation for Git to diff.

Example with PDF files and the pdftotext utility:

In .gitattributes:

~~~gitattributes
*.pdf diff=pdftext
~~~

In local Git configuration:

~~~bash
git config --local diff.pdftext.textconv 'pdftotext -layout'
~~~

Then:

~~~bash
git diff HEAD~1 HEAD -- docs/manual.pdf
~~~

Git invokes textconv on both versions of the file and compares the extracted text. This helps review wording changes without manually opening every PDF.

Tool names and syntax depend on the installed converter. If textconv does not work, check whether the executable is in PATH and verify driver configuration:

~~~bash
git config --show-origin --show-scope --get-regexp '^diff\.pdftext\.'
git check-attr diff -- docs/manual.pdf
~~~

### 14.1. Textconv Is Not a Binary Patch

Textconv is a one-way conversion strictly for display. The generated text output is not the original file content and cannot be used as a patch to reconstruct a PDF or image.

Do not use textconv output as a substitute for binary objects in a repository. When transferring binary files, use Git objects, binary patches, or an appropriate artifact storage system.

### 14.2. Textconv Can Omit Important Differences

Two PDFs can yield identical extracted text while differing in layout, images, fonts, or metadata. Similarly, two images can share identical metadata while differing in pixels. Textconv compares only what the converter outputs.

Therefore, use textconv as a supplementary perspective. For critical changes, open the file in a viewer or specialized tool to verify both rendered content and required metadata.

### 14.3. Enabling or Disabling textconv Per Run

You can tell Git to use textconv:

~~~bash
git diff --textconv HEAD~1 HEAD -- docs/manual.pdf
~~~

Or disable textconv to see how Git handles the raw blob:

~~~bash
git diff --no-textconv HEAD~1 HEAD -- docs/manual.pdf
~~~

When debugging, compare both outputs to determine whether a difference originates in the raw data or in the converter.

## 15. Comparing Images with difftool

Suppose a repository has two versions of a PNG logo. An image comparison tool can show both images side by side, overlay them, or generate a pixel-difference map.

Workflow:

1. Identify the two commits or states to compare.
2. Confirm the file actually changed using git diff --name-status.
3. Choose an image viewer or diff tool with image support.
4. Open both versions via git difftool.
5. Check dimensions, alpha channels, color profiles, and visual content if those factors matter.

Example:

~~~bash
git difftool --tool=meld HEAD~1 HEAD -- assets/logo.png
~~~

If Meld or your current tool cannot render PNGs as desired, use a dedicated image viewer or a custom difftool command. Git only passes both file versions to the tool; image-comparison capabilities depend on the external program.

Do not conclude two images are identical merely because their metadata matches. If pixel-level comparison is required, use a tool capable of pixel diffing or overlays.

## 16. Comparing PDFs and Office Documents

For PDFs, you can combine two approaches:

- Textconv to spot added, deleted, or modified wording.
- PDF compare to inspect layout, pages, images, tables, and fonts.

For DOCX or ODT, a tool can extract XML/text or open both versions directly in an office application. Keep in mind that ZIP-based office files contain many internal components; a small edit can modify multiple XML entries.

Textconv configuration can use a converter suited to the format. Do not assume every DOCX file can be meaningfully compared simply by forcing Git to read it as text.

For documents with legal, technical, or business significance, review both content and final layout. A clean text diff does not guarantee pages or diagrams did not break.

## 17. Comparing Archives, Packages, and Executables

For ZIP, JAR, or binary packages, a typical review workflow includes:

1. View git diff --stat to see which files changed and how sizes changed.
2. Check checksums or object IDs to confirm whether the blob changed.
3. List archive contents in both versions using an appropriate tool.
4. Compare added, deleted, or replaced file entries.
5. If needed, extract critical entries and compare their contents individually.
6. For executables, use binary, symbol, or dependency analysis tools when you need to understand what changed.

Do not rely solely on files having the same name or nearly identical sizes. Two archives can differ due to timestamps or entry ordering even when inner files are unchanged; conversely, a small internal change can alter the checksum of the entire archive.

If a package is a build artifact, consider storing it in an artifact registry rather than committing it to the source repository. If it must be versioned alongside source code, establish a policy around Git LFS or an artifact system.

## 18. Git LFS and Binary Diffs

Git LFS stores large file contents outside the regular object database and commits a pointer file into Git. The pointer contains metadata identifying the LFS object, such as its OID and size.

Consequently, when diffing two commits containing LFS files, you may see changes to the pointer rather than the actual content bytes. This is not an error; Git is comparing the content stored inside the main repository.

When reviewing LFS files:

- Verify that the LFS objects have been downloaded and are accessible.
- Use Git LFS tools and an appropriate viewer to open both actual versions.
- Compare metadata/checksums and format-specific contents.
- Do not draw conclusions solely from pointer changes.

For repositories using LFS, ensure team members and CI have Git LFS installed, have access to the endpoint, and fetch all required objects before running checks or releases.

## 19. Using difftool for Multiple Files and Directories

If a commit modifies many binary assets, a directory diff provides an overview of added, deleted, and modified files.

Example:

~~~bash
git difftool --dir-diff --tool=meld HEAD~1 HEAD -- assets/
~~~

The tool receives two directory trees representing the two sides. You can browse files and open differing ones in the corresponding viewer.

If the tool does not support directory diffs or cannot render binaries, list changed files first:

~~~bash
git diff --name-status HEAD~1 HEAD -- assets/
~~~

Then open each path needing review:

~~~bash
git difftool --tool=meld HEAD~1 HEAD -- assets/logo.png
git difftool --tool=meld HEAD~1 HEAD -- assets/banner.png
~~~

Not every difftool handles hundreds of binary files efficiently. Restrict pathspecs by asset group or file type under review.

## 20. Checking Configuration and Troubleshooting difftool

If Git does not open the tool as expected, check configuration:

~~~bash
git config --show-origin --show-scope --get diff.tool
git config --show-origin --show-scope --get difftool.prompt
git config --show-origin --show-scope --get-regexp '^difftool\.'
~~~

Verify whether the tool is recognized:

~~~bash
git difftool --tool-help
~~~

Common issues:

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Git opens a different editor | diff.tool points to another tool | Inspect config with origin |
| Executable not found | Tool is not installed or missing from PATH | Verify executable in shell |
| Git prompts before each file | difftool.prompt is enabled | Use --no-prompt or local config |
| Tool opens but cannot read binary | Tool supports text only | Choose a format-appropriate viewer |
| No textconv output | Driver unmapped or executable failed | Check .gitattributes and diff.<driver>.textconv |
| PDF diff shows only partial changes | Textconv only extracts text | Open PDF compare to inspect layout |
| Directory diff does not work | Tool does not support directory comparison | Use another tool or compare file by file |

To run once without prompting:

~~~bash
git difftool --no-prompt --tool=meld HEAD~1 HEAD -- assets/
~~~

If a custom command fails, test the executable directly against two sample files before invoking it through Git. Read the error message and check quoting on paths containing spaces.

## 21. Distinguishing difftool from mergetool

These commands serve different purposes:

| Command | Purpose | Result |
|---|---|---|
| git diff | Display differences in the terminal | Text diff or notice that binaries differ |
| git difftool | Launch an external tool to inspect two versions | Assists with review and comparison |
| git mergetool | Launch a tool to resolve conflicted files | Produces merged content to stage |
| git apply | Apply a patch to the working tree | Updates files according to the patch |

Do not use difftool expecting it to resolve conflicts automatically. When a merge stops due to conflicts, understand the base/ours/theirs versions and use mergetool or manual edits, then stage the resolved files.

## 22. Binary Change Review Workflow Before Commit or Release

A practical workflow:

1. Run git status to identify which binary files are new, modified, or deleted.
2. Use git diff --name-status and --stat to see the scope.
3. Use git check-attr to verify binary/text attributes.
4. Determine which two versions to compare: index vs. working tree, HEAD vs. index, or two commits.
5. Select a viewer or custom diff tool appropriate for the format.
6. Check metadata, checksums, or archive entry listings if needed.
7. Consider repository size impact and LFS/artifact policies.
8. Review the final content before staging or committing.
9. Document why the asset changed if reviewers cannot infer it from the diff.

Example command sequence:

~~~bash
git status --short
git diff --name-status
git diff --stat
git check-attr -a -- assets/logo.png
git difftool --tool=meld -- assets/logo.png
git diff --cached --stat
git diff --cached --check
~~~

If the file is already staged, add --cached to difftool so it properly compares the index content against HEAD. Always confirm the diff is opening the exact two sides you intend to review.

## 23. Common Mistakes

- **Thinking Git does not support binary files.** Git stores blobs normally; only the diff display differs.
- **Forcing images or archives to be diffed as text.** Output can be meaningless and unhelpful for review.
- **Using --binary to visually inspect images.** Binary patches are for transferring and applying changes, not visual inspection.
- **Assuming textconv shows every change.** It only compares the text representation emitted by the converter.
- **Confusing difftool with mergetool.** Difftool is for viewing; mergetool is for resolving conflicts.
- **Configuring a tool whose executable is not installed.** Git recognizes the tool name, but the OS cannot find the program.
- **Misidentifying the two comparison sides.** Difftool might compare index vs. working tree while you intended two commits.
- **Failing to check real LFS files.** Git diff may only show pointer changes.
- **Ignoring metadata and checksums.** A file can change metadata without altering visible content, or vice versa.
- **Reviewing only statistics.** --stat does not replace opening and inspecting the asset's contents.

## 24. Key Takeaways

Git stores binary files as blobs just like any other file, though it normally does not generate line diffs for non-text content. Use --stat, --numstat, --summary, --raw, and --name-status to see which files changed; use --binary when you need to produce an applicable patch; and only use --text once you have confirmed the data is genuinely readable as text. For visual reviews, use git difftool with a viewer suited to the format. Textconv is useful when a textual representation can be extracted, though it does not replace inspecting the original content. Always confirm the exact two versions, the right tool, and the right scope before concluding a binary change is valid.
