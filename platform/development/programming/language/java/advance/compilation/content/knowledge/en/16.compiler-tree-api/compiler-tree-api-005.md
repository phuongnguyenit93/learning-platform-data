# Determining Source Positions to Report Errors or Display Java Syntax Tree Analysis Results

## 1. The Problem: Mapping from an AST Node Back to the Exact Source Line and Column

A Java analysis tool often traverses the **abstract syntax tree (AST)** to find method invocations, declarations, invalid expressions, or source rules to warn about. However, users do not want to see only the message “detected Math.max call”; they need to know **which file, which line, which column, and which character span** to jump to the position, underline it, or show suggestions in the editor.

In the JDK's Compiler Tree API, a `Tree` represents a syntactic structure and does not inherently contain line/column numbers. You must combine:

- `CompilationUnitTree`: root of a source file, knowing `getSourceFile()` and `getLineMap()`.
- `Trees.getSourcePositions()`: returns `SourcePositions`, mapping a `Tree` node within the matching compilation unit to a **character offset** from the start of the file.
- `SourcePositions.getStartPosition(unit, tree)` and `getEndPosition(unit, tree)`: start/end positions when known by the compiler.
- `LineMap.getLineNumber(offset)` and `getColumnNumber(offset)`: convert offsets to lines/columns according to the actual source text.
- `TreePathScanner`: scans the AST and maintains the `TreePath` context from the compilation unit to the node under inspection.
- `Trees.printMessage(kind, message, tree, compilationUnit)`: lets a javac-based tool emit a diagnostic attached to the source node.
- `DiagnosticCollector`: collects compiler errors/warnings as structured data.

Main flow:

~~~text
         .java file
            |
       JavacTask.parse()
            |
    CompilationUnitTree
            |
      TreePathScanner
            |
        Tree node
            |
 SourcePositions.getStartPosition(unit, node)
            |
    0-based char offset
            |
 CompilationUnitTree.getLineMap()
            |
       line / column
            |
   Console / IDE / code review / warning
~~~

**Mandatory rule:** always pair a `Tree` with the exact `CompilationUnitTree` that contains it. An offset of 120 in file A means nothing if converted to a line using file B's `LineMap`.

## 2. Different Position Types and Their Meanings

| Quantity | API | Coordinate system |
| --- | --- | --- |
| Source file | `unit.getSourceFile()` | `JavaFileObject` and URI of the compilation unit |
| Start offset | `positions.getStartPosition(unit, node)` | Character position from the start of source, **0-based** |
| End offset | `positions.getEndPosition(unit, node)` | End position of the syntactic span, may be unknown |
| Line | `unit.getLineMap().getLineNumber(start)` | Line in file, **1-based** |
| Column | `unit.getLineMap().getColumnNumber(start)` | Column on line, **1-based**, accounts for tab expansion |
| Diagnostic coordinates | `Diagnostic.getLineNumber()` / `getColumnNumber()` | Provided by compiler, may not exist |
| Offset-form diagnostic positions | `Diagnostic.getStartPosition()` / `getPosition()` / `getEndPosition()` | Computed on the diagnostic's source, may be `NOPOS` |

The `SourcePositions` documentation specifies offsets measured from the beginning of the compilation unit, with the first character at position 0. `LineMap` performs the conversion. For tab characters, the column reflects the compiler's tab expansion rather than simply the character count of the substring from the newline.

Do not confuse:

- **Byte offset** in a UTF-8 file is not the same as the compiler's **character offset**. Vietnamese characters can occupy multiple bytes.
- **IDE line/column** may follow a different convention (some editor protocols use 0-based line/character).
- **End position** is not an “end line” or “character count” sent straight to the UI; before highlighting, convert both start and end to the editor's coordinate system.
- `Tree.toString()` formats the expression according to the compiler and does not return original text positions.

For synthesized nodes not present in source, or when the compiler lacks location info, `getStartPosition` / `getEndPosition` can return `Diagnostic.NOPOS` (value -1). Always check before calling `LineMap` or slicing source text.

## 3. Differences Among Tree, TreePath, and CompilationUnitTree

A `Tree` represents a single node such as `MethodInvocationTree`, `ClassTree`, `VariableTree`, or `LiteralTree`. A `CompilationUnitTree` represents *an entire source file*. `TreePath` holds the ancestor chain from the compilation unit to the node, which is very useful for finding the enclosing method/class or retrieving symbols/types after semantic analysis.

| Need | What to use |
| --- | --- |
| Determine coordinates in file | `SourcePositions` + `CompilationUnitTree` |
| Traverse method calls in file | `TreePathScanner.visitMethodInvocation` |
| Know enclosing ancestors/owner of a call | `TreePathScanner.getCurrentPath()` |
| Find corresponding declaration after analyze | `Trees.getElement(TreePath)` |
| Find resolved type | `Trees.getTypeMirror(TreePath)` |
| Attach warning to source | `Trees.printMessage` |
| Attach warning to declaration in an annotation processor | `Messager.printMessage` with the corresponding `Element` |

`TreePathScanner` is usually better suited than `TreeScanner` if the problem requires context and symbol resolution. For a simple syntactic check needing only line/column, `TreeScanner` can also suffice as long as you hold the right `CompilationUnitTree`.

**Do not call `Trees.getElement(path)` on a freshly parsed tree assuming full symbols exist.** To obtain accurate `Element`/`TypeMirror` values, you must run the necessary resolution/analyze phases and handle source errors; whereas obtaining syntactic positions usually only needs parse.

## 4. Complete Java 17+ Example: Printing Locations of Two Method Calls

The example uses `com.sun.source.*` in JDK module `jdk.compiler`. We build a program **to analyze source**, not an annotation processor. It reads a `.java` file, calls `JavacTask.parse()`, scans `MethodInvocationTree` nodes, and prints file/line/column.

Structure:

~~~text
project/
├── LocateCalls.java
├── src/
│   └── demo/Sample.java
└── out/               # LocateCalls tool classes
~~~

### 4.1. File src/demo/Sample.java

Keep whitespace, blank lines, and line breaks exactly as shown so line/column results match:

~~~java
package demo;

public final class Sample {
    public static void main(String[] args) {
        System.out.println(Math.max(2, 5));
    }
}
~~~

The line contains two nested method invocations: `System.out.println(...)` on the outside and `Math.max(2, 5)` inside.

### 4.2. File LocateCalls.java

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.LineMap;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;

public final class LocateCalls {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LocateCalls source-file");
        }

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics,
                             Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> input =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(Path.of(args[0])));

            JavacTask task = (JavacTask) compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, input);

            Iterable<? extends CompilationUnitTree> parsed =
                    task.parse();

            Trees trees = Trees.instance(task);
            SourcePositions positions = trees.getSourcePositions();

            for (CompilationUnitTree unit : parsed) {
                new TreePathScanner<Void, Void>() {
                    @Override
                    public Void visitMethodInvocation(
                            MethodInvocationTree node,
                            Void ignored) {

                        long start =
                                positions.getStartPosition(unit, node);
                        long end =
                                positions.getEndPosition(unit, node);

                        if (start != Diagnostic.NOPOS) {
                            LineMap map = unit.getLineMap();
                            System.out.printf(Locale.ROOT,
                                    "CALL %s @ %d:%d%n",
                                    node.getMethodSelect(),
                                    map.getLineNumber(start),
                                    map.getColumnNumber(start));
                        }

                        if (end != Diagnostic.NOPOS
                                && end < start) {
                            throw new IllegalStateException(
                                    "Invalid source span");
                        }

                        return super.visitMethodInvocation(
                                node, ignored);
                    }
                }.scan(unit, null);
            }
        }

        for (Diagnostic<? extends JavaFileObject> diagnostic :
                diagnostics.getDiagnostics()) {
            if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
                System.err.println(
                        diagnostic.getMessage(Locale.ROOT));
            }
        }
    }
}
~~~

### 4.3. Compile and run

Use JDK 17+ with `javac` and `jdk.compiler`; from the project directory:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out LocateCalls.java
java -cp out LocateCalls src/demo/Sample.java
~~~

**Exact stdout** when the source file preserves exact line breaks and indentation:

~~~text
CALL System.out.println @ 5:9
CALL Math.max @ 5:28
~~~

The order above occurs because `TreePathScanner` visits the outer call first and then the nested inner call, and we print before calling `super.visitMethodInvocation`. Do not assume every custom traversal keeps the same order if the author modifies the scanner.

On Windows PowerShell, you can create the directory with:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out LocateCalls.java
java -cp out LocateCalls src/demo/Sample.java
~~~

The `Sample` program **does not need to be compiled** for LocateCalls to read its AST. If you want to run Sample as a standalone Java application, compile it into a class first:

~~~bash
javac --release 17 -d out src/demo/Sample.java
java -cp out demo.Sample
~~~

When running Sample, stdout is:

~~~text
5
~~~

**Hands-on verification:** the LocateCalls example was compiled and run on JDK 21 with `--release 17`. The two positions `5:9` and `5:28` are observed results from the exact sample above, not indexes guessed from node names.

## 5. Decoding Line/Column in the Example

Given the line:

~~~java
        System.out.println(Math.max(2, 5));
~~~

- There are **8 spaces** before `System`, so the `System.out.println` call starts at column **9**.
- `Math.max` sits inside `println( ... )`, starting at column **28**.
- Both start on **line 5**.
- In the AST, the outer `MethodInvocationTree` has a child node representing `Math.max(2, 5)`.
- Calling `getStartPosition(unit, outer)` points to the start of `System`; calling it for the inner node points to the start of `Math`.

The key point is that coordinates are **returned by the compiler from the AST**; counting spaces manually here only helps learners verify the output. For files with tabs, Unicode, CRLF, and complex tokens/comments, use `LineMap` rather than manually calculating `lastIndexOf("\\n")` and counting characters.

`getLineNumber` and `getColumnNumber` are **1-based**; `SourcePositions` offsets are **0-based**. If an IDE/editor expects 0-based indexing, convert at the boundary when sending data to the UI, without mutating the compiler's original data during analysis.

## 6. Getting the Full Source Span for Highlighting

To underline an entire expression instead of pointing to a single position, both start and end are needed:

~~~java
// Fragment inside scanner, assuming unit, node, and positions exist:
long start = positions.getStartPosition(unit, node);
long end = positions.getEndPosition(unit, node);

if (start != Diagnostic.NOPOS
        && end != Diagnostic.NOPOS
        && end >= start) {
    LineMap map = unit.getLineMap();
    long startLine = map.getLineNumber(start);
    long startColumn = map.getColumnNumber(start);
    long endLine = map.getLineNumber(end);
    long endColumn = map.getColumnNumber(end);
    // Send this span to the editor or create a code lens/report.
}
~~~

This is a **fragment**, not a standalone runnable Java file. In the typical javac model, the end offset is the position right after the syntactic span, convenient for a `[start, end)` highlight interval. However, the `SourcePositions` API guarantees start/end positions and may report `NOPOS`; when slicing source text or converting to an editor protocol, verify the compiler/consumer convention to avoid off-by-one errors.

**A span can cross multiple lines.** For example, a lambda body or invocation spanning three lines will have startLine different from endLine. Do not store only `line` and a “single-line length” and mis-highlight the rest.

When needing the actual characters:

~~~java
// Fragment: sourceText is the String of the matching compilation unit.
// Slice only after offsets and length have been checked.
if (0 <= start && start <= end
        && end <= sourceText.length()) {
    String snippet =
            sourceText.substring((int) start, (int) end);
}
~~~

Apply this only once certain that the offsets and `sourceText` content come from **the exact source version parsed by the compiler**, not file content subsequently modified in the editor. If source originates from an in-memory `SimpleJavaFileObject`, read that same object rather than guessing on the filesystem. For real source files, you can use `unit.getSourceFile().getCharContent(true)` and verify encoding/length.

Regarding Unicode: do not turn compiler offsets into **UTF-8 byte offsets** by casting to int and indexing directly into a byte array; for editors using UTF-16 code units, verify indexing rules and surrogate pairs.

## 7. Printing Diagnostics at the Exact Node with Trees.printMessage

If the tool wants to report a **warning/error with file and position info**, instead of manually printing:

~~~java
System.err.println("Avoid Math.max");
~~~

use the `Trees` API:

~~~java
// Fragment placed inside visitMethodInvocation of TreePathScanner.
// trees and unit must belong to the task currently being scanned.
trees.printMessage(
        Diagnostic.Kind.WARNING,
        "Review this invocation",
        node,
        unit);
~~~

`Trees.printMessage` accepts a `Diagnostic.Kind`, message, node, and the compilation unit containing the node. It attaches the source position to the diagnostic per contract, useful for compiler output and integrated tooling. You do not need to manually concatenate file path, `:`, line, and column into the message.

If you want to report errors only for one kind of call, **do not arbitrarily check `node.toString().contains("...")`**: that is tree text, which can be affected by syntax and cannot distinguish overloaded methods. Use `TreePathScanner.getCurrentPath()` and after semantic resolution call `Trees.getElement(path)` to find the actual method declaration, then inspect `ExecutableElement`, owner, and types under the Java language model. That goes beyond the purely syntactic coordinate-printing example, yet is essential when building real static analysis rules.

If an **annotation processor** needs to emit a warning, the `Messager.printMessage(Diagnostic.Kind, ..., Element)` API can attach errors to a declaration; it does not always let you pinpoint an AST expression inside a method. When a rule needs expression-level positions, `Trees` + `Tree` are usually more suitable. The two APIs serve different levels.

## 8. DiagnosticCollector and the Compiler's Own Error Coordinates

When the compiler analyzes source with errors, `DiagnosticCollector<JavaFileObject>` gives us structured information. To request actual type checking rather than just parsing, you can call `task.analyze()` after `task.parse()`, assuming the compiler/task is set up appropriately.

~~~java
// Fragment, must lie within a valid JavacTask lifecycle:
Iterable<? extends CompilationUnitTree> units = task.parse();
task.analyze();

for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    if (d.getKind() == Diagnostic.Kind.ERROR) {
        JavaFileObject file = d.getSource();
        System.err.printf(Locale.ROOT,
                "ERROR %s:%d:%d %s%n",
                file == null ? "<unknown>" : file.toUri(),
                d.getLineNumber(),
                d.getColumnNumber(),
                d.getMessage(Locale.ROOT));
    }
}
~~~

This is a **fragment**, not a standalone runnable program. On erroneous source, `analyze()` typically surfaces resolution/type-checking errors that `parse()` alone had not detected. Do not call `task.call()` after using individual analysis phases in a way disallowed by the tool contract; manage the `JavacTask` lifecycle explicitly.

Important methods of `Diagnostic`:

| Method | Information |
| --- | --- |
| `getKind()` | Error, warning, mandatory warning, note, etc. |
| `getSource()` | Source file object or null |
| `getLineNumber()` | Source line if available, or `NOPOS` |
| `getColumnNumber()` | Source column if available, or `NOPOS` |
| `getPosition()` | Focal diagnostic position |
| `getStartPosition()` | Start of diagnostic span if available |
| `getEndPosition()` | End of diagnostic span if available |
| `getCode()` | Tool diagnostic code |
| `getMessage(Locale)` | Display message; wording depends on JDK/locale |

For IDE integration, retain **kind, file, offsets/line/column, and code** instead of parsing javac's stderr formatting with regex. Not every diagnostic has a source line/column, for example option errors or build-setup messages. Check `NOPOS` to display a project-level warning if no node can be located.

Once you have an AST node, `SourcePositions` usually gives the span of **the syntactic node**; `Diagnostic` gives the span **chosen by the compiler to report the error**. The two spans may not coincide, and that is not necessarily a compiler bug: a diagnostic might underline only the method name, whereas `MethodInvocationTree` encompasses the entire call with arguments.

## 9. Using TreePathScanner to Keep Context During Analysis

`TreePathScanner` provides `getCurrentPath()` inside the visitor. The path helps identify the parent node, enclosing method, and resolved element. Example:

~~~java
// Fragment inside scanner:
@Override
public Void visitMethodInvocation(MethodInvocationTree node,
                                  Void unused) {
    TreePath path = getCurrentPath();
    // path.getLeaf() is the node of this invocation.
    // path.getParentPath() leads to the parent AST node.
    // trees.getElement(path) is useful after analyze().
    return super.visitMethodInvocation(node, unused);
}
~~~

Not every invocation corresponds to a successfully resolved method: source may be broken, a processor may generate code in a later round, or overload resolution may fail. In such cases, `trees.getElement(path)` may return null or parts of the model may be error types; the analysis tool must not crash.

When traversing multiple source units, create a new scanner per unit or pass the exact unit into the visitor context, rather than using a global variable pinned to the first file. `CompilationUnitTree.getSourceFile()` is the source to report the corresponding file.

You can obtain a tree from an `Element` with `Trees.getTree(element)` or a path with `Trees.getPath(element)` in cases where the compiler holds a source tree for that declaration, but **there is no guarantee** every external library class has a source AST available. A class found only via a dependency JAR may have an `Element` and `TypeMirror` without any source tree/offset in the current compilation.

## 10. Distinguishing Syntactic Node Positions from Character Positions Seen by Users

The AST does not preserve every lexical detail the way a verbatim source-preserving parser would. Some punctuation, whitespace, comments, or annotations/qualifiers may map to different nodes, and the token you want to highlight does not necessarily coincide with the entire AST node span.

For example, when inspecting the call:

~~~java
service
    .getClient()
    .send("ok");
~~~

`MethodInvocationTree` encompasses the entire call; `MethodSelect` is one subtree; the arguments are other subtrees. If you only want to underline the `send` identifier, taking start/end of **the entire invocation** might highlight the whole call chain. Pick the exact subtree, or use an additional token/source reader when you need the exact position of a specific punctuation mark or name in syntax.

Do not assume `node.toString().indexOf("send")` added to the node's start offset produces accurate coordinates: `toString()` may format differently from source text and does not preserve comments/whitespace. Use `SourcePositions` for appropriate nodes; if token-level precision beyond AST coverage is needed, combine with a lexer/token API with a clear contract and keep the same source snapshot.

In addition:

- **Tabs:** `LineMap.getColumnNumber` accounts for tab expansion; counting chars manually in a substring is often wrong.
- **CRLF/LF:** changing the line map after normalizing newlines can skew offsets unless the source snapshot is also replaced.
- **Unicode:** Java source can include supplementary characters outside the BMP or Unicode escapes. Avoid assuming offset == UTF-8 byte index.
- **Modified source files:** positions taken from an old build must not be blindly applied to a newer editor buffer.
- **Synthetic/recovered trees:** the compiler creates nodes without spans or with incomplete positions; there must be a fallback.
- **Multiple files with the same name:** `Sample.java` in two different source roots must be distinguished using `JavaFileObject.toUri()` or a canonical file identifier, not just the basename.

A good analyzer records **URI, snapshot version, start/end offsets, and normalized line/column** (if the consumer needs them) so the UI aligns accurately. If no position is available, display a file/project-level error instead of fabricating line 1, column 1.

## 11. Common Mistakes When Building Source-Location Reporting Tools

| Symptom | Root error | How to fix |
| --- | --- | --- |
| Reports line 0/column 0 | Confusing 0-based offset with 1-based line/column | Convert using `LineMap` |
| Off only after encountering a tab | Computing column manually via `substring.length` | Use `LineMap.getColumnNumber` |
| Breaks on Unicode/emoji text | Using byte offset as char offset | Distinguish UTF-8 bytes from Java char offsets |
| Highlights wrong file | Using unit/LineMap of a different source | Carry the matching `CompilationUnitTree` with the node |
| `IndexOutOfBoundsException` during substring | Missing `NOPOS` check or mismatched source snapshot | Validate offset, bounds, and snapshot |
| Looking up positions of a class from an external JAR | No source AST for dependency | Use symbol metadata, fall back if no source exists |
| `getElement(path)` is null | Haven't run analyze or source has errors | Run the right phase and handle resolution errors |
| Highlights entire invocation instead of method name | Selected `MethodInvocationTree` too broadly | Choose the right subtree or source token |
| Printing warnings with `System.out.println` | Loses diagnostic/source location integration | Use `Trees.printMessage` |
| Using `node.toString()` then searching the file | Pretty-print does not match original source | Get offsets from `SourcePositions` |
| Wrong positions after edit | Cached offsets from an older source | Attach version/snapshot, re-parse after edits |
| `-1` appears in output | Compiler has no position for the node | Check `Diagnostic.NOPOS` |
| Diagnostic has line but no end span | Not every compiler supplies a full highlight range | Show caret at position or use a fallback |
| Duplicate messages on child/descendant AST | Scanner reports on both outer and inner invocation | Design rules by node kind and owner/context |

## 12. Workflow for Exporting AST Coordinates to IDEs or Static Analysis Reports

A reliable pipeline typically includes:

1. **Lock source:** record source URI, encoding, version/hash, or snapshot ID before analysis.
2. **Create JavacTask:** select compilation units, `--release`, classpath/module path, and annotation processing policy. Do not use inputs different from the file displayed in the editor.
3. **Parse AST:** obtain `CompilationUnitTree` and `Trees.getSourcePositions()`.
4. **Scan with context:** use `TreePathScanner`; at each reported node, keep the matching unit and path.
5. **Get valid offsets:** verify `getStartPosition` and `getEndPosition` differ from `Diagnostic.NOPOS` and satisfy valid ordering/bounds.
6. **Convert coordinates:** use `LineMap`. Choose 1-based/0-based convention at the UI interface layer, without scattering `+1/-1` adjustments across the analyzer.
7. **Verify semantics if the rule requires it:** execute `analyze` then use `Trees.getElement/getTypeMirror`, handling unresolved symbols.
8. **Emit diagnostics:** prefer the compiler diagnostic API or a structure with file/span/severity/code/message, avoiding a plain text string alone.
9. **Test concrete edge cases:** include nested calls, multi-line invocations, tabs, CRLF, Unicode, broken source, and generated nodes.
10. **Ensure freshness:** match the source snapshot before the editor highlights or applies a quick fix.

### Practice Exercises

- Run the `LocateCalls` example as-is to obtain `CALL System.out.println @ 5:9` and `CALL Math.max @ 5:28`.
- Add a blank line at the top of `Sample.java`; predict that both calls shift to line 6 and re-run to confirm.
- Replace the 8 spaces before `System` with 1 tab; use experimental output to check tab expansion in `LineMap`.
- Move `Math.max` onto the next line; compare start/end of the outer invocation and inner invocation.
- Add `trees.printMessage(Diagnostic.Kind.WARNING, "Review this invocation", node, unit)` inside the visitor; observe how the compiler attaches the warning to the node's position.
- Test source missing a `;`, distinguish parser diagnostics from custom analyzer warnings; do not assign fake positions to nodes for which the compiler returns `NOPOS`.
- If building an IDE integration, convert coordinates to editor conventions once at the boundary and test highlighting after file edits.

**Conclusion:** `SourcePositions` returns **offsets bound to an AST node and compilation unit**, `LineMap` converts offsets to **line/column in source**, and `Trees.printMessage` or `DiagnosticCollector` connects analysis findings to **positioned diagnostics**. Using these APIs instead of parsing `Tree.toString()` or counting newlines manually yields more accurate and extensible results when source contains nested expressions, Unicode, tabs, multiple files, and compiler errors.

## References

- [Java SE 17 — SourcePositions](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/SourcePositions.html).
- [Java SE 17 — LineMap](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/LineMap.html).
- [Java SE 17 — Trees](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/Trees.html).
- [Java SE 17 — TreePathScanner](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html).
- [Java SE 17 — JavacTask](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html).
