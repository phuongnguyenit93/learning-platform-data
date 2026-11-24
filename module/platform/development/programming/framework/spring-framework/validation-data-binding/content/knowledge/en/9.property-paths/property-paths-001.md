# Simple Property Names and Paths like `address.city` in Spring Data Binding

## 1. What are a property name and a property path?

When Spring binds data onto a Java object, it needs to know how the **target property** is identified by name. A simple property name is a single segment such as `name`, `age`, or `city`. A property path can consist of multiple dot-separated segments to access nested objects, for example `address.city`.

```text
CustomerForm
  name: String
  address: Address
             city: String

Property name: "name"           -> CustomerForm.name
Property path: "address.city"   -> CustomerForm.address.city
```

Spring commonly uses property paths in `BeanWrapper`, `DataBinder`, `WebDataBinder`, `BindingResult`, Spring form binding, and field error messages. These names describe the **object structure**, not database column names or JSON paths in a general sense.

For example, if an object has `getAddress()` and `getAddress().getCity()`, `address.city` is a valid access path. By contrast, `address_city`, `address/city`, and `Address.City` are not automatically equivalent when using standard property access APIs.

## 2. JavaBean properties and simple property names

With the default property access mode, Spring recognizes properties through JavaBeans getters/setters. For example:

```java
public class CustomerForm {
    private String name;
    private int age;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public int getAge() { return age; }
    public void setAge(int age) { this.age = age; }
}
```

`name` and `age` are simple property names. When binding `name=An` and `age=21`, the binder can invoke the corresponding setter, converting `"21"` to `int` before assigning it.

| Source name | Target property | Target type | Behavior |
| --- | --- | --- | --- |
| `name` | `setName(String)` | `String` | Assigns a string value |
| `age` | `setAge(int)` | `int` | Needs string-to-integer conversion when input is `String` |
| `address.city` | `getAddress().setCity(String)` | `String` | Navigates through the `address` object |

JavaBean properties **do not necessarily match** private field names: Spring prioritizes the getter/setter contract in bean property access. A property with only a getter is usually readable but not writable through normal setter access. Direct-field access can be chosen with a separate API, but that is a different access mode and requires design/security consideration.

## 3. Nested paths: `address.city`

Suppose we have two classes:

```java
public class Address {
    private String city;
    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }
}

public class CustomerForm {
    private Address address = new Address();
    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }
}
```

To read `address.city`, Spring first retrieves `CustomerForm.address`, then retrieves the `city` property of `Address`. To write, Spring must navigate to `Address` and then assign `city` through its setter or configured field-access mechanism.

A path can be deeper, such as `shippingAddress.country.code`, if each segment is valid and intermediate objects exist or can be auto-created as configured. Do not assume Spring can create every nested object: constructors, access levels, abstract/interface types, and auto-grow limits all matter.

### Dots are not raw reflection

`BeanWrapper` uses Spring property access abstractions; it is not equivalent to a hand-written chain of Java reflection calls. Spring handles metadata, conversion, exceptions, and supported path forms.

For a nested JavaBean property, the path is interpreted **segment by segment** and each segment must be valid in the target model. If `address` is `null` while auto-grow is disabled, attempting to write `address.city` can raise `NullValueInNestedPathException`. If auto-grow is enabled and Spring can instantiate an `Address`, the operation can succeed. Default states across APIs, constructors, and versions may differ; check the configuration directly when behavior must be guaranteed.

## 4. Complete Java 17+ example with `BeanWrapper`

`BeanWrapper` is an API that lets you manipulate simple property names and nested property paths outside HTTP. Save the file `PropertyPathDemo.java`:

```java
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;

public class PropertyPathDemo {
    public static class Address {
        private String city;
        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }

    public static class CustomerForm {
        private String name;
        private Address address = new Address();

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }
        public Address getAddress() { return address; }
        public void setAddress(Address address) { this.address = address; }
    }

    public static void main(String[] args) {
        CustomerForm customer = new CustomerForm();
        BeanWrapper wrapper = new BeanWrapperImpl(customer);

        wrapper.setPropertyValue("name", "An");
        wrapper.setPropertyValue("address.city", "Da Nang");

        System.out.println(wrapper.getPropertyValue("name"));
        System.out.println(wrapper.getPropertyValue("address.city"));
        System.out.println(customer.getAddress().getCity());
    }
}
```

Stdout:

```text
An
Da Nang
Da Nang
```

Here `wrapper` does not create a copy: it operates on the `customer` instance itself. `setPropertyValue` uses a simple property name for `name` and a nested path for `address.city`; `getPropertyValue` reads back the assigned values.

This example requires compatible Spring Framework libraries (at least the module containing `BeanWrapper` and its dependencies). If all JARs are already in the `SPRING_CP` variable, on Linux/macOS:

```bash
javac -cp "$SPRING_CP" PropertyPathDemo.java
java -cp ".:$SPRING_CP" PropertyPathDemo
```

On Windows, use `;` instead of `:` in the classpath. This is a Java 17+ program with `main`; `javac PropertyPathDemo.java` without the Spring dependencies will fail because the JDK does not provide `org.springframework.beans.*`.

## 5. `DataBinder.bind()` example with simple name and nested path

`DataBinder` accepts `PropertyValues` and applies property paths onto a target. The example below uses the **two nested classes already declared in `PropertyPathDemo`**; the snippet is placed inside a method of another class or inside `main` with appropriate imports:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

PropertyPathDemo.CustomerForm form =
        new PropertyPathDemo.CustomerForm();
DataBinder binder = new DataBinder(form, "customer");

MutablePropertyValues values = new MutablePropertyValues();
values.add("name", "Binh");
values.add("address.city", "Hanoi");

binder.bind(values);
BindingResult result = binder.getBindingResult();

System.out.println(form.getName());
System.out.println(form.getAddress().getCity());
System.out.println(result.hasErrors());
```

Output when using the same `CustomerForm` with an already initialized `address`:

```text
Binh
Hanoi
false
```

`MutablePropertyValues` holds key/value pairs. The binder uses key names to locate the matching JavaBean properties, can convert values before assigning them, and stores any resulting errors in `BindingResult`. If `address.city` does not exist or cannot be written, the result can be affected by `ignoreUnknownFields`, `ignoreInvalidFields`, and binder policies; you should design explicit input acceptance/rejection behavior.

## 6. Paths with collections and maps

Alongside simple names and dot notation, Spring property access can support indexed/mapped syntax when the data types and accessors allow it:

```text
items[0].sku              -> sku property of the first element in items
addresses[1].city         -> city of the second element
attributes[region]        -> value by key region in the map
```

These are **path syntax** examples, not a guarantee that every collection/map will auto-grow. Successful binding depends on Java object structure, collection/map type, generic type (if Spring can infer it), null state, auto-grow limits, and conversion. For instance, `items[99999999].name` must be blocked by configured limits rather than letting clients expand collections arbitrarily.

### Auto-grow limits

`DataBinder` provides mechanisms to control `autoGrowNestedPaths` and `autoGrowCollectionLimit`. When auto-grow is enabled, Spring can instantiate intermediate objects or expand collections within the allowed range. This feature is convenient for form binding, but can consume resources and create an attack surface for user-controlled input. Use allowlists, DTOs, and size/depth limits when accepting untrusted data.

## 7. Binding does not mean unrestricted access to all fields

Property paths are the exact names a client can try to supply, so **mass assignment** is a risk that must be managed. For example:

```java
public class AccountForm {
    private String displayName;
    private boolean admin;
    // getters/setters ...
}
```

If an application binds every parameter onto `AccountForm` without restriction, input `admin=true` can alter a field not meant for clients. With nested paths, input `owner.permissions[0]` also risks reaching deep into the object graph if permitted.

Use an allowlist to restrict fields:

```java
DataBinder binder = new DataBinder(form, "customer");
binder.setAllowedFields("name", "address.city");
binder.bind(values);
```

Names in allowed fields must match the actual property paths. Other paths, such as `address.country` or `admin`, are suppressed when they do not match the policy. You can inspect `binder.getBindingResult().getSuppressedFields()` to detect blocked input. **Do not assume a suppressed field becomes a `FieldError` by default:** the application may need to explicitly return an error when disallowed paths are detected.

## 8. Property paths and error paths in `BindingResult`

When a field fails, Spring records the property path name in `FieldError`. For example, if a form has a numeric `address.zipCode` property and the client sends `abc`, the error field can be `address.zipCode` with a code such as `typeMismatch`.

```java
BindingResult result = binder.getBindingResult();
boolean cityInvalid = result.hasFieldErrors("address.city");
var fieldError = result.getFieldError("address.city");
```

This snippet assumes the `binder` variable exists. If there is an error on the `address.city` field, `fieldError` provides the code, rejected value, and other details. If there is no error, `getFieldError(...)` can return `null`; check before dereferencing.

In a validator, `Errors.rejectValue("address.city", "city.required")` can record a field error under the nested property path. If using `errors.pushNestedPath("address")`, reject calls with field `city` are applied relative to the nested path and require `popNestedPath()` to restore state. Never call `pushNestedPath` and forget to pop before continuing to validate other fields.

## 9. Comparison with syntax at other layers

| Context | Meaning of `address.city` |
| --- | --- |
| `BeanWrapper` | Property path inside a Java object |
| `DataBinder` | Property name used to bind input onto an object |
| `BindingResult` | Field/property path name for tracking errors |
| Spring MVC `@ModelAttribute` | Can be a form parameter name for binding a nested property |
| JSON request body | JSON object is handled by a deserializer; does not necessarily call `DataBinder.bind(PropertyValues)` |
| SQL | Not inherently a column syntax; depends on schema and query |

For example, with HTTP form data:

```text
name=An&address.city=Hue
```

represents two keys, `name` and `address.city`. When the server uses Spring MVC model attribute binding and allows both properties, the binder can assign both corresponding values.

With JSON, nested data typically looks like:

```json
{
  "name": "An",
  "address": { "city": "Hue" }
}
```

Spring MVC can use Jackson or an appropriate message converter to deserialize `@RequestBody`; this is not automatically flattening JSON keys into the string `address.city` along the same property-binding path. In addition, `@RequestParam("address.city")` retrieves a single request parameter named `address.city`, which differs from using a nested path on a model attribute.

## 10. Common mistakes

- **Confusing field names with properties:** the property `getFirstName()` is usually named `firstName`; variants like `first_name` or `firstname` do not all match automatically.
- **Reversing segment order:** `city.address` cannot replace `address.city` when the root object is `CustomerForm`.
- **Null intermediate objects:** if `address == null` and auto-grow cannot create it, the nested path will fail to bind.
- **Missing setter or non-writable type:** a getter-only property is usually not writable through JavaBean property access.
- **Invalid input type:** the path is valid, but the value cannot be converted, leading to a conversion/binding error (for example `typeMismatch`).
- **Wrong collection structure:** `items[0].sku` requires a compatible collection and element type, not merely a string key.
- **Assuming unknown fields always error:** the binder's default ignore-unknown behavior may skip unrecognized paths; configure an explicit policy.
- **Allowing overly broad paths:** risks mass assignment and uncontrolled object graph expansion.
- **Confusing `DataBinder` with validation:** binding to a path does not guarantee values satisfy business rules; invoke a validator when needed.

## 11. Practice checklist

1. Identify the root object and the actual JavaBean property names.
2. Use simple names (`name`) or nested paths (`address.city`) matching the structure.
3. Ensure intermediate objects exist or configure auto-grow appropriately.
4. Check property readability/writability and converters for non-string types.
5. Set an allowlist of property paths from untrusted data sources.
6. Inspect `BindingResult`, including field errors and suppressed fields.
7. Test valid input, null nested objects, wrong names, wrong types, and overly deep collection paths.

**Key takeaway:** `name` is a simple property; `address.city` is a chain of properties joined to access a nested object. Spring uses property paths to bind and report errors, but writability and safety depend on JavaBean structure, conversion, binder configuration, and the access rules set by the application.
