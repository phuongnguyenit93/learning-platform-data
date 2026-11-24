# Missing, Unreadable, or Unwritable Property Errors in Spring Data Binding

Spring Framework uses **property paths** to locate data inside Java objects, such as `name`, `address.city`, and `items[0].price`. When working with `BeanWrapper` or `DataBinder`, a property name may **not exist**, **exist yet be unreadable**, or **exist yet be unwritable**. These three errors sound similar, but differ in root cause, exception, impact on data binding, and remediation.

For instance, a form sends `displayNmae=Lan` (a typo), a class has `getStatus()` without `setStatus(...)`, or `address` is `null` when code attempts to write `address.city`. Sometimes Spring throws an exception, sometimes it silently ignores unknown fields under binder defaults, and sometimes it records a `FieldError` in `BindingResult`. **Do not assume every property error becomes HTTP 400 or produces a `FieldError`.**

This lesson focuses on how Spring views property paths in the **Property Paths** topic group, specifically JavaBean property access, exceptions in `org.springframework.beans`, `DataBinder` policies, and diagnostic testing. Hands-on examples use Java 17 with Spring Framework 6.2.x.

## 1. Property paths and read/write requirements

| Expression | Traversal through object |
| --- | --- |
| `name` | Direct property of the object |
| `address.city` | Retrieve `address` object, then access `city` |
| `contacts[0].email` | First element in `contacts` collection/array, then property `email` |
| `preferences['theme']` | Key `theme` in a compatible map |

Example with two classes:

```java
public class ProfileForm {
    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}

public class Address {
    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
```

With **JavaBean property access**, `address.city` is resolved by navigating through `getAddress()` and the accessors of `city`. On write, Spring normally must find an existing nested object, or instantiate one per configuration, and then invoke the leaf property's setter.

Three separate questions apply:

1. **Is the path syntax/name accurate?** `address.city` is not `adress.city`.
2. **Is the access direction supported?** Reading requires a getter; writing requires a setter or equivalent access mechanism.
3. **Are the object state and input value valid?** A nested object might be `null`, `"abc"` cannot convert to `Integer`, or a getter/setter might throw an exception.

A property genuinely existing on a class **does not guarantee every operation on it will succeed**.

## 2. Case 1: property does not exist

If a form submits `displayNmae` when the DTO only has `displayName`, Spring does not recognize that name under standard JavaBeans rules.

```java
BeanWrapperImpl wrapper = new BeanWrapperImpl(new ProfileForm());
boolean existsForRead = wrapper.isReadableProperty("displayNmae");
boolean existsForWrite = wrapper.isWritableProperty("displayNmae");
```

Both results are typically `false`. Direct access:

- Reading via `getPropertyValue("displayNmae")` can throw `NotReadablePropertyException`.
- Writing via `setPropertyValue("displayNmae", value)` can throw `NotWritablePropertyException`.

Those are two **operation-specific** exceptions, rather than a dedicated exception named `UnknownPropertyException`. Missing names are normally surfaced at access time.

**Key difference with `DataBinder`:** `setIgnoreUnknownFields(boolean)` defaults to **`true`**. When calling `DataBinder.bind(PropertyValues)`, input fields that do not match a property can be **ignored**. That means a misspelled field name can silently drop input rather than throwing or writing unexpectedly.

## 3. Case 2: property is unreadable

A JavaBean property can have a setter without a getter:

```java
public class LoginForm {
    private String oneTimeCode;

    public void setOneTimeCode(String oneTimeCode) {
        this.oneTimeCode = oneTimeCode;
    }

    // Intentionally omit getOneTimeCode().
}
```

This is a **write-only** property. `BeanWrapperImpl.isWritableProperty("oneTimeCode")` can return `true`, whereas `isReadableProperty("oneTimeCode")` returns `false`. Calling:

```java
wrapper.getPropertyValue("oneTimeCode");
```

on a wrapper around such a `LoginForm` typically throws **`NotReadablePropertyException`**.

Similar situations occur when:

- The getter is missing or does not follow `getX()`/`isX()` naming conventions.
- The getter lacks appropriate visibility for JavaBeans introspection.
- An intermediate property in a nested path lacks a getter: attempting to reach `address.city` when the root class only has `setAddress(Address)`.
- A getter exists yet throws an exception itself: that is an **accessor invocation error**, not necessarily `NotReadablePropertyException`.

Do not rush to add getters for secret fields if the application does not need to read them back. Design forms and processing logic to fit storage and security needs.

## 4. Case 3: property is unwritable

A JavaBean has a getter without a setter:

```java
public class OrderView {
    private final String status = "NEW";

    public String getStatus() {
        return status;
    }

    // No setStatus(String).
}
```

`status` is a **read-only** property. It can be read via its getter, yet attempting to write with:

```java
BeanWrapperImpl wrapper = new BeanWrapperImpl(new OrderView());
wrapper.setPropertyValue("status", "APPROVED");
```

typically throws **`NotWritablePropertyException`** because there is no matching JavaBeans write method.

A property can also be unwritable if its setter is misnamed, non-public when required, has an incompatible type, or because the binder uses a different access mode than assumed. However, not every write failure is `NotWritablePropertyException`: if a real setter throws an exception, the cause is different; if a converter cannot convert a string to the setter's parameter type, that is a **type mismatch**.

Do not add setters to server-owned fields (`role`, `approved`, `status`) merely to silence binding errors. If those fields are not valid client inputs, omit them from the input DTO or manage them in the business layer.

### Read/write capability comparison table

| JavaBeans structure | Read | Write | Typical failure mode |
| --- | --- | --- | --- |
| Valid getter and setter | Yes | Yes | Can still fail on conversion or method invocation |
| Getter only | Yes | No | Write: `NotWritablePropertyException` |
| Setter only | No | Yes | Read: `NotReadablePropertyException` |
| Property absent | No | No | Direct access: direction-specific exception; `DataBinder` may ignore unknown keys |
| Valid nested property with `null` intermediate | Depends on state | Depends on auto-grow | `NullValueInNestedPathException` if unable to traverse |

"Yes" in the table only refers to accessor discovery; it guarantees neither that getters/setters will not throw nor that type conversion will succeed.

## 5. Exception hierarchy in Spring Beans

Key classes reside in package `org.springframework.beans`:

| Exception | Typical meaning |
| --- | --- |
| `InvalidPropertyException` | Referenced path or property is invalid; superclass of several specific exceptions |
| `NotReadablePropertyException` | Cannot read property, commonly missing getter |
| `NotWritablePropertyException` | Cannot write property, commonly missing setter, or property does not exist |
| `NullValueInNestedPathException` | Navigating a nested property whose intermediate value is `null` |
| `TypeMismatchException` | Cannot convert input value into the required target type |
| `MethodInvocationException` | Getter/setter exists yet throws an exception during invocation |
| `PropertyBatchUpdateException` | Multiple property access errors reported together during batch updates |

The first three subclasses relate to invalid paths as follows:

```text
InvalidPropertyException
├── NotReadablePropertyException
├── NotWritablePropertyException
└── NullValueInNestedPathException
```

`TypeMismatchException` and `MethodInvocationException` do not sit under these three branches; they represent value-conversion or accessor-execution failures. Catching `InvalidPropertyException` therefore does not mean every binding failure has been caught.

**Do not confuse these with constraint violations.** `@NotBlank`, `@NotNull`, `@Min`, or `@Email` belong to data validation (Jakarta Bean Validation). A property can be completely readable/writable and still violate constraints.

## 6. Runnable Java 17 example: BeanWrapper and DataBinder

This hands-on example needs neither Spring Boot nor an HTTP server. Its goal is to show clearly:

- `BeanWrapperImpl` recognizing read-only, write-only, and non-existent properties.
- Nested path access hitting `null` when auto-grow is disabled.
- `DataBinder` ignoring unknown fields by default, auto-creating nested objects when possible, yet still recording conversion errors in `BindingResult`.

### 6.1. Gradle structure

```text
property-path-errors/
├── settings.gradle
├── build.gradle
└── src/main/java/example/PropertyPathErrorsDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'property-path-errors'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'example.PropertyPathErrorsDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Use JDK 17+ and a compatible Gradle version with access to Maven Central to download dependencies on first run. `spring-context` brings in the Spring modules used by the demo.

### 6.2. Complete code

**`src/main/java/example/PropertyPathErrorsDemo.java`**

```java
package example;

import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.NotReadablePropertyException;
import org.springframework.beans.NotWritablePropertyException;
import org.springframework.beans.NullValueInNestedPathException;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class PropertyPathErrorsDemo {

    public static class Address {
        private String city;

        public Address() {
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class Profile {
        private String name;
        private Integer age;
        private Address address;
        private String status = "NEW";
        private String secret;

        public Profile() {
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }

        public String getStatus() {
            return status;
        }

        // Intentionally omit setStatus(String).

        public void setSecret(String secret) {
            this.secret = secret;
        }

        // Intentionally omit getSecret().
    }

    public static void main(String[] args) {
        Profile inspect = new Profile();
        BeanWrapperImpl wrapper = new BeanWrapperImpl(inspect);

        System.out.println("nameReadable="
                + wrapper.isReadableProperty("name"));
        System.out.println("statusWritable="
                + wrapper.isWritableProperty("status"));
        System.out.println("secretReadable="
                + wrapper.isReadableProperty("secret"));
        System.out.println("secretWritable="
                + wrapper.isWritableProperty("secret"));
        System.out.println("ghostReadable="
                + wrapper.isReadableProperty("ghost"));

        try {
            wrapper.setPropertyValue("status", "APPROVED");
        } catch (NotWritablePropertyException ex) {
            System.out.println("statusWrite="
                    + ex.getClass().getSimpleName());
        }

        try {
            wrapper.getPropertyValue("secret");
        } catch (NotReadablePropertyException ex) {
            System.out.println("secretRead="
                    + ex.getClass().getSimpleName());
        }

        wrapper.setAutoGrowNestedPaths(false);
        try {
            wrapper.setPropertyValue("address.city", "Hue");
        } catch (NullValueInNestedPathException ex) {
            System.out.println("nullNested="
                    + ex.getClass().getSimpleName());
        }

        Profile form = new Profile();
        DataBinder binder = new DataBinder(form, "profile");

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("name", "Lan");
        values.add("address.city", "Hue");
        values.add("ghost", "unexpected");
        values.add("age", "not-a-number");

        binder.bind(values);

        System.out.println("name=" + form.getName());
        System.out.println("city=" + form.getAddress().getCity());
        System.out.println("ageError="
                + (binder.getBindingResult().getFieldError("age") != null));
        System.out.println("errorFields="
                + binder.getBindingResult().getFieldErrors().stream()
                        .map(FieldError::getField).toList());
    }
}
```

Run from the project directory:

```bash
gradle -q run
```

If a Gradle wrapper is present, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows.

**Expected stdout:**

```text
nameReadable=true
statusWritable=false
secretReadable=false
secretWritable=true
ghostReadable=false
statusWrite=NotWritablePropertyException
secretRead=NotReadablePropertyException
nullNested=NullValueInNestedPathException
name=Lan
city=Hue
ageError=true
errorFields=[age]
```

Explanation:

1. `name` has both getter and setter; it is readable.
2. `status` has only a getter, so it is unwritable; writing directly throws `NotWritablePropertyException`.
3. `secret` has only a setter, so it is unreadable; reading directly throws `NotReadablePropertyException`.
4. `ghost` is not a JavaBean property on `Profile`; `isReadableProperty("ghost")` is `false`.
5. `inspect.address` is `null`; with auto-grow off on `wrapper`, trying to write `address.city` throws `NullValueInNestedPathException`.
6. A separate `DataBinder` defaults to auto-grow nested paths = `true`; it can instantiate `Address()` and write `city="Hue"`, because the child class has a no-arg constructor and matching accessors.
7. `DataBinder` defaults to ignore unknown fields = `true`, so `ghost` is skipped and produces no field error here.
8. `age` is an `Integer` with a setter, yet `"not-a-number"` fails numeric conversion; the binder records a `FieldError` for `age` in `BindingResult`.

**Why use two objects?** `inspect` is used for direct `BeanWrapperImpl` operations, while `form` is used for the binder. Disabling auto-grow on the first wrapper does **not** affect the new binder. This keeps the two policies separate so each failure mode is clear.

## 7. Two easily confused flags: ignoreUnknownFields and ignoreInvalidFields

`DataBinder` provides important options:

| Option | Default | Meaning |
| --- | --- | --- |
| `setIgnoreUnknownFields(boolean)` | `true` | Ignores inputs without a corresponding property |
| `setIgnoreInvalidFields(boolean)` | `false` | Ignores certain inputs whose path is declared yet currently unreachable, e.g., a `null` nested segment |
| `setAutoGrowNestedPaths(boolean)` | `true` on a standard DataBinder | Attempts to instantiate nested objects when encountering `null` and creation is possible |

These settings apply to **property binding** via `bind(PropertyValues)`, do not govern normal value lookup through `BindingResult`, and are not equivalent settings for constructor binding.

### 7.1. Unknown field

```java
DataBinder binder = new DataBinder(new Profile(), "profile");
binder.setIgnoreUnknownFields(true); // Default value.
```

When a request sends `ghost=foo` and the target has no `ghost` property, the binder can ignore the key. To detect unknown fields instead of skipping them:

```java
binder.setIgnoreUnknownFields(false);
```

Then `bind(...)` on a non-existent property can throw `NotWritablePropertyException` rather than creating a standard `FieldError`. Therefore never check only `BindingResult.hasErrors()` and conclude the request had no unknown fields; understand the exception mechanism and binder policy.

### 7.2. Invalid field

This is the case where the property/path name is valid, yet **the path has no reachable object**:

```java
DataBinder binder = new DataBinder(new Profile(), "profile");
binder.setAutoGrowNestedPaths(false);
binder.setIgnoreInvalidFields(false); // Default value.
```

If binding `address.city=Hue` while `address` is `null`, `NullValueInNestedPathException` can occur. If business rules genuinely require skipping inputs for absent child objects, consider:

```java
binder.setIgnoreInvalidFields(true);
```

However, this **does not create the child object**; it only allows skipping certain unreachable paths per binder policy. Do not enable it indiscriminately to hide an object-design bug. When a field must be persisted, fix the DTO structure or initialization.

### 7.3. Auto-grow nested paths

If `Profile.address == null`, yet `Address` has a no-arg constructor, getters/setters, and matching type metadata, DataBinder can:

```text
input: address.city=Hue
  -> instantiate Address() for Profile.address
  -> call setCity("Hue")
  -> Profile.address.city == "Hue"
```

Still, auto-grow **does not guarantee** creating every interface, abstract type, non-instantiable class, or arbitrary collection. For collections/indices, Spring also enforces an auto-grow limit to control size and memory cost.

When debugging, ask in order: **is the path spelled right -> is the property readable/writable -> is an intermediate object null -> how is auto-grow configured**.

## 8. Nested paths: errors can occur at any level

Consider:

```text
Order
└── shippingAddress
    └── country
        └── code
```

With `shippingAddress.country.code`, failure can happen at any segment:

- `shippingAdress` is misspelled -> path does not exist.
- `Order` has `setShippingAddress(...)` without `getShippingAddress()` -> cannot navigate to reach `country`.
- `shippingAddress == null` -> may need auto-grow or pre-initialization.
- `country == null` while its type is an interface without an instantiation path -> auto-grow can fail.
- `code` has only a getter -> readable yet lacks a setter to write.
- `code` has `setCode(Integer)` while client sends `abc` -> type mismatch, not a writable error.
- `getCountry()` exists yet throws an exception -> method invocation error, not a missing getter.

Spring also supports property paths across lists/maps like `items[0].sku`; for indices/keys, verify the collection is initialized, element types are clear, auto-grow limits apply, and bracket syntax is accurate.

If using `Errors.rejectValue("shippingAddress.country.code", ...)` to add a validation error, that call does not auto-create child objects. With `BeanPropertyBindingResult`, resolving the field value for error reporting can still require path segments to be traversable. Do not use validator nested paths to mask object-graph bugs.

## 9. Getters/setters, property names, and access modes

Property names follow JavaBeans conventions. For example:

```java
private String displayName;

public String getDisplayName() {
    return displayName;
}

public void setDisplayName(String displayName) {
    this.displayName = displayName;
}
```

The recognized property is `displayName`. Other request keys like `display_name`, `displayname`, or `DisplayName` should not be assumed equivalent without a dedicated mapping mechanism.

Common pitfalls:

- `getFullname()` and `setFullName(...)` differ in casing, producing mismatched property names.
- `getURL()` follows special acronym capitalization rules in JavaBeans introspection.
- For primitive `boolean`, `isActive()` is the standard read method; for wrapper `Boolean`, `getActive()` is clearer.
- Setters taking mismatched types or inconsistent overloads can cause Spring to pick an unexpected accessor.
- Making getters/setters `private` prevents standard JavaBeans introspection from treating them as public accessors.

**Private fields are normal.** A JavaBean with `private` fields and public getters/setters binds cleanly. Conversely, having a field with the same name as a request key does not make it bind automatically if required getters/setters are missing.

Spring lets you call `binder.initDirectFieldAccess()` to access fields directly in certain scenarios. This mode differs from **default JavaBean property access**; do not treat it as "make every field writable" to fix errors, since it can widen the data surface clients can alter.

## 10. Conversion and validation errors are not unwritable property errors

Suppose a class has:

```java
private Integer age;

public Integer getAge() {
    return age;
}

public void setAge(Integer age) {
    this.age = age;
}
```

A client sends `age=abc`. `age` exists with valid getter/setter. The failure here is that Spring **cannot convert** `"abc"` to `Integer`; in `DataBinder.bind(...)`, this is normally represented as a `FieldError` with code `typeMismatch`.

```java
BindingResult result = binder.getBindingResult();
FieldError ageError = result.getFieldError("age");
if (ageError != null) {
    System.out.println(ageError.getField());
    System.out.println(ageError.getCode());
}
```

This snippet illustrates code inside a method with an existing `binder` variable and appropriate imports. `getCode()` is typically `typeMismatch` for conversion errors; `getCodes()` provides more specific codes for message resolution.

Conversely, if `age=17` converts to `Integer` cleanly yet violates a `@Min(18)` constraint, that is a **validation** error, not a conversion failure or missing setter.

Quick distinction:

| Error | Root cause |
| --- | --- |
| `NotReadablePropertyException` | No valid read path |
| `NotWritablePropertyException` | No valid write path |
| `NullValueInNestedPathException` | An intermediate object along the path is `null` |
| `FieldError` with code `typeMismatch` | Input value cannot convert to the property type |
| `FieldError` with constraint code, e.g., `NotBlank` | Value fails a validation rule |
| `MethodInvocationException` | Accessor threw an exception during execution |

Do not try to solve conversion errors by adding an already-existing setter, or solve read-only errors by disabling validation.

## 11. In Spring MVC: why is BindingResult sometimes empty of errors?

Form-handling controller:

```java
@PostMapping("/profiles")
public String update(
        @Valid @ModelAttribute("profile") ProfileForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "profiles/edit";
    }
    return "profiles/success";
}
```

This is an **illustrative integration snippet**, belonging inside an MVC controller with matching imports and views. `BindingResult` must immediately follow the model attribute it serves.

Not every failure becomes a `FieldError`:

1. **Non-existent fields** can be skipped because `ignoreUnknownFields=true`.
2. **Unconvertible field values** normally produce a type-mismatch `FieldError`.
3. **Unrecoverable access errors** can throw an exception and abort binding before the controller checks `BindingResult`.
4. **Constraint validation** runs only when a matching validator/trigger is active.
5. With `@RequestBody` JSON, Spring uses an `HttpMessageConverter` (typically Jackson); JSON errors can produce `HttpMessageNotReadableException`, distinct from BeanWrapper's `NotReadablePropertyException`.

The binder can be configured locally:

```java
@InitBinder("profile")
void configure(WebDataBinder binder) {
    binder.setIgnoreUnknownFields(false);
    binder.setAllowedFields("name", "age", "address.city");
}
```

This snippet is illustrative only, assuming matching attribute name and DTO. `setAllowedFields` restricts **which fields are allowed to bind**, while `setIgnoreUnknownFields(false)` controls handling of **unknown properties** after filtering. Fields absent from the allowlist can be suppressed before unknown-field handling runs; do not expect this setup alone to detect every out-of-contract parameter.

**Security:** never bind client input directly onto JPA/domain entities containing `role`, `isAdmin`, `creditLimit`, or `approved`. Create an input DTO with only user-editable fields. Fixing `NotWritablePropertyException` by adding public setters everywhere can introduce a *mass assignment* vulnerability.

## 12. Debug in order so you do not apply the wrong fix

1. **Get the exact property name.** Compare the request key, exception message, and JavaBean property; check casing, indices, and dots carefully.
2. **Verify the target object.** Which class is the binder inspecting? Could it be an unexpected subtype? Prior to binding, are nested values null?
3. **Distinguish the binding mechanism.** `@ModelAttribute` JavaBean, direct field access, constructor binding, or `@RequestBody` JSON?
4. **Inspect accessors.** Does the leaf field have a matching public setter? Do intermediate steps have getters? Are getters/setters named accurately?
5. **Use Spring's tools.** Call `isReadableProperty(path)` and `isWritableProperty(path)` on a test object's `BeanWrapperImpl`; for nested paths, results also depend on object state and auto-grow settings.
6. **Read the exact exception.** `NotReadablePropertyException` differs from `NotWritablePropertyException`; `NullValueInNestedPathException` differs from `TypeMismatchException`.
7. **Check binder configuration.** `ignoreUnknownFields`, `ignoreInvalidFields`, `autoGrowNestedPaths`, `allowedFields`, and `directFieldAccess`.
8. **Inspect recorded errors.** `binder.getBindingResult().getFieldErrors()` reveals conversion/validation errors, yet does not capture every skipped input.
9. **Read the root cause.** When getters/setters throw exceptions, fix the method body rather than renaming fields blindly.
10. **Write a small test.** Separate direct BeanWrapper access from a DataBinder with field-ignoring policies. Never compare different configurations on the same binder instance that already holds prior errors.

### Diagnosing with property descriptors

You can inspect JavaBeans methods with `java.beans.Introspector`, though `BeanWrapperImpl` is more practical when verifying **whether Spring itself can read/write a path under the current configuration**. Even when `isWritableProperty` is `true`, a setter can still throw and conversion can still fail; it checks access capability, not input validity.

## 13. Practical troubleshooting matrix

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Client sends `fristName`, DTO has `firstName` | Input typo | Fix key, verify with real request |
| `status` readable yet reports not writable | Getter only | Do not bind server-owned fields; or choose proper DTO/constructor binding |
| `secret` writable yet reading throws | Setter only | Add getter only with sound justification, or do not read back secret |
| `address.city` reports null nested path | `address` is null, auto-grow off/cannot instantiate | Pre-initialize nested object or fix structure |
| `address.city` reports not readable | Missing getter on intermediate property | Check `getAddress()` before `getCity()` |
| `age=xyz` causes typeMismatch | String cannot convert to Integer | Return field error, fix input/converter |
| Setter exists yet exception thrown | Setter method throws internally | Inspect cause wrapped inside method invocation |
| No error seen for unknown field | Binder ignores unknown fields by default | Check DTO, request keys, and ignoreUnknownFields flag |
| Enabling ignoreInvalidFields loses values | Nested path was skipped | Fix object graph; ignore only when business rules allow |
| Same DTO fails on JSON | Deserializer differs from JavaBean form binding | Check Jackson/HTTP converter and JSON shape |
| Opening setters on all fields to silence errors | Overly broad write surface | Create input DTO, restrict allowed fields |

## 14. Practice: spot the bug in a nested object

Given two classes:

```java
public class PaymentForm {
    private String reference;
    private Account account;

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }

    public Account getAccount() {
        return account;
    }

    // No setAccount(Account).
}

public class Account {
    private String iban;

    public String getIban() {
        return iban;
    }

    public void setIban(String iban) {
        this.iban = iban;
    }
}
```

Suppose `account == null`:

1. Is `reference` readable/writable via JavaBeans? Why?
2. Why can `account.iban` fail even though `Account` has `setIban(...)`?
3. Why does `setPropertyValue("account", new Account())` on `BeanWrapperImpl` fail?
4. If input contains key `referrence` (typo), will default `DataBinder` necessarily produce a `FieldError`?
5. How does a type error when binding `reference` differ from violating a `@NotBlank` constraint?

**Guided answers:** (1) Has both getter and setter. (2) Must cross `account`, which is currently null; auto-grow can fail due to lacking a write path on `account` to attach the new instance. (3) Missing `setAccount`, so it can throw `NotWritablePropertyException`. (4) No; unknown fields can be ignored by default. (5) Conversion/property access is a different mechanism from validation constraints; inspect the exact error type.

## 15. Summary and references

- **Does not exist:** property/path name is misspelled or absent on the object; `DataBinder` ignores many unknown fields by default.
- **Unreadable:** lacks read path, usually missing getter -> `NotReadablePropertyException`.
- **Unwritable:** lacks write path, usually missing setter -> `NotWritablePropertyException`.
- **Null nested object:** check auto-grow or pre-initialize valid objects -> may see `NullValueInNestedPathException`.
- **Has setter yet wrong input type:** check conversion and `BindingResult`, commonly `typeMismatch`; do not confuse with unwritable.
- **Never fix errors by opening every setter or silently ignoring all fields:** align the data model, write allowlist policy, and endpoint contract.

Primary references to verify APIs and behavior:

- [Spring Framework — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html): ignore flags, auto-grow, bind, and BindingResult.
- [Spring Framework — BeanWrapperImpl](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/BeanWrapperImpl.html): property access, getters/setters, nested paths.
- [Spring Framework — NotReadablePropertyException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/NotReadablePropertyException.html), [NotWritablePropertyException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/NotWritablePropertyException.html), and [NullValueInNestedPathException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/NullValueInNestedPathException.html): common property access errors.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): principles of property/constructor binding and field control.
- [Spring Framework — MVC @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): form binding/validation through controllers.
