# Thông tin tạo, sửa và trách nhiệm cập nhật metadata

Trong ứng dụng Java sử dụng Hibernate/JPA, ngoài dữ liệu nghiệp vụ như mã đơn hàng, số tiền hoặc trạng thái, một entity thường cần lưu **metadata về quá trình tạo và sửa đổi**:

- **`createdAt`**: bản ghi được tạo lúc nào?
- **`updatedAt` / `lastModifiedAt`**: bản ghi được cập nhật lần gần nhất lúc nào?
- **`createdBy`**: tác nhân nào tạo bản ghi?
- **`updatedBy` / `lastModifiedBy`**: tác nhân nào thực hiện thay đổi gần nhất?
- Đôi khi còn có **nguồn thay đổi**, **correlation ID**, **lý do thay đổi**, **revision**, **deletedAt`** hoặc **job ID**.

Những trường này có vẻ đơn giản, nhưng sai lầm về **quyền sở hữu và thời điểm cập nhật** rất dễ làm metadata không nhất quán. Một entity có `updatedAt` nhưng bulk HQL UPDATE không đổi trường đó; service cập nhật `createdAt` bằng dữ liệu client; database trigger thay timestamp sau khi Hibernate đã giữ bản cũ trong persistence context; hoặc `@PreUpdate` ghi nhận một thay đổi rồi transaction rollback — tất cả đều có thể khiến thông tin audit bị hiểu sai.

Trong chương **Sự kiện và mở rộng**, cần trả lời ba câu hỏi:

1. **Ai chịu trách nhiệm cập nhật metadata?** Entity callback JPA, cơ chế Hibernate timestamp, Spring Data JPA auditing, application service hay database?
2. **Metadata được cập nhật vào thời điểm nào?** Khi `persist()`, khi dirty checking/flush, lúc SQL chạy hay khi transaction commit?
3. **Những đường ghi nào có thể bỏ qua cơ chế đó?** Bulk JPQL/HQL, native SQL, script migration, ETL, nhiều ứng dụng dùng chung DB, upsert và triggers.

Mục tiêu của bài học là xây một chính sách nhất quán, có thể kiểm thử và vận hành được. **Không có một annotation duy nhất giải quyết đầy đủ tất cả các câu hỏi trên.**

---

## 1. Metadata tạo/sửa là gì?

Giả sử bảng đơn hàng:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(19, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    version BIGINT NOT NULL
);
~~~

Một row có thể là:

| Trường | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| `id` | 9001 | Định danh bản ghi |
| `tenant_id` | 42 | Phạm vi dữ liệu |
| `status` | `PAID` | Trạng thái nghiệp vụ |
| `created_at` | `2026-11-15T03:00:00Z` | Lúc tạo row |
| `updated_at` | `2026-11-15T08:25:00Z` | Lúc cập nhật gần nhất |
| `created_by` | `user-17` | Actor tạo row |
| `updated_by` | `batch-2026-11` | Actor/systems sửa gần nhất |
| `version` | `6` | Phiên bản dùng kiểm tra cạnh tranh |

### 1.1. Các nhóm metadata không được trộn lẫn

| Loại | Ví dụ | Dùng để làm gì? |
| --- | --- | --- |
| **Creation metadata** | `createdAt`, `createdBy` | Ghi nhận nguồn gốc row |
| **Modification metadata** | `updatedAt`, `updatedBy` | Ghi nhận thay đổi gần nhất |
| **Concurrency metadata** | `@Version` | Phát hiện concurrent update/stale write |
| **Business time** | `paidAt`, `shippedAt`, `effectiveFrom` | Sự kiện/thời điểm có ý nghĩa nghiệp vụ |
| **Deletion metadata** | `deletedAt`, `deletedBy` | Soft-delete và nguyên nhân xóa |
| **Audit history** | revision, before/after, event log | Truy vết *toàn bộ* chuỗi thay đổi |
| **Trace metadata** | correlationId, requestId, jobId | Nối thao tác với log/job/message |

Ví dụ `paidAt` không phải `updatedAt`. Đơn hàng có thể sửa địa chỉ giao hàng sau khi đã thanh toán, khiến `updatedAt` đổi nhưng `paidAt` vẫn giữ nguyên. Tương tự, `version` không phải đồng hồ và không nói ai sửa bản ghi.

### 1.2. “Lần sửa gần nhất” phải được định nghĩa rõ

Một hệ thống cần quyết định `updatedAt` nghĩa là:

- Lúc **entity state thay đổi và được flush**?
- Lúc **database thực thi UPDATE**?
- Lúc **transaction commit**?
- Lúc **sự kiện nghiệp vụ xảy ra**?
- Lúc **hệ thống nguồn thông báo thay đổi**?

Đây là các thời điểm khác nhau. Phần lớn các annotation auditing phổ thông ghi nhận thời điểm ứng dụng/ORM xử lý ghi, **không phải một commit timestamp chính xác**. Nếu báo cáo pháp lý hoặc hệ thống phân tán cần commit-time ordering, cần thiết kế riêng theo DB/event log.

## 2. Một chính sách trách nhiệm rõ ràng

Một thiết kế tốt phải chọn **nguồn có thẩm quyền** cho từng trường.

| Trường | Chủ sở hữu điển hình | Bên không nên tự ý ghi |
| --- | --- | --- |
| `createdAt` | Hibernate/JPA/Spring Data auditing hoặc DB | API client, mapper cập nhật tùy ý |
| `updatedAt` | Cùng cơ chế được chuẩn hóa cho mọi đường ghi | Controller/DTO tùy ý |
| `createdBy` | Server-side actor resolver/application context | User gửi raw actor ID không kiểm chứng |
| `updatedBy` | Server-side actor resolver; với DB trigger cần context bảo mật | Raw request JSON |
| `version` | ORM optimistic locking hoặc cơ chế version của DB | DTO sửa tự do |
| `paidAt` | Domain operation thanh toán | Generic auditing listener |
| `deletedAt` | Soft-delete domain/application policy | Generic save không hiểu delete |
| Audit history | Audit subsystem / append-only event log | Một cột updatedAt đơn lẻ |

### 2.1. Tránh hai chủ sở hữu cùng ghi một cột

Không nên vừa:

~~~java
@UpdateTimestamp
private Instant updatedAt;
~~~

vừa có listener `@PreUpdate` tự set `updatedAt`, lại vừa có database trigger luôn đổi `updated_at`, **mà không định nghĩa bên nào là nguồn thật**.

Những cơ chế đó có thể cạnh tranh, tạo timestamp khác nhau hoặc khiến state trong Hibernate bị stale. Chọn một nguồn authoritative, hoặc định nghĩa rõ cách đọc lại giá trị do DB tạo.

### 2.2. Ba kiến trúc thường gặp

1. **ORM-owned:** Hibernate/JPA callbacks hoặc Spring Data auditing điền metadata; phù hợp nếu hầu hết writes đều qua một ứng dụng ORM.
2. **Database-owned:** DEFAULT/trigger tự điền timestamp cho mọi SQL writers; phù hợp nếu nhiều dịch vụ, scripts hoặc ETL cùng ghi DB.
3. **Hybrid có chủ đích:** Database sở hữu timestamps, còn application sở hữu actor/source metadata và chuyển context đáng tin cậy; cần rõ ownership và cách đồng bộ giá trị.

Không có lựa chọn mặc định đúng cho mọi hệ thống. Điều quan trọng là tính **nhất quán xuyên tất cả write paths**.

## 3. Vòng đời JPA: callback được kích hoạt ở đâu?

JPA cung cấp lifecycle callbacks:

| Callback | Điểm gắn thông thường |
| --- | --- |
| `@PrePersist` | Trước khi persist entity mới vào DB |
| `@PostPersist` | Sau thao tác persist/insert tương ứng theo lifecycle |
| `@PreUpdate` | Trước khi thực thi UPDATE entity theo dirty checking |
| `@PostUpdate` | Sau UPDATE entity tương ứng |
| `@PreRemove` | Trước khi remove entity |
| `@PostRemove` | Sau remove entity |
| `@PostLoad` | Sau khi entity được load/refresh phù hợp |

Trong thực tế, **thời điểm chính xác liên quan flush/statement/ID strategy có thể khác theo provider và mapping**; không nên dựa vào callback để tuyên bố đã commit.

~~~mermaid
flowchart TD
    A["Entity mới"] --> B["persist()"]
    B --> C["@PrePersist"]
    C --> D["INSERT tại thời điểm phù hợp"]
    D --> E["@PostPersist"]
    E --> F{"Transaction"}
    F -->|"Commit"| G["Dữ liệu bền vững"]
    F -->|"Rollback"| H["Không có commit"]
    I["Managed entity được sửa"] --> J["Dirty checking / flush"]
    J --> K{"Có entity UPDATE?"}
    K -->|"Có"| L["@PreUpdate, UPDATE, @PostUpdate"]
    K -->|"Không"| M["Không mặc định có PreUpdate"]
    L --> F
~~~

### 3.1. @PreUpdate không có nghĩa “mỗi lần gọi setter”

Ví dụ:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
order.setStatus(OrderStatus.PAID);
order.setStatus(OrderStatus.PAID);
~~~

JPA không gọi `@PreUpdate` mỗi lần setter chạy. Callback gắn với lifecycle update được provider xác định trong quá trình synchronization/flush.

Nếu cuối cùng entity không dirty hoặc không tạo UPDATE, **đừng mặc định `@PreUpdate` sẽ được gọi**. Một số mapping/bytecode enhancement có chi tiết khác nhau; hãy kiểm thử đường ghi thật.

### 3.2. @PostUpdate chưa chắc là commit

Một `@PostUpdate` có thể đã chạy, nhưng transaction sau đó bị rollback vì constraint hoặc lỗi ở thao tác khác. Vì vậy **không gửi email, webhook hay message không thể rollback ngay trong JPA callback** chỉ vì thấy PostUpdate.

### 3.3. Callback không phải nơi thích hợp cho DB I/O tùy tiện

Lifecycle callback nên nhẹ và dự đoán được. Không dùng callback để gọi repository, tạo hàng loạt entity khác, chạy query tùy tiện hoặc gọi HTTP external service. Những thao tác đó có thể gây flush đệ quy, coupling, ordering khó đoán hoặc side effects khi transaction rollback.

## 4. Cách 1 — JPA @PrePersist và @PreUpdate cho timestamps

Một cách **không phụ thuộc Spring Data** là dùng JPA lifecycle callbacks trong `@MappedSuperclass`:

~~~java
package com.example.persistence;

import jakarta.persistence.*;
import java.time.Instant;

@MappedSuperclass
public abstract class TimestampedEntity {

    @Column(
        name = "created_at",
        nullable = false,
        updatable = false
    )
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    protected void onCreate() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = Instant.now();
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
~~~

Entity kế thừa:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder extends TimestampedEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false)
    private String status;

    @Version
    private Long version;

    protected PurchaseOrder() {}

    public void changeStatus(String nextStatus) {
        if (!java.util.Objects.equals(status, nextStatus)) {
            status = nextStatus;
        }
    }
}
~~~

### 4.1. Vì sao set cả createdAt và updatedAt khi insert?

Nhiều hệ thống định nghĩa:

- `createdAt`: thời điểm INSERT.
- `updatedAt`: thời điểm ghi gần nhất, **bao gồm lúc tạo**.

Khi đó cả hai đều có giá trị khi row mới được tạo. Nếu domain muốn `updatedAt = null` cho tới lần sửa đầu tiên, đó là contract khác và database column phải cho phép NULL.

Cần quyết định thống nhất giữa API, báo cáo, index và integration tests.

### 4.2. Có nên dùng Instant.now() trực tiếp?

`Instant.now()` đơn giản, nhưng phụ thuộc system clock của JVM, khó kiểm thử với thời gian giả và có thể lệch giữa nhiều nodes.

Với ứng dụng quan trọng, nên có cách **inject Clock** hoặc một audit time provider có thể kiểm soát. JPA entity listener không tự được Spring quản lý trong mọi cấu hình, nên việc dependency injection vào listener cần thiết kế rõ. Spring Data auditing cung cấp `DateTimeProvider` hữu ích cho trường hợp này.

### 4.3. @Column(updatable=false) bảo vệ ở tầng nào?

~~~java
@Column(name = "created_at", updatable = false)
private Instant createdAt;
~~~

tuyên bố cho JPA provider **không đưa cột này vào SQL UPDATE thông thường do ORM sinh**. Nó không phải một database constraint tự động bảo vệ mọi đường ghi:

- Native SQL vẫn có thể UPDATE cột.
- DBA/script vẫn có thể sửa.
- Một ứng dụng khác vẫn có thể ghi.
- Đổi giá trị Java field bằng reflection/mapper chưa chắc có tác dụng SQL như developer tưởng.

Muốn createdAt bất biến ở tầng DB, cân nhắc quyền ghi, trigger hoặc constraint/policy tương ứng.

### 4.4. MappedSuperclass có lợi ích gì?

`@MappedSuperclass` giúp nhiều entity dùng chung mappings/callback logic mà không tạo bảng riêng cho lớp base. Nhưng không bắt buộc mọi entity đều có cùng audit semantics. Ví dụ immutable event table chỉ cần `createdAt`, trong khi bảng config có thể cần cả `updatedAt`.

## 5. Entity listener tách khỏi entity

Thay vì đặt callback trên base class, có thể khai báo listener:

~~~java
package com.example.persistence;

import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import java.time.Instant;

public class TimestampListener {

    @PrePersist
    public void beforeInsert(PurchaseOrder order) {
        Instant now = Instant.now();
        order.initializeTimestamps(now);
    }

    @PreUpdate
    public void beforeUpdate(PurchaseOrder order) {
        order.markUpdated(Instant.now());
    }
}
~~~

Entity minh họa:

~~~java
@Entity
@EntityListeners(TimestampListener.class)
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column(name = "created_at", updatable = false, nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected PurchaseOrder() {}

    void initializeTimestamps(Instant now) {
        this.createdAt = now;
        this.updatedAt = now;
    }

    void markUpdated(Instant now) {
        this.updatedAt = now;
    }
}
~~~

Đây là minh họa API lifecycle listener; với project thật cần setters/constructors và các business fields phù hợp. JPA callback methods có chữ ký, phạm vi và inheritance rules cần tuân thủ theo Jakarta Persistence version đang dùng.

### 5.1. Khi nào chọn entity listener?

- Nhiều entity dùng cùng lifecycle behavior.
- Không muốn entity chứa mã tính timestamp.
- Cần kiểm soát logic gọi theo JPA callbacks.
- Có thể giữ callback nhẹ, độc lập với repository/network.

Nhưng entity listener không tự bảo đảm chạy cho bulk HQL/native SQL. Nó vẫn nằm ở ORM lifecycle path.

### 5.2. Không tạo recursion trong listener

Không làm kiểu:

~~~java
@PreUpdate
void beforeUpdate(PurchaseOrder order) {
    entityManager.persist(new AuditLog(...));
    entityManager.flush();
}
~~~

Vấn đề là listener đang chạy trong một vòng synchronization; gọi lại EntityManager operations có thể gây lỗi hoặc behavior không portable. Với audit log nhiều bản ghi, dùng cơ chế audit riêng như Envers hoặc outbox ở service/DB layer tùy yêu cầu.

## 6. Cách 2 — Hibernate @CreationTimestamp và @UpdateTimestamp

Hibernate hỗ trợ annotations timestamp chuyên biệt:

~~~java
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;
import java.time.Instant;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    // Các business fields, constructors...
}
~~~

### 6.1. Ý nghĩa

- `@CreationTimestamp` yêu cầu Hibernate tự điền timestamp tạo khi entity được INSERT.
- `@UpdateTimestamp` yêu cầu Hibernate tự cập nhật timestamp vào lúc entity được UPDATE do ORM quản lý theo mapping.

Lưu ý **đây là extension của Hibernate, không phải JPA annotation chuẩn**. Nếu thay Hibernate bằng JPA provider khác, không giả định annotation này được hiểu giống nhau.

### 6.2. Nguồn thời gian VM hay DB?

Các phiên bản Hibernate phù hợp có cơ chế chọn nguồn tạo timestamp, ví dụ:

~~~java
import org.hibernate.annotations.SourceType;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@CreationTimestamp(source = SourceType.VM)
private Instant createdAt;

@UpdateTimestamp(source = SourceType.VM)
private Instant updatedAt;
~~~

`SourceType.VM` sử dụng nguồn thời gian phía ứng dụng. Các Hibernate versions hỗ trợ `SourceType.DB` có thể lấy thời gian từ database:

~~~java
@CreationTimestamp(source = SourceType.DB)
private Instant createdAt;

@UpdateTimestamp(source = SourceType.DB)
private Instant updatedAt;
~~~

Đừng copy cấu hình mà không kiểm tra version Hibernate/dialect đang dùng. Nguồn thời gian DB có thể yêu cầu SQL function hoặc cơ chế retrieve generated values phù hợp.

### 6.3. Hibernate timestamp khác actor auditing

Hai annotation trên cung cấp **thời gian**, không tự biết `createdBy` hay `updatedBy` là user nào. Muốn ghi actor phải có thêm application context, listener hoặc auditing framework.

### 6.4. Có nên đồng thời dùng @PreUpdate?

Thông thường **không nên để cả `@UpdateTimestamp` và callback `@PreUpdate` cùng set một field**. Nếu cần business-specific logic, hãy chọn rõ một owner, không để timestamp bị ghi hai lần với hai thời điểm khác nhau.

### 6.5. Thế nào là “entity UPDATE”?

Giả sử:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
order.changeStatus("PAID");
~~~

Hibernate dirty checking và flush có thể tạo UPDATE, làm `@UpdateTimestamp` thay đổi. Nhưng nếu code không thay đổi persistent state, **không mặc định Hibernate sinh SQL UPDATE chỉ vì `save()` được gọi**.

## 7. Cách 3 — Spring Data JPA auditing

Spring Data JPA cung cấp auditing annotations:

- `@CreatedDate`.
- `@LastModifiedDate`.
- `@CreatedBy`.
- `@LastModifiedBy`.

Với JPA auditing infrastructure, có thể tự động điền thời gian và actor khi entity được tạo/sửa theo lifecycle.

### 7.1. Entity với AuditingEntityListener

~~~java
package com.example.orders;

import jakarta.persistence.*;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;

@Entity
@EntityListeners(AuditingEntityListener.class)
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @CreatedBy
    @Column(name = "created_by", nullable = false, updatable = false)
    private String createdBy;

    @LastModifiedBy
    @Column(name = "updated_by", nullable = false)
    private String updatedBy;

    @Version
    private Long version;

    @Column(nullable = false)
    private String status;

    protected PurchaseOrder() {}

    public void changeStatus(String next) {
        this.status = next;
    }
}
~~~

### 7.2. Bật JPA auditing

~~~java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorProvider")
public class JpaAuditingConfiguration {
}
~~~

Ứng dụng cần có Spring Data JPA và cấu hình auditing/listener đúng; chỉ thêm annotation lên field mà chưa bật hạ tầng auditing thì không đủ.

### 7.3. AuditorAware xác định ai đang thao tác

~~~java
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Optional;

@Configuration
public class AuditorConfiguration {

    @Bean("auditorProvider")
    public AuditorAware<String> auditorProvider() {
        return () -> {
            Authentication authentication =
                SecurityContextHolder.getContext()
                    .getAuthentication();

            if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.of("system");
            }

            return Optional.ofNullable(authentication.getName());
        };
    }
}
~~~

Ví dụ giả định ứng dụng có Spring Security và security context phản ánh principal đã xác thực. Nếu không dùng Spring Security, `AuditorAware` có thể lấy actor từ một **request/job context đáng tin** khác.

### 7.4. Vì sao không dùng actor từ request body?

Không chấp nhận trực tiếp:

~~~json
{
  "status": "PAID",
  "updatedBy": "admin"
}
~~~

rồi ghi `updatedBy = "admin"`. User có thể giả mạo actor. `createdBy`/`updatedBy` phải được lấy từ thông tin đã **xác thực/ủy quyền phía server**, hoặc nguồn hệ thống có độ tin cậy tương ứng.

Client có thể cung cấp một business reason, nhưng identity của người thực hiện không nên để client tự chọn.

### 7.5. Anonymous và system jobs

`AuditorAware` trả `Optional.empty()` khi không có actor có thể làm trường `createdBy` nullable=false không được điền, dẫn đến constraint failure. Có một số policy:

- Dùng actor hệ thống có định danh rõ như `system:scheduler`.
- Với batch job, dùng `job:<jobId>` hoặc một service account ổn định.
- Từ chối ghi nếu nghiệp vụ bắt buộc authenticated human actor.
- Cho phép NULL nếu metadata contract thực sự chấp nhận unknown actor.

**Không lạm dụng `"system"` để che mọi thiếu sót xác thực.** Nếu user-facing write bắt buộc có người chịu trách nhiệm, absence của actor có thể là lỗi chứ không phải fallback.

## 8. @LastModifiedDate có được set khi INSERT không?

Trong Spring Data auditing, cấu hình mặc định thông dụng có thể đánh dấu entity **modified on creation**. Nghĩa là khi insert:

~~~text
createdAt  = now
updatedAt  = now
createdBy  = actor
updatedBy  = actor
~~~

Spring Data JPA `@EnableJpaAuditing` có tùy chọn `modifyOnCreate` trong các phiên bản hỗ trợ để kiểm soát hành vi này.

Nếu nghiệp vụ đòi:

~~~text
createdAt  = now
updatedAt  = null cho tới lần UPDATE đầu
~~~

cần cấu hình và mapping cột nullable tương ứng. Đừng giả định `updatedAt` null hoặc không null khi tạo mà không viết test xác nhận.

### 8.1. Quy tắc API cần rõ

Một REST API trả:

~~~json
{
  "createdAt": "2026-11-15T03:00:00Z",
  "updatedAt": "2026-11-15T03:00:00Z"
}
~~~

là hợp lý nếu “lần ghi gần nhất” bao gồm INSERT. Một API khác muốn phân biệt “chưa từng sửa kể từ lúc tạo” có thể dùng revision=0 hoặc một flag/domain concept rõ ràng, thay vì dựa vào việc hai timestamp có bằng nhau.

### 8.2. Độ chính xác có thể thay đổi

Hai timestamp có thể khác nhau vài microseconds do cách generator chạy, nguồn clock hoặc DB precision. Không dùng equality tuyệt đối của timestamps như bằng chứng duy nhất rằng row chưa từng sửa.

## 9. Thời gian kiểm thử: DateTimeProvider và Clock

Dùng `Instant.now()` trực tiếp làm test phải sleep hoặc đo thời gian gần đúng; test dễ không ổn định. Spring Data auditing có thể lấy thời gian qua `DateTimeProvider`.

Ví dụ cấu hình:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class AuditTimeConfiguration {

    @Bean
    public Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean("auditDateTimeProvider")
    public DateTimeProvider dateTimeProvider(Clock auditClock) {
        return () -> Optional.of(Instant.now(auditClock));
    }
}
~~~

Và:

~~~java
@Configuration
@EnableJpaAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "auditDateTimeProvider"
)
public class JpaAuditingConfiguration {
}
~~~

Các snippets `@EnableJpaAuditing` ở đây minh họa **một cấu hình hợp nhất**; dự án chỉ khai báo một cấu hình auditing thích hợp, không copy nhiều `@EnableJpaAuditing` trùng nhau.

### 9.1. Clock trong integration test

Một test có thể inject:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-11-15T03:00:00Z"),
    java.time.ZoneOffset.UTC
);
~~~

và cấu hình test `DateTimeProvider` dựa trên clock đó, giúp assert timestamp không phụ thuộc tốc độ máy.

Nếu cần kiểm thử thời gian đổi giữa insert và update, có thể dùng một clock test điều chỉnh được hoặc provider thay đổi theo từng bước, thay vì `Thread.sleep()`.

### 9.2. Clock VM là một nguồn có thể lệch

Ở hệ thống nhiều JVM, nếu nodes bị lệch đồng hồ, timestamp của hai updates có thể không phản ánh đúng thứ tự thực tế. Dùng NTP/time synchronization, hoặc chọn database-owned time nếu yêu cầu ordering nghiêm ngặt và DB phù hợp.

Ngay cả khi đồng bộ đồng hồ, timestamp vẫn không phải thay thế cho transaction serialization hoặc optimistic locking.

## 10. Cách 4 — Database default cho created_at

Nếu DB chịu trách nhiệm:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Cú pháp trên có phong cách PostgreSQL; các DB khác có type/default syntax khác nhau.

**DEFAULT chỉ có tác dụng khi INSERT không cung cấp giá trị cột hoặc dùng DEFAULT theo cú pháp DB.** Nếu ORM vẫn gửi `created_at = NULL`, DB default có thể không chạy và NOT NULL constraint bị lỗi.

### 10.1. Mapping bỏ cột khỏi INSERT

Ví dụ DB-owned:

~~~java
@Column(
    name = "created_at",
    nullable = false,
    insertable = false,
    updatable = false
)
private Instant createdAt;
~~~

Với `insertable=false`, Hibernate thông thường không đưa cột vào INSERT, để DB default điền. Nhưng **entity Java có thể chưa có giá trị generated mới ngay sau persist/flush**, tùy cách mapping và Hibernate version.

Nếu service cần đọc lại DB-generated value, cân nhắc:

- Hibernate-generated property mapping như `@Generated` theo version phù hợp.
- `em.flush()` rồi `em.refresh(entity)` trong transaction thích hợp.
- Re-query sau commit bằng EntityManager mới.

Không tự giả định Java field đã đồng bộ với DB trigger/default khi không có generated-value strategy.

### 10.2. DEFAULT không tự xử lý UPDATE

SQL default cho `updated_at` chạy ở INSERT, không tự thay đổi khi UPDATE. Nếu dùng DB-owned updatedAt, thường cần trigger hoặc SQL update statement explicitly set timestamp.

## 11. Database trigger cho updated_at

PostgreSQL minh họa:

~~~sql
CREATE OR REPLACE FUNCTION touch_purchase_order()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_purchase_order_updated_at
BEFORE UPDATE ON purchase_orders
FOR EACH ROW
EXECUTE FUNCTION touch_purchase_order();
~~~

Trigger này set `updated_at` cho **mọi UPDATE** trên table, kể cả UPDATE đổi một field không quan trọng hoặc viết lại cùng giá trị.

### 11.1. Ưu điểm

- Bao phủ UPDATE từ Hibernate, JDBC, native SQL và các script khác.
- Không phụ thuộc ứng dụng có bật JPA lifecycle listener.
- Clock có thể thống nhất ở database.
- Tránh những bulk HQL UPDATE quên điền timestamp.

### 11.2. Trade-off

- Logic bị đặt trong DB, cần migration/version control.
- Hibernate có thể giữ stale `updatedAt` nếu không fetch lại.
- Trigger chạy trên UPDATE ngay cả khi transaction sau đó rollback; dữ liệu cuối cùng vẫn rollback cùng transaction.
- Một no-op UPDATE vẫn có thể làm updatedAt đổi.
- Khác biệt cú pháp và semantics giữa PostgreSQL/MySQL/Oracle/SQL Server.
- Actor metadata cần cách truyền context tới DB đáng tin, không tự xuất hiện.

### 11.3. CURRENT_TIMESTAMP và clock_timestamp khác nhau

Trên PostgreSQL, `CURRENT_TIMESTAMP` phản ánh thời điểm bắt đầu transaction, còn `clock_timestamp()` là thời gian thực tại lần gọi.

Một transaction dài có thể UPDATE nhiều rows, nếu dùng transaction timestamp thì các rows có thể cùng giá trị; dùng wall-clock time có thể tăng theo từng invocation. Hãy chọn theo contract metadata.

Đừng nhầm một timestamp lấy khi UPDATE với **commit timestamp**. Trigger vẫn chạy *trước* commit.

### 11.4. Khi có trigger, ORM nên xử lý thế nào?

Nếu database sở hữu `updated_at`, application thường tránh ghi trường đó:

~~~java
@Column(
    name = "updated_at",
    nullable = false,
    insertable = false,
    updatable = false
)
private Instant updatedAt;
~~~

Cần phối hợp với DEFAULT/trigger INSERT để cột có giá trị ban đầu. Nếu cần Hibernate luôn đọc giá trị mới, dùng mapping generated property hỗ trợ trong version hoặc refresh phù hợp.

Đừng đồng thời gắn `@UpdateTimestamp` lên cùng cột rồi dựa vào trigger để ghi đè mà không có chính sách rõ.

### 11.5. Bảo vệ created_at bất biến ở DB

`@Column(updatable=false)` là chỉ dẫn ORM. Nếu tất cả writers được phép chạy SQL native, muốn đảm bảo createdAt không đổi có thể sử dụng:

- Trigger từ chối thay đổi `created_at`.
- SQL permissions hạn chế UPDATE cột.
- Một storage model append-only nơi phù hợp.

Chi phí và nhu cầu bảo vệ khác nhau tùy hệ thống; không phải mọi ứng dụng CRUD nhỏ đều cần trigger bảo vệ riêng.

## 12. Actor trong DB trigger: bài toán khó hơn timestamp

Database biết session user/role, nhưng ứng dụng thường dùng **một technical DB account** cho cả nghìn người dùng. Nếu trigger gán `updated_by = current_user`, nó có thể chỉ cho kết quả `app_service`, không phải người dùng nghiệp vụ.

Một phương án PostgreSQL là truyền actor context có kiểm soát:

~~~sql
SELECT set_config('app.actor_id', 'user-17', true);
~~~

Tham số `true` yêu cầu scope theo transaction local trong ngữ cảnh phù hợp. Trigger có thể đọc:

~~~sql
current_setting('app.actor_id', true)
~~~

Nhưng thiết kế này có nhiều điều kiện:

- Chỉ server xác thực mới được xác định actor.
- Context phải được thiết lập **mỗi transaction** trước writes.
- Kết nối từ pool phải không rò context giữa requests.
- Không cho client tùy ý ghi actor/session variable thiếu kiểm soát.
- Cần fallback chính sách cho scheduler/ETL.
- Kiểm thử transaction boundaries và connection reuse.
- DB function/trigger phải được version control.

Đây là extension riêng PostgreSQL. Với đa số ứng dụng Spring đơn cơ sở dữ liệu, **Spring Data AuditorAware đơn giản hơn cho actor** nếu mọi đường ghi qua JPA; với nhiều writers, cần một chính sách truyền actor tới DB hoặc ghi audit log từ một tầng thống nhất.

## 13. Spring Data auditing và Hibernate timestamps: nên chọn cái nào?

| Tiêu chí | JPA callbacks | Hibernate timestamps | Spring Data auditing | DB default/trigger |
| --- | --- | --- | --- | --- |
| JPA chuẩn | Có | Không | Không phải JPA chuẩn | Không |
| Timestamps | Tự triển khai | Có sẵn | Có sẵn | Có sẵn |
| Actor | Tự cung cấp context | Không tự cung cấp | `AuditorAware` | Cần DB/session context |
| Dễ test với Clock | Cần thiết kế | Tùy generator/nguồn thời gian | `DateTimeProvider` | DB test/time control |
| Bao phủ bulk HQL | Không | Không tự động cho entity callbacks | Không | Trigger có thể bao phủ SQL UPDATE |
| Bao phủ native SQL | Không | Không | Không | Có nếu trigger trên bảng |
| Bao phủ writers ngoài app | Không | Không | Không | Có |
| Portability DB | Cao hơn | Theo Hibernate | Theo Spring Data | Thấp hơn nếu trigger vendor-specific |
| Đồng bộ giá trị DB-generated | ORM sở hữu | ORM biết generator | ORM sở hữu | Cần refresh/generated mapping |
| Phù hợp | Ứng dụng JPA thuần, logic đơn giản | Hibernate-only timestamps | Spring Boot + Security + JPA | DB nhiều writers/ETL |

### 13.1. Khi dùng Spring Boot + JPA

Nếu đa số writes đi qua Spring Data JPA, muốn ghi cả created/updated time và actor, **Spring Data auditing thường là lựa chọn rõ ràng**.

Nếu chỉ cần timestamps và đã chấp nhận phụ thuộc Hibernate, `@CreationTimestamp`/`@UpdateTimestamp` ít boilerplate.

Nếu DB được nhiều ứng dụng/scripts cùng sửa, nghiêng về database-owned timestamps để tránh mỗi writer tự nhớ quy tắc.

### 13.2. Không giả vờ một phương án bao trọn mọi trường hợp

Spring auditing rất tiện, nhưng **không tự chạy khi DBA cập nhật bằng SQL**. Database trigger bao phủ SQL, nhưng actor trong DB không tự biết principal của Spring Security. Muốn đầy đủ phải kết hợp trách nhiệm một cách minh bạch.

## 14. Dirty checking: updatedAt đổi lúc nào?

Trong Hibernate, thay đổi persistent state của managed entity thường được phát hiện khi flush.

~~~java
@Transactional
public void changeStatus(Long id, OrderStatus status) {
    PurchaseOrder order = em.find(PurchaseOrder.class, id);
    order.changeStatus(status);
    // UPDATE có thể chỉ xảy ra khi flush/commit.
}
~~~

### 14.1. Nếu giá trị không thay đổi?

~~~java
order.changeStatus(order.getStatus());
~~~

Nếu cuối cùng entity không dirty, Hibernate có thể không phát SQL UPDATE. Khi đó `@PreUpdate`, `@UpdateTimestamp` hoặc `@LastModifiedDate` có thể **không** làm `updatedAt` đổi, tùy đường ghi và mapping.

Đừng dùng `repository.save(entity)` như một lệnh “đụng vào timestamp” chắc chắn khi không có thay đổi persistent state.

### 14.2. Nếu chỉ thay đổi collection?

Ví dụ thêm một item vào `order.lines` nhưng không đổi field trong bảng `purchase_orders`. Hibernate có thể chỉ thực hiện INSERT vào `order_lines` hoặc UPDATE join table, không nhất thiết UPDATE row của Order.

Khi đó `order.updatedAt` **không nhất thiết đổi** dù aggregate nghiệp vụ đã thay đổi.

Nếu business yêu cầu “mọi thay đổi đối với aggregate Order đều cập nhật order.updatedAt”, cần đưa logic vào domain/application service, chẳng hạn:

~~~java
public void addLine(OrderLine line, Instant now) {
    lines.add(line);
    line.setOrder(this);
    this.updatedAt = now;
}
~~~

Nhưng nếu cũng có generic `@UpdateTimestamp`/`@PreUpdate` owner, đừng tạo xung đột. Có thể dùng một field `revisionTouch` hoặc domain operation đánh dấu root dirty, rồi cơ chế auditing cập nhật timestamp khi root UPDATE thực sự diễn ra. Điều quan trọng là **hợp đồng “aggregate modified” khác “row modified”**.

### 14.3. @DynamicUpdate và update SQL

Hibernate `@DynamicUpdate` có thể chỉ đưa các cột dirty vào SQL UPDATE, ảnh hưởng SQL shape/batching. Nếu DB trigger sở hữu `updatedAt`, nó vẫn có thể cập nhật cột đó. Nếu ORM annotation sở hữu, cần hiểu nó được cập nhật/đưa vào SQL theo cơ chế generator đang dùng.

Không tối ưu SQL shape khi chưa xác định đúng semantics metadata.

## 15. Merge, detached entity và nguồn metadata

JPA `EntityManager.merge()` sao chép persistent state từ một detached/new entity sang một managed instance. Một DTO-to-entity mapper không cẩn thận có thể đem cả `createdAt`, `createdBy`, `updatedAt` từ request vào entity rồi `merge()`.

Ví dụ anti-pattern:

~~~java
@PostMapping("/orders/{id}")
public Order update(
        @PathVariable Long id,
        @RequestBody Order incoming) {

    incoming.setId(id);
    return repository.save(incoming);
}
~~~

Những vấn đề:

- Client có thể điền `createdAt` giả.
- Các field không gửi có thể bị map thành NULL/default rồi overwrite.
- `repository.save()` có thể dùng `merge()` tùy entity new/existing detection.
- Metadata và phiên bản optimistic lock có thể sai.
- Entity API bị lộ trực tiếp ra request/response.

### 15.1. Cách làm tốt hơn: DTO và managed entity

~~~java
public record ChangeOrderStatusRequest(OrderStatus status) {}

@Transactional
public void changeStatus(
        Long orderId,
        ChangeOrderStatusRequest request) {

    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        orderId
    );

    if (order == null) {
        throw new EntityNotFoundException();
    }

    order.changeStatus(request.status());
    // createdAt/updatedAt/actor được owner phù hợp xử lý.
}
~~~

Chỉ map các business fields được cho phép. Metadata nên là read-only trong API request hoặc không xuất hiện trong write DTO, trừ những use case nhập lịch sử có policy riêng.

### 15.2. @Column(updatable=false) không giải quyết toàn bộ mass assignment

Annotation có thể ngăn SQL UPDATE cho một field, nhưng DTO-to-entity mapping vẫn có thể làm Java object state sai tạm thời. Hơn nữa, các audit fields khác hoặc native SQL có thể vẫn bị ghi.

Giải pháp chính là **command DTO whitelist và ownership**, không chỉ ORM mapping flag.

### 15.3. Import dữ liệu lịch sử là trường hợp riêng

Một job chuyển đổi dữ liệu có thể cần giữ `originalCreatedAt` từ hệ thống cũ. Không nên giả mạo timestamp hiện tại và cũng không nên để mọi API client tự set createdAt.

Có thể lưu:

- `createdAt`: thời điểm row được tạo trong hệ thống hiện tại.
- `sourceCreatedAt`: thời điểm bản ghi gốc được tạo ở hệ thống nguồn.
- `importedAt`: thời điểm import.

Nếu nghiệp vụ quyết định preserved historical creation time là `createdAt`, cần một import-specific policy, validation và audit provenance rõ. Không thay đổi generic auditing của mọi API chỉ cho một migration.

## 16. Bulk JPQL/HQL UPDATE bỏ qua lifecycle callbacks

Một trong những bẫy quan trọng nhất:

~~~java
int affected = em.createQuery("""
    update PurchaseOrder o
    set o.status = :newStatus
    where o.status = :oldStatus
    """)
    .setParameter("newStatus", OrderStatus.COMPLETED)
    .setParameter("oldStatus", OrderStatus.PAID)
    .executeUpdate();
~~~

Bulk update **không chạy như vòng lặp tìm từng entity managed rồi setter**. Vì vậy đừng mong `@PreUpdate`, `@UpdateTimestamp` hoặc Spring Data `@LastModifiedDate` tự điền metadata cho từng row từ đường bulk DML này.

### 16.1. Phải set metadata rõ ràng nếu ORM/app sở hữu

Giả sử entity có `updatedAt`, `updatedBy`, version numeric và tenant:

~~~java
Instant now = clock.instant();
String actor = currentActor.id();

int affected = em.createQuery("""
    update PurchaseOrder o
    set o.status = :newStatus,
        o.updatedAt = :now,
        o.updatedBy = :actor,
        o.version = o.version + 1
    where o.tenantId = :tenantId
      and o.status = :oldStatus
    """)
    .setParameter("newStatus", OrderStatus.COMPLETED)
    .setParameter("oldStatus", OrderStatus.PAID)
    .setParameter("now", now)
    .setParameter("actor", actor)
    .setParameter("tenantId", authenticatedTenantId)
    .executeUpdate();
~~~

Ví dụ này minh họa cách **tự quản lý version numeric và metadata trong bulk DML**; dùng cùng entity mapping với các field tương ứng. Nó không thay thế một chiến lược concurrency đầy đủ nếu nghiệp vụ phải kiểm tra expected version cho từng row.

### 16.2. Nếu DB trigger sở hữu updatedAt

Không cần set `updatedAt` ở mọi bulk SQL nếu trigger đảm nhận đúng. Nhưng `updatedBy` vẫn cần policy. Đừng vừa set timestamp ở application vừa để trigger ghi đè khác mà không đồng bộ.

### 16.3. Persistence context có thể stale

Sau bulk update, managed entities đã load trước đó có thể vẫn giữ `status`, `updatedAt` và `version` cũ. Tùy use case, cần `em.clear()` hoặc `refresh()`/context mới để đọc lại.

`em.clear()` detach mọi managed entities; phải flush những thay đổi pending phù hợp trước khi clear, tránh làm mất updates chưa synchronized.

### 16.4. Đừng quên tenant và soft-delete filters

Một bulk DML dễ gây hậu quả nghiêm trọng nếu bỏ predicate authorization:

~~~hql
update PurchaseOrder o set o.status = :status
~~~

Cần scope theo tenant/business constraints tương ứng. Auditing không thay thế authorization; row metadata đúng nhưng update sai tenant vẫn là lỗi bảo mật.

## 17. Native SQL, JDBC và scripts

Các đường ghi dưới đây **không đi qua entity lifecycle callbacks**:

~~~sql
UPDATE purchase_orders
SET status = 'COMPLETED'
WHERE id = 9001;
~~~

~~~java
jdbcTemplate.update("""
    update purchase_orders
       set status = ?
     where id = ?
    """,
    "COMPLETED",
    9001L
);
~~~

Cũng vậy với Flyway/Liquibase data migrations, ETL pipeline, DBA scripts hoặc ứng dụng khác dùng chung database.

Nếu ứng dụng sở hữu timestamp bằng ORM, cần quy định **mọi SQL viết tay tự điền metadata**:

~~~sql
UPDATE purchase_orders
SET status = :status,
    updated_at = :now,
    updated_by = :actor
WHERE tenant_id = :tenantId
  AND id = :id;
~~~

Hoặc chọn DB trigger để tránh phụ thuộc từng writer ghi đúng `updated_at`.

### 17.1. Native SQL có thể bỏ qua @Version

Một native UPDATE không tự tăng version hoặc kiểm tra expected version chỉ vì entity Java có `@Version`. Nếu cần optimistic concurrency:

~~~sql
UPDATE purchase_orders
SET status = :status,
    updated_at = :now,
    updated_by = :actor,
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND version = :expectedVersion;
~~~

Nếu `affectedRows = 0`, ứng dụng phải phân biệt not found/not authorized/stale version theo policy; không tự coi thành công.

### 17.2. Đồng bộ với entity cache

Native DML/trigger có thể làm persistence context và caches không phản ánh dữ liệu mới. Cần dùng EntityManager synchronization/refresh/clear và chiến lược invalidation/cache phù hợp. Metadata chính xác trong DB nhưng entity Java trả ra timestamp cũ vẫn là bug ở tầng API.

## 18. INSERT, UPDATE và soft delete

### 18.1. Tạo mới

Khi INSERT:

~~~text
createdAt = now
updatedAt = now (nếu contract chọn)
createdBy = currentActor
updatedBy = currentActor (nếu contract chọn)
~~~

`createdAt` và `createdBy` sau đó nên được coi là bất biến theo policy thông thường.

### 18.2. Sửa nghiệp vụ

Khi status/amount/address đổi:

~~~text
createdAt/createdBy: giữ nguyên
updatedAt/updatedBy: cập nhật
version: tăng theo optimistic locking policy
~~~

### 18.3. Soft delete

Một soft-delete operation có thể ghi:

~~~text
deletedAt = now
deletedBy = actor
updatedAt = now
updatedBy = actor
status = DELETED
~~~

Nhưng không phải hệ thống nào cũng coi soft delete là “last modification”; cần chọn rõ semantics. Nếu soft delete triển khai bằng HQL/native UPDATE, generic `@PreUpdate` không tự được gọi.

### 18.4. Physical delete

Khi DELETE hẳn row, mọi metadata trên row cũng mất nếu không có audit history/archival. `@PreRemove` có thể chạy cho entity remove path, nhưng không đảm bảo callback audit tồn tại sau delete hay transaction commit.

Nếu phải chứng minh ai xóa dữ liệu, cần audit log, soft-delete, tombstone hoặc event/outbox bền vững theo yêu cầu.

## 19. @Version không thay updatedAt

Ví dụ:

~~~java
@Version
@Column(name = "version", nullable = false)
private Long version;
~~~

Optimistic locking thường dùng version như:

~~~sql
UPDATE purchase_orders
SET status = ?,
    version = ?
WHERE id = ?
  AND version = ?;
~~~

Nếu transaction khác đã sửa row, version cũ không còn phù hợp và UPDATE có thể tác động 0 row; Hibernate sẽ xử lý conflict theo hợp đồng optimistic locking.

### 19.1. Vì sao timestamp không tốt để thay thế version mặc định?

Timestamps có giới hạn độ chính xác và clock skew. Hai thao tác gần nhau có thể có cùng giá trị timestamp sau khi database làm tròn; clock VM có thể lệch giữa nodes. Thứ tự timestamp cũng không phải serialization order chắc chắn.

`@Version` thường đáng tin hơn cho optimistic concurrency của ORM. Có thể lưu cả `version` và `updatedAt` vì mục đích khác nhau.

### 19.2. Versioned UPDATE cũng cần metadata owner

Hibernate tăng `version` không có nghĩa tự ghi `updatedBy`. Ngược lại, listener thay `updatedAt` không bảo đảm kiểm tra concurrent writers nếu thiếu version/locking policy.

## 20. Transaction rollback và tính trung thực của metadata

Một callback có thể làm:

~~~java
@PreUpdate
void updateMetadata() {
    updatedAt = Instant.now();
}
~~~

sau đó Hibernate gửi SQL UPDATE. Nhưng transaction có thể rollback.

Kết luận cần nhớ:

- **Metadata trên entity Java** có thể đã đổi.
- **SQL log** có thể hiển thị UPDATE.
- **Database committed state** có thể vẫn giữ giá trị cũ vì rollback.

Do đó đừng phát ra sự kiện “Order đã sửa thành công” ngay trong `@PreUpdate` hoặc `@PostUpdate`.

### 20.1. Sự kiện after-commit

Nếu cần chạy một tác vụ *sau khi transaction commit*, Spring hỗ trợ các cơ chế như:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderUpdatedEvent event) {
    // ...
}
~~~

Nhưng after-commit listener chạy trong process và có thể bị mất khi process crash trước khi thực hiện. Nếu cần bảo đảm gửi message bền vững, **transactional outbox** thường là lựa chọn phù hợp.

### 20.2. Outbox và audit history khác nhau

Outbox ghi event để phát ra hệ thống khác. Audit history lưu các thay đổi nhằm truy vết/khôi phục/kiểm toán. Có thể chia sẻ một số dữ liệu nhưng không nên mặc định cùng một bảng outbox là audit log đầy đủ.

## 21. Metadata hiện tại không phải audit trail

Một row:

~~~text
createdAt = 03:00
createdBy = user-17
updatedAt = 08:25
updatedBy = user-29
~~~

chỉ cho biết lần tạo và lần sửa gần nhất. Nó **không cho biết**:

- Đã sửa bao nhiêu lần.
- Từng sửa field nào.
- Giá trị trước/sau là gì.
- Ai sửa ở lần thứ hai.
- Lý do sửa.
- Transaction nào rollback.
- Có xóa rồi khôi phục không.

Nếu yêu cầu là truy vết tất cả revisions, cân nhắc:

- Hibernate Envers (entity revision auditing theo khả năng/version).
- Append-only audit event table.
- Database triggers ghi audit history.
- CDC/change data capture cho các mục đích phù hợp.
- Event sourcing nếu toàn mô hình nghiệp vụ được thiết kế theo event streams.

### 21.1. Hibernate Envers bổ sung gì?

Hibernate Envers có thể lưu revision records cho những entity được đánh dấu audit theo cơ chế của nó, giúp xem lịch sử các versions của entity. Nhưng phải xác định các đường ghi được hỗ trợ: **bulk HQL/native SQL thường không đi theo entity lifecycle auditing thông thường**, nên không giả định Envers ghi đầy đủ mọi thay đổi nếu DB còn nhiều writers.

Audit history của hệ thống cần có test trên tất cả paths quan trọng.

### 21.2. CDC không tự có actor nghiệp vụ

CDC có thể quan sát thay đổi ở database log nhưng thường không tự biết Spring principal nếu actor không được lưu trong row, transaction context hoặc event metadata. Cần thiết kế provenance, không chỉ bắt được physical changes.

## 22. Đồng hồ, timezone và độ chính xác của database

### 22.1. Nên lưu kiểu nào?

Trong Java, `Instant` thường là lựa chọn tốt cho audit timestamps vì biểu diễn một mốc thời gian tuyệt đối.

Trong DB, kiểu cụ thể phụ thuộc database:

- PostgreSQL: `timestamptz`/`TIMESTAMP WITH TIME ZONE` có semantics phù hợp với instant.
- Một số DB dùng `TIMESTAMP`/`DATETIME` không lưu timezone; cần policy UTC rõ ràng.
- Driver/JDBC mapping quyết định chuyển đổi giữa Java và SQL.

Không giả định mọi database lưu timezone offset hoặc nanosecond precision giống nhau.

### 22.2. Cấu hình UTC

Nếu dữ liệu đi qua nhiều timezone, nên chuẩn hóa storage/serialization sang UTC và chuyển sang timezone nghiệp vụ tại presentation layer khi phù hợp.

Tuy nhiên, `Instant` không tự khắc phục sai cấu hình Hibernate/JDBC/database session timezone. Kiểm tra dữ liệu đọc lại trên DB mục tiêu, đặc biệt ranh giới DST nếu cần hiển thị theo timezone vùng.

### 22.3. Độ phân giải thời gian

JVM có thể tạo Instant với precision khác database column. Ví dụ một giá trị:

~~~text
2026-11-15T08:25:00.123456789Z
~~~

có thể được database lưu với microsecond/millisecond precision tùy DB/column, khiến assert exact Instant thất bại.

Trong integration tests, so sánh theo precision DB hỗ trợ hoặc đọc lại giá trị đã lưu để kiểm tra contract. Không dùng timestamp equality như optimistic lock thay thế version.

### 22.4. Clock skew và thứ tự

Nếu hai writers ở các servers có clock lệch:

~~~text
Node A thực hiện trước nhưng clock = 10:00:05
Node B thực hiện sau nhưng clock = 10:00:03
~~~

`updatedAt` của B có thể nhỏ hơn A. Đối với ordering quan trọng, cần một cơ chế thứ tự đáng tin hơn như sequence/revision/DB coordination hoặc event log, không chỉ wall-clock timestamps.

## 23. Actor, bảo mật và quyền riêng tư

### 23.1. Ghi định danh bền vững

Thường nên lưu actor ID ổn định (`userId`/service account ID), không chỉ display name hay email vì chúng có thể thay đổi. Khi hiển thị UI, có thể join/resolve sang tên hiện tại theo quyền truy cập.

### 23.2. Actor có thể không phải người dùng

Các tác nhân phổ biến:

- User thao tác HTTP.
- Service account của một API nội bộ.
- Scheduled job.
- Message consumer.
- Data migration.
- Administrator vận hành.
- Automated repair process.

Thay vì một chuỗi “system” chung cho tất cả, khi cần truy vết nên lưu thêm `sourceSystem`, `jobId` hoặc `correlationId` với retention/privacy policy.

### 23.3. SecurityContext thường gắn với thread

Nếu xử lý bằng `@Async` hoặc worker thread khác, không mặc định `SecurityContextHolder` của HTTP thread được truyền sang. ActorAware trong background thread có thể trả empty/system.

Có thể truyền **immutable, server-validated actor context** vào job/message, hoặc áp dụng context propagation được cấu hình rõ. Không truyền toàn bộ mutable entity/EntityManager xuyên threads; Session/EntityManager không phải đối tượng dùng chung đồng thời.

### 23.4. Không tin actor từ Kafka/event tùy tiện

Một message có trường `userId` không tự là nguồn đáng tin; cần xác định producer trust boundary và có authentication/signature/authorization phù hợp. Nếu message đến từ nguồn ít tin cậy, actor phải được xác minh trước khi đưa vào metadata.

### 23.5. Audit metadata có thể là dữ liệu cá nhân

`createdBy`/`updatedBy` có thể liên kết một cá nhân. Cần kiểm soát quyền xem, thời gian lưu và chính sách xóa/ẩn danh phù hợp. Audit requirements có thể khác dữ liệu người dùng thông thường; thiết kế phải cân bằng compliance và quyền riêng tư.

## 24. Trường hợp immutable entity và append-only data

Không phải mọi bảng cần `updatedAt`. Với audit event, ledger hoặc ledger entries có tính append-only, sửa dữ liệu có thể bị cấm theo thiết kế. Khi đó:

~~~java
@Entity
@org.hibernate.annotations.Immutable
@Table(name = "audit_events")
public class AuditEvent {

    @Id
    private Long id;

    @CreationTimestamp
    @Column(name = "created_at", updatable = false, nullable = false)
    private Instant createdAt;

    // Các field event immutable...
}
~~~

`@Immutable` là Hibernate-specific mapping hint; không phải database constraint tự ngăn mọi SQL native UPDATE. Nếu yêu cầu bất biến nghiêm ngặt, enforce thêm ở DB privileges/schema/append-only storage model.

### 24.1. Vì sao không ép updatedAt vào immutable event?

Nếu record được tạo một lần và không cập nhật, `updatedAt` không đem nhiều giá trị, lại dễ khiến người đọc hiểu nhầm có sửa đổi lịch sử. Dùng `occurredAt` và `recordedAt` riêng nếu event time khác ingestion time.

## 25. Migration schema và dữ liệu cũ

Khi thêm auditing fields vào một bảng đang có hàng triệu rows:

### 25.1. Tránh thêm NOT NULL ngay khi không có dữ liệu

Một hướng migration an toàn:

1. Thêm cột nullable hoặc default phù hợp.
2. Deploy code ghi metadata cho rows mới/updated.
3. Backfill rows cũ bằng một policy được duyệt.
4. Kiểm tra tỷ lệ missing/invalid.
5. Thêm NOT NULL/constraints/index sau khi dữ liệu đáp ứng.
6. Nếu có DB trigger, deploy và test như schema object chính thức.

Ví dụ concept:

~~~sql
ALTER TABLE purchase_orders
ADD COLUMN created_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE;
~~~

Backfill cần business semantics chứ không phải cứ đặt mọi lịch sử thành `CURRENT_TIMESTAMP`.

### 25.2. Không chế tạo lịch sử giả

Nếu bảng cũ không có thời điểm tạo gốc, đặt `createdAt = now` cho một row 5 năm tuổi có thể gây hiểu nhầm.

Các lựa chọn:

- Dùng timestamp có sẵn từ source đáng tin.
- Đặt `createdAt` theo thời điểm migration và lưu `metadataOrigin = MIGRATED`.
- Cho phép null/unknown khi business policy cho phép.
- Lưu `importedAt` và `sourceCreatedAt` riêng.

Cần ghi lại quyết định migration để người dùng analytics hiểu trường có giới hạn gì.

### 25.3. Rolling deploy

Trong lúc có nhiều application versions chạy song song, một version mới có thể ghi metadata khác version cũ. Nếu cần zero-downtime, thiết kế schema defaults/triggers tương thích và thứ tự deploy để không xuất hiện null hoặc creator không chính xác.

## 26. Kiểm thử JPA lifecycle với integration test

Unit test gọi trực tiếp `onCreate()` có thể kiểm tra logic Java, nhưng không chứng minh JPA callback được gọi tại đúng thời điểm. Cần integration test có EntityManager và DB.

### 26.1. Test tạo mới

~~~java
@Test
void creationMetadataIsPersisted() {
    PurchaseOrder order = createValidOrder();

    em.persist(order);
    em.flush();
    em.clear();

    PurchaseOrder reloaded =
        em.find(PurchaseOrder.class, order.getId());

    assertThat(reloaded.getCreatedAt()).isNotNull();
    assertThat(reloaded.getUpdatedAt()).isNotNull();
}
~~~

Ví dụ `createValidOrder()` là test fixture; entity cần mapping/getters tương ứng. `flush()`/`clear()` giúp test đọc persisted state, nhưng test có thể đang trong transaction và **chưa commit**. Nếu cần kiểm chứng commit/rollback, đặt ranh giới transaction phù hợp.

### 26.2. Test updatedAt khi dirty entity

Một test nên:

1. Persist entity và commit.
2. Điều chỉnh test clock sang thời điểm sau.
3. Mở transaction mới, load managed entity.
4. Thực hiện một thay đổi persistent field.
5. Flush/commit.
6. Đọc lại entity trong persistence context mới.
7. Xác nhận `createdAt` giữ nguyên và `updatedAt` phản ánh lần update theo precision policy.

Không dùng `Thread.sleep()` để tạo “thời gian khác” nếu đã có Clock/DateTimeProvider.

### 26.3. Test no-op update

Gọi setter với cùng giá trị hoặc `repository.save()` trên entity không dirty; đo SQL và metadata. Kết quả có thể phụ thuộc provider/mapping, vì vậy phải xác nhận theo **contract mà ứng dụng cam kết**.

### 26.4. Test callback không xảy ra với bulk update

~~~java
int count = em.createQuery("""
    update PurchaseOrder o
    set o.status = :status
    """)
    .setParameter("status", OrderStatus.COMPLETED)
    .executeUpdate();
~~~

Sau đó đọc DB trong context mới và kiểm tra `updatedAt` có đổi hay không. Nếu ORM callbacks là owner và query không set metadata, có thể phát hiện gap; nếu DB trigger là owner, kết quả có thể khác. Đây là test quan trọng để chứng minh ownership.

### 26.5. Test actor thay đổi

- Tạo entity khi actor là `user-A`.
- Update khi actor là `user-B`.
- Xác nhận `createdBy=user-A`, `updatedBy=user-B`.
- Chạy background job với service account và xác nhận actor policy.
- Thử principal không hợp lệ/anonymous để kiểm tra reject hoặc fallback chính xác.

### 26.6. Test rollback

Thực hiện một update rồi ném exception làm transaction rollback. Sau đó đọc DB trong transaction mới; `updatedAt` và business fields phải phản ánh **committed state cũ**, không phải Java object đã bị thay đổi trong transaction lỗi.

### 26.7. Test đồng thời

Dùng hai transactions với cùng entity version, update xung đột; xác nhận optimistic conflict và chỉ committed version/timestamp được giữ theo chính sách.

## 27. Spring Data @DataJpaTest và auditing configuration

`@DataJpaTest` thường cung cấp JPA slice và test transaction, nhưng **không nhất thiết tự nạp mọi @Configuration/@EnableJpaAuditing/AuditorAware bean của ứng dụng giống @SpringBootTest**.

Nếu test auditing:

- Import auditing config phù hợp.
- Cung cấp test AuditorAware xác định.
- Cung cấp DateTimeProvider/Clock kiểm soát được.
- Dùng DB product/driver gần production khi đánh giá timestamp precision/SQL triggers.
- Kiểm tra rollback mặc định của test để không nhầm với committed result.

Ví dụ định hướng:

~~~java
@DataJpaTest
@Import({
    JpaAuditingConfiguration.class,
    AuditTestConfiguration.class
})
class PurchaseOrderAuditingIT {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void recordsCreator() {
        PurchaseOrder order = newValidOrder();
        entityManager.persistAndFlush(order);
        assertThat(order.getCreatedBy()).isEqualTo("test-user");
    }
}
~~~

`AuditTestConfiguration` giả định định nghĩa test `AuditorAware<String>` và `DateTimeProvider`. Không copy test như code chạy độc lập khi chưa có entity/fixtures/imports phù hợp.

### 27.1. Kiểm tra Spring Boot test không che lỗi

Test class gắn `@Transactional` có thể mở sẵn transaction, che những lỗi về transaction proxy ở service layer. Nếu mục tiêu là kiểm chứng metadata sau commit, có thể dùng `TransactionTemplate` hoặc transaction testing utilities để tách scope và re-read.

## 28. Các tình huống thất bại cần chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `createdAt` null sau INSERT | Auditing chưa bật, listener chưa đăng ký, DB default bị insert NULL | Mapping, generated SQL, entity listeners |
| `createdBy` null | AuditorAware trả empty, principal không có, async context mất | Auth/job context và fallback policy |
| `updatedAt` không đổi sau `save()` | Entity không dirty hoặc `save()` không tạo UPDATE | SQL log, persistence context |
| `updatedAt` không đổi sau bulk UPDATE | Bulk bypass ORM lifecycle | Explicit SET hoặc DB trigger |
| `updatedAt` trong Java khác DB | Trigger/default đổi giá trị nhưng ORM chưa refresh | Generated mapping, refresh/readback |
| `createdAt` bị đổi khi PUT | DTO mass assignment/merge hoặc native SQL | Command DTO whitelist và DB policies |
| `updatedAt` đổi dù không thay business value | Trigger chạy mọi UPDATE hoặc ORM phát UPDATE | Trigger semantics và SQL log |
| `updatedBy=system` với user request | SecurityContext absent, async, bean config sai | ActorAware và auth path |
| `updatedAt` đi lùi giữa servers | Clock skew, JVM timestamps | Đồng bộ clock, DB source/time semantics |
| Timestamps sai vài microseconds | DB precision truncation | Column/JDBC precision và test expectation |
| `updatedAt` mới nhưng update rollback | Nhìn entity Java/log thay vì committed DB | Re-read sau transaction |
| `@Version` đổi nhưng `updatedAt` không | Hai cơ chế ownership khác nhau | ORM generator/listener/bulk path |
| Lịch sử thay đổi bị thiếu | Chỉ có current metadata, không audit trail | Envers/history/outbox/CDC policy |
| Metadata khác nhau giữa app và script | Nhiều writers không cùng contract | Chuyển DB ownership hoặc enforce write standard |
| Actor nhầm tenant | Identity không xác thực/metadata bị client sửa | Server-side identity + tenant checks |

### 28.1. Bật logging để xem SQL thực tế

Hibernate 6 trong Spring Boot, ví dụ môi trường phát triển:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Bind TRACE có thể lộ dữ liệu nhạy cảm, không bật tràn lan trên production. Xem SQL INSERT/UPDATE để xác định Hibernate có điền các cột metadata không; với DB triggers, đọc lại DB vì trigger có thể thay đổi giá trị sau SQL template do Hibernate gửi.

### 28.2. Không đánh đồng SQL UPDATE và commit

Log SQL có UPDATE không chứng minh transaction đã commit. Nếu dùng `@PostUpdate` hoặc SQL log để phát event business thành công, có thể gửi sự kiện giả khi transaction rollback.

## 29. Bộ tiêu chí chọn owner cho metadata

Trước khi quyết định architecture, trả lời:

1. Có bao nhiêu **writers** vào bảng? Chỉ Hibernate hay còn JDBC/scripts/ETL?
2. Có yêu cầu **createdBy/updatedBy** là actor nghiệp vụ không? Actor đến từ đâu?
3. Metadata có cần thống nhất **giữa nhiều services**?
4. Timestamp lấy theo JVM hay DB? Có cần precision/order đặc biệt?
5. Có dùng **bulk HQL/native SQL** thường xuyên không?
6. Có **soft delete**, upsert, import lịch sử hay append-only entity không?
7. Có yêu cầu audit **tất cả revisions** hay chỉ latest?
8. API có cần trả giá trị metadata **ngay sau flush**?
9. Có database triggers/SQL migration tooling được vận hành tốt không?
10. Có phương án integration test tất cả write paths không?

### 29.1. Hướng chọn thông dụng

- **Một Spring Boot app, chủ yếu JPA, cần actor:** Spring Data auditing + AuditorAware + test Clock.
- **Hibernate-only, chỉ cần timestamps:** `@CreationTimestamp`/`@UpdateTimestamp`.
- **JPA không Spring, đơn giản:** `@PrePersist`/`@PreUpdate` hoặc entity listener.
- **Nhiều SQL writers:** DB-owned defaults/triggers cho timestamps; actor phải có context contract rõ.
- **Cần lịch sử mọi lần sửa:** Envers/audit history/CDC hoặc event model bổ sung; không chỉ bốn cột metadata.
- **Bulk mutation nhiều:** Explicitly set metadata/version hoặc dùng DB trigger có test.
- **Độ chính xác thời gian cao/ordering nghiêm ngặt:** Thiết kế DB/revision/transaction semantics, không dùng updatedAt một mình.

## 30. Checklist triển khai

- [ ] `createdAt` và `updatedAt` có semantics rõ: insert/update/commit/business time.
- [ ] `createdBy` và `updatedBy` lấy từ actor đã xác minh server-side.
- [ ] Đã xác định **một owner authoritative** cho mỗi field.
- [ ] Không gắn @UpdateTimestamp, JPA listener và DB trigger cùng sở hữu một cột vô ý.
- [ ] Metadata không được map tự do từ request DTO.
- [ ] `createdAt`/`createdBy` giữ bất biến theo policy.
- [ ] `@Version` được dùng độc lập nếu cần optimistic locking.
- [ ] Hiểu `@PreUpdate` gắn với actual entity UPDATE, không phải mọi setter.
- [ ] Test quan hệ/collection-only changes nếu `updatedAt` đại diện aggregate.
- [ ] Bulk HQL/native SQL/scripts cập nhật metadata theo hợp đồng.
- [ ] Database defaults thực sự chạy (INSERT không override bằng NULL).
- [ ] ORM biết cách refresh DB-generated timestamp khi cần.
- [ ] Timezone/precision/clock source đã được chuẩn hóa.
- [ ] AuditorAware xử lý anonymous, batch jobs và async rõ ràng.
- [ ] Soft delete/physical delete có lịch sử phù hợp.
- [ ] Event phát sau commit hoặc qua outbox nếu cần reliability.
- [ ] Integration tests xác minh insert, update, no-op, bulk, rollback, merge, version và actor.
- [ ] Migration/backfill không tạo lịch sử giả mạo.
- [ ] SQL logging/metrics không làm lộ metadata nhạy cảm.

## 31. Bài tập thực hành

### Bài 1 — Tách loại metadata

Một Order có `createdAt`, `updatedAt`, `paidAt`, `version` và `deletedAt`. Hãy phân loại mỗi field là persistence metadata, business time hay concurrency/deletion metadata. Vì sao không dùng updatedAt để thay paidAt?

### Bài 2 — @PrePersist và @PreUpdate

Viết một `@MappedSuperclass` có `createdAt`/`updatedAt`; khởi tạo cả hai ở `@PrePersist`, chỉ cập nhật updatedAt ở `@PreUpdate`. Lý giải vì sao gọi setter không tự gọi PreUpdate ngay lập tức.

### Bài 3 — Save nhưng updatedAt không đổi

Service load managed entity rồi gọi setter với đúng giá trị cũ và `repository.save()`. Sau commit updatedAt giữ nguyên. Có nhất thiết là lỗi không? Cần kiểm tra SQL/dirty checking thế nào?

### Bài 4 — Hibernate annotations

So sánh `@CreationTimestamp` và `@UpdateTimestamp` với JPA callbacks. Chúng có tự biết user hiện tại không? Có thể phụ thuộc Hibernate version thế nào?

### Bài 5 — Spring Data auditing

Viết entity có `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy`. Cần annotation listener và configuration nào? `AuditorAware` lấy actor từ đâu?

### Bài 6 — @LastModifiedDate khi tạo

Trong ứng dụng muốn `updatedAt = createdAt` lúc INSERT. Nếu test thấy updatedAt null, kiểm tra những cấu hình/column mappings nào?

### Bài 7 — Actor từ client

Client gửi JSON có `updatedBy="admin"`. Vì sao không được tin trường này? Thiết kế DTO và server-side auditor thế nào?

### Bài 8 — Background job

Scheduled job chạy không có SecurityContext của HTTP user. Khi audit createdBy/updatedBy, nên dùng actor nào? Cách xác định nguồn job/correlation ID?

### Bài 9 — DB default và INSERT NULL

Một cột `created_at DEFAULT CURRENT_TIMESTAMP NOT NULL` vẫn báo NOT NULL violation khi Hibernate INSERT. Vì sao? `insertable=false` giúp gì?

### Bài 10 — Trigger và stale entity

PostgreSQL trigger thay `updated_at` sau UPDATE. Hibernate trả entity với updatedAt cũ. Giải thích nguyên nhân và ít nhất hai cách đọc giá trị mới.

### Bài 11 — Bulk HQL

Một bulk HQL UPDATE đổi trạng thái 10.000 Order nhưng updatedAt/updatedBy vẫn cũ. Vì sao? Viết HQL cập nhật metadata và numeric version có tenant scope.

### Bài 12 — SQL native

JDBC code update Order trực tiếp. Những annotation nào không được gọi tự động? Vì sao phải đảm bảo version/metadata/tenant predicates ở SQL?

### Bài 13 — Collection-only change

Thêm một OrderLine nhưng không cập nhật các cột trên Order. `@PreUpdate` của Order có chắc chạy không? Nếu business yêu cầu order.updatedAt thay đổi, thiết kế ra sao?

### Bài 14 — Rollback

`@PostUpdate` đã chạy, sau đó transaction rollback. Có thể dùng callback để gửi email “đã sửa đơn hàng thành công” không? Giải pháp nào phù hợp?

### Bài 15 — Audit history

Một row chỉ có createdAt/by và updatedAt/by. Có thể biết 20 lần sửa trước đã sửa những field gì không? Khi nào chọn Envers/audit table/CDC?

### Bài 16 — Optimistic locking

Hai nodes update một row gần như đồng thời, timestamps bị làm tròn về cùng mili giây. Vì sao `updatedAt` không đủ để phát hiện concurrent update? `@Version` đóng vai trò gì?

### Bài 17 — Migration

Bảng tồn tại 5 năm mới được thêm createdAt. Vì sao backfill toàn bộ thành NOW có thể sai nghĩa? Đề xuất schema và sourceCreatedAt/importedAt strategy.

### Bài 18 — Multi-writer architecture

Ba ứng dụng và một ETL cùng sửa bảng orders. Nên để ORM callback hay DB trigger sở hữu updatedAt? createdBy/updatedBy phải được cung cấp thế nào?

### Bài 19 — Integration tests

Lập test matrix bao gồm insert, update, no-op, rollback, bulk HQL, native SQL, soft-delete, actor thiếu, time precision và optimistic conflict. Chỉ rõ test nào cần DB thật.

### Bài 20 — Thiết kế ownership

Một dự án dùng Spring Data auditing trên updatedAt, Hibernate @UpdateTimestamp trên cùng field và DB trigger nữa. Phân tích rủi ro và trình bày cách chuyển sang một owner rõ ràng.

### Gợi ý đáp án

- **Bài 1:** created/updated là persistence metadata; paidAt là business event; version là concurrency; deletedAt là deletion metadata.
- **Bài 2:** Callback gắn với lifecycle/flush, không phải setter call.
- **Bài 3:** Không nhất thiết; entity không dirty thì UPDATE có thể không chạy.
- **Bài 4:** Hibernate annotations điền timestamps, không tự resolve actor; phụ thuộc provider/version.
- **Bài 5:** `AuditingEntityListener`, `@EnableJpaAuditing`, `AuditorAware` và DateTimeProvider nếu cần.
- **Bài 6:** Kiểm tra modifyOnCreate, mapping nullable và auditing listener/config.
- **Bài 7:** User có thể giả mạo; chỉ map business fields và lấy principal server-side.
- **Bài 8:** Service account/job identity có provenance rõ, không gắn user giả.
- **Bài 9:** SQL INSERT NULL có thể override DEFAULT; omit cột bằng mapping phù hợp.
- **Bài 10:** Trigger chạy DB-side; refresh hoặc generated-value mapping/re-query.
- **Bài 11:** Bulk bypass callbacks; set updatedAt/updatedBy/version rõ và filter tenant.
- **Bài 12:** Lifecycle callbacks không chạy với native SQL; tự bảo vệ metadata, version và quyền.
- **Bài 13:** Không chắc; cần đánh dấu aggregate root dirty hoặc explicit domain policy.
- **Bài 14:** Không; callback không chứng minh commit; dùng after-commit/outbox.
- **Bài 15:** Không; cần revision history/audit events nếu yêu cầu mọi lần sửa.
- **Bài 16:** Clock precision/skew; @Version làm optimistic concurrency check.
- **Bài 17:** Tạo lịch sử giả; phân biệt sourceCreatedAt/importedAt và record provenance.
- **Bài 18:** DB trigger thường bao phủ timestamps tốt hơn; actor cần trusted context contract.
- **Bài 19:** DB integration tests xác nhận lifecycle, timestamp precision, triggers và transactions.
- **Bài 20:** Nhiều owners dễ ghi đè/stale; chọn một owner, migration và test mọi write path.

---

## Tổng kết

**Metadata tạo/sửa là một hợp đồng dữ liệu có chủ sở hữu**, không chỉ là bốn cột hay một annotation. Muốn dữ liệu đúng, cần xác định:

1. **Ngữ nghĩa:** createdAt, updatedAt, actor, version, business event time và audit history là những khái niệm khác nhau.
2. **Trách nhiệm:** JPA callback, Hibernate timestamp, Spring Data auditing hay DB default/trigger phải có phạm vi sở hữu rõ ràng; không ghi cùng field ở nhiều tầng vô tình.
3. **Write paths:** entity dirty checking có callbacks/generators, nhưng bulk HQL, native SQL, ETL và migrations có thể bypass ORM lifecycle. Metadata phải được xử lý ở tất cả các đường ghi được hỗ trợ.
4. **Transaction:** @PreUpdate/@PostUpdate và SQL log không chứng minh commit. Dữ liệu chỉ bền vững sau transaction thành công; event đáng tin cần after-commit semantics hoặc outbox.
5. **Bảo mật:** actor do server xác thực, không lấy từ payload tùy ý; xử lý background/async jobs và tenant context minh bạch.
6. **Khả năng kiểm chứng:** kiểm thử insert, update, no-op, bulk DML, rollback, trigger, precision, clock skew và optimistic locking trên database mục tiêu.

**Một chính sách owner nhất quán, DTO an toàn, integration tests và quy trình migration rõ ràng có giá trị hơn việc gắn thêm nhiều annotation auditing mà không biết chúng tương tác thế nào.**
