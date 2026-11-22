# Annotations Do Not Automatically Execute Validation or Business Behavior

## 1. Annotations are metadata, not self-executing commands

Java annotations are used to **attach structured information** to programs: classes, fields, methods, constructors, parameters, and other elements permitted by `@Target`. Example:

~~~java
class Registration {
    @RequiredText
    String username;

    @Minimum(18)
    int age;
}
~~~

The snippet above is illustrative only, using two custom annotations `@RequiredText` and `@Minimum` that will be presented in full in the runnable example below.

When the class is instantiated or a field is assigned a value, Java does **not automatically** read `@RequiredText`, check for blank strings, read `@Minimum(18)`, and reject an age under 18. An annotation only describes a *potential rule*. For that rule to take effect, **there must be a component that understands the metadata and executes behavior**:

- A compiler or annotation processor reads annotations at compile time, when designed to do so.
- A framework/container/runner reads annotations at runtime and invokes an appropriate validation engine, interceptor, mapper, test runner, or business logic.
- The application itself uses Reflection to look up annotations and **explicitly** runs checking/enforcement code.

Three conceptual layers must be separated:

1. **Declaration**: `@Minimum(18)` attaches the value 18 to metadata.
2. **Reading metadata**: `field.getAnnotation(Minimum.class)` returns the annotation information if it is accessible at runtime.
3. **Enforcing the rule**: code reads `minimum.value()`, compares the field value, decides to accept/reject, and handles the outcome.

Layer 1 alone does not automatically produce layer 3. Even layer 2 does not make validation run if the program does not use the metadata to make decisions.

**To be precise:** A custom annotation itself contains no “trigger when value changes” mechanism. Java has several standard annotations understood in specific ways by the compiler or tools, such as `@Override` (compiler checks method overriding) or `@Deprecated` (warns on API usage). Those are still **other tools processing metadata**, not an annotation running a validate method by itself at runtime.

## 2. `@Retention(RUNTIME)` makes annotations readable, but creates no behavior

For Reflection to read an annotation from a class file, the annotation type normally needs `@Retention(RetentionPolicy.RUNTIME)`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface RequiredText {
}
~~~

This is an annotation definition that can be read by Reflection at runtime; **it does not check any value yet**.

| Retention policy | Meaning | Runtime `getAnnotation(...)` |
| --- | --- | --- |
| `SOURCE` | Annotation belongs only to source scope, not stored in the class file | Not visible |
| `CLASS` | Annotation may reside in the class file but is not retained for runtime Reflection access | Not visible |
| `RUNTIME` | Metadata is retained so Reflection can look it up at runtime | Visible if the annotation exists on the queried element |

`@Target(ElementType.FIELD)` restricts where `@RequiredText` may be placed to **fields**; it does not declare that any field must contain a non-empty string. If placed mistakenly on a method, the compiler may reject it because of `@Target`; that is a syntax/metadata rule, not user-data validation.

When an annotation type omits `@Retention`, the default is `RetentionPolicy.CLASS`. Therefore, if writing an annotation meant for runtime Reflection processing, check retention explicitly. However, **`RUNTIME` is only a condition for reading metadata, not a trigger** activating an engine.

## 3. Standalone runnable Java 17+ example: annotations exist yet a validator must still be called

Create a single file named **`AnnotationValidationDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface RequiredText {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Minimum {
    int value();
}

class Signup {
    @RequiredText
    public String username;

    @Minimum(18)
    public int age;

    Signup(String username, int age) {
        this.username = username;
        this.age = age;
    }
}

public class AnnotationValidationDemo {
    static List<String> validate(Object bean) throws IllegalAccessException {
        List<String> errors = new ArrayList<>();
        Field[] fields = bean.getClass().getDeclaredFields();

        // getDeclaredFields() order is not guaranteed.
        Arrays.sort(fields, Comparator.comparing(Field::getName));

        for (Field field : fields) {
            if (field.isAnnotationPresent(RequiredText.class)) {
                Object value = field.get(bean);
                if (!(value instanceof String text) || text.isBlank()) {
                    errors.add(field.getName() + ": required");
                }
            }

            Minimum minimum = field.getAnnotation(Minimum.class);
            if (minimum != null) {
                int value = field.getInt(bean);
                if (value < minimum.value()) {
                    errors.add(field.getName()
                            + ": minimum " + minimum.value());
                }
            }
        }
        return errors;
    }

    static void register(Signup signup) {
        // Only simulates a business action by printing a message.
        System.out.println("registered username="
                + signup.username.trim() + ", age=" + signup.age);
    }

    public static void main(String[] args) throws Exception {
        Signup invalid = new Signup("  ", 16);

        System.out.println("annotation present: "
                + Signup.class.getDeclaredField("username")
                        .isAnnotationPresent(RequiredText.class));

        System.out.println("without validation:");
        register(invalid);

        List<String> errors = validate(invalid);
        System.out.println("errors: " + errors);
        if (errors.isEmpty()) {
            register(invalid);
        } else {
            System.out.println("rejected by explicit validator");
        }

        Signup valid = new Signup("Lan", 23);
        if (validate(valid).isEmpty()) {
            register(valid);
        }
    }
}
~~~

From the directory containing the file, compile and run:

~~~bash
javac --release 17 AnnotationValidationDemo.java
java AnnotationValidationDemo
~~~

Output:

~~~text
annotation present: true
without validation:
registered username=, age=16
errors: [age: minimum 18, username: required]
rejected by explicit validator
registered username=Lan, age=23
~~~

### Exact analysis of what just happened

1. `@RequiredText` and `@Minimum(18)` are merely annotations declared on the two fields. The object `Signup("  ", 16)` is still instantiated normally: the constructor does not automatically invoke a validator.
2. `isAnnotationPresent(RequiredText.class)` returns `true` because the annotation on the field has `RUNTIME` retention. **However, this metadata lookup does not validate the value of `username`.**
3. `register(invalid)` is called directly **before** validation. It still executes, even though `username` is all whitespace and `age` is less than 18. The `register` method in the example only prints a message; in real business logic, this could be a point that creates corrupt data.
4. Only when code explicitly calls `validate(invalid)` does the validator iterate fields, look up annotations, read values via Reflection, and perform `if`/comparisons.
5. `Minimum.value()` returns the configuration value **18**; the code `value < minimum.value()` is the actual **check condition**. If the condition holds, the validator explicitly adds an error message.
6. `RequiredText` has no members, yet the validator establishes the convention that the marked field must be a non-null `String` containing more than whitespace. The rule lives in **the validator's code**, not generated automatically from the annotation's name.
7. `getDeclaredFields()` promises no return order. The example sorts fields by name before validating so the error list has a deterministic order: `age` then `username`.
8. Only when passing a valid object `Signup("Lan", 23)` and getting an empty list from the validator does the program call `register(valid)`. The control branch `if (errors.isEmpty())` decides whether to allow the business action.

Equivalent logic was verified with Java 17 APIs on the JDK, producing the exact output above. The fields in the example are public to focus on annotation behavior; for private fields, a validator must also comply with **Reflection access checks** and module boundaries.

## 4. Why doesn't metadata automatically protect object invariants?

Annotations are attached to **declaration elements**; they do not automatically turn field assignments into conditional setters, replace constructors, or install interceptors on every Java call.

For example, objects can be created and mutated via multiple paths:

~~~java
Signup user = new Signup("Lan", 23);
user.age = -1;                   // The field still accepts -1.
user.username = "  ";           // The annotation does not block assignment.
~~~

This is an illustrative snippet using the `Signup` class from the program above, not a standalone file. Because `Signup` declares public fields and its constructor/setters perform no checks, any caller with Java access can assign invalid values, even though the annotations exist.

A validation engine takes effect **only at the points where it is invoked**. If you validate an object before saving it, yet later the object is mutated or another code path skips the check, bad data can still slip through. Validation at **trust boundaries and data-write points** matters more than simply placing annotations.

In production design, it is generally best to:

- Enforce invariants directly in constructors/factories, setters, or domain methods when they are conditions that must always hold.
- Invoke validation intentionally at API boundaries and before sensitive operations (DB writes, money transfers, privilege grants, resource creation, etc.).
- Combine with database constraints where appropriate, such as `NOT NULL`, `CHECK`, or unique constraints. Annotations in Java code **do not replace** database-level controls.
- Never assume an object valid at check time will remain valid if subsequent mutation is permitted.

The difference in roles: **annotations express policy; engines/logic enforce policy**.

## 5. Which APIs does Java Reflection use to read annotations?

Some representative APIs of `java.lang.reflect.AnnotatedElement` and `Field`:

| API | Purpose | Automatically runs validation? |
| --- | --- | --- |
| `field.isAnnotationPresent(RequiredText.class)` | Asks whether the annotation is present under Reflection rules | No |
| `field.getAnnotation(Minimum.class)` | Gets the annotation instance or `null` | No |
| `field.getAnnotations()` | Gets runtime annotations present on the element under API rules | No |
| `field.getDeclaredAnnotations()` | Gets annotations declared directly on the element | No |
| `clazz.getDeclaredFields()` | Lists fields declared directly in the class | No |
| `minimum.value()` | Reads the configuration value of `@Minimum(...)` | No |
| `field.get(bean)` / `field.getInt(bean)` | Reads the runtime value of a field | Does not compare against annotation automatically |

Annotations have **elements** such as `int value();` — these are configuration attributes, not bodies of business-processing methods. In `@Minimum(18)`, calling `minimum.value()` simply returns `18`. If code does not execute `if (age < 18)` or equivalent, no rejection behavior occurs.

Note on inheritance: `@Inherited` relates only to certain lookup rules for annotations on **classes**; it does not mean annotations placed on superclass fields/methods are automatically copied to subclass fields/methods. An annotation scanner must decide whether to traverse superclasses, interfaces, overriding methods, or nested objects; the JVM does not build application-specific traversal automatically.

## 6. What roles do the compiler, annotation processors, and runtime frameworks play?

### 6.1 Compiler recognizes certain standard annotations

Example:

~~~java
class Parent {
    void run() {}
}

class Child extends Parent {
    @Override
    void run() {}
}
~~~

With `@Override`, the compiler verifies that the method genuinely overrides/implements an eligible method. If wrong, the code fails to compile. That is behavior of **the compiler understanding a standard annotation**; `@Override` does not supply a method body that runs automatically at runtime. `@Deprecated` is likewise used by tools to warn about discouraged APIs.

### 6.2 Compile-time annotation processors

A registered and enabled annotation processor can read annotations and check code, emit diagnostics, or generate sources/resources. For instance, a framework may provide a processor for `@GenerateBuilder`, yet **merely defining** `@GenerateBuilder` will not generate a builder unless a processor/build pipeline processes it.

Processors typically operate on the compiler model (`javax.annotation.processing`, `javax.lang.model`), not by invoking running business methods. `SOURCE` or `CLASS` retention may suffice for some compile-time tools; not every annotation needs `RUNTIME`.

### 6.3 Runtime frameworks/containers

A framework can read metadata at startup or on each invocation and wire up:

- Validators for constraint annotations.
- Interceptors/proxies for transactions, logging, metrics, or security.
- JSON/ORM mappers to bind fields/properties to data.
- Test runners that locate methods marked with test annotations and explicitly invoke them.

For example, `@Transactional` in a specific framework is meaningful only when the framework creates and manages the corresponding transaction mechanism. If you instantiate with `new` outside the container, call a method along a path that bypasses the proxy/interceptor, or omit/misconfigure the required framework, the expected effect may not occur. Exact behavior depends on the framework and configuration, not a universal self-execution rule of Java annotations.

Do not assume an annotation with an imperative-sounding name (such as `@Validate`, `@Cacheable`, `@Secure`, `@Audit`) will automatically carry out that command.

## 7. Relation to Bean Validation / Jakarta Validation

In the Java ecosystem, annotations such as `@NotNull`, `@NotBlank`, `@Size`, and `@Min` are commonly associated with **Jakarta Bean Validation**. Yet for constraints to take effect, there must be a **validation provider/engine** and a point that actually invokes or integrates the engine.

Conceptual flow:

~~~text
Object with constraint annotations
           |
           v
Validation provider reads metadata
           |
           v
Engine checks current values
           |
       +---+---+
       |       |
     valid   error
       |       |
       v       v
  continue   return violations / report error
~~~

If using Jakarta Validation in an application, you can call a `Validator` supplied by a provider; the example below is **illustrative code requiring the Jakarta Validation API and a corresponding provider**, not a standalone Java SE program:

~~~java
// jakarta.validation.Validator validator = ...; // supplied by provider
// Set<ConstraintViolation<UserInput>> errors = validator.validate(input);
// if (!errors.isEmpty()) {
//     // Stop / report error intentionally.
// }
~~~

In plain Java SE, there is no rule that custom-named annotations `@RequiredText` or `@Minimum` equate to standard Jakarta constraints. The `AnnotationValidationDemo` example in section 3 uses a **custom validator**. Meanwhile frameworks such as Spring may integrate validation at specific points (e.g., request handling, method validation when enabled and properly configured). You must not infer from attaching annotations that every direct method call or assignment across the entire application is automatically validated.

In particular, distinguish:

- **Constraint annotation definition**: states the condition to satisfy.
- **Validator implementation**: defines the evaluation algorithm.
- **Validation invocation**: decides *when*, *which objects*, *which groups* are checked, and *what to do on failure*.

All three parts must work together to form a real validation mechanism.

## 8. From validation to business behavior: annotations do not replace the orchestrator

Validation and business logic are not identical. An annotation can describe an input condition, yet **even with valid data**, the system still has to orchestrate business decisions itself:

~~~java
List<String> errors = validate(signup);
if (!errors.isEmpty()) {
    throw new IllegalArgumentException(errors.toString());
}
register(signup);
~~~

This is an illustrative snippet reusing `validate`, `register`, and `Signup` from the complete program. If the `if` branch is omitted or a caller invokes `register` directly, business logic can still run on invalid data.

Several questions must be answered by application/engine design; annotations do not decide them automatically:

1. Validate upon receiving an HTTP request, before DB write, before emitting an event, or at every step?
2. How to report errors: exception, HTTP 400/422, violation list, or UI integration?
3. Does validation failure roll back a transaction, cancel an event, or keep an audit log?
4. Do we also need cross-field checks (`startDate <= endDate`), per-user permissions, external data, and current state?
5. If data is created via a job, import, message queue, or Reflection rather than HTTP, must the validator be called again?

A framework may offer default answers or extension points, but **the answers come from the framework and configuration**. They are not inherent properties of every annotation.

## 9. Common mistakes

| Misconception / bug | Reality | Fix |
| --- | --- | --- |
| “Once `@RequiredText` is added, the constructor automatically blocks null/blank.” | Annotation metadata does not block assignments/instantiation. | Call a validator explicitly or check invariants in constructor/factory. |
| “Having `@Retention(RUNTIME)` makes validation run automatically.” | `RUNTIME` only lets Reflection read the annotation. | Write/configure a processing component and an appropriate call site. |
| “Reading `getAnnotation(...)` enforces the rule.” | `getAnnotation` only returns metadata. | Read the elements, then run checks and handle results. |
| “`@Min(18)` automatically blocks every assignment to the field.” | The field can still change if code has write access. | Validate at write boundaries or enforce invariants in the domain model. |
| “Installing the annotations library is enough; no provider needed.” | Constraints need an engine and an activation path. | Check dependencies, provider, framework integration, and invocation paths. |
| “`@Transactional` always works in every direct call.” | Many frameworks use proxies/interceptors and apply only on managed call paths. | Understand interception mechanisms, configuration, and object lifecycles. |
| “Annotations declared on a superclass are definitely scanned on subclasses.” | Annotation inheritance rules depend on element/API kind and scanner. | Review `@Inherited` scope accurately; traverse class hierarchy if needed. |
| “Once validation has run once, the object can never be invalid.” | Mutable objects can change after checking. | Design immutable/invariant types and validate at trust boundaries. |
| “Validated data is authorized for business processing.” | Data-format validity does not imply sufficient authority or business eligibility. | Separate input validation, authorization, business rules, and transactions. |

### Note on Reflection access

If a validator scans private fields, `Field.get(bean)` is still subject to Java access checks. `getDeclaredFields()` can find the metadata, yet does not guarantee the caller may read the field. `trySetAccessible()` can fail when named module boundaries are not open for deep reflection. **Do not** work around access errors by silently skipping validation; design public accessors/APIs or adjust module configuration appropriately, if authorized.

### Note on trust boundaries and security

Do not use annotations and application-invoked validators as the **sole protection layer** for permissions, money, inventory counts, or data integrity. The system must verify permissions, transaction state, and constraints at points that cannot be bypassed by other entry paths. Descriptive annotations can be part of that architecture, but there is no guarantee the system enforces them automatically.

## 10. Checklist when designing runtime annotations

1. Determine whether the annotation is for compile-time, runtime, or tooling; if runtime Reflection must read it, choose `@Retention(RUNTIME)`.
2. Specify placement with `@Target`: class, field, method, parameter, constructor, etc.
3. Clearly define element meanings, defaults, handling of null/mismatched types, and error messages.
4. Build or choose a metadata-reading engine; if using custom annotations, real handling code must exist.
5. Specify **call sites**: constructor/factory, HTTP boundary, service method, transaction boundary, pre-DB save, test runner, etc.
6. Ensure every required entry path goes through validation; do not let direct calls or critical mutations bypass it.
7. Define violation outcomes (throw, return violations, reject/rollback, log) and distinguish them from other business errors.
8. Test both when the annotation **is present without the engine running** and when the engine runs and properly rejects invalid data.
9. Verify Reflection/module access and final class files in the deployment environment.
10. Do not expect annotation names, retention, or Reflection metadata to produce side effects on their own.

## 11. Self-check

**Question 1:** Does `@Minimum(18)` mean the JVM automatically throws an exception when field `age` is set to 16? **No.** Only an invoked engine or real logic evaluates and rejects it.

**Question 2:** `field.isAnnotationPresent(Minimum.class)` returns `true`. Does that prove validation ran? **No.** It only confirms matching runtime metadata exists.

**Question 3:** How does `@Retention(RUNTIME)` differ from `@Target(FIELD)`? **`Retention`** controls how long the annotation is retained; **`Target`** controls valid locations for the annotation.

**Question 4:** Why was the age-16 object still “registered” on the first call in the example program? **Because the program called the business method directly before calling the validator.** No automatic validation mechanism is generated by the annotation alone.

**Question 5:** If using Jakarta Validation constraints while forgetting to run/integrate a provider, what happens? **The annotations may still exist, yet there is no guarantee constraints are automatically evaluated** on every object or assignment.

**Question 6:** Can annotations influence a program? **Yes, when a compiler, processor, framework, or the application itself is designed to read and process them.** Do not confuse “does not execute by itself” with “has no effect when integrated with tooling”.

**Key takeaway:** Annotations are **metadata about rules or intent**. `@Retention(RUNTIME)` makes metadata observable to Reflection; `getAnnotation` reads metadata; **the engine/caller** is what evaluates validation, blocks invalid data, and performs business behavior.