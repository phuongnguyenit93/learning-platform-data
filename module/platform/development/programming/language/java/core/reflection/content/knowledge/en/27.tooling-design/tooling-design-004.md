# Filtering `static`, `synthetic`, `bridge`, and Unsuitable Members When Designing Reflection Tools

## 1. Why does a Reflection tool need to filter members?

A class may contain `static` constants, compiler-generated fields, bridge methods for generic dispatch, `Object` methods, or administrative APIs that the tool must not expose. `getDeclaredMethods()` and `getDeclaredFields()` list candidates according to query scope; they **do not enforce business contracts**.

An inspector displaying instance behavior may exclude `static` and `bridge`; a bytecode analyzer needs to keep those very members. Therefore, filtering is based on **read/write/invoke role**, signature, visibility, annotations, and declaration source, with explicit decisions for `synthetic`. The Java 17+ example in this article illustrates both filters: displayable methods and writable fields.

## 2. Reading metadata accurately before filtering

`Class<?>` returns the following member groups:

| API | Scope | Key points to note |
| --- | --- | --- |
| `getDeclaredMethods()` | Methods declared directly on the class/interface, all visibilities | Does not automatically include inherited methods; may show bridge/synthetic methods |
| `getMethods()` | `public` methods of the type and inherited `public` methods | May include `Object` methods; not limited to methods declared by the type |
| `getDeclaredFields()` | Fields declared directly, all visibilities | May include compiler-generated fields |
| `getFields()` | `public` fields of the type and inherited `public` fields | Fields may be hidden, so inspect declaring class |
| `getDeclaredConstructors()` | Constructors declared directly, all visibilities | Constructors are not inherited |
| `getConstructors()` | `public` constructors of the type itself | There is no "inherited constructor" |

**No return order is guaranteed** from the Reflection arrays above. Do not assign business meaning to `methods[0]` or `fields[0]`; if deterministic output is needed, sort explicitly by a clear key.

Member metadata can return:

- `member.getName()`: name.
- `member.getDeclaringClass()`: class/interface that directly declares the member.
- `member.getModifiers()`: modifier flag set, decoded with `java.lang.reflect.Modifier`.
- `member.isSynthetic()`: member marked synthetic in the class file.
- For `Method`: `isBridge()`, `isVarArgs()`, `getParameterTypes()`, `getReturnType()`, `getAnnotations()`.
- For `Field`: `getType()`, `getGenericType()`, and `isEnumConstant()`.
- For `Constructor<?>`: `getParameterTypes()`, `isVarArgs()`, and `isSynthetic()`.

Name and modifiers are **not sufficient** to decide accessibility or invocability: you must consider declaring class, package, module, receiver, and access rules at the call site.

## 3. Filtering `static` accurately

`static` has different meanings for fields and methods:

- **Static method** belongs to the class and does not require an instance receiver.
- **Static field** belongs to the class and does not require an instance receiver; it may be a constant, configuration variable, or shared data.
- **Instance method/field** operates on an object receiving the call.

Check with `Modifier.isStatic(member.getModifiers())`:

```java
boolean instanceMethod = !Modifier.isStatic(method.getModifiers());
boolean instanceField = !Modifier.isStatic(field.getModifiers());
```

This is an illustrative snippet; `method`, `field`, and importing `java.lang.reflect.Modifier` must exist in context.

A mapper for *one object's* state typically skips static fields. A tool listing utility functions might select **only** static methods. Do not apply an "exclude static" filter mechanically to every tool.

**Note:** A nested class declared `static` does not mean its constructors are "static constructors". Constructors are not static methods; filtering `Modifier.isStatic` on methods/fields differs from deciding to exclude constructors.

## 4. What is `synthetic`?

`Member.isSynthetic()` indicates the member is marked **`ACC_SYNTHETIC`** in class file metadata (as represented by the JVM/Reflection). Compilers may generate such members to implement language features such as internal access, captures, bridges, or other support mechanisms.

Examples you may encounter:

- A synthetic field holding a reference to the enclosing instance in certain inner classes.
- A compiler-generated field storing captured values from surrounding context.
- Compiler-generated helper methods.
- Bridge methods created to preserve polymorphism with generic erasure or covariant returns.

**Do not rely on names starting with `$`** to detect synthetic members: `$` is a valid character in Java identifiers, and compiler naming conventions vary across compilers/versions. At the same time, **not every compiler-generated member has `isSynthetic() == true`**: for instance, a valid record accessor or default constructor may be part of the type's source API.

`isSynthetic()` is suitable for removing technical members from business interfaces, whereas for bytecode analysis tools or debuggers, synthetic members themselves are data to observe.

## 5. Why does `bridge` appear, and how does it differ from `synthetic`?

A **bridge method** is a method the compiler may generate to preserve Java override/dispatch rules when bytecode signatures are affected by type erasure or covariant return types.

Source example:

```java
class Parent<T> {
    public T convert(T input) {
        return input;
    }
}

class Child extends Parent<String> {
    @Override
    public String convert(String input) {
        return input.toUpperCase();
    }
}
```

In bytecode, `Parent<T>.convert(T)` uses the erased form corresponding to `convert(Object)`. `Child.convert(String)` has a different signature at the JVM level, so the compiler may generate a bridge method `convert(Object)` in `Child` to cast the input type and invoke the actual `convert(String)`.

In Reflection:

- `Method.isBridge()` detects bridge methods.
- `Method.isSynthetic()` is also typically `true` on bridges generated by `javac`, but **the two concepts are not identical**. Evaluate both flags separately if policy requires it.
- If a tool exposes both the implementation method and the bridge as two business operations, users may see duplicates or two confusing signatures.
- **Do not delete or "disable" bridges at runtime.** Bridges are a valid part of Java polymorphic behavior. "Filtering" here only means deciding *whether to include them in the tool's API catalog*.

A developer-facing method lister commonly filters:

```java
!method.isBridge() && !method.isSynthetic()
```

Yet this remains a tool policy. Binary compatibility analyzers, debuggers, or bytecode inspectors may need to keep both.

## 6. Complete Java 17+ example: filtering methods and fields by goal

The example constructs two lists:

1. **Displayable methods:** only `public`, instance methods declared directly in the class, non-synthetic/non-bridge, zero parameters, with a return value.
2. **Fields writable through a data interface:** only `public`, instance fields, non-synthetic, non-`final`.

Save as **`MemberFilterDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class MemberFilterDemo {
    public static class Parent<T> {
        public T convert(T value) {
            return value;
        }
    }

    public static class Sample extends Parent<String> {
        public String label = "initial";
        public final String id = "fixed";
        public static String category = "demo";
        private String secret = "hidden";

        public static String version() {
            return "v1";
        }

        public String describe() {
            return "sample";
        }

        public void reset() {
            label = "";
        }

        @Override
        public String convert(String value) {
            return value.toUpperCase(Locale.ROOT);
        }

        private String internal() {
            return secret;
        }
    }

    public static void main(String[] args) {
        Method[] declaredMethods = Sample.class.getDeclaredMethods();
        Field[] declaredFields = Sample.class.getDeclaredFields();

        List<String> visibleMethods = Arrays.stream(declaredMethods)
                .filter(m -> Modifier.isPublic(m.getModifiers()))
                .filter(m -> !Modifier.isStatic(m.getModifiers()))
                .filter(m -> !m.isSynthetic() && !m.isBridge())
                .filter(m -> m.getParameterCount() == 0)
                .filter(m -> m.getReturnType() != void.class)
                .map(Method::getName)
                .sorted()
                .toList();

        List<String> writableFields = Arrays.stream(declaredFields)
                .filter(f -> Modifier.isPublic(f.getModifiers()))
                .filter(f -> !Modifier.isStatic(f.getModifiers()))
                .filter(f -> !Modifier.isFinal(f.getModifiers()))
                .filter(f -> !f.isSynthetic())
                .map(Field::getName)
                .sorted()
                .toList();

        long bridgeCount = Arrays.stream(declaredMethods)
                .filter(Method::isBridge)
                .count();

        System.out.println("methods=" + visibleMethods);
        System.out.println("writableFields=" + writableFields);
        System.out.println("bridges=" + bridgeCount);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac MemberFilterDemo.java
java MemberFilterDemo
```

Output when compiled with JDK 17 `javac`:

```text
methods=[describe]
writableFields=[label]
bridges=1
```

**Why is this output right?**

- `describe()` is selected: `public`, instance method, no parameters, returns `String`, and is neither bridge nor synthetic.
- `version()` is excluded because it is `static`; `reset()` is excluded because it returns `void`; `convert(String)` is excluded by the zero-parameter method policy; `internal()` is excluded because it is `private`.
- When overriding `Parent<String>.convert(String)`, `javac` generates a bridge like `convert(Object)` in `Sample`. The filter detects bridge/synthetic and excludes this method from the business list.
- `label` is selected because it is a `public`, instance, non-`final` field.
- `category` is excluded because it is `static`; `id` is excluded because it is `final`; `secret` is excluded because it is `private`.
- `sorted()` makes the output deterministic even though `getDeclaredMethods()`/`getDeclaredFields()` do not guarantee order.

**Limitations of the example:** This is a policy for building a display list and a writable-field list, **not** the right filter for every serializer, ORM, test framework, or API generator. The example uses `getDeclared...` so it only considers members declared directly in `Sample`, excluding inherited `Object` methods from the result. It checks modifiers but **does not yet check access permissions when invoked across different modules**: that must be addressed separately when integrating a real tool.

## 7. Defining "unsuitable" by role, signature, and visibility

Besides `static`, `synthetic`, and `bridge`, a tool often must check:

| Criterion | When to filter? | What must not be inferred |
| --- | --- | --- |
| `public` / `protected` / package-private / `private` | When exposing only public APIs or limiting access | Having the `public` modifier does not guarantee invocability across all modules |
| `abstract` | If the tool requires an operation to have its own implementation in the class | An abstract method can still be dispatched on a concrete subclass instance |
| `final` on fields | If the tool wants to *write* the field | A `final` field can still be read; does not mean synthetic |
| `transient` on fields | When serialization policy chooses to skip transient | Not automatically meaningless to every framework |
| `volatile` on fields | When appropriate concurrent access rules are needed | `volatile` does not mean a field must be excluded from all lists |
| `isVarArgs()` | If the invoker cannot construct varargs arrays | Varargs is still a valid Java method |
| Parameter list and return type | When the tool only supports a specific API shape | Do not judge a method broken just because its signature does not match policy |
| Annotations | When publishing only marked members | Annotations are only readable at runtime with appropriate retention |
| Declaring class and inheritance | When listing only the API of the class under inspection | Inherited/default methods may be APIs that should be kept |
| Actual accessibility | Before invoking a method, constructor, or reading/writing a field | Discovering metadata does not mean permission to use it |
| Name and overload signature pair | When building an operation registry | Using only the method name as key can overwrite overloads |

For example, a `transient` field is meaningful for traditional Java serialization, whereas a data-mapping library may have its own contract. A method `void reset()` is valid API; it is only excluded if **the tool is building a list of readable functions returning results** as in the example above.

If using the method list for automatic invocation, clearly determine what parameter types can be supplied: `Class<?>[] getParameterTypes()`, `getReturnType()`, `getExceptionTypes()`, `isVarArgs()`, and method/parameter annotations. Never randomly invoke every zero-argument method because they may cause side effects, write files, send requests, or mutate state.

## 8. Notes when traversing inheritance, overloads, and `Object` methods

`getDeclaredMethods()` only considers directly declared methods. `getMethods()` considers public methods within the scope noted above and may return familiar methods such as `toString()`, `hashCode()`, or `getClass()` where applicable.

If only business operations are desired, you can use an explicit annotation-based policy instead of inferring from names. When allowing inherited methods:

1. Clarify whether methods inherited from superclasses or interface `default` methods are accepted.
2. Use `getDeclaringClass()` to know where it was declared; do not assume every `Method` returned by `Child.class.getMethods()` belongs to `Child`.
3. Avoid treating all methods with the same name as duplicates: `process(int)` and `process(String)` are **two overloads**.
4. When constructing an operation key, include the name and **parameter type list**; if integrating JVM signatures/covariant returns/bridges, define a complete representation policy.
5. You may need to resolve overridden methods according to the "most specific implementation" rule if building a combined hierarchy catalog. Never take the first method returned as the default choice.

Example illustrating an overload-distinguishing key:

```java
static String signature(Method method) {
    String params = Arrays.stream(method.getParameterTypes())
            .map(Class::getTypeName)
            .collect(java.util.stream.Collectors.joining(", "));
    return method.getName() + "(" + params + ")";
}
```

This snippet must be placed in a class with imports for `java.lang.reflect.Method` and `java.util.Arrays`; it is not a standalone program. In multi-class systems, add declaring class/loader/module identity for cases requiring entity disambiguation. For stable comparison data, do not rely solely on `Method.toString()` or the natural order of Reflection APIs.

**Special cases:** Records have valid accessors like `name()`; enums have enum constant fields and language-provided methods; those items may not carry the synthetic flag. If a tool wishes not to publish them, it must have explicit rules based on **class kind/role/annotation**, rather than inferring from `isSynthetic()`.

## 9. Annotation whitelisting and explicit policy

For a tool that performs real actions, a safer approach than automatically invoking every public method is requiring an annotation that identifies supported operations. The annotation needs `@Retention(RetentionPolicy.RUNTIME)` to be read via Reflection at runtime.

Illustrative example:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface ToolAction {}

class ExampleActions {
    @ToolAction
    public String status() {
        return "OK";
    }

    public void deleteAll() {
        // Not automatically published because @ToolAction is missing.
    }
}
```

This is an illustrative snippet without `main`. While iterating over `Method`, you can add `method.isAnnotationPresent(ToolAction.class)` to accept only intentionally declared operations. A real system must also authenticate user permissions, constrain parameters, handle errors, and manage side effects; annotations **do not by themselves grant access rights or security**.

Decide annotation inheritance/override rules upfront. `@Inherited` only defines inheritance rules for annotations on **classes**; it does not implicitly cause annotations on superclass methods to be inherited as a framework might desire. If custom rules are needed for overridden methods, walk the hierarchy and define that logic explicitly.

## 10. Constructors and nested classes

Constructors do not use `Method.isBridge()`; you can check `Constructor.isSynthetic()`, visibility, annotations, and parameter lists. Constructors are not inherited, so `getDeclaredConstructors()` and `getConstructors()` have markedly different semantics from methods.

For example, dependency injection tools typically pick a constructor with an appropriate annotation or by a deterministic convention. Never default to picking the **first constructor** in the array; Reflection ordering is unstable. Never automatically invoke every discovered constructor: constructors can do expensive work, allocate resources, or have side effects.

For nested classes, distinguish:

- `static` nested classes usually do not need an enclosing instance to be instantiated.
- Non-static inner classes usually hold a reference to an enclosing instance, and their bytecode constructors may carry an additional parameter related to the enclosing instance.
- The compiler may generate synthetic fields supporting that relationship.

Therefore, tools that automatically construct constructor arguments must inspect **actual parameter types**, rather than inferring from source appearance or skipping all synthetic parameters based on rigid assumptions.

## 11. Access rights: "eligible for display" is not yet "invocable"

Before calling `Method.invoke(...)`, `Constructor.newInstance(...)`, or `Field.get/set(...)`, check the caller's and module's access permissions. A `public` class in a package not exported to the calling module may still be inaccessible in the expected way. `getDeclaredMethod` finding a private member does not turn the private member into public.

Practical points:

- `method.canAccess(receiver)`, `field.canAccess(receiver)`, or `constructor.canAccess(null)` can help check access in the appropriate context; instance members require a matching receiver, static members use `null`.
- Do not abuse `setAccessible(true)` to bypass protection; the Java Platform Module System (JPMS) may reject deep reflection, e.g., throwing `InaccessibleObjectException`. `opens` and `exports` serve different purposes.
- If switching to `MethodHandle` or `VarHandle`, `MethodHandles.Lookup` operations still carry their own access model; having a `Method` does not guarantee `unreflect` will succeed.
- When a registry caches metadata/handles by class, consider class loader lifecycles: a global cache can pin plugin classes and prevent unloading.

Metadata filters can identify *candidates*. Before execution, the tool must verify actual operation capabilities and access control policies in the user/program context.

## 12. Verifying filter quality in real systems

A reliable filter should include checks for:

- **Generic bridge:** an override whose erasure generates a bridge does not appear twice in the business list, yet Java dispatch continues to work.
- **Static:** static fields/methods are included or excluded according to the published policy.
- **Synthetic:** compiler-generated members do not slip into the business catalog if policy forbids them, and non-synthetic members are not accepted blindly either.
- **Final, private, transient, varargs:** evaluated individually according to read, write, invoke, or serialization goals.
- **Overload:** `f(int)` and `f(String)` have distinct identities.
- **Inheritance/default method:** neither dropped nor duplicated unintentionally.
- **Enum/record/nested class:** tested against specific class kinds, not just field/method names.
- **Module/class loader:** same type name defined by different loaders is not treated as one class; access errors are handled transparently.
- **Determinism:** results are sorted using a consistent comparator/key, independent of Reflection order.
- **Side effects:** only invoke members permitted by contract and authorization; metadata listing tools must not speculatively run every method.

A good design separates three steps: **metadata collection → validity decision → execution or publication**. This lets you test filter predicates independently, explain why a member was skipped, and change policies per task without altering Java runtime behavior.

### Self-check questions

1. Why can `getDeclaredMethods()` return more methods than the number written directly in a subclass's source code?
2. What is `Method.isBridge()` used to detect? If a bridge is synthetic, should bridge checks be skipped in every tool?
3. For an object serializer, when is `Modifier.isStatic` a reasonable criterion? When is it the wrong criterion?
4. Why can a `final` field be read yet usually shouldn't appear in a writable list?
5. Why can using only the method name as a registry key lose overloads?
6. How do `getMethods()` and `getDeclaredMethods()` differ regarding inherited members and visibility?
7. If a `Method` is public but the target package is not exported to the calling module, can the access check step be skipped?
8. Why does an annotation whitelist require `RetentionPolicy.RUNTIME`, and why is an annotation still insufficient to guarantee a safe call?

**Key takeaway:** `static`, `synthetic`, and `bridge` are technical characteristics with specific meanings. Reflection tools should filter them according to a **concrete usage contract**, combined with visibility, signature, access permissions, inheritance, annotations, and executability; never treat any single flag as the sole quality criterion.
