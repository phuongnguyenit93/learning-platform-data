# Prerequisites, Java Core Scope, and Learning Sequence for Reflection

## 1. Purpose of This Roadmap

Reflection allows Java to discover a type's metadata while the program is running and, when permitted, locate constructors, methods, or fields for dynamic manipulation. This topic sits at the intersection of **data types**, **method invocation mechanisms**, **access permissions**, and **metadata**. Learning in a logical order helps you tell apart when you are merely observing structure and when the program is actually executing code or mutating state.

This lesson serves as a **learning map**: defining the required foundation, the boundaries of Reflection within Java Core, the practice sequence, and self-assessment criteria. The dedicated lessons in this chapter explain each API, generic mechanisms, annotations, and related design choices in detail.

After this lesson, you should be able to answer for yourself: "Do I have enough background to start?", "What do I need to learn before trying to invoke a method via Reflection?", and "What kind of practice exercise proves I truly understand instead of just copying runnable code?"

## 2. Recommended Knowledge Before Starting

| Foundation | What You Should Be Able to Do | Connection to Reflection |
| --- | --- | --- |
| Classes and instances | Create objects, distinguish reference variables from real objects | `Class<?>` represents a type; objects hold state |
| Constructors, fields, methods | Write parameterized constructors and methods with return values | Corresponding metadata objects exist: `Constructor`, `Field`, `Method` |
| Inheritance and interfaces | Distinguish overriding from overloading, understand inherited methods | Member lookup results depend on types, signatures, and inheritance rules |
| Access scope | Understand `public`, `protected`, package-private, `private`, `static` | Finding metadata does not mean access is permitted |
| Packages, JDK, and classpath | Compile/run Java files, know fully qualified class names | `Class.forName` needs a binary name and an appropriate class loader |
| Primitives, wrappers, arrays | Distinguish `int` from `Integer` and array types | Constructor/method lookups require exact parameter types |
| Exceptions | Read stack traces, recognize checked and unchecked exceptions | Lookup, instantiation, and dynamic-call errors happen at different steps |
| Generics and annotations | Know `List<String>`, wildcards, `@Annotation` syntax | Prepares you for type erasure, `Type`, and runtime retention |

**Minimum bar:** You can start the metadata observation section if you know how to write a class, create instances, and call regular methods. Before diving into generics/annotations, review the corresponding concepts; mastering both from the very first lesson is not required.

### 10-Minute Self-Check Exercise

Write a `Student` class yourself with a `private String name` field, a `public Student(String name)` constructor, and a `public String greet()` method. Then, without using Reflection:

1. Create two objects with different names and explain why they share the same type yet hold separate state.
2. Add a subclass `GraduateStudent` that overrides `greet()`. Predict the result when calling through a variable of type `Student`.
3. Add an overload `greet(String prefix)` and explain how the compiler distinguishes the two signatures.
4. Try changing a method to `private` and observe the error when calling it from outside the class.

If these steps are still difficult, strengthen classes/objects, polymorphism, access scope, and exceptions first. That foundation is essential for understanding why a `Method` can be found yet an `invoke` call can still fail.

## 3. Scope of Reflection in Java Core

This chapter focuses on APIs built into the JDK:

- **`java.lang.Class`:** runtime type identification, type names, superclasses, interfaces, and member discovery.
- **`java.lang.reflect`:** `Constructor`, `Method`, `Field`, `Modifier`, and `Type` for reading metadata; creating objects, invoking methods, or reading/writing fields only with clear intent and valid permissions.
- **Runtime annotations:** reading annotations according to retention and declaration location, distinguishing metadata from framework processing logic.
- **Boundaries of Reflection:** declared/inherited, access control, the Java Platform Module System (JPMS), type erasure, exceptions, performance, and maintainability.

**Out of primary scope:** building a full DI container/ORM from scratch, bytecode manipulation with ASM/Byte Buddy, instrumentation agents, JNI, complex `ClassLoader` mechanisms, or advanced optimization with `MethodHandle`/`VarHandle`. Those topics may use or complement Reflection, but they are not prerequisites for mastering the core APIs.

Reflection also does not replace interfaces, polymorphism, or direct calls. If the program already knows the types and behaviors at compile time, prefer normal Java APIs. When a library must inspect types supplied by another application at runtime, that is where Reflection shows its clear value.

## 4. A Small Starting Point: Reading Metadata Only

Your first hands-on step should **observe** before instantiating or calling dynamically. Create the file `FirstMetadataCheck.java`:

~~~java
import java.lang.reflect.Method;

public class FirstMetadataCheck {
    public static void main(String[] args) throws NoSuchMethodException {
        Class<?> type = String.class;
        Method method = type.getMethod("substring", int.class);

        System.out.println(type.getName());
        System.out.println(method.getName());
        System.out.println(method.getReturnType().getSimpleName());
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac FirstMetadataCheck.java
java FirstMetadataCheck
~~~

Output:

~~~text
java.lang.String
substring
String
~~~

You just obtained a `Class<?>`, looked up metadata for a public method taking an `int` parameter, and read its return type. No `String` object was mutated, nor was `substring` invoked. Try replacing `int.class` with `Integer.class` to observe `NoSuchMethodException`: signature lookup in Reflection does not treat primitives and wrappers as the same type.

This example introduces only the first skill. When moving on to invoking methods or creating instances, you will use `Method.invoke` or `Constructor.newInstance` and will also need receiver checks, access permissions, and error handling.

## 5. Learning Sequence: From Understanding Types to Controlled API Usage

| Stage | Focus | Evidence of Understanding |
| --- | --- | --- |
| **0. Java Core Review** | Classes/objects, overloading, overriding, constructors, access modifiers, and exceptions | Complete the `Student` exercise without using Reflection |
| **1. Static and Runtime Types** | `SomeType.class`, `obj.getClass()`, `Class.forName`; distinguishing variable type from object's actual class | Explain why `Animal a = new Dog()` has two type perspectives |
| **2. Structure Discovery** | `Class` and the `get...` / `getDeclared...` families; names, modifiers, constructors, methods, fields | List members, distinguish declared/public/inherited, without relying on return order |
| **3. Observation vs. Execution Boundary** | Metadata vs. `Field.get`, `Field.set`, `Method.invoke`, `Constructor.newInstance` | Point out which lines read metadata and which lines can mutate state |
| **4. Metadata in Type Relationships** | Inheritance, generic `Type`, type erasure, runtime annotations, and `@Inherited` | Explain why declaration metadata can exist even when an instance's type argument is erased |
| **5. Limits and Errors** | Wrong names/signatures, access permissions, JPMS, exceptions thrown by target methods, untrusted input | Diagnose the exact failing step instead of blindly adding `setAccessible(true)` |
| **6. Integration and Design Choices** | Plugin example, inspector, interfaces/`ServiceLoader`, performance and maintainability trade-offs | Know when Reflection is necessary and when direct APIs suffice |

This roadmap does not require memorizing dozens of method names. At each stage, note three things: **what the input data is**, **what the returned object/API represents**, and **when a call can execute code or throw an error**.

### Four Checkpoints to Pass

**Checkpoint A — Know which type you are inspecting.** Create a superclass-typed variable holding a subclass instance. Compare the outputs of `Parent.class` and `instance.getClass()`; explain them in terms of compiler and runtime. If you do not understand this difference, do not use `getDeclaredMethods()` to infer "every callable method."

**Checkpoint B — Separate lookup from action.** From a `Class<?>`, read only member names, modifiers, and signatures; verify that the target method has not been called. Then intentionally perform one `invoke` call and observe the state change to see the transition point.

**Checkpoint C — Understand metadata limits.** Read the generic signature of a `List<String>` field and compare it with `getClass()` of an `ArrayList` object; test an annotation with `RetentionPolicy.RUNTIME`. Explain why declaration metadata does not guarantee that runtime values satisfy every generic constraint.

**Checkpoint D — Contract-based design.** Load an implementation from configuration, verify that it actually implements the published interface, and then invoke business logic through the interface. Evaluate whether a factory/registry or `ServiceLoader` could solve the requirement more simply.

## 6. Capstone Practice: Building ClassInspector

After completing the stages, write `ClassInspector` that takes a `Class<?>` and generates a report about the type. The first goal is a **read-only tool**, since discovery tasks do not need to automatically execute business code.

The initial version should print the binary name and simple name, superclass, direct interfaces, constructors, methods, and fields along with their modifiers. Test it on three types: a simple class, a subclass with overridden methods, and a class with runtime annotations.

Enhance iteratively:

1. Let the user choose **declared members only** or **inheritable public members**; clearly label the selection alongside the output.
2. Sort member names before displaying, because Reflection does not guarantee the order of arrays returned by APIs.
3. Flag bridge/synthetic methods when encountering generic overrides; do not treat every element of `getDeclaredMethods()` as a method typed in source code.
4. Read only annotations active at runtime, distinguishing class annotations from annotations on type arguments or methods.
5. If adding an execution mode, allow only approved public methods; separate validation, object creation, and method invocation from the read-only inspector flow.

When testing, intentionally trigger three errors: a wrong method name, a wrong parameter signature, and a target method throwing an exception itself. Demonstrate how a **lookup-step error** differs from a **wrapped error during method execution**. For private members in another module, prefer explicit access design instead of assuming Reflection can open them.

### Capstone Completion Criteria

- The report does not mutate object state when in discovery-only mode.
- You can accurately predict which members appear in declared mode vs. public/inherited mode.
- Output remains deterministic after sorting, even when the order returned by Reflection varies.
- Limitations of annotation and generic metadata are clearly identified.
- Errors are described by **class + member + signature + failing step**, including the root cause during execution.
- You can explain the decision to keep Reflection at the tooling boundary while using regular calls in business logic.

## 7. How to Self-Assess and Continue Learning

Do not stop at checking "a few console lines printed right." You have mastered a stage when you can **predict output before running**, explain output after running, and fix an intentionally broken variant while preserving access boundaries.

Signs you should review:

- You think `Class<?>` is a data instance of the described class.
- You think `getDeclaredMethod` both finds and invokes a method, or always bypasses access checks.
- You expect `getClass()` to recover every generic type argument that appeared in the source variable.
- You do not distinguish `NoSuchMethodException` from the cause inside `InvocationTargetException.getCause()`.
- You use Reflection for every call merely to pick a different implementation when the program already has a shared interface.

The recommended reading order for this chapter is: **What Reflection is and what problem it solves → compile-time vs. runtime type info → metadata vs. execution/state → roles of Class and java.lang.reflect → inheritance/generics/annotations → Reflection vs. direct calls → end-to-end example**. You can return to this lesson to mark your learning milestones.

Once you complete `ClassInspector` and can explain the limits above, you have the foundation to study how Reflection is applied in real test runners, serializers, dependency injection containers, or plugin loaders. Frameworks may employ additional techniques; verify how they handle metadata and access permissions rather than assuming every framework works exactly like introductory examples.