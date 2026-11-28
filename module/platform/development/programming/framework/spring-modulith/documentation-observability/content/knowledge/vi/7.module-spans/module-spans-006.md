# Module invocation type

## Mục tiêu học tập

Trong chương **Module spans**, bài học này giải thích trường `module.invocation-type` của những span do Spring Modulith tạo khi ứng dụng Spring Boot tương tác qua ranh giới application module.

Sau bài học, bạn có thể:

1. Giải thích **invocation type** cho biết loại điểm vào của một module, và phân biệt nó với tên module, tên method, HTTP method hay loại phụ thuộc trong module graph.
2. Phân biệt hai loại lời gọi được Spring Modulith mô tả: **`bean`** và **`event listener`**.
3. Đọc các key `module.identifier`, `module.name`, `module.invocation-type`, `module.method` trên một module entry span.
4. Giải thích vì sao trace có thể bị chia khi event listener xử lý bất đồng bộ, cũng như vai trò của trace context propagation.
5. Xác minh instrumentation bằng một luồng nghiệp vụ cụ thể, nhận biết trường hợp thiếu span và tránh rút ra kết luận nghiệp vụ sai từ metadata quan sát.
6. Sử dụng invocation type để lọc, so sánh và điều tra tương tác module mà không tạo metric tags có cardinality không kiểm soát.

**Bối cảnh học phần:** Spring Modulith hỗ trợ sinh tài liệu ranh giới application module và quan sát tương tác trong ứng dụng Spring Boot. Module graph giúp hiểu các quan hệ phụ thuộc được phát hiện; Actuator công bố cấu trúc module khi được cấu hình; Micrometer spans, event metrics, tracing và context propagation hỗ trợ kiểm chứng hành vi vận hành. **`module.invocation-type` thuộc lớp quan sát runtime**, trả lời cụ thể một lời gọi vào module đã được nhận diện theo loại nào.

> Phạm vi API: Theo tài liệu **Spring Modulith 2.2**, Module Entry Span có tag `module.invocation-type` với hai loại được mô tả là **“event listener”** và **“bean”**. Tên key ổn định theo tài liệu phiên bản này; khi đổi release hoặc dùng backend chuyển đổi tag, hãy đối chiếu dữ liệu thực tế trước khi viết truy vấn cố định.

## 1. Module invocation type là gì?

Khi một phần trong ứng dụng gọi thành phần thuộc API của một application module, Spring Modulith có thể chặn lời gọi đó bằng một aspect và tạo **Micrometer observation/span**. Một application module không chỉ được gọi bằng lời gọi method trực tiếp trên Spring bean; nó còn có thể tiếp nhận **application event** qua một listener.

`module.invocation-type` là nhãn giúp người đọc span trả lời câu hỏi:

> **Điểm vào module đang được quan sát thuộc kiểu lời gọi thông thường trên Spring bean hay thuộc kiểu gọi một application event listener?**

Nhãn này bổ sung ý nghĩa cho module span. Nó không phải tên riêng của module hoặc identifier của một sự kiện.

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **`module.identifier`** | Module nào được đi vào? | `inventory`, `payments` |
| **`module.name`** | Tên hiển thị của module là gì? | `Inventory` |
| **`module.method`** | Method nào đã được gọi ở điểm quan sát? | `InventoryFacade.reserve(…)` |
| **`module.invocation-type`** | Lời gọi vào module theo cơ chế nào? | `bean` hoặc `event listener` |
| **`traceId`** | Những span nào thuộc cùng trace được theo dõi? | Một định danh trace do hệ thống tracing tạo |
| **`spanId`** | Span cụ thể nào trong trace? | Một định danh span |
| **`orderId`** | Đơn hàng nghiệp vụ nào? | ID do ứng dụng quản lý, không phải tag mặc định của Modulith |

**Ví dụ đọc nhanh:**

- `module.identifier=inventory`, `module.invocation-type=bean`: một điểm vào `inventory` được quan sát dưới dạng lời gọi Spring bean.
- `module.identifier=payments`, `module.invocation-type=event listener`: một listener được instrument tại module `payments` đang nhận lời gọi xử lý event.

Không nên diễn giải “bean” là một loại HTTP request hoặc “event listener” là một message broker cụ thể. Đây là cách Spring Modulith **phân loại điểm vào module**, không phải giao thức truyền dữ liệu.

## 2. Hai loại invocation chính

### 2.1. `bean`: lời gọi method trên thành phần Spring

Loại **bean** thường xuất hiện khi một thành phần thuộc API công khai của application module được gọi như một Spring bean. Ví dụ `orders` gọi `InventoryFacade.reserve(…)` trong `inventory`.

Diễn biến thường gặp:

1. Spring đã tạo bean của `InventoryFacade`.
2. Một Spring component khác lấy bean thông qua dependency injection.
3. Lời gọi đi qua điểm được instrumentation của Spring Modulith.
4. Một module observation/span được tạo cho lời gọi và mang các tag nhận diện module, method, invocation type.
5. Method trả về hoặc ném lỗi; span hoàn tất theo hành vi instrumentation.

Loại `bean` mô tả **đường gọi qua bean**. Nó **không tự chứng minh**:

- lời gọi đi qua mạng;
- method được thực thi trong một database transaction mới;
- dữ liệu đã được commit;
- nghiệp vụ đã hoàn tất;
- đây nhất thiết là lời gọi xuyên module: phạm vi span phụ thuộc API module và instrumentation thực tế.

### 2.2. `event listener`: lời gọi vào hàm tiếp nhận application event

Loại **event listener** biểu thị điểm vào module được quan sát là một lời gọi tới listener nhận application event, chẳng hạn method dùng `@EventListener` hoặc `@TransactionalEventListener` được cấu hình đúng.

Đặc trưng:

- Bên phát công bố một event thay vì gọi trực tiếp method listener như một API nghiệp vụ thông thường.
- Spring event infrastructure xác định listener phù hợp rồi gọi method xử lý.
- Spring Modulith nhận diện lời gọi listener và có thể đánh dấu module entry span bằng invocation type tương ứng.
- Listener có thể xử lý đồng bộ hoặc bất đồng bộ, tùy loại listener và cấu hình; **invocation type không thay thế thông tin về cách lên lịch xử lý**.

Nếu listener nhận `OrderPlaced` rồi thực hiện thay đổi ở `payments`, tag cho biết điểm vào là event listener. Nó **không nói rằng event đến từ Kafka**, event đã được lưu bền, hoặc listener xử lý an toàn trước retry.

### 2.3. Bảng so sánh

| Tiêu chí | `bean` | `event listener` |
| --- | --- | --- |
| Đường vào điển hình | Gọi method trên Spring bean thuộc API module. | Spring gọi listener khi application event được phát. |
| Mức liên kết trong mã | Caller thường phụ thuộc trực tiếp vào API được gọi. | Publisher biết kiểu event, không nhất thiết phụ thuộc trực tiếp vào listener. |
| Luồng thực thi | Thường cùng call stack khi đồng bộ. | Có thể cùng thread hoặc bất đồng bộ tùy listener. |
| Điểm cần xem trong trace | Module nào được gọi, method nào, độ trễ và exception. | Module nào nhận event, listener nào, độ trễ, retry và liên hệ với publication. |
| Tag `module.invocation-type` | `bean` theo phân loại được tài liệu hóa. | `event listener` theo phân loại được tài liệu hóa. |
| Điều tag không bảo đảm | Dữ liệu đã commit hoặc nghiệp vụ thành công. | Exactly-once, thứ tự xử lý, propagation hay transaction thành công. |

**Lưu ý về giá trị trong backend:** Tài liệu dùng cách diễn đạt “bean” và “event listener”. Một exporter, hệ thống index hoặc quy ước tùy biến của ứng dụng có thể biến đổi biểu diễn. Khi cần filter chính xác, đọc ít nhất một span thực tế từ release của mình để xác nhận **giá trị chuỗi được lưu**.

## 3. Module entry span chứa những thông tin nào?

Theo mục *Observability Spans → Module Entry Span* của Spring Modulith, các tag được tài liệu hóa gồm:

| Key | Chức năng | Cách sử dụng |
| --- | --- | --- |
| `module.identifier` | Định danh kỹ thuật của application module. | Nhóm span theo module hoặc tìm chỗ chuyển giao giữa module. |
| `module.name` | Tên module thân thiện với người đọc. | Hiển thị trên dashboard và khi review trace. |
| `module.invocation-type` | Phân biệt loại lời gọi, ví dụ bean/event listener. | Lọc độ trễ hoặc lỗi của từng dạng điểm vào. |
| `module.method` | Method được thực thi trong module. | Khoanh vùng method tốn thời gian hoặc phát sinh exception. |

### 3.1. Low cardinality và high cardinality

Trong API quan sát của Spring Modulith, enum `ModulithObservations.LowKeys` mô tả `MODULE_IDENTIFIER`, `MODULE_NAME` và `INVOCATION_TYPE`. Enum `ModulithObservations.HighKeys` mô tả `MODULE_METHOD`.

Ý nghĩa thực hành:

- `module.identifier` và `module.invocation-type` có tập giá trị hữu hạn khi kiến trúc module ổn định; chúng thường thích hợp để lọc hoặc tổng hợp.
- `module.method` mô tả method cụ thể, có thể có nhiều biến thể theo signature/version; cần xem khả năng hỗ trợ và cardinality của backend.
- Giá trị tùy biến chứa `orderId`, `eventId`, `customerEmail` hoặc `traceId` **không được đưa vào metric tags** vì có thể tạo hàng triệu time series hoặc lộ thông tin.

**Không suy ra** rằng tất cả tag trên được xuất dưới cùng một dạng metric label ở mọi backend. Micrometer Observation, Micrometer Tracing, OpenTelemetry và công cụ lưu trữ có các cách chuyển đổi riêng. Hãy kiểm tra dữ liệu ở nơi cần truy vấn.

### 3.2. Ví dụ span ở dạng minh họa

Đây là **biểu diễn dễ đọc**, không phải JSON gốc hay định dạng bắt buộc của Spring Modulith:

~~~yaml
traceId: "example-trace-id"
spanId: "example-span-id"
name: "inventory module entry"
attributes:
  module.identifier: "inventory"
  module.name: "Inventory"
  module.invocation-type: "bean"
  module.method: "InventoryFacade.reserve"
durationMs: 18
status: "OK"
~~~

Từ dữ liệu này, có thể khẳng định rằng **một lời gọi vào điểm instrument của inventory được quan sát với thời lượng 18 ms**. Không thể kết luận reservation đã commit thành công hoặc không có retry trước/sau span đó nếu thiếu các bằng chứng khác.

Tương tự, một listener có thể được thể hiện ở dạng:

~~~yaml
name: "payments module entry"
attributes:
  module.identifier: "payments"
  module.invocation-type: "event listener"
  module.method: "PaymentPreparationListener.on"
durationMs: 9
~~~

Tên span, signature của method và các giá trị mô phỏng ở đây là **giả định của ví dụ**. Chỉ các **tên key** và **ý nghĩa phân loại** mới là phần cần đối chiếu với tài liệu framework.

## 4. Ví dụ xuyên suốt: đặt hàng, giữ kho và nhận event

Giả sử ứng dụng Spring Boot có module `orders`, `inventory` và `payments`. Yêu cầu nghiệp vụ: khi tạo đơn, dịch vụ đặt giữ kho trực tiếp; sau đó công bố sự kiện để thành phần thanh toán chuẩn bị xử lý.

~~~mermaid
flowchart LR
    H["HTTP POST /orders"] --> O["orders\nOrderService.place"]
    O -->|"Gọi Spring bean API"| I["inventory\nInventoryFacade.reserve"]
    O -->|"publish OrderPlaced"| E(("Application Event"))
    E -->|"Spring gọi listener"| P["payments\nPaymentPreparationListener.on"]
    I -.-> BI["Module span\ninvocation-type = bean"]
    P -.-> EV["Module span\ninvocation-type = event listener"]
~~~

Các khối chấm trong sơ đồ là **lát cắt quan sát giả định**. Hệ thống thực có thể có thêm span HTTP, SQL, transaction, message producer hoặc span khác do nhiều thư viện tạo. Không mặc định mỗi mũi tên trong sơ đồ sẽ có chính xác một span.

### 4.1. API bean ở module inventory

~~~java
package com.example.shop.inventory;

import java.util.UUID;
import org.springframework.stereotype.Service;

// Đặt trong package API của application module inventory.
@Service
public class InventoryFacade {

    public void reserve(UUID orderId) {
        // Minh họa: gọi service nội bộ và lưu reservation theo nghiệp vụ.
        // Phần thực thi lưu trữ được lược bỏ.
    }
}
~~~

`InventoryFacade` là Spring bean được công khai qua package API của module. Khi một phần khác gọi `reserve` qua Spring-managed bean và instrumentation hoạt động, đây là **ứng viên cho module entry span loại bean**.

Lưu ý: ví dụ chỉ biểu diễn cấu trúc và điểm quan sát; method trống không thực hiện giữ kho thật. Trong ứng dụng thực tế, đặt logic dữ liệu tại service/repository phù hợp, có kiểm tra bất biến và transaction.

### 4.2. Bên gọi thuộc module orders

~~~java
package com.example.shop.orders;

import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import com.example.shop.inventory.InventoryFacade;

@Service
public class OrderService {

    private final InventoryFacade inventory;
    private final ApplicationEventPublisher events;

    public OrderService(InventoryFacade inventory, ApplicationEventPublisher events) {
        this.inventory = inventory;
        this.events = events;
    }

    public void place(UUID orderId) {
        inventory.reserve(orderId);           // Lời gọi trực tiếp qua bean.
        events.publishEvent(new OrderPlaced(orderId)); // Publication event.
    }
}
~~~

Kiểu event riêng của ứng dụng:

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

Trong ví dụ này, `orders` phụ thuộc trực tiếp vào `InventoryFacade`. Lời gọi vào module `inventory` có thể mang invocation type `bean` nếu phù hợp điều kiện instrumentation.

Việc gọi `events.publishEvent(...)` **không đồng nghĩa** chính publication đó đã tạo module entry span loại event listener. Listener phải thật sự được chọn và gọi ở module đích; khi ấy chính lời gọi listener mới là điểm quan sát liên quan.

### 4.3. Event listener thuộc module payments

~~~java
package com.example.shop.payments;

import com.example.shop.orders.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentPreparationListener {

    @EventListener
    public void on(OrderPlaced event) {
        // Minh họa: tiếp nhận event và chuẩn bị xử lý thanh toán.
        // Chưa có kết nối cổng thanh toán thực.
    }
}
~~~

Khi Spring dispatch `OrderPlaced` tới listener, điểm vào `PaymentPreparationListener.on(...)` có thể được instrument và gắn invocation type `event listener`.

**Điểm khác nhau cần thấy:** `orders` không gọi `paymentPreparationListener.on(...)` trực tiếp. Spring event infrastructure kích hoạt method listener khi một event phù hợp được publish. Do đó cùng một application module có thể chứa cả API bean thường lẫn listener và xuất hiện với nhiều giá trị invocation type qua những luồng khác nhau.

### 4.4. Hạn chế của ví dụ

Để giữ bài học tập trung vào span type, ví dụ chưa cài đặt transaction, persist reservation, trạng thái thanh toán hoặc giao dịch ngoài. Một luồng đặt hàng thực cần chính sách rõ ràng khi `reserve` hoặc listener thất bại.

`@EventListener` với cơ chế event mặc định thường xử lý **đồng bộ**. Nếu sử dụng `@Async`, `@TransactionalEventListener` hoặc cơ chế publication registry, thời điểm và phương thức thực thi có thể khác. Những thay đổi đó **không biến một event listener thành lời gọi bean thường** về mặt ý nghĩa điểm vào, nhưng có thể làm thay đổi vị trí span, trace context và thời gian kết thúc nghiệp vụ.

## 5. Đọc timeline của một trace có cả hai invocation type

Với event listener đồng bộ và tracing được cấu hình, một hành trình quan sát được có thể trông như sau:

~~~text
HTTP POST /orders                                 0–75 ms
└── orders: OrderService.place                    4–67 ms
    ├── inventory: InventoryFacade.reserve       10–34 ms
    │   module.identifier=inventory
    │   module.invocation-type=bean
    └── payments: PaymentPreparationListener.on   40–51 ms
        module.identifier=payments
        module.invocation-type=event listener
~~~

Đây là **timeline minh họa**, không phải output được bảo đảm bởi Spring Modulith. Việc có span `orders: OrderService.place` phụ thuộc có thực sự là điểm module entry được instrument hay không; HTTP span phụ thuộc hạ tầng web/tracing. Quan hệ cha–con giữa các span có thể thay đổi theo điểm bắt đầu observation và cách propagation.

Từ timeline, ta có thể:

- Nhận diện `inventory` được đi vào theo nhánh bean và `payments` qua listener.
- Xác định tương đối đoạn nào chiếm nhiều thời gian trong một trace đã thu thập.
- Tìm method cần kiểm tra khi có lỗi hoặc độ trễ bất thường.

Không thể từ timeline này kết luận:

- sự kiện thanh toán đã được ghi bền;
- đơn hàng đủ điều kiện giao;
- số lượng hàng đã bị trừ đúng một lần;
- không có listener nào thất bại ngoài tập span đã thu thập;
- mọi thao tác thuộc cùng một transaction trong database.

**Invocation type mô tả nguồn gốc lời gọi, không đánh giá nghiệp vụ đúng hay sai.**

## 6. Khác biệt với dependency type của module graph

Đây là chỗ thường nhầm vì Spring Modulith dùng chữ “type” ở cả cấu trúc và quan sát runtime.

Module Actuator có thể cung cấp thông tin dependency, ví dụ JSON được lược giản:

~~~json
{
  "orders": {
    "displayName": "Orders",
    "basePackage": "com.example.shop.orders",
    "dependencies": [
      {
        "target": "inventory",
        "types": ["USES_COMPONENT"]
      }
    ]
  },
  "payments": {
    "displayName": "Payments",
    "basePackage": "com.example.shop.payments",
    "dependencies": [
      {
        "target": "orders",
        "types": ["EVENT_LISTENER"]
      }
    ]
  }
}
~~~

**Payload trên là dữ liệu minh họa về module graph**; quan hệ thực tế được phát hiện từ code. Chú ý hướng `payments → orders` trong graph có thể biểu diễn phụ thuộc của listener vào **event type** được định nghĩa trong module orders, mặc dù event được publish từ orders và xử lý tại payments.

So sánh:

| Thuộc tính | `dependencies[].types[]` trong module graph | `module.invocation-type` trong span |
| --- | --- | --- |
| Phạm vi | Quan hệ phụ thuộc **cấu trúc** giữa module. | Một **lời gọi runtime đã được instrument** vào module. |
| Nguồn dữ liệu | Phân tích module/class/bean/listener của ứng dụng. | Instrumentation của Spring Modulith và Micrometer observation. |
| Các giá trị được tài liệu hóa | `DEFAULT`, `USES_COMPONENT`, `EVENT_LISTENER`. | “bean”, “event listener”. |
| Ý nghĩa `EVENT_LISTENER` | Tồn tại phụ thuộc liên quan event listener giữa module. | Không phải giá trị của trường này; đây là category khác. |
| Khi nào có? | Có thể xem trong metadata cấu trúc khi ứng dụng không phát event nào. | Chỉ có trong span khi đường xử lý được gọi, instrument và thu thập. |
| Dùng làm gì? | Kiểm tra ranh giới, phát hiện coupling và thiết kế kiến trúc. | Điều tra tương tác runtime, độ trễ, lỗi hoặc tuyến xử lý. |

**Cảnh báo:** Không nên áp dụng phép biến đổi tự động kiểu `USES_COMPONENT → bean` và `EVENT_LISTENER → event listener` rồi coi đó là toàn bộ dữ liệu runtime. Một module có dependency tĩnh nhưng không được gọi trong request đang xem. Ngược lại, một trace có invocation type chỉ phản ánh đường chạy được ghi nhận, không tự mô tả tất cả phụ thuộc tĩnh.

## 7. Synchronous và asynchronous event listeners

Invocation type có thể vẫn là `event listener` cho cả xử lý đồng bộ và bất đồng bộ. Điều thay đổi đáng kể là **ngữ cảnh và cấu trúc trace**.

### 7.1. Listener đồng bộ

Ở cấu hình `@EventListener` thông thường, Spring có thể gọi listener ngay trên thread phát event. Một span listener có thể trở thành child span của span đang mở khi event được publish và tracing instrumentation kết nối đúng.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant HTTP as HTTP request
    participant Orders as orders
    participant Bus as Spring EventPublisher
    participant Pay as payments listener

    HTTP->>Orders: place(orderId)
    Orders->>Bus: publishEvent(OrderPlaced)
    Bus->>Pay: on(OrderPlaced)
    Note over Pay: invocation-type = event listener
    Pay-->>Bus: return
    Bus-->>Orders: return
    Orders-->>HTTP: response
~~~

Với xử lý đồng bộ, exception từ listener có thể truyền tới bên publish tùy cấu hình và xử lý ngoại lệ. Trace hữu ích để xem nơi lỗi phát sinh, nhưng **không được xem status span như kết quả transaction cuối cùng**.

### 7.2. Listener bất đồng bộ

Khi kết hợp `@Async` và `@EventListener`, method listener có thể chạy trên executor thread khác khi asynchronous execution được bật và cấu hình đúng.

Ví dụ có tính minh họa:

~~~java
@Component
class AsyncPaymentPreparationListener {

    @Async
    @EventListener
    public void on(OrderPlaced event) {
        // Chạy bất đồng bộ nếu @EnableAsync / executor được cấu hình phù hợp.
    }
}
~~~

Để kích hoạt kiểu chạy này, cần cấu hình `@EnableAsync` hoặc tương đương và kiểm tra executor thực tế. Không nên chỉ thêm annotation rồi mặc định mọi lời gọi sẽ chạy trên thread khác.

Dòng thời gian có thể là:

~~~text
Thread web:
  HTTP span ── orders publishes event ── HTTP ends

Thread executor:
                   payments event-listener span ───── finishes later
                   module.invocation-type=event listener
~~~

**Điểm cốt lõi:** Invocation type cho biết đây là listener, **không cho biết** trace context đã được truyền sang executor. Nếu propagation không được thiết lập, listener có thể thuộc trace khác hoặc không có parent đúng như kỳ vọng. Nếu context được truyền, cách span liên kết còn tùy instrumentation và mô hình bất đồng bộ.

### 7.3. Transactional event listener

`@TransactionalEventListener` hỗ trợ gắn thời điểm gọi listener với pha transaction, ví dụ `AFTER_COMMIT`:

~~~java
@Component
class PaymentAfterCommitListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        // Xử lý sau khi transaction phát event đã commit.
    }
}
~~~

Đoạn này là **ví dụ trong một ứng dụng đã cấu hình transaction phù hợp**; nếu không có transaction tương thích, listener có thể không chạy (trừ khi dùng tùy chọn fallback theo chính sách). Hãy nhớ:

- Event publication, transaction commit và listener invocation có thể là những thời điểm khác nhau.
- Listener chạy sau commit của transaction nguồn **không đồng nghĩa** thao tác bên ngoài trong listener đã thành công.
- Module entry span có invocation type `event listener` nếu listener được instrument, nhưng giá trị đó **không mã hóa `AFTER_COMMIT`**, retry count, transaction status hoặc thread model.

Việc listener có thể thất bại sau khi transaction nguồn commit là một lý do cần cơ chế retry/registry, idempotency và đối soát khi miền nghiệp vụ yêu cầu.

## 8. Bật module spans trong Spring Boot

### 8.1. Chọn dependency

Nếu cần cả Modulith Actuator và observability:

~~~groovy
dependencies {
    // Với Spring Modulith BOM tương thích đã được cấu hình.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Nếu chỉ muốn instrument tương tác module:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-observability-core'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Tương đương Maven cho core:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-observability-core</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Các ví dụ giả định **BOM/ dependency management của Spring Modulith** đã cung cấp phiên bản phù hợp với Spring Boot hiện dùng. Không sao chép số version ở một bài khác vào dự án mà chưa kiểm tra compatibility matrix.

### 8.2. Có instrumentation chưa đồng nghĩa có trace trên backend

`spring-modulith-observability-core` giúp tạo Micrometer observations/spans cho các điểm module API được instrument. Để xem trace trên Zipkin, Jaeger hoặc Tempo cần thêm:

1. **Micrometer tracing bridge** tương thích với phiên bản Spring Boot và hệ tracing được chọn;
2. **Exporter/transport** và cấu hình kết nối tới collector hoặc backend;
3. **Sampling** phù hợp với môi trường;
4. Quyền truy cập và retention của backend;
5. Context propagation phù hợp khi đi qua executor, async event listener hoặc message broker.

Các thành phần này thuộc hạ tầng observability chung. **Không cần khai báo `spring-modulith-observability-api` ở compile scope chỉ để đọc `module.invocation-type` có sẵn.** Artifact API riêng cần khi code ứng dụng thật sự import extension point, chẳng hạn `ModulithObservationConvention` để tùy biến convention.

### 8.3. Ví dụ cách bật endpoint phục vụ kiểm chứng

Nếu muốn xem endpoint Actuator metrics ở môi trường phát triển:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

Cấu hình này **không tự thêm** trace exporter và cũng **không tạo một HTTP endpoint dành riêng cho `module.invocation-type`**. Module invocation type là thuộc tính của observation/span, thường được đọc tại hệ thống tracing, hoặc trong test sử dụng Micrometer ObservationRegistry và tracing infrastructure.

Không nên expose mọi Actuator endpoint ra Internet; chỉ bật endpoint cần thiết và bảo vệ bằng cơ chế mạng/xác thực phù hợp.

## 9. Tìm invocation type trong trace một cách đáng tin cậy

Giả sử muốn tìm các event listener chậm ở module `payments`.

**Bước 1 – tạo một luồng có thể lặp lại.** Gửi một request tạo đơn trong môi trường thử nghiệm, bảo đảm `OrderPlaced` thực sự được publish và có listener đang hoạt động.

**Bước 2 – xác nhận có module instrumentation.** Trên backend tracing, tìm spans chứa `module.identifier` hoặc `module.name`. Nếu chỉ thấy HTTP span hoặc database span, chưa đủ để kết luận Spring Modulith đã instrument đúng API module.

**Bước 3 – mở thuộc tính span.** Xem `module.invocation-type` và `module.method` tại module entry span, phân biệt từ giá trị thực được exporter ghi nhận.

**Bước 4 – phân loại lời gọi.** Một listener trong payments có thể cho loại `event listener`; một API bean trong inventory có thể cho loại `bean`. Nếu khác kỳ vọng, kiểm tra nơi class được đặt, annotation listener, Spring proxy và phiên bản instrumentation.

**Bước 5 – đối chiếu trạng thái nghiệp vụ.** Nếu span báo OK nhưng đơn vẫn chưa được thanh toán hoặc giữ hàng, kiểm tra data store, transaction, handler retry và event publication registry. Không thay thế chúng bằng suy luận từ span.

### 9.1. Ví dụ điều kiện lọc, chỉ mang tính diễn giải

Một backend có thể cho phép filter theo các attribute:

~~~text
module.identifier = "payments"
AND module.invocation-type = "event listener"
~~~

hoặc:

~~~text
module.identifier = "inventory"
AND module.invocation-type = "bean"
~~~

**Đây là pseudo-query**, không phải ngôn ngữ truy vấn chung cho Zipkin, Jaeger, Grafana Tempo, PromQL hoặc Micrometer. Cú pháp filter, tên attribute sau exporter và biểu diễn giá trị có thể khác. Hãy lấy một span thực để tạo câu truy vấn đúng theo backend của dự án.

### 9.2. Điều gì có thể trả lời bằng invocation type?

| Câu hỏi | Dùng invocation type thế nào? | Giới hạn |
| --- | --- | --- |
| Module `payments` thường được vào qua API bean hay event listener? | Đếm/phân loại các **span đã quan sát** theo invocation type. | Bị ảnh hưởng bởi sampling và khả năng thu thập. |
| Listener nào kéo dài thời gian xử lý? | Lọc `event listener` rồi xem `module.method` và duration. | Duration span không luôn bằng thời gian toàn workflow. |
| Vì sao traces mất liên kết ở bước async? | Tìm listener span riêng, đối chiếu với event/correlation ID và propagation. | Invocation type không tự liên kết trace bị đứt. |
| Module nào có tần suất gọi trực tiếp lớn? | Lọc `bean` và nhóm theo module. | Không phải mọi nội bộ method đều được instrument. |
| Có bug nghiệp vụ nào làm ghi tiền hai lần? | Giúp tìm các listener span đã được chạy. | Phải kiểm tra idempotency và dữ liệu commit để khẳng định. |

### 9.3. Không dùng số span làm số giao dịch duy nhất

Một nghiệp vụ có thể phát nhiều span. Một event có thể được giao lại và tạo thêm invocation. Ngược lại, sampling có thể loại bỏ một phần span. Vì thế:

- **Số span loại bean** không nhất thiết bằng số request HTTP.
- **Số span loại event listener** không nhất thiết bằng số event duy nhất đã được phát.
- **Số span không lỗi** không chứng minh mọi transaction đã commit.
- **Không thấy span** chưa đủ kết luận method chưa chạy, vì có thể do instrumentation, proxy, propagation, sampling hoặc exporter.

Với thống kê nghiệp vụ chính xác, dùng mã định danh và dữ liệu có thẩm quyền. Với thống kê telemetry, ghi rõ đó là các **quan sát được thu thập**, cùng chính sách lấy mẫu và phạm vi thời gian.

## 10. Các lỗi thực tế khi kỳ vọng invocation type

### 10.1. Không thấy span `bean` dù method chắc chắn chạy

Các nguyên nhân thường gặp:

- Class gọi được nhưng **không thuộc API của application module** theo cách Modulith nhận diện; có thể là bean nội bộ.
- Method được gọi từ chính instance qua `this.method(...)` hoặc đường đi không qua proxy/interceptor đang dùng; các dạng self-invocation có thể bỏ qua Spring AOP advice.
- Bean được khởi tạo không qua Spring container, hoặc component/module discovery không như kỳ vọng.
- Dependency observability core/starter không có ở runtime, hoặc auto-configuration chưa hoạt động.
- Đường gọi đã chạy nhưng span bị sampling/exporter lọc, không hiển thị trong backend.
- Ứng dụng tùy biến convention làm đổi tên hoặc thuộc tính và dashboard vẫn dùng filter cũ.

**Hướng xử lý:** kiểm tra dependency và module detection trước; chạy một lời gọi trực tiếp vào bean API module qua Spring-managed reference, xem registry/traces trong môi trường thử nghiệm, rồi mới điều tra exporter.

### 10.2. Có listener xử lý event nhưng không thấy `event listener`

Tự kiểm tra:

1. Listener có thực sự được Spring đăng ký bằng annotation/API hỗ trợ không?
2. Event có đúng class/kiểu mà listener nhận không?
3. Listener chạy ngay, sau commit, hoặc bị hoãn bởi executor? Đã chờ đủ thời gian chưa?
4. Nếu là `@TransactionalEventListener`, có transaction phù hợp không?
5. Listener nằm ở module và cấu trúc API mà instrumentation nhận diện không?
6. Có tracing backend/sampling đủ để nhìn thấy lời gọi không?
7. Nếu async, span có thể ở trace khác do context propagation chưa đúng không?

Không nên đổi nhãn `module.invocation-type` thủ công để che đi việc listener không được instrument. Phải làm rõ nguyên nhân tại điểm gọi.

### 10.3. Có span nhưng loại không giống điều dự đoán

Ví dụ một method vừa được expose như Spring bean vừa có annotation event listener trong các cấu hình khác nhau. Cần xem **điểm vào thực tế đang bị intercept** và cách Spring Modulith phân loại `MethodInvocation`, thay vì kết luận từ tên method. Interface `ObservedModule` của Spring Modulith có khả năng nhận diện liệu một invocation có là **event listener invocation** hay không; framework dựa vào loại lời gọi này để tạo metadata.

Khi có custom aspect, proxy chaining hoặc nhiều nguồn instrumentation, trace còn có thể chứa nhiều span gần nhau. Đọc đúng span mang các key `module.*` trước khi diễn giải.

### 10.4. Filter theo `module.method` khiến dashboard tăng cardinality

`module.method` được API observation tài liệu hóa là **high-cardinality key**. Những truy vấn nhóm trực tiếp theo mọi method ở metric backend có thể tốn chi phí và không được exporter nào cũng chuyển thành metric labels. Ưu tiên `module.identifier` và `module.invocation-type` cho thống kê tổng hợp, còn `module.method` dùng khi điều tra chi tiết trong trace.

### 10.5. Nhầm invocation type với network span kind

Một span có `SpanKind.SERVER` hoặc `SpanKind.CLIENT` trong hệ thống tracing mô tả vai trò nhận/gửi request theo mô hình distributed tracing. `module.invocation-type` lại mô tả lời gọi **bean** hay **event listener** ở mức ứng dụng. Hai trục này không tương đương:

- Event listener có thể chạy hoàn toàn **trong cùng JVM** mà không có network server span.
- Bean invocation có thể gọi method nội bộ trong monolith, không phải HTTP client call.
- Một event được đưa qua message broker có thể tạo messaging spans riêng, trong khi module entry span vẫn là event listener tại điểm xử lý.

## 11. Sử dụng invocation type để kiểm chứng kiến trúc khi vận hành

Hãy ghép ba lớp thông tin:

1. **Module graph / tài liệu module:** Quan hệ phụ thuộc nào tồn tại, API nào được công khai?
2. **Module entry spans:** Những điểm vào module nào thực sự được quan sát, invocation type là gì và mất bao lâu?
3. **Dữ liệu nghiệp vụ và vận hành:** Trạng thái đơn, reservation, payment, event publication registry, retries và lỗi ở storage/backend?

Ví dụ nhóm chủ trương rằng `orders` chỉ nên giao tiếp với `payments` qua sự kiện. Có thể:

- Kiểm tra module graph hoặc test kiến trúc để xem dependency trực tiếp nào tồn tại và có hợp lệ không.
- Quan sát trace để tìm span `payments` mang `module.invocation-type=bean` trong các kịch bản đang chạy.
- Nếu tìm thấy, điều tra caller và đoạn code tương ứng; có thể luồng mới đã thêm API bean ngoài dự kiến.
- Nếu không tìm thấy, **chưa được khẳng định tuyệt đối** không hề có lời gọi bean nào: trace được lấy mẫu hoặc kịch bản chưa bao phủ.

Tại đây, invocation type cung cấp **bằng chứng runtime** bổ sung cho các quy tắc kiến trúc tĩnh. Nó không thay thế kiểm thử kiến trúc (`ApplicationModules.verify()`), cũng không thay thế bất biến nghiệp vụ và test integration.

### Ma trận kiểm chứng

| Mục tiêu | Phương tiện chính | Vai trò của invocation type |
| --- | --- | --- |
| Cấm `orders` import class nội bộ của `payments` | Kiểm tra dependency/module boundaries. | Không thể tự phát hiện mọi import tĩnh. |
| Kiểm tra một luồng đi vào `inventory` bằng API bean | Integration test + module entry span. | Cho biết loại điểm vào đã được quan sát là `bean`. |
| Kiểm tra `OrderPlaced` được listener của `payments` xử lý | Event/integration test + trạng thái handler. | Hỗ trợ xác nhận dấu vết điểm vào `event listener`. |
| Kiểm tra listener không chạy trùng | Idempotency, ràng buộc dữ liệu, test retry. | Span chỉ giúp khoanh vùng các lần xử lý đã thấy. |
| Chẩn đoán listener chậm | Tracing, event publication state, executor metrics. | Cho phép lọc nhóm listener spans. |
| Hiểu lý do trace bị tách | Context propagation, executor/messaging integration. | Phân biệt nhánh listener khi điều tra. |

## 12. Kịch bản điều tra từng bước

**Sự cố:** Khách hàng báo đơn hàng xử lý chậm. HTTP endpoint tạo đơn mất trung bình 120 ms, nhưng một số đơn cần hơn 30 giây mới bắt đầu chuẩn bị thanh toán. Nhóm đã bật Modulith observability.

Điều tra theo thứ tự:

1. **Lấy một orderId và thời điểm cụ thể.** Truy dữ liệu đơn và event publication để biết sự kiện được phát, listener được gọi lúc nào, có retry không.
2. **Tìm HTTP trace tạo đơn.** Xác nhận có span `inventory` loại `bean` và thời lượng của nó. Nếu tồn kho nhanh, tránh quy kết chậm tại API giữ hàng.
3. **Tìm span `payments` loại `event listener`.** Nếu span xuất hiện nhiều giây sau request, kiểm tra executor queue, transaction commit, lịch xử lý event và propagation.
4. **Đối chiếu event publication metrics.** Counter có thể cho xu hướng lượng event, nhưng không thay thế trạng thái publication/handler của đơn cụ thể.
5. **Phân biệt chậm trước và trong listener.** Một listener span bắt đầu muộn nhưng chạy chỉ 10 ms gợi ý điểm nghẽn ở hàng đợi, scheduling hoặc giao event. Một span listener dài 30 giây gợi ý logic bên trong hoặc dependency nó gọi đang chậm.
6. **Kiểm tra outcome nghiệp vụ.** Nếu listener báo hoàn tất nhưng payment chưa đúng, cần xem commit, idempotency và cổng thanh toán, không dừng ở trạng thái span.
7. **Bổ sung cảnh báo thích hợp.** Theo dõi độ trễ publication-to-processing, tần suất retry và các đơn kẹt trạng thái. Nhãn metric nên hữu hạn theo module, loại xử lý, loại lỗi; không dùng mỗi orderId làm metric tag.

Sơ đồ phân nhánh giúp xác định điểm nghi vấn:

~~~mermaid
flowchart TD
    A["Đơn bị xử lý chậm"] --> B{"Có module spans?"}
    B -->|"Không"| C["Kiểm tra instrumentation,\nproxy, sampling, exporter"]
    B -->|"Có"| D{"inventory bean span chậm?"}
    D -->|"Có"| E["Điều tra InventoryFacade\nvà dependency bên trong"]
    D -->|"Không"| F{"payments event listener span xuất hiện?"}
    F -->|"Không"| G["Kiểm tra event dispatch,\ntransaction, executor, propagation"]
    F -->|"Có"| H{"Span listener dài hay bắt đầu muộn?"}
    H -->|"Span dài"| I["Điều tra logic listener,\nDB hoặc external calls"]
    H -->|"Bắt đầu muộn"| J["Điều tra queue,\nscheduling, retry, commit"]
~~~

## 13. Checklist tự kiểm tra

Trước khi đưa dashboard theo invocation type vào sử dụng:

- [ ] Đã xác nhận phiên bản Spring Modulith và tên key từ tài liệu đúng release?
- [ ] Có `spring-modulith-observability-core` hoặc starter Insight trên runtime classpath?
- [ ] Có Micrometer tracing bridge/exporter/backend khi cần xem traces ngoài JVM?
- [ ] Đã chạy kịch bản **bean API call** và thấy `module.invocation-type` phù hợp?
- [ ] Đã chạy kịch bản **event listener** và thấy `module.invocation-type` phù hợp?
- [ ] Đã xác minh giá trị tag thực tế sau khi được exporter đưa vào backend?
- [ ] Đã phân biệt dependency types trên module graph với invocation type trên spans?
- [ ] Đã xem xét `@Async`, executor, `@TransactionalEventListener` và context propagation?
- [ ] Đã xác minh scope instrumentation gồm đúng API module và listener mong muốn?
- [ ] Đã hiểu giới hạn sampling, retries và việc các span không đại diện cho giao dịch duy nhất?
- [ ] Đã tránh metric labels có cardinality lớn hoặc chứa dữ liệu cá nhân?
- [ ] Đã có phép kiểm tra nghiệp vụ riêng cho transaction, idempotency và trạng thái sau commit?

## 14. Bài tập luyện tập

1. **Phân loại:** Một trace có `module.identifier=inventory`, `module.method=InventoryFacade.reserve`, `module.invocation-type=bean`. Hãy nêu những điều có thể và không thể kết luận từ span này.
2. **Sự kiện:** Một module `payments` nhận `OrderPlaced` qua `@EventListener`. Vì sao invocation type là `event listener` dù method xử lý vẫn nằm trên một Spring bean?
3. **Đồ thị:** JSON Module Actuator cho thấy `payments → orders` với dependency type `EVENT_LISTENER`. Điều đó có đồng nghĩa trace của mọi request đều có một span `event listener` không? Vì sao?
4. **Bất đồng bộ:** Listener dùng `@Async`. HTTP trace kết thúc trước khi listener chạy, và span listener xuất hiện ở trace khác. Hãy nêu ít nhất ba kiểm tra về executor, context propagation, sampling và correlation.
5. **Tối ưu:** Bạn thấy các span `bean` của `inventory` ngắn nhưng span `event listener` của `payments` chậm. Các vị trí nào cần điều tra trước khi sửa code?
6. **Thiết kế dashboard:** Hãy đề xuất hai nhóm phân loại thấp cardinality theo `module.identifier` và `module.invocation-type`, giải thích vì sao không dùng `orderId` làm metric label.
7. **Đúng đắn nghiệp vụ:** Hai span listener cùng eventId đều báo OK. Nêu cách xác minh một payment chỉ được ghi một lần sau retry.
8. **Kiểm tra phiên bản:** Nâng Spring Modulith khiến dữ liệu backend hiển thị invocation type khác cách filter cũ. Các bằng chứng và bước chuyển đổi nào cần trước khi sửa dashboard?

## 15. Ghi nhớ

**`module.invocation-type` là một thuộc tính của Module Entry Span mô tả cách lời gọi vào application module được nhận diện: bean invocation hay event listener invocation.** Nó hữu ích khi:

- phân loại các điểm vào theo kiểu tương tác;
- điều tra độ trễ trong lời gọi API module so với listener;
- nhận diện ranh giới cần kiểm tra context propagation;
- đối chiếu runtime spans với tài liệu/module graph để phát hiện dấu hiệu kiến trúc thay đổi.

Tuy nhiên, một loại invocation **không** xác định HTTP protocol, transaction lifecycle, bảo đảm giao event, độ bền dữ liệu hoặc tính đúng đắn nghiệp vụ. Cần kết hợp module graph, Actuator, metrics, tracing, kiểm thử kiến trúc, idempotency và đối soát để kiểm chứng ứng dụng Spring Boot khi vận hành.

### Tài liệu tham khảo

- [Spring Modulith 2.2 — Production-ready Features: Observing Application Modules và Module Entry Span](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html).
- [Spring Modulith — Production-ready Features (theo phiên bản tài liệu hiện hành)](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith Javadoc — ModulithObservations.LowKeys](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.LowKeys.html).
- [Spring Modulith Javadoc — ModulithObservations.HighKeys](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.HighKeys.html).
- [Spring Modulith Javadoc — ObservedModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ObservedModule.html).
- [Spring Modulith Javadoc — ModulithContext](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithContext.html).
