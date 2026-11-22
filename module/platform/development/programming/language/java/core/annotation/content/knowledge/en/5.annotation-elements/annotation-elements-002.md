# `Class<?>` and `Class<? extends T>` Elements in Java Annotations

In Java, an **annotation element** can store a reference to a *type* via a `Class` value. Typically, annotation authors declare `Class<?>` when they want to accept arbitrary types, or `Class<? extends SomeType>` when they only want to accept types belonging to an inheritance hierarchy or implementing a specific interface. The value placed on the annotation is typically a **class literal** such as `String.class` or `MyHandler.class`; it denotes the chosen type and does not pre-create an object of that type.

Short example:

```java
interface Handler {}

class EmailHandler implements Handler {}
class SmsHandler implements Handler {}

@interface AnyType {
    Class<?> value();
}

@interface HandlerType {
    Class<? extends Handler> value();
}

@AnyType(String.class)
class A {}

@HandlerType(EmailHandler.class)
class B {}
```

Both declarations are valid. With `@AnyType`, the compiler accepts `String.class` or `EmailHandler.class`. With `@HandlerType`, the compiler checks that the specified type must be `Handler` or a subtype/implementing type of `Handler`.

## 1. What does a `Class` element in an annotation actually hold?

A `Class<?>` is an object representing information about a Java type at runtime, commonly called a **class token**. In annotation syntax, `SomeType.class` is the way to specify a class token that complies with the rule that *annotation values must be determined at compile time*.

```java
@interface ModelInfo {
    Class<?> model();
}

@ModelInfo(model = String.class)
class StringModel {}

@ModelInfo(model = int.class)
class PrimitiveModel {}

@ModelInfo(model = String[].class)
class ArrayModel {}
```

Points to distinguish:

- `String.class` denotes the `String` type; it does **not** create a new string.
- `int.class` is the class literal for the primitive type `int`, not an object that can be instantiated via a constructor.
- `String[].class` is the class literal for the array type `String[]`.
- `Class<?>` is the **declared type** of the element; `String.class` is the **value** passed to the element.

An annotation stores metadata about a type choice. If the program needs to instantiate an instance from that class token, it must do so separately, for example via a factory, dependency injection, or reflection; merely writing `@ModelInfo(model = String.class)` does not automatically invoke a constructor.

According to JLS Java 17 §9.6.1, a valid return type of an annotation element can be `Class` or a parameterized form of `Class`, such as `Class<?>` or `Class<? extends Handler>`. This is a special valid case for annotation elements; do not generalize this to assume that any generic type such as `List<String>` or `Map<String, Integer>` can be used as an element.

## 2. Meaning of `?`: `Class<?>`

In Java generics, `?` is an **unbounded wildcard**: it does not fix which type the class token must represent. When declaring:

```java
@interface TypeHint {
    Class<?> value();
}
```

you can write:

```java
@TypeHint(String.class)
class A {}

@TypeHint(Integer.class)
class B {}

@TypeHint(Runnable.class)
class C {}

@TypeHint(int.class)
class D {}
```

The `?` does not turn the element into `Object`. Every value must still be a class token of type `Class`. For example, `@TypeHint("String")` is invalid because `"String"` is a `String`, not a `Class<?>`; `@TypeHint(new Object())` is also invalid.

You need to understand the **invariance** of the generic `Class<T>`:

```java
Class<String> stringType = String.class;

// Invalid even though String extends Object:
// Class<Object> objectType = String.class;

Class<?> anyType = String.class; // Valid
```

`String` is a subtype of `Object`, but `Class<String>` is not a subtype of `Class<Object>`. The wildcard addresses the need to accept multiple class tokens while still preserving the information that the value is of type `Class`.

## 3. Constraining with `Class<? extends T>`

`Class<? extends T>` is the class token of a type **assignable to `T`**, meaning `T` itself, a subclass of `T`, or a class implementing `T` if `T` is an interface.

In an actual annotation declaration, replace the illustrative symbol `T` with a **known specific type**, such as `Number`, `Runnable`, or a business interface that you define:

```java
@interface NumericType {
    Class<? extends Number> value();
}

@NumericType(Integer.class)
class IntegralCase {}

@NumericType(Double.class)
class DecimalCase {}

@NumericType(Number.class)
class BaseCase {}
```

`Integer` and `Double` inherit from `Number`; `Number.class` is also valid because the upper bound `extends Number` includes `Number` itself. Conversely:

```java
// Compile error: String is not a subtype of Number.
// @NumericType(String.class)
// class InvalidNumericCase {}
```

Here, `extends` in a wildcard covers both **class inheritance** and **interface implementation**:

```java
interface Task {}

class BackupTask implements Task {}
class CleanupTask implements Task {}

@interface TaskType {
    Class<? extends Task> value();
}

@TaskType(BackupTask.class)
class BackupConfig {}

@TaskType(CleanupTask.class)
class CleanupConfig {}

// Invalid: String does not implement Task.
// @TaskType(String.class)
// class WrongTaskConfig {}
```

Do not confuse `Class<? extends T>` with `Class<T>`:

| Element type | `Integer.class` | `Number.class` | `String.class` |
|---|---|---|---|
| `Class<?>` | Valid | Valid | Valid |
| `Class<Number>` | Invalid | Valid | Invalid |
| `Class<? extends Number>` | Valid | Valid | Invalid |

`Class<Number>` only accepts a class token whose corresponding generic type is `Number`; `Class<? extends Number>` extends this to subtypes of `Number`. Thanks to this, annotations can check an important part of the type contract at compile time.

### Why do examples often write `T` without declaring `@interface Config<T>`?

The symbol `T` in `Class<? extends T>` is usually a **type variable in generic explanations**. Java annotation interfaces **cannot be generic**: you cannot write `@interface Config<T>`. Therefore, do not use:

```java
// Invalid: annotation interfaces cannot declare type parameters.
// @interface Config<T> {
//     Class<? extends T> value();
// }
```

Replace `T` with an actual type name:

```java
interface Service {}

@interface ServiceConfig {
    Class<? extends Service> implementation();
}
```

Outside annotations, in regular generic classes or methods, `Class<? extends T>` can certainly use `T` as a type parameter; the restriction here comes from **annotation declaration rules**, not from a general prohibition in generics.

## 4. Syntax for passing a class literal to an element

When an element is named `value`, Java allows omitting the `value =` part:

```java
@interface JsonModel {
    Class<?> value();
}

@JsonModel(value = String.class)
class Explicit {}

@JsonModel(String.class)
class ShortForm {}
```

Both annotations above hold the same value `String.class`.

If the element name is not `value`, you must write the element name:

```java
@interface UseImplementation {
    Class<? extends Runnable> implementation();
}

@UseImplementation(implementation = Thread.class)
class WorkerConfig {}
```

`Thread` implements `Runnable`, so the assignment is valid. `@UseImplementation(Thread.class)` will fail with an error because the annotation does not have an element named `value`.

The value must be a **valid class literal**, not taken from a variable/runtime expression:

```java
class InvalidInputExamples {
    static final Class<?> CACHED = String.class;

    // Invalid: cannot pass a Class variable even if it is static final.
    // @JsonModel(CACHED)
    // class ByVariable {}

    // Invalid: a method call is evaluated at runtime, not a class literal.
    // @JsonModel(String.class.getClass())
    // class ByCall {}

    // Invalid: an annotation element does not accept null.
    // @JsonModel(null)
    // class NullValue {}
}
```

Another case: `List<String>.class` is not valid class literal syntax; Java generics apply *type erasure*, so you can use `List.class` but not `List<String>.class`. Similarly, `T.class` does not exist if `T` is a type parameter.

## 5. Runnable Java 17+ example: selecting a Formatter with an annotation

The example below uses `Class<? extends Formatter>` as a required element so the compiler only accepts compatible classes. At the same time, it uses `Class<?>` to hold metadata that does not require an inheritance relationship.

Create a single file named `AnnotationClassElementsDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.Locale;

interface Formatter {
    String format(String input);
}

class UppercaseFormatter implements Formatter {
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}

class LowercaseFormatter implements Formatter {
    public String format(String input) {
        return input.toLowerCase(Locale.ROOT);
    }
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface UseFormatter {
    Class<? extends Formatter> value();
    Class<?> marker() default Void.class;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Candidates {
    Class<? extends Formatter>[] value() default {};
}

@UseFormatter(value = UppercaseFormatter.class, marker = String.class)
@Candidates({UppercaseFormatter.class, LowercaseFormatter.class})
class Report {}

@UseFormatter(LowercaseFormatter.class)
@Candidates(LowercaseFormatter.class)
class Message {}

public class AnnotationClassElementsDemo {
    static void inspect(Class<?> owner) throws ReflectiveOperationException {
        UseFormatter config = owner.getAnnotation(UseFormatter.class);
        Candidates candidates = owner.getAnnotation(Candidates.class);

        Class<? extends Formatter> type = config.value();
        Formatter formatter = type.getDeclaredConstructor().newInstance();

        String[] names = Arrays.stream(candidates.value())
                .map(Class::getSimpleName)
                .toArray(String[]::new);

        System.out.println(owner.getSimpleName() + " -> "
                + formatter.format("Java"));
        System.out.println("marker=" + config.marker().getSimpleName());
        System.out.println("candidates=" + Arrays.toString(names));
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        inspect(Report.class);
        inspect(Message.class);
    }
}
```

Compile with Java 17 or a newer JDK that supports `--release 17`:

```bash
javac --release 17 AnnotationClassElementsDemo.java
java AnnotationClassElementsDemo
```

Output:

```text
Report -> JAVA
marker=String
candidates=[UppercaseFormatter, LowercaseFormatter]
Message -> java
marker=Void
candidates=[LowercaseFormatter]
```

What happens step by step:

1. `@UseFormatter(UppercaseFormatter.class)` or `@UseFormatter(LowercaseFormatter.class)` stores metadata about the class; the compiler verifies that the type implements `Formatter`.
2. `@Retention(RetentionPolicy.RUNTIME)` retains the annotation in runtime metadata so `Class.getAnnotation(...)` can read it. `@Target(ElementType.TYPE)` allows attaching the annotation to a class.
3. `config.value()` returns the selected `Class<? extends Formatter>`; `getDeclaredConstructor().newInstance()` is the call that **creates the actual object**, separate from the annotation declaration step.
4. `marker` has type `Class<?>`, so `String.class` is accepted. On `Message`, `marker` is omitted, so it receives `Void.class` from the default value.
5. `Candidates` holds an **array of class tokens**; a single-element array can be written in shorthand as `@Candidates(LowercaseFormatter.class)`.

The example is designed so that the classes have a no-argument constructor and are accessible from the program itself. In real-world applications, a class token does not guarantee that the chosen type has a suitable constructor or can be instantiated: an interface, an abstract class, a constructor with parameters, an inaccessible constructor, or a constructor that throws an exception can still cause failures at the instantiation step. In a framework environment, a factory or dependency injection typically handles instantiating the service.

**Note on verification scope:** `Class<? extends Formatter>` checks the **type relationship at compile time** for the class literal; it does not prove that the formatter executes correctly according to business requirements or is thread-safe.

## 6. `Class<?>[]` and `Class<? extends T>[]` arrays

Annotation elements allow **one-dimensional arrays** of valid `Class` types, including Class with wildcards. This is a way to describe multiple types at once.

```java
@interface Dependencies {
    Class<?>[] value();
}

@Dependencies({String.class, Integer.class})
class UsesSeveralTypes {}

@Dependencies(String.class)
class UsesOneType {}

@Dependencies({})
class UsesNoTypes {}
```

As with any array-typed annotation element, shorthand syntax can be used when there is only one element. If you want to restrict all elements to the same type family:

```java
interface Plugin {}

class FilePlugin implements Plugin {}
class NetworkPlugin implements Plugin {}

@interface Plugins {
    Class<? extends Plugin>[] value() default {};
}

@Plugins({FilePlugin.class, NetworkPlugin.class})
class TwoPlugins {}

@Plugins(FilePlugin.class)
class OnePlugin {}

@Plugins
class NoPlugins {}

@Plugins({})
class ExplicitlyEmpty {}
```

Comparison:

- `Class<?>`: a class token of any type.
- `Class<? extends Plugin>`: a class token belonging to the `Plugin` family.
- `Class<?>[]`: an array of class tokens of arbitrary types.
- `Class<? extends Plugin>[]`: an array of class tokens where **each element** belongs to the `Plugin` family.

An empty array `{}` is a valid value for an array-typed element; omitting the element is only valid if the declaration has `default`. Annotations do not allow multidimensional array element types such as `Class<?>[][]`; the element rules only permit one-dimensional arrays whose component type is in the list of allowed types.

## 7. `default`, sentinel classes, and the absence of `null`

For an element of type `Class<?>`, annotations do not allow passing `null`; nor is there a natural "no class" syntax as a `Class` value. Depending on requirements, the design can choose:

**Option 1: required element**

```java
@interface RepositoryBinding {
    Class<?> entity();
}

@RepositoryBinding(entity = String.class)
class StringRepository {}
```

Omitting `entity` will cause a compile error.

**Option 2: designate a class to represent the "unselected" state**

```java
@interface OptionalEntity {
    Class<?> value() default Void.class;
}

@OptionalEntity
class UnspecifiedEntity {}

@OptionalEntity(String.class)
class SpecifiedEntity {}
```

`Void.class` is simply a **sentinel convention chosen by the designer**. It is a valid class token and does not automatically mean "no value" in the Java language. Code that reads the annotation must explicitly interpret it:

```java
Class<?> selected = UnspecifiedEntity.class
        .getAnnotation(OptionalEntity.class).value();

if (selected == Void.class) {
    System.out.println("No entity selected");
}
```

If you use `Class<? extends Plugin>`, `Void.class` is **invalid** because `Void` does not implement `Plugin`. You can declare `default Plugin.class` if `Plugin` is an interface, but when reading it you need to treat `Plugin.class` as a sentinel by convention; the interface itself cannot be instantiated directly. Another option is to create a special plugin type per the application contract, or change the design so the element is not required where absence is needed.

## 8. What the `extends` constraint can and cannot check

When using `Class<? extends Service>`:

```java
interface Service {
    void execute();
}

abstract class AbstractService implements Service {}

class ConcreteService implements Service {
    public void execute() {
        System.out.println("done");
    }
}

@interface ServiceSelector {
    Class<? extends Service> value();
}

@ServiceSelector(Service.class)
class SelectInterface {}

@ServiceSelector(AbstractService.class)
class SelectAbstract {}

@ServiceSelector(ConcreteService.class)
class SelectConcrete {}
```

**All three cases are valid at compile time**: `Service` itself, the abstract class implementing `Service`, and the concrete class all satisfy the `extends Service` bound. However, only `ConcreteService` is suitable for direct instantiation via its corresponding constructor in this example.

The generic constraint **cannot** guarantee that:

- the specified class is concrete rather than an interface or an abstract class;
- it has a public no-argument constructor;
- the class has sufficient accessibility via reflection/module system;
- the constructor runs successfully and the object satisfies business requirements.

If the system truly requires those conditions, additional verification must be performed in the annotation-processing layer: via an annotation processor at compile time or via validation at startup/runtime. When the specified class is a subtype in Java terms, the compiler helps rule out choices from a **different type family** early on, but this does not replace checking instantiability.

## 9. Reading `Class<?>` elements and generic limitations at runtime

Because annotation metadata can persist until runtime if an appropriate retention is declared, a program can read:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Mapping {
    Class<?> requestType();
}

@Mapping(requestType = String.class)
class StringEndpoint {}

class MetadataReader {
    static void read() {
        Mapping mapping = StringEndpoint.class.getAnnotation(Mapping.class);
        Class<?> type = mapping.requestType();
        System.out.println(type.getName());
    }
}
```

`Class<?>` is an object carrying type information at runtime. However, Java generics have *type erasure*: the class token `List.class` does not carry the full parameterized type `List<String>`. An annotation element accepting `Class<?>` cannot represent a generic type such as `List<String>` solely with `List.class`.

If you need metadata that includes the generic type, consider an alternative design such as declaring multiple separate elements (a raw `Class<?>` type along with additional configuration information) or handling type representation at the appropriate reflection/annotation processing layer. Do not pretend that `Class<List<String>>` can be passed using `List<String>.class`.

## 10. Warnings and common errors

### Error 1: Passing a class name as a string

```java
@interface Select {
    Class<?> value();
}

// Invalid: String value, not Class.
// @Select("java.lang.String")
// class WrongName {}

@Select(String.class)
class CorrectName {}
```

If the API is designed to accept a class name as a string, the element must be declared as `String`; in that case, the compiler does not check type relationships the way it does with `Class<? extends T>`.

### Error 2: Generic bound mismatch

```java
@interface NumberType {
    Class<? extends Number> value();
}

// Invalid: String is not a Number.
// @NumberType(String.class)
// class Wrong {}

@NumberType(Integer.class)
class Right {}
```

This is a compile-time error, not an error that `@SuppressWarnings("unchecked")` can suppress.

### Error 3: Using `Class<T>` too strictly

```java
@interface ExactNumber {
    Class<Number> value();
}

// Invalid: Class<Integer> is not assignable to Class<Number>.
// @ExactNumber(Integer.class)
// class Wrong {}

@ExactNumber(Number.class)
class Right {}
```

If the actual requirement is "a class in the Number family", change it to `Class<? extends Number>`.

### Error 4: Passing a method result or a class token variable

```java
@interface InspectType {
    Class<?> value();
}

class Lookup {
    static final Class<?> TYPE = String.class;
}

// Invalid even though the variable is declared final:
// @InspectType(Lookup.TYPE)
// class Wrong {}

@InspectType(String.class)
class Right {}
```

An annotation value must satisfy the syntax/restrictions of an *element value*; a `Class<?>` variable does not become a class literal merely because it is `final`.

### Error 5: Confusing a class token with an instance

```java
interface Job {}
class SendJob implements Job {}

@interface JobConfig {
    Class<? extends Job> value();
}

@JobConfig(SendJob.class)
class Sender {}
```

Applying the annotation does not call `new SendJob()`. Only when other code explicitly reads `JobConfig` and requests a factory/reflective constructor can an instance be created. The type constraint helps verify that the object, **if created**, will belong to the `Job` family, but it does not create the object.

### Error 6: Assuming every class token can be instantiated

If an element is declared as `Class<? extends Runnable>`, `Runnable.class` still matches the bound because the interface itself satisfies the type bound; however, calling `Runnable.class.getDeclaredConstructor().newInstance()` cannot create an instance of an interface. The same applies to an abstract class or a class without a no-argument constructor. Define a clear contract for the application and validate it when processing the metadata.

### Error 7: Forgetting retention or single-element arrays

By default, annotations have `CLASS` retention; when you want to use `getAnnotation(...)` at runtime, `@Retention(RetentionPolicy.RUNTIME)` is required. For an array element, `@Plugins(FilePlugin.class)` is an array of **one** class token, while `@Plugins({})` is an empty array; this is valid syntax and does not change the declared type `Class<? extends Plugin>[]`.

## 11. Which element type should you choose for the problem?

| Requirement | Appropriate element type | Example value |
|---|---|---|
| Record an arbitrary type | `Class<?>` | `String.class` |
| Accept only types in an interface/base class family | `Class<? extends Handler>` | `EmailHandler.class` |
| Record multiple types without needing a shared bound | `Class<?>[]` | `{String.class, Integer.class}` |
| Record multiple implementations belonging to the same contract | `Class<? extends Handler>[]` | `{EmailHandler.class, SmsHandler.class}` |
| Require a single exact type, without accepting subtypes via generics | `Class<Number>` | `Number.class` |

In annotation designs used for plugins, strategies, or handlers, `Class<? extends Handler>` usually expresses intent more clearly than `Class<?>`: the compiler will catch passing a class that does not implement `Handler` early. For metadata describing a payload type or a type without a mandatory inheritance relationship, `Class<?>` may be more appropriate.

## 12. Self-check exercises

**Exercise 1.** Given:

```java
interface Parser {}
class JsonParser implements Parser {}
class XmlParser implements Parser {}

@interface Parsers {
    Class<? extends Parser>[] value();
}
```

Classify each of the following:

1. `@Parsers({JsonParser.class, XmlParser.class})`
2. `@Parsers(JsonParser.class)`
3. `@Parsers({})`
4. `@Parsers(String.class)`
5. `@Parsers`

**Answer:** 1, 2, and 3 are valid. Case 4 is invalid because `String` does not implement `Parser`. Case 5 is invalid because `value()` is a required element without a `default`.

**Exercise 2.** Why does `Class<?>` accept `String.class` whereas `Class<Object>` does not?

**Answer:** `Class<T>` is an invariant generic type: the relationship `String extends Object` does not imply `Class<String> extends Class<Object>`. The wildcard `?` allows `Class<?>` to refer to class tokens of multiple types.

**Exercise 3.** Is `@interface Factory<T> { Class<? extends T> value(); }` a valid annotation? How should you declare it if you want to restrict implementations to `Runnable`?

**Answer:** No. Annotation interfaces cannot be generic. Use `@interface Factory { Class<? extends Runnable> value(); }`.

**Exercise 4.** Is `@Factory(Runnable.class)` valid with the declaration from Exercise 3? Is it sufficient to invoke a constructor and run a Runnable?

**Answer:** It is valid in terms of type relationship because `Runnable` satisfies `extends Runnable`. However, `Runnable` is an interface and cannot be instantiated directly. The code reading the metadata still needs to check whether it can be instantiated or use an appropriate factory/container.

**Exercise 5.** Given `Class<?> marker() default Void.class;`, does omitting `marker` make the annotation return `null`?

**Answer:** No. The value of the element is `Void.class`, exactly as declared in the default; the "not selected" meaning exists only when the application explicitly adopts that convention.

## References

- [JLS Java SE 17 — `9.6.1 Annotation Interface Elements`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1): confirms the `Class` type, parameterized forms of `Class`, one-dimensional arrays, and the official `Class<? extends Formatter>` example.
- [JLS Java SE 17 — `9.7.1 Normal Annotations`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1): syntax and value restrictions for annotation elements.
- [Java SE 17 API — `Class<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): class tokens, `getAnnotation`, `getDeclaredConstructor`, and related runtime APIs.
- [JLS Java SE 17 — `4.5 Parameterized Types`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): wildcards and generic type relationships.
