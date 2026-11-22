# Đo thời gian truy vấn, thời gian chờ pool và thời gian giao dịch

## 1. Vì sao cần đo riêng ba loại thời gian?

Trong ứng dụng Spring Data Relational R2DBC, một request có thể mất nhiều thời gian trước khi trả kết quả. Nguyên nhân không nhất thiết nằm ở câu SQL. Request có thể phải chờ connection từ pool, chờ database xử lý, đọc một result stream dài, thực hiện mapping hoặc giữ transaction trong lúc chạy logic ứng dụng.

Ba khoảng thời gian cần quan sát riêng là:

- **Thời gian truy vấn (query duration):** thời gian thực thi một thao tác database theo ranh giới đo đã chọn. Ở tầng ứng dụng, phép đo thường bao gồm thời gian từ lúc publisher bắt đầu chạy đến khi kết quả được tiêu thụ xong; ở tầng driver/proxy hoặc database, phép đo có thể chỉ tập trung vào statement.
- **Thời gian chờ connection (pool acquire duration):** thời gian từ lúc ứng dụng yêu cầu connection từ pool đến khi nhận được connection hoặc yêu cầu thất bại/hết hạn.
- **Thời gian giao dịch (transaction duration):** thời gian của toàn bộ transaction, từ khi transaction bắt đầu đến khi hoàn tất commit hoặc rollback theo ranh giới đo.

Ba số đo này trả lời những câu hỏi khác nhau:

| Số đo | Câu hỏi được trả lời |
|---|---|
| Query duration | Thao tác SQL và đọc kết quả mất bao lâu? |
| Pool acquire duration | Ứng dụng có phải chờ connection vì pool đang bận không? |
| Transaction duration | Một đơn vị công việc atomic giữ transaction/connection trong bao lâu? |

Ví dụ, một query có thể chỉ chạy 15 ms nhưng request mất 400 ms vì chờ pool 300 ms. Một transaction có thể mất 2 giây dù tổng thời gian SQL chỉ 100 ms vì code chờ một dịch vụ khác trong lúc transaction còn mở.

Nếu chỉ đo thời gian toàn request, rất khó biết cần tối ưu query, tăng/giảm pool, rút ngắn transaction hay giới hạn concurrency. Tách các số đo giúp tìm đúng nút thắt.

## 2. Phân rã đường đi của một thao tác R2DBC

Một thao tác repository thường trải qua nhiều giai đoạn:

~~~text
Caller subscribe()
       |
       v
Reactive pipeline bắt đầu
       |
       v
Yêu cầu connection từ ConnectionFactory
       |
       v
Chờ pool acquire (nếu pool bận)
       |
       v
Nhận connection
       |
       v
Gửi statement qua R2DBC driver
       |
       v
Database xử lý SQL / lock / I/O
       |
       v
Đọc result và map row
       |
       v
Publisher complete / error / cancel
       |
       v
Trả connection về pool
~~~

Với một query đơn giản ngoài transaction, connection có thể được giải phóng khi thao tác hoàn tất. Với reactive transaction, connection thường được giữ trong phạm vi transaction, kể cả giữa các statement.

Có thể phân loại các khoảng thời gian như sau:

- Thời gian chờ trước khi có connection.
- Thời gian round-trip statement và database.
- Thời gian nhận toàn bộ result stream.
- Thời gian mapping/chuyển đổi ở phía ứng dụng.
- Thời gian chờ giữa các thao tác trong transaction.
- Thời gian commit hoặc rollback.

Không phải công cụ nào cũng đo được tất cả các khoảng này. Một timer bao quanh repository publisher thường đo thời gian quan sát được ở tầng ứng dụng, còn statement listener đo ở tầng driver/proxy và database statistics đo theo góc nhìn server.

Khi đọc dashboard, phải biết chính xác timer bắt đầu và kết thúc ở đâu. Hai biểu đồ cùng mang tên query duration nhưng có ranh giới khác nhau sẽ không thể so sánh trực tiếp.

## 3. Publisher lazy ảnh hưởng đến cách đo thời gian

Publisher reactive thường lazy. Gọi repository method tạo ra một publisher; câu SQL thường chỉ được thực thi khi publisher được subscribe.

Ví dụ:

~~~java
Mono<Customer> query = customerRepository.findById(42L);
~~~

Nếu bắt đầu đồng hồ ngay khi tạo biến query rồi đợi một lúc mới subscribe, thời gian đo sẽ bao gồm cả khoảng thời gian publisher nằm yên chưa thực thi. Đó không phải thời gian query.

Hãy bắt đầu phép đo bên trong `Mono.defer` hoặc `Flux.defer` để mỗi subscription có một lần đo riêng:

~~~java
return Mono.defer(() -> {
    long started = System.nanoTime();

    return customerRepository.findById(id)
            .doFinally(signal -> {
                long elapsed = System.nanoTime() - started;
                recordDuration(elapsed);
            });
});
~~~

`System.nanoTime()` phù hợp để đo khoảng thời gian vì nó là đồng hồ đơn điệu, không bị thay đổi bởi việc đồng bộ giờ hệ thống. Dùng `System.currentTimeMillis()` để ghi timestamp sự kiện, không nên dùng làm đồng hồ đo duration.

Nếu publisher được subscribe nhiều lần, `defer` tạo phép đo mới cho mỗi subscription. Điều này rất quan trọng khi repository publisher là cold và mỗi subscription có thể chạy SQL lại.

## 4. Đo thời gian thao tác ở tầng repository

Một cách đơn giản là đo thời gian từ lúc repository publisher được subscribe đến khi nó phát tín hiệu terminal.

Ví dụ với Mono:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return Mono.defer(() -> {
        long started = System.nanoTime();

        return customerRepository.findById(id)
                .doFinally(signal -> {
                    long elapsedNanos =
                            System.nanoTime() - started;

                    log.debug(
                            "customer.findById completed in {} ms, signal={}",
                            elapsedNanos / 1_000_000.0,
                            signal
                    );
                });
    });
}
~~~

Đoạn code minh họa ranh giới thời gian của publisher repository. Nó có thể bao gồm:

- Thời gian chờ connection pool.
- Thời gian gửi và thực thi SQL.
- Thời gian nhận kết quả.
- Mapping row thành entity.
- Chi phí driver và các operator nằm trước `doFinally`.

Nó không phải thời gian database thuần. Nếu cần tách pool wait và statement execution, cần thêm instrumentation ở ConnectionFactory/pool và driver/proxy hoặc database.

Với Flux, timer nên dừng khi toàn bộ stream hoàn tất, phát lỗi hoặc bị hủy. Không dừng timer ngay khi nhận row đầu tiên nếu mục tiêu là đo thời gian đọc toàn bộ kết quả.

### 4.1. Phân biệt time-to-first-row và time-to-complete

Một Flux truy vấn 100.000 hàng có thể phát hàng đầu tiên sau 20 ms nhưng mất 3 giây để đọc hết. Hai chỉ số đều có ý nghĩa:

- **Time-to-first-row:** thời gian từ subscribe đến phần tử đầu tiên. Hữu ích với endpoint streaming và khả năng phản hồi sớm.
- **Time-to-complete:** thời gian từ subscribe đến khi toàn bộ Flux hoàn tất. Hữu ích với export, batch và tổng thời gian giữ result stream.

Ví dụ:

~~~java
public Flux<Customer> streamCustomers() {
    return Flux.defer(() -> {
        long started = System.nanoTime();
        AtomicBoolean firstRow = new AtomicBoolean();

        return customerRepository.findAll()
                .doOnNext(customer -> {
                    if (firstRow.compareAndSet(false, true)) {
                        long firstRowNanos =
                                System.nanoTime() - started;
                        recordFirstRow(firstRowNanos);
                    }
                })
                .doFinally(signal -> {
                    long totalNanos =
                            System.nanoTime() - started;
                    recordStreamDuration(totalNanos, signal);
                });
    });
}
~~~

Nếu Flux hoàn tất rỗng, không có time-to-first-row. Hãy ghi nhận riêng kết quả empty thay vì để metric first-row không có dữ liệu rồi diễn giải nhầm là query chưa chạy.

Nếu downstream xử lý mỗi row lâu, vị trí đặt timer ảnh hưởng kết quả. Đặt timer sát publisher repository đo thời gian đọc từ repository; đặt timer sau các operator xử lý/export sẽ đo cả công việc downstream. Đặt tên metric phản ánh đúng ranh giới đó.

## 5. Ghi duration bằng Micrometer Timer

Trong ứng dụng Spring Boot, Micrometer là lựa chọn phổ biến để ghi duration và đưa metrics tới hệ thống quan sát như Prometheus hoặc backend tương ứng.

Một Timer thường cung cấp:

- Số lần ghi nhận.
- Tổng thời gian.
- Giá trị lớn nhất theo cửa sổ/implementation.
- Histogram hoặc percentile khi được cấu hình.
- Tag để phân loại metric theo operation và outcome.

Ví dụ đơn giản dùng Timer được tạo sẵn:

~~~java
@Component
class CustomerRepositoryMetrics {

    private final Timer findByIdTimer;

    CustomerRepositoryMetrics(MeterRegistry registry) {
        this.findByIdTimer = Timer.builder("app.r2dbc.repository")
                .description("Repository publisher duration")
                .tag("operation", "customer.findById")
                .register(registry);
    }

    Mono<Customer> measureFindById(
            Long id,
            CustomerRepository repository) {

        return Mono.defer(() ->
                Mono.fromCallable(System::nanoTime)
                        .flatMap(started ->
                                repository.findById(id)
                                        .doFinally(signal -> {
                                            long elapsed =
                                                    System.nanoTime() - started;
                                            findByIdTimer.record(
                                                    elapsed,
                                                    TimeUnit.NANOSECONDS
                                            );
                                        })
                        )
        );
    }
}
~~~

Ví dụ này cho thấy vị trí đặt timer theo subscription; trong code production có thể dùng một helper để tránh lặp và phân loại outcome. Với thao tác reactive, không nên tự subscribe để ghi metric. Hãy gắn operator vào publisher đang được trả về.

Một lựa chọn khác là dùng `Timer.Sample` để chọn Timer/tag ở thời điểm kết thúc:

~~~java
Mono<Customer> measuredFind(Long id) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);
        AtomicReference<String> outcome =
                new AtomicReference<>("cancelled");

        return repository.findById(id)
                .doOnSuccess(customer ->
                        outcome.set(customer == null ? "empty" : "success"))
                .doOnError(error -> outcome.set("error"))
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        outcome.set("cancelled");
                    }

                    Timer timer = Timer.builder("app.r2dbc.repository")
                            .tag("operation", "customer.findById")
                            .tag("outcome", outcome.get())
                            .register(meterRegistry);

                    sample.stop(timer);
                });
    });
}
~~~

Trong ví dụ Mono, `doOnSuccess` nhận `null` khi publisher hoàn tất rỗng. `doFinally` ghi nhận cả complete, error và cancel. Có thể bổ sung tag cho loại thao tác, nhưng giữ tag có số lượng giá trị hữu hạn.

Đối với Flux, dùng `doOnComplete` để đánh dấu success, `doOnError` cho error và `doFinally` để ghi nhận duration/cancel. Đừng dùng `doOnNext` làm điểm dừng timer vì Flux có thể phát nhiều phần tử.

### 5.1. Không tạo metric name hoặc tag từ dữ liệu động

Không dùng các giá trị sau làm tag metric:

- Customer ID hoặc Order ID.
- Email, username hoặc tenant ID không giới hạn.
- Toàn bộ SQL statement.
- Bind parameter.
- Trace ID hoặc request ID.
- URL có path parameter.

Những giá trị này tạo cardinality rất lớn, làm tăng bộ nhớ và chi phí của hệ thống metrics. Dùng tên operation ổn định như `customer.findById`, `order.save` hoặc nhóm query có giới hạn. Trace ID thuộc log/trace, không phải metric label.

## 6. Đo thời gian chờ connection pool

Pool acquire duration là thời gian từ khi code yêu cầu connection đến khi pool cấp connection hoặc trả lỗi.

Đây là chỉ số cần thiết khi:

- Số connection acquired thường xuyên bằng max-size.
- Pending acquire tăng.
- Request chờ connection lâu.
- Có nhiều timeout lấy connection.
- Database active session chưa cao nhưng ứng dụng vẫn bị chậm.

Cần phân biệt:

- **Acquire latency:** thời gian chờ connection từ pool.
- **Connection creation latency:** thời gian tạo kết nối vật lý mới khi pool cần mở connection.
- **Query duration:** thời gian thực hiện thao tác sau khi có connection.
- **Connection hold duration:** thời gian connection được giữ trước khi trả lại pool.

Một pool có thể có acquire latency cao vì không còn connection rảnh. Nhưng nguyên nhân gốc có thể là query chậm, transaction dài hoặc Flux stream giữ connection quá lâu.

### 6.1. Quan sát các trạng thái pool

Các pool metrics thường cung cấp hoặc cho phép suy ra những trạng thái như:

| Metric | Ý nghĩa |
|---|---|
| acquired / in-use | Connection đang được mượn |
| allocated | Tổng connection được pool cấp phát |
| idle | Connection đang rảnh |
| pending acquire | Yêu cầu đang chờ connection |
| acquire timeout | Số lần yêu cầu không lấy được connection trong thời hạn |
| acquire duration | Thời gian chờ để lấy connection nếu instrumentation hỗ trợ |
| connection creation duration | Thời gian mở connection mới nếu được đo |

Tên metric cụ thể phụ thuộc phiên bản Spring Boot, r2dbc-pool và hệ thống metrics. Hãy kiểm tra các metric thực tế được expose trong ứng dụng thay vì giả định mọi phiên bản có cùng tên.

Pool gauges là số liệu tại một thời điểm. Chúng giúp phát hiện saturation nhưng không tự cho biết mỗi request đã chờ bao lâu. Muốn đo acquire latency, cần timer ở acquisition boundary hoặc metric recorder mà pool cung cấp.

### 6.2. Đo tại ConnectionFactory boundary

Về nguyên tắc, có thể đo thời gian từ khi gọi `ConnectionFactory.create()` đến khi publisher phát connection:

~~~java
Mono<Connection> acquireMeasured(ConnectionFactory factory) {
    return Mono.defer(() -> {
        long started = System.nanoTime();

        return Mono.from(factory.create())
                .doOnSuccess(connection -> {
                    long elapsed = System.nanoTime() - started;
                    recordPoolAcquireSuccess(elapsed);
                })
                .doOnError(error -> {
                    long elapsed = System.nanoTime() - started;
                    recordPoolAcquireFailure(elapsed);
                });
    });
}
~~~

Đây là minh họa ranh giới acquisition, không phải cách thay thế tùy tiện ConnectionFactory của Spring. Nếu repository/transaction manager dùng ConnectionFactory khác, timer này sẽ không đo connection mà repository thực sự mượn.

Để áp dụng toàn ứng dụng, instrument đúng pooled ConnectionFactory mà Spring Data và transaction manager sử dụng, thông qua pool metrics, Micrometer integration hoặc một decorator/proxy tương thích với R2DBC SPI. Không mở một connection riêng chỉ để đo rồi suy luận thời gian chờ của repository.

Phép đo tại create() thường phản ánh thời gian từ yêu cầu cấp connection đến lúc connection được phát cho caller. Tùy pool, nó có thể bao gồm chờ slot, validation và tạo connection mới. Ghi rõ metric là acquisition latency, không mặc định đó chỉ là queue wait thuần.

### 6.3. Acquire timeout và pending queue

Nếu pool đạt max-size, yêu cầu mới có thể chờ trong hàng đợi acquire. Nếu quá thời hạn cấu hình, thao tác thất bại bằng lỗi acquire timeout.

Một số biểu hiện:

- Acquired gần max-size liên tục.
- Idle gần 0.
- Pending acquire tăng.
- Acquire duration p95/p99 tăng.
- Acquire timeout tăng.

Đừng chỉ tăng max-size ngay. Trước tiên, kiểm tra connection hold duration, query duration, transaction duration, số replica và ngân sách connection database. Nếu database đã bão hòa, thêm connection có thể làm query chậm hơn.

## 7. Đo thời gian thực thi statement ở tầng driver

Timer bao quanh repository publisher hữu ích cho góc nhìn ứng dụng, nhưng nó thường bao gồm cả acquire và đọc kết quả. Nếu cần tách thời gian statement, có thể instrument ở tầng R2DBC driver hoặc proxy.

Một lựa chọn là dùng thư viện proxy tương thích R2DBC để quan sát vòng đời statement/execution. Listener có thể ghi nhận các mốc như:

- Trước khi statement được thực thi.
- Sau khi statement hoàn tất.
- Lỗi khi thực thi.
- Các thông tin statement và số hàng ảnh hưởng nếu proxy cung cấp.

Cách triển khai cụ thể phụ thuộc thư viện và phiên bản. Khi chọn proxy, cần xác nhận nó hỗ trợ phiên bản R2DBC SPI và driver của ứng dụng.

Phép đo statement ở client có thể bao gồm network round-trip, database response và việc nhận kết quả theo cách proxy định nghĩa. Nó không nhất thiết bằng thời gian CPU mà database dành riêng cho SQL.

### 7.1. So sánh ba góc nhìn

| Nơi đo | Thường bao gồm | Không nhất thiết bao gồm |
|---|---|---|
| Timer quanh repository publisher | Acquire, statement, fetch, mapping trong publisher | Logic downstream nằm sau timer |
| Statement proxy/driver | Thực thi statement và result lifecycle theo proxy | Thời gian chờ pool trước khi có connection |
| Database server statistics | Thời gian statement theo cách server ghi nhận | Queue và thời gian chờ ở ứng dụng/pool |

Không cộng các số đo này lại với nhau. Chúng có thể bao phủ cùng một khoảng thời gian ở các tầng khác nhau.

### 7.2. Query Flux cần xác định thời điểm hoàn tất

Với SELECT trả về nhiều hàng, statement có thể được thực thi trước khi toàn bộ result stream được tiêu thụ. Một listener đo tới lúc execute trả result object có thể cho thời gian khác với timer đo tới khi Flux complete.

Nếu hệ thống streaming, cần đo riêng:

- Thời gian gửi statement/nhận response ban đầu.
- Thời gian đến row đầu tiên.
- Thời gian đọc hết result stream.
- Thời gian downstream xử lý xong nếu nghiệp vụ cần.

Tên metric phải thể hiện chính xác mốc kết thúc.

## 8. Đo thời gian giao dịch reactive

Transaction duration đo toàn bộ phạm vi transaction, không chỉ từng câu SQL. Nó có thể bao gồm:

- Acquire connection.
- Bắt đầu transaction.
- Một hoặc nhiều statement.
- Thời gian chờ giữa các statement.
- Logic ứng dụng chạy bên trong transaction.
- Commit hoặc rollback.

Với `TransactionalOperator`, có thể bọc publisher và đo vòng đời subscription:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    Mono<Order> work =
            orderRepository.save(toOrder(command))
                    .flatMap(saved ->
                            orderLineRepository.saveAll(toLines(saved.id(), command))
                                    .thenReturn(saved)
                    );

    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return transactionalOperator.transactional(work)
                .doOnError(error ->
                        recordTransactionOutcome("error"))
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        recordTransactionOutcome("cancelled");
                    }

                    sample.stop(transactionTimer);
                });
    });
}
~~~

Ví dụ này đo thời gian từ lúc subscriber bắt đầu publisher được bọc bởi TransactionalOperator đến tín hiệu terminal quan sát được. Tùy vị trí operator và semantics cleanup của transaction manager, nếu cần xác định chính xác thời điểm commit/rollback hoàn tất, hãy dùng transaction synchronization hoặc instrumentation của transaction manager thay vì chỉ dựa vào timer ở tầng service.

Với annotation `@Transactional`, có thể đo publisher trả về từ service ở caller boundary. Bắt đầu đồng hồ bên trong `Mono.defer` để không tính khoảng thời gian publisher chờ subscription.

### 8.1. Transaction duration khác tổng query duration

Giả sử transaction có ba query:

| Thành phần | Thời gian |
|---|---:|
| Acquire connection | 20 ms |
| Query 1 | 15 ms |
| Logic ứng dụng | 300 ms |
| Query 2 | 20 ms |
| Query 3 | 10 ms |
| Commit và cleanup | 5 ms |

Transaction có thể kéo dài khoảng 370 ms dù tổng thời gian statement chỉ 45 ms. Connection bị giữ trong phần logic ứng dụng 300 ms.

Đây là lý do transaction duration là chỉ số riêng. Nếu transaction dài, cần xem có công việc nào không cần atomic lại nằm bên trong boundary hay không.

### 8.2. Không giữ transaction trong lúc chờ dịch vụ ngoài

Không nên gọi HTTP, gửi email, chờ message hoặc thực hiện xử lý CPU lâu trong transaction nếu không cần thiết. Những thao tác đó kéo dài connection hold time và có thể giữ lock/snapshot.

Thay vì một transaction dài, cân nhắc:

- Tách thành các transaction ngắn.
- Dùng saga hoặc workflow có bước bù trừ.
- Dùng transactional outbox cho việc phát message.
- Đưa công việc CPU-heavy ra ngoài transaction.
- Tạo trạng thái trung gian rõ ràng trong domain.

Không tách transaction nếu nghiệp vụ thực sự yêu cầu atomic giữa các thao tác database; hãy xác định ranh giới theo tính toàn vẹn dữ liệu.

## 9. Đo commit, rollback và cancellation

Không phải transaction nào cũng kết thúc thành công. Nên phân loại outcome:

- Commit thành công.
- Rollback do error.
- Rollback do cancellation.
- Transaction begin/commit/rollback thất bại.
- Acquire hoặc begin thất bại trước khi statement chạy.

Nếu chỉ ghi một Timer không có outcome, bạn sẽ khó phân biệt transaction thành công với transaction lỗi hoặc bị hủy.

Với reactive transaction, cancellation là một tín hiệu quan trọng. Khi subscriber hủy, transaction manager thường cần cleanup và rollback transaction đang mở. Tuy nhiên, thời điểm downstream nhận cancellation không nhất thiết đồng nghĩa database đã hoàn tất rollback. Nếu cần metric chính xác cho thời gian cleanup/rollback, instrument transaction manager hoặc synchronization callback ở giai đoạn after-completion.

Không ghi cancellation thành success. Cũng không giả định mọi request timeout đều rollback được transaction đã commit trước đó.

## 10. Phân biệt query duration, connection hold duration và transaction duration

Ba thời gian thường bị nhầm lẫn:

- **Query duration:** thời gian một thao tác statement/result được đo theo ranh giới cụ thể.
- **Connection hold duration:** thời gian một connection được giữ từ lúc acquire đến lúc release.
- **Transaction duration:** thời gian một transaction tồn tại từ begin đến completion.

Một transaction có thể chạy nhiều query trên cùng connection. Khi đó:

~~~text
Transaction duration
  ├── Acquire connection
  ├── Query A
  ├── Application work
  ├── Query B
  ├── Application work
  ├── Query C
  └── Commit / rollback / cleanup
~~~

Connection hold duration thường gần với transaction duration nếu connection được bind trong toàn bộ transaction, nhưng hai khái niệm không luôn đồng nhất trong mọi implementation hoặc trường hợp nested/resource management.

Ngoài transaction, một Flux dài cũng có thể giữ connection trong thời gian đọc result. Vì vậy, connection hold duration có thể dài dù không có transaction tường minh.

Đo cả ba giúp nhận ra trường hợp query nhanh nhưng connection bị giữ lâu.

## 11. Dùng database server metrics để đối chiếu

Client-side instrumentation cho biết ứng dụng chờ bao lâu. Database server metrics giúp xác định database thực sự làm gì trong khoảng đó.

Với PostgreSQL, có thể xem các nguồn như:

- `pg_stat_activity`: session, trạng thái và wait event.
- `pg_stat_statements`: thống kê câu lệnh theo nhóm nếu extension được bật.
- Slow query logging hoặc log duration.
- `EXPLAIN (ANALYZE, BUFFERS)` trên query phù hợp trong môi trường an toàn.
- Lock monitoring và transaction age.

Với MySQL, có thể xem Performance Schema, statement digest, process list, lock wait và slow query log. Các hệ quản trị khác có công cụ tương đương.

Server-side duration không nhất thiết bằng client-side duration. Ví dụ:

- Client đo 200 ms.
- Server ghi nhận query execution 40 ms.
- Phần còn lại có thể là pool acquire, network, driver, result transfer, mapping hoặc thời gian client tiêu thụ stream.

Ngược lại, nếu server-side duration cao và có lock wait, tối ưu pool ở ứng dụng không giải quyết nguyên nhân chính.

## 12. Tương quan metrics giữa các tầng

Để tìm nguyên nhân, đặt các biểu đồ cạnh nhau theo cùng khoảng thời gian:

- Request latency p50/p95/p99.
- Repository/query duration.
- Pool acquire duration.
- Pool acquired/idle/pending.
- Transaction duration.
- Database active sessions.
- Database CPU/I/O.
- Lock wait/deadlock.
- Error và timeout rate.

Một số mẫu chẩn đoán:

| Quan sát | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Acquire duration cao, query duration thấp | Pool bận hoặc connection giữ lâu | Kiểm tra pending, transaction và stream |
| Acquire duration thấp, query duration cao | SQL chậm, lock, network hoặc fetch lớn | Kiểm tra query plan và server metrics |
| Query duration thấp, transaction duration cao | Logic ứng dụng hoặc chờ giữa các query | Thu hẹp transaction boundary |
| Acquired luôn gần max, pending tăng | Pool saturation | Kiểm tra hold time và DB headroom |
| Pool còn idle nhưng request chậm | Nút thắt ở SQL, app hoặc network | Đối chiếu statement và request timing |
| DB CPU cao, latency tăng khi pool tăng | Database bão hòa | Giảm concurrency, tối ưu query |
| Transaction duration dài, idle-in-transaction tăng | Transaction chờ công việc bên ngoài | Tách I/O ngoài DB khỏi transaction |
| Query p99 cao nhưng median thấp | Một số query/parameter/data skew | Phân nhóm query ổn định và xem slow query |

Không kết luận từ một metric riêng. Ví dụ pending acquire tăng có thể do pool quá nhỏ, nhưng cũng có thể do query chậm hoặc transaction dài làm connection không được trả về.

## 13. Thiết kế metric name và tag có cardinality thấp

Một bộ metric có thể đặt theo nhóm:

| Metric gợi ý | Loại | Tag gợi ý |
|---|---|---|
| `app.r2dbc.query.duration` | Timer | operation, outcome |
| `app.r2dbc.pool.acquire` | Timer | pool, outcome |
| `app.r2dbc.transaction.duration` | Timer | transaction, outcome |
| `app.r2dbc.connection.hold` | Timer | pool, outcome |
| `app.r2dbc.pool.pending` | Gauge | pool |
| `app.r2dbc.pool.acquired` | Gauge | pool |
| `app.r2dbc.operation.errors` | Counter | operation, error_type |

Đây là tên gợi ý do ứng dụng định nghĩa; tên metric thực tế có thể khác theo convention và backend.

Tag tốt:

- operation: `customer.findById`, `order.save`.
- outcome: `success`, `empty`, `error`, `cancelled`.
- pool: `primary`, `reporting`.
- database: `orders`, `customers` nếu số lượng cố định.

Tag không tốt:

- SQL đầy đủ có literal.
- ID của từng entity.
- Request path chứa ID.
- User email.
- Trace ID.
- Exception message tự do.
- Giá trị bind parameter.

Nếu cần xem SQL cụ thể, dùng trace hoặc log đã được kiểm soát và che dữ liệu nhạy cảm. Không đưa SQL và dữ liệu cá nhân vào metrics label.

## 14. Histogram và percentile: xem p95/p99 thay vì chỉ trung bình

Average duration có thể che giấu các request rất chậm. Ví dụ 99 query mất 10 ms và một query mất 2 giây có thể làm average tăng, nhưng không cho biết phân phối.

Nên quan sát:

- p50: latency điển hình.
- p95: 5% thao tác chậm nhất vượt ngưỡng này.
- p99: tail latency.
- Max: điểm chậm nhất trong cửa sổ, cần đọc thận trọng.
- Count: số lượng sample trong cửa sổ.

Với Micrometer, có thể bật histogram hoặc percentile phù hợp với backend. Ví dụ:

~~~java
Timer queryTimer = Timer.builder("app.r2dbc.query.duration")
        .description("R2DBC query publisher duration")
        .publishPercentileHistogram()
        .tag("operation", "customer.findById")
        .register(meterRegistry);
~~~

Cấu hình histogram tạo thêm chuỗi bucket và chi phí lưu trữ. Chỉ bật cho metric cần SLO/alert hoặc phân tích tail latency. Hãy dùng bucket phù hợp với đơn vị thời gian và mục tiêu của hệ thống.

Không so sánh p99 từ hai nguồn có sample count rất khác nhau mà không xem quy mô mẫu. Một p99 từ 10 sample không ổn định như p99 từ hàng nghìn sample.

## 15. Ghi log truy vấn chậm một cách an toàn

Metrics cho biết xu hướng; log giúp điều tra một lần query cụ thể. Có thể ghi log khi duration vượt ngưỡng:

~~~java
.doFinally(signal -> {
    long elapsed = System.nanoTime() - started;

    if (elapsed > slowQueryThresholdNanos) {
        log.warn(
                "Slow repository operation: operation={}, durationMs={}, signal={}",
                "customer.findById",
                elapsed / 1_000_000.0,
                signal
        );
    }
});
~~~

Tên operation nên ổn định và không chứa ID. Nếu cần liên kết với request, dùng trace/span context trong log theo chính sách observability.

Tránh log password, email, token, thông tin cá nhân hoặc toàn bộ bind parameter. Nếu phải ghi SQL, dùng câu lệnh đã loại literal và áp dụng chính sách masking. Log chậm cần có sampling hoặc rate limit nếu hệ thống có lượng query lớn, tránh tạo thêm I/O và làm log backend quá tải.

## 16. Đo retry đúng cách

Retry có thể làm thời gian người dùng chờ dài hơn thời gian của một lần query.

Ví dụ:

~~~java
return repository.findById(id)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100)));
~~~

Có hai ranh giới đo hữu ích:

- **Mỗi attempt:** đo riêng từng lần thực thi nguồn query. Hữu ích để biết mỗi lần query mất bao lâu và có bao nhiêu attempt.
- **Toàn bộ operation:** đo từ subscription ban đầu đến kết quả cuối sau retry/backoff. Hữu ích cho latency mà caller thực sự trải nghiệm.

Nếu timer đặt bên trong nguồn trước retry, mỗi lần resubscribe có thể tạo sample mới. Nếu timer bao quanh toàn bộ publisher sau retry, duration bao gồm cả các lần thử và khoảng backoff.

Ghi thêm số attempt bằng counter có giới hạn tag. Không retry lỗi constraint hoặc lỗi validation. Với write, phải đánh giá idempotency và trường hợp database đã commit nhưng client không nhận được response.

Retry có thể làm query latency trung bình của từng attempt trông bình thường trong khi operation latency tăng cao. Cần xem cả hai.

## 17. Đo thao tác ghi và đọc stream

Đọc và ghi có hình thái thời gian khác nhau:

- Một INSERT thường phát ít kết quả và có thể hoàn tất nhanh.
- Một UPDATE/DELETE có thể chờ lock hoặc ảnh hưởng nhiều hàng.
- Một SELECT trả Flux có thể kéo dài theo số hàng và tốc độ subscriber.
- Batch save có thể gồm nhiều statement hoặc nhiều lần round-trip tùy implementation.

Đối với Flux, cần đo số hàng được phát cùng duration:

~~~java
AtomicLong rowCount = new AtomicLong();

return repository.findAll()
        .doOnNext(row -> rowCount.incrementAndGet())
        .doFinally(signal -> {
            recordRowsReturned(rowCount.get());
            recordStreamOutcome(signal);
        });
~~~

Nếu dùng metrics, có thể ghi distribution của row count hoặc số hàng theo operation. Không dùng số hàng tùy ý làm tag vì cardinality có thể tăng; ghi nó như histogram/distribution hoặc log có kiểm soát.

Với batch, ghi nhận batch size và duration. Một batch 10 hàng và một batch 10.000 hàng không thể so sánh duration mà không tính quy mô công việc.

## 18. Đo thời gian connection được giữ

Acquire latency thấp không đảm bảo pool khỏe. Connection có thể được mượn nhanh nhưng bị giữ lâu.

Connection hold duration có thể đo ở nơi pool cấp và thu hồi connection, hoặc qua proxy/wrapper theo lifecycle connection. Cần phân biệt:

- Thời gian từ lúc pool cấp connection đến lúc connection được trả về.
- Thời gian statement thực thi.
- Thời gian transaction tồn tại.

Trong transaction, connection hold duration thường phản ánh thời gian transaction sử dụng connection. Với stream dài ngoài transaction, thời gian đọc result có thể giữ connection đến khi stream complete/cancel.

Nếu pool hoặc proxy không expose hold timer trực tiếp, có thể suy ra một phần qua acquired gauge, query/transaction duration và instrumentation phù hợp. Không lấy `max-life-time` hoặc `max-idle-time` làm connection hold duration; chúng là chính sách tuổi thọ/nhàn rỗi của connection, không phải thời gian một request đang mượn connection.

## 19. Tránh instrumentation làm thay đổi behavior

Instrumentation nên quan sát publisher mà không tạo thêm subscription hoặc thay đổi semantics.

Không nên:

~~~java
Mono<Customer> result = repository.findById(id);
result.subscribe(); // Tạo subscription riêng để log
return result;
~~~

Đoạn code trên có thể thực thi query hai lần: một subscription cho logging và một subscription của caller.

Hãy gắn operator vào publisher được trả về:

~~~java
return repository.findById(id)
        .doOnNext(customer -> log.debug("Customer found"))
        .doFinally(signal -> recordCompletion(signal));
~~~

Các nguyên tắc khác:

- Không gọi block() chỉ để đo thời gian.
- Không consume Flux trong một nhánh rồi trả Flux gốc cho caller.
- Không mở connection phụ để suy luận pool wait của query chính.
- Không thay đổi exception hoặc empty signal chỉ để tạo metric.
- Không ghi log đồng bộ nặng trên event-loop.
- Không tạo tag động theo mỗi request.
- Đảm bảo timer được tạo theo subscription nếu publisher có thể được subscribe nhiều lần.

Nếu dùng helper instrumentation, hãy kiểm tra helper giữ nguyên onNext, complete, error, cancellation và backpressure.

## 20. Transaction annotation và vị trí đặt timer

Với method có `@Transactional`, Spring transaction interceptor bao publisher reactive mà method trả về. Nếu muốn đo thời gian mà caller quan sát được, đặt timer ở caller boundary:

~~~java
public Mono<Order> submit(CreateOrderCommand command) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return orderService.createOrder(command)
                .doFinally(signal -> sample.stop(orderTransactionTimer));
    });
}
~~~

Trong ví dụ, `orderService.createOrder` cần được gọi qua Spring proxy. Việc gọi method bên trong `Mono.defer` giúp thời điểm gọi và subscribe nằm trong cùng lifecycle đo.

Nếu đặt timer bên trong method trước khi publisher được subscribe, thời gian publisher nằm chờ có thể bị tính sai. Nếu timer nằm bên trong một operator trước transaction interceptor, nó có thể không bao gồm toàn bộ commit/rollback cleanup.

Đối với nhu cầu đo chính xác transaction completion, cân nhắc transaction synchronization/observation ở tầng transaction manager. Ghi rõ đây là service operation duration hay transaction manager duration.

## 21. Transaction synchronization cho sự kiện hoàn tất

Spring reactive transaction hỗ trợ transaction synchronization trong Reactor Context khi transaction manager đang hoạt động. Synchronization có thể nhận thông báo sau completion để phân loại commit hoặc rollback theo transaction lifecycle.

Ý tưởng sử dụng:

- Đăng ký synchronization trong transaction context hiện hành.
- Ghi timestamp khi transaction bắt đầu hoặc khi synchronization được đăng ký theo ranh giới phù hợp.
- Trong callback after-completion, ghi duration và trạng thái commit/rollback.
- Không lưu transaction synchronization trong ThreadLocal imperative.
- Không đăng ký synchronization ngoài reactive transaction rồi kỳ vọng callback sẽ chạy.

API và callback cụ thể phụ thuộc Spring Framework version và cách transaction được tạo. Khi cần đo commit/rollback chính xác, hãy dùng API reactive transaction synchronization tương ứng của phiên bản đang chạy và kiểm tra bằng integration test.

Không tự tạo một transaction phụ chỉ để đo transaction chính. Việc đó sẽ thay đổi connection usage và làm số đo sai.

## 22. Ví dụ phân tích một request chậm

Giả sử dashboard cho thấy:

| Chỉ số | Giá trị |
|---|---:|
| Request duration p95 | 900 ms |
| Pool acquire p95 | 500 ms |
| Query duration p95 | 70 ms |
| Transaction duration p95 | 760 ms |
| Pending acquire | Tăng liên tục |
| Database CPU | 40% |

Diễn giải:

1. Request chậm phần lớn vì chờ pool.
2. Query không quá chậm theo số đo hiện tại.
3. Transaction kéo dài hơn tổng thời gian SQL nhiều, có thể có logic hoặc khoảng chờ giữa các query.
4. Database CPU chưa cao, nhưng cần kiểm tra lock, session và workload khác.
5. Tăng pool có thể giúp nếu database còn headroom, nhưng trước hết cần xem connection hold duration và transaction boundary.

Một trường hợp khác:

| Chỉ số | Giá trị |
|---|---:|
| Request duration p95 | 850 ms |
| Pool acquire p95 | 8 ms |
| Query duration p95 | 720 ms |
| Transaction duration p95 | 780 ms |
| Database CPU | 95% |
| Lock wait | Thấp |

Trường hợp này pool không phải nút thắt chính. Cần xem query plan, index, dữ liệu, số hàng đọc và concurrency. Tăng max-size có thể làm database bão hòa hơn.

Các con số chỉ là ví dụ minh họa. Kết luận thực tế cần xem cùng thời điểm, cùng workload và cùng ranh giới đo.

## 23. Alert theo triệu chứng và SLO

Không nên đặt alert chỉ vì một query vượt một ngưỡng cố định. Một thao tác batch có thể hợp lệ khi chạy lâu hơn một lookup.

Có thể định nghĩa SLO theo loại operation:

- Lookup theo ID: latency p95/p99.
- Ghi đơn hàng: latency và error rate.
- Batch import: throughput và thời gian hoàn tất batch.
- Transaction: duration và rollback rate.
- Pool: acquire timeout, pending queue và saturation.

Alert nên kết hợp:

- Duration vượt ngưỡng trong một khoảng thời gian.
- Error/timeout rate tăng.
- Pending acquire liên tục cao.
- Acquired gần max-size kéo dài.
- Database resource hoặc lock wait bất thường.
- Request SLO bị vi phạm.

Dùng cửa sổ thời gian đủ để tránh cảnh báo do một spike rất ngắn. Với metric histogram, tính percentile từ bucket hoặc backend theo cấu hình phù hợp. Đừng chỉ dùng max vì một sample đơn lẻ có thể tạo alert nhiễu.

## 24. Kiểm thử instrumentation

Instrumentation cần được kiểm tra để bảo đảm nó không thay đổi semantics của publisher.

Có thể dùng publisher giả lập với delay để xác nhận timer:

~~~java
@Test
void shouldRecordPublisherDuration() {
    Mono<String> source = Mono.delay(Duration.ofMillis(20))
            .map(ignored -> "ok");

    StepVerifier.create(metrics.measure("test.operation", source))
            .expectNext("ok")
            .verifyComplete();

    assertThat(registry.get("app.r2dbc.operation")
            .timer()
            .count())
            .isEqualTo(1);
}
~~~

Ví dụ minh họa cần điều chỉnh theo helper đo metric thực tế. Các trường hợp nên kiểm tra:

- Mono success.
- Mono empty.
- Flux complete.
- Error.
- Cancellation.
- Publisher được subscribe nhiều lần.
- Retry: mỗi attempt và toàn operation được đo đúng ranh giới.
- Instrumentation không tạo thêm subscription.
- Tag luôn có cardinality giới hạn.

Để kiểm tra pool acquire, query và transaction thật, dùng integration test với R2DBC driver/database. Có thể tạo tải có kiểm soát hoặc cố tình giới hạn pool nhỏ trong test để quan sát pending acquire và timeout. Tránh dùng sleep tùy tiện; dùng StepVerifier, latches hoặc test utilities có điều phối rõ.

## 25. Quy trình điều tra một thao tác database chậm

Khi phát hiện query/request chậm, đi theo thứ tự:

1. Xác định operation và khoảng thời gian đo chính xác.
2. So sánh request duration với repository/query duration.
3. Xem pool acquire latency và pending acquire.
4. Xem connection acquired, idle và max-size.
5. Xem transaction duration và connection hold duration.
6. Xác định query nào chiếm thời gian lớn trong transaction.
7. Đối chiếu statement timing với database server statistics.
8. Kiểm tra lock wait, slow query và execution plan.
9. Kiểm tra result size, streaming và downstream consumer.
10. Kiểm tra retry/backoff có làm operation kéo dài không.
11. Thay đổi một yếu tố, chạy lại cùng workload và so sánh p95/p99.
12. Theo dõi sau deploy để xác nhận cải thiện.

Không tăng pool chỉ vì request chậm. Không tối ưu query chỉ vì transaction dài. Đầu tiên xác định phần thời gian nằm ở acquire, statement, fetch, app work hay transaction completion.

## 26. Những lỗi thường gặp khi đo

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Query duration bao gồm thời gian publisher chưa subscribe | Timer bắt đầu khi tạo publisher | Bắt đầu trong `defer` |
| Query metric ghi hai lần | Tự subscribe thêm để log | Gắn operator vào publisher gốc |
| Timer không ghi khi subscriber cancel | Chỉ dùng doOnSuccess/doOnComplete | Dùng doFinally và phân loại cancel |
| Mono empty bị tính là error hoặc success có dữ liệu | Không phân biệt null trong doOnSuccess | Ghi outcome empty riêng |
| Flux duration chỉ phản ánh row đầu | Dừng timer trong doOnNext đầu tiên | Đo tới complete/error/cancel |
| Pool wait bị nhầm là SQL chậm | Timer repository bao cả acquisition | Đo pool acquire riêng |
| Transaction duration lớn hơn tổng query | Có logic/chờ giữa statement hoặc cleanup | Đo transaction boundary và connection hold |
| Pool pending tăng nhưng query nhanh | Connection bị giữ lâu hoặc pool nhỏ | Kiểm tra hold time và transaction |
| Metric backend quá tải | Tag chứa ID/SQL/trace | Dùng tag có cardinality thấp |
| p99 không ổn định | Sample count ít hoặc histogram chưa phù hợp | Xem count, bucket và cửa sổ đo |
| Retry làm latency người dùng tăng nhưng query timer bình thường | Timer chỉ đo từng attempt | Đo cả attempt và toàn operation |
| Log chậm làm ứng dụng chậm thêm | Log quá nhiều hoặc ghi đồng bộ nặng | Sampling, rate limit và async logging phù hợp |
| Số đo client khác server | Ranh giới đo khác nhau | Ghi rõ client/server timing và đối chiếu |

## 27. Checklist triển khai observability cho R2DBC

Trước khi đưa metrics vào production, xác nhận:

1. Query timer bắt đầu tại subscription, không phải lúc tạo publisher.
2. Query timer có ranh giới rõ: repository operation, statement hay toàn stream.
3. Flux có time-to-first-row và time-to-complete khi cần.
4. Pool acquire duration được đo riêng với query duration.
5. Pool gauges có acquired, idle, allocated và pending nếu driver/pool hỗ trợ.
6. Transaction duration được đo tại boundary phù hợp.
7. Có thể phân loại commit, rollback, error và cancellation khi cần.
8. Connection hold duration được quan sát hoặc có cách suy luận đáng tin cậy.
9. Có p50/p95/p99 và sample count cho operation quan trọng.
10. Tag metric có cardinality thấp.
11. SQL/bind data nhạy cảm không bị ghi vào metrics/log.
12. Retry được đo theo attempt và toàn operation.
13. Instrumentation không gọi subscribe/block hoặc tạo query phụ.
14. Metrics pool, application và database được đối chiếu cùng thời điểm.
15. Có dashboard/alert theo SLO và triệu chứng.
16. Đã kiểm thử instrumentation với success, empty, error, cancel và nhiều subscription.

## 28. Kết luận

Đo thời gian truy vấn, thời gian chờ pool và thời gian giao dịch giúp phân biệt ba nguồn chậm thường bị gộp chung trong ứng dụng Spring Data R2DBC. Timer quanh repository publisher cho biết thời gian quan sát ở tầng ứng dụng; instrumentation tại ConnectionFactory/pool cho biết thời gian acquire; statement proxy và database metrics giúp hiểu thời gian thực thi SQL; timer hoặc transaction synchronization cho biết transaction tồn tại bao lâu và kết thúc theo cách nào.

Hãy bắt đầu phép đo khi publisher được subscribe, dùng đồng hồ đơn điệu, ghi nhận complete/error/cancel và không tạo subscription phụ. Kết hợp duration với pool gauges, transaction duration, database CPU/lock và request latency p95/p99. Giữ metric tag có cardinality thấp và bảo vệ dữ liệu SQL nhạy cảm. Khi các số đo có ranh giới rõ và được đối chiếu cùng nhau, bạn có thể xác định nên tối ưu query, giảm thời gian giữ connection, điều chỉnh concurrency/pool hay thu hẹp transaction boundary thay vì thay đổi cấu hình theo phỏng đoán.

