# Cô lập JDBC và thư viện chặn khi chưa thể thay thế

Trong ứng dụng reactive, một lời gọi JDBC hoặc một thư viện đồng bộ có thể giữ thread cho đến khi thao tác I/O hoàn tất. Nếu lời gọi đó chạy trên event loop của WebFlux hoặc trên thread dùng để phát tín hiệu cho nhiều request, một truy vấn chậm có thể làm trì hoãn nhiều luồng xử lý khác. Khi chưa thể thay JDBC bằng driver reactive hoặc thay thư viện cũ bằng API bất đồng bộ, ta vẫn có thể tích hợp chúng an toàn hơn bằng cách cô lập phần blocking trên Scheduler phù hợp và kiểm soát lượng công việc được đưa vào.

Bài học thuộc chương **Tích hợp I/O** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy theo các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành **Mono**, **Flux**, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Bài này tập trung vào cách đưa JDBC và thư viện blocking vào Reactor khi việc thay thế chúng chưa khả thi, đồng thời làm rõ các giới hạn về thread, transaction, connection pool và cancellation.

## Vì sao JDBC có thể làm nghẽn pipeline reactive?

JDBC là API đồng bộ. Khi gọi `executeQuery`, `executeUpdate` hoặc đọc `ResultSet`, thread gọi phương thức thường phải chờ driver và database hoàn tất công việc. Trong khi chờ, thread đó không thể xử lý tín hiệu khác.

Một server reactive như WebFlux thường dùng số lượng event loop thread nhỏ và chia sẻ chúng giữa nhiều kết nối. Nếu một controller gọi JDBC trực tiếp trên event loop, thao tác blocking có thể giữ thread xử lý request trong thời gian chờ database. Nhiều request đồng thời sẽ cạnh tranh số thread hữu hạn và làm tăng độ trễ toàn hệ thống.

Vấn đề tương tự xuất hiện với các thư viện cũ:

- HTTP client đồng bộ hoặc SOAP client cũ.
- SDK của nhà cung cấp chỉ có phương thức blocking.
- Truy cập tệp đồng bộ hoặc API hệ thống chờ I/O.
- Thư viện xử lý tài liệu gọi I/O đồng bộ bên trong.

Đưa các lời gọi này vào một pipeline `Mono` hoặc `Flux` không tự biến chúng thành non-blocking. Cần xác định đúng ranh giới blocking và chuyển phần thực thi đó sang Scheduler chuyên xử lý tác vụ chờ I/O.

## Dùng fromCallable kết hợp subscribeOn

Với một lời gọi JDBC trả về một kết quả, có thể dùng `Mono.fromCallable`:

~~~java
Mono<Customer> findCustomer(String customerId) {
    return Mono.fromCallable(() ->
            jdbcTemplate.queryForObject(
                "select id, name from customer where id = ?",
                customerRowMapper,
                customerId
            ))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Hai phần của pipeline giải quyết hai vấn đề riêng:

- `fromCallable` trì hoãn việc gọi JDBC đến khi có subscription và chuyển exception được ném thành tín hiệu `onError`.
- `subscribeOn(Schedulers.boundedElastic())` đưa quá trình thực thi nguồn sang Scheduler dành cho các tác vụ blocking có thời gian chờ không cố định.

Nhờ đó, thread gọi subscribe không trực tiếp chờ truy vấn JDBC. Khi truy vấn hoàn tất, kết quả hoặc lỗi được chuyển tiếp trong pipeline reactive.

Không nên dùng `Mono.just` để bọc kết quả của một lời gọi blocking:

~~~java
// Lời gọi JDBC chạy ngay khi phương thức này được gọi.
Mono<Customer> unsafe = Mono.just(
    jdbcTemplate.queryForObject(sql, customerRowMapper, customerId)
);
~~~

Đối số của `Mono.just` được tính trước khi `Mono` được tạo. Thêm `subscribeOn` sau đó cũng không thể chuyển ngược lời gọi đã xảy ra. Hãy đặt lời gọi bên trong `fromCallable`.

Với thao tác không trả về giá trị, có thể dùng `Mono.fromRunnable`:

~~~java
Mono<Void> updateLastSeen(String customerId) {
    return Mono.fromRunnable(() ->
            jdbcTemplate.update(
                "update customer set last_seen = current_timestamp where id = ?",
                customerId
            ))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`fromRunnable` phát hoàn tất khi Runnable chạy xong và phát lỗi nếu Runnable ném exception. Đây là cách phù hợp cho thao tác ghi mà caller chỉ cần biết nó đã hoàn tất hay thất bại.

## Cô lập một thư viện blocking bất kỳ

Nguyên tắc tương tự áp dụng cho SDK đồng bộ:

~~~java
Mono<LegacyResponse> callLegacyService(LegacyRequest request) {
    return Mono.fromCallable(() ->
            legacyClient.execute(request))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Nên đặt adapter tại ranh giới tích hợp. Các tầng service phía trên chỉ làm việc với `Mono` hoặc `Flux`, không cần biết lời gọi bên dưới đang dùng JDBC hay SDK blocking. Khi thư viện được thay bằng API reactive thật sự, có thể thay phần triển khai adapter mà ít ảnh hưởng đến hợp đồng của các tầng gọi.

Nếu thư viện đã có API bất đồng bộ hoặc reactive chính thức, hãy ưu tiên API đó. Không cần đưa một HTTP client non-blocking sang `boundedElastic` chỉ vì nó thực hiện I/O. Scheduler cần phản ánh hành vi thực tế của phương thức.

## Quản lý Connection và tài nguyên trong phạm vi lời gọi blocking

Khi dùng `JdbcTemplate`, Spring quản lý việc lấy và trả connection theo cơ chế của nó. Với JDBC thuần, cần đảm bảo connection, statement và result set được đóng ngay trong khối blocking:

~~~java
Mono<List<Customer>> loadCustomers(DataSource dataSource) {
    return Mono.fromCallable(() -> {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(
                     "select id, name from customer");
             ResultSet resultSet = statement.executeQuery()) {

            List<Customer> customers = new ArrayList<>();
            while (resultSet.next()) {
                customers.add(new Customer(
                    resultSet.getString("id"),
                    resultSet.getString("name")
                ));
            }
            return List.copyOf(customers);
        }
    }).subscribeOn(Schedulers.boundedElastic());
}
~~~

Toàn bộ chuỗi lấy connection, thực thi câu lệnh, đọc kết quả và đóng tài nguyên nằm trong cùng một lần gọi đồng bộ. `try-with-resources` đảm bảo các tài nguyên được đóng khi khối lệnh hoàn tất hoặc ném lỗi. `fromCallable` giữ toàn bộ khối đó trên worker của `boundedElastic`.

Không nên lấy connection ở một thread rồi giữ nó qua nhiều bước reactive có thể đổi scheduler. JDBC connection và các transaction imperative thường gắn với thread hoặc cơ chế quản lý tài nguyên của framework. Giữ connection mở trong khi chờ một Publisher khác có thể chiếm connection của pool lâu hơn cần thiết và làm transaction khó dự đoán.

Với kết quả lớn, tránh tải toàn bộ bảng vào một `List` nếu ứng dụng có thể xử lý theo trang. Mỗi trang có thể là một thao tác blocking ngắn, được điều phối riêng, hoặc dùng cơ chế cursor có vòng đời được quản lý trọn vẹn trong cùng một khối blocking. Không phát `ResultSet` ra ngoài khối đã đóng connection.

## Transaction JDBC phải nằm trọn trong thao tác blocking

Transaction JDBC imperative thường dựa vào connection được giữ trong suốt transaction. Với Spring transaction manager kiểu JDBC, tài nguyên thường được gắn với thread hiện tại. Vì vậy, một cách tích hợp rõ ràng là đặt toàn bộ transaction imperative bên trong một `Callable`:

~~~java
Mono<Order> updateOrder(String orderId) {
    return Mono.fromCallable(() ->
            transactionTemplate.execute(status -> {
                orderRepository.updateStatus(orderId, "PAID");
                inventoryRepository.reserveFor(orderId);
                return orderRepository.findById(orderId);
            }))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`transactionTemplate.execute` bắt đầu, commit hoặc rollback transaction trong cùng lời gọi đồng bộ. Các thao tác repository bên trong được thực hiện trên cùng thread trong phạm vi transaction đó.

Không nên chia một transaction JDBC imperative thành nhiều toán tử reactive rồi giả định transaction tự đi theo subscription khi scheduler thay đổi:

~~~java
// Không dùng mô hình này để giữ một JDBC transaction qua các ranh giới async.
Mono<Order> unsafe = beginJdbcTransaction()
    .then(loadOrderReactive())
    .publishOn(Schedulers.parallel())
    .flatMap(this::updateOrderReactive);
~~~

Nếu `beginJdbcTransaction` dùng ThreadLocal hoặc connection gắn với thread, việc chuyển scheduler có thể làm các bước sau không còn chạy trong transaction đã mở. Transaction reactive cần driver và transaction manager hỗ trợ reactive, chẳng hạn R2DBC. Nếu hệ thống vẫn dùng JDBC, hãy giữ transaction đồng bộ trong một đơn vị blocking có giới hạn thời gian và độ dài hợp lý.

Không giữ transaction JDBC mở trong khi chờ một lời gọi mạng khác. Thời gian giữ connection dài làm giảm khả năng phục vụ request khác và tăng nguy cơ timeout hoặc deadlock. Nếu quy trình nghiệp vụ gồm cả database và dịch vụ bên ngoài, hãy thiết kế ranh giới transaction, trạng thái trung gian và cơ chế bù trừ phù hợp thay vì kéo dài một transaction JDBC qua toàn bộ workflow.

## Giới hạn concurrency để bảo vệ connection pool

`Schedulers.boundedElastic()` giới hạn số worker theo cấu hình, nhưng điều đó không đồng nghĩa số lời gọi JDBC luôn phù hợp với kích thước connection pool. Nếu nhiều subscription cùng lúc chờ connection, pool có thể cạn và các tác vụ tiếp tục chiếm worker trong lúc đợi.

Với một luồng ID cần tải từng bản ghi, có thể giới hạn số Publisher con đồng thời bằng `flatMap`:

~~~java
Flux<Customer> customers = customerIds
    .flatMap(this::findCustomer, maxConcurrent);
~~~

`maxConcurrent` là giới hạn do ứng dụng lựa chọn dựa trên năng lực của connection pool, tải database và các luồng công việc khác đang dùng chung pool. Không nên đặt nó bằng toàn bộ số connection tối đa nếu còn request khác cần truy cập database. Cần chừa dung lượng cho các thao tác quan trọng và theo dõi thời gian chờ lấy connection.

Nếu cần xử lý tuần tự, dùng `concatMap`:

~~~java
Flux<UpdateResult> updates = updateRequests
    .concatMap(this::applyBlockingUpdate);
~~~

`concatMap` chỉ đăng ký Publisher con tiếp theo sau khi Publisher hiện tại hoàn tất. Cách này giảm concurrency và giữ thứ tự xử lý theo đầu vào, nhưng có thể làm throughput thấp hơn. Hãy dùng khi thứ tự là yêu cầu nghiệp vụ hoặc khi muốn kiểm soát tải ở mức một thao tác tại một thời điểm.

Không nên gọi hàng nghìn tác vụ blocking cùng lúc rồi hy vọng scheduler tự điều tiết toàn bộ tài nguyên. Cần xem xét đồng thời giới hạn worker, giới hạn concurrency của pipeline, kích thước connection pool và khả năng chịu tải của database.

## Timeout, lỗi và retry

Có thể đặt timeout ở pipeline để giới hạn thời gian chờ của subscriber:

~~~java
Mono<Customer> customer = findCustomer(customerId)
    .timeout(Duration.ofSeconds(2))
    .onErrorMap(TimeoutException.class,
        error -> new CustomerLookupTimeoutException(customerId, error));
~~~

Timeout reactive giới hạn thời gian mà pipeline chờ tín hiệu. Tuy nhiên, cancellation của subscription không bảo đảm một lời gọi JDBC đã bắt đầu sẽ dừng ngay lập tức. Driver có thể tiếp tục thực thi cho đến khi truy vấn trả về hoặc bị hủy theo cơ chế riêng của driver.

Vì vậy, cần cấu hình thêm timeout ở đúng tầng:

- Query timeout hoặc statement timeout của JDBC/driver.
- Network/socket timeout nếu driver hỗ trợ.
- Connection acquisition timeout của pool.
- Deadline nghiệp vụ ở tầng service.

Các giới hạn này giải quyết những khoảng chờ khác nhau. Một timeout reactive không thay thế query timeout của database.

`retry` chỉ nên áp dụng cho lỗi tạm thời có thể thử lại an toàn. Với thao tác đọc, retry có giới hạn có thể phù hợp nếu lỗi được phân loại là transient. Với thao tác ghi, cần biết lần trước đã commit hay chưa; nếu không, retry có thể thực hiện side effect hai lần. Hãy dùng idempotency key, unique constraint hoặc cơ chế đối soát nếu thao tác có thể được gửi lại.

Ví dụ retry có giới hạn cho lỗi kết nối tạm thời:

~~~java
Mono<Customer> customer = findCustomer(customerId)
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
        .filter(this::isTransientDatabaseFailure));
~~~

Số lần thử và khoảng backoff cần phù hợp với SLA, connection pool và khả năng chịu tải của database. Retry không phân loại có thể khuếch đại sự cố khi database đang quá tải.

## Cancellation không đảm bảo dừng JDBC ngay lập tức

Khi client đóng kết nối hoặc downstream hủy subscription, Reactor truyền cancellation ngược lên upstream. Một Publisher có thể dừng timer, hủy HTTP request hoặc giải phóng tài nguyên nếu API nền hỗ trợ. Nhưng lời gọi JDBC blocking đã chạy thường không thể bị dừng tức thì chỉ bằng `dispose` hoặc `cancel`.

Điều này có một hệ quả vận hành: request đã hết hạn có thể không còn cần kết quả, nhưng worker vẫn bị giữ cho đến khi JDBC call kết thúc. Nếu nhiều truy vấn như vậy xảy ra, worker và connection pool vẫn có thể bị chiếm dù client đã ngắt kết nối.

Để giảm rủi ro:

- Cấu hình query timeout và network timeout tại driver.
- Giới hạn số thao tác blocking đồng thời.
- Giữ transaction ngắn và đóng connection trong cùng khối blocking.
- Theo dõi truy vấn chạy lâu, pool pending và số worker đang hoạt động.
- Ưu tiên driver reactive khi hệ thống cần cancellation và backpressure xuyên suốt đến database.

Đừng coi việc client hủy request là bằng chứng truy vấn đã bị database dừng hoặc transaction đã rollback. Với lệnh ghi, cần xác định kết quả cuối cùng qua trạng thái lưu trữ hoặc mã giao dịch.

## Kiểm thử adapter blocking

Có thể kiểm thử rằng lời gọi chỉ chạy khi có subscription và exception được truyền thành tín hiệu lỗi:

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> source = Mono.fromCallable(() -> {
    calls.incrementAndGet();
    return 42;
}).subscribeOn(Schedulers.boundedElastic());

assertEquals(0, calls.get());

StepVerifier.create(source)
    .expectNext(42)
    .verifyComplete();

assertEquals(1, calls.get());
~~~

Kiểm thử này xác nhận tính lazy của adapter. Nó không chứng minh bằng chính nó rằng mọi lời gọi chạy trên thread phù hợp; nếu cần xác minh scheduler, có thể inject một Scheduler vào adapter và kiểm soát nó trong test, hoặc quan sát thread tại ranh giới blocking trong integration test.

Kiểm thử lỗi từ thư viện blocking:

~~~java
IOException original = new IOException("legacy storage unavailable");

Mono<String> source = Mono.fromCallable(() -> {
    throw original;
}).subscribeOn(Schedulers.boundedElastic());

StepVerifier.create(source)
    .expectErrorMatches(error -> error == original)
    .verify();
~~~

Kiểm thử giới hạn concurrency có thể dùng bộ đếm số tác vụ đang hoạt động và một nguồn test điều khiển được. Mục tiêu là xác nhận số lời gọi JDBC đồng thời không vượt quá giới hạn cấu hình của adapter. Với integration test, nên xác minh thêm connection pool không bị cạn trong tải dự kiến và timeout của driver có tác dụng như mong đợi.

## Khi nào nên thay JDBC bằng R2DBC?

Cô lập JDBC là một giải pháp tích hợp thực tế khi thư viện hoặc driver reactive chưa có, hoặc khi việc thay thế chưa phù hợp với phạm vi dự án. Tuy nhiên, JDBC vẫn là blocking I/O. `boundedElastic` bảo vệ event loop bằng cách chuyển phần chờ sang worker khác, nhưng không biến toàn bộ đường đi đến database thành non-blocking.

Nên cân nhắc R2DBC hoặc driver reactive khi:

- Hệ thống cần nhiều kết nối đồng thời và muốn tránh giữ thread trong lúc chờ database.
- Backpressure và cancellation cần đi xuyên suốt đến thao tác database.
- Kiến trúc đã dùng reactive transaction manager.
- Driver, database và hệ sinh thái quan sát hỗ trợ đầy đủ cho nhu cầu triển khai.

Việc chuyển đổi có chi phí: API, transaction, mapping, kiểm thử và vận hành có thể khác JDBC. Không nên thay driver chỉ để làm cho chữ ký phương thức trả về `Mono`; cần đánh giá cả hành vi thực thi và hợp đồng transaction.

## Những lỗi thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Gọi JDBC trực tiếp trong controller reactive | Có thể chặn event loop | Bọc bằng `fromCallable` và `subscribeOn(boundedElastic())` |
| Dùng `Mono.just(jdbcCall())` | JDBC chạy ngay khi lắp ráp pipeline | Dùng `Mono.fromCallable` |
| Dùng `publishOn` để chuyển lời gọi JDBC nguồn | `publishOn` chỉ đổi xử lý tín hiệu downstream | Dùng `subscribeOn` cho nguồn blocking |
| Dùng `Schedulers.parallel()` cho JDBC | Giữ worker CPU trong lúc chờ I/O | Dùng Scheduler dành cho blocking |
| Giữ JDBC connection qua nhiều bước async | Transaction và connection có thể không còn gắn với thread phù hợp | Giữ transaction trong một khối blocking hoặc dùng driver reactive |
| Không giới hạn số Publisher con JDBC | Có thể làm cạn connection pool và tăng hàng đợi | Dùng `flatMap` có giới hạn hoặc `concatMap` |
| Chỉ dùng `timeout` reactive | JDBC có thể vẫn tiếp tục chạy sau cancellation | Cấu hình timeout ở driver, statement và pool |
| Retry mọi lỗi ghi | Có thể lặp side effect | Phân loại lỗi và bảo đảm idempotency |

## Nguyên tắc thiết kế adapter blocking

Trước khi tích hợp JDBC hoặc thư viện đồng bộ vào pipeline reactive, hãy xác định:

1. Phương thức nào thực sự blocking và phần nào có thể dùng API reactive native?
2. Toàn bộ lời gọi blocking có nằm trong `fromCallable` hoặc `fromRunnable` không?
3. `subscribeOn(boundedElastic())` đã được đặt tại nguồn blocking chưa?
4. Connection, statement, result set và transaction được mở/đóng trong cùng phạm vi thực thi chưa?
5. Concurrency của pipeline có phù hợp với connection pool và giới hạn database không?
6. Timeout ở pipeline, driver, statement và pool đã được phân biệt rõ chưa?
7. Nếu cancellation xảy ra, công việc blocking có thể tiếp tục bao lâu và side effect được đối soát thế nào?
8. Kiểm thử có xác nhận tính lazy, tín hiệu lỗi, giới hạn concurrency và hành vi của driver không?

Cô lập lời gọi tại ranh giới adapter, chuyển nó sang Scheduler dành cho tác vụ chờ I/O, giữ transaction và tài nguyên trong một đơn vị thực thi đồng bộ có giới hạn, rồi kiểm soát concurrency theo năng lực của pool. Cách làm này giúp pipeline reactive tích hợp được hệ thống cũ mà vẫn nhận diện rõ phần nào còn blocking và những giới hạn cần quản lý.
