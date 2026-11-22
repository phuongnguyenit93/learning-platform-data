# Inheritance Restrictions and Circular Dependency Errors Between Annotation Types in Java

A Java annotation type is declared using `@interface`. It resembles a regular interface in several respects, but **does not have an arbitrary `extends` inheritance mechanism**, and its elements must have valid data types. In particular, Java **forbids an annotation from containing its own annotation type in the return type chain of its elements, directly or indirectly**.

This topic involves three relationships that are easily confused with one another:

1. **Type inheritance relationship** (`extends`): an annotation type cannot declare a parent using `extends` like a regular interface.
2. **Data containment relationship**: an annotation element can return another annotation type, but the dependency chain through return types **must not form a cycle**.
3. **Annotation application / class-level annotation inheritance relationship**: an annotation can be applied to another annotation (meta-annotation); `@Inherited` can allow an annotation to be queried from a subclass. These two mechanisms **are not annotation type inheritance**.

Understanding the difference helps you design clean metadata, avoid compilation errors, and avoid expecting Java to automatically merge annotations according to the semantics of a framework.

## 1. An Annotation Type Is a Special Interface, but Has No extends Clause

An annotation type is declared as follows:

```java
@interface Label {
    String value();
}
```

This is a **valid annotation type declaration**. The `value()` element describes the required data that users of the annotation must provide (unless it has a `default` value). It is not an arbitrary method with an executable body.

Java specifies that the direct superinterface of **every annotation type** is always `java.lang.annotation.Annotation`. This relationship is implicitly established by the language; programmers **cannot choose a superinterface using `extends`**.

Invalid example that intentionally **does not compile**:

```java
@interface ParentTag {
    String value();
}

// INVALID: @interface syntax does not allow extends.
@interface ChildTag extends ParentTag {
    int version();
}
```

When moving from regular interfaces to annotations, do not carry over the following intuition:

```java
interface Parent {
    void doWork();
}

// VALID for a regular interface.
interface Child extends Parent {
    void doMore();
}
```

The two snippets demonstrate the syntactic difference: `interface Child extends Parent` is allowed for a regular interface; `@interface ChildTag extends ParentTag` is invalid.

**Consequences:**

- There is no way to create `@AdminRole` to "inherit all elements" of `@Role` using `extends`.
- You cannot expect a new annotation to automatically inherit `value()`, `level()`, `default`, or meta-annotations attached to another annotation.
- You can organize annotations using **composition** or supplementary metadata, but the consuming program/tool must understand and process that relationship.

A subtle point: because `@interface` is a kind of interface, Java gives it the methods defined by `java.lang.annotation.Annotation`, such as `annotationType()`. However, these inherited methods **do not become annotation elements declared by you**.

## 2. What Types Are Allowed for Annotation Elements?

Inside an `@interface` body, methods declaring elements have restricted return types. Java allows:

| Type Category | Valid Element Examples |
| --- | --- |
| Primitive types | `int level();`, `boolean enabled();` |
| `String` | `String name();` |
| `Class` or a `Class` type with valid generics | `Class<?> target();` |
| An enum type | `Mode mode();` if `Mode` is an enum |
| Another annotation type | `Details details();` |
| One-dimensional array of the valid types above | `String[] tags();`, `Details[] items();` |

Example of a valid structure:

```java
enum Priority {
    LOW, HIGH
}

@interface Details {
    String author();
    int revision() default 1;
}

@interface Definition {
    String name();
    Priority priority() default Priority.LOW;
    Details details();
    Class<?> owner();
    String[] aliases() default {};
}
```

These are **logically standalone type declarations** without a `main` method. `Definition` has a one-way dependency on `Details`, because the `details()` element returns the annotation type `Details`.

The following declarations are **invalid and must not be included in a runnable program**:

```java
@interface Invalid {
    Object object();         // INVALID: Object is not a valid element type.
    java.util.List<String> names(); // INVALID: List<String> is invalid.
    String[][] matrix();     // INVALID: two-dimensional array.
    void run();              // INVALID: void is not a valid element type.
}
```

Java also restricts element signatures: the method takes no parameters, has no type parameters and no `throws` clause, and cannot define a body like a regular instance method. The circular dependency error is an additional rule alongside the return type restrictions.

## 3. Direct Circular Dependency Error: An Annotation Returning Itself

Consider the intentionally invalid declaration:

```java
@interface SelfRef {
    SelfRef value();  // INVALID: the element type is the containing annotation itself.
}
```

Circular dependency model:

```text
SelfRef
   └── value(): SelfRef
             └── back to SelfRef
```

The compiler reports an error because the annotation type `SelfRef` contains an element of type `SelfRef`.

Changing from a single object to an array **does not break the cycle**:

```java
@interface TreeNode {
    TreeNode[] children();  // STILL INVALID: the array component type is TreeNode.
}
```

Some people draw an analogy to Java classes being able to reference themselves, such as:

```java
class Node {
    Node next; // Valid for a regular Java class.
}
```

That reasoning cannot be applied as-is to `@interface`. Classes have flexible object references at runtime; annotation elements must belong to a finite metadata value model and comply with the cycle rules of the Java Language Specification (JLS §9.6.1).

## 4. Indirect Circular Dependency Error: A → B → A

Java also prohibits **cycles spanning multiple annotation types**, even when each declaration only mentions a different type:

```java
@interface Ping {
    Pong value();
}

@interface Pong {
    Ping value();
}
```

This is an **example that intentionally causes a compile-time error**, not a runnable program. The dependency cycle:

```text
Ping.value(): Pong
      ↓
Pong.value(): Ping
      ↓
back to Ping
```

Longer cases are still invalid:

```java
@interface A {
    B b();
}

@interface B {
    C[] c();
}

@interface C {
    A parent();
}
```

Even though `B.c()` returns `C[]`, the dependency edge is still from `B` to `C`. The result is `A → B → C → A`.

### Rule for Self-Checking

Consider only the relationship where **an annotation element has another annotation type**, or an array of another annotation type, as its return type. Represent it as a directed graph:

- Each annotation type is a vertex.
- `@interface X { Y item(); }` creates the edge `X → Y`.
- `@interface X { Y[] items(); }` also creates the edge `X → Y`.
- If following those edges leads back to an already-visited vertex, **there is a prohibited cycle**.
- If there is no cycle, the containment relationship among the annotation types can be valid, provided that other declaration and usage rules are also satisfied.

Example of acyclic composition:

```text
RequestMeta
    ├── OwnerInfo
    └── AuditInfo
             └── AuditFlags

No edge leads back to RequestMeta.
```

Thinking in terms of a graph helps detect long cycles across multiple metadata layers, even when each `@interface` resides in a separate file.

## 5. Do Not Confuse Element Cycles with Meta-Annotation Cycles

**Very important point:** Java **allows** an annotation type to be annotated by another annotation type, and cycles can even occur in the relationship of *applying an annotation to an annotation declaration*. The cycle prohibition in §9.6.1 applies to **element return type cycles**, not every arrow-like relationship between annotations.

Valid example of a meta-annotation relationship, presented as declarations within the same package scope:

```java
@Right
@interface Left {}

@Left
@interface Right {}
```

Here:

- `@Right` is **applied to the declaration** of `Left`.
- `@Left` is **applied to the declaration** of `Right`.
- Neither annotation declares an element returning the other annotation type.

According to JLS §9.7.1, the relationship "annotation type A annotates the declaration of annotation type B" may form a cycle. **You should not apply the element cycle prohibition rule to meta-annotation cycles**.

However, some frameworks may traverse meta-annotations recursively; in that case, meta-annotation cycles must be **handled by the tool** using a set of visited types or an appropriate stopping rule. That is a concern for the tool reading the metadata, not an element cycle error that `javac` is required to reject.

### Meta-Annotations Do Not Mean Element Inheritance or Automatic Metadata "Propagation"

Example:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Secured {
    String role();
}

@Secured(role = "ADMIN")
@Retention(RetentionPolicy.RUNTIME)
@interface AdminOnly {}

@AdminOnly
class Dashboard {}
```

These are **illustrative declarations** with no `main` yet. The `Secured` annotation is applied to the **`AdminOnly` annotation type**. `Dashboard` is directly annotated with `AdminOnly`, **not directly annotated with `Secured`**.

Therefore, with plain Java reflection:

```java
// With the declarations above:
Dashboard.class.getAnnotation(Secured.class); // null
AdminOnly.class.getAnnotation(Secured.class); // returns the Secured annotation
```

The two statements above are **illustrative expressions**, not a standalone program. A framework can proactively traverse meta-annotations deeply to interpret `@AdminOnly` as "role=ADMIN", but Java reflection does not automatically infer that `Secured` is directly present on `Dashboard`.

## 6. @Inherited: Class-Level Annotation Inheritance Is Not Annotation Type Inheritance

The name `@Inherited` easily creates the impression that annotation types can `extends` each other. In reality, it is a **standard meta-annotation** placed on the definition of an annotation type, affecting how Java reflection **looks up annotations on a class through its superclass chain**.

Example:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Access {
    String role();
}

@Access(role = "USER")
class BaseController {}

class AccountController extends BaseController {}
```

`AccountController.class.getAnnotation(Access.class)` can find `@Access` from `BaseController` because `@Inherited` is present and the annotation is retained until runtime.

**Limitations to keep in mind:**

- `@Inherited` works when an annotation **is queried on a class declaration**; it does not add `extends` to the annotation type declaration.
- Lookup proceeds only through **superclasses**, not through interfaces that the class `implements`.
- It does not cause annotations on **methods, fields, or parameters** to be automatically inherited through member overriding/inheritance relationships.
- `Class.getAnnotation(...)` can return an inherited annotation; `Class.getDeclaredAnnotation(...)` only reads annotations declared directly on the class being inspected.
- If the subclass declares that same annotation type itself, the directly declared annotation takes precedence during lookup.

This is different from the **annotation element return type** restriction in JLS §9.6.1. An `@Inherited` definition cannot make the circular declaration `@interface Node { Node next(); }` valid.

## 7. Standalone Java 17+ Example: Valid Composition and Observing @Inherited

Create a single file named **`AnnotationBoundariesDemo.java`** with the following content. All required types are contained within the file, with exactly one `public` class matching the file name. This example demonstrates:

- **One-way composition**: `@Feature` contains an element of type `Detail`.
- **No element cycles**, so it compiles successfully.
- One annotation with `@Inherited` and another annotation without `@Inherited`.
- The difference between `getAnnotation` and `getDeclaredAnnotation`.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Hint {
    String value();
}

// Used only as a nested value of another annotation.
@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface Detail {
    String name();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Feature {
    Detail detail(); // Edge Feature -> Detail, does not point back to Feature.
}

@Role("base")
@Hint("direct")
class Parent {}

class Child extends Parent {}

@Feature(detail = @Detail(name = "audit"))
class Service {}

public class AnnotationBoundariesDemo {
    public static void main(String[] args) {
        Role inherited = Child.class.getAnnotation(Role.class);
        System.out.println(inherited.value());

        Role declared = Child.class.getDeclaredAnnotation(Role.class);
        System.out.println(declared == null);

        Hint notInherited = Child.class.getAnnotation(Hint.class);
        System.out.println(notInherited == null);

        Feature feature = Service.class.getAnnotation(Feature.class);
        System.out.println(feature.detail().name());
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 AnnotationBoundariesDemo.java
java AnnotationBoundariesDemo
```

Exact stdout of `java AnnotationBoundariesDemo`:

```text
base
true
true
audit
```

Explanation:

1. `base`: `Child` extends the `Parent` class, and `Role` has `@Inherited`. The `getAnnotation(Role.class)` lookup checks the superclass.
2. `true` (second line): `Child` does not **directly** declare `@Role`, so `getDeclaredAnnotation(Role.class)` returns `null`.
3. `true` (third line): `Hint` does not have `@Inherited`, so `Child.class.getAnnotation(Hint.class)` returns `null` even though `Parent` has `@Hint`.
4. `audit`: `Feature.detail()` holds an annotation value of type `Detail`, and can be validly accessed at runtime thanks to `@Retention(RUNTIME)`.

Note: `@Target({})` is used for `Detail` to restrict that annotation to the role of a **nested value**, rather than being applied directly to a class/method. This is a design choice; it does not turn `Feature → Detail` into an inheritance relationship.

### Comparison of Valid Code and Invalid Code

| Scenario | Result | Reason |
| --- | --- | --- |
| `@interface A { String value(); }` | Valid | The element type is `String` |
| `@interface A { B value(); }`; `@interface B { String name(); }` | Valid | One-way dependency `A → B` |
| `@interface A { A value(); }` | Compile-time error | Direct element self-reference |
| `@interface A { B value(); }`; `@interface B { A value(); }` | Compile-time error | Indirect element cycle |
| `@interface B extends A {}` | Invalid | Annotation type declarations do not have `extends` |
| `@B @interface A {}`; `@A @interface B {}` | Valid with respect to the element cycle rule | This is a meta-annotation relationship cycle, not an element type |
| `@Inherited` on type `A` | Valid if applied to the appropriate target | Controls annotation lookup on subclasses; does not inherit elements |

## 8. A Related Real-World Case: @Repeatable and Container Annotations

Java supports applying an annotation repeatedly through `@Repeatable`. This mechanism requires a **container annotation** with a `value()` element that returns an array of the repeated annotation.

Example of valid declarations:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@interface Tags {
    Tag[] value();
}
```

Here there is an element relationship **`Tags → Tag`**, while `@Repeatable(Tags.class)` is metadata attached to the declaration of `Tag`. That **does not automatically create an element edge `Tag → Tags`**, because `Tag` does not declare a method returning `Tags`.

Adding an element like the following to `Tag` will form a return type cycle and be rejected:

```java
// INVALID illustration: the following definitions create an element cycle.
@Repeatable(Tags.class)
@interface Tag {
    Tags parent(); // Tag -> Tags
}

@interface Tags {
    Tag[] value(); // Tags -> Tag
}
```

The snippet above intentionally **does not compile**; if you keep the initial container declaration without adding the `parent()` element, the `@Repeatable` structure can be valid. To use repeatable annotations in a real project, other conditions regarding retention, target, and container elements under JLS §9.6.3 must also be satisfied.

This case shows why you cannot conclude that "whenever two annotations mention each other's names, it is a cycle error." **What matters is which relationship creates an edge through an element return type.**

## 9. Redesigning Annotations When Encountering a Cycle Error

Suppose a system wants to describe a workflow using metadata, and the initial design accidentally creates a cycle:

```java
// INVALID: the two types directly/indirectly contain each other.
@interface Workflow {
    Step[] steps();
}

@interface Step {
    Workflow parent();
}
```

You can fix this by **keeping the relationship one-way** if the problem only requires grouping:

```java
@interface Step {
    String name();
}

@interface Workflow {
    Step[] steps();
}

@Workflow(steps = {
    @Step(name = "validate"),
    @Step(name = "persist")
})
class OrderWorkflow {}
```

The second snippet contains **valid** annotation declarations and usage (without `main` yet). Each `Step` only carries simple data; `Workflow` groups the steps together. Avoid putting `Workflow` back into `Step`.

If a "back-link" is truly needed, you can store an identifier, such as `String workflowId()`, and let code handle the mapping outside the annotation. For tree structures, dynamic graphs, or self-referential data, a regular object model may be more suitable than annotation metadata.

**Do not switch to `Class<?>` just to bypass the rule and then assume Java will validate the entire business relationship for you.** `Class<?>` is a valid element type, but verifying whether a class token points to the expected kind and handling logical cycles still belong to the metadata-consuming code.

### Step-by-Step Error Checking

1. Read the exact `javac` error and locate the element declaring an annotation return type.
2. Draw the dependency edges `A → B` from the element methods, including array-typed elements.
3. Determine whether any cycle leads back to the same annotation type.
4. Determine which relationships genuinely need to be stored in both directions. If not needed, remove the return edge or replace it with identifier data.
5. Stick to element types permitted by the JLS; avoid `Object`, `List`, and multidimensional arrays.
6. If the annotations merely **annotate each other** without cyclic elements, check the consumer/framework to determine whether the metadata cycle is handled safely. Do not immediately blame `@interface`.

## 10. Common Misconceptions

**"An annotation type is an interface, so `@interface B extends A` must be valid."** False. Annotation type syntax does not allow `extends`, even though it has the implicit superinterface `Annotation`.

**"`@Inherited` allows a child annotation to inherit elements from a parent annotation."** False. `@Inherited` affects how reflection looks up annotations through superclasses when an annotation is applied to a class.

**"An annotation containing another annotation is an error."** False. `@interface A { B b(); }` is valid when `B` is validly declared and there is no dependency path leading back to `A`.

**"Using `A[]` instead of `A` eliminates self-reference."** False. The array still contains the annotation type `A` and creates the corresponding cycle.

**"Two annotations applied to each other are guaranteed to be a compilation error."** False. Meta-annotations can form cycles without violating the element cycle prohibition rule. However, a consumer that traverses metadata recursively needs its own stopping mechanism.

**"If an annotation is meta-annotated with another annotation, every class using it automatically carries the other annotation."** False for plain Java reflection. Interpreting that composite relationship requires an appropriate consumer.

**"`@Repeatable` automatically causes a cycle error because the container references the repeated annotation."** False. Only the container element returns the repeated annotation; the `@Repeatable` attribute itself is not an element returning the container.

## 11. Self-Check Questions

**Question 1.** Why does `@interface B extends A {}` fail, while `interface B extends A {}` can be valid?

**Answer:** `@interface` has its own syntax without `extends` and always has the language-defined superinterface `java.lang.annotation.Annotation`. Regular interfaces are allowed to specify superinterfaces.

**Question 2.** Is the dependency `Header → Footer → Header` through returned elements accepted by Java?

**Answer:** No. That is an indirect cycle in the annotation's element types.

**Question 3.** Is `@interface Tree { Tree[] children(); }` valid because it uses an array?

**Answer:** No. The array element is still `Tree`, creating a self-reference.

**Question 4.** Why are `@A @interface B {}` and `@B @interface A {}` not necessarily an element cycle error?

**Answer:** Because that is a relationship where an annotation is applied to another annotation declaration; no element is required to return the other type itself.

**Question 5.** Does `@Inherited` apply automatically to annotations on interfaces and overridden methods?

**Answer:** No. It applies to looking up annotations on a class through its superclass chain.

**Question 6.** When you need a `@Workflow` annotation containing multiple `@Step` annotations, while also needing workflow information from each step, how should you begin fixing the design?

**Answer:** Keep the `Workflow → Step` direction in the elements and pass an identifier key or handle the reverse relationship in separate logic, avoiding `Step → Workflow` via annotation elements.

## Official Documentation

- [Java Language Specification 17, §9.6 — Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6).
- [JLS 17, §9.6.1 — Annotation Interface Elements and Prohibition of Self-Reference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1).
- [JLS 17, §9.7.1 — Meta-Annotation Relationships That May Form Cycles](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1).
- [Java 17 API: java.lang.annotation.Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html).

When reviewing an annotation design, distinguish between **type inheritance**, **element-based dependency**, and **annotation application relationships**. Java restricts each relationship according to different rules; making this distinction accurately helps you read compiler errors and choose a sound metadata design.
