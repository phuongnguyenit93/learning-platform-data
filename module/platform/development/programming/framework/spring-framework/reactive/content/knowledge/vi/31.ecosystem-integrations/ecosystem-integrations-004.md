# ReactiveTransactionManager và ngữ cảnh giao dịch theo subscription

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Tích hợp hệ sinh thái  
**Mục tiêu:** Hiểu vì sao giao dịch reactive không đi theo `ThreadLocal` mà đi theo `Reactor Context`, khi nào transaction bắt đầu/kết thúc, cách dùng `ReactiveTransactionManager`, `@Transactional` và `TransactionalOperator` với R2DBC, đồng thời tránh các lỗi do subscription, cancellation, retry và resource ownership.

## 1. Tóm tắt cốt lõi

Với giao dịch imperative truyền thống, Spring dùng `PlatformTransactionManager` và thường gắn trạng thái giao dịch vào thread hiện tại thông qua `ThreadLocal`. Mã JDBC trong cùng thread có thể tìm thấy connection đang tham gia transaction.

Với reactive code, luồng xử lý có thể chuyển thread sau `publishOn`, network callback hoặc async operation. Do đó **không thể dùng thread identity làm ranh giới giao dịch**. Spring dùng `ReactiveTransactionManager` để gắn trạng thái và resource giao dịch vào **Reactor Context của subscriber**, và các reactive database operation cùng pipeline sẽ truy cập resource đó.

Ba ý cần nhớ:

1. **Khai báo chưa phải thực thi.** Gọi một method trả `Mono`/`Flux` hoặc tạo `TransactionalOperator` chưa tự mở transaction; transaction được kích hoạt khi publisher được subscribe.
2. **Một subscription là một lần thực thi.** Subscribe lại vào cold transactional publisher thường khởi tạo một lần thực thi và transaction mới, chứ không “đọc lại” kết quả commit lần trước.
3. **Transaction gắn với reactive chain.** Các bước data access phải ở trong pipeline được bọc transactional và giữ cùng Reactor Context. Tự gọi `subscribe()` tạo luồng độc lập; JDBC blocking không tự trở thành participant của R2DBC transaction.

Một transaction điển hình: **subscription → begin → acquire/bind connection → SQL publisher → commit hoặc rollback → release connection**.

## 2. ReactiveTransactionManager là gì?

`org.springframework.transaction.ReactiveTransactionManager` là contract reactive của Spring để quản lý transaction. Thay vì trả ngay `TransactionStatus` hoặc thao tác blocking, các method trả publisher:

```java
public interface ReactiveTransactionManager extends TransactionManager {

    Mono<ReactiveTransaction> getReactiveTransaction(
            TransactionDefinition definition);

    Mono<Void> commit(ReactiveTransaction transaction);

    Mono<Void> rollback(ReactiveTransaction transaction);
}
```

Đây là **rút gọn chữ ký để học**, không phải toàn bộ source interface. Nó biểu đạt ba hành động: lấy hoặc tham gia transaction, commit và rollback. Một implementation phải quản lý resource, propagation, synchronization và cleanup theo contract của backend.

Các implementation/khái niệm thường gặp:

| Backend | Transaction manager hoặc cơ chế | Phạm vi |
|---|---|---|
| R2DBC | `R2dbcTransactionManager` | Một `ConnectionFactory` và các connection do nó cấp |
| Reactive MongoDB | `ReactiveMongoTransactionManager` | MongoDB session, yêu cầu cấu hình server hỗ trợ transaction |
| JDBC/JPA | `JdbcTransactionManager`, `JpaTransactionManager` | Imperative, không dùng để biến lời gọi JDBC thành R2DBC |
| Mã tùy biến | Implementation `ReactiveTransactionManager` | Chỉ khi cần quản lý resource giao dịch riêng |

Dùng đúng manager của resource bạn thao tác. Một transaction của R2DBC không tự bao trùm MongoDB, Kafka, HTTP hoặc một database khác.

### 2.1. ReactiveTransactionManager khác PlatformTransactionManager

| Tiêu chí | PlatformTransactionManager | ReactiveTransactionManager |
|---|---|---|
| Mô hình | Imperative | Reactive Publisher |
| Context mặc định | Thread-bound qua `ThreadLocal` | Subscriber-bound qua `Reactor Context` |
| Bắt đầu | Trong quá trình gọi method/proxy imperative | Khi subscribe publisher giao dịch |
| Resource | JDBC `Connection`, JPA `EntityManager`... | R2DBC `Connection`, reactive session... |
| API programmatic | `TransactionTemplate` | `TransactionalOperator` |
| Method declarative | Phần lớn trả object/`void` | Trả `Publisher`/`Mono`/`Flux` |
| Chạy tốt với thread switch | ThreadLocal không tự lan truyền | Context đi theo reactive subscription |
| Blocking SQL | Có thể dùng | Tránh; dùng driver reactive đúng backend |

Cùng một annotation `@Transactional` có thể áp dụng ở cả hai mô hình, nhưng **transaction manager và cách truyền context khác nhau**. Đừng suy luận rằng vì một method trả `Mono` nên một `DataSourceTransactionManager` sẽ tự tạo transaction R2DBC.

## 3. Vì sao context phải đi theo subscriber?

Reactive Streams gồm `Publisher`, `Subscriber` và `Subscription`. `Publisher` chỉ mô tả công việc. `Subscriber` kích hoạt công việc và giữ tín hiệu request/cancel. Reactor bổ sung `Context` để lưu metadata gắn với **subscription**, không gắn cố định với worker thread.

Sơ đồ:

```text
Service method creates Mono/Flux
           |
           |  no subscription yet
           v
  Transactional publisher
           |
           |  subscriber subscribes
           v
 TransactionalOperator/Interceptor
           |
           +-- obtain transaction from manager
           +-- bind context/resources to subscriber
           |
           v
    R2DBC query publisher 1
           |
           v
    R2DBC query publisher 2
           |
           +-- onComplete  --> commit
           +-- onError     --> rollback / apply rollback rules
           +-- cancel      --> rollback since Spring 5.3
           |
           v
  Release transaction resource
```

`Reactor Context` có thể được truyền qua các operator và qua thay đổi thread nếu chúng nằm trong cùng reactive subscription. Ví dụ `publishOn(Schedulers.parallel())` không mặc nhiên làm mất context khi dùng đúng Reactor API.

Không nhầm `Context` với `ThreadLocal`. Một thread có thể xử lý nhiều subscription; cùng subscription có thể chạy callback trên nhiều thread. Các giá trị context còn phụ thuộc chỗ gọi `contextWrite` và hướng truyền context trong chain.

### 3.1. Subscription-scoped nghĩa là gì?

```java
Mono<Void> operation = service.savePair("invoice-A");

// Tạo publisher chưa làm DB insert.
Mono<Void> sameOperation = operation;

// Subscription thứ nhất: chạy transaction #1.
operation.subscribe();

// Subscription thứ hai: chạy transaction #2.
sameOperation.subscribe();
```

Đây là snippet minh họa ý nghĩa, không phải cách viết production. Hai lần `subscribe()` riêng biệt có thể tạo hai lần ghi. Nếu tác vụ có side effect, hãy thiết kế idempotency và tránh resubscribe vô ý.

Trong ứng dụng WebFlux, controller thường **trả publisher** cho Spring, để framework subscribe đúng lifecycle HTTP:

```java
@PostMapping("/payments")
public Mono<ResponseEntity<Void>> create(
        @RequestBody Mono<PaymentCommand> body) {

    return body.flatMap(paymentService::save)
            .thenReturn(ResponseEntity.accepted().build());
}
```

Không gọi `paymentService.save(...).subscribe()` rồi trả success ngay: request HTTP sẽ không biết task bên trong thất bại hay bị hủy.

### 3.2. Defer và lazy execution

`Mono.defer` hữu ích khi cần tính toán hoặc lấy dữ liệu ngay lúc subscription:

```java
Mono<Void> transactionFlow = Mono.defer(() ->
        repository.insertFirst()
                .then(repository.insertSecond()))
        .as(transactionalOperator::transactional);
```

`Mono.defer` tạo các publisher con cho mỗi subscription. Với repository API đã lazy thì không cần bọc `defer` mọi nơi; dùng khi logic tạo publisher phụ thuộc trạng thái tại thời điểm subscribe.

Không thực hiện side effect bên ngoài reactive publisher:

```java
// Sai: chạy lời gọi imperative trước khi có subscription.
sendEmailNow();
return repository.save(entity).as(operator::transactional);
```

Email sẽ được gửi trước khi DB transaction thực thi và không thể rollback theo transaction R2DBC.

## 4. R2dbcTransactionManager bind connection theo Context

`R2dbcTransactionManager` quản lý transaction cho **một** `io.r2dbc.spi.ConnectionFactory`. Khi transaction bắt đầu, manager lấy `Connection` từ factory, đặt transaction state và bind connection vào subscriber Context. Các hoạt động R2DBC trong cùng context nên dùng connection đó.

Spring Framework yêu cầu data access tích hợp qua:

- `DatabaseClient` hoặc Spring Data R2DBC repository/template, vốn dùng cơ chế transaction-aware.
- `ConnectionFactoryUtils.getConnection(factory)` nếu tự viết R2DBC client thấp tầng.
- `TransactionAwareConnectionFactoryProxy` khi phải cung cấp một factory tương thích với consumer bên ngoài không tích hợp sẵn.

**Không** trực tiếp gọi `connectionFactory.create()` bên trong method đang có transaction rồi nghĩ rằng đó là transaction-bound connection. Việc này có thể tạo connection mới ngoài transaction đã bind. Với API tùy biến, hãy dùng `ConnectionFactoryUtils` hoặc wrapper phù hợp.

`ConnectionFactory` giống nơi tạo connection, không phải một connection dùng chung. `R2dbcTransactionManager` và `DatabaseClient` phải tham chiếu đến factory tương thích; nếu ứng dụng có nhiều factory, phân biệt rõ manager và data access sử dụng cái nào.

### 4.1. Không share một connection giữa nhiều subscription

Một R2DBC `Connection` gắn với transaction thường không được thiết kế để chạy nhiều query đồng thời tự do từ nhiều subscriber. Hãy để Spring quản lý lifecycle; đừng lưu transaction connection vào field singleton hoặc Reactor context thủ công.

Dùng `then` hoặc `concatMap` khi các SQL step phải diễn ra tuần tự. Tránh `flatMap` với concurrency lớn trên các thao tác cùng transaction nếu driver không hỗ trợ truy vấn song song trên một connection.

Một pool R2DBC có thể cấp nhiều connection cho các transaction độc lập, nhưng trong một transaction, các SQL operation được quản lý để dùng đúng resource đã bind.

## 5. @Transactional trong reactive service

`@Transactional` là lựa chọn declarative khi giao dịch là một đặc tính của method service. Method phải trả reactive type để Spring dùng reactive transaction path:

```java
@Service
class OrderService {

    private final OrderRepository orders;
    private final AuditRepository audit;

    OrderService(OrderRepository orders, AuditRepository audit) {
        this.orders = orders;
        this.audit = audit;
    }

    @Transactional
    public Mono<Void> place(Order order) {
        return orders.save(order)
                .flatMap(saved -> audit.record(saved.getId()))
                .then();
    }
}
```

Đây là snippet cần các repository/DTO và import tương ứng. Hai repository phải dùng cùng transaction-capable reactive backend/resource. Spring proxy/interceptor bọc publisher trả về; khi framework hoặc caller subscribe, transaction mở và các thao tác data access tham gia cùng context.

**Cần gọi qua Spring-managed proxy.** Lời gọi `this.place(...)` bên trong cùng class thường đi vòng qua transaction advice trong proxy mode. Dùng method của bean khác, tái cấu trúc service hoặc `TransactionalOperator` để đặt ranh giới rõ.

### 5.1. @Transactional không biến mã imperative thành reactive

Ví dụ không phù hợp với reactive manager:

```java
@Transactional
public void writeNow() {
    jdbcTemplate.update("UPDATE account SET balance = ...");
}
```

Method trả `void` và JDBC blocking cần `PlatformTransactionManager`, không phải `ReactiveTransactionManager`. Ngược lại, phương thức trả `Mono<Void>` thao tác với R2DBC phải chọn manager reactive.

Nếu ứng dụng có cả JDBC và R2DBC, chỉ định bean bằng `@Transactional("r2dbcTransactionManager")` hoặc cấu hình qualifier phù hợp; không để cùng một tên manager bị dùng sai mô hình.

### 5.2. Quy tắc rollback của annotation

`@Transactional` mặc định dùng propagation `REQUIRED`, isolation mặc định và mặc định rollback cho `RuntimeException` hoặc `Error`; checked exception thường không kích hoạt rollback trừ khi cấu hình `rollbackFor` hoặc rule tương đương.

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
public Mono<Void> performReactiveTask() {
    return executeSteps();
}
```

Đây là snippet giả định `BusinessCheckedException` và `executeSteps` tồn tại. Với `TransactionalOperator` programmatic, error signal trong transactional publisher dẫn tới rollback; với annotation declarative, các rollback rules của annotation phải được xét theo exception type.

Không chuyển error thành complete thành công bằng `onErrorResume` bên **trong** transaction rồi mong transaction tự rollback. Nếu đã xử lý lỗi thành success trước khi biên transaction nhận được error, Spring có thể commit. Muốn rollback dù sau đó trả kết quả fallback, hãy đặt fallback **sau** boundary hoặc dùng `ReactiveTransaction#setRollbackOnly()` trong callback.

## 6. TransactionalOperator: ranh giới tường minh

`TransactionalOperator` là lựa chọn programmatic tương ứng `TransactionTemplate` của imperative code. Có thể tạo từ manager:

```java
@Bean
TransactionalOperator transactionalOperator(
        ReactiveTransactionManager manager) {
    return TransactionalOperator.create(manager);
}
```

Spring Boot có thể tự cung cấp bean `TransactionalOperator` khi context có một `ReactiveTransactionManager` phù hợp; nếu có sẵn, không cần khai báo trùng. Ví dụ bean ở trên dùng khi muốn cấu hình rõ hoặc chạy ngoài Boot.

Hai cách sử dụng:

**Operator-style** — bọc publisher hiện có:

```java
Mono<Void> workflow = debit(accountA, 100)
        .then(credit(accountB, 100))
        .as(transactionalOperator::transactional);
```

**Callback-style** — transaction chỉ bao quanh phần được tạo trong callback:

```java
Flux<Receipt> results = transactionalOperator.execute(status ->
        reserveStock()
                .thenMany(loadReceipts()));
```

Trong callback, có thể đánh dấu rollback-only:

```java
Mono<Void> workflow = transactionalOperator
        .execute(status ->
                validateAndWrite()
                        .doOnNext(result -> {
                            if (!result.accepted()) {
                                status.setRollbackOnly();
                            }
                        }))
        .then();
```

Các snippet giả định method domain tồn tại. Với `execute(...)`, return type là `Flux<T>`; dùng `.then()` nếu logic cuối cùng không cần trả giá trị.

### 6.1. Chỗ đặt operator quyết định scope

Cả hai bước bên trong transaction:

```java
return firstWrite()
        .then(secondWrite())
        .as(transactionalOperator::transactional);
```

Chỉ `firstWrite` bên trong transaction; `secondWrite` ở bên ngoài:

```java
return firstWrite()
        .as(transactionalOperator::transactional)
        .then(secondWrite());
```

Sự khác biệt là vị trí `as(...)`. Hãy đặt transactional boundary quanh toàn bộ đơn vị nghiệp vụ cần atomic, không quanh một repository call rồi gọi tiếp các bước ngoài transaction.

### 6.2. TransactionalOperator không phải một connection duy nhất cố định

`TransactionalOperator` có thể là singleton bean và dùng chung giữa nhiều request; nó là **cấu hình boundary**, không phải connection đang mở. Mỗi subscription tạo transaction context phù hợp, được manager cấp resource và dọn lại khi hoàn thành.

Không tạo `R2dbcTransactionManager` mới cho mỗi request. Tạo manager/operator một lần ở cấu hình rồi tái sử dụng.

## 7. Tín hiệu Complete, Error và Cancel

Đời sống giao dịch phụ thuộc vào tín hiệu của publisher:

| Tín hiệu | Hành vi thường gặp | Ý nghĩa |
|---|---|---|
| `onComplete` sau khi các bước thành công | Commit | Unit of work hoàn tất |
| `onError` | Rollback theo policy manager/rollback rules | Có lỗi trong transaction |
| `cancel` | Rollback với Spring 5.3+ | Subscriber dừng nhận, transaction chưa hoàn tất |
| Không có subscription | Không begin | Publisher chỉ được khai báo |
| Subscription thứ hai | Một lần thực thi/transaction mới | Cold publisher chạy lại |

Đặc biệt, **cancel không phải onError**. Nó có thể do client đóng kết nối, user bỏ trang, timeout downstream, hoặc operator không còn muốn nhận item.

Spring Framework nêu rõ: kể từ 5.3, cancel signal dẫn đến rollback cho reactive transaction. Điều này khiến các operator như `take(n)`, `next()` và `timeout(...)` cần được xét kỹ nếu nằm **sau transactional publisher**.

### 7.1. next() và take() có thể khiến transaction rollback

Ví dụ có nhiều result:

```java
Flux<Row> rows = fetchRowsAndUpdateAudit()
        .as(transactionalOperator::transactional);

// next() lấy item đầu rồi cancel phần còn lại.
Mono<Row> first = rows.next();
```

Nếu source chưa complete, `next()` cancel upstream. Transaction nhận cancel và rollback, cho dù caller đã thấy một `Row`. Đừng coi `onNext` đã được phát là bằng chứng transaction commit.

Nếu cần hoàn thành toàn bộ workflow rồi chỉ trả item đầu, hãy thiết kế lại để query/transaction complete trước khi phát kết quả cuối; cân nhắc dùng `collectList` cho tập hữu hạn nhỏ hoặc một query chỉ trả đúng một giá trị. Không aggregate stream lớn/vô hạn.

### 7.2. onNext có thể phát trước commit

`Flux<T>` trong transaction có thể phát các item tới downstream trong lúc transaction vẫn mở. Nếu commit cuối cùng thất bại, caller có thể đã quan sát một phần dữ liệu.

Khi cần bảo đảm caller chỉ nhận “thành công” sau commit, dùng `Mono<Void>`/`Mono<Receipt>` được tính theo unit of work hoàn tất, hoặc buffer kết quả hữu hạn bên trong boundary và chỉ phát aggregate sau khi commit. Chú ý placement của `.as(transactionalOperator::transactional)` và các operator downstream.

Ví dụ:

```java
Mono<List<Item>> result = loadAndUpdate()
        .collectList()
        .as(transactionalOperator::transactional);
```

`Mono<List<Item>>` chỉ phát list sau khi nguồn `Flux` complete, nhưng trong quá trình transaction commit vẫn có thể có edge case tại ranh giới operator; hãy kiểm tra semantics của `TransactionalOperator` và test các lỗi commit thực tế. Không dùng ví dụ này để hứa exactly-once delivery hoặc phân tán.

## 8. Kiểm tra transaction Context khi chạy

Để chẩn đoán trong một reactive chain, Spring cung cấp:

```java
Mono<Boolean> active = TransactionSynchronizationManager
        .forCurrentTransaction()
        .map(TransactionSynchronizationManager::isActualTransactionActive);
```

`forCurrentTransaction()` trả manager gắn với transaction context hiện tại hoặc lỗi nếu không có context. Gọi nó **bên trong** pipeline được quản lý; không gọi ở bên ngoài rồi gán vào một `ThreadLocal` để dùng sau.

Thử bọc:

```java
Mono<Boolean> active = TransactionSynchronizationManager
        .forCurrentTransaction()
        .map(TransactionSynchronizationManager::isActualTransactionActive)
        .as(transactionalOperator::transactional);
```

Khi subscribe, callback ở trong transaction context và thường thấy `true`. Giá trị này cho biết một transaction đang active; không chứng minh hai query dùng cùng connection nếu bạn tự tạo raw connection không qua helper.

Dùng context API này cho diagnostics/integration đặc thù. Logic nghiệp vụ nên để Spring Data R2DBC tham gia resource qua `DatabaseClient`, thay vì tự chạm transaction context trong từng repository method.

## 9. Khi đổi thread, context có mất không?

Các operator Reactor như `publishOn` và `subscribeOn` có thể thay đổi thread thực thi nhưng vẫn truyền Reactor Context của cùng subscription:

```java
Mono<Void> flow = repository.writeOne()
        .publishOn(Schedulers.parallel())
        .then(repository.writeTwo())
        .as(transactionalOperator::transactional);
```

Cấu hình này vẫn là **một reactive pipeline**. Tuy nhiên, không nên chuyển query DB sang `parallel()` chỉ để “tăng tốc” khi chúng dùng chung một transaction-bound connection. Driver có thể không hỗ trợ nhiều query đồng thời trên cùng connection.

Những thao tác làm tách subscription hoặc bỏ context:

- Gọi `subscribe()` thủ công trên một publisher khác.
- Tạo callback chạy ngoài Reactor pipeline rồi thực hiện DB call độc lập.
- Chuyển sang `CompletableFuture`/executor mà không có cơ chế bridge context rõ.
- Gọi repository ở listener hoặc scheduled job và tưởng transaction của HTTP request vẫn còn.

`Reactor Context` khác logging MDC `ThreadLocal`. Muốn dùng MDC/tracing qua reactive chain, cấu hình context propagation phù hợp, đừng suy ra rằng MDC tự giữ transaction resource.

## 10. Transaction boundary với retry, timeout và fallback

### 10.1. Retry có thể tạo transaction mới cho mỗi attempt

```java
Mono<Void> attempt = writeSteps()
        .as(transactionalOperator::transactional);

return attempt.retryWhen(
        Retry.backoff(2, Duration.ofMillis(100)));
```

Nếu lần thực thi đầu phát error, transaction được rollback, sau đó `retryWhen` resubscribe toàn bộ transactional publisher để tạo attempt mới. Chỉ retry lỗi transient phù hợp; các side effect ngoài database có thể đã xảy ra.

Không đặt retry bừa bên trong transaction rồi kỳ vọng DB transaction vẫn hợp lệ sau lỗi SQL. Ví dụ PostgreSQL có thể đánh dấu transaction aborted sau statement failure và yêu cầu rollback trước khi chạy query tiếp.

### 10.2. Timeout có thể dẫn đến cancel và rollback

```java
Mono<Void> result = writeSteps()
        .as(transactionalOperator::transactional)
        .timeout(Duration.ofSeconds(3));
```

Khi downstream timeout, `timeout` có thể cancel nguồn, làm transaction rollback. Timeout không bảo đảm một external HTTP call hoặc side effect đã xảy ra được hoàn tác. Nếu cần timeout DB statement hoặc lock riêng, cấu hình ở driver/database theo tính năng hỗ trợ.

### 10.3. Fallback đặt trước/sau boundary khác nhau

Bắt lỗi **bên trong** rồi trả success:

```java
Mono<Void> result = writeSteps()
        .onErrorResume(error -> Mono.empty())
        .as(transactionalOperator::transactional);
```

Transaction thấy complete thành công và có thể commit các write trước lỗi.

Bắt lỗi **sau** khi boundary đã rollback:

```java
Mono<Void> result = writeSteps()
        .as(transactionalOperator::transactional)
        .onErrorResume(error -> fallbackAfterRollback(error));
```

Fallback chạy sau khi transaction trước đã kết thúc; nếu fallback ghi database, nó cần transaction riêng khi nghiệp vụ yêu cầu. Hai đoạn code không tương đương về atomicity.

## 11. Transaction settings và propagation

Các tham số phổ biến:

- `propagation`: REQUIRED, REQUIRES_NEW, SUPPORTS, MANDATORY, NOT_SUPPORTED...
- `isolation`: READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE... tùy backend.
- `timeout`: ngân sách thời gian của transaction theo manager/driver.
- `readOnly`: gợi ý hoặc policy read-only, mức thực thi phụ thuộc DB/driver.
- `rollbackFor` / `noRollbackFor`: rollback rules trong declarative transaction.

Ví dụ annotation:

```java
@Transactional(
        transactionManager = "transactionManager",
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        timeout = 5)
public Mono<Void> applyChanges() {
    return updateA().then(updateB());
}
```

Ví dụ programmatic:

```java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();
definition.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
definition.setTimeout(5);

TransactionalOperator operator =
        TransactionalOperator.create(manager, definition);
```

Đây là snippets cần dependency manager và methods minh họa. Hãy kiểm tra manager/driver hỗ trợ isolation và propagation nào. **REQUIRES_NEW** cần resource độc lập phù hợp và pool đủ connection; **NESTED** hoặc savepoint không được giả định hỗ trợ ở mọi reactive backend.

`readOnly=true` không phải cơ chế authorization: ứng dụng không nên dùng nó để thay thế quyền truy cập SQL. Isolation cao có thể làm tăng locking và contention, cần đo thông lượng/độ trễ.

## 12. Tích hợp hệ sinh thái: R2DBC, MongoDB và các hệ thống khác

### 12.1. Spring Data R2DBC

R2DBC là API reactive cho cơ sở dữ liệu quan hệ. `R2dbcTransactionManager` kết hợp với `DatabaseClient`, `R2dbcEntityTemplate` hoặc repository giúp cùng subscription dùng đúng connection.

Trong Spring Boot, dependency `spring-boot-starter-data-r2dbc`, một driver như `r2dbc-postgresql` hoặc `r2dbc-h2` và `spring.r2dbc.*` thường đủ để Boot auto-configure `ConnectionFactory` và manager (khi điều kiện phù hợp).

Connection pool R2DBC có lifecycle riêng. Không giữ transaction mở trong khi chờ HTTP call lâu hoặc xử lý CPU nặng. Khi transaction đang mở, connection thường bị giữ, làm giảm pool capacity.

### 12.2. Reactive MongoDB

`ReactiveMongoTransactionManager` làm việc với MongoDB `ClientSession` trong reactive context. MongoDB deployment phải hỗ trợ transaction (ví dụ replica set/sharded cluster đúng phiên bản). Không thể chỉ thêm annotation để biến standalone MongoDB không hỗ trợ transaction thành hệ thống có ACID transaction.

R2DBC transaction và MongoDB transaction là hai resource độc lập. Nếu workflow ghi cả hai, cần pattern như Saga/Outbox/compensation; một `@Transactional` trên R2DBC manager không tạo distributed two-phase commit cho cả MongoDB.

### 12.3. WebClient, Kafka và message broker

HTTP call, Kafka publish hoặc email không nằm trong cùng database transaction R2DBC. Nếu DB commit thất bại sau khi đã gửi Kafka message, message không tự thu hồi. Nếu DB commit thành công nhưng gửi message thất bại, dữ liệu và event có thể lệch.

**Transactional Outbox** thường là pattern phù hợp:

1. Trong một DB transaction, ghi entity nghiệp vụ **và** một row outbox.
2. Commit cả hai cùng nhau.
3. Một publisher/relay riêng đọc outbox, gửi event.
4. Đánh dấu published với retry/idempotency và monitoring.

Không viết một callback `doOnSuccess` để gửi event rồi coi việc gửi đó được bảo vệ bởi DB rollback. Chọn boundaries rõ và chấp nhận tính chất at-least-once cùng xử lý duplicate ở consumer.

## 13. Ví dụ hoàn chỉnh: Java 17 + Spring Boot 3.5.16 + R2DBC H2

Ví dụ dùng H2 in-memory qua driver R2DBC, Spring Boot auto-configure `ConnectionFactory` và `ReactiveTransactionManager`. Một service có hai phong cách:

- `savePair(...)` và `saveThenFail(...)` dùng `TransactionalOperator`.
- `saveWithAnnotation(...)` dùng `@Transactional`.

Integration test kiểm tra rằng writes chỉ chạy khi subscribe, commit lưu dữ liệu, lỗi rollback, mỗi lần subscribe chạy lại và declarative transaction hoạt động. Không cần HTTP server.

### 13.1. Cấu trúc project

```text
reactive-tx-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/ReactiveTxApplication.java
    │   ├── java/demo/LedgerService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/demo/LedgerServiceTest.java
```

### 13.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-tx-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-r2dbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-data-r2dbc` cung cấp integration R2DBC; `spring-boot-starter-aop` đảm bảo infrastructure proxy cho ví dụ `@Transactional`. `r2dbc-h2` là driver demo, không phải lựa chọn mặc định cho production. Boot BOM quản lý các dependency version tương thích.

### 13.3. application.properties

```properties
spring.application.name=reactive-tx-demo
spring.main.web-application-type=none
spring.r2dbc.url=r2dbc:h2:mem:///txdemo?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.username=sa
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
```

H2 `DB_CLOSE_DELAY=-1` giữ database in-memory tồn tại sau khi connection cuối đóng trong thời gian JVM còn chạy. Nó giúp `schema.sql` được khởi tạo trước khi test dùng các connection khác. Cấu hình này chỉ dành cho demo/test; không dùng H2 in-memory làm kho dữ liệu bền vững.

### 13.4. schema.sql

```sql
CREATE TABLE ledger_entries (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    label VARCHAR(200) NOT NULL
);
```

Spring Boot chạy script trong quá trình khởi tạo SQL theo `spring.sql.init.*`. Trong production, quản lý schema bằng công cụ migration và tránh chạy scripts test trên database thật.

### 13.5. ReactiveTxApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTxApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveTxApplication.class, args);
    }
}
```

### 13.6. LedgerService.java

```java
package demo;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.reactive.TransactionSynchronizationManager;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;

@Service
public class LedgerService {

    private final DatabaseClient db;
    private final TransactionalOperator operator;

    public LedgerService(
            DatabaseClient db,
            ReactiveTransactionManager manager) {

        this.db = db;
        this.operator = TransactionalOperator.create(manager);
    }

    private Mono<Void> insert(String label) {
        return db.sql(
                "INSERT INTO ledger_entries(label) VALUES (:label)")
                .bind("label", label)
                .then();
    }

    // Success -> commit both inserts.
    public Mono<Void> savePair(String key) {
        return insert(key + "-A")
                .then(insert(key + "-B"))
                .as(operator::transactional);
    }

    // Error -> roll back the first insert.
    public Mono<Void> saveThenFail(String key) {
        return insert(key + "-A")
                .then(Mono.<Void>error(
                        new IllegalStateException("planned failure")))
                .as(operator::transactional);
    }

    // Spring AOP applies the reactive transaction advice.
    @Transactional
    public Mono<Void> saveWithAnnotation(String key) {
        return insert(key + "-A")
                .then(insert(key + "-B"));
    }

    // Read-only diagnostic query outside transactional boundary.
    public Mono<Long> count(String label) {
        return db.sql(
                "SELECT COUNT(*) AS total "
                + "FROM ledger_entries WHERE label = :label")
                .bind("label", label)
                .map((row, metadata) ->
                        ((Number) row.get("total")).longValue())
                .one();
    }

    // Context is inspected inside a new reactive transaction.
    public Mono<Boolean> transactionIsActive() {
        return TransactionSynchronizationManager
                .forCurrentTransaction()
                .map(TransactionSynchronizationManager::
                        isActualTransactionActive)
                .as(operator::transactional);
    }
}
```

Giải thích các điểm then chốt:

1. Constructor nhận một `ReactiveTransactionManager` do Boot auto-configure; khởi tạo operator một lần để reuse.
2. `insert` trả `Mono<Void>` lazy từ `DatabaseClient`, không chạy SQL ngay khi được gọi.
3. `savePair` đưa hai lệnh insert vào cùng transactional publisher bằng `then` và `as`.
4. `saveThenFail` phát `IllegalStateException` sau insert đầu, làm toàn bộ transaction rollback.
5. `saveWithAnnotation` trả publisher từ Spring-managed service bean; AOP xử lý transaction lúc subscribe.
6. `count` không tham gia transaction ghi ở trước, vì test subscribe nó **sau** khi transactional publisher kết thúc.
7. `transactionIsActive` đọc transaction context ngay trong boundary và phải trả `true` khi chạy đúng.

### 13.7. LedgerServiceTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class LedgerServiceTest {

    @Autowired
    LedgerService service;

    @Test
    void commitsAllWritesOnNormalCompletion() {
        StepVerifier.create(service.savePair("success"))
                .verifyComplete();

        StepVerifier.create(service.count("success-A"))
                .expectNext(1L)
                .verifyComplete();

        StepVerifier.create(service.count("success-B"))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void rollsBackWhenPublisherFails() {
        StepVerifier.create(service.saveThenFail("failure"))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && error.getMessage().equals("planned failure"))
                .verify();

        StepVerifier.create(service.count("failure-A"))
                .expectNext(0L)
                .verifyComplete();
    }

    @Test
    void doesNotOpenTransactionUntilSubscription() {
        Mono<Void> notYetSubscribed =
                service.savePair("deferred");

        StepVerifier.create(service.count("deferred-A"))
                .expectNext(0L)
                .verifyComplete();

        StepVerifier.create(notYetSubscribed)
                .verifyComplete();

        StepVerifier.create(service.count("deferred-A"))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void everySubscriptionRunsAgain() {
        Mono<Void> cold = service.savePair("repeated");

        StepVerifier.create(cold).verifyComplete();
        StepVerifier.create(cold).verifyComplete();

        StepVerifier.create(service.count("repeated-A"))
                .expectNext(2L)
                .verifyComplete();

        StepVerifier.create(service.count("repeated-B"))
                .expectNext(2L)
                .verifyComplete();
    }

    @Test
    void transactionalAnnotationUsesReactiveManager() {
        StepVerifier.create(service.saveWithAnnotation("annotated"))
                .verifyComplete();

        StepVerifier.create(service.count("annotated-A"))
                .expectNext(1L)
                .verifyComplete();

        StepVerifier.create(service.count("annotated-B"))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void transactionContextExistsDuringExecution() {
        StepVerifier.create(service.transactionIsActive())
                .expectNext(true)
                .verifyComplete();
    }
}
```

Chạy từ thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả kỳ vọng theo logic kiểm thử:** sáu `@Test` hoàn tất thành công, không có assertion failure; `mvn` trả exit code `0`. Các test kiểm tra kết quả DB thông qua query thật chứ không chỉ mock method. Các dòng log Spring Boot/H2 có thể khác nhau giữa môi trường; không giả định stdout cố định ngoài kết quả test thành công.

Có thể khởi động application bằng:

```bash
mvn spring-boot:run
```

Ứng dụng demo không mở HTTP server vì `web-application-type=none`, nên không có endpoint REST để gọi bằng `curl`. Với project này, `mvn test` là cách minh họa tính đúng đắn của transaction rõ nhất.

**Giới hạn của ví dụ:** dùng một in-memory database và một transaction manager. Nó không chứng minh transaction phân tán, khả năng rollback side effect HTTP/Kafka, sự hỗ trợ mọi isolation/propagation của các driver khác hoặc behavior của hệ thống chịu tải production.

## 14. Bài tập mở rộng sau ví dụ

Có thể bổ sung các test sau để hiểu sâu hơn:

### 14.1. Thử lỗi sau hai insert

Đổi `saveThenFail` để thực hiện hai insert rồi phát `Mono.error`. Cả hai row phải không xuất hiện sau rollback. Điều này chứng minh toàn bộ unit of work có chung boundary, không chỉ lệnh đầu tiên.

### 14.2. Thử đặt operator sai vị trí

Tạo method:

```java
public Mono<Void> partialTransaction(String key) {
    return insert(key + "-A")
            .as(operator::transactional)
            .then(insert(key + "-B"));
}
```

Nếu bước B phát lỗi, bước A đã commit nên không tự rollback. Đặt operator ngoài cả hai bước để có atomicity. Không thêm method này vào logic production; dùng test để minh họa scope.

### 14.3. Thử cancellation sau item đầu

Tạo một `Flux` bên trong transaction có ít nhất hai item, rồi dùng `next()` ở downstream. Quan sát rằng cancellation có thể dẫn tới rollback. Dùng kiểm thử có deadline và query xác minh, đừng chỉ dựa vào `doOnCancel` log. Phải tách thời điểm item được emit và thời điểm transaction commit.

### 14.4. Thử đổi thread

Thêm `publishOn(Schedulers.parallel())` giữa hai thao tác DB trong một pipeline tuần tự. Giao dịch vẫn nên được truyền qua Reactor Context. Không dùng `flatMap` với concurrency cao trên cùng transaction connection.

### 14.5. Thử retry bao ngoài

Bọc một transactional publisher có thể thất bại transient bằng `retryWhen` ở **ngoài** boundary. Mỗi attempt nên là một subscription mới với transaction mới. Kiểm tra số lần ghi, lock timeout và idempotency thay vì chỉ kiểm tra response cuối.

## 15. Lỗi thường gặp

1. **Nghĩ gọi method trả Mono là đã commit.** Reactive transaction chỉ bắt đầu khi có subscription.
2. **Nhầm ThreadLocal với Reactor Context.** Transaction context reactive đi theo subscriber, không gắn cố định với thread.
3. **Tự gọi subscribe trong service.** Tạo subscription ngoài boundary và khiến caller không kiểm soát error/cancel.
4. **Dùng JDBC blocking dưới ReactiveTransactionManager.** JDBC không tự dùng transaction-bound R2DBC connection.
5. **Dùng PlatformTransactionManager cho reactive service.** Chọn đúng manager theo backend và return type.
6. **Tự tạo raw connection với ConnectionFactory.create().** Có thể bypass context-bound resource; dùng DatabaseClient hoặc ConnectionFactoryUtils.
7. **Subscribe lại cold publisher có side effect.** Có thể chạy hai transaction và ghi hai lần; cần idempotency.
8. **Đặt TransactionalOperator trước bước DB cuối.** Bước cuối nằm ngoài transaction, không còn atomic.
9. **Bắt lỗi bằng onErrorResume bên trong transaction.** Transaction có thể thấy complete và commit dữ liệu trước lỗi.
10. **Coi onError luôn rollback như nhau trong mọi annotation.** @Transactional có rollback rules; checked exception mặc định khác RuntimeException.
11. **Cho rằng onNext đồng nghĩa commit.** Flux có thể phát item trước khi transaction kết thúc.
12. **Dùng next/take downstream không xét cancellation.** Spring reactive transaction rollback khi cancel.
13. **Nghĩ timeout luôn rollback mọi side effect.** Cancel/rollback DB không hoàn tác email, Kafka hoặc HTTP đã gửi.
14. **Cho rằng publishOn làm mất transaction.** Reactor Context được duy trì trong cùng subscription; vấn đề thực sự là tách pipeline hoặc dùng blocking.
15. **Chạy query DB đồng thời trên một transaction-bound connection.** Driver có thể không cho phép; dùng tuần tự nếu phù hợp.
16. **Gọi @Transactional method qua this trong proxy mode.** Self-invocation thường bỏ qua AOP advice.
17. **Định nghĩa nhiều transaction manager mà không chọn qualifier.** Có thể chọn sai resource hoặc lỗi ambiguity.
18. **Nghĩ @Transactional tạo distributed transaction.** Một R2DBC manager chỉ bảo vệ resource nó quản lý.
19. **Mở transaction rồi gọi HTTP API chậm.** Giữ connection và lock lâu, tăng pool contention.
20. **Đặt retry bên trong transaction sau SQL error.** Transaction có thể đã bị DB đánh dấu aborted; rollback rồi retry bằng transaction mới.
21. **Giả định readOnly là quyền bảo mật.** Đây là flag/policy có mức hỗ trợ khác nhau, không thay authorization.
22. **Giả định mọi driver hỗ trợ NESTED/REQUIRES_NEW như nhau.** Cần kiểm tra savepoint, connection và propagation.
23. **Lưu ReactiveTransaction vào field singleton.** Transaction status/resource là theo execution, không để chia sẻ giữa request.
24. **Đọc transaction context ngoài boundary rồi đoán có active transaction.** Dùng forCurrentTransaction trong pipeline đang được quản lý.
25. **Không kiểm tra rollback bằng dữ liệu thật.** Một unit test mock không chứng minh server DB có rollback.
26. **Trộn @Transactional với TransactionalOperator vô ý.** Có thể tạo nested/participating boundary khó hiểu; chọn một owner nghiệp vụ.
27. **Thiếu timeout/cleanup cho connection.** Transaction có thể chiếm pool lâu hoặc bị treo nếu external I/O không có deadline.
28. **Không kiểm tra schema init hoặc migration.** H2 in-memory khác PostgreSQL/MySQL về isolation/DDL/SQL syntax.
29. **Nhầm reactive transaction với exactly-once delivery.** Commit DB không đảm bảo event ngoài DB được gửi một lần.
30. **Chỉ test happy path.** Cần test rollback, cancel, error handling, retry, timeout và context boundary.

## 16. Checklist production

Trước khi triển khai giao dịch reactive, hãy kiểm tra:

- Data access đang dùng R2DBC, reactive MongoDB hay JDBC/JPA?
- `ReactiveTransactionManager` có đúng resource và chỉ có một candidate phù hợp không?
- `@Transactional` method trả `Mono`/`Flux` và được gọi qua Spring proxy không?
- Các bước data access có cùng Reactor Context và cùng transaction boundary không?
- Có `subscribe()` thủ công, callback ngoài pipeline hoặc `block()` trong reactive service không?
- Có tự tạo connection ngoài `ConnectionFactoryUtils` hoặc tích hợp Spring Data không?
- Ranh giới operator được đặt quanh **tất cả** write cần atomic không?
- Khi xử lý exception, boundary nhìn thấy error để rollback hay chỉ thấy success?
- Với `Flux`, caller có thể `take`/`next`/timeout làm cancel trước commit không?
- Có resubscription do retry, repeat, cache, HTTP retry hoặc duplicate message không?
- Retry có chạy trong transaction mới và chỉ dành cho lỗi transient/idempotent?
- Backend hỗ trợ isolation/timeout/propagation đã khai báo không?
- Có giao dịch mở quá lâu vì gọi external HTTP/Kafka hoặc xử lý CPU nặng không?
- R2DBC pool đủ capacity cho số transaction đồng thời và lock time hợp lý không?
- Giao tiếp giữa DB và Kafka/HTTP có cần transactional outbox hoặc Saga không?
- Có metrics cho active transaction, connection pool, pending acquire, lock và timeout không?
- Có test DB thật cho commit, rollback, cancellation, concurrency và startup/shutdown không?
- Có test transaction manager qualifier nếu ứng dụng có nhiều backend không?
- Có giới hạn payload/query result và tránh một Flux transaction vô hạn không?

**Ghi nhớ:** Reactive transaction có **cùng mục tiêu atomicity** như transaction imperative nhưng khác ở cách ràng buộc lifecycle: transaction bắt đầu theo **subscription**, trạng thái/resource đi theo **Reactor Context**, và mỗi lần resubscribe có thể mở một transaction mới. `R2dbcTransactionManager` quản lý connection cho một `ConnectionFactory`; `@Transactional` và `TransactionalOperator` tạo boundary để các query Spring R2DBC cùng context tham gia. Complete thường commit, error rollback theo policy, cancel dẫn tới rollback. Không tách subscription, không dùng blocking JDBC thay R2DBC, và không coi giao dịch một database là giao dịch phân tán.

## Tài liệu tham khảo

- Spring Framework — [Declarative Transactions: Reactive return types and Reactor context](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).
- Spring Framework — [Programmatic Transaction Management: TransactionalOperator, cancellation, transaction settings](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html).
- Spring Framework — [Using @Transactional and rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- Spring Framework — [Data Access with R2DBC: ConnectionFactoryUtils and R2dbcTransactionManager](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html).
- Spring Framework — [TransactionalOperator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/reactive/TransactionalOperator.html).
- Spring Framework — [TransactionSynchronizationManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/reactive/TransactionSynchronizationManager.html).
- Spring Boot 3.5 — [R2DBC database configuration](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html).
- Spring Boot 3.5 — [SQL script initialization with R2DBC](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html).
- Spring Boot 3.5.16 — [TransactionAutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/transaction/TransactionAutoConfiguration.html).
- R2DBC H2 — [Driver connection URL and options](https://github.com/r2dbc/r2dbc-h2).
- Project Reactor — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
