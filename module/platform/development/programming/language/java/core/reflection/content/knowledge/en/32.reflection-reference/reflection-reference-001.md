# Comparison Table of `getX` and `getDeclaredX` in Java Reflection

## 1. Two API Groups Solving Two Different Questions

When working with `java.lang.Class<?>`, Reflection calls often have two "families" of similar-looking names:

- **`getX(...)` / `getXs()`**: for **methods, fields, constructors, and member classes**, the corresponding group typically focuses on **`public` members**, sometimes including **inherited** `public` members.
- **`getDeclaredX(...)` / `getDeclaredXs()`**: finds members **declared directly in the type being inspected**, including `public`, `protected`, package-private, and `private`; **it does not automatically traverse inherited members**.

Two important dimensions of distinction are:

1. **Visibility:** only `public` or all access levels?
2. **Origin:** is the member declared directly, or can it be inherited from a superclass/interface?

**There is no rule that "`getX` always traverses inheritance" for every kind of member.** For example, constructors **are not inherited** in Java. Annotations have their own inheritance rules via `@Inherited`, which do not apply identically to methods/fields. Therefore, you should learn **the table for each kind of `X`** instead of applying a single mantra to all APIs.

All examples in this article are based on Java 17 or later. `getX` and `getDeclaredX` only **return metadata or type information**; they do not automatically grant permission to invoke a `private` member, do not automatically execute a method, and do not automatically create an instance.

## 2. Overview Table: API Pairs on `Class<?>`

### 2.1. Methods — `Method`

| Requirement | `getX` | `getDeclaredX` |
| --- | --- | --- |
| Get a single method by name and parameter type list | `getMethod(String, Class<?>...)` | `getDeclaredMethod(String, Class<?>...)` |
| Get a set of methods | `getMethods()` | `getDeclaredMethods()` |
| Visibility | Only `public` methods | All access levels |
| Inherited methods | May include `public` methods from superclasses and interfaces | No; only directly declared methods |
| Private method in the current class | Not found with `getMethod` | Can retrieve metadata with `getDeclaredMethod` |
| Directly declared `public` method | Yes | Yes |
| `public` methods of `Object` | Usually appear in `getMethods()` when applied to a regular class | Only appear if the inspected class directly declares/overrides them |

Both single-lookup APIs inspect **name + declared parameter types**, without passing argument values. For example:

```java
Method one = type.getMethod("process", String.class);
Method two = type.getDeclaredMethod("process", String.class);
```

This is an illustrative snippet: a `Class<?> type` variable and an import of `java.lang.reflect.Method` are required. There is no receiver parameter in the metadata lookup call, even though invoking an instance method later requires an instance.

**A subtle point:** `Class.getMethod(...)` has rules for searching public members in the class/interface hierarchy, not "returning the method on the first superclass encountered." If a method is overridden, the API can select the matching method declared in the subclass. When you need to know who declared the method, use `method.getDeclaringClass()`. `getDeclaredMethod(...)` only checks the current class/interface.

### 2.2. Fields — `Field`

| Requirement | `getX` | `getDeclaredX` |
| --- | --- | --- |
| Get a single field by name | `getField(String)` | `getDeclaredField(String)` |
| Get a set of fields | `getFields()` | `getDeclaredFields()` |
| Visibility | Only `public` | All access levels |
| Fields from superclasses/interfaces | May appear if `public` | Does not automatically retrieve inherited fields |
| Private field declared in the current class | No | Can retrieve metadata |
| `static` or instance field | Both can be returned if matching | Both can be returned if matching |

Fields **are not overridden**, but can be **hidden (*field hiding*)** in a subclass. When both a superclass and a subclass have a field with the same name, the lookup APIs have their own policy for selecting the `Field` object; do not treat two fields with different declaring classes as one. Use `field.getDeclaringClass()` to verify. For data mapping tools, you often need to traverse the hierarchy manually and decide whether to allow hidden fields.

`getDeclaredFields()` can return compiler-generated fields (`isSynthetic()`), especially in inner classes or specially compiled constructs. This is still metadata of the class file; if you want to list business state, apply a separate filter.

### 2.3. Constructors — `Constructor<?>`

| Requirement | `getX` | `getDeclaredX` |
| --- | --- | --- |
| Get a single constructor by parameter type list | `getConstructor(Class<?>...)` | `getDeclaredConstructor(Class<?>...)` |
| Get a set of constructors | `getConstructors()` | `getDeclaredConstructors()` |
| Visibility | Only `public` | All access levels |
| Inherited from superclass | **No** | **No** |
| Private constructor of the current class | No | Can retrieve metadata |
| `public` constructor of the class itself | Yes | Yes |

Constructors do not have a method name supplied by the caller; the source name matches the class name, while Reflection selects by parameter type list. Superclass constructors **are not** inherited by subclasses.

A class can have multiple overloaded constructors. If you pass the wrong signature to `getConstructor(...)` or `getDeclaredConstructor(...)`, the program throws `NoSuchMethodException`, even when the class actually has a "similar-looking" constructor.

### 2.4. Member classes/interfaces — `Class<?>[]`

| API | Meaning |
| --- | --- |
| `getClasses()` | Returns **`public` member** classes and interfaces of the type; for classes, may include inherited public member types |
| `getDeclaredClasses()` | Returns **directly declared member** classes/interfaces in the type, regardless of visibility |

For example, `Parent.PublicNested` can appear in `Child.class.getClasses()` if `Child extends Parent`; `Child.PrivateNested` is in `Child.class.getDeclaredClasses()` but does not appear in `getClasses()` because it is not public.

**Do not confuse `getDeclaredClasses()` with "every class written inside a method".** This API targets *member classes/interfaces*, not arbitrarily listing all local classes/anonymous classes present in bytecode. To find the enclosing class of a known nested/local/anonymous class, see also `getDeclaringClass()`, `getEnclosingClass()`, `getEnclosingMethod()`, and `getEnclosingConstructor()` — however, they do not have a corresponding `getDeclared...` pair with the same semantics.

### 2.5. Annotations — `AnnotatedElement` and `Class<?>`

| API | Returned Content | Inheritance |
| --- | --- | --- |
| `getAnnotation(A.class)` | A single annotation of type `A` visible according to `AnnotatedElement` rules | For **classes** and annotations carrying `@Inherited`, may be retrieved from a superclass |
| `getDeclaredAnnotation(A.class)` | A single annotation of type `A` **directly declared** | Does not search from superclass |
| `getAnnotations()` | Annotations considered "present" | For **classes**, may include `@Inherited` annotations from a superclass |
| `getDeclaredAnnotations()` | Annotations directly on the element | Not inherited |
| `getAnnotationsByType(A.class)` | Annotations of type `A` according to repeatable and inheritance rules | May consider inheritance on classes under the `@Inherited` condition |
| `getDeclaredAnnotationsByType(A.class)` | Annotations of type `A` declared directly or contained in a directly declared repeatable container | Does not traverse superclasses |

**The `@Inherited` rule does not apply to annotations on methods, fields, constructors, or interfaces in the manner of class inheritance.** For example, if a subclass overrides a method, the annotation on the superclass method does not automatically appear as an "inherited" annotation on the new method. Frameworks wanting that policy must traverse the method hierarchy themselves.

With repeatable annotations (`@Repeatable`), the `ByType` APIs also understand annotations contained inside a **container annotation**; therefore, `getAnnotationsByType` cannot simply be replaced by a single `getAnnotation`.

**In summary:** The "declared" pair in annotations means **directly on the element**, but "non-declared" does not mean "every annotation from every ancestor".

## 3. API Groups Without a Corresponding `getDeclaredX` Pair

Not every API name starting with `get` has a `getDeclared` overload/family. For example:

- `getSuperclass()` and `getGenericSuperclass()`: retrieve the superclass of the type; there is no `getDeclaredSuperclass()`.
- `getInterfaces()` and `getGenericInterfaces()`: describe the interfaces directly declared in the `implements`/`extends` list of the inspected type; this is not an API for "all interfaces inherited across the tree" and there is no `getDeclaredInterfaces()`.
- `getTypeParameters()`: generic type variables declared on the class; there is no `getDeclaredTypeParameters()`.
- `getEnclosingClass()`, `getEnclosingMethod()`, `getEnclosingConstructor()`: describe the lexical enclosing context for a type when present; there is no directly declared pair.
- `getDeclaringClass()`: distinguishes a nested member type and its declaring class; not identical to `getEnclosingClass()` in all cases.
- `getRecordComponents()`: returns record component metadata for a record (Java 16+), or `null` if not a record; there is no `getDeclaredRecordComponents()`.

**Do not invent APIs named `getDeclaredX` by naming convention.** Look up the exact existing API on `Class` or `AnnotatedElement`. This article focuses on the Reflection groups that query members and annotations, not every method in the JDK.

## 4. Complete Java 17+ Example: Comparing the Results

The example uses a subclass with inherited public method/field, private method/field/constructor, an inherited public nested class, and a private nested class. It also demonstrates the `@Inherited` annotation difference.

Save as **`DeclaredVsPublicDemo.java`**:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.stream.Collectors;

public class DeclaredVsPublicDemo {
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @interface Tag {
        String value();
    }

    @Tag("from-parent")
    public static class Parent {
        public int inheritedField = 1;
        private int parentPrivateField = 2;

        public Parent() {}

        public void inheritedCall() {}

        private void parentPrivateCall() {}

        public static class PublicNested {}
    }

    public static class Child extends Parent {
        private String secret = "hidden";

        public Child() {}

        private Child(int code) {
            this.secret = "id-" + code;
        }

        public String local() {
            return "local";
        }

        private void hidden() {}

        private static class PrivateNested {}
    }

    public static void main(String[] args) throws Exception {
        Class<Child> type = Child.class;

        System.out.println("method inherited public="
                + (type.getMethod("inheritedCall")
                        .getDeclaringClass() == Parent.class));
        System.out.println("method inherited declared absent="
                + hasNoDeclaredMethod(type, "inheritedCall"));
        System.out.println("method private declared="
                + (type.getDeclaredMethod("hidden")
                        .getDeclaringClass() == Child.class));
        System.out.println("method private public absent="
                + hasNoPublicMethod(type, "hidden"));

        System.out.println("field inherited public="
                + (type.getField("inheritedField")
                        .getDeclaringClass() == Parent.class));
        System.out.println("field inherited declared absent="
                + hasNoDeclaredField(type, "inheritedField"));
        System.out.println("field private declared="
                + (type.getDeclaredField("secret")
                        .getDeclaringClass() == Child.class));
        System.out.println("field private public absent="
                + hasNoPublicField(type, "secret"));

        System.out.println("constructor public count="
                + type.getConstructors().length);
        System.out.println("constructor declared count="
                + type.getDeclaredConstructors().length);
        System.out.println("constructor private declared="
                + Modifier.isPrivate(
                        type.getDeclaredConstructor(int.class)
                                .getModifiers()));

        System.out.println("nested inherited public="
                + Arrays.asList(type.getClasses())
                        .contains(Parent.PublicNested.class));
        System.out.println("nested own private declared="
                + Arrays.asList(type.getDeclaredClasses())
                        .contains(Child.PrivateNested.class));

        System.out.println("annotation inherited="
                + (type.getAnnotation(Tag.class) != null));
        System.out.println("annotation declared absent="
                + (type.getDeclaredAnnotation(Tag.class) == null));

        String declaredNames =
                Arrays.stream(type.getDeclaredMethods())
                        .filter(m -> !m.isSynthetic() && !m.isBridge())
                        .map(Method::getName)
                        .sorted()
                        .collect(Collectors.joining(","));
        System.out.println("declared method names=" + declaredNames);
    }

    private static boolean hasNoDeclaredMethod(
            Class<?> type, String name) {
        try {
            type.getDeclaredMethod(name);
            return false;
        } catch (NoSuchMethodException e) {
            return true;
        }
    }

    private static boolean hasNoPublicMethod(
            Class<?> type, String name) {
        try {
            type.getMethod(name);
            return false;
        } catch (NoSuchMethodException e) {
            return true;
        }
    }

    private static boolean hasNoDeclaredField(
            Class<?> type, String name) {
        try {
            type.getDeclaredField(name);
            return false;
        } catch (NoSuchFieldException e) {
            return true;
        }
    }

    private static boolean hasNoPublicField(
            Class<?> type, String name) {
        try {
            type.getField(name);
            return false;
        } catch (NoSuchFieldException e) {
            return true;
        }
    }
}
```

### Compiling and Running

```bash
javac DeclaredVsPublicDemo.java
java DeclaredVsPublicDemo
```

Expected output on JDK 17:

```text
method inherited public=true
method inherited declared absent=true
method private declared=true
method private public absent=true
field inherited public=true
field inherited declared absent=true
field private declared=true
field private public absent=true
constructor public count=1
constructor declared count=2
constructor private declared=true
nested inherited public=true
nested own private declared=true
annotation inherited=true
annotation declared absent=true
declared method names=hidden,local
```

**Technical note on the example:** `Child`'s `getDeclaredMethods()` only includes the two methods `hidden` and `local` because the helper methods `hasNo...` reside in the **outer class `DeclaredVsPublicDemo`**, not in `Child`. `Child` is a member nested class; no compiler-generated methods are declared in the example above with JDK 17 `javac`. The `sorted()` call removes dependency on Reflection's return order.

### Analysis of Each Result Group

- `Child.class.getMethod("inheritedCall")` finds the public method from `Parent`; `getDeclaringClass()` is `Parent.class`. However, `Child.class.getDeclaredMethod("inheritedCall")` throws `NoSuchMethodException` because `Child` does not declare this method.
- `Child.class.getDeclaredMethod("hidden")` finds `Child`'s private method. `Child.class.getMethod("hidden")` does not find it because it is not public.
- `getField("inheritedField")` sees the public field from `Parent`; `getDeclaredField("inheritedField")` does not see it. Conversely, `getDeclaredField("secret")` finds `Child`'s private field, while `getField("secret")` does not.
- `Child` has one `public` constructor and one `private` constructor, so `getConstructors().length == 1`, `getDeclaredConstructors().length == 2`. None of `Parent`'s constructors are inherited.
- `Child.class.getClasses()` finds `Parent.PublicNested`; `Child.class.getDeclaredClasses()` finds `Child.PrivateNested` even though this nested class is private.
- `@Tag` is declared directly on `Parent` and carries `@Inherited`; `Child.class.getAnnotation(Tag.class)` returns the inherited annotation according to class rules, whereas `getDeclaredAnnotation(Tag.class)` is `null`.
- The checks reporting "absent=true" actually catch `NoSuchMethodException` or `NoSuchFieldException` properly. They do not mask other errors with `catch (Exception ignored)`.

## 5. Reading the Result Table Correctly: Do Not Confuse "Metadata Exists" with "Permission to Invoke"

`getDeclaredMethod("hidden")` succeeding does **not** mean code anywhere is allowed to invoke that private method.

Illustrative example, placed in a method with `throws ReflectiveOperationException` and appropriate instances:

```java
Method hidden = Child.class.getDeclaredMethod("hidden");
// hidden.invoke(child) may have access denied depending on the caller.
```

Consider:

- **Java visibility**: `public`, `protected`, package-private, `private`, and the relationship between caller/target.
- **Java Platform Module System (JPMS)**: whether the package has `exports` for public API or `opens` for deep reflection, and whether the caller module can read the target module.
- **`AccessibleObject`**: `canAccess(receiver)`, `trySetAccessible()`, or `setAccessible(true)` can check/alter the ability to suppress access checks, subject to JPMS limits.
- **Method handles**: `MethodHandles.Lookup` and `privateLookupIn` have their own permission rules; having a `Method` does not automatically grant permission to create a handle.
- **Target object and parameters**: correct receiver type, number/types of arguments, callable constructor; valid metadata does not guarantee the target operation will succeed.

**`getDeclared...` does not mean "bypass `private`"**. It means the lookup API is not restricted to public members; runtime access permission is the next step.

A type in a non-exported package can still expose metadata to some APIs, but that does not prove code in another module can invoke `public` members of that type. Do not use `Modifier.isPublic(...)` as the final conclusion about cross-module access.

## 6. Choosing Between `getMethods()` and `getDeclaredMethods()` for Each Tool

### 6.1. Building a List of Public APIs That Callers Are Allowed to Use

When you want to list a class's public API, `getMethods()` is usually a better starting point than `getDeclaredMethods()` because it can include public methods from superclasses/interfaces. However:

- The result may include methods from `Object` such as `toString`, `hashCode`, `getClass`.
- The result may include static, overloaded, bridge, or synthetic methods.
- Public metadata does not guarantee that callers from other modules have corresponding access rights.
- If the application only wants operations marked with an annotation, you must apply an additional separate filter.

Illustrative example: filtering public non-static, non-synthetic/bridge methods and sorting:

```java
List<Method> methods = Arrays.stream(type.getMethods())
        .filter(m -> !Modifier.isStatic(m.getModifiers()))
        .filter(m -> !m.isSynthetic() && !m.isBridge())
        .sorted(Comparator.comparing(Method::getName))
        .toList();
```

This snippet requires `Class<?> type` along with imports `List`, `Method`, `Arrays`, `Modifier`, `Comparator`; it is only a snippet, not a standalone program. Sorting by name helps display order, but **does not produce a unique key for overloaded methods**.

### 6.2. Inspecting the Detailed Structure of a Class

When writing a serializer, ORM, debugger, or bytecode analysis tool, `getDeclaredFields()`/`getDeclaredMethods()` may be more appropriate because they show the members actually declared in the class. If you need to walk through superclasses, you must traverse manually:

```java
for (Class<?> current = type;
        current != null;
        current = current.getSuperclass()) {
    for (Field field : current.getDeclaredFields()) {
        // Analyze fields belonging specifically to current.
        // Do not implicitly assume the tool has Field.get/set access.
    }
}
```

This is an illustrative snippet requiring a `Class<?> type` variable and importing `Field`. For interfaces, traversing `getInterfaces()` requires a separate branch (a class superclass loop does not automatically aggregate the interface hierarchy).

If you want to skip fields that are not instance state, check `Modifier.isStatic(field.getModifiers())`. If you want to keep only readable/writable fields, you must evaluate `final` and access rights. **Do not treat every declared member as a business-relevant member.**

### 6.3. Selecting a Constructor for Dependency Injection

`getDeclaredConstructors()` can be useful for discovering non-public or annotated constructors, but **you should not invoke the first constructor in the array**: the order is not guaranteed, and access rights must still be checked. `getConstructors()` is only suitable if the DI framework expects to use public constructors.

For example, constructors of records, enums, non-static inner classes, and classes with compiler-generated constructors have specific characteristics; you must use the real signature from Reflection, not infer it from display names.

### 6.4. Generating a Schema from Annotations

For class-level annotations carrying `@Inherited`, `getAnnotation` or `getAnnotationsByType` may make sense if the framework intentionally inherits metadata from superclasses. If the tool only wants annotations declared **on the class itself**, use `getDeclaredAnnotation` / `getDeclaredAnnotationsByType`.

Do not forget that method/field annotations **are not automatically inherited via `@Inherited`**. If the policy requires finding annotations on overridden methods, define clear rules for manually traversing superclasses/interfaces, resolving method signatures, and handling conflicts.

## 7. Common Mistakes

| Mistake | Why Is It Wrong? | How to Handle It |
| --- | --- | --- |
| Using `getDeclaredMethod` and expecting to find inherited methods | Declared only checks the current type | Use `getMethod` if inherited public methods are needed, or traverse the hierarchy manually |
| Using `getMethod` to find a private method | `getMethod` is public only | `getDeclaredMethod` to obtain metadata, then check valid access |
| Using `getDeclaredFields` and thinking you have all superclass fields | Does not traverse superclasses automatically | Loop `getSuperclass()` and use `getDeclaredFields()` for each type |
| Expecting `getConstructors` to return superclass constructors | Constructors are not inherited | Only query constructors of the class to be instantiated |
| Calling `getDeclaredClasses` and expecting to see all local/anonymous classes in methods | The API returns direct member classes/interfaces | Distinguish member/nested/local/anonymous types and enclosing APIs |
| Thinking `getAnnotation` and `getDeclaredAnnotation` are always identical | `@Inherited` class annotations can be inherited | Choose an explicit inheritance policy |
| Thinking `@Inherited` annotations propagate down to overridden methods | `@Inherited` does not apply that way to methods | Traverse the method hierarchy manually if needed |
| Ignoring `NoSuchMethodException`/`NoSuchFieldException` | Wrong name/signature causes lookup to fail | Catch the right exception type, log the name and parameters searched |
| Assuming `getDeclared...` lets you call private members across modules | Metadata lookup does not grant execution rights | Handle `opens`/`Lookup`/access properly instead of bypassing restrictions |
| Relying on `getMethods()[0]` or `getDeclaredFields()[0]` | Array order is not guaranteed | Sort with an intentional comparator/key |
| Using only method name as a key | Overloads can share the same name | Use name + parameter types, and declaring class/loader if needed |
| Calling Reflection on a `null` instance or wrong receiver | Metadata lookup is valid but invoke/field access is wrong | Validate receiver and arguments before execution |

**Note on exceptions:** The single-element calls `getMethod`, `getDeclaredMethod`, `getConstructor`, and `getDeclaredConstructor` can throw `NoSuchMethodException`; the single-element calls `getField` / `getDeclaredField` can throw `NoSuchFieldException`. APIs returning **arrays** normally return an empty array when there are no results, rather than throwing "NoSuchX" merely because the list has no members. In addition, there can still be other errors related to type loading, security, or the runtime environment.

## 8. Accurate Reflection Lookup Checklist

1. **Choose the data kind:** method, field, constructor, member class, or annotation?
2. **Determine required visibility:** public API or also non-public members?
3. **Determine scope:** only directly declared, or including superclasses/interfaces?
4. **Read the corresponding API table:** do not apply method inheritance rules to constructors/annotations.
5. **Match the exact signature:** methods and constructors rely on the parameter type list; with overloads, name alone is not enough.
6. **Verify declaring class:** use `getDeclaringClass()` of `Method`/`Field`/`Constructor` so you do not mistake the origin.
7. **Set filtering policy:** static, bridge, synthetic, abstract, final, annotations, and executability depending on the goal.
8. **Check access separately:** class visibility, JPMS `exports`/`opens`, caller, receiver, `trySetAccessible` when there is a valid reason.
9. **Sort results:** if stable display or snapshot comparison across runs is needed.
10. **Cache only with proper key and lifecycle:** `Class<?>` reflects class loader identity; avoid maps keyed only by class name if multiple loaders exist.

### Self-Check Questions

1. `Child.class.getMethod("run")` can find a public method of a superclass, whereas what happens with `Child.class.getDeclaredMethod("run")` if `Child` does not override it?
2. Why can `getDeclaredConstructor()` find a private constructor while `getConstructor()` cannot?
3. How do `getClasses()` and `getDeclaredClasses()` differ in visibility and inheritance?
4. Why can `Child.class.getAnnotation(Tag.class)` differ from `getDeclaredAnnotation(Tag.class)` when `Tag` carries `@Inherited`?
5. Does `getDeclaredFields()` include superclass fields? If not, how do you traverse the entire hierarchy?
6. Does succeeding with `getDeclaredMethod("hidden")` guarantee that `Method.invoke` from another module will succeed?
7. Why should you sort the results of `getDeclaredMethods()` yourself and check `Method.isBridge()` in an API generation tool?
8. Why can you not infer that every `getX` API in Java has a `getDeclaredX` counterpart?

**Conclusion:** For methods/fields/member classes, `getX` is generally the **public** lookup path and may include **inherited** members; `getDeclaredX` is the lookup path for **directly declared members with any visibility**. Constructors **are not inherited**; annotations follow their own `@Inherited` and repeatable rules. Choose APIs by **member kind + visibility + scope + execution rights**, rather than relying solely on the `Declared` prefix.
