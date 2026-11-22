# Predicate.not() and Predicate.isEqual() in Java

In Java, **Predicate<T>** represents a condition that takes a value of type T and returns a boolean. Besides writing lambdas manually, the **java.util.function** package provides two very useful static methods when **composing conditions**:

- **Predicate.not(predicate):** creates a predicate whose result is the **negation** of the provided predicate. This method has been available since **Java 11**.
- **Predicate.isEqual(targetRef):** creates a predicate that tests whether an object is **equal** to the target object according to the equals contract; it also supports the case where targetRef is null. This method has been available since **Java 8**.

These two tools help write pipelines with clear intent, such as "remove blank strings", "select elements with a desired value", or "exclude values not equal to X", without necessarily creating manual negating lambdas. This lesson covers syntax, generic inference, relationships with negate/and/or, runnable Java 17 examples, and common mistakes.

## 1. Foundation: What is Predicate<T>?

Predicate<T> is a standard functional interface with a single abstract method:

~~~java
boolean test(T value);
~~~

Example:

~~~java
java.util.function.Predicate<String> longName =
    name -> name.length() >= 4;

System.out.println(longName.test("Java")); // true
System.out.println(longName.test("Go"));   // false
~~~

Predicate has composition default methods like **and**, **or**, **negate** and static methods **not**, **isEqual**. Unlike Function<T,R>, Predicate<T> does not transform a T into an arbitrary data value R; the standard result of test is always boolean.

Distinguish between:

| Component | What does it take? | What does it produce? |
| --- | --- | --- |
| Predicate<T>.test(value) | A T | boolean |
| predicate.negate() | Takes no method parameters | Predicate<T> with inverted result |
| Predicate.not(predicate) | A compatible Predicate | Predicate<T> with inverted result |
| Predicate.isEqual(targetRef) | An object as the reference value | Predicate<T> testing equality with targetRef |
| predicate.and(other) | Another Predicate | Predicate<T> combined with AND |
| predicate.or(other) | Another Predicate | Predicate<T> combined with OR |

**Note:** Predicate.not and Predicate.isEqual are **static factory methods**: they return a predicate object for later use. Calling a predicate-creating method **does not mean** data has been checked yet; condition evaluation happens when test is called or when an API like Stream.filter executes.

## 2. Predicate.not(): negating a predicate

API signature (written in an equivalent form for easier reading):

~~~java
static <T> Predicate<T> not(Predicate<? super T> target);
~~~

The method returns a new predicate whose result is equivalent to **!target.test(value)** for the same value. Example:

~~~java
import java.util.function.Predicate;

Predicate<String> blank = String::isBlank;
Predicate<String> notBlank = Predicate.not(blank);

System.out.println(blank.test("   "));    // true
System.out.println(notBlank.test("   ")); // false
System.out.println(notBlank.test("Java")); // true
~~~

These are illustrative statements inside a method; if placed in a standalone class, class/main declarations must be added. **Predicate.not(blank) does not mutate blank**; both predicates can be used independently.

### 2.1. Why is static not useful with method references?

When filtering non-blank strings, a familiar style is:

~~~java
List<String> kept = values.stream()
    .filter(value -> !value.isBlank())
    .toList();
~~~

Since Java 11, you can use:

~~~java
List<String> kept = values.stream()
    .filter(Predicate.not(String::isBlank))
    .toList();
~~~

The intent "filter non-blank strings" is expressed as the negation of a method reference. In this snippet, **String::isBlank** is an instance method of the object that the predicate receives. The method reference gets a matching target type from the parameter of Predicate.not and Stream.filter.

You can use a static import to shorten it:

~~~java
import static java.util.function.Predicate.not;
~~~

Then:

~~~java
List<String> kept = values.stream()
    .filter(not(String::isBlank))
    .toList();
~~~

In these illustrative snippets, List<String> and values must be declared in an actual program. Choose static import if the name not is clear enough in the codebase; if there are multiple methods with the same name, writing Predicate.not(...) avoids ambiguity.

### 2.2. Comparing not and negate

The two approaches are usually equivalent in logical result:

~~~java
Predicate<Integer> positive = number -> number > 0;
Predicate<Integer> notPositive1 = positive.negate();
Predicate<Integer> notPositive2 = Predicate.not(positive);
~~~

Both return false for 3 and true for 0, -2.

**Differences in expression:**

- **positive.negate()** is convenient when you already have a predicate variable or an expression that clearly returns a predicate.
- **Predicate.not(String::isBlank)** is convenient for directly negating a **method reference**; no intermediate variable is needed.
- **Predicate.not(...)** is a static method, so it reads well in condition compositions and can be statically imported.

Avoid the misconception that not "negates an object" at call time; it **returns a predicate** to negate the results of later test calls. Neither guarantees that the callback is pure, thread-safe, or exception-free.

### 2.3. Null value of the input predicate

~~~java
// Will throw NullPointerException:
Predicate<String> invalid = Predicate.not(null);
~~~

The target predicate itself must be **non-null**. This differs from whether the predicate can **test a null value** at test time: that capability depends on the original predicate.

For example, String::isBlank does not accept a null receiver. Predicate.not(String::isBlank) does not automatically turn isBlank(null) into false; it can still throw NullPointerException on test(null).

If a collection may contain null, handle null explicitly or use a condition that supports null, rather than believing the word not automatically provides null-safety.

## 3. Predicate.isEqual(): creating an equality condition

Conceptual API signature:

~~~java
static <T> Predicate<T> isEqual(Object targetRef);
~~~

targetRef is the **reference value** to compare against. Each time test(candidate) is called, the predicate returns true when the two values are considered equal according to logic corresponding to **Objects.equals(targetRef, candidate)**.

~~~java
Predicate<String> isJava = Predicate.isEqual("Java");

System.out.println(isJava.test("Java")); // true
System.out.println(isJava.test("Go"));   // false
System.out.println(isJava.test(null));   // false
~~~

The key is comparing **equality**, not object address identity. For String, equals normally compares string content, whereas the == operator compares two references (aside from other boxing/primitive cases not relevant here).

### 3.1. Comparison with Objects.equals()

A typical lambda:

~~~java
Predicate<String> isJava =
    candidate -> java.util.Objects.equals("Java", candidate);
~~~

Can be expressed as:

~~~java
Predicate<String> isJava = Predicate.isEqual("Java");
~~~

When evaluated, both return a boolean based on equality comparison. In code with many conditions or pipelines, Predicate.isEqual helps emphasize "the goal is equality with a reference value".

**Distinguishing comparison direction:** Java calls equals on a non-null object in the appropriate position; for classes with an incorrect, asymmetric, or side-effecting equals implementation, comparison direction may matter. Therefore, adhere to the equals contract (especially symmetry, transitivity, consistency) and do not use isEqual as a mechanism to fix a data type's broken equality.

### 3.2. Null values are supported

One of the benefits of isEqual is **handling a null reference**:

~~~java
Predicate<Object> isNull = Predicate.isEqual(null);

System.out.println(isNull.test(null));   // true
System.out.println(isNull.test("abc"));  // false
~~~

With targetRef = null, isEqual creates a predicate that checks whether candidate is null. Therefore:

~~~java
Predicate<Object> nonNull =
    Predicate.not(Predicate.isEqual(null));
~~~

returns true for non-null objects and false for null.

However, when the sole purpose is checking null, writing with a method reference can be clearer:

~~~java
Predicate<Object> isNull = java.util.Objects::isNull;
Predicate<Object> nonNull = java.util.Objects::nonNull;
~~~

Or in a pipeline:

~~~java
values.stream()
    .filter(java.util.Objects::nonNull)
    .toList();
~~~

Do not mistakenly assume Stream.of or List.of allows null: **List.of does not accept null elements**, and Stream.of can create a stream containing null when null elements are provided in the appropriate context. When you need to illustrate a list with null, you can use ArrayList and add(null).

### 3.3. Equality is based on equals, not arbitrary structural comparison

Example:

~~~java
record Point(int x, int y) {}

Predicate<Point> origin = Predicate.isEqual(new Point(0, 0));
System.out.println(origin.test(new Point(0, 0))); // true
~~~

Java records provide equals/hashCode based on components, so the two Points in the example are equal. But if the object is an ordinary class that does not override equals, the equals inherited from Object normally relies on reference identity. isEqual **does not** automatically infer "two objects with all the same fields are equal".

To compare by a single property, use a predicate describing that property:

~~~java
Predicate<Point> xIsZero = point -> point.x() == 0;
~~~

This is a different condition from being equal to Point(0,0).

### 3.4. Case-sensitive string comparison

~~~java
Predicate<String> exact = Predicate.isEqual("admin");

System.out.println(exact.test("admin")); // true
System.out.println(exact.test("ADMIN")); // false
~~~

String.equals is case-sensitive. If case-insensitive comparison is needed, choose appropriate logic:

~~~java
Predicate<String> adminIgnoreCase =
    text -> "admin".equalsIgnoreCase(text);
~~~

This lambda can return false when text is null, because the receiver is the string literal "admin". Avoid writing text.equalsIgnoreCase("admin") when text can be null. For complex normalization rules, locale and Unicode rules must be clearly defined; isEqual does not normalize strings automatically.

## 4. Combining not, isEqual, and, and or

**Predicate.and**, **Predicate.or**, and **Predicate.negate** are default methods, while **Predicate.not** and **Predicate.isEqual** are static methods. They help express logic as easily testable components.

Example selecting order status:

~~~java
record Order(String status, boolean paid) {}

Predicate<Order> paid = Order::paid;
Predicate<Order> notCancelled =
    Predicate.not(order -> "CANCELLED".equals(order.status()));

Predicate<Order> accepted = paid.and(notCancelled);
~~~

This is illustrative code that needs to be placed in a context with appropriate Order/Predicate declarations. accepted.test(order) is only true if order is paid **and** status is not CANCELLED.

You can use isEqual for a property:

~~~java
Predicate<String> isCancelled =
    Predicate.isEqual("CANCELLED");

Predicate<Order> active =
    order -> !isCancelled.test(order.status());
~~~

However, if it is just to check one field once, adding multiple predicate layers can be verbose. Do not force isEqual everywhere; "CANCELLED".equals(order.status()) is often already very clear.

### 4.1. Combining conditions with short-circuiting

~~~java
Predicate<String> nonNull = java.util.Objects::nonNull;
Predicate<String> nonBlank = Predicate.not(String::isBlank);

Predicate<String> valid = nonNull.and(nonBlank);
~~~

Here valid.test(null) is false **without calling nonBlank** thanks to the short-circuit rule of and: if the left condition is false, the right condition is not called. This is a way to combine conditions that can handle null safely.

Similarly:

~~~java
Predicate<String> isSpecial = Predicate.isEqual("SPECIAL");
Predicate<String> longValue = text -> text.length() >= 8;

Predicate<String> allowed = isSpecial.or(longValue);
~~~

With test("SPECIAL"), the first branch is true, so the second branch does not run. With test(null), isSpecial returns false and then longValue can throw NullPointerException: **or does not make subsequent predicates null-safe**.

If null must be handled in all cases, combine a protective first condition:

~~~java
Predicate<String> allowedSafely =
    java.util.Objects::<String>nonNull;
~~~

This line only creates a non-null checking predicate; in an application, appropriate predicates can be chained onto it. A more self-explanatory example is:

~~~java
Predicate<String> nonNullAndAllowed =
    ((Predicate<String>) java.util.Objects::nonNull)
        .and(isSpecial.or(longValue));
~~~

With a null input, the nonNull check is false so the subsequent branch does not run. The clearest way is sometimes to extract a Predicate<String> nonNull variable before composing to avoid cluttered casts.

### 4.2. De Morgan's Laws

For pure, total predicates A and B (that do not throw errors), in terms of logical result:

- not(A.and(B)) is equivalent to not(A).or(not(B)).
- not(A.or(B)) is equivalent to not(A).and(not(B)).

In Java:

~~~java
Predicate<String> a = text -> text.startsWith("J");
Predicate<String> b = text -> text.length() > 3;

Predicate<String> neither =
    Predicate.not(a.or(b));

Predicate<String> equivalent =
    Predicate.not(a).and(Predicate.not(b));
~~~

Both predicates produce the same boolean result for a non-null String; however **if callbacks have side effects or exceptions**, differences in execution order/paths may be observable depending on how the transformation and condition structure are written. Therefore, it is best to write predicates **without side effects** and without depending on external mutable state.

### 4.3. Negating the right scope

A common mistake is confusing:

~~~java
Predicate<String> isEmpty = String::isEmpty;
Predicate<String> isNotEmpty = Predicate.not(isEmpty);
~~~

with:

~~~java
Predicate<String> isBlank = String::isBlank;
Predicate<String> isNotBlank = Predicate.not(isBlank);
~~~

**String.isEmpty()** is only true when length is 0, whereas **String.isBlank()** is true when the string is empty or consists only of whitespace characters as defined by Character.isWhitespace. The string "   " is not empty, yet it is blank. Choose the business-appropriate base predicate **before** negating.

## 5. In the Stream API: expressing intent clearly

### 5.1. Filtering non-blank values

~~~java
List<String> result = List.of("Java", " ", "Stream", "")
    .stream()
    .filter(Predicate.not(String::isBlank))
    .toList();
~~~

The result is ["Java", "Stream"]. This is a case where Predicate.not produces a readable expression when the base method reference already expresses the property well.

If the source can contain null, null must be filtered out first:

~~~java
List<String> result = input.stream()
    .filter(java.util.Objects::nonNull)
    .filter(Predicate.not(String::isBlank))
    .toList();
~~~

Conversely, .filter(Predicate.not(String::isBlank)) by itself **does not** check for null and can throw NullPointerException when an element is null.

### 5.2. Filtering exact target values

~~~java
List<String> result = List.of("NEW", "PAID", "NEW")
    .stream()
    .filter(Predicate.isEqual("NEW"))
    .toList();
~~~

Result is ["NEW", "NEW"], preserving the encounter order of the sequential source stream.

Conversely, to exclude all "NEW":

~~~java
List<String> result = List.of("NEW", "PAID", "NEW")
    .stream()
    .filter(Predicate.not(Predicate.isEqual("NEW")))
    .toList();
~~~

Result is ["PAID"]. You can use .filter(status -> !"NEW".equals(status)) if that is shorter and easier to understand in context; there is no requirement that every expression use factory methods.

### 5.3. Finding the first element not equal to X

~~~java
String firstOther = List.of("A", "B", "A").stream()
    .filter(Predicate.not(Predicate.isEqual("A")))
    .findFirst()
    .orElse("none");
~~~

firstOther equals "B". findFirst and orElse clarify the not-found case. With a parallel source, findFirst still honors the encounter order contract when the source is ordered, though cost and execution mechanics may differ from a sequential stream.

### 5.4. Note on lazy evaluation

filter is an intermediate operation and may **not call the predicate yet** until there is a terminal operation like toList, count, or findFirst. Streams can short-circuit or optimize certain operations. Therefore, do not use Predicate.not or Predicate.isEqual as a guaranteed point for counting evaluations or writing critical logs.

A Predicate is a condition description; **applying** the condition is decided by the API invoking the callback.

## 6. Generic type inference and method references

### 6.1. Predicate.not preserves the desired type

Predicate.not uses type parameter T and parameter Predicate<? super T> to accept a predicate on T or a supertype of T. This is useful when combining objects with a type hierarchy:

~~~java
Predicate<CharSequence> emptyText =
    text -> text.length() == 0;

Predicate<String> notEmptyString = Predicate.not(emptyText);
~~~

With a String input, Predicate<CharSequence> can still test it because String implements CharSequence. Here there is a clear target type on the left-hand side to infer T = String.

Avoid using raw Predicate because it loses type checking and increases the chance of ClassCastException when the predicate is used with the wrong type.

### 6.2. Predicate.isEqual takes Object, but returns Predicate<T>

~~~java
Predicate<String> isJava = Predicate.isEqual("Java");
Predicate<Object> isNull = Predicate.isEqual(null);
~~~

The generic type of the resulting predicate is usually inferred from the target type or method context. targetRef has a declared type of Object so it can accept many kinds of reference values; **this does not mean every test call skips type checking**: if the variable is declared as Predicate<String>, test(123) is invalid at compile time.

When using a method reference or lambda nested deeply in generic calls, the compiler sometimes needs extra type hints. Prefer explicitly typed predicate variables or valid type witnesses instead of abusing Object casts.

### 6.3. Target type of a method reference in not

~~~java
Predicate<String> notEmpty =
    Predicate.not(String::isEmpty);
~~~

String::isEmpty is a method reference to an instance method with no explicit parameters, with the receiver supplied from the argument of test(String). The compiler checks compatibility against the function descriptor of Predicate<String>.

**Not every method reference is valid**: if the method takes/returns types that do not match the SAM test(T) → boolean, the compiler will reject it. Predicate.not does not automatically convert Function<T,R> or Consumer<T> into Predicate<T>.

## 7. Predicate.isEqual and the equals/hashCode contract

When comparing objects, isEqual relies on **equality**, so the equals design of the data type determines the result:

1. **Reflexive:** an object x equals itself (x.equals(x) is true for non-null x).
2. **Symmetric:** x.equals(y) and y.equals(x) must have consistent results.
3. **Transitive:** if x equals y and y equals z, then x equals z.
4. **Consistent:** unchanged when information participating in equals does not change.
5. **Non-null:** x.equals(null) must be false for non-null x.

For records with suitable components, Java generates equals based on the components; for ordinary classes, equals/hashCode must be overridden carefully if data-based equality is required.

Example:

~~~java
record Code(String value) {}

Predicate<Code> match = Predicate.isEqual(new Code("X"));
System.out.println(match.test(new Code("X"))); // true
~~~

If a class does not override equals from Object, two instances with identical field data will usually still not be equal. Predicate.isEqual **does not** replace defining the equality contract on the object type.

**On mutable references:** targetRef is provided when creating the predicate; if the reference object is mutable and fields participating in equals change afterward, comparison results can also change. When stable comparison is needed, use immutable data or create an appropriate snapshot. Do not confuse creating a predicate once with freezing the state of all related objects.

**On hashCode:** Predicate.isEqual itself does not create a hash collection and does not call hashCode to compare, but if that object is also used in HashMap/HashSet, a consistent equals/hashCode contract must be maintained.

## 8. Side effects and evaluation order

A predicate can perform side effects:

~~~java
java.util.concurrent.atomic.AtomicInteger calls =
    new java.util.concurrent.atomic.AtomicInteger();

Predicate<String> checked = text -> {
    calls.incrementAndGet();
    return text.isBlank();
};

Predicate<String> notBlank = Predicate.not(checked);
~~~

Calling notBlank.test("Java") still calls checked.test("Java") and increments calls once. **Predicate.not does not cancel or undo side effects** of the original predicate; it only negates the returned boolean. Using AtomicInteger can make the increment atomic, but it does not make the callback pure.

Similarly, with Predicate.isEqual(mutableTarget), if a custom equals has side effects, calling test can still trigger side effects. Do not put business logic that depends on call count or call order inside filter, especially with parallel streams.

When combining and/or, there is short-circuiting; when calling negate/not, the negated result is only meaningful when the inner predicate completes normally. If the original predicate throws an exception, the exception still propagates, rather than being "flipped" to false or true.

## 9. Complete Java 17+ program

This program demonstrates **Predicate.not**, **Predicate.isEqual**, **negate**, **and**, method references, and null checking. In addition, there is a rule for record User and a case-insensitive example using equals with custom logic.

Create **PredicateCompositionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Predicate;

public class PredicateCompositionDemo {
    record User(String username, boolean active) {}

    static List<String> nonBlankValues(List<String> values) {
        return values.stream()
            .filter(Predicate.not(String::isBlank))
            .toList();
    }

    static List<User> activeNonGuestUsers(List<User> users) {
        Predicate<User> active = User::active;
        Predicate<User> notGuest =
            Predicate.not(user -> user.username().equalsIgnoreCase("guest"));
        return users.stream().filter(active.and(notGuest)).toList();
    }

    public static void main(String[] args) {
        List<String> values = List.of("Java", "  ", "Stream", "");
        System.out.println("nonBlank=" + nonBlankValues(values));

        Predicate<String> isAdmin = Predicate.isEqual("admin");
        System.out.println("admin=" + isAdmin.test("admin"));
        System.out.println("other=" + isAdmin.test("guest"));
        System.out.println("notAdmin=" + isAdmin.negate().test("guest"));

        Predicate<Object> isNull = Predicate.isEqual(null);
        System.out.println("isNull=" + isNull.test(null));
        System.out.println("isNullText=" + isNull.test(""));

        List<User> users = List.of(
            new User("alice", true),
            new User("guest", true),
            new User("bob", false),
            new User("carol", true)
        );
        System.out.println("eligible=" + activeNonGuestUsers(users));

        List<String> possiblyNull = new ArrayList<>();
        possiblyNull.add(null);
        possiblyNull.add("Java");
        System.out.println("nullCount=" +
            possiblyNull.stream().filter(Predicate.isEqual(null)).count());

        Predicate<String> lowercaseAdmin =
            text -> "admin".equals(text.toLowerCase(Locale.ROOT));
        System.out.println("caseFold=" + lowercaseAdmin.test("ADMIN"));
    }
}
~~~

Compile and run from the folder containing the file with JDK 17 or newer:

~~~bash
javac PredicateCompositionDemo.java
java PredicateCompositionDemo
~~~

**Exact stdout:**

~~~text
nonBlank=[Java, Stream]
admin=true
other=false
notAdmin=true
isNull=true
isNullText=false
eligible=[User[username=alice, active=true], User[username=carol, active=true]]
nullCount=1
caseFold=true
~~~

Analysis:

1. nonBlankValues excludes "  " and "" using Predicate.not(String::isBlank), keeping Java and Stream in source order.
2. isAdmin uses Predicate.isEqual("admin"), checking exact case-sensitive equality; guest does not equal admin.
3. isAdmin.negate() returns true for guest because the base condition is false.
4. Predicate.isEqual(null) returns true for test(null), false for test(""); these two results are completely different.
5. activeNonGuestUsers combines two conditions: user.active() and username not equal to "guest" via equalsIgnoreCase. Only alice and carol are kept.
6. possiblyNull is an ArrayList so it can contain null, unlike List.of. Filtering with isEqual(null) counts exactly one null element.
7. lowercaseAdmin uses a lowercase conversion rule with Locale.ROOT and compares to "admin", so "ADMIN" is accepted. This is a custom rule, **not the behavior of Predicate.isEqual**.

The program uses immutable lists for normal data and only uses ArrayList to illustrate null. In a real application, if User.username() can be null, the current notGuest lambda can throw NullPointerException; add validation contracts or null-safe comparisons per business requirements.

## 10. Common mistakes and how to fix them

**Mistake 1 — Confusing Predicate.not with calling test immediately.** Predicate.not creates a new Predicate; you must call test or pass it to a callback API to apply it. not(...) does not run through a stream by itself.

**Mistake 2 — Assuming not makes a callback null-safe.** Predicate.not(String::isBlank) can still throw NullPointerException on test(null). Filter out null first or use a predicate capable of handling null.

**Mistake 3 — Confusing not with negate.** Both negate logic, but not is a static method taking a predicate, while negate is an instance method on a predicate. Use whichever expression makes the code clearest.

**Mistake 4 — Confusing isEqual with ==.** Predicate.isEqual uses equality via equals/Objects.equals. It does not merely check whether two variables point to the same object, unless the data type's equals has that meaning.

**Mistake 5 — Thinking isEqual automatically ignores case.** For String, "admin" does not equal "ADMIN". To ignore case, use an explicit rule or normalize data beforehand.

**Mistake 6 — Using List.of(null) when illustrating null comparison.** List.of does not accept null and can throw NullPointerException when creating the list. Use ArrayList or a data source that can contain null to test Predicate.isEqual(null).

**Mistake 7 — Replacing equals-contract checks with isEqual.** For records, equality is usually component-based; for mutable classes that do not override equals, results may differ from expectations. Check the equals definition before using isEqual.

**Mistake 8 — Writing predicates with side effects and expecting them to run once.** Streams have lazy evaluation, short-circuiting, and optimizations. When using and/or, the subsequent condition may not be called. Do not rely on callback invocation counts to write critical audits.

**Mistake 9 — Forgetting the Java version.** Predicate.isEqual has been available since Java 8; **Predicate.not was added in Java 11**. Code using Predicate.not will not compile when targeting JDK 8, even though methods like negate/and/or already exist.

**Mistake 10 — Abusing generic casts.** When the compiler reports type inference errors, prioritize checking the types of the stream and functional interface and naming explicit Predicate<T> variables, rather than raw-casting to Predicate or Object and losing type safety.

**Mistake 11 — Wrong order of null-safe conditions.** nonNull.and(notBlank) can protect the later branch from null; reversing it to notBlank.and(nonNull) causes notBlank to encounter null first. Because and short-circuits in order, condition order matters.

**Mistake 12 — Confusing isEmpty with isBlank.** A string containing only spaces is not empty, yet it is blank. Check the business definition before negating the condition.

## 11. Which style to choose?

| Purpose | Clear expression |
| --- | --- |
| Negate an already-named predicate | predicate.negate() |
| Negate a method reference at the call site | Predicate.not(String::isBlank) |
| Filter elements equal to a constant | Predicate.isEqual("ACTIVE") |
| Filter elements not equal to a constant | Predicate.not(Predicate.isEqual("ACTIVE")) |
| Check for null | Objects::isNull or Predicate.isEqual(null) |
| Exclude null | Objects::nonNull or Predicate.not(Predicate.isEqual(null)) |
| Combine conditions | predicateA.and(predicateB), predicateA.or(predicateB) |
| Compare by property | value -> value.property().equals(target) with appropriate null handling |
| Case-insensitive comparison | value -> "target".equalsIgnoreCase(value) |

There is no mandatory rule to write every expression through Predicate.not or isEqual. For example, .filter(value -> !"ACTIVE".equals(value)) is sometimes clearer than .filter(Predicate.not(Predicate.isEqual("ACTIVE"))). Choose a style consistent with your team and prioritize **clear intent, testability, and data safety**.

## 12. Self-check questions

1. How are Predicate.not(String::isBlank) and predicate.negate() similar and different in how they create a predicate?
2. Why does Predicate.not(String::isBlank).test(null) not safely become true?
3. Does Predicate.isEqual("Java").test(new String("Java")) return true or false? Why?
4. How do Predicate.isEqual(null).test(null) and Predicate.isEqual(null).test("") differ?
5. If a collection can contain null, why should Objects::nonNull be filtered before Predicate.not(String::isBlank)?
6. With predicateA.and(predicateB), does predicateB run when predicateA returns false?
7. How do String.isEmpty and String.isBlank differ when used on a string containing only whitespace?
8. For a class that does not override equals, does isEqual automatically compare all fields?
9. Why cannot Predicate.isEqual("ADMIN") replace a predicate comparing with equalsIgnoreCase?
10. When designing a parallel Stream filter, why should you not update a shared counter inside the callback?
11. When using JDK 8, what can replace Predicate.not(predicate) while preserving negation behavior?
12. How can isEqual and not be combined to exclude a specific order status while keeping other statuses?

**Summary:** Predicate.not helps **negate a condition**, especially concisely with method references. Predicate.isEqual creates an **equality comparison condition against a reference object**, including a null reference. Using them properly with negate, and, and or makes Java filtering rules and pipelines easier to read, though you must still understand equals, generic types, null, short-circuiting, and callback side effects.
