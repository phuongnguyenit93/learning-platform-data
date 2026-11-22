# Hủy hoặc lỗi trong giao dịch reactive và trách nhiệm giải phóng kết nối

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Tích hợp hệ sinh thái  
**Bài học:** Hủy hoặc lỗi trong giao dịch và trách nhiệm giải phóng kết nối

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt ba tín hiệu kết thúc `onComplete`, `onError` và `cancel` của Reactive Streams; hiểu vì sao cancel không phải một exception thông thường.
2. Giải thích giao dịch reactive gắn với **Reactor Context và subscription**, thay vì ThreadLocal như giao dịch JDBC imperative.
3. Mô tả vòng đời connection: acquire → begin transaction → thực thi lệnh → commit/rollback → reset/close hoặc trả pool.
4. Sử dụng `R2dbcTransactionManager`, `TransactionalOperator` hoặc `@Transactional` để Spring chịu trách nhiệm hoàn tất transaction.
5. Hiểu quy tắc Spring Framework 5.3+: **cancel trong reactive transaction dẫn đến rollback**, không phải commit.
6. Nhận diện lỗi do `take`, `next`, `timeout`, client disconnect hoặc downstream hủy subscription.
7. Phân biệt rollback của transaction với việc giải phóng connection; không coi việc rollback là đã đóng connection.
8. Dùng `Mono.usingWhen`/`Flux.usingWhen` cho tài nguyên reactive quản lý thủ công, không sử dụng `doFinally` để khởi động cleanup bất đồng bộ rồi bỏ mặc.
9. Kiểm thử commit, rollback trên error, rollback trên cancel và trả connection về pool bằng Spring Boot 3.3.5, R2DBC H2, Reactor Test.
10. Đặt timeout, giới hạn pool, log và metrics để phát hiện connection leak trong vận hành.

## 1. Bối cảnh: một transaction đang chạy dở

Xét dịch vụ lưu hai bản ghi:

```text
HTTP/WebSocket/RSocket client
          |
          v
Reactive service (Mono/Flux)
          |
          v
TransactionalOperator hoặc @Transactional
          |
          v
R2dbcTransactionManager
          |
          v
ConnectionFactory -> R2DBC Connection -> Database
```

Một giao dịch chỉ đúng khi có ranh giới hoàn tất rõ ràng. Nếu cả hai câu lệnh ghi thành công và publisher kết thúc bình thường thì commit; nếu công việc lỗi thì rollback; nếu subscriber hủy giữa chừng thì transaction cũng phải được kết thúc và tài nguyên phải được trả lại.

Điểm khó là Reactive Streams cho phép caller **không đọc hết dữ liệu**. Một browser đóng kết nối, client timeout hoặc toán tử `take(1)` đều có thể khiến subscription bị cancel. Đó không nhất thiết là lỗi của database; nó là tín hiệu rằng downstream không còn cần phần dữ liệu phía upstream.

Nếu bỏ qua cancel, connection có thể vẫn nằm trong trạng thái transaction mở, chiếm một slot của pool. Khi nhiều request như vậy xảy ra, toàn bộ dịch vụ có thể hết connection dù database vẫn hoạt động.

## 2. Ba cách một publisher kết thúc

Một subscription có thể gặp:

| Kết cục | Ý nghĩa | Reactor có thể quan sát bằng | Tác động mong đợi tới transaction |
| --- | --- | --- | --- |
| **Complete** | Publisher đã hoàn thành thành công (có hoặc không có dữ liệu) | `doOnComplete` trên Flux, `doOnSuccess` trên Mono, `doFinally(ON_COMPLETE)` | Commit nếu transaction không bị đánh dấu rollback-only. |
| **Error** | Publisher kết thúc bởi lỗi terminal `onError` | `doOnError`, `doFinally(ON_ERROR)` | Rollback theo chính sách transaction; với `TransactionalOperator` lỗi từ publisher dẫn đến rollback. |
| **Cancel** | Subscriber chủ động không muốn nhận thêm dữ liệu | `doOnCancel`, `doFinally(CANCEL)` | Spring reactive transaction từ 5.3 rollback trên cancel. |

Lưu ý: `cancel` **không phải** một `onError` và không mang theo nguyên nhân lỗi. Reactor không thể biết việc hủy do người dùng rời trang, do `timeout`, do `take(1)`, do `next()` hay do downstream ngừng tiêu thụ. Vì vậy hạ tầng giao dịch không thể coi cancel là thành công.

Ví dụ quan sát tín hiệu:

```java
Flux<Integer> source = Flux.range(1, 10)
        .doOnCancel(() -> System.out.println("cancel observed"))
        .doFinally(signal ->
                System.out.println("finally=" + signal));

source.take(2).collectList();
```

Đây chỉ mới là **khai báo pipeline**; chưa có subscription nên chưa in gì. Khi subscribe vào publisher được tạo bởi `take(2)`, downstream lấy đủ hai phần tử và hủy upstream. `doOnCancel` và `doFinally` trên **source** sẽ ghi nhận cancel. Nếu đặt `doFinally` ở phía **sau** `take(2)`, nó có thể thấy COMPLETE của pipeline đã biến thành công việc hữu hạn. Vị trí operator vì thế rất quan trọng khi đọc log.

`Mono.empty()` hoàn thành bình thường và thường dẫn tới commit; “không có item” **không tự động** đồng nghĩa “cần rollback”.

## 3. Giao dịch reactive khác giao dịch imperative

### 3.1. Transaction context nằm trong Reactor Context

Với JDBC thông thường, transaction gắn với ThreadLocal và thread đang chạy. Với Spring reactive transaction, hạ tầng dùng Reactor Context gắn với subscriber và subscription.

```text
Subscriber
   |
   +--- Reactor Context: TransactionContext
             |
             +--- resource holder: R2DBC Connection
             |
             +--- TransactionSynchronization
   |
   +--- db.queryA() ----+
   |                    | cùng transaction context
   +--- db.queryB() ----+
```

Những thao tác truy cập R2DBC thông qua Spring `DatabaseClient` hoặc Spring Data R2DBC có thể tham gia connection được bind trong context của transaction. Hai phương thức không cần chạy trên cùng một Java Thread miễn là pipeline giữ được Reactor Context theo cách framework hỗ trợ.

Lưu ý:

- `publishOn` và `subscribeOn` của Reactor không tự động làm mất Reactor Context khi dùng đúng cách. Vấn đề thường là **tách pipeline thành subscription khác**, tự gọi `subscribe()` ở bên trong service, hoặc rời khỏi reactive context.
- `ThreadLocal` riêng của ứng dụng không thay thế được `Reactor Context` cho transaction reactive.
- Một `@Transactional` reactive method phải trả `Publisher` hoặc reactive type phù hợp để interceptor bao được subscription. Method chỉ trả `void` hoặc tự `subscribe()` bên trong không phải ranh giới transaction reactive đúng.
- Proxy-based `@Transactional` không áp dụng khi một method trong cùng object tự gọi method transactional qua `this`, nếu không đi qua proxy.

### 3.2. Ai giữ connection?

`ConnectionFactory` tạo R2DBC `Connection`. `R2dbcTransactionManager` lấy connection, bắt đầu transaction, gắn connection vào transaction context và quản lý kết thúc.

`DatabaseClient`/Spring Data R2DBC hoạt động qua cơ chế lấy connection có nhận biết transaction. Vì thế, trong một pipeline hợp lệ, những database call thuộc cùng transaction có thể dùng connection transaction-bound thay vì mỗi lệnh tự mở một connection độc lập.

`ConnectionFactoryUtils.getConnection` và `releaseConnection` là API hỗ trợ transaction-bound resource cho mã tích hợp thấp tầng. Không gọi `ConnectionFactory.create()` trực tiếp bên trong transaction Spring rồi mặc nhiên nghĩ connection mới đó đã tham gia transaction hiện tại: đó có thể là **connection khác** ngoài ranh giới commit/rollback của Spring.

## 4. Vòng đời của transaction và connection

Đường đi mong đợi:

```text
subscribe
  |
  v
Acquire R2DBC Connection từ pool/driver
  |
  v
Begin transaction
  |
  v
Các câu lệnh SQL reactive
  |
  +---- onComplete ---> COMMIT --------+
  |                                    |
  +---- onError ------> ROLLBACK ------+
  |                                    |
  +---- cancel -------> ROLLBACK ------+
                                       |
                                       v
                             Cleanup transaction state
                                       |
                                       v
                         Release connection / return to pool
```

**Commit/rollback** quyết định số phận thay đổi dữ liệu trong transaction. **Release/close** quyết định số phận tài nguyên connection. Hai thao tác khác nhau; muốn bảo đảm tài nguyên không bị giữ mãi phải làm cả hai theo lifecycle thích hợp.

Trong pool R2DBC, gọi `Connection.close()` trên connection wrapper thường **trả connection về pool** để có thể tái sử dụng; nó không nhất thiết đóng socket vật lý. Với connection không qua pool, close thường đóng tài nguyên driver. Không đồng nhất “close” với “ngắt TCP”.

`Connection.close()` trong R2DBC trả một `Publisher<Void>`; chỉ tạo publisher mà không subscribe/compose thì cleanup không được thực thi theo cách reactive. Spring transaction manager đã xử lý lifecycle này cho connection do Spring quản lý. Ứng dụng không nên tự close connection đang được transaction manager sở hữu.

### 4.1. Sau rollback vẫn phải release

Khi transaction lỗi:

1. Phát hiện terminal error hoặc cancellation.
2. Yêu cầu rollback.
3. Tháo resource binding khỏi transaction context.
4. Reset trạng thái cần thiết để connection dùng lại.
5. Release connection về pool hoặc đóng driver connection.

Trong vận hành thực, rollback hoặc cleanup cũng có thể lỗi vì connection bị ngắt hoặc database không phản hồi. Không hứa mọi connection sẽ được tái sử dụng thành công sau mọi lỗi mạng; cần metric, timeout và kiểm tra pool để phát hiện lỗi cleanup.

### 4.2. Trách nhiệm ở từng tầng

| Tầng | Trách nhiệm |
| --- | --- |
| Caller / HTTP handler | Subscribe/return publisher đúng lifecycle; đặt timeout, không nuốt lỗi vô ý, hủy khi không còn cần. |
| Service | Xác định ranh giới nghiệp vụ; không tự subscribe hoặc tách database calls khỏi transaction; không block event loop. |
| Spring transaction manager | Begin, commit, rollback, transaction context và cleanup của connection transaction-bound. |
| R2DBC driver | Thực thi lệnh, rollback/commit và close theo SPI. |
| Connection pool | Cấp connection có giới hạn, nhận connection được release, validate/reset/loại connection hỏng theo cấu hình. |
| Người viết mã low-level | Nếu tự acquire connection thì phải compose cleanup cho complete, error và cancel. |
| Hệ thống vận hành | Theo dõi acquired/idle/pending, query chậm, timeout, rollback failure, leak và shutdown. |

## 5. Spring TransactionalOperator: cách an toàn mặc định

`TransactionalOperator` là operator để đóng khung một `Mono` hoặc `Flux` trong reactive transaction. Đây là lựa chọn nên dùng cho programmatic transaction management.

```java
Mono<Void> operation =
        insertFirst()
                .then(insertSecond())
                .as(transactionalOperator::transactional);
```

Transaction bắt đầu khi có subscription, các lệnh chạy theo thứ tự; khi publisher hoàn tất sẽ commit. Nếu bất kỳ lệnh nào phát error, operator đi vào rollback. Nếu subscriber cancel publisher transaction, operator thực hiện rollback theo semantics của Spring Framework 5.3+.

Có hai phong cách:

**Operator-style:**

```java
return repo.debit(accountId, amount)
        .then(repo.credit(otherId, amount))
        .as(transactionalOperator::transactional);
```

**Callback-style:**

```java
return transactionalOperator.execute(status ->
        repo.debit(accountId, amount)
                .then(repo.credit(otherId, amount)))
        .then();
```

`execute` có thể nhận `ReactiveTransaction status` và gọi `status.setRollbackOnly()` nếu nghiệp vụ quyết định không commit dù không muốn phát error. Tránh dựng transaction bằng cách tự gọi từng phương thức trên `ReactiveTransactionManager` nếu không cần, vì bạn sẽ phải xử lý nhiều đường lỗi, rollback failure và cancellation hơn.

### 5.1. Cấu hình TransactionalOperator

```java
@Configuration
class TxConfig {
    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
```

Đối với R2DBC, Boot thường cấu hình `R2dbcTransactionManager` khi có `ConnectionFactory` và dependency tương ứng. Nếu có nhiều transaction manager, chỉ định đúng manager để không vô tình dùng transaction manager kiểu imperative.

### 5.2. @Transactional cho reactive service

Cũng có thể dùng annotation:

```java
@Service
class PaymentService {
    private final PaymentRepository repository;

    PaymentService(PaymentRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Void> transfer(long from, long to, long amount) {
        return repository.subtract(from, amount)
                .then(repository.add(to, amount));
    }
}
```

Đoạn này chỉ minh họa việc khai báo ranh giới; `PaymentRepository` và các method là API nghiệp vụ giả định, không phải phần của chương trình chạy ở cuối bài.

Không gọi `transfer(...).subscribe()` bên trong service rồi trả về `Mono.empty()`, vì công việc đã tách sang subscription riêng. Caller bên ngoài sẽ thấy một transaction khác với công việc database thực tế.

Với annotation, các quy tắc rollback của `@Transactional` (mặc định RuntimeException/Error; checked exception cần quy tắc `rollbackFor` khi phù hợp) vẫn phải được xem xét. Đừng suy từ ví dụ `TransactionalOperator` rằng mọi policy rollback cho mọi loại exception ở annotation đều giống hệt nhau.

## 6. Error trong transaction: rollback và nguy cơ nuốt lỗi

### 6.1. Lỗi thực sự đi ra khỏi transaction boundary

```java
Mono<Void> tx =
        insertRecord(10L)
                .then(Mono.<Void>error(
                        new IllegalStateException("forced failure")))
                .as(transactionalOperator::transactional);
```

Lệnh insert hoàn tất trước khi `Mono.error` phát tín hiệu lỗi. TransactionalOperator thấy error, rollback và phát lỗi tới caller. Khi query lại từ một transaction mới, bản ghi 10 không tồn tại nếu rollback thành công.

`onErrorMap` chỉ đổi kiểu lỗi; nếu vẫn phát error thì transaction thường vẫn rollback. `doOnError` dùng để log hoặc metric nhưng không tiêu thụ lỗi.

### 6.2. Nuốt lỗi bên trong ranh giới có thể khiến commit

```java
Mono<Void> tx =
        insertRecord(11L)
                .then(Mono.<Void>error(
                        new IllegalStateException("recoverable")))
                .onErrorResume(error -> Mono.empty())
                .as(transactionalOperator::transactional);
```

`onErrorResume` xử lý error **trước khi** transaction operator quan sát nó. Từ góc nhìn TransactionalOperator, publisher kết thúc bình thường. Nếu không `setRollbackOnly`, nó có thể commit bản ghi 11. Đây là một lỗi logic quan trọng.

Nếu cần fallback sau khi rollback, đặt handler bên **ngoài** transaction:

```java
return insertRecord(12L)
        .then(Mono.<Void>error(
                new IllegalStateException("rejected")))
        .as(transactionalOperator::transactional)
        .onErrorResume(IllegalStateException.class,
                error -> Mono.empty());
```

Khi đó error đi qua transaction boundary, rollback được thực hiện rồi caller mới nhận kết quả fallback. Không xử lý tất cả exception như nhau; rollback failure, connection failure và business validation cần chính sách khác nhau.

### 6.3. setRollbackOnly khi muốn trả kết quả nghiệp vụ

Nếu muốn trả một kết quả hợp lệ nhưng không commit:

```java
Mono<String> result = transactionalOperator
        .execute(status -> performChecks()
                .flatMap(accepted -> {
                    if (!accepted) {
                        status.setRollbackOnly();
                        return Mono.just("REJECTED");
                    }
                    return persistChanges().thenReturn("ACCEPTED");
                }))
        .single();
```

`performChecks` và `persistChanges` là method minh họa, không nằm trong project chạy ở mục 12. Với các luồng dạng `Flux`, không gọi `single()` nếu callback có thể phát 0 hoặc nhiều item.

### 6.4. Lỗi sau commit không thể tự rollback

Nếu transaction đã commit và sau đó caller gặp lỗi lúc gửi HTTP response, ghi log hoặc gọi API khác, không thể “rollback” database đã commit chỉ bằng việc phát `Mono.error` ở downstream. Cần thiết kế outbox, trạng thái nghiệp vụ và idempotency nếu giao dịch phải phối hợp với external system.

## 7. Cancel trong transaction: Spring Framework 5.3+ rollback

Tài liệu Spring Framework xác nhận: từ phiên bản **5.3**, cancel signal trong reactive transaction dẫn tới rollback. Lý do là cancellation không cho biết transaction đã làm đủ công việc hay chưa và cũng không cho biết nguyên nhân hủy.

Những operator thường tạo cancellation:

- `Flux.take(n)`: lấy đủ n item thì hủy upstream.
- `Flux.next()`: lấy item đầu tiên rồi hủy nguồn Flux.
- `Mono.timeout(Duration)`/`Flux.timeout(Duration)`: khi quá hạn, cancel nguồn gốc và phát TimeoutException cho downstream.
- Client WebFlux ngắt kết nối hoặc stream bị đóng: có thể dẫn đến cancel pipeline, tùy lifecycle adapter và thời điểm.
- `Disposable.dispose()` hoặc `Subscription.cancel()`: application chủ động hủy.

### 7.1. Bẫy: return Flux trong một transaction ghi dữ liệu

```java
Flux<Long> tx = insertRecord(20L)
        .thenMany(Flux.just(1L, 2L, 3L))
        .as(transactionalOperator::transactional);

Mono<Long> first = tx.next();
```

`next()` lấy phần tử đầu rồi cancel phần còn lại của transaction Flux. Mặc dù SQL insert có thể đã thực hiện, transaction có thể **rollback** vì publisher chưa complete. Đừng suy rằng nhận được item nghĩa là transaction đã commit.

Hãy kiểm tra vị trí đặt toán tử:

```java
Flux<Long> risky = expensiveFlux()
        .as(transactionalOperator::transactional)
        .take(1); // take downstream có thể cancel transaction.
```

Nếu chỉ muốn lấy một record, hãy thay đổi truy vấn để trả một record rồi cho transaction hoàn tất tự nhiên, ví dụ `DatabaseClient...one()` hoặc SQL `LIMIT 1` theo database, thay vì làm một stream dài hạn rồi hủy.

### 7.2. Đừng đặt transaction quanh stream sống vô hạn

```java
Flux<Event> live =
        databaseChanges()
                .concatWith(liveNotifications())
                .as(transactionalOperator::transactional);
```

Đoạn minh họa này có thể giữ connection và transaction đến khi client hủy hoặc nguồn complete; nếu liveNotifications là stream vô hạn, transaction sẽ kéo dài rất lâu. Đó thường là thiết kế sai.

Phương án thường tốt hơn: giới hạn transaction trong thao tác đọc/ghi hữu hạn, commit và release connection **trước khi** phát dữ liệu live:

```java
Mono<List<Event>> initialSnapshot =
        readFiniteSnapshot()
                .collectList()
                .as(transactionalOperator::transactional);

Flux<Event> feed =
        initialSnapshot.flatMapMany(snapshot ->
                Flux.fromIterable(snapshot)
                        .concatWith(liveNotifications()));
```

Đây là ví dụ minh họa cho nguyên tắc tách ranh giới; method Event là API giả định. Chỉ dùng khi snapshot có kích thước giới hạn; nếu dữ liệu lớn, dùng paging/chunk transaction và cơ chế consistency phù hợp, không gom vô hạn vào list.

### 7.3. Cancel không phải rollback thần kỳ

Nếu transaction đã commit trước khi cancellation tới, cancellation không hoàn tác commit. Nếu database/driver mất kết nối giữa lúc commit, trạng thái có thể không xác định từ góc nhìn caller. Tránh hứa rằng “client timeout thì chắc chắn database không đổi”.

Với thao tác quan trọng, trả ID/idempotency key và có cơ chế hỏi lại kết quả; không tự retry bừa vì nguy cơ ghi hai lần.

## 8. Giải phóng connection: dùng Spring-managed API trước tiên

Spring `DatabaseClient` và Spring Data R2DBC đã tích hợp với transaction manager. Đây là lựa chọn an toàn mặc định cho thao tác database trong service reactive.

```java
Mono<Void> insert = databaseClient
        .sql("INSERT INTO audit_events(event_id, label) "
                + "VALUES (:id, :label)")
        .bind("id", 100L)
        .bind("label", "hello")
        .fetch()
        .rowsUpdated()
        .then();

return insert.as(transactionalOperator::transactional);
```

Mã trên không cần tự acquire/close connection. TransactionOperator và DatabaseClient phối hợp để lấy connection transaction-bound, rollback hoặc commit, cleanup rồi release.

### 8.1. ConnectionFactoryUtils

Khi phải tích hợp một thư viện R2DBC cấp thấp nhưng vẫn muốn tham gia Spring transaction, có thể dùng:

```java
ConnectionFactoryUtils.getConnection(connectionFactory);
ConnectionFactoryUtils.releaseConnection(connection, connectionFactory);
```

Đây là các method trả publisher; cần compose chúng vào chuỗi reactive. `releaseConnection` hiểu connection nào đã được gắn với transaction context và **không đóng nhầm** connection mà transaction manager vẫn đang sử dụng.

Đừng gọi `connection.close()` trực tiếp giữa transaction Spring để “giải phóng sớm”; điều đó có thể làm các lệnh tiếp theo lỗi hoặc làm hỏng transaction.

### 8.2. Tự lấy connection: Flux/Mono.usingWhen

Nếu code thật sự tự tạo connection **ngoài transaction được Spring quản lý**, dùng `usingWhen` để cleanup trên cả complete, error và cancel:

```java
public Mono<Integer> readConstant(ConnectionFactory factory) {
    return Mono.usingWhen(
            Mono.from(factory.create()),
            connection -> Flux.from(
                    connection.createStatement("SELECT 1").execute())
                    .flatMap(result -> Flux.from(
                            result.map((row, metadata) ->
                                    ((Number) row.get(0)).intValue())))
                    .single(),
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close()));
}
```

Đây là một method Java minh họa cần import `ConnectionFactory`, `Mono` và `Flux`; nó không phải một class độc lập của project ở mục 12. Trong ba callback cleanup:

1. Callback thứ ba chạy khi resource closure complete.
2. Callback thứ tư chạy khi resource closure error.
3. Callback thứ năm chạy khi subscription bị cancel.

Reactor sẽ subscribe/điều phối cleanup publisher. Nếu cleanup thất bại, tín hiệu cuối cùng mà caller thấy còn phụ thuộc semantics của `usingWhen`; không mặc định lỗi nghiệp vụ luôn được giữ nguyên.

**Chú ý:** `usingWhen` ở trên chỉ quản lý **đóng connection**, không tự bắt đầu/commit/rollback SQL transaction. Nếu bạn tự gọi `beginTransaction()`, bạn cũng phải triển khai commit trên success, rollback trên error/cancel và close trong mọi nhánh (kể cả khi commit/rollback lỗi). Vì rất dễ bỏ sót đường lỗi, ưu tiên `R2dbcTransactionManager` và `TransactionalOperator`.

### 8.3. Vì sao doFinally không thay thế usingWhen?

Ví dụ nguy hiểm:

```java
Mono<Result> result = doWork(connection)
        .doFinally(signal -> connection.close());
```

Trong R2DBC, `close()` trả `Publisher<Void>`. Gọi method rồi bỏ kết quả như trên **không thực thi cleanup một cách đáng tin**. Biến thể sau cũng thiếu kiểm soát:

```java
.doFinally(signal ->
        Mono.from(connection.close()).subscribe());
```

Nó khởi động subscription riêng, tách cleanup khỏi lifecycle chính; lỗi close có thể bị bỏ qua và caller không chờ close hoàn tất. `doFinally` rất tốt cho metric/log/signal inspection, nhưng không phải công cụ thay thế resource management async có cấu trúc.

Dùng `usingWhen` cho tài nguyên tự quản lý hoặc để Spring transaction manager làm thay.

### 8.4. Không close/commit hai lần

Không vừa để Spring quản lý transaction vừa tự gọi `commitTransaction()`, `rollbackTransaction()` hoặc `close()` trên cùng transactional connection. Điều đó phá ownership: manager có thể còn cần connection để chạy SQL tiếp, rollback hoặc cleanup.

Chỉ một tầng chịu trách nhiệm lifecycle cuối cùng của mỗi connection. Mã truy cập dữ liệu bên trong service chỉ dựng Publisher của công việc; không đóng tài nguyên thuộc manager.

## 9. Thứ tự operator làm thay đổi semantics

So sánh:

| Pipeline | Transaction thấy gì? | Kết quả có thể xảy ra |
| --- | --- | --- |
| `work.as(tx::transactional)` | Complete/error/cancel từ work | Commit nếu complete; rollback nếu error/cancel. |
| `work.onErrorResume(...).as(tx::transactional)` | Có thể chỉ thấy complete | Có thể commit sau khi nuốt lỗi. |
| `work.as(tx::transactional).onErrorResume(...)` | Error đi qua tx trước fallback | Rollback rồi fallback. |
| `work.as(tx::transactional).take(1)` | Downstream cancel transaction Flux | Rollback dù item đầu đã tới client. |
| `work.take(1).as(tx::transactional)` | Tx thấy một Flux đã hoàn tất bình thường | Có thể commit, **nhưng công việc không được tiêu thụ đầy đủ**; chỉ an toàn nếu đó là ý định nghiệp vụ. |
| `work.as(tx::transactional).timeout(d)` | Khi hết hạn, timeout cancel upstream | Rollback nếu transaction còn hoạt động; không hoàn tác commit đã hoàn tất. |
| `work.timeout(d).as(tx::transactional)` | Timeout được chuyển thành error bên trong tx | Rollback theo error; chỉ khác vị trí quan sát/timeout scope. |

Không thay đổi vị trí operator chỉ để “ép commit” trong khi còn công việc chưa chạy. Hãy xác định ranh giới nghiệp vụ đúng: mọi thao tác cần atomic nằm trong transaction; phía ngoài chỉ nhận kết quả khi transaction đã kết thúc.

Một `onErrorContinue` lạm dụng có thể bỏ qua lỗi của từng phần tử và khiến pipeline complete. Với giao dịch yêu cầu atomicity, tránh `onErrorContinue` nếu không có phân tích rất rõ về dữ liệu nào đã ghi và chính sách rollback.

## 10. Connection pool, timeout và starvation

Trong ứng dụng reactive, một transaction giữ connection tới khi complete, error hoặc cancel được xử lý và cleanup. Dù code không block Java thread, nó vẫn có thể giữ **connection hữu hạn**.

Ví dụ pool tối đa ba connection:

```text
Pool max = 3

Request A: transaction đang chờ upstream vô hạn -> giữ 1 connection
Request B: transaction đọc stream dài hạn     -> giữ 1 connection
Request C: transaction xử lý chậm              -> giữ 1 connection
Request D: acquire connection -> phải chờ
Request E: acquire connection -> phải chờ
```

Hệ quả: thời gian chờ pool tăng, request timeout, throughput giảm; thêm thread không giải quyết được thiếu connection.

Cấu hình cần cân nhắc:

- `spring.r2dbc.pool.max-size`: giới hạn connection pool.
- `spring.r2dbc.pool.initial-size` và `min-idle`: số connection được tạo/giữ tối thiểu.
- `spring.r2dbc.pool.max-acquire-time`: timeout khi chờ lấy connection.
- `spring.r2dbc.pool.max-idle-time` và `max-life-time`: chính sách tuổi connection.
- Database statement timeout và transaction timeout: giới hạn công việc quá lâu.
- Ngưỡng concurrency ở service: tránh quá nhiều transaction cùng lúc.

Không dùng một pool cực lớn để che transaction leak; điều đó có thể chuyển áp lực sang database. Theo dõi acquired/allocated/idle/pending và các lỗi acquire.

### 10.1. Hết thời gian chờ pool khác với transaction timeout

- **Pool acquire timeout:** không lấy được connection mới/rảnh trong thời gian giới hạn. Transaction có thể chưa bắt đầu.
- **Connect timeout:** không thiết lập được kết nối vật lý tới database.
- **Statement/query timeout:** một lệnh SQL chạy quá lâu.
- **Transaction timeout:** thời gian transaction được phép tồn tại theo policy và khả năng driver/manager.
- **Publisher timeout:** downstream không nhận tín hiệu trong khoảng định trước, gây error/cancel ở vị trí tương ứng.

Không mặc định một `timeout(Duration)` của Reactor thay thế được timeout ở tầng driver, database, connection pool hoặc protocol.

## 11. Ví dụ Spring Boot 3.3.5: commit, error, cancel, release

Ứng dụng demo dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5**, **Spring Data R2DBC**, **H2 in-memory**, **r2dbc-pool** và **Reactor Test**.

Để kiểm chứng vòng đời, pool cố ý có **max-size = 1**. Sau một transaction bị cancel, test mới phải lấy lại được connection để query, giúp phát hiện việc tài nguyên bị giữ. Đây là cấu hình dành riêng cho demo, **không phải khuyến nghị production**.

### 11.1. Cấu trúc project

```text
reactive-tx-cancel/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ReactiveTxCancelApplication.java
    │   │   ├── TransactionConfig.java
    │   │   └── LedgerService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/demo/
        └── LedgerServiceTest.java
```

### 11.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-tx-cancel</artifactId>
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
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-pool</artifactId>
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

Spring Boot BOM quản lý các phiên bản dependency tương thích. Khi dùng phiên bản Spring/driver khác, đối chiếu lại API và quy tắc rollback/cancel trước khi triển khai.

### 11.3. application.properties

```properties
spring.application.name=reactive-tx-cancel
spring.main.web-application-type=none

spring.r2dbc.url=r2dbc:h2:mem:///txdemo?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=1
spring.r2dbc.pool.max-size=1
spring.r2dbc.pool.max-acquire-time=5s

spring.sql.init.mode=always
```

`DB_CLOSE_DELAY=-1` giữ database H2 in-memory tồn tại khi connection vật lý cuối cùng đóng trong tiến trình demo. `spring.sql.init.mode=always` yêu cầu chạy `schema.sql` khi context khởi động. Pool một connection bảo đảm truy vấn xác minh sau cancel phải chờ tài nguyên được trả về.

### 11.4. schema.sql

```sql
CREATE TABLE IF NOT EXISTS ledger_entries (
    entry_id BIGINT PRIMARY KEY,
    label VARCHAR(100) NOT NULL
);
```

SQL này chỉ khởi tạo schema. Không có database ngoài hoặc tài khoản truy cập cần thiết.

### 11.5. ReactiveTxCancelApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTxCancelApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveTxCancelApplication.class, args);
    }
}
```

### 11.6. TransactionConfig.java

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class TransactionConfig {
    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
```

Spring Boot cấu hình reactive transaction manager từ R2DBC ConnectionFactory. Bean trên cung cấp TransactionalOperator để service dùng tường minh. Không tạo `TransactionTemplate` cho reactive pipeline vì đó là API dành cho transaction imperative.

### 11.7. LedgerService.java

```java
package demo;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class LedgerService {

    private final DatabaseClient db;
    private final TransactionalOperator tx;

    public LedgerService(DatabaseClient db, TransactionalOperator tx) {
        this.db = db;
        this.tx = tx;
    }

    private Mono<Void> insert(long id, String label) {
        return db.sql(
                    "INSERT INTO ledger_entries(entry_id, label) "
                    + "VALUES (:id, :label)")
                .bind("id", id)
                .bind("label", label)
                .fetch()
                .rowsUpdated()
                .then();
    }

    // Complete -> COMMIT.
    public Mono<Void> saveTwo(long firstId, long secondId) {
        return insert(firstId, "first")
                .then(insert(secondId, "second"))
                .as(tx::transactional);
    }

    // Error -> ROLLBACK.
    public Mono<Void> failAfterInsert(long id) {
        return insert(id, "before-error")
                .then(Mono.<Void>error(
                        new IllegalStateException("intentional failure")))
                .as(tx::transactional);
    }

    // Cancel -> ROLLBACK.
    // Emit một item nhưng cố ý không complete.
    public Flux<Long> insertThenNeverComplete(long id) {
        return insert(id, "before-cancel")
                .thenMany(
                        Flux.just(id).concatWith(Flux.<Long>never()))
                .as(tx::transactional);
    }

    // Lỗi được xử lý trước khi tx thấy nó -> có thể COMMIT.
    public Mono<Void> recoverInside(long id) {
        return insert(id, "recovered-inside")
                .then(Mono.<Void>error(
                        new IllegalStateException("handled error")))
                .onErrorResume(IllegalStateException.class,
                        error -> Mono.empty())
                .as(tx::transactional);
    }

    // Truy vấn từ subscription khác: không nằm trong transaction trên.
    public Mono<Boolean> exists(long id) {
        return db.sql(
                    "SELECT entry_id FROM ledger_entries "
                    + "WHERE entry_id = :id")
                .bind("id", id)
                .map((row, metadata) ->
                        ((Number) row.get(0)).longValue())
                .first()
                .hasElement();
    }

    public Mono<Long> countAll() {
        return db.sql("SELECT COUNT(*) FROM ledger_entries")
                .map((row, metadata) ->
                        ((Number) row.get(0)).longValue())
                .one();
    }

    // Test-only reset: ngoài transaction đang được kiểm thử.
    public Mono<Void> clearAll() {
        return db.sql("DELETE FROM ledger_entries")
                .fetch()
                .rowsUpdated()
                .then();
    }
}
```

Các điểm cần chú ý:

- `saveTwo` dùng `then`, tránh chạy các lệnh SQL trên cùng transactional connection đồng thời không kiểm soát.
- `failAfterInsert` ghi một dòng rồi phát error để transaction rollback.
- `insertThenNeverComplete` ghi dòng, phát một item và **không phát completion**. Test hủy sau item để kiểm chứng cancel.
- `recoverInside` nuốt error ngay bên trong transaction; dữ liệu vẫn commit. Đây là trường hợp đối chứng quan trọng.
- `exists` và `countAll` dùng `DatabaseClient` lấy connection từ pool theo cách transaction-aware. Chúng không tự đóng connection hoặc gọi `subscribe()`.

### 11.8. LedgerServiceTest.java

```java
package demo;

import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

@SpringBootTest
class LedgerServiceTest {

    @Autowired
    LedgerService service;

    @BeforeEach
    void reset() {
        // Block chỉ ở thread chạy unit/integration test.
        service.clearAll().block(Duration.ofSeconds(5));
    }

    @Test
    void completeCommitsAndConnectionIsReusable() {
        StepVerifier.create(service.saveTwo(1L, 2L))
                .verifyComplete();

        StepVerifier.create(service.countAll())
                .expectNext(2L)
                .verifyComplete();

        StepVerifier.create(service.exists(1L))
                .expectNext(true)
                .verifyComplete();
    }

    @Test
    void terminalErrorRollsBack() {
        StepVerifier.create(service.failAfterInsert(3L))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "intentional failure".equals(
                                error.getMessage()))
                .verify();

        StepVerifier.create(service.exists(3L))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void cancellingOpenTransactionRollsBackAndReleasesConnection() {
        StepVerifier.create(
                        service.insertThenNeverComplete(4L))
                .expectNext(4L)
                .thenCancel()
                .verify();

        // Pool max-size=1: phép kiểm tra chỉ chạy khi connection
        // đã được trả về. Timeout để phát hiện cleanup/pool leak.
        StepVerifier.create(
                        service.exists(4L)
                                .timeout(Duration.ofSeconds(5)))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void suppressingErrorInsideTransactionMayCommit() {
        StepVerifier.create(service.recoverInside(5L))
                .verifyComplete();

        StepVerifier.create(service.exists(5L))
                .expectNext(true)
                .verifyComplete();
    }
}
```

Ở test cancel, `StepVerifier.thenCancel()` phát cancellation sau item đầu tiên. `TransactionalOperator` có đường rollback khi bị cancel. Bởi pool chỉ có một connection, truy vấn `exists(4L)` phía sau buộc phải chờ connection trở về pool; nếu transaction giữ connection mãi thì truy vấn có thể timeout.

Kiểm tra `exists(false)` giúp thấy insert không commit. Phép kiểm tra này và pool một connection tạo bằng chứng tích hợp hữu ích, nhưng để phân tích lỗi nghiêm trọng ở production còn cần metric, log transaction, trace và kiểm tra behavior của driver/database thật.

### 11.9. Chạy và kết quả dự kiến

Ở thư mục project, chạy:

```bash
mvn test
```

Kết quả kỳ vọng: JUnit chạy **4 tests, 0 failures, 0 errors** (nếu môi trường Java/Maven và dependency tương thích, DB khởi tạo thành công). Các assertion lần lượt kiểm tra:

| Test | Tín hiệu transaction | Dữ liệu cuối cùng |
| --- | --- | --- |
| `completeCommitsAndConnectionIsReusable` | Complete | Hai bản ghi được commit. |
| `terminalErrorRollsBack` | Error | Bản ghi 3 không tồn tại. |
| `cancellingOpenTransactionRollsBackAndReleasesConnection` | Cancel | Bản ghi 4 không tồn tại; truy vấn mới có thể lấy connection. |
| `suppressingErrorInsideTransactionMayCommit` | Complete sau fallback | Bản ghi 5 tồn tại. |

`mvn spring-boot:run` khởi động context và tạo schema, nhưng ứng dụng demo này không mở HTTP endpoint và không tự chạy các test; muốn quan sát kết quả, dùng `mvn test`. Không suy rằng quá trình khởi động ứng dụng tự thực hiện các giao dịch test.

## 12. Tình huống phức tạp: nhiều repository và hệ sinh thái reactive

### 12.1. Nhiều repository trên cùng một ConnectionFactory

Nếu dùng hai repository R2DBC cùng tham gia `R2dbcTransactionManager` và cùng connection context, các câu lệnh của chúng có thể nằm chung transaction. Hãy compose chúng:

```java
return orderRepository.save(order)
        .flatMap(saved -> inventoryRepository.reserve(saved))
        .then()
        .as(tx::transactional);
```

Các repository ở đây là API nghiệp vụ minh họa. Không gọi `subscribe()` riêng cho `inventoryRepository.reserve`; nếu làm vậy, nó có thể chạy ngoài transaction ban đầu.

### 12.2. Database + HTTP API không tạo distributed transaction

Một transaction R2DBC không tự gom cả database và HTTP service vào cùng atomic commit:

```java
return db.insertOrder(order)
        .then(webClient.post()
                .uri("/charge")
                .retrieve()
                .bodyToMono(Void.class))
        .as(tx::transactional);
```

Đây là anti-pattern nếu giả định charge và DB sẽ rollback cùng nhau. HTTP side effect phía kia có thể đã hoàn tất dù transaction DB sau đó bị cancel/rollback. Hãy dùng **transactional outbox, saga/compensation và idempotency key**, tùy yêu cầu nghiệp vụ.

Đừng giữ DB transaction mở trong lúc chờ HTTP chậm nếu không cần; nó chiếm connection lâu và tăng nguy cơ pool starvation.

### 12.3. Kafka/RabbitMQ/RSocket không cùng transaction R2DBC

Một publisher message qua Kafka, RabbitMQ hoặc RSocket có lifecycle riêng. R2DBC rollback không tự thu hồi message đã được publish. Nếu cần “DB commit thì mới publish”, cân nhắc outbox table trong cùng database transaction, sau đó publisher riêng đọc outbox và phát message có idempotency.

Không dùng FNF hoặc thao tác gửi không có ack làm bằng chứng external system đã nhận/chạy nghiệp vụ.

### 12.4. WebFlux client disconnect và cancellation

Khi HTTP client disconnect, server thường có thể hủy subscriber của response pipeline. Nhưng thời điểm việc hủy truyền tới transaction phụ thuộc framework adapter, buffering, việc response đã commit, và vị trí của transaction trong pipeline.

Hãy test trực tiếp trường hợp disconnect bằng integration test phù hợp với runtime, không giả định mọi TCP disconnect đều rollback mọi giao dịch đã hoàn tất. Với thao tác tạo tài nguyên quan trọng, bảo đảm tính đúng đắn bằng trạng thái bền vững và idempotency, không chỉ bằng cancellation.

## 13. Quan sát và xử lý sự cố

### 13.1. Metric nên có

| Metric | Tín hiệu cảnh báo |
| --- | --- |
| Acquired/active connections | Luôn gần `max-size` dù request rate thấp. |
| Idle connections | Gần 0 trong thời gian dài bất thường. |
| Pending acquire / acquire latency | Request mới chờ pool ngày càng lâu. |
| Transaction duration | Giao dịch kéo dài hơn SLA. |
| Rollback on error/cancel | Tỷ lệ rollback tăng đột biến. |
| DB query duration | Câu lệnh chậm hoặc lock chặn transaction. |
| Connection create/close failures | Driver/network/DB hỏng hoặc cleanup lỗi. |
| Timed-out subscriptions | Timeout downstream quá thấp hoặc DB quá chậm. |

Nếu có Micrometer/Actuator, bật những metric do driver/pool thực sự xuất ra rồi đặt cảnh báo phù hợp. Không tự giả định mọi tên metric giống nhau giữa driver và version.

### 13.2. Cách truy vết một connection bị giữ

1. Xác định symptom: pool acquired cao, pending tăng hay lỗi timeout?
2. Kiểm tra transaction có Flux không kết thúc hoặc gọi `block()` trên event loop không.
3. Tìm `take`, `next`, `timeout`, `onErrorResume` và nơi tự gọi `subscribe()` quanh transaction.
4. Kiểm tra liệu mã có tự gọi `ConnectionFactory.create()` hoặc `close()` không compose cleanup.
5. Đối chiếu ID request/transaction với thời gian borrow/release, lỗi driver và DB lock.
6. Thực hiện integration test cancel/timeout với pool nhỏ để tái hiện.
7. Sửa ownership và ranh giới transaction; không chỉ tăng pool size để che lỗi.

Không log password, dữ liệu SQL nhạy cảm, bind parameter chứa PII hoặc connection URL có credential. Log có giới hạn và giữ correlation ID.

### 13.3. Timeout và shutdown

Khi ứng dụng shutdown, dừng nhận request mới, chờ các transaction còn hoạt động trong một khoảng hữu hạn, cancel các stream không cần thiết rồi đóng ConnectionPool/ConnectionFactory theo lifecycle của Spring Boot. Không dispose pool khi còn transaction đang thực sự sử dụng connection.

Không tự tạo nhiều ConnectionPool bean ngoài Spring rồi bỏ quên `dispose()`. Nếu tự quản lý pool, cấu hình shutdown để dispose đúng lúc và kiểm tra các connection còn acquired.

## 14. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi cancel như complete | Có thể commit công việc chưa kết thúc | Spring reactive 5.3+ rollback cancel; thiết kế pipeline cho kết thúc rõ ràng. |
| Nghĩ cancel luôn là `onError` | Error handler không chạy khi cancel | Dùng `doFinally` để quan sát, transaction manager/usingWhen để cleanup. |
| Dùng `Flux.next()` phía ngoài transaction Flux | Hủy upstream rồi rollback | Truy vấn một record hoặc bố trí transaction đúng ranh giới. |
| Giữ transaction quanh live stream vô hạn | Chiếm connection đến khi bị hủy | Commit giao dịch đọc snapshot ngắn rồi stream ngoài transaction. |
| Nuốt lỗi bằng `onErrorResume` trước tx | Transaction thấy complete và có thể commit | Để error đi qua boundary hoặc `setRollbackOnly` rõ ràng. |
| Sử dụng `Mono.empty()` để biểu diễn rollback | Empty là complete bình thường | Dùng error/rollbackOnly theo contract. |
| Nghĩ client timeout bảo đảm DB không đổi | Commit có thể đã diễn ra | Sử dụng ID, idempotency và query trạng thái. |
| Tự gọi `subscribe()` trong transactional service | Tách subscription và Reactor Context | Compose và return toàn bộ publisher cho caller. |
| Dùng JDBC blocking bên trong R2DBC pipeline | Chặn event loop và transaction khác nhau | Dùng driver reactive hoặc cô lập blocking với scheduler riêng, không giả định chung transaction. |
| Gọi `ConnectionFactory.create()` rồi coi là connection trong tx | Có thể mở connection ngoài context | Dùng DatabaseClient hoặc ConnectionFactoryUtils. |
| Tự close connection Spring đang quản lý | Manager mất tài nguyên giữa giao dịch | Để transaction manager làm cleanup. |
| Gọi `connection.close()` nhưng bỏ publisher | Cleanup không được subscribe | Dùng `usingWhen` hoặc compose close đúng cách. |
| `doFinally(...subscribe(close))` | Cleanup ngoài pipeline, khó xử lý lỗi | Dùng structured async cleanup. |
| Chỉ rollback mà quên release | Pool bị cạn | Bảo đảm cleanup/reset/close trên mọi đường kết thúc. |
| Cho rằng rollback không thể lỗi | Connection lỗi có thể cản trở rollback | Theo dõi rollback failure, trạng thái DB và connection health. |
| Retry POST/transfer vô hạn sau timeout | Trùng side effect | Retry có giới hạn, backoff và idempotency key. |
| Tăng pool để che leak | Tăng áp lực lên DB mà không chữa gốc | Sửa transaction scope và lifecycle, thêm metrics. |
| Dùng chung @Transactional với self-invocation | Proxy không can thiệp | Gọi qua bean/proxy hoặc dùng TransactionalOperator trực tiếp. |
| Viết test chỉ kiểm tra exception | Bỏ sót commit/rollback sai | Truy vấn dữ liệu sau giao dịch và kiểm tra pool được trả. |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `onError` và `cancel` khác nhau thế nào?  
**Đáp án:** onError là terminal error của publisher; cancel là subscriber dừng subscription và không có nguyên nhân đính kèm. Spring 5.3+ xử lý cancel của reactive transaction bằng rollback.

**Câu 2.** Khi transaction phát một item rồi client dùng `take(1)`, chắc chắn đã commit chưa?  
**Đáp án:** Chưa. take có thể cancel upstream transaction Flux và dẫn đến rollback, ngay cả khi item đã được gửi.

**Câu 3.** `Mono.empty()` có tự rollback không?  
**Đáp án:** Không; đó là complete bình thường, thường dẫn tới commit nếu transaction không rollback-only.

**Câu 4.** Vì sao `onErrorResume` trước `TransactionalOperator` nguy hiểm?  
**Đáp án:** Nó có thể biến lỗi thành completion; operator không thấy error và có thể commit những lệnh đã chạy.

**Câu 5.** Spring reactive transaction gắn với ThreadLocal hay Reactor Context?  
**Đáp án:** Reactor Context gắn với subscription. Tự subscribe một pipeline con có thể tách transaction context.

**Câu 6.** Rollback và close có đồng nghĩa không?  
**Đáp án:** Không. Rollback xử lý thay đổi dữ liệu, close/release trả tài nguyên về pool hoặc driver.

**Câu 7.** `Connection.close()` của R2DBC cần điều gì để thực thi?  
**Đáp án:** Nó trả Publisher; cần compose/subscribe qua lifecycle reactive. Với Spring-managed connection, để manager chịu trách nhiệm.

**Câu 8.** Vì sao nên dùng `usingWhen` thay `doFinally` để close connection thủ công?  
**Đáp án:** usingWhen điều phối cleanup async trên complete/error/cancel và quản lý tín hiệu lỗi cleanup; doFinally chỉ là callback đồng bộ, không tự chờ publisher close.

**Câu 9.** Khi nào connection được trả pool?  
**Đáp án:** Sau khi manager hoàn tất commit/rollback và cleanup, hoặc sau khi mã low-level đóng resource đúng cách; thời điểm thực tế phụ thuộc driver/pool.

**Câu 10.** Dùng một transaction DB bao cả HTTP call có bảo đảm tất cả cùng atomic không?  
**Đáp án:** Không. HTTP/Kafka/RSocket không tự tham gia atomic commit R2DBC; cần outbox, saga hoặc idempotency khi phối hợp.

## 16. Ghi nhớ

- Trong Spring Framework **5.3+**, cancel ở reactive transaction dẫn đến **rollback**; trên complete sẽ commit nếu không rollback-only, trên error sẽ rollback theo chính sách áp dụng.
- **Transaction completion** và **connection release** là hai trách nhiệm liên quan nhưng khác nhau. Một connection bị giữ làm cạn pool dù thread không bị block.
- Ưu tiên `DatabaseClient`/Spring Data R2DBC với `R2dbcTransactionManager`, `TransactionalOperator` hoặc `@Transactional`; không tự begin/commit/close connection Spring đang quản lý.
- `onErrorResume` **bên trong** transaction có thể khiến commit sau lỗi; `take`, `next` và `timeout` **bên ngoài** transaction có thể cancel và rollback.
- Dùng `usingWhen` cho connection tự quản lý. `doFinally` phù hợp quan sát tín hiệu, không thay cleanup bất đồng bộ có cấu trúc.
- Thiết kế transaction ngắn, hữu hạn, có giới hạn tài nguyên; không bọc live stream vô hạn và không coi client timeout là bằng chứng DB chưa commit.
- Test luôn ba đường complete/error/cancel và kiểm tra dữ liệu **sau transaction**, đồng thời quan sát connection pool.

## 17. Tài liệu tham khảo

1. [Spring Framework 6.2 – Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): `TransactionalOperator` và Cancel Signals; từ Spring 5.3 cancel dẫn tới rollback.
2. [Spring Framework – Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): reactive Publisher, Reactor Context và transaction manager.
3. [Spring Framework – @Transactional Settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): rollback rules và propagation.
4. [Spring Framework – Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html): `DatabaseClient`, connection management và `ConnectionFactoryUtils`.
5. [R2DBC SPI 1.0 – Connection API](https://r2dbc.io/spec/1.0.0.RELEASE/api/io/r2dbc/spi/Connection.html): `commitTransaction`, `rollbackTransaction`, `close`.
6. [Project Reactor – Mono.usingWhen API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): cleanup trên complete/error/cancel.
7. [Spring Boot 3.3 – Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.r2dbc.pool.*`.
8. [Spring Boot – Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): `schema.sql` cho R2DBC ConnectionFactory.
9. [R2DBC H2 – Supported Connection URLs](https://github.com/r2dbc/r2dbc-h2): `r2dbc:h2:mem:///...` và H2 options.
