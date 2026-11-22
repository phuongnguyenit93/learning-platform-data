# Phân biệt thông tin lần sửa gần nhất với lịch sử thay đổi đầy đủ

> **Chương:** Auditing  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Phân biệt *metadata lần tạo/lần sửa gần nhất* với *audit trail nhiều phiên bản*; thiết lập Spring Data auditing (`@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy`) trong imperative/reactive; nhận diện đường ghi không kích hoạt auditing; thiết kế lịch sử thay đổi có actor, lý do, thời điểm, revision, before/after và request ID; ghi state + history nhất quán bằng MongoDB transaction; xử lý cạnh tranh, retry, bảo mật, change streams, khôi phục lịch sử và kiểm thử.

## 1. Một document trả lời được bao nhiêu câu hỏi về quá khứ?

Giả sử collection `orders` đang chứa:

~~~javascript
{
  _id: "o901",
  tenant_id: "t01",
  status: "SHIPPED",
  delivery_address: "12 Nguyễn Văn A",
  created_at: ISODate("2026-10-10T02:00:00Z"),
  created_by: "customer-22",
  updated_at: ISODate("2026-11-20T03:00:00Z"),
  updated_by: "operator-08"
}
~~~

Document trên biết **ai tạo** và **ai sửa gần nhất**, nhưng không biết:

- Trước khi thành `SHIPPED`, order có những trạng thái nào và chuyển khi nào?
- Ai đổi địa chỉ giao hàng từ giá trị cũ sang giá trị hiện tại?
- Lý do sửa là yêu cầu khách hàng hay điều chỉnh nội bộ?
- Đã có bao nhiêu lần cập nhật giữa ngày tạo và lần sửa cuối?
- Hai API độc lập có cập nhật cùng document khiến một thay đổi bị ghi đè không?
- Có thể chứng minh dữ liệu ở một revision cụ thể để điều tra tranh chấp không?

**Câu trả lời:** Chỉ `createdAt/By` và `lastModifiedAt/By` là **audit metadata trên bản ghi hiện tại**, không phải **lịch sử thay đổi đầy đủ**.

### 1.1. Hai loại dữ liệu cần tách

**Current state (một document):**

~~~javascript
{
  _id: "o901",
  status: "SHIPPED",
  revision: NumberLong(3),
  updated_by: "operator-08",
  updated_at: ISODate("2026-11-20T03:00:00Z")
}
~~~

**History (nhiều sự kiện, lưu riêng):**

~~~javascript
[
  {
    _id: "o901:1",
    order_id: "o901",
    revision: NumberLong(1),
    action: "CREATED",
    actor_id: "customer-22",
    changed_at: ISODate("2026-10-10T02:00:00Z")
  },
  {
    _id: "o901:2",
    order_id: "o901",
    revision: NumberLong(2),
    action: "ADDRESS_CHANGED",
    actor_id: "customer-22",
    changed_at: ISODate("2026-11-01T09:15:00Z")
  },
  {
    _id: "o901:3",
    order_id: "o901",
    revision: NumberLong(3),
    action: "SHIPPED",
    actor_id: "operator-08",
    changed_at: ISODate("2026-11-20T03:00:00Z")
  }
]
~~~

Đây là ví dụ biểu diễn khái niệm; collection lịch sử thật cần quyết định có lưu snapshot, diff, requestId, tenantId, schema version và trường nhạy cảm hay không.

### 1.2. Bảng so sánh nhanh

| Tiêu chí | Last-modified metadata | Full change history |
| --- | --- | --- |
| Nơi lưu | Ngay trong entity hiện tại | Collection/bảng/event log riêng |
| Số bản ghi | Một bản ghi hiện tại | Nhiều sự kiện hoặc snapshot theo revision |
| Ai tạo, lúc nào | Có thể biết | Có thể ghi như event đầu tiên |
| Ai sửa cuối, lúc nào | Có thể biết | Truy xuất được từ event cuối |
| Các lần sửa trung gian | **Không** | **Có**, nếu được ghi từ đầu và không có đường ghi bỏ sót |
| Giá trị trước/sau | **Không** từ metadata đơn thuần | Có nếu thiết kế lưu diff/snapshot |
| Lý do, nguồn request | Không mặc định | Có nếu thêm metadata và capture đúng |
| Truy vấn trạng thái ở thời điểm cũ | Không thể tự tái dựng | Có điều kiện với đầy đủ lịch sử/snapshot |
| Chi phí lưu trữ | Thấp | Tăng theo số lần sửa và payload |
| Rủi ro khi quên ghi | Metadata sai/cũ | Có lỗ hổng lịch sử và sai audit chain |

> **Nguyên tắc:** `@LastModifiedDate` và `@LastModifiedBy` **không biến MongoDB document thành event-sourced aggregate**. Muốn lịch sử đầy đủ cần chọn chiến lược thu thập **mọi đường ghi**, đảm bảo thứ tự và lưu bền vững.

## 2. Phân biệt auditing, logging, journaling, CDC và event sourcing

Các từ này thường được dùng lẫn nhau nhưng giải quyết vấn đề khác:

| Cơ chế | Mục tiêu chính | Có lưu đầy đủ lịch sử nghiệp vụ? |
| --- | --- | --- |
| **Spring Data auditing annotations** | Gắn dấu ai/khi nào tạo/sửa trên entity | Không |
| **Application logs** | Chẩn đoán hành vi ứng dụng và lỗi | Không bảo đảm; thiếu/rotate/redaction |
| **MongoDB journal/WAL** | Phục hồi dữ liệu sau sự cố máy chủ | Không phải hồ sơ audit nghiệp vụ |
| **MongoDB oplog** | Hỗ trợ replication/các cơ chế CDC | Không phải kho lưu lịch sử lâu dài |
| **MongoDB change streams** | Quan sát thay đổi trong deployment hỗ trợ | Có thể làm nguồn thu thập nhưng cần checkpoint/replay/retention |
| **Transactional audit collection** | Persist sự kiện thay đổi cùng business write | Có, trong phạm vi các đường ghi được thiết kế bắt buộc |
| **Transactional outbox** | Gửi sự kiện bền vững đến hệ thống khác | Có thể chứa event audit, nhưng mục đích delivery khác retention audit |
| **Event sourcing** | Lưu các event làm nguồn sự thật và dựng lại state | Có nếu thiết kế event model và replay nhất quán |
| **Snapshots/versioning** | Lưu trạng thái tại một số/all mốc | Có điều kiện, không tự biết actor/reason |
| **Backups/PITR** | Khôi phục dữ liệu hạ tầng về thời điểm trước | Không thay truy vết actor và lý do nghiệp vụ |

### 2.1. Ví dụ dễ nhầm

~~~text
@LastModifiedDate = 2026-11-20 10:00
                 ≠
Đã ghi lại mọi thay đổi trước 10:00.

MongoDB journal tồn tại
                 ≠
Có thể hỏi “ai đổi trường address?” bằng journal.

Change stream chạy
                 ≠
Có đủ lịch sử từ khi collection được tạo.

Outbox event đã được gửi
                 ≠
Event tồn tại vĩnh viễn theo retention policy.
~~~

## 3. Kiến trúc tham khảo cho một order được cập nhật nhiều lần

~~~mermaid
flowchart TD
    A["API / job / consumer"] --> B["Application service"]
    B --> C{"Đường ghi được kiểm soát?"}
    C -->|"Entity save"| D["Spring Data auditing fields"]
    C -->|"Conditional update"| E["Cập nhật metadata tường minh"]
    D --> F["MongoDB transaction"]
    E --> F
    F --> G["orders: current state"]
    F --> H["order_history: append-only event"]
    F --> I["Optional outbox: event delivery"]
    H --> J["API truy vấn lịch sử"]
    I --> K["Dispatcher -> downstream"]
~~~

**Tách responsibility:**

- **Current collection** tối ưu đọc trạng thái hiện tại.
- **History collection** tối ưu truy cứu actor, revision, diff/snapshot và lý do.
- **Outbox collection** (nếu có) tối ưu giao sự kiện đáng tin cậy, retry và trạng thái delivery.

Không buộc cả ba phải có cùng retention. Ví dụ outbox record có thể dọn sau delivery 30 ngày, còn audit history theo yêu cầu pháp lý/doanh nghiệp có thể giữ lâu hơn — nhưng thời hạn cụ thể phải xuất phát từ policy của hệ thống, không tự đặt mặc định.

## 4. Spring Data MongoDB auditing có những annotation nào?

Spring Data cung cấp:

| Annotation | Công dụng | Điền bằng gì? |
| --- | --- | --- |
| `@CreatedDate` | Thời điểm entity được tạo mới theo auditing lifecycle | DateTimeProvider/clock |
| `@LastModifiedDate` | Thời điểm sửa gần nhất qua đường save/auditing | DateTimeProvider/clock |
| `@CreatedBy` | Actor khởi tạo entity | `AuditorAware<T>` hoặc reactive equivalent |
| `@LastModifiedBy` | Actor sửa entity gần nhất | `AuditorAware<T>` hoặc reactive equivalent |
| `@Version` | Optimistic concurrency/version field | Spring Data mapping/versioning, **không phải history** |

### 4.1. Cơ chế tạo và sửa

~~~text
save entity mới
  -> CreatedDate/CreatedBy (nếu auditing được bật)
  -> LastModifiedDate/LastModifiedBy có thể được điền khi tạo,
     phụ thuộc modifyOnCreate và cấu hình auditing

save entity đã tồn tại
  -> LastModifiedDate/LastModifiedBy được cập nhật qua auditing callback
  -> các giá trị last-modified cũ bị thay thế trên current document
~~~

Đây là **metadata tại bản ghi hiện tại**. Không có tập giá trị last-modified trước đó được Spring tự append vào collection lịch sử.

### 4.2. Auditing có thể bị thiếu hoặc sai ngữ cảnh

- Nếu không bật `@EnableMongoAuditing`/`@EnableReactiveMongoAuditing` phù hợp, annotation có thể không được xử lý như kỳ vọng.
- Nếu không có `AuditorAware`/`ReactiveAuditorAware`, trường actor có thể không được điền.
- Background job không có end-user SecurityContext; actor cần được khai báo rõ.
- Update/query-level và raw driver bypass entity save callback có thể **không tự cập nhật auditing fields**.
- App clock không được đồng bộ có thể làm mốc thời gian lệch giữa các instances.
- Một record bị sửa trực tiếp qua `mongosh`/migration không được ứng dụng Java intercept.

## 5. Cấu hình auditing cho Spring MVC / imperative MongoDB

### 5.1. Bật auditing

~~~java
// MongoAuditConfig.java
package com.example.audit;

import java.time.Clock;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing(auditorAwareRef = "auditorProvider")
public class MongoAuditConfig {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean("auditorProvider")
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system-demo");
    }
}
~~~

`"system-demo"` chỉ giúp fixture tự chứa và **không phù hợp production**. Trong service thực, auditor phải đến từ **security principal đã xác thực** hoặc actor của system job được cấp quyền, không tin username do client tự khai.

### 5.2. Lấy actor từ Spring Security

~~~java
import java.util.Optional;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public final class SecurityAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication auth = SecurityContextHolder
            .getContext().getAuthentication();

        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }
        return Optional.of(auth.getName());
    }
}
~~~

Đây là implementation dành cho **imperative security context**. Cần thay bean demo:

~~~java
@Bean("auditorProvider")
AuditorAware<String> auditorProvider() {
    return new SecurityAuditorAware();
}
~~~

Không khai báo **cả hai** bean cùng tên `auditorProvider`. Nếu ứng dụng không dùng Spring Security, có thể lấy actor từ một component context tin cậy khác, nhưng phải tránh truyền user ID tùy ý từ body.

### 5.3. Actor hệ thống cần danh tính riêng

Các loại actor thường gặp:

~~~text
USER       -> account id / subject đã xác thực
SERVICE    -> service principal/canonical workload identity
SCHEDULER  -> tên job + version/owner
MIGRATION  -> deployment/migration ID
UNKNOWN    -> chỉ dùng khi thật sự không thể xác định
~~~

Để tránh trộn hai loại, có thể dùng một record:

~~~java
public record AuditActor(
    String type,
    String id
) {}
~~~

Khi đó auditing field và `AuditorAware<AuditActor>` cần một mapping bền vững phù hợp. Không phải chỉ gắn một string `"admin"` rồi kết luận đã có bằng chứng người thực hiện.

### 5.4. Thời điểm từ đâu?

`@CreatedDate`/`@LastModifiedDate` sử dụng cơ chế cung cấp thời gian của Spring Data Auditing. Có thể cấu hình `DateTimeProvider` nếu cần clock chung/test clock:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import org.springframework.data.auditing.DateTimeProvider;

DateTimeProvider provider(Clock clock) {
    return () -> Optional.of(Instant.now(clock));
}
~~~

Với cấu hình auditing đầy đủ, đặt bean `DateTimeProvider` và chỉ định bằng `dateTimeProviderRef` nếu cần. Phải xác nhận phiên bản Spring Data đang dùng hỗ trợ exact configuration attributes. Chú ý timestamp ở đây do **application clock** cung cấp; không phải immutable server commit timestamp.

## 6. Entity hiện tại có auditing metadata

~~~java
// OrderDocument.java
package com.example.audit;

import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_audit_009")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String status;
    private String deliveryCity;
    private long revision; // Business revision ví dụ, quản lý riêng.

    @CreatedDate
    private Instant createdAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @LastModifiedBy
    private String lastModifiedBy;

    protected OrderDocument() {}

    public OrderDocument(
            String id, String tenantId,
            String status, String deliveryCity) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.deliveryCity = deliveryCity;
        this.revision = 1;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public String getDeliveryCity() { return deliveryCity; }
    public long getRevision() { return revision; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getLastModifiedAt() { return lastModifiedAt; }
    public String getCreatedBy() { return createdBy; }
    public String getLastModifiedBy() { return lastModifiedBy; }

    public void changeCity(String next) {
        this.deliveryCity = next;
    }
}
~~~

Trong ví dụ này `revision` **không phải `@Version`**; nó được dùng minh họa revision nghiệp vụ và cần service cập nhật đúng khi thay đổi state. Nếu dùng `@Version`, Spring Data điều khiển optimistic version theo mapping rules; không tự giả định hai cơ chế revision có thể được cập nhật giống hệt nhau.

### 6.1. Khi insert qua repository

~~~java
// OrderRepository.java
package com.example.audit;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {
}
~~~

~~~java
OrderDocument order = new OrderDocument(
    "o901", "t01", "PENDING", "Hà Nội"
);

OrderDocument saved = orderRepository.insert(order);
// Với auditing config đúng:
//   saved.getCreatedAt() != null
//   saved.getCreatedBy() == "system-demo" (trong fixture)
~~~

**Lưu ý:** Kiểm giá trị auditing trên entity sau insert dựa trên auditing callback/config thực tế; đừng assume các annotations có hiệu lực trong một unit test dùng mock repository hoặc khi chưa bật auditing.

### 6.2. Khi sửa qua `save`

~~~java
OrderDocument current = orderRepository.findById("o901")
    .orElseThrow();
current.changeCity("Đà Nẵng");
OrderDocument savedAgain = orderRepository.save(current);

// lastModifiedAt/lastModifiedBy được gán lại trên current document
// nhưng lịch sử giá trị cũ không tự được ghi ở nơi khác.
~~~

`save` có thể thực hiện replace/upsert document tùy state và mapping. Nếu hai request cùng đọc entity phiên bản cũ, cả hai `save` có nguy cơ **lost update** trừ khi có optimistic locking, predicate version hoặc transaction strategy phù hợp.

## 7. `@LastModifiedDate` KHÔNG được bảo đảm trên mọi đường ghi

### 7.1. `MongoTemplate.updateFirst`

~~~java
Query query = Query.query(
    Criteria.where("id").is("o901")
);

mongoTemplate.updateFirst(
    query,
    new Update().set("deliveryCity", "Huế"),
    OrderDocument.class
);
~~~

Ở đường **update operator trực tiếp**, Spring Data không chạy trọn mapping lifecycle callback như `save(entity)`. Vì vậy không nên dựa vào `@LastModifiedDate` để chắc `lastModifiedAt`/`lastModifiedBy` được tự điền. Có thể update đã thay `deliveryCity` nhưng các trường auditing **vẫn giữ giá trị cũ**.

**Lưu ý:** Cơ chế xử lý `@Version` của Spring Data với một số update operations là một tính năng khác; việc version có thể được tăng tự động không suy ra date/by auditing cũng được update.

### 7.2. Tự cập nhật metadata khi dùng operator update

~~~java
Instant now = clock.instant();
String actorId = trustedActor.id();

Update update = new Update()
    .set("deliveryCity", "Huế")
    .set("lastModifiedAt", now)
    .set("lastModifiedBy", actorId);

mongoTemplate.updateFirst(query, update, OrderDocument.class);
~~~

`clock`/`trustedActor` là dependencies đã được xác thực/configured; đây chỉ là snippet trong service. Cần kiểm `matchedCount` và điều kiện tenant/state/version, không update theo ID một cách thiếu kiểm quyền.

### 7.3. Những đường ghi cần rà soát

| Đường ghi | Tự đi qua entity auditing callbacks? | Kỳ vọng lịch sử đầy đủ |
| --- | --- | --- |
| `MongoRepository.insert/save` | Thường **có** khi bật auditing | **Không** tự có history |
| `MongoTemplate.insert/save(entity)` | Thường có mapping/auditing callbacks | Không tự có history |
| `MongoTemplate.updateFirst/updateMulti` | Không đi qua save entity callbacks như save | Phải tự ghi event |
| `findAndModify` | Query/update operator path, không giả định auditing entity save | Phải tự ghi event |
| `bulkOps` / bulk driver | Không đồng nhất callback/auditing với save từng entity | Phải tự ghi event |
| Aggregation pipeline update | Không đi qua entity save callbacks | Phải tự ghi event |
| Raw MongoDB Java Driver | Không chịu Spring auditing annotations | Phải tự ghi event |
| `mongosh`/migration/admin tool | Bypass application auditing | Phải có audit/migration trail riêng |
| TTL expiry/server background delete | Không phải entity save event | Nếu cần log xóa, dùng chiến lược khác |

Không có nghĩa mọi write đều “sai” nếu bỏ Spring auditing. Điều quan trọng là **định nghĩa một hợp đồng bắt buộc về audit và kiểm soát tất cả đường ghi**.

## 8. `@Version` phát hiện cạnh tranh, nhưng không lưu lịch sử

Một document có thể được sửa đồng thời:

~~~text
Request A đọc order rev=7, city="Hà Nội"
Request B đọc order rev=7, city="Hà Nội"

A ghi city="Huế"
B ghi city="Đà Nẵng"

Nếu thiếu guard/version, B có thể ghi đè A mà không báo xung đột.
LastModifiedAt chỉ cho biết lần cuối; không ghi lại A đã sửa gì.
~~~

### 8.1. `@Version` dùng với entity save

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

Khi lưu entity được mapping theo Spring Data, version hỗ trợ **optimistic locking** trong các đường ghi phù hợp. Nếu một request save entity đã cũ, Spring Data có thể ném `OptimisticLockingFailureException` thay vì âm thầm ghi đè.

**Điều kiện thực tế:** Để phát hiện write failure đáng tin, dùng **acknowledged write concern**; với `w:0` không thể tin exception phản ánh kết quả server.

### 8.2. Version không phải audit trail

~~~javascript
{
  _id: "o901",
  version: NumberLong(13),
  last_modified_by: "operator-08"
}
~~~

Ngay cả khi version là 13, metadata hiện tại **không chứa 12 versions trước**. `@Version` giúp phát hiện ghi cạnh tranh và kiểm soát thứ tự, không tự tạo 12 history documents.

### 8.3. Business revision khác mapping version

Trong ví dụ `OrderDocument` đang có `revision` do ứng dụng quản lý. Hai cách hợp lý:

1. **Mapping version**: dùng `@Version` và API save đã xác minh semantics.
2. **Business revision**: dùng field `revision` bình thường, tăng bằng `$inc` với predicate `revision == expectedRevision`.

Không gắn đồng thời `@Version` vào field rồi **tự động `$inc` thêm lần nữa** nếu chưa hiểu cách Spring Data xử lý `@Version` trong update operators; có thể dẫn tới tăng phiên bản sai.

### 8.4. Revision được dùng để sắp xếp history

Nếu history có:

~~~text
o901:1 CREATED
o901:2 CITY_CHANGED
o901:3 SHIPPED
~~~

thì `revision` là **thứ tự logic** đối với cùng aggregate. Timestamp không nên là thứ tự duy nhất: hai instances có thể có clock lệch, hai event có timestamp giống nhau hoặc commit sau khi timestamp đã được tạo.

## 9. Thiết kế collection lưu lịch sử đầy đủ

Thay vì chỉ sửa current document, tạo collection chuyên dụng, ví dụ `order_history_009`.

### 9.1. Các field nên cân nhắc

| Field | Ví dụ | Tại sao cần |
| --- | --- | --- |
| `_id` | `o901:2` | ID bất biến/unique cho một revision |
| `tenant_id` | `t01` | Tách dữ liệu giữa tenants |
| `order_id` | `o901` | Khóa aggregate |
| `revision` | `2` | Thứ tự logic của thay đổi |
| `command_id` | `cmd-8e72` | Đối soát request/retry |
| `action` | `DELIVERY_CITY_CHANGED` | Tên ý nghĩa nghiệp vụ |
| `actor_type` | `USER`/`SERVICE` | Kiểu chủ thể |
| `actor_id` | `operator-08` | Ai thực hiện (đã xác thực) |
| `occurred_at` | Timestamp UTC | Thời điểm ứng dụng ghi nhận thay đổi |
| `reason_code` | `CUSTOMER_REQUEST` | Lý do đã chuẩn hóa |
| `before_city` / `after_city` | `Hà Nội` / `Huế` | Giá trị được phép lưu theo policy |
| `schema_version` | `1` | Phiên bản payload history |
| `correlation_id` | `req-001` | Nối trace/batch nghiệp vụ |
| `source` | `ADMIN_API` | Đường cập nhật đã thực hiện |

Không phải mọi field đều cần trong mọi hệ thống. **Dữ liệu nhạy cảm** (địa chỉ cụ thể, token, password, thông tin thanh toán) phải được phân loại; “audit đầy đủ” **không có nghĩa phải giữ mọi secret từng tồn tại**.

### 9.2. Ba chiến lược lưu nội dung

| Kiểu history | Ví dụ | Ưu điểm | Nhược điểm |
| --- | --- | --- | --- |
| **Full snapshot per revision** | Lưu toàn bộ order ở rev2 | Truy vấn trạng thái cũ đơn giản | Tốn storage, rủi ro copy PII quá mức |
| **Diff/patch per revision** | `city: Hà Nội → Huế` | Tiết kiệm, rõ field sửa | Replay phức tạp; cần xử lý schema upgrades |
| **Domain event** | `DeliveryCityChanged` với actor/reason | Diễn đạt ý nghĩa nghiệp vụ | Không tự chứa mọi field; replay cần quy tắc |

Trong ví dụ chọn **domain event + before/after của field được phép audit**. Một hệ thống lớn có thể kết hợp snapshots định kỳ với events xen giữa để giảm chi phí replay.

### 9.3. Không coi domain event bất kỳ là dữ liệu đủ để khôi phục

Một event:

~~~javascript
{
  action: "ORDER_SHIPPED",
  order_id: "o901",
  occurred_at: ISODate("2026-11-20T03:00:00Z")
}
~~~

không chứa đủ thông tin để tái dựng mọi field của order. Nếu muốn **point-in-time reconstruction**, phải định nghĩa schema, event order, reducer/replay semantics, initial snapshot và cách xử lý deletes/migrations.

## 10. Entity lịch sử: không tự ghi đè history

~~~java
// OrderHistoryEvent.java
package com.example.audit;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "order_history_009")
public class OrderHistoryEvent {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("order_id")
    private String orderId;

    private long revision;
    private String commandId;
    private String action;
    private String actorType;
    private String actorId;
    private String reasonCode;
    private String beforeCity;
    private String afterCity;
    private Instant occurredAt;
    private int schemaVersion;

    protected OrderHistoryEvent() {}

    public OrderHistoryEvent(
            String id, String tenantId, String orderId,
            long revision, String commandId, String action,
            String actorType, String actorId,
            String reasonCode, String beforeCity,
            String afterCity, Instant occurredAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.revision = revision;
        this.commandId = commandId;
        this.action = action;
        this.actorType = actorType;
        this.actorId = actorId;
        this.reasonCode = reasonCode;
        this.beforeCity = beforeCity;
        this.afterCity = afterCity;
        this.occurredAt = occurredAt;
        this.schemaVersion = 1;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getOrderId() { return orderId; }
    public long getRevision() { return revision; }
    public String getCommandId() { return commandId; }
    public String getAction() { return action; }
    public String getActorId() { return actorId; }
    public String getBeforeCity() { return beforeCity; }
    public String getAfterCity() { return afterCity; }
}
~~~

Thiết kế class không cung cấp public setters để **khuyến khích bất biến ở application layer**. Nhưng Java class không thể ngăn một admin/raw driver `update`/`delete` MongoDB. Để bảo vệ thực sự cần **least-privilege DB roles, phân quyền ghi, backup/retention, monitoring, append-only policy** và trong trường hợp yêu cầu compliance có thể cần lưu trữ bất biến/WORM bên ngoài.

### 10.1. Không dùng `save(history)` làm upsert im lặng

~~~java
mongoTemplate.insert(historyEvent);
~~~

Ưu tiên `insert` khi history event phải là **sự kiện mới**, để duplicate `_id` trả lỗi thay vì vô tình replace bản ghi cũ. Không tự động coi mọi duplicate là “thành công” khi chưa kiểm **tenant, commandId, revision và payload**.

## 11. Khởi tạo collection và index trong môi trường thử nghiệm

~~~javascript
use spring_data_mongodb_lab

db.createCollection("orders_audit_009");
db.createCollection("order_history_009");

db.order_history_009.createIndex(
  { tenant_id: 1, order_id: 1, revision: 1 },
  { unique: true, name: "uq_tenant_order_revision" }
);

db.order_history_009.createIndex(
  { tenant_id: 1, commandId: 1 },
  { unique: true, name: "uq_tenant_command" }
);

db.order_history_009.createIndex(
  { tenant_id: 1, order_id: 1, occurredAt: -1 },
  { name: "ix_history_time" }
);
~~~

**Quan trọng về tên trường:** Entity ở mục 10 dùng `@Field("tenant_id")`, `@Field("order_id")`, nhưng `revision`, `commandId`, `occurredAt` không có alias nên tên BSON mặc định theo Java property. Các index ở `mongosh` phải dùng **tên BSON thực**, không tự đoán snake_case cho field không gắn `@Field`. Với application dùng naming strategy khác, cần kiểm mapping thực tế.

### 11.1. Khi chọn unique index cho commandId

Nếu một `commandId` chỉ unique **trong phạm vi tenant**, index compound `{tenant_id,commandId}` phù hợp. Nhưng nếu nhiều history events hợp lệ được tạo từ cùng một command, unique index đó sẽ gây conflict; cần đổi thành `{tenant_id,commandId,eventSequence}` hoặc tách command log.

Chọn uniqueness dựa trên **hợp đồng nghiệp vụ**, không coi “cứ unique request ID” là đúng cho mọi domain.

### 11.2. Lưu ý với sharding

Unique index trên sharded collection có yêu cầu về shard key/prefix tùy topology và phiên bản. Không suy rằng các compound unique indexes ở ví dụ sẽ hợp lệ nguyên xi trên mọi sharded cluster. Khi có sharding cần thiết kế placement, shard key, transaction routing và unique constraints trước.

### 11.3. Không tạo collection/index bên trong request transaction

Migration/deployment nên tạo collection và index **trước khi** nhận traffic. Đừng để service thay đổi schema/index khi người dùng đang cập nhật order, vừa kéo dài transaction vừa dễ gặp ràng buộc DDL/version.

## 12. Cùng một thao tác cập nhật nhưng ba mức đảm bảo

### 12.1. Chỉ cập nhật current document

~~~java
mongoTemplate.updateFirst(
    query,
    new Update()
        .set("deliveryCity", "Huế")
        .set("lastModifiedAt", clock.instant())
        .set("lastModifiedBy", actorId),
    OrderDocument.class
);
~~~

Kết quả: có **trạng thái hiện tại** và **metadata cuối**, **không có history**.

### 12.2. Cập nhật current rồi insert history nhưng không có transaction

~~~java
mongoTemplate.updateFirst(query, update, OrderDocument.class);
mongoTemplate.insert(historyEvent);
~~~

Nếu insert history lỗi sau khi update đã được ACK, current state đã đổi mà không có history event. Nếu history được insert trước và current update lỗi, lại có event mô tả thay đổi chưa xảy ra.

Hai lệnh được gọi **tuần tự** không đồng nghĩa **atomic**.

### 12.3. Cập nhật current và append history trong cùng transaction

~~~text
MongoDB transaction T1
    |
    +-- guarded update order revision 4 -> 5
    +-- insert history event (orderId, revision 5)
    |
    +-- COMMIT -> cả hai được công nhận cùng lúc
         hoặc
    +-- ABORT  -> không commit bên nào
~~~

Đây là baseline mạnh để đảm bảo current state và history cùng tiến khi nghiệp vụ yêu cầu truy vết đầy đủ.

**Caveat:** Transaction không tự bao phủ script ngoài ứng dụng, raw driver không tham gia session, thao tác database khác client, email/HTTP hoặc thao tác xóa trực tiếp của admin. Cần kiểm soát **mọi đường ghi**.

## 13. MongoDB transaction manager: dùng chung một session

Ví dụ cấu hình phù hợp với một **replica set test** hoặc deployment hỗ trợ transactions:

~~~java
// MongoTransactionConfig.java
package com.example.audit;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        TransactionOptions options = TransactionOptions.builder()
            .readPreference(ReadPreference.primary())
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(
                WriteConcern.MAJORITY.withJournal(true))
            .build();
        return new MongoTransactionManager(factory, options);
    }
}
~~~

Với `@Transactional` imperative, Spring gắn MongoDB session vào transaction context của thread khi phương thức được gọi **qua proxy**.

### 13.1. Cần xác minh

- Topology là replica set/sharded deployment hỗ trợ multi-document transaction.
- `MongoTemplate` trong service dùng **cùng MongoDatabaseFactory** với `MongoTransactionManager`.
- Không dùng `this.methodAnnotatedTransactional()` rồi tin transaction sẽ tự mở.
- Không giữ transaction mở qua HTTP call/SMTP hoặc xử lý kéo dài.
- Commit write concern và read concern được chọn theo mức durability nghiệp vụ.
- Cả collection order/history đã được tạo trước workflow trong test/deployment.

### 13.2. Atomic commit khác độ bền sau failover

Một transaction có thể atomic nhưng nếu commit chỉ được acknowledged theo write concern yếu (ví dụ `w:1`), một commit đã ACK vẫn có thể gặp rủi ro rollback trong failover trước khi majority replication. Chọn majority/journal phù hợp với SLO, nhưng **đừng** nghĩ majority thay backup hay policy retention audit.

## 14. Service ghi state và history trong cùng transaction

Đây là ví dụ trọng tâm: mọi thay đổi địa chỉ ở phạm vi *city* được ghi thành event mới.

### 14.1. Service cập nhật có guard trên revision

~~~java
// OrderChangeService.java
package com.example.audit;

import java.time.Clock;
import java.time.Instant;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderChangeService {
    private final MongoTemplate mongo;
    private final Clock clock;

    public OrderChangeService(
            MongoTemplate mongo, Clock clock) {
        this.mongo = mongo;
        this.clock = clock;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public OrderHistoryEvent changeDeliveryCity(
            String tenantId,
            String orderId,
            long expectedRevision,
            String nextCity,
            String actorId,
            String commandId) {

        requireValid(tenantId, orderId, nextCity, actorId, commandId);
        Instant changedAt = clock.instant();

        Query eligible = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("revision").is(expectedRevision)
        );

        Update change = new Update()
            .set("deliveryCity", nextCity)
            .set("lastModifiedAt", changedAt)
            .set("lastModifiedBy", actorId)
            .inc("revision", 1);

        OrderDocument before = mongo.findAndModify(
            eligible, change,
            FindAndModifyOptions.options().returnNew(false),
            OrderDocument.class
        );

        if (before == null) {
            throw new OrderChangeConflictException(
                "Order missing, wrong tenant or stale revision");
        }

        long nextRevision = expectedRevision + 1;
        OrderHistoryEvent history = new OrderHistoryEvent(
            orderId + ":" + nextRevision,
            tenantId,
            orderId,
            nextRevision,
            commandId,
            "DELIVERY_CITY_CHANGED",
            "USER",
            actorId,
            "CUSTOMER_REQUEST",
            before.getDeliveryCity(),
            nextCity,
            changedAt
        );

        // Nếu history insert thất bại, transaction rollback
        // CẢ order update và insert history.
        return mongo.insert(history);
    }

    private static void requireValid(
            String tenantId, String orderId,
            String city, String actorId, String commandId) {
        if (tenantId == null || tenantId.isBlank()
                || orderId == null || orderId.isBlank()
                || city == null || city.isBlank()
                || actorId == null || actorId.isBlank()
                || commandId == null || commandId.isBlank()) {
            throw new IllegalArgumentException(
                "Missing change command fields");
        }
    }
}
~~~

Trong đó:

~~~java
// OrderChangeConflictException.java
package com.example.audit;

public class OrderChangeConflictException extends RuntimeException {
    public OrderChangeConflictException(String message) {
        super(message);
    }
}
~~~

### 14.2. Giải thích từng bước

1. **Validate** các input bắt buộc; `tenantId`/`actorId` trong production phải đến từ principal/service context đáng tin cậy.
2. **Guard** theo `orderId + tenantId + expectedRevision`. Nếu revision thay đổi trước đó, `findAndModify` không match.
3. **Atomic update** current document, tăng revision đúng một lần.
4. **Return old document** từ `findAndModify(...returnNew(false))`, nhờ đó lịch sử biết giá trị `beforeCity` thực sự ở revision trước.
5. **Insert history** với `_id` ổn định `orderId:nextRevision` trong **cùng transaction**.
6. **Commit** sau khi thân method return qua Spring transactional proxy.

**Quan trọng:** `findAndModify` được thực hiện theo kiểu update operator; vì vậy service **set lastModifiedAt/By tường minh**. Không giả định `@LastModifiedDate` trên entity tự chạy như `save`.

### 14.3. Vì sao đọc `before` từ kết quả update thay vì đọc trước?

Nếu làm:

~~~java
OrderDocument before = mongo.findById(orderId, OrderDocument.class);
mongo.updateFirst(onlyById, update, OrderDocument.class);
mongo.insert(historyFrom(before));
~~~

thì một writer khác có thể cập nhật order giữa `find` và `update` nếu không có guard/transaction phù hợp. `findAndModify` với `expectedRevision` và cùng transaction làm rõ **giá trị nào thật sự được thay đổi**. Transaction khác vẫn có thể gây write conflict, khi ấy service cần phân loại lỗi và cân nhắc retry transaction an toàn.

### 14.4. Kết quả current state

Giả sử trước:

~~~javascript
{
  _id: "o901",
  tenant_id: "t01",
  deliveryCity: "Hà Nội",
  revision: NumberLong(1)
}
~~~

Sau khi command `changeDeliveryCity(..., expectedRevision=1, nextCity="Huế")` commit:

~~~javascript
{
  _id: "o901",
  tenant_id: "t01",
  deliveryCity: "Huế",
  revision: NumberLong(2),
  lastModifiedBy: "operator-08",
  lastModifiedAt: ISODate("2026-11-20T03:00:00Z")
}
~~~

và history:

~~~javascript
{
  _id: "o901:2",
  tenant_id: "t01",
  order_id: "o901",
  revision: NumberLong(2),
  commandId: "cmd-901-2",
  action: "DELIVERY_CITY_CHANGED",
  actorId: "operator-08",
  beforeCity: "Hà Nội",
  afterCity: "Huế"
}
~~~

Timestamp trong JSON là ví dụ minh họa; giá trị thực do `Clock` của service cung cấp tại thời điểm request.

### 14.5. Nếu history bị duplicate?

Giả sử `order_history_009` đã có `_id="o901:2"` nhưng current order vẫn rev1 do dữ liệu bất nhất hoặc test cố ý tạo conflict. `mongo.insert(history)` sẽ bị unique constraint từ chối; với transaction đúng, current order **không được commit** ở rev2.

Không tự xóa bản ghi lịch sử cũ trong catch để “retry cho qua”. Đó là hành động phá audit trail.

## 15. Muốn lịch sử “đầy đủ” phải ghi cả CREATE và DELETE

Service ở mục 14 mới ghi **một kiểu thay đổi**: đổi city. Nếu order được tạo mà không ghi `CREATED` event, rồi bị xóa bằng raw `delete` không có history, thì audit collection vẫn **không đầy đủ**.

### 15.1. Ghi event lúc tạo

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public OrderDocument createOrder(
        String tenantId,
        String orderId,
        String city,
        String actorId,
        String commandId) {

    OrderDocument order = new OrderDocument(
        orderId, tenantId, "PENDING", city
    );

    OrderDocument inserted = mongo.insert(order);

    mongo.insert(new OrderHistoryEvent(
        orderId + ":1",
        tenantId,
        orderId,
        1L,
        commandId,
        "CREATED",
        "USER",
        actorId,
        "ORDER_SUBMITTED",
        null,
        city,
        clock.instant()
    ));

    return inserted;
}
~~~

Đây là **method bổ sung** vào một service có `mongo`/`clock` như mục 14, không phải đoạn hoàn chỉnh độc lập. Hai `insert` chạy trong **cùng transaction**. Nếu history insert lỗi, order insert bị abort.

Khi dùng Spring auditing, `@CreatedDate/By` trên order vẫn mô tả creator/time ở current document. `CREATED` event bổ sung bằng chứng nghiệp vụ **“order được tạo với command này, revision 1”**. Hai cơ chế hỗ trợ nhau, không thay thế nhau.

### 15.2. Xóa mềm (`soft delete`)

Với dữ liệu cần truy vết, nhiều hệ thống dùng:

~~~javascript
{
  _id: "o901",
  deleted: true,
  deleted_at: ISODate("2026-11-20T10:00:00Z"),
  revision: NumberLong(9)
}
~~~

Khi soft delete:

1. Cập nhật `deleted=true` với tenant/revision guard.
2. Append history event `DELETED` hoặc `ARCHIVED` trong cùng transaction.
3. Ẩn order khỏi query nghiệp vụ mặc định.
4. Xác định policy retention, privacy và khả năng restore.

**Không coi soft delete là “không cần data deletion policy”**: quy định xóa/ẩn danh PII có thể yêu cầu xử lý khác.

### 15.3. Xóa vật lý (`hard delete`)

Nếu bắt buộc xóa current document, có thể dùng transaction:

~~~text
findAndRemove order với predicate tenant/revision
    -> lấy dữ liệu trước khi xóa được phép lưu
    -> insert event HARD_DELETED / TOMBSTONE
    -> commit
~~~

Nếu cần tuân thủ “quyền được xóa”, history event có thể **không được phép chứa lại toàn bộ PII vừa xóa**. Giữ metadata tối thiểu theo policy (ví dụ ID đã pseudonymize, action, legal basis) hoặc xóa/ẩn danh cả history khi được yêu cầu hợp pháp.

### 15.4. Mọi mutation path phải được quản trị

Muốn bảo đảm toàn bộ hành trình:

~~~text
CREATE -> UPDATE -> UPDATE -> DELETE
   |        |         |        |
   v        v         v        v
 history  history   history  history
~~~

Các batch jobs, migrations, admin commands, trực tiếp raw driver và thao tác restore cũng phải nằm trong chính sách. Không có thư viện annotation nào tự chứng minh rằng **mọi người có quyền ghi MongoDB** đều đã dùng đúng application service.

## 16. Retry, duplicate và commit result không xác định

Một hệ phân tán phải coi “client bị timeout” và “server không ghi” là **hai khẳng định khác nhau**.

### 16.1. Kịch bản ACK commit bị mất

~~~text
t0  T1 update order rev1 -> rev2.
t1  T1 insert history o901:2 với commandId cmd-002.
t2  MongoDB commit T1 thành công.
t3  Kết nối đứt trước khi client nhận ACK commit.
t4  Client nhận exception / timeout.
~~~

Lúc t4, order **có thể đã** rev2 và history **có thể đã** tồn tại. Nếu API tự chạy lại command với revision 2 → 3 và ID mới, lịch sử sẽ có **hai thay đổi nghiệp vụ** dù khách hàng chỉ gửi một yêu cầu.

### 16.2. Dùng commandId làm idempotency key

Ví dụ:

~~~javascript
db.order_history_009.findOne({
  tenant_id: "t01",
  commandId: "cmd-002"
});
~~~

Nếu tìm thấy event, cần **đối chiếu cùng tenant, aggregate, action, desired payload/fingerprint** rồi trả lại kết quả trước đó nếu thực sự là cùng command. Nếu không tìm thấy ngay lập tức, cũng không tự kết luận transaction chưa commit: query/read concern và outcome chưa chắc chắn cần được đánh giá.

Một triển khai production nên có **idempotent command handler**:

~~~text
Request commandId = X
    |
    +-- Đã có X, cùng fingerprint
    |     -> trả kết quả persisted.
    |
    +-- Đã có X, fingerprint khác
    |     -> reject conflict; không thực hiện lần hai.
    |
    +-- Chưa thấy X, trạng thái commit cũ chưa chắc chắn
    |     -> đối soát hoặc retry theo protocol an toàn.
    |
    +-- X mới, revision đúng
          -> transaction update state + insert history(X).
~~~

**Chú ý:** Service mục 14 là ví dụ **atomic state+history**, nhưng **chưa** cài đầy đủ idempotency reconciliation flow ở cấp API. Điều này cần bổ sung trước production.

### 16.3. Phân biệt hai error labels

| Tình huống | Khuyến nghị khái niệm |
| --- | --- |
| `TransientTransactionError` | Một số lỗi cho phép **retry toàn transaction body mới**, với giới hạn và idempotency |
| `UnknownTransactionCommitResult` | Kết quả commit chưa rõ; **retry commit** theo driver/session khi còn khả dụng, hoặc đối soát |
| Duplicate history `_id` | Có thể event đã tồn tại; đối chiếu payload/command trước khi coi là trùng hợp lệ |
| Stale `revision` | Có writer khác thắng; trả conflict hoặc đọc lại/merge có kiểm soát |
| Validation error | Sửa input/schema, không retry vô hạn |

Đừng viết một `catch(Exception) { retryService(); }` vì có thể tạo side effects trùng và che lỗi logic.

### 16.4. Optimistic concurrency và revision

Với `revision` tự quản lý như mục 14, mỗi mutation dự kiến:

~~~text
expectedRevision = 5
update predicate revision == 5
increment revision -> 6
append history revision 6
~~~

Nếu hai writers đều muốn chuyển 5 → 6, chỉ một workflow hợp lệ có thể commit state+history trong điều kiện thông thường; transaction conflict/conditional update/unique history giúp phát hiện cạnh tranh.

Không dựa vào thứ tự timestamp để “đoán ai ghi sau” rồi khôi phục mất update. **Revision và transaction acknowledgment** mới là nguồn đáng tin cậy hơn cho logic.

## 17. Truy vấn lịch sử có kiểm soát tenant

### 17.1. Lịch sử theo revision trong `mongosh`

~~~javascript
db.order_history_009.find(
  { tenant_id: "t01", order_id: "o901" },
  {
    _id: 1,
    revision: 1,
    action: 1,
    actorId: 1,
    occurredAt: 1,
    beforeCity: 1,
    afterCity: 1
  }
).sort({ revision: 1 });
~~~

Kết quả là **lịch sử trong phạm vi tenant t01 và order o901**. Một API production phải enforce tenant trong query từ **security context**; không lấy tenant tùy ý từ URL mà không kiểm quyền.

### 17.2. Repository method

~~~java
// OrderHistoryRepository.java
package com.example.audit;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderHistoryRepository
        extends MongoRepository<OrderHistoryEvent, String> {

    List<OrderHistoryEvent>
    findByTenantIdAndOrderIdOrderByRevisionAsc(
        String tenantId, String orderId);
}
~~~

Với history nhỏ có thể trả `List`; nếu một order có hàng trăm nghìn events thì cần phân trang/cursor streaming theo revision và tránh giữ toàn bộ kết quả trong RAM.

### 17.3. Keyset pagination theo revision

~~~java
Query page = Query.query(
    Criteria.where("tenantId").is(authenticatedTenant)
        .and("orderId").is(orderId)
        .and("revision").gt(afterRevision)
)
.with(Sort.by(Sort.Direction.ASC, "revision"))
.limit(100);

List<OrderHistoryEvent> events =
    mongoTemplate.find(page, OrderHistoryEvent.class);
~~~

Import `org.springframework.data.domain.Sort` cùng `Criteria`/`Query`. Dùng business revision làm cursor thường ổn hơn pagination `skip` trên hàng triệu events, nhưng phải đảm bảo revision monotonic và retention không tạo gap bất thường.

**Không nói rằng gap là chắc chắn lỗi** nếu hệ thống intentionally chỉ ghi event cho một tập operations hoặc đã áp retention. Muốn lịch sử **đầy đủ**, định nghĩa invariant: với mỗi successful mutation phải có đúng một history entry hoặc số event theo contract.

### 17.4. Timeline query theo timestamp

~~~javascript
db.order_history_009.find({
  tenant_id: "t01",
  order_id: "o901",
  occurredAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ occurredAt: 1, revision: 1 });
~~~

Dùng UTC và interval `[start,end)` để tránh lặp biên. Nhưng **thứ tự nghiệp vụ nên dựa trên revision** trong cùng aggregate; timestamp chỉ hữu ích cho lọc/report.

## 18. Lấy state ở quá khứ: yêu cầu dữ liệu nào?

### 18.1. Muốn state ở revision 5

Nếu history lưu **full snapshot sau mỗi write**, có thể lấy snapshot revision 5 trực tiếp.

Nếu history chỉ lưu **diff events**, cần:

1. Initial state hoặc snapshot gần nhất trước rev5.
2. Tất cả events từ snapshot tới rev5.
3. Reducer/replay logic xử lý schema version và field semantics.
4. Bảo đảm không thiếu event, duplicate hoặc sai thứ tự.

### 18.2. Ví dụ reducer khái niệm

~~~java
OrderState applyEvent(
        OrderState current,
        OrderHistoryEvent event) {

    if (event.getRevision() != current.revision() + 1) {
        throw new IllegalStateException(
            "History has a missing or reordered revision");
    }

    if ("DELIVERY_CITY_CHANGED".equals(event.getAction())) {
        return current.withDeliveryCity(
            event.getAfterCity(),
            event.getRevision()
        );
    }

    throw new UnsupportedOperationException(
        "Unknown event type: " + event.getAction());
}
~~~

`OrderState` và `withDeliveryCity(...)` ở đây là kiểu/hàm minh họa cho snapshot/replay, chưa phải class được định nghĩa trong bài. Cần khai báo đầy đủ cùng reducer cho `CREATED`, `DELETED`, migration events và business rules nếu làm event sourcing thật.

### 18.3. “Full history” cũng có thể không đủ

Nếu event chỉ ghi `OrderApproved` mà không ghi trạng thái shipping address trước/sau, bạn **không thể** khôi phục shipping address ở thời điểm đó từ event này. “Đầy đủ” là một **hợp đồng về phạm vi thông tin**, không phải tên collection.

### 18.4. Thời điểm event khác thời điểm commit

`occurredAt` trong ứng dụng thường được tạo **trước commit**. Nếu transaction chờ vài giây vì write concern/replication, timestamp đó không phải server commit timestamp.

Muốn đối chiếu ordering/độ bền phải dùng revision, transaction semantics và (nếu có) metadata CDC/operation time theo hợp đồng thích hợp. Không suy commit order tuyệt đối từ `Instant.now()` ở nhiều nodes.

## 19. Change streams và CDC có thay transactional history không?

MongoDB change streams cho phép quan sát insert/update/replace/delete trên replica set/sharded deployment phù hợp. Nó có thể dùng để xây **read model hoặc kho lịch sử tập trung** khi kiến trúc đủ điều kiện.

### 19.1. Luồng CDC

~~~mermaid
flowchart LR
    A["MongoDB current collection"] --> B["Change stream consumer"]
    B --> C["Normalize event / metadata"]
    C --> D["Audit datastore"]
    B --> E["Resume token checkpoint"]
    D --> F["History queries"]
~~~

### 19.2. Nhưng CDC có nhiều giới hạn

- **Không tự biết actor/reason** nếu current document/command không chứa thông tin đó.
- Update event có thể chỉ chứa `updateDescription` (các field thay đổi), không phải **before document** đầy đủ.
- `fullDocument: "updateLookup"` có thể tra current document **đã thay đổi thêm** tại thời điểm lookup; đừng coi đó là snapshot đúng ngay lúc event gốc nếu có concurrent writes.
- **Pre-images/post-images** yêu cầu cấu hình và có retention/availability constraints; không mặc định có vô hạn.
- Resume token có thể không còn khi oplog history vượt retention và consumer outage kéo dài.
- Consumer có thể xử lý lại events sau reconnect; cần idempotency/checkpoint.
- Application bypass, migrations và direct admin operations vẫn xuất hiện như DB changes nhưng không mang ngữ nghĩa business đầy đủ.

### 19.3. Khi nào chọn CDC?

CDC hữu ích nếu muốn quan sát **mọi đường ghi được MongoDB phát**, kể cả driver ngoài Spring Data, và chuyển đổi vào một kho khác. Nhưng nếu yêu cầu **business audit bắt buộc và đồng thời** với thay đổi order, **transactional history cùng current state** thường có hợp đồng chặt hơn.

Một chiến lược kết hợp:

~~~text
App transaction: current + domain history
                         |
              Change stream trên history
                         |
           Archive / index / analytics
~~~

Ở đây source of truth cho ý nghĩa nghiệp vụ là **history record đã được app persist**, còn change stream được dùng để phân phối/replicate sang hệ khác.

## 20. Bảo mật và tính tin cậy của audit trail

### 20.1. Không cho người dùng tự khai “tôi là ai”

Sai:

~~~java
history.setActorId(request.getActorId());
~~~

Nếu actorId lấy trực tiếp từ HTTP body mà không được xác thực, người dùng có thể giả người khác.

Đúng về nguyên tắc:

~~~java
String actorId = authenticatedPrincipal.subject();
String tenantId = authenticatedPrincipal.tenantId();
~~~

`authenticatedPrincipal` là interface/trừu tượng của ứng dụng, không phải Java built-in. Với background job, dùng service account và lưu correlation ID/trigger origin rõ ràng.

### 20.2. Không sao chép secret vào lịch sử

Ví dụ người dùng đổi mật khẩu:

~~~text
KHÔNG lưu:
beforePassword = "plaintext-old"
afterPassword  = "plaintext-new"
~~~

Nên lưu:

~~~javascript
{
  action: "PASSWORD_CHANGED",
  actor_id: "user-22",
  occurred_at: ISODate("2026-11-20T03:00:00Z"),
  changed_fields: ["password"]
}
~~~

Đừng lưu password hash, token, API key, full credit card hay thông tin cá nhân nhạy cảm khi không có cơ sở/nhu cầu pháp lý cụ thể.

### 20.3. PII, retention và quyền được xóa

Audit có thể cần giữ dữ liệu để tuân thủ yêu cầu pháp lý, nhưng cũng có nghĩa vụ minimization/retention:

- Phân loại từng field và mục đích lưu.
- Mã hóa at rest/in transit theo chính sách.
- Phân quyền đọc history chặt hơn đọc current state nếu cần.
- Xác định thời gian giữ lại, ẩn danh/pseudonymize/redact hợp pháp.
- Tách payload và metadata; trường nhạy cảm có thể được tokenize hoặc không ghi.
- Không bật TTL index xóa history chỉ vì muốn giảm storage mà chưa duyệt policy.

### 20.4. Bảo vệ khỏi sửa/xóa lịch sử

Một collection MongoDB thông thường **không tự bất biến** đối với người có quyền update/delete/admin. Nên:

1. Cho application role ghi history theo `insert`, tránh grant update/delete không cần thiết (tùy quyền MongoDB hỗ trợ).
2. Tách quyền vận hành/migration và có audit log của thao tác quản trị.
3. Giám sát xóa/sửa history bất thường.
4. Backup và kiểm tra khả năng restore, đặc biệt disaster recovery.
5. Nếu yêu cầu chống sửa/xóa cấp độ pháp lý, cân nhắc archive WORM/immutable storage, ký/hashing event chains hoặc external evidence service **được threat-model đúng**.

Hash chaining có thể giúp phát hiện sửa trái phép nhưng **không ngăn kẻ có toàn quyền sửa cả chain và khóa ký**, trừ khi anchor/khóa/backup nằm ngoài miền tin cậy có thể bị xâm phạm.

### 20.5. History không phải log chứa mọi HTTP payload

HTTP request body có thể chứa secrets, định dạng lớn hoặc dữ liệu không được phép lưu. History nên chứa **những field/transition cần giải trình** và fingerprint/metadata đủ xác thực nguồn, không dump nguyên request/response một cách không kiểm soát.

## 21. Auditing trong ứng dụng reactive Spring Data MongoDB

Reactive application có lifecycle và actor context khác imperative.

### 21.1. Bật reactive auditing

~~~java
// ReactiveAuditConfig.java
package com.example.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.mongodb.config.EnableReactiveMongoAuditing;
import reactor.core.publisher.Mono;

@Configuration
@EnableReactiveMongoAuditing(
    auditorAwareRef = "reactiveAuditorProvider"
)
public class ReactiveAuditConfig {

    @Bean("reactiveAuditorProvider")
    ReactiveAuditorAware<String> reactiveAuditorProvider() {
        return () -> Mono.just("system-demo");
    }
}
~~~

Đây là bean **demo**. Production phải lấy actor từ reactive security context hoặc service principal được xác thực. Nếu ứng dụng chỉ có imperative MongoDB thì không cần bật reactive auditing chỉ vì dependency Reactor tồn tại.

### 21.2. Lấy actor từ WebFlux Security

~~~java
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public final class ReactiveSecurityAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .filter(auth ->
                auth != null && auth.isAuthenticated()
                    && !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName);
    }
}
~~~

Bean:

~~~java
@Bean("reactiveAuditorProvider")
ReactiveAuditorAware<String> reactiveAuditorProvider() {
    return new ReactiveSecurityAuditorAware();
}
~~~

Chỉ dùng **một** `reactiveAuditorProvider`. Với Spring Security OAuth2/JWT, `Authentication.getName()` có thể là subject hoặc tên do adapter thiết lập; cần xác nhận nó là **stable principal ID** đúng chính sách, không suy rằng tên hiển thị luôn là định danh bất biến.

### 21.3. Vì sao ThreadLocal không đủ?

Reactive flows có thể đổi execution thread mà vẫn duy trì `Reactor Context`. `SecurityContextHolder` kiểu imperative không phải nguồn actor đáng tin cậy cho WebFlux reactive pipelines. Nếu dùng thread-local actor không đúng context, history có thể ghi:

~~~text
actor = null
actor = "SYSTEM"
actor = user từ một request trước (nếu code tự quản lý ThreadLocal sai)
~~~

Trong reactive auditing, dùng `ReactiveAuditorAware`; trong custom service có thể truyền `AuditContext` đã xác thực thông qua reactive chain. Không tự đặt `ThreadLocal` rồi cho rằng Reactor sẽ giữ actor đúng.

### 21.4. Reactive repository save vẫn không tạo history đầy đủ

~~~java
Mono<OrderDocument> saved = reactiveOrderRepository.save(order);
~~~

Nếu reactive auditing được bật và callback đi qua mapping pipeline, current entity có thể được điền `lastModifiedAt/By`. Nhưng `Mono` của save **không tự phát ra 10 prior versions** hay ghi 10 events trong `order_history_009`.

Tương tự imperative, reactive `ReactiveMongoTemplate.updateFirst(...)` không đồng nhất với lifecycle `save(entity)`. Những update operators trực tiếp cần set metadata/history theo application service.

## 22. Reactive transaction: state + history phải được ghép tuần tự

### 22.1. Cấu hình reactive transaction manager

~~~java
// ReactiveMongoTxConfig.java
package com.example.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class ReactiveMongoTxConfig {
    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }

    @Bean
    TransactionalOperator auditTransactionOperator(
            ReactiveMongoTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
~~~

Transaction reactive dùng **Reactor Context** để truyền session. Trong cùng một transaction MongoDB, driver **không hỗ trợ chạy song song các operations trên cùng session**.

### 22.2. Ghi history sau khi update matched

~~~java
// ReactiveOrderChangeService.java
package com.example.audit;

import java.time.Clock;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderChangeService {
    private final ReactiveMongoTemplate mongo;
    private final TransactionalOperator transactions;
    private final Clock clock;

    public ReactiveOrderChangeService(
            ReactiveMongoTemplate mongo,
            TransactionalOperator transactions,
            Clock clock) {
        this.mongo = mongo;
        this.transactions = transactions;
        this.clock = clock;
    }

    public Mono<OrderHistoryEvent> changeDeliveryCity(
            String tenantId, String orderId,
            long expectedRevision, String nextCity,
            String actorId, String commandId) {

        return Mono.defer(() -> {
            var now = clock.instant();
            Query eligible = Query.query(
                Criteria.where("id").is(orderId)
                    .and("tenantId").is(tenantId)
                    .and("revision").is(expectedRevision)
            );
            Update change = new Update()
                .set("deliveryCity", nextCity)
                .set("lastModifiedAt", now)
                .set("lastModifiedBy", actorId)
                .inc("revision", 1);

            return mongo.findAndModify(
                    eligible,
                    change,
                    FindAndModifyOptions.options()
                        .returnNew(false),
                    OrderDocument.class
                )
                .switchIfEmpty(Mono.error(
                    new OrderChangeConflictException(
                        "Not found or stale revision")))
                .flatMap(before -> {
                    OrderHistoryEvent event =
                        new OrderHistoryEvent(
                            orderId + ":" + (expectedRevision + 1),
                            tenantId, orderId,
                            expectedRevision + 1,
                            commandId,
                            "DELIVERY_CITY_CHANGED",
                            "USER", actorId,
                            "CUSTOMER_REQUEST",
                            before.getDeliveryCity(),
                            nextCity, now
                        );
                    return mongo.insert(event);
                });
        }).as(transactions::transactional);
    }
}
~~~

**Semantics:** `findAndModify` và `insert(history)` được subscribe **tuần tự** trong cùng reactive transaction. Nếu history insert thất bại hoặc update không tìm được order, transaction abort và current state không được commit.

Đây là minh họa phục vụ nội dung: production cần validation, security context, policy reason code, idempotency reconciliation và transaction options chính thức. Đừng lấy actor/tenant từ input client không xác thực.

### 22.3. Phản ví dụ: `Mono.when` trong cùng transaction

~~~java
// KHÔNG dùng:
Mono.when(
    mongo.updateFirst(eligible, update, OrderDocument.class),
    mongo.insert(historyEvent)
).as(transactions::transactional);
~~~

Hai Publisher có thể cùng chạy trong **một session transaction** — thao tác parallel không được hỗ trợ, và history được tạo trước khi biết update có thực sự match hay không. Dùng `flatMap`/`then` có thứ tự như trên.

### 22.4. Không tự `subscribe()` bên trong transaction

~~~java
// Sai:
@Transactional
public Mono<Void> change(...) {
    mongo.updateFirst(...).subscribe();
    mongo.insert(history).subscribe();
    return Mono.empty();
}
~~~

Hai subscriptions có thể tạo luồng/context độc lập, không đảm bảo cùng session hay commit. Trả về **một Publisher đã compose toàn bộ công việc** để WebFlux/consumer/StepVerifier subscribe một lần.

### 22.5. Cancellation không chứng minh MongoDB đã rollback

Nếu HTTP request bị cancel sau khi driver gửi commit, transaction có thể đã commit dù client không nhận được acknowledgment. Cần xử lý **unknown outcome** bằng stable commandId, revision và reconciliation giống imperative.

## 23. Audit có cần ghi nhận attempt thất bại?

Cần phân biệt:

1. **History of committed state changes**: các thay đổi thực sự được commit.
2. **Security/operational audit of attempted actions**: kể cả lần bị từ chối hoặc lỗi trước commit.

Nếu transaction bị abort, history event ghi **trong cùng transaction** cũng abort. Đây là hành vi đúng cho log của **committed change**, nhưng không ghi lại “người dùng A đã cố sửa order B nhưng bị từ chối”.

### 23.1. Thiết kế hai lớp

~~~text
Business change history:
  -> append event cùng transaction business.
  -> chỉ có committed changes.

Security/attempt log:
  -> ghi độc lập theo policy, không bị rollback cùng business.
  -> có thể có rejected/denied/rate-limited attempts.
~~~

### 23.2. Không bắt buộc ghi attempt vào cùng collection

Security audit event có thể chứa request ID, actor đã xác thực, hành động, quyết định cho phép/từ chối và thời điểm; **không** lưu raw credentials hay thông tin nhạy cảm chưa phân loại.

Khi ghi attempt ở một hệ riêng, nó có thể tạm không đồng bộ với business transaction; mục tiêu ở đây là **bằng chứng đã có hành động thử**, chứ không phải state revision.

### 23.3. Vì sao listener AFTER_ROLLBACK không đủ?

Nếu access control từ chối request **trước khi transaction/event được tạo**, sẽ không có event domain được publish và listener `AFTER_ROLLBACK` không chạy. Security audit phải phát sinh tại **chỗ quyết định security/business**, không chỉ phụ thuộc callback transaction.

Nếu muốn log cả failed attempt ngay cả khi application crash, phải thiết kế delivery bền vững/queue hoặc hệ thống audit độc lập — không thể có bằng chứng tuyệt đối từ callback in-memory.

## 24. Migration, backfill và giới hạn “lịch sử từ ngày nào”

Giả sử hệ thống đã có 3 triệu orders từ năm trước, rồi hôm nay mới bật auditing và tạo `order_history_009`.

### 24.1. Không tự bịa lịch sử quá khứ

Bạn có thể backfill một **baseline snapshot**:

~~~javascript
{
  _id: "o901:baseline",
  order_id: "o901",
  action: "BASELINE_IMPORT",
  baseline_at: ISODate("2026-11-20T00:00:00Z"),
  known_revision: NumberLong(1),
  historical_completeness: "FROM_BASELINE_ONLY"
}
~~~

Nhưng không được tạo giả các events `CREATED`/`CHANGED` ngày xưa nếu không có nguồn chứng cứ. Baseline chỉ biết **trạng thái ở thời điểm lấy mẫu**, không biết chính xác lịch sử trước đó.

### 24.2. Đánh dấu phạm vi đầy đủ

Định nghĩa metadata:

~~~text
historyTrackingStartedAt
baselineSource
baselineChecksum
historySchemaVersion
coverageStatus = COMPLETE_FROM_START | FROM_BASELINE | PARTIAL
~~~

Chúng giúp API/đội kiểm toán không nhầm “có một history collection” với “có lịch sử đầy đủ từ khi order sinh ra”.

### 24.3. Chạy migration đồng thời với traffic

Nếu backfill đang diễn ra khi orders được cập nhật:

- Cần snapshot/consistency strategy rõ ràng.
- Không tự ghi đè revision mới bằng baseline cũ.
- Có checkpoint/cursor và idempotent restart.
- Có phát hiện gaps/duplicates.
- Có rollback và chạy lại an toàn.

Một migration có thể cần read concern, change stream resume token hoặc tạm chuyển quyền ghi theo kế hoạch. **Không** tự thao tác collection trên production mà chưa có design/runbook.

### 24.4. Sửa/audit các thay đổi từ hệ thống cũ

Script migration dùng raw driver có thể ghi đúng entity state nhưng **không được auditing annotation tự gắn actor**. Hãy đặt actor dạng service/migration ID và phát history sự kiện `MIGRATION_APPLIED` theo quy tắc hiện hành, hoặc lưu một migration log độc lập được duyệt.

## 25. Hiệu năng, kích thước và index

### 25.1. Chi phí mỗi thay đổi

Với transactional history, một lần sửa order thường có:

~~~text
1 current document update
+ 1 append history insert
+ transaction coordination overhead
+ index maintenance
+ replication/journal durability work
~~~

Lượng ghi và storage thường tăng so với chỉ update một document; đây là chi phí của truy vết và atomicity.

### 25.2. Index history theo access pattern

Cho query:

~~~javascript
db.order_history_009.find({
  tenant_id: "t01",
  order_id: "o901"
}).sort({ revision: 1 });
~~~

index:

~~~javascript
{ tenant_id: 1, order_id: 1, revision: 1 }
~~~

phù hợp việc lọc theo tenant/order và sắp xếp theo revision, đồng thời unique constraint bảo vệ duplicate revision.

Index `{tenant_id,commandId}` phục vụ đối soát idempotency. Nhưng **mỗi index là một write amplification** trên collection append-heavy. Không thêm index không có query thực.

### 25.3. Batch history không được bỏ bảo đảm

Bulk migration hoặc import có thể ghi nhiều history events, nhưng `bulkOps(UNORDERED)` không tự là transaction. Nếu một batch lỗi, các events khác có thể đã được persist. Nếu cần atomic state+history cho từng aggregate, hãy chia transaction theo phạm vi logic và thiết kế retry/partial progress.

### 25.4. Không nhét history vô hạn vào array trong current document

Anti-pattern:

~~~javascript
{
  _id: "o901",
  history: [
    /* hàng trăm nghìn entries tăng mãi */
  ]
}
~~~

Document có giới hạn BSON size; array tăng vô hạn dẫn tới document growth, write contention và chi phí update/đọc lớn. Collection lịch sử riêng thường phù hợp khi số lượng events không bị giới hạn nhỏ và ổn định.

### 25.5. Chọn snapshot interval khi replay chậm

Nếu cần dựng lại state rev100.000, việc replay 100.000 events mỗi lần đọc có thể tốn thời gian. Một chiến lược là snapshot mỗi N revisions (ví dụ 500, chọn qua benchmark), sau đó replay phần còn lại.

Nhưng snapshots cũng phải gắn revision/schema version, có checksum/cách verify và retention policy; không dùng một snapshot bị sửa sai làm bằng chứng history đầy đủ.

### 25.6. Metrics hữu ích

| Metric | Ý nghĩa |
| --- | --- |
| `audit.history.insert_failures` | Lỗi append history |
| `audit.transaction.abort_rate` | Conflict hoặc lỗi transaction |
| `audit.revision_conflicts` | Stale write/optimistic locking |
| `audit.command_duplicates` | Retry/idempotency |
| `audit.coverage_gaps` | Current revision thiếu history tương ứng |
| `audit.history_write_latency` | Chi phí ghi thêm history |
| `audit.history_query_p95` | Chi phí truy vấn timeline |
| `audit.retention_backlog` | Dữ liệu quá hạn cần xử lý |
| `audit.unauthorized_access` | Cố gắng truy vấn lịch sử trái quyền |
| `audit.cdc_lag` | Độ trễ khi đẩy history sang kho phân tích |

Tránh metric labels theo từng `orderId`/`userId`/`commandId` vì cardinality không giới hạn; dùng trace/log bảo mật để điều tra theo ID riêng.

## 26. Kiểm thử tích hợp: audit metadata không tự trở thành history

Unit test chỉ mock repository không chứng minh callback auditing, MongoDB transaction, index uniqueness hoặc mapping field thực sự chạy. Test các invariant trên MongoDB test instance.

### 26.1. Điều kiện môi trường

- Spring Boot + Spring Data MongoDB phù hợp với version dự án.
- MongoDB **replica set test** để kiểm multi-document transaction (một-node replica set đủ cho commit/abort cơ bản, không mô phỏng failover).
- Các beans `MongoAuditConfig`, `MongoTransactionConfig`, `OrderChangeService`.
- `MongoTemplate` và transaction manager cùng `MongoDatabaseFactory`.
- Tạo collections trước khi chạy transaction.
- Mỗi test dùng fixture riêng và cleanup chỉ trên DB test được quản lý.
- **Không** đặt `@Transactional` trên test method/class nếu đang muốn quan sát commit/rollback của service, vì outer test transaction có thể che kết quả thật.

### 26.2. Test metadata và transaction history

~~~java
// MongoAuditingHistoryIntegrationTest.java
package com.example.audit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@DataMongoTest
@Import({
    MongoAuditConfig.class,
    MongoTransactionConfig.class,
    OrderChangeService.class
})
class MongoAuditingHistoryIntegrationTest {
    private static final String TENANT = "it-audit-009";
    private static final String ORDER = "it-order-009";

    @Autowired MongoTemplate mongo;
    @Autowired OrderChangeService service;

    @BeforeEach
    void prepare() {
        if (!mongo.collectionExists(OrderDocument.class)) {
            mongo.createCollection(OrderDocument.class);
        }
        if (!mongo.collectionExists(OrderHistoryEvent.class)) {
            mongo.createCollection(OrderHistoryEvent.class);
        }

        clearFixture();
        mongo.insert(new OrderDocument(
            ORDER, TENANT, "PENDING", "Hà Nội"
        ));
    }

    @AfterEach
    void cleanup() {
        clearFixture();
    }

    private void clearFixture() {
        mongo.remove(
            Query.query(
                Criteria.where("id").is(ORDER)
                    .and("tenantId").is(TENANT)
            ),
            OrderDocument.class
        );

        mongo.remove(
            Query.query(
                Criteria.where("orderId").is(ORDER)
                    .and("tenantId").is(TENANT)
            ),
            OrderHistoryEvent.class
        );
    }

    @Test
    void insertFillsAuditingMetadataButNotHistory() {
        OrderDocument current =
            mongo.findById(ORDER, OrderDocument.class);

        assertThat(current).isNotNull();
        assertThat(current.getCreatedAt()).isNotNull();
        assertThat(current.getCreatedBy()).isEqualTo("system-demo");

        // Phép insert entity không tự tạo history record.
        assertThat(mongo.count(
            Query.query(
                Criteria.where("orderId").is(ORDER)
            ),
            OrderHistoryEvent.class
        )).isZero();
    }

    @Test
    void transactionUpdatesCurrentAndAppendsHistory() {
        OrderHistoryEvent written = service.changeDeliveryCity(
            TENANT, ORDER, 1L,
            "Huế", "operator-08", "cmd-it-009-1"
        );

        OrderDocument current =
            mongo.findById(ORDER, OrderDocument.class);

        assertThat(current.getDeliveryCity()).isEqualTo("Huế");
        assertThat(current.getRevision()).isEqualTo(2L);
        assertThat(current.getLastModifiedBy())
            .isEqualTo("operator-08");
        assertThat(current.getLastModifiedAt()).isNotNull();

        assertThat(written.getId()).isEqualTo(ORDER + ":2");
        assertThat(written.getBeforeCity()).isEqualTo("Hà Nội");
        assertThat(written.getAfterCity()).isEqualTo("Huế");
        assertThat(written.getRevision()).isEqualTo(2L);
        assertThat(written.getActorId()).isEqualTo("operator-08");

        assertThat(mongo.findById(
            ORDER + ":2", OrderHistoryEvent.class
        )).isNotNull();
    }

    @Test
    void staleRevisionCannotOverwriteOrAppendHistory() {
        service.changeDeliveryCity(
            TENANT, ORDER, 1L,
            "Huế", "operator-08", "cmd-it-009-first"
        );

        assertThatThrownBy(() ->
            service.changeDeliveryCity(
                TENANT, ORDER, 1L,
                "Đà Nẵng", "operator-09", "cmd-it-009-stale"
            )
        ).isInstanceOf(OrderChangeConflictException.class);

        OrderDocument current =
            mongo.findById(ORDER, OrderDocument.class);
        assertThat(current.getDeliveryCity()).isEqualTo("Huế");
        assertThat(current.getRevision()).isEqualTo(2L);

        assertThat(mongo.count(
            Query.query(
                Criteria.where("orderId").is(ORDER)
            ),
            OrderHistoryEvent.class
        )).isEqualTo(1L);
    }

    @Test
    void duplicateHistoryAbortsCurrentUpdate() {
        // Gieo một history event có cùng _id revision 2,
        // để mô phỏng conflict và xác minh atomic rollback.
        mongo.insert(new OrderHistoryEvent(
            ORDER + ":2", TENANT, ORDER, 2L,
            "cmd-existing", "DELIVERY_CITY_CHANGED",
            "USER", "operator-existing",
            "DATA_REPAIR", "Hà Nội", "Cần Thơ",
            java.time.Instant.now()
        ));

        assertThatThrownBy(() ->
            service.changeDeliveryCity(
                TENANT, ORDER, 1L,
                "Huế", "operator-08", "cmd-conflict"
            )
        ).isInstanceOf(DuplicateKeyException.class);

        OrderDocument after =
            mongo.findById(ORDER, OrderDocument.class);
        assertThat(after.getDeliveryCity()).isEqualTo("Hà Nội");
        assertThat(after.getRevision()).isEqualTo(1L);

        // Event cũ vẫn nguyên; transaction lỗi không xóa lịch sử cũ.
        assertThat(mongo.findById(
            ORDER + ":2", OrderHistoryEvent.class
        ).getCommandId()).isEqualTo("cmd-existing");
    }

    @Test
    void queryUpdateDoesNotAutomaticallyCreateHistory() {
        OrderDocument before =
            mongo.findById(ORDER, OrderDocument.class);
        var previousLastModified = before.getLastModifiedAt();

        mongo.updateFirst(
            Query.query(
                Criteria.where("id").is(ORDER)
                    .and("tenantId").is(TENANT)
            ),
            new Update().set("deliveryCity", "Hải Phòng"),
            OrderDocument.class
        );

        OrderDocument after =
            mongo.findById(ORDER, OrderDocument.class);
        assertThat(after.getDeliveryCity())
            .isEqualTo("Hải Phòng");

        // updateFirst không đi qua save-entity auditing callback
        // như repository.save(entity):
        assertThat(after.getLastModifiedAt())
            .isEqualTo(previousLastModified);
        assertThat(mongo.count(
            Query.query(
                Criteria.where("orderId").is(ORDER)
            ),
            OrderHistoryEvent.class
        )).isZero();
    }
}
~~~

**Giới hạn:** Ví dụ dùng `@DataMongoTest` theo cấu trúc Spring Boot 3.x. Một số package/test starters có thể khác trên Spring Boot 4 hoặc project riêng. Nếu Spring Data version dịch duplicate-key qua wrapper khác, xem exception/cause trước khi chỉnh test assertion; **phép kiểm rollback current state** mới là yêu cầu cốt lõi.

### 26.3. Test này chưa chứng minh “full history” cho toàn hệ thống

Test ở trên cố tình tạo fixture bằng `mongo.insert(new OrderDocument(...))` mà **không ghi CREATED event**, để chứng minh auditing annotation **không tự tạo history**. Vì vậy fixture chỉ có event revision2 sau khi đổi city, **không phải lịch sử hoàn chỉnh từ CREATE**.

Để chứng minh hệ thống full history, cần thêm test dùng `createOrder(...)` (mục 15), các transition khác, soft/hard delete, admin/migration paths và detector phát hiện gap. Không khẳng định tất cả production writes đã audited chỉ từ một test happy path.

### 26.4. Test dưới concurrent writes

Hai requests cùng expectedRevision=1 có thể chạy cạnh tranh. Trong môi trường replica set:

1. Chuẩn bị order revision1.
2. Cho hai calls `changeDeliveryCity(...,expectedRevision=1)` chạy đồng thời.
3. Chấp nhận một transaction có thể bị `WriteConflict`/transient error hoặc no-match tùy interleaving.
4. Kiểm cuối cùng current revision2, một history event revision2 theo invariant.
5. Kiểm không có history event “ảo” cho request bị từ chối.

Không test concurrency bằng cách chỉ run hai `save` trên mock entity. Kết quả thực phụ thuộc transaction isolation, query predicate và unique indexes.

### 26.5. Test failover/unknown commit result

Thông thường không thể mô phỏng chính xác `UnknownTransactionCommitResult` bằng cách ném `IllegalStateException` **bên trong** transaction body. Để test commit ambiguity cần fault injection riêng ở ranh giới commit, nhiều-node test cluster hoặc test harness hỗ trợ driver error labels.

**Không ngắt primary/stepdown production hay MongoDB dùng chung chỉ để học.**

## 27. Kiểm thử reactive auditing và history

### 27.1. Test auditing metadata

Với bean `ReactiveAuditConfig`, `ReactiveMongoTemplate` và repository:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import reactor.test.StepVerifier;

OrderDocument sample = new OrderDocument(
    "rx-audit-009", "rx-tenant", "PENDING", "Hà Nội"
);

StepVerifier.create(reactiveMongoTemplate.insert(sample))
    .assertNext(saved -> {
        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getCreatedBy()).isEqualTo("system-demo");
    })
    .verifyComplete();
~~~

Đây là đoạn trong một **test method** đã inject `ReactiveMongoTemplate`, chạy với reactive auditing config phù hợp. Cần cleanup fixture sau test và đảm bảo collection test tồn tại. Không lấy nó làm bằng chứng full history.

### 27.2. Test state + history transaction

~~~java
StepVerifier.create(
    reactiveOrderChangeService.changeDeliveryCity(
        "rx-tenant", "rx-audit-009", 1L,
        "Huế", "rx-operator", "rx-command-1"
    )
).assertNext(event -> {
    assertThat(event.getBeforeCity()).isEqualTo("Hà Nội");
    assertThat(event.getAfterCity()).isEqualTo("Huế");
}).verifyComplete();

StepVerifier.create(
    reactiveMongoTemplate.findById(
        "rx-audit-009", OrderDocument.class
    )
).assertNext(order -> {
    assertThat(order.getRevision()).isEqualTo(2L);
    assertThat(order.getDeliveryCity()).isEqualTo("Huế");
}).verifyComplete();
~~~

Test cần **replica set**, collection được tạo trước transaction và cả hai beans cùng `ReactiveMongoDatabaseFactory`. Test tiếp trường hợp history duplicate: sau `expectError`, truy vấn current state xác nhận **vẫn rev1/city cũ**.

Nếu chỉ gọi:

~~~java
Mono<OrderHistoryEvent> deferred =
    reactiveOrderChangeService.changeDeliveryCity(...);
~~~

nhưng không subscribe, lệnh MongoDB thường **chưa chạy**. `StepVerifier` xác nhận publisher thật sự được thực thi; không dùng `block()` trong WebFlux runtime.

### 27.3. Reactive actor phải được gắn context khi test

Với `ReactiveSecurityAuditorAware`, unit/integration tests cần tạo security principal trong Reactor Context bằng tiện ích Spring Security test phù hợp (ví dụ `contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))`). Nếu không, auditor có thể là `Mono.empty()` và `createdBy` không được set.

Không sửa test để luôn ép actor `"SYSTEM"` rồi kết luận code production sẽ lấy đúng người dùng.

## 28. Những sai lầm thường gặp

| Quan niệm/triệu chứng | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| “Có `@LastModifiedDate` là có lịch sử mọi lần sửa” | Annotation ghi đè metadata hiện tại | Tạo history events riêng |
| “`@Version` lưu mọi phiên bản” | Version chỉ kiểm cạnh tranh | Append history/snapshot theo revision |
| “MongoDB journal là audit log” | Journal phục vụ recovery, không actor/reason | Domain history + access policy |
| “Application logs đã đủ audit” | Logs có thể thiếu/rotate/đổi format | Persist canonical audit records |
| “Change stream có pre-image bất kỳ lúc nào” | Pre-images cần cấu hình, retention hữu hạn | Đọc server docs/config, bổ sung app history |
| “UpdateFirst tự cập nhật LastModifiedDate” | Không đi qua save entity auditing callback | Set metadata tường minh |
| “Bulk write tự gọi auditing callback cho từng entity” | Bulk API có lifecycle khác | Service/history policy cho bulk |
| “Một save tạo tự động audit event” | Spring annotations không append collection riêng | Transactional history insert |
| “Cứ hai lệnh Java liên tiếp là atomic” | Lệnh thứ hai lỗi không undo lệnh đầu | MongoDB transaction |
| “Transaction commit rồi là đã có external email” | External side effect ngoài MongoDB | Outbox và consumer idempotency |
| “History có revision10 là có 10 events” | Có thể thiếu CREATE/một số mutation paths | Check coverage/gaps |
| “Xóa order không cần event” | Hard delete làm mất current state | Tombstone/history theo policy |
| “Timestamp đủ sắp lịch sử chính xác” | Clock skew, equal timestamps, pre-commit time | Business revision + transaction semantics |
| “ActorId từ HTTP body là bằng chứng” | Có thể giả danh | Authenticated principal/service identity |
| “Audit đầy đủ phải lưu mọi secret” | Vi phạm data minimization | Chỉ lưu field được duyệt/redacted |
| “History class không setter nghĩa là bất biến” | Admin/raw driver vẫn có thể update/delete | DB roles, monitoring, immutable archive |
| “Duplicate history luôn nên bỏ qua” | Có thể payload/command conflict | Đối chiếu fingerprint |
| “Timeout commit nghĩa chưa ghi” | Commit có thể đã thành công | Unknown outcome + idempotency |
| “Reactive SecurityContextHolder là đủ” | Reactive dùng Reactor Context | ReactiveAuditorAware |
| “`Mono.when` trong một tx giúp tăng throughput” | Parallel same-session unsupported | Tuần tự transaction operations |
| “Migration backfill tự biết ai sửa trước đó” | Chỉ có snapshot hiện tại | Đánh dấu baseline coverage |
| “Có unique index trên order history là audit không thể bị xóa” | Unique không chặn delete/admin | Least privilege, backup, external evidence |
| “Single-node majority test chứng minh failover resilience” | Majority 1-node chỉ cần một member | Multi-node chaos test riêng |
| “Có history thì khỏi cần backup” | History có thể bị xóa/sai cùng DB | Backup/restore và retention policy |

## 29. Checklist thiết kế auditing production

1. **Xác định phạm vi:** chỉ cần “ai/khi nào sửa gần nhất” hay cần “toàn bộ lịch sử” từ khi tạo đến khi xóa?
2. **Định nghĩa audit coverage:** những entity, field, action và hệ thống nào phải được ghi?
3. **Bật đúng auditing mode**: `@EnableMongoAuditing` cho imperative, `@EnableReactiveMongoAuditing` cho reactive.
4. **Kiểm `AuditorAware`/`ReactiveAuditorAware`** lấy actor từ identity đáng tin cậy; không nhận actor giả từ HTTP body.
5. **Kiểm thời gian**: UTC, clock sync, source of time, phân biệt occurredAt và commit.
6. **Không suy metadata là lịch sử**: `@LastModifiedDate`/`@LastModifiedBy` chỉ giữ giá trị cuối.
7. **Không suy version là lịch sử**: `@Version` phát hiện cạnh tranh, không tự persist prior states.
8. **Inventory tất cả write paths**: repository save, MongoTemplate update, bulk, raw driver, migrations, admin, TTL, reactive flows.
9. **Set metadata tường minh** trên các update operator paths không đi qua entity auditing callback.
10. **Chọn history schema**: action, actor, tenant, aggregate ID, revision, request/command ID, before/after có chọn lọc, reason, schema version.
11. **Đặt unique indexes** theo invariant `tenant+order+revision` và idempotency key phù hợp.
12. **Ghi event CREATE, UPDATE, DELETE** cùng policy nếu yêu cầu lịch sử từ đầu tới cuối.
13. **Dùng MongoDB transaction** cho current state và history khi cần all-or-nothing.
14. **Guard current state** bằng tenant, expected revision, business predicate; không tin save thông thường tránh được mọi lost update.
15. **Bảo đảm cùng database factory/session** giữa transactional operations.
16. **Chọn commit write concern** theo yêu cầu durability; majority/journal không thay backup.
17. **Định nghĩa unknown commit outcome**, không retry mù và không tạo command ID mới cho cùng nghiệp vụ.
18. **Gắn actor hệ thống rõ ràng** cho jobs/migrations, phân biệt user/service/migration.
19. **Thiết kế privacy policy**: whitelist fields, redaction, encryption, access controls và thời gian giữ.
20. **Không coi collection tự bất biến**: quyền cập nhật/xóa và admin cần bị giới hạn/giám sát.
21. **Định nghĩa baseline** khi bật auditing trên dữ liệu cũ; không tạo lịch sử quá khứ từ suy đoán.
22. **Dùng revision làm thứ tự logic** và query history có tenant guard/keyset pagination.
23. **Đánh giá CDC/change stream** theo retention/resume token và metadata bị thiếu; không thay thế app business semantics một cách máy móc.
24. **Phân biệt committed change history với denied attempt/security audit**.
25. **Test trên MongoDB replica set thật**: insert metadata, operator bypass, transaction rollback, unique index, stale revision, reactive session.
26. **Có reconciliation jobs** để đối chiếu current revisions và history coverage.
27. **Có observability**: history insert failures, revision conflict, gaps, idempotency duplicates và latency.
28. **Có runbook** để restore/repair history khi phát hiện lỗ hổng mà không giả mạo evidence.

## 30. Bài thực hành có đáp án

### Bài 1 — Last-modified

Current order có `createdAt`, `createdBy`, `lastModifiedAt` và `lastModifiedBy`. Có thể biết ai sửa trước người cuối cùng không?

**Đáp án:** Không từ các field ấy. Chúng chỉ giữ creator và lần sửa cuối. Muốn biết các lần trung gian phải lưu history events hoặc nguồn lịch sử tin cậy khác từ trước đó.

### Bài 2 — Annotation

Nêu annotation phù hợp cho thời điểm tạo và thời điểm sửa gần nhất.

**Đáp án:**

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;
~~~

Chúng cần auditing config/đường mapping tương ứng; không tự append history.

### Bài 3 — Ai sửa?

`@LastModifiedBy` lấy ID người dùng từ đâu?

**Đáp án:** Từ `AuditorAware<T>` trong imperative hoặc `ReactiveAuditorAware<T>` trong reactive auditing, dựa trên identity đã xác thực hoặc service principal. Không tin input actor tùy ý từ body.

### Bài 4 — Sự khác nhau giữa `save` và `updateFirst`

Vì sao `updateFirst` có thể sửa `deliveryCity` nhưng không cập nhật `lastModifiedAt`?

**Đáp án:** Update operator không đi qua pipeline entity save/auditing callback như `save(entity)`. Hãy set audit metadata tường minh hoặc dùng một write path đã được chuẩn hóa ở application service.

### Bài 5 — `@Version`

Document version 8 có nghĩa MongoDB giữ lại đủ version 1–7 không?

**Đáp án:** Không. `@Version` hỗ trợ optimistic locking/versioning current state, không tự persist các bản cũ.

### Bài 6 — Hai write liên tiếp

Service update order rồi insert history, không dùng transaction. Insert history lỗi. Điều gì có thể xảy ra?

**Đáp án:** Order đã đổi nhưng history thiếu. Hai câu lệnh Java tuần tự không tạo atomicity xuyên document/collection.

### Bài 7 — Transaction

Viết annotation để cùng rollback update và insert history trong imperative Spring Data MongoDB.

**Đáp án:**

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void changeOrderAndAppendHistory(...) {
    // MongoTemplate operations trên cùng MongoDatabaseFactory.
}
~~~

Phải có manager, topology replica set/sharded cluster hỗ trợ và lời gọi qua proxy; annotation không tự bảo đảm mọi dependency dùng cùng session.

### Bài 8 — Trả về giá trị trước update

MongoTemplate API nào giúp update theo predicate và lấy document cũ trong một operation?

**Đáp án:** `findAndModify` với `FindAndModifyOptions.options().returnNew(false)` và predicate gồm ID, tenant, expected revision; vẫn cần transaction nếu còn insert history riêng.

### Bài 9 — Race condition

Hai request cùng đọc revision 3 rồi đều muốn ghi revision 4. Làm thế nào tránh silent overwrite?

**Đáp án:** Dùng optimistic version/guard `revision==3`, transaction khi ghi history, và unique history key theo revision. Request không thắng phải xử lý conflict/retry theo nghiệp vụ, không tự ghi đè.

### Bài 10 — History fields

Ngoài actor và timestamp, cần thông tin gì để giải trình một lần đổi city?

**Đáp án:** Tenant, aggregate ID, revision, action, before/after city, reasonCode, commandId/request correlation, schema version và source nếu chính sách cần. Không bắt buộc lưu địa chỉ chi tiết hoặc secret.

### Bài 11 — Event ID

Tại sao `_id="o901:4"` có ích cho audit history?

**Đáp án:** Mỗi revision có ID ổn định và unique. Lần append trùng bị constraint phát hiện; khi retry phải đối chiếu payload/command, không vô điều kiện bỏ qua duplicate.

### Bài 12 — Unknown commit

MongoDB có thể đã commit state+history, nhưng client timeout. Có thể gọi lại toàn nghiệp vụ với `commandId` mới không?

**Đáp án:** Không mặc định. Dùng stable command ID và đối soát persisted history, phân loại lỗi commit; retry sai có thể tạo revision/event thứ hai.

### Bài 13 — Created event

Order được insert bằng repository, có `@CreatedDate`, nhưng không có event `CREATED`. History có thể gọi là đầy đủ từ đầu không?

**Đáp án:** Không. Phải append CREATED event theo hợp đồng (thường cùng transaction) nếu yêu cầu reconstruct/timeline từ thời điểm tạo.

### Bài 14 — Hard delete

Xóa order bằng `deleteById` có tự lưu prior values ở history không?

**Đáp án:** Không. Cần một đường xóa được kiểm soát: findAndRemove/guard, event/tombstone, transaction và retention/privacy policy phù hợp.

### Bài 15 — Oplog

Có thể coi MongoDB oplog như kho audit history vô hạn để điều tra mọi revision không?

**Đáp án:** Không. Oplog phục vụ replication, có retention hữu hạn và không tự chứa actor/reason nghiệp vụ. CDC dựa trên oplog cần checkpoint/resume và source semantics phù hợp.

### Bài 16 — Full document lookup

Change stream `fullDocument:"updateLookup"` có luôn trả chính xác snapshot tại thời điểm update gốc không?

**Đáp án:** Không nên giả định như vậy khi có concurrent writes; lookup có thể trả state mới hơn. Muốn previous/new images cần cấu hình/retention phù hợp hoặc ghi diff/history trong transaction.

### Bài 17 — Replay

History chỉ lưu `ORDER_SHIPPED` và timestamp, không ghi địa chỉ. Có thể dựng địa chỉ ở revision đó không?

**Đáp án:** Không chỉ từ event ấy. Cần snapshot/diff events đủ thông tin và reducer xử lý schema đúng.

### Bài 18 — Timestamp

Hai application instances ghi cùng order và có clock lệch. Nên sắp xếp theo `occurredAt` hay revision?

**Đáp án:** Theo business revision cho thứ tự của cùng aggregate. Timestamp dùng cho lọc/report nhưng không chứng minh commit order tuyệt đối.

### Bài 19 — Auditing và user identity

Client gửi `actorId="admin"` trong JSON body. Có nên đưa vào `@LastModifiedBy` không?

**Đáp án:** Không. Lấy từ authenticated principal/service identity. Nếu có delegation, lưu thêm principal thực, delegator và lý do theo policy.

### Bài 20 — Secret

Trong lịch sử đổi password, có nên lưu old/new password plaintext để “đầy đủ” không?

**Đáp án:** Không. Ghi action, actor, timestamp, trường thay đổi và metadata tối thiểu được phê duyệt. Không lưu credentials/secrets.

### Bài 21 — Migration

Hôm nay bật audit cho dữ liệu đã tồn tại một năm. Có thể tự tạo 20 revision quá khứ từ current state không?

**Đáp án:** Không. Chỉ backfill baseline snapshot với nguồn/time/coverage rõ; không bịa các transitions không có chứng cứ.

### Bài 22 — Reactive actor

Ứng dụng WebFlux dùng `SecurityContextHolder` thread-local để lấy actor nhưng một pipeline đổi thread. Rủi ro?

**Đáp án:** Actor có thể thiếu/sai. Dùng `ReactiveAuditorAware` dựa trên Reactor/Reactive Security context, hoặc truyền context tin cậy trong pipeline.

### Bài 23 — Reactive transaction

Hai lệnh `update order` và `insert history` đang được gọi bằng `Mono.when(...)` bên trong một `TransactionalOperator`. Có vấn đề gì?

**Đáp án:** Chúng có thể chạy song song trong cùng session, điều MongoDB reactive driver không hỗ trợ; insert history còn cần phụ thuộc vào kết quả update. Dùng `flatMap` tuần tự trong transaction.

### Bài 24 — Attempt thất bại

Người dùng không có quyền thử sửa order; request bị chặn trước transaction. Có thể thấy attempt này trong committed-change history không?

**Đáp án:** Không mặc nhiên. Cần security/attempt audit độc lập với business committed-change history; tránh đưa denied attempt vào collection “đã thay đổi” như thể write thành công.

### Bài 25 — Admin có thể xóa audit

Entity history class chỉ có constructor/getters, không setter. Có làm nó immutable trên MongoDB không?

**Đáp án:** Không. MongoDB roles có quyền update/delete/admin vẫn có thể sửa/xóa. Cần least privilege, monitoring, backups và nếu cần WORM/external evidence.

### Bài 26 — Complete audit coverage

Một integration test `repository.save` cho thấy `@LastModifiedDate` thay đổi. Đã đủ để khẳng định mọi write đều audited chưa?

**Đáp án:** Chưa. Cần kiểm `updateFirst`, bulk, raw driver, migrations, deletes, reactive writes và mọi integration paths; đồng thời kiểm history collection có event tương ứng.

### Bài 27 — Backup

Nếu current state + history dùng transaction majority/journal, còn cần backup không?

**Đáp án:** Có. Majority/journal không bảo vệ khỏi xóa nhầm đã commit, code bug, mất toàn vùng hoặc admin phá history; cần backup, restore test và retention được duyệt.

### Bài 28 — Phạm vi bảo đảm

Một hệ thống có history bắt đầu từ năm 2026, nhưng dữ liệu từ năm 2024. API nên hiển thị “toàn bộ lịch sử” không?

**Đáp án:** Không. Nên biểu diễn `FROM_BASELINE_ONLY` hoặc metadata coverage tương đương, nêu rõ **lịch sử ghi nhận từ mốc nào** và khoảng trống đã biết.

## Tài liệu tham khảo

- [Spring Data MongoDB — Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html): `@EnableMongoAuditing`, `@EnableReactiveMongoAuditing`, cấu hình actor/time và mapping metadata.
- [Spring Data MongoDB — Entity Callbacks](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): lifecycle mapping, `AuditingEntityCallback` và giới hạn các đường ghi.
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking): `@Version`, version guard và conflict.
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `save`, `updateFirst`, `findAndModify` và bulk operations.
- [Spring Data MongoDB — Client Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): Mongo transaction manager, reactive session và atomic multi-document writes.
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html): `AuditorAware` và `ReactiveAuditorAware` trong hệ Spring Data.
- [Spring Data MongoDB — `MongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): mapping/CRUD, entity-based vs operator-based writes.
- [Spring Data MongoDB — `ReactiveMongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): reactive write/result and transaction flow.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): atomic commit/abort, transaction restrictions và durability.
- [MongoDB Manual — `findAndModify`](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/): atomic conditional update với trả về document trước/sau.
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): unique keys cho history revision/command id.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): CDC, event resume tokens và vận hành consumer.
- [MongoDB Manual — Pre- and Post-Images](https://www.mongodb.com/docs/manual/changestreams/#change-streams-with-document-pre--and-post-images): điều kiện hỗ trợ và retention của images.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): majority/journal/acknowledgment và rủi ro rollback.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): retry behavior, ambiguity và topology.
- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/): lựa chọn current document, referenced history và indexing.
