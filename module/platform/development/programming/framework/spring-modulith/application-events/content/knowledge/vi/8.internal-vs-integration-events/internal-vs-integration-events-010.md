# Chiến lược chuyển tiếp giữa internal event và integration event

## 1. Bối cảnh: khi ranh giới giao tiếp thay đổi

Một ứng dụng **Spring Modulith** có thể bắt đầu dưới dạng modular monolith: các module nghiệp vụ chạy chung tiến trình, giao tiếp qua Spring application events để giảm phụ thuộc trực tiếp. Ví dụ, module **Orders** phát `OrderPaid`; module **Notifications** lên lịch gửi xác nhận, còn **Reporting** cập nhật báo cáo. Cả ba module cùng chạy trong một ứng dụng Spring.

Vài tháng sau, doanh nghiệp tích hợp CRM, hệ thống kế toán hoặc một dịch vụ giao hàng độc lập. Những hệ thống này cũng cần biết sự kiện đơn hàng đã thanh toán. **Internal event** trước đây phục vụ giao tiếp giữa các module nay trở thành nguồn thông tin để phát **integration event** ra ngoài tiến trình.

Điểm khó không nằm ở lệnh gửi một thông điệp tới broker. Khi vượt qua ranh giới triển khai, hệ thống phải thiết kế thêm hợp đồng dữ liệu ổn định, tính tương thích phiên bản, độ bền giao tin, retry, idempotency, quan sát, đồng bộ dữ liệu ban đầu và khả năng chuyển đổi không gián đoạn.

Trong module học **SPRING_MODULITH_APPLICATION_EVENTS**, “chiến lược chuyển tiếp” là cách **di chuyển có kiểm soát từ giao tiếp nội bộ sang tích hợp bên ngoài**, hoặc thay đổi tuyến sự kiện, đồng thời giữ ranh giới và quy tắc nghiệp vụ của từng module.

### Kết quả học tập

Sau bài này, bạn có thể:

- Quyết định khi nào nên giữ internal event và khi nào cần integration event.
- Thiết kế lớp chuyển tiếp từ sự thật nghiệp vụ nội bộ sang thông điệp tích hợp ổn định.
- So sánh event externalization của Spring Modulith, publication registry và transactional outbox.
- Lập kế hoạch migration theo từng giai đoạn với consumer chạy song song và điểm cắt chuyển rõ ràng.
- Xử lý duplicate, event đến muộn, ordering, replay, snapshot và rollback.
- Đặt tiêu chí đo lường và kiểm thử trước khi đưa integration event vào vận hành thật.

## 2. Hiện trạng và đích đến: hai ranh giới khác nhau

### 2.1. Luồng chỉ có internal event

~~~mermaid
flowchart LR
  subgraph JVM["Một ứng dụng Spring Modulith"]
    O["Orders"] -->|"OrderPaid"| E(("Spring application events"))
    E --> N["Notifications"]
    E --> R["Reporting"]
  end
~~~

`ApplicationEventPublisher` chuyển sự kiện trong Spring application context. Module phát không biết các listener cụ thể. Với `@ApplicationModuleListener`, module nhận có thể xử lý sau commit, bất đồng bộ, trong transaction riêng.

Tuy nhiên, chỉ gọi `publishEvent(...)` **không tự tạo thông điệp trên Kafka, RabbitMQ hoặc HTTP webhook**. Sự kiện chưa rời ranh giới triển khai.

### 2.2. Đích đến có consumer bên ngoài

~~~mermaid
flowchart LR
  subgraph JVM["Ứng dụng Spring Modulith"]
    O["Orders"] --> E(("Internal OrderPaid"))
    E --> N["Notifications"]
    E --> X["Externalization adapter"]
  end
  X -->|"OrderPaidV1"| B[("Broker / integration channel")]
  B --> C["CRM"]
  B --> A["Accounting"]
~~~

Tại lớp chuyển tiếp:

1. Orders tiếp tục sở hữu sự thật **“đơn đã thanh toán”**.
2. Notifications có thể tiếp tục dùng internal event, không bắt buộc biết broker.
3. Adapter chỉ chọn những sự kiện cần đưa ra ngoài, tạo integration contract và gửi qua transport thích hợp.
4. CRM và Accounting chỉ phụ thuộc vào integration contract, không import entity hoặc service Java nội bộ.

**Nguyên tắc:** thay đổi kênh phân phối không được âm thầm thay đổi định nghĩa nghiệp vụ. Một `OrderPaid` chỉ phát khi điều kiện “paid” của Orders thực sự được đáp ứng, bất kể hệ thống có bao nhiêu consumer.

## 3. Khi nào cần chuyển tiếp?

Không phải event nào cũng nên trở thành integration event.

| Nhu cầu | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Notifications cùng ứng dụng cần phản ứng sau commit | Giữ internal event với listener | Không cần hệ thống vận chuyển bên ngoài |
| CRM ngoài tiến trình cần thông báo đơn đã thanh toán | Externalize event chọn lọc | Phải vượt deployment boundary |
| Chuyển module Fulfillment thành dịch vụ riêng | Chuẩn bị integration contract và cutover consumer | Ranh giới triển khai thay đổi |
| Báo cáo cần dựng lại toàn bộ dữ liệu lịch sử | Snapshot + catch-up hoặc luồng CDC/event store thích hợp | Registry của application event không mặc nhiên là kho lưu mọi event lịch sử |
| Một invariant cần được kiểm tra ngay trong transaction Orders | Giữ lời gọi đồng bộ/public API hoặc thiết kế workflow có kiểm soát | Event sau commit không trả kết quả bắt buộc tức thời |
| Dữ liệu kỹ thuật nội bộ như invalidation của cache local | Giữ internal nếu không có consumer ngoài | Tránh phát tán chi tiết triển khai |

Một câu hỏi quan trọng trước khi chuyển là: **consumer ngoài cần biết sự thật đã xảy ra hay cần điều khiển bước hiện tại?** Nếu cần yêu cầu “hãy giữ tồn kho và trả kết quả”, đó là command/workflow, không nên chỉ đổi tên thành một integration event rồi mong có kết quả đồng bộ.

### 3.1. Điều kiện bắt đầu migration

Nên có đủ bốn thông tin:

- **Business fact:** event nào thật sự có ý nghĩa với hệ thống ngoài?
- **Owner:** module nào chịu trách nhiệm xác nhận và công bố sự thật?
- **Tính nhất quán:** consumer có thể chậm bao lâu; việc xử lý trễ có ảnh hưởng quyết định giao dịch chính không?
- **Kỳ vọng vận hành:** cần giao lại khi lỗi, giữ thứ tự theo aggregate, bảo lưu dữ liệu lịch sử, quan sát và khôi phục tới mức nào?

Thiếu những câu trả lời này, việc thêm broker có thể chỉ tạo thêm một lớp không chắc chắn.

## 4. Ba chiến lược chuyển tiếp thường gặp

### Chiến lược A — Giữ internal event, externalize có chọn lọc

Orders tiếp tục phát `OrderPaid` qua Spring. Spring Modulith event externalization chọn các sự kiện cần thiết, định tuyến và đưa chúng tới broker. Listener nội bộ giữ nguyên.

**Phù hợp khi:** ứng dụng vẫn là modular monolith, chỉ có một số consumer ngoài cần dữ liệu.

**Lợi ích:** thay đổi ít ở code publisher, giữ cấu trúc module và các listener sẵn có.

**Đánh đổi:** cần quản lý backend publication, mapping schema, cấu hình broker và các thuộc tính độ bền cụ thể của cơ chế externalization đang dùng.

### Chiến lược B — Dùng contract tích hợp riêng và adapter

Giữ `OrderPaid` là sự kiện nội bộ, rồi ánh xạ sang `OrderPaidV1` hoặc envelope JSON dành cho hệ thống ngoài.

~~~text
Orders: OrderPaid (Java contract nội bộ)
        |
        v
Integration adapter + mapper
        |
        v
orders.paid.v1 (schema và topic công khai)
~~~

**Phù hợp khi:** payload bên ngoài có vòng đời dài, consumer triển khai độc lập hoặc cần kiểm soát dữ liệu nhạy cảm.

**Lợi ích:** nội bộ có thể tiến hóa mà không trực tiếp làm vỡ public integration schema; dễ thêm version, routing metadata và quản trị hợp đồng.

**Đánh đổi:** thêm mapper và test contract; phải kiểm soát để cùng một sự thật không bị biến đổi ý nghĩa giữa hai loại event.

### Chiến lược C — Transactional outbox hoặc cơ chế chuyển giao bền vững chuyên dụng

Module ghi state nghiệp vụ **và bản ghi thông điệp/outbox trong cùng transaction database**. Một relay độc lập đọc outbox và gửi tới broker, sau đó đánh dấu đã gửi. Consumer xử lý thông điệp với idempotency.

**Phù hợp khi:** yêu cầu độ tin cậy, throughput, recovery, ordering hay nhiều instance phức tạp hơn; cần các tính năng outbox chuyên dụng.

**Lợi ích:** không phụ thuộc vào gọi broker trực tiếp trong transaction nghiệp vụ; có một bản ghi bền vững để khôi phục sau crash.

**Đánh đổi:** thêm bảng, relay/CDC hoặc giải pháp outbox, cơ chế retry, dọn dẹp, vận hành và duplicate handling.

| Tiêu chí | Externalize bằng Spring Modulith | Contract riêng + adapter | Outbox chuyên dụng |
| --- | --- | --- | --- |
| Duy trì publisher `ApplicationEventPublisher` | Có | Có thể có | Có thể có |
| Tách schema ngoài khỏi Java nội bộ | Có thể cấu hình mapping | Chủ đích của giải pháp | Thường kết hợp mapper |
| Cần broker / hạ tầng ngoài | Có | Có nếu phải giao liên tiến trình | Có nếu phải giao liên tiến trình |
| Theo dõi giao event | Qua registry khi cấu hình phù hợp | Phụ thuộc cơ chế adapter | Qua outbox/relay theo triển khai |
| Khả năng replay lịch sử tùy ý | Không mặc nhiên | Không mặc nhiên | Không mặc nhiên; phụ thuộc chính sách lưu |
| Chi phí vận hành | Tương đối gọn | Thêm quản trị contract | Thêm relay/CDC và dữ liệu outbox |

Hai cách đầu có thể **kết hợp**: dùng Spring Modulith externalization nhưng mapping event nội bộ thành payload integration riêng. Outbox có thể được dùng cùng chiến lược ánh xạ đó.

## 5. Bắt đầu bằng kiểm kê và xác định ranh giới contract

Đừng bắt đầu migration bằng cách đánh dấu externalize mọi event. Hãy lập bảng các sự kiện hiện có:

| Event hiện tại | Owner | Consumer nội bộ | Consumer mới | Nên externalize? |
| --- | --- | --- | --- | --- |
| `OrderPaid` | Orders | Notifications, Reporting | CRM, Accounting | Có, nếu contract đủ rõ |
| `OrderDraftSaved` | Orders | Không có | Không có | Không |
| `InventoryReserved` | Inventory | Fulfillment | Warehouse system | Có thể, nếu ngoài hệ thống cần mốc này |
| `EmailJobRetried` | Notifications | Monitoring | CRM | Thường không, vì là chi tiết kỹ thuật |
| `OrderCancelled` | Orders | Fulfillment, Loyalty | CRM | Có thể; cần định nghĩa mốc hủy và ordering |

Với mỗi event được chọn, ghi lại tối thiểu:

1. Điều kiện phát và điều kiện không được phát.
2. Mối liên hệ với transaction và trạng thái đã commit.
3. Khóa aggregate, định danh sự kiện, thời điểm phát sinh, phiên bản.
4. Người nhận, hành động họ làm, có cần dữ liệu lịch sử hay chỉ tương lai.
5. Dữ liệu nào không được đưa ra ngoài hệ thống.
6. Yêu cầu độ trễ, khôi phục, thứ tự và khả năng chấp nhận duplicate.

Sau đó, quyết định **đâu là hợp đồng nội bộ** và **đâu là hợp đồng integration**. Hợp đồng tích hợp cần tồn tại ngay cả khi entity, package và implementation của Orders thay đổi.

## 6. Thiết kế hai contract không làm rò rỉ domain model

### 6.1. Internal event

~~~java
package com.acme.shop.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        BigDecimal paidAmount,
        String currency,
        long orderVersion
) {}
~~~

Type này do Orders sở hữu. Các field mô tả **số tiền thanh toán tại thời điểm phát event**, không phải số dư hoặc trạng thái thanh toán hiện tại. `orderVersion` là phiên bản aggregate có quy tắc tăng rõ ràng; nó chỉ hữu ích cho ordering nếu nguồn dữ liệu quản lý nó nhất quán.

### 6.2. Integration event v1

Một contract truyền qua broker có thể dùng JSON:

~~~json
{
  "eventId": "d1985b42-1da1-4da9-afcf-a75fd66bacdd",
  "eventType": "orders.paid",
  "schemaVersion": 1,
  "orderId": "68f4da8e-701b-4f8a-84d4-afbd75a468c2",
  "orderVersion": 7,
  "occurredAt": "2026-11-25T08:00:00Z",
  "amount": "125000.00",
  "currency": "VND"
}
~~~

Đây là **schema minh họa**, không phải JSON mà Spring Modulith tự tạo mặc định. Ví dụ serialize `amount` thành chuỗi decimal để giảm khả năng sai khác biểu diễn số giữa các ngôn ngữ; quy ước đơn vị, scale, rounding và currency phải thống nhất trong hợp đồng thực tế.

Hợp đồng cần tài liệu hóa:

| Thuộc tính | Vai trò |
| --- | --- |
| `eventId` | Chống xử lý lặp theo từng sự kiện |
| `eventType` | Loại sự thật nghiệp vụ, độc lập class Java |
| `schemaVersion` | Kiểm soát thay đổi payload integration |
| `orderId` | Khóa nghiệp vụ/aggregate để định tuyến hoặc partition |
| `orderVersion` | Giúp consumer phát hiện event cũ nếu quy tắc version đáng tin cậy |
| `occurredAt` | Truy vết thời điểm nghiệp vụ; không đảm bảo thứ tự nhận |
| `amount`, `currency` | Snapshot dữ liệu được phép công bố |

**Không gửi trực tiếp JPA entity**, session, lazy association, private token hoặc các thông tin nhạy cảm không cần thiết ra broker. Một consumer ở ngoài ứng dụng không nên bị buộc hiểu cấu trúc bảng và lớp Java nội bộ.

### 6.3. Mapping có kiểm soát

Có thể tạo một payload integration tách khỏi type nội bộ:

~~~java
package com.acme.shop.integration;

import com.acme.shop.orders.OrderPaid;
import java.util.UUID;

public record OrderPaidMessageV1(
        String eventId,
        String orderId,
        long orderVersion,
        String occurredAt,
        String amount,
        String currency,
        int schemaVersion
) {
    public static OrderPaidMessageV1 from(OrderPaid source) {
        return new OrderPaidMessageV1(
                source.eventId().toString(),
                source.orderId().toString(),
                source.orderVersion(),
                source.occurredAt().toString(),
                source.paidAmount().toPlainString(),
                source.currency(),
                1
        );
    }
}
~~~

Bài này dùng một mapper Java đơn giản để minh họa biến đổi dữ liệu. Khi dùng Spring Modulith event externalization thực tế, cần cấu hình mapping để cơ chế externalization gửi `OrderPaidMessageV1` thay vì tự động gửi nguyên `OrderPaid`.

Như vậy, Orders chỉ định nghĩa sự thật nghiệp vụ; adapter chịu trách nhiệm public schema và transport.

## 7. Spring Modulith hỗ trợ externalize event như thế nào?

Spring Modulith cung cấp cơ chế **event externalization** để chọn các Spring application event và chuyển chúng qua hạ tầng messaging được tích hợp. Quy trình tổng quát gồm ba bước:

1. **Select:** xác định những event type nào được đưa ra ngoài.
2. **Map:** tùy chọn biến đổi payload, bổ sung header hoặc xây contract riêng.
3. **Route:** quyết định topic, exchange, channel và routing key theo transport.

Ví dụ đơn giản khi chấp nhận serialize trực tiếp event theo cơ chế mặc định:

~~~java
package com.acme.shop.orders;

import java.time.Instant;
import java.util.UUID;
import org.springframework.modulith.events.Externalized;

@Externalized("orders.confirmed.v1")
public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

Để ví dụ này thực sự phát ra broker, ứng dụng còn cần dependency Spring Modulith theo transport thích hợp, backend publication cần thiết và cấu hình kết nối. Annotation chỉ là **quyết định chọn event/định tuyến**, không tự tạo Kafka hoặc tự bảo đảm mọi thông điệp đã được gửi bền vững.

Nếu schema ngoài phải khác class nội bộ, dùng cấu hình `EventExternalizationConfiguration`. Ví dụ sơ đồ cấu hình Java sau minh họa API builder của Spring Modulith:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.events.EventExternalizationConfiguration;

@Configuration
class IntegrationEventConfiguration {

    @Bean
    EventExternalizationConfiguration externalizationConfiguration() {
        return EventExternalizationConfiguration.externalizing()
                .select(EventExternalizationConfiguration.annotatedAsExternalized())
                .mapping(OrderPaid.class, OrderPaidMessageV1::from)
                .build();
    }
}
~~~

Trong thiết kế kết hợp, event `OrderPaid` cần được chọn để externalize, ví dụ qua `@Externalized` hoặc phương thức selection khác phù hợp version; code trên chỉ minh họa cấu hình mapping. Cần đảm bảo bộ chọn, định tuyến, message serializer và bean mapper thực tế có đúng theo phiên bản Spring Modulith ứng dụng sử dụng.

Với Kafka, AMQP, JMS hoặc Spring Messaging, Spring Modulith có các module tích hợp khác nhau. Topic/routing key và serialization cần được kiểm tra theo từng transport. Nếu ordering theo `orderId` quan trọng, đừng bỏ qua chiến lược message key và partition, nhưng **message key không tự giải quyết mọi tình huống out-of-order khi retry hoặc nhiều producer**.

### Lưu ý về phiên bản Spring Modulith

Tài liệu Spring Modulith 2.2 mô tả native externalization dựa trên asynchronous transactional event listener và Event Publication Registry. Tài liệu cũng phân biệt khả năng này với **outbox chuyên dụng**; từ Spring Modulith 2.1 có thêm lựa chọn tích hợp outbox thông qua Namastack hoặc JobRunr trong các tình huống phù hợp. Cấu hình, dependency và khả năng vận hành khác nhau theo release, nên cần kiểm tra tài liệu đúng phiên bản ứng dụng đang dùng.

## 8. Độ tin cậy: từ commit nội bộ tới broker acknowledgement

Một thách thức chuyển tiếp là khoảng trống giữa “database Orders đã commit” và “broker đã nhận thông điệp”.

### 8.1. Khi chỉ publish event trong bộ nhớ

~~~text
TX Orders commit -> JVM crash -> external broker không nhận event
~~~

Nếu không có publication log/outbox bền vững, event có thể bị mất khỏi luồng tích hợp khi ứng dụng tắt ở điểm xấu.

### 8.2. Khi dùng Event Publication Registry

Spring Modulith **Event Publication Registry** lưu publication ứng với transactional listeners dưới sự quản lý của cơ chế registry được cấu hình. Việc ghi nhận publication gắn với transaction nghiệp vụ; publication chưa hoàn thành có thể được quan sát và khôi phục qua cơ chế resubmission phù hợp.

~~~mermaid
sequenceDiagram
  autonumber
  participant O as Orders
  participant DB as Database
  participant P as Publication Registry
  participant X as Externalization listener
  participant B as Broker
  O->>DB: Lưu Order = PAID
  O->>P: Ghi nhận publication cần xử lý
  O->>DB: Commit transaction
  P-->>X: Xử lý event sau commit
  X->>B: Gửi integration message
  alt Broker xác nhận gửi thành công
    X-->>P: Đánh dấu completed
  else Lỗi/timeout
    X-->>P: Để publication ở trạng thái chưa hoàn thành hoặc failed
  end
~~~

Registry không bảo đảm consumer ngoài broker đã hoàn thành nghiệp vụ, cũng không mang nghĩa exactly-once end-to-end. Nếu broker đã nhận nhưng publisher chưa nhận ack hoặc chưa ghi nhận completed, một lần gửi lại có thể tạo thông điệp trùng.

**Phân biệt rõ các trạng thái thành công:**

- Orders commit thành công.
- Publication được ghi nhận bền vững theo cấu hình.
- Broker chấp nhận thông điệp.
- Consumer nhận thông điệp.
- Consumer commit thay đổi state.
- Side effect ngoài DB (email/API khác) hoàn tất.

Không được đồng nhất các mốc này thành một trạng thái `SUCCESS` duy nhất.

### 8.3. Khi nào cần transactional outbox?

Outbox ghi **event gửi ra ngoài** vào cùng transaction với state nghiệp vụ; relay riêng chịu trách nhiệm giao cho broker. Đây là pattern hữu ích khi cần kiểm soát queueing, throughput, backpressure, replay hoặc multi-instance sâu hơn.

Tuy nhiên, outbox vẫn có thể gửi trùng khi relay crash sau broker ack nhưng trước cập nhật trạng thái outbox. Consumer vẫn cần idempotency. Đồng thời, không nên xem Event Publication Registry và outbox chuyên dụng là hai tên khác nhau cho một triển khai hoàn toàn giống nhau: cơ chế và tính năng của chúng khác theo thư viện/configuration.

## 9. Lộ trình chuyển tiếp theo từng giai đoạn

Nên chia migration thành các bước nhỏ có điều kiện xác minh cụ thể.

| Giai đoạn | Công việc | Tiêu chí chuyển giai đoạn |
| --- | --- | --- |
| **0. Khảo sát** | Kiểm kê event, owner, consumer, transaction, SLA và dữ liệu nhạy cảm | Có bảng contract và trách nhiệm rõ |
| **1. Ổn định internal event** | Tên, payload, ID, trạng thái, test publisher/listener | Publisher chỉ phát khi sự thật đúng; không rò rỉ entity |
| **2. Định nghĩa external contract** | Schema v1, routing, partition key, version, ownership, policy | Consumer xác nhận hiểu contract |
| **3. Thêm lớp externalization** | Tạo adapter và mapping; cấu hình broker, registry/outbox | Có kiểm thử message, transaction, crash và retry |
| **4. Chạy shadow** | Consumer mới nhận nhưng không tạo side effect thật | Theo dõi chênh lệch dữ liệu và lag đạt ngưỡng |
| **5. Chuyển dần consumer** | Chọn owner thực thi duy nhất cho mỗi side effect; bật xử lý thật có kiểm soát | Không double processing; dữ liệu hội tụ |
| **6. Vận hành ổn định** | Quan sát, alert, retry, reconciliation, runbook | Các chỉ số ổn định trong cửa sổ đánh giá |
| **7. Dọn tuyến cũ** | Gỡ listener/adapter không còn cần thiết theo kế hoạch | Đã vượt hạn rollback và không còn consumer phụ thuộc |

~~~mermaid
flowchart LR
  A["Ổn định nội bộ"] --> B["Tách integration contract"]
  B --> C["Externalization có lưu bền vững"]
  C --> D["Shadow + đối soát"]
  D --> E["Cutover có kiểm soát"]
  E --> F["Quan sát + dọn tuyến cũ"]
~~~

Không phải dự án nào cũng cần đủ bảy bước; quy mô migration phụ thuộc rủi ro. Nhưng thứ tự **định nghĩa contract -> kiểm tra giao -> xác minh consumer -> cutover** giúp hạn chế việc broker chạy được trong khi nghiệp vụ bị xử lý sai.

## 10. Chạy song song an toàn: shadow, dual run và cutover

Khi chuyển một chức năng từ listener nội bộ sang consumer bên ngoài, giai đoạn nguy hiểm nhất thường là lúc **hai bên đều có khả năng tạo cùng side effect**.

Ví dụ:

- Listener cũ trong Notifications tạo email job sau `OrderPaid`.
- Dịch vụ Notifications mới nhận `orders.paid.v1` từ Kafka và cũng tạo email job.

Nếu bật cả hai để gửi email thật, một lần thanh toán có thể tạo **hai email**. Idempotency theo event ID giữa hai database không nhất thiết ngăn được điều này nếu mỗi hệ thống có kho dedup riêng.

### 10.1. Shadow consumer

Trong giai đoạn đầu, dịch vụ mới:

- Nhận và parse integration message.
- Kiểm tra schema, ordering và khả năng xử lý.
- Ghi kết quả dự kiến vào bảng/test sink hoặc metrics.
- **Không gửi email, không ghi state có tác động thật và không gọi API thanh toán.**

So sánh event count, business key, các trạng thái dự kiến, latency và error rate giữa xử lý cũ/mới.

### 10.2. Chọn một chủ sở hữu side effect

Khi kết quả shadow đã đủ tin cậy, thực hiện cutover theo feature flag hoặc theo nhóm khách hàng/tenant nếu architecture cho phép. Với mỗi `orderId` hoặc nhóm được chọn, chỉ **một** tuyến có quyền tạo side effect thật.

Một chiến lược đơn giản:

~~~text
phase=SHADOW       -> tuyến cũ thực thi; tuyến mới chỉ quan sát
phase=CANARY       -> nhóm A: tuyến mới thực thi; nhóm B: tuyến cũ
phase=NEW_PRIMARY  -> tuyến mới thực thi toàn bộ; tuyến cũ chỉ quan sát/tắt
phase=RETIRED      -> bỏ tuyến cũ sau thời gian an toàn
~~~

Việc định tuyến phải ổn định và có thể kiểm chứng khi restart/deploy. Trong hệ thống nhiều instance, flag cục bộ từng JVM có thể khiến hai instance bất đồng quyết định; cần nguồn điều khiển thống nhất hoặc cơ chế phân chia rõ.

### 10.3. Dual publish khác dual consume

**Dual publish** là gửi cùng sự thật qua hai kênh; **dual consume** là hai consumer cùng nhận. Cả hai có thể dùng để chuyển đổi hạ tầng, nhưng sẽ tăng nguy cơ duplicate, thứ tự lệch và xác định nguồn sự thật.

Nếu cần xuất hai schema hoặc hai topic trong giai đoạn tương thích, hãy đảm bảo chúng mang cùng `eventId` hoặc có mapping/correlation ổn định, đồng thời công bố rõ đâu là nguồn ưu tiên. Không để consumer ghi nghiệp vụ qua cả hai kênh mà không có cơ chế dedup xuyên kênh.

## 11. Đồng bộ dữ liệu ban đầu và bắt kịp sự kiện mới

Một consumer mới thường không chỉ cần event phát **từ thời điểm bật**. CRM có thể cần toàn bộ đơn hàng đã thanh toán từ trước.

**Publication Registry không mặc nhiên là event store đầy đủ để replay tùy ý cho consumer ra đời sau.** Registry theo dõi các publication của listener đã có tại thời điểm phát; muốn đồng bộ dữ liệu lịch sử cần một luồng backfill riêng hoặc nguồn dữ liệu lịch sử phù hợp.

Có ba cách chính:

| Cách | Phù hợp | Điểm chú ý |
| --- | --- | --- |
| **Snapshot + catch-up** | Consumer cần trạng thái hiện tại rồi theo kịp event mới | Phải có watermark/cursor tránh mất khoảng giao nhau |
| **Replay từ event store/broker có retention** | Hệ thống thực sự có lịch sử sự kiện đầy đủ và tương thích | Quản lý version, ordering, retention và side effect |
| **CDC/outbox feed có điểm bắt đầu rõ** | Muốn stream theo thay đổi DB hoặc bản ghi outbox | Phải hiểu thứ tự commit, transaction và cấu trúc dữ liệu |

### 11.1. Snapshot + catch-up

Ví dụ quy trình an toàn hơn một lần “dump dữ liệu rồi subscribe”:

1. Đăng ký consumer vào stream hoặc xác định một offset/cursor nguồn nhất quán.
2. Chụp snapshot trạng thái nghiệp vụ với watermark cụ thể.
3. Tải snapshot vào read model mới.
4. Tiêu thụ các event từ cursor phù hợp, deduplicate theo `eventId`/business key và áp dụng điều kiện version.
5. Khi độ trễ về ngưỡng chấp nhận được, bật consumer mới phục vụ request thật.

Chi tiết vị trí snapshot và offset phải được thiết kế theo cơ chế database/broker đang dùng. Nếu snapshot không nhất quán với cursor, có thể có khoảng **mất event** hoặc **áp dụng event hai lần** tại ranh giới.

### 11.2. Hai dạng consumer khác nhau

- **Read model/analytics:** có thể xây lại từ snapshot và stream nếu đủ dữ liệu; rollback/cutover tương đối dễ.
- **Side-effect consumer:** gửi email, trả tiền, tạo shipment. Không được replay lịch sử một cách vô điều kiện vì có thể gửi lại email cũ hoặc tạo shipment đã tồn tại. Cần chế độ dry-run, idempotency key và quy tắc “chỉ xử lý mới từ mốc cutover”.

Thiết kế backfill phải dựa trên **mục đích tiêu thụ**, không dùng một chiến lược replay chung cho tất cả consumer.

## 12. Ordering, duplicate và eventual consistency sau khi vượt tiến trình

Khi listener chạy bất đồng bộ hoặc thông điệp qua broker, không thể giả định thứ tự phát bằng thứ tự xử lý ở mọi consumer.

~~~text
Orders:
  V7: OrderPaid
  V8: OrderRefunded

Consumer nhận:
  V8: OrderRefunded
  V7: OrderPaid  (bị retry, tới muộn)
~~~

Nếu consumer áp dụng mọi event theo thứ tự nhận mà không kiểm tra version/state, dữ liệu có thể chuyển ngược thành “đang thanh toán” sau khi đã hoàn tiền.

Các biện pháp:

- **Aggregate version:** truyền một `orderVersion` monotonic theo `orderId`, chỉ áp dụng event có phiên bản phù hợp.
- **Partition key:** cố gắng định tuyến event của cùng aggregate tới cùng partition khi transport hỗ trợ, để giữ một phần ordering.
- **State-machine guard:** không cho consumer chuyển trạng thái terminal về state cũ.
- **Gap detection:** phát hiện version nhảy cóc; có thể chờ event thiếu hoặc đồng bộ trạng thái hiện hành theo API hợp lệ.
- **Deduplication:** lưu `eventId` đã xử lý cùng kết quả side effect trong transaction của consumer.

Một lần retry có thể xuất hiện sau khi event mới đã được áp dụng, nên **partition key không thay thế version guard**. Event `occurredAt` cũng không nên được xem như đồng hồ thứ tự tuyệt đối.

### 12.1. At-least-once và exactly-once

Một hệ thống đáng tin cậy thường phải chấp nhận thông điệp có thể được giao **ít nhất một lần** trong những cấu hình lưu bền và retry phù hợp. Điều này đồng nghĩa consumer **có thể nhận lặp**.

Kể cả broker có một số khả năng exactly-once cho thao tác trong phạm vi riêng, toàn bộ workflow từ database Orders -> broker -> database CRM -> email/API ngoài vẫn không tự trở thành exactly-once. Với side effect, nên dùng idempotency, transaction consumer, đối soát và cơ chế bù trừ khi cần.

## 13. Kế hoạch rollback và khả năng đảo chiều migration

Một chiến lược chuyển tiếp đáng tin cậy phải trả lời từ trước: **khi tuyến mới lỗi, quay về trạng thái an toàn bằng cách nào?**

| Sự cố | Hành động đề xuất | Điều cần tránh |
| --- | --- | --- |
| Broker tạm thời không sẵn sàng | Giữ publication/outbox chưa hoàn thành, retry có kiểm soát và báo động | Trả thành công “đã gửi broker” khi chưa có xác nhận |
| Consumer mới xử lý sai schema | Dừng side effect tuyến mới, giữ dữ liệu để phân tích, sửa mapper/consumer | Retry vô hạn thông điệp sai schema |
| Duplicate tạo nguy cơ email hai lần | Duy trì một owner thực thi và khóa idempotency | Bật cùng lúc cả hai tuyến gửi thật |
| Consumer mới có lag vượt SLA | Dừng cutover thêm, mở rộng capacity/kiểm tra backpressure | Xóa pending event để giảm lag biểu đồ |
| Chênh lệch dữ liệu read model | Chạy reconciliation, snapshot lại phạm vi lỗi hoặc replay an toàn | Coi việc nhận đủ message đồng nghĩa state đúng |
| Rollback sang consumer cũ | Chuyển owner, khôi phục subscription/checkpoint phù hợp | Bật tuyến cũ mà chưa đối soát side effect đã làm bởi tuyến mới |

### 13.1. Rollback code khác rollback nghiệp vụ

Nếu đã gửi email, tạo shipment hoặc thanh toán ở hệ thống ngoài, việc deploy lại version cũ **không hoàn tác** các side effect đó. Hệ thống có thể cần compensation, correction event hoặc quy trình thủ công theo quy tắc nghiệp vụ.

Nên thiết kế **thời gian giữ tuyến cũ** và điều kiện retire rõ ràng. Khi đã hết thời hạn rollback, gỡ code cũ và giảm nợ kỹ thuật; không duy trì hai tuyến gửi thật lâu dài chỉ vì chưa quyết định owner.

### 13.2. Chuyển ngược từ integration về internal event

Nếu một dịch vụ được sáp nhập trở lại modular monolith, có thể chuyển consumer bên ngoài thành `@ApplicationModuleListener` nội bộ. Vẫn cần:

1. Xác định ai sở hữu state và business invariant sau khi gộp.
2. Bảo tồn event ID, trạng thái processing và lịch sử side effect để không xử lý trùng trong thời gian cutover.
3. Di chuyển dữ liệu bằng snapshot/catch-up nếu database cũ khác database mới.
4. Dừng tuyến broker cũ theo thứ tự kiểm soát; không xóa outbox hoặc pending messages khi chưa đối soát.

Thay kênh giao tiếp có thể giảm độ trễ nhưng không tự làm mất các rủi ro nghiệp vụ do dữ liệu lịch sử và side effect tạo ra.

## 14. Quan sát và vận hành trong giai đoạn chuyển tiếp

Sự kiện “đã được publish” là một tín hiệu rất khác “consumer đã hoàn thành”. Nên thiết kế quan sát từ nguồn đến đích.

| Chỉ số / trường log | Cách dùng |
| --- | --- |
| `eventId`, `eventType`, `orderId`, `correlationId` | Nối trace giữa Orders, externalizer và consumer |
| `schemaVersion`, topic/route | Xác minh contract và đích gửi |
| Publication pending/failed và tuổi publication | Phát hiện sự kiện chưa được externalize |
| Broker produce ack/errors | Phân biệt lỗi mạng/broker với lỗi processing nội bộ |
| Consumer lag, retry count và dead-letter | Theo dõi hệ thống ngoài đang theo kịp hay bị kẹt |
| Processing success/failure theo consumer | Xác định module nhận nào chịu trách nhiệm lỗi |
| Reconciliation mismatch | Kiểm tra state thực tế, tránh chỉ dựa trên số lượng event |
| Latency P50/P95/P99 end-to-end | Đánh giá SLA thực tế qua nhiều bước |

Ví dụ log có cấu trúc:

~~~text
eventType=orders.paid eventId=d198... orderId=68f4... schema=1 phase=EXTERNALIZED
eventType=orders.paid eventId=d198... consumer=crm phase=APPLIED
eventType=orders.paid eventId=d198... consumer=accounting phase=RETRY reason=TIMEOUT
~~~

Không nên log toàn bộ payload chứa PII hoặc thông tin thanh toán nhạy cảm. Nếu chạy multi-instance, cần chú ý khả năng một instance đang xử lý publication trong khi instance khác cố re-submit; cấu hình khôi phục theo phiên bản Spring Modulith, trạng thái publication và cơ chế khóa/claim thực tế.

### Tiêu chí bật và tắt tuyến

Một migration có thể đặt ngưỡng làm ví dụ, cần điều chỉnh theo nghiệp vụ:

- Không có chênh lệch business key ngoài phạm vi đã xác định trong quá trình shadow.
- Schema validation và test tương thích đạt.
- Không phát sinh side effect trùng trong canary.
- Pending publications và consumer lag nằm trong SLA.
- Có phương án đối soát và một thủ tục rollback đã được diễn tập.

Không lấy một lần gửi thành công trên môi trường local làm căn cứ duy nhất để bật toàn bộ traffic production.

## 15. Kiểm thử trước khi chuyển tuyến

Tổ chức test theo **hợp đồng**, **giao tin**, **nghiệp vụ** và **sự cố**.

### 15.1. Contract test

- Kiểm tra mapping `OrderPaid` -> `OrderPaidMessageV1` đúng `eventId`, `orderId`, amount và currency.
- Kiểm tra schema version, field bắt buộc, serialization và định tuyến.
- Kiểm tra không xuất dữ liệu nội bộ, thông tin cá nhân ngoài phạm vi cho phép.
- Kiểm tra consumer cũ có thể đọc schema được công bố theo chính sách tương thích.

### 15.2. Transaction và reliability test

| Tình huống | Điều phải xác minh |
| --- | --- |
| Orders commit thành công | Internal event được phát theo contract; integration publication được ghi nhận/gửi theo cấu hình |
| Orders rollback | Không đưa sự thật `OrderPaid` bị rollback thành integration event đã xác nhận |
| Broker lỗi hoặc timeout | Publication/outbox còn khả năng khôi phục; không đánh dấu sai thành công |
| JVM dừng ngay sau commit | Khi khởi động lại, recovery xử lý publication tồn đọng |
| Broker nhận, publisher mất ack | Có thể gửi lại; consumer không nhân đôi tác dụng |
| Consumer crash sau DB commit trước ack | Consumer nhận lại nhưng trạng thái cuối đúng nhờ idempotency |
| Event phiên bản cũ đến sau version mới | Consumer từ chối hoặc xử lý theo quy tắc ordering hợp lệ |
| Chạy shadow và canary | Chỉ owner được chọn tạo side effect thật |
| Cutover rồi rollback | Không bỏ sót hoặc xử lý lại tác vụ đã hoàn thành |

### 15.3. Module test và kiểm tra kiến trúc

Trong Spring Modulith, có thể dùng `@ApplicationModuleTest` và tiện ích `PublishedEvents` để xác minh publisher; dùng `Scenario` để kiểm tra dòng sự kiện và điều kiện hoàn thành bất đồng bộ theo API phù hợp phiên bản. `ApplicationModules.of(...).verify()` kiểm tra các quy tắc dependency mà framework hỗ trợ.

Ví dụ kiểm tra ranh giới module:

~~~java
import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTest {
    @Test
    void moduleBoundariesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đây không phải test tích hợp broker. Cần test riêng cho serialization, transport, backend publication và broker/consumer thực tế. Với `@ApplicationModuleListener` chạy sau commit, test phải tạo transaction **thực sự commit** và chờ kết quả bằng điều kiện có timeout; test mặc định rollback có thể không kích hoạt listener sau commit.

### 15.4. Diễn tập sự cố

Nên mô phỏng ít nhất các lỗi:

1. Broker ngắt kết nối sau Orders commit.
2. Ứng dụng chết trước khi publication hoàn thành.
3. Consumer nhận trùng event và retry.
4. Consumer lag tăng đột biến.
5. Schema mới bị consumer cũ từ chối.
6. Rollback từ new-primary về old-primary khi một phần side effect đã xảy ra.

Kết quả kiểm thử cần ghi rõ **dữ liệu nào còn lưu, actor nào có thể replay, tác vụ nào không thể hoàn tác**.

## 16. Ví dụ kế hoạch: tách Notifications ra khỏi modular monolith

Ban đầu:

~~~text
Orders -> OrderPaid -> Notifications nội bộ -> ghi email_job -> gửi email
~~~

Mục tiêu:

~~~text
Orders -> internal OrderPaid
                |
                +-> externalize orders.paid.v1 -> Kafka
                                                |
                                                v
                                        Notifications service
                                        -> email_job riêng
                                        -> email provider
~~~

Một trình tự thực hiện thực tế:

**Tuần/giai đoạn 1 — Đóng băng ngữ nghĩa:** thống nhất “paid” là điều kiện nào, publisher nào sở hữu, `eventId`/`orderId`/`orderVersion` và cách phát khi transaction commit. Đưa type vào public API phù hợp và viết module test.

**Giai đoạn 2 — Tạo contract bên ngoài:** định nghĩa `orders.paid.v1`, mapper và test với Notifications service. Không gửi entity JPA hoặc DTO tùy biến theo database Orders.

**Giai đoạn 3 — Thiết lập giao tin bền vững:** cấu hình Spring Modulith event externalization và publication storage phù hợp; đánh giá liệu native externalization đủ hay cần giải pháp outbox chuyên dụng. Thử crash và broker timeout.

**Giai đoạn 4 — Shadow consumer:** service mới nhận event nhưng chỉ dựng projection/test job, chưa gửi email thật. Đối soát với listener cũ qua `eventId` và `orderId`.

**Giai đoạn 5 — Cutover:** chọn một tuyến được phép tạo job/email cho từng nhóm đơn; dùng flag có chung nguồn điều khiển và khóa chống gửi lặp. Theo dõi số email, lag, lỗi và reconciliation.

**Giai đoạn 6 — Ổn định và retire:** dừng listener cũ sau khi không còn pending side effect, đã đủ quan sát và đạt cửa sổ rollback. Gỡ các coupling cũ, bảo toàn contract integration cho các consumer đang sử dụng.

Trong toàn bộ quá trình, Orders tiếp tục phát **một sự thật nghiệp vụ**; quyết định module nào xử lý và ở tiến trình nào thuộc về thiết kế triển khai. Không tạo sự kiện nghiệp vụ mới như `OrderPaidForKafka` chỉ để đánh dấu transport mới.

## 17. Sai lầm thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Cách phòng |
| --- | --- | --- |
| Externalize mọi event nội bộ | Rò rỉ implementation, khó versioning | Chỉ chọn event có nhu cầu tích hợp rõ |
| Dùng JPA entity làm message broker | Coupling DB và lỗi serialization/lazy state | DTO/schema integration riêng |
| Gửi broker trực tiếp trong transaction rồi cho rằng hai bên atomic | Commit business và broker có thể lệch | Registry/outbox và recovery được cấu hình |
| Coi registry là kho lịch sử vô hạn | Consumer mới thiếu dữ liệu quá khứ | Snapshot, backfill, event store/retention hợp lệ |
| Chạy hai consumer có side effect thật | Gửi email, tạo shipment trùng | Shadow/canary và một owner thực thi |
| Dùng timestamp để sắp xếp tuyệt đối | Out-of-order làm state đi lùi | Aggregate version, partition, guard, reconciliation |
| Chỉ kiểm tra delivery count | Không phát hiện state sai dù đủ message | Đối soát state và business invariant |
| Không chuẩn bị rollback trước cutover | Rủi ro kéo dài khi tuyến mới lỗi | Runbook, checkpoint, giữ tuyến cũ một thời gian |
| Dùng cùng schema nội bộ và bên ngoài mãi mãi | Deploy độc lập trở nên khó | Tách mapping và contract ownership |
| Kỳ vọng exactly-once xuyên DB, broker và email | Side effect lặp không được xử lý | Idempotency và kế hoạch compensation |

## 18. Bài tập thực hành

### Bài 1 — Chọn sự kiện externalize

Một ứng dụng bán hàng đang có `OrderDraftUpdated`, `OrderPaid`, `InventoryReserved`, `EmailQueued` và `OrderCancelled`. CRM chỉ cần thông tin đơn đã thanh toán/hủy, kho ngoài cần thông tin đã giữ hàng. Hãy lập bảng event cần externalize, consumer, payload tối thiểu và rủi ro khi event đến muộn.

### Bài 2 — Thiết kế contract và mapper

Từ internal `OrderPaid(eventId, orderId, occurredAt, paidAmount, currency, orderVersion)`, hãy tạo schema `orders.paid.v1` và test mapping. Thêm một field không bắt buộc sau này; giải thích cách duy trì tương thích khi còn consumer v1.

### Bài 3 — Xây runbook cutover

Notifications hiện gửi email nội bộ. Service mới nhận qua Kafka. Hãy mô tả shadow -> canary -> new-primary -> retire, cách giữ duy nhất một bên được gửi thật và điều kiện rollback khi consumer lag hoặc tỷ lệ lỗi vượt ngưỡng.

### Bài 4 — Giải quyết kịch bản crash

Giả sử broker đã nhận một event nhưng ứng dụng chết trước khi publication được đánh dấu hoàn tất. Sau restart, event có thể được gửi lại. Thiết kế consumer với `eventId`, unique constraint và transaction để tránh tạo hai email job. Thảo luận vì sao điều này vẫn chưa tự bảo đảm một nhà cung cấp email sẽ không gửi hai email nếu API của họ không hỗ trợ idempotency.

### Bài 5 — Đồng bộ consumer mới

CRM cần trạng thái của 100.000 đơn cũ và các event phát sinh trong lúc nhập dữ liệu. Hãy thiết kế snapshot + cursor/catch-up và chỉ ra chỗ có thể mất hoặc nhận trùng event. Xác định tiêu chí để bật CRM làm consumer chính thức.

## 19. Checklist chuyển tiếp

- [ ] Đã xác định event nào là sự thật nghiệp vụ đáng công bố ra ngoài.
- [ ] Publisher và owner của event rõ ràng, không phát khi transaction thất bại.
- [ ] Schema, version, routing và payload của integration event có tài liệu.
- [ ] Không xuất entity nội bộ hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Đã lựa chọn registry/outbox phù hợp với yêu cầu độ tin cậy và phiên bản thư viện.
- [ ] Đã có xử lý retry, duplicate, ordering và event đến muộn.
- [ ] Consumer mới có cách đồng bộ dữ liệu ban đầu nếu cần.
- [ ] Shadow/canary không gây side effect trùng; chỉ một tuyến được quyền xử lý thật.
- [ ] Có metrics, alert, trace, reconciliation và runbook khôi phục.
- [ ] Đã kiểm tra rollback/cutover trên các kịch bản có crash và lỗi transport.
- [ ] Đã xác định khi nào có thể gỡ tuyến cũ mà không làm mất pending work.

## 20. Tổng kết

**Chiến lược chuyển tiếp hiệu quả** cho Spring Modulith giữ nguyên ý nghĩa sự kiện trong module sở hữu, chọn lọc những sự thật phải xuất ra ngoài, rồi bổ sung hợp đồng tích hợp và cơ chế giao đáng tin cậy phù hợp. `ApplicationEventPublisher` và các listener nội bộ tiếp tục giúp giảm phụ thuộc trong modular monolith; Spring Modulith event externalization có thể nối những sự kiện đã chọn tới messaging bên ngoài.

Từ thời điểm có consumer triển khai độc lập, cần quản lý thêm versioning, routing, persistence, retry, idempotency, initial sync, ordering và quan sát end-to-end. Cutover từng phần, shadow testing và kế hoạch rollback giúp di chuyển trách nhiệm mà không đồng thời kích hoạt hai tuyến side effect thật.

### Tài liệu tham khảo

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional listeners, Event Publication Registry, event externalization, testing và các lựa chọn outbox theo phiên bản.
- [Spring Modulith — EventExternalizationConfiguration API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventExternalizationConfiguration.html): cấu hình chọn event, mapping và routing cho externalization.

> Các đoạn mã và định tuyến ở đây minh họa thiết kế. Khi triển khai, cần đối chiếu dependency, API và thuộc tính cấu hình với **phiên bản Spring Modulith** của ứng dụng thực tế.
