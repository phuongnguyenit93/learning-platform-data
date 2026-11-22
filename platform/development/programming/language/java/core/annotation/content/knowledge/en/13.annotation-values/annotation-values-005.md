# Observable Immutability and Arrays Returned from Annotations in Java Core

An annotation in Java describes **declared metadata** on a program, not a configuration object that can be modified arbitrarily while the application is running. However, annotation elements are allowed to have array types such as `String[]`, `int[]`, or `Rule[]`; in Java, an array itself is an object **whose elements can be modified**. Therefore, an important question arises: if you call `annotation.roles()`, receive a `String[]`, and modify its elements, does the metadata in the annotation change as well?

For annotation instances returned by the standard JDK Reflection mechanism, the verifiable answer is **no**: modifying the returned array does not change the element values observed when reading the annotation later. The standard implementation mechanism protects internal array values with a **defensive copy** when necessary. Nevertheless, the array that the calling code receives **is still an ordinary, mutable Java array**, and API users should not rely on the reference identity of the returned array.

This lesson explains precisely the concept of *observable immutability*, how annotation arrays work, the empty-array exception, the `equals`/`hashCode` contract, and what to keep in mind when writing annotation-processing libraries.

## 1. Objectives

After studying this lesson, you will be able to:

- Distinguish between annotation metadata having stable values and the fact that **the returned array is locally mutable**.
- Explain why modifying a `String[]`, `int[]`, or nested annotation array obtained from an annotation should not alter subsequent reads.
- Understand **defensive copying** and why you must not rely on `==` to compare returned arrays.
- Know why an empty array is a special case: there are no elements to modify, so array identity is a detail that should not be used as a contract.
- Use `Arrays.toString`, `Arrays.equals`, and `Arrays.hashCode` properly when working with array values.
- Distinguish the equality contract of **two annotations** from reference equality of two arrays.
- Inspect default values using `Method.getDefaultValue()` without confusing them with the effective value of a specific annotation.
- Recognize the difference between an annotation created by Java Reflection and an arbitrary user-written implementation.

## 2. What Does an Array-Typed Annotation Element Look Like?

In Java, an annotation type is declared using `@interface`. An array-typed element is written like a parameterless method:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Access {
    String[] roles() default {"reader", "writer"};
    int[] ports() default {8080, 8443};
}
~~~

This is an illustrative declaration, without `main` yet. When using `@Access` without passing the two elements, their effective values are an array of two strings and an array of two integers, respectively.

Each annotation element has a type restricted by Java: a primitive, `String`, `Class`, enum, annotation type, or a **one-dimensional array** of those types. You cannot declare `List<String> roles()` or `String[][] roles()` as a valid annotation element. An annotation element also does not accept `null`.

At the usage site, they can be overridden:

~~~java
@Access(roles = {"admin"}, ports = {9000})
class AdminEndpoint {}
~~~

If you call `getAnnotation(Access.class).roles()`, you receive an object of type `String[]`. From an API standpoint, the array elements can be modified:

~~~java
Access annotation = AdminEndpoint.class.getAnnotation(Access.class);
String[] local = annotation.roles();
local[0] = "guest";  // Valid for the local variable, but does not modify the annotation.
~~~

**Key distinction:** The fact that the assignment above does not throw an error does not prove that the annotation has been modified. It only proves that `local` references a mutable Java array object.

## 3. What Does “Observable Immutability” Mean?

Suppose the annotation initially has `roles = {"reader", "writer"}`.

~~~java
String[] snapshot = annotation.roles();
snapshot[0] = "modified";

System.out.println(Arrays.toString(snapshot));
System.out.println(Arrays.toString(annotation.roles()));
~~~

In the standard Reflection implementation commonly found in modern JDKs, the corresponding output is:

~~~text
[modified, writer]
[reader, writer]
~~~

The `snapshot` array is the piece of data **held by the calling code**. When you modify `snapshot[0]`, only the snapshot is changed. Another call to `annotation.roles()` still shows stable metadata values.

**Observable immutability** here means that through the normal Reflection API, annotation-consuming code cannot alter the annotation values defined in the class file merely by modifying elements of the returned array. It does **not** mean that the returned array itself is an immutable collection.

Do not confuse these three concepts:

| Concept | What Is True |
| --- | --- |
| Annotation metadata | Declared or default values are read stably provided the annotation type and environment do not change |
| Returned `String[]` / `int[]` | An ordinary Java array whose copy's elements can be reassigned |
| Changes to the snapshot | Do not reflect as a change to the annotation value on subsequent reads |

This refers to using the public Reflection API for its intended purpose. Unsupported low-level intervention mechanisms, bytecode replacement, class reloading, or custom implementations of the annotation interface are outside the scope of this topic and should not be used as evidence that the API permits modifying metadata.

## 4. Defensive Copy: Why Does Modifying the Array Not Change the Annotation Value?

An annotation implementation generated by the JDK is responsible for returning each element's value. To protect the metadata, the implementation typically follows this idea for arrays **with elements**:

~~~java
// CONCEPTUAL ILLUSTRATION CODE, not the actual JDK definition.
String[] storedRoles = {"reader", "writer"};

String[] readRoles() {
    return storedRoles.clone();
}
~~~

`clone()` creates a new array object with the elements copied over. If the calling code modifies this array, `storedRoles` is unaffected.

Example:

~~~java
String[] a = {"reader", "writer"};
String[] b = a.clone();
b[0] = "modified";

System.out.println(Arrays.toString(a)); // [reader, writer]
System.out.println(Arrays.toString(b)); // [modified, writer]
System.out.println(a == b);             // false
~~~

Array `clone()` is a **shallow copy**: it copies the elements; if an element is a reference, the referenced object is not deep-copied. However, an annotation element does not allow an array of `List<Object>` or an array of arbitrary mutable Java objects. Valid element types such as strings, `Class`, enums, annotation instances, or primitives make protecting values governed by the annotation contract simpler.

In OpenJDK releases, the element invocation mechanism on the annotation proxy handles cloning **non-empty** arrays when returning them. This is a **useful implementation detail to understand and verify yourself**, not a reason to build logic that depends on the specific object identity of a `roles()` call.

### Single-Element or Multi-Element Arrays

For an array element containing data, copying helps prevent the bug where “external code modifies an element and the annotation value changes.” The complete program in Section 6 verifies this for `String[]`, `int[]`, and `Note[]`.

### Empty Arrays

With `String[] empty() default {}`, the array length is `0`. There is no `empty()[0]` to assign because doing so would throw `ArrayIndexOutOfBoundsException`. Therefore, an implementation can **reuse an empty array** instead of cloning it without creating any opportunity to modify elements.

Do not rely on:

~~~java
// DO NOT use this as a business condition.
boolean same = annotation.empty() == annotation.empty();
~~~

The value of `same` is not a criterion for determining whether the annotation is immutable. Your API should care about `annotation.empty().length == 0` and array contents, not object identity of the array.

## 5. Nested Annotation Arrays Are Also Protected

An annotation element is not limited to `String[]` or `int[]`; it can also return **an array of other annotations**:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Note {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Settings {
    Note[] notes() default {
        @Note("stable"),
        @Note("audited")
    };
}
~~~

The code above is an illustrative declaration. When calling `settings.notes()`, you receive a `Note[]`. You can write:

~~~java
Note[] snapshots = settings.notes();
snapshots[0] = null;
~~~

However, assigning `null` in the **copy of the array** does not mean the `Note` element declared in the metadata has been removed. Reading `settings.notes()[0].value()` again still returns the defined value.

Do not confuse:

- `@Note("stable")` is an **annotation instance**, which has a `value()` element; it does not have a `setValue(...)` setter.
- `Note[]` is a **reference array** containing those annotation instances, allowing the calling code to replace elements **in the returned array**.
- Copying the array does not mean there is a Java constructor `new Note(...)` or a deep copy of the annotation object.

If a nested annotation itself has an array-typed element, read its elements through its own annotation API. Do not write a library that relies on modifying `settings.notes()[0].values()[0]` to update metadata: these are locally mutable snapshots, not a configuration-mutation channel.

## 6. Standalone Runnable Java 17+ Example and Exact Output

Create **a single file** named `AnnotationArraySafetyDemo.java`, place the supporting classes/annotations in the same file, and omit any `package` declaration for convenience when running:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Note {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Settings {
    String[] roles() default {"reader", "writer"};
    int[] ports() default {8080, 8443};
    Note[] notes() default {@Note("stable")};
    String[] empty() default {};
}

@Settings
class Service {}

@Settings
class ServiceCopy {}

public class AnnotationArraySafetyDemo {
    public static void main(String[] args)
            throws NoSuchMethodException {

        Settings settings = Service.class.getAnnotation(Settings.class);

        String[] rolesSnapshot = settings.roles();
        rolesSnapshot[0] = "modified";

        int[] portsSnapshot = settings.ports();
        portsSnapshot[0] = 0;

        Note[] notesSnapshot = settings.notes();
        notesSnapshot[0] = null;

        System.out.println("roles=" + Arrays.toString(settings.roles()));
        System.out.println("ports=" + Arrays.toString(settings.ports()));
        System.out.println("note=" + settings.notes()[0].value());
        System.out.println("firstSnapshot="
                + Arrays.toString(rolesSnapshot));
        System.out.println("sameArray="
                + (rolesSnapshot == settings.roles()));

        Settings copy =
                ServiceCopy.class.getAnnotation(Settings.class);
        System.out.println("equals=" + settings.equals(copy));
        System.out.println("hashEqual="
                + (settings.hashCode() == copy.hashCode()));
        System.out.println("emptyLength=" + settings.empty().length);

        Object defaultRoles =
                Settings.class.getMethod("roles").getDefaultValue();
        System.out.println("declaredDefault="
                + Arrays.toString((String[]) defaultRoles));
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 AnnotationArraySafetyDemo.java
java AnnotationArraySafetyDemo
~~~

**Stdout:**

~~~text
roles=[reader, writer]
ports=[8080, 8443]
note=stable
firstSnapshot=[modified, writer]
sameArray=false
equals=true
hashEqual=true
emptyLength=0
declaredDefault=[reader, writer]
~~~

### Line-by-Line Explanation

1. `roles=[reader, writer]`: even though `rolesSnapshot[0]` was assigned `"modified"`, a new read via `settings.roles()` still sees the two original strings.
2. `ports=[8080, 8443]`: changing `portsSnapshot[0]` to `0` does not replace the annotation's `int[]` value.
3. `note=stable`: replacing the first element of `notesSnapshot` with `null` only modifies the snapshot. The `@Note("stable")` annotation in the original data remains readable.
4. `firstSnapshot=[modified, writer]`: the array held by the calling code in the local variable really is **mutable**. This is the other half of the key distinction.
5. `sameArray=false`: with standard OpenJDK implementations and non-empty arrays, a subsequent call creates a separate array copy. **This is an empirical observation of this example; you should not use `==` as a general API contract.**
6. `equals=true`: `@Settings` on `Service` and `ServiceCopy` have the same element values, so the two annotations are equivalent **by value**, even though they are attached to two different classes.
7. `hashEqual=true`: two annotations that are equivalent according to `equals` have the same hash code. Modifying an external snapshot in the calling code does not alter the annotation content used to compute the hash.
8. `emptyLength=0`: the default `empty() default {}` represents a valid empty array, not `null`.
9. `declaredDefault=[reader, writer]`: Reflection reads **the default value declared on the annotation type** using `Method.getDefaultValue()`; this is not a shared variable for writing runtime configuration.

Note that `Settings.class.getMethod("roles")` retrieves a `Method` describing the `roles()` element of the annotation type. `getDefaultValue()` returns `Object`; the code casts it to `String[]` because it knows the exact declared element type. If an element has no default, this API returns `null`, which does not mean an annotation element is allowed to take `null` as a value.

The main code does not assume any specific format of `annotation.toString()` because that format is partly implementation-dependent. Every stdout line in the example is produced by the explicitly shown reads and comparisons.

## 7. `equals` and `hashCode` of Annotations with Array Elements

The `java.lang.annotation.Annotation` interface defines the `equals` contract based on **the annotation type and each of the element values**. Two annotations do not need to be **the same object reference** to be considered equal.

For array-typed elements, Java compares contents according to the corresponding `Arrays.equals` method, rather than using `==` between two array references. This has significant implications:

~~~java
String[] left = {"reader", "writer"};
String[] right = {"reader", "writer"};

System.out.println(left == right);             // false
System.out.println(Arrays.equals(left, right)); // true
~~~

If the same annotation type has identical element values, two annotation instances must be considered equivalent under the `Annotation.equals` contract. The returned arrays may be two distinct objects, yet their initial contents remain the same.

`Annotation.hashCode` is also based on **member names and member values**. For array values, the content-based hashing rule corresponding to `Arrays.hashCode` is used. For nested annotations, the rule applies recursively according to the annotation contract.

You do not need to compute hash codes manually with a formula in ordinary applications. However, you need to know:

- Do not use `annotationA == annotationB` in place of `annotationA.equals(annotationB)`.
- Do not use `annotationA.roles() == annotationB.roles()` to check whether two configurations have the same roles.
- When you need to compare **the value arrays by themselves**, use `Arrays.equals(a, b)` or an appropriate element-comparison utility.
- When you need to compare **the entire annotation**, use `Annotation.equals`; it has its own contract for each element and array.
- Do not build a cache relying on the ability to modify array snapshots to change `annotation.hashCode()`: such modification is not meant to mutate the original metadata.

`toString()` is useful for debugging, but the exact format of the annotation string may depend on the JDK/implementation. Avoid using the `toString()` string as a persistent data key or performing exact checks against unversioned text snapshots.

## 8. `getDefaultValue()` vs. Effective Values: Do Not Equate Them

There are two distinct questions when reading annotation arrays:

**A. “What value does the specific annotation on a class currently have?”**

~~~java
Settings settings = Service.class.getAnnotation(Settings.class);
String[] effectiveRoles = settings.roles();
~~~

The result here is the **effective** value: the value directly supplied at the annotation site if present; otherwise, it receives the default of `Settings.roles()`.

**B. “What default is the `roles()` element declared with?”**

~~~java
Object declaredDefault =
        Settings.class.getMethod("roles").getDefaultValue();
String[] defaults = (String[]) declaredDefault;
~~~

The result here is the default value belonging to the **annotation type**, regardless of whether `Service` overrides `roles`.

Example:

~~~java
@Settings(roles = {"admin"})
class AdminService {}
~~~

On `AdminService`, the effective `settings.roles()` is `{"admin"}`, whereas `Settings.class.getMethod("roles").getDefaultValue()` still describes the default `{"reader", "writer"}`.

Treat the array returned by `getDefaultValue()` as **read-only by intent**, and create your application's own copy if you need to modify it to build another configuration. Do not use mutating the array returned by Reflection as a means to update the annotation type's default.

An advanced point from the Java Language Specification: a default is declared on the annotation type and is applied **when the annotation is read**, rather than being copied as an explicit element value into every annotation usage site. Changing the default definition in another library version can change the effective value for annotation sites that omitted that element. That is a matter of **updating the annotation type definition**, not mutating a runtime array snapshot.

## 9. What You Should Not Infer

### 9.1. “Observable Immutability” Does Not Mean No Code Can Mutate Any Object Implementing an Annotation Interface

You might have a non-standard or custom implementation of an annotation interface in Java, or an application-created proxy. It is even possible to build an arbitrary `InvocationHandler` that returns an internally held array reference and then mutates it. Such objects **do not necessarily** exhibit the array-defensive behavior provided by standard JDK Reflection annotations.

Therefore, when saying “annotations return array copies,” this must be placed in the context of **annotation instances created/read through the standard Reflection mechanism**. It should not be treated as a guarantee about every object that can be cast to `Annotation` regardless of its origin.

### 9.2. Do Not Assume All Element Calls Return the Same Array Reference

`annotation.roles() == annotation.roles()` is not the right business question. Non-empty arrays may be cloned when returned; empty arrays may be shared because they have no elements to modify. Use array contents and length, not reference identity.

### 9.3. Do Not Assume Defensive Copy Means Deep-Copying Everything

If `Note[]` is cloned, copying the **array** does not mean each `Note` object is also copied along with it. With standard annotations, the elements of `Note` follow the annotation contract themselves, so you cannot use a setter on `Note` to alter metadata. If you build arbitrary Java structures outside the annotation API, a shallow copy may not be sufficient to protect mutable objects inside the array.

### 9.4. Do Not Turn Annotations into Mutable State Storage

If the application needs to add or remove roles at runtime, keep them in a configuration object, a managed collection, or a separate service state. Annotations are better suited for **static declarative** descriptions and values that processing code reads and interprets.

### 9.5. Do Not Equate Annotations with Immutable Collections

`List.of("reader", "writer")` returns an unmodifiable list; however, `annotation.roles()` returns `String[]`, which allows modifying elements **of the snapshot**. Calling `Arrays.asList(annotation.roles())` can create a list view backed by the snapshot array; modifying the list view can alter the snapshot, though it is not meant to modify the underlying annotation. If you want to use the data in an unmodifiable form in your code, convert it into an immutable structure under your control, such as `List.copyOf(Arrays.asList(annotation.roles()))`.

## 10. Common Mistakes

**Mistake 1 — Modifying the returned array and expecting the annotation to change.** `roles[0] = "admin"` only modifies the array held by the calling code. Reading the annotation again still returns the declared value; update the annotation source or the runtime configuration system properly.

**Mistake 2 — Calling the array immutable just because the annotation value is stable.** `String[]` is still a mutable array. Immutability here refers to the observable stability of the **metadata**, not Java forbidding element assignment on the copy.

**Mistake 3 — Using `==` to compare arrays.** `String[] a = annotation.roles(); String[] b = annotation.roles();` can contain equal values even though `a == b` is `false`. Use `Arrays.equals(a, b)`.

**Mistake 4 — Assuming an empty array must be cloned every time.** An empty array has no elements that can be modified, so an implementation may reuse it. Do not write assertions about the identity of an empty array.

**Mistake 5 — Confusing shallow copy and deep copy.** Copying the `Note[]` array at the container level does not mean the Note instances are newly created or provide a way to edit element values. With standard annotations, values are read according to the annotation's own contract.

**Mistake 6 — Comparing two annotations with `==`.** Different proxies can represent equivalent annotations. Use `equals` when you need annotation equality semantics.

**Mistake 7 — Comparing arrays with `Object.equals` when implementing `equals` yourself.** Java arrays inherit `Object.equals` by identity; the `Annotation.equals` contract requires comparing array contents. Use `Arrays.equals` when handling member values yourself.

**Mistake 8 — Thinking `getDefaultValue()` is a mutable configuration area.** This method is used to **read the default of the annotation type**. If you need to construct another configuration, clone the data into a separate object.

**Mistake 9 — Omitting runtime retention.** Without `@Retention(RUNTIME)`, an annotation type has a default retention of `CLASS`; `Class.getAnnotation(...)` will not see the annotation at runtime. The main demo explicitly specifies the retention.

**Mistake 10 — Confusing `null` and an empty array.** Annotation array elements cannot accept `null`; `default {}` is a valid empty array. `Method.getDefaultValue()` can return `null` when an element **has no default**, but that is a Reflection indicator rather than a valid annotation value.

**Mistake 11 — Printing an array with `println(array)` and expecting to see a list.** Use `Arrays.toString(array)` for one-dimensional arrays; for arbitrary multi-level Java structures, consider `Arrays.deepToString(...)`. Annotation elements themselves cannot be declared as multidimensional arrays like `String[][]`.

**Mistake 12 — Relying on `annotation.toString()` for strict format assertions.** Its content can be helpful, but the textual syntax of this method is partly implementation-dependent. Tests should directly check element values and `equals`/`hashCode` relationships.

## 11. Hands-on Exercises

1. Run `AnnotationArraySafetyDemo.java`. Before running it, predict each line of stdout and explain the role of defensive copying.
2. Remove the assignment `rolesSnapshot[0] = "modified"`. Observe the `firstSnapshot` and `roles` lines, and compare with the modified version.
3. Add `String[] zones() default {"north", "south"};` to `Settings`. Call `settings.zones()`, modify an element in the snapshot, and read it again to verify.
4. Add `@Settings(roles = {"admin"})` to another class and compare the new annotation with the default `@Settings` using `equals`; explain why they are not equal.
5. Add a class `@Settings(roles = {"reader", "writer"}, ports = {8080, 8443}, notes = {@Note("stable")})` without specifying `empty`. Compare it with `@Settings` using only defaults. Explain why `equals` evaluates **effective values** rather than merely whether elements were written explicitly.
6. Test `settings.empty() == settings.empty()` on your current JDK environment. Record the result, and explain why it must not be used as portable logic.
7. Use `Settings.class.getMethod("ports").getDefaultValue()` to retrieve the default array, cast it to `int[]`, print it with `Arrays.toString`, and distinguish this from calling `settings.ports()`.
8. Try `String[] a = settings.roles(); String[] b = settings.roles();` and compare `a == b` with `Arrays.equals(a, b)`. Explain the difference.
9. Create `Note[] copy = settings.notes(); copy[0] = null;`. Check `settings.notes()[0].value()` again and explain why the annotation value does not disappear.
10. Design a `RuntimeConfig` class containing a `List<String>` that can be modified according to business requirements, initialized using `Arrays.asList(settings.roles())` and copied into an appropriate structure. Explain why this state must be managed **outside** the annotation.

## 12. End-of-Lesson Checklist

| Question | Key Answer to Know |
| --- | --- |
| Can elements of an array returned from an annotation be reassigned? | Yes, it is a Java array received in the calling code |
| Does reassigning array elements modify the underlying Reflection annotation? | For standard annotations read by the JDK, no |
| What does a defensive copy help with? | Prevents external code from modifying the internal array used as the element value |
| Does an empty array necessarily create a new reference every time? | You should not rely on that assumption |
| Are two arrays with the same contents `==`? | Not necessarily; use `Arrays.equals` |
| Are two annotations of the same type with the same element values equal? | Yes, under the `Annotation.equals` contract |
| Does `Annotation.hashCode` consider array contents? | Yes, according to the member-values hashing rule |
| What does `getDefaultValue()` read? | The default on the annotation type definition |
| How do you actually change configuration at runtime? | Use separate state/config, do not modify annotation snapshots |

**Conclusion:** An annotation is metadata that code can read and interpret. When an element is an array, the API still returns a mutable array type, but the JDK's defensive copies preserve **the observable annotation values on subsequent reads**. Do not confuse snapshot mutation with annotation mutation, and compare values rather than array identity.

### References

- [Java SE 17 — `java.lang.annotation.Annotation`: equals, hashCode, toString, annotationType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html).
- [Java SE 17 — `java.lang.reflect.Method.getDefaultValue()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue()).
- [Java SE 17 — `java.util.Arrays`: toString, equals, hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html).
- [Java Language Specification 17 — `9.6.2`: Defaults for Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2).
