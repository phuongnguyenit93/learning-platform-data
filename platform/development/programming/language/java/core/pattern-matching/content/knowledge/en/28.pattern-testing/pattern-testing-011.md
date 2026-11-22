# Property-based testing for patterns in Java 21+

## 1. What does property-based testing test?

**Property-based testing (PBT)** is a method of writing **properties that must hold for a large set of inputs**, then letting a data generator produce many cases to search for a **counterexample**. Instead of checking only three fixed examples, we state propositions such as:

- For every `Parcel` of a valid type, the pattern-based classification function must agree with the independent business specification.
- Changing the tracking ID (`trackingId`) must not change the shipping tier if the tier depends only on weight and valid destination information.
- With a valid destination, a parcel weighing exactly **5,000 g** still belongs to `STANDARD`; starting from **5,001 g** it becomes `HEAVY`.
- With a `null` selector or record component, the result must follow the defined policy; it must not silently fall into an unintended `MatchException`.
- Adding a subtype to a sealed hierarchy must not create an unhandled state that tests fail to detect.

This is a testing approach particularly well suited to **pattern matching** because the outcome depends simultaneously on:

1. **Type and structure**: `String`, `Integer`, sealed subtypes, records, and nested record patterns.
2. **Constraints in patterns**: which components are deconstructed, and which values can be `null`.
3. **`when` guards**: Boolean expressions, `>`/`>=` boundaries, and short-circuit evaluation order.
4. **`switch` branch order**: specific patterns, guards, and fallback branches.
5. **Exhaustiveness and domain changes**: whether all subtypes have been covered.

**Do not confuse PBT with a random smoke test.** A test that merely generates data and calls a method without an assertion checking correctness is not useful PBT. A property must be independent and carry business meaning.

**Java version:** Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) became standard in **Java 21**. The sample code runs on JDK 21+ without `--enable-preview`. The section using `java.util.Random` requires no external framework; the final section introduces how to write true properties using **jqwik** on the JUnit Platform, with shrinking support.

## 2. Translating domain rules into properties

Suppose we have a parcel classification system:

```java
sealed interface Parcel permits Physical, Digital, Unknown {}
record City(String name) {}
record Physical(String trackingId, City city, int grams)
        implements Parcel {}
record Digital(String trackingId, String email)
        implements Parcel {}
record Unknown() implements Parcel {}
```

Business contract:

| Type / input | Rule | Result |
| --- | --- | --- |
| `Physical` | City exists, name is not `null`/blank, `grams > 5_000` | `HEAVY` |
| `Physical` | City exists, name is not `null`/blank, `1 <= grams <= 5_000` | `STANDARD` |
| `Physical` | Invalid City or `grams <= 0` | `INVALID_PHYSICAL` |
| `Digital` | Email is non-`null` and contains `@` (simple rule for the example) | `DIGITAL` |
| `Digital` | Email is missing `@` or is `null` | `INVALID_DIGITAL` |
| `Unknown` | No specific rule | `UNKNOWN` |
| `null` selector | No parcel | `MISSING` |

*Note:* checking email with `contains("@")` is only an illustrative assumption, **not a complete email validator**. Tests should use the exact **published domain contract**, rather than treating a demo rule as a universal standard.

From the table above, create a suite of properties across independent levels:

- **Oracle / differential property:** `classify(parcel) == reference(parcel)` across all generated values, where `reference` is an independent, readable implementation derived from the contract.
- **Boundary property:** exactly 5,000 g is `STANDARD`, 5,001 g is `HEAVY`; zero or negative weight is invalid.
- **Metamorphic property:** changing `trackingId` (and changing one valid City name to another valid City name) does not change the tier when the weight remains the same.
- **Null/shape property:** `Physical(null-city)`, `Physical(City(null))`, and `Physical(City(" "))` take the `INVALID_PHYSICAL` branch; a `null` selector takes `MISSING`.
- **No-unexpected-exception property:** for inputs within the domain permitted by the contract, `classify` must not throw unexpected exceptions.

Not every property needs to be written as an output comparison identical to the switch. Metamorphic, invariant, and boundary propositions help uncover bugs **even when the oracle shares the same flaw as the implementation**.

## 3. Data generators need to know the pattern branches

Uniform random generation over all `int` values often misses the values that need testing most: **0, 1, 5,000, and 5,001**. Similarly, random character generation may rarely produce `null`, empty strings, or blank strings.

For `Parcel`, generate **structure first, values second**:

1. Choose a case: `null` selector, `Physical`, `Digital`, or `Unknown`.
2. If `Physical`, decide whether to create a `City`; if so, pick `City.name` from `null`, empty, blank, and valid names.
3. Generate `grams` as a mix of: **boundary values** `-1, 0, 1, 4_999, 5_000, 5_001`, extreme values, and random numbers in a representative range.
4. If `Digital`, generate `null`, empty, missing-`@`, or `@`-containing emails.
5. Ensure failing runs can be reproduced using a **seed**, and when using a PBT framework, leverage **shrinking** to minimize the failing input.

**Why weight each category?** A generator with a poor distribution might produce 99% `Unknown`, leaving the `Physical` guard branches barely tested. Monitor distribution (classification statistics) and tune the generator so important branches are hit frequently enough.

**Both valid and invalid inputs matter:** If the domain forbids a `null` `City` in the constructor, the happy-path test generator should not create that state. However, API tests receiving unvalidated data or deserialization still need malformed inputs at the **system boundary**. Keep these two datasets distinct so tests do not contradict the model's invariants.

## 4. Complete, runnable Java 21 program

The following program tests across three layers: **12 boundary examples**, **20,000 randomly generated inputs compared against an oracle**, and **5,000 metamorphic checks**. No external libraries are needed.

Save the file as **`ParcelPatternPropertyDemo.java`**:

```java
public class ParcelPatternPropertyDemo {
    sealed interface Parcel permits Physical, Digital, Unknown {}

    record City(String name) {}

    record Physical(String trackingId, City city, int grams)
            implements Parcel {}

    record Digital(String trackingId, String email)
            implements Parcel {}

    record Unknown() implements Parcel {}

    // System under test: nested record pattern + when guards.
    static String classify(Parcel parcel) {
        return switch (parcel) {
            case Physical(var id, City(String city), int grams)
                    when grams > 5_000
                            && city != null && !city.isBlank() ->
                    "HEAVY";

            case Physical(var id, City(String city), int grams)
                    when grams > 0
                            && city != null && !city.isBlank() ->
                    "STANDARD";

            case Physical(var id, var city, var grams) ->
                    "INVALID_PHYSICAL";

            case Digital(var id, var email)
                    when email != null && email.contains("@") ->
                    "DIGITAL";

            case Digital(var id, var email) ->
                    "INVALID_DIGITAL";

            case Unknown unknown -> "UNKNOWN";
            case null -> "MISSING";
        };
    }

    // Independent oracle: does not use nested record patterns/when.
    // Written from the contract table to provide a second verification path.
    static String reference(Parcel parcel) {
        if (parcel == null) {
            return "MISSING";
        }

        if (parcel instanceof Physical physical) {
            City city = physical.city();

            if (city == null || city.name() == null ||
                    city.name().isBlank() || physical.grams() <= 0) {
                return "INVALID_PHYSICAL";
            }

            return physical.grams() > 5_000
                    ? "HEAVY" : "STANDARD";
        }

        if (parcel instanceof Digital digital) {
            return digital.email() != null
                    && digital.email().contains("@")
                            ? "DIGITAL" : "INVALID_DIGITAL";
        }

        if (parcel instanceof Unknown) {
            return "UNKNOWN";
        }

        throw new AssertionError("Unknown Parcel implementation");
    }

    static void assertEqual(
            String expected, String actual, Object value) {
        if (!java.util.Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "value=" + value + " expected=" + expected
                            + " actual=" + actual);
        }
    }

    // Generator biased toward producing boundary types and values.
    static Parcel generate(java.util.Random random) {
        String[] cities = {
                null, "", " ", "HCM", "Huế", "Hà Nội"
        };

        String[] emails = {
                null, "", "no-at-sign", "a@b", "person@example.com"
        };

        int[] edges = {
                -1, 0, 1, 4_999, 5_000, 5_001,
                Integer.MIN_VALUE, Integer.MAX_VALUE
        };

        int grams = random.nextBoolean()
                ? edges[random.nextInt(edges.length)]
                : random.nextInt(20_001) - 10_000;

        String id = "P" + random.nextInt(100);

        return switch (random.nextInt(6)) {
            case 0 -> null;

            case 1, 2, 3 -> new Physical(
                    id,
                    random.nextInt(5) == 0
                            ? null
                            : new City(
                                    cities[random.nextInt(cities.length)]),
                    grams);

            case 4 -> new Digital(
                    id,
                    emails[random.nextInt(emails.length)]);

            default -> new Unknown();
        };
    }

    public static void main(String[] args) {
        Parcel[] boundaries = {
                new Physical("A", new City("HCM"), 5_000),
                new Physical("A", new City("HCM"), 5_001),
                new Physical("A", new City("HCM"), 1),
                new Physical("A", new City("HCM"), 0),
                new Physical("A", new City("HCM"), -1),
                new Physical("A", null, 10),
                new Physical("A", new City(null), 10),
                new Physical("A", new City(" "), 10),
                new Digital("D", "a@b"),
                new Digital("D", null),
                new Unknown(),
                null
        };

        String[] expected = {
                "STANDARD", "HEAVY", "STANDARD",
                "INVALID_PHYSICAL", "INVALID_PHYSICAL",
                "INVALID_PHYSICAL", "INVALID_PHYSICAL",
                "INVALID_PHYSICAL", "DIGITAL",
                "INVALID_DIGITAL", "UNKNOWN", "MISSING"
        };

        for (int i = 0; i < boundaries.length; i++) {
            assertEqual(
                    expected[i], classify(boundaries[i]), boundaries[i]);
        }
        System.out.println("boundaries=12 PASS");

        final long seed = 24_301L;
        java.util.Random random = new java.util.Random(seed);

        for (int i = 0; i < 20_000; i++) {
            Parcel input = generate(random);
            assertEqual(reference(input), classify(input), input);
        }
        System.out.println(
                "differential=20000 PASS (seed=" + seed + ")");

        // Metamorphic: trackingId and valid City name do not
        // change the tier for the same positive weight.
        java.util.Random metamorphicRandom =
                new java.util.Random(seed + 1);

        for (int i = 0; i < 5_000; i++) {
            int grams = 1 + metamorphicRandom.nextInt(10_000);
            Parcel original = new Physical(
                    "ID-A", new City("HCM"), grams);
            Parcel renamed = new Physical(
                    "ID-B", new City("Huế"), grams);

            assertEqual(
                    classify(original), classify(renamed), renamed);
        }
        System.out.println("metamorphic=5000 PASS");
    }
}
```

Compile and run:

```bash
javac --release 21 ParcelPatternPropertyDemo.java
java ParcelPatternPropertyDemo
```

**Exact stdout:**

```text
boundaries=12 PASS
differential=20000 PASS (seed=24301)
metamorphic=5000 PASS
```

The program was tested on JDK 24 using Java 21 syntax. This section uses **hand-rolled randomized property checks** to provide a pure-JDK runnable example. It **does not automatically shrink** counterexamples; a dedicated framework like jqwik provides that mechanism.

### 4.1. Explaining nested record branches and null data

The first two branches use:

```java
case Physical(var id, City(String city), int grams)
        when grams > 5_000 && city != null && !city.isBlank() ->
        "HEAVY";
```

`City(String city)` matches only when the `City` component is actually a `City` record, **not when `City` itself is `null`**. However, `City` can exist and contain `name == null`; the guard checking `city != null` handles that case.

The third branch:

```java
case Physical(var id, var city, var grams) -> "INVALID_PHYSICAL";
```

is the fallback branch for `Physical` instances that fail the two guards above, including a `null` `City`, blank `City`, and non-positive weight. This branch is placed **after** the specific branches; if placed before them, it would cover other `Physical` cases and cause the branches above to be dominated.

### 4.2. Why have both fixed example tests and random tests?

Property-based testing **complements**, rather than replaces, example-based testing. Fixed cases prove that critical boundaries are explicitly asserted (5,000/5,001, `null` at each level) even if the generator happens not to produce them. The random loop explores additional combinations that the author did not enumerate; metamorphic properties catch a different class of regressions than simple oracle output comparisons.

`seed = 24301` reproduces **the exact generation sequence of this code** as long as the generator and random calls remain unchanged. If you modify the generator or the generation algorithm version, the same seed does not necessarily produce the same input sequence. When a bug is found, record the **specific counterexample value** and turn it into a fixed regression test.

## 5. A real PBT framework: jqwik

In a Maven/Gradle project, **jqwik** provides these concepts:

- `@Property`: marks a property test and configures the number of tries.
- `@ForAll`: automatically generated parameter.
- `@Provide` and `Arbitrary<T>`: describe domain generators.
- `Arbitraries.oneOf(...)`: combines boundary-case generators with random distributions.
- **Shrinking:** after finding a failing input, jqwik typically searches for a **simpler** version that still falsifies the property (shrinking capability and quality depend on the generator).

A sample Maven dependency (you can use a compatible version per the [jqwik User Guide](https://jqwik.net/docs/current/user-guide); `1.10.2` is shown below):

```xml
<dependency>
    <groupId>net.jqwik</groupId>
    <artifactId>jqwik</artifactId>
    <version>1.10.2</version>
    <scope>test</scope>
</dependency>
```

The project needs to run tests on the **JUnit Platform**, such as a modern Maven Surefire version, configured for Java 21 compilation. Place the production file at `src/main/java/ParcelPatternPropertyDemo.java` and the property test file at `src/test/java/ParcelPatternProperties.java`; both in the same package (or the same default package for a simple example). In a real project, use an explicit named package.

Example test using jqwik:

```java
import net.jqwik.api.*;
import net.jqwik.api.constraints.IntRange;

class ParcelPatternProperties {

    @Provide
    Arbitrary<Integer> gramsNearBoundary() {
        return Arbitraries.oneOf(
                Arbitraries.of(
                        -1, 0, 1, 4_999, 5_000, 5_001,
                        Integer.MIN_VALUE, Integer.MAX_VALUE),
                Arbitraries.integers().between(-10_000, 10_000));
    }

    @Property(tries = 1_000)
    void resultMatchesReference(
            @ForAll("gramsNearBoundary") int grams) {
        var parcel = new ParcelPatternPropertyDemo.Physical(
                "A", new ParcelPatternPropertyDemo.City("HCM"), grams);

        String expected = ParcelPatternPropertyDemo.reference(parcel);
        String actual = ParcelPatternPropertyDemo.classify(parcel);

        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "grams=" + grams
                            + " expected=" + expected
                            + " actual=" + actual);
        }
    }

    @Property(tries = 500)
    void changingIdAndValidCityDoesNotChangeCategory(
            @ForAll @IntRange(min = 1, max = 10_000) int grams) {
        var first = new ParcelPatternPropertyDemo.Physical(
                "A", new ParcelPatternPropertyDemo.City("HCM"), grams);
        var second = new ParcelPatternPropertyDemo.Physical(
                "B", new ParcelPatternPropertyDemo.City("Huế"), grams);

        String x = ParcelPatternPropertyDemo.classify(first);
        String y = ParcelPatternPropertyDemo.classify(second);

        if (!x.equals(y)) {
            throw new AssertionError("grams=" + grams
                    + " first=" + x + " second=" + y);
        }
    }
}
```

Run according to the project configuration:

```bash
mvn test
```

This is a **framework integration example**; the `ParcelPatternPropertyDemo.java` program in section 4 was executed standalone with the JDK. The jqwik snippet uses APIs per the documentation, but requires a project with the corresponding dependency and test-runner configuration.

**Limitation of the jqwik test above:** the two properties focus on `Physical` with a valid `City`. **They do not yet test all subtypes/`null` cases**, so you need to add a `@Provide` for `Parcel` that generates `Digital`, `Unknown`, a `null` selector, a `null` `City`, and a `null`/blank `City` name. Do not claim "the entire switch has been property-tested" just because these two properties pass.

### 5.1. Designing `Arbitrary<Parcel>` for a sealed hierarchy

An actionable strategy:

- `physicalArbitrary()` combines `trackingId`, `City`, and `grams` using `Combinators.combine(...).as(...)`.
- `digitalArbitrary()` combines an identifier with valid/invalid emails.
- `unknownArbitrary()` uses `Arbitraries.just(new Unknown())`.
- `parcelArbitrary()` uses `Arbitraries.oneOf(physical, digital, unknown)` and then **injectNull** at the selector level if the domain allows `null`.
- Create separate **valid domain** and **invalid input** generators when constructors or schemas have constraints, avoiding excessive filtering via `filter(...)`.

Avoid using `Arbitraries.randomValue(...)` with an ad-hoc generator without understanding its drawback: according to jqwik, values created this way **cannot be shrunk**. For structured record data, prefer composing shrinkable `Arbitrary` instances so counterexamples can be usefully minimized.

### 5.2. Shrinking: from complex input to minimal failing case

Suppose someone replaces `grams > 5_000` with `grams >= 5_000` in the `HEAVY` branch. When running the property:

```java
// Wrong if the contract states only > 5_000 is HEAVY:
case Physical(var id, City(String city), int grams)
        when grams >= 5_000 && city != null && !city.isBlank() ->
        "HEAVY";
```

The boundary test directly catches `new Physical("A", new City("HCM"), 5_000)`: the specification expects `STANDARD`, while the code returns `HEAVY`.

With a generator and framework that support shrinking, jqwik **can** try to reduce a failing input down to a simple boundary value. There is no guarantee it will always shrink to 5,000; the outcome depends on the generator, try order/count, and constraints. When you get a counterexample, record the **specific input + seed + library version**, fix the code, and add a fixed regression test.

## 6. Five high-value property patterns for pattern matching

### 6.1. Agreement with an independent oracle

`classify(input) == reference(input)` can catch wrong guard ordering, missing fallbacks, or mistaken thresholds. However, **avoid copying the switch itself into the oracle**: if both copy the same bug, the test can pass falsely. Write the reference from a domain table, simple expressions, or expected data confirmed by domain stakeholders.

### 6.2. Metamorphic property

When it is hard to know the exact output for a random input, you can still know that a transformation **must not change the result**:

- Changing the identifier does not affect the shipping group.
- For a valid `City`, changing the name from `HCM` to `Huế` does not affect the weight-based group.
- If the domain normalizes letter case, changing the input's case must not change the group (only valid when the contract actually specifies this).

A metamorphic relation requires clear **preconditions**. If `City` is changed to `null` or blank, the "same group" relation no longer holds. Writing a property without its precondition produces false positives.

### 6.3. No unexpected exception / totality

For selectors and record components within the permitted domain, the classification function should complete normally and return one of the valid labels. However, **do not define an overly weak property** like "no exception means PASS": a `default -> "OTHER"` that masks every error will also never throw.

Combine the totality property with an oracle, value-set checks, and boundary testing. For sealed hierarchies or nested record patterns, watch out for `MatchException` when a `null` nested record causes all exhaustive cases to miss, or when a client was compiled against an older set of subtypes.

### 6.4. Exhaustiveness, subtypes, and branch ordering

The Java 21 compiler checks exhaustiveness for `sealed` types, but runtime tests remain valuable for:

- Nullable components inside nested record patterns.
- Two guards that can both be true, where the more specific branch must come first.
- Cases where a child subtype must take precedence over a parent type.
- Specifications with an unguarded branch catching the remainder.

When adding a subtype to a sealed hierarchy, first update the generator to **actually produce the new subtype**, then test the classifier. If you only add a case branch without updating the generator, PBT may never hit the new path.

### 6.5. Regression property against a legacy implementation

When migrating legacy `instanceof + cast` code to a `switch` pattern, the property:

`newVersion(input) == oldVersion(input)`

is useful when **the old behavior is the accepted contract**. Also check `null` handling, exception types, and important side effects, especially when refactoring from manual getter checks to record deconstruction. Identical return values do not prove that two versions match in database writes, events, logs, or exceptions.

Do not run both variants simultaneously against production systems if they have side effects; use isolated tests and appropriate fakes/mocks.

## 7. What PBT cannot guarantee on its own

1. **It does not prove the program correct for all inputs.** 20,000 test cases are finite data, not a formal proof.
2. **It does not automatically guarantee branch coverage.** Increasing `tries` while the generator only creates `Digital` will not test `Physical`.
3. **It cannot rescue a wrong oracle.** You need contract reviews, independent tests, and sometimes mutation testing.
4. **It does not automatically determine the valid data domain.** The generator must reflect invariants/constructors/APIs.
5. **It cannot automatically find every deep state.** Nested records, generic data, and sealed subtypes need structured generators.
6. **It must not be turned into flaky tests.** I/O sources, wall-clock time, and global state can cause random, hard-to-reproduce property failures.
7. **It does not replace specification examples.** Boundaries 0, 1, 5,000, and 5,001 should have explicit tests alongside the generator.
8. **It does not guarantee optimal shrinking.** Data generated by unshrinkable methods or excessive filtering can make counterexamples hard to minimize.
9. **It does not guarantee null-safe matching.** With nested patterns, `null` can appear at multiple levels; you need generators and cases at the right level.

**Therefore:** combine **example-based tests + property-based tests + coverage + specification review**. PBT is strongest when it provides an independent verification angle.

## 8. Process for adopting PBT in a codebase

1. **Pick a pattern-based classification method** with a clear contract: subtype conditions, guards, boundaries, and `null` handling.
2. **Write a decision table**: each input type, condition, expected output, and exception/fallback behavior.
3. **Create regression examples first** for boundaries and past bugs.
4. **Choose properties**: appropriate oracle/differential, metamorphic, and invariant checks. Write the proposition in plain language before encoding it as an assertion.
5. **Build generators around the domain structure**: subtypes, nested records, `null` at each level, boundaries, and invalid data if the API accepts it.
6. **Run with a reproducible seed**, preserving failing inputs. Use a framework with shrinking when datasets are complex.
7. **Read the distribution report**: did every subtype/guard appear often enough? If a branch is unhit, fix the generator or add explicit tests.
8. **Save counterexamples as fixed tests** and fix the implementation. After fixing, re-run the entire suite.
9. **When adding subtypes or changing the domain**, update the specification, generator, properties, and regression tests together.
10. **Keep costs reasonable**: a few hundred/thousand fast tries in CI; very large data generation or expensive integration tests can be moved to a separate schedule.

### Code review checklist for property tests

- [ ] Does the property state the **domain contract**, rather than merely asserting that the implementation equals itself?
- [ ] Does the generator produce all main subtypes and `null` at every nullable level?
- [ ] Are there boundary values for `when` guards and case ordering?
- [ ] Are valid inputs and invalid inputs distinguished?
- [ ] Are there independent tests for `MatchException`/`NullPointerException` if the domain has those error paths?
- [ ] Are the seed, counterexample, and shrink/replay strategy clear?
- [ ] Is the oracle written independently, avoiding algorithm copy-pasting?
- [ ] Do metamorphic relations have proper preconditions, avoiding false positives?
- [ ] Are coverage/distribution metrics observed rather than just counting `tries`?
- [ ] Are tests independent of time, execution order, external systems, and global mutable state?

## 9. Practice exercises

**Exercise 1 — Catch a boundary bug.** Replace `grams > 5_000` with `grams >= 5_000` in `classify`. Run the program: the first boundary test must catch `Physical(..., 5000)`. Restore `>` after the exercise.

**Exercise 2 — Null in nested patterns.** Remove the `case Physical(var id, var city, var grams)` branch and test inputs `Physical(..., null, 10)` and `Physical(..., City(null), 10)`. Consider the compiler's exhaustiveness requirements and runtime behavior. Do not assume that `case null` handles a `null` nested record.

**Exercise 3 — Generate more numeric data.** Include `Integer.MAX_VALUE`/`MIN_VALUE` in the generator (already present), then add a property that avoids overflow-prone arithmetic when checking thresholds. Write an assertion with a message containing the failing input.

**Exercise 4 — Actual coverage.** Count how many times `HEAVY`, `STANDARD`, `INVALID_PHYSICAL`, `DIGITAL`, `INVALID_DIGITAL`, `UNKNOWN`, and `MISSING` occur across 20,000 runs. If any group has 0 samples, adjust the generator or add specific tests.

**Exercise 5 — Migrate to jqwik.** Create an `Arbitrary<Parcel>` combining all subtypes and nullable components, write a `@Property` comparing against `reference`, and then intentionally introduce a threshold bug to observe shrinking/counterexamples.

**Conclusion:** Property-based testing for pattern matching starts with **the contract and input structure**, not a random loop. A good suite models subtypes, nested records, `null`s, guard boundaries, and case ordering, while using **independent oracles**, **metamorphic relations**, and **reproducible counterexamples**. With a framework like jqwik, shrinking helps turn a complex failure into a compact example for debugging and adding a regression test.

### References

- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- jqwik User Guide — Generators, Property, @ForAll, @Provide, Shrinking: https://jqwik.net/docs/current/user-guide
