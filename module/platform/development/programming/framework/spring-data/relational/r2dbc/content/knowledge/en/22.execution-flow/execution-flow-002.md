# Using then, thenMany, and delayUntil to Express Dependencies

In reactive applications using Spring Data R2DBC, many operations must run in a dependent order: save data before reading next, delete old data before emitting a new list, or return an entity only after a related asynchronous operation completes.

Reactor provides the `then`, `thenMany`, and `delayUntil` operators to express these relationships without calling `block()` or creating manual subscriptions. All three care about when a publisher completes, but they differ in whether they keep or discard the input value and in the type of data emitted.

- **then** waits for the current publisher to complete successfully, discards its values, and switches to a subsequent `Mono` or simply emits a completion signal.
- **thenMany** also waits for the current publisher to complete successfully, discards its values, and then switches to a publisher that can emit multiple elements.
- **delayUntil** preserves each value from the source publisher, but only emits that value after the dependent publisher created from it completes.

Choosing the right operator makes the code express intent clearly: whether you need to wait for a task to finish, switch to a new result stream, or keep the current value while waiting on a dependent task.

## 1. Reactive publishers and dependency relationships

In Reactor, `Mono<T>` represents a result that may or may not exist; `Flux<T>` represents a sequence of zero, one, or many elements. Publishers are typically lazy: calling a repository or reactive client builds the pipeline, while the I/O operation only starts upon subscription.

For example:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

At the moment `saved` is assigned, there is no guarantee the SQL statement has executed. Only when the publisher is subscribed to does Spring Data R2DBC perform the save operation.

If the next step depends on the save completing, chain both publishers within the same pipeline. Do not call `subscribe()` inside a service to trigger the second step manually, because doing so prevents the caller from controlling the result, errors, and cancellation of the entire operation.

### 1.1. Three common dependency patterns

Suppose the application just saved an order:

1. Save the order, then write an audit log. The order entity does not need to be retained from the audit publisher. This is a wait-for-completion and move-to-next-step relationship: `then`.
2. Delete expired sessions, then emit the list of active sessions. The value from the delete operation is not needed in the final result, while the next step returns multiple sessions: `thenMany`.
3. Save the order, call the inventory service using the newly saved order's ID, and return the order only after inventory confirms. You need to keep the order entity itself while waiting on the dependent operation: `delayUntil`.

## 2. Use then when you only care that the publisher completed

`then()` ignores all values emitted by the source publisher and returns a `Mono<Void>` that completes only when the source publisher completes successfully.

~~~java
Mono<Void> result = customerRepository.save(customer).then();
~~~

If you want to run another `Mono` after the source publisher completes, use `then(Mono<V>)`:

~~~java
Mono<Order> result = auditRepository.save(auditRecord)
        .then(orderRepository.findById(orderId));
~~~

The sequence is:

1. Subscribe to the audit-saving publisher.
2. Wait for the audit save operation to complete.
3. If successful, subscribe to the order-finding publisher.
4. Emit the found order or complete empty if no order exists.

The `AuditRecord` emitted by `save()` is discarded. The value from the second publisher becomes the value of the final `Mono<Order>`.

### 2.1. then() without a second publisher

When you only need to express that an operation must finish before the service completes, use `then()`:

~~~java
public Mono<Void> recordCustomerCreation(Customer customer) {
    AuditRecord audit = AuditRecord.customerCreated(customer.getId());

    return auditRepository.save(audit).then();
}
~~~

`save()` may emit the saved entity, but the service only returns a completion signal. The caller does not receive the audit entity.

### 2.2. Use thenReturn when returning a fixed value

If the source publisher must complete before returning an already available value, you can use `thenReturn(value)`:

~~~java
return auditRepository.save(auditRecord)
        .thenReturn("AUDIT_RECORDED");
~~~

This is a concise equivalent in meaning to switching to a `Mono` emitting a fixed value after the source publisher completes. The audit value emitted by `save()` is not kept.

### 2.3. Use then(Mono.defer(...)) when the next publisher must be created lazily

If constructing the next publisher needs to happen after the first publisher completes, you can use `Mono.defer`:

~~~java
return auditRepository.save(auditRecord)
        .then(Mono.defer(() -> notificationClient.publish(event)));
~~~

`then` only subscribes to the second publisher after the first completes successfully. `defer` additionally delays calling the publisher factory function until the second step is actually subscribed to. This is useful when the subsequent step needs to read state at execution time or build a fresh request.

If the expression creating the publisher has no side effects and can be created upfront, wrapping it in `defer` is not strictly necessary.

## 3. Use thenMany when the next step returns multiple elements

`thenMany(Publisher<V>)` waits for the source publisher to complete successfully, discards all source values, then subscribes to the next publisher and emits its values as a `Flux<V>`.

Example deleting expired sessions then reading active ones:

~~~java
public Flux<Session> findActiveSessions(LocalDateTime now) {
    return sessionRepository.deleteExpired(now)
            .thenMany(sessionRepository.findAllByStatus("ACTIVE"));
}
~~~

Suppose `deleteExpired` returns `Mono<Integer>` containing the deleted row count. That count is ignored. After deletion completes, `findAllByStatus` is subscribed to and the sessions are emitted.

### 3.1. Results from the first publisher are not prepended to the final Flux

`thenMany` differs from `concatWith`:

~~~java
Flux<String> combined = firstFlux.concatWith(secondFlux);
~~~

`concatWith` emits all elements from `firstFlux`, then emits elements from `secondFlux`.

Meanwhile:

~~~java
Flux<String> replaced = firstFlux.thenMany(secondFlux);
~~~

`thenMany` discards the elements of `firstFlux`; the resulting `Flux` only emits elements from `secondFlux` after `firstFlux` completes.

### 3.2. Using thenMany for multi-step flows

Example saving batch metadata and then emitting records to process:

~~~java
public Flux<Order> prepareAndFindOrders(BatchRun run) {
    return batchRunRepository.save(run)
            .thenMany(orderRepository.findAllByStatus("READY"));
}
~~~

The `BatchRun` entity emitted by `save()` is not included in the resulting `Flux`. The final `Flux` contains orders from the second repository.

If you need to use the `BatchRun` value to construct the next query, `thenMany` is not suitable because it discards the source value. In that case, use `flatMapMany` or an operator that receives the value.

~~~java
return batchRunRepository.save(run)
        .flatMapMany(saved -> orderRepository.findAllByBatchId(saved.getId()));
~~~

`flatMapMany` receives the saved entity to create the dependent `Flux`. This is the right choice when the next step needs the previous step's value.

## 4. Use delayUntil when keeping the value while waiting on a dependent publisher

`delayUntil` is used when the source publisher emits a value, the application creates a dependent publisher from that value, and emits the source value only after the dependent publisher completes.

Example saving an order, then reserving inventory with the generated ID:

~~~java
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .delayUntil(saved -> inventoryClient.reserve(saved.getId()));
}
~~~

Processing flow:

1. `save()` persists the order and emits the saved entity.
2. `delayUntil` receives that entity in the trigger generator function.
3. `inventoryClient.reserve(saved.getId())` is subscribed to.
4. When the `reserve` publisher completes successfully, `delayUntil` emits the `saved` entity itself.

The result remains `Mono<Order>`. The order value is preserved; any value emitted by the inventory publisher (if any) does not replace the order entity.

### 4.1. delayUntil is not a timer

The operator name contains “delay”, but its primary meaning is delaying the emission of a value until a dependent publisher completes. It does not wait for a fixed time duration by default.

If you only want a time-based delay, use an operator like `delayElement(Duration)`:

~~~java
return orderRepository.findById(id)
        .delayElement(Duration.ofSeconds(2));
~~~

If you want to wait for an asynchronous task, use `delayUntil`:

~~~java
return orderRepository.findById(id)
        .delayUntil(order -> auditClient.recordViewed(order.getId()));
~~~

### 4.2. The trigger is commonly a Mono<Void>

The dependent publisher often only needs to signal completion rather than emit data. Therefore, a `Mono<Void>` type is commonly suitable:

~~~java
return customerRepository.findById(customerId)
        .delayUntil(customer -> auditRepository
                .save(AuditRecord.customerViewed(customer.getId()))
                .then());
~~~

Once the audit save finishes, `delayUntil` emits `Customer`. The entity is not replaced by `AuditRecord`.

### 4.3. delayUntil on Flux

`Flux.delayUntil` applies the waiting relationship to each source element:

~~~java
public Flux<Customer> verifyPendingCustomers() {
    return customerRepository.findAllByStatus("PENDING")
            .delayUntil(customer -> verificationClient.verify(customer.getId()));
}
~~~

Each customer is emitted only after its corresponding verification publisher completes. Elements preserve source order; an element's trigger publisher must complete before that element is emitted.

For large datasets, consider bounding the source, pagination, and the capacity of the dependent service. `delayUntil` expresses per-element waiting; it is not an automatic substitute for every parallel processing strategy.

## 5. Comparing then, thenMany, and delayUntil

| Operator | What does it wait for? | Keeps source value? | Common result type | Use when |
| --- | --- | --- | --- | --- |
| then() | Source completes successfully | No | Mono<Void> | Only need to wait for the operation to finish |
| then(Mono<V>) | Source completes before running next Mono | No | Mono<V> | Switching to another Mono result |
| thenReturn(value) | Source completes before emitting fixed value | No | Mono<V> | Wait for completion then return a constant/existing object |
| thenMany(Publisher<V>) | Source completes before running next publisher | No | Flux<V> | Switching to a multi-element stream |
| delayUntil(fn) | Trigger created from each value completes | Yes | Mono<T> or Flux<T> | Keep source value while waiting on dependent work |

### 5.1. Simple diagram

~~~text
then:
  Publisher<A> --complete--> Publisher<B> --emit B
        (drop A)

thenMany:
  Publisher<A> --complete--> Publisher<B...> --emit B...
        (drop A)

delayUntil:
  Publisher<A> --emit A--> Trigger(A) --complete--> emit A
        (keep A)
~~~

## 6. Distinguishing from flatMap, flatMapMany, and concatMap

These operators also chain publishers, but their purposes differ.

### 6.1. flatMap: use source value to produce a new result

~~~java
return orderRepository.save(order)
        .flatMap(saved -> paymentClient.authorize(saved.getId()));
~~~

The result is the output from `paymentClient.authorize`, not the order entity. `flatMap` fits when the value emitted by the previous step is needed to create the next publisher and the final result comes from that publisher.

### 6.2. flatMap with thenReturn: wait on dependency while keeping value

You can write:

~~~java
return orderRepository.save(order)
        .flatMap(saved -> inventoryClient.reserve(saved.getId())
                .thenReturn(saved));
~~~

This is a valid way to express it: call `reserve`, discard its result, and return the order. `delayUntil` expresses this intent more directly and concisely:

~~~java
return orderRepository.save(order)
        .delayUntil(saved -> inventoryClient.reserve(saved.getId()));
~~~

### 6.3. flatMapMany: use source value to create a subsequent Flux

~~~java
return customerRepository.findById(customerId)
        .flatMapMany(customer -> orderRepository.findAllByCustomerId(customer.getId()));
~~~

The result is the orders, not the customer. If you only want to wait for a `Mono` publisher to complete and then emit an independent `Flux`, use `thenMany`.

### 6.4. concatMap: process each element and preserve order

With `Flux`, `concatMap` maps each element to a dependent publisher, subscribes sequentially, and emits the inner publisher's results:

~~~java
return customerRepository.findAllByStatus("PENDING")
        .concatMap(customer -> verificationClient.verifyAndReturn(customer));
~~~

`concatMap` fits when you need the results from the inner publisher and want sequential processing. `delayUntil` fits when you need to preserve the original source `customer` after a trigger completes.

## 7. Handling empty publishers

A `Mono` can complete without emitting a value. This affects how operators behave.

### 7.1. then still runs the next step when the source is empty

~~~java
Mono<Void> first = Mono.empty();

Mono<String> result = first.then(Mono.just("NEXT"));
~~~

The first publisher completes successfully even without emitting a value. Because `then` only cares about the completion signal, the second publisher is still subscribed to and emits `NEXT`.

This also means if `findById()` returns `Mono.empty()`, the following snippet:

~~~java
return customerRepository.findById(id)
        .then(auditRepository.recordLookup(id));
~~~

still writes the audit even when no customer is found. If the audit should only be written when the customer exists, use `flatMap`:

~~~java
return customerRepository.findById(id)
        .flatMap(customer -> auditRepository.recordLookup(id)
                .thenReturn(customer));
~~~

### 7.2. thenMany also runs the next publisher when the source is empty

~~~java
return Mono.<Integer>empty()
        .thenMany(Flux.just("A", "B"));
~~~

The final `Flux` still emits `A` and `B`, because the source completed successfully. If the next step should only run when the source has a value, use `flatMapMany` on the `Mono`:

~~~java
return customerRepository.findById(id)
        .flatMapMany(customer -> orderRepository.findAllByCustomerId(customer.getId()));
~~~

If the customer does not exist, the resulting `Flux` completes empty and the order query is not invoked.

### 7.3. delayUntil does not invoke the trigger when the source emits no value

~~~java
return customerRepository.findById(id)
        .delayUntil(customer -> auditRepository.recordLookup(id));
~~~

If `findById` completes empty, there is no customer to pass to the trigger function. The audit is not called and the result also completes empty.

This is an important distinction: `then`/`thenMany` wait for source completion, whereas `delayUntil` requires a source value to create the dependent publisher.

## 8. Error handling in dependency chains

Sequencing operators only move to the next step after the previous publisher completes successfully.

### 8.1. Error in the source publisher

~~~java
return auditRepository.save(auditRecord)
        .then(notificationClient.publish(event));
~~~

If saving the audit emits an error, the notification publisher is not subscribed to. The audit error is propagated downstream to the caller.

### 8.2. Error in the subsequent publisher

~~~java
return auditRepository.save(auditRecord)
        .then(notificationClient.publish(event));
~~~

If the audit succeeds but `publish` emits an error, the final pipeline emits the error from the `publish` step. The already-saved audit is not automatically undone unless both operations participate in the same rollback-capable transaction and actually use the same transactional resource.

### 8.3. Error in the delayUntil trigger

~~~java
return orderRepository.save(order)
        .delayUntil(saved -> inventoryClient.reserve(saved.getId()));
~~~

If `reserve` emits an error, the order entity is not emitted from the final pipeline; the trigger error propagates to the caller. The order save operation may already have completed before `reserve` failed.

If compensation is needed when `reserve` fails, express the compensation explicitly:

~~~java
return orderRepository.save(order)
        .delayUntil(saved -> inventoryClient.reserve(saved.getId())
                .onErrorResume(error -> orderRepository.markReservationFailed(saved.getId())
                        .then(Mono.error(error))));
~~~

This example only illustrates how to chain a compensating publisher. In a real system, you need to design order states, retries, idempotency, and handling for cases where compensation also fails.

### 8.4. Use onErrorResume intentionally

Do not swallow errors just to keep the pipeline going:

~~~java
return orderRepository.save(order)
        .delayUntil(saved -> inventoryClient.reserve(saved.getId())
                .onErrorResume(error -> Mono.empty()));
~~~

This code turns a reservation error into a successful completion. `delayUntil` then emits the order as if the trigger completed normally. Only do this if business rules accept a failed reservation while still returning the order and have a clear mechanism to track its state.

## 9. Cancellation and non-completing publishers

The dependent publisher must complete for the operator to move forward or emit the value.

- If the source publisher never completes, `then` and `thenMany` never run the next step.
- If the `delayUntil` trigger does not complete, the corresponding source value is never emitted.
- If a publisher emits an error, the error propagates downstream and subsequent steps are skipped.
- If downstream cancels, Reactor propagates cancellation to active publishers according to the rules of that operator and publisher.

Set appropriate timeouts for network or database operations that may hang:

~~~java
return orderRepository.save(order)
        .delayUntil(saved -> inventoryClient.reserve(saved.getId())
                .timeout(Duration.ofSeconds(3)));
~~~

A timeout does not guarantee that side effects in an external system are reversed. It only terminates the publisher on the application side; the external system may have already received and processed the request. For non-idempotent operations, use an idempotency key or status lookup mechanism to avoid duplicate execution.

## 10. Reactive transactions and sequencing operators

`then`, `thenMany`, and `delayUntil` keep publishers within the same pipeline. If the pipeline runs inside a reactive transaction, participating R2DBC operations can share the same transaction context when they use the matching `ConnectionFactory` and transaction manager.

Example:

~~~java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .flatMap(saved -> orderAuditRepository.save(
                    OrderAudit.created(saved.getId()))
                    .thenReturn(saved));
}
~~~

Here saving the order and the audit are chained sequentially. If both repositories use the same R2DBC transaction manager and errors propagate out, an error in the audit can roll back the entire transaction.

### 10.1. Do not prolong transactions with external service calls

Example:

~~~java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .delayUntil(saved -> inventoryClient.reserve(saved.getId()));
}
~~~

If the transaction wraps the entire publisher, the database connection may be held while the application waits for the inventory service. When the external service is slow, the R2DBC pool may have connections tied up longer than necessary.

If you need to coordinate the database with an external service, consider saving state/an outbox record in a short transaction, committing, and then publishing events via a worker. Do not assume an R2DBC transaction can roll back side effects that already occurred in an HTTP service or message broker.

### 10.2. Do not call subscribe() inside a service

Avoid:

~~~java
public Mono<Order> createOrder(Order order) {
    orderRepository.save(order)
            .flatMap(saved -> inventoryClient.reserve(saved.getId()))
            .subscribe();

    return Mono.just(order);
}
~~~

An independent subscription detaches the work from the returned publisher. The caller does not wait for the reservation, does not receive errors from the reservation, and the transaction context may not be preserved as intended.

Return the entire pipeline:

~~~java
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .delayUntil(saved -> inventoryClient.reserve(saved.getId()));
}
~~~

## 11. Combined example: save, write audit, then emit a list

A use case may involve several types of dependencies:

1. Save an order and obtain its ID.
2. Write an audit record using the generated ID.
3. After the audit completes, emit recent orders.

~~~java
public Flux<OrderListItem> createAndRefresh(Order order) {
    return orderRepository.save(order)
            .flatMap(saved -> orderAuditRepository.save(
                    OrderAudit.created(saved.getId()))
                    .thenReturn(saved))
            .thenMany(orderReadRepository.findRecent());
}
~~~

`flatMap` is used in the audit step because the saved order's ID is required. `thenReturn(saved)` discards the audit entity and returns the order. `thenMany` waits for the entire save/audit pipeline to complete before subscribing to the list query and emitting `Flux<OrderListItem>`.

If you do not need to emit the list and only need to return the saved order, use:

~~~java
public Mono<Order> create(Order order) {
    return orderRepository.save(order)
            .delayUntil(saved -> orderAuditRepository.save(
                    OrderAudit.created(saved.getId())));
}
~~~

`delayUntil` retains the order and waits for the audit to complete. Because the two examples have different return contracts, choose the operator based on the data type the API needs to return.

## 12. Example processing each Flux element

Suppose you need to emit each customer after sending an asynchronous verification request:

~~~java
public Flux<Customer> verifyCustomers() {
    return customerRepository.findAllByStatus("PENDING")
            .delayUntil(customer -> verificationClient.verify(customer.getId()));
}
~~~

If you want to emit only the results from the verification service, use `flatMap`:

~~~java
public Flux<VerificationResult> verifyCustomers() {
    return customerRepository.findAllByStatus("PENDING")
            .flatMap(customer -> verificationClient.verifyAndReturn(customer.getId()));
}
~~~

If you need sequential processing and want verification results emitted in source order:

~~~java
public Flux<VerificationResult> verifyCustomersInOrder() {
    return customerRepository.findAllByStatus("PENDING")
            .concatMap(customer -> verificationClient.verifyAndReturn(customer.getId()));
}
~~~

The three pipelines differ in the emitted values and how inner publishers are executed. Choose according to the API contract, not just code brevity.

## 13. Common mistakes when choosing operators

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Saved entity not received | Used `then()`, which discarded the source value | Use `flatMap`, `delayUntil`, or keep the value with `thenReturn` |
| Subsequent query runs even when entity does not exist | Used `then` after `Mono.empty()` | Use `flatMap` or `flatMapMany` if the next step requires the entity |
| Second publisher does not run | First publisher emitted an error or did not complete | Check source errors, timeouts, and completion |
| Final Flux contains only data from the second step | Used `thenMany`, which drops source data | Use `concatWith` if you want to concatenate both streams |
| Entity emitted before side effect finishes | Used `doOnNext` to call publisher or failed to chain dependent publisher | Use `delayUntil` or `flatMap` appropriately |
| Final result is data from dependent service | Used `flatMap` when intending to keep source entity | Use `delayUntil` or `flatMap(...thenReturn(source))` |
| Audit runs even when record is not found | Used `then` after a potentially empty `Mono` | Place audit inside `flatMap` when it should only run if a value exists |
| External service error hidden | Used `onErrorResume` returning `Mono.empty()` unintentionally | Map error to a clear business state or propagate the error |
| Transaction holds connection too long | Waiting on HTTP/message publisher inside transaction | Narrow transaction scope, consider outbox/after-commit |
| Side effect runs twice | Retried a non-idempotent publisher | Use idempotency keys and design safe retries |

## 14. Operator selection table by intent

| Intent | Recommended operator |
| --- | --- |
| Wait for operation to finish, no value needed | `then()` |
| Wait for operation A then return result from Mono B | `then(monoB)` |
| Wait for operation A then return a fixed value | `thenReturn(value)` |
| Wait for operation A then emit Flux B | `thenMany(fluxB)` |
| Wait for publisher created from value A then emit A | `delayUntil(value -> trigger(value))` |
| Use value A to create Mono B and return B's result | `flatMap(value -> monoB)` |
| Use value A to create Flux B and return B's values | `flatMapMany(value -> fluxB)` |
| Emit all elements of Flux A followed by Flux B | `concatWith(fluxB)` |
| Process each element sequentially and emit processing results | `concatMap(value -> publisher(value))` |

## 15. Testing execution order

You should test both the resulting values and the subscription order of dependent publishers. You can use `StepVerifier`, `PublisherProbe`, or `TestPublisher` from Reactor Test depending on the scenario.

### 15.1. Testing then

~~~java
@Test
void thenSubscribesSecondPublisherAfterFirstCompletes() {
    PublisherProbe<String> second = PublisherProbe.of(Mono.just("done"));

    Mono<String> result = Mono.just("ignored")
            .then(second.mono());

    StepVerifier.create(result)
            .expectNext("done")
            .verifyComplete();

    second.assertWasSubscribed();
}
~~~

The test verifies that the second publisher is subscribed to and that the ignored source value does not appear.

### 15.2. Testing thenMany

~~~java
@Test
void thenManyEmitsOnlySecondPublisherValues() {
    Flux<String> result = Flux.just("old-1", "old-2")
            .thenMany(Flux.just("new-1", "new-2"));

    StepVerifier.create(result)
            .expectNext("new-1", "new-2")
            .verifyComplete();
}
~~~

The test verifies that source elements are discarded and the subsequent `Flux` is emitted completely.

### 15.3. Testing delayUntil

~~~java
@Test
void delayUntilPreservesSourceValueUntilTriggerCompletes() {
    PublisherProbe<Void> trigger = PublisherProbe.of(Mono.empty());

    Mono<String> result = Mono.just("order-10")
            .delayUntil(ignored -> trigger.mono());

    StepVerifier.create(result)
            .expectNext("order-10")
            .verifyComplete();

    trigger.assertWasSubscribed();
}
~~~

The test verifies that the trigger is subscribed to and the source value is preserved.

### 15.4. Additional cases to verify

- Source publisher completes empty.
- Source publisher emits an error.
- Second publisher or trigger emits an error.
- Trigger does not complete until the test explicitly allows it.
- Downstream cancels while the dependent publisher is running.
- `Flux` with multiple elements where triggers complete at different times.
- Side effects are not inadvertently subscribed to twice.
- Reactive transaction is preserved when R2DBC publishers are chained in the same pipeline.

## 16. Decision flowchart

~~~mermaid
flowchart TD
    A["Need to chain a dependent publisher?"] --> B{"Need to keep the source value?"}
    B -->|"No"| C{"Does the next publisher emit multiple elements?"}
    C -->|"No"| D["then or then Mono"]
    C -->|"Yes"| E["thenMany"]
    B -->|"Yes"| F{"Is the dependent publisher created from the source value?"}
    F -->|"Yes and only need to wait for completion"| G["delayUntil"]
    F -->|"Yes and need to return the dependent publisher result"| H["flatMap or flatMapMany"]
    F -->|"No"| I["Consider zip/concat/merge based on actual relationship"]
    D --> J["Test empty, error, and cancel"]
    E --> J
    G --> J
    H --> J
    I --> J
~~~

## 17. Conclusion

`then`, `thenMany`, and `delayUntil` all help express dependency relationships in a reactive pipeline, but they have distinct contracts. `then` and `thenMany` discard the source value, wait for the source to complete, and switch to the next publisher; `delayUntil` retains the source value and emits it only after the dependent publisher completes.

Use `then` when you only care that the previous step finished, `thenMany` when the next step emits a multi-element stream, and `delayUntil` when you need to preserve the current entity or value while waiting for an asynchronous operation. If the next step needs the result derived from the source value, use `flatMap` or `flatMapMany`. Always keep operations within the same publisher chain, handle empty/error/cancel explicitly, and avoid prolonging reactive transactions with unnecessary external service calls.
