# Trạng thái tùy chọn

## 1. Trạng thái tùy chọn là gì trong hợp đồng sự kiện?

Trong một ứng dụng **Spring Modulith**, các module giao tiếp qua application events để giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Một event mô tả sự thật đã xảy ra, chẳng hạn `OrderStatusChanged` (trạng thái đơn hàng đã thay đổi), `PaymentCaptured` (đã ghi nhận thanh toán) hoặc `ShipmentDispatched` (đã bàn giao hàng cho đơn vị vận chuyển). Module nhận event có thể xử lý sau khi transaction của module nguồn commit, thậm chí xử lý lại nếu lần trước thất bại.

**Trạng thái tùy chọn** trong hợp đồng sự kiện là một thông tin trạng thái **có thể chưa tồn tại, không áp dụng hoặc không được biết tại thời điểm phát event**, trong khi event vẫn có đủ thông tin bắt buộc để giữ nguyên ý nghĩa nghiệp vụ. Ví dụ, với `OrderStatusChanged`:

- `currentStatus` cho biết trạng thái **đã đạt tới** sau thay đổi. Đây là dữ liệu cốt lõi, không thể thiếu.
- `previousStatus` có thể không biết khi nhập lịch sử cũ. Trường này có thể được định nghĩa là **tùy chọn**.
- `reasonCode` có thể chỉ xuất hiện với một số loại chuyển trạng thái, ví dụ `CANCELLED_BY_CUSTOMER`.

Một hợp đồng rõ ràng phải trả lời được: **thiếu trường có nghĩa là gì, người nhận được phép làm gì khi thiếu, và phiên bản event cũ/mới có xử lý giống nhau hay không?**

Ví dụ hai event minh họa:

~~~json
{
  "eventId": "0f37ce10-0c31-4dce-8dcc-313fbde09911",
  "orderId": "dca52a1a-990a-4987-aed9-8243d6e99402",
  "currentStatus": "CONFIRMED",
  "previousStatus": "CREATED",
  "occurredAt": "2026-01-10T08:30:00Z"
}
~~~

~~~json
{
  "eventId": "d2466c59-cef2-486e-bf63-1ef15e369aa0",
  "orderId": "dca52a1a-990a-4987-aed9-8243d6e99402",
  "currentStatus": "CONFIRMED",
  "occurredAt": "2026-01-10T08:30:00Z"
}
~~~

Trong event thứ hai, `previousStatus` không xuất hiện. Nếu contract đã quy định **“thiếu previousStatus = không biết trạng thái trước”**, người nhận vẫn hiểu đơn đã chuyển sang `CONFIRMED`, nhưng không được tự suy diễn nó chắc chắn chuyển từ `CREATED`.

**Điểm cốt lõi:** sự kiện `OrderStatusChanged` phải chứa `currentStatus` hợp lệ. Nếu trạng thái mới còn chưa xác định, không nên phát một event “đã thay đổi trạng thái” với `currentStatus = null`; hãy chọn loại event khác thể hiện đúng sự thật, ví dụ `OrderSubmitted` hoặc `StatusDeterminationPending` nếu thực sự có trạng thái chờ xác định.

Sau bài này, bạn sẽ biết cách mô hình trường trạng thái tùy chọn, phân biệt thiếu dữ liệu với một giá trị trạng thái thực, xử lý tương thích phiên bản, thiết kế listener an toàn, và kiểm thử event được lưu bền hay phát lại trong Spring Modulith.

## 2. Phân biệt bốn trường hợp dễ bị nhầm

Một trường “không có giá trị” có thể mang nhiều ý nghĩa khác nhau. Cần thống nhất ý nghĩa **trước khi chọn kiểu Java hoặc định dạng JSON**.

| Trường hợp | Ý nghĩa nghiệp vụ | Cách mô hình thường phù hợp |
| --- | --- | --- |
| Có giá trị | Giá trị trạng thái đã được biết, ví dụ `CREATED` | Enum hoặc value object có kiểm tra |
| Chưa biết (*unknown*) | Sự kiện có thật nhưng không có thông tin trạng thái trước | Trường tùy chọn với quy ước “vắng mặt = unknown” |
| Không áp dụng (*not applicable*) | Thuộc tính này không có nghĩa ở trường hợp hiện tại | Trường tùy chọn được mô tả rõ, hoặc biến thể event |
| Đang chờ (*pending*) | Nghiệp vụ có một trạng thái cụ thể là đang chờ | Một enum/value object `PENDING` thực sự |

**`null` không tự động đồng nghĩa `PENDING`.** “Chưa biết trạng thái cũ” khác hoàn toàn “đơn đang chờ xác nhận”. Cũng không nên dùng `UNKNOWN`, `NONE`, `N_A` và `null` thay thế lẫn nhau nếu chúng biểu diễn các khái niệm khác nhau.

Ví dụ: đơn mới được tạo chưa có ngày giao dự kiến. Nếu ngày giao dự kiến chưa được quyết định, trường `estimatedDeliveryAt` có thể vắng mặt theo hợp đồng. Nhưng khi chuyển sang trạng thái `SHIPPED`, hệ thống phải biết trạng thái đó thực sự đã xảy ra; không thể coi `currentStatus` là tùy chọn để che việc thiếu dữ liệu nghiệp vụ bắt buộc.

Với trường **thực sự có ba trạng thái** như “chưa được đánh giá”, “được duyệt”, “bị từ chối”, nên biểu diễn tường minh bằng enum `NOT_REVIEWED` / `APPROVED` / `REJECTED` thay vì chỉ dựa vào boolean nullable. Khi có từ bốn khả năng nghiệp vụ trở lên hoặc cần metadata khác nhau, các biến thể event chuyên biệt thường dễ hiểu hơn.

## 3. Vắng mặt, `null` và chuỗi rỗng trong JSON

Xét ba payload:

~~~json
{"currentStatus":"CONFIRMED"}
~~~

~~~json
{"currentStatus":"CONFIRMED","previousStatus":null}
~~~

~~~json
{"currentStatus":"CONFIRMED","previousStatus":""}
~~~

Chúng không nhất thiết có cùng ngữ nghĩa:

- **Vắng mặt (absent):** key `previousStatus` không tồn tại. Đây có thể là cách biểu diễn chuẩn cho “không biết” hoặc cho event thuộc phiên bản cũ chưa có trường đó.
- **`null` tường minh:** key tồn tại nhưng mang JSON `null`. Có hệ thống xem tương đương “vắng mặt”, có hệ thống phân biệt “được chủ động xóa”; hợp đồng phải nói rõ.
- **Chuỗi rỗng:** key có kiểu chuỗi nhưng giá trị rỗng. Với enum trạng thái, đây thường là **dữ liệu sai hợp đồng**, không nên âm thầm coi là `null`.

Trong một domain event thông báo **sự thật đã xảy ra**, việc phân biệt “không gửi trường” và “yêu cầu xóa trường” thường không cần thiết. Đó là ngữ nghĩa hay gặp ở API *patch/update command*. Với `OrderStatusChanged`, cách đơn giản là định nghĩa **vắng mặt hoặc `null` của `previousStatus` cùng nghĩa “không biết”**, còn chuỗi rỗng và giá trị enum không hợp lệ bị từ chối.

Nếu hệ thống **thực sự cần phân biệt** ba trạng thái “không được cung cấp”, “được cung cấp để xóa”, “được cung cấp một giá trị”, một trường Java nullable đơn giản là chưa đủ. Khi đó cần kiểu biểu diễn tường minh, ví dụ biến thể có `kind` cùng giá trị, hoặc một cấu trúc *presence marker*. Cần đặc biệt cẩn trọng vì nhiều bộ deserialize mặc định ánh xạ cả JSON absent và JSON `null` thành Java `null`.

Không dùng giá trị mặc định tưởng như “an toàn” nhưng mang ý nghĩa sai:

~~~java
// Sai: tự suy diễn trạng thái trước mà event không hề khẳng định.
OrderStatus before = event.previousStatus() == null
        ? OrderStatus.CREATED
        : event.previousStatus();
~~~

Nếu listener chỉ cần biết trạng thái mới là `CONFIRMED`, nó có thể xử lý theo `currentStatus`. Nếu listener **cần biết chính xác chuyển từ đâu sang đâu**, thiếu `previousStatus` phải được xử lý thành một nhánh nghiệp vụ rõ ràng: bỏ qua có giám sát, gọi API đọc trạng thái thích hợp nếu hợp lệ về thời điểm, hoặc chuyển event vào luồng đối soát.

## 4. Thiết kế kiểu Java cho event có trường trạng thái tùy chọn

Trong Java, `Optional<T>` hữu ích để thể hiện kết quả có thể vắng mặt ở **API nội bộ**. Tuy nhiên, với DTO event có thể được serialize, lưu trong Event Publication Registry và đọc lại sau khi triển khai phiên bản mới, **trường record kiểu `Optional<OrderStatus>` không phải lựa chọn mặc định tốt nhất**: hỗ trợ serialize/deserialize tùy bộ thư viện và cấu hình, và `Optional` còn có thể bị truyền thành `null` do code bên ngoài.

Một giải pháp thực dụng là dùng trường Java nullable có tài liệu hợp đồng và xác minh bất biến ở constructor. Trong ví dụ này, mỗi khai báo `public` nằm trong **file Java riêng**:

~~~java
// com/example/shop/orders/OrderStatus.java
package com.example.shop.orders;

public enum OrderStatus {
    CREATED,
    CONFIRMED,
    CANCELLED
}
~~~

~~~java
// com/example/shop/orders/OrderStatusChanged.java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

/**
 * Sự kiện trạng thái đơn đã thay đổi.
 * previousStatus == null: trạng thái trước không được biết.
 * reasonCode == null: thay đổi này không cung cấp lý do bổ sung.
 */
public record OrderStatusChanged(
        UUID eventId,
        UUID correlationId,
        UUID orderId,
        OrderStatus currentStatus,
        OrderStatus previousStatus,
        String reasonCode,
        Instant occurredAt
) {
    public OrderStatusChanged {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(correlationId, "correlationId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(currentStatus, "currentStatus");
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (previousStatus == currentStatus) {
            throw new IllegalArgumentException(
                    "Previous and current status must differ");
        }
        if (reasonCode != null && reasonCode.isBlank()) {
            throw new IllegalArgumentException("Blank reasonCode");
        }
    }

    public boolean hasKnownPreviousStatus() {
        return previousStatus != null;
    }
}
~~~

Hợp đồng của record đặt **bất biến bắt buộc** lên `eventId`, `correlationId`, `orderId`, `currentStatus` và `occurredAt`. Trường `previousStatus` có thể là `null` do lịch sử không đủ thông tin; `reasonCode` có thể là `null` khi không có lý do bổ sung.

Các lựa chọn thiết kế cần được ghi nhận:

1. **Không yêu cầu consumer đoán giá trị.** Tên `hasKnownPreviousStatus()` làm rõ điều kiện có dữ liệu; không có `getPreviousStatusOrCreated()` vì việc tự chọn `CREATED` có thể sai.
2. **Không dùng giá trị mặc định cho trạng thái bắt buộc.** `currentStatus = null` bị chặn ngay lúc tạo.
3. **Giữ kiểu event ở API công khai của module `orders`.** Module khác chỉ import event, không dùng entity JPA hay repository nội bộ.
4. **Chọn chính sách serializer nhất quán.** Nếu contract JSON quy định bỏ field khi `null`, cấu hình bộ serialize tương ứng và kiểm thử round trip.
5. **Không coi event là lệnh cập nhật một phần.** Event khẳng định trạng thái mới; `previousStatus` là metadata bổ sung, không phải chỉ thị “nếu rỗng thì giữ nguyên trạng thái”.

Với Spring/Jackson, ví dụ cấu hình để bỏ những thuộc tính `null` khỏi JSON là `@JsonInclude(JsonInclude.Include.NON_NULL)` trên record hoặc cấu hình tương đương tại mapper được sử dụng. Annotation đó **chỉ có tác dụng khi đường serialize thực tế dùng Jackson và tôn trọng cấu hình ấy**; không giả định mọi backend lưu event của Spring Modulith đều có đúng hành vi này.

## 5. Khi nào nên tách loại event thay cho trạng thái tùy chọn?

Trường tùy chọn hợp lý khi thiếu nó **không làm đổi bản chất của event**. Nếu một trường quyết định event thuộc loại nghiệp vụ nào, một event riêng thường rõ nghĩa hơn.

Ví dụ thiết kế quá chung chung:

~~~java
public record OrderEvent(
        UUID orderId,
        OrderStatus status,     // Có thể null?
        String paymentResult,   // Có thể null?
        String cancellationReason // Có thể null?
) {}
~~~

Người nhận phải đoán ý nghĩa từ nhiều tổ hợp `null`. Có thể xuất hiện trạng thái mâu thuẫn như “đơn đã hủy” nhưng `paymentResult = SUCCESS` mà không rõ đây là kết quả trước hay sau hoàn tiền.

Một cách tách có chủ đích:

| Sự kiện | Sự thật bắt buộc | Thuộc tính có thể tùy chọn |
| --- | --- | --- |
| `OrderPlaced` | Đơn mới đã được đặt, có `orderId` | `promotionCode` nếu khách không áp mã |
| `OrderConfirmed` | Đơn được xác nhận, có `orderId` và thời điểm xác nhận | `confirmedByAgentId` nếu xác nhận tự động |
| `OrderCancelled` | Đơn đã hủy, có `orderId` | `reasonCode` nếu lịch sử không đủ dữ liệu |
| `PaymentCaptured` | Thanh toán đã được ghi nhận, có `paymentId` và số tiền | `externalReference` nếu không có mã đối tác |
| `OrderStatusChanged` | Trạng thái mới hợp lệ | `previousStatus` khi dữ liệu lịch sử chưa biết |

Không nhất thiết phải tách mọi trạng thái thành một loại event khác nhau. Nếu hệ thống có nhu cầu thực tế theo dõi mọi chuyển trạng thái qua một contract `OrderStatusChanged`, đây vẫn là lựa chọn hợp lệ. Tiêu chí quan trọng là **tên và các field bắt buộc phải khẳng định được một sự thật rõ ràng**.

## 6. Publisher chỉ đưa thông tin thực sự biết

Module sở hữu đơn hàng chịu trách nhiệm xác thực quy tắc chuyển trạng thái. Trong giao dịch thông thường, module này thường **biết** trạng thái trước và sau, vì vậy nên phát cả hai. Trường tùy chọn chủ yếu hỗ trợ các nguồn sự kiện hợp lệ mà dữ liệu lịch sử không đầy đủ hoặc không áp dụng.

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.OrderStatus;
import com.example.shop.orders.OrderStatusChanged;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderService(OrderRepository orders,
                        ApplicationEventPublisher events,
                        Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId, UUID correlationId) {
        OrderEntity order = orders.findById(orderId).orElseThrow();
        OrderStatus before = order.getStatus();
        if (before == OrderStatus.CONFIRMED) {
            return; // Không phát sự kiện đổi trạng thái khi không đổi.
        }

        order.confirm(); // Kiểm tra quy tắc và chuyển trạng thái.
        events.publishEvent(new OrderStatusChanged(
                UUID.randomUUID(),
                correlationId,
                orderId,
                OrderStatus.CONFIRMED,
                before,
                null,                  // Không có lý do bổ sung.
                Instant.now(clock)));
    }
}
~~~

`OrderRepository`, `OrderEntity` và `Clock` là những thành phần minh họa đã được cấu hình trong ứng dụng. Trong môi trường có cập nhật đồng thời, owner phải thực thi locking hoặc optimistic versioning thích hợp để tránh hai transaction cùng công bố các chuyển trạng thái mâu thuẫn.

Nếu nhập dữ liệu cũ và chỉ biết `currentStatus = CONFIRMED`, publisher nhập lịch sử **có thể** phát `OrderStatusChanged` với `previousStatus = null` theo contract đã thỏa thuận. Điều này khác với việc lấy dữ liệu hiện tại trong database rồi tùy tiện suy đoán trạng thái trước của một event xảy ra từ nhiều tháng trước.

**`ApplicationEventPublisher.publishEvent(...)` không khẳng định transaction đã commit.** Listener `@EventListener` thường chạy đồng bộ ngay; còn listener `@TransactionalEventListener` mặc định nhận sau commit thành công khi publisher chạy trong transaction. Quy tắc tùy chọn của payload không làm thay đổi ngữ nghĩa transaction ấy.

## 7. Consumer xử lý trạng thái tùy chọn mà không đoán

Module `notifications` có thể chỉ cần biết khi trạng thái **mới** là `CONFIRMED`. Lúc đó, `previousStatus` chỉ dùng để chẩn đoán và không nên trở thành điều kiện ngầm để gửi thông báo:

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.OrderStatus;
import com.example.shop.orders.OrderStatusChanged;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmationListener {
    private static final Logger log =
            LoggerFactory.getLogger(OrderConfirmationListener.class);

    private final NotificationService notifications;

    OrderConfirmationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderStatusChanged event) {
        if (event.currentStatus() != OrderStatus.CONFIRMED) {
            return;
        }

        if (event.hasKnownPreviousStatus()) {
            log.debug("Order {} transitioned {} -> {}, eventId={}",
                    event.orderId(), event.previousStatus(),
                    event.currentStatus(), event.eventId());
        } else {
            log.info("Previous status unknown for order {}, eventId={}",
                    event.orderId(), event.eventId());
        }

        notifications.sendConfirmationOnce(event.orderId());
    }
}
~~~

Ví dụ giả định `NotificationService.sendConfirmationOnce(...)` thực thi idempotency phù hợp với quy tắc “mỗi đơn được gửi một thông báo xác nhận”. Nếu nghiệp vụ cho phép xác nhận nhiều lần hợp lệ, khóa idempotency cần phản ánh mỗi lần xác nhận hoặc một định danh sự kiện, tùy đặc tả; không thể luôn dùng mỗi `orderId`.

`@ApplicationModuleListener` do Spring Modulith cung cấp và kết hợp cơ chế listener sau commit, thực thi bất đồng bộ cùng một transaction mới (`REQUIRES_NEW`) cho listener. Ứng dụng phải cấu hình hỗ trợ xử lý async/executor phù hợp. Một listener có thể nhận event khi transaction nguồn đã commit; lỗi gửi thông báo **không rollback được giao dịch nguồn**.

Đối với consumer **bắt buộc cần trạng thái trước**, như tính thời lượng ở trạng thái `CREATED`, cần chọn một chính sách minh bạch:

- Với `previousStatus` hiện diện và hợp lệ, tính toán bình thường.
- Với `previousStatus` không có, ghi nhận dữ liệu không đủ và chuyển sang đối soát hoặc bỏ qua phép đo nếu phép đo chỉ là bổ trợ.
- Nếu nghiệp vụ cho phép truy vấn module nguồn, dùng **API công khai** để lấy thông tin; tuy nhiên trạng thái **hiện tại** của đơn chưa chắc bằng trạng thái **trước tại thời điểm event**. Không coi truy vấn hiện tại là cách tự động khôi phục lịch sử.
- Nếu không thể thực hiện an toàn, chủ động báo lỗi theo chính sách xử lý và để publication được quan sát/khôi phục. Không retry vô hạn một lỗi dữ liệu vĩnh viễn.

Mỗi consumer phải xác định **những trường nào nó cần bắt buộc** cho hành vi của mình; “tùy chọn trong contract” không đồng nghĩa “mọi consumer phải xử lý thành công trong mọi trạng thái thiếu”.

## 8. Tương thích khi bổ sung trường tùy chọn vào event

Tình huống thường gặp: phiên bản đầu tiên của `OrderStatusChanged` chỉ có `eventId`, `orderId`, `currentStatus`, `occurredAt`. Sau này nhóm phát triển muốn thêm `previousStatus` để quan sát, nhưng event cũ vẫn tồn tại trong database/registry hoặc payload từ hệ thống khác.

~~~mermaid
flowchart LR
    V1["Event v1<br/>currentStatus"] --> D["Consumer đọc sự kiện"]
    V2["Event v2<br/>currentStatus + previousStatus?"] --> D
    D --> C{"Có previousStatus?"}
    C -->|Có| K["Sử dụng chuyển trạng thái đầy đủ"]
    C -->|Không| U["Đánh dấu unknown<br/>không đoán"]
~~~

Quy trình thay đổi contract an toàn gồm:

1. **Xác nhận ý nghĩa trường mới.** `previousStatus` có nghĩa “trạng thái trước khi chuyển”, chứ không phải “trạng thái gần nhất khi listener chạy”.
2. **Định nghĩa giá trị khi dữ liệu v1 không có.** Consumer v2 hiểu vắng mặt hoặc `null` là **unknown**. Không tạo dữ liệu lịch sử giả.
3. **Đánh giá constructor/binary compatibility.** Thêm thành phần vào Java `record` thay đổi canonical constructor, nên code producer/consumer gọi constructor cũ có thể phải sửa hoặc cần overload/phương án tương thích.
4. **Đánh giá wire/storage compatibility.** Nếu event lưu trong Event Publication Registry hoặc externalize, phải kiểm thử việc deserialize bản ghi cũ bằng phiên bản mới; việc thêm nullable field **không bảo đảm** serializer của mọi backend tự tương thích.
5. **Triển khai consumer chấp nhận cả dạng cũ và mới trước khi bắt buộc producer phát field mới** nếu có nhiều phiên bản hệ thống cùng chạy hoặc có event lưu bền.
6. **Kiểm thử event round trip qua chính serializer đang dùng**, bằng payload v1, payload v2, null tường minh, giá trị enum sai và dữ liệu bắt buộc bị thiếu.

| Thay đổi contract | Rủi ro | Hướng xử lý thường phù hợp |
| --- | --- | --- |
| Thêm field bổ trợ nullable | Constructor thay đổi; event cũ thiếu field | Consumer có fallback rõ; kiểm thử serializer và mã gọi |
| Đổi field tùy chọn thành bắt buộc | Event cũ có thể thiếu | Version event, migration/upcaster hoặc duy trì hỗ trợ v1 |
| Đổi ý nghĩa `null` | Consumer có thể diễn giải sai | Tránh đổi âm thầm; công bố phiên bản/loại event mới |
| Đổi tên field | Bản ghi cũ không còn khớp | Giữ alias tương thích nếu thư viện hỗ trợ, hoặc migration |
| Đổi tên/loại bỏ enum constant | Deserialization event cũ có thể thất bại | Chiến lược version/mapping; không xóa giá trị đang lưu |
| Thêm trạng thái enum mới | Consumer cũ không biết trạng thái | Fallback chính sách, nâng cấp consumer hoặc event version |

Với event thuộc **API công khai của module**, cả hợp đồng Java và dữ liệu bền vững đều phải được xem xét. Dù Spring Modulith chạy trong một JVM, sự kiện còn chưa xử lý có thể sống qua một lần triển khai ứng dụng và được phục hồi bằng phiên bản code mới.

## 9. Optional state không phải optional event delivery

Hai khái niệm này độc lập:

- **Trường trạng thái tùy chọn:** một thuộc tính event hợp lệ có thể vắng mặt theo quy ước (ví dụ `previousStatus`).
- **Giao sự kiện đáng tin cậy:** một event đã phát cần đến được transactional listener hoặc có dấu vết để xử lý lại khi thất bại.

Event Publication Registry của Spring Modulith có thể ghi bản ghi publication tương ứng với từng transactional listener, theo dõi hoàn tất và giúp xác định publication chưa được xử lý. Để có tính bền vững, phải cấu hình implementation lưu trữ phù hợp (chẳng hạn JDBC/JPA) cùng transaction và schema/database cần thiết. Chỉ dùng `@ApplicationModuleListener` **không tự làm mọi event được ghi bền vững**.

Giả sử `OrderStatusChanged` có `previousStatus = null` và listener đã xử lý gửi email nhưng gặp sự cố trước khi registry ghi completion. Khi publication được phát lại:

- Payload logic vẫn phải diễn tả cùng event: `eventId`, `orderId`, `currentStatus`, `previousStatus` và `correlationId` không được thay tùy tiện.
- `previousStatus` vẫn là **unknown**; retry không có nghĩa hệ thống bỗng biết dữ liệu đã thiếu.
- Listener phải idempotent với tác động của mình, ví dụ ràng buộc duy nhất khi ghi trạng thái gửi email, hoặc idempotency key tại dịch vụ bên ngoài.
- Correlation ID giúp nối log lần phát đầu với lần retry; nó **không phải** khóa deduplicate cho mọi event thuộc cùng workflow.
- Lỗi dữ liệu thiếu không thể bổ sung được không nên được retry vô hạn như lỗi mạng tạm thời. Cần chính sách phân loại, cảnh báo và đối soát.

Registry giảm nguy cơ thất lạc publication, nhưng **không bảo đảm exactly-once cho side effect bên ngoài**. Khi một email đã gửi thành công nhưng trạng thái hoàn tất chưa được lưu, listener có thể bị gọi lại. Quy tắc chống trùng nằm ở module tiêu thụ.

## 10. Kiểm thử contract và giá trị tùy chọn

Kiểm thử chỉ tình huống “đủ mọi field” là chưa đủ. Với một field có thể vắng mặt, cần xác minh cả **điều gì được cho phép**, **điều gì bị từ chối** và **consumer được làm gì khi dữ liệu thiếu**.

| Kịch bản | Kết quả mong muốn |
| --- | --- |
| Event có `currentStatus = CONFIRMED` và `previousStatus = CREATED` | Consumer hiểu đầy đủ chuyển trạng thái |
| Event có `currentStatus = CONFIRMED` và `previousStatus = null` | Event hợp lệ; consumer không đoán trạng thái cũ |
| Event có `currentStatus = null` | Constructor/validation từ chối |
| Event có `previousStatus = currentStatus` | Từ chối event “đã thay đổi” nhưng không có chuyển trạng thái |
| `reasonCode` là chuỗi rỗng | Từ chối theo hợp đồng |
| JSON v1 không chứa `previousStatus` | Consumer v2 nhận đúng semantics `unknown` nếu serializer hỗ trợ |
| JSON có trạng thái enum không tồn tại | Báo lỗi tương thích; không tự ánh xạ sang một trạng thái hợp lệ |
| Transaction nguồn rollback | Listener sau commit không được chạy như thể event đã hoàn tất |
| Retry cùng event sau khi listener lỗi | Giữ semantics của `null` và không gây tác động trùng |

### 10.1. Unit test kiểm tra bất biến của event

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.shop.orders.OrderStatus;
import com.example.shop.orders.OrderStatusChanged;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderStatusChangedTest {

    @Test
    void allowsUnknownPreviousStatus() {
        OrderStatusChanged event = new OrderStatusChanged(
                UUID.randomUUID(),
                UUID.randomUUID(),
                UUID.randomUUID(),
                OrderStatus.CONFIRMED,
                null,
                null,
                Instant.parse("2026-01-10T08:30:00Z"));

        assertThat(event.currentStatus())
                .isEqualTo(OrderStatus.CONFIRMED);
        assertThat(event.hasKnownPreviousStatus()).isFalse();
    }

    @Test
    void rejectsMissingMandatoryCurrentStatus() {
        assertThatThrownBy(() -> new OrderStatusChanged(
                UUID.randomUUID(),
                UUID.randomUUID(),
                UUID.randomUUID(),
                null,
                null,
                null,
                Instant.now()))
                .isInstanceOf(NullPointerException.class)
                .hasMessageContaining("currentStatus");
    }
}
~~~

Đây là unit test hợp đồng trong bộ nhớ, không phải kiểm thử serializer hay transaction. Nếu dùng Jackson lưu JSON, cần test riêng với `ObjectMapper` và các module/cấu hình của ứng dụng (đặc biệt là xử lý `Instant`, enum, Java record, null/absent). Nếu dùng implementation registry khác, phải kiểm tra bằng đúng cách lưu/khôi phục mà nó dùng.

### 10.2. Kiểm thử Spring Modulith và xử lý sau commit

Các phép kiểm thử tích hợp nên bao gồm:

1. Gọi publisher trong transaction rồi commit; chờ listener bất đồng bộ với timeout, kiểm tra side effect.
2. Cho publisher rollback; kiểm tra listener `AFTER_COMMIT` không chạy.
3. Publish event có `previousStatus = null` nhưng `currentStatus` hợp lệ; xác minh consumer theo chính sách fallback.
4. Gây lỗi listener, kiểm tra publication chưa hoàn tất và cơ chế phục hồi đã cấu hình; xử lý lại cùng event không gây gửi thông báo trùng.
5. Dùng payload phiên bản cũ đã lưu, chạy lại đường deserialize và listener của phiên bản mới.
6. Chạy `ApplicationModules.of(ShopApplication.class).verify()` để kiểm tra ranh giới phụ thuộc; `notifications` chỉ import API event công khai của `orders`.

Test sau commit phải **thực sự commit transaction nguồn**. Một test được bao bởi transaction tự rollback có thể không kích hoạt listener mặc định của `@TransactionalEventListener`. Khi dùng `@ApplicationModuleListener`, không assert ngay sau `publishEvent(...)` vì listener chạy bất đồng bộ.

## 11. Những lỗi thường gặp

**Đưa trạng thái mới thành tùy chọn trong event “đã thay đổi trạng thái”.** Nếu không biết trạng thái mới, event không khẳng định được điều nó đặt tên. Cần sửa mô hình event hoặc luồng nghiệp vụ.

**Coi `null` luôn là một trạng thái nghiệp vụ.** Nếu `null` có nghĩa “không biết” còn `PENDING` là trạng thái thật, phải tách bạch.

**Dùng `Optional<T>` làm field payload mà không kiểm tra serializer.** `Optional` thích hợp cho API truy vấn nội bộ, nhưng việc lưu và deserialize record chứa `Optional` phụ thuộc hạ tầng và module serializer thực tế.

**Áp giá trị mặc định tùy tiện khi event cũ thiếu trường.** `previousStatus = CREATED` có thể tạo dữ liệu lịch sử sai. Cần fallback được mô tả trong contract.

**Đổi enum hoặc đổi ý nghĩa trường mà không xét publication cũ.** Event chưa xử lý trong registry có thể bị lỗi deserialize sau khi triển khai phiên bản mới.

**Tự cho rằng event có `null` cần retry.** Trường tùy chọn được contract cho phép là dữ liệu **hợp lệ**; còn lỗi dữ liệu bắt buộc thiếu có thể là lỗi vĩnh viễn, cần cảnh báo/đối soát hơn là retry liên tục.

**Dùng một event với hàng chục trường tùy chọn và tên quá chung.** Khi các tổ hợp giá trị thể hiện các sự thật nghiệp vụ khác nhau, tách thành event chuyên biệt sẽ dễ hiểu và an toàn hơn.

**Dùng dữ liệu hiện tại để suy diễn trạng thái quá khứ.** Sau khi listener chạy trễ hoặc retry, đơn hàng có thể đã chuyển tiếp sang trạng thái khác. Chỉ tra cứu hiện tại nếu logic nghiệp vụ chấp nhận sự khác biệt thời điểm.

## 12. Bài thực hành: hợp đồng trạng thái đơn hàng có trường tùy chọn

Thiết kế module `orders` phát `OrderStatusChanged`; module `notifications` gửi xác nhận khi đơn chuyển sang `CONFIRMED`; module `analytics` dùng trạng thái trước để đo tỉ lệ chuyển đổi.

Yêu cầu thực hiện:

1. Công bố `OrderStatus` cùng `OrderStatusChanged` trong API của `orders`. Bắt buộc `currentStatus`, `orderId`, `eventId`, `correlationId` và `occurredAt`; cho phép `previousStatus` và `reasonCode` vắng mặt theo quy ước rõ ràng.
2. Trong publisher, phát event sau khi áp dụng chuyển trạng thái hợp lệ trong transaction; không phát event khi đơn vốn đã ở trạng thái mục tiêu.
3. Viết listener `notifications` dùng `@ApplicationModuleListener`. Nếu `currentStatus = CONFIRMED` thì gửi xác nhận, bất kể `previousStatus` biết hay không; triển khai idempotency.
4. Viết consumer `analytics` có nhánh xử lý “previous status unknown”: ghi số lượng event không đủ dữ liệu hoặc chuyển đối soát, tránh mặc định `CREATED`.
5. Tạo hai payload JSON đại diện cho v1 (chỉ có trạng thái mới) và v2 (thêm trạng thái cũ); kiểm thử deserialize vào consumer v2 bằng serializer được cấu hình thực tế.
6. Thử rollback, gửi lại event và mô phỏng listener thất bại. Xác minh kết quả đã commit, publication, log và dữ liệu cuối cùng.

**Câu hỏi tự kiểm tra:**

- Vì sao `previousStatus` có thể tùy chọn trong `OrderStatusChanged` nhưng `currentStatus` không thể?
- Trường `null` có giống với enum `PENDING` không? Khi nào nên dùng một enum mới?
- Khi event cũ bị retry sau khi thay phiên bản, có thể “điền bừa” trạng thái trước từ bản ghi đơn hàng hiện tại không?
- Vì sao Event Publication Registry và idempotency của listener là hai cơ chế bổ sung cho nhau?

## 13. Kết luận

**Trạng thái tùy chọn là một quyết định về ngữ nghĩa hợp đồng**, không đơn thuần là chọn `Optional` hay cho phép Java `null`. Một event phải vẫn mô tả chính xác sự thật nghiệp vụ khi field tùy chọn vắng mặt. Với `OrderStatusChanged`, trạng thái mới là bắt buộc; trạng thái trước có thể không biết và consumer phải xử lý theo quy tắc đã thống nhất.

Trong Spring Modulith, hợp đồng này còn phải hoạt động đúng khi listener chạy sau commit, khi publication được lưu bền, khi retry, và khi ứng dụng nâng cấp phiên bản. Hãy kiểm tra chặt field bắt buộc, mô tả rõ nghĩa của absent/null, giữ event bất biến, xử lý idempotent và kiểm thử với dữ liệu đã lưu. Những lựa chọn ấy giúp các module phát triển độc lập mà không làm sai ý nghĩa dữ liệu khi sự kiện đi qua nhiều ranh giới nghiệp vụ.

**Tài liệu chính thức để đọc thêm:**

- [Spring Modulith — Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Jackson Annotations — JsonInclude](https://github.com/FasterXML/jackson-annotations/wiki/Jackson-Annotations)
