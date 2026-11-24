# Reading ScriptException with File Name, Line, and Column When Provided by the Engine

## 1. Role of ScriptException in Embedded Scripting

The Java Scripting API (JSR 223, package `javax.script`) lets a host application invoke a script engine via `ScriptEngine.eval(...)`. When the parser or script evaluation reports an error through the engine's mechanism, Java can receive `javax.script.ScriptException`. Beyond the error message, the exception object carries location metadata **if the engine supplies it**:

- `getFileName()`: name of the source/script attached to the error by the engine; may be `null`.
- `getLineNumber()`: error line number; `-1` indicates unknown location.
- `getColumnNumber()`: error column number; `-1` indicates unknown location.
- `getMessage()`: error description; may already include filename, line, and column depending on the constructor/engine.
- `getCause()`: root cause if the exception was constructed with a cause or attached by the engine.

Not every engine accurately populates all three location fields. Never assume `getLineNumber()` or `getColumnNumber()` is always positive, that an engine always counts columns by Unicode characters like your editor, or that `getFileName()` always equals a real path on disk.

## 2. Distinguishing Three Types of Information

| Component | Meaning | Note |
| --- | --- | --- |
| File name / source | Script identifier used by the engine when reporting errors | May be a logical name like `rules/discount.js`, not necessarily a physical path |
| Line | Position in source according to the engine | `-1` means unknown; concatenated/preprocessed sources can shift line numbers |
| Column | Position within the line according to the engine | `-1` means unknown; column unit, starting index, and counting rules depend on the engine |
| Error message | Description of syntax/runtime failure | Does not fully replace structured metadata |
| Cause / stack trace | Deeper underlying reason | May be absent; do not lose stack traces when wrapping |

In many engines, locations are reported as 1-based line/column numbers, yet the `ScriptException` API **does not guarantee every engine aligns locations with how your editor displays them**. When building an IDE or rule system with line highlighting, test against the specific engine—especially for sources containing multi-byte characters, tabs, CRLF, or Unicode supplementary characters.

## 3. Safely Extracting and Displaying Metadata

Minimal Java 17+ example requiring no installed engine: constructing a `ScriptException` and displaying its fields:

```java
import javax.script.ScriptException;

public class ScriptErrorReport {
    static String location(ScriptException ex) {
        String source = ex.getFileName();
        if (source == null || source.isBlank()) source = "<unknown source>";
        String line = ex.getLineNumber() >= 0
                ? Integer.toString(ex.getLineNumber()) : "?";
        String column = ex.getColumnNumber() >= 0
                ? Integer.toString(ex.getColumnNumber()) : "?";
        return source + ":" + line + ":" + column;
    }

    public static void main(String[] args) {
        ScriptException ex =
                new ScriptException("Unexpected token", "rules/example.dsl", 7, 12);
        System.out.println(location(ex));
        System.out.println("Message: " + ex.getMessage());

        ScriptException unknown = new ScriptException("Evaluation failed");
        System.out.println(location(unknown));
    }
}
```

Run:

```bash
javac --release 17 ScriptErrorReport.java
java ScriptErrorReport
```

Output:

```text
rules/example.dsl:7:12
Message: Unexpected token in rules/example.dsl at line number 7 at column number 12
<unknown source>:?:?
```

`ScriptException(String message, String fileName, int line, int column)` can append location info to `getMessage()`; therefore, if you concatenate `location + message` when logging, the source name, line, and column may be duplicated. Define a consistent log format: separate structured metadata for machines and readable messages for humans.

## 4. Catching Exceptions from a Real Script Engine

Typical API usage:

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("engine-name");
if (engine == null) {
    throw new IllegalStateException("Required script engine not installed");
}
try {
    engine.eval(scriptText);
} catch (ScriptException ex) {
    System.err.println("Script: " + ex.getFileName());
    System.err.println("Line: " + ex.getLineNumber());
    System.err.println("Column: " + ex.getColumnNumber());
    throw ex;
}
```

This is an illustrative snippet inside a method with `scriptText` and `import javax.script.*`. JDK 17 **does not bundle Nashorn by default**; `ScriptEngineManager` may discover no engines if you do not install a provider via dependencies/module path. Do not write default examples calling `getEngineByName("JavaScript")` and claiming they always run out of the box.

### Attaching a Source Identifier via ScriptEngine.FILENAME

JSR 223 defines the key `ScriptEngine.FILENAME` (whose full name is typically `javax.script.filename`). Some engines use this attribute as the script name in diagnostics:

```java
ScriptContext context = engine.getContext();
Object old = context.getAttribute(ScriptEngine.FILENAME,
        ScriptContext.ENGINE_SCOPE);
try {
    context.setAttribute(ScriptEngine.FILENAME,
            "rules/tax-policy.dsl", ScriptContext.ENGINE_SCOPE);
    engine.eval(scriptText, context);
} catch (ScriptException ex) {
    logScriptError(ex);
} finally {
    if (old == null) {
        context.removeAttribute(ScriptEngine.FILENAME,
                ScriptContext.ENGINE_SCOPE);
    } else {
        context.setAttribute(ScriptEngine.FILENAME, old,
                ScriptContext.ENGINE_SCOPE);
    }
}
```

This is an illustrative snippet assuming `engine`, `scriptText`, and `logScriptError` are declared. **No engine is forced to populate FILENAME in every ScriptException**; if the engine does not support it, `getFileName()` may still be `null`. Additionally, `getContext()` may be shared across multiple evaluations: context updates should be synchronized, or create a separate `SimpleScriptContext` per request to avoid leaking script names across runs.

Context-isolation approach per evaluation:

```java
ScriptContext context = new SimpleScriptContext();
context.setAttribute(ScriptEngine.FILENAME, "rules/tax-policy.dsl",
        ScriptContext.ENGINE_SCOPE);
engine.eval(scriptText, context);
```

This snippet belongs inside a method with appropriate imports. If the script needs bindings, readers/writers, or global scope, configure that context accordingly; a fresh `SimpleScriptContext` does not automatically copy all settings from the engine's default context.

## 5. Mock Engine Example to Verify Error-Handling Paths

When unit-testing error-reporting logic, you can construct `ScriptException` based on test inputs without depending on an external engine. Below is a standalone Java 17+ program using a mock `evaluate` function to represent two cases: a parser providing location and a runtime not providing location.

```java
import javax.script.ScriptException;

public class ScriptExceptionCases {
    static void evaluate(String sourceName, boolean hasLocation)
            throws ScriptException {
        if (hasLocation) {
            throw new ScriptException("Invalid assignment", sourceName, 3, 8);
        }
        throw new ScriptException("Execution failed");
    }

    static void print(ScriptException ex, String fallbackSource) {
        String name = ex.getFileName() == null
                ? fallbackSource : ex.getFileName();
        String line = ex.getLineNumber() < 0
                ? "unknown" : Integer.toString(ex.getLineNumber());
        String column = ex.getColumnNumber() < 0
                ? "unknown" : Integer.toString(ex.getColumnNumber());
        System.out.println("source=" + name +
                ", line=" + line + ", column=" + column);
    }

    public static void main(String[] args) {
        for (boolean loc : new boolean[] {true, false}) {
            try {
                evaluate("workflow.dsl", loc);
            } catch (ScriptException ex) {
                print(ex, "workflow.dsl");
            }
        }
    }
}
```

Run:

```bash
javac --release 17 ScriptExceptionCases.java
java ScriptExceptionCases
```

Output:

```text
source=workflow.dsl, line=3, column=8
source=workflow.dsl, line=unknown, column=unknown
```

This example demonstrates **handling** metadata and fallbacks; it does not claim to include a JavaScript engine or real parser. In a real application, replace `evaluate` with the target engine; unit tests for error formatters still run deterministically without environmental dependencies.

## 6. How Can Source Locations Shift?

Script engines report locations based on **the source they see**, not necessarily the text the user opened in an editor. The following transformations easily cause offsets to drift:

- Prepending header/helper code before eval: an error on line 20 of the combined string may correspond to line 17 of the original file.
- Concatenating multiple script files into one string: `getFileName()` may point to the combined file, and line numbers will not map directly to the original source.
- Preprocessors/macros: one token in the original source can expand into multiple tokens in the evaluated string.
- CRLF vs. LF: an engine may count lines/columns differently from display tools if source is normalized.
- Tabs and Unicode: the engine's column unit does not necessarily equal the visual column width in an editor.

To render accurate underlines, maintain a **source map** or offset-mapping table from the evaluated string back to the original source. Without a mapping, report locations against the text the engine actually received and clarify that it is a generated source location. Never blindly add or subtract line numbers when the pipeline performs multi-step transformations.

## 7. Propagating Errors Across Architectural Layers

A script-running system typically has layers: API → script runner → JSR 223 engine. If the runner catches `ScriptException` and throws `new RuntimeException(ex.getMessage())`, all file/line/column metadata and the cause are lost. There are two safe options:

1. Preserve `ScriptException` and let the calling layer handle it.
2. Wrap the error in a domain exception that retains the cause and explicit metadata (source name, line, column) so the API/UI can display it.

Illustrative snippet inside a method:

```java
try {
    return engine.eval(script, context);
} catch (ScriptException ex) {
    throw new ScriptRunFailure(
            sourceId, ex.getLineNumber(), ex.getColumnNumber(), ex);
}
```

`ScriptRunFailure` here is a **custom-defined** domain exception class, not a built-in Java API. Never swallow `getCause()` or keep only the message string when diagnostics are needed.

### Safe Logging

For user-supplied scripts, avoid logging the entire raw source or secrets inside bindings; log the normalized source ID, error type, line/column if known, request correlation ID, and stack trace at the permitted level. If `getFileName()` is an external path, avoid returning full filesystem paths in API responses. The UI should escape error messages before rendering so script messages cannot inject unsafe content into HTML or logs.

## 8. Common Issues and Fixes

| Scenario | Cause | Resolution |
| --- | --- | --- |
| File name is `null` | Engine lacks info or ignores `FILENAME` | Fall back to the application's source ID |
| Line/column is `-1` | Engine did not report location | Display `unknown`; do not coerce to 0 |
| Column mismatches editor | Tabs, Unicode, newlines, or engine rules | Check units/indexing; use a source map if transformed |
| `getMessage()` repeats file/line | `ScriptException` constructor embedded metadata in message | Format logs to avoid duplication |
| `getEngineByName(...)` returns `null` | Engine provider not installed | Install proper dependency; inspect classpath/module path |
| Errors show wrong file under concurrency | Shared mutable `ScriptContext` | Create separate contexts or synchronize |
| Wrapping exception loses line/column | Kept only the message string | Preserve `ScriptException` or metadata + cause |
| Script source modified before eval | Locations reflect generated text | Maintain a source map; document the mapping |
| Runtime error lacks location | Engine does not supply runtime locations | Surface limitation clearly; use stack trace/cause if available |

## 9. Practical Checklist

- [ ] Verify `ScriptEngine` exists before calling eval.
- [ ] Attach a valid source identifier via `ScriptEngine.FILENAME` if supported by the engine.
- [ ] Read `getFileName()`, `getLineNumber()`, and `getColumnNumber()` instead of parsing the message string.
- [ ] Treat `null`/`-1` as unknown location.
- [ ] Preserve cause and stack trace when propagating exceptions across layers.
- [ ] Test syntax errors, runtime errors, and engines that omit location metadata.
- [ ] If preprocessing/concatenating files, maintain an offset/line source map.
- [ ] Do not assume JDK 17 includes Nashorn/a JavaScript engine.
- [ ] Do not expose host paths or secret sources in user-facing diagnostics.
- [ ] Ensure error formatters run reliably even when no engine is installed.

**Conclusion:** `ScriptException` offers a structured API for reading source name, line, and column, yet **how complete that metadata is depends on the script engine**. Always read and check the getters directly, apply sensible fallbacks, preserve the cause, and display locations only when reliable. This keeps error reporting in embedded scripting systems clear without fragile message-string parsing.
