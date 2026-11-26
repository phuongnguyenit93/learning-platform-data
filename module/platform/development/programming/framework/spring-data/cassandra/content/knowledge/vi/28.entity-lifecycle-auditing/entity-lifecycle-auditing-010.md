# Kiểm soát nguồn thời gian và người thao tác

Khi một đơn hàng được tạo, chỉnh sửa hoặc đổi trạng thái, hệ thống thường muốn biết **ai đã thực hiện** và **thời điểm nào**. Trong **Spring Data Cassandra**, các annotation `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy` cùng cơ chế **auditing** hỗ trợ điền những thông tin này khi entity được xử lý qua đường ánh xạ của framework.

Tuy nhiên, auditing không đáng tin cậy chỉ vì một class có đủ bốn annotation. Một ứng dụng thực tế còn phải trả lời: đồng hồ lấy từ đâu, múi giờ và độ chính xác ra sao, danh tính actor nào được chấp nhận, job nền không có HTTP request ghi gì, luồng async/reactive truyền context thế nào, client có thể giả danh người sửa hay không, và một mutation CQL trực tiếp có đi qua Spring Data auditing hay không.

Bài thuộc chương **Vòng đời và auditing** của module **SPRING_DATA_CASSANDRA**: truy cập Apache Cassandra qua entity mapping, repository, `CassandraTemplate` và CQL, đồng thời tôn trọng thiết kế theo truy vấn, partition key, consistency, paging và đặc tính dữ liệu phân tán.

**Mục tiêu cuối cùng:** tạo được một *audit contract* nhất quán giữa các đường ghi, có thể kiểm thử, quan sát và xử lý ngoại lệ; không nhầm metadata của entity với lịch sử bất biến hoặc với write timestamp dùng cho last-write-wins.

## 1. Những câu hỏi auditing phải trả lời

Giả sử một service xử lý lệnh chuyển đơn hàng `NEW → PAID`:

~~~text
HTTP request từ người dùng U123
    |
    | 1. Xác thực và kiểm tra tenant/quyền
    v
Ứng dụng nạp order (version=4)
    |
    | 2. Kiểm tra chuyển trạng thái
    v
Ứng dụng cập nhật order và lưu bằng Spring Data
    |
    | 3. Auditing điền người/thời gian sửa
    | 4. Optimistic locking/LWT kiểm tra version nếu cấu hình
    v
Cassandra: status=PAID, updated_at, updated_by, version=5
~~~

Một thiết kế tốt phải có đáp án rõ cho các câu hỏi:

1. **Nguồn thời gian:** backend, client, nguồn external event hay database? Đồng hồ nào tin cậy?
2. **Nguồn người thao tác:** Spring Security principal, service identity, scheduler hay consumer?
3. **Biên trust:** ai được phép đặt `createdBy`, `updatedBy` và timestamp?
4. **Vòng đời entity:** khi nào tạo, khi nào sửa, khi nào ghi raw CQL/batch không có auditing callback?
5. **Concurrency:** hai writer cùng đọc một version có bị mất cập nhật không?
6. **Độ đầy đủ:** các trường auditing chỉ phản ánh **giá trị hiện tại** hay có chứng cứ cho mọi lần thay đổi?
7. **Báo cáo:** muốn lọc theo actor/ngày thì bảng đã có access pattern tương ứng chưa?
8. **Vận hành:** clock skew, mất identity context, retry, late event và backfill được xử lý thế nào?

Nói “bật auditing là xong” chỉ mới xử lý một phần của vấn đề.

## 2. Bốn trường auditing và phạm vi của chúng

| Annotation | Cột CQL gợi ý | Ý nghĩa | Khi nào thường được đặt |
|---|---|---|---|
| `@CreatedDate` | `created_at timestamp` | Thời điểm entity được tạo theo lifecycle của Spring Data | Khi framework xem entity là **mới** |
| `@LastModifiedDate` | `updated_at timestamp` | Thời điểm framework xử lý thay đổi | Trong thao tác update được hỗ trợ, tùy cấu hình create |
| `@CreatedBy` | `created_by text` | Actor tạo entity | Khi entity được coi là mới và có auditor |
| `@LastModifiedBy` | `updated_by text` | Actor cho lần chỉnh sửa hiện tại | Khi update được auditing xử lý và có auditor |

Các annotation này thuộc **Spring Data Commons**, import từ `org.springframework.data.annotation`, không phải JPA:

~~~java
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
~~~

Đây là các **cột dữ liệu thông thường**; chúng không phải log bất biến và không phải metadata do Apache Cassandra tự ghi theo tên cột.

### 2.1. Một ảnh chụp không phải lịch sử

~~~text
Lần 1: CREATE bởi user:101 lúc 09:00
    created_at = 09:00
    created_by = user:101
    updated_at = 09:00 (nếu cấu hình ghi modified trên create)
    updated_by = user:101

Lần 2: UPDATE bởi user:202 lúc 09:15
    updated_at = 09:15
    updated_by = user:202

Lần 3: UPDATE bởi svc:billing lúc 09:20
    updated_at = 09:20
    updated_by = svc:billing
~~~

Sau lần 3, hàng có thể chỉ chứa `updated_by=svc:billing`. Danh tính `user:202` ở lần sửa trước **không còn trong cột đó**. Nếu cần biết toàn bộ lịch sử, cần một **bảng audit events riêng** hoặc hệ ghi sự kiện có bảo đảm/retention phù hợp (phần 14).

### 2.2. Phân biệt owner, người tạo và người sửa

Không nhầm:

- **Owner:** ai sở hữu tài nguyên, có thể đổi theo nghiệp vụ.
- **CreatedBy:** actor tạo entity tại một lần ghi theo lifecycle ứng dụng.
- **LastModifiedBy:** actor của lần cập nhật metadata gần nhất được ghi.
- **Authenticated principal:** danh tính đã được xác thực trong request hiện hành.
- **Actor có hiệu lực:** ai chịu trách nhiệm nghiệp vụ, có thể là user hoặc service hành động *on behalf of* user.

Những khái niệm này có thể khác nhau. Khi một job nền cập nhật đơn, `updated_by` nên biểu diễn job/service theo hợp đồng; không tự gán người tạo đơn như thể người đó đã thực hiện thay đổi.

## 3. Kiểu thời gian: CQL timestamp không phải write timestamp

Đối với Cassandra, ít nhất có ba mốc thời gian:

| Loại | Cách lấy | Mục đích |
|---|---|---|
| **Audit time của ứng dụng** | `DateTimeProvider`/backend `Clock` | Giá trị `created_at`, `updated_at` |
| **Event time** | Cột payload như `occurred_at` do domain cung cấp | Khi sự kiện nghiệp vụ thật sự diễn ra |
| **Write timestamp** | Metadata mutation từ driver/coordinator hoặc `USING TIMESTAMP` | Hòa giải các phiên bản cell theo LWW |

~~~sql
SELECT updated_at,
       WRITETIME(updated_at) AS updated_at_write_micros
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
~~~

- `updated_at` là cột CQL `timestamp`, giá trị có độ chính xác **mili giây**.
- `WRITETIME(updated_at)` là **metadata micro giây** của cell `updated_at`, không phải một alias cho `updated_at`.
- Hai mốc có thể khác nhau do clock skew, retry, import, explicit write timestamp hoặc chính sách tạo audit time.
- Cập nhật cột `updated_at` không buộc Cassandra dùng giá trị đó làm write timestamp của mutation.

**Quan trọng:** `@LastModifiedDate` không phải giải pháp chống lost update. Nếu cần tránh hai writer ghi đè nhau, dùng `@Version`/LWT hoặc một protocol CAS theo business invariant.

### 3.1. Chọn Instant và biểu diễn UTC

Dùng `java.time.Instant` cho mốc tuyệt đối:

~~~java
import java.time.Instant;

Instant auditTime = Instant.parse("2026-11-25T09:00:00.123Z");
~~~

Cassandra lưu CQL `timestamp` như một thời điểm với precision mili giây, **không lưu timezone ID** như `Asia/Ho_Chi_Minh`. Hiển thị theo timezone người dùng nên làm ở API/UI, không lưu `LocalDateTime` phụ thuộc timezone mặc định của máy rồi giả vờ nó là UTC.

Nếu nhận `Instant` có nano giây, cần công bố chính sách: truncate về mili giây, round, hoặc từ chối giá trị không tròn mili giây. Không viết integration test đòi giữ nguyên `Instant.now()` tới nano giây sau round-trip CQL timestamp.

## 4. Bảng theo primary key để minh họa auditing

Ứng dụng có API đọc/sửa **một đơn theo tenant và ID**:

~~~sql
CREATE TABLE orders_by_id (
    tenant_id uuid,
    order_id uuid,
    status text,
    total_amount decimal,
    created_at timestamp,
    created_by text,
    updated_at timestamp,
    updated_by text,
    version bigint,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

| Cột | Vai trò |
|---|---|
| `tenant_id` | Thành phần partition key 1, phục vụ cô lập tenant |
| `order_id` | Thành phần partition key 2, định danh đơn |
| `status`, `total_amount` | Dữ liệu nghiệp vụ |
| `created_at`, `updated_at` | Giá trị thời gian được ứng dụng ghi |
| `created_by`, `updated_by` | Định danh actor đã được chuẩn hóa |
| `version` | Optimistic locking của Spring Data, không phải clock |

Query point read:

~~~sql
SELECT tenant_id, order_id, status, total_amount,
       created_at, created_by, updated_at, updated_by, version
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
~~~

**Đủ hai khóa partition** là điều kiện để định vị đúng hàng. Auditing không tạo index hay cho phép `SELECT * FROM orders_by_id WHERE updated_by = ?` trên toàn bộ bảng theo kiểu SQL. Nếu cần “các thay đổi mới nhất bởi actor U”, thiết kế bảng truy cập hoặc hệ audit events riêng theo query (phần 14).

### 4.1. Chọn lưu actor ID, không lưu thông tin nhạy cảm tùy ý

Ví dụ `created_by='user:7f39...'`, `updated_by='service:billing-settlement'`. Ưu tiên một **stable actor ID** hoặc principal ID; tránh đưa email, access token, authorization header, thông tin cá nhân hoặc JSON principal nguyên vẹn vào cột `text`.

Với hệ multi-tenant, actor ID phải được diễn giải trong phạm vi tenant và kiểm tra authorization **trước khi ghi**. Một chuỗi `user:123` không tự chứng minh actor đó thuộc tenant hiện tại.

## 5. Enable auditing và nguồn thời gian có kiểm soát

Spring Data Cassandra cần auditing được bật và cung cấp context phù hợp. Trong một ứng dụng Spring Boot dùng synchronous repository/`CassandraTemplate`, cấu hình tham khảo:

~~~java
package example.audit;

import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.cassandra.config.EnableCassandraAuditing;

@Configuration
@EnableCassandraAuditing(
        auditorAwareRef = "requestAuditor",
        dateTimeProviderRef = "auditDateTimeProvider")
public class CassandraAuditingConfig {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean("auditDateTimeProvider")
    DateTimeProvider auditDateTimeProvider(Clock auditClock) {
        return () -> Optional.of(
                Instant.now(auditClock)
                        .truncatedTo(ChronoUnit.MILLIS));
    }
}
~~~

Ý nghĩa:

1. `@EnableCassandraAuditing` bật auditing ở **đường Spring Data Cassandra được hỗ trợ**.
2. `DateTimeProvider` cung cấp thời gian cho các thuộc tính auditing kiểu date/time.
3. `Clock` được inject thay vì gọi `Instant.now()` tùy tiện trong nhiều service và callback.
4. `truncatedTo(MILLIS)` làm chính sách precision minh bạch và giúp test round-trip với Cassandra nhất quán.
5. `auditorAwareRef` chỉ định bean chọn actor; ta sẽ định nghĩa ở phần 6.

**Không nhầm:** việc có bean `Clock` **không đổi cấu hình đồng hồ vật lý của Cassandra**, không đặt write timestamp cho driver và không đồng bộ thời gian giữa các máy. Nó chỉ giúp kiểm soát **giá trị thời gian ứng dụng đưa vào cột audit**.

### 5.1. DateTimeProvider khác Bean Clock thông thường

Nếu chỉ tạo bean `Clock` rồi gọi `Instant.now(clock)` trong một service, Spring Data auditing **không tự suy ra rằng Clock đó phải được dùng**. Dùng `dateTimeProviderRef` để gắn rõ nguồn thời gian cho callback auditing.

Khi có nhiều module cùng đăng ký auditing hoặc nhiều `Clock`, hãy đặt tên bean rõ và kiểm tra context startup. Không bật hai cấu hình auditing trùng nhau một cách ngẫu nhiên rồi đoán bean nào sẽ thắng.

### 5.2. Precision khi ứng dụng lưu timestamp

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant supplied = Instant.parse("2026-11-25T09:00:00.123456789Z");
Instant stored = supplied.truncatedTo(ChronoUnit.MILLIS);

// stored == 2026-11-25T09:00:00.123Z
~~~

**Chú ý:** truncate là chính sách mẫu, không phải quy tắc bắt buộc cho mọi hệ thống. Nếu cần bảo toàn độ chính xác micro/nano giây của event time, thiết kế thêm cột/cấu trúc riêng, không ép `timestamp` của Cassandra làm điều mà kiểu dữ liệu không biểu diễn.

## 6. AuditorAware: danh tính actor đến từ đâu?

`AuditorAware<T>` thuộc Spring Data Commons:

~~~java
import org.springframework.data.domain.AuditorAware;
~~~

Định nghĩa `T` tương ứng kiểu của các field `@CreatedBy` và `@LastModifiedBy`. Trong ví dụ này, cả hai là `String`. Provider nhận trách nhiệm **chọn actor đang thực hiện** theo context hiện hành.

### 6.1. Ví dụ lấy actor đã xác thực từ Spring Security

~~~java
package example.audit;

import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
public class AuditorProviderConfig {

    @Bean("requestAuditor")
    AuditorAware<String> requestAuditor() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext()
                            .getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            // Ví dụ: ứng dụng đã cấu hình authentication.getName()
            // trả về stable actor ID, KHÔNG phải token hoặc email.
            return Optional.of(
                    "user:" + authentication.getName());
        };
    }
}
~~~

Đây là **ví dụ có điều kiện**: `authentication.getName()` chỉ được dùng như **stable actor ID** nếu cấu hình security của dự án thực sự cung cấp điều đó. Có provider trả username hoặc email; khi ấy cần lấy ID từ **custom principal/JWT claim đã được kiểm chứng** thay vì lưu trực tiếp `getName()`.

**Không lấy actor từ request body**:

~~~json
{
  "orderId": "…",
  "status": "PAID",
  "updatedBy": "admin"
}
~~~

Field `updatedBy` do client gửi **không đáng tin cậy**; một người dùng bình thường có thể tự nhận là admin. Nếu API không có yêu cầu cho phép “acting on behalf of” theo cơ chế ủy quyền được xác thực, hãy **bỏ qua hoặc từ chối** field đó và điền actor từ server-side security context.

### 6.2. Anonymous không nên tự biến thành SYSTEM

Khi `AuditorAware` trả `Optional.empty()`, auditing có thể không có giá trị actor để ghi. Đừng âm thầm thay actor của mọi request không có security context bằng `"SYSTEM"`, vì điều đó che lỗi xác thực/context propagation.

Nên phân biệt:

- **Request bắt buộc authenticated:** không có actor ⇒ từ chối request hoặc báo lỗi authorization trước khi lưu.
- **Scheduled job đã đăng ký:** actor được định danh rõ là `service:retention-job`.
- **Message consumer:** actor là `service:order-consumer`, có thể lưu thêm originator khi nghiệp vụ cần.
- **Data migration:** actor là `service:migration-2026-11` hoặc ID vận hành có truy vết.
- **Anonymous write được phép:** phải có policy riêng rõ ràng, không giả mạo user ID.

Nếu nghiệp vụ **bắt buộc** bốn trường audit phải có giá trị, annotation tự thân **không thay database constraint hay domain validation**. Kiểm tra actor trước khi xử lý command và kiểm chứng dữ liệu sau lưu.

## 7. Entity mapping đủ bốn trường auditing

Lớp khóa ghép chỉ có hai thành phần partition:

~~~java
package example.orders;

import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class OrderKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "order_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID orderId;

    public OrderKey() {}

    public OrderKey(UUID tenantId, UUID orderId) {
        this.tenantId = tenantId;
        this.orderId = orderId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }
    public UUID getOrderId() { return orderId; }
    public void setOrderId(UUID value) { orderId = value; }

    @Override
    public boolean equals(Object candidate) {
        if (this == candidate) return true;
        if (!(candidate instanceof OrderKey)) return false;
        OrderKey other = (OrderKey) candidate;
        return Objects.equals(tenantId, other.tenantId)
                && Objects.equals(orderId, other.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, orderId);
    }
}
~~~

Entity:

~~~java
package example.orders;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderState {

    @PrimaryKey
    private OrderKey id;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedDate
    @Column("updated_at")
    private Instant updatedAt;

    @LastModifiedBy
    @Column("updated_by")
    private String updatedBy;

    @Version
    @Column("version")
    private Long version;

    public OrderState() {}

    public OrderState(OrderKey id, String status,
                      BigDecimal totalAmount) {
        this.id = id;
        this.status = status;
        this.totalAmount = totalAmount;
        // Để framework/provider điền auditing và version.
    }

    public OrderKey getId() { return id; }
    public void setId(OrderKey value) { id = value; }
    public String getStatus() { return status; }
    public void setStatus(String value) { status = value; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public void setTotalAmount(BigDecimal value) { totalAmount = value; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant value) { createdAt = value; }
    public String getCreatedBy() { return createdBy; }
    public void setCreatedBy(String value) { createdBy = value; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant value) { updatedAt = value; }
    public String getUpdatedBy() { return updatedBy; }
    public void setUpdatedBy(String value) { updatedBy = value; }
    public Long getVersion() { return version; }
    public void setVersion(Long value) { version = value; }
}
~~~

Hai class `public` phải nằm trong **hai file Java riêng**. `@Version` giúp dùng optimistic locking ở đường thao tác **một entity được Spring Data hỗ trợ**; nó không phải một phần bắt buộc của auditing, nhưng rất hữu ích để tránh một writer cũ ghi đè đồng thời `status` và `updated_by`.

### 7.1. Không để createdBy/createdAt vào primary key

Audit fields cần là **các cột thường có thể được điền qua lifecycle**. Đừng đưa `created_by` hoặc `created_at` vào primary key chỉ để dễ hiển thị. Làm vậy có thể khiến identity của hàng phụ thuộc vào actor/clock, và việc “sửa người tạo” trở thành đổi khóa.

Nếu yêu cầu **truy vấn danh sách theo created_at**, nên thiết kế bảng truy cập theo ngày/khách/tenant và clustering key phù hợp. Primary key phục vụ query pattern, không tự động được thay bằng auditing metadata.

## 8. Repository và chu kỳ tạo – sửa

Repository:

~~~java
package example.orders;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderStateRepository
        extends CassandraRepository<OrderState, OrderKey> {
}
~~~

Tạo:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

OrderState created = repository.save(new OrderState(
        new OrderKey(tenantId, orderId),
        "NEW",
        new BigDecimal("125000.00")));
~~~

Với auditing được bật, actor được cung cấp và mapping hợp lệ, Spring có thể điền `createdAt`/`createdBy` khi coi entity là mới. Với phiên bản/config mặc định phổ biến, `updatedAt`/`updatedBy` có thể cũng được đặt khi create, nhưng **đừng thiết kế contract dựa vào giả định này nếu chưa kiểm tra cấu hình `modifyOnCreate` và phiên bản thực tế**.

Đọc và sửa:

~~~java
OrderKey key = new OrderKey(tenantId, orderId);
OrderState current = repository.findById(key).orElseThrow();

current.setStatus("PAID");
OrderState saved = repository.save(current);

// createdAt, createdBy về ý tưởng giữ nguyên.
// updatedAt, updatedBy được auditing cập nhật
// khi đường save đi qua callback phù hợp.
~~~

Nếu entity có `@Version Long version`, Spring Data Cassandra dùng **LWT optimistic locking** ở đường entity-level được hỗ trợ để phát hiện stale update. Cần catch `OptimisticLockingFailureException` ở service boundary và xử lý conflict thay vì retry mù.

### 8.1. “Entity mới” là trạng thái framework quyết định

Một row “chưa từng tồn tại trong Cassandra” khác với một object mà Spring Data **đang coi là new**. Framework dựa trên metadata/newness detection, `@Version`, `@Id`, `Persistable` hoặc cơ chế cụ thể của phiên bản.

Nếu ứng dụng dựng một object mới với primary key trùng hàng cũ nhưng version null, thao tác có thể đi qua nhánh insert có điều kiện, không tự trở thành “update và giữ createdBy” như suy đoán.

**Đặc biệt:** không tự gọi `setCreatedAt` với thời gian client rồi gọi `save` để hi vọng callback bảo vệ mọi bất biến. Hãy kiểm thử hành vi create/update tương ứng với chiến lược state detection của entity.

### 8.2. Delete không có nghĩa auditing tự ghi deletedBy

~~~java
repository.deleteById(new OrderKey(tenantId, orderId));
~~~

Câu lệnh delete **không tương đương một entity update** nên không được giả định `@LastModifiedBy`/ `@LastModifiedDate` sẽ tạo một lịch sử xóa lâu dài. Khi hàng bị delete/tombstone, các cột audit của hàng đó không còn là nơi đáng tin cậy để tra cứu “ai xóa”.

Nếu cần truy vết xóa, sử dụng **soft delete có version/audit** hoặc **audit event riêng** theo yêu cầu; đánh giá retention và tính nhất quán với hành động xóa (phần 14). Cần phân biệt rõ yêu cầu pháp lý phải xóa nội dung nhạy cảm với việc duy trì bản ghi audit tối thiểu.

## 9. Phạm vi callbacks và các đường ghi có/không auditing

Cơ chế auditing của Spring Data được tích hợp trong **entity mapping lifecycle**, liên quan các entity callbacks, chứ không phải một trigger nằm trong Apache Cassandra.

| Đường ghi | Có thể dùng auditing mapping? | Ghi chú |
|---|---|---|
| `CassandraRepository.save(entity)` | **Có**, khi auditing cấu hình đúng | Đường entity-level thông dụng |
| `CassandraTemplate.insert(entity)` | **Có**, trong đường mapping/callback hỗ trợ | Kiểm thử chính xác hành vi phiên bản và options |
| `CassandraTemplate.update(entity)` | **Có**, trong đường mapping/callback hỗ trợ | Phân biệt với query-based update |
| `CassandraTemplate` với `Query/Update` chỉ định cột | **Không mặc định giống lifecycle entity** | Có thể bỏ qua auditing entity callbacks |
| `CqlTemplate.execute("UPDATE ...")` | **Không tự đọc entity annotation** | Phải điền audit fields rõ |
| `CqlSession.execute(PreparedStatement)` | **Không** | Driver chỉ biết CQL/bind values |
| `@Query` DML viết tay | **Không được giả định** | CQL thực tế quyết định audit fields |
| Batch DML | **Không được giả định** như nhiều `save` tuần tự | Kiểm tra lifecycle/optimistic locking riêng |
| Job external dùng `cqlsh` hoặc migration | **Không** | Không đi qua Spring Data application callbacks |

**Điểm cần kiểm chứng theo version:** tên callback, thứ tự callbacks và phạm vi `beforeConvert`/`beforeSave` có thể khác nhau theo API của Spring Data Cassandra. Để dựa vào auditing trong một hệ nhiều writer, hãy tạo **integration tests trên phiên bản dependency đang chạy** và quan sát chính giá trị CQL sau những đường ghi quan trọng.

### 9.1. Raw CQL phải điền actor/time tường minh

~~~sql
UPDATE orders_by_id
SET status = ?,
    updated_at = ?,
    updated_by = ?
WHERE tenant_id = ? AND order_id = ?;
~~~

Nếu `CqlTemplate` thực thi câu trên, người viết DAO phải cung cấp `updated_at` từ **trusted backend clock** và `updated_by` từ **trusted actor context**. Spring Data **không tự sửa CQL thô** để thêm các cột này.

Một sự cố phổ biến:

~~~text
Service A: repository.save(order)
    → status=PAID, updated_by=user:101

Service B: CqlSession UPDATE status='CANCELLED'
    → chỉ đổi status, không đổi updated_by

Reader thấy:
    status=CANCELLED, updated_by=user:101
~~~

Kết quả khiến audit field đánh lạc hướng: `user:101` **không phải** actor thay đổi gần nhất. Mọi writer cần tuân thủ chung một protocol hoặc ghi event riêng, không chỉ bật annotation trong một service.

## 10. Auditing và optimistic locking: hai trách nhiệm khác nhau

Hai writer đọc cùng `version=4`:

~~~text
T0: Order status=NEW, version=4

Writer A đọc version=4
Writer B đọc version=4

A muốn status=PAID, actor=user:111
B muốn status=CANCELLED, actor=user:222

Nếu cả hai ghi vô điều kiện:
    winner phụ thuộc LWW/write timestamp,
    audit fields có thể phản ánh một phần mutation.

Nếu cả hai dùng @Version LWT:
    một writer có thể thành công từ version=4 → 5,
    writer còn lại bị từ chối vì stale version.
~~~

Cần phân biệt:

- **Auditing** quyết định *giá trị nào điền vào created/updated fields*.
- **Optimistic locking** quyết định *mutation có được áp dụng khi version vẫn đúng không*.
- **Cassandra write timestamp** quyết định *hòa giải phiên bản cell* trong storage.
- **Consistency level** quyết định *số replica tham gia xác nhận* theo cấu hình, không tự biến UPDATE thành CAS.

Không suy ra từ `updated_at` mới hơn rằng mutation sẽ thắng. Không suy ra từ `LOCAL_QUORUM` rằng hai writer không thể lost update. Khi cần bất biến nghiệp vụ, dùng LWT/`@Version` và bảo đảm mọi writer tham gia protocol chung.

### 10.1. LWT thất bại có làm thay đổi audit fields?

Một câu conditional mutation không được áp dụng thì **dữ liệu trong Cassandra không được cập nhật bởi mutation đó**, kể cả `updated_by`/`updated_at` nếu chúng là một phần của mutation. Tuy vậy, object Java có thể đã được auditing callback **điền giá trị trong bộ nhớ trước khi thất bại**.

Vì vậy, sau `OptimisticLockingFailureException`, **không trả object Java vừa sửa như thể đã được lưu**. Phải đọc trạng thái thực từ Cassandra và quyết định theo domain.

## 11. Kiểm soát nguồn thời gian trong hệ nhiều instance

Giả sử có ba instance ghi Cassandra:

~~~text
App A: đồng hồ lệch +18 giây
App B: đồng hồ đúng
App C: đồng hồ lệch -7 giây
~~~

Nếu mỗi instance gọi `Instant.now()` từ đồng hồ của mình, `updated_at` có thể không theo thứ tự request thực tế. Nếu Java Driver còn dùng **client-side timestamp generator**, sai lệch đồng hồ cũng có thể ảnh hưởng **write timestamp** riêng của mutation và kết quả hòa giải LWW.

Hai tác động **khác nhau nhưng liên quan**:

1. **Audit time sai:** báo cáo “ai sửa gần nhất” bị nhầm thời gian.
2. **Write timestamp sai:** một mutation có timestamp tương lai có thể lấn át những mutation đến sau trong thực tế.

### 11.1. Đồng bộ đồng hồ và phát hiện lệch

- Dùng NTP/clock synchronization đáng tin cậy cho các máy ứng dụng và cluster.
- Theo dõi clock drift và cảnh báo khi vượt ngưỡng SLA.
- Xác định một **trusted clock policy** để các service thống nhất.
- Không truyền timestamp của điện thoại/web client vào `DateTimeProvider` cho auditing hệ thống.
- Không dùng write timestamp quá khứ/tương lai để “sửa” audit history nếu không hiểu hậu quả LWW.
- Nếu cần **thứ tự nghiệp vụ**, dùng version/sequence/CAS; đồng hồ dù chuẩn vẫn không thay thế concurrency control.

### 11.2. Nguồn thời gian “database time” có giải quyết tất cả?

Trong Cassandra không có trigger SQL chuẩn để tự cập nhật bốn cột auditing khi mỗi application gửi mutation. Việc dùng `WRITETIME()` để suy ra `updated_at` cũng không phù hợp: metadata là **theo cell**, có độ chính xác micro giây, có thể khác nhau giữa `status`, `updated_at`, `updated_by` và không phải lịch sử đầy đủ.

Nếu chính sách yêu cầu thời gian từ nguồn tập trung, dùng một **trusted time service/Clock abstraction** được kiểm soát. Nhưng không đổi tất cả request thành RPC tới một dịch vụ đồng hồ mà thiếu đánh giá availability, latency và độ chính xác cần thiết.

### 11.3. Nhiều lần gọi Clock trong cùng command

Nếu service gọi clock một lần cho `updatedAt`, callback auditing gọi clock lần nữa cho cùng entity, một vài mili giây có thể khác nhau. Thông thường đó không phải lỗi nếu mỗi trường có ý nghĩa khác nhau, nhưng với một **command audit** yêu cầu “mọi trường cùng instant” cần xác định một `AuditContext` gồm actor/time được capture tại **biên xử lý command**, rồi dùng nhất quán qua các đường ghi.

Điều này cần được thiết kế rõ ràng: một `DateTimeProvider` mặc định lấy “now” mỗi callback **không hứa** mọi mutation trên mọi bảng dùng chính xác cùng một `Instant`.

## 12. Actor của job nền, consumer, async và reactive

Trong HTTP đồng bộ thông thường, Spring Security `SecurityContextHolder` có thể có authentication. Nhưng một job nền hoặc một callback chạy trên thread khác **không tự có cùng context**.

| Nguồn ghi | Actor gợi ý | Rủi ro |
|---|---|---|
| HTTP authenticated | `user:<stable-id>` | Principal bị giả mạo nếu lấy request body |
| Scheduled job | `service:retention-job` | Không có request security context |
| Kafka/event consumer | `service:order-consumer` | Payload “initiatedBy” chưa được xác thực |
| Data migration | `service:migration-<id>` | Script raw CQL không kích hoạt callback |
| Async task | Actor snapshot được truyền có kiểm soát | Thread-local context không tự truyền |
| Reactive pipeline | Reactive security context | Thread-local imperative không đáng tin |
| Admin impersonation được ủy quyền | Cặp effective actor / original actor | Mất dấu người ủy quyền nếu chỉ ghi một field |

### 12.1. Một actor ID hay hai actor ID?

Khi một support agent hành động thay khách hàng:

~~~text
effectiveActor = user:customer-17
initiatedBy    = user:support-agent-4
reason         = approved-support-action
~~~

Nếu hệ thống chỉ lưu một `updated_by`, nên xác định **ai là actor chịu trách nhiệm** của thao tác theo hợp đồng. Nếu audit yêu cầu ghi lại cả người trực tiếp thực hiện và đối tượng đại diện, dùng **một audit event có cả hai ID**, có authorization grant và lý do phù hợp. Không nhét JSON phức tạp vào một field `updated_by` đơn giản rồi coi như audit đầy đủ.

### 12.2. Không mặc định security context sẽ đi qua @Async

Ví dụ sau **không phải một bảo đảm**:

~~~java
@Async
public void processLater(OrderCommand command) {
    repository.save(command.toEntity());
}
~~~

Nếu `AuditorAware` đọc `SecurityContextHolder` nhưng task chạy trên thread pool, context có thể **mất** hoặc bị xử lý không đúng. Giải pháp phải có chủ đích:

- Truyền một `AuditActor`/command metadata đã xác thực vào job.
- Dùng cơ chế context propagation của Spring Security phù hợp khi thực sự cần.
- Không serialize access token để tiện chuyển context trong hàng đợi.
- Tránh ThreadLocal tự chế không được cleanup vì có nguy cơ rò identity giữa các task.
- Với job được ủy quyền, xác định actor là **service** và lưu `initiatedBy` riêng nếu cần.

### 12.3. ReactiveAuditorAware và reactive context

Trong reactive pipeline, danh tính thường nằm trong **Reactor Context**. Không dùng `AuditorAware` dựa hoàn toàn vào thread-local imperative rồi giả định luôn đúng khi luồng đổi thread.

Tùy phiên bản Spring Data Cassandra/Spring Security, cần đánh giá **reactive auditing support**, `ReactiveAuditorAware` và cách truy xuất `ReactiveSecurityContextHolder` theo stack thực tế. Chỉ khi framework hỗ trợ và đã cấu hình đúng mới dựa vào callback auditing reactive. Nếu chưa có cơ chế tương ứng, hãy **truyền AuditContext tường minh** đến biên ghi bằng `ReactiveCassandraTemplate`/driver.

Không gọi `.block()` trong event-loop chỉ để lấy actor hoặc thời gian. Kiểm thử actor thực tế khi pipeline chuyển scheduler và xử lý retry/resubscription; một Reactor subscription mới có thể dẫn đến callback mới và audit time mới nếu không có policy cố định cho command.

### 12.4. Không giả mạo actor khi context trống

Một số ứng dụng chọn `Optional.of("SYSTEM")` khi không tìm thấy principal. Đây là bug audit nguy hiểm nếu request đáng ra phải authenticated.

**Quy tắc:** actor “system” chỉ hợp lệ khi **chính đường thực thi đã được định danh là system operation**, không phải fallback cho việc mất context. Phân biệt rõ lỗi authorization, bug propagation và legitimate background job.


## 13. Một giao thức audit tường minh cho đường CQL trực tiếp

Khi hệ thống không dùng `repository.save(entity)` mà cập nhật bằng `CqlSession`, hãy **chọn actor và thời gian trong service đã xác thực**, rồi truyền vào DAO cùng expected version. Không để DAO tự lấy actor từ một request body bất kỳ, cũng không hardcode `updated_by='SYSTEM'` để tránh lỗi cấu hình.

Thiết kế một command:

~~~java
package example.orders;

import java.time.Instant;
import java.util.UUID;

public record StatusChangeCommand(
        UUID tenantId,
        UUID orderId,
        String nextStatus,
        long expectedVersion,
        String actorId,
        Instant auditTime) {
}
~~~

`actorId` và `auditTime` phải được **backend tin cậy cung cấp**. Trong controller, không cho client tự đặt hai field này; một service policy layer sẽ xác định chúng từ authentication context và `Clock`.

DAO có điều kiện `IF version = ?`:

~~~java
package example.orders;

import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class AuditedStatusDao {
    private final CqlSession session;
    private final PreparedStatement update;

    public AuditedStatusDao(CqlSession session) {
        this.session = session;
        this.update = session.prepare(
                "UPDATE orders_by_id " +
                "SET status = ?, updated_at = ?, " +
                "updated_by = ?, version = ? " +
                "WHERE tenant_id = ? AND order_id = ? " +
                "IF version = ?");
    }

    public boolean tryChange(StatusChangeCommand command) {
        if (command.actorId() == null
                || command.actorId().isBlank()) {
            throw new IllegalArgumentException("Trusted actor required");
        }
        if (command.auditTime() == null) {
            throw new IllegalArgumentException("Audit time required");
        }

        long nextVersion =
                Math.addExact(command.expectedVersion(), 1L);

        Row result = session.execute(update.bind(
                command.nextStatus(),
                command.auditTime(),
                command.actorId(),
                nextVersion,
                command.tenantId(),
                command.orderId(),
                command.expectedVersion()
        )).one();

        if (result == null) {
            throw new IllegalStateException("Missing LWT result");
        }
        return result.getBoolean("[applied]");
    }
}
~~~

Đây là **CAS tường minh** dùng Java Driver, không phải `@Version` tự sinh. Trả về `false` chỉ khi Cassandra phản hồi rằng điều kiện không được áp dụng; nếu có timeout/transport error, kết quả **chưa rõ** và cần xử lý riêng.

### 13.1. Nguyên tắc capture một audit context

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

String trustedActor = actorResolver.requireActor(); // Pseudocode
Instant now = Instant.now(auditClock)
        .truncatedTo(ChronoUnit.MILLIS);

StatusChangeCommand cmd = new StatusChangeCommand(
        tenantId, orderId, "PAID", expectedVersion,
        trustedActor, now);
boolean applied = auditedStatusDao.tryChange(cmd);
~~~

`actorResolver.requireActor()` là **abstraction do ứng dụng cần triển khai**, không phải API có sẵn của Spring Data. Nó phải trả một định danh ổn định từ context đã xác thực hoặc fail-closed.

**Tại sao capture một lần?** Một command nên có thời điểm/actor rõ ràng dù bên dưới cần nhiều bước. Khi retry, nếu hợp đồng muốn giữ nguyên “thời điểm yêu cầu ban đầu”, giữ nguyên `auditTime`/command ID, không tự biến mỗi lượt retry thành một lần thay đổi nghiệp vụ mới.

### 13.2. Trong CqlTemplate

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.CqlOperations;

public void updateStatusWithoutCas(
        CqlOperations cql,
        UUID tenantId, UUID orderId,
        String nextStatus, String actorId, Instant auditTime) {

    cql.execute(
            "UPDATE orders_by_id " +
            "SET status = ?, updated_by = ?, updated_at = ? " +
            "WHERE tenant_id = ? AND order_id = ?",
            nextStatus, actorId, auditTime,
            tenantId, orderId);
}
~~~

Ví dụ này minh họa **cách cung cấp cột auditing** qua `CqlTemplate`; nó **không có optimistic locking**, vì CQL không có `IF version`. Không dùng đường vô điều kiện này bên cạnh version-aware repository cho cùng dữ liệu cần concurrency control, trừ khi đã có protocol rõ ràng để cập nhật version/đảm bảo invariants.

Lệnh `CqlOperations.execute(...)` thành công **không phải affected-row-count** xác nhận hàng tồn tại. Cassandra dùng upsert semantics; muốn điều kiện tồn tại hoặc version, dùng LWT thích hợp và đọc `[applied]`.

### 13.3. Auditing trên một entity không tự bảo vệ batch

`CassandraBatchOperations` là cơ chế nhóm mutations, **không tương đương việc gọi `repository.save(entity)` lần lượt với optimistic locking `@Version`**. Không giả định auditing lifecycle và optimistic locking trên mỗi entity có cùng semantics trong mọi kiểu batch.

Nếu batch chạm nhiều bảng/partition, một giá trị `AuditContext` dùng chung có thể làm metadata payload nhất quán, nhưng **không tạo isolation xuyên partition**. Phải phân biệt rõ **nhất quán của audit fields đã chọn** với **khả năng quan sát commit của nhiều dòng/bảng**.

## 14. Khi nào cần bảng lịch sử audit riêng?

Bốn cột `created_at/by` và `updated_at/by` hữu ích cho **ảnh chụp hiện tại**. Nhưng nhiều bài toán cần hỏi:

- Ai đã chuyển đơn từ `NEW` sang `PAID`, và vì sao?
- Trước khi xóa, giá trị `status` là gì?
- Một tác vụ nền đã tác động những entity nào trong một khoảng thời gian?
- Có bao nhiêu lần một command được retry, và kết quả cuối có được xác nhận không?
- Trình tự thay đổi nào cần được đối soát khi một read model chậm cập nhật?

Các câu hỏi này yêu cầu **audit trail/event log** tách biệt.

### 14.1. Schema audit events theo một entity và tháng

Một read model lấy lịch sử một đơn trong một tháng:

~~~sql
CREATE TABLE audit_changes_by_entity_month (
    tenant_id uuid,
    entity_type text,
    entity_id uuid,
    month_bucket date,
    changed_at timestamp,
    change_id uuid,
    actor_id text,
    action text,
    previous_version bigint,
    next_version bigint,
    request_id uuid,
    reason text,
    PRIMARY KEY (
        (tenant_id, entity_type, entity_id, month_bucket),
        changed_at, change_id
    )
) WITH CLUSTERING ORDER BY (
    changed_at DESC,
    change_id ASC
);
~~~

| Thành phần khóa | Mục đích |
|---|---|
| `(tenant_id, entity_type, entity_id, month_bucket)` | Chọn lịch sử của một entity trong tháng |
| `changed_at DESC` | Đọc sự kiện mới nhất trước |
| `change_id ASC` | Phân biệt nhiều thay đổi cùng mili giây |
| `actor_id` | Stable actor ID của command |
| `previous_version/next_version` | Thứ tự/điều kiện ứng dụng |
| `request_id` | Tương quan giữa request, command và trace |
| `reason` | Mã lý do đã được kiểm soát, không ghi dữ liệu nhạy cảm tùy ý |

Đọc:

~~~sql
SELECT changed_at, change_id, actor_id, action,
       previous_version, next_version, request_id, reason
FROM audit_changes_by_entity_month
WHERE tenant_id = ?
  AND entity_type = ?
  AND entity_id = ?
  AND month_bucket = ?
LIMIT 50;
~~~

Schema này **không tự trả “tất cả thay đổi bởi actor X trên toàn tenant”**. Với query đó cần một bảng truy cập khác theo `(tenant_id,actor_id,day_bucket)`, hoặc một hệ thống index/search/audit log chuyên dụng có governance phù hợp.

### 14.2. Append-only là hợp đồng ứng dụng, không phải bảo vệ vật lý mặc định

Bảng trên thường được dùng theo nguyên tắc append-only:

~~~sql
INSERT INTO audit_changes_by_entity_month (
    tenant_id, entity_type, entity_id, month_bucket,
    changed_at, change_id, actor_id, action,
    previous_version, next_version, request_id, reason
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

`IF NOT EXISTS` có thể giúp tránh ghi trùng cùng primary key, nhưng dùng LWT có chi phí. Có thể chọn chiến lược idempotency phù hợp với yêu cầu, **không nhất thiết mọi audit event đều cần LWT**.

“Append-only” ở đây nghĩa là **ứng dụng không sửa/xóa tùy tiện**. Cassandra vẫn cho phép DELETE/UPDATE theo quyền, nên audit có yêu cầu pháp lý/tamper evidence cần thêm **phân quyền, retention, backup, cryptographic integrity hoặc hệ log chuyên biệt**. Không gọi một bảng Cassandra bình thường là “immutable” chỉ vì code hiện tại chỉ dùng INSERT.

### 14.3. Ghi state và audit event ở hai bảng không mặc định nguyên tử

~~~text
Bảng A: orders_by_id
  UPDATE status=PAID, version=5

Bảng B: audit_changes_by_entity_month
  INSERT event "OrderPaid", changeId=E123
~~~

Hai bảng dùng hai primary keys/partitions vật lý. Nếu một mutation thành công nhưng mutation kia timeout, hệ thống có thể xuất hiện state đã đổi mà audit event chưa có, hoặc ngược lại. `@Version` của `orders_by_id` không tự điều phối audit table.

Một logged batch nhiều partition có **bảo đảm atomicity theo batchlog** nhưng **không có isolation xuyên partition**, không phải transaction SQL với global snapshot và không làm `@Version` trên nhiều entity tự chạy. Cần cân nhắc performance, concurrency và cách ứng dụng xử lý kết quả chưa rõ.

Nếu hệ thống yêu cầu audit trail đáng tin cậy hơn, đánh giá:

1. **Một aggregate/source of truth** được ghi bằng CAS với version.
2. **Event/outbox record** có ID và version ổn định, ghi theo protocol phù hợp.
3. Consumer cập nhật audit/read model **idempotent** và có checkpoint.
4. **Reconciliation** phát hiện thiếu event, event đến muộn hoặc projection lag.
5. Quy định rõ khi nào client được phép thấy trạng thái “đã xác nhận”.

Không khẳng định “bật `@CreatedBy` là có đầy đủ audit log”.

### 14.4. Event time và audit time lại khác nhau

Một consumer nhận message:

~~~text
business occurredAt : 2026-11-20T09:00Z
message receivedAt  : 2026-11-25T10:00Z
audit record written: 2026-11-25T10:00Z
~~~

Nếu bảng audit dùng `changed_at` làm clustering, phải xác định nó đại diện **thời điểm nghiệp vụ**, **thời điểm thực thi command** hay **thời điểm ghi audit**. Có thể lưu cả `occurred_at` và `recorded_at` nếu sản phẩm cần. Không đặt cùng tên `updatedAt` cho cả ba rồi tạo ordering không rõ nghĩa.

## 15. Quyền truy cập, multi-tenant và riêng tư của actor

Auditing có giá trị khi định danh là **đúng và được phép**, không chỉ “có một chuỗi”.

### 15.1. Verify tenant trước khi tạo audit event

~~~text
Token principal = user:U1
Request tenantId = T2

Authorization policy:
    U1 có quyền UPDATE order trong T2?

Nếu không:
    trả lỗi authorization,
    KHÔNG cập nhật status,
    KHÔNG viết audit "U1 đã cập nhật thành công".
~~~

Nếu cần ghi **security event** cho một nỗ lực bị từ chối, nó là một loại event khác (“unauthorized attempt”), không phải **business change applied**.

### 15.2. Không coi actor ID là bằng chứng xác thực

Chuỗi `"user:123"` trong Cassandra **không tự xác thực** danh tính. Bằng chứng đến từ hệ identity/auth và logs có integrity phù hợp. Audit field có thể bị giả mạo bởi một service có quyền ghi raw CQL, job migration hoặc client được cấp quyền quá rộng.

Do đó:

- Chặn quyền ghi trực tiếp từ client công khai vào Cassandra.
- Sử dụng service credentials với least privilege, phân tách quyền đọc/ghi.
- Kiểm soát người được sửa/đọc bảng audit events.
- Giữ audit actor ID **có cấu trúc** (loại actor, ổn định, tenant scope).
- Ghi request/correlation ID và outcome theo policy nếu cần đối soát.
- Đặt retention cho audit data; tránh lưu thông tin cá nhân không cần thiết.

### 15.3. Logging không nên vô tình tiết lộ actor/token

Một log debug in toàn bộ `Authentication`, JWT hoặc `OrderState` có thể lộ thông tin vượt nhu cầu vận hành. Chỉ log correlation ID, actor ID đã được cho phép và metadata an toàn; mask/redact PII và secret ở mọi tầng.

Nếu dùng observability traces, cần chính sách riêng cho actor-related attributes, sampling và thời gian giữ dữ liệu. Không coi `updated_by` là một trường vô hại mặc định được công bố trên mọi API.

## 16. Migration, backfill và những hàng chưa có audit fields

Trong hệ thống hiện có, nhiều hàng có thể chưa có `created_at/by` hoặc `updated_at/by`. Nếu triển khai annotation mới:

- Cassandra cho phép một số cột thường không có giá trị, và truy vấn có thể trả `null`.
- Auditing callback **không tự backfill mọi hàng cũ** chỉ vì service khởi động.
- Một lần `save` entity cũ có thể đi qua **nhánh update**, không phải create; `createdAt/createdBy` cũ có thể vẫn null.
- Đừng “khôi phục” created time bằng cách gọi `Instant.now()` rồi khẳng định đó là thời gian tạo thật của dữ liệu lịch sử.

### 16.1. Phân biệt các loại nguồn dữ liệu migration

| Nguồn giá trị | Chất lượng chứng cứ | Cách xử lý |
|---|---|---|
| Có event log tạo entity | Thường đủ để tái dựng creation time/actor theo contract | Backfill và ghi provenance |
| Có bản ghi legacy `created_timestamp` nhưng không có actor | Chỉ có thời gian legacy | Giữ actor = null/unknown theo policy |
| Chỉ có hiện trạng Cassandra | Không chắc biết thời điểm tạo thật | Không tự dựng timestamp “thật” |
| Dùng `WRITETIME(status)` | Metadata của cell hiện tại, có thể bị cập nhật nhiều lần | Không coi là creation time tổng quát |
| Import dữ liệu từ hệ khác | Có thể có actor/system identity của import | Tách nguồn nghiệp vụ khỏi nguồn import |

Nếu cần sentinel cho actor thiếu, chẳng hạn `migration:unknown`, phải thể hiện **nó là một nguồn giả định/phân loại thiếu thông tin**, không là con người thật từng thao tác. Có thể lưu migration ID và provenance trong một bảng riêng để audit việc backfill.

### 16.2. Backfill bằng CQL không kích hoạt callback auditing

~~~sql
UPDATE orders_by_id
SET created_at = ?,
    created_by = ?
WHERE tenant_id = ? AND order_id = ?;
~~~

Đây là mutation raw CQL; nó **không** gọi `@CreatedDate` của entity và cũng không tự xác thực actor. Hãy tách lệnh migration khỏi service CRUD thông thường, rate-limit nếu cần, theo dõi tombstones/cell versions và đừng dùng timestamp metadata quá xa tương lai để “ưu tiên” dữ liệu.

Nếu migration phải đồng tồn tại với writes ở production, cần giao thức version/CAS rõ ràng để tránh đè lên giá trị hợp lệ của user và tạo lại audit time sai.

## 17. Nguồn thời gian với idempotency, retry và kết quả chưa rõ

Cassandra là hệ phân tán; sau timeout client không thể luôn biết mutation đã được áp dụng hay chưa.

Ví dụ:

~~~text
Command C1 tạo lúc 09:00:00.123
  actor = user:101
  commandId = C1

Lần gửi 1:
  CQL được áp dụng, response bị mất.

Lần gửi 2:
  nếu tạo updated_at=09:00:07.250,
  hệ thống có thể biến retry thành "lần sửa mới".
~~~

Cần xác định contract:

- **Audit time của command:** capture một lần trước khi gửi, giữ nguyên qua retry nếu cùng logical command.
- **Processing time của từng attempt:** có thể ghi ở log/trace riêng, không thay audit time của command.
- **Commit/ACK time:** là mốc quan sát kết quả, không nhất thiết bằng `@LastModifiedDate`.
- **Event time:** thời điểm nghiệp vụ, có thể đến muộn; không tự bằng thời điểm commit.
- **Write timestamp metadata:** được driver/Cassandra dùng hòa giải LWW, không tự bằng bất kỳ mốc nào trên.

### 17.1. Retry LWT không phải retry UPDATE bình thường

Nếu lần đầu `UPDATE ... IF version=4` đã thành công, một retry cùng expected version `4` có thể trả `[applied]=false` do version đã thành `5`. **Không suy rằng toàn bộ command thất bại** chỉ dựa vào lần retry. Cần đối chiếu command ID/aggregate version và trạng thái thực.

Đừng tăng version trong object cũ rồi retry để “ép thành công”. Hành động đó có thể ghi đè một mutation mới từ writer khác. Nếu business invariant cần exact-once effect, dùng dedup/command log/idempotency protocol, không coi audit fields là khóa idempotency.

### 17.2. Timestamp của callback không phải commit timestamp

`DateTimeProvider` có thể được gọi **trước khi request gửi tới Cassandra**. Nếu request phải chờ mạng/Paxos hoặc timeout, `updated_at` là thời điểm callback/chuẩn bị mutation theo policy, **không phải timestamp được database xác nhận commit chính xác**.

Nếu yêu cầu chứng cứ về “lúc nào database đã commit”, cần thiết kế cơ chế quan sát/acknowledgement và audit event tương ứng, không chỉ đặt tên `updatedAt` rồi suy diễn.

## 18. Integration test: kiểm tra dữ liệu thật trong Cassandra

Unit test `DateTimeProvider` và `AuditorAware` quan trọng, nhưng không chứng minh hai callback được Spring Data gọi đúng trong `repository.save()`. Nên có **integration test với Cassandra thật**, keyspace/schema đã provision và Spring context auditing đã bật.

### 18.1. Kiểm tra create và update bằng principal test

Ví dụ dùng dependency `spring-security-test` cung cấp `@WithMockUser`:

~~~java
package example.orders;

import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class OrderAuditingIntegrationTest {
    @Autowired OrderStateRepository repository;

    @Test
    @WithMockUser(username = "audit-user-101")
    void createAndUpdateUseAuthenticatedActor() {
        OrderKey key = new OrderKey(
                UUID.randomUUID(), UUID.randomUUID());

        Instant before = Instant.now().minusSeconds(5);
        OrderState created = repository.save(new OrderState(
                key, "NEW", new BigDecimal("100.00")));
        Instant after = Instant.now().plusSeconds(5);

        assertNotNull(created.getCreatedAt());
        assertEquals("user:audit-user-101", created.getCreatedBy());
        assertFalse(created.getCreatedAt().isBefore(before));
        assertFalse(created.getCreatedAt().isAfter(after));
        assertEquals(0L, created.getVersion());

        OrderState loaded = repository.findById(key).orElseThrow();
        Instant originalCreated = loaded.getCreatedAt();
        String originalActor = loaded.getCreatedBy();

        loaded.setStatus("PAID");
        OrderState changed = repository.save(loaded);

        assertEquals("user:audit-user-101", changed.getUpdatedBy());
        assertNotNull(changed.getUpdatedAt());
        assertEquals(originalCreated, changed.getCreatedAt());
        assertEquals(originalActor, changed.getCreatedBy());
        assertEquals(1L, changed.getVersion());

        OrderState persisted = repository.findById(key).orElseThrow();
        assertEquals("PAID", persisted.getStatus());
        assertEquals("user:audit-user-101", persisted.getUpdatedBy());
    }
}
~~~

Đây là **ví dụ định hướng integration test**, chưa được chạy trong STEP 4. Nó giả định:

- Context đã đăng ký đúng `@EnableCassandraAuditing`.
- `requestAuditor` dùng `authentication.getName()` như ví dụ phần 6.
- Có dependency Spring Security Test và test authentication được truyền tới thread thực thi.
- `OrderState` mapping và bảng `orders_by_id` đã tồn tại.
- `@Version Long` được Spring Data quản lý trong thao tác một entity.
- Đồng hồ không lệch quá mức sai số `before/after`; nếu dùng `Clock.fixed`, điều chỉnh assertions tương ứng.

Cần dùng fixture mới theo UUID để tránh trạng thái cũ của các test khác. Không chạy test destructive trong production.

### 18.2. Unit test DateTimeProvider với fixed Clock

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.data.auditing.DateTimeProvider;

class AuditClockUnitTest {

    @Test
    void providerReturnsControlledMillisecondInstant() {
        Instant fixed = Instant.parse(
                "2026-11-25T09:00:00.123456789Z");
        Clock clock = Clock.fixed(fixed, ZoneOffset.UTC);

        DateTimeProvider provider = () -> Optional.of(
                Instant.now(clock).truncatedTo(ChronoUnit.MILLIS));

        assertEquals(
                Instant.parse("2026-11-25T09:00:00.123Z"),
                provider.getNow().orElseThrow());
    }
}
~~~

Bài test này chỉ chứng minh **hàm provider** và chính sách precision; **không** thay thế integration test kiểm tra auditing callback khi lưu Cassandra.

### 18.3. Test hai actor khác nhau

Một bài test có thể:

1. Tạo entity dưới actor `user:creator-101`.
2. Đọc entity dưới actor `user:editor-202`.
3. Cập nhật `status` bằng `repository.save`.
4. Kiểm chứng `created_by` vẫn là creator, `updated_by` là editor.
5. Dùng actor từ security context thật trong test; không chỉ gọi `setUpdatedBy` trên entity rồi so sánh object với chính nó.

Khi test bằng `@WithMockUser` trên hai method riêng, cần truyền **primary key fixture được quản lý đúng** và không dựa vào thứ tự chạy giữa các test. Một kịch bản end-to-end có thể dùng helper chạy dưới hai `SecurityContext` được thiết lập/cleanup có kiểm soát.

### 18.4. Test raw CQL bypass auditing

Trong test cô lập, sau khi tạo order qua repository:

~~~sql
UPDATE orders_by_id
SET status = 'CANCELLED'
WHERE tenant_id = ? AND order_id = ?;
~~~

Đọc lại `status`, `updated_by`, `updated_at`, `version`.

Kỳ vọng về mặt cơ chế: raw CQL **chỉ ghi những cột nó đề cập**, không kích hoạt Spring auditing, không tự tăng version. Do đó test phải **phơi lộ rủi ro protocol**, chứ không khẳng định audit fields tự đổi.

Đừng đưa câu UPDATE vô điều kiện vào production nếu entity đang dùng `@Version` để bảo vệ invariant; test này nhằm **chứng minh sự thiếu bảo vệ** và thúc đẩy thống nhất write paths.

### 18.5. Các kiểm thử khác

| Bài test | Kết quả cần chứng minh |
|---|---|
| No authentication trên write bắt buộc auth | Request bị từ chối **trước khi lưu**, không được gán SYSTEM giả |
| Background actor `service:retention-job` | Được xác định bởi job context có chủ đích |
| Async task | Actor không mất hoặc không rò từ task trước |
| Reactive pipeline | Actor được lấy đúng từ reactive context, không dùng thread-local sai |
| Clock fixed/precision | Timestamp theo policy UTC, tròn mili giây |
| Clock skew giả lập | Ứng dụng không coi `updated_at` là sequence CAS |
| Concurrent writers | `@Version` từ chối stale update |
| Raw CQL | Auditing callback không tự chạy |
| Delete theo ID | Không tự có dòng lịch sử `deleted_by` |
| Batch nhiều bảng | Không mặc định atomic snapshot toàn cục |
| LWT timeout | Xử lý kết quả chưa rõ, không trả thành công giả |
| Import legacy entity | Không tự bịa createdAt/createdBy |
| Event log retry | Change ID ổn định, không tạo lịch sử trùng |
| Security/logging | Không đưa JWT, email hoặc PII ngoài policy vào audit fields |

## 19. Quan sát vận hành và báo cáo audit

Một số chỉ số có ích:

| Nhóm | Tín hiệu |
|---|---|
| **Completeness** | Tỷ lệ entity thiếu `created_at/by` hoặc `updated_at/by` ngoài policy |
| **Identity** | Audit actor unknown, missing security context, tỷ lệ system jobs |
| **Clock** | NTP drift, timestamp future-skew, precision violations |
| **Concurrency** | `OptimisticLockingFailureException`, LWT contention/timeout |
| **Persistence** | Raw CQL writes, batch paths, event projection lag |
| **Retention** | TTL/tombstones của audit events, backup retention |
| **Security** | Unauthorized attempts, privileged changes, audit table access |
| **Read** | p95/p99, hot partition, paging/tombstone scans của bảng audit log |

**Đừng quét toàn Cassandra** chỉ để tính tỷ lệ audit missing fields theo lịch trình. Với dữ liệu lớn, chọn phương án sampling an toàn, counter/metrics ở đường ghi, hoặc bảng/stream phục vụ thống kê. Một câu `ALLOW FILTERING` trên bảng lớn không phải giải pháp báo cáo lâu dài.

### 19.1. SLA của audit dữ liệu hiện tại và audit event khác nhau

Có thể có hai mức:

- **Current-state audit:** `updated_by`/ `updated_at` đi cùng entity, dùng để hiển thị “sửa lần gần nhất”.
- **Audit trail:** các audit events phải được ghi/đối soát với độ trễ SLA cho phép và có thể phục hồi khi consumer thất bại.

Nếu audit trail cần bằng chứng pháp lý, yêu cầu durability, integrity, retention, access controls và event completeness thường **nghiêm ngặt hơn** CRUD auditing thông thường. Cần phân tích threat model trước khi chọn Cassandra table làm bản ghi cuối.

## 20. Lỗi thường gặp và hướng khắc phục

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Lấy `updatedBy` từ JSON client | Người dùng giả mạo actor | Lấy từ principal đã xác thực |
| Để `AnonymousAuthenticationToken` thành user thật | Audit chứa actor sai | Kiểm tra auth và fail-closed |
| Mất SecurityContext trong `@Async` | Audit rỗng hoặc giả SYSTEM | Truyền AuditContext/propagate có kiểm soát |
| Dùng ThreadLocal imperative trong Reactor | Wrong actor khi scheduler đổi thread | Dùng reactive context hỗ trợ hoặc context tường minh |
| Gọi `Instant.now()` tùy ý mỗi tầng | Mốc không nhất quán và khó test | Inject `Clock`, dùng `DateTimeProvider` |
| Ghi `LocalDateTime` theo server default zone | Sai giờ giữa môi trường | Dùng `Instant` và zone policy |
| So sánh `Instant` nano với CQL timestamp | Test round-trip thất bại | Chuẩn hóa mili giây |
| Xem `updated_at` là write timestamp | Hiểu sai LWW | Phân biệt cột CQL với `WRITETIME` |
| Dùng `updated_at` thay version | Lost update khi concurrent writers | Dùng `@Version`/LWT |
| Tin `@CreatedDate` luôn bất biến dù raw CQL | Có thể bị ghi đè | Bảo vệ write paths/quyền ghi |
| Tin `@LastModifiedBy` tự chạy trên CqlSession | Audit bỏ sót actor | Điền actor/time tường minh trong DAO |
| Tin `save` là PATCH field-level trong mọi case | Null/omitted fields có semantics riêng | Dùng update chọn lọc, test mapping |
| Tin batch tự động có auditing/LWT cho mọi entity | Bỏ sót checks, lỗi từng phần | Kiểm tra API và test đường batch |
| Hiểu `deleteById` tạo audit event xóa | Không có log xóa | Ghi event riêng/soft delete |
| Bật auditing cho hàng legacy là đã backfill | Cột cũ vẫn null | Migration có provenance |
| Lấy `WRITETIME` của cell làm thời gian tạo entity | Không phải creation timestamp tin cậy | Dùng source-of-truth event/legacy metadata |
| Retry command bằng timestamp mới mỗi lần | Sai lịch sử/overwrite | Command ID và audit time ổn định |
| Ghi email/JWT vào actor text | Lộ PII/secret | Stable IDs và data minimization |
| Thấy audit fields có giá trị nên nghĩ có audit trail | Chỉ là ảnh chụp gần nhất | Bảng event log và đối soát |
| Truy vấn toàn bảng theo `updated_by` | Thiếu access table/index | Thiết kế theo query pattern |

## 21. Bài tập thực hành

Ứng dụng quản lý phiếu hoàn tiền có bảng:

~~~sql
CREATE TABLE refund_state_by_id (
    tenant_id uuid,
    refund_id uuid,
    status text,
    amount decimal,
    created_at timestamp,
    created_by text,
    updated_at timestamp,
    updated_by text,
    version bigint,
    PRIMARY KEY ((tenant_id, refund_id))
);
~~~

### Bài tập A — nguồn actor có thể tin cậy

Hai request:

~~~json
{"refundId":"R1","status":"APPROVED","updatedBy":"admin"}
~~~

và:

~~~json
{"refundId":"R1","status":"APPROVED"}
~~~

Đều đến từ authentication `user:clerk-101`. Hãy giải thích actor nào phải được lưu, vì sao input `updatedBy` không được tin, và trường hợp nào cần ghi riêng một sự kiện bị từ chối.

### Bài tập B — DateTimeProvider có thể kiểm thử

Viết `Clock.fixed` ở `2026-11-25T09:00:00.123456789Z`; triển khai `DateTimeProvider` trả `Instant` đã truncate mili giây. Kỳ vọng `created_at` sau lưu mới là `2026-11-25T09:00:00.123Z` trên test cluster đã provision.

Giải thích vì sao đổi `ZoneId` hiển thị ở UI **không được đổi instant đang lưu**.

### Bài tập C — hai writer cùng version

Writer A và B cùng đọc `version=2`, A đổi `status=APPROVED` dưới actor `user:manager-A`, B đổi `status=REJECTED` dưới actor `user:manager-B`.

1. Nếu cả hai `UPDATE` vô điều kiện, có thể xảy ra gì với `status` và audit fields?
2. Với `@Version`/LWT `IF version=2`, writer nào có thể được áp dụng?
3. Writer bị từ chối phải xử lý gì?
4. Vì sao không tự tăng `version` trong entity stale rồi retry?

### Bài tập D — batch và auditing nhiều bảng

Sau khi refund được duyệt, service cần ghi bảng `refund_state_by_id` và bảng `refunds_by_customer_month` có partition key khác.

Hãy đề xuất cách giữ actor/time trong command, bảo vệ aggregate bằng CAS, cập nhật projection với event ID/version idempotent và đối soát khi projection chậm. Giải thích vì sao một logged batch **không tạo snapshot/isolation xuyên bảng** và `@Version` trên một entity **không bảo vệ batch**.

### Bài tập E — nguồn thời gian của event đến muộn

Một consumer xử lý refund event xảy ra ngày 20/11 nhưng tới hệ thống ngày 25/11.

- `occurred_at` nên lấy từ đâu và có thể tin đến mức nào?
- `recorded_at`/audit time nên lấy từ nguồn nào?
- Nếu dùng `updated_at` để hiển thị lần cập nhật gần nhất, điều gì phải công bố?
- Vì sao không được tự chọn write timestamp bằng `event.occurredAt`?
- Khi retry command, audit time có nên thay đổi không? Phụ thuộc hợp đồng nào?

### Bài tập F — audit history và query-driven design

Thiết kế bảng `refund_audit_by_entity_month` để đọc 50 thay đổi gần nhất của một refund theo tháng. Chọn composite partition key, clustering time và change ID. Mở rộng nếu UI còn cần báo cáo “tất cả thay đổi của một actor trong một ngày” mà không dùng `ALLOW FILTERING`.

### Câu hỏi tự kiểm tra

1. Bốn annotation auditing Spring Data có tên gì?
2. `@EnableCassandraAuditing` có tự chọn `Clock` ứng dụng nếu không gắn `DateTimeProvider` không?
3. `AuditorAware<String>` nên lấy actor từ request body hay trusted principal?
4. Vì sao `updated_by` không phải log đầy đủ mọi lần thay đổi?
5. Một job scheduler không có principal HTTP nên ghi actor như thế nào?
6. Vì sao async/thread pool có thể làm mất `SecurityContextHolder`?
7. Trong Reactor, dùng imperative thread-local AuditorAware có đáng tin không?
8. `@LastModifiedDate` có tự là write timestamp metadata của Cassandra không?
9. `repository.save` và raw `CqlSession.execute` có cùng auditing callbacks không?
10. `@Version` và `updated_at` khác nhau ở trách nhiệm nào?
11. Vì sao timeout LWT không chứng minh mutation chưa được áp dụng?
12. Bật auditing có tự backfill `created_by` cho hàng cũ không?
13. Xóa entity có tự sinh `deleted_by` bất biến không?
14. Nếu cần audit trail đáng tin cậy, cần thêm những cơ chế nào ngoài bốn cột?

**Đáp án gợi ý:** (1) `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy`; (2) không mặc định; (3) principal đã xác thực; (4) chỉ phản ánh trạng thái gần nhất; (5) actor service rõ danh tính; (6) thread-local không tự truyền; (7) không, cần reactive/context phù hợp; (8) không; (9) không; (10) version là CAS, updated_at là dữ liệu; (11) phản hồi có thể mất sau commit; (12) không; (13) không; (14) log events, idempotency, reconciliation, access control, retention/integrity và policy phù hợp.

## 22. Checklist trước khi triển khai

- [ ] Đã định nghĩa rõ **người tạo/người sửa**, nguồn actor và định dạng stable ID.
- [ ] Không lấy `createdBy`/`updatedBy` từ payload chưa được xác thực.
- [ ] Kiểm tra authorization và tenant scope trước khi tạo mutation.
- [ ] Cấu hình `@EnableCassandraAuditing` và `auditorAwareRef` đúng bean.
- [ ] Cấu hình `dateTimeProviderRef` với `Clock` đáng tin cậy và chính sách precision.
- [ ] Dùng `Instant`, tránh timezone mặc định không kiểm soát.
- [ ] Đồng bộ/giám sát clock drift trên app nodes và cluster.
- [ ] Phân biệt audit time, event time, processing time và Cassandra write timestamp.
- [ ] Các trường auditing nằm ở **cột thường**, không bị đưa vào primary key tùy tiện.
- [ ] Entity mapping khớp schema và newness/version semantics đã được test.
- [ ] Hiểu `@Version`/LWT phát hiện lost update, audit fields không thay thế CAS.
- [ ] Kiểm tra `OptimisticLockingFailureException` và xử lý timeout chưa rõ kết quả.
- [ ] Mọi raw CQL, `@Query` DML, batch và migration tôn trọng audit protocol chung.
- [ ] Không giả định auditing callback tự chạy trên `CqlSession`.
- [ ] Background jobs có actor service hợp lệ; không fallback SYSTEM cho lỗi auth.
- [ ] Async/reactive có context propagation phù hợp, kiểm thử không rò actor giữa tasks.
- [ ] `created_at/by` của hàng cũ có provenance hoặc chính sách null/unknown.
- [ ] Không coi bốn cột auditing là audit history bất biến.
- [ ] Khi cần lịch sử, có event/change ID ổn định và bảng truy cập theo query.
- [ ] Đã phân tích consistency, projection lag, ghi từng phần giữa hai bảng và reconciliation.
- [ ] Có policy retention, truy cập audit data và xử lý PII/secret.
- [ ] Integration tests kiểm chứng create/update, hai actor, raw CQL bypass và concurrent writers.
- [ ] Không suy từ thành công kỹ thuật của Markdown rằng code ví dụ đã QA/CI/production.

## 23. Tổng kết

**Kiểm soát nguồn thời gian và người thao tác** là một hợp đồng xuyên suốt nhiều tầng:

1. **Spring Data auditing** điền giá trị vào các trường `created_at/by` và `updated_at/by` ở **đường entity lifecycle được hỗ trợ**.
2. **`DateTimeProvider` và `Clock`** giúp định nghĩa nguồn thời gian, UTC và precision; **`AuditorAware`** giúp lấy actor tin cậy từ context đã được xác thực.
3. **Raw CQL, batch, migration, async và reactive** cần được kiểm tra riêng; không có bảo đảm “annotation sẽ chạy ở mọi đường ghi”.
4. **`@Version`/LWT** giúp bảo vệ concurrency khi cần, nhưng không thay auditing, không bảo vệ nhiều bảng một cách tự động.
5. **Audit trail** muốn đầy đủ phải có event log, ID ổn định, policy lưu giữ, đối soát và kiểm soát quyền phù hợp — không chỉ thêm bốn cột vào entity.

Trong Spring Data Cassandra, audit đáng tin cậy bắt đầu từ **nguồn dữ liệu đúng và quyền truy cập đúng**, tiếp đến là **write protocol thống nhất**, và kết thúc ở **integration tests trên Cassandra thật**.

## Tài liệu tham khảo

- [Spring Data Cassandra — Auditing](https://docs.spring.io/spring-data/cassandra/reference/auditing.html).
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html).
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).
- [Spring Data Cassandra — Entity Callbacks](https://docs.spring.io/spring-data/cassandra/reference/cassandra/entity-callbacks.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Spring Data Cassandra — Repository Core Concepts](https://docs.spring.io/spring-data/cassandra/reference/repositories/core-concepts.html).
- [Spring Security — SecurityContextHolder](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html).
- [Spring Security — Reactive Security](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html).
- [Apache Cassandra — CQL Data Manipulation, IF và BATCH](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Apache Cassandra Java Driver 4 — Query Timestamps](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/query_timestamps/).
