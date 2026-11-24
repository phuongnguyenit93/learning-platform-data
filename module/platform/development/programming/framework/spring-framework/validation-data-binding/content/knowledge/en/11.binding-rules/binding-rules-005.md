# setRequiredFields and missing-field errors in Spring Framework property binding

When receiving a form, an application often needs to distinguish **the client omitted a required field** from **the client sent the field, but the data is invalid**. Spring provides **DataBinder.setRequiredFields(String...)** to verify which fields must be present in the input values during **property binding**. If the requirement is not met, the binder creates a **FieldError** with the **required** code (via **DefaultBindingErrorProcessor**), and the caller can inspect the error through **BindingResult**.

For example, a registration form requires **email**. Even if the Java object already holds an **email** value beforehand, a request containing only **displayName** still violates the rule **"email must be submitted in this bind pass"**. Conversely, a request sending **email=abc** counts as having a value for binding: **setRequiredFields(...)** itself does not validate email address syntax. Evaluating data semantics requires separate validation.

This article focuses specifically on **DataBinder.bind(PropertyValues)** and **WebDataBinder property binding**, covering missing cases, blank values, error codes, interaction with allowed fields, Spring MVC integration, and boundaries with Bean Validation, constructor binding, and JSON.

## 1. The contract of setRequiredFields(...)

On **org.springframework.validation.DataBinder**, the primary APIs are:

~~~java
binder.setRequiredFields("email", "displayName");
String[] configured = binder.getRequiredFields();
binder.bind(propertyValues);
BindingResult result = binder.getBindingResult();
~~~

The snippet above illustrates usage inside a method with appropriate **binder** and **propertyValues**; import **org.springframework.validation.DataBinder** and **BindingResult**. **setRequiredFields(...)** takes the list of property names required on **each** invocation of **bind(PropertyValues)**. No annotations are needed on the field for this check to take effect.

Configure before binding:

~~~java
RegistrationForm form = new RegistrationForm();
DataBinder binder = new DataBinder(form, "registrationForm");
binder.setRequiredFields("email");
binder.bind(new MutablePropertyValues(Map.of("displayName", "Lan")));
~~~

In this illustration, **RegistrationForm** is a JavaBean and **MutablePropertyValues** holds request data. Because the input lacks the **email** property, Spring records a **required** error for that field. Even if **form.getEmail()** already had a non-**null** value prior to binding, **omitted** input still violates the binder's rule.

Essential aspects of the contract:

- Required names are **property/path names received in PropertyValues**, such as **email** or **address.city**, not database column names.
- The check applies to a **specific bind pass**. It does not prove the object is complete after other processing steps, and it never fabricates a missing request field.
- A request can miss **multiple** required fields. Spring records the corresponding errors in **BindingResult** rather than merely returning a boolean.
- **getRequiredFields()** lets you inspect the current configuration; calling **setRequiredFields(...)** with a new list replaces the required fields configured on that binder.
- This is a **property binding rule** for **bind(PropertyValues)**. It does not apply to **DataBinder.construct(ValueResolver)**, because constructor binding has its own parameter resolution mechanism.
- **setRequiredFields(...) does not run Bean Validation automatically**. Even when all required fields are present, you must invoke a validator or enable **@Valid/@Validated** in the handler flow if content constraints must be checked.

Here, **required** means *the input must be present and not considered empty by the binder's rules*. Do not treat it as an all-purpose annotation checking every Java value.

## 2. Which fields does Spring consider "missing"?

A common point of confusion is that the Javadoc emphasizes **fields absent from PropertyValues**, whereas **DataBinder.checkRequiredFields(...)** in Spring 6.x also treats certain **submitted-but-empty** values as missing.

For a property registered as required, typical behavior is:

| Property value in the bind pass | Required check result | Reason |
| --- | --- | --- |
| Absent from **PropertyValues** | **required** error | Input field not found |
| Field name present, Java value **null** | **required** error | No value |
| **""** (empty string) | **required** error | No text |
| **"   "** or whitespace characters only | **required** error | **StringUtils.hasText(...)** returns false |
| **String[]** of length 0 | **required** error | No elements |
| **String[]** with blank/whitespace first element | **required** error | Binder checks the first element for string arrays |
| **"abc"** or **"0"** | Passes required check | Has text; whether content matches target type/semantics is separate |
| **false**, numeric **0**, non-null collection | Not automatically treated as missing just for being "falsey" or empty | This mechanism does not replace validators for every data type |

**Example to remember:** **email=abc** is present and non-blank, so **setRequiredFields("email")** does not report it missing, even though **abc** is not a valid email address. An **Integer quantity = -2** passes the required check once submitted, yet still needs **@Min(1)**. A non-null empty **List** is not checked the same way as an empty **String** by this logic; if a list needs at least one item, use **@NotEmpty** or an equivalent rule.

For **String[]**, the implementation inspects the **first element**. If the first element is blank while subsequent elements contain text, the required check can still fail. For this reason, do not rely on unusual multi-value inputs to bypass rules. Clearly define which form fields are single-value versus multi-value, then validate the target type.

### Existing data can still trigger a missing-field error

Suppose the object already has:

~~~java
form.setEmail("old@example.com");
~~~

Yet the new request sends only:

~~~text
displayName=Lan
~~~

If the binder is configured with **setRequiredFields("email")**, it checks the **current request's** property values and records **required**. This is not a post-bind check of **form.getEmail() == null**. When a bind pass misses a required field, the old value may remain on the target; **hasErrors()** is the critical signal not to proceed.

Accordingly, **setRequiredFields** fits APIs or forms that expect the field to be re-sent on **every request**, whereas for a partial-update **PATCH** operation, forcing every request to resubmit all fields can be the wrong design choice.

## 3. Internal DataBinder flow: errors are created before assignment

For a **DataBinder** applying property values, the core flow of **doBind(MutablePropertyValues)** is:

~~~text
DataBinder.bind(PropertyValues)
         |
         v
Copy/canonicalize PropertyValues for processing
         |
         v
checkAllowedFields(...)   --> exclude disallowed input fields
         |
         v
checkRequiredFields(...)  --> find missing/empty required fields
         |                    |
         |                    +-- create FieldError, code "required"
         |                    +-- remove corresponding empty PropertyValue
         v
applyPropertyValues(...)  --> convert types and assign remaining properties
         |                    |
         |                    +-- may add typeMismatch / methodInvocation errors
         v
BindingResult             --> holds binding errors
         |
         v
Validation if triggered separately --> may append constraint errors
~~~

This ordering yields three consequences:

**First, the required check runs on inputs after allowed-fields filtering.** If you mark **email** as required while **setAllowedFields(...)** omits email, the email input can be stripped before `checkRequiredFields` runs. As a result, **required** still fires even though the client sent email. Therefore, when combining **allowedFields** and **requiredFields**, ensure all required fields are actually permitted to bind.

**Second, when Spring detects a blank required field, it records the error and removes that value from the PropertyValues to be assigned.** For instance, if the request sends **email="   "** while the target previously held **email="old@example.com"**, the target may keep **old@example.com** after binding while **BindingResult** holds the **required** error. Never inspect the final target value alone and assume the required check succeeded.

**Third, required errors differ from type conversion errors.** With **age=abc** when **age** is **Integer**, the **age** field *is present*, so it is not flagged as missing; the conversion step can produce a **typeMismatch** error instead. Both errors go into **BindingResult**, yet their causes and user-facing messages should differ.

In Spring MVC, **WebDataBinder** also processes form field markers and defaults before calling base binding—for example, specially prefixed parameters used for checkboxes. Thus, on a concrete HTTP form, inspecting the property values **processed by WebDataBinder** is more accurate than reading raw request strings alone.

## 4. BindingResult, FieldError, and the required code

**setRequiredFields(...)** does not throw an exception on ordinary missing-field errors. Errors are passed to the **BindingErrorProcessor** configured on DataBinder; the default **DefaultBindingErrorProcessor** invokes **processMissingFieldError(...)** to create a **FieldError** with code **required**.

Observable APIs:

~~~java
BindingResult result = binder.getBindingResult();

boolean hasErrors = result.hasErrors();
int missingOrOtherErrors = result.getErrorCount();

FieldError emailError = result.getFieldError("email");
if (emailError != null) {
    String primaryCode = emailError.getCode();
    String[] resolvableCodes = emailError.getCodes();
}
~~~

This is an **illustrative snippet** with Spring's **BindingResult** and **FieldError** imported. **getCode()** is typically the generic **required** code for default missing-field errors; **getCodes()** supplies an expanded code list for resolving messages by object/field/type. For example, object **registrationForm** with **String** field **email** may produce codes in roughly this precedence order:

~~~text
required.registrationForm.email
required.email
required.java.lang.String
required
~~~

The exact list depends on the configured **MessageCodesResolver**. Error codes from a custom **BindingErrorProcessor** or validator may also differ.

Therefore, when rendering forms or building JSON errors, use your application's message resolution (such as **MessageSource**) rather than exposing exception names or opaque technical codes. Example **messages_vi.properties**:

~~~properties
required.registrationForm.email=Bạn cần nhập địa chỉ email.
required.email=Vui lòng cung cấp email.
required=Trường bắt buộc chưa được cung cấp.
typeMismatch=Giá trị nhập có định dạng không phù hợp.
~~~

**required** differs from **typeMismatch**:

| Error | Where detected | Example | How to explain it |
| --- | --- | --- | --- |
| **required** | Required fields check (or custom validator deliberately reusing the code) | **email** missing or whitespace | A mandatory field must be provided |
| **typeMismatch** | Type conversion / property assignment | **age=abc** for **Integer age** | Value cannot be converted to the target type |
| **methodInvocation** | Error invoking setter via Spring property access | Setter rejects value or throws during invocation | Inspect setter/property logic |
| **NotBlank / NotNull / Size...** | Bean Validation when enabled | Empty string, null, exceeds length | Violates declared constraint |
| Custom business error code | Application service/domain/validator | Email already registered, insufficient permission | Handle per business rules |

Do not rely on **hasErrors()** alone to conclude all errors are missing fields. Iterate **getFieldErrors()** or inspect **getFieldError("email")**, **getCodes()**, and the error source.

## 5. Standalone Java 17+ example: missing, blank, old data, and invalid content

Uses **Spring Framework 6.2.10** in a console program with no HTTP server needed. The example demonstrates:

1. Omitting **email** → **required**.
2. Sending **email** containing only spaces → **required**.
3. Sending an email with text → no required error.
4. Object already has an old email while request omits email → **required**, old email remains.
5. Sending non-email string **abc** → required passes because text is present.
6. Sending **String[]** with an empty first element → **required**.

Create the structure:

~~~text
required-fields-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── RequiredFieldsDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>required-fields-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/RequiredFieldsDemo.java**:

~~~java
package demo;

import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public final class RequiredFieldsDemo {

    public static void main(String[] args) {
        run("missing", values("displayName", "Ada"), null);
        run("blank", values("email", "   "), null);
        run("present", values("email", "ada@example.com"), null);
        run("preFilledMissing",
                values("displayName", "Ada"), "old@example.com");
        run("nonEmailText", values("email", "abc"), null);

        MutablePropertyValues firstArrayElementEmpty =
                new MutablePropertyValues();
        firstArrayElementEmpty.add(
                "email", new String[] {"", "ada@example.com"});
        run("arrayFirstEmpty", firstArrayElementEmpty, null);
    }

    private static MutablePropertyValues values(String key, String value) {
        return new MutablePropertyValues(Map.of(key, value));
    }

    private static void run(
            String label, MutablePropertyValues input, String oldEmail) {

        RegistrationForm form = new RegistrationForm();
        form.setEmail(oldEmail);

        DataBinder binder = new DataBinder(form, "registrationForm");
        binder.setAllowedFields("email", "displayName");
        binder.setRequiredFields("email");

        binder.bind(input);
        BindingResult result = binder.getBindingResult();
        FieldError error = result.getFieldError("email");

        System.out.println(label
                + ": errors=" + result.hasErrors()
                + ", code=" + (error == null ? "none" : error.getCode())
                + ", email=" + form.getEmail());
    }

    public static final class RegistrationForm {
        private String email;
        private String displayName;

        public RegistrationForm() {
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }
    }
}
~~~

From the directory containing **pom.xml**, with **JDK 17+** and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.RequiredFieldsDemo
~~~

**Lines printed by the program itself**, excluding build tool logs:

~~~text
missing: errors=true, code=required, email=null
blank: errors=true, code=required, email=null
present: errors=false, code=none, email=ada@example.com
preFilledMissing: errors=true, code=required, email=old@example.com
nonEmailText: errors=false, code=none, email=abc
arrayFirstEmpty: errors=true, code=required, email=null
~~~

Output analysis:

- **missing:** only **displayName** is present, so **email** is absent from PropertyValues; **DefaultBindingErrorProcessor** records a required error.
- **blank:** **email** is present, yet **"   "** lacks content per **StringUtils.hasText**; Spring removes the empty PropertyValue from assignment and adds a required error.
- **present:** the email value has text, so it binds to **email** and **hasErrors() == false**. The code has not run Bean Validation.
- **preFilledMissing:** although **RegistrationForm.email** started as **old@example.com**, omitting email in the request still violates required; Spring does not clear the existing value on the target when a field is missing, so **BindingResult** is what tells you the bind failed.
- **nonEmailText:** **abc** counts as "present", and the binder enforces no email format rules; use **@Email**, a custom validator, or dedicated checks if needed.
- **arrayFirstEmpty:** the implementation checks the first element of **String[]**, so a blank first element **""** causes the field to be treated as missing even if later elements have text.

**Note on isolation:** each case creates a fresh **RegistrationForm** and **DataBinder**, so errors do not accumulate across cases. This example demonstrates property-binding required rules without HTTP, JSON, validation annotations, or database persistence.

### Testing an explicit null value

If you also want to test Java **null** in PropertyValues (as distinct from the literal string **"null"**), you can add a case:

~~~java
MutablePropertyValues input = new MutablePropertyValues();
input.add("email", null);
run("explicitNull", input, null);
~~~

This goes inside the same **RequiredFieldsDemo** class; **run(...)** must be accessible as in the code above. The output is **errors=true**, **code=required**, **email=null**. **Map.of("email", null)** is invalid in Java and throws before Spring binds, so the example uses **MutablePropertyValues.add(...)**.

## 6. Spring MVC integration using @InitBinder

In a Spring MVC application with a form:

~~~text
POST /registrations
Content-Type: application/x-www-form-urlencoded

displayName=Lan
~~~

A controller can require **email** to be present during property binding of the **registrationForm** model attribute:

~~~java
@Controller
class RegistrationController {

    @InitBinder("registrationForm")
    void customize(WebDataBinder binder) {
        binder.setAllowedFields("email", "displayName");
        binder.setRequiredFields("email");
    }

    @PostMapping("/registrations")
    String register(
            @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return "registration-form";
        }

        // In a real app: validate content and business rules further,
        // then call the service to handle the registration request.
        return "redirect:/registrations/success";
    }
}
~~~

This is **illustrative code placed inside an existing Spring MVC application**, not a standalone runnable class. **RegistrationForm** is the JavaBean from the previous example or a dedicated DTO with the same structure; import **Controller**, **InitBinder**, **PostMapping**, **ModelAttribute**, **WebDataBinder**, and **BindingResult**. The **registration-form** template and success route are hypothetical web app components.

Role of each part:

- **@InitBinder("registrationForm")** applies configuration to the binder for the model attribute of that name. The name in **@ModelAttribute("registrationForm")** must match.
- **binder.setRequiredFields("email")** requires the form input to include email in this bind pass. It takes effect in the **binding phase** and does not need **@Valid** to produce a required error.
- **binder.setAllowedFields(...)** narrows which properties clients may bind. Required field **email** is included in allowed fields to avoid blocking itself.
- **BindingResult** must appear immediately after its corresponding model attribute parameter; the controller checks **hasErrors()** and returns the form when binding errors exist.
- If **BindingResult/Errors** is not placed in the proper position, Spring MVC handles errors via the corresponding exception/response mechanism; never assume the controller continues as if error-free.

**@Valid/@Validated** can be added when Bean Validation is needed, though its purpose differs from **setRequiredFields**. If an application uses constructor binding instead of property binding, rethink where required checks live because this setting targets **bind(PropertyValues)**. With **@RequestBody JSON**, an HTTP message converter typically deserializes objects via Jackson; **setRequiredFields** on WebDataBinder is not a universal switch for requiring JSON fields.

### When combined with @Valid

Suppose the DTO has:

~~~java
public class RegistrationForm {
    @jakarta.validation.constraints.NotBlank
    @jakarta.validation.constraints.Email
    private String email;

    // getters/setters...
}
~~~

This is an **illustrative snippet**; to run it, declare a Bean Validation provider (e.g. **spring-boot-starter-validation** in Spring Boot) and enable validation on the handler:

~~~java
@PostMapping("/registrations")
String register(
        @jakarta.validation.Valid
        @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "registration-form";
    }
    return "redirect:/registrations/success";
}
~~~

The **email** field can produce a `required` error code from binding when missing, or a constraint code from validation when bound data violates rules. Spring MVC routes both through **BindingResult**, yet their origins differ; do not infer from **hasErrors()** alone that one mechanism replaces the other. **@NotBlank** checks the object's value after binding; **setRequiredFields** checks input presence/non-emptiness during the bind pass.

## 7. Comparing setRequiredFields with other "required" mechanisms

| Mechanism | Where checked | What it requires | Scope to watch out for |
| --- | --- | --- | --- |
| **DataBinder.setRequiredFields("email")** | Property values in **bind(PropertyValues)** | Field must appear and be non-empty per binder required logic | Does not check email format; does not apply to constructor binding |
| **@NotNull** | Bean Validation on property value | Object value must not be **null** | **""** or **" "** is still non-null |
| **@NotBlank** | Bean Validation on **CharSequence** | Not null, not empty, and not whitespace-only | Does not necessarily require the field to be newly sent in this request if the object already held a value |
| **@NotEmpty** | Bean Validation | Non-empty string, collection, map, or array | Does not validate individual elements |
| **@Email** | Bean Validation | Content matches email format per provider/constraint | Does not check whether the email exists in the system |
| **@RequestParam(required = true)** | Spring MVC method argument resolver | Request parameter required by argument resolution | Separate exception path, not model attribute `setRequiredFields` |
| **@RequestBody(required = true)** | Spring MVC reading request body | Request body must be supplied per argument contract | Does not guarantee every JSON field inside the body is present |
| Custom service/domain validation | Application service and domain | Rules depending on state, permissions, current data | Needs transaction/concurrency handling during updates |

### Three non-equivalent examples

**A. Form omits email, while target initially holds an old email.**

- **setRequiredFields("email")** reports missing input.
- **@NotNull** on the target may still pass because the target already had an old email.
- This shows that **"the request must send the field"** and **"the final object has a value"** are two different conditions.

**B. Form sends email=abc.**

- Required check passes because text is present.
- **@Email** can catch the invalid format if Bean Validation runs.
- The service can still reject it if another user already registered that email.

**C. Form sends quantity=-1.**

- Required check for `quantity` passes because a value was received.
- **@Min(1)** catches the negative number if validation is enabled.
- When creating an order, the service also checks purchase limits and stock. No single annotation protects concurrent transactions on its own.

## 8. Interaction with allowedFields, disallowedFields, and path names

A common pitfall configuration:

~~~java
DataBinder binder = new DataBinder(form, "registrationForm");
binder.setAllowedFields("displayName");  // DOES NOT include email
binder.setRequiredFields("email");
binder.bind(new MutablePropertyValues(Map.of(
        "email", "ada@example.com",
        "displayName", "Ada"
)));
~~~

Even though the request sends email, **checkAllowedFields(...)** strips **email** from the bindable inputs before **checkRequiredFields(...)** executes. The result can show **getSuppressedFields()** containing email and **getFieldError("email")** with code `required`. This is an application configuration bug, not a user mistake. If email is genuinely both bindable and mandatory, keep the configuration consistent:

~~~java
binder.setAllowedFields("email", "displayName");
binder.setRequiredFields("email");
~~~

Never enable binding on sensitive fields just to avoid missing-field errors; design the request DTO and required list to match only what users are actually allowed to edit.

### Nested field: address.city

If you require a path like:

~~~java
binder.setRequiredFields("address.city");
~~~

the input property the binder looks for is **address.city**. A client sending only **address.street** does not satisfy that requirement, even if the **address** object already exists. Conversely, having **address.city** in PropertyValues does not guarantee binding succeeds: Spring must still traverse the intermediate **address** object (possibly auto-instantiating it if permitted and constructible), then convert and assign the value.

**setRequiredFields is not wildcard validation for every nested field.** Required names are compared against canonicalized property names; to require multiple fields, list each actual path name. For collections like **addresses[0].city**, design valid counts/indexes and separate validation rules rather than using a vague single name in place of structural collection checks.

### Targets with ignored/suppressed fields

If results show **result.getSuppressedFields()** is non-empty, check whether the request tried to set a disallowed field. An **allowedFields** misconfiguration and a **required** error can occur simultaneously; fix the root cause instead of just changing the message to "you forgot to enter an email".

## 9. Common HTTP form traps

**Unchecked checkboxes usually emit no parameter.** A standard HTML checkbox is often absent from the request when unchecked. If you call **setRequiredFields("subscribed")** trying to require that *the user saw/accepted terms*, distinguish "checkbox absent", "submitted false", and "checked true". Required checks only measure input presence/non-emptiness; they do not automatically interpret **false** as rejecting terms. **WebDataBinder** also has checkbox field marker/default handling, so test with real requests before drawing conclusions.

**Hidden fields do not make data trustworthy.** Putting **email** or **role** in a hidden input lets the required check pass, yet clients can still tamper with it. Verify permissions, ownership, and server-determined data at the appropriate layer.

**Required fields rarely fit PATCH.** In partial updates, clients may send only the fields they want to change; forcing **email** on every call can reject valid requests. Use separate DTOs for create/replace/partial update or apply validation groups/checks appropriately.

**Form field names must match properties.** If HTML submits **contactEmail** while the binder requires **email**, the required check looks for **email** and reports it missing. Fix the form/DTO mapping rather than relaxing the check without investigation.

**A present field can still fail assignment.** Badly typed data causes **typeMismatch** during binding; faulty getters/setters cause property access errors. Passing the required check does not guarantee every property was set successfully.

**Reporting missing while still mutating data.** Property binding may already have assigned other fields before returning **BindingResult**; it is not a transactional rollback. Halt business processing when errors exist, and bind into a dedicated DTO before translating into domain commands.

**Expecting setRequiredFields to trigger via annotations alone.** You must configure the binder actually used by the framework or invoke the binder manually. Another **DataBinder** or a JSON **@RequestBody** does not inherit settings just because another bean configured them elsewhere.

**Customizing BindingErrorProcessor without updating the error contract.** If you replace the default processor, error codes and types may change. UI and tests must rely on the error contract your application intentionally defines, rather than assuming every implementation produces the exact same FieldError.

## 10. Designing error responses

In MVC forms, controllers typically place **BindingResult** right after **@ModelAttribute** and re-render the template to show errors next to the relevant fields. In REST APIs, turning errors into **400 Bad Request**, **ProblemDetail**, or another JSON schema is decided by your **exception handler/response contract**; **setRequiredFields** itself returns no HTTP status.

A sample JSON error representation might look like:

~~~json
{
  "type": "validation_error",
  "errors": [
    {
      "field": "email",
      "code": "required",
      "message": "Please provide an email."
    }
  ]
}
~~~

This is a **suggested format**, not a fixed default body from Spring MVC. Never return stack traces or internal details. When localizing, keep the stable error code **required** alongside the field name, while resolving messages from **MessageSource** by locale.

If multiple errors occur together, return the full error set so the client can fix everything at once—for example, missing email and invalid age type. Avoid collapsing all FieldErrors into a single generic **"invalid request"** while dropping field names and error codes if callers need specific feedback.

## 11. Test matrix for required fields

A test suite aligned with Spring's behavior should include both **DataBinder unit tests** and **MVC integration tests** if controllers exist.

| Test | Input / initial state | Expectation |
| --- | --- | --- |
| Missing | PropertyValues lacks **email** | **FieldError(email)** with code **required** |
| Explicit null | PropertyValues has **email = null** | **required** |
| Empty String | **email = ""** | **required** |
| Whitespace String | **email = "   "** | **required** |
| String[] empty | **email = new String[0]** | **required** |
| First array element blank | **email = ["", "abc"]** | **required** |
| Present text | **email = "abc"** | No required error; format checked separately |
| Existing value, request missing | Target **email = "old@example.com"**, request omits email | **required** even though target holds old value |
| Allowed vs required conflict | Email required, but allowlist excludes email | Email stripped; catch misconfiguration |
| Nested path | Required **address.city**, request sends only **address.street** | Required error for **address.city** |
| Type mismatch | Required **age**, request sends **age=abc** for Integer | Field present, yet may emit **typeMismatch** |
| PATCH scenario | Update displayName only | Do not configure email as required if contract allows omitting it |
| JSON input | **@RequestBody** missing email | Verify via JSON deserialization/Bean Validation; do not assume setRequiredFields ran |

Tests should inspect both **FieldError.getCode()** and target values after binding. The case where email is blank while the target holds a prior value demonstrates Spring's step of **removing invalid PropertyValues from assignment**. In MVC tests, verify that **@InitBinder** is actually invoked for the right model attribute and that **BindingResult** is placed immediately after that parameter.

## 12. Checklist for proper usage

Before choosing **setRequiredFields(...)**, ask yourself:

1. Does the data source flow through **DataBinder.bind(PropertyValues)**? For constructor binding or JSON bodies, use other mechanisms.
2. Does "required" mean **the field must be sent in the request** or simply **the final object must hold a valid value**? Those two goals can yield different outcomes.
3. Do required field names match actual property paths and appear in **allowedFields**?
4. Do HTML form inputs involve **field markers/defaults**, multi-value arrays, or checkboxes?
5. After binding, does the code inspect **BindingResult** before executing business writes?
6. When data is present yet invalid in content, are **@NotBlank**, **@Email**, **@Min**, Spring Validators, or domain logic in place?
7. When user feedback is needed, does the app map the **required** code to clear localized messages?

Remember that **"required in property binding"** is a rule about **the input values of a bind pass**. It complements type conversion, validation, and domain rules, rather than replacing those three mechanisms.

## Official documentation

- [Spring Framework 6.2.10 — DataBinder API: setRequiredFields, checkRequiredFields, bind](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2.10 — DefaultBindingErrorProcessor](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/DefaultBindingErrorProcessor.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring MVC — @ModelAttribute method arguments and BindingResult](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Jakarta Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
