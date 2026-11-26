# Tạo listener

## Mục tiêu thực hành

Trong bài này, bạn sẽ tạo một listener thuộc module Fulfillment để nhận event OrderConfirmed do module Orders phát ra. Khi đơn hàng được xác nhận và transaction của Orders commit, listener tạo một yêu cầu fulfillment tương ứng.

Luồng hoàn chỉnh:

1. Orders cập nhật trạng thái đơn hàng trong transaction.
2. Orders công bố OrderConfirmed qua ApplicationEventPublisher.
3. Transaction commit thành công.
4. Spring Modulith dispatch event tới listener của Fulfillment.
5. Listener xử lý trong transaction riêng và tạo fulfillment request.
6. Integration test chờ side effect được commit rồi xác nhận kết quả.

Bài thực hành giúp bạn hiểu cách publisher và listener giao tiếp qua application event, giữ ranh giới module, xử lý sau commit và thiết kế listener an toàn khi event được giao lại.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant O as Orders module
    participant DB as Orders database
    participant E as Spring event infrastructure
    participant F as Fulfillment listener
    participant FDB as Fulfillment database

    API->>O: confirm(orderId)
    O->>DB: Update order status
    O->>E: publish OrderConfirmed
    O->>DB: Commit transaction
    DB-->>E: Commit completed
    E->>F: Dispatch after commit
    F->>FDB: Create fulfillment request
    FDB-->>F: Commit listener transaction
~~~

Các tên module, package và bảng trong bài là ví dụ cho một ứng dụng Spring Modulith. Hãy ánh xạ chúng sang cấu trúc dự án của bạn, giữ nguyên nguyên tắc: event là contract được công bố, listener thuộc module tiêu thụ và mỗi module sở hữu dữ liệu của mình.

## Chuẩn bị cấu trúc module

Giả sử ứng dụng có hai module:

- Orders sở hữu đơn hàng và quyết định khi nào đơn hàng được xác nhận.
- Fulfillment nhận thông tin đơn hàng đã xác nhận và tạo yêu cầu xử lý giao hàng.

Một cấu trúc package minh họa:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   ├── OrderConfirmationService.java
│   ├── OrderRepository.java
│   └── OrderConfirmed.java
└── fulfillment
    ├── FulfillmentRequest.java
    ├── FulfillmentRequestRepository.java
    ├── FulfillmentService.java
    └── OrderConfirmedListener.java
~~~

Trong Spring Modulith, package cấp cao nhất thường đại diện cho module. Các package con thuộc module tương ứng, trừ khi kiến trúc ứng dụng khai báo cấu trúc khác.

Orders công bố kiểu event mà module khác được phép sử dụng. Fulfillment phụ thuộc vào contract được công bố đó; nó không truy cập repository hoặc entity nội bộ của Orders.

Trước khi viết listener, xác định rõ:

- Event nào biểu diễn thay đổi nghiệp vụ đã hoàn tất?
- Module nào sở hữu event contract?
- Module nào nhận event?
- Side effect của listener thuộc dữ liệu module nào?
- Listener cần xử lý sau commit hay có thể chạy đồng bộ?

## Bước 1: Tạo event contract trong Orders

Tạo một event bất biến để mô tả việc đơn hàng đã được xác nhận:

~~~java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Các field có ý nghĩa:

| Field | Ý nghĩa |
|---|---|
| eventId | Định danh duy nhất của lần phát sinh sự kiện, giữ ổn định qua retry và redelivery |
| orderId | Định danh đơn hàng được xác nhận |
| occurredAt | Thời điểm nghiệp vụ xác nhận đơn hàng xảy ra |

Event chỉ mang dữ liệu cần thiết để consumer hiểu sự kiện và thực hiện trách nhiệm của mình. Không truyền JPA entity hoặc toàn bộ object graph qua module boundary.

Nếu Fulfillment cần thêm thông tin để tạo yêu cầu, hãy quyết định rõ nên đưa snapshot nào vào event và thông tin nào được lấy qua public API. Không để listener truy cập trực tiếp repository nội bộ của Orders.

Event class cần được công bố ở package/API mà module tiêu thụ được phép phụ thuộc. Không đặt contract dùng chung trong package internal hoặc package implementation không được công bố.

## Bước 2: Phát event từ use case xác nhận đơn hàng

Publisher công bố event sau khi thay đổi trạng thái nghiệp vụ trong cùng transaction:

~~~java
package com.example.shop.orders;

import java.time.Clock;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderConfirmationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderConfirmationService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        var order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm(clock.instant());

        events.publishEvent(new OrderConfirmed(
            UUID.randomUUID(),
            orderId,
            clock.instant()
        ));
    }
}
~~~

Ví dụ giả định Order có method confirm và repository cung cấp findById. Trong code thực tế, nên lấy một thời điểm duy nhất từ Clock rồi dùng nhất quán cho cả thay đổi aggregate và event:

~~~java
Instant now = clock.instant();
order.confirm(now);

events.publishEvent(new OrderConfirmed(
    UUID.randomUUID(),
    orderId,
    now
));
~~~

Điểm quan trọng là publisher phát event trong transaction của use case. Spring Modulith có thể ghi nhận publication cho listener được quản lý và chỉ kích hoạt listener transaction-bound sau khi transaction phát event commit thành công.

Nếu transaction rollback, listener after-commit không được xử lý một thay đổi chưa commit. Không phát event từ một luồng không có transaction rồi mong listener after-commit hoạt động như khi publisher commit.

## Bước 3: Tạo dữ liệu mà Fulfillment sở hữu

Listener cần một side effect quan sát được. Trong bài này, Fulfillment tạo một fulfillment request theo orderId và ghi lại eventId để hỗ trợ idempotency.

Ví dụ bảng PostgreSQL:

~~~sql
CREATE TABLE fulfillment_request (
    event_id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_fulfillment_request_order
    ON fulfillment_request(order_id);
~~~

event_id là khóa chính để cùng một event không tạo hai request. Nếu nghiệp vụ quy định mỗi đơn hàng chỉ có một fulfillment request, có thể bổ sung unique constraint trên order_id. Chọn khóa duy nhất theo invariant thật của nghiệp vụ.

Tạo writer dùng insert-if-absent:

~~~java
package com.example.shop.fulfillment;

import java.sql.Timestamp;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class FulfillmentRequestWriter {

    private final JdbcTemplate jdbc;

    FulfillmentRequestWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    boolean insertIfAbsent(OrderConfirmed event) {
        int inserted = jdbc.update("""
            INSERT INTO fulfillment_request (
                event_id, order_id, requested_at
            )
            VALUES (?, ?, ?)
            ON CONFLICT (event_id) DO NOTHING
            """,
            event.eventId(),
            event.orderId(),
            Timestamp.from(event.occurredAt())
        );

        return inserted == 1;
    }
}
~~~

Đoạn SQL sử dụng cú pháp PostgreSQL ON CONFLICT. Nếu dự án dùng database khác, thay bằng cơ chế insert-if-absent hoặc upsert tương ứng. Điều cần giữ là tính duy nhất phải được bảo vệ ở database; kiểm tra exists rồi insert riêng rẽ không đủ chống race condition khi hai lần giao event chạy đồng thời.

## Bước 4: Viết service xử lý event

Service thuộc Fulfillment chịu trách nhiệm tạo request trong transaction của module:

~~~java
package com.example.shop.fulfillment;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class FulfillmentService {

    private final FulfillmentRequestWriter requests;

    FulfillmentService(FulfillmentRequestWriter requests) {
        this.requests = requests;
    }

    @Transactional
    public void handle(OrderConfirmed event) {
        boolean created = requests.insertIfAbsent(event);

        if (!created) {
            // Event đã được xử lý trước đó; không tạo side effect lần nữa.
            return;
        }

        // Thực hiện các thay đổi database thuộc Fulfillment
        // trong cùng transaction này.
    }
}
~~~

Không đưa logic nghiệp vụ dài vào method listener. Listener nên là adapter mỏng nhận event rồi chuyển cho application service của module sở hữu side effect.

Nếu tạo thêm bản ghi hoặc phát event tiếp theo, hãy thực hiện trong transaction phù hợp. Nếu cần gửi HTTP hoặc gọi hệ thống ngoài, không giữ transaction database mở trong lúc chờ network; cân nhắc outbox hoặc workflow có trạng thái riêng.

## Bước 5: Tạo listener bằng @ApplicationModuleListener

Tạo listener trong package Fulfillment:

~~~java
package com.example.shop.fulfillment;

import com.example.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmedListener {

    private final FulfillmentService fulfillment;

    OrderConfirmedListener(FulfillmentService fulfillment) {
        this.fulfillment = fulfillment;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        fulfillment.handle(event);
    }
}
~~~

@ApplicationModuleListener là annotation Spring Modulith dành cho listener module được xử lý sau commit và bất đồng bộ theo semantics của framework. Annotation kết hợp cơ chế transaction-bound event listener, async execution và transaction riêng cho việc xử lý listener.

Điều này tạo ra ranh giới rõ:

- Orders commit thay đổi đơn hàng.
- Listener chỉ được xử lý sau commit.
- Fulfillment xử lý trong transaction của chính nó.
- Lỗi listener không thể rollback transaction Orders đã commit.
- Publication được theo dõi theo listener khi Event Publication Registry được cấu hình.

Nếu ứng dụng chưa bật async processing theo cấu hình Spring, hãy xác nhận cấu hình @EnableAsync và executor phù hợp với phiên bản Spring/Spring Modulith đang dùng. Dùng executor có giới hạn thread và queue cho tải production; không tạo thread vô hạn khi listener chậm.

Nếu cần listener đồng bộ sau commit, có thể dùng @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT). Chọn cơ chế theo yêu cầu latency, isolation và khả năng phục hồi; không mặc định mọi listener đều cần bất đồng bộ.

## Bước 6: Kiểm tra module dependency

Fulfillment cần phụ thuộc vào contract OrderConfirmed được Orders công bố. Nó không nên phụ thuộc vào OrderRepository, entity nội bộ hoặc service implementation của Orders.

Kiểm tra các nguyên tắc:

- Event class nằm trong API được công bố.
- Fulfillment chỉ import kiểu contract cần thiết.
- Orders không cần biết OrderConfirmedListener tồn tại.
- Fulfillment sở hữu FulfillmentRequest và repository của nó.
- Không có dependency vòng giữa Orders và Fulfillment.

Spring Modulith có thể kiểm tra cấu trúc module qua ApplicationModules:

~~~java
class ModuleArchitectureTests {

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đây là kiểm tra kiến trúc; nó bổ sung cho test listener và không thay thế việc kiểm tra hành vi thực tế.

## Bước 7: Viết unit test cho listener

Unit test kiểm tra listener chuyển đúng event sang service:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderConfirmedListenerTests {

    @Mock
    FulfillmentService fulfillment;

    @InjectMocks
    OrderConfirmedListener listener;

    @Test
    void delegatesEventToFulfillmentService() {
        var event = new OrderConfirmed(
            UUID.randomUUID(),
            UUID.randomUUID(),
            Instant.parse("2026-11-25T10:00:00Z")
        );

        listener.on(event);

        verify(fulfillment).handle(event);
    }
}
~~~

Unit test không cần khởi tạo ApplicationContext hoặc broker. Nó xác nhận trách nhiệm của adapter listener. Việc Spring có đăng ký listener đúng và transaction phase hoạt động cần integration test riêng.

## Bước 8: Viết integration test cho publisher và listener

Dùng ApplicationContext thật để xác nhận Orders phát event và Fulfillment tạo request. Ví dụ:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrderConfirmationListenerIntegrationTests {

    @Autowired
    OrderConfirmationService confirmation;

    @Autowired
    FulfillmentRequestRepository requests;

    @Test
    void createsFulfillmentRequestAfterOrderCommit() {
        UUID orderId = createPendingOrder();

        confirmation.confirm(orderId);

        await()
            .atMost(Duration.ofSeconds(10))
            .untilAsserted(() ->
                assertThat(requests.findByOrderId(orderId))
                    .isPresent()
            );
    }
}
~~~

Ví dụ dùng Awaitility để chờ listener bất đồng bộ hoàn tất. createPendingOrder và repository query là fixture/API của dự án, cần được triển khai theo mô hình dữ liệu thực tế.

Không gắn @Transactional lên test method trong ví dụ này nếu điều đó khiến transaction test bên ngoài chưa commit. Transaction của confirmation service cần kết thúc và commit trước khi listener after-commit được kích hoạt.

Test phải xác nhận side effect đã commit, không chỉ xác nhận publishEvent đã được gọi hoặc listener method đã bắt đầu chạy.

## Bước 9: Kiểm thử rollback và duplicate delivery

Hai tình huống cần được kiểm tra trước khi đưa listener vào production.

### Publisher rollback

Khi transaction Orders rollback:

- Trạng thái đơn hàng không được commit.
- Listener after-commit không tạo fulfillment request.
- Không có side effect downstream tương ứng với đơn hàng chưa được xác nhận.

Dùng transaction integration test thật để kiểm tra rollback. Không chỉ mock repository ném exception vì điều đó không chứng minh transaction event listener được kích hoạt đúng phase.

### Duplicate delivery

Khi cùng OrderConfirmed được giao lại:

- eventId vẫn giữ nguyên.
- Fulfillment không tạo thêm request cho cùng event.
- Các side effect được bảo vệ bằng unique constraint hoặc idempotency key.
- Lần xử lý trùng được ghi nhận theo mức quan sát phù hợp.

Không giả định listener chỉ chạy một lần. Process có thể dừng sau khi database commit nhưng trước khi publication được ghi nhận hoàn tất. Registry hoặc broker có thể giao lại event để bảo đảm phục hồi.

## Bước 10: Hiểu lỗi listener và Event Publication Registry

Event Publication Registry theo dõi publication của application event tới các listener được quản lý. Với listener hoàn tất thành công, publication tương ứng được ghi nhận hoàn tất theo implementation. Nếu listener lỗi, publication có thể còn ở trạng thái incomplete để phục hồi.

Trong vận hành cần quan sát:

- Listener nào đang có publication pending.
- Tuổi publication lâu nhất.
- Số lần xử lý thất bại hoặc resubmit.
- Lỗi database hoặc dependency của Fulfillment.
- Số event bị deduplicate.
- Thời gian từ commit Orders tới khi Fulfillment hoàn tất.

Registry không phải event store tổng quát và không thay thế idempotency. Khả năng resubmit và retention phụ thuộc persistence implementation cùng phiên bản Spring Modulith. Dùng API chính thức được cung cấp; không sửa bảng registry nội bộ tùy tiện.

Nếu listener gọi API bên ngoài rồi thất bại trước khi publication hoàn tất, lần resubmit có thể gọi API lần nữa. Hãy dùng idempotency key ở hệ thống đích hoặc ghi một outbox/workflow record để quản lý side effect đó.

## Bước 11: Cấu hình và kiểm soát async execution

Listener bất đồng bộ cần executor được quản lý. Trong production, xem xét:

- Thread pool có giới hạn.
- Queue có giới hạn và chính sách từ chối task rõ ràng.
- Tên thread giúp nhận diện listener.
- Metrics về active thread, queue depth và task rejection.
- Graceful shutdown để xử lý task đang chạy.
- Transaction timeout phù hợp với thao tác database.
- Giới hạn concurrency theo connection pool và năng lực database.

Nếu listener chạy lâu, không tăng thread pool vô hạn. Queue tăng liên tục là dấu hiệu tốc độ event đến vượt năng lực xử lý; cần backpressure hoặc tăng capacity có kiểm soát.

Không dùng listener async để che giấu một công việc nặng không có giới hạn. Tách công việc thành workflow hoặc message ngoài ứng dụng khi yêu cầu scale và isolation thực sự cần thiết.

## Bước 12: Quan sát listener trong production

Gắn eventId và orderId vào structured log để nối publisher với listener. Không đưa các ID này thành metric label có cardinality cao.

Các metric hữu ích:

| Metric | Mục đích |
|---|---|
| fulfillment_listener_duration | Thời gian xử lý listener |
| fulfillment_listener_success_total | Số lần xử lý thành công |
| fulfillment_listener_failure_total | Số lần xử lý thất bại |
| fulfillment_event_duplicate_total | Số event bị bỏ qua do đã xử lý |
| event_publication_pending | Số publication chưa hoàn tất |
| event_publication_oldest_age | Tuổi publication pending lâu nhất |
| async_executor_queue_size | Số task đang chờ executor |

Trace nên nối được command xác nhận đơn hàng, transaction commit và listener xử lý. Nếu event đi qua nhiều tiến trình, truyền trace context qua message header theo chuẩn observability của hệ thống.

Không log toàn bộ payload nếu event có dữ liệu nhạy cảm. Chỉ ghi field cần điều tra và tuân theo chính sách bảo vệ dữ liệu.

## Những lỗi thường gặp khi tạo listener

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Listener đặt sai package hoặc không được scan | Event không có consumer | Kiểm tra module package và bean registration |
| Event class không được công bố | Module khác không thể phụ thuộc đúng contract | Đặt event trong API package được công bố |
| Publish ngoài transaction | Listener after-commit không được kích hoạt như mong đợi | Phát event trong transaction nghiệp vụ |
| Dùng listener thường nhưng kỳ vọng after-commit | Listener có thể chạy trước commit | Dùng transaction-bound listener |
| Test bọc transaction rồi rollback cuối test | Listener after-commit không chạy | Để publisher transaction commit thật |
| Listener có side effect không idempotent | Duplicate delivery tạo dữ liệu trùng | Unique constraint, inbox hoặc idempotency key |
| Listener gọi HTTP khi đang giữ DB transaction | Transaction kéo dài và giữ connection | Dùng outbox/workflow cho external side effect |
| Không quan sát publication pending | Lỗi listener tồn tại lâu mà không được phát hiện | Metric, alert và runbook phục hồi |

## Kết quả cần đạt

Sau khi hoàn thành bài thực hành, bạn cần có:

- Event OrderConfirmed bất biến được Orders công bố.
- Publisher phát event trong transaction xác nhận đơn hàng.
- Listener OrderConfirmedListener thuộc module Fulfillment.
- Listener được xử lý sau commit theo cấu hình Spring Modulith.
- FulfillmentService tạo request trong transaction riêng.
- Database bảo vệ idempotency cho event được giao lại.
- Unit test xác nhận listener delegate đúng event.
- Integration test xác nhận side effect sau commit.
- Test rollback và duplicate delivery.
- Quan sát được listener failure và publication pending.

## Bài tập mở rộng

1. Thêm listener thứ hai trong module Notification để tạo notification request nội bộ.
2. Viết test chứng minh cả hai listener nhận cùng event và side effect độc lập.
3. Làm listener Fulfillment thất bại tạm thời, sau đó resubmit publication theo API Spring Modulith của phiên bản dự án.
4. Thêm metric cho processing duration và publication pending age.
5. Thử gửi cùng event hai lần và xác nhận chỉ có một fulfillment request.
6. Externalize OrderConfirmed sang broker trong một bài riêng; giữ nguyên event contract và bổ sung broker integration test.

## Tài liệu tham khảo

- Spring Modulith Reference — Application Events: https://docs.spring.io/spring-modulith/reference/events.html
- Spring Modulith Reference — Testing Application Modules: https://docs.spring.io/spring-modulith/reference/testing.html
- Spring Framework Reference — Application Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring JDBC Reference: https://docs.spring.io/spring-framework/reference/data-access/jdbc.html
