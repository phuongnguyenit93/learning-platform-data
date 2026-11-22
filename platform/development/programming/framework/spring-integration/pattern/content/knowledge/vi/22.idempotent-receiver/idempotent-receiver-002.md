# Message ID và idempotency key

## 1. Tại sao một message có thể được xử lý nhiều lần?

Trong hệ thống tích hợp, một broker hoặc adapter có thể giao lại **cùng một sự kiện nghiệp vụ** nếu acknowledgment bị mất, consumer crash hoặc retry được kích hoạt. Đây là điều thường gặp trong các luồng có tính chất **at-least-once delivery**.

Giả sử dịch vụ thanh toán nhận yêu cầu thu tiền cho đơn `ORD-1001`:

~~~text
10:00:00  Consumer nhận PAYMENT_REQUESTED.
10:00:01  Payment API đã thu tiền thành công.
10:00:02  Consumer crash trước khi ack broker.
10:00:05  Broker giao lại message.
10:00:06  Consumer gọi Payment API một lần nữa?
~~~

Nếu consumer xem mỗi lần nhận là một lệnh mới, khách hàng có thể bị thu tiền hai lần. Mẫu **Idempotent Receiver** giúp consumer nhận ra rằng một thao tác **đã được thực hiện hoặc đã có kết quả có thẩm quyền**, để việc giao lại không nhân đôi tác động nghiệp vụ.

Điểm khó là: **Message ID của framework không nhất thiết là idempotency key phù hợp với nghiệp vụ.** Message có thể được tạo lại khi đi qua Transformer, adapter hoặc lúc retry, trong khi thao tác thanh toán vẫn là một operation duy nhất.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant R as Receiver
    participant L as Operation Ledger
    participant P as Payment Service
    B->>R: Delivery #1, operationId=PAY-1001
    R->>L: Find operation PAY-1001
    L-->>R: Not completed
    R->>P: Charge, idempotency-key=PAY-1001
    P-->>R: SUCCESS
    R->>L: Record COMPLETED + receipt
    Note over R,B: Ack bị mất / consumer crash
    B->>R: Delivery #2, operationId=PAY-1001
    R->>L: Find operation PAY-1001
    L-->>R: COMPLETED + receipt
    Note over R: Không charge lần hai
~~~

Sơ đồ thể hiện **kết quả mong muốn**, không tự khẳng định một database ledger và một Payment API luôn cập nhật nguyên tử. Phần xử lý crash và kết quả **UNKNOWN** sẽ được giải thích riêng.

Bài học thuộc chương **Idempotent receiver** của module `SPRING_INTEGRATION_PATTERN`: học triển khai Enterprise Integration Patterns bằng Spring Integration để tạo message flow ít phụ thuộc, dễ mở rộng; kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, kiểm thử và quan sát các nhánh xử lý.

### Mục tiêu bài học

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **Spring Message ID**, **event ID**, **delivery ID**, **correlation ID**, **trace ID** và **business idempotency key**.
2. Chọn đúng phạm vi idempotency theo **tenant, consumer/operation, business intent và version**.
3. Hiểu vì sao một message có ID mới vẫn có thể là duplicate và hai message có cùng business entity chưa chắc là duplicate.
4. Thiết kế idempotent handler với **durable inbox/operation ledger**, trạng thái, fingerprint và receipt.
5. Biết giới hạn của `IdempotentReceiverInterceptor`, `MetadataStoreSelector` và `ConcurrentMetadataStore` khi xử lý side effect.
6. Xác định retry, crash, duplicate, concurrent consumers, timeout và late replies cần được kiểm thử thế nào.
7. Kết hợp Idempotent Receiver với các EIP khác mà không làm mất metadata hoặc che lỗi nghiệp vụ.

## 2. Message ID không phải lúc nào cũng là idempotency key

### 2.1. Các loại ID trong một integration flow

| Định danh | Nó xác định điều gì? | Dùng để làm gì? |
|---|---|---|
| **Spring `MessageHeaders.ID`** | Một Spring `Message<?>` cụ thể trong quá trình xử lý. | Trace/debug identity của message trong framework. |
| **Business `eventId`** | Một lần phát sinh sự kiện nghiệp vụ tại nguồn. | Dedupe một sự kiện được giao nhiều lần. |
| **Business `operationId`** | Một hành động nghiệp vụ được yêu cầu, ví dụ một lần charge đơn hàng. | Idempotency của side effect hoặc API command. |
| **Broker record coordinate** | Vị trí record trong topic/partition/offset hoặc envelope tương đương. | Điều tra transport, consumer offset và redelivery. |
| **Delivery/attempt ID** | Một lần giao hoặc một lần thử. | Debug retry, latency, failure attempt. |
| **`correlationId`** | Nhóm các messages liên quan hoặc một request–reply conversation. | Splitter/Aggregator/Gateway correlation. |
| **`traceId`/`spanId`** | Luồng quan sát phân tán. | Tracing giữa service và thread. |
| **`claimId`** | Tham chiếu đến payload trong Claim Check store. | Khôi phục dữ liệu; không nhất thiết bảo vệ side effect. |
| **`sequenceNumber`** | Vị trí trong một chuỗi message. | Resequencer/Aggregator sequence semantics. |

**Không có một ID nào tự thay thế tất cả các ID khác.** Cần xác định “**thao tác nào phải chỉ có tác động một lần**” trước khi chọn khóa.

### 2.2. Message ID có thể đổi dù nội dung nghiệp vụ không đổi

Một message mới do `MessageBuilder` tạo thường có ID do framework cấp:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> first =
        MessageBuilder.withPayload("PAY-ORD-1001").build();

Message<String> rebuilt =
        MessageBuilder.withPayload(first.getPayload()).build();

// Một message mới thông thường có MessageHeaders.ID mới.
// Nhưng business operation vẫn là PAY-ORD-1001.
~~~

Ngay cả khi payload giống nhau, không nên kỳ vọng `first.getHeaders().getId()` và `rebuilt.getHeaders().getId()` luôn bằng nhau. Framework, adapter và cách dựng message quyết định metadata nào được bảo tồn hoặc sinh lại. Nếu chỉ dedupe theo ID này, một **business duplicate** có thể lọt qua.

### 2.3. Một message ID cũng không phải bằng chứng payment chưa chạy

Ví dụ broker redelivery có thể giữ nguyên ID ở envelope hoặc tạo lại Spring message với ID mới. Dù thế nào, một handler cần tra trạng thái **operationId=PAY-ORD-1001** ở nơi chịu trách nhiệm side effect. Việc compare Message ID **không thể xác nhận external payment đã commit hay chưa**.

### 2.4. Cùng orderId không có nghĩa cùng operation

~~~text
Order ORD-1001:
  CHARGE initial amount=100000
  REFUND partial amount=20000
  CHARGE adjustment amount=5000
~~~

Nếu khóa dedupe chỉ là `orderId`, thao tác REFUND hợp lệ có thể bị coi là trùng với CHARGE ban đầu. Khóa nên phản ánh **loại thao tác và lần thực hiện**:

~~~text
TENANT-A / PAYMENTS / CHARGE-ORD-1001-V1
TENANT-A / PAYMENTS / REFUND-ORD-1001-R1
TENANT-A / PAYMENTS / CHARGE-ORD-1001-ADJUST-1
~~~

Đây là **giá trị ví dụ**, không phải format bắt buộc. Ở hệ thống thật, operation ID phải đến từ một nguồn có thẩm quyền và có quy tắc cấp duy nhất, không ghép chuỗi tùy ý từ các field người dùng có thể giả mạo.

## 3. Câu hỏi quan trọng nhất: “Giống nhau” ở cấp nào?

### 3.1. Event deduplication

Một sự kiện `OrderPaid(eventId=EVT-23)` được giao ba lần do broker retry. Một consumer cập nhật projection có thể cần chỉ áp dụng **EVT-23 một lần**.

~~~text
eventId=EVT-23, delivery#1
eventId=EVT-23, delivery#2
eventId=EVT-23, delivery#3

idempotency identity = (consumerName, tenantId, eventId)
~~~

Nếu hai consumer khác nhau đều phải xử lý `EVT-23` — ví dụ BillingProjection và NotificationService — việc Projection đã xử lý không được ngăn Notification nhận sự kiện hợp lệ. Vì vậy khóa cần **scope theo consumer** nếu các side effect khác nhau.

### 3.2. Command/operation idempotency

Một API `ChargePayment` có thể bị gọi lại với operation ID cố định khi HTTP timeout:

~~~text
operationId=CHARGE-456, attempt=1 -> timeout
operationId=CHARGE-456, attempt=2 -> same business action
~~~

Ở đây business operation key quan trọng hơn event ID của message transport. Nếu caller gửi cùng operationId nhưng **amount khác**, đó có thể là **key conflict**, không phải duplicate an toàn.

### 3.3. State-based idempotency

Một số handler vốn có thể idempotent nhờ state:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = ? AND status = 'PENDING';
~~~

Lệnh trên có thể không áp dụng lần hai nếu điều kiện đã thay đổi. Nhưng nó **chưa tự bảo vệ** những side effect khác như gửi email, gọi payment hay ghi audit. Và nếu trạng thái `PAID` có thể chuyển đi rồi quay lại `PENDING`, cần business version/transition ID để tránh replay lệnh cũ.

### 3.4. Kết quả có phải giữ nguyên không?

**Idempotent side effect** nghĩa là gọi lại cùng operation không tạo tác động nghiệp vụ mới. Một API cũng có thể chọn **trả lại receipt cũ** để caller không thấy kết quả mâu thuẫn.

Phân biệt:

- **At-most-one side effect:** không charge hai lần.
- **Stable response:** retry nhận cùng receipt/operation state.
- **Deterministic payload:** toàn bộ response từng byte giống nhau.

Không phải lúc nào ba yêu cầu cũng tương đương. Timestamp quan sát có thể khác giữa các lần retry, nhưng **idempotency key và business outcome cuối** phải nhất quán theo contract.

## 4. Tiêu chí chọn idempotency key tốt

### 4.1. Các tính chất cần có

Một khóa tốt nên:

1. **Ổn định giữa các lần giao/retry cùng thao tác.**
2. **Phân biệt các thao tác hợp lệ khác nhau** trên cùng business entity.
3. **Có scope rõ** theo tenant và consumer/operation.
4. **Được cấp bởi nguồn có thẩm quyền** hoặc kiểm chứng được tại ingress.
5. **Không phụ thuộc timestamp nhận hoặc Spring Message ID mới.**
6. **Có thể lưu lâu hơn retry/redelivery horizon** theo retention policy.
7. **Có cách phát hiện same key nhưng payload khác** qua fingerprint hoặc contract validation.
8. **Không tiết lộ dữ liệu nhạy cảm** không cần thiết khi xuất hiện trong logs/headers.

### 4.2. Key tốt và key rủi ro

| Khóa | Đánh giá | Lý do |
|---|---|---|
| `tenantId + service + operationId` | Tốt nếu các thành phần có nguồn đáng tin. | Phân biệt tenant, operation và consumer. |
| `tenantId + eventId + consumerId` | Tốt cho event receiver. | Một event xử lý một lần cho mỗi consumer. |
| `orderId` | Thường không đủ. | Một đơn có nhiều operation/versions. |
| `payload.toString()` | Không an toàn. | Format không ổn định, không đảm bảo canonicalization. |
| `MessageHeaders.ID` | Không đủ cho business effect. | Có thể đổi khi message được tạo lại. |
| `traceId` | Không phù hợp. | Một trace có thể chứa nhiều operations. |
| `correlationId` | Không mặc định. | Có thể gom nhiều child messages của Splitter. |
| `sequenceNumber` | Sai khi đứng một mình. | Cùng số thứ tự ở nhiều group. |
| `System.currentTimeMillis()` khi nhận | Sai. | Mỗi retry tạo khóa mới. |
| `broker offset` | Chỉ có ích trong bối cảnh cụ thể. | Không ổn định nếu event được republish thành record mới. |

### 4.3. Composite key nên là cấu trúc, không nối chuỗi tùy tiện

Trong database, ưu tiên composite unique key:

~~~sql
UNIQUE (tenant_id, consumer_name, operation_id)
~~~

Một chuỗi `tenant + ":" + operation` có thể bị va chạm nếu các thành phần chứa dấu phân cách. Nếu cần lưu vào `ConcurrentMetadataStore` nhận khóa String, hãy dùng **encoding không mơ hồ** hoặc encode các thành phần đã validation:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

final class IdempotencyKeys {
    private static String segment(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("EMPTY_ID_COMPONENT");
        }
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(
                        value.getBytes(StandardCharsets.UTF_8));
    }

    static String forOperation(
            String tenantId,
            String consumerName,
            String operationId) {
        return segment(tenantId) + "."
                + segment(consumerName) + "."
                + segment(operationId);
    }
}
~~~

Đây là **canonical encoding cho tổ hợp các chuỗi đã được tin cậy**, không phải ký số hay mã hóa bí mật. Base64 URL-safe chỉ làm các thành phần phân tách không mơ hồ; nó **không ẩn PII, không chống giả mạo**. Nếu token/key đi qua trust boundary, cần authentication, authorization và integrity protection tương ứng.

### 4.4. Key có version và consumer scope

Một hệ thống có thể đổi logic handler:

~~~text
Projection v1 consumes EVT-23
Projection v2 replays EVT-23 to rebuild state
~~~

Nếu dùng cùng inbox key của v1, v2 có thể bị chặn toàn bộ replay. Ngược lại, nếu vô tình thêm version vào key của **payment charge**, deploy v2 có thể tạo một charge mới cho operation cũ. Vì vậy:

- **Projection rebuild:** có thể có `consumerName/version` hoặc namespace mới được phê duyệt.
- **Business side effect:** giữ cùng operation key qua deploy, trừ khi thực sự là một operation mới.
- **Key migration:** có kế hoạch đọc state cũ, không tự đổi namespace rồi coi mọi message là mới.

### 4.5. Payload fingerprint để phát hiện key reuse sai

Ví dụ cùng `CHARGE-456`:

~~~text
Attempt 1: amountVnd=100000, currency=VND
Attempt 2: amountVnd=900000, currency=VND
~~~

Lần hai không nên nhận “SUCCESS cũ” một cách mù quáng. Hãy lưu fingerprint của **các field business định nghĩa operation**, rồi reject hoặc điều tra khi key giống nhưng fingerprint khác.

Không lấy fingerprint bằng Java `Object.hashCode()`, vì không bảo đảm ổn định xuyên tiến trình/version. Cần canonical serialization với schema version, currency, amount representation, normalization và chính sách bảo mật; `SHA-256` của dữ liệu đã canonicalize có thể là một lựa chọn kỹ thuật, nhưng hash **không thay authorization**.

## 5. Mô hình Java: idempotency key gắn với business operation

Ví dụ hướng tới **Java 17+, Spring Boot 3.x và Spring Integration 6.x**. Các type được hiểu là nằm cùng package; khi dùng trong dự án hãy tách các `public` type ra file phù hợp. Business rule thanh toán ở đây **chỉ là mô phỏng**, không phải tích hợp cổng thanh toán thực.

### 5.1. Lệnh thanh toán có ID rõ ràng

~~~java
import java.math.BigDecimal;
import java.util.Objects;

record ChargeCommand(
        String tenantId,
        String operationId,
        String orderId,
        BigDecimal amountVnd) {

    ChargeCommand {
        if (tenantId == null || tenantId.isBlank()
                || operationId == null || operationId.isBlank()
                || orderId == null || orderId.isBlank()
                || amountVnd == null
                || amountVnd.signum() <= 0) {
            throw new IllegalArgumentException(
                    "INVALID_CHARGE_COMMAND");
        }
    }
}

record OperationKey(
        String tenantId,
        String consumerName,
        String operationId) {
    OperationKey {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(consumerName);
        Objects.requireNonNull(operationId);
    }
}

record ChargeReceipt(
        String operationId,
        String paymentReference,
        String status) {}
~~~

Các trường có vai trò khác nhau:

- `tenantId` ngăn nhầm dữ liệu giữa tenant.
- `operationId` cố định giữa những lần retry **cùng một thao tác charge**.
- `orderId` xác định order, nhưng một order có thể có nhiều charges/refunds hợp lệ.
- `amountVnd` là dữ liệu business phải được kiểm tra để phát hiện **same key, different payload**.
- `consumerName` là scope của receiver, ở ví dụ này có thể cố định `PAYMENT_CHARGE`.

### 5.2. Fingerprint có chủ đích

Với mô hình tiền VND minh họa, ta dùng canonical tuple của `orderId` và `amountVnd`. Một production system cần canonical schema version và validate currency/scale đúng nghiệp vụ; demo dưới đây **không dùng hash mật mã**.

~~~java
final class ChargeFingerprint {
    static String of(ChargeCommand command) {
        return IdempotencyKeys.forOperation(
                command.tenantId(),
                command.orderId(),
                command.amountVnd()
                        .stripTrailingZeros()
                        .toPlainString());
    }
}
~~~

Việc tạo fingerprint từ dữ liệu business giúp:

~~~text
same operationId + same fingerprint
  -> duplicate / retry hợp lệ

same operationId + different fingerprint
  -> OPERATION_CONFLICT
~~~

**Không mặc định mọi field đều nên đưa vào fingerprint.** Ví dụ request timestamp, tracing metadata hay deliveryAttempt có thể thay đổi hợp lệ giữa các lần retry. Ngược lại, amount/currency/customer/merchant scope là những field quan trọng với payment. Chính sách chọn field cần được ghi rõ và version hóa.

### 5.3. Một fake receiver giữ receipt cho duplicate

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

record StoredChargeOutcome(
        String fingerprint,
        ChargeReceipt receipt) {}

final class InMemoryIdempotentChargeReceiver {
    private static final String CONSUMER = "PAYMENT_CHARGE";

    private final ConcurrentMap<OperationKey, StoredChargeOutcome> done =
            new ConcurrentHashMap<>();

    private final AtomicInteger appliedCharges =
            new AtomicInteger();

    ChargeReceipt handle(ChargeCommand command) {
        OperationKey key = new OperationKey(
                command.tenantId(), CONSUMER, command.operationId());
        String fingerprint = ChargeFingerprint.of(command);

        StoredChargeOutcome result = done.compute(key, (ignored, old) -> {
            if (old != null) {
                if (!old.fingerprint().equals(fingerprint)) {
                    throw new IllegalStateException(
                            "OPERATION_CONFLICT");
                }
                return old;
            }

            // Fake in-memory effect: không gọi HTTP/DB bên ngoài.
            int number = appliedCharges.incrementAndGet();
            ChargeReceipt receipt = new ChargeReceipt(
                    command.operationId(),
                    "SIMULATED-PAYMENT-" + number,
                    "SUCCESS");
            return new StoredChargeOutcome(fingerprint, receipt);
        });

        return result.receipt();
    }

    int appliedCount() {
        return appliedCharges.get();
    }
}
~~~

**Tại sao dùng `ConcurrentHashMap.compute`?** Trong fake, thao tác tra key, so fingerprint và tạo receipt được serialize tương ứng key trong cùng JVM; các thread chạy đồng thời cùng key không tự tạo hai entry thành công.

**Tại sao tuyệt đối không sao chép nguyên cách này sang Payment API thật?**

- Mapping function của `compute` không phải transaction với cổng thanh toán ngoài.
- Nếu JVM crash, map và receipt đều mất.
- Remote call có thể commit rồi trả timeout; map không biết outcome.
- Multiple JVMs không chia sẻ một map duy nhất.
- Một lần `compute` lâu có thể khóa/chặn xử lý khác trong cùng vùng cấu trúc dữ liệu.

Với side effect thật, dùng **durable operation ledger**, locking/unique constraints và **idempotency ngay tại hệ thống tạo side effect**, hoặc reconciliation thích hợp. `compute` ở đây chỉ là một fixture học tập để thấy cấu trúc key và duplicate behavior.

### 5.4. So sánh với dedupe theo Spring Message ID

Giả sử consumer dùng:

~~~java
String seenKey = message.getHeaders().getId().toString();
~~~

Nếu một Transformer tạo message khác mà vẫn mang `operationId=PAY-1001`, `seenKey` có thể khác nên receiver không thấy duplicate. Thay vào đó:

~~~java
ChargeCommand payload = (ChargeCommand) message.getPayload();
OperationKey key = new OperationKey(
        payload.tenantId(),
        "PAYMENT_CHARGE",
        payload.operationId());
~~~

Đó là một **business operation identity**, không phụ thuộc instance ID của Spring message.

## 6. Kiểm thử JUnit 5 cho idempotency key

### 6.1. Cùng operation, nhiều lần nhận: chỉ một fake charge

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class IdempotentChargeSuccessTest {

    @Test
    void sameOperationReturnsOriginalReceipt() {
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();

        ChargeCommand command = new ChargeCommand(
                "TENANT-A",
                "CHARGE-1001",
                "ORD-1001",
                new BigDecimal("100000"));

        ChargeReceipt first = receiver.handle(command);
        ChargeReceipt second = receiver.handle(command);
        ChargeReceipt third = receiver.handle(command);

        assertEquals(first, second);
        assertEquals(first, third);
        assertEquals(1, receiver.appliedCount());
    }
}
~~~

Test xác nhận fake trả receipt cũ khi cùng operation được giao ba lần; nó **không** chứng minh external payment provider có exactly-once.

### 6.2. Cùng order nhưng hai operations khác nhau

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class DifferentOperationTest {
    @Test
    void separateOperationsOnSameOrderAreNotDeduplicated() {
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();

        ChargeCommand initial = new ChargeCommand(
                "TENANT-A", "CHARGE-INIT", "ORD-1",
                new BigDecimal("100000"));
        ChargeCommand adjustment = new ChargeCommand(
                "TENANT-A", "CHARGE-ADJUST", "ORD-1",
                new BigDecimal("5000"));

        ChargeReceipt a = receiver.handle(initial);
        ChargeReceipt b = receiver.handle(adjustment);

        assertNotEquals(a.paymentReference(), b.paymentReference());
        assertEquals(2, receiver.appliedCount());
    }
}
~~~

Nếu chỉ dedupe theo `orderId`, test này sẽ fail vì thao tác điều chỉnh bị bỏ nhầm.

### 6.3. Cùng operation ID nhưng amount khác phải conflict

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OperationConflictTest {
    @Test
    void sameKeyWithDifferentPayloadIsNotSafeDuplicate() {
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();

        receiver.handle(new ChargeCommand(
                "TENANT-A", "CHARGE-1", "ORD-1",
                new BigDecimal("100000")));

        IllegalStateException error = assertThrows(
                IllegalStateException.class, () ->
                        receiver.handle(new ChargeCommand(
                                "TENANT-A", "CHARGE-1", "ORD-1",
                                new BigDecimal("900000"))));

        assertEquals("OPERATION_CONFLICT", error.getMessage());
        assertEquals(1, receiver.appliedCount());
    }
}
~~~

Lỗi này khác một duplicate hợp lệ. Không nên xử lý bằng cách lấy receipt cũ bất chấp amount mới, và không nên tự động cấp operation ID mới nếu caller không có quyền tạo một charge mới.

### 6.4. Hai tenants dùng cùng local operation ID

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TenantIsolationTest {
    @Test
    void sameOperationLabelAcrossTenantsHasIndependentScope() {
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();

        receiver.handle(new ChargeCommand(
                "TENANT-A", "CHARGE-1", "ORD-1",
                new BigDecimal("100000")));
        receiver.handle(new ChargeCommand(
                "TENANT-B", "CHARGE-1", "ORD-1",
                new BigDecimal("100000")));

        assertEquals(2, receiver.appliedCount());
    }
}
~~~

Một khóa thiếu tenant có thể khiến yêu cầu hợp lệ của tenant B bị chặn bởi trạng thái của tenant A. Ngược lại, việc thêm tenant vào key không thay thế **ủy quyền tenant thực sự**; client không được tự chọn tenant ID để truy cập record của người khác.

### 6.5. Hai thread cùng nhận một operation

~~~java
import java.math.BigDecimal;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ConcurrentDuplicateTest {
    @Test
    void twoThreadsSeeSameFakeReceipt() throws Exception {
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();
        ChargeCommand command = new ChargeCommand(
                "TENANT-A", "CHARGE-1", "ORD-1",
                new BigDecimal("100000"));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        try {
            Future<ChargeReceipt> a = pool.submit(() -> {
                start.await();
                return receiver.handle(command);
            });
            Future<ChargeReceipt> b = pool.submit(() -> {
                start.await();
                return receiver.handle(command);
            });
            start.countDown();

            assertEquals(a.get(), b.get());
            assertEquals(1, receiver.appliedCount());
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Một concurrency test trên một JVM giúp phát hiện race ở fake. Với nhiều pods/instances, phải có **integration test** dùng chung persistent ledger/remote idempotency boundary, không chỉ tin `ConcurrentHashMap`.

## 7. Tại sao bảng “đã thấy message” chưa đủ để xử lý an toàn?

### 7.1. Ghi “SEEN” trước khi làm business work

Một receiver đơn giản có thể làm:

~~~text
if seenStore.putIfAbsent(key, "SEEN") == null:
    chargePayment()
else:
    skip()
~~~

Giả sử:

~~~text
T1  Record SEEN được ghi thành công.
T2  Worker crash trước khi gọi Payment.
T3  Broker redeliver cùng operation.
T4  Receiver thấy SEEN nên skip.
~~~

Kết quả: **không có charge**, nhưng duplicate bị bỏ qua. Đây là failure mode **at-most-once attempt**, không đủ cho yêu cầu xử lý có kết quả cuối rõ ràng.

### 7.2. Ghi “SEEN” sau khi làm business work

Đảo thứ tự:

~~~text
T1  Payment charge SUCCESS.
T2  Worker crash trước khi ghi SEEN.
T3  Broker redeliver.
T4  Receiver không thấy key, gọi Payment lần hai.
~~~

Kết quả: **có nguy cơ charge hai lần**. Đặt check **trước** hay **sau** không tự giải quyết vấn đề crash nằm giữa hai thao tác độc lập.

### 7.3. Ba nhóm trạng thái không nên nhập nhằng

| Trạng thái | Ý nghĩa | Hành động khi duplicate đến |
|---|---|---|
| **COMPLETED** | Business outcome đã được xác nhận và lưu có thẩm quyền. | Trả receipt cũ hoặc acknowledge/skip theo contract. |
| **IN_PROGRESS** | Một attempt đang được xử lý hoặc giữ lease. | Chờ, trả PENDING hoặc điều phối retry; không khởi động side effect mới một cách mù quáng. |
| **UNKNOWN** | Side effect có thể đã commit nhưng receipt bị mất. | Reconcile với nguồn có thẩm quyền trước khi retry. |

Những trạng thái khác có thể có:

- `RECEIVED`: message đã đi vào inbox nhưng chưa bắt đầu.
- `FAILED_RETRYABLE`: chưa hoàn tất, có thể retry theo policy.
- `FAILED_FINAL`: kết quả lỗi cuối, không tự thử lại.
- `REJECTED_CONFLICT`: same key, fingerprint khác.
- `CANCELLED`: đã hủy theo quyền/policy; không tự mở lại bằng redelivery.

**Một string `SEEN` không mang đủ ngữ nghĩa** để xử lý tất cả những trường hợp trên.

### 7.4. State machine tham khảo

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> IN_PROGRESS: acquire operation
    IN_PROGRESS --> COMPLETED: commit confirmed
    IN_PROGRESS --> FAILED_RETRYABLE: known transient failure
    FAILED_RETRYABLE --> IN_PROGRESS: authorized retry
    IN_PROGRESS --> UNKNOWN: outcome uncertain
    UNKNOWN --> COMPLETED: reconciled committed
    UNKNOWN --> FAILED_RETRYABLE: reconciled not committed
    RECEIVED --> REJECTED_CONFLICT: fingerprint mismatch
    COMPLETED --> [*]
    REJECTED_CONFLICT --> [*]
~~~

Đây là **mô hình nghiệp vụ/điều phối**, không phải state machine được Spring Integration tự sinh chỉ bằng một annotation.

## 8. Durable inbox/operation ledger

### 8.1. Schema tối thiểu có khóa duy nhất

Ví dụ PostgreSQL-style SQL để diễn tả contract:

~~~sql
CREATE TABLE processed_operations (
    tenant_id          VARCHAR(120) NOT NULL,
    consumer_name      VARCHAR(120) NOT NULL,
    operation_id       VARCHAR(200) NOT NULL,
    payload_fingerprint VARCHAR(200) NOT NULL,
    status             VARCHAR(40) NOT NULL,
    receipt_json       TEXT,
    created_at         TIMESTAMPTZ NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, consumer_name, operation_id)
);
~~~

**Primary key** bảo vệ tính duy nhất của business operation trong phạm vi được chọn. Nhưng nó **không tự bảo vệ** remote HTTP side effect khi record và payment nằm ở hai hệ thống khác nhau.

Với audit và recovery có thể cần thêm:

- `attempt_count`, `last_error_code`, `next_retry_at`.
- `lease_owner`, `lease_until`, `fencing_version`.
- `external_payment_reference`.
- `result_version`, `schema_version`.
- `expires_at`/retention metadata.
- Chỉ lưu fingerprint/receipt đã được phê duyệt, không tùy tiện lưu dữ liệu cá nhân.

### 8.2. Cùng DB transaction: áp dụng business update + lưu receipt

Nếu business side effect **cũng nằm trong cùng database transaction**, có thể thực hiện:

~~~text
BEGIN TRANSACTION

1. INSERT inbox key (tenant, consumer, operation)
   ON CONFLICT DO NOTHING
2. SELECT operation row FOR UPDATE
3. Nếu COMPLETED:
     - fingerprint khớp -> trả receipt đã lưu
     - fingerprint khác -> OPERATION_CONFLICT
4. Nếu đủ điều kiện xử lý:
     - thực hiện business mutation trong cùng DB
     - lưu receipt và status=COMPLETED
5. COMMIT
~~~

Ví dụ cú pháp PostgreSQL:

~~~sql
INSERT INTO processed_operations (
    tenant_id, consumer_name, operation_id,
    payload_fingerprint, status, created_at, updated_at
)
VALUES (
    :tenant, :consumer, :operation,
    :fingerprint, 'RECEIVED', CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, consumer_name, operation_id)
DO NOTHING;

SELECT status, payload_fingerprint, receipt_json
FROM processed_operations
WHERE tenant_id = :tenant
  AND consumer_name = :consumer
  AND operation_id = :operation
FOR UPDATE;
~~~

**Đây là skeleton SQL**, không phải transaction hoàn chỉnh để copy chạy ngay. Cần xử lý row locking, isolation level, lỗi unique constraint, deadlock, response serialization và quyền truy cập. Không gọi remote Payment API trong cùng DB transaction rồi tự suy rằng payment đã được rollback nếu DB rollback.

### 8.3. Khi side effect nằm ngoài database

~~~mermaid
flowchart TD
    M[Command message] --> L[(Durable Operation Ledger)]
    L -->|COMPLETED| R[Return stored receipt]
    L -->|RECEIVED / safe to start| P[External Payment API]
    P -->|Success receipt| C[Persist COMPLETED]
    P -->|Timeout / unknown| U[Mark UNKNOWN]
    U --> Q[Query/reconcile external status]
    Q -->|Already committed| C
    Q -->|Definitely not committed| RET[Retry with same idempotency key]
    RET --> P
~~~

Ba điểm cần bảo vệ:

1. **Cùng operation key tới external API** nếu nhà cung cấp hỗ trợ idempotency.
2. **Không retry mù khi kết quả UNKNOWN**; hỏi trạng thái/reconcile trước khi gọi lại.
3. **Dùng ledger bền vững và concurrency control** để nhiều consumer không tạo hai requests độc lập khi cùng key.

Nếu external service không hỗ trợ idempotency lẫn status query, hệ thống không thể hứa exactly-once bằng vài dòng Spring Integration config. Cần thiết kế nghiệp vụ bù trừ/manual reconciliation hoặc thay đổi hợp đồng.

### 8.4. “Exactly-once” là phạm vi nào?

Một broker có thể cung cấp những cơ chế xử lý giao dịch nhất định cho **broker records**; một database có unique key; một payment service có idempotency header. Nhưng “exactly-once” phải nói rõ **qua ranh giới nào**:

| Phạm vi | Có thể bảo đảm gì? |
|---|---|
| Inbox insert trong một DB | Unique operation record theo primary key. |
| Cùng DB transaction | Business mutation + receipt có thể atomic nếu cả hai cùng transaction. |
| Broker consume → broker publish | Có thể có transaction/offset semantics theo broker/config. |
| Broker → remote HTTP payment | Không tự atomic; cần remote idempotency/reconciliation. |
| Payment → email notification | Có thể cần outbox, duplicate-safe notification, workflow state. |

**Idempotent Receiver không biến toàn bộ mạng lưới service thành một transaction phân tán.** Nó là một trong các cơ chế giúp xử lý redelivery một cách có kiểm soát.

## 9. Các tình huống failure cần diễn giải riêng

### 9.1. Ack bị mất sau commit

~~~text
Consume event E1
  -> commit business change + receipt
  -> ack broker (ack lost)

Broker redeliver E1
  -> receiver reads COMPLETED
  -> return previous receipt or skip expected side effect
  -> acknowledge duplicate
~~~

Đây là tình huống Idempotent Receiver giải quyết tốt **nếu có record bền vững** được lưu trước ack theo contract.

### 9.2. Crash khi IN_PROGRESS

~~~text
Receiver A:
  -> claim operation key
  -> status IN_PROGRESS
  -> crash

Receiver B:
  -> sees IN_PROGRESS
~~~

Receiver B không nên chờ vô hạn, nhưng cũng không nên tự coi operation đã thất bại. Có thể dùng lease deadline, heartbeat và fencing; khi lease hết hạn, **khả năng worker A còn sống hoặc side effect đã commit** phải được giải quyết theo hệ thống đích.

### 9.3. Hai workers đồng thời

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant L as Ledger
    participant X as External API
    A->>L: Claim operation OP-1
    B->>L: Claim operation OP-1
    L-->>A: Lease/fence=10
    L-->>B: Already IN_PROGRESS
    A->>X: Request idempotencyKey=OP-1
    X-->>A: SUCCESS
    A->>L: Commit COMPLETED with fence=10
    Note over B: Không tạo business operation mới
~~~

Sơ đồ là **hợp đồng mong muốn**. Việc ledger trả lease/fence phải được triển khai bằng transaction/CAS có tính nhất quán phù hợp, không phải chỉ bằng một `SELECT` rồi `UPDATE` không kiểm soát race.

### 9.4. Key trùng nhưng payload mâu thuẫn

Nếu có receipt cũ:

~~~text
operationId=OP-1
fingerprint=F1
status=COMPLETED
~~~

và message mới có `operationId=OP-1` nhưng fingerprint `F2`, không nên trả receipt F1 như một duplicate hợp lệ hoặc tạo operation mới im lặng. Kết quả nên là **OPERATION_CONFLICT**, với audit và điều tra nếu liên quan payment/tenant.

### 9.5. Late reply từ attempt cũ

Ví dụ attempt 1 timeout, attempt 2 bắt đầu, rồi response của attempt 1 đến muộn. Nếu ledger nhận cả hai:

- Không để status cũ `FAILED_RETRYABLE` ghi đè `COMPLETED`.
- Dùng version/fencing hoặc state transition guard.
- Phân biệt **attempt ID** (đổi mỗi lần thử) với **operation ID** (giữ nguyên).
- Nếu hai external references xuất hiện cho cùng key, cần reconciliation chứ không tùy ý chọn kết quả mới nhất.

### 9.6. Delete dedupe record quá sớm

~~~text
Idempotency record TTL = 5 phút
Broker redelivery / DLQ replay horizon = 24 giờ
~~~

Một duplicate sau 2 giờ có thể không thấy key và bị xem là mới. Retention phải phù hợp **horizon mà cùng operation có thể được replay** và yêu cầu bảo mật/dữ liệu. Nếu cần giữ tombstone dài hơn payload gốc, hãy tách metadata tối thiểu khỏi dữ liệu nhạy cảm.

## 10. Idempotent Receiver trong Spring Integration

### 10.1. Hai cách tích hợp thường gặp

Với Spring Integration, có thể triển khai pattern ở hai mức:

1. **Tại message handler/service**: handler tra durable ledger, phân loại duplicate/conflict và trả receipt cũ hoặc thực hiện operation.
2. **Tại endpoint advice**: dùng `IdempotentReceiverInterceptor` kết hợp `MessageSelector`/`MetadataStoreSelector` để phát hiện những message có khóa đã gặp, sau đó đánh dấu, discard hoặc xử lý theo cấu hình.

Cách 2 rất hữu ích cho **lọc/thông báo duplicate ở endpoint**, nhưng **không tự thay thế** business ledger và external idempotency khi xử lý thanh toán, ghi đơn hoặc tạo side effect có rủi ro.

### 10.2. Flow Java DSL với receiver theo business key

Đây là ví dụ tự chứa dùng fake receiver trong `Spring Integration Java DSL`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@MessagingGateway
interface ChargeGateway {
    @Gateway(
            requestChannel = "payment.command.input",
            replyTimeout = 5000)
    ChargeReceipt charge(ChargeCommand command);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class IdempotentReceiverFlowConfiguration {

    @Bean(name = "payment.command.input")
    MessageChannel paymentCommandInput() {
        return new DirectChannel();
    }

    @Bean
    InMemoryIdempotentChargeReceiver chargeReceiver() {
        return new InMemoryIdempotentChargeReceiver();
    }

    @Bean
    IntegrationFlow chargeFlow(
            InMemoryIdempotentChargeReceiver receiver) {
        return IntegrationFlow.from("payment.command.input")
                .handle(ChargeCommand.class,
                        (command, headers) -> receiver.handle(command))
                .get();
    }
}
~~~

Flow này tạo một request–reply handler nhận `ChargeCommand` và trả `ChargeReceipt`. Việc xử lý duplicate nằm **trong service**, dựa trên `tenantId + consumerName + operationId`, chứ không dựa trên `MessageHeaders.ID`.

**Giới hạn demo:** `InMemoryIdempotentChargeReceiver` là fake; Spring context restart thì map mất, còn ngoại vi chưa có side effect thật. Với production, thay handler bằng service có **durable ledger**, operation idempotency và transaction/reconciliation thích hợp.

### 10.3. `IdempotentReceiverInterceptor` và `MetadataStoreSelector`

Spring Integration có cơ chế **Idempotent Receiver advice**. Một triển khai phổ biến dùng selector đọc **business key** để so với metadata store. Sơ đồ:

~~~mermaid
flowchart LR
    I[Message<ChargeCommand>] --> A[Idempotent Receiver Advice]
    A --> K["Key = tenant/consumer/operation"]
    K --> S[(Metadata Store)]
    S -->|Key mới| H[Target Handler]
    S -->|Key đã tồn tại| D["Duplicate handling theo cấu hình"]
~~~

Ý tưởng tối thiểu:

~~~java
// Mã minh họa cách nối selector vào advice.
// Cần đối chiếu constructor/DSL options với phiên bản Spring Integration
// đang dùng và kiểm thử hành vi duplicate thực tế.

import org.springframework.integration.core.MessageSelector;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;

ConcurrentMetadataStore seenStore =
        new SimpleMetadataStore();

MessageSelector selector = message -> {
    ChargeCommand command =
            (ChargeCommand) message.getPayload();

    String key = IdempotencyKeys.forOperation(
            command.tenantId(),
            "PAYMENT_CHARGE",
            command.operationId());

    // null nghĩa là putIfAbsent thêm thành công vào fake store.
    return seenStore.putIfAbsent(key, "SEEN") == null;
};

IdempotentReceiverInterceptor advice =
        new IdempotentReceiverInterceptor(selector);
~~~

Với dependency hiện tại, cũng có thể xem **`MetadataStoreSelector`**, chuyên phối hợp cơ chế chọn message và metadata store. Có thể sử dụng `ConcurrentMetadataStore` để thực hiện key check-and-set có tính nguyên tử **trong phạm vi implementation của store**.

**Ba cảnh báo quan trọng:**

- **Advice có thể đánh dấu duplicate bằng header** như `duplicateMessage` hoặc chuyển sang discard/error path tùy phiên bản và cấu hình. Không tự mặc định mọi duplicate bị chặn trước handler: hãy kiểm tra cả hành vi mặc định và cấu hình thực.
- `putIfAbsent(key, "SEEN")` đánh dấu **trước** business work. Nếu handler lỗi, một retry cùng key có thể bị coi là duplicate dù side effect **chưa thành công**. Cần state/recovery policy hoặc áp dụng advice cho use case thực sự chấp nhận at-most-once admission.
- `SimpleMetadataStore` là in-memory và không thay durable ledger. Chỉ một metadata key `SEEN` không đủ để trả receipt, xác thực fingerprint hoặc reconcile remote payment.

**Không nên gắn advice trên và đồng thời gắn durable business ledger rồi giả định cả hai có cùng transaction.** Nếu cần advice để quan sát duplicate, phải định nghĩa rõ message trùng được đánh dấu, bỏ qua hay gửi vào nhánh nào, và điều đó có ảnh hưởng gì tới Gateway reply.

### 10.4. Khác biệt giữa duplicate header và business outcome

Một message có thể được **đánh dấu**:

~~~text
headers.duplicateMessage = true
payload.operationId = CHARGE-1001
~~~

Nhưng receiver còn phải biết:

- `CHARGE-1001` đã **COMPLETED** và có receipt?
- Operation vẫn **IN_PROGRESS** hay đã quá lease?
- Payload giống request trước hay có conflict?
- Người gửi có quyền xem receipt đã lưu?
- Client có cần **một reply** hay chỉ cần drop message?

Nếu request đi qua `MessagingGateway`, việc discard duplicate **không trả receipt** có thể khiến caller timeout, dù operation trước đã thành công. Khi API contract cần stable result, xử lý business idempotency **trong handler** thường rõ ràng hơn so với drop im lặng.

### 10.5. Header-based key hay payload-based key?

Hai cách lấy khóa:

~~~java
// Header do trusted ingress adapter cấp:
String fromHeader = (String)
        message.getHeaders().get("idempotencyKey");

// Payload nghiệp vụ:
ChargeCommand command =
        (ChargeCommand) message.getPayload();
String fromPayload = IdempotencyKeys.forOperation(
        command.tenantId(),
        "PAYMENT_CHARGE",
        command.operationId());
~~~

**Header nào được tin?** Nếu external caller được tự đặt header `idempotencyKey`, adapter phải kiểm tra quyền và ràng buộc nó với tenant/operation; không dùng raw header để bỏ qua validation hoặc xem receipt của operation khác. Nếu payload đủ nguồn tin cậy, việc dựng khóa server-side có thể rõ ràng hơn.

### 10.6. Endpoint advice đặt sai chỗ có thể khóa nhầm retry

~~~text
Source -> Filter -> Transformer -> Payment Handler

Idempotent advice trước Filter:
  SEEN được ghi dù Filter loại message.

Idempotent advice ở Payment Handler:
  Chỉ ghi nhận message đã tới target handler.
  Nhưng nếu handler lỗi sau marker, vẫn phải có recovery.
~~~

Không nên chỉ hỏi “đặt interceptor ở đâu cho nhanh?”. Hãy xác định **mốc nào được gọi là processed**, và **record đó có tồn tại cùng transaction với side effect cần bảo vệ hay không**.

## 11. Spring Integration integration tests

### 11.1. Retry cùng operation có một receipt ổn định

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(IdempotentReceiverFlowConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class IdempotentReceiverIntegrationTest {

    @Autowired
    ChargeGateway gateway;

    @Autowired
    InMemoryIdempotentChargeReceiver receiver;

    @Test
    void duplicateRequestReturnsExistingResult() {
        ChargeCommand command = new ChargeCommand(
                "TENANT-A",
                "CHARGE-1001",
                "ORD-1001",
                new BigDecimal("100000"));

        ChargeReceipt first = gateway.charge(command);
        ChargeReceipt again = gateway.charge(command);

        assertEquals(first, again);
        assertEquals(1, receiver.appliedCount());
    }

    @Test
    void independentOperationCreatesAnotherReceipt() {
        gateway.charge(new ChargeCommand(
                "TENANT-A", "CHARGE-1", "ORD-1",
                new BigDecimal("100000")));
        gateway.charge(new ChargeCommand(
                "TENANT-A", "CHARGE-2", "ORD-1",
                new BigDecimal("5000")));

        assertEquals(2, receiver.appliedCount());
    }
}
~~~

Các test này kiểm tra **Gateway → channel → handler → return value** trong một Spring context. Chúng chưa đi qua broker, remote payment, DB durability hay interceptor selector, vì thế cần những test khác cho từng ranh giới đó.

### 11.2. Spring Message IDs có thể khác, operation vẫn giống

Một test riêng chứng minh hai message được tạo từ cùng command có thể mang ID khác:

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class SpringMessageIdVsOperationIdTest {

    @Test
    void distinctMessageIdsCanCarrySameOperation() {
        ChargeCommand command = new ChargeCommand(
                "TENANT-A", "CHARGE-77", "ORD-77",
                new BigDecimal("100000"));

        Message<ChargeCommand> first =
                MessageBuilder.withPayload(command).build();
        Message<ChargeCommand> second =
                MessageBuilder.withPayload(command).build();

        assertNotEquals(
                first.getHeaders().getId(),
                second.getHeaders().getId());
        assertEquals(
                first.getPayload().operationId(),
                second.getPayload().operationId());
    }
}
~~~

Kết quả này minh họa **framework message identity** và **business operation identity** là hai tầng khác nhau. Đừng dùng unit test tạo message mới để suy ra broker luôn đổi ID khi redelivery: transport và converter có thể có semantics riêng.

### 11.3. Test duplicate advice phải kiểm tra cả handler

Nếu dùng `IdempotentReceiverInterceptor`, một test đúng cần kiểm tra:

1. Lần đầu key mới, selector đánh dấu accepted.
2. Lần hai key cũ, metadata store cho biết duplicate.
3. Thông điệp bị **mark/discard/exception** đúng theo cấu hình, chứ không tự suy rằng false luôn drop.
4. Nếu discard, caller/Gateway nhận kết quả hoặc timeout đúng contract.
5. Nếu handler ném lỗi ở lần đầu, retry không bị chặn sai bởi marker `SEEN` — hoặc phải ghi nhận đây là at-most-once admission có chủ đích.
6. Restart/multi-instance với production metadata store có kết quả đúng expected retention.

Không thể dùng riêng test `selector.accept(...)` để chứng minh business operation được xử lý exactly-once.

## 12. Tương tác với Broker, Gateway, retry và error channel

### 12.1. Transport retry không nhất thiết giữ nguyên Spring Message ID

Khi message đi qua Kafka/JMS/AMQP/HTTP, hãy tách các lớp:

~~~text
Business event:
  eventId=EVT-77
  operationId=CHARGE-77

Transport record:
  topic=payments.requests
  partition=2
  offset=581

Spring Integration message in JVM:
  headers.id=UUID-1

Retry / republish:
  same eventId=EVT-77
  maybe new transport record offset=622
  maybe new headers.id=UUID-2
~~~

Nếu consumer chỉ dedupe bằng `topic/partition/offset`, một event được **republish thành record mới** có thể lọt qua. Nếu chỉ dùng `headers.id`, message rebuild cũng có thể tạo ID mới. **Business eventId/operationId** thường là khóa ổn định hơn khi muốn chống tác động lặp của cùng một logical event.

### 12.2. Delivery semantics không đồng nghĩa business idempotency

| Delivery situation | Rủi ro | Cần gì? |
|---|---|---|
| **At-most-once delivery** | Message có thể mất trước business commit. | Chấp nhận rủi ro mất hoặc dùng giao thức khác. |
| **At-least-once delivery** | Cùng message được giao lại. | Idempotent Receiver/ledger và retry policy. |
| **Broker transaction** | Broker records/offsets có tính chất nhất định theo broker. | Vẫn cần bảo vệ side effect ngoài broker. |
| **HTTP caller retry** | Command có thể được gửi lại với message ID khác. | Caller-supplied/server-issued operation ID ổn định và validation. |
| **DLQ replay** | Event cũ quay lại sau nhiều giờ/ngày. | Retention, dedupe state và reauthorization phù hợp. |
| **Outbox relay retry** | Một event có thể publish lặp. | Event ID giữ nguyên giữa các publish attempts. |

**Không tuyên bố exactly-once end-to-end chỉ vì broker có transaction mode hoặc consumer idempotency advice.** Phải chỉ ra điểm side effect được bảo vệ bằng cách nào.

### 12.3. Ack trước hay sau business commit?

~~~text
Receive
  -> validate
  -> look up / acquire operation key
  -> execute business work
  -> persist authoritative outcome
  -> broker acknowledgment
~~~

Đây là **thứ tự logic mong muốn** cho một loại flow at-least-once. Nếu ack trước khi kết quả được lưu bền, crash có thể làm mất operation. Nếu ack sau commit, crash có thể khiến broker giao lại, nên receiver phải dedupe. Transactional adapter, broker offset semantics và store commit cụ thể cần được kiểm chứng theo hạ tầng.

### 12.4. Gateway reply timeout không chứng minh business thất bại

Một request–reply Gateway có thể:

~~~text
T0 Caller gửi CHARGE-77.
T1 Receiver gọi external payment.
T2 Payment commit.
T3 Reply network bị mất.
T4 Gateway timeout.
T5 Caller retry CHARGE-77.
~~~

Lần thử lại nên giữ **same operationId**, kiểm tra receipt trạng thái hoặc dùng remote idempotency key. Không cấp operation ID mới mỗi lần caller gặp timeout, trừ khi nghiệp vụ thực sự muốn tạo một operation khác có sự cho phép.

### 12.5. Error channel là đường lỗi, không phải inbox ledger

Spring Integration có thể tạo `ErrorMessage` và đưa vào `errorChannel` theo execution model/configuration. Nhưng:

- Một message bị retry không chắc đã có `ErrorMessage` trong mọi cấu hình.
- Một lỗi ở thread khác có thể xảy ra **sau khi producer đã nhận ack**.
- Một exception từ handler không có nghĩa external side effect chưa commit.
- Recovery handler nhận `Throwable` không tự biết operation đã COMPLETED/UNKNOWN.
- Một duplicate bị interceptor discard có thể không tạo lỗi kỹ thuật nào cả.

Hãy lưu **business operation state và receipt** trong ledger thích hợp, dùng error channel để **phân loại, quan sát, schedule retry, quarantine** theo contract.

### 12.6. Retry advice nên đặt vào đâu?

Một ví dụ có hai endpoint:

~~~text
Token / Message
  -> Idempotency check / acquire
  -> External payment call
  -> Persist completion
~~~

Nếu đặt `RequestHandlerRetryAdvice` quanh **toàn bộ endpoint** sau khi đã ghi `SEEN` trong selector, lần hai có thể bị coi là duplicate dù lần đầu chưa hoàn tất. Nếu advice chỉ quanh external payment call, cần giữ **same operationId/idempotency key** và không retry UNKNOWN một cách mù quáng.

| Retry scope | Khóa phải ổn định | Rủi ro chính |
|---|---|---|
| Retry local handler | Operation key. | Marker “SEEN” được ghi quá sớm. |
| Retry broker record | Event/operation ID. | Redelivery sau commit; ack lost. |
| Retry HTTP payment | External idempotency key. | Timeout sau remote commit. |
| Replay từ DLQ | Original event identity + consumer scope. | Dedupe record đã expired, schema đổi. |
| Rebuild projection | Event ID + versioned consumer namespace. | Dedupe cũ chặn replay cần thiết. |

Đừng retry bằng cách **xóa thủ công idempotency key** để “cho message chạy lại” khi chưa biết side effect đã commit hay chưa.

## 13. Kết hợp với Router, Filter, Splitter và Aggregator

### 13.1. Router: một event có thể tạo nhiều operations

Một sự kiện `OrderPaid(eventId=EVT-77)` được Router gửi tới:

~~~mermaid
flowchart TD
    E["OrderPaid EVT-77"] --> R{Router / Recipient List}
    R --> B[BillingProjection]
    R --> N[Notification]
    R --> A[Audit]
    B --> K1["Key BILLING/EVT-77"]
    N --> K2["Key NOTIFY/EVT-77"]
    A --> K3["Key AUDIT/EVT-77"]
~~~

Nếu tất cả dùng chung global dedupe key chỉ `EVT-77`, Billing có thể đánh dấu SEEN trước, làm Notification và Audit coi message là duplicate. Đúng hơn, cần **consumer-specific scope** hoặc một operation ID riêng cho từng side effect.

Nếu Router thực sự chỉ chọn **một** route trong một lần, cũng phải định nghĩa khi policy routing thay đổi và event được replay: route cũ đã hoàn tất có được xử lý lại không? Thay namespace/route có thể tạo effect mới, cần phê duyệt.

### 13.2. Filter có thể ghi SEEN quá sớm

~~~text
Idempotency filter marks EVT-77 as SEEN
  -> Business Filter rejects EVT-77
  -> Retry with corrected data still treated as duplicate
~~~

Cần phân biệt:

- **Malformed/permanently rejected event:** có thể ghi một final rejection outcome để không xử lý mãi.
- **Temporarily ineligible event:** có thể cần retry/re-evaluate theo business policy, không nên đánh dấu COMPLETED.
- **Accepted/processed event:** chỉ ghi completion sau khi đúng điều kiện nghiệp vụ hoàn tất.

Một `MessageSelector` chạy trước business Filter có thể là lựa chọn đúng cho **admission dedupe**, nhưng đừng ngầm coi nó là **business completion dedupe**.

### 13.3. Splitter: parent correlation không phải child idempotency key

~~~text
Batch B-1, correlationId=B-1
  -> Item #1 (itemId=I-1)
  -> Item #2 (itemId=I-2)
  -> Item #3 (itemId=I-3)
~~~

Nếu mỗi child dùng `correlationId=B-1` làm idempotency key, item #2 và #3 có thể bị coi là trùng item #1.

Khóa phù hợp hơn:

~~~text
(tenantId, PROCESS_ITEM, batchProcessingId, itemId)
~~~

hoặc một stable `itemOperationId` do producer cấp. `sequenceNumber` có thể hữu ích khi ID per-item được xác định ổn định theo input snapshot, nhưng không chỉ dùng sequence number vì nhiều batch cùng có số 1,2,3.

### 13.4. Aggregator: duplicate có thể làm release sai

Một Aggregator chờ ba message:

~~~text
Expected: I-1, I-2, I-3
Received: I-1, I-1, I-2
~~~

Nếu chỉ đếm `group.size()==3`, duplicate có thể che message thiếu `I-3`. Dedupe nên diễn ra theo **business item identity**, còn Aggregator nên đối chiếu tập expected IDs và release strategy phù hợp; không chỉ tin tổng số message.

Nếu Idempotent Receiver **bỏ qua duplicate** trước Aggregator, hãy đảm bảo nó không bỏ qua **outcome bắt buộc** làm group chờ vô hạn. Có thể phải trả stored result cho duplicate thay vì discard im lặng.

### 13.5. Resequencer: thứ tự không bảo đảm không lặp

Resequencer có thể phát các message theo sequenceNumber đúng thứ tự nhưng broker redelivery vẫn tạo duplicate của cùng logical event. **Ordering** và **idempotency** là hai bất biến khác nhau.

~~~text
Received: seq=2, seq=1, seq=2 (redelivery)
Desired business effects:
  effect(seq=1) đúng một lần
  effect(seq=2) đúng một lần
~~~

Cần cả sequence/correlation contract, duplicate handling và downstream idempotency. Nếu drop một duplicate, Resequencer phải vẫn có đủ vị trí để release đúng.

### 13.6. Claim Check: claim ID mới không tạo operation mới

Một original order có thể được reissue claim vì token cũ expired:

~~~text
Claim C-100 -> operation PAY-ORD-1
Claim C-200 -> operation PAY-ORD-1 (authorized replay)
~~~

Nếu dùng `claimId` làm idempotency key, lần C-200 có thể gọi lại payment dù business operation đã được thực hiện qua C-100. Phải phân biệt **payload retrieval reference** và **business operation ID**.

### 13.7. Scatter–Gather: một yêu cầu, nhiều branch outcomes

~~~text
requestId=REQ-1
  -> inventory branch: op=REQ-1/inventory
  -> fraud branch:     op=REQ-1/fraud
~~~

Hai branch đều có thể nhận cùng request ID nhưng có tác dụng khác nhau, nên scope idempotency theo recipient. Gatherer cần:

- Dedupe reply cùng `requestId + recipientId` theo attempt/version contract.
- Không đếm hai Inventory replies thành hai required recipients.
- Không coi một branch đã COMPLETED là đủ để xác nhận toàn request.
- Bảo vệ late reply từ attempt cũ sau group timeout.

**Một global key chỉ bằng requestId sẽ chặn nhầm branch hợp lệ.**

## 14. Khi một Transformer làm biến đổi message identity

### 14.1. Một message mới không tự tạo một business event mới

~~~java
// Input là event cần normalize.
record PaidEvent(String eventId, String orderId) {}
record NormalizedPaidEvent(String eventId, String orderId) {}

NormalizedPaidEvent normalize(PaidEvent event) {
    return new NormalizedPaidEvent(
            event.eventId(),
            event.orderId().trim().toUpperCase());
}
~~~

Transformer có thể tạo payload mới và message mới; nhưng nếu `eventId` vẫn là EVT-77, đó có thể là **cùng một business event**. Dedupe theo Spring Message ID mới sẽ không thể hiện điều này.

### 14.2. Không để Transformer tự sinh operationId khi retry

Sai:

~~~java
String operationId =
        java.util.UUID.randomUUID().toString();
~~~

nếu code này chạy **mỗi lần nhận** cùng command. Như vậy retry có key khác và idempotency bị vô hiệu hóa.

Đúng hơn: operationId được cấp từ **nguồn đáng tin tại lúc tạo business operation**, được truyền nguyên qua retry/replay. Với các events không có ID upstream, phải có chiến lược đánh số tại điểm nhập (ingress) có state bền vững; không tự tạo random ID ở mỗi consumer attempt.

### 14.3. Header mapping và trust boundary

Nếu eventId hoặc idempotencyKey nằm trong header Kafka/HTTP:

- Có được truyền qua outbound/inbound adapter không?
- Header bị đổi kiểu hoặc format khi deserialize không?
- Adapter có được phép dùng header do external client tự đặt không?
- Có mâu thuẫn giữa payload operationId và header idempotencyKey không?
- Header có bị lọc khi đi qua Transform/Bridge/Router không?

Một cách an toàn là xác định **một nguồn sự thật** cho operation identity, kiểm tra và chuẩn hóa ở trusted ingress, sau đó propagate nhất quán. Không copy toàn bộ untrusted headers rồi dùng chúng làm quyền để đọc stored receipts.

## 15. TTL, memory, persistence và dữ liệu nhận diện duplicate

### 15.1. Dedupe state phải sống đủ lâu

Một bảng key được xóa sau 10 phút có thể không đủ khi:

~~~text
Broker retry window:      30 phút
DLQ replay window:        7 ngày
Payment dispute window:   dài hơn
Retention policy:         theo nghiệp vụ và pháp lý
~~~

Không phải lúc nào cũng phải giữ **toàn bộ payload hoặc receipt** suốt thời gian trên. Có thể tách:

- **Active operation record:** key, state, receipt, lease, đủ cho in-flight retry.
- **Completed tombstone:** key, final status, fingerprint, external reference tối thiểu cho replay horizon.
- **Audit archive:** theo retention và access policy riêng, nếu thật sự cần.

Nhưng nếu tombstone mất trong khi một event cũ còn có thể replay, consumer có thể xử lý lại như event mới. Đặt TTL là một **quyết định nghiệp vụ/kiến trúc**, không chỉ là tuning cache.

### 15.2. SimpleMetadataStore không bảo đảm persistence qua restart

`SimpleMetadataStore` phù hợp học/kiểm thử hoặc use case chấp nhận state trong memory. Với durable idempotency, cân nhắc `ConcurrentMetadataStore` có persistence/transaction phù hợp hoặc một bảng inbox/ledger riêng.

Các câu hỏi phải trả lời:

- Dedupe store có chia sẻ giữa nhiều JVM không?
- `putIfAbsent` có atomic khi hai nodes chạy đồng thời không?
- Store restart có giữ key không?
- Có transaction bao trùm business mutation không?
- Khi cleanup xóa key, một late duplicate sẽ xử lý thế nào?
- Có cơ chế giới hạn số key, TTL và alert capacity không?

Không đánh đồng interface `ConcurrentMetadataStore` với **distributed exactly-once**. Tính chất phụ thuộc implementation backend và ranh giới side effect.

### 15.3. Store unavailable khác duplicate

~~~text
metadata store read timeout
~~~

Tình trạng này không chứng minh operation đã thấy trước đó. Nếu store unavailable, chiến lược an toàn cho payment thường là **không gọi external side effect mới mà không có biện pháp idempotency thay thế**.

Một số hệ thống có thể cho phép degraded mode với remote idempotency key nếu external API đủ mạnh, nhưng đó là policy được xác nhận riêng; không mặc định “không đọc được ledger thì cứ xử lý”.

### 15.4. Cleanup là một workflow riêng

Nếu operation đã COMPLETED nhưng việc xóa dữ liệu nhạy cảm khỏi ledger gặp lỗi, **không được retry payment chỉ vì cleanup lỗi**.

~~~text
Operation status = COMPLETED
Cleanup status   = PENDING_DELETE

Cleanup worker:
  retry deleting old payload/temporary data
  retain minimal dedupe tombstone if policy requires
  alert if deletion exceeds deadline
~~~

Cần đảm bảo backup, replication, cache và DLQ không giữ dữ liệu quá hạn so với retention policy. Một “delete succeeded” ở primary database không tự chứng minh mọi bản sao đã bị xử lý.

## 16. Bảo mật khi dùng idempotency key

### 16.1. Không tin khóa do client tự cấp mà không có ràng buộc

Giả sử HTTP caller gửi:

~~~text
Idempotency-Key: CHARGE-1001
Tenant: TENANT-A
~~~

Hệ thống không được xem hai header này là quyền hạn. Phải:

1. Xác thực caller (mTLS/token/session theo môi trường).
2. Suy ra tenant/merchant scope từ **principal hoặc server-side authorization context**.
3. Đối chiếu operationId thuộc caller và business resource đúng quyền.
4. Validate key format, length, entropy/reuse policy và rate limit.
5. Nếu key đã tồn tại, kiểm tra **payload fingerprint** trước khi trả receipt.
6. Không tiết lộ receipt của một operation không thuộc quyền caller.

Một key dễ đoán chỉ là **định danh**, không phải bằng chứng quyền sở hữu.

### 16.2. Dedupe không được che security incident

Nếu token của tenant B giả mạo operation ID của tenant A, hệ thống không nên trả `DUPLICATE_SUCCESS` trước bước authorization. Thứ tự nên là:

~~~text
Authenticate
  -> Authorize tenant/resource/operation
  -> Validate idempotency key + fingerprint
  -> Read/claim operation state
  -> Return previous result / execute operation
~~~

Thậm chí phản hồi “operation key đã tồn tại” cũng có thể gây lộ thông tin nếu không kiểm soát quyền. API có thể cần trả lỗi chung cho những key thuộc scope không được phép.

### 16.3. Payload fingerprint không thay dữ liệu gốc đáng tin

Nếu hash dữ liệu đã bị attacker chỉnh sửa nhưng không xác thực input source, fingerprint chỉ chứng minh “hai bytes giống nhau”, không chứng minh **nghiệp vụ được phép**. Với event từ broker, cần kiểm tra nguồn producer, schema version, chữ ký/authentication nếu cần và tenant isolation.

### 16.4. Không log toàn bộ idempotency key khi chứa PII

Một operation ID như `PAY:customer-email@example.com` có thể làm lộ thông tin cá nhân trong metrics/logs. Nên dùng opaque ID hoặc reference được che/hash phù hợp, hạn chế retention và phân quyền.

Với metric labels, **không** dùng operationId, eventId, tenant user ID hoặc Spring Message ID có cardinality rất cao. Dùng labels hữu hạn như component, outcome, reason class, route.

## 17. Quan sát luồng: đâu là “đã thấy”, đâu là “đã hoàn tất”?

### 17.1. Các sự kiện gợi ý

~~~text
event=MESSAGE_RECEIVED
  operationRef=CHARGE-1001
  deliveryAttempt=1

event=IDEMPOTENCY_KEY_VALIDATED
  operationRef=CHARGE-1001
  keyScope=PAYMENT_CHARGE

event=OPERATION_ACQUIRED
  operationRef=CHARGE-1001
  state=IN_PROGRESS

event=SIDE_EFFECT_REQUESTED
  operationRef=CHARGE-1001
  remoteIdempotencyKey=CHARGE-1001

event=OPERATION_COMPLETED
  operationRef=CHARGE-1001
  receiptRef=PAY-XYZ

event=DUPLICATE_RECEIVED
  operationRef=CHARGE-1001
  deliveryAttempt=2

event=DUPLICATE_RESULT_RETURNED
  operationRef=CHARGE-1001
  result=EXISTING_RECEIPT
~~~

Đây là **schema structured logs do ứng dụng đề xuất**, không phải sự kiện Spring Integration mặc định. Một log `IDEMPOTENCY_KEY_VALIDATED` không nên bị nhầm với `OPERATION_COMPLETED`.

### 17.2. Metrics gợi ý

| Metric | Ý nghĩa |
|---|---|
| `receiver_messages_total` | Số lần message tới receiver (bao gồm redelivery). |
| `receiver_unique_operations_total` | Số business operation mới được chấp nhận. |
| `receiver_duplicates_total{reason}` | Số duplicate hợp lệ, đã hoàn tất hoặc còn in-progress. |
| `receiver_conflicts_total` | Same key, different fingerprint. |
| `receiver_completed_total{status}` | Số operation hoàn tất với status cuối. |
| `receiver_outcome_unknown_total` | Số operation cần reconciliation. |
| `receiver_lease_expired_total` | Số lease operation hết hạn. |
| `receiver_retry_total{reason}` | Số retry do lỗi được phân loại. |
| `receiver_dlq_replay_total` | Số operation được replay qua DLQ. |
| `receiver_metadata_store_errors_total` | Số lỗi đọc/ghi idempotency state. |
| `receiver_operation_latency_seconds` | Độ trễ từ bắt đầu đến outcome. |
| `receiver_pending_operations` | Số operation chưa có final outcome. |
| `receiver_cleanup_failed_total` | Cleanup dữ liệu hết retention thất bại. |

Đây là tên metric minh họa, không khẳng định framework tự sinh trong mọi cấu hình. Không gộp **số message nhận** với **số operation mới**: nếu event được giao ba lần, metric nhận tăng ba còn metric operation mới chỉ tăng một theo contract.

### 17.3. Mốc vận hành và kết luận hợp lệ

| Tín hiệu | Có thể khẳng định | Chưa thể khẳng định |
|---|---|---|
| Message received | Consumer đã nhận một delivery. | Operation chưa từng xử lý trước. |
| Key found | Store có record matching. | Business đã COMPLETED. |
| `SEEN` marker written | Selector lưu dấu xuất hiện. | Side effect đã commit. |
| IN_PROGRESS lease acquired | Một worker có quyền xử lý theo lease contract. | Remote effect chưa xảy ra ở worker cũ. |
| Receipt persisted COMPLETED | Ledger xác nhận outcome. | Mọi hệ thống ngoài đồng bộ atomically nếu không có reconciliation. |
| Broker acked | Broker ghi nhận ack theo semantics. | Không còn redelivery/replay ở nơi khác. |
| Duplicate discarded | Message này không đi tiếp qua đường discard. | Caller đã nhận một receipt hợp lệ. |

### 17.4. Message History không phải durable inbox

Spring Integration Message History (khi tracking được cấu hình) có thể giúp thấy message đi qua Router, Transformer, Gateway hoặc handler nào. Nhưng nó không phải:

- Durable mapping `operationId -> COMPLETED receipt`.
- Bằng chứng external payment đã commit.
- Mô hình kiểm soát concurrency qua nhiều JVM.
- Cơ chế giữ TTL/replay tombstone.
- Bản ghi authorization cho tenant.

Muốn điều tra một duplicate thật, kết hợp **business operation ledger, transport coordinates, message headers, trace context và outcome logs**.

## 18. Chẩn đoán: vì sao một duplicate vẫn tạo side effect?

Khi phát hiện một đơn bị xử lý hai lần, kiểm tra theo thứ tự:

1. **Business intent:** hai requests có thực sự là cùng operation không, hay là hai operations hợp lệ trên cùng order?
2. **Operation ID:** producer có giữ ID ổn định giữa retry/replay không?
3. **Key scope:** receiver có dùng đúng tenant, consumer và operation type không?
4. **Header conversion:** Transformer/adapter có tạo ID mới hoặc làm mất business key không?
5. **Fingerprint:** hai messages có cùng nội dung business hay bị reuse key sai?
6. **Store:** có dùng in-memory store trên hai pods không? `putIfAbsent` có atomic trong backend chung không?
7. **TTL:** dedupe record có bị xóa trước DLQ replay/redelivery không?
8. **Advice:** selector có chỉ mark `SEEN` trước handler nhưng handler thất bại không? Duplicate có được discard hay vẫn chạy?
9. **Side effect:** remote service có nhận cùng idempotency key không? Nó có giữ key đủ lâu không?
10. **Crash window:** payment commit rồi ack/ledger record bị mất vào thời điểm nào?
11. **Concurrency:** hai workers có cùng xử lý operation trước khi lock/ledger có hiệu lực không?
12. **Recovery:** late reply hay stale attempt có ghi đè status COMPLETED không?
13. **Code path:** có một nhánh bypass receiver và gọi external API trực tiếp không?
14. **Audit:** có đủ record để xác minh external references và số lần charge thực không?

Đừng “sửa” bằng cách tăng TTL tùy tiện hoặc chuyển tất cả vào một queue FIFO trước khi xác định lỗi. Thứ tự arrival và idempotency của business side effect là những bất biến khác nhau.

## 19. Bổ sung kiểm thử các ngộ nhận về key

### 19.1. Mark SEEN không đồng nghĩa handler chạy thành công

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class PrematureSeenMarkerTest {
    @Test
    void seenBeforeCommitCanBlockAValidRetry() {
        ConcurrentMetadataStore store = new SimpleMetadataStore();
        String operationKey = IdempotencyKeys.forOperation(
                "TENANT-A", "PAYMENT_CHARGE", "OP-1");

        // Attempt 1: đánh dấu rồi crash trước business effect.
        assertNull(store.putIfAbsent(operationKey, "SEEN"));

        // Attempt 2: selector kiểu SEEN-only coi đây là duplicate.
        assertNotNull(store.putIfAbsent(operationKey, "SEEN"));

        // Chưa có receipt nào để chứng minh operation COMPLETED.
        // Đây là minh họa hạn chế, KHÔNG phải behavior đúng cho payment.
    }
}
~~~

Test này **cố tình chứng minh một thiết kế thiếu an toàn**. Nó chỉ kiểm tra store marker, không gọi payment. Nếu ứng dụng yêu cầu retry sau lỗi trước commit, phải thay marker `SEEN` bằng state/recovery rõ hoặc một transaction phù hợp.

### 19.2. Dấu phân cách trong key không được gây va chạm

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNotEquals;

class CompositeKeyEncodingTest {
    @Test
    void encodedSegmentsDoNotCollapseDifferentTuples() {
        String first = IdempotencyKeys.forOperation(
                "TENANT:A", "PAYMENT", "OP-1");
        String second = IdempotencyKeys.forOperation(
                "TENANT", "A:PAYMENT", "OP-1");

        assertNotEquals(first, second);
    }
}
~~~

Nếu không có encoding hoặc composite DB primary key, hai bộ thành phần khác nhau có thể tạo cùng một chuỗi khi dùng phép nối không an toàn.

### 19.3. Không gán operation mới chỉ vì Spring Message ID mới

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class RebuiltMessageStillDuplicateTest {
    @Test
    void rebuiltEnvelopeDoesNotChangeTheBusinessOperation() {
        ChargeCommand command = new ChargeCommand(
                "TENANT-A", "CHARGE-77", "ORD-77",
                new BigDecimal("100000"));

        Message<ChargeCommand> first =
                MessageBuilder.withPayload(command).build();
        Message<ChargeCommand> second =
                MessageBuilder.withPayload(command).build();
        InMemoryIdempotentChargeReceiver receiver =
                new InMemoryIdempotentChargeReceiver();

        assertNotEquals(
                first.getHeaders().getId(),
                second.getHeaders().getId());
        assertEquals(
                receiver.handle(first.getPayload()),
                receiver.handle(second.getPayload()));
        assertEquals(1, receiver.appliedCount());
    }
}
~~~

### 19.4. Kiểm thử normalization của amount trong fingerprint

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ChargeFingerprintTest {
    @Test
    void mathematicallyEqualAmountsShareDemoFingerprint() {
        ChargeCommand a = new ChargeCommand(
                "TENANT-A", "OP-1", "ORD-1",
                new BigDecimal("100000"));
        ChargeCommand b = new ChargeCommand(
                "TENANT-A", "OP-1", "ORD-1",
                new BigDecimal("100000.00"));

        assertEquals(
                ChargeFingerprint.of(a),
                ChargeFingerprint.of(b));
    }
}
~~~

Trong sản phẩm thật, amount normalization phải nhất quán với currency và rule tính tiền; không mặc nhiên coi các số có kiểu scale khác nhau là tương đương nếu nghiệp vụ cố tình phân biệt.

## 20. Ma trận kiểm thử Message ID và idempotency key

| ID | Kịch bản | Điều phải xác minh | Điều không được xảy ra |
|---|---|---|---|
| IR-01 | Message mới, operation key mới | Tạo business operation một lần. | Bị discard nhầm. |
| IR-02 | Cùng message được broker redeliver | Trả receipt/ack duplicate theo contract. | Lặp side effect. |
| IR-03 | Cùng business operation nhưng Spring Message ID mới | Vẫn được nhận diện là duplicate. | Chạy lại do ID mới. |
| IR-04 | Cùng Message ID nhưng business operation khác do lỗi producer | Validation/provenance phát hiện. | Gộp nhầm operations. |
| IR-05 | Một order có charge và refund hợp lệ | Hai operation keys khác nhau. | Refund bị bỏ vì cùng orderId. |
| IR-06 | Cùng operationId, same fingerprint | Trả cùng receipt. | Charge lại. |
| IR-07 | Cùng operationId, amount khác | OPERATION_CONFLICT. | Trả success cũ hoặc charge mới im lặng. |
| IR-08 | Cùng local operationId ở hai tenants | Phân tách tenant scope. | Chặn tenant B do tenant A. |
| IR-09 | Hai consumer cùng eventId | Mỗi consumer xử lý một lần. | Global marker chặn consumer thứ hai. |
| IR-10 | Một consumer nhận ba copies của cùng eventId | Một business effect. | Đếm ba events mới. |
| IR-11 | Two threads nhận cùng key | Atomic key claim/dedupe. | Cả hai tạo side effect độc lập. |
| IR-12 | Hai JVM dùng chung key | Durable shared ledger. | Mỗi JVM dùng map riêng rồi xử lý hai lần. |
| IR-13 | Selector ghi SEEN rồi handler crash | Retry/recovery policy không bỏ lỡ work. | Skip vĩnh viễn chưa xử lý. |
| IR-14 | Handler commit rồi crash trước SEEN | Remote idempotency/reconciliation. | Tạo side effect thứ hai. |
| IR-15 | DB inbox + business effect cùng transaction | Atomic completion theo DB contract. | Inbox committed nhưng business update mất. |
| IR-16 | Remote HTTP payment timeout sau commit | UNKNOWN rồi reconcile. | Retry mù tạo charge mới. |
| IR-17 | Broker ack bị mất sau ledger commit | Duplicate trả previous receipt. | Operation mới. |
| IR-18 | Gateway caller retry sau reply timeout | Stable operation key. | UUID mới cho cùng operation. |
| IR-19 | Late reply của attempt cũ | State/version guard. | FAILED ghi đè COMPLETED. |
| IR-20 | Lease hết hạn nhưng worker cũ vẫn sống | Fencing/reconciliation. | Worker cũ commit stale state. |
| IR-21 | Metadata store unavailable | Controlled error/degraded policy. | Hiểu thành key mới an toàn. |
| IR-22 | Metadata store chỉ in-memory, process restart | Hạn chế được test hoặc thay bằng store durable. | Hứa dedupe qua restart. |
| IR-23 | TTL record 5 phút, replay sau 1 ngày | Retention/replay policy rõ. | Late replay chạy như mới ngoài ý muốn. |
| IR-24 | DLQ replay cùng event ID | Giữ identity và đúng scope. | Cấp ID mới mỗi lần requeue. |
| IR-25 | Outbox publish cùng event hai lần | Dedupe ở consumer. | Notification/payment nhân đôi. |
| IR-26 | Transformer tạo message mới | Business identity được giữ. | Dedupe theo headers.id mới. |
| IR-27 | Filter loại message trước handler | Rejection/seen semantics rõ. | Đánh dấu COMPLETED sai. |
| IR-28 | Router gửi event tới hai subscribers | Consumer-specific keys. | Chỉ nhánh đầu được xử lý. |
| IR-29 | Splitter có ba child cùng correlationId | Per-child key. | Chặn nhầm child #2, #3. |
| IR-30 | Aggregator nhận duplicate item result | Không dùng duplicate thay missing. | Release group thiếu item. |
| IR-31 | Resequencer reorder nhưng nhận duplicate | Ordering và dedupe đều đúng. | Commit trùng. |
| IR-32 | Claim Check reissue claim mới | Giữ operation identity. | Side effect mới do claimId khác. |
| IR-33 | Scatter–Gather nhận duplicate branch reply | Recipient-scoped dedupe. | Hai Inventory thay Fraud. |
| IR-34 | HTTP header key do client giả mạo | AuthN/AuthZ/tenant bind. | Lộ stored receipt. |
| IR-35 | Same key nhưng request của principal khác | Không trả receipt trái quyền. | Leakage giữa accounts. |
| IR-36 | Key chứa dấu phân cách | Composite encoding không mơ hồ. | Collision sai. |
| IR-37 | Payload canonicalization thay đổi sau deploy | Versioning/compatibility. | Conflict giả hoặc duplicate lọt. |
| IR-38 | Advice duplicate handling mặc định | Test mark/discard/error thật. | Giả định duplicate luôn bị drop. |
| IR-39 | Gateway duplicate bị discard | Caller có response/timeout đúng contract. | Im lặng treo không kiểm soát. |
| IR-40 | Cleanup record sau completion | Tombstone/retention phù hợp. | Side effect lặp sau key expiry. |
| IR-41 | Event schema cũ replay vào handler mới | Scope/version migration rõ. | Xử lý trái policy. |
| IR-42 | Business failure cuối và retry cùng key | Trả/recover theo trạng thái được định nghĩa. | Biến rejection vĩnh viễn thành success giả. |
| IR-43 | Unknown operation không có receipt | Reconcile/manual action. | Tuyên bố chưa commit vô căn cứ. |
| IR-44 | Một nhánh bypass idempotent handler | Detection/system test. | Side effect không qua protection. |
| IR-45 | Metrics khi 1 event được giao 5 lần | 5 receives, 1 unique operation. | Đếm 5 business operations. |

### 20.1. Chọn cấp kiểm thử đúng

| Cấp | Test tốt nhất cho | Không chứng minh được |
|---|---|---|
| **Unit test key derivation** | Tenant/consumer/op scope, fingerprint, normalization. | DB uniqueness hoặc broker ack. |
| **Unit test in-memory receiver** | Duplicate returns receipt, conflict, concurrent fake. | Remote payment idempotency qua crash. |
| **Spring Integration test** | Gateway, Message ID rebuild, selector/advice, channel behavior. | Durability của metadata store nếu không dùng store thật. |
| **Database integration test** | Unique constraints, transactions, lock/lease, recovery. | Remote HTTP side effect khi chỉ fake. |
| **Adapter test** | Broker redelivery, header mapping, retry advice scope. | Payment external API commit nếu chưa tích hợp. |
| **System/chaos test** | Crash windows, timeout after commit, multi-node concurrency. | Mọi failure mode production theo thời gian. |
| **Security test** | Tenant auth, key spoofing, receipt access, retention. | Toàn bộ rủi ro nếu chưa review trust boundaries. |

Một **unit test xanh** chỉ chứng minh logic trong memory đúng với fixture; nếu mục tiêu là không charge trùng sau crash, cần test tại **đúng ranh giới giữa broker, durable state và payment provider**.

## 21. Những sai lầm thiết kế thường gặp

| Sai lầm | Hậu quả | Cách làm phù hợp |
|---|---|---|
| Dùng `MessageHeaders.ID` làm business idempotency key. | Message rebuild có ID mới, duplicate lọt. | Dùng stable eventId/operationId từ nguồn đáng tin. |
| Dùng `orderId` cho mọi tác động trên order. | Refund/adjustment hợp lệ bị chặn. | Key theo loại và lần business operation. |
| Dùng `traceId` để chống trùng. | Nhiều operations cùng trace bị coi là một. | Trace cho quan sát, operation ID cho idempotency. |
| Dùng `correlationId` của Splitter cho từng child. | Nhiều child bị coi là duplicate. | Thêm child/operation identity đúng scope. |
| Dùng cùng key cho mọi subscribers của event. | Subscriber thứ hai không xử lý. | Consumer-scoped key hoặc operation-specific key. |
| Tự sinh UUID mới ở consumer mỗi lần nhận. | Retry luôn có key mới. | Cấp operation ID ổn định ở ingress/producer. |
| Đánh dấu `SEEN` trước handler rồi coi là COMPLETED. | Crash trước commit gây mất xử lý. | Durable state/transaction/recovery. |
| Đánh dấu `SEEN` chỉ sau handler mà không có remote idempotency. | Crash sau commit có thể tạo effect trùng. | Reconciliation/remote idempotency key. |
| Giả định interceptor luôn discard duplicate. | Duplicate vẫn đi qua handler theo cấu hình. | Test behavior mark/discard/error thực tế. |
| Discard duplicate của Gateway mà không trả reply. | Caller timeout dù operation đã xong. | Return stored receipt/status. |
| Chỉ dùng `SimpleMetadataStore` khi có nhiều nodes. | Mỗi node có state riêng, duplicate chạy hai lần. | Durable/shared store có atomic contract. |
| Chỉ dùng một DB `SELECT` rồi `INSERT`. | Race giữa concurrent workers. | Unique constraint/CAS/locking transaction. |
| Đồng nhất DB transaction với remote HTTP commit. | Không rollback được external effect. | Idempotency at side-effect boundary/reconcile. |
| Retry khi remote timeout nghĩa là operation chưa commit. | Double charge. | Outcome UNKNOWN và query status. |
| Trả previous receipt cho cùng key nhưng payload khác. | Che dữ liệu mâu thuẫn. | Fingerprint/version check, conflict error. |
| Xóa dedupe state trước replay horizon. | Late duplicate chạy như mới. | Retention/tombstone phù hợp. |
| Reissue Claim Check ID rồi coi là operation mới. | Một original được xử lý lặp. | Tách claim ID và operation ID. |
| Cứ thấy failed event thì xóa key và chạy lại. | Có thể lặp side effect đã commit. | Chọn recovery theo state và chứng cứ. |
| Coi queue FIFO là bảo đảm exactly-once. | Retry vẫn có duplicate. | Ordering và idempotency độc lập. |
| Coi broker transaction là exactly-once payment. | HTTP payment ngoài broker có thể lặp. | External idempotency/reconciliation. |
| Dùng user-supplied key để lấy receipt mà không authorization. | Lộ trạng thái/receipt của tenant khác. | Bind key với principal và resource. |
| Log operation keys chứa email/PII. | Rò rỉ dữ liệu trong log/metrics. | Opaque IDs, masking, label cardinality. |
| Chỉ test happy path một message. | Không thấy crash window, race, replay. | Test matrix có duplicate/concurrency/restart. |
| Một operation có final FAILURE nhưng duplicate được xem là success. | Sai business outcome. | Lưu/đọc final state với semantics rõ. |

## 22. Bài tập thực hành

1. **Đọc Message ID:** tạo hai Spring `Message<ChargeCommand>` từ cùng payload, in `MessageHeaders.ID` và operationId; mô tả vì sao một ID có thể khác nhưng operation vẫn giống.
2. **Dedupe fake:** dùng `InMemoryIdempotentChargeReceiver` xử lý cùng command ba lần, assert chỉ một simulated charge.
3. **Key conflict:** giữ operationId nhưng đổi amount; xác minh `OPERATION_CONFLICT` thay vì return success cũ.
4. **Same order, two operations:** tạo CHARGE và ADJUSTMENT trên một order, chọn hai operation IDs khác nhau rồi kiểm tra cả hai đều được xử lý.
5. **Multi-tenant:** cùng local operationId ở hai tenants; verify mỗi tenant có state riêng và auth vẫn được kiểm tra.
6. **Consumer scope:** cho BillingProjection và NotificationService xử lý cùng `eventId`; thiết kế key để không chặn nhầm nhánh.
7. **Delimiter collision:** tạo các thành phần key chứa dấu `:`, kiểm tra encoding không nhập nhằng.
8. **Stable normalization:** cùng amount `100000` và `100000.00`, thử fingerprint theo policy để xác nhận cùng operation khi hợp lệ.
9. **Premature SEEN marker:** đánh dấu SEEN trước handler rồi giả lập crash, chỉ ra vì sao retry bị bỏ nhầm.
10. **Post-commit marker:** giả lập business commit trước khi ghi marker, rồi crash; thiết kế cách ngăn side effect lặp.
11. **Operation state machine:** thêm `IN_PROGRESS`/`COMPLETED`/`UNKNOWN` và transitions vào fake, test không trả COMPLETED từ state UNKNOWN.
12. **Durable inbox:** tạo bảng có unique key `(tenant_id, consumer_name, operation_id)`; kiểm thử hai transactions cố tạo cùng key.
13. **Atomic DB work:** ghi một business projection và receipt trong cùng DB transaction; kill transaction giữa chừng rồi xác minh rollback consistent.
14. **Remote payment:** fake remote provider hỗ trợ idempotency key và status query; mô phỏng commit success rồi mất response, retry không charge lại.
15. **Concurrent workers:** dùng hai threads và nhiều process thử cùng key, chứng minh unique operation effect tại DB/provider.
16. **Lease/fencing:** worker A giữ lease cũ, B có lease mới; thử để A commit và xác minh bị chặn bởi version guard.
17. **Spring Integration DSL:** cấu hình `ChargeGateway` → handler, gọi lại cùng command và assert returned receipt giống nhau.
18. **IdempotentReceiverInterceptor:** dùng `MetadataStoreSelector` hoặc selector tương đương, test key mới và duplicate, kiểm tra thực tế mark/discard/error behavior theo config.
19. **Retry advice scope:** gây lỗi ở handler sau khi selector ghi SEEN; kiểm tra retry có bị chặn sai không và thay thiết kế nếu cần.
20. **Router/Recipient List:** dùng một eventId gửi tới hai consumer, triển khai consumer-specific keys rồi thử redelivery.
21. **Splitter:** chia batch thành ba items cùng correlation ID, chọn per-item operation keys và tránh chặn nhầm item thứ hai.
22. **Aggregator:** gửi `I-1, I-1, I-2` thay vì `I-1, I-2, I-3`; chứng minh duplicate không thể thay missing child.
23. **Claim Check replay:** tạo claim mới cho cùng business operation, kiểm tra ledger vẫn trả receipt cũ khi payment đã hoàn tất.
24. **Broker integration:** gửi event qua adapter, thay đổi Spring Message ID lúc deserialize, kiểm tra business key còn nguyên và duplicate được xử lý đúng.
25. **DLQ replay:** cho event quay lại sau TTL ngắn, chứng minh rủi ro effect lặp; thiết kế retention/tombstone theo horizon thực.
26. **Authorization:** caller tenant B tự gửi operationId của tenant A; xác nhận không nhận được receipt hoặc trạng thái không được phép.
27. **Monitoring:** tạo log `OPERATION_ACQUIRED`, `OPERATION_COMPLETED`, `DUPLICATE_RESULT_RETURNED` và dashboard per-reason không chứa high-cardinality labels.
28. **Failure runbook:** viết luồng recovery cho `COMPLETED`, `IN_PROGRESS`, `UNKNOWN`, `FAILED_RETRYABLE` và `REJECTED_CONFLICT`, phân biệt trường hợp cần reconciliation.

### Tiêu chí đánh giá một implementation

- Một logical operation có **key ổn định** qua retry, broker redelivery và message rebuild không?
- Khóa có phân biệt tenant, consumer và operation hợp lệ khác nhau không?
- Same key, different payload được phát hiện hay bị coi là duplicate success?
- State phân biệt **đã thấy** với **đã hoàn tất** không?
- Durable record có sống qua crash, multi-node và replay horizon không?
- External side effect có remote idempotency hoặc recovery/reconciliation không?
- Gateway duplicate có trả previous receipt/status đúng contract không?
- Retry/DLQ/callback bị timeout có được xử lý mà không tạo operation mới mù quáng không?
- Các nhánh Filter/Router/Splitter/Aggregator có dùng đúng cấp identity không?
- Có kiểm thử cả nơi lưu state, transport và nơi commit effect thay vì chỉ mock không?

## 23. Câu hỏi tự kiểm tra

**Câu 1:** Hai Spring messages có `MessageHeaders.ID` khác nhau nhưng cùng `operationId`. Chúng có thể là một business duplicate không?

**Có.** Nếu cùng logical operation được retry hoặc message được tạo lại, Spring message IDs khác không chứng minh đó là operation mới.

**Câu 2:** Hai messages cùng `orderId` nhưng một lệnh CHARGE và một lệnh REFUND. Có nên dedupe bằng `orderId` không?

**Không.** Chúng là hai business operations khác nhau; khóa phải phân biệt loại thao tác và lần thực hiện.

**Câu 3:** `correlationId` có thể thay `operationId` không?

**Không mặc định.** Correlation dùng gom message group/request–reply, có thể bao gồm nhiều child operations; một group ID không đủ để chống trùng từng side effect.

**Câu 4:** Tại sao `traceId` không phải idempotency key?

**Vì** nhiều operations có thể cùng trace, và retry có thể tạo trace mới. Trace phục vụ observability, không định nghĩa identity nghiệp vụ.

**Câu 5:** Nếu một consumer đã ghi `SEEN` rồi crash trước khi handler chạy, retry sẽ thế nào?

Nếu selector chỉ kiểm tra SEEN, retry có thể bị chặn sai. Cần state/recovery/transaction thích hợp; SEEN không phải COMPLETED.

**Câu 6:** Nếu handler đã commit nhưng process chết trước khi ghi SEEN?

Một redelivery có thể gọi lại handler. Cần external idempotency, durable result reconciliation hoặc transaction chung khi khả thi.

**Câu 7:** Khi nào một duplicate có thể trả previous receipt?

Khi key, tenant/resource, fingerprint và **COMPLETED outcome có thẩm quyền** khớp theo hợp đồng. Không trả receipt cho một token giả hoặc operation còn UNKNOWN.

**Câu 8:** Cùng operationId nhưng amount khác có nên được coi là duplicate hợp lệ?

**Không.** Cần kiểm tra fingerprint và từ chối/điều tra key conflict thay vì trả SUCCESS cũ.

**Câu 9:** Vì sao cần thêm `consumerName` vào event dedupe key?

Vì một sự kiện có thể cần tạo tác động độc lập ở Billing, Notification và Audit; trạng thái đã xử lý ở một consumer không nên chặn consumer khác.

**Câu 10:** Dùng `SimpleMetadataStore` trên một pod có bảo đảm dedupe khi chạy ba pods không?

**Không.** Store trong memory ở từng pod không tạo atomic shared state giữa pods hoặc giữ dữ liệu sau restart.

**Câu 11:** `ConcurrentMetadataStore.putIfAbsent` có đồng nghĩa business mutation và marker luôn commit cùng lúc?

**Không.** Atomicity của putIfAbsent chỉ áp dụng theo store contract, không bao trùm external HTTP payment trừ khi có cơ chế giao dịch/idempotency bổ sung.

**Câu 12:** Gateway trả timeout có nghĩa payment chưa charge không?

**Không.** Payment có thể đã commit nhưng response thất lạc; đó là tình huống UNKNOWN cần reconcile.

**Câu 13:** Với Inbox/DB transaction duy nhất, có thể bảo vệ duplicate của business mutation trong cùng DB không?

**Có thể**, nếu key unique, khóa/transaction và business update/receipt thực sự thuộc cùng transaction và recovery đúng. Điều này không tự mở rộng sang hệ thống ngoài.

**Câu 14:** Nếu một message đi qua Transformer rồi có Spring Message ID mới, làm thế nào giữ idempotency?

Giữ stable business `eventId`/`operationId` trong payload hoặc metadata đã được chuẩn hóa/propagate; derive key từ nguồn có thẩm quyền, không từ ID instance mới.

**Câu 15:** Một Splitter tạo ba child với cùng correlation ID. Dedupe toàn bộ bằng correlation ID có đúng không?

**Không.** Ba child là các phần khác nhau. Cần per-item identity, ví dụ `batchProcessingId + itemId`.

**Câu 16:** Resequencer có ngăn duplicate side effect không?

**Không tự động.** Nó phục hồi thứ tự phát message theo sequence contract; idempotency cần bảo vệ từng operation.

**Câu 17:** Claim Check cấp token mới cho cùng original operation, có nên tạo charge mới không?

**Không mặc định.** Claim ID là payload reference; nếu replay cùng operation, giữ operation ID và check durable receipt/idempotency.

**Câu 18:** Nếu metadata store unavailable, có thể coi key là mới và tiếp tục payment không?

**Không nên mặc định.** Không biết operation đã xử lý hay chưa; cần policy fail closed hoặc remote idempotency/reconciliation được xác nhận.

**Câu 19:** Nếu record TTL hết nhưng broker còn có thể replay, điều gì xảy ra?

Một duplicate cũ có thể được xem là operation mới. Cần retention/tombstone/replay policy đủ cho horizon mong đợi.

**Câu 20:** IdempotentReceiverInterceptor tự làm tất cả duplicate an toàn khi handler có side effect không?

**Không.** Advice/selector giúp phát hiện/đánh dấu hoặc xử lý duplicate theo cấu hình. Với side effect quan trọng, còn cần durable operation state, receipt, concurrency control và idempotency ở ranh giới commit.

**Câu 21:** Có thể dùng `Object.hashCode()` để lưu operation fingerprint xuyên deploy không?

**Không nên.** Dùng canonical serialization và cơ chế fingerprint ổn định, có version khi cần; hash không thay authorization.

**Câu 22:** Một duplicate bị discard thì có chắc Gateway không timeout không?

**Không.** Nếu caller chờ request–reply, discard im lặng có thể làm mất reply. Cần thiết kế trả receipt/status hoặc error contract phù hợp.

**Câu 23:** Tại sao state IN_PROGRESS cần lease/fencing?

Vì worker có thể crash, pause hoặc mất kết nối; lease giúp recovery, còn fencing/version bảo vệ trường hợp worker cũ tiếp tục chạy sau khi lease đã được cấp lại.

**Câu 24:** “Exactly-once” có thể được kết luận chỉ vì broker transaction đã bật?

**Không.** Phải chỉ ra phạm vi và ranh giới. Một remote payment API nằm ngoài broker transaction có thể vẫn bị gọi lại.

## 24. Hướng dẫn ra quyết định nhanh

~~~mermaid
flowchart TD
    I[Message tới receiver] --> A{Đã xác thực và authorize?}
    A -->|Không| DENY[Reject / security audit]
    A -->|Có| K[Derive stable scoped business key]
    K --> F{Fingerprint hợp lệ?}
    F -->|Không| CONFLICT[Reject conflict]
    F -->|Có| L{Durable operation state}
    L -->|COMPLETED| OLD[Return previous receipt / duplicate ack]
    L -->|IN_PROGRESS| WAIT[Wait / PENDING / recovery policy]
    L -->|UNKNOWN| RECON[Reconcile external outcome]
    L -->|New or safe retry| WORK[Acquire key + execute safely]
    WORK --> COMMIT[Persist authoritative outcome]
    COMMIT --> ACK[Reply / acknowledge transport]
~~~

Sơ đồ này giúp đặt câu hỏi **trước khi gọi side effect**, không phải một thuật toán transaction hoàn chỉnh. Một implementation phải bảo vệ race ở bước acquire, phân biệt failed final/retryable và có chính sách xử lý khi ledger không sẵn sàng.

## 25. Kết luận

**Message ID và idempotency key không phải cùng một khái niệm.** Spring `MessageHeaders.ID` nhận diện một message cụ thể; một business event hoặc operation có thể trải qua nhiều messages, deliveries, retries, adapters, JVM và trace contexts. Vì vậy **Idempotent Receiver nên xác định duplicate theo stable business identity** ở đúng phạm vi tenant, consumer và operation, thay vì mặc định dùng ID của message instance, timestamp hoặc correlation group.

Với Spring Integration, `IdempotentReceiverInterceptor`, `MetadataStoreSelector` và `ConcurrentMetadataStore` có thể hỗ trợ kiểm tra key ở endpoint. Nhưng một marker `SEEN` không đồng nghĩa operation đã hoàn tất, một `SimpleMetadataStore` không phải durable ledger, và việc discard duplicate không tự trả previous receipt cho Gateway. Đối với side effect quan trọng, phải kết hợp **unique operation key, payload fingerprint, durable state/receipt, concurrency control, idempotency tại external API khi có và reconciliation cho trạng thái UNKNOWN**.

Trong module `SPRING_INTEGRATION_PATTERN`, hãy kiểm thử từng tầng: **key derivation → in-memory/unit behavior → Spring Integration flow/advice → database/transport → system crash/retry**. Khi phối hợp với Router, Filter, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Claim Check, Gateway và error channel, hãy luôn phân biệt **message nào đang được giao**, **operation nào cần được thực hiện**, **kết quả nào đã được commit**, và **lần gửi lại nào chỉ nên đọc kết quả cũ**. Đó là nền tảng để xây dựng luồng thông điệp đáng tin cậy, dễ mở rộng và truy nguyên được khi hệ thống gặp lỗi.
