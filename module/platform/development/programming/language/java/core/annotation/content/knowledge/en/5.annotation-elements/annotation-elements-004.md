# One-Dimensional Arrays and Unsupported Element Types in Java Annotations

## 1. Why are annotation element types restricted?

When defining an annotation type with `@interface`, each *element* declares the data type that a user can supply to the annotation. For example:

```java
@interface Topics {
    String[] names();
}
```

`names()` is an **element returning `String[]`**, not a method used to process an arbitrary array. The annotation usage site must provide a valid value directly in the source code:

```java
@Topics(names = {"java", "annotation"})
class Guide {}
```

Because annotations are metadata recorded by the Java compiler according to specific rules, elements can only have certain types. Java allows **one-dimensional arrays** of valid element types, but does **not** allow multidimensional arrays, collections, arbitrary objects, or generic types just because they are also valid Java types.

The goal of this lesson is to accurately answer three questions:

1. Which types can be declared for an annotation element, especially when adding `[]`?
2. How do you write values and default values, and how do you read array values?
3. Why are `String[][]`, `List<String>`, `Object[]`, `Integer[]`, and many other types rejected by the compiler?

## 2. List of element types allowed by Java

An annotation element can have a return type from the following categories:

| Category | Valid element example | Valid one-dimensional array form |
|---|---|---|
| Primitive type | `int count();`, `boolean enabled();` | `int[] codes();`, `boolean[] flags();` |
| `String` | `String title();` | `String[] tags();` |
| `Class` and forms with appropriate type parameters | `Class<?> type();` | `Class<?>[] types();` |
| `enum` type | `Level level();` | `Level[] levels();` |
| Another annotation type | `Option option();` | `Option[] options();` |

For the primitive category, all eight types `boolean`, `byte`, `short`, `int`, `long`, `char`, `float`, and `double` are valid, in both single and one-dimensional array forms.

```java
enum Level {
    LOW, MEDIUM, HIGH
}

@interface Option {
    String key();
    String value();
}

@interface Settings {
    int[] retryDelays();
    String[] aliases();
    boolean[] checks();
    Class<?>[] processors();
    Level[] levels();
    Option[] options();
}
```

All declarations in `Settings` are valid. `Class<?>[]` is **a one-dimensional array with elements of type `Class<?>`**, while `Option[]` is a one-dimensional array containing nested annotation values.

The `[]` only indicates one dimension. There are no exceptions for multidimensional arrays: even `String[][]` and `int[][]` are not allowed as the return type of an annotation element.

**Note:** These constraints apply to *elements* such as `String[] tags();`. A regular Java variable can use many other types and data structures; do not confuse the rules for annotation elements with the rules for Java variables, fields, or methods in general.

## 3. How to declare a one-dimensional array

Syntax:

```java
@interface Marker {
    String[] labels();
    int[] statuses() default {200};
}
```

Where:

- `String[] labels();` declares a required element whose value is a string array.
- `int[] statuses() default {200};` declares an optional element, defaulting to an array containing a single integer `200`.
- `default {}` represents an **empty array** and is also a valid default value.
- The element name is followed by empty `()` because annotation elements cannot declare method parameters.

An example of both primitive arrays and object arrays from the supported categories:

```java
@interface BuildProfile {
    String[] modules() default {};
    int[] supportedVersions() default {17, 21};
    char[] markers() default {'A', 'B'};
    boolean[] featureFlags() default {true, false};
}
```

Although `String[]` and `Class<?>[]` have array syntax similar to regular Java, how **annotation values are declared** has its own restrictions. The following section explains this in detail.

## 4. How to pass an array when using an annotation

Given the declaration:

```java
@interface Roles {
    String[] names();
}
```

There are three valid usage forms:

```java
@Roles(names = {"ADMIN", "EDITOR"}) // Two elements
class AdminService {}

@Roles(names = {"USER"})            // One element
class UserService {}

@Roles(names = {})                  // Empty array
class PublicService {}
```

In the annotation value position, the `{...}` list acts as an annotation-specific *array initializer* syntax containing values matching the element type.

If there is only **one** value of the array element type, Java allows omitting the curly braces:

```java
@Roles(names = "GUEST")
class GuestService {}
```

`@Roles(names = "GUEST")` is equivalent in array value to `@Roles(names = {"GUEST"})`. Both provide a `String[]` array of one element; Java does not change the declared type of `names()` to `String`.

Annotation array syntax also allows a trailing comma at the end of the list:

```java
@Roles(names = {"ADMIN", "EDITOR",})
class TrailingCommaExample {}
```

The trailing comma is optional and is often useful when each element is on its own line.

### Do not use `new` to initialize an array at the annotation usage site

The following snippet is **intentionally incorrect**:

```java
@Roles(names = new String[] {"ADMIN", "EDITOR"})
class InvalidConstruction {}
```

When passing an array to an annotation, use `{"ADMIN", "EDITOR"}`. An annotation element value has its own syntax and does not accept an array creation expression `new String[] {...}` in that position, even though that expression is valid when initializing a regular Java variable.

## 5. Arrays with an element named `value`: shorthand syntax

If an annotation declares an element named exactly `value`, Java allows omitting `value =` when using it:

```java
@interface Tags {
    String[] value();
}

@Tags({"core", "java"})
class CoreLesson {}

@Tags("java")
class SingleTagLesson {}

@Tags(value = {"annotation", "arrays"})
class ExplicitLesson {}

@Tags({})
class UntaggedLesson {}
```

All of the above forms are valid, with an array containing the corresponding number of elements.

The two shorthands here are **two independent rules**:

1. `@Tags(...)` omits the element name because it is named `value`.
2. `@Tags("java")` omits `{...}` because `value()` is a one-dimensional array while being supplied with exactly **one** element of type `String`.

For an element with a name other than `value`, the name cannot be omitted:

```java
@interface Routes {
    String[] paths();
}

@Routes(paths = {"/users", "/orders"})
class ValidRoutes {}

// Invalid: Routes does not declare a value() element
@Routes({"/users", "/orders"})
class InvalidRoutes {}
```

If multiple elements need to be passed, use the explicit `name = value` syntax:

```java
@interface Permissions {
    String[] value();
    boolean audited() default false;
}

@Permissions(value = {"READ", "WRITE"}, audited = true)
class ReportController {}
```

Do not mix an unnamed value form with named pairs, such as `@Permissions({"READ"}, audited = true)`; this is not valid syntax.

## 6. Default values of array-type elements

Use `default` in the **annotation type definition** to provide a value when the usage site does not pass that element:

```java
@interface SupportedFormats {
    String[] value() default {"json"};
    int[] versions() default {1, 2};
    String[] optionalTags() default {};
}

@SupportedFormats
class DefaultFormats {}

@SupportedFormats(value = {"xml", "csv"}, versions = {2, 3})
class CustomFormats {}
```

`@SupportedFormats` is valid because all three elements have `default`. A default value does not necessarily contain elements: `default {}` is a valid empty array.

Conversely, if an array element has no `default`, it is still **required**, even though the user can supply an empty array:

```java
@interface RequiredTags {
    String[] names();
}

@RequiredTags(names = {})
class ValidEmptyTags {}

// Invalid: missing names(), because it has no default
@RequiredTags
class MissingTags {}
```

The important distinction:

- `@RequiredTags(names = {})`: the element has been supplied with an empty array.
- `@RequiredTags`: the element is not supplied and has no default, so it is a compilation error.

`default null` is not valid for an annotation element. If you want the default to be "no elements", use `default {}`; if you want to distinguish between "not declared" and "declared as an empty array", you need to design appropriate metadata/values instead of relying on `null`.

## 7. Example of `enum`, `Class`, and nested annotation arrays

Suppose you want to declare a list of deployment environments, handler types, and configuration options:

```java
enum Environment {
    DEV, TEST, PROD
}

@interface Property {
    String key();
    String value();
}

@interface Deployment {
    Environment[] environments() default {Environment.DEV};
    Class<?>[] handlers() default {};
    Property[] properties() default {};
}
```

Usage:

```java
@Deployment(
    environments = {Environment.TEST, Environment.PROD},
    handlers = {String.class, Integer.class},
    properties = {
        @Property(key = "region", value = "ap-southeast"),
        @Property(key = "retry", value = "3")
    }
)
class DataProcessor {}
```

Each category has clear rules:

- `Environment[]` accepts **enum constants** such as `Environment.PROD`, not the string `"PROD"`.
- `Class<?>[]` accepts **class literals** such as `String.class` and `Integer.class`, not `new String(...)`.
- `Property[]` accepts **annotation literals** such as `@Property(...)`; do not instantiate with `new Property()`.
- All values still reside in a **one-dimensional array** of the exact element type.

With a single element, you can use the shorthand form such as `environments = Environment.DEV`, `handlers = String.class`, or `properties = @Property(key = "x", value = "y")`. However, the `{...}` form is often clearer when readers need to immediately recognize that the element is an array.

## 8. **Unsupported** element types

### 8.1. Multidimensional arrays

```java
@interface InvalidMatrix {
    String[][] labels();  // Invalid
    int[][] coordinates(); // Invalid
}
```

Java allows these types for regular variables or fields, but does not allow them as the return type of an annotation element.

If metadata needs to represent grouped data, you can use a **one-dimensional array of nested annotations**:

```java
@interface Row {
    int[] values();
}

@interface GridInfo {
    Row[] rows();
}

@GridInfo(rows = {
    @Row(values = {1, 2}),
    @Row(values = {3, 4})
})
class MatrixLikeConfig {}
```

`Row[]` is a one-dimensional array of an annotation type, and each `Row` has an element of type `int[]`. This structure describes rows of arbitrary length while still complying with annotation type rules. It is a **structured metadata model**, not an `int[][]` element.

### 8.2. `Object` and arbitrary classes

```java
@interface InvalidObjects {
    Object value();        // Invalid
    Object[] values();     // Invalid
    Integer[] numbers();   // Invalid
    StringBuilder text();  // Invalid
}
```

Not every object in Java is a valid annotation element type. `Integer` is a wrapper class, different from the primitive type `int`; `Integer[]` is invalid even though `int[]` is valid. Notable exceptions among supported reference types are `String` and `Class` according to the language rules.

Corresponding corrections, when appropriate for the meaning of the data:

- `Integer[] numbers()` → `int[] numbers()`.
- `StringBuilder text()` → `String text()`.
- `Object value()` → a specific supported type, such as `String`, an enum, `Class<?>`, or a nested annotation. Choosing the type depends on the metadata's meaning; there is no general automatic conversion.

### 8.3. Collection, Map, Optional, and arbitrary generic types

```java
import java.util.List;
import java.util.Map;
import java.util.Optional;

@interface InvalidContainers {
    List<String> tags();        // Invalid
    Map<String, String> props(); // Invalid
    Optional<String> label();    // Invalid
    List<String>[] groups();    // Invalid
}
```

`List<String>`, `Map<...>`, and `Optional<String>` are all valid Java reference types in many contexts, but they do not belong to the set of annotation element return types. Adding `[]` to `List<String>` does not make it valid either.

If you need list-like metadata, prefer a valid array such as `String[]` or an enum array. If you need key/value pairs, nested annotations can express them:

```java
@interface Pair {
    String key();
    String value();
}

@interface Pairs {
    Pair[] value() default {};
}

@Pairs({
    @Pair(key = "env", value = "test"),
    @Pair(key = "region", value = "asia")
})
class PairConfig {}
```

Do not use annotations to store complex dynamic object structures; metadata should generally be small, static, and clearly typed.

### 8.4. The `void` type, multidimensional arrays of valid types, and type variables

```java
@interface OtherInvalid {
    void execute();            // Invalid: void
    Class<?>[][] classes();    // Invalid: two-dimensional array
}
```

`Class<?>[]` is valid; `Class<?>[][]` is invalid because it has two dimensions.

An annotation type also cannot declare type parameters like a generic interface:

```java
// Invalid: an annotation type cannot declare <T>
@interface GenericMarker<T> {
    T value();
}
```

Instead of using a type variable `T` for an element, choose a supported type, such as `Class<?> value();` if you need to describe a class.

## 9. Why can't `new String[]` and array variables replace an annotation initializer?

The **element type** restriction and the **element value expression** restriction are two different issues:

- `String[] names();` is a *valid element type*.
- `@Names(value = {"a", "b"})` is a *valid way to pass a value*.
- `@Names(value = new String[]{"a", "b"})` is an *invalid value expression in an annotation*.
- `@Names(value = SOME_ARRAY)` is invalid if `SOME_ARRAY` is a regular array variable, even when it is declared `static final`.

Example:

```java
@interface Names {
    String[] value();
}

class Constants {
    static final String[] SAVED = {"a", "b"};
}

@Names({"a", "b"})
class ValidNameList {}

// Invalid: a new-array expression is not valid as an element value
@Names(new String[] {"a", "b"})
class InvalidNewArray {}

// Invalid: SAVED is an array in a variable, not an annotation array initializer
@Names(Constants.SAVED)
class InvalidVariable {}
```

A common point of confusion is that being a `static final` variable does not mean it is a *compile-time constant variable*. In Java, the concept of a constant variable applies only to a `final` variable of primitive type or `String` initialized with a constant expression. Arrays are objects, so a `static final String[]` does not become a valid annotation constant value.

Conversely, each individual string value inside an array initializer can be a `String` constant:

```java
@interface Labels {
    String[] value();
}

class LabelConstants {
    static final String MAIN = "core";
    static final String EXTRA = "annotation";
}

@Labels({LabelConstants.MAIN, LabelConstants.EXTRA})
class ValidConstants {}
```

Here, **each element** is a valid constant string; the array list itself is still supplied with `{...}`.

## 10. Complete Java 17+ example: declaring, using, and reading arrays

Create the file **`AnnotationArrayDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

enum Level {
    LOW, HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@interface Option {
    String key();
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Catalog {
    String[] names();
    int[] codes() default {200};
    Level[] levels() default {};
    Class<?>[] handlers() default {};
    Option[] options() default {};
}

@Catalog(
    names = {"core", "annotation"},
    codes = {200, 201},
    levels = {Level.LOW, Level.HIGH},
    handlers = {String.class, Integer.class},
    options = {
        @Option(key = "mode", value = "study")
    }
)
class CatalogService {}

public class AnnotationArrayDemo {
    public static void main(String[] args) {
        Catalog catalog =
                CatalogService.class.getAnnotation(Catalog.class);

        System.out.println("names=" + Arrays.toString(catalog.names()));
        System.out.println("codes=" + Arrays.toString(catalog.codes()));
        System.out.println("levels=" + Arrays.toString(catalog.levels()));
        System.out.println("handlers=" + Arrays.toString(catalog.handlers()));
        System.out.println("options=" + catalog.options().length);
    }
}
```

Compile and run with JDK 17 or later in the directory containing the file:

```bash
javac AnnotationArrayDemo.java
java AnnotationArrayDemo
```

Expected output:

```text
names=[core, annotation]
codes=[200, 201]
levels=[LOW, HIGH]
handlers=[class java.lang.String, class java.lang.Integer]
options=1
```

Explanation:

1. `Catalog` declares five elements; all of them are one-dimensional arrays of supported types.
2. `names()` has no `default`, so this value is required. The remaining elements have defaults and can be omitted at the usage site.
3. `@Catalog(...)` passes an array initializer for each element: strings, numbers, enums, class literals, and annotation literals.
4. `@Retention(RetentionPolicy.RUNTIME)` on `Catalog` allows `getAnnotation(Catalog.class)` to access the metadata at runtime.
5. `Arrays.toString(...)` converts the read arrays into strings for inspection; `catalog.options().length` confirms the nested annotation array has one element.

If you want an example using a single value instead of a single-element array, write `@Catalog(names = "single")` on another class. The compiler still treats `names()` as `String[]`, and when read, you will receive an array of length `1`.

## 11. How to identify and fix compiler errors

When `javac` rejects an annotation declaration or value, classify the error before fixing it:

| Code snippet or scenario | Cause | How to fix |
|---|---|---|
| `String[][] values();` | Multidimensional arrays are not supported | A one-dimensional array of a valid type, or a nested annotation |
| `List<String> tags();` | A collection is not an annotation element type | `String[] tags();` if appropriate |
| `Integer[] numbers();` | Wrapper classes are not in the set of valid types | `int[] numbers();` |
| `Object[] objects();` | The element type Object is invalid | Choose a supported type |
| `String[] tags() default null;` | `null` is invalid | `default {}` or a valid array of values |
| `@Tags(value = new String[]{"a"})` | Array creation syntax with `new` is invalid | `@Tags({"a"})` |
| `@Tags(value = SOME_STRING_ARRAY)` | Regular array variables cannot be used as an array element value | Declare `{...}` directly |
| `@Tags` when `value()` has no `default` | Missing required element | `@Tags({})` or pass an appropriate value |
| `@LevelSet(levels = {"LOW"})` | Wrong type: requires an enum, received a string | `levels = {Level.LOW}` |
| `@Types(values = {new Object()})` | Annotations do not accept arbitrary newly created objects | Use a class literal or another metadata type |

The exact name and details of the `javac` message depend on the code snippet and JDK version. When encountering `invalid type for annotation type element`, review the **return type in `@interface`**. When encountering an error message at the annotation usage site, check the **element type, array initializer, `default`, and constant nature of each value**.

In particular, **an empty array is different from a missing element**. If a required element has an array type, providing `{}` is valid, whereas omitting the element completely is still an error.

## 12. Self-check exercises

Consider the following three definitions:

```java
enum Color {
    RED, BLUE
}

@interface ColorOptions {
    Color[] colors() default {};
}

@interface MatrixValues {
    int[][] data();
}

@interface Strings {
    String[] value();
}
```

Evaluate:

1. Is `@ColorOptions(colors = {Color.RED, Color.BLUE})` valid?
2. Is `@ColorOptions(colors = Color.RED)` valid?
3. Is `@Strings({"a", "b"})` valid?
4. Is `@Strings("a")` valid?
5. Is `@Strings({})` valid?
6. Is `@Strings` valid?
7. Is `int[][] data()` in `MatrixValues` valid?
8. If `MatrixValues` is changed to `@interface MatrixValues { int[] data(); }`, is `@MatrixValues(data = {1, 2})` valid?

Answers and explanations:

1. **Yes.** This is a one-dimensional array containing two valid enum constants.
2. **Yes.** An array element can accept a single value of the same array element type in an annotation context.
3. **Yes.** `value()` allows omitting the name, and the array contains two valid strings.
4. **Yes.** Both the `value` name shorthand and the single-element array shorthand apply simultaneously.
5. **Yes.** An empty array has been supplied; `Strings.value()` is a required element, but it is not required to have elements in the array.
6. **No.** `Strings.value()` has no `default`, so the element cannot be omitted.
7. **No.** A two-dimensional array is not a valid annotation element type; the definition of `MatrixValues` itself will not compile.
8. **Yes.** `int[]` is a valid type and `{1, 2}` is a valid array initializer.

If you want to test compiling, put the valid definitions and correct examples into a separate file; remove or fix `MatrixValues` first, because an error right in the annotation definition can make other error messages harder to read.

## 13. Checklist to remember

- An annotation element may only return a primitive type, `String`, an appropriate `Class`, an enum, an annotation, or a **one-dimensional array** of those types.
- `T[]` is valid if `T` is an allowed element type; `T[][]` is invalid, even for `String` or `int`.
- `List`, `Map`, `Optional`, `Object`, wrappers such as `Integer`, and arbitrary classes are not supported element types.
- Use `{a, b}`, `{a}`, or `{}` to pass an array; when there is a single value of the array element type, Java allows omitting the curly braces.
- Use `@Annotation(...)` without writing the element name only when the element is named `value`.
- Default values for arrays are typically written as `default {...}`; `default {}` is a valid empty array; do not use `default null`.
- An array is a required element if it has no `default`, even though its valid value can be `{}`.
- Do not use `new T[]{...}`, a `static final` array variable, or a runtime call to produce a value for an annotation element.
- For enum/class/nested annotation arrays, each element must be an enum constant/class literal/annotation literal respectively.
- If you need to describe a multi-layered structure, consider a one-dimensional array of nested annotations instead of a multidimensional array or collection.

Properly understanding the difference between **regular Java data types** and **valid annotation element types** helps avoid errors when defining `@interface` and when attaching metadata values at usage sites.
