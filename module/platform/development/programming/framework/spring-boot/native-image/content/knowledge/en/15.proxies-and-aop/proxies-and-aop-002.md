# Interface order and matching proxy metadata

## 1. Why does interface order matter?

Spring AOP often uses proxies to apply transactions, security, caching, logging, or other advice around method calls. With JDK dynamic proxies, a proxy is created from an interface list. This list not only tells the proxy which contracts it must implement; **the interface order is also part of the proxy configuration**.

In Java, two proxies created from the same set of interfaces in different orders can be two distinct proxy classes. This affects the metadata that GraalVM Native Image needs to know before building. If Spring AOT or the application registers proxy hints with an interface order that does not match the proxy actually created at runtime, Native Image may fail to find matching metadata for that interface combination.

In the **SPRING_BOOT_NATIVE_IMAGE** module, you need to understand how Spring AOT declares proxies and why it is necessary to preserve exact interface lists, order, and classloader assumptions. This lesson focuses on JDK dynamic proxies and the `RuntimeHints.proxies()` API.

## 2. A JDK dynamic proxy is defined by an interface list

The JDK provides `java.lang.reflect.Proxy` to create a proxy implementing one or more interfaces:

```java
public interface PaymentService {
    Receipt pay(String orderId);
}

public interface Auditable {
    String auditId();
}
```

Creating the proxy:

```java
Object proxy = Proxy.newProxyInstance(
        PaymentService.class.getClassLoader(),
        new Class<?>[] { PaymentService.class, Auditable.class },
        invocationHandler
);
```

The generated proxy class implements both `PaymentService` and `Auditable`. Interface method calls are forwarded to `InvocationHandler`.

The JDK requires the passed-in interfaces to satisfy validity conditions, including visibility through the classloader and having no method conflicts that cannot be resolved under proxy rules. An empty interface list, an invalid interface, or incompatible visibility can cause proxy creation to fail.

## 3. Interface order is part of proxy identity

Consider two lists:

```java
new Class<?>[] { PaymentService.class, Auditable.class }
new Class<?>[] { Auditable.class, PaymentService.class }
```

Both contain the same two interfaces, but in different order. JDK dynamic proxies treat interface order as part of the proxy class definition; therefore, the two orders can produce two different proxy classes. The order also affects the interface order returned when introspecting the proxy class.

This has a practical implication in Native Image: proxy metadata is registered for an ordered list of interfaces. A hint for `[PaymentService, Auditable]` must not be assumed to automatically cover `[Auditable, PaymentService]`.

| Interface list | Expected understanding |
|---|---|
| `[PaymentService, Auditable]` | One specific proxy combination |
| `[Auditable, PaymentService]` | A different combination due to changed order |
| `[PaymentService]` | A proxy implementing only one interface |
| `[PaymentService, Auditable, MetricsAware]` | A third combination, requiring metadata in exact order |

Do not arbitrarily reorder the interface list after metadata has been declared. If the application creates a proxy with one order, the registrar must register that exact order.

## 4. Spring ProxyHints and RuntimeHints.proxies()

Spring AOT provides an API to declare required JDK proxies:

```java
hints.proxies().registerJdkProxy(
        PaymentService.class,
        Auditable.class
);
```

The argument order is preserved in the proxy hint. When Native Image processes metadata, the interface combination is described in the exact declared order.

You can register this via `RuntimeHintsRegistrar`:

```java
final class PaymentProxyHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.proxies().registerJdkProxy(
                PaymentService.class,
                Auditable.class
        );
    }
}
```

Attach the registrar to Spring configuration:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentProxyHints.class)
class PaymentAotConfiguration {
}
```

Spring AOT collects proxy hints at build time. Declaring interfaces only in reflection hints does not replace proxy hints: proxy generation is a separate kind of runtime capability.

## 5. Metadata must match the proxy actually created

Suppose a library or Spring configuration creates a proxy as follows:

```java
Class<?>[] interfaces = {
    PaymentService.class,
    Auditable.class
};

Object proxy = Proxy.newProxyInstance(
        classLoader,
        interfaces,
        handler
);
```

The hint must reflect this accurately:

```java
hints.proxies().registerJdkProxy(
        PaymentService.class,
        Auditable.class
);
```

If another runtime path creates a proxy with the reversed order, you must either declare that combination as well or standardize proxy creation so everywhere uses the same order. Registering each interface individually is not equivalent to registering the proxy combination.

**Rule:** proxy metadata describes an ordered proxy interface set, not an unordered set of interfaces that can be combined arbitrarily.

## 6. Why is a proxy hint not the same as a reflection hint?

Reflection hints describe classes/members accessed via Java reflection; proxy hints describe interface combinations needed to generate a JDK dynamic proxy.

| Need | RuntimeHints API |
|---|---|
| Invoke constructor via reflection | `hints.reflection()` |
| Invoke method via reflection | `hints.reflection()` |
| Access field via reflection | `hints.reflection()` |
| Create JDK dynamic proxy from interfaces | `hints.proxies().registerJdkProxy(...)` |
| Read classpath resource | `hints.resources()` |
| Access type from JNI | `hints.jni()` |

An application may need both reflection and proxy hints. For example, a framework creates a JDK proxy for a service interface while also using reflection to read annotations or call the implementation's constructor. Registering a proxy does not automatically register all reflection members of the target class.

## 7. Spring AOP example with an interface proxy

Consider a service:

```java
public interface OrderOperations {
    String submit(String orderId);
}

@Service
class OrderService implements OrderOperations {
    @Override
    public String submit(String orderId) {
        return "submitted:" + orderId;
    }
}
```

An aspect that logs invocations:

```java
@Aspect
@Component
class AuditAspect {

    @Around("execution(* com.example.OrderOperations.*(..))")
    Object audit(ProceedingJoinPoint joinPoint) throws Throwable {
        return joinPoint.proceed();
    }
}
```

When Spring AOP uses a JDK dynamic proxy, the proxy implements the `OrderOperations` interface. If the application also has an additional interface such as `Auditable`, the actual interface combination must be determined from how Spring creates the proxy and which advisors/introductions are configured.

Not every Spring AOP application needs hand-written proxy hints. Spring AOT and integration libraries can register the necessary metadata. Only add a registrar when there is a custom proxy combination or when diagnostics show metadata is missing.

## 8. Interface introductions and multiple advisors

Spring AOP can add interfaces to a proxy through introductions/advisors. In that case, the proxy implements not only the original business interface, but also the introduced interfaces.

For example, a proxy might need:

- `OrderOperations`: business contract.
- `Auditable`: contract for querying the audit id.
- `DecoratedObject`: contract added by the framework.

The final list depends on the proxy factory, target, and advisor configuration. When registering hints, base them on **the actual interface list of the final proxy**, not only by looking at the interfaces declared on the implementation class.

If there are multiple advisor variants producing different interface combinations, each JDK proxy combination must be inspected and registered accordingly. Alternatively, standardize the proxy configuration to reduce the number of variants.

## 9. Classloader and visibility are also part of proxy creation conditions

A JDK dynamic proxy is created through a classloader. The interfaces must be visible in that classloader context and satisfy visibility/module rules. Two interfaces with the same name loaded by different classloaders can still be two distinct `Class` objects.

When debugging proxies, inspect:

```java
for (Class<?> type : interfaces) {
    System.out.println(type.getName());
    System.out.println(type.getClassLoader());
    System.out.println(type.getModule());
}
```

With Native Image, classloader behavior can differ from JVM applications that use complex plugin classloaders. Native Image works best with a set of types and proxies determined before building. Do not expect to load new interfaces from plugins after the executable is created.

Proxy hints cannot fix invisible interfaces, invalid module access, or classloaders producing incompatible `Class` objects. Those Java requirements must still hold when creating the proxy.

## 10. Standardizing interface order when creating proxies

If the application creates proxies directly, keep the interface list in one place and use that same list for both the runtime factory and the hint registrar.

For example:

```java
final class ProxyContracts {

    static Class<?>[] paymentInterfaces() {
        return new Class<?>[] {
                PaymentService.class,
                Auditable.class
        };
    }
}
```

Runtime proxy factory:

```java
Proxy.newProxyInstance(
        PaymentService.class.getClassLoader(),
        ProxyContracts.paymentInterfaces(),
        handler
);
```

The registrar can call the same helper to register:

```java
hints.proxies().registerJdkProxy(
        ProxyContracts.paymentInterfaces()
);
```

Check the `registerJdkProxy` overload signature against your Spring Framework version; supported versions accept varargs interface classes. Ensure the helper returns only a stable list, independent of environment or runtime state.

If the interface list is built from non-fixed runtime configuration, you must determine every valid combination ahead of time and register each combination at build time, or change the design so the proxy interface set is stable.

## 11. Verifying the proxy interface list before registering hints

You can inspect the proxy class on the JVM:

```java
Class<?> proxyClass = proxy.getClass();

System.out.println(
        Arrays.toString(proxyClass.getInterfaces()));
```

Or assert it:

```java
assertThat(proxy.getClass().getInterfaces())
        .containsExactly(
                PaymentService.class,
                Auditable.class
        );
```

`containsExactly` verifies both content and order. `containsExactlyInAnyOrder` only verifies the set of elements, which is insufficient for checking proxy metadata that requires exact order.

For Spring-created proxies, you can retrieve the bean from `ApplicationContext` and check:

```java
Object bean = context.getBean(OrderOperations.class);
Class<?>[] interfaces = bean.getClass().getInterfaces();
```

A proxy may be wrapped in multiple layers or have framework-added interfaces; inspect the exact final object that your code uses. Do not assume the interface list consists solely of business interfaces.

## 12. Testing proxy RuntimeHints

Spring provides `RuntimeHintsPredicates` to test proxy hints. For example:

```java
@Test
void registersPaymentJdkProxy() {
    RuntimeHints hints = new RuntimeHints();

    new PaymentProxyHints().registerHints(
            hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.proxies()
            .forInterfaces(
                    PaymentService.class,
                    Auditable.class)
            .test(hints))
            .isTrue();
}
```

The predicate API may vary by Spring Framework version; check your project's Javadoc/IDE to use the exact method. The key thing to verify is the exact **combination and order** of interfaces.

A unit test only proves that the registrar records the metadata properly. It does not prove that Spring AOT collected the registrar or that the native executable creates the proxy successfully. You need to build native and run an integration test that creates that exact proxy in the binary.

## 13. Diagnosing proxy errors on Native Image

| Symptom | Possible cause | Resolution direction |
|---|---|---|
| Native fails to create JDK proxy | Missing proxy hint for interface combination | Register the actual interface combination |
| Hint has same interfaces but proxy still fails | Interface order differs | Compare lists using `containsExactly` |
| JVM creates proxy, native fails | Proxy created dynamically without AOT metadata | Check registrar and AOT output |
| Only one proxy bean fails | Advisor/introduction adds extra interfaces | Inspect the final proxy's interface list |
| Class visibility error | Interface not visible through classloader/module | Fix classloader/module configuration |
| Reflection on target fails | Missing separate reflection metadata | Register additional reflection hints |
| New plugin interface does not work | Interface only appears after build | Rebuild image or change plugin architecture |

When diagnosing, distinguish between proxy creation failures and target method invocation failures. Proxy metadata may be correct while the target method still fails due to reflection, access, or business logic.

## 14. Hands-on lab: two-interface proxy in a native image

**Context:** a Spring Boot application has `OrderOperations` and `Auditable`. A proxy factory creates a JDK proxy implementing both interfaces in a fixed order.

**Step 1 — Create interfaces.** Declare two interfaces with independent methods and an appropriate implementation.

**Step 2 — Create proxy on the JVM.** Use `Proxy.newProxyInstance` with the list `[OrderOperations, Auditable]`; verify the proxy class interfaces using `containsExactly`.

**Step 3 — Register RuntimeHints.** Write a `RuntimeHintsRegistrar` calling `hints.proxies().registerJdkProxy(OrderOperations.class, Auditable.class)`.

**Step 4 — Write unit tests.** Use `RuntimeHintsPredicates` to verify the exact interface combination and order.

**Step 5 — Create reversed-order variant.** Create the proxy `[Auditable, OrderOperations]`, confirm it is a different combination, and do not assume the initial hint covers this variant.

**Step 6 — Build native.** Run Spring AOT and GraalVM Native Image; verify that the registrar is collected.

**Step 7 — Run native integration test.** Create the proxy, invoke methods from both interfaces, and confirm behavior matches the JVM.

Completion criteria: proxy metadata matches the exact interface list and order; every valid variant is registered; the native executable creates and uses the proxy properly.

## 15. Conclusion

A JDK dynamic proxy is defined by an ordered list of interfaces. Therefore, **the interface order in `RuntimeHints.proxies().registerJdkProxy(...)` must match the order of the proxy actually created**. Registering individual interfaces or the same set of interfaces in a different order does not replace metadata for the required combination.

In Spring Boot Native Image, determine the final interface list after Spring AOP/advisors/introductions configure the proxy, keep the list consistent between registrar and runtime factory, verify with ordered assertions, and run native integration tests. Proxy hints are a separate part of `RuntimeHints` and must be combined with reflection hints when the target or framework also accesses members via reflection.
