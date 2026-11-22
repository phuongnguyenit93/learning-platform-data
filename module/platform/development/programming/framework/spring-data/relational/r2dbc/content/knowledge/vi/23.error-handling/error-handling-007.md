# Nguy cơ ghi trùng khi mất kết nối sau khi cơ sở dữ liệu đã ghi

Một request ghi dữ liệu có thể gặp lỗi mạng ngay sau khi database đã thực hiện và commit thay đổi. Ứng dụng chỉ nhìn thấy timeout hoặc connection reset nên không biết chắc thao tác đã thành công hay chưa. Nếu tự động gửi lại câu lệnh như một thao tác mới, hệ thống có thể tạo bản ghi trùng, trừ tiền hai lần, giữ chỗ tồn kho nhiều lần hoặc phát sinh side effect lặp.

Đây là tình huống **kết quả ghi không xác định** (ambiguous write outcome). Nó khác với lỗi xảy ra chắc chắn trước khi database nhận lệnh hoặc lỗi constraint mà database trả về rõ ràng. Trong trường hợp mất xác nhận, database có thể đã commit dù client không nhận được phản hồi.

Với Spring Data R2DBC, các publisher reactive có thể được subscribe lại bởi Reactor retry, HTTP client, gateway hoặc chính người dùng. Vì vậy, mọi thao tác ghi có thể được thử lại cần có chiến lược chống trùng phù hợp. Một cách phổ biến là dùng **idempotency key** ổn định kết hợp unique constraint và lưu dấu nhận diện request trong cùng transaction với thay đổi nghiệp vụ.

## 1. Tình huống mất kết nối sau khi database đã ghi

Giả sử API tạo đơn hàng gửi câu lệnh insert tới database:

1. Ứng dụng gửi lệnh insert order.
2. Database nhận lệnh, ghi bản ghi và commit transaction.
3. Database gửi kết quả thành công về ứng dụng.
4. Kết nối mạng bị đứt trước khi ứng dụng nhận được phản hồi.
5. Publisher phía ứng dụng kết thúc bằng lỗi kết nối hoặc timeout.

Ở bước 5, ứng dụng không thể suy ra chắc chắn rằng insert đã rollback. Database có thể đã commit thành công; chỉ có thông báo xác nhận bị mất trên đường truyền.

### 1.1. Vì sao caller không thể biết kết quả chỉ từ exception?

Một exception như connection reset, timeout hoặc connection closed cho biết việc trao đổi với database không hoàn tất theo cách ứng dụng mong đợi. Nó không nhất thiết cho biết database đã rollback.

Có ba khả năng:

- **Lệnh chưa tới database:** không có thay đổi nào được thực hiện.
- **Lệnh đã chạy nhưng transaction chưa commit:** khi connection mất, database có thể rollback transaction sau khi phát hiện session kết thúc.
- **Commit đã thành công nhưng acknowledgement bị mất:** dữ liệu đã được lưu, trong khi caller nhận lỗi.

Từ phía client, hai khả năng cuối có thể trông giống nhau: publisher phát lỗi mà không có kết quả nghiệp vụ.

### 1.2. Sơ đồ tình huống

~~~text
Ứng dụng                 Database
   |                         |
   |---- INSERT order ------>|
   |                         | ghi dữ liệu
   |                         | COMMIT
   |<--- success response ---|
   X kết nối bị đứt trước khi ứng dụng nhận response
   |
   | publisher báo lỗi
   |
   |---- retry INSERT ------>| có thể tạo bản ghi thứ hai
~~~

Lỗi xuất hiện ở ranh giới giữa database commit và ứng dụng nhận acknowledgement. Đây là lý do retry một lệnh ghi cần được thiết kế khác với retry một truy vấn đọc.

## 2. Vì sao retry có thể tạo dữ liệu trùng?

Các repository method và query reactive thường trả về publisher lazy. Mỗi lần subscribe lại một publisher cold có thể thực hiện lại thao tác database.

Ví dụ:

~~~java
public Mono<Order> createOrder(CreateOrderRequest request) {
    Order order = new Order(
            null,
            request.customerId(),
            request.totalAmount()
    );

    return orderRepository.save(order)
            .retry(1);
}
~~~

Nếu lần subscribe đầu đã insert và commit nhưng phản hồi bị mất, retry có thể chạy lại insert. Nếu khóa chính được database tự sinh, lần thứ hai có thể tạo một order mới với ID khác. Database không thể biết hai lệnh đó là cùng một ý định nghiệp vụ nếu ứng dụng không cung cấp định danh chung.

### 2.1. Những nơi có thể tự gửi lại request

Việc gửi lặp không chỉ đến từ Reactor:

- Reactor retry hoặc retryWhen trong service.
- HTTP client retry khi không nhận response.
- API gateway hoặc reverse proxy retry request.
- Người dùng bấm nút gửi lại sau khi thấy timeout.
- Mobile app gửi lại request khi khôi phục mạng.
- Message broker giao lại message vì consumer chưa acknowledge.
- Job nền chạy lại sau khi process restart.

Do đó, chống trùng cần được bảo vệ ở ranh giới lưu trữ hoặc nghiệp vụ, không chỉ dựa vào một đoạn code retry trong service.

### 2.2. Không phải mọi lỗi đều có thể retry

Một số lỗi có kết quả rõ ràng:

- Validation thất bại trước khi ghi.
- Vi phạm foreign key hoặc check constraint.
- Vi phạm unique constraint của dữ liệu nghiệp vụ.
- Lỗi cú pháp SQL.
- Lỗi chuyển đổi kiểu dữ liệu.

Retry các lỗi này thường không giúp thành công. Với lỗi kết nối hoặc timeout xảy ra trong lúc ghi/commit, kết quả có thể không xác định và cần truy vấn lại bằng một định danh ổn định.

## 3. Idempotency là gì?

Một thao tác là **idempotent** nếu thực hiện lặp lại cùng một yêu cầu với cùng định danh không làm thay đổi kết quả nghiệp vụ nhiều lần so với thực hiện một lần.

Ví dụ:

- Gán trạng thái đơn hàng thành PAID có thể idempotent nếu cùng một trạng thái được ghi lặp lại không tạo thêm side effect.
- Tạo đơn hàng mới thường không idempotent vì mỗi lần insert có thể tạo một order khác.
- Tăng số dư thêm 100 không idempotent vì chạy hai lần sẽ tăng 200.
- Đặt chỗ 1 sản phẩm có thể không idempotent nếu mỗi lần gọi làm giảm tồn kho hoặc tăng số lượng reservation.

Idempotency key là một mã duy nhất đại diện cho một ý định nghiệp vụ. Client tạo key trước lần gửi đầu tiên và dùng lại chính key đó cho mọi lần retry của cùng ý định.

Ví dụ header HTTP:

~~~http
POST /orders
Idempotency-Key: 8d1c9a6e-2f50-4e54-a4b2-1a76c1c5a8d0
Content-Type: application/json
~~~

Server lưu key cùng kết quả xử lý. Nếu nhận lại request có cùng key, server tra cứu kết quả cũ và trả lại kết quả tương ứng thay vì thực hiện nghiệp vụ lần thứ hai.

### 3.1. Key phải ổn định qua các lần retry

Key cần được tạo một lần ở ranh giới request hoặc command:

~~~java
String idempotencyKey = request.idempotencyKey();

return service.createOrder(idempotencyKey, request.command());
~~~

Không tạo key mới mỗi lần publisher được subscribe. Ví dụ không nên sinh UUID bên trong một supplier bị retry:

~~~java
// Không phù hợp: mỗi subscription có thể sinh key mới.
Mono.defer(() -> service.createOrder(UUID.randomUUID().toString(), command));
~~~

Nếu key thay đổi theo mỗi lần thử, database xem các lần gửi là các thao tác độc lập và cơ chế chống trùng mất tác dụng.

### 3.2. Phạm vi của key

Không nên dùng một key trần mà không xác định phạm vi. Có thể định danh duy nhất theo tenant/client, tên thao tác/API và idempotency key do client gửi.

Một unique constraint dạng tổ hợp giúp tránh va chạm giữa các client hoặc loại thao tác:

~~~sql
UNIQUE (tenant_id, operation, idempotency_key)
~~~

Không dùng ID người dùng hoặc dữ liệu nhạy cảm làm key trực tiếp. Key nên khó đoán, có độ dài giới hạn và được kiểm tra định dạng.

## 4. Lưu idempotency key bằng unique constraint

Một cách triển khai bền vững là tạo bảng lưu dấu request. Ví dụ:

~~~sql
CREATE TABLE command_receipts (
    tenant_id BIGINT NOT NULL,
    operation VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(120) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    result_order_id BIGINT,
    completed_at TIMESTAMP,
    PRIMARY KEY (tenant_id, operation, idempotency_key)
);
~~~

Các cột có ý nghĩa:

| Cột | Mục đích |
| --- | --- |
| tenant_id | Phạm vi tenant đã xác thực |
| operation | Loại nghiệp vụ mà key đại diện |
| idempotency_key | Mã ổn định của một ý định gửi |
| request_hash | Hash của payload chuẩn hóa để phát hiện dùng lại key với nội dung khác |
| result_order_id | Tham chiếu kết quả nghiệp vụ đã tạo |
| completed_at | Thời điểm nghiệp vụ được ghi nhận hoàn tất |

Khóa chính/unique constraint là lớp bảo vệ cuối cùng khi hai request cùng key đến đồng thời. Kiểm tra kiểu SELECT trước rồi mới INSERT không đủ an toàn, vì hai request có thể cùng đọc thấy chưa có key và sau đó cùng insert.

### 4.1. Vì sao cần request hash?

Một client không nên dùng cùng key cho hai payload khác nhau. Ví dụ:

- Lần đầu key K tạo order trị giá 100.
- Lần sau key K được gửi với tổng tiền 500.

Server cần phát hiện việc tái sử dụng key sai mục đích. Nếu hash payload không khớp, trả lỗi conflict thay vì trả kết quả cũ như thể request giống nhau.

Hash cần được tính từ biểu diễn chuẩn hóa của các field có ý nghĩa nghiệp vụ. Không nên hash chuỗi JSON thô nếu thứ tự property, khoảng trắng hoặc cách serialize có thể thay đổi mà nội dung nghiệp vụ vẫn giống nhau.

### 4.2. Không chỉ lưu key trong bộ nhớ

Một map trong memory không bảo vệ được khi ứng dụng chạy nhiều instance, process restart, request được route sang instance khác hoặc cache bị xóa. Idempotency record cần nằm trong nơi lưu trữ bền vững có unique constraint.

Nếu dùng cache phân tán, vẫn cần đánh giá atomicity, persistence, eviction và hành vi khi cache mất kết nối.

## 5. Ghi receipt và dữ liệu nghiệp vụ trong cùng transaction

Điểm quan trọng nhất là idempotency receipt và thay đổi nghiệp vụ phải commit cùng nhau. Nếu receipt được ghi trong transaction riêng rồi việc tạo order thất bại, key có thể bị đánh dấu đã dùng dù order chưa tồn tại. Ngược lại, nếu order được commit nhưng receipt không được ghi, retry có thể tạo order thứ hai.

Luồng mong muốn:

1. Insert receipt với key và request hash.
2. Tạo order.
3. Lưu ID order vào receipt và đánh dấu hoàn tất.
4. Commit cả hai thay đổi trong cùng transaction.

Nếu bất kỳ bước nào thất bại trước commit, cả receipt và order đều rollback. Nếu commit thành công nhưng acknowledgement mất, retry cùng key sẽ gặp unique constraint và có thể tìm lại kết quả đã lưu.

### 5.1. Repository cho receipt

Một interface minh họa:

~~~java
public interface CommandReceiptRepository {

    Mono<Integer> insertReceipt(
            Long tenantId,
            String operation,
            String key,
            String requestHash);

    Mono<Integer> completeReceipt(
            Long tenantId,
            String operation,
            String key,
            Long orderId);

    Mono<CommandReceipt> findReceipt(
            Long tenantId,
            String operation,
            String key);
}
~~~

Implementation có thể dùng repository custom, DatabaseClient hoặc R2dbcEntityTemplate. Lệnh insert receipt phải dựa vào unique constraint ở database; không thay thế bằng chuỗi SELECT rồi INSERT không có bảo vệ cạnh tranh.

### 5.2. Phần xử lý nằm trong transaction

~~~java
private Mono<OrderResult> createOrderOnce(
        Long tenantId,
        String key,
        String requestHash,
        CreateOrderCommand command) {

    return receiptRepository.insertReceipt(
                    tenantId, "CREATE_ORDER", key, requestHash)
            .then(orderRepository.save(
                    Order.newOrder(command.customerId(), command.totalAmount())))
            .flatMap(saved -> receiptRepository.completeReceipt(
                            tenantId, "CREATE_ORDER", key, saved.getId())
                    .thenReturn(OrderResult.from(saved)));
}
~~~

Phương thức này chỉ mô tả công việc cần nằm trong transaction. Khi triển khai, transaction boundary phải bao quanh toàn bộ chuỗi publisher. Nếu insert receipt bị trùng, lỗi phải làm transaction hiện tại kết thúc/rollback trước khi đọc receipt cũ.

### 5.3. Bao transaction bằng TransactionalOperator

~~~java
public Mono<OrderResult> createOrder(
        Long tenantId,
        String key,
        String requestHash,
        CreateOrderCommand command) {

    Mono<OrderResult> oneAttempt = transactionalOperator.transactional(
            createOrderOnce(tenantId, key, requestHash, command));

    return oneAttempt;
}
~~~

Trong ứng dụng Spring, TransactionalOperator phải được cấu hình với R2dbcTransactionManager dùng cùng ConnectionFactory với các repository. Có thể dùng reactive @Transactional ở một service method thay thế, nhưng cần bảo đảm lời gọi đi qua transaction proxy và toàn bộ thao tác nằm trong publisher chain.

## 6. Xử lý request lặp và trả lại kết quả cũ

Khi receipt đã tồn tại, server cần:

1. Đọc receipt bằng tenant, operation và key.
2. So sánh request hash.
3. Nếu hash khác, trả conflict vì key đã được dùng cho payload khác.
4. Nếu hash giống và receipt hoàn tất, tải kết quả nghiệp vụ hoặc dựng lại response đã lưu.
5. Nếu receipt đang xử lý theo một mô hình xử lý nhiều giai đoạn, trả trạng thái đang xử lý hoặc chờ theo chính sách đã định nghĩa.

Ví dụ phần tra cứu:

~~~java
private Mono<OrderResult> returnExistingResult(
        Long tenantId,
        String key,
        String requestHash) {

    return receiptRepository.findReceipt(
                    tenantId, "CREATE_ORDER", key)
            .switchIfEmpty(Mono.error(new IllegalStateException(
                    "Receipt conflict occurred but no receipt is visible yet")))
            .flatMap(receipt -> {
                if (!receipt.requestHash().equals(requestHash)) {
                    return Mono.error(new IdempotencyKeyReuseException(key));
                }

                if (receipt.resultOrderId() == null) {
                    return Mono.error(new OperationStillProcessingException(key));
                }

                return orderRepository.findById(receipt.resultOrderId())
                        .map(OrderResult::from);
            });
}
~~~

Trong mô hình receipt và order cùng transaction, receipt hoàn tất chỉ được commit khi order đã được lưu. Vì vậy, request lặp sau khi unique conflict thường có thể đọc được receipt hoàn chỉnh. Nếu hệ thống dùng workflow nhiều giai đoạn và commit trạng thái PROCESSING riêng, cần có lease, timeout, recovery worker và quy tắc xử lý trạng thái treo.

### 6.1. Bắt duplicate key ở ngoài transaction đã thất bại

Một unique constraint violation trong PostgreSQL làm transaction hiện tại rơi vào trạng thái lỗi cho tới khi rollback. Vì vậy, không nên bắt DuplicateKeyException rồi truy vấn receipt trong cùng transaction đã bị lỗi.

Đặt phần tra cứu sau transaction operator:

~~~java
public Mono<OrderResult> createOrderIdempotently(
        Long tenantId,
        String key,
        String requestHash,
        CreateOrderCommand command) {

    Mono<OrderResult> transaction = transactionalOperator.transactional(
            createOrderOnce(tenantId, key, requestHash, command));

    return transaction.onErrorResume(
            this::isIdempotencyReceiptConflict,
            error -> returnExistingResult(tenantId, key, requestHash));
}
~~~

isIdempotencyReceiptConflict phải nhận diện đúng unique constraint của bảng receipt, không được coi mọi DuplicateKeyException là request lặp. Một vi phạm unique constraint khác, chẳng hạn email hoặc order number, là lỗi nghiệp vụ riêng.

Khi transaction đầu tiên còn đang xử lý, insert receipt thứ hai có thể phải chờ unique index giải quyết kết quả. Nếu transaction đầu commit, request thứ hai nhận conflict; nếu transaction đầu rollback, request thứ hai có thể insert receipt và tiếp tục tạo order. Cơ chế cụ thể phụ thuộc database, nhưng unique constraint là điểm đồng bộ giữa các request.

## 7. Retry có kiểm soát trong Reactor

Reactor có các toán tử retry, nhưng retry có nghĩa là subscribe lại publisher nguồn. Với một write publisher, điều này có thể thực thi lại câu lệnh ghi.

### 7.1. Không retry mù thao tác ghi

Không nên áp dụng:

~~~java
return orderRepository.save(order)
        .retry(1);
~~~

Đoạn code không phân biệt lỗi tạm thời có thể retry an toàn với lỗi mà database đã commit nhưng acknowledgement bị mất. Nếu lệnh đầu đã thành công, mỗi lần retry có thể tạo thêm order.

### 7.2. Retry chỉ lỗi kết nối được xem là tạm thời

Nếu đã có idempotency key bền vững, có thể retry toàn bộ transaction với cùng key và cùng request hash:

~~~java
Mono<OrderResult> oneAttempt = transactionalOperator.transactional(
        createOrderOnce(tenantId, stableKey, requestHash, command));

return oneAttempt
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(this::isTransientConnectionFailure))
        .onErrorResume(
                this::isIdempotencyReceiptConflict,
                error -> returnExistingResult(tenantId, stableKey, requestHash));
~~~

Đây là cấu trúc minh họa. Cần triển khai bộ phân loại exception phù hợp với driver/database và đảm bảo duplicate receipt conflict không bị retry như lỗi mạng. Retry phải tạo một transaction mới cho mỗi lần thử; transaction boundary cần bao quanh một lần thực thi, rồi retry ở bên ngoài boundary đó.

Nếu lần đầu đã commit nhưng mất acknowledgement, lần thử sau dùng cùng key sẽ không tạo order thứ hai. Nó gặp receipt đã tồn tại và luồng xử lý chuyển sang đọc kết quả cũ.

### 7.3. Giới hạn retry và dùng backoff

Retry nên có số lần thử tối đa, exponential backoff hoặc khoảng chờ có giới hạn, jitter nếu nhiều instance có thể retry đồng thời, timeout tổng thể, bộ lọc lỗi tạm thời, metrics và log.

Không retry vô hạn. Retry dồn dập có thể làm database quá tải đúng lúc hệ thống đang gặp sự cố.

### 7.4. Không sinh lại key trong mỗi lần thử

Key và request hash phải được tính trước khi tạo publisher có thể retry:

~~~java
String stableKey = command.idempotencyKey();
String requestHash = requestHasher.hash(command);

Mono<OrderResult> work = createOrderIdempotently(
        tenantId, stableKey, requestHash, command);
~~~

Không đặt việc sinh UUID hoặc tạo command mới bên trong supplier được Reactor subscribe lại. Mọi lần thử của cùng ý định phải dùng cùng key.

## 8. Khi nào unique constraint nghiệp vụ là đủ?

Một số nghiệp vụ có định danh tự nhiên duy nhất. Ví dụ mã đơn hàng, mã thanh toán từ nhà cung cấp, mã hóa đơn trong một tenant hoặc mã sự kiện nguồn đã được xử lý.

Có thể dùng unique constraint trên định danh đó để ngăn bản ghi trùng:

~~~sql
ALTER TABLE payments
ADD CONSTRAINT uk_payment_provider_reference
UNIQUE (provider_name, provider_reference);
~~~

Nếu retry cùng một thanh toán, database từ chối bản ghi trùng reference. Ứng dụng có thể đọc payment hiện có để xác định kết quả.

Tuy nhiên, unique business key chỉ đủ khi định danh đó thực sự đại diện cho cùng một ý định nghiệp vụ. Nếu cùng một khách hàng có thể tạo nhiều order giống hệt nhau một cách hợp lệ, không thể dùng customer ID + amount làm unique key tùy tiện.

Idempotency key thường phù hợp với request/API; unique business key phù hợp với một định danh vốn đã duy nhất trong domain. Có thể dùng cả hai.

## 9. Upsert không tự động giải quyết mọi vấn đề

Một số database hỗ trợ cú pháp upsert như PostgreSQL ON CONFLICT hoặc MySQL ON DUPLICATE KEY UPDATE. Upsert có thể hữu ích để ghi một projection hoặc trạng thái có khóa ổn định.

Ví dụ PostgreSQL:

~~~sql
INSERT INTO order_requests (tenant_id, idempotency_key, request_hash)
VALUES (:tenantId, :key, :requestHash)
ON CONFLICT (tenant_id, idempotency_key) DO NOTHING;
~~~

Nếu không insert được vì key đã tồn tại, ứng dụng đọc receipt cũ và kiểm tra hash. Đây là một cách claim key không cần xử lý exception unique constraint, nhưng vẫn phải thực hiện việc đọc kết quả và kiểm tra payload.

Không nên dùng upsert một cách máy móc cho nghiệp vụ tạo order. Nếu nhánh UPDATE ghi đè dữ liệu hoặc kích hoạt trigger/side effect, retry có thể vẫn làm thay đổi trạng thái ngoài mong đợi. Upsert chỉ idempotent nếu toàn bộ semantics của nhánh conflict thực sự an toàn khi chạy lặp.

ON CONFLICT và ON DUPLICATE KEY UPDATE là cú pháp đặc thù database. Hãy kiểm tra dialect, driver R2DBC và cách Spring Data bind tham số khi dùng native SQL.

## 10. Phân biệt idempotency của database với side effect bên ngoài

Transaction R2DBC chỉ bảo vệ tài nguyên database tham gia transaction đó. Nó không thể rollback một request HTTP đã gửi, email đã gửi, khoản thanh toán đã được provider chấp nhận hoặc message đã được broker nhận.

Ví dụ:

1. Insert order và commit thành công.
2. Gọi payment provider để capture tiền.
3. Provider đã capture nhưng phản hồi bị mất.
4. Ứng dụng retry và capture lần nữa.

Idempotency receipt trong database không tự ngăn provider capture hai lần nếu request gửi tới provider không có cơ chế chống trùng tương ứng.

### 10.1. Dùng idempotency key ở cả ranh giới provider

Nếu provider hỗ trợ idempotency key, truyền cùng một key cho mọi lần gửi cùng một nghiệp vụ. Lưu provider reference và trạng thái để tra cứu khi phản hồi bị mất.

Không tự sinh key mới cho mỗi lần gọi provider. Key nên đại diện cho cùng một payment intent xuyên suốt retry.

### 10.2. Dùng transactional outbox cho message/event

Nếu cần phát sự kiện sau khi ghi order, có thể ghi order và outbox record trong cùng transaction:

~~~text
Transaction R2DBC:
  INSERT order
  INSERT outbox_event
  COMMIT

Worker:
  đọc outbox chưa gửi
  publish event
  đánh dấu đã gửi
~~~

Nếu worker publish thành công nhưng mất acknowledgement trước khi đánh dấu đã gửi, event có thể được publish lại. Consumer cần inbox/deduplication key hoặc xử lý idempotent.

Outbox bảo đảm thay đổi nghiệp vụ và ý định phát event được lưu cùng nhau. Nó không biến việc giao message thành exactly-once end-to-end.

### 10.3. Inbox ở consumer

Consumer có thể lưu event ID với unique constraint cùng transaction xử lý dữ liệu:

1. Claim event ID trong inbox.
2. Nếu đã tồn tại, bỏ qua event trùng hoặc trả kết quả đã xử lý.
3. Nếu mới, thực hiện thay đổi nghiệp vụ.
4. Commit inbox record và thay đổi nghiệp vụ cùng transaction.

Mô hình này giúp xử lý message giao ít nhất một lần mà hiệu ứng trong database không bị lặp.

## 11. Timeout, cancellation và trạng thái transaction

Trong R2DBC, timeout hoặc cancellation ở phía ứng dụng không chứng minh rằng database chưa ghi dữ liệu.

Các tình huống cần phân biệt:

- Request timeout trước khi statement được gửi.
- Statement đang chạy và driver gửi cancellation.
- Database đã thực thi statement nhưng transaction chưa commit.
- Commit đã tới database nhưng acknowledgement bị mất.
- Ứng dụng bị dừng sau commit nhưng trước khi trả HTTP response.

Tùy thời điểm, database có thể rollback hoặc đã commit. Khi connection đã mất, ứng dụng không thể dựa vào một lệnh rollback gửi qua chính connection đó để xác nhận trạng thái.

### 11.1. Không coi timeout là bằng chứng rollback

~~~java
return orderRepository.save(order)
        .timeout(Duration.ofSeconds(2));
~~~

Nếu timeout xảy ra, publisher phát lỗi TimeoutException. Điều đó không chứng minh order chưa được commit. Không nên tạo một order mới với key khác để “thử lại cho chắc”.

### 11.2. Tra cứu bằng idempotency key trên kết nối mới

Sau lỗi không xác định, ứng dụng có thể dùng connection mới để tìm receipt:

~~~java
return createOrderIdempotently(...)
        .onErrorResume(this::isAmbiguousConnectionFailure,
                error -> returnExistingResult(tenantId, key, requestHash));
~~~

Đây là phác thảo luồng xử lý. Nếu receipt chưa tồn tại ngay lúc tra cứu, transaction cũ có thể vẫn đang được database giải quyết hoặc kết nối chưa được dọn xong. Có thể cần thử lại thao tác claim key bằng cùng key, với timeout/backoff giới hạn, thay vì lập tức kết luận thất bại và tạo một key mới.

### 11.3. TransactionalOperator không thể làm mất sự mơ hồ của commit

TransactionalOperator giúp mở, commit hoặc rollback transaction theo publisher lifecycle. Tuy nhiên, nếu kết nối bị mất đúng lúc commit, client vẫn có thể không biết commit đã thành công hay chưa. Transaction manager có thể cố gắng rollback hoặc dọn dẹp connection, nhưng không thể khẳng định database chưa commit chỉ từ việc nhận exception.

Idempotency record nằm cùng transaction với dữ liệu nghiệp vụ là cách để truy vấn trạng thái sau đó bằng một connection mới.

## 12. Thiết kế API idempotent

Một API tạo order có thể tuân theo hợp đồng:

1. Client gửi Idempotency-Key cho mỗi ý định tạo order.
2. Client dùng lại key nếu không nhận được kết quả và cần retry.
3. Server xác thực tenant và payload.
4. Server tính hash payload chuẩn hóa.
5. Server claim key bằng unique constraint.
6. Server tạo order và lưu kết quả receipt trong cùng transaction.
7. Request lặp cùng key và cùng payload nhận lại kết quả cũ.
8. Request lặp cùng key nhưng payload khác nhận conflict.

Ví dụ response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "orderId": 4821,
  "status": "CREATED"
}
~~~

Khi request giống hệt được gửi lại với cùng key, server có thể trả lại cùng body và status theo chính sách API. Có thể thêm header thể hiện đây là kết quả được replay nếu hợp đồng cần phân biệt.

### 12.1. Key không thay thế authorization

Receipt phải được tra cứu trong phạm vi tenant/client đã xác thực. Không để người dùng khác chỉ cần biết key là đọc được kết quả nghiệp vụ.

### 12.2. Chính sách lưu giữ key

Thời gian giữ receipt phải dài hơn khoảng thời gian client, gateway, job hoặc provider có thể retry. Nếu xóa key quá sớm, request cũ gửi lại có thể tạo thao tác mới.

Với nghiệp vụ tài chính hoặc tạo dữ liệu có giá trị lâu dài, có thể cần lưu idempotency record lâu dài hoặc lưu unique business reference thay vì xóa theo TTL ngắn.

## 13. Quan sát và vận hành

Nên ghi nhận các thông tin sau trong log/metrics:

- Operation và idempotency key (có thể log dạng hash/mask nếu cần).
- Tenant hoặc client ID đã được xác thực.
- Request hash hoặc phiên bản payload, tránh log dữ liệu nhạy cảm.
- Kết quả claim key: mới, đã tồn tại, payload mismatch.
- Số lần retry và loại exception.
- Thời gian transaction, thời gian acquire connection và thời gian commit nếu đo được.
- Receipt cuối cùng: completed, processing hoặc failed theo mô hình trạng thái.
- Provider reference nếu có side effect bên ngoài.

Metrics có thể gồm:

| Metric | Ý nghĩa |
| --- | --- |
| idempotency_requests_total | Tổng số request có key |
| idempotency_replays_total | Số request được trả lại kết quả cũ |
| idempotency_payload_conflicts_total | Số lần cùng key nhưng payload khác |
| write_ambiguous_failures_total | Số lỗi ghi có kết quả không xác định |
| write_retry_attempts_total | Số lần retry thao tác ghi |
| idempotency_processing_age | Tuổi của receipt còn ở trạng thái xử lý |

Không log raw key hoặc payload nhạy cảm nếu không cần thiết. Dùng correlation ID để nối log giữa API, worker và provider.

## 14. Những lỗi thiết kế thường gặp

| Thiết kế/lỗi | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Retry mọi exception của save() | Ghi trùng sau commit nhưng mất acknowledgement | Phân loại lỗi và dùng idempotency key |
| Sinh key mới mỗi lần retry | Mỗi lần thử được xem là request mới | Giữ key ổn định cho cùng ý định |
| Chỉ SELECT kiểm tra key rồi INSERT | Hai request đồng thời có thể cùng vượt qua kiểm tra | Unique constraint và xử lý conflict |
| Ghi receipt và order ở hai transaction riêng | Receipt có thể tồn tại mà order không có hoặc ngược lại | Ghi cả hai trong cùng transaction |
| Bắt duplicate rồi query trong transaction đã lỗi | Database có thể đánh dấu transaction aborted | Để transaction rollback rồi query bằng connection/transaction mới |
| Coi mọi duplicate key là request replay | Có thể che lỗi unique constraint nghiệp vụ khác | Nhận diện đúng constraint của receipt |
| Không so sánh request hash | Cùng key nhưng payload khác có thể nhận nhầm kết quả | Hash payload chuẩn hóa và trả conflict |
| Dùng map trong memory | Mất bảo vệ khi restart hoặc chạy nhiều instance | Lưu receipt bền vững với unique constraint |
| Dùng upsert không xem xét side effect | Trigger hoặc nhánh update có thể chạy lặp | Xác định rõ semantics của nhánh conflict |
| Cho rằng timeout nghĩa là rollback | Tạo lại thao tác đã commit | Tra cứu bằng key ổn định |
| Transaction DB bao gồm lời gọi HTTP dài | Giữ connection lâu, nhưng không rollback được provider | Outbox/saga và idempotency ở provider |
| Xóa receipt quá sớm | Retry muộn tạo dữ liệu trùng | Retention phù hợp với retry window và domain |

## 15. Kiểm thử tình huống mất acknowledgement

Một test chỉ kiểm tra repository trả về thành công không thể chứng minh hệ thống chống được ghi trùng. Cần mô phỏng việc database đã commit nhưng ứng dụng không nhận được phản hồi.

### 15.1. Test request lặp cùng key

Chuẩn bị một request tạo order với key K:

1. Gửi request lần đầu và xác nhận có một order cùng receipt.
2. Gửi lại cùng key và cùng payload.
3. Xác nhận response lần hai tham chiếu cùng order ID.
4. Xác nhận số order được tạo vẫn là một.

### 15.2. Test cùng key nhưng payload khác

1. Gửi key K với tổng tiền 100.
2. Gửi lại key K với tổng tiền 500.
3. Xác nhận server trả conflict.
4. Xác nhận order ban đầu không bị thay đổi.

### 15.3. Test hai request đồng thời

Khởi chạy hai request cùng tenant, operation, key và payload bằng hai connection/transaction độc lập. Xác nhận chỉ một request claim được key và tạo order; request còn lại chờ hoặc nhận conflict rồi đọc kết quả cũ; cả hai response cuối cùng tham chiếu cùng một order; không có hai receipt hoặc hai order cho cùng key.

### 15.4. Test lỗi trước commit

Cho một bước sau insert receipt phát lỗi trước commit. Xác nhận cả receipt và order đều rollback. Sau đó gửi lại cùng key và xác nhận request có thể thực hiện thành công.

### 15.5. Test commit thành công nhưng response bị bỏ

Dùng fault injection ở tầng network/proxy hoặc test harness để:

1. Cho database commit transaction.
2. Chặn hoặc đóng kết nối trước khi acknowledgement tới ứng dụng.
3. Để caller nhận timeout/connection error.
4. Gửi lại cùng key.
5. Xác nhận server trả kết quả đã lưu và không tạo order mới.

Đây là test quan trọng nhất cho tình huống của bài học. Chỉ ngắt kết nối trước khi gửi SQL không mô phỏng được lỗi mất acknowledgement sau commit.

### 15.6. Test side effect ngoài database

Nếu order tạo payment hoặc phát message, kiểm tra provider nhận cùng idempotency key qua retry, outbox không mất event khi process restart, consumer deduplicate event ID và event được giao lại không làm side effect lặp.

## 16. Ví dụ kiểm thử service với StepVerifier

~~~java
@Test
void sameKeyAndSamePayloadShouldReturnSameOrder() {
    CreateOrderCommand command = new CreateOrderCommand(7L, new BigDecimal("100.00"));
    String key = "client-request-123";
    String hash = requestHasher.hash(command);

    Mono<OrderResult> first = service.createOrderIdempotently(1L, key, hash, command);
    Mono<OrderResult> replay = service.createOrderIdempotently(1L, key, hash, command);

    StepVerifier.create(first)
            .assertNext(result -> assertThat(result.orderId()).isNotNull())
            .verifyComplete();

    StepVerifier.create(replay)
            .assertNext(result -> assertThat(result.orderId()).isEqualTo(
                    findPreviouslyCreatedOrderId()))
            .verifyComplete();
}
~~~

Đoạn code trên minh họa ý tưởng; test thực tế nên lấy ID đầu tiên từ kết quả rồi so sánh trực tiếp, đồng thời query database để xác nhận chỉ có một order. Không dùng một helper đọc dữ liệu ngoài transaction nếu test cần kiểm tra tính nguyên tử của receipt và order.

## 17. Checklist thiết kế thao tác ghi có thể retry

- [ ] Đã xác định thao tác có tạo side effect hoặc bản ghi mới khi chạy lặp hay không.
- [ ] Client tạo và giữ một idempotency key ổn định cho mỗi ý định.
- [ ] Key được scope theo tenant/client và operation.
- [ ] Database có unique constraint bảo vệ key.
- [ ] Payload hash được lưu và so sánh khi key được dùng lại.
- [ ] Receipt và thay đổi nghiệp vụ được ghi trong cùng transaction.
- [ ] Duplicate receipt được xử lý sau khi transaction thử đã rollback.
- [ ] Retry chỉ áp dụng cho lỗi được phân loại là tạm thời và có giới hạn.
- [ ] Mọi lần retry dùng lại cùng key và cùng request hash.
- [ ] Side effect ngoài database có idempotency/outbox/inbox riêng.
- [ ] Receipt được giữ đủ lâu để bao phủ khoảng thời gian retry.
- [ ] Có test cho concurrent duplicate, rollback trước commit và mất acknowledgement sau commit.

## 18. Luồng xử lý khi mất kết nối sau thao tác ghi

~~~mermaid
flowchart TD
    A[Nhận command và idempotency key] --> B[Tính request hash]
    B --> C[Bắt đầu reactive transaction]
    C --> D[Insert receipt với unique key]
    D --> E{Claim key thành công?}
    E -->|Có| F[Ghi dữ liệu nghiệp vụ]
    F --> G[Lưu result reference vào receipt]
    G --> H[COMMIT]
    H --> I{Caller nhận acknowledgement?}
    I -->|Có| J[Trả kết quả]
    I -->|Không| K[Caller thấy kết quả không xác định]
    E -->|Không, key đã tồn tại| L[Rollback transaction thử]
    L --> M[Đọc receipt bằng transaction/kết nối mới]
    K --> N[Retry hoặc tra cứu bằng cùng key]
    N --> M
    M --> O{Request hash có khớp?}
    O -->|Không| P[Trả conflict]
    O -->|Có và đã hoàn tất| Q[Trả lại kết quả cũ]
    O -->|Chưa có kết quả| R[Chờ/claim lại theo chính sách recovery]
~~~

## 19. Kết luận

Mất kết nối sau khi database đã ghi có thể khiến ứng dụng nhận lỗi dù transaction đã commit. Vì caller không thể suy ra trạng thái commit chỉ từ timeout hoặc connection reset, retry một lệnh insert/update không có bảo vệ có thể tạo dữ liệu trùng hoặc lặp side effect.

Hãy làm cho thao tác ghi có thể nhận diện lặp bằng idempotency key ổn định, unique constraint và request hash. Ghi receipt cùng thay đổi nghiệp vụ trong một transaction; khi gặp key đã tồn tại, đọc kết quả cũ sau khi transaction thử đã rollback và trả lại kết quả tương ứng. Chỉ retry lỗi tạm thời với số lần giới hạn và dùng lại cùng key. Với message hoặc dịch vụ bên ngoài, bổ sung outbox/inbox hoặc idempotency của provider vì transaction R2DBC không thể rollback side effect ở hệ thống khác.

Kiểm thử phải bao gồm trường hợp database đã commit nhưng acknowledgement bị mất. Khi thiết kế đúng, request có thể được gửi lại nhiều lần, nhưng một ý định nghiệp vụ chỉ tạo một hiệu ứng dữ liệu trong phạm vi mà cơ chế idempotency bảo vệ.
