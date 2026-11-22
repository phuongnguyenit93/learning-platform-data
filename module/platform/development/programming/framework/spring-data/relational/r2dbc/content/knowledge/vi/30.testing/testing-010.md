# Kiểm thử xung đột đồng thời, khóa lạc quan và tính lũy đẳng

## 1. Vì sao cần kiểm thử đồng thời?

Ứng dụng Spring Data Relational R2DBC thường xử lý nhiều request cùng lúc. Mỗi request có thể đọc và thay đổi cùng một bản ghi, ngay cả khi code của từng request chạy đúng khi kiểm thử riêng lẻ.

Một ví dụ đơn giản là cập nhật số lượng tồn kho:

- Hai request cùng đọc số lượng còn lại là 5.
- Request A đặt số lượng thành 4.
- Request B đặt số lượng thành 3 dựa trên bản đọc cũ.
- Nếu cả hai thao tác ghi đều được chấp nhận mà không có kiểm soát phù hợp, thay đổi của A có thể bị ghi đè.

Một vấn đề khác xuất hiện khi client gửi lại cùng một yêu cầu do timeout hoặc retry. Ví dụ, client gọi API tạo đơn hàng, server đã lưu thành công nhưng response bị mất trên đường truyền. Client không biết yêu cầu đã hoàn tất nên gửi lại. Nếu server xử lý như một yêu cầu mới, ứng dụng có thể tạo hai đơn hàng hoặc thu tiền hai lần.

Ba khái niệm cần phân biệt:

- **Xung đột đồng thời:** nhiều thao tác cạnh tranh trên cùng dữ liệu tại cùng thời điểm.
- **Optimistic locking:** phát hiện một bản ghi đã thay đổi kể từ lúc được đọc, thường bằng thuộc tính version.
- **Idempotency:** bảo đảm việc gửi lại cùng một ý định nghiệp vụ không tạo thêm tác động ngoài dự kiến.

Kiểm thử cần chứng minh cả ba hành vi ở cấp database và service. Unit test thuần Java không thể chứng minh câu UPDATE có điều kiện version được driver thực thi đúng, unique constraint bảo vệ idempotency key ra sao, hoặc hai transaction thật sự cạnh tranh trên các connection riêng.

## 2. Phân biệt optimistic locking và idempotency

Hai cơ chế này giải quyết những vấn đề khác nhau.

| Cơ chế | Câu hỏi được trả lời | Cơ chế bảo vệ điển hình |
|---|---|---|
| Optimistic locking | Dữ liệu tôi đang sửa có còn là phiên bản tôi đã đọc không? | Cột version và điều kiện version trong UPDATE/DELETE |
| Idempotency | Đây có phải là lần gửi lại của cùng một yêu cầu nghiệp vụ không? | Idempotency key có unique constraint và kết quả đã xử lý |
| Database constraint | Dữ liệu có vi phạm bất biến được database bảo vệ không? | UNIQUE, CHECK, NOT NULL, FOREIGN KEY |
| Transaction | Các thay đổi database nào phải commit hoặc rollback cùng nhau? | Reactive transaction manager |

Ví dụ:

- Hai người cùng sửa trạng thái một đơn hàng bằng hai màn hình khác nhau: optimistic locking giúp phát hiện bản sửa cũ.
- Một client gửi lại POST /orders với cùng idempotency key: idempotency giúp trả lại kết quả của lần xử lý trước.
- Hai request khác nhau cùng đặt một mã đơn hàng: unique constraint bảo vệ tính duy nhất.
- Cập nhật order, inventory và outbox phải cùng thành công: transaction bảo vệ tính nguyên tử trong cùng database.

Không dùng một cơ chế thay thế cho tất cả các cơ chế còn lại. Một API có thể cần cả transaction, @Version, unique constraint và idempotency key.

## 3. Chuẩn bị dữ liệu có version

Spring Data Relational hỗ trợ optimistic locking qua annotation @Version.

Ví dụ entity:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Schema tương ứng:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);
~~~

Khi entity được lưu qua mapping infrastructure của Spring Data, framework sử dụng version để phát hiện cập nhật cạnh tranh. Về ý tưởng, thao tác update tương đương:

~~~sql
UPDATE orders
SET status = :status,
    version = :nextVersion
WHERE id = :id
  AND version = :expectedVersion;
~~~

Nếu không có hàng nào khớp ID và version kỳ vọng, Spring Data có thể phát OptimisticLockingFailureException.

Giá trị version ban đầu và kiểu dữ liệu cụ thể cần phù hợp với cấu hình Spring Data và schema. Hãy dùng entity được trả về từ save vì đối tượng đó mang version mới sau thao tác thành công. Không tự tăng version trước khi gọi save.

## 4. Kiểm thử optimistic locking bằng hai bản entity cũ

Đây là test cơ bản nhất để chứng minh optimistic locking.

### 4.1. Đọc cùng một version hai lần

Test cần tạo hai object độc lập từ cùng một trạng thái database:

~~~java
@Test
void shouldRejectSecondSaveFromStaleEntity() {
    Mono<Void> test = orderRepository.findById(orderId)
        .flatMap(firstRead ->
            orderRepository.findById(orderId)
                .flatMap(secondRead -> {
                    assertThat(firstRead.getVersion())
                        .isEqualTo(secondRead.getVersion());

                    firstRead.setStatus("PAID");
                    secondRead.setStatus("CANCELLED");

                    return orderRepository.save(firstRead)
                        .then(orderRepository.save(secondRead))
                        .then();
                })
        );

    StepVerifier.create(test)
        .expectError(OptimisticLockingFailureException.class)
        .verify();
}
~~~

Trình tự của test:

1. Đọc entity lần thứ nhất.
2. Đọc entity lần thứ hai trước khi có thao tác ghi.
3. Xác nhận hai bản đọc mang cùng version.
4. Lưu bản thứ nhất, khiến version trong database tăng.
5. Lưu bản thứ hai vẫn mang version cũ.
6. Xác nhận thao tác thứ hai phát lỗi optimistic locking.

Test này kiểm tra hành vi stale entity một cách xác định. Nó hữu ích và nhanh, nhưng chưa phải là một cuộc đua đồng thời thực sự: hai thao tác save được thực hiện tuần tự.

### 4.2. Xác nhận dữ liệu cuối cùng

Không chỉ kiểm tra exception. Hãy đọc lại database để xác nhận:

- Trạng thái của lần save thành công vẫn được giữ.
- Version chỉ tăng theo số lần ghi thành công.
- Bản ghi không bị xóa hoặc thay đổi một phần.

Ví dụ:

~~~java
StepVerifier.create(orderRepository.findById(orderId))
    .assertNext(saved -> {
        assertThat(saved.getStatus()).isEqualTo("PAID");
        assertThat(saved.getVersion()).isEqualTo(initialVersion + 1);
    })
    .verifyComplete();
~~~

Test cần bảo đảm initialVersion là version đã lưu trước khi chạy kịch bản. Không hard-code version nếu cơ chế insert hoặc fixture của dự án có quy ước khởi tạo khác.

## 5. Kiểm thử race condition thật bằng hai transaction

Một test hai bản entity cũ chứng minh stale write bị từ chối. Để kiểm tra hai request thực sự cạnh tranh, cần cho hai transaction riêng cùng đọc một version trước khi cả hai được phép ghi.

Không dùng Thread.sleep để cố tạo race. Sleep phụ thuộc tốc độ máy, CI load và scheduler nên test dễ chập chờn.

Có thể dùng một barrier reactive để đồng bộ hai publisher.

### 5.1. Điều kiện của test

Một test race đáng tin cậy cần:

- Hai subscription độc lập.
- Hai transaction độc lập.
- Hai connection khả dụng trong pool.
- Cả hai transaction đọc xong cùng version trước khi được mở barrier.
- Cả hai cùng tiếp tục tới bước save sau khi barrier phát tín hiệu.
- Test không bị bao trong một transaction bên ngoài dùng chung connection.
- Kết quả lỗi được materialize để một lỗi không hủy publisher còn lại trước khi thu thập kết quả.

Nếu connection pool chỉ cho phép một connection, transaction thứ nhất có thể giữ connection trong lúc chờ barrier và transaction thứ hai không thể đọc để tới barrier. Test sẽ treo. Cần cấu hình pool có ít nhất hai connection cho kịch bản này.

### 5.2. Ví dụ barrier không blocking

Dùng Reactor Sinks để chờ cả hai transaction đọc xong:

~~~java
private Mono<Order> updateAfterBothReads(
        Long orderId,
        String status,
        Sinks.One<Void> release,
        AtomicInteger arrivals) {

    Mono<Order> work = orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(
            new OrderNotFoundException(orderId)
        ))
        .flatMap(order -> {
            if (arrivals.incrementAndGet() == 2) {
                release.tryEmitEmpty();
            }

            return release.asMono()
                .then(Mono.defer(() -> {
                    order.setStatus(status);
                    return orderRepository.save(order);
                }));
        });

    return transactionalOperator.transactional(work);
}
~~~

Mỗi lần gọi updateAfterBothReads tạo một publisher transaction riêng. Cả hai transaction đọc entity, sau đó chờ cùng một Sinks.One. Khi transaction thứ hai đến barrier, sink phát tín hiệu và cả hai cùng tiếp tục.

Ví dụ test:

~~~java
@Test
void onlyOneConcurrentUpdateCanSaveTheSameVersion() {
    Sinks.One<Void> release = Sinks.one();
    AtomicInteger arrivals = new AtomicInteger();

    Mono<Signal<Order>> first =
        updateAfterBothReads(
            orderId, "PAID", release, arrivals
        ).materialize();

    Mono<Signal<Order>> second =
        updateAfterBothReads(
            orderId, "CANCELLED", release, arrivals
        ).materialize();

    StepVerifier.create(Mono.zip(first, second))
        .assertNext(result -> {
            List<Signal<Order>> signals =
                List.of(result.getT1(), result.getT2());

            long successes = signals.stream()
                .filter(Signal::isOnNext)
                .count();

            long failures = signals.stream()
                .filter(Signal::isOnError)
                .count();

            assertThat(successes).isEqualTo(1);
            assertThat(failures).isEqualTo(1);

            Throwable error = signals.stream()
                .filter(Signal::isOnError)
                .findFirst()
                .orElseThrow()
                .getThrowable();

            assertThat(Exceptions.unwrap(error))
                .isInstanceOf(OptimisticLockingFailureException.class);
        })
        .verifyComplete();
}
~~~

Đoạn code minh họa cần import các kiểu liên quan như Signal, Sinks, AtomicInteger, List, Exceptions và TransactionalOperator. Tên repository, entity và exception được thay theo dự án.

Materialize chuyển tín hiệu onNext/onError thành một giá trị Signal. Vì vậy Mono.zip có thể đợi cả hai kết quả thay vì bị kết thúc ngay khi một publisher phát lỗi.

### 5.3. Xác minh trạng thái sau race

Sau khi hai signal đã được thu thập, đọc lại order bằng một truy vấn mới:

~~~java
StepVerifier.create(orderRepository.findById(orderId))
    .assertNext(saved -> {
        assertThat(saved.getVersion()).isEqualTo(initialVersion + 1);
        assertThat(List.of("PAID", "CANCELLED"))
            .contains(saved.getStatus());
    })
    .verifyComplete();
~~~

Chỉ một update được chấp nhận, nên version tăng một lần. Trạng thái cuối là giá trị của request thắng cuộc; test không nên giả định trước request nào thắng vì thứ tự scheduling có thể thay đổi.

Không gắn @Transactional cho chính test method nếu điều đó khiến hai lời gọi service tham gia cùng một transaction test. Mục tiêu là tạo hai transaction độc lập giống hai request thật. Hãy đọc lại dữ liệu sau khi cả hai transaction kết thúc.

## 6. Kiểm thử cập nhật có điều kiện để bảo vệ bất biến

Optimistic locking phù hợp với việc cập nhật entity theo version. Một số bất biến có thể được bảo vệ trực tiếp bằng một câu SQL có điều kiện.

Ví dụ trừ tồn kho:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
~~~

Nếu rowsUpdated bằng 1, thao tác trừ kho thành công. Nếu bằng 0, không đủ tồn kho hoặc không có sản phẩm phù hợp.

Ví dụ service:

~~~java
public Mono<Void> reserve(Long productId, int quantity) {
    return databaseClient.sql("""
            UPDATE inventory
            SET available = available - :quantity
            WHERE product_id = :productId
              AND available >= :quantity
            """)
        .bind("quantity", quantity)
        .bind("productId", productId)
        .fetch()
        .rowsUpdated()
        .flatMap(rows -> {
            if (rows == 1) {
                return Mono.empty();
            }

            return Mono.error(
                new InsufficientInventoryException(productId)
            );
        });
}
~~~

Đây là thao tác atomic ở database: điều kiện và phép trừ nằm trong cùng câu UPDATE. Hai request cùng tranh chấp không thể cùng trừ nếu tổng số lượng vượt quá tồn kho còn lại.

Nếu query tự viết như trên, ứng dụng phải tự quản lý mọi điều kiện version nếu cũng cần optimistic locking. @Version không tự thêm điều kiện vào mọi câu SQL DatabaseClient.

### 6.1. Test hai request cùng đặt tồn kho

Giả sử số lượng ban đầu là 5. Hai request cùng đặt 4:

- Tối đa một request có thể cập nhật thành công.
- Request còn lại nhận rowsUpdated bằng 0 sau khi điều kiện không còn đúng.
- Số lượng cuối cùng không âm.
- Tổng số lượng được giữ không vượt quá 5.

Test có thể chạy hai publisher độc lập:

~~~java
Mono<Signal<Void>> first =
    inventoryService.reserve(productId, 4).materialize();

Mono<Signal<Void>> second =
    inventoryService.reserve(productId, 4).materialize();

StepVerifier.create(Mono.zip(first, second))
    .assertNext(pair -> {
        List<Signal<Void>> signals =
            List.of(pair.getT1(), pair.getT2());

        assertThat(signals.stream().filter(Signal::isOnComplete).count())
            .isEqualTo(1);

        assertThat(signals.stream().filter(Signal::isOnError).count())
            .isEqualTo(1);
    })
    .verifyComplete();
~~~

Sau đó đọc inventory và xác nhận available bằng 1. Cách viết chính xác phụ thuộc kiểu kết quả của service và cách ánh xạ rowsUpdated.

## 7. Idempotency trong API

### 7.1. Vấn đề gửi lại cùng yêu cầu

Một request có thể được gửi lại do:

- Client timeout trong khi server đã xử lý thành công.
- Gateway retry khi không nhận được response.
- Người dùng bấm nút nhiều lần.
- Message broker giao lại message sau khi consumer chưa xác nhận.
- Worker khởi động lại sau khi đã thực hiện một phần công việc.

Nếu mỗi lần gửi đều tạo một đơn hàng mới, hệ thống không idempotent.

Một idempotency key đại diện cho một ý định nghiệp vụ duy nhất. Client tạo key cho lần thao tác ban đầu và gửi lại chính key đó nếu cần retry.

Ví dụ request:

~~~http
POST /orders
Idempotency-Key: 2f4b2b9a-7a70-4b3d-91b0-8d4d25a63f02
Content-Type: application/json
~~~

Nếu client gửi lại cùng yêu cầu với cùng key, server nhận biết đây là lần gửi lại và trả về kết quả đã ghi nhận thay vì tạo đơn hàng thứ hai.

### 7.2. Bảng lưu idempotency key

Một schema đơn giản:

~~~sql
CREATE TABLE idempotency_records (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    client_id VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(150) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(30) NOT NULL,
    resource_id BIGINT,
    response_body TEXT,
    created_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    CONSTRAINT uq_idempotency_client_key
        UNIQUE (client_id, idempotency_key)
);
~~~

Unique constraint trên client_id và idempotency_key là lớp bảo vệ quyết định khi hai request cùng key đến đồng thời.

Các trường thường có ý nghĩa:

- client_id: phạm vi người gọi hoặc tenant.
- idempotency_key: định danh lần thực hiện logic.
- request_hash: dấu vân tay payload để phát hiện cùng key nhưng nội dung khác.
- status: trạng thái như IN_PROGRESS, COMPLETED hoặc FAILED.
- resource_id: ID đơn hàng hoặc tài nguyên được tạo.
- response_body: kết quả cần trả lại nếu API muốn replay response.
- created_at/completed_at: thời điểm bắt đầu và hoàn tất.

Không chỉ dựa vào việc kiểm tra key bằng SELECT trước khi INSERT. Hai request có thể cùng SELECT và cùng thấy key chưa tồn tại. Unique constraint phải bảo vệ cuộc đua ở database.

### 7.3. Cùng key nhưng payload khác

Nếu client dùng cùng idempotency key nhưng gửi payload khác, không được âm thầm trả kết quả của payload cũ hoặc xử lý payload mới như một yêu cầu mới.

Hãy so sánh request_hash:

- Cùng key, cùng hash, đã COMPLETED: trả lại kết quả trước đó.
- Cùng key, cùng hash, đang IN_PROGRESS: trả trạng thái đang xử lý hoặc cho client retry theo hợp đồng API.
- Cùng key, khác hash: trả lỗi conflict hoặc lỗi request không hợp lệ theo hợp đồng API.
- Key chưa tồn tại: thử claim key và xử lý nghiệp vụ.

Hash nên được tạo từ biểu diễn request đã chuẩn hóa và bao gồm những trường có ý nghĩa nghiệp vụ. Không hash JSON thô nếu thứ tự thuộc tính hoặc format có thể thay đổi mà nội dung logic vẫn giống nhau.

## 8. Xử lý hai request cùng idempotency key

### 8.1. Không dùng SELECT rồi INSERT như cơ chế khóa duy nhất

Mẫu dễ sai:

~~~java
return idempotencyRepository.findByKey(key)
    .flatMap(existing -> Mono.just(existing.getResponse()))
    .switchIfEmpty(
        createOrder(command)
            .flatMap(order -> idempotencyRepository.save(
                new IdempotencyRecord(key, order.getId())
            ))
    );
~~~

Hai request đồng thời có thể cùng đọc thấy key chưa tồn tại, sau đó cả hai cùng tạo order. Việc kiểm tra trước khi insert không bảo vệ race condition.

Cần một thao tác claim được database bảo vệ bằng unique constraint hoặc câu INSERT có xử lý conflict.

### 8.2. Claim key bằng INSERT nguyên tử

Với PostgreSQL, có thể dùng:

~~~sql
INSERT INTO idempotency_records (
    client_id,
    idempotency_key,
    request_hash,
    status,
    created_at
)
VALUES (
    :clientId,
    :key,
    :requestHash,
    'IN_PROGRESS',
    CURRENT_TIMESTAMP
)
ON CONFLICT (client_id, idempotency_key) DO NOTHING;
~~~

Đọc rowsUpdated:

- 1: request đã claim được key.
- 0: key đã tồn tại và request cần đọc trạng thái hiện tại.

Câu lệnh ON CONFLICT là đặc thù PostgreSQL. Database khác có cú pháp upsert/ignore khác. Hãy dùng cú pháp của hệ quản trị đang triển khai và kiểm thử trên đúng driver.

Sau khi claim thành công, tạo resource và cập nhật idempotency record thành COMPLETED trong cùng transaction database:

~~~text
BEGIN
  INSERT idempotency key
  INSERT order
  INSERT outbox event
  UPDATE idempotency record -> COMPLETED
COMMIT
~~~

Nếu transaction rollback, cả key claim và order/outbox đều rollback. Request retry có thể thử claim lại.

### 8.3. Xử lý khi key đã tồn tại

Nếu INSERT không claim được key:

1. Đọc record hiện tại theo client_id và idempotency_key.
2. So sánh request_hash.
3. Nếu khác hash, trả conflict.
4. Nếu COMPLETED, trả lại resource/response đã lưu.
5. Nếu IN_PROGRESS, trả trạng thái đang xử lý hoặc áp dụng chính sách chờ/ retry có giới hạn.
6. Nếu record FAILED, áp dụng chính sách nghiệp vụ rõ ràng: trả lỗi đã lưu, cho phép retry cùng operation, hoặc yêu cầu key mới.

Với PostgreSQL, nếu dùng INSERT thường và để unique constraint violation phát sinh, transaction hiện tại có thể bị đánh dấu aborted. Không nên bắt lỗi unique rồi tiếp tục SELECT trong cùng transaction như thể transaction vẫn dùng được. Cách INSERT ... ON CONFLICT DO NOTHING giúp xử lý conflict mà không làm transaction rơi vào trạng thái lỗi theo cách đó.

### 8.4. Hai request cùng key có thể chờ nhau

Nếu request thứ nhất đã insert key nhưng chưa commit, request thứ hai insert cùng key có thể phải chờ unique check hoàn tất. Sau khi transaction đầu commit, request thứ hai nhận kết quả conflict/không insert được. Nếu transaction đầu rollback, request thứ hai có thể claim key.

Đây là hành vi cần được kiểm thử trên database thật. Test mock repository không thể chứng minh unique constraint và locking behavior của database.

## 9. Idempotency không đồng nghĩa exactly-once

Idempotency giúp một thao tác có thể được gửi lại mà không tạo tác động trùng theo key. Nó không tự bảo đảm một hệ thống phân tán chỉ thực hiện đúng một lần mọi side effect.

Ví dụ:

1. Server gọi payment gateway.
2. Gateway xử lý thanh toán thành công.
3. Kết nối bị timeout trước khi server nhận response.
4. Server không biết payment đã thành công hay chưa.

Nếu server gọi lại với một payment request mới, có thể bị thu tiền hai lần. Cần dùng idempotency key được gateway hỗ trợ hoặc truy vấn trạng thái giao dịch trước khi retry.

Với message broker, consumer có thể nhận cùng event nhiều lần. Consumer nên ghi nhận event ID đã xử lý bằng unique constraint hoặc một cơ chế deduplication tương đương.

Mô hình phổ biến là at-least-once delivery kết hợp idempotent consumer. Không dựa vào lời hứa exactly-once chung chung nếu từng hệ thống tham gia không cung cấp semantics đó.

## 10. Kết hợp idempotency với transaction và outbox

Khi tạo order và cần phát event, có thể lưu ba phần trong một transaction:

- Idempotency record.
- Order.
- Outbox event.

Ví dụ luồng:

~~~text
POST /orders + Idempotency-Key
             |
             v
      Service layer
             |
             v
      R2DBC transaction
             |
             +-- claim idempotency key
             |
             +-- create order
             |
             +-- create outbox event
             |
             +-- mark idempotency COMPLETED
             |
             v
           COMMIT
             |
             v
       Return response
             |
             v
       Outbox worker
             |
             v
     Publish event / call external system
~~~

Nếu tạo order thành công nhưng ghi outbox thất bại, transaction rollback cả order và idempotency record. Client retry cùng key có thể thực hiện lại.

Nếu transaction commit nhưng response bị mất, client retry cùng key sẽ đọc idempotency record COMPLETED và nhận lại kết quả trước đó.

Worker xử lý outbox có thể publish lặp nếu crash sau khi gửi message nhưng trước khi đánh dấu event đã gửi. Vì vậy consumer hoặc hệ thống đích cũng cần idempotency theo event ID.

## 11. Kiểm thử idempotency

### 11.1. Gửi lại tuần tự cùng key

Test đầu tiên gửi cùng request hai lần:

~~~java
@Test
void repeatedRequestWithSameKeyReturnsSameOrder() {
    Mono<OrderResponse> first =
        orderService.create(command, idempotencyKey);

    Mono<OrderResponse> second =
        orderService.create(command, idempotencyKey);

    StepVerifier.create(first)
        .assertNext(firstResponse ->
            StepVerifier.create(second)
                .assertNext(secondResponse -> {
                    assertThat(secondResponse.orderId())
                        .isEqualTo(firstResponse.orderId());
                })
                .verifyComplete()
        )
        .verifyComplete();
}
~~~

Cấu trúc lồng StepVerifier trong assertNext chỉ để minh họa ý tưởng; trong test thực tế, nên nối hai publisher bằng flatMap hoặc thu thập kết quả bằng Tuple để tránh subscription lồng khó đọc.

Một cách viết gọn hơn:

~~~java
Mono.zip(
    orderService.create(command, idempotencyKey),
    orderService.create(command, idempotencyKey)
).as(StepVerifier::create)
    .assertNext(pair ->
        assertThat(pair.getT1().orderId())
            .isEqualTo(pair.getT2().orderId())
    )
    .verifyComplete();
~~~

Nếu hai publisher được subscribe đồng thời, test này cũng tạo một cuộc đua cùng key. Để tách rõ kiểm thử tuần tự và đồng thời, hãy viết hai test riêng.

### 11.2. Kiểm tra số lượng resource

Sau khi gửi cùng key nhiều lần, xác nhận database chỉ có một order:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE idempotency_key = :key;
~~~

Nếu idempotency key được lưu ở bảng riêng, hãy đếm record theo client_id/key và kiểm tra resource_id. Không chỉ xác nhận hai response giống nhau; hai resource khác nhau có thể vô tình trả cùng một response do lỗi mapping.

### 11.3. Cùng key nhưng payload khác

Test phải xác nhận cùng key với request hash khác bị từ chối:

~~~java
StepVerifier.create(
    orderService.create(differentCommand, idempotencyKey)
)
.expectError(IdempotencyKeyReuseException.class)
.verify();
~~~

Sau đó xác nhận resource đầu tiên vẫn giữ nguyên và không có order thứ hai.

### 11.4. Hai request đồng thời cùng key

Dùng barrier tương tự test optimistic locking:

- Hai request bắt đầu với cùng key và cùng payload.
- Cả hai cùng tới bước claim.
- Unique constraint chỉ cho phép một record.
- Một request thực hiện tạo order.
- Request còn lại đọc kết quả đã hoàn tất hoặc nhận trạng thái IN_PROGRESS theo chính sách.
- Cuối cùng chỉ có một order và một outbox event tương ứng.

Kết quả API của hai request có thể khác nhau về HTTP status nếu hợp đồng cho phép request thứ hai nhận 202 Accepted trong khi request đầu đang xử lý. Điều cần bảo đảm là không tạo hai tác động nghiệp vụ.

### 11.5. Mô phỏng mất response sau commit

Đây là kịch bản quan trọng:

1. Service commit order, idempotency record và outbox.
2. Test giả lập response bị mất hoặc client không nhận được.
3. Client gửi lại cùng key.
4. Server trả kết quả đã lưu.
5. Database vẫn chỉ có một order và một outbox event.

Không cần thật sự cắt mạng trong mọi unit test. Có thể tách phần xử lý nghiệp vụ khỏi HTTP response và kiểm tra trực tiếp hành vi retry cùng key. Integration test cấp HTTP có thể bổ sung mô phỏng timeout khi cần.

## 12. Kiểm thử consumer idempotent và duplicate delivery

Outbox worker hoặc message consumer có thể nhận cùng event nhiều lần. Một bảng processed_events có thể lưu event ID đã xử lý:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_processed_event
        UNIQUE (consumer_name, event_id)
);
~~~

Consumer thực hiện trong một transaction:

1. Thử insert processed event ID.
2. Nếu insert thành công, thực hiện thay đổi nghiệp vụ.
3. Commit cả dấu processed và thay đổi.
4. Nếu event ID đã tồn tại, bỏ qua tác động trùng.

Hai request consumer cùng event ID phải được bảo vệ bởi unique constraint. Nếu chỉ SELECT trước khi INSERT, chúng vẫn có thể cùng thấy chưa xử lý.

Ví dụ logic khái niệm:

~~~java
public Mono<Void> handle(OrderConfirmed event) {
    return transactionalOperator.transactional(
        processedEventRepository.claim(
                "inventory-consumer",
                event.eventId()
            )
            .flatMap(claimed -> {
                if (!claimed) {
                    return Mono.empty();
                }

                return inventoryRepository.reserveForOrder(event.orderId());
            })
    );
}
~~~

claim phải là thao tác nguyên tử được bảo vệ bởi unique constraint hoặc upsert phù hợp. Nếu claim và cập nhật inventory nằm trong cùng transaction, lỗi ở bước inventory sẽ rollback cả processed marker để event có thể được xử lý lại.

Nếu đánh dấu processed trước transaction nghiệp vụ rồi transaction sau thất bại, event có thể bị bỏ qua vĩnh viễn. Vì vậy processed marker và side effect database cần cùng transaction cục bộ.

## 13. Kiểm thử retry sau optimistic locking conflict

Retry optimistic locking cần tải lại entity mới nhất và áp dụng lại ý định nghiệp vụ. Không retry cùng object stale.

Ví dụ một thao tác tăng counter:

~~~java
public Mono<Inventory> addStock(Long productId, int amount) {
    return updateOnce(productId, amount)
        .retryWhen(
            Retry.max(2)
                .filter(
                    OptimisticLockingFailureException.class::isInstance
                )
        );
}

private Mono<Inventory> updateOnce(Long productId, int amount) {
    return inventoryRepository.findById(productId)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(productId)
        ))
        .flatMap(inventory -> {
            inventory.setAvailable(
                inventory.getAvailable() + amount
            );
            return inventoryRepository.save(inventory);
        });
}
~~~

Mỗi lần subscribe lại updateOnce, pipeline đọc entity mới và tính lại số lượng từ version mới nhất.

Tuy nhiên, retry chỉ an toàn nếu thao tác thực sự có thể áp dụng lại. Không đặt side effect như gửi email hoặc charge payment trong updateOnce nếu retry có thể lặp side effect đó.

### 13.1. Kiểm tra giới hạn retry

Test nên xác nhận:

- Conflict đầu tiên khiến pipeline đọc lại.
- Lần retry thành công với version mới.
- Retry không vượt quá số lần cấu hình.
- Nếu mọi lần đều conflict, lỗi cuối được trả về.
- Các lỗi không phải optimistic locking không bị retry nhầm.

Có thể dùng mock cho số lần gọi để kiểm tra logic retry, nhưng cần integration test riêng để xác nhận database thực sự phát lỗi optimistic locking.

### 13.2. Không retry lỗi constraint hoặc lỗi kết nối một cách tùy tiện

Unique constraint violation, validation failure, timeout và connection failure có semantics khác nhau. Chỉ retry những lỗi có thể phục hồi theo chính sách nghiệp vụ.

Nếu retry sau timeout của một side effect ngoài, kết quả có thể không rõ ràng. Hãy dùng idempotency key và đối soát trạng thái thay vì gửi lại lệnh mới.

## 14. Test data, transaction test và isolation

### 14.1. Dùng database tương thích với production

Hành vi concurrency phụ thuộc database:

- Cách khóa hàng khi UPDATE.
- Cách xử lý unique constraint khi hai transaction insert cùng key.
- Isolation level mặc định.
- Semantics của upsert.
- Hành vi rowsUpdated.
- Kiểu dữ liệu và conversion của R2DBC driver.

Một database in-memory có thể không mô phỏng đúng hành vi của PostgreSQL hoặc hệ quản trị production. Với test concurrency và idempotency, nên dùng cùng hệ quản trị và R2DBC driver như môi trường chạy thật, thường thông qua Testcontainers.

### 14.2. Không bọc toàn bộ race test trong một transaction

Nếu test class hoặc test method có transaction ngoài, hai service call có thể tham gia cùng transaction context hoặc không tạo ra hai connection độc lập như mong muốn.

Để kiểm tra race:

- Tạo fixture và commit trước khi bắt đầu test.
- Gọi hai service publisher độc lập.
- Mỗi publisher mở transaction riêng.
- Đợi cả hai kết thúc.
- Đọc lại trạng thái bằng truy vấn mới.
- Dọn dữ liệu sau khi assertion hoàn tất.

Nếu dùng test transaction management, hãy kiểm tra rõ cách transaction context được truyền và đảm bảo nó không làm mất tính độc lập của hai request.

### 14.3. Pool phải đủ connection

Race test dùng hai transaction giữ connection đồng thời cần ít nhất hai connection. Nếu có nhiều transaction chờ barrier, pool cần đủ số connection tương ứng.

Một test treo ở barrier thường có thể do pool chỉ cấp một connection, không nhất thiết do lỗi ở optimistic locking.

Không tăng pool toàn ứng dụng chỉ để sửa test. Hãy cấu hình pool riêng cho test fixture và bảo đảm nó được đóng đúng cách.

### 14.4. Không dùng Thread.sleep để đồng bộ

Thread.sleep chỉ trì hoãn một khoảng thời gian, không chứng minh hai request đã đọc cùng version. Kết quả phụ thuộc tải máy và thời điểm scheduler.

Ưu tiên:

- Reactor Sinks hoặc barrier reactive.
- Latch không blocking chỉ khi được dùng đúng cách ở test thread, không trên event-loop.
- Test hook sau khi đọc dữ liệu.
- Cơ chế đồng bộ tường minh trong fixture.

Mục tiêu là đồng bộ theo sự kiện thực tế, ví dụ "cả hai transaction đã đọc xong", thay vì "đợi 100 mili giây rồi hy vọng".

## 15. Kiểm thử các tình huống lỗi và phục hồi

Một bộ test tốt cần bao phủ nhiều đường thất bại:

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Hai entity cùng version được lưu tuần tự | Lần đầu thành công, lần sau conflict |
| Hai transaction cùng cập nhật version cũ | Chỉ một update thành công |
| Hai request trừ tồn kho vượt số lượng | Không có tồn kho âm |
| Hai request cùng idempotency key và payload | Chỉ một resource nghiệp vụ |
| Cùng key nhưng payload khác | Request thứ hai bị từ chối |
| Retry sau commit nhưng mất response | Trả lại kết quả cũ |
| Worker nhận cùng event hai lần | Consumer chỉ áp dụng side effect database một lần |
| Transaction ghi order nhưng outbox lỗi | Cả order và outbox rollback |
| Retry optimistic locking | Đọc lại entity mới trước lần ghi tiếp theo |
| Retry gặp lỗi validation | Không retry vô hạn hoặc che lỗi |
| Consumer crash trước commit | Processed marker và thay đổi nghiệp vụ cùng rollback |
| Consumer crash sau commit trước ack | Event giao lại nhưng được deduplicate |

Kiểm tra dữ liệu sau lỗi là phần quan trọng. Một exception đúng kiểu không chứng minh dữ liệu không bị ghi một phần.

## 16. Kiểm thử API idempotency với WebFlux

Ở tầng HTTP, cần xác nhận header idempotency được nhận và truyền tới service.

Ví dụ controller:

~~~java
@PostMapping("/orders")
public Mono<ResponseEntity<OrderResponse>> create(
        @RequestHeader("Idempotency-Key") String key,
        @RequestBody CreateOrderRequest request) {

    return orderService.create(request, key)
        .map(response -> ResponseEntity.ok(response));
}
~~~

Một số API có thể trả 201 Created cho lần tạo đầu và 200 OK cho lần replay, hoặc giữ cùng status/response. Điều quan trọng là hợp đồng phải nhất quán và được kiểm thử.

Test HTTP cần xác nhận:

- Thiếu key bị xử lý theo chính sách API.
- Key sai định dạng bị từ chối.
- Key cùng payload trả cùng resource ID.
- Key khác payload trả conflict.
- Header được chuyển đúng vào service.
- Response replay không tạo thêm outbox event.
- Hai request cùng key gửi đồng thời không tạo resource trùng.

Không lấy địa chỉ IP hoặc user agent làm idempotency key. Key nên đại diện cho một hành động nghiệp vụ do client tạo và được giới hạn theo client/tenant đã xác thực.

## 17. Phân biệt idempotency key với optimistic version trong API

Một API có thể dùng cả hai:

~~~text
POST /orders
Idempotency-Key: request-abc
       |
       +-- ngăn tạo đơn hàng trùng khi retry cùng request


PUT /orders/42
If-Match: "order-42-v7"
       |
       +-- ngăn ghi đè khi client sửa version cũ
~~~

Idempotency key áp dụng cho cùng một request logic được gửi lại. ETag/If-Match hoặc version áp dụng cho việc cập nhật một resource đã tồn tại dựa trên phiên bản client nhìn thấy.

Ví dụ:

- Client gửi POST tạo order, timeout rồi gửi lại cùng key: server replay kết quả.
- Hai người sửa order 42, người thứ hai gửi If-Match version 7 sau khi người thứ nhất đã lưu version 8: server từ chối stale update.
- Client gửi POST với key mới: đây là một ý định mới, có thể tạo resource mới nếu nghiệp vụ cho phép.

Không dùng idempotency key để thay optimistic locking. Cũng không dùng version của order làm idempotency key cho mọi thao tác tạo mới.

## 18. Những lỗi thường gặp

| Lỗi hoặc nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ test hai lần save tuần tự rồi kết luận đã test race | Chưa kiểm tra hai transaction cạnh tranh thật | Thêm barrier để cả hai cùng đọc trước khi ghi |
| Test race trong một transaction test chung | Hai lời gọi có thể không độc lập | Dùng hai transaction riêng và xác minh connection/pool |
| Dùng Thread.sleep để tạo race | Test chập chờn theo tải máy | Đồng bộ bằng barrier reactive |
| Pool chỉ có một connection trong test | Transaction đầu giữ connection chờ, transaction sau không tới barrier | Cấp ít nhất hai connection cho race test |
| Chỉ assert exception | Không chứng minh dữ liệu cuối cùng đúng | Đọc lại database và kiểm tra version/trạng thái |
| Retry cùng entity stale | Lặp lại điều kiện version cũ | Đọc lại và áp dụng lại thay đổi |
| Retry mọi exception | Có thể lặp lỗi vĩnh viễn hoặc side effect | Lọc đúng lỗi và giới hạn retry |
| Chỉ SELECT key rồi mới INSERT | Hai request có thể cùng thấy key chưa tồn tại | Unique constraint và atomic claim |
| Cùng idempotency key nhưng payload khác vẫn replay | Trả kết quả sai cho ý định khác | Lưu request hash và từ chối key reuse khác payload |
| Bắt unique violation rồi query trong transaction đã abort | Transaction có thể không còn dùng được | Dùng upsert/ON CONFLICT hoặc xử lý ở transaction mới |
| Chỉ lưu key sau khi tạo order | Crash có thể tạo order trùng trước khi key được ghi | Claim key, tạo resource và lưu kết quả trong cùng transaction |
| Gọi payment gateway trong transaction và retry toàn bộ | Có thể charge nhiều lần | Idempotency key ở gateway và outbox/saga |
| Đánh dấu event processed trước khi cập nhật dữ liệu | Event có thể bị bỏ qua nếu bước ghi lỗi | Cùng transaction cho marker và thay đổi nghiệp vụ |
| Nghĩ exactly-once được bảo đảm bởi message broker | Side effect vẫn có thể lặp ở ranh giới hệ thống | At-least-once + idempotent consumer |
| Dùng database test khác production | Không tái hiện đúng lock/upsert/driver semantics | Integration test trên database và driver mục tiêu |

## 19. Quy trình xây dựng bộ kiểm thử concurrency và idempotency

Có thể triển khai theo trình tự:

1. Xác định các entity có thể được nhiều request cập nhật cùng lúc.
2. Thêm @Version cho entity phù hợp và migration cho cột version.
3. Xác định các bất biến cần được bảo vệ bằng câu SQL atomic hoặc database constraint.
4. Xác định endpoint/command có thể bị client gửi lại sau timeout.
5. Chọn phạm vi idempotency key theo tenant/client và loại operation.
6. Tạo bảng idempotency với unique constraint và request hash.
7. Ghi idempotency record, dữ liệu nghiệp vụ và outbox trong cùng transaction nếu cần.
8. Viết test stale entity với hai bản đọc cùng version.
9. Viết race test có barrier, hai transaction và hai connection độc lập.
10. Kiểm tra trạng thái database sau khi một thao tác thắng và một thao tác conflict.
11. Viết test hai request cùng idempotency key và cùng payload.
12. Viết test cùng key nhưng payload khác.
13. Kiểm thử duplicate event delivery và consumer deduplication.
14. Kiểm tra timeout, cancel, crash/retry và side effect ngoài database.
15. Chạy integration test trên đúng R2DBC driver và database mục tiêu.
16. Theo dõi conflict rate, duplicate key rate, retry count và thời gian xử lý trong production.

## 20. Bài tập tự kiểm tra

### Bài 1: Stale entity

Hai lần đọc cùng một Order đều nhận version 4. Lần đầu save thành công. Lần thứ hai phải nhận kết quả gì?

Gợi ý: Save thứ hai dùng version cũ nên phát OptimisticLockingFailureException. Database giữ thay đổi của lần đầu.

### Bài 2: Race test

Vì sao hai lần save tuần tự không đủ để chứng minh hai transaction cạnh tranh thật?

Gợi ý: Chúng không chạy cùng lúc và không chứng minh hai transaction đã cùng đọc một version trước khi ghi. Dùng barrier sau bước đọc để đồng bộ hai publisher độc lập.

### Bài 3: Connection pool

Race test có hai transaction cùng chờ barrier nhưng pool chỉ có một connection. Điều gì có thể xảy ra?

Gợi ý: Transaction thứ nhất giữ connection trong lúc chờ. Transaction thứ hai không lấy được connection để đọc và tới barrier, khiến test treo.

### Bài 4: Idempotency

Client gửi lại cùng POST request với cùng key sau khi response bị mất. Server nên làm gì?

Gợi ý: Đọc idempotency record và trả lại kết quả đã hoàn tất, không tạo resource mới.

### Bài 5: Payload khác

Hai request dùng cùng idempotency key nhưng request hash khác nhau. Có nên trả kết quả cũ không?

Gợi ý: Không. Đây là việc tái sử dụng key sai mục đích và cần bị từ chối theo hợp đồng API.

### Bài 6: Unique constraint

Vì sao SELECT trước rồi INSERT idempotency key vẫn có race condition?

Gợi ý: Hai transaction có thể cùng SELECT trước khi một transaction INSERT. Unique constraint và thao tác claim nguyên tử mới bảo vệ được cuộc đua.

### Bài 7: Duplicate event

Consumer xử lý event rồi crash trước khi ack. Broker giao lại event. Làm sao tránh áp dụng nghiệp vụ hai lần?

Gợi ý: Lưu event ID trong processed_events với unique constraint và cập nhật marker cùng transaction với side effect database.

### Bài 8: Retry optimistic locking

Có nên gọi retry(3) trên cùng Mono đã chứa entity stale không?

Gợi ý: Không. Mỗi lần retry phải thực hiện lại bước đọc để nhận version mới và áp dụng lại ý định nghiệp vụ.

### Bài 9: Exactly-once

Idempotency record trong database có bảo đảm payment gateway chỉ charge một lần không?

Gợi ý: Không nếu gateway không tham gia cùng transaction. Cần idempotency key được gateway hỗ trợ, truy vấn trạng thái và quy trình đối soát.

### Bài 10: Test rollback

Sau khi một transaction ghi order rồi lỗi khi ghi outbox, cần xác nhận điều gì?

Gợi ý: Cả order và outbox record đều không tồn tại sau rollback. Chỉ assert exception là chưa đủ.

## 21. Ghi nhớ

- Xung đột đồng thời, optimistic locking và idempotency là ba vấn đề liên quan nhưng khác nhau.
- @Version giúp Spring Data phát hiện entity đã thay đổi kể từ lần đọc.
- Test stale entity nên đọc hai bản trước khi save bản thứ nhất, sau đó xác nhận bản thứ hai bị từ chối.
- Race test thực sự cần hai transaction và hai connection độc lập cùng đọc trước khi ghi.
- Dùng barrier reactive thay vì Thread.sleep để đồng bộ thời điểm cạnh tranh.
- Không bọc race test trong một transaction ngoài làm mất tính độc lập của hai request.
- Kiểm tra dữ liệu sau race: chỉ một update thành công, version tăng đúng và trạng thái cuối thuộc request thắng.
- Câu UPDATE có điều kiện giúp bảo vệ bất biến như tồn kho không âm.
- Idempotency key đại diện cho một ý định nghiệp vụ được gửi lại; unique constraint là lớp bảo vệ race quan trọng.
- Lưu request hash để phát hiện cùng key nhưng payload khác.
- Claim key, ghi dữ liệu nghiệp vụ và lưu outbox/kết quả trong cùng transaction khi cần tính nguyên tử.
- Duplicate message cần được xử lý bằng idempotent consumer và processed event ID có unique constraint.
- Retry optimistic locking phải đọc lại entity mới; không retry cùng object stale.
- Timeout không chứng minh side effect bên ngoài chưa xảy ra. Dùng idempotency và đối soát cho các thao tác như thanh toán.
- Exactly-once không tự xuất hiện chỉ nhờ Reactor, R2DBC hay message broker; hãy thiết kế at-least-once delivery với xử lý lặp an toàn.
- Integration test nên dùng đúng database và R2DBC driver mục tiêu để kiểm chứng locking, unique constraint và upsert behavior.

Một bộ kiểm thử tốt không chỉ chứng minh service trả đúng exception. Nó phải tái hiện được hai transaction cạnh tranh, chứng minh database chỉ chấp nhận thay đổi hợp lệ, và xác nhận request hoặc event được gửi lại không tạo thêm tác động nghiệp vụ. Kết hợp @Version, câu lệnh atomic, unique constraint, idempotency key và transaction theo đúng trách nhiệm sẽ giúp ứng dụng R2DBC xử lý concurrency và retry một cách có thể dự đoán.

