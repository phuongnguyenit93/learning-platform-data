# Event nội bộ không phải ranh giới bảo mật trong Spring Framework Application Events

## 1. Tuyên bố cốt lõi và mục tiêu học tập

**Spring Application Events là cơ chế thông báo trong một `ApplicationContext`, không phải ranh giới xác thực, phân quyền hoặc cô lập dữ liệu.** Một bean có thể gọi `ApplicationEventPublisher.publishEvent(...)` để gửi một object; Spring lựa chọn và gọi những listener phù hợp. Việc một listener nhận được event **không tự chứng minh** rằng người dùng đã được xác thực, đã có quyền với đối tượng, payload có nguồn đáng tin, hoặc dữ liệu được phép chuyển sang consumer.

Đây là chủ đề **Bảo mật và dữ liệu** trong module **Spring Framework Application Events**. Bài học nhằm giúp phân biệt:

- **Thông báo đã xảy ra:** `OrderPlaced`, `PaymentConfirmed` hoặc `CustomerUpdated` được phát từ một phần của ứng dụng.
- **Quyết định cấp quyền:** ai được phép thực hiện thao tác, trên aggregate nào, dưới tenant nào và với dữ liệu nào.
- **Nguồn sự thật:** dữ liệu authoritative trong database, chính sách phân quyền, principal đã được xác thực và trạng thái nghiệp vụ đã commit.
- **Dữ liệu dùng để theo dõi:** `actorId`, `correlationId` và `eventId` có thể là audit metadata, **không phải chứng thư cấp quyền**.
- **Ranh giới xử lý:** sync, `@Async`, `@TransactionalEventListener` và message broker có cách truyền context/lỗi khác nhau nhưng không tự thay thế kiểm soát bảo mật.

Một **hệ thống nội bộ** có thể vẫn tiếp nhận dữ liệu từ HTTP, webhook, queue, job, plugin, callback hoặc mã của các nhóm khác nhau. Một payload trông có vẻ “nội bộ” vẫn có thể bắt nguồn từ dữ liệu do người gọi kiểm soát. Ngoài ra, code có thể phát event trực tiếp ngoài workflow dự kiến, test có thể tạo event giả và một listener có thể chạy ở thời điểm khác với lúc yêu cầu ban đầu được xác thực.

**Kết luận sớm:** đừng dùng việc “event đã được publish” làm điều kiện duy nhất để thực thi một hành động đặc quyền. Phải thiết kế authorization ở ranh giới nghiệp vụ và bảo vệ listener theo đúng mức rủi ro của side effect.

## 2. Spring Application Events thực sự bảo đảm điều gì?

Một publisher thông thường:

```java
@Service
public class OrderService {
    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void publishDemo() {
        events.publishEvent(new OrderPlaced("ORD-42"));
    }
}
```

Đây là **đoạn tích hợp minh họa**, không phải file Java biên dịch độc lập. Nó cần bean Spring, `OrderPlaced`, import `@Service` và `ApplicationEventPublisher`. Không có đoạn nào trong lời gọi `publishEvent` cho biết Spring đã:
- Kiểm tra JWT/session của request;
- Kiểm tra người gọi có sở hữu `ORD-42`;
- Kiểm tra quyền theo tenant;
- Chứng thực nguồn gốc của mỗi field trong payload;
- Mã hóa hoặc lọc dữ liệu theo quyền consumer;
- Bảo đảm listener chạy sau commit thành công;
- Lưu event để khôi phục khi JVM restart;
- Ngăn một bean khác phát object tương tự.

`ApplicationEventPublisher` là API **phát thông báo**. `SimpleApplicationEventMulticaster` chọn listener theo loại event/adapter rồi dispatch. `@EventListener` là cơ chế đăng ký callback, **không phải** annotation bảo mật.

Spring Security có các cơ chế riêng như filter chain, method security, authorization checks, `SecurityContextHolder` và integrations với async execution. Chúng chỉ phát huy tác dụng khi **được cấu hình và áp dụng đúng ranh giới**. Không nên tin rằng chỉ vì ứng dụng có Spring Security dependency thì mọi listener tự được kiểm tra quyền.

### Phạm vi “nội bộ” nghĩa là gì?

Application Events đi trong một application context; chúng không phải message bus công khai cho phép client gửi trực tiếp bằng giao thức mạng. Điều đó làm giảm một số bề mặt tấn công, nhưng **không tạo security sandbox giữa các Spring beans**. Nếu một thành phần trong cùng JVM bị xâm phạm hoặc đã có quyền thực thi code với độ tin cậy tương đương, nó có thể gọi service, publish event, đọc bean hoặc truy cập tài nguyên khác theo đặc quyền process.

Vì vậy, kiểm tra thêm ở listener có thể giúp chống **lỗi lập trình và dữ liệu giả/không hợp lệ**, nhưng không nên quảng cáo nó là cách cô lập **mã độc chạy trong cùng process với cùng quyền**. Muốn cô lập mạnh cần ranh giới hệ điều hành/process, identity độc lập, network policy, credentials có giới hạn và authorization tại dịch vụ tiếp nhận.

## 3. Mô hình đe dọa: ai phát, ai nghe, ai tin?

Hãy bắt đầu từ luồng:

```text
Untrusted HTTP request / webhook / message
          |
          v
Authentication + authorization ở entry point
          |
          v
Application service kiểm tra domain invariant / tenant / ownership
          |
          +--> DB transaction ghi trạng thái nghiệp vụ
          |
          +--> publishEvent(ImmutableDomainEvent)
                         |
              Spring event multicaster
                         |
             +-----------+----------------+
             |                            |
       Audit listener                 Notification listener
             |                            |
      dữ liệu tối thiểu              truy cập API/email
             |                            |
      kiểm soát PII                  side effect đặc quyền
```

Các câu hỏi trước khi viết listener:

1. Event được phát từ code nào? Có bao nhiêu đường dẫn có thể publish **cùng event type**?
2. Actor đã được xác thực ở đâu? Quyết định ủy quyền có đang phụ thuộc vào một `actorId` do client tự gửi không?
3. Event có mang `tenantId`, `ownerId` hoặc `customerId` không? Các giá trị đó lấy từ nguồn tin cậy hay request body?
4. Listener đọc dữ liệu nào, cần mức truy cập nào, có chạm cross-tenant data không?
5. Listener chỉ ghi metric, hay gửi email, xuất dữ liệu, cập nhật số dư, tạo hóa đơn, kích hoạt thanh toán?
6. Nếu event bị phát lại, giả mạo, đến sai thứ tự hoặc đến sau khi quyền đã bị thu hồi, side effect có còn an toàn không?
7. Ai xem được log/event payload? Có hệ thống tracing, dead-letter queue, backup và support console lưu lại dữ liệu không?

| Sai lầm | Mô tả | Tác động |
| --- | --- | --- |
| **Confused deputy** | Listener có credential mạnh làm theo payload từ nguồn không đủ tin cậy | Thao tác thay người gọi không đủ quyền |
| **BOLA/IDOR** | Listener dùng `orderId` hoặc `customerId` không check ownership | Đọc/ghi object của người khác |
| **Cross-tenant leakage** | Chỉ tin `tenantId` trong payload | Xuất dữ liệu từ tenant khác |
| **Privilege escalation** | Event chứa `role=ADMIN` hay `approved=true` do caller điều khiển | Bỏ qua quyết định authorization |
| **Data overexposure** | Event mang full JPA entity hoặc DTO quá rộng | Rò rỉ PII/secret qua listener, log, broker |
| **Replay/duplicate** | Consumer xử lý event cũ nhiều lần | Gửi thông báo hoặc tạo side effect trùng |
| **Context confusion** | Async listener nhầm `SecurityContext` hoặc MDC | Gán nhầm actor/tenant, audit sai |
| **TOCTOU** | Quyền hợp lệ lúc phát nhưng đã đổi trước lúc listener xử lý | Quyết định dùng dữ liệu cũ không còn hợp lệ |

Không phải mọi listener đều cần tái kiểm tra một authorization query tốn kém. Mức bảo vệ phụ thuộc vào **độ nhạy side effect**, nơi quyền đã được cưỡng chế và việc event có phải một fact đã được lưu từ luồng tin cậy hay không. Tuy vậy, mọi thiết kế đều cần nêu rõ nguồn sự thật và phạm vi tin cậy thay vì ngầm mặc định event type tự đáng tin.

## 4. Authorization phải xảy ra ở command/application-service boundary

Giả sử người dùng gửi lệnh đặt hàng. Quy trình đúng:

1. Tầng HTTP xác thực token/session qua Spring Security hoặc cơ chế tương đương.
2. Lấy **principal đã xác thực từ trusted security infrastructure**, không lấy username/role trực tiếp từ request JSON.
3. Application service kiểm tra actor có quyền đặt **chính đơn hàng đó**; đồng thời xác minh tenant, ownership, trạng thái đơn và business invariant.
4. Nếu bị từ chối, không thay đổi aggregate, không ghi outbox và không phát business fact `OrderPlaced`.
5. Nếu được phép, thực hiện thay đổi trạng thái trong transaction, rồi phát domain event hoặc lưu outbox theo yêu cầu delivery.
6. Listener nhận một **thông báo về nghiệp vụ đã được chấp nhận**, không phải một “vé quyền” để dùng tùy ý ở mọi nơi.

Mẫu Spring Security **tích hợp**:

```java
@Service
public class PlaceOrderService {
    private final OrderRepository orders;
    private final OrderPermissionService permissions;
    private final ApplicationEventPublisher publisher;

    public PlaceOrderService(
            OrderRepository orders,
            OrderPermissionService permissions,
            ApplicationEventPublisher publisher) {
        this.orders = orders;
        this.permissions = permissions;
        this.publisher = publisher;
    }

    @PreAuthorize("hasAuthority('ORDER_PLACE')")
    @Transactional
    public void placeOrder(String orderId, Authentication actor) {
        OrderEntity order = orders.findById(orderId).orElseThrow();

        if (!permissions.mayPlace(actor, order)) {
            throw new AccessDeniedException("No access to order");
        }

        order.place();
        publisher.publishEvent(new OrderPlacedEvent(
            UUID.randomUUID().toString(),
            order.getId(),
            order.getTenantId()
        ));
    }
}
```

**Đây không phải file chạy độc lập.** Cần `@EnableMethodSecurity`, method được gọi qua Spring proxy, các dependency/import Spring Security, JPA entity/repository, `OrderPlacedEvent`, và transaction manager thích hợp. Đừng tự tạo một `Authentication` từ dữ liệu request chưa xác thực; trong web flow nên lấy nó từ Spring Security context/framework đã được xác minh. Với thao tác đặc quyền cao, có thể truy vấn lại người dùng/quyền từ nguồn authoritative.

**Chỉ `@PreAuthorize("hasAuthority('ORDER_PLACE')")` không đủ cho object-level authorization.** Kiểm tra `permissions.mayPlace(actor, order)` xác nhận ownership/tenant theo domain. Nếu bỏ kiểm tra object cụ thể, người dùng có quyền chung vẫn có thể thao tác đơn của người khác.

**Cẩn thận self-invocation:** phương thức có `@PreAuthorize` được gọi nội bộ bằng `this.placeOrder(...)` trong cùng bean có thể không đi qua security proxy; một event listener gọi trực tiếp private method càng không tự nhận method security advice. Nếu bảo vệ dựa trên Spring AOP proxy, test đúng đường gọi qua Spring bean/proxy và cấu hình `@EnableMethodSecurity`.

## 5. Event type không phải bằng chứng authorization

Một codebase có thể có nhiều publisher:

```java
applicationEventPublisher.publishEvent(
    new OrderPlacedEvent("EVT-FAKE", "ORD-42", "tenant-A")
);
```

Đây là **mã minh họa**, không phải ví dụ có giao thức mạng cho attacker. Nó cho thấy một bean có thể dựng instance và gọi publish nếu có `ApplicationEventPublisher`. `@EventListener(OrderPlacedEvent)` không phân biệt event phát từ application service hợp lệ với event được phát trực tiếp từ một helper sai thiết kế.

Một listener nguy hiểm:

```java
@EventListener
public void on(OrderPlacedEvent event) {
    refundOrChargeService.charge(event.orderId());
}
```

Nếu side effect là thao tác tài chính, chỉ tin `event.orderId()` là không đủ. Một event sai hoặc duplicate có thể kích hoạt charge không mong muốn. Listener cần làm rõ: đây là **fact đã được commit** hay chỉ là **yêu cầu xử lý**? Nếu là command, nên đi qua application service có authorization/invariant; nếu là event, listener phải dựa trên fact/intent đã được ghi nhận và cơ chế idempotency.

### Những hướng bảo vệ theo mức độ

- **Phân quyền ở command boundary:** không tạo fact khi actor không có quyền.
- **Đọc lại trạng thái có thẩm quyền:** listener cần side effect nhạy cảm nên xác minh aggregate/state/outbox record phù hợp, không lấy mỗi cờ `approved=true` từ payload.
- **Event ID và nguồn phát hợp lệ:** consumer quan trọng có thể đối chiếu `eventId` với outbox/approved work item đã lưu.
- **Idempotency theo event ID:** không áp dụng một effect nhiều lần khi replay.
- **Object/tenant scoping tại DB query:** truy vấn theo `tenantId` và object ID được xác thực, không dùng raw ID đơn lẻ nếu multi-tenant.
- **Không để lộ capability mạnh:** listener có thể cần credential riêng chỉ đủ cho tác vụ của nó; ở một process, credentials thường chia sẻ ranh giới OS nên không coi đây là sandbox.
- **Audit có thể kiểm chứng:** log cả event ID, actor đã xác thực (nếu phù hợp), tenant, quyết định và kết quả, theo chính sách dữ liệu.

Không có một annotation biến Spring event bus thành trust boundary. Các biện pháp trên bổ trợ nhau và phải đặt ở đúng nơi chịu trách nhiệm.

## 6. Actor ID, tenant ID, correlation ID, event ID: metadata không phải credential

| Field | Ý nghĩa hợp lệ | Điều không được suy diễn |
| --- | --- | --- |
| `actorId` | Ghi dấu ai đã khởi tạo business action | Không chứng minh actor đang có quyền ở thời điểm consumer chạy |
| `tenantId` | Phân vùng nghiệp vụ liên quan đến event | Không cho phép đọc mọi record có tenant ID do payload cung cấp |
| `eventId` | Định danh logical event, dedupe khi retry | Không phải chữ ký số hoặc bằng chứng event đã được authorize |
| `correlationId` | Nối log/tracing của workflow | Không phải security token |
| `aggregateId` | Identity của object nghiệp vụ | Không phải chứng cứ ownership |
| `occurredAt` | Thời điểm fact xảy ra | Không tự chứng minh commit hoặc tính mới của trạng thái |
| `schemaVersion` | Phiên bản cấu trúc payload | Không thay validation của nội dung |

Ví dụ payload immutable tối thiểu:

```java
public record OrderPlacedEvent(
    String eventId,
    String orderId,
    String tenantId,
    String actorId,
    long totalCents
) {}
```

Payload có ích cho audit và các consumer được phép xử lý, nhưng **không phải access-control decision**. Hãy validate format/nonnull/range ở boundary và xác định provenance. Với event bắt buộc dùng lâu dài, giữ schema version, time và correlation ID theo contract; không gửi full Spring Security `Authentication`, session, JWT hoặc permission object mutable.

### Phân biệt “event ghi lại actor” với “event mang quyền”

Một business fact có thể hợp pháp ngay cả khi actor đã logout sau commit; do đó, yêu cầu **quyền tại thời điểm tạo fact** có thể khác yêu cầu **quyền hiện tại lúc xử lý**. Ví dụ:

- Audit nghiệp vụ: cần nhớ ai đã thực hiện đặt đơn lúc đó.
- Gửi email cho khách hàng: cần policy hiện tại về đồng ý nhận email, địa chỉ hiện tại và scope dữ liệu.
- Tạo một khoản thanh toán: cần payment intent đã được chấp nhận, idempotency và trạng thái order, không chỉ actorId.
- Export dữ liệu cá nhân: có thể phải kiểm tra entitlement hiện tại và legal basis, không dùng “đã từng authorize” làm giấy phép vĩnh viễn.

Quyết định phải được định nghĩa theo nghiệp vụ, không “luôn reauthorize” hoặc “không bao giờ reauthorize” một cách máy móc.

## 7. Dữ liệu tối thiểu và sự nguy hiểm của payload quá rộng

Một event nội bộ có thể dễ dàng mang entity:

```java
public record UnsafeCustomerChanged(CustomerEntity customer) {}
```

Đây là **anti-pattern minh họa**. Nếu `CustomerEntity` là JPA managed entity, event giữ cùng reference mutable và có thể làm lộ cả graph lazy relationships, thông tin liên hệ, định danh cá nhân, hashed credentials hoặc trường quản trị. Việc đặt entity trong `record` không làm entity bất biến hoặc giới hạn người nghe.

Rủi ro cụ thể:
- Listener chỉ cần `customerId` nhưng nhận email/địa chỉ/phone không cần thiết.
- Logger vô tình in `event.toString()` và lộ PII.
- AOP instrumentation hoặc exception handling serialize object không theo policy.
- Async handler giữ entity sang thread khác, gặp lỗi lazy-loading hoặc dữ liệu thay đổi.
- Nếu sau này forward event ra Kafka/queue, cả internal schema biến thành hợp đồng external và lộ field nhạy cảm.
- Vùng logs, tracing, DLQ, backup và monitoring có retention/quyền truy cập khác DB gốc.

**Nguyên tắc data minimization:** mỗi event phải chứa đúng các facts cần thiết cho consumer đã được duyệt. Nên cân nhắc chỉ gửi ID và snapshot tối thiểu, rồi để consumer truy vấn dữ liệu cần thiết qua service/repository có scoping và authorization phù hợp.

Chú ý: ID-only **không tự bảo đảm bảo mật**. Nếu listener có quyền đọc toàn DB và query bằng ID không kiểm tra tenant/ownership, việc giấu field trong payload vẫn không ngăn BOLA/IDOR. Data minimization và authorization là hai lớp khác nhau.

### Snapshot có thể phải được bảo vệ như dữ liệu gốc

Nếu event chứa địa chỉ, email hoặc tổng tiền tại một thời điểm, snapshot đó tồn tại trong logs/outbox/broker lâu hơn entity hiện tại. Cần policy:
- Dữ liệu nào được phép đưa vào event?
- Ai đọc được event store, DLQ, trace và log?
- Retention bao lâu, có encryption-at-rest hoặc redaction không?
- Việc xóa/chỉnh sửa dữ liệu theo yêu cầu privacy được xử lý ở các bản sao thế nào?
- Có versioning/compatibility và khả năng thu hồi dữ liệu không?

Không xem event DTO là “an toàn” chỉ vì nó không mang entity. Một DTO immutable chứa secret vẫn là secret.

## 8. Ví dụ Java 17+ chạy được: không tin event chỉ vì nó được publish

Ví dụ sau dùng **Spring Context 6.1.21** và bộ nhớ RAM để mô tả:
1. Một application service kiểm tra ownership **từ repository mô phỏng** trước khi thay trạng thái order.
2. Một lời gọi trái phép bị từ chối trước khi phát event.
3. Một component bất kỳ trong cùng context có thể phát một event **giả** bằng `publishEvent`.
4. Listener nhạy cảm kiểm tra event ID có tương ứng một fact đã được application service ghi nhận hay không.
5. Phát lại event hợp lệ bị bỏ qua bằng idempotency key.

**Giới hạn rất quan trọng:** đây là **minh họa defensive programming**, không phải hệ thống authentication hoặc security sandbox. Tham số `authenticatedActor` được **giả định** đã được tầng entry point lấy từ một principal xác thực đáng tin; demo không có Spring Security, JWT hay DB. Nếu caller có thể tùy ý đặt tham số này thành `alice`, kiểm tra ownership không bảo vệ được gì. Map và Set trong RAM không an toàn qua restart/multi-instance và mọi bean đủ quyền code có thể thao túng repository; production cần Spring Security, policy rõ và DB transaction/unique constraints.

### 8.1. Cấu trúc dự án

```text
internal-event-security/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/InternalEventSecurityDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'internal-event-security'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.InternalEventSecurityDemo'
}
```

### 8.2. File Java hoàn chỉnh

`src/main/java/demo/InternalEventSecurityDemo.java`:

```java
package demo;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class InternalEventSecurityDemo {

    public record OrderPlaced(
            String eventId, String orderId, String actorId) {}

    // Repository mô phỏng: trong production phải dùng storage đáng tin.
    public static final class OrderRepository {
        private final Map<String, String> owners =
            Map.of("ORD-42", "alice");
        private final Set<String> placed = new HashSet<>();
        private final Map<String, String> recordedFacts =
            new HashMap<>();

        public boolean ownedBy(String orderId, String actorId) {
            return actorId != null
                && actorId.equals(owners.get(orderId));
        }

        public void recordPlaced(String orderId, String eventId) {
            if (!placed.add(orderId)) {
                throw new IllegalStateException("Order already placed");
            }
            recordedFacts.put(eventId, orderId);
        }

        public boolean hasRecordedFact(
                String eventId, String orderId) {
            return orderId != null
                && orderId.equals(recordedFacts.get(eventId));
        }
    }

    public static final class PlaceOrderService {
        private final OrderRepository repository;
        private final ApplicationEventPublisher publisher;
        private final AtomicInteger sequence = new AtomicInteger();

        public PlaceOrderService(
                OrderRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        // authenticatedActor: được GIẢ ĐỊNH đã xác thực trước đó.
        public OrderPlaced place(
                String authenticatedActor, String orderId) {
            if (!repository.ownedBy(orderId, authenticatedActor)) {
                throw new SecurityException("Not allowed to place order");
            }

            String eventId =
                "EVT-" + sequence.incrementAndGet();
            repository.recordPlaced(orderId, eventId);

            OrderPlaced event =
                new OrderPlaced(eventId, orderId, authenticatedActor);
            publisher.publishEvent(event);
            return event;
        }
    }

    public static final class NotificationListener {
        private final OrderRepository repository;
        private final Set<String> processedIds = new HashSet<>();
        private int effects;

        public NotificationListener(OrderRepository repository) {
            this.repository = repository;
        }

        @EventListener
        public void on(OrderPlaced event) {
            if (!repository.hasRecordedFact(
                    event.eventId(), event.orderId())) {
                System.out.println(
                    "REJECTED eventId=" + event.eventId()
                );
                return;
            }

            if (!processedIds.add(event.eventId())) {
                System.out.println(
                    "DUPLICATE eventId=" + event.eventId()
                );
                return;
            }

            effects++;
            System.out.println(
                "HANDLED eventId=" + event.eventId()
                    + " orderId=" + event.orderId()
            );
        }

        public int effects() {
            return effects;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderRepository orderRepository() {
            return new OrderRepository();
        }

        @Bean
        public PlaceOrderService placeOrderService(
                OrderRepository repository,
                ApplicationEventPublisher publisher) {
            return new PlaceOrderService(repository, publisher);
        }

        @Bean
        public NotificationListener notificationListener(
                OrderRepository repository) {
            return new NotificationListener(repository);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            PlaceOrderService orders =
                context.getBean(PlaceOrderService.class);
            NotificationListener listener =
                context.getBean(NotificationListener.class);

            try {
                orders.place("mallory", "ORD-42");
            } catch (SecurityException expected) {
                System.out.println("DENIED actor=mallory");
            }

            // Cố ý bypass service: Spring không authenticate event.
            context.publishEvent(
                new OrderPlaced("EVT-FORGED", "ORD-42", "mallory")
            );

            // Actor giả định đã xác thực và có ownership.
            OrderPlaced accepted =
                orders.place("alice", "ORD-42");

            // Replay của chính cùng một event.
            context.publishEvent(accepted);

            System.out.println("business_effects=" + listener.effects());
        }
    }
}
```

Chạy trong thư mục project với JDK 17+ và Gradle:

```bash
gradle run --quiet
```

**Stdout nghiệp vụ kỳ vọng** (không tính dòng log phụ của Gradle hoặc Spring):

```text
DENIED actor=mallory
REJECTED eventId=EVT-FORGED
HANDLED eventId=EVT-1 orderId=ORD-42
DUPLICATE eventId=EVT-1
business_effects=1
```

### 8.3. Phân tích output

1. `PlaceOrderService.place("mallory", ...)` không thỏa `repository.ownedBy(...)`, nên ném `SecurityException` **trước** việc ghi fact hoặc publish. Main in `DENIED`.
2. Một event giả được phát trực tiếp từ context: Spring không chặn việc tạo object `OrderPlaced`. Listener được gọi, nhưng kiểm tra `recordedFacts` không thấy `EVT-FORGED` nên in `REJECTED`.
3. `PlaceOrderService.place("alice", "ORD-42")` giả định actor là principal hợp lệ, kiểm tra ownership, ghi fact với ID `EVT-1` và publish. Listener thấy fact đã ghi nên in `HANDLED`.
4. Khi cùng `accepted` được publish lần hai, `processedIds.add(eventId)` trả false, listener in `DUPLICATE` và không tăng `effects`.
5. Tổng `business_effects=1` cho thấy code demo chống duplicate trong một JVM và một thread. Nó **không** chứng minh đúng authorization nếu caller tự chọn tên actor hoặc chống được mã tùy ý chạy trong cùng process.
6. Với nhiều threads/processes hoặc lỗi giữa việc ghi `processedIds` và thực hiện side effect, `HashSet` không đủ. Cần transaction/unique constraint hoặc idempotency key của hệ thống ngoài.

**Tại sao đây là ví dụ về security boundary?** Nó minh họa sự khác biệt giữa **event đã được Spring dispatch** và **event tương ứng một business fact được application service chấp nhận**. Nhưng listener kiểm tra RAM chỉ là lớp bảo vệ chống sai sót; **nó không tạo ranh giới cô lập an toàn giữa các beans cùng process**. Nếu một module không đáng tin được phép chạy code tùy ý trong JVM, hãy tách module ra thành service/process với authorization qua API thay vì dựa vào event handler.

## 9. Dữ liệu giả có thể lọt qua event như thế nào?

Một ví dụ khác: controller nhận JSON:

```json
{
  "orderId": "ORD-42",
  "tenantId": "tenant-admin",
  "approved": true
}
```

Đây là **dữ liệu đầu vào minh họa**, không phải tín hiệu đáng tin. Nếu controller map trực tiếp request thành event:

```java
@PostMapping("/orders/place")
public void place(@RequestBody PlaceOrderRequest request) {
    events.publishEvent(new OrderPlacementApproved(
        request.orderId(),
        request.tenantId(),
        request.approved()
    ));
}
```

để listener đặc quyền thấy `approved=true` rồi thực thi side effect, ứng dụng đã biến **input do client kiểm soát** thành điều giống quyết định authorization. Nguy cơ là **confused deputy**: listener có credential mạnh làm theo dữ liệu chưa được kiểm tra.

Thay vì đó:
- Request body chỉ diễn đạt yêu cầu, không chứa kết luận được quyền.
- Controller dựa vào authentication đã được verify, gọi application service.
- Service nạp object theo tenant/owner từ nguồn authoritative, kiểm tra policy, rồi xử lý command.
- Event chỉ biểu diễn fact đã xảy ra và dữ liệu tối thiểu được duyệt.
- Listener nhạy cảm dựa trên fact/outbox/record có tính thẩm quyền hoặc kiểm tra lại policy khi cần.

Ngay cả `@Valid`/Bean Validation trên request DTO chỉ kiểm tra **hình dạng/giới hạn dữ liệu**, không thay object-level authorization hoặc business policy.

## 10. Multi-tenant: tenantId trong event không phải bộ lọc tin cậy

Nếu hệ thống phục vụ nhiều tenant, một event có thể mang `tenantId` để định tuyến công việc. Nhưng listener không được mù quáng dùng giá trị đó để truy vấn bất kỳ object nào.

Ví dụ nguy hiểm:

```java
OrderEntity order = repository.findById(event.orderId())
    .orElseThrow();
externalApi.send(order.getCustomerEmail());
```

Nó có thể đọc một order thuộc tenant khác nếu ID hợp lệ nhưng policy không được áp dụng. Mẫu an toàn hơn:

```java
OrderEntity order = repository.findByIdAndTenantId(
        event.orderId(), trustedTenantId
    )
    .orElseThrow();
```

Hai đoạn trên là **mẫu tích hợp**: repo/query và `trustedTenantId` phải đến từ nguồn có thẩm quyền, không chỉ là event field do caller tự điền. Trong DB cần áp dụng tenant scope ở mọi truy vấn, update/delete và object relationship phù hợp; cân nhắc row-level security hoặc repository API luôn yêu cầu tenant khi hệ thống có nguy cơ cross-tenant.

Một tình huống TOCTOU: tenant/object ownership thay đổi sau khi event được phát nhưng trước khi async listener đọc lại. Listener phải xác định yêu cầu của mình dựa trên **snapshot đã được ủy quyền tại thời điểm fact** hay **quyền hiện tại**. Không có một đáp án chung; phải nêu rõ chính sách nghiệp vụ.

## 11. Spring SecurityContext: không tự truyền qua async listener

Trong servlet stack, `SecurityContextHolder` mặc định dùng chiến lược dựa trên `ThreadLocal`. Khi multicaster sử dụng `TaskExecutor` hoặc method listener có `@Async`, worker thường là **thread khác**, không tự có context xác thực của request.

```text
HTTP request thread
  SecurityContext(actor=alice)
          |
          +--> publishEvent(OrderPlaced)
                        |
                        +--> executor worker thread
                               SecurityContext có thể rỗng
```

Điều đó có hai hệ quả:
1. Nếu listener **cần** biết actor nguồn để audit, nên ghi một `actorId` đã xác nhận vào event fact; không đọc `SecurityContextHolder` ở thread sau đó rồi đoán.
2. Nếu listener thực sự cần thực hiện thao tác dưới identity hiện hành, có thể dùng cơ chế propagation được Spring Security hỗ trợ, nhưng phải cân nhắc **scope, privilege, thời gian tồn tại và cleanup**.

Spring Security có những wrapper như `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` và `DelegatingSecurityContextAsyncTaskExecutor` để gắn/chuyển `SecurityContext` theo contract. Ví dụ cấu hình **tích hợp**:

```java
@Bean("securedTaskExecutor")
AsyncTaskExecutor securedTaskExecutor(
        ThreadPoolTaskExecutor delegate) {
    return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
}
```

Đoạn này cần Spring Security concurrency integration và imports tương ứng; chỉ dùng khi executor này thực sự là executor mà listener/task sẽ được submit qua.

**Không coi propagation là authorization.** Sao chép một context có role cao sang task có thể khiến background work chạy với quyền rộng hơn cần thiết. Context có thể trở nên stale khi user bị khóa hoặc role bị thu hồi, và task có thể hoàn tất sau khi request đã kết thúc. Đối với job dài hạn, nhiều trường hợp nên dùng **service identity tối thiểu** và kiểm tra policy ở nơi xử lý, thay vì giữ nguyên quyền của người dùng trên một thread pool.

### MDC/correlation ID cũng không phải SecurityContext

`MDC.put("userId", ...)` chỉ là dữ liệu logging. `correlationId`, `traceId` hoặc thread name không chứng minh authentication; không dùng chúng trong `@PreAuthorize` như một security principal. Nếu cần audit, đưa actor đã được xác minh thành metadata và kiểm soát log access/PII.

## 12. Transaction timing không nâng mức tin cậy

Với Spring event đồng bộ, `@EventListener` có thể chạy **trước DB commit** trong transaction của publisher. Listener làm side effect ngoài DB khi transaction sau đó rollback có thể gây không nhất quán.

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` trì hoãn callback tới sau commit thành công, nhưng không:
- Chứng thực ai tạo event;
- Xác minh tenant/ownership;
- Cấm các bean khác publish cùng event type;
- Bảo đảm callback không bị mất khi JVM crash;
- Tạo một security principal mới cho worker;
- Tự bảo đảm idempotency hoặc authorization cho side effect.

Ví dụ tích hợp:

```java
@Component
public class OrderEmailListener {
    private final OrderReadService orders;
    private final MailGateway mail;

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderPlacedEvent event) {
        OrderEmailView view = orders.loadAllowedNotificationView(
            event.orderId(), event.tenantId()
        );
        mail.sendConfirmation(view);
    }
}
```

Đây là **đoạn tích hợp**, cần bean/repository, kiểu view, chính sách tenant và các import. `orders.loadAllowedNotificationView` phải được triển khai đúng với dữ liệu có thẩm quyền; chỉ đặt tên method “Allowed” không làm nó tự an toàn.

Nếu callback sau commit đọc/ghi database, cần transaction mới thích hợp khi cần (ví dụ bean method với `@Transactional(propagation = REQUIRES_NEW)`), không giả định transaction gốc còn commit cho các thay đổi sau đó. Với Spring Test, một test `@Transactional` tự rollback cuối test sẽ không kích hoạt AFTER_COMMIT; phải commit thật khi muốn kiểm thử phase.

**Ranh giới bảo mật và tính bền vững là hai trục khác nhau**: một event có thể đã được authorize nhưng vẫn bị mất do crash; hoặc được chuyển qua broker rất bền vững nhưng chứa dữ liệu sai tenant. Thiết kế phải xử lý cả hai.

## 13. Outbox và broker không tự bảo đảm tính an toàn dữ liệu

Để không mất event sau commit, ứng dụng có thể dùng transactional outbox:

```text
Application service
  |-- Authentication + object-level authorization
  |-- Domain transition
  |-- INSERT outbox(eventId, aggregateId, type, safePayload)
  |-- COMMIT cả domain state + outbox
                         |
                         v
               Outbox dispatcher / broker
                         |
                         v
               Consumer validate, authorize
                         |
                         v
               Idempotent business effect
```

Outbox có giá trị về **reliability**, không phải về xác thực. Nếu producer ghi dữ liệu nhạy cảm hoặc payload sai tenant vào outbox, broker sẽ phát lại một lỗi bảo mật rất bền bỉ. Vì vậy:
- Thiết kế integration event schema tách khỏi JPA entity.
- Định nghĩa field cần thiết, quyền của consumer và data classification.
- Áp dụng ACL/IAM/broker topic permissions, TLS và encryption theo yêu cầu.
- Dedupe theo `eventId` và consumer identity khi retry.
- Consumer validate message schema, nguồn và policy của chính mình.
- Bảo vệ DLQ, tracing, replay consoles và outbox admin tooling vì có thể chứa payload.
- Giám sát retry và quyền truy cập; tránh log raw event trong exception.

Nếu hệ thống ngoài process nhận event, **ranh giới tin cậy trở nên rõ hơn**: đừng tin chỉ vì message đến từ “internal topic”. Cần service identity, message transport security và authorization ở consumer. Chữ ký hoặc envelope metadata chỉ hữu ích nếu được quản lý khóa/xác minh theo một threat model phù hợp, không thay business authorization.

## 14. Replay, idempotency và quyền thay đổi theo thời gian

Giả sử event `CustomerExportRequested(EVT-42)` đã được tạo khi user có quyền export. Trước lúc background worker chạy, quyền bị thu hồi. Có ít nhất hai policy hợp lệ tùy ứng dụng:

| Policy | Ý nghĩa | Khi phù hợp? |
| --- | --- | --- |
| **Authorize at request time** | Ý định được chấp nhận thành job có tính ràng buộc; worker dùng authorized intent đã commit | Công việc đã được phê duyệt, muốn thực thi sau theo contract |
| **Reauthorize at execution time** | Worker kiểm tra quyền hiện tại trước khi xuất dữ liệu | Dữ liệu nhạy cảm/quyền có thể bị thu hồi và yêu cầu phải có hiệu lực ngay |
| **Hybrid** | Lưu approved intent, nhưng còn kiểm tra consent/legal basis/tenant policy trước side effect | Workflow dài, nhiều thay đổi trạng thái và yêu cầu compliance |

Không mặc định mọi event phải kiểm tra lại user role theo thời điểm xử lý; như thế có thể làm hỏng quy trình hợp lệ khi user đã logout. Ngược lại, cũng không mặc định “đã từng hợp lệ thì sau này luôn hợp lệ” với export dữ liệu hoặc quyền cao. Ghi policy rõ trong use case.

**Idempotency khác authorization.** Một unique constraint theo `(consumer_name, event_id)` giúp tránh xử lý lại cùng event, nhưng event được accept lần đầu vẫn có thể trái phép nếu không có authorization. Một event ID không phải “vé đã kiểm tra”.

Với external API, ưu tiên dùng idempotency key được upstream chấp nhận; nếu timeout không rõ kết quả, reconciliation theo external reference có thể cần thiết. Không chỉ ghi một Set trong RAM rồi coi multi-instance an toàn.

## 15. Bảo vệ listener làm side effect đặc quyền

Một listener có thể chỉ làm best-effort cache invalidation, nhưng cũng có thể:
- Gửi email chứa PII;
- Export dữ liệu khách hàng;
- Tạo bút toán, thanh toán hoặc hoàn tiền;
- Gửi thông điệp đến hệ thống đối tác;
- Chỉnh trạng thái user, tenant hoặc quyền truy cập.

Với side effect nhạy cảm, hãy thiết kế một handler contract:

1. **Nguồn ý định:** một business fact/command đã được service nhận hợp lệ, lý tưởng lưu trong DB/outbox với ID ổn định.
2. **Scope dữ liệu:** aggregate/tenant được lấy từ record có thẩm quyền; mọi query có tenant/ownership guard phù hợp.
3. **Quyền:** quyết định ở command boundary và/hoặc reauthorization theo policy thực thi.
4. **Dữ liệu tối thiểu:** chỉ đọc những trường listener cần; tránh full entity và raw request body.
5. **Idempotency:** có key và transaction/unique constraint hoặc cơ chế của external API.
6. **Audit:** lưu ai đã yêu cầu, cái gì được quyết định, khi nào, dưới policy/version nào nếu cần.
7. **Failure policy:** nếu thiếu quyền hoặc thấy event giả, fail closed, không âm thầm thực hiện tác vụ; ghi log/metric an toàn và có đường điều tra.
8. **Recovery:** retry không được bỏ qua auth/validation; nếu dùng DLQ/replay, quyền của người replay được kiểm soát.

Một listener có thể gọi service có method security thay vì tự sao chép policy. Nhưng cần chắc chắn lời gọi đi qua **Spring proxy/authorization infrastructure**, và method security bảo vệ đúng resource, không chỉ role chung.

### Không giao “root privileges” mặc định cho background task

Việc một worker là trusted infrastructure không có nghĩa mọi event được phép ra lệnh cho worker làm bất cứ điều gì. Thiết kế task-specific service methods và credentials theo least privilege, hạn chế endpoint được gọi, quyền DB/table, scope message topic và dữ liệu xuất. Một “god listener” đọc mọi event và làm mọi side effect sẽ khó audit và khó kiểm soát blast radius.

## 16. Kiểm thử bảo mật event đúng cách

### 16.1. Authorization ở entry/service boundary

- User không có quyền tổng quát → service từ chối trước khi thay đổi DB hoặc publish business fact.
- User có quyền `ORDER_PLACE` nhưng không sở hữu order → service từ chối.
- User của tenant A cố thao tác order tenant B → service từ chối.
- User có quyền hợp lệ → aggregate transition đúng và một fact phù hợp được ghi nhận.
- Kích hoạt method qua bean/proxy, không chỉ gọi trực tiếp method không được advice.

Nếu test sử dụng `@WithMockUser`, phải phân biệt **giả lập principal cho test** với bằng chứng hệ thống xác thực JWT/OAuth thật. Có thể cần integration test filter chain riêng để chứng minh authentication boundary.

### 16.2. Listener nhận payload giả

Trong context test, gọi `publishEvent(new OrderPlacedEvent(...))` trực tiếp với event chưa được xác minh. Với listener side effect nhạy cảm, assert nó **không** thực hiện email/charge/export nếu hợp đồng yêu cầu phải có approved fact. Demo mục 8 minh họa phép kiểm tra này.

Đây là một lớp test chống **accidental publication**; nó không chứng minh lớp code độc hại chạy cùng JVM bị cô lập. Nếu security model có plugin không đáng tin, cần test separation qua service/process/credentials thật.

### 16.3. Dedupe và concurrency

- Gửi lại cùng `eventId` → side effect không bị nhân đôi.
- Hai event ID khác nhau cho cùng aggregate → consumer xử lý theo semantic/version riêng, không loại nhầm vì chỉ nhìn aggregate ID.
- Hai worker đồng thời claim cùng event → unique constraint hoặc cơ chế atomic bảo vệ effect.
- Nếu lỗi sau side effect trước ACK, retry cùng ID không lặp business effect ngoài dự định.

### 16.4. Async SecurityContext và MDC

Tạo một test listener chạy trên `ThreadPoolTaskExecutor` với `@Async` hoặc multicaster executor. Assert:
- Context không được giả định tự propagate.
- Nếu dùng `DelegatingSecurityContextAsyncTaskExecutor`, context được set/clear theo policy và không rò sang task của actor khác.
- Authorization không được suy từ thread name/MDC.
- Task xử lý muộn dùng approved intent hoặc reauthorization theo policy.
- Không có principal thì code fail closed ở thao tác đặc quyền, thay vì dùng quyền admin mặc định.

Chờ task bằng `CountDownLatch`/`CompletableFuture`/Awaitility với timeout hữu hạn; không dùng `Thread.sleep` rồi suy đoán kết quả.

### 16.5. Transaction và crash windows

- Publish trước rollback: không có side effect không được phép xảy ra khi command rollback.
- `@TransactionalEventListener(AFTER_COMMIT)` chỉ xử lý khi commit thật; không dùng test transaction tự rollback mà kỳ vọng callback.
- Crash sau DB commit trước callback → phải có outbox nếu event không được phép mất.
- Outbox replay/broker retry → consumer vẫn validate nguồn, scope và idempotency.

### 16.6. Rò rỉ dữ liệu

Kiểm tra event DTO/serialization:
- Không có access token, password, secret, full entity graph hoặc PII ngoài phạm vi.
- Logger không gọi `toString()` trên toàn bộ payload nhạy cảm.
- Exception handlers/metrics/tracing không lộ event body.
- DLQ/outbox/log retention và quyền đọc tương ứng với phân loại dữ liệu.
- Cross-tenant queries có test cụ thể với ID hợp lệ thuộc tenant khác.

## 17. Anti-pattern và cách sửa

| Anti-pattern | Vì sao sai | Thay thế |
| --- | --- | --- |
| “Có `@EventListener` nên event là trusted” | Listener registration chỉ là dispatch | Validate nguồn và dùng approved domain fact |
| Dùng `event.actorId` như principal | Actor ID là dữ liệu, có thể spoof/stale | Principal từ Spring Security boundary, policy rõ |
| Gắn `role=ADMIN` trong event | Cờ do caller gửi không phải authorization | Kiểm tra quyền ở service/consumer |
| Cho client tự gửi `tenantId` rồi truy vấn toàn DB | Dễ cross-tenant | Derive tenant từ trusted context/record và scope query |
| Gửi managed JPA entity cho mọi listener | Mutable, lazy, overexposure | Immutable DTO/snapshot/ID tối thiểu |
| Đưa JWT trong event để “giữ quyền” | Lộ credential, token có thể hết hạn, leak qua log/broker | Dùng actor metadata + policy, service identity khi cần |
| Copy SecurityContext qua mọi thread | Privilege propagation không kiểm soát | Chỉ propagate khi cần; scope/cleanup và least privilege |
| Tin `AFTER_COMMIT` nghĩa secure/durable | Phase khác authorization/delivery guarantee | Authorization + outbox nếu cần |
| Dedupe eventId là đủ để bảo mật | Idempotency không chứng minh quyền | Authorization độc lập |
| Listener gửi API bên ngoài theo ID raw | Confused deputy/IDOR | Đọc authoritative record và policy trước side effect |
| Một tenant ID trong event là “tenant isolation” | Chỉ là chuỗi metadata | Tenant-scoped repository/RLS/service policy |
| Log toàn bộ event “để debug” | Rò rỉ PII, token, dữ liệu dài hạn | Structured log chỉ các ID an toàn |
| Coi internal broker topic là trusted tuyệt đối | Có thể bị cấu hình sai/producer khác gửi | Broker ACL, identity, consumer authorization |

## 18. Checklist thiết kế trước khi merge

- [ ] Đã phân biệt event notification với authentication/authorization boundary?
- [ ] Command/application service lấy principal từ nguồn **đã xác thực**, không từ body do client điều khiển?
- [ ] Có object-level authorization, tenant isolation và domain invariant trước khi tạo business fact?
- [ ] Code không giả định `publishEvent` hay `@EventListener` tự validate nguồn event?
- [ ] Listener đặc quyền dùng approved record/policy có thẩm quyền thay vì tin cờ trong payload?
- [ ] Event payload chỉ chứa ID/facts cần thiết, không chứa token, credential, managed entity hoặc dữ liệu dư thừa?
- [ ] `actorId`, `tenantId`, `correlationId` và `eventId` được dùng đúng vai trò, không làm vé cấp quyền?
- [ ] Async task không tự giả định `SecurityContextHolder` đi theo thread?
- [ ] Nếu có propagate security context, scope và cleanup được kiểm thử, không cấp quyền mạnh quá mức?
- [ ] Quyết định authorize-at-request hay reauthorize-at-execution đã được nêu rõ cho công việc chạy muộn?
- [ ] `@TransactionalEventListener` được dùng đúng phase, không bị nhầm với security hoặc durability?
- [ ] Công việc không được mất đã có outbox/queue và consumer idempotent, vẫn validate security?
- [ ] Schema/serialization/logging/trace/DLQ tuân theo data classification và retention policy?
- [ ] Có test event giả, quyền object, cross-tenant, replay, concurrency và failure windows?
- [ ] Nếu code không đáng tin cần chạy extension, đã có **process/service isolation thật** thay vì xem ApplicationContext là sandbox?

**Ghi nhớ:** event nội bộ là **tín hiệu trong ứng dụng**, không phải **bằng chứng được cấp quyền**. Spring giúp phát và chọn listener, còn ứng dụng phải tự xác thực nguồn vào, kiểm tra authorization/ownership/tenant, tối thiểu hóa dữ liệu và giới hạn side effect. Nếu cần tách code không đáng tin, hãy dựng ranh giới bảo mật thật ở process/service/API và identity, không dựa vào việc hai module giao tiếp qua `publishEvent`.

## Tài liệu tham khảo

- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.1 — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Concurrent Execution / SecurityContext](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Cheat Sheet — Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
