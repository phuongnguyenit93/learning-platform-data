# Warming Up JIT Without Creating Real Business Transactions or Data

When a Java application starts up, many methods may initially run via the interpreter. The JVM collects information about call frequency, data types, and branch behavior. Methods that are hot enough can be compiled by the JIT compiler into machine code to run faster. The process of proactively invoking critical code paths before serving real requests is often called warmup.

With CRaC, an application can perform warmup before creating a checkpoint so that the JVM state is already prepared. However, warmup needs to be separated from real business operations. The goal is to warm up the necessary computations and processing paths using synthetic data, in-memory adapters, or fake collaborators, without creating orders, without writing customer data, without deducting inventory, and without opening real database transactions.

## 1. What Does JIT Warmup Do?

The JVM does not necessarily compile all methods as soon as the application starts. With HotSpot and JVMs that have tiered compilation, a method is typically executed first, after which the runtime collects profiles and decides whether to compile it.

Overview of the process:

~~~text
Application starts
       |
       v
Class loading and initialization
       |
       v
Method runs via interpreter
       |
       v
JVM collects invocation / back-edge counters
and profiles on data types, branches, call sites
       |
       v
Method becomes sufficiently hot
       |
       v
JIT compiler generates machine code
       |
       v
Subsequent calls can run using compiled code
~~~

JIT can optimize many characteristics of code:

- Inline small or frequently called methods.
- Optimize branches based on collected profiles.
- Optimize object accesses and type checks.
- Eliminate certain unnecessary computations or branches.
- Compile loops or hot code within loops.

The JVM can use multiple compilation tiers. Therefore, a method already compiled at an initial tier can still be recompiled with higher optimization when the runtime has more profile data. Some optimization assumptions can also become invalidated, causing the method to deoptimize and fall back to the interpreter or be recompiled.

Warmup is not synonymous with calling every method once. A single call is usually only enough to execute code and possibly load classes; it does not guarantee the method has reached the JIT compilation threshold.

## 2. Distinguishing Class Loading, Initialization, and JIT Compilation

These three activities are related but not identical:

| Activity | Meaning | Example |
|---|---|---|
| Class loading | The JVM locates and loads the class definition | Loading PricingService from the classpath |
| Class initialization | Runs static initializers and initializes static fields | Creating a cache or reading a system property in a static block |
| JIT compilation | Compiles hot methods into machine code | Compiling PricingService.quote after many invocations |

Calling Class.forName() alone can cause a class to be loaded and initialized, but does not warm up all methods of the class. Conversely, calling a method many times can trigger the necessary steps and supply profiles for JIT.

Class initialization can also create side effects. If a static initializer opens connections, registers listeners, or reads secrets, warmup that loads classes can trigger those actions. Therefore, components being warmed up need safe and controllable initialization.

## 3. Identifying Which Code Needs Warmup

Do not try to warm up every class and method in the application. Start with code paths that have a clear impact on latency after receiving traffic:

- Compute-intensive or frequently called business rules.
- Request data transformation and validation.
- Mapping, serialization, and deserialization.
- Filters, parsers, or algorithms used on the main request path.
- Common processing branches of a use case.

You can use profiles from testing environments or production observations to identify hot code paths. When no profiles are available, select several representative use cases and common input types.

Warmup should represent real data shapes and execution patterns:

- Include multiple different input values instead of repeating a single constant.
- Traverse common business branches.
- Use realistic implementation types at call sites if polymorphic code needs to be warmed up.
- Avoid calling only a rare code path and concluding the entire use case is warm.

JIT optimizes based on profiles. If warmup only uses one implementation type while real traffic uses multiple different types, optimization assumptions may no longer hold and the JVM may deoptimize or recompile.

## 4. Separating Computation Logic from Transactions and Side Effects

An effective way to warm up without creating real transactions is to separate pure logic from the persistence orchestration and side-effect layer.

For example, order placement processing may consist of:

~~~text
HTTP request
    |
    v
Application service (@Transactional)
    |
    +----> Read data from repository
    |
    +----> Call payment gateway
    |
    +----> Write order and inventory
    |
    v
Commit transaction

Warmup path:
Warmup runner
    |
    v
Domain / computation service
    |
    +----> Synthetic input
    |
    +----> In-memory catalog or fake collaborator
    |
    v
Synthetic result, no business writes
~~~

Warmup directly invokes the computation part needing optimization, without calling the application service that opens transactions, without calling real repositories, and without calling real payment or message gateways.

If a method has the **@Transactional** annotation, calling that method can trigger the transaction manager even when the code inside does not write data. **@Transactional(readOnly = true)** can also still open a transaction and session; the readOnly attribute is not a general guarantee that there will be no side effects. Therefore, transaction rollback should not be used as a default way to warm up JIT.

Rollback also cannot undo all side effects. Sequences may have already incremented, messages may have been sent, emails may have been dispatched, audit logs may have been written, or an external service may have processed a request. The safe approach is not to invoke side-effecting adapters in the warmup path.

## 5. Example: Warming Up Quote Logic with Synthetic Data

The following example uses a PricingService containing pricing logic. Catalog is an interface; warmup uses an in-memory catalog with synthetic product codes. This code path does not use JDBC, a transaction manager, a message broker, or a payment gateway.

~~~java
import java.util.List;
import java.util.Map;

public final class JitWarmupExample {
    record Product(String sku, int unitPriceCents, int taxBasisPoints) {}

    record QuoteRequest(String sku, int quantity, String region) {}

    record Quote(String sku, int quantity, long subtotalCents,
                 long taxCents, long totalCents) {}

    interface Catalog {
        Product find(String sku);
    }

    static final class PricingService {
        private final Catalog catalog;

        PricingService(Catalog catalog) {
            this.catalog = catalog;
        }

        Quote quote(QuoteRequest request) {
            if (request.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "Quantity must be positive");
            }

            Product product = catalog.find(request.sku());
            if (product == null) {
                throw new IllegalArgumentException("Unknown SKU");
            }

            long subtotal = (long) product.unitPriceCents()
                    * request.quantity();
            long tax = (subtotal * product.taxBasisPoints() + 5_000L)
                    / 10_000L;
            long total = subtotal + tax;

            return new Quote(
                    product.sku(),
                    request.quantity(),
                    subtotal,
                    tax,
                    total);
        }
    }

    static final class WarmupRunner {
        private static volatile long resultSink;

        long warm(PricingService pricingService) {
            List<QuoteRequest> samples = List.of(
                    new QuoteRequest("SYNTH-A", 1, "VN"),
                    new QuoteRequest("SYNTH-B", 3, "VN"),
                    new QuoteRequest("SYNTH-A", 5, "SG"),
                    new QuoteRequest("SYNTH-C", 2, "SG"));

            long checksum = 0;
            int rounds = 20_000; // Illustrative value only.

            for (int i = 0; i < rounds; i++) {
                Quote quote = pricingService.quote(
                        samples.get(i % samples.size()));
                checksum = checksum * 31 + quote.totalCents();
            }

            resultSink = checksum;
            return resultSink;
        }
    }

    public static void main(String[] args) {
        Map<String, Product> syntheticProducts = Map.of(
                "SYNTH-A", new Product("SYNTH-A", 12_500, 800),
                "SYNTH-B", new Product("SYNTH-B", 7_900, 500),
                "SYNTH-C", new Product("SYNTH-C", 21_000, 1_000));

        Catalog inMemoryCatalog = syntheticProducts::get;
        PricingService pricingService =
                new PricingService(inMemoryCatalog);

        long checksum = new WarmupRunner().warm(pricingService);
        System.out.println("Warmup completed: " + checksum);
    }
}
~~~

The example illustrates several principles:

- Warmup calls the exact quote method containing the logic to be warmed up.
- The requests and SKUs are all synthetic data, not representing real customers or orders.
- Catalog only reads from an in-memory Map.
- There is no repository writing data, database transaction, payment, or message.
- Results are fed into a checksum and a volatile field so computation results are observable, avoiding turning warmup into a loop that has no effect at all.

The iteration count of 20,000 is only an illustrative number, not a guaranteed JIT threshold. Compilation thresholds depend on the JVM, tiered compilation, profiles, method size, and runtime flags. Choose the iteration count according to the startup budget and measure on the exact deployment runtime.

In a real application, PricingService can be a domain service used by an application service. The real application service still opens transactions and calls repositories when handling requests. Warmup only constructs PricingService with an in-memory collaborator and invokes the pure computation part.

## 6. Warming Up Multiple Branches While Keeping Data Synthetic

If a method has multiple branches, warmup needs to traverse the critical ones. For example:

- Products belonging to multiple tax groups.
- Quantities in different ranges.
- Valid currencies or regions.
- Discounted and non-discounted cases.
- Valid inputs and common errors if error-handling branches are important.

There is no need to create a massive dataset or one identical to production. You only need synthetic samples diverse enough for code to run through the necessary branches.

Avoid repeating the same immutable object with all identical values if real traffic has many input shapes. JIT may optimize based on an overly narrow profile. Use multiple synthetic samples representative of critical branches.

If a call site uses multiple implementations, such as multiple types of TaxPolicy or Serializer, representative implementations can be included in warmup. This helps profiles reflect realistic call patterns more closely. Only use implementations that do not create side effects and have a safe lifecycle.

## 7. What Warmup Should Not Call

To avoid creating real business transactions or data, avoid directly calling:

- Application services with **@Transactional** or other transaction boundaries.
- Real repositories that can INSERT, UPDATE, DELETE, or create audit records.
- Payment gateways, email services, SMS providers, or notification services.
- Message publishers or consumers processing real messages.
- APIs that create orders, make reservations, deduct inventory, provision accounts, or mutate customer state.
- Real schedulers that can trigger periodic jobs.
- External APIs with side effects even if the request is called for warmup purposes.

Do not assume that using a request carrying a warmup=true header is sufficient to avoid side effects. Every adapter must have an explicit policy so it does not send data externally or write business data. A better approach is to use separate dependencies during warmup, configured with in-memory implementations or no-op implementations.

If it is necessary to initialize a library's classes or parsers, determine whether static initializers and constructors open resources, register listeners, send telemetry, or read secrets. Class loading can trigger initialization code; warmup needs to account for this.

## 8. Why Is Rollback Not a Safe Warmup Strategy?

An approach that easily comes to mind is running the real use case inside a transaction and rolling back after warmup. This approach does not guarantee the application will not create real data or side effects:

- Database sequences/identities may still increment even if the transaction rolls back.
- Triggers or extensions may call external systems.
- Messages or emails may have already been sent before rollback.
- Some storage systems or APIs do not support transaction rollback.
- Caches, metrics, audit logs, or external counters may have already changed.
- Real transactions consume connections, locks, and database resources.

Even when the database rolls back completely, opening a transaction still violates the goal of warmup without creating real transactions. Therefore, warmup should run on logic that does not require transactions or use fake adapters.

## 9. Combining JIT Warmup with CRaC Checkpoint

A startup workflow may consist of:

~~~text
Initialize JVM and framework
       |
       v
Load classes and create required beans
       |
       v
Initialize safe dependencies
       |
       v
Run JIT warmup with synthetic data
       |
       v
Wait for warmup to finish and close temporary executors
       |
       v
Bring application to quiescent state
       |
       v
Create CRaC checkpoint
       |
       v
Restore on deployment
       |
       v
Verify dependencies and readiness
       |
       v
Receive real traffic
~~~

Warmup needs to complete before creating a checkpoint. Do not let warmup executors, virtual threads, or background tasks continue running without an explicit lifecycle policy. If warmup opens temporary resources, close them before checkpoint or let a Resource own and manage them properly according to library guidelines.

The JVM can preserve compiled JIT state in the checkpoint image, but you should not assume every compiled method will always retain its machine code or never need recompilation. The runtime can deoptimize or recompile when profiles and optimization assumptions change. Actual behavior depends on the JDK, vendor, CPU architecture, flags, and CRaC implementation.

Therefore, pre-checkpoint warmup is a way to prepare the runtime, not a commitment that every request after restore will run in maximum optimized state from the very start.

## 10. Warmup Does Not Replace Dependency Recovery

Warmup with fake adapters only warms up the code that was called. It does not warm up the database server, real connection pools, TLS handshakes, DNS caches, broker connections, or remote services.

For example, calling PricingService with an in-memory Catalog can warm up pricing calculation logic, but does not compile or initialize the entire JDBC path of the real repository. If the goal requires checking database connectivity, that is a separate preflight step and may open connections or transactions depending on the driver/database.

Separate the two goals:

- **Safe JIT warmup:** invoke the logic needing optimization with synthetic data and side-effect-free adapters.
- **Dependency readiness:** verify connections to external services according to allowed policy. This step must be designed separately, have restricted permissions, and not be confused with transaction-free warmup.

After restore, dependencies need to be verified according to their lifecycle. A hot JIT method does not prove the database connection is still valid or credentials are still in effect.

## 11. Measuring Warmup and Observing JIT

Warmup should be measured by duration, CPU usage, invocation counts, and latency of the code path after warmup. Do not pick an iteration count merely because a fixed number seems large enough.

With HotSpot, the diagnostic option **-XX:+PrintCompilation** can be used in testing environments to observe compilation events. Output and diagnostic options may differ across JVMs and releases. Do not enable this verbose logging in production without evaluating the impact.

JFR and JDK profiling tools can help observe compilation activity and CPU. Use a configuration appropriate for the target JDK to identify which methods are actually compiled and when compilation occurs.

When measuring, distinguish between:

- Class loading/initialization time.
- Warmup and compilation time.
- GC time incurred due to synthetic data.
- Latency of the method after warmup.
- Latency after restore and number of deoptimizations/recompilations if any.

A benchmark needs to control the environment and data. If you need to seriously compare algorithm performance, use JMH in a dedicated benchmark environment; do not take a simple startup loop as an accurate benchmark result.

## 12. Common Mistakes

**Calling real application services to warm up.**

The method may open transactions, write data, or call external systems. Separate pure logic and invoke that part directly with fake collaborators.

**Using a transaction and rolling back.**

Rollback does not undo all side effects and still creates real transactions. Do not use this approach when the goal is transaction-free warmup.

**Using production data.**

Real customer or order data is not needed to warm up JIT. Create a synthetic dataset with representative shapes and no personal information.

**Calling a method only once.**

A single call does not guarantee the method reaches the JIT threshold. Choose the invocation count based on measurement and startup budget.

**Repeating a single fixed input.**

JIT may optimize based on an overly narrow profile. Use multiple synthetic samples representative of critical branches.

**Over-warming.**

Prolonged warmup slows startup, increases CPU, allocation, and GC. Only warm up code paths with clear value.

**Assuming warmup warms up every library and dependency.**

Fake adapters do not invoke code of real drivers or remote clients. Logic warmup and dependency checking are two different steps.

**Letting warmup tasks run across checkpoint.**

Still-running tasks can hold temporary objects, threads, or resources. Wait for completion and close executors before checkpointing.

**Assuming JIT code will never be recompiled after restore.**

The JVM can deoptimize or recompile. Measure on the exact JDK, vendor, architecture, and CRaC configuration.

## 13. Safe Implementation Workflow

A practical workflow:

1. Select methods and use cases that impact latency.
2. Separate computation logic from transactions, persistence, and side effects.
3. Create synthetic inputs with multiple representative values and branches.
4. Use in-memory or no-op adapters for all dependencies not allowed to create side effects.
5. Call the code needing warmup directly, without calling facades that open transactions.
6. Measure warmup time and post-warmup latency to tune the iteration count.
7. Ensure all warmup tasks complete and temporary executors are closed.
8. Bring the application to a quiescent state and then create the checkpoint.
9. After restore, verify dependencies, configuration, and readiness before receiving traffic.
10. Test checkpoint/restore multiple times to confirm no unexpected business data, transactions, messages, or background tasks are created.

## 14. Conclusion

JIT warmup helps the JVM collect profiles and compile hot methods before the application serves real traffic. In CRaC applications, warmup can be performed before checkpoint to prepare critical code paths.

For warmup not to create real business transactions or data, separate computation logic from transaction boundaries and side-effecting adapters. Use synthetic data, in-memory collaborators, or no-op adapters; do not call real application services, do not rely on rollback, and do not send requests to business systems. Warmup needs to finish before checkpoint, while the ability to retain JIT code after restore must be verified on the exact deployment JDK and CRaC runtime.
