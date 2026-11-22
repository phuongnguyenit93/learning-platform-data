# Java Pattern Matching Review and Testing Checklist

**Pattern matching** helps Java code reduce manual casting and express branches more clearly, but concise syntax does not automatically guarantee that all data is handled correctly. A misordered `case` can be shadowed; a nested record pattern can fail to match due to a `null` component; a `when` guard can miss a boundary case; and an accidental `default` can hide missing handling when a subtype is added. Therefore, **Pattern Matching code review and testing** must verify **both compiler rules and runtime behavior as well as business contracts**.

This article belongs to **Java Core Pattern Matching → Checklist pattern**, under the topic **Review and Testing Checklist**. The content is designed for use when opening or reviewing a pull request (PR) that includes `instanceof` type patterns, record patterns, nested deconstruction, sealed hierarchies, and pattern matching for `switch`. At the end of the article, there are two standalone, verified Java 21+ programs: one that **runs 11 runtime test cases**, and one that uses the **Java Compiler API** to verify two scenarios that must be rejected and one positive control that must compile successfully.

**Versions:** Pattern matching for `instanceof` has been stable since **Java 16** (JEP 394), records since Java 16 (JEP 395), sealed classes/interfaces since **Java 17** (JEP 409), and record patterns and pattern matching for `switch` since **Java 21** (JEP 440/441). The examples using `case Type(var ...)` and `when` guards require **JDK 21+**, with no preview flags needed.

## 1. Reading the checklist in three layers

Do not just ask "Does the code compile?". Distinguish three layers of verification:

| Layer | Questions to answer | Primary tools |
| --- | --- | --- |
| **Compile-time** | Does the syntax match the target JDK? Are the patterns valid? Are any cases dominated or is the switch non-exhaustive? | `javac --release 21`, compiler tests |
| **Behavior** | Do matching inputs, non-matching inputs, `null`, true/false guards, and fallback branches produce the expected results? | Unit tests, parameterized tests, assertions |
| **Design and business logic** | Are invariants, access permissions, side effects, state, compatibility, and scope of changes handled properly? | Code review, integration tests, domain tests |

The compiler can catch certain issues such as dominance, scope, or exhaustiveness. However, it **cannot automatically know** what error code an empty order should return, whether a guard calling a payment gateway is safe, or whether two conditions `n > 5` and `n > 3` are ordered according to business policy.

### One-minute checklist before diving into details

- [ ] The PR clearly specifies the **JDK/build target** and the new pattern features used.
- [ ] The selector and the selector's static type are clear (`Object`, sealed type, record, etc.).
- [ ] `instanceof` type patterns are used for simple cases; not every check is forced into a long `switch`.
- [ ] Record patterns extract components in the **exact order** and with the right business names.
- [ ] Pattern variable scope matches only the paths where the pattern matched.
- [ ] `null` for the selector and `null` for nested components are considered separately.
- [ ] Guarded/narrower cases precede general cases; no branch is dominated.
- [ ] For a sealed `switch`, the exhaustiveness strategy and whether `default` is needed are clearly understood.
- [ ] Guards are easy-to-read conditions, preferably pure, without hidden side effects.
- [ ] Tests include at least one **match**, **non-match**, **guard false**, and **null** where relevant.
- [ ] The code can be recompiled and retested automatically in CI.

This is the orientation overview. The following sections explain **why each item needs checking** and **how to write the corresponding tests**.

## 2. Review the selector type and Java version first

A good review starts with the **inputs and tooling**, not with the shape of the `case` branches.

Example:

~~~java
// Java 21+, snippet; 'input' has type Object.
String result = switch (input) {
    case String text -> "Text";
    case Integer number -> "Number";
    case null -> "Missing";
    default -> "Other";
};
~~~

On `Object`, many types are not listed, so `default` makes sense. If the selector is a **sealed interface** with only a few direct subtypes, specific cases can be used without `default` so the compiler reminds you when the model is extended.

**Version review checklist:**

1. Which JDK does the project actually use for the compiler? Are `java -version`, `javac -version`, Maven/Gradle toolchains, and CI aligned?
2. What is the `source/release` level? `javac --release 17` cannot compile record patterns and pattern `switch` in Java 21 syntax.
3. Is any old preview syntax being used? `when` in pattern `switch` is stable in Java 21; do not copy preview examples from older JDKs without checking.
4. Does the deployment runtime support the generated **class-file version**? Java 21 uses major version 65; running Java 21 bytecode on JVM 17 can result in `UnsupportedClassVersionError`.
5. Do dependencies and build plugins require a different JDK than the target the project commits to?

**Suggested test:** run a clean build and compiler with the declared target; run unit/integration tests on the minimum supported JVM. `--release` controls syntax and Java Platform APIs at compile time, but does not replace runtime/dependency testing.

## 3. Review `instanceof` type patterns and flow scoping

Traditional style:

~~~java
// Snippet inside a method taking Object input.
if (input instanceof String) {
    String value = (String) input;
    System.out.println(value.trim());
}
~~~

Since Java 16, you can write:

~~~java
// Java 16+, snippet.
if (input instanceof String value) {
    System.out.println(value.trim());
}
~~~

**Points to review:**

- A type pattern **does not match `null`**: if `input == null`, the `if` branch does not execute.
- `value` is only in scope where flow analysis proves the pattern has matched.
- Removing the cast must **preserve behavior**. Do not simultaneously delete a null check, change an exception, or alter business logic just because the syntax is shorter.
- Variable names like `value`/`customer`/`text` communicate role better than a single letter `x` in longer code.
- With generic types, watch out for type erasure and constraints on valid patterns; do not assume you can do `instanceof List<String>` as a full runtime generic type check.

### Valid flow scoping

~~~java
// Java 16+, snippet inside a method returning String.
if (!(input instanceof String text)) {
    return "Other";
}
return text.trim();
~~~

The non-matching branch returns early, so below it the compiler knows `text` is definitely bound.

### Intentionally invalid flow scoping

~~~java
// INTENTIONALLY INVALID: execution can continue even without a match.
if (!(input instanceof String text)) {
    System.out.println("Other");
}
return text.trim();
~~~

The compiler cannot guarantee that `text` exists at the `return` statement. This is a **scope / definite-match error**, not a dominance error.

**Tests:** at minimum test an input of the matching type, a non-matching type, and `null`. If the pattern has an accompanying `&&` condition, also test a value that makes the right-hand side false; if the condition was refactored from `if/else`, compare before-and-after behavior.

## 4. Review record patterns and component order

Record patterns rely on the **structure and order of declared components**:

~~~java
record Point(int x, int y) {}

// Java 21+, snippet inside a method taking Object input.
if (input instanceof Point(var x, var y)) {
    System.out.println(x + "," + y);
}
~~~

With `Point(2, 3)`, `x` is `int 2` and `y` is `int 3`. `var` here does not give the variable type `Object`; the compiler infers the type from the record component.

### Dangerous pitfall: swapped names that still compile

~~~java
record Address(String city, String country) {}

// INTENTIONALLY SEMANTICALLY WRONG, even though it compiles.
if (input instanceof Address(var country, var city)) {
    System.out.println(city + "/" + country);
}
~~~

`country` in the pattern actually receives the **first component `city`**, and `city` actually receives `country`. Because both are `String`, the compiler cannot detect that the intended variable meanings were swapped.

**Record checklist:**

- [ ] Component count and order match the record signature.
- [ ] Local variable names reflect the actual components, especially when multiple components share the same type.
- [ ] Inferred types of `var` are clearly understood; when ambiguous, use typed patterns or named accessors.
- [ ] Record constructors/factories enforce necessary invariants; **patterns do not perform business validation on their own**.
- [ ] If the record shape is part of a public API, changing component count or order has been evaluated for compatibility.
- [ ] Do not use a record pattern just to extract a single field if `object.field()` is clearer and less coupled to structure.

**Tests:** construct records with components that are clearly distinct in value and meaning, such as `Address("Hue", "VN")`, to easily catch swapped components. Test the data contract, not just branch counts.

## 5. Review nested deconstruction: selector `null` vs component `null`

Suppose:

~~~java
record Address(String city) {}
record Customer(String id, Address address) {}
~~~

Nested pattern:

~~~java
// Java 21+, snippet; input has type Object.
String result = switch (input) {
    case Customer(var id, Address(var city)) -> id + ":" + city;
    case Customer(var id, var address) -> "Missing address";
    case null -> "No customer";
    default -> "Other";
};
~~~

Distinguish these cases:

- `input == null`: selects `case null`.
- `new Customer("C-1", null)`: the nested `Address(...)` **does not match**; the `Customer(var id, var address)` branch can still match and bind `address == null`.
- `new Customer("C-2", new Address(null))`: the nested `Address(var city)` can still match, because `var city` accepts a null reference value; a separate guard or validation is needed to handle a null city.
- `new Customer("C-3", new Address("Hue"))`: the nested pattern matches successfully.

**Do not automatically equate** "nested pattern did not match" with "invalid data". A pattern only states that **the required shape did not match**. Business validation may still need to return `MISSING_CUSTOMER`, `INVALID_CITY`, or different reasons.

**Minimum test matrix:**

| Input | What to verify |
| --- | --- |
| Selector `null` | Has `case null` or an explicit null-rejection policy |
| Outer record non-`null`, nested component `null` | Nested record pattern does not match and falls back properly |
| Outer record non-`null`, nested record has `null` reference field | `var` binds null; guard/validation behaves properly |
| All records/components present | Nested branch succeeds |
| Record of matching type but rejected by business guard | Logical fall-through to the next case, not classic Java `case:` fall-through |
| Selector value of unrelated type | Proper default policy or narrow API type |

`case ... ->` branches in `switch` **do not use classic switch-statement fall-through**. When a guard evaluates to false, matching continues to the next case; when an arrow branch is selected, execution does not continue into subsequent branches.

## 6. Review `when` guards and case order

A guard is evaluated **only after its corresponding pattern matches**:

~~~java
// Java 21+, input has type Object.
String category = switch (input) {
    case Integer n when n >= 100 -> "large";
    case Integer n when n > 0 -> "positive";
    case Integer n -> "non-positive";
    case null -> "missing";
    default -> "unsupported";
};
~~~

Reviewers should ask:

1. **Are boundaries right?** `n == 100` goes to large; `n == 1` goes to positive; `n == 0` goes to non-positive.
2. **Are cases ordered sensibly?** Narrower/stricter branches typically come before broader ones.
3. **Is the guard pure?** Expressions like `n >= 100` are appropriate; operations like `repository.save(...)` or `paymentGateway.charge(...)` are not appropriate as branch-selection conditions.
4. **Is there a fallback?** For an `Integer` that fails the guards, `case Integer n` handles it; for other types, `default` or another contract must be defined.
5. **Do not treat exceptions as false.** If a helper inside a guard throws an exception, `switch` does not automatically move to the next case as it does when a guard returns Boolean `false`.
6. **How do overlapping guards interact?** The compiler does not prove all relationships between complex Boolean expressions; test boundary values and cases where multiple guards are true.

### Dominance: the compiler can catch shadowed branches

~~~java
// INTENTIONALLY INVALID; input has type Object.
String label = switch (input) {
    case CharSequence text -> "some text";
    case String text -> "string";
    case null -> "missing";
    default -> "other";
};
~~~

`String` is a subtype of `CharSequence`, so `case String text` is covered by the preceding case. The Java 21 compiler rejects the dominated branch.

Similarly:

~~~java
// INTENTIONALLY INVALID; general String branch shadows the guarded branch.
String label = switch (input) {
    case String text -> "text";
    case String text when text.isBlank() -> "blank";
    case null -> "missing";
    default -> "other";
};
~~~

**Fix:** place `case String text when text.isBlank()` before `case String text`, and place specific subtype cases before general supertype cases.

### But the compiler does not solve every logic problem

~~~java
// Java 21+: compiles, but has the wrong classification intent.
String category = switch (input) {
    case Integer n when n > 10 -> "over ten";
    case Integer n when n > 20 -> "over twenty";
    case Integer n -> "other integer";
    case null -> "missing";
    default -> "other";
};
~~~

`25` satisfies both guards, yet it is handled first by `n > 10`. The compiler does not attempt to prove arbitrary mathematical relationships between guards. If values over 20 should be classified separately, place `n > 20` before `n > 10` and **verify at runtime**.

**Guard test checklist:** values just below threshold, at threshold, and just above threshold; guard returning `false`; multiple guards that can all be true; null in reference components; helper throwing an exception if permitted by the contract. Do not test only a single "happy" value.

## 7. Review `sealed` hierarchies and exhaustiveness

A sealed hierarchy controls the permitted set of subtypes:

~~~java
// Java 21+, snippet declared in an appropriate scope.
sealed interface Action permits Create, Cancel {}
record Create(String id) implements Action {}
record Cancel(String id) implements Action {}
~~~

Switch expression:

~~~java
// action has type Action.
String type = switch (action) {
    case Create(var id) -> "create";
    case Cancel(var id) -> "cancel";
    case null -> "missing";
};
~~~

No `default` is needed because all subtypes are handled, and `case null` handles a null selector per the example's policy. If a new permitted subtype is added without updating the switch, the compiler can report **non-exhaustive** on recompile.

**Two common misconceptions:**

- **`null` is not a permitted subtype.** An exhaustive switch over sealed subtypes can compile **without `case null`**, but a null selector can still throw `NullPointerException` at runtime if not explicitly handled. Thus "the compiler says exhaustive" does not mean "null-safe".
- **`default` can hide missing subtypes.** A `default -> "other"` provides a fallback branch, but it can prevent adding a subtype from producing a compile-time signal requiring the new variant to be handled. Use it when you genuinely have an unknown/fallback policy, not just to make the build green.

For a sealed hierarchy with a `non-sealed` branch or other extension contracts, examine the exact permitted types and coverage. Never assume every interface with the `sealed` keyword has the same closed set of concrete branches.

**Sealed switch review checklist:**

- [ ] Is the set of variants truly closed, or do external plugins need to extend it?
- [ ] Does every existing subtype have an appropriate handling branch?
- [ ] Is there a `null` branch if null is valid, or is null proactively rejected?
- [ ] Is there a `default`? If so, why is a fallback more important than the compiler catching missing subtypes?
- [ ] When a new subtype is added, are there compile-time regression tests and runtime tests to verify behavior?
- [ ] Is there a broad case like `case Action a` shadowing subsequent specific cases?

## 8. A Java 21+ program to test 11 runtime scenarios

The example below **intentionally uses a small model** to test multiple pattern-matching rules in a single file, without needing JUnit, Spring, or any external library beyond the JDK.

The sample domain has two command types: `Create` and `Ship`. `Ship` contains `Customer`, which contains `Address`. Guards check IDs and city data; fallbacks handle incomplete commands. This is an **illustrative classification model**, not a production shipping system.

Create the file **`PatternReviewChecklistDemo.java`**:

~~~java
public class PatternReviewChecklistDemo {
    sealed interface Command permits Create, Ship {}

    record Create(String orderId, int units) implements Command {}
    record Address(String city) {}
    record Customer(String id, Address address) {}
    record Ship(String orderId, Customer customer) implements Command {}

    static boolean hasText(String text) {
        return text != null && !text.isBlank();
    }

    static String route(Command command) {
        return switch (command) {
            case Create(var id, var units)
                    when hasText(id) && units > 0 ->
                    "CREATE:" + id + ":" + units;

            case Create(var id, var units) -> "REJECT_CREATE";

            case Ship(var id, Customer(var customerId, Address(var city)))
                    when hasText(id) && hasText(customerId) && hasText(city) ->
                    "SHIP:" + id + ":" + city;

            case Ship(var id, var customer) -> "REJECT_SHIP";

            case null -> "MISSING";
        };
    }

    static void verify(String label, Command input, String expected) {
        String actual = route(input);
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        System.out.println(label + "=" + actual);
    }

    public static void main(String[] args) {
        verify("create-valid", new Create("O-1", 2), "CREATE:O-1:2");
        verify("create-zero", new Create("O-2", 0), "REJECT_CREATE");
        verify("create-blank-id", new Create("  ", 3), "REJECT_CREATE");

        verify("ship-valid",
                new Ship("O-3", new Customer("C-1", new Address("Hue"))),
                "SHIP:O-3:Hue");

        verify("ship-null-customer",
                new Ship("O-3", null), "REJECT_SHIP");

        verify("ship-null-address",
                new Ship("O-3", new Customer("C-2", null)),
                "REJECT_SHIP");

        verify("ship-blank-city",
                new Ship("O-3", new Customer("C-3", new Address("  "))),
                "REJECT_SHIP");

        verify("ship-null-city",
                new Ship("O-3", new Customer("C-3", new Address(null))),
                "REJECT_SHIP");

        verify("ship-blank-customer-id",
                new Ship("O-3", new Customer(" ", new Address("Hue"))),
                "REJECT_SHIP");

        verify("ship-null-order-id",
                new Ship(null, new Customer("C-1", new Address("Hue"))),
                "REJECT_SHIP");

        verify("null-selector", null, "MISSING");
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac --release 21 -encoding UTF-8 PatternReviewChecklistDemo.java
java PatternReviewChecklistDemo
~~~

Verified output:

~~~text
create-valid=CREATE:O-1:2
create-zero=REJECT_CREATE
create-blank-id=REJECT_CREATE
ship-valid=SHIP:O-3:Hue
ship-null-customer=REJECT_SHIP
ship-null-address=REJECT_SHIP
ship-blank-city=REJECT_SHIP
ship-null-city=REJECT_SHIP
ship-blank-customer-id=REJECT_SHIP
ship-null-order-id=REJECT_SHIP
null-selector=MISSING
~~~

### Why use `verify(...)` instead of just printing results?

Each call has a clear **expected output**. If `route` returns a different result, `verify` throws `AssertionError`, preventing the test from completing normally. There is no need to pass `-ea` because we **explicitly throw `AssertionError`**, unlike Java's `assert` statement which can be disabled when assertions are not enabled.

In CI, run the program and check the exit code: a failing test must fail the job. Printing to stdout helps **trace execution paths**, while assertions handle **verification**.

### Why are there two `Create` cases?

`case Create(var id, var units) when hasText(id) && units > 0` is the valid branch. The unguarded `Create` branch after it catches `units <= 0` or blank/null IDs. If the unguarded branch were placed first, the guarded branch after it would be dominated.

### Why are there multiple `Ship` scenarios?

`Ship(var id, Customer(var customerId, Address(var city)))` requires both `Customer` and `Address` to be non-null. However, `new Address(null)` can still be constructed under this record declaration; the nested pattern matches **structurally**, and then the `hasText(city)` guard returns false. That differs from `new Customer("C-2", null)`, where the nested `Address(...)` fails to match at the structural step.

### What do these tests not cover?

These 11 tests illustrate core rules; they do **not** prove a shipping system is safe. They do not test order existence, user authentication, order state, authorization, real addresses, concurrency, databases, retries, or idempotency. Those require **separate integration/domain tests** when real business logic is involved.

## 9. Test matrix: turning the checklist into test cases

When testing a method that uses pattern `switch`, do not write tests by counting `case` lines; instead, identify the **distinct matching paths**.

| Test group | Typical input | Expectation to assert |
| --- | --- | --- |
| Type pattern match | Value with matching runtime subtype | Branch is selected; pattern variable has the expected value |
| Type pattern non-match | Different runtime type | Fallback/other branch is selected |
| Selector `null` | `null` | `case null` policy or explicit exception |
| Nested component `null` | `Ship(..., null)` | Nested record does not match; fallback works |
| Component inside nested record `null` | `Address(null)` | `var` binds null and guard/validation decides |
| Guard true | Valid ID, positive units | Guarded branch |
| Guard false | Blank ID, zero units | Subsequent/fallback branch |
| Boundary conditions | `-1, 0, 1` or exact threshold | Correct classification on both sides of the boundary |
| Multiple guards true | Value satisfying multiple thresholds | Priority branch selected in the right order |
| New sealed subtype | Added permitted variant | Compile-time or runtime regression catches missing handling |
| Record component reordered/resized | Modified record declaration | Compiler and semantic tests catch mismatches |
| Helper throws error | Data or dependency triggers exception | Exception path follows contract; not silently treated as guard false |
| Custom accessor | Accessor with observable logic | No accidental reliance on invocation count |
| Side effects | Mock repository/payment/notification | No writes/charges just to select a branch |
| Toolchain | Build with real target | Source/API and runtime compatibility |

You do not need to test the full Cartesian product of all cases in a very large system; choose **representatives for each branch and each risk boundary**, then expand based on domain properties.

### Partitioning and boundary-value testing

For `units > 0`, partition values into negative, zero, and positive; test at least `-1`, `0`, and `1`. For `amount >= 10_000`, test `9_999`, `10_000`, and `10_001`. If a guard contains multiple conditions, test each condition failing independently before testing combinations where multiple conditions fail together.

### When multiple guards overlap

If `when n >= 100` precedes `when n > 0`, testing `n=101` confirms the first branch takes priority; testing `n=1` confirms the second branch still receives its valid values. **Compile success does not prove business ordering is correct**.

## 10. Compile-failure tests for dominance and exhaustiveness

Some pattern-matching rules should be tested at **compile time**, rather than trying to run source code that the compiler must reject.

### Case 1 — dominated case

~~~java
// INTENTIONALLY INVALID, Java 21+, selector has type Object.
String kind = switch (input) {
    case CharSequence text -> "text";
    case String text -> "string";
    case null -> "null";
    default -> "other";
};
~~~

Reason: `case CharSequence` already covers `String`. The compiler must reject the dominated `case String` branch.

### Case 2 — non-exhaustive sealed switch

~~~java
// INTENTIONALLY INVALID: only one of two subtypes is handled.
sealed interface Action permits Open, Close {}
record Open() implements Action {}
record Close() implements Action {}

static String describe(Action input) {
    return switch (input) {
        case Open() -> "open";
        // Missing Close().
    };
}
~~~

Reason: the `switch expression` does not cover all subtypes of `Action`. **This is an exhaustiveness error, not a dominance error**.

### Case 3 — positive control

~~~java
// VALID when placed in an appropriate class/scope.
static String describe(Action input) {
    return switch (input) {
        case Open() -> "open";
        case Close() -> "close";
        case null -> "missing";
    };
}
~~~

Case 3 must compile successfully. A **positive control** is important: if every source snippet fails because of a wrong compiler target or missing class, then "the negative test failed" does not necessarily prove the rule under test.

**Warning:** Do not place intentionally invalid examples into `src/main/java` where they break the main build. For automated testing, keep source fixtures separate and invoke the compiler from a test harness.

## 11. Compile verification program using the Java Compiler API

This program uses `javax.tools.JavaCompiler` to compile three independent source snippets **in memory**, without creating a `Sample.java` file for each negative test. It checks:
- Dominance: must be rejected.
- Non-exhaustiveness: must be rejected.
- Positive control: must compile successfully.

To stay focused on the success/failure result, the harness below **does not classify diagnostic codes**. In a high-quality compile-failure test suite, you should also inspect diagnostics to avoid negative tests "passing" due to unrelated syntax errors.

Create the file **`PatternCompileCheckDemo.java`**:

~~~java
public class PatternCompileCheckDemo {
    private static boolean compile(String source) {
        var compiler = javax.tools.ToolProvider.getSystemJavaCompiler();
        var diagnostics = new javax.tools.DiagnosticCollector<
                javax.tools.JavaFileObject>();

        var file = new javax.tools.SimpleJavaFileObject(
                java.net.URI.create("string:///Sample.java"),
                javax.tools.JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignored) {
                return source;
            }
        };

        try (var standard = compiler.getStandardFileManager(
                diagnostics, java.util.Locale.ROOT,
                java.nio.charset.StandardCharsets.UTF_8)) {
            var memory = new javax.tools.ForwardingJavaFileManager<
                    javax.tools.StandardJavaFileManager>(standard) {
                @Override
                public javax.tools.JavaFileObject getJavaFileForOutput(
                        Location location, String className,
                        javax.tools.JavaFileObject.Kind kind,
                        javax.tools.FileObject sibling) {
                    return new javax.tools.SimpleJavaFileObject(
                            java.net.URI.create("mem:///"
                                    + className.replace('.', '/')
                                    + kind.extension),
                            kind) {
                        @Override
                        public java.io.OutputStream openOutputStream() {
                            return new java.io.ByteArrayOutputStream();
                        }
                    };
                }
            };

            return Boolean.TRUE.equals(compiler.getTask(
                    null, memory, diagnostics,
                    java.util.List.of("--release", "21", "-proc:none"),
                    null, java.util.List.of(file)).call());
        } catch (java.io.IOException e) {
            throw new java.io.UncheckedIOException(e);
        }
    }

    static void check(String name, boolean result, boolean expected) {
        if (result != expected) {
            throw new AssertionError(name + " expected " + expected
                    + ", got " + result);
        }
        System.out.println(
                name + "=" + (result ? "compiled" : "rejected"));
    }

    public static void main(String[] args) {
        String dominance = """
                public class Sample {
                    static String describe(Object input) {
                        return switch (input) {
                            case CharSequence text -> "text";
                            case String text -> "string";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """;

        String exhaustive = """
                public class Sample {
                    sealed interface Action permits Open, Close {}
                    record Open() implements Action {}
                    record Close() implements Action {}
                    static String describe(Action input) {
                        return switch (input) {
                            case Open() -> "open";
                        };
                    }
                }
                """;

        String valid = """
                public class Sample {
                    sealed interface Action permits Open, Close {}
                    record Open() implements Action {}
                    record Close() implements Action {}
                    static String describe(Action input) {
                        return switch (input) {
                            case Open() -> "open";
                            case Close() -> "close";
                            case null -> "missing";
                        };
                    }
                }
                """;

        check("dominance", compile(dominance), false);
        check("non-exhaustive", compile(exhaustive), false);
        check("valid exhaustive", compile(valid), true);
    }
}
~~~

Compile and run with **JDK 21 or later**:

~~~bash
javac --release 21 -encoding UTF-8 PatternCompileCheckDemo.java
java PatternCompileCheckDemo
~~~

Verified output:

~~~text
dominance=rejected
non-exhaustive=rejected
valid exhaustive=compiled
~~~

### Points to review in compiler tests

- `--release 21` requires the JDK running the compiler to support the Java 21 target.
- `ToolProvider.getSystemJavaCompiler()` requires an environment with a compiler, typically a **JDK**, not a runtime that omits compilation tools.
- `SimpleJavaFileObject` supplies source from a string; `ForwardingJavaFileManager` captures output in `ByteArrayOutputStream` so the build directory stays clean.
- Each fixture uses the class name `Sample`, but is compiled in a separate task so there is no need to rename files per test.
- `false` only confirms **compilation failed**. For rigorous negative tests, use `DiagnosticCollector` to also check the dominance or non-exhaustiveness error code/location.
- `javac` diagnostic codes and error wording **should not be treated as a stable API across all compilers/JDKs**. If you pin the JDK in CI, you can assert a specific set of codes verified for that version; avoid coupling to a full English error message.
- A test suite needs a **positive control** to catch cases where every compile attempt fails due to environment setup.

If you want to check each case in the console, you can put a complete snippet in a separate file, run `javac --release 21 ...`, and inspect the exit code and diagnostics. Do not treat an arbitrary failed `javac` command as conclusive proof of dominance.

## 12. Comparing behavior before and after refactoring

A PR often converts legacy code like:

~~~java
// Legacy Java snippet, selector has type Object.
if (input instanceof String) {
    String text = (String) input;
    return text.trim();
}
return "Other";
~~~

to:

~~~java
// Java 16+, snippet inside a method returning String.
if (input instanceof String text) {
    return text.trim();
}
return "Other";
~~~

This is a small refactor; all execution paths must still be preserved:

| Input | Before | After | Expectation |
| --- | --- | --- | --- |
| `"  A  "` | `"A"` | `"A"` | Equivalent |
| `""` | `""` | `""` | Do not add validation unless requested |
| `42` | `"Other"` | `"Other"` | Equivalent |
| `null` | `"Other"` | `"Other"` | Equivalent |

For larger refactors (`if/else` → `switch`; casts → nested deconstruction), build a before-and-after test table covering **non-matching cases** and **branch priority order**. A change meant to "make code shorter" can accidentally alter an exception, drop a validation step, or turn a null case into a new fallback.

**Review recommendation:** separate syntax-refactoring PRs from business-logic PRs when possible. If both must change together, clearly document which parts are expected to preserve behavior and which parts intentionally change behavior, with separate tests for each.

## 13. From unit tests to integration tests

Not every risk can be caught by a single test layer.

### Pure unit tests

Use for:
- Classification by runtime type and record shape.
- Selecting `when`-guarded cases at boundary values.
- Handling null selectors and null components.
- Verifying results from a `switch expression`.

You can use a `verify(...)` harness like Section 8 or your project's unit-testing framework. With JUnit 5, you can write parameterized tests; however, **you do not need JUnit to understand the essence of pattern matching**. If using real JUnit, declare the dependency and version according to your project build.

### Integration tests

Needed when patterns are used at boundaries:
- JSON deserialization into multiple record subtypes.
- HTTP requests or events from a message broker with new variants.
- Persistence and schema evolution.
- Authorization, policies, transactions, or retries.
- Libraries compiled at a different Java target than the runtime JVM.

These issues **are not automatically solved** by `case Record(...)` or sealed hierarchies. For example, a `record` does not automatically provide a polymorphic JSON discriminator; the serializer still needs its own configuration/contract.

### Property-based and metamorphic tests

For classifiers with simple conditions, you can test properties such as:

> For all `Create(id, units)` where `id` has content and `units > 0`, the result must start with `"CREATE:"`; for `units <= 0`, the result must be `"REJECT_CREATE"`.

This is a **property specification**, not executed source code. Property-based testing tools can generate many inputs to uncover boundary values or unusual Unicode strings. Keep invariants faithful to the contract; do not write properties broader than the intended behavior.

### Mutation tests

You can intentionally change `units > 0` to `units >= 0`. If the test suite includes `units == 0`, the mutation will be caught. Similarly, swapping the order of two guards or removing a null fallback helps evaluate how well the test suite protects branch logic. You do not need to deploy a mutation-testing framework to apply the principle: **every critical condition must have tests that distinguish true from false**.

## 14. Guard and accessor quality in code review

An appropriate guard:

~~~java
// Snippet; id and count come from the matched pattern.
when id != null && !id.isBlank() && count > 0
~~~

A risky guard:

~~~java
// ANTI-PATTERN, illustrates the idea only, not standalone source.
case PayOrder(var id, var amount)
        when paymentGateway.charge(id, amount) -> "Paid";
~~~

If `charge` affects external systems, it can run while Java **is evaluating the condition**, even if the guard returns `false` and moves on to a later case. `switch` does not roll back that action. Separate **pure classification/validation** from **execution with side effects** in a service/handler with a clear contract.

Record accessors should also be simple and consistent. A custom accessor can be called during deconstruction; if execution evaluates multiple patterns before selecting a branch, component reads may be repeated. Do not hide state updates inside an accessor and then write tests assuming "deconstruction always calls each getter only once".

**Additional exception-path review:** if a helper in a guard or accessor throws an exception, `switch` can complete abruptly. That is not "guard false". Test exceptions when they carry business meaning, and do not catch and swallow them just to make a test pass.

## 15. CI checklist for modules using Java Pattern Matching

A minimal pipeline typically needs:

1. Select the **exact JDK** (for example, JDK 21) and log the version.
2. Use the Maven/Gradle **wrapper** instead of relying on a local machine's tool version.
3. Build from a clean output directory with the right source/release target.
4. Run unit tests covering `null`, guards, branches, and nested record shapes.
5. Run compile-failure and compile-success tests for documented rules, using a controlled compiler version.
6. Run necessary integration tests for serializers, DB, policies, and runtime.
7. If publishing a library, verify class-file target and dependency compatibility.
8. Report clearly which test case failed; do not lump all compiler errors into a single "pattern matching failed" bucket.

Example local commands for the two programs in this article:

~~~bash
javac --release 21 -encoding UTF-8 PatternReviewChecklistDemo.java
java PatternReviewChecklistDemo

javac --release 21 -encoding UTF-8 PatternCompileCheckDemo.java
java PatternCompileCheckDemo
~~~

If using Maven Wrapper:

~~~bash
./mvnw -B -ntp clean verify
~~~

If using Gradle Wrapper:

~~~bash
./gradlew --no-daemon clean test
~~~

The wrapper commands only apply when the repository has the corresponding build configuration. Do not assume they guarantee the test framework ran every compiler fixture: compile-failure test suites must be **explicitly integrated** into the build.

### A short PR report template you can use

~~~text
Target Java: 21
Changes: instanceof/cast -> record pattern + switch expression
Contracts preserved: output for null selector and null nested component
Guards: pure conditions, no I/O
Exhaustiveness: sealed hierarchy, no default hiding new subtypes
Verified: compile success, match/non-match paths, boundaries,
          guard false, null, fallback, relevant exceptions
Remaining risks: dependency/serialization/integration (if any)
~~~

This is a **PR description template**, not a configuration file. Reviewers should be able to read it and know **which behaviors are likely affected**.

## 16. Common testing mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Testing only the happy path | Misses guard false, null components, and fallbacks | Build a match/fail path matrix |
| Checking only compile success | Branch priority or business logic can still be wrong | Add runtime boundary tests |
| Negative test checks only `!compiled` | False positives from syntax/classpath errors | Verify diagnostics and positive control |
| Testing dominance on `Object` without `default` | Unrelated exhaustiveness error may appear | Keep fixtures minimal and valid aside from the intended error |
| Testing selector `null`, skipping component `null` | Misses nested pattern failures | Test both kinds of null |
| Confusing `var` with a non-null component check | Accepts or rejects unintended data | Write null-component and guard tests |
| Skipping exact threshold values | Misses `>` vs `>=` bugs | Test just below, at, and just above threshold |
| Using `default` in every sealed switch | Can hide missing subtypes later | Review the exhaustiveness strategy |
| Using Java `assert` without `-ea` | Assertions do not run in tests | Use a framework/`AssertionError` or pass `-ea` explicitly |
| Over-mocking a pure classifier | Hard-to-read tests coupled to implementation | Assert outputs from inputs |
| Performing I/O in guards | Branch testing triggers side effects | Separate decision from execution |
| Measuring only line coverage | Lines execute while branches/guards remain untested | Use branch/boundary coverage and a case matrix |
| Using a newer IDE JDK with an older CI JDK | Builds fail outside local environments | Pin toolchain and target in CI |
| Mixing syntax changes with business-rule changes | Hard to tell where a regression came from | Split PRs or write tests specifying each change |

## 17. Self-practice exercises and answers

### Exercise 1 — Designing three `instanceof` tests

Given the method:

~~~java
// Java 16+, snippet inside an appropriate class/method.
static String normalize(Object input) {
    if (input instanceof String text) {
        return text.trim();
    }
    return "Other";
}
~~~

Choose three inputs to protect the contract.

**Answer:** `"  A  "` expecting `"A"`; `42` expecting `"Other"`; `null` expecting `"Other"`. You can also add `""` to prove the method does not alter empty-string policy.

### Exercise 2 — Distinguishing two kinds of record null

With `record Container(RecordItem item) {}` and `record RecordItem(String code) {}`, predict which branch is selected when `input = new Container(null)` and when `input = new Container(new RecordItem(null))`:

~~~java
String result = switch (input) {
    case Container(RecordItem(var code)) -> "Record " + code;
    case Container(var item) -> "Incomplete";
    case null -> "Missing";
    default -> "Other";
};
~~~

**Answer:** `Container(null)` selects `"Incomplete"` because the nested record does not match. `Container(RecordItem(null))` selects the first branch and produces `"Record null"` because `var code` binds null; if undesirable, add a `code != null` guard or validation.

### Exercise 3 — Order of guarded cases

~~~java
// INTENTIONALLY INVALID: broad String branch comes first.
String label = switch (input) {
    case String s -> "text";
    case String s when s.isBlank() -> "blank";
    case null -> "null";
    default -> "other";
};
~~~

**Answer:** The second branch is dominated; place `case String s when s.isBlank()` before `case String s`. Add runtime tests for `"   "` and `"A"` for the fixed version.

### Exercise 4 — Which test needs the compiler, and which needs runtime?

A `switch expression` over sealed `Action` is missing the `Close` subtype; another `switch` has two guards `n > 3` and `n > 5` in the wrong order. Which tool fits each?

**Answer:** The missing subtype is an **exhaustiveness** error requiring a compile-failure test. Mathematically misordered guards can still compile; they need **runtime behavior tests** with values like `n=6` plus logic review.

### Exercise 5 — Finding a weakness in a test suite

A suite only tests `Create("O-1", 1)`. The code is changed from `units > 0` to `units >= 0` and the suite still passes. Why?

**Answer:** There is no boundary test for `units == 0`. Add `Create("O-2", 0)` expecting `REJECT_CREATE`; you can also add `-1` and a positive value to distinguish all three partitions.

### Exercise 6 — Should a guard write an audit log?

A reviewer sees:

~~~java
// Illustrates the idea only.
case Ship(var id, var customer) when auditAndCheck(id) -> ...
~~~

`auditAndCheck` writes an audit record and returns a Boolean. What should be done?

**Answer:** Request separating the **decision predicate** from the **audit write action**. A false guard does not roll back side effects; fallback branches and retries can cause unintended writes. If auditing is a system requirement, place it in the processing flow with an explicit policy, not hidden inside a condition.

### Exercise 7 — `default` and extending a sealed hierarchy

A sealed `switch` currently handles `Create`, `Ship`, and has `default -> "other"`. The team adds `Refund`. Will the compiler definitely require adding a `Refund` branch?

**Answer:** No. `default` covers the remaining cases, so it can mask the requirement to handle the new variant. If the goal is to force the code to account for new subtypes at build time, avoid `default` and write explicit exhaustive cases.

## 18. Final checklist for reviewers

You can copy this checklist into a PR template:

- [ ] **Target:** source/release/JDK/toolchains are specified.
- [ ] **Selector:** static type and possible input values are clear.
- [ ] **Pattern:** type/record/nested patterns are valid; variables bind to the right components.
- [ ] **Scope:** pattern variables are not used outside paths guaranteed to match.
- [ ] **Null:** null selector, null component, and blank/empty payload are considered separately.
- [ ] **Guard:** conditions and boundaries are right, no hidden side effects; exceptions handled properly.
- [ ] **Dominance:** specific/narrow branches precede broad ones; no case is rejected by the compiler.
- [ ] **Exhaustive:** sealed switch covers all variants; any `default` has a clear reason.
- [ ] **Domain:** constructor/factory validation and business invariants are not mistakenly delegated to patterns.
- [ ] **Readability:** component names are clear; nested patterns are not overly deep; avoid refactoring just for brevity.
- [ ] **Runtime tests:** happy path, non-match, guard false, null, boundaries, fallback.
- [ ] **Compile tests:** negative cases fail for the right reason and include a positive control when needed.
- [ ] **Regression:** before-and-after refactoring preserves the contract or documents intentional changes.
- [ ] **Integration:** serializers, dependencies, I/O, and runtime are tested if within the PR scope.
- [ ] **CI:** tests run via build wrapper and a JVM supporting the target.
- [ ] **Evidence:** author recorded verification commands, test results, and remaining risks.

## 19. Takeaways and official references

**Reviewing pattern matching means reviewing a branching decision**, not just reviewing `case` syntax. The compiler enforces constraints like scope, dominance, and exhaustiveness; runtime tests verify `null`, guards, boundary data, and branch priority; and code review protects invariants, side effects, and maintainability.

When unsure what else to test, ask: **"Is there any other kind of input that causes the program to take a different matching path?"**. If so, consider adding a representative of that kind. Whenever you add a subtype, change a record structure, or reorder cases, re-run **both compile tests and behavior tests**.

**Official references:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [Java Language Specification SE 21 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [JavaCompiler API (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html).
