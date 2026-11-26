# Đánh giá thay đổi nghiệp vụ khi thêm một mẫu truy vấn mới

> **Chủ đề:** Thiết kế theo truy vấn trong Spring Data Cassandra. Bài học hướng dẫn cách chuyển một yêu cầu nghiệp vụ mới thành quyết định về mô hình dữ liệu, repository, CQL, tính nhất quán, phân trang và chi phí vận hành trên Apache Cassandra.

## 1. Vì sao một màn hình mới có thể dẫn tới một bảng mới?

Trong hệ quản trị quan hệ, khi sản phẩm cần thêm bộ lọc, lập trình viên thường nghĩ đến cách mở rộng `WHERE`, thêm index hoặc viết `JOIN`. Cassandra hoạt động theo một mô hình khác: dữ liệu được **phân phối theo partition key** và sắp xếp **trong từng partition** theo clustering columns. Vì vậy, một kiểu truy cập mới có thể đòi hỏi **bảng đọc mới**, ngay cả khi dữ liệu nghiệp vụ không đổi.

Ví dụ: hệ thống IoT đã có màn hình lịch sử của một thiết bị. Người vận hành giờ muốn xem những cảnh báo pin yếu mới nhất của **toàn bộ thiết bị trong một chi nhánh**. Cả hai màn hình dùng cùng sự kiện, nhưng cách tìm dữ liệu rất khác.

Điểm cần đánh giá không phải là “có thể viết CQL chạy được không?” mà là:

- Có biết đầy đủ partition key ngay khi nhận yêu cầu không?
- Mỗi lần đọc cần chạm bao nhiêu partition, bao nhiêu replica, bao nhiêu dòng?
- Truy vấn có trả thứ tự mong muốn mà không cần quét hoặc sắp xếp lượng dữ liệu lớn không?
- Ghi dữ liệu sang một bảng khác làm tăng độ trễ, lưu trữ và gánh nặng đồng bộ thế nào?
- Dữ liệu cũ, sự kiện tới muộn, phân trang và xóa dữ liệu sẽ được xử lý ra sao?

**Mục tiêu học tập:** có thể lập bản đánh giá tác động trước khi sửa code; chọn giữa giữ bảng cũ, thêm bảng phục vụ truy vấn, dùng chỉ mục phù hợp hoặc chuyển nhu cầu sang hệ tìm kiếm/phân tích; và thiết kế quá trình chuyển đổi có thể kiểm chứng.

## 2. Hệ thống hiện tại: lịch sử theo thiết bị và ngày

Giả sử nền tảng quản lý nhiều khách hàng (`tenant`), mỗi khách hàng có các chi nhánh (`site`) và nhiều thiết bị (`device`). Thiết bị gửi sự kiện với:

| Trường | Ý nghĩa |
| --- | --- |
| `tenant_id` | Khách hàng sở hữu dữ liệu |
| `device_id` | Thiết bị phát sinh sự kiện |
| `site_id` | Chi nhánh mà thiết bị thuộc về **tại thời điểm xảy ra sự kiện** |
| `event_time` | Thời điểm sự kiện xảy ra, chuẩn hóa UTC |
| `event_id` | Mã sự kiện ổn định qua các lần gửi lại |
| `event_type` | `TEMPERATURE`, `BATTERY_LOW`, `DISCONNECTED`, ... |
| `payload` | Chi tiết sự kiện (ví dụ chuỗi JSON) |
| `received_at` | Thời điểm hệ thống nhận sự kiện |

Truy vấn đang phục vụ tốt là:

> Xem tối đa 50 sự kiện mới nhất của một thiết bị vào một ngày UTC, hoặc đọc tiếp những sự kiện cũ hơn.

Schema hiện tại:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    tenant_id   uuid,
    device_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    site_id     uuid,
    event_type  text,
    payload     text,
    received_at timestamp,
    PRIMARY KEY ((tenant_id, device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`(tenant_id, device_id, event_day)` là **partition key tổng hợp**; `event_time` và `event_id` là **clustering columns**. Truy vấn phù hợp:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Cassandra định tuyến trực tiếp đến partition của đúng thiết bị và ngày, rồi đọc theo thứ tự clustering đã lưu. **Cột `site_id` có tồn tại trong row không có nghĩa `site_id` là một khóa tra cứu hiệu quả.** Cột dữ liệu và partition key có vai trò hoàn toàn khác nhau.

## 3. Đọc yêu cầu nghiệp vụ mới như một hợp đồng truy vấn

Product đưa ra user story:

> “Là nhân viên vận hành chi nhánh, tôi muốn xem 50 cảnh báo `BATTERY_LOW` mới nhất của tất cả thiết bị trong chi nhánh trong 24 giờ gần nhất, và có thể tải các trang cũ hơn.”

Không nên bắt đầu bằng việc sửa repository. Trước hết phải làm rõ **hợp đồng đọc**:

| Câu hỏi | Giả định được chốt cho ví dụ |
| --- | --- |
| Người dùng chọn gì? | `tenantId`, `siteId`; loại cảnh báo cố định `BATTERY_LOW` |
| Thứ tự? | `event_time` giảm dần; có tie-breaker ổn định |
| Cửa sổ thời gian? | `[now - 24h, now)` theo UTC, tức bao gồm đầu, loại trừ cuối |
| Kích thước trang? | 50 sự kiện mỗi trang, duyệt tiếp bằng con trỏ |
| Độ mới chấp nhận? | Ví dụ cho phép độ trễ đồng bộ bảng đọc tối đa 10 giây |
| Retention? | Ví dụ giữ dữ liệu cảnh báo 30 ngày |
| Quyền truy cập? | Người dùng chỉ được xem `siteId` thuộc `tenantId` được cấp quyền |
| Mục tiêu hiệu năng? | Ví dụ p95 dưới 300 ms cho trang đầu trong tải dự kiến |

Các số 10 giây, 30 ngày và 300 ms là **giả định để luyện cách phân tích**, không phải bảo đảm mặc định của Cassandra. Trong dự án thật, chúng phải được thống nhất với product/SRE và được đo trong môi trường đại diện.

Cần hỏi thêm ngay nếu yêu cầu chưa rõ: “24 giờ” dựa vào `event_time` hay `received_at`? Thiết bị đổi chi nhánh thì sự kiện cũ thuộc chi nhánh cũ hay mới? Có lọc thêm trạng thái “chưa xử lý” hay không? Một số bộ lọc làm thay đổi partition key, khiến phương án thiết kế thay đổi hoàn toàn.

### Mô tả truy vấn dưới dạng access pattern

~~~text
Tên:  Q2 — Các cảnh báo pin yếu mới nhất theo chi nhánh

Input:    tenantId, siteId, eventType=BATTERY_LOW, from, to, pageSize, cursor
Filter:   [from, to), giới hạn 24 giờ
Sort:     eventTime DESC, deviceId ASC, eventId ASC
Output:   <= 50 cảnh báo + cursor để đọc tiếp
Tenant:   Bắt buộc kiểm tra quyền trên site
SLO:      p95 <= 300 ms (giả định cần kiểm thử)
~~~

Định nghĩa chính xác này ngăn việc vô tình mở rộng sang “tìm mọi sự kiện theo bất kỳ điều kiện nào”, một yêu cầu không phù hợp với một bảng Cassandra đơn lẻ.

## 4. Phân tích khoảng cách: bảng cũ không phục vụ Q2

Bảng `events_by_device_day` tối ưu cho Q1: **một thiết bị + một ngày**. Với Q2, client chỉ biết `tenantId`, `siteId`, `eventType` và khoảng thời gian; client **không có danh sách partition key cho mọi thiết bị**.

Ba cách thường được đề xuất nhưng có vấn đề:

1. **Thêm `WHERE site_id = ... AND event_type = ...` vào bảng cũ.** Hai cột này không nằm trong partition key hoặc clustering key. Cassandra không thể tự phân phối truy vấn như một cơ sở dữ liệu quan hệ có index phù hợp. `ALLOW FILTERING` không giải quyết giới hạn hiệu năng; nó có thể buộc hệ thống đọc nhiều dữ liệu để loại bỏ phần lớn kết quả.
2. **Lấy danh sách tất cả thiết bị trong chi nhánh rồi fan-out.** Nếu chi nhánh có 2.000 thiết bị và cửa sổ kéo qua hai ngày UTC, có thể phải đọc tới khoảng 4.000 partition trước khi ghép kết quả. Cách này chỉ đáng cân nhắc với nhóm thiết bị nhỏ, số lần truy vấn ít và giới hạn chặt chẽ.
3. **Dùng `CassandraTemplate` hay repository tạo câu CQL linh hoạt hơn.** API Java giúp viết truy vấn, nhưng **không thay đổi cách Cassandra định tuyến dữ liệu**. Khi access pattern không khớp schema, đổi API không giải quyết được nguyên nhân.

Điểm khác biệt là **hình dạng truy vấn**, không phải cú pháp hay framework. Trước khi quyết định, phải ước lượng số partition, kích thước kết quả, tần suất gọi và yêu cầu thứ tự.

## 5. Ước lượng tải và kiểm tra phương án

Giả sử chi nhánh lớn nhất có 1.500 thiết bị, mỗi thiết bị gửi một sự kiện/phút:

~~~text
Số sự kiện/ngày/chi nhánh = 1.500 × 60 × 24 = 2.160.000
Tỉ lệ BATTERY_LOW giả định = 2%
Số cảnh báo/ngày ≈ 43.200
Kích thước một row projection giả định = 400 byte
Dữ liệu row thô ≈ 17,3 MB/ngày/chi nhánh/loại cảnh báo
~~~

Đây chỉ là **ước lượng dung lượng dữ liệu thô**, chưa gồm overhead, replication factor, memtable/SSTable, tombstone và compaction. Cần đo phân phối thực tế, đặc biệt **site có lưu lượng lớn nhất**, không chỉ số trung bình. Trong hệ thống sự kiện, cảnh báo có thể tăng đột biến đồng loạt khi nhiều thiết bị mất nguồn hoặc mất kết nối.

Một bảng dữ liệu riêng cho Q2 sẽ chỉ chứa sự kiện `BATTERY_LOW`, không nhất thiết sao chép toàn bộ 2,16 triệu sự kiện/ngày. Nếu Q2 chỉ truy cập khoảng 43.200 cảnh báo/ngày, việc lưu thêm một bản chiếu (projection) có thể hợp lý hơn hàng nghìn partition-read cho mỗi lần mở dashboard.

Kết quả kiểm tra cần ghi được:

- **Đọc:** số bucket/partition trên mỗi yêu cầu, số dòng quét để lấy 50 dòng, p95/p99.
- **Ghi:** số row mới mỗi sự kiện, đỉnh ghi đồng thời, latency và failure rate.
- **Dung lượng:** row/partition, byte/partition, retention, replication, tombstone.
- **Tính đúng:** thời gian dữ liệu xuất hiện ở bảng mới, độ trùng/lỗi do retry, khớp dữ liệu cũ.

Các phép tính này là cơ sở ra quyết định; nếu kết quả cho thấy partition quá nóng, phải sửa bucket hoặc partition key **trước** khi triển khai.

## 6. Đặt các phương án cạnh nhau

| Phương án | Khi nào có thể dùng | Giới hạn cần đánh giá |
| --- | --- | --- |
| Giữ bảng cũ, fan-out theo thiết bị | Số thiết bị ít, ít request, chấp nhận chi phí ghép kết quả | Chi phí tăng theo số thiết bị × số ngày; sắp xếp và paging nhiều nguồn phức tạp |
| Thêm bảng phục vụ Q2 | Mẫu truy vấn ổn định, được gọi thường xuyên, cần latency dự đoán được | Denormalization, thêm ghi và lưu trữ, đồng bộ và backfill |
| Secondary index / Storage-Attached Index (nếu hệ Cassandra đang dùng hỗ trợ) | Filter có đặc tính phù hợp với chỉ mục, được đo bằng dữ liệu thực | Khả năng hỗ trợ phụ thuộc phiên bản/nền tảng; cần kiểm tra selectivity, latency, hot partition và consistency |
| Materialized view | Chỉ trong các trường hợp đáp ứng ràng buộc kỹ thuật và vận hành của Cassandra | Không thay thế việc phân tích khóa truy vấn; cần đánh giá giới hạn, backfill và trạng thái view |
| Công cụ search / OLAP riêng | Tìm kiếm tự do nhiều điều kiện, thống kê/tổng hợp nhiều thiết bị hoặc lịch sử dài | Đồng bộ thêm hệ thống, chi phí vận hành, độ trễ dữ liệu |

**Lựa chọn của ví dụ:** thêm bảng `alerts_by_site_type_day` cho Q2. Quyết định này dựa trên giả định dashboard chạy thường xuyên, truy vấn cố định theo chi nhánh và loại cảnh báo, dữ liệu có thể chậm tối đa vài giây. Nó **không** có nghĩa luôn phải thêm bảng cho mọi yêu cầu sản phẩm.

## 7. Thiết kế bảng mới theo Q2

Thiết kế một bản chiếu lưu đúng các cột cần hiển thị, với partition key gồm khách hàng, chi nhánh, loại cảnh báo và ngày UTC:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.alerts_by_site_type_day (
    tenant_id   uuid,
    site_id     uuid,
    event_type  text,
    event_day   date,
    event_time  timestamp,
    device_id   uuid,
    event_id    uuid,
    message     text,
    received_at timestamp,
    PRIMARY KEY (
        (tenant_id, site_id, event_type, event_day),
        event_time, device_id, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC, device_id ASC, event_id ASC
);
~~~

Phân tích khóa:

- `(tenant_id, site_id, event_type, event_day)` là **partition key**. Mỗi tổ hợp khách hàng–chi nhánh–loại cảnh báo–ngày định tuyến tới một partition.
- `event_time DESC` đưa cảnh báo mới nhất lên trước trong partition.
- `device_id` và `event_id` làm **tie-breaker** và tránh ghi đè hai sự kiện có cùng timestamp nhưng khác thiết bị/sự kiện.
- `message` và `received_at` là cột dữ liệu phục vụ UI, không tham gia định tuyến.

Không cần lưu toàn bộ JSON từ bảng Q1 nếu trang cảnh báo chỉ hiển thị thông điệp tóm tắt. Việc chọn payload nhỏ giảm chi phí truyền và đọc. Khi người dùng mở chi tiết sự kiện, ứng dụng có thể chuyển về truy vấn Q1 bằng `tenantId`, `deviceId`, ngày và khóa sự kiện.

### Ví dụ ghi bản chiếu

~~~sql
INSERT INTO telemetry.alerts_by_site_type_day (
    tenant_id, site_id, event_type, event_day,
    event_time, device_id, event_id, message, received_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    33333333-3333-4333-8333-333333333333,
    'BATTERY_LOW',
    '2026-11-25',
    '2026-11-25T08:30:00Z',
    22222222-2222-4222-8222-222222222222,
    44444444-4444-4444-8444-444444444444,
    'Pin thiết bị còn 8%',
    '2026-11-25T08:30:02Z'
);
~~~

Nếu sự kiện được gửi lại, hãy giữ nguyên `event_id`, `device_id` và `event_time` đã chuẩn hóa đến **millisecond**. Ghi lại cùng primary key sẽ cập nhật cùng row. Tạo `event_id` mới trên mỗi retry sẽ gây trùng lặp ở bảng mới.

### CQL đọc một bucket

~~~sql
SELECT event_time, device_id, event_id, message
FROM telemetry.alerts_by_site_type_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND site_id = 33333333-3333-4333-8333-333333333333
  AND event_type = 'BATTERY_LOW'
  AND event_day = '2026-11-25'
  AND event_time >= '2026-11-25T08:00:00Z'
  AND event_time <  '2026-11-25T09:00:00Z'
LIMIT 50;
~~~

CQL này có **đầy đủ partition key** và lọc dải trên clustering column đầu tiên. Nó không cần `ALLOW FILTERING`, không dùng `JOIN` và không giả định sort toàn bộ các partition.

## 8. Mẫu truy vấn “24 giờ gần nhất” cần xử lý nhiều bucket

Với ngày UTC là partition key, khoảng 24 giờ có thể chạm **hai ngày khác nhau**. Ví dụ lúc `2026-11-25T09:00:00Z`, cửa sổ là:

~~~text
from = 2026-11-24T09:00:00Z
to   = 2026-11-25T09:00:00Z (exclusive)

Partition ngày 24:
  [2026-11-24T09:00:00Z, 2026-11-25T00:00:00Z)

Partition ngày 25:
  [2026-11-25T00:00:00Z, 2026-11-25T09:00:00Z)
~~~

Quy trình đọc:

1. Chốt `from` và `to` trên server một lần cho toàn bộ lần duyệt; không tính lại `now()` khi client xin trang tiếp.
2. Xác định các ngày UTC giao với `[from, to)`. Với cửa sổ 24 giờ, tối đa hai ngày; với cửa sổ tùy ý cần áp dụng giới hạn số ngày.
3. Đọc từng partition với đúng khóa và giới hạn thời gian của nó; trong mỗi partition, dữ liệu đã sắp xếp theo `event_time DESC`.
4. Ghép tối đa `pageSize` kết quả theo cùng thứ tự toàn cục, dùng `device_id` và `event_id` để phá hòa nếu timestamp bằng nhau.
5. Trả continuation token có trạng thái đọc của từng partition và thông tin về bản ghi đã trả hoặc buffer chưa tiêu thụ.

**Không thể dùng một `ORDER BY event_time DESC` để Cassandra sắp xếp chung hai partition.** Việc ghép là trách nhiệm của ứng dụng. Vì partition được chia theo ngày và khoảng thời gian không chồng nhau, có thể duyệt ngày mới trước rồi mới đến ngày cũ, nhưng cursor vẫn phải giữ tiến độ riêng và xét giới hạn thời gian chính xác.

Nếu dashboard yêu cầu “mọi loại cảnh báo” thay vì một `event_type` cụ thể, `event_type` trong partition key hiện tại không còn phù hợp cho một truy vấn đơn. Cần đánh giá một bảng khác, fan-out trên tập loại nhỏ có giới hạn, hoặc chọn công cụ khác.

## 9. Ánh xạ bảng mới trong Spring Data Cassandra

CQL quyết định access pattern; Spring Data Cassandra giúp tổ chức entity, repository, `CassandraTemplate` và các phép đọc/ghi. Ví dụ mã dưới đây minh họa cách biểu diễn **khóa chính tổng hợp** của bảng Q2; đặt các lớp vào những tệp Java riêng.

**`SiteAlertKey.java`**

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class SiteAlertKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "site_id", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private UUID siteId;

    @PrimaryKeyColumn(name = "event_type", ordinal = 2,
        type = PrimaryKeyType.PARTITIONED)
    private String eventType;

    @PrimaryKeyColumn(name = "event_day", ordinal = 3,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "event_time", ordinal = 4,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant eventTime;

    @PrimaryKeyColumn(name = "device_id", ordinal = 5,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private UUID deviceId;

    @PrimaryKeyColumn(name = "event_id", ordinal = 6,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private UUID eventId;

    public SiteAlertKey() {}

    public SiteAlertKey(UUID tenantId, UUID siteId, String eventType,
                        LocalDate eventDay, Instant eventTime,
                        UUID deviceId, UUID eventId) {
        this.tenantId = tenantId;
        this.siteId = siteId;
        this.eventType = eventType;
        this.eventDay = eventDay;
        this.eventTime = eventTime;
        this.deviceId = deviceId;
        this.eventId = eventId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }
    public UUID getSiteId() { return siteId; }
    public void setSiteId(UUID value) { siteId = value; }
    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }
    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { eventDay = value; }
    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant value) { eventTime = value; }
    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }
    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof SiteAlertKey that)) return false;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(siteId, that.siteId)
            && Objects.equals(eventType, that.eventType)
            && Objects.equals(eventDay, that.eventDay)
            && Objects.equals(eventTime, that.eventTime)
            && Objects.equals(deviceId, that.deviceId)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, siteId, eventType, eventDay,
                            eventTime, deviceId, eventId);
    }
}
~~~

**`SiteAlert.java`**

~~~java
import java.time.Instant;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("alerts_by_site_type_day")
public class SiteAlert {
    @PrimaryKey
    private SiteAlertKey key;

    @Column("message")
    private String message;

    @Column("received_at")
    private Instant receivedAt;

    public SiteAlert() {}

    public SiteAlert(SiteAlertKey key, String message, Instant receivedAt) {
        this.key = key;
        this.message = message;
        this.receivedAt = receivedAt;
    }

    public SiteAlertKey getKey() { return key; }
    public void setKey(SiteAlertKey value) { key = value; }
    public String getMessage() { return message; }
    public void setMessage(String value) { message = value; }
    public Instant getReceivedAt() { return receivedAt; }
    public void setReceivedAt(Instant value) { receivedAt = value; }
}
~~~

**`SiteAlertRepository.java`**

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface SiteAlertRepository
        extends CassandraRepository<SiteAlert, SiteAlertKey> {

    @Query("SELECT * FROM alerts_by_site_type_day "
         + "WHERE tenant_id = ?0 AND site_id = ?1 "
         + "AND event_type = ?2 AND event_day = ?3 "
         + "AND event_time >= ?4 AND event_time < ?5")
    Slice<SiteAlert> findBucket(
        UUID tenantId, UUID siteId, String eventType,
        LocalDate eventDay, Instant from, Instant to, Pageable page);
}
~~~

Ví dụ đọc **một** partition bằng repository:

~~~java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

Slice<SiteAlert> first = repository.findBucket(
    tenantId, siteId, "BATTERY_LOW", day, from, to,
    CassandraPageRequest.first(50));

if (first.hasNext()) {
    Slice<SiteAlert> next = repository.findBucket(
        tenantId, siteId, "BATTERY_LOW", day, from, to,
        first.nextPageable());
}
~~~

Đây là phân trang **trong một bucket**, không phải lời giải hoàn chỉnh cho việc ghép nhiều ngày. `Slice` cung cấp thông tin “còn trang sau không?” mà không cần tổng số row, và `CassandraPageRequest` mang trạng thái tiếp tục phù hợp với Cassandra. Không thiết kế API cho phép nhảy đến `page=1000` bằng offset như SQL. Nếu cần điều kiện đọc động mà vẫn đúng khóa, có thể dùng `CassandraTemplate` với `Query` và `Criteria`; nhưng template vẫn bị ràng buộc bởi thiết kế partition.

### Kiểm tra dữ liệu ngay tại tầng ứng dụng

Trước khi gọi repository, service nên:

- Xác thực người dùng được xem `tenantId` và `siteId`; Cassandra không tự thực hiện phân quyền nghiệp vụ theo chi nhánh.
- Giới hạn `pageSize`, số bucket được duyệt, khoảng thời gian và số request đồng thời.
- Chuẩn hóa `Instant` đến millisecond khi dùng trong khóa hoặc boundary; xác định rõ chính sách với thời điểm không nằm đúng millisecond.
- Cố định `from`/`to` trong cursor; không dùng thời điểm mới ở mỗi trang.
- Ràng buộc continuation token với điều kiện truy vấn, ký/xác minh token khi cần; không cho client tự thay paging state.

## 10. Đường ghi: bảng mới không tự nhận dữ liệu

Thêm bảng CQL không khiến `alerts_by_site_type_day` tự có dữ liệu từ `events_by_device_day`. Hệ thống phải quyết định **ai tạo projection, khi nào và làm sao khôi phục khi lỗi**.

~~~mermaid
flowchart LR
    A["Sự kiện từ thiết bị"] --> B["Luồng ingest"]
    B --> C["Bảng Q1: events_by_device_day"]
    B --> D{"BATTERY_LOW?"}
    D -- Có --> E["Bảng Q2: alerts_by_site_type_day"]
    D -- Không --> F["Không ghi projection"]
    E --> G["API cảnh báo theo site"]
    C --> H["API lịch sử theo device"]
~~~

Hai row ở Q1 và Q2 thường thuộc **hai partition khác nhau**. Ghi Q1 thành công rồi ghi Q2 thất bại sẽ để lại dữ liệu lệch; ghi Q2 xong nhưng Q1 thất bại cũng có thể xảy ra nếu thực hiện độc lập. Bọc hai lời gọi `repository.save(...)` trong một phương thức Java **không** tạo transaction ACID đa bảng như trong RDBMS.

Để vận hành vững hơn, nên lựa chọn một **nguồn sự kiện có khả năng phát lại** và consumer cập nhật các bảng theo cơ chế at-least-once, idempotent theo khóa sự kiện; hoặc sử dụng CDC/pipeline thích hợp được kiểm chứng. Ví dụ quy trình:

1. Nhận sự kiện đã qua kiểm tra schema, `tenantId`, `siteId` và thời gian.
2. Ghi vào nguồn bền vững có thể replay; phân phối đến writer Q1 và projector Q2.
3. Projector chỉ tạo row Q2 cho `BATTERY_LOW`, giữ khóa ổn định để retry an toàn.
4. Ghi nhận offset/checkpoint sau khi xử lý thành công theo cơ chế của pipeline; có retry, dead-letter và reconciliation phù hợp.
5. Giám sát lag, số lần retry, số sự kiện thiếu bản chiếu và tuổi của dữ liệu hiển thị.

Một `LOGGED BATCH` trên nhiều partition có chi phí cao và **không cung cấp isolation/rollback như một transaction quan hệ**; không nên dùng như giải pháp mặc định để “đồng bộ mọi bảng”. Việc chọn batch, CDC hay event log cần dựa trên nhu cầu atomicity, thứ tự sự kiện và khả năng vận hành.

**Độ mới của projection** là một yêu cầu riêng. Đặt consistency `LOCAL_QUORUM` cho đọc/ghi từng bảng giúp cải thiện đảm bảo ở **replica của cùng dữ liệu**, nhưng không làm Q2 xuất hiện ngay khi Q1 vừa ghi xong nếu projector đang chậm.

## 11. Các tình huống nghiệp vụ dễ bị bỏ sót

### Sự kiện đến muộn hoặc sai thứ tự

Thiết bị mất kết nối và gửi bù sự kiện từ hôm qua. Nếu hệ thống chọn bucket theo `received_at`, cảnh báo sẽ xuất hiện sai ngày so với trục thời gian nghiệp vụ. Ở đây đã chốt **theo `event_time` UTC**, nên projector phải xác định `event_day` từ `event_time`.

Timestamp trong Cassandra có độ chính xác millisecond. Nếu hai event khác nhau trùng millisecond, cặp `device_id`/`event_id` giúp tách row. Nếu một nguồn retry cùng sự kiện nhưng đổi timestamp hoặc ID, cần chuẩn hóa và deduplicate từ tầng ingest.

### Thiết bị chuyển chi nhánh

Giả sử thiết bị D thuộc site A khi sự kiện xảy ra, nhưng hôm nay chuyển sang site B. Với hợp đồng “site **tại thời điểm sự kiện**”, row projection của sự kiện cũ tiếp tục thuộc A. Nếu product muốn lịch sử tái quy về site hiện tại, đó là **một access pattern khác**: cần thay đổi dữ liệu/đọc hoặc một job di chuyển bản chiếu, không nên âm thầm cập nhật `site_id` của các row cũ.

### Thêm filter trạng thái xử lý

“Chỉ xem cảnh báo **chưa được xác nhận**” nghe giống một điều kiện `WHERE acknowledged = false`. Nhưng `acknowledged` là trạng thái có thể đổi, còn bảng hiện tại được khóa theo site/type/day/time. Nếu đưa trạng thái biến đổi vào partition key, đổi trạng thái thường buộc **xóa row cũ và ghi row mới**, phát sinh tombstone, lỗi đồng bộ và race conditions. Cần đánh giá lại yêu cầu: trạng thái ít thay đổi hay rất thường xuyên, có cần truy vấn theo trạng thái không, có thể giữ index riêng/hàng đợi tác vụ hay không. Đừng thêm một cột rồi giả định Cassandra lọc nó hiệu quả.

### Xóa dữ liệu, retention và TTL

Q1 và Q2 phải có quy tắc retention nhất quán theo yêu cầu pháp lý/sản phẩm. TTL của Cassandra thường tính từ thời điểm **ghi** row, nên sự kiện đến muộn có thể tồn tại lâu hơn thời gian muốn giữ nếu chỉ áp TTL cố định từ lúc ingest. TTL cũng tạo tombstone; chọn compaction và thời gian grace cần dựa trên đặc trưng ghi, sửa, xóa và replica repair.

Khi cần xóa toàn bộ dữ liệu thiết bị hoặc một khách hàng, phải tìm và xóa **mọi bản chiếu có liên quan**, không chỉ Q1. Thiết kế quyền xóa dữ liệu phải có một danh mục các bảng phục vụ truy vấn để không bỏ sót.

### Partition nóng hoặc quá lớn

Nếu một site tạo hàng trăm nghìn cảnh báo/ngày, `(tenant, site, type, day)` có thể trở thành partition quá lớn hoặc hot partition. Cân nhắc bucket theo giờ, hoặc shard có kiểm soát, nhưng mỗi thay đổi sẽ tăng số partition cần truy vấn và độ khó phân trang. Đo thực tế bằng workload đại diện, gồm cả đợt tăng cảnh báo đồng loạt.

## 12. Kế hoạch triển khai thay đổi an toàn

Với một bảng mới, rủi ro lớn nhất thường nằm ở **migration dữ liệu và chuyển luồng đọc**, không phải câu `CREATE TABLE`.

| Giai đoạn | Thực hiện | Dấu hiệu đạt |
| --- | --- | --- |
| 1. Chốt contract | Ký duyệt filter, sort, độ mới, retention, SLO, phân quyền | Ví dụ truy vấn và tiêu chí chấp nhận rõ ràng |
| 2. Đo tải | Thu thập QPS, site lớn nhất, row/ngày, fan-out, dung lượng, p95/p99 | Biết partition có nằm trong ngưỡng đo được không |
| 3. Tạo schema | Tạo bảng Q2, cấu hình RF/consistency theo cluster và migration | Schema sẵn sàng trên môi trường thử nghiệm |
| 4. Triển khai projection | Kết nối ingest/replay/CDC, đo lag và lỗi | Sự kiện mới xuất hiện ở Q2 đúng khóa và thời gian |
| 5. Backfill lịch sử | Quét lịch sử Q1 **theo các partition đã biết**; dùng metadata phù hợp để tránh truy vấn toàn cluster; ghi Q2 có kiểm soát tốc độ | Bù đủ khoảng lịch sử cần phục vụ, có checkpoint |
| 6. Đối soát | So sánh sự kiện nguồn với projection theo sample/site/day, kiểm tra duplicate/missing | Sai khác trong ngưỡng thỏa thuận |
| 7. Shadow read/canary | Chạy API mới cho nội bộ rồi nhóm nhỏ; đo latency, error, tombstone, lag | Đạt SLO và tính đúng |
| 8. Chuyển traffic | Bật feature flag có thể rollback về API cũ hoặc tạm tắt màn hình mới | Có runbook và dashboard theo dõi |
| 9. Dọn nợ kỹ thuật | Đảm bảo worker retry, retention, alert và chi phí vận hành ổn định | Ownership vận hành rõ ràng |

**Backfill cần chú ý:** Q1 chia dữ liệu theo tenant–device–day, nên không thể lấy toàn bộ sự kiện của một site chỉ bằng một `WHERE site_id = ...`. Công việc backfill phải có nguồn danh sách thiết bị/partition có kiểm soát hoặc pipeline sự kiện lịch sử. Tránh dùng `SELECT *` toàn cluster và tránh nhiều lần `COUNT(*)` trên partition lớn để so sánh số lượng.

**Trình tự an toàn:** tạo bảng Q2 → bật nguồn ghi cho dữ liệu mới → bù dữ liệu cũ → đối soát → mở đọc cho người dùng. Nếu backfill và luồng mới chạy đồng thời, cần khóa sự kiện ổn định để viết lại cùng row, và checkpoint để tiếp tục sau lỗi. Khi có sửa/xóa trong thời gian backfill, cần định nghĩa cách reconciliation cập nhật trạng thái cuối cùng.

## 13. Kiểm thử cần chứng minh điều gì?

Các tình huống sau kiểm tra **đúng access pattern** thay vì chỉ xác nhận phương thức repository trả về dữ liệu:

| Thử nghiệm | Kỳ vọng |
| --- | --- |
| Hai thiết bị cùng site phát `BATTERY_LOW` trong một ngày | Cả hai xuất hiện trong timeline site, sắp theo `event_time` |
| Hai tenant có cùng `site_id` tình cờ | Dữ liệu bị tách nhờ `tenant_id` trong partition key và kiểm tra quyền ở API |
| Sự kiện tới đúng 00:00 UTC | Được ghi vào bucket ngày mới |
| Cửa sổ 24h qua hai ngày UTC | API đọc hai partition, không bỏ sót ranh giới và không nhân đôi |
| Hai cảnh báo có cùng millisecond | Tie-breaker ổn định và row không ghi đè nhau |
| Gửi lại cùng event | Không tạo row trùng khi bộ khóa không đổi |
| Q1 ghi thành công nhưng Q2 tạm lỗi | Pipeline retry/replay bổ sung được projection; có đo lag |
| Site có sự kiện tăng đột biến | Độ trễ, partition size và compaction vẫn trong mức chấp nhận hoặc có phương án chia bucket |
| Client đổi filter nhưng giữ cursor cũ | API từ chối cursor, không trộn trạng thái phân trang |
| Người dùng không có quyền trên site | Bị từ chối trước truy vấn dữ liệu |
| TTL hết hạn hoặc yêu cầu xóa dữ liệu | Các bảng projection liên quan đều tuân thủ chính sách retention/xóa |

Nên kiểm thử với **nhiều thiết bị, nhiều partition, sự kiện tới muộn và lưu lượng cao**. Một vài row chạy đúng trên máy cục bộ không chứng minh schema đã phù hợp tải sản xuất. Với bảng đọc định hướng time series, tập trung theo dõi p95/p99, timeout, page size, số partition truy vấn, dropped mutations, tombstone scan, compaction backlog và projection lag.

## 14. Mẫu phiếu đánh giá trước khi chấp nhận một access pattern

Mỗi yêu cầu bổ sung màn hình hoặc bộ lọc nên có một bản ghi ngắn, có thể gửi review:

~~~text
Tên truy vấn: Q2 — BATTERY_LOW gần nhất theo site
Chủ sở hữu nghiệp vụ: Đội vận hành
Đầu vào: tenantId, siteId, eventType, from, to, cursor
Dữ liệu trả về: 50 bản ghi/trang, eventTime DESC
Giới hạn: tối đa 24h/truy vấn, retention 30 ngày
Độ mới dữ liệu: <= 10 giây (mục tiêu giả định)
SLO: p95 <= 300 ms (mục tiêu giả định)
Bảng nguồn: events_by_device_day
Bảng đọc đề xuất: alerts_by_site_type_day
Partition key mới: (tenant_id, site_id, event_type, event_day)
Clustering key: event_time DESC, device_id ASC, event_id ASC
Ghi bổ sung: chỉ sự kiện BATTERY_LOW
Phân trang: paging state mỗi bucket + cursor API
Rủi ro: projector lag, dữ liệu muộn, hot partition, backfill
Đo lường: QPS, latency, lag, sai khác đối soát, dung lượng
Điều kiện rollout: backfill đạt, có dashboard/rollback
Điều kiện xem lại thiết kế: thêm filter hoặc vượt ngưỡng tải
~~~

Bản đánh giá nên chỉ rõ **mẫu truy vấn nào được hỗ trợ** và mẫu nào chưa được hỗ trợ. Điều này giúp tránh dùng nhầm một bảng có tên nghe gần đúng nhưng partition key lại phục vụ một câu hỏi khác.

## 15. Bài tập thực hành

**Bài A — Phát hiện thay đổi mẫu truy vấn.** Với bảng Q1, product muốn xem “10 thiết bị phát sinh nhiều `DISCONNECTED` nhất trên toàn hệ thống trong tuần”. Hãy giải thích vì sao Q1 không phù hợp để trả một câu trả lời nhanh; phân biệt nhu cầu thống kê/top-N với nhu cầu timeline và đề xuất kiến trúc aggregate hoặc OLAP hợp lý.

**Bài B — Thử một access pattern khác.** Product đổi Q2 thành “mọi loại cảnh báo của một site, không chọn `eventType`”. Hãy thiết kế lại partition key hoặc trình bày cách fan-out trên tập loại nhỏ; ước lượng số partition cần đọc trong 24 giờ và những thay đổi ở API cursor.

**Bài C — Lập kế hoạch vận hành.** Cho site có 100.000 cảnh báo mỗi ngày, row projection trung bình 700 byte, retention 30 ngày, RF=3. Ước lượng dung lượng dữ liệu thô và dung lượng sao lưu theo RF (chưa tính overhead); đề xuất tiêu chí đo để quyết định bucket ngày hay giờ. Đừng dùng chỉ kích thước row trung bình để kết luận partition an toàn.

**Bài D — Tình huống lỗi.** Hệ thống ghi Q1 thành công nhưng projector Q2 dừng trong 45 phút. Hãy mô tả cách phát hiện độ trễ, replay idempotent, đối soát và điều kiện bật lại trang cảnh báo. Nêu khác biệt giữa đảm bảo đọc consistency của một bảng và tính đầy đủ của hai bảng do pipeline khác nhau cập nhật.

**Tiêu chí hoàn thành:** người học xác định rõ thay đổi trong input/filter/sort, tìm đúng partition key cho từng truy vấn, ước lượng chi phí đọc và ghi, nhận diện rủi ro đồng bộ/backfill, đồng thời trình bày kế hoạch kiểm chứng trước khi đưa tính năng lên sản xuất.

## Tài liệu tham khảo

- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/cql_singlefile.html): khóa phân vùng, clustering order và truy vấn.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): mô hình dữ liệu phục vụ access pattern.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): khóa chính tổng hợp và entity mapping.
- [Spring Data Cassandra — Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): `@Query`, repository và paging.
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): truy vấn bằng template và criteria.
