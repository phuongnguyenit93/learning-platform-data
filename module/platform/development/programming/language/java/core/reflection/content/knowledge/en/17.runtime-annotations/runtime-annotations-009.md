# Reading Annotation Element Values via Methods of the Annotation Type

## 1. Annotation elements are zero-parameter methods

In Java, an annotation type is declared using `@interface`. Inside, **annotation elements** can be declared as **zero-parameter** methods returning a language-permitted type. Example:

~~~java
@interface Route {
    String value();
    int priority() default 1;
}
~~~

`value()` and `priority()` are neither public fields nor business methods with method bodies. They are **element declarations** of the annotation type. When a class or method is annotated:

~~~java
@Route(value = "/orders", priority = 5)
class OrderEndpoint {
}
~~~

Java stores the appropriate annotation name–value pairs in the metadata of the marked element. If the annotation has **`RetentionPolicy.RUNTIME`**, Reflection can read an annotation instance and invoke **its element methods** to obtain values:

~~~java
Route route = OrderEndpoint.class.getAnnotation(Route.class);
if (route != null) {
    System.out.println(route.value());    // /orders
    System.out.println(route.priority()); // 5
}
~~~

These illustrative fragments explain the principle; the complete Java 17 program in section 4 includes imports, retention, and all related types.

Core point: **Reading an annotation value means invoking the element method on an annotation instance**. There is no need to look up a field of the same name, do not use `Field.get`, and reading metadata itself **does not execute the business logic** described by the annotation.

## 2. Two objects to distinguish: annotation type and annotation instance

Suppose `@Rule("checkout")` is attached to `Checkout.class`:

- **The annotation type** is `Rule.class`. It is the `Class<Rule>` object representing the `@interface Rule` definition, containing declared element methods such as `String value()` and `int retries() default 3`.
- **The annotation instance** is the value `Rule rule = Checkout.class.getAnnotation(Rule.class)`, representing the annotation information attached to class `Checkout`. It implements the annotation interface and supplies element values.
- **The annotated target** is `Checkout.class`, not `rule`. The metadata belongs to the element carrying the annotation (class, method, field, parameter, ...).

Typical processing flow:

~~~text
Define @interface Rule
       |
       v
Use @Rule(...) on an element
       |
       v
Class file has annotation metadata (if retention allows)
       |
       v
Reflection: element.getAnnotation(Rule.class)
       |
       v
Rule annotation = ...
       |
       +-- annotation.value()
       +-- annotation.retries()
       +-- annotation.tags()
       +-- annotation.owner().name()
~~~

**Common mistake:** writing `Rule.class.getDeclaredMethod("retries")` and thinking the `Method` object alone already holds the value `5` of the annotation on `Checkout`. In reality, that `Method` describes the **element method** shared across the entire annotation type. To read **the value at a specific usage site**, you must invoke the method on the exact **annotation instance**. `Method.getDefaultValue()` is another API: it describes **the default value declared on the annotation type**, not the overridden value at a usage site.

## 3. Valid return types for annotation elements

An annotation element can only return one of the following types:

1. Primitive types: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`.
2. `String`.
3. `Class` (including parameterized `Class<?>` forms permitted by the language).
4. An `enum` type.
5. Another annotation type (nested annotation value).
6. A **one-dimensional** array of any of the above.

Example table:

| Element declaration | Usage on annotation | Type received when reading |
| --- | --- | --- |
| `String value();` | `@Rule("checkout")` | `String` |
| `int retries() default 3;` | `@Rule(retries = 5, ...)` | `int` |
| `boolean enabled() default true;` | `enabled = false` | `boolean` |
| `Level level() default Level.LOW;` | `level = Level.HIGH` | `Level` |
| `Class<?> handler() default String.class;` | `handler = Integer.class` | `Class<?>` |
| `String[] tags() default {};` | `tags = {"fast", "safe"}` | `String[]` |
| `Owner owner() default @Owner(name = "system");` | `owner = @Owner(name = "core")` | `Owner` |

Java does not permit an annotation element to return `List<String>`, `Map`, `Object`, multidimensional arrays, or other disallowed arbitrary types. Instead of returning `List<String>`, declare `String[]` and convert to a collection in application code if needed.

Additionally, **`null` is not a valid annotation element value**. An element must be specified at the usage site if it has no default, or takes its default when omitted. For a `String[]` element, an empty array `{}` differs from `null`. Element methods declare no parameters or `throws` clauses, and have no method body like ordinary methods.

## 4. Complete Java 17 example

Create the file **`AnnotationElementsDemo.java`**. The program defines an annotation with multiple element types, attaches one annotation with explicit values and one relying on defaults, then reads them via the annotation type's methods.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

enum Level {
    LOW, HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@interface Owner {
    String name();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Rule {
    String value();
    int retries() default 3;
    Level level() default Level.LOW;
    Class<?> handler() default String.class;
    String[] tags() default {};
    Owner owner() default @Owner(name = "system");
}

@Rule(
        value = "checkout",
        retries = 5,
        level = Level.HIGH,
        handler = Integer.class,
        tags = {"fast", "safe"},
        owner = @Owner(name = "core"))
class Checkout {
}

@Rule("fallback")
class Fallback {
}

public class AnnotationElementsDemo {
    public static void main(String[] args) throws Exception {
        Rule rule = Checkout.class.getAnnotation(Rule.class);

        System.out.println("present=" + (rule != null));
        System.out.println("annotationType="
                + rule.annotationType().getSimpleName());
        System.out.println("value=" + rule.value());
        System.out.println("retries=" + rule.retries());
        System.out.println("level=" + rule.level());
        System.out.println("handler=" + rule.handler().getSimpleName());
        System.out.println("tags=" + Arrays.toString(rule.tags()));
        System.out.println("owner=" + rule.owner().name());

        Rule fallback = Fallback.class.getAnnotation(Rule.class);
        System.out.println("fallback-retries=" + fallback.retries());
        System.out.println("fallback-level=" + fallback.level());
        System.out.println("fallback-handler="
                + fallback.handler().getSimpleName());
        System.out.println("fallback-tags="
                + Arrays.toString(fallback.tags()));
        System.out.println("fallback-owner=" + fallback.owner().name());

        Method retriesMethod = Rule.class.getDeclaredMethod("retries");
        System.out.println("reflective-retries="
                + retriesMethod.invoke(rule));
        System.out.println("declared-default="
                + retriesMethod.getDefaultValue());

        System.out.println("missing="
                + (String.class.getAnnotation(Rule.class) == null));
    }
}
~~~

Compile/run from the directory containing the file:

~~~bash
javac --release 17 AnnotationElementsDemo.java
java AnnotationElementsDemo
~~~

Output:

~~~text
present=true
annotationType=Rule
value=checkout
retries=5
level=HIGH
handler=Integer
tags=[fast, safe]
owner=core
fallback-retries=3
fallback-level=LOW
fallback-handler=String
fallback-tags=[]
fallback-owner=system
reflective-retries=5
declared-default=3
missing=true
~~~

The example's behavior was verified via the Java Compiler at Java 17 level and equivalent logic tested in JShell. This lesson uses annotations in the default package so no `module-info.java` file is needed; in real projects, declare packages explicitly.

### Output analysis

1. `@Retention(RUNTIME)` on `Rule` allows `Checkout.class.getAnnotation(Rule.class)` to retrieve the declared annotation, so `rule != null` is `true`. `annotationType()` returns `Rule.class`.
2. `rule.value()` is `"checkout"`, matching the value written in `@Rule(value = "checkout", ...)`. `rule.retries()` returns primitive `int` `5`, not the default `3`, because the annotation on `Checkout` overrides it.
3. `rule.level()` returns enum `Level.HIGH`; `rule.handler()` returns `Integer.class`; `rule.tags()` returns a `String[]` array holding two values; `rule.owner()` returns a **nested annotation instance** of type `Owner`, and `.name()` returns `"core"`.
4. `@Rule("fallback")` is shorthand syntax for the element named `value`. Because all other elements have `default` values, they can be omitted when attaching the annotation to `Fallback`. Hence `fallback.retries()` gets `3`, `fallback.tags()` returns an empty array, and `fallback.owner().name()` is `"system"`.
5. `Rule.class.getDeclaredMethod("retries")` retrieves the `Method` describing the element method. `retriesMethod.invoke(rule)` returns **the value on annotation instance `rule`**, i.e., `5`; because calling via `Method.invoke` has return type `Object`, the primitive `int` is boxed into `Integer` during reflection.
6. `retriesMethod.getDefaultValue()` reads **the default on the element declaration** (`3`). It does not change depending on where the annotation is attached. If the element declares no default, this API returns `null`.
7. `String.class.getAnnotation(Rule.class)` returns `null` because annotation `Rule` is not present on `String.class` under the corresponding lookup rules. Production code should always handle absent annotations.

Reading an annotation element **does not invoke a business handler** because it only returns metadata. For example, `handler = Integer.class` stores a class literal; it **does not instantiate `Integer`** and does not launch any processing logic.

## 5. Clean reading: calling element methods statically

If you know the annotation type when writing the program, the simplest approach is:

~~~java
Rule rule = SomeClass.class.getAnnotation(Rule.class);
if (rule != null) {
    String route = rule.value();
    int retries = rule.retries();
    Level level = rule.level();
    String[] tags = rule.tags();
}
~~~

This snippet is illustrative only, assuming `SomeClass` is annotated with `@Rule` and the types are defined as in section 4.

Advantages of the **typed API**:

- The compiler checks exact method names and return types.
- No need to cast `Object` from `Method.invoke`.
- Easy to read and refactor when the annotation type renames an element.
- Array/enum/class/nested annotation values retain their declared types, reducing runtime errors.

For annotations that must be present, depending on the API you can use `getDeclaredAnnotation` to retrieve annotations declared directly on the element, or `getAnnotation` for lookup following `AnnotatedElement` rules. Whichever API is used, if no matching annotation exists, the result is `null` (for single `getAnnotation`/`getDeclaredAnnotation`) — **do not call `rule.value()` before checking**.

Do not use `field.get(...)` on an annotation instance to read `value` or `retries`. An annotation type's structure is exposed via **element methods**, with no public fields of the same name to read.

## 6. Dynamic reading: element method introspection and `Method.invoke`

A framework may not know all element names in an annotation type ahead of time. In that case, it can accept `Annotation annotation` and iterate over element methods:

~~~java
import java.lang.annotation.Annotation;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

static void printElements(Annotation annotation) throws Exception {
    Method[] methods = annotation.annotationType().getDeclaredMethods();
    Arrays.sort(methods, Comparator.comparing(Method::getName));

    for (Method method : methods) {
        Object actualValue = method.invoke(annotation);
        Object defaultValue = method.getDefaultValue();

        System.out.println(method.getName()
                + " -> " + stringify(actualValue)
                + " (default=" + stringify(defaultValue) + ")");
    }
}

static String stringify(Object value) {
    if (value == null) return "null";
    if (value instanceof Object[] array) return Arrays.deepToString(array);
    if (value instanceof int[] array) return Arrays.toString(array);
    if (value instanceof long[] array) return Arrays.toString(array);
    if (value instanceof boolean[] array) return Arrays.toString(array);
    if (value instanceof char[] array) return Arrays.toString(array);
    if (value instanceof byte[] array) return Arrays.toString(array);
    if (value instanceof short[] array) return Arrays.toString(array);
    if (value instanceof float[] array) return Arrays.toString(array);
    if (value instanceof double[] array) return Arrays.toString(array);
    return String.valueOf(value);
}
~~~

These are **illustrative methods to insert into a class**, not a standalone file with `main`. `printElements` only needs an annotation instance already obtained via Reflection. To use these methods standalone, place them in a valid Java class and pass a corresponding annotation.

Key points:

- `annotation.annotationType()` returns the **exact annotation interface**; it is a clearer choice than `annotation.getClass()` when looking up elements. A runtime annotation instance may be implemented by the JDK as a proxy/implementation class, but **the implementation class is not your element contract**.
- `getDeclaredMethods()` on an annotation type returns the element methods declared on that annotation type itself. Do not rely on the returned array order; sort by name if stable logging is needed.
- `Method.invoke(annotation)` invokes the element method on the **annotation instance**. If the result is primitive, `invoke` returns a wrapper; if an array, an array object of the exact type; if a nested annotation, an annotation instance.
- `Method.getDefaultValue()` returns the default **declared** on the element, or `null` if no default exists. It does not tell you the actual value at each annotation usage.
- If you need to distinguish a value equaling the default because it was omitted when attaching the annotation versus because the author **explicitly wrote a value equal to the default**, Reflection generally shows only the **effective resolved value**. Do not use `actualValue.equals(defaultValue)` to conclude whether the author typed the element in source code.
- Do not treat `Annotation.toString()` as a stable data serialization interface. Read specific elements and format them yourself when outputting JSON/logs/APIs.

The loop above uses `instanceof Object[]` to display reference arrays; primitive arrays each have their own `Arrays.toString` branch. If you merely write `String.valueOf(value)` for an array, you may see a type-name/hash string instead of the array contents.

## 7. Distinguishing default from instance value

In `@interface RetryPolicy { int attempts() default 3; String label(); }`, the element `attempts()` has default `3`, while `label()` must be supplied. `RetryPolicy.class.getDeclaredMethod("attempts").getDefaultValue()` returns `Integer(3)`; calling `attempts()` on an annotation instance returns the **effective** value at the usage site, which can differ from 3. `getDefaultValue()` returns `null` for `label()` because no default is declared, which does not mean `label()` on a valid annotation returns null.

An effective value equaling the default does not prove the author omitted the element in source code. The separate lesson on `Method.getDefaultValue()` thoroughly analyzes data types, annotation evolution, and distinguishing interface default methods.

## 8. The special `value` case and syntax misconceptions

An element named `value` has Java's shorthand syntax when it is the sole element specified where the annotation is attached:

~~~java
@Rule("checkout")
class A {
}
~~~

It is equivalent to `@Rule(value = "checkout")` (remaining elements use defaults if any). However, if additional elements must be declared, use named form:

~~~java
@Rule(value = "checkout", retries = 5)
class B {
}
~~~

Do not interpret `value()` as a method with inherent business meaning or a special auto-running method. It merely has a convenient syntactic rule when applying the annotation. Syntax like `@Rule("checkout", retries = 5)` is not a permitted shorthand in Java; you must write `value =` when supplying additional element–value pairs.

**An annotation can have multiple elements**, yet only the single element `value` has this shorthand syntax. Elements without defaults must be passed at the annotation site even if their names are not `value`.

## 9. Reading on the right runtime element

To retrieve an annotation on a **method**, use `Method` from `clazz.getDeclaredMethod(...)` and read via `method.getAnnotation(MyAnnotation.class)`; calling `clazz.getAnnotation(...)` only queries annotations on the **class**. For fields, constructors, parameters, or TYPE_USE, you must likewise select the exact Reflection/`AnnotatedType` object. `@Retention(RUNTIME)` ensures matching metadata is kept for reading; `@Target` only restricts valid sites and creates no behavior on its own. Declared, inherited, and repeatable APIs are explained earlier in the chapter.

## 10. Runtime errors to handle when reading annotations

Reading annotation elements is normally straightforward, yet framework code processing class files from multiple versions can encounter exceptions:

| Situation | Related API | Interpretation/handling |
| --- | --- | --- |
| Annotation does not exist on element | `getAnnotation(...)` | Returns `null`; check before calling element methods |
| Annotation is not retained at `RUNTIME` | `getAnnotation(...)` | Metadata is unavailable to runtime Reflection; do not infer names/values |
| Reading element method from typed annotation instance | `rule.value()`, `rule.retries()` | Returns value with declared type |
| Getting default of an element with no default | `Method.getDefaultValue()` | Returns `null`; does not mean a valid annotation instance has value `null` |
| Calling `Method.invoke` with wrong instance or arguments | `invoke(...)` | Can throw `IllegalArgumentException` or related Reflection exceptions |
| Class literal in annotation references a type that no longer exists | Element returning `Class<?>` | Can throw `TypeNotPresentException` when accessing the element |
| Enum element references an enum constant removed at runtime | Element returning `enum` | Can throw `EnumConstantNotPresentException` |
| Element declaration type changed incompatibly with stored metadata | Reading element from older class file | Can throw `AnnotationTypeMismatchException` |
| A required element is missing due to incompatible changes across versions | Element method call | Can throw `IncompleteAnnotationException` |

When using `Method.invoke`, an exception thrown by the invoked method can be **wrapped in `InvocationTargetException`**, so inspect `getCause()` if diagnostics are needed. If a program assumes an element name from configuration and calls `getDeclaredMethod("name")` incorrectly, the lookup API can throw `NoSuchMethodException`; that is not an error caused by an annotation instance lacking a value.

Abnormal cases are usually tied to version-mismatched class files, missing dependencies, class loaders, or transformed bytecode. Do not write a generic annotation handler that catches all exceptions just to silently ignore required metadata.

## 11. Reading member values does not yet execute business logic

With `@MinimumAge(18)`, `annotation.value()` only returns the number `18`; it does not automatically read a field, compare ages, or reject input. Likewise, an element `handler()` returning `Class<?>` does not automatically instantiate and run a handler. A validator/framework or caller is needed to read the configuration, retrieve actual data, and make decisions. The final lesson of the chapter provides a runnable example and clarifies validation boundaries.

## 12. Checklist when reading annotation elements in an application

1. **Identify where the annotation is attached:** class, method, field, constructor, or parameter; query the right element.
2. **Verify retention:** `RUNTIME` is required for reading via runtime Reflection.
3. **Choose the right annotation type:** use `getAnnotation(MyAnno.class)` and check for `null`.
4. **Prefer typed accessors:** `anno.value()`, `anno.level()`, `anno.tags()` when the type is known; avoid unnecessary double Reflection.
5. **If handling generically:** use `annotation.annotationType().getDeclaredMethods()`, `method.invoke(annotation)`, and `getDefaultValue()` for their intended purposes.
6. **Do not confuse default with actual:** a default on the declaration does not prove the current annotation instance uses the default.
7. **Handle multi-type values:** primitives/wrappers, `String`, `Class<?>`, enums, nested annotations, one-dimensional arrays; format arrays properly.
8. **Consider class loaders and versions:** changing element signatures or referenced enums/classes can cause reading code to throw runtime exceptions.
9. **Keep metadata separate from business logic:** specific code/frameworks are needed to turn annotation values into validation, routing, transaction handling, or behavior.
10. **Test against real artifacts:** when multiple modules or bytecode tools are involved, verify annotations are truly retained with appropriate values in the released class files.

## 13. Self-check

**Question 1:** An annotation type declares `int retries() default 3;`. `Rule rule` on `Checkout` specifies `retries = 5`. What do `rule.retries()` and `Rule.class.getDeclaredMethod("retries").getDefaultValue()` return? **5 and 3 respectively.**

**Question 2:** `getAnnotation(MyAnno.class)` returns `null`. Can you call `.value()`? **No.** You must verify the annotation exists on the right element and is retained at runtime.

**Question 3:** An element declares `String[] tags() default {};`. Does calling `annotation.tags()` return `List<String>` or `String[]`? **`String[]`**, so you must use `Arrays.toString`/loop over the array to display its contents.

**Question 4:** Why is calling `rule.owner().name()` valid? **Because `owner()` returns an annotation instance of type `Owner`**, and `Owner` has element `name()` returning `String`.

**Question 5:** Can you use `annotation.getClass().getDeclaredMethods()` and treat every found method as a standard element? **You should not.** Use `annotation.annotationType()` to get the annotation type contract and avoid confusing it with the implementation class.

**Question 6:** `handler()` returns `Integer.class`. Does that mean the application instantiated `Integer` and ran a handler? **No.** That is only a class literal value; execution behavior must be decided by the caller.

**Question 7:** If `Method.getDefaultValue()` is `null`, does `annotation.element()` also have to be `null`? **No.** It only means the element declared no default; a valid annotation instance must have a value per annotation usage rules.

**Key takeaway:** **An annotation element is a zero-parameter method on the annotation type.** Obtain the annotation instance from the right element (`getAnnotation`), then invoke the element method (`annotation.value()` or `Method.invoke(annotation)`) to read the **actual value**. Use `Method.getDefaultValue()` only when you want to read the **declared default value**, and do not confuse metadata with business behavior.