# Avoiding Blocking on the Event Loop and Choosing a Scheduler for Blocking Tasks

## Lesson objectives

In a Spring WebFlux application, Reactor handles many requests using a limited number of event loop threads. Each thread must return to processing quickly so it can accept network events and forward reactive signals. If a blocking operation ties up an event loop thread for a long duration, other requests sharing that thread also have to wait. The system can experience widespread latency spikes even if only one dependency is slow.

A circuit breaker helps stop sending new calls to a failing dependency, but it does not automatically turn a synchronous call into a non-blocking one, nor does it choose a scheduler on its own. The application must keep reactive operations on appropriate threads while moving irreplaceable blocking APIs onto a scheduler dedicated to blocking tasks.

After this lesson, you will be able to:

- Explain the role of the event loop and the impact of blocking a reactive processing thread.
- Recognize common blocking operations in controllers and Reactor chains.
- Use subscribeOn and Schedulers.boundedElastic() to run blocking APIs on an appropriate worker.
- Distinguish subscribeOn from publishOn and choose schedulers by workload type.
- Combine offloaded blocking calls with a reactive circuit breaker while preserving the protection boundary.
- Coordinate schedulers, timeouts, and bulkheads to limit the impact of slow dependencies.

## 1. The event loop must be freed quickly

WebFlux uses an asynchronous processing model built on Reactor and a small set of event loops from the network runtime. Instead of dedicating a thread per request and holding that thread throughout I/O wait times, an event loop handles many connections by accepting events, performing a short piece of work, and moving on to the next task.

One event loop thread can serve many requests. When code running on this thread invokes a blocking method, the thread cannot process any other events until that method returns.

For example, if a handler calls a synchronous HTTP client and the dependent service takes 3 seconds to respond, the event loop executing the handler may be held for that entire duration. Other requests assigned to the same event loop are also delayed. As the number of blocking calls grows, latency and queues can climb rapidly.

Ideal reactive processing flow:

    Request
       |
       v
    Event loop
       |
       +-- creates publisher
       |
       +-- sends async request
       |
       +-- returns thread to event loop
       |
       +-- receives signal when data arrives
       |
       +-- continues brief non-blocking processing

When I/O completes, the reactive library emits a signal so the processing chain resumes. The event loop does not need to stand idle waiting on a thread for a network response.

Key point: reactive does not mean every piece of code in the chain is automatically non-blocking. If an operator calls synchronous JDBC, RestTemplate, synchronous file I/O, or Thread.sleep, that code still blocks whichever thread executes it.

## 2. Recognizing blocking operations

Several operations easily block the event loop unintentionally:

- Synchronous HTTP calls using RestTemplate or an HTTP client API that waits directly for results.
- Database queries via synchronous JDBC or JPA.
- Calling Future.get(), CompletableFuture.join(), or waiting on a semaphore/latch.
- Calling Mono.block(), Flux.blockFirst(), or Flux.blockLast() in a reactive request flow.
- Using Thread.sleep() for waiting or retrying.
- Reading/writing files using synchronous APIs.
- Calling third-party libraries whose methods only return after I/O finishes.

Inappropriate example in WebFlux:

    @RestController
    public class InventoryController {

        private final RestTemplate restTemplate;

        @GetMapping("/inventory/{sku}")
        public InventoryResponse find(@PathVariable String sku) {
            return restTemplate.getForObject(
                "http://inventory-service/inventory/" + sku,
                InventoryResponse.class
            );
        }
    }

The find method performs a synchronous HTTP request directly during request handling. If the controller runs on the event loop, that thread must wait for the result from inventory-service.

Another example is creating a publisher and then calling block to extract data:

    @GetMapping("/inventory/{sku}")
    public Mono<InventoryResponse> find(@PathVariable String sku) {
        InventoryResponse response = webClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResponse.class)
            .block();

        return Mono.just(response);
    }

The code above turns a WebClient call into a synchronous wait. Return the publisher directly instead:

    @GetMapping("/inventory/{sku}")
    public Mono<InventoryResponse> find(@PathVariable String sku) {
        return webClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResponse.class);
    }

Do not call block() in a WebFlux processing flow to retrieve a value and then re-wrap it in Mono or Flux. Let the publisher be composed and subscribed to by the reactive runtime.

## 3. Prefer non-blocking APIs whenever possible

If a library already provides a truly reactive or asynchronous API, use that API. Examples:

| Need | Preferred API in reactive flows | APIs requiring caution |
| --- | --- | --- |
| HTTP calls | WebClient | RestTemplate or synchronous HTTP clients |
| Database queries | R2DBC and corresponding reactive repositories | Blocking JDBC, JPA |
| Handling a single result | Mono | Calling block() to retrieve the result |
| Handling multiple results | Flux | Collecting large datasets into a List just to wait for completion |
| Waiting for a duration | Mono.delay or timing operators | Thread.sleep |
| Combining async tasks | then, flatMap, zip, and Reactor operators | Future.get or join |

Example using WebClient returning Mono:

    public Mono<InventoryResponse> find(String sku) {
        return webClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResponse.class);
    }

WebClient performs I/O in a non-blocking manner. You do not need to move this call onto boundedElastic simply because it accesses the network. Adding a scheduler does not improve the API and can introduce unnecessary thread switching.

If the database already has a reactive driver, use a reactive repository and keep the entire processing chain reactive. Moving a JDBC query onto boundedElastic prevents blocking the event loop, yet the operation remains blocking and still occupies a worker thread while waiting.

## 4. Offloading blocking APIs with boundedElastic

When a blocking API cannot yet be replaced, isolate it from the event loop. Reactor provides Schedulers.boundedElastic() for blocking tasks with variable execution times.

With Mono, you can use Mono.fromCallable to defer invoking the API until subscription occurs, then apply subscribeOn:

    Mono<InventoryResponse> request = Mono.fromCallable(() ->
        restTemplate.getForObject(
            "http://inventory-service/inventory/{sku}",
            InventoryResponse.class,
            sku
        )
    ).subscribeOn(Schedulers.boundedElastic());

fromCallable builds a publisher from a Callable. The Callable only runs when the publisher is subscribed to. subscribeOn(Schedulers.boundedElastic()) places subscription and execution of this source onto a boundedElastic worker, so the RestTemplate call does not occupy the event loop.

The same pattern works for JDBC or blocking libraries:

    Mono<Customer> customer = Mono.fromCallable(() ->
        jdbcCustomerRepository.findById(customerId)
            .orElseThrow(() -> new CustomerNotFoundException(customerId))
    ).subscribeOn(Schedulers.boundedElastic());

For a task that returns no value, use fromRunnable:

    Mono<Void> writeAudit = Mono.fromRunnable(() ->
        blockingAuditClient.write(event)
    ).subscribeOn(Schedulers.boundedElastic());

Do not invoke the blocking method before creating the publisher. The following example is still wrong:

    Customer customer = jdbcCustomerRepository.findById(customerId)
        .orElseThrow();

    Mono<Customer> result = Mono.just(customer)
        .subscribeOn(Schedulers.boundedElastic());

The JDBC query already ran before Mono was created. subscribeOn cannot move already-completed work to another scheduler. Put the call itself inside fromCallable or fromRunnable so it executes only upon subscription.

## 5. Choosing the right placement for subscribeOn and publishOn

subscribeOn and publishOn both relate to schedulers, but they play different roles.

| Operator | Effect | When to use |
| --- | --- | --- |
| subscribeOn(scheduler) | Controls the scheduler used to subscribe to the source and execute synchronous source work when subscription starts. | Moving a blocking source such as fromCallable onto boundedElastic. |
| publishOn(scheduler) | Switches processing of subsequent signals and downstream operators to the chosen scheduler. | Moving a downstream processing stage onto another scheduler. |

Example placing subscribeOn properly:

    Mono<Customer> customer = Mono.fromCallable(() ->
        jdbcCustomerRepository.findById(customerId).orElseThrow()
    ).subscribeOn(Schedulers.boundedElastic());

Example using publishOn to switch a downstream processing step:

    Mono<CustomerView> view = webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(Customer.class)
        .publishOn(Schedulers.parallel())
        .map(this::calculateCpuIntensiveView);

WebClient still performs non-blocking I/O. Once the result arrives, publishOn switches subsequent signals and the downstream map operator to the parallel scheduler to execute CPU computation.

Do not place publishOn after a blocking call to try to offload that call itself:

    Mono<Customer> wrong = Mono.fromCallable(() ->
        jdbcCustomerRepository.findById(customerId).orElseThrow()
    ).publishOn(Schedulers.boundedElastic());

The fromCallable source can execute before publishOn switches signals downstream. Thus, the JDBC query still risks running on the subscribing thread, such as the event loop. Use subscribeOn to place the blocking source onto boundedElastic.

Practical rules:

- Place subscribeOn close to the blocking source, typically right after fromCallable or fromRunnable.
- Use publishOn when you need to switch schedulers for subsequent processing steps.
- Do not add multiple scheduler switches without a measurable reason.
- Do not assume publishOn changes the scheduler of steps located before it.

## 6. Choosing a scheduler by workload type

Reactor provides several commonly used schedulers:

| Scheduler | Purpose | Examples |
| --- | --- | --- |
| Schedulers.parallel() | CPU-bound work, sharing a pool sized to match CPU cores. | Data transformations, pure computation, processing without I/O waits. |
| Schedulers.boundedElastic() | Blocking tasks with variable wait times, with bounded workers and queues. | JDBC, RestTemplate, synchronous file reads, blocking SDKs. |
| Schedulers.single() | A single shared sequential worker. | Lightweight tasks that intentionally must run sequentially. |
| Schedulers.immediate() | Executes immediately on the current thread. | Special cases needing to stay on the current execution context; do not use to offload blocking work. |

Do not run JDBC, RestTemplate, or Thread.sleep on Schedulers.parallel(). That pool is meant for CPU-bound work; one blocked worker degrades capacity for other tasks.

boundedElastic fits blocking APIs better because worker counts are bounded and excess tasks wait in a bounded queue. However, boundedElastic is not an infinite resource. If a dependent service hangs, workers can be held for a long time and queues can grow. Combine client timeouts, concurrency limits, and circuit breakers.

For a blocking workload with dedicated isolation requirements, you can create a separate scheduler via Schedulers.newBoundedElastic(...) and manage its lifecycle. When the application shuts down, dispose of any created scheduler. Do not create a new scheduler per request, as that consumes excessive resources and is hard to control.

## 7. Combining boundedElastic with a reactive circuit breaker

A circuit breaker does not pick a scheduler on its own and does not make RestTemplate non-blocking. Create the blocking publisher, offload the source to boundedElastic, and then pass that publisher through the reactive circuit breaker.

Example using Spring Cloud ReactiveCircuitBreakerFactory:

    import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
    import org.springframework.stereotype.Service;
    import org.springframework.web.client.RestTemplate;
    import reactor.core.publisher.Mono;
    import reactor.core.scheduler.Schedulers;

    @Service
    public class ReactiveInventoryGateway {

        private final RestTemplate restTemplate;
        private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public ReactiveInventoryGateway(
                RestTemplate restTemplate,
                ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.restTemplate = restTemplate;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public Mono<InventoryResponse> find(String sku) {
            Mono<InventoryResponse> blockingRequest = Mono.fromCallable(() ->
                restTemplate.getForObject(
                    "http://inventory-service/inventory/{sku}",
                    InventoryResponse.class,
                    sku
                )
            ).subscribeOn(Schedulers.boundedElastic());

            return circuitBreakerFactory.create("inventory-read").run(
                blockingRequest,
                error -> Mono.just(InventoryResponse.unknown(sku))
            );
        }
    }

Two separate responsibilities are at work here:

- subscribeOn(boundedElastic()) ensures RestTemplate runs on an appropriate worker without occupying the event loop.
- The reactive circuit breaker monitors publisher outcomes and can reject new calls when the dependency is unhealthy. The fallback function returns a Mono of the same data type.

If the breaker transitions to OPEN, the primary publisher is not executed and the fallback can return an UNKNOWN status. If the publisher runs, call errors or execution duration are evaluated per breaker configuration. Offloading does not alter the protection boundary: the monitored operation is still the call to inventory-service.

If using Resilience4j's Reactor operator directly, you can decorate the publisher similarly:

    Mono<InventoryResponse> protectedRequest = Mono.fromCallable(() ->
        restTemplate.getForObject(
            "http://inventory-service/inventory/{sku}",
            InventoryResponse.class,
            sku
        )
    )
    .subscribeOn(Schedulers.boundedElastic())
    .transformDeferred(CircuitBreakerOperator.of(inventoryBreaker))
    .onErrorResume(
        CallNotPermittedException.class,
        error -> Mono.just(InventoryResponse.unknown(sku))
    );

Place the circuit breaker operator before onErrorResume so the breaker receives the source error before it is converted into a fallback. If errors are converted into success results before the breaker observes them, failure rate statistics may fail to reflect actual dependency health.

## 8. Bounding wait time and concurrent blocking tasks

Offloading frees the event loop, but it does not make a blocking call finish faster. If inventory-service does not respond, a boundedElastic worker can still remain occupied until the HTTP client times out or the operation finishes.

Coordinate multiple mechanisms:

- **HTTP client timeout:** bound connection and response wait times on RestTemplate or whichever synchronous client is used.
- **Circuit breaker:** use failure rate and slow call rate to stop sending new calls when a dependency has issues.
- **Bulkhead:** limit concurrent calls to a dependency to avoid exhausting workers or resources.
- **Scheduler:** isolate blocking tasks from the event loop and configure appropriate worker/queue limits.

Example Resilience4j bulkhead configuration:

    resilience4j:
      bulkhead:
        instances:
          inventory-read:
            maxConcurrentCalls: 20
            maxWaitDuration: 0ms

This limit illustrates maximum concurrent calls per bulkhead instance. If the application runs multiple pods, total calls to inventory-service can exceed one pod's limit. Account for aggregate load across instances when choosing values.

You can also add a timeout at the Reactor layer:

    Mono<InventoryResponse> request = Mono.fromCallable(() ->
        restTemplate.getForObject(
            "http://inventory-service/inventory/{sku}",
            InventoryResponse.class,
            sku
        )
    )
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(2));

Reactor's timeout emits an error signal and cancels the subscription when time expires. However, cancelling the subscription does not guarantee an underlying blocking call immediately stops or the worker thread is freed. Configure real timeouts on the HTTP client; do not rely solely on Mono.timeout to stop synchronous I/O.

If many requests are queued in boundedElastic, examine concurrency and queueing. A bulkhead placed in front of the blocking operation can fail fast instead of letting a backlog of tasks queue up and consume resources. A circuit breaker stops calling a persistently failing dependency; a bulkhead caps running tasks; a timeout bounds wait duration. These three mechanisms complement one another.

## 9. Avoiding unintended subscriptions and thread switches

Reactor publishers are typically lazy. Creating a Mono or Flux does not mean the task has run. Work executes when subscribed.

Do not call subscribe() manually inside a controller or service just to start work and then return a different publisher. Doing so detaches work from the request lifecycle, making it hard for errors and cancellations to propagate properly.

Pattern to avoid:

    public Mono<InventoryResponse> find(String sku) {
        Mono<InventoryResponse> request = createBlockingRequest(sku);

        request.subscribe();

        return Mono.just(InventoryResponse.unknown(sku));
    }

This code creates a separate subscription and returns the fallback result immediately, while the real request continues running independently. Return the protected publisher so the framework manages the subscription:

    public Mono<InventoryResponse> find(String sku) {
        return createBlockingRequest(sku)
            .subscribeOn(Schedulers.boundedElastic());
    }

Also avoid subscribing multiple times to the same cold publisher unless you intend to send multiple requests to the dependent service. If the same result is needed by multiple branches, consider sharing operators or combining publishers rather than creating manual subscriptions.

Client-side cancellation can cancel the reactive chain and cancellation-aware operations. However, a blocking API may continue running until it finishes on its own or hits a client-layer timeout. Therefore, bounding execution time and concurrent blocking tasks remains essential even when using Reactor.

## 10. Verifying the event loop and scheduler in practice

You can verify scheduler choices by observing executing threads. In a test publisher, print the thread name at the source and at a subsequent processing stage:

    Mono<String> sample = Mono.fromCallable(() -> {
        System.out.println("blocking source: " + Thread.currentThread().getName());
        return "done";
    })
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(value -> {
        System.out.println("cpu stage: " + Thread.currentThread().getName());
        return value.toUpperCase();
    });

Expected result:

- blocking source runs on a worker whose name belongs to boundedElastic.
- cpu stage runs on a worker belonging to parallel.
- the event loop is not held while the blocking source waits.

Exact thread names depend on the runtime and Reactor version; verify scheduler type and actual execution path rather than depending on a hardcoded thread name string in tests.

Signs that the event loop is being blocked:

- Latency increases simultaneously across many reactive endpoints.
- Event loop thread count is low while processing or wait times spike.
- Warning logs reporting blocking calls on threads marked non-blocking.
- One endpoint calling a synchronous library slows down other endpoints sharing the same runtime.

BlockHound can be integrated in development or test environments to detect certain blocking calls on threads marked non-blocking. This tool helps catch issues early, though it does not replace understanding library APIs and performing realistic load tests.

## 11. Hands-on exercise: protecting a blocking HTTP library

Suppose order-service currently uses RestTemplate to call inventory-service, while the rest of the application uses WebFlux.

1. Create a gateway method returning Mono<InventoryResponse>.
2. Wrap the RestTemplate call in Mono.fromCallable so it only runs on subscribe.
3. Apply subscribeOn(Schedulers.boundedElastic()) immediately after the blocking source.
4. Wrap the publisher with ReactiveCircuitBreakerFactory using the ID inventory-read.
5. Configure connect timeout and response timeout on the HTTP client.
6. Add a fallback representing an unknown inventory status.
7. Generate test load while inventory-service responds slowly; observe that the event loop still serves other endpoints.
8. Limit concurrent calls with a bulkhead and observe requests exceeding the limit.
9. Make inventory-service fail repeatedly so the breaker transitions to OPEN, then recover to observe HALF_OPEN.
10. Inspect thread logs to confirm RestTemplate does not run on the event loop.

Try an additional version using WebClient. Compare the two approaches: WebClient performs non-blocking I/O and does not need boundedElastic; RestTemplate remains blocking even when offloaded to boundedElastic. Both can be protected with a circuit breaker, but offloading alone does not make a blocking API reactive.

When finished, you should be able to identify which code blocks, which thread runs that code, why subscribeOn must sit close to the blocking source, and when publishOn is appropriate. You should also be able to explain why schedulers, timeouts, bulkheads, and circuit breakers each have distinct responsibilities. Combining these mechanisms properly keeps event loops ready to serve requests and limits blast radius when remote dependencies are slow or unavailable.
