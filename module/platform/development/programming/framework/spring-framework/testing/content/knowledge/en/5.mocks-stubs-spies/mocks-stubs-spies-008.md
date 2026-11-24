# Spies Calling Real Behavior and Side-Effect Risks During Setup

In Mockito, a spy is a test double that retains most of an object's real behavior. When an unstubbed method is called, a spy typically executes the real implementation. This is useful when you need to selectively replace a few behaviors in a legacy object or observe interactions while keeping the remaining processing intact.

However, executing real behavior introduces an easily overlooked risk: **the standard stubbing syntax `when(spy.method()).thenReturn(...)` calls the real method during test setup**. If that method writes to a database, sends an HTTP request, publishes a message, writes a file, sends email, or mutates shared state, side effects can occur before the Act phase of the test even begins.

With spies, you must understand when the real call occurs, choose the right stubbing API, and control external dependencies. This lesson focuses on that mechanism in the context of unit testing with Spring and Mockito.

## 1. How does a spy differ from a mock and a real object?

A mock normally returns configured values or defaults and records interactions. It does not run the real implementation of ordinary methods on its own. A spy preserves the object's real behavior; unstubbed methods execute as if calling the real object.

| Characteristic | Real object | Mock | Spy |
| --- | --- | --- | --- |
| Unstubbed methods | Runs real implementation | Does not run real implementation by default | Runs real implementation |
| Can stub methods | Not via Mockito | Yes | Yes |
| Can verify calls | Not directly with Mockito | Yes | Yes |
| Risk of side effects when calling methods | Yes | Usually not from mock implementation | Yes |
| Typical purpose | Test real behavior with controlled dependencies | Replace dependencies and verify interactions | Selectively override part of a real object's behavior |

A spy is usually created from an already instantiated object:

```java
InventoryService realService = new InventoryService(repository);
InventoryService spyService = Mockito.spy(realService);
```

Or using a static import:

```java
InventoryService spyService = spy(new InventoryService(repository));
```

Use the reference returned by `spy(...)` in the test. Mockito creates a spy whose initial state is taken from the passed object; a spy is not a proxy delegating every call back to the original instance. Therefore, do not keep both references and expect state changes on the original object to stay synchronized with the spy.

## 2. Why can `when(spy.method()).thenReturn(...)` cause side effects?

Java evaluates arguments before invoking the outer method. When writing:

```java
when(spyService.reserve("BOOK-1", 2)).thenReturn(true);
```

`spyService.reserve("BOOK-1", 2)` is invoked first so Mockito can record the call to stub. Because this is a spy, the real method can execute right during the setup step.

Suppose the service has the following implementation:

```java
class InventoryService {

    private final InventoryRepository repository;

    InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    public boolean reserve(String sku, int quantity) {
        Stock stock = repository.findBySku(sku).orElseThrow();

        if (stock.availableQuantity() < quantity) {
            return false;
        }

        stock.reserve(quantity);
        repository.save(stock);
        return true;
    }
}
```

If `repository` is a real database, the stubbing statement above can read and update real inventory right inside Arrange. If the data does not exist, it can even throw an exception before the test reaches Act. If the method sends a request to an external system, the test may accidentally create a real transaction.

This is a key difference between a mock and a spy: when stubbing a mock with `when(mock.method())`, the method's real implementation is not called normally; with a spy, the real method is called to produce the invocation to record.

## 3. Using `doReturn(...).when(spy)...` for safe stubbing

Mockito provides the `doReturn`, `doThrow`, `doAnswer`, `doNothing`, and `doCallRealMethod` APIs. The `doReturn(...).when(spy).method(...)` syntax configures a stub without running the method's real implementation during configuration.

Replace the risky example with:

```java
InventoryService spyService = spy(new InventoryService(repository));

doReturn(true)
    .when(spyService)
    .reserve("BOOK-1", 2);
```

Now, when another component calls `spyService.reserve("BOOK-1", 2)`, Mockito returns `true` per the stub. The real `reserve()` method neither runs at setup time nor runs for calls matching the stub.

Argument matchers can be used:

```java
doReturn(true)
    .when(spyService)
    .reserve(eq("BOOK-1"), anyInt());
```

When using matchers, every argument in the same call must follow Mockito's matcher rules. For example, `eq("BOOK-1")` paired with `anyInt()` is valid; do not mix matchers with literal values on other parameters.

`doReturn()` has the advantage of avoiding real method execution during stubbing, though it is less type-safe than `when(...).thenReturn(...)`: the compiler does not verify the return value type with the same strictness. Use it when needed to stub a spy or when `do...` stubbing syntax is appropriate.

## 4. Choosing a `do...` API by behavior type

Mockito's API family supports different stubbing modes:

| API | Purpose | When used with a spy |
| --- | --- | --- |
| `doReturn(value)` | Return a fixed value | Stub a value-returning method without running the real method during setup |
| `doThrow(exception)` | Throw an exception | Simulate a dependency or error branch without executing real behavior |
| `doAnswer(answer)` | Customize result based on invocation | Generate responses from arguments or update a test fixture |
| `doNothing()` | Do nothing for a `void` method | Prevent real methods from sending email, writing files, or performing side effects |
| `doCallRealMethod()` | Request calling the real implementation | Used when a mock needs to call a real method; on a spy, real methods already run by default if unstubbed |

### Stubbing a value-returning method

```java
doReturn(Optional.of(stock))
    .when(spyRepository)
    .findBySku("BOOK-1");
```

### Stubbing to throw an exception

```java
doThrow(new PaymentGatewayUnavailableException())
    .when(spyGateway)
    .charge(any(PaymentRequest.class));
```

### Stubbing a `void` method to block real side effects

```java
doNothing()
    .when(spyNotificationPort)
    .sendConfirmation(any(OrderConfirmation.class));
```

If a `void` method on a spy is not stubbed, its real implementation runs when the test calls it. `doNothing()` prevents sending real emails when the test only needs to observe the call.

### Generating responses based on parameters

```java
doAnswer(invocation -> {
    PaymentRequest request = invocation.getArgument(0);
    return PaymentResult.approved("test-payment-" + request.orderId());
}).when(spyGateway).charge(any(PaymentRequest.class));
```

`doAnswer()` is useful when the result must depend on input data. If only a fixed result is needed, `doReturn()` is usually easier to read.

## 5. Comparing both stubbing styles in the same example

Suppose `ReportService.loadReport()` reads data from a store and might touch a real system. Another test checks how `ReportService.export()` behaves when the report is not found.

```java
class ReportService {

    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    public Report loadReport(String id) {
        return repository.findById(id).orElseThrow();
    }

    public byte[] export(String id) {
        Report report = loadReport(id);
        return renderPdf(report);
    }

    private byte[] renderPdf(Report report) {
        // Generate PDF
        return new byte[0];
    }
}
```

Style prone to calling real code during setup:

```java
ReportService spyService = spy(new ReportService(realRepository));

when(spyService.loadReport("missing-report"))
    .thenThrow(new ReportNotFoundException());
```

Before Mockito registers the exception for later calls, the real `loadReport("missing-report")` already ran. It could query the database, fail at the repository, or depend on existing data.

Style that avoids the real call:

```java
ReportService spyService = spy(new ReportService(realRepository));

doThrow(new ReportNotFoundException())
    .when(spyService)
    .loadReport("missing-report");
```

When the test calls `export("missing-report")`, the internal `loadReport()` call on the spy is stubbed and throws the configured exception. Even so, this example also shows how spies can couple tests to a class's internal structure. If the goal is testing behavior when the repository lacks a report, a better design is usually creating a real `ReportService` with a mock repository returning `Optional.empty()`.

## 6. Spies on `void` methods and unwanted side effects

For `void` methods, `when(spy.method()).thenReturn(...)` syntax cannot be used. Mockito provides `doNothing()` or `doThrow()`.

Suppose we have a notification adapter:

```java
class EmailNotifier {

    public void send(String recipient, String subject) {
        // Call real SMTP or email provider
    }
}
```

If the test wants to observe the call without sending real email:

```java
EmailNotifier notifier = spy(new EmailNotifier());

doNothing()
    .when(notifier)
    .send(anyString(), anyString());

service.sendReceipt(notifier);

verify(notifier).send("customer@example.test", "Order receipt");
```

In this case, `doNothing()` blocks the email-sending implementation when the service calls the method. However, if the test's goal is verifying that the SMTP adapter itself sends the right request, do not stub that method; test the adapter separately using an SMTP sandbox or fake server.

For a `void` method that needs to simulate failure:

```java
doThrow(new NotificationUnavailableException())
    .when(notifier)
    .send(anyString(), anyString());
```

This lets you verify how the service handles notification delivery errors without opening a real connection.

## 7. Risk of side effects at spy creation time

Safety during stubbing does not eliminate all risks. To create a spy from an object, the real object must be instantiated first:

```java
EmailNotifier realNotifier = new EmailNotifier();
EmailNotifier spyNotifier = spy(realNotifier);
```

`EmailNotifier`'s constructor already executed before `spy()` was called. If the constructor opens sockets, spawns threads, reads environment configuration, creates files, or connects to a database, those side effects have already occurred. `doReturn()` only prevents a stubbed method's implementation from running during stubbing; it does not undo constructors or other prior actions.

Consider these points before creating a spy:

- Does the constructor perform I/O or initialize resources?
- Do injected dependencies point to real systems?
- Are there initialization methods like `@PostConstruct` that connect or write data?
- Can unstubbed methods call HTTP, databases, brokers, the filesystem, or cloud services?
- Does the object hold state shared across tests?

Prefer simple constructors, dependency injection, and dedicated I/O adapters. When testing logic, pass mocks or fakes for external dependencies. When testing adapters, set up a controlled test double environment.

## 8. Spies and object state

A spy invokes real implementations for unstubbed methods, so methods can mutate the spy's state. This can make tests depend on call ordering or state left over from setup.

Example:

```java
class Counter {
    private int value;

    public int incrementAndGet() {
        return ++value;
    }

    public int currentValue() {
        return value;
    }
}
```

If you write:

```java
Counter counter = spy(new Counter());
when(counter.incrementAndGet()).thenReturn(100);
```

the real `incrementAndGet()` executes during stub setup and increments `value` to 1. Afterward, matching calls return 100 without incrementing the value via real logic. Internal state is therefore no longer what the test might assume.

If the goal is stubbing this method without mutating state:

```java
Counter counter = spy(new Counter());
doReturn(100).when(counter).incrementAndGet();
```

When using spies, clearly track state before Arrange, after stubbing, and after Act. If a test needs a specific initial state, instantiate a new object per test or use explicit fixtures/resets. Do not rely on JUnit execution order for spy state to be preserved or refreshed.

## 9. Spies can invoke other methods inside real methods

A method on a spy can call multiple other methods on the same object or on dependencies. When the real method runs, those internal calls can also trigger side effects.

For example, `publishReport()` might call `loadReport()`, `render()`, `writeFile()`, and then `upload()`. When stubbing `when(spy.publishReport(id)).thenReturn(result)`, the entire real flow can execute during setup. A method that looks like pure computation might indirectly write files or call external services.

Therefore, before using `when(...)` on a spy, read the method's implementation and the methods it calls. Do not assume a method is safe solely from its name or return type.

If you need to stub a method to block a risky flow, use `doReturn`, `doThrow`, or `doNothing` as appropriate. If the method under test has too many internal branches and side effects, consider extracting I/O behind ports and testing the use case with mocks/fakes of those ports.

## 10. Is using a spy in unit tests actually necessary?

Spies are generally helpful in narrow situations:

- A legacy class has a couple of hard-to-replace methods that need temporary stubbing to test another branch.
- You need to observe calls to one method on a real object while keeping the behavior of remaining methods.
- Part of an implementation can safely run with controlled dependencies, while one specific method must be overridden.
- Gradually migrating a large class toward a ports-and-adapters architecture when everything cannot be extracted immediately.

A spy is rarely the first choice when testing business services. If a test wants to test the real `OrderService`, instantiate a real `OrderService` with mocks or fakes for the repository, payment port, and notification port. Then there is no need to spy on the service under test itself.

Preferred structure example:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    @Mock
    PaymentPort payment;

    @Mock
    NotificationPort notifications;

    private OrderService service;

    @BeforeEach
    void setUp() {
        service = new OrderService(repository, payment, notifications);
    }

    @Test
    void savesOrderWhenPaymentIsApproved() {
        when(payment.charge(any()))
            .thenReturn(PaymentResult.approved("payment-1"));

        service.place(validCommand());

        verify(repository).save(any(Order.class));
    }
}
```

The service is a real object; dependencies with side effects sit behind ports and are replaced with mocks. The test both runs real service logic and controls external interactions. This is usually a clearer, lower-risk design than spying on the service and stubbing internal methods.

## 11. Spies in Spring Test and Spring Boot

In tests with a Spring context, you sometimes need to spy on a Spring-managed bean to keep most real behavior while overriding a specific method. Spring annotations support registering Mockito spies in the context. Spring Framework 6.2 and later provide `@MockitoSpyBean`; older Spring Boot projects may use `@SpyBean` from Spring Boot Test.

Example with `@MockitoSpyBean`:

```java
@SpringBootTest
class OrderWorkflowTest {

    @MockitoSpyBean
    PaymentAdapter paymentAdapter;

    @Autowired
    OrderService orderService;

    @Test
    void handlesPaymentDeclinedByGateway() {
        doReturn(PaymentResult.declined("declined"))
            .when(paymentAdapter)
            .charge(any(PaymentRequest.class));

        assertThrows(PaymentDeclinedException.class,
            () -> orderService.place(validCommand()));
    }
}
```

Here Spring builds the context and beans; the annotation registers a spy for the selected bean. `doReturn()` prevents the real `charge()` method from being called during stubbing. Using `when(paymentAdapter.charge(...)).thenReturn(...)` could cause the adapter to call the real payment gateway during Arrange.

Spy beans in Spring still carry distinct risks:

- The context must initialize the bean and its dependencies; initialization callbacks such as `@PostConstruct` may still run.
- Beans may be proxied by Spring AOP for transactions, security, or caching; spying a bean must be configured properly so it does not strip away the behavior under test.
- If multiple beans share the same type, specify the target bean via a qualifier or bean name per the annotation API in use.
- A test context using a spy can be cached and shared across multiple tests; leftover state or stubs must be managed carefully.
- Spy beans couple tests to the application's bean structure; use them only when genuine integration verification is needed.

When the goal is testing transactions, security, or AOP, verify that the test routes through the bean/proxy properly. Do not conclude that transactions work just because a spy method was invoked.

## 12. Spies and Mockito annotations

Mockito supports creating spies via manual APIs or annotations. Example:

```java
@ExtendWith(MockitoExtension.class)
class LegacyCalculatorTest {

    @Spy
    LegacyCalculator calculator = new LegacyCalculator();

    @Test
    void usesStubbedRateWhenCalculatingTotal() {
        doReturn(0.1).when(calculator).taxRate();

        assertEquals(110.0, calculator.total(100.0));
    }
}
```

`@Spy` requires an instantiable instance. If the constructor needs dependencies, construct the instance explicitly with mocks/fakes or use Mockito's appropriate initialization. Do not assume the spy annotation automatically turns an object with a complex constructor and side effects into a safe object.

`@InjectMocks` can be combined with spies in some test setups, though you must keep clear which object is the SUT and which is a dependency. When multiple annotations participate in constructing objects, tests can obscure how dependencies are injected. Instantiating objects directly in `@BeforeEach` is often more transparent when constructors take several ports.

## 13. Spies, final methods, and technical limits

The ability to spy or stub methods depends on the Mockito version and configured mock maker. Modern Mockito setups support many cases that used to be restricted, though you should not assume every method can be intercepted under every configuration.

Points to keep in mind:

- Private methods are not part of standard Mockito APIs for direct stubbing. If a private method holds important logic needing standalone testing, consider extracting it into a component with a clear responsibility.
- Final methods, final classes, and certain special types depend on the mock maker and Mockito version.
- Static methods require dedicated mocking mechanisms and are not natural targets for instance spies.
- Native methods or methods tightly bound to the runtime may not be suitable for spying.
- Some methods may be affected by framework proxies or bytecode instrumentation, making behavior hard to reason about.

If Mockito reports that it cannot stub or verify a method, check your Mockito configuration and class design before adding complex workarounds. Usually a small port or separate adapter makes tests more stable.

## 14. Managing stubs and resetting between tests

Spies hold real state, so one test can mutate state and affect subsequent tests if the same spy is shared. JUnit Jupiter creates a new test class instance per test method under its default `PER_METHOD` lifecycle, while Spring contexts and beans can be reused across multiple tests. Mockito extensions also manage mocks/spies according to the initialized test lifecycle.

Prefer creating a fresh spy per test whenever possible. If using a shared spy bean in a Spring context:

- Use the Spring Test/Mockito reset API suited to your version when you need to clear stubs and invocation history.
- Never rely on test execution order for a stub to remain active.
- Never mutate shared state without restoring it.
- Be cautious with parallel execution because one test may interact with the spy while another test alters stubs.

Resetting a mock/spy does not necessarily restore all business state of the real object. It can clear stubbing and invocation history, yet it cannot roll back databases, files, messages, or side effects that already occurred. To isolate data, use transaction rollback, dedicated databases, fresh fake state, or controlled cleanup.

## 15. Separating side effects between the Arrange and Act phases

A readable test usually splits into three phases:

1. **Arrange:** create fixtures, instantiate objects, configure mocks/spies.
2. **Act:** invoke the behavior the test needs to verify.
3. **Assert:** verify outcomes and interactions.

When stubbing a spy with `when(spy.method())`, the real implementation can run during Arrange. That breaks the expectation that Arrange only prepares state. A test could send email or update a database before the tested action starts.

Use `doReturn`/`doThrow`/`doNothing` when stubbing spies to prevent real methods from running during Arrange. If a real method must run to test behavior, call it explicitly in Act and prepare its dependencies safely.

Example:

```java
@Test
void publishesReportWhenReportIsAvailable() {
    ReportService spyService = spy(new ReportService(repository, publisher));

    doReturn(sampleReport())
        .when(spyService)
        .loadReport("report-7");

    // Act: the real call to publish() runs here
    spyService.publish("report-7");

    // Assert: confirm the publish port received the report
    verify(publisher).publish(sampleReport());
}
```

In this example, `loadReport()` is stubbed so it does not query a real repository; `publish()` still runs its real implementation during Act. The publisher should be a mock or fake so it does not send real messages. This is controlled spy usage, though if `publish()` is the core logic under test, consider extracting `loadReport` into a repository port instead of stubbing an internal method.

## 16. Decision table: when to use `when` vs `doReturn`?

| Object being stubbed | Usually suitable syntax | Reason |
| --- | --- | --- |
| Regular mock | `when(mock.method()).thenReturn(value)` | Mocks do not run real implementations by default |
| Spy, pure method where calling real code during setup is safe | Can use `when(spy.method()).thenReturn(value)` | Real method runs during setup without concerning side effects |
| Spy, method reading DB/calling network/writing data | `doReturn(value).when(spy).method()` | Avoids calling the real implementation during stubbing |
| Spy, method needing to throw an exception instead of running | `doThrow(error).when(spy).method()` | Prevents real side effects and simulates error branch |
| Spy, `void` method with side effects | `doNothing().when(spy).method()` | Blocks real implementation |
| Spy, dynamic response based on arguments | `doAnswer(...).when(spy).method()` | Controls behavior without calling the real method during setup |

There is no rule requiring `doReturn` for every spy stub. If a method is a pure function with no external state access and calling it in Arrange causes no side effects, `when(...).thenReturn(...)` can still be used. However, `doReturn` is the safer option whenever you are unsure what the real method will do.

## 17. Situations where spies should be avoided

Reconsider the design if:

- You spy on a service just to stub a repository or HTTP client. Inject a mock/fake of the port instead of spying on the service.
- You spy on a bean whose constructor or `@PostConstruct` connects to real systems. Separate resource initialization into an adapter or controlled lifecycle.
- You stub many methods on the same spy. The class may have too many responsibilities or the test is coupled to internal structure.
- You use a spy to test transactions, caching, or security, yet the test bypasses real Spring proxies.
- You spy on a real repository and stub methods with `when(...)` that can query or update the database during Arrange.
- You spy on an object with shared state, background threads, or active schedulers.
- The test needs full control over all dependencies. A real object with mock/fake dependencies is usually simpler.

A spy is a testing aid, not a reason to keep a class with blurry boundaries. If stubbing an internal method becomes a prerequisite for testability, consider extracting that behavior into a clearly named collaborator or port.

## 18. Example comparing spy-based design vs port-based design

Suppose `OrderService` calculates totals, accesses the database, calls a payment API, and sends emails. A spy-based test might have to stub `loadCustomer()`, `chargeCard()`, `saveOrder()`, and `sendEmail()`. Every time internal structure changes, the test must change with it.

A port-separated design:

```java
class OrderService {

    private final CustomerRepository customers;
    private final PaymentPort payments;
    private final OrderRepository orders;
    private final NotificationPort notifications;

    OrderService(
            CustomerRepository customers,
            PaymentPort payments,
            OrderRepository orders,
            NotificationPort notifications) {
        this.customers = customers;
        this.payments = payments;
        this.orders = orders;
        this.notifications = notifications;
    }

    OrderId place(PlaceOrderCommand command) {
        Customer customer = customers.findById(command.customerId())
            .orElseThrow(CustomerNotFoundException::new);

        PaymentResult payment = payments.charge(
            new PaymentRequest(command.amount(), command.paymentToken())
        );

        Order order = Order.create(customer, command, payment);
        orders.save(order);
        notifications.sendOrderConfirmation(order);
        return order.id();
    }
}
```

Unit test instantiating the real service and mocking the ports:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock CustomerRepository customers;
    @Mock PaymentPort payments;
    @Mock OrderRepository orders;
    @Mock NotificationPort notifications;

    private OrderService service;

    @BeforeEach
    void setUp() {
        service = new OrderService(customers, payments, orders, notifications);
    }

    @Test
    void doesNotSendConfirmationWhenPaymentIsDeclined() {
        when(customers.findById("customer-42"))
            .thenReturn(Optional.of(sampleCustomer()));
        when(payments.charge(any()))
            .thenReturn(PaymentResult.declined("declined"));

        assertThrows(PaymentDeclinedException.class,
            () -> service.place(validCommand()));

        verify(orders, never()).save(any());
        verify(notifications, never()).sendOrderConfirmation(any());
    }
}
```

The test does not need to spy on `OrderService`. It executes real logic while side effects are controlled at the ports. This keeps the test aligned with application contracts instead of internal methods.

## 19. Safety checklist when stubbing spies

Before configuring a stub on a spy, verify:

- Will the real method execute immediately when writing `when(spy.method())`?
- Does that method call a database, HTTP, broker, email, filesystem, or cloud service?
- Does the method mutate state, increment counters, write audit logs, or emit events?
- Did the constructor and lifecycle callbacks already create real resources?
- Can `doReturn`, `doThrow`, `doNothing`, or `doAnswer` be used to avoid running the method in Arrange?
- Can external dependencies be replaced with mocks/fakes so Act is safe?
- Is the test verifying public behavior or stubbing too many internal methods?
- Is a separate integration test needed to prove adapters, Spring proxies, or transactions?

If you cannot answer confidently about a real method's side effects, read its implementation and dependencies before stubbing. Do not treat a call inside `when(...)` as a purely declarative operation when the stubbed object is a spy.

## 20. Controlled spy usage workflow

1. **Define the goal:** state clearly which methods must keep real behavior and which must be stubbed.
2. **Inspect initialization:** check whether constructors, dependencies, and lifecycle hooks create side effects.
3. **Isolate I/O:** replace databases, HTTP, message brokers, email, and filesystems with test adapters or suitable test doubles.
4. **Choose stubbing syntax:** for spies, prefer `doReturn`, `doThrow`, `doNothing`, or `doAnswer` when real methods must not run during Arrange.
5. **Run real behavior in Act:** let the real method execute only when the test intentionally verifies it.
6. **Assert outcomes:** verify business outcomes and meaningful interactions across ports.
7. **Re-evaluate necessity:** if multiple internal methods must be stubbed, extract dependencies or switch to testing the real object with mock/fake collaborators.

Spies are helpful when part of real behavior must be preserved, but they can also trigger unintended side effects during setup. With Mockito, the key difference lies in how Java evaluates the call inside `when(spy.method())`; use the `do...` API family to stub without running the real implementation. In Spring applications, also control bean initialization, dependencies, proxies, and lifecycle. When I/O boundaries sit behind clear ports, most unit tests can use real objects with mock/fake dependencies and reserve spies for situations that genuinely require them.
