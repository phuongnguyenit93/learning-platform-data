# CustomNumberEditor, CustomBooleanEditor, and CustomDateEditor in Spring Data Binding

## 1. Big Picture: Why Are These Three PropertyEditors Needed?

An HTML form or query parameter typically sends values as strings: quantity is **"12"**, a toggle answer is **"Y"**, and a start date is **"29/02/2024"**. Yet the Java DTO declares types **Integer**, **Boolean**, and **java.util.Date**. Before assigning into the DTO, Spring must understand which Java value each string represents.

Three classes in package **org.springframework.beans.propertyeditors** solve three familiar conversion tasks:

- **CustomNumberEditor**: converts strings into a **Number** subclass such as **Integer**, **Long**, or **BigDecimal**, optionally using a custom **NumberFormat**.
- **CustomBooleanEditor**: converts strings representing true/false into **Boolean**, using default recognition rules or two custom strings.
- **CustomDateEditor**: converts date strings into **java.util.Date** based on an application-supplied **DateFormat**.

These are translators of *value representations*, not business validation annotations. They do not answer "is the order valid?" or "has this date passed?". They answer first: "can the received string be converted to the target type under these rules?".

Target example:

~~~text
Form input                         DTO after binding
--------------------------------------------------------------
quantity = "12"                 -> Integer quantity = 12
enabled  = "Y"                  -> Boolean enabled = true
startDate = "29/02/2024"        -> Date startDate = Feb 29, 2024
~~~

If data has wrong types like **quantity="twelve"**, **enabled="maybe"**, or **startDate="31/02/2025"**, the binder must report errors instead of inventing an "approximate" value.

**Article scope:** **PropertyEditor** group in topic **Spring Framework – validation-data-binding**. Focuses on the JavaBeans/Spring DataBinder mechanism, editor scope configuration, error handling, and limitations of using these traditional editors.

## 2. From Input String to Java Property: The PropertyEditor Mechanism

**java.beans.PropertyEditor** is an interface dating back to JavaBeans. Common methods include:

- **setAsText(String)**: receives text representation; the editor parses it and stores the internal Java value via **setValue(...)**.
- **getValue()**: returns the Java value currently held by the editor.
- **setValue(Object)**: places a Java value into the editor; some implementations may check or coerce the type.
- **getAsText()**: formats the held value into a string; useful when rendering data back into a form.

The editors in this article extend **PropertyEditorSupport**, the base implementation class provided by Java. Each editor holds internal state, so a single custom editor instance should not be shared across multiple threads/requests.

Conceptually, property binding proceeds as follows:

~~~text
HTTP form / MutablePropertyValues
          |
          v
DataBinder + BeanWrapper
          |
          +-- locate target property to assign
          +-- inspect Java type of the property
          +-- apply matching PropertyEditor/ConversionService
          |      |
          |      +-- setAsText("12") -> getValue() is Integer 12
          |      +-- if parse fails -> record binding error
          |
          v
Invoke setter or configured property access mechanism
          |
          v
BindingResult: type conversion errors, suppressed fields, etc.
          |
          v
Validator runs if explicitly triggered by the application
~~~

The diagram is a conceptual model for understanding responsibilities. Spring also has **ConversionService** and **Formatter**; a custom editor registered for the right type/path participates in conversion when the binder needs it. Do not assume every string across every HTTP path passes through the same editor.

In Spring MVC, a **WebDataBinder** binds data for model attributes following the mechanism inherited from **DataBinder**. With **@RequestBody** JSON, Jackson/HttpMessageConverter normally reads and deserializes JSON; registering editors via **@InitBinder** does not automatically transform every JSON field before Jackson.

## 3. Quick Comparison of the Three Editors

| Editor | Target type | Key configuration | Example value | Notes |
| --- | --- | --- | --- | --- |
| **CustomNumberEditor** | **Number** subclass: Integer, Long, Double, BigDecimal... | **numberClass**, optional **NumberFormat**, **allowEmpty** | "12" -> Integer 12 | Choose exact target type and format/Locale |
| **CustomBooleanEditor** | **Boolean** or matching usage for boolean | optional **trueString**, **falseString**, **allowEmpty** | "Y" -> true | Must define accepted string set |
| **CustomDateEditor** | **java.util.Date** | **DateFormat**, **allowEmpty**, optional **exactDateLength** | "29/02/2024" -> Date | DateFormat, time zone, and strictness must be controlled |

All three can convert empty strings to **null** when configured with **allowEmpty=true**. **null** only makes sense when the target property can hold null; primitive types like **int** or **boolean** cannot represent null. **allowEmpty=true** also does not automatically make a field optional in business terms: check **@NotNull**, **@NotBlank**, or domain logic.

Spring includes built-in number and Boolean editors in **BeanWrapperImpl**'s defaults, yet applications can still register custom variants to alter formatting or accepted values. **CustomDateEditor is not registered automatically by default** because no single date format fits every application; when needed, register it with an explicit format.

## 4. CustomNumberEditor: Controlling Number Type and Format

Typical constructors:

~~~java
new CustomNumberEditor(Integer.class, false);

new CustomNumberEditor(
        java.math.BigDecimal.class,
        java.text.NumberFormat.getNumberInstance(java.util.Locale.US),
        true);
~~~

The two calls above are configuration illustrations, not a standalone program.

The first form uses Spring's standard number parsing; the second adds a **NumberFormat** for text formatted per **Locale.US**. **allowEmpty=false** rejects empty strings instead of returning null; **allowEmpty=true** permits them. **numberClass** must be a **Number** subclass (such as **Integer.class**, not **int.class**).

What CustomNumberEditor does:

1. Receives the string passed into **setAsText(...)**.
2. If empty and allowed, sets value to **null**; if disallowed, reports an error.
3. If a **NumberFormat** is provided, uses that format to parse; otherwise uses standard number parsing.
4. Converts/coerces the result to the declared **Number** class if appropriate and stores the value for the binder to assign to the property.
5. When formatting back to text, **getAsText()** can apply the provided **NumberFormat** or standard number rendering.

Do not use **CustomNumberEditor(Integer.class, ...)** to directly bind a value into a **BigDecimal** property; editor type and target type must match. For monetary values, prefer **BigDecimal** over **Double** when decimal precision matters.

### Locale and separators

For example, **"1,234.50"** can mean something different from **"1.234,50"** depending on Locale. If an application expects formatted numbers with separators, declare the expected Locale and configure **NumberFormat** explicitly. Do not strip all commas/dots to "rescue" inputs, as that can corrupt the numeric value.

**NumberFormat can parse more loosely than strict input rules.** If an API requires the entire string to adhere strictly to a pattern, add syntax and length checks on the input string or use a specialized strict full-string parser. **CustomNumberEditor** does not replace numeric range checks, domain bounds, or authorization.

## 5. CustomBooleanEditor: Mapping Strings to Boolean

Common constructors:

~~~java
new CustomBooleanEditor(true);
new CustomBooleanEditor("Y", "N", true);
new CustomBooleanEditor("enabled", "disabled", false);
~~~

With the **CustomBooleanEditor(boolean allowEmpty)** constructor, strings are recognized using Spring's default rules, case-insensitively for words:

| Representation | Boolean value |
| --- | --- |
| "true", "on", "yes", "1" | true |
| "false", "off", "no", "0" | false |
| Empty string, allowEmpty=true | null |
| "maybe" | Cannot convert |

When specifying both **trueString** and **falseString** such as **"Y"** and **"N"**, the editor prioritizes those exact labels for each value; do not assume all default variants like **"yes"** remain accepted. Label matching follows the editor's case-insensitive comparison logic. Do not collapse all unrecognized strings into **false**, as invalid data would silently be interpreted as a user decision.

**Boolean** is a wrapper with three possible states: **true**, **false**, **null**. Primitive **boolean** has only **true/false**. An unchecked checkbox omitted from a form is not identical to an explicit **"N"** value; **WebDataBinder** also has a field marker mechanism for form checkboxes. Define the input contract and test "omitted", "empty string sent", and "N sent" separately.

If business rules need to distinguish **unselected** from **explicitly false**, use **Boolean** and an appropriate empty-value policy. If the user is required to make a choice, a constraint like **@NotNull** can validate after binding succeeds.

## 6. CustomDateEditor: Parsing java.util.Date by Specific Format

Constructors:

~~~java
new CustomDateEditor(dateFormat, false);
new CustomDateEditor(dateFormat, false, 10);
~~~

Where **dateFormat** is a valid **java.text.DateFormat** object, for example:

~~~java
java.text.SimpleDateFormat format =
        new java.text.SimpleDateFormat(
                "dd/MM/yyyy", java.util.Locale.ROOT);

format.setLenient(false);
format.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
~~~

This is a configuration excerpt, not a standalone program. For **"29/02/2024"**, the Gregorian calendar accepts the leap day; for **"31/02/2025"**, **setLenient(false)** requires rejecting a nonexistent date rather than rolling over into the next month.

**allowEmpty** handles empty strings as null or error, just like the previous two editors. **exactDateLength=10** adds text length validation, helpful because **SimpleDateFormat** has some non-strict parsing behaviors even with **setLenient(false)**. However, checking length alone does not guarantee every position, digit, and separator matches the pattern: if an API demands exact **dd/MM/yyyy**, test strict formatting and consider **java.time.DateTimeFormatter** in strict mode for new business logic.

**DateFormat/SimpleDateFormat is stateful and unsafe to share arbitrarily across threads.** In web applications, create a fresh formatter and editor per binder or use appropriate modern formatter mechanisms. Never share one **CustomDateEditor** instance as a singleton across multiple requests.

Important distinction: **CustomDateEditor** handles **java.util.Date**, meaning an instant represented by milliseconds since the epoch. If the data represents a **calendar date without time/time zone**, the better domain type is usually **java.time.LocalDate**. For LocalDate, use **@DateTimeFormat** or a Formatter/Converter for **java.time**; do not register CustomDateEditor and expect it to apply to LocalDate.

## 7. Complete Java 17+ Example: Three Editors in One DataBinder

This example uses **Java 17** and **Spring Framework 6.2.15** to reproduce binding onto a JavaBean. Input is constructed in-memory; there is no HTTP server. We intentionally configure editors per property using **registerCustomEditor(type, propertyPath, editor)** to avoid affecting unrelated properties of the same type.

Structure:

~~~text
spring-property-editor-demo/
├── pom.xml
└── src/main/java/demo/PropertyEditorsDemo.java
~~~

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-property-editor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.15</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.PropertyEditorsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/PropertyEditorsDemo.java:**

~~~java
package demo;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.propertyeditors.CustomBooleanEditor;
import org.springframework.beans.propertyeditors.CustomDateEditor;
import org.springframework.beans.propertyeditors.CustomNumberEditor;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class PropertyEditorsDemo {

    public static void main(String[] args) {
        show("OK", "12", "Y", "29/02/2024");
        show("OPTIONAL_BLANK", "12", "", "29/02/2024");
        show("INVALID", "twelve", "maybe", "31/02/2025");
    }

    private static void show(
            String label, String quantityText,
            String enabledText, String dateText) {

        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form, "registrationForm");

        binder.setAllowedFields("quantity", "enabled", "startDate");

        // An editor for Integer (quantity is required at the parse step).
        binder.registerCustomEditor(
                Integer.class, "quantity",
                new CustomNumberEditor(Integer.class, false));

        // Y = true; N = false; empty string = null.
        binder.registerCustomEditor(
                Boolean.class, "enabled",
                new CustomBooleanEditor("Y", "N", true));

        // Create a new DateFormat per binder; never share across requests.
        SimpleDateFormat inputFormat =
                new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
        inputFormat.setLenient(false);
        inputFormat.setTimeZone(TimeZone.getTimeZone("UTC"));

        binder.registerCustomEditor(
                Date.class, "startDate",
                new CustomDateEditor(inputFormat, false, 10));

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("quantity", quantityText);
        values.add("enabled", enabledText);
        values.add("startDate", dateText);

        binder.bind(values);
        BindingResult errors = binder.getBindingResult();

        SimpleDateFormat outputFormat =
                new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
        outputFormat.setTimeZone(TimeZone.getTimeZone("UTC"));

        String date = form.getStartDate() == null
                ? "null"
                : outputFormat.format(form.getStartDate());

        System.out.println("[" + label + "]");
        System.out.println("quantity=" + form.getQuantity());
        System.out.println("enabled=" + form.getEnabled());
        System.out.println("startDate=" + date);
        System.out.println("hasErrors=" + errors.hasErrors());

        if (errors.hasErrors()) {
            System.out.println(
                    "quantity.error=" + errors.hasFieldErrors("quantity"));
            System.out.println(
                    "enabled.error=" + errors.hasFieldErrors("enabled"));
            System.out.println(
                    "startDate.error=" + errors.hasFieldErrors("startDate"));
        }
    }

    public static final class RegistrationForm {
        private Integer quantity;
        private Boolean enabled;
        private Date startDate;

        public RegistrationForm() {
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public Boolean getEnabled() {
            return enabled;
        }

        public void setEnabled(Boolean enabled) {
            this.enabled = enabled;
        }

        public Date getStartDate() {
            return startDate;
        }

        public void setStartDate(Date startDate) {
            this.startDate = startDate;
        }
    }
}
~~~

Run in the directory containing **pom.xml**:

~~~bash
mvn -q compile exec:java
~~~

Requires JDK 17+ and Maven; Maven Central access is needed on first run. Expected program output (excluding Maven logs):

~~~text
[OK]
quantity=12
enabled=true
startDate=2024-02-29
hasErrors=false
[OPTIONAL_BLANK]
quantity=12
enabled=null
startDate=2024-02-29
hasErrors=false
[INVALID]
quantity=null
enabled=null
startDate=null
hasErrors=true
quantity.error=true
enabled.error=true
startDate.error=true
~~~

### Explanation of each case

**OK:** **"12"** converts to **Integer 12**; **"Y"** becomes **Boolean.TRUE**; **"29/02/2024"** becomes a valid Date. When printing, the program uses UTC and format **yyyy-MM-dd**, so the date output does not depend on the machine's default time zone. **BindingResult** has no errors.

**OPTIONAL_BLANK:** same valid number/date, while **enabled** is an empty string. **CustomBooleanEditor("Y","N",true)** interprets it as **null**, so **hasErrors=false**. If business rules require a selection, a validator or constraint is needed to reject null after binding.

**INVALID:** all three strings fail the configured rules: **"twelve"** cannot become an Integer; **"maybe"** is not in the Y/N set; **31/02/2025** is a nonexistent date rejected by the non-lenient formatter. The binder records field errors; fields on the newly created DTO retain their default null values. Never "auto-fix" invalid data into a seemingly valid value.

The example uses **setAllowedFields(...)** to permit only the three declared properties to receive input. Restricting to declared fields matters even when editors can convert many types: successful conversion does not mean the user is allowed to modify every property.

### When a field fails conversion, how are errors identified?

~~~java
for (org.springframework.validation.FieldError error
        : errors.getFieldErrors()) {
    System.out.println(error.getField()
            + ": bindingFailure=" + error.isBindingFailure());
}
~~~

This snippet **depends on the errors variable in the main example** and does not run standalone. For conversion failures recorded by DataBinder, **FieldError.isBindingFailure()** indicates an error during the binding phase. **@Valid**, **@NotNull**, **@Min**, or other constraints must be triggered separately; a **FieldError** from type conversion is not automatically a Bean Validation error.

## 8. Registering in Spring MVC with @InitBinder

In a controller receiving **@ModelAttribute("registrationForm")**, editors can be registered before Spring binds the request:

~~~java
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

import org.springframework.beans.propertyeditors.CustomBooleanEditor;
import org.springframework.beans.propertyeditors.CustomDateEditor;
import org.springframework.beans.propertyeditors.CustomNumberEditor;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

// Place this method inside an appropriate @Controller or @ControllerAdvice:
@InitBinder("registrationForm")
public void configureRegistration(WebDataBinder binder) {
    binder.registerCustomEditor(
            Integer.class, "quantity",
            new CustomNumberEditor(Integer.class, false));

    binder.registerCustomEditor(
            Boolean.class, "enabled",
            new CustomBooleanEditor("Y", "N", true));

    SimpleDateFormat dateFormat =
            new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
    dateFormat.setLenient(false);
    dateFormat.setTimeZone(TimeZone.getTimeZone("UTC"));

    binder.registerCustomEditor(
            Date.class, "startDate",
            new CustomDateEditor(dateFormat, false, 10));

    binder.setAllowedFields("quantity", "enabled", "startDate");
}
~~~

The **@InitBinder** snippet is Spring MVC integration code, which must reside inside an appropriate controller or advice class; by itself it is not a program with **main**. The name **registrationForm** must match the model attribute name. In MVC, a WebDataBinder is normally created per binding pass, so we instantiate a fresh DateFormat/editor inside this method rather than keeping a shared SimpleDateFormat object.

Example controller consuming the form:

~~~java
@PostMapping("/registration")
public String save(
        @Valid @ModelAttribute("registrationForm")
        RegistrationForm input,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration-form";
    }
    return "registration-success";
}
~~~

This is also an integration snippet, requiring annotation imports, DTO class, validation provider, corresponding views, and actual constraints to evaluate. **BindingResult** must appear immediately after the **@ModelAttribute** argument it describes. If input has the wrong type, the error typically carries code **typeMismatch**; if type conversion succeeds yet constraints fail, Bean Validation (when enabled) produces separate constraint errors.

**Registering by field or by type?**

- **registerCustomEditor(Integer.class, "quantity", editor)**: scoped specifically to **quantity**.
- **registerCustomEditor(Integer.class, editor)**: applies across type **Integer** within the binder's scope, which is broader.
- **registerCustomEditor(Date.class, "startDate", editor)**: ensures the date format applies exclusively to **startDate** without forcing all Dates into one pattern by default.

Prefer narrow scope when properties of the same type have different input conventions; at the same time, avoid letting an editor silently affect unrelated forms/models.

## 9. Distinguishing PropertyEditor from ConversionService, Formatter, and JSON

| Problem | Mechanism to consider | Why |
| --- | --- | --- |
| Convert form String -> Integer/Boolean/Date under legacy rules | **CustomNumberEditor**, **CustomBooleanEditor**, **CustomDateEditor** | Exact role of JavaBeans PropertyEditors |
| Convert custom domain types across multiple application layers | **Converter<S,T>** in **ConversionService** | Enables reusable conversion rules independent of editor state |
| Format/parse numbers and dates by Locale in UI | **Formatter<T>**, Spring **FormattingConversionService** | Two-way formatting model with locale context |
| DTO uses LocalDate, LocalDateTime | **@DateTimeFormat**, Formatter/Converter for **java.time** | Modern date/time types are not java.util.Date |
| JSON @RequestBody | **Jackson** via **HttpMessageConverter** | JSON is read/deserialized before validation; @InitBinder is not a JSON deserializer |
| Validate values after conversion | **Bean Validation**, **Validator** | Constraints such as minimum age, domain syntax, valid date ranges |

There is no rule saying "use only PropertyEditor" or "always discard PropertyEditor". In modern codebases, **Converter/Formatter** are usually more convenient for reusable conversions and Locale-based formatting; editors remain useful for understanding legacy systems and certain specialized DataBinder configurations.

### Notes on format safety

- **NumberFormat** is not a validator guaranteeing the string contains solely the declared characters; add strict checks if the input contract demands them.
- **SimpleDateFormat** is unsafe when sharing a mutable instance across threads. Create a fresh one per binder or move to appropriate modern date/time APIs.
- **Exact date length** is only an extra check; it does not replace **setLenient(false)** or a full strict parser.
- Values **null**, **""**, whitespace-only strings, and *omitted fields* can carry distinct business meanings.
- Accepting **"Y"/"N"** may suit legacy forms yet does not automatically apply cleanly to standard JSON booleans.
- Avoid writing sensitive raw inputs to logs or returning raw parser exceptions to clients. APIs should use clear error codes and contract messages.

## 10. How to Inspect and Handle Conversion Errors

When a form fails to bind, ask in order:

1. **What is the Java property type?** Integer or int, Boolean or boolean, Date or LocalDate?
2. **What is the actual input data?** Does query/form send "12", "Y", "29/02/2024", or another representation?
3. **Which editors are registered, and at what scope?** By type or by property path? Does the **@InitBinder** method target the right model attribute name?
4. **Is allowEmpty appropriate?** Should an empty string become null or be rejected?
5. **Does the formatter have the right Locale/TimeZone/lenient settings?** Do leap days, nonexistent dates, day/month order, and separators match?
6. **What errors did BindingResult record?** Check **hasErrors()**, **getFieldErrors("field")**, **FieldError.isBindingFailure()**, and code **typeMismatch** when present.
7. **Has validation run?** Successful conversion does not guarantee constraints like **@Min(1)** or **@NotNull** were checked.

An API can return a structured error like this (illustrative JSON, not the default output of the Java example):

~~~json
{
  "code": "TYPE_MISMATCH",
  "field": "startDate",
  "message": "Date must be in dd/MM/yyyy format and be a valid calendar date."
}
~~~

When a form has multiple errors, collect field-level errors and report them per input location; do not collapse all failures into a vague message like "Invalid data". At the same time, avoid exposing stack traces or internal parser details inappropriate for end users.

## 11. Common Misconceptions

1. **CustomNumberEditor is a numeric validator.** False: it primarily parses/converts representations. Business bounds like quantity greater than 0 still require separate constraints.
2. **CustomBooleanEditor accepts only "true"/"false".** False under Spring's defaults; and applications can also define custom labels like Y/N.
3. **Unrecognized strings automatically become false.** False: data not matching accepted values must trigger a conversion error.
4. **allowEmpty=true guarantees the field is valid.** False: it permits null; business rules may still require a value.
5. **CustomDateEditor accepts every date of the same length.** False: it requires a valid DateFormat, valid calendar date, and appropriate parse mode.
6. **setLenient(false) alone enforces every format character strictly.** False: SimpleDateFormat has parsing quirks that require extra verification.
7. **One DateFormat can be stored as a singleton for all requests.** Unsafe for stateful SimpleDateFormat.
8. **CustomDateEditor automatically applies to LocalDate.** False: it targets java.util.Date, whereas LocalDate uses different conversion mechanisms.
9. **@InitBinder definitely converts @RequestBody JSON.** False: JSON normally goes through Jackson/HttpMessageConverter.
10. **Registering an editor by type does not affect other fields.** It can affect every property of that type in the binder; use property paths when distinct formatting is needed.
11. **If there are no binding errors, validation is unnecessary.** False: a validly converted value can still violate business rules.
12. **Converting a value means the client has permission to write that property.** False: input DTOs, field allowlists, and authorization checks are still required.

## 12. Practice Exercises

**Exercise 1 — Boolean with a different protocol.** Change the editor to **CustomBooleanEditor("enabled","disabled",false)**. Try submitting **"enabled"**, **"disabled"**, **""**, **"Y"**. Classify each case as true, false, or parse error. Explain the effect of **allowEmpty=false**.

**Exercise 2 — Locale-aware numbers.** Add **BigDecimal amount** to the DTO and register **CustomNumberEditor(BigDecimal.class, numberFormat, true)** with a specific NumberFormat. Compare comma and dot inputs. Determine how to strictly validate the entire string when the API format requires it.

**Exercise 3 — Leap days.** Using the date editor configuration from section 7, test **29/02/2024**, **29/02/2025**, **31/04/2025**, and **01/01/2025**. Explain why **setLenient(false)** matters.

**Exercise 4 — Migrating from Date to LocalDate.** Change the **startDate** field to **LocalDate**. Explain why **@DateTimeFormat** or a dedicated LocalDate formatter is needed instead of keeping the Date editor.

**Exercise 5 — BindingResult.** With invalid inputs across all three fields simultaneously, extract field name, error code, and **isBindingFailure()**. Design an error JSON payload listing each field without leaking sensitive raw input.

## 13. References

- [Spring Framework – Data Binding and PropertyEditors](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html).
- [CustomNumberEditor – Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/propertyeditors/CustomNumberEditor.html).
- [CustomBooleanEditor – Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0-M4/javadoc-api/org/springframework/beans/propertyeditors/CustomBooleanEditor.html).
- [CustomDateEditor – Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/beans/propertyeditors/CustomDateEditor.html).
- [Web MVC – @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html).
- [ConversionService and Spring Formatter](https://docs.spring.io/spring-framework/reference/core/validation/convert.html).

**Rule of practice:** identify the exact Java target type, format, and empty-value policy; register editors in the required scope; inspect errors via BindingResult; only then apply validation and authorization checks. CustomNumberEditor, CustomBooleanEditor, and CustomDateEditor help Spring interpret input representations, rather than replacing business rules.