# Target Object Selection and Initialization in Spring Framework Data Binding

## 1. What Is the Target Object, and Why Must It Be Selected Correctly?

In Spring MVC, data sent by the client often starts in string form such as `displayName=Lan&age=21`. The **target object** (binding target) is the Java object into which `WebDataBinder` populates those values, after determining property names, data types, conversion rules, and writable fields.

For example, with a parameter `@ModelAttribute("signupForm") SignupForm form`, Spring must determine **which `signupForm` object** will be used before binding data. That object may already exist in the Model/Session, be provided by a Model-populating method, be converted from a request value, or be newly instantiated by Spring. Choosing the wrong object can lead to overwriting existing data, binding the wrong fields, or accidentally allowing the client to modify sensitive properties.

Distinguish three concepts:

| Concept | Role | Example |
| --- | --- | --- |
| **Data source** | Values supplied by the client; untrusted by default | `email=lan@example.com`, `age=21` |
| **Target object** | Existing or newly created Java instance to receive values | `SignupForm`, `ProfileForm` |
| **Binder** | Component coordinating constructor/property binding, conversion, and errors | `WebDataBinder` in MVC, `DataBinder` at core level |

This article covers the **instance selection and pre-/during-binding initialization** phase of a Spring MVC flow using `@ModelAttribute`, while also relating to the `DataBinder` API at the Spring Core layer. `@RequestBody` goes through body reading and `HttpMessageConverter` (e.g., JSON deserialization), so you should not automatically apply the same model attribute selection rules to `@RequestBody`.

## 2. From Handler Parameter to Concrete Object

The mental flow when Spring MVC processes an `@ModelAttribute` parameter:

```text
HTTP request
   |
   v
Handler method resolved
   |
   v
Resolver identifies @ModelAttribute parameter
   |
   v
Determine attribute name and target Java type
   |
   v
Find/obtain existing target object in Model
   |                          \
   | Found                    | Not found
   v                          v
Use that instance      Check sources that can supply the object
                              | (e.g. Converter from path variable)
                              v
                        If needed, instantiate a new object
   \                          /
    v                        v
      Create/configure WebDataBinder
                |
                v
   Constructor binding when target creation is needed
   Property binding when permitted
                |
                v
   BindingResult + validation (if requested)
                |
                v
      Pass argument into controller
```

The diagram above shows **selection possibilities**, not a guarantee of an immutable algorithmic order across every Spring version, every resolver, and every configuration. The core point: when the target already exists, the binder works on that instance; when the target does not exist yet, Spring must find a way to provide/instantiate it.

### 2.1. Determining the Name Before Lookup

* `@ModelAttribute("profileForm") ProfileForm form` requests the model attribute name `profileForm`. This is the most controllable approach when pairing with `@ModelAttribute` methods, `@InitBinder`, or `@SessionAttributes`.
* With `@ModelAttribute ProfileForm form`, Spring derives the name by convention from the object type. Do not assume the Java variable name always determines the attribute name; declare the name explicitly in flows with multiple model objects.
* A parameter of a complex type not handled by another resolver may be treated as an implicit `@ModelAttribute`. Writing the annotation explicitly makes it easier for readers and AOT/native-image processing to reason about.
* If it is a simple parameter like `String` or `int`, Spring MVC usually resolves it like `@RequestParam`; if it is `@RequestBody`, a separate body-processing path is used.

### 2.2. Paths That Can Supply the Target

| Object source | When it occurs | Meaning for initialization phase |
| --- | --- | --- |
| **Request Model** | `Model.addAttribute("name", object)` or an `@ModelAttribute("name")` method has added the object | Reuses the existing instance; no need to create a new one for that parameter |
| **Controller's `@SessionAttributes`** | Attribute declared by the controller and managed across multiple requests | Restores the object into the model within the workflow; requires session lifecycle management |
| **`Converter<String, T>`** | Attribute name matches a request/path variable value and a compatible converter exists | Creates/fetches `T` from a string value (can look up the object in a service) |
| **Target class constructor** | No suitable instance is provided | Spring instantiates a new one via an empty constructor or a data-bearing constructor, depending on class design |
| **Caller supplies target to `DataBinder`** | Using `DataBinder` directly outside the argument resolver mechanism | Caller provides an existing object or configures target type for `construct` |

**A model object is not synonymous with a JPA entity:** an `@ModelAttribute` can be an input DTO, a command object, or a domain object. Using a dedicated DTO generally makes it easier to restrict input.

## 3. Reusing an Existing Target

### 3.1. `@ModelAttribute` Method Preparing the Model

A method annotated with `@ModelAttribute` at the method level in a `@Controller`/`@ControllerAdvice` can be invoked before the handler to add data to the Model. The example below is an **illustrative snippet inside an existing controller**, assuming `profileService` and `ProfileForm` are already defined:

```java
@ModelAttribute("profileForm")
public ProfileForm loadProfile(@PathVariable("id") long id) {
    return profileService.loadEditableForm(id);
}

@InitBinder("profileForm")
public void restrictProfileFields(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "city");
}

@PostMapping("/profiles/{id}")
public String saveProfile(
        @PathVariable("id") long id,
        @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "profile-edit";
    }
    profileService.updateProfile(id, form.getDisplayName(), form.getCity());
    return "redirect:/profiles/" + id;
}
```

In the request `POST /profiles/42`, `loadProfile` fetches the current form of profile 42 and puts it into the Model under the name `profileForm`. The handler receives **that exact instance** to bind only the allowed properties, rather than creating an empty form and hoping a client-supplied ID tells it which record to edit. `BindingResult` sits immediately after the corresponding parameter so the handler can process binding errors.

Keep this distinction clear: the Model of a `GET` request does not automatically persist into the subsequent `POST`. To reload the object on each request, you can use a model-loading method as above; to maintain state across multiple requests in a wizard, consider `@SessionAttributes`. For persisted data, the service must verify access rights to the ID on the server side.

### 3.2. Target Managed via `@SessionAttributes`

`@SessionAttributes("wizardForm")` at the controller level is used to keep a model attribute across multiple requests within the same workflow. Once the session attribute is restored into the Model, the binder can work on that object. When finishing the workflow, call `SessionStatus.setComplete()` to remove the attributes managed by this annotation.

```java
@Controller
@SessionAttributes("wizardForm")
class WizardController {
    @ModelAttribute("wizardForm")
    WizardForm newWizardForm() {
        return new WizardForm();
    }

    @PostMapping("/wizard/finish")
    String finish(@ModelAttribute("wizardForm") WizardForm form,
                  BindingResult errors,
                  SessionStatus status) {
        if (errors.hasErrors()) {
            return "wizard";
        }
        status.setComplete();
        return "done";
    }
}
```

This is an integration example requiring the `WizardForm` class and MVC configuration. `@SessionAttributes` serves a controller-scoped model, unlike `@SessionAttribute` which reads an already existing session attribute. You should not turn the HTTP session into long-term storage for all form data.

### 3.3. Obtaining the Target via `Converter`

If a handler declares `@ModelAttribute("account") Account account` with route `/accounts/{account}`, Spring MVC can use a registered `Converter<String, Account>` to convert the path variable `account` into an `Account`. The converter can call a service to load the object to be processed.

**Important condition:** the attribute name must match a suitable request/path variable name and a compatible converter must exist. The existence of a `Converter<String, Account>` does not mean Spring automatically looks up an account by arbitrary ID fields. Access permissions, bindable fields, and object state after retrieval remain the responsibility of application design.

## 4. When No Instance Exists Yet: Two Main Initialization Styles

### 4.1. No-Arg Constructor Followed by Property Binding

With a mutable JavaBean having a no-arg constructor and setters, Spring can create an empty object and then assign each permitted property:

```java
public class ProfileForm {
    private String displayName;
    private String city;

    public ProfileForm() { }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { this.displayName = value; }

    public String getCity() { return city; }
    public void setCity(String value) { this.city = value; }
}
```

For the request `displayName=Lan&city=Da%20Nang` and a new `ProfileForm` target, after property binding we get `displayName = "Lan"` and `city = "Da Nang"`. Values may require conversion if the target type is `int`, `LocalDate`, or an enum.

**Note:** the no-arg constructor only handles object creation; populating setters is a separate step. `setAllowedFields(...)` restricts which properties are allowed to be updated; Spring does not automatically know a setter is "sensitive." If the binder is configured in declarative-binding-only mode without declaring allowed fields, property binding is skipped.

### 4.2. Constructor Binding for Immutable Objects

With a `record` or a class with an explicit data constructor, Spring retrieves request parameters by **constructor parameter name**, converts their types, and passes them into the constructor. This is suitable for form inputs designed to be immutable. The complete example below is `SignupController.java` in a **web-configured Spring MVC application**, using Java 17+ and Spring Framework 6.1+:

```java
import org.springframework.http.MediaType;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.*;

@RestController
public class SignupController {

    public record SignupForm(String email, int age) {}

    @InitBinder("signupForm")
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    @PostMapping(path = "/signup",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public String signup(@ModelAttribute("signupForm") SignupForm form,
                         BindingResult errors) {
        if (errors.hasErrors()) {
            return "INVALID";
        }
        return form.email() + " / " + form.age();
    }
}
```

Example endpoint call while the application is running:

```http
POST /signup HTTP/1.1
Content-Type: application/x-www-form-urlencoded

email=lan%40example.com&age=21
```

With valid input and no additional validators, the response body is:

```text
lan@example.com / 21
```

Explanation: `SignupForm` has no setters; Spring matches `email` and `age` to the record's constructor and converts `"21"` to `int`. `@InitBinder("signupForm")` enables `declarativeBinding` so free-form property binding is not performed. Since there is no `role` field in the constructor, the client cannot create a `role` property just by sending `role=ADMIN`.

When using a **class** with a multi-parameter constructor, make sure parameter names can be read by Spring (for example compiling Java with `-parameters`); Java records store component metadata conveniently for this style. You can use `@BindParam("display-name")` on a constructor parameter to map a request key that differs from the variable name. If a class has multiple constructors, constructor selection follows Spring's rules and class structure; prefer a single clear data constructor or explicit initialization configuration to avoid ambiguity.

Constructor binding can also initialize nested objects; it also supports `List`, `Map`, and array structures for input formats supported by Spring. Even so, input depth and size from clients must still be properly designed, bounded, and tested.

### 4.3. How Direct `DataBinder` Usage Differs from MVC

In Spring Core, a caller can pass an existing target via `new DataBinder(existingObject, "profileForm")` and then call `bind(PropertyValues)`. If you want the binder to **create the target itself** via constructor binding (API since Spring 6.1), the caller initializes the binder with a `null` target, configures `targetType` via `setTargetType(ResolvableType)`, and calls `construct(ValueResolver)`. Then inspect `getBindingResult()` and `getTarget()`.

```text
Existing target provided upfront:
  DataBinder(existing, "name") -> bind(propertyValues)

Creating target via constructor:
  DataBinder(null, "name")
      -> setTargetType(...)
      -> construct(valueResolver)
      -> getTarget()/getBindingResult()
      -> bind(...) if needed and permitted
```

This is an **API call diagram**, not a standalone runnable Java file. In MVC controllers, resolvers and `WebDataBinderFactory` handle most of the selection/initialization, so the application usually does not need to call this API sequence manually.

## 5. In What Ways Can a Target Be Bound?

Distinguish **target creation** from **populating/overwriting data**:

| State when binder starts | Constructor binding | Property binding |
| --- | --- | --- |
| Target does not exist yet and is created via a data constructor | Reads inputs matching constructor parameters to create object | Can run afterward if object has matching properties and config allows it |
| Target newly created via no-arg constructor | Creates no-arg instance | Setters/JavaBean properties receive permitted inputs |
| Target already obtained from Model/Session/service/Converter | No need to run constructor again on that instance | Can overwrite permitted properties if binding is enabled |
| `@ModelAttribute(binding = false)` | Object still must be appropriately supplied/instantiated | Skips binding from request for this parameter |

By default, `DataBinder` supports both constructor binding and property binding. When you set `binder.setDeclarativeBinding(true)`, constructor binding remains supported, whereas property binding is performed only if `allowedFields` is configured. This is very different from thinking "having a constructor guarantees all setters are locked."

Auto-growing nested paths via property binding, when configured and possible, is also not the same as constructing nested objects via constructors. Do not rely on auto-grow to instantiate complex domain entities or traverse unanticipated property graphs.

## 6. Choosing a Safe Target When Handling Update Forms

### 6.1. Do Not Bind Raw Requests into Privileged Entities

Suppose a `User` entity has `displayName`, `role`, `enabled`, `ownerId`. If you fetch the entity from the database and property-bind all request parameters directly onto it, a client can try sending:

```text
displayName=Lan&role=ADMIN&enabled=true
```

If the application inadvertently allows writing these properties, a **mass assignment/over-posting** vulnerability arises. Looking up the right entity by ID does not make binding all fields safe.

Prefer:

1. Create a DTO containing only accepted input fields, ideally an immutable object with an explicit constructor.
2. With property binding, restrict fields using `@InitBinder` and `setAllowedFields("displayName", "city")`; avoid overly broad wildcards.
3. For applications on Spring 6.1+, use `setDeclarativeBinding(true)` so constructor binding applies without unrestricted setter binding.
4. Load the persisted target and check access permissions by ID in the service; then copy only verified fields from the DTO into the entity.
5. When only reading an object from the Model, use `@ModelAttribute(binding = false)` so the request cannot modify it. **Do not** confuse `binding=false` with skipping object retrieval.

Example combining an input DTO with a safely loaded object in a controller (service/domain classes are assumed to exist):

```java
@ModelAttribute("account")
Account loadAccount(@PathVariable("id") long id) {
    return accountService.findEditableById(id);
}

@PostMapping("/accounts/{id}/name")
String changeName(@ModelAttribute("nameForm") NameForm input,
                  BindingResult errors,
                  @ModelAttribute(value = "account", binding = false)
                  Account account) {
    if (errors.hasErrors()) {
        return "change-name";
    }
    accountService.changeDisplayName(account, input.displayName());
    return "redirect:/accounts/" + account.getId();
}
```

Here `NameForm` should be a DTO/record accepting only `displayName`. The `account` object is looked up on the server side without being bound from the request, cleanly separating the two responsibilities: "identifying the record" and "receiving user-editable input." Authorization still needs to be checked in the service.

### 6.2. Common Scenarios

| Scenario | Target to choose | Consequence |
| --- | --- | --- |
| New registration | New DTO/record, constructor binding | Each request gets its own instance; accepts only declared parameters |
| Profile edit form | Update DTO loaded from service, or new DTO with server-handled ID | Prevents client from deciding edit permissions or target record ID |
| Multi-step wizard | Model attribute managed by `@SessionAttributes` when appropriate | Reuses state; requires `SessionStatus.setComplete()` upon completion |
| Path variable representing a domain object | Compatible Converter or Model-loading method | Must check permissions, existence, and field limits before updating |
| Using object read-only | Model attribute with `binding=false` | Prevents pouring request parameters into the read-only object |
| JSON body to REST endpoint | `@RequestBody` + message conversion | Object creation flow via body deserialization, distinct from `@ModelAttribute` |

## 7. Failures During Target Creation and Binding

**Unable to instantiate.** The class has no constructor supported by Spring, a parameterized constructor lacks readable parameter-name metadata, or an abstract/interface type has no suitable instantiation path. Check DTO design, constructors, `-parameters`, `@BindParam`, and Model target sources. Avoid misdiagnosing this as the client omitting all fields when the real issue is constructor configuration.

**Unable to convert a value.** For instance, `age=abc` for `int age` causes a type conversion error; if the binder can represent the error, inspect `BindingResult` and codes such as `typeMismatch`. Do not use the bound object as valid data when `errors.hasErrors()` is true. Instance-creation failures do not always map to a single exception type; the handler and Spring version determine exact handling.

**Wrong attribute selected.** `@ModelAttribute("form")` does not share the same name as an object added under `"profileForm"`, so Spring may fail to find the intended object and fall back to creating a new one. Use explicit, consistent names across factory methods, handlers, binders, and session annotations.

**GET and POST forms use two different instances.** The Model is scoped per HTTP request; an object added to the Model while rendering GET does not automatically persist to POST. Reload from a service or use a state mechanism with a clear lifecycle.

**Misplaced `BindingResult`.** If you need to handle errors for an `@ModelAttribute` inside the controller, place `BindingResult` immediately after that parameter. With `@Valid`/`@Validated` validation, omitting the corresponding `BindingResult` can cause Spring to throw an exception according to validation configuration.

**Binder accepts too many fields.** The request contains unexpected property names; loading the right target does not prevent property binding from modifying other fields. Check `setAllowedFields`, `declarativeBinding`, the DTO, and suppressed fields.

**Confusing binding with persistence.** Binding only prepares the object for the handler. It does not automatically call `repository.save(...)`, commit a transaction, or verify business permissions; those decisions still belong to the service/application layer.

## 8. Self-Check Workflow When Building an Endpoint

1. Determine whether the handler parameter uses `@ModelAttribute` or `@RequestBody`; if `@ModelAttribute`, state the attribute name explicitly.
2. Ask: is the desired object already in the Model (including factory/session methods) or does it need to be newly created?
3. If newly created, choose either a mutable bean with a no-arg constructor and setters **or** an immutable DTO/record with a data constructor; ensure Spring can read parameter names.
4. If using an existing object, ask whether the client is genuinely allowed to update that object; if not, disable binding or use a separate input DTO.
5. Configure bindable fields via `@InitBinder` and any needed converters/formatters; check the impact of nested/indexed inputs.
6. Add `BindingResult` in the right position if the handler handles errors itself, and design appropriate validation.
7. Test at least three cases: valid request; invalid type / missing required data; request attempting to add sensitive fields outside the allowlist.
8. If using a session-based workflow, verify that subsequent requests receive the right object and that the session is cleaned up when finished.

**Explain the flow to yourself with one question:** for `POST /profiles/42` with `displayName=Lan`, where did the `ProfileForm` instance come from, which constructor ran (if any), what allowed assigning `displayName`, and which `BindingResult` holds invalid data? Being able to answer all four points means you have correctly mapped out the target selection and initialization stage.

## References

- Spring Framework Reference — `@ModelAttribute` method arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference — `@ModelAttribute` methods and Model initialization: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-modelattrib-methods.html
- Spring Framework Reference — MVC Data Binding and model design: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework Reference — Core Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework Reference — `@InitBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Reference — `@SessionAttributes`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html
