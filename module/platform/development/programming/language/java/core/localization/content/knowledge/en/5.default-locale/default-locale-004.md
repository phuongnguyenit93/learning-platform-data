# Why Not Change the Default Locale per User?

## 1. The Problem: One JVM Serving Multiple Users

Suppose a Java application concurrently serves:

- User A who chooses Vietnamese, locale `vi-VN`.
- User B who chooses English (United States), locale `en-US`.
- User C who chooses French, locale `fr-FR`.

A tempting but wrong approach is for the server, whenever it receives a request from A, B, or C, to call `Locale.setDefault(requestLocale)` and then continue processing with APIs that use `Locale.getDefault()`. **The default locale is shared default state within the JVM, not a private attribute of each request, thread, or user.** When B changes it, A's *subsequent* operations that read the default may also see B's locale.

Rule to remember: **the user/request locale must be determined and passed explicitly through the processing flow**, while the JVM default locale should only serve as a process-level default (for example, a single-language application or an initial choice when no preference exists).

After this lesson, you will be able to explain the scope of `getDefault/setDefault`, identify race condition bugs in multi-request applications, handle the `DISPLAY`/`FORMAT` categories properly, design methods that take an explicit `Locale`, and write tests without leaking global state.

## 2. What Scope Do `Locale.getDefault()` and `Locale.setDefault()` Affect?

`java.util.Locale` provides these APIs:

| API | Meaning |
| --- | --- |
| `Locale.getDefault()` | Returns the JVM's general default locale (base default locale) |
| `Locale.setDefault(Locale)` | Changes the general default; also sets the defaults for the `DISPLAY` and `FORMAT` categories |
| `Locale.getDefault(Locale.Category.FORMAT)` | Returns the category default used for formatting (numbers, dates/times, currencies in category-aware APIs) |
| `Locale.getDefault(Locale.Category.DISPLAY)` | Returns the category default for displaying language/region names |
| `Locale.setDefault(Locale.Category, Locale)` | Changes the corresponding category default at the JVM level; does **not** create a per-thread locale |

Initial default values are typically established based on operating system configuration and Java environment/startup properties; they can be changed while the program runs. Therefore, `Locale.getDefault()` is not an immutable constant over the JVM's lifetime.

What calling `setDefault` does **not** do:

- Does not bind the locale to `Thread.currentThread()` or the current request.
- Does not guarantee that previously created formatters/resources automatically switch to the new default; some APIs read the default at object creation time and may cache data.
- Does not affect only the currently logged-in user.
- Does not become safe merely because a servlet request is handled on a separate thread.
- Does not change the default time zone: `Locale` and `TimeZone`/`ZoneId` are separate concepts.

A system may run multiple JVMs/processes, each with its own default. Inside **the same JVM**, all threads share this state, even if requests are processed by different thread pools.

## 3. Race Condition: What Happens When Two Requests Run Concurrently?

Consider this sequence:

1. Request A (Vietnamese user) calls `Locale.setDefault(vi-VN)`.
2. A pauses before the data-formatting step.
3. Request B calls `Locale.setDefault(en-US)`.
4. A resumes and calls `Locale.getDefault()` or creates a formatter using the default. A may receive `en-US`, contrary to its `vi-VN` preference.
5. If A sets the default again, other operations of B or C may also be affected.

`Locale.setDefault` mutates global state; even if individual reads/writes of the default have API-level synchronization, **the multi-step sequence “set locale → do work → restore” does not become a private transaction for a request**. Holding a lock around one block of code still does not control all other libraries and threads reading the default in the JVM.

### Java 17+ Example with Deterministic Execution Order

File `DefaultLocaleRaceDemo.java`:

```java
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class DefaultLocaleRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        Locale previous = Locale.getDefault();
        CountDownLatch aliceHasSet = new CountDownLatch(1);
        CountDownLatch bobHasSet = new CountDownLatch(1);
        AtomicReference<String> aliceObserved = new AtomicReference<>();
        AtomicReference<String> bobObserved = new AtomicReference<>();

        Thread alice = new Thread(() -> {
            Locale.setDefault(Locale.forLanguageTag("vi-VN"));
            aliceHasSet.countDown();
            try {
                bobHasSet.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            aliceObserved.set(Locale.getDefault().toLanguageTag());
        });

        Thread bob = new Thread(() -> {
            try {
                aliceHasSet.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            Locale.setDefault(Locale.US);
            bobObserved.set(Locale.getDefault().toLanguageTag());
            bobHasSet.countDown();
        });

        try {
            alice.start();
            bob.start();
            alice.join();
            bob.join();

            System.out.println("Alice expects: vi-VN");
            System.out.println("Alice sees: " + aliceObserved.get());
            System.out.println("Bob expects: en-US");
            System.out.println("Bob sees: " + bobObserved.get());
        } finally {
            // Only so the experiment does not leave the default altered.
            Locale.setDefault(previous);
        }
    }
}
```

Run with JDK 17 or higher:

```bash
javac DefaultLocaleRaceDemo.java
java DefaultLocaleRaceDemo
```

Output:

```text
Alice expects: vi-VN
Alice sees: en-US
Bob expects: en-US
Bob sees: en-US
```

The two `CountDownLatch` instances force Bob to change the default **after** Alice sets `vi-VN` and **before** Alice reads it. `AtomicReference` merely stores each thread's result so `main` prints them in a consistent order. The example intentionally uses `setDefault` to expose the bug; it is **not** a recommended coding pattern in servers. The `finally` block only cleans up the environment for the experiment after waiting for both threads to finish; adding `finally` to a production request handler **does not eliminate races** between requests.

## 4. Real-World Bugs Caused by Changing Defaults per Request

| Situation | Possible Mismatch |
| --- | --- |
| `NumberFormat.getNumberInstance()` without passing a locale | Decimal/grouping separators depend on the default locale at the moment the formatter is obtained |
| `DateFormat.getDateInstance()` without passing a locale | Month names and date formatting may change with the default |
| `DateTimeFormatter` using a pattern with month names without configuring an appropriate locale | Month/day name strings may not match the user's language |
| `ResourceBundle.getBundle(baseName)` without passing a locale | May pick a bundle from a default that differs from the request language |
| Internal library calling `Locale.getDefault()` | The in-flight request may use another request's preference |
| Logs/audits recording formatted data using a shifting default | Hard to reproduce or compare data across runs |
| Running a test that changes the default without restoring it | Subsequent tests depend on execution order and fail intermittently |

**Not all locale-sensitive APIs read the default at the same time.** One formatter may capture the locale when created; another may consult the default at call time. Therefore, the right fix must rely on passing configuration data explicitly, rather than guessing when the runtime reads the default.

Moreover, mishandling locales also breaks functionality: parsing `"1,234"` can be interpreted differently across conventions; displaying dates as `01/02/2026` causes day/month confusion; case matching/conversion requires explicit linguistic rules. These issues require the right APIs and policies, not repeatedly mutating the JVM default.

## 5. The Right Approach: Pass the User's `Locale` Explicitly

The key pattern is **resolve the locale once per request → pass the locale to formatting, translation, and response functions**:

```text
HTTP request / user profile / accepted language preference
                       |
                       v
          Validate + select supported Locale
                       |
                       v
            Request context / method parameter
                       |
             +---------+---------+
             |         |         |
             v         v         v
        NumberFormat  DateTime   ResourceBundle
                      Formatter
             \         |         /
              \        |        /
               v       v       v
              Return user-specific result
```

Preference sources may include account settings, an allowed query parameter, a session cookie, or the HTTP `Accept-Language` header. Even if the user sends a string like `vi-VN`, the application must still validate syntax, constrain to the supported locale set, and apply policy-based fallback. The full `Accept-Language` header containing tags/weights (`q`) is **not a single language tag**.

### Java 17+ Example: Formatting per Request Without Calling `setDefault`

File `ExplicitLocaleDemo.java`:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class ExplicitLocaleDemo {
    static String renderNumber(double value, Locale requestLocale) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(requestLocale);
        formatter.setGroupingUsed(false); // Keep output simple.
        return requestLocale.toLanguageTag()
                + ": " + formatter.format(value);
    }

    public static void main(String[] args) {
        Locale alice = Locale.forLanguageTag("vi-VN");
        Locale bob = Locale.forLanguageTag("en-US");

        System.out.println(renderNumber(1234.5, alice));
        System.out.println(renderNumber(1234.5, bob));
    }
}
```

```bash
javac ExplicitLocaleDemo.java
java ExplicitLocaleDemo
```

Output with standard JDK locale data:

```text
vi-VN: 1234,5
en-US: 1234.5
```

The core point is that both formatting operations receive **their own `Locale` object** and do not modify the JVM default. Using `setGroupingUsed(false)` only disables thousands grouping so the example focuses on the decimal separator. Visual presentation can still be influenced by the Java environment's locale provider/data; use APIs to format by locale instead of manually synthesizing separators by replacing characters in strings.

### APIs That Commonly Have Overloads Accepting a Locale

```java
// Illustrative snippets inside a method where requestLocale already exists.
NumberFormat numberFormatter =
        NumberFormat.getNumberInstance(requestLocale);

NumberFormat currencyFormatter =
        NumberFormat.getCurrencyInstance(requestLocale);

java.text.DateFormat dateFormatter =
        java.text.DateFormat.getDateInstance(
                java.text.DateFormat.MEDIUM, requestLocale);

java.time.format.DateTimeFormatter dateTimeFormatter =
        java.time.format.DateTimeFormatter
                .ofLocalizedDate(java.time.format.FormatStyle.MEDIUM)
                .withLocale(requestLocale);

java.util.ResourceBundle bundle =
        java.util.ResourceBundle.getBundle("messages", requestLocale);
```

This is an **illustrative code snippet**, not a self-compiling Java file: `requestLocale` must be declared and available in scope, and `messages` must have the corresponding resource bundles on the classpath.

With `ResourceBundle`, passing a locale helps select candidate bundles according to the request; if no matching resource exists, the default fallback mechanism may still consider the default locale. If you need an immutable, tightly controlled fallback completely isolated from the JVM default, design an explicit bundle lookup policy (for example `ResourceBundle.Control` in supported environments or application-managed fallback) and supply valid bundles. Passing a `Locale` is a necessary step, though it does not by itself guarantee every translated string exists.

## 6. Do `Locale.Category.FORMAT` and `DISPLAY` Solve the Problem?

Java allows two specialized default groups:

- `Locale.Category.FORMAT`: for locale-dependent formatting operations.
- `Locale.Category.DISPLAY`: for display names of languages, countries, and related objects.

Example:

```java
Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE);
```

This call **still modifies the shared default of the FORMAT category in the JVM**. It does not create "user A's FORMAT locale". Another request can overwrite this category; newly created formatters that pick the category default can be affected. `Locale.setDefault(Locale)` also changes both category defaults.

### Java 17+ Illustration of Category Scope

File `LocaleCategoryDemo.java`:

```java
import java.util.Locale;

public class LocaleCategoryDemo {
    public static void main(String[] args) {
        Locale beforeBase = Locale.getDefault();
        Locale beforeFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        Locale beforeDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);

        try {
            Locale.setDefault(Locale.US);
            Locale.setDefault(
                    Locale.Category.FORMAT, Locale.FRANCE);

            System.out.println(Locale.getDefault().toLanguageTag());
            System.out.println(
                    Locale.getDefault(Locale.Category.FORMAT)
                            .toLanguageTag());
            System.out.println(
                    Locale.getDefault(Locale.Category.DISPLAY)
                            .toLanguageTag());
        } finally {
            Locale.setDefault(beforeBase);
            Locale.setDefault(
                    Locale.Category.FORMAT, beforeFormat);
            Locale.setDefault(
                    Locale.Category.DISPLAY, beforeDisplay);
        }
    }
}
```

```bash
javac LocaleCategoryDemo.java
java LocaleCategoryDemo
```

Output:

```text
en-US
fr-FR
en-US
```

That means at this point the base default is `en-US`, the format default is `fr-FR`, and the display default is `en-US`. Setting different values **does not** create per-user isolation. Only change categories during process initialization or in controlled tests; do not call them per request.

## 7. Do Not Confuse Locale with Thread Context or Time Zone

The default `Locale` is **different** from other contexts in an application:

- `ThreadLocal<Locale>` only attaches a value to a particular thread, but **does not change `Locale.getDefault()`** and APIs do not automatically switch to reading that `ThreadLocal`.
- A server using a thread pool may reuse the same thread for multiple requests; if using `ThreadLocal` as a request context, you must manage its lifecycle and call `remove()` in `finally` or use the framework's context mechanism. With asynchronous processing/thread switching, the context is not automatically carried over either.
- A web framework may provide its own `LocaleResolver` or context mechanism; that is the framework's locale management layer, not calling `Locale.setDefault` for the JVM.
- `ZoneId`/`TimeZone` represent time zones. Users sharing the `en-US` locale can still live in different time zones; a `vi-VN` user may also live abroad. Do not infer the time zone from the locale and do not call `TimeZone.setDefault` per request.

In ordinary Java code, the clearest and most testable approach is to pass `Locale` directly via parameters or hold it in a **per-request immutable** context object, then supply it to locale-aware APIs. Only use `ThreadLocal` when there is a well-defined scope management mechanism properly read by every relevant component.

## 8. Rules for Selecting a Request's Locale

A typical workflow:

1. **Read the preference** from the user profile or request. If the source is untrusted, do not assume the string is valid.
2. **Parse the syntax**: for a single BCP 47 tag, use `Locale.Builder.setLanguageTag(...)` to catch malformed input; for a full `Accept-Language` header, use a parser for language range lists such as `Locale.LanguageRange.parse(...)`, handling priority/weight rules.
3. **Match against the supported list** of the application: a syntactically valid locale may still lack translation resources.
4. **Apply intentional fallback**: for example `vi-VN` if no preference is set or the requested locale is unsupported. You can prioritize language matching before falling back, depending on business rules.
5. **Pass an explicit `Locale`** into services, formatters, resource lookups, and response rendering. Never call `setDefault` while handling requests.
6. **Label/observe cleanly**: when debugging, log `requestLocale.toLanguageTag()` instead of inferring the user from `Locale.getDefault()`.

To avoid confusion, the **response locale** and the **content translation language** may need an alignment policy. For example, if a request chooses `fr-CA` while the application only has `fr` translations and formatters supporting `fr-CA`, you might use `fr-CA` for numbers/dates and `fr` for text resources; that rule must be designed explicitly.

## 9. Testing: When Can `setDefault` Be Used?

Some tests need to prove that code does not depend on the CI runner's machine default. In an **isolated single-threaded test**, you can save the initial default, temporarily change it, run assertions, and restore it in `finally`. If tests run in parallel within the same JVM, changing the default still affects other tests; the cleanest isolation is to **pass `Locale` directly** or run global-default experiments in a separate JVM.

Examples of good testing practices:

- Check that `renderNumber(value, Locale.FRANCE)` produces the right localized form regardless of whatever default the JVM has.
- Instantiate renderers/services with explicit locales and invoke them concurrently with different locales; results must be independent of request order.
- For tests that must modify the global default, disable parallel execution for the affected tests—including library code that reads defaults—and restore all of base/`FORMAT`/`DISPLAY`. Do not assume merely having `finally` makes a test safe under a parallel test runner.

Do not put `Locale.setDefault` in a singleton constructor, request filter, or interceptor as a per-user language solution. A singleton holding a per-request `Locale` is also dangerous if a mutable field is overwritten by another request; prefer parameter passing or independent scoped objects.

## 10. Common Mistakes and Fixes

| Wrong Practice | Consequence | Right Practice |
| --- | --- | --- |
| `Locale.setDefault(userLocale)` in a request handler | Alters global value, causing request collisions | `NumberFormat.get...Instance(userLocale)` and overloads accepting `Locale` |
| Calling `setDefault` at request start and restoring at the end | Two requests can interleave during processing | Never mutate the default per request |
| Thinking `Locale.setDefault(Category.FORMAT, ...)` is per-thread | Categories are also shared state | Pass an explicit locale to formatters |
| Reading the default once and storing it in a static singleton as user preference | Freezes the wrong preference for users | Resolve the preference from each request's context |
| Using `ThreadLocal` without calling `remove` | Thread pool can retain the previous request's state | Manage scope and cleanup; prefer method parameters |
| Using `Locale.getDefault()` to infer the request's language | Reflects JVM configuration, not the user | Use the locale resolved from the request source |
| Treating `Locale` as a time zone | Displays wrong times | Pass `ZoneId` independently |
| Running tests that mutate defaults in parallel | Tests become flaky due to shared state | Test with explicit locales or isolate the JVM |

## 11. Self-Check

1. A JVM handles 100 concurrent requests. Does calling `Locale.setDefault(Locale.US)` in request A create a private locale for A? **No**, the default is shared across the JVM.
2. Does `Locale.setDefault(Locale.Category.DISPLAY, Locale.FRANCE)` affect only the current thread? **No**; the display category default is still JVM-wide.
3. Why is restoring the default in `try/finally` at the end of each request still insufficient? **Because another request can read/write the default between the time the current request sets it and restores it**.
4. How do you pass a locale when formatting numbers? **`NumberFormat.getNumberInstance(requestLocale)`**.
5. Does `ThreadLocal<Locale>` automatically make `Locale.getDefault()` change per thread? **No**. Code must actively read the context and pass it to APIs.
6. If a user has `vi-VN` but lives in a time zone outside Vietnam, should you infer the time zone from the locale? **No**; use a `ZoneId` from the appropriate configuration.

## References

- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `getDefault`, `setDefault`, `Category`, `forLanguageTag`, and related APIs.
- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): factories accepting a locale.
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): `withLocale` and localized formatters.
- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): locale lookup and fallback.
