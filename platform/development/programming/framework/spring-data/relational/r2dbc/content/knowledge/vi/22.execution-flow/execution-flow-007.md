# Tách tác vụ chặn không thể tránh và đánh giá lại ranh giới giao dịch

## 1. Vì sao phải tách tác vụ blocking trong ứng dụng reactive?

Spring Data Relational R2DBC cung cấp API truy cập database theo mô hình reactive. Các thao tác thường trả về Mono hoặc Flux và không yêu cầu thread của ứng dụng phải chờ đồng bộ cho đến khi database trả kết quả.

Tuy nhiên, một ứng dụng thực tế có thể vẫn phải gọi thư viện cũ hoặc dịch vụ chỉ cung cấp API blocking, ví dụ:

- Thư viện JDBC cũ.
- SDK thanh toán chỉ có phương thức đồng bộ.
- API đọc file hoặc gọi hệ thống tệp đồng bộ.
- Client HTTP đời cũ thực hiện I/O chặn.
- Thư viện xử lý tài liệu có lời gọi đồng bộ tốn thời gian.
- Một API nội bộ chưa có phiên bản reactive.

Nếu gọi trực tiếp một phương thức blocking trên thread xử lý reactive, thread đó phải chờ cho đến khi công việc hoàn tất. Trong ứng dụng Spring WebFlux, điều này có thể chiếm thread event-loop vốn được thiết kế để xử lý nhiều request bằng các thao tác không chặn.

Giải pháp là cô lập tác vụ blocking vào scheduler phù hợp, thường là Schedulers.boundedElastic(), rồi kết hợp kết quả trở lại pipeline reactive.

Việc tách blocking chỉ giải quyết vấn đề sử dụng thread. Nó chưa tự giải quyết câu hỏi quan trọng khác: tác vụ blocking nên chạy ở trong hay ngoài transaction R2DBC? Nếu một transaction đã mở và đang giữ connection trong lúc chờ lời gọi blocking, connection và có thể cả lock database sẽ bị giữ lâu hơn cần thiết.

Bài này tập trung vào hai quyết định có liên quan:

1. Đưa tác vụ blocking không thể tránh ra khỏi event-loop.
2. Thiết kế lại ranh giới transaction để transaction R2DBC chỉ bao quanh các thao tác database thực sự cần tính nguyên tử.

## 2. Phân biệt blocking và non-blocking

### 2.1. Blocking là gì?

Một lời gọi blocking giữ thread hiện tại cho đến khi có kết quả hoặc hết thời gian chờ.

Ví dụ:

~~~java
String response = legacyClient.fetchCustomer(customerId);
~~~

Nếu fetchCustomer gọi mạng đồng bộ và mất 2 giây, thread gọi phương thức phải chờ trong khoảng thời gian đó. Thread không thể tiếp tục xử lý công việc khác trong lúc chờ.

Tương tự:

~~~java
Customer customer = jdbcTemplate.queryForObject(
    "SELECT id, full_name FROM customers WHERE id = ?",
    customerRowMapper,
    customerId
);
~~~

JDBC là API blocking. Khi chạy câu truy vấn, thread gọi phải chờ database trả kết quả.

### 2.2. Non-blocking là gì?

Với API reactive, thao tác được biểu diễn bằng publisher. Thread gọi không phải đứng chờ kết quả theo kiểu đồng bộ:

~~~java
Mono<Customer> customer =
    customerRepository.findById(customerId);
~~~

Đoạn code tạo publisher. Khi publisher được subscribe, R2DBC driver thực hiện I/O theo API non-blocking và phát tín hiệu khi có kết quả, lỗi hoặc hoàn tất.

Cần nhớ:

- Mono và Flux là kiểu biểu diễn một luồng xử lý, không phải bằng chứng rằng mọi dòng code bên trong đều non-blocking.
- Nếu gọi một hàm blocking bên trong map, flatMap hoặc doOnNext, hàm đó vẫn chặn thread đang thực thi callback.
- Việc một phương thức trả về Mono không có nghĩa phần code trước khi tạo Mono tự động trở thành non-blocking.

Ví dụ sai:

~~~java
public Mono<CustomerView> getCustomer(Long id) {
    Customer customer = legacyClient.fetchCustomer(id); // Blocking ngay lúc gọi

    return Mono.just(toView(customer));
}
~~~

Lời gọi blocking xảy ra trước khi publisher được trả về. Không có scheduler nào tự động chuyển nó sang thread khác.

## 3. Cô lập blocking call bằng Mono.fromCallable

### 3.1. Mẫu cơ bản

Với phương thức blocking trả về một giá trị, dùng Mono.fromCallable() và subscribeOn(Schedulers.boundedElastic()):

~~~java
public Mono<CustomerProfile> loadProfile(Long customerId) {
    return Mono.fromCallable(
            () -> legacyClient.fetchCustomerProfile(customerId)
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Ý nghĩa:

- Mono.fromCallable() trì hoãn việc gọi hàm cho đến khi có subscription.
- subscribeOn(...) yêu cầu subscription và phần nguồn Callable chạy trên scheduler được chỉ định.
- Schedulers.boundedElastic() cung cấp worker phù hợp cho tác vụ blocking, với giới hạn tài nguyên thay vì tạo thread không kiểm soát.

Khi publisher được subscribe, lời gọi fetchCustomerProfile chạy trên bounded elastic worker. Event-loop không phải trực tiếp chờ lời gọi đó.

### 3.2. Không gọi blocking trước khi tạo Callable

Không viết:

~~~java
String result = legacyClient.fetchData();

return Mono.fromCallable(() -> result)
    .subscribeOn(Schedulers.boundedElastic());
~~~

Blocking đã xảy ra ở dòng đầu tiên. fromCallable chỉ bọc một biến đã có sẵn, nên không chuyển lời gọi sang scheduler khác.

Hãy đặt chính lời gọi blocking bên trong Callable:

~~~java
return Mono.fromCallable(() -> legacyClient.fetchData())
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 3.3. Dùng Mono.fromRunnable cho phương thức không trả kết quả

Nếu phương thức blocking chỉ thực hiện hành động và không trả giá trị, dùng Mono.fromRunnable():

~~~java
public Mono<Void> writeArchive(Long orderId) {
    return Mono.fromRunnable(
            () -> legacyArchiveClient.archive(orderId)
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Publisher hoàn tất khi phương thức blocking kết thúc. Nếu phương thức ném exception, publisher phát tín hiệu lỗi.

### 3.4. Xử lý kết quả null

Mono.fromCallable() không phát một phần tử null. Nếu Callable trả null, Mono hoàn tất rỗng.

Ví dụ:

~~~java
return Mono.fromCallable(
        () -> legacyClient.findOptionalCustomer(customerId)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .switchIfEmpty(Mono.error(
        new CustomerNotFoundException(customerId)
    ));
~~~

Hãy xác định rõ null có nghĩa là không tìm thấy dữ liệu, kết quả chưa có hay lỗi của thư viện cũ. Đừng để việc chuyển null thành Mono rỗng làm mất ý nghĩa nghiệp vụ.

## 4. Vì sao cần dùng boundedElastic?

### 4.1. Không chạy blocking trên event-loop

Các thread event-loop của WebFlux được thiết kế để xử lý nhanh callback và phối hợp I/O non-blocking. Nếu nhiều request cùng gọi một SDK blocking trên các thread này, event-loop có thể bị chiếm dụng. Các request khác phải chờ dù database hoặc network của chúng đã sẵn sàng.

Đưa blocking call sang boundedElastic giúp tách nhóm thread chờ I/O đồng bộ khỏi nhóm thread xử lý reactive.

### 4.2. boundedElastic có giới hạn tài nguyên

Schedulers.boundedElastic() được thiết kế cho tác vụ blocking có thời gian chờ. Scheduler quản lý số worker và hàng đợi theo giới hạn của Reactor, thay vì tạo thread vô hạn.

Tuy nhiên, boundedElastic không phải tài nguyên vô hạn:

- Nếu blocking call kéo dài, worker bị chiếm lâu.
- Nếu lượng tác vụ vượt khả năng xử lý, công việc có thể phải chờ trong hàng đợi.
- Nếu thư viện cũ bị treo hoặc không có timeout, worker có thể bị giữ quá lâu.
- Nếu đẩy một lượng công việc rất lớn vào scheduler, độ trễ và áp lực bộ nhớ có thể tăng.

Hãy cấu hình timeout ở chính client blocking, giới hạn concurrency khi xử lý nhiều phần tử và theo dõi tình trạng scheduler.

### 4.3. Không dùng parallel cho I/O blocking

Schedulers.parallel() hướng tới các tác vụ tính toán ngắn, không chặn. Không nên chuyển JDBC, file I/O đồng bộ hoặc HTTP client blocking sang parallel.

Mẫu phù hợp:

~~~java
Mono.fromCallable(() -> jdbcTemplate.queryForObject(
        "SELECT full_name FROM customers WHERE id = ?",
        String.class,
        customerId
    ))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Nếu tác vụ là tính toán CPU-bound thuần túy và không chặn I/O, có thể cân nhắc Schedulers.parallel(). Cần phân loại đúng loại công việc trước khi chọn scheduler.

### 4.4. Có thể tạo scheduler riêng cho thư viện blocking

Nếu hệ thống có một nhóm lời gọi blocking đặc thù cần giới hạn độc lập, có thể tạo bounded elastic scheduler riêng:

~~~java
@Configuration
public class LegacyClientSchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    public Scheduler legacyClientScheduler() {
        return Schedulers.newBoundedElastic(
            12,
            500,
            "legacy-client"
        );
    }
}
~~~

Sau đó inject scheduler:

~~~java
@Service
public class LegacyProfileService {

    private final LegacyClient legacyClient;
    private final Scheduler legacyClientScheduler;

    public LegacyProfileService(
            LegacyClient legacyClient,
            Scheduler legacyClientScheduler) {
        this.legacyClient = legacyClient;
        this.legacyClientScheduler = legacyClientScheduler;
    }

    public Mono<CustomerProfile> load(Long customerId) {
        return Mono.fromCallable(
                () -> legacyClient.fetchCustomerProfile(customerId)
            )
            .subscribeOn(legacyClientScheduler);
    }
}
~~~

Các giá trị thread cap và queue cap chỉ là ví dụ. Hãy chọn theo thời gian xử lý, mức concurrency, giới hạn của dịch vụ ngoài và tài nguyên triển khai. Scheduler riêng cũng cần được dispose khi ứng dụng dừng.

Không tạo một scheduler mới cho từng request. Scheduler là tài nguyên hạ tầng dùng chung theo vòng đời ứng dụng hoặc theo nhóm công việc.

## 5. Đặt subscribeOn đúng vị trí

### 5.1. subscribeOn và publishOn khác nhau

Hai toán tử có vai trò khác nhau:

- subscribeOn ảnh hưởng đến nơi subscription đi vào nguồn publisher và thường được dùng để chuyển lời gọi blocking được bọc trong fromCallable.
- publishOn chuyển việc xử lý các tín hiệu downstream sang scheduler khác kể từ vị trí toán tử.

Ví dụ:

~~~java
Mono.fromCallable(() -> legacyClient.fetchData())
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::toView);
~~~

Callable chạy trên boundedElastic. map tiếp theo nhận tín hiệu từ nguồn đó và thường chạy trên worker phát tín hiệu, trừ khi có toán tử scheduler khác thay đổi luồng thực thi.

### 5.2. publishOn đặt sau lời gọi không sửa được blocking đã xảy ra

Không nên viết:

~~~java
Mono.fromCallable(() -> legacyClient.fetchData())
    .publishOn(Schedulers.boundedElastic());
~~~

Với cách này, publishOn đặt sau nguồn không bảo đảm Callable được thực thi trên boundedElastic. publishOn điều khiển việc phát tín hiệu downstream; nó không phải cách chuyển subscription của nguồn blocking.

Hãy đặt subscribeOn trên publisher nguồn:

~~~java
Mono.fromCallable(() -> legacyClient.fetchData())
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 5.3. Chỉ cô lập phần blocking

Không cần chuyển toàn bộ pipeline R2DBC sang boundedElastic. Hãy bọc đúng lời gọi blocking:

~~~java
public Mono<CustomerView> getCustomer(Long id) {
    return Mono.fromCallable(() -> legacyClient.fetchName(id))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(name ->
            customerRepository.findById(id)
                .map(customer -> new CustomerView(
                    customer.getId(),
                    name,
                    customer.getEmail()
                ))
        );
}
~~~

Lời gọi legacy chạy trên boundedElastic. Truy vấn repository vẫn sử dụng R2DBC theo cơ chế reactive của nó.

Không thêm subscribeOn(boundedElastic()) cho mọi repository method chỉ vì một phần khác của flow là blocking. Điều đó làm khó quan sát scheduler và không biến một driver blocking thành R2DBC.

## 6. Kết hợp blocking call với repository reactive

Một flow có thể cần lấy thông tin từ SDK blocking rồi mới đọc hoặc ghi database:

~~~java
public Mono<CustomerView> loadCustomerView(Long customerId) {
    return Mono.fromCallable(
            () -> legacyClient.fetchExternalLabel(customerId)
        )
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(label ->
            customerRepository.findById(customerId)
                .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(customerId)
                ))
                .map(customer -> new CustomerView(
                    customer.getId(),
                    customer.getFullName(),
                    label
                ))
        );
}
~~~

Luồng này có các bước:

1. Subscriber kích hoạt Callable.
2. Callable chạy trên boundedElastic.
3. Khi có label, flatMap đăng ký publisher đọc từ repository.
4. Repository thực hiện truy vấn R2DBC.
5. Kết quả được chuyển thành CustomerView.

Nếu SDK blocking không cần dữ liệu từ transaction database, đây là cấu trúc tương đối đơn giản. Không cần mở transaction R2DBC trước khi gọi SDK.

### 6.1. Khi cần xử lý nhiều phần tử

Nếu phải gọi một API blocking cho từng phần tử, có thể dùng flatMap với giới hạn concurrency:

~~~java
public Flux<CustomerView> loadViews(Flux<Long> customerIds) {
    return customerIds.flatMap(
        id -> Mono.fromCallable(
                () -> legacyClient.fetchExternalLabel(id)
            )
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap(label ->
                customerRepository.findById(id)
                    .map(customer -> new CustomerView(
                        customer.getId(),
                        customer.getFullName(),
                        label
                    ))
            ),
        8
    );
}
~~~

Tham số 8 giới hạn số publisher con được subscribe đồng thời qua flatMap. Đây là ví dụ để minh họa giới hạn concurrency; giá trị thực tế phải dựa trên giới hạn của SDK, scheduler, database pool và dịch vụ ngoài.

Nếu thứ tự đầu ra phải giữ nguyên thứ tự đầu vào, cân nhắc flatMapSequential hoặc concatMap. concatMap xử lý tuần tự, giảm concurrency nhưng có thể tăng tổng thời gian.

Không tăng concurrency chỉ để sử dụng hết worker. Một SDK blocking có giới hạn kết nối riêng; gửi quá nhiều request có thể làm dịch vụ ngoài quá tải.

## 7. Tách transaction R2DBC khỏi lời gọi blocking

### 7.1. Vấn đề khi gọi blocking bên trong transaction

Xem ví dụ:

~~~java
@Transactional
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            Mono.fromCallable(() ->
                blockingPaymentClient.authorize(orderId)
            )
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap(payment -> {
                order.setStatus("PAID");
                return orderRepository.save(order);
            })
        );
}
~~~

Mặc dù blocking call đã được chuyển sang boundedElastic, transaction reactive vẫn có thể đang mở trong suốt publisher. Connection R2DBC được transaction manager gắn với Reactor Context có thể vẫn bị giữ trong lúc payment client chờ phản hồi.

Điều này gây ra một số hệ quả:

- Connection pool bị chiếm trong lúc không có câu SQL nào chạy.
- Transaction tồn tại lâu hơn cần thiết.
- Lock database có thể bị giữ lâu hơn.
- Transaction timeout dễ xảy ra hơn.
- Khi dịch vụ thanh toán chậm, các request khác có thể thiếu connection.
- Giao dịch database không thể tự rollback một khoản thanh toán đã được hệ thống ngoài chấp nhận.

Chuyển blocking call sang boundedElastic chỉ giải phóng event-loop. Nó không tự giải phóng connection hoặc kết thúc transaction đang bao quanh publisher.

### 7.2. Không mở transaction trước một lời gọi ngoài database nếu không cần

Nếu kiểm tra bên ngoài không cần nằm trong transaction database, hãy thực hiện nó trước. Sau khi có kết quả, mới mở transaction cho các thao tác database cần nguyên tử:

~~~java
public Mono<Order> confirmOrder(Long orderId) {
    return Mono.fromCallable(
            () -> blockingPaymentClient.authorize(orderId)
        )
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(paymentResult ->
            transactionalOperator.transactional(
                orderRepository.findById(orderId)
                    .switchIfEmpty(Mono.error(
                        new OrderNotFoundException(orderId)
                    ))
                    .flatMap(order -> {
                        order.setStatus("PAID");
                        order.setPaymentReference(
                            paymentResult.reference()
                        );
                        return orderRepository.save(order);
                    })
            )
        );
}
~~~

Trong ví dụ, lời gọi blocking hoàn tất trước khi TransactionalOperator mở transaction. Transaction chỉ bao quanh việc đọc và cập nhật order.

Đây là cấu trúc phù hợp khi kết quả thanh toán có thể được xác minh độc lập trước thao tác ghi database. Trong thực tế, cần xử lý thêm trường hợp trạng thái order đã thay đổi trong lúc gọi payment, request bị gửi lặp hoặc kết quả payment không thể áp dụng. Hãy dùng idempotency key và kiểm tra trạng thái nghiệp vụ trước khi ghi.

### 7.3. Nếu cần dữ liệu database trước khi gọi blocking

Có thể cần đọc một số dữ liệu để tạo request cho hệ thống ngoài. Không nhất thiết phải giữ transaction trong lúc chờ hệ thống đó.

Một cấu trúc có thể là:

1. Đọc dữ liệu cần thiết trong một truy vấn hoặc transaction ngắn.
2. Kết thúc transaction.
3. Gọi hệ thống blocking trên boundedElastic.
4. Mở transaction mới, đọc lại dữ liệu hiện tại và kiểm tra điều kiện.
5. Ghi kết quả nếu trạng thái vẫn phù hợp.

Ví dụ:

~~~java
public Mono<Order> processOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .map(this::toPaymentCommand)
        .flatMap(command ->
            Mono.fromCallable(
                    () -> blockingPaymentClient.authorize(command)
                )
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(paymentResult ->
                    transactionalOperator.transactional(
                        orderRepository.findById(orderId)
                            .switchIfEmpty(Mono.error(
                                new OrderNotFoundException(orderId)
                            ))
                            .flatMap(current -> {
                                if (!current.canApply(paymentResult)) {
                                    return Mono.error(
                                        new OrderStateConflictException(orderId)
                                    );
                                }

                                current.markPaid(paymentResult.reference());
                                return orderRepository.save(current);
                            })
                    )
                )
        );
}
~~~

Ví dụ nhấn mạnh việc tải lại trạng thái trong transaction ghi. Nếu entity có @Version, optimistic locking còn giúp phát hiện thay đổi cạnh tranh xảy ra sau lần đọc cuối và trước lúc save.

Nếu việc gọi hệ thống ngoài phải được thực hiện đúng một lần, không chỉ dựa vào việc gọi blocking trước transaction. Hãy thiết kế idempotency và xử lý kết quả không chắc chắn khi timeout.

## 8. Ranh giới transaction phải theo tính nguyên tử của dữ liệu

### 8.1. Transaction chỉ bảo vệ tài nguyên tham gia transaction đó

Một reactive transaction R2DBC bảo vệ các thao tác database tham gia cùng transaction manager và connection. Nó không tự động bao gồm:

- Một lời gọi HTTP tới dịch vụ khác.
- Một thao tác gửi email.
- Một lệnh ghi file.
- Một lời gọi SDK thanh toán.
- Một câu lệnh JDBC dùng connection riêng.
- Một message được gửi tới broker không tham gia transaction đó.

Nếu một trong các thao tác ngoài database thành công rồi thao tác R2DBC thất bại, rollback database không thể tự đảo ngược side effect bên ngoài.

### 8.2. JDBC blocking không tự tham gia R2DBC transaction

Một ứng dụng có thể dùng đồng thời R2DBC và JDBC, nhưng hai API thường dùng connection và transaction manager khác nhau.

Ví dụ:

~~~java
@Transactional
public Mono<Void> updateBothStores(Long id) {
    return orderRepository.findById(id)
        .flatMap(order -> {
            jdbcTemplate.update(
                "INSERT INTO legacy_audit(order_id) VALUES (?)",
                id
            );

            order.setStatus("UPDATED");
            return orderRepository.save(order);
        })
        .then();
}
~~~

Ví dụ này có vấn đề:

- jdbcTemplate.update(...) là blocking và đang chạy trên thread hiện tại.
- JDBC dùng transaction/connection của JDBC nếu được cấu hình, không tự động dùng R2DBC connection.
- @Transactional reactive thường được điều khiển bởi R2DBC reactive transaction manager nếu phương thức dùng transaction manager đó.
- Rollback R2DBC không mặc nhiên rollback lệnh JDBC đã commit độc lập.
- Lời gọi JDBC còn có thể chặn thread reactive.

Nếu bắt buộc dùng JDBC legacy, hãy cô lập nó bằng boundedElastic và thiết kế tính nhất quán giữa hai hệ thống một cách tường minh. Không giả định hai transaction manager độc lập tạo thành một transaction nguyên tử.

### 8.3. Transaction ngắn giúp giảm thời gian giữ connection

Transaction nên bao quanh những thao tác database phải cùng commit/rollback. Hãy tránh đưa các bước sau vào giữa transaction nếu chúng có thể chờ lâu:

- Gọi HTTP hoặc SDK blocking.
- Chờ người dùng xác nhận.
- Chờ message broker không tham gia transaction.
- Đọc/ghi file lớn.
- Tính toán dài không cần giữ trạng thái database.
- Retry một dịch vụ ngoài có thời gian chờ không dự đoán được.

Một transaction ngắn làm giảm thời gian giữ connection, giảm thời gian giữ lock và giảm nguy cơ pool bị cạn.

## 9. Khi nào dùng outbox hoặc saga?

Nếu nghiệp vụ phải phối hợp database với side effect bên ngoài, việc chỉ di chuyển blocking call ra ngoài transaction có thể chưa đủ. Cần một quy trình nhất quán.

### 9.1. Transactional outbox

Ví dụ, khi xác nhận đơn hàng, ứng dụng cần cập nhật trạng thái đơn hàng và ghi nhận yêu cầu gửi thông báo hoặc gọi hệ thống ngoài tiếp theo.

Thay vì gọi dịch vụ ngoài ngay trong transaction, ứng dụng ghi một outbox record cùng transaction với dữ liệu nghiệp vụ:

~~~java
public Mono<Order> markReadyForPayment(Long orderId) {
    return transactionalOperator.transactional(
        orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
            .flatMap(order -> {
                order.markPaymentPending();

                return orderRepository.save(order)
                    .flatMap(saved ->
                        outboxRepository.save(
                            OutboxEvent.paymentRequested(
                                saved.getId(),
                                saved.getVersion()
                            )
                        ).thenReturn(saved)
                    );
            })
    );
}
~~~

Sau khi transaction commit, một worker riêng đọc outbox và gọi hệ thống ngoài. Worker có thể dùng client reactive hoặc bọc client blocking bằng boundedElastic.

Lợi ích:

- Order và outbox event được ghi cùng transaction.
- Nếu transaction rollback, event không được ghi.
- Nếu ứng dụng dừng sau commit, event vẫn còn trong database để worker xử lý lại.
- Worker có thể retry theo chính sách và dùng idempotency key để tránh side effect lặp.

Outbox không làm hệ thống ngoài tham gia transaction R2DBC. Nó tạo một điểm ghi nhận bền vững để xử lý bất đồng bộ và phục hồi khi có lỗi.

### 9.2. Saga và hành động bù

Với nghiệp vụ nhiều bước qua nhiều hệ thống, có thể dùng saga. Mỗi bước hoàn tất độc lập và có hành động bù nếu bước sau thất bại.

Ví dụ:

1. Tạo đơn hàng ở trạng thái PENDING.
2. Gửi yêu cầu giữ tồn kho.
3. Yêu cầu thanh toán.
4. Cập nhật đơn hàng thành CONFIRMED.
5. Nếu thanh toán thất bại, giải phóng tồn kho và chuyển đơn hàng sang trạng thái phù hợp.

Các bước bù không phải rollback database theo nghĩa transaction ACID. Chúng là thao tác nghiệp vụ riêng, có thể thất bại và cần được retry/quan sát.

### 9.3. Chọn cách phù hợp

| Tình huống | Cách cân nhắc |
|---|---|
| Blocking call chỉ đọc dữ liệu bên ngoài, không cần cùng transaction | Gọi trước hoặc sau transaction, bọc bằng boundedElastic |
| Cập nhật nhiều bảng trong cùng một database | Reactive transaction ngắn |
| Ghi database rồi cần gửi message/email | Transactional outbox |
| Phối hợp nhiều hệ thống với nhiều bước và hành động bù | Saga |
| JDBC legacy và R2DBC cùng ghi dữ liệu | Thiết kế đồng bộ rõ ràng; không giả định một transaction chung |
| Gọi payment gateway có thể bị timeout và retry | Idempotency key, trạng thái trung gian và quy trình đối soát |

## 10. Đặt timeout và xử lý cancellation cho blocking call

### 10.1. Timeout ở publisher

Có thể đặt timeout ở mức reactive:

~~~java
Mono<PaymentResult> payment =
    Mono.fromCallable(() -> blockingPaymentClient.authorize(command))
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(5));
~~~

Timeout khiến subscriber nhận lỗi nếu không có tín hiệu trong thời gian quy định. Tuy nhiên, hủy subscription không bảo đảm một thư viện blocking sẽ dừng ngay lập tức. Nhiều phương thức blocking không kiểm tra interrupt hoặc không hỗ trợ cancellation.

Vì vậy, cần cấu hình timeout ngay trong client:

- Connect timeout.
- Read/response timeout.
- Request timeout.
- Timeout chờ connection từ pool riêng của SDK.

Timeout ở Reactor là lớp bảo vệ thêm cho pipeline. Nó không thay thế timeout bên trong thư viện blocking.

### 10.2. Cancellation không phải lúc nào cũng dừng được tác vụ blocking

Nếu client HTTP blocking đang chờ socket và subscriber cancel, thread có thể vẫn tiếp tục chờ cho đến khi client timeout hoặc lời gọi kết thúc. Điều này có thể giữ worker boundedElastic dù downstream đã bỏ kết quả.

Hãy chọn thư viện có timeout rõ ràng và khả năng hủy nếu có thể. Không khởi chạy các tác vụ blocking không giới hạn rồi kỳ vọng Reactor tự dừng tất cả khi request bị hủy.

### 10.3. Không retry mọi lỗi timeout

Timeout có thể xảy ra sau khi hệ thống ngoài đã thực hiện thao tác nhưng phản hồi chưa về. Ví dụ, cổng thanh toán đã nhận giao dịch nhưng ứng dụng không nhận được response. Gửi lại một yêu cầu thanh toán mới có thể tạo giao dịch trùng.

Hãy dùng idempotency key do nghiệp vụ quản lý, truy vấn trạng thái giao dịch hoặc quy trình đối soát trước khi retry một side effect có tính không đảo ngược.

## 11. Giới hạn concurrency cho tác vụ blocking

Schedulers.boundedElastic() có giới hạn tài nguyên nội bộ, nhưng pipeline cũng nên giới hạn số tác vụ mà ứng dụng phát ra.

Ví dụ:

~~~java
return customerIds.flatMap(
    id -> Mono.fromCallable(() -> legacyClient.fetchProfile(id))
        .subscribeOn(Schedulers.boundedElastic()),
    10
);
~~~

Tham số concurrency giới hạn số inner publisher được đăng ký đồng thời bởi flatMap. Điều này giúp ứng dụng không gửi hàng nghìn lời gọi blocking cùng lúc.

Cần xem xét đồng thời:

- Số worker của scheduler.
- Số kết nối mà SDK blocking có thể mở.
- Giới hạn rate của dịch vụ ngoài.
- Số connection trong R2DBC pool.
- Thời gian trung bình và phân vị cao của lời gọi blocking.
- Số request đồng thời trong ứng dụng.

Không dùng số worker bằng số connection R2DBC pool một cách máy móc. Hai nhóm tài nguyên phục vụ hai loại I/O khác nhau và có vòng đời khác nhau.

Nếu một luồng xử lý cần gọi blocking cho từng phần tử nhưng kết quả có thể xử lý độc lập, flatMap với concurrency giới hạn thường phù hợp. Nếu thứ tự là bắt buộc hoặc thư viện không thread-safe, dùng concatMap hoặc concurrency bằng 1.

## 12. Reactor Context và transaction context khi đổi scheduler

### 12.1. Reactive transaction không dựa vào thread cố định

Spring quản lý reactive transaction bằng Reactor Context. Vì vậy, transaction context có thể đi theo reactive pipeline qua các toán tử và scheduler switch được thực hiện đúng trong Reactor.

Không nên hiểu rằng đổi từ event-loop sang boundedElastic tự động làm mất transaction. Nếu publisher vẫn được nối trong cùng pipeline, Reactor Context được truyền theo subscription.

Tuy nhiên, nếu một đoạn code tự tạo thread, tự gọi subscribe hoặc chuyển sang một API callback không tích hợp Reactor Context, ngữ cảnh reactive có thể không còn được truyền như mong muốn.

### 12.2. Không tạo subscription độc lập

Ví dụ sai:

~~~java
@Transactional
public Mono<Void> updateOrder(Long orderId) {
    orderRepository.findById(orderId)
        .flatMap(order -> orderRepository.save(order))
        .subscribe();

    return Mono.empty();
}
~~~

Subscription gọi thủ công tách khỏi publisher mà Spring quản lý cho phương thức. Transaction có thể hoàn tất trước khi thao tác save kết thúc.

Hãy trả publisher:

~~~java
@Transactional
public Mono<Void> updateOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> orderRepository.save(order))
        .then();
}
~~~

Nếu cần gọi blocking, hãy kết hợp publisher đó vào chuỗi bằng flatMap thay vì subscribe thủ công.

### 12.3. ThreadLocal của thư viện cũ là vấn đề riêng

Một số thư viện blocking dùng ThreadLocal để lưu thông tin request, security principal, MDC hoặc transaction context. Reactor Context không đồng nghĩa với ThreadLocal.

Khi lời gọi được chuyển sang boundedElastic, ThreadLocal của thread ban đầu không tự động xuất hiện trên worker mới. Nếu thư viện cần các giá trị đó, hãy truyền chúng qua tham số hoặc dùng cơ chế context propagation phù hợp với framework và phiên bản đang dùng.

Không nên dựa vào việc hai bước tình cờ chạy trên cùng một thread. Reactive pipeline không cam kết giữ một thread duy nhất từ đầu đến cuối.

## 13. Những mẫu code cần tránh

### 13.1. Gọi blocking trực tiếp trong map

Không phù hợp:

~~~java
return customerRepository.findById(id)
    .map(customer -> legacyClient.fetchLabel(customer.getId()));
~~~

map có thể chạy trên thread phát tín hiệu từ R2DBC. Lời gọi blocking sẽ chiếm thread đó.

Cách tách:

~~~java
return customerRepository.findById(id)
    .flatMap(customer ->
        Mono.fromCallable(
                () -> legacyClient.fetchLabel(customer.getId())
            )
            .subscribeOn(Schedulers.boundedElastic())
            .map(label -> toView(customer, label))
    );
~~~

### 13.2. Dùng Mono.just với lời gọi blocking

Không phù hợp:

~~~java
return Mono.just(legacyClient.fetchData());
~~~

Java đánh giá đối số của Mono.just ngay lập tức. Lời gọi blocking xảy ra khi phương thức được gọi, trước subscription.

Cách đúng:

~~~java
return Mono.fromCallable(() -> legacyClient.fetchData())
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 13.3. Dùng block để gọi reactive code

Không phù hợp:

~~~java
return Mono.fromCallable(() ->
    customerRepository.findById(id).block()
).subscribeOn(Schedulers.boundedElastic());
~~~

Cách này biến truy vấn R2DBC thành thao tác blocking, tạo subscription lồng nhau và làm mất lợi ích của reactive composition. Không bọc một publisher reactive trong Callable chỉ để gọi block.

Hãy kết hợp publisher trực tiếp:

~~~java
return customerRepository.findById(id)
    .flatMap(customer -> processCustomer(customer));
~~~

### 13.4. Dùng publishOn sau lời gọi blocking

Không phù hợp:

~~~java
return Mono.just(legacyClient.fetchData())
    .publishOn(Schedulers.boundedElastic());
~~~

Lời gọi blocking được thực hiện trước khi Mono.just được tạo. publishOn không thể chuyển ngược việc đã xảy ra.

Cách đúng:

~~~java
return Mono.fromCallable(() -> legacyClient.fetchData())
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 13.5. Giữ transaction trong lúc gọi dịch vụ ngoài

Không nên mặc định:

~~~java
@Transactional
public Mono<Order> pay(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            Mono.fromCallable(() -> blockingPaymentClient.pay(order))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(result -> orderRepository.save(
                    order.withPaymentResult(result)
                ))
        );
}
~~~

Dù thread blocking đã được cô lập, transaction R2DBC vẫn có thể giữ connection trong lúc thanh toán chờ phản hồi. Nếu cổng thanh toán mất 10 giây, transaction cũng có thể kéo dài tương ứng.

Hãy đánh giá lại nghiệp vụ, tách transaction ghi ngắn và dùng trạng thái trung gian, outbox hoặc saga khi cần phối hợp side effect bên ngoài database.

## 14. Kiểm thử và quan sát

### 14.1. Kiểm tra blocking trên thread không được phép block

BlockHound có thể giúp phát hiện một số lời gọi blocking chạy trên thread được đánh dấu non-blocking trong lúc test. Đây là công cụ hữu ích khi phát triển ứng dụng Reactor/WebFlux.

Một test có thể xác nhận flow trả kết quả đúng:

~~~java
StepVerifier.create(service.loadProfile(42L))
    .expectNextMatches(profile ->
        profile.customerId().equals(42L)
    )
    .verifyComplete();
~~~

Test này kiểm tra kết quả reactive. Để xác nhận blocking call không chạy trên event-loop, cần test hoặc instrumentation phù hợp; không chỉ dựa vào việc StepVerifier hoàn tất.

### 14.2. Theo dõi scheduler

Khi dùng boundedElastic, quan sát:

- Số tác vụ đang chạy.
- Số tác vụ chờ.
- Thời gian chờ trước khi bắt đầu.
- Thời gian thực thi của blocking call.
- Tỷ lệ timeout và lỗi.
- Số worker bị chiếm lâu.

Nếu scheduler thường xuyên chạm giới hạn, hãy tìm nguyên nhân ở thời gian chờ, client timeout, concurrency và khả năng phục hồi của dịch vụ ngoài trước khi tăng thread cap.

### 14.3. Theo dõi transaction và connection pool

Đối với R2DBC, theo dõi:

- Thời gian transaction.
- Số connection đang được cấp.
- Số connection nhàn rỗi.
- Số request đang chờ connection.
- Query duration.
- Lock wait và transaction timeout nếu database cung cấp.

Nếu thời gian transaction tăng tương ứng với thời gian phản hồi của SDK blocking, có thể transaction đang bao quanh lời gọi ngoài database. Hãy xem lại ranh giới transaction thay vì chỉ tăng kích thước pool.

### 14.4. Kiểm tra lỗi khi cancel hoặc timeout

Hãy thử:

- Client blocking trả kết quả bình thường.
- Client blocking ném exception.
- Client blocking timeout.
- Request downstream cancel trước khi blocking call hoàn tất.
- Database lỗi sau khi blocking call thành công.
- Retry không tạo side effect lặp.

Một timeout ở reactive layer không bảo đảm tác vụ blocking đã dừng. Cần xác minh hành vi của chính thư viện và cấu hình timeout bên trong nó.

## 15. Quy trình đánh giá lại ranh giới transaction

Khi một luồng reactive có tác vụ blocking, hãy trả lời các câu hỏi sau theo thứ tự:

1. Lời gọi đó có thực sự blocking không, hay đã có API reactive/asynchronous thay thế?
2. Có thể loại bỏ thư viện cũ hoặc chuyển sang client non-blocking không?
3. Nếu không thể thay thế, lời gọi có được bọc bằng Mono.fromCallable hoặc Mono.fromRunnable không?
4. subscribeOn(Schedulers.boundedElastic()) có được đặt trên đúng publisher nguồn không?
5. Có giới hạn concurrency và timeout ở client blocking không?
6. Blocking call có cần dữ liệu database trước đó không?
7. Transaction có đang mở trong lúc chờ lời gọi ngoài không?
8. Những thao tác database nào thực sự cần cùng commit/rollback?
9. Có thể kết thúc transaction đọc trước, gọi blocking, rồi mở transaction ghi ngắn sau không?
10. Nếu hệ thống ngoài thực hiện side effect, có cần idempotency key, outbox hoặc saga không?
11. Nếu có JDBC legacy, nó dùng transaction manager/connection riêng hay không?
12. Có bảo đảm lỗi, timeout và cancellation không làm rò rỉ connection hoặc lặp side effect không?
13. Có theo dõi scheduler, pool và transaction duration để xác nhận thiết kế không?

Một transaction nên bắt đầu gần thời điểm thực hiện các thao tác database cần nguyên tử và kết thúc ngay sau khi chúng hoàn tất. Không giữ transaction chỉ để bao bọc toàn bộ vòng đời request nếu trong đó có nhiều bước không thuộc cùng một transaction database.

## 16. Bài tập tự kiểm tra

### Bài 1: Cô lập lời gọi blocking

Một SDK cũ có phương thức fetchDocument(Long id) trả về Document và thực hiện HTTP đồng bộ. Hãy viết publisher phù hợp.

Gợi ý:

~~~java
Mono<Document> document =
    Mono.fromCallable(() -> legacySdk.fetchDocument(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

### Bài 2: Phương thức không trả kết quả

Một thư viện ghi file bằng phương thức void exportReport(). Hãy bọc nó trong publisher.

Gợi ý:

~~~java
Mono<Void> export =
    Mono.fromRunnable(() -> legacyExporter.exportReport())
        .subscribeOn(Schedulers.boundedElastic());
~~~

### Bài 3: Phân biệt subscribeOn và publishOn

Vì sao Mono.fromCallable(blockingCall).publishOn(boundedElastic()) không phải mẫu phù hợp để bảo đảm Callable chạy trên boundedElastic?

Gợi ý: publishOn điều khiển việc xử lý tín hiệu downstream từ vị trí đó; subscribeOn đặt subscription của nguồn lên scheduler. Dùng subscribeOn trên publisher Callable.

### Bài 4: Đánh giá transaction

Một phương thức @Transactional đọc order, gọi payment gateway blocking trong 8 giây rồi cập nhật order. Việc thêm subscribeOn(boundedElastic) đã giải quyết hết vấn đề chưa?

Gợi ý: Chưa. Event-loop được giải phóng nhưng transaction có thể vẫn giữ connection trong 8 giây. Cân nhắc gọi gateway ngoài transaction, sau đó mở transaction ngắn để cập nhật trạng thái và kiểm tra version.

### Bài 5: JDBC và R2DBC

Một service reactive có @Transactional dùng R2DBC repository và JdbcTemplate. Có thể giả định cả hai thao tác rollback cùng nhau không?

Gợi ý: Không. JDBC và R2DBC thường dùng connection/transaction manager riêng. Cần thiết kế phối hợp rõ ràng, không giả định có transaction chung.

### Bài 6: Timeout của blocking call

Publisher được timeout sau 3 giây nhưng SDK blocking vẫn chờ socket 30 giây. Vì sao worker boundedElastic có thể tiếp tục bị chiếm?

Gợi ý: Cancellation không bảo đảm interrupt được lời gọi blocking. Cần đặt timeout ở chính SDK/client và kiểm tra khả năng cancel.

### Bài 7: Dùng outbox

Một thao tác cập nhật order phải phát message sau khi commit. Vì sao outbox hữu ích?

Gợi ý: Ghi order và outbox event trong cùng transaction. Worker gửi message sau commit và có thể retry bằng idempotency key nếu broker hoặc worker gặp lỗi.

## 17. Ghi nhớ

- R2DBC và Reactor không làm một thư viện blocking trở thành non-blocking.
- Dùng Mono.fromCallable() cho lời gọi blocking có kết quả và Mono.fromRunnable() cho hành động không trả kết quả.
- Đặt subscribeOn(Schedulers.boundedElastic()) trên publisher nguồn để cô lập blocking call.
- Không dùng Mono.just(blockingCall()), không gọi blocking trực tiếp trong map, và không dùng block() để lồng reactive publisher.
- boundedElastic có giới hạn worker và hàng đợi; cần timeout ở client và giới hạn concurrency.
- Chỉ cô lập đoạn blocking. Các thao tác repository R2DBC vẫn nên được kết hợp reactive bình thường.
- Đổi scheduler không tự giải phóng connection hoặc kết thúc transaction đang hoạt động.
- Không giữ transaction R2DBC trong lúc chờ I/O blocking ngoài database nếu nghiệp vụ không thực sự cần điều đó.
- JDBC blocking thường dùng transaction manager và connection riêng; không tự tham gia R2DBC transaction.
- Transaction chỉ bao quanh các thao tác database cần tính nguyên tử.
- Khi phối hợp database với side effect ngoài, cân nhắc idempotency, transactional outbox hoặc saga.
- Reactor Context có thể đi qua scheduler trong pipeline; subscription thủ công hoặc thread/executor tự tạo có thể làm mất ngữ cảnh.
- Timeout reactive không bảo đảm tác vụ blocking dừng ngay; cần cấu hình timeout của thư viện.
- Theo dõi thời gian transaction, connection pool và boundedElastic để phát hiện tài nguyên bị giữ lâu.

Khi gặp một tác vụ blocking không thể thay thế, hãy cô lập đúng lời gọi bằng boundedElastic rồi xem lại transaction đang bao quanh nó. Giữ transaction R2DBC ngắn và chỉ bao gồm các thao tác database cần cùng commit hoặc rollback. Với side effect ngoài database, dùng cơ chế phối hợp phù hợp thay vì kỳ vọng một transaction R2DBC có thể kiểm soát mọi hệ thống.

