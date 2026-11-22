# Tenant isolation trong event — Spring Framework Application Events

## 1. Vấn đề: một event có thể làm rò rỉ dữ liệu giữa các tenant như thế nào?

Trong hệ thống **multi-tenant**, một ứng dụng phục vụ nhiều tổ chức/khách hàng độc lập trên cùng hạ tầng. Mỗi tenant có dữ liệu, quyền truy cập và ranh giới xử lý riêng. Khi một service phát `OrderCreated`, listener có thể cập nhật read model, gửi email, ghi audit, tính quota hoặc lưu một bản thông báo vào outbox. Nếu listener truy vấn hoặc ghi dữ liệu **không có điều kiện tenant**, một event hợp lệ của tenant A có thể làm thay đổi dữ liệu của tenant B.

Ví dụ một thiết kế rủi ro:

```java
@EventListener
public void onOrderCreated(OrderCreated event) {
    // Nguy hiểm: tìm order chỉ theo orderId.
    Order order = orderRepository.findByOrderId(event.orderId());
    notificationService.send(order.customerEmail());
}
```

Đây là **phản ví dụ**, không phải mã độc lập: chưa có các class repository và service. Nếu cả hai tenant đều sử dụng `orderId = "ORDER-7"`, hoặc repository vô tình trả bản ghi đầu tiên tìm thấy, listener có thể gửi thông báo sai người nhận.

Một sai lầm khác là dùng `TenantContext.getCurrentTenant()` từ `ThreadLocal` bên trong listener `@Async`. Thread xử lý bất đồng bộ thường **không có context của thread đã publish**. Nếu dùng thread pool mà không dọn context đúng cách, worker thậm chí có thể giữ **tenant ID cũ** từ công việc trước. Cả hai đều có thể tạo lỗi cross-tenant.

**Tenant isolation trong event** là tập hợp các bảo vệ nhằm đảm bảo dữ liệu và tác dụng phụ của event thuộc đúng tenant, ở **từng chặng**: xác thực nguồn, kiểm tra quyền, tạo payload, dispatch, truy vấn dữ liệu, ghi kết quả, retry, lưu log và chuyển sang hệ thống khác.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu **tenant ID là dữ liệu định danh phạm vi**, không phải bằng chứng người gửi đã được cấp quyền.
2. Xây event payload chứa `tenantId`, `eventId` và các ID nghiệp vụ một cách rõ ràng.
3. Xác định tenant từ **danh tính đã xác thực và quyền thành viên đáng tin**, không tin mù quáng header/body của request.
4. Dùng khóa và truy vấn **(tenant_id, entity_id)** để tránh trùng ID giữa các tenant.
5. Kiểm tra **nguồn gốc event** trước khi một listener thực hiện thao tác nhạy cảm.
6. Phân biệt tenant scope trong event với `SecurityContext`, MDC và `ThreadLocal` khi chạy `@Async`.
7. Chọn cách bảo vệ phù hợp cho database, cache, outbox, broker, object storage, log và tác vụ nền.
8. Kiểm thử cách ly hai tenant cùng dùng một `orderId`, từ chối cross-tenant access và phát hiện event bị giả mạo.
9. Biết giới hạn của Spring Application Events: cơ chế in-process **không phải security boundary hoặc cơ chế delivery bền vững**.

## 2. Tenant isolation bảo vệ những gì?

Trong một event-driven workflow, cần xem xét cả **confidentiality**, **integrity** và **availability**:

| Mục tiêu | Câu hỏi | Ví dụ vi phạm |
| --- | --- | --- |
| Confidentiality | Listener có đọc/lộ dữ liệu tenant khác không? | Email của tenant B bị gửi vào luồng của tenant A |
| Integrity | Event của tenant A có sửa dữ liệu tenant B không? | Projection của B bị cập nhật từ event A |
| Authorization | Người hoặc service phát event có quyền ở tenant đích không? | Client tự sửa `tenantId` trong JSON |
| Provenance | Event có thật do nguồn tin cậy tạo không? | Consumer nhận message giả có tenant ID bất kỳ |
| Resource isolation | Một tenant có làm nghẽn toàn bộ event worker không? | Một tenant phát quá nhiều sự kiện, làm đầy queue chung |
| Auditability | Có truy vết được thao tác theo tenant và quyền không? | Log chỉ có `orderId`, không có `tenantId` |
| Resilience | Retry/replay có giữ đúng tenant và khóa idempotency không? | Replay sự kiện A bằng context đang là B |

Không nên coi việc thêm một field `tenantId` vào event là giải pháp đầy đủ. Field này giúp **xác định scope dữ liệu**, nhưng không ngăn caller độc hại viết một tenant ID khác vào payload. Ranh giới tin cậy phải được thực thi **trước khi tạo event** và **tại nơi tạo tác dụng phụ**.

### Mô hình nguy cơ tối thiểu

Giả định hệ thống có:

- Tenant `tenant-a` và `tenant-b`.
- Người dùng `alice` là thành viên của tenant A.
- Người dùng `bob` là thành viên của tenant B.
- Mỗi tenant có thể có một đơn tên `ORDER-7`.
- Một listener xử lý `OrderCreated` để cập nhật read model.

Các yêu cầu:

```text
alice -> tenant-a / ORDER-7       ALLOW
bob   -> tenant-b / ORDER-7       ALLOW
alice -> tenant-b / ORDER-7       DENY
event A -> projection của A      ALLOW
event A -> projection của B      DENY
```

Cùng một `orderId` ở hai tenant không phải trùng dữ liệu; vì thế phải phân biệt các bản ghi bằng **tenant_id cộng với order_id**.

## 3. Một event multi-tenant nên mang những trường nào?

Một payload immutable bằng Java 17 record:

```java
public record OrderCreated(
        String eventId,
        String tenantId,
        String orderId,
        Instant occurredAt
) {}
```

Đây là snippet kiểu dữ liệu; ví dụ hoàn chỉnh ở mục 8 bổ sung validation.

Ý nghĩa:

| Trường | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| `tenantId` | Phạm vi tenant sở hữu sự kiện | Lấy từ quyền đã được xác nhận; không tự tin client input |
| `eventId` | ID cho một event occurrence | Giữ nguyên khi retry/replay cùng occurrence |
| `orderId` | Định danh đối tượng trong tenant | Có thể trùng ở tenant khác |
| `occurredAt` | Thời điểm nghiệp vụ tạo event | Dùng `Instant` hoặc clock có kiểm soát |
| `correlationId` (nếu có) | Gom các event thuộc workflow | Không tự suy ra quyền hoặc idempotency |
| `causationId` (nếu có) | Event cha trực tiếp | Không thay thế tenant ID |
| `schemaVersion` (nếu cần) | Version payload | Hữu ích khi message lưu bền vững và được nâng cấp |

**Mỗi event dẫn xuất phải giữ đúng tenant của nghiệp vụ nguồn**, trừ khi có một workflow cross-tenant được ủy quyền rõ ràng và audit đầy đủ. Không lấy tenant mới từ MDC hoặc HTTP request hiện tại nếu event đã được xử lý sang thread khác.

### Record là bất biến nông

Field của record là `final`, nhưng một record chứa `List<Customer>` hoặc entity mutable vẫn không bất biến sâu. Với collection, có thể dùng `List.copyOf(...)`; với phần tử mutable phải tạo snapshot immutable riêng. Không đưa cả entity JPA hoặc `Authentication`/`SecurityContext` đang sống vào event payload. Payload nên chứa những ID và giá trị nghiệp vụ cần thiết, không phải resource nhạy cảm có vòng đời gắn thread/request.

### Tránh mang dữ liệu nhạy cảm khi không cần

Một `OrderCreated` chỉ cần `orderId` và `tenantId` để listener đọc thêm thông tin đã được cấp quyền thì không cần kèm toàn bộ email, thông tin thẻ hay địa chỉ. Record tự tạo `toString()` chứa component; nếu payload mang PII/secrets, `log.info("{}", event)` có thể vô tình lộ dữ liệu.

## 4. Tạo tenant context từ danh tính đáng tin

### 4.1. Không tin header tenantId một cách độc lập

Một request có thể gửi:

```http
POST /tenants/tenant-b/orders
Authorization: Bearer <access-token>
Content-Type: application/json

{"orderId":"ORDER-7"}
```

Đây là **ví dụ request mô tả**, không phải credential thật. Path chứa `tenant-b` là **tenant được yêu cầu**, không phải bằng chứng caller có quyền. Server phải:

1. Xác thực token/session và xác định principal đáng tin.
2. Tra cứu tenant membership, role hoặc entitlement hiện hành của principal.
3. Xác minh principal được phép thực hiện thao tác **trên tenant-b**.
4. Nếu cho phép, dùng tenant được xác nhận để gọi service và tạo event.
5. Nếu không, trả lỗi phù hợp mà không rò rỉ dữ liệu của tenant khác.

Không tin `tenantId` trong JSON body, query param hay một header tùy ý chỉ vì tên trường nghe hợp lý. Các giá trị này có thể được dùng như **requested tenant**, nhưng phải được đối chiếu với quyền đã xác thực.

### 4.2. Vai trò của Spring Security

Trong ứng dụng tích hợp Spring Security, danh tính được thể hiện qua `Authentication` nằm trong `SecurityContextHolder` theo chiến lược cấu hình. Nhưng **chỉ đọc `authentication.getName()` không phải là một phép kiểm tra tenant membership**.

Nên có một service authorization:

```java
public void requireTenantPermission(
        Authentication authentication,
        String requestedTenantId,
        String operation) {
    // Kiểm tra xác thực thực sự, không phải anonymous.
    // Tra quyền/tenant membership từ nguồn tin cậy.
    // Xác nhận operation được phép ở requestedTenantId.
    // Nếu không, ném AccessDeniedException.
}
```

Đây là **pseudocode API theo kiến trúc**, không phải implementation độc lập: cần xây policy, kiểm soát anonymous, token claims và nguồn membership thực tế. Claim `tenant_id` trong token có thể là đầu vào tin cậy **chỉ sau khi token đã được xác thực chữ ký, issuer, audience, expiry và policy theo hệ thống**. Nếu một người có nhiều tenant, không nên giả định claim mặc định là quyền cho mọi tenant.

**Không tạo quyền từ context logging.** `MDC.put("tenantId", "...")` phục vụ log, không chứng minh caller được quyền truy cập tenant đó.

## 5. Bốn lớp bảo vệ trong pipeline event

```text
HTTP / broker / scheduler
        |
        | 1. AUTHENTICATE + AUTHORIZE nguồn
        v
Application service
        |
        | 2. CREATE trusted immutable event
        |    { tenantId, eventId, orderId }
        v
ApplicationEventPublisher.publishEvent(event)
        |
        | 3. VALIDATE event provenance / invariant
        v
@EventListener(OrderCreated)
        |
        | 4. TENANT-SCOPED REPOSITORY / PROJECTION
        v
(tenant_id, order_id) database/cache/storage
```

**Lớp 1 — Xác thực và phân quyền tại đầu vào.** Nếu message đến từ broker/HTTP, xác thực source identity, kiểm tra quyền tenant, schema và nguồn phát. Một payload chỉ mang tên tenant không thể tự chứng minh tính hợp lệ.

**Lớp 2 — Ghi tenant đã xác nhận vào event.** Service không dùng arbitrary tenant ID từ caller mà lấy tenant đã được authorize. Event có ID ổn định và dữ liệu cần thiết cho công việc chạy chậm hoặc replay.

**Lớp 3 — Listener kiểm tra lại khi cần.** Tùy mức nhạy cảm, listener xác thực event thuộc nguồn/aggregate/trạng thái đáng tin, đặc biệt khi event có thể tới từ broker hay public integration. Nếu consumer nhận untrusted message, cần cơ chế authentication/authorization của producer (ví dụ ACL broker, service identity, signature hoặc authoritative data), không chỉ so sánh các trường payload với nhau.

**Lớp 4 — Mọi truy cập lưu trữ đều được scope theo tenant.** Query, update, cache key, outbox key và object path phải dùng tenant đúng. Ngay cả khi một tầng bỏ sót validation, database policy/tenant partition có thể là lớp bảo vệ bổ sung.

## 6. Database isolation: tenant là một phần của khóa và truy vấn

### 6.1. Mô hình shared table

Một schema tối thiểu:

```sql
CREATE TABLE orders (
    tenant_id  VARCHAR(80) NOT NULL,
    order_id   VARCHAR(80) NOT NULL,
    status     VARCHAR(30) NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
```

`ORDER-7` có thể tồn tại ở `tenant-a` và `tenant-b` mà không xung đột.

Truy vấn **đúng phạm vi**:

```sql
SELECT tenant_id, order_id, status
FROM orders
WHERE tenant_id = ?
  AND order_id = ?;
```

Cập nhật **đúng phạm vi**:

```sql
UPDATE orders
SET status = ?
WHERE tenant_id = ?
  AND order_id = ?;
```

Cấm một repository nhạy cảm làm kiểu:

```sql
SELECT * FROM orders WHERE order_id = ?;
```

nếu `orderId` chỉ duy nhất **trong phạm vi tenant**. Một truy vấn thiếu tenant có thể trả nhầm hàng tenant khác hoặc làm lộ sự tồn tại của dữ liệu ngoài quyền.

Các phương thức repository nên buộc truyền tenant:

```java
Optional<Order> findByTenantIdAndOrderId(
        String tenantId, String orderId);
```

Đây là **minh họa chữ ký repository**, cần định nghĩa entity/JPA repository theo ứng dụng. Query method có tenant không đồng nghĩa authorization đã được hoàn tất: service phải xác nhận caller được phép dùng `tenantId` đó.

### 6.2. Schema-per-tenant hoặc database-per-tenant

Một hệ thống có thể dùng ba kiến trúc:

| Kiến trúc | Ưu điểm | Rủi ro cần giải quyết |
| --- | --- | --- |
| Shared table, discriminator `tenant_id` | Tiết kiệm hạ tầng, dễ mở rộng nhiều tenant nhỏ | Quên predicate/constraint gây cross-tenant |
| Schema-per-tenant | Tách object database theo tenant | Chọn schema nhầm, connection pool giữ schema cũ |
| Database-per-tenant | Cách ly lưu trữ vật lý/logic mạnh hơn | Định tuyến connection nhầm, chi phí vận hành lớn |

Dù theo mô hình nào, **tenant routing ở listener** phải dựa vào tenant được validate. Khi dùng Hibernate multi-tenancy, cần cấu hình resolver/connection provider theo phiên bản ORM và thiết kế hệ thống; không giả định mọi truy vấn tự an toàn chỉ vì code có `tenantId`.

### 6.3. Row-level security là lớp defense-in-depth

Với PostgreSQL, Row-Level Security (RLS) có thể giới hạn hàng được đọc/ghi theo tenant ở tầng database. Nhưng phải cấu hình policy, role, connection/session/transaction setting đúng cách; table owner hoặc role có đặc quyền có thể bypass tùy cấu hình. Đừng cho rằng bật một flag mà không kiểm thử role và connection pooling đã tạo sự cách ly.

Ngay cả khi có RLS, **service vẫn phải phân quyền caller**. RLS là lớp bảo vệ thêm, không thay thế authentication hay policy nghiệp vụ.

## 7. Spring ApplicationEventPublisher có phải security boundary?

**Không.** `publishEvent(Object)` là cơ chế phát và phân phối sự kiện **bên trong ApplicationContext**. Khi một bean bất kỳ được cấp tham chiếu tới `ApplicationEventPublisher`, bean đó có thể phát object tùy ý theo API. Framework **không xác thực chữ ký message, kiểm tra tenant membership hoặc áp dụng ACL nghiệp vụ cho từng payload**.

Ví dụ một bean có thể tạo:

```java
publisher.publishEvent(
        new OrderCreated(
                "evt-forged",
                "tenant-b",
                "ORDER-7",
                Instant.now()));
```

Chỉ vì payload ghi `tenant-b` không có nghĩa event thật sự được tạo bởi dịch vụ có quyền trên tenant B. Nếu listener ghi database dựa hoàn toàn vào field này, nó đang tin dữ liệu chưa được xác minh.

Trong mô hình **trusted application code** và một context nội bộ, có thể coi service publisher đã được kiểm soát bởi code review và authorization tại cửa vào; song với tích hợp message từ bên ngoài, cần kiểm tra source identity, tenant scope, integrity và event schema tại **adapter biên giới**. Các consumer có tác dụng phụ nhạy cảm nên validate dữ liệu nghiệp vụ từ nguồn sự thật đáng tin.

### Không nhầm `getSource()` với tenant identity

Một event truyền thống kế thừa `ApplicationEvent` có `getSource()` do constructor nhận vào, nhưng field đó **không tự chứng minh producer được phép sử dụng một tenant**. Với record POJO, Spring có thể bọc thành `PayloadApplicationEvent`; wrapper `source` cũng không phải là authentication identity của tenant.

Không quyết định quyền chỉ dựa trên class của source object hoặc tên method listener.

## 8. Ví dụ hoàn chỉnh Java 17 + Spring Framework 6.2

Ví dụ console sau mô phỏng **hai tenant dùng cùng orderId** và ba phép kiểm soát:

1. `alice` tạo đơn `ORDER-7` cho `tenant-a`, `bob` tạo `ORDER-7` cho `tenant-b`.
2. Đọc projection bị giới hạn bởi quyền tenant. `alice` không được đọc của `tenant-b`.
3. Phát một `OrderCreated` bị giả mạo: gán `tenant-b` nhưng dùng `eventId` gốc của tenant A. Listener so khớp với **bản ghi nguồn tin cậy theo tenant và orderId**, nên từ chối.

Ví dụ cố ý dùng một `TenantAuthorizer` in-memory thay cho Spring Security hoàn chỉnh để logic tenant dễ kiểm chứng. Tham số `authenticatedUser` trong demo **đại diện danh tính đã được xác thực ở đầu vào**, không phải lời khuyên tin userId do request gửi lên. Production phải nhận principal từ security layer có kiểm tra.

### 8.1. Cấu trúc thư mục

```text
tenant-isolation-events/
├── pom.xml
└── src/main/java/example/TenantIsolationDemo.java
```

### 8.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>tenant-isolation-events</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.TenantIsolationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. Tệp src/main/java/example/TenantIsolationDemo.java

```java
package example;

import java.time.Instant;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class TenantIsolationDemo {

    // Cặp khóa: cùng orderId ở tenant khác là bản ghi khác.
    public record OrderKey(String tenantId, String orderId) {
        public OrderKey {
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(orderId, "orderId");
        }
    }

    // Payload POJO bất biến, Spring nhận qua publishEvent(Object).
    public record OrderCreated(
            String eventId,
            String tenantId,
            String orderId,
            Instant occurredAt) {

        public OrderCreated {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(occurredAt, "occurredAt");

            if (eventId.isBlank()
                    || tenantId.isBlank()
                    || orderId.isBlank()) {
                throw new IllegalArgumentException(
                        "Event identifiers cannot be blank");
            }
        }
    }

    // Demo: ACL tĩnh đại diện một nguồn membership đáng tin.
    // Production: user lấy từ Authentication đã được kiểm chứng.
    public static final class TenantAuthorizer {
        private final Map<String, Set<String>> membership = Map.of(
                "alice", Set.of("tenant-a"),
                "bob", Set.of("tenant-b"));

        public void requireMembership(
                String authenticatedUser,
                String tenantId) {
            if (!membership.getOrDefault(
                    authenticatedUser, Set.of()).contains(tenantId)) {
                throw new SecurityException(
                        "Not allowed to access requested tenant");
            }
        }
    }

    public static final class OrderStore {
        // eventId đã xác thực gắn với (tenantId, orderId).
        private final Map<OrderKey, String> events =
                new ConcurrentHashMap<>();

        public void create(OrderKey key, String eventId) {
            if (events.putIfAbsent(key, eventId) != null) {
                throw new IllegalStateException(
                        "Order already exists in this tenant");
            }
        }

        public boolean matches(OrderKey key, String eventId) {
            return Objects.equals(events.get(key), eventId);
        }
    }

    public static final class ProjectionStore {
        private final Map<OrderKey, String> projections =
                new ConcurrentHashMap<>();

        public void project(OrderKey key, String eventId) {
            // Idempotent cho event "OrderCreated" trong demo.
            projections.putIfAbsent(key, eventId);
        }

        public String get(OrderKey key) {
            return projections.get(key);
        }

        public int rowCount() {
            return projections.size();
        }
    }

    public static class OrderService {
        private final TenantAuthorizer authorizer;
        private final OrderStore orderStore;
        private final ProjectionStore projectionStore;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                TenantAuthorizer authorizer,
                OrderStore orderStore,
                ProjectionStore projectionStore,
                ApplicationEventPublisher publisher) {
            this.authorizer = authorizer;
            this.orderStore = orderStore;
            this.projectionStore = projectionStore;
            this.publisher = publisher;
        }

        public void create(
                String authenticatedUser,
                String tenantId,
                String orderId,
                String eventId,
                Instant occurredAt) {
            // Không được dùng tenant từ request khi chưa check ACL.
            authorizer.requireMembership(authenticatedUser, tenantId);

            OrderCreated event = new OrderCreated(
                    eventId, tenantId, orderId, occurredAt);
            OrderKey key = new OrderKey(tenantId, orderId);

            // Demo in-memory, production dùng transaction + outbox.
            orderStore.create(key, event.eventId());
            publisher.publishEvent(event);
        }

        public String readProjection(
                String authenticatedUser,
                String tenantId,
                String orderId) {
            authorizer.requireMembership(authenticatedUser, tenantId);
            return projectionStore.get(new OrderKey(tenantId, orderId));
        }
    }

    public static class OrderProjectionListener {
        private final OrderStore orders;
        private final ProjectionStore projections;
        private final AtomicInteger rejected = new AtomicInteger();

        public OrderProjectionListener(
                OrderStore orders,
                ProjectionStore projections) {
            this.orders = orders;
            this.projections = projections;
        }

        @EventListener
        public void onCreated(OrderCreated event) {
            OrderKey key =
                    new OrderKey(event.tenantId(), event.orderId());

            // Kiểm tra eventId với nguồn sự thật theo đúng tenant.
            if (!orders.matches(key, event.eventId())) {
                rejected.incrementAndGet();
                throw new SecurityException(
                        "Event not backed by authoritative order");
            }

            projections.project(key, event.eventId());
        }

        public int rejectedCount() {
            return rejected.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public TenantAuthorizer tenantAuthorizer() {
            return new TenantAuthorizer();
        }

        @Bean
        public OrderStore orderStore() {
            return new OrderStore();
        }

        @Bean
        public ProjectionStore projectionStore() {
            return new ProjectionStore();
        }

        @Bean
        public OrderService orderService(
                TenantAuthorizer authorizer,
                OrderStore orders,
                ProjectionStore projections,
                ApplicationEventPublisher publisher) {
            return new OrderService(
                    authorizer, orders, projections, publisher);
        }

        @Bean
        public OrderProjectionListener projectionListener(
                OrderStore orders,
                ProjectionStore projections) {
            return new OrderProjectionListener(orders, projections);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            OrderService service = context.getBean(OrderService.class);
            ProjectionStore projections =
                    context.getBean(ProjectionStore.class);
            OrderProjectionListener listener =
                    context.getBean(OrderProjectionListener.class);

            Instant time = Instant.parse("2026-11-01T08:00:00Z");

            // Hai tenant sở hữu hai ORDER-7 độc lập.
            service.create(
                    "alice", "tenant-a", "ORDER-7", "evt-A", time);
            service.create(
                    "bob", "tenant-b", "ORDER-7", "evt-B", time);

            boolean crossTenantReadDenied = false;
            try {
                service.readProjection(
                        "alice", "tenant-b", "ORDER-7");
            } catch (SecurityException expected) {
                crossTenantReadDenied = true;
            }

            boolean unauthorizedCreateDenied = false;
            try {
                service.create(
                        "alice", "tenant-b", "ORDER-8",
                        "evt-forbidden", time);
            } catch (SecurityException expected) {
                unauthorizedCreateDenied = true;
            }

            boolean forgedEventRejected = false;
            try {
                // Đổi tenant, giữ eventId của A -> không hợp lệ cho B.
                context.publishEvent(new OrderCreated(
                        "evt-A", "tenant-b", "ORDER-7", time));
            } catch (SecurityException expected) {
                forgedEventRejected = true;
            }

            System.out.println("A event="
                    + service.readProjection(
                            "alice", "tenant-a", "ORDER-7"));
            System.out.println("B event="
                    + service.readProjection(
                            "bob", "tenant-b", "ORDER-7"));
            System.out.println("Cross-tenant read denied="
                    + crossTenantReadDenied);
            System.out.println("Unauthorized create denied="
                    + unauthorizedCreateDenied);
            System.out.println("Forged event rejected="
                    + forgedEventRejected);
            System.out.println("Projection rows="
                    + projections.rowCount());
            System.out.println("Rejected events="
                    + listener.rejectedCount());
        }
    }
}
```

### 8.4. Lệnh chạy

Mở terminal trong thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

**Bảy dòng do chương trình in**, không tính log Maven hoặc Spring:

```text
A event=evt-A
B event=evt-B
Cross-tenant read denied=true
Unauthorized create denied=true
Forged event rejected=true
Projection rows=2
Rejected events=1
```

**Giải thích từng dòng:**

1. Tenant A có `OrderKey("tenant-a","ORDER-7")` gắn với `evt-A`.
2. Tenant B có `OrderKey("tenant-b","ORDER-7")` gắn với `evt-B`. Hai khóa không va chạm dù `orderId` giống nhau.
3. `alice` không có membership ở `tenant-b` nên service từ chối truy vấn tenant B, trước khi tra projection.
4. Cố tạo `ORDER-8` của tenant B dưới danh tính `alice` bị từ chối trước khi ghi store/publish event.
5. Event giả mang `tenant-b/ORDER-7` nhưng `eventId="evt-A"`, trong khi nguồn sự thật của khóa đó là `evt-B`. Listener từ chối, không ghi projection từ event giả.
6. Projection store có đúng hai entry sau các thao tác hợp lệ.
7. Listener ghi nhận một event bị từ chối.

**Đặc điểm của ví dụ:**

- Record `OrderCreated` là POJO; Spring phát trực tiếp bằng `publishEvent(Object)` rồi đưa tới `@EventListener`.
- Multicaster mặc định chạy **đồng bộ**, nên exception `SecurityException` của listener có thể lan về điểm `publishEvent(...)` và được main bắt trong ví dụ.
- `ConcurrentHashMap` bảo vệ thao tác đơn giản trong một JVM, nhưng **không phải database multi-tenant**, không có transaction, không bảo đảm bền vững hoặc cách ly giữa các replica.
- `eventId` cố định chỉ để kết quả dễ kiểm tra; production cần cấp phát ID duy nhất, ổn định khi retry.
- Việc so khớp `eventId` với `OrderStore` là **kiểm tra nhất quán nội bộ của demo**, không phải xác thực chữ ký producer; với event từ bên ngoài cần xác minh source identity và tính toàn vẹn thông điệp.
- Nếu listener đồng bộ thất bại sau khi `orderStore.create(...)` đã ghi, ví dụ **không rollback** bản ghi in-memory. Production dùng transaction/outbox và chính sách lỗi rõ ràng.
- `ProjectionStore.get(...)` được giữ ở lớp storage đơn giản; **chỉ public service endpoint có kiểm tra membership**. Ở hệ thống thực, mọi đường truy cập quan trọng phải được scope/authorize, không cho bean hoặc endpoint tùy ý bypass service.

### 8.5. Vì sao không dùng ThreadLocal tenant trong ví dụ?

Từng event đã mang `tenantId` được kiểm tra. Listener tạo `OrderKey(event.tenantId(), event.orderId())` để chọn đúng dữ liệu. Nhờ thế logic không phụ thuộc việc listener đang chạy trên request thread hay executor worker.

Khi dùng `@Async`, thông tin nghiệp vụ quan trọng vẫn nằm trong **event payload bất biến**. Việc truyền `SecurityContext` cho một worker có thể cần ở một số thiết kế, nhưng đó là quyết định riêng và không thể dùng thay bước kiểm tra provenance/authorization của event.

## 9. Chuyển thread: @Async, ThreadLocal và SecurityContext

Một listener bất đồng bộ có thể khai báo:

```java
@Async("tenantEventExecutor")
@EventListener
public void onCreated(OrderCreated event) {
    tenantScopedProjectionService.apply(
            event.tenantId(), event.orderId(), event.eventId());
}
```

Đây là đoạn **tích hợp**, cần `@EnableAsync`, bean executor `tenantEventExecutor` và một service thực hiện kiểm tra đáng tin. Không phải phần của demo đồng bộ ở mục 8.

### Vấn đề với ThreadLocal

`TenantContext` custom thường sử dụng `ThreadLocal<String>`. Khi event được nộp vào thread pool, worker không mặc nhiên mang đúng tenant của publisher. Một ví dụ nguy hiểm:

```java
@Async
@EventListener
public void onOrder(OrderCreated event) {
    String tenant = TenantContext.getTenant();
    repository.updateStatus(tenant, event.orderId());
}
```

Đây là **phản ví dụ**. Tenant có thể null hoặc sai khi worker được tái sử dụng. Để xử lý business event, ưu tiên `event.tenantId()` đã được kiểm tra và repository bắt buộc có tenant key.

### Khi bắt buộc dùng scoped tenant context

Một số ORM/schema-router hoặc thư viện yêu cầu context gắn thread. Khi đó có thể tạo scope có `try/finally`:

```java
String previous = TenantContext.getTenant();
try {
    TenantContext.setTenant(validatedEventTenant);
    executeTenantScopedWork();
} finally {
    if (previous == null) {
        TenantContext.clear();
    } else {
        TenantContext.setTenant(previous);
    }
}
```

Đây là đoạn minh họa; `validatedEventTenant` phải đã được **kiểm chứng** từ nguồn tin cậy, không lấy thẳng từ payload untrusted. Thứ tự rất quan trọng: **validate trước, cài tenant context sau**. Nếu không restore trong `finally`, worker có thể giữ tenant cũ và làm rò dữ liệu giữa các task.

**Không copy toàn bộ `SecurityContextHolder` hoặc transaction context bằng một MDC TaskDecorator tùy ý rồi xem như đã có quyền.** MDC chỉ phục vụ logging. Spring Security có `DelegatingSecurityContextExecutor` / `DelegatingSecurityContextAsyncTaskExecutor` để truyền security context theo phạm vi task khi cần. Nhưng **propagation không đồng nghĩa authorization mới**; policy vẫn phải kiểm tra quyền của actor/producer ở ranh giới tin cậy.

### Loại context nào cần truyền?

| Context | Vai trò | Có phải bằng chứng tenant permission không? |
| --- | --- | --- |
| `event.tenantId()` | Định tuyến dữ liệu theo tenant trong payload | Không; phải kiểm chứng nguồn |
| Spring `SecurityContext` | Chứa Authentication theo chiến lược của security stack | Chỉ có giá trị khi auth/authorization đúng |
| MDC `tenantId` | Làm phong phú log | Không |
| Custom `TenantContext` | Scoped routing cho thread/ORM | Không, nếu chưa validate trước |
| Transaction context | Connection/commit/rollback trên thread | Không; không tự truyền qua `@Async` |
| Correlation/trace IDs | Truy vết workflow | Không |

Với tác vụ nền khởi chạy sau thời gian dài, request principal có thể hết hạn hoặc quyền tenant thay đổi. Hãy cân nhắc **service identity + scoped authorization hiện hành** thay vì giữ nguyên một object `Authentication` sống từ request cũ.

## 10. Xử lý event từ broker và boundary liên dịch vụ

Một Spring bean nhận message từ Kafka/RabbitMQ có thể chuyển object thành `ApplicationEventPublisher.publishEvent(...)`. Nhưng event từ broker **không tự trở thành trusted** chỉ vì sau đó nó đi vào Spring context.

Pipeline an toàn:

```text
Broker message
    |
    +--> authenticate producer / verify topic ACL or signature
    +--> validate schema + required IDs
    +--> authorize producer for tenantId
    +--> resolve trusted tenant / aggregate metadata
    +--> publish validated internal event
    |
    v
Tenant-aware consumer
    +--> tenant-scoped repository / cache / outbox
```

Một adapter nên kiểm tra:

- **Nguồn phát** có phải service được phép phát loại sự kiện này không?
- Producer có quyền phát event cho tenant nêu trong message không?
- Message có phải bản replay hợp lệ hay có dấu hiệu giả mạo/chỉnh sửa?
- `eventId` có ổn định, schema/version có được hỗ trợ không?
- Định danh aggregate thuộc tenant nào trong nguồn dữ liệu đáng tin?
- Có vi phạm chính sách riêng về PII hoặc thời hạn lưu trữ không?

Không dùng broker partition/topic name như bằng chứng quyền duy nhất nếu ACL và routing không được kiểm soát. Cũng không lấy tenant từ một header message có thể bị producer không tin cậy ghi đè rồi tự mở schema/database cho tenant đó.

### Cross-tenant workflow hợp lệ

Một nghiệp vụ quản trị có thể **cố ý** tương tác nhiều tenant, ví dụ tổng hợp hóa đơn cho nhà điều hành dịch vụ hoặc di chuyển dữ liệu có kiểm soát. Không được dùng một bypass không giới hạn tên “admin” mà thiếu kiểm toán.

Thiết kế nên ghi rõ:

- Chủ thể thực hiện: service identity hoặc nhân viên có vai trò được cấp.
- Phạm vi tenant nguồn và tenant đích.
- Quyền/đồng ý cần thiết cho thao tác.
- Mục đích và audit record.
- Những trường dữ liệu được phép sao chép; dữ liệu nhạy cảm phải được tối thiểu hóa.
- Các bước rollback/compensation khi chuyển dữ liệu giữa hai tenant thất bại.

Tách thành command/workflow có authorization rõ ràng, thay vì âm thầm cho listener của tenant A ghi vào tenant B.

## 11. Tenant isolation trong transaction và outbox

Một listener dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` được gọi sau khi transaction phát event đã commit; nhưng annotation **không tự kiểm tra tenant hoặc bảo đảm xử lý bền vững**.

Ví dụ tích hợp:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommit(OrderCreated event) {
    tenantAwareOutboxService.schedule(
            event.tenantId(), event.eventId(), event.orderId());
}
```

Đây là snippet; `tenantAwareOutboxService` cần kiểm tra provenance và ghi outbox trong **transaction mới** phù hợp khi callback hậu commit. Đừng dùng một transaction context đã commit để ghi thêm rồi mặc định dữ liệu sẽ được commit lần nữa.

**Cửa sổ mất event:** nếu process crash sau business commit nhưng trước callback `AFTER_COMMIT`, công việc follow-up có thể bị mất. Nếu phải bảo đảm không mất event, hãy ghi **event outbox record trong cùng business transaction** với dữ liệu đơn hàng.

Schema gợi ý:

```sql
CREATE TABLE event_outbox (
    tenant_id       VARCHAR(80) NOT NULL,
    event_id        VARCHAR(80) NOT NULL,
    aggregate_id    VARCHAR(80) NOT NULL,
    event_type      VARCHAR(100) NOT NULL,
    payload_json    CLOB NOT NULL,
    status          VARCHAR(30) NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
);
```

Đây là schema minh họa; kiểu `CLOB` và index cụ thể cần điều chỉnh theo DB. Tính duy nhất theo `(tenant_id,event_id)` phù hợp nếu ID là duy nhất trong tenant; nếu `eventId` duy nhất toàn cục, có thể có ràng buộc bổ sung.

Outbox worker cần giữ tenant trong task metadata và chỉ lấy những dữ liệu thuộc đúng tenant. Nếu worker dùng connection với schema-per-tenant, phải chọn schema **trước truy vấn**, không để pool tái sử dụng một schema của tenant trước.

### Idempotency trong môi trường nhiều tenant

Một bảng processed markers:

```sql
CREATE TABLE processed_events (
    tenant_id      VARCHAR(80) NOT NULL,
    consumer_name  VARCHAR(80) NOT NULL,
    event_id       VARCHAR(80) NOT NULL,
    PRIMARY KEY (tenant_id, consumer_name, event_id)
);
```

Khóa này ngăn cùng consumer xử lý lặp một event occurrence trong một tenant, **không chặn event hợp lệ có cùng ID cục bộ ở tenant khác**. Nhưng nếu một event độc hại đổi tenantId và giữ eventId, marker không tự phát hiện giả mạo; vẫn cần kiểm chứng provenance và quyền ở input.

Với thao tác chuyển tiền/hóa đơn, còn cần **business uniqueness** như `(tenant_id,payment_id,invoice_type)`. Delivery dedupe và business uniqueness là hai hợp đồng riêng.

## 12. Cache, object storage và read model phải tách tenant

Tenant isolation không dừng ở SQL.

### Cache keys

Phản ví dụ:

```java
cache.get("ORDER-7");
```

Nếu cùng key này được dùng cho tenant A và B, cache có thể trả dữ liệu sai tenant. Một key phù hợp hơn:

```text
orders:tenant-a:ORDER-7
orders:tenant-b:ORDER-7
```

Nên dùng format key ổn định, có escaping/hash phù hợp để tránh va chạm khi tenantId hoặc orderId chứa ký tự phân cách. Với Redis hay các cache dùng chung, cần policy về tenant namespaces, TTL, cache invalidation và hạn chế quyền truy cập.

### Object storage

Nếu listener tạo file PDF:

```text
receipts/tenant-a/PAY-42.pdf
receipts/tenant-b/PAY-42.pdf
```

Path prefix giúp tổ chức dữ liệu nhưng **không tự cung cấp ACL**. Quyền bucket/object, presigned URL, tenant authorization và thời gian hiệu lực URL vẫn cần kiểm soát. Không dựa vào tên path khó đoán để thay xác thực.

### Search index và analytics

Event có thể cập nhật Elasticsearch/OpenSearch, read model hoặc hệ thống analytics. Khi query/search index, filter tenant là bắt buộc nếu nhiều tenant chia một index. Đừng chỉ áp dụng filter ở UI trong khi API hậu trường trả dữ liệu toàn tenant.

Nếu một event phát tới metrics/analytics có dữ liệu tổng hợp cross-tenant, phải có policy về dữ liệu được phép tổng hợp, mức ẩn danh, retention và quyền xem dashboard.

## 13. Logging, tracing và thông tin nhạy cảm

Một event-driven pipeline có thể ghi:

```text
tenantId
eventId
eventType
aggregateId / orderId
correlationId
causationId
handlerName
processingAttempt
processingStatus
instanceId
```

Ví dụ log an toàn hơn:

```text
tenant=tenant-a event=evt-A type=OrderCreated
handler=projection status=SUCCESS aggregate=ORDER-7
```

Không ghi toàn bộ payload chứa thông tin thẻ, email, token hoặc bí mật. Dù một log có `tenantId` đúng, nó không chứng minh repository query đã dùng tenant. Logging cần kết hợp với test và monitoring ở tầng dữ liệu.

Trong hệ thống sử dụng SLF4J MDC, có thể cài MDC từ **tenant đã được kiểm chứng** trong phạm vi listener:

```java
String previous = MDC.get("tenantId");
try {
    MDC.put("tenantId", trustedTenantId);
    processEvent();
} finally {
    if (previous == null) {
        MDC.remove("tenantId");
    } else {
        MDC.put("tenantId", previous);
    }
}
```

Đây là đoạn tích hợp; chỉ dùng sau khi xác định `trustedTenantId` từ nguồn đáng tin. Không lấy tenant context từ log rồi dùng nó làm bằng chứng phân quyền. Nếu xử lý async, cần scope/cleanup trên đúng worker thread; không để MDC của tenant A tồn tại khi worker chuyển sang event B.

### Tenant ID cũng có thể nhạy cảm

Trong một số hệ thống, tenantId chính là tên tổ chức hoặc mã nội bộ có thể tiết lộ quan hệ khách hàng. Không mặc định mọi tenant identifier đều có thể xuất hiện trong log công khai hoặc URL. Có thể dùng identifier giả danh, giới hạn access logs và retention theo chính sách.

## 14. Resource isolation và chống “noisy neighbor”

Ngay cả khi dữ liệu không bị trộn, một tenant có thể làm giảm khả năng phục vụ tenant khác nếu spam event:

```text
tenant-a -> 50,000 events -> shared executor queue đầy
tenant-b -> 10 events     -> chờ rất lâu / bị từ chối
```

Đây là vấn đề **availability isolation**, không chỉ confidentiality. Cân nhắc:

- Quota / rate limit số event đầu vào theo tenant hoặc theo actor.
- Queue partition theo tenant/nhóm dịch vụ khi cần bảo đảm fairness.
- Bounded queue và backpressure thay vì hàng đợi vô hạn.
- Retry/backoff theo tenant; không cho một tenant có lỗi phá vòng lặp gây nghẽn toàn pool.
- Per-tenant metric cho backlog, oldest event, latency, rejected count.
- Phân loại tenant workload (nhỏ/lớn/đặc biệt) và điều phối công bằng.
- Circuit breaker hoặc cách ly pool cho tác vụ tốn tài nguyên nếu cần.

Nhưng **thread-per-tenant** hoặc **executor-per-tenant** cũng có chi phí và nguy cơ cạn tài nguyên khi số tenant lớn. Phải đo thực tế trước khi áp dụng mô hình phân vùng mạnh.

## 15. Event replay, retry và tenant identity

Khi đọc lại một event từ outbox/event store:

- Giữ nguyên `eventId` và `tenantId` của occurrence đã lưu.
- Không lấy tenant hiện tại từ request đang xử lý hoặc từ worker `ThreadLocal` tồn dư.
- Kiểm tra bản ghi lưu có nguồn/tính toàn vẹn đáng tin.
- Dùng `(tenantId, consumer, eventId)` cho idempotency nếu eventId chỉ unique trong tenant.
- Khi read model được rebuild, không tự động gửi email/HTTP hoặc tạo tác dụng phụ ngoài từ mọi event lịch sử.
- Nếu tenant đã bị xóa, bị đình chỉ hoặc mất quyền xử lý theo policy mới, cần xác định chính sách replay/retention rõ ràng, không mặc định cứ có event cũ là được xử lý.
- Với replay xuyên tenant cho mục đích quản trị, dùng quyền đặc biệt có audit thay vì giả mạo security context của từng tenant.

### Đừng xem tenantId trong payload là vé thông hành

Payload replay có thể chứa `tenantId = tenant-b`. Nếu message store bị chỉnh sửa hoặc producer giả mạo, việc worker tin trường này và truy vấn database B là lỗ hổng. Cần kiểm tra nguồn thông điệp hoặc đối chiếu aggregate/tenant với dữ liệu authoritative, đặc biệt khi effect nhạy cảm.

Ví dụ chương trình mục 8 kiểm tra cặp `OrderKey + eventId` với `OrderStore`. Đây là một lớp sanity check hữu ích, nhưng **không thay xác thực producer thật** khi dữ liệu đã rời ranh giới ứng dụng.

## 16. Kiểm thử tenant isolation có hệ thống

Một suite nên có cả **positive tests** và **negative tests**:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Alice tạo đơn A | Chỉ tenant A có record và projection |
| Bob tạo đơn B cùng `ORDER-7` | Tenant B có record riêng, không đè A |
| Alice đọc projection B | Bị từ chối trước khi đọc |
| Alice cố tạo record cho B | Bị từ chối, không có event/record mới |
| Event đổi tenantId nhưng giữ eventId của A | Listener từ chối vì không khớp nguồn sự thật B |
| Event có ID/tenant rỗng hoặc null | Constructor/validator từ chối |
| Replay event hợp lệ của A | Không làm thay đổi dữ liệu B; effect idempotent theo chính sách |
| Event A xử lý bằng `@Async` | Không phụ thuộc ThreadLocal stale/null |
| Worker xử lý A rồi B trên cùng thread | Không rò tenant context giữa hai task |
| Query/update repository | Mọi đường có tenant predicate hoặc policy DB |
| Ghi outbox, processed marker | Khóa có tenant; transaction và retry giữ nguyên tenant |
| Hai tenant có cùng payment/order ID | Không va chạm cache, DB, object path |
| Consumer từ broker nhận tenantId giả | Bị chặn ở biên giới xác thực/authorization |
| Admin được phép thao tác cross-tenant | Có quyền cụ thể, audit và phạm vi rõ |
| Một tenant bắn event quá mức | Quota/fairness/backpressure không làm B ngừng phục vụ |

### 16.1. Test không chỉ gọi trực tiếp listener

Nếu chỉ gọi:

```java
listener.onCreated(
        new OrderCreated("evt-A", "tenant-a", "ORDER-7", time));
```

thì test này có thể kiểm tra logic handler nhưng **không chứng minh** Spring đã route đúng event. Một integration test nên khởi động context, dùng service thật gọi `publishEvent(...)` và assert projection, giống ví dụ mục 8.

Có thể dùng `@RecordApplicationEvents` của Spring TestContext để ghi nhận event trong test:

```java
@SpringJUnitConfig(Config.class)
@RecordApplicationEvents
class TenantEventTests {
    @Autowired OrderService service;

    @Test
    void publishesOnlyAuthorizedTenant(ApplicationEvents events) {
        events.clear();
        service.create(
                "alice", "tenant-a", "ORDER-7",
                "evt-A", Instant.parse("2026-11-01T08:00:00Z"));

        List<OrderCreated> actual =
                events.stream(OrderCreated.class).toList();

        assertEquals(1, actual.size());
        assertEquals("tenant-a", actual.get(0).tenantId());
    }
}
```

Đây là **snippet test tích hợp**, không phải một file test hoàn chỉnh vì cần test fixture, import và bean config từ mục 8. Trong test suite dùng Spring TestContext, đảm bảo test setup không làm tích lũy state qua các test dùng chung context; không đặt cùng khóa đã tồn tại vào singleton store khi test khác chạy trước. Test nên thiết lập fixture sạch hoặc context riêng.

### 16.2. Test negative phải kiểm tra không có tác dụng phụ

Khi một yêu cầu không hợp lệ bị từ chối, đừng chỉ assert có `SecurityException`. Phải assert:

- Không tạo order trong tenant đích.
- Không publish event hợp lệ cho tenant đích.
- Không có outbox row hay notification job.
- Không có cache entry/projection của tenant khác bị đổi.
- Audit ghi được lần truy cập bị từ chối mà không lộ nội dung bản ghi bí mật.

Một event giả mạo có thể bị listener từ chối **sau khi** một listener khác đã xử lý nếu multicaster có nhiều subscriber. Vì vậy với message untrusted, kiểm tra tại adapter **trước publish** vẫn rất quan trọng; một listener tự phòng vệ không bảo đảm mọi subscriber khác đều an toàn.

### 16.3. Test async với cùng worker

Với pool một worker, gửi event A, event B, rồi một event thiếu/invalid tenant. Dùng latch/future có timeout để đợi, không dùng `Thread.sleep(100)` rồi kiểm tra. Nếu có scoped TenantContext, mỗi task phải dọn bằng `finally`; không được để task B nhìn thấy tenant A.

Đối với tenant routing, test phải xác minh **database/query** dùng tenant đúng, không chỉ log MDC in đúng tenant.

### 16.4. Test database isolation thật

Nếu dùng shared table, integration test cần xác nhận cùng `orderId` ở hai tenant và query đúng tenant; thêm test update/delete có tenant filter. Nếu dùng schema-per-tenant, thử cố ý tái sử dụng connection để xác nhận schema được reset/route đúng. Nếu dùng RLS, test dưới **database role thực tế** mà ứng dụng dùng; tài khoản superuser/owner có thể cho kết quả sai.

## 17. Các lỗi thường gặp

1. **Chỉ thêm `tenantId` vào event rồi xem như đã an toàn.** Field không phải bằng chứng producer được phép chọn tenant đó.
2. **Tin `X-Tenant-Id` hoặc body JSON một cách tuyệt đối.** Client có thể sửa trường tenant.
3. **Lấy tenant từ MDC để truy vấn DB.** MDC dành cho logging, không phải authorization.
4. **Lấy TenantContext ThreadLocal trong listener async.** Worker không tự có đúng context của publisher.
5. **Không clear/restore TenantContext sau task.** Worker của tenant B có thể dùng tenant A còn sót.
6. **Truy vấn entity chỉ theo `orderId` khi ID unique trong tenant.** Dễ đọc hoặc sửa bản ghi sai tenant.
7. **Cache key không chứa tenant.** Hai tenant có thể dùng chung `ORDER-7`.
8. **Object storage key có tenant nhưng bucket ACL không giới hạn.** Prefix không thay thế authorization.
9. **Dùng `SecurityContextHolder.getContext()` mà không xác thực principal/membership.** Chỉ có object context chưa chứng minh quyền.
10. **Đưa nguyên `Authentication` hoặc HttpServletRequest vào event.** Dễ mang state hết hạn, mutable hoặc thông tin nhạy cảm.
11. **Tin broker header tenantId mà không kiểm tra producer.** Message giả có thể định tuyến sang tenant khác.
12. **Dùng `getSource()` của Spring event làm identity của tenant.** Source không có hợp đồng authorization.
13. **Tạo derived event rồi bỏ tenantId hoặc thay nó bằng tenant hiện tại.** Làm đứt provenance của workflow.
14. **Ghi outbox không có tenant và dedupe key quá rộng.** EventId có thể trùng theo phạm vi tenant hoặc hiệu ứng bị trộn.
15. **Gửi dữ liệu nhạy cảm trong payload rồi log `toString()`.** Có thể lộ PII/secrets.
16. **Dùng một tài khoản DB có quyền bypass mọi RLS mà nghĩ RLS vẫn bảo vệ.** Cần test role/config thật.
17. **Chỉ validate một listener rồi để message untrusted được publish cho tất cả subscriber.** Listener khác vẫn có thể bị khai thác.
18. **Cho rằng `@Async` hoặc `@TransactionalEventListener` tự bổ sung bảo mật.** Annotation chỉ điều khiển thời điểm/thread, không tự kiểm tra tenant.
19. **Tin rằng transaction gốc theo qua worker.** Không mặc định; cần transaction mới đúng phạm vi.
20. **Không xét event replay khi tenant bị đình chỉ hoặc đã xóa.** Chính sách vận hành và pháp lý có thể thay đổi.
21. **Dùng quyền admin toàn cục cho mọi background task.** Một event sai tenant có thể có quyền ghi mọi nơi.
22. **Không test hai tenant có cùng ID.** Test chỉ dùng ID toàn cục duy nhất có thể bỏ sót lỗi thiếu tenant predicate.
23. **Không giới hạn tải theo tenant.** Một tenant có thể làm nghẽn queue/worker chung.
24. **Nhầm logging context với tenant authorization.** Log có tenantId đúng chưa nói được event đã được xử lý đúng tenant.

## 18. Checklist đưa vào production

- [ ] Mỗi event nhạy cảm có `tenantId`, `eventId` và aggregate ID rõ ràng.
- [ ] Tenant được xác định từ principal/claims đã xác thực và membership/role có hiệu lực.
- [ ] Không tin header/body tenant trước khi kiểm tra quyền.
- [ ] Event từ broker/API ngoài được xác thực producer và validate trước khi publish nội bộ.
- [ ] Listener kiểm tra nguồn dữ liệu/tenant khi thao tác nhạy cảm; không chỉ nhìn vào tên tenant trong payload.
- [ ] Truy vấn và cập nhật DB bắt buộc có tenant predicate hoặc policy ORM/RLS được test.
- [ ] Khóa unique/foreign key phù hợp với phạm vi tenant; tránh suy ra `orderId` unique toàn hệ thống.
- [ ] Cache, object storage, search index và read model có tenant namespace/filter.
- [ ] Event immutable và không mang entity mutable, request, token hoặc secret không cần thiết.
- [ ] Async listener không phụ thuộc ThreadLocal bị thiếu hoặc stale; scoped context luôn restore trong `finally`.
- [ ] MDC/traceId dùng cho quan sát, không cấp quyền.
- [ ] Transaction, outbox và idempotency giữ nguyên tenant qua retry/replay.
- [ ] Consumer side effect cần bảo đảm không ghi sang tenant khác, kể cả khi event bị phát lại.
- [ ] Cross-tenant admin workflow có quyền cụ thể và audit.
- [ ] Có test read/write/rollback và case hai tenant cùng ID.
- [ ] Có test event giả mạo, thiếu tenant, tenant mismatch và worker reuse.
- [ ] Có metric/alert về event bị từ chối, mismatched tenant, backlog và quota theo tenant.
- [ ] Việc log và lưu event tuân thủ yêu cầu tối thiểu hóa dữ liệu và retention.

**Ghi nhớ:** tenant isolation trong Spring Application Events không nằm ở một annotation duy nhất. Cần **xác thực và phân quyền tenant ở đầu vào**, mang tenant đã được xác minh vào **event payload bất biến**, **kiểm tra provenance** trước effect, dùng khóa/truy vấn **tenant-scoped** ở mọi lưu trữ, và quản lý đúng transaction, thread context, retry và outbox. Một `tenantId` trong event là thông tin định tuyến quan trọng, **không tự nó là chứng cứ quyền truy cập**.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Hibernate ORM — Multi-tenancy and tenant identifier resolution](https://docs.hibernate.org/orm/6.4/userguide/html_single/Hibernate_User_Guide.html#multitenacy)
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
