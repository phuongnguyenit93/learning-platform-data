# @CreatedDate, @LastModifiedDate, @CreatedBy và @LastModifiedBy

> **Chương:** Vòng đời và auditing  
> **Phạm vi:** Spring Data Cassandra truy cập Apache Cassandra qua entity mapping, repository, CassandraTemplate và CQL.  
> **Mục tiêu:** cấu hình đúng bốn annotation auditing, xác định actor và thời điểm, nhận biết entity mới, kiểm chứng insert/update, đồng thời hiểu những đường ghi **không tự chạy auditing** và giới hạn của Cassandra trong môi trường phân tán.

## 1. Bài toán: ai đổi trạng thái thiết bị và đổi khi nào?

Trong một nền tảng IoT, bảng metadata của thiết bị chứa tên hiển thị, firmware và cấu hình. Một thiết bị có thể được đăng ký bởi người vận hành, sau đó đổi tên qua giao diện quản trị; một tác vụ nền có thể đồng bộ firmware từ hệ thống khác.

API cần trả lời:

- Ai tạo bản ghi metadata này?
- Bản ghi được tạo vào thời điểm nào?
- Ai là người hoặc hệ thống sửa gần nhất?
- Thời điểm sửa gần nhất là khi nào?

Ví dụ:

~~~text
tenant_id       = 11111111-1111-4111-8111-111111111111
device_id       = 22222222-2222-4222-8222-222222222222
display_name    = "Cảm biến kho A"
created_at      = 2026-11-25T08:00:00Z
created_by      = "user:operator-42"
modified_at     = 2026-11-25T09:15:00Z
modified_by     = "service:device-sync"
~~~

Spring Data cung cấp bốn annotation để điền những thông tin trên **khi entity đi qua luồng lưu trữ có hỗ trợ auditing**. Tuy nhiên, chúng không phải trigger của Cassandra server: một lệnh `UPDATE` viết thẳng bằng CQL hoặc một worker khác có thể không chạy callback này.

**Điểm quan trọng nhất của riêng Cassandra:** vì ID phải có trước khi ghi, Spring Data có thể hiểu một entity mới với ID đã gán là entity **đã tồn tại**. Nếu không thiết kế cơ chế nhận biết entity mới, `@CreatedDate` và `@CreatedBy` có thể không được điền theo kỳ vọng.

## 2. Bốn annotation có ý nghĩa gì?

Cả bốn thuộc package `org.springframework.data.annotation`.

| Annotation | Ý nghĩa | Cột CQL ví dụ | Thời điểm dự kiến |
| --- | --- | --- | --- |
| `@CreatedDate` | Thời điểm ứng dụng tạo entity | `created_at timestamp` | Khi auditing xác định entity **mới** |
| `@LastModifiedDate` | Thời điểm entity được sửa/lưu theo luồng auditing | `modified_at timestamp` | Khi sửa; có thể cả lúc tạo |
| `@CreatedBy` | Actor được xác định tại thời điểm tạo | `created_by text` | Khi tạo và có auditor |
| `@LastModifiedBy` | Actor thực hiện thay đổi gần nhất | `modified_by text` | Khi sửa; có thể cả lúc tạo |

Ví dụ cú pháp:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;

@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant modifiedAt;

@CreatedBy
private String createdBy;

@LastModifiedBy
private String modifiedBy;
~~~

Những annotation này có thể áp dụng chọn lọc. Nếu chỉ cần thời gian, không bắt buộc có `AuditorAware`. Nếu dùng trường actor, ứng dụng cần cơ chế xác định auditor để biết ai đang thực hiện thao tác.

**Audit metadata khác audit history:** bốn field thường chỉ giữ **trạng thái mới nhất** và thông tin tạo ban đầu. Chúng không ghi lại mọi lần sửa, không lưu before/after của từng thay đổi và không tự đáp ứng yêu cầu nhật ký bất biến.

## 3. Cassandra không tự cập nhật các annotation này

Luồng dự kiến khi dùng Spring Data entity:

~~~mermaid
flowchart TD
    A["HTTP request / worker / message consumer"] --> B["Xác định actor đáng tin cậy"]
    B --> C["Service thao tác entity"]
    C --> D["Repository.save / Template entity insert-update"]
    D --> E["AuditingEntityCallback: BeforeConvert"]
    E --> F{"Entity được nhận diện là mới?"}
    F -->|Có| G["CreatedDate, CreatedBy và modified fields theo cấu hình"]
    F -->|Không| H["LastModifiedDate, LastModifiedBy"]
    G --> I["Mapping thành CQL statement"]
    H --> I
    I --> J["Cassandra replicas nhận mutation"]
~~~

Spring Data Cassandra sử dụng `AuditingEntityCallback` trên pha `BeforeConvert` để đánh dấu một entity được tạo hay sửa trước khi nó được chuyển thành statement. Đây là cơ chế **phía ứng dụng Java**, không phải server-side trigger.

Vì vậy, các đường ghi sau phải được đánh giá riêng:

- `repository.save(entity)` và các thao tác entity của `CassandraTemplate` có thể đi qua callbacks.
- `CassandraTemplate.update(Query, Update, Class)` cập nhật theo cột/CQL, không cần một entity để chạy auditing theo cách trên.
- `CqlTemplate.execute(...)`, `CqlSession.execute(...)` và `@Query` viết câu `UPDATE` trực tiếp không tự “biết” bốn annotation trên entity.
- Worker ở dịch vụ khác, script migration, `cqlsh`, CDC/replay hoặc batch đặc biệt có thể ghi mà không qua Spring auditing.

**Không đưa ra cam kết “mọi UPDATE đều có modified_at/modified_by” chỉ vì entity đã gắn annotation.** Muốn cam kết đó, phải có chính sách bao phủ **mọi đường ghi**.

## 4. Tạo schema cho metadata thiết bị

Ví dụ dùng bảng một row cho một `tenant_id + device_id`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS telemetry.device_metadata_by_id (
    tenant_id     uuid,
    device_id     uuid,
    display_name  text,
    firmware      text,
    created_at    timestamp,
    modified_at   timestamp,
    created_by    text,
    modified_by   text,
    version       bigint,
    PRIMARY KEY ((tenant_id, device_id))
);
~~~

`SimpleStrategy` với RF=1 chỉ dành cho môi trường học tập. Trong production, replication strategy, RF và consistency phải phù hợp topology thực tế, thường là `NetworkTopologyStrategy` cho nhiều datacenter.

Ở đây:

- `(tenant_id, device_id)` là **composite partition key** duy nhất của một row.
- `created_at`/`modified_at` ánh xạ từ `Instant`, kiểu CQL `timestamp`.
- `created_by`/`modified_by` lưu một định danh actor đơn giản, không phải thông tin xác thực bí mật.
- `version` dùng cho **optimistic locking**, đồng thời giúp Spring Data phân biệt entity mới khi ID đã có.

Lựa chọn partition key này phục vụ query metadata bằng cả `tenantId` và `deviceId`:

~~~sql
SELECT display_name, firmware, created_at, modified_at,
       created_by, modified_by, version
FROM telemetry.device_metadata_by_id
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222;
~~~

Cassandra không sinh ID tự động; ứng dụng phải cung cấp cả hai UUID. `version` không phải thành phần partition key hay clustering key, mà là cột phục vụ điều kiện cập nhật.

## 5. Ánh xạ composite key trong Java

Một lớp khóa phù hợp DDL:

~~~java
import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class DeviceKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(
        name = "tenant_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    public DeviceKey() { }

    public DeviceKey(UUID tenantId, UUID deviceId) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.deviceId = Objects.requireNonNull(deviceId);
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof DeviceKey that)) return false;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(deviceId, that.deviceId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, deviceId);
    }
}
~~~

`equals`/`hashCode` phải xét đủ hai phần khóa; chỉ so `deviceId` có thể khiến hai thiết bị thuộc hai tenant bị nhầm là một. Dùng `@PrimaryKeyClass` với `@PrimaryKeyColumn` để metadata mapping không phụ thuộc cách framework suy tên mặc định.

Trong các API, luôn kiểm tra tenant ở service/security layer. Việc tenant nằm trong primary key giúp định vị và tách dữ liệu, **không tự cung cấp authorization**.

## 6. Entity chứa đầy đủ bốn field auditing và version

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_metadata_by_id")
public class DeviceMetadata {

    @PrimaryKey
    private DeviceKey key;

    @Column("display_name")
    private String displayName;

    @Column("firmware")
    private String firmware;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedDate
    @Column("modified_at")
    private Instant modifiedAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedBy
    @Column("modified_by")
    private String modifiedBy;

    @Version
    @Column("version")
    private Long version;

    public DeviceMetadata() { }

    public DeviceMetadata(DeviceKey key, String name) {
        this.key = key;
        this.displayName = name;
    }

    public DeviceKey getKey() { return key; }
    public void setKey(DeviceKey value) { key = value; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { displayName = value; }

    public String getFirmware() { return firmware; }
    public void setFirmware(String value) { firmware = value; }

    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant value) { createdAt = value; }

    public Instant getModifiedAt() { return modifiedAt; }
    public void setModifiedAt(Instant value) { modifiedAt = value; }

    public String getCreatedBy() { return createdBy; }
    public void setCreatedBy(String value) { createdBy = value; }

    public String getModifiedBy() { return modifiedBy; }
    public void setModifiedBy(String value) { modifiedBy = value; }

    public Long getVersion() { return version; }
    public void setVersion(Long value) { version = value; }
}
~~~

Điểm cần chú ý:

- `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy` đều từ `org.springframework.data.annotation`, **không** phải JPA annotations.
- `@Version` thuộc Spring Data Commons; trong Cassandra, optimistic locking tận dụng lightweight transactions (LWT).
- Dùng `Long` chứ không dùng primitive `long` để giá trị `null` biểu diễn entity chưa có version.
- Cột audit là **regular columns**, không nên đặt vào partition key; nếu thay đổi audit field thì primary key không đổi.
- Entity có setter để minh họa; với immutable domain object/record cần constructor, mapping và callback phù hợp phiên bản Spring Data đang sử dụng.

**Không cho client ghi tùy ý** vào `createdBy` hoặc `modifiedBy`. Những field này phải đến từ hệ thống xác thực/tác vụ đáng tin cậy, không phải từ request JSON.

## 7. Bật auditing bằng @EnableCassandraAuditing

Thêm starter Cassandra theo dependency management của Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
}
~~~

Khai báo auditing trong configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.config.EnableCassandraAuditing;

@Configuration
@EnableCassandraAuditing(
    auditorAwareRef = "currentAuditor",
    modifyOnCreate = true)
public class CassandraAuditConfiguration {
}
~~~

`@EnableCassandraAuditing` đăng ký hạ tầng auditing cho đường **imperative**. Nếu chỉ gắn bốn annotation lên entity nhưng không bật auditing, đừng kỳ vọng framework tự điền field.

Có thể cấu hình:

| Thuộc tính | Mục đích | Mặc định trong Javadoc |
| --- | --- | --- |
| `auditorAwareRef` | Chọn bean `AuditorAware` khi có nhiều bean | Chuỗi rỗng, tự chọn bean nếu có |
| `dateTimeProviderRef` | Chọn bean `DateTimeProvider` để cấp thời gian | Chuỗi rỗng |
| `setDates` | Có thiết lập ngày tạo/sửa hay không | `true` |
| `modifyOnCreate` | Có điền modified fields lúc tạo hay không | `true` |

Với `modifyOnCreate = true`, một entity mới có thể được điền cả `createdAt/createdBy` và `modifiedAt/modifiedBy` khi tạo. Nếu nghiệp vụ muốn modified fields chỉ xuất hiện **sau lần sửa đầu tiên**, chọn `modifyOnCreate = false` và kiểm thử đúng version.

**Không có cờ `spring.cassandra.auditing.enabled` mặc định nào thay thế trực tiếp** việc cấu hình auditing nêu trên. Tên và khả năng cấu hình phải đối chiếu với Spring Data version mà ứng dụng sử dụng.

## 8. AuditorAware: lấy danh tính actor từ nơi đáng tin cậy

Khi dùng `@CreatedBy` hoặc `@LastModifiedBy`, Spring Data cần `AuditorAware<T>`. Ở đây field actor là `String`, nên bean dùng `AuditorAware<String>`.

Ví dụ dựa trên Spring Security cho application **imperative**:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
public class CurrentActorConfiguration {

    @Bean("currentAuditor")
    public AuditorAware<String> currentAuditor() {
        return () -> Optional.ofNullable(
                    SecurityContextHolder.getContext()
                        .getAuthentication())
            .filter(Authentication::isAuthenticated)
            .filter(auth ->
                !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .filter(name -> !name.isBlank());
    }
}
~~~

Ví dụ này yêu cầu Spring Security và giả định `Authentication.getName()` cho định danh đã xác thực phù hợp với chính sách audit. Nếu dùng OAuth2/JWT, bạn có thể cần map một claim ổn định như subject ID, không mặc định username có thể đổi là định danh bền vững.

**Tại sao phải loại anonymous?** Spring Security có thể trả một `AnonymousAuthenticationToken` được coi là authenticated theo cách implementation đánh dấu. Dùng mỗi `Authentication::isAuthenticated` không nhất thiết loại được anonymous.

Trong batch job hoặc message consumer không có HTTP SecurityContext, bean ở trên có thể trả `Optional.empty()`. Điều đó không nên tự bị diễn giải thành actor “người dùng cuối”. Phải chọn chính sách actor hệ thống một cách có chủ đích.

## 9. Actor của worker, scheduler và message consumer

Một tác vụ nền đổi firmware bằng sự kiện từ hệ thống ngoài. Không có người dùng đăng nhập trực tiếp, nhưng vẫn cần audit:

~~~text
Operation: firmware sync
Actor:     service:firmware-sync
Origin:    trusted scheduled job/message consumer
Request:   internal correlation ID
~~~

Hai cách thiết kế phổ biến:

1. **Identity of service:** cấu hình một danh tính ổn định cho worker, ví dụ `service:firmware-sync`; sử dụng nguồn thông tin trong môi trường thực thi được tin cậy.
2. **On-behalf-of actor:** nếu job thực thi thay một người dùng, lưu identity của người đó và metadata nguồn/correlation ID, sau khi đã xác thực sự ủy quyền.

Không lấy `createdBy` hoặc `modifiedBy` trực tiếp từ body request hoặc header do client bất kỳ gửi. Một header `X-Actor: admin` không biến caller thành admin.

Khi cần phân biệt actor loại user/service, có thể dùng string có prefix ổn định hoặc một object audit tách `actor_type` và `actor_id`. Nếu nhu cầu truy vấn theo actor nhiều, hãy cân nhắc bảng audit events theo access pattern, thay vì lọc ad hoc `WHERE modified_by = ?` trên bảng metadata có partition key theo device.

## 10. DateTimeProvider và thời gian audit

`@CreatedDate`/`@LastModifiedDate` lấy thời gian từ `DateTimeProvider` của Spring Data. Mặc định là provider thời gian hiện tại; có thể cấp provider riêng bằng `dateTimeProviderRef`.

Ví dụ dùng `Clock` để có thể kiểm soát trong test:

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

    @Bean("auditTime")
    public DateTimeProvider auditTime(Clock auditClock) {
        return () -> Optional.of(Instant.now(auditClock));
    }
}
~~~

Đổi annotation cấu hình thành:

~~~java
@EnableCassandraAuditing(
    auditorAwareRef = "currentAuditor",
    dateTimeProviderRef = "auditTime",
    modifyOnCreate = true)
~~~

Trong unit/integration test có thể thay `Clock.systemUTC()` bằng một `Clock.fixed(...)` hoặc một provider có thể điều khiển, giúp test không phải dùng `Thread.sleep(...)`.

### Audit date không phải Cassandra writetime

| Thời gian | Nguồn | Mục đích |
| --- | --- | --- |
| `created_at`/`modified_at` | Spring Data auditing/provider | Thời gian sự kiện tạo/sửa theo ứng dụng |
| `WRITETIME(column)` | Cassandra mutation timestamp | Hòa giải xung đột replica/last-write-wins |
| `event_time` | Timestamp nghiệp vụ từ thiết bị | Thời điểm event xảy ra |
| `received_at` | Ingest service | Thời điểm hệ thống tiếp nhận event |

Ba loại thời gian này có thể khác nhau. Cassandra `timestamp` thường lưu độ phân giải **millisecond**, trong khi Java `Instant` có nanosecond; test phải hiểu chính sách chuyển đổi chính xác.

## 11. Vấn đề riêng của Cassandra: entity có ID sẵn chưa chắc được xem là mới

Trong SQL/JPA, nhiều ứng dụng quen ID tự tăng sau khi INSERT. Cassandra không tự sinh primary key lúc ghi, nên ứng dụng thường làm:

~~~java
DeviceMetadata entity = new DeviceMetadata(
    new DeviceKey(tenantId, deviceId), "Cảm biến kho A");
repository.save(entity);
~~~

Mặc định, Spring Data dùng **ID inspection**: nếu ID khác null, entity thường được coi là **không mới**. Với Cassandra, ID luôn phải được gán trước, nên cơ chế mặc định này **không đủ** để auditing biết đó là lần tạo đầu tiên.

Kết quả không mong muốn có thể là:

~~~text
Entity vừa dựng:
  key        = có giá trị
  createdAt  = null
  createdBy  = null

Spring Data nhận diện:
  "id khác null" -> không mới

Auditing khi save:
  cập nhật modifiedAt/modifiedBy
  có thể không điền createdAt/createdBy
~~~

Tài liệu Spring Data Cassandra nhắc rõ: muốn auditing hoạt động đúng với entity có ID do ứng dụng gán, hãy cân nhắc **optimistic locking với `@Version`** hoặc triển khai `Persistable` để điều khiển `isNew()`.

Đây là điểm đáng kiểm tra nhất nếu test phát hiện `@LastModifiedDate` có giá trị còn `@CreatedDate` luôn null.

## 12. Lựa chọn 1: dùng @Version để nhận biết entity mới

Entity ở mục 6 có:

~~~java
@Version
@Column("version")
private Long version;
~~~

Khi tạo entity mới, `version == null`. Spring Data có thể dùng trạng thái version để xác định đây là entity mới, dù `DeviceKey` đã có đầy đủ UUID. Khi lần lưu đầu thành công, version được quản lý theo cơ chế optimistic locking của Spring Data Cassandra.

Điểm được:

- Phân biệt rõ entity mới/đã lưu trong nhiều tình huống.
- Hỗ trợ tránh lost update khi hai writer cùng sửa cùng entity.
- Có thể kết hợp với auditing để điền created fields đúng lần tạo.

Đánh đổi:

- Cassandra optimistic locking dùng **lightweight transactions (LWT)** để kiểm tra điều kiện `IF NOT EXISTS` hoặc version khi update/delete.
- LWT có chi phí đồng thuận và latency cao hơn write thông thường.
- Có thể gặp optimistic locking failure khi version cũ; phải xử lý xung đột có chủ đích.
- Không nên đưa LWT vào đường ghi hàng trăm nghìn telemetry events/giây nếu không có lý do nghiệp vụ.
- `@Version` không biến nhiều bảng/partition thành transaction SQL hay thay thế kiểm soát consistency.

Trong bài này, bảng `device_metadata_by_id` được giả định có lưu lượng sửa metadata tương đối thấp. Với time-series events ingest rất lớn, nên chọn kiến trúc khác thay vì gắn version và audit callbacks lên mọi event một cách máy móc.

## 13. Lựa chọn 2: Persistable để tự kiểm soát isNew()

Nếu không muốn dùng LWT chỉ để nhận biết “mới”, Spring Data cho phép entity implements `Persistable<ID>`. Ví dụ **rút gọn** để minh họa cơ chế:

~~~java
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;

public class PersistableDeviceMetadata
        implements Persistable<DeviceKey> {

    private DeviceKey key;

    @Transient
    private boolean newEntity;

    // Constructor cho object đã load từ Cassandra cần newEntity=false.
    protected PersistableDeviceMetadata() {
        this.newEntity = false;
    }

    // Factory dành riêng cho lần tạo mới.
    public static PersistableDeviceMetadata create(DeviceKey key) {
        PersistableDeviceMetadata entity =
            new PersistableDeviceMetadata();
        entity.key = key;
        entity.newEntity = true;
        return entity;
    }

    @Override
    public DeviceKey getId() {
        return key;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    // Các field/mapping/audit annotations khác cần khai báo thêm.
    // Sau khi save thành công cần chuyển trạng thái newEntity=false
    // trước khi sử dụng lại object cho một lần update.
}
~~~

Đây **không phải một entity hoàn chỉnh để copy nguyên vào production**: nó chưa khai báo `@Table`, `@PrimaryKey`, các cột và bốn field audit. Nó chỉ cho thấy nguyên tắc xác định trạng thái mới.

Các điều kiện phải bảo đảm:

- Entity mới do factory tạo có `isNew() == true`.
- Entity đọc từ Cassandra có `isNew() == false`.
- Sau khi save thành công, nếu sử dụng lại object, phải cập nhật trạng thái isNew phù hợp.
- `newEntity` cần `@Transient` để không ghi vào Cassandra.
- Nếu đang dùng immutable entity, có thể dùng callback/factory hoặc bản sao với trạng thái đúng.
- `Persistable` **không tự cung cấp chống xung đột khi ghi đồng thời**; nếu cần optimistic locking, phải thiết kế riêng.

Với nhiều nhóm, `@Version` là lựa chọn dễ kiểm soát hơn cho bảng metadata ít write; `Persistable` phù hợp khi đã có quy ước lifecycle chặt chẽ và test đầy đủ.

## 14. Insert lần đầu: created và modified fields được điền thế nào?

Giả sử auditing bật với `modifyOnCreate = true`, entity mới được nhận diện đúng, và `AuditorAware` trả actor `user:operator-42`.

Ví dụ trình tự mong đợi:

~~~text
Before save:
  key         = (tenant, device)
  displayName = "Kho A"
  version     = null
  createdAt   = null
  createdBy   = null
  modifiedAt  = null
  modifiedBy  = null

Spring auditing on new entity:
  createdAt   = now
  createdBy   = user:operator-42
  modifiedAt  = now
  modifiedBy  = user:operator-42

Sau khi lưu thành công:
  version     = phiên bản được Spring Data quản lý
~~~

Nếu cấu hình `modifyOnCreate = false` thì modified fields có thể để trống lúc tạo theo quy tắc auditing.

**Đừng dựa vào hard-code “version bắt đầu bằng 0 hay 1”** trong logic nghiệp vụ khi chưa kiểm chứng implementation/version; nên kiểm tra non-null và tăng phù hợp sau các lần update trong integration tests.

### Save ở Cassandra không đơn thuần là INSERT kiểu RDBMS

Cassandra có upsert semantics cho nhiều câu `INSERT/UPDATE`. Nếu dùng optimistic locking, Spring Data có thể dùng điều kiện LWT để thực thi việc tạo khi row chưa tồn tại. Nếu không dùng version/điều kiện, ghi vào một key cũ có thể cập nhật row thay vì tạo một bản ghi mới tách biệt.

**Không suy rằng `@CreatedDate` tự làm Cassandra từ chối ghi đè row đã tồn tại.** Audit metadata mô tả tác nhân/thời điểm; ràng buộc tạo mới, version và kiểm tra sự tồn tại là những yêu cầu riêng.

## 15. Update entity: giữ nguyên created, đổi modified

Repository:

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceMetadataRepository
        extends CassandraRepository<DeviceMetadata, DeviceKey> {
}
~~~

Service minh họa:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class DeviceMetadataService {
    private final DeviceMetadataRepository repository;

    public DeviceMetadataService(DeviceMetadataRepository repository) {
        this.repository = repository;
    }

    public DeviceMetadata register(
            UUID tenantId, UUID deviceId, String name) {
        DeviceMetadata fresh = new DeviceMetadata(
            new DeviceKey(tenantId, deviceId), name);
        return repository.save(fresh);
    }

    public DeviceMetadata rename(DeviceKey key, String newName) {
        DeviceMetadata current = repository.findById(key)
            .orElseThrow(() ->
                new IllegalArgumentException("Không tìm thấy thiết bị"));
        current.setDisplayName(newName);
        return repository.save(current);
    }
}
~~~

Với đường update entity hợp lệ và version được quản lý đúng, kỳ vọng:

~~~text
createdAt  -> giữ nguyên
createdBy  -> giữ nguyên
modifiedAt -> đổi theo time provider
modifiedBy -> đổi theo AuditorAware hiện tại
version    -> tiến theo optimistic locking
~~~

Lưu ý khi nghiệp vụ yêu cầu “không sửa nếu không có gì đổi”: gọi `save` lại dù tên không thay đổi vẫn có thể kích hoạt đường modified auditing. Service cần so dữ liệu trước khi quyết định ghi, hoặc chốt rằng save/no-op vẫn là một sự kiện sửa được ghi nhận.

Trong hệ phân tán, hai writer cùng đọc một version rồi đổi tên khác nhau có thể dẫn đến optimistic locking conflict. Hãy trả lỗi nghiệp vụ thích hợp hoặc yêu cầu client tải lại, không retry vô hạn.

## 16. Partial update qua Query + Update có thể bỏ qua auditing callback

Để cập nhật **chỉ một field** mà không ghi lại entity:

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import org.springframework.data.cassandra.core.query.Update;

public void renameDirectly(
        CassandraTemplate template,
        UUID tenantId, UUID deviceId, String newName) {

    Query query = Query.query(
        Criteria.where("tenant_id").is(tenantId)
            .and("device_id").is(deviceId));

    Update update = Update.update("display_name", newName);

    template.update(query, update, DeviceMetadata.class);
}
~~~

Cách này tạo một update dựa trên `Query`/`Update` chứ không nhất thiết đi qua entity auditing callback. **Không được mặc định** `modified_at` và `modified_by` được gắn tự động.

Nếu đường ghi này là yêu cầu nghiệp vụ, hãy đặt audit fields một cách tường minh, dùng cùng nguồn thời gian/actor đáng tin cậy:

~~~java
import java.time.Instant;

Update update = Update.update("display_name", newName)
    .set("modified_at", Instant.now(clock))
    .set("modified_by", actorId);

template.update(query, update, DeviceMetadata.class);
~~~

Hai điều cần cân nhắc:

1. Với bảng có `@Version`, đường query update trực tiếp có thể **bỏ qua cơ chế optimistic locking** của entity, gây lost update hoặc khiến version không thay đổi theo kỳ vọng. Không trộn nó với `repository.save` mà không có chính sách concurrency nhất quán.
2. Cassandra `UPDATE` thông thường có thể mang semantics **upsert**. Nếu cần bảo đảm row đã tồn tại, phải dùng cơ chế điều kiện như `IF EXISTS` hoặc điều kiện theo version khi có yêu cầu, hiểu chi phí LWT.

Để giữ nguyên created fields, **không** đưa `created_at`/`created_by` vào mutation patch. Hãy kiểm tra câu CQL thực tế và tác động đến các cột khác.

## 17. CqlSession, CqlTemplate và @Query UPDATE không chạy auditing Spring Data

Một CQL tường minh:

~~~sql
UPDATE telemetry.device_metadata_by_id
SET firmware = '1.2.4'
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222;
~~~

Nếu thực thi qua `CqlSession.execute(...)`, `CqlTemplate.execute(...)`, `cqlsh` hoặc một method repository `@Query` chứa DML, server chỉ thấy CQL. Nó không biết `@LastModifiedDate` hoặc `@LastModifiedBy` trên Java class.

Một câu cập nhật có audit fields chủ đích:

~~~sql
UPDATE telemetry.device_metadata_by_id
SET firmware = ?,
    modified_at = ?,
    modified_by = ?
WHERE tenant_id = ?
  AND device_id = ?;
~~~

Bind parameters thay vì nối actor hoặc tên device từ request vào chuỗi CQL. Nguồn actor/time phải được tái sử dụng nhất quán với auditing ở luồng entity.

**Không gọi DML trực tiếp là “đã được audit” chỉ vì code chạy trong Spring Boot.** Cần integration test trên tất cả writer chính: REST service, event consumer, scheduled job, migration/maintenance và batch.

## 18. Auditing và version không thay thế hệ thống lưu lịch sử thay đổi

Giả sử bản ghi đã được sửa ba lần:

~~~text
08:00  operator-42 tạo device
08:30  operator-42 đổi display_name
09:15  firmware-sync đổi firmware
10:00  operator-17 đổi display_name
~~~

Sau cùng, bốn field audit chỉ có thể cho biết:

~~~text
created_by    = operator-42
created_at    = 08:00
modified_by   = operator-17
modified_at   = 10:00
~~~

Chúng **không lưu lại** hai lần sửa lúc 08:30 và 09:15. Nếu có yêu cầu truy vết đầy đủ vì vận hành, tuân thủ hoặc bảo mật, cần mô hình append-only/audit event ngoài bảng metadata.

Ví dụ bảng read model audit theo thiết bị/ngày:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.device_audit_by_day (
    tenant_id       uuid,
    device_id       uuid,
    audit_day       date,
    occurred_at     timestamp,
    audit_event_id  uuid,
    actor_id        text,
    operation       text,
    correlation_id  text,
    detail          text,
    PRIMARY KEY (
        (tenant_id, device_id, audit_day),
        occurred_at, audit_event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC, audit_event_id ASC
);
~~~

Khi đọc:

~~~sql
SELECT occurred_at, audit_event_id, actor_id, operation
FROM telemetry.device_audit_by_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND audit_day = '2026-11-25'
LIMIT 50;
~~~

Audit history cần event ID ổn định, policy chống trùng/replay, quyền đọc, retention, masking thông tin bí mật và tính nhất quán giữa metadata row với event log. Hai bảng Cassandra được ghi độc lập **không tự thành transaction ACID đa partition**.

Nếu cần audit không thể sửa/xóa, bản thân Cassandra table bình thường không tạo ra tính bất biến ở mức pháp lý. Phải bổ sung cơ chế kiểm soát ghi, lưu trữ bất biến/ký số hoặc hệ thống audit chuyên dụng theo yêu cầu thực tế.

## 19. Dữ liệu phân tán: createdAt không phải thời gian tuyệt đối server

Trong Cassandra, nhiều instance ứng dụng có thể ghi đồng thời vào cùng partition. `DateTimeProvider` thường lấy thời gian từ **clock của ứng dụng**, không nhất thiết từ đồng hồ của server Cassandra.

Hãy phân biệt:

- `created_at` biểu thị thời điểm ứng dụng coi entity là mới và điền audit.
- `modified_at` biểu thị thời điểm ứng dụng lưu entity qua auditing.
- Cassandra mutation timestamp quyết định hòa giải cell giữa replicas theo quy tắc của engine.
- `event_time` của cảm biến có thể là thời điểm thiết bị ghi nhận event, không cùng thời điểm HTTP request.

Vì vậy, một write sau theo wall-clock của API **không luôn thắng** một write khác nếu client timestamps/replica conflict được quản lý khác. `@Version` giúp ngăn update dựa trên version cũ trong trường hợp được hỗ trợ, nhưng không thay thế cơ chế xử lý một chuỗi sự kiện nghiệp vụ có thứ tự toàn cục.

Trong nhiều instance, đồng bộ NTP, policy timezone UTC và loại timestamp cần được chuẩn hóa. Không dùng `LocalDateTime.now()` từ timezone máy chủ để lắp vào Cassandra timestamp rồi coi tất cả service hiểu cùng một múi giờ.

## 20. Dùng Instant và kiểm thử độ chính xác thời gian

CQL `timestamp` thường có độ phân giải **millisecond**. Java `Instant` hỗ trợ nanosecond. Khi test, đừng so sánh trước/ sau lưu mà không xét chuyển đổi.

Ví dụ canonicalize:

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant now = Instant.now(clock)
    .truncatedTo(ChronoUnit.MILLIS);
~~~

Một `DateTimeProvider` tùy chỉnh cho auditing:

~~~java
@Bean("auditTime")
DateTimeProvider auditTime(Clock clock) {
    return () -> Optional.of(
        Instant.now(clock).truncatedTo(ChronoUnit.MILLIS));
}
~~~

Dùng UTC cho múi giờ trình bày, và `Instant` cho mốc tuyệt đối. Nếu cần hiển thị theo múi giờ người dùng, chuyển đổi ở tầng API/frontend, không ép `Instant` thành local time rồi lưu lại.

Trong test, so `Instant` đã round-trip từ Cassandra với giá trị được chuẩn hóa, hoặc dùng một `Clock.fixed` ở millisecond. Tránh `Thread.sleep(10)` chỉ để mong `modifiedAt > createdAt`: kết quả có thể vẫn bằng nhau do độ phân giải hoặc thực thi nhanh.

## 21. Auditing và TTL/tombstone

Một hệ IoT có thể đặt TTL cho dữ liệu telemetry, nhưng bảng metadata thiết bị/audit thường có yêu cầu retention khác.

Cassandra TTL hết hạn khiến giá trị không còn hiển thị và có thể sinh tombstone. Nếu audit fields có TTL:

- `created_at`/`created_by` có thể hết hạn trước khi bản ghi metadata kết thúc vòng đời.
- Một lần update khác có thể làm thay đổi TTL của những cell được ghi lại.
- `modified_at`/`modified_by` có thể mất đi không đồng thời với các field khác nếu TTL khác.
- Tombstone và compaction ảnh hưởng dung lượng/hiệu năng; không thể suy rằng dữ liệu đã bị xóa vật lý ngay thời điểm TTL kết thúc.

Do vậy, cần **chính sách TTL riêng** cho metadata, telemetry events và audit event log. Nếu audit history dùng retention lâu dài, không copy TTL ngắn của bảng sự kiện cảm biến sang bảng audit.

Các trường audit không tự làm quá trình delete hoặc compaction trở nên có thể truy vết đầy đủ. Nếu cần ghi nhận ai xóa entity, hãy tạo **deletion audit event** trước/đồng thời theo workflow đáng tin cậy thay vì chỉ dựa vào bốn field của row sắp bị xóa.

## 22. Reactive auditing dùng hạ tầng khác imperative

Nếu ứng dụng dùng `ReactiveCassandraRepository` hoặc `ReactiveCassandraTemplate`, bật cấu hình tương ứng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.config.EnableReactiveCassandraAuditing;

@Configuration
@EnableReactiveCassandraAuditing(
    auditorAwareRef = "reactiveAuditor",
    modifyOnCreate = true)
public class ReactiveAuditConfiguration {
}
~~~

Auditor provider reactive:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

@Configuration
public class ReactiveActorConfiguration {

    @Bean("reactiveAuditor")
    public ReactiveAuditorAware<String> reactiveAuditor() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication())
            .filter(Authentication::isAuthenticated)
            .filter(auth ->
                !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .filter(name -> !name.isBlank());
    }
}
~~~

**Không dùng `SecurityContextHolder` ThreadLocal như nguồn actor chính cho luồng reactive** nếu identity thực tế nằm trong Reactor context. Khi dùng scheduler, operator đổi thread hoặc message consumer, security context propagation phải được thiết kế/kiểm thử riêng.

Đừng bật cả imperative/reactive auditing và khai báo hai provider cùng tên mà không hiểu repository đang chạy hạ tầng nào. Chọn đúng annotation và `AuditorAware`/`ReactiveAuditorAware` theo kiểu ứng dụng.

## 23. Kiểm thử integration: tạo mới, lưu lại, sửa và đọc lại

Để kiểm chứng Spring Data và Cassandra thật, dùng test keyspace cô lập hoặc Testcontainers cùng migration DDL, Spring context có cấu hình auditing và auditor provider kiểm soát được. Ví dụ test mô tả contract:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DeviceMetadataAuditingIT {

    @Autowired
    DeviceMetadataRepository repository;

    @Test
    void createAndUpdatePreserveCreatedFields() {
        DeviceKey key = new DeviceKey(
            UUID.randomUUID(), UUID.randomUUID());

        DeviceMetadata created = repository.save(
            new DeviceMetadata(key, "Kho A"));

        assertThat(created.getCreatedAt()).isNotNull();
        assertThat(created.getModifiedAt()).isNotNull();
        assertThat(created.getCreatedBy()).isNotBlank();
        assertThat(created.getModifiedBy()).isNotBlank();
        assertThat(created.getVersion()).isNotNull();

        DeviceMetadata reloaded =
            repository.findById(key).orElseThrow();

        var originalCreatedAt = reloaded.getCreatedAt();
        var originalCreatedBy = reloaded.getCreatedBy();

        reloaded.setDisplayName("Kho B");
        DeviceMetadata updated = repository.save(reloaded);

        assertThat(updated.getCreatedAt())
            .isEqualTo(originalCreatedAt);
        assertThat(updated.getCreatedBy())
            .isEqualTo(originalCreatedBy);
        assertThat(updated.getModifiedAt()).isNotNull();
        assertThat(updated.getModifiedBy()).isNotBlank();
        assertThat(updated.getDisplayName()).isEqualTo("Kho B");
    }
}
~~~

**Tiền đề của ví dụ:** test đã đăng ký một `AuditorAware<String>` trả identity xác định (hoặc mock context bảo mật), migration đã tạo `version bigint`, entity được Spring Data nhận là mới nhờ `@Version`, Cassandra thực tế đang chạy. Nếu actor provider trả empty, assertion `isNotBlank()` sẽ không đạt — đây là tín hiệu kiểm tra cấu hình, không phải lý do tự gán một username giả trong production.

### Kiểm tra actor thay đổi giữa hai lần save

Một test đầy đủ hơn cần:

1. Save lần đầu dưới actor `user:creator`.
2. Lấy entity từ Cassandra, thay đổi displayName.
3. Save lại dưới actor `user:editor`.
4. Đọc lại; kỳ vọng `createdBy` vẫn là creator và `modifiedBy` là editor.
5. Kiểm tra `createdAt` giữ nguyên; `modifiedAt` đi theo provider thời gian.
6. Đảm bảo version tiến lên và không có write khác chen vào khiến test thất bại vì concurrency.

Không cần khẳng định `modifiedAt > createdAt` nếu hai thao tác cùng millisecond. Có thể cấp hai thời điểm cố định khác nhau qua DateTimeProvider để chứng minh thay đổi deterministic.

## 24. Kiểm thử đường ghi bỏ qua entity callbacks

Bên cạnh test repository, cần test câu update CQL trực tiếp:

~~~sql
UPDATE telemetry.device_metadata_by_id
SET display_name = 'Kho C'
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222;
~~~

Sau câu này, không được mặc định `modified_by` và `modified_at` đã được Spring tự cập nhật.

Một test quan trọng:

- Seed metadata qua repository, lưu lại bộ audit fields.
- Gọi `CqlSession`/`CqlTemplate` hoặc `CassandraTemplate.update(Query, Update, ...)`.
- Đọc lại metadata và kiểm tra field nào thay đổi thực tế.
- Nếu policy yêu cầu audit tất cả thay đổi, thay code CQL để ghi modified fields có chủ đích rồi kiểm thử lại.
- Khi entity có `@Version`, kiểm tra update ngoài repository có bypass version không và quyết định có cấm đường đó hay không.

Test này giúp phát hiện lỗi nghiêm trọng: service CRUD có audit đầy đủ nhưng worker/background job lại ghi metadata trực tiếp, dẫn đến `modifiedBy` sai mặc dù giá trị firmware đã đổi.

## 25. Kiểm thử optimistic locking và đồng thời

Một kịch bản:

~~~text
Actor A đọc row version V.
Actor B đọc cùng row version V.
Actor A sửa display_name rồi save, thành công -> version V+1.
Actor B sửa firmware trên object version V và save.
~~~

Khi Spring Data sử dụng `@Version`, lần lưu của B có thể bị từ chối do version không còn khớp. Test nên chấp nhận/bắt loại optimistic locking exception phù hợp phiên bản, xác minh row cuối cùng và đảm bảo không âm thầm ghi đè audit metadata của A.

Về mặt nghiệp vụ:

- Nếu B retry bằng cách đọc lại rồi áp thay đổi, actor B có thể trở thành `modifiedBy` mới nhất; đó là hệ quả hợp lý.
- Nếu B retry lại **entity cũ** không điều chỉnh version, có nguy cơ vòng lặp lỗi hoặc lost update nếu đường ghi bypass LWT.
- Nếu mutation từ worker không qua repository, version và auditing có thể không tăng, phá vỡ giả định của các client khác.

Vì vậy, đừng trộn hai kiểu writer mà không quy định chính sách chung. Bốn audit annotations không tự giải quyết concurrency; optimistic locking là một cơ chế bổ sung có đánh đổi hiệu năng.

## 26. Chống giả mạo và bảo vệ audit metadata

Các trường `createdBy` và `modifiedBy` có thể trở thành dữ liệu nhạy cảm trong hệ thống nhiều tenant. Những nguyên tắc tối thiểu:

- Actor phải đến từ danh tính được xác thực/ủy quyền hoặc service identity tin cậy.
- Không nhận `createdBy`, `createdAt`, `modifiedBy` từ DTO công khai như field do client tùy ý cung cấp.
- Kiểm tra caller có quyền thao tác `tenant_id/device_id`; một repository query theo partition key không thay thế authorization.
- Không lưu access token, JWT nguyên văn, password, email cá nhân không cần thiết hoặc secret vào field actor.
- Dùng ID ổn định, có thể resolve thông tin hiển thị từ hệ thống identity nếu cần.
- Có chính sách redaction, retention và hạn chế quyền đọc audit history.
- Nếu yêu cầu pháp lý đòi hỏi audit chống sửa/xóa, cần lưu trữ/cơ chế bất biến, ký số hoặc log tập trung được thiết kế cho mục tiêu đó.

**Không dùng audit field như một authorization rule duy nhất.** Việc `createdBy="user:42"` không tự có nghĩa user 42 còn quyền chỉnh sửa bản ghi sau khi vai trò hoặc quyền tenant thay đổi.

## 27. Troubleshooting: tại sao auditing không được điền?

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Cả bốn field đều null | Chưa bật `@EnableCassandraAuditing`, entity không đi qua callbacks, hoặc mapping sai | Cấu hình Spring, đường ghi và DDL |
| `createdAt` null, `modifiedAt` có giá trị | Entity có ID sẵn nhưng Spring Data coi là không mới | Kiểm tra `@Version` hoặc `Persistable.isNew()` |
| `createdBy`/`modifiedBy` null | `AuditorAware` trả empty hoặc không được đăng ký/chọn | SecurityContext, bean name, job identity |
| Modified fields được điền ngay khi insert | `modifyOnCreate=true` là mặc định | Đổi policy nếu muốn chỉ có sau update |
| CQL update thành công nhưng `modifiedAt` cũ | Query/Update hoặc raw CQL không kích hoạt entity auditing | Ghi modified fields tường minh hoặc thống nhất đường ghi |
| Audit timestamp lệch nhau giữa instance | Clock/timezone hoặc precision không thống nhất | UTC, NTP, `Clock` và millisecond |
| Save bị optimistic locking failure | Object có version cũ hoặc row bị sửa đồng thời | Retry có chủ đích sau khi reload, đo LWT |
| CQL trực tiếp sửa row nhưng version không tăng | Bypass entity optimistic locking | Cấm/mô hình lại writer hoặc dùng điều kiện rõ |
| `@CreatedDate` bị thay mỗi lần save | Entity bị coi là mới nhiều lần hoặc code tự set field | Kiểm tra `isNew()`, Persistable lifecycle |
| Test Cassandra một node xanh nhưng production sai | Chưa test concurrency/CL, job khác ghi ngoài callback | Integration test đa writer và test phân tán |
| Modified audit mất sau TTL | Cột audit có TTL/ngữ nghĩa ghi lại khác dự định | Kiểm tra TTL, mutation và compaction |
| Tên actor không chính xác với JWT | Dùng username/display name thay stable ID | Chính sách mapping identity/claim |

Khi debug, log entity ID, operation, actor type, policy version và correlation ID nếu được phép, **không log payload nhạy cảm**. Nếu nghi mapping lỗi, đối chiếu `DESCRIBE TABLE`, `system_schema` và CQL thực tế thay vì chỉ nhìn Java annotation.

## 28. Ma trận lựa chọn thiết kế auditing

| Tình huống | Cách làm gợi ý | Điều không nên giả định |
| --- | --- | --- |
| CRUD metadata thiết bị lưu lượng thấp | Entity auditing + `@Version` + repository | `@Version` không có chi phí |
| Entity có ID tự gán, không muốn LWT | `Persistable`/`isNew` với lifecycle được kiểm thử | Cờ `isNew` tự cập nhật sau save |
| Chỉ cần thời gian tạo/sửa | `@CreatedDate` và `@LastModifiedDate` | Bắt buộc có `AuditorAware` |
| Cần actor của user HTTP | `AuditorAware<String>` dựa vào security principal | Header client là identity tin cậy |
| Reactive WebFlux | `@EnableReactiveCassandraAuditing` + `ReactiveAuditorAware` | ThreadLocal luôn có actor |
| Scheduled job/message consumer | Service identity và correlation ID rõ ràng | `SecurityContextHolder` luôn có user |
| Partial update bằng `Query + Update` | Ghi modified fields tường minh, xem concurrency | Entity callback tự chạy trên query update |
| Nhiều dịch vụ ghi cùng bảng | Chuẩn hóa audit policy và version/actor/time ở mọi writer | Chỉ một Spring service quyết định mọi mutation |
| Cần lịch sử mọi lần thay đổi | Audit event stream/table chuyên dụng | Bốn field latest audit là lịch sử bất biến |
| Cần audit compliance không thể xóa | Store/controls bất biến, authorization, retention, integrity | Cassandra table thường là append-only tuyệt đối |

## 29. Quy trình triển khai auditing vào một dự án

1. **Chốt nghiệp vụ:** tạo/sửa nghĩa là gì, no-op có tính là sửa không, actor nào được công nhận, có cần audit history không.
2. **Thiết kế schema:** bốn cột audit regular, kiểu `timestamp/text`; xác định TTL và retention.
3. **Chọn chiến lược nhận biết entity mới:** `@Version`/LWT hoặc `Persistable` với lifecycle test.
4. **Bật auditing:** `@EnableCassandraAuditing` hoặc reactive variant; chọn đúng bean auditor.
5. **Chuẩn hóa actor:** lấy từ security principal hoặc service identity tin cậy; bảo vệ tenant authorization.
6. **Chuẩn hóa thời gian:** UTC, `Instant`, `DateTimeProvider`/`Clock` và chính sách độ phân giải.
7. **Kiểm kê đường ghi:** repository, template, CQL, batch, consumer, migration; bổ sung explicit audit ở nơi callback không chạy.
8. **Kiểm thử tích hợp:** insert, update, actor thay đổi, empty principal, no-op, concurrency và time precision.
9. **Kiểm thử dữ liệu phân tán:** CL, multi-writer, optimistic locking và các request retry.
10. **Quan sát:** tỷ lệ thiếu audit fields, LWT latency, failed updates, principal resolution errors và write p95/p99.
11. **Triển khai theo đợt:** migration schema trước, canary, so sánh dữ liệu audit, kế hoạch backfill cho row cũ.
12. **Bảo vệ lịch sử:** nếu cần audit bất biến, lập pipeline append-only/reconciliation riêng.

### Dữ liệu cũ chưa có audit fields

Sau khi thêm các cột audit, dữ liệu đã tồn tại không tự có `created_at`/`created_by` đúng lịch sử. Không nên backfill bằng `now()` rồi gọi đó là “thời điểm tạo thực”.

Phải quy định rõ: `unknown`/`legacy-import`, thời điểm lấy từ nguồn có chứng cứ, hoặc trường `migrated_at` riêng. Nếu chỉ có ngày nhập migration, không thể suy ra actor tạo lịch sử.

## 30. Bài tập vận dụng

### Bài A — Bốn annotation

Đối với một thiết bị mới do `user:alice` đăng ký và sau đó `service:firmware-sync` sửa firmware, xác định kỳ vọng cho `createdAt`, `modifiedAt`, `createdBy` và `modifiedBy` trước/sau thao tác với `modifyOnCreate=true`.

**Gợi ý:** created fields giữ actor/time ban đầu; modified fields phản ánh lần ghi cuối.

### Bài B — Vì sao CreatedDate null?

Một entity có `@PrimaryKey` được gán trước lần save, không có `@Version`, không implements `Persistable`. Sau save, `modifiedAt` khác null còn `createdAt` null. Giải thích chiến lược `isNew()` và đề xuất hai cách sửa.

### Bài C — Đánh đổi LWT

Metadata thiết bị có vài lần sửa mỗi ngày; event telemetry có hàng chục nghìn writes/giây. Chọn nơi nên dùng `@Version` và nơi nên cân nhắc giải pháp khác. Nêu chi phí đồng thuận, concurrency và rủi ro lost update.

### Bài D — AuditorAware an toàn

Viết một `AuditorAware<String>` lấy stable user ID từ Spring Security, loại anonymous, trả Optional.empty khi không có principal. Thiết kế identity cho scheduled job mà không nhận actor tùy ý từ HTTP header.

### Bài E — DateTimeProvider

Thiết kế `Clock.fixed` cho test; thực hiện create và update ở hai thời điểm kiểm soát, kiểm tra createdAt bất biến và modifiedAt đổi. Vì sao không dùng `Thread.sleep` để chứng minh tính đúng?

### Bài F — Query Update và callback

Một service dùng `CassandraTemplate.update(Query, Update, DeviceMetadata.class)` đổi tên. Hãy giải thích vì sao không được hứa auditing tự chạy và viết cách cập nhật `modified_at/modified_by` một cách có chủ đích. Nếu entity có `@Version`, phải xét thêm điều gì?

### Bài G — Reactive auditing

Ứng dụng dùng WebFlux và ReactiveCassandraRepository. Vì sao `SecurityContextHolder` ThreadLocal không phải nguồn identity đáng tin cho reactive chain? Chọn annotation/provider thay thế và mô tả cách test context propagation.

### Bài H — Auditing so với audit log

Một bản ghi đổi firmware năm lần; bốn audit fields cho phép trả lời được và không trả lời được câu hỏi nào? Thiết kế bảng audit events theo tenant/device/day với event ID để lưu lịch sử, nêu thách thức dual-write và replay.

### Bài I — Timestamp và consistency

Hai service có đồng hồ khác nhau vài giây cùng ghi metadata. `modifiedAt` có bảo đảm tương ứng write timestamp Cassandra mới nhất không? Đề xuất chính sách Clock/UTC, optimistic locking và monitoring phù hợp.

### Bài J — Backfill dữ liệu cũ

Một triệu device rows được tạo trước ngày bổ sung auditing, không có lịch sử người tạo. Viết chính sách backfill không bịa `createdBy`/`createdAt`, xác định trường nào để null/unknown và cách ghi provenance của migration.

**Tiêu chí đạt:** người học phân biệt chính xác bốn annotation, kích hoạt auditing, xử lý `AuditorAware`, hiểu lỗi `isNew()` với ID Cassandra, nhận biết callback không bao phủ mọi CQL, đồng thời thiết kế test và policy cho multi-tenant/multi-writer.

## 31. Checklist trước khi đưa auditing lên production

- [ ] Đã phân biệt audit metadata bốn field với audit history bất biến?
- [ ] `@EnableCassandraAuditing`/reactive variant được bật đúng kiểu ứng dụng?
- [ ] Bốn annotation thuộc Spring Data và mapping CQL đúng tên cột?
- [ ] Entity ID gán trước có chiến lược `isNew()` đúng: `@Version` hay `Persistable`?
- [ ] Đã đo chi phí LWT nếu dùng `@Version` trên đường ghi nóng?
- [ ] `modifyOnCreate` đúng với hợp đồng nghiệp vụ?
- [ ] Bean `AuditorAware` có stable actor ID và loại anonymous?
- [ ] Scheduled job/worker có identity đáng tin, không dựa vào header client?
- [ ] `DateTimeProvider`/`Clock` thống nhất UTC, precision và test được?
- [ ] Mọi luồng repository/template/raw CQL/batch/consumer đều có policy audit?
- [ ] Direct CQL hoặc `Query + Update` không bị hiểu nhầm tự chạy callbacks?
- [ ] Nếu dùng version, mọi writer đều tuân theo chiến lược concurrency?
- [ ] `createdAt`/`createdBy` không bị thay ngoài ý muốn khi update?
- [ ] Có test insert/update, dữ liệu null, actor đổi, no-op và retry?
- [ ] Có kiểm tra tenant authorization, bí mật dữ liệu và quyền đọc audit fields?
- [ ] Có chính sách TTL/retention riêng cho metadata/audit history?
- [ ] Dữ liệu cũ được đánh dấu provenance, không bịa thời điểm/actor tạo?
- [ ] Có metrics về audit completeness, lỗi actor resolution, LWT và latency?
- [ ] Nếu cần lịch sử đầy đủ, đã có event log/reconciliation và cơ chế integrity?

## Tài liệu tham khảo

- [Spring Data Cassandra — Auditing Configuration](https://docs.spring.io/spring-data/cassandra/reference/cassandra/auditing.html): `@EnableCassandraAuditing`, `AuditorAware` và reactive auditing.
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/cassandra/reference/data-commons/4.2/auditing.html): bốn annotation, `DateTimeProvider`, `AuditorAware` và `ReactiveAuditorAware`.
- [Spring Data Cassandra — EnableCassandraAuditing Javadoc](https://docs.spring.io/spring-data/cassandra/docs/4.5.x/api/org/springframework/data/cassandra/config/EnableCassandraAuditing.html): `auditorAwareRef`, `dateTimeProviderRef`, `setDates` và `modifyOnCreate`.
- [Spring Data Cassandra — Lifecycle Events and Callbacks](https://docs.spring.io/spring-data/cassandra/reference/cassandra/events.html): `AuditingEntityCallback` và pha `BeforeConvert`.
- [Spring Data Cassandra — Entity State Detection](https://docs.spring.io/spring-data/cassandra/reference/repositories/core-concepts.html): `@Version`, `Persistable`, ID inspection và lưu ý riêng của Cassandra.
- [Spring Data Cassandra — Persisting Entities](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): save, update, optimistic locking với LWT.
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): primary key và table schema.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): upsert, conditional writes, timestamp và TTL.
