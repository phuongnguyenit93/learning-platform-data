# Xử lý hủy đăng ký và giải phóng tài nguyên

Trong ứng dụng reactive dùng Spring Data R2DBC, một truy vấn thường được biểu diễn bằng `Mono` hoặc `Flux`. Công việc chỉ bắt đầu khi có subscriber và có thể kết thúc theo ba cách chính: hoàn tất bình thường, phát lỗi hoặc bị hủy (cancellation). Khi subscriber hủy đăng ký, pipeline phải truyền tín hiệu hủy về phía nguồn và giải phóng những tài nguyên đã được cấp, chẳng hạn kết nối database, transaction hoặc tài nguyên đọc dữ liệu.

Hủy đăng ký không đồng nghĩa với rollback mọi tác động đã xảy ra. Nó yêu cầu publisher dừng việc phát dữ liệu và cố gắng dừng công việc đang chạy theo khả năng của nguồn. Driver R2DBC có thể gửi tín hiệu hủy tới database, nhưng việc một câu SQL đang thực thi dừng ngay lập tức còn phụ thuộc driver và hệ quản trị. Những thay đổi đã commit hoặc side effect đã xảy ra ở hệ thống bên ngoài không thể được hoàn tác chỉ bằng cách cancel một subscription.

## 1. Subscription và cancellation trong Reactive Streams

Reactive Streams sử dụng giao thức giữa Publisher, Subscriber và Subscription:

- Subscriber đăng ký với Publisher và nhận một Subscription.
- Subscriber yêu cầu phần tử bằng `request(n)`.
- Publisher phát `onNext`, sau đó kết thúc bằng `onComplete` hoặc `onError`.
- Subscriber có thể gọi `cancel()` trên Subscription để báo rằng nó không còn muốn nhận kết quả.

Cancellation là tín hiệu một chiều từ subscriber về publisher. Sau khi hủy, subscriber không được mong đợi nhận thêm tín hiệu dữ liệu từ subscription đó. Publisher và các nguồn bên dưới cần ngừng công việc có thể ngừng và giải phóng tài nguyên.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant C as Subscriber / WebFlux
    participant R as Reactor pipeline
    participant D as R2DBC driver
    participant DB as Database
    C->>R: subscribe()
    R->>D: execute query
    D->>DB: SQL request
    DB-->>D: Rows / result
    D-->>R: onNext(...)
    C->>R: cancel()
    R->>D: propagate cancellation
    Note over D,DB: Driver may request query cancellation
    R->>D: release connection/resource
~~~

Đây là mô hình khái niệm. Thời điểm database thực sự dừng câu lệnh và thời điểm connection sẵn sàng được tái sử dụng phụ thuộc vào driver, giao thức và database.

## 2. Những tình huống tạo ra cancellation

Cancellation có thể xuất hiện từ nhiều nơi:

- Client HTTP đóng kết nối khi WebFlux vẫn đang tạo response.
- Một publisher phía trên gọi `take(n)` và không cần phần tử tiếp theo.
- `timeout(...)` hết hạn và hủy publisher nguồn trước khi phát lỗi timeout.
- Một luồng ghép bị hủy vì publisher khác thất bại hoặc subscriber không còn nhu cầu.
- Người dùng chủ động dừng một tác vụ hoặc ứng dụng đóng.
- Một subscription bị hủy trong quá trình shutdown.

Ví dụ:

~~~java
Flux<Product> firstFive = productRepository.findAll()
        .take(5);
~~~

Sau khi nhận đủ năm phần tử, `take(5)` hoàn tất downstream và hủy subscription upstream vì không cần đọc thêm. Nếu upstream đang giữ tài nguyên, nó phải xử lý tín hiệu hủy.

Ví dụ timeout:

~~~java
Mono<Product> product = productRepository.findById(id)
        .timeout(Duration.ofSeconds(2));
~~~

Nếu truy vấn không phát kết quả trong thời hạn, Reactor hủy publisher nguồn rồi phát `TimeoutException` downstream. Timeout là một nguyên nhân dẫn tới cancellation, nhưng downstream nhìn thấy lỗi timeout chứ không nhất thiết nhận một tín hiệu cancel trực tiếp.

## 3. Cancellation khác với complete và error

Ba kết cục cần được phân biệt:

| Tín hiệu | Ý nghĩa | Cách xử lý thường gặp |
| --- | --- | --- |
| Complete | Publisher đã phát hết dữ liệu bình thường | Commit transaction nếu transaction hợp lệ; giải phóng tài nguyên |
| Error | Publisher thất bại | Rollback transaction theo chính sách; giải phóng tài nguyên |
| Cancel | Subscriber không còn muốn nhận dữ liệu | Dừng công việc có thể dừng; rollback transaction đang mở theo transaction manager; giải phóng tài nguyên |

Cancellation không phải một loại `onError`. Subscriber gọi `Subscription.cancel()`; publisher không phát `onError(CancellationException)` chỉ vì bị cancel. Nếu ứng dụng cần log hoặc đo số lần hủy, hãy dùng hook cancellation/finalization thay vì chờ error.

## 4. Theo dõi cancellation bằng Reactor

Reactor cung cấp một số operator để quan sát vòng đời:

### doOnCancel

`doOnCancel` chạy khi subscription bị hủy:

~~~java
return productRepository.findAll()
        .doOnCancel(() ->
                log.info("Product stream was cancelled")
        );
~~~

Hook này phù hợp cho metric, log hoặc cập nhật trạng thái quan sát nhẹ. Callback là thao tác đồng bộ và không trả về publisher cleanup. Không dùng nó làm cơ chế chính để đóng connection bất đồng bộ.

### doFinally

`doFinally` chạy khi luồng kết thúc bằng complete, error hoặc cancel:

~~~java
return productRepository.findAll()
        .doFinally(signalType ->
                log.debug("Stream finished with signal {}", signalType)
        );
~~~

`SignalType` giúp phân biệt `ON_COMPLETE`, `ON_ERROR` và `CANCEL`. Đây là nơi thích hợp để ghi metric kết thúc luồng, thời gian xử lý hoặc số lần cancel.

### doOnTerminate

`doOnTerminate` được gọi khi publisher hoàn tất hoặc lỗi, nhưng không phải hook cho cancellation. Nếu cần quan sát cả ba kết cục, dùng `doFinally`.

Không nên đặt cleanup bất đồng bộ vào `doFinally`:

~~~java
// Không phù hợp để đóng connection bất đồng bộ.
source.doFinally(signal -> connection.close());
~~~

`doFinally` nhận callback trả về void. Publisher trả về từ `connection.close()` không được chờ hoặc phối hợp như một bước cleanup trong pipeline. Dùng `usingWhen` khi cleanup trả về publisher.

## 5. Spring Data R2DBC tự quản lý connection trong repository

Khi dùng Spring Data R2DBC repository, `R2dbcEntityTemplate` hoặc `DatabaseClient`, thông thường không cần tự lấy và đóng connection:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

Spring Data và R2DBC infrastructure quản lý việc lấy connection, thực thi câu lệnh, tiêu thụ result và giải phóng connection khi thao tác kết thúc hoặc bị hủy. Khi sử dụng connection pool, việc gọi close trên connection được pool quản lý thường trả connection về pool để tái sử dụng; không nhất thiết đóng socket vật lý.

Vì vậy, không lấy thêm một connection thủ công chỉ để chạy cùng truy vấn repository, và không tự đóng connection mà Spring Data đang sử dụng. Hãy giữ publisher reactive và để infrastructure quản lý vòng đời tài nguyên.

## 6. Khi nào cần quản lý Connection thủ công?

Chỉ nên dùng R2DBC SPI trực tiếp khi có nhu cầu mà repository, template hoặc DatabaseClient không đáp ứng, chẳng hạn cần điều khiển statement/result ở mức thấp hoặc tích hợp một thao tác đặc thù.

Khi gọi `ConnectionFactory.create()`, ứng dụng sở hữu trách nhiệm giải phóng connection đã nhận. Cần xử lý cả ba kết cục:

- Publisher hoàn tất bình thường.
- Publisher phát lỗi.
- Subscriber hủy subscription.

Không chỉ dùng `doOnSuccess` hoặc `doOnError` để đóng connection vì những hook đó không bao phủ đầy đủ cancellation và không phối hợp cleanup bất đồng bộ.

## 7. Dùng usingWhen để giải phóng connection

Reactor cung cấp `Mono.usingWhen` và `Flux.usingWhen` cho tài nguyên có cleanup bất đồng bộ. `usingWhen` nhận:

1. Publisher cấp tài nguyên.
2. Hàm sử dụng tài nguyên và tạo publisher kết quả.
3. Hàm cleanup khi complete.
4. Hàm cleanup khi error.
5. Hàm cleanup khi cancel.

Ví dụ PostgreSQL với R2DBC SPI:

~~~java
public Mono<Long> updateCustomerStatus(Long id, String status) {
    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> Flux.from(
                            connection.createStatement("""
                                    UPDATE customer
                                    SET status = $1
                                    WHERE id = $2
                                    """)
                                    .bind(0, status)
                                    .bind(1, id)
                                    .execute()
                    )
                    .concatMap(result ->
                            Mono.from(result.getRowsUpdated())
                    )
                    .reduce(0L, Long::sum),
            connection -> Mono.from(connection.close()),
            (connection, error) ->
                    Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
~~~

Trong ví dụ:

- `ConnectionFactory.create()` cấp một connection.
- Hàm sử dụng chạy câu UPDATE và thu thập số hàng bị tác động.
- Cleanup được gọi khi complete, error hoặc cancel.
- `Connection.close()` trả publisher và được `usingWhen` phối hợp.

Ví dụ dùng placeholder kiểu PostgreSQL (`$1`, `$2`). Placeholder và kiểu bind phụ thuộc driver. Khi dùng pool, `close()` thường trả connection về pool.

Không lặp lại cleanup bằng `doFinally` bên ngoài `usingWhen`; việc đó có thể đóng cùng một connection nhiều lần hoặc tạo side effect khó kiểm soát.

## 8. Vì sao usingWhen tốt hơn try/finally trong reactive code?

Một đoạn imperative có thể viết:

~~~java
Connection connection = factory.create().block();
try {
    // execute SQL
} finally {
    connection.close().block();
}
~~~

Đây là cách không phù hợp trong luồng reactive:

- `block()` chặn thread để chờ lấy connection.
- `close().block()` chặn thread khi cleanup.
- Cancellation của subscriber không tự động đi vào khối finally theo đúng vòng đời publisher.
- Lỗi và cancellation có thể xảy ra trong lúc một publisher bất đồng bộ đang chạy.

`usingWhen` gắn tài nguyên vào vòng đời publisher. Khi subscription kết thúc, Reactor chạy cleanup publisher tương ứng và phối hợp quá trình đó với terminal signal.

## 9. Connection.close() trong pool có nghĩa gì?

Trong R2DBC, `Connection.close()` là thao tác kết thúc việc sử dụng connection. Nếu connection đến từ pool, pool thường triển khai close như việc trả connection về pool:

- Connection có thể được kiểm tra trước khi tái sử dụng.
- Nếu connection vẫn hợp lệ, pool đưa nó về nhóm idle.
- Nếu connection bị hỏng hoặc quá tuổi thọ, pool có thể loại bỏ và đóng connection vật lý.
- Nếu connection thuộc transaction đang mở, transaction cần được hoàn tất hoặc rollback theo cơ chế quản lý trước khi connection có thể tái sử dụng.

Không nên giữ connection lâu hơn thời gian cần thiết. Connection bị giữ sau cancellation có thể làm pool thiếu connection, khiến request khác phải chờ hoặc gặp acquire timeout.

## 10. Hủy publisher khi đang chạy query có dừng SQL ngay không?

Không có cam kết chung rằng một lệnh cancel từ Reactor sẽ dừng câu SQL trên server ngay lập tức.

Cancellation được truyền qua Subscription đến R2DBC driver. Driver có thể:

- Gửi tín hiệu hủy qua giao thức database nếu được hỗ trợ.
- Hủy việc đọc result và đóng/giải phóng resource.
- Đợi hoạt động mạng hoặc server trả về trước khi connection có thể tái sử dụng.
- Không thể ngắt ngay một thao tác server đang thực thi trong một số trường hợp.

Khả năng cụ thể phụ thuộc R2DBC driver, database, phiên bản và loại câu lệnh. Vì vậy, cancellation giúp ứng dụng không tiếp tục tiêu thụ kết quả và cho phép driver dừng công việc khi có thể; nó không phải cam kết thời gian dừng SQL.

Nếu câu lệnh có thể chạy lâu, cần phối hợp thêm statement/query timeout, timeout của request, giới hạn tài nguyên database và theo dõi query đang chạy. Không dùng cancellation thay thế timeout phía database.

## 11. Cancellation và reactive transaction

Nếu publisher nằm trong reactive transaction, cancellation có ý nghĩa đặc biệt. Spring transaction infrastructure quản lý transaction theo Reactor Context. Khi subscriber hủy publisher trước khi transaction hoàn tất, transaction manager có thể rollback transaction đang mở và giải phóng connection theo cơ chế của nó.

Ví dụ:

~~~java
public Flux<Order> streamOrders() {
    Flux<Order> work = orderRepository.findAll()
            .doOnCancel(() ->
                    log.info("Order stream cancelled")
            );

    return transactionalOperator.transactional(work);
}
~~~

Nếu downstream hủy trước khi Flux hoàn tất, transaction reactive bị hủy và transaction manager xử lý rollback. Vì vậy, không nên bọc một luồng đọc rất dài hoặc stream không giới hạn trong transaction nếu không cần một ranh giới transaction kéo dài như vậy.

Với `Mono` thao tác ghi ngắn, cancellation thường xảy ra trước khi kết quả được phát hoặc trong lúc database đang xử lý. Kết quả cuối cùng phụ thuộc transaction manager và driver; nếu transaction đã commit xong trước khi cancel đến, cancellation không thể đảo ngược commit đó.

Không gọi `subscribe()` trong phương thức transactional. Subscription tách rời có thể chạy ngoài transaction context của caller.

## 12. Vị trí của onErrorResume ảnh hưởng đến rollback

Nếu lỗi được truyền ra ngoài `TransactionalOperator`, operator có thể quan sát lỗi và rollback:

~~~java
return transactionalOperator.transactional(work)
        .onErrorResume(error -> {
            log.error("Transaction failed and was rolled back", error);
            return Mono.empty();
        });
~~~

Ở đây, xử lý lỗi nằm bên ngoài operator. Operator nhận lỗi trước, thực hiện rollback, sau đó publisher bên ngoài mới phục hồi thành complete.

Nếu phục hồi lỗi bên trong publisher được bao bởi transaction:

~~~java
return transactionalOperator.transactional(
        work.onErrorResume(error -> Mono.empty())
);
~~~

operator có thể chỉ nhìn thấy publisher hoàn tất bình thường và commit. Nếu muốn rollback dù lỗi đã được phục hồi bên trong, cần dùng transaction status và đánh dấu rollback-only bằng `TransactionalOperator.execute(...)`.

Quy tắc này áp dụng cho error recovery. Cancellation không đi qua `onErrorResume` như một exception thông thường; cần dùng cancellation-aware cleanup và transaction management.

## 13. Hủy một luồng ghép bằng flatMap

Khi dùng `flatMap`, một publisher có thể có nhiều inner publisher đang hoạt động:

~~~java
return customerRepository.findAll()
        .flatMap(customer ->
                orderRepository.findRecentByCustomerId(customer.id())
        );
~~~

Nếu subscriber hủy luồng ngoài, Reactor truyền cancellation tới nguồn và các inner subscription đang hoạt động. Driver có cơ hội hủy các truy vấn tương ứng và giải phóng resource.

Nếu một inner publisher đã hoàn tất và commit transaction riêng trước khi cancellation đến, những thay đổi đã commit không bị đảo ngược bởi việc hủy luồng ngoài. Cancellation không phải cơ chế rollback toàn bộ các side effect độc lập.

Khi cần một đơn vị nguyên tử, hãy đặt các thao tác cần phối hợp trong cùng reactive transaction thay vì tạo transaction riêng cho từng inner publisher.

## 14. Cancellation không hoàn tác side effect bên ngoài database

Giả sử pipeline vừa lưu đơn hàng vừa gửi email:

~~~java
return orderRepository.save(order)
        .flatMap(saved ->
                emailClient.sendConfirmation(saved)
                        .thenReturn(saved)
        );
~~~

Nếu client hủy request sau khi email đã được gửi, cancellation không thể thu hồi email. Tương tự, lời gọi thanh toán, publish message hoặc cập nhật hệ thống ngoài không tự rollback cùng transaction R2DBC.

Với nghiệp vụ cần phối hợp database và hệ thống ngoài, cân nhắc:

- Ghi đơn hàng và outbox event trong cùng transaction.
- Tiến trình riêng gửi event sau commit.
- Idempotency key để tránh xử lý lặp.
- Retry có giới hạn và backoff.
- Saga hoặc thao tác bù trừ nếu quy trình gồm nhiều dịch vụ.

Đừng đặt lời gọi HTTP chậm bên trong transaction đang giữ connection/row lock nếu có thể tách nó ra.

## 15. Cleanup khi dùng tài nguyên khác

Nguyên tắc `usingWhen` không chỉ dành cho Connection. Nó phù hợp với tài nguyên có thao tác giải phóng bất đồng bộ như:

- Cursor hoặc streaming result do một API cụ thể quản lý.
- File hoặc stream có cleanup bất đồng bộ.
- Session hoặc handle do thư viện reactive cấp.
- Một resource được tạo từ publisher và phải đóng khi complete, error hoặc cancel.

Với tài nguyên Java có cleanup đồng bộ và không chặn, có thể dùng `using` hoặc `doFinally` tùy semantics. Với cleanup trả publisher, ưu tiên `usingWhen` để Reactor đợi quá trình giải phóng.

Không nên giữ connection trong một field singleton của service. Connection là tài nguyên có vòng đời ngắn, thường được cấp cho một thao tác hoặc transaction cụ thể.

## 16. Cancellation, timeout và backpressure

Backpressure điều khiển số phần tử subscriber muốn nhận; cancellation chấm dứt nhu cầu nhận phần tử của subscription.

Ví dụ:

~~~java
return eventRepository.findAll()
        .limitRate(64)
        .take(100);
~~~

- `limitRate(64)` điều tiết yêu cầu upstream theo từng đợt.
- `take(100)` hoàn tất sau 100 phần tử và hủy upstream.

Backpressure không tự giải phóng connection nếu publisher vẫn đang hoạt động. Khi luồng thực sự bị hủy, nguồn cần thực hiện cleanup.

Timeout có thể tạo cancellation upstream:

~~~java
return databaseCall()
        .timeout(Duration.ofSeconds(3))
        .onErrorMap(
                TimeoutException.class,
                error -> new DatabaseRequestTimeoutException()
        );
~~~

Timeout ở Reactor giới hạn thời gian chờ của publisher. Nếu cần giới hạn thời gian câu lệnh ở server, hãy cấu hình query/statement timeout phù hợp với database và driver. Hai giới hạn này có thể phối hợp nhưng không đồng nghĩa.

## 17. Theo dõi cancellation và tài nguyên trong vận hành

Nên thu thập các tín hiệu giúp xác định cancellation có làm rò rỉ tài nguyên hay không:

| Metric/log | Điều cần quan sát |
| --- | --- |
| Số subscription bị cancel | Client ngắt kết nối, timeout hoặc consumer dừng |
| Query duration | Câu SQL còn chạy lâu sau khi request bị hủy |
| Active/idle/pending connections | Connection có được trả về pool hay không |
| Connection acquire latency | Request khác có phải chờ connection sau các cancellation |
| Transaction rollback count | Transaction bị rollback do error/cancel |
| Cleanup failure | Lỗi khi đóng resource hoặc trả connection về pool |
| Timeout/deadlock count | Database đang bị chờ hoặc tranh chấp |

Ví dụ metric đơn giản:

~~~java
return orderRepository.findAll()
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                cancellationCounter.increment();
            }
        });
~~~

Không log toàn bộ dữ liệu nhạy cảm của hàng hoặc tham số SQL chỉ để điều tra cancellation. Ghi correlation ID, thời gian, loại operation và trạng thái resource là đủ trong nhiều trường hợp.

## 18. Kiểm thử cancellation

Unit test có thể dùng `StepVerifier` để xác nhận publisher nhận cancellation:

~~~java
StepVerifier.create(service.streamOrders())
        .expectNextCount(1)
        .thenCancel()
        .verify();
~~~

Có thể kiểm tra hook:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Integer> source = Flux.<Integer>never()
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
        .thenCancel()
        .verify();

assertTrue(cancelled.get());
~~~

Test này chỉ chứng minh cancellation được truyền qua publisher và callback được gọi. Nó không chứng minh driver đã hủy SQL trên server hoặc connection đã được trả về pool.

Integration test với database thực tế nên:

1. Tạo một truy vấn streaming đủ lâu hoặc publisher giữ connection có kiểm soát.
2. Subscribe và nhận một phần kết quả.
3. Hủy subscription.
4. Chờ cleanup hoàn tất theo deadline test.
5. Kiểm tra active connection giảm hoặc connection có thể được cấp lại.
6. Kiểm tra transaction bị rollback nếu publisher nằm trong transaction.
7. Quan sát database để xác định query còn chạy hay đã bị driver hủy.

Không dùng sleep dài tùy tiện. Dùng latch, sink, barrier hoặc tín hiệu điều phối có timeout để test ổn định. Chạy test trên cùng loại driver và database với production.

## 19. Các lỗi thường gặp

1. **Dùng doOnSuccess/doOnError để cleanup connection.** Những hook này không xử lý đầy đủ cancellation và cleanup bất đồng bộ.
2. **Dùng doFinally để gọi close().** Publisher cleanup trả về không được chờ; dùng usingWhen.
3. **Gọi block() trong service reactive.** Làm chặn thread và phá vỡ phối hợp cancellation.
4. **Tự subscribe() trong service.** Tạo subscription độc lập và caller không còn điều khiển được vòng đời.
5. **Quên nhánh cancel của usingWhen.** Resource có thể bị giữ khi subscriber hủy.
6. **Tự đóng connection do DatabaseClient quản lý.** Có thể làm hỏng vòng đời connection của Spring/pool.
7. **Cho rằng cancel luôn dừng SQL ngay lập tức.** Driver/database có thể cần thời gian hoặc không hỗ trợ hủy một số thao tác.
8. **Cho rằng cancellation rollback side effect đã commit.** Commit đã hoàn tất không thể bị hủy ngược.
9. **Nuốt error bên trong transaction.** Operator có thể thấy complete và commit nếu không đánh dấu rollback-only.
10. **Giữ transaction cho Flux dài.** Connection và khóa có thể bị giữ trong thời gian client tiêu thụ dữ liệu.
11. **Coi timeout của Reactor là statement timeout.** Cần cấu hình timeout ở đúng tầng.
12. **Không đo connection pool sau cancellation.** Có thể xảy ra leak hoặc cleanup chậm mà log request không thể hiện.

## Quy tắc lựa chọn nhanh

- Dùng `doOnCancel` để quan sát cancellation và `doFinally` để ghi nhận complete/error/cancel.
- Dùng `usingWhen` khi tự quản lý resource có cleanup trả về publisher.
- Với repository, `DatabaseClient` và template, để Spring Data quản lý connection.
- Dùng reactive transaction để bao các thao tác cần rollback khi error/cancel.
- Đặt `onErrorResume` bên ngoài transaction nếu muốn transaction quan sát lỗi và rollback trước khi phục hồi.
- Dùng timeout ở Reactor cho deadline publisher và query timeout ở database/driver cho thời gian thực thi SQL.
- Không giả định cancel chắc chắn dừng SQL ngay lập tức hoặc hoàn tác side effect bên ngoài database.
- Kiểm tra pool, transaction và driver bằng integration test có cancellation thật.

Cancellation là một phần bình thường trong vòng đời reactive stream. Trong Spring Data R2DBC, cancellation cần truyền tới publisher nguồn để driver có cơ hội dừng việc đọc hoặc thực thi, transaction manager có thể rollback transaction đang mở và tài nguyên phải được giải phóng. Với thao tác repository thông thường, Spring quản lý connection; khi tự dùng R2DBC SPI, hãy dùng `usingWhen` để cleanup trên cả complete, error và cancel. Theo dõi cancellation cùng trạng thái connection pool và kiểm thử trên driver/database thực tế để phát hiện việc giữ tài nguyên quá lâu.
