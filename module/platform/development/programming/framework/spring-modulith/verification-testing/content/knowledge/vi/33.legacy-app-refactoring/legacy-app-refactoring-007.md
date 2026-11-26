# Chuyển gọi trực tiếp thành event khi có lý do

> **Chương:** Refactoring an existing app  
> **Module đào tạo:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Mục tiêu:** Quyết định **khi nào** nên thay một lời gọi Java đồng bộ giữa hai phần của ứng dụng legacy bằng Spring Modulith application event, thực hiện chuyển đổi có kiểm soát và **thu bằng chứng bằng Java/JUnit** rằng ranh giới module, transaction, side effect, rollback và khả năng phục hồi vẫn đúng.  
> **Bối cảnh:** Module `orders` gọi trực tiếp `notifications` sau khi tạo đơn hàng. Ta chỉ chuyển thành event khi gửi thông báo **không thuộc điều kiện chấp nhận đơn hàng**; những bất biến phải hoàn tất ngay vẫn cần hợp đồng đồng bộ rõ ràng.

## 1. Quyết định trước khi refactor: phụ thuộc thời gian hay phụ thuộc nghiệp vụ?

**“Giảm coupling” không phải lý do đầy đủ để chuyển mọi method call thành event.** Hai module có thể phụ thuộc nhau hợp lệ qua public API, trong khi event bất đồng bộ làm thay đổi thời điểm hoàn tất, lỗi trả về caller và cả mô hình nhất quán dữ liệu.

Giả sử legacy use case:

~~~text
POST /orders
  -> orders.OrderService.place(...)
     -> lưu order
     -> notifications.NotificationService.sendConfirmation(orderId)
     -> trả HTTP 201
~~~

Cần hỏi:

1. **Điều kiện thành công:** Nếu email chưa gửi, order có vẫn hợp lệ để trả `201 Created` không?
2. **Failure isolation:** Provider email bị lỗi có nên rollback order đã đủ điều kiện đặt không?
3. **Nhất quán:** Consumer cần đọc order *sau commit* hay cần tham gia quyết định tức thời?
4. **Hợp đồng khách hàng:** API có hứa email đã gửi trước khi return? Nếu có, chuyển sang event là **thay đổi observable contract**, không chỉ refactor nội bộ.
5. **Độ tin cậy:** Có nhu cầu durable publication, retry, idempotency và backlog monitoring không?

| Tình huống | Nên chọn | Vì sao |
| --- | --- | --- |
| Inventory reservation là điều kiện để chấp nhận order | Public command đồng bộ hoặc workflow xác nhận kết quả | Caller phải biết kết quả trước khi chấp nhận |
| Payment authorization bắt buộc thành công ngay | Đồng bộ hoặc orchestrated PENDING flow | Không thể gọi “đã thanh toán” chỉ vì event đã phát |
| Audit record **phải nguyên tử** với order trong cùng DB | Ghi trong T1 với transaction guarantee | Eventual consumer có thể fail sau commit |
| Đưa xác nhận email vào hàng đợi | Event hậu commit | Email lỗi không làm order không hợp lệ |
| Cập nhật read model/report có thể chậm | Event với eventual consistency | Có thể retry và idempotency |
| Tính giá cần trả trong HTTP response | Synchronous service | Response phụ thuộc ngay kết quả |
| Nhiều consumer quan tâm một sự kiện đã xảy ra | Public application event | Producer không điều phối từng handler |

~~~mermaid
flowchart TD
    A["Lời gọi trực tiếp giữa modules"] --> B{"Caller cần kết quả ngay cho invariant?"}
    B -- "Có" --> C["Giữ synchronous command"]
    B -- "Không" --> D{"Business cho phép eventual outcome?"}
    D -- "Không" --> C
    D -- "Có" --> E{"Có policy retry, duplicate, failure?"}
    E -- "Chưa" --> F["Thiết kế reliability trước"]
    E -- "Có" --> G["Cân nhắc event hậu commit"]
    G --> T["Contract tests + integration + CI"]
~~~

**Phạm vi bài:** `OrderPlaced` là fact “order đã được chấp nhận”. Notification chỉ cần **eventually queued**, có thể được gửi sau. Nếu nghiệp vụ yêu cầu email được gửi thành công ngay, **không áp dụng** refactor này mà chưa thống nhất lại hợp đồng.

## 2. Đọc đúng hợp đồng legacy trước khi tháo direct call

Ví dụ code cũ:

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class LegacyOrderService {

    private final LegacyOrderRepository orders;
    private final NotificationGateway notifications;

    LegacyOrderService(
            LegacyOrderRepository orders,
            NotificationGateway notifications) {
        this.orders = orders;
        this.notifications = notifications;
    }

    @Transactional
    public UUID place(String customerRef) {
        UUID id = UUID.randomUUID();
        orders.save(new LegacyOrder(id, customerRef));

        // Direct call vào notifications/provider.
        notifications.sendConfirmation(id);
        return id;
    }
}
~~~

`LegacyOrderRepository`, `LegacyOrder` và `NotificationGateway` là các cộng tác viên của **biến thể trước-refactor**, không phải class cần lưu chung với bản mới.

| Câu hỏi | Legacy behavior có thể là |
| --- | --- |
| Provider ném unchecked exception | T1 order rollback nếu lỗi đi qua transaction proxy |
| Provider đã gửi email nhưng T1 commit fail | Có email cho order không tồn tại; external side effect không rollback |
| Method `place` trả về khi nào | Sau khi provider call return, không chắc email tới inbox |
| Chi phí | External latency nằm trong critical path và giữ transaction resources |
| Module boundary | `orders` phụ thuộc `notifications` hoặc một port liên quan |
| Có vi phạm `ApplicationModules.verify()` chưa? | **Chưa chắc**: direct public API call có thể đúng kiến trúc |

**Có method call đồng bộ không đồng nghĩa sai kiến trúc.** Động lực chuyển đổi phải dựa trên failure isolation, fan-out hoặc consistency/lifecycle requirement.

### Characterization tests cần ghi nhận

- Order input hợp lệ tạo đúng dữ liệu.
- Input sai không gửi thông báo.
- Notification call xảy ra đúng số lần theo contract cũ.
- Khi gateway lỗi, caller có nhận lỗi? Order rollback hay vẫn lưu?
- Payment/inventory vẫn là quyết định đồng bộ, không vô tình chuyển sang eventual.
- Có bên nào đang dựa vào việc email call kết thúc trước `place(...)` return?

Unit interaction test minh họa:

~~~java
@Test
void legacy_calls_notification_once() {
    var repository = mock(LegacyOrderRepository.class);
    var gateway = mock(NotificationGateway.class);
    var service = new LegacyOrderService(repository, gateway);

    UUID id = service.place("CUS-7");

    verify(repository).save(any(LegacyOrder.class));
    verify(gateway).sendConfirmation(id);
    verifyNoMoreInteractions(gateway);
}
~~~

Cần imports JUnit/Mockito. Service được tạo bằng `new` **không kích hoạt Spring `@Transactional`**; test trên chỉ bảo vệ interaction, không xác minh rollback. Transaction behavior cũ phải được kiểm tra bằng một integration test có Spring proxy và DB thật.

### Sự thay đổi contract phải được công khai

Trước refactor:

~~~text
place(...) success
  => notification provider call đã return
~~~

Sau refactor:

~~~text
place(...) success
  => T1 order commit thành công
  => event được phát theo cơ chế đang cấu hình
  => notification eventually QUEUED theo reliability contract
~~~

Đây **không phải hợp đồng giống hệt**. Cần đồng thuận acceptance criteria: khi nào client thấy order accepted, thời hạn notification queued/sent, cách đo backlog và failure.

## 3. Chọn event fact công khai, tránh biến event thành RPC trá hình

**`src/main/java/com/example/shop/orders/OrderPlaced.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

`OrderPlaced` là **fact của orders**. `SendConfirmationEmail` lại là command hướng tới consumer cụ thể; nếu đó là ý đồ thật, một public command/service có thể rõ hơn.

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderCommands.java
│   ├── OrderPlaced.java
│   └── internal/
│       ├── OrderApplicationService.java
│       ├── OrderEntity.java
│       └── OrderRepository.java
└── notifications/
    ├── NotificationQueries.java
    ├── NotificationState.java
    └── internal/
        ├── OrderPlacedListener.java
        ├── NotificationJobWriter.java
        └── NotificationQueryService.java
~~~

Dependency Java sau refactor là `notifications → orders.OrderPlaced`; direction nghiệp vụ là `orders phát event, notifications nhận`. `orders` không cần import `notifications` hay entity/repository internal của consumer.

**`src/main/java/com/example/shop/orders/OrderCommands.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public interface OrderCommands {
    UUID place(String customerRef);
}
~~~

**`src/main/java/com/example/shop/orders/internal/OrderEntity.java`**

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_orders")
class OrderEntity {

    @Id
    private UUID id;

    @Column(name = "customer_ref", nullable = false)
    private String customerRef;

    protected OrderEntity() {}

    OrderEntity(UUID id, String customerRef) {
        this.id = id;
        this.customerRef = customerRef;
    }
}
~~~

**`src/main/java/com/example/shop/orders/internal/OrderRepository.java`**

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {}
~~~

**`src/main/java/com/example/shop/orders/internal/OrderApplicationService.java`**

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.orders.OrderCommands;
import com.example.shop.orders.OrderPlaced;

@Service
class OrderApplicationService implements OrderCommands {

    private final OrderRepository repository;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            OrderRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Override
    @Transactional
    public UUID place(String customerRef) {
        if (customerRef == null || customerRef.isBlank()) {
            throw new IllegalArgumentException(
                    "customerRef must not be blank");
        }

        UUID id = UUID.randomUUID();
        repository.save(new OrderEntity(id, customerRef));

        events.publishEvent(new OrderPlaced(id));
        return id;
    }
}
~~~

`publishEvent` được gọi **trong T1**, chưa phải lúc T1 commit. Khi gọi service qua Spring transaction proxy và không có outer transaction, interceptor xử lý commit trước khi call hoàn tất thành công; listener hậu commit có thể còn chạy. Đừng sửa bằng cách catch lỗi từ direct notification call rồi bỏ qua: như vậy không loại bỏ coupling.

### Quy tắc event contract

| Cần quyết định | Hướng hợp lý |
| --- | --- |
| Payload chứa JPA entity? | Không; chỉ DTO/record public |
| Payload chứa email/PII? | Ưu tiên ID hoặc dữ liệu tối thiểu; review privacy/retention |
| Consumer cần snapshot tại thời điểm phát? | Dùng immutable snapshot/version khi contract thực sự yêu cầu |
| Consumer import `orders.internal`? | Không; dùng public event/queries |
| Event có thể đi ra broker? | Thiết kế versioning/schema compatibility và durability |
| Fan-out nhiều consumers? | Mỗi consumer độc lập, không dựa vào thứ tự ngẫu nhiên |
| Thay tên/ý nghĩa event? | Consumer contract tests và migration plan |

## 4. Listener hậu commit ghi work item bền và tránh giữ T2 qua provider call

Mục tiêu sau chuyển đổi: **T1 chấp nhận order**, **T2 ghi thông báo chờ xử lý**, **worker gửi email riêng**.

~~~mermaid
sequenceDiagram
    participant API as Caller
    participant O as orders T1
    participant E as Spring events
    participant N as notifications T2
    participant DB as Database
    participant W as Notification worker

    API->>O: place(customerRef)
    O->>DB: INSERT customer_orders
    O->>E: publish OrderPlaced(id)
    O->>DB: COMMIT T1
    O-->>API: orderId
    E-->>N: @ApplicationModuleListener AFTER_COMMIT
    N->>DB: INSERT QUEUED if absent
    N->>DB: COMMIT T2
    W->>DB: Claim QUEUED
    W->>W: Send with stable idempotency key
    W->>DB: Short transaction mark SENT/FAILED
~~~

`@ApplicationModuleListener` trong các bản Spring Modulith tương thích thường là listener hậu commit, async và transaction mới. **Không đánh đồng** với `@Async @EventListener` có thể chạy trước T1 commit.

### Schema PostgreSQL minh họa

Một migration tương đương `src/main/resources/db/migration/V1__orders_notifications.sql`:

~~~sql
CREATE TABLE customer_orders (
    id UUID PRIMARY KEY,
    customer_ref VARCHAR(120) NOT NULL
);

CREATE TABLE notification_jobs (
    order_id UUID PRIMARY KEY,
    state VARCHAR(24) NOT NULL
        CHECK (state IN ('QUEUED', 'SENT', 'FAILED'))
);
~~~

Hệ thống legacy có migration thật thì tạo **migration version tiếp theo**, không ghi đè V1/schema cũ. Không bắt buộc FK xuyên module; nếu dùng, đánh giá coupling vật lý.

**`src/main/java/com/example/shop/notifications/NotificationState.java`**

~~~java
package com.example.shop.notifications;

public enum NotificationState {
    NOT_QUEUED,
    QUEUED,
    SENT,
    FAILED
}
~~~

**`src/main/java/com/example/shop/notifications/NotificationQueries.java`**

~~~java
package com.example.shop.notifications;

import java.util.UUID;

public interface NotificationQueries {
    NotificationState stateOf(UUID orderId);
}
~~~

**`src/main/java/com/example/shop/notifications/internal/NotificationJobWriter.java`**

~~~java
package com.example.shop.notifications.internal;

import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
class NotificationJobWriter {

    private final JdbcTemplate jdbc;

    NotificationJobWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    void queueIfAbsent(UUID id) {
        jdbc.update("""
                INSERT INTO notification_jobs(order_id, state)
                VALUES (?, 'QUEUED')
                ON CONFLICT (order_id) DO NOTHING
                """, id);
    }
}
~~~

`ON CONFLICT` là cú pháp **PostgreSQL**, không copy nguyên sang MySQL/SQL Server/Oracle. Unique primary key tạo invariant **một work item cho một order ID** ngay cả khi listener nhận duplicate.

**`src/main/java/com/example/shop/notifications/internal/OrderPlacedListener.java`**

~~~java
package com.example.shop.notifications.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;

@Component
class OrderPlacedListener {

    private final NotificationJobWriter writer;

    OrderPlacedListener(NotificationJobWriter writer) {
        this.writer = writer;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        writer.queueIfAbsent(event.orderId());
    }
}
~~~

**`src/main/java/com/example/shop/notifications/internal/NotificationQueryService.java`**

~~~java
package com.example.shop.notifications.internal;

import java.util.List;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.notifications.NotificationQueries;
import com.example.shop.notifications.NotificationState;

@Service
class NotificationQueryService implements NotificationQueries {

    private final JdbcTemplate jdbc;

    NotificationQueryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional(readOnly = true)
    public NotificationState stateOf(UUID id) {
        List<NotificationState> rows = jdbc.query(
                """
                SELECT state FROM notification_jobs
                WHERE order_id = ?
                """,
                (rs, rowNum) -> NotificationState.valueOf(
                        rs.getString("state")),
                id);

        return rows.isEmpty()
                ? NotificationState.NOT_QUEUED
                : rows.get(0);
    }
}
~~~

### Giới hạn chính xác của bước event ingress

- Listener ghi `QUEUED` trong T2, **không** bảo đảm email đã `SENT`.
- Worker có retry/dead-letter/`FAILED` riêng. Không giữ T2 mở qua provider I/O dài.
- `queueIfAbsent` failure nên propagate để T2 rollback; nếu có persistent Event Publication Registry, adapter có thể theo dõi publication chưa completed. Không catch rồi nuốt lỗi.
- `JdbcTemplate` tham gia transaction-bound connection khi Spring cấu hình đúng; nhưng `writer.queueIfAbsent(...)` return **không chứng minh T2 commit**. Test dùng fresh public read `QUEUED`.
- Unique DB row không ngăn provider gửi cùng email hai lần nếu response thất lạc; cần idempotency key hoặc reconciliation ở worker.

**Phần code chỉ mô tả giai đoạn order → QUEUED.** Tạo `SENT`/`FAILED` và provider adapter là workflow tiếp theo; test đúng của bài này chờ `QUEUED`, không tuyên bố đã giao email.

## 5. Lộ trình refactor an toàn: đổi contract có kiểm soát, không tạo hai side effects

Chuyển một call thành event không nên là thao tác “đổi một dòng code” trong một đợt deploy thiếu quan sát. Một lộ trình có thể kiểm chứng:

| Bước | Thay đổi | Điều kiện để đi tiếp |
| --- | --- | --- |
| 1. Characterize | Ghi contract cũ: response, transaction, notification error behavior | Legacy behavior/failure được ghi bằng tests |
| 2. Chốt business semantics | Cho phép notification eventual hay không; SLA thế nào | Product/API stakeholders chấp nhận |
| 3. Dựng consumer capability | Tạo public event, bảng `notification_jobs`, listener và public query | Writer idempotent; consumer IT hoạt động |
| 4. Dựng reliability | Registry/outbox nếu yêu cầu, retry worker, metrics/alerts | Failure/recovery path có test |
| 5. Cut over | Bỏ direct call, phát event trong T1 | Producer test và full integration xanh |
| 6. Observe | Kiểm tra accepted orders, queued lag, failure backlog, duplicate effects | Không vi phạm SLO/invariant |
| 7. Retire | Xóa dependency legacy, config và route cũ khi an toàn | Architecture gate chặn việc gọi trực tiếp quay lại |

### Diff thể hiện ranh giới mới

~~~diff
 class OrderApplicationService {

-    private final NotificationGateway notifications;
+    private final ApplicationEventPublisher events;

     @Transactional
     public UUID place(String customerRef) {
         UUID id = UUID.randomUUID();
         repository.save(new OrderEntity(id, customerRef));

-        notifications.sendConfirmation(id);
+        events.publishEvent(new OrderPlaced(id));

         return id;
     }
 }
~~~

**Không phát event đồng thời vẫn gọi `sendConfirmation(id)` cho cùng mục đích** trong phase cutover thông thường. Nếu hai đường cùng chạy, mỗi đường có thể gửi email, và test đơn giản chỉ assert `QUEUED` sẽ không bắt duplicate external effect.

### Shadow traffic phải vô hại

Nếu cần so sánh số liệu trước/sau:

- Giữ direct path active và chỉ ghi **shadow event vào observer không tạo email**; hoặc
- Ghi business decision/outbox intent thụ động rồi kiểm tra payload/lag mà **không chạy side effect hai lần**; hoặc
- Dùng feature flag chọn **một** path thực thi cho một order, có idempotency key ổn định và rõ policy với in-flight orders.

Không âm thầm bật cả hai listeners cho cùng loại event rồi kỳ vọng provider sẽ tự dedupe. Nếu có email đã được gửi trước cutover và các old events được replay, phải định nghĩa rule không gửi lại, hoặc stable idempotency key.

### Data migration và tương thích rolling deploy

Đối với ứng dụng đang có traffic:

1. Triển khai schema consumer theo phương pháp **expand-before-switch** (không phá code old version).
2. Triển khai listener/worker mới nhưng chưa đồng thời tạo external side effect với old path; dùng feature toggle/safe routing có kiểm chứng.
3. Kiểm tra dữ liệu events phát ở giai đoạn rolling deploy có schema tương thích; nếu bắt buộc replay historical event, version payload và dedupe theo ID.
4. Switch producer từ direct call sang publish fact, vẫn giữ metrics so sánh.
5. Chỉ xóa old interface/class/config sau khi không còn phiên bản cũ phụ thuộc và backlog đã được xử lý đúng policy.

**Rollback deploy không tự rollback một event đã publish**. Với event đã được nhận/queue, cần biết worker mới còn chạy không, idempotency key còn hợp lệ không và rollback code cũ có tạo side effect trùng hay không.

### Transactional outbox hay registry?

Nếu yêu cầu **bền qua crash**, chỉ `ApplicationEventPublisher.publishEvent(...)` trong JVM **không đủ để tự kết luận** delivery durable qua mọi failure window. Spring Modulith Event Publication Registry kết hợp persistence adapter có thể theo dõi incomplete publications, nhưng bảo đảm transaction coupling, completion và resubmission phụ thuộc cấu hình/version. Outbox hoặc queue broker là các lựa chọn kiến trúc khác có cost riêng.

**Điều kiện để chuyển đổi:** Có câu trả lời rõ cho trường hợp “T1 commit, process crash trước khi notification QUEUED”; nếu business đòi bảo đảm không mất notification, phải có persistent event intent/recovery strategy và bài kiểm tra failure path, không chỉ happy path.

## 6. @ApplicationModuleTest: kiểm tra đúng lời hứa của producer

Đặt test trong package `com.example.shop.orders` để slice Spring Modulith có thể bootstrap module producer đúng phạm vi.

**`src/test/java/com/example/shop/orders/OrderPublicationTest.java`**

~~~java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrderPublicationTest {

    @Autowired
    OrderCommands orders;

    @Test
    void publishes_order_placed_with_same_id(
            PublishedEvents publishedEvents) {

        UUID id = orders.place("CUSTOMER-42");

        assertThat(publishedEvents.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }

    @Test
    void rejects_invalid_command_without_publication(
            PublishedEvents publishedEvents) {

        assertThatThrownBy(() -> orders.place("  "))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(publishedEvents.ofType(OrderPlaced.class))
                .isEmpty();
    }
}
~~~

### Đây là một contract test, không phải proof email đã được gửi

- `PublishedEvents` cho thấy producer đã **publish** event có type/payload đúng.
- `anySatisfy` chỉ cần **ít nhất một** event thỏa điều kiện; nó **không** chứng minh exactly-once publication. Nếu yêu cầu đúng một event, kiểm tra số event phù hợp theo API collection của Spring Modulith version đang dùng.
- Event được publish **trong T1**; `PublishedEvents` không chứng minh consumer `AFTER_COMMIT` chạy, T2 commit, provider gửi email hay registry durable.
- `@ApplicationModuleTest` producer-only không nhất thiết bootstrap `notifications`. Không chờ `NotificationState.QUEUED` trong module slice thiếu consumer.
- Nếu producer persistence cần JPA/transaction manager, test phải có datasource/schema tương thích; dùng test profile, migrations hoặc Testcontainers. Annotation không tự sinh schema.

### Regression cases khi bỏ direct call

Một test characterization cũ có `verify(notificationGateway).sendConfirmation(id)` **không còn là acceptance criterion** sau khi product đã chấp nhận event contract. Thay vì xóa tất cả evidence, chuyển nó thành hai mệnh đề:

1. Producer **không còn phụ thuộc/không gọi** module notifications (arch gate ở mục 9).
2. Producer **phát đúng `OrderPlaced`** (module test ở trên).

Test thứ ba, ở mức integration, chứng minh notifications **tự phản ứng** với event đã commit và tạo work item. Ba mệnh đề kiểm soát cả **mối phụ thuộc** lẫn **hành vi** mà direct call từng bảo đảm.

### Mutation control

- Bỏ `events.publishEvent(...)`: `publishes_order_placed_with_same_id` phải đỏ.
- Phát event với UUID mới thay vì `id`: assertion payload phải đỏ.
- Bỏ validation input: test invalid command phải đỏ.
- Chỉ thay consumer listener mà producer test vẫn xanh: bình thường, vì không thuộc phạm vi test này.

Không dùng producer test xanh để suy luận việc listener được khởi tạo/đăng ký ở application context.

## 7. SpringBootTest + PostgreSQL: chứng minh after-commit, rollback và trạng thái đã commit

Integration test là nơi kiểm tra **điều quan trọng nhất khi refactor**: order được commit **không cần đợi email provider**, nhưng notification work item được tạo sau commit và nhìn thấy qua public module API.

Giả định migration SQL ở mục 4 có mặt, Flyway được bật và Spring Boot/JPA đang dùng PostgreSQL. Với Spring Boot 3.1+ có thể dùng `@ServiceConnection` để nối Testcontainers vào ứng dụng test.

**`src/test/java/com/example/shop/OrderNotificationFlowIT.java`**

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import com.example.shop.orders.OrderCommands;
import com.example.shop.orders.OrderPlaced;
import com.example.shop.notifications.NotificationQueries;
import com.example.shop.notifications.NotificationState;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "spring.jpa.hibernate.ddl-auto=validate")
@Import(OrderNotificationFlowIT.PhaseProbeConfig.class)
class OrderNotificationFlowIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    OrderCommands orders;

    @Autowired
    NotificationQueries notifications;

    @Autowired
    TransactionTemplate transactions;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    RollbackProbe rollbackProbe;

    @Test
    void accepted_order_eventually_has_queued_notification() {
        UUID id = orders.place("CUS-" + UUID.randomUUID());

        assertThat(committedOrderCount(id)).isEqualTo(1);

        await()
                .alias("notification QUEUED for order " + id)
                .atMost(Duration.ofSeconds(8))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() ->
                        assertThat(notifications.stateOf(id))
                                .isEqualTo(NotificationState.QUEUED));

        assertThat(queuedJobCount(id)).isEqualTo(1);

        // QUEUED != SENT. Email provider là workflow riêng.
    }

    @Test
    void rolled_back_order_must_not_queue_after_commit_listener() {
        UUID id = transactions.execute(status -> {
            UUID created = orders.place("CUS-ROLLBACK-"
                    + UUID.randomUUID());

            // OrderCommands.place dùng REQUIRED mặc định,
            // nên có thể tham gia outer T1 này.
            status.setRollbackOnly();
            return created;
        });

        assertThat(id).isNotNull();
        assertThat(committedOrderCount(id)).isZero();

        // AFTER_ROLLBACK probe chạy theo transaction phase.
        assertThat(rollbackProbe.wasRolledBack(id)).isTrue();

        // Đây là bounded negative observation window,
        // KHÔNG chứng minh "không bao giờ" cho mọi handler sai.
        await()
                .during(Duration.ofMillis(300))
                .atMost(Duration.ofSeconds(2))
                .until(() ->
                        notifications.stateOf(id)
                                == NotificationState.NOT_QUEUED);
    }

    private int committedOrderCount(UUID id) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer_orders WHERE id = ?",
                Integer.class, id);
    }

    private int queuedJobCount(UUID id) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM notification_jobs WHERE order_id = ?",
                Integer.class, id);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class PhaseProbeConfig {

        @Bean
        RollbackProbe rollbackProbe() {
            return new RollbackProbe();
        }
    }

    static class RollbackProbe {

        private final Set<UUID> rolledBack =
                ConcurrentHashMap.newKeySet();

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_ROLLBACK)
        public void on(OrderPlaced event) {
            rolledBack.add(event.orderId());
        }

        boolean wasRolledBack(UUID id) {
            return rolledBack.contains(id);
        }
    }
}
~~~

### Giải thích chính xác từng oracle

| Bằng chứng | Có thể khẳng định | Không được khẳng định |
| --- | --- | --- |
| `orders.place` return và `committedOrderCount(id)==1` | T1 đã ghi/commit order | Consumer T2 đã chạy |
| `NotificationState.QUEUED` qua fresh read | T2 tạo work item đã visible | Email provider đã gửi |
| `queuedJobCount(id)==1` | Đúng một row có key `order_id` | External effect chỉ diễn ra một lần |
| `RollbackProbe.wasRolledBack(id)` | Event đi qua phase AFTER_ROLLBACK trong test | Mọi adapter không thể có ghost event |
| `committedOrderCount(id)==0` sau rollback | Order không commit | Một faulty listener không thể dispatch sai |
| `during(300ms)` absence | Không thấy job trong observation window | “Không bao giờ” trong mọi lịch chạy |

Rollback `@TransactionalEventListener` là một **test phase probe** chỉ kiểm tra callback do test đăng ký; không thay thế kiểm chứng event infrastructure/registry thực. Để chứng minh tuyệt đối một faulty listener bị dispatch trước commit, cần thí nghiệm có controlled producer gate và test-only early-listener probe, không chỉ một assertion âm tức thời.

### Vì sao không đặt @Transactional trên JUnit test?

Nếu test method được Spring Test mở outer transaction rồi rollback khi method kết thúc, `OrderApplicationService.place(...)` có thể tham gia T0, khiến listener `AFTER_COMMIT` không chạy. Bài happy-path ở trên **không có outer test transaction**; bài rollback dùng `TransactionTemplate` một cách chủ đích.

### Khi setup integration phải để ý

- Cần Java 17+, Spring Boot 3.1+ cho `@ServiceConnection`, JUnit 5, PostgreSQL driver, Testcontainers PostgreSQL/Jupiter, Flyway và Spring Modulith artifacts tương thích.
- `spring.jpa.hibernate.ddl-auto=validate` yêu cầu migration/schema đã tồn tại. Schema SQL của mục 4 chỉ là mẫu; với legacy app phải viết migration đúng version của hệ thống.
- Spring TestContext cache có thể sống lâu hơn PostgreSQL class-scoped container ở một số cách tổ chức suite; đồng bộ lifecycle để tránh DataSource trỏ container đã stop.
- Test data dùng UUID riêng; không dùng `@AfterEach deleteAll()` khi background listener còn retry.
- `@ServiceConnection` gắn đúng container; Testcontainers startup có budget riêng so với Awaitility business wait.
- Không tắt Spring-managed executor từ `@AfterEach` để “dọn event”; điều đó có thể làm test khác bị `RejectedExecutionException`.

### Một phép thử không nên viết

~~~java
UUID id = orders.place("CUS-TEST");
assertThat(notifications.stateOf(id))
        .isEqualTo(NotificationState.QUEUED);
~~~

Listener async đúng vẫn có thể chưa xử lý khi query chạy. Đây là **false negative do test timing**, không phải minh chứng event bị mất. Dùng Awaitility bounded để đợi **business state đã commit**, không sleep cố định.

## 8. Failure/replay: event không tự bảo đảm exactly-once hay tránh mất dữ liệu

Chuyển sang event có thể **cải thiện failure isolation**, nhưng cũng chuyển một số lỗi từ request thread sang worker sau commit. Nếu không có cơ chế theo dõi, `201 Created` vẫn có thể đi kèm notification không bao giờ được queue.

### Các failure windows cần quyết định rõ

| Cửa sổ | Rủi ro | Bằng chứng kiểm thử |
| --- | --- | --- |
| T1 rollback sau publish | Listener sai pha hoặc broker nhận quá sớm tạo “ghost notification” | Rollback phase + committed DB + broker/outbox test |
| T1 commit, process crash trước listener | Notification không QUEUED nếu thiếu persistent publication/recovery | Restart/resubmit trên đúng adapter/version |
| Listener T2 lỗi khi INSERT | Job không commit, có thể còn incomplete publication | Exception, rollback T2, registry |
| Registry replay cùng OrderPlaced | Duplicate listener invocation | Writer idempotency + replay test |
| Queue worker gọi provider, response thất lạc | Có thể gửi email hai lần | Provider idempotency key/reconciliation |
| Event cũ replay khi job đã SENT | Không được reset SENT → QUEUED | Upsert test |
| Nhiều notification types trên một order | Key chỉ `order_id` có thể quá chặt | Key `(order_id, type, revision)` nếu business cần |

**Ba trạng thái khác nhau:** Event Publication Registry theo dõi việc giao event **tới listener**; `notification_jobs` theo dõi yêu cầu gửi thông báo; external provider có receipt riêng. Registry completed **không đồng nghĩa email SENT**, còn unique DB row **không chứng minh** provider chỉ gửi một lần.

### PostgreSQL writer test: duplicate không tạo job thứ hai

Đặt test trong `com.example.shop.notifications.internal` để truy cập writer package-private. Test này cần **cùng PostgreSQL schema/test profile** với integration ở mục 7. Nếu chạy độc lập, cấu hình `@ServiceConnection`/Testcontainers hoặc datasource PostgreSQL riêng; không dùng H2 rồi kỳ vọng `ON CONFLICT` giống production.

**`src/test/java/com/example/shop/notifications/internal/NotificationJobWriterIT.java`**

~~~java
package com.example.shop.notifications.internal;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class NotificationJobWriterIT {

    @Autowired
    NotificationJobWriter writer;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void duplicate_requests_create_one_job() {
        UUID id = UUID.randomUUID();

        writer.queueIfAbsent(id);
        writer.queueIfAbsent(id);

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM notification_jobs WHERE order_id = ?",
                Integer.class, id);

        assertThat(count).isEqualTo(1);
    }

    @Test
    void late_replay_does_not_reset_sent_job() {
        UUID id = UUID.randomUUID();

        writer.queueIfAbsent(id);
        jdbc.update(
                "UPDATE notification_jobs SET state='SENT' WHERE order_id=?",
                id);

        writer.queueIfAbsent(id);

        String state = jdbc.queryForObject(
                "SELECT state FROM notification_jobs WHERE order_id=?",
                String.class, id);

        assertThat(state).isEqualTo("SENT");
    }
}
~~~

**Mức bằng chứng:** Hai test chứng minh **writer + DB constraint/upsert** idempotent theo ID, chưa chứng minh listener được gọi đúng hai lần hay provider không gửi email trùng. Khi test event replay thật, cần chờ bằng chứng callback/recovery hoàn tất (probe hoặc registry theo adapter), không publish duplicate rồi query tức thời.

### Event Publication Registry và crash recovery

Spring Modulith Event Publication Registry với persistence adapter có thể theo dõi incomplete publications và hỗ trợ resubmit tùy version/cấu hình. Reliability test nên trả lời:

1. Publication được ghi durable và cùng transaction boundary nào với T1?
2. T1 rollback có để lại publication không hợp lệ trong storage không?
3. Listener lỗi có **rethrow**, hay bị catch/nuốt khiến registry tưởng thành công?
4. Publication nào pending ở target listener nào?
5. Resubmit/restart có tạo đúng `QUEUED`, không duplicate effect?
6. Retry/recovery budget có phù hợp deadline nghiệp vụ?

~~~java
// Pseudocode: điều chỉnh API theo đúng Spring Modulith
// version và registry adapter thực tế.
UUID id = publishOrderAndForceListenerFailure();

assertThat(publications.incompleteFor(id, "notifications"))
        .isTrue();

disableInjectedFailure();
recoveryTrigger.resubmitIncomplete();

await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            assertThat(notifications.stateOf(id))
                    .isEqualTo(NotificationState.QUEUED);

            assertThat(publications.incompleteFor(
                    id, "notifications")).isFalse();
        });
~~~

`publications.incompleteFor` và `recoveryTrigger.resubmitIncomplete` là **pseudocode interfaces**, không phải API chắc chắn có sẵn trong mọi Spring Modulith release. Không mặc định registry được cấu hình persistent, retry vô hạn, hoặc event delivery exactly once. Nếu ứng dụng chỉ publish in-process mà không có durable mechanism, phải ghi rõ **crash window chưa được bảo vệ**.

### External email idempotency khác unique queue row

~~~text
Attempt 1: send(key = "order-confirmation:" + orderId)
           provider thực sự gửi, HTTP response thất lạc
Attempt 2: send(same key)
           provider trả existing receipt nếu hỗ trợ
Local worker: mark SENT một lần
~~~

Nếu provider không hỗ trợ idempotency key, cần reconciliation/provider receipt, hoặc review mức chấp nhận duplicate external effect. **Không khẳng định một unique DB job loại trừ hai email**.

Khi email là nghĩa vụ bắt buộc và không thể mất sau crash, cần transactional outbox/work queue, retry và vận hành rõ ràng. **Nếu chưa có strategy bảo vệ failure windows này, dừng cutover có thể là quyết định kiến trúc đúng hơn chuyển sang event ngay.**

## 9. Architecture test và CI gate: chặn dependency sai lẫn hồi quy nghiệp vụ

Một integration test thấy `QUEUED` vẫn **chưa chứng minh** producer đã ngừng gọi `NotificationGateway`. Có thể direct path và event path cùng chạy, gây duplicate email mà test chỉ quan sát DB không phát hiện. Vì vậy, kiểm chứng **dependency** và **behavior** phải độc lập.

### ApplicationModules.verify() kiểm tra kiến trúc module

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void boundaries_are_valid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` giúp phát hiện dependency cycles, truy cập implementation ngoài public module API và allowed dependencies vi phạm nếu khai báo. **Nhưng** `orders → notifications` qua public API có thể vẫn hợp lệ theo cấu hình mặc định, nên nó **không đủ** chứng minh direct call đã bị loại bỏ.

### ArchUnit bảo vệ mục tiêu đặc thù của lần refactor

**`src/test/java/com/example/shop/NoDirectNotificationDependencyTest.java`**

~~~java
package com.example.shop;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import org.junit.jupiter.api.Test;
import com.tngtech.archunit.core.importer.ClassFileImporter;

class NoDirectNotificationDependencyTest {

    @Test
    void orders_does_not_depend_on_notifications() {
        var code = new ClassFileImporter()
                .importPackages("com.example.shop");

        noClasses()
                .that()
                .resideInAPackage("com.example.shop.orders..")
                .should()
                .dependOnClassesThat()
                .resideInAPackage("com.example.shop.notifications..")
                .check(code);
    }
}
~~~

Cần ArchUnit test dependency. Rule chặn **dependency tĩnh Java bytecode** từ producer tới consumer sau cutover; reflection/string-based lookups có thể không được phát hiện. Vì vậy vẫn cần producer contract và cross-module integration tests.

Nếu đang trong giai đoạn **chưa cutover**, rule này có thể đỏ do legacy direct dependency tồn tại. Đưa thành mandatory merge gate khi migration thực sự loại bỏ dependency, không để test cố tình đỏ vĩnh viễn.

### CI quality gate theo mệnh đề cụ thể

| Gate | Cần chứng minh | Lỗi bắt được |
| --- | --- | --- |
| Legacy characterization | Contract cũ đã được hiểu và thay đổi đã được chấp nhận | Thay response/rollback ngoài ý muốn |
| Business acceptance | Notification eventual là semantics được chấp nhận | Đưa điều kiện bắt buộc sang async |
| `ApplicationModules.verify()` | Module boundary/cycle hợp lệ | Truy cập `internal`, vòng phụ thuộc |
| ArchUnit `orders !→ notifications` | Producer không còn direct static dependency | Thêm lại gateway call |
| `@ApplicationModuleTest` + `PublishedEvents` | Producer phát đúng event ID/type | Bỏ publish hoặc payload sai |
| Cross-module `@SpringBootTest` | T1 commit → T2 QUEUED visible | Listener không đăng ký, T2 rollback |
| Rollback phase test | Rollback T1 không tạo work item hậu commit | Ghost queue |
| Writer idempotency | Duplicate không tạo job thứ hai/reset SENT | Conflict policy bị phá |
| Registry/recovery | Incomplete publication phục hồi theo adapter contract | Lost publication |
| Provider contract | Retry không nhân đôi external effect | Gửi email trùng khi response lost |
| Critical E2E | Caller thấy order accepted và status đúng | API tiếp tục hứa SENT ngay |

### Negative controls cần làm đúng test đỏ

- Bỏ `events.publishEvent` → producer publication test đỏ.
- Phát `OrderPlaced` với UUID khác order thật → payload assertion đỏ.
- Bỏ `@ApplicationModuleListener` → producer test có thể xanh nhưng cross-module QUEUED test đỏ.
- Import `notifications.NotificationQueries` từ `orders` → ArchUnit đỏ.
- Bỏ `ON CONFLICT`/unique constraint → writer replay test đỏ hoặc phát duplicate exception/row.
- Đặt outer `@Transactional` sai lên happy-path integration → test bị timeout giả; chỉnh fixture, không tăng wait.
- Catch và nuốt exception trong listener → registry/recovery test phải chỉ ra sai completed/pending semantics.

Làm mutation trong nhánh thực hành rồi hoàn nguyên, không lưu một test cố ý fail vào pipeline chính.

### Observability sau cutover

Các metric dưới đây là **đề xuất tự triển khai**, không mặc định Spring Modulith:

~~~text
orders_accepted_total
notification_jobs_queued_total
notification_jobs_sent_total
notification_jobs_failed_total
notification_oldest_queued_age_seconds
notification_delivery_attempts_total
event_publications_incomplete_total    (nếu adapter cung cấp)
provider_duplicate_effects_total      (nếu đo được)
~~~

Monitor **age** của jobs/publications chứ không chỉ count, vì producer có thể liên tục accepted orders trong khi consumer backlog tăng. Đo p95/p99 order acceptance trước/sau refactor nếu mục tiêu là tách external latency khỏi critical path; không tuyên bố performance tốt hơn mà chưa có bằng chứng.

### Time budgets sau khi đổi contract

- **Order acceptance deadline:** T1 commit, không phải email SENT.
- **Notification QUEUED deadline:** Eventual propagation từ T1 sang T2, Awaitility bounded.
- **Notification SENT deadline:** SLO riêng cho external workflow nếu business yêu cầu.
- **Registry recovery:** Test reliability riêng trên storage/restart, không chờ vô hạn.
- **CI job timeout:** Outer guard, không thay completion oracle.

Đừng buộc mọi unit/module test chờ production backoff dài. Dùng fake clock/delay cho retry policy, integration test với state query, và targeted recovery suite.

## 10. Thực hành, câu hỏi và checklist quyết định chuyển event

### Bài thực hành theo bằng chứng

**Bài A — Khi không được đổi sang async.** Chọn một rule như inventory reservation. Viết test rằng reservation failure ngăn committed order. Giải thích vì sao thay bằng `InventoryReservationRequested` async sẽ làm API chấp nhận order thiếu bằng chứng.

**Bài B — Characterize legacy.** Cho `NotificationGateway.sendConfirmation` ném exception; unit test quan sát caller, integration test xác minh DB rollback thực. Mock/unit test không thể chứng minh transaction rollback.

**Bài C — Refactor producer.** Bỏ direct notification call, publish `new OrderPlaced(id)`; không chạy cả hai. Chạy `OrderPublicationTest` và kiểm tra invalid input không publish.

**Bài D — Consumer hậu commit.** Dùng `@ApplicationModuleListener` tạo `notification_jobs`. PostgreSQL Testcontainers integration phải await `NotificationState.QUEUED`, không assert email đã SENT.

**Bài E — Rollback sau publish.** Tạo T1 bằng `TransactionTemplate`, publish rồi `setRollbackOnly()`; kiểm tra committed row absent, AFTER_ROLLBACK probe và bounded absence. Giải thích vì sao snapshot âm chưa chứng minh “không bao giờ”.

**Bài F — Duplicate/replay.** Gọi `queueIfAbsent(id)` hai lần, assert một row; đánh dấu SENT rồi enqueue lại, assert không reset state. Mở rộng bằng replay listener thật và đợi bằng chứng callback hoàn tất.

**Bài G — Crash window.** Inject T2 failure sau T1 commit. Trên đúng persistent registry adapter, xem incomplete publication, resubmit qua API version tương thích, await QUEUED. Không tự bịa API và không xóa pending trước khi đọc.

**Bài H — Gỡ dependency.** Chạy `ApplicationModules.verify()` và ArchUnit `orders !→ notifications`. Thêm lại import `NotificationGateway` từ producer, kiểm tra ArchUnit đỏ.

**Bài I — Công khai contract mới.** Viết HTTP/API integration test chứng minh `place` trả về sau khi order accepted, **không** mặc định email SENT. Thiết kế public notification status query nếu UX cần theo dõi.

### Câu hỏi tự đánh giá

1. Vì sao “giảm coupling” chưa đủ để chuyển mọi direct call thành event?
2. Gọi public API giữa hai Spring Modulith modules có luôn sai không?
3. `OrderPlaced` là fact, còn `SendConfirmationEmail` là command khác nhau thế nào?
4. `publishEvent` trong T1 có nghĩa T1 đã commit?
5. Vì sao `@Async @EventListener` có thể xử lý trước commit?
6. `@ApplicationModuleListener` giải quyết timing nào, chưa đảm bảo durability nào?
7. Vì sao `QUEUED` khác `SENT`?
8. DB unique work item và external provider idempotency khác nhau thế nào?
9. Vì sao cutover direct+event đồng thời dễ nhân đôi side effect?
10. `PublishedEvents` có chứng minh T2 commit/recovery không?
11. Vì sao rollback test cần transaction thật?
12. Vì sao `ApplicationModules.verify()` xanh mà direct call vẫn có thể tồn tại?
13. ArchUnit có thể bảo vệ mục tiêu gì thêm?
14. Nếu chỉ in-memory publish rồi crash sau T1, nguy cơ gì?
15. Khi nào **không** chuyển thành event mới là thiết kế đúng?

### Checklist trước khi hoàn tất migration

- [ ] Characterization tests ghi nhận legacy success/failure semantics.
- [ ] Business chấp nhận notification eventual; API không đổi contract âm thầm.
- [ ] Các điều kiện cần kết quả ngay vẫn dùng synchronous command/workflow xác nhận.
- [ ] Event tên theo fact, nằm trong public API module owner.
- [ ] Event payload không dùng JPA entity/internal type hoặc PII không cần thiết.
- [ ] Producer publish trong T1 thật qua Spring transaction proxy.
- [ ] Đã loại direct notification call; không chạy hai side-effect paths.
- [ ] Consumer dùng hậu commit semantics, không đọc source chưa commit.
- [ ] Work item QUEUED được commit trong T2 ngắn, không giữ transaction qua provider backoff.
- [ ] Có public `NotificationQueries` làm outcome oracle.
- [ ] `@ApplicationModuleTest` + `PublishedEvents` kiểm tra đúng event ID/type.
- [ ] Cross-module PostgreSQL IT xác minh T1 commit → T2 QUEUED.
- [ ] Rollback sau publish có phase/DB evidence, không chỉ snapshot âm.
- [ ] Unique key/upsert bảo vệ duplicate queue writes.
- [ ] Replay không reset SENT thành QUEUED.
- [ ] Provider có idempotency/reconciliation khi có retry.
- [ ] Registry/outbox được đánh giá theo crash/durability requirement.
- [ ] Reliability test dùng đúng adapter/version, không bịa exactly-once.
- [ ] Schema migration, rolling deployment có expand/cutover/retire plan.
- [ ] Không xóa fixture khi listener có thể retry/commit muộn.
- [ ] `ApplicationModules.verify()` bảo vệ module boundary.
- [ ] ArchUnit chặn `orders → notifications` khi đó là mục tiêu migration.
- [ ] CI giữ producer, after-commit, rollback, replay/recovery gates.
- [ ] Có metrics backlog/lag/failed jobs với owner vận hành.
- [ ] Có deploy rollback strategy không chạy lại hai đường gửi.
- [ ] Acceptance criteria chứng minh refactor giải quyết vấn đề thật.

**Ghi nhớ:** Chỉ chuyển direct call thành application event khi có **lý do về thời điểm hoàn tất, failure isolation hoặc fan-out** và business thật sự cho phép eventual outcome. Với `orders → notifications`, `OrderPlaced` được publish trong T1, `@ApplicationModuleListener` ghi `QUEUED` sau commit trong T2 và worker gửi email riêng. Kiểm chứng bằng `@ApplicationModuleTest`, `PublishedEvents`, PostgreSQL integration, rollback/replay/idempotency tests, `ApplicationModules.verify()` và ArchUnit. **Event không tự mang lại durability hay exactly-once**; chỉ coi refactor hoàn tất khi các failure windows và vận hành sau cutover đã được kiểm soát.





