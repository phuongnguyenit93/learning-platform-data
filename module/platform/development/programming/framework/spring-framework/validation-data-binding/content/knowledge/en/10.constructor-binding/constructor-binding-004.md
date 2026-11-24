# construct and Reading Objects Created via Constructor Binding

## 1. Purpose and Context

In Spring Framework, **constructor binding** creates a new object by taking input data, mapping it to **constructor parameters**, converting types, and invoking that constructor. This topic focuses on two operations on `org.springframework.validation.DataBinder`:

1. **`construct(DataBinder.ValueResolver)`** to build an object from input data when no target exists yet.
2. **`getTarget()`** to read the object Spring created, combined with **`getBindingResult()`** to check for errors before using it.

A fitting example: receiving `name=Lan`, `age=26`, `address.city=Hue` and constructing a `Signup` record containing `String`, `Integer`, and a nested `Address` record. Constructor binding is useful for **records, immutable DTOs, and classes with parameterized constructors**, especially when avoiding reliance on setters.

The content below applies to **Java 17+ and Spring Framework 6.2.x**. The `DataBinder.construct(...)` API was introduced in Spring 6.1; `ValueResolver.getNames()` appeared in 6.1.2. Spring Boot 3.x projects should check the actual Spring Framework version provided by dependency management.

After this lesson, you will be able to:

- Prepare `DataBinder` properly with a `null` target and `ResolvableType`.
- Implement `DataBinder.ValueResolver` to feed data into constructors.
- Read the created object cleanly with `getTarget()` and cast safely.
- Check `BindingResult` before using the object.
- Distinguish constructor-based object creation from property writing and running validation.
- Handle nested objects, conversion errors, parameter names, and untrusted data.

## 2. When to Call `construct`?

A `DataBinder` is commonly created for an **already existing object**:

~~~java
Person person = new Person();
DataBinder binder = new DataBinder(person);
binder.bind(propertyValues);
~~~

This is an **illustrative snippet** for property binding: `person` already exists, and `bind(...)` finds matching properties to assign data to. `Person` and `propertyValues` must be defined in a real program.

Constructor binding goes the other direction:

~~~java
DataBinder binder = new DataBinder(null, "signup");
binder.setTargetType(ResolvableType.forClass(Signup.class));
binder.construct(valueResolver);

BindingResult result = binder.getBindingResult();
Object created = binder.getTarget();
~~~

The second snippet is also a **fragment**, which will be expanded into a runnable program in section 4. Meaning of each step:

1. `new DataBinder(null, "signup")`: there is no object to bind onto yet; `"signup"` is the logical name used for errors and the model.
2. `setTargetType(ResolvableType.forClass(Signup.class))`: tells the binder **which type to create**. `ResolvableType` also supports describing generic types when needed.
3. `construct(valueResolver)`: asks the resolver for constructor argument values, converts types, and builds the object.
4. `getBindingResult()`: checks creation/binding errors.
5. `getTarget()`: retrieves the created object; its return type is `Object`, so appropriate checking/casting is needed.

**Do not call `construct` as a way to re-initialize an existing target.** This API expects the initial target to be `null` and the target type to be configured. If `getTarget()` already holds an object, calling it violates the precondition. Also do not call `construct` repeatedly just to "read" the object; after successful creation, read via `getTarget()`.

## 3. Internal Processing Flow at a Conceptual Level

~~~text
Map / request parameters / data source
       name="Lan"
       age="26"
       address.city="Hue"
                   |
                   v
new DataBinder(null, "signup")
setTargetType(Signup.class)
                   |
                   v
          construct(ValueResolver)
                   |
          +--------+---------+
          |                  |
     Find constructor    ValueResolver
     parameters          resolves names and values
          |                  |
          +--------+---------+
                   |
          Convert by type
            String -> Integer
                   |
       Create Address (nested object)
                   |
        Invoke canonical constructor
                   |
        +----------+----------+
        |                     |
    No errors          Conversion error
        |                     |
   getTarget()         getBindingResult()
        |              contains FieldError
   Use Signup           Inspect errors
~~~

The flow above explains API responsibilities; **do not assume** every error is turned into a complete `Signup` object. If conversion fails, check `BindingResult` and the target state. If the constructor itself throws an exception unrelated to conversion, calling `construct` can also throw `BeanInstantiationException`; that is an error path to distinguish.

Spring can select a data constructor suited to the target type. Designs should have **one clear data constructor**. Java records define a canonical constructor and component names. When multiple constructors exist, selection behavior may depend on default constructors and metadata; do not add arbitrary constructors and expect Spring to guess "the right one".

## 4. Complete Java Example: construct and Reading the Target

To practice without a web server, use Spring `spring-context` because `DataBinder` resides in this module. Spring pulls in the required transitive dependencies.

### 4.1. Project Structure

~~~text
constructor-binding-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/ConstructDemo.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'constructor-binding-demo'
~~~

File `build.gradle` for Gradle Groovy DSL:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ConstructDemo'
}
~~~

`6.2.18` is a pinned version used for the example. In real Spring Boot projects, prefer Boot's dependency management/BOM to select compatible Spring versions.

### 4.2. File `src/main/java/demo/ConstructDemo.java`

~~~java
package demo;

import java.util.Map;
import java.util.Set;

import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class ConstructDemo {

    public record Address(String city) {}

    public record Signup(String name, Integer age, Address address) {}

    private static DataBinder.ValueResolver fromMap(
            Map<String, ?> inputs) {

        return new DataBinder.ValueResolver() {
            @Override
            public Object resolveValue(String name, Class<?> type) {
                return inputs.get(name);
            }

            @Override
            public Set<String> getNames() {
                return inputs.keySet();
            }
        };
    }

    public static void main(String[] args) {
        Map<String, String> inputs = Map.of(
                "name", "Lan",
                "age", "26",
                "address.city", "Hue"
        );

        DataBinder binder = new DataBinder(null, "signup");
        binder.setTargetType(
                ResolvableType.forClass(Signup.class));

        binder.construct(fromMap(inputs));

        BindingResult errors = binder.getBindingResult();
        if (errors.hasErrors()) {
            errors.getAllErrors().forEach(error ->
                    System.out.println(error.getCode()));
            return;
        }

        Object target = binder.getTarget();

        if (!(target instanceof Signup created)) {
            throw new IllegalStateException(
                    "Failed to create Signup");
        }

        System.out.println("name=" + created.name());
        System.out.println("age=" + created.age());
        System.out.println("city=" + created.address().city());
        System.out.println("objectName=" + binder.getObjectName());
        System.out.println("sameTarget=" +
                (errors.getTarget() == created));
    }
}
~~~

This is **a standalone Java file in the project above**, with complete package, imports, and `main` method. Spring does not need a controller to use `DataBinder` programmatically like this.

### 4.3. Running the Program and Output

In the directory containing `build.gradle`, with Gradle Wrapper generated:

~~~bash
./gradlew run
~~~

On Windows:

~~~powershell
.\gradlew.bat run
~~~

Aside from task output printed by Gradle, the Java program's stdout for valid data is:

~~~text
name=Lan
age=26
city=Hue
objectName=signup
sameTarget=true
~~~

Line-by-line explanation:

- `name=Lan`: the value `"Lan"` goes into the `String name` parameter.
- `age=26`: `"26"` is converted to `Integer` before calling the constructor.
- `city=Hue`: Spring constructs the child record `Address("Hue")` from the `address.city` path.
- `objectName=signup`: the name configured by `new DataBinder(null, "signup")`, which does not have to match the Java class name.
- `sameTarget=true`: upon successful creation, `BindingResult#getTarget()` points to the same object as the target retrieved from the binder.

The lesson uses `Map.of` to simulate input data. In Spring MVC, the actual source may be form/query parameters supplied by the HTTP infrastructure. The mechanism of querying names and values follows the same principles.

## 5. Role of `ValueResolver`: Exactly Two Methods

In Spring 6.2.x, `DataBinder.ValueResolver` defines two primary methods:

~~~java
Object resolveValue(String name, Class<?> type);

Set<String> getNames();
~~~

This is a condensed API signature for learning, not source code redefining the interface.

**`resolveValue(name, type)`** is called by Spring when it needs a value for a constructor parameter. `name` is the name determined by Spring, which can be a nested path like `address.city`. `type` indicates the target parameter type; the resolver can return the raw value and let the binder perform conversion.

In the example, the resolver uses `inputs.get(name)`. It returns `"26"` for `age`; the binder converts that string to `Integer`. If the data source already returned `Integer`, the mechanism still fits. If the name does not exist, the resolver returns `null`.

**`getNames()`** returns the set of names present in the source. It matters when Spring needs to know whether deeper fields exist at a nested path to decide whether to construct a child object. With input `address.city`, `getNames()` helps recognize that data for `address` exists even without a standalone key named `address`.

Common mapper example:

~~~java
static DataBinder.ValueResolver fromMap(
        Map<String, ?> input) {

    return new DataBinder.ValueResolver() {
        @Override
        public Object resolveValue(String name, Class<?> type) {
            return input.get(name);
        }

        @Override
        public Set<String> getNames() {
            return input.keySet();
        }
    };
}
~~~

This is a **fragment of the same idea from section 4**, requiring imports for `DataBinder`, `Map`, and `Set` when placed in a standalone file. Do not implement `getNames()` as `Set.of()` if the source contains nested paths; otherwise the binder may fail to detect data under `address.city`.

Key points to remember:

1. `ValueResolver` is **how input is read**, not an API to invoke constructors directly.
2. Do not use arbitrary Java field names if the source uses different keys. Parameter names must be resolved properly or mapped via explicit rules.
3. `resolveValue` should not arbitrarily write into other objects, mutate the source map, or store per-request state in a singleton.
4. `getNames()` should reflect the actual input key set, including nested/indexed keys.
5. Across early Spring 6.1 releases, the interface shape evolved; this guide deliberately targets **6.2.x**, so do not mix code from 6.1.0 with 6.2.x.

## 6. Properly Reading the Created Object from `getTarget()`

### 6.1. `getTarget()` Returns `Object`, Not Generic `T`

`DataBinder` is not `DataBinder<Signup>`. Therefore:

~~~java
Object target = binder.getTarget();

if (target instanceof Signup signup) {
    System.out.println(signup.name());
}
~~~

This is a **fragment** using a binder after a successful `construct` and the `Signup` record from section 4. Use Java 17+ `instanceof` pattern matching to avoid hasty casts.

If the system already controls `targetType` and confirms there are no errors, casting `Signup signup = (Signup) binder.getTarget();` is also valid. However, when handling untrusted input, check whether the target is `null` and verify its type to produce clear diagnostics.

### 6.2. Reliable Verification Order

~~~java
binder.construct(resolver);

BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    // Read errors, do not pass target to business logic.
    return;
}

Object target = binder.getTarget();
if (!(target instanceof Signup signup)) {
    throw new IllegalStateException("Target has not been created");
}

// Only use signup after checking.
~~~

This is a **fragment**, omitting `binder` and `resolver` initialization. In the program in section 4, this entire section has full context.

**Do not misunderstand `getTarget() != null` as proof that the data is valid.** `getTarget()` answers "which object is the binder holding?". `BindingResult` answers "are there any binding/validation errors?". Certain configurations or error timing may leave the object uncreated; check errors and the target in a clear order.

### 6.3. `getBindingResult().getTarget()` and the Model

In a successful creation case:

~~~java
BindingResult result = binder.getBindingResult();
Object viaBinder = binder.getTarget();
Object viaResult = result.getTarget();

System.out.println(viaBinder == viaResult);
~~~

This is a fragment matching the valid example. Both calls point to the same target object, but their **API purposes differ**: `DataBinder#getTarget()` exposes the target managed by the binder, while `BindingResult` provides errors and information for binding/view rendering.

`BindingResult#getModel()` creates a map intended for presentation layers, typically containing two logical entries:

- keyed by `binder.getObjectName()` containing the model attribute;
- keyed by `BindingResult.MODEL_KEY_PREFIX + objectName` containing the `BindingResult` itself.

Example:

~~~java
Map<String, Object> model = result.getModel();
Object attribute = model.get("signup");

boolean hasErrorsEntry = model.containsKey(
        BindingResult.MODEL_KEY_PREFIX + "signup");
~~~

This is a **fragment**; `Map` must be imported and `result` must already exist. `getModel()` is useful in MVC/view flows; when you just want to read the newly constructed object inside a job/service, `getTarget()` is clearer. Do not assume the model map is automatically a JSON response or repository entity.

## 7. What If Conversion Fails?

A string-based request value is not guaranteed to convert to a constructor parameter. For example, `age=not-a-number` cannot convert to `Integer`. In that case, the binder can record a `FieldError` in `BindingResult` with a code in the `typeMismatch` family.

Try this standalone fragment:

~~~java
DataBinder invalid = new DataBinder(null, "signup");
invalid.setTargetType(
        ResolvableType.forClass(Signup.class));

invalid.construct(fromMap(Map.of(
        "name", "Lan",
        "age", "not-a-number",
        "address.city", "Hue"
)));

BindingResult result = invalid.getBindingResult();
System.out.println(result.hasFieldErrors("age"));
~~~

This is a **fragment inside the `ConstructDemo` class** in section 4, reusing the same record and helper. With Spring 6.2.x and default conversion, it is expected to print `true` because `age` cannot be converted. Do not rely on the exact error message text since message codes and locale can affect the rendered message.

To inspect errors in more detail:

~~~java
result.getFieldErrors().forEach(error -> {
    System.out.println("field=" + error.getField());
    System.out.println("code=" + error.getCode());
});
~~~

Avoid returning the raw `getRejectedValue()` to clients if it could be a password, token, identifier, or sensitive data.

### Conversion Errors vs. Constructor Exceptions

Distinguish between:

| Issue | How it is handled |
| --- | --- |
| String `"26"` for `Integer age` | The binder can convert it to `26`. |
| String `"abc"` for `Integer age` | Check `BindingResult`, typically contains a `typeMismatch` error. |
| Parameter name does not match | Resolver may return `null`; check required data and validation policy. |
| Constructor itself throws `IllegalArgumentException` | May lead to `BeanInstantiationException`, not treated as a normal FieldError. |
| Target type unset or initial target non-null | Violates `construct` preconditions; fix API usage. |

Do not promise users that every object creation error ends up in `BindingResult`: a constructor can fail due to its own logic (e.g., invariant checks throwing an exception) or misconfiguration. Catch exceptions only at an appropriate layer, without swallowing errors and proceeding with an invalid target.

## 8. Constructor Parameter Names: Records, Regular Classes, and `-parameters`

Constructor binding relies on argument names. Records usually fit naturally because they have a canonical constructor tied to their components (`name`, `age`, `address`).

For regular Java classes, preserve parameter name metadata during compilation. A suitable Gradle configuration is:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += '-parameters'
}
~~~

In `build.gradle` from section 4, add this snippet if the build does not already enable that flag. Some Spring Boot toolchains already configure `-parameters`; no need to duplicate it if present.

An example constructor-only class:

~~~java
package demo;

public final class CreateOrder {
    private final String sku;
    private final Integer quantity;

    public CreateOrder(String sku, Integer quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public Integer getQuantity() {
        return quantity;
    }
}
~~~

This is a **valid Java file**, though running `construct` requires the Spring dependency, setting `targetType` to `CreateOrder.class`, and providing the keys `sku` and `quantity`. The class does not need setters. If you prefer not to rely on `-parameters`, you can annotate the constructor with `@java.beans.ConstructorProperties({"sku", "quantity"})` when suitable for your design and version.

### When HTTP Names Differ from Java Names

Spring MVC/WebFlux supports `@BindParam` for names passed into constructors, such as hyphenated form names:

~~~java
import org.springframework.web.bind.annotation.BindParam;

public record SearchForm(
        @BindParam("search-text") String text,
        Integer page) {}
~~~

This is a **fragment** that must be placed in a Java file with the proper package and Spring Web dependency. With an HTTP form sending `search-text=java`, MVC can map the input to `text`.

Note: Spring Web's `@BindParam` is not the default mechanism for **every** manually created `DataBinder`. When using `DataBinder` directly as in section 4 and renaming parameters, configure a suitable `DataBinder.NameResolver` or normalize the keys fed into the resolver. Do not assume `search-text` becomes `text` automatically just because an MVC annotation is present in code.

## 9. Nested Objects, Collections, and Indexed Paths

One strength of constructor binding is the ability to construct **child objects via their own constructors**. For example in `Signup`:

~~~java
public record Address(String city) {}

public record Signup(
        String name,
        Integer age,
        Address address) {}
~~~

The input does not have to contain a pre-built `Address` object. As long as the input has the nested key `address.city`, Spring can construct `Address("Hue")` and pass it into `Signup`'s canonical constructor.

For collections, key formatting can look like:

~~~text
items[0].sku=BOOK
items[0].quantity=2
items[1].sku=PEN
items[1].quantity=3
~~~

The records could be:

~~~java
public record LineItem(String sku, Integer quantity) {}

public record Basket(java.util.List<LineItem> items) {}
~~~

This is an **illustrative type definition**, not a full runnable program. Spring constructor binding supports lists/maps/arrays via single-value or indexed-key data. When writing a manual `ValueResolver`, `getNames()` must include all indexed keys so the framework knows which branches have data.

**Limits:** do not allocate enormous collections by default just because a client sends a huge index. Configure appropriate limits on request size, collection size, and the Spring binder. Auto-growing nested paths in **property binding** and constructing nested objects in **constructor binding** are two different processing paths; do not use `setAutoGrowNestedPaths(true)` as a guarantee that all nested constructors will work.

For immutable nested DTOs, design constructors free of side effects and use immutable child types. If a record holds a mutable `List`, immutability is only shallow reference immutability; consider `List.copyOf(...)` in the canonical constructor when domain requirements warrant it.

## 10. `construct`, `bind`, and `validate` Are Not the Same Operation

A common misconception is thinking all three are just different names for "putting data into an object." In reality:

| API | Primary role | Object state |
| --- | --- | --- |
| `construct(ValueResolver)` | Converts input to constructor args and creates the object | Typically starts from a `null` target |
| `bind(PropertyValues)` | Writes properties onto an existing target | Typically uses setter/field access |
| `validate()` | Runs registered validators | Requires a target suitable for checking |
| `getBindingResult()` | Reads binding errors and status | Can be used after construct/bind/validate |
| `getTarget()` | Retrieves the binder's target | May be `null` before creation or after failure |

For a DTO with only a canonical constructor like a record, you usually **do not need to call `bind(...)` after `construct(...)`**. Setter-based property binding adds no value for immutable records and may not be supported for fields without setters.

If a class has setters and the application intentionally combines constructor binding with property binding, Spring allows that design. However, restrict allowed fields and clearly separate required constructor parameters from optional properties.

### Validation Does Not Appear Automatically Just by Calling construct

The standalone program in section 4 creates the object; it **does not automatically run all Bean Validation rules** after `construct`. To invoke a Spring `Validator` manually:

~~~java
DataBinder binder = new DataBinder(null, "signup");
binder.setTargetType(ResolvableType.forClass(Signup.class));

binder.construct(fromMap(inputs));

if (!binder.getBindingResult().hasErrors()
        && binder.getTarget() != null) {
    binder.addValidators(myValidator);
    binder.validate();
}

if (binder.getBindingResult().hasErrors()) {
    // Handle errors.
}
~~~

This is a **fragment**, assuming `myValidator` is an `org.springframework.validation.Validator` supporting `Signup` and already created; `inputs` has data as in section 4. `validate()` runs registered validators and adds errors to `BindingResult`.

In Spring MVC, when a handler declares `@Valid` or `@Validated` on `@ModelAttribute`, the framework can trigger validation in the request lifecycle. **`@InitBinder`** is where you configure the binder/validator before binding, not where you call `construct` manually inside a controller.

## 11. In Spring MVC: Who Calls construct and Where Does the Controller Read It?

Most MVC controllers **do not need to write**:

~~~java
DataBinder binder = new DataBinder(null);
binder.setTargetType(...);
binder.construct(...);
~~~

Spring MVC creates and configures the binder when resolving handler arguments. For an `@ModelAttribute` parameter that is a record, Spring can perform constructor binding, populate the argument, and pass the created object to the controller.

Example fragment in a controller:

~~~java
@PostMapping("/signups")
ResponseEntity<?> create(
        @Valid @ModelAttribute("signup") Signup form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }

    return ResponseEntity.ok(form);
}
~~~

This is a **fragment**, needing imports for `@Valid`, `@ModelAttribute`, `@PostMapping`, `ResponseEntity`, and the `Signup` definition, as well as Spring MVC and a Bean Validation provider if constraints are used. `@Valid` only has practical effect when the DTO carries applicable constraints.

In this controller, **`form` is already the object created and bound by Spring**. The controller does not need to call `binder.getTarget()` itself. `BindingResult` must appear **immediately after** the validated parameter to receive errors for that object.

Correspondence:

~~~text
Java app calling DataBinder directly:
  construct(...) -> getBindingResult() -> getTarget()

Spring MVC controller:
  framework handles @ModelAttribute
  -> handler receives Signup form, BindingResult errors
  -> controller reads form / checks errors
~~~

Beyond `@ModelAttribute`, `@RequestBody` JSON typically goes through an `HttpMessageConverter` (usually Jackson) to deserialize the object. Both can instantiate records, yet **`@RequestBody` does not use the same `DataBinder.construct(ValueResolver)` path meant for form parameters**. Do not generalize findings from `DataBinder`'s constructor binding API to describe all JSON deserialization.

## 12. Common Mistakes When Reading the Target

**Forgetting `setTargetType`.** `new DataBinder(null)` does not know which class to construct yet. To use `construct`, configure `ResolvableType` beforehand.

**Passing an existing target to the binder constructor and still calling `construct`.** That call violates preconditions because the target is no longer `null`. If you need to bind properties onto an existing object, consider `bind(...)`.

**Writing a `ValueResolver` missing `getNames()` in Spring 6.2.** The interface requires both methods; omitting it will not compile. Especially for nested data, an empty name set makes child object construction unreliable.

**Mismatched constructor parameter names.** The source sends `display-name`, while the constructor parameter is `displayName`; without mapping, the resolver may return `null`. Document name mapping conventions and test them thoroughly.

**Calling `getTarget()` too early.** Before `construct`, the binder's target in the example is `null`. Afterward, still check errors and type.

**Checking only the target without checking `BindingResult`.** When conversion errors occur, the binding result is where diagnostics live; do not pass an unvalidated object to services.

**Assuming `construct` runs all validators automatically.** Validation is a separate step that must be triggered per configuration (e.g., `binder.validate()` or `@Valid` in MVC).

**Confusing record constructor binding with setter binding.** Records do not have JavaBean setters; use constructors to supply parameters rather than trying to add setters for `bind`.

**Not restricting input fields.** Constructor binding limits parameters to what the constructor accepts, but if you put `role` or `isAdmin` in a public DTO's constructor, clients can still try sending them. DTOs must expose only permitted fields; enforce authorization in services.

**Sharing a DataBinder across requests.** `DataBinder` holds the target, error state, and conversion configuration; create a fresh instance per binding operation/object rather than reusing it as a mutable singleton across requests.

## 13. Verification and Practice Exercises

### Exercise 1: Creating a Simple Object

Replace `Signup` with the record:

~~~java
public record ProductInput(String sku, Integer quantity) {}
~~~

Build `DataBinder(null, "product")`, set target type `ProductInput.class`, supply keys `sku=BOOK` and `quantity=2`, then call `construct(...)`. Expected output when reading the target:

~~~text
sku=BOOK
quantity=2
~~~

This is the expected output of two print statements, **not yet a standalone Java program**. You can reuse the `fromMap(...)` helper from section 4 to avoid rewriting `ValueResolver`.

### Exercise 2: Conversion Error

Change `quantity=2` to `quantity=two`. After `construct(...)`, run:

~~~java
BindingResult result = binder.getBindingResult();
System.out.println(result.hasFieldErrors("quantity"));
~~~

Check the error instead of immediately casting/reading the target. To display full details, iterate `result.getFieldErrors()` and print field names/error codes.

### Exercise 3: Nested Record

Create `Delivery(String recipient, Address address)` and test the two keys `recipient=An`, `address.city=DaNang`. Verify `ValueResolver.getNames()` includes both keys accurately. The expected outcome is a `Delivery` with a non-null `address` and its corresponding `city` component.

### Pre-Production Application Checklist

- `DataBinder` is created with a `null` target.
- `setTargetType(...)` accurately describes the target class.
- The target type has a clear data constructor whose parameter names can be discovered or mapped.
- `ValueResolver.resolveValue(...)` and `getNames()` accurately reflect the source.
- Type conversion and nested paths are tested.
- After `construct(...)`, `BindingResult` is inspected before using `getTarget()`.
- Target casting/checking is done safely, avoiding null object usage.
- Validation runs separately when needed, while DTOs and services control allowed fields and authorization.

## 14. Takeaways

In Spring Framework 6.2.x, using `DataBinder` for constructor binding follows a clear sequence:

~~~text
new DataBinder(null, objectName)
  -> setTargetType(ResolvableType.forClass(Target.class))
  -> construct(ValueResolver)
  -> getBindingResult() to check for errors
  -> getTarget() to retrieve the created object
~~~

`construct` is responsible for **building the target**, `getTarget` **reads the target**, and `getBindingResult` **tells how far the binding result can be trusted**. These three operations should be understood together, especially when data comes from forms or untrusted external sources.

### Official References

- [Spring Framework 6.2 — Data Binding and Constructor Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html)
- [DataBinder API (Spring Framework 6.2)](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.html)
- [DataBinder.ValueResolver API (Spring Framework 6.2)](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html)
- [Spring MVC — @ModelAttribute argument](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
