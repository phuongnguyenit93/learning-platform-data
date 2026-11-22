# Wrapping Native Methods with Java Methods at Initial Class Definition

A Java method declared as **native** has no **Code attribute** containing JVM instructions, so timing, tracing, or logging calls cannot be placed directly into that method's body using ASM's `AdviceAdapter`. To measure **calls going from Java into native code**, a Java agent can transform the class file **at the time the JVM defines the class for the first time**, creating a **non-native Java wrapper** that keeps the original name/descriptor and renaming the native declaration with a dedicated prefix. The wrapper contains bytecode that records the call and then invokes the renamed native method.

However, renaming a native method raises a question: **how is an existing JNI C/C++ library linked**, if it exports the old name such as **Java_demo_NativeMath_add** rather than the new name? Java Instrumentation provides **Instrumentation.setNativeMethodPrefix(...)**, which allows the JVM to retry native method resolution by considering a prefix registered by the transformer.

The goal of this lesson is to understand the mechanism and limitations of **native wrapping at initial class definition**, distinguish Java Instrumentation from **JNI** and **JVM TI**, and implement a Java 17 + JNI C + ASM demo. This is **not** a technique for replacing C/C++ implementations or a mechanism for adding methods to any already-loaded class via retransformation.

## 1. Distinguishing Native Methods and Java Methods

~~~java
// Application source code.
public static native int add(int a, int b);
~~~

The class file records the **ACC_NATIVE** flag and a method descriptor, for example **(II)I** (takes two `int`s, returns an `int`). A native declaration **has no Java Code attribute**. Meanwhile, a normal Java method:

~~~java
public static int addJava(int a, int b) {
    return a + b;
}
~~~

has a **Code attribute** and instructions such as `ILOAD`, `IADD`, `IRETURN`. A `ClassFileTransformer` can transform class file bytes, but it cannot "insert `ILOAD` into the Code of a native method" when there is no Code.

| Characteristic | Regular Java method | Native method |
| --- | --- | --- |
| ACC_NATIVE | No | Yes |
| Code attribute | Yes, for methods with a body | No |
| JVM instructions representing method body | Yes | No |
| ASM AdviceAdapter insertion into method body | Possible | Not directly |
| Execution path | JVM/interpreter/JIT | JNI/native implementation |
| Suitable Java instrumentation point | Insert advice into Code | Create a **Java wrapper** then call native |
| JNI symbol compatibility | No native resolution | Must resolve to the correct native implementation |

If you both keep **ACC_NATIVE** and add a Code attribute to the **same method**, the class file is invalid. If you remove `ACC_NATIVE` without generating valid Code for the Java method, the class file can also be rejected. Rather, there must be **two separate methods**: one native declaration and one Java wrapper.

## 2. Before and After Transformation Model

Initially:

~~~java
// Original source: demo.NativeMath
public static native int add(int a, int b);
~~~

After the transformer processes the class file at initial load, the JVM sees an equivalent structure:

~~~java
// Java model for explanation; not compiler-modified source.
public static int add(int a, int b) {
    recordEnter();
    int value = $$$DemoNative$$_add(a, b);
    recordExit();
    return value;
}

public static native int $$$DemoNative$$_add(int a, int b);
~~~

Where:

- **add(II)I** remains the API that callers were compiled against and invoke. However, it is now a **Java method with Code**, not native.
- **$$$DemoNative$$_add(II)I** is the new native declaration with the same descriptor, so it can still route to the original C code.
- **setNativeMethodPrefix(transformer, "$$$DemoNative$$_")** tells the JVM how to retry native resolution when the new name does not find an implementation under standard rules.
- **recordEnter/recordExit** can be event/metric/tracing code. In the demo, we print to the console for easy verification.
- If the native call throws a `Throwable`, the `recordExit` statement located **after the invocation** will not run; to record exceptional exits as well, you must build a separate Java handler and rethrow the exact `Throwable`.

Diagram:

~~~text
App.main
   |
   v
NativeMath.add(2,3)       <- new Java wrapper
   |
   +-- WRAP_ENTER
   |
   +-- $$$DemoNative$$_add(2,3)  <- prefixed native method
                |
                v
           JVM JNI resolution
                |
                +-- try symbol by new name
                |
                +-- if not found: native-prefix fallback
                |
                v
           Java_demo_NativeMath_add(JNIEnv*, jclass, jint, jint)
                |
                v
             return 5
   |
   +-- WRAP_EXIT
   |
   v
RESULT=5
~~~

Java instrumentation points can observe **the timing around the native call**, but cannot themselves see C instructions, `malloc`/native heap, native locks, or internal JNI function details. Measuring inside native code requires a native profiler, JVMTI, or appropriate C/C++ instrumentation.

## 3. Why Must the Wrapper Be Created When the Class Is Defined?

When **ClassFileTransformer** receives bytes during the **initial class definition**, the JVM has not yet installed the method schema for that class. The transformer is permitted to propose a valid class file containing:

1. The original native method **renamed**.
2. A **new** Java method with the original name and descriptor.
3. Bytecode in `Code` to record and invoke the prefixed native method.

That is, there is a **structural class change**.

**retransformClasses** and **redefineClasses** on already-loaded classes have important restrictions regarding adding, removing, or renaming methods, fields, and other schema parts. You cannot by default attach an agent to an already-running application and retransform an already-loaded native method into two methods. Some types of instrumentation on the `Code` of an existing Java method are still supported, but **a native wrapper requiring a new method and renaming a native method** is a different case.

Exact timeline:

~~~text
JVM -javaagent:... starts
   |
   v
premain(agentArgs, Instrumentation)
   |
   +-- check isNativeMethodPrefixSupported()
   +-- addTransformer(t, false)
   +-- setNativeMethodPrefix(t, PREFIX)
   |
   v
Application starts using demo.NativeMath
   |
   v
ClassFileTransformer.transform(...) at initial definition
   |
   +-- match className / method descriptor / ACC_NATIVE
   +-- rename native add -> PREFIX + add
   +-- add Java method add() containing Code
   +-- return new class file byte[]
   |
   v
JVM verify/link/define class
   |
   v
NativeMath.add() calls wrapper -> prefixed native -> C implementation
~~~

Registering **before the target class loads** is the key point. If `premain` code or an agent dependency accidentally references `NativeMath` before registering the transformer, the opportunity to create the wrapper at initial load has passed. Do not bundle the application target class into the agent JAR and use it directly inside `premain`.

**Warning:** `ClassFileTransformer` can also be called during redefine/retransform; the example below only supports initial definition and intentionally skips when **classBeingRedefined != null**. Once the class is loaded, do not attempt to return bytes that add a new method.

## 4. Native Method Prefix: Capability and Registration Order

Two Java SE 17 APIs you need to know:

~~~java
// Signatures from java.lang.instrument.Instrumentation.
boolean isNativeMethodPrefixSupported();

void setNativeMethodPrefix(
        ClassFileTransformer transformer, String prefix);
~~~

The **native-prefix capability is optional**, granted by the JVM if the agent manifest requests **Can-Set-Native-Method-Prefix: true** and the JVM supports it. A manifest missing this attribute usually causes **isNativeMethodPrefixSupported()** to return `false`.

Correct code sequence:

~~~java
// Illustrative snippet in premain, not a standalone file.
if (!inst.isNativeMethodPrefixSupported()) {
    throw new IllegalStateException(
        "Native method prefix unsupported");
}

ClassFileTransformer transformer = new NativeWrapTransformer();
inst.addTransformer(transformer, false);
inst.setNativeMethodPrefix(transformer, "$$$DemoNative$$_");
~~~

**setNativeMethodPrefix** must receive a **transformer that has already been registered**, otherwise it may throw **IllegalArgumentException**. If `transformer` is `null`, it may throw **NullPointerException**; if the capability is not granted, **UnsupportedOperationException**. An empty or `null` prefix does not enable prefix-based retry of native resolution for that transformer.

A prefix like **wrapped_** can easily collide with existing method names; use an agent-specific name, for example **$$$DemoNative$$_**. The prefix must **match character for character** between the native declaration name generated by the transformer and the argument to `setNativeMethodPrefix`.

### 4.1. Prefix Alone Does Not Create Methods

Calling `setNativeMethodPrefix` alone without actually transforming the class file **does not create a wrapper** and does not alter the native method. The transformer still needs to receive `classfileBuffer`, write a valid class file, and return a **new `byte[]`**. If the class is out of scope, **return `null`**.

### 4.2. JNI Resolution: Automatic and RegisterNatives

According to JNI, the JVM can locate a native implementation via:

- **Automatic native method resolution**: looking up a symbol based on the escaped class/method name, for example **Java_demo_NativeMath_add**.
- **RegisterNatives**: the native library explicitly binds a method name + descriptor to a C function pointer.

The **setNativeMethodPrefix** Javadoc specifies fallback for **both** paths:

- Automatic: the JVM tries the symbol of the prefixed native method; if not found, it can retry with the prefix stripped from the implementation name being searched.
- RegisterNatives: when an association by the original name fails to find a matching declaration after renaming, the JVM can retry the association using the prefixed method name.

Therefore, the C library can continue exporting **Java_demo_NativeMath_add**, while the Java declaration is renamed to **$$$DemoNative$$_add**. This mechanism is only used when normal resolution fails, so you can **selectively wrap** specific native methods.

**Not every third-party JNI library is guaranteed to be automatically compatible**: some libraries call `GetMethodID` themselves, use dynamic native registration, reside on a different bootstrap class loader, or have special metadata/native symbols. Testing on the target native library and JDK is necessary.

## 5. Hands-On Lab: Java 17 + JNI C + ASM

We will build a complete program with the native method **demo.NativeMath.add(int,int)**, a C implementation returning the sum of two numbers, and a Java startup agent using ASM to turn the native method into a wrapper. There is no bytecode library in the **application**; ASM belongs solely to the **agent**.

Results to demonstrate:

- **Without agent**: JNI works, output **RESULT=5**.
- **With agent**: console prints **AGENT_PREFIX_READY**, **AGENT_WRAPPED**, **WRAP_ENTER**, **WRAP_EXIT**, and finally still **RESULT=5**.
- The original C JNI symbol name **is unchanged**.

### 5.1. Directory Structure

~~~text
nativewrap-demo/
  pom.xml
  src/
    agent/
      java/
        demo/
          NativeAgent.java
    app/
      java/
        demo/
          NativeMath.java
          App.java
    native/
      nativeops.c
  out/
    app/             <-- generated by javac
    include/         <-- JNI header generated by javac -h
  target/
    nativewrap-agent.jar  <-- created by Maven Shade
~~~

Separating the application code from the agent ensures **demo.NativeMath is not accidentally defined before the transformer is registered**.

### 5.2. File src/app/java/demo/NativeMath.java

~~~java
package demo;

public final class NativeMath {
    static {
        System.loadLibrary("nativeops");
    }

    private NativeMath() {
    }

    public static native int add(int a, int b);
}
~~~

**System.loadLibrary("nativeops")** loads the library according to the platform naming convention: Linux **libnativeops.so**, macOS **libnativeops.dylib**, Windows **nativeops.dll**. It does not compile C automatically. The class initializer runs before the first native method call.

### 5.3. File src/app/java/demo/App.java

~~~java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("RESULT=" + NativeMath.add(2, 3));
    }
}
~~~

The `NativeMath` class has not been used in `premain`, so when `main` starts and executes the call, the transformer is already in place.

### 5.4. File src/native/nativeops.c

~~~c
#include "demo_NativeMath.h"

JNIEXPORT jint JNICALL Java_demo_NativeMath_add(
        JNIEnv* env, jclass owner, jint a, jint b) {
    (void) env;
    (void) owner;
    return a + b;
}
~~~

The **demo_NativeMath.h** header is generated by **javac -h** from the original declaration. Because the method is **static**, the second JNI parameter is **jclass**. An instance native method uses **jobject** in that position. **JNIEnv*** is tied to a thread and must not be saved and arbitrarily reused on another thread.

The C function keeps the name **Java_demo_NativeMath_add** rather than being changed to a prefixed symbol. The JVM's prefix fallback handles the linkage.

### 5.5. File src/agent/java/demo/NativeAgent.java

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class NativeAgent {
    private static final String PREFIX = "$$$DemoNative$$_";

    private NativeAgent() {
    }

    public static void premain(String args, Instrumentation inst) {
        if (!inst.isNativeMethodPrefixSupported()) {
            throw new IllegalStateException(
                    "Native prefix unsupported");
        }

        ClassFileTransformer t = new NativeWrapTransformer();
        inst.addTransformer(t, false);
        inst.setNativeMethodPrefix(t, PREFIX);
        System.out.println("AGENT_PREFIX_READY");
    }

    private static final class NativeWrapTransformer
            implements ClassFileTransformer {

        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer) {

            if (!"demo/NativeMath".equals(className)
                    || classBeingRedefined != null) {
                return null;
            }

            ClassReader reader = new ClassReader(classfileBuffer);
            ClassWriter writer = new ClassWriter(
                    reader, ClassWriter.COMPUTE_MAXS);
            boolean[] changed = {false};

            ClassVisitor visitor = new ClassVisitor(
                    Opcodes.ASM9, writer) {

                @Override
                public MethodVisitor visitMethod(
                        int access,
                        String name,
                        String descriptor,
                        String signature,
                        String[] exceptions) {

                    boolean selected =
                            "add".equals(name)
                            && "(II)I".equals(descriptor)
                            && (access & Opcodes.ACC_NATIVE) != 0
                            && (access & Opcodes.ACC_STATIC) != 0;

                    if (!selected) {
                        return super.visitMethod(
                                access, name, descriptor,
                                signature, exceptions);
                    }

                    changed[0] = true;

                    // Original method remains native, but with a prefix.
                    return super.visitMethod(
                            access, PREFIX + name, descriptor,
                            signature, exceptions);
                }

                @Override
                public void visitEnd() {
                    if (changed[0]) {
                        MethodVisitor mv = super.visitMethod(
                                Opcodes.ACC_PUBLIC
                                        | Opcodes.ACC_STATIC,
                                "add", "(II)I", null, null);

                        mv.visitCode();
                        print(mv, "WRAP_ENTER");

                        mv.visitVarInsn(Opcodes.ILOAD, 0);
                        mv.visitVarInsn(Opcodes.ILOAD, 1);
                        mv.visitMethodInsn(
                                Opcodes.INVOKESTATIC,
                                "demo/NativeMath",
                                PREFIX + "add",
                                "(II)I", false);

                        mv.visitVarInsn(Opcodes.ISTORE, 2);
                        print(mv, "WRAP_EXIT");
                        mv.visitVarInsn(Opcodes.ILOAD, 2);
                        mv.visitInsn(Opcodes.IRETURN);

                        // With COMPUTE_MAXS, ASM computes max.
                        mv.visitMaxs(0, 0);
                        mv.visitEnd();
                    }
                    super.visitEnd();
                }

                private void print(
                        MethodVisitor mv, String message) {
                    mv.visitFieldInsn(
                            Opcodes.GETSTATIC,
                            "java/lang/System", "out",
                            "Ljava/io/PrintStream;");
                    mv.visitLdcInsn(message);
                    mv.visitMethodInsn(
                            Opcodes.INVOKEVIRTUAL,
                            "java/io/PrintStream", "println",
                            "(Ljava/lang/String;)V",
                            false);
                }
            };

            reader.accept(visitor, 0);

            if (!changed[0]) {
                return null;
            }

            System.out.println(
                    "AGENT_WRAPPED demo/NativeMath.add");
            return writer.toByteArray();
        }
    }
}
~~~

This is a complete Java file using **ASM 9.7.1**. Note the following principles:

1. The transformer filters on the internal class name **demo/NativeMath**, and skips redefinition callbacks. In complex class loader environments, you should also filter by defining loader/module.
2. Match **name + descriptor (II)I + ACC_NATIVE + ACC_STATIC**; do not apply blindly to overloads.
3. The original native method is renamed to **$$$DemoNative$$_add** while **keeping ACC_NATIVE**, flags, and descriptor. It receives no `Code`.
4. The wrapper adds the method **public static add(II)I**, **without ACC_NATIVE**, with `Code`.
5. The wrapper prints `WRAP_ENTER`, loads the two `int`s from local slots 0/1, calls **INVOKESTATIC** on the prefixed native method, stores the result in slot 2, prints `WRAP_EXIT`, and then executes `IRETURN`.
6. **ClassWriter.COMPUTE_MAXS** recomputes stack/local sizes for this simple branchless method. `classfileBuffer` is not mutated; the writer returns a new byte array.
7. When no matching native method is found, return `null`; do not produce a pointless new class copy.
8. The **AGENT_WRAPPED** log indicates that the transformer supplied new bytes, **not proof that JNI executed correctly**. You must observe the application's output.

The demo code does not add an exceptional-exit hook, nor does it support instance methods, `void`/`long`/`double`/object returns, or `synchronized` native methods. Those cases require a general generator and separate bytecode verification.

### 5.6. File pom.xml: Packaging ASM into the Agent

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>nativewrap-agent</artifactId>
  <version>1.0.0</version>

  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.7.1</version>
    </dependency>
  </dependencies>

  <build>
    <sourceDirectory>src/agent/java</sourceDirectory>
    <finalName>nativewrap-agent</finalName>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.5.3</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <manifestEntries>
                    <Premain-Class>demo.NativeAgent</Premain-Class>
                    <Can-Set-Native-Method-Prefix>true</Can-Set-Native-Method-Prefix>
                  </manifestEntries>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Maven compiles **only the agent sources** from `src/agent/java`, packages ASM into the JAR, and generates the manifest with **Premain-Class** and **Can-Set-Native-Method-Prefix: true**. Maven needs to download dependencies from the repository on the first run or use cached versions. If multiple agents carry different versions of ASM, consider **shading/relocation** or class loader isolation to avoid conflicts.

**Can-Retransform-Classes** and **Can-Redefine-Classes** are not needed for this initial-load wrapper demo. Both are capabilities distinct from native prefix.

## 6. Build Commands and Output on Linux

### 6.1. Compile Java and Generate the JNI Header

~~~bash
mkdir -p out/app out/include

javac --release 17 -h out/include -d out/app \
  src/app/java/demo/NativeMath.java \
  src/app/java/demo/App.java
~~~

Use **javac -h** to generate **out/include/demo_NativeMath.h** with the exact JNI prototype. The file **out/app/demo/NativeMath.class** remains the original class with the native declaration, without a wrapper yet.

### 6.2. Compile the C Library with gcc

Set **JAVA_HOME** to the JDK directory. In a POSIX shell on Linux with `readlink -f`, you can compute it as:

~~~bash
JDK_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

gcc -shared -fPIC \
  -I"$JDK_HOME/include" \
  -I"$JDK_HOME/include/linux" \
  -Iout/include \
  -o libnativeops.so \
  src/native/nativeops.c
~~~

The shared library build command and include paths depend on the OS. macOS typically uses **include/darwin** and **libnativeops.dylib**; Windows uses the appropriate compiler tools to build **nativeops.dll**. Do not put `.so` files on the Java classpath instead of using **System.loadLibrary**.

### 6.3. Package the Agent

~~~bash
mvn -q -DskipTests package
jar tf target/nativewrap-agent.jar
~~~

The JAR must contain **META-INF/MANIFEST.MF**, **demo/NativeAgent.class**, and the packaged ASM classes. The manifest must have **Premain-Class: demo.NativeAgent** and **Can-Set-Native-Method-Prefix: true**. If the prefix attribute is missing, **isNativeMethodPrefixSupported()** may return `false` even if the JVM generally supports that capability.

### 6.4. Baseline Run Without Agent

~~~bash
java -Djava.library.path=. -cp out/app demo.App
~~~

Output:

~~~text
RESULT=5
~~~

Without a wrapper, the original native method resolves to the C implementation and returns `2+3=5`.

### 6.5. Run With Agent

~~~bash
java -Djava.library.path=. \
  -javaagent:target/nativewrap-agent.jar \
  -cp out/app demo.App
~~~

Expected output:

~~~text
AGENT_PREFIX_READY
AGENT_WRAPPED demo/NativeMath.add
WRAP_ENTER
WRAP_EXIT
RESULT=5
~~~

**Output explanation:** `premain` registers the prefix; the transformer sees `NativeMath` at initial definition and returns class bytes containing the wrapper; the wrapper logs entry and then calls the prefixed native method; JNI resolves back to the original C native symbol; the wrapper logs exit; the caller receives **5**.

If the native call throws an exception, **WRAP_EXIT** will not appear because there is no exceptional-path handler in the demo. When implementing production telemetry, you must decide how to measure **normal exit** and **exceptional exit** separately.

**Demo reliability:** the same ASM algorithm and native-prefix resolution were verified against a compatible JDK using an ASM tool with an equivalent API. The Maven build using ASM 9.7.1 is provided as instructed, though not directly tested in the reader's production environment.

## 7. Native Resolution Mechanism Behind the Example

### 7.1. JNI Name Mangling

The JVM has rules for constructing native symbol names from class/method names, consisting of the prefix **Java_**, the escaped binary class name, an underscore, and the escaped method name. For overloaded native methods, a long name appending the escaped parameter descriptor may be required.

Non-overloaded example:

~~~text
Java class:          demo.NativeMath
Native declaration:  add(II)I
JNI symbol:          Java_demo_NativeMath_add
~~~

Important escapes: **/** usually becomes **_**, an underscore in the original name becomes **_1**, a semicolon in a descriptor becomes **_2**, and **[** becomes **_3**. Use **javac -h** rather than manually concatenating JNI names as strings when dealing with overloaded methods, arrays, or object parameters.

### 7.2. Prefix Fallback in the Example

~~~text
Native method in the transformed class:
    $$$DemoNative$$_add(II)I

JVM searches for symbol by prefixed native name
    |
    +-- no matching implementation found
    |
    +-- transformer's native prefix is "$$$DemoNative$$_"
    |
    +-- retry resolution using original name add
    |
    v
Java_demo_NativeMath_add -> existing C code
~~~

**setNativeMethodPrefix does not automatically rename C symbols**; it changes the JVM's fallback strategy. Because fallback is only used after normal resolution fails, an unrenamed native method continues to work as before, allowing a transformer to wrap selectively.

### 7.3. JNI RegisterNatives

If a library uses **JNI RegisterNatives** instead of automatic symbol export, the JVM also has rules for retrying the association when a method name is prefixed by a transformer. However, a native library may use custom policies, method lookups, or complex registration paths; you must test against the exact target native library and JDK version.

### 7.4. The "Native Library Loaded" Condition

**System.loadLibrary("nativeops")** runs in the static initializer of `NativeMath` in the demo. If that call is omitted or the JVM cannot find **libnativeops.so**, the wrapper can still be defined properly, but invocation will fail with **UnsatisfiedLinkError**. This is a **JNI load/linkage** error, not evidence that the `ClassFileTransformer` failed to work.

## 8. Using javap to Verify the Class File

For the original file:

~~~bash
javap -c -p -s -classpath out/app demo.NativeMath
~~~

You will see the native method **add(II)I**, but not the wrapper. That is normal: `ClassFileTransformer` does not overwrite **out/app/demo/NativeMath.class**; it returns bytes for the JVM to use when defining the class in memory.

To inspect the transformed class, you need to dump **the bytes returned by the transformer** in a test environment and run `javap` on that dump, or use appropriate class/runtime analysis tools. Do not dump class bytes indiscriminately in production due to overhead and data-leak risks.

Abbreviated disassembly of the class after transformation:

~~~text
public static native int $$$DemoNative$$_add(int, int);
  descriptor: (II)I
  flags: ACC_PUBLIC, ACC_STATIC, ACC_NATIVE

public static int add(int, int);
  descriptor: (II)I
  flags: ACC_PUBLIC, ACC_STATIC
  Code:
    getstatic java/lang/System.out
    ldc "WRAP_ENTER"
    invokevirtual java/io/PrintStream.println
    iload_0
    iload_1
    invokestatic demo/NativeMath.$$$DemoNative$$_add
    istore_2
    getstatic java/lang/System.out
    ldc "WRAP_EXIT"
    invokevirtual java/io/PrintStream.println
    iload_2
    ireturn
~~~

This is an **instruction logic illustration**: exact constant-pool indices, bytecode offsets, and printing syntax depend on `javap`/ASM/JDK. What needs verification is that **the native declaration has no Code**, **the Java wrapper has Code**, and the instruction invokes the correct prefixed native method with descriptor **(II)I**.

## 9. Extending to Instance Methods, Overloads, and Data Types

The example only wraps **static int add(int,int)**. A general-purpose transformer needs to handle many cases:

| Method kind | What changes in the wrapper | Second JNI argument |
| --- | --- | --- |
| static native | Arguments start at local slot 0; invoke with INVOKESTATIC | jclass |
| instance native | Local slot 0 is `this`; arguments start at slot 1; invoke with opcode matching access | jobject |
| void return | Ends with RETURN | Depends on static/instance |
| int/boolean/byte/short/char | IRETURN | Depends on static/instance |
| long | LRETURN, local occupies 2 slots | Depends on static/instance |
| float | FRETURN | Depends on static/instance |
| double | DRETURN, local occupies 2 slots | Depends on static/instance |
| object/array | ARETURN | Depends on static/instance |

The descriptor is the key contract. A method taking `long`, `double`, and `String` has the form:

~~~text
(JDLjava/lang/String;)V

If it is an instance method:
slot 0    -> this
slot 1-2  -> long
slot 3-4  -> double
slot 5    -> String
~~~

You cannot use **ILOAD 0, ILOAD 1** for every method as in the demo. You must compute local slots and opcodes from the JVM descriptor; ASM's **Type** class or another bytecode library helps handle this accurately.

### 9.1. Overloaded Native Methods

~~~java
// Two methods with the same name but different descriptors.
public static native int add(int a, int b);
public static native long add(long a, long b);
~~~

The transformer must match **name + descriptor**. JNI automatic resolution has **short name** and **long name** (appending the encoded parameter descriptor) mechanisms to distinguish overloaded native methods. If both are renamed, each native declaration needs a wrapper with the matching descriptor, and JNI symbol resolution must be tested with actual overloads.

### 9.2. Synchronized Native

The original native method may carry **ACC_SYNCHRONIZED**. When transforming into a Java wrapper and a renamed native method, you must decide **which method holds the monitor** and preserve the exact lock timing/target object. For static methods, the monitor attaches to the `Class` object; for instance methods, the monitor attaches to the receiver.

Mechanically copying all flags to both the wrapper and the native method can cause double locking, increase overhead, or alter the semantics of the measurement point. If you want the monitor to enclose both the advice and the native call, you typically design the wrapper to keep `synchronized`, while the prefixed native method is adjusted intentionally; any flag/ABI changes must be verified. The demo has no `synchronized` methods, so it does not handle this case.

### 9.3. Throwable from Native Code

If C code calls JNI `ThrowNew` or a native call completes with a pending exception, the Java call to the prefixed native method can throw a `Throwable` into the wrapper. To observe exceptional exits, a general wrapper can be structured as:

~~~java
// Source-level pseudocode, not standalone ASM code.
static int add(int a, int b) {
    hookEnter();
    try {
        int value = prefixedNativeAdd(a, b);
        hookSuccess(value);
        return value;
    } catch (Throwable original) {
        hookFailure(original);
        throw original;
    }
}
~~~

You must preserve **Throwable type, identity, and stack/exception semantics**, and ensure the hook itself does not inadvertently alter the original error. When emitting `try`/`catch` with ASM, you need to update the **exception table, StackMapTable, and frame computation**. Do not use a "catch every Throwable and return 0" pattern for observability tools.

### 9.4. Reflection and Metadata

After transformation, reflection can see a native method with the prefixed name and a Java method with the original name. If the original method carried **annotations, generic Signature, parameter annotations, declared exceptions**, or framework-specific metadata, the transformer must decide whether the metadata belongs on the wrapper or the native declaration.

The demo has no annotations, keeping the code short. For public APIs, moving metadata must not be treated as a trivial detail: frameworks relying on annotations may change behavior even when the JNI result remains correct.

## 10. Native Wrapping with Multiple Agents

Multiple `ClassFileTransformer`s can wrap the same native method. Each transformer needs a **distinct prefix**; the order of transformers and how they receive bytes form a **chain of wrappers**.

~~~text
Original:              native foo
Transformer A:         Java wrapper foo
                       native $A_foo

Transformer B:         can add wrapper for $A_foo
                       native $B_$A_foo

JVM native resolution: links through the matching prefix chain
                       to the original JNI implementation of foo
~~~

According to the Javadoc, the prefix mechanism accounts for **wrappers present at intermediate layers** to avoid applying prefixes from transformers that did not actually wrap the native method. Prefixes are considered in the order of the relevant transformers; a meta-agent may need to manage multiple prefixes.

**Typical risks:**

- Agent B rebuilds the class from the original bytes, accidentally wiping out wrapper A.
- Two agents share the same prefix, causing method name collisions.
- Agent B receives bytes that already have a wrapper, but mismatches `ACC_NATIVE`/descriptor.
- A transformer is invoked again and inserts a duplicate wrapper.
- Transformer order differs from expectations due to different `canRetransform`/native Java transformer groups.

Test **A**, **B**, **A+B**, and **B+A** separately, and keep transformation logic idempotent. With multiple agents, **a single "transformed" log line** does not prove that all other wrappers still work.

## 11. How Does JVM TI SetNativeMethodPrefix Differ from Java Instrumentation?

A Java agent typically uses **ClassFileTransformer** and **Instrumentation.setNativeMethodPrefix**. A native JVMTI agent uses **ClassFileLoadHook** to receive class file data and **SetNativeMethodPrefix** when it holds the corresponding capability.

Reference signatures:

~~~c
// JVMTI interface, not a JNI function on JNIEnv*.
jvmtiError SetNativeMethodPrefix(
    jvmtiEnv* env, const char* prefix);

jvmtiError SetNativeMethodPrefixes(
    jvmtiEnv* env,
    jint prefix_count,
    char** prefixes);
~~~

**SetNativeMethodPrefixes** is used in environments that must manage multiple prefixes like a meta-agent. The corresponding native prefix capability in JVMTI is **can_set_native_method_prefix**. Java Instrumentation provides a Java API layer associating a prefix with **a registered `ClassFileTransformer`**; it does not require Java agent authors to manipulate **jvmtiEnv** pointers directly.

**JNI vs. JVMTI:** JNI uses `JNIEnv` for native code to interact with the JVM and implement methods; JVM TI is for tools that observe/control the JVM via events/capabilities. Do not confuse JVMTI's **SetNativeMethodPrefix** with a JNI function that `NativeMath`'s C implementation can call arbitrarily.

## 12. Troubleshooting

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| isNativeMethodPrefixSupported=false | Manifest missing capability or JVM unsupported | Manifest and JDK/JVM |
| setNativeMethodPrefix throws IllegalArgumentException | Transformer not yet registered | `addTransformer` first |
| AGENT_PREFIX_READY present but no AGENT_WRAPPED | Class already loaded or wrong className/filter | Load timing, internal name, loader |
| AGENT_WRAPPED present but no WRAP_ENTER | Wrapper never called or class rejected | Class load errors, callsite/descriptor |
| WRAP_ENTER followed by UnsatisfiedLinkError | Library/symbol/prefix resolution failed | `System.loadLibrary`, JNI symbol, prefix |
| Missing JNI library | Wrong `java.library.path` | `.so`/`.dll`/`.dylib` file, loader errors |
| ClassFormatError | Invalid native flags/Code/duplicate name | `javap` and classfile structure |
| VerifyError | Wrong stack/local/frames/return opcode | ASM verifier, JVM verification |
| NoSuchMethodError | Incorrect prefixed native name or descriptor | Owner/name/descriptor |
| IllegalAccessError | Wrong visibility/module/helper access | ACC flags, defining loader, JPMS |
| WRAP_EXIT does not appear | Native threw an error or JVM crashed | Exception/crash diagnostics |
| Late agent attach has no wrapper | Initial class definition already occurred | Change strategy to caller instrumentation |
| Result changes with two agents | Prefix collision/transformer order | A/B/A+B/B+A tests |
| Native crash | Wrong C ABI/JNI usage | JNI header, `-Xcheck:jni`, native debugger |

### 12.1. Diagnostic Tools

- **javac -h**: JNI header and function prototypes.
- **javap -c -p -s -v**: method descriptors, flags, `Code` attribute.
- **jar tf** and manifest inspection: agent entry point/capability.
- **nm -D libnativeops.so** on Linux: exported native symbols.
- **-Xcheck:jni** on supported JVMs: detects certain JNI usage errors.
- **JVM exception stack trace / hs_err_pid log**: distinguishes class definition failures, `UnsatisfiedLinkError`, and native crashes.
- **Thread dumps/profilers**: overhead, races, deadlocks.

When debugging, note the **className, defining loader, module, original method descriptor, prefix, and native JNI symbol**, and separate the stages: transformer invoked, new `byte[]` returned, class accepted by JVM, wrapper executed, JNI implementation returned expected result.

## 13. Cases Requiring Different Solutions

- **Already-loaded classes**: the approach of adding a method wrapper at initial definition cannot be reapplied as-is via retransform. Instrument callsites or use JVMTI/native tooling depending on requirements.
- **Need to measure inside the C implementation**: a Java wrapper only sees the boundary; you must instrument native code or use a native profiler.
- **Native method called from native code bypassing the Java wrapper**: a Java wrapper cannot observe native-to-native calls.
- **Methods with complex ABI or overloads**: use standard descriptors/JNI headers and a corresponding generator.
- **JDK internal native methods**: depend on classloader/bootstrap, module encapsulation, and special JVM constraints; do not arbitrarily extend the demo to all of `java.base`.
- **Multiple class loaders with the same FQCN**: filter accurately by `Class`/loader; native libraries have classloader-specific lifecycles.
- **Low-latency production**: logging to console on every invocation has high overhead; use safe hooks, minimize allocations, and benchmark after warm-up.

## 14. Essential Test Matrix

| Test | Expected |
| --- | --- |
| Baseline without agent | `RESULT=5`, no WRAP lines |
| Native wrapper with correct prefix | `WRAP_ENTER`, `WRAP_EXIT`, `RESULT=5` |
| Capability disabled | Agent clearly reports unsupported, does not fake success |
| Missing JNI library | `UnsatisfiedLinkError` detected |
| Wrong JNI symbol | Native method resolution fails |
| Method outside filter | Transformer returns `null` |
| Prefixed method already exists | No duplicate/collision created |
| Class loaded before agent | Wrapper not added via retransform |
| Native overload | Descriptor/JNI long-name matched correctly |
| Instance native | `this`/`jobject` and invocation opcode correct |
| long/double arguments | Local slot widths correct |
| Native throws Throwable | Not swallowed, caller sees appropriate type/identity |
| synchronized native | Monitor semantics unchanged |
| Two agents | Prefix and wrapper composition correct |
| Reflection/annotations | API metadata preserved per contract |
| Concurrent calls | Hook has no race/deadlock |
| Different module/classloader | Helper/native visibility valid |
| Classfile verification | JVM accepts class definition |

## 15. Self-Check Questions

1. **Why can't ClassFileTransformer insert advice directly into a native method body?** A native method has no `Code` attribute containing JVM bytecode.
2. **What needs to be created to observe native calls in Java?** A Java wrapper with `Code` keeping the original name/descriptor, and a prefixed native declaration keeping the old descriptor.
3. **Does setNativeMethodPrefix modify the class file by itself?** No; it only enables retrying native method resolution.
4. **What happens if the manifest capability is missing?** Native-prefix support may not be granted; you must check before setting it.
5. **Why is addTransformer called before setNativeMethodPrefix?** The prefix is associated with an already-registered transformer.
6. **Why must this be done at initial class definition?** Renaming the original and adding a wrapper is a method schema change generally disallowed during retransformation of already-loaded classes.
7. **Must the C symbol name Java_demo_NativeMath_add be changed?** Not in the demo: native prefix fallback allows linking to the old implementation.
8. **If native code throws an exception, does WRAP_EXIT run?** Not when the statement is merely placed after the invocation. You need a handler/`finally` if you want to log exceptional exits as well.
9. **How does static JNI differ from instance JNI?** Static receives `jclass`, instance receives `jobject`; the wrapper's local slots/invocation must match accordingly.
10. **If two agents both wrap native methods, can they share a prefix?** They should not; each transformer needs a unique prefix to avoid collisions.
11. **Does the AGENT_WRAPPED log prove the native call succeeded?** Not yet. You must observe the wrapper executing and the actual result/exception.
12. **Does JVMTI SetNativeMethodPrefix use JNIEnv*?** No; it belongs to the JVMTI interface with `jvmtiEnv` and its own capability.

## 16. Checklist for Applying to a Real Agent

- I understand **ACC_NATIVE** and why native methods have no `Code`.
- I know the target **method name + descriptor + flags**, classloader, and module.
- The transformer runs at **initial class definition** rather than trying to add methods to already-loaded classes.
- The manifest has **Can-Set-Native-Method-Prefix: true**, and JVM support is checked.
- `addTransformer` runs before `setNativeMethodPrefix`.
- The prefix is unique, matches the renamed native name, and does not collide.
- The Java wrapper preserves the original API; the native declaration retains its descriptor and `ACC_NATIVE`.
- The wrapper uses the right opcode, local slots, return opcode, and class owner.
- The output `byte[]` is valid, **does not mutate `classfileBuffer`**; out-of-scope classes return `null`.
- JNI automatic resolution/`RegisterNatives` has been tested with the real library.
- Return values, exceptions, `synchronized`, annotations, and caller visibility are preserved properly.
- Do not equate a Java wrapper with instrumenting internal C code.
- Tested baseline/wrapped, JNI errors, multiple agents, class loaders/modules, and concurrency.
- Success is verified by actual runtime behavior, not just transformer logs.

## 17. Official References

- [Java 17 — Instrumentation.setNativeMethodPrefix](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#setNativeMethodPrefix(java.lang.instrument.ClassFileTransformer,java.lang.String)): native wrapper design, fallback for JNI automatic resolution/`RegisterNatives`, multiple prefixes, and exceptions.
- [Java 17 — Instrumentation.isNativeMethodPrefixSupported](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#isNativeMethodPrefixSupported()): optional capability.
- [Java 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, `Premain-Class`, `Can-Set-Native-Method-Prefix`.
- [Java 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transform at class load, immutable input, and return bytes.
- [JNI Specification 17 — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): native library loading, mangled symbol names, `RegisterNatives`, and JNI argument conventions.
- [JVM Specification 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): `ACC_NATIVE`, `Code` attribute, descriptors.
- [JVM TI 17 Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html): `ClassFileLoadHook`, native method prefix functions, and capability.
- [ASM 9.7.1](https://central.sonatype.com/artifact/org.ow2.asm/asm/9.7.1): reader/visitor/writer used to generate method bytecode.

**Key takeaway:** Native methods have no Java `Code` in which to insert instrumentation directly. **Wrap the native method with a Java method containing `Code` at initial class definition**, rename the native method using a **transformer prefix**, register **setNativeMethodPrefix** with the proper capability before class load, preserve descriptor/JNI semantics, and verify that both the wrapper and the native implementation actually work.
