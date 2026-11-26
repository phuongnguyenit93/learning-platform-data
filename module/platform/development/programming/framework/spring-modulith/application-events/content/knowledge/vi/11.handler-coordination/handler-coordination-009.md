# Tránh điều phối ẩn

## 1. Điều phối ẩn xuất hiện như thế nào?

Trong **Spring Modulith**, application events giúp các module giao tiếp mà không cần gọi trực tiếp implementation của nhau. Module `orders` có thể phát `OrderPlaced`; module `notifications`, `inventory` và `reporting` đăng ký listener để phản ứng. Cách này đặc biệt hữu ích với các **tác vụ phụ độc lập** như gửi email hoặc cập nhật báo cáo sau commit.

Tuy nhiên, việc chuyển mọi bước nghiệp vụ thành listener **không tự động làm kiến trúc tốt hơn**. Khi một quy trình chỉ hoàn tất nếu các handler thực thi **theo một thứ tự nhất định**, phụ thuộc vào **trạng thái do handler khác tạo** hoặc cần **quyết định bước kế tiếp sau thất bại**, nhưng những quy tắc đó nằm rải rác trong các listener, hệ thống đang có **điều phối ẩn (hidden orchestration)**.

Ví dụ một quy trình checkout được viết theo chuỗi sau:

~~~mermaid
flowchart LR
    O["orders<br/>OrderPlaced"] --> I["inventory listener<br/>Giữ hàng"]
    I --> IR(["StockReserved"])
    IR --> P["payments listener<br/>Thu tiền"]
    P --> PC(["PaymentCaptured"])
    PC --> S["shipping listener<br/>Tạo vận đơn"]
~~~

Sơ đồ có vẻ đơn giản, nhưng người đọc phải lần theo nhiều module mới biết **“đơn được giao khi nào?”** và **“nếu đã giữ hàng nhưng thu tiền thất bại thì ai giải phóng tồn kho?”**. Không có nơi nào mô tả toàn bộ quy tắc điều phối và trạng thái của quy trình.

**Tránh điều phối ẩn** không có nghĩa là cấm chuỗi event. Ý nghĩa là: khi các bước có **điều kiện tiên quyết, trạng thái chờ, rẽ nhánh, retry, timeout hoặc bù trừ**, phải làm rõ **module nào sở hữu quy trình**, **trạng thái nào đang tồn tại**, và **ai quyết định bước tiếp theo**.

Trong học phần `SPRING_MODULITH_APPLICATION_EVENTS`, vấn đề này gắn trực tiếp với publisher/listener, ranh giới nghiệp vụ, xử lý sau commit, Event Publication Registry và khả năng quan sát giao sự kiện. Bài học sẽ giúp bạn thiết kế các handler dễ kiểm tra mà không biến application events thành một “workflow engine vô hình”.

## 2. Nhận diện điều phối ẩn từ mã nguồn

Điều phối ẩn thường xuất hiện khi **mối quan hệ về thời gian và thứ tự** không được thể hiện trong một hợp đồng hoặc mô hình trạng thái rõ ràng.

Những dấu hiệu điển hình:

1. **Một listener ngầm chờ kết quả của listener khác.** Ví dụ handler gửi email đọc bảng điểm và mặc định listener cộng điểm đã chạy trước.
2. **Thêm `@Order` để “bảo đảm” chuỗi nghiệp vụ.** Thứ tự callback không thể thay cho trạng thái đã commit, đặc biệt với listener async.
3. **Event mang tên command** như `ChargePaymentNow` nhưng được phát như một sự thật nghiệp vụ, khiến không rõ ai chịu trách nhiệm quyết định và phản hồi kết quả.
4. **Không biết toàn bộ trạng thái quy trình ở đâu.** Handler nào cũng có một cờ riêng nhưng không có bản ghi cho biết checkout đang đợi giữ hàng, đợi thanh toán hay đang cần xử lý lỗi.
5. **Retry một listener có thể kích hoạt lại cả chuỗi**, gây gửi email/cộng điểm/trừ tồn kho nhiều lần.
6. **Không ai xử lý khi một bước thất bại vĩnh viễn.** Publication được phát lại vô hạn mà không có quy tắc bù trừ hoặc chuyển sang xử lý thủ công.
7. **Khó viết test end-to-end.** Test chỉ thành công nếu các listener tình cờ thực thi theo một thứ tự cụ thể hoặc được ép bằng sleep.
8. **Module sửa dữ liệu của module khác** để “báo hiệu đã xong”, làm mất quyền sở hữu dữ liệu.

Một anti-pattern thường thấy:

~~~java
// Minh họa cách KHÔNG nên phụ thuộc vào kết quả của handler khác.
@ApplicationModuleListener
void on(OrderPlaced event) {
    // Giả định: listener giữ hàng đã chạy và commit trước.
    if (inventoryRepository.existsByOrderId(event.orderId())) {
        paymentGateway.capture(event.orderId());
    }
}
~~~

Đoạn mã sai về **mô hình điều phối** chứ không nhất thiết sai cú pháp: listener không có hợp đồng nào đảm bảo listener giữ hàng đã hoàn tất trước, và `inventoryRepository` còn là chi tiết lưu trữ của module khác. Khi listener xử lý sau commit và bất đồng bộ, thứ tự hoàn tất có thể khác giữa các lần chạy.

Giải pháp không phải là thêm một khoảng chờ tùy ý. Cần phát biểu rõ **“chỉ khi có `StockReserved` hợp lệ của checkout này, mới được chuyển sang bước yêu cầu thanh toán”** và xác định nơi lưu quyết định chuyển bước.

## 3. Phân biệt choreography và orchestration

Hai cách phối hợp thường gặp có mục tiêu khác nhau:

| Thuộc tính | Choreography bằng events | Orchestration tường minh |
| --- | --- | --- |
| Ai quyết định bước tiếp theo? | Mỗi module tự phản ứng với sự thật đã xảy ra | Một thành phần sở hữu quy trình quyết định chuyển trạng thái và gửi yêu cầu |
| Phù hợp với | Các tác động phụ tương đối độc lập | Quy trình nhiều bước có thứ tự, rẽ nhánh, deadline, bù trừ |
| Nguồn trạng thái tiến độ | Phân tán ở consumer | Có bản ghi tiến độ do process manager/coordinator sở hữu |
| Mức phụ thuộc trực tiếp | Producer ít biết consumer | Coordinator phụ thuộc các API công khai cần điều phối |
| Rủi ro chính | Luồng nghiệp vụ bị ẩn trong mạng lưới handler | Coordinator có thể phình to nếu nhận quá nhiều trách nhiệm |
| Khả năng quan sát | Ghép log, event, registry, projection | Có thêm trạng thái quy trình làm đầu mối tra cứu |

Ví dụ **choreography phù hợp**:

~~~mermaid
flowchart LR
    C["OrderConfirmed"] --> N["notifications"]
    C --> A["analytics"]
    C --> R["reporting"]
~~~

Ba consumer thực hiện công việc sau xác nhận đơn; thành công của reporting không phải điều kiện để gửi email. Chúng có thể hoàn thành theo thứ tự bất kỳ, retry riêng và sở hữu dữ liệu riêng.

Ví dụ **cần điều phối tường minh**:

~~~mermaid
flowchart TB
    W["CheckoutProcessCoordinator<br/>Sở hữu trạng thái quy trình"]
    W -->|"reserve stock"| I["inventory API"]
    I -->|"StockReserved / StockRejected"| W
    W -->|"capture payment khi đã giữ hàng"| P["payments API"]
    P -->|"PaymentCaptured / PaymentFailed"| W
    W -->|"CheckoutCompleted"| N["notifications / shipping"]
~~~

**Orchestration không bắt buộc đồng bộ.** Coordinator có thể nhận event sau commit, cập nhật trạng thái và phát ra *ý định thực hiện command* bền vững để một dispatcher gửi lệnh. Điểm khác biệt là **quy tắc chuyển bước được mô hình hóa rõ**, không bị phân tán trong các handler tự động gọi nhau.

Không nên áp orchestration cho mọi hành vi nhỏ. Nếu một event chỉ kích hoạt việc cập nhật read model và gửi thông báo độc lập, fan-out bằng listener là đơn giản và phù hợp hơn.

## 4. Vì sao Spring events không bảo đảm thứ tự quy trình?

Cần hiểu đúng các loại listener:

| Cơ chế | Thời điểm thông thường | Có tự đảm bảo thứ tự hoàn tất giữa các consumer? |
| --- | --- | --- |
| `@EventListener` | Đồng bộ lúc `publishEvent(...)` với cấu hình mặc định | `@Order` có thể ảnh hưởng thứ tự gọi listener đồng bộ, không phải quy tắc workflow |
| `@TransactionalEventListener` | Mặc định `AFTER_COMMIT` | Không tự bật async; callback sau commit không phải cam kết trạng thái consumer đã ghi bền |
| `@ApplicationModuleListener` | Sau commit, async, transaction riêng (`REQUIRES_NEW`) | **Không**; các consumer có thể hoàn tất khác thứ tự |

Những hệ quả quan trọng:

- Khi `orders` publish trong transaction chưa commit, `@EventListener` đồng bộ có thể chạy **trước commit** và ném lỗi làm rollback nguồn.
- `@TransactionalEventListener(AFTER_COMMIT)` chỉ được thực thi theo pha sau commit khi có transaction phù hợp; publish ngoài transaction thì listener mặc định bị bỏ qua, trừ cấu hình `fallbackExecution`.
- `@ApplicationModuleListener` của Spring Modulith phù hợp với tác vụ phản ứng sau commit; cần cấu hình async/executor phù hợp trong ứng dụng. Việc xử lý ở transaction riêng giúp consumer độc lập hơn nhưng làm thứ tự hoàn tất khó dự đoán.
- Một consumer hoàn tất không có nghĩa những consumer khác đã hoàn tất. Một lần gọi `publishEvent(...)` không phải “barrier” chờ toàn bộ listener.

Ví dụ không nên làm:

~~~java
@Order(1)
@ApplicationModuleListener
void reserveStock(OrderPlaced event) {
    // ...
}

@Order(2)
@ApplicationModuleListener
void chargePayment(OrderPlaced event) {
    // KHÔNG được mặc định reserveStock đã commit.
}
~~~

Với xử lý async, dù listener được chọn theo một thứ tự đăng ký nào đó, executor và các transaction độc lập có thể khiến `chargePayment` bắt đầu hoặc hoàn tất trước `reserveStock`. Và `@Order` cũng không biến sự kiện `OrderPlaced` thành xác nhận giữ hàng.

Nếu cần điều kiện “đã giữ hàng”, hãy chờ **sự thật `StockReserved`**, hoặc cho một coordinator chủ động gọi API đồng bộ và kiểm tra kết quả nếu yêu cầu tính nhất quán tức thời.

## 5. Xác định owner của quy trình trước khi viết handler

Một quy trình đi qua nhiều module thường có hai nhóm trách nhiệm:

- **Domain owner:** mỗi module quản lý dữ liệu và bất biến của chính nó. `inventory` quản lý reservation; `payments` quản lý giao dịch thu tiền; `orders` quản lý đơn.
- **Process owner:** một module, ví dụ `checkout`, quản lý tiến độ toàn bộ checkout, điều kiện chuyển bước, timeout và chính sách xử lý thất bại.

Hai trách nhiệm này **không nhất thiết nằm chung module**. `checkout` không cần đọc/ghi bảng `payments.transactions` và không có quyền tự “đánh dấu thanh toán thành công”. Nó chỉ ghi nhận rằng **đã nhận một `PaymentCaptured` hợp lệ**, rồi chuyển trạng thái workflow của mình.

Ví dụ trạng thái quy trình:

| Trạng thái checkout | Ý nghĩa | Tín hiệu/hành động kế tiếp |
| --- | --- | --- |
| `WAITING_FOR_STOCK` | Đã yêu cầu giữ hàng, chưa có kết quả | Đợi `StockReserved` hoặc `StockReservationRejected` |
| `WAITING_FOR_PAYMENT` | Hàng đã giữ, yêu cầu thanh toán đã được lên lịch/gửi | Đợi `PaymentCaptured` hoặc `PaymentFailed` |
| `COMPLETED` | Điều kiện checkout thành công đã đủ | Phát `CheckoutCompleted` |
| `COMPENSATION_REQUIRED` | Bước sau thất bại, có tài nguyên cần trả lại | Lên lịch release inventory/hoàn tiền nếu nghiệp vụ yêu cầu |
| `FAILED` | Quy trình kết thúc thất bại | Phát `CheckoutFailed` và thông báo phù hợp |

Đây là mô hình minh họa: ứng dụng thật có thể thêm `TIMED_OUT`, `CANCELLING`, `MANUAL_REVIEW` hoặc các trạng thái kiểm soát giao lệnh. Quan trọng là **có nguồn sự thật của tiến độ**, không suy đoán từ việc handler nào vừa log thành công.

~~~mermaid
stateDiagram-v2
    [*] --> WAITING_FOR_STOCK
    WAITING_FOR_STOCK --> WAITING_FOR_PAYMENT: StockReserved
    WAITING_FOR_STOCK --> FAILED: StockReservationRejected
    WAITING_FOR_PAYMENT --> COMPLETED: PaymentCaptured
    WAITING_FOR_PAYMENT --> COMPENSATION_REQUIRED: PaymentFailed
    COMPENSATION_REQUIRED --> FAILED: StockReleased
    COMPLETED --> [*]
    FAILED --> [*]
~~~

Với sơ đồ này, người vận hành có thể tra một `checkoutId` và biết bước nào chưa hoàn tất. Listener chỉ chuyển tiếp tín hiệu vào coordinator; **coordinator** quyết định chuyển trạng thái và phát hành command ý định bước tiếp theo.

## 6. Command, event và kết quả không được trộn lẫn

Với quy trình có điều phối, phân biệt rõ:

| Loại thông điệp | Ví dụ | Ý nghĩa | Ai sở hữu |
| --- | --- | --- | --- |
| Command | `ReserveStock(checkoutId, items)` | Yêu cầu inventory thực hiện giữ hàng | Coordinator gửi qua API công khai của inventory |
| Result event | `StockReserved(checkoutId, reservationId)` | Hàng **đã được giữ** | Inventory phát sau thay đổi trạng thái |
| Failure event | `StockReservationRejected(checkoutId, reason)` | Yêu cầu giữ hàng bị từ chối | Inventory phát theo hợp đồng |
| Command | `CapturePayment(checkoutId, paymentKey)` | Yêu cầu payments thu tiền idempotent | Coordinator gửi qua API công khai của payments |
| Result event | `PaymentCaptured(checkoutId, paymentId)` | Thu tiền đã thành công | Payments phát sau cập nhật hợp lệ |
| Workflow result event | `CheckoutCompleted(checkoutId, orderId)` | Quy trình checkout hoàn tất | Checkout phát |

Đặt tên một event `PaymentCaptureRequested` rồi để listener tự thực thi có thể chấp nhận trong hệ thống dùng **internal command message bus** được thiết kế tường minh. Nhưng nếu tất cả thông điệp đều được gọi chung là domain event, rất dễ nhầm **một lời yêu cầu** với **một sự thật đã hoàn tất**.

Trong bài này, các **command** được biểu diễn bằng API công khai hoặc command outbox nội bộ do coordinator quản lý; còn các **event** mang kết quả đã được module sở hữu xác nhận.

## 7. Ví dụ cấu trúc Spring Modulith với coordinator tường minh

Các package module sau nằm trực tiếp dưới package gốc `com.example.shop`:

~~~text
com.example.shop
├── ShopApplication.java
├── checkout/
│   ├── CheckoutCompleted.java       # Event workflow công khai
│   └── internal/
│       ├── CheckoutProcess.java     # Tiến độ và quy tắc chuyển bước
│       ├── CheckoutProcessRepository.java
│       ├── CheckoutCoordinator.java # Quyết định bước kế tiếp
│       ├── CheckoutEventHandlers.java
│       └── CommandOutbox.java       # Ý định gọi API bền vững
├── inventory/
│   ├── InventoryOperations.java     # API command công khai
│   ├── StockReserved.java           # Event kết quả công khai
│   └── internal/
│       └── InventoryReservationService.java
├── payments/
│   ├── PaymentOperations.java       # API command công khai
│   ├── PaymentCaptured.java         # Event kết quả công khai
│   └── internal/
│       └── PaymentService.java
└── notifications/
    └── internal/
        └── CheckoutCompletedListener.java
~~~

Hướng phụ thuộc mã nguồn được giữ rõ:

~~~mermaid
flowchart LR
    C["checkout"] -->|"sử dụng public APIs + events"| I["inventory"]
    C -->|"sử dụng public APIs + events"| P["payments"]
    N["notifications"] -->|"lắng nghe CheckoutCompleted"| C
~~~

`inventory` và `payments` **không import implementation của `checkout`**. Khi thực hiện yêu cầu, chúng nhận `checkoutId` dưới dạng UUID/value object trong API và phát event kết quả thuộc **API của chính chúng**. Việc dùng cùng một ID không đồng nghĩa các module phải phụ thuộc trực tiếp vào entity của nhau.

**Lưu ý:** sơ đồ là thiết kế tham chiếu, không phải một thư viện process manager có sẵn do Spring Modulith tạo tự động. Chúng ta phải hiện thực lưu trạng thái, bảo vệ concurrency và gửi command an toàn.

### 7.1. Event kết quả do module chịu trách nhiệm phát

~~~java
// com/example/shop/inventory/StockReserved.java
package com.example.shop.inventory;

import java.time.Instant;
import java.util.UUID;

public record StockReserved(
        UUID eventId,
        UUID correlationId,
        UUID checkoutId,
        UUID reservationId,
        Instant occurredAt
) {}
~~~

~~~java
// com/example/shop/payments/PaymentCaptured.java
package com.example.shop.payments;

import java.time.Instant;
import java.util.UUID;

public record PaymentCaptured(
        UUID eventId,
        UUID correlationId,
        UUID checkoutId,
        UUID paymentId,
        Instant occurredAt
) {}
~~~

Mỗi `public record` ở ví dụ trên thuộc **file Java riêng** đúng tên. Event cần có ID bất biến, correlation ID để truy vết, `checkoutId` để tìm đúng quy trình và thông tin cần thiết cho bước tiếp theo. Trong hệ thống thật, constructor nên kiểm tra các trường bắt buộc và có hợp đồng serialization phù hợp với Event Publication Registry.

### 7.2. Listener không quyết định workflow riêng lẻ

~~~java
// com/example/shop/checkout/internal/CheckoutEventHandlers.java
package com.example.shop.checkout.internal;

import com.example.shop.inventory.StockReserved;
import com.example.shop.payments.PaymentCaptured;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class CheckoutEventHandlers {
    private final CheckoutCoordinator coordinator;

    CheckoutEventHandlers(CheckoutCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @ApplicationModuleListener
    void on(StockReserved event) {
        coordinator.onStockReserved(event);
    }

    @ApplicationModuleListener
    void on(PaymentCaptured event) {
        coordinator.onPaymentCaptured(event);
    }
}
~~~

Điểm khác với điều phối ẩn là handler ở đây **không tự suy đoán trạng thái của module khác và không quyết định toàn bộ chính sách**. Nó chuyển event đến `CheckoutCoordinator` — nơi tập trung quy tắc chuyển bước và chịu trách nhiệm xác định hành động kế tiếp.

### 7.3. Coordinator quản lý trạng thái và ý định command

~~~java
// com/example/shop/checkout/internal/CheckoutCoordinator.java
package com.example.shop.checkout.internal;

import com.example.shop.inventory.StockReserved;
import com.example.shop.payments.PaymentCaptured;
import com.example.shop.checkout.CheckoutCompleted;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class CheckoutCoordinator {
    private final CheckoutProcessRepository processes;
    private final CommandOutbox commands;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    CheckoutCoordinator(CheckoutProcessRepository processes,
                        CommandOutbox commands,
                        ApplicationEventPublisher events,
                        Clock clock) {
        this.processes = processes;
        this.commands = commands;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void onStockReserved(StockReserved event) {
        // Repository dùng lock/version phù hợp để chống hai handler đồng thời.
        CheckoutProcess process =
                processes.getForUpdate(event.checkoutId());

        // false khi đã xử lý event hoặc tiến độ không cho phép chuyển bước.
        if (!process.recordStockReservedOnce(
                event.eventId(), event.reservationId())) {
            return;
        }

        // Ghi Ý ĐỊNH gọi payment, không gọi cổng thanh toán trong transaction.
        commands.enqueuePaymentCapture(
                process.checkoutId(),
                process.orderId(),
                process.paymentIdempotencyKey(),
                event.correlationId());
    }

    @Transactional
    public void onPaymentCaptured(PaymentCaptured event) {
        CheckoutProcess process =
                processes.getForUpdate(event.checkoutId());

        if (!process.recordPaymentCapturedOnce(
                event.eventId(), event.paymentId())) {
            return;
        }

        events.publishEvent(new CheckoutCompleted(
                UUID.randomUUID(),
                event.correlationId(),
                process.checkoutId(),
                process.orderId(),
                Instant.now(clock)));
    }
}
~~~

Các kiểu `CheckoutProcess`, `CheckoutProcessRepository` và `CommandOutbox` là **abstraction minh họa**, không phải API dựng sẵn của Spring Modulith. Trong implementation thực, `recordStockReservedOnce` phải chuyển từ `WAITING_FOR_STOCK` sang `WAITING_FOR_PAYMENT` đúng một lần và lưu được event đã xử lý hoặc một unique constraint tương ứng. Tương tự, `recordPaymentCapturedOnce` chỉ hoàn tất workflow từ trạng thái hợp lệ.

Mục tiêu của đoạn mã là thể hiện **ranh giới transaction**:

1. Handler nhận event kết quả.
2. Coordinator khóa/kiểm soát version của bản ghi workflow, kiểm tra transition hợp lệ.
3. Coordinator cập nhật tiến độ và **ghi ý định command vào outbox trong cùng transaction**.
4. Một dispatcher riêng đọc command sau commit rồi gọi `PaymentOperations.captureOnce(...)` với **idempotency key ổn định**, không giữ transaction database khi chờ mạng.
5. Module `payments` xác nhận kết quả, cập nhật dữ liệu nó sở hữu và phát `PaymentCaptured`; coordinator nhận event để chuyển trạng thái tiếp.

`CheckoutCompleted` cũng là event public trong module `checkout`:

~~~java
// com/example/shop/checkout/CheckoutCompleted.java
package com.example.shop.checkout;

import java.time.Instant;
import java.util.UUID;

public record CheckoutCompleted(
        UUID eventId,
        UUID correlationId,
        UUID checkoutId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

Module `notifications` có thể nghe `CheckoutCompleted` để gửi xác nhận; `checkout` không cần gọi implementation của `notifications`. Đây là nơi **choreography** tiếp tục phù hợp: việc gửi thông báo là tác động phụ sau khi workflow đã hoàn tất.

## 8. Command outbox: tách quyết định với gửi yêu cầu

Một coordinator có thể cập nhật trạng thái thành `WAITING_FOR_PAYMENT` rồi gọi thẳng cổng thanh toán bên ngoài ngay trong transaction. Cách này rủi ro:

- Nếu thanh toán thành công nhưng transaction DB rollback, hệ thống có tiền đã thu nhưng workflow không ghi nhận.
- Nếu mạng treo, transaction giữ tài nguyên và khóa quá lâu.
- Nếu process chết giữa lúc ghi trạng thái và lúc gọi thanh toán, không biết đã gửi command hay chưa.

Mẫu **transactional outbox cho command** giải quyết phần ghi nhận ý định:

~~~text
Transaction của checkout:
  UPDATE checkout_process SET state = 'WAITING_FOR_PAYMENT'
  INSERT INTO checkout_command_outbox (
      command_id, checkout_id, kind, idempotency_key, status
  ) VALUES (..., 'PAYMENT_CAPTURE', ..., 'PENDING')
COMMIT

Dispatcher sau commit:
  claim một command PENDING bằng lock/lease
  -> gọi PaymentOperations.captureOnce(...) với idempotency_key
  -> ghi nhận tình trạng dispatch và chờ PaymentCaptured/PaymentFailed
~~~

Không coi outbox là cơ chế exactly-once: dispatcher có thể crash sau khi bên nhận xử lý command nhưng trước khi đánh dấu nó đã gửi. Do đó **phía nhận command phải idempotent** theo `commandId` hoặc khóa nghiệp vụ ổn định. Cần tránh giữ database transaction mở trong lúc gọi HTTP/cổng thanh toán.

**Đừng nhầm hai loại lưu trữ:**

| Thành phần | Mục đích | Sở hữu |
| --- | --- | --- |
| Checkout process store | Trạng thái và điều kiện chuyển bước của workflow | `checkout` |
| Command outbox | Ý định gọi API/broker cho bước tiếp theo, có cơ chế gửi lại | `checkout` |
| Event Publication Registry | Theo dõi việc giao application event cho transactional listeners | Hạ tầng Spring Modulith |
| Ledger/transaction của payments | Sự thật thanh toán và khóa idempotency | `payments` |

Event Publication Registry **không tự thay thế** process store hoặc command outbox của một workflow. Nó giúp theo dõi publication cho listener sau commit; còn quy tắc “khi nào gọi payment” là trách nhiệm của coordinator.

## 9. Lỗi, retry, idempotency và bù trừ

Một quy trình có điều phối rõ ràng phải nêu cách xử lý **từng bước thất bại**:

| Tình huống | Không nên làm | Cách thiết kế đúng hướng |
| --- | --- | --- |
| Giữ hàng bị từ chối | Cho thanh toán tiếp vì listener payment đã nhận `OrderPlaced` | Chuyển checkout sang `FAILED`, không phát ý định thu tiền |
| Thu tiền timeout | Tạo command mới với khóa mới mỗi lần retry | Phát lại cùng command với idempotency key ổn định, kiểm tra kết quả phía payments |
| Thu tiền thất bại vĩnh viễn | Để tồn kho giữ mãi | Chuyển sang `COMPENSATION_REQUIRED`, phát lệnh release inventory có kiểm soát |
| Listener nhận `StockReserved` hai lần | Gửi hai lệnh thu tiền | State transition idempotent + unique command key |
| `PaymentCaptured` đến trước `StockReserved` | Tự bỏ qua không ghi dấu hoặc “đoán” đã giữ hàng | Chọn chính sách lưu event pending, đối soát hoặc kiểm tra trạng thái bất thường |
| JVM chết sau commit nguồn | Giả định listener chắc chắn đã chạy | Registry bền vững + phục hồi publication; process state vẫn là nguồn tiến độ |
| Dispatcher crash sau khi payment đã nhận command | Gọi payment với khóa ngẫu nhiên lần hai | Gửi lại bằng cùng idempotency key; payments chịu trách nhiệm chống thu tiền trùng |

**Bù trừ (compensation)** khác rollback database. Khi transaction giữ hàng đã commit, rồi thanh toán không thể hoàn tất, không thể rollback transaction cũ bằng một annotation. Phải có **nghiệp vụ giải phóng reservation** hoặc hành động đảo ngược phù hợp. Bù trừ có thể thất bại và cũng cần trạng thái, retry, giám sát riêng.

Không phải mọi sự cố đều tự retry vô hạn. Ví dụ `PaymentFailed` do thẻ bị từ chối có thể cần chuyển workflow sang `FAILED` hoặc chờ người dùng đổi phương thức; timeout mạng có thể phù hợp với retry có backoff. Phân loại lỗi theo nghiệp vụ, không chỉ theo exception.

**Idempotency có hai tầng:**

1. Handler/process transition không được tiến thêm bước hai lần khi nhận lại cùng event: kiểm tra `eventId`/trạng thái và ràng buộc duy nhất.
2. Command thực thi bên ngoài không được tạo hai tác động nghiệp vụ khi được gửi lại: khóa `paymentIdempotencyKey` được bên nhận tôn trọng.

Chỉ dùng `correlationId` để deduplicate toàn bộ workflow là sai: nhiều event và command hợp lệ có thể cùng chia sẻ correlation ID.

## 10. Event Publication Registry giúp gì khi nhiều handler nối nhau?

Spring Modulith cung cấp **Event Publication Registry** để theo dõi sự kiện được giao tới transactional listeners. Với backend bền vững được cấu hình phù hợp, publication có thể được đăng ký trong transaction nguồn và đánh dấu hoàn tất sau khi listener xử lý thành công.

Một chuỗi event nhiều bước có thể phát sinh nhiều publication khác nhau:

~~~text
StockReserved(eventId=E1, checkoutId=C42)
    -> CheckoutEventHandlers.on(StockReserved)     COMPLETED

PaymentCaptured(eventId=E2, checkoutId=C42)
    -> CheckoutEventHandlers.on(PaymentCaptured)  INCOMPLETE

CheckoutProcess(C42)
    state = WAITING_FOR_PAYMENT
~~~

Nếu xử lý `PaymentCaptured` lỗi, registry giúp xác định publication chưa hoàn tất và hỗ trợ khôi phục theo phiên bản/cấu hình đang sử dụng. Nhưng registry **không tự ra quyết định** rằng cần gửi lại command thu tiền hay hoàn trả tồn kho; quyết định đó nằm ở process state và luật workflow.

Một event có thể có nhiều listener. Registry theo dõi tiến độ **publication đến từng listener** chứ không phải đặt một cờ `processed` chung cho toàn bộ event. Nếu `analytics` xử lý xong còn checkout listener thất bại, không nên vì thế xem workflow đã tiến bước.

Những giới hạn cần lưu ý:

- Cần chọn và cấu hình implementation registry thực sự bền vững (ví dụ JDBC/JPA) và transaction nhất quán; annotation listener không tự bảo đảm độ bền.
- `@ApplicationModuleListener` xử lý sau commit và bất đồng bộ; một listener thất bại **không rollback** được transaction nguồn đã commit.
- Cần thiết lập cơ chế resubmit/recovery và giới hạn lần thử phù hợp, không giả định hệ thống tự retry vô hạn.
- Event có thể được xử lý lại sau khi đã thực hiện tác động, nếu crash xảy ra trước khi completion được lưu. Do đó idempotency là bắt buộc.
- Publication Registry không bảo đảm exactly-once đối với payment gateway, email hay HTTP side effects.

Vì vậy, **registry trả lời “việc giao event cho listener đã hoàn tất chưa?”**; còn **process manager trả lời “workflow đang ở trạng thái nào và tiếp theo phải làm gì?”**. Hai câu hỏi khác nhau và cần hai mô hình trạng thái phù hợp.

## 11. Giữ ranh giới module khi đưa coordinator vào

Một coordinator dễ trở thành “God service” nếu nó bắt đầu đọc/ghi entity nội bộ của các module khác. Để tránh:

- Chỉ import **public API** của `inventory`/`payments` và các event kết quả của chúng, không phụ thuộc repository/entity nội bộ.
- Coordinator sở hữu `checkout_process` và command outbox, không sở hữu bảng inventory reservation hoặc payment transaction.
- Giữ thuật toán nghiệp vụ cục bộ ở module owner: `inventory` quyết định có đủ hàng; `payments` quyết định thanh toán hợp lệ; `checkout` quyết định thứ tự và điều kiện chuyển bước.
- Sử dụng DTO/value object công khai, ID ổn định và hợp đồng lỗi rõ ràng.
- Kiểm tra đồ thị module không có vòng phụ thuộc: coordinator dùng module cung cấp API; module cung cấp **không gọi ngược implementation của coordinator**.

Kiểm tra kiến trúc cơ bản:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {
    @Test
    void moduleDependenciesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` kiểm tra các phụ thuộc module và quy tắc public API được Spring Modulith nhận diện; nó không chứng minh transaction, business compensation hay native SQL luôn đúng. Kết hợp với code review và kiểm thử hành vi.

## 12. Quan sát điều phối: trạng thái quy trình khác log handler

Khi quy trình bị treo, chỉ có log `"StockReserved received"` không đủ kết luận. Cần quan sát:

| Thành phần | Dữ liệu cần biết | Tác dụng |
| --- | --- | --- |
| Workflow | `checkoutId`, state, version, `updatedAt`, deadline | Biết bước hiện tại và trạng thái nào đang chờ |
| Event | `eventId`, `correlationId`, causation ID nếu có | Liên kết nguyên nhân giữa nhiều module |
| Publication | Listener đích, tình trạng completion, lỗi, tuổi publication | Biết sự cố giao event |
| Command outbox | `commandId`, idempotency key, lần gửi, lỗi và lease | Biết command đã gửi hay còn chờ |
| Domain owner | `reservationId`, `paymentId` và trạng thái kết quả | Đối chiếu sự thật nghiệp vụ ở mỗi module |

Ví dụ dashboard/chẩn đoán:

~~~text
checkoutId     = C42
correlationId  = R8
workflow.state = WAITING_FOR_PAYMENT
workflow.ver   = 3

inventory: reservation confirmed (reservationId=I77)
command:   PAYMENT_CAPTURE, dispatched twice with SAME idempotency key
payments:  result still pending
registry:  no incomplete StockReserved publication

Next action: đối soát trạng thái payment và timeout policy
~~~

Không dùng `correlationId` hoặc `checkoutId` làm tag metrics có cardinality cực cao; giữ các ID chi tiết ở structured logs/traces và dữ liệu workflow. Tags metrics nên là `workflow_type`, `state`, `handler`, `result`, `error_type` có số lượng giá trị hữu hạn.

## 13. Kiểm thử việc tránh điều phối ẩn

### 13.1. Kiểm thử state transition

Giả sử coordinator nhận event `StockReserved` với `checkoutId` hợp lệ:

~~~java
// Pseudocode kiểm thử nghiệp vụ, không phải một test runnable hoàn chỉnh.
var event = new StockReserved(
        eventId, correlationId, checkoutId, reservationId, occurredAt);

coordinator.onStockReserved(event);

assertThat(processes.find(checkoutId).state())
        .isEqualTo(WAITING_FOR_PAYMENT);
assertThat(outbox.pendingPaymentCommands(checkoutId)).hasSize(1);

// Nhận lại cùng event -> không tạo command thứ hai.
coordinator.onStockReserved(event);
assertThat(outbox.pendingPaymentCommands(checkoutId)).hasSize(1);
~~~

Trong test thực tế, `CheckoutProcessRepository` và `CommandOutbox` cần là fake repository với ngữ nghĩa transaction được mô phỏng hoặc các adapter database kiểm thử; với concurrent delivery, nên kiểm tra bằng database có lock/unique constraint thật.

### 13.2. Ma trận tích hợp quan trọng

| Tình huống | Kết quả mong đợi |
| --- | --- |
| `StockReserved` tới một lần | Workflow sang `WAITING_FOR_PAYMENT`, đúng một command intent |
| `StockReserved` tới hai lần | Không ghi đè trạng thái và không tạo command thứ hai |
| Hai listener xử lý cùng checkout song song | Chỉ một transition thắng, version/lock bảo vệ |
| `PaymentCaptured` đến trước điều kiện giữ hàng | Không đánh dấu `COMPLETED` trái quy tắc; có đối soát |
| `PaymentFailed` sau khi đã giữ hàng | Chuyển sang chính sách bù trừ phù hợp |
| Transaction xử lý event rollback | Không có transition/outbox của lần xử lý thất bại được commit |
| JVM chết sau workflow commit nhưng trước dispatch command | Dispatcher có thể khôi phục command outbox |
| JVM chết sau tác động thanh toán nhưng trước xác nhận gửi command | Gửi lại với cùng idempotency key, không thu tiền hai lần |
| Handler event bị lỗi trước completion | Publication có thể phục hồi theo registry cấu hình |
| Một consumer reporting lỗi | Không làm sai quyết định workflow của checkout |

Với `@ApplicationModuleListener`, integration test phải **thực sự commit** transaction nguồn để kích hoạt callback sau commit, sau đó chờ bất đồng bộ với timeout. Một method test `@Transactional` tự rollback có thể khiến listener `AFTER_COMMIT` không chạy. Không dùng `Thread.sleep` với thời gian tùy tiện như bằng chứng thứ tự nghiệp vụ.

### 13.3. Kiểm thử cấu trúc và review

Ngoài `ApplicationModules.verify()`, cần kiểm tra:

1. Không có listener nào kiểm tra trực tiếp repository nội bộ module khác để suy đoán bước đã xong.
2. Không dùng `@Order` hoặc thứ tự thread để giữ bất biến nghiệp vụ.
3. Quy tắc chuyển trạng thái workflow tập trung tại process owner và có thể test độc lập.
4. Mỗi command ngoài transaction có idempotency key; mỗi event kết quả được xử lý idempotent.
5. Có trạng thái và đường xử lý lỗi vĩnh viễn, timeout, bù trừ và can thiệp vận hành.

## 14. Kế hoạch chuyển từ chuỗi listener ẩn sang điều phối tường minh

Không nhất thiết phải viết lại toàn bộ hệ thống. Có thể chuyển đổi theo từng bước:

1. **Vẽ chuỗi event thực tế**, gồm các listener và dữ liệu chúng đọc/ghi. Đánh dấu cạnh “A cần xong trước B” và “nếu A lỗi thì B phải dừng”.
2. **Phân loại fan-out độc lập và workflow có ràng buộc.** Giữ các tác vụ phụ thực sự độc lập trong listener đơn giản.
3. **Chọn process owner** phù hợp với ngôn ngữ nghiệp vụ, không mặc định đặt mọi điều phối vào `orders` hay một module `common` lớn.
4. **Định nghĩa state machine và các kết quả rõ nghĩa** như `StockReserved`, `StockReservationRejected`, `PaymentCaptured` và `PaymentFailed`.
5. **Tạo process store** có version/idempotency, rồi chuyển logic quyết định bước kế tiếp từ listener sang coordinator.
6. **Tách gửi command ra khỏi transaction** nếu có side effect mạng hoặc xử lý lâu; dùng command outbox và idempotency ở module nhận.
7. **Cấu hình registry và quan sát**, xác minh restart/retry không làm trôi trạng thái hoặc gây lặp side effect.
8. **Bổ sung tests** cho rollback, giao lại event, out-of-order, crash và bù trừ trước khi bỏ chuỗi handler cũ.

**Cảnh báo triển khai:** Chuyển từ gọi API đồng bộ sang event sau commit thay đổi tính nhất quán của quy trình. Trước khi thay phải nêu rõ thời điểm nào được phép trả “đã thanh toán”, “đã xác nhận” và “hoàn tất checkout”. Không dùng lời gọi `publishEvent(...)` làm bằng chứng rằng toàn bộ chuỗi đã hoàn tất.

## 15. Bài thực hành

Cho workflow giữ hàng rồi thu tiền. Phiên bản đầu tiên có hai listener cùng nghe `OrderPlaced`: `InventoryListener` giữ hàng; `PaymentListener` đọc bảng reservation rồi thu tiền khi thấy hàng đã giữ.

Hãy cải tiến theo yêu cầu:

1. Chỉ ra **điều phối ẩn** và rủi ro với thứ tự, rollback, retry và truy cập bảng xuyên module.
2. Thiết kế state machine cho `checkout` với `WAITING_FOR_STOCK`, `WAITING_FOR_PAYMENT`, `COMPLETED`, `COMPENSATION_REQUIRED`, `FAILED`.
3. Xác định module nào sở hữu `StockReserved`, `PaymentCaptured`, `CheckoutCompleted`; không đưa entity JPA vào public event.
4. Viết listener `@ApplicationModuleListener` cho hai event kết quả, nhưng để quy tắc quyết định bước tiếp theo nằm trong `CheckoutCoordinator`.
5. Mô hình hóa command outbox để lưu yêu cầu thanh toán và khóa idempotency; giải thích cách phục hồi khi dispatcher crash.
6. Thử gửi `StockReserved` hai lần và nhận `PaymentCaptured` trước thời điểm hợp lệ. Xác minh workflow không chuyển sai trạng thái.
7. Thử timeout thanh toán sau khi hàng đã giữ. Viết chính sách bù trừ rõ ràng và trạng thái theo dõi bù trừ.
8. Kiểm tra ranh giới bằng `ApplicationModules.verify()` và bổ sung dashboard/log theo `checkoutId`.

**Câu hỏi tự đánh giá:**

- Vì sao `@Order` không phải cơ chế điều phối an toàn giữa các `@ApplicationModuleListener`?
- Khi reporting và notifications độc lập, có cần process manager không?
- Registry biết một event đã giao thành công; tại sao nó chưa đủ để kết luận checkout đã hoàn tất?
- Làm thế nào bảo đảm retry payment không thu tiền hai lần sau khi JVM crash?
- Khi một bước đã commit nhưng bước tiếp theo thất bại, tại sao cần compensation thay vì kỳ vọng rollback transaction cũ?

## 16. Ghi nhớ

**Tránh điều phối ẩn** nghĩa là không để quy tắc workflow sống rải rác trong các handler và phụ thuộc vào thứ tự thực thi tình cờ. Với những tác vụ độc lập, **choreography bằng application events** là cách giảm coupling hiệu quả. Với quy trình nhiều bước cần trạng thái, điều kiện tiên quyết, retry và bù trừ, hãy **mô hình hóa orchestration tường minh** bằng một process owner, state machine, command API/outbox và event kết quả.

Spring Modulith hỗ trợ phát/nhận event, listener sau commit và Event Publication Registry để theo dõi việc xử lý; nó **không tự động quyết định business workflow hoặc đảm bảo exactly-once cho tác động bên ngoài**. Quy tắc đúng là: event công bố sự thật, coordinator quyết định bước tiếp, module owner giữ quyền sở hữu dữ liệu, và hệ thống lưu đủ trạng thái để phục hồi minh bạch sau lỗi.

**Tài liệu tham khảo chính thức:**

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
