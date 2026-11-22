# 11.3 Bootstrap method contract with `Lookup`, name, `MethodType`, and static arguments

## 1. From `invokedynamic` to bootstrap method: what needs to be linked?

In Java bytecode, `invokedynamic` is a call instruction with a **dynamic call site**. Unlike `invokestatic` or `invokevirtual`, this instruction itself does not contain a `Methodref` pointing directly to the Java method that will be executed on every call. Instead, the class file contains a **call site description** and a **bootstrap method specifier**. When the JVM resolves (*resolve/link*) the call site, it invokes a **bootstrap method (BSM)** to obtain a `java.lang.invoke.CallSite` object. The `CallSite` carries the `MethodHandle` to the execution target.

Common BSM contract for `invokedynamic`:

~~~java
public static CallSite bootstrap(
    MethodHandles.Lookup caller,
    String name,
    MethodType invokedType,
    /* 0 or more static arguments */
) throws Throwable
~~~

This is an **illustrative signature template**, not a verbatim compilable Java declaration because the comment stands in for the parameter list. The three standard inputs are:

1. `MethodHandles.Lookup caller`: **the access-privilege context of the class containing the `invokedynamic` instruction**.
2. `String name`: **the unqualified name** attached to the call site itself.
3. `MethodType invokedType`: **the exact signature of the `invokedynamic` instruction**, consisting of parameter types and return type.
4. **Additional static arguments, if any**: metadata recorded in `BootstrapMethods` of the class file and taken from the constant pool, for example `String`, `int`, `Class`, `MethodType`, `MethodHandle`, or valid dynamic constants.

The BSM must provide a **non-null** `CallSite` whose `CallSite.type()` **matches** the method descriptor of `invokedynamic` **exactly**. It is allowed to look up methods, select an implementation, bind arguments with `insertArguments`, or adapt a method handle with `asType` *before* creating the `CallSite`. After successful linkage, subsequent executions of the call site use the **CallSite's target**, without going through bootstrap code like a normal call every time.

**Important warning:** "The BSM runs exactly once under all circumstances" is too strong a statement. When multiple threads resolve a symbolic reference simultaneously, the JVMS allows **multiple concurrent BSM executions**, and then the JVM selects one result to install for the site and discards the other results. After successful linkage, executing `invokedynamic` does not re-bootstrap on every invocation. Therefore, a BSM should avoid unsafe side effects under contention.

### Why is it necessary to understand this contract?

- When using lambdas/method references, `javac` typically emits `invokedynamic` and `LambdaMetafactory.metafactory` as the BSM.
- When concatenating strings with the `+` syntax, modern `javac` typically uses `StringConcatFactory.makeConcatWithConstants` with a **recipe** as a static argument.
- Compilers for languages running on the JVM and bytecode generation frameworks can use custom BSMs to select or generate targets.
- When encountering `BootstrapMethodError` at runtime, one needs to know the error occurred in the **linkage phase** rather than assuming it is in the target method's logic.

## 2. Flow diagram of linking a call site

~~~text
Class file
  |
  +-- CONSTANT_InvokeDynamic
  |     name: decorate
  |     descriptor: (Ljava/lang/String;)Ljava/lang/String;
  |     bootstrap specifier index: 0
  |
  +-- BootstrapMethods[0]
        MethodHandle REF_invokeStatic -> DecorateBootstrap.bootstrap
        static arg #1 -> "Hi-"
        static arg #2 -> int 2
                             |
                             v
                    JVM resolves site
                             |
                             v
        bootstrap(callerLookup, "decorate",
                  MethodType(String)->String,
                  "Hi-", 2)
                             |
                             v
             BSM returns CallSite with type
                  (String)String
                             |
                             v
           JVM installs link for site
                             |
                             v
   invokedynamic runs target receiving "Ada"
           -> "Hi-Hi-Ada"
~~~

There are **two distinct points in time**:

- **Linkage time**: the JVM resolves the BSM and static arguments, supplies `Lookup`/name/type, invokes the BSM, and checks the `CallSite`.
- **Invocation time**: each time the `invokedynamic` bytecode is executed, it passes **dynamic arguments from the operand stack** to the target. Values like `"Ada"` or `"Bob"` in the example are not static bootstrap arguments.

The JVM may perform resolution eagerly or when the site first needs to execute, according to the JVM's linkage rules. Do not treat the exact timing of a println inside a BSM as a contract about scheduling across all JVMs.

## 3. Contract of each BSM parameter

| BSM Parameter | Source provided by the JVM | Meaning and common pitfalls |
| --- | --- | --- |
| `Lookup caller` | Context of the class **containing the `invokedynamic` instruction** | Not by default the class **defining the BSM**; not permitted to arbitrarily access any class |
| `String name` | `NameAndType` of `CONSTANT_InvokeDynamic` | Is the **site** name, not necessarily the final method name on the target |
| `MethodType invokedType` | Method descriptor of `CONSTANT_InvokeDynamic` | Describes the **call site** (parameters taken from the operand stack and return pushed to the stack), not necessarily the signature of the method referenced in Java source |
| Static arg 1…N | Constant-pool entries in `BootstrapMethods` | Metadata **fixed at linkage**, in the exact order in the class file, not runtime arguments |
| `CallSite` result | Return value of the BSM | Must be non-null, with the exact target type; the target may be a transformed/adapted method handle |

### 3.1. `MethodHandles.Lookup`: privileges of the *caller*, not "omnipotent" privileges

Suppose the `invokedynamic` bytecode resides in the class `example.GeneratedCaller`, while the BSM is defined in `example.BootstrapLibrary`. `caller.lookupClass()` reflects **`GeneratedCaller`**, not `BootstrapLibrary`.

The Lookup is supplied by the JVM so the BSM can create method handles with access privileges corresponding to the context of the **class containing the site**. This is useful when the BSM needs to look up private methods/members that the compiled code has permission to use. However, every call to `findStatic`, `findVirtual`, `findSpecial`, or `privateLookupIn` still obeys access modes, modules, and the protection rules of `Lookup`.

A BSM should not ignore `caller` and arbitrarily use `MethodHandles.lookup()` in the library class when the target needs to access members of the calling class. `lookup()` in the library reflects the **library's privileges**, which may differ from the caller's privileges. Conversely, `caller` must not be used as a mechanism to bypass Java module encapsulation.

### 3.2. `String name`: name of the *site*, not a mandatory target name

In lambdas, `invokedynamic` may carry the name `apply`, `get`, `run`, etc. corresponding to the functional interface. The target of the `CallSite` is usually a **factory creating a function object**, rather than the `apply` method being called directly at lambda-creation time.

In the custom BSM example in section 6, the site name is `decorate` for readability. The BSM can completely choose a method named `render` or `dispatch`, as long as the target type and semantics fit. There is no general contract forcing `caller.findStatic(..., name, type)` to succeed just because the site carries that `name`.

One should validate `name` if a BSM library only supports a specific set of operations; using name to select an implementation is a BSM decision, not default JVM magic resolution.

### 3.3. `MethodType invokedType`: especially must check the **return type**

For example, the JVM descriptor:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

corresponds to:

~~~java
MethodType.methodType(String.class, String.class)
~~~

and displays via `toString()` as:

~~~text
(String)String
~~~

This is the type of the **call site**: one `String` goes in, one `String` comes out. If the initial target handle has `(String,int,String)String`, the BSM can bind the first two parameters and obtain `(String)String`. If using `target.asType(invokedType)`, the conversion must be valid; the final `CallSite` must still have the exact required type.

**Do not confuse `invokedType` with the signature of the BSM.** The BSM may take `(Lookup,String,MethodType,String,int)CallSite` while the linked site has `(String)String`. The two types are used for **two different calls**: calling the BSM at linkage time and calling the target at invocation time.

### 3.4. Static arguments (*static bootstrap arguments*)

"Static" here means **fixed metadata attached to the site in the class file**, not "a Java `static` variable". They are **not** the runtime arguments inside the parentheses of a source expression/target invocation.

According to JVMS 17, each static argument in `BootstrapMethods` points to a **loadable constant-pool entry**, for example:

- `CONSTANT_String`: a `String` such as `"Hi-"`.
- `CONSTANT_Integer/Float/Long/Double`: numeric constants; when the BSM is invoked via a method handle, the value is represented as the appropriate wrapper, and can then be unboxed to match a primitive parameter.
- `CONSTANT_Class`: a `Class<?>` object.
- `CONSTANT_MethodType`: a resolved `MethodType`.
- `CONSTANT_MethodHandle`: a resolved method handle.
- `CONSTANT_Dynamic`: a dynamic constant whose resolution can produce an additional value; it carries **its own bootstrap contract**, not automatically identical to the BSM of `invokedynamic`.

Static arguments appear **after the three implicit arguments**, in the **exact recorded order**. The JVM does not inspect their values to select a BSM overload by business rules. The bootstrap method handle is invoked with the list `caller, name, type, staticArg1, ...` with semantics **as if by `MethodHandle.invokeWithArguments(...)`**. Therefore, a BSM signature typically declares the three standard types and the corresponding static args; per the specification, the handle's parameter types may differ when `invokeWithArguments` conversions allow, and a varargs collector can gather trailing arguments.

**Do not assert rigidly that a BSM must have the exact Java signature `(Lookup,String,MethodType,...)CallSite`.** That is the **conventional and most usable** interface, but what the JVM actually requires is that the bootstrap method handle *can accept* the arguments it supplies and return a valid result. `CONSTANT_Dynamic` (condy) has some constraints of its own; do not impose condy rules onto invokedynamic.

## 4. Traces in the class file: `InvokeDynamic` and `BootstrapMethods`

An `invokedynamic` instruction uses a constant-pool entry of type `CONSTANT_InvokeDynamic`. This entry attaches:

- **bootstrap method attribute index**: points into the class's `BootstrapMethods` table.
- **name-and-type index**: indicates the **site name and method descriptor**.

Class-level `BootstrapMethods` points to:

- `bootstrap_method_ref`, which is a `CONSTANT_MethodHandle` identifying the BSM to invoke.
- `num_bootstrap_arguments` and the corresponding list of `bootstrap_arguments` (there may be no static args).

This is a **two-table** relationship: `CONSTANT_InvokeDynamic` uses an index into `BootstrapMethods`; the entry in `BootstrapMethods` leads to the BSM method handle and the list of static args. Do not confuse an ordinary `Methodref` with the complete information needed to link a call site.

In a `javap -v` listing, one typically sees a structure similar to:

~~~text
#18 = InvokeDynamic  #0:#17
#17 = NameAndType    #16:#6
#15 = MethodHandle   6:#14   // REF_invokeStatic ...
BootstrapMethods:
  0: #15 REF_invokeStatic ...
    Method arguments:
      #20 ...
      #21 ...
~~~

**The `#18`/`#17` numbers here are only used in the generated class example in section 6.** For another class or when the compiler/JDK changes, constant-pool indices and `javap` presentation may differ. What needs to be recognized is the relationship `InvokeDynamic → bootstrap index → MethodHandle + static arguments`.

## 5. Real example with Java source: `LambdaMetafactory` and static arguments

When writing a lambda or method reference in Java, the JDK compiler typically uses `invokedynamic` to build the function object. This is an example **with a real invokedynamic** without needing to hand-craft bytecode.

Create **`LambdaIndyDemo.java`**:

~~~java
import java.util.Locale;
import java.util.function.UnaryOperator;

public class LambdaIndyDemo {
    static String upper(String value) {
        return value.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        UnaryOperator<String> op = LambdaIndyDemo::upper;
        System.out.println(op.apply("java"));
    }
}
~~~

Compile/run/inspect:

~~~sh
javac --release 17 LambdaIndyDemo.java
java LambdaIndyDemo
javap -v -p LambdaIndyDemo
~~~

**Stdout of `java LambdaIndyDemo`:**

~~~text
JAVA
~~~

In the `javap` output, look for the components (ignoring `#...` numbers since they may differ):

~~~text
InvokeDynamic ... apply:()Ljava/util/function/UnaryOperator;
BootstrapMethods:
  ... REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory
    Method arguments:
      (Ljava/lang/Object;)Ljava/lang/Object;
      REF_invokeStatic LambdaIndyDemo.upper:(Ljava/lang/String;)Ljava/lang/String;
      (Ljava/lang/String;)Ljava/lang/String;
~~~

Analyzing the three implicit inputs:

- **`caller`**: Lookup for the class containing the instruction — `LambdaIndyDemo`.
- **`name`**: `apply`, the method name of the functional interface in this context.
- **`invokedType`**: `()UnaryOperator`. This is **the type of the factory call site creating the lambda object**, not `(String)String`.

The three **static arguments** of the `LambdaMetafactory.metafactory` BSM in the example:

1. `samMethodType`: the JVM type of the abstract method in the functional interface, typically erased as `(Object)Object`.
2. `implMethod`: `MethodHandle` pointing to the implementation `LambdaIndyDemo.upper(String)String`.
3. `instantiatedMethodType`: the method type at the type-specialization level `(String)String`.

**The distinction to grasp:** when the program later calls `op.apply("java")`, that is an interface call on the newly created object; it is not a new bootstrap of the lambda-creating instruction. The `CallSite` from metafactory acts as a **factory**, while the lambda object executes the behavior delegated via the implementation method handle.

Do not try to guess the shape of the lambda's implementation class (hidden or not, reused or not) based on the output of a single JVM. The contract here is the linkage and behavior of the functional interface, not the identity/representation of the created object.

## 6. Custom bootstrap example with a **real invokedynamic** and two static arguments

Ordinary Java source **has no direct syntax** to write an arbitrary `invokedynamic` instruction with a chosen BSM. To illustrate **all four groups of information passed by the JVM**, this example uses the **standard Java 17 API `java.io.DataOutputStream`** to create a small class file carrying an `invokedynamic` instruction. It requires no ASM library, JDK-internal APIs, or external plugins.

The example set has three standalone source files in the same directory:

~~~text
DecorateBootstrap.java   - bootstrap and target method
IndyClassWriter.java     - writes IndyGenerated.class in JVM format
IndyRunner.java          - loads the generated class and invokes it 2 times
~~~

### 6.1. Bootstrap method receiving full `Lookup`, `name`, `MethodType`, and static args

Save **`DecorateBootstrap.java`**:

~~~java
import java.lang.invoke.*;

public class DecorateBootstrap {
    public static int linkCount;

    public static CallSite bootstrap(
            MethodHandles.Lookup caller,
            String name,
            MethodType type,
            String prefix,
            int repeat) throws Throwable {
        linkCount++;
        System.out.println("link=" + caller.lookupClass().getSimpleName()
                + "|" + name + "|" + type + "|" + prefix + "|" + repeat);

        MethodHandle impl = caller.findStatic(
                DecorateBootstrap.class, "decorate",
                MethodType.methodType(String.class,
                        String.class, int.class, String.class));

        MethodHandle bound = MethodHandles.insertArguments(
                impl, 0, prefix, repeat).asType(type);
        return new ConstantCallSite(bound);
    }

    public static String decorate(
            String prefix, int repeat, String input) {
        return prefix.repeat(repeat) + input;
    }
}
~~~

`decorate` is the target method `(String,int,String)String`. The BSM receives `prefix` and `repeat` at linkage time, then:

1. `caller.findStatic(...)` looks up the target using the privileges of the class containing the site. The target in the example is `public static` to make access clear.
2. `insertArguments(impl,0,prefix,repeat)` fixes the first two parameters. The remaining handle has type `(String)String`.
3. `asType(type)` ensures adaptation to the exact type required by the site (already matching in the example).
4. `new ConstantCallSite(bound)` returns a call site with an immutable target.

`linkCount` is an observation variable **intended exclusively for a single-threaded demo**. Do not use incrementing `linkCount++` as a safe metric for a BSM resolved concurrently; the JVMS allows concurrent bootstrap calls.

### 6.2. Writing the class file carrying `CONSTANT_InvokeDynamic` and `BootstrapMethods`

Save **`IndyClassWriter.java`**:

~~~java
import java.io.*;
import java.nio.file.*;

public class IndyClassWriter {
    private static void utf(DataOutputStream out, String value)
            throws IOException {
        out.writeByte(1);
        out.writeUTF(value);
    }

    private static void clazz(DataOutputStream out, int name)
            throws IOException {
        out.writeByte(7);
        out.writeShort(name);
    }

    private static void nameType(
            DataOutputStream out, int name, int descriptor)
            throws IOException {
        out.writeByte(12);
        out.writeShort(name);
        out.writeShort(descriptor);
    }

    private static void methodRef(
            DataOutputStream out, int clazz, int nt)
            throws IOException {
        out.writeByte(10);
        out.writeShort(clazz);
        out.writeShort(nt);
    }

    private static void methodHandle(
            DataOutputStream out, int kind, int ref)
            throws IOException {
        out.writeByte(15);
        out.writeByte(kind);
        out.writeShort(ref);
    }

    private static void indy(
            DataOutputStream out, int bootstrap, int nt)
            throws IOException {
        out.writeByte(18);
        out.writeShort(bootstrap);
        out.writeShort(nt);
    }

    private static void str(DataOutputStream out, int utf8)
            throws IOException {
        out.writeByte(8);
        out.writeShort(utf8);
    }

    private static void integer(DataOutputStream out, int number)
            throws IOException {
        out.writeByte(3);
        out.writeInt(number);
    }

    public static void main(String[] args) throws Exception {
        Path target = Path.of(args.length == 0 ? "." : args[0],
                "IndyGenerated.class");

        try (DataOutputStream out = new DataOutputStream(
                Files.newOutputStream(target))) {
            out.writeInt(0xCAFEBABE);
            out.writeShort(0);
            out.writeShort(61); // class-file version 61 = Java 17
            out.writeShort(22); // CP count: 21 entries + slot zero

            utf(out, "IndyGenerated");                 // #1
            clazz(out, 1);                             // #2
            utf(out, "java/lang/Object");              // #3
            clazz(out, 3);                             // #4
            utf(out, "run");                           // #5
            utf(out, "(Ljava/lang/String;)Ljava/lang/String;"); // #6
            utf(out, "Code");                          // #7
            utf(out, "BootstrapMethods");              // #8
            utf(out, "DecorateBootstrap");             // #9
            clazz(out, 9);                             // #10
            utf(out, "bootstrap");                     // #11
            utf(out, "(Ljava/lang/invoke/MethodHandles$Lookup;"
                    + "Ljava/lang/String;Ljava/lang/invoke/MethodType;"
                    + "Ljava/lang/String;I)Ljava/lang/invoke/CallSite;"); // #12
            nameType(out, 11, 12);                     // #13
            methodRef(out, 10, 13);                    // #14
            methodHandle(out, 6, 14);                  // #15 REF_invokeStatic
            utf(out, "decorate");                      // #16
            nameType(out, 16, 6);                      // #17
            indy(out, 0, 17);                          // #18 BSM 0
            utf(out, "Hi-");                           // #19
            str(out, 19);                              // #20 static String
            integer(out, 2);                           // #21 static int

            out.writeShort(0x0021); // public + super
            out.writeShort(2);      // this_class
            out.writeShort(4);      // java/lang/Object
            out.writeShort(0);      // interfaces
            out.writeShort(0);      // fields
            out.writeShort(1);      // methods

            out.writeShort(0x0009); // public static run
            out.writeShort(5);      // "run"
            out.writeShort(6);      // (String)String
            out.writeShort(1);      // Code attribute count
            out.writeShort(7);      // "Code"
            out.writeInt(19);       // attribute length
            out.writeShort(1);      // max_stack
            out.writeShort(1);      // max_locals
            out.writeInt(7);        // bytecode length
            out.writeByte(0x2a);    // aload_0
            out.writeByte(0xba);    // invokedynamic
            out.writeShort(18);     // CP #18
            out.writeShort(0);      // reserved zero bytes
            out.writeByte(0xb0);    // areturn
            out.writeShort(0);      // exception table length
            out.writeShort(0);      // nested Code attributes

            out.writeShort(1);      // class attributes
            out.writeShort(8);      // "BootstrapMethods"
            out.writeInt(10);       // attribute length
            out.writeShort(1);      // one bootstrap entry
            out.writeShort(15);     // MethodHandle #15
            out.writeShort(2);      // two static args
            out.writeShort(20);     // "Hi-"
            out.writeShort(21);     // int 2
        }
        System.out.println("generated=IndyGenerated.class");
    }
}
~~~

Note the minimal bytecode contents:

- Java 17 uses class-file major version **61**.
- The `aload_0` instruction pushes the `String` parameter onto the operand stack.
- The `invokedynamic #18` instruction calls the dynamic site `decorate:(String)String`; the bytecode ends with two 0 bytes.
- The `areturn` instruction returns the `String` for the `run` method.
- `#15` is a `REF_invokeStatic` method handle pointing to `DecorateBootstrap.bootstrap`.
- `#20` is the static argument `"Hi-"`, and `#21` is the static argument `2`. They are stored in `BootstrapMethods`, **not** loaded as parameters of the `run` method.
- The generated class **only has the static method `run(String)`**, with no constructor needed because the runner creates no instance. This is an illustrative class file, not a general-purpose bytecode generator. All constant-pool strings are ASCII so they can be written simply with `writeUTF`.

### 6.3. Runner loading the newly generated class

Save **`IndyRunner.java`**:

~~~java
import java.lang.reflect.Method;

public class IndyRunner {
    public static void main(String[] args) throws Exception {
        Class<?> generated = Class.forName("IndyGenerated");
        Method run = generated.getMethod("run", String.class);

        System.out.println("first=" + run.invoke(null, "Ada"));
        System.out.println("second=" + run.invoke(null, "Bob"));
        System.out.println("linkCount=" + DecorateBootstrap.linkCount);
    }
}
~~~

From the directory containing all three source files, using JDK 17+:

~~~sh
javac --release 17 -d out DecorateBootstrap.java IndyClassWriter.java IndyRunner.java
java -cp out IndyClassWriter out
java -cp out IndyRunner
javap -classpath out -v -p IndyGenerated
~~~

The `javap` command is an **observation step** and does not alter the output of the runner program.

**Stdout of the two `java` commands (in order):**

~~~text
generated=IndyGenerated.class
link=IndyGenerated|decorate|(String)String|Hi-|2
first=Hi-Hi-Ada
second=Hi-Hi-Bob
linkCount=1
~~~

**Why is this a real invokedynamic?** `IndyClassWriter` writes opcode `0xba` and `CONSTANT_InvokeDynamic` into the class file. The JVM links the instruction when executing `IndyGenerated.run("Ada")`. The BSM is invoked by the JVM with the exact three implicit arguments + two static arguments. `IndyRunner` uses Reflection to **call the `run` method**, but **the `invokedynamic` instruction actually resides inside the bytecode of `run`**, rather than being simulated by Reflection.

**Line-by-line explanation:**

- `caller.lookupClass().getSimpleName()` is **`IndyGenerated`**, even though the BSM is defined in `DecorateBootstrap`.
- `name` is `decorate` as attached to the site by `#17 NameAndType`.
- `type` prints `(String)String` because the call site takes one runtime `String` and returns one `String`.
- The two static arguments are `"Hi-"` and `2`; the BSM uses them to bind the prefix and repeat count.
- `"Ada"` and `"Bob"` are **dynamic arguments** of two separate invocations and do not appear in the static-argument list.
- The BSM links successfully using `ConstantCallSite`, and subsequent executions of the site use the bound target. In this sequential program, `linkCount=1`.

Let's look at the key section of `javap -v -p IndyGenerated` (these numbers are **fixed in the example generator**, but should not be treated as a general rule):

~~~text
#15 = MethodHandle ... REF_invokeStatic DecorateBootstrap.bootstrap
#17 = NameAndType  #16:#6    // decorate:(Ljava/lang/String;)Ljava/lang/String;
#18 = InvokeDynamic #0:#17   // #0:decorate:(Ljava/lang/String;)Ljava/lang/String;
#20 = String       #19       // Hi-
#21 = Integer      2
...
  public static java.lang.String run(java.lang.String);
    ...
       1: invokedynamic #18,  0
...
BootstrapMethods:
  0: #15 REF_invokeStatic DecorateBootstrap.bootstrap...
    Method arguments:
      #20 Hi-
      #21 2
~~~

This is the concrete relationship between *call-site name/type* and *bootstrap method + static args* in the class file. Do not confuse the literal `"Hi-"` with `"Ada"`/`"Bob"`.

## 7. How does a BSM return a `CallSite` properly?

The BSM is responsible for ensuring that `CallSite.type()` **equals** the `invokedType` passed by the JVM. In the example:

~~~text
BSM signature:    (Lookup,String,MethodType,String,int)CallSite
Site descriptor:  (String)String
Target before bind:(String,int,String)String
Static arguments: "Hi-", 2
Target after bind:  (String)String
CallSite.type():  (String)String  [matches site]
~~~

The JVM does not automatically guess "pass two static args and drop them from the target signature". It is the BSM itself that calls `insertArguments` to **transform** the initial target into the exact method handle the site needs.

### Types of `CallSite`

| Class | Can the target change? | When to use |
| --- | --- | --- |
| `ConstantCallSite` | No. `setTarget` always throws `UnsupportedOperationException` | Fixed linkage, such as lambda factories or immutable custom sites |
| `MutableCallSite` | Yes; observing updates across threads requires coordinating `MutableCallSite.syncAll(...)` per the API | Inline caches, runtimes needing to relink targets with lower memory-ordering cost |
| `VolatileCallSite` | Yes, the target has volatile semantics on update/read | Needing other threads to see target updates under volatile contract |

Even when mutable, **the type of the call site does not change**. `setTarget(newTarget)` requires `newTarget.type()` to have the same type as the old target; otherwise, it throws `WrongMethodTypeException`. One cannot change `(String)String` to `(int)int` just by relinking.

**`CallSite.dynamicInvoker()`** provides a method handle equivalent to a dynamic call to the current target. For `ConstantCallSite`, it is equivalent to the fixed target; for mutable/volatile sites, it follows the updated target according to the respective rules. In section 6, the JVM attaches the `CallSite` itself to execute `invokedynamic`.

### When is `MethodHandle.asType` needed?

A target method looked up with `Lookup` may have a method type different from the site type yet **validly convertible** via `asType(invokedType)`. For example, a handle returning `Integer` while the site expects `Object` can be adapted. However, `asType` does **not** automatically allow arbitrary primitive narrowing or turning a `String` into a number. If a conversion is invalid, the BSM should check/redesign the adapter rather than returning a target of the wrong type.

Do not assume the JVM will automatically adapt a `CallSite` whose target type differs from the descriptor: **that is the BSM's responsibility before returning the CallSite**. A mismatch still fails linkage.

## 8. Bootstrap errors: `BootstrapMethodError` and main causes

Errors during the **resolution/linkage** step differ from exceptions thrown **after the target has run**.

| Situation | Typical consequence |
| --- | --- |
| Bootstrap method handle cannot be resolved or static arguments cannot be resolved | Linkage fails, potentially with `LinkageError`/`BootstrapMethodError` depending on the phase |
| BSM receives wrong/missing static arguments and cannot be invoked via `invokeWithArguments` | Usually causes an exception when invoking the BSM; the runtime may report `BootstrapMethodError` depending on the underlying exception |
| BSM throws an exception that is **not an `Error`** | JVMS requires resolution to fail with `BootstrapMethodError` wrapping the original cause |
| BSM directly throws an `Error` or subclass | Resolution may fail with **that `Error` itself**, not always wrapped |
| BSM returns `null`, or a value that is not a `CallSite` | `BootstrapMethodError` |
| BSM returns a CallSite whose type **differs** from the site descriptor | `BootstrapMethodError` |
| Already linked fine, target throws `IllegalArgumentException` or another exception at invoke time | Error from **target invocation**, not `BootstrapMethodError` by default |

**Incorrect target type example (snippet, not a standalone program):**

~~~java
// actual invokedType is (String)String
MethodHandle wrong = MethodHandles.constant(String.class, "bad");
// wrong.type() == ()String, not (String)String
return new ConstantCallSite(wrong);
~~~

If the logic above is placed into the BSM of a `(String)String` site and `invokedynamic` is actually executed, the JVM will reject the CallSite type `()String` and fail linkage with `BootstrapMethodError`. This is **not** a regular `MethodHandle.invoke(...)` call that adapts types automatically; the `invokedynamic` validator requires **CallSite type equal to the site descriptor**.

### Runtime errors often misattributed to the BSM

- `ClassCastException` in the target body: do not automatically conclude the BSM is wrong; inspect the target's conversion/cast code.
- `WrongMethodTypeException` when the BSM builds an invalid `asType` adapter: the BSM may throw this exception, after which the JVM reports a bootstrap error during linkage.
- `IllegalAccessException` when the BSM uses `Lookup.findStatic` with insufficient privileges: identify who `lookupClass()` is and whether the target is accessible.
- `NoSuchMethodException` when the BSM looks up a method with the wrong name/type: this is a lookup error in the BSM, not the JVM automatically selecting an overload for `name`.
- `InvocationTargetException` may appear if the application itself uses `Method.invoke` to call the runner/target (such as `IndyRunner`); it is Reflection's wrapper, **not** how `invokedynamic` wraps every exception from the target.

**How to investigate:** look at the outer error and `getCause()` (when present), distinguishing bootstrap, target, and caller stack frames. Do not "fix" a BSM by swallowing an exception and returning a wrong-typed CallSite: that only turns a clear root cause into a hard-to-diagnose linkage error.

## 9. The issue that a site may bootstrap multiple times concurrently

JVMS 17 states the possibility that multiple threads simultaneously resolve a symbolic reference to a dynamically-computed call site:

1. Multiple bootstrap method invocations **may run concurrently**.
2. The JVM selects **one result** and installs that result for all threads using the same symbolic reference at the appropriate site.
3. Other bootstrap executions may complete, but their results are discarded.

Therefore, when a BSM creates expensive objects, writes to a global cache, or increments a counter without synchronization, there is a risk of duplicated side effects. Do not take the `linkCount=1` output of the sequential example as a guarantee for all concurrent scheduling.

On the other hand, **an instruction that has linked successfully reuses the link**, without calling the BSM again on every execution. `ConstantCallSite` fixes the target; `MutableCallSite`/`VolatileCallSite` allow changing the target **without re-bootstrapping** once per switch. Changing the target must obey type/visibility semantics.

Regarding granularity, understand that linkage belongs to the **call site/symbolic reference in the class-file context**, not an automatic singleton shared across all classes, all instructions, or all class loaders. Two call sites calling the same BSM and having the same static args **do not thereby default to a single CallSite**.

## 10. Comparison with `ConstantDynamic` (to avoid confusing contracts)

Since Java 11, the constant pool also has `CONSTANT_Dynamic` (*condy*): a **constant computed upon resolution**. Condy also uses a bootstrap method and static arguments, but with a different goal:

| Characteristic | `invokedynamic` | `CONSTANT_Dynamic` |
| --- | --- | --- |
| What is resolved | Dynamic **call site** | Dynamic **constant** |
| Common third input | `MethodType` (method descriptor) | `Class<?>` (field descriptor / constant type) |
| Required result | `CallSite` whose type matches site descriptor | Constant value matching constant descriptor |
| Runtime after resolution | Invokes target when instruction runs | Uses resolved constant value |
| Focus of this lesson? | **Yes** | Only for distinction |

Do not write a generic BSM for condy and assume the signature/return is valid for indy, and vice versa. The JVMS clearly specifies the different inputs and validation for the two kinds of symbolic references.

## 11. Checklist for designing and verifying a bootstrap method

When building a compiler, bytecode emitter, runtime linker, or analyzing `javap`, check in order:

1. **What name and descriptor does `CONSTANT_InvokeDynamic` have?** Determine the exact arity and return type, not just the method name in source.
2. **Which bootstrap index?** Look up the corresponding entry in `BootstrapMethods`, then trace `bootstrap_method_ref` to the specific method handle.
3. **How many static arguments?** Read the constant-pool kinds, order, values, and resolution/boxing behavior; do not confuse them with runtime operands.
4. **Can the BSM accept those values?** Check the method handle type or varargs collector per `invokeWithArguments` semantics; for example, `String` and `int` must match or be convertible.
5. **Who is `caller.lookupClass()`?** It is the class containing the call site. Use lookup privileges appropriate for the target/module, without assuming privileges from the bootstrap class.
6. **How does the BSM handle `name`?** Does it dispatch by name, ignore name, or validate a set of names? Do not assume name is the target's name.
7. **What does the BSM do with `invokedType`?** Create a target method handle with the exact type, binding parameters or using `asType` if valid.
8. **Is the `CallSite` non-null and its type an exact match?** Do not return a wrong-type target hoping the JVM will cast it automatically.
9. **Choose `ConstantCallSite` or mutable/volatile?** Is relinking needed, what is the memory visibility across threads, and how does type immutability apply?
10. **Does the BSM have side effects?** Account for concurrent resolution and caching; do not rely on "runs only once" as a guard.
11. **Is the failure at linkage or invocation?** Distinguish `BootstrapMethodError` from target exceptions; inspect the cause and stack trace.
12. **Can the bytecode be verified?** Run `javap -v -p -c` and inspect `InvokeDynamic`, `BootstrapMethods`, the BSM method handle, and static args together.

### Common mistakes

- "The three BSM arguments are inputs passed by the application on every site call." — False: the JVM supplies them at linkage time.
- "`caller` is the `Lookup` of the class containing the bootstrap method." — False: it reflects the class containing the instruction.
- "`name` must be the name of the target Java method." — False: it is the call site name; the BSM chooses its meaning.
- "`invokedType` is the signature of the BSM." — False: it is the type of the **call site**.
- "Static args are `static` fields." — False: they are constant-pool metadata attached to the bootstrap specifier.
- "Just return any `CallSite` and the JVM will adapt it automatically." — False: the type must match exactly.
- "`asType` can convert any data." — False: conversions have limits.
- "Every execution of indy calls the BSM again." — False after successful linkage.
- "A BSM is never invoked concurrently for a site." — False per the JVMS.
- "`invokedynamic` is only created using Java Reflection code." — False: it is an opcode in the class file; Reflection can help invoke a method containing the opcode, but does not create that opcode.
- "A lambda site type is always `(String)String` if the lambda body takes/returns `String`." — False: the site type usually describes **the factory creating the functional object**.
- "Every BSM exception is wrapped into `BootstrapMethodError`." — False: the JVMS distinguishes `Error` from other exceptions.
- "Two sites sharing a BSM means sharing a single CallSite." — Not guaranteed; each site links per symbolic reference context.

## 12. Exercises with answers

**Question 1.** An instruction has `name="make"`, descriptor `(I)Ljava/lang/String;`, and static arg `"TAG"`. What is the `MethodType` supplied by the JVM?

**Answer:** `MethodType.methodType(String.class, int.class)`, displayed as `(int)String`. `"TAG"` does not increase the number of runtime arguments of the site.

**Question 2.** A BSM declares `(Lookup,String,MethodType,String,int)CallSite`, and `BootstrapMethods` has two static args `"Hi-"`, `2`. Which are the three implicit args and which are the two static args?

**Answer:** The caller's Lookup, name, and MethodType are implicit JVM inputs. `"Hi-"` and `2` are static arguments from the class file, in exact order. The site's runtime argument is passed after the BSM links, and is not among these five values passed to the BSM.

**Question 3.** If `caller.lookupClass()` prints `IndyGenerated` while the bootstrap is defined in `DecorateBootstrap`, is that wrong?

**Answer:** No. That is precisely the caller context of the invokedynamic instruction.

**Question 4.** For a `(String)String` site, the BSM returns `new ConstantCallSite(MethodHandles.constant(String.class,"x"))`. Why does it fail?

**Answer:** The handle from `constant` has type `()String`, so the CallSite type mismatches the `(String)String` descriptor; the JVM reports `BootstrapMethodError` during linkage.

**Question 5.** In the `LambdaIndyDemo` example, the indy name is `apply` and the site type is `()UnaryOperator`. Why is it not `(String)String`?

**Answer:** The site creates a functional object. `(String)String` describes the implementation method/instantiated SAM type, a static argument to `LambdaMetafactory`, not the type of the factory site.

**Question 6.** `compareAndSet` and `invokedynamic` are both runtime-related. Can they be called the same kind of "bootstrap method"?

**Answer:** No. CAS is an atomic update on a variable; invokedynamic bootstrap is the operation of linking a dynamic call site. They differ in goal and API.

**Question 7.** If the same `IndyGenerated.run` is called sequentially 1,000 times after successful linkage, must the BSM run 1,000 times?

**Answer:** No. The linkage is retained to execute the target on subsequent calls. However, do not extrapolate this into a guarantee that concurrent resolution always invokes the BSM only once.

**Question 8.** A BSM throws `IllegalArgumentException` while creating an adapter; what is the outer error typically? What if it throws `LinkageError` itself?

**Answer:** `IllegalArgumentException` is not an `Error`, so resolution fails with `BootstrapMethodError` carrying the original cause. An `Error` may be propagated as itself according to JVMS rules.

**Question 9.** To have a target with two static parameters pre-bound, where should the adjustment be made?

**Answer:** Inside the BSM, use `insertArguments`/appropriate combinators to bring the initial target to the exact type of the site. Static arguments are not automatically stripped from the target descriptor by the JVM.

**Question 10.** Why can't `javap -c` alone be used to fully understand static bootstrap arguments?

**Answer:** `javap -c` shows the opcode and constant-pool index, whereas `javap -v` displays `BootstrapMethods` and the metadata needed to relate the BSM to its static arguments.

## 13. Java 17 Reference Documentation

- JVMS 17, `5.4.3.6` — *Dynamically-Computed Constant and Call Site Resolution*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6
- JVMS 17, `4.4.10` — `CONSTANT_InvokeDynamic_info`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10
- JVMS 17, `4.7.23` — `BootstrapMethods` attribute: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.23
- JVMS 17, `6.5` — `invokedynamic` instruction: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic
- Java SE 17, `CallSite`, `ConstantCallSite`, `MutableCallSite`, `VolatileCallSite`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html
- Java SE 17, `LambdaMetafactory` and the three bootstrap static arguments for lambdas: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html
- Java SE 17, `MethodHandles.Lookup` / `MethodHandle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE 17, `BootstrapMethodError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/BootstrapMethodError.html

**Conclusion:** The contract of an `invokedynamic` BSM is that **the JVM supplies the calling class's `Lookup`, the site name, the site `MethodType`, and the encoded static arguments**, and then requires a non-null `CallSite` with a target type matching the descriptor. The BSM decides how to look up/bind/adapt the target; the JVM retains the link and executes the target for subsequent dynamic arguments. Clearly distinguishing **linkage inputs**, **static metadata**, and **runtime call arguments** is the key to reading `javap`, debugging `BootstrapMethodError`, and designing safe bootstraps.