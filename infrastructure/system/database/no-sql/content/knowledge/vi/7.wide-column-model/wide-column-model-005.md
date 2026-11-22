# Chia nhóm theo thời gian hoặc miền dữ liệu để giới hạn phân vùng

Trong các hệ cơ sở dữ liệu thuộc **mô hình cột rộng** (*wide-column*), đặc biệt khi thiết kế bảng theo phong cách **Apache Cassandra**, một quyết định rất quan trọng là: **mỗi phân vùng (*partition*) sẽ chứa những hàng nào, có thể phát triển lớn đến đâu và có bao nhiêu yêu cầu cùng truy cập vào nó?**

Nếu đưa toàn bộ lịch sử sự kiện của một thiết bị, mọi đơn hàng của một khách hàng hoặc toàn bộ dữ liệu của một tenant vào **một phân vùng không có giới hạn theo thời gian**, phân vùng đó có thể tăng mãi. Mỗi lần đọc, ghi, compaction hoặc phục hồi sẽ ngày càng khó quản lý. Ngược lại, chia dữ liệu thành quá nhiều phân vùng nhỏ khiến truy vấn phải gửi yêu cầu tới nhiều nơi và ghép kết quả.

**Chia nhóm theo thời gian** (*time bucketing*) và **chia nhóm theo miền dữ liệu** (*domain bucketing*) là hai kỹ thuật đưa một thành phần phân nhóm vào khóa phân vùng. Nhờ vậy, mỗi phân vùng chỉ giữ một phạm vi dữ liệu có thể dự đoán được. Hai kỹ thuật thường được kết hợp, chẳng hạn: **một thiết bị + một ngày** hoặc **một tenant + một dự án + một tháng**.

Bài học dùng Cassandra Query Language (**CQL**) làm ví dụ để giải thích partition key và clustering columns. Hệ wide-column khác như Bigtable hoặc HBase có API, cách tổ chức hàng và thuật ngữ riêng; không nên áp dụng nguyên xi cú pháp hay hành vi của Cassandra cho mọi sản phẩm.

## 1. Phân vùng trong mô hình cột rộng

Ở Cassandra, **khóa chính** (*primary key*) xác định:

- **Partition key:** một hoặc nhiều cột dùng để định vị phân vùng logic và phân phối dữ liệu trong cụm.
- **Clustering columns:** các cột dùng để định danh và tổ chức thứ tự hàng **bên trong cùng một phân vùng**.

Ví dụ:

~~~sql
CREATE TABLE readings_by_device (
    device_id text,
    measured_at timestamp,
    reading_id timeuuid,
    temperature_c double,
    PRIMARY KEY ((device_id), measured_at, reading_id)
) WITH CLUSTERING ORDER BY (measured_at DESC, reading_id DESC);
~~~

Trong bảng này:

- `device_id` là **partition key**.
- `measured_at` và `reading_id` là **clustering columns**.
- Mọi điểm đo của `device_id = 'sensor-17'` nằm trong **cùng một phân vùng logic**, được tổ chức theo các clustering columns.
- `reading_id` giúp phân biệt các điểm đo có cùng timestamp; mã phải được tạo duy nhất theo quy tắc ứng dụng.

~~~text
Partition: device_id = sensor-17
  ├── 2026-11-14 10:03:00Z / event-A → 28.4°C
  ├── 2026-11-14 10:02:00Z / event-B → 28.3°C
  ├── 2026-11-14 10:01:00Z / event-C → 28.1°C
  ├── ... (nhiều tháng dữ liệu)
  └── ... (nhiều năm dữ liệu)
~~~

Một truy vấn lấy điểm đo gần nhất của `sensor-17` khá tự nhiên vì biết partition key và thứ tự clustering. Nhưng nếu thiết bị hoạt động liên tục, phân vùng có thể tăng rất lớn, dù phần lớn truy vấn chỉ cần vài giờ hoặc vài ngày gần đây.

### Phân vùng logic khác file lưu trữ và node

Một phân vùng logic không nhất thiết được lưu thành một tệp riêng. Cassandra có thể lưu dữ liệu của phân vùng qua nhiều SSTable, dùng bộ nhớ đệm, compaction và nhân bản dữ liệu giữa các node. Partition key được dùng trong cơ chế phân phối dữ liệu; trong các hệ khác, cách phân phối có thể khác.

Do đó, khi nói “giới hạn phân vùng”, mục tiêu là **giới hạn số hàng/dung lượng và lưu lượng tập trung của một đơn vị dữ liệu logic**, đồng thời giảm số phân vùng phải đọc cho các mẫu truy vấn quan trọng. Không có một kích thước phân vùng lý tưởng chung cho mọi DBMS, phần cứng hay workload.

## 2. Vì sao phân vùng không giới hạn là vấn đề?

Giả sử một thiết bị ghi 20 điểm đo mỗi giây, không ngừng trong nhiều tháng. Nếu mỗi điểm được gắn vào cùng partition `device_id`, số hàng tăng mãi:

~~~text
Một ngày:
    20 điểm/giây × 86.400 giây = 1.728.000 điểm

Một tháng 30 ngày:
    1.728.000 × 30 = 51.840.000 điểm

Sau một năm 365 ngày:
    1.728.000 × 365 = 630.720.000 điểm
~~~

Các con số này chỉ là phép tính số điểm đo, chưa bao gồm độ rộng bản ghi, index, metadata, tombstone, nén, nhân bản hoặc biến thiên thực tế của tải.

Một phân vùng phát triển quá lớn có thể dẫn đến:

1. **Đọc dài hơn cần thiết:** truy vấn phải xem nhiều hàng hoặc nhiều phần lưu trữ liên quan; các truy vấn không lọc đúng clustering range có thể đặc biệt tốn kém.
2. **Tăng chi phí duy trì:** compaction, streaming, repair và vận hành với dữ liệu lớn có thể khó khăn hơn tùy DBMS và cấu hình.
3. **Tồn lưu dữ liệu đã xóa/hết hạn:** với hệ dùng tombstone, truy vấn rộng và chính sách TTL không phù hợp có thể khiến chi phí đọc tăng.
4. **Phân bố tải lệch:** một partition có lưu lượng đọc hoặc ghi rất cao có thể trở thành **hot partition**, dù cụm có nhiều node.
5. **Khó thực hiện chính sách vòng đời:** khi dữ liệu có thời gian giữ khác nhau nhưng nằm trộn trong một phân vùng khổng lồ, việc vận hành và truy vấn lịch sử phức tạp hơn.

Điều quan trọng là **phân vùng lớn** và **phân vùng nóng** không hoàn toàn giống nhau. Một phân vùng lưu nhiều năm dữ liệu nhưng hiếm được đọc có thể lớn mà không nóng; một phân vùng chỉ chứa vài nghìn hàng nhưng nhận hàng chục nghìn yêu cầu/giây vẫn có thể nóng.

## 3. Ý tưởng chung của bucketing

Thay vì dùng:

~~~text
partition_key = device_id
~~~

ta đưa vào một thành phần phân nhóm:

~~~text
partition_key = (device_id, bucket)
~~~

Trong đó `bucket` được tính theo một quy tắc **xác định, nhất quán** từ dữ liệu và mẫu truy cập. Ví dụ:

- Theo thời gian: `2026-11-14`, `2026-W46`, `2026-11` hoặc khoảng 10:00–10:59 UTC.
- Theo miền: `tenantId`, `projectId`, `siteId`, `regionId`, `deviceId`.
- Kết hợp: `(tenantId, deviceId, day)`.
- Với một nhóm quá nóng: thêm `shardId` được tính từ một giá trị phù hợp.

~~~text
Không chia bucket:
  device=sensor-17
       └── [mọi dữ liệu từ trước tới nay]  → lớn dần

Chia theo ngày:
  device=sensor-17, day=2026-11-12
       └── [dữ liệu ngày 12]
  device=sensor-17, day=2026-11-13
       └── [dữ liệu ngày 13]
  device=sensor-17, day=2026-11-14
       └── [dữ liệu ngày 14]
~~~

Nhờ có bucket, hệ thống có thể dự tính số hàng mỗi phân vùng. Tuy nhiên, điều này chỉ hiệu quả khi **mỗi bucket thật sự có giới hạn hợp lý**. Nếu mọi khách hàng trên toàn hệ thống cùng ghi vào partition `day=2026-11-14`, vẫn có thể tạo một partition khổng lồ hoặc quá nóng.

## 4. Chia theo thời gian: ngày, giờ, tuần hay tháng?

**Time bucketing** thêm một khoảng thời gian đã được làm tròn/chuẩn hóa vào khóa phân vùng. Với một sự kiện có thời điểm `occurred_at`, có thể xác định:

~~~text
time bucket theo ngày UTC:
  2026-11-14T00:00:00Z đến trước 2026-11-15T00:00:00Z
    → bucket_day = 2026-11-14

time bucket theo giờ UTC:
  2026-11-14T10:00:00Z đến trước 2026-11-14T11:00:00Z
    → bucket_hour = 2026-11-14T10
~~~

Với dữ liệu tần suất thấp, bucket theo tháng có thể đủ. Với dữ liệu tần suất rất cao, bucket theo giờ hoặc ngắn hơn có thể cần thiết. **Độ rộng bucket là quyết định theo tải và mẫu truy vấn**, không phải quy tắc “cột rộng luôn chia theo ngày”.

### Công thức ước lượng ban đầu

Gọi:

- `r`: số bản ghi trung bình mỗi giây của **một nhóm domain** (ví dụ một thiết bị).
- `T`: số giây trong một bucket.
- `s`: số byte ước lượng cho một bản ghi ở mức dữ liệu logic.

Ta có ước lượng:

\[
N_{\text{bucket}}\approx rT
\]

\[
B_{\text{logical}}\approx rTs
\]

Đây là phép ước lượng **dung lượng logic** và số hàng để bắt đầu thiết kế; không phải dự báo dung lượng SSTable trên đĩa. Dung lượng và tải thực tế còn chịu ảnh hưởng của clustering columns, overhead lưu trữ, nén, TTL, tombstone, replication và cách DBMS tổ chức dữ liệu.

**Ví dụ:** một thiết bị phát 20 bản ghi/giây, trung bình mỗi bản ghi có payload khoảng 1 KiB:

| Độ rộng bucket | Số bản ghi ước lượng | Dung lượng payload logic |
| --- | ---: | ---: |
| 1 giờ | 72.000 | Khoảng 70 MiB |
| 1 ngày | 1.728.000 | Khoảng 1,65 GiB |
| 30 ngày | 51.840.000 | Khoảng 49,4 GiB |

Một phân vùng theo tháng trong ví dụ này rất lớn về mặt payload logic. Chia theo giờ có thể là điểm khởi đầu để thử tải, nhưng vẫn phải xét phân bố thực tế, giới hạn sản phẩm và mẫu đọc. Không nên lấy một ngưỡng MB cố định làm “quy chuẩn Cassandra” cho mọi hệ thống.

### Bucket càng nhỏ có luôn tốt hơn?

Không. Nếu dashboard cần đọc 7 ngày gần nhất:

- Bucket theo ngày: thường cần đọc **7–8 bucket** tùy biên thời gian.
- Bucket theo giờ: có thể cần đọc **168–169 bucket**.
- Bucket theo phút: có thể cần đọc trên **10.000 bucket**.

Mỗi bucket quá nhỏ có thể giảm kích thước partition nhưng làm tăng số request, metadata, thao tác phân trang và số nguồn kết quả phải hợp nhất. Bài toán là tìm **độ rộng đủ nhỏ để giới hạn kích thước/hotness, nhưng đủ lớn để truy vấn thường gặp chạm ít bucket**.

## 5. Thiết kế bảng Cassandra chia theo ngày

Giả sử hệ thống IoT cần lấy các điểm đo của một thiết bị theo khoảng thời gian. Bảng có thể được thiết kế:

~~~sql
CREATE TABLE readings_by_device_day (
    tenant_id text,
    device_id text,
    bucket_day date,
    measured_at timestamp,
    reading_id timeuuid,
    temperature_c double,
    humidity_percent double,
    PRIMARY KEY (
        (tenant_id, device_id, bucket_day),
        measured_at,
        reading_id
    )
) WITH CLUSTERING ORDER BY (
    measured_at DESC,
    reading_id DESC
);
~~~

Giải thích thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `tenant_id` | Giới hạn miền sở hữu dữ liệu theo tenant trong ứng dụng |
| `device_id` | Nhóm dữ liệu theo thiết bị có ID ổn định |
| `bucket_day` | Chặn phạm vi lịch sử của một partition ở một ngày |
| `measured_at` | Clustering column để đọc theo thời gian trong partition |
| `reading_id` | Phân biệt các lần đo có thể trùng timestamp |
| `temperature_c`, `humidity_percent` | Payload |

Cặp ngoặc kép trong `PRIMARY KEY ((tenant_id, device_id, bucket_day), measured_at, reading_id)` có ý nghĩa: **ba cột trong ngoặc bên trong tạo thành một partition key ghép**. Các cột sau dấu ngoặc bên trong là clustering columns. Nếu bỏ phân biệt này, ứng dụng rất dễ hiểu nhầm cột nào phải được biết để định vị partition.

### Ghi dữ liệu vào bucket tương ứng

Ứng dụng nhận bản đo:

~~~json
{
  "tenantId": "T17",
  "deviceId": "sensor-17",
  "measuredAt": "2026-11-14T10:15:23Z",
  "readingId": "timeuuid-do-client-tao",
  "temperatureC": 28.4,
  "humidityPercent": 70.2
}
~~~

Ứng dụng xác định `bucket_day = 2026-11-14` theo **ngày UTC của `measuredAt`**, rồi ghi:

~~~sql
INSERT INTO readings_by_device_day (
    tenant_id,
    device_id,
    bucket_day,
    measured_at,
    reading_id,
    temperature_c,
    humidity_percent
) VALUES (
    'T17',
    'sensor-17',
    '2026-11-14',
    '2026-11-14T10:15:23Z',
    123e4567-e89b-11d3-a456-426614174000,
    28.4,
    70.2
);
~~~

`reading_id` ở đây là một UUID phiên bản thời gian dùng để minh họa cột kiểu `timeuuid`. Trong ứng dụng thực tế, cần tạo mã hợp lệ và duy nhất theo quy tắc nhập dữ liệu; không dùng lại một ID minh họa cho nhiều bản đo. Nếu một nguồn gửi lại cùng bản đo sau timeout, hãy xác định chính sách **deduplication/idempotency** và sử dụng định danh ổn định tương ứng.

### Truy vấn một ngày

Khi màn hình cần các bản đo của một thiết bị trong khoảng 10:00–11:00 UTC:

~~~sql
SELECT measured_at, reading_id, temperature_c, humidity_percent
FROM readings_by_device_day
WHERE tenant_id = 'T17'
  AND device_id = 'sensor-17'
  AND bucket_day = '2026-11-14'
  AND measured_at >= '2026-11-14T10:00:00Z'
  AND measured_at <  '2026-11-14T11:00:00Z'
LIMIT 100;
~~~

Truy vấn có đủ **partition key** để xác định một partition, sau đó dùng khoảng `measured_at` trên clustering columns. Do bảng được sắp theo `measured_at DESC`, nó phù hợp với thao tác đọc dữ liệu mới nhất trong partition.

Điều kiện `measured_at < end` tạo một **khoảng nửa mở** `[start, end)`, giúp hai cửa sổ thời gian liên tiếp không cùng lấy bản đo tại điểm biên. Quy tắc này cần được giữ nhất quán trong toàn bộ API.

**Điểm cần nhớ:** chỉ lọc `measured_at` mà bỏ `bucket_day` không tự khiến Cassandra tìm được mọi partition có dữ liệu trong thời gian đó. Ứng dụng phải biết bucket tương ứng hoặc dùng một cấu trúc truy cập khác.

## 6. Đọc nhiều bucket: tính đúng kết quả và chi phí fan-out

Giả sử người dùng hỏi **90 phút gần nhất** lúc `2026-11-14T00:30:00Z`. Khoảng cần đọc là:

~~~text
start = 2026-11-13T23:00:00Z
end   = 2026-11-14T00:30:00Z

Bucket ngày:
  2026-11-13  → đọc 23:00–24:00
  2026-11-14  → đọc 00:00–00:30
~~~

Hai partition khác nhau phải được đọc, rồi kết quả được **hợp nhất và sắp xếp** theo `measured_at`. Một query vào `bucket_day = '2026-11-14'` sẽ bỏ sót toàn bộ dữ liệu trước nửa đêm.

Thuật toán ứng dụng có thể được mô tả:

~~~text
readReadings(tenantId, deviceId, start, end):
  1. Chuẩn hóa start/end về UTC, dùng khoảng [start, end).
  2. Xác định danh sách bucket ngày giao với khoảng.
  3. Với mỗi bucket:
       - Query theo đầy đủ tenantId + deviceId + bucket_day.
       - Giới hạn measured_at vào phần giao của bucket và [start, end).
       - Đọc theo trang, tránh lấy toàn bộ lịch sử vào bộ nhớ.
  4. Gộp kết quả của các bucket.
  5. Sắp xếp theo measured_at DESC, reading_id DESC.
  6. Trả trang kết quả kèm thông tin tiếp tục nếu còn dữ liệu.
~~~

Trong một hệ thống có nhiều partition, cần giới hạn số yêu cầu chạy song song để tránh gây tải đột biến. Với truy vấn nhiều bucket, **phân trang không chỉ là CQL paging state của một truy vấn đơn**: API có thể cần giữ tiến độ theo từng bucket, giá trị sắp xếp cuối, giới hạn kết quả và cách ghép khi dữ liệu mới xuất hiện.

### Điểm khó khi lấy “20 sự kiện mới nhất”

Giả sử mỗi bucket đã có thứ tự giảm dần. Muốn lấy **20 sự kiện mới nhất toàn khoảng**, không nên chỉ lấy 20 từ bucket cũ rồi nối vào kết quả bucket mới mà bỏ qua việc so sánh thời điểm giữa các nguồn. Cần chọn top 20 từ các luồng kết quả đã được sắp xếp, có quy tắc phá hòa khi timestamp trùng (ví dụ `reading_id`).

Nếu bucket gần nhất đã có 20 kết quả, truy vấn cũ hơn đôi khi không cần thiết để lấy top 20. Nhưng điều này chỉ đúng khi ranh giới thời gian và thứ tự giữa các bucket bảo đảm rằng không có bản đo của bucket cũ mới hơn bản đo đã lấy; khi dùng event time lệch/không chuẩn, phải kiểm tra lại giả định.

### Bucket không phải transaction snapshot xuyên thời gian

Khi truy vấn nhiều partition, một sự kiện đến muộn hoặc dữ liệu bị cập nhật trong lúc quét có thể làm kết quả giữa các trang không phản ánh đúng cùng một thời điểm. Hãy xác định yêu cầu:

- Dashboard thời gian thực chấp nhận kết quả thay đổi giữa các lần đọc?
- Báo cáo tài chính/kiểm toán cần snapshot đóng băng tại một mốc?
- API có dùng **watermark** và ghi nhận “đã nhận đủ dữ liệu tới thời điểm nào” không?

Không thể suy luận rằng việc chia bucket tự cung cấp snapshot nhất quán trên nhiều partition.

## 7. Chia theo miền dữ liệu: tenant, dự án, thiết bị, khách hàng

**Domain bucketing** phân vùng theo một **miền nghiệp vụ tự nhiên** hoặc một nhóm thuộc tính của miền đó. Ví dụ:

~~~text
(tenant_id, device_id)
(tenant_id, project_id)
(customer_id, order_group)
(region_id, site_id)
~~~

Thay vì đưa tất cả sự kiện của mọi tenant vào một nhóm, mỗi tenant/dự án/thiết bị có phạm vi riêng.

### So sánh những khóa phân vùng có vẻ hợp lý

Hệ thống quản lý hàng triệu thiết bị của nhiều khách hàng có thể cân nhắc:

| Partition key | Ưu điểm | Vấn đề có thể gặp |
| --- | --- | --- |
| `tenant_id` | Lấy dữ liệu trong một tenant dễ định vị | Tenant lớn chứa quá nhiều thiết bị và lịch sử; dễ tạo partition khổng lồ |
| `device_id` | Nhóm theo thiết bị | Phải bảo đảm ID duy nhất toàn hệ thống; lịch sử thiết bị vẫn tăng vô hạn |
| `(tenant_id, device_id)` | Phân tách thiết bị theo tenant | Lịch sử mỗi thiết bị vẫn tăng mãi |
| `(tenant_id, bucket_day)` | Tách tenant theo ngày | Tenant rất lớn vẫn có thể tạo partition nóng/lớn trong một ngày |
| `(tenant_id, device_id, bucket_day)` | Giới hạn từng thiết bị, từng ngày | Truy vấn toàn tenant/ngày phải đọc nhiều partition |

Không có khóa nào tốt nhất cho mọi truy vấn. Nếu màn hình luôn chọn **một thiết bị**, nhóm theo `tenant_id + device_id` rất tự nhiên. Nếu màn hình chủ yếu cần **tổng hợp tất cả thiết bị của tenant theo ngày**, việc đọc từng partition thiết bị có thể quá tốn kém; nên cân nhắc **bảng đọc/dữ liệu tổng hợp theo tenant–ngày** được tạo riêng.

### Miền dữ liệu phải được định nghĩa đủ ổn định

Ví dụ phân vùng theo `region_name` có thể gặp rắc rối khi vùng được đổi tên hoặc một cửa hàng chuyển vùng quản lý. Nếu khóa partition chứa giá trị có thể đổi, di chuyển thực thể sang miền mới thường đòi hỏi **ghi dữ liệu theo khóa mới và xử lý dữ liệu ở khóa cũ**, cùng mọi nơi tham chiếu.

Các định danh miền như `tenant_id`, `project_id`, `device_id` nên có quy tắc ổn định. Những thuộc tính kinh doanh dễ thay đổi (trạng thái đơn hàng, tên hiển thị, phân loại động) có thể cần read model riêng thay vì dùng làm partition key cho dữ liệu gốc.

## 8. Kết hợp miền dữ liệu và thời gian

Thực tế, thiết kế thường cần cả hai chiều. Ví dụ:

~~~text
Partition key = (tenant_id, device_id, bucket_day)

Clustering = measured_at DESC, reading_id DESC
~~~

Cách này phục vụ tốt câu hỏi **“Trong ngày D, các bản đo của thiết bị X thuộc tenant Y là gì?”**.

Ví dụ trong một hệ thống xử lý đơn hàng, có thể chọn:

~~~sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id text,
    bucket_month text,
    created_at timestamp,
    order_id text,
    status text,
    total_vnd decimal,
    PRIMARY KEY (
        (tenant_id, customer_id, bucket_month),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

`bucket_month` ở đây là chuỗi dạng `YYYY-MM` do ứng dụng sinh nhất quán, ví dụ `2026-11`. Đây là ví dụ minh họa tổ chức dữ liệu; trong hệ thống thực tế có thể dùng kiểu số hoặc cấu trúc thời gian khác phù hợp hơn.

Đọc đơn hàng tháng 11 của khách hàng cụ thể:

~~~sql
SELECT created_at, order_id, status, total_vnd
FROM orders_by_customer_month
WHERE tenant_id = 'T17'
  AND customer_id = 'C42'
  AND bucket_month = '2026-11'
LIMIT 50;
~~~

Nhưng câu hỏi **“mọi đơn hàng trạng thái PAID trong toàn tenant hôm nay”** là một mẫu truy cập khác. Một bảng theo khách hàng/tháng không tự đáp ứng tốt câu hỏi đó khi không biết `customer_id`. Có thể cần:

- Một **read model** riêng theo tenant và ngày/trạng thái, có khả năng giới hạn partition.
- Một bảng tổng hợp theo ngày nếu chỉ cần số lượng hoặc tổng tiền, thay vì mọi đơn.
- Một hệ thống tìm kiếm/analytics phù hợp nếu cần lọc linh hoạt nhiều thuộc tính.

Trong mô hình wide-column định hướng truy vấn, việc giữ **nhiều biểu diễn phục vụ những access pattern khác nhau** là lựa chọn có thể hợp lý, nhưng phải tính chi phí đồng bộ và cách bảo vệ nguồn dữ liệu có thẩm quyền.

## 9. Chọn kích thước bucket từ workload thực tế

Cách chọn một ngày hay một giờ nên dựa trên dữ liệu đo được hoặc một giả định được ghi rõ.

### Bước 1 — Xác định nhóm domain trước

Ví dụ số sự kiện của **một thiết bị**, không lấy trung bình toàn hệ thống rồi chia cho số thiết bị nếu phân bố rất lệch. Một thiết bị công nghiệp có thể gửi 100 bản ghi/giây, còn một cảm biến pin gửi một bản ghi mỗi 10 phút.

Khi chỉ nhìn trung bình, ta dễ bỏ qua những nhóm tạo hot partition. Cần xét **p95/p99 của số bản ghi theo nhóm**, cùng các nhóm có kích thước hoặc tốc độ ghi lớn nhất.

### Bước 2 — Tính số hàng và dung lượng theo khoảng

Lấy `record_rate × bucket_duration` để ước tính số hàng, sau đó nhân kích thước trung bình mỗi hàng để ước lượng payload. Ghi thêm một khoảng dự phòng cho **đỉnh tải**, kích thước payload có thể khác nhau, clustering metadata, tombstone và overhead.

Nếu tải thay đổi theo giờ, nên tính:

~~~text
Số hàng trong bucket =
  tổng số bản ghi thực tế hoặc dự báo đi vào bucket đó

Không nhất thiết =
  tốc độ trung bình năm × số giây của bucket
~~~

### Bước 3 — Xác định khoảng đọc thường gặp

Ví dụ:

| Truy vấn | Tần suất | Phạm vi thường đọc | Gợi ý ảnh hưởng |
| --- | --- | --- | --- |
| 15 phút gần nhất của một thiết bị | Rất cao | Một thiết bị, 15 phút | Bucket giờ có thể giúp giới hạn partition |
| Biểu đồ 24 giờ của một thiết bị | Cao | Một thiết bị, một ngày | Bucket ngày giảm fan-out nhưng có thể quá lớn |
| Lịch sử 90 ngày | Thấp | Nhiều bucket | Cần phân trang, downsampling hoặc bảng tổng hợp |
| Cảnh báo theo site | Trung bình | Nhiều thiết bị trong site | Đọc fan-out có thể lớn; cân nhắc index/projection theo site |
| Tổng số điểm đo theo tenant/ngày | Định kỳ | Nhiều thiết bị | Bảng tổng hợp tenant–ngày có thể phù hợp hơn |

### Bước 4 — Đánh giá số bucket và độ trễ truy vấn

Giả sử mỗi truy vấn phải đọc `k` bucket, mỗi bucket trả nhiều trang. Tổng chi phí chịu ảnh hưởng bởi:

- Số request và round trip mạng.
- Mức song song có giới hạn.
- Dung lượng đọc trong mỗi bucket.
- Số node và partition được truy cập.
- Chi phí hợp nhất, sắp xếp, loại trùng và phân trang.

Tối ưu chỉ theo kích thước partition có thể dẫn đến quá nhiều truy vấn nhỏ. Tối ưu chỉ theo số truy vấn có thể tạo partition quá lớn. Cần **đo cả hai phía**.

### Bước 5 — Quy định mục tiêu kiểm chứng

Thay vì nói “partition dưới X MB là luôn tốt”, hãy lập mục tiêu theo workload cụ thể, chẳng hạn:

~~~text
Workload: Read last 15 minutes of one sensor
Target latency: p95 <= 100 ms (mục tiêu minh họa)
Expected peak write rate: 100 events/s per heavy sensor
Query result size: max 1,000 points per API page
Bucket candidates: hour, 6 hours, day
Measurements:
  - actual partition size distribution
  - read/write p95 and p99 latency
  - partitions touched per query
  - coordinator and storage-node load
  - tombstone scans and compaction pressure
~~~

Giá trị **100 ms là một mục tiêu giả định để minh họa cách viết yêu cầu**, không phải một bảo đảm hay benchmark của Cassandra.

## 10. Timezone và biên bucket: lỗi nhỏ có thể mất dữ liệu

**Một sự kiện phải luôn được ánh xạ vào cùng bucket theo cùng quy tắc**, bất kể client, múi giờ hiển thị hoặc nơi xử lý sự kiện.

Giả sử một sự kiện xảy ra lúc `2026-11-14T00:30:00+07:00`. Đây là `2026-11-13T17:30:00Z` trong UTC. Nếu ứng dụng dùng **bucket theo ngày UTC**, sự kiện này thuộc `2026-11-13`, không phải `2026-11-14`.

Hai quy tắc khác nhau sẽ tạo sai lệch:

~~~text
Writer tính bucket theo giờ Việt Nam:
  2026-11-14T00:30:00+07:00 → ngày 2026-11-14

Reader tính bucket theo UTC:
  2026-11-13T17:30:00Z      → ngày 2026-11-13

Kết quả: reader có thể truy vấn sai phân vùng.
~~~

### Quy tắc thực hành

1. **Lưu timestamp có ngữ nghĩa rõ ràng.** Dùng UTC cho thời điểm tuyệt đối và chuyển sang giờ địa phương chỉ khi hiển thị hoặc xử lý nghiệp vụ yêu cầu.
2. **Tính bucket bằng cùng một hàm/quy tắc** cho mọi writer, reader, job backfill và consumer.
3. **Phân biệt event time với ingestion time.** Dữ liệu đến trễ phải có chính sách bucket nhất quán.
4. **Dùng khoảng nửa mở `[start, end)`** khi xác định cửa sổ; dữ liệu đúng tại `end` thuộc khoảng tiếp theo.
5. **Định nghĩa cách xử lý giờ mùa hè** nếu bucket theo lịch địa phương ở khu vực có DST; một ngày lịch địa phương có thể không luôn dài 24 giờ.
6. **Phiên bản hóa quy tắc bucket nếu thay đổi.** Chuyển từ UTC sang giờ địa phương hoặc từ ngày sang giờ có thể đòi hỏi migration dữ liệu cũ.

Nếu yêu cầu nghiệp vụ thật sự là **báo cáo theo ngày làm việc địa phương**, ứng dụng có thể cần một trường hoặc projection dùng lịch địa phương. Không nên âm thầm đổi partition bucket của dữ liệu gốc theo timezone hiển thị của từng người xem.

## 11. Dữ liệu đến muộn, sai thứ tự và ghi lại

Hệ thống thu thập sự kiện hiếm khi nhận dữ liệu đúng thứ tự tuyệt đối. Một thiết bị có thể offline hai giờ rồi gửi lại những bản đo cũ, hoặc mạng có thể gửi lặp một bản ghi.

Giả sử:

~~~text
measured_at = 2026-11-13T23:55:00Z
received_at = 2026-11-14T02:00:00Z
~~~

Nếu thiết kế **bucket theo measurement/event time**, bản ghi này vẫn phải vào `2026-11-13`, dù được nhận ngày 14. Điều này có những hệ quả:

- Writer phải có khả năng tính và ghi vào bucket lịch sử.
- Reader hoặc job tổng hợp cần xử lý dữ liệu đến muộn; báo cáo ngày 13 trước đó có thể cần được cập nhật.
- Nếu chỉ tiêu thụ “bucket hôm nay”, quá trình cập nhật có thể bỏ sót dữ liệu cũ đến muộn.
- Chính sách retention phải tính đến thời gian trễ tối đa chấp nhận được.

Nếu chọn **bucket theo ingestion time**, hệ thống ghi sự kiện vào bucket ngày 14, nhưng truy vấn theo `measured_at` trong ngày 13 có thể phải xem cả bucket đến muộn của những ngày khác. Việc này làm mô hình truy vấn khác đi.

### Event time hay ingestion time?

| Cách chọn bucket | Lợi ích | Đánh đổi |
| --- | --- | --- |
| Theo **event time** | Truy vấn lịch sử theo thời gian sự việc dễ suy ra bucket | Dữ liệu đến muộn có thể ghi ngược vào bucket cũ |
| Theo **ingestion time** | Dễ giới hạn chỗ ghi theo thời gian hệ thống tiếp nhận | Truy vấn theo thời gian sự việc có thể phải quét thêm khoảng ingestion |
| Cả hai chiều qua hai read model | Hỗ trợ nhiều nhu cầu | Tăng dữ liệu dẫn xuất và chi phí đồng bộ |

Cần công bố rõ `eventTime` và `ingestedAt` trong hợp đồng dữ liệu. Không đặt tên chung chung `timestamp` rồi để mỗi dịch vụ hiểu một cách.

### Ghi lặp và tính idempotent

Trong Cassandra, cùng một **full primary key** trỏ đến cùng một hàng logic. Nếu ứng dụng gửi lại bản ghi với partition và clustering key giống hệt, việc ghi có thể cập nhật cùng hàng thay vì tạo một hàng mới. Nhưng điều này chỉ giúp chống bản ghi trùng nếu:

- Writer tính **cùng bucket** cho cùng sự kiện.
- Sự kiện có **định danh ổn định**, không sinh một `reading_id` mới mỗi lần retry.
- Chính sách cập nhật, timestamp ghi và dữ liệu không tạo ra giá trị sai khi gửi lại.

Với hệ cần tính chính xác số lần xảy ra, phải phân biệt **một sự kiện được gửi lại** với **hai sự kiện thực sự khác nhau** có cùng thời gian đo.

## 12. Khi bucket theo thời gian vẫn còn quá nóng: thêm shard

Một vài thiết bị có thể phát khối lượng dữ liệu quá lớn đến mức **một thiết bị trong một giờ** vẫn tạo điểm nóng. Có thể đưa thêm `shard_id` vào partition key:

~~~text
partition_key =
  (tenant_id, device_id, bucket_hour, shard_id)

shard_id = stableHash(reading_id) modulo shard_count
~~~

Ví dụ với 8 shard:

~~~text
sensor-17 / 2026-11-14T10 / shard 0
sensor-17 / 2026-11-14T10 / shard 1
sensor-17 / 2026-11-14T10 / shard 2
...
sensor-17 / 2026-11-14T10 / shard 7
~~~

Ghi có thể được phân tán trên nhiều partition, nhưng **đọc đầy đủ một giờ của một thiết bị** phải xét tất cả shard từ 0 đến 7 rồi hợp nhất kết quả.

Đánh đổi:

| Lợi ích | Chi phí |
| --- | --- |
| Giảm tập trung tải ghi vào một partition | Tăng số partition phải đọc |
| Giảm số hàng trong từng partition | Cần thuật toán chọn shard ổn định và nhất quán |
| Có thể mở rộng workload của nhóm rất nóng | Thêm logic merge, phân trang và xử lý fan-out |

### Không thay đổi shard count tùy tiện

Nếu `shard_id = hash(id) mod 8` hôm nay nhưng tháng sau đổi thành `mod 16`, cùng một ID có thể được ánh xạ tới shard khác. Điều này gây khó cho đọc dữ liệu cũ, retry, dedup và migration.

Một thiết kế cần ghi rõ **phiên bản chính sách shard** và **phạm vi thời gian áp dụng**. Ví dụ quy định các bucket bắt đầu từ tháng mới dùng 16 shard, còn bucket cũ vẫn đọc theo 8 shard. Nếu phải di chuyển dữ liệu, cần kế hoạch backfill/dual-read và cách xác nhận đã hoàn tất.

### Băm khóa theo đối tượng có giúp phân tải không?

Nếu băm `device_id` để tạo shard nhưng truy vấn chỉ có **một thiết bị**, mọi sự kiện của thiết bị đó vẫn rơi vào **cùng shard**. Muốn chia một dòng sự kiện cực nóng thành nhiều partition, phải chọn đầu vào hash thay đổi giữa các sự kiện (như `reading_id`) mà vẫn có thể tái tạo ổn định khi retry.

Ngược lại, nếu tải đã trải đều giữa nhiều thiết bị, thêm shard nhân tạo có thể chỉ tăng phức tạp mà không có lợi ích đáng kể.

## 13. Dữ liệu hết hạn, tombstone và compaction

Dữ liệu theo thời gian thường có chính sách lưu giữ: điểm đo chi tiết 30 ngày, báo cáo giờ một năm, hoặc sự kiện audit nhiều năm. Thiết kế bucket cần đi cùng chính sách **TTL**, xóa, downsampling và compaction.

Trong Cassandra, **TTL** có thể được đặt trên dữ liệu lúc ghi; dữ liệu hết hạn thường liên quan đến **tombstone** và cơ chế compaction để dọn vật lý sau đó. Cần phân biệt:

- **Thời điểm sự kiện xảy ra**.
- **Thời điểm ứng dụng ghi dữ liệu**.
- **Thời điểm TTL được tính và bắt đầu** theo ngữ nghĩa của thao tác ghi.
- **Thời điểm dữ liệu không còn xuất hiện trong kết quả truy vấn** và thời điểm lưu trữ vật lý được thu hồi.

Ví dụ một sự kiện của 20 ngày trước mới được gửi tới hôm nay. Nếu gán TTL 30 ngày **tính từ lúc ghi**, nó có thể tiếp tục tồn tại thêm 30 ngày từ hôm nay, khiến tổng vòng đời tính theo `event_time` dài hơn 30 ngày.

Nếu yêu cầu là “giữ 30 ngày kể từ khi sự kiện xảy ra”, ứng dụng phải tính **thời gian còn lại** tại lúc ghi hoặc dùng cơ chế retention phù hợp, đồng thời quyết định phải làm gì khi sự kiện đã quá hạn trước lúc tiếp nhận.

### Phân vùng theo ngày không tự xóa toàn bộ dữ liệu ngày cũ

Việc có `bucket_day` giúp xác định dữ liệu lịch sử theo phạm vi, nhưng **không tự làm bucket cũ biến mất**. Chính sách retention cần được triển khai bằng cơ chế được DBMS hỗ trợ; xóa hàng loạt bằng nhiều lệnh xóa có thể tạo nhiều tombstone và ảnh hưởng truy vấn.

Với workload chuỗi thời gian trong Cassandra, chiến lược **TimeWindowCompactionStrategy (TWCS)** có thể là một lựa chọn để cân nhắc, nhất là khi dữ liệu có vòng đời và TTL phù hợp với các cửa sổ thời gian. Nhưng TWCS không thay thế thiết kế partition key hay retention, và các bản ghi đến muộn, cập nhật khác thời gian hoặc TTL không đồng nhất có thể khiến hành vi compaction phức tạp hơn.

**Điểm quan trọng:** không nên tự hứa rằng “mỗi bucket một ngày thì xóa cả ngày rất nhanh” khi chưa có cơ chế xóa/compaction tương ứng và chưa kiểm tra bảo đảm của DBMS. Cũng không dùng TTL để thay thế cho yêu cầu kiểm toán hoặc lưu trữ pháp lý mà nghiệp vụ bắt buộc giữ.

## 14. Thay đổi quy tắc bucket là một migration dữ liệu

Giả sử hệ thống khởi đầu với `(tenant_id, device_id, bucket_day)`, sau đó thấy partition của thiết bị tải cao quá lớn và muốn đổi sang `bucket_hour`.

Không thể chỉ đổi công thức ở writer mà reader cũ tự đọc được mọi dữ liệu:

~~~text
Trước:
  sensor-17 / day=2026-11-13
  sensor-17 / day=2026-11-14

Sau:
  sensor-17 / hour=2026-11-14T09
  sensor-17 / hour=2026-11-14T10
  sensor-17 / hour=2026-11-14T11
~~~

Việc đổi thành phần của **primary key** thường cần một bảng/cấu trúc mới hoặc kế hoạch di chuyển dữ liệu thích hợp; không nên giả định có thể cập nhật tại chỗ primary key của từng hàng mà giữ nguyên mọi quan hệ truy cập.

Một cách chuyển có thể gồm:

1. **Xác định phiên bản sơ đồ mới:** ví dụ bảng `readings_by_device_hour` với partition key theo giờ.
2. **Triển khai reader có thể truy cập cả cũ và mới** theo mốc thời gian hoặc quy tắc version đã công bố.
3. **Chuyển writer** sang cấu trúc mới bằng cơ chế kiểm soát được; nếu có giai đoạn ghi song song, phải xử lý lỗi ghi thành công một bên.
4. **Backfill** dữ liệu lịch sử nếu yêu cầu phải dùng cấu trúc mới cho toàn bộ truy vấn.
5. **Đối soát** số bản ghi/định danh, trường dữ liệu, time range và khả năng truy vấn.
6. **Ngừng dùng cấu trúc cũ** sau khi đã xác nhận không còn consumer hoặc dữ liệu cần thiết.

Backfill không nên ghi đè mù quáng bản ghi mới hoặc tạo lại sự kiện dưới ID khác. Việc đổi bucket có thể kéo theo thay đổi về lưu giữ, read model, phân trang và vận hành.

## 15. Những lỗi thiết kế dễ mắc

| Sai lầm | Hậu quả | Cách khắc phục tư duy |
| --- | --- | --- |
| Dùng `tenant_id` làm toàn bộ partition key cho dữ liệu tăng liên tục | Một tenant lớn tạo partition rất rộng | Tách theo thực thể con và/hoặc thời gian phù hợp |
| Chia theo ngày nhưng mọi thiết bị cùng một partition `day` | Partition theo ngày vẫn nóng/lớn | Đưa miền phù hợp vào partition key |
| Chia theo giờ cho dữ liệu hiếm, nhưng truy vấn thường xem cả năm | Hàng nghìn bucket phải đọc | Dùng bucket rộng hơn hoặc bảng tổng hợp |
| Chọn kích thước bucket chỉ bằng trung bình toàn cụm | Không thấy tenant/thiết bị có tải đột biến | Ước lượng và đo phân bố theo từng nhóm |
| Writer tính ngày theo giờ địa phương, reader tính ngày UTC | Đọc sai bucket, mất kết quả | Dùng cùng quy tắc thời gian và biên khoảng |
| Chỉ đọc bucket hôm nay cho truy vấn “90 phút gần nhất” | Bỏ dữ liệu nằm qua nửa đêm | Liệt kê toàn bộ bucket giao với khoảng |
| Đổi day sang hour mà không hỗ trợ dữ liệu cũ | Reader bỏ sót lịch sử | Migration và versioning rõ ràng |
| Sinh ID sự kiện mới mỗi lần retry | Tạo bản ghi trùng | Giữ định danh sự kiện ổn định |
| Coi TTL là dọn vật lý tức thì | Dự báo dung lượng, tombstone và chi phí đọc sai | Hiểu semantics TTL/compaction của DBMS |
| Thêm nhiều shard cho mọi nhóm dữ liệu | Fan-out và quản lý phức tạp không cần thiết | Chỉ shard khi đã xác định hot partition |
| Dùng `ALLOW FILTERING` để “chữa” truy vấn thiếu partition key | Đọc rộng và hiệu suất khó dự đoán khi tải tăng | Thiết kế bảng/index/read model theo truy vấn |
| Dùng bucket theo trạng thái nghiệp vụ biến động | Trạng thái thay đổi đòi hỏi di chuyển/đồng bộ dữ liệu | Dùng khóa ổn định hoặc projection riêng |

## 16. Kịch bản tổng hợp: hệ thống theo dõi kho lạnh

Một doanh nghiệp có nhiều tenant. Mỗi tenant có nhiều kho; mỗi kho có hàng trăm cảm biến. Hệ thống cần:

- Xem **15 phút gần nhất của một cảm biến** với độ trễ thấp.
- Xem **biểu đồ 24 giờ của một cảm biến**.
- Tính **nhiệt độ cao nhất mỗi giờ của toàn kho**.
- Giữ điểm đo chi tiết trong một khoảng thời gian giới hạn.
- Tiếp nhận những bản đo bị gửi trễ khi cảm biến mất mạng.

### 16.1. Chọn một bảng điểm đo gốc

Có thể khảo sát:

~~~text
readings_by_sensor_hour
  partition key = (tenant_id, sensor_id, bucket_hour)
  clustering = (measured_at DESC, reading_id DESC)
  payload = temperature, humidity, metadata
~~~

Đường đọc 15 phút thường chỉ chạm một hoặc hai bucket giờ; truy vấn 24 giờ phải chạm khoảng 24–25 bucket (tùy thời điểm bắt đầu và kết thúc). Khả năng đáp ứng độ trễ cần được thử tải với số điểm đo và số cảm biến thực tế.

Nếu tốc độ một cảm biến thấp và truy vấn 24 giờ rất phổ biến, bucket ngày có thể giảm số partition đọc. Nếu một nhóm cảm biến đặc biệt nóng, bucket giờ hoặc shard phụ có thể phù hợp hơn.

### 16.2. Một bảng tổng hợp theo kho–giờ

Yêu cầu “nhiệt độ cao nhất mỗi giờ của toàn kho” không nhất thiết nên quét mọi cảm biến và mọi bản đo của giờ đó mỗi lần dashboard tải lại. Có thể xây **projection**:

~~~text
warehouse_hourly_temperature
  key: tenant_id + warehouse_id + hour
  value: minTemp, maxTemp, avgTemp, sampleCount, computedAt
~~~

Projection được tính từ các bản đo nguồn theo một luồng cập nhật đã thiết kế. Khi nhận bản đo đến muộn, bộ tổng hợp cần có cách điều chỉnh kết quả giờ tương ứng hoặc quy tắc chốt kết quả theo watermark.

Đây là **dữ liệu dẫn xuất**, nên cần biết nguồn có thẩm quyền, độ trễ cập nhật, tính idempotent và cách đối soát.

### 16.3. Đọc lịch sử có giới hạn

API có thể yêu cầu:

~~~text
GET /sensors/S17/readings?from=...&to=...&limit=500
~~~

Ứng dụng nên:

1. Xác thực quyền truy cập sensor thuộc tenant.
2. Giới hạn `from/to` theo retention và chính sách tối đa của API.
3. Xác định các bucket giờ giao với khoảng.
4. Giới hạn mức song song và số điểm đọc.
5. Ghép, sắp xếp và phân trang theo một cursor phù hợp.
6. Trả rõ nếu dữ liệu đang cập nhật hoặc đã hết hạn.

Đặt `tenant_id` vào partition key có ích cho tổ chức dữ liệu, **không thay thế kiểm tra quyền**. Không được tin tenant ID do client truyền mà không kiểm chứng.

## 17. Bài tập phân tích

### Bài 1 — Chọn ngày hay giờ

Một thiết bị phát 2 bản ghi/phút, mỗi bản ghi khoảng 300 byte. Dashboard thường đọc 7 ngày gần nhất, đôi khi đọc 30 ngày. Một thiết kế bucket theo giờ có thể tạo bao nhiêu bucket cho truy vấn 7 ngày? Có nên khảo sát bucket theo ngày không?

**Gợi ý:** 7 ngày × 24 giờ = 168 giờ, có thể thêm bucket giao biên nếu khoảng không đúng giờ. Tải mỗi thiết bị khá thấp nên cần cân nhắc bucket ngày để giảm fan-out, rồi kiểm tra ước lượng dung lượng và số hàng thực tế.

### Bài 2 — Chọn domain key

Một tenant có 200.000 thiết bị. Vì sao partition key `(tenant_id, bucket_day)` có thể không đủ, dù đã chia theo ngày?

**Gợi ý:** mọi bản ghi của tất cả thiết bị trong tenant cùng ngày vẫn vào một partition. Có thể cần phân tách theo `device_id` hoặc nhóm thiết bị, tùy truy vấn chính.

### Bài 3 — Sự kiện đến trễ

Một sự kiện có `occurred_at = 2026-11-13T23:55:00Z` nhưng được nhận lúc `2026-11-14T02:00:00Z`. Nếu bucket theo **event time UTC**, sự kiện phải được ghi vào bucket nào? Báo cáo ngày 13 đã tính xong phải xử lý ra sao?

**Gợi ý:** sự kiện thuộc bucket ngày 13; báo cáo/đầu đọc cần cơ chế cập nhật kết quả khi dữ liệu đến muộn hoặc chính sách đóng cửa sổ rõ ràng.

### Bài 4 — Một thiết bị quá nóng

Một thiết bị ghi 100.000 sự kiện trong một phút, trong khi các thiết bị khác chỉ vài sự kiện. Việc thêm `shard_id = hash(device_id) mod 8` có chia được lưu lượng của thiết bị nóng không?

**Gợi ý:** không, vì `device_id` không đổi nên tất cả sự kiện của thiết bị vẫn đi cùng một shard. Cần chọn thành phần thay đổi theo sự kiện nếu thật sự cần chia tải của một thiết bị, rồi chấp nhận chi phí đọc tất cả shard liên quan.

### Bài 5 — Truy vấn qua ranh giới tháng

Bảng `orders_by_customer_month` phân vùng theo `(tenant_id, customer_id, bucket_month)`. API cần 50 đơn gần nhất của một khách hàng vào ngày đầu tháng 12. Tại sao có thể phải truy vấn cả tháng 11? Khi nào có thể dừng đọc các tháng cũ?

**Gợi ý:** tháng 12 có thể chưa đủ 50 đơn. Cần tiếp tục duyệt các bucket tháng trước theo thứ tự và dừng khi đủ kết quả, đã đạt giới hạn lịch sử hoặc không còn dữ liệu phù hợp, với cơ chế phân trang và sắp xếp đúng.

### Bài 6 — TTL của dữ liệu trễ

Yêu cầu: “Điểm đo chỉ được giữ 30 ngày tính từ `measured_at`”. Một bản ghi 25 ngày tuổi được gửi tới hôm nay. Nếu ứng dụng đặt TTL 30 ngày từ thời điểm ghi, yêu cầu có được đáp ứng không?

**Gợi ý:** không; bản ghi có thể tồn tại khoảng 55 ngày tính từ lúc đo. Cần tính TTL còn lại hoặc dùng chính sách retention khác phù hợp.

## 18. Mẫu tài liệu thiết kế bucket

Một hợp đồng ngắn cho bảng theo thiết bị và giờ có thể ghi:

~~~yaml
dataset: sensor_readings
dbmsExample: Apache Cassandra
sourceOfTruth: Sensor ingestion service
partitionKey:
  - tenant_id
  - device_id
  - bucket_hour
clustering:
  - measured_at DESC
  - reading_id DESC
bucket:
  unit: hour
  timezone: UTC
  derivedFrom: measured_at
  intervalConvention: "[start, end)"
idempotency:
  stableId: reading_id
readPatterns:
  - "Read last 15 minutes of one sensor"
  - "Read last 24 hours of one sensor"
retention:
  requirement: "Policy defined relative to measured_at"
  implementation: "Must account for late arrivals and DBMS TTL semantics"
consumer:
  maxFanout: "Defined per API and observed in production"
  pagination: "Merge per-bucket ordered pages"
monitoring:
  - partition_size_distribution
  - hot_partition_throughput
  - query_fanout
  - read_write_p95_p99
  - tombstone_and_compaction_pressure
schemaMigration:
  strategy: "Version bucket policy and support old/new readers"
~~~

Đây chỉ là **đặc tả minh họa để nhóm phát triển thống nhất cách dùng dữ liệu**, không phải cấu hình Cassandra tự thực thi. Các mức giới hạn cụ thể, retention, kiểu khóa và cơ chế giám sát phải được xác định theo triển khai thực tế.

## 19. Ghi nhớ

**Chia nhóm theo thời gian** đặt giới hạn cho số bản ghi thuộc một khoảng. **Chia nhóm theo miền dữ liệu** thu hẹp nhóm thực thể cùng chia sẻ phân vùng. **Kết hợp cả hai** thường tạo partition có ranh giới phù hợp hơn cho dữ liệu tăng liên tục trong mô hình cột rộng.

Khi quyết định partition key và bucket, hãy lần lượt trả lời:

1. **Truy vấn quan trọng nhất đã biết những khóa nào?** Cassandra cần đủ partition key để truy cập trực tiếp một partition theo thiết kế bảng.
2. **Một partition lớn và nóng đến mức nào?** Ước lượng theo **một nhóm miền**, đỉnh tải, số hàng và dung lượng, rồi đo phân bố thực tế.
3. **Một truy vấn chạm bao nhiêu bucket?** Bucket quá nhỏ tạo fan-out; bucket quá rộng tạo partition lớn.
4. **Cách tính bucket có thống nhất không?** Đặc biệt với UTC, dữ liệu đến muộn và biên khoảng thời gian.
5. **Có cần read model khác cho mẫu truy vấn khác không?** Truy vấn theo thiết bị và tổng hợp theo tenant/site thường nên được đánh giá riêng.
6. **Retention, compaction và migration hoạt động thế nào?** Không giả định bucket tự xóa, TTL tự giải quyết lịch sử hoặc việc đổi khóa không cần chuyển dữ liệu.

Thiết kế thành công là thiết kế **phân vùng có kích thước/tải dự đoán và kiểm soát được, đồng thời giữ số partition phải đọc ở mức phù hợp với truy vấn thực tế**. Đó là mục tiêu của time bucketing và domain bucketing trong mô hình cột rộng.
