# Deconstruction pattern and design goals

**Scope:** Java Core Pattern Matching, Deconstruction group. This article uses **record patterns**, the form of record deconstruction standardized in **Java 21 (JEP 440)**. Examples compile with JDK 21 or later without needing to enable preview.

## 1. What problem does the deconstruction pattern solve?

When a value carries structured data, a piece of code often needs to perform two consecutive tasks: **check what type it belongs to** and **extract the components to process**. The traditional approach is to use **instanceof**, create a variable for the object after the type check, and then call the component accessor methods.

Suppose we have a record:

~~~java
record Size(int width, int height) {}
~~~

When receiving an Object variable, we can write:

~~~java
if (value instanceof Size size) {
    int width = size.width();
    int height = size.height();
    System.out.println(width + " x " + height);
}
~~~

Java 21 allows placing the deconstruction pattern directly in the check expression:

~~~java
if (value instanceof Size(int width, int height)) {
    System.out.println(width + " x " + height);
}
~~~

The pattern **Size(int width, int height)** both requires the object to match the Size record and binds the values of the two components to width and height. The true branch can immediately use the bound variables.

This is the core goal: **bringing data shape checking and data extraction to the same location in the code**, so that readers clearly see which components the handling branch needs. This is not a mechanism for creating new objects, replacing constructors, or mutating the state of a record.

In Java 21, we usually call this specific form a **record pattern**. The concept of **deconstruction pattern** emphasizes the action of extracting components from an object; Java 21 does not have an arbitrary deconstructor syntax applicable to all ordinary classes.

## 2. Mechanism of record patterns

A record has a list of components declared in order:

~~~java
record Size(int width, int height) {}
record Shipment(String id, Size size, int units) {}
~~~

The corresponding pattern also describes the components **in the exact same positional order**:

~~~java
// Pattern 1: directly extract the three components of Shipment.
if (value instanceof Shipment(var id, var size, var units)) {
    System.out.println(id);
}

// Pattern 2: further deconstruct Size in the second component.
if (value instanceof Shipment(
        var id, Size(int width, int height), int units)) {
    System.out.println(id + ": " + width + " x " + height);
}
~~~

The code snippets above are **syntax illustrations**: assuming the two records have already been declared and value is a variable of type Object.

The matching process can be understood in four steps:

1. Check whether the outer value matches the specified record type (Shipment).
2. Extract the corresponding components of the record via the accessors provided by the record.
3. Continue matching each component against its subpattern; in the second pattern, the **size** component must match the **Size(...)** record pattern.
4. If the entire pattern matches, the variables **id, width, height, units** are bound and used within the scope where Java proves the pattern has matched.

**var** in a record pattern allows the compiler to infer the type of the component. For example, in **Shipment(var id, var size, var units)**, id has type String, size has type Size, and units has type int. Explicit types such as **int width** or **Size(...)** can be used when doing so helps the reader recognize the data directly in the pattern.

**Note on positional order:** **Size(int width, int height)** has two components in declaration order. Renaming the variables to **Size(int height, int width)** does not make Java swap the data positions; the first value is still passed into the first variable. Patterns do not support selecting components by name like a key/value mapping structure. You cannot write **Size(int width)** for a record consisting of two components.

## 3. Key design goals

### 3.1. Reduce mechanical steps before writing the main logic

When a branch needs multiple components, a record pattern can replace the repeated steps of extracting the object and calling accessors. The code focuses on **the values that the branch uses**, rather than intermediate variables that only serve to unpack data.

This does not mean every accessor call should be converted to a pattern. If a branch only needs one component, or also needs to pass the record object itself to another method, a type pattern with an accessor may be easier to understand.

### 3.2. Bring data structure directly into the decision condition

The nested pattern **Shipment(var id, Size(int width, int height), int units)** clearly states that the branch requires **a Shipment with a Size in the second position**. There is no need to read the branch body to discover this structural condition.

The goal here is **explicitness of preconditions on data shape**. It is useful for nested records, especially when code processes parser results, events, type-classified return values, or domain data represented by records.

### 3.3. Composable with other pattern matching expressions

Record patterns work with **instanceof** and **switch** supporting pattern matching in Java 21. You can nest a record pattern inside another record pattern and combine it with the **when** guard of a switch to express processing choices.

For example:

~~~java
return switch (value) {
    case Shipment(var id, Size(int w, int h), int units)
            when w > 0 && h > 0 && units > 0 ->
            "%s: %dx%d, units=%d".formatted(id, w, h, units);
    case Shipment(var id, var size, var units) ->
            "Invalid shipment: " + id;
    case null -> "No value";
    default -> "Unsupported";
};
~~~

The first branch expresses **correct type, correct structure, and satisfies business rules**. The next Shipment branch covers Shipments that do not meet the preceding condition; the last branch handles types outside the supported scope. With a selector of type Object, a fallback case is required; if you want to accept null, handle **case null** explicitly.

The **when** guard is evaluated after its preceding pattern matches, so **w, h, units** can be used in the guard. A Shipment branch with a specific guard must be placed before a general Shipment branch; reversing the order can cause the later branch to be dominated and reported as an error by the compiler.

### 3.4. Maintain type safety and clear variable scoping

The compiler checks the record type, the number of components, and the compatibility between subpatterns and components. Pattern variables are only in scope where matching is guaranteed. In **if (value instanceof Size(int width, int height))**, width and height are available in the true branch; they cannot be arbitrarily used along a path where the pattern might not have matched.

The purpose of record patterns is **describing data for decision-making**, not relaxing type checking or performing unchecked casts.

## 4. Complete example: comparing the manual approach and the deconstruction pattern

Requirement: receive an Object. If it is a Shipment with a valid Size, positive width and height, and positive units, return a description; if it is a Shipment that does not meet the conditions, return an invalid data message; null input and other types have their own messages.

Save all of the following code into **DeconstructionDesignDemo.java**:

~~~java
public class DeconstructionDesignDemo {
    record Size(int width, int height) {}
    record Shipment(String id, Size size, int units) {}

    static String manual(Object value) {
        if (value == null) return "No value";
        if (!(value instanceof Shipment shipment)) return "Unsupported";

        Size size = shipment.size();
        if (size != null
                && size.width() > 0
                && size.height() > 0
                && shipment.units() > 0) {
            return "%s: %dx%d, units=%d".formatted(
                    shipment.id(),
                    size.width(),
                    size.height(),
                    shipment.units());
        }
        return "Invalid shipment: " + shipment.id();
    }

    static String withPatterns(Object value) {
        return switch (value) {
            case Shipment(var id, Size(int w, int h), int units)
                    when w > 0 && h > 0 && units > 0 ->
                    "%s: %dx%d, units=%d".formatted(id, w, h, units);

            case Shipment(var id, var size, var units) ->
                    "Invalid shipment: " + id;

            case null -> "No value";
            default -> "Unsupported";
        };
    }

    public static void main(String[] args) {
        Object[] examples = {
                new Shipment("S-01", new Size(20, 10), 3),
                new Shipment("S-02", null, 2),
                new Shipment("S-03", new Size(0, 10), 1),
                null,
                "text"
        };

        for (Object example : examples) {
            String a = manual(example);
            String b = withPatterns(example);
            System.out.println(b + " | same=" + a.equals(b));
        }
    }
}
~~~

Use JDK 21 or later:

~~~bash
javac DeconstructionDesignDemo.java
java DeconstructionDesignDemo
~~~

Output:

~~~text
S-01: 20x10, units=3 | same=true
Invalid shipment: S-02 | same=true
Invalid shipment: S-03 | same=true
No value | same=true
Unsupported | same=true
~~~

**Reading the output:**

- **S-01** has a complete Shipment and Size; all three conditions—width, height, and units—are positive, so it matches the first branch.
- **S-02** is a Shipment with **size = null**. It does not match the nested **Size(int w, int h)** pattern, and then matches the fallback Shipment branch.
- **S-03** has a non-null Size, but width is 0: the structural pattern matches, **when** is not satisfied, so it falls through to the fallback Shipment branch.
- **null** enters **case null**, while the string **"text"** enters **default**.
- The **same=true** value for all five inputs demonstrates that the two implementations in this example produce the same results, not that the two approaches are always equivalent in every program.

The improvement of the record pattern is that the first branch directly shows **Shipment containing Size with width, height, and units to check**; there is no need to look for accessor calls in the body. The trade-off is that nested patterns together with guards can become long if the model is complex.

## 5. Deconstruction is not synonymous with data validation

A record pattern expresses **shape and type**, while business rules often require additional conditions.

For example, **Size(int w, int h)** checks that the size component can be viewed as a Size record and extracts w and h. It **does not automatically guarantee** that w and h are positive. Checking **w > 0 && h > 0** in the guard is what expresses that requirement.

It is also necessary to distinguish **null in a nested record** from **null in a leaf component**:

- If Shipment has **size = null**, the nested pattern **Size(int w, int h)** does not match because there is no Size record to deconstruct.
- If a reference component is bound by an unconditional pattern such as **var id** or an unconditional type pattern matching the component type in a record pattern, the bound value **can still be null**. Do not infer that every component is non-null after a record pattern matches.
- Primitive components such as int cannot hold null; boxed types such as Integer or reference components can be null if the record's constructor allows it.
- A record can proactively check invariants in its constructor. However, the deconstruction syntax itself does not automatically enforce those domain rules.

If the application needs to check that id is non-empty, units is within a value range, or the shipping status is valid, use explicit business conditions, methods whose names express intent, or establish appropriate invariants in the record. Do not turn patterns into an imaginary validation mechanism.

## 6. Limitations and design choices

### Only records can be deconstructed with record pattern syntax

The **SomeRecord(...)** syntax in Java 21 applies to compatible **record** types. It does not work for an ordinary class just because that class has getters or a constructor with a parameter list similar to a record. Java 21 also does not provide arbitrary destructuring assignment in the form of a single statement declaring multiple variables from an object.

A record pattern uses the component structure declared by the record; it does not call a constructor to create a copy. With a regular type pattern, you obtain a variable representing the object itself and can call accessors when needed.

### Decide to use patterns based on clarity, not line count

| Case | Consideration |
| --- | --- |
| A simple record where multiple components need to be read | A short record pattern is usually clear |
| A branch only needs one component or the whole object | A type pattern and accessor may be easier to follow |
| A branch depends on a short nested record structure | A nested record pattern helps present the condition inline |
| Deeply nested patterns with many variables and long guards | Split into a nested record check step or a separate method |
| Need to distinguish failure reasons for each subcomponent | Handle step by step instead of lumping all non-matching cases together |
| Component structure changes frequently | Consider that the pattern will couple directly to the record's component API |

A deeply nested pattern can make code hard to read even with fewer lines. The design goal is to help readers recognize **why the handling branch applies**, so variable names, layout, and condition boundaries matter more than achieving the shortest line count.

### Do not automatically assume record patterns improve performance

Record pattern syntax primarily improves **expressiveness and type checking**. Whether it is faster or slower depends on the program, accessor behavior, the compiler, and the JVM. You should not choose record patterns solely based on expected performance gains without measuring.

## 7. Common mistakes

1. **Confusing a pattern with a constructor:** **Size(int w, int h)** in instanceof/switch is a pattern, not creating a new Size.
2. **Confusing component order:** record patterns are positional; renaming variables does not change the components they receive.
3. **Missing or extra components:** the pattern must correspond to the number of components of the record, even when only a few values are needed.
4. **Assuming a null nested record still matches a nested record pattern:** **Size(...)** does not match null; a handling branch is needed if the data can be missing.
5. **Assuming all variables after deconstruction are non-null:** reference components bound by unconditional patterns can still be null.
6. **Confusing structural checks with business logic:** deconstruction extracts components; positivity/negativity, bounds, or validity conditions require separate checking code.
7. **Using pattern variables outside their valid scope:** pattern variables can only be used where a match is guaranteed; on the false path, they are not implicitly available.
8. **Placing a broad case before a case with a specific guard:** this can cause the specific branch to be dominated and cause a compilation error.
9. **Relying on default to handle a null selector:** with switch pattern matching, use **case null** when null is an input that needs to be supported.

## 8. How to self-evaluate a design

Before using a deconstruction pattern, answer the following questions: is the input actually a record; does this branch need multiple components; does seeing the record structure directly in the condition help understand the business logic; do null and wrong-type cases have clear handling paths; is the guard short enough to read immediately; and is the dependency on the record's component order/structure acceptable?

If a pattern makes the purpose of the branch clearer, a record pattern is a good choice. If it exposes too many unrelated details, forces the reader to count parentheses, or mixes together many business checks, keep the nested record in a named variable and process it in smaller steps.

**Key takeaway:** the design goal of the deconstruction pattern is to combine **type checking, structural description, and component binding** into a type-safe way of writing code that fits Java's pattern matching. Conciseness is only valuable when readers understand the conditions and behavior faster.