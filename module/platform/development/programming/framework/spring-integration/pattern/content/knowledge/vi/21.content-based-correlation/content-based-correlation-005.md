# Không dùng giá trị dễ thay đổi làm correlation key

Trong một luồng tích hợp, các message thuộc cùng một nghiệp vụ có thể đến từ nhiều service, xuất hiện ở những thời điểm khác nhau và mang dữ liệu đã được cập nhật. **Content-based correlation** là cách xác định mối liên hệ giữa message bằng **giá trị trong nội dung nghiệp vụ**, thay vì chỉ dựa vào thứ tự đến hoặc một message ID riêng lẻ. Lợi ích là các sự kiện như đặt hàng, thanh toán và giữ tồn kho có thể được gom lại thành một kết quả; rủi ro là **chọn sai giá trị làm correlation key** sẽ khiến các message bị tách nhóm hoặc trộn nhóm một cách âm thầm.

Bài **Không dùng giá trị dễ thay đổi làm correlation key** thuộc chương **Content-based correlation**, module **SPRING_INTEGRATION_PATTERN**. Module hướng tới triển khai Enterprise Integration Patterns với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý.

**Nguyên tắc trọng tâm:** khóa tương quan phải nhận diện **cùng một đơn vị nghiệp vụ cần hội tụ**, **ổn định xuyên suốt vòng đời nhóm**, **không nhập nhằng giữa những nhóm khác nhau** và **được kiểm chứng tại ranh giới tin cậy**. Những thuộc tính như email, tên, địa chỉ, trạng thái, số tiền hoặc thời gian cập nhật thường **không đáp ứng đủ** các điều kiện này.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa content-based correlation và phân biệt nó với routing theo nội dung.
2. Giải thích vì sao một thuộc tính **có trong payload** không có nghĩa nó là correlation key thích hợp.
3. Nhận ra hai kiểu lỗi: **một nghiệp vụ bị chia thành nhiều group** và **nhiều nghiệp vụ bị trộn vào cùng group**.
4. Chọn một khóa ổn định như `(tenantId, orderId)` hoặc `(tenantId, orderId, workflowRunId)` theo phạm vi nghiệp vụ.
5. Phân biệt correlation key với `eventId`, `MessageHeaders.ID`, `traceId`, `sequenceNumber` và `sequenceSize`.
6. Tách việc **validate/normalize key tại ingress** khỏi việc **gom message** trong Aggregator.
7. Triển khai custom correlation strategy bằng Java 17 và Spring Integration Java DSL.
8. Viết release/output processor để chỉ phát kết quả khi có đủ những loại event cần thiết.
9. Kiểm thử việc email/trạng thái đổi giữa các event, hai đơn chung email, hai tenant trùng order ID và message đến sai thứ tự.
10. Thiết kế duplicate handling, late arrivals, reprocessing, key migration, retention và idempotency.
11. Giải thích hậu quả của key không ổn định tới `MessageGroupStore`, throughput, timeout và vận hành.
12. Áp dụng nguyên tắc này vào Aggregator, Resequencer, Gateway và những luồng xử lý bất đồng bộ khác.

## 2. Khi correlation key bị chọn sai

Giả sử ứng dụng muốn phát `OrderReady` khi đủ ba dữ liệu:

- `OrderRegistered`: đơn đã được tạo;
- `PaymentCaptured`: thanh toán đã được xác nhận;
- `InventoryReserved`: tồn kho đã được giữ.

Các sự kiện có thể đến cách nhau hàng giây hoặc hàng phút.

~~~mermaid
flowchart LR
    O["OrderRegistered"] --> C["Correlation strategy"]
    P["PaymentCaptured"] --> C
    I["InventoryReserved"] --> C
    C --> G[("MessageGroupStore")]
    G --> R{"Đủ 3 loại?"}
    R -->|Không| W["Giữ group, chờ"]
    R -->|Có| OUT["OrderReady"]
~~~

**Correlation strategy** trả lời câu hỏi: message này thuộc **group nào**? Nếu chọn theo `orderId` ổn định, ba event về cùng một đơn có thể gặp nhau. Nếu chọn theo `customerEmail`, hệ thống có nguy cơ sai theo hai hướng.

### 2.1. Lỗi thứ nhất: một đơn bị tách thành hai nhóm

~~~text
10:00 OrderRegistered
  orderId = ORDER-101
  email = alice@old.example.invalid

10:01 Customer cập nhật email

10:02 PaymentCaptured
  orderId = ORDER-101
  email = alice@new.example.invalid

10:03 InventoryReserved
  orderId = ORDER-101
  email = alice@new.example.invalid
~~~

Nếu correlation key = email:

~~~text
Group "alice@old.example.invalid":
  OrderRegistered(ORDER-101)
  -> thiếu Payment + Inventory

Group "alice@new.example.invalid":
  PaymentCaptured(ORDER-101)
  InventoryReserved(ORDER-101)
  -> thiếu OrderRegistered
~~~

Cả hai group đều có thể **chờ mãi** hoặc hết hạn dù cả ba event thực tế đã được gửi.

Nếu correlation key = `(tenantId, orderId)`:

~~~text
Group ("tenant-a", "ORDER-101"):
  OrderRegistered
  PaymentCaptured
  InventoryReserved
  -> đủ, có thể tạo OrderReady
~~~

### 2.2. Lỗi thứ hai: hai đơn bị trộn làm một

Một khách có thể đặt nhiều đơn:

~~~text
OrderRegistered(ORDER-101, email=alice@example.invalid)
OrderRegistered(ORDER-102, email=alice@example.invalid)
PaymentCaptured(ORDER-102, email=alice@example.invalid)
InventoryReserved(ORDER-101, email=alice@example.invalid)
~~~

Nếu correlation theo email, tất cả nằm cùng group dù **order IDs khác nhau**. Một release strategy chỉ đếm message có thể tạo kết quả thanh toán/tồn kho **sai đơn**.

**Lưu ý:** một khóa không đổi nhưng **không đủ phân biệt** cũng nguy hiểm như một khóa thay đổi. Email có thể ít thay đổi trong một tuần, nhưng nó vẫn không phải định danh cho *một đơn hàng cụ thể*.

## 3. Correlation khác với Filter và Router theo nội dung

Cả ba đều có thể đọc payload, nhưng mục đích không giống nhau:

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| **Content-based Router** | Message cần đi tới channel nào? | `amount >= 1000` → high-value |
| **Filter** | Message có được đi tiếp không? | `status == APPROVED` |
| **Content-based Correlation** | Message thuộc nhóm nghiệp vụ nào? | `(tenantId, orderId)` |
| **Aggregator** | Nhóm khi nào đủ, output là gì? | Đủ Order, Payment, Inventory |
| **Resequencer** | Các message liên quan cần phát theo thứ tự nào? | `sequenceNumber=1..N` |

Một Router **có thể dùng trạng thái thay đổi** để chọn nhánh theo chính sách hiện tại; đó không có nghĩa trạng thái là một correlation key phù hợp. Correlation phải **ổn định suốt thời gian các message cần hội tụ**.

Ví dụ:

~~~java
// Routing theo một quyết định kinh doanh hiện tại:
String route = order.amount().compareTo(limit) >= 0
        ? "orders.highValue"
        : "orders.standard";

// Correlation theo identity ổn định:
BusinessKey key = new BusinessKey(
        order.tenantId(),
        order.orderId());
~~~

Một đơn được tăng tổng tiền từ 900 lên 1.100 có thể thay đổi **routing policy**, nhưng vẫn là **cùng một đơn** cần nhận các event thanh toán/tồn kho.

## 4. Tiêu chí của một correlation key tốt

Một giá trị có vẻ duy nhất ở thời điểm hiện tại chưa chắc đủ. Khóa cần thỏa các điều kiện dưới đây.

| Tiêu chí | Câu hỏi kiểm tra | Hậu quả nếu không thỏa |
|---|---|---|
| **Ổn định** | Key có đổi từ lúc group mở đến lúc đóng không? | Một business flow bị chia nhiều group |
| **Đúng phạm vi** | Key định danh đúng *đơn vị cần gom* không? | Nhiều order cùng customer bị trộn |
| **Đủ duy nhất** | Hai nghiệp vụ khác nhau có thể cùng key không? | Cross-order/cross-tenant contamination |
| **Có ở mọi event** | Mọi producer có thể cung cấp/tra được key không? | Message thiếu key, bị reject/sai nhóm |
| **Nhất quán định dạng** | Producer dùng cùng kiểu, canonical form không? | `ord-1` và `ORD-1` thành hai nhóm |
| **Được xác thực** | Tenant/ownership có được kiểm chứng không? | Client có thể trộn group trái quyền |
| **Tuổi thọ phù hợp** | Key có được tái sử dụng trong kỳ hạn lưu group không? | Reprocessing tạo collision với group cũ |
| **Có thể lưu trữ** | Key hoạt động với store/serializer/distributed lock không? | Restart/multi-instance fail |
| **Quan sát được an toàn** | Có cách trace mà không lộ PII không? | Rò rỉ log/metric hoặc khó debug |

Với quy trình OrderReady, `tenantId` và `orderId` là **ứng viên** hợp lý nếu chúng là ID nội bộ được cam kết ổn định; cần xác nhận hợp đồng dữ liệu thay vì giả định mọi trường tên `orderId` đều đúng.

### 4.1. Một điều kiện kiểm tra hữu ích

Với các event `e1` và `e2` thuộc cùng group nghiệp vụ G:

~~~text
businessGroup(e1) == businessGroup(e2)
     ==> correlationKey(e1) == correlationKey(e2)
~~~

Với các event thuộc hai group **khác nhau**:

~~~text
businessGroup(e1) != businessGroup(e2)
     ==> correlationKey(e1) != correlationKey(e2)
~~~

Hai điều kiện diễn đạt **nhất quán trong group** và **phân biệt giữa group**. Chúng là tiêu chuẩn thiết kế logic, không phải assertion rằng thế giới thực luôn có định danh lý tưởng. Khi nguồn dữ liệu chưa bảo đảm chúng, phải thiết kế mapping hoặc quy trình reconciliation.

### 4.2. Phạm vi của group phải rõ

Những thứ có thể tạo group khác nhau:

- Một đơn hàng cụ thể.
- Một lần thanh toán (payment attempt) cụ thể.
- Một lần thực hiện workflow.
- Một batch dữ liệu có batch ID.
- Một phiên xử lý tài liệu.
- Một khoảng thời gian (window) có ID cố định.

Không chọn `customerId` cho group theo order nếu một khách có nhiều order; cũng không chọn `orderId` cho group theo **payment attempt** nếu một đơn có nhiều attempt và cần giữ chúng tách biệt.

## 5. Những giá trị **không nên** làm key theo mặc định

### 5.1. Email, số điện thoại, tên người dùng

- Khách có thể cập nhật liên hệ.
- Email/điện thoại có thể được tái sử dụng hoặc chia sẻ.
- Việc viết hoa, Unicode, khoảng trắng hay normalize có thể khác nhau.
- Đây có thể là dữ liệu cá nhân cần bảo vệ khỏi logs/metrics.
- Nhiều đơn của một khách cùng email vẫn là các group khác nhau.

Dùng một **customer ID nội bộ ổn định** nếu group thực sự là theo customer; dùng **order ID** nếu group theo order.

### 5.2. Trạng thái workflow

~~~text
NEW -> VALIDATED -> PAID -> PACKING -> SHIPPED
~~~

Nếu nhóm theo `status`, mỗi bước tạo một group khác. Trạng thái giúp **Filter/Router**, không phải định danh một nghiệp vụ duy nhất.

### 5.3. Amount, balance, score, priority, tier

~~~text
amount = 900.00 -> chỉnh đơn -> 1050.00
riskScore = 0.20 -> model tính lại -> 0.84
priority = NORMAL -> VIP
~~~

Chúng là **thuộc tính nghiệp vụ** và có thể cập nhật. Chúng cũng thường **không duy nhất**, vì nhiều đơn có cùng amount/tier.

### 5.4. Timestamps

`createdAt` có thể ổn định nếu được coi là một thành phần của ID được quản lý, nhưng bản thân timestamp không phải lúc nào duy nhất. `updatedAt` **chắc chắn thường thay đổi**. Giờ hệ thống có thể lệch giữa các producer.

Đừng dùng `System.currentTimeMillis()` hoặc `Instant.now()` khi tính correlation strategy: cùng một event gửi lại sau 10 giây sẽ rơi vào group khác.

### 5.5. Display name, SKU label, địa chỉ, URL

Nhãn hiển thị, tên sản phẩm, địa chỉ vận chuyển hay đường dẫn ngoài có thể được cập nhật, chuẩn hóa hoặc thay đổi do redirect. Nếu domain có một **canonical ID bất biến**, nên dùng ID đó; nếu không, cần định nghĩa mapping/version rõ.

### 5.6. ID tự sinh cho từng message

`MessageHeaders.ID` hoặc `eventId` thường là duy nhất **cho từng event**, không phải **cho nhóm các event khác nhau cùng một đơn**. Nếu dùng eventId làm key để gom Order + Payment + Inventory, ba event sẽ nằm trong ba group riêng.

## 6. Phân biệt các định danh thường gặp

| Định danh | Đối tượng nhận diện | Dùng làm correlation key khi nào? |
|---|---|---|
| `MessageHeaders.ID` | Một Spring Message instance | Không cho group có nhiều event |
| `eventId` | Một business event riêng | Để dedup/replay, thường không cho group OrderReady |
| `traceId` | Một chuỗi xử lý/tracing context | Không thay business group key |
| `spanId` | Một bước trong distributed trace | Không |
| `customerId` | Một customer | Chỉ nếu group đúng là theo customer |
| `orderId` | Một order | Phù hợp nếu group theo order và ID unique trong phạm vi |
| `tenantId` | Một tenant | Dùng cùng ID nghiệp vụ nếu ID có thể trùng giữa tenants |
| `paymentAttemptId` | Một lần thanh toán | Khi group theo payment attempt |
| `workflowRunId` | Một lần thực hiện workflow | Khi mỗi run cần group riêng |
| `sequenceNumber` | Vị trí một part | Không thể định danh cả group |
| `sequenceSize` | Tổng part dự kiến | Không thể định danh cả group |
| `correlationId` header | Metadata framework hoặc producer cung cấp | Chỉ khi nội dung/nguồn đã được kiểm chứng đúng group |

**Tên header không phải bằng chứng ngữ nghĩa.** Một producer có thể gắn `correlationId` bằng một request ID mới cho mỗi HTTP call; các event của cùng order khi ấy vẫn có correlation ID khác nhau. Đừng dùng nó mù quáng làm business key.

## 7. Khóa ghép: tenantId + orderId

Nếu `orderId` chỉ unique trong mỗi tenant, khóa group cần cả hai thành phần.

~~~text
Tenant A, ORDER-101 -> Group A/ORDER-101
Tenant B, ORDER-101 -> Group B/ORDER-101
~~~

Nếu dùng mỗi `orderId`, hai tenant có thể bị trộn cùng group dù khác tài khoản và quyền truy cập.

### 7.1. Dùng value object thay vì nối chuỗi ngây thơ

~~~java
import java.io.Serializable;

public record BusinessKey(
        String tenantId,
        String orderId
) implements Serializable {

    public BusinessKey {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "TENANT_ID_REQUIRED");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "ORDER_ID_REQUIRED");
        }
    }
}
~~~

`record` tự có `equals` và `hashCode` theo hai field, giúp so sánh group key đúng về **giá trị**.

Nếu tùy tiện nối chuỗi:

~~~java
String key = tenantId + ":" + orderId;
~~~

có thể xảy ra collision nếu giá trị chứa dấu phân cách:

~~~text
tenantId="a:b", orderId="c" -> "a:b:c"
tenantId="a",   orderId="b:c" -> "a:b:c"
~~~

Một value object giải quyết collision của phép nối và thể hiện rõ tên thành phần. Với distributed MessageGroupStore, hãy xác minh **serialization/stable equality/key mapping** trên backend thực tế. Không giả định mọi store hoặc serializer có thể nhận mọi object Java tự định nghĩa mà không cấu hình.

### 7.2. Có nên thêm workflowRunId?

Nếu cùng một order trải qua nhiều workflow chạy lại, cùng một `(tenantId, orderId)` có thể không đủ phân biệt **lần xử lý thứ nhất** và **lần reprocess thứ hai**.

~~~java
import java.io.Serializable;

public record RunKey(
        String tenantId,
        String orderId,
        String workflowRunId
) implements Serializable {}
~~~

Chỉ thêm `workflowRunId` nếu **mọi producer** tham gia group cùng biết một run ID cố định trong suốt run. Nếu mỗi service tự tạo run ID mới, khóa ghép khiến event lại bị chia nhóm.

Với một workflow chỉ nên có một `OrderReady` tồn tại cho mỗi order, `(tenantId, orderId)` cộng idempotency có thể là lựa chọn đúng hơn; không phải cứ thêm nhiều trường thì correlation sẽ an toàn hơn.

## 8. Chọn đúng đơn vị cần gom trước khi viết code

Trước khi mở IDE, hãy hoàn thiện bảng contract này:

| Thành phần | Ví dụ |
|---|---|
| Business group | Một đơn chờ ba event để tạo OrderReady |
| Correlation key | `BusinessKey(tenantId, orderId)` |
| Các loại part | OrderRegistered, PaymentCaptured, InventoryReserved |
| Group release | Có đúng một part hợp lệ mỗi loại |
| Key xuất hiện ở đâu | Payload của từng event |
| Canonical ID từ đâu | Order service/tenant registry đã xác thực |
| Duplicate policy | Dedup eventId hoặc reject trùng loại |
| Missing part | Timeout/expiry + incomplete group outcome |
| Late part | Reject, correction hoặc reconciliation theo contract |
| Reprocess | Có version/run policy và output idempotency |
| Output | `OrderReady(tenantId, orderId, paymentId, reservationId, amount)` |

Nếu không thể điền mục **Canonical ID từ đâu**, chưa nên viết correlation strategy bằng một chuỗi bất kỳ có sẵn trong payload.

## 9. Event model Java 17: giữ stable ID, cho phép mutable snapshot

Để chứng minh được hai ý **identity không đổi** và **thuộc tính có thể đổi**, ta định nghĩa một sealed event hierarchy với `tenantId`, `orderId`, `eventId` chung. `customerEmailSnapshot` được đưa vào các event chỉ để minh họa dữ liệu snapshot có thể thay đổi giữa các nguồn.

~~~java
import java.math.BigDecimal;

public sealed interface OrderPart
        permits OrderRegistered, PaymentCaptured, InventoryReserved {

    String eventId();

    String tenantId();

    String orderId();

    String customerEmailSnapshot();

    default BusinessKey businessKey() {
        return new BusinessKey(tenantId(), orderId());
    }
}

public record OrderRegistered(
        String eventId,
        String tenantId,
        String orderId,
        String customerEmailSnapshot,
        BigDecimal amount
) implements OrderPart {}

public record PaymentCaptured(
        String eventId,
        String tenantId,
        String orderId,
        String customerEmailSnapshot,
        String paymentId
) implements OrderPart {}

public record InventoryReserved(
        String eventId,
        String tenantId,
        String orderId,
        String customerEmailSnapshot,
        String reservationId
) implements OrderPart {}

public record OrderReady(
        BusinessKey businessKey,
        BigDecimal amount,
        String paymentId,
        String reservationId
) {}
~~~

Các kiểu `public` top-level trong cùng code block dùng để trình bày; khi đưa vào project Java, **tách mỗi kiểu thành một source file cùng tên**. Java 17+ hỗ trợ record/sealed types; nếu hệ thống dùng Java phiên bản khác, cần model tương đương.

**Ghi chú bảo mật:** email snapshot trong ví dụ không cần thiết cho aggregation output thật. Hãy loại dữ liệu cá nhân khỏi event/headers nếu nghiệp vụ không cần; việc có email ở cả ba event chỉ để **minh họa rủi ro khi chọn nó làm key**.

### 9.1. Timeline với email thay đổi

~~~text
10:00 OrderRegistered(
  tenantId=tenant-a, orderId=ORDER-101,
  customerEmailSnapshot=alice@old.example.invalid)

10:05 PaymentCaptured(
  tenantId=tenant-a, orderId=ORDER-101,
  customerEmailSnapshot=alice@new.example.invalid)

10:06 InventoryReserved(
  tenantId=tenant-a, orderId=ORDER-101,
  customerEmailSnapshot=alice@new.example.invalid)
~~~

Tất cả các event có:

~~~java
new BusinessKey("tenant-a", "ORDER-101")
~~~

và vì thế thuộc **cùng group**, bất kể email snapshot có thay đổi hay không.

## 10. Một correlation strategy thuần, có validation

~~~java
import org.springframework.messaging.Message;

public final class StableOrderCorrelation {

    public BusinessKey key(Message<?> message) {
        if (!(message.getPayload() instanceof OrderPart part)) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_ORDER_PART");
        }

        if (part.eventId() == null
                || part.eventId().isBlank()) {
            throw new IllegalArgumentException(
                    "EVENT_ID_REQUIRED");
        }

        // BusinessKey constructor kiểm tra tenantId/orderId.
        return new BusinessKey(
                part.tenantId(),
                part.orderId());
    }
}
~~~

Ở đây correlation strategy là một **pure mapping** từ message sang stable business identity, không gọi API ngoài hoặc đọc clock:

~~~text
Message<OrderPart>
  -> validate ID
  -> BusinessKey(tenantId, orderId)
~~~

### 10.1. Không đưa status vào key

~~~java
// Anti-pattern: cùng đơn đổi trạng thái sẽ sang nhóm khác.
String unstable = part.orderId()
        + ":" + currentStatus;
~~~

Nếu `currentStatus` đổi từ NEW sang PAID, key đổi dù group vẫn cùng một đơn. Trạng thái có thể dùng trong release/output logic, **không phải định danh nhóm**.

### 10.2. Không gọi service tra email mới mỗi lần tính key

~~~java
// Anti-pattern: giá trị có thể khác giữa lần nhận và retry.
String unstable = customerService
        .lookupCurrentEmail(customerId);
~~~

Dù mỗi event mang customerId ổn định, lookup “email hiện tại” theo thời gian làm correlation phụ thuộc database state. Khi retry sau email update, **cùng một event** có thể ra key mới, tạo group khác. Dùng một ID canonical được xác định theo contract, không dùng thuộc tính "hiện tại" dễ thay đổi.

### 10.3. Không dùng clock hoặc random

~~~java
// Cả hai đều làm replay rơi vào nhóm khác.
String badKey1 = orderId + "-" + System.currentTimeMillis();
String badKey2 = orderId + "-" + java.util.UUID.randomUUID();
~~~

Random UUID phù hợp khi **tạo một ID group mới đúng một lần ở producer** và truyền nó nhất quán đến mọi part; nó **không phù hợp khi mỗi consumer tự tạo mới** ở correlation strategy.

## 11. Ingress validation và canonicalization

Cùng một logical ID có thể được gửi với nhiều biểu diễn:

~~~text
ORDER-101
order-101
 ORDER-101
urn:order:ORDER-101
~~~

Có nên tự trim/lowercase không? **Không luôn luôn.** Một số ID phân biệt chữ hoa/chữ thường; tự normalize có thể khiến hai ID thật bị nhập chung. Cần canonical form được **công bố bởi hệ thống chủ sở hữu ID**.

### 11.1. Nguyên tắc

- Validate định dạng trước khi đưa message vào Aggregator.
- Convert external ID sang canonical internal ID ở **adapter boundary**.
- Không để mỗi service tự định nghĩa luật normalize.
- Nếu ID đã chuẩn và case-sensitive, giữ nguyên.
- Nếu tenant ID bị gửi từ client, đối chiếu với tenant đã xác thực.
- Nếu có alias/merge, dùng mapping có version/history và quy trình nhất quán.

Ví dụ một adapter chỉ chấp nhận ID đã chuẩn:

~~~java
import java.util.regex.Pattern;

public final class OrderIdentityValidator {

    private static final Pattern ORDER_ID =
            Pattern.compile("ORDER-[A-Z0-9]+");

    public String requireCanonicalOrderId(String value) {
        if (value == null || !ORDER_ID.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "NON_CANONICAL_ORDER_ID");
        }
        return value;
    }
}
~~~

Đây là **ví dụ quy tắc nghiệp vụ**, không phải format mặc định của Spring Integration. Nếu hệ thống dùng UUID, Snowflake ID hay một schema khác, hãy thay bằng hợp đồng tương ứng.

### 11.2. Nếu cần mapping giữa external IDs

~~~text
Payment provider says: externalOrderRef="X-5002"
Order service says:     orderId="ORDER-101"
~~~

Không correlate trực tiếp `X-5002` với `ORDER-101` và kỳ vọng framework tự hiểu là một. Cần map rõ external reference sang canonical order ID:

~~~text
Payment adapter
  externalOrderRef="X-5002"
  -> trusted mapping
  -> orderId="ORDER-101"
  -> PaymentCaptured(tenant-a, ORDER-101, ...)
~~~

Nếu mapping không tồn tại hoặc không chắc chắn, **quarantine / retry reconciliation** thay vì tự đoán theo email hoặc amount.

## 12. Correlation trong Spring Integration Aggregator

Với Splitter thông thường, framework có thể tạo header `correlationId`/`sequenceSize` để Aggregator mặc định biết gom những part thuộc một split batch. Nhưng với **các sự kiện độc lập từ Order/Payment/Inventory services**, không thể giả định ba producer cùng dùng một `correlationId` mặc định.

Cần một **custom correlation strategy** trả về stable business key từ payload.

~~~mermaid
flowchart TD
    A["OrderRegistered"] --> N["Validate + canonicalize identity"]
    B["PaymentCaptured"] --> N
    C["InventoryReserved"] --> N
    N --> CORR["StableOrderCorrelation.key(message)"]
    CORR --> GROUP[("MessageGroupStore theo BusinessKey")]
    GROUP --> REL{"Release strategy"}
    REL -->|Chưa đủ| WAIT["Chờ thêm part"]
    REL -->|Đủ| OUT["OrderReady output processor"]
~~~

### 12.1. Correlation và release là hai trách nhiệm

Correlation strategy phải trả lời **group nào**. Release strategy trả lời **group đã hoàn tất chưa**.

Nếu group theo `BusinessKey` nhưng chỉ có OrderRegistered và PaymentCaptured, key vẫn đúng — đơn giản là **chưa đủ dữ liệu**. Không thêm một field trạng thái vào key chỉ để “biết đã thanh toán”.

### 12.2. Release strategy không thể chỉ đếm message

~~~text
OrderRegistered(ORDER-101)
PaymentCaptured(ORDER-101)
PaymentCaptured(ORDER-101)  // redelivery
~~~

Ba message không có nghĩa đã có InventoryReserved. Release policy nên kiểm tra đủ **đúng loại part**; phía trước cần dedup theo `eventId` và policy xử lý trùng.

## 13. Release policy và output processor

Ví dụ tập trung vào **happy path đúng một event mỗi loại**. Nó chủ ý **không nuốt duplicate** để người học thấy rằng duplicate cần được xử lý riêng.

### 13.1. Release khi đủ ba loại

~~~java
import org.springframework.integration.store.MessageGroup;

public final class OrderGroupReleasePolicy {

    public boolean complete(MessageGroup group) {
        long orders = count(group, OrderRegistered.class);
        long payments = count(group, PaymentCaptured.class);
        long inventory = count(group, InventoryReserved.class);

        return orders == 1
                && payments == 1
                && inventory == 1
                && group.size() == 3;
    }

    private long count(
            MessageGroup group, Class<?> type) {
        return group.getMessages().stream()
                .map(message -> message.getPayload())
                .filter(type::isInstance)
                .count();
    }
}
~~~

Nếu hai PaymentCaptured giống nhau được lưu, policy sẽ không release khi thiếu Inventory. **Nhưng** nếu duplicate làm group có bốn part, policy trên cũng không release dù có đủ ba loại. Trong hệ thống thực, cần deduplicate hoặc phân giải event versions **trước khi nhóm bị kẹt**, cùng group timeout/expiry phù hợp.

### 13.2. Domain assembler tạo OrderReady

~~~java
import java.util.List;
import java.util.Objects;

import org.springframework.integration.store.MessageGroup;

public final class OrderReadyProcessor {

    public OrderReady process(MessageGroup group) {
        OrderGroupReleasePolicy policy =
                new OrderGroupReleasePolicy();

        if (!policy.complete(group)) {
            throw new IllegalArgumentException(
                    "ORDER_GROUP_INCOMPLETE");
        }

        OrderRegistered order =
                exactlyOne(group, OrderRegistered.class);

        PaymentCaptured payment =
                exactlyOne(group, PaymentCaptured.class);

        InventoryReserved inventory =
                exactlyOne(group, InventoryReserved.class);

        BusinessKey key = order.businessKey();

        if (!key.equals(payment.businessKey())
                || !key.equals(inventory.businessKey())) {
            throw new IllegalStateException(
                    "BUSINESS_KEY_MISMATCH");
        }

        Objects.requireNonNull(order.amount(), "amount");
        if (order.amount().signum() < 0) {
            throw new IllegalArgumentException(
                    "ORDER_AMOUNT_INVALID");
        }

        return new OrderReady(
                key,
                order.amount(),
                payment.paymentId(),
                inventory.reservationId());
    }

    private <T extends OrderPart> T exactlyOne(
            MessageGroup group,
            Class<T> type) {

        List<T> matches = group.getMessages().stream()
                .map(message -> message.getPayload())
                .filter(type::isInstance)
                .map(type::cast)
                .toList();

        if (matches.size() != 1) {
            throw new IllegalArgumentException(
                    "MISSING_OR_DUPLICATE_" + type.getSimpleName());
        }

        return matches.get(0);
    }
}
~~~

**Vì sao assembler vẫn kiểm tra key?** Correlation strategy được kỳ vọng đưa event cùng key vào group, nhưng payload có thể sai hoặc bị biến đổi giữa các điểm. Việc xác minh lại invariant tại output boundary giúp chặn kết quả sai trước khi ghi DB hoặc phát event.

Ở production, nên bổ sung kiểm tra `eventId`, trạng thái thanh toán, tồn kho, amount/version, authorization và nguồn event. Đoạn code minh họa **cơ chế chọn stable key** và ghép ba sự kiện.
## 14. Java DSL: dùng stable business key để correlate

Với ba nguồn Order/Payment/Inventory độc lập, không thể giả định chúng đều phát header `correlationId` giống nhau như các part do Splitter tạo. Có thể cấu hình Aggregator với custom strategies:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class StableCorrelationConfiguration {

    @Bean(name = "order.parts.input")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.ready")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public StableOrderCorrelation correlation() {
        return new StableOrderCorrelation();
    }

    @Bean
    public OrderGroupReleasePolicy releasePolicy() {
        return new OrderGroupReleasePolicy();
    }

    @Bean
    public OrderReadyProcessor outputProcessor() {
        return new OrderReadyProcessor();
    }

    @Bean
    public IntegrationFlow stableOrderFlow(
            StableOrderCorrelation correlation,
            OrderGroupReleasePolicy release,
            OrderReadyProcessor processor) {

        return IntegrationFlow
                .from("order.parts.input")
                .aggregate(spec -> spec
                        .correlationStrategy(correlation::key)
                        .releaseStrategy(release::complete)
                        .outputProcessor(processor::process))
                .channel("orders.ready")
                .get();
    }
}
~~~

Flow xử lý:

~~~text
Message<OrderPart>
  -> StableOrderCorrelation: BusinessKey(tenantId, orderId)
  -> MessageGroupStore giữ group theo key
  -> OrderGroupReleasePolicy: đủ 3 loại part
  -> OrderReadyProcessor: tạo OrderReady
  -> orders.ready
~~~

`QueueChannel` ở ví dụ chỉ là test fixture trong một JVM. Khi triển khai thật, phải bổ sung timeout/expiry, duplicate handling, persistent group store nếu cần, transaction và error channel theo topology.

### 14.1. Các callback không được trộn trách nhiệm

- **Correlation strategy** không nên gọi DB tra email hiện tại hoặc tạo UUID mới.
- **Release strategy** không nên gửi email, ghi DB hoặc chọn output channel.
- **Output processor** nên xác minh lại business identity của cả nhóm.
- **Output channel** là đường gửi kết quả sau release, không quyết định nhóm.
- **Downstream handler** cần idempotency vì output có thể được giao lại.

`BusinessKey` là immutable record và so sánh theo value. Nhưng khi dùng persistent `MessageGroupStore`, cần xác minh serialization, equality và cách backend lưu group key.

## 15. Unit test: email đổi nhưng key không đổi

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.support.GenericMessage;

class StableOrderCorrelationTest {

    private final StableOrderCorrelation strategy =
            new StableOrderCorrelation();

    @Test
    void changedEmailStillProducesSameGroupKey() {
        OrderRegistered order = new OrderRegistered(
                "evt-o-1", "tenant-a", "ORDER-101",
                "alice@old.example.invalid",
                new BigDecimal("300.00"));

        PaymentCaptured payment = new PaymentCaptured(
                "evt-p-1", "tenant-a", "ORDER-101",
                "alice@new.example.invalid",
                "PAY-101");

        assertEquals(
                strategy.key(new GenericMessage<>(order)),
                strategy.key(new GenericMessage<>(payment)));
    }

    @Test
    void sameEmailDoesNotMergeTwoOrders() {
        OrderRegistered first = new OrderRegistered(
                "evt-o-1", "tenant-a", "ORDER-101",
                "alice@example.invalid",
                new BigDecimal("300.00"));

        OrderRegistered second = new OrderRegistered(
                "evt-o-2", "tenant-a", "ORDER-102",
                "alice@example.invalid",
                new BigDecimal("400.00"));

        assertNotEquals(
                strategy.key(new GenericMessage<>(first)),
                strategy.key(new GenericMessage<>(second)));
    }

    @Test
    void tenantIsPartOfTheGroupIdentity() {
        OrderRegistered a = new OrderRegistered(
                "evt-a", "tenant-a", "ORDER-101",
                "a@example.invalid",
                new BigDecimal("100.00"));

        OrderRegistered b = new OrderRegistered(
                "evt-b", "tenant-b", "ORDER-101",
                "b@example.invalid",
                new BigDecimal("200.00"));

        assertNotEquals(
                strategy.key(new GenericMessage<>(a)),
                strategy.key(new GenericMessage<>(b)));
    }

    @Test
    void blankOrderIdIsRejected() {
        OrderRegistered invalid = new OrderRegistered(
                "evt-invalid", "tenant-a", "",
                "a@example.invalid",
                new BigDecimal("100.00"));

        assertThrows(IllegalArgumentException.class,
                () -> strategy.key(new GenericMessage<>(invalid)));
    }
}
~~~

Test xác nhận tính **ổn định trong cùng group**, tính **phân biệt giữa group** và validation ID. Chúng không thay test authorization của tenant tại ingress.

## 16. Unit test release/output bằng MessageGroup

Dùng `SimpleMessageStore` tạo group cho test chiến lược:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.integration.store.MessageGroup;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.support.GenericMessage;

class OrderGroupReleasePolicyTest {

    @Test
    void waitsForAllThreeEventTypes() {
        BusinessKey key =
                new BusinessKey("tenant-a", "ORDER-101");

        SimpleMessageStore store = new SimpleMessageStore();

        store.addMessageToGroup(key, new GenericMessage<>(
                new OrderRegistered(
                        "evt-o", "tenant-a", "ORDER-101",
                        "old@example.invalid",
                        new BigDecimal("300.00"))));

        store.addMessageToGroup(key, new GenericMessage<>(
                new PaymentCaptured(
                        "evt-p", "tenant-a", "ORDER-101",
                        "new@example.invalid", "PAY-101")));

        OrderGroupReleasePolicy policy =
                new OrderGroupReleasePolicy();

        assertFalse(policy.complete(store.getMessageGroup(key)));

        store.addMessageToGroup(key, new GenericMessage<>(
                new InventoryReserved(
                        "evt-i", "tenant-a", "ORDER-101",
                        "new@example.invalid", "RES-101")));

        MessageGroup complete = store.getMessageGroup(key);
        assertTrue(policy.complete(complete));

        OrderReady ready =
                new OrderReadyProcessor().process(complete);

        assertEquals(key, ready.businessKey());
        assertEquals("PAY-101", ready.paymentId());
        assertEquals("RES-101", ready.reservationId());
        assertEquals(
                new BigDecimal("300.00"), ready.amount());
    }
}
~~~

Đây là test **business policies**; không thay thế integration test của chính Aggregator endpoint. Nếu group có hai PaymentCaptured trùng nhưng thiếu Inventory, `group.size()==3` là điều kiện không an toàn. Policy minh họa đếm từng loại, trong khi ứng dụng thật cần dedup theo `eventId` hoặc xử lý conflict trước khi lưu group.

## 17. Integration test qua Spring Integration channels

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = StableCorrelationConfiguration.class)
class StableCorrelationFlowTest {

    @Autowired
    @Qualifier("order.parts.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.ready")
    PollableChannel output;

    @Test
    void joinsEventsAfterEmailUpdate() {
        assertTrue(input.send(MessageBuilder.withPayload(
                new OrderRegistered(
                        "evt-o-101", "tenant-a", "ORDER-101",
                        "alice@old.example.invalid",
                        new BigDecimal("300.00")))
                .build()));

        assertNull(output.receive(0));

        assertTrue(input.send(MessageBuilder.withPayload(
                new PaymentCaptured(
                        "evt-p-101", "tenant-a", "ORDER-101",
                        "alice@new.example.invalid",
                        "PAY-101"))
                .build()));

        assertNull(output.receive(0));

        assertTrue(input.send(MessageBuilder.withPayload(
                new InventoryReserved(
                        "evt-i-101", "tenant-a", "ORDER-101",
                        "alice@new.example.invalid",
                        "RES-101"))
                .build()));

        Message<?> message = output.receive(1000);
        assertNotNull(message);
        assertInstanceOf(OrderReady.class, message.getPayload());

        OrderReady result = (OrderReady) message.getPayload();
        assertEquals(
                new BusinessKey("tenant-a", "ORDER-101"),
                result.businessKey());
        assertEquals("PAY-101", result.paymentId());
        assertEquals("RES-101", result.reservationId());
        assertEquals(
                new BigDecimal("300.00"), result.amount());

        assertNull(output.receive(0));
    }
}
~~~

Ở flow đồng bộ trong bộ nhớ, hai event đầu không làm Aggregator release; event thứ ba tạo một `OrderReady`. Email thay đổi không làm đổi group. Test không chứng minh exactly-once side effects, timeout, khả năng chịu restart hoặc nhiều instances.

### 17.1. Test interleaving hai đơn có cùng email

Gửi:

~~~text
A: OrderRegistered(ORDER-101, alice@example.invalid)
B: OrderRegistered(ORDER-102, alice@example.invalid)
B: PaymentCaptured(ORDER-102, alice@example.invalid)
A: InventoryReserved(ORDER-101, alice@example.invalid)
~~~

Kỳ vọng **chưa có output** vì cả A và B đều thiếu một part. Tiếp theo gửi Payment của A và Inventory của B, rồi assert có đúng **hai output tách biệt**, không nhầm payment/stock của hai đơn.

### 17.2. Test cùng orderId nhưng khác tenant

Gửi đủ ba event cho cả `tenant-a/ORDER-101` và `tenant-b/ORDER-101`. Hai output phải mang hai `BusinessKey` riêng, không trộn part. Tenant phải được xác thực trước khi message vào group.

### 17.3. Test isolation

Nếu các test dùng cached Spring ApplicationContext, những group chưa hoàn tất trong `SimpleMessageStore` có thể tồn tại tới test khác. Hãy dùng unique group IDs mỗi test, cleanup fixtures hoặc cô lập context.
## 18. Mapping external ID sang canonical key

Trong hệ thống phân tán, producer có thể dùng các reference khác nhau:

~~~text
Order service:
  tenantId=tenant-a, orderId=ORDER-101

Payment provider:
  externalOrderRef=EXT-5002, merchantAccount=ACCT-X

Inventory service:
  inventoryRequest=REQ-99, orderReference=ORDER-101
~~~

Content-based correlation không thể tự suy rằng `EXT-5002` và `ORDER-101` thuộc cùng đơn. Cần một bước **identity resolution** đáng tin trước khi đưa message vào Aggregator.

~~~mermaid
flowchart LR
    O["Order event"] --> V["Validate canonical key"]
    P["Payment external ref"] --> M["Trusted identity mapping"]
    M --> V
    I["Inventory reference"] --> V
    V --> C["Canonical OrderPart"]
    C --> A["Aggregator by BusinessKey"]
~~~

Các trách nhiệm của adapter:

1. Xác thực nguồn event, tenant hoặc merchant account.
2. Tra mapping external reference → canonical order ID.
3. Kiểm tra mapping không nhập nhằng, không thuộc tenant khác.
4. Chuyển thành `OrderPart` có đúng `tenantId` và `orderId`.
5. Khi mapping thiếu, xử lý retry bounded, quarantine hoặc reconciliation.
6. Không tự đoán group bằng email, số tiền hoặc địa chỉ nhận hàng.

### 18.1. Canonicalization không phải lowercase tùy ý

Nếu hệ thống chủ sở hữu ID cam kết `order-101` và `ORDER-101` là cùng một đơn, adapter có thể normalize. Nếu ID phân biệt hoa/thường, làm vậy có thể **trộn hai nghiệp vụ**.

Không dùng `trim()` hoặc `toLowerCase()` trên mọi ID chỉ vì muốn tránh lỗi nhập liệu. Hợp đồng canonical ID phải được xác định bởi hệ thống cấp ID, có test collision và quy tắc migration.

### 18.2. Không lookup giá trị hiện tại khi tính correlation

Một correlation strategy gọi API lấy "email hiện tại" ở mỗi lần chạy sẽ không còn ổn định sau khi email đổi hoặc khi event replay. Thay vào đó, resolve **business identity** ở adapter, giữ một key nhất quán và chỉ đánh giá pure mapping trong strategy.

## 19. Replay, duplicate và late arrival

### 19.1. Replay giữ business key không đổi

~~~text
Lần đầu:
  eventId=evt-pay-101
  MessageHeaders.ID=UUID-A
  BusinessKey=(tenant-a, ORDER-101)

Redelivery:
  eventId=evt-pay-101
  MessageHeaders.ID=UUID-B
  BusinessKey=(tenant-a, ORDER-101)
~~~

Một event có thể được tạo lại thành Spring Message mới với ID khác, nhưng vẫn phải thuộc group gốc. Không dùng `MessageHeaders.ID`, `Instant.now()` hoặc random UUID **được sinh tại consumer** để quyết định correlation.

### 19.2. Dùng eventId cho dedup, không làm key gom ba loại event

Có thể xây pipeline:

~~~text
Ingress -> Validate tenant/business ID
        -> Dedup by (sourceId,eventId)
        -> Aggregator by BusinessKey
        -> Output handler có idempotency
~~~

Trong nhiều hệ thống, `eventId` chỉ unique trong namespace của producer; cần ghép `sourceId`/`tenantId` thích hợp. Nếu cùng eventId được gửi với payload khác nhau, coi là **data integrity conflict**, không âm thầm chọn một bản.

### 19.3. Late arrival sau release

Nếu Inventory được phát lại sau khi `OrderReady` đã xử lý, một group hoàn tất có thể bị mở lại hoặc bị bỏ qua tùy cấu hình completion/expiry. Thiết kế phải có:

- Completed-group metadata/tombstone và thời gian retention hợp lý.
- Late arrival policy: discard, quarantine hoặc correction.
- Idempotent output handler và output event ID ổn định.
- Metric số replay, duplicate và late arrivals.
- Quy tắc rõ khi đó là một **business correction**, không phải redelivery đơn thuần.

**Khóa đúng chỉ bảo đảm group identity; không tự giải quyết exactly-once business side effects.**

## 20. Reprocessing và workflowRunId

Một order có thể cần xử lý lại. Hãy phân biệt **retry của cùng workflow** và **một workflow run mới có kết quả riêng**.

### 20.1. Retry cùng workflow

Nếu broker retry PaymentCaptured, vẫn giữ `BusinessKey(tenantId,orderId)`. Không thêm `retryCount` vào correlation key, vì mỗi attempt delivery sẽ trở thành một group khác.

### 20.2. Workflow run mới

Nếu nghiệp vụ quy định reprocessing phải tạo một kết quả mới độc lập, có thể dùng `RunKey(tenantId,orderId,workflowRunId)`. Nhưng ID run phải được **cấp một lần** và mọi producer của cùng run phải dùng đúng một giá trị đó. Nếu ba service tự tạo random run IDs, ba event không bao giờ hội tụ.

### 20.3. Payment attempt khác order

Nếu gom những event thuộc **một payment attempt**, `paymentAttemptId` có thể đúng hơn `orderId`. Còn nếu mục tiêu là OrderReady cho toàn đơn sau một payment thành công, business policy phải xác định attempt nào được chấp nhận rồi kết hợp nó với đơn. **Đơn vị cần gom quyết định key**, không phải chọn field có vẻ duy nhất ngẫu nhiên.

## 21. Khi ID thay đổi: alias, merge và migration

Không có hệ thống nào tránh hoàn toàn việc đổi chuẩn ID hoặc hợp nhất dữ liệu. Ví dụ:

~~~text
10:00 OrderRegistered: oldOrderId=ORD-OLD-101
10:05 Thay đổi chuẩn ID
10:06 PaymentCaptured: newOrderId=ORDER-101
~~~

Nếu hai sự kiện vào Aggregator với hai key khác nhau, chúng bị chia group. Hướng giải quyết:

1. Ưu tiên một **canonical internal ID không đổi**; external/display IDs có thể thay.
2. Duy trì bảng alias old→canonical với version, audit và quyền kiểm soát.
3. Chuyển đổi ở adapter trước khi tính correlation.
4. Nếu thật sự phải đổi key group, cần migration cả `MessageGroupStore`, lock keys và completed-group metadata.
5. Kiểm tra những event format cũ vẫn đang nằm trong broker.
6. Thiết kế reconciliation nếu mapping bị xung đột.

Không dựa vào email/amount để tự merge hai group vì chúng có thể là hai đơn khác nhau.

### 21.1. Mutable object làm map key

Một `HashMap` hoặc store dựa trên hash có thể lookup sai nếu key object thay đổi các field tham gia `equals/hashCode` **sau khi insert**. Dùng record/value object immutable như `BusinessKey` hoặc canonical string đã đóng băng.

## 22. Content-based correlation trong Resequencer

Resequencer cũng cần group identity để sắp các message liên quan theo `sequenceNumber`. Mọi batch đều có thể có part số 1, 2, 3, nên sequence number **không thể thay group key**.

~~~text
Batch A:
  key=A
  sequenceNumber=1,2,3

Batch B:
  key=B
  sequenceNumber=1,2,3
~~~

Nếu cùng khách chạy hai batch, không dùng email làm key. Dùng `batchId` hoặc `(tenantId,batchId)` có ID ổn định cho cả batch. Correlation đúng cũng không chữa được `sequenceSize` sai, duplicate sequence number hoặc part thiếu: cần validation/release/timeout riêng.

## 23. Content-based correlation trong Gateway

Gateway thực hiện request–reply và có thể mang `replyChannel`. Nhưng group từ Order, Payment, Inventory services có thể hoàn tất sau nhiều phút, khi Gateway/HTTP request ban đầu đã timeout.

Cần tách:

- `replyChannel`: nơi nhận reply của một request còn hoạt động.
- `traceId`: theo dõi đường xử lý trong distributed tracing.
- `BusinessKey`: định danh nghiệp vụ để các part hội tụ.
- `eventId`: nhận dạng từng event để dedup.
- `outputEventId`: nhận dạng kết quả để downstream idempotent.

Với workflow dài, có thể trả `202 Accepted` và tracking ID, rồi phát `OrderReady` async khi đủ event. Không đồng nhất tracking ID của HTTP với correlation key nếu hai ID có vòng đời khác nhau.

## 24. MessageGroupStore và timeout khi key bị drift

Giá trị dễ thay đổi có thể tạo nhiều group **gần đủ**:

~~~text
Group old-email:
  OrderRegistered
  -> thiếu Payment và Inventory

Group new-email:
  PaymentCaptured
  InventoryReserved
  -> thiếu OrderRegistered
~~~

Hậu quả:

- `open_groups` tăng.
- Tuổi nhóm và số group expired tăng.
- Store sử dụng thêm RAM/DB.
- Kết quả chậm hoặc không có.
- Người vận hành nghĩ event bị mất trong broker dù cả ba event đã đến.

Tăng timeout chưa chắc giúp, vì hai group vẫn có **hai key khác nhau**.

### 24.1. Persistence và concurrency

`SimpleMessageStore` in-memory phù hợp demo/test nhưng không bảo đảm survive restart. Khi nhiều JVM xử lý các part cùng group:

- Cần partition cùng stable key về một instance **hoặc** shared store/locking phù hợp.
- Key phải có encoding/serialization nhất quán.
- Phải tránh release trùng giữa các instances.
- Cần idempotency cho kết quả và side effect downstream.

### 24.2. Timeout và incomplete outcome

Nếu part không đến trước deadline:

1. Ghi nhận group key an toàn và loại part còn thiếu.
2. Phân biệt missing part thật với key drift/ID mapping fail.
3. Áp dụng expiry/cleanup và partial policy theo hợp đồng.
4. Không phát `OrderReady` nếu InventoryReserved còn thiếu.
5. Định nghĩa xử lý late arrival sau group expiry.

## 25. Observability cho chất lượng correlation key

| Metric/log field | Mục tiêu |
|---|---|
| `correlation_key_invalid_total` | Key trống/sai format |
| `identity_resolution_failed_total` | External ID không map được |
| `aggregation_open_groups` | Số group đang chờ |
| `aggregation_group_age_seconds` | Nhóm chờ quá lâu |
| `aggregation_completed_total` | Group đã release |
| `aggregation_expired_total` | Group không hoàn tất |
| `aggregation_duplicate_event_total` | Event trùng |
| `aggregation_late_arrival_total` | Event tới sau group đóng |
| `aggregation_output_key_mismatch_total` | Part không cùng business identity |
| `aggregation_idempotent_skip_total` | Output trùng bị chặn |

Log chẩn đoán có thể gồm:

~~~text
flow=order-ready
eventType=PaymentCaptured
eventId=evt-p-101
businessKeyHash=approved-hash
correlationSource=canonical-order-id
partsPresent=[OrderRegistered,PaymentCaptured]
missing=[InventoryReserved]
release=false
groupAgeMs=38000
~~~

Không dùng email, phone, `orderId`, `eventId` hoặc `traceId` làm **metric label cardinality cao**. Chúng có thể xuất hiện trong logs/traces theo chính sách bảo mật, hoặc được hash/redact thích hợp.

### 25.1. Những dấu hiệu key drift

- Cùng eventId sau retry lại mang business key khác.
- Group expiry tăng ngay sau khi thay logic normalize ID.
- Nhiều group chung customer/email nhưng các part bị phân tán.
- Producer ghi nhận đủ event nhưng Aggregator không release.
- Chỉ một tenant bị lỗi sau migration ID.
- Số group có một part tăng bất thường.

## 26. Sai lầm phổ biến

| Sai lầm | Hậu quả | Khắc phục |
|---|---|---|
| Group theo email | Một order bị tách; hai order cùng email bị merge | Canonical order ID |
| Group theo status | Mỗi trạng thái tạo group khác | Status dùng cho Router/Filter |
| Group theo amount | Sửa giá tạo key mới | Amount không phải identity |
| Group theo customerId | Nhiều order của khách bị trộn | Key theo đơn vị order |
| Group theo traceId | Service độc lập có traces khác nhau | Business correlation |
| Group theo eventId | Mỗi event thành group riêng | eventId cho dedup |
| Group theo Message ID | Retry/new message ID đổi | Stable business ID |
| Chỉ group theo orderId, thiếu tenant | Cross-tenant collision | Composite trusted key |
| Key có retry count | Replay mở nhóm khác | Tách retry khỏi run identity |
| Key random ở consumer | Các part không hội tụ | Cấp ID một lần ở coordinator |
| Lowercase mọi ID | Có thể trộn case-sensitive IDs | Theo ID authority |
| Chỉ đếm group.size() | Duplicate thay missing part | Release theo loại part, dedup |
| Không có expiry | Group mồ côi không được cleanup | Timeout, expiry, metrics |
| Đổi key format mà không migrate | Group cũ bị bỏ quên | Alias/migration/reconciliation |
| Coi Aggregator là exactly-once | Side effect trùng sau replay | Idempotent handler/outbox |

## 27. Bài tập thực hành

**Bài 1 — Chọn key:** với email, phone, updatedAt, status, amount, orderId, tenantId và eventId, chọn group key cho một OrderReady flow và giải thích.

**Bài 2 — Email đổi:** gửi OrderRegistered email cũ, PaymentCaptured và InventoryReserved email mới; assert một OrderReady.

**Bài 3 — Hai đơn chung email:** gửi event xen kẽ của ORDER-101/ORDER-102; assert hai kết quả riêng và không trộn payment/inventory.

**Bài 4 — Hai tenant trùng ID:** gửi tenant-a/ORDER-101 và tenant-b/ORDER-101; assert không cross-tenant merge.

**Bài 5 — Status đổi:** viết anti-pattern theo `orderId+status`; mô phỏng NEW→PAID để chứng minh group bị chia.

**Bài 6 — Replay:** gửi cùng eventId với MessageHeaders.ID khác; key phải không đổi, dedup phải xử lý bản sao.

**Bài 7 — Case sensitivity:** thử `order-101` và `ORDER-101`; xác định normalize hay reject dựa trên hợp đồng ID.

**Bài 8 — External reference:** map `EXT-5002` của Payment sang `ORDER-101`; mapping thiếu phải có error/reconciliation flow.

**Bài 9 — Duplicate:** cho group gồm Order, Payment, Payment; không phát OrderReady rồi xử lý duplicate trước khi nhóm kẹt.

**Bài 10 — Mutable map key:** dùng object có equals/hashCode phụ thuộc một field có setter; sửa field sau insert và giải thích lookup failure.

**Bài 11 — Workflow run:** chọn khi nào thêm workflowRunId và cách phân phối cùng ID cho tất cả producer.

**Bài 12 — ID migration:** đổi ORD-OLD-101 sang ORDER-101 khi group có hai part; thiết kế alias và state migration.

**Bài 13 — Timeout:** tạo missing part thật và key drift giả, dùng logs/metrics để phân biệt.

**Bài 14 — Security:** payload khai tenant-b nhưng principal là tenant-a; xác định nơi reject trước khi group.

**Bài 15 — End-to-end:** ghép canonicalization → Aggregator custom correlation → Router theo OrderReady; test key/release/output/idempotency.

### Câu hỏi tự kiểm tra

1. Content-based correlation khác routing dựa trên nội dung như thế nào?
2. Email có thể làm một order bị tách thành hai group ra sao?
3. CustomerId ổn định nhưng vì sao vẫn sai cho group order?
4. Hai group khác nhau có thể dùng cùng key không?
5. Correlation key, eventId, Message ID và traceId khác nhau thế nào?
6. Khi nào tenantId cần đi cùng orderId?
7. Khi nào thêm workflowRunId?
8. Vì sao không dùng mutable object làm group key?
9. Lowercase một ID có thể gây collision trong trường hợp nào?
10. Nếu Payment chỉ có externalOrderRef thì xử lý thế nào?
11. Retry sau email update có cần tạo group mới không?
12. Vì sao group.size()==3 có thể thiếu Inventory?
13. Key đúng có tự bảo đảm release đúng không?
14. Khi nào cần persistent MessageGroupStore?
15. Late arrival sau group release phải xử lý thế nào?
16. Đổi ID format ảnh hưởng những state nào?
17. Vì sao không dùng raw orderId làm metric label?
18. Test nào bắt được lỗi trộn group xuyên tenant?

## 28. Checklist thiết kế

- [ ] Xác định đúng đơn vị nghiệp vụ cần hội tụ trước khi chọn key.
- [ ] Key ổn định trong toàn bộ vòng đời group, kể cả replay.
- [ ] Key phân biệt giữa hai group, cả khi khác tenant.
- [ ] Mọi producer dùng canonical business identity thống nhất.
- [ ] Tenant và ownership được xác thực tại ingress.
- [ ] Không dùng email, phone, name, status, amount, updatedAt theo mặc định.
- [ ] Không dùng MessageHeaders.ID, traceId, eventId thay business group identity.
- [ ] Không tạo key mới từ clock/random khi consumer xử lý.
- [ ] Có validation cho key thiếu, sai kiểu hoặc sai format.
- [ ] Canonicalization được quyết định bởi ID authority.
- [ ] Composite key immutable, encoding không collision.
- [ ] Store/serializer/lock tương thích group key và version.
- [ ] External IDs được resolve trước Aggregator.
- [ ] Release policy kiểm tra đủ loại dữ liệu, không chỉ raw count.
- [ ] Có dedup theo eventId và conflict policy.
- [ ] Có timeout/expiry và incomplete group handling.
- [ ] Có late-arrival, correction và retention policy.
- [ ] Downstream handler có idempotency.
- [ ] Reprocessing/workflowRunId được thiết kế khi cần.
- [ ] Có migration/alias plan trước khi đổi chuẩn key.
- [ ] Test email đổi, hai đơn cùng email và hai tenant trùng ID.
- [ ] Test out-of-order, missing part, duplicate, replay và restart nếu cần.
- [ ] Có metric về key drift, open groups, expiry và output mismatch.
- [ ] Không lộ PII/identifiers trong metrics và logs không đủ quyền.

## 29. Tổng kết

**Không dùng giá trị dễ thay đổi làm correlation key** là nguyên tắc quan trọng của Content-based correlation. Một trường có thể phù hợp để Filter, Router hoặc tính toán nhưng không phù hợp để **định danh những message thuộc cùng một nghiệp vụ**. Email, số điện thoại, trạng thái, số tiền hoặc updatedAt có thể thay đổi; customerId tuy ổn định vẫn quá rộng nếu muốn gom theo **một đơn**.

Trong Spring Integration, hãy chọn **canonical business identity ổn định**, ví dụ `BusinessKey(tenantId,orderId)`, với IDs được kiểm chứng đúng namespace. Correlation strategy chọn group; release strategy quyết định nhóm đủ chưa; output processor xác minh invariant rồi tạo `OrderReady`. Không nhầm business key với eventId, traceId hay sequence headers; đồng thời dùng duplicate handling và idempotency cho retry/replay.

Để vận hành trong **SPRING_INTEGRATION_PATTERN**, cần thêm MessageGroupStore phù hợp, expiry, migration/alias, security, observability và kiểm thử các tình huống dữ liệu thay đổi. Khi key ổn định và đúng phạm vi, Router, Filter, Aggregator, Resequencer, Gateway và error/retry flows mới phối hợp chính xác trong những quy trình bất đồng bộ.

### Tài liệu tham khảo

- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Resequencer: https://docs.spring.io/spring-integration/reference/resequencer.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — CorrelationStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/CorrelationStrategy.html
- Spring Integration API — ReleaseStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/ReleaseStrategy.html
- Spring Integration API — MessageGroup: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroup.html
- Spring Integration API — SimpleMessageStore: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/SimpleMessageStore.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/





