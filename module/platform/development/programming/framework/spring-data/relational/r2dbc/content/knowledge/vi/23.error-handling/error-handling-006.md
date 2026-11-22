# Đặt retry đúng phạm vi để tạo giao dịch mới khi cần

Trong ứng dụng Spring Data R2DBC, một nghiệp vụ thường gồm nhiều thao tác database nằm trong cùng reactive transaction. Khi transaction thất bại do deadlock, serialization conflict hoặc lỗi tài nguyên tạm thời, ứng dụng đôi khi cần chạy lại toàn bộ nghiệp vụ. Điều quan trọng là **retry phải nằm bên ngoài ranh giới transaction** nếu mỗi lần thử cần một transaction mới.

Reactor retry hoạt động bằng cách subscribe lại publisher nguồn. Vì vậy, vị trí của `retryWhen` so với `TransactionalOperator.transactional(...)` quyết định publisher nào được subscribe lại và transaction có được tạo lại hay không. Retry bên trong transaction có thể chạy lại câu lệnh trên chính transaction đã lỗi hoặc đã bị đánh dấu rollback-only. Retry bên ngoài transaction cho phép lần thử trước rollback xong rồi lần subscribe tiếp theo mở một transaction mới.

## 1. Retry trong reactive pipeline hoạt động thế nào?

Các toán tử retry của Reactor không “chạy tiếp từ dòng bị lỗi”. Khi upstream phát lỗi và chính sách retry cho phép thử lại, Reactor subscribe lại publisher nguồn:

~~~java
Mono<Result> result = operation()
        .retryWhen(Retry.max(3));
~~~

Publisher `operation()` được subscribe lại khi có lỗi được chính sách chấp nhận. Nếu có side effect trong quá trình tạo publisher thay vì trong quá trình subscribe, side effect đó có thể không chạy lại đúng cách. Vì vậy, các thao tác cần tạo lại cho mỗi lần thử nên được đặt trong `Mono.defer` hoặc `Flux.defer`.

Ví dụ:

~~~java
Mono<Result> operation = Mono.defer(() -> callDatabase());
~~~

Mỗi subscription gọi lại supplier và tạo publisher cho lần thực thi đó. Với Spring Data R2DBC, repository publisher thường lazy, nhưng `defer` vẫn hữu ích khi việc dựng command, đọc clock, tạo object hoặc chọn tham số cần diễn ra lại theo từng attempt.

## 2. Vì sao transaction lỗi thường không thể tiếp tục dùng?

Một transaction database có trạng thái và vòng đời riêng. Khi gặp lỗi như deadlock hoặc serialization failure, database có thể hủy hoặc đánh dấu transaction hiện tại phải rollback. Một số database, chẳng hạn PostgreSQL, chuyển transaction sang trạng thái aborted sau một lỗi statement; các câu lệnh tiếp theo trong transaction đó sẽ tiếp tục thất bại cho đến khi rollback.

Do đó, retry riêng câu lệnh lỗi trong cùng transaction thường không giải quyết được vấn đề. Muốn thử lại nghiệp vụ sau một lỗi transaction, cần:

1. Để transaction hiện tại nhận lỗi.
2. Rollback transaction đó và giải phóng tài nguyên.
3. Bắt đầu transaction mới.
4. Chạy lại toàn bộ đơn vị công việc cần nhất quán.

Điều này đặc biệt quan trọng với lỗi serialization và deadlock: database thường yêu cầu ứng dụng chạy lại toàn bộ transaction, vì kết quả đọc trước đó có thể không còn hợp lệ.

## 3. Đặt retry bên ngoài TransactionalOperator

Đây là cách phổ biến khi dùng `TransactionalOperator`:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    Mono<Order> oneAttempt = transactionalOperator.transactional(
            Mono.defer(() -> createOrderWork(command))
    );

    return oneAttempt.retryWhen(retryPolicy);
}

private Mono<Order> createOrderWork(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(saved ->
                    orderLineRepository.saveAll(
                            toLines(saved.id(), command.items())
                    ).thenReturn(saved)
            )
            .flatMap(saved ->
                    auditRepository.save(toAudit(saved.id()))
                            .thenReturn(saved)
            );
}
~~~

Thứ tự ở đây là:

1. `transactional(...)` tạo publisher đại diện cho một lần thực hiện transaction.
2. `retryWhen(...)` bao publisher transaction đó.
3. Nếu một attempt phát lỗi retryable, transaction operator xử lý rollback và kết thúc attempt.
4. Retry subscribe lại publisher transaction.
5. Subscription mới bắt đầu một transaction mới rồi chạy lại `createOrderWork`.

Vì retry ở bên ngoài transaction publisher, lần thử mới có cơ hội nhận một connection/transaction mới từ cùng transaction manager. Không phải chỉ câu lệnh cuối cùng được thử lại; toàn bộ `createOrderWork` được chạy lại để giữ tính nhất quán của nghiệp vụ.

## 4. Đặt retry bên trong transaction có vấn đề gì?

Ví dụ dễ gây nhầm:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    Mono<Order> work = Mono.defer(() -> createOrderWork(command))
            .retryWhen(retryPolicy);

    return transactionalOperator.transactional(work);
}
~~~

Trong cấu trúc này, transaction operator bao toàn bộ publisher đã có retry. Khi `work` phát lỗi, `retryWhen` ở bên trong bắt lỗi và subscribe lại `work` trước khi lỗi được truyền ra ngoài transaction operator. Các lần thử có thể vẫn nằm trong cùng transaction context và dùng cùng transaction.

Nếu database đã đánh dấu transaction rollback-only hoặc ở trạng thái aborted, lần thử tiếp theo vẫn chạy trên transaction không còn dùng được. Khi publisher cuối cùng hoàn tất, transaction cũng có thể bị rollback hoặc báo lỗi commit.

| Cấu trúc | Retry tác động lên | Kết quả về transaction |
| --- | --- | --- |
| `transactional(work).retryWhen(retry)` | Publisher transaction | Mỗi subscription mới có thể tạo transaction mới |
| `transactional(work.retryWhen(retry))` | Publisher công việc bên trong transaction | Các lần thử có thể dùng lại transaction hiện tại |

Khi cần transaction mới cho từng attempt, hãy đặt retry ở ngoài `transactional(...)`.

## 5. Ví dụ chính sách retry có backoff và giới hạn

Không nên retry vô hạn hoặc ngay lập tức. Dùng `Retry.backoff` để giới hạn số lần thử và tăng dần thời gian chờ:

~~~java
private Retry retryPolicy() {
    return Retry.backoff(3, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.5)
            .filter(this::isRetryable)
            .doBeforeRetry(signal ->
                    log.warn(
                            "Retrying transaction, attempt={}, cause={}",
                            signal.totalRetries() + 1,
                            signal.failure().toString()
                    )
            )
            .onRetryExhaustedThrow((spec, signal) ->
                    signal.failure()
            );
}
~~~

Trong Reactor, tham số `maxAttempts` của `Retry.backoff(maxAttempts, ...)` là số lần retry tối đa sau lần thực thi đầu tiên. Ví dụ `3` có thể tạo tối đa một lần chạy ban đầu cộng ba lần thử lại. Nếu cần giới hạn tổng số attempt, hãy tính rõ số lần chạy ban đầu cộng số lần retry.

Backoff giảm áp lực lên database khi nhiều request cùng gặp lỗi. Jitter thêm độ ngẫu nhiên để các request không đồng loạt retry cùng thời điểm. `maxBackoff` giới hạn thời gian chờ lớn nhất.

## 6. Chỉ retry lỗi có khả năng tạm thời

Không phải lỗi nào cũng tự hết khi chạy lại. Phân loại lỗi trước khi cấu hình retry:

| Nhóm lỗi | Thường nên retry? | Lý do |
| --- | --- | --- |
| Deadlock victim | Có thể | Transaction bị hủy do cạnh tranh; attempt mới có thể thành công |
| Serialization failure | Có thể | Database yêu cầu chạy lại transaction với snapshot mới |
| Lỗi tài nguyên/kết nối tạm thời trước khi commit | Có thể | Tài nguyên có thể phục hồi |
| Lock unavailable với NOWAIT | Tùy nghiệp vụ | Retry có backoff nếu việc chờ là mong muốn |
| Unique constraint violation | Thường không | Dữ liệu đầu vào hoặc trạng thái đã xung đột; retry y nguyên thường thất bại tiếp |
| Foreign key violation | Không | Thường là lỗi dữ liệu hoặc thứ tự nghiệp vụ |
| SQL syntax/column mapping error | Không | Chạy lại không sửa được câu SQL |
| Authentication/permission error | Không | Cần sửa cấu hình hoặc quyền |
| Validation error | Không | Cần sửa dữ liệu đầu vào |
| Query canceled hoặc client cancellation | Không mặc định | Người gọi đã hủy hoặc query bị hủy; không nên tự khởi động lại vô điều kiện |

Spring có thể dịch lỗi R2DBC thành các kiểu `DataAccessException`; driver cũng có hệ exception riêng. Predicate retry nên dựa trên loại lỗi đã được dịch, SQLSTATE/vendor code hoặc classifier của ứng dụng. Không dựa vào chuỗi message vì message có thể thay đổi theo driver và phiên bản.

Ví dụ predicate khung:

~~~java
private boolean isRetryable(Throwable error) {
    if (error instanceof TransientDataAccessException) {
        return true;
    }

    // Bổ sung phân loại theo SQLSTATE hoặc mã lỗi
    // của database/driver mà ứng dụng đang sử dụng.
    return isKnownTransientDatabaseFailure(error);
}
~~~

`isKnownTransientDatabaseFailure` là hàm phân loại của ứng dụng, không phải API có sẵn của Spring. Hãy chỉ đưa vào đây các lỗi đã xác nhận có thể phục hồi và an toàn để chạy lại.

## 7. SQLSTATE và lỗi transaction theo database

Với PostgreSQL, một số SQLSTATE thường được quan tâm khi thiết kế retry:

| SQLSTATE | Tên lỗi | Cách xử lý thường gặp |
| --- | --- | --- |
| `40001` | serialization_failure | Rollback và retry toàn bộ transaction |
| `40P01` | deadlock_detected | Rollback và cân nhắc retry toàn bộ transaction |
| `55P03` | lock_not_available | Chỉ retry nếu chính sách NOWAIT/lock của nghiệp vụ cho phép |
| `57014` | query_canceled | Không retry tự động nếu do timeout hoặc cancellation của caller |

Đây là mã PostgreSQL; database khác có thể dùng mã lỗi và semantics khác. Một số lỗi kết nối thuộc nhóm SQLSTATE `08xxx`, nhưng lỗi kết nối xảy ra quanh thời điểm commit có thể tạo ra kết quả không xác định: server có thể đã commit nhưng client mất phản hồi.

Khi driver hoặc Spring chuyển đổi exception, SQLSTATE có thể nằm trong exception gốc hoặc metadata của driver. Hãy kiểm tra exception chain và tài liệu driver thay vì giả định mọi exception đều giữ nguyên kiểu hoặc trường dữ liệu.

## 8. Tạo mới transaction với TransactionalOperator và Retry

Một ví dụ đầy đủ:

~~~java
@Service
public class PaymentService {

    private final TransactionalOperator transactionalOperator;
    private final PaymentRepository paymentRepository;
    private final LedgerRepository ledgerRepository;

    public PaymentService(
            TransactionalOperator transactionalOperator,
            PaymentRepository paymentRepository,
            LedgerRepository ledgerRepository) {
        this.transactionalOperator = transactionalOperator;
        this.paymentRepository = paymentRepository;
        this.ledgerRepository = ledgerRepository;
    }

    public Mono<Payment> process(PaymentCommand command) {
        Retry retry = Retry.backoff(3, Duration.ofMillis(150))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(this::isRetryable)
                .onRetryExhaustedThrow((spec, signal) ->
                        signal.failure()
                );

        Mono<Payment> oneTransaction = transactionalOperator.transactional(
                Mono.defer(() ->
                        paymentRepository.save(toPayment(command))
                                .flatMap(payment ->
                                        ledgerRepository.save(
                                                toLedgerEntry(payment)
                                        ).thenReturn(payment)
                                )
                )
        );

        return oneTransaction.retryWhen(retry);
    }

    private boolean isRetryable(Throwable error) {
        return error instanceof TransientDataAccessException;
    }
}
~~~

Mỗi lần subscribe lại `oneTransaction`, transaction operator được kích hoạt lại. Nếu lỗi là deadlock hoặc serialization conflict đã được phân loại, attempt trước được rollback trước khi retry bắt đầu.

Ví dụ predicate ở đây chỉ mang tính minh họa. Trong ứng dụng thật, cần xác nhận exception translation của Spring Data và driver, đồng thời bổ sung mã lỗi cụ thể của database. Không nên coi mọi `TransientDataAccessException` đều an toàn để retry nếu thao tác có side effect không idempotent hoặc kết quả commit không xác định.

## 9. Dùng @Transactional: đặt retry ở service bên ngoài

Với declarative transaction, có thể tách phần thực hiện một attempt vào một bean riêng có `@Transactional`, còn bean điều phối đặt retry bên ngoài:

~~~java
@Service
public class OrderTransaction {

    private final OrderRepository orderRepository;
    private final OrderLineRepository lineRepository;

    public OrderTransaction(
            OrderRepository orderRepository,
            OrderLineRepository lineRepository) {
        this.orderRepository = orderRepository;
        this.lineRepository = lineRepository;
    }

    @Transactional
    public Mono<Order> executeOnce(CreateOrderCommand command) {
        return orderRepository.save(toOrder(command))
                .flatMap(order ->
                        lineRepository.saveAll(toLines(order.id(), command))
                                .thenReturn(order)
                );
    }
}
~~~

Facade:

~~~java
@Service
public class OrderFacade {

    private final OrderTransaction orderTransaction;
    private final Retry retryPolicy;

    public OrderFacade(
            OrderTransaction orderTransaction,
            Retry retryPolicy) {
        this.orderTransaction = orderTransaction;
        this.retryPolicy = retryPolicy;
    }

    public Mono<Order> create(CreateOrderCommand command) {
        return orderTransaction.executeOnce(command)
                .retryWhen(retryPolicy);
    }
}
~~~

Lời gọi qua bean Spring khác đi qua proxy transaction. Publisher trả về từ `executeOnce` được bọc trong transaction; retry ở facade subscribe lại publisher đó. Mỗi subscription mới có thể mở một transaction mới.

Tránh đặt `@Transactional` trên chính facade rồi đặt `retryWhen` trong method đó nếu mục tiêu là tạo transaction mới mỗi attempt. Khi đó retry nằm bên trong publisher thuộc transaction của facade.

Ngoài ra, self-invocation (một method trong cùng class gọi method `@Transactional` khác bằng `this`) thường không đi qua proxy và có thể bỏ qua annotation. Tách bean hoặc dùng `TransactionalOperator` giúp ranh giới dễ thấy hơn.

## 10. Retry toàn bộ đơn vị nghiệp vụ, không chỉ câu lệnh cuối

Giả sử một transaction:

1. Đọc số dư tài khoản.
2. Kiểm tra giới hạn.
3. Ghi khoản trừ.
4. Ghi khoản cộng.
5. Ghi audit.

Nếu lỗi serialization xảy ra ở bước 4, dữ liệu đọc ở bước 1 có thể đã cũ. Retry riêng bước 4 sẽ dùng lại quyết định nghiệp vụ dựa trên dữ liệu cũ. Cách đúng thường là rollback và chạy lại toàn bộ quy trình từ bước 1 trong transaction mới.

Ví dụ phạm vi retry:

~~~java
Mono<TransferResult> oneAttempt =
        transactionalOperator.transactional(
                Mono.defer(() -> readValidateAndTransfer(command))
        );

return oneAttempt.retryWhen(retryPolicy);
~~~

Không đặt retry chỉ quanh `ledgerRepository.save(...)` nếu kết quả của thao tác đó phụ thuộc vào các giá trị đã đọc trước trong transaction bị lỗi.

## 11. Idempotency trước khi retry thao tác ghi

Retry có thể khiến một thao tác được thực hiện nhiều lần. Nguy hiểm nhất là khi client mất kết nối sau khi server đã commit nhưng trước khi client nhận được phản hồi:

1. Database commit thành công.
2. Kết nối bị ngắt trước khi ứng dụng nhận kết quả.
3. Ứng dụng thấy lỗi kết nối và không biết commit đã xảy ra hay chưa.
4. Retry tạo thêm một bản ghi hoặc thực hiện side effect lần thứ hai.

Đây là kết quả commit không xác định (ambiguous outcome). Không thể giải quyết bằng cách chỉ tăng số lần retry.

Với thao tác ghi quan trọng, thiết kế idempotency:

- Nhận một idempotency key ổn định từ request.
- Lưu key với unique constraint trong cùng database.
- Gắn kết quả nghiệp vụ với key đó.
- Khi request được gửi lại, đọc kết quả đã lưu thay vì tạo tác động lần nữa.
- Đảm bảo các bảng ghi nhận idempotency và dữ liệu nghiệp vụ được cập nhật trong cùng transaction.

Ví dụ schema:

~~~sql
CREATE TABLE payment_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    payment_id BIGINT NOT NULL,
    result_status VARCHAR(30) NOT NULL
);
~~~

Một request retry với cùng key có thể tìm thấy kết quả đã được xử lý. Cách xử lý insert trùng cần được thiết kế theo database và nghiệp vụ, ví dụ truy vấn kết quả hiện có hoặc dùng cú pháp upsert phù hợp.

## 12. Retry và unique constraint

Unique constraint violation thường không phải lỗi tạm thời. Nếu retry cùng một câu INSERT với cùng dữ liệu, lần thử sau thường vẫn vi phạm constraint.

Tuy nhiên, unique constraint có thể là một phần của chiến lược idempotency: khi insert key đã tồn tại, ứng dụng truy vấn bản ghi hiện có và trả kết quả cũ. Đây là xử lý xung đột có chủ đích, không phải retry mù.

Phân biệt:

- **Retry:** chạy lại công việc sau lỗi được xác định là tạm thời.
- **Conflict recovery:** nhận biết một bản ghi đã được tạo và đọc kết quả hiện có.
- **Upsert:** dùng semantics của database để insert hoặc cập nhật theo constraint.

Không gộp ba cơ chế thành một `retryWhen(Retry.max(...))` chung.

## 13. Backoff, jitter và deadline tổng thể

Retry phải nằm trong ngân sách thời gian của request hoặc job. Nếu mỗi attempt mất 3 giây, có 3 lần retry và backoff tổng cộng 2 giây, tổng thời gian có thể vượt quá deadline HTTP.

Một chính sách nên xác định:

- Số lần retry tối đa.
- Backoff ban đầu và mức tối đa.
- Jitter.
- Các lỗi được phép retry.
- Deadline tổng thể.
- Hành vi khi hết retry.

Ví dụ:

~~~java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(1))
        .jitter(0.5)
        .filter(this::isRetryable)
        .doBeforeRetry(signal ->
                log.warn(
                        "Retry attempt {} after {}",
                        signal.totalRetries() + 1,
                        signal.failure().getClass().getSimpleName()
                )
        );

return oneTransaction
        .retryWhen(retryPolicy)
        .timeout(Duration.ofSeconds(8));
~~~

Timeout ngoài cùng giới hạn thời gian của toàn bộ quá trình retry. Khi timeout xảy ra, subscription hiện tại bị cancel; transaction đang mở cần được transaction manager xử lý theo cancellation. Không retry timeout một cách tự động trừ khi chính sách rõ ràng cho phép và thao tác an toàn.

Nếu cần phân biệt timeout của từng attempt và deadline tổng, có thể đặt timeout ở hai vị trí khác nhau nhưng phải hiểu publisher nào bị hủy và transaction nào đang mở. Không để các timeout chồng lấn mà không có chủ đích.

## 14. Retry khi gặp deadlock hoặc serialization failure

Deadlock và serialization failure thường yêu cầu chạy lại toàn bộ transaction. Một mẫu tổng quát:

~~~java
Mono<Result> oneAttempt = transactionalOperator.transactional(
        Mono.defer(() -> executeBusinessUnit(command))
);

Retry retry = Retry.backoff(3, Duration.ofMillis(50))
        .maxBackoff(Duration.ofSeconds(1))
        .filter(this::isDeadlockOrSerializationFailure);

return oneAttempt.retryWhen(retry);
~~~

Mỗi attempt có transaction riêng. Database có cơ hội chọn một thứ tự thực thi khác hoặc snapshot mới ở lần thử tiếp theo.

Không retry quá nhiều khi hệ thống đang có tranh chấp cao. Nếu mọi request cùng retry liên tục, tải tăng và tạo thêm deadlock. Dùng backoff, jitter, giới hạn concurrency và tối ưu thứ tự truy cập hàng.

## 15. Không retry cancellation như lỗi tạm thời thông thường

Cancellation thường biểu thị subscriber không còn muốn kết quả. Reactor retry xử lý lỗi, không phải tín hiệu cancellation thông thường. Không nên biến cancellation thành lỗi có thể retry bằng cách tùy tiện map mọi kết cục thành exception.

Timeout có thể hủy publisher nguồn rồi phát một lỗi timeout downstream. Nếu predicate cho phép retry timeout, cần chắc chắn:

- Transaction attempt cũ đã được rollback/cleanup trước khi thử lại.
- Câu lệnh có thể dừng hoặc kết quả không gây side effect trùng.
- Deadline tổng còn đủ thời gian.
- Client thực sự vẫn cần kết quả.

Nếu client HTTP đã đóng kết nối, tiếp tục chạy lại một nghiệp vụ ghi có thể lãng phí tài nguyên và gây tác động ngoài ý muốn. Đối với job nền, cancellation có thể có ý nghĩa khác và cần quy tắc tiếp tục riêng.

## 16. Tránh retry lồng nhau ở nhiều tầng

Giả sử tầng repository retry 3 lần và tầng service cũng retry 3 lần. Một request có thể tạo tới 4 × 4 = 16 lần thực thi tùy cách tính attempt và vị trí operator.

Retry lồng nhau làm tăng:

- Tổng số truy vấn và connection được sử dụng.
- Thời gian request.
- Khó khăn khi đọc log và xác định số lần thử.
- Nguy cơ tạo tác động trùng.
- Áp lực lên database đang gặp sự cố.

Nên chọn một tầng sở hữu chính sách retry cho một đơn vị công việc. Với lỗi transaction như deadlock/serialization, tầng service/use-case thường phù hợp vì nó biết toàn bộ transaction cần chạy lại.

Nếu một client hoặc driver đã có retry nội bộ, cần tính nó vào ngân sách retry tổng. Tránh để mỗi tầng tự retry độc lập mà không có giới hạn chung.

## 17. Logging và quan sát retry

Mỗi attempt nên có thông tin đủ để phân tích:

- Correlation ID hoặc request/job ID.
- Tên nghiệp vụ và transaction.
- Số lần retry hiện tại.
- Loại exception và SQLSTATE/vendor code nếu có.
- Thời gian thực thi và backoff.
- Kết quả cuối cùng: success, exhausted, timeout hoặc cancellation.

Ví dụ:

~~~java
.doBeforeRetry(signal ->
        log.warn(
                "Retrying createOrder, attempt={}, exception={}",
                signal.totalRetries() + 1,
                signal.failure().getClass().getName()
        )
)
~~~

Không ghi toàn bộ payload thanh toán, thông tin cá nhân hoặc dữ liệu nhạy cảm vào log. Metric retry nên có nhãn giới hạn cardinality; không dùng ID người dùng hoặc request làm label có thể tạo quá nhiều chuỗi metric.

## 18. Kiểm thử để xác nhận mỗi lần retry có transaction mới

Unit test với publisher giả có thể xác nhận số lần subscribe, nhưng không chứng minh transaction manager đã tạo transaction mới. Cần integration test trên database:

1. Tạo dữ liệu ban đầu.
2. Trong attempt đầu, thực hiện một thay đổi rồi phát lỗi transaction retryable.
3. Xác nhận attempt đầu rollback.
4. Cho attempt tiếp theo chạy và hoàn tất.
5. Xác nhận dữ liệu cuối chỉ phản ánh một lần thực thi thành công.
6. Ghi nhận transaction/connection theo cách phù hợp để chứng minh attempt mới dùng transaction mới.

Có thể dùng `AtomicInteger` để giả lập lỗi lần đầu:

~~~java
AtomicInteger attempts = new AtomicInteger();

Mono<Result> oneTransaction = transactionalOperator.transactional(
        Mono.defer(() -> {
            int attempt = attempts.incrementAndGet();
            return repository.save(createRow(attempt))
                    .flatMap(saved -> attempt == 1
                            ? Mono.error(new SimulatedTransientFailure())
                            : Mono.just(toResult(saved))
                    );
        })
);

return oneTransaction.retryWhen(Retry.max(1));
~~~

Đây là test minh họa cơ chế subscribe lại, không mô phỏng đầy đủ deadlock/serialization của database. Để xác nhận rollback thật, hãy truy vấn dữ liệu sau mỗi kịch bản hoặc dùng lỗi database thực tế có thể tái tạo.

Các trường hợp nên kiểm thử:

- Lỗi retryable lần đầu rồi thành công.
- Lỗi không retryable và chỉ có một attempt.
- Hết số lần retry.
- Transaction rollback trước khi attempt mới bắt đầu.
- Lỗi ở bước cuối của một workflow nhiều câu lệnh.
- Timeout/cancellation khi một attempt đang chạy.
- Mất kết nối quanh thời điểm commit và hành vi idempotency.
- Hai request đồng thời gây deadlock hoặc serialization conflict.

## 19. Các lỗi thường gặp

1. **Đặt retry bên trong transaction.** Các attempt có thể dùng cùng transaction đã lỗi hoặc rollback-only.
2. **Chỉ retry câu lệnh cuối.** Các giá trị đọc và quyết định nghiệp vụ trước đó có thể đã cũ.
3. **Retry mọi exception.** Validation, SQL syntax, unique và foreign key thường không tự hết khi chạy lại.
4. **Retry vô hạn hoặc không backoff.** Làm tăng tải lên database đang gặp sự cố.
5. **Không có jitter.** Nhiều request có thể retry đồng thời và tạo retry storm.
6. **Không giới hạn deadline tổng.** Tổng thời gian có thể vượt quá timeout của request.
7. **Retry thao tác ghi không idempotent.** Mất phản hồi sau commit có thể khiến nghiệp vụ chạy hai lần.
8. **Coi lỗi kết nối luôn đồng nghĩa rollback.** Client có thể không biết server đã commit hay chưa.
9. **Nuốt lỗi bên trong transaction rồi retry ở ngoài.** Khi lỗi đã được phục hồi thành complete, retry bên ngoài không còn thấy lỗi để chạy lại.
10. **Dùng @Transactional và retry trong cùng method không đúng phạm vi.** Proxy có thể bao publisher bên ngoài retry, khiến các lần thử không có transaction mới.
11. **Self-invocation method @Transactional.** Lời gọi nội bộ có thể bỏ qua Spring proxy.
12. **Retry lồng ở repository, service và client.** Số lần thực thi thực tế tăng theo cấp số nhân.
13. **Retry cancellation.** Caller có thể đã bỏ yêu cầu; không tự khởi động lại vô điều kiện.
14. **Không log attempt và nguyên nhân.** Khó phân biệt lỗi gốc với lỗi sau retry.

## Quy tắc lựa chọn nhanh

- Khi lỗi transaction cần chạy lại toàn bộ nghiệp vụ, đặt retry **bên ngoài** `TransactionalOperator.transactional(...)`.
- Dùng `Mono.defer` hoặc `Flux.defer` để dựng lại công việc cho mỗi attempt khi cần.
- Với `@Transactional`, đặt retry ở caller/bean bên ngoài transaction proxy để mỗi subscription đi qua một transaction boundary mới.
- Retry có giới hạn, backoff, jitter và predicate chỉ nhận lỗi tạm thời đã xác định.
- Chạy lại toàn bộ transaction khi dữ liệu đọc trước đó có thể đã lỗi thời.
- Thiết kế idempotency cho thao tác ghi và xử lý kết quả commit không xác định.
- Không retry validation, SQL syntax, permission hoặc constraint violation theo cách chung chung.
- Phối hợp retry với deadline, cancellation và connection pool.
- Tránh retry lồng nhau ở nhiều tầng; chọn một nơi sở hữu chính sách.
- Kiểm thử rollback và transaction mới bằng database/driver mục tiêu.

Retry chỉ an toàn khi đặt đúng ranh giới và biết rõ loại lỗi đang xử lý. Trong Spring Data R2DBC, nếu cần một transaction mới cho mỗi lần thử, hãy để transaction publisher nằm bên trong retry publisher: `transactional(work).retryWhen(policy)`. Mỗi lần subscribe lại sẽ mở một attempt transaction mới sau khi attempt trước kết thúc. Kết hợp cách đặt operator này với retry có giới hạn, phân loại lỗi, backoff, idempotency và integration test giúp xử lý deadlock hoặc serialization conflict mà không tiếp tục dùng một transaction đã hỏng hoặc tạo tác động ghi trùng.
