# Mapping diagnostics back to the right original source and location during in-memory Java compilation

When using `javax.tools.JavaCompiler` to compile source code created in memory, the compiler may return a `Diagnostic` pointing to a virtual file such as `string:///lab/First.java`. However, the learner or IDE user is editing **a document, code block in an editor, or original input snippet**. If the tool automatically adds a package, wrapper class, import lines, or generates intermediate code before invoking the compiler, the line/column reported by javac may **differ from the line/column in the original document**.

Therefore, the problem is not merely "getting diagnostics from javac" but **accurately mapping the (source, location) pair** from the source space seen by the compiler back to the document the user actually wrote. Getting this mapping wrong can cause an IDE to underline the wrong line, a grading system to point at the wrong answer, or a service to report user A's errors onto user B's source snippet.

The lesson has two levels:

1. **Compiling one or more virtual files verbatim:** you can use `Diagnostic.getSource()` along with `getLineNumber()`, `getColumnNumber()`, and `getPosition()` to associate a diagnostic with the right source, if the virtual file actually contains the exact original content.
2. **Compiling transformed sources:** a **source map / provenance map** recorded during code generation is required to translate offsets, lines, and columns of generated code back to the original source. Relying solely on javac's line numbers is insufficient.

The examples use **Java 17+**, `javax.tools`, and the compiler included in the JDK. Two key programs were verified by running them with **OpenJDK 21**.

## 1. Which source is a Diagnostic referring to?

For a physical file, javac usually displays messages tied to the real source path. For an in-memory file, `JavaFileObject` represents the source file and can carry a URI provided by the tool.

Example of a source object with a URI:

~~~text
string:///lab/First.java
~~~

The compiler may return a diagnostic containing:

~~~text
source  = string:///lab/First.java
line    = 5
column  = 28
kind    = ERROR
message = cannot find symbol ...
~~~

This is an **illustrative example of the fields**, not the guaranteed full stdout of a compiler version. Information accessed via the `Diagnostic` API is independent of how javac renders carets on stderr.

With the Java Compiler API, the key methods are:

| Method | Meaning |
| --- | --- |
| `getSource()` | Source associated with the diagnostic by the compiler; may be `null` |
| `getPosition()` | Offset from the start of the source object, **0**-based when valid |
| `getLineNumber()` | Line number of the diagnostic position, **1**-based when valid |
| `getColumnNumber()` | Column number of the diagnostic position, **1**-based when valid |
| `getStartPosition()` | Start position of the error span provided by the compiler |
| `getEndPosition()` | End position of the error span provided by the compiler |
| `getKind()` | `ERROR`, `WARNING`, `NOTE`, etc. |
| `getCode()` | Diagnostic code per the compiler implementation; may be null |
| `getMessage(Locale)` | Message text; may depend on implementation/locale |

According to `javax.tools.Diagnostic` documentation, diagnostics not associated with a position or file are **valid**. When there is no position, the API uses `Diagnostic.NOPOS`; the source may be `null`. Therefore, do not design systems assuming every warning has a line, column, and character span to underline.

### 1.1. Three coordinate systems to distinguish

**Original document coordinates:** the position in text that the user sees before the tool adds or removes content. If the editor numbers lines from 1 and columns from 1, a position might be line 2, column 20.

**Coordinates of the `JavaFileObject` received by the compiler:** offset and line/column in the code string returned by `getCharContent(boolean)`. When you prepend 2 lines of a wrapper class, the error location lies on line 4 of the source sent to the compiler even though it is only on line 2 of the original snippet.

**UI presentation coordinates:** may be a 0-based line/column pair (e.g., many editor APIs), a UTF-16 offset, or pixel positions. Converting from compiler data to UI also requires a consistent translation step.

**Do not use line numbers from the virtual source as original line numbers if any transformation occurred.** You must know the virtual source and the transformations applied.

## 2. Foundational step: keeping virtual source identity stable

When creating in-memory files, you can extend `SimpleJavaFileObject` and override `getCharContent(boolean)`:

~~~java
import java.net.URI;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;

final class MemorySource extends SimpleJavaFileObject {
    private final String code;

    MemorySource(String name, String code) {
        super(
            URI.create("string:///lab/" + name),
            JavaFileObject.Kind.SOURCE
        );
        this.code = code;
    }

    @Override
    public CharSequence getCharContent(
            boolean ignoreEncodingErrors) {
        return code;
    }
}
~~~

This is an **illustrative class without `main`**; include it in a program that invokes the compiler to use it. The URI ends in `.java` to match `JavaFileObject.Kind.SOURCE`, and the filename should match the corresponding public top-level class name.

Practical rules:

- Each source needs a **separate URI** within the compilation task's input set, such as `string:///lab/First.java` and `string:///lab/Second.java`.
- **Do not reuse one URI for multiple distinct documents** and rely only on display names in the UI.
- When multiple requests/document revisions coexist, include **document ID + revision/version** in the application's tracking data. A clean-looking relative URI is not globally sufficient.
- Record the **exact source string passed into the compiler**. If a compiler diagnostic is based on version A text while the UI displays edited version B, locations can be wrong even if mapping code is correct.
- Do not assume `toUri()` is a filesystem path: the `string:///` scheme is an application-defined virtual file identifier, not a file on disk.
- Do not trust URIs from untrusted sources as real file paths without validation: the application must avoid leaking internal paths or mixing up tenants when displaying errors.

**Key point:** in cases without content transformation, the mapping is one-to-one between **virtual file URI + content snapshot** and the original source document. If this pair cannot be determined, do not attempt to assign lines/columns to an arbitrary file.

## 3. Complete example 1: two in-memory sources, two errors in two different files

This example tests **reading `getSource()` properly** instead of attributing all diagnostics to the first file. Create `SourceDiagnostics.java`:

~~~java
import java.net.URI;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class SourceDiagnostics {
    static final class MemorySource extends SimpleJavaFileObject {
        private final String code;

        MemorySource(String name, String code) {
            super(
                URI.create("string:///lab/" + name),
                Kind.SOURCE
            );
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignore) {
            return code;
        }
    }

    public static void main(String[] args) throws Exception {
        String first = String.join("\n",
            "package lab;",
            "public class First {",
            "    public void run() {",
            "        int ok = 1;",
            "        System.out.println(okk);",
            "    }",
            "}");

        String second = String.join("\n",
            "package lab;",
            "public class Second {",
            "    int answer = \"wrong\";",
            "}");

        JavaCompiler compiler =
            ToolProvider.getSystemJavaCompiler();

        DiagnosticCollector<JavaFileObject> diagnostics =
            new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                 compiler.getStandardFileManager(
                     diagnostics, null, null)) {

            var output = Files.createTempDirectory("compiler-demo-");

            boolean success = compiler.getTask(
                null, manager, diagnostics,
                List.of("-proc:none", "-d", output.toString()),
                null,
                List.of(
                    new MemorySource("First.java", first),
                    new MemorySource("Second.java", second)
                )
            ).call();

            System.out.println("success=" + success);
        }

        List<String> errors = new ArrayList<>();

        for (Diagnostic<? extends JavaFileObject> d
                : diagnostics.getDiagnostics()) {
            if (d.getKind() != Diagnostic.Kind.ERROR ||
                    d.getSource() == null) {
                continue;
            }

            String path = d.getSource().toUri().getPath();
            String file =
                path.substring(path.lastIndexOf('/') + 1);

            errors.add(
                file + ":" + d.getLineNumber() + ":" +
                d.getKind()
            );
        }

        errors.sort(String::compareTo);
        errors.forEach(System.out::println);
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac SourceDiagnostics.java
java SourceDiagnostics
~~~

**Stdout verified with OpenJDK 21:**

~~~text
success=false
First.java:5:ERROR
Second.java:3:ERROR
~~~

**Why are there two diagnostics?**

- `First.java` has an undeclared reference `okk` on line 5, while the declared variable name is `ok`.
- `Second.java` attempts to assign a `String` to an `int` field on line 3.
- Both code snippets have separate URIs. The collector receives diagnostics attached to their respective sources.
- The program **filters for ERROR, skips diagnostics without a source, and sorts the strings** for stable presentation. The order in which javac emits diagnostics should not be used as a key to identify sources.

**Do not extract only the trailing filename as a long-term identity.** The snippet prints `First.java` and `Second.java` purely for learner readability. In a real system, two packages or two different users' documents might share the name `Main.java`; use the full URI or an internal source ID mapped to the URI.

### 3.1. The compiler does not automatically execute the compiled program

`success=false` is the result of the **compilation task**; the host program `SourceDiagnostics` still runs and prints error info normally. It does not mean the Java runtime executed `First` or `Second` code. Do not conflate **compile-time diagnostics** with exceptions thrown when running a compiled program.

In the example, `-proc:none` disables annotation processing to keep the test simple and avoid unintended processors altering diagnostics. `-d` specifies a temporary output directory; since the sources contain errors, do not assume the compiler generates valid classes for either.

## 4. Cases where getSource() and getPosition() are not enough

A reliable error-reporting system must handle:

| Status | Appropriate behavior |
| --- | --- |
| `getSource()==null` | Display a general diagnostic without picking an arbitrary file |
| `getPosition()==Diagnostic.NOPOS` | Display the message without creating a positional highlight |
| `getLineNumber()==NOPOS` | Do not default to line 1 |
| Offset exceeds snapshot length | Reject mapping and record an unmappable diagnostic |
| URI not in task's source registry | Display as a diagnostic from an unrecognized source; may be a generated source |
| Source object belongs to an old revision | Do not apply positions to the newer revision's text |
| Diagnostic points to a tool-generated wrapper | Associate with the generated source, do not blame the user's snippet |
| Diagnostic span crosses multiple original sources | Do not draw a fake continuous underline in an original document |

Some diagnostics concerning compiler options or the build environment are not tied to a `.java` file. That is not an API bug; it is simply a **category of issue without a specific source location**.

**Do not discard the message and diagnostic kind** when there is no position. A warning without a source can still be important, for instance due to compiler options or annotation processor configuration.

## 5. A harder problem: when original source has been transformed

Suppose a user enters the following two lines into a snippet editor:

~~~java
int ok = 1;
System.out.println(unknown);
~~~

This is a **code fragment inside a method**, not a complete standalone compilable Java file. The tool creates a wrapper class:

~~~java
class Wrapper {
    static void run() {
int ok = 1;
System.out.println(unknown);
    }
}
~~~

The compiler sees the error on line **4** of `Wrapper.java` because two lines were added above it. However, in the editor, `unknown` is on line **2**. If the system underlines line 4 in the editor, it has mapped it incorrectly.

Conceptual flow:

~~~text
Original source in editor: snippet, revision R
  line 1: int ok = 1;
  line 2: System.out.println(unknown);
                  |
                  | add prefix + suffix
                  v
Source sent to compiler: string:///generated/Wrapper.java
  line 1: class Wrapper {
  line 2:     static void run() {
  line 3: int ok = 1;
  line 4: System.out.println(unknown);
  line 5:     }
  line 6: }
                  |
                  v
Diagnostic: Wrapper.java, line 4, column 20
                  |
                  | source-map based on original character range
                  v
Correct display: snippet revision R, line 2, column 20
~~~

In the case of **only prepending a prefix and appending a suffix while keeping the snippet characters intact in between**, offset mapping is straightforward:

~~~text
generated = prefix + original + suffix

startOfOriginal = prefix.length()
endOfOriginal   = startOfOriginal + original.length()

If position p is in [startOfOriginal, endOfOriginal):
    originalOffset = p - startOfOriginal

Otherwise:
    position belongs to the wrapper or lies outside the mapped region
~~~

The key is **recording the code generation process** rather than guessing positions by searching for matching text in the generated file. Two source segments can have identical content; string searching will cause mismatches.

## 6. Complete example 2: mapping wrapper diagnostics back to the original snippet

Create `MapWrapped.java`:

~~~java
import java.net.URI;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class MapWrapped {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String code) {
            super(
                URI.create("string:///generated/Wrapper.java"),
                Kind.SOURCE
            );
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignore) {
            return code;
        }
    }

    static int[] lineColumn(String source, int offset) {
        int line = 1;
        int column = 1;

        for (int i = 0; i < offset; i++) {
            if (source.charAt(i) == '\n') {
                line++;
                column = 1;
            } else {
                column++;
            }
        }

        return new int[] { line, column };
    }

    public static void main(String[] args) {
        String original =
            "int ok = 1;\nSystem.out.println(unknown);";

        String prefix =
            "class Wrapper {\n    static void run() {\n";

        String suffix = "\n    }\n}\n";

        String generated = prefix + original + suffix;

        int start = prefix.length();
        int end = start + original.length();

        JavaCompiler compiler =
            ToolProvider.getSystemJavaCompiler();

        DiagnosticCollector<JavaFileObject> diagnostics =
            new DiagnosticCollector<>();

        boolean ok = compiler.getTask(
            null, null, diagnostics,
            List.of("-proc:none"),
            null,
            List.of(new Source(generated))
        ).call();

        System.out.println("success=" + ok);

        for (Diagnostic<? extends JavaFileObject> d
                : diagnostics.getDiagnostics()) {
            if (d.getKind() != Diagnostic.Kind.ERROR) {
                continue;
            }

            long p = d.getPosition();

            if (p == Diagnostic.NOPOS ||
                    p < start || p >= end) {
                System.out.println("unmapped");
                continue;
            }

            int relative = (int) p - start;
            int[] location = lineColumn(original, relative);

            System.out.println(
                "compiled=" + d.getLineNumber() + ":" +
                d.getColumnNumber()
            );
            System.out.println(
                "original=" + location[0] + ":" +
                location[1]
            );
        }
    }
}
~~~

Compile/run with JDK 17+ including a system compiler:

~~~bash
javac MapWrapped.java
java MapWrapped
~~~

**Stdout verified on OpenJDK 21:**

~~~text
success=false
compiled=4:20
original=2:20
~~~

### 6.1. Step-by-step walkthrough of the mapping

- `original` contains the exact fragment entered by the user: two lines, each ending according to LF rules in the Java string.
- `prefix` and `suffix` are system-generated content, **not part of the original document**.
- `start` and `end` define a **one-to-one region** between the original snippet and a character range in `generated`.
- `d.getPosition()` retrieves the offset returned by the compiler on the `Wrapper.java` source object.
- Because the position lies within the original range, we compute `relative=p-start`.
- `lineColumn(original, relative)` counts line/column on the **original snippet string**, not the wrapper string.
- The diagnostic about `unknown` on line 4 of the wrapper is displayed on line 2 of the snippet.

**Important condition:** the inserted snippet **does not alter characters** and uses LF line terminators. Therefore, subtracting the prefix length is accurate for the source snapshot in the example. If the tool automatically prepends four spaces to each line, converts CRLF to LF, alters Unicode escapes, or renames variables, this mapping is **no longer sufficient**.

### 6.2. This is a single-segment demo, not a general-purpose source map

The program only inspects `ERROR` diagnostics, has only one virtual source, and one insertion region. If a diagnostic is caused by the wrapper, it prints `unmapped`. In a real system you need to:

- Verify that `d.getSource()` actually points to the expected `generated/Wrapper.java`.
- Associate the source map with the right **document ID and revision**.
- Support multiple virtual files, multiple source segments, and multiple transformation kinds.
- Handle spans alongside `NOPOS` locations and errors inside generated boilerplate.
- Convert coordinates to the editor's convention (typically 0-based), rather than using 1-based values from diagnostics as in the stdout example.

**Do not pin errors located inside the wrapper onto the first or last character of the snippet just to "always show a highlight."** That produces misleading information for users.

## 7. Designing a source map for multiple segments and multiple documents

An authoring/grading system may assemble a Java class from regions:

~~~text
[boilerplate prefix]
[user A's snippet, revision 13]
[generated helper]
[user B's snippet, revision 8]
[boilerplate suffix]
~~~

Then there is only one virtual `JavaFileObject`, yet the content comes from **multiple distinct original sources**. A segment metadata table is needed:

| Metadata field | Example | Function |
| --- | --- | --- |
| generated URI | string:///run42/Combined.java | Identifies the source sent to the compiler |
| generated start | 120 | Start offset of the segment in generated source |
| generated end | 182 | Exclusive end offset in generated source |
| original document ID | editor://draft-A | Identifies the exact user document |
| original revision | 13 | Prevents mapping locations onto an edited version |
| original start | 0 | Start offset in the original document |
| mapping kind | exact-copy | Whether every character is preserved or complex mapping is needed |
| generated-only | true/false | Marks a tool-generated region without a direct original source |

**Invariant rule when using exact-copy segments:**

~~~text
generated[genStart : genEnd] ==
original[origStart : origStart + (genEnd - genStart)]

For p in [genStart, genEnd):
    originalOffset = origStart + (p - genStart)
~~~

If every segment has its `generated URI` or an index keyed by URI, the right segment can be found by the **(source URI, offset)** pair. When the number of segments is large, store segments sorted by generated start and use binary search instead of linear scanning for each diagnostic.

**Do not confuse source URIs with user-provided file paths.** Normalize and manage URIs at the application layer; real keys can be independent IDs mapped one-to-one to URIs used in the task. Two classes with the same simple filename in different packages must still have distinct identities.

### 7.1. More complex transformations

A simple prefix addition shifts offsets by a constant. However, other transformations are **non-linear**:

- Adding indentation to **every line**: after each newline, the offset shifts by an extra indent character count.
- Converting CRLF to LF: each line-break pair shrinks by one code unit compared to the old source.
- Inserting imports between segments: an extra generated-only segment is added in the middle.
- Replacing identifiers or escapes: the character count changes mid-segment.
- Merging multiple snippets: each snippet has different start/end offsets and document identities.
- Stripping comments or running a formatter: relative positions can shift across the whole file.

In these cases, a **source map generated concurrently with the transformation** is required. A maintainable approach is tagging every output segment with its provenance: generated-only, exact-copy, or token/character-level mapping. For rewrites that do not preserve 1-to-1 correspondence, clearly define precision as **character-level**, **token-level**, or merely **nearest source block**.

Do not assume every diagnostic can be mapped to an exact location. If the compiler reports an error on a system-generated token, the truth may be "error in generated code" or "original position unknown." Displaying that is more honest than underlining an arbitrary word.

### 7.2. When a generated span crosses two original segments

`getStartPosition()` and `getEndPosition()` may point to a span covering multiple tokens. With segment-based mapping, a span can only be mapped completely as a continuous range in the original document **when all parts share compatible provenance and contiguous ordering**.

If a span starts in snippet A and ends in a generated helper, do not produce a "continuous" highlight range on document A. You can:

1. Map only the **primary caret** if it lies inside a valid exact-copy segment.
2. Omit underlining the full span.
3. Display the diagnostic attached to the generated source and note the related origin at a lower level.
4. Provide a link to the generated file for users or developers to investigate.

Do not assume every compiler interprets `getEndPosition()` identically as an exclusive end index when building cross-compiler systems; consult the contract and test before using the API as a UI span.

## 8. Lines, columns, offsets, and UTF-16

### 8.1. Distinguishing 0-based and 1-based

With `Diagnostic`:

- `getPosition()` uses a **0-based offset**.
- `getLineNumber()` starts at **1** when a position is available.
- `getColumnNumber()` starts at **1** when a position is available.
- Many editor APIs use **0-based** lines and columns, so subtract 1 when passing to the editor.
- Some editors use **UTF-16 offsets**, whereas applications in other languages may count Unicode code points.

Do not compute `getLineNumber()-1` if the value is `NOPOS`. Check the value before converting to 0-based indices.

### 8.2. UTF-16 and surrogate pairs

Java `String` stores strings in UTF-16 code units. When code before an error point contains a Unicode character outside the Basic Multilingual Plane (such as an emoji), `String.length()` increases by **2** code units for that character.

With javac/Java Compiler API, use the exact **Java string sent to the compiler** and keep UTF-16 indexing consistent when subtracting prefixes and mapping offsets. **Do not take code point counts from JavaScript/Python and subtract them directly from Java UTF-16 offsets without conversion.** A multilingual tool should explicitly document its encoding/index convention in the source map.

Principle example:

~~~text
String:     "A😀B"
Code point: A | 😀 | B        = 3 code points
UTF-16:     A | high | low | B = 4 code units

Position of B by UTF-16 offset: 3
Position of B by Unicode code point offset: 2
~~~

If the editor API requires UTF-8 byte offsets, further conversion is needed; `String.length()` cannot be used directly.

### 8.3. LF, CRLF, and tabs

The `lineColumn` demo handles only LF. For Windows sources using CRLF or standalone CR, a production line mapper function needs to:

- Recognize **CR**, **LF**, and **CRLF** under a consistent policy.
- Count CRLF as **one line break**.
- Have a clear rule when an offset falls directly inside a CRLF pair.
- Separate **columns in code units** from **display columns after tab expansion**.
- Maintain a `lineStarts` table for fast offset mapping if the editor has many diagnostics.

If the tool decides to normalize all sources to LF before compiling, it must **record the normalization in the source map**; do not use post-normalization line/column numbers and pretend they match the original CRLF document.

### 8.4. Do not estimate positions by counting spaces in messages

Caret characters in text output can be affected by tabs or Unicode display width. `Diagnostic.getPosition()` and `getLineNumber()/getColumnNumber()` are much better structured than parsing stderr snippets with `^`. API positions still need proper conversion against the source snapshot, but many alignment bugs from text output are avoided.

## 9. Error codes and messages must also stay tied to the right source

Besides source/position, retain:

~~~text
DiagnosticRecord
  documentId
  revision
  originalLine / originalColumn / originalRange (if mapping is valid)
  generatedUri / generatedPosition
  kind
  code
  message
  mappingStatus
~~~

**`getCode()` is implementation-dependent** and may return `null`. Do not use a specific code as the sole key to route a diagnostic to an original document; source identity determines that.

`getMessage(Locale.ENGLISH)` or the application locale provides content for display. If multiple diagnostics share the same code or message, they **are not the same error**: different files or different positions must still remain separate records.

Nor should you treat the order in which the collector returns diagnostics as fixed across JDK releases or multiple compilation tasks. When the UI wants sorting, it can sort by **document + offset + severity**, while keeping the original identity before sorting.

**Errors from processors:** an annotation processor may emit diagnostics attached to an element/annotation/value; the compiler may also report errors from processor-generated source. Identify the actual diagnostic source, and only map back to the source using the annotation if the processor/tool provides proper provenance. Not every generated-source error has an exact location in the original annotation.

## 10. Designing an end-to-end workflow for an in-memory compilation tool

A system with an editor and compiler service should separate the steps:

~~~text
1. Receive request
   - documentId, revision, exact content, compilation options

2. Create immutable source snapshot
   - store originalText and line endings info

3. Build sources sent to compiler
   - separate JavaFileObject per URI
   - if transformed, store generatedText + sourceMap

4. Run JavaCompiler
   - configure file manager, classpath, options, processor policy
   - register DiagnosticCollector

5. Read each Diagnostic
   - getSource, getPosition, start/end, line/column, kind/code/message

6. Look up source record
   - based on URI + task ID/snapshot
   - never rely solely on simple filename

7. Map position/range
   - unchanged source: identity mapping
   - transformed source: source map
   - null/NOPOS/unmapped: no fake highlighting

8. Convert to editor coordinates
   - 0-based line/column or UTF-16 offset per editor API

9. Return result with revision
   - UI only displays highlights if revision still matches

10. Verify
   - test multi-file, generated wrappers, CRLF, Unicode, NOPOS
~~~

### 10.1. Immutable snapshots are as important as source maps

Suppose a user starts compiling at revision **17**, then types a new line at the top of the document creating revision **18** before the compiler returns results. Diagnostics may map accurately to revision 17 positions yet no longer be accurate for revision 18.

Safe solutions:

- Return the revision alongside the diagnostics.
- If the editor is already on a different revision, **do not apply highlights to old coordinates** without remapping according to the editor's edits.
- You can rerun compilation on the new revision or use document change tracking if the system supports it.
- Do not rely on having the same file count as proof that content has not changed.

For multi-tenant services, the source registry should be isolated by **request/tenant**. Do not leave an old request's URIs registered and accidentally receive diagnostics from a new request.

### 10.2. Be careful with JavaFileManager and generated sources

`JavaFileManager` may return file objects for sources/classes other than the source objects submitted directly by the user. When javac or an annotation processor generates code, diagnostics may point to a newly **generated JavaFileObject**.

Therefore, manage a registry containing:

- **Input sources** provided by the user.
- **Generated sources** created by templates/wrappers/processors.
- **Class/resource outputs** if tracking is needed.
- **Provenance** between generated sources and inputs when grounded.

In simple examples, `-proc:none` avoids unintended effects from annotation processors. In real systems using processing, do not disable processors blindly because the program may end up missing generated code; instead, control processor sources, outputs, and mappings.

## 11. Distinguishing simple line-number mapping from a proper source map

A common mistake is applying:

~~~text
originalLine = generatedLine - prefix_line_count
~~~

This formula **is only valid** in a very narrow case: every snippet line is preserved intact, each generated line has a contiguous origin, and no lines are added or transformed inside the snippet.

Even in snippet scenarios, the tool might:

- Add indentation to each line;
- Wrap a class/method while also modifying imports;
- Change line endings per operating system;
- Replace a placeholder with a longer expression;
- Insert helper lines between two snippets;
- Generate multiple Java files from the same document.

In those cases, **line-number mapping alone cannot yield the right column**, and may not yield the right line. Prefer offset mapping with explicit segments. Using line/column should only be the **final display step** after determining the exact origin offset.

**Useful policy:** an exact-copy source-map segment must prove that the output slice equals the original substring. If it cannot be proven, mark it as another mapping kind and provide only the precision you can guarantee.

## 12. Real-world errors and how to fix them

| Symptom | Common cause | Fix |
| --- | --- | --- |
| All errors appear in the first file | Not reading `Diagnostic.getSource()` | Use source identity for each diagnostic |
| Errors shifted down two lines | Compiler compiles a wrapper with a two-line prefix | Use a source map; do not use generated line as original line |
| Columns shifted on later lines | Tool adds per-line indentation | Record mapping per segment/line or per character |
| Error jumps to a file with the same name | Using `Main.java` as the sole key | Use the full URI/source ID |
| Errors attached to a newer revision | Editor changed content during compilation | Attach revision to snapshots and responses |
| Warning without position appears on line 1 | Not handling `NOPOS` or null source | Show general diagnostic without highlights |
| Highlight extends past EOF | Offset applied to wrong snapshot or wrong UTF-16 | Validate bounds + encoding convention |
| Error in generated helper blamed on user | Missing generated-only tag | Keep generated source and mappingStatus=unmapped |
| Annotation processor error points to generated file | Not tracking Filer output | Record provenance or report generated source |
| Valid URI yet wrong class | Registry reused / key collision | Key by task + URI + revision |
| Message content parsed incorrectly | Parsing stderr with regex | Use `DiagnosticCollector` |
| Virtual source not recognized as right file kind | Wrong URI/Kind or incompatible filename | Use URI ending in `.java` and `Kind.SOURCE` |

A QA process should intentionally introduce **errors at the start, middle, and end of source**, **two files with the same simple name in different packages**, **Unicode characters**, **CRLF**, **prefix-adding transforms**, and **diagnostics with no source position**.

### 12.1. Distinguishing mapping bugs from compiler errors

If `Diagnostic.getPosition()` is already right in the generated source yet the UI highlights the wrong spot in the original, the bug usually lies in **source map/editor conversion**. If the compiler places a diagnostic at a seemingly unrelated spot, that may be where the parser detected a missing semicolon or brace rather than a broken map.

Do not write logic that "finds a better location automatically" by searching for keywords in messages or source code. A variable name can appear multiple times; matching the first occurrence silently increases wrong locations.

### 12.2. When only javac errors on stderr are available

If running the compiler as an external process via `ProcessBuilder`, you may only receive stderr containing paths, lines, and carets. You can parse it to aid tooling, however:

- Message formats can change across versions and locales.
- Compile errors involving virtual files may lack real paths.
- Carets can be affected by tabs or terminal width.
- Not every diagnostic has a line/column.

When code runs inside the JVM and can use the Java Compiler API, `DiagnosticCollector` is a much better-structured and more reliable path for mapping.

## 13. Self-practice exercises

**Exercise 1 — Multiple files.** Run `SourceDiagnostics.java`, verify line 5 of First.java and line 3 of Second.java. Add another class with the same filename in a different package; design a URI registry without identity collisions.

**Exercise 2 — Wrapper.** Run `MapWrapped.java`, explain why javac returns `4:20` while the original snippet is `2:20`. Add a comment line to the prefix yourself and predict how compiler coordinates change; verify that the original location stays unchanged.

**Exercise 3 — Deleting the source map.** Suppose you only have the message `Wrapper.java:4:20` without knowing the prefix/suffix or original snippet. Do you have enough info to determine the editor file and position? Explain why not.

**Exercise 4 — Unicode.** Place a non-BMP character before the error in the snippet. Compare the offset measured by Java `String.length()` with the count of Unicode code points. Show why mixing the two systems shifts columns.

**Exercise 5 — CRLF.** Replace newlines in original with CRLF while keeping a mapping function that only counts LF and increments column for CR. Fix the mapper so CRLF counts as one line break; write tests for offsets right before/at/after the line terminator.

**Exercise 6 — Compiler error without source.** Handle a hypothetical diagnostic with `source=null` and `position=NOPOS`: what should the UI show and what should it not show?

**Exercise 7 — Generated source.** Suppose an annotation processor generates `GeneratedMapper.java` and the compiler reports an error inside it. Identify what evidence is needed to attribute this error back to the user annotation rather than attaching it arbitrarily to the original source.

**Exercise 8 — Code review.** An application currently runs `diagnostics.forEach(d -> editor.highlight(d.getLineNumber()-1))`. List at least five failure cases and propose a source/snapshot/source map data structure to fix it.

## 14. Self-check questions

1. Why is `Diagnostic.getSource()` a mandatory fact in a compilation task with multiple sources?
2. Which coordinate systems do `getPosition()` and `getLineNumber()` use?
3. When can `getSource()` be null, and what does `Diagnostic.NOPOS` mean?
4. Why is `URI.toString()` insufficient to identify the right revision of a document?
5. When is the mapping `originalOffset = generatedOffset - prefix.length()` accurate?
6. Why does adding per-line indentation break a constant-offset subtraction?
7. How do you distinguish errors in wrapper code from errors in the user's snippet?
8. Should a diagnostic span crossing a generated-only region become one continuous highlight in the original document?
9. Where do UTF-16 code units differ from Unicode code points?
10. Why is a compiler API record with source/position more reliable than self-parsed stderr messages?
11. Why is document revision needed when compiling asynchronously?
12. Why do errors in annotation-processor-generated source not automatically map accurately back to the original annotation?

## 15. Official documentation

- **Java SE 21 — javax.tools.Diagnostic API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/Diagnostic.html
- **Java SE 21 — javax.tools.DiagnosticCollector:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html
- **Java SE 21 — javax.tools.JavaCompiler:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html
- **Java SE 21 — javax.tools.JavaFileObject:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileObject.html
- **Java SE 21 — javax.tools.SimpleJavaFileObject:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html
- **Java SE 21 — javax.tools.StandardJavaFileManager:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html
- **Oracle JDK 21 — javac command reference:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html

**Key takeaway:** When compiling Java in memory, **diagnostics must be interpreted relative to the exact `JavaFileObject` seen by the compiler**. If it is a verbatim copy of the original document, identity mapping usually suffices. If the source was generated/wrapped/normalized, you need a **source map recorded at transformation time**, tied to document ID and revision, handling `null/NOPOS`, and only then converting to editor line/column coordinates. **An error that cannot be mapped reliably must be marked unmapped rather than fabricating a fake position.**