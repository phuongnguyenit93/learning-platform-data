# Poly Expressions, Nested Calls, and Target Type Propagation Limits in Java Generics

## 1. Framing the problem accurately

When using generics, Java can infer type parameters thanks to the **context** in which an expression appears. For example:

~~~java
List<String> names = Collections.emptyList();
~~~

The method Collections.emptyList() has a declaration along the lines of **static <T> List<T> emptyList()**. It takes no arguments, yet in the assignment above, Java still infers T as String thanks to the target type **List<String>**.

This capability is tied to **poly expressions**: expressions whose type depends on an appropriate context, rather than being determined solely from the expression's internal contents.

A harder question arises when there are nested calls:

~~~java
List<String> a = identity(Collections.emptyList());
List<String> b = Collections.emptyList().stream().toList();
~~~

Both expressions appear to start from emptyList(), yet the first statement compiles while the second **does not compile**. We must examine the **syntactic position of each call**, the kind of context supplying the target type, and how type constraints flow across methods. This is the most important practical limit of nested type inference.

Examples in this lesson use Java 17+ and standard APIs from java.util, java.util.function, and java.util.stream.

## 2. Three foundational concepts: target type, standalone expression, and poly expression

**Target type** is the type the context expects the expression to produce. Common sources of target types include:

- **Assignment / explicitly typed declaration**: List<String> x = Collections.emptyList();.
- **Method call argument**: consume(Collections.emptyList()); when consume takes List<String>.
- **Return expression from a method**: a method declared to return List<String>, then return Collections.emptyList();.
- **Explicit casts** and certain other specified contexts.
- **Branches of a reference conditional expression** when the conditional expression itself is a poly expression.

A **standalone expression** is an expression whose type is determined primarily from the expression itself and its own context, rather than having an expected type applied from an outer assignment via the poly expression mechanism.

A **poly expression** is an expression specified by the Java Language Specification to receive a target type in certain contexts. Being inside an assignment statement does not mean every subexpression receives the same target type.

Example:

~~~java
List<String> one = Collections.emptyList(); // Target type helps infer T = String.
var two = Collections.emptyList();          // List<Object>: no String target.
~~~

With the second declaration, **var is not a String target type**. At the emptyList() call with no specific constraints, T is inferred as Object and the static type of two is List<Object>. Using two in later lines does not change the already-inferred result.

### Poly expression does not equate to generic expression

Not every expression containing generics is a poly expression in every position. For a generic **method invocation**, the main conditions are that the call appears in an **assignment context** or **invocation context**, uses type parameters related to the return type, and belongs to a form permitted by the JLS to receive a target type. Such a call positioned as the receiver of a subsequent call does not automatically receive the target type from an outer assignment.

Other common forms of poly expressions include lambda expressions, method references, constructor calls using diamond in appropriate contexts, certain reference conditional expressions, and reference switch expressions. Each form has its own rules. We cannot conclude that every expression located inside a poly expression is itself a poly expression.

## 3. Generic type inference at a method invocation

Consider a custom generic method:

~~~java
static <T> T identity(T value) {
    return value;
}
~~~

The type parameter T appears in both the input parameter and the return type. Therefore, the compiler can receive constraints from the **actual argument**, the **target type of the entire call**, or both to find a satisfying type.

~~~java
String s = identity("Java");                  // T = String thanks to argument "Java".
List<String> x = identity(Collections.emptyList());
~~~

On line x:

1. The target type of the assignment is List<String>.
2. identity(...) is a generic call eligible to be checked in an assignment context.
3. The constraint from identity's return type T is tied to List<String>.
4. The inner Collections.emptyList() call is evaluated as an argument to identity, constrained by formal parameter T.
5. The generic constraint solver coordinates information from the outer call and the inner call; the valid result is List<String>.

Thus, we can say **target type information flows through nested call inference** in this case. However, this is not a mechanical copy of the target type from outside into every subexpression. The compiler solves the constraint system according to Java's type inference rules; differences in syntactic position and formal parameter types can change the outcome.

### Target type from a method argument

Suppose we have:

~~~java
static void consume(List<String> names) {
    System.out.println(names);
}
~~~

Both of the following calls are valid:

~~~java
consume(Collections.emptyList());
consume(identity(Collections.emptyList()));
~~~

The argument to consume appears in an **invocation context** requiring List<String>. In the nested case, inference can coordinate constraints across identity and emptyList.

Conversely:

~~~java
var temp = Collections.emptyList(); // temp is List<Object>.
// consume(temp);                   // Compile error.
~~~

**An already-typed intermediate variable** is an important boundary. Once temp is inferred as List<Object>, a subsequent consume call cannot reach back to turn temp into List<String>.

### Target type from return

If the enclosing method has return type List<String>, the return expression also has a target type context:

~~~java
static List<String> makeNames() {
    return identity(Collections.emptyList());
}
~~~

The return statement is valid because the constraint system can infer the generic calls to a type compatible with List<String>. Putting the same initializer into a var variable before returning changes the situation:

~~~java
static List<String> brokenExample() {
    var intermediate = Collections.emptyList(); // List<Object>.
    // return intermediate;                      // Does not compile.
    return Collections.emptyList();              // Valid.
}
~~~

The return keyword itself does not alter the type of an already-declared variable.

## 4. When does a target type NOT propagate across nested calls?

This is the easiest point to get wrong. Compare two cases:

~~~java
List<String> valid = Collections.emptyList();
List<String> invalid = Collections.emptyList().stream().toList(); // Error.
~~~

In the valid line, emptyList() is the **entire right-hand expression** of the assignment, so it receives target type List<String>.

In the invalid line, emptyList() serves as the **receiver** of the .stream() call. The **Collections.emptyList()** part does not appear directly in the assignment context or invocation context of the assignment to List<String>. Its type is determined first at the receiver position, where there is no constraint forcing T to be String. With no specific type argument, it is inferred as List<Object>. Then:

~~~text
Collections.emptyList()      → List<Object>
             .stream()       → Stream<Object>
             .toList()       → List<Object>
Assigned to List<String>     → Compile error
~~~

Even though the entire expression sits on the right-hand side of List<String>, the compiler **does not propagate the String target backwards through the method call chain to revise an already-determined receiver type**.

### Resolving the receiver boundary

Provide the type before starting the chain:

~~~java
List<String> good = Collections.<String>emptyList()
        .stream()
        .toList();
~~~

The expression **Collections.<String>emptyList()** is a generic method call with a **type witness** <String>. It forces T to be String right at the point where the receiver is created. Then stream() returns Stream<String> and toList() returns List<String>.

Similarly, with Stream.empty():

~~~java
List<String> bad = java.util.stream.Stream.empty().toList(); // Error.
List<String> good = java.util.stream.Stream.<String>empty().toList();
~~~

Stream.empty() is in the receiver position of toList(), so it defaults to Stream<Object> when no other constraints exist. Stream.<String>empty() fixes this by explicitly specifying the type before chaining.

**Useful checking rule:** identify which expression acts as the receiver at each dot. If the receiver is a generic call with no arguments carrying type information, the outermost assignment's target type is usually not enough to re-type that receiver.

## 5. Diamond in nested calls: tracking the boundaries accurately

Constructors using diamond receive information from the target type and from passed arguments:

```java
List<String> a = new ArrayList<>();
List<String> b = new ArrayList<>(Collections.emptyList());
var c = new ArrayList<>();                // ArrayList<Object>.
var d = new ArrayList<>(List.of("Java")); // ArrayList<String>.
```

Line `b` is a **constructor call with target** `List<String>`; the E constraint from `ArrayList<E>` coordinates with the generic call `Collections.emptyList()` as the constructor argument. Line `c` lacks both a String target and an argument determining E; line `d` receives String information from the constructor argument itself.

Unlike a **receiver chain** in section 4, a generic call inside a constructor is an **argument**, so it gets a chance to participate in inference through an invocation context. However, if you first assign `var source = Collections.emptyList()`, the `List<Object>` type of that variable is already locked in; `new ArrayList<>(source)` does not automatically turn it into `List<String>`.

Distinguish two boundaries: *a constructor argument can receive contextual information*; *a generic method call that has become the receiver of a method chain does not necessarily receive the outermost target*. This is why this lesson analyzes expression positions rather than merely repeating instructions for using diamond.

## 6. Lambdas and method references: poly expressions requiring a target type

The difference is very clear when using functional interfaces:

~~~java
Function<String, Integer> length = s -> s.length();
~~~

The lambda expression **s -> s.length()** receives target type Function<String, Integer>; the compiler knows parameter s is String and can look up the length() method.

The following statement does not compile:

~~~java
var length = s -> s.length(); // Error: lambda expression needs an explicit target-type.
~~~

The reason is not that var is forbidden in all lambda-related declarations: a lambda **requires a functional interface target type**, and var cannot infer the intended functional interface from the lambda body alone. A single lambda can match many different interfaces.

Method references work similarly:

~~~java
Supplier<List<String>> factory = Collections::emptyList;
Function<String, Integer> length = String::length;
~~~

The two variables above have clear functional interface targets, so the compiler knows the method signature to match.

~~~java
var factory = Collections::emptyList; // Error: method reference needs a target type.
~~~

Using var with **the result of a method call returning a functional interface** is different; in that case, the initializer already has its own type. Example:

~~~java
static java.util.function.Function<String, Integer> createLengthFunction() {
    return String::length;
}

var lengthFunction = createLengthFunction(); // Valid.
~~~

Here var infers from the return type Function<String, Integer> of createLengthFunction(), not directly from the method reference.

## 7. Conditional expressions and target type limits

A reference conditional expression can be a poly expression when it appears in an appropriate context:

~~~java
List<String> chosen = flag
        ? Collections.emptyList()
        : List.of("fallback");
~~~

In a program where flag is a declared boolean, the assignment has target List<String>. That information can be used to check both branches, including inferring emptyList() as List<String>. The target type is distributed according to the rules of a **reference conditional expression**.

However, you should not conclude that every operator expression propagates types through this mechanism. For instance, arithmetic expressions, conditional expressions with primitive branches, method call chains, and lambdas each have their own rules; an outer assignment does not make all subexpressions poly by default.

In particular:

~~~java
var chosen = flag
        ? Collections.emptyList()
        : List.of("fallback");
~~~

There is no List<String> target supplied by the left-hand side. The compiler must determine the type of the conditional expression using the rules applied when no specific target context exists; do not assume chosen is guaranteed to have type List<String> just because one branch contains strings.

## 8. Runnable Java 17+ program

Save the following code as **PolyTargetDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Function;
import java.util.function.Supplier;

public class PolyTargetDemo {
    static <T> T identity(T input) {
        return input;
    }

    static void consume(List<String> names) {
        System.out.println("consume=" + names);
    }

    static List<String> fromReturn() {
        return identity(Collections.emptyList());
    }

    public static void main(String[] args) {
        List<String> direct = Collections.emptyList();

        // Target type coordinates with nested generic call.
        List<String> nested = identity(Collections.emptyList());
        consume(identity(Collections.emptyList()));

        // Diamond and inner generic call are inferred together.
        List<String> constructed =
                new ArrayList<>(Collections.emptyList());

        // Type witness overcomes receiver boundary in method chain.
        List<String> chained = Collections.<String>emptyList()
                .stream()
                .toList();

        // Lambda and method reference receive types from functional interface.
        Supplier<List<String>> factory = Collections::emptyList;
        Function<String, Integer> length = String::length;

        // Reference conditional expression receives target List<String>.
        List<String> selected = true
                ? Collections.emptyList()
                : List.of("fallback");

        // Even with var, constructor argument provides type information.
        var inferred = new ArrayList<>(List.of("A", "B"));

        System.out.println("direct=" + direct);
        System.out.println("nested=" + nested);
        System.out.println("constructed=" + constructed);
        System.out.println("chained=" + chained);
        System.out.println("factory=" + factory.get());
        System.out.println("length=" + length.apply("Java"));
        System.out.println("selected=" + selected);
        System.out.println("inferred=" + inferred);
        System.out.println("fromReturn=" + fromReturn());
    }
}
~~~

Compile and run with Java 17 or newer:

~~~bash
javac PolyTargetDemo.java
java PolyTargetDemo
~~~

Exact stdout:

~~~text
consume=[]
direct=[]
nested=[]
constructed=[]
chained=[]
factory=[]
length=4
selected=[]
inferred=[A, B]
fromReturn=[]
~~~

**Why is selected an empty list?** The condition true selects the Collections.emptyList() branch. The other branch List.of("fallback") is still type-valid, though not executed. Calling length.apply("Java") returns 4 because the String "Java" has four characters.

For the test code with `static <T> T identity(T input)`, the outer target type can constrain T and the inner emptyList() call. For the chained line, writing the type witness directly at emptyList() ensures the receiver has type List<String> before calling stream().

## 9. Deliberately non-compiling snippets and how to fix them

The examples below are **standalone snippets for error identification**, not meant to be inserted directly into PolyTargetDemo.java.

### Mistake A: target type does not travel backwards through a receiver

~~~java
List<String> x = Collections.emptyList().stream().toList(); // Does not compile.
~~~

Reason: the emptyList() call at the receiver position is inferred as List<Object>; then toList() yields List<Object>, which cannot be assigned to List<String>.

~~~java
List<String> x = Collections.<String>emptyList().stream().toList();
~~~

Fix using a type witness on the call that needs a type constraint, before the stream() chain.

### Mistake B: expecting an intermediate variable to change type retroactively

~~~java
var values = Collections.emptyList(); // List<Object>.
List<String> names = values;          // Does not compile.
~~~

Reason: type inference completes on the line declaring values. Generics in Java are invariant, so List<Object> cannot automatically convert to List<String>.

~~~java
List<String> values = Collections.emptyList();
List<String> names = values;
~~~

Fix by providing the target type right where the variable values is created.

### Mistake C: using var directly with a lambda/method reference

~~~java
var mapper = (String s) -> s.length(); // Does not compile.
var supplier = Collections::emptyList; // Does not compile.
~~~

Fix by declaring a concrete functional interface:

~~~java
Function<String, Integer> mapper = s -> s.length();
Supplier<List<String>> supplier = Collections::emptyList;
~~~

### Mistake D: assuming every nested method invocation receives a single target type

Compare:

~~~java
List<String> works = identity(Collections.emptyList());
List<String> fails = Collections.emptyList().stream().toList();
~~~

The first statement has generic constraint linking from identity to the emptyList() argument; the second statement has a **receiver boundary**, so it is not inferred the same way. "Nested" only describes syntactic appearance; **the nested position** determines the type context.

### Mistake E: thinking Object is a raw type or dynamic type

~~~java
var source = Collections.emptyList(); // List<Object>, with a concrete generic type.
~~~

List<Object> differs from raw List and List<?>:

- **List<Object>** allows adding Object and subtypes if the list is modifiable.
- **Raw List** discards generic parameter information and can lead to unchecked warnings.
- **List<?>** is a list of unknown element type; you cannot freely add non-null values.

However, Collections.emptyList() specifically returns an **unmodifiable empty list**. Being inferred as List<Object> does not mean calling add will succeed at runtime. Properly typed code can still throw UnsupportedOperationException if the collection does not support modification.

## 10. Process for self-analyzing a complex generic expression

When you do not understand why the compiler picks Object, String, or reports incompatible types, follow these steps:

1. **Bracket the entire expression being assigned/returned/passed as an argument** and note the expected target type if present.
2. **Locate generic method invocations**: inspect method declarations, type parameters, return types, and formal parameters.
3. **Identify the context of each specific call**: assignment, invocation, return, or receiver of a subsequent call.
4. **Find actual constraint sources**: target type, actual arguments, type witness, diamond, and upper bounds on type parameters.
5. **Identify inference boundaries**: intermediate variables with locked-in types; generic invocations in receiver positions that may not receive the outermost target.
6. **Verify intermediate static type results before chaining further**: List<Object> → Stream<Object> → List<Object> will not automatically turn into List<String>.
7. **Fix at the point where type information is missing**: write an explicit type on the variable, a type witness on the generic method, a type argument on the constructor, or keep the expression inside a context with a suitable target type.

Do not fix with blind casts or raw types just to satisfy the compiler: doing so hides the root cause and can introduce unchecked warnings or runtime errors.

## 11. Summary by context

| Expression | Target type available? | What happens |
| --- | --- | --- |
| List<String> a = Collections.emptyList(); | Yes, List<String> | T of emptyList is inferred as String. |
| var a = Collections.emptyList(); | No String target type | a is List<Object>. |
| List<String> a = identity(Collections.emptyList()); | Yes, List<String> | Nested generic inference can coordinate constraints. |
| consume(Collections.emptyList()); | Yes, List<String> parameter | Generic argument is inferred to match formal parameter. |
| List<String> a = Collections.emptyList().stream().toList(); | Yes at outer assignment, missing at receiver | emptyList infers List<Object>; assignment fails. |
| List<String> a = Collections.<String>emptyList().stream().toList(); | String specified explicitly at emptyList | Chain yields List<String> and compiles. |
| List<String> a = new ArrayList<>(); | Yes, List<String> | Diamond infers ArrayList<String>. |
| var a = new ArrayList<>(); | No concrete E constraint | a is ArrayList<Object>. |
| Function<String,Integer> f = String::length; | Yes, functional interface | Method reference is checked against target type. |
| var f = String::length; | No functional interface | Does not compile. |

Rows with the same variable names a/f in the table are **separate scenarios**, not a sequential program.

## 12. Self-check questions

**Question 1.** Why can List<String> x = identity(Collections.emptyList()); be valid while var temp = Collections.emptyList(); followed by assigning temp to List<String> produces an error?

**Answer:** The first case solves generic constraints within a single expression that has target type List<String>. The second case locks temp's type as List<Object> beforehand; the target type at the later assignment does not re-infer that variable.

**Question 2.** Why does List<String> x = Collections.emptyList().stream().toList(); fail even though String is written on the left?

**Answer:** emptyList() sits at the receiver position of .stream(), lacking the List<String> target; it is inferred as List<Object>, and the Object element type propagates through Stream and toList.

**Question 3.** What are two ways to fix the case in Question 2 without using raw types or unchecked casts?

**Answer:** Write Collections.<String>emptyList().stream().toList(), or create an intermediate variable List<String> source = Collections.emptyList(); and then call source.stream().toList().

**Question 4.** Why does var f = String::length; fail to compile, whereas Function<String, Integer> f = String::length; is valid?

**Answer:** A method reference requires a target functional interface to determine its function signature; var does not supply that signature at the initializer.

**Question 5.** Is var values = new ArrayList<>(List.of("A")); guaranteed to be ArrayList<Object>?

**Answer:** No. The List.of("A") argument carries String element information, enabling the constructor to infer ArrayList<String> right at the initializer.

**Remember:** Type inference is based on **constraints at the position where the expression is evaluated**. Target types can assist nested generic calls when poly expression rules permit, but they do not propagate unconditionally across receivers, intermediate variables, or every expression form. When the compiler does not infer what you intended, provide the type right at the boundary where information is missing.
