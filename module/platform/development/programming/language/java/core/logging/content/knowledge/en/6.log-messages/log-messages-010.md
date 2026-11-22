# Message Language in Java Core Logging

## 1. What Is Log Message Language?

In logging, a **message** is the natural-language description of an event that an application wants to record. The **message language** can be English, Vietnamese, or another language, depending on the audience, the operations system, and project policy.

For example, the same event:

~~~text
English: Order ORD-42 was created successfully
Tiếng Việt: Đơn hàng ORD-42 đã được tạo thành công
~~~

The two sentences are in different languages but describe the same **order.created** event. The event does not change when the message is translated. This is the most important point when designing logs: **technical semantics and identifier fields remain stable; human-readable text can be localized when needed**.

This lesson helps you:

- Choose a consistent language for messages used to diagnose Java applications.
- Distinguish **logs for operations engineers** from **user-facing notifications** and localized content.
- Design **event keys/codes**, message templates, and structured attributes so logs remain searchable even when text changes.
- Understand **Locale**, **ResourceBundle**, **LogRecord**, and **Formatter.formatMessage** in **java.util.logging (JUL)**.
- Write and run a Java 17+ program that emits the same event with English and Vietnamese messages.
- Handle parameters, Unicode, fallbacks, exceptions, multithreaded context, and common mistakes that make logs hard to analyze.

**Scope:** This lesson belongs to the **Log message** group of **Java Core Logging**. Its focus is the language of log content and how to manage it; it does not expand into a full course on UI internationalization or configuring a specific observability backend.

## 2. Distinguishing Types of Language in a Log Record

A log record can contain multiple kinds of data, but not every field should be translated.

Example of structured log data:

~~~json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "event": "order.created",
  "language": "vi-VN",
  "message": "Đơn hàng ORD-42 đã được tạo thành công",
  "order_id": "ORD-42",
  "request_id": "req-42"
}
~~~

| Component | How should it be managed? | Why? |
| --- | --- | --- |
| **event = order.created** | Stable name, not translated per locale | Used for searching, aggregation, and linking to alerts |
| **level = INFO** | Value defined by the logging API/backend | Severity must not change based on message language |
| **service, request_id, order_id** | Consistent field names and identifiers | Cross-service querying and request correlation |
| **message** | Language chosen according to policy | Helps human readers understand the event |
| **language/locale** | BCP 47 tag such as en or vi-VN when actually needed | Identifies the translation of the message |
| **timestamp** | Time point with timezone, consistent format | Used for comparison, ordering, and investigation |
| **error.type** | Stable error code/type | Aggregates errors even when messages differ |

**Do not use translated text as the sole identifier key.** If a sentence changes from "Order created" to "Created order" or is translated into Vietnamese, full-sentence-based search becomes fragmented. The event code **order.created** lets you find the same event with a fixed condition.

### 2.1. Diagnostic Messages Differ from UI Notifications

Three surfaces are commonly confused:

1. **Operational logs:** intended for developers, SREs, support teams, and alerting systems. They must be easy to search, carry investigative information, and never expose sensitive data.
2. **User-facing messages:** returned to web/mobile interfaces or customer-facing documentation. They usually need to be translated according to the user's locale and written for product experience.
3. **Audit/security events:** audit records require dedicated structure, durability, access control, and retention policies. Translating content must not break event codes used for auditing.

Example when a payment is rejected:

~~~text
Log event: payment.rejected
Log message: Payment rejected by issuer; reason=do_not_honor
User message vi-VN: Không thể hoàn tất thanh toán. Vui lòng thử phương thức khác.
~~~

Do not expose raw technical logs or stack traces to end users. Conversely, friendly UI translations usually lack enough context for engineers to diagnose server-side errors.

## 3. Choosing English, Vietnamese, or Locale-Based Localization?

There is no single mandatory rule for all Java projects. You should choose based on **the audience** and **how telemetry is consumed**.

### 3.1. One Standard Language for Operational Logs

For many systems with international development teams, **consistent English** is a common choice because API names, exceptions, search tools, and technical documentation are usually in English. In an internal operations team that only uses Vietnamese, consistent use of Vietnamese can also be appropriate.

What matters more than the specific choice is:

- Having a **shared convention** for new messages.
- Using consistent business terminology and action names.
- Not randomly mixing English and Vietnamese for the same event type.
- Not automatically switching log language whenever an individual user changes their UI language if logs are used for centralized querying.
- Keeping event codes and field names stable so cross-service data remains compatible.

A multi-instance system should avoid having each machine emit the same event in a different language solely due to default OS/JVM configuration.

### 3.2. Localizing Messages When There Is a Real Need

Localized logging can be useful when logs are displayed directly to regional support teams, when a product has a multilingual dashboard, or when specific documentation/operational requirements exist.

In that case, store at least:

- A language-independent **event key/code**;
- **Clearly named or structured parameters**;
- **The locale of the translation**, if the translation is stored as part of the event;
- **The rendered message**, if immediate human readability is needed.

There are two main approaches:

**Translate at log-creation time:** the producer selects the locale, looks up the message template, and writes the final text. This is immediately readable, but can cause centralized data to contain multiple languages.

**Translate at display time:** the producer stores the event key and data; the log viewer chooses the language and renders the message. This makes switching the reader's language easy, but requires the display system to maintain a translation catalog and template versioning.

Do not auto-translate at the collector as a one-way step and discard the original event code: translation may be inaccurate, lose technical meaning, and make querying difficult.

### 3.3. An Easy-to-Operate Policy

A practical policy is:

- Production logs use **one standard technical language** for the message field.
- Event codes, attributes, severity, and technical errors use a stable schema.
- User-facing notifications are translated **separately**, according to the UI locale.
- Support multilingual log messages only when there is a concrete need and dedicated testing.
- Never use message sentences as the sole key for dashboards or alerts.

This is an architectural recommendation, not a fixed rule of Java.

## 4. Writing Clear and Translatable Messages

A useful message must help operators know **what happened**, **the outcome**, **the involved entity**, and **the next action when needed**.

Poor examples:

~~~text
Error
Failed!!!
Something went wrong
Đã có lỗi xảy ra
Lỗi tại đây
~~~

These sentences lack the subject, context, or cause. Better examples:

~~~text
event=order.created orderId=ORD-42
event=payment.rejected reasonCode=do_not_honor
event=inventory.lookup_failed dependency=inventory-db errorType=TimeoutException
~~~

If the application also includes human-readable messages:

~~~text
English: Inventory lookup timed out after 250 ms
Tiếng Việt: Tra cứu tồn kho hết thời gian chờ sau 250 ms
~~~

**Authoring rules:**

1. Use clear subjects and verbs, e.g., "Order created", "Connection timed out", "Retry scheduled".
2. Use consistent tense/state: **created** means completed; **creating** means in progress. A translation must not change the meaning of the event.
3. Avoid messages containing only exclamations or severity words. Severity already belongs in the level field.
4. Write stable templates; put orderId, duration, and reasonCode into **parameters/fields** instead of generating thousands of completely different sentences.
5. Do not attempt to translate **class names, package names, exception types, HTTP statuses, traceId, metric names, or event keys**. These are technical data, not ordinary prose.
6. Standardize business terminology. For example, *order* in a system might be **đơn hàng** in Vietnamese; do not alternate between different terms for the same concept.
7. Place important information in queryable fields. Messages help with quick reading; **schemas and event IDs** enable querying and automation.
8. Avoid arbitrary punctuation that makes grepping harder; if single-line text logs are desired, sanitize newlines and control characters from inputs.

### 4.1. Assign Levels by Semantics, Not by Language

The same event translated into two languages must still have the same severity, unless the business behavior itself differs:

~~~text
INFO  event=order.created message=Order created successfully
INFO  event=order.created message=Đơn hàng đã được tạo thành công
WARN  event=payment.rejected reasonCode=issuer_unavailable
~~~

Do not escalate WARNING to SEVERE just because a translated sentence sounds "more serious." Base severity on operational impact, recovery state, and application policy.

## 5. Java Locale and ResourceBundle

Java provides internationalization (i18n) mechanisms through **java.util.Locale** and **java.util.ResourceBundle**.

**Locale** describes a language/region context, for example:

~~~java
Locale.ENGLISH;                // en
Locale.forLanguageTag("vi");   // vi
Locale.forLanguageTag("vi-VN"); // vi-VN
Locale.forLanguageTag("en-US"); // en-US
~~~

The snippet above only illustrates Java expressions and is not a standalone runnable program. **Language tags** should be standardized, typically using BCP 47 such as **en**, **vi**, or **vi-VN**.

**ResourceBundle** is a collection of translations/values looked up by **key** and **Locale**. Example logical catalog:

| Key | en | vi |
| --- | --- | --- |
| order.created | Order {0} was created successfully | Đơn hàng {0} đã được tạo thành công |
| order.rejected | Order {0} was rejected | Đơn hàng {0} đã bị từ chối |
| inventory.timeout | Inventory lookup timed out | Tra cứu tồn kho đã hết thời gian chờ |

Here **{0}** is a parameter in **java.text.MessageFormat** syntax. The key and event meaning stay the same; the catalog supplies text matching the locale.

A ResourceBundle can be backed by:

- **Properties files** on the classpath, such as messages_en.properties and messages_vi.properties.
- **Java classes extending ListResourceBundle**, suitable for standalone examples or scenarios managed in code.

When using **ResourceBundle.getBundle(baseName, locale)**, Java searches for bundles following the candidate locale chain and ResourceBundle fallback mechanism. There is no guarantee every key has a translation: you may encounter **MissingResourceException** or receive a fallback value depending on lookup/configuration.

**Note:** The JVM default Locale is process-wide state. Do not use **Locale.setDefault(...)** per request in a multithreaded server to translate logs individually; other requests can be unintentionally affected. If you need to control a specific language, pass **Locale** explicitly to where the template is selected.

## 6. The i18n Mechanism of java.util.logging (JUL)

JUL has the following components related to message language:

- **Logger:** where LogRecords are emitted; a Logger can be associated with a ResourceBundle name at the logger level depending on the API used.
- **LogRecord:** holds level, message/key, parameters, Throwable, and optionally a **ResourceBundle** along with the bundle name.
- **ResourceBundle:** maps a key such as order.created to an English/Vietnamese template.
- **Formatter:** converts a LogRecord into text. **Formatter.formatMessage(record)** looks up the message using the ResourceBundle on the record and formats parameters according to JUL conventions.
- **Handler:** writes Formatter output to the console, a file, or another destination.

High-level processing pipeline:

~~~text
Code emits event "order.created"
           |
           v
       LogRecord
  level=INFO
  message="order.created"
  parameters=["ORD-42"]
  resourceBundle=messages_vi
           |
           v
  Formatter.formatMessage(record)
  -> look up "order.created" in bundle
  -> retrieve "Đơn hàng {0} đã được tạo thành công"
  -> replace parameter {0} with "ORD-42"
           |
           v
  "Đơn hàng ORD-42 đã được tạo thành công"
           |
           v
  Handler / console / file
~~~

**Distinguish message key from formatted message:** In the example, **record.getMessage()** remains **order.created**; **formatMessage(record)** produces the translated sentence. If only the translated sentence is recorded without keeping the key in another field, querying across languages by event becomes harder.

### 6.1. Attaching a Bundle to a Logger or LogRecord

JUL supports declaring a logger with a bundle name, such as:

~~~java
Logger logger = Logger.getLogger("demo.orders", "messages");
~~~

This snippet **requires a messages catalog available on the classpath**; this single line is not a complete program. When using this approach, the application must understand how JUL locates bundles and locales at runtime. A Logger shared across all requests should not be treated as a "per-request language switcher" by repeatedly reconfiguring global state.

To demonstrate selecting a **distinct locale per event** and avoid affecting the default Locale, the program in the next section creates a **LogRecord** and attaches the corresponding ResourceBundle. This technique is especially easy to verify in a Java Core example; it does not mean every production application must manually instantiate LogRecord.

## 7. Standalone Java 17+ Example: Same Event, Two Languages

The following program:

1. Uses **one stable event key**: order.created.
2. Defines two **ListResourceBundle** classes for **en** and **vi** in the same Java file so it can run immediately.
3. Creates two INFO LogRecords, each carrying a **ResourceBundle** and the orderId parameter.
4. Uses **Formatter.formatMessage(record)** to obtain the translated sentence.
5. Prints **event key, language, and message** to clearly show the stable part and the localized part.

Create the file **LogMessageLanguageDemo.java**, saving the source code in **UTF-8**:

~~~java
import java.util.ListResourceBundle;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LogMessageLanguageDemo {
    private static final Logger LOG = Logger.getLogger("demo.language");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler handler = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                String language = record.getResourceBundle().getLocale().getLanguage();
                return "event=" + record.getMessage()
                        + " lang=" + language
                        + " message=" + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        handler.setLevel(Level.INFO);
        LOG.addHandler(handler);

        try {
            emit(Locale.ENGLISH, "ORD-42");
            emit(Locale.forLanguageTag("vi"), "ORD-42");
            handler.flush();
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }
    }

    private static void emit(Locale locale, String orderId) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("LogMessageLanguageDemo$Messages", locale);
        LogRecord record = new LogRecord(Level.INFO, "order.created");
        record.setResourceBundle(bundle);
        record.setResourceBundleName(bundle.getBaseBundleName());
        record.setParameters(new Object[] {orderId});
        LOG.log(record);
    }

    public static class Messages_en extends ListResourceBundle {
        @Override
        protected Object[][] getContents() {
            return new Object[][] {
                    {"order.created", "Order {0} was created successfully"}
            };
        }
    }

    public static class Messages_vi extends ListResourceBundle {
        @Override
        protected Object[][] getContents() {
            return new Object[][] {
                    {"order.created", "Đơn hàng {0} đã được tạo thành công"}
            };
        }
    }
}
~~~

Compile targeting Java 17, specifying encoding so Vietnamese characters in the source are read properly:

~~~bash
javac --release 17 -encoding UTF-8 LogMessageLanguageDemo.java
java LogMessageLanguageDemo
~~~

**stdout verified by running the program** (two lines):

~~~text
event=order.created lang=en message=Order ORD-42 was created successfully
event=order.created lang=vi message=Đơn hàng ORD-42 đã được tạo thành công
~~~

### 7.1. Key Takeaways

**Same event key.** Both records have the same **record.getMessage() == "order.created"** and the same INFO severity. This identifier does not change regardless of which language the reader prefers.

**Bundle selected explicitly.** The **emit(locale, orderId)** method calls **ResourceBundle.getBundle** with the passed-in locale; the program does not mutate the JVM's default Locale. This is crucial when multiple requests have different language contexts.

**ResourceBundle attached per LogRecord.** **setResourceBundle(bundle)** tells the Formatter where to look up the translation. **setResourceBundleName(...)** provides the catalog name and corresponding metadata; attaching the bundle directly makes the example self-contained and easy to control.

**Formatter preserves both key and translated text.** **record.getMessage()** is used as the event; **formatMessage(record)** retrieves the translated sentence and substitutes parameters. If you drop the event key, the log collection system is left with language-dependent strings and becomes fragmented.

**StreamHandler requires flush.** StreamHandler can buffer output, so the example calls **handler.flush()** before finishing, ensuring both lines appear on stdout in the expected order. **setUseParentHandlers(false)** prevents duplicate records from parent Logger handlers, which may use stderr or a different format.

**Single Java file.** The base bundle name contains **$** because Messages_en and Messages_vi are **nested public static classes** inside LogMessageLanguageDemo. This is a convenience so the exercise needs only one source file. In real projects, separate properties files or catalogs are usually easier to maintain.

### 7.2. Output Chosen by Environment and Policy

The example prints both languages to prove i18n works; production usually does not need to **duplicate every event into two lines**. Choose one of the designed policies: one standard language, messages per specific locale, or storing keys/attributes and translating at display time.

The custom Formatter in the example only demonstrates the mechanism. It assumes the record has a bundle; a production formatter must safely handle records without a bundle, missing key errors, and malformed inputs. Use a reliable encoder/formatter to ensure proper encoding, escaping, metadata, and exceptions.

## 8. Managing Translations with Properties Files in Real Projects

If you want to separate code and translations, you can place the following files **on the classpath**:

**messages_en.properties**

~~~properties
order.created=Order {0} was created successfully
order.rejected=Order {0} was rejected
~~~

**messages_vi.properties**

~~~properties
order.created=Đơn hàng {0} đã được tạo thành công
order.rejected=Đơn hàng {0} đã bị từ chối
~~~

In code, call:

~~~java
ResourceBundle en = ResourceBundle.getBundle("messages", Locale.ENGLISH);
ResourceBundle vi = ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi"));
~~~

These snippets assume both properties files are properly packaged on the classpath. If you want explicit fallback support when a translation is missing, you should usually include **messages.properties** as the root bundle with default content. Test fallback logic and missing keys in your actual application environment.

**Encoding note:** For **ResourceBundle backed by PropertyResourceBundle on JDK 9+**, the default properties-file reading mechanism supports UTF-8 per JDK rules (with ISO-8859-1 fallback in applicable cases). This **differs** from some legacy Properties APIs—for example, **Properties.load(InputStream)** still decodes as ISO-8859-1. Do not assume every API reading `.properties` files handles Vietnamese the same way. Keep files in UTF-8, test accented characters during build and runtime, and when reading with a **Reader**, specify the charset explicitly.

**Translation is not just word replacement.** A Vietnamese sentence may reorder parameters compared to English. Use keys and numbered placeholders so each locale can order words grammatically.

Example:

~~~text
en: Customer {0} requested product {1}
vi: Khách hàng {0} yêu cầu sản phẩm {1}
~~~

If another language needs to swap subject and object, the template can place **{1}** before **{0}** without changing the argument order in code. Keys and parameter lists must have a clear contract so translators do not mix up values.

## 9. Placeholders and Locale-Aware Formatting

### 9.1. JUL Uses MessageFormat for Message Parameters

In the example, the template uses **{0}**:

~~~text
order.created = Order {0} was created successfully
~~~

JUL's Formatter provides **formatMessage(LogRecord)**: it looks up the record's bundle and applies the appropriate parameter formatting for the message. Parameter values are passed via **LogRecord.setParameters(...)** or corresponding logging overloads.

Keep in mind:

- **{0}**, **{1}** are **java.text.MessageFormat** placeholders.
- **{0,number}**, **{0,date}** apply formatted rules and are affected by the locale at formatting time.
- The **apostrophe (')** acts as a quote character in MessageFormat patterns; when you need a literal apostrophe, you generally must use **two consecutive apostrophes ('')**.
- Literal curly braces must be properly escaped/quoted according to MessageFormat rules.
- Never use untrusted data directly as a **pattern**; keep patterns managed by the application/catalog.
- Test templates with String, Number, Date, null, and Unicode parameters to avoid surprises.

**An important subtlety:** **The ResourceBundle Locale used to select a translation does not mean all number/date formatting automatically uses that locale.** With JUL's standard mechanism, Formatter.formatMessage uses MessageFormat according to the JDK implementation; number/date formatting may rely on the **default FORMAT locale** rather than the locale of the bundle you passed. If a message must format currency, dates/times, or numbers in a specific locale, explicitly use **MessageFormat(pattern, locale)** or a formatter with a clear contract, and test the output.

In logs meant for machine analysis, it is usually better to record timestamps, counts, durations, and currencies in **fields with explicit types/units**, avoiding dependence on a particular language's decimal/grouping separators.

### 9.2. Do Not Confuse JUL Syntax with SLF4J

Parameterization syntax is not uniform across frameworks:

| Mechanism | Template example | Note |
| --- | --- | --- |
| **JUL + MessageFormat** | Order {0} created | Parameter indices start at 0 |
| **SLF4J** | Order {} created | Positional placeholder, does not translate messages |
| **String.format** | Order %s created | printf syntax; locale may affect formatting |
| **MessageFormat(pattern, locale)** | Total: {0,number} | Locale is explicitly passed to the formatter |

Illustration using **SLF4J** (requires SLF4J library and a compatible provider; cannot run with JDK alone):

~~~java
logger.info("Order {} created", orderId);
~~~

This is **parameterized logging**, not automatically **localized logging**. If you want translations in an SLF4J/Logback/Log4j 2 setup, decide where translations are looked up and use the appropriate formatter/encoder for that stack. Do not copy a MessageFormat **{0}** pattern directly into a **{}** API and expect identical behavior.

## 10. Structured Messages Enable Language Independence

When messages vary by locale, the best way to avoid depending on prose is to use **structured logging**, or at least stable event codes and attributes.

Example of two records:

~~~json
{
  "level": "INFO",
  "event": "order.created",
  "language": "en",
  "message": "Order ORD-42 was created successfully",
  "order_id": "ORD-42"
}
~~~

~~~json
{
  "level": "INFO",
  "event": "order.created",
  "language": "vi",
  "message": "Đơn hàng ORD-42 đã được tạo thành công",
  "order_id": "ORD-42"
}
~~~

Both records can be grouped by **event = order.created**. If a system only has a message field without an event code, queries must search for both sentences or rely on brittle text-based rules.

In production, the event code is often sufficient for querying and aggregation. A specific English/Vietnamese message can be generated when an operator opens the detailed log.

**Suggested schema:**

- **event**: stable code such as order.created, order.rejected, inventory.timeout.
- **message**: human-readable sentence, which may be translated.
- **message_key**: if a translation key distinct from the event code is needed.
- **language** or **locale**: only when the application actually emits multilingual messages and needs to distinguish translations.
- **service, environment, version**: where the event originated.
- **request_id, trace_id, span_id**: correlation attributes if corresponding instrumentation exists.
- **error.type, reason_code**: standardized values for searching.

Name fields consistently according to your system's schema. Do not invent field names by translating them into Vietnamese or using different enum names across languages.

### 10.1. Why Should You Not Parse Messages to Extract Data?

Suppose a system uses regex to extract orderId from:

~~~text
Order ORD-42 was created successfully
~~~

When translated to:

~~~text
Đơn hàng ORD-42 đã được tạo thành công
~~~

The regex may fail to match. If the message changes punctuation or word order, the regex breaks again. **order_id = ORD-42** is a stable attribute independent of translation. This is also why event codes should be attached when alerting and building dashboards.

## 11. Unicode, Vietnamese Diacritics, and End-to-End Encoding

Multilingual messages are only useful if Unicode characters are preserved from emission to viewing. Common failures include Vietnamese characters turning into **????**, garbled characters like **Ã** due to misdecoding, characters lost when writing files, or multiline logs being split improperly.

Pipeline to verify:

~~~text
Java source / ResourceBundle (Unicode)
       |
       v
Java String / LogRecord
       |
       v
Formatter / Encoder
       |
       v
Console / file (charset)
       |
       v
Log agent / collector / transport
       |
       v
Storage / search UI
~~~

A few notes:

1. **Java String is Unicode** at the data-model level; this does not guarantee the console, file, or log collector is encoding/decoding correctly.
2. Use **UTF-8** consistently for source/catalogs and configure encoders/sinks when charset options exist.
3. When compiling Java source containing Vietnamese across operating systems, specify **javac -encoding UTF-8**, as in the practical example.
4. Do not conclude text is corrupted in the application solely because the console displays it incorrectly; the issue may be the terminal, font, output charset, or collector. Inspect each layer.
5. During search, an accented character can be represented by multiple equivalent Unicode sequences (e.g., composed vs. decomposed forms). Consider **Unicode normalization** in the search pipeline if your system requires it; do not automatically alter unauthorized business content or IDs.
6. A text record must sanitize newlines/control characters from inputs to prevent **log injection**. A JSON encoder must escape properly rather than concatenating strings manually and calling it JSON.
7. **Do not normalize or encode secrets or personal information into logs just to make debugging easier.** Control allowed data before constructing messages.

## 12. Locale in Multithreaded and Multi-Service Applications

In a server application, each request may carry a different locale. If you change **Locale.setDefault(...)** per request, that mutates JVM-wide state and can concurrently affect formatting in other requests.

Safer options are:

1. Decide the **log language policy** at the application/service level, usually one unified language.
2. If an event needs a specific translation, pass **Locale** to the function selecting the ResourceBundle or rendering the message instead of changing the default Locale.
3. When working with **ExecutorService, CompletableFuture, virtual threads**, or async pipelines, pass required context explicitly or use a context-propagation mechanism with a clear contract.
4. Avoid storing a user's Locale in a ThreadLocal without cleaning it up; thread pools can reuse threads and accidentally carry over the previous request's locale.
5. Preserve **event keys and structured attributes** across services. Service A using Vietnamese and Service B using English must still share matching event codes/traceIds if distributed tracing is used.

**Do not use Accept-Language or user locale to decide the language of all backend logs** if operations expects a single language. Accept-Language is useful for user-facing responses; diagnostic logs may follow a different policy.

### 12.1. Propagating Locale Is Not Propagating Trace Context

Locale selects a translation. **requestId, traceId, spanId** correlate events. The two kinds of context serve different purposes; never use locale as an ID or build correlation IDs from translated sentences.

When dispatching a task to another thread, the system should clearly determine:
- Is the user's locale actually needed in this task?
- Are the event code and request/trace context propagated properly?
- Is the message rendered at event-creation time or when processed by an async appender?
- If the locale changes after the record is created, will the backend still render consistently?

Defining **when translation is selected** helps prevent logs from the same request from unexpectedly appearing in multiple languages.

## 13. Exception Messages, Stack Traces, and Language

A Java exception has **getMessage()** and **getLocalizedMessage()**. However, do not assume every exception has a translation: by default, many exceptions return the same content for both methods; libraries may choose their own behavior.

When logging errors, prioritize:
- **Stable error type** (class name/error code).
- **Useful context** (operation, dependency, requestId).
- **Throwable/stack trace** when needed for investigation and permitted by data policy.
- **Standardized message** for operators.
- **User-facing message** translated separately, never displaying raw technical exceptions directly.

Illustrative JUL logging example:

~~~java
// Illustration inside a method where the logger variable and error exception already exist.
logger.log(Level.WARNING, "event=inventory.lookup_failed", error);
~~~

This overload keeps the Throwable in the LogRecord so the Handler/Formatter can render the stack trace as configured. This is not a standalone program; it requires the **logger** variable, **error**, and JUL imports in an appropriate context.

**Do not translate class/method names in stack traces.** Those identifiers must reflect the actual code for source lookup, version identification, and investigation.

**Watch out for sensitive data:** library exception messages may contain URLs, queries, tokens, payloads, or user data. Translating a sentence does not automatically make it safe to log.

## 14. Fallbacks, Translation Versioning, and Consistency

An i18n system needs a plan for missing translations:

- **Missing locale:** fall back to the root bundle or standard language per policy.
- **Missing key:** never let an entire business flow fail just because of a log message; test catalogs and handle errors appropriately in the logging layer.
- **Missing parameter:** avoid templates displaying literal "{1}" or placing values in the wrong positions.
- **Wording updates:** phrasing may change, but event codes and schemas should remain stable if the semantics have not changed.
- **Meaning changes:** if "order.created" previously meant a draft order and now means a paid order, that is a semantic contract change; consider a new event key rather than just changing the translation.
- **Multi-version deployments:** older and newer services may have different wording. Query by event code, service version, and stable attributes.

**ResourceBundle fallback** has its own rules: following candidate locales, the root bundle, and in some lookup paths the JVM default locale. Do not assume an untranslated locale will always fall back to English without configuring the catalog and testing it. A root catalog such as **messages.properties** and tests per language tag help catch these cases early.

Organizations should have checks verifying that:
- Every critical key has the required translations.
- Placeholder counts and parameter types are consistent.
- Translations do not accidentally alter the meaning of an error/event.
- New wording does not break dashboards, alerts, or parsers.
- Translation files are packaged properly and display Unicode accurately.

## 15. Relationship Between Message Language and SLF4J/Logback/Log4j 2

In the Java ecosystem, logging APIs and backends can differ from JUL:

**SLF4J** is a facade: a call like **logger.info("Order {} created", id)** is parameterized. By default, it does not look up a ResourceBundle or translate content by locale. For i18n, the application/configuration must design a step to select the message template, then use the appropriate API to log or preserve event/attributes.

**Logback/Log4j 2** provide encoders/layouts/filters/appenders or similar mechanisms; they can emit JSON/structured fields. When using such backends, leverage structured logging instead of forcing every translation into a single message string and parsing it back out.

A flow can look like:

~~~text
Business code: eventKey + structured attributes
                    |
                    v
      Logging facade/provider/backend
                    |
         +----------+------------+
         |                       |
         v                       v
  Canonical event fields   Human-readable message
         |                (by policy/locale)
         +-----------+-----------+
                     |
                     v
               Encoder / sink
                     |
                     v
              Log storage/search
~~~

**Do not confuse the two concepts:** *parameterization* is inserting values into a template to form a sentence; *localization* is choosing the template appropriate for a language. A system can be parameterized without being localized at all. A system can also be localized while keeping canonical event codes.

When switching backends, do not assume JUL's formatMessage method or `{0}` syntax will automatically behave the same way in SLF4J. Check the actual API, dependencies/providers, and formatter contract.

## 16. Testing Message Quality and Translations

Valuable test cases include:

| Case | Expected outcome |
| --- | --- |
| Same eventKey with en and vi locales | Event key, level, and IDs are identical; message is translated properly |
| Message with parameters | Values land in the right placeholders without loss or misordering |
| Missing a locale | Falls back per policy, verified by tests |
| Missing message key | Handled gracefully; missing translation caught in QA |
| Vietnamese diacritics present | UTF-8 preserved through formatter and sink |
| Quotes and curly braces present | MessageFormat escaping works properly |
| Newlines or control characters in input | Does not corrupt log structure or forge fake records |
| Concurrent requests with different locales | No locale leakage between requests |
| English or Vietnamese wording updated | Dashboards still query by event code and fields |
| Exception containing sensitive content | Log drops/redacts data per policy |

**End-to-end testing** when using centralized collection: do not only check Java Strings in unit tests. Verify that Vietnamese messages passing through console/file, agent, transport, and search UI do not suffer encoding corruption; queries based on event codes must still find all events.

**stdout note:** The Java program in Section 7 uses a Handler writing to stdout and flushing; this produces deterministic output for the exercise. A default JUL ConsoleHandler normally writes to stderr with a different format. When switching the example to ConsoleHandler, expect different output due to configuration rather than assuming a translation bug.

## 17. Common Mistakes

### Mistake 1 — Translating the Event Code Too

**Wrong:** In the vi locale, changing the event from order.created to donhang.datao.  
**Consequence:** Dashboards, alerts, and cross-service queries no longer share a common key.  
**Right:** Keep **order.created** fixed; translate the **message** field.

### Mistake 2 — Using the Log Sentence as a Classification Key

**Wrong:** A rule "contains Order was created" to count successes.  
**Consequence:** When translated or reworded, metrics become wrong.  
**Right:** Use **event**, **status**, and structured attributes.

### Mistake 3 — Assuming SLF4J {} Translates Automatically

**Wrong:** Replacing "Order {} created" with a key and expecting the provider to find Vietnamese automatically.  
**Right:** SLF4J parameterization and ResourceBundle localization are two separate things; explicit configuration or template-lookup code is required.

### Mistake 4 — Changing the Default Locale per Request

**Wrong:** Every HTTP request calls Locale.setDefault(userLocale).  
**Consequence:** Concurrent requests can interfere with each other.  
**Right:** Pass Locale to translation logic or use a catalog selected within a controlled scope.

### Mistake 5 — Believing ResourceBundle Locale Controls Numbers/Dates

**Wrong:** Seeing a vi bundle and concluding date/number placeholders are guaranteed to use vi-VN formatting.  
**Right:** Check the formatter and Locale used to format those data types; pass an explicit locale if needed.

### Mistake 6 — Forgetting UTF-8 at One Link in the Chain

**Wrong:** Vietnamese source is correct, but output after the collector turns into garbled text; assuming ResourceBundle is missing a key.  
**Right:** Check encoding across source, resource files, build, handler, terminal, transport, and storage.

### Mistake 7 — Using User Messages Instead of Technical Logs

**Wrong:** Server only logs "Không thể thanh toán" with no error code, requestId, or dependency.  
**Right:** Friendly user messages are translated separately; technical logs retain the event, outcome, and useful context.

### Mistake 8 — Translating Exception/Class Names and Hiding the Cause

**Wrong:** Saving only a translated sentence and discarding exception type and cause information.  
**Right:** Keep error codes, exception types, context, and stack traces when needed and permitted by policy.

### Mistake 9 — Emitting Multiple Translations per Event by Default

**Wrong:** Every request logs both English and Vietnamese versions to production logs simultaneously.  
**Consequence:** Volume increases, double-counting is easy, and ordering/correlation become confusing.  
**Right:** Choose a clear policy, optionally storing keys and rendering translations at view time.

### Mistake 10 — Feeding Untrusted Content into Templates

**Wrong:** Using raw input as a MessageFormat pattern or concatenating user newlines into text logs.  
**Right:** Templates are managed by the application; variable data belongs only in validated and escaped parameters/fields.

## 18. Exercises and Self-Assessment Questions

**Exercise A — Add a third language.** In the Java program, add a **Messages_fr** catalog or another bundle and call **emit(Locale.forLanguageTag("fr"), "ORD-42")**. Verify the event key **order.created** still matches the previous two lines. This exercise requires you to supply an appropriate translation yourself rather than inferring translations from the event code.

**Exercise B — Check missing keys.** Add an **order.rejected** event without a translation in one bundle. Observe how ResourceBundle/JUL handles it, then design a catalog check to detect missing keys at build/test time.

**Exercise C — Choose a policy.** A system has three services logging together: one in Vietnam, one in Singapore, and one in the US. Propose an operational language, event code standard, field names, locale handling, and a way to localize user-facing messages while still querying by a single event.

**Exercise D — Number/date parameters.** Create a template containing {0,number} and test formatting in en-US/vi-VN using MessageFormat with an explicit Locale. Compare with JUL's default formatMessage(record) to understand the scope of the bundle locale.

**Exercise E — Create a structured event.** From the Vietnamese sentence "Đơn hàng ORD-42 đã được tạo thành công", split it into **event**, **order_id**, **level**, **message**, and **language** fields. Demonstrate that a query by event still works when the language changes.

### Review Questions

**1. Should the event code order.created be translated into a Vietnamese code?**  
No. The event code is a stable technical contract; translate the message and keep the code.

**2. Why might an English message appear even when a request sends locale vi-VN?**  
Because logs may use a standard language, ResourceBundle has fallbacks, the app did not pass the locale, or the Formatter/backend does not perform localization as expected. Check the actual code and configuration.

**3. Which components does JUL use to support message translation?**  
ResourceBundle holds templates; LogRecord holds the message key/parameters/bundle; Formatter.formatMessage can look up translations and format parameters.

**4. Does a translation that swaps the order of {0} and {1} require changing the logging code?**  
No, as long as the parameter contract stays the same and the template places placeholders in the right positions.

**5. Why is changing Locale.setDefault per request dangerous?**  
It is JVM-wide shared state that can affect other requests and concurrent formatting operations.

**6. Why can't alerting rely solely on message text?**  
Content can change when translations, wording, or formatting change. Use stable event IDs, levels, and fields.

**7. Where should you check if Vietnamese messages have corrupted diacritics?**  
Check in order: source/catalog files, charset at compile/read time, formatter/handler, terminal, collector, storage, and search UI.

## 19. Conclusion

**The language of a log message is a decision about audience and operations**, not an attribute that changes the nature of an event. Java supports localization through **Locale**, **ResourceBundle**, and JUL's formatting mechanism, but translation must be designed alongside **event keys**, **schemas**, **parameters**, **encoding**, and **locale policies**.

The Java 17 exercise shows that the same **order.created** event can emit an English or Vietnamese sentence while the event code and order identifier remain unchanged. A maintainable logging architecture keeps technical data stable, chooses message languages intentionally, and always tests missing translations, Unicode, and end-to-end delivery to the observability destination.
