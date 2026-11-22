# @Target in Java: FIELD, METHOD, and CONSTRUCTOR

In Java, an annotation can only appear at the **declaration locations** permitted by that annotation type. Three common targets for marking members inside a class are `ElementType.FIELD`, `ElementType.METHOD`, and `ElementType.CONSTRUCTOR`. They correspond to **fields**, **methods**, and **constructors**.

For example, the same class can declare separate metadata for where state is stored, where behavior is provided, and where objects are initialized:

```java
class Account {
    @ColumnName("account_id")  // Example annotation for FIELD.
    private final String id;

    @CreatedBy("constructor") // Example annotation for CONSTRUCTOR.
    Account(String id) {
        this.id = id;
    }

    @AccessLabel("read")      // Example annotation for METHOD.
    String getId() {
        return id;
    }
}
```

The snippet above **only illustrates annotation placement**; to compile, the corresponding `ColumnName`, `CreatedBy`, and `AccessLabel` annotations must be declared. A complete, standalone compilable Java 17+ program will appear in section 7.

This lesson focuses on the **application target (`@Target`)**. The target answers the question *"Where can the annotation be written?"*; it does not determine whether metadata is retained until runtime or what a framework will do with that metadata.

## 1. Distinguishing the Three Targets Through Java Declarations

| `ElementType` | Permits annotation on | Example valid locations | Easily confused locations |
| --- | --- | --- | --- |
| `FIELD` | Field declarations of a class or interface, including enum constants | `@Tag private int count;` | Local variables in a method, parameters, getters |
| `METHOD` | Method declarations, including interface methods and annotation type elements | `@Tag public int size() { ... }` | Constructors, method calls `size()`, parameters |
| `CONSTRUCTOR` | Constructor declarations | `@Tag public Person() {}` | Methods with names similar to a constructor, `new Person()` statements |

These are **declaration targets**, not every place in source code where a field, method, or constructor is used.

- **FIELD:** a declaration element for storing state at the class/interface level. Java treats an enum constant as a form of field declaration in the context of `@Target`.
- **METHOD:** a declaration element for a method with a name, return type (or `void`), and parameter list. Getters and setters are both methods; the field itself that they operate on remains a separate declaration.
- **CONSTRUCTOR:** a declaration element specifying how to create an object, carrying the same name as the class and **declaring no return type**. A constructor is a distinct member, not a `void` method.

In Java, these three names are constants of the standard `java.lang.annotation.ElementType` enum, referenced in the `java.lang.annotation.Target` meta-annotation.

## 2. Declaring Scope with @Target

Restricting to a single location:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface FieldOnly {
    String value();
}
```

When an annotation type must be used on **multiple locations**, pass an array of enum values:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.CONSTRUCTOR
})
@interface ReviewMark {
    String value();
}
```

The two snippets above are **illustrative annotation type declarations** that can compile in an appropriate Java file. `@Target` is placed **on the annotation definition**, while `@ReviewMark("...")` or `@FieldOnly("...")` is placed on the element they mark.

With `ReviewMark`, all three locations are permitted; this **does not require** attaching the annotation to every field, method, or constructor. Each place where you want to attach it is chosen independently.

### What if @Target Is Omitted?

If an annotation type **has no `@Target`**, according to the JLS, it applies by default in **declaration** contexts. That does not automatically permit usage in every type context such as `List<@Tag String>`; usage in a type-use context requires appropriate permission via `ElementType.TYPE_USE`.

To keep the annotation contract clear, you should declare `@Target` precisely for the locations that the consumer actually supports. An annotation designed solely for processing fields that allows arbitrary attachment to methods can easily cause confusion.

### @Target Differs from @Retention

The two meta-annotations address two independent questions:

- `@Target`: **Which elements can the annotation be used on?**
- `@Retention`: **Until which stage is the annotation retained?** `SOURCE`, `CLASS`, or `RUNTIME`.

Example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface TrackedMethod {
    String value();
}
```

`TrackedMethod` applies only to **method declarations**, while also allowing reflection code to retrieve the annotation on the method at runtime. If `@Retention` is not declared, the default is `CLASS`, so you should not expect `getAnnotation()` to find that annotation at runtime.

Both `@Target` and `@Retention` only declare metadata. Java does not automatically perform logging, permission checks, or database persistence just because a custom annotation is placed at a valid location.

## 3. FIELD: Fields and Enum Constants

Valid example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface FieldLabel {
    String value();
}

class Customer {
    @FieldLabel("database-key")
    private String customerId;

    @FieldLabel("display")
    public static final String CATEGORY = "CUSTOMER";
}
```

Here, both `customerId` and `CATEGORY` are **fields**, even though one is an instance/private field and the other is static/final. `FIELD` does not mean "primitive variable" or "immutable variable"; it specifies the declaration location.

For enums, an enum constant is also a location belonging to `FIELD`:

```java
// Assume FieldLabel has been declared as in the example above.
enum OrderStatus {
    @FieldLabel("waiting")
    PENDING,

    @FieldLabel("done")
    COMPLETED
}
```

This is an **additional illustrative snippet** using the previously declared `FieldLabel`. An annotation with `@Target(FIELD)` is valid on enum constants.

### FIELD Does Not Apply to Local Variables

**Intentionally failing compilation** example:

```java
// FieldLabel only has @Target(FIELD).
class InvalidLocal {
    void execute() {
        @FieldLabel("temporary")
        int attempts = 0;  // WRONG: this is LOCAL_VARIABLE, not FIELD.
    }
}
```

Having the same `int` data type does not mean having the same declaration context. `int attempts` inside a method body is a local variable, belonging to `ElementType.LOCAL_VARIABLE`, whereas `int attempts` directly inside a class is a field.

**FIELD also does not automatically follow the getter.** Attaching `@FieldLabel` to the `customerId` field does not cause the `getCustomerId()` method to automatically carry that annotation. Some libraries have their own "field access" or "property access" rules; this is a decision of the framework reading the metadata, not a default effect of `@Target(FIELD)`.

## 4. METHOD: Behavior Declarations

Valid example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface ActionLabel {
    String value();
}

class UserService {
    @ActionLabel("query")
    public String findName() {
        return "An";
    }

    @ActionLabel("command")
    public void rename(String newName) {
        // Processing logic is omitted in the target example.
    }
}
```

`findName()` and `rename(...)` are methods, so `@ActionLabel` can be attached to them. This does not depend on whether the method returns a value, accepts parameters, or has the `public` modifier.

Other method locations can also use the corresponding annotation:

- Method declarations in an interface, including abstract, default, or static methods.
- Instance/static method declarations in a class.
- Getter/setter methods.
- **Annotation elements** such as `String value();` inside an `@interface` also belong to the method declaration context according to the JLS.

### METHOD Is Not a Method Call

The following example is **invalid**, because on the line after the comment, `@ActionLabel` is placed before a call statement instead of a method declaration:

```java
// WRONG illustration; not a compilable program.
void perform(UserService service) {
    @ActionLabel("call")
    service.findName();
}
```

A `METHOD` annotation sits on the **declaration** of `findName()`, not at each call site. To collect information when a method is called, an explicit runtime mechanism (such as an interceptor/proxy or instrumentation) is needed to read the metadata and actively perform the corresponding action.

### @Override Is a Familiar Example

`@Override` is a standard annotation with `@Target(METHOD)`. The compiler uses it to check that a method actually overrides or implements a matching method from a supertype:

```java
class Parent {
    void execute() {}
}

class Child extends Parent {
    @Override
    void execute() {}
}
```

The snippet above compiles validly. If a method name is misspelled, `@Override` helps the compiler detect the error. `@Override` also cannot be placed on a constructor.

## 5. CONSTRUCTOR: Object Initialization Declarations

A constructor has the same name as the class and has no return type. It is declared inside the class, which differs from the syntax for **calling a constructor** using `new`.

Valid example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.CONSTRUCTOR)
@interface InitLabel {
    String value();
}

class Report {
    @InitLabel("empty")
    public Report() {
    }

    @InitLabel("named")
    public Report(String title) {
    }
}
```

Two overloaded constructors have different signatures, and an annotation can be attached individually to each constructor. Java does not take an annotation on one constructor and apply it by default to all other constructors of the same class.

**CONSTRUCTOR is not a `new` statement.** This snippet is an **intentionally wrong example**:

```java
// Wrong: a declaration-target annotation does not attach to a new expression.
Report report = @InitLabel("at-call") new Report();
```

Here `@InitLabel` is only permitted on a **constructor declaration**. Annotation forms permitted in certain **type-use contexts** are a different mechanism; this example cannot use a CONSTRUCTOR annotation to attach metadata to each instantiation.

### What About a Method With the Same Name as the Class That Has a Return Type?

```java
class Printer {
    // This is a CONSTRUCTOR.
    Printer() {
    }

    // This is a normal METHOD because it declares the void return type.
    void Printer(int copies) {
    }
}
```

Although the name `Printer` appears in both, `Printer()` is a constructor and `void Printer(int copies)` is a method. To attach an annotation to each of the two declarations respectively, the appropriate `CONSTRUCTOR` and `METHOD` targets are required.

### Default Constructors and Superclass Constructors

If no constructor is written, the compiler may provide a default constructor according to Java's rules. There is no place in source code to put a custom annotation on that **implicitly declared constructor**. When an annotation for a constructor is needed, explicitly declare the appropriate constructor yourself.

Constructors **are not inherited** from the superclass. An annotation on a superclass constructor does not automatically appear on a subclass constructor, even when the subclass calls `super(...)`.

## 6. Valid Locations and Invalid Cases

Suppose there is an annotation:

```java
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.CONSTRUCTOR
})
@interface Marker {}
```

This snippet **illustrates a declaration** and needs imports for `Target` and `ElementType` or fully qualified names to compile. `@Marker` can be placed on fields, methods, and constructors.

However, **it is not permitted** to be attached to:

| Location | Corresponding target | Reason `@Marker` is invalid |
| --- | --- | --- |
| Class declaration `class Device` | `TYPE` | `TYPE` is not in the target set |
| Parameter `void save(String id)` | `PARAMETER` | `PARAMETER` is not permitted |
| Local variable `int retries` in a method | `LOCAL_VARIABLE` | Not a field |
| Type usage in generic `List<@Marker String>` | `TYPE_USE` | Does not support type-use |
| Package/module declaration | `PACKAGE` / `MODULE` | Outside the three targets |
| Call `run()` or `new Device()` | Not a METHOD/CONSTRUCTOR declaration | The three targets are only for declaration locations |

Do not infer `FIELD` just because a parameter or variable "holds data". In Java, the **declaration** kind determines the target.

### Direct Compiler Error Example

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface MethodOnly {}

class InvalidPlacement {
    @MethodOnly
    InvalidPlacement() { // ERROR: @MethodOnly does not apply to a constructor.
    }
}
```

The snippet above **intentionally fails to compile**; it illustrates that the compiler checks target compatibility before the program runs. To fix it, change the annotation's target to `CONSTRUCTOR` (if the annotation is truly meant for constructors), or move the annotation to a valid method.

## 7. Standalone Java 17+ Example: All Three Targets and Reflection

Create **a single file `TargetKindsDemo.java`** with the entire content below. This is a complete program: the annotation is defined once and used on a field, a method, and a constructor of the same class.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.CONSTRUCTOR
})
@interface Audit {
    String value();
}

class Invoice {
    @Audit("field:code")
    private final String code;

    @Audit("constructor:create")
    public Invoice(String code) {
        this.code = code;
    }

    @Audit("method:read")
    public String getCode() {
        return code;
    }
}

public class TargetKindsDemo {
    public static void main(String[] args) throws NoSuchFieldException,
            NoSuchMethodException {
        Class<Invoice> type = Invoice.class;

        Audit fieldTag = type.getDeclaredField("code")
                .getAnnotation(Audit.class);
        Audit methodTag = type.getDeclaredMethod("getCode")
                .getAnnotation(Audit.class);
        Audit constructorTag = type.getDeclaredConstructor(String.class)
                .getAnnotation(Audit.class);

        System.out.println(fieldTag.value());
        System.out.println(methodTag.value());
        System.out.println(constructorTag.value());

        Invoice invoice = new Invoice("INV-42");
        System.out.println(invoice.getCode());
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 TargetKindsDemo.java
java TargetKindsDemo
```

**Exact** stdout from the `java TargetKindsDemo` command:

```text
field:code
method:read
constructor:create
INV-42
```

Reason:

1. `getDeclaredField("code")` returns the `Field` representing the `code` declaration, where `@Audit("field:code")` is present.
2. `getDeclaredMethod("getCode")` returns the `Method` representing the getter method, where `@Audit("method:read")` is present.
3. `getDeclaredConstructor(String.class)` returns the `Constructor<Invoice>` corresponding to the constructor taking a `String`. Its metadata is `constructor:create`.
4. Finally, `new Invoice("INV-42")` calls the constructor normally; `getCode()` returns the field value. The annotation does not change the field read/write logic inside the method body.

The example uses `@Retention(RUNTIME)`, so the three `getAnnotation(Audit.class)` calls return a non-`null` annotation. If retention is changed to `SOURCE` or `CLASS`, the annotation does not appear through ordinary reflection; calling `value()` on a `null` result will throw a `NullPointerException`. To experiment with retention safely, check `tag == null` before reading `value()`.

### Choosing the Right Reflection API

| Target to inspect | API to retrieve the member | Reflection type |
| --- | --- | --- |
| Field named `code` | `Invoice.class.getDeclaredField("code")` | `java.lang.reflect.Field` |
| Method `getCode()` | `Invoice.class.getDeclaredMethod("getCode")` | `java.lang.reflect.Method` |
| Constructor taking `String` | `Invoice.class.getDeclaredConstructor(String.class)` | `java.lang.reflect.Constructor` |

For overloaded methods, `getDeclaredMethod` also requires the exact classes of the **parameter types**; the same applies to overloaded constructors. `getDeclared*` allows finding declarations including private ones, but **merely reading metadata does not automatically grant permission to invoke a private member** when access or module restrictions apply.

Distinguish between `getDeclaredMethod` (declared directly in the inspected class) and `getMethod` (public methods that may be inherited). Finding an inherited method is different from an annotation on the original method automatically copying to an overriding method.

## 8. Why Does an Annotation on a Field Not Automatically Appear on the Getter?

Consider a class:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.METHOD})
@interface Rule {}

class User {
    @Rule
    private String username;

    public String getUsername() {
        return username;
    }
}
```

This is an **illustrative snippet**, requiring the appropriate imports for `Retention`, `RetentionPolicy`, `Target`, and `ElementType`.

Through reflection, the two members are two separate declarations:

```java
// Illustrates expressions if class User and annotation Rule exist:
User.class.getDeclaredField("username")
        .isAnnotationPresent(Rule.class);      // true
User.class.getDeclaredMethod("getUsername")
        .isAnnotationPresent(Rule.class);      // false
```

A data tool may **define a convention** prioritizing field annotations or getter annotations to look up configuration. Another tool may inspect both. Java does not impose a single business meaning on valid locations.

If you want to mark both the field and the getter, you can attach the annotation to each declaration (when the target permits). You also should not expect `@Inherited` to make an overriding method "automatically inherit" an annotation: `@Inherited` only governs annotation lookup on **classes** along superclasses within the scope supported by the specification.

## 9. Special Notes: Enum Constants, Record Components, and Type-Use

### Enum Constants Belong to FIELD

```java
@Target(ElementType.FIELD)
@interface Flag {}

enum Mode {
    @Flag FAST,
    @Flag SAFE
}
```

These are illustrative declarations (requiring imports for `Target` and `ElementType`). `FAST` and `SAFE` are enum constants, which count as field declarations for target rules.

### Record Components Have Their Own Rules

Since Java 16, records have **record components** in their header. Java has `ElementType.RECORD_COMPONENT`, but annotations applicable to fields/methods/parameters can also be used on a record component declaration and **are propagated to the corresponding member** according to the rules for records.

Illustrative example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Stored {}

record Product(@Stored String id) {}
```

This is a valid Java 17 declaration. `@Stored` is eligible to be applied to the record component and is propagated to the corresponding **implicitly declared field**. Therefore, `Product.class.getDeclaredField("id").isAnnotationPresent(Stored.class)` is `true`. However, this annotation does not automatically become an annotation on the accessor under `METHOD`, because the `Stored` type only declares `FIELD`.

Read the record propagation rules when working with validation, serialization, or persistence; you should not assume that every annotation attached to a component appears identically on the field, accessor, constructor parameter, and `RecordComponent` itself.

### TYPE_USE Is a Separate Branch

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_USE)
@interface NonBlankType {}

class Names {
    List<@NonBlankType String> values;
}
```

Here `@NonBlankType` is attached to **the type usage of `String` inside a generic argument**, which differs from attaching to a `FIELD` declaration. `FIELD`, `METHOD`, and `CONSTRUCTOR` cannot replace `TYPE_USE`.

A syntactic position can be both a declaration site and adjacent to a data type. If an annotation permits both a declaration target and `TYPE_USE`, the JLS has specific rules determining that the annotation can apply to both. For this lesson, the main examples use only the three declaration targets to keep the meaning clear.

## 10. Common Mistakes When Using FIELD, METHOD, and CONSTRUCTOR

**Mistake 1 — Attaching FIELD to a local variable.** A field is a member variable of a class/interface, not every named variable. `LOCAL_VARIABLE` is needed if the annotation truly must apply to local variable declarations.

**Mistake 2 — Treating a getter as a field.** Even though a getter reads a field, it is still a method and requires `METHOD`. You should read the framework documentation to decide whether to configure by field or by property.

**Mistake 3 — Using METHOD for a constructor.** A constructor has no return type and is not a method; it requires `CONSTRUCTOR`.

**Mistake 4 — Attaching an annotation to a call site.** `@Target(METHOD)` is for method declarations, not every `foo()` call. `@Target(CONSTRUCTOR)` is for constructor declarations, not `new` expressions.

**Mistake 5 — Omitting retention while using reflection.** `@Target` may be correct, yet reflection will still not see the annotation if retention is not `RUNTIME`.

**Mistake 6 — Assuming attaching an annotation automatically adds behavior.** Custom annotations like `@Audit` only carry data. To write audit logs, there must be a consumer that actually reads the annotation and executes the logging mechanism.

**Mistake 7 — Assuming FIELD/METHOD apply to a record component the same way as in regular classes.** Records have special annotation application/propagation rules. You must check the specific target, retention, and target member.

**Mistake 8 — Confusing member inheritance with annotation copying.** Overriding a method or declaring a constructor in a subclass does not cause annotations on the original method/constructor to automatically appear on the new declaration.

## 11. Self-Check Questions

**Question 1.** Is attaching `@Target(FIELD)` to `private String name;` valid? What about `String name` inside a method?

**Answer:** On the field, it is valid. A variable inside a method is a `LOCAL_VARIABLE`, so an annotation that only permits `FIELD` is invalid there.

**Question 2.** Can `@Target(METHOD)` be placed right before `service.execute()`?

**Answer:** No. `METHOD` applies to **method declarations**, not call statements.

**Question 3.** Are the two overloads `Customer()` and `Customer(String id)` the same constructor such that an annotation is automatically shared?

**Answer:** No. These are two separate constructors with different signatures; annotations are declared separately on each constructor if needed.

**Question 4.** Why does reflection return `null` when an annotation has the right `@Target(METHOD)` but does not have `@Retention(RUNTIME)`?

**Answer:** `@Target` specifies the location. The default retention is `CLASS`, which is not accessible via ordinary reflection at runtime.

**Question 5.** What target does an annotation intended only for a JavaBean getter need?

**Answer:** `ElementType.METHOD`, because a getter is a method. A separate annotation for fields is declared using `ElementType.FIELD`.

**Question 6.** Can `@Target(FIELD)` be used on an enum constant?

**Answer:** Yes. The JLS classifies enum constants under field declaration contexts.

**Question 7.** When an annotation placed on a record component is propagated to the field, does that mean it is also automatically placed on the accessor method?

**Answer:** No. You must check whether the annotation supports `METHOD` and the corresponding propagation rules.

## References

- [Java Language Specification 17, §9.6.4.1 — @Target and Declaration Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1).
- [Java Language Specification 17, §9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4).
- [Java Language Specification 17, §8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3).
- [Java SE 17 API — ElementType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html).
- [Java SE 17 API — Target](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html).

To apply this properly in a project, start from the **declaration kind** you want to mark, choose `FIELD`, `METHOD`, or `CONSTRUCTOR` with `@Target`, and then decide whether the annotation needs to be processed at compile time or runtime. When you need to retrieve the annotation at runtime, check `@Retention` and the appropriate reflection API next.
