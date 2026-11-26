# deleteById, delete và điều kiện khóa cần thiết

## Mục tiêu học tập

Trong Spring Data Cassandra, `CassandraRepository` cung cấp các thao tác xóa quen thuộc như `deleteById(id)` và `delete(entity)`. Tên phương thức nhìn giống repository của cơ sở dữ liệu quan hệ, nhưng hành vi lưu trữ bên dưới vẫn tuân theo **Cassandra Query Language (CQL)**: dữ liệu được định tuyến bằng **partition key**, hàng được phân biệt bằng **clustering columns**, và thao tác xóa tạo **tombstone** thay vì nhất thiết loại bỏ byte dữ liệu ngay lập tức.

Sau bài thuộc chương **Repository** của module `SPRING_DATA_CASSANDRA`, bạn có thể:

- Phân biệt `deleteById(ID)` và `delete(T entity)`, biết khi nào nên dùng mỗi phương thức.
- Đọc khóa chính CQL để xác định các giá trị bắt buộc khi xóa đúng **một hàng**.
- Phân biệt **row delete**, **partition delete** và **column delete** ở tầng CQL.
- Biết vì sao không thể xóa tùy tiện bằng regular column và không nên dùng `ALLOW FILTERING` để “sửa” thiết kế xóa.
- Xử lý yêu cầu “chỉ xóa nếu tồn tại”, ghi đồng thời, retry và kiểm soát các hậu quả của tombstone.
- Đánh giá chi phí khi dữ liệu được nhân bản ở nhiều bảng phục vụ truy vấn và khi áp dụng paging/consistency.

## 1. Xóa trong Cassandra khác với xóa trong cơ sở dữ liệu quan hệ thế nào?

Trong nhiều hệ quản trị quan hệ, lập trình viên có thể viết câu lệnh `DELETE FROM table WHERE status = 'EXPIRED'` rồi để query planner quyết định cách tìm hàng. Cassandra ưu tiên các truy vấn có thể **xác định partition**; `DELETE` cũng phải tuân thủ quy tắc khóa của bảng.

Hai điều đặc biệt cần nhớ:

1. **Xác định đúng đối tượng bị xóa:** Cassandra dùng toàn bộ partition key để định tuyến đến các replica chịu trách nhiệm. Để xóa **một hàng CQL** trong một partition có nhiều hàng, còn cần xác định clustering key tương ứng.
2. **Xóa logic trước khi dọn dữ liệu vật lý:** thao tác xóa tạo dấu xóa (*tombstone*) để các replica có thể nhận biết giá trị/hàng đã bị xóa trong hệ phân tán. Dữ liệu không nhất thiết biến mất ngay khỏi SSTable sau khi câu lệnh trả về thành công.

```text
Ứng dụng
   |
   v
CassandraRepository.deleteById(id)
   |
   v
Spring Data mapping: id -> các cột primary key
   |
   v
CQL DELETE với điều kiện khóa cần thiết
   |
   v
CqlSession / Java Driver -> replica của partition
   |
   v
Ghi tombstone -> dọn vật lý về sau theo cơ chế Cassandra
```

Repository giúp giảm mã boilerplate, nhưng **không làm Cassandra có khóa ngoại, ON DELETE CASCADE hay giao dịch nhiều bảng kiểu RDBMS**.

## 2. Ví dụ đơn giản: deleteById với khóa chính một cột

Giả sử ứng dụng lưu cấu hình thiết bị, thường truy vấn và xóa theo mã thiết bị:

```sql
CREATE TABLE device_settings_by_id (
    device_id uuid PRIMARY KEY,
    display_name text,
    enabled boolean
);
```

Ở bảng này, `device_id` vừa là **partition key**, vừa là **toàn bộ primary key**; mỗi partition có tối đa một hàng CQL theo khóa đó.

Entity Java:

```java
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_settings_by_id")
public class DeviceSetting {

    @PrimaryKey("device_id")
    private UUID deviceId;

    @Column("display_name")
    private String displayName;

    @Column("enabled")
    private Boolean enabled;

    public UUID getDeviceId() {
        return deviceId;
    }

    // Bổ sung constructor, getter/setter khác theo quy ước dự án.
}
```

Repository:

```java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceSettingRepository
        extends CassandraRepository<DeviceSetting, UUID> {
}
```

Xóa theo ID:

```java
UUID deviceId = UUID.fromString(
        "11111111-1111-4111-8111-111111111111");

deviceSettingRepository.deleteById(deviceId);
```

Ở ví dụ này, tầng truy cập dữ liệu có đủ khóa `device_id` để định vị chính xác partition/hàng cần xóa. CQL tương ứng về mặt ý nghĩa:

```sql
DELETE FROM device_settings_by_id
WHERE device_id = 11111111-1111-4111-8111-111111111111;
```

**Điểm cần phân biệt:** `deleteById` trả về `void` theo hợp đồng repository thông dụng; lời gọi này **không trả về** số hàng đã bị xóa theo kiểu JDBC. Cassandra có thể ghi dấu xóa ngay cả khi hàng không tồn tại tại thời điểm yêu cầu. Nếu nghiệp vụ cần biết chắc “hàng đã tồn tại và được xóa bởi lần gọi này”, phải thiết kế thêm cách kiểm tra hoặc cơ chế điều kiện phù hợp.

## 3. delete(entity): nguồn khóa đến từ đối tượng

Với cùng entity `DeviceSetting`, có thể dùng:

```java
DeviceSetting setting = deviceSettingRepository
        .findById(deviceId)
        .orElseThrow();

deviceSettingRepository.delete(setting);
```

Sự khác nhau giữa hai phương thức:

| Phương thức | Đầu vào | Điều cần có | Khi nào thích hợp |
| --- | --- | --- | --- |
| `deleteById(ID id)` | Định danh của entity. | Giá trị ID đầy đủ, hợp lệ, ánh xạ được về khóa chính CQL. | API đã nhận ID, không cần tải entity chỉ để lấy ID. |
| `delete(T entity)` | Đối tượng entity. | Entity có giá trị khóa chính đầy đủ và mapping hợp lệ. | Đã có entity trong luồng nghiệp vụ, muốn xóa theo định danh của nó. |

Đối với hai phương thức, bản chất là **xóa theo identity**, không phải:

- Xóa mọi hàng có regular column trùng với một property của entity.
- So sánh tất cả các field của entity với dữ liệu đang lưu.
- Xóa theo mọi điều kiện lọc bất kỳ trong request.

Ví dụ, thay đổi `setting.enabled` từ `true` sang `false` trong một object **không** khiến `delete(setting)` chuyển thành câu lệnh “xóa tất cả thiết bị đang tắt”. Trường dùng để định vị hàng vẫn là khóa chính.

**Lưu ý về entity chưa đủ khóa:** đừng gọi `delete(entity)` với đối tượng DTO được tạo từ request nhưng thiếu ID hoặc thiếu các thành phần của khóa tổng hợp. Tùy phiên bản và cách mapping, thao tác có thể thất bại ở tầng Spring Data hoặc tạo điều kiện xóa không đáp ứng yêu cầu CQL. Hãy validate ID ở biên service.

## 4. Khóa tổng hợp: chỉ partition key chưa đủ để xóa một hàng

Xét hệ thống audit log lưu nhiều sự kiện theo tenant và ngày. API cần xóa **một sự kiện xác định**, không được xóa toàn bộ nhật ký của ngày.

```sql
CREATE TABLE audit_events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Đọc khóa:

- `(tenant_id, event_day)` là **partition key tổng hợp**. Cả hai giá trị định tuyến đến cùng partition logic.
- `occurred_at` và `event_id` là **clustering columns**. Hai cột này xác định hàng cụ thể trong partition.
- `event_type` và `payload` là **regular columns**, không thuộc primary key.

```text
Partition: (tenant=T1, day=2026-11-25)
  Row: (08:30:00, E1) -> LOGIN, ...
  Row: (08:45:00, E2) -> UPDATE_PROFILE, ...
  Row: (09:20:00, E3) -> LOGOUT, ...
```

Muốn xóa riêng hàng E2, câu CQL cần đầy đủ primary key:

```sql
DELETE FROM audit_events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-25'
  AND occurred_at = '2026-11-25T08:45:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
```

Nếu chỉ dùng:

```sql
DELETE FROM audit_events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-25';
```

thì đây là **partition delete**: xóa các hàng thuộc **toàn bộ partition tenant/ngày**, không phải riêng E2. Nó có thể là thao tác hợp lệ ở CQL nhưng hoàn toàn sai yêu cầu “xóa một sự kiện”.

### 4.1. Vì sao Spring Data cần một ID tổng hợp?

Vì bảng có khóa nhiều cột, loại ID của repository cũng cần diễn đạt được toàn bộ khóa. Một lựa chọn thường dùng là `@PrimaryKeyClass` với `@PrimaryKeyColumn`:

```java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class AuditEventKey implements Serializable {

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "event_day", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 2,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private UUID eventId;

    public AuditEventKey() {
    }

    public AuditEventKey(
            UUID tenantId, LocalDate eventDay,
            Instant occurredAt, UUID eventId) {
        this.tenantId = tenantId;
        this.eventDay = eventDay;
        this.occurredAt = occurredAt;
        this.eventId = eventId;
    }

    // Bổ sung getter/setter và equals/hashCode cho mọi thành phần khóa.
}
```

Entity:

```java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("audit_events_by_tenant_day")
public class AuditEvent {

    @PrimaryKey
    private AuditEventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    public AuditEventKey getKey() {
        return key;
    }

    // Bổ sung constructor/getter/setter theo quy ước dự án.
}
```

Repository khai báo ID theo đúng lớp khóa:

```java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface AuditEventRepository
        extends CassandraRepository<AuditEvent, AuditEventKey> {
}
```

Xóa một hàng:

```java
AuditEventKey key = new AuditEventKey(
        UUID.fromString("11111111-1111-4111-8111-111111111111"),
        LocalDate.parse("2026-11-25"),
        Instant.parse("2026-11-25T08:45:00Z"),
        UUID.fromString("22222222-2222-4222-8222-222222222222")
);

auditEventRepository.deleteById(key);
```

Ở đây giả định đã có `auditEventRepository` được inject và các import kiểu Java. Ví dụ khóa là **khung mapping cần bổ sung các accessor, equality methods** để dùng như class thực tế; trọng tâm của bài là bốn thành phần khóa được cung cấp đầy đủ.

### 4.2. Nếu API chỉ có event_id thì sao?

Với bảng này, `event_id` là clustering column cuối cùng, **không phải** partition key. Biết `event_id` đơn lẻ không đủ để định tuyến đến partition/hàng, ngay cả khi UUID có vẻ duy nhất toàn hệ thống.

Các lựa chọn thiết kế:

1. Yêu cầu client/API cung cấp `tenant_id`, `event_day`, `occurred_at` cùng `event_id`.
2. Lưu metadata tra cứu từ `event_id` đến khóa đầy đủ trong một bảng phụ thiết kế riêng nếu đây là nhu cầu thường xuyên.
3. Thiết kế lại bảng phục vụ truy cập/xóa theo `event_id` khi đây là đường truy cập chính, đồng thời cân nhắc các truy vấn khác.

Không được chỉ thay signature repository thành `deleteById(UUID eventId)` khi ID thực của entity là `AuditEventKey`. Không có phép màu Spring Data nào tự tra mọi partition để tìm một clustering column.

## 5. Row delete, partition delete và column delete

Ba trường hợp có ý nghĩa vận hành khác nhau:

| Loại xóa | Câu CQL minh họa | Phạm vi bị ảnh hưởng |
| --- | --- | --- |
| **Row delete** | `DELETE FROM ... WHERE tenant_id=? AND event_day=? AND occurred_at=? AND event_id=?` | Một hàng có khóa chính đầy đủ. |
| **Partition delete** | `DELETE FROM ... WHERE tenant_id=? AND event_day=?` | Mọi hàng trong một partition logic. |
| **Column delete** | `DELETE payload FROM ... WHERE tenant_id=? AND event_day=? AND occurred_at=? AND event_id=?` | Xóa giá trị của cột dữ liệu được chỉ định trong hàng đó. |

Ví dụ xóa riêng `payload` của sự kiện E2 nhưng giữ khóa và `event_type`:

```sql
DELETE payload
FROM audit_events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-25'
  AND occurred_at = '2026-11-25T08:45:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
```

Không dùng column delete để xóa riêng một thành phần của primary key. Khi một giá trị thuộc khóa phải thay đổi, thường cần **ghi ở khóa mới và xóa ở khóa cũ** bằng các thao tác được điều phối phù hợp với nghiệp vụ.

### Vì sao partition delete nguy hiểm trong service?

Ví dụ, một service nhận `tenantId` và `eventDay` để “xóa một event” nhưng quên xác định `occurredAt` và `eventId`. Nếu nhà phát triển tự viết CQL:

```sql
DELETE FROM audit_events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-25';
```

thì request hợp lệ theo khóa partition có thể xóa nhiều bản ghi hơn ý định. Bởi vậy, hãy phân biệt tên API nghiệp vụ:

- `deleteOneEvent(fullKey)`: cần khóa của hàng.
- `purgeEventsOfDay(tenantId, day)`: là thao tác **quy mô partition**, cần quyền và giới hạn rõ ràng.

Không nên che một lệnh xóa cả partition sau tên phương thức hoặc endpoint gợi ý xóa đúng một bản ghi.

## 6. deleteById và delete không phải “xóa theo WHERE bất kỳ”

Một yêu cầu khác: “Xóa tất cả audit event có `event_type = 'DEBUG'`”. Trong bảng mẫu, `event_type` là regular column; Cassandra không thể mặc định định tuyến theo nó.

Không nên giả định có thể viết:

```sql
-- Không có điều kiện định vị partition / hàng thích hợp:
-- DELETE FROM audit_events_by_tenant_day WHERE event_type = 'DEBUG';
```

Hoặc định nghĩa một repository method rồi kỳ vọng Spring Data chuyển nó thành việc tìm/xóa hàng trên toàn cụm mà không xét khóa:

```java
// Không nên suy luận rằng chỉ tên phương thức đã bảo đảm
// thao tác này được hỗ trợ và hiệu quả trên bảng hiện tại.
// void deleteByEventType(String eventType);
```

Thay vào đó, cần trả lời:

1. API có thể xác định được **những partition cụ thể** chứa dữ liệu cần xóa không?
2. Một bảng theo truy vấn khác có giúp tìm **đủ primary key** của các hàng cần xóa không?
3. Đây là nhu cầu xóa từng record, dọn một bucket thời gian, hay chính sách giữ dữ liệu nhiều tháng?
4. Có thể dùng **TTL** phù hợp ngay lúc ghi để dữ liệu tự hết hạn theo nghiệp vụ không?

Nếu phải duyệt một tập hàng để xóa, nên thực hiện job có checkpoint, paging, giới hạn tốc độ và kiểm soát mức đồng thời; không biến một request HTTP thành quét toàn bộ bảng khi chưa có đánh giá chi phí.

**`ALLOW FILTERING` không phải giải pháp tổng quát cho DELETE**. Nó không xóa được hạn chế thiết kế khóa và có thể tạo truy vấn đọc đắt ngay cả khi sử dụng ở những tình huống CQL cho phép lọc.

## 7. Nếu bản ghi không tồn tại thì sao?

Khi gọi:

```java
auditEventRepository.deleteById(key);
```

không nên suy ra rằng:

- Repository luôn truy vấn tồn tại trước khi xóa.
- Phương thức trả số hàng đã xóa.
- Sau khi phương thức trả thành công, mọi replica đã dọn sạch dữ liệu vật lý.
- Một yêu cầu đọc với mọi consistency level đều quan sát trạng thái giống nhau ngay tức thì.

Với thao tác xóa CQL thông thường, Cassandra có thể ghi dấu xóa ngay cả khi hàng được nhắm đến chưa tồn tại. Vì vậy, `void` không nói “hàng vừa bị xóa vốn chắc chắn đã tồn tại”.

### 7.1. Có thể kiểm tra existsById trước không?

Có thể kiểm tra cho **trải nghiệm nghiệp vụ**, ví dụ trả thông báo 404 nếu ngay trước đó không tìm thấy:

```java
if (!auditEventRepository.existsById(key)) {
    throw new IllegalArgumentException("Audit event not found");
}

auditEventRepository.deleteById(key);
```

Nhưng đây là **hai thao tác tách biệt**. Giữa `existsById` và `deleteById`, client khác có thể thay đổi dữ liệu; vì vậy phép kiểm tra này không tạo điều kiện xóa nguyên tử và làm tăng ít nhất một lần đọc. Chỉ sử dụng khi phù hợp với yêu cầu, tránh dùng như cơ chế bảo đảm tồn tại tuyệt đối.

### 7.2. Khi thực sự cần delete có điều kiện: IF EXISTS

Cassandra hỗ trợ một số thao tác điều kiện dùng **lightweight transaction (LWT)**. Ví dụ:

```sql
DELETE FROM audit_events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-25'
  AND occurred_at = '2026-11-25T08:45:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222
IF EXISTS;
```

Kết quả CQL điều kiện có thể cho biết thao tác **đã được áp dụng hay không** (thường qua trường `[applied]` khi làm việc với kết quả của driver).

Điều kiện `IF EXISTS` không đồng nghĩa với giao dịch phân tán nhiều bảng, và LWT tốn chi phí phối hợp hơn thao tác ghi/xóa thường. Hãy dùng nó khi **tính điều kiện là yêu cầu nghiệp vụ thực sự**, không tự thêm vào mọi lệnh xóa để “an toàn hơn”.

API repository `deleteById` thông dụng không tự trả trạng thái `[applied]`. Khi cần semantics điều kiện và kiểm tra kết quả rõ ràng, dùng CQL qua API thích hợp (ví dụ driver hoặc `CassandraTemplate` theo khả năng phiên bản) và xử lý kết quả.

## 8. Tombstone: xóa logic và chi phí lưu trữ

Khi nhận lệnh xóa, Cassandra không thể đơn giản bỏ dữ liệu cũ khỏi mọi bản sao ngay lập tức: một replica có thể tạm thời không sẵn sàng, và các SSTable là cấu trúc lưu trữ bất biến. Vì vậy, Cassandra dùng tombstone biểu thị rằng dữ liệu đã bị xóa.

```text
T0: INSERT  (tenant=T1, day=D, event=E2) -> dữ liệu được ghi
T1: DELETE  (tenant=T1, day=D, event=E2) -> tombstone
T2: READ    -> cần xét dấu xóa và dữ liệu cũ theo quy tắc Cassandra
T3: Compaction / quá trình dọn dẹp phù hợp -> có thể loại bỏ dữ liệu cũ
```

### 8.1. Các dạng tombstone thường gặp

- **Row tombstone:** xóa một hàng cụ thể.
- **Partition tombstone:** đánh dấu xóa toàn bộ partition.
- **Column/cell tombstone:** xóa một giá trị cột.
- **Range tombstone:** đánh dấu xóa phạm vi clustering khi CQL hỗ trợ điều kiện tương ứng.
- **TTL expiration:** dữ liệu hết hạn cũng có thể tạo dấu xóa cần được xử lý.

Không nên nhầm số câu lệnh `DELETE` với số tombstone vật lý chính xác được tạo: phụ thuộc loại thao tác, schema, phiên bản và cách Cassandra biểu diễn thay đổi.

### 8.2. Vì sao xóa nhiều có thể làm đọc chậm?

Một truy vấn `SELECT ... LIMIT 20` có thể vẫn phải xét nhiều dấu xóa khi tìm đủ 20 hàng còn hiệu lực. Các khu vực dữ liệu có nhiều tombstone, đặc biệt khi đọc theo phạm vi clustering hoặc trên partition lớn, có thể làm tăng CPU, I/O và độ trễ.

Đối với bảng nhật ký lưu theo ngày:

- Nếu thường xóa từng event ngay sau khi xử lý, số tombstone có thể tăng.
- Nếu một partition tồn tại rất lâu và có nhiều lần thêm/xóa, kích thước và chi phí đọc có thể cao dù số hàng “còn sống” không lớn.
- Nếu có thể định nghĩa **thời hạn lưu giữ** khi ghi, hãy cân nhắc TTL và bucket theo thời gian; nhưng TTL cũng tạo tombstone, không phải cách xóa miễn phí.

### 8.3. gc_grace_seconds không phải thời gian dữ liệu chắc chắn được xóa khỏi đĩa

Cassandra sử dụng các quy tắc về thời gian giữ tombstone, repair và compaction để tránh các bản sao chứa dữ liệu cũ làm dữ liệu đã xóa xuất hiện trở lại (*zombie data*) trong những điều kiện nhất định. Tham số `gc_grace_seconds` liên quan đến ranh giới an toàn ấy.

**Đừng tự ý giảm `gc_grace_seconds` xuống 0 chỉ vì muốn giải phóng dung lượng nhanh.** Cần hiểu lịch repair, trạng thái replica, chế độ compaction và phiên bản Cassandra; thời gian đủ điều kiện dọn tombstone không có nghĩa dữ liệu sẽ được dọn đúng thời điểm đó.

Một chiến lược lưu giữ dữ liệu nên được thiết kế **cùng với mô hình partition và quy trình vận hành**, không chỉ bằng cách gọi `deleteById` thường xuyên.

## 9. Tính nhất quán, ghi đồng thời và retry

### 9.1. Consistency level ảnh hưởng điều gì?

Cassandra nhân bản dữ liệu theo keyspace replication. Một thao tác xóa có **consistency level**, quy định bao nhiêu replica cần phản hồi cho thao tác thành công theo cấu hình/topology.

Ví dụ `LOCAL_QUORUM` trong hệ thống có replication và local datacenter phù hợp có thể tăng yêu cầu xác nhận từ replica so với consistency level thấp hơn. Nhưng nó **không**:

- Biến delete thành thao tác tức thời dọn dữ liệu vật lý trên mọi node.
- Cung cấp `JOIN` hay cascade sang mọi bảng chứa cùng một bản ghi nghiệp vụ.
- Bảo đảm xóa theo một điều kiện không thuộc partition key trở nên hợp lệ.
- Tự tạo giao dịch ACID nhiều partition như trong cơ sở dữ liệu quan hệ.

Ứng dụng cần lựa chọn consistency cho thao tác ghi/xóa và các lần đọc theo yêu cầu về độ trễ, khả dụng và nhất quán dữ liệu.

### 9.2. Lệnh xóa thông thường và thao tác ghi cạnh tranh

Cassandra sử dụng timestamp để giải quyết các thay đổi cạnh tranh ở mức dữ liệu. Nếu có một `DELETE` và một `INSERT/UPDATE` cùng nhắm đến khóa giống nhau, kết quả quan sát cuối cùng phụ thuộc timestamp, thứ tự và ngữ nghĩa của các ghi, không chỉ phụ thuộc request nào đến HTTP service trước.

Một tình huống:

```text
Service A: xóa event E2
Service B: ghi lại event E2 bằng khóa cũ
                      |
                      v
        Cần quy tắc nghiệp vụ về ai được phép ghi và khi nào
```

Nếu mục tiêu là “sau khi người dùng xóa, không ai được tự tái tạo bản ghi”, chỉ lệnh delete không đủ. Cần kiểm soát các luồng ghi, trạng thái nghiệp vụ hoặc cơ chế điều kiện thích hợp.

### 9.3. Retry phải xét tác dụng phụ

Lặp lại một lệnh xóa cùng khóa thường có ý nghĩa nghiệp vụ “bản ghi này cần vắng mặt”. Tuy vậy, không nên coi mọi retry trong hệ thống phân tán là an toàn tuyệt đối:

- Client timeout không chứng minh lệnh xóa chưa được Cassandra nhận.
- Nếu một client khác vừa ghi giá trị mới vào cùng khóa, retry delete muộn có thể xóa mất dữ liệu mới.
- Nếu xóa kéo theo thao tác ở bảng phụ, cache, object storage hoặc phát sự kiện, những phần đó cần cơ chế idempotency và kiểm soát thứ tự riêng.

Thiết kế một **ID thao tác**, phiên bản/trạng thái nghiệp vụ hoặc cơ chế đồng bộ phù hợp nếu hệ thống yêu cầu chính xác khi request được thử lại.

## 10. Dữ liệu nhân bản theo truy vấn: xóa không tự lan sang bảng khác

Cassandra thường dùng **denormalization**: cùng một thực thể nghiệp vụ được biểu diễn trong nhiều bảng để phục vụ các kiểu đọc khác nhau.

Ví dụ:

```sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    order_status text
);

CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    order_month text,
    created_at timestamp,
    order_id uuid,
    order_status text,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Một đơn có thể có hàng trong cả hai bảng. Nếu gọi repository của `orders_by_id`:

```java
ordersByIdRepository.deleteById(orderId);
```

thì **không có cascade tự động** sang `orders_by_customer_month`. Muốn bỏ đơn khỏi danh sách khách hàng, phải xác định đầy đủ khóa của hàng ở bảng phụ: `customer_id`, `order_month`, `created_at` và `order_id`.

```sql
DELETE FROM orders_by_customer_month
WHERE customer_id = 33333333-3333-4333-8333-333333333333
  AND order_month = '2026-11'
  AND created_at = '2026-11-25T10:00:00Z'
  AND order_id = 44444444-4444-4444-8444-444444444444;
```

Hai thao tác xóa thuộc các partition/bảng khác nhau. Nếu một thao tác thành công còn thao tác kia lỗi, hai cách nhìn có thể tạm thời lệch nhau. Tầng nghiệp vụ cần xác định:

1. Bảng nào là **nguồn dữ liệu chuẩn**.
2. Có cần lưu metadata khóa của bảng phụ để xóa đúng không.
3. Làm thế nào để retry/đối soát khi cập nhật thiếu.
4. Có nên dùng **soft delete** hoặc trạng thái nghiệp vụ `DELETED` trước khi thu dọn dữ liệu vật lý không.

`BATCH` không mặc nhiên cung cấp isolation và tính chất giao dịch quan hệ cho các bảng/partition khác nhau. Việc dùng logged batch nhiều partition cần đánh giá ngữ nghĩa và chi phí phối hợp, không xem là cách tăng tốc xóa hàng loạt.

## 11. deleteAll và các thao tác xóa quy mô lớn

Tên `deleteAll()` dễ khiến người dùng nghĩ đến thao tác dọn bảng nhanh. Nhưng đối với Cassandra, **xóa toàn bộ các hàng** hoặc xóa phần lớn dữ liệu bằng hàng loạt thao tác thông thường có thể tốn tài nguyên và tạo nhiều tombstone.

Không sử dụng `repository.deleteAll()` như thao tác bảo trì tùy tiện trên bảng sản xuất có dữ liệu lớn. Hành vi thực thi cụ thể phụ thuộc repository/phiên bản; cần đánh giá số lượng hàng, yêu cầu đọc danh sách khóa và tải phát sinh.

Một số tình huống nên dùng chiến lược khác:

| Nhu cầu | Hướng cân nhắc | Lưu ý |
| --- | --- | --- |
| Dữ liệu chỉ cần giữ trong N ngày | TTL theo chính sách nghiệp vụ và time bucket. | TTL cũng tạo tombstone; phải đo tác động. |
| Xóa toàn bộ một tenant trong một ngày | Partition delete nếu schema và yêu cầu cho phép. | Cần xác nhận thao tác thực sự muốn xóa **cả partition**. |
| Xóa toàn bộ bảng thử nghiệm | Công cụ quản trị/CQL thích hợp, có kiểm soát môi trường. | Không dùng thao tác phá hủy dữ liệu trong production nếu chưa có quy trình vận hành. |
| Xóa một tập record được xác định bằng điều kiện ngoài khóa | Job đọc khóa phù hợp, phân trang và xóa có kiểm soát; hoặc bảng phụ phục vụ truy vấn. | Quét toàn bảng/cross-partition có thể rất đắt. |
| Xóa vì yêu cầu quyền riêng tư | Thiết kế bao quát cả bảng phụ, cache, bản sao và hệ thống lưu trữ liên quan. | Tombstone không đồng nghĩa byte trên mọi hệ thống đã bị loại bỏ tức thời. |

Trường hợp xóa dữ liệu vì yêu cầu tuân thủ/chính sách lưu giữ cần được đánh giá theo quy định và kiến trúc hệ thống, không chỉ dựa vào kết quả thành công của một API repository.

## 12. CQL trực tiếp và CassandraTemplate khi cần kiểm soát thao tác

Repository phù hợp với xóa một entity khi đã có khóa chính. Khi muốn một điều kiện đặc thù hoặc thao tác trên cột, có thể dùng `CassandraTemplate` hoặc prepared CQL theo API Spring Data/Java Driver tương thích.

Ví dụ chuẩn bị lệnh xóa bằng driver:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class AuditEventCqlDelete {

    private final CqlSession session;
    private final PreparedStatement deleteOne;

    public AuditEventCqlDelete(CqlSession session) {
        this.session = session;
        this.deleteOne = session.prepare("""
            DELETE FROM audit_events_by_tenant_day
            WHERE tenant_id = ?
              AND event_day = ?
              AND occurred_at = ?
              AND event_id = ?
            """);
    }

    public void delete(
            UUID tenantId, LocalDate eventDay,
            Instant occurredAt, UUID eventId) {
        session.execute(deleteOne.bind(
                tenantId, eventDay, occurredAt, eventId));
    }
}
```

Điểm đáng chú ý:

- Query bind **đúng cả bốn cột của khóa chính**.
- Prepared statement được tạo một lần khi khởi tạo đối tượng minh họa, không phải mỗi lần xóa.
- Không ghép dữ liệu đầu vào thành chuỗi CQL.
- Phương thức hiện tại không dùng `IF EXISTS`, không nhận được kết quả “đã từng tồn tại” từ một điều kiện LWT.

Trong ứng dụng Spring, `CqlSession` thường có vòng đời được container quản lý. Đừng tự đóng session sau mỗi lần gọi `delete()`; driver quản lý kết nối và các yêu cầu thực thi bên dưới.

### Repository, template hay driver?

| Cách gọi | Ưu thế | Cần chú ý |
| --- | --- | --- |
| `repository.deleteById(id)` | Ngắn gọn, phù hợp xóa entity theo ID. | ID phải đầy đủ; không phản hồi row count. |
| `repository.delete(entity)` | Tiện khi đã có entity với khóa hợp lệ. | Không tự so khớp regular columns hoặc tự cascade. |
| `CassandraTemplate` | Điều khiển rõ hơn thao tác qua API Spring Data, tận dụng mapping. | API khác nhau theo phiên bản; CQL vẫn có quy tắc khóa. |
| `CqlSession` + prepared CQL | Chủ động với câu lệnh và kết quả điều kiện. | Tự quản lý bind, ngữ nghĩa truy vấn và kiểm thử. |

## 13. Thiết kế API xóa an toàn

Xét endpoint:

```text
DELETE /tenants/{tenantId}/audit-events/{eventId}
```

Nếu bảng lưu theo `(tenant_id, event_day)` và clustering key `(occurred_at, event_id)`, endpoint trên **thiếu thông tin để truy vấn/xóa trực tiếp một hàng**.

Có thể cải tiến thành một API có đầy đủ thông tin khóa:

```text
DELETE /tenants/{tenantId}/audit-days/{eventDay}/events/{occurredAt}/{eventId}
```

Hoặc nếu muốn giữ URL ngắn, service cần một bảng tra cứu từ `eventId` đến **khóa CQL đầy đủ**. Bảng tra cứu này cũng cần chiến lược tạo, cập nhật, xóa và đối soát phù hợp.

### Quy trình kiểm tra trước khi xóa

1. **Xác thực/ủy quyền:** request có quyền thao tác với tenant hoặc dữ liệu này không?
2. **Xác định loại thao tác:** xóa một hàng, một partition hay một cột?
3. **Kiểm tra khóa:** có đủ partition key và clustering key cho phạm vi đã chọn không?
4. **Kiểm tra trạng thái nghiệp vụ:** có được phép xóa ở giai đoạn hiện tại không; cần `IF EXISTS`/LWT hay điều phối cấp ứng dụng?
5. **Kiểm tra dữ liệu dẫn xuất:** có bảng danh sách, cache hoặc hệ thống bên ngoài cần xử lý tiếp không?
6. **Kiểm tra chính sách giữ dữ liệu:** xóa ngay, soft delete hay TTL là mô hình phù hợp?
7. **Đo lường:** theo dõi số lần delete, latency, tombstone, timeout và tác động lên các truy vấn đọc.

Không nên dùng “xóa theo ID” như từ đồng nghĩa với “xóa tất cả dấu vết nghiệp vụ” nếu dữ liệu còn hiện diện ở nhiều nơi.

## 14. Kiểm thử những trường hợp dễ sai

Kiểm thử tích hợp với một Cassandra test environment có schema tương ứng nên bao gồm:

| Ca kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Xóa bằng `deleteById` với khóa đơn hợp lệ | Không đọc được hàng ở khóa đó theo query phù hợp sau khi thao tác đã được quan sát với consistency tương ứng. |
| Xóa bằng `delete(entity)` | Chỉ hàng có khóa chính từ entity bị nhắm đến. |
| Xóa E2 trong partition có E1/E2/E3 | E1 và E3 không bị xóa theo. |
| Xóa với ID có thiếu thành phần khóa tổng hợp | Input bị từ chối hoặc thao tác không thành công; không tự chuyển thành xóa cả partition. |
| Xóa bản ghi không tồn tại | Không suy ra số hàng bị xóa từ `void`; xử lý theo hợp đồng API nghiệp vụ. |
| Xóa có `IF EXISTS` | Đọc kết quả `[applied]` theo contract của driver/API phù hợp. |
| Hai request ghi và xóa cùng khóa đồng thời | Kết quả tuân theo chính sách xử lý cạnh tranh đã thiết kế. |
| Xóa bản ghi được nhân bản ở bảng khác | Kiểm tra tất cả cách nhìn được cập nhật/đối soát theo chính sách nghiệp vụ. |
| Xóa khối lượng lớn | Theo dõi latency, tombstone, kích thước partition và tốc độ compaction/repair. |

Ví dụ suy luận trên ba hàng:

```text
Trước:
  (T1, 2026-11-25) -> E1, E2, E3

Gọi deleteById(key của E2):
  (T1, 2026-11-25) -> E1, E3

Gọi CQL DELETE chỉ với (T1, 2026-11-25):
  partition tương ứng bị đánh dấu xóa
```

Mô hình minh họa này nói về **kết quả logic** của các hàng, không nói dữ liệu vật lý đã được loại bỏ ngay khỏi SSTable hoặc mọi replica đồng thời.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Bảng có `PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)`. Chỉ biết `tenant_id` và `event_day` có đủ để xóa một event không?

**Trả lời:** Không. Hai giá trị đó chỉ định partition; muốn xóa đúng một hàng cần cả `occurred_at` và `event_id`. Một lệnh CQL xóa chỉ theo partition key có thể xóa toàn bộ partition.

**Câu 2.** `delete(entity)` có so sánh `event_type` và `payload` của entity để xác định hàng cần xóa không?

**Trả lời:** Không nên giả định như vậy. Thao tác xóa theo entity được định vị dựa trên primary key, không phải mọi regular column.

**Câu 3.** Gọi `existsById` rồi `deleteById` có bảo đảm hàng vẫn tồn tại tại thời điểm xóa không?

**Trả lời:** Không. Đây là hai thao tác có khoảng thời gian giữa chúng; nếu cần tính điều kiện nguyên tử trên hàng, cân nhắc `IF EXISTS`/LWT và kiểm soát kết quả áp dụng.

**Câu 4.** Vì sao xóa nhiều hàng có thể làm truy vấn `LIMIT 20` chậm?

**Trả lời:** Cassandra có thể phải xử lý nhiều tombstone để tìm đủ hàng còn hiệu lực. `LIMIT` không loại bỏ chi phí xử lý dấu xóa.

**Câu 5.** Xóa đơn hàng ở `orders_by_id` có làm mất đơn ở `orders_by_customer_month` không?

**Trả lời:** Không tự động. Đây là hai bảng với khóa khác nhau; cần cơ chế xóa/đối soát từng cách nhìn.

**Câu 6.** Vì sao không nên rút `gc_grace_seconds` xuống 0 chỉ để xóa dữ liệu nhanh?

**Trả lời:** Tombstone hỗ trợ ngăn dữ liệu cũ trên replica tái xuất hiện; cấu hình dọn quá sớm mà không xét repair và trạng thái cụm có thể tạo rủi ro. Việc dọn vật lý còn phụ thuộc compaction và điều kiện khác.

## Tổng kết

`deleteById(ID)` và `delete(T entity)` trong Spring Data Cassandra giúp xóa theo **định danh của entity**, nhưng phải được hiểu trong mô hình CQL: **partition key định vị partition**, còn **clustering key xác định hàng** bên trong partition. Với khóa tổng hợp, hãy cung cấp **đủ toàn bộ primary key** nếu mục tiêu là xóa đúng một hàng. Tránh nhầm thao tác đó với xóa cả partition hoặc xóa theo regular column.

Mọi lệnh xóa đều cần xét **tombstone, replication, consistency, retry, tính đồng thời và dữ liệu nhân bản ở nhiều bảng**. Repository giúp mã Java ngắn gọn; thiết kế khóa, nghiệp vụ xóa và kiểm soát hiệu năng vẫn phải phù hợp với Apache Cassandra — giống như khi sử dụng `CassandraTemplate` hoặc CQL trực tiếp.
