# `null` Arguments, Primitives, Overloads, and Varargs in Spring AOP

## 1. Why is this important when writing a Spring Aspect?

A call to a Spring bean may involve `null` arguments, `int` or `boolean` primitives, methods sharing the same name with different parameter types (*overloads*), or a method declaring `String...` (*varargs*). When using `@Before`, `@Around`, or another advice type, we need to know **which method** Spring AOP identifies and **which argument values** it extracts.

There are two different checks that are very easy to confuse:

1. **`execution(...)`** selects a *method execution join point* by its **declared method signature**, such as method name, formal parameter count, and formal parameter types.
2. **`args(...)`** inspects the **arguments at the call**, and can type-check or **bind argument values** to advice parameters. Some `args` conditions require runtime checks, whereas `execution` typically uses static signature information.

In Spring AOP, both apply only to **method executions passing through a Spring AOP proxy**. They do not automatically turn every Java method call into an advisable join point.

Specific cases:

| Situation | Key point to remember |
| --- | --- |
| `null` argument | A `null` value has no runtime class; when checking types, consider the declared parameter type and pointcut mechanics, not `arg.getClass()` directly |
| `int`, `boolean`, ... | The Java method still has a primitive type; however, `JoinPoint.getArgs()` is `Object[]`, so primitive values appear as boxed values |
| Overload | Java resolves overloads by compile-time argument types; the Spring proxy intercepts the **already selected concrete method**, rather than picking a new overload |
| Varargs `T...` | At the bytecode/reflective method signature level, varargs is **a single `T[]` array parameter**, not an infinite number of formal parameters |
| Binding advice parameters | Names in `args(name)` must be properly linked by Spring to Java advice parameters; `argNames` can be supplied |
| Modifying arguments in `@Around` | `proceed(Object[])` must receive the right logical parameter count and types, paying attention to primitives, `null`, and varargs arrays |

**Scope:** focuses on **Spring Aspect / Spring AOP**, advice types, `JoinPoint`/`ProceedingJoinPoint`, and Spring method matching; does not repeat general AOP theory or AspectJ compile-time weaving.

## 2. Two ways to read arguments inside advice

### 2.1. General approach: `JoinPoint.getArgs()`

Every advice type supports `JoinPoint` as its first parameter, while `@Around` uses `ProceedingJoinPoint`. Example:

```java
@Before("execution(* com.example.service..*.*(..))")
public void inspect(JoinPoint jp) {
    Object[] args = jp.getArgs();

    System.out.println("count=" + args.length);
    for (int i = 0; i < args.length; i++) {
        Object value = args[i];
        System.out.println(
            i + ": " + (value == null ? "<null>" : value.getClass().getName())
        );
    }
}
```

This is an **illustrative snippet to place inside a Spring-managed `@Aspect` bean**. `getArgs()` gives each argument at the invocation as an element of `Object[]`:

- Argument passed as `null` → `null` element, with no class on which to call `getClass()`.
- Formal parameter `int` → value in `Object[]` is **boxed** into the corresponding `Integer`.
- Varargs `String... tags` → typically **one `String[]` element** in `Object[]` (not automatically flattened into multiple top-level elements).
- With overloads, the count/types of **runtime values** may not uniquely identify the exact method signature. Both overloads `foo(String)` and `foo(Integer)` can be invoked with an appropriately cast `null`.

`Object[]` contains the **argument values passed to the call**, not an array of declared formal parameter types. To know the method's declared types, use `MethodSignature`.

### 2.2. Typed approach: `args(name)` for binding

Spring AOP lets you bind arguments to Java parameters of the advice:

```java
@Before(
    value = "execution(* com.example.service..*.save(..)) && args(id,..)",
    argNames = "id"
)
public void beforeSave(String id) {
    System.out.println("id=" + id);
}
```

**This is a snippet, not a standalone file.** The `args(id,..)` syntax:

- Selects join points having **at least one argument**, where the first argument satisfies `id`'s binding type.
- Binds the first argument value to the advice parameter `String id`.
- `,..` allows **zero or more** trailing arguments.
- `argNames = "id"` states the binding name explicitly to reduce dependence on compiler parameter-name metadata.

Do not confuse:

- `args(java.lang.String)`: the content inside is a **type pattern**.
- `args(id)` with Java advice parameter `String id`: this is the **binding form**.
- `execution(* *.*(java.lang.String))`: checks the **declared method parameter type**, not the runtime class of a specific value.

Spring recommends using typed binding when possible, though when observing multiple overloads, `null`, and varargs simultaneously, `JoinPoint.getArgs()` combined with `MethodSignature` is often easier to analyze.

## 3. The `null` argument case

### 3.1. A `null` value has no runtime class

Suppose the method is:

```java
public String accept(String value) {
    return value == null ? "EMPTY" : value;
}
```

And the call through the Spring proxy is:

```java
service.accept(null);
```

Inside the Spring advice, `jp.getArgs().length == 1` and `jp.getArgs()[0] == null`. Never write:

```java
String typeName = jp.getArgs()[0].getClass().getName();
```

because it can throw a `NullPointerException` **right inside the advice**, causing a new error before the target even runs.

Safer approach:

```java
Object arg = jp.getArgs()[0];
String kind = (arg == null) ? "null" : arg.getClass().getSimpleName();
```

Snippets in this section are not a complete project; section 7 provides a runnable program.

### 3.2. Distinguishing `execution` and `args` when `null` is passed

For a method declared `accept(String value)`:

- `execution(* *.accept(java.lang.String))` matches the **single `String` parameter signature**, whether the invocation passes `"abc"` or `null`.
- `args(java.lang.String)` is a type-related condition on the argument. In AspectJ semantics, when an argument **is `null`**, matching is evaluated against whether the **static declared argument type** is compatible with the type pattern; no runtime class can be obtained from `null` itself. For a method with a declared `String` parameter, it can match `null`.
- If a method declares `accept(Object value)` and the caller passes `null`, **do not assume** `args(java.lang.String)` must match as it did for a declared `String` parameter: the static type is `Object`, and `null` provides no runtime class proving it is a `String`.

An easily misunderstood case:

```java
Object item = null;
service.acceptObject(item); // method acceptObject(Object)
```

You cannot reason "item was meant to hold a String so `args(String)` matches"; for `null`, dynamic object type information does not exist.

**Practical rule:** if an advice's goal is to handle **`null` values as well**, match the method by its explicit signature using `execution(...)` or an appropriate method scope, then use `JoinPoint.getArgs()` and check for `null` inside the advice. This approach is predictable, easy to verify, and does not rely on false assumptions about runtime classes.

### 3.3. `null` and typed binding

Example:

```java
@Before(
    value = "execution(* demo..*.accept(java.lang.String)) && args(value)",
    argNames = "value"
)
public void capture(String value) {
    System.out.println(value == null ? "NULL INPUT" : "INPUT " + value);
}
```

This is an **illustrative** advice, not added to the project in section 7. The fact that a reference-type binding can carry `null` **is not the same** as being able to bind `null` into a primitive `int`. If you need to actively handle `null`, make the advice parameter an appropriate reference type and check before dereferencing.

`null` **cannot be passed directly** as a value to a primitive `int`/`boolean` formal parameter of a Java method; if an `Integer` wrapper is unboxed from `null`, a `NullPointerException` can occur before the Spring proxy actually receives that call.

## 4. Primitives and boxing across Spring AOP

### 4.1. Formal parameter is primitive, yet `getArgs()` contains a wrapper

Consider:

```java
public int addOne(int number) {
    return number + 1;
}
```

With a client calling `addOne(4)` through the proxy:

| Question | Result |
| --- | --- |
| `Method.getParameterTypes()[0]` | `int.class` |
| `method.getParameterTypes()[0].isPrimitive()` | `true` |
| `JoinPoint.getArgs()[0]` | Boxed `Integer` holding value 4 |
| `JoinPoint.getArgs()[0] instanceof Integer` | `true` |
| Can `null` be passed directly for a formal `int`? | No |

At the JVM reflective/AOP invocation boundary, `Object[]` cannot hold a primitive such as `int` directly. Thus Java boxing/unboxing participates when representing or forwarding arguments.

### 4.2. `args` and autoboxing

Under AspectJ pointcut semantics, boxing/unboxing is accounted for when matching primitive/wrapper types. For instance, with **one argument** of type `int`, both `args(int)` and `args(java.lang.Integer)` can match; this does not alter the formal signature being `int`.

Distinguish clearly:

```text
Method signature: addOne(int)
                        |
                Spring AOP invocation
                        |
              JoinPoint.getArgs()[0]
                        |
                        v
                  Integer(4)
```

If you want to select **only formal primitive `int`**, use:

```java
@Before("execution(* demo..*.addOne(int))")
public void beforePrimitiveAdd() {
    // match method signature addOne(int)
}
```

If you want to bind the value:

```java
@Before(
    value = "execution(* demo..*.addOne(int)) && args(amount)",
    argNames = "amount"
)
public void beforeAdd(int amount) {
    System.out.println("amount=" + amount);
}
```

These are **two standalone snippets**, requiring an `@Aspect` bean and imports. `argNames` holds the advice parameter name, unrelated to the formal parameter name on the implementation (the formal parameter may be named `number` while the binding is still named `amount`).

### 4.3. Common primitive mistakes

- **Casting `Object` to primitive incorrectly:** use `((Integer) obj).intValue()` or a valid unboxing cast, not `obj.getClass() == int.class`.
- **Replacing an argument with `null` when the target expects `int`:** `proceed(...)` can fail when Spring/reflective invocation has to unbox `null`.
- **Having advice return `null` for a primitive-returning method:** if `@Around` returns `null` instead of an `int`, Spring can throw an error because `null` cannot serve as a primitive return value.
- **Assuming `Integer` and `int` are always identical:** declared method signatures `calculate(int)` and `calculate(Integer)` are **two different overloads**, even though argument reflection may show `Integer` for both when non-null.

## 5. Overloads: which method does Spring advice intercept?

Java selects the **overload** before Spring AOP executes the invocation on the proxy. Example:

```java
public String render(String text) { return "S:" + text; }
public String render(Integer number) { return "I:" + number; }
```

With calls:

```java
service.render("hello");            // render(String)
service.render(Integer.valueOf(3)); // render(Integer)
service.render((String) null);      // render(String)
service.render((Integer) null);     // render(Integer)
```

An uncast call:

```java
service.render(null);
```

is a **compile error due to an ambiguous overload** in this example of two unrelated types `String` and `Integer`. Spring AOP does not "re-resolve" overloads at runtime; the program must compile first.

### 5.1. Why is `getArgs()` not enough to identify an overload?

Both calls:

```java
service.render((String) null);
service.render((Integer) null);
```

produce a `JoinPoint.getArgs()` represented as:

```text
[null]
```

Yet the method signatures differ. To know the exact method:

```java
MethodSignature sig = (MethodSignature) jp.getSignature();
Class<?>[] declaredTypes = sig.getMethod().getParameterTypes();
```

- For the first overload: `declaredTypes[0] == String.class`.
- For the second overload: `declaredTypes[0] == Integer.class`.

That code is a snippet requiring imports for `org.aspectj.lang.reflect.MethodSignature`, and `java.lang.reflect.Method` if referencing `Method` directly.

### 5.2. Pointcuts targeting a specific overload

```java
@Before("execution(* demo..*.render(java.lang.String))")
public void beforeRenderText() {
    System.out.println("TEXT");
}

@Before("execution(* demo..*.render(java.lang.Integer))")
public void beforeRenderNumber() {
    System.out.println("NUMBER");
}
```

These are **two illustrative advice methods**. Spring AOP uses the static signature to distinguish the two overloaded methods, even when the client passes a cast `null`.

Do not rely on `args(java.lang.String)` alone if you need to restrict **strictly** to the overload with a formal `String` parameter: when the declared parameter is `Object` while the runtime value is `String`, `args(String)` can still match `render(Object)`. Combine `execution(...)` and `args(...)` when you need both static method selection and runtime value conditions.

### 5.3. `int` vs. `Integer` overloads

If a class has:

```java
void total(int quantity) { }
void total(Integer quantity) { }
```

then Java has two valid overloads. When calling `total(5)`, the compiler normally chooses the directly matching formal primitive `int`; `total(Integer.valueOf(5))` chooses the `Integer` reference. For `total(null)`, formal `int` cannot accept null, so the `Integer` wrapper overload can be chosen.

In `getArgs()`, successful calls to either overload can appear as a boxed `Integer`, so **you must use the method signature to distinguish formal `int` from `Integer`**.

## 6. Varargs: `T...` is a formal array parameter

### 6.1. What signature does the method compile to?

Java:

```java
public String tags(String label, String... names) {
    return label + ":" + names.length;
}
```

In terms of reflective parameters, the signature is equivalent to:

```java
tags(String label, String[] names)
```

plus the **`isVarArgs`** flag on the method. When a client calls:

```java
service.tags("many", "a", "b");
```

the Java compiler packs the varargs into the trailing array before the invocation. In Spring AOP:

- `MethodSignature.getMethod().getParameterCount()` is **2**, not 3.
- `JoinPoint.getArgs().length` is normally **2**.
- `getArgs()[0]` is the String `"many"`.
- `getArgs()[1]` is `String[] {"a","b"}`, **not** two top-level arguments `"a"`, `"b"`.
- `((MethodSignature) jp.getSignature()).getMethod().isVarArgs()` returns `true`.

If you plan to bind the varargs portion, think of **one `String[]` array argument**, not an unbounded list of Java advice parameters.

### 6.2. Three varargs states to distinguish

| Java call | Second formal argument inside method |
| --- | --- |
| `tags("zero")` | `new String[0]`, i.e., an empty array |
| `tags("two","a","b")` | `String[] {"a","b"}` |
| `tags("nil",(String[]) null)` | **null array**, not an empty array |
| `tags("oneNull",(String) null)` | `String[] {null}`, i.e., an array with one null element |

`tags("nil", (String[]) null)` is a special call requiring an explicit cast. For:

```java
tags("ambiguous", null);
```

Java may emit a **non-varargs call for last parameter** warning, because `null` could be the array argument itself; do not leave readers guessing whether `null` means a single element inside the array. If you want one null element, use `(String)null` or `new String[] { null }`.

When advice needs to print arrays cleanly, use:

```java
System.out.println(Arrays.deepToString(jp.getArgs()));
```

with `import java.util.Arrays`. `Arrays.toString(jp.getArgs())` can print the identity string of a nested `String[]`; `deepToString` displays nested array contents in readable form.

### 6.3. `execution(..)` pointcuts with varargs

To select `tags(String, String...)` precisely by Java reflection parameter types, note that the last parameter is `String[]`. However, AspectJ pattern syntax for varargs requires care around ellipsis syntax. Unless you intentionally need to filter by array signature, a clear, less error-prone approach is:

```java
@Before("execution(* demo..*.tags(..))")
public void beforeTags(JoinPoint jp) {
    Object[] args = jp.getArgs();
    // Inspect the signature and trailing array if needed.
}
```

This is a snippet. `(..)` matches any number of formal parameters on a method named `tags`; inspecting the actual array via `MethodSignature` avoids confusing call-site varargs with formal parameter count.

**Do not use** `args(label, first, second)` merely because a Java source call has two vararg elements; those are not three formal invocation arguments in proxy mechanics.

## 7. Runnable Spring AOP project: four scenarios in one service

The complete example uses **Java 17+, Maven, Spring Framework 6.2.6**. It contains:

- One Spring-managed bean `ArgumentService`, target implementation `ArgumentServiceImpl`.
- One `@Aspect` using a single `@Around` advice solely to **record the method signature and argument values** and call `proceed()` once without modifying data.
- Calls with `null`, primitive `int`, two overloads taking `String`/`Integer`, and varargs that are empty, multi-element, null array, or an array containing null.
- Output independent of generated proxy class names: the aspect prints **declared parameter simple names** from `MethodSignature` and argument values via `Arrays.deepToString`.

Organizing a single `@Around` ensures the trace does not depend on advisor ordering across multiple advice methods matching one join point. The code runs using Spring's proxy-based AOP, **not** compile-time weaving.

### 7.1. Directory structure

```text
spring-aop-argument-cases/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ArgumentCasesDemo.java
```

### 7.2. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-argument-cases</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ArgumentCasesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. File `src/main/java/demo/ArgumentCasesDemo.java`

```java
package demo;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class ArgumentCasesDemo {

    public interface ArgumentService {
        String accept(String value);
        int addOne(int number);
        String render(String value);
        String render(Integer value);
        String tags(String label, String... values);
    }

    public static class ArgumentServiceImpl implements ArgumentService {

        @Override
        public String accept(String value) {
            System.out.println("TARGET accept=" + value);
            return value == null ? "NULL" : "TEXT:" + value;
        }

        @Override
        public int addOne(int number) {
            System.out.println("TARGET addOne=" + number);
            return number + 1;
        }

        @Override
        public String render(String value) {
            System.out.println("TARGET render(String)=" + value);
            return "S:" + value;
        }

        @Override
        public String render(Integer value) {
            System.out.println("TARGET render(Integer)=" + value);
            return "I:" + value;
        }

        @Override
        public String tags(String label, String... values) {
            String view = values == null ? "null" : Arrays.toString(values);
            System.out.println(
                "TARGET tags label=" + label + " values=" + view
            );
            return label + ":" + (values == null ? "NULL" : values.length);
        }
    }

    @Aspect
    public static class TraceAspect {

        @Around(
            "execution(* demo..*.accept(..)) || " +
            "execution(* demo..*.addOne(..)) || " +
            "execution(* demo..*.render(..)) || " +
            "execution(* demo..*.tags(..))"
        )
        public Object trace(ProceedingJoinPoint pjp) throws Throwable {
            Method method =
                ((MethodSignature) pjp.getSignature()).getMethod();

            String declaredTypes = Arrays.stream(method.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(","));

            System.out.println(
                "AOP " + method.getName()
                    + "(" + declaredTypes + ")"
                    + " varargs=" + method.isVarArgs()
                    + " args=" + Arrays.deepToString(pjp.getArgs())
            );

            return pjp.proceed();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {
        @Bean
        public ArgumentService argumentService() {
            return new ArgumentServiceImpl();
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                 new AnnotationConfigApplicationContext(Config.class)) {

            ArgumentService service = ctx.getBean(ArgumentService.class);
            System.out.println("AOP_PROXY=" + AopUtils.isAopProxy(service));

            System.out.println("CLIENT=" + service.accept(null));
            System.out.println("CLIENT=" + service.addOne(4));
            System.out.println("CLIENT=" + service.render((String) null));
            System.out.println("CLIENT=" + service.render((Integer) null));
            System.out.println("CLIENT=" + service.tags("zero"));
            System.out.println("CLIENT=" + service.tags("many", "x", "y"));
            System.out.println(
                "CLIENT=" + service.tags("nil", (String[]) null)
            );
            System.out.println(
                "CLIENT=" + service.tags("oneNull", (String) null)
            );
        }
    }
}
```

Because `ArgumentService` is an interface, the Spring Framework configuration with `proxyTargetClass = false` can create a **JDK dynamic proxy**. `TraceAspect` is registered via `@Bean`, so Spring reads `@Aspect` and builds an advisor applying to the methods in the expression.

### 7.4. Running Maven

From the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Stdout lines printed by the program itself, according to the logic and signatures in the example** (excluding Maven/Spring's own logging):

```text
AOP_PROXY=true
AOP accept(String) varargs=false args=[null]
TARGET accept=null
CLIENT=NULL
AOP addOne(int) varargs=false args=[4]
TARGET addOne=4
CLIENT=5
AOP render(String) varargs=false args=[null]
TARGET render(String)=null
CLIENT=S:null
AOP render(Integer) varargs=false args=[null]
TARGET render(Integer)=null
CLIENT=I:null
AOP tags(String,String[]) varargs=true args=[zero, []]
TARGET tags label=zero values=[]
CLIENT=zero:0
AOP tags(String,String[]) varargs=true args=[many, [x, y]]
TARGET tags label=many values=[x, y]
CLIENT=many:2
AOP tags(String,String[]) varargs=true args=[nil, null]
TARGET tags label=nil values=null
CLIENT=nil:NULL
AOP tags(String,String[]) varargs=true args=[oneNull, [null]]
TARGET tags label=oneNull values=[null]
CLIENT=oneNull:1
```

This is the **expected stdout from the presented code**, not a claim of having executed Maven in a specific environment.

### 7.5. Analyzing the output by topic

**`accept(null)` case:** the advice sees `args=[null]` yet still identifies the formal parameter as `String` via `MethodSignature`. The target returns `NULL` without throwing a `NullPointerException`.

**`addOne(4)` case:** the signature shows `addOne(int)`, while `getArgs()` represents primitive value `4` as an element of `Object[]` and prints `[4]`.

**Two `render(...)` overloads:** both have `args=[null]`. Relying solely on runtime values in the array cannot tell which overload the caller chose; the signature shows `render(String)` or `render(Integer)`.

**Empty varargs:** `tags("zero")` still has **2 formal arguments**, where the trailing array has length 0. Hence output `[zero, []]`.

**Multi-element varargs:** `tags("many","x","y")` has one label and one trailing array; `Arrays.deepToString` prints `[many, [x, y]]`, not three top-level elements.

**Null array:** `tags("nil",(String[])null)` passes `null` as the trailing array; output is `[nil, null]` and the target is written not to dereference `null`.

**Single null element:** `tags("oneNull",(String)null)` creates a length-1 array holding `null`; output is `[oneNull, [null]]`, clearly distinct from a null array.

## 8. Pairing `execution(...)` and `args(...)` for the right purpose

The four illustrative expressions below **are not advice registered in the project from section 7**:

```java
// 1. Formal method signature has one String parameter
@Before("execution(* demo..*.accept(java.lang.String))")
public void declaredString() { }

// 2. Runtime argument bound by type String
@Before(
    value = "execution(* demo..*.accept(..)) && args(value)",
    argNames = "value"
)
public void boundString(String value) { }

// 3. Formal overload render(Integer)
@Before("execution(* demo..*.render(java.lang.Integer))")
public void integerOverload() { }

// 4. Formal primitive int
@Before("execution(* demo..*.addOne(int))")
public void primitiveOverload() { }
```

For **overloads**, prefer `execution(...FormalType...)` to select the signature. For **runtime conditions or extracting specific values**, use `args(...)` (binding) or `JoinPoint.getArgs()` when broad inspection is needed.

### `args(..)` does not distinguish every overload by itself

Specifically:

- If overloads include `render(String)` and `render(Object)`, an invocation of `render(Object)` receiving a runtime `String` can satisfy `args(String)` even though the declared signature is not `render(String)`.
- If an argument is `null`, typed matching outcomes are influenced by the declared parameter type; do not treat `args(String)` as an `arg instanceof String` check in every situation.
- If a method has primitive `int`, the argument observed in `Object[]` is a boxed wrapper. Do not infer formal signatures from `Object#getClass()` alone.
- If a method uses varargs, the trailing part of `args` typically corresponds to **one array argument** in the runtime invocation, not a separate binding variable per vararg element.

A safe strategy for general logging is a **relatively static pointcut** paired with `Object[]` and signature handling that checks for null and arrays.

## 9. Replacing arguments with `ProceedingJoinPoint.proceed(Object[])`

Inside `@Around`, Spring lets you continue the chain with a **replacement argument array**:

```java
@Around("execution(* demo..*.accept(java.lang.String))")
public Object trimInput(ProceedingJoinPoint pjp) throws Throwable {
    Object[] next = pjp.getArgs().clone();

    String oldValue = (String) next[0]; // May be null
    next[0] = oldValue == null ? "" : oldValue.trim();

    return pjp.proceed(next);
}
```

This is a **snippet**, not registered in section 7's project. Key points:

1. `proceed()` preserves the current arguments.
2. `proceed(next)` forwards the new values to the next step of the Spring AOP invocation, suitable for input normalization.
3. The length of `next` must match the **formal parameter count** of the intercepted method. Do not confuse the number of elements in a varargs array with the formal parameter count.
4. Replacement values must be **assignable** to the formal parameter types; primitives cannot accept `null`.
5. If the method is overloaded, `proceed(newArgs)` **does not invoke a different overload**. It continues the *already selected method invocation* with new values, without re-running Java overload resolution.
6. Altering arguments can affect business logic, cache keys, validation, and other advice depending on interceptor ordering; modify only deliberately and test thoroughly.

### 9.1. When modifying varargs

Suppose we are advising:

```java
String tags(String label, String... values);
```

In formal parameters, there are **two positions**: `String` and `String[]`. To replace the trailing array with two elements:

```java
Object[] next = pjp.getArgs().clone();
next[1] = new String[] {"normalized", "checked"};
return pjp.proceed(next);
```

If you mistakenly pass:

```java
return pjp.proceed(new Object[] {
    "label", "normalized", "checked"
});
```

then the replacement `Object[]` has three elements while the formal method has only **two parameters**; this is not a safe way to pass varargs to `proceed(Object[])`.

### 9.2. `int` and `Integer` when replacing args

For `addOne(int)`:

```java
Object[] args = pjp.getArgs().clone();
args[0] = Integer.valueOf(10); // Valid to unbox to int
return pjp.proceed(args);
```

Do not set `args[0] = null`: `null` cannot be unboxed into primitive `int`. Also do not substitute an arbitrary `Long` for `Integer` assuming Spring will always convert every numeric type as you wish.

### 9.3. Spring AOP and native AspectJ differ on binding

Spring documentation explains how to write `proceed(Object[])` consistently when using fully-typed `@Around` advice and binding method arguments in matching order. When moving logic from Spring proxy mode to AspectJ weaving mode, **do not assume** every way of passing `Object[]` in snippets preserves the same semantics; follow the advice-arguments/binding contract of that mode.

## 10. Common misunderstandings with `@args`

In Spring AOP pointcuts, `args(Type)` and `@args(Annotation)` are **completely different**:

- `args(Type)` inspects runtime argument types/values and supports the binding form.
- `@args(Annotation)` uses an **annotation on the runtime class of the argument object** for matching via the annotation designator mechanism.

Example:

```java
@Pointcut("@args(com.example.app.Tracked)")
public void trackedRuntimeArgument() {
}
```

This is an **illustrative snippet** requiring real annotation/class definitions. With a `null` argument, there is **no runtime object class** on which to check annotations. Hence `@args(Tracked)` cannot be used as a general way to detect an annotation placed on the formal parameter type when the value is null.

If you need conditions on **annotations on parameter declarations** or on methods, choose the appropriate tool (reflection metadata, annotation resolvers, or `@annotation` for method annotations) rather than equating them with `@args`.

## 11. Proxy boundaries, JDK/CGLIB, and method eligibility

### 11.1. Same expression, yet the method skips the proxy

A Spring aspect has a pointcut matching `addOne(int)`, yet if the caller invokes:

```java
new ArgumentServiceImpl().addOne(4);
```

that object is not a Spring AOP proxy, so the advice does not run.

Similarly, when the target executes:

```java
public void outer() {
    this.inner("x");
}
```

the `this.inner(...)` call inside the target does not go back through the proxy. Even if `inner(String)` matches `args(String)` and `execution(...)`, Spring AOP will not process a new join point at the proxy boundary for that internal call.

### 11.2. Proxy strategy affects where interception is possible

- A JDK dynamic proxy exposes interface methods. In the runnable project, both overloads `render(String)` and `render(Integer)` live on the interface, so clients can call them through the JDK proxy.
- A CGLIB subclass proxy can intercept overridable methods on the implementation; `final`/`private` methods cannot be advised via CGLIB overriding.
- Switching from JDK to CGLIB **does not change the Java nature of null or varargs**: `String...` is still an array in the signature, and primitives still undergo boxing across `Object[]`.
- There is no need to force CGLIB just to distinguish overloads if the interface already declares them.

### 11.3. Reflected `Method` may be the interface method

With a JDK proxy, `MethodSignature.getMethod()` typically reflects the interface method being invoked. It still carries the formal parameter signature needed to distinguish overloads and varargs. If you need the specific declaration on the implementation to read method annotations, Spring provides helpers such as `AopUtils.getMostSpecificMethod(interfaceMethod, targetClass)`. However, for **argument count, formal types, and `isVarArgs`**, the interface signature is sufficient in the demo.

## 12. Tool selection rule table

| Need | Preferred approach | Reason |
| --- | --- | --- |
| Record all argument values, including null/arrays | `JoinPoint.getArgs()` + null-safe checks | Does not enforce a single typed parameter binding |
| Distinguish two same-named overloads | `MethodSignature.getMethod().getParameterTypes()` or `execution(...Type...)` | `null` values can make runtime arrays look identical |
| Bind a first parameter of a specific type | `args(name,..)` + Java advice param + `argNames` | Clear typed binding |
| Select only methods with formal `int` | `execution(* *.method(int))` | Avoids confusing boxed runtime values with declared signature |
| Know whether a method uses varargs | `Method.isVarArgs()` | Accurate metadata flag instead of counting call-site arguments |
| Count varargs elements | Inspect/cast trailing formal array, then `Array.getLength` or `values.length` | Varargs is passed as a single formal array parameter |
| Modify inputs before the target | `@Around` and `proceed(Object[])` | Has chain-control authority |
| Select by runtime object annotations | `@args(...)`, accounting for null limits | Does not mean the same as `args(...)` |
| Diagnose missing advice | Check proxy, expression, and call path | Spring AOP only intercepts calls going through the proxy |

## 13. Debugging checklist

1. **Did the client obtain the proper Spring bean from context?** Never use `new` to test advice.
2. **Is the bean proxied?** Use `AopUtils.isAopProxy(bean)` in tests.
3. **What is the actual method signature?** Print `MethodSignature.getMethod()` and `getParameterTypes()`.
4. **Is the pointcut matching static signature or runtime arg types?** Distinguish `execution` from `args`.
5. **Are there `null` arguments?** Avoid dereferencing; check declared types rather than guessing runtime classes.
6. **Is the formal parameter primitive or wrapper?** `int` and `Integer` are different overloads, yet `getArgs()` displays boxed values.
7. **Does the overloaded method have an ambiguous call?** Java compile-time resolution may require an explicit cast on `null`.
8. **Is varargs the trailing array?** Distinguish an empty array, a null array, and an array containing a null element.
9. **Does any `@Around` modify arguments?** `proceed(Object[])` must match the formal parameter count and compatible types.
10. **Is there an `args(...)` binding name mismatch?** Check advice parameter names, `argNames`, and binding types.
11. **Was the method short-circuited by another advice?** Caching/around advice might skip invoking the target.
12. **Are self-invocation, `final`/`private`, or JDK/CGLIB differences involved?** A matching pointcut does not mean every call is intercepted by a Spring proxy.
13. **Does logging cause side effects?** Do not blindly call `toString()` on large or sensitive inputs; for arrays, use safe formatting and mind security.

## 14. Self-check exercises

**Q1.** `String accept(String value)` is called with `null` through a proxy. What are `getArgs()[0]` and the formal parameter type?  
**Answer:** The value is `null`; the formal type is still `String.class`.

**Q2.** `int addOne(int number)` is called with `4`. What class does `getArgs()[0].getClass()` usually return?  
**Answer:** `Integer.class` due to boxing; the formal type is still `int.class`.

**Q3.** Given `render(String)` and `render(Integer)`, does calling `render(null)` reach the Spring aspect?  
**Answer:** No, if Java compilation fails with an ambiguous overload error; a cast like `(String)null` or `(Integer)null` is required to choose a method.

**Q4.** With `render((String)null)` and `render((Integer)null)`, is the `getArgs()` array enough to distinguish the overloads?  
**Answer:** No; both can be `[null]`. Use `MethodSignature` or match `execution(...FormalType...)`.

**Q5.** `tags("x","a","b")` invokes `tags(String, String...)`. What is `getArgs().length` normally?  
**Answer:** 2, because the formal varargs parameter is a single `String[]`.

**Q6.** What is the difference between `tags("x")` and `tags("x",(String[])null)`?  
**Answer:** The first passes an empty array; the second passes a null array. Target code must handle them differently if desired.

**Q7.** How does `tags("x",(String)null)` differ from a null array?  
**Answer:** It creates a one-element array containing `null`; the array length is 1, not `null`.

**Q8.** Does `args(String)` mean the exact same thing as `execution(* *(String))`?  
**Answer:** No. `execution` selects the formal method signature, while `args` evaluates the argument/type at invocation; `null` and runtime subtypes make the difference clear.

**Q9.** An `@Around` advice intercepted `render(String)` and calls `proceed(new Object[]{Integer.valueOf(5)})`. Does it switch to the `render(Integer)` overload?  
**Answer:** No. Spring continues the invocation of the already selected method; new arguments do not force Java to re-select an overload.

**Q10.** Is `proceed(new Object[]{"label","a","b"})` appropriate for passing three vararg elements to `tags(String, String...)`?  
**Answer:** No. The formal signature has two parameters, so a trailing array like `new Object[]{"label", new String[]{"a","b"}}` is required.

**Q11.** If `@Before` matches a method yet the target calls it internally via `this.method()`, will the advice definitely run?  
**Answer:** No, because self-invocation on the target bypasses the Spring proxy.

**Q12.** Why should you avoid calling `value.getClass()` on every element of `getArgs()` when logging?  
**Answer:** Because elements may be `null`; furthermore, logging raw values can expose secrets and varargs arrays require specialized formatting.

## 15. Official documentation

- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `JoinPoint.getArgs()`, `args(name)` binding, advice parameter names, `proceed(Object[])`.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): `execution(...)` versus `args(...)`, static method signatures, and runtime argument matching.
- [Spring Framework — Pointcut API](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/pointcuts.html): static/dynamic method matching in Spring proxies.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB limits and self-invocation.
- [AspectJ Programming Guide — Pointcut Semantics](https://eclipse.dev/aspectj/doc/released/progguide/semantics-pointcuts.html): `args` semantics and `null` handling.
- [AspectJ 5 — Autoboxing and Unboxing](https://eclipse.dev/aspectj/doc/latest/adk15notebook/autoboxing.html): matching primitives and wrappers with `args`.
