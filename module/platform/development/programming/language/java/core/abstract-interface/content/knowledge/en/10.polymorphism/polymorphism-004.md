# Selecting overloads at compile time and overrides at runtime in Java

In Java, a method call can go through **two different decisions**:

1. **Overload resolution**: the compiler selects the **method signature** that matches the *static type* of the receiver expression, the *static types* of the arguments, and the parameter conversion rules.
2. **Override dispatch**: for polymorphic instance methods, the JVM selects the **implementation** of the chosen signature based on the *actual class of the receiver object* at runtime.

Therefore, an easy phrase to remember is that **overload is selected at compile time; override is selected at runtime**. However, the scope of this statement must be understood accurately: runtime does not “re-select an overload” based on the actual class of the argument; it looks up the appropriate implementation for the signature decided during compilation. `static` methods, `private` methods, constructors, and `super` call cases follow different rules from ordinary polymorphic instance method calls.

This lesson focuses on Java Core, specifically distinguishing between **declared type** and **actual type**, how overload and override work together in the same call expression, and common mistakes when using inheritance, interfaces, `null`, boxing, and varargs.

## 1. Distinguishing the two mechanisms

| Criterion | Overload | Override |
| --- | --- | --- |
| Idea | Multiple methods with the same name but different parameter lists | A subclass/implementation provides new behavior for an inherited instance method or one declared in an interface |
| Method distinction | By name and parameter types/count/order (along with Java's signature rules) | Same signature eligible for overriding; return type must be compatible |
| Where is it chosen? | **Compile time**: checks the set of available methods and selects the specific call | **Runtime**: looks up the matching implementation on the actual class of the receiver |
| Key factors | Static types of receiver and arguments, conversions, specificity | Runtime class of the receiver, inheritance relationship, and overriding method |
| Example | `print(Object)` and `print(String)` | `Animal.speak()` overridden by `Dog` |
| Limitations to remember | Changing only the return type does not create a valid overload | `static` is hiding; `private` is not overridden; `final` cannot be overridden |

Overload example:

~~~java
void show(Object value) { }
void show(String value) { }
~~~

Override example:

~~~java
class Base {
    String name() { return "Base"; }
}

class Child extends Base {
    @Override
    String name() { return "Child"; }
}
~~~

The two blocks above only illustrate declarations inside a class; they are not two standalone runnable programs.

**Static type** is the type Java knows at compile time; for example, the variable `Animal pet` has static type `Animal`. The **runtime type** of the object can be `Dog` if `pet = new Dog()`. For overload, `pet` is treated as `Animal`; for override, the selected instance method can execute the code belonging to `Dog`.

## 2. Complete Java 17 program: overload and override appearing together

Create the file **OverloadOverrideDemo.java** with the following content:

~~~java
public class OverloadOverrideDemo {
    static class Animal { }
    static final class Dog extends Animal { }
    static final class Cat extends Animal { }

    static class Handler {
        String handle(Animal value) {
            return "Handler.handle(Animal)";
        }

        String handle(Dog value) {
            return "Handler.handle(Dog)";
        }

        static String identify(Animal value) {
            return "Handler.identify(Animal)";
        }
    }

    static final class FastHandler extends Handler {
        @Override
        String handle(Animal value) {
            return "FastHandler.handle(Animal)";
        }

        @Override
        String handle(Dog value) {
            return "FastHandler.handle(Dog)";
        }

        // NEW overload; does not override any method in Handler.
        String handle(Cat value) {
            return "FastHandler.handle(Cat)";
        }

        // Hiding static method; NOT an override.
        static String identify(Animal value) {
            return "FastHandler.identify(Animal)";
        }
    }

    static String choose(long value) {
        return "choose(long)";
    }

    static String choose(Integer value) {
        return "choose(Integer)";
    }

    static String choose(int... values) {
        return "choose(int...)";
    }

    static String print(Object value) {
        return "print(Object)";
    }

    static String print(String value) {
        return "print(String)";
    }

    public static void main(String[] args) {
        Handler handler = new FastHandler();
        Animal animalDog = new Dog();
        Dog dog = new Dog();
        Cat cat = new Cat();

        System.out.println("1: " + handler.handle(animalDog));
        System.out.println("2: " + handler.handle(dog));
        System.out.println("3: " + handler.handle(cat));
        System.out.println("4: "
                + ((FastHandler) handler).handle(cat));

        System.out.println("5: " + choose(7));
        Integer boxed = 7;
        System.out.println("6: " + choose(boxed));
        System.out.println("7: " + choose());

        Object text = "hello";
        System.out.println("8: " + print(text));
        System.out.println("9: " + print("hello"));
        System.out.println("10: " + print(null));

        System.out.println("11: " + Handler.identify(dog));
        System.out.println("12: " + FastHandler.identify(dog));
    }
}
~~~

Compile and run commands, JDK 17 or later:

~~~bash
javac -encoding UTF-8 OverloadOverrideDemo.java
java OverloadOverrideDemo
~~~

Standard output of the program:

~~~text
1: FastHandler.handle(Animal)
2: FastHandler.handle(Dog)
3: FastHandler.handle(Animal)
4: FastHandler.handle(Cat)
5: choose(long)
6: choose(Integer)
7: choose(int...)
8: print(Object)
9: print(String)
10: print(String)
11: Handler.identify(Animal)
12: FastHandler.identify(Animal)
~~~

There is no randomness, threading, or network I/O in this example; return values are determined by Java's rules, so the output lines above can be explained step by step.

### 2.1. Why does line 1 call `FastHandler.handle(Animal)`?

~~~java
Handler handler = new FastHandler();
Animal animalDog = new Dog();
handler.handle(animalDog);
~~~

At compile time:

- The receiver `handler` has static type `Handler`, so the compiler considers `handle(Animal)` and `handle(Dog)` from `Handler`'s API.
- The argument expression `animalDog` has static type `Animal`, even though the referenced object is a `Dog`.
- `Animal` does not automatically convert down to `Dog`, so the chosen overload is **`handle(Animal)`**.

At runtime:

- The actual receiver is a `FastHandler` object.
- `FastHandler` has overridden `handle(Animal)`, so **`FastHandler.handle(Animal)`** runs.

**There is no third step that looks at the `Dog` object and switches to `handle(Dog)`.** This is the core point of the lesson.

### 2.2. What do lines 2, 3, and 4 change?

| Call | Receiver static type | Argument static type | Selected overload | Runtime implementation |
| --- | --- | --- | --- | --- |
| `handler.handle(animalDog)` | Handler | Animal | `handle(Animal)` | `FastHandler.handle(Animal)` |
| `handler.handle(dog)` | Handler | Dog | `handle(Dog)` | `FastHandler.handle(Dog)` |
| `handler.handle(cat)` | Handler | Cat | `handle(Animal)` | `FastHandler.handle(Animal)` |
| `((FastHandler) handler).handle(cat)` | FastHandler | Cat | `handle(Cat)` | `FastHandler.handle(Cat)` |

Line 3 often surprises people: even though `FastHandler` has `handle(Cat)`, the receiver variable is declared as `Handler`. The compiler can only consider the set of methods provided by the `Handler` type; `handle(Cat)` is not in that set, so `Cat` is passed to `handle(Animal)`. Runtime only dispatches the override of `handle(Animal)`.

Line 4 uses a cast to `FastHandler`, changing **the static type of the receiver expression to `FastHandler`**. Only then does the `handle(Cat)` overload become available and get selected. The cast is safe here because the actual object is a `FastHandler`; for a `Handler` instance that is not a `FastHandler`, such a cast can cause a `ClassCastException`. Do not turn casting into a general solution for API design.

## 3. Order of reasoning for a method call

You can read a `receiver.method(argument)` call according to this process:

~~~text
COMPILE TIME
  |
  +-- What is the static type of the receiver?
  |
  +-- What is the set of accessible methods with a matching name?
  |
  +-- What are the static types and count of the arguments?
  |
  +-- Which overloads are applicable under Java's conversion rules?
  |
  +-- Which method is the most specific? Is there any ambiguity?
  |
  +-- Record the selected method signature/target.
  |
RUNTIME (for polymorphic instance method calls)
  |
  +-- Evaluate the receiver and arguments, checking for null when necessary.
  |
  +-- What class does the actual receiver belong to?
  |
  +-- Which method in that class overrides the selected signature?
  |
  +-- Execute the corresponding implementation.
~~~

This diagram is a summary for learning purposes. The normative details on lookup, accessibility, overload applicability, and call dispatch are in the **Java Language Specification, Section 15.12 (Method Invocation Expressions)**. Rules for `super`, `static`, `private`, interfaces, generics, and special kinds of method invocation have their own details; do not interpret the diagram as a bytecode algorithm for every kind of call.

A runtime object determines the implementation only if Java performs an overridable instance dispatch. For non-overridable methods or `super` calls, the JVM does not freely look up another override in the usual way.

## 4. What does the compiler base overload selection on?

Overloading means multiple declarations with the same name and different **parameter lists**. Parameter order matters:

~~~java
void transfer(String from, int amount) { }
void transfer(int amount, String from) { }
~~~

The two methods above are two different overloads. Conversely, two declarations `String read(int x)` and `int read(int x)` in the same class are **invalid**: differing only in return type is not enough to create an overload.

Adding a different `throws` clause or renaming parameter variables does not create a new overload signature either. For generics, watch out for **type erasure**: two declarations that look different in their generic parameters sometimes have the same erasure and therefore cannot coexist.

### 4.1. The compiler checks applicability in multiple phases

Simplifying the phases Java uses when selecting an overload:

1. **Strict invocation**: prioritizes methods applicable without needing boxing/unboxing or variable-arity varargs calls; standard conversions such as widening primitive (`int` → `long`) and widening reference (`String` → `Object`) can be used.
2. **Loose invocation**: if the first phase finds no applicable overload, additionally allows boxing/unboxing conversions and combinations accepted by Java.
3. **Variable arity invocation**: if there is still no applicable method, considers variable-length varargs calls.

Once a candidate set is obtained in the selected phase, the compiler chooses the **most specific** method according to Java's rules. If there is no single valid choice, it reports an *ambiguous method call* error at compile time. It is incorrect to say that Java always “chooses the method needing the fewest conversions” in a generic conversion-counting sense; the rule set has distinct phases and specificity criteria.

That is why the example:

~~~java
choose(7);
~~~

calls `choose(long)`: the literal `7` has type `int`. Converting `int` to `long` via **primitive widening** already applies in the strict phase. `choose(Integer)` requires boxing, so it is not prioritized ahead of a method already valid in the first phase. `choose(int...)` in the example is the varargs option when there are no candidates in earlier phases; when calling `choose()`, the single-parameter `long` and `Integer` overloads do not apply, leaving only varargs.

With:

~~~java
Integer boxed = 7;
choose(boxed);
~~~

`Integer` matches `choose(Integer)` directly in the strict phase. `choose(long)` requires unboxing and widening, so line 6 calls `choose(Integer)`.

**Note on varargs:** a method declared with `int...` can accept an `int[]` array in a fixed-arity call. You cannot always conclude that “anything with three dots is only considered last”. The varargs-phase rule is about **variable arity invocation**; a method declared with varargs can still apply in an earlier phase when the argument has the exact array type.

### 4.2. The static type of a variable determines the overload

In the main program:

~~~java
Object text = "hello";
print(text);      // print(Object)
print("hello");   // print(String)
print(null);      // print(String)
~~~

First case: `text` has static type `Object`, so it cannot be passed directly to `print(String)`; actually referencing a string does not change the compile-time decision. Second case: the literal `"hello"` has type `String`, so `print(String)` is more specific than `print(Object)`. Last case: the `null` literal can be passed to both `Object` and `String`, but `String` is a subtype of `Object`, so `print(String)` is more specific.

Be careful: `null` does not have a runtime class that helps “choose a method”; the decision is still made at compile time.

### 4.3. Overloads can be ambiguous even when each is valid

The following example intentionally **does not compile** if placed in the same class:

~~~java
static void show(String value) { }
static void show(Integer value) { }

// show(null); // Compile error: ambiguous method call.
~~~

`null` is compatible with both `String` and `Integer`, but neither type is a subtype of the other, so there is no single more specific overload.

Another ambiguous case:

~~~java
static void combine(CharSequence value) { }
static void combine(java.io.Serializable value) { }

// combine("hello"); // Compile error: ambiguous method call.
~~~

`String` implements both `CharSequence` and `Serializable`, while the two parameter types have no subtype relationship to favor a single overload.

The snippets in Section 4.3 are only for analyzing compilation errors and **do not belong to OverloadOverrideDemo.java**. If you truly need to select one overload, you can pass an argument with an explicit static type, such as casting `(String) null` to choose `show(String)`; this is a technique for clarifying intent, not a substitute for API design that avoids ambiguous overloads.

## 5. Runtime dispatch occurs only with a matching override

Take another simple example: the subclass adds no overloads and only overrides the same signature.

~~~java
class Speaker {
    String speak() {
        return "Speaker";
    }
}

class LoudSpeaker extends Speaker {
    @Override
    String speak() {
        return "LoudSpeaker";
    }
}
~~~

Place the code above in an appropriate Java context and call:

~~~java
Speaker s = new LoudSpeaker();
System.out.println(s.speak()); // LoudSpeaker
~~~

Here, **there is no overload** `speak(...)` to compare. The compiler recognizes `Speaker.speak()` in the static type `Speaker`. The JVM invokes the overriding implementation in `LoudSpeaker` based on the runtime class of `s`.

When calling an overridden method through an interface type, the principle remains the same:

~~~java
interface Reporter {
    String report();
}

class PlainReporter implements Reporter {
    @Override
    public String report() {
        return "plain";
    }
}
~~~

Example inside a method:

~~~java
Reporter r = new PlainReporter();
System.out.println(r.report()); // plain
~~~

`Reporter` describes the contract; the runtime class `PlainReporter` provides the implementation. When a class has multiple inherited implementations, Java has override and default-method selection rules to determine which method will run. That does not cause overloads to be selected based on the runtime object of an argument.

## 6. `static`, `private`, `final`, and `super`: exceptions you must understand

Having two methods with the same name in a parent and child class does not automatically make an override.

| Situation | Actual mechanism | Consequence |
| --- | --- | --- |
| Subclass defines an instance method with the same valid signature as the superclass | **Override** | Dispatched based on the runtime receiver |
| Subclass defines a `static` method with the same signature as the superclass's `static` method | **Method hiding** | Not dynamically dispatched based on the runtime receiver |
| A `private` method with the same name/signature appears in both classes | Two separate methods | The parent's private method is not overridden |
| A `final` method in the parent class | Cannot be overridden in the subclass | Attempting to override causes a compile-time error |
| `super.method()` in a subclass | Calls the implementation of the specified superclass under `super` semantics | Does not dispatch back to the subclass's own override |
| Constructor with the same name as the class | Constructor overloading, not constructor overriding | Constructors are not inherited and do not participate in dynamic dispatch like instance methods |

Lines 11 and 12 in the complete program illustrate **static hiding**:

~~~java
Handler.identify(dog);      // Handler.identify(Animal)
FastHandler.identify(dog);  // FastHandler.identify(Animal)
~~~

The `FastHandler` class redeclares static `identify(Animal)`; it **hides** the superclass's static method rather than overriding it. You should call static methods using the **class name** as shown above. Java allows certain forms of static access through an instance variable, but that style misleads readers into thinking static methods have runtime dispatch.

In practice, `private` helpers are commonly used to hold internal logic, while `final` methods are used when you want to prevent subclasses from changing a method's behavior. Both should be chosen based on design intent, not merely to avoid polymorphism.

## 7. Overload and override can work together without swapping roles

Suppose you build a data-processing API:

~~~java
class ParentProcessor {
    String process(Object input) {
        return "Parent object";
    }
}

class ChildProcessor extends ParentProcessor {
    @Override
    String process(Object input) {
        return "Child object";
    }

    String process(String input) {
        return "Child string";
    }
}
~~~

Illustrative expressions:

~~~java
ParentProcessor p = new ChildProcessor();
Object value = "abc";

// p.process(value) -> "Child object"
// p.process("abc") -> "Child object"
// ((ChildProcessor) p).process("abc") -> "Child string"
~~~

In both calls through `p`, the compiler only sees `ParentProcessor`'s `process(Object)`; runtime finds `ChildProcessor`'s override of `process(Object)`, even when the argument is a string. Only when the static receiver becomes `ChildProcessor` does the `process(String)` overload become a candidate for the compiler to consider.

Do not design a system expecting overload to automatically become **double dispatch** on both the receiver and the arguments. Standard Java dispatches once based on the runtime receiver for the selected signature; it does not inspect the runtime types of all arguments to find the best-matching overload.

If the business goal is to process differently based on **the runtime type of an argument**, deliberate options include:

- Calling the overload at a place where the specific static type has already been determined.
- Using a polymorphic contract on the argument object itself, so that the object invokes the appropriate logic (for example, `animal.accept(visitor)` in the Visitor pattern when multiple dispatches are genuinely needed).
- Using `instanceof` with Java pattern matching when the type branches are finite, clear, and appropriate for the context.

You should not apply a complex design pattern just because you have two overloads; prefer a clear API and easily testable logic.

## 8. Overload with inheritance, generics, and type erasure

When inheritance and generics are involved, keep additional rules in mind:

**Overload resolution is still based on expressions at compile time.** If declared as `List<Animal>` and the runtime object is actually created from `ArrayList<Animal>`, the call is still based on the methods visible through the static type `List<Animal>`.

**Type erasure affects signatures at the JVM level.** Two methods with the same name differing only in generic parameters, such as:

~~~java
void load(java.util.List<String> values) { }
void load(java.util.List<Integer> values) { }
~~~

cannot be declared together in one class: after erasure, both have a `List` parameter, leading to a **name clash**. This is an intentionally invalid code example; do not place it in a runnable file.

**Overriding with generics can still be dynamically dispatched.** The compiler may generate a *bridge method* to preserve overriding after erasure and for covariant return types. This is a compiler/JVM compatibility detail; from the programmer's perspective, valid calls still follow the rules of overload at compile time and override at runtime.

Conceptual example of a bridge method:

~~~java
interface Converter<T> {
    T convert(T value);
}

final class UppercaseConverter implements Converter<String> {
    @Override
    public String convert(String value) {
        return value.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

When using `Converter<String> converter = new UppercaseConverter();`, calling `converter.convert("java")` returns `"JAVA"`. With generics, the compiler creates/implements the necessary mechanisms so that `UppercaseConverter`'s implementation matches the interface method after erasure; API users do not need to call bridge methods manually.

Be careful not to confuse **override-equivalent signatures**, subsignature rules, erasure, and overloading. Subtle cases should be cross-checked against the JLS and compile-tested on the target Java version.

## 9. Mental-model mistakes that lead to bugs

| Misconception | What Java actually does | How to verify |
| --- | --- | --- |
| “If the argument object is a Dog, the Dog overload is automatically selected” | Overload checks the **static** type of the argument expression | Write down the declared type of each variable and the list of available overloads |
| “Because the receiver is a FastHandler, all overloads specific to FastHandler are usable” | The overload set is determined by the **static** type of the receiver | Try replacing `Handler h` with `FastHandler h` and observe the difference |
| “Override re-decides the parameter types” | Override selects the implementation for an already-determined signature | Write down the compile-time signature first, then determine the runtime class |
| “A `static` method with the same name in a subclass is an override” | This is method hiding | Use the class name when calling static methods; do not expect polymorphism |
| “Changing only the return type is overloading” | It does not create a different overload signature | Compare method names and parameter lists |
| “Boxing is always preferred over widening” | Strict-phase rules can choose primitive widening before boxing | Check method applicability phase by phase |
| “`null` always selects an overload with a reference type” | It may select a more specific subtype or be ambiguous | Compare subtype relationships among parameter types |
| “Every method with varargs is only considered in the final phase” | A varargs method can also apply in fixed-arity form when receiving an appropriate array | Distinguish a `T[]` parameter type from varargs expansion |
| “If there is an override, calling via `super` still runs the subclass override” | `super.method()` has semantics to call the version selected from the superclass | Check the invocation kind and the scope of the `super` keyword |

## 10. A method for analyzing any call

When encountering hard-to-read code, fill in the following two steps before predicting the output:

~~~text
Step 1 — COMPILE TIME:
  Static type of receiver: ...
  Static type of argument: ...
  Visible overloads: ...
  Selected overload/signature: ...

Step 2 — RUNTIME:
  Actual class of receiver: ...
  Valid override for the signature from Step 1? ...
  Executed implementation: ...
~~~

Applying this to the example:

~~~java
Handler h = new FastHandler();
Animal a = new Dog();
h.handle(a);
~~~

We get:

~~~text
Step 1 — COMPILE TIME:
  Receiver: Handler
  Argument: Animal
  Overloads: handle(Animal), handle(Dog)
  Selected signature: handle(Animal)

Step 2 — RUNTIME:
  Actual receiver: FastHandler
  Override: FastHandler.handle(Animal)
  Result: "FastHandler.handle(Animal)"
~~~

This is a more reliable way to check than just looking at the expression `new Dog()` and guessing Java will call the method closest to `Dog`.

## 11. Exercises with answers

### Exercise 1 — Declared type differs from actual type

Suppose a class has two overloads `test(Object)` and `test(String)`:

~~~java
Object x = "ABC";
// Which signature will test(x) select?
~~~

**Answer:** `test(Object)`, because `x` has static type `Object`. The actual string `"ABC"` does not make the compiler re-select `test(String)`.

### Exercise 2 — Override without a new overload

~~~java
class A {
    String label(Number x) { return "A"; }
}
class B extends A {
    @Override
    String label(Number x) { return "B"; }
}

A ref = new B();
// What does ref.label(Integer.valueOf(9)) return?
~~~

**Answer:** `"B"`. The compiler selects `label(Number)`, because `Integer` can be converted up to `Number`. The runtime receiver is `B`, so the override `B.label(Number)` is used. The `ref` declaration and call need to be placed inside a method when used as a complete program.

### Exercise 3 — When an overload is ambiguous

Given two overloads `test(String)` and `test(Integer)`, does calling `test(null)` run either method?

**Answer:** No; the compiler reports an ambiguity error because neither overload is more specific than the other. You can clarify the target with `test((String) null)` if that is genuinely the program's intent.

### Exercise 4 — A subclass overload “hidden” by the receiver's static type

Using `Handler`, `FastHandler`, and `Cat` from the main program, why does `Handler h = new FastHandler(); h.handle(new Cat());` not call `FastHandler.handle(Cat)`?

**Answer:** The receiver's static type is `Handler`, and `Handler` does not declare `handle(Cat)`. The compiler selects `handle(Animal)`, and then runtime looks up the override `FastHandler.handle(Animal)`. Java does not perform overload resolution again at runtime.

### Exercise 5 — Primitive widening, boxing, and varargs

With `choose(long)`, `choose(Integer)`, and `choose(int...)` as in the main program, explain the results of `choose(7)`, `choose(Integer.valueOf(7))`, and `choose()`.

**Answer:** They respectively select `long` (primitive widening applies in the strict phase), `Integer` (exact reference match), and `int...` (the variable-arity phase for 0 arguments).

## 12. Takeaways for API design

- **Use overload** when multiple operations share the same meaning but accept different forms of data. Avoid overload pairs that can easily become ambiguous with `null`, auto-boxing, or parent/child types.
- **Use override** when the same instance contract needs different behavior depending on the runtime implementation; in that case, consumers should work through the appropriate parent type/interface.
- **Do not rely on runtime arguments to choose an overload.** If you want to branch based on an argument's runtime type, you need a design that explicitly controls dispatch.
- **When debugging a call, determine the compile-time signature first.** Only then look up the implementation based on the runtime receiver. For static, private, or `super`, apply their specific rules instead of the dynamic override model.
- **Read compile error messages about ambiguous overload, incompatible types, and name clash.** These errors indicate that the compiler could not find a single valid signature from the static type information.

The key point: **overload answers “which parameter list of the method are we calling?”, whereas override answers “what is the implementation of that method on the current object?”**. Separating these two questions helps explain Java polymorphism accurately, even when declared types, actual types, and overloads in parent/child classes differ.
