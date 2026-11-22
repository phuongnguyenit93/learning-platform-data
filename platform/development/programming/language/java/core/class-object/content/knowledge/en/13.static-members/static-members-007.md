# `static import` in Java: utility and risk of reduced readability

When using a `static` member of another class, Java normally requires specifying the **type name** before the member, such as `Math.PI`, `Math.max(3, 5)`, or `Collections.emptyList()`. **Static import** allows bringing one or more **accessible** static member names into the compilation unit's name lookup scope, so in appropriate contexts you can write `PI`, `max(3, 5)`, or `emptyList()` without repeating the type name.

This syntax is very useful for mathematical formulas, test code, constants with clear meanings, and certain frequently used utility functions. However, if used indiscriminately, **readers have difficulty seeing where a name originates**, and it is easy to encounter confusion with names in the current class or other static imports. The issue does not lie in the performance of the import statement, but in the **semantics and maintainability of the source code**.

This lesson belongs to Java Core — *class-object*, **Static members** group. The goal is to properly understand static import, distinguish it from regular import and from `static` itself, know how to handle name collisions, and choose sensible usage guidelines. The standalone programs use **Java 17 or later**, accompanied by run commands and outputs you can cross-check.

## 1. From accessing static members to static import

A class can expose static fields and methods:

~~~java
double area = Math.PI * Math.pow(2.0, 2.0);
int larger = Math.max(3, 5);
~~~

These are two illustrative statements placed inside a method. `Math` is the `java.lang.Math` class, `PI` is a static field, and `pow` and `max` are static methods of that class.

They can be replaced with:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.max;
import static java.lang.Math.pow;
~~~

These import declarations must be placed in the **import section of the Java file**, after the `package` declaration if any and before the top-level class declarations. Then, in the class/method body, you can use:

~~~java
double area = PI * pow(2.0, 2.0);
int larger = max(3, 5);
~~~

Both ways compute the same values. **Static import does not copy fields or methods** into your class; it only helps the compiler resolve the **simple name** to the corresponding member.

An important condition: the member must actually be an applicable static member and **accessible** from where it is used. Static import **does not bypass** `private`, `protected`, or Java's package/module access rules.

## 2. Two syntactic forms of static import

Java supports two main forms:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.max;
~~~

The **single-static-import declaration** form imports the name of a specific static member from a type. For an overloaded method like `Math.max`, the name `max` is used to find the appropriate static overloads; it does not necessarily represent only a single parameter signature.

The second form:

~~~java
import static java.lang.Math.*;
~~~

is a **static-import-on-demand declaration**. It allows looking up by name the accessible static members of `Math`, as needed. The `*` here **does not mean every class in the `java.lang` package**, nor does it import regular instance methods of `Math`.

| Syntax | Meaning | Example |
| --- | --- | --- |
| `import java.util.Collections;` | Imports the **class name** `Collections` | `Collections.emptyList()` |
| `import static java.util.Collections.emptyList;` | Imports the **static method** name `emptyList` | `emptyList()` |
| `import static java.lang.Math.PI;` | Imports the **static field** name `PI` | `PI * radius * radius` |
| `import static java.lang.Math.*;` | Looks up accessible static members of `Math` on demand | `sqrt(9)`, `max(2,3)` |
| `import java.lang.Math.*;` | **Invalid** for the intent of importing members as a static import | Do not use instead of `import static` |

A Java file can use **both regular imports and static imports**. For example, `import java.util.List;` allows writing the type name `List`, while `import static java.util.List.of;` allows calling the static method `of(...)` by its short name.

## 3. Complete program: selectively importing `Math` members

Create the file **`StaticImportBasicDemo.java`**:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.max;
import static java.lang.Math.pow;
import static java.lang.Math.sqrt;
import static java.lang.System.out;

import java.util.Locale;

public class StaticImportBasicDemo {
    public static void main(String[] args) {
        double radius = 2.0;
        double area = PI * pow(radius, 2);

        out.printf(Locale.ROOT, "area=%.2f%n", area);
        out.println("sqrt=" + sqrt(81));
        out.println("max=" + max(4, 9));

        // The qualified form is still always valid.
        out.println("qualified=" + Math.max(4, 9));
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac -encoding UTF-8 StaticImportBasicDemo.java
java StaticImportBasicDemo
~~~

**Stdout:**

~~~text
area=12.57
sqrt=9.0
max=9
qualified=9
~~~

### What is happening

- `PI` is `Math.PI`, and `pow(radius,2)` is `Math.pow(radius,2)`.
- `sqrt(81)` returns a `double`, which is concatenated into the string `9.0`.
- `max(4,9)` selects the overload that handles two `int` values, returning 9.
- `out` is the `public static final PrintStream out` field of `System`; `out.println(...)` is equivalent to accessing `System.out.println(...)`.
- `Locale.ROOT` ensures formatting the decimal `12.57` does not depend on the default locale of the machine running the program.
- Even with the static import of `max`, the code **can** still write `Math.max(...)`. The import does not remove or forbid the qualified name.

This example uses selective static imports to demonstrate the mechanism. In real applications, many teams will **not static import `System.out`** because `System.out.println` is already very easy to recognize, whereas `out.println` may force the reader to search for the source of `out`. This is precisely the readability trade-off of static import.

## 4. `static import` is not the same as a `static` declaration

Two questions need to be distinguished:

1. **`static` at the member declaration:** determines that the member belongs to the type/class rather than each instance, according to Java semantics.
2. **`import static` at the top of the using file:** determines whether static member names of **another type** can be referred to in short form.

Example:

~~~java
class Calculations {
    static int twice(int number) {
        return Math.multiplyExact(number, 2);
    }

    int instanceValue() {
        return 7;
    }
}
~~~

This is a valid illustrative class. In another file with an appropriate `package`/access permissions, you can static import `twice` if the method is exposed to the call site. You cannot use static import to turn `instanceValue()` into a static method on its own.

For the `Calculations` class example above, `twice` is currently package-private. If the client is in **another package**, you need to expose the method as `public static` and allow access to the enclosing type, instead of expecting static import to grant access.

Static import also **does not instantiate objects** for you. It only imports the name of a member that can be used without a receiver instance. For an instance method, the caller still needs an object, for example `text.trim()`, and cannot rely on `import static java.lang.String.trim;`.

## 5. When does static import improve readability?

A pragmatic rule: **a short name should carry enough meaning on its own in the context where it is used**.

For example, with familiar math functions:

~~~java
double distance = sqrt(pow(dx, 2) + pow(dy, 2));
~~~

This is an illustrative expression, assuming the file has static imports for `sqrt` and `pow`, and `dx`, `dy` are numeric values in scope. If the author is writing a series of mathematical formulas, the names `sqrt`, `pow`, `sin`, and `cos` can make the expressions more concise and closer to how formulas are read.

However:

~~~java
double distance = Math.sqrt(Math.pow(dx, 2) + Math.pow(dy, 2));
~~~

is also clear, and additionally shows the **source of the function** immediately. For readers new to the codebase, or when the project has multiple utility classes with their own `sqrt`/`pow`, the form with `Math.` may be easier to look up.

Static import is appropriate when:

- There are many calls to **a small set of static members** and the member names are familiar.
- The context makes the origin of the name **clear** without needing to jump to the top of the file.
- Repeating the class name obscures the main intent of the expression.
- Team conventions have clearly specified which static imports are allowed and preferred.

You should not evaluate "more concise" solely by character count. **Concise yet ambiguous** can cost more debugging time than writing `Math.max` or `Collections.emptyList` in full.

## 6. Static import in collection and stream processing code

The standard library has many static utility methods suitable for selective importing. Create the file **`CollectionStaticImportDemo.java`**:

~~~java
import static java.util.Comparator.comparingInt;
import static java.util.Collections.reverseOrder;
import static java.util.stream.Collectors.joining;

import java.util.List;

public class CollectionStaticImportDemo {
    public static void main(String[] args) {
        List<String> words = List.of("Java", "Go", "Kotlin");

        String byLength = words.stream()
                .sorted(comparingInt(String::length))
                .collect(joining(", "));

        String descending = words.stream()
                .sorted(reverseOrder())
                .collect(joining(", "));

        System.out.println("length=" + byLength);
        System.out.println("reverse=" + descending);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CollectionStaticImportDemo.java
java CollectionStaticImportDemo
~~~

**Stdout:**

~~~text
length=Go, Java, Kotlin
reverse=Kotlin, Java, Go
~~~

Explanation:

- `comparingInt(String::length)` returns a `Comparator<String>` based on length. Strings of length 2, 4, and 6 are sorted in order.
- `joining(", ")` is the returned collector to join the strings with a comma and a space.
- `reverseOrder()` from `Collections` returns a comparator according to the **reversed natural order** of `String`, so in this dataset it is `Kotlin, Java, Go`.

The names `comparingInt` and `joining` have fairly clear meanings within a stream operation chain. However, if a file only has **a single call**, writing `Comparator.comparingInt` or `Collectors.joining` is usually short enough.

**Note:** `Collections.reverseOrder()` creates a comparator; it does not reverse the `words` list in place. In the example, sorting runs on the stream and produces the resulting string. If you use `Collections.reverse(list)`, the behavior is different: it modifies the order of a mutable list in place.

## 7. Static import on constants and enum constants

Static import can bring **static constants** into the name scope:

~~~java
import static java.time.DayOfWeek.MONDAY;
import static java.time.DayOfWeek.FRIDAY;
~~~

With these import lines at the top of the file, the usage snippet:

~~~java
java.time.DayOfWeek first = MONDAY;
boolean isFriday = first == FRIDAY;
~~~

has a clear meaning when the context is about **days of the week**. `MONDAY` and `FRIDAY` are enum constants belonging to `DayOfWeek`.

Standalone runnable example **`EnumStaticImportDemo.java`**:

~~~java
import static java.time.DayOfWeek.FRIDAY;
import static java.time.DayOfWeek.MONDAY;

import java.time.DayOfWeek;

public class EnumStaticImportDemo {
    public static void main(String[] args) {
        DayOfWeek start = MONDAY;
        DayOfWeek end = FRIDAY;

        System.out.println("start=" + start);
        System.out.println("end=" + end);
        System.out.println("same=" + (start == end));
        System.out.println("end number=" + end.getValue());
    }
}
~~~

~~~bash
javac EnumStaticImportDemo.java
java EnumStaticImportDemo
~~~

Stdout:

~~~text
start=MONDAY
end=FRIDAY
same=false
end number=5
~~~

Enum constants are unique objects per constant in an enum, so `==` is an appropriate identity comparison for the same enum type.

### Limitations when importing too many constants

If you write:

~~~java
import static java.time.DayOfWeek.*;
~~~

then names like `MONDAY`, `TUESDAY`, and `SUNDAY` are brought into lookup scope. For a file that only handles calendars, this can be reasonable; in a multi-purpose file, short names may lack context. Writing `DayOfWeek.MONDAY` sometimes avoids having to guess which enum `MONDAY` belongs to.

An independent point: in a `switch` on an enum in Java 17, case labels use the **enum constant name without a preceding type name** according to enum switch rules; that is **not** a benefit created by static import. Do not add static imports just to justify the `case MONDAY:` syntax.

## 8. Static importing a nested type

Not only fields and methods, static import can also import the name of an **accessible static member type**, for example the `Map.Entry` type:

~~~java
import static java.util.Map.Entry;
~~~

`Entry` is a member interface of `Map`, and a member type in an interface is implicitly declared `public static`. After importing, you can refer to `Entry` without writing `Map.Entry` in appropriate places where the type is used.

Create the file **`StaticNestedTypeImportDemo.java`**:

~~~java
import static java.util.Map.Entry;

import java.util.Map;

public class StaticNestedTypeImportDemo {
    public static void main(String[] args) {
        Entry<String, Integer> entry = Map.entry("An", 7);

        System.out.println("key=" + entry.getKey());
        System.out.println("value=" + entry.getValue());
    }
}
~~~

Run:

~~~bash
javac StaticNestedTypeImportDemo.java
java StaticNestedTypeImportDemo
~~~

Stdout:

~~~text
key=An
value=7
~~~

A more common and possibly more recognizable way is to import the type using:

~~~java
import java.util.Map.Entry;
~~~

Both can make the name `Entry` usable according to the rules of each import form. For **nested member types**, prefer whichever approach expresses semantics clearly and consistently within the project. Static importing a nested type is a valid feature, though not always necessary to use.

Do not confuse a **static nested class** with a **top-level class**: `import static some.package.*;` is not used to import all classes of a package. The `*` in a static import operates on **static members of a specific type**.

## 9. Using static import with a project-defined utility class

To static import a member of a **class you wrote** from another package, the class and the member need appropriate access permissions. We will create the directory structure:

~~~text
src/
  com/
    example/
      shared/
        Numbers.java
      app/
        PackageStaticImportDemo.java
~~~

First file: **`src/com/example/shared/Numbers.java`**

~~~java
package com.example.shared;

public final class Numbers {
    public static final int LIMIT = 10;

    private Numbers() {
    }

    public static int capped(int value) {
        return Math.min(LIMIT, Math.max(0, value));
    }
}
~~~

Second file: **`src/com/example/app/PackageStaticImportDemo.java`**

~~~java
package com.example.app;

import static com.example.shared.Numbers.LIMIT;
import static com.example.shared.Numbers.capped;

public class PackageStaticImportDemo {
    public static void main(String[] args) {
        System.out.println("limit=" + LIMIT);
        System.out.println("low=" + capped(-3));
        System.out.println("high=" + capped(18));
        System.out.println("qualified="
                + com.example.shared.Numbers.capped(4));
    }
}
~~~

From the directory **containing `src`**, run:

~~~bash
javac -encoding UTF-8 -d out src/com/example/shared/Numbers.java src/com/example/app/PackageStaticImportDemo.java
java -cp out com.example.app.PackageStaticImportDemo
~~~

**Stdout:**

~~~text
limit=10
low=0
high=10
qualified=4
~~~

Explanation:

- `Numbers` is a `public final class` belonging to the `com.example.shared` package.
- `LIMIT` and `capped` are `public static` members, so the file in `com.example.app` can import and use them.
- `private Numbers()` prevents creating a `Numbers` instance from outside; we do not need an instance because all utilities are static.
- `capped` keeps the value within the range `0..LIMIT` using `Math.min` and `Math.max`.
- Writing the full name `com.example.shared.Numbers.capped(4)` remains valid even with the static import.
- When there is a `package` declaration, the `java` command runs the **package-qualified class name**, not just the file name.

**Note on the unnamed package:** you should not rely on static importing a class declared in the default (unnamed) package, because an import requires an appropriate type name and Java does not support importing types from the unnamed package in the way used for named packages. Multi-file projects should declare explicit packages.

## 10. Static import does not bypass access scope

Consider the class:

~~~java
package com.example.shared;

public final class SecretNumbers {
    private static final int INTERNAL = 7;
    static final int PACKAGE_ONLY = 8;
    public static final int PUBLIC_VALUE = 9;

    private SecretNumbers() {
    }
}
~~~

This is an illustrative class that can be saved separately as `SecretNumbers.java`, without `main`. A file in **another** package can static import `PUBLIC_VALUE`, however:

~~~java
// The following lines, if used as imports in another package,
// will not grant access to non-public members.
// import static com.example.shared.SecretNumbers.INTERNAL;
// import static com.example.shared.SecretNumbers.PACKAGE_ONLY;
~~~

The two commented-out lines are **intentionally invalid examples**, because `INTERNAL` is `private` and `PACKAGE_ONLY` has package-private access level. Static import does not make those members public.

Even if you use `import static com.example.shared.SecretNumbers.*;`, inaccessible private or package-private members still **do not become usable** from another package.

If a helper is meant to be an internal implementation detail, keep it private/package-private according to the project architecture. Do not widen access just so a static import can compile, unless the API genuinely needs to expose that member.

## 11. First risk: short names lose their origin

Consider a `normalize` function in a code snippet:

~~~java
String result = normalize(input);
~~~

This is an illustrative line inside a method that has `input` of an appropriate type. The reader does not yet know:

- Is `normalize` a method of the current class or an **imported static method**?
- If it is a static import, does it belong to `TextUtils`, `PathUtils`, or another utility type?
- Does it only compute a new result or does it also modify other state?
- What normalization rules does it follow, and can it throw an exception?

If you write:

~~~java
String result = TextNormalizer.normalize(input);
~~~

then the origin is disclosed right at the point of use. For uncommon business operations or operations with side effects, the type name makes the code much easier to read than just `normalize(input)`.

Of course, if the project has **a very standard name** and everyone knows how it is used in that module, static import can still be clear. The criterion is **understandability at the call site**, not just the number of import lines.

### `System.out` is an example of this trade-off

Writing `out.println(...)` is shorter than `System.out.println(...)`, but `out` is a very generic name; a class might also have a variable named `out` with a different meaning. Therefore, static importing `System.out` to save a few characters usually **does not bring clear benefits** for production code.

## 12. Second risk: two sources with members of the same name

For example, `Integer` and `Long` both expose the constant `MAX_VALUE`. If you use static-import-on-demand from both:

~~~java
import static java.lang.Integer.*;
import static java.lang.Long.*;
~~~

and then write:

~~~java
// System.out.println(MAX_VALUE); // Error: the name MAX_VALUE is ambiguous.
~~~

then the compiler does not have a single unique choice between `Integer.MAX_VALUE` and `Long.MAX_VALUE` in this context.

The following illustration is a **complete program** **`StaticImportAmbiguityDemo.java`** showing how to resolve it using qualification:

~~~java
import static java.lang.Integer.*;
import static java.lang.Long.*;

public class StaticImportAmbiguityDemo {
    public static void main(String[] args) {
        // System.out.println(MAX_VALUE); // Ambiguous if uncommented.

        System.out.println("int max=" + Integer.MAX_VALUE);
        System.out.println("long max=" + Long.MAX_VALUE);
    }
}
~~~

Compile/run:

~~~bash
javac StaticImportAmbiguityDemo.java
java StaticImportAmbiguityDemo
~~~

**Stdout:**

~~~text
int max=2147483647
long max=9223372036854775807
~~~

The takeaway is not that any static imports containing colliding names cannot be declared in the same file. **A name collision error may only appear when using a simple name** in a context that cannot be resolved. Using the type-qualified name is a clear and reliable resolution.

With overloaded methods from multiple sources, method selection rules can be more complex: the compiler may find an appropriate overload or report ambiguity depending on the parameter list, declaration source, and scope. Do not assume "a later import overrides an earlier import": **Java does not choose a static import based on the order of import lines**.

## 13. Some name resolution rules to remember

Resolving a simple name in Java follows the JLS rules on scope, declarations, and imports. At this level of study, keep in mind:

1. **A declaration closer to the point of use can shadow an imported name.** If a local variable has the name `PI`, writing `PI` in that scope can read the local variable instead of `Math.PI`.
2. **Members of the current class can take precedence over names imported via static import** in cases governed by scope and method resolution rules. Do not assume that an imported `max` is definitely `Math.max` if the current class also has a `max`.
3. **Single-member imports and on-demand imports have different resolution rules.** You should not expect the position of an import line to determine the outcome.
4. **Two static-import-on-demand declarations with members of the same name** can make that name ambiguous when used.
5. **Type-qualified names** such as `Math.PI` or `Long.MAX_VALUE` usually indicate clearly which member is intended and are easy to review.
6. **Imports do not bypass access permissions** or change method signatures, overloads, or the static type of expressions.

Example of a local variable shadowing the name of a statically imported constant:

~~~java
import static java.lang.Math.PI;

public class ShadowStaticImportDemo {
    public static void main(String[] args) {
        double PI = 3.0;
        System.out.println("local=" + PI);
        System.out.println("math=" + Math.PI);
    }
}
~~~

Commands:

~~~bash
javac ShadowStaticImportDemo.java
java ShadowStaticImportDemo
~~~

Stdout:

~~~text
local=3.0
math=3.141592653589793
~~~

This program demonstrates that **an import does not force every use of `PI` to point to `Math.PI`**. The same simple name can express a different meaning due to declaration scope. Therefore, type-qualified names are often appropriate when misunderstanding needs to be eliminated.

## 14. On-demand import `*` and the cost to code readability

The form:

~~~java
import static java.lang.Math.*;
~~~

is shorter than many separate imports when using a series of `Math` functions. It also does not create a runtime operation to "load every function" into an object; imports primarily serve **name resolution at compile time**.

However, on-demand import has trade-offs:

- Readers do not immediately see in the import section **which specific names are used**.
- When a new static member appears in the API or another import is added, a **name collision** can arise at the call site.
- Review or lookup tools may need extra searching to know which class a short call belongs to.
- For short constants, `*` can bring many common names into lookup scope, increasing the risk of shadowing or ambiguity.

**You should not claim that on-demand import causes the JVM to load every static member into RAM when the program runs.** It is not a loop or a method call; class loading and initialization follow their own rules and do not simply happen just because of an import declaration.

In a large codebase, **single static imports** are usually a safer default. On-demand can be reasonable when there are genuinely many clear static names from **a specific type** and the team is consistent in its conventions.

## 15. Static import and Java `enum` / testing

In test code, there are many assertion calls such as `assertEquals`, `assertTrue`, and `assertThrows`. Static import often helps test expressions focus on **what is being tested**, for example when the testing tool provides these methods as `static`.

Illustrating the **API idea of a testing library**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
~~~

This is **not an example that compiles with JDK 17 alone**: types in the `org.junit.jupiter.api` package belong to the JUnit Jupiter library, which requires adding the corresponding dependency and test configuration. The purpose is to illustrate a real-world scenario where static import is commonly used.

When the name `assertEquals` is already very familiar in a test file, writing:

~~~java
assertEquals(5, actual);
assertTrue(isValid);
~~~

is usually easy to understand. Conversely, if a project has multiple assertion libraries defining functions with the same name, wholesale importing can make overloads or error messages hard to analyze.

Outside of tests, enum constants like `MONDAY` and `FRIDAY` can be statically imported when an algorithm genuinely revolves around **a specific enum**. There is no need to apply the same approach to every kind of constant in the project.

## 16. Avoid static importing ambiguous business helpers

If a project has classes:

~~~text
PriceRules.calculate(...)
TaxRules.calculate(...)
ShippingRules.calculate(...)
~~~

then statically importing `calculate` from multiple sources can make a call like `calculate(order)` hard to understand: is it calculating the price, tax, or shipping fee?

Even if the compiler can select a single overload, the reader still has to trace back to the imports to know **which business rule was invoked**. The type name in the form `TaxRules.calculate(order)` is valuable information, not merely redundant characters.

A suggestion:

| Situation | Usually best to write |
| --- | --- |
| Long math formulas using a few familiar `Math` functions | Can selectively static import `sqrt`, `pow` |
| Tests with a consistent assertion API | Static import the assertions needed |
| An enum constant appearing many times in a specialized function | Can static import the enum constant |
| Domain helpers with generic names `calculate`, `validate`, `parse` | Prefer `TypeName.method(...)` |
| Constants `MAX_VALUE`, `DEFAULT`, `LIMIT` from multiple places | Prefer `TypeName.CONSTANT` |
| A single utility call in the entire file | Usually write the full type name |
| Multiple libraries with methods of the same name | Keep the qualifier to avoid ambiguous/hard-to-track static imports |

This is especially important in modules with security, monetary, or state logic: **clearly seeing the source of a decision** is usually worth more than a few saved characters.

## 17. Code review: deciding whether to use or remove static import

When reviewing a static import, ask practical questions:

1. **Is the short name clear right at the point of use?** `PI` in a math formula may be clear; `process` is not.
2. **Is the source of the member significant for business logic?** If so, keep `TypeName.`.
3. **How many times is it used?** A single use is usually not worth losing context.
4. **Is there a risk of name collision with another local/member/import?** Check both fields and methods.
5. **Are the overloads easy to understand?** Multiple sources importing short-named methods can make resolution results hard to predict.
6. **Can it be replaced by an ordinary import of the class?** `Math.max` is sometimes a more balanced option.
7. **Is the import unnecessarily widening the API?** Do not turn a `private` helper into public just so you can static import it.
8. **Does the formatter/IDE convert explicit imports to wildcard imports?** If so, style settings need to be consistent.
9. **Can someone new to the project trace the declaration easily?** If it is difficult, rename/keep the qualifier.
10. **Is there an official team style rule?** It should be applied consistently across the entire codebase.

A readable static import is one where, when removing the class name, **the meaning of the expression remains obvious**. If you constantly have to look at the top of the file to decode it, it can do more harm than good.

## 18. Common compilation errors

| Error | Cause | How to fix |
| --- | --- | --- |
| Writing `import Math.PI;` | Incorrect syntax for importing a static member | `import static java.lang.Math.PI;` |
| Writing `import static java.lang.Math;` | Missing member name after the type name | Choose `Math.PI`, `Math.max`, or `Math.*` |
| Writing a static import inside a class/method body | Imports must be in the import section of the compilation unit | Move to the top of the file, after `package` |
| Importing an instance method like `String.trim` | The method is not static | Call through an object, e.g., `text.trim()` |
| Static importing a private member from another package | Import does not grant new permissions | Use a public API or change the design |
| On-demand importing two classes with `MAX_VALUE` and calling `MAX_VALUE` | The used name becomes ambiguous | `Integer.MAX_VALUE` / `Long.MAX_VALUE` |
| Writing `import static my.package.*;` intending to import all package classes | Static import requires a **type containing members**, not a package wildcard | Use a regular class import or import a specific static member |
| Static importing a class from the unnamed package | Cannot use default-package-based type import as intended | Put the source in a named package |
| Expecting `import static` to allow calling methods of any object | Does not replace the object receiver | Use `instance.method()` |
| Assuming an imported method overrides a method of the same name in the class | Name/overload resolution follows the JLS, not import order | Use the full type name to clarify |
| Using `*` on every utility class | Increases name collision risk and makes tracing sources hard | Selectively static import or remove static import |

Errors **commented out as examples** are not treated as code to be compiled. All standalone programs in this lesson have kept error-causing lines inactive or used full names so they can compile.

## 19. Does static import affect performance?

**An import declaration itself is not equivalent to calling a method at runtime.** It helps the compiler resolve names. The two expressions:

~~~java
Math.max(3, 5)
~~~

and:

~~~java
max(3, 5)
~~~

(when `import static java.lang.Math.max;` is present) resolve to the appropriate member according to overload rules. You should not try to optimize performance by changing `Math.max` to `max`; the difference is in **how the source code is written**.

The factors that determine actual runtime behavior include the selected method, arguments, types, JIT, side effects, and data structures, not whether the name is written with a qualifier or a static import.

Even so, **name conflicts in source code** can prevent an expression from compiling or cause a different method to be selected when the declaration environment changes. Thus, static import has a real impact on **understandability and maintainability**, even though it is not a runtime speedup mechanism.

## 20. Self-check exercises

**Exercise 1 — Syntax.** Write static imports to use `PI` and `sqrt` from `java.lang.Math` without needing to write `Math.` at the call site.

**Exercise 2 — Distinction.** How do `import java.util.Collections;` and `import static java.util.Collections.emptyList;` differ regarding which names can be written in short form?

**Exercise 3 — The `*` wildcard.** Does `import static java.lang.Math.*;` import all classes in the `java.lang` package? Does it cause the JVM to immediately run all static methods of `Math`?

**Exercise 4 — Access.** A type `public Utils` has a method `private static int secret()`. Can another class `import static Utils.secret;` to bypass `private`?

**Exercise 5 — Ambiguity.** If you on-demand import `Integer.*` and `Long.*`, why can `MAX_VALUE` be ambiguous? Rewrite the print statement so it clearly specifies the `int` limit.

**Exercise 6 — Shadowing.** Inside a method that has `double PI=3;`, even with `Math.PI` statically imported, what value does `System.out.println(PI)` print? What must you write to get the value from `Math`?

**Exercise 7 — Static and instance.** Why is static importing `Collections.sort` a different thing from calling `list.sort(comparator)`? Which one is a static method and which one needs a receiver object?

**Exercise 8 — Enum.** If a file works with `DayOfWeek` very frequently, when might importing `MONDAY` and `FRIDAY` be reasonable? When is `DayOfWeek.MONDAY` clearer?

**Exercise 9 — Nested type.** Write a static import to use the `Entry` name of `java.util.Map`. Without using static import, what regular import could be used?

**Exercise 10 — Design.** A project has three static methods with the same name `calculate` in the classes `TaxRules`, `PriceRules`, and `ShippingRules`. Should all three be imported into an order-processing file? Why?

**Exercise 11 — Package.** In the `Numbers` example, what access permission conditions are needed for a file in another package to call `capped` via static import? What name must the run command specify for a class with a package?

**Exercise 12 — Review.** With a single call `Math.max(2,5)` in a 300-line file, is static importing `max` guaranteed to make the code easier to read? What criteria do you use to decide?

### Reference answers

1. `import static java.lang.Math.PI;` and `import static java.lang.Math.sqrt;`.
2. Regular import provides the type name `Collections`; static import provides the method name `emptyList` used at appropriate call sites.
3. No. It only participates in looking up accessible static members of the `Math` type; it does not automatically execute all methods.
4. No. Private access rules do not change with static import.
5. Both `Integer` and `Long` have `MAX_VALUE`; write `Integer.MAX_VALUE` to clearly specify `int`.
6. It prints `3.0` because the local variable shadows the imported name; use `Math.PI` to refer to the static field.
7. `Collections.sort(list)` is a static method call on `Collections`; `list.sort(comparator)` is an instance method on the list object. Static import does not turn an instance method into a static one.
8. When the context clearly involves one enum and the names appear frequently; use a qualifier if it is easy to confuse or you want to make the type explicit.
9. `import static java.util.Map.Entry;`; regular import is `import java.util.Map.Entry;`.
10. Usually no: `TaxRules.calculate(...)` makes the business source clearer than `calculate(...)`.
11. The `Numbers` type and the `capped` method must be accessible from the client, for example `public`; run `com.example.app.PackageStaticImportDemo` with the classpath containing the compiled files.
12. Not necessarily; consider frequency, name clarity, collision risk, and codebase conventions. A single call is usually clear enough with `Math.max`.

## 21. Reference documentation

- [Java Language Specification 17, §7.5.3 — Single Static Import Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.5.3): static import by specific member name.
- [Java Language Specification 17, §7.5.4 — Static-Import-on-Demand Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.5.4): static import with `*`.
- [Java Language Specification 17, §6.5 — Determining the Meaning of a Name](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5): resolving names, members, and scope.
- [Java Language Specification 17, §6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): accessibility rules still apply when importing.
- [Java SE 17 API — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `PI`, `max`, `pow`, `sqrt`.
- [Java SE 17 API — Introspector is unrelated; see Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): `comparingInt` and comparison utility methods.
- [Java SE 17 API — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): `joining`.

**Remember:** `import static` helps call **an accessible static member of a type** by a shorter name, but does not change access permissions, does not turn an instance method into a static one, and does not speed up the program. Prefer **selective importing** when the short name remains clear (formulas, assertions, certain constants/utilities); keep `TypeName.member` when the origin matters, the name is too generic, or there is a risk of collision. Good static import usage is a choice that serves **code readers**, not a goal of shortening every line.
