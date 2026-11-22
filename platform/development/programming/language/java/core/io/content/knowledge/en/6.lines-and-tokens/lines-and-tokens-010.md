# StreamTokenizer and Choosing the Right Parsing Tool in Java I/O

## 1. Goal and Role of `StreamTokenizer`

When reading text, a program often needs to go beyond reading character by character or line by line: it must recognize **words**, **numbers**, **punctuation/separators**, and sometimes **quoted strings**. Splitting text into meaningful elements like this is called *tokenization*. Java provides the long-standing `java.io.StreamTokenizer` class to read tokens one at a time from a character stream and customize certain recognition rules.

This lesson belongs to the **Lines and Tokens** topic of Java Core I/O. After completing it, you should be able to:

- Know when to use `StreamTokenizer`, understand the `nextToken()` loop, constants `TT_WORD`, `TT_NUMBER`, `TT_EOL`, `TT_EOF`, and fields `ttype`, `sval`, `nval`.
- Understand how to define word characters, whitespace, quotes, comments, numbers, ordinary characters, and line endings.
- Write Java 17+ programs that process tokens, distinguish EOF and EOL, retrieve line numbers, manage `Reader` lifecycles, and handle errors.
- Recognize the limits of a tokenizer: **tokenizing is not parsing**, it does not understand CSV/JSON out of the box, and it does not enforce semantic rules automatically.
- Choose the right tool among `StreamTokenizer`, `Scanner`, `BufferedReader` + string/regex processing, CSV/JSON parsers, and dedicated lexers/parsers.

**Main takeaway:** `StreamTokenizer` fits when input is a **simple text language with clear token rules that should be read sequentially from a `Reader`**. For standard formats or complex grammars, choose a parser dedicated to that format.

## 2. Distinguishing Characters, Lines, Tokens, and Structure

Suppose the input is:

```text
total = 12.5
name = "Ada Lovelace"
```

There are multiple processing levels:

1. **Character reading:** `Reader.read()` yields `char` units and signals EOF with `-1`.
2. **Line reading:** `BufferedReader.readLine()` returns one line string without line-termination characters; returns `null` when lines are exhausted.
3. **Tokenization:** a tokenizer identifies `total` as a word, `=` as a standalone punctuation mark, `12.5` as a number; on the next line, `"Ada Lovelace"` is recognized as a quoted token per configured syntax.
4. **Parsing:** the parser understands that the structure must be `name = value`, checking valid key names, properly typed values, ordering, and required punctuation.
5. **Validation/semantics:** the application checks that `total` is non-negative, `name` is non-empty, or values lie within allowed ranges.

Tokenization **does not automatically perform** steps 4 and 5. A lexically valid sequence of tokens can still represent an invalid configuration or expression.

| Goal | Operation / Tool |
| --- | --- |
| Simply preserve text line by line | `BufferedReader.readLine()` |
| Read strings/words/numbers from simple input | `Scanner` or `StreamTokenizer` |
| Control character classification and individual symbol tokens | `StreamTokenizer` |
| Split logs with clear, low-complexity rules | Read line by line + String methods / `Pattern` |
| Read RFC-compliant CSV or handle quotes, embedded commas, multiline fields | Dedicated CSV library |
| Read JSON with nested objects/arrays, escapes, Unicode | Standard JSON parser library |
| Custom language with grammar, precedence, token positions, detailed errors | Dedicated lexer/parser or generator such as ANTLR |

## 3. Mechanics of `java.io.StreamTokenizer`

Create a tokenizer from a `Reader`:

```java
java.io.StreamTokenizer tokenizer =
        new java.io.StreamTokenizer(reader);
```

`reader` is an already open `Reader`. `nextToken()` reads the next token, returns its token type code (`int`), and updates the tokenizer's state:

| Member | Meaning | How to Access |
| --- | --- | --- |
| `StreamTokenizer.TT_WORD` | Token classified as a word | When returned, read text from `tokenizer.sval` |
| `StreamTokenizer.TT_NUMBER` | Token classified as a number | When returned, read `double` value from `tokenizer.nval` |
| `StreamTokenizer.TT_EOL` | End-of-line marker (when `eolIsSignificant(true)` is enabled) | Not treated as string content |
| `StreamTokenizer.TT_EOF` | End of input stream | Exit the loop; stop reading |
| Code of an ordinary character or quote character | For example `'='`, `'+'`, `'"'` | For ordinary punctuation: handle the character; for quoted tokens: `sval` holds the inner content |
| `tokenizer.ttype` | Type of the most recent token | Can be checked instead of the `int` returned by `nextToken()` |
| `tokenizer.sval` | Text of a word or quoted string token | Interpret only when the token type matches |
| `tokenizer.nval` | Numeric value as a `double` | Interpret only when type is `TT_NUMBER` |
| `tokenizer.lineno()` | Current line number per tokenizer's counter | Useful for error context; not column or character offset |

Tokens can be processed with a loop:

```java
int type;
while ((type = tokenizer.nextToken()) != StreamTokenizer.TT_EOF) {
    if (type == StreamTokenizer.TT_WORD) {
        // Use tokenizer.sval
    } else if (type == StreamTokenizer.TT_NUMBER) {
        // Use tokenizer.nval
    } else {
        // Handle punctuation, quoted strings, or EOL depending on configuration
    }
}
```

The snippet above **illustrates structure only**, not a standalone program: `tokenizer` must be created from a `Reader` with proper source lifecycle management.

### 3.1. EOF Differs from EOL

- **EOF** (`TT_EOF`): the source has no more tokens; the token-reading loop must terminate.
- **EOL** (`TT_EOL`): a line boundary *when enabled*; the caller continues reading tokens on the next line.
- By default, line endings are skipped like whitespace. Call `eolIsSignificant(true)` if the grammar treats lines as record boundaries.
- `lineno()` is helpful for including line numbers in error messages, though the tokenizer does not track column numbers or byte offsets for each token.

If the application needs to distinguish **blank lines**, **end of record**, or per-line fields, EOL matters. If the grammar allows records to span multiple lines, stopping on EOL can break parsing.

### 3.2. Numbers Are Stored as `double`

When `TT_NUMBER` appears, `nval` is a `double`. For integers larger than binary floating-point exact precision, decimals requiring financial precision, or numbers with special formatting, do not treat this as a "lossless" number parser.

For example, large 64-bit integers lose precision when passed through `double`; monetary values like `0.1` have no exact finite binary representation. If data must preserve exact digits, read tokens **as strings** under an appropriate grammar and parse with `Long.parseLong`, `BigInteger`, or `BigDecimal` plus validation; do not route through `nval` first.

## 4. Java 17+: Complete Example Recognizing Words, Numbers, Symbols, Quoted Strings, and EOL

The example fixes input inside a `StringReader` for deterministic test output. In real applications, you can use `Files.newBufferedReader(path, StandardCharsets.UTF_8)` instead of `StringReader`. `StringReader` is an in-memory source well suited to short sample data.

Save the code to **`StreamTokenizerDemo.java`**:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StreamTokenizer;
import java.io.StringReader;

public class StreamTokenizerDemo {
    public static void main(String[] args) throws IOException {
        String input = "total = 12.5\nname = \"Ada Lovelace\"\n";

        try (Reader reader = new StringReader(input)) {
            StreamTokenizer tokenizer = new StreamTokenizer(reader);
            tokenizer.eolIsSignificant(true);

            while (true) {
                int type = tokenizer.nextToken();

                if (type == StreamTokenizer.TT_EOF) {
                    System.out.println("EOF");
                    break;
                }
                if (type == StreamTokenizer.TT_EOL) {
                    System.out.println("EOL");
                } else if (type == StreamTokenizer.TT_WORD) {
                    System.out.println("WORD " + tokenizer.sval);
                } else if (type == StreamTokenizer.TT_NUMBER) {
                    System.out.println("NUMBER " + tokenizer.nval);
                } else if (type == '"') {
                    System.out.println("QUOTED " + tokenizer.sval);
                } else {
                    System.out.println("CHAR " + (char) type);
                }
            }
        }
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 StreamTokenizerDemo.java
java StreamTokenizerDemo
```

**Example stdout:**

```text
WORD total
CHAR =
NUMBER 12.5
EOL
WORD name
CHAR =
QUOTED Ada Lovelace
EOL
EOF
```

**Explanation:**

- `total` and `name` are `TT_WORD`; their text lives in `sval`.
- `12.5` is `TT_NUMBER`; `nval` displays `12.5`.
- `=` is an ordinary character, so the final branch prints `CHAR =`.
- `"` indicates a quoted token; `sval` holds `Ada Lovelace`, including the internal space but excluding the surrounding quotes.
- Because `eolIsSignificant(true)` was called and the input has `\n` at the end of **both lines**, we receive two `EOL` tokens before `EOF`.
- `try-with-resources` closes the `Reader`. `StreamTokenizer` itself is not a separately closeable resource, yet the underlying reader generally must be closed, especially when opening files/sockets.

This example demonstrates **token classification** without verifying that `=` sits between key and value. To enforce a grammar, add steps like "expect key name → require equals sign → require value" and report an error on unexpected token types.

## 5. Customizing Syntax: Using Configuration Methods Properly

A primary strength of `StreamTokenizer` is defining which characters count as word, whitespace, comment, quote, and ordinary single-character tokens.

| Method | Effect | Things to Watch Out For |
| --- | --- | --- |
| `wordChars(low, high)` | Marks character range as word constituents | Configured ranges are only part of a grammar; does not automatically know full Java identifiers |
| `whitespaceChars(low, high)` | Marks character range as whitespace | Easy to accidentally drop delimiters if set too broadly |
| `ordinaryChar(ch)` / `ordinaryChars(low, high)` | Classifies characters as standalone single-char tokens | Overrides prior word/whitespace/comment/quote roles |
| `quoteChar(ch)` | Sets quote open/close character for quoted strings | Not equivalent to a standard JSON or CSV string parser |
| `commentChar(ch)` | Sets single-line comment starter until end of line | Meaningful only if the grammar defines comments that way |
| `slashSlashComments(true)` | Recognizes `//` style comments | Consider carefully if text contains URLs/paths with `//` |
| `slashStarComments(true)` | Recognizes `/* ... */` style comments | Does not automatically handle nested comment grammars |
| `parseNumbers()` | Enables tokenizer's number recognition | Numbers return as `double`; does not replace exact number parsers |
| `eolIsSignificant(true)` | Emits EOL tokens in the stream | Not equivalent to reading complete lines |
| `lowerCaseMode(true)` | Converts word tokens to lowercase | Can lose significant case distinctions |
| `resetSyntax()` | Resets all character syntax tables | Must reconfigure word/whitespace/quote/number/comment as needed |
| `pushBack()` | Pushes back the last read token so `nextToken()` returns it once more | Supports only single-token lookahead, not an arbitrary token buffer |

### 5.1. Supporting Underscore Identifiers and `#` Comments

By default, do not assume identifiers like `user_name` will be tokenized as desired by your grammar. For simple config files, you can add `_` to word characters and treat `#` as a comment.

Save as **`ConfiguredTokenizerDemo.java`**:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StreamTokenizer;
import java.io.StringReader;

public class ConfiguredTokenizerDemo {
    public static void main(String[] args) throws IOException {
        String source =
                "user_name = \"Ada Lovelace\" # annotation\n"
                + "attempts = 3";

        try (Reader reader = new StringReader(source)) {
            StreamTokenizer tokenizer = new StreamTokenizer(reader);
            tokenizer.wordChars('_', '_');
            tokenizer.commentChar('#');

            int type;
            while ((type = tokenizer.nextToken())
                    != StreamTokenizer.TT_EOF) {
                if (type == StreamTokenizer.TT_WORD) {
                    System.out.println("WORD " + tokenizer.sval);
                } else if (type == StreamTokenizer.TT_NUMBER) {
                    System.out.println("NUMBER " + tokenizer.nval);
                } else if (type == '"') {
                    System.out.println("QUOTED " + tokenizer.sval);
                } else {
                    System.out.println("CHAR " + (char) type);
                }
            }
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ConfiguredTokenizerDemo.java
java ConfiguredTokenizerDemo
```

**stdout:**

```text
WORD user_name
CHAR =
QUOTED Ada Lovelace
WORD attempts
CHAR =
NUMBER 3.0
```

**Explanation:** `wordChars('_', '_')` makes `user_name` a single word token. `commentChar('#')` skips from `#` to end of line. Because EOL was not enabled as in the prior example, the program prints no `EOL`. `attempts = 3` still classifies into word, symbol, and number. The value `3` prints as `3.0` because `nval` is a `double`.

The two programs above show that `StreamTokenizer`'s configuration is convenient for a small token set. However, the code **only prints tokens**; a real parser must still catch missing fields, duplicate keys, mistyped values, disallowed comments, and invalid ordering.

### 5.2. Be Careful with `resetSyntax()` and Precedence Changes

Calling `resetSyntax()` wipes out default rules; if you then call only `wordChars('a', 'z')` while forgetting whitespace, numbers, and quotes, the tokenizer will no longer behave like default. Draft a table of your desired grammar before writing configuration calls and write tests for:

- Leading/trailing word characters.
- Negative signs, decimal points in numbers, and precision.
- Equals signs, commas, semicolons, or brackets.
- Single and double quotes; unclosed strings; escape characters.
- Whitespace, CRLF, and LF.
- Comments inside and outside quoted text.
- Non-ASCII Unicode characters.

Never call one method and assume the tokenizer becomes a full Java, CSV, or JSON lexer. In particular, recognizing punctuation in standard formats often involves escaping and state tracking that simple per-character tables cannot express.

## 6. When Is `StreamTokenizer` Appropriate?

Use `StreamTokenizer` when:

1. Input is a character stream that can be read sequentially with a small lexical grammar, such as internal `name = value` directives, lists of names and numbers, or educational command sets.
2. You want character-level customization of words/numbers/quotes/comments/EOL without writing a scanner from scratch.
3. Sequential tokens suffice and the downstream grammar is very simple; you can write a small state machine to validate token ordering.
4. You accept `double` limitations for numbers or have a separate strategy for parsing numbers needing exact precision.
5. You do not need exact column positions, byte offsets, complex syntax trees, or sophisticated error recovery.

Example of a good fit: a mini language used to practice distinguishing `name`, `=`, `number`, and `;` tokens with well-defined keywords and syntax. That is very different from taking arbitrary SQL, JSON, or Java source files and expecting `StreamTokenizer` to handle the full grammar.

## 7. Comparison with Other Parsing Tools

### 7.1. `Scanner`: Reading Data by Delimiter and Pattern

`java.util.Scanner` is typically convenient for whitespace-delimited token input, locale-aware number parsing, and regex delimiters:

```java
// Illustrative: scanner only processes the example string, not a CSV parser.
try (java.util.Scanner scanner =
        new java.util.Scanner("red blue 42")) {
    while (scanner.hasNext()) {
        System.out.println(scanner.next());
    }
}
```

With the snippet above, stdout is three lines `red`, `blue`, and `42`. `Scanner` provides `hasNextInt()`, `nextInt()`, `useDelimiter(...)`, and locale support; when parsing numbers, watch formatting and `InputMismatchException`. When reading from files, close the scanner (because it manages its wrapped source).

**Pros:** readable API for small inputs or whitespace/regex-delimited formats. **Cons:** regex/locale/per-call overhead can be significant compared to simple chunk processing; `Scanner` does not magically become a CSV/JSON parser or full language lexer either.

Choose `StreamTokenizer` if character classification and basic quote/comment rules fit its design; choose `Scanner` if input consists mainly of delimiter/pattern-separated fields and you want convenient type conversion methods.

### 7.2. `BufferedReader` + `String` / `Pattern`: Line-by-Line Control

For logs structured as "one record per line", it is often easiest to read via `readLine()` and then apply `indexOf`, `split`, or `Pattern` per your specific grammar:

```java
// Illustrative single simple line, not a CSV parser.
String record = "ERROR|42|disk full";
String[] fields = record.split("\\|", -1);
System.out.println(fields[0]); // ERROR
System.out.println(fields[1]); // 42
```

Note that `String.split` takes a **regular expression**, so `|` must be escaped as `"\\|"` in Java. The `-1` limit retains trailing empty fields; without it, trailing empty fields may be dropped.

**Pros:** convenient when the business unit is one line and error reports need line numbers. **Cons:** error-prone with quotes/escapes, multiline records, or abnormally long lines; `readLine()` reads an entire line into a `String` without bounding line length. For untrusted logs, enforce line quotas and input checks.

### 7.3. `StringTokenizer`: Legacy Class for Simple String Splitting

`java.util.StringTokenizer` splits **an already-loaded `String`**, mainly by delimiter characters. It does not read tokens directly from a `Reader` and does not properly understand quoted fields or structured formats. For new code, `String.split`/`Pattern` or a proper format parser is usually easier to reason about; do not use `StringTokenizer` as a general-purpose parser.

### 7.4. CSV, JSON, and Standard Formats: Dedicated Parsers

CSV example:

```text
id,name,description
1,"Ada, A.","first, second"
```

If you split solely on commas, `"Ada, A."` gets split incorrectly. CSV also involves escaped double quotes, embedded newlines inside fields, headers, encoding, and dialect variations. Use a CSV library supporting the required standard/dialect (such as Apache Commons CSV or OpenCSV, depending on project dependencies). When parsing critical data, specify the dialect and error-reporting policy clearly.

JSON example:

```json
{"user":{"name":"Ada","roles":["reader","writer"]},"active":true}
```

JSON requires a parser that understands objects, arrays, escapes, numbers, booleans, null, and nested structures. `StreamTokenizer` does not build JSON trees or validate JSON grammar. Use an appropriate JSON parser library such as Jackson or Gson if available in your project; enforce size and nesting-depth limits on untrusted input.

### 7.5. Dedicated Lexer/Parser

When parsing expressions with operators, precedence, nested parentheses, variables, keywords, complex string literals, or custom multi-rule languages, clearly separate:

- **Lexer:** turns characters into tokens carrying type, text, and position.
- **Parser:** checks grammar and builds syntax structures such as an AST.
- **Semantic validation:** checks types, variable names, operations, and value bounds.

`StreamTokenizer` assists only with part of lexing. For stronger needs, consider a clean custom lexer, well-bounded `Pattern` rules, or a parser generator like ANTLR, depending on grammar scale and maintenance requirements.

## 8. Quick Decision Matrix

| Actual Input | Starting Choice | Why |
| --- | --- | --- |
| Simple whitespace-separated list of words/numbers | `Scanner` | Readable, provides `nextInt`/`nextDouble` |
| Mini language with basic words, numbers, punctuation, quotes/comments | `StreamTokenizer` | Configurable character classes, returns tokens sequentially from `Reader` |
| "One record per line" logs with clear delimiters and few fields | `BufferedReader` + line logic / `Pattern` | Easy record control and error reporting |
| CSV files with quotes, embedded delimiters, or multiline cells | Dedicated CSV parser | Correctly handles CSV structure and escaping |
| Nested JSON | Dedicated JSON parser | Handles grammar, escapes, and data types |
| Fixed byte layout, binary protocols | `InputStream`/`DataInputStream`/`ByteBuffer` | Data is binary, not text to tokenize |
| Language with expression grammar, source positions, error recovery | Dedicated lexer/parser | `StreamTokenizer` is insufficient for full grammars |
| Huge files needing only token counting/filtering | Streaming reader with resource bounds | Avoids loading full document; enforces token/line quotas |

**There is no "best" tool independent of requirements.** Choose based on actual format, required correctness, input size, error reporting, performance, maintainability, and available libraries.

## 9. Structuring a Small Token-Based Parser

Suppose a command grammar is:

```text
assignment := identifier "=" value
identifier := a valid word
value      := quoted-string | number | word
```

A proper parser must sequentially:

1. Call `nextToken()` and require `TT_WORD` for the key name; otherwise report an error with `lineno()`.
2. Call `nextToken()` and require `'='`. If missing, do not silently accept the next token as the value.
3. Call `nextToken()` and accept only valid token types for value.
4. Verify the record ended: EOL, `;`, or EOF, strictly per your chosen grammar.
5. Validate key names, values, large numbers/precision, and duplicate fields; return contextual errors.
6. If single-token lookahead is needed, `pushBack()` can put back the token just read for the next read; do not treat it as an arbitrary-length buffer.

If the grammar assigns meaning to line boundaries, enable `eolIsSignificant(true)`, yet carefully test end-of-source right after the last token without a trailing newline. If the grammar requires `;`, configure and verify that token explicitly.

### 9.1. Why Not Just Concatenate Token Strings?

For input `x == 4`, a tokenizer may return `x`, `=`, `=`, `4` in sequence. If the application only collects words/numbers and ignores punctuation, it may accidentally accept the invalid expression as "x = 4". The parser is responsible for checking exact token order and count.

For input `total = 99999999999999999999`, reading `nval` as `double` and casting to `long` loses data or alters the value. Keep lexing and parsing cleanly separated: numbers needing exact precision should be parsed from original digit strings by an appropriate numeric parser.

## 10. Source Management, Unicode, Security, and Resources

### 10.1. Charset and File Sources

For text files, open with an explicit charset:

```java
// API illustration: path is an existing Path.
try (java.io.Reader reader = java.nio.file.Files.newBufferedReader(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    java.io.StreamTokenizer tokenizer =
            new java.io.StreamTokenizer(reader);
    // Read and process tokens according to the application's grammar.
}
```

This is an **illustrative snippet**, not a standalone program because `path` is not declared. `try-with-resources` closes the reader even if `nextToken()` throws `IOException`.

`StreamTokenizer` operates at Java's `char` layer, not the byte layer. If data is decoded with the wrong charset, tokens can be corrupted from the start. For Unicode, do not automatically assume character-range settings match a grammar accepting every valid Unicode identifier; if specific Unicode code point/normalization rules apply, define and test that grammar explicitly.

### 10.2. Bounding Untrusted Input

Streaming reads do not imply unconditional safety. An extremely long quoted token, an infinite line, endless tokens, or a blocking source can exhaust memory, CPU, time, or connections.

When parsing network/user input, enforce policies:

- Limit **total bytes** read (at the byte layer) and/or character counts if business rules require.
- Limit **token count, token size, line count, and nesting depth** if the grammar has nested constructs.
- Set **timeouts/cancellation** at the source layer for potentially blocking sockets/pipes.
- Handle malformed syntax cleanly: unclosed quotes, missing fields, out-of-range numbers, out-of-grammar characters.
- Never evaluate strings derived from tokens as code or queries without context-appropriate validation and escaping/parameterization.
- For standards with dedicated parsers, prefer library-supported resource limits instead of assuming a tokenizer is safe by default.

`StreamTokenizer` does not enforce built-in token or character quotas for every scenario. When strict bounds are required, place a measuring/limiting wrapper on the input or use a parser with verified limit support.

### 10.3. Exceptions and Error Handling

`nextToken()` can throw `IOException` when the reader hits an I/O problem. That differs from grammar errors: for example, an unexpected token is a **syntax/parsing** error that application code must report. Distinguish three categories:

- **I/O:** unreadable file, network failure, lost permissions.
- **Lexical/syntax:** invalid character, malformed quote/grammar, missing delimiter.
- **Semantic:** disallowed key, out-of-bounds value, duplicate field.

Do not skip unexpected tokens just to "keep reading"; doing so corrupts data and hides input errors.

## 11. Common Mistakes

- Mistaking `StreamTokenizer` for a JSON/CSV parser or a complete programming language parser.
- Confusing `StreamTokenizer.TT_EOF` with `TT_EOL`; forgetting to enable EOL when the grammar distinguishes lines.
- Reading `sval` when the token is not a word/quoted string or reading `nval` when the token is not a number.
- Trusting `nval` to represent exact integers or exact decimals for all values.
- Failing to check `=`, brackets, or token ordering; collecting only words/numbers while ignoring punctuation.
- Forgetting to manage `Reader` lifecycle; the tokenizer does not close its source automatically.
- Calling `resetSyntax()` and forgetting to re-declare whitespace/quotes/numbers.
- Enabling comment syntax without considering strings containing comment-like characters.
- Using `String.split(",")` to parse CSV containing quoted commas.
- Using a simple regex to parse nested JSON.
- Treating a streaming API as safe for unbounded input: huge tokens or slow reads still require limits.
- Omitting charset when reading files and failing to test Unicode/CRLF/LF.

## 12. Exercises and Self-Assessment Criteria

1. **Token classification:** predict the stdout of `StreamTokenizerDemo` if `eolIsSignificant(true)` is removed. Does the `EOF` token disappear? (No.)
2. **Punctuation rules:** add `;` to the input, modify the parser to require strictly one `=` and optional trailing `;`. Verify `x == 4` is rejected.
3. **Word customization:** add identifier `first_name` to `ConfiguredTokenizerDemo`. Explain why `wordChars('_', '_')` is needed.
4. **Exact numbers:** test a 20-digit identifier. Why should you not store it in `nval` and cast to `long`? Design an approach handling the raw token as a string.
5. **Tool comparison:** given `a,b,"c,d"`, explain why `split(",")` fails and choose a CSV parser.
6. **Multiline data:** create input with two commands, an empty line, CRLF line endings, and EOF without a trailing newline. Define how the parser detects record boundaries.
7. **Source failure:** simulate an `IOException` from the reader and distinguish the I/O error message from a "missing `=`" error.
8. **Unicode:** test names and values with Vietnamese diacritics and emoji; define the desired identifier grammar and file-reading charset.
9. **Resources:** identify where `Reader` is closed, where quotas/timeouts belong, and why `StreamTokenizer` does not handle those automatically.

**Final check:** you should be able to distinguish **tokenization, parsing, and validation**, write a `nextToken()` loop that terminates cleanly on EOF, know how to read `sval`/`nval` for the matching token types, and choose a dedicated parser whenever format rules exceed a simple lexer.
