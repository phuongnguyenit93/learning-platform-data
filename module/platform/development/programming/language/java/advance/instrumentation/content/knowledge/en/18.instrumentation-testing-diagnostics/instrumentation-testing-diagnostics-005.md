# Preserving Results, Exceptions, State, and Application Method Invocation Counts

**Context:** Java Advance → instrumentation → **Testing and Diagnostics**.

Instrumentation introduces auxiliary code such as tracing, metrics, audit, or profiling into application execution. It is only trustworthy when **it does not alter the business behavior that the tool is tasked with observing**. Testing that only confirms "the program still runs" is not enough: a transformer can accidentally **call a method twice**, change a return value, **wrap/replace an exception**, write extra data, or lose concurrency context while still passing a simple smoke test.

The goal of this lesson is to verify, on **the same set of inputs and reproducible test conditions**, that the original version (*baseline*) and the instrumented version (*instrumented*) preserve:

1. **Results** — return values, return types, reference identity when part of the contract, and special properties of the data.
2. **Exceptions** — whether one is thrown or not, type, message/cause/suppressed per contract, **the exact Throwable object itself** when the path only has an observation role, and not swallowing/converting error types.
3. **State** — field/state mutation, collections, static state, counters, DB/cache/IO effects, and post-execution invariants.
4. **Application method invocation counts** — each real business call must correspond to **one execution**, not re-invoked by a transformer/wrapper to "inspect the result", and with no duplicate span records caused by inserting a hook twice.

The lesson includes a **complete Java 17+ lab with a Java agent using ASM**, two separate run commands (baseline and instrumented), assertions and expected stdout, along with a test matrix for return/exception/recursion/concurrency/async. Dynamic attach permission is not needed; the agent uses `-javaagent` at JVM startup.

> **Important limitation:** "Preservation" here means **business invariants observable according to test criteria**. A real-world agent still consumes CPU/memory and can affect timing, JIT, stack traces, or scheduling. It does not promise **total system equivalence for all inputs** from just a few test cases. Any changes from telemetry itself are **intentional side effects**, which must be distinguished from altered business side effects.

## 1. Defining Precisely What Must Be Equal

Let:

- `P` be the original program.
- `T(P)` be the program after instrumentation.
- `x` be the provided input.
- `E` be the controlled environment/configuration conditions.
- `B(P,x,E)` be the observed business outcome, **excluding internal telemetry**.

The testing objective is:

```text
B(P, x, E) == B(T(P), x, E)
```

This is a **testing model**, not a requirement that the bytes or execution times of the two programs be identical. It can be decomposed as:

```text
BusinessObservation =
  {
    normalResult,
    thrownOutcome,
    businessStateAfter,
    externallyVisibleEffects,
    applicationMethodInvocationCounts
  }
```

For each synchronous call, one side must either return a normal value or throw an exception; **it cannot simultaneously return normally and throw to the caller**. Both runs must make the same choice according to the defined contract.

### 1.1. Appropriate Comparison Rules for Each Type

| Target to compare | What counts as "unchanged"? | Easily missed bugs |
| --- | --- | --- |
| `int`, `long`, `boolean`, and other primitives | Same value | Probe accidentally alters or drops an operand on the stack |
| `float`, `double` | Per contract criteria; consider `NaN`, `-0.0`, bit patterns when needed | `==` does not detect all bit-level differences |
| `String` / immutable DTO | Equivalent content; identity if API guarantees it | Wrapper creates a new string and caller relies on `==` |
| Reference return | Keeps **the same object reference** when contract requires, no copy | Creates a new list/object instead of returning the original |
| `void` | Unchanged business logic and side effects | "No return" does not mean no bugs |
| Exceptions | Type, message, cause/suppressed, identity per contract | `catch(Exception e) { throw new RuntimeException(e); }` |
| State | Fields, collections, object graph/static state, versioning | Hook adds a mutation or skips a mutation |
| External effect | Same DB writes/HTTP calls/messages/files per contract | Agent uses a "retry" that executes business logic twice |
| Application count | Same number of times **the method body ran** | Hook measures by calling the method again |
| Measurement event | Event count must match the observation policy, **not** business calls | One entry but two exit events, duplicate spans |

Not every system requires comparing **every byte** of serialized data or **every line of a stack trace**. Define **acceptance criteria before measuring**, avoiding deciding only after a run to ignore inconvenient differences.

### 1.2. Three Different Kinds of "Call Counts"

One invocation of `Service.process` can lead to multiple calls to helper methods; each instrumented call also runs `Probe.onEntry`. Therefore, separate:

```text
N_app(m)   = number of times business method m's body executes
N_probe(m) = number of times observation hook for m is triggered
N_span(m)  = number of logical spans/events recorded for m
```

With **entry-only instrumentation** in the lab:

```text
N_app(m) baseline == N_app(m) instrumented
N_probe(m) baseline == 0
N_probe(m) instrumented == N_app(m) instrumented
```

With full tracing, you usually want **one logical span per invocation**, with **one start and one terminal outcome** (normal/error). But do not automatically equate "two START/END events" with "two business invocations".

## 2. Why Does Instrumentation Easily Break Invariants?

### 2.1. Re-invoking a Method to Measure the Result

A dangerous wrapper:

```java
// Anti-pattern, not complete source.
Object first = target.call();
logger.info("result=" + target.call()); // SECOND CALL!
return first;
```

If `target.call()` transfers money, writes to a DB, sends an email, or increments a counter, it has run twice. The logger must not **re-invoke the business method itself** just to get a value to display. Store **the result of one invocation**, then only read the reference without calling the target again.

A reasonable version at the Java wrapper level:

```java
// Fragment: target and types are declared in another program.
Object result = target.call();
try {
    safeRecord(result);
} catch (RuntimeException telemetryFailure) {
    // Only per TELEMETRY fail-open policy.
}
return result;
```

However, this approach also needs to check whether `safeRecord` mutates `result`/the object graph; a logger using `result.toString()` can execute application code, trigger side effects, or throw an exception. "Logging does not change behavior" is only true if the logger/probe is designed to be **bounded**.

### 2.2. Wrapping or Swallowing Exceptions

Another anti-pattern:

```java
// Anti-pattern: changes the business throwable's type and identity.
try {
    return service.doWork();
} catch (Exception original) {
    throw new IllegalStateException("instrumentation failed", original);
}
```

This changes the exception type/message/identity on the path the caller sees; code catching `IOException` or `IllegalArgumentException` may behave differently.

When errors need to be observed, you must usually **record without altering the throwable** and **rethrow the exact same object**. In the synchronous Java model, use `catch` and then `throw original;` with the proper checked type, or use `finally` only for cleanup. But **do not** place a telemetry call that can throw inside `finally` and assume by default that the original throwable is preserved: an error from `finally` can **overwrite the outcome**.

### 2.3. Hook Running Twice on the Same Method

Example:

```text
Load time:        instrument BankAccount.deposit the 1st time
Retransform time: transformer inserts the same hook the 2nd time
Result:           one business invocation -> two Probe.onEntry calls
```

This is a **situation that can occur in a pipeline lacking idempotency**, not a default that every retransform always duplicates hooks. `ClassFileTransformer` has different rules between transformers that do/do not support retransformation. Always check the *stage*, output bytes, and whether the hook code is already present. Avoid using random constant pool indices or byte offsets as markers.

### 2.4. Probe Altering State or Lock Ordering

An instrumentation helper that accidentally writes to a `ThreadLocal` without cleanup, alters the caller's MDC, acquires locks in the wrong order, calls an application service during logging, or triggers a recursive callback can:

- Dirty the context of the next request on a thread pool.
- Cause deadlocks or different lock contention.
- Cause extra network calls/DB writes.
- Alter static caches, transaction scopes, or permission contexts.
- Create recursion/`StackOverflowError` in the tracer.

**Design principle:** instrumentation must be logically isolated from the application, resource-bounded, never re-invoke the target method, and never modify business input/output data.

## 3. `ClassFileTransformer` Contract Related to Correctness

JDK 17 defines:

```java
// API fragment, not a standalone program.
byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
        throws IllegalClassFormatException;
```

There is also a **six-parameter overload with `Module`** on JDK 9+; overriding the five-parameter version remains valid. For a transformer:

- **Do not modify `classfileBuffer` directly** as provided by the JVM.
- When no transformation is needed, **`return null`**.
- When transformation is needed, return a **new `byte[]` array** containing a valid class file.
- Multiple transformers can be **chained**; the previous output is the next input.
- The JVM may still continue loading with unchanged bytes if a transformer throws an exception; that is **not a reliable fail-fast mechanism** to guarantee the agent has instrumented. You must verify actual effectiveness and report errors clearly.
- When redefining/retransforming, the output must satisfy **schema restrictions**, stack frames, the bytecode verifier, and all VM conditions.
- `className` uses an **internal name** like `demo/BankAccount`, not a Java source name like `demo.BankAccount`.

**Testing note:** for each method to be measured, check the class loader, method descriptor, and callback count. An overloaded method name alone is not enough to uniquely identify a method.

## 4. Designing an Experiment Comparing Two Independent JVMs

We will keep the **application source** unchanged and run **two Java processes**:

```text
Run A (baseline)
  java -cp app-and-agent.jar demo.App
       │
       ▼
  Original BankAccount methods
       │
       ▼
  Assert result / exception / state / application counts
  Probe counts = 0

Run B (instrumented)
  java -DexpectTrace=true -javaagent:app-and-agent.jar \
       -cp app-and-agent.jar demo.App
       │
       ▼
  Agent premain -> ClassFileTransformer -> ASM inserts onEntry
       │
       ▼
  Same BankAccount business methods
       │
       ▼
  Assert result / exception / state / application counts
  Probe counts = actual business counts
```

Two separate processes prevent static counters, JIT state, class loading, and side effects from a previous run from interfering with the next run. Input data is hardcoded identically, without using wall-clock time/randomness/external databases to determine results.

**Key point:** the baseline and instrumented programs print identical **BUSINESS, EXCEPTIONS, IDENTITY, STATE, CALLS** lines. Only the **PROBE** line differs **intentionally**. If any business invariant diverges, do **not** treat the test as passing just because `RESULT=PASS` is printed from other code.

### 4.1. Lab Test Cases

| Method | Input/scenario | Signals to preserve | Count |
| --- | --- | --- | --- |
| `deposit(int)` | `20` and `-1` | Returns 120; one argument error; execution count = 2 | 2 |
| `withdraw(int)` | `30` and `200` | Returns 90; one insufficient funds error; count = 2 | 2 |
| `raise(RuntimeException)` | Pass a specific `marker` | Rethrows **the same marker object**, unchanged suppressed | 1 |
| `recursive(int)` | `3` | Returns 6; called for `3,2,1,0`, exact count 4 | 4 |
| `tick()` | Two threads, 100 times each | State increments to exactly 200; synchronized via `synchronized` | 200 |

These are **method body execution counts**, **not** the total number of Java method calls across the entire application (getter calls, `Future.get`, `System.out.println`, etc. are also methods but fall outside the instrumentation scope).

## 5. Java 17+ Lab: Source Code, Agent, Build, and Assertions

### 5.1. Project Structure

```text
transparency-lab/
├── pom.xml
└── src/main/java/demo/
    ├── BankAccount.java
    ├── Probe.java
    ├── TraceAgent.java
    └── App.java
```

Requires **JDK 17+**, Maven 3.x, and access to download Maven dependencies (or an existing local repository/cache). Maven will produce **one shaded JAR containing the application code, agent, and ASM**. We use the same artifact in both runs; the only difference is the presence/absence of `-javaagent`.

### 5.2. `pom.xml` — Maven 17 and ASM

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>transparency-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.7.1</version>
    </dependency>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm-commons</artifactId>
      <version>9.7.1</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration>
          <release>17</release>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.6.0</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <manifestEntries>
                    <Premain-Class>demo.TraceAgent</Premain-Class>
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
```

`maven-shade-plugin` packages both `asm` and `asm-commons` into the JAR so the JVM can load the transformer in `premain`. If you use a regular JAR containing only project classes without ASM dependencies, agent startup can throw `NoClassDefFoundError: org/objectweb/asm/...` before the application starts. The `Premain-Class` manifest entry is required when using `-javaagent`. This lab does not need `Can-Retransform-Classes` because the transformer registers at **load time**, with no retransform calls.

### 5.3. `src/main/java/demo/BankAccount.java` — Stateful Business Logic

```java
package demo;

public final class BankAccount {
    private int balance;
    private int depositCalls;
    private int withdrawCalls;
    private int raiseCalls;
    private int recursiveCalls;
    private int ticks;

    public BankAccount(int initialBalance) {
        this.balance = initialBalance;
    }

    public int deposit(int amount) {
        depositCalls++;
        if (amount <= 0) {
            throw new IllegalArgumentException(
                    "amount must be positive");
        }
        balance += amount;
        return balance;
    }

    public int withdraw(int amount) {
        withdrawCalls++;
        if (amount <= 0) {
            throw new IllegalArgumentException(
                    "amount must be positive");
        }
        if (amount > balance) {
            throw new IllegalStateException(
                    "insufficient funds");
        }
        balance -= amount;
        return balance;
    }

    public void raise(RuntimeException marker) {
        raiseCalls++;
        throw marker;
    }

    public int recursive(int n) {
        recursiveCalls++;
        if (n <= 0) {
            return 0;
        }
        return n + recursive(n - 1);
    }

    public synchronized void tick() {
        ticks++;
    }

    public int balance() {
        return balance;
    }

    public int depositCalls() {
        return depositCalls;
    }

    public int withdrawCalls() {
        return withdrawCalls;
    }

    public int raiseCalls() {
        return raiseCalls;
    }

    public int recursiveCalls() {
        return recursiveCalls;
    }

    public synchronized int ticks() {
        return ticks;
    }
}
```

This is **the application class with no instrumentation code**. In the test, the counters `depositCalls`/`withdrawCalls`/`raiseCalls`/`recursiveCalls` are part of **the lab's business state**, incremented inside each method and used as the "source of truth" for how many times the method body ran.

- `deposit(20)` on a balance of 100 returns 120.
- `withdraw(30)` returns 90.
- `deposit(-1)` throws `IllegalArgumentException` **after recording one call**, without changing balance.
- `withdraw(200)` throws `IllegalStateException`, without changing balance.
- `raise(marker)` throws **the exact object** passed in, without creating a wrapper.
- `recursive(3)` runs four times (3,2,1,0) and returns `3+2+1+0=6`.
- `tick` is `synchronized`, so two threads can increment it exactly 200 times if each thread calls it 100 times and we wait for them to finish.

The length/structure of the class matters less than having **normal return, exception, object identity, state, recursion, and concurrency** in the same scenario.

### 5.4. `src/main/java/demo/Probe.java` — Agent's Separate State

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public final class Probe {
    private static final AtomicInteger DEPOSIT = new AtomicInteger();
    private static final AtomicInteger WITHDRAW = new AtomicInteger();
    private static final AtomicInteger RAISE = new AtomicInteger();
    private static final AtomicInteger RECURSIVE = new AtomicInteger();
    private static final AtomicInteger TICK = new AtomicInteger();

    private Probe() {}

    public static void onEntry(String name) {
        switch (name) {
            case "deposit" -> DEPOSIT.incrementAndGet();
            case "withdraw" -> WITHDRAW.incrementAndGet();
            case "raise" -> RAISE.incrementAndGet();
            case "recursive" -> RECURSIVE.incrementAndGet();
            case "tick" -> TICK.incrementAndGet();
            default -> {
                // Out of sample scope: ignore.
            }
        }
    }

    public static int count(String name) {
        return switch (name) {
            case "deposit" -> DEPOSIT.get();
            case "withdraw" -> WITHDRAW.get();
            case "raise" -> RAISE.get();
            case "recursive" -> RECURSIVE.get();
            case "tick" -> TICK.get();
            default -> 0;
        };
    }
}
```

`Probe` **does not call back into any method of `BankAccount`**. It only increments independent `AtomicInteger`s; thus logging does not directly alter `balance`, `ticks`, or business counters. `AtomicInteger` is important when multiple threads call `tick` concurrently: using a plain `int++` in the probe could lose updates and report wrong counts.

In real production systems, even `AtomicInteger.incrementAndGet()` has cost and can theoretically be affected by severe system errors such as `OutOfMemoryError` when a helper class first loads. **No Java telemetry helper has strictly zero impact**. Evaluate fail-open behavior, early initialization, bounded overhead, and excluding helper classes from instrumentation.

### 5.5. `src/main/java/demo/TraceAgent.java` — ASM Transformer Inserting Entry Hook Only

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.commons.AdviceAdapter;

public final class TraceAgent {
    private TraceAgent() {}

    public static void premain(
            String arguments, Instrumentation instrumentation) {
        instrumentation.addTransformer(new AccountTransformer());
    }

    private static final class AccountTransformer
            implements ClassFileTransformer {

        private static boolean watched(
                String name, String descriptor) {
            return switch (name) {
                case "deposit", "withdraw", "recursive" ->
                        "(I)I".equals(descriptor);
                case "raise" ->
                        "(Ljava/lang/RuntimeException;)V"
                                .equals(descriptor);
                case "tick" -> "()V".equals(descriptor);
                default -> false;
            };
        }

        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer)
                throws IllegalClassFormatException {

            if (!"demo/BankAccount".equals(className)) {
                return null;
            }

            try {
                ClassReader reader = new ClassReader(classfileBuffer);
                ClassWriter writer = new ClassWriter(
                        reader, ClassWriter.COMPUTE_MAXS);

                ClassVisitor visitor =
                        new ClassVisitor(Opcodes.ASM9, writer) {
                    @Override
                    public MethodVisitor visitMethod(
                            int access,
                            String name,
                            String descriptor,
                            String signature,
                            String[] exceptions) {

                        MethodVisitor original = super.visitMethod(
                                access, name, descriptor,
                                signature, exceptions);

                        if (original == null
                                || (access & (Opcodes.ACC_ABSTRACT
                                    | Opcodes.ACC_NATIVE)) != 0
                                || !watched(name, descriptor)) {
                            return original;
                        }

                        return new AdviceAdapter(
                                Opcodes.ASM9, original, access,
                                name, descriptor) {
                            @Override
                            protected void onMethodEnter() {
                                visitLdcInsn(name);
                                visitMethodInsn(
                                        Opcodes.INVOKESTATIC,
                                        "demo/Probe",
                                        "onEntry",
                                        "(Ljava/lang/String;)V",
                                        false);
                            }
                        };
                    }
                };

                reader.accept(visitor, 0);
                return writer.toByteArray();
            } catch (RuntimeException failure) {
                IllegalClassFormatException error =
                        new IllegalClassFormatException(
                            "Cannot transform demo/BankAccount");
                error.initCause(failure);
                throw error;
            }
        }
    }
}
```

**Bytecode path analysis:**

1. The transformer selects only **`demo/BankAccount`** at load time, leaving JDK classes, `Probe`, `TraceAgent`, or logger classes untouched. Filtering is based on the internal name with `/`.
2. `watched` selects **exact name + descriptor** of the five business methods. Constructors, getters, and other overloads are not instrumented.
3. `ClassReader` reads the input without **writing into `classfileBuffer`**. `ClassWriter` produces a **new byte array**.
4. `AdviceAdapter.onMethodEnter` inserts two instructions at the start of each selected method: pushing the method name via `LDC` and calling `Probe.onEntry(name)` exactly once when the method actually begins executing.
5. The hook does not read arguments, modify local variables, read/write return operands, or **catch/wrap exceptions**. The original business instruction flow is preserved.
6. `ClassWriter.COMPUTE_MAXS` recomputes max operand stack/local requirements appropriate for inserting `LDC` followed by `INVOKESTATIC`. Because the example does not add branches/handlers or alter control flow, new stack-map frames do not need to be generated manually. **Do not generalize** this to all instrumentation styles; complex transformations require dedicated frame computation and verifier design.
7. In Java 17, overriding the **five-parameter** `transform` method is forwarded to by the interface's default six-parameter overload, per Javadoc.
8. If transformation fails, the JVM may still continue loading the class unchanged (per the transformer contract). Therefore, **instrumented tests must assert probe counts**; having `-javaagent` on the command line must not be treated as proof that new bytecode was actually applied.

**Why does the lab only insert an entry hook?** This is the minimal level sufficient to measure method body execution counts and verify preservation for both **normal returns and thrown exceptions**. It intentionally avoids an incompletely handled "exit hook" implementation so as not to conflate an explicit `ATHROW` case with all errors that can exit a method.

### 5.6. `src/main/java/demo/App.java` — Differential Assertions

```java
package demo;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class App {
    private App() {}

    @FunctionalInterface
    private interface Attempt {
        void run();
    }

    private static Throwable capture(Attempt action) {
        try {
            action.run();
        } catch (Throwable thrown) {
            return thrown;
        }
        throw new AssertionError("Expected an exception");
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError("Invariant failed: " + label);
        }
    }

    public static void main(String[] args) throws Exception {
        BankAccount account = new BankAccount(100);

        int deposited = account.deposit(20);
        int withdrawn = account.withdraw(30);

        Throwable invalid = capture(() -> {
            account.deposit(-1);
        });
        Throwable insufficient = capture(() -> {
            account.withdraw(200);
        });

        RuntimeException marker =
                new IllegalArgumentException("marker");
        Throwable caughtMarker = capture(() -> {
            account.raise(marker);
        });

        int recursive = account.recursive(3);

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Runnable job = () -> {
                for (int i = 0; i < 100; i++) {
                    account.tick();
                }
            };

            Future<?> first = executor.submit(job);
            Future<?> second = executor.submit(job);
            first.get();
            second.get();
        } finally {
            executor.shutdownNow();
        }

        check(deposited == 120, "deposit result");
        check(withdrawn == 90, "withdraw result");
        check(recursive == 6, "recursive result");
        check(account.balance() == 90, "balance");
        check(account.ticks() == 200, "ticks");

        check(invalid.getClass() == IllegalArgumentException.class
                && "amount must be positive".equals(
                        invalid.getMessage()),
                "invalid exception");
        check(insufficient.getClass() == IllegalStateException.class
                && "insufficient funds".equals(
                        insufficient.getMessage()),
                "insufficient exception");
        check(caughtMarker == marker, "Throwable identity");
        check(caughtMarker.getSuppressed().length == 0,
                "no suppressed errors");

        check(account.depositCalls() == 2, "deposit calls");
        check(account.withdrawCalls() == 2, "withdraw calls");
        check(account.raiseCalls() == 1, "raise calls");
        check(account.recursiveCalls() == 4, "recursive calls");

        boolean expectTrace = Boolean.getBoolean("expectTrace");
        int scale = expectTrace ? 1 : 0;
        check(Probe.count("deposit") == 2 * scale,
                "probe deposit");
        check(Probe.count("withdraw") == 2 * scale,
                "probe withdraw");
        check(Probe.count("raise") == scale, "probe raise");
        check(Probe.count("recursive") == 4 * scale,
                "probe recursive");
        check(Probe.count("tick") == 200 * scale,
                "probe tick");

        System.out.println("BUSINESS=deposit:" + deposited
                + ",withdraw:" + withdrawn
                + ",recursive:" + recursive
                + ",balance:" + account.balance());
        System.out.println("EXCEPTIONS="
                + invalid.getClass().getSimpleName() + ":"
                + invalid.getMessage() + "|"
                + insufficient.getClass().getSimpleName() + ":"
                + insufficient.getMessage());
        System.out.println("IDENTITY="
                + (caughtMarker == marker)
                + ",suppressed="
                + caughtMarker.getSuppressed().length);
        System.out.println("STATE=balance:" + account.balance()
                + ",ticks:" + account.ticks());
        System.out.println("CALLS=deposit:"
                + account.depositCalls()
                + ",withdraw:" + account.withdrawCalls()
                + ",raise:" + account.raiseCalls()
                + ",recursive:" + account.recursiveCalls()
                + ",tick:" + account.ticks());
        System.out.println("PROBE=deposit:"
                + Probe.count("deposit")
                + ",withdraw:" + Probe.count("withdraw")
                + ",raise:" + Probe.count("raise")
                + ",recursive:" + Probe.count("recursive")
                + ",tick:" + Probe.count("tick"));
        System.out.println("RESULT=PASS");
    }
}
```

The program **does not use JUnit**, but every invariant is asserted via `check(...)`. If a value is wrong, it throws `AssertionError`, the JVM returns a non-zero exit code, and **does not print `RESULT=PASS`**. This is a way to build a standalone experiment without test dependencies. In a real project, move assertions into systematic unit/integration tests.

`Boolean.getBoolean("expectTrace")` reads a Java system property. **Baseline** defaults to `false`, so probe counts must be 0. **Agent run** uses `-DexpectTrace=true`, requiring probe counts to match business invocation counts. If the transformer fails to install the hook, the agent run test will **fail** instead of falsely reporting successful instrumentation.

Do not make the test **depend on the ordering of the two threads**: `Future.get()` waits for both to finish, and `tick()` is `synchronized`. The printed numbers are deterministic, even under different schedulers.

## 6. Running Both Versions and Reading Stdout

### 6.1. Build Once

In the `transparency-lab` directory:

```bash
mvn -q -DskipTests package
```

Upon success, the standard artifact of this Maven configuration is:

```text
target/transparency-lab-1.0.0.jar
```

This JAR contains both the application source and `TraceAgent`, ASM runtime dependencies, and the `Premain-Class: demo.TraceAgent` manifest entry. Requires Maven 3.x, JDK 17+, and a repository containing `asm`/`asm-commons` 9.7.1 and compiler/shade plugins. The lesson does not assume the build command was executed separately inside the document; the stdout below is the **expected output from the presented source**.

### 6.2. Baseline (No Agent)

```bash
java -cp target/transparency-lab-1.0.0.jar demo.App
```

Application stdout:

```text
BUSINESS=deposit:120,withdraw:90,recursive:6,balance:90
EXCEPTIONS=IllegalArgumentException:amount must be positive|IllegalStateException:insufficient funds
IDENTITY=true,suppressed=0
STATE=balance:90,ticks:200
CALLS=deposit:2,withdraw:2,raise:1,recursive:4,tick:200
PROBE=deposit:0,withdraw:0,raise:0,recursive:0,tick:0
RESULT=PASS
```

### 6.3. Instrumented (Startup Agent)

```bash
java -DexpectTrace=true \
    -javaagent:target/transparency-lab-1.0.0.jar \
    -cp target/transparency-lab-1.0.0.jar demo.App
```

On Windows PowerShell, write it on a single line:

```powershell
java -DexpectTrace=true -javaagent:target/transparency-lab-1.0.0.jar -cp target/transparency-lab-1.0.0.jar demo.App
```

Expected application stdout:

```text
BUSINESS=deposit:120,withdraw:90,recursive:6,balance:90
EXCEPTIONS=IllegalArgumentException:amount must be positive|IllegalStateException:insufficient funds
IDENTITY=true,suppressed=0
STATE=balance:90,ticks:200
CALLS=deposit:2,withdraw:2,raise:1,recursive:4,tick:200
PROBE=deposit:2,withdraw:2,raise:1,recursive:4,tick:200
RESULT=PASS
```

**Reading the results:**

- `BUSINESS` is identical: return values are correct.
- `EXCEPTIONS` is identical: invalid amount and insufficient funds errors did not change type/message.
- `IDENTITY=true` in **both runs**: `raise` actually rethrew the **marker object passed within the same process**; it is not two JVMs sharing the same object reference.
- `STATE` is identical: balance=90, total ticks=200.
- `CALLS` is identical: no second **business invocation** occurred due to instrumentation.
- `PROBE` is intentionally **different**: baseline has no hooks; the agent has exactly one `onEntry` per invocation, including invalid/exceptional paths and recursion.
- `RESULT=PASS` appears only when all checks finish.

This is a simple experiment, yet much higher-signal than just seeing an "agent loaded" log line.

### 6.4. Verifying Bytecode and the Verifier

You can add verification on the target JVM:

```bash
java -Xverify:all -DexpectTrace=true \
    -javaagent:target/transparency-lab-1.0.0.jar \
    -cp target/transparency-lab-1.0.0.jar demo.App
```

`-Xverify:all` instructs the VM to perform stricter class bytecode verification; if a transformed class has broken stack frames/operand stacks, the test can fail early. **Passing the verifier does not guarantee semantic equivalence**; you must still run the assertions above.

If you want to dump the **actual output class-file bytes** from the transformer to inspect with `javap -c -v`, add a dedicated snapshot mechanism in the test environment. Running `javap` directly on `target/transparency-lab-1.0.0.jar` **only sees the class file on disk**, not the instructions the agent inserted at runtime. Do not use the JAR's bytecode hash as proof that instrumentation did or did not run.

## 7. Why Is This Differential Testing Approach Valuable?

We intentionally avoid writing two versions of business code to compare: **only one `BankAccount`** is compiled, and the same class bytes are launched via two command lines. The Java agent transforms the class at load time in run B; therefore any business difference can be attributed to instrumentation or uncontrolled environmental variables.

The tests verify **both sides**:

1. **Business correctness baseline:** receives the right values, exceptions, and state per contract.
2. **Non-regression under instrumentation:** all invariants are repeated with the agent active.
3. **Effectiveness of instrumentation:** probe counts are exact, avoiding a false PASS where "the agent didn't run so it didn't break the app".

Several properties were specifically designed in:

- At least two errors are thrown **from inside methods**.
- One `raise` error checks **Throwable identity** to catch wrappers creating new exceptions.
- There is a **recursive call graph**: instrumentation must insert an entry for **each invocation**, not one entry for the whole recursion tree.
- There is a **multi-threaded synchronized method**: avoiding concluding "instrumented correctly" just from sequential test results.
- There are **application method counters** independent of `Probe` counters: making it possible to detect a tool that miscounts or calls a business method extra times.

**Being honest:** the lab uses small inputs and in-memory state; it does not yet prove preservation of external DB/HTTP effects or correctness across all exception classes, JIT optimizations, JVM vendors, and production loads. That is why subsequent testing layers are needed.

## 8. Preserving Return Values Across All Opcodes

A transformer intercepting at method exit must understand that the JVM has multiple return instructions:

| Source return type | Common opcode | Stack before return |
| --- | --- | --- |
| `void` | `RETURN` | No return value |
| `int`, `boolean`, `byte`, `char`, `short` | `IRETURN` | One category-1 value |
| `float` | `FRETURN` | One category-1 value |
| `long` | `LRETURN` | One category-2 value |
| `double` | `DRETURN` | One category-2 value |
| Object/array reference | `ARETURN` | One reference |
| Throwing an exception | `ATHROW` | One reference to throwable |

If you want to log a return value, the hook **must not consume the operand and forget to put it back**. With ASM, `dup` applies to category-1; `dup2` suits category-2. Alternatively, use `AdviceAdapter.newLocal(Type)` and save/load with the right type, combined with recomputing stack frames/locals when needed. Do not use `DUP` for `long`/`double`.

A pseudocode idea:

```text
Method returns int:
   [ ... original computation ... ]
   push(result)
   DUP                 // keep a copy for the original IRETURN
   INVOKESTATIC Probe.recordInt(I)V
   IRETURN

Original return value remains on the operand stack.
```

This is only a **stack illustration**, not a complete method with full frames. Probe `recordInt` must not interfere with the result and is responsible for handling telemetry errors. If it throws, the original return will be replaced by an error. Therefore, **keeping the value on the stack is necessary but not sufficient** to preserve semantics.

### 8.1. Especially with Object References and Mutable Results

If a method returns `List<Order>`, logging via `list.toString()` can execute application-defined code, mutate state, or throw. If the instrumenter creates a copy of the list, the caller may no longer hold the same reference and subsequent updates will not go into the original object.

Tests should check:

- `assertSame(referenceBefore, returnedReference)` when identity is part of the contract.
- Values and element order when needed.
- No mutation or iteration side effects causing `ConcurrentModificationException`.
- `null` remains `null`; the hook does not "helpfully" replace it with an empty object.
- For `double`, check `Double.doubleToRawLongBits(...)` when `-0.0`/NaN payloads must be preserved, or use a domain-specific comparator if the API only promises numerical equivalence.

**Do not compare `Double.NaN == Double.NaN`** to conclude two outputs differ: `NaN != NaN` under IEEE-754, while the application may treat both as the same valid result kind.

## 9. Preserving Exceptions, Both Explicit and Implicit Errors

### 9.1. "Same Exception Type" Is Not Necessarily Enough

The same `IllegalArgumentException` with a different `message`, `cause`, `suppressed`, or identity can cause the caller to handle it differently:

```java
// Anti-pattern: alters the identity and stack trace of the original error.
catch (RuntimeException original) {
    throw new RuntimeException(original.getMessage(), original);
}
```

If the caller relies on `e == marker`, the snippet above breaks the contract. When only observing, **do not create a new exception to replace the business outcome**. Check `Throwable.getClass()`, `getMessage()`, `getCause()`, `getSuppressed()`, and identity when meaningful.

### 9.2. Explicit `ATHROW` Errors Differ from Implicit Errors from Callees

With ASM `AdviceAdapter.onMethodExit(int opcode)`, the callback is invoked right before **return/throw instructions** seen by the visitor, including explicit `ATHROW`. However, a method can also **terminate abnormally because an instruction/callee throws an error where the current bytecode has no explicit `ATHROW` instruction** at that site.

Example:

```java
// Fragment: externalService and Request exist in the real program.
public void send(Request request) {
    externalService.send(request); // callee may throw!
}
```

If the callee throws, the program **does not execute `RETURN` at the end of the method** and does not necessarily pass through an explicit `ATHROW` of `send`. Using only `onMethodExit(ATHROW)` to count "all exception exits" is **incomplete**.

To emit a complete terminal event, you need a catch-all handler wrapping the appropriate method scope, record the error, and **rethrow the exact same Throwable**, while avoiding double-counting already-observed `ATHROW`s:

```text
method body (proper try scope)
  normal return -> record exactly one normal exit; return original value
  explicit/implicit throw -> catch-all handler:
      record exactly one error exit
      throw the SAME throwable
```

This is **control-flow pseudocode**, not complete ASM code. For constructors, special care is required for the `uninitialized this` state before `super(...)`/`this(...)`; do not blindly apply a catch-all that the verifier rejects. Exception tables, handler ordering, stack-map frames, and original try/catch/finally semantics must remain valid.

### 9.3. Telemetry Failure Can Mask a Business Exception

Example:

```java
// Anti-pattern: if logError throws, the caller does not see original.
try {
    return operation();
} catch (Throwable original) {
    logger.logError(original); // may throw
    throw original;
}
```

A fail-open model can try catching **telemetry errors** separately, ensuring it does not turn into a replacement for `original`. However, "catching all `Throwable`" also has limits: for `ThreadDeath`, `OutOfMemoryError`, `StackOverflowError`, or JVM termination, there is no absolute safety guarantee. Keep the telemetry path small, avoid expensive allocations/locks, and have queues/budgets/sampling and clear policies for critical errors.

**Distinguish** business exceptions from instrumentation exceptions in tests; if the tracer fails while the business logic returned correctly, telemetry status may be degraded rather than silently claiming full measurement.

## 10. Preserving Post-Execution State

State to compare is not just an `int balance`. For real applications, expand to include:

| State/effect | How to verify | Instrumentation risk |
| --- | --- | --- |
| Object fields | Snapshot business DTO/state or reasonable deep diff | Probe mutates object/collection |
| Static caches | Same keys/values/version counters | Hook initializes/writes cache differently |
| ThreadLocal/MDC | Before-after on same thread and worker thread pool | Missing cleanup in `finally` |
| Transaction state | Commit/rollback and persistence counts | Probe re-invokes DAO or causes wrong rollback |
| External requests | Stub/mock server counting HTTP/gRPC calls | Double invocation, out-of-policy retries |
| Messages | In-memory broker/test topic counting publishes | Duplicate send or altered correlation ID |
| Files | Compare bytes/metadata and meaningful write counts | Logging accidentally writes to business path |
| Locks/monitor ownership | Concurrency, liveness, lock ordering tests | Hook holds another lock causing deadlock |
| Async task graph | Count submitted/completed tasks | Spawns extra tasks or loses context |
| Metrics/tracing | Verify separately from app business state | Telemetry drops/duplicates events |

Merely taking `toString()` or JSON serialization of an object is not guaranteed to be side-effect-free: custom getters, lazy-loading ORM, serializer hooks, and iteration can mutate state. Use test doubles/recorders **independent of instrumentation** to capture external effects.

### 10.1. Snapshotting Business State Properly

For objects with mutable fields, define a projection containing only the **business data** to preserve:

```text
Before:
   account.id, balance, version, pendingWrites
After:
   account.id, balance, version, pendingWrites

Telemetry:
   span count, timing, log buffer -> verify separately
```

If a logger/tracer adds a field to an app object just to hold a span id, that can be a **schema mutation** disallowed under redefinition/retransformation. Use scoped context or an appropriate side table instead, while still controlling memory leaks and class loader lifetimes.

### 10.2. Especially with Transactions and Retries

A **pre-designed** business retry mechanism can be valid, but instrumentation **must not add retries on its own** just to "re-fetch a result" or upon seeing a telemetry failure. When testing, distinguish:

- **Request attempts** at the client.
- **Invocation count** of the instrumented method.
- **DB transaction count**.
- **Committed side effects**.

A request may invoke a business method twice due to a valid retry policy; do not blindly enforce "exactly one invocation per request" if the contract allows retries. Tests should use expected counts based on the scenario, not guesswork.

## 11. Invocation Counts: Recursion, Concurrency, Overloads, and Dispatch

### 11.1. Recursion

For `recursive(3)`:

```text
recursive(3)
  recursive(2)
    recursive(1)
      recursive(0)
```

This is **four method invocations**, not one. If the business counter is 4 while the probe reports 1, the hook may only wrap the outermost call. If the probe reports 8, the transformer may have inserted the hook twice or another wrapper layer is also measuring. Clarify whether a metric is counting **method entry**, **root request**, or **logical transaction** before reporting a bug.

### 11.2. Concurrency

Two threads calling `tick` concurrently have no fixed linear order under the JVM scheduler. What must be preserved is:

```text
100 calls from Thread A + 100 calls from Thread B
= 200 business method entries
= 200 probe entries when agent is enabled
= 200 state increments in the synchronized lab
```

Do not write tests asserting log order `A, B, A, B...` unless synchronization forces that order. Use `CountDownLatch`/`Future.get` to wait for completion and then compare **counts/invariants**, and give tests a timeout in CI to detect deadlocks.

### 11.3. Overloads, Bridge, and Synthetic Methods

Methods with the same name but different descriptors are **different methods**:

```text
save(I)V
save(Ljava/lang/String;)V
```

If a tracker relies only on `methodName`, it can mix counts of two overloads. With generic overrides, the compiler can generate **bridge methods**; a source call can pass through a bridge and then the implementation method, so **two bytecode method entries** can correspond to **one logical operation**.

Rules:

- Identify bytecode methods by **owner internal class + name + descriptor**, adding defining loader identity when needed.
- Define a policy on whether to instrument `ACC_BRIDGE`/`ACC_SYNTHETIC`.
- Count **logical business operations** at the appropriate service boundary, rather than mechanically summing every bytecode helper call.
- Include tests for overloads/default methods/inheritance and dynamic dispatch.

### 11.4. Reentrant Logging and the Hook Instrumenting Itself

If `Probe.onEntry` is also selected by the transformer, this can happen:

```text
BankAccount.deposit
  -> Probe.onEntry
      -> Probe.onEntry
          -> Probe.onEntry
             ... StackOverflowError
```

A proper transformer must avoid instrumenting its own helper packages, logging framework hot paths, unnecessary bootstrap classes, or must have a **reentrancy guard** based on a properly cleaned-up `ThreadLocal`. The lab filters solely on `demo/BankAccount` so it avoids this chain.

## 12. Preserving `try/finally` and Multi-Threaded Context

A tracing context often performs `push`/`pop` on a span:

```java
// Model fragment; SpanScope is not part of the standard JDK.
SpanScope scope = traceContext.openScope();
try {
    return businessWork();
} finally {
    scope.close();
}
```

This code may be necessary but not sufficient: if `openScope` or `close` throws, the business outcome can change. When using `ThreadLocal`, cleanup must happen on both normal and exceptional paths, preventing a previous request's span from leaking to the next request on a thread pool.

In `CompletableFuture`, Reactor, virtual threads, or callback frameworks, a logical operation can span **multiple execution contexts**. "One Java method entry" differs from "one request span". Tracing must propagate context in a controlled way across scheduling boundaries; do not simply assume `ThreadLocal` persists when a callback runs on another thread.

A good test for a thread pool:

```text
Task A: set correlation id = X, invoke business, cleanup
Task B: do not set correlation id
Expected: Task B does NOT see X
```

This is a **test plan**, not stdout from the main lab. Use `try/finally` cleanup and assert on the same executor thread during testing to catch leaks.

## 13. Async Testing: Exceptions Are Not Necessarily Thrown Immediately at the Caller

Synchronous method:

```java
Result result = service.call(); // value or throw immediately at the call site
```

Asynchronous method:

```java
CompletableFuture<Result> future = service.callAsync();
```

`callAsync()` may **return a future normally**, and then the future completes exceptionally later. If an agent replaces the `CompletionStage`/`Future` object, calls `join()` on behalf of the caller, adds a state-mutating callback, or wraps the exception incorrectly, the caller can see a different outcome.

Async test matrix:

- Does Future/Publisher reference identity need to be preserved?
- Is the completion value equivalent?
- What **original cause** does an exceptional completion contain, and was it extra-wrapped outside the contract?
- Are cancellation, timeouts, and interrupts preserved?
- Does the callback run once, on the right executor/context, and without extra invocations?
- The count of the business method **creating a future** and the count of **completion callbacks** must be counted **separately**.

Do not mechanically compare `CompletionException` to a synchronously thrown exception: `join()` normally wraps exceptional completion in `CompletionException` per API. Choose assertions matching **the layer the caller actually uses**.

## 14. Practical Multi-Layered Testing Process

### Layer 1 — Single-Method Contract

For each target:

- Normal return, null, empty, boundary, large values.
- Expected errors per business rules.
- `Error` and unchecked exceptions if relevant.
- Reference identity/aliasing per contract.
- State mutations and application call count.
- Special primitive returns: NaN/negative zero/long/double categories.

### Layer 2 — Bytecode Correctness

After transformation:

- Class file parses cleanly.
- Class/method descriptors are not accidentally altered.
- `StackMapTable`, max stack/max locals, and exception tables are valid.
- Branch offsets/control flow and handlers are correct.
- Constructors/`<clinit>`, synchronized methods, and native/abstract methods are not mis-instrumented.
- Output class version is compatible with the target JVM.
- `-Xverify:all` and tests on the real VM.

### Layer 3 — Differential Runs

Run baseline and agent **in two separate JVMs** with:

- Same JDK/vendor/version.
- Same classpath/module-path and app artifact.
- Same input fixtures and timezone/locale when relevant.
- Fake clock/random/HTTP/database in deterministic scenarios.
- Same concurrency workload, but comparing invariants rather than arbitrary scheduler ordering.
- Exit status, stdout business projection, test fixtures/external effects.

### Layer 4 — Agent Pipeline

Test single agent and multiple agents:

- Agent added before/after other transformers.
- Each transformer processes only the right targets.
- Load time, retransform, redefine if required.
- No duplicate hooks inserted after repeated retransforms.
- Different class loaders, module access, bootstrap visibility.
- Hooks do not trigger recursive class loading and do not retain `Class<?>`/loaders indefinitely.

### Layer 5 — Regression/Soak Tests

With real/simulated traffic:

- Compare throughput, p95/p99 latency, and GC overhead.
- Look for deadlocks, hung threads, thread pool saturation.
- Verify telemetry backpressure does not fail business logic.
- Check memory leaks, queue growth, dropped telemetry, and error sampling.
- Run for minutes/hours with diverse loads/inputs.
- Have rollback/disable switches for the agent if instrumentation causes wrong outcomes.

Do not cram everything into a single unit test; different bug classes surface at different layers.

## 15. Diagnostics When Baseline and Agent Differ

| Symptom | Likely cause | Troubleshooting direction |
| --- | --- | --- |
| Different return value | Mishandled `IRETURN`/`ARETURN`/`LRETURN` operand, helper mutates return | Check stack/local saves, identity, and code paths |
| Business counter doubled | Wrapper executes target twice, instrumentation-induced retry | Separate valid request retries from hook-induced invocations |
| Probe counter doubled while business unchanged | Hook inserted twice, measuring bridge/wrapper too, or two agents | Dump transformed bytes, check method descriptors and transformer ordering |
| Probe = 0 on agent run | Transformer did not run/match target or failed silently | Assert effectiveness, check manifest, loader, class name |
| Exception type/message changed | Catch/wrap or logging callback threw | Preserve original Throwable; isolate telemetry errors |
| `Throwable` identity differs | Agent created a new exception | Rethrow same throwable, do not wrap when contract requires identity |
| Extra suppressed errors | `try-with-resources`/scope close or helper added suppressed | Check telemetry lifecycle and exception policy |
| Lost exception events | Used only `onMethodExit(ATHROW)` | Add properly scoped catch-all, avoid double counting |
| Different state | Helper touches fields, re-calls side-effecting getter, duplicate async task | Mock external effects, assert snapshots |
| `VerifyError` | Bad stack map frames/handler offsets/operand stack | ASM checks/`-Xverify:all`/target JVM load |
| `ClassFormatError` | Malformed output classfile | Check reader/writer, do not mutate input in place |
| `NoClassDefFoundError: demo/Probe` | Helper not visible to target's defining loader | Ensure class-loader/module strategy, not only system loader |
| Deadlock when agent enabled | Probe holds locks/sync log/reentrant class loading | Bound callbacks, exclude logger/agent classes |
| Undercounting under concurrency | Non-atomic counter, race, or sampling | AtomicLong/LongAdder, synchronization; distinguish sampled metrics |
| Context leaks to next request | `ThreadLocal` not cleaned up | `try/finally`, test executor thread reuse |
| Different async completion | Agent intercepts future and alters cancellation/cause | Compare returned stage semantics and exceptional completion |
| JUnit passes but production fails | Tests lack third-party agents, modules, classloaders, JDK matrix | Integration tests with full startup path |
| Different stack trace despite same error | Code offsets/frames shifted by instrumentation | Define stack trace fidelity per contract, do not confuse with exception outcome |
| High agent overhead | Too many probes/logging/string formatting | Sampling, aggregation, instrumentation scope |
| Results differ due to nondeterministic input | Time/random/network/scheduling/DB state differs between runs | Use fixtures and compare appropriate invariants |

## 16. End-of-Lesson QA Checklist

- [ ] Defined **business observation** and separated telemetry state from business logic.
- [ ] Each target has tests for return values, void paths, expected errors, state, and application invocation counts.
- [ ] Never re-invoke a method just to log, fetch a result, or measure duration.
- [ ] Preserve the same returned reference if the API requires identity.
- [ ] Do not alter throwable type/message/cause/suppressed/identity against contract.
- [ ] Do not let a telemetry failure in `finally` mask the original return/exception.
- [ ] Measure invocation counts by name+descriptor/loader, not just source method name.
- [ ] Test recursion, overloads/bridge/synthetic, synchronized, and concurrent calls.
- [ ] Test implicit exception exits, not confusing explicit `ATHROW` with all exceptional paths.
- [ ] Return `null` when the transformer does not change the class; if transforming, return new bytes without mutating input `classfileBuffer`.
- [ ] Verify class output; compute stack/frames/handlers/constructor rules correctly.
- [ ] Use two separate JVMs and the same business fixtures for baseline vs instrumented runs.
- [ ] Verify the agent actually triggers hooks, avoiding false passes when a transformer silently fails.
- [ ] Test classloader/module/helper visibility, and do not instrument recursive logging helpers.
- [ ] Test context cleanup on pool threads and async exceptional completions.
- [ ] Distinguish sampled/dropped telemetry from actual application method counts.
- [ ] Verify external effects, DB writes/messages/HTTP calls with test doubles or a sandbox.
- [ ] For retransform/redefine, ensure idempotency and no duplicate hook insertion.
- [ ] Have performance/soak tests, a backpressure policy, and agent rollback capability.

## 17. Self-Check Questions

1. **Instrumentation logs the result by calling `service.doWork()` twice. Is app call count preserved?**  
   No. Logging caused the business method to run an extra time and may trigger extra side effects.

2. **A probe records two events (START and END) for one method invocation. Does that mean the business method ran twice?**  
   No. Event count and application invocation count are two different quantities.

3. **Why run baseline and agent in two separate JVMs instead of sequentially in the same process?**  
   To prevent static state, class loading, agent redefinition/JIT, and counters from the first run from interfering with the second run.

4. **An agent run has all business outputs right, but Probe counts 0. Does the instrumentation test pass?**  
   No. The transformer may not have run while the original business code still worked; hook effectiveness must be asserted.

5. **Does `deposit(-1)` throwing an error still increment the business invocation count?**  
   Yes in the example, because the method body started and incremented the counter before validation; it is still one invocation.

6. **How many invocations of `recursive` does `recursive(3)` make?**  
   Four: n=3,2,1,0. A correct entry-only probe must observe four calls.

7. **Two threads each increment 100 times, yet the probe reports 190 while business state is 200. Where could the bug be?**  
   The probe may be using a non-atomic counter, sampling/dropped events, or a telemetry race; investigate independently from business state.

8. **Does `catch (RuntimeException e) { throw new IllegalStateException(e); }` preserve Throwable identity?**  
   No. It creates a different object and changes the exception type.

9. **Why can `finally { logger.close(); }` alter the app's outcome?**  
   If `close()` throws, it can mask the original return/exception.

10. **Does `onMethodExit(ATHROW)` see every error thrown by a callee that is not caught?**  
    No. An error can exit through control flow without the current method executing an explicit `ATHROW`.

11. **Why is `DUP` insufficient for returning `long`/`double`?**  
    These are category-2 values that require proper two-slot handling (`DUP2` or an appropriate local var).

12. **If a method returns a new reference in the instrumented version with content equal to the original object, is it always equivalent?**  
    No, if the caller cares about object identity, aliasing, or mutation.

13. **Does `Arrays.equals(before, after)` on class file bytes prove business equivalence?**  
    No. Different bytecode bytes can have the same behavior, or can break semantics; proper testing is required.

14. **Why is the total number of Java method entries in an agent-enabled program inevitably higher than baseline?**  
    Because hooks call extra helper methods. What must be preserved is **application business method invocation count**, not the sum of all helper calls.

15. **An agent catches every throwable and logs it; should it swallow `OutOfMemoryError` to "not break the app"?**  
    No solution guarantees absolute safety under severe resource errors. Design lightweight telemetry and have a clear policy for fail-open/degraded operation.

16. **How do you verify no duplicate hooks are inserted on retransform?**  
    Capture exact input/output, identify hooks by symbolic instructions, retransform multiple times, and compare probe counts with business counts.

17. **An async method returns a `CompletableFuture` successfully and the future fails later. When should the terminal outcome be recorded?**  
    Per the operation's contract: usually by tracking future completion separately, without confusing synchronous return with async success.

18. **Is passing the verifier enough to claim instrumentation preserves state/exceptions?**  
    No. The verifier checks bytecode validity; it does not prove business equivalence.

19. **Why not always compare the entire stack trace character-by-character?**  
    Instrumentation can shift line/offset/frame layouts; determine whether stack-trace fidelity is an actual requirement or only outcome exception type/message/cause.

20. **What conditions are sufficient to declare the lab test PASS?**  
    Business results, exception contract, state/call counts, and probe effectiveness all pass according to the mode run. Never report PASS if agent hooks are missing or business invariants fail.

## 18. Official Documentation and Tools

1. Oracle JDK 17 — **`java.lang.instrument.ClassFileTransformer`**: callback, transformer chaining, immutable `classfileBuffer`, `return null` or new bytes: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
2. Oracle JDK 17 — **`java.lang.instrument` package**: `-javaagent`, `Premain-Class`/`premain`, agent startup and module visibility: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
3. Oracle JDK 17 — **`Instrumentation`**: retransform/redefine, modifiability, and transformer ordering: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
4. ASM — **`AdviceAdapter`**: `onMethodEnter` and `onMethodExit`; explicit return/`ATHROW`, constructor semantics: https://asm.ow2.io/javadoc/org/objectweb/asm/commons/AdviceAdapter.html
5. ASM — official documentation and release history: https://asm.ow2.io/
6. Maven Central — **`asm-commons 9.7.1`**: https://central.sonatype.com/artifact/org.ow2.asm/asm-commons/9.7.1
7. Oracle JDK 17 — **`Throwable`**: cause, suppressed exceptions, and stack traces: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html
8. Oracle JDK 17 — **`AtomicInteger`**: thread-safe counters: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
9. Oracle JDK 17 — **`Future.get`**, memory-consistency/cancellation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
10. JVM Specification 17 — **Chapter 6**, return opcodes, `athrow`, and method invocation instructions: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html

**Conclusion:** Correct instrumentation does not just "record telemetry": it must **preserve values and identity when the contract requires, avoid changing exception types/objects, avoid adding business state mutations, and avoid re-invoking methods outside the original logic**. Run the same baseline and agent scenarios in **two independent JVMs**, check both business assertions and probe effectiveness, and then expand to concurrency, async, multiple agents, the bytecode verifier, and production-like tests.
