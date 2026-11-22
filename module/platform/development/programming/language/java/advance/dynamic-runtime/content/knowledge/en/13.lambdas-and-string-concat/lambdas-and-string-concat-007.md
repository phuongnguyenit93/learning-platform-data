# 13.7 StringConcatFactory, recipes, and constant arguments in dynamic string concatenation

In modern Java, a string concatenation expression such as `"User=" + name + "; n=" + count` can be compiled by the compiler into an **`invokedynamic` instruction** instead of an explicit `new StringBuilder().append(...).toString()` sequence of instructions. The bootstrap commonly used for these call sites is **`java.lang.invoke.StringConcatFactory`**. It constructs a `CallSite` and `MethodHandle` representing the string concatenation operation based on the **signature of the dynamic arguments**, a **recipe** describing the concatenation order, and **constant arguments** from the bootstrap when needed.

Key points:

- `\u0001` (control character **U+0001**) in the recipe is **a dynamic argument**: the value is supplied **on each invocation**.
- `\u0002` (control character **U+0002**) in the recipe is **a constant argument**: the value is supplied **at linkage/bootstrap time**.
- Any other character in the recipe is **literal text** that will appear in place during concatenation.
- **The number of U+0001 occurrences must equal the number of parameters in `concatType`**; **the number of U+0002 occurrences must equal the number of elements in `constants`**. A mismatch → `StringConcatException` when calling the factory.
- `CallSite.type()` and `CallSite.getTarget().type()` must match the exact `MethodType` of the concatenation. Bootstrap constants **are not in the runtime parameter list** of the handle.

This lesson moves from the linkage diagram to recipe syntax, a runnable Java 17+ demo, type/placeholder check errors, how to use `javap` to inspect the actual recipe in a class file, and optimization notes.

## 1. Two distinct phases: linkage and invocation

~~~text
Java code:     return "User=" + name + "; n=" + count;
                                 |
                                 v
javac (usually uses invokedynamic with Java 9+)
                                 |
                                 v
Bytecode: invokedynamic ... (String,int)String
          BootstrapMethods -> StringConcatFactory.makeConcatWithConstants
          example recipe: "User=\\u0001; n=\\u0001"
                                 |
                    FIRST SITE LINKAGE
                                 v
JVM passes Lookup, name, MethodType, recipe, and static constants
                                 |
             StringConcatFactory creates CallSite + target MethodHandle
                                 |
                    JVM verifies target type
                                 |
                        RUNTIME INVOCATION
                                 v
       target("Lan", 7) -----> "User=Lan; n=7"
       target("An",  3) -----> "User=An; n=3"
~~~

**Linkage** is the phase where the factory is called with `MethodType`, recipe, and constants to create a specialized concatenation. **Invocation** is the phase where the handle receives the actual dynamic values and produces the string. The factory does not re-run every time the same linked call site is invoked to build the concatenation from scratch; it creates a reusable concatenation capability.

Whether the compiler uses `invokedynamic` or not is a bytecode generation strategy detail, not a mandatory Java rule for every expression. With the `javac --release 17` example below, it is possible to **actually observe** an `invokedynamic` and recipe using `javap`. The expression result must still conform to the string concatenation semantics of the Java Language Specification (JLS).

## 2. The two main APIs of StringConcatFactory

~~~java
public static CallSite makeConcat(
        MethodHandles.Lookup lookup,
        String name,
        MethodType concatType) throws StringConcatException;

public static CallSite makeConcatWithConstants(
        MethodHandles.Lookup lookup,
        String name,
        MethodType concatType,
        String recipe,
        Object... constants) throws StringConcatException;
~~~

These are **API signatures** extracted from Java SE 17; they are not method definitions to copy into an application.

| Parameter | Meaning |
| --- | --- |
| `lookup` | `Lookup` representing the caller context. According to the Javadoc, the factory requires **full privilege access**; the JVM provides an appropriate lookup when used as an `invokedynamic` bootstrap. |
| `name` | Symbolic name of the call site. **The factory does not use this name to decide how to concatenate**; when actually linking `invokedynamic`, the JVM takes it from the instruction's `NameAndType`. |
| `concatType` | Signature of the **target/call site**, including the types and number of **dynamic arguments**, along with the return type. |
| `recipe` | Only present in `makeConcatWithConstants`; a string describing literals and U+0001/U+0002 placeholders. |
| `constants` | Static bootstrap values corresponding to each U+0002; they do not become parameters of the `MethodHandle` at invocation. |

### `makeConcat`: all inputs are dynamic arguments

`makeConcat(lookup, name, concatType)` does not take a recipe or bootstrap constants. When the target is invoked, it concatenates all arguments from left to right according to String conversion rules. Edge cases noted by the Javadoc:

- No inputs: the result is the empty string `""`.
- One input: the result is the string representation of the input according to JLS string conversion.
- Two or more inputs: converts each input to a string and concatenates them in sequence, without automatically inserting separators.

For example, `concatType=(String,int)String`, the target receives `("Lan",7)` and returns `"Lan7"`. If you want to add `"User="`, `"; n="`, or fixed spaces, you must pass them as **dynamic args** or use `makeConcatWithConstants`.

### `makeConcatWithConstants`: the recipe directs the concatenation

`makeConcatWithConstants` adds a recipe, allowing static parts to be represented **in the recipe** or via **bootstrap constants**. The target still only receives the **dynamic args** counted by U+0001. For example:

~~~text
concatType = (String,int)String
recipe     = "ID=" + U+0001 + "; label=" + U+0002 + "; n=" + U+0001
constants  = ["STATIC"]

runtime    = ("X", 7)
result     = "ID=X; label=STATIC; n=7"
~~~

Number of U+0001: **2**, equal to parameter count `2`. Number of U+0002: **1**, equal to length `constants=1`. Even though the recipe has one static constant, `target.type()` is still `(String,int)String`, not `(String,String,int)String`.

## 3. A recipe is a string with two special markers, not an expression parser

`StringConcatFactory` scans the recipe from **left to right**; each character carries one of three meanings:

| Character in recipe | Unicode value | Content source | When supplied? |
| --- | --- | --- | --- |
| `\u0001` | U+0001 (SOH) | Next **dynamic argument**, in parameter order in `concatType` | **Every time the target is invoked** |
| `\u0002` | U+0002 (STX) | Next **static constant**, in order in `constants` | **At bootstrap/linkage time** |
| Other characters | E.g., `U`, `s`, `e`, `r`, `=`, space, `:` | The literal character itself | Embedded in the recipe |

The recipe has **no** concept of evaluating expressions, variable names like `name`, or escaping markers with a backslash. Whenever U+0001/U+0002 appear, they are **always** interpreted as placeholders. The notation `\u0001` in documentation is a way to *display the control code*; in an actual `String recipe`, that position must contain the Java `char` with value 1. Similarly for U+0002/value 2.

To keep Java source transparent and avoid accidentally putting invisible control characters into an editor, you can write:

~~~java
char ARG = (char) 1;     // U+0001: dynamic argument
char CONST = (char) 2;   // U+0002: bootstrap constant

String recipe = "ID=" + ARG + "; label=" + CONST + "; n=" + ARG;
~~~

This is an **illustrative snippet** inside a method, not a standalone file. The Java compiler produces an actual string containing U+0001/U+0002, and the factory will parse it at linkage time. In source code you can also use Java literals `"\u0001"` / `"\u0002"`, but using the `(char)1` cast makes reading the code and avoiding invisible characters easier.

### 3.1. How the recipe is read character by character

~~~text
Recipe: "ID="  \u0001  "; label="  \u0002  "; n="  \u0001
             |                     |                   |
             v                     v                   v
         arg #0 "X"          constant #0        arg #1 7
                                "STATIC"
                         |
                         v
Result: "ID=X; label=STATIC; n=7"
~~~

The first and second dynamic arguments are **consumed in order**, not by name. Two U+0001 placeholders look identical symbolically, but they represent **two different argument positions**. If you want to repeat the same input in the result, you must design the signature/recipe and argument supply accordingly; the factory has no syntax like `{0}` to automatically repeat parameter 0. It is not `MessageFormat`.

### 3.2. Literal text, static constant, and dynamic argument are three different ways

For example, suppose you want to concatenate `"prefix:"` with the value `name`:

1. **Literal in the recipe**: `"prefix:" + ARG`. `prefix:` appears directly in the recipe.
2. **Static constant**: `CONST + ARG`, with `constants[0]="prefix:"`. The prefix is passed at linkage time, not in the target parameter list.
3. **Dynamic argument**: `ARG + ARG` and `concatType=(String,String)String`, invoked with `("prefix:", name)` each time.

The three forms can produce the same output string, but they have different **shapes and costs**: dynamic arguments are passed on each call; static constants are bootstrap data; recipe literals are direct character components.

**Do not use U+0001 or U+0002 as a bare literal character in a recipe.** These two characters are reserved markers. If you actually want to concatenate a U+0001/U+0002 control character as data, put it into a **constant string** and insert it via U+0002 (or pass it via a dynamic argument). For example, the program below creates a constant `"[" + ARG + "/" + CONST + "]"` and puts that entire string into a static constant, so the markers are **inside the constant value**, not re-parsed as a recipe.

## 4. Relationship between MethodType, CallSite, and marker counts

Example:

~~~java
MethodType signature = MethodType.methodType(
        String.class, String.class, int.class);
// (String,int)String

CallSite site = StringConcatFactory.makeConcatWithConstants(
        MethodHandles.lookup(),
        "concat",
        signature,
        "ID=" + (char) 1 + "; kind=" + (char) 2 + "; count=" + (char) 1,
        "STATIC");
~~~

These are illustrative statements inside a method that handles `StringConcatException`. Upon success:

~~~text
site.type()                 = (String,int)String
site.getTarget().type()     = (String,int)String
site.dynamicInvoker().type()= (String,int)String

dynamic marker count        = 2
bootstrap constant count    = 1
invokeExact arguments       = (String,int)
~~~

The target's `MethodType` **does not contain** `String recipe` or the bootstrap constants. The recipe and constants serve **linkage**, and are not on the operand stack of a target invocation.

`CallSite` invariant: once a site is validly created, `site.getTarget().type().equals(site.type())`. When used with an actual `invokedynamic`, the JVM also verifies that the CallSite type matches the descriptor recorded in the class file. `StringConcatFactory` creates a target matching `concatType` if the factory succeeds; you should not assume the target returns a different type and expect the JVM to coerce it automatically.

### The return type does not have to be strictly `String.class`

The Javadoc states the condition **“return type in concatType is assignable from String”**. Because `String` implements `CharSequence` and extends `Object`, return types such as `String.class`, `CharSequence.class`, or `Object.class` are valid if the other conditions are met. This is an **assignability direction constraint**, not “only accepts String.class”.

A verified example:

~~~java
MethodType wideType = MethodType.methodType(Object.class, String.class);
CallSite site = StringConcatFactory.makeConcat(
        MethodHandles.lookup(), "concat", wideType);
Object actual = site.dynamicInvoker().invokeExact("hi");
// actual.equals("hi") == true
// site.type() == (String)Object
~~~

This example is a statement snippet inside a method with `throws Throwable`. Even though the **descriptor** says it returns `Object`, the object actually produced is a `String`; the method handle has the exact type `(String)Object`. Conversely, `void.class` is **not** a supertype of String, so `(String)void` is invalid for describing a string concatenation target.

### Parameter limit: **200 parameter slots**, not 200 characters

According to the Javadoc, the number of **parameter slots** in `concatType` must not exceed **200**. Types `long` and `double` occupy **two JVM slots**; parameters like `int`, `float`, or references normally occupy one slot. Therefore, “200 slots” does **not** mean 200 `long` parameters are always accepted, and it has nothing to do with the length of the resulting string.

The JVM also has a class file structural limit on the number of slots in a method invocation (a general limit of 255), so StringConcatFactory reserves room for certain implementation strategies and sets the threshold at 200. For extremely large concatenations, split them into smaller concatenations in a structure supported by the compiler/JIT; do not try to bypass the threshold by inserting arbitrary placeholders.

## 5. Recipe constraints to check before creating a CallSite

| Condition | How to check | Valid example | Invalid example |
| --- | --- | --- | --- |
| Dynamic parameters | `count(U+0001) == concatType.parameterCount()` | Type `(String,int)String` with 2 `ARG` markers | Type has 2 parameters but recipe has 1 `ARG` |
| Bootstrap constants | `count(U+0002) == constants.length` | Recipe has 1 `CONST` and 1 constant | Recipe has 0 `CONST` but passes `"extra"` |
| Return type | `concatType.returnType().isAssignableFrom(String.class)` | `String`, `Object` | `void`, `int` |
| Method size | `concatType.parameterSlotCount <= 200` (per JVM descriptor semantics) | 2 parameters `String,int` use 2 slots | 201 `int` parameters use 201 slots |
| Lookup privileges | `lookup` has full privilege per factory contract | `MethodHandles.lookup()` in normal application code | `publicLookup()` does not meet the full privilege requirement |
| Null inputs | Appropriate `lookup`/`name`/`concatType`/`recipe`/`constants` non-null; static constants must not be null | `constants={"STATIC"}` | Null static constant via `CONST` marker |

When calling `StringConcatFactory.makeConcatWithConstants(...)` **directly** from Java code, type/count mismatches usually throw **`StringConcatException`**; related null inputs can throw **`NullPointerException`**. If the error occurs **during the bootstrap of an actual `invokedynamic`**, the JVM may wrap non-`Error` linkage failures into **`BootstrapMethodError`**, so direct API errors must be distinguished from errors when linking an instruction.

A factory is allowed to optimize execution without changing the result. You should not depend on a specific `CallSite` subclass returned by the factory unless guaranteed by the API. Use `site.getTarget()`/`site.dynamicInvoker()` and compare `site.type()` with `concatType`.

## 6. Dynamic `null`, static `null`, and string conversion

### 6.1. Dynamic argument `null` is valid

According to the Javadoc, an argument at U+0001 can be `null`. During concatenation, a `null` reference is converted to the literal `"null"` according to JLS String Conversion:

~~~java
MethodType type = MethodType.methodType(
        String.class, String.class, int.class);
CallSite site = StringConcatFactory.makeConcat(
        MethodHandles.lookup(), "concat", type);
String out = (String) site.dynamicInvoker().invokeExact((String) null, 0);
// out.equals("null0") == true
~~~

The illustration uses `(String)null` so the call-site type matches `(String,int)String` exactly; if you write a bare `null` literal without a cast in complex signature-polymorphic situations, the compiler may not infer the exact argument type for `invokeExact`.

### 6.2. Static constant `null` is rejected

With `makeConcatWithConstants`, **a static constant passed into the recipe must not be null** according to the Java SE 17 API. Example:

~~~java
MethodType noArgs = MethodType.methodType(String.class);
String recipe = String.valueOf((char) 2);
StringConcatFactory.makeConcatWithConstants(
        MethodHandles.lookup(), "concat", noArgs, recipe, new Object[] { null });
~~~

This snippet **intentionally triggers a `NullPointerException` at the factory**; it does not mean normal String concatenation forbids null. Distinguish between a **null dynamic argument** (allowed and produces the string `"null"`) and a **null static bootstrap constant** (invalid for this API). Use `new Object[]{null}` in the illustration to pass **one constant element with value null**, rather than passing a null varargs array itself.

### 6.3. Converting an object to String

Dynamic values are converted to strings according to JLS `5.1.11` and the string concatenation operator `15.18.1`:

- Primitive `int=7` → `"7"`, `boolean=true` → `"true"`, etc.
- Reference to `String` → that string's content itself.
- `null` reference → `"null"`.
- Reference to another object → converted to a string according to the object's contract; you should not assume every `toString()` is cheap or free of side effects.

For static constants, the Javadoc states the factory **may** perform String conversion of the constant, including calling `toString()` if needed, **once** at linkage time. Do not rely on `toString()` side effects as application logic: timing and optimization strategies can make those assumptions hard to guarantee. If you need a value computed on each invocation, use a **dynamic argument U+0001**, not a bootstrap constant.

## 7. Complete Java 17+: two factories, recipes, constants, and intentional errors

Create the file **`ConcatRecipeDemo.java`**:

~~~java
import java.lang.invoke.*;
import java.util.Arrays;

public final class ConcatRecipeDemo {
    static final char ARG = (char) 1;
    static final char CONST = (char) 2;

    static String compiled(String name, int n) {
        return "User=" + name + "; n=" + n;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType sig = MethodType.methodType(String.class, String.class, int.class);

        // 1. makeConcat: all are dynamic arguments.
        CallSite simple = StringConcatFactory.makeConcat(lookup, "arbitrary", sig);
        String simpleResult = (String) simple.dynamicInvoker().invokeExact("Lan", 7);
        System.out.println("simple type = " + simple.type());
        System.out.println("simple = " + simpleResult);

        // 2. makeConcatWithConstants: literal text + two dynamic markers.
        String recipe = "User=" + ARG + "; n=" + ARG;
        CallSite withText = StringConcatFactory.makeConcatWithConstants(
                lookup, "unusedName", sig, recipe);
        System.out.println("recipe result = " +
                (String) withText.dynamicInvoker().invokeExact("Lan", 7));

        // 3. A static constant inserted between two dynamic arguments.
        String withConstant = "ID=" + ARG + "; label=" + CONST + "; n=" + ARG;
        CallSite c = StringConcatFactory.makeConcatWithConstants(
                lookup, "concat", sig, withConstant, "STATIC");
        System.out.println("with constants type = " + c.type());
        System.out.println("with constants = " +
                (String) c.dynamicInvoker().invokeExact("X", 7));

        // 4. Need to print actual U+0001/U+0002 characters: pass via static constant.
        MethodType single = MethodType.methodType(String.class, String.class);
        String escapedRecipe = "literal=" + CONST + "; arg=" + ARG;
        CallSite escaped = StringConcatFactory.makeConcatWithConstants(
                lookup, "concat", single, escapedRecipe,
                "[" + ARG + "/" + CONST + "]");
        String literal = (String) escaped.dynamicInvoker().invokeExact("x");
        System.out.println("reserved characters preserved = " +
                literal.equals("literal=[" + ARG + "/" + CONST + "]; arg=x"));

        // 5. No dynamic args; static constants do not become target args.
        MethodType noArgs = MethodType.methodType(String.class);
        CallSite empty = StringConcatFactory.makeConcat(lookup, "concat", noArgs);
        System.out.println("zero-args is empty = " +
                ((String) empty.dynamicInvoker().invokeExact()).isEmpty());
        CallSite constantsOnly = StringConcatFactory.makeConcatWithConstants(
                lookup, "concat", noArgs, "Hello, " + CONST, "world");
        System.out.println("constants only = " +
                (String) constantsOnly.dynamicInvoker().invokeExact());

        // 6. Return type Object is valid because Object is a supertype of String.
        CallSite wide = StringConcatFactory.makeConcat(
                lookup, "concat", MethodType.methodType(Object.class, String.class));
        Object wideResult = wide.dynamicInvoker().invokeExact("hi");
        System.out.println("Object return = " + wide.type());
        System.out.println("Object actual String = " + wideResult.equals("hi"));

        // 7. Dynamic null is valid and converted to the string "null".
        String nullResult = (String) simple.dynamicInvoker().invokeExact((String) null, 0);
        System.out.println("dynamic null = " + nullResult);

        // 8. Wrong count of dynamic markers.
        try {
            StringConcatFactory.makeConcatWithConstants(
                    lookup, "concat", sig, "only " + ARG);
        } catch (StringConcatException ex) {
            System.out.println("dynamic markers mismatch = " +
                    ex.getClass().getSimpleName());
        }

        // 9. Wrong count of constant markers.
        try {
            StringConcatFactory.makeConcatWithConstants(
                    lookup, "concat", sig, recipe, "extra");
        } catch (StringConcatException ex) {
            System.out.println("constant markers mismatch = " +
                    ex.getClass().getSimpleName());
        }

        // 10. Return type void cannot receive a String result.
        try {
            StringConcatFactory.makeConcat(lookup, "concat",
                    MethodType.methodType(void.class, String.class));
        } catch (StringConcatException ex) {
            System.out.println("void result mismatch = " +
                    ex.getClass().getSimpleName());
        }

        // 11. Null static constant.
        try {
            StringConcatFactory.makeConcatWithConstants(
                    lookup, "concat", noArgs, String.valueOf(CONST),
                    new Object[] { null });
        } catch (NullPointerException ex) {
            System.out.println("null static constant = " +
                    ex.getClass().getSimpleName());
        }

        // 12. Exceeding 200 parameter slots.
        try {
            Class<?>[] types = new Class<?>[201];
            Arrays.fill(types, int.class);
            StringConcatFactory.makeConcat(
                    lookup, "concat", MethodType.methodType(String.class, types));
        } catch (StringConcatException ex) {
            System.out.println("201 parameter slots = " +
                    ex.getClass().getSimpleName());
        }

        // 13. Real + concatenation compiled by javac into invokedynamic.
        System.out.println("javac concat = " + compiled("Lan", 7));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ConcatRecipeDemo.java
java ConcatRecipeDemo
~~~

**Exact `stdout` tested on JDK 24, compiled with `--release 17`:**

~~~text
simple type = (String,int)String
simple = Lan7
recipe result = User=Lan; n=7
with constants type = (String,int)String
with constants = ID=X; label=STATIC; n=7
reserved characters preserved = true
zero-args is empty = true
constants only = Hello, world
Object return = (String)Object
Object actual String = true
dynamic null = null0
dynamic markers mismatch = StringConcatException
constant markers mismatch = StringConcatException
void result mismatch = StringConcatException
null static constant = NullPointerException
201 parameter slots = StringConcatException
javac concat = User=Lan; n=7
~~~

The example was compiled and run with JDK 24 in `--release 17` mode. The `--release 17` option restricts the source/API to Java SE 17; this is different from claiming it was run directly on a JVM 17. The result strings, exception class names, and method types above were verified by running the program.

### 7.1. Explaining the first six lines

`makeConcat` receives `("Lan",7)` and therefore returns `"Lan7"`. There is no space or separator because the simple factory has no recipe.

`withText` receives the same two dynamic args but has the recipe `"User=" + ARG + "; n=" + ARG`, so it returns `"User=Lan; n=7"`; the factory inserts literal text without needing to create two new dynamic inputs.

`c` has the same `MethodType=(String,int)String`, but the recipe also has `CONST` and the static constant `"STATIC"`. The text `STATIC` is not a third argument at invocation; the result `ID=X; label=STATIC; n=7` proves it is held in the linkage part.

### 7.2. Why are reserved characters not mistaken for markers?

In `escapedRecipe`, there is only **one** U+0002 to insert a constant string and **one** U+0001 for the dynamic `"x"`. The constant string actually contains the two control characters between `[` and `]`, but **constant values are not parsed as a new recipe**. Checking with `String.equals` avoids printing invisible control characters to the console, so the output is easy to verify as `true`.

### 7.3. Zero dynamic inputs and wide return types

`empty` has target type `()String`, returning `""`. `constantsOnly` still has target type `()String` because the recipe only uses one U+0002 and no U+0001; the output is `Hello, world`. `wide` has target type `(String)Object` and returns an actual object holding `"hi"`; the example proves that the return type **can be a supertype of String**.

### 7.4. Errors caught at the right stage

The `try/catch` blocks simulate errors **when calling the factory directly**, not errors linking an actual `invokedynamic` instruction:

- Recipe contains 1 dynamic marker, type has 2 parameters → `StringConcatException`.
- Recipe has no static marker, but constants has 1 element → `StringConcatException`.
- Return type `void` cannot receive a `String` result → `StringConcatException`.
- Null static constant → `NullPointerException`.
- 201 parameter slots, exceeding the 200 threshold → `StringConcatException`.

The program only catches the intentionally triggered exceptions; other errors remain exposed rather than being arbitrarily swallowed by catching `Throwable`. This is a good way to write tests for API contracts.

## 8. Reading bytecode: proving the compiler generated a real invokedynamic

Run from the directory containing the class file:

~~~bash
javap -c -p ConcatRecipeDemo
javap -v -p ConcatRecipeDemo
~~~

In the tested `javac --release 17` build, the `compiled` method has bytecode like:

~~~text
static java.lang.String compiled(java.lang.String, int);
    Code:
       0: aload_0
       1: iload_1
       2: invokedynamic #7,  0
          // InvokeDynamic #0:makeConcatWithConstants:(Ljava/lang/String;I)Ljava/lang/String;
       7: areturn
~~~

The **index numbers** `#7`, `#0`, and line offsets may vary by compiler/JDK, because they are constant pool references, not a stable API. The corresponding `BootstrapMethods` section (abbreviated to show structure) will have:

~~~text
BootstrapMethods:
  0: ... REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants
    Method arguments:
      ... User=\u0001; n=\u0001
~~~

Here `\u0001` is how `javap` displays the control character in the recipe. It is not the two characters `\` and `u` in the concatenated result, but represents the placeholder for dynamic arguments.

### 8.1. Three things **not** to confuse in `javap`

| Observed item | Example | Role |
| --- | --- | --- |
| **Instruction** descriptor | `(Ljava/lang/String;I)Ljava/lang/String;` | Exactly two dynamic args `String` and `int`; return type `String` |
| **Bootstrap** signature | `(Lookup,String,MethodType,String,Object[])CallSite` in the method reference metadata | Signature of the Java method providing linkage, **not** the signature of runtime string concatenation |
| **Static bootstrap argument** recipe | `"User=\u0001; n=\u0001"` | Instructions for inserting literals and arguments in order |

To see what the compiler actually linked, you must find the `invokedynamic` line **inside the `compiled` body**, then follow `InvokeDynamic #...` to `BootstrapMethods`. The `main` code also contains string concatenations in `System.out.println` statements, so there can be **several other invokedynamic lines**. Do not take the recipe from another call site to explain the `compiled` method.

A key distinction: a Java call like `StringConcatFactory.makeConcatWithConstants(lookup,...,recipe)` in `main` is **calling the factory directly**, not automatically generating an `invokedynamic` instruction corresponding to the `CallSite` you are creating. Real instructions in the program appear when the compiler generates them for `"User=" + name + "; n=" + n` (and potentially other concatenations). These are two different approaches to understanding the same API.

## 9. Errors distinguished by three phases

| Phase | Example | Common error type | Right way to think about it |
| --- | --- | --- | --- |
| **Direct factory call** | Recipe missing U+0001, extra U+0002, `void` return, >200 slots | `StringConcatException` | API rejects an invalid **concatenation description** |
| **Direct factory call** | Passing null recipe or null static constant | `NullPointerException` | Null input is invalid for the factory |
| **JVM linkage of invokedynamic** | Bootstrap throws non-`Error`, fails to return a valid CallSite, or target type mismatches descriptor | `BootstrapMethodError` per JVMS rules | Error while linking the **instruction** |
| **MethodHandle invocation** | `invokeExact` site expects `(String)String` but handle is `(Object)String` | `WrongMethodTypeException` | Wrong **call-site type** at invocation |
| **Runtime String conversion** | An object's conversion method has buggy logic | Exception from conversion along the execution path | Not the same as a recipe mismatch |
| **Other mechanism** | `IllegalAccessException` when looking up another member manually | Separate lookup access error | Not a recipe parsing error |

With `MethodHandle.invokeExact`, both **parameter types and return type** at the Java call-site must **match `MethodHandle.type()` exactly**. Do not assume that because `String` is a subtype of `Object`, an `invokeExact` can automatically change the descriptor. If you need to adapt types validly, create an adapter with `asType`, but that is a choice of the calling code, not an automatic recipe-fixing feature.

`StringConcatException` extends `ReflectiveOperationException` and is a checked exception that can be thrown when building a concatenation. In the demo program, `main throws Throwable` covers both factory errors and `MethodHandle.invokeExact`.

## 10. When to put constants in the recipe, and when to use U+0002?

Putting literals directly in the recipe is usually the shortest way for separators and simple text like `"User="` or `"; n="`. U+0002 is useful when you need to supply a constant **as a separate bootstrap argument**:

- A long constant string or one reused in metadata/constant pool instead of embedding every character directly into the recipe.
- A constant containing U+0001 or U+0002 characters, which cannot be embedded literally directly into the recipe.
- A constant of a suitable constant-pool type, converted by the factory to its string representation at linkage; check the `toString` contract, null, and bootstrap argument size.
- Bytecode generators/DSL compilers that intentionally choose recipe shapes to balance the number of generated concatenation shapes, the number of bootstrap constants, and runtime performance.

Consider the API Note of `StringConcatFactory`: advanced strategies may yield slightly more efficient invocation bytecode in some cases, but can also generate **more specialized shapes** at runtime. “Putting every static part into U+0002” is not automatically more optimal than leaving literals in the recipe.

**Do not use bootstrap constants as mutable storage per invocation.** They are supplied at linkage and may be processed/converted by the factory at that time. When data needs to vary per user, request, or transaction, pass it in a **dynamic argument U+0001**.

### Constants in a class file differ from `final` variables in source code

The word “constant” in this lesson refers to **bootstrap static arguments** represented in class file metadata according to JVM rules. It does not mean any object referenced by a Java `final` variable can be stuffed into an arbitrary `invokedynamic` as a bootstrap constant. Class files have allowed constant types (such as strings, integers/floats, method handles, method types, classes, and appropriate dynamic constant structures); you must follow constant pool and `BootstrapMethods` rules.

In Java code calling the API **directly**, you can pass runtime objects via varargs per the Java method signature, but that **does not prove** it can be represented as a static bootstrap argument in a standard generated class file. When generating `invokedynamic` bytecode yourself, you must choose static argument types supported by the JVM.

## 11. Do string conversion and evaluation order differ from normal `+`?

The contract of StringConcatFactory is tied to **String conversion** rules (JLS `5.1.11`) and the **String Concatenation Operator `+`** (JLS `15.18.1`). Values are converted to strings and then combined from left to right. However, do not infer from this that Java argument expressions can be evaluated in an arbitrary order:

~~~java
String output = "A=" + first() + ", B=" + second();
~~~

This is an **illustrative** example requiring `first()` and `second()` to be defined. Under Java semantics, sub-expressions are evaluated in the order specified by the language. Even if the compiler uses a single `invokedynamic` at the end, it must preserve the observable behavior of the program, including the order of side effects from evaluating operands.

**Do not conflate** expression evaluation order with the order in which the factory parses the recipe: the recipe specifies **where already-computed values go**, whereas Java evaluation order specifies **when runtime values are computed** before the instruction is invoked. These are two different layers.

Regarding `char` and Unicode: a recipe contains UTF-16 `char`s; the two markers are the two code units U+0001/U+0002. Other Unicode characters in the recipe are preserved as Java UTF-16 code units. If you need literal control characters, pass them via a constant or dynamic arg as in the example instead of trying to “backslash-escape” them in the recipe.

## 12. Choosing StringConcatFactory or StringBuilder?

### When writing Java business code

Usually, write a simple expression:

~~~java
String message = "User=" + name + "; n=" + count;
~~~

The compiler/JVM chooses the appropriate concatenation strategy automatically. **There is no need, and you should not** call `StringConcatFactory` manually for every string concatenation; it is a low-level API for compilers, code generators, bytecode runtimes, or frameworks that need to create dynamic call sites. For appends inside complex loops or when capacity control is needed, an explicit `StringBuilder` is still easier to use. Measure actual performance instead of assuming the factory is faster for every workload.

### When building a compiler or runtime

`StringConcatFactory` makes sense if:

- You emit `invokedynamic` for string concatenation expressions in a DSL.
- You know the `MethodType` of the operands ahead of time, but **do not know the runtime values** until invocation.
- You want to pre-bind literals/static constants without increasing the target's arity.
- You need to preserve the JVM linkage contract, with the target type matching the instruction's descriptor.
- You have tests for bytecode/constant pool/recipe shape and check `StringConcatException`/`BootstrapMethodError` at each layer.

Pay attention to class loader lifecycles, the number of generated shapes, recipe sizes, reuse/caching strategies, and throughput/latency. The factory may optimize using JDK-dependent implementation strategies; **do not depend on hidden class names, internal paths, or specific bytecode shapes**.

## 13. Ordered recipe debugging checklist

1. **Read the invokedynamic descriptor:** determine the exact `MethodType`, including primitive/reference types, return type, and number/types of dynamic arguments.
2. **Count U+0001:** does it equal `concatType.parameterCount()` exactly? Each marker corresponds to an argument passed when the target runs.
3. **Count U+0002:** does it equal the number of static bootstrap constants exactly? Constants follow marker order.
4. **Check return type:** `concatType.returnType().isAssignableFrom(String.class)` must be `true`; `Object` can be valid, `void` is invalid.
5. **Check parameter slots:** must not exceed 200; remember `long` and `double` each occupy two slots.
6. **Check null:** dynamic null is valid; static constant null is rejected.
7. **Check literal control characters:** if literal U+0001/U+0002 appears in the **content** you want to concatenate, do not put it bare in the recipe.
8. **Check lookup privileges:** requires full privilege access per the factory Javadoc.
9. **Identify the error phase:** direct factory `StringConcatException`, instruction linkage `BootstrapMethodError`, wrong-type handle invocation `WrongMethodTypeException`.
10. **Find the right BootstrapMethods entry:** multiple concatenations can emit multiple `invokedynamic` instructions; match the constant-pool index of the instruction being debugged.
11. **Do not guess performance:** benchmark and inspect optimizations on the actual JVM.

## 14. Self-check questions

**Question 1.** How many dynamic arguments does the recipe `"A=" + ARG + ", B=" + ARG` have? If `concatType=(String,int)String`, is it valid?

**Answer:** It has **two U+0001**, corresponding to two dynamic args; the type has two parameters, so it is valid in placeholder count. The result from `("Lan",3)` is `"A=Lan, B=3"`.

**Question 2.** Recipe `"A=" + ARG + ", C=" + CONST` has `constants={"fixed"}`. Does the target need to receive an extra `"fixed"` argument at invocation?

**Answer:** No. Static constants belong to linkage. If `concatType=(String)String`, the target only receives one dynamic `String` and returns a String.

**Question 3.** Why can't you put the U+0001 character directly into a recipe to have it printed literally?

**Answer:** U+0001 is a reserved marker for dynamic arguments. You must pass a literal control character via a **static constant U+0002** or a dynamic argument, not bare in the recipe.

**Question 4.** Is `concatType=(String)Object` rejected because the return type is not `String.class`?

**Answer:** No. `Object.class.isAssignableFrom(String.class)` is true, so it is valid as a return type; the resulting object is still a String.

**Question 5.** `makeConcatWithConstants` has a recipe containing two `CONST`s, but only one constant in `constants`. What does the factory do?

**Answer:** `StringConcatException`, because the number of U+0002 differs from the number of static constant elements.

**Question 6.** Do passing `null` in a dynamic argument position and passing `null` as a static constant have the same behavior?

**Answer:** No. A dynamic null is converted to `"null"` per String conversion; a static null constant causes the factory to throw `NullPointerException` per the API contract.

**Question 7.** If the factory directly throws `StringConcatException`, will a JVM `invokedynamic` instruction running with a similar bootstrap always see that exact exception type at the caller?

**Answer:** Not necessarily. During invokedynamic linkage, non-`Error` exceptions from a bootstrap are typically wrapped by the JVM into `BootstrapMethodError`; that is a different error layer.

**Question 8.** Do 150 `long` parameters fit within 200 parameter slots?

**Answer:** No. Each `long` occupies 2 slots, totaling 300, exceeding the StringConcatFactory limit. (In practice there is also a JVM descriptor slot limit, so a descriptor containing 150 `long`s may be invalid at another layer.)

**Question 9.** In `javap -v`, is the signature `(Lookup,String,MethodType,String,Object[])CallSite` the signature of the runtime string concatenation target?

**Answer:** No. That is the signature of the **bootstrap method**. The target type is in the descriptor right at the `invokedynamic` instruction.

**Question 10.** Should you proactively move all literals into U+0002 to achieve the best performance?

**Answer:** No. Choosing between recipe, inline literals, and static constants affects the number of generated shapes; it must be balanced for the workload, and is usually left to the compiler/JDK for normal Java source.

## Official documentation

- [Java SE 17 — StringConcatFactory: makeConcat, makeConcatWithConstants, recipes, and linkage invariants](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html)
- [Java SE 17 — StringConcatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatException.html)
- [Java SE 17 — CallSite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [Java SE 17 — MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [JLS Java SE 17 — `5.1.11 String Conversion`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.11)
- [JLS Java SE 17 — `15.18.1 String Concatenation Operator +`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18.1)
- [JVMS Java SE 17 — `5.4.3.6 Dynamically-Computed Constant and Call Site Resolution`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
- [JVMS Java SE 17 — `6.5 invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic)
