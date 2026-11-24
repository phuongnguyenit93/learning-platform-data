# Static MethodMatcher and Dynamic Argument-Based Checking in Spring AOP

## 1. Goal: Same Signature, Multiple Decisions Based on Arguments

Suppose `TransferService.transfer(String, int)` is always eligible for minimal logging, but only calls with `amount >= 1000` require additional auditing. Spring AOP lets you separate **static conditions** (class, method name, parameter types/count) from **dynamic conditions** (the actual value of `amount` in each invocation).

`Pointcut` contains a `ClassFilter` and a `MethodMatcher`; `DefaultPointcutAdvisor` pairs a Pointcut with an advice inside a Spring proxy. For `MethodMatcher`, distinguish three methods:

- `matches(Method, Class<?>)`: static check to see if the method can receive advice.
- `isRuntime()`: indicates whether actual runtime values need to be checked on each invocation.
- `matches(Method, Class<?>, Object... args)`: called only when the static step is true and `isRuntime()` is true; it may return true for one call and false for another.

## 2. Predicting Behavior When Methods and Arguments Change

| Call through proxy | Static match transfer(String,int) | Dynamic match amount >= 1000 | Dynamic audit |
| --- | --- | --- | --- |
| `transfer("A", 50)` | Yes | No | Skipped |
| `transfer("B", 1500)` | Yes | Yes | Runs |
| `balance("A")` | No | Not needed | Skipped |

`ClassFilter` remains the first gate to exclude unrelated target classes altogether. Spring may cache static decisions when creating or resolving proxies; do not attach side effects to a matcher or assert that it runs exactly once. For a method that passes the static step, the runtime matcher is evaluated on each invocation according to the argument state at that moment, and only then does Spring decide whether to run the corresponding advice.

Spring provides two built-in classes: `StaticMethodMatcherPointcut` (`isRuntime() == false`) and `DynamicMethodMatcherPointcut` (`isRuntime() == true`). A static matcher fits when the same signature always yields the same decision; a dynamic matcher requires a sufficiently narrow static condition and a lightweight, pure `args` check that does not alter business state. The next example implements this exact `transfer` scenario using `ProxyFactory`.

## 3. Complete Example with Spring ProxyFactory

Requirement: the `transfer` method of `TransferService` is audited. The **static** approach audits every transfer call. The **dynamic** approach audits only when the `amount >= 1000` argument condition holds. The example uses Java 17+ and Spring AOP directly, without a Spring Boot container or `@Aspect` annotations.

**`build.gradle`** (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-aop:6.1.21'
}

application {
    mainClass = 'example.MatchersDemo'
}
```

**`src/main/java/example/MatchersDemo.java`**:

```java
package example;

import java.lang.reflect.Method;
import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.Pointcut;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.DefaultPointcutAdvisor;
import org.springframework.aop.support.DynamicMethodMatcherPointcut;
import org.springframework.aop.support.StaticMethodMatcherPointcut;

public class MatchersDemo {

    public interface TransferService {
        void transfer(String account, int amount);
        void balance(String account);
    }

    static final class TransferServiceImpl implements TransferService {
        @Override
        public void transfer(String account, int amount) {
            System.out.println("TARGET transfer " + account + " " + amount);
        }

        @Override
        public void balance(String account) {
            System.out.println("TARGET balance " + account);
        }
    }

    private static boolean isTransfer(Method method, Class<?> targetClass) {
        return TransferService.class.isAssignableFrom(targetClass)
                && method.getName().equals("transfer")
                && method.getParameterCount() == 2
                && method.getParameterTypes()[0] == String.class
                && method.getParameterTypes()[1] == int.class;
    }

    static final class StaticTransferPointcut
            extends StaticMethodMatcherPointcut {
        @Override
        public boolean matches(Method method, Class<?> targetClass) {
            return isTransfer(method, targetClass);
        }
    }

    static final class LargeTransferPointcut
            extends DynamicMethodMatcherPointcut {
        @Override
        public boolean matches(Method method, Class<?> targetClass) {
            // Exclude unrelated methods before inspecting args.
            return isTransfer(method, targetClass);
        }

        @Override
        public boolean matches(Method method, Class<?> targetClass,
                               Object... args) {
            // int parameter is boxed into Integer in args.
            return args.length == 2
                    && args[1] instanceof Integer amount
                    && amount >= 1000;
        }
    }

    private static TransferService createProxy(Pointcut pointcut) {
        ProxyFactory factory = new ProxyFactory(new TransferServiceImpl());
        factory.setInterfaces(TransferService.class);
        factory.setProxyTargetClass(false);

        MethodInterceptor audit = invocation -> {
            System.out.println("ADVICE audit");
            return invocation.proceed();
        };
        factory.addAdvisor(new DefaultPointcutAdvisor(pointcut, audit));
        return (TransferService) factory.getProxy();
    }

    public static void main(String[] args) {
        System.out.println("=== STATIC ===");
        TransferService a = createProxy(new StaticTransferPointcut());
        a.transfer("ACC", 100);
        a.transfer("ACC", 1500);
        a.balance("ACC");

        System.out.println("=== DYNAMIC ===");
        TransferService b = createProxy(new LargeTransferPointcut());
        b.transfer("ACC", 100);
        b.transfer("ACC", 1500);
        b.balance("ACC");
    }
}
```

Run in the directory containing `build.gradle` with `gradle run` (if the project has a Gradle wrapper: `./gradlew run`; PowerShell: `.\gradlew.bat run`). Program stdout, excluding Gradle logs:

```text
=== STATIC ===
ADVICE audit
TARGET transfer ACC 100
ADVICE audit
TARGET transfer ACC 1500
TARGET balance ACC
=== DYNAMIC ===
TARGET transfer ACC 100
ADVICE audit
TARGET transfer ACC 1500
TARGET balance ACC
```

Reading the results:

1. With the **static** pointcut, both `transfer` calls receive advice, because `Method` and `targetClass` do not change regardless of the amount.
2. With the **dynamic** pointcut, the static step selects `transfer`; the runtime step checks `args[1]`. When amount is `100`, the advice does not run, yet the target still executes. When amount is `1500`, the advice runs before the target.
3. `balance` is excluded immediately in `matches(Method, Class<?>)` for both pointcuts, so no audit line is printed.
4. `setInterfaces` and `setProxyTargetClass(false)` make the example use a JDK interface proxy; calls to methods through the interface proxy are what pass through Spring AOP.

Note: `instanceof Integer amount` uses Java 17 pattern matching, and primitive `int` is boxed when placed into `Object[] args`. Checking `args.length` alongside `instanceof` prevents errors if the signature is unexpected. Checking both the name **and parameter types** in the static step also prevents accidentally matching overloads.

## 4. Designing Efficient Matchers

Place conditions **independent of input values** in the two-parameter overload:

```java
@Override
public boolean matches(Method method, Class<?> targetClass) {
    return method.getName().equals("transfer")
            && method.getParameterCount() == 2;
}
```

Place only conditions **requiring runtime call values** in the three-parameter overload:

```java
@Override
public boolean matches(Method method, Class<?> targetClass, Object... args) {
    return args.length == 2
            && args[1] instanceof Integer amount
            && amount >= 1000;
}
```

These two snippets illustrate the separation of responsibilities; the full runnable example in Section 3 performs stricter signature checking.

For a service with many methods where only `transfer` needs a threshold check, the static filter avoids the cost of inspecting `args` on other methods. Do not let the static overload always return `true` unless you genuinely intend to run dynamic checks for all of them.

A matcher should be **fast, side-effect free, and without I/O**, must not mutate `args`, and must not depend on unpredictably changing state. For very expensive conditions (DB, HTTP), consider performing them in the service/advice with clear caching and error-handling policies; dynamic matchers are invoked frequently in the method call path.

## 5. Common Pitfalls

**Confusing `isRuntime()` with runtime proxy creation.** It only indicates whether the `args`-taking overload must also be evaluated. `StaticMethodMatcherPointcut` has `isRuntime() == false`; `DynamicMethodMatcherPointcut` has `isRuntime() == true`. When implementing `MethodMatcher` directly, all three methods must be consistent.

**Confusing method signature with actual arguments.** `method.getParameterTypes()` gives the declared type (`int.class`), whereas `args` holds the values of a specific call (e.g., `Integer(100)`, `Integer(1500)`). Static checks cannot distinguish between these two values.

**Assuming returning `false` from a matcher stops the transaction/target.** Returning `false` only skips applying the corresponding advice. To reject invalid data, you must perform validation/authorization or throw an exception in the appropriate business layer; do not rely solely on a matcher to block execution.

**Failing to filter in the static step.** If you only need `transfer`, check the name/signature in the two-parameter overload. Letting the static overload return `true` for every method forces Spring to execute dynamic checks far more often than necessary.

**Relying on how many times the static overload is called.** Spring may evaluate static matching during proxy creation or method resolution and use caching; implementation details and call counts can vary. Rely only on the contract that runtime checks require a static match and `isRuntime == true`.

**Forgetting advice ordering.** Runtime matching is performed right before its corresponding advice; earlier advices in the interceptor chain may have already run. If an earlier interceptor mutates arguments, chain ordering can affect observed values. Therefore, avoid writing matchers with side effects or reliance on unguaranteed call ordering.

**Forgetting proxy boundaries.** External calls through the proxy are handled by Spring AOP. A self-invocation like `this.transfer(...)` inside the same target typically bypasses the proxy; the matcher will not be used for that internal call.

## 6. Choosing Static, Dynamic, or Spring AspectJ Expressions?

- Choose **`StaticMethodMatcherPointcut`** for conditions based on name, signature, class, or stable metadata. This is the preferred direction whenever input values are not needed.
- Choose **`DynamicMethodMatcherPointcut`** when you need to *decide whether to run advice* based on per-call arguments, such as an amount exceeding a threshold.
- For common pointcut criteria, AspectJ expressions supported by Spring AOP (such as `execution(...)`, `within(...)`, `args(...)`) are often more concise. `args(...)` can bind/check argument types at runtime, though it does not directly provide syntax for numeric comparisons like `amount >= 1000`; in such cases you can check inside the advice or use a custom dynamic `MethodMatcher`.

Do not build a dynamic matcher just to replace a condition that can be completely solved with static matching.

## 7. Self-Check Questions

1. `matches(Method, Class) == false`, `isRuntime() == true`: does the `args` overload run? **No**; the static step already excluded the method.
2. `isRuntime() == false`: can you distinguish two calls with the same signature but different amounts? **No**, not with that MethodMatcher.
3. Dynamic matcher returns `false` when amount=100: does the target still run? **Yes**, provided other components in the chain do not block it.
4. You only need to audit every `transfer`: which class should you use? **`StaticMethodMatcherPointcut`**, because the criteria do not depend on args.
5. For `transfer(String, int)`, how do `getParameterTypes()[1]` and `args[1]` differ? **Declared type `int.class`** versus **boxed `Integer` value at call time**.

## Official Spring Documentation

- [Spring Reference — Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html)
- [Spring 6.1 — MethodMatcher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/aop/MethodMatcher.html)
- [Spring 6.1 — StaticMethodMatcherPointcut](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/aop/support/StaticMethodMatcherPointcut.html)
- [Spring 6.1 — DynamicMethodMatcherPointcut](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/aop/support/DynamicMethodMatcherPointcut.html)