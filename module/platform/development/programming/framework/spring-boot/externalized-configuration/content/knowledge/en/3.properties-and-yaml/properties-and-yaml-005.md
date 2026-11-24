# Multiline Strings in YAML: Preserving and Folding Line Breaks

## 1. Why are multiline strings needed?

In Spring Boot configuration, many properties need only a single line: service port, retry count, server address. Yet some values naturally span multiple lines, such as:

- Email bodies or notifications sent to users.
- Text displayed on a welcome screen.
- Long SQL queries or structured data templates.
- Instructions, descriptions, terms, or multi-paragraph messages.

There are two distinct needs. For an email, line breaks are part of the content and must be preserved. For a description wrapped solely for readability in the configuration file, the application usually wants **a single continuous string** with lines joined by spaces.

YAML addresses both needs with **block scalars**:

- `|` (*literal style*): preserves line breaks between content lines.
- `>` (*folded style*): folds ordinary consecutive lines into one line separated by spaces; blank lines still mark paragraph breaks.

These two symbols determine **how text in YAML becomes a string value**. When Spring Boot loads `application.yaml`, the application receives the value already processed by the YAML parser, not the raw visual layout from the file.

## 2. Visualizing how YAML processes lines

Consider two values both written across three lines:

~~~yaml
app:
  literal-message: |
    Hello,
    the system will undergo maintenance today.
    Thank you.

  folded-message: >
    Hello,
    the system will undergo maintenance today.
    Thank you.
~~~

If we use `\n` to **represent** a newline character in the explanation, the two values correspond to:

~~~text
app.literal-message
"Hello,\nthe system will undergo maintenance today.\nThank you.\n"

app.folded-message
"Hello, the system will undergo maintenance today. Thank you.\n"
~~~

In these two illustrations, `\n` represents **an actual newline character**. It does not mean YAML inserted the two literal characters backslash and `n`.

Notice the final `\n` in both values: that is the **default ending rule** for block scalars. The next sections explain how to change it.

### Distinguishing three concepts

1. **Physical line in the YAML file:** the line you see in your editor.
2. **Line breaks inside the string value:** the actual characters remaining after YAML is parsed.
3. **Trailing line break at the end of the string:** the ending character after the last content line; controlled separately by *chomping* rules.

Two values can occupy the same number of lines on screen yet produce completely different strings.

## 3. The `|` indicator: preserving line breaks

`|` fits when **how lines are broken is part of the meaning**.

~~~yaml
mail:
  subject: "Maintenance Notice"
  body: |
    Hello,

    The service will undergo maintenance from 22:00 to 23:00.
    Please save your work before this time.

    Best regards,
    Operations Team
~~~

The value of `mail.body` preserves the line breaks between text lines. The blank lines between paragraphs are also preserved. With default `|`, the string also ends with a trailing newline after `Operations Team`.

When sending the content via a plain-text email API, the text stays divided into paragraphs as desired. If sent as HTML, newline characters in a string do not automatically become `<br>` tags; rendering depends on the content format and the receiving application.

Another example is a multiline string used as a banner:

~~~yaml
app:
  banner: |-
    -------------------------
    APPLICATION UNDER MAINTENANCE
    Please check back later.
    -------------------------
~~~

Here, `|-` preserves the line breaks **inside** the banner while stripping the **trailing** newline at the end of the string. That way, Java code can decide on its own whether to add a blank line after the banner.

### When should you choose `|`?

- Plain-text email content or notifications requiring specific paragraph breaks.
- Text output templates, signatures, banners, or commands where line boundaries matter.
- Data whose line structure must stay intact for further processing.

`|` preserves line breaks, yet it is still subject to YAML's **indentation and whitespace** rules. It does not mean every space used for indentation in the file becomes part of the string content.

## 4. The `>` indicator: folding lines for readable prose

`>` is useful when the content is a long paragraph and splitting it across multiple lines in the file is only to make it easier to read and version-control.

~~~yaml
app:
  description: >-
    This service processes account registration requests
    and sends a confirmation email to the user
    after the data is validated.
~~~

The resulting value is:

~~~text
"This service processes account registration requests and sends a confirmation email to the user after the data is validated."
~~~

`>` replaces line breaks between ordinary text lines with **a single space**. `-` strips the trailing newline at the end of the string.

### Blank lines create paragraph boundaries

`>` does not collapse everything onto one line. When there is a blank line between two groups of text lines, the paragraph boundary is preserved:

~~~yaml
app:
  description: >-
    First, the user enters information
    and submits a registration request.

    Then, the system sends an email
    to confirm the contact address.
~~~

The result can be represented as:

~~~text
"First, the user enters information and submits a registration request.\nThen, the system sends an email to confirm the contact address."
~~~

One blank line between two paragraphs in YAML corresponds to one newline character between the two paragraphs in the folded value. If multiple explicit blank lines are required, examine the exact number of blank lines and how the block terminates.

### More-indented lines are a special case

Inside a `>` string, a line indented **deeper than the normal content level** is called a *more-indented* line. YAML preserves line breaks associated with more-indented sections rather than folding them under the normal rule.

~~~yaml
help:
  message: >-
    Steps to perform:
      1. Open settings.
      2. Select notifications.
    Complete the action.
~~~

Because there are two content spaces before `1.` and `2.`, this example behaves differently from a paragraph whose lines all share the same indentation. For instructions with fixed formatting, `|` is usually clearer and less surprising than `>`.

## 5. `-`, `+`, and default: controlling the end of the string

`|` or `>` determines **how line breaks in the body are handled**. A second indicator, if present, determines **trailing line breaks at the end of the value**. This is the *chomping* rule.

| Form | Rule name | Meaning |
| --- | --- | --- |
| `|` or `>` | Clip (default) | Keeps one final newline; strips extra trailing blank lines. |
| `|-` or `>-` | Strip | Strips the final newline and any trailing blank lines. |
| `|+` or `>+` | Keep | Keeps the final newline and all trailing blank lines. |

**The only difference is at the end of the string**. For instance, `|-` still preserves line breaks between content lines, while `>-` still folds ordinary lines into a paragraph.

### Comparing the same content

~~~yaml
clip: |
  A
  B

strip: |-
  A
  B

keep: |+
  A
  B

next: value
~~~

The effective characters are described as follows:

| Key | String representation | Explanation |
| --- | --- | --- |
| `clip` | `"A\nB\n"` | Ends with exactly one newline character. |
| `strip` | `"A\nB"` | No trailing newline. |
| `keep` | `"A\nB\n\n"` | Has the trailing newline plus one blank line before the next key. |

In the example, the blank line right before `next` belongs to the `keep` block and is preserved because of `+`. Adding more blank lines at the end of the block causes `+` to preserve those as well.

Common choices:

- Want a multiline string **without an automatic trailing newline**: choose `|-`.
- Want a long description as one continuous paragraph: choose `>-`.
- Want standard multiline text with one trailing newline: choose `|`.
- Only use `+` when trailing blank lines are genuinely required by a format.

Do not mistake `|-` for "removing all line breaks"; it only strips the trailing ending of the value.

## 6. Indentation: YAML uses spaces to define the string scope

A block scalar sits beneath a YAML key. Its content must be indented deeper than the key that owns it:

~~~yaml
app:
  greeting: |-
    Hello,
    have a great day.
  timeout: 10s
~~~

The two lines `Hello,` and `have a great day.` belong to the value of `app.greeting`. The key `timeout` returns to the same indentation level as `greeting` and is therefore **outside the string**.

The YAML parser detects a common indentation level for the block and **strips that indentation** from each line of the value. Spaces beyond that common level remain part of the content.

~~~yaml
app:
  message: |-
    Normal line
      Line indented by two spaces
    Final line
~~~

Corresponding value:

~~~text
"Normal line\n  Line indented by two spaces\nFinal line"
~~~

The second line has two spaces **inside the actual string**. Distinguish these from the four block-level spaces used for YAML layout.

### Explicit indentation indicator

Normally YAML infers content indentation from the first non-empty line. When you need to preserve leading spaces on lines or when the first line is all whitespace, you can specify the indentation level right after `|` or `>`:

~~~yaml
banner: |2-
    Line with two leading spaces.
    Next line.
~~~

`2` specifies a block indentation of two spaces relative to the root key. In the example, each content line is indented four spaces; after stripping the two block spaces, the value keeps **two leading spaces on each line**.

Forms like `|2-` and `|-2` both express an indentation indicator combined with the *strip* rule. Still, for ordinary configuration, prefer consistent indentation and only use numeric indicators when leading whitespace must be preserved.

**Note:** YAML uses spaces for indentation. Never use tabs for structural indentation; tabs can make the file unparseable. Trailing spaces on lines can also become unwanted content, especially when strings are processed character-for-character.

## 7. Colons, `#`, and special characters in block scalars

Inside a `|` or `>` block, characters such as colons and hash symbols are generally treated as **plain text content** as long as they stay within the block's indentation:

~~~yaml
app:
  instructions: |-
    Note: do not close the application.
    # This is a content line, not a YAML comment.
    Step 1: save data.
    Step 2: close the program.
~~~

The line starting with `#` above **still belongs to `app.instructions`**, because it is inside the block scalar content. Likewise, `:` in a sentence does not open a new YAML key.

Once the block's indentation ends, YAML resumes parsing keys and values according to normal structure. Therefore, you cannot arbitrarily align a content line with the parent key.

A literal `\n` typed **inside** a `|` or `>` block is not a newline escape; the backslash and `n` are ordinary characters inside the block scalar. Use physical lines and choose `|`/`>` to express line-break intent.

## 8. Using multiline strings in Spring Boot's application.yaml

Suppose an application needs two properties: a notification template that keeps line breaks and a description that folds lines.

`src/main/resources/application.yaml`:

~~~yaml
app:
  notice: |-
    Hello,

    Your request has been received.
    We will contact you within 24 hours.

    Best regards,
    Support Team

  description: >-
    The service receives support requests,
    verifies the required details,
    and routes the request to the responsible team.
~~~

After Spring Boot loads Config Data, the keys `app.notice` and `app.description` become string values accessible via `Environment`.

### 8.1. Reading directly with Environment

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class NoticeService {
    private final Environment environment;

    public NoticeService(Environment environment) {
        this.environment = environment;
    }

    public String notice() {
        return environment.getRequiredProperty("app.notice");
    }

    public String description() {
        return environment.getRequiredProperty("app.description");
    }
}
~~~

`notice()` returns a string preserving the line breaks and blank lines in the template; `description()` returns a continuous paragraph. Because both use `-`, neither has a trailing newline.

### 8.2. Binding multiple properties with @ConfigurationProperties

When you have a group of related properties, you can use a record:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppTextProperties(
        String notice,
        String description) {
}
~~~

Register the record using `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(AppTextProperties.class)` in configuration. Spring Boot then binds both keys to the corresponding `String` fields.

~~~java
import org.springframework.stereotype.Service;

@Service
public class MessageService {
    private final AppTextProperties properties;

    public MessageService(AppTextProperties properties) {
        this.properties = properties;
    }

    public String composeNotice() {
        return properties.notice();
    }
}
~~~

The return type remains `String`; `|` and `>` syntax only participates when **parsing the YAML file**, and does not appear as special syntax in Java.

### 8.3. Using @Value for a single key

You can also read a single property on its own:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class NoticeTemplate {
    private final String text;

    NoticeTemplate(@Value("${app.notice}") String text) {
        this.text = text;
    }

    public String text() {
        return text;
    }
}
~~~

`@Value` receives the string resolved from `Environment`. If the value contains real line breaks, Java keeps them. Spring does not automatically insert or strip line breaks just because `@Value` is used instead of `@ConfigurationProperties`.

## 9. Distinguishing YAML formatting from the value used by the application

Suppose two configuration entries are written differently:

~~~yaml
first: |-
  First line
  Second line

second: >-
  First line
  Second line
~~~

When the application concatenates, compares, sends over HTTP, or displays them, line breaks can affect the outcome:

~~~java
String first = environment.getRequiredProperty("first");
String second = environment.getRequiredProperty("second");

System.out.println(first.equals(second)); // false
System.out.println(first.contains("\n"));  // true
System.out.println(second.contains("\n")); // false
~~~

`first` contains `"First line\nSecond line"`; `second` contains `"First line Second line"`. The two values differ even though both are laid out across two YAML lines.

For human-readable text, this difference may only affect display. For strings used in digital signing, checksum calculation, signature verification, exact matching, or transmission to systems requiring fixed formatting, differing by a single newline can cause failures.

Also remember that the string only holds this value after YAML is parsed. If the same property also exists in an environment variable or command-line argument with higher precedence, the value the application receives is determined by Spring Boot's property source order. `|`/`>` does not alter that precedence.

## 10. Common misuse scenarios

### 10.1. Using `>` for text that must keep line breaks

~~~yaml
script: >-
  echo start
  echo done
~~~

The effective string is `"echo start echo done"`, not two separate commands. If the receiving system requires one command per line, use `|-`.

### 10.2. Using `|` for a description wrapped only for readability

~~~yaml
description: |-
  This is a long description
  split across lines for readability.
~~~

The value keeps a newline in the middle, whereas Java code may expect a continuous paragraph. For that purpose, `>-` is more appropriate.

### 10.3. Forgetting the trailing newline

~~~yaml
payload: |
  READY
~~~

The value is `"READY\n"`, not `"READY"`. If an external protocol requires an exact match for `READY`, use `|-`.

### 10.4. Treating every blank line in `>` as a space

Blank lines create paragraph breaks, so `>` does not simply replace every newline with a space. When text has multiple paragraphs or more-indented lines, folding has exceptions. If you need control over every line break, choosing `|` is more predictable.

### 10.5. Misaligning content indentation

~~~yaml
app:
  message: |-
    Valid line
  Misaligned line
~~~

`Misaligned line` does not belong to `app.message`. Because it lacks valid key–value syntax at that position, this example causes a YAML syntax error. Check space positions, avoid tabs, and indent content deeper than the `message` key.

### 10.6. Confusing escapes with real newlines

~~~yaml
app:
  text: |-
    Line one\nLine two
~~~

The content here has only **one physical line** and contains the two literal characters `\` and `n` in the middle. It is not the same as:

~~~yaml
app:
  text: |-
    Line one
    Line two
~~~

Only the second example has a real line break between the two text parts.

### 10.7. Assuming YAML protects sensitive data

Block scalars help represent multiline strings; they do not encrypt data or replace secrets management. Never put secret keys or sensitive content into an `application.yaml` committed to a public repository. Multiline secrets such as certificates or cryptographic keys can also require exact newline formatting, so check the documentation of both the secret provider and the consumer.

## 11. How to inspect the real value when debugging

When content renders incorrectly, the naked eye often cannot distinguish spaces, newlines, or trailing characters. In development, inspect the string loaded from `Environment`:

~~~java
String value = environment.getRequiredProperty("app.notice");

System.out.println("Length = " + value.length());
System.out.println(
    value.replace("\r", "\\r")
         .replace("\n", "\\n\n")
);
~~~

This prints `\r`/`\n` markers to make line-break characters visible. For sensitive data, **do not log the value**; use harmless sample strings when practicing.

If the value still differs from expectations, check in order: whether the intended YAML file is being loaded; whether the key is overridden by a higher-precedence configuration source; whether `|` or `>` was chosen; whether `-`/`+` is used; and whether indentation and trailing blank lines are right. These are the most frequent causes.

## 12. Practice exercises

### Exercise 1 — predict the resulting string

~~~yaml
a: |-
  Hello
  there
b: >-
  Hello
  there
c: |
  Hello
  there
~~~

Represent each result using `\n`:

- `a` has a newline between the two words and no trailing newline.
- `b` has a space between the two words and no trailing newline.
- `c` has a newline between the two words and one trailing newline.

Answer:

~~~text
a = "Hello\nthere"
b = "Hello there"
c = "Hello\nthere\n"
~~~

### Exercise 2 — fix syntax to match intent

The application needs to send the following email:

~~~text
Hello,

Your request is complete.
Thank you.
~~~

Create `mail.body` with the exact line breaks shown above and no trailing newline. Answer:

~~~yaml
mail:
  body: |-
    Hello,

    Your request is complete.
    Thank you.
~~~

### Exercise 3 — reduce physical line width without becoming multiline in Java

Given a three-sentence description, wrap the text across multiple lines in the file for readability while retrieving only **a single line**:

~~~yaml
app:
  description: >-
    The system validates the request.
    Then the data is saved.
    Finally the result is returned.
~~~

Check with `Environment.getProperty("app.description")`. The result is a single string with sentences separated by spaces and no internal or trailing newlines.

### Exercise 4 — test the effect of `+`

Write a `|+` string with two extra blank lines before the next key, then compare its length against `|` and `|-` with the same body content. Notice the number of trailing newline characters kept at the end. Observe the actual values to distinguish *clip*, *strip*, and *keep*.

## 13. Selection cheat sheet

| Goal | Syntax to consider | Thing to remember |
| --- | --- | --- |
| Keep newlines between lines and keep one trailing newline | `|` | Fits standard multiline text. |
| Keep internal newlines with no trailing newline | `|-` | Easy to use for email templates, banners, and exact-match strings. |
| Fold physical lines into one paragraph, keeping trailing newline | `>` | Blank lines and more-indented lines have special rules. |
| Fold lines and strip trailing newline | `>-` | Fits long descriptions wrapped across multiple YAML lines. |
| Keep trailing blank lines as well | `|+` or `>+` | Use only when trailing whitespace is meaningful. |
| Content with leading spaces that must be preserved | `|2-` or corresponding indentation indicator | Check common indentation and remaining spaces. |

**Quick memory rule:** `|` keeps lines, `>` folds lines; `-` strips the trailing newline, `+` keeps trailing blank lines, and no modifier keeps one trailing newline by default. Spring Boot reads **the string value after YAML parsing**; block scalar syntax only controls how that value is produced.

**References:**
- [YAML 1.2.2 — Block Scalar Styles](https://yaml.org/spec/1.2.2/#81-block-scalar-styles).
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
