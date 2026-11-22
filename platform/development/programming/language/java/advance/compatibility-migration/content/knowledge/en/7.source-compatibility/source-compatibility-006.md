# Lambdas and Method References When Functional Contracts Change

## 1. Why Do Functional Contract Changes Affect Java Source Code?

Lambda expressions and method references allow passing behavior as a value. They appear in the Stream API, callbacks, listeners, executors, comparators, event handlers, and many library APIs. A small change in the functional type required by an API can break compilation across numerous call sites, even when the lambda body still looks valid at a glance.

For example, a library initially accepts `Function<String, Integer>` and then changes the parameter to `ToIntFunction<String>`. Both take a `String` and return a numeric value, yet the result type and type contract differ: `Function` returns `Integer`, whereas `ToIntFunction` returns `int`. A lambda may keep compiling thanks to target typing and boxing/unboxing, yet variables or method references already declared under the old type may need adjustment.

When analyzing source compatibility in a Java migration, three components must be understood:

- **Functional interface:** an interface with a single abstract method suited to serve as the target type for a lambda or method reference.
- **Lambda expression:** an expression providing the implementation for a functional interface's abstract method.
- **Method reference:** syntax referencing a method or constructor that can be adapted to the target functional interface's signature.

When a functional contract changes, the compiler must re-check parameter count and types, return type, generic types, checked exceptions, overload resolution, and target-type context. A previously valid expression may fail to compile, or may resolve to a different overload than originally intended.

This lesson focuses on identifying those impacts, reading compiler errors, and converting call sites in a controlled manner when upgrading APIs, libraries, or frameworks.

## 2. Functional Interfaces Are the Contract of Lambdas

### 2.1. Single Abstract Method (SAM)

A functional interface has a single abstract method (Single Abstract Method — SAM). `default` and `static` methods do not increase the SAM count. Abstract methods with equivalent signatures inherited from multiple interfaces can also count as a single abstract contract under Java rules.

Example:

```java
@FunctionalInterface
interface TextFormatter {
    String format(String input);
}

TextFormatter trimAndUpper = text -> text.trim().toUpperCase();
System.out.println(trimAndUpper.format("  java  "));
```

The lambda `text -> ...` is checked against the SAM `format(String)`. The compiler knows `text` has type `String` and the result must be compatible with `String`.

The `@FunctionalInterface` annotation is not mandatory for writing lambdas, yet should be used on interfaces designed as functional contracts. If a change accidentally adds a second abstract method, the compiler will report an error immediately at the interface declaration.

### 2.2. Common Functional Interfaces in the JDK

The `java.util.function` package provides commonly used functional types:

| Interface | General contract | Example usage |
| --- | --- | --- |
| `Predicate<T>` | `boolean test(T value)` | Filtering condition |
| `Function<T, R>` | `R apply(T value)` | Value transformation |
| `Consumer<T>` | `void accept(T value)` | Processing with side effects |
| `Supplier<T>` | `T get()` | Supplying a value |
| `UnaryOperator<T>` | `T apply(T value)` | Same-type input/output transformation |
| `BiFunction<T, U, R>` | `R apply(T left, U right)` | Combining two inputs |
| `BiConsumer<T, U>` | `void accept(T left, U right)` | Processing two inputs |
| `ToIntFunction<T>` | `int applyAsInt(T value)` | Converting to primitive `int` |
| `IntFunction<R>` | `R apply(int value)` | Taking primitive `int` |
| `IntPredicate` | `boolean test(int value)` | Predicate for `int` |

Specialized primitive interfaces avoid some boxing/unboxing operations. Therefore, switching from `Function<T, Integer>` to `ToIntFunction<T>` changes both the SAM type and how the API represents the result.

### 2.3. Changes to `default` and `static` Methods

Adding a `default` method or `static` method to a functional interface usually does not break the SAM property because the abstract method count does not increase.

```java
@FunctionalInterface
interface NameRule {
    boolean accepts(String name);

    default boolean acceptsNonBlank(String name) {
        return name != null && !name.isBlank() && accepts(name);
    }

    static NameRule allowAll() {
        return name -> true;
    }
}
```

Existing lambdas still implement `accepts(String)`. However, a new default method can still affect behavior when called, conflict with a default method inherited from another interface, or change how frameworks use the interface. Therefore, “SAM unchanged” does not equate to “no behavioral change”.

If a new abstract method without a default implementation is added, the interface is no longer a functional interface and existing lambdas cannot implement it. This is a clear source-compatibility change.

## 3. Lambdas Are Checked Against Their Target Type

A lambda does not have a complete standalone type like an explicitly declared object class. The compiler uses the target type—typically a functional interface at an assignment, method parameter, or return position—to infer parameters and check the body.

```java
Predicate<String> isLong = value -> value.length() > 10;
Function<String, Integer> length = value -> value.length();
Consumer<String> print = value -> System.out.println(value);
```

In the three examples:

- `Predicate<String>` requires one `String` parameter and a boolean result.
- `Function<String, Integer>` requires one `String` parameter and an `Integer`-compatible result.
- `Consumer<String>` requires one `String` parameter; the body is used as an action returning no value.

The target type can come from an API signature:

```java
void register(Predicate<String> rule) {
    // Save rule for later use
}

register(value -> value.startsWith("J"));
```

If a library changes the `register` parameter to another functional interface, the compiler re-analyzes the lambda under the new contract. The lambda may remain valid, yet inferred parameter types, return type, checked exceptions, or overload selection may change.

### 3.1. Lambdas with Explicit Parameter Types

Explicit parameter types can be declared to clarify intent:

```java
Predicate<String> rule = (String value) -> value.startsWith("J");
```

This is helpful when the compiler cannot infer types or when multiple overloads exist. However, explicit declarations do not make a new contract compatible with old parameter types. If the API switches from `String` to `Path`, the lambda `(String value) -> ...` still does not fit.

### 3.2. Block Lambdas and Return Types

With block lambdas, `return` branches must satisfy the SAM return type:

```java
Function<String, Integer> parseLength = value -> {
    if (value == null) {
        return 0;
    }
    return value.length();
};
```

If the functional interface changes its return type from `Integer` to `String`, `return` statements must be adjusted. If it changes to `void`, a block lambda cannot retain previous return values. Conversely, a lambda returning nothing cannot automatically satisfy a SAM requiring a value.

## 4. Method References and Their Adaptation Forms

Method references use an existing method instead of writing a direct forwarding lambda. The compiler still needs a target type to determine which method is selected and how parameters/results are adapted.

### 4.1. Referencing a Static Method

```java
Function<String, Integer> parser = Integer::parseInt;
```

Semantically equivalent to:

```java
Function<String, Integer> parser = value -> Integer.parseInt(value);
```

The target type indicates a method taking `String` and returning `Integer` is needed. The compiler can select the `Integer.parseInt(String)` overload returning `int`, then box it to `Integer` per `Function`'s return type.

### 4.2. Referencing an Instance Method on a Specific Object (Bound Reference)

```java
String prefix = "java-";
Function<String, String> addPrefix = prefix::concat;
```

The receiving object is already fixed in `prefix::concat`; the semantically equivalent lambda is:

```java
Function<String, String> addPrefix = value -> prefix.concat(value);
```

The receiver object is captured when the method reference expression is created. If the `prefix` variable is later reassigned to another string, the already-created method reference keeps the original receiver. If the receiver is `null`, an error can occur when creating the method reference because the receiver expression must be evaluated immediately.

### 4.3. Referencing an Instance Method on an Arbitrary Object of a Given Type (Unbound Reference)

```java
Function<String, String> trim = String::trim;
```

In this form, the first parameter of the functional interface becomes the method receiver:

```java
Function<String, String> trim = value -> value.trim();
```

A two-parameter example:

```java
BiFunction<String, Integer, Character> charAt = String::charAt;
```

The first parameter is the `String` receiver, the second parameter is passed to `charAt(int)`, and the primitive `char` result is boxed to `Character`.

### 4.4. Constructor References

```java
Supplier<ArrayList<String>> newList = ArrayList::new;
Function<Integer, ArrayList<String>> listWithCapacity = ArrayList::new;
```

The target type helps the compiler choose the no-arg constructor or the constructor taking `int`. If the API changes the target type, the selected constructor overload can change or become invalid.

### 4.5. Summary of Method Reference Forms

| Form | Syntax | Meaning |
| --- | --- | --- |
| Static method | `TypeName::staticMethod` | Call static method on type |
| Bound instance | `instance::method` | Call method on fixed receiver |
| Unbound instance | `TypeName::instanceMethod` | First parameter acts as receiver |
| Constructor | `TypeName::new` | Construct object via matching constructor |
| Array constructor | `TypeName[]::new` | Construct array with given input size |

Array constructor example:

```java
IntFunction<String[]> createArray = String[]::new;
String[] values = createArray.apply(3);
```

Method references are concise, yet do not allow writing extra parameter transformation logic, exception handling, or condition checks. When contracts change, an explicit lambda is often easier to adapt.

## 5. SAM Changes That Affect Lambdas and Method References

### 5.1. Changing Parameter Count

Suppose an old API accepts a single-parameter callback:

```java
@FunctionalInterface
interface ItemHandler {
    void handle(String item);
}
```

Call site:

```java
ItemHandler handler = item -> System.out.println(item);
```

If the contract changes to two parameters:

```java
@FunctionalInterface
interface ItemHandler {
    void handle(String item, int index);
}
```

The single-parameter lambda is no longer compatible. It must accept the extra parameter or use an adapter:

```java
BiConsumer<String, Integer> handler =
        (item, index) -> System.out.println(index + ": " + item);
```

Method references also need a method with a matching parameter count. `System.out::println` has multiple overloads, yet a two-parameter target type will not automatically turn it into an operation accepting two values. A lambda can be written to combine parameters.

### 5.2. Changing Parameter Types

Suppose an API switches from:

```java
Consumer<String> consumer = value -> process(value);
```

to `Consumer<Path>`. The lambda infers `value` as `Path`, so the body must use `Path` APIs. If the lambda explicitly declared `(String value) -> ...`, it will not be compatible with `Consumer<Path>`.

For method references, a new parameter type can make the method no longer fit:

```java
Function<String, Integer> parse = Integer::parseInt;
```

If the target switches to `Function<Path, Integer>`, `Integer.parseInt` does not accept `Path`. Explicit conversion is required:

```java
Function<Path, Integer> parseFileNameLength =
        path -> Integer.parseInt(path.getFileName().toString());
```

Do not fix by casting arbitrarily. Determine which data type the new API truly expects and whether the conversion is valid for all inputs.

### 5.3. Changing Return Type

If the SAM switches from `R` to `void`, or from `void` to `R`, lambda bodies and method references may no longer fit.

Old example:

```java
Function<String, Integer> length = String::length;
```

If the new API expects `Consumer<String>`, you can use:

```java
Consumer<String> printLength = value -> System.out.println(value.length());
```

Conversely, a method returning `void` cannot serve as the source for a `Function<T, R>` needing a value. Determine where the return value can come from; you cannot conjure a meaningful result by casting.

A special case: a method reference to a value-returning method can match a `Consumer` target when the call is a statement expression and the return value is discarded:

```java
Consumer<String> addToList = list::add;
```

`List.add` returns `boolean`, yet in a `Consumer` context, the result is ignored. This does not mean every value-returning method can replace any `void` method; the method must still match parameter and method-reference compatibility rules.

### 5.4. Changing Checked Exceptions

Checked exceptions are a key part of source contracts. Example:

```java
@FunctionalInterface
interface TextReader {
    String read(Path path) throws IOException;
}

TextReader reader = Files::readString;
```

`Files.readString(Path)` throws `IOException`, so the `TextReader` target permits this exception.

If the API changes to `Function<Path, String>`, the method reference above is no longer valid because `Function.apply` does not declare `IOException`. Handle the exception inside the lambda:

```java
Function<Path, String> reader = path -> {
    try {
        return Files.readString(path);
    } catch (IOException exception) {
        throw new UncheckedIOException(exception);
    }
};
```

Or keep a specialized functional interface if propagating checked exceptions is an intentional part of the API:

```java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T value) throws IOException;
}
```

If a SAM previously declared `throws IOException` and drops that declaration, lambdas calling APIs that throw `IOException` may stop compiling. If a SAM widens from `IOException` to `Exception`, callers invoking the SAM method may also have to handle the broader exception type. Changes to `throws` frequently impact source compatibility even without changing JVM method descriptors.

### 5.5. Changing Generic Types and Variance

Generic types determine the concrete target type of a lambda. Example:

```java
Function<String, Integer> length = String::length;
Function<CharSequence, Integer> lengthOfSequence = CharSequence::length;
```

The two variables have different types even though both represent taking length. `Function<String, Integer>` is not a subtype of `Function<CharSequence, Integer>` because generic types in Java are invariant.

APIs often use wildcards to accept functions more flexibly:

```java
static <T> void consumeAll(
        Iterable<T> values,
        Consumer<? super T> consumer) {
    for (T value : values) {
        consumer.accept(value);
    }
}
```

`? super T` allows the consumer to accept `T` or a supertype of `T`. For transformation functions, a common pattern is:

```java
static <T, R> List<R> mapAll(
        Iterable<T> values,
        Function<? super T, ? extends R> mapper) {
    List<R> result = new ArrayList<>();
    for (T value : values) {
        result.add(mapper.apply(value));
    }
    return result;
}
```

Inputs use `? super T` because the function can accept a broader type than `T`; outputs use `? extends R` because the function can return a subtype of `R`. If an API replaces wildcards with stricter invariant types, some method references or function variables being passed in may no longer be accepted.

### 5.6. Changing SAM Name or Method

Renaming the abstract method usually does not break lambda compilation at call sites if the functional interface type remains the same and lambdas do not invoke the SAM name directly. However, code directly calling `handler.oldName(...)`, method references to the SAM method itself, reflection, or frameworks relying on method names can be affected.

Example:

```java
@FunctionalInterface
interface RetryPolicy {
    boolean shouldRetry(int attempt);
}

RetryPolicy policy = attempt -> attempt < 3;
boolean retry = policy.shouldRetry(1);
```

If the SAM is renamed to `canRetry(int)`, the lambda assignment may stay valid yet the call `policy.shouldRetry(1)` will no longer compile. Therefore, when evaluating source compatibility, inspect both where lambdas are created and where interface methods are called.

## 6. Overload Resolution Can Change When Methods Are Added or Modified

Method references are often resolved by target type. If a library adds an overload or changes the overload set, an expression can become ambiguous or pick a different method.

For example, two APIs taking two different functional interfaces:

```java
static void configure(Function<String, String> mapper) {
    // ...
}

static void configure(UnaryOperator<String> mapper) {
    // ...
}
```

These two interfaces share the same parameter/return shape, yet `UnaryOperator<String>` is a subtype of `Function<String, String>`. Overloading APIs with functional interfaces in a subtype relationship easily makes lambda or method-reference calls hard to read and can lead to overload selection different from what the author expected. API design should avoid overloads differing only by nearly identical functional interfaces.

When the compiler reports an ambiguous method call, clarify the target type with an intermediate variable or cast:

```java
Function<String, String> mapper = String::trim;
configure(mapper);

configure((UnaryOperator<String>) String::trim);
```

Use casts only when intentionally selecting the corresponding overload. If an API change alters overload resolution, verify which method gets called and whether semantics remain accurate.

### 6.1. Overloads of the Referenced Method

A method reference can point to an overloaded method:

```java
Function<String, String> stringify = String::valueOf;
```

In this specific example, `String::valueOf` has multiple static overloads, yet the target type takes only one `String`. The compiler picks the matching overload. If the target type changes or the library adds overloads, resolution results can change.

When facing obscure errors, write an explicit lambda to give the compiler a call with clear context:

```java
Function<Object, String> stringify = value -> String.valueOf(value);
```

The lambda clarifies the input type and the body call. However, if `String.valueOf` has multiple overloads still matching `value`'s type, use a more specific parameter type or invoke a concrete overload.

### 6.2. Generic Method References and Type Inference

Method references to generic methods can depend heavily on target type:

```java
Function<String, String> identity = Function.identity();
```

When target type is lost or an API uses more complex wildcards, the compiler may fail to infer type arguments. An intermediate variable with a concrete type or a lambda declaring explicit parameter types often helps establish intent.

Do not add broad casts like `(Function) ...` to suppress errors. Raw types bypass generic checks and can push failures to runtime as `ClassCastException`.

## 7. API Changes From `Function` to Specialized Interfaces

A common library change is moving from general functional interfaces to specialized interfaces to express contracts more clearly or avoid boxing.

| Change | Potential impact | Handling |
| --- | --- | --- |
| `Function<T, Boolean>` → `Predicate<T>` | SAM changes from `apply` to `test`; `Function` variables cannot be passed directly | Change variable type and method reference, or use adapter `value -> old.apply(value)` |
| `Function<T, Integer>` → `ToIntFunction<T>` | Primitive `int` result; SAM changes to `applyAsInt` | Use compatible lambda/method reference and check boxing/null semantics |
| `Function<T, T>` → `UnaryOperator<T>` | More specific target type; `Function<T,T>` variables may not pass to `UnaryOperator<T>` parameter | Update declaration if matching contract or create an adapter |
| `Consumer<T>` → custom callback with added context | Parameter count or exception contract changes | Write lambda accepting the new context and update call sites |
| Custom SAM drops checked exception | Lambdas calling I/O no longer compile directly | Catch and translate exceptions or keep specialized I/O interface |

Example converting from `Function<String, Boolean>` to `Predicate<String>`:

```java
Function<String, Boolean> oldRule = value -> value.startsWith("J");

Predicate<String> newRule = value -> oldRule.apply(value);
```

In new code, declare `Predicate<String>` directly if the API expects a predicate:

```java
Predicate<String> newRule = value -> value.startsWith("J");
```

A detail to watch is that `Function<String, Boolean>` can return `null`, whereas `Predicate<String>` returns primitive `boolean`. If an adapter calls `oldRule.apply(value)` and receives `null`, unboxing to boolean can throw `NullPointerException`. Converting types is not just swapping interface names; nullability and semantics must be clarified.

## 8. A Method Reference May Remain Valid Yet Change Meaning

A method reference compiling successfully is not enough to prove equivalent behavior. The following changes can alter its meaning:

- A different overload is selected because target type or overload set changed.
- The referenced method changes semantics, default values, or error handling.
- The receiver of a bound method reference is created at a different time than the reader assumes.
- Generic types are inferred broader/narrower, changing actual runtime types of passed values.
- Boxing/unboxing appears or disappears when switching between wrapper and primitive functional interfaces.
- The new API invokes the callback multiple times, on a different thread, or at a different point in time than before.

For example, an API previously invoked a callback synchronously inside the method, while the new version stores the callback to invoke asynchronously. Lambdas/method references may still compile, yet mutable variable capture, thread-safety, and object lifetimes have changed. This is behavioral compatibility that requires separate testing.

Therefore, when upgrading callback APIs, read documentation on invocation timing, invocation count, threads, ordering, cancellation, and exception propagation, beyond just fixing compile errors.

## 9. Call-Site Conversion Strategies

### 9.1. Prefer Explicit Lambdas When Adaptation Is Needed

Method references fit when source signature and target type match directly. When parameters must change, data must be transformed, exceptions handled, or validation added, an explicit lambda expresses logic more clearly.

Example API changing from `Function<String, Integer>` to `ToIntFunction<Path>`:

```java
// Previously
Function<String, Integer> oldMapper = Integer::parseInt;

// After the contract requires Path -> int
ToIntFunction<Path> newMapper = path ->
        Integer.parseInt(path.getFileName().toString());
```

The lambda clearly shows `Path` is converted to a filename before parsing. If the filename is not a valid number, decide how to handle the error instead of letting `NumberFormatException` surface unexpectedly.

### 9.2. Use Adapters to Keep Old Modules Working During Transition

When multiple modules cannot migrate simultaneously, an adapter can translate between old and new contracts.

```java
static <T, U, R> Function<T, R> adapt(
        Function<? super T, ? extends U> before,
        Function<? super U, ? extends R> after) {
    return value -> after.apply(before.apply(value));
}
```

Example:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, String> label = number -> "ID-" + number;

Function<String, String> toLabel = adapt(parse, label);
System.out.println(toLabel.apply("42"));
```

Adapters let modules call new APIs while still accepting inputs from old modules. However, they need an owner and deadline if serving only migration. Once all consumers move to the new contract, remove adapters to avoid maintaining two ways to express the same operation.

### 9.3. Preserve Checked Exceptions Using Appropriate Functional Interfaces

If a callback performs I/O, you can define a functional interface explicitly declaring exceptions instead of wrapping unchecked at every call site:

```java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T value) throws IOException;
}

IOFunction<Path, String> readText = Files::readString;
```

If the new API only accepts `Function<Path, String>`, handle `IOException` inside the lambda or use another abstraction supported by the API. This decision affects where exceptions are handled and how callers observe errors.

### 9.4. Avoid Raw Types or Unchecked Casts

Patterns like the following typically mask problems:

```java
Function raw = (Function) someCallback;
```

Raw types skip generic checks. If actual types mismatch, failures can emerge late at runtime. Use concrete generic types, checked adapters, or explicit conversions.

## 10. Evaluation Process When Functional Contracts Change

When upgrading a library/framework that changes functional interfaces, follow this sequence:

### Step 1: Identify Old and New Contracts

Record:

- Functional interface and SAM names.
- Parameter count, order, and types.
- Return type, primitive/wrapper, and nullability.
- Generic parameters, bounds, and wildcards.
- Declared checked exceptions.
- New default/static methods or semantic changes.
- How the API invokes the callback: sync/async, invocation count, thread, and order.

### Step 2: Locate All Call Sites

Search for lambdas, method references, functional interface variables, methods taking/returning callbacks, and direct SAM calls. Do not search only for `->` or `::`; callbacks can be assigned via variables, returned from factories, stored in fields, or created by helper methods.

### Step 3: Compile to Categorize Errors

Compiler errors may indicate:

- Incompatible parameter types.
- Incompatible return type.
- Unhandled checked exception.
- Cannot infer type arguments.
- Reference to method is ambiguous.
- Method reference cannot be applied to given types.
- Functional interface is not valid because it has multiple abstract methods.

Group errors by category instead of fixing line by line by guesswork. One SAM change can cause dozens of identical errors across modules.

### Step 4: Choose Appropriate Fixes

- Keep method references if signatures still match and semantics are unchanged.
- Use explicit lambdas if types change or parameters/results must be transformed.
- Use adapters if multiple consumers must be supported during transition.
- Swap functional interfaces if the new API expresses the contract better.
- Disambiguate overloads or introduce intermediate typed variables if calls become ambiguous.
- Handle checked exceptions at a clearly designed boundary.

### Step 5: Test Behavior

Test normal cases, null/empty values, boundary data, conversion errors, checked exceptions, callback invocation counts, and how callbacks interact with threads/lifecycles. For overloaded method references, write a small test or assign to an explicit target-type variable to confirm which overload is chosen.

### Step 6: Remove Transition Layers Post-Migration

If adapters or legacy overloads were added solely for transition, monitor remaining consumers using them. Remove them once evidence confirms no caller still needs the old contract and the new API version is uniformly adopted.

## 11. Comprehensive Example: Callback API Changing From `Function` to `Predicate`

Suppose the old library version provides:

```java
public void filterNames(Function<String, Boolean> condition) {
    // ...
}
```

Consumer calls:

```java
filterNames(name -> name.startsWith("A"));
filterNames(String::isEmpty);
```

The new version changes the API:

```java
public void filterNames(Predicate<String> condition) {
    // ...
}
```

Inline lambdas may continue compiling because the compiler re-infers the target type. However, variables declared with the old type cannot be passed directly:

```java
Function<String, Boolean> condition = name -> name.startsWith("A");
filterNames(condition); // Incompatible with Predicate<String>
```

Convert the variable to the new type:

```java
Predicate<String> condition = name -> name.startsWith("A");
filterNames(condition);
```

If `Function` must be retained temporarily:

```java
Function<String, Boolean> oldCondition = name -> name.startsWith("A");
Predicate<String> adapted = name -> Boolean.TRUE.equals(oldCondition.apply(name));
filterNames(adapted);
```

The adapter uses `Boolean.TRUE.equals` to treat `null` returned by the old function as `false`, avoiding unboxing errors. This is a semantic decision that must be confirmed against business requirements; if `null` must be treated as an error, throw an explicit exception instead of silently converting it to `false`.

For `String::isEmpty`, the method reference can continue matching `Predicate<String>` because `isEmpty()` returns primitive boolean and takes a `String` receiver. Still, verify the method reference points to the desired overload/type if the target API changes further.

## 12. Designing Callback APIs to Reduce Compatibility Risk

Library authors can lower migration costs with several guidelines:

- Choose built-in JDK functional interfaces when the contract fits; avoid creating multiple interfaces of the same shape without clear reason.
- Name methods and generic parameters to express intent accurately, especially distinguishing predicates, mappings, and consumers.
- Use sensible wildcard variance, such as `Predicate<? super T>` or `Function<? super T, ? extends R>`, to reduce unnecessary constraints on consumers.
- Avoid overloading methods differing only by two functional interfaces with identical arity and nearly equivalent return types.
- Keep checked exception contracts stable or provide a clear abstraction for fallible operations.
- Clearly specify how many times callbacks are invoked, synchronously or asynchronously, on which thread, and whether they may run after the method returns.
- When a SAM must change, consider supplying an adapter/default method or a differently named new API during a transition window.
- Use `@FunctionalInterface` so the compiler protects SAM design intent.
- Provide release notes and migration examples for target-type, generic, exception, or overload changes.

Do not preserve old APIs forever merely to avoid all changes. What matters is having a planned roadmap, deprecation warnings where appropriate, and migration examples clear enough for consumers to fix correctly.

## 13. Common Errors When Migrating Lambdas and Method References

| Symptom | Common cause | Handling |
| --- | --- | --- |
| Lambda no longer compiles | SAM parameter count/types or return type changed | Read new SAM signature and update lambda for the new target type. |
| Method reference finds no matching method | Source method does not match target type parameters/result | Write an explicit lambda to convert clearly or pick a specific overload. |
| Unhandled checked exception | New functional interface does not declare that exception | Catch/convert the exception or use an interface with matching throws. |
| Cannot infer type arguments | Generic bounds/wildcards or target type changed | Declare variable types, type witnesses, or explicit lambda parameter types. |
| Ambiguous method call | Multiple overloads accept similar functional interfaces | Extract target-type variable or cast intentionally; review overload design. |
| `NullPointerException` after switching `Function<T, Boolean>` to `Predicate<T>` | Null `Boolean` result unboxed to `boolean` | Define null semantics and convert intentionally. |
| Callback still compiles yet runs differently | Invocation timing, count, thread, or semantics changed | Read runtime contract and add integration/concurrency tests. |
| Lambda reports multiple abstract methods | Interface is no longer a SAM | Add default implementation or implement the interface with a concrete class. |

## 14. Conclusion

Lambdas and method references are always checked against their target functional interface. When a functional contract changes, inspect SAM signatures, generic types, return types, checked exceptions, overload resolution, and how callbacks execute. A method reference may still compile yet select a different overload or behave differently; an inline lambda may adapt automatically through target typing while a functional-interface variable declared with the old type can no longer be passed.

During migration, first clarify the old and new contracts, locate all call sites, classify compiler errors, and choose among method references, explicit lambdas, and adapters. Finally, test callback behavior—invocation count, threads, exceptions, and null semantics—to ensure source changes accurately reflect the library's new contract.
