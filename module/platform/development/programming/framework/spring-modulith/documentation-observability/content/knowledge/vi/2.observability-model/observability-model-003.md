# Công bố sự kiện miền và xử lý bất đồng bộ

Trong một ứng dụng Spring Boot được tổ chức theo **Spring Modulith**, các application module nên có ranh giới rõ ràng: module đặt hàng chịu trách nhiệm nghiệp vụ đơn hàng, module thông báo chịu trách nhiệm thông báo, còn module thanh toán chịu trách nhiệm thanh toán. **Sự kiện miền (domain event)** cho phép một module công bố điều đã xảy ra trong nghiệp vụ, để các module khác phản ứng mà module phát sự kiện không phải gọi trực tiếp vào phần triển khai của chúng.

Bài học thuộc chương **Mô hình quan sát** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**: sử dụng Spring Modulith để tài liệu hóa ranh giới application module và quan sát tương tác trong ứng dụng Spring Boot. Vì vậy, ngoài cách công bố và tiếp nhận sự kiện, trọng tâm là **xác định khi nào công việc thực sự chạy, khi nào được coi là hoàn tất, và dùng dấu vết vận hành nào để chứng minh điều đó**. Các khái niệm về module graph, Actuator, event metrics, tracing và context propagation sẽ được nối trực tiếp với luồng xử lý bất đồng bộ.

## 1. Từ lời gọi trực tiếp đến sự kiện miền

Giả sử thao tác đặt hàng cần lưu đơn hàng, gửi email xác nhận và ghi dữ liệu cho báo cáo. Cách triển khai gọi trực tiếp các dịch vụ sau khi lưu đơn tạo ra những vấn đề:

- Module **order** phải biết API của **notification** và **reporting**, làm tăng phụ thuộc giữa các module.
- Một lỗi hoặc độ trễ khi gửi email có thể kéo dài luồng xử lý đặt hàng.
- Khó phân biệt thất bại của nghiệp vụ chính với thất bại của tác vụ phát sinh.
- Khi xử lý chuyển sang luồng nền, một phản hồi HTTP thành công không còn chứng minh mọi tác vụ đã hoàn tất.

Thay vào đó, module **order** phát sự kiện **OrderPlaced**. Các module quan tâm có thể đăng ký xử lý sự kiện theo hợp đồng công khai. Sự kiện biểu thị **một sự thật đã xảy ra**, không phải mệnh lệnh yêu cầu một module cụ thể thực hiện công việc.

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Sự kiện miền | **OrderPlaced** | Đơn hàng đã được tạo theo quy tắc nghiệp vụ. |
| Lệnh (command) | **SendOrderConfirmation** | Yêu cầu thực hiện một hành động cụ thể. |
| Module phát | **order** | Sở hữu quy tắc tạo đơn và thời điểm phát sự kiện. |
| Module nhận | **notification**, **reporting** | Tự chọn cách phản ứng với sự kiện đã công bố. |
| Event bus trong tiến trình | **ApplicationEventPublisher** | Phân phối sự kiện cho listener Spring trong cùng ứng dụng. |
| Event broker ngoài tiến trình | Kafka, RabbitMQ, v.v. | Truyền thông điệp giữa các tiến trình; đòi hỏi cơ chế tích hợp riêng. |

**ApplicationEventPublisher không tự biến sự kiện thành thông điệp bền vững trên broker.** Với Spring Modulith, module vẫn có thể giao tiếp bằng Spring application events ngay trong cùng tiến trình. Khi cần giao tiếp giữa các dịch vụ, cần thiết kế bước externalization/broker riêng cùng các bảo đảm giao hàng phù hợp.

### Thiết kế hợp đồng sự kiện

Một sự kiện hữu ích nên có tên ở thì quá khứ, bất biến, chứa dữ liệu đủ cho phía nhận và có mã định danh ổn định:

~~~java
package com.example.shop.order;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

Ở ví dụ này, **OrderPlaced** được đặt tại API có thể truy cập của module **order**; đối tác không cần phụ thuộc vào entity, repository hay package nội bộ của module đó. **eventId** giúp nhận diện một lần phát sinh sự kiện khi retry; **orderId** là khóa nghiệp vụ; **occurredAt** ghi nhận thời điểm sự kiện được tạo. Không đưa toàn bộ JPA entity, thông tin nhạy cảm hoặc object graph có quan hệ lazy-loading vào payload.

Sự kiện nên biểu diễn đúng trạng thái nghiệp vụ và được phát tại nơi trạng thái ấy được thay đổi. Nếu sau này phải thêm trường, cần cân nhắc tương thích giữa publisher và listener; với hợp đồng được externalize ra broker, quy tắc versioning càng quan trọng.

## 2. Công bố sự kiện trong giao dịch nghiệp vụ

Module **order** lưu đơn và phát sự kiện qua **ApplicationEventPublisher**:

~~~java
package com.example.shop.order;

import java.time.Instant;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    @Transactional
    public UUID place(CreateOrderRequest request) {
        Order order = orders.save(Order.from(request));

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                order.getId(),
                Instant.now()
        ));

        return order.getId();
    }
}
~~~

Đây là **đoạn minh họa**: **Order**, **OrderRepository** và **CreateOrderRequest** là các kiểu nghiệp vụ giả định trong dự án. Các thành phần quan trọng cần nhận ra là **@Transactional** và **events.publishEvent(...)**.

Cần phân biệt hai thời điểm:

1. Lời gọi **publishEvent** xảy ra *bên trong* phương thức đặt hàng, khi giao dịch có thể vẫn chưa commit.
2. Việc listener thực sự xử lý trước hay sau commit phụ thuộc vào **loại listener**, không phụ thuộc riêng lời gọi **publishEvent**.

Nếu module nhận dùng listener đồng bộ thông thường, mã xử lý có thể chạy ngay trong luồng gọi hiện tại. Nếu module nhận dùng listener theo giao dịch sau commit, công việc sẽ chỉ bắt đầu ở pha tương ứng sau khi giao dịch đã commit thành công. Cách phân biệt này quyết định liệu tác vụ phụ có nhìn thấy dữ liệu đã commit hay làm gián đoạn nghiệp vụ chính.

## 3. Chọn đúng mô hình listener

| Cơ chế | Thời điểm mặc định | Luồng / giao dịch | Điều cần quan sát |
| --- | --- | --- | --- |
| **@EventListener** | Khi sự kiện được phát | Thường đồng bộ, cùng luồng; có thể đang ở trong giao dịch publisher | Độ trễ và lỗi listener có thể tác động trực tiếp tới publisher. |
| **@TransactionalEventListener** | **AFTER_COMMIT** | Gắn với pha giao dịch; bản thân annotation không tạo xử lý bất đồng bộ | Sự kiện có bị bỏ qua do không có giao dịch hay không; callback chạy sau commit hay chưa. |
| **@Async** kết hợp listener | Theo executor được cấu hình | Chạy trên luồng khác | Lỗi bất đồng bộ, hàng đợi executor và việc truyền ngữ cảnh quan sát. |
| **@ApplicationModuleListener** của Spring Modulith | Sau commit giao dịch | Cơ chế listener theo giao dịch, xử lý bất đồng bộ và sử dụng giao dịch riêng | Hoàn tất/thất bại của từng listener, retry, độ trễ sau commit. |

**@ApplicationModuleListener** là lựa chọn thuận tiện cho giao tiếp bất đồng bộ giữa các application module: nó kết hợp hành vi listener theo giao dịch với xử lý bất đồng bộ và ranh giới giao dịch riêng cho listener. Điều này tránh nhầm lẫn giữa **“giao dịch đặt hàng đã commit”** và **“module thông báo đã xử lý thành công”**.

Ví dụ một listener trong module **notification**:

~~~java
package com.example.shop.notification.internal;

import com.example.shop.order.OrderPlaced;
import lombok.RequiredArgsConstructor;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
class OrderPlacedListener {

    private final NotificationRequestRepository requests;

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        // Ghi yêu cầu thông báo vào DB của module notification.
        // eventId phải có ràng buộc duy nhất để tránh tạo trùng khi retry.
        if (!requests.existsByEventId(event.eventId())) {
            requests.save(new NotificationRequest(
                    event.eventId(), event.orderId()
            ));
        }
    }
}
~~~

Trong ví dụ, repository và entity thông báo là các thành phần giả định. Việc kiểm tra tồn tại chỉ mang tính minh họa; trong triển khai thật, **unique constraint trên eventId** mới giúp chặn tạo trùng khi hai luồng đồng thời xử lý cùng sự kiện. Nếu listener gọi hệ thống email bên ngoài, cần thêm cơ chế chống gửi trùng ở hệ thống đích hoặc lưu tác vụ gửi vào bảng outbox/queue phù hợp. Không nên xem giao dịch cơ sở dữ liệu và thao tác gửi email là một giao dịch nguyên tử.

### Ba tình huống dễ gây hiểu sai

**Giao dịch đặt hàng rollback.** Với listener theo giao dịch **AFTER_COMMIT**, callback không được gọi để xử lý sự kiện của giao dịch đã rollback. Ngược lại, một **@EventListener** đồng bộ có thể đã chạy trước khi rollback, nên việc đặt tác vụ có side effect ở đó cần cân nhắc kỹ.

**Không tồn tại giao dịch đang hoạt động.** **@TransactionalEventListener** mặc định không thực thi nếu không có transaction phù hợp, trừ khi cấu hình chế độ fallback. Một bài test gọi publisher bên ngoài transaction có thể cho kết quả khác luồng nghiệp vụ thực tế.

**Listener thất bại sau khi đơn hàng đã commit.** Lỗi ở listener bất đồng bộ không tự đảo ngược giao dịch đã hoàn tất của publisher. Hệ thống phải theo dõi lần xử lý thất bại, quyết định cách phát lại và bảo đảm listener an toàn khi xử lý trùng.

## 4. Vòng đời sự kiện và ranh giới bất đồng bộ

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant O as Order module
    participant D as Database
    participant R as Publication registry
    participant N as Notification module
    C->>O: place order
    O->>D: Lưu đơn trong transaction
    O->>O: publish OrderPlaced
    opt Có registry bền vững
        O->>R: Ghi publication chưa hoàn tất
    end
    O->>D: Commit transaction
    O-->>C: Trả kết quả đặt hàng
    O-->>N: Dispatch sau commit, bất đồng bộ
    N->>N: Xử lý trong transaction riêng
    alt Xử lý thành công
        N-->>R: Đánh dấu publication hoàn tất nếu có registry
    else Xử lý lỗi
        N-->>R: Publication còn chưa hoàn tất nếu có registry
    end
~~~

Sơ đồ minh họa dòng thời gian logic; thứ tự thực tế giữa việc trả phản hồi HTTP và việc worker bất đồng bộ bắt đầu chạy có thể thay đổi theo scheduling. **Không dựa vào việc client đã nhận HTTP 200/201 để kết luận email đã được gửi**.

Một giao dịch của publisher chỉ chịu trách nhiệm tính nhất quán của nghiệp vụ đặt hàng. Listener bất đồng bộ có vòng đời riêng: có thể bắt đầu muộn, gặp lỗi, được thử lại hoặc chạy lại sau khi ứng dụng khởi động lại nếu hệ thống có cơ chế phục hồi. Bởi vậy, trạng thái **đã phát**, **đang xử lý**, **đã hoàn tất** và **cần xử lý lại** phải được phân biệt khi vận hành.

### Bảng diễn giải trạng thái

| Trạng thái thực tế | Điều có thể khẳng định | Điều chưa thể khẳng định |
| --- | --- | --- |
| Publisher gọi **publishEvent** | Sự kiện đã được chuyển cho cơ chế phát event trong tiến trình | Transaction đã commit; mọi listener đã nhận và hoàn tất. |
| Transaction publisher commit | Thay đổi nghiệp vụ chính đã được xác nhận | Listener async đã xử lý xong. |
| Listener bắt đầu | Tác vụ phụ đã nhận cơ hội xử lý | Tác vụ đã bền vững, thành công hoặc chỉ chạy đúng một lần. |
| Listener trả về thành công | Luồng xử lý listener hoàn thành theo mã ứng dụng | Side effect ở hệ thống ngoài có tính exactly-once. |
| Có publication chưa hoàn tất | Tồn tại công việc cần điều tra hoặc phục hồi | Sự kiện chắc chắn chưa gây side effect nào. |

## 5. Event Publication Registry: theo dõi việc giao sự kiện

Spring Modulith cung cấp cơ chế **Event Publication Registry** để theo dõi việc công bố sự kiện tới các transactional event listener. Khi cấu hình một triển khai **bền vững** phù hợp (ví dụ dựa trên JDBC/JPA), registry có thể lưu các publication cần xử lý trong cùng giao dịch của publisher và ghi nhận khi listener hoàn tất. Cơ chế này hữu ích vì xử lý bất đồng bộ có thể thất bại sau khi dữ liệu nghiệp vụ đã commit.

Lưu ý ba giới hạn:

1. **Registry phụ thuộc vào dependency và cấu hình thực tế.** Không mặc định suy ra mọi ứng dụng chỉ cần gọi **publishEvent** là đã có lưu trữ bền vững.
2. **Publication chưa hoàn tất không đồng nghĩa hệ thống tự retry vô hạn.** Việc tìm, phát lại hoặc lên lịch phục hồi cần kiểm tra API và cấu hình của phiên bản Spring Modulith đang sử dụng.
3. **Có thể có xử lý trùng.** Listener có thể thực hiện side effect rồi chết trước khi hoàn thành việc ghi nhận publication. Khi phát lại, cùng sự kiện có thể xuất hiện lần nữa. Thiết kế theo **at-least-once + idempotency** là cách suy nghĩ an toàn hơn việc giả định exactly-once.

Ví dụ: listener ghi một hàng thông báo với khóa duy nhất **eventId**. Nếu lần đầu đã ghi thành công nhưng việc ghi nhận publication hoàn tất bị gián đoạn, lần sau listener thấy cùng eventId và không thêm hàng mới. Đối với API bên ngoài, cần kiểm tra phía nhận có hỗ trợ **idempotency key** hay không. Nếu không, có thể cần thiết kế thêm bảng trạng thái gửi, outbox hoặc quy trình đối soát.

Registry giúp biết **listener nào còn tồn đọng**; nó không thay thế hoàn toàn message broker, cơ chế dead-letter queue, chính sách backoff, giới hạn retry và công cụ quan sát hệ thống bên ngoài.

## 6. Quan sát runtime: module graph, Actuator, metrics và tracing

**Module graph** trả lời câu hỏi **“module nào được phép phụ thuộc module nào?”**. Việc tạo tài liệu kiến trúc từ Spring Modulith thể hiện các application module và quan hệ phụ thuộc, bao gồm bối cảnh hợp đồng công khai giữa chúng. Tuy nhiên, biểu đồ kiến trúc tĩnh không đủ để trả lời **“sự kiện nào vừa lỗi vào lúc 14:05?”**.

Đối với câu hỏi vận hành, kết hợp các nguồn sau:

| Nguồn thông tin | Trả lời câu hỏi | Giới hạn cần nhớ |
| --- | --- | --- |
| Kiểm tra module và tài liệu module graph | Có phụ thuộc sai ranh giới hoặc gọi vào package nội bộ không? | Phản ánh cấu trúc/mối quan hệ, không chứng minh một event runtime đã thành công. |
| Actuator và tích hợp Spring Modulith | Ứng dụng có những module nào; endpoint sức khỏe, metrics hoạt động ra sao? | Endpoint phải được thêm dependency, cấu hình và expose phù hợp; endpoint module không phải danh sách sự kiện đã giao thành công. |
| Event Publication Registry | Publication nào chưa hoàn tất; listener nào cần xem xét? | Cần backend và quy trình vận hành; trạng thái chưa hoàn tất có thể cần đối soát side effect. |
| Micrometer metrics | Lượng sự kiện, lỗi, thời gian xử lý, backlog tăng hay giảm? | Những metric nghiệp vụ riêng phải được instrument hoặc xuất từ hệ thống phù hợp. |
| Distributed tracing | Luồng nào tạo đơn và listener/module nào xử lý tiếp? | Qua ranh giới async có thể đứt trace nếu không truyền observation context. |
| Structured logs | EventId nào lỗi; stack trace nào xuất hiện? | Cần correlation ID thống nhất và tránh ghi dữ liệu nhạy cảm. |

Nếu bật tích hợp Actuator dành cho application modules, có thể kiểm tra endpoint mô tả các module như **/actuator/applicationmodules**, tùy phiên bản và cấu hình expose. **/actuator/health** và **/actuator/metrics** phục vụ tình trạng ứng dụng và metrics; **/actuator/prometheus** cần registry/exposure tương ứng. Dữ liệu trace thường được xuất tới backend tracing (ví dụ Jaeger/Tempo/Zipkin thông qua hệ thống quan sát phù hợp), không phải một bảo đảm tự có chỉ vì Actuator đang chạy.

### 6.1. Metric nên theo dõi

Những tên dưới đây là **gợi ý metric nghiệp vụ tự thiết kế**, không phải cam kết Spring Modulith tự sinh tất cả metric có tên này:

| Metric gợi ý | Kiểu | Diễn giải |
| --- | --- | --- |
| **domain_event_published_total** | Counter | Số lần publisher phát sự kiện theo event type và module phát. |
| **domain_event_listener_completed_total** | Counter | Số lần listener kết thúc thành công theo event type, listener và outcome. |
| **domain_event_listener_failed_total** | Counter | Số lần xử lý lỗi, giúp nhận diện failure rate. |
| **domain_event_processing_duration_seconds** | Timer/Histogram | Thời gian listener thực thi; theo dõi p50/p95/p99. |
| **domain_event_pending** | Gauge | Số publication chưa hoàn tất từ registry hoặc cơ chế hàng đợi thực tế. |
| **domain_event_oldest_pending_age_seconds** | Gauge | Tuổi của publication chưa hoàn tất lâu nhất. |

Chọn nhãn có **số lượng giá trị hữu hạn** như event type, publisher module, listener và outcome. Không dùng **eventId**, **orderId**, email hoặc trace ID làm nhãn metric: mỗi giá trị gần như duy nhất sẽ tạo cardinality rất lớn. Các định danh này phù hợp hơn với structured logs/traces.

Ví dụ tiêu chí giám sát:

- **Pending count** tăng liên tục dù lưu lượng phát sự kiện ổn định: kiểm tra worker, lỗi listener và cơ chế retry.
- **Oldest pending age** vượt thời gian phục vụ mong đợi: kiểm tra publication đang mắc kẹt, ngay cả khi số lượng pending ít.
- **p95 listener duration** tăng: kiểm tra dependency ngoài, nghẽn DB hoặc executor quá tải.
- **Failure rate** tăng sau một deployment: xác định module/listener và phiên bản được triển khai, rồi đối chiếu logs và traces.

### 6.2. Trace đi qua ranh giới bất đồng bộ

Yêu cầu HTTP tạo đơn thường có một trace đang hoạt động. Sau commit, **@ApplicationModuleListener** xử lý ở luồng nền, nơi trace context, MDC và các thread-local khác **không được mặc định bảo đảm giữ nguyên**. Cần kiểm tra cách cấu hình Micrometer Tracing/Context Propagation và executor hoặc TaskDecorator phù hợp với stack, phiên bản sử dụng.

Một cách thực hành có thể kiểm chứng:

1. Ở luồng publisher, log có **traceId**, **module=order**, **eventId** và **orderId**.
2. Sự kiện giữ **eventId** làm khóa tương quan nghiệp vụ không phụ thuộc vào thread-local.
3. Ở listener, bắt đầu hoặc liên kết observation/span xử lý; log có **module=notification**, **eventId**, trạng thái và thời gian xử lý.
4. Đối chiếu trace của publisher và listener trên backend quan sát. Nếu trace bị tách, dùng eventId để tra cứu cả hai bên và sửa cấu hình propagation khi cần.

Không giả định annotation **@Async** tự động truyền toàn bộ security context, MDC hay tracing context. Cũng không truyền dữ liệu nhạy cảm trong event chỉ để nối trace. Đối với luồng ghi nhận audit hay điều tra dài hạn, correlation ID tồn tại trong event và log bền vững thường đáng tin cậy hơn việc chỉ phụ thuộc trace retention.

### 6.3. Ví dụ log có thể đối chiếu

~~~text
2026-11-27T09:00:00Z INFO  module=order
  action=order_placed eventType=OrderPlaced
  eventId=7d1e... orderId=0c42... traceId=ab12...

2026-11-27T09:00:01Z INFO  module=notification
  action=listener_started eventType=OrderPlaced
  eventId=7d1e... traceId=ab12...

2026-11-27T09:00:03Z ERROR module=notification
  action=listener_failed eventType=OrderPlaced
  eventId=7d1e... errorType=MailGatewayTimeout
~~~

Các giá trị trên chỉ là dữ liệu minh họa. Trong triển khai thật, **traceId ở listener có thể khác hoặc vắng mặt** nếu không cấu hình propagation; việc hai dòng có cùng **eventId** mới là phép nối chắc chắn do chính hợp đồng sự kiện cung cấp.

## 7. Quy trình xử lý một lỗi thực tế

Tình huống: khách hàng đặt đơn thành công nhưng email xác nhận không xuất hiện.

**Bước 1 — Xác định giao dịch nghiệp vụ.** Tra **orderId** trong DB và tìm log công bố **OrderPlaced**. Nếu transaction đã rollback, không mong chờ **AFTER_COMMIT** listener chạy. Nếu đã commit, chuyển sang kiểm tra luồng bất đồng bộ.

**Bước 2 — Xác định sự kiện và listener.** Dùng **eventId** đối chiếu giữa log publisher, registry (nếu có) và log notification. Nếu không có log listener, kiểm tra registration, điều kiện có transaction, việc dispatch/executor và tình trạng ứng dụng.

**Bước 3 — Phân loại lỗi.** Listener chưa chạy, chạy nhưng ném exception, chạy thành công nhưng chưa gửi email, hay email gateway chấp nhận yêu cầu nhưng quá trình gửi tiếp theo thất bại là các nguyên nhân khác nhau. Chúng cần điểm đo khác nhau.

**Bước 4 — Kiểm tra publication còn tồn đọng.** Khi registry bền vững được bật, tìm publication chưa hoàn tất và quyết định phát lại theo cơ chế của phiên bản được triển khai. Trước khi phát lại, kiểm tra listener idempotent và đối soát side effect để tránh gửi trùng.

**Bước 5 — Xác nhận phục hồi.** Theo dõi publication chuyển sang hoàn tất, pending age giảm, metric thành công tăng và kết quả thực tế ở hệ thống notification. Nếu chỉ dựa vào HTTP thành công của publisher hoặc metric listener đã bắt đầu, cuộc điều tra vẫn chưa đủ bằng chứng.

### Ma trận sự cố thường gặp

| Triệu chứng | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không có log listener sau khi gọi publisher | Publisher không có transaction; transaction rollback; listener chưa đăng ký; executor không chạy | Kiểm tra transaction boundary, annotation và bean scanning, log/trace ở thời điểm dispatch. |
| HTTP trả thành công nhưng email thất bại | Listener chạy async sau commit; dependency ngoài lỗi | Dùng registry/log/metrics để tìm publication lỗi và retry an toàn. |
| Một sự kiện tạo hai email | Retry sau side effect, xử lý trùng hoặc cạnh tranh giữa worker | Dùng eventId, unique constraint và idempotency ở phía gửi. |
| Trace dừng ở publisher | Context chưa được truyền qua executor | Kiểm tra Micrometer Context Propagation và cấu hình executor; nối nghiệp vụ qua eventId. |
| Pending count tăng, CPU vẫn thấp | Listener nghẽn I/O, executor thiếu worker, downstream quá chậm | Đo duration, queue/wait time, timeout và capacity của dependency. |
| Listener thấy dữ liệu chưa commit | Đã dùng listener đồng bộ trong giao dịch publisher | Xem lại **@TransactionalEventListener**/**@ApplicationModuleListener** và ranh giới giao dịch. |
| Thêm retry khiến dữ liệu bị nhân đôi | Listener không idempotent | Ràng buộc khóa nghiệp vụ và ghi nhận xử lý trùng một cách an toàn. |

## 8. Cách kiểm chứng kiến trúc và hành vi

Tài liệu module graph cho thấy cấu trúc dự kiến; bài kiểm thử và observability cho thấy ứng dụng có thực sự hành xử như thiết kế không. Nên kiểm chứng theo từng lớp.

### Kiểm chứng ranh giới module

Trong bài test kiến trúc, Spring Modulith có API **ApplicationModules** để xác minh các quy tắc phụ thuộc module:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**ShopApplication** là class Spring Boot chính trong ví dụ. Phép kiểm tra này giúp phát hiện phụ thuộc module không hợp lệ, nhưng **không thay cho test sự kiện**; nó không chứng minh listener đã chạy sau commit hay hoạt động idempotent. Spring Modulith còn có khả năng sinh tài liệu/module diagram, hữu ích để đối chiếu hợp đồng phát/nhận với cấu trúc mã nguồn.

### Kiểm chứng thời điểm và khả năng phục hồi

Một bộ integration test nên bao phủ:

1. **Commit:** tạo đơn thành công; có **OrderPlaced** với đúng **orderId** và listener xử lý sau commit.
2. **Rollback:** phát sự kiện trong giao dịch rồi gây rollback; listener **AFTER_COMMIT** không tạo tác vụ thông báo.
3. **Async:** test đợi có điều kiện để xác nhận tác vụ hoàn tất; không viết assertion giả định listener xong ngay khi **place(...)** trả về.
4. **Failure:** giả lập downstream ném exception; xác nhận publication còn chưa hoàn tất khi registry bền vững được cấu hình.
5. **Recovery:** phát lại cùng sự kiện; xác nhận tạo đúng một yêu cầu thông báo nhờ **eventId** và ràng buộc DB.
6. **Observability:** xác nhận log chứa eventId, metrics phản ánh outcome/duration và trace/correlation hợp lý sau khi đổi thread.

Trong thực tế có thể sử dụng hỗ trợ integration testing/Scenario của Spring Modulith để chờ event và xác minh kết quả. Khi test hành vi async, ưu tiên cơ chế chờ có timeout hữu hạn và điều kiện cụ thể thay vì **Thread.sleep(...)** cố định; nếu test phụ thuộc backend registry thì cần khởi tạo backend đó thật, không suy ra độ bền từ mock event bus.

### Tiêu chí chấp nhận có thể đo

| Mục tiêu | Bằng chứng |
| --- | --- |
| Module **order** không phụ thuộc triển khai **notification** | Kiểm chứng ranh giới module và review public event contract. |
| Đơn hàng rollback không phát sinh thông báo | Integration test với transaction rollback. |
| Tác vụ async lỗi không làm rollback đơn hàng đã commit | Integration test lỗi listener và dữ liệu order được giữ nguyên. |
| Sự kiện lặp không tạo dữ liệu thông báo trùng | Test replay/đồng thời, unique constraint trên eventId. |
| Sự kiện tồn đọng được phát hiện | Registry query/metric pending và cảnh báo tuổi tồn đọng. |
| Có thể lần từ HTTP request sang listener | Trace khi đã cấu hình propagation và eventId trong log hai module. |

## 9. Các quyết định thiết kế cần ghi lại trong tài liệu module

**Mức độ nhất quán.** Nếu nghiệp vụ bắt buộc thanh toán và đơn hàng phải thành công hoặc thất bại cùng nhau, không tự động chuyển mọi bước sang event async. Sự kiện bất đồng bộ phù hợp hơn với tác vụ hậu xử lý có thể chấp nhận độ trễ, hoặc với workflow phân tán có chính sách bù trừ rõ ràng.

**Thứ tự sự kiện.** Nhiều event cho cùng **orderId** có thể được listener xử lý lệch thứ tự khi chạy trên executor hoặc khi retry. Nếu thứ tự quan trọng, cần version/sequence theo aggregate và cơ chế sắp thứ tự tại consumer hoặc hạ tầng truyền thông.

**Khả năng vận hành.** Xác định retry/backoff, giới hạn số lần xử lý, cách đưa sự kiện không thể xử lý vào quy trình điều tra, thời hạn retention và quyền truy cập dữ liệu event. Công cụ ghi nhận publication không tự quyết định chính sách kinh doanh.

**Quan sát theo ranh giới module.** Tài liệu hóa ít nhất publisher module, event type, listener module, transaction phase, tác vụ side effect, idempotency key và metric/log/trace liên quan. Đó là cầu nối giữa tài liệu kiến trúc và sự thật vận hành.

**Không phụ thuộc vào trace cho tính đúng đắn.** Tracing giúp điều tra và tối ưu hiệu năng; hoạt động kinh doanh phải được bảo vệ bằng transaction, registry, trạng thái nghiệp vụ và idempotency, kể cả khi sampling không ghi lại trace.

## 10. Tổng kết kiến thức

Trong Spring Modulith, **ApplicationEventPublisher** tạo điểm giao tiếp dựa trên sự kiện giữa các module. **@ApplicationModuleListener** giúp xử lý sự kiện sau commit và bất đồng bộ trong giao dịch riêng, nhưng thành công của publisher và thành công của listener là **hai mốc độc lập**. Nếu sử dụng **Event Publication Registry** bền vững, hệ thống có thêm thông tin về publication chưa hoàn tất để điều tra và phục hồi; listener vẫn cần idempotency khi replay.

Để kiểm chứng kiến trúc mô-đun trong vận hành, hãy dùng **module graph** xác nhận ranh giới phụ thuộc, **Actuator** quan sát tình trạng ứng dụng, **metrics** phát hiện độ trễ/lỗi/tồn đọng, **tracing** quan sát đường đi thực thi và **eventId trong structured logs** để tương quan chắc chắn qua ranh giới bất đồng bộ. Đó là cách chuyển từ câu hỏi **“đã phát sự kiện chưa?”** sang câu hỏi có thể trả lời bằng bằng chứng: **“module nào đã xử lý, khi nào, kết quả ra sao và có thể phục hồi an toàn không?”**
