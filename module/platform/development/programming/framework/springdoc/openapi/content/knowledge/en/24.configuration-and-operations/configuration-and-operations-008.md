# Rules for Escaping, Line Breaks, and Keeping Markdown Content Readable

Springdoc extracts metadata from annotations, models, and configuration to generate OpenAPI JSON/YAML. Description fields such as **@Operation.description**, **@Parameter.description**, **@Schema.description**, or **@ApiResponse.description** can contain Markdown so Swagger UI renders documentation more legibly.

When writing such content, distinguish the processing layers: Java string literals, YAML scalars, JSON strings, and Markdown syntax. Each layer has its own escaping and line-break rules. Mixing one layer's syntax into another can leave literal backslashes visible, lose line breaks, break JSON, or cause Swagger UI to render formatting incorrectly.

## 1. Four Syntax Layers to Distinguish

A description may pass through several stages before a user sees it:

~~~text
Java annotation / YAML source
          |
          v
String in the application
          |
          v
OpenAPI model
          |
          v
Serialized JSON or YAML
          |
          v
Swagger UI parses Markdown
          |
          v
Content rendered in browser
~~~

| Layer | Example | Key Rule |
| --- | --- | --- |
| Java source | "Line 1\nLine 2" | Escape according to Java string literals |
| YAML source | description: "Line 1\nLine 2" | Escape according to YAML double-quoted scalars |
| JSON output | "description": "Line 1\nLine 2" | Escape quotes, backslashes, and control characters |
| Markdown | bold, lists, headings | Use Markdown/CommonMark syntax |

There is no single escaping rule covering all four layers. Identify whether content is being written in Java, YAML, JSON, or Markdown before adding backslashes.

## 2. Markdown in OpenAPI Descriptions

OpenAPI allows CommonMark in description fields. Springdoc passes description text from annotations into the specification; Swagger UI then renders Markdown according to the capabilities of its UI version.

Fields that commonly hold descriptions:

- **@OpenAPIDefinition(info = @Info(description = ...))**: describes the API document.
- **@Operation(description = ...)**: describes an operation.
- **@Parameter(description = ...)**: explains a parameter.
- **@Schema(description = ...)**: describes an object or property.
- **@ApiResponse(description = ...)**: explains a response.
- **@SecurityScheme(description = ...)**: explains a security scheme.

Use summary for a short sentence identifying the operation and description for instructions, conditions, examples, or detailed rules. Avoid cramming multi-paragraph Markdown into summary because the UI may display summary in narrow slots.

Markdown content example:

~~~~markdown
Search books by keyword.

**Rules**

- q is the search keyword.
- page starts at 0.
- If there are no matches, the API returns an empty list.

Example request:

~~~http
GET /api/books?q=spring&page=0
~~~
~~~~

The snippet above has two paragraphs, a list, and a code block. Blank lines help Markdown separate blocks cleanly.

## 3. Line Breaks in Markdown

Markdown does not always treat a single newline character in source as a rendered line break. Adjacent lines of text in the same paragraph are usually joined into one line when rendered.

Source example:

~~~markdown
First line
Second line
~~~

Typically, renderers display them as one continuous paragraph. To start a new paragraph, insert a blank line:

~~~markdown
First line.

Second line.
~~~

If you genuinely need a hard line break within the same paragraph, CommonMark allows two trailing spaces at the end of a line or a backslash before the newline:

~~~markdown
Address: 12 Nguyen Hue.  
City: Ho Chi Minh.
~~~

Or:

~~~markdown
Address: 12 Nguyen Hue.\
City: Ho Chi Minh.
~~~

In technical documentation, prefer separate paragraphs or lists rather than relying on two trailing spaces. Trailing spaces are hard to see, easily stripped by editors or formatters, and can alter rendered output.

## 4. Escaping Special Markdown Characters

Certain characters carry syntactic meaning in Markdown: asterisks, underscores, hash signs, greater-than signs, square brackets, parentheses, pipes, and backslashes. When you want to display them as literal text, escape them with a backslash or place them inside a code span.

| Character to Display | Common Syntax | Result |
| --- | --- | --- |
| Asterisk | backslash + asterisk | asterisk |
| Underscore | backslash + underscore | underscore |
| Leading hash sign | backslash + hash sign | hash sign |
| Greater-than sign | backslash + greater-than sign | greater-than sign |
| Pipe in a table | backslash + pipe | pipe |
| Property name | springdoc.api-docs.path | springdoc.api-docs.path |

When describing class names, properties, endpoints, or expressions with many special characters, code spans are usually easier to read and less error-prone than escaping every character.

Example:

~~~markdown
The `springdoc.api-docs.path` property changes the OpenAPI document URL.

Generic `List<String>` represents a list of strings.

| Header | Meaning |
| --- | --- |
| A \| B | Expression containing a pipe |
~~~

For angle brackets or less-than/greater-than signs such as List&lt;String&gt;, code spans prevent renderers from misinterpreting them as HTML tags.

## 5. Code Spans and Code Fences

Code spans use a pair of backticks for a short inline snippet. Markdown source example:

~~~markdown
Set `springdoc.swagger-ui.path=/docs` in application.properties.
~~~

Code fences present multiline code snippets. Specify the language so readers recognize it easily and renderers can apply syntax highlighting:

~~~~markdown
~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~
~~~~

If the code itself contains three consecutive backticks, use a longer fence or tildes. Example:

~~~~~markdown
~~~~text
Example content containing three backticks inside.
~~~~
~~~~~

When writing a Java text block containing Markdown code fences, choose an outer fence distinct enough not to close the code block prematurely. In this article, examples use tilde fences so inner code can preserve its structure.

You do not need to escape quotes, slashes, or brackets inside a Markdown code fence. Content inside a code fence is treated as sample code rather than parsed as regular Markdown syntax.

## 6. Escaping Strings in Java Annotations

Annotations accept Java string values. With standard string literals, escape sequences are processed by Java before Springdoc receives the value:

~~~java
@Operation(
    summary = "Search books",
    description = "Search books by keyword.\n\n**Rules:**\n- q must not be blank.\n- page starts at 0."
)
~~~

In Java:

| Sequence in Source | Character in Runtime String |
| --- | --- |
| One backslash followed by n | Line feed, newline |
| One backslash followed by t | Tab |
| Two consecutive backslashes | One backslash |
| Backslash before double quote | One double quote |
| Two backslashes followed by n | Two characters: backslash and letter n |

A common point of confusion is the newline escape (one backslash followed by n) versus the literal string of two backslashes followed by n:

- One backslash followed by n produces an actual newline in the runtime string.
- Two backslashes followed by n produce two characters (backslash and n); when rendered, literal backslash-n appears.

If the goal is a line break in the description, use one backslash followed by n in Java source. If the goal is illustrating the literal characters backslash-n, use two backslashes followed by n.

## 7. Using Java Text Blocks for Multiline Descriptions

Since Java 15, text blocks make multiline strings much more readable:

~~~~java
@Operation(
    operationId = "searchBooks",
    summary = "Search books",
    description = """
        Search books by keyword with pagination.

        **Parameters**

        - q: search keyword.
        - page: page number, starting at 0.

        Example:

        ~~~http
        GET /api/books?q=spring&page=0
        ~~~
        """
)
~~~~

A text block is a string literal and can be used as an annotation value when it satisfies Java's constant expression rules. It preserves newlines in its content while Java still processes indentation and escape sequences under text-block rules.

Key considerations:

- Common leading indentation whitespace is stripped based on the closing delimiter position.
- Blank lines are preserved in the content.
- Escape sequences such as **\\n** and **\\\\** are still processed by Java.
- The closing delimiter's column determines how much indentation is stripped.
- Do not mix tabs and spaces if you want predictable alignment.

Place the closing delimiter at a consistent column and inspect the final String value when strict formatting is required.

With Java 8 or Java 11, you can concatenate strings:

~~~java
@Operation(
    description =
        "Search books by keyword.\n\n" +
        "**Parameters**\n\n" +
        "- q: search keyword.\n" +
        "- page: page number starting at 0."
)
~~~

When concatenating strings, each segment needs explicit newlines. Simply joining strings without **\n** will run lines together.

## 8. Escaping in YAML Scalars

When authoring OpenAPI YAML manually or placing descriptions in a YAML source, there are three common scalar styles:

### Plain Scalar

~~~yaml
description: Search books by keyword
~~~

Plain scalars fit simple single lines. If content contains a colon followed by whitespace, comment characters, or complex Markdown structure, use a quoted scalar or block scalar to prevent the YAML parser from misinterpreting it.

### Single-Quoted Scalar

~~~yaml
description: 'String with "double quotes" and backslash \n kept verbatim'
~~~

In single-quoted scalars, backslashes do not escape newlines. To include a single quote inside, write two consecutive single quotes:

~~~yaml
description: 'User''s API'
~~~

### Double-Quoted Scalar

~~~yaml
description: "First line\nSecond line"
~~~

Double-quoted scalars interpret YAML escape sequences. One backslash followed by n turns into a newline in the parsed value; two backslashes followed by n represent a backslash and the letter n.

## 9. Using Block Scalars to Keep Multiline Markdown Clean in YAML

For descriptions containing headings, lists, and code fences, block scalars are usually more readable and require less escaping:

~~~~yaml
description: |-
  Search books by keyword.

  **Rules**

  - q is the search keyword.
  - page starts at 0.

  Example:

  ~~~http
  GET /api/books?q=spring&page=0
  ~~~
~~~~

Block scalar indicators:

| Syntax | Meaning |
| --- | --- |
| literal block | Preserves newlines between lines and keeps one trailing newline per YAML rules |
| literal block with minus | Preserves internal newlines but strips trailing newlines |
| literal block with plus | Preserves all trailing newlines |
| folded block | Typically folds single newlines between text lines into spaces |
| folded block with minus | Folded block and strips trailing newlines |

For Markdown, literal blocks are usually better than folded blocks because Markdown relies on blank lines and line-by-line structure to recognize headings, lists, and code fences. Folded scalars can collapse Markdown lines into a single paragraph.

Block scalar indentation matters greatly. Content must be indented deeper than the `description` key; inconsistent indentation can cause YAML errors or misparsed structure.

## 10. Escaping JSON in OpenAPI Examples

OpenAPI JSON is standard JSON. Inside a JSON string:

- Double quotes inside the value must be preceded by one backslash.
- Literal backslashes inside the value must be represented by two consecutive backslashes.
- Newlines must use one backslash followed by n; do not insert raw line breaks inside a JSON string.
- Tabs and control characters must be escaped.

Valid JSON example:

~~~json
{
  "description": "First line\nSecond line",
  "path": "C:\\docs\\openapi"
}
~~~

After parsing the JSON, the description value contains an actual newline and path contains one backslash at each directory separator.

When using @ExampleObject, the `value` attribute is typically a string containing JSON. If using a regular Java string, you must escape both the Java layer and the JSON layer:

~~~java
@ExampleObject(
    name = "book",
    value = "{\"title\":\"Spring Boot\",\"note\":\"Line 1\\nLine 2\"}"
)
~~~

Here:

1. A backslash before a double quote is Java escaping to include quotes inside the string.
2. Two backslashes followed by n in Java source produce one backslash followed by n in the JSON text.
3. The JSON parser then converts the JSON newline escape into an actual newline in the value.

These are two nested escaping layers. Missing one layer prevents Java from compiling or produces invalid JSON examples.

## 11. Using Java Text Blocks for JSON Examples

Text blocks make JSON easier to read because individual double quotes do not need escaping:

~~~java
@ExampleObject(
    name = "book",
    summary = "Example of a book",
    value = """
        {
          "id": 42,
          "title": "Spring Boot",
          "note": "Line 1\\nLine 2",
          "path": "C:\\\\docs"
        }
        """
)
~~~

In this example, two backslashes before n in the Java text block produce one backslash before n in the JSON string. Likewise, four backslashes in source produce two backslashes in the JSON text, leaving one backslash in the parsed JSON value.

Do not replace two backslashes before n with one backslash before n in a JSON example when the goal is a JSON string containing an escaped newline. If Java processes the newline escape first, the JSON text receives a raw newline inside a quoted string and becomes invalid JSON.

## 12. Do Not Confuse Real Newlines with Literal Backslash-n

These two texts are different:

~~~text
Line 1
Line 2
~~~

and:

~~~text
Line 1\nLine 2
~~~

The first contains a newline character between the two lines. The second contains the two characters backslash and n. Depending on your goal:

| Goal | Java Source | Runtime Value |
| --- | --- | --- |
| Actual line break | Java source has one backslash before n | Two lines |
| Display literal backslash-n | Java source has two backslashes before n | Two characters: backslash and n |

When OpenAPI is serialized to JSON, real newlines inside a description are represented by the **\n** escape in JSON text. That is normal behavior of a JSON serializer; when clients parse the JSON, the description string still contains real newlines.

Do not inspect raw JSON text and assume content was double-escaped. Parse the JSON or view the description in Swagger UI to inspect the deserialized value.

## 13. Using Markdown for Property Names and HTML-Like Characters

Java generic names, expressions, or text containing less-than/greater-than signs should be placed in code spans:

~~~markdown
The handler returns Mono<ServerResponse>.

Generic Map<String, Object> represents a map with string keys.
~~~

If you write &lt;ServerResponse&gt; directly outside a code span, some renderers may interpret it as an HTML tag. When you need to display angle brackets as plain text, you can use HTML entities:

~~~markdown
Expression A &lt; B and C &gt; D.
~~~

Avoid injecting arbitrary HTML into descriptions. Swagger UI may sanitize or process HTML depending on its version's security policy; HTML content does not always render as expected. Prefer CommonMark and code spans.

In Markdown tables, the pipe character separates columns. If a cell value contains a pipe, escape it:

~~~markdown
| Header | Meaning |
| --- | --- |
| A \| B | Expression with a pipe |
~~~

Inside code fences, pipes do not need escaping because the parser is in code mode.

## 14. Writing Readable Descriptions in Swagger UI

A good description is structured to match the amount of information:

- Open with one or two sentences stating the operation's purpose.
- Use small headings when there are multiple rule groups.
- Use lists for preconditions or sequences.
- Use tables for parameter mappings, error codes, or enum values.
- Use code fences for sample requests/responses.
- Use inline code for properties, types, endpoints, and technical values.
- Separate paragraphs with blank lines.

Example:

~~~java
@Operation(
    summary = "Create book",
    description = """
        Create a new book in the catalog.

        **Rules**

        - title must not be blank.
        - publicationYear must not exceed the current year.

        **Outcomes**

        - 201: created successfully.
        - 400: invalid input data.
        - 409: book already exists.
        """
)
~~~

Do not add numerous headings for a description that is only a few sentences long. Conversely, long descriptions should be broken into small sections rather than written as one wall of text.

## 15. Markdown Structure Should Not Be Broken by Incorrect Escaping

Formatting bugs usually stem from escaping at the wrong layer or placing newlines incorrectly:

| Desired Output | Common Mistake | Proper Approach |
| --- | --- | --- |
| Two paragraphs | Breaking line only once | Insert a blank line |
| Markdown bold | Escaping asterisks around words | Write bold syntax directly |
| Code span | Escaping every character inside code | Use a code span |
| Markdown list | Putting literal backslash-n characters | Produce real newlines in the runtime String |
| JSON example with newline | Inserting raw newline inside JSON string | Use JSON escape \n |
| Multiline YAML description | Using a long plain scalar | Use a literal block |
| Pipe inside table cell | Writing unescaped pipe value | Escape pipe or use a code span |
| Code fence containing backticks | Outer fence same length as inner fence | Use a longer outer fence or tildes |

Do not escape an entire Markdown block before placing it into an annotation. Doing so causes bold markers, lists, or code fences to display verbatim instead of rendering.

## 16. Verifying Content via OpenAPI JSON/YAML

After starting the application, open the OpenAPI endpoint, typically /v3/api-docs or the path configured via springdoc.api-docs.path.

Inspect these fields:

- info.description for the overview description.
- description of each operation under paths.
- description of each parameter.
- requestBody.description and requestBody.content for requests.
- description and content of each response by status code.
- description of schemas and each property in components.schemas.

When viewing raw JSON, newlines are normally serialized as **\n**. That does not mean Swagger UI will display literal backslash and n. Once JSON is parsed, the String value contains actual newlines.

With YAML output, block scalars may represent multiline descriptions using literal style or an equivalent form depending on the serializer. Do not infer content solely from how the serializer chose quotes or block style; inspect the parsed value.

## 17. Verifying Rendering in Swagger UI

After confirming the OpenAPI document has the right content, open Swagger UI and check:

1. Are paragraphs separated properly?
2. Do headings and lists render at the intended levels?
3. Does inline code preserve property names, types, and endpoints?
4. Do code fences preserve indentation without closing prematurely?
5. Do tables have all columns intact without breaking on pipes in cell text?
6. Do less-than/greater-than signs render as code rather than getting parsed as HTML?
7. Do lines containing backslashes show the right number of characters?
8. Can JSON examples be copied and parsed cleanly?

If OpenAPI JSON is accurate while the UI renders differently, the cause may lie in Swagger UI's Markdown renderer or sanitizer. Try basic CommonMark syntax before using HTML or renderer-specific extensions.

## 18. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Swagger UI displays literal backslash-n | Java source used two backslashes before n so runtime received backslash and n | Use one newline escape when an actual line break is needed |
| Two lines merge into one paragraph | Markdown source lacks a blank line | Insert a blank line between paragraphs |
| List does not render | Items lack newlines or indentation is wrong | Use real newlines and hyphen prefixes |
| Bold or heading shows raw asterisks/hashes | Unnecessarily escaped Markdown syntax | Remove backslashes before Markdown symbols |
| JSON example throws parse error | Java and JSON escaping got mixed | Inspect JSON text produced after Java builds the String |
| JSON has raw newline inside string | Java text block turned newline escape into raw newline before JSON parsing | Use double backslash before n in Java text blocks for JSON escapes |
| Backslashes in Windows paths disappear | Java or JSON treated backslash as an escape | Escape per layer or use text blocks properly |
| YAML parse error on description | Plain scalar contains special characters or bad indentation | Use quoted scalar or block scalar |
| YAML Markdown lines get collapsed | Used a folded scalar | Use a literal block |
| Table columns shift | Unescaped pipe in cell | Escape pipes or use code spans appropriately |
| Code block gets truncated | Inner fence matches outer fence | Increase outer fence length or switch to tildes |
| HTML tags vanish | Renderer sanitizes HTML | Use CommonMark, code spans, or HTML entities |

## 19. Recommended Conventions for Development Teams

To keep documentation consistent across controllers and modules:

1. Write descriptions in short sentences stating purpose and usage conditions clearly.
2. Use Java text blocks for multiline descriptions when targeting Java 15 or newer.
3. On older Java versions, concatenate strings with explicit double newlines between paragraphs.
4. Use YAML literal block scalars when storing multiline Markdown in OpenAPI YAML.
5. Apply proper JSON escaping inside @ExampleObject.value.
6. Escape characters only when required by the syntax of the current layer.
7. Use code spans for technical identifiers containing special characters.
8. Use language-tagged code fences and check nested fences.
9. Avoid hard line breaks based on trailing spaces.
10. Verify both OpenAPI JSON/YAML and Swagger UI before publishing documentation.

## 20. Checklist Before Finalizing Descriptions

- [ ] Identified whether the string is written in Java, YAML, JSON, or Markdown.
- [ ] Applied escape sequences for the right layer without double-escaping.
- [ ] Used Java newline escapes for actual newlines in Strings.
- [ ] Ensured JSON strings contain no raw newlines or unescaped quotes.
- [ ] Used appropriate block scalars for multiline YAML descriptions.
- [ ] Included blank lines between Markdown paragraphs.
- [ ] Verified headings, lists, tables, and code fences have valid syntax.
- [ ] Escaped special characters or wrapped them in code spans where needed.
- [ ] Avoided relying on trailing spaces for line breaks.
- [ ] Maintained consistent indentation inside Java text blocks.
- [ ] Verified parsed description values in OpenAPI JSON/YAML.
- [ ] Confirmed Swagger UI renders paragraphs, lists, tables, code, and examples properly.

Escaping and line breaks must be handled according to the right syntax layer. Java governs the runtime String, YAML/JSON governs how strings are stored and transmitted, and Markdown governs how descriptions are presented. Using real newlines for Markdown structure, proper JSON escaping, and avoiding double-escaping keeps Springdoc documentation readable in Swagger UI while preserving accurate content in OpenAPI JSON/YAML.
