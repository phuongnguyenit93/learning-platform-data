# Method Overloading and What Forms a Method Signature in Java

> **Java core — language-basics / Methods**  
> **Environment:** JDK 17+, no preview features or external libraries needed.  
> **Objective:** Recognize **valid overload** declarations, know which components truly distinguish a **method signature**, understand how Java selects an overload at compile time, and avoid duplicate signatures or ambiguous calls.

## 1. What Is Method Overloading?

*Method overloading* allows a class to have multiple methods with the **same name** but **different parameter type lists**, to express operations with the same conceptual purpose:

~~~java
static String render(int number) {
    return "int:" + number;
}

static String render(long number) {
    return "long:" + number;
}

static String render(String text) {
    return "String:" + text;
}

static String render(int left, int right) {
    return "pair:" + (left + right);
}
~~~

The following calls resolve to their corresponding declarations:

~~~java
render(7);        // "int:7"
render(7L);       // "long:7"
render("7");      // "String:7"
render(3, 4);     // "pair:7"
~~~

All are invoked using the name `render`, yet the compiler selects the method based on **argument count, types of argument expressions, and Java's overload resolution rules**. Using the same name does not mean methods can be declared arbitrarily.

Overloading is **choosing among declarations with different signatures**; it is not *overriding*, where a subclass redefines an inherited method under its own rules.

## 2. Which Components Form a Method Signature?

For non-generic methods at an introductory level, identify the signature by **method name + ordered list of parameter types**.

| Change in declaration | Creates a different overload? | Example |
| --- | --- | --- |
| Same name, **different number of parameters** | Yes | `print(int)` and `print(int, int)` |
| Same name, **different parameter types** | Yes | `print(int)` and `print(long)` |
| Same name, **different order of parameter types** | Yes | `show(int, String)` and `show(String, int)` |
| Changing only **parameter variable names** | No | `calc(int x)` and `calc(int y)` |
| Changing only **return type** | No | `int calc(int)` and `long calc(int)` |
| Changing only `public`/`private`, `static`, or `final` | No | `static calc(int)` and instance `calc(int)` |
| Changing only `throws` clause | No | `work(int)` and `work(int) throws IOException` |

Two methods in the same class cannot coexist merely by changing components that **do not distinguish a signature**. Even `static` and instance methods **cannot** be declared with the same name and parameter list in the same class.

Valid example due to **different parameter order**:

~~~java
static String combine(int count, String label) {
    return count + "/" + label;
}

static String combine(String label, int count) {
    return label + "/" + count;
}
~~~

Parameter types `int, String` and `String, int` produce two distinct signatures even though both have two parameters. Swapping only the **names** `count`/`label` while keeping the types in the same positions **does not** create an overload.

**Specification scope note:** For *generic* methods, the signature definition in the Java Language Specification also considers type parameters and type equivalence rules; checking for name/type collisions after *type erasure* is also important. The name + parameter types rule above is the accurate model for the non-generic examples in this lesson.

## 3. Invalid Declarations Due to Duplicate Signatures

The following pairs are **compile-time error examples**; do not place them together in a runnable program:

~~~java
// ERROR 1: changing only parameter name.
// static int size(int count) { return count; }
// static int size(int amount) { return amount; }

// ERROR 2: changing only return type.
// static int value(int x) { return x; }
// static String value(int x) { return "" + x; }

// ERROR 3: changing only static or access modifier.
// static int code(int x) { return x; }
// int code(int x) { return x; }

// ERROR 4: differing only in throws.
// static int load(int x) { return x; }
// static int load(int x) throws java.io.IOException { return x; }
~~~

Different return types **are allowed** if the parameter lists already differ:

~~~java
static int parseValue(int value) {
    return value;
}

static String parseValue(String value) {
    return value.trim();
}
~~~

In the two methods above, the `int` vs. `String` difference in the **parameter** is what makes the overload valid; differing return types is simply each method's choice.

**Arrays and varargs:** `int... values` is treated as an `int[]` array parameter in the signature; you cannot simultaneously declare `sum(int[])` and `sum(int...)` with the same name in the same class:

~~~java
// Choose ONLY ONE of the two declarations below:
// static int sum(int[] values) { ... }
// static int sum(int... values) { ... } // Duplicate signature with the version above.
~~~

**Generics and erasure:** `process(List<String>)` cannot overload `process(List<Integer>)` in the same class solely via the `String`/`Integer` type arguments. Both have the same parameter *erasure* `List` and cause a *name clash*:

~~~java
// DOES NOT COMPILE if both are in the same class:
// static void process(java.util.List<String> a) {}
// static void process(java.util.List<Integer> b) {}
~~~

## 4. How Does Java Select an Overload at Compile Time?

The compiler examines methods with a matching name, checks applicability for the argument types, and selects the most specific method according to Java's rules. You can remember the order in which key phases are considered:

1. **Fixed-arity call without boxing/unboxing** (primitive/reference widening may be used).
2. **Fixed-arity call allowing boxing/unboxing** when the previous phase has no applicable method.
3. **Varargs call** when the previous phases fail to select an applicable method.

Example with primitive widening `int → long` and boxing `int → Integer`:

~~~java
static String select(long value) {
    return "long:" + value;
}

static String select(Integer value) {
    return "Integer:" + value;
}
~~~

| Call | Selected overload | Why |
| --- | --- | --- |
| `select(5)` | `select(long)` | Widening `int` to `long` is considered before boxing |
| `select(5L)` | `select(long)` | Exact match `long` |
| `select(Integer.valueOf(5))` | `select(Integer)` | Exact reference match `Integer` |
| `select((Integer) null)` | `select(Integer)` | Expression type is `Integer`; does not unbox null |

**Do not guess by “runtime type of the object”:** Normal overload selection is based on the **static type of the expression at the call site**. If you have `Object value = "Hi";`, the call `label(value)` selects overload `label(Object)` rather than switching to `label(String)` because the actual object is a string.

Among equally applicable overloads, Java also applies the **most specific** rule. If a single most specific method cannot be chosen, the call fails with an **ambiguous** error rather than guessing at random.

## 5. `null`, Casting, and Ambiguous Calls

Suppose there are two methods:

~~~java
static String label(Object value) {
    return "Object:" + value;
}

static String label(String value) {
    return "String:" + value;
}
~~~

Because `String` is a subtype of `Object`, the results are:

~~~java
label("Hi");              // "String:Hi"
label((Object) "Hi");     // "Object:Hi"
label(null);              // "String:null" (String is more specific than Object).
~~~

Use a **cast** to clarify the expression type at the call site when needed. However, casts should not replace clear API design.

If you declare a pair of overloads whose types are **unrelated by a subtype relationship**:

~~~java
// Suppose these are declared:
// static void choose(String text) {}
// static void choose(Integer number) {}

// choose(null);             // ERROR: ambiguous.
// choose((String) null);    // VALID: selects String.
// choose((Integer) null);   // VALID: selects Integer.
~~~

Java cannot uniquely choose for `choose(null)` between `String` and `Integer`. That is an error **at compile time**, not a `NullPointerException` at runtime.

## 6. Varargs and Overload Resolution Phases

In a signature, `int... values` corresponds to an `int[]` array parameter: you cannot declare both `f(int...)` and `f(int[])` with the same name in a single class.

~~~java
static String choose(int value) { return "single:" + value; }
static String choose(int... values) {
    return "count=" + values.length;
}

System.out.println(choose(4));    // single:4.
System.out.println(choose(4, 5)); // count=2.
System.out.println(choose());     // count=0.
~~~

A call with one `int` selects the **fixed** overload when a method is applicable in the fixed-arity phase, before needing varargs. Multiple varargs overloads with unrelated element types can make `f()` or `f(null)` **ambiguous at compile time**.

For this lesson, you only need to know that varargs **does not create a new signature** and affects overload selection. The varargs/arrays lesson focuses on passed arrays, `null`, array element types, and generic varargs risks.


## 7. Standalone Runnable Java 17+ Program

Create the file **MethodOverloadDemo.java**:

~~~java
public final class MethodOverloadDemo {
    private static String render(int value) {
        return "int:" + value;
    }

    private static String render(long value) {
        return "long:" + value;
    }

    private static String render(String value) {
        return "String:" + value;
    }

    private static String render(int left, int right) {
        return "pair:" + (left + right);
    }

    private static String combine(int count, String label) {
        return count + "/" + label;
    }

    private static String combine(String label, int count) {
        return label + "/" + count;
    }

    private static String select(long value) {
        return "long:" + value;
    }

    private static String select(Integer value) {
        return "Integer:" + value;
    }

    private static String label(Object value) {
        return "Object:" + value;
    }

    private static String label(String value) {
        return "String:" + value;
    }

    private static String aggregate(int... values) {
        int sum = 0;
        for (int value : values) {
            sum += value;
        }
        return "count=" + values.length + ",sum=" + sum;
    }

    private static String aggregate(int value) {
        return "single:" + value;
    }

    // Valid: overloads main, though the launcher selects main(String[]).
    public static String main(int value) {
        return "main(int):" + value;
    }

    public static void main(String[] args) {
        System.out.println("int=" + render(7));
        System.out.println("long=" + render(7L));
        System.out.println("string=" + render("7"));
        System.out.println("pair=" + render(3, 4));

        System.out.println("orderedA=" + combine(2, "X"));
        System.out.println("orderedB=" + combine("X", 2));

        System.out.println("widen=" + select(5));
        System.out.println("boxed=" + select(Integer.valueOf(5)));
        System.out.println("castNull=" + select((Integer) null));

        Object upcast = "Hi";
        System.out.println("referenceStaticType=" + label(upcast));
        System.out.println("referenceString=" + label("Hi"));
        System.out.println("referenceNull=" + label(null));

        System.out.println("varargsEmpty=" + aggregate());
        System.out.println("varargsMany=" + aggregate(2, 3, 4));
        System.out.println("varargsArray=" + aggregate(new int[] {8, 9}));
        System.out.println("fixedOne=" + aggregate(4));

        System.out.println("otherMain=" + main(3));
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 MethodOverloadDemo.java
java MethodOverloadDemo
~~~

**Exact expected stdout:**

~~~text
int=int:7
long=long:7
string=String:7
pair=pair:7
orderedA=2/X
orderedB=X/2
widen=long:5
boxed=Integer:5
castNull=Integer:null
referenceStaticType=Object:Hi
referenceString=String:Hi
referenceNull=String:null
varargsEmpty=count=0,sum=0
varargsMany=count=3,sum=9
varargsArray=count=2,sum=17
fixedOne=single:4
otherMain=main(int):3
~~~

`widen=long:5` illustrates primitive widening taking priority over boxing; `referenceStaticType` shows overload selection is based on the expression's type. `fixedOne` shows the fixed-arity version can take priority over varargs. The launcher still runs `main(String[])` even though the class also has `main(int)`.

## 8. Checklist and Exercises

| Before declaring an overload | What to check |
| --- | --- |
| Are the names identical? | To overload, use the same name |
| Do parameter types/count/order genuinely differ? | This is the deciding factor at an introductory level |
| Changed only return type or parameter names? | Does not create a valid overload |
| Changed only `static`, access modifier, `throws`? | Does not distinguish signatures |
| `int...` vs. `int[]`? | Duplicate signature, do not declare both |
| Generic `List<String>` and `List<Integer>`? | Hits a name clash due to erasure |
| Passing `null` to two unrelated parameter types? | Can be ambiguous; consider casting or a clearer API |
| Too many overloads taking closely related types? | Test calls with literals, casts, boxing, and varargs |

**Exercise 1.** Write `area(int side)` and `area(int width, int height)` to compute the area of a square/rectangle. State where the two signatures differ.

**Exercise 2.** Write `describe(int)`, `describe(long)`, and `describe(String)`. Predict the choice when passing `4`, `4L`, and `"4"`.

**Exercise 3.** Explain why `void test(int x)` and `int test(int y)` cannot both be declared even though their return types differ.

**Exercise 4.** Write two overloads taking `(int, String)` and `(String, int)`; test passing arguments in the right and wrong order to observe compile-time checking.

**Exercise 5.** Create `print(Object)` and `print(String)`. Predict the calls `print(null)`, `print((Object) "x")`, and `print("x")`. Then analyze the ambiguity error if `Object` is replaced with `Integer`.

**Exercise 6.** Write `total(int... values)` and call it with 0, 1, multiple elements, or an `int[]`; explain why you cannot additionally declare `total(int[])` with the same name.

### Key Takeaway

**Overloading distinguishes methods by name and parameter type list (count, types, order)**; you cannot change only return type, parameter names, `static`, or `throws`. Java selects overloads based on **argument types at compile time**, following applicability and specificity rules. Watch out for ambiguous `null`, boxing/varargs, and signature collisions after generic erasure.