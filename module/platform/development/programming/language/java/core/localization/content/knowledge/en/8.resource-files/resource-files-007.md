# Organizing Stable Keys and Context Comments for Translators

## Lesson objectives

In a multilingual Java application, a screen can display content from `.properties` resource files, typically via `ResourceBundle`. A **resource key** is the identifier linking application code to a translation; the **value** is the text the user sees. If keys change whenever wording changes, get reused with a different meaning, or lack context notes, translators can easily produce wrong sentences even when every individual word looks right.

After this lesson, you will be able to:

- Name keys by **meaning and usage location** so Java code, translations, and translation-management tools share a stable reference.
- Explain why wording tweaks should usually change only the **value**, while a change in **meaning** calls for a new key.
- Write context notes for translators: where the text appears, action, target object, tone, placeholders, length constraints, and examples.
- Understand Java `.properties` comment rules and their limitation: comments live in the source file and **do not become values accessible through `ResourceBundle`**.
- Manage keys across multiple locales, detect missing keys or placeholders, and prevent fallback from hiding missing translations.
- Apply these principles using a compilable and runnable Java 17+ example.

This lesson is about **designing and maintaining resource files**. It does not require building a new translation system or changing how `Locale` is selected.

## 1. Resource keys are a stable contract

Consider a line in `messages_vi.properties`:

```properties
checkout.action.pay=Thanh toán
```

Here:

- `checkout.action.pay` is the **key**: the identifier that source code uses to look up the resource.
- `Thanh toán` is the **value**: the Vietnamese text shown to the user.
- `checkout` describes the feature, `action` is the content kind, and `pay` is the action intent.

Java code:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "messages", Locale.forLanguageTag("vi-VN"));
String label = bundle.getString("checkout.action.pay");
```

This is an illustrative snippet inside a method; `java.util.ResourceBundle` and `java.util.Locale` are already imported. `messages_vi.properties` must sit at the classpath location referenced by the `messages` base name.

If the content team changes the UI label from "Thanh toán" to "Tiến hành thanh toán", **the key stays `checkout.action.pay`**; only the value changes. That keeps Java code, tests, missing-translation metrics, and translation tools from changing on every copy edit.

Conversely, if a button previously **paid immediately** and is changed to **save the order to pay later**, the action's meaning has changed: you should create a new key, such as `checkout.action.saveForLater`, and update the call site. Keeping the `pay` key for a "save" action misleads anyone reading the file, especially translators.

### What makes a key stable?

A good key describes a **relatively long-lived semantic role**, independent of any specific translated phrasing. It should:

1. Be clear enough to distinguish from other keys.
2. Be used consistently by code and across all locale resources.
3. Not require renaming when wording improves, yet **be replaced** when the underlying semantics change.
4. Avoid depending on screen order, line numbers, personal names, or a single locale's phrasing.
5. Have clear ownership: which team owns it and where it is used.

Keys are part of the **source code ↔ resources ↔ translation workflow** contract. Renaming a key is equivalent to renaming an entry point: you must audit call sites and every localization.

## 2. Structured naming conventions

`ResourceBundle` enforces no single key-naming convention. However, a project should define a convention and follow it consistently.

One common pattern:

```text
<feature>.<element-or-content-kind>.<semantic-intent>
```

Examples:

| Suggested key | Intent |
| --- | --- |
| `checkout.action.pay` | Label of the button that executes payment |
| `checkout.action.cancel` | Label of the button that cancels the checkout step |
| `checkout.summary.itemCount` | Item-count message in the order summary |
| `checkout.error.paymentDeclined` | Message when a transaction is declined |
| `account.error.sessionExpired` | Message when a login session expires |
| `profile.field.displayName.label` | Label of the display-name field |
| `profile.field.displayName.hint` | Helper text below the display-name field |
| `navigation.menu.orders` | Navigation item label leading to orders |

What matters is not the number of dots, but **stability, searchability, and accurate intent**. A team might choose `feature.component.purpose` or another convention. Do not force every key into three levels if doing so produces long, vague, or awkward names.

Keys should be easy to find with text search in the codebase, easy to group in translation tools, and clear about feature ownership.

### Comparing naming approaches

| Weak key | Problem | Better alternative |
| --- | --- | --- |
| `button1` | Position-dependent; unclear what the button does | `checkout.action.pay` |
| `label_12` | Arbitrary index carries no semantics | `profile.field.email.label` |
| `click_here` | Uses English copy as an identifier | `account.action.verifyEmail` |
| `error` | Too generic; different errors have different contexts | `checkout.error.paymentDeclined` |
| `hello_text_new_v2` | Encodes editing state; not durable | `home.welcome.greeting` |
| `confirm` used for every button | "Confirm" might mean confirming cancel, delete, or pay | Split keys by actual action |
| `checkout.title.2026` | Ties the key to a year when semantics do not depend on the year | `checkout.page.title` |

You can intentionally **share a key** when the same message genuinely has the same meaning and display contract. Yet two places both using "Open", "Save", or "Continue" in different contexts are not enough reason to share a key: translations depend on the target object, gender/person, verb form, button width, tone, or sentence position.

**Do not use the English string itself as the key just because the source language is English.** When copy changes, key names like `Pay now` quickly become misleading and awkward to manage in code.

## 3. One value can have multiple meanings — why do translators need context?

Consider the English string `"Open"`:

- In a file manager, it can mean **open a file**.
- In an order status, it can mean **open / not yet closed**.
- On a business-hours sign, it can mean **open for business**.

If translators receive only:

```properties
common.open=Open
```

they lack the information to pick the right wording. In particular, one English word can correspond to multiple translations depending on part of speech, number, gender, and grammar in other languages.

Split keys by meaning:

```properties
file.action.open=Open
order.status.open=Open
store.status.open=Open
```

The English values are identical, but their meanings differ. Other languages may require three distinct translations.

### What context is enough?

Every potentially ambiguous key should include details that actually affect the translation:

- **Where it appears:** screen, dialog, email, heading, aria-label, error banner, tooltip.
- **Function:** what happens when the user clicks it, or what state is being described.
- **Target object:** whether "Open" applies to a file, order, store, or account.
- **Tone:** friendly, formal, serious warning; avoid random tone shifts across screens.
- **Length and layout constraints:** tight button label vs. multi-sentence description; state character limits only when the UI truly enforces one.
- **Parameters:** what count `{0}` represents, whether `{1}` is a person's name or a timestamp; where units and formatting come from.
- **Example:** a sample sentence rendered with anonymized realistic data.
- **What must stay unchanged:** product names, template variables, allowed URLs/markup, punctuation, or special legal wording if any.

Notes should be concise and accurate, written from the perspective of **the translator as the reader**. A comment like "Translation here" adds no value. A comment like "Button label on the checkout screen; user clicks it to start payment immediately" is far more helpful.

## 4. Comments in Java .properties

Java `.properties` files allow comment lines starting with `#` or `!` (after leading whitespace skipped per properties syntax). For example:

```properties
# TRANSLATORS: Label on the primary checkout button.
# Action: starts payment immediately; not "save for later".
checkout.action.pay=Pay now

# TRANSLATORS: Shown above the cart items.
# {0} = total number of line items, already calculated by the app.
checkout.summary.itemCount=Items: {0}
```

The example file has two keys; the comment lines help translators understand context.

**Key point:** `PropertyResourceBundle` does not turn those comments into resources accessible by key. Calling `getString("TRANSLATORS")` in Java will not retrieve comment metadata; translator notes live in the source file and translation-management tools.

Some translation import/export tools strip or move comments, so your localization pipeline must verify comment preservation. If your team uses a translation platform, map the platform's description/context fields to source comments or stable metadata rather than merely hoping comments survive round-trips.

### Comments are separate from displayed values

```properties
# This is a translator note; users never see it.
account.error.sessionExpired=Your session has expired
```

The displayed value is only `Your session has expired`. The comment line is never included in output and does not change how `ResourceBundle` looks up the key.

Do not hide business metadata needed at runtime inside comments, because Java does not read comments after `PropertyResourceBundle` parses the file. Runtime metadata needs its own explicit design instead of relying on `#` lines.

## 5. Source code, base bundle, and translations should share one key contract

A familiar resource layout in a Java application:

```text
src/main/resources/
  messages.properties
  messages_vi.properties
  messages_fr.properties
  messages_ja.properties
```

- `messages.properties` can serve as the **root/default bundle** and the project's reference key catalog.
- `messages_vi.properties` holds Vietnamese translations.
- `messages_fr.properties` holds French translations.
- `messages_ja.properties` holds Japanese translations.

In a packaged application, you can use a base name like `com.example.i18n.messages` and place resources at `com/example/i18n/messages*.properties`. Traditional `ResourceBundle` filenames use `_` to join candidate locale parts such as `messages_vi_VN.properties`, whereas BCP 47 language tags passed to `Locale.forLanguageTag("vi-VN")` use hyphens `-`.

The same key should carry **the same meaning** in every locale:

```properties
# messages.properties
account.error.sessionExpired=Your session has expired.
```

```properties
# messages_vi.properties
account.error.sessionExpired=Phiên đăng nhập của bạn đã hết hạn.
```

Never let the same key mean "session expired" in English and "wrong password" in another language. That is a semantic compatibility bug even though none of the files have syntax errors.

### Must every file contain every key?

At runtime, `ResourceBundle` looks up keys in parent/fallback bundles; a translation missing a key can still resolve from its parent bundle. However, for **localization quality**, never treat "no exception thrown" as proof that translations are complete.

Distinguish three states:

1. **Key defined in that locale itself.**
2. **Key resolved from the root/parent bundle when missing in the locale.**
3. **Key not found at any fallback level.**

Case 2 can leave the UI mixing English and Vietnamese. If the product requires complete translation, QA tooling must compare **the actual set of keys declared in each source file** against the reference catalog, rather than just calling `ResourceBundle.getBundle(...).getString(key)` and seeing a value returned.

Some teams intentionally allow a few keys to fall back (proper names or untranslated content); those exceptions should be tracked explicitly rather than silently counted as complete.

## 6. Keeping keys stable across product changes

### Changing wording while keeping meaning

Suppose the key is:

```properties
checkout.action.pay=Pay now
```

The content team wants to change it to:

```properties
checkout.action.pay=Complete payment
```

If the button's function is still executing payment, **keep the key**. Update the source text, mark translations for review, and update the comment if the display context changed. There is no technical reason to rename it to `checkout.action.completePayment` just because the English phrasing was rewritten.

### Changing meaning: create a new key

If the button changes to "Schedule payment", it no longer means paying immediately. Create a new key such as `checkout.action.schedulePayment`, add a new description, and update Java references. Keep the old key while it is still used; delete it only after verifying no call sites remain and the translation workflow has migrated cleanly.

### Renaming or moving a feature

When a module is renamed while its functionality stays the same, you do not have to rename every key immediately just to tidy up namespaces. Consider:

- Is the resource key part of a public contract referenced by other components?
- Will renaming keys cause translation platforms to treat existing text as brand-new content?
- Should an alias or migration window be kept for one release?
- Do translators or analytics tools depend on the old IDs?

Never reuse a retired key for a new meaning: lingering translation memory or stale translations may get applied to an unrelated context.

### Checklist for reviewing a key change

1. Identify the new meaning and display location.
2. Check all call sites of the existing key.
3. Choose between editing the value, adding a new key, or doing an explicit migration.
4. Update the reference source, all relevant translations, and comments.
5. Check for extra/missing keys, placeholders, formatting, and UI layout.
6. Remove the old key only once it has no remaining consumers; do not "clean up keys" with unverified bulk deletions.

## 7. Placeholders are part of the translation contract

Translated strings often contain slots for runtime data. With `java.text.MessageFormat`, placeholders use syntax such as `{0}`, `{1}`, and optional subformats.

Example:

```properties
# TRANSLATORS: Summary line below the shopping cart.
# {0} = the number of products in the cart.
checkout.summary.itemCount=Items: {0}
```

Vietnamese version:

```properties
# TRANSLATORS: Summary line directly below the shopping cart.
# {0} = number of products in the cart, calculated by the app.
checkout.summary.itemCount=Số sản phẩm: {0}
```

The two sentences can use different word order, yet both preserve `{0}` so the program substitutes the count accurately. If a translation deletes it or accidentally changes it to `{1}`, runtime data can vanish or display wrongly.

### When there are multiple parameters

```properties
# {0} = buyer display name; {1} = order identifier.
order.notification.created=Hello {0}, order {1} is ready.
```

Translators need to know **the role of each index**, especially when target-language word order differs from English. They may reorder `{0}` and `{1}` in a translation when grammar calls for it, but they must not swap or alter their meanings.

Do not ask translators to invent or alter placeholder counts or template variables without a matching code-contract change. When the source text changes its parameter list, QA must verify every locale accordingly.

### MessageFormat is not printf, and single quotes matter

`MessageFormat` uses a different syntax from `String.format`. `{0}` is not `%s`. `MessageFormat` also has special rules for single quotes `'` and braces. For example, to display a literal apostrophe in a `MessageFormat` pattern, you may need to double it as `''`.

If a translation contains apostrophes, braces, or formatted number/date patterns, test it with **the exact formatter used at runtime**. Do not test with manual string replacement like `replace("{0}", value)` assuming it behaves like `MessageFormat`.

For singular/plural counts, replacing a single placeholder is not always enough across all languages. You may need pluralization rules via an appropriate i18n library or dedicated patterns; do not extrapolate English grammar rules to every locale.

### Never embed user-specific text into keys

Keys are stable identifiers, so never create keys like:

```text
order.error.paymentDeclinedForJohn
cart.items.3
welcome.Alice
```

Instead, use one key with placeholders so runtime data stays separate from translated text. That prevents key explosion, preserves proper grammar, and avoids putting personal data into resource IDs.

## 8. Complete Java 17+ example: comments, stable keys, and MessageFormat

Let us build a `messages` bundle family consisting of a root bundle, a Vietnamese bundle, and a Java program. The example runs on Java 17+; messages are looked up by key, and comments in properties help translators understand context without becoming keys.

Create **three files in the same directory**, saving the `.properties` files as UTF-8.

### File messages.properties

```properties
# TRANSLATORS: Primary button on the checkout screen.
# Action: immediately proceeds to payment, not saving for later.
checkout.action.pay=Pay now

# TRANSLATORS: Summary line shown below the cart.
# {0} = number of products currently in the cart.
checkout.summary.itemCount=Items: {0}

# TRANSLATORS: Displayed when a logged-in session expires.
account.error.sessionExpired=Your session has expired.

# TRANSLATORS: Link text opening the refund policy.
checkout.link.refundPolicy=Refund policy
```

### File messages_vi.properties

```properties
# TRANSLATORS: Primary button on the checkout screen; executes payment immediately.
checkout.action.pay=Thanh toán ngay

# TRANSLATORS: Summary line below the shopping cart.
# {0} = number of products in the cart.
checkout.summary.itemCount=Số sản phẩm: {0}

# TRANSLATORS: Displayed when the login session expires.
account.error.sessionExpired=Phiên đăng nhập đã hết hạn.
```

`checkout.link.refundPolicy` is intentionally left untranslated in the Vietnamese file to illustrate fallback from the root bundle. In a real product, this is a key that a missing-translation report should flag.

### File ResourceKeyDemo.java

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class ResourceKeyDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);

        String button = bundle.getString("checkout.action.pay");
        String pattern = bundle.getString("checkout.summary.itemCount");
        String summary = new MessageFormat(pattern, locale)
                .format(new Object[] {3});

        System.out.println(button);
        System.out.println(summary);
        System.out.println(
                bundle.getString("account.error.sessionExpired"));
        System.out.println(
                bundle.getString("checkout.link.refundPolicy"));

        System.out.println(bundle.containsKey("TRANSLATORS"));
    }
}
```

Compile and run from the directory containing all three files:

```bash
javac -encoding UTF-8 ResourceKeyDemo.java
java -cp . ResourceKeyDemo
```

Stdout:

```text
Thanh toán ngay
Số sản phẩm: 3
Phiên đăng nhập đã hết hạn.
Refund policy
false
```

**Line-by-line explanation:**

1. `checkout.action.pay` retrieves the value from `messages_vi.properties`; the key in Java contains no Vietnamese text or button wording.
2. `checkout.summary.itemCount` preserves the `{0}` parameter, and `MessageFormat` substitutes `3`.
3. `account.error.sessionExpired` retrieves the Vietnamese sentence using the same semantic key across both locales.
4. `checkout.link.refundPolicy` is absent from the Vietnamese file; `ResourceBundle` finds the value in the parent/root bundle. The example runs, yet **the translation is incomplete**.
5. `containsKey("TRANSLATORS")` returns `false` because `# TRANSLATORS: ...` comments are source metadata and do not create a `TRANSLATORS` key.

The example uses an explicit locale, avoiding changes to the JVM's `Locale.setDefault`. Java 17+ reads `.properties` files in `ResourceBundle` using UTF-8-capable loading; avoid authoring files in uncontrolled encodings.

### In a real project

In Maven or Gradle projects, files are typically stored at `src/main/resources/messages.properties` and `src/main/resources/messages_vi.properties`, with Java classes in the corresponding source directory. If placing bundles inside a package, use the matching resource path and full base name. Files must be present on the runtime classpath; leaving them in a working directory without packaging them can cause `MissingResourceException`.

In environments with the module system, custom class loaders, or a custom `ResourceBundle.Control`, also verify the corresponding resource-loading rules. The example here assumes the default classpath.

## 9. Keeping comments in sync with changes

A misleading comment can be worse than a missing comment. Suppose:

```properties
# Button opens the refund details, no payment is performed.
checkout.action.pay=Pay now
```

The key name, value, and comment disagree about the action. Translators may translate it as "view refund policy," while Java code still invokes the key for the payment button.

When making updates:

- **Displayed copy:** check whether the comment still describes the context accurately.
- **Product behavior:** decide whether a new key and a new comment are needed.
- **Placeholders:** update parameter positions and descriptions, and test parameter counts and ordering.
- **UI constraints:** update only when UI constraints actually change; avoid inventing arbitrary character limits.
- **Screenshots or reference links:** if your translation tool supports them, attach the right screen and keep links working across UI redesigns.

During reviews, translators should receive **enough context to choose phrasing** without having to read the entire Java codebase. Good notes reduce back-and-forth questions and mistranslations, though they do not replace testing in the real UI.

## 10. Quality checks and automation

### A. Comparing each locale's key set

The key set in `messages.properties` serves as the baseline when the project uses the root bundle as its primary source. For each language file:

- **Missing keys:** present in the root but not defined in that file.
- **Extra keys:** present in the language file but no longer in the root or not permitted.
- **Duplicate keys:** repeated in the same file, allowing one value to shadow another.
- **Empty values:** key present with an empty value; valid in rare contexts, requires a policy.
- **Stale comments:** describe the wrong action or wrong placeholders.
- **Orphan keys:** keys in resources with no remaining call sites; do not delete mechanically when dynamic lookups exist.

To detect missing translations, tools should inspect **keys declared in each individual file** rather than only querying `ResourceBundle.containsKey(key)`. Reason: `containsKey` traverses the parent chain, so a key missing from the Vietnamese file still reports as present via root fallback.

Properties-reading libraries can also overwrite duplicate keys and lose the fact that a key appeared twice. To catch duplicates reliably, a lint tool should analyze **the raw source file** (handling escapes and line continuations accurately) rather than inspecting only the final map.

### B. Checking placeholders, types, and quotes

If code calls `new MessageFormat(pattern, locale)`, tests should:

1. Parse patterns for **every supported locale** with the corresponding `MessageFormat`.
2. Verify expected placeholders against the code/source contract.
3. Catch missing, extra, or misnumbered parameter indices, and check number/date/time parameter types where needed.
4. Assert sample formatted outputs with test inputs, including special characters and boundary values.
5. Check patterns containing single quotes and braces, which commonly cause translation bugs.

You cannot enforce "placeholders must appear in the exact same order as the source" across all languages: translations may reorder `{0}` and `{1}` for natural grammar. What must be preserved is **the same meaning and valid parameter set**.

### C. Checking text in the real UI

A translation can be valid in the file and still cause:

- Truncated text on buttons, tabs, and navigation bars.
- Sentences missing articles or suffixes due to missing context.
- Names or numbers concatenated in an awkward order.
- Broken diacritics, fonts, text direction, or special characters.
- Inconsistent tone between screens and emails.

Therefore, resource-file QA and UI QA complement each other. When doing visual/screenshot reviews, give translators the right screens and states, especially for easily misunderstood keys.

### D. CI checks you can adopt

A minimal pipeline can enforce:

1. No properties syntax errors or UTF-8 encoding errors.
2. No duplicate keys outside an approved exception list.
3. No broken placeholders under the formatter in use.
4. Every key referenced in code exists in the source catalog, unless explicitly marked as dynamic access.
5. Every new key has sufficient context where needed.
6. Translation completion rates are calculated from **actual keys in each locale**, without counting fallback as translated.
7. Semantic changes use transparent key migrations.

Not every issue has to block a release identically. You can tier missing translations, unused keys, placeholder errors, and syntax errors by severity. However, **the difference between genuine translations and fallback** must always remain visible in reports.

## 11. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `button1` or `label42` | Impossible to infer the key's meaning | Name by feature and function |
| Using literal English sentences as keys | Copy edits make identifiers misleading | Separate stable keys from displayed values |
| Renaming keys on every wording edit | Loses translation memory and increases migration work | Keep the key when semantics do not change |
| Reusing an old key for a new feature | Old translations get applied in the wrong context | Create a new key and update call sites |
| Merging every `common.ok`, `common.open`, `common.save` | Loses action context and part-of-speech distinctions | Reuse only when the meaning is truly identical |
| Leaving `{0}` placeholders undocumented | Translators may drop, misorder, or break syntax | Document parameter meaning and examples |
| Treating `#` comments as runtime metadata | Code cannot read comments via `ResourceBundle` | Use comments for the translation workflow; use a separate schema if runtime needs it |
| Testing only `bundle.getString(key)` | Root fallback hides missing translations | Compare the key set declared inside each locale file |
| Editing `.properties` without checking encoding | Vietnamese characters break during packaging or reading | Standardize on UTF-8 and test Unicode at runtime |
| Treating a source typo fix as a new key | Creates unnecessary duplicates and missing translations | Keep the key and flag the value for re-translation |
| Concatenating translated fragments to build sentences | Grammar, word order, and plurals become hard to translate | Design complete messages with meaningful placeholders |
| Skipping checks after importing from translation tools | Comments or placeholders may get stripped | Lint and test outputs after import |

## 12. Practice exercises

**Exercise 1 — Splitting keys by meaning.** An application has three screens: opening a file, viewing an order's "Open" status, and showing that a store is open. Propose three semantically distinct keys and write comments that prevent translators from confusing them.

**Exercise 2 — Keep the key or change it?** The `checkout.action.pay` button changes its value from "Pay now" to "Complete payment" while still paying immediately. Should you keep the key or create a new one? Later, the product changes the action to "Schedule payment for next week"; does your decision change, and why?

**Exercise 3 — Placeholders.** A message has `order.status.ready=Order {0} is ready for {1}`, where `{0}` is the order ID and `{1}` is the recipient's name. Write two comment lines clearly describing the parameters and explain why a translator may reorder the placeholders if their language requires it.

**Exercise 4 — Detecting missing translations.** In `ResourceKeyDemo`, why does `getString("checkout.link.refundPolicy")` still succeed and return "Refund policy"? Describe how to detect that this key **lacks a Vietnamese translation** even though the call throws no exception.

**Exercise 5 — Evaluating comments.** Compare `# label text` and `# Button at checkout; pressing it starts payment immediately.`. Which comment is more helpful, and what information is still missing if the button has a width constraint?

## 13. Summary

**A resource key is a stable contract identifier; a value is text that can evolve per locale and copy revision.** Design keys around meaning, not display order or verbatim English text. Two identical-looking strings can still require two keys if their contexts differ; retired keys should not be reused for new actions.

**Translator comments explain meaning in context**, especially display location, function, target object, and placeholders. In `.properties` files, `#`/`!` comments assist the translation authoring workflow but cannot be read as key/value entries through `ResourceBundle`.

Finally, maintain alignment between source and translations through key-set comparisons, placeholder checks, and UI QA. `ResourceBundle` can fall back cleanly even when the requested locale lacks a translation; your testing pipeline must surface that gap so users do not end up seeing mixed-language screens.
