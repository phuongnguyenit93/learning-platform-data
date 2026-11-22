# Switching Language at Runtime and Refreshing Formatted Data in Java

## 1. What Is Runtime Language Switching in a Live Application?

Suppose a Java application is currently displaying:

~~~text
[en-US] Orders
Welcome, Lan!
Date: March 5, 2025
Quantity: 1,234.50
~~~

The user clicks **Tiếng Việt** without restarting. The UI must update labels, messages, and formatting:

~~~text
[vi-VN] Đơn hàng
Xin chào, Lan!
Ngày: 5 tháng 3, 2025
Số lượng: 1.234,50
~~~

This is not merely swapping the text `Orders` for `Đơn hàng`. Selecting a new locale can affect:

- Labels, titles, menus, buttons, tooltips, placeholders, error messages, and accessibility text.
- Formatting of numbers, percentages, currency units, dates/times, and month names.
- Parameterized messages, parameter ordering, plurals, and phrasing choices.
- Table headers, numeric columns, chart axis labels, empty-state descriptions, and open notifications.
- LTR/RTL layout, line wrapping, text run direction, and fonts.
- Asynchronous results formatted before the user switched languages.
- Uncommitted input fields: avoiding losing drafts or misreading grouping marks when switching locales.

**Core principle:** switching locale changes the **presentation context**. It does not cause already-formatted `String`s to update themselves, nor should it alter business data. Keep data strongly typed, update locale state, reselect resources/formatters, and re-render the UI.

## 2. Three Layers That Must Not Be Mixed

~~~text
DOMAIN MODEL (immutable source)
  customerName: "Lan"
  orderId: 42
  quantity: BigDecimal("1234.50")
  date: LocalDate.of(2025,3,5)
  price: Money(amount, Currency.USD)
            |
            | apply PresentationContext
            v
PRESENTATION CONTEXT
  uiLocale: en-US / vi-VN
  formatLocale: en-US / vi-VN (if separated by app)
  zone: Asia/Ho_Chi_Minh
  currency: USD (true business currency)
            |
            v
PRESENTATION
  ResourceBundle -> labels/messages
  NumberFormat -> numbers/money/percentages
  DateTimeFormatter -> dates/times
  MessageFormat -> parameterized messages
  ComponentOrientation -> LTR/RTL
            |
            v
UI/RENDERER
~~~

| What to preserve | Data type | On locale switch |
| --- | --- | --- |
| Quantity | `BigDecimal` | Call number formatter with new locale |
| Calendar date without time | `LocalDate` | Reformat with new locale |
| Absolute instant | `Instant` | Format with selected locale and `ZoneId` |
| Currency | `Currency` alongside `BigDecimal` value | Change symbol placement/style; **never convert currency** |
| Order ID | ID, schema-defined `String` | Normally keep characters verbatim, do not format as a number |
| Customer name | Original `String` | Keep name intact; insert into new message |
| UI language | `Locale` or BCP 47 language tag | Update state and notify presenters |
| Formatted string | Derived `String` | **Regenerate**, never treat as source data |

A `BigDecimal("1234.50")` does not become `BigDecimal("1.234,50")` when changing language. `"1.234,50"` is only a **display string**. Likewise, given an `Instant`, changing locale does not alter `ZoneId` or the event's point in time.

**Why not store data as labels?** Because translations, separator conventions, and JDK locale data can differ across users or updates. A formatted string is insufficient to recover typed semantics safely.

## 3. `Locale.setDefault` Is Not a Per-User Language Switch

An approach that looks deceptively simple:

~~~java
Locale.setDefault(Locale.forLanguageTag("vi-VN"));
frame.repaint();
~~~

This is just an **illustrative fragment** inside a method requiring `import Locale` and an existing `frame` variable. It does not guarantee the open UI will switch languages.

Three problems:

1. `Locale.setDefault` mutates the **JVM-wide default locale** (or JVM-wide category), not a single request or window.
2. Previously constructed `ResourceBundle`, `NumberFormat`, `MessageFormat`, and `DateTimeFormatter` instances **do not update** their contents when you mutate the default.
3. `repaint` only redraws stored labels; unless `JLabel.setText` is called with the new translation, the old text remains.

### Multi-User Server: Race Conditions

~~~text
Request A: selects vi-VN -> Locale.setDefault(vi-VN)
Request B: selects en-US -> Locale.setDefault(en-US)
Request A: formats number with NumberFormat.getInstance()
           -> may accidentally use B's default
~~~

Never use the mutable default locale to serve concurrent users. Instead:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle b = ResourceBundle.getBundle("Messages", locale);
NumberFormat nf = NumberFormat.getNumberInstance(locale);
DateTimeFormatter df = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(locale);
~~~

This is a **fragment inside a method** requiring imports for `java.util.Locale`, `java.util.ResourceBundle`, `java.text.NumberFormat`, `java.time.format.DateTimeFormatter`, and `FormatStyle`.

A locale belongs to a **session, screen, or request**. Never keep a mutable static `currentLocale` shared across all clients in a web server.

## 4. Proper Locale-Switching Flow

When a user selects a new language:

1. **Receive event** `LanguageChanged(newLocale)`.
2. **Validate** that the locale is in the app's supported set; never assume a valid tag has translations.
3. **Update state** at the proper scope (user/session/window).
4. **Select resources** from `ResourceBundle` for that locale.
5. **Prepare formatters** for the new locale; ensure mutable formatters are never reused improperly.
6. **Rebuild presentation models** from typed data and message keys, never re-parsing old UI strings to recover values.
7. **Update every view** dependent on locale: labels, numbers, dates, validation errors, tooltips, tables, dialogs, accessibility.
8. **Update layout** if text direction, label lengths, alignment, or fonts change.
9. **Preserve user input** and current selections unless product policy calls for controlled conversion.
10. **Discard stale async results** or reformat them using the current locale.
11. **Persist preference** if the user expects their language choice to survive across sessions.

A reactive app can trigger bindings that depend on `locale`; an imperative app can call `applyLocale(locale)` to update components. Both must inventory every place where text was formatted.

## 5. Complete Console Example: Switching `en-US` to `vi-VN`

A Java 17+ example runnable with just the JDK, no Maven or framework required. Create this directory:

~~~text
locale-console/
  LanguageSwitchDemo.java
  Messages_en.properties
  Messages_vi.properties
~~~

Create `Messages_en.properties` in UTF-8:

~~~properties
title=Orders
welcome=Welcome, {0}!
date=Date
quantity=Quantity
name=Customer
language=Language
~~~

Create `Messages_vi.properties` in UTF-8:

~~~properties
title=Đơn hàng
welcome=Xin chào, {0}!
date=Ngày
quantity=Số lượng
name=Khách hàng
language=Ngôn ngữ
~~~

Create `LanguageSwitchDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ResourceBundle;

public class LanguageSwitchDemo {
    record Order(
            String customer,
            BigDecimal quantity,
            LocalDate date
    ) {}

    static final class OrderScreen {
        private final Order order; // Source data
        private Locale locale;     // Presentation state

        OrderScreen(Order order, Locale locale) {
            this.order = order;
            this.locale = locale;
        }

        void changeLanguage(Locale next) {
            this.locale = next;
            render();
        }

        void render() {
            ResourceBundle messages =
                    ResourceBundle.getBundle("Messages", locale);

            NumberFormat numbers =
                    NumberFormat.getNumberInstance(locale);
            numbers.setMinimumFractionDigits(2);
            numbers.setMaximumFractionDigits(2);

            DateTimeFormatter dates = DateTimeFormatter
                    .ofLocalizedDate(FormatStyle.LONG)
                    .withLocale(locale);

            MessageFormat welcome = new MessageFormat(
                    messages.getString("welcome"), locale);

            System.out.println("[" + locale.toLanguageTag()
                    + "] " + messages.getString("title"));
            System.out.println(welcome.format(
                    new Object[]{order.customer()}));
            System.out.println(messages.getString("date") + ": "
                    + order.date().format(dates));
            System.out.println(messages.getString("quantity") + ": "
                    + numbers.format(order.quantity()));
        }
    }

    public static void main(String[] args) {
        Order order = new Order(
                "Lan",
                new BigDecimal("1234.50"),
                LocalDate.of(2025, 3, 5));

        OrderScreen screen = new OrderScreen(
                order, Locale.forLanguageTag("en-US"));
        screen.render();

        screen.changeLanguage(Locale.forLanguageTag("vi-VN"));
    }
}
~~~

Compile and run inside `locale-console`:

~~~bash
javac -encoding UTF-8 LanguageSwitchDemo.java
java -cp . LanguageSwitchDemo
~~~

Reference output from a JDK with standard locale data:

~~~text
[en-US] Orders
Welcome, Lan!
Date: March 5, 2025
Quantity: 1,234.50
[vi-VN] Đơn hàng
Xin chào, Lan!
Ngày: 5 tháng 3, 2025
Số lượng: 1.234,50
~~~

**Note:** exact grouping separators, spacing, or date wording may vary by provider/JDK/CLDR. Fixed keys/labels from `.properties` files must match; number/date output should be tested on the supported target environment.

### Why Is This Example Right?

- `Order` is an immutable `record`: the exact same source data is rendered twice.
- `changeLanguage` updates the **screen's** `Locale`, never calling `Locale.setDefault`.
- `render` reselects `ResourceBundle`, `NumberFormat`, `DateTimeFormatter`, and `MessageFormat` for the current locale.
- Date and number are **reformatted from typed values**, rather than parsing `"March 5, 2025"` or `"1,234.50"` and guessing backward.
- Each language owns the **full sentence** `welcome` with placeholder `{0}`; translators can adjust parameter order if needed.
- All `.properties` files and Java literals are saved in UTF-8; `javac -encoding UTF-8` prevents compilation differences on older environments.

**Scope limit:** the console example only simulates events. In a GUI, `render` updates components or observable state; underlying data rules remain identical.

## 6. `ResourceBundle`: Switching Locales Differs from Reloading Files

`ResourceBundle.getBundle("Messages", locale)` selects the matching bundle. An already-fetched `ResourceBundle english` **does not turn into Vietnamese** when state changes.

~~~java
ResourceBundle english = ResourceBundle.getBundle(
        "Messages", Locale.ENGLISH);
ResourceBundle vietnamese = ResourceBundle.getBundle(
        "Messages", Locale.forLanguageTag("vi-VN"));
~~~

This is a fragment inside a method requiring imports for `java.util.ResourceBundle` and `java.util.Locale`.

### Is Caching a Problem?

`ResourceBundle` caches bundles to avoid reloading the same file repeatedly. Switching `en-US` → `vi-VN` **requests a different locale**; it does not modify source files. Normally, therefore, **do not call `ResourceBundle.clearCache()` on every switch**.

Consider invalidation only when **bundle file contents change at runtime**. For resources packaged inside a JAR, changes normally ship only in a new release. For live external sources, define a TTL/`needsReload` policy or custom provider mechanism. Do not confuse looking up another bundle with refreshing a cached entry.

### Fallback and Missing Keys

`ResourceBundle` searches candidate locales and inherits keys from parent bundles. If `Messages_vi_VN.properties` is absent while `Messages_vi.properties` exists, the app can use the `vi` bundle. However, if no resource exists for the requested locale, the default fallback algorithm may consult the JVM's default locale.

To prevent server language from leaking into the UI:

- Allow choosing only **supported locales**; verify available resources.
- Define an intentional **business fallback**, such as English for missing keys.
- On classpath/unnamed modules, you can use `ResourceBundle.Control.getNoFallbackControl` to suppress fallback to the JVM default while keeping candidate/parent root chains.
- In **named modules** (JPMS), `ResourceBundle.getBundle(..., Control)` is unsupported; use module/provider mechanisms instead.

`MissingResourceException` can be thrown on a missing bundle or key; validate key completeness at build/QA time and define explicit error/fallback handling rather than silently returning empty strings.

## 7. `NumberFormat`: Recreate per Locale, Keep the Underlying Number

Example:

~~~java
BigDecimal value = new BigDecimal("1234.50");
Locale us = Locale.forLanguageTag("en-US");
Locale vi = Locale.forLanguageTag("vi-VN");

NumberFormat en = NumberFormat.getNumberInstance(us);
NumberFormat vn = NumberFormat.getNumberInstance(vi);
en.setMinimumFractionDigits(2);
en.setMaximumFractionDigits(2);
vn.setMinimumFractionDigits(2);
vn.setMaximumFractionDigits(2);

System.out.println(en.format(value));
System.out.println(vn.format(value));
~~~

This is a fragment inside a method requiring imports for `BigDecimal`, `Locale`, and `NumberFormat`. Standard JDK locale data typically outputs:

~~~text
1,234.50
1.234,50
~~~

`NumberFormat` and `DecimalFormat` are **mutable** and must not be treated as thread-safe when shared without synchronization. A formatter created for `Locale.US` does not change when the default locale changes. When rendering for multiple users, create formatters per request or clone/configure per task.

### Language Does Not Automatically Change Currency Units

If an order is in **USD**, switching the UI to Vietnamese does not turn it into VND. To display it:

~~~java
Currency usd = Currency.getInstance("USD");
NumberFormat money = NumberFormat.getCurrencyInstance(locale);
money.setCurrency(usd);
String shown = money.format(amount);
~~~

This is a fragment inside a method requiring imports for `java.util.Currency` and `java.text.NumberFormat`, plus `locale` and `amount` variables. `setCurrency` changes the displayed currency without **performing exchange-rate conversion**. Nor does it always adjust configured fraction digits automatically; for money, establish explicit precision/rounding and currency-identity policies.

## 8. `DateTimeFormatter`: Shareable with Explicit Configuration

`DateTimeFormatter` in `java.time` is **immutable and thread-safe**. `withLocale` returns a new formatter:

~~~java
DateTimeFormatter base =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

DateTimeFormatter english = base.withLocale(Locale.US);
DateTimeFormatter vietnamese = base.withLocale(
        Locale.forLanguageTag("vi-VN"));
~~~

This is a fragment inside a method requiring imports for `DateTimeFormatter`, `FormatStyle`, and `Locale`. `base` remains unchanged.

When displaying an `Instant`, add `ZoneId`:

~~~java
Instant moment = Instant.parse("2025-03-05T10:15:30Z");
ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");

DateTimeFormatter f = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.MEDIUM)
        .withLocale(locale)
        .withZone(userZone);

String displayed = f.format(moment);
~~~

This is a fragment inside a method requiring imports for `java.time.Instant`, `ZoneId`, `DateTimeFormatter`, and `FormatStyle`, plus a `locale` variable.

**Changing `Locale` differs from changing `ZoneId`.** A user may want an English UI in Vietnam, or a Vietnamese UI in Berlin's time zone. Keep those settings separate when business requirements allow it.

## 9. `MessageFormat`: `setLocale` Does Not Update Existing Subformats

`MessageFormat` supports localized parameterized sentences. However, its Javadoc states explicitly that **`setLocale` does not update `Format` objects previously created by `applyPattern`**. Legacy code keeping a `MessageFormat` with `{0,number}` and calling only `setLocale` can continue formatting numbers in the old locale.

### Complete Java 17+ Example

Create `MessageFormatSwitchDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageFormatSwitchDemo {
    public static void main(String[] args) {
        Locale en = Locale.forLanguageTag("en-US");
        Locale vi = Locale.forLanguageTag("vi-VN");

        MessageFormat formatter =
                new MessageFormat("{0,number}", en);

        System.out.println("Before: "
                + formatter.format(new Object[]{1234.5}));

        formatter.setLocale(vi);
        System.out.println("Only setLocale: "
                + formatter.format(new Object[]{1234.5}));

        formatter.applyPattern("{0,number}");
        System.out.println("Re-apply pattern: "
                + formatter.format(new Object[]{1234.5}));

        MessageFormat fresh =
                new MessageFormat("{0,number}", vi);
        System.out.println("Fresh formatter: "
                + fresh.format(new Object[]{1234.5}));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 MessageFormatSwitchDemo.java
java MessageFormatSwitchDemo
~~~

Verified JDK output:

~~~text
Before: 1,234.5
Only setLocale: 1,234.5
Re-apply pattern: 1.234,5
Fresh formatter: 1.234,5
~~~

**Recommendation:** when switching locales in a UI, construct a fresh `MessageFormat` with **the new locale's translated pattern**. If reusing instances, understand mutable state, `applyPattern`, and manually configured number/date subformats. Never share a mutable `MessageFormat` across threads without synchronization.

### Messages Must Be Translated as Complete Sentences

Avoid concatenating:

~~~java
String s = bundle.getString("prefix")
        + " " + customer + " " + bundle.getString("suffix");
~~~

This is a fragment inside a method with existing `bundle` and `customer`. Sentence structure varies across languages. Use `welcome=Welcome, {0}!` and `welcome=Xin chào, {0}!` so translators control parameter order. Check `MessageFormat` single-quote escaping rules and consider locale-aware pluralization libraries for complex messages.

## 10. Swing GUI: Refreshing Components on Language Switch

A Swing app needs to update **`JLabel`s, window title, formatted values, and component orientation**, not just reassign one variable. The example below reuses `Messages_en.properties` and `Messages_vi.properties` from Example 1, containing keys `title`, `welcome`, `date`, `quantity`, `name`, and `language`.

Create `SwingLanguageSwitchDemo.java` in the same directory:

~~~java
import java.awt.ComponentOrientation;
import java.awt.GridLayout;
import java.math.BigDecimal;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ResourceBundle;
import javax.swing.JComboBox;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.JTextField;
import javax.swing.SwingUtilities;

public class SwingLanguageSwitchDemo {
    private final JFrame frame = new JFrame();
    private final JPanel panel = new JPanel(
            new GridLayout(5, 2, 8, 8));

    private final JComboBox<String> language =
            new JComboBox<>(new String[]{"English", "Tiếng Việt"});
    private final JLabel languageLabel = new JLabel();
    private final JLabel customerLabel = new JLabel();
    private final JTextField customerField = new JTextField("Lan", 12);
    private final JLabel dateLabel = new JLabel();
    private final JLabel dateValue = new JLabel();
    private final JLabel quantityLabel = new JLabel();
    private final JLabel quantityValue = new JLabel();
    private final JLabel greetingLabel = new JLabel();

    private final LocalDate date = LocalDate.of(2025, 3, 5);
    private final BigDecimal quantity = new BigDecimal("1234.50");

    SwingLanguageSwitchDemo() {
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);

        panel.add(languageLabel);
        panel.add(language);
        panel.add(customerLabel);
        panel.add(customerField);
        panel.add(dateLabel);
        panel.add(dateValue);
        panel.add(quantityLabel);
        panel.add(quantityValue);
        panel.add(greetingLabel);
        panel.add(new JLabel());
        frame.setContentPane(panel);

        language.addActionListener(e -> {
            Locale locale = language.getSelectedIndex() == 0
                    ? Locale.forLanguageTag("en-US")
                    : Locale.forLanguageTag("vi-VN");
            applyLocale(locale);
        });

        applyLocale(Locale.forLanguageTag("en-US"));
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }

    private void applyLocale(Locale locale) {
        ResourceBundle b = ResourceBundle.getBundle(
                "Messages", locale);
        NumberFormat number = NumberFormat.getNumberInstance(locale);
        number.setMinimumFractionDigits(2);
        number.setMaximumFractionDigits(2);

        DateTimeFormatter dates =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(locale);
        MessageFormat greeting =
                new MessageFormat(b.getString("welcome"), locale);

        frame.setTitle(b.getString("title"));
        languageLabel.setText(b.getString("language"));
        customerLabel.setText(b.getString("name"));
        dateLabel.setText(b.getString("date"));
        dateValue.setText(date.format(dates));
        quantityLabel.setText(b.getString("quantity"));
        quantityValue.setText(number.format(quantity));
        greetingLabel.setText(greeting.format(
                new Object[]{customerField.getText()}));

        ComponentOrientation orientation =
                ComponentOrientation.getOrientation(locale);
        frame.applyComponentOrientation(orientation);
        panel.applyComponentOrientation(orientation);
        panel.revalidate();
        panel.repaint();
        frame.pack();
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(SwingLanguageSwitchDemo::new);
    }
}
~~~

Compile and run in a **desktop/GUI environment**, not headless CI:

~~~bash
javac -encoding UTF-8 SwingLanguageSwitchDemo.java
java -cp . SwingLanguageSwitchDemo
~~~

### What the Swing Demo Handles

- The window opens once; the user picks from the dropdown to switch locale **while running**.
- Event listeners and Swing updates execute on the **Event Dispatch Thread (EDT)** because the constructor runs via `SwingUtilities.invokeLater`.
- Labels, frame title, date, number, and greeting are all **recomputed**.
- The customer `JTextField` is preserved; switching language **does not wipe out typed input**.
- `ComponentOrientation` lets the layout adopt directional hints from the locale; complex RTL apps should test individual widgets and layout manager support.
- `revalidate`/`repaint`/`pack` help the UI adapt when translations are longer.
- The screen's `LocalDate` and `BigDecimal` objects remain intact.

**Production limitations:** the demo does not update the greeting while typing the name; for live updates, attach an appropriate `DocumentListener`. Menus, tooltips, validation messages, accessible descriptions, table headers, and child windows need similar refresh logic. Some components also need focus/selection handling or custom layouts beyond `applyComponentOrientation`.

## 11. Reactivity: Locale Is State, Recomputed Strings Are Derived Data

In large GUIs, manually writing hundreds of `label.setText(...)` calls is error-prone. MVVM/reactive architectures let you define:

~~~text
localeState = vi-VN
   |
   +--> titleText      = bundle(localeState).getString("title")
   +--> amountText     = formatNumber(amount, localeState)
   +--> dateText       = formatDate(date, localeState)
   +--> welcomeText    = formatMessage(name, localeState)
   +--> orientation    = direction(localeState)
   |
   v
View observes derived values and re-renders
~~~

In JavaFX, you can use observable properties/bindings; in web frontends, use state management. Regardless of framework, **every derived value must declare its dependency on `locale`**. If date text is computed once in a constructor and cached without invalidation, changing language state will not update it.

Distinguish two models:

- **Imperative:** an `applyLocale(locale)` method updates each component. Works for small apps with a thorough checklist.
- **Reactive:** locale is state and labels/numbers/dates are derived values. Scales across many screens; frameworks assist invalidation, though caches and async updates still require management.

Avoid keeping isolated copies of locale per dialog without synchronizing them if the product expects all windows to switch language together.

## 12. Switching Locale While a Field Is Being Edited

Suppose a form is receiving a number in `en-US`:

~~~text
1,234.50
~~~

Before submitting, the user switches to `vi-VN`. If code takes that string and feeds it to a `vi-VN` parser, `,` may be read as the **decimal separator**, and `.` as the grouping separator. That can yield the wrong value or parse only a prefix.

Choose an explicit policy:

**Policy A — Preserve draft.** While input is uncommitted, keep `JTextField.getText()` untouched and store `localeAtEditStart`; update only labels/hints until editing finishes. On commit, parse with the input's associated locale or ask for confirmation.

**Policy B — Controlled conversion.** Before switching, parse/validate the input using the **old locale** into a `BigDecimal`. If valid and accepted by the user, reformat from the typed value into the new locale while handling focus/caret/selection.

**Do not do this:**

~~~java
NumberFormat parser =
        NumberFormat.getNumberInstance(currentLocale);
Number value = parser.parse(uncommittedText);
~~~

This snippet **illustrates the wrong approach** (and would also need `ParseException` handling). `currentLocale` may already differ from the locale the user was using while typing.

`NumberFormat.parse` can also consume just a valid **prefix**; when strict validation is required, use `ParsePosition` to confirm the full string was consumed and check grouping positions, scale, and business bounds.

## 13. Asynchrony: Prevent Stale-Language Results from Overwriting the New UI

Example:

~~~text
t0: screen is en-US; fetch starts
t1: user switches to vi-VN
t2: English response arrives after the switch
t3: if applied blindly -> UI mixes English and Vietnamese
~~~

Two important safeguards:

1. **Fetch locale-neutral business data** when possible, then format for the current locale **right at commit/render time**.
2. For tasks returning already-translated or pre-formatted content, attach a **locale/version/generation** token; on completion, apply the result only if it still matches current state.

### Generation Guard Pattern (Architectural Snippet)

~~~java
final AtomicLong generation = new AtomicLong();
volatile Locale current = Locale.forLanguageTag("en-US");

void changeLanguage(Locale next) {
    current = next;
    generation.incrementAndGet();
    renderAll(next);
}

void startLoad() {
    long version = generation.get();
    Locale requested = current;

    fetchAsync().thenAccept(data -> {
        runOnUiThread(() -> {
            // Check inside the UI callback, not just before enqueuing.
            if (version != generation.get()) {
                return;
            }
            renderData(data, requested);
        });
    });
}
~~~

This is a **non-standalone fragment** requiring `AtomicLong` from `java.util.concurrent.atomic`. `fetchAsync`, `runOnUiThread`, `renderAll`, and `renderData` are framework-supplied methods.

**Why check inside the UI callback?** If you check `generation` only before enqueuing onto the EDT, the user could switch locale between that check and when the callback actually executes. Perform the final check at the commit point.

In a multi-user app, `generation` must be scoped per **user/session/window**, never a server-wide counter where users accidentally cancel each other's jobs.

## 14. Separate `uiLocale`, `formatLocale`, `zone`, and `currency` When Needed

Some applications allow English UI text alongside German number rules, Vietnam time zone, and USD currency. You do not have to collapse all choices into a single `Locale`:

~~~java
record UserPreferences(
        Locale uiLocale,
        Locale formatLocale,
        ZoneId zone,
        Currency currency
) {}
~~~

This is a declaration snippet inside a class requiring imports for `java.util.Locale`, `java.time.ZoneId`, and `java.util.Currency`.

Each layer uses the right attribute:

| Attribute | Responsibility |
| --- | --- |
| `uiLocale` | Picks `ResourceBundle`, button names, help text, messages |
| `formatLocale` | Formats numbers and dates per chosen convention |
| `zone` | Converts `Instant` into local time |
| `currency` | Currency unit of the value, not an exchange rate |
| `measurementSystem` (if any) | Unit policy, e.g., km/mi |

For small applications, one shared locale may suffice. Once business requirements allow independent settings, never silently alter `zone` or `currency` when the user only picks a language.

## 15. Language Switching Also Touches Text Direction, Accessibility, and Layout

Vietnamese and English are typically LTR. Expanding to Arabic or Hebrew can require:

- Updating container/paragraph base direction for the target locale.
- Aligning labels, icon/text order, button order, and table orientation.
- Isolating LTR URLs, emails, or product codes embedded inside RTL sentences.
- Updating accessible names/descriptions for screen readers.
- Updating tooltips, alt text, and cached strings in menus/dialogs.
- Checking font fallback, combining marks, and translation length changes.
- Ensuring logical order of data and IDs is **never reversed** to match visual order.

In Swing, `ComponentOrientation.getOrientation(locale)` is the starting point; in HTML, use `dir` and `<bdi>`. Never call `new StringBuilder(text).reverse()` to "convert to RTL": reversing strings breaks numbers, punctuation, emojis, and grammar.

For formatted dates, `DateTimeFormatter.ofLocalizedDate` is usually better than forcing a fixed day/month/year pattern across all locales. For standalone month names in calendar headers, use `LLLL` instead of `MMMM` in languages that distinguish standalone vs. formatting month forms.

## 16. UI Areas to Refresh and Completion Criteria

| Area to check | Examples | What to do |
| --- | --- | --- |
| Header | Window title, navigation bar | Fetch text for new locale |
| Controls | Buttons, menus, tabs | Update labels/shortcuts/tooltips |
| Forms | Labels, hints, placeholders | Update text while preserving user drafts |
| Validation | Errors, warnings, inline help | Re-translate active errors without losing error state |
| Notifications | Snackbars, toasts, dialogs | Update/dismiss/keep history per policy |
| Tables | Headers, numeric/date cells | Re-run renderers with new locale |
| Charts | Axis ticks, legends | Reformat labels from source numbers |
| Calendars | Month names, weekdays | Format according to locale |
| Documents | Previews, emails, exports | Use recipient/job locale |
| Accessibility | Accessible names, descriptions | Refresh screen-reader text |
| Text direction | LTR/RTL | Update orientation and isolation |
| Async | Late-arriving data | Version guard or re-render with current locale |

**Never just call `repaint()`:** the UI must **receive the new strings** before painting. `repaint` only draws existing text.

## 17. Example 3 — Self-Testing Resource Selection and Data Preservation

The test below needs no JUnit framework. Reuse `Messages_en.properties` and `Messages_vi.properties` from Example 1.

Create `LocaleSwitchSelfTest.java`:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocaleSwitchSelfTest {
    static void require(boolean ok, String detail) {
        if (!ok) {
            throw new AssertionError(detail);
        }
    }

    public static void main(String[] args) {
        Locale en = Locale.forLanguageTag("en-US");
        Locale vi = Locale.forLanguageTag("vi-VN");

        BigDecimal quantity = new BigDecimal("1234.50");
        LocalDate date = LocalDate.of(2025, 3, 5);

        ResourceBundle english =
                ResourceBundle.getBundle("Messages", en);
        ResourceBundle vietnamese =
                ResourceBundle.getBundle("Messages", vi);

        require(english.getString("date").equals("Date"),
                "Wrong en resource");
        require(vietnamese.getString("date").equals("Ngày"),
                "Wrong vi resource");

        NumberFormat enNumbers =
                NumberFormat.getNumberInstance(en);
        NumberFormat viNumbers =
                NumberFormat.getNumberInstance(vi);

        String enText = enNumbers.format(quantity);
        String viText = viNumbers.format(quantity);
        require(!enText.isEmpty() && !viText.isEmpty(),
                "Number rendering failed");

        DateTimeFormatter enDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG).withLocale(en);
        DateTimeFormatter viDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.LONG).withLocale(vi);

        require(!date.format(enDate).isEmpty(),
                "English date missing");
        require(!date.format(viDate).isEmpty(),
                "Vietnamese date missing");

        require(quantity.equals(new BigDecimal("1234.50")),
                "Quantity unexpectedly changed");
        require(date.equals(LocalDate.of(2025, 3, 5)),
                "Date unexpectedly changed");

        System.out.println("PASS: translations selected by locale");
        System.out.println("PASS: locale-specific formatting performed");
        System.out.println("PASS: typed domain data unchanged");
    }
}
~~~

Compile and run in the resources directory:

~~~bash
javac -encoding UTF-8 LocaleSwitchSelfTest.java
java -cp . LocaleSwitchSelfTest
~~~

Output:

~~~text
PASS: translations selected by locale
PASS: locale-specific formatting performed
PASS: typed domain data unchanged
~~~

The test focuses on **the contract**: right catalog, formatting per requested locale, unchanged domain data. It does not require date/number strings to share identical punctuation across every JDK/provider. If a product requires exact literal output, pin the JDK/CLDR version or test on the actual deployment environment.

## 18. End-to-End Test Matrix

| Scenario | How to test | Expected result |
| --- | --- | --- |
| Switch en → vi → en | Toggle repeatedly on the same screen | No leftover labels from previous locale |
| Formatting | One `BigDecimal` and `LocalDate` | Strings update, source values stay unchanged |
| Missing key | Remove a resource key in a test bundle | Explicit fallback or error per policy |
| Unsupported locale | Choose `fr-CA` when only en, vi exist | Never silently picks server language |
| User input | Type en number then switch to vi | Does not misparse or wipe field |
| Async race | Switch locale before response arrives | Never applies stale text |
| Multi-user | Run vi and en requests concurrently | Zero locale leakage |
| Currency | Order stored in USD | Remains USD after UI switch |
| Zone | Fixed Instant + time zone | Hours do not shift just from language switch |
| RTL | Switch to an RTL language | Layout/markup does not scramble URLs/numbers |
| Swing EDT | Change dropdown in UI | No component updates off the EDT |
| Build resources | Package `.properties` into JAR | `ResourceBundle` locates files properly |
| Java upgrades | Run across supported JDKs | CLDR differences are reviewed |

### Common Mistakes

- **`Locale.setDefault` per request:** creates races across users; pass `Locale` explicitly.
- **Updating state without re-rendering:** labels/tooltips stay stale; invalidate derived presentation.
- **Caching formatted number/date strings globally:** shows wrong separators; cache typed data or include locale in cache keys.
- **Keeping `MessageFormat` and calling only `setLocale`:** old subformats persist; recreate or call `applyPattern` properly.
- **Reusing mutable `NumberFormat` across requests:** risks races; instantiate per request.
- **Calling `ResourceBundle.clearCache` on every locale switch:** unnecessary when files have not changed.
- **Changing currency/zone when changing language:** alters transaction meaning; keep those decisions separate.
- **Reformatting uncommitted drafts:** loses data or flips separators; track the input's original locale.
- **Forgetting async notifications:** stale English overwrites new Vietnamese; guard with generation at commit time.
- **Ignoring accessibility text and layout:** leaves the UI only superficially translated.
- **Translating messages by concatenating fragments:** breaks grammar order; translate whole patterns.
- **Testing only English:** misses separator, RTL, inflected month names, and plural bugs.

## 19. Saving User Language for the Next Launch

Store a **BCP 47 language tag** instead of an arbitrary display string:

~~~java
Locale selected = Locale.forLanguageTag("vi-VN");
String stored = selected.toLanguageTag(); // vi-VN
Locale restored = Locale.forLanguageTag(stored);
~~~

This is a fragment inside a method requiring `import java.util.Locale`.

Sources may include account settings, cookies/sessions, local config, a window's temporary selection, or the initial request's `Accept-Language`. Define a **precedence order**: explicit user selection should generally override browser hints, while server defaults act only as a defined fallback.

`Locale.forLanguageTag` does not guarantee the application has complete resources for that locale. Always map to **tested supported locales**, with an explicit fallback or closest-match policy when translations are missing.

## 20. Practice Exercises

1. Add `Messages_de.properties` to the console demo and let the user cycle `en-US → de-DE → vi-VN`; verify `Order` stays untouched.
2. Add a percentage column and a USD price; distinguish display locale selection from currency unit and exchange rate.
3. Use `MessageFormatSwitchDemo` to explain why `setLocale` alone is not enough to update previously built subformats.
4. In the Swing demo, add a menu, tooltip, and validation error message; ensure visible items all refresh on language switch.
5. Build a form accepting `1,234.50` in `en-US` and switching to `vi-VN` mid-edit; design a policy that preserves meaning.
6. Write a test for two concurrent users, one using `vi-VN` and one using `en-US`, without a single `Locale.setDefault` call.
7. Simulate an HTTP task returning an `en-US` formatted string after the UI switched to `vi-VN`; use a generation guard to reject the stale result.
8. Test locale `ar-EG` to verify RTL direction, URL/email display, and layout.
9. Separate `uiLocale` and `formatLocale`: English UI, German number formatting; explain how to wire resources and formatters.
10. Remove a key from the Vietnamese bundle; define the fallback policy and how QA reports the gap.
11. Explain the difference between changing the selected locale and reloading a cached resource file.
12. When displayed dates or numbers change after a JDK upgrade, determine whether the cause lies in CLDR data, locale, or the business model.

## 21. Implementation Checklist

1. Store **locale in the right session/window/request state**, never mutating the JVM-wide default locale.
2. Keep typed data such as `BigDecimal`, `LocalDate`, `Instant`, and `Currency`; treat formatted strings as derived.
3. Select `ResourceBundle` for the new locale; define supported locales and fallbacks.
4. Select formatters for the new locale; account for mutability in `NumberFormat`/`MessageFormat`.
5. Re-render **all** locale-dependent components, not just primary labels.
6. Handle uncommitted forms carefully, preserving drafts and tracking the parsing locale.
7. Keep locale separate from time zone, currency, exchange rates, and measurement units.
8. Refresh accessibility text, orientation, and layout when RTL is needed.
9. Reject stale async results or format at commit time using the active locale.
10. Test repeated locale toggling, multi-user concurrency, missing resources, headless CI, and JDK versions.
11. Invalidate bundle caches only when **translation sources change**, not on every switch.
12. Persist a BCP 47 language tag to restore the user's choice.

**Key takeaway:** Switching language at runtime is a **presentation-state change**, not a mutation of source data. A new `Locale` never automatically updates existing `String`s or formatters. **Keep data typed → update locale context → reselect bundles/formatters → refresh UI → guard async results and in-progress inputs.** That is the foundation for multilingual Java applications that behave consistently without restarting.

### References

- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html) — BCP 47, default locale, and locale scoping.
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html) — resource lookup, fallback, and caching.
- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) — parameterized messages, locale, `applyPattern`.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) — numbers and currencies.
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) — dates/times and immutable formatters.
- [Java SE 17 — ComponentOrientation](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/ComponentOrientation.html) — component display direction.
- [Java SE 17 — SwingUtilities](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/swing/SwingUtilities.html) — Swing updates on the EDT.
