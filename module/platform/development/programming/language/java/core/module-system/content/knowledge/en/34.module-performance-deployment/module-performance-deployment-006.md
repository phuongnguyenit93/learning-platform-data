# Impact of Reflection and Deep Access

## 1. Where Does Reflection Affect Performance?

Reflection allows a program to inspect classes, fields, methods, and constructors and invoke members when the target name or type is only determined at runtime. This mechanism is very useful for frameworks, dependency injection, ORMs, serialization, plugins, and dynamic configuration systems.

In return, a reflection-based execution flow can incur costs across several stages:

- **Discovery:** finding classes, scanning packages, or reading metadata.
- **Lookup:** obtaining objects describing classes, fields, methods, or constructors.
- **Access check:** checking access permissions under Java language access rules and module boundaries.
- **Invocation:** calling a method or constructor through the reflection API.
- **Conversion and boxing:** type conversion, boxing primitives, or handling argument arrays.
- **Metadata and caching:** storing reflected objects, annotations, or mapping information for reuse.

You should not conclude that every reflection call is slower than a normal Java call by the same fixed factor. Cost depends on the operation type, JDK, how the JVM optimizes, call frequency, caching strategy, and actual workload. A reflection operation that runs once at application startup may be negligible; the same operation inside a loop processing millions of requests can become a hot spot.

It is also important to separate framework initialization cost from per-request processing cost. Package scanning, reading annotations, and building metadata typically happen at startup or when creating a registry. Invocation can occur continuously at runtime. These two kinds of cost must be measured and optimized separately.

## 2. Reflection Steps That Can Create Overhead

### Discovery and Lookup

For example, finding a method by name:

~~~java
Method method = Customer.class.getMethod(
    "displayName"
);
~~~

Searching metadata can take more work than holding a previously looked-up method reference. If code performs **getMethod** or **getDeclaredMethod** repeatedly during every processing step, the lookup portion can add unnecessary cost.

If the class structure is stable, look it up once when building metadata or a registry and reuse the **Method**, **Field**, or **Constructor** object. If a framework supports many different classes, cache by class and by the kind of metadata needed.

### Invocation

Calling a method via reflection:

~~~java
Method method = Customer.class.getMethod("name");
Object result = method.invoke(customer);
~~~

A **Method.invoke** call has several characteristics different from a direct method call:

- Arguments are passed via an array or list of Object arguments.
- Primitives may require boxing when passing through Object-based APIs.
- The return value comes back as Object, requiring a cast or unboxing if needed.
- Exceptions from the invoked method are typically wrapped in **InvocationTargetException**.
- The JVM must process the corresponding metadata and access rules.

A direct call:

~~~java
String result = customer.name();
~~~

usually gives the compiler and JIT more type information. However, the actual performance gap also depends on whether the JVM can optimize the reflection call site and how the application uses reflected objects.

### Constructor and Field Access

Creating an object via reflection:

~~~java
Constructor<Customer> constructor =
    Customer.class.getConstructor(String.class);

Customer customer = constructor.newInstance("An");
~~~

Reading a field:

~~~java
Field field = Customer.class.getDeclaredField("name");
Object value = field.get(customer);
~~~

Writing a field:

~~~java
field.set(customer, "Binh");
~~~

These operations are useful for frameworks that instantiate objects or map data. If they are called many times, consider caching constructors/fields and avoiding repeated lookup steps. For statically typed data on hot paths, public APIs or strongly typed factories are usually easier to optimize.

## 3. Reflection on Modern JDK Versions

The JVM's reflection implementation has evolved over time. Starting in JDK 18, JEP 416 replaced the older core reflection implementation based on bytecode-generated accessors with an implementation built on method handles.

This means performance conclusions drawn from an older JDK may no longer hold on newer JDKs. Some reflection cases can be optimized better by the JIT, especially when **Method**, **Constructor**, or **Field** objects are kept stable and can be treated as constants at the call site.

Results still depend on usage:

- Reflection objects looked up once and stored in stable fields create favorable conditions for JIT optimization.
- Continuous dynamic lookup, changing metadata, or complex polymorphic call sites can limit optimization.
- Boxing, argument arrays, type conversions, and exceptions can still create overhead.
- Reflection accessing private members or crossing module boundaries carries additional access-check requirements.

Therefore, when optimizing, measure on the exact JDK used in production. Do not take an old benchmark as a conclusion for all Java versions.

## 4. Deep Access and Access-Check Costs

Deep reflection often uses **setAccessible(true)** or **trySetAccessible()** to access non-public members:

~~~java
Field field = Customer.class.getDeclaredField("email");

if (field.trySetAccessible()) {
    Object email = field.get(customer);
}
~~~

The JVM must enforce Java and JPMS access rules. A package in a named module may be exported for public type access yet not opened for deep reflection. If the package is not opened appropriately, **trySetAccessible()** may return false or **setAccessible(true)** may throw **InaccessibleObjectException**.

Deep access can impact design and performance in several ways:

- Frameworks must check access permissions when initializing metadata.
- Calling the access-enabling operation repeatedly performs unnecessary duplicate work.
- Access may be restricted by module descriptors or runtime options.
- Broadly opening packages weakens encapsulation and turns internal implementations into framework dependency points.

If a framework needs deep access, perform the check and configure accessibility once when creating metadata, then reuse the configured object. Do not call **setAccessible(true)** on the same field on every request.

### exports and opens Serve Different Roles

**exports** allows other modules to access public types in a package:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

**opens** allows deep reflection into a package:

~~~java
module com.example.model {
    opens com.example.model.entity
        to com.example.orm;
}
~~~

If temporary configuration is needed at launch, you can use:

~~~bash
java \
  --add-opens com.example.model/com.example.model.entity=com.example.orm \
  -m com.example.app/com.example.app.Main
~~~

These directives handle access permissions, not reflection acceleration. Opening a package does not make **Method.invoke** faster by itself; the purpose is to permit reflection operations otherwise blocked by JPMS. Open only the exact packages to the exact modules that need them.

## 5. Caching Metadata to Avoid Repeated Lookups

A common optimization is storing looked-up metadata instead of searching again on every call.

Example caching a method per class:

~~~java
private static final Map<Class<?>, Method> NAME_METHODS =
    new ConcurrentHashMap<>();

static Method nameMethod(Class<?> type) {
    return NAME_METHODS.computeIfAbsent(type, key -> {
        try {
            return key.getMethod("name");
        } catch (NoSuchMethodException e) {
            throw new IllegalArgumentException(e);
        }
    });
}
~~~

When used:

~~~java
Method method = nameMethod(customer.getClass());
Object name = method.invoke(customer);
~~~

Caching can reduce repeated lookups, but its lifecycle and memory also need management:

- Do not cache every class ever encountered if the class set is unbounded.
- A static map holding strong references to Class objects can prevent class loaders from being reclaimed.
- Applications supporting hot reload or plugins that unload modules/class loaders must have a cache cleanup strategy.
- Caches should store only metadata actually needed, avoiding holding excessive annotations, MethodHandles, or auxiliary objects.
- If multiple threads initialize metadata concurrently, use appropriate synchronization or concurrent caching.

For metadata tied to each class, **ClassValue** is often worth considering:

~~~java
private static final ClassValue<Method> NAME_METHOD =
    new ClassValue<>() {
        @Override
        protected Method computeValue(Class<?> type) {
            try {
                return type.getMethod("name");
            } catch (NoSuchMethodException e) {
                throw new IllegalArgumentException(e);
            }
        }
    };
~~~

**ClassValue** ties data to the lifetime of the Class and suits per-class metadata. Even so, still avoid letting metadata hold references beyond the intended lifecycle or creating reference chains that retain another class loader.

## 6. MethodHandles as an Alternative

**MethodHandles** provide a way to invoke methods and access fields through a typed handle object. This API is often suitable when frameworks want to construct typed call sites or reuse a looked-up operation.

Example looking up a public method:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle getter = lookup.findVirtual(
    Customer.class,
    "name",
    MethodType.methodType(String.class)
);

String name = (String) getter.invokeExact(customer);
~~~

Compared to **Method.invoke**, MethodHandle has several differences:

- MethodHandle carries parameter types and return type in MethodType.
- Access permissions are checked when creating the handle.
- Handles can be combined, transformed, and reused.
- **invokeExact** requires the call-site types to match the handle's type exactly.
- Errors and type conversions follow different rules from reflection.

For deep access, you can use **privateLookupIn** when permitted by the module/package:

~~~java
MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(
        Customer.class,
        MethodHandles.lookup()
    );
~~~

If the package is not opened to the caller module, creating a private lookup can fail. MethodHandles do not bypass JPMS boundaries.

Do not rewrite all reflection to MethodHandles merely because you heard they are faster. Measure on real workloads. For some call sites, the JIT optimizes MethodHandle very well; in other cases, type conversion cost, dynamic lookup, or framework logic still dominates.

## 7. Reducing Cost at the Design Layer

If reflection sits on a hot path, consider design changes:

- **Direct API calls:** if types and methods are known at compile time, direct calls are usually clearer and easier to optimize.
- **Interface dispatch:** define an interface and call through the interface instead of looking up methods by name every time.
- **Registered factories or constructors:** instantiate objects through a known factory instead of scanning constructors repeatedly.
- **ServiceLoader:** use SPI for declared plugin providers instead of scanning all classes for implementations.
- **Annotation processing:** shift part of metadata discovery to compile time to reduce startup scanning.
- **Code generation:** generate mappers, serializers, or adapters at build time if the workload demands high throughput and structures are stable.
- **Metadata caching:** look up once and reuse within a reasonable lifecycle.

Interface example:

~~~java
public interface NameProvider {
    String name(Customer customer);
}
~~~

The application holds an implementation:

~~~java
NameProvider provider = new DefaultNameProvider();
String name = provider.name(customer);
~~~

If the goal is simply to retrieve a customer's name, an interface can be much simpler than looking up a method by string and invoking reflection on every call. However, for frameworks that must support unknown classes ahead of time, reflection remains valuable; optimize where and how often it is used.

## 8. How Reflection Affects Startup and Throughput

Not all applications are affected in the same way.

**Startup time** can increase due to:

- Scanning packages and listing classes.
- Reading annotations or generic metadata.
- Building registries for thousands of classes.
- Looking up constructors, fields, and methods.
- Generating proxies, adapters, or ORM metadata.
- Loading classes and initializing frameworks.

**Throughput or latency** can be affected when:

- Reflection invocations sit inside request-processing loops.
- Frameworks map millions of fields or properties.
- Serialization/deserialization calls dynamic accessors for every object.
- ORMs read/write fields via reflection on every operation.
- Every call performs method lookup or accessibility checks again.

An application may start slowly yet run fast at runtime if metadata is prebuilt and well cached. Conversely, a light startup where each request dynamically scans or looks up metadata can cause high latency. Measure both phases independently.

## 9. Measuring Performance Properly with JMH

Do not use a simple loop and **System.nanoTime()** to conclude how many times slower reflection is. JIT compilation, dead-code elimination, warmup, class loading, and CPU scheduling can distort results.

Use JMH to benchmark equivalent cases:

1. Direct call.
2. Reflection lookup on every call.
3. Reflection with a cached Method.
4. Cached MethodHandle.
5. Factory or interface dispatch if applicable.

Skeleton benchmark example:

~~~java
@State(Scope.Thread)
public class ReflectionBenchmark {
    private final Customer customer = new Customer("An");
    private Method cachedMethod;

    @Setup
    public void setup() throws Exception {
        cachedMethod = Customer.class.getMethod("name");
    }

    @Benchmark
    public String direct() {
        return customer.name();
    }

    @Benchmark
    public Object reflectionCached() throws Exception {
        return cachedMethod.invoke(customer);
    }

    @Benchmark
    public Object reflectionLookupEachTime() throws Exception {
        Method method =
            Customer.class.getMethod("name");
        return method.invoke(customer);
    }
}
~~~

This is only an illustrative skeleton. In real benchmarks, ensure cases return the same result and perform equivalent work. You can add a MethodHandle benchmark, making sure to configure MethodType and return types properly.

Measurement principles:

- Use warmup and multiple measurement iterations.
- Run multiple forks to reduce effects from prior JVM state.
- Prevent results from being eliminated; return results or use Blackhole.
- Separate lookup from invocation if you want to know the cost of each step.
- Measure both throughput and latency if the application cares about both.
- Use the same JDK, flags, CPU, and workload close to production.
- Measure startup separately with appropriate tools; do not infer startup from JMH microbenchmarks.
- Run multiple times and report variance, not just the single best number.

If the goal is to reduce startup time, measure the number of classes scanned, registry creation time, and framework initialization time. If the goal is to increase throughput, measure invocations per request, allocations, CPU profile, and percentile latencies.

## 10. Memory Costs to Watch

Reflection does not affect CPU alone. Frameworks can create and retain many metadata objects:

- Method, Field, and Constructor instances.
- Annotation proxies and annotation data.
- Argument arrays and boxed objects.
- Per-class registry maps.
- MethodHandle and lookup objects.
- Dynamically generated proxy classes or adapters.

Caching can reduce CPU while increasing memory. If a cache is unbounded, a growing number of classes/plugins can bloat the heap. If a cache retains classes from a plugin class loader, the class loader may fail to be reclaimed after the plugin stops.

When designing a cache:

1. Identify reusable data and its lifetime.
2. Associate per-Class metadata using ClassValue when appropriate.
3. Provide a mechanism to clear registries when a plugin or sub-application is unloaded.
4. Do not retain class loaders, Methods, or MethodHandles longer than necessary.
5. Monitor heap, loaded class count, and class loaders when the application supports reloading.

Do not optimize CPU with an unbounded cache. Choose a cache policy aligned with class and plugin lifecycles.

## 11. Deep Access and Security

Deep reflection can increase the risk of depending on internal implementations. When a framework accesses private fields or unexported packages, changing class internals can break the application even if the public API has not changed.

Several principles:

- Prefer constructors, accessors, or public APIs.
- Open packages using **opens ... to module** instead of opening the entire module when possible.
- Avoid opening broad JDK internal packages just to keep legacy libraries running.
- Upgrade frameworks to versions supporting JPMS and the target JDK.
- Handle **InaccessibleObjectException** explicitly rather than silently ignoring it.
- Do not use reflection to bypass security rules or module boundaries beyond the intended scope.

**opens** does not make invocations faster. It only permits deep reflection within the declared scope. Broadening access permissions can hurt encapsulation and maintainability, so it should not be treated as a performance optimization.

## 12. Recommended Optimization Workflow

When discovering that reflection impacts performance, follow this sequence:

1. Determine whether the reflection operation sits on startup or on the request path.
2. Use a profiler to confirm whether lookup, invocation, access checks, or object allocation actually consumes time.
3. Look up metadata once and cache within an appropriate lifecycle scope.
4. Check whether caches retain unloaded class loaders or plugins.
5. Consider MethodHandles if you need typed, reusable call sites.
6. Replace reflection with public APIs, interfaces, factories, or code generation when structures are known.
7. If deep access is required, open only the right packages to the right modules and configure access once when building metadata.
8. Benchmark alternatives with JMH on the exact target JDK.
9. Run functional tests to verify frameworks, ORMs, serialization, and plugins still work.
10. Re-measure startup, throughput, latency, and memory on a production-like artifact.

Do not optimize a piece of reflection merely because it looks complex. If a profiler shows negligible cost, changes can make code harder to maintain without improving real-world experience.

## 13. Takeaways

- Reflection incurs costs in discovery, lookup, access checks, invocation, boxing, and metadata.
- Repeated lookups can often be reduced by caching Method, Field, or Constructor objects.
- JDK 18 and later use a method-handle-based core reflection implementation per JEP 416; benchmark on the target JDK.
- **exports** allows access to public types; **opens** allows deep reflection. Neither mechanism is a speed optimization.
- **MethodHandles** are typed and suit certain dynamic call sites, but are not automatically faster than every reflection usage.
- Caches must manage memory and class loader lifecycles, especially in plugin/hot-reload applications.
- Use JMH and profilers to separate lookup, invocation, startup, throughput, and latency.
- Only change design after confirming reflection is a real hot spot.

Reflection is an essential tool for building flexible frameworks. Good performance depends on placing discovery and lookup in the right phase, reusing metadata, limiting deep access, and measuring on the deployment JDK. When execution paths are stable, strongly typed APIs or build-time generated code can reduce dynamic work and make JVM optimization easier.
