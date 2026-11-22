# Building an Object Validator Using RUNTIME Annotations and Reflection in Java

An **object validator** reads the state of an object and returns errors if the data does not satisfy the declared rules. Java allows placing rules near fields using annotations, for example **@Required**, **@NotBlank**, or **@IntRange(min = 18, max = 65)**. If these annotations have **@Retention(RetentionPolicy.RUNTIME)**, the program can use **reflection** to find them and check field values at runtime.

This hands-on exercise builds a small validator in Java 17, **with no framework dependencies**, capable of:

- Rejecting reference fields that are **null** via **@Required**.
- Rejecting null, empty, or whitespace-only strings via **@NotBlank**.
- Checking that integers lie within a closed interval via **@IntRange**.
- Traversing into nested objects via **@ValidNested**, producing error paths such as **address.city**.
- Also reading **private fields**, handling reflection access errors, skipping static/synthetic fields, and sorting results stably.
- Avoiding infinite recursion when the object graph has reference cycles.

This is a way to learn annotation and reflection mechanisms. It is **not a complete replacement for Jakarta Bean Validation**: it does not yet have groups, container elements, custom constraint validators, message interpolation, localization, or the full set of configuration validation rules.

## 1. Overall Processing Flow

A validator can be organized into the following steps:

~~~text
Account object
       |
       v
Iterate over fields using reflection
       |
       +--> Find annotations via getAnnotation(...)
       |
       +--> Read value via Field.get(instance)
       |
       +--> Run corresponding rule:
       |      @Required -> value != null
       |      @NotBlank -> non-blank String
       |      @IntRange -> min <= integer <= max
       |
       +--> @ValidNested -> recurse into child bean
       |
       v
Error list (field path + message)
~~~

**Annotations do not validate data by themselves.** **@IntRange** only stores the two min/max values. It is the code inside **Validator** that reads that metadata, retrieves the actual data, and decides whether there is an error.

Three responsibilities should be separated:

1. **Constraint definitions:** annotations that describe metadata.
2. **Object definitions:** data fields carrying annotations.
3. **Validation mechanism:** the validator combines metadata with current values and returns the result.

With this design, an annotation type can be reused across many different DTOs/entities. When you need to add a rule, you extend the validator or add a dedicated rule model, instead of rewriting manual checks for each class.

## 2. Defining the Four Validation Annotations

All example annotations are placed on **fields**, so **@Target(ElementType.FIELD)** is used. The rules must be read **at runtime**, so **RetentionPolicy.RUNTIME** is chosen.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Required {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface NotBlank {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface IntRange {
    long min();
    long max();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface ValidNested {}
~~~

Here:

- **Required** is a marker annotation; it does not need elements because it only indicates that the field must be non-null.
- **NotBlank** is also a marker; its rule is for **String**, not for numbers or lists. In this exercise's implementation, it **already includes a null check**.
- **IntRange** has two required elements **min()**, **max()**; no arbitrary defaults are chosen because numeric bounds depend on the business domain.
- **ValidNested** is a marker requesting traversal into a nested object if that object exists.
- **@Target(FIELD)** prevents users from placing these rules on classes or methods. It does not by itself guarantee that a field has a type compatible with each rule.
- **@Retention(RUNTIME)** ensures reflection can retrieve the annotation via **Field.getAnnotation(...)** at runtime.

**Note:** If **@Retention** is omitted, the default policy is **RetentionPolicy.CLASS**, which is insufficient for reading annotations via standard reflection. **@Target** and **@Retention** are metadata on the **annotation type**; they do not directly trigger validation logic in the object validator.

### How Are Constraints Expressed?

| Annotation | Expected Field Type | When Is an Error Raised? |
| --- | --- | --- |
| **@Required** | Any reference type | Value is **null** |
| **@NotBlank** | **String** | String is null or **String.isBlank() == true** |
| **@IntRange(min, max)** | **int**, **long**, **Integer**, **Long** in the example | Non-null value is outside the range [min, max] |
| **@ValidNested** | A nested bean | Continues validating annotated fields of the child bean; by itself it does not forbid null |

Because **@IntRange** does not forbid null on its own, for nullable **Integer** or **Long** you need to combine it with **@Required** if a value is mandatory. For primitive **int/long**, null cannot be held; therefore placing @Required on a primitive generally makes no sense.

If **@NotBlank** is placed on an int field, this exercise's validator **reports a type-mismatch annotation usage error** via an exception, instead of silently treating the int as a string or ignoring it.

## 3. Defining the Objects to Validate

We have two classes:

~~~java
final class Address {
    @NotBlank private final String city;

    Address(String city) {
        this.city = city;
    }
}

final class Account {
    @Required @ValidNested private final Address address;
    @IntRange(min = 18, max = 65) private final int age;
    @Required private final String id;
    @NotBlank private final String name;

    Account(String id, String name, int age, Address address) {
        this.id = id;
        this.name = name;
        this.age = age;
        this.address = address;
    }
}
~~~

**Account** has four fields:

- **address**: must be non-null and, if present, must have the rules of **Address** validated. To express both conditions, **@Required @ValidNested** must be combined.
- **age**: has type **int**, and must be between **18 and 65** inclusive of both endpoints.
- **id**: only needs to be non-**null**; an empty string value still passes @Required. If the business logic requires a non-empty string, **@NotBlank** should be used instead or combined with an appropriate rule.
- **name**: @NotBlank rejects **null**, **""**, **"   "**, and strings consisting only of whitespace characters according to the **String.isBlank()** method.

For Address, **city** must be a non-blank string. If an Account has a valid Address but city contains only whitespace, the validator records an error with the **path address.city**.

All fields are declared **private final**. Reflection needs to read them, **not modify them**. This avoids confusing input validation with data mutation: the validator only observes and returns error information.

## 4. Reading Annotations and Field Values with Reflection

A Field object represents a field declared on a class. Important methods:

~~~java
Field[] fields = type.getDeclaredFields();
Required required = field.getAnnotation(Required.class);
Object value = field.get(bean);
~~~

This is an illustrative snippet inside a validator where the variables **type**, **field**, and **bean** already exist and **IllegalAccessException** is handled.

- **Class.getDeclaredFields()** retrieves fields declared directly on a class, including private fields; this call by itself does not return fields of a superclass.
- **Field.getAnnotation(A.class)** returns the annotation of type A when present, or **null** if not found.
- **Field.isAnnotationPresent(A.class)** is suitable when only a boolean is needed.
- **Field.get(bean)** retrieves the field's value on a specific instance; primitive values are boxed into wrappers such as **Integer** or **Long**.
- **Field.getName()** gives the field name; to build error paths for nested beans, append the field name to the prefix.
- **Modifier.isStatic(...)** helps skip static fields because they belong to the class, not to individual object instances.
- **Field.isSynthetic()** helps skip compiler-generated fields, avoiding validating structures not intentionally declared by the DTO author.

**Do not rely on the order returned by getDeclaredFields().** Java reflection does not guarantee a fixed field order; the example sorts by name using **Arrays.sort(fields, Comparator.comparing(Field::getName))** so that test results are reproducible.

### Private Fields and JPMS

For private fields, code calling **Field.get(bean)** from another class is normally subject to Java access control. We use:

~~~java
if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "cannot access " + field.getName());
}
~~~

**trySetAccessible()** attempts to allow the reflection operation to bypass normal Java access checks. If not permitted, it returns false; you should not assume it always succeeds.

In the standalone example running on the classpath, classes belong to the unnamed module, so this operation works. However, if the DTO lives in another **named module**, that module may need to **opens** the corresponding package to the module containing the validator:

~~~java
module application.model {
    opens application.dto to application.validator;
}
~~~

This is a **JPMS illustrative snippet**, valid only when the modules/packages mentioned in the example exist. **exports** does not mean **opens**; exports supports type access under the Java language, whereas opens allows deep reflection into non-public members under the corresponding conditions.

**You should not arbitrarily use --add-opens for every package** in a real application; choose an appropriate access strategy and limit the opened scope. This exercise's validator reports a clear configuration error if a field cannot be read.

## 5. Complete Java 17+ Example, Compiled and Run

Create exactly one file **src/demo/ValidationDemo.java** with all of the code below:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Required {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface NotBlank {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface IntRange {
    long min();
    long max();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface ValidNested {}

final class Address {
    @NotBlank private final String city;
    Address(String city) { this.city = city; }
}

final class Account {
    @Required @ValidNested private final Address address;
    @IntRange(min = 18, max = 65) private final int age;
    @Required private final String id;
    @NotBlank private final String name;

    Account(String id, String name, int age, Address address) {
        this.id = id;
        this.name = name;
        this.age = age;
        this.address = address;
    }
}

final class Validator {
    private Validator() {}

    static List<String> validate(Object root) {
        if (root == null) {
            throw new IllegalArgumentException("root must not be null");
        }
        List<String> errors = new ArrayList<>();
        Set<Object> active = Collections.newSetFromMap(new IdentityHashMap<>());
        visit(root, "", active, errors);
        return List.copyOf(errors);
    }

    private static void visit(Object bean, String prefix,
            Set<Object> active, List<String> errors) {
        if (!active.add(bean)) {
            errors.add(prefix + ": cycle detected");
            return;
        }
        try {
            for (Class<?> type = bean.getClass();
                    type != null && type != Object.class;
                    type = type.getSuperclass()) {
                Field[] fields = type.getDeclaredFields();
                Arrays.sort(fields, Comparator.comparing(Field::getName));

                for (Field field : fields) {
                    if (field.isSynthetic() || Modifier.isStatic(field.getModifiers())) {
                        continue;
                    }
                    Required required = field.getAnnotation(Required.class);
                    NotBlank notBlank = field.getAnnotation(NotBlank.class);
                    IntRange range = field.getAnnotation(IntRange.class);
                    ValidNested nested = field.getAnnotation(ValidNested.class);
                    if (required == null && notBlank == null
                            && range == null && nested == null) {
                        continue;
                    }

                    String path = prefix.isEmpty() ? field.getName()
                            : prefix + "." + field.getName();
                    if (!field.trySetAccessible()) {
                        throw new IllegalStateException("cannot access " + path);
                    }
                    Object value;
                    try {
                        value = field.get(bean);
                    } catch (IllegalAccessException ex) {
                        throw new IllegalStateException("cannot read " + path, ex);
                    }

                    if (required != null && value == null) {
                        errors.add(path + ": must not be null");
                    }
                    if (notBlank != null) {
                        if (field.getType() != String.class) {
                            throw new IllegalArgumentException(
                                    "@NotBlank requires String: " + path);
                        }
                        if (value == null || ((String) value).isBlank()) {
                            errors.add(path + ": must not be blank");
                        }
                    }
                    if (range != null) {
                        Class<?> t = field.getType();
                        if (t != int.class && t != long.class
                                && t != Integer.class && t != Long.class) {
                            throw new IllegalArgumentException(
                                    "@IntRange requires int/long: " + path);
                        }
                        if (range.min() > range.max()) {
                            throw new IllegalArgumentException(
                                    "invalid @IntRange bounds: " + path);
                        }
                        if (value != null) {
                            long number = ((Number) value).longValue();
                            if (number < range.min() || number > range.max()) {
                                errors.add(path + ": must be between "
                                        + range.min() + " and " + range.max());
                            }
                        }
                    }
                    if (nested != null && value != null) {
                        visit(value, path, active, errors);
                    }
                }
            }
        } finally {
            active.remove(bean);
        }
    }
}

public class ValidationDemo {
    public static void main(String[] args) {
        Account valid = new Account("A-01", "Lan", 22,
                new Address("Hà Nội"));
        Account invalid = new Account(null, "  ", 16,
                new Address("  "));
        Account missing = new Account("A-02", "Nam", 30, null);
        show("valid", valid);
        show("invalid", invalid);
        show("missing", missing);
    }

    private static void show(String title, Account account) {
        List<String> errors = Validator.validate(account);
        System.out.println(title + " count=" + errors.size());
        errors.forEach(System.out::println);
    }
}
~~~

Compile and run from the directory containing **src**:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/ValidationDemo.java
java -cp out demo.ValidationDemo
~~~

**Actual stdout of the program:**

~~~text
valid count=0
invalid count=4
address.city: must not be blank
age: must be between 18 and 65
id: must not be null
name: must not be blank
missing count=1
address: must not be null
~~~

The example was **compiled and executed successfully on JDK 21 with --release 17**. The **--release 17** option instructs the compiler to conform to the Java 17 API/language; if the project runs on a specific JDK 17 distribution, verify again in that deployment environment.

### Why Are There Exactly Four Errors on invalid?

For Account invalid:

- **address** is non-null, so @Required on address passes. **@ValidNested** leads the validator into Address.
- **address.city** contains only whitespace, so @NotBlank fails.
- **age = 16**, which lies outside the closed range **[18, 65]**, so @IntRange fails.
- **id = null**, so @Required fails.
- **name = "  "** (two spaces), so @NotBlank fails.

That is **4 errors** in total. The program sorts fields in each class by name, so the errors are in the order **address.city, age, id, name**.

For Account missing, there is only one error: **address: must not be null**. Because address is null, the **@ValidNested** branch does not traverse into a nonexistent object. This prevents accidentally throwing a NullPointerException when reading **address.city**.

For Account valid, all conditions pass, so **validate(...)** returns an **empty List<String>**.

## 6. Reading Each Rule Group Directly

A validator can be viewed as predicates applied to values retrieved from fields.

### 6.1. Required Only Checks for null

~~~java
if (required != null && value == null) {
    errors.add(path + ": must not be null");
}
~~~

The @Required condition **does not forbid empty strings, the number 0, or empty collections**. If the business logic requires those constraints, you should not assume @Required handles them automatically.

**Required on a primitive int** is usually redundant because a primitive field cannot hold null. If you need to represent missing data, you can use a nullable **Integer** with @Required, or a type that expresses absence more explicitly.

### 6.2. NotBlank Validates String

~~~java
if (notBlank != null) {
    if (field.getType() != String.class) {
        throw new IllegalArgumentException(
                "@NotBlank requires String: " + path);
    }
    if (value == null || ((String) value).isBlank()) {
        errors.add(path + ": must not be blank");
    }
}
~~~

**String.isBlank()** has been available since Java 11 and uses Java's whitespace character definition. It returns true for an empty string or a string consisting only of Java-recognized whitespace characters. That fits the Java 17 example.

**Why check the field type first?** Because @Target(FIELD) only restricts declaration placement; it is not enough to guarantee the field is a String. An int field could still be annotated with @NotBlank by an author, so the validator must clearly diagnose misconfigurations.

### 6.3. IntRange Checks a Closed Range

~~~java
IntRange range = field.getAnnotation(IntRange.class);
if (range != null) {
    // Check the field type and min <= max first.
    if (value != null) {
        long n = ((Number) value).longValue();
        if (n < range.min() || n > range.max()) {
            errors.add(path + ": outside allowed range");
        }
    }
}
~~~

This is a **shortened illustrative snippet**; the full version above includes logic to check the exact **int/long/Integer/Long** types, check **min <= max**, and print a message containing both endpoints.

A closed range means **min and max are also valid**. With **@IntRange(min = 18, max = 65)**, the values 18, 22, and 65 pass; 17 and 66 fail.

When an **Integer/Long** wrapper field is null, IntRange in this exercise **skips it** because there is no number to compare. To treat null as an error, combine it with @Required. This design separates **presence** constraints from **value-domain** constraints.

Do not blindly call **longValue()** on arbitrary Number types such as Double, BigDecimal, or BigInteger; the conversion can lose information. The validator intentionally restricts this to only the four types int/long and their wrappers.

### 6.4. ValidNested Recurses

~~~java
if (nested != null && value != null) {
    visit(value, path, active, errors);
}
~~~

**ValidNested does not forbid null on its own**. Combine it with **@Required** if the child bean must not be missing. **path** accumulates field names so an error on Address is reported as **address.city**.

This code only supports **a single direct child object**. If a field holds a **List<Address>**, **Set<Address>**, **Map<String, Address>**, an array, or an Optional, this example does not automatically traverse each element. You need a dedicated design for constructing paths such as **addresses[2].city** and handling nulls, collections, and keys.

## 7. Avoiding Reference Cycles When Validating Nested Beans

An object graph can contain a cycle:

~~~text
Account -> Address -> Owner -> Account
   ^                         |
   +-------------------------+
~~~

If the validator keeps recursing along every @ValidNested without checking, the program risks looping infinitely and throwing a **StackOverflowError**.

The example uses:

~~~java
Set<Object> active =
        Collections.newSetFromMap(new IdentityHashMap<>());
~~~

and:

~~~java
if (!active.add(bean)) {
    errors.add(prefix + ": cycle detected");
    return;
}
try {
    // Traverse fields and possibly recurse into child beans.
} finally {
    active.remove(bean);
}
~~~

Meaning:

- **IdentityHashMap** compares objects by **reference identity**, not by **equals()/hashCode()** that the DTO might define. Two DTOs with equal contents that are two distinct objects do not form a cycle on their own.
- **active** is the set of objects **currently on the active recursion branch**. If an object appears again on the same branch, there is a reference cycle.
- **finally remove(bean)** allows a valid object to be referenced by two independent branches without being mistakenly flagged as a permanent cycle.
- The example chooses to return **a validation error** when a cycle is detected. In a production system, a different policy may be chosen: skipping already-seen branches, limiting depth, or checking cycles with a specialized rule.

The **active** set is created fresh for each call to **Validator.validate(root)**; therefore independent validation runs do not share state. It is not a global cache.

**Note:** This mechanism only detects cycles by reference. It does not turn the validator into a tool for handling arbitrary object graphs; beans may contain library structures or data links that should not be recursively reflected.

## 8. Reading Private Fields via Reflection: Important Limitations

The reflection library has two groups of issues:

**First, access errors:** In a strongly encapsulated module environment, **trySetAccessible()** can return false. This exercise's code throws **IllegalStateException("cannot access ...")**. You should not silently swallow the error and report "object is valid", because then some constraints have not been checked.

**Second, field scope:** **getDeclaredFields()** only includes fields declared directly on the current class. The example uses a loop walking up to superclasses:

~~~java
for (Class<?> type = bean.getClass();
        type != null && type != Object.class;
        type = type.getSuperclass()) {
    Field[] fields = type.getDeclaredFields();
    // Check each field at this level.
}
~~~

This approach allows reading constraints placed on parent fields, even when those fields are private. However, **field shadowing** can cause a subclass and a superclass to declare the same field name: in that case both fields may be traversed, and a path consisting only of the field name will not distinguish them. If complex class hierarchies must be supported, include the **declaring class** in the path or metadata, and define a clear traversal order.

**Third, field ordering:** Sorting with **Comparator.comparing(Field::getName)** ensures the order within each class does not depend on how the JVM initially returns the field array. However, the parent/child classes overall are traversed in the order determined by the loop (the runtime class first, then its superclasses).

**Fourth, static/synthetic fields:** The code skips them to focus on instance state. If an application needs to validate constants or static configuration, that should be a separate concern.

**Fifth, compatibility with Java records:** Records typically have private final fields and component accessors. The example's field reflection mechanism can read these fields when access permits, but a general-purpose validator library should consider the record components API, constructor constraints, and the immutability philosophy of records. Reflection should not be used to write back to final fields.

## 9. Distinguishing Data Errors from Validator Configuration Errors

A good validation system must distinguish:

**Validation violation:** the object contains data that fails a valid rule. For example, **age=16** with **@IntRange(min=18,max=65)** produces an error and is added to the List.

**Annotation misuse / configuration error:** the metadata itself is declared incorrectly for the validator. For example:

~~~java
class WrongConfig {
    @NotBlank int quantity;
    @IntRange(min = 10, max = 1) long score;
}
~~~

In this implementation:

- **@NotBlank** on an int causes an **IllegalArgumentException** because the rule only accepts String.
- **@IntRange(min=10,max=1)** has min greater than max and is therefore also a misconfiguration, rather than a valid range where every number fails.
- If @IntRange is placed on Double or String, the validator reports a type error instead of performing an unsafe conversion.
- If a field to validate is private and cannot be accessed under JPMS, the validator throws **IllegalStateException** instead of silently skipping it.

**Why not treat all of those cases simply as validation messages?** Because input data and programming/rule-declaration errors have different remediation lifecycles. A DTO with invalid data can be fixed by re-entering input; an annotation placed on the wrong type requires fixing code/config and rebuilding/redeploying.

In a production library, configuration errors can be checked **when the validator initializes** or via an **annotation processor at compile time** to catch them earlier. This exercise checks them during runtime traversal to keep the example short and the mechanism clear.

## 10. When to Use Reflection, and When to Use Annotation Processing?

This exercise intentionally uses **RUNTIME + reflection**, because it must read the **current values of an object**. For example:

~~~java
Account account =
        new Account("A-01", "Lan", 22, new Address("Hà Nội"));

List<String> violations = Validator.validate(account);
~~~

The values **"Lan"**, **22**, and **"Hà Nội"** only exist when the program instantiates the object; a processor working on source code at compile time cannot know what data every future runtime object will hold.

Both mechanisms can be combined:

- **Annotation processor (compile time):** verifies that @NotBlank is only placed on String and @IntRange only on compatible integer types; generates metadata or optimized validator code.
- **Reflection (runtime):** retrieves field values from a specific object and then executes the rules.
- **Generated validator (runtime):** replaces reflection with classes pre-generated by the processor, if the goal is to reduce reflection access overhead at runtime.

**Do not infer that simply having @Retention(RUNTIME) makes an annotation execute automatically via a validation engine.** Retention only determines that metadata remains available for reflection to read; the validator must be invoked explicitly.

## 11. Known Limitations Before Going to Production

The demo aims to teach the mechanism properly and has intentional limitations:

| Concern | Current Demo | Extension Direction |
| --- | --- | --- |
| Rule types | Required, NotBlank, IntRange, ValidNested | Design a dedicated registry for **ConstraintValidator** implementations |
| Constraint targets | FIELD | Support METHOD, PARAMETER, RECORD_COMPONENT, or TYPE_USE as needed |
| Output | List<String> | A **Violation(path, code, message, invalidValue)** type; avoid logging sensitive data |
| Nested beans | A single direct object field | Support collection/array/Map with paths containing indices/keys |
| Reference cycles | Returns a cycle error on the recursion branch | Skip policy, depth limit, or specialized graph validation |
| Validation groups | None | Group constraints by scenarios such as create/update |
| Error messages | Hardcoded English strings | Message catalog, localization, parameterized messages |
| Reflection performance | Scans annotations on every call | Cache Field/Rule metadata per Class, control class loader lifecycle |
| Annotation configuration errors | Detected during validation | Compile-time processor or schema check at startup |
| JPMS | trySetAccessible, error if unreadable | Explicit opens configuration or appropriate accessors/method handles |
| Inherited and shadowed fields | Traverses superclasses, names may collide | Store declaring class in metadata/violation |
| Thread safety | Fresh List/active per call | Read-only caches, ensure shared state is immutable when extending |

For real-world business applications, you should evaluate **Jakarta Bean Validation** and a suitable implementation rather than rebuilding the entire validation lifecycle, rule set, validation groups, i18n, and framework integration. The goal of this hands-on exercise is to understand the core mechanism behind how annotation-driven systems work.

### Do Not Automatically Mutate the Object

The validator in the example **does not modify fields** and does not try to turn invalid data into valid data. For instance, name = "  " is blank and therefore returns an error; the code does not automatically trim and reassign the value. Input normalization is a separate step that requires explicit business rules.

**Do not put raw passwords/tokens into errors or logs.** If Violation is later extended to include invalidValue, pay attention to sensitive data. In the demo program, errors contain only the field path and the failed rule.

## 12. Manual Tests and Edge Cases to Add

Cases to test with Account:

| Input Data | Expected Result |
| --- | --- |
| name = "Lan", age=22, id non-null, address.city="Hà Nội" | No errors |
| name = "" or "   " | Error name: must not be blank |
| name = null | Error name: must not be blank |
| id = null | Error id: must not be null |
| id = "" | No Required error (because it is non-null) |
| age = 18 or 65 | No IntRange error |
| age = 17 or 66 | Range error |
| address = null | Error on address from Required; no recursion |
| address.city = " " | Error on address.city |
| root passed to Validator.validate(null) | IllegalArgumentException |
| Cycle A → B → A if both links have @ValidNested | cycle detected error, no infinite recursion |
| @NotBlank placed on int | IllegalArgumentException, not treated as invalid data |
| @IntRange min > max | IllegalArgumentException due to configuration |
| Private field in a module not open for reflection | IllegalStateException when trySetAccessible returns false |

If you want to verify that **reflection truly requires RUNTIME**, try changing an annotation's @Retention to CLASS and recompiling. Under the standard reflection runtime model, that annotation **can no longer be found by Field.getAnnotation(...)**, so the corresponding rule is skipped. This is why default retention cannot be used arbitrarily for a runtime validator.

### Verifying Error Ordering

The demo code uses:

~~~java
Arrays.sort(fields, Comparator.comparing(Field::getName));
~~~

As a result, even though the JVM returns getDeclaredFields in an unspecified order, errors on Account in the example stay in alphabetical order by field name: **address, age, id, name**. Address has only **city**; nested errors appear immediately while processing the address field, before age.

This enables exact stdout testing and avoids flaky tests caused by relying on unguaranteed reflection ordering.

## 13. Common Errors and How to Fix Them

| Error | Cause | Fix |
| --- | --- | --- |
| Annotation has default retention but the validator does not see it | Default is CLASS, not RUNTIME | Declare @Retention(RUNTIME) |
| Specifying @Target(METHOD) but placing it on a field | Target is on the wrong element | Use @Target(FIELD) |
| Calling getAnnotation on Class to find a FIELD annotation | Querying the wrong reflection object | Obtain Field from Class and then call Field.getAnnotation |
| Using getFields() and missing private fields | getFields returns public fields | Use getDeclaredFields and an appropriate access policy |
| Reading a private field directly and hitting IllegalAccessException | Access not yet permitted | Try trySetAccessible, consider JPMS opens |
| Checking only @Required and letting "" strings pass | Required only forbids null | Use NotBlank for String |
| Expecting @IntRange to forbid null on Integer automatically | Range checks the number if present | Combine with @Required |
| Using @NotBlank on int | Field type mismatches the rule | Diagnose annotation misuse |
| Arbitrarily using String.trim().isEmpty() instead of isBlank | The two ways of handling whitespace can differ | Define the semantics explicitly; for example, use isBlank |
| Not sorting getDeclaredFields and testing error ordering | Reflection does not guarantee ordering | Sort Field[] or sort violations |
| Recursing into every object including Java platform objects | May read outside intended scope and hit module restrictions | Only apply @ValidNested to appropriate domain beans |
| Not checking reference cycles | Risk of StackOverflowError | Identity-based recursion stack |
| Swallowing reflection access errors and returning an empty List | Some constraints were never checked | Report a clear error, do not treat as valid |
| Using annotations to hold rules without calling Validator | Annotations are passive metadata | Call validate(...) at an appropriate boundary |
| Placing @Required on an int field expecting to catch "not entered" | Primitive int always defaults to 0 | Use a nullable Integer and @Required if needed |

## 14. Extension Exercises with Solution Guidance

**Exercise 1 — Add @MinLength**

Definition:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface MinLength {
    int value();
}
~~~

Requirements: accept only String fields, check the minimum length; if value < 0, report a configuration error. You need to decide whether null causes an error or requires combining with @Required. A reasonable approach is to skip null as IntRange does, while @NotBlank or @Required handles presence.

**Exercise 2 — Create a Stronger Violation Type Than Strings**

Instead of List<String>, create a Java 17 record:

~~~java
record Violation(String path, String rule, String message) {}
~~~

Example:

~~~text
Violation(path="age", rule="IntRange",
          message="must be between 18 and 65")
~~~

This is a **data representation diagram**, not the default output printed by a Java record in a runnable example. Separating path, rule, and message allows the frontend to handle errors in a structured way, supports message translation, and makes testing more specific.

**Exercise 3 — Support List<Address>**

Given:

~~~java
class Company {
    @ValidNested
    java.util.List<Address> locations;
}
~~~

The current code **does not handle List properly yet**. Detect Collection, iterate over each element, construct paths like **locations[0].city**, and avoid infinite loops caused by reference cycles.

**Exercise 4 — Catch Annotation Configuration Errors at Compile Time**

Write an annotation processor that checks **@NotBlank** is only used on String and **@IntRange** only on int/long/Integer/Long. If a misuse is found, report **Diagnostic.Kind.ERROR**. This processor does not need to know runtime bean values; it only verifies that annotations are placed on the right field types.

**Exercise 5 — Compare with Manual Validation**

Write a Java function that validates Account directly without using annotations. Compare the number of places that must be updated when adding a new object type against the metadata-scanning validator approach. The benefit of annotations is declarativeness/reusability; the cost is reflection, configuration checking, and managing complexity as the system grows.

**Exercise 6 — Try a Named Module Configuration**

Place Account in a different named module and try running the validator. If reflection cannot read private fields, declare **opens** on the DTO package for the validator module using valid module names, then try again. Explain why **exports** is not always sufficient for reading private fields.

## 15. Authoritative References

- **Java SE 17 — java.lang.annotation.Retention:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html — the default retention value is CLASS if not declared.
- **Java SE 17 — java.lang.reflect.Field:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html — get, getDeclaredAnnotations, and field access permissions.
- **Java SE 17 — java.lang.reflect.AccessibleObject:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html — trySetAccessible and behavior under JPMS.
- **Java SE 17 — java.lang.Class.getDeclaredFields():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getDeclaredFields() — retrieving fields declared on a class.
- **Java SE 17 — java.lang.String.isBlank():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#isBlank() — checking whether a string is empty or contains only whitespace.
- **Java Language Specification §9.6.4.2 — @Retention:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2 — retention lifetime of annotation metadata.

**Conclusion:** A validator based on runtime annotations requires three indispensable components: **annotation types describing rules**, **reflection retrieving the right metadata and field values**, and **validation code returning errors according to a defined policy**. RUNTIME retention allows finding rules at runtime, @Target(FIELD) restricts placement targets, and Validator checks the actual data. When extending to collections, inheritance, JPMS, and complex configurations, keep data violations separate from configuration errors and add tests for each case.
