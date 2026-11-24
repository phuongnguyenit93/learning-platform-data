# hasErrors, hasFieldErrors, getFieldErrors, and getGlobalErrors in Spring

## 1. Context: An Object Can Have Multiple Kinds of Errors

When Spring receives a form, converts types, and validates data, the outcome is not merely "valid" or "invalid". An input object can contain:

- **Field errors:** related to a specific property, such as an empty **email**, **quantity** less than 1, or the string **"abc"** failing to convert to **Integer**.
- **Global/object errors:** related to a rule applying to the whole object, often coordinating multiple properties, such as **startDay** being greater than **endDay**. This error is not necessarily attached to a single field.
- **Both at once:** a form that is both missing a name and has an invalid date range.

Spring provides the **org.springframework.validation.Errors** interface to record and query those errors. **BindingResult** extends **Errors**, adding details about the data-binding process. In Spring MVC, a properly placed **BindingResult** argument lets the controller handle binding and validation results for a model attribute.

Four central methods in this article:

1. **hasErrors()** — are there *any* errors?
2. **hasFieldErrors()** / **hasFieldErrors(String field)** — are there any field errors, or does a specific field have errors?
3. **getFieldErrors()** / **getFieldErrors(String field)** — retrieve the list of field errors.
4. **getGlobalErrors()** — retrieve the list of object-wide errors.

These methods **only read errors already recorded on the current Errors object**. They do not run converters, check annotations, query errors elsewhere, or modify data on their own.

## 2. Exact Comparison of the Four Methods

| API | Return type | Scope examined | When to use |
| --- | --- | --- | --- |
| **hasErrors()** | boolean | All errors (field **and** global) | Deciding whether to proceed or re-render the form with errors |
| **hasFieldErrors()** | boolean | All field-level errors | Checking whether at least one property is invalid |
| **hasFieldErrors("email")** | boolean | Errors on the **email** field | Showing error state next to an input box |
| **getFieldErrors()** | List<FieldError> | All field errors, across all properties | Building a detailed per-field error list |
| **getFieldErrors("email")** | List<FieldError> | Errors attached to the **email** field | Displaying multiple messages for the same field |
| **getGlobalErrors()** | List<ObjectError> | Object-wide errors only | Displaying messages for cross-field or form-wide rules |

**Key point:** **hasErrors() == true** does not imply **hasFieldErrors() == true**. A single object-wide error is enough for **hasErrors()** to return **true**.

**getFieldErrors()** and **getGlobalErrors()** are always disjoint in scope: **getFieldErrors()** excludes global errors; **getGlobalErrors()** never returns **FieldError** instances recorded for a specific field.

For supporting APIs, **hasGlobalErrors()** checks for global errors, **getGlobalError()** returns the first global error (or null), **getFieldError("email")** returns the first error for a field (or null), **getAllErrors()** returns both groups as **List<ObjectError>**, and **getErrorCount()** counts all errors.

### Truth table for error combinations

| State of Errors | hasErrors() | hasFieldErrors() | getFieldErrors().size() | getGlobalErrors().size() |
| --- | --- | --- | --- | --- |
| No errors | false | false | 0 | 0 |
| Only 2 field errors | true | true | 2 | 0 |
| Only 1 global error | true | false | 0 | 1 |
| 2 field errors + 1 global error | true | true | 2 | 1 |

The counts in the table are examples; one field can have multiple **FieldError** instances and one object can have multiple **ObjectError** instances. Never assume each field has at most one error.

## 3. How Are Field Errors and Global Errors Created?

**Errors.rejectValue(field, code, message)** records an error attached to a property name. Example:

~~~java
errors.rejectValue("customerName", "required", "Customer name is required");
errors.rejectValue("quantity", "positive", "Quantity must be positive");
~~~

**Errors.reject(code, message)** records an object-level error, for example:

~~~java
errors.reject("date.order", "Start day must not exceed end day");
~~~

These are illustrative statements inside a **Validator** or code block that already holds an **Errors** instance; they are not standalone programs. **code** is the error code used in message resolution (MessageSource/MessageCodesResolver), while **message** is the default message. When reading an error via **getCode()**, you may encounter codes expanded with object/field names, so do not build APIs assuming **getCode()** always equals the exact short string passed to **rejectValue**.

**Binding errors:** when DataBinder cannot assign a raw value to the Java type (such as **age=abc** for an **Integer age** property), **BindingResult** can also contain a **FieldError** typically coded **typeMismatch** with **isBindingFailure() == true**. Because this is a property error, **hasFieldErrors()** and **getFieldErrors()** include it even though it is not a Bean Validation error.

**Bean Validation errors:** constraints like **@NotBlank**, **@Min**, and **@NotNull** (when the validator is triggered) usually create field errors when placed on properties. Class-level constraints can create global errors when the violation path targets the object level; custom validators can also call **rejectValue** to attach errors to a specific field. Therefore, inspect **where the error is actually recorded**, rather than inferring mechanically from the annotation name.

Regarding Java types:

- **FieldError** extends **ObjectError** and adds **getField()**, **getRejectedValue()**, and **isBindingFailure()**.
- **ObjectError** represents an object-level error and provides **getObjectName()**, **getCode()**, **getCodes()**, and **getDefaultMessage()**.
- **Errors** and **BindingResult** represent errors for **a chosen target object**, not an aggregator of every error across the entire request or application.

## 4. Runnable Java 17+ Example: Three Error States

The following example uses **Spring Framework 6.2.18** and Java 17+. It constructs three order objects, invokes a validator via **DataBinder**, and uses all four APIs to distinguish field errors from object-wide errors.

Directory structure:

~~~text
errors-methods-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ErrorsMethodsDemo.java
~~~

Create **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>errors-methods-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
                    <mainClass>demo.ErrorsMethodsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Create **src/main/java/demo/ErrorsMethodsDemo.java**:

~~~java
package demo;

import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.Validator;

public final class ErrorsMethodsDemo {

    public static void main(String[] args) {
        show("MIXED", new OrderForm(" ", 0, 9, 7));
        show("GLOBAL_ONLY", new OrderForm("Mai", 2, 9, 7));
        show("VALID", new OrderForm("Mai", 2, 5, 7));
    }

    private static void show(String title, OrderForm form) {
        DataBinder binder = new DataBinder(form, "orderForm");
        binder.setValidator(new OrderValidator());
        binder.validate();

        // BindingResult extends Errors: all target methods
        // can be called through the Errors interface.
        Errors errors = binder.getBindingResult();

        System.out.println("[" + title + "]");
        System.out.println("hasErrors=" + errors.hasErrors());
        System.out.println("hasFieldErrors=" + errors.hasFieldErrors());
        System.out.println("hasFieldErrors(customerName)="
                + errors.hasFieldErrors("customerName"));
        System.out.println("hasFieldErrors(startDay)="
                + errors.hasFieldErrors("startDay"));
        System.out.println("getFieldErrors().size="
                + errors.getFieldErrors().size());
        System.out.println("getFieldErrors(customerName).size="
                + errors.getFieldErrors("customerName").size());
        System.out.println("getGlobalErrors().size="
                + errors.getGlobalErrors().size());

        for (FieldError error : errors.getFieldErrors()) {
            System.out.println("FIELD " + error.getField()
                    + ": " + error.getDefaultMessage());
        }
        for (ObjectError error : errors.getGlobalErrors()) {
            System.out.println("GLOBAL: " + error.getDefaultMessage());
        }
    }

    public static final class OrderForm {
        private String customerName;
        private Integer quantity;
        private int startDay;
        private int endDay;

        public OrderForm(String customerName, Integer quantity,
                         int startDay, int endDay) {
            this.customerName = customerName;
            this.quantity = quantity;
            this.startDay = startDay;
            this.endDay = endDay;
        }

        public String getCustomerName() {
            return customerName;
        }

        public void setCustomerName(String customerName) {
            this.customerName = customerName;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public int getStartDay() {
            return startDay;
        }

        public void setStartDay(int startDay) {
            this.startDay = startDay;
        }

        public int getEndDay() {
            return endDay;
        }

        public void setEndDay(int endDay) {
            this.endDay = endDay;
        }
    }

    private static final class OrderValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return OrderForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            OrderForm form = (OrderForm) target;

            if (form.getCustomerName() == null
                    || form.getCustomerName().isBlank()) {
                errors.rejectValue("customerName", "required",
                        "Customer name is required");
            }

            if (form.getQuantity() == null
                    || form.getQuantity() < 1) {
                errors.rejectValue("quantity", "positive",
                        "Quantity must be positive");
            }

            if (form.getStartDay() > form.getEndDay()) {
                errors.reject("date.order",
                        "Start day must not exceed end day");
            }
        }
    }
}
~~~

In the directory containing **pom.xml**, run (requires Maven and JDK 17+, plus dependency download permissions on the first run):

~~~bash
mvn -q compile exec:java
~~~

Expected output, **excluding Maven logs if your environment enables extra logging**:

~~~text
[MIXED]
hasErrors=true
hasFieldErrors=true
hasFieldErrors(customerName)=true
hasFieldErrors(startDay)=false
getFieldErrors().size=2
getFieldErrors(customerName).size=1
getGlobalErrors().size=1
FIELD customerName: Customer name is required
FIELD quantity: Quantity must be positive
GLOBAL: Start day must not exceed end day
[GLOBAL_ONLY]
hasErrors=true
hasFieldErrors=false
hasFieldErrors(customerName)=false
hasFieldErrors(startDay)=false
getFieldErrors().size=0
getFieldErrors(customerName).size=0
getGlobalErrors().size=1
GLOBAL: Start day must not exceed end day
[VALID]
hasErrors=false
hasFieldErrors=false
hasFieldErrors(customerName)=false
hasFieldErrors(startDay)=false
getFieldErrors().size=0
getFieldErrors(customerName).size=0
getGlobalErrors().size=0
~~~

**Explaining each state:**

- **MIXED:** blank **customerName** and **quantity** equal to 0 produce two **FieldError** records via **rejectValue**. **startDay=9, endDay=7** violates the cross-field relationship, producing one **ObjectError** via **reject**. Hence **hasErrors()** and **hasFieldErrors()** are both true, the field list has 2 items, and the global list has 1 item.
- **GLOBAL_ONLY:** name and quantity are valid, but the date range is still wrong. **hasErrors()** is true even though **hasFieldErrors()** is false. This explains why checking only **hasFieldErrors()** misses errors that must be displayed.
- **VALID:** no errors in any group. All counts are 0 and all checks are false.
- In **MIXED**, **hasFieldErrors("startDay")** is false even though the start day contributed to the failure. Reason: the validator used **reject(...)** for the cross-field rule, so the error sits in the **global** group, not as a **FieldError** on startDay.

The sample explicitly calls **binder.validate()**. It does not use HTTP or string value binding, because the focus is on error-reading APIs; when a real application receives requests, type-conversion errors can also be recorded in the same **BindingResult**.

## 5. Applying to Spring MVC

In a form-receiving Spring MVC controller, place **BindingResult** immediately after the **@ModelAttribute** parameter being validated:

~~~java
// Snippet inside @Controller/@RestController of a Spring MVC application;
// requires OrderRequest, @Valid, and appropriate imports.
@PostMapping("/orders")
public String submit(
        @Valid @ModelAttribute("orderRequest") OrderRequest request,
        BindingResult result) {

    if (result.hasErrors()) {
        // May contain FieldError, ObjectError, or both.
        for (FieldError fieldError : result.getFieldErrors()) {
            String field = fieldError.getField();
            String message = fieldError.getDefaultMessage();
            // Convert into an appropriate message for the right field.
        }

        for (ObjectError globalError : result.getGlobalErrors()) {
            String message = globalError.getDefaultMessage();
            // Display in the general form message section.
        }

        return "orders/form";
    }

    return "orders/success";
}
~~~

This is an **integration snippet**, not a standalone compilable controller: it requires an **OrderRequest** class, corresponding views, imports, validators, and cross-field constraints if global errors are actually expected. **@Valid** activates Bean Validation in a supported context; it does not automatically generate object-wide errors just because a form has multiple fields.

A common conditional pattern:

~~~java
if (result.hasErrors()) {
    if (result.hasFieldErrors("email")) {
        // Display error next to the email input.
    }
    if (!result.getGlobalErrors().isEmpty()) {
        // Display general error for the whole form.
    }
    return "form";
}
~~~

Why should **hasErrors()** be the outer guard? Because a branch with only global errors must still halt further processing. A production application also needs error-code categorization, localization, context handling, and output filtering rather than exposing raw internal messages directly to APIs.

**Parameter order note:** in Spring MVC, an **Errors/BindingResult** capturing errors for a model parameter must sit **immediately after** that parameter. If misplaced or omitted, Spring may handle/propagate errors via exceptions instead of letting the controller read them as shown above. Never inspect object A's **BindingResult** to decide whether object B has errors.

## 6. Reading and Presenting Error Lists Properly

### 6.1. getFieldErrors() vs getFieldErrors("field")

**getFieldErrors()** retrieves all field errors on the current target. A field can appear multiple times if it fails multiple constraints; do not treat the list size as the number of invalid fields.

**getFieldErrors("email")** retrieves only errors attached to the **email** field. If there are no matching errors, the list is empty, so you can iterate safely without null checks. Standard Spring implementations can support nested field names or field patterns, though when rendering a specific input control you should prefer known property names such as **address.street**.

For example, if there are 3 **FieldError** items distributed as 2 errors on email and 1 error on age:

~~~text
getFieldErrors().size()          = 3
getFieldErrors("email").size()   = 2
getFieldErrors("age").size()     = 1
hasFieldErrors("phone")          = false
~~~

These numbers are a hypothetical illustration, not additional output from the program in Section 4.

If you only want the first error per field to keep the UI compact, use **getFieldError("email")**, while handling the possibility of **null**. Use **getFieldErrors("email")** when you want users to see every violation related to that field.

### 6.2. getGlobalErrors() is for form-level messages

An object-wide error can come from cross-field rules like "end date must be after start date", "at least one contact method must be provided", or errors recorded via **Errors.reject(...)**.

**getGlobalErrors()** returns **List<ObjectError>** and does not automatically convert these into **FieldError** instances. If UX requirements call for highlighting both date inputs, UI code needs an explicit mapping from the object-level error code to the related fields, or the validator must record field-specific errors with **rejectValue**. Do not assume **hasFieldErrors("startDay")** will be true when only a global error exists.

To combine all errors into one list, **getAllErrors()** returns a list containing both **ObjectError** and **FieldError**. When you need two separate display areas, it is still better to use **getFieldErrors()** and **getGlobalErrors()** directly.

### 6.3. Combining with BindingResult type-conversion errors

When a form submits **quantity=abc** for a Java property **Integer quantity**, the binder can record a **FieldError** due to **typeMismatch**. Example:

~~~java
for (FieldError error : bindingResult.getFieldErrors("quantity")) {
    if (error.isBindingFailure()) {
        // Submitted value could not be converted/assigned to the target type.
    } else {
        // Constraint/validation error on the field, depending on the error source.
    }
}
~~~

This snippet illustrates code in an environment that already has **BindingResult**, not a standalone runnable program. **hasFieldErrors("quantity")** still returns true for typeMismatch; the method **does not distinguish the cause** of a field error. To distinguish type-conversion errors from Bean Validation errors, check **FieldError.isBindingFailure()**, error codes, or the phase-specific exception type.

For **@RequestBody** JSON, if the converter fails to deserialize JSON into an object, the controller might never receive a **BindingResult** as in form binding; body-reading failures typically raise **HttpMessageNotReadableException**. Therefore, the four methods above are meaningful **only when a corresponding Errors/BindingResult exists**; they do not replace handling deserialization failures.

## 7. Designing Structured API/UI Error Responses

A helpful response can separate field errors from object-wide errors. Conceptual JSON example for the MIXED case:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "customerName",
      "message": "Customer name must not be blank."
    },
    {
      "field": "quantity",
      "message": "Quantity must be greater than 0."
    }
  ],
  "globalErrors": [
    {
      "message": "Start day must not be after end day."
    }
  ]
}
~~~

This is a **proposed response contract**, not default JSON returned by Spring and not output from the console program. When implementing:

1. Only invoke data-persistence business logic when **!result.hasErrors()** and all other required checks pass.
2. Distribute **getFieldErrors()** by field name so the UI places messages next to the matching input controls.
3. Display **getGlobalErrors()** in a form-level banner, or map cross-field codes to the UI if your product defines a clear convention.
4. Use stable error codes and **MessageSource** for localization if the application serves multiple languages.
5. Never echo **getRejectedValue()** verbatim for passwords, tokens, or sensitive data; never assume every **getDefaultMessage()** is safe to show to clients.
6. Do not rely on element ordering as a business guarantee. If message priority must be fixed, define explicit sorting in the presentation layer.

If you only check **hasFieldErrors()** and treat the rest as success, the system would accept the **GLOBAL_ONLY** case in our example even though the rule "start day must not exceed end day" is violated.

## 8. Testing by Error Group

For real validators and controllers, test the following states:

| Scenario | hasErrors() | hasFieldErrors() | getFieldErrors() | getGlobalErrors() |
| --- | --- | --- | --- | --- |
| All fields valid, cross-field rule valid | false | false | Empty | Empty |
| Only customerName blank | true | true | Has customerName error | Empty |
| Only quantity invalid | true | true | Has quantity error | Empty |
| Only startDay > endDay and validator uses reject(...) | true | false | Empty | Has date relationship error |
| Both blank customerName and invalid date range | true | true | Has customerName error | Has date relationship error |
| quantity cannot convert from string | true if binder records error | true if binder records field error | May contain typeMismatch FieldError | Depends on other errors |

Also verify that **getFieldErrors("customerName")** does not include quantity errors, and that **hasFieldErrors("startDay")** can be false when date violations are recorded only at the global level. When using **@Valid** with Spring MVC, verify **BindingResult** sits immediately after the right argument and the validator actually runs. If you have a custom object-level validator, activate it via proper configuration; Spring does not automatically generate global errors for cross-field comparisons.

## 9. Common Misconceptions

**Misconception 1: hasErrors() and hasFieldErrors() are equivalent.** False: a single global error makes **hasErrors()** true while **hasFieldErrors()** can remain false.

**Misconception 2: getFieldErrors() retrieves every error.** False: this list contains only **FieldError** instances. If you need all errors, use **getAllErrors()**; if you need object-wide errors, use **getGlobalErrors()**.

**Misconception 3: cross-field errors always show up as per-field errors.** False: that depends on whether the validator records the error with **reject(...)** or **rejectValue(...)**, or how a constraint specifies its violation path.

**Misconception 4: hasFieldErrors("name") returns a message.** False: it returns a boolean. Use **getFieldErrors("name")** to inspect **FieldError** details or **getFieldError("name")** for the first error.

**Misconception 5: getFieldErrors().size() equals the number of invalid fields.** False: a single field can produce multiple **FieldError** entries.

**Misconception 6: only @Valid errors appear in BindingResult.** False: binding/type-conversion errors can also be recorded there and appear in the field-error list.

**Misconception 7: getGlobalErrors() is where all HTTP exceptions belong.** False: **Errors** holds error info tied to the target object. JSON parsing errors, missing endpoints, or infrastructure failures follow different handling paths.

**Misconception 8: getDefaultMessage() can be used without checking.** False: a message might be absent or contain details that should not be exposed externally. Normalize codes/messages in the API presentation layer.

## 10. Self-Check Questions

1. A form has one **reject("date.order", "...")** error and no **rejectValue** calls: what do **hasErrors()** and **hasFieldErrors()** return? What is **getGlobalErrors().size()**?
2. One field fails three constraints simultaneously: must **getFieldErrors("field").size()** equal 1?
3. If a controller only checks **if (result.hasFieldErrors()) return "form"**, which error scenario slips through?
4. To display every error on the **email** field, should you use **hasFieldErrors("email")** or **getFieldErrors("email")**?
5. With form input **age=abc** and Java property **Integer age**, why can **getFieldErrors("age")** already contain an error before **@Min** is even evaluated?
6. When an error stems from a rule spanning two fields, what must you do so the UI knows which inputs to highlight?

**Answer guide:** (1) **true**, **false**, **1**; (2) no, there can be multiple errors; (3) global-only errors; (4) **getFieldErrors("email")**; (5) the binder records **typeMismatch** as a field error; (6) map the global error per UI convention or record appropriate field errors as well.

## 11. Official Spring API References

- [Errors — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/Errors.html).
- [BindingResult — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/BindingResult.html).
- [FieldError — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/FieldError.html).
- [ObjectError — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/ObjectError.html).
- [Validation, Data Binding and Type Conversion — Spring Reference](https://docs.spring.io/spring-framework/reference/core/validation.html).
- [Spring MVC @ModelAttribute — Spring Reference](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html).

**Closing rule:** use **hasErrors()** to decide whether any error exists, **hasFieldErrors(...)** to check property errors, **getFieldErrors(...)** to obtain per-field error details, and **getGlobalErrors()** to preserve object-wide errors. Always distinguish the error data recorded on **Errors** from whether the framework itself successfully executed binding/validation.