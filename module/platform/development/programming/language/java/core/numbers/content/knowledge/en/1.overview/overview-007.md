# Prerequisites and Recommended Learning Sequence — Java Core: Numbers

## 1. Who Is This Lesson For?

This is a **preparation and self-study map** for learners who already know basic Java syntax but are unsure where to start when facing numeric problems. The goal is to assess your starting point, establish a practice order, and know where to backtrack when mistakes happen; the preceding lessons provide in-depth explanations of each type and operation.

You need JDK 17 or newer to run the examples, and must know how to create a class with `main`, declare variables, write expressions, call methods, handle exceptions, and read terminal output. You do not yet need Spring, multithreading, or JVM memory internals.

## 2. Prerequisites Check

| Foundation | Must Be Able To | If Not Yet Ready |
| --- | --- | --- |
| JDK and terminal | Run `javac File.java` then `java File` | Review compiler, classpath, and Java source files |
| Variables, literals, operators | Predict `2 + 3 * 4` and `(2 + 3) * 4` | Review operator precedence and parentheses |
| Data types, type conversions | Distinguish `int`, `double`, casting before/after division | Review operand types and assignment |
| Methods and `import` | Call `Math.max(2, 3)` | Review calling static methods |
| Branching, loops | Check negative values, iterate over multiple inputs | Review conditionals and comparison operators |
| Exceptions | Use `try/catch` for invalid parsing or integer division by 0 | Review `NumberFormatException`, `ArithmeticException` |

### Self-Runnable Entry Check

Create `NumbersPrerequisiteCheck.java`:

```java
public class NumbersPrerequisiteCheck {
    public static void main(String[] args) {
        int items = 7;
        int groups = 2;
        System.out.println(items / groups);
        System.out.println((double) items / groups);
        System.out.println(2 + 3 * 4);
        System.out.println((2 + 3) * 4);
    }
}
```

```bash
javac NumbersPrerequisiteCheck.java
java NumbersPrerequisiteCheck
```

Result:

```text
3
3.5
14
20
```

If the output differs from your prediction, explain **the types at the moment each operation occurs** and operator precedence before running again. This is a check of foundational Java skills, not a memorization test of value-range tables.

## 3. Eight-Lesson Learning Sequence for the Chapter

The chapter menu starts with real-world scenarios, moves into mechanisms, and concludes with using the right JDK version. Follow the order below on your first pass; if you already know a topic, use the self-check column to choose what to review.

| Stage | Lesson in Chapter | Self-Check Question Before Moving On |
| --- | --- | --- |
| 1 | What Are Numbers in Java and What Problems Need Representation | Explain why code `"00123"` differs from quantity 123 and price 123.00 |
| 2 | Distinguishing Mathematical Value, Data Type, and Storage Representation | Separate value, type, stored bits, and display string |
| 3 | Integers, Floating-Point Numbers, and Exact Decimals | Predict behavior of integer division, floating-point, and BigDecimal |
| 4 | How Value Range Differs from Precision | Distinguish overflow from loss of resolution in floating-point numbers |
| 5 | Map of Primitives, Wrappers, Number, BigInteger, and BigDecimal | Know why unboxing null fails and why Number has no generic addition operator |
| 6 | Choosing Types by Data Semantics and Calculation Requirements | Justify type choices for invoices, counters, sensors, and APIs |
| 7 | Prerequisites and Recommended Learning Sequence | Self-assess weak spots and plan targeted review |
| 8 | Java Core Scope and How to Cross-Reference JDK Versions | Check whether a method exists in Java 17 or was introduced only in Java 21 |

**How to use the map:** After stage 2, practice explaining why a displayed number can differ from its stored bit representation. After stages 3–4, test `0.1 + 0.2` and adding `1` to `1e16` to see the difference between representation error and resolution. Stage 5 helps you read APIs taking `Number`; stage 6 asks you to make decisions backed by data contracts; stage 8 verifies compatibility when moving a project to another JDK.

## 4. Ordered Practice

### Exercise A — Read Expressions Before Running

Given `int a = 9, b = 4;`, predict `a / b`, `a % b`, `(double) a / b`, and `(double) (a / b)`. Self-verify that the outputs are `2`, `1`, `2.25`, `2.0` respectively. If wrong, review **stages 2–3**; the cause is operand types and cast timing.

### Exercise B — Identify the Kind of Error

Run `Integer.MAX_VALUE + 1`, `16777216f + 1 == 16777216f`, and `0.1 + 0.2 == 0.3`. The three expressions respectively demonstrate integer overflow, float resolution, and binary rounding. Explain the differences before choosing `Math.addExact`, changing the numeric type, or using exact decimal. If confused, review **stages 3–4**.

### Exercise C — From Requirements to Data Types

An order has code `"000045"`, quantity 3, price `"19.95"`, 8% tax, and total processed volume exceeding 4 billion bytes. Propose Java types and identify:

1. Which field is an identifier, and which fields are quantities to compute?
2. Which intermediate operation could overflow if both operands are `int`?
3. Where must scale, currency unit, `RoundingMode`, and rounding timing be agreed upon?
4. Do JSON/client and database preserve the values, units, and leading zeros intact?

If you cannot defend your decisions, go back to **stages 5–6**.

### Exercise D — Check JDK Compatibility

Using release-specific API documentation, look up `Math.addExact`, `NumberFormat.getCompactNumberInstance`, and `Math.clamp`. Compile appropriate examples with `javac --release 17`, distinguishing missing APIs from syntax errors. If you do not yet know how compiler, runtime, and `--release` differ, review **stage 8**.

## 5. How to Self-Study and Record Evidence

At each stage, keep a short table of *prediction → experiment → actual output → root cause → lesson to review*. For measurements, test `NaN` and error bounds; for integers, test extreme values and intermediate operations; for money, test midpoint values requiring rounding; for wrappers, test `null` at unboxing. The goal is to explain **why** a result happens and **when** an approach remains valid.

Check off each item after self-testing:

- [ ] Can compile/run standalone Numbers examples and distinguish compile errors from runtime exceptions.
- [ ] Can predict operand types for integer division, promotion, casts, and result assignment.
- [ ] Recognize overflow and apply `Math.*Exact` on the right operation when checking is needed.
- [ ] Distinguish range, precision, and floating-point representation error.
- [ ] Explain primitives, wrappers, `Number`, `BigInteger`, `BigDecimal`, and `null` risks.
- [ ] Choose types based on domain, units, operations, and specific decimal/rounding requirements.
- [ ] Verify data preservation across JSON, databases, formatting, and locales.
- [ ] Know how to look up the right API version and verify `javac --release` on the target runtime.

**Once achieved:** move on to the advanced numeric API lessons in the module. If any item remains incomplete, return to the exact stage and craft a new boundary test; there is no need to restudy the entire chapter over one small slip.