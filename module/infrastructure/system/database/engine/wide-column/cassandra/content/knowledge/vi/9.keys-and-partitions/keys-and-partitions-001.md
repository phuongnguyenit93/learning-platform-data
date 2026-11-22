# Quan hệ giữa primary key, partition key và clustering column

Trong Apache Cassandra, `PRIMARY KEY` vừa định danh một hàng dữ liệu, vừa quyết định **dữ liệu được phân phối đến đâu** và **các hàng trong cùng phân vùng được sắp xếp như thế nào**. Đây là khác biệt quan trọng so với cách thường hiểu khóa chính trong cơ sở dữ liệu quan hệ.

Sau bài học, bạn có thể:

- Phân biệt `primary key`, `partition key` và `clustering column` qua cú pháp CQL.
- Giải thích vì sao các hàng có cùng partition key nằm trong cùng một phân vùng logic và được lưu trên cùng tập replica.
- Viết bảng theo truy vấn, đặc biệt là truy vấn theo một thực thể và một khoảng thời gian.
- Nhận ra những thiết kế gây phân vùng quá lớn, phân bố tải không đều hoặc không hỗ trợ truy vấn dự kiến.

## 1. Ba khái niệm liên quan với nhau như thế nào?

Một bảng Cassandra có một `PRIMARY KEY`, gồm **partition key bắt buộc** và **không hoặc nhiều clustering column**:

```text
PRIMARY KEY = partition key + [clustering column 1, clustering column 2, ...]
               |                         |
               |                         +-- Xác định và sắp thứ tự hàng
               +-- Xác định phân vùng và vị trí phân phối
```

| Thành phần | Chức năng | Phạm vi tác động |
| --- | --- | --- |
| **Primary key** | Định danh duy nhất một hàng logic; gồm toàn bộ partition key và clustering columns (nếu có). | Toàn bảng. |
| **Partition key** | Tạo giá trị khóa phân vùng; Cassandra tính token để xác định các replica chịu trách nhiệm lưu phân vùng. | Phân phối dữ liệu giữa các node/replica. |
| **Clustering column** | Phân biệt các hàng trong cùng phân vùng và quyết định thứ tự sắp xếp của chúng. | Bên trong một phân vùng. |

**Quy tắc nhận diện từ CQL:**

```sql
-- Một cột làm partition key, không có clustering column.
PRIMARY KEY (user_id)

-- user_id là partition key; created_at là clustering column.
PRIMARY KEY (user_id, created_at)

-- Partition key ghép gồm tenant_id và user_id;
-- created_at là clustering column.
PRIMARY KEY ((tenant_id, user_id), created_at)

-- Partition key ghép gồm hai cột;
-- created_at và event_id là hai clustering columns theo thứ tự.
PRIMARY KEY ((tenant_id, user_id), created_at, event_id)
```

Các dấu ngoặc **có ý nghĩa ngữ nghĩa**, không chỉ để trình bày:

- `PRIMARY KEY (tenant_id, user_id, created_at)` có partition key là **`tenant_id`**; `user_id` và `created_at` là clustering columns.
- `PRIMARY KEY ((tenant_id, user_id), created_at)` có partition key ghép **`(tenant_id, user_id)`**; chỉ `created_at` là clustering column.

Hai khai báo này cho phép những kiểu truy vấn và tạo ra cách phân bố dữ liệu rất khác nhau.

> **Ghi nhớ:** `primary key` là toàn bộ tọa độ của một hàng; `partition key` chọn phân vùng; `clustering columns` chọn vị trí của hàng *bên trong* phân vùng đó.

## 2. Từ partition key đến phân vùng và replica

Cassandra là cơ sở dữ liệu wide-column phân tán. Mỗi **giá trị partition key hoàn chỉnh** tương ứng với một phân vùng logic. Với partition key ghép, phải xét *tổ hợp* tất cả các thành phần, không chỉ từng thành phần riêng lẻ.

Ví dụ, giả sử partition key là `(tenant_id, device_id, event_day)`:

```text
(acme, device-01, 2026-11-21) ── token ──> tập replica phụ trách phân vùng A
     ├─ (08:30, event-01) : nhiệt độ = 38.2
     ├─ (08:20, event-02) : nhiệt độ = 37.9
     └─ (08:10, event-03) : nhiệt độ = 37.7

(acme, device-01, 2026-11-22) ── token ──> tập replica phụ trách phân vùng B
     └─ (09:00, event-04) : nhiệt độ = 38.0

(acme, device-02, 2026-11-21) ── token ──> tập replica phụ trách phân vùng C
     └─ (08:30, event-05) : nhiệt độ = 36.5
```

Tên A/B/C ở đây biểu thị **các phân vùng logic**, không hàm ý chúng chắc chắn được đặt trên các máy chủ khác nhau. Cassandra dùng partitioner (thông dụng là `Murmur3Partitioner`) để ánh xạ partition key sang token; chiến lược replication cùng cấu trúc ring quyết định node nào giữ bản sao. Số replica phụ thuộc vào `replication factor` của keyspace.

Hệ quả trực tiếp:

1. Hai hàng có cùng giá trị của *mọi* thành phần partition key thuộc cùng phân vùng logic và cùng tập replica chịu trách nhiệm.
2. Đổi một thành phần partition key có thể làm token thay đổi, vì vậy hàng có thể nằm ở một tập replica khác.
3. Clustering column **không tham gia xác định token**; nó tổ chức các hàng sau khi đã xác định phân vùng.
4. Phân vùng logic không đồng nghĩa một khối dữ liệu liên tục duy nhất trên đĩa: cơ chế lưu trữ LSM/SSTable có thể trải dữ liệu của phân vùng qua nhiều tệp trước khi compaction.

## 3. Đọc một định nghĩa bảng từ trái sang phải

Xét yêu cầu: một hệ thống IoT cần lấy **20 sự kiện mới nhất của một thiết bị trong một ngày**, hoặc lấy sự kiện của thiết bị ấy trong một khoảng thời gian. Mỗi khách hàng (`tenant`) sở hữu nhiều thiết bị; dữ liệu nhiều ngày phải được giới hạn kích thước phân vùng.

```sql
CREATE TABLE sensor_events_by_device_day (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    timeuuid,
    event_type  text,
    reading     double,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Trong ví dụ này:

| Thành phần | Các cột | Ý nghĩa |
| --- | --- | --- |
| Partition key | `(tenant_id, device_id, event_day)` | Mỗi thiết bị của mỗi tenant có một phân vùng cho mỗi ngày. |
| Clustering column 1 | `event_time` | Sắp sự kiện theo thời điểm, mới nhất trước. |
| Clustering column 2 | `event_id` | Phân biệt những sự kiện có cùng `event_time`; tạo thứ tự phụ. |
| Primary key đầy đủ | `(tenant_id, device_id, event_day, event_time, event_id)` | Định danh một hàng sự kiện. |
| Cột thường | `event_type`, `reading` | Dữ liệu của sự kiện, không tham gia định danh hàng và vị trí phân vùng. |

`CLUSTERING ORDER BY` chỉ định thứ tự vật lý logic khi đọc các hàng theo clustering key. Nếu không khai báo, thứ tự clustering mặc định là tăng dần (`ASC`). Nó không tạo khả năng sắp xếp tùy ý trên các cột thường.

Thử ghi hai sự kiện cùng thiết bị, cùng ngày và cùng thời điểm đo:

```sql
INSERT INTO sensor_events_by_device_day (
    tenant_id, device_id, event_day,
    event_time, event_id, event_type, reading
) VALUES (
    'acme', a14d4f48-5ca8-4c4e-9b13-3c9680cdb993, '2026-11-21',
    '2026-11-21T08:30:00+0700', now(), 'temperature', 38.2
);

INSERT INTO sensor_events_by_device_day (
    tenant_id, device_id, event_day,
    event_time, event_id, event_type, reading
) VALUES (
    'acme', a14d4f48-5ca8-4c4e-9b13-3c9680cdb993, '2026-11-21',
    '2026-11-21T08:30:00+0700', now(), 'temperature', 38.3
);
```

Hàm `now()` của CQL tạo một giá trị `timeuuid` mới cho `event_id`, nên hai lệnh có thể tạo hai hàng riêng dù trùng `event_time`. Với hệ thống thực, nếu cần chống ghi lặp do retry, nên dùng một `event_id` ổn định do phía ứng dụng cung cấp thay vì sinh ID mới ở mỗi lần thử lại.

Nếu ghi lại **đúng cùng tổ hợp primary key**, Cassandra cập nhật/ghi đè giá trị các cột của **cùng hàng logic** theo quy tắc xung đột dựa trên timestamp của các bản ghi; nó không tạo thêm hàng mới. Vì vậy, thêm clustering column chỉ để đủ tính duy nhất cần xuất phát từ định danh sự kiện thực sự.

## 4. Primary key quyết định truy vấn nào hiệu quả

Điểm xuất phát là chọn đúng phân vùng bằng **đầy đủ partition key**, rồi dùng clustering column để giới hạn hoặc sắp xếp kết quả bên trong phân vùng.

### Lấy các sự kiện mới nhất của thiết bị trong ngày

```sql
SELECT event_time, event_id, event_type, reading
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = a14d4f48-5ca8-4c4e-9b13-3c9680cdb993
  AND event_day = '2026-11-21'
LIMIT 20;
```

Vì schema đã khai báo `event_time DESC, event_id DESC`, kết quả trong phân vùng được đọc theo thứ tự đó. Cassandra không cần quét mọi thiết bị hoặc sắp xếp toàn bộ bảng để tìm 20 sự kiện đầu tiên của phân vùng này.

### Lấy sự kiện trong một khoảng thời gian

```sql
SELECT event_time, event_id, event_type, reading
FROM sensor_events_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = a14d4f48-5ca8-4c4e-9b13-3c9680cdb993
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00+0700'
  AND event_time <  '2026-11-21T09:00:00+0700';
```

Truy vấn sử dụng điều kiện bằng trên toàn bộ partition key và điều kiện khoảng trên clustering column đầu tiên. Nếu cần truy vấn **nhiều ngày**, ứng dụng có thể đọc từng bucket ngày phù hợp rồi tổng hợp kết quả, hoặc tạo thêm bảng phù hợp với kiểu truy vấn liên ngày.

### Những truy vấn không khớp khóa

Với bảng vừa tạo, các mẫu sau **không phải đường truy cập phân vùng thông thường**:

```sql
-- Thiếu hai thành phần của partition key ghép:
SELECT * FROM sensor_events_by_device_day
WHERE tenant_id = 'acme';

-- Không xác định partition key; event_type chỉ là cột thường:
SELECT * FROM sensor_events_by_device_day
WHERE event_type = 'temperature';
```

Nếu không có cơ chế chỉ mục phù hợp, Cassandra thường từ chối các truy vấn này do phải lọc rộng. `ALLOW FILTERING` có thể cho phép một số trường hợp nhưng dễ gây quét nhiều dữ liệu và độ trễ khó dự đoán; **không nên coi đó là cách sửa một mô hình khóa không phù hợp**. Khi cần truy vấn sự kiện theo loại trên toàn tenant, hãy thiết kế một bảng truy vấn riêng hoặc đánh giá chỉ mục phù hợp với dữ liệu và phiên bản Cassandra đang dùng.

Đối với `ORDER BY` trong CQL, các cột được sắp xếp phải là clustering columns theo trật tự khóa được hỗ trợ; thao tác này hữu ích nhất khi đã chọn đúng phân vùng. Nó không thay thế `ORDER BY` tùy ý trên một tập hàng rải khắp cluster như trong SQL quan hệ.

## 5. Điều gì tạo nên tính duy nhất của hàng?

Xét ba bản ghi của cùng thiết bị và cùng ngày:

| `event_time` | `event_id` | Kết quả |
| --- | --- | --- |
| `08:30:00` | `id-A` | Hàng 1. |
| `08:30:00` | `id-B` | Hàng 2, vì khác clustering key `event_id`. |
| `08:30:00` | `id-A` | Cùng primary key với hàng 1; là ghi vào hàng 1, không phải hàng 3. |

Cần phân biệt **tính duy nhất của primary key** với một ràng buộc nghiệp vụ. Cassandra không tự đảm bảo rằng các `event_id` trong *những phân vùng khác nhau* là duy nhất toàn hệ thống: nếu `event_id` không phải toàn bộ primary key, hai hàng ở hai phân vùng có thể trùng giá trị này. Muốn thực thi ràng buộc duy nhất ở phạm vi khác, cần thiết kế khóa, quy trình ghi hoặc cơ chế phối hợp phù hợp.

Các cột thuộc primary key không được có giá trị `null` trong khóa của hàng được ghi. Thay đổi khóa chính nghĩa là thay đổi tọa độ hàng: thường phải ghi một hàng mới ở khóa mới và, nếu cần, xóa hàng cũ. `UPDATE` chỉ dùng để thay giá trị các cột không thuộc primary key của hàng đã được xác định bởi khóa.

## 6. Chọn partition key: cân bằng tốc độ truy vấn và phân bố tải

Một partition key tốt cần đồng thời thỏa hai mục tiêu:

1. **Khớp kiểu truy vấn chủ lực:** các điều kiện thường có mặt trong `WHERE` phải xác định được partition key mà không quét toàn bộ cluster.
2. **Giữ phân vùng và tải ở mức hợp lý:** không để một giá trị khóa thu gom dữ liệu vô hạn hoặc nhận phần lớn lưu lượng ghi/đọc.

Giả sử một thiết bị phát sinh 1.000 sự kiện mỗi ngày, dữ liệu có kích thước trung bình 1 KiB/sự kiện (chỉ là giả định minh họa, chưa tính metadata, tombstone và nén):

| Thiết kế partition key | Quy mô logic ước tính | Nhận xét |
| --- | --- | --- |
| `(tenant_id, device_id)` | Khoảng 365.000 hàng, tương đương 356 MiB sau một năm. | Phân vùng lớn dần theo thời gian, khó giới hạn. |
| `(tenant_id, device_id, event_day)` | Khoảng 1.000 hàng, tương đương 0,98 MiB mỗi ngày. | Khoanh vùng dữ liệu theo ngày; dễ đọc lịch sử theo ngày. |
| `(tenant_id, device_id, event_time)` | Gần như mỗi sự kiện một phân vùng. | Dễ phân tán nhỏ lẻ nhưng mất lợi thế đọc chuỗi thời gian theo một phân vùng. |

Các con số chỉ mô tả lượng dữ liệu giả định; kích thước SSTable thực tế còn phụ thuộc kiểu cột, số lần cập nhật/xóa, tombstone, compression và compaction. Bucket theo giờ, ngày hoặc tháng phải chọn theo **lưu lượng và nhu cầu đọc thực tế**, không có kích thước bucket tối ưu cho mọi hệ thống.

Một thiết kế tưởng hợp lý nhưng dễ tạo **hot partition** là:

```sql
PRIMARY KEY (tenant_id, device_id, event_time)
```

Ở đây chỉ `tenant_id` là partition key. Nếu một tenant rất lớn, tất cả sự kiện của tenant đó cùng rơi vào một phân vùng, bất kể số thiết bị; các cột `device_id` và `event_time` chỉ là clustering columns. Muốn phân vùng theo từng thiết bị/ngày, cần viết:

```sql
PRIMARY KEY ((tenant_id, device_id, event_day), event_time, event_id)
```

Tăng `replication factor` không tự chia một phân vùng quá lớn thành nhiều phân vùng độc lập; bản sao vẫn chịu cùng khối lượng dữ liệu logic. Muốn tránh hotspot, cần sửa cách chọn partition key hoặc bucket theo nhu cầu truy cập.

## 7. Các lỗi thiết kế thường gặp

| Dấu hiệu | Nguyên nhân liên quan đến khóa | Hướng xử lý |
| --- | --- | --- |
| Đọc toàn tenant chậm, một số node quá tải | Chỉ dùng `tenant_id` làm partition key dù tenant có lượng dữ liệu lớn. | Thêm thành phần phân vùng hợp lý theo thực thể, thời gian hoặc bucket. |
| Truy vấn theo `device_id` nhưng schema yêu cầu `tenant_id` và `event_day` | Thiếu thành phần partition key trong truy vấn. | Bảo đảm ứng dụng biết đủ khóa, hoặc thiết kế bảng khác cho truy vấn đó. |
| Hai sự kiện cùng timestamp bị hợp nhất | Primary key chỉ có `event_time` làm clustering column. | Thêm định danh sự kiện ổn định như `event_id` vào clustering key. |
| Cần tìm theo `event_type` nhưng phải `ALLOW FILTERING` | `event_type` không nằm trên đường truy cập bằng partition/clustering key. | Thiết kế bảng theo truy vấn hoặc đánh giá chỉ mục thích hợp. |
| Dữ liệu tăng mãi trong một partition | Không có bucket thời gian hoặc bucket không đủ nhỏ. | Chia theo ngày/giờ/tháng tùy tốc độ phát sinh và yêu cầu đọc. |
| Mỗi sự kiện nằm ở một partition riêng dù thường đọc theo dải thời gian | Đưa timestamp có độ phân biệt cao vào partition key. | Giữ định danh thực thể/bucket trong partition key; đặt timestamp ở clustering column. |

Trong Cassandra, **thay đổi cấu trúc primary key thường đòi hỏi tạo bảng mới, ghi chuyển dữ liệu và chuyển luồng đọc/ghi**, chứ không chỉ `ALTER TABLE` để thay khóa. Vì vậy nên xác định truy vấn và ước lượng kích thước phân vùng trước khi triển khai.

## 8. Tự kiểm tra bằng một ví dụ khác

Cho bảng lưu đơn hàng theo khách hàng:

```sql
CREATE TABLE orders_by_customer (
    tenant_id    text,
    customer_id  uuid,
    created_at   timestamp,
    order_id     uuid,
    amount       decimal,
    PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Hãy tự trả lời trước khi xem gợi ý:

1. Hai đơn hàng cùng `tenant_id`, cùng `customer_id`, khác `created_at` có thuộc cùng phân vùng không?
2. Hai đơn hàng cùng `customer_id` nhưng khác `tenant_id` có chắc thuộc cùng phân vùng không?
3. Truy vấn lịch sử đơn hàng của **một** khách hàng trong khoảng `created_at` có phù hợp với schema không?
4. Có thể chỉ dùng `WHERE created_at >= ...` để đọc tất cả đơn hàng mới nhất trên mọi tenant một cách hiệu quả bằng bảng này không?

**Đáp án:** (1) Có, vì partition key giống nhau; `created_at` chỉ ảnh hưởng thứ tự/hàng. (2) Không, vì `tenant_id` là một phần partition key. (3) Có, khi cung cấp `tenant_id` và `customer_id` rồi lọc khoảng trên `created_at`. (4) Không; truy vấn toàn cục theo thời gian cần thiết kế đường truy cập khác.

## 9. Nguyên tắc mang vào thực hành

- Đọc cú pháp `PRIMARY KEY`: **cặp ngoặc trong cùng** xác định partition key ghép; các cột phía sau là clustering columns.
- Chọn partition key theo điều kiện truy vấn và giới hạn kích thước/tải phân vùng; phân phối token xảy ra theo **toàn bộ** partition key.
- Chọn clustering columns để định danh các hàng trong phân vùng và hỗ trợ đọc theo thứ tự/khoảng; thứ tự clustering có ý nghĩa.
- Cùng một primary key là cùng một hàng logic. Muốn nhiều sự kiện trùng timestamp, cần thêm cột phân biệt vào khóa.
- Cassandra khuyến khích **thiết kế bảng theo truy vấn**. Các kiểu truy cập khác biệt có thể cần bảng dữ liệu phục vụ truy vấn riêng, thay vì cố viết một bảng để đáp ứng mọi `WHERE` và `ORDER BY`.

Hiểu đúng ba loại khóa này là nền tảng để học tiếp về token, replication, mức nhất quán đọc/ghi, phân vùng quá lớn, compaction và vận hành Cassandra trong ứng dụng Java.
