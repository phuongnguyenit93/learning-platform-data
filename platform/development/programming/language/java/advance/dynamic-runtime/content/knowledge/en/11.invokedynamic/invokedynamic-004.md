# 11.4 Distinguishing arguments passed to bootstrap from arguments of the actual call

In Java, the `invokedynamic` bytecode instruction separates **call-site linkage** (*linkage*) from **call-site execution** (*invocation*). Therefore, there are two very different groups of arguments:

1. **Arguments for the bootstrap method (BSM):** used to **decide which behavior this call site will link to**. The JVM provides the `MethodHandles.Lookup` context, the call-site name `String`, and the call-site type `MethodType`; in addition, there may be **bootstrap arguments recorded in the class file** (constants, `MethodHandle`, `MethodType`, ...). The bootstrap runs during linkage to provide a `CallSite`.
2. **Arguments of the actual call:** are **the values on the operand stack** at the time the `invokedynamic` instruction is executed (after linkage); they are passed to the `CallSite`'s target according to the signature declared by the call site. This data changes between calls depending on program flow.

Principle: **bootstrap arguments configure how the call works; invocation arguments provide the data for each individual call.** Both types can be `String` or `int`, but they travel through **two different paths, at two different stages**.

This lesson uses the JVM class file, `BootstrapMethods`, `MethodType`, `CallSite`, `StringConcatFactory`, and `LambdaMetafactory` to point out the difference, accompanied by three Java 17+ examples (one transparent simulation via the API and two cases where `javac` actually generates `invokedynamic`).

## 1. Overall view through a two-stage diagram

~~~text
                         CLASS FILE
 ┌────────────────────────────────────────────────────┐
 │ CONSTANT_InvokeDynamic_info                        │
 │   - bootstrap_method_attr_index                    │
 │   - name_and_type_index                            │
 │                                                    │
 │ BootstrapMethods attribute                         │
 │   - bootstrap_method_ref                           │
 │   - bootstrap_arguments[] (pre-recorded constants) │
 └────────────────────────────────────────────────────┘
                        │
          Linking the invokedynamic call site
                        │
                        ▼
       JVM calls bootstrap with information:
       (Lookup, invokedName, invokedType, staticArg1, ...)
                        │
                        ▼
             BSM creates/returns CallSite
                        │
                        ▼
               CallSite.target
                        ▲
                        │
       Execute invokedynamic according to descriptor
       (runtimeArg1, runtimeArg2, ...) -> result
                        ▲
                        │
            Values from operand stack
~~~

It is **not** the case that every time `invokedynamic` runs, it must call the bootstrap and then call the target. Linkage usually occurs when the call site is needed for the first time; after succeeding, subsequent executions use the target of the linked call site. In an environment where multiple threads simultaneously trigger linkage, the JVM may perform multiple competing bootstrap operations and then choose one result; therefore, **do not design based on the assumption that a BSM is guaranteed to run only once across all execution schedules**.

The name `invokedName` and `invokedType` are information the JVM takes from the call site itself; they are different from the *additional bootstrap arguments* located in `BootstrapMethods`. Each call site in bytecode has its own linkage and signature, even when multiple call sites share the same bootstrap method.

## 2. Precisely identifying the three groups of data

Instead of calling everything "invokedynamic parameters", let us name them:

| Group | Origin | When is it used? | Example | Role |
| --- | --- | --- | --- | --- |
| **Standard information passed by the JVM to the BSM** | Call-site name, descriptor, and JVM context | During linkage | `Lookup lookup`, `String name`, `MethodType type` | Tells the BSM which call site is being linked |
| **Additional bootstrap static arguments** | `BootstrapMethods.bootstrap_arguments[]` in the class file | During linkage | recipe `"user=\u0001"`, a `MethodHandle`, a `MethodType`, number `42` | Configures how to select/build the target |
| **Runtime invocation arguments** | Operand stack of the executing thread | Every time the `invokedynamic` instruction executes | `user="Lan"`, `score=81` | Data that the target receives and processes |

Cases that should not be confused:

- **A bootstrap static argument is not synonymous with a Java `static` variable.** The word "static" here refers to arguments **fixed in the bootstrap description of the class file**, not the `static` modifier on a field or method.
- **Not all arguments passed into the bootstrap are recorded in `bootstrap_arguments[]`.** The first three parameters `Lookup`, `String name`, and `MethodType` are provided by the JVM; they are **standard information**, not three elements added by the programmer to the class file's array.
- **A runtime argument can always hold the same value.** It is still a runtime argument because it is pushed onto the operand stack when the call runs, not because its value is guaranteed to change. Conversely, a static argument can affect behavior that produces a target receiving changing data.
- **The return type of `invokedynamic` is not a runtime argument**. It resides in the call-site descriptor, is represented in the `MethodType` that the bootstrap receives, and determines the number/type of return values on the stack.
- **There is no implicit receiver for `invokedynamic` in the style of `invokevirtual`.** If a receiver is needed, it must appear as an explicit parameter in the descriptor and be pushed onto the stack accordingly.

## 3. Where does the JVM find the BSM and static arguments?

The class file contains a `CONSTANT_InvokeDynamic_info` in the constant pool, which logically binds:

- **`bootstrap_method_attr_index`**: points to an entry in the class's `BootstrapMethods` table.
- **`name_and_type_index`**: indicates the call-site name and the **method descriptor** of `invokedynamic`, for example `(Ljava/lang/String;I)Ljava/lang/String;` meaning it takes `String, int` and returns `String`.

The `BootstrapMethods` table contains `bootstrap_method_ref` (a `MethodHandle` reference to the BSM) and the `bootstrap_arguments[]` list. These elements are constants that can be loaded according to class-file rules: such as `String`, primitive numbers represented by the constant pool, `Class`, `MethodType`, `MethodHandle`, and in modern class files dynamic constants can be used when valid.

This brings an important difference:

~~~text
CONSTANT_InvokeDynamic
  name = makeConcatWithConstants
  descriptor = (Ljava/lang/String;I)Ljava/lang/String;
  bootstrap method = StringConcatFactory.makeConcatWithConstants
  static arguments = recipe "user=\u0001; score=\u0001"

On run 1:
  operand stack provides ("Lan", 81)
  target produces "user=Lan; score=81"

On run 2:
  operand stack provides ("Minh", 40)
  target produces "user=Minh; score=40"
~~~

`recipe` is chosen at the linkage step, whereas `"Lan"`, `81`, `"Minh"`, `40` are the actual arguments at the invocation step. The recipe is not automatically put into the `(String,int)String` input list of the call, unless the BSM intentionally builds a target that has a mechanism to use that recipe internally.

**Distinguishing the two descriptors:** the descriptor of the **bootstrap method** (taking `Lookup`, `String`, `MethodType`, additional configurations...) is not the descriptor of the **invokedynamic call site** (only runtime arguments and return type). The signature of the original method chosen by the BSM can also differ from both, because the BSM is allowed to pre-bind parameters or create adapters.

## 4. What is the bootstrap method called with?

A BSM typically has an equivalent Java shape:

~~~java
public static CallSite bootstrap(
        MethodHandles.Lookup lookup,
        String invokedName,
        MethodType invokedType,
        String recipe,
        int mode) throws Throwable {
    // Based on linkage information and configuration, create a CallSite.
    // Not complete implementation code.
    throw new UnsupportedOperationException();
}
~~~

This is a **signature illustration**, not an executable BSM: the method intentionally throws an exception and lacks an enclosing class context. A BSM can use appropriate types or varargs for additional bootstrap arguments according to the JVM contract; the specific signature depends on the BSM kind. With `invokedynamic`, a valid linkage result is a `CallSite` whose target has a signature matching the call site.

The parameters:

**`lookup` — lookup and access-privilege context.** The JVM provides a lookup for the class containing the instruction being linked. The BSM uses it to `findStatic`/`findVirtual`/... or create handles matching access privileges. Do not confuse this with a runtime receiver.

**`invokedName` — the name recorded in `NameAndType`.** For example, the requested bootstrap name is `makeConcatWithConstants` in a compiler-generated call site. This name helps the BSM distinguish the call site when needed, but it **is not itself a business argument** of the target.

**`invokedType` — the execution signature of `invokedynamic`.** For example `(String,int)String`. It indicates the values that will be popped from the stack when calling and the result type that will be pushed back. The BSM must return a `CallSite` whose `type()` matches this signature exactly.

**`recipe`, `mode` — additional static bootstrap arguments.** They are recorded in `BootstrapMethods` (or in the simulation example, passed when actively calling the Java function). They help the BSM decide the target, and do not automatically become parameters of the target. The BSM can use `insertArguments`, `bindTo`, `asType`, `guardWithTest`, and combinators to fold configuration into the behavior to be called.

### What happens if the BSM is wrong?

If the bootstrap cannot perform linkage, throws an error, returns an invalid result, or returns a `CallSite` with a mismatched signature, the JVM may report a `BootstrapMethodError` at the linkage step. This is **different** from `WrongMethodTypeException` when code later misuses `invokeExact` on a handle. One should not catch all linkage errors and pretend they are user input errors.

A BSM should create a target whose type is carefully checked before returning, especially when using multiple combinators that alter the parameter list.

## 5. What are the runtime arguments of invokedynamic?

An `invokedynamic` bytecode instruction is associated with a method descriptor, for example:

~~~text
(String,int)String
~~~

To execute a call according to this descriptor, the JVM pops from the operand stack a `String` reference and an `int` integer in exact order, then executes the call site's current target with those values. If the method descriptor has a return type other than `void`, the result is placed back onto the stack.

A simplified view from bytecode:

~~~text
aload_0          // load String user (runtime)
iload_1          // load int score (runtime)
invokedynamic ... (Ljava/lang/String;I)Ljava/lang/String;
areturn          // return processed String
~~~

The snippet above is a **bytecode model**, not a complete literal `javap` file with specific constant-pool numbers. The values of `user` and `score` are loaded by code running before the opcode, not read from `bootstrap_arguments[]`.

Key points:

- **The types of invocation arguments** come from the descriptor, not from the accidental types of variables in the BSM.
- **Runtime values** can come from local variables, fields, results of other methods, or constants pushed onto the stack at runtime. Even if the initial value is the literal `"Lan"` in source, it is still a runtime argument of the opcode itself when placed on the stack to make the call.
- `invokedynamic` does not require having runtime arguments. With the descriptor `()String`, the call consumes no arguments; the BSM can still receive multiple configuration bootstrap arguments.
- Do not assume that any BSM with side effects only runs when each invocation runs; these two stages are separated.

## 6. MethodType is the bridge, not a list of values

Two quantities to distinguish:

~~~java
MethodType siteType =
        MethodType.methodType(
                String.class, String.class, int.class);
// siteType.toString() = "(String,int)String"
~~~

`siteType` only describes **one `String` and one `int` passed at call time**. It does not contain the value `"Lan"` or `81`. The BSM receives `siteType` at linkage time to know what type the target must have.

Similarly:

~~~java
MethodHandle target = /* valid handle */;
MethodType actual = target.type();
~~~

`actual` describes the input/output of the handle, not the data of a single execution turn. If the BSM creates a raw handle `(String,int,String,int)String` while the call site needs `(String,int)String`, it must build an additional adapter, for example binding `prefix` and `minScore` to the first two parameters. Then:

~~~text
raw target:
  (String prefix, int minScore, String user, int score)String

after insertArguments(raw, 0, prefix, minScore):
  (String user, int score)String

call site needs:
  (String user, int score)String   ✓
~~~

This is **one way of using static configuration**: the configuration values do not appear in the final call signature, but have been stored inside the handle. Another BSM might use a static argument to **select** among multiple targets instead of binding; the JVM does not force every BSM to use `insertArguments`.

## 7. Complete Java 17+ Example 1: simulating linkage with the API

The program below **does not itself generate an `invokedynamic` opcode for the simulated call**. It calls the `bootstrap(...)` function directly in Java so you can clearly observe the difference, then calls `CallSite.dynamicInvoker()` twice. The goal is to see at which stage the four configuration and runtime values are used; real examples where `javac` generates `invokedynamic` will appear in the next sections.

Create the file **BootstrapArgumentsDemo.java**:

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class BootstrapArgumentsDemo {
    private static int bootstrapCalls;

    public static String render(
            String prefix, int minimum, String user, int score) {
        String result = score >= minimum ? " PASS" : " RETRY";
        return prefix + user + "=" + score + result;
    }

    public static CallSite bootstrap(
            MethodHandles.Lookup lookup,
            String invokedName,
            MethodType invokedType,
            String prefix,
            int minimum) throws ReflectiveOperationException {

        bootstrapCalls++;
        System.out.println("bootstrap name: " + invokedName);
        System.out.println("bootstrap type: " + invokedType);
        System.out.println("static arguments: " + prefix + " | " + minimum);

        MethodType rawType = MethodType.methodType(
                String.class,
                String.class, int.class, String.class, int.class);
        MethodHandle raw = lookup.findStatic(
                BootstrapArgumentsDemo.class, "render", rawType);

        // The two configuration values are bound to the target.
        // raw: (String,int,String,int)String
        // bound: (String,int)String
        MethodHandle bound = MethodHandles.insertArguments(
                raw, 0, prefix, minimum);

        if (!bound.type().equals(invokedType)) {
            throw new IllegalArgumentException(
                    "wrong call-site type: " + bound.type());
        }

        return new ConstantCallSite(bound);
    }

    public static void main(String[] args) throws Throwable {
        MethodType runtimeType = MethodType.methodType(
                String.class, String.class, int.class);

        // SIMULATING JVM LINKAGE: call bootstrap directly.
        CallSite site = bootstrap(
                MethodHandles.lookup(),
                "renderScore",
                runtimeType,
                "report:",
                60);

        MethodHandle invoker = site.dynamicInvoker();
        System.out.println("invoker type: " + invoker.type());

        // Runtime arguments: user and score, not prefix/minimum.
        String first = (String) invoker.invokeExact("Lan", 75);
        String second = (String) invoker.invokeExact("Minh", 40);

        System.out.println("call 1: " + first);
        System.out.println("call 2: " + second);
        System.out.println("bootstrap calls: " + bootstrapCalls);
    }
}
~~~

Compile/run:

~~~bash
javac BootstrapArgumentsDemo.java
java BootstrapArgumentsDemo
~~~

Expected stdout:

~~~text
bootstrap name: renderScore
bootstrap type: (String,int)String
static arguments: report: | 60
invoker type: (String,int)String
call 1: report:Lan=75 PASS
call 2: report:Minh=40 RETRY
bootstrap calls: 1
~~~

### How to read the output

**Step 1 — linkage configuration:** the simulation program provides `invokedName = "renderScore"`, `invokedType = (String,int)String`, and two values `"report:"`, `60`. This is a **bootstrap call from source code**, intended to simulate the data that the JVM provides during linkage of a real site; the run count in the example is determined by exactly **one direct Java call** in `main`.

**Step 2 — raw method handle:** the `render` method declares four parameters `(String,int,String,int)String`. The first two parameters are configuration, and the last two parameters are business data.

**Step 3 — bind static configuration:** `insertArguments(raw, 0, prefix, minimum)` binds the first two values. The new handle `bound` has type `(String,int)String`, matching `runtimeType`. Static arguments do not appear in the runtime parameter list of the site.

**Step 4 — create CallSite:** `new ConstantCallSite(bound)` keeps the target stable. `site.dynamicInvoker()` is a handle with this exact `MethodType`.

**Step 5 — invocation:** two turns pass `("Lan",75)` and `("Minh",40)`. The target reuses `prefix="report:"` and `minimum=60` bound during the handle-building step; only `user` and `score` are per-call data.

**Limitation of the example:** `bootstrap calls: 1` **does not prove** that a real JVM invokedynamic BSM is only executed once in all situations. Because here we actively called the bootstrap method once; JVM `invokedynamic` linkage has its own rules and may have races during concurrent linkage. In addition, string concatenations inside Java 17 may be compiled by the compiler into **other** `invokedynamic` instructions, not the call site created by the simulation snippet.

## 8. Complete Java 17+ Example 2: javac generates invokedynamic for string concatenation

This time we write normal Java and then **observe the real bytecode**. Java 17 by default usually compiles string concatenation using `invokedynamic` combined with `java.lang.invoke.StringConcatFactory`.

Create the file **StringConcatIndyDemo.java**:

~~~java
public class StringConcatIndyDemo {
    public static String describe(String user, int score) {
        return "user=" + user + "; score=" + score;
    }

    public static void main(String[] args) {
        System.out.println(describe("Lan", 81));
        System.out.println(describe("Minh", 40));
    }
}
~~~

Run:

~~~bash
javac StringConcatIndyDemo.java
java StringConcatIndyDemo
~~~

Expected stdout:

~~~text
user=Lan; score=81
user=Minh; score=40
~~~

Inspect detailed bytecode:

~~~bash
javap -c -v StringConcatIndyDemo
~~~

In the `javap` output, find the `describe` method, the `invokedynamic` line, and the `BootstrapMethods` section. An illustrative excerpt **by shape**, omitting constant-pool indexes because `#...` numbers are assigned by the compiler and can change:

~~~text
public static java.lang.String describe(java.lang.String, int);
  ...
    aload_0
    iload_1
    invokedynamic ... // makeConcatWithConstants:
                      // (Ljava/lang/String;I)Ljava/lang/String;
    areturn

BootstrapMethods:
  ...
  REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants
  Method arguments:
    user=\u0001; score=\u0001
~~~

This is **not an exact copy of the full stdout of `javap`**; it illustrates the fields to locate. `#...` indexes, bytecode offsets, how control characters are printed, and some optimization details may vary by `javac`/JDK. The `java` command above has the complete, deterministic stdout for comparison.

Key points to read from the excerpt:

- `aload_0` and `iload_1` take `user` and `score` of the `describe` method call turn, loading them onto the operand stack.
- `invokedynamic` has descriptor `(Ljava/lang/String;I)Ljava/lang/String;`, meaning the **runtime invocation** takes exactly one `String` and one `int`, returning `String`.
- The BSM is `StringConcatFactory.makeConcatWithConstants`. The text `makeConcatWithConstants` is not "user data"; it is the name related to the bootstrap mechanism that enables string concatenation.
- The recipe string containing `\u0001` is a marker representing **one dynamic argument**. The recipe `"user=\u0001; score=\u0001"` describes the insertion positions for the two runtime arguments; the recipe is a **static bootstrap argument**.
- For the program above, the recipe/configuration does not need to change for `"Lan",81` and `"Minh",40`. Runtime data changes, so the two returned strings differ.

### Recipe markers and static constants

`StringConcatFactory.makeConcatWithConstants` has a convention of using `\u0001` as a placeholder for a **runtime argument**; `\u0002` can indicate another **bootstrap constant** provided via `constants` depending on the recipe. That is a convention **specific to StringConcatFactory**, **not** a rule that every BSM must use special characters.

Conceptual example:

~~~text
recipe      = "user=\u0001, fixed=\u0002"
runtime arg = "Lan"
static arg  = "MODE-A"

result      = "user=Lan, fixed=MODE-A"
~~~

This is only a model illustrating how markers are processed, not a claim that `javac` will generate that exact recipe from the program above. Distinguish:

- `\u0001` marks **the slot to fill a runtime argument**.
- `\u0002` marks **the slot to fill a bootstrap constant** in the recipe.
- Both markers are **characters inside the static recipe**, but they point to two different value sources during the creation/operation of string concatenation.

If using `javap`, look at both **Method arguments** in `BootstrapMethods` and the **descriptor** as well as the instructions loading values before `invokedynamic`. Reading only one part makes it easy to mistake the recipe for a runtime parameter.

## 9. Bootstrap signature of StringConcatFactory and call-site signature

`StringConcatFactory` provides a specialized BSM (simplified API syntax):

~~~java
CallSite makeConcatWithConstants(
        MethodHandles.Lookup lookup,
        String name,
        MethodType concatType,
        String recipe,
        Object... constants)
~~~

In this case:

**Bootstrap inputs:**

- `lookup`: provided by the JVM for the class containing the call site.
- `name`: call-site name, provided by the JVM.
- `concatType`: `(String,int)String`, from the opcode's descriptor.
- `recipe`: string concatenation configuration taken from `BootstrapMethods`.
- `constants` (if any): other fixed configuration taken from bootstrap arguments.

**Runtime invocation inputs:**

- `user:String` and `score:int` are loaded onto the operand stack before `invokedynamic`.
- The target result is a `String`.

Although there can be both `String recipe` and `String user`, **do not infer that they go into the same slot**. `recipe` belongs to the BSM, `user` belongs to the runtime descriptor. The BSM has the right to create a target that uses `recipe` to process `user`/`score` later; the JVM does not automatically merge the two lists.

On the other hand, `concatType` is **type metadata**, not the concatenation result and not a business argument named `concatType` received by the target. `MethodType` serves as the bridge from linkage to type-checking of the target.

## 10. Complete Java 17+ Example 3: lambda capture is a runtime argument of invokedynamic

Lambdas are a case that very easily causes confusion. When Java compiles a lambda with **captured variables**, `invokedynamic` is used at **the point where the lambda object is created**. The captured value (such as `prefix`) is passed as a **runtime argument of the invokedynamic opcode itself**, not a static bootstrap argument.

Later, when you call the functional interface method on the lambda object, that call usually goes through `invokeinterface` — **not the same invokedynamic opcode that created the lambda**.

Create the file **LambdaCaptureDemo.java**:

~~~java
public class LambdaCaptureDemo {
    @FunctionalInterface
    interface Formatter {
        String apply(String value);
    }

    static Formatter make(String prefix) {
        return value -> prefix + value;
    }

    public static void main(String[] args) {
        Formatter hello = make("Hello ");
        Formatter welcome = make("Welcome ");

        System.out.println(hello.apply("Lan"));
        System.out.println(welcome.apply("Minh"));
    }
}
~~~

Compile and run:

~~~bash
javac LambdaCaptureDemo.java
java LambdaCaptureDemo
~~~

Expected stdout:

~~~text
Hello Lan
Welcome Minh
~~~

Inspect the class file:

~~~bash
javap -c -v LambdaCaptureDemo
~~~

Find the `make` method and the `BootstrapMethods` section. An abbreviated bytecode diagram:

~~~text
make(String prefix):
    aload_0
    invokedynamic ... // apply:(Ljava/lang/String;)LLambdaCaptureDemo$Formatter;
    areturn

main(...):
    ...
    invokeinterface ... // LambdaCaptureDemo$Formatter.apply:(String)String
    ...

BootstrapMethods:
    REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
    arguments: samMethodType, implementationMethodHandle,
               instantiatedMethodType
~~~

The illustrative code above does not attempt to reproduce exact constant-pool offsets/indexes or descriptor syntax of every `javap` line. Pay attention to the essence:

1. **The BSM is `LambdaMetafactory.metafactory`.** The static bootstrap arguments describe the abstract method type of the functional interface, the `MethodHandle` for the lambda implementation, and the instantiated method type; they are not the values `"Hello "` or `"Welcome "` themselves.
2. **`prefix` is a captured runtime argument** of the `invokedynamic` opcode at `make`. Each call `make("Hello ")` or `make("Welcome ")` supplies a different `String` at runtime to create a lambda object with the corresponding captured state.
3. **`value` in `hello.apply("Lan")` is an argument of the subsequent `apply` call**, not an argument of the `invokedynamic` that created the `hello` object. These are **two different call moments**: the factory invocation to create the lambda, then the invocation of the functional interface method to process data.
4. The lambda body contains the string concatenation `prefix + value`; in Java 17, the compiler may generate **another invokedynamic** for the string concatenation operation inside the synthetic lambda method. When viewing `javap`, one must match each `invokedynamic` with its corresponding bootstrap entry, without merging `LambdaMetafactory` and `StringConcatFactory` into one.
5. Even though the captured value is retained for a long time inside the lambda object after creation, it **does not turn into a static bootstrap argument**. "Being retained" and "being recorded fixedly in the class file" are two different concepts.

Comparison table:

| Value | Which call does it belong to? | Path |
| --- | --- | --- |
| Method type of SAM `Formatter.apply` | Bootstrap linkage of lambda factory | Static bootstrap argument |
| MethodHandle pointing to lambda implementation | Bootstrap linkage of lambda factory | Static bootstrap argument |
| `prefix="Hello "` | `invokedynamic` in `make` | Runtime argument to create lambda |
| `prefix="Welcome "` | Another `invokedynamic` turn in `make` | Runtime argument to create lambda |
| `"Lan"` | `hello.apply("Lan")` | Argument of `invokeinterface` after lambda is created |
| `"Minh"` | `welcome.apply("Minh")` | Argument of `invokeinterface` after lambda is created |

This is an example showing that **the same term "argument" can refer to multiple different calls**, so one must identify the opcode/call site before classifying.

## 11. Formula for inspecting the two argument lists from bytecode

When reading an `invokedynamic` instruction in `javap -v -c`, proceed in order:

**A. Find the invokedynamic line in the method of interest.** Identify what it does: string concatenation, lambda creation, or linking a dynamic language. Do not assume all opcodes share the same BSM.

**B. Read the call-site descriptor.** With `(Ljava/lang/String;I)Ljava/lang/String;`, the runtime arguments are `String` and `int`, and the return is `String`. This is the number/type of data loaded/consumed on the operand stack on each run.

**C. Observe the instructions immediately before the opcode.** For example `aload_0`, `iload_1`. They can tell which local variables the values come from. On complex paths, values may be computed from many preceding opcodes; do not just read the two nearest lines and ignore stack flow.

**D. Find the bootstrap index of the `CONSTANT_InvokeDynamic_info` entry.** Follow it to the `BootstrapMethods` section to identify `bootstrap_method_ref`.

**E. Read the `Method arguments` list of that entry.** These are the additional static bootstrap arguments. For concat, there is usually a recipe; for lambda, there are usually method types and an implementation handle.

**F. Add the three JVM-provided parameters to the bootstrap diagram.** Do not forget `Lookup`, `name`, `MethodType`; they usually do not appear as three "Method arguments" elements in the `BootstrapMethods` table, yet the JVM still provides them to the BSM.

**G. Check which CallSite type the BSM returns.** If implementing a BSM yourself, check `callSite.type().equals(invokedType)`. For compiler-generated class files, look at the actual descriptor and the corresponding factory API.

**H. Compare changes across execution turns.** Try two different runtime values at the same call site; if the output differs, do not infer that the BSM was re-run. Many targets use fixed linkage configuration to process dynamic data.

### Table template for taking notes during investigation

| Field to record | Concat example |
| --- | --- |
| Class/method containing opcode | `StringConcatIndyDemo.describe` |
| Opcode | `invokedynamic` |
| Name/descriptor | `makeConcatWithConstants : (String,int)String` |
| BSM | `StringConcatFactory.makeConcatWithConstants` |
| Bootstrap static args | Recipe `"user=\u0001; score=\u0001"` |
| JVM-provided BSM args | `Lookup`, name, `MethodType` |
| Runtime arguments | `user:String`, `score:int` |
| Who provides runtime args? | Bytecode loads two local values onto the operand stack |
| What does target receive? | Two runtime values according to descriptor |
| Return value | A `String` from target |

For `LambdaMetafactory` examples, clearly write "runtime args of **lambda factory invokedynamic**" and "args of **SAM invocation**" on two separate lines.

## 12. Do not confuse the bootstrap method with the target handle itself

A bootstrap method can:

- Find a direct method handle using `lookup.findStatic(...)`.
- Bind configuration values using `MethodHandles.insertArguments(...)`.
- Adapt signatures using `asType(...)` when a valid conversion exists.
- Choose a `ConstantCallSite` or set up a `MutableCallSite`.
- Return a `CallSite` for the JVM to link the call site.

**The BSM does not have to be the method called on every runtime turn.** It is a *factory/linker* that creates the call structure. It is `CallSite.target` or the call site's dynamic invoker that represents the behavior executed in subsequent calls.

Conceptual example:

~~~text
Bootstrap:
  bootstrap(Lookup, "calculate", (int)int, "fast")
    └── configures "fast" to select target
         └── returns ConstantCallSite(target: (int)int)

Invocation 1:
  invokedynamic with runtime int=4
    └── target(4) -> result

Invocation 2:
  invokedynamic with runtime int=9
    └── target(9) -> result
~~~

In this diagram, `"fast"` is a **configuration** bootstrap argument; `4` and `9` are runtime arguments. If the target needs to be modified later, with `ConstantCallSite` the target is stable; with `MutableCallSite` or `VolatileCallSite` there can be a mechanism to update the target according to that class's contract, but retargeting **does not require automatically re-running the BSM**.

`CallSite` is designed so that the target's type is compatible with the call site's type. With `MutableCallSite`, when updating via `setTarget`, the new target's type must match the call site; changing behavior must not change the descriptor of the `invokedynamic` instruction itself.

## 13. Common mistakes when writing your own bootstrap or reading bytecode

| Symptom/confusion | Cause | How to fix |
| --- | --- | --- |
| Thinking `bootstrap_arguments[]` contains `user` and `score` | Reading recipe while ignoring operand stack and descriptor | Separate static BSM data from runtime invocation data |
| Thinking the JVM passes recipe to target as first parameter | Confusing BSM signature with call-site signature | Read `invokedType`, check target type after binding/adaptation |
| Using `(Lookup,String,MethodType,...)` as runtime signature | Confusing linker signature with opcode signature | Call-site descriptor only describes runtime inputs and return |
| Not seeing the three JVM-provided parameters in `Method arguments` | First three parameters are not additional static args in the array | Explicitly record `Lookup`, `name`, `type` in the BSM diagram |
| Running the same opcode many times and thinking bootstrap runs each turn | Confusing linkage with invocation | Check call-site model: link when needed, use target afterward |
| Over-relying on "bootstrap always runs exactly 1 time" | Not considering possible linkage races | Do not put "must run exactly once" side effects into BSM when correctness requires it |
| Target type differs from site descriptor | Haven't bound/adapted enough parameters | Compare `target.type()` with `invokedType` before returning `CallSite` |
| BSM errors but only trying to fix runtime argument | Linkage error differs from per-call data error | Distinguish `BootstrapMethodError` from target/runtime exceptions |
| Lambda capture treated as static bootstrap argument | Seeing prefix retained in lambda object | Observe `aload_0` before lambda factory `invokedynamic` |
| `lambda.apply(x)` called the "invoke dynamic" of the factory | Not distinguishing lambda creation step from lambda usage step | Use `javap` to separate `invokedynamic` and `invokeinterface` |
| BSM for String concat confused with BSM for Lambda | Same class has multiple invokedynamic opcodes | Follow each bootstrap index and bootstrap method ref separately |
| Not seeing `invokedynamic` in expected bytecode | Compiler/JDK/optimization or instruction transformed | Use standard JDK 17, inspect `javap -c -v` and specific method |
| Believing static argument "is always a Java static field" | Misleading name | Static argument here is fixed configuration stored in class-file metadata |
| Treating `MethodType` as if it holds input values | Equating types and actual objects | `MethodType` only stores types, values come from stack |
| Thinking invokedynamic has a hidden receiver | Applying `invokevirtual` rules to invokedynamic | All runtime parameters are explicit in the descriptor |
| Forgetting void/no-argument call sites | Assuming there must be runtime arguments | Descriptor can be `()void`, `()String`... even if BSM has configuration |

## 14. Self-check questions with answers

**1. What is the fundamental difference between bootstrap arguments and invocation arguments?**  
Bootstrap arguments serve **linking/configuring** the call site; invocation arguments are **runtime values** that the target processes every time the opcode runs.

**2. A BSM receives `Lookup`, `String name`, `MethodType`. Are these three values in `bootstrap_arguments[]`?**  
No. Those are the three standard parameters provided by the JVM. `bootstrap_arguments[]` contains **additional arguments** recorded in the class file.

**3. Call site `(String,int)String` has static argument `"prefix"`. When calling the target, how many runtime parameters must the caller pass?**  
Two: `String` and `int`. `"prefix"` may have been bound/used by the BSM to select the target, but it does not automatically increase the `parameterCount()` of the call site.

**4. Why does `StringConcatFactory` receive a recipe while `invokedynamic` only passes `user` and `score`?**  
Recipe is configuration for the BSM, describing how to combine runtime values; it is not an input slot in the call-site descriptor.

**5. If code loads a literal `"Lan"` onto the stack right before `invokedynamic`, what kind of argument is `"Lan"`?**  
It is a **runtime invocation argument** of the opcode. "Runtime" describes the data-passing path at execution time, not requiring the value to be dynamically changing.

**6. Does the `MethodType` received at bootstrap contain `"Lan"`?**  
No. It can describe `String.class` at a parameter slot, without storing values.

**7. If a BSM returns a `ConstantCallSite`, does each call turn automatically re-run the BSM?**  
Not under the normal mechanism after linkage: runtime uses the linked target. However, one must not rely on the bootstrap side-effect count being equal to 1 in all concurrent situations.

**8. Lambda `prefix -> ...` has captured variable `prefix`. Why is `prefix` not a static bootstrap arg?**  
The value of `prefix` is loaded when the **lambda factory invokedynamic** runs, i.e., it is a runtime argument of that opcode itself. Static bootstrap args describe the SAM/implementation types and compiler configurations recorded in the class file.

**9. When calling `formatter.apply("Lan")`, is `"Lan"` an argument of the invokedynamic that created the lambda earlier?**  
No. This is an argument of an `apply` call after the lambda object already exists; the bytecode is usually `invokeinterface`.

**10. How do a CallSite type mismatch with the descriptor and invalid runtime data differ?**  
A mismatched call-site type is a **linkage/target-setup** error; invalid runtime data is an error when **the target runs**, for example parsing failure.

**11. With `invokedynamic ()String`, can the bootstrap receive static arguments?**  
Yes. The runtime invocation has no arguments, but the BSM can still be configured with constants.

**12. Why not read only `BootstrapMethods` and ignore the opcode?**  
Because `BootstrapMethods` provides linker information and static configuration; the number/types of runtime arguments are in the **descriptor** of `invokedynamic` and the actual values are loaded by preceding bytecode.

**13. When a BSM uses `insertArguments` to bind two static values, can the final target take fewer parameters than the raw method?**  
Yes. The raw handle might be `(String,int,String,int)String`, and after binding configuration becomes `(String,int)String`, matching the runtime invocation.

**14. Does `MutableCallSite.setTarget` force the JVM to re-run the BSM or change the descriptor?**  
No. It changes the target according to the call-site contract while keeping the same type; the BSM itself is not automatically re-run by the retarget operation.

**15. Are two invokedynamic opcodes in the same class guaranteed to share the same static arguments?**  
No. One must check each constant-pool entry and bootstrap method index. Even the same BSM can be configured with different bootstrap arguments.

## 15. Practical checklist when debugging invokedynamic

- [ ] Identify **exactly one `invokedynamic` opcode** being analyzed.
- [ ] Record the `name` and **descriptor** of the call site; convert the descriptor to `MethodType` to know runtime inputs and return.
- [ ] Look at bytecode before the opcode to determine **the source of operand-stack values**.
- [ ] Follow the bootstrap index to `BootstrapMethods`, identify **bootstrap_method_ref**.
- [ ] Separately record the **bootstrap_arguments[]** list of the corresponding entry.
- [ ] Add `Lookup`, `name`, `MethodType` as the three **JVM-provided** values when describing the BSM call.
- [ ] Distinguish **BSM signature**, **raw target signature**, and **call-site target signature**; they are not required to be identical.
- [ ] Check that `CallSite.type()` and `target.type()` match the final descriptor.
- [ ] If there are captures or adapters, clearly note **which values are bound** and **which values are still passed per turn**.
- [ ] If the class has both lambdas and string concatenation, analyze `LambdaMetafactory` and `StringConcatFactory` entries separately.
- [ ] Distinguish **linkage** errors and **runtime target** errors.
- [ ] Do not infer how many times the BSM ran from how many times the target prints output.

## 16. Conclusion

`invokedynamic` has two stages with different meanings: **linkage** via the bootstrap method, then **execution** via the call site's target. During linkage, the JVM passes `Lookup`, name, and `MethodType`; the class file additionally provides **static bootstrap arguments** to configure the target. During invocation, the JVM passes **runtime arguments taken from the operand stack** according to the call-site descriptor, and the target returns the corresponding result.

Therefore, to answer the question "when is this parameter passed?", one needs to determine whether **the parameter belongs to the BSM signature, belongs to `BootstrapMethods`, or belongs to the descriptor of invokedynamic**. Even when all three have the same `String` type, simply distinguishing the source and the time of use enables reading bytecode accurately, writing valid BSMs, and avoiding confusing lambda capture/concat recipe values with business arguments.
