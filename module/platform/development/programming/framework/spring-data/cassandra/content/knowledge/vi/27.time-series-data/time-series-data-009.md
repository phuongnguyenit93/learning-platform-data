# Quan hệ giữa mẫu ghi, TTL và chiến lược compaction theo thời gian

Trong các hệ thống **time-series** chạy trên Apache Cassandra, việc chọn `timestamp`, `TTL` và **TimeWindowCompactionStrategy (TWCS)** không thể thực hiện độc lập. Ba quyết định này liên quan tới **mẫu ghi dữ liệu**, độ trễ của dữ liệu đến muộn, kích thước partition, thời điểm hết hạn, số tombstone phải quét và khả năng thu dọn SSTable.

Một hiểu lầm thường gặp là: *“Bảng chia theo ngày, giữ TTL bảy ngày và bật TWCS một ngày, vậy dữ liệu của ngày cũ sẽ được xóa gọn chính xác sau bảy ngày.”* Trên thực tế, **ngày của sự kiện**, **timestamp metadata của mutation**, **thời điểm bắt đầu TTL** và **cửa sổ compaction** là các đại lượng **khác nhau**. Dữ liệu đến muộn, sửa hàng cũ, thời hạn TTL không đồng đều và replay với write timestamp khác thường có thể khiến các SSTable chứa những cell có vòng đời rất khác nhau, làm giảm hiệu quả thu dọn.

Bài thuộc chương **Dữ liệu thời gian** của module **SPRING_DATA_CASSANDRA**. Ta sẽ thiết kế schema theo query, thao tác bằng Spring Data Cassandra (`@Table`, repository, `CassandraTemplate`), CQL và Java Driver; tiếp đó liên hệ **time bucketing**, **TTL**, **tombstones**, **TWCS**, **consistency**, **paging** và các phép đo vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **event time**, **ingestion time**, **CQL timestamp value**, **write timestamp metadata** và **thời điểm TTL hết hạn**.
2. Thiết kế bảng time-series theo **partition key có bucket** và **clustering order** phù hợp truy vấn.
3. Chọn **TTL đồng nhất** hoặc **TTL theo deadline của sự kiện**, hiểu sự khác nhau khi có **late arrivals/backfill**.
4. Giải thích TWCS gom SSTable thành các **cửa sổ thời gian ghi**, không dựa trực tiếp vào cột `occurred_at` hoặc tên `day_bucket`.
5. Nhận diện vì sao **out-of-order writes**, TTL hỗn hợp, overwrite, repair/streaming và dữ liệu rất muộn có thể cản trở việc loại bỏ SSTable hết hạn.
6. Đọc `TTL()`, `WRITETIME()`, cấu hình `system_schema.tables`; viết integration test và đề xuất benchmark/giám sát có giới hạn.
7. Dùng repository/`Slice` để đọc từng trang và không nhầm số hàng của trang với chi phí tombstone scan.

> **Ý chính:** `TWCS` không phải đồng hồ tự xóa dữ liệu. Nó là **chiến lược compaction các SSTable**, hiệu quả nhất khi các cell trong cùng cửa sổ có tuổi và thời hạn hết hiệu lực tương đối đồng đều.

## 2. Bốn loại thời gian phải đặt tên rõ

Giả sử một cảm biến gửi sự kiện:
 
~~~json
{
  "deviceId": "3bcff89a-a3ee-4b0d-b4a6-e22999fe6775",
  "eventId": "50f70c6e-992f-4b8c-9163-a669e10ff85d",
  "occurredAt": "2026-11-20T12:00:00Z",
  "temperatureC": 31.25
}
~~~

Sự kiện có thể được tạo vào 20/11 nhưng gateway mất mạng, đến 25/11 mới đồng bộ.

| Khái niệm | Ví dụ | Ai xác định? | Công dụng |
|---|---|---|---|
| **Event time** | 20/11 12:00 UTC | Thiết bị/domain | Sắp xếp lịch sử theo lúc sự kiện xảy ra |
| **Ingestion time** | 25/11 09:00 UTC | Backend tiếp nhận | Kiểm soát lag, retention theo lúc nhận |
| **CQL `timestamp`** | Giá trị `occurred_at`, `ingested_at` | Ứng dụng ghi vào cột | Dữ liệu nghiệp vụ, độ chính xác mili giây |
| **Write timestamp** | Số micro giây gắn vào cell | Driver/coordinator hoặc `USING TIMESTAMP` | Quy tắc hòa giải last-write-wins |
| **TTL expiration** | Sau N giây từ lúc mutation được áp dụng, theo cơ chế TTL | Cassandra và policy của câu ghi | Chuyển dữ liệu sang trạng thái hết hiệu lực |

Ba phép đo thường bị gộp nhầm:

~~~text
event time            2026-11-20 12:00Z
    |
    | 5 ngày nằm offline
    v
ingestion time        2026-11-25 09:00Z
    |
    | INSERT USING TTL 604800
    v
thời điểm hết TTL    khoảng 2026-12-02 09:00Z
                      (retention theo lúc ghi/nhận)
~~~

Nếu nghiệp vụ yêu cầu **giữ tối đa bảy ngày kể từ lúc sự kiện xảy ra**, thì dữ liệu của 20/11 **không được giữ thêm bảy ngày kể từ 25/11**. Ứng dụng phải tính phần TTL còn lại đến deadline nghiệp vụ, hoặc từ chối sự kiện đã quá hạn.

**Một điểm nữa:** TWCS xác định cửa sổ dựa trên **write timestamp của dữ liệu trong SSTable** (với logic phân loại SSTable của phiên bản cụ thể), chứ không tự đọc giá trị cột `occurred_at` hoặc `day_bucket` để xác định cửa sổ.

## 3. Mẫu ghi time-series quyết định thiết kế lưu trữ

Có ít nhất bốn mẫu ghi cần phân biệt:

| Mẫu ghi | Đặc điểm | Hệ quả đối với TTL/TWCS |
|---|---|---|
| **Append-only, gần đúng thời gian thực** | Mỗi sự kiện là một hàng mới, thời gian ghi gần event time | Thường thuận lợi cho TTL đồng đều và TWCS |
| **Late arrivals** | Sự kiện cũ được nhận/ghi sau vài giờ hoặc ngày | Bucket theo event time có thể cũ, nhưng write timestamp thuộc thời điểm nhận |
| **Backfill lịch sử** | Nạp hàng triệu sự kiện cũ vào ngày hiện tại | Có thể tạo SSTable chứa dữ liệu với tuổi nghiệp vụ khác tuổi ghi |
| **Update/delete ngẫu nhiên** | Sửa hoặc xóa các hàng đã lâu | Phát sinh cell versions/tombstones mới, làm dữ liệu cũ và mới chồng lấn |
| **Mixed retention** | Một số cột TTL 1 ngày, số khác 90 ngày hoặc không TTL | Khó thu dọn trọn SSTable khi còn cell sống lâu |
| **Replay với explicit write timestamp** | `USING TIMESTAMP` đặt metadata quá khứ/tương lai | Có thể gây lệch cửa sổ, xung đột LWW và ảnh hưởng thu dọn |

Bảng time-series hiệu quả thường ưu tiên **ghi append-only**, dữ liệu ít bị sửa, có TTL/retention nhất quán và truy vấn theo partition đã biết. Đó là xu hướng thiết kế, **không phải yêu cầu bắt buộc của Cassandra**; ứng dụng vẫn có thể ghi trễ hoặc sửa dữ liệu, nhưng phải chấp nhận chi phí tương ứng.

### 3.1. Hai chính sách retention khác nhau

**Chính sách A — giữ bảy ngày từ khi ghi:**

~~~text
Event xảy ra ngày 20/11.
Cassandra nhận ngày 25/11.
TTL 7 ngày cho INSERT.
=> Hết TTL xấp xỉ 02/12.
~~~

**Chính sách B — giữ đến hết bảy ngày từ khi xảy ra:**

~~~text
Event xảy ra ngày 20/11 lúc 12:00.
Deadline = 27/11 lúc 12:00.
Backend nhận ngày 25/11 lúc 09:00.
TTL còn lại xấp xỉ 2 ngày 3 giờ.
=> Hết TTL gần deadline 27/11.
~~~

**Chọn chính sách dựa trên hợp đồng sản phẩm và pháp lý**, không chọn theo khả năng TWCS. Nếu phải xóa đúng hạn theo event time, cần xử lý sai lệch đồng hồ thiết bị, sự kiện giả mạo thời gian, độ trễ rất lớn và giới hạn clock skew.

## 4. Thiết kế schema theo truy vấn: thiết bị và bucket ngày

Yêu cầu API:

~~~text
GET /tenants/{tenantId}/devices/{deviceId}/events
    ?day=2026-11-25
    &pageSize=50

Trả các sự kiện mới nhất của một thiết bị trong một ngày.
~~~

Schema:

~~~sql
CREATE TABLE telemetry_events_by_device_day (
    tenant_id uuid,
    device_id uuid,
    day_bucket date,
    occurred_at timestamp,
    event_id uuid,
    ingested_at timestamp,
    event_type text,
    payload text,
    PRIMARY KEY (
        (tenant_id, device_id, day_bucket),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

| Cột | Vai trò | Ý nghĩa cho time-series |
|---|---|---|
| `tenant_id` | Partition key | Cô lập tenant |
| `device_id` | Partition key | Phân phối dữ liệu theo thiết bị |
| `day_bucket` | Partition key | Giới hạn số hàng của một thiết bị/ngày |
| `occurred_at` | Clustering DESC | Sắp lịch sử theo event time |
| `event_id` | Clustering ASC | Phân biệt sự kiện trùng timestamp |
| `ingested_at` | Cột thường | Quan sát độ trễ nhận dữ liệu |
| `event_type`, `payload` | Cột thường | Nội dung ghi/đọc |

Truy vấn:

~~~sql
SELECT occurred_at, event_id, ingested_at, event_type, payload
FROM telemetry_events_by_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?;
~~~

**Phải cung cấp đầy đủ composite partition key.** Không dùng `SELECT * ... WHERE event_type = ?` để quét tự do trên bảng này; muốn lọc theo type, tenant hoặc tất cả thiết bị ở một thời điểm, cần access table/index được thiết kế và benchmark riêng.

### 4.1. Bucket ngày không luôn đủ nhỏ

Giả sử một thiết bị ghi **5.000 sự kiện/giây**:

~~~text
5.000 sự kiện/giây × 86.400 giây
= 432.000.000 sự kiện trong một ngày
~~~

Một partition/ngày của thiết bị này là **quá lớn cho thiết kế thực tế** trong nhiều hệ thống. Cần cân nhắc bucket theo giờ/phút hoặc shard có kiểm soát. Ngược lại, với cảm biến chỉ gửi vài chục sự kiện/ngày, bucket theo giờ tạo quá nhiều partition nhỏ và khiến đọc lịch sử phức tạp.

**Nguyên tắc:** chọn kích thước bucket theo **số hàng/byte mỗi partition, độ trễ, payload, TTL, phân bố thiết bị và truy vấn**, không chỉ chọn ngày vì tên chương là “time-series”.

### 4.2. Bucket không đồng nghĩa compaction window

~~~text
day_bucket = 2026-11-20
    => phục vụ định vị partition và truy vấn

SSTable được ghi/flushed ngày 2026-11-25
    => write timestamps có thể thuộc cửa sổ 25/11

Cấu hình TWCS: cửa sổ 1 ngày
    => quản lý nhóm SSTables theo thời gian ghi
~~~

Một hàng sự kiện nằm trong partition `day_bucket=20/11` nhưng metadata ghi của nó có thể thuộc **cửa sổ TWCS ngày 25/11** vì event được nhận trễ. Điều này hoàn toàn có thể xảy ra và không tự động là bug.

## 5. TTL per-write và TTL mặc định của bảng

**TTL (Time To Live)** quy định số giây dữ liệu được ghi còn hiệu lực theo cơ chế Cassandra. Khi TTL hết, giá trị không còn được đọc như cell live; storage vẫn cần quản lý tombstone/thông tin hết hạn cho tới khi có thể thu dọn an toàn.

### 5.1. Cấp TTL cho một INSERT

~~~sql
INSERT INTO telemetry_events_by_device_day (
    tenant_id, device_id, day_bucket, occurred_at, event_id,
    ingested_at, event_type, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
USING TTL 604800;
~~~

`604800` giây = 7 ngày. Với mutation này, TTL áp dụng cho các **giá trị non-key được ghi** theo semantics của Cassandra. **Primary key không được hiểu như các cột thông thường có thể đổi TTL tùy ý.** Khi các cell dữ liệu hết hạn, hàng có thể biến mất khỏi kết quả truy vấn nếu không còn dữ liệu live.

### 5.2. TTL mặc định ở cấp bảng

Nếu dữ liệu của bảng đều có retention nhất quán, có thể đặt:

~~~sql
CREATE TABLE telemetry_events_by_device_day (
    tenant_id uuid,
    device_id uuid,
    day_bucket date,
    occurred_at timestamp,
    event_id uuid,
    ingested_at timestamp,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, day_bucket), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)
  AND default_time_to_live = 604800;
~~~

`default_time_to_live` có thể giảm việc quên TTL ở từng `INSERT`, nhưng **nó không làm retention tự động theo cột `occurred_at`**. Dữ liệu nhập trễ vẫn có nguy cơ sống thêm bảy ngày kể từ thời điểm ghi, không phải từ ngày sự kiện.

Khi thay TTL mặc định trên bảng đang chạy, phải đánh giá dữ liệu cũ, cập nhật mới, tombstone generation và cách áp dụng TTL giữa các phiên bản Cassandra. Không thay đổi `ALTER TABLE` ở production mà thiếu kế hoạch migration.

### 5.3. TTL không đồng nghĩa delete vật lý tức thì

~~~text
INSERT ở T0, TTL=1 giờ
    |
    v
T0 + 1 giờ: dữ liệu hết hiệu lực logic
    |
    v
Dữ liệu/tombstone có thể vẫn nằm trong SSTables
    |
    v
Compaction đủ điều kiện: storage mới có thể thu dọn
~~~

`SELECT` không thấy hàng **không chứng minh** dữ liệu đã bị xóa khỏi mọi SSTable, replica, snapshot hoặc backup.

## 6. TWCS là gì?

**TimeWindowCompactionStrategy** là một **chiến lược compaction** phù hợp với nhiều workload time-series ghi theo thời gian, đặc biệt khi dữ liệu ghi gần tuần tự và có TTL tương đối đồng đều.

Khái niệm đơn giản:

1. SSTables chứa dữ liệu có **write timestamps** được phân loại theo **cửa sổ thời gian**.
2. Trong **cửa sổ hiện tại**, Cassandra thực hiện compaction theo cơ chế của TWCS và phiên bản.
3. Khi một cửa sổ đã đóng, các SSTables của cửa sổ đó có thể được compact để giảm số tệp.
4. Khi toàn bộ dữ liệu trong một SSTable **đều hết hiệu lực** và thỏa điều kiện an toàn, việc loại bỏ **cả SSTable** có thể hiệu quả hơn xử lý từng tombstone.
5. Một số dữ liệu có tuổi khác nhau, overlap, reparations/streaming hoặc ghi đến muộn có thể làm quá trình đó kém hiệu quả.

TWCS **không phải lịch chạy SQL `DELETE WHERE occurred_at < ...`**. Nó cũng không tự sắp xếp hàng theo `occurred_at`: thứ tự query do **partition/clustering key** quyết định.

### 6.1. Ví dụ cửa sổ theo ngày

~~~text
Write timestamps             Cửa sổ TWCS
------------------------------------------------
25/11 00:00 - 23:59       -> Window W25
26/11 00:00 - 23:59       -> Window W26
27/11 00:00 - 23:59       -> Window W27

SSTable A: chỉ chứa cell thuộc W25
SSTable B: chỉ chứa cell thuộc W26

Nếu TTL tương tự nhau:
    A có thể hết hiệu lực cùng giai đoạn.
    B hết hiệu lực muộn hơn.

Nhưng:
    SSTable C chứa cell cũ W25 và cell mới W27
    -> việc bỏ cả SSTable có thể bị chặn bởi cell còn sống.
~~~

Ví dụ này để diễn giải nguyên lý. TWCS phân loại **SSTable** dựa trên thông tin write timestamp (đặc biệt cực đại timestamp của dữ liệu trong SSTable theo logic triển khai), không tách từng cell ra đúng một file cho từng ngày. Vì vậy **một SSTable chứa cell với timestamp rất khác nhau** là tình huống gây khó cho retention.

### 6.2. Cấu hình TWCS trong CQL

~~~sql
CREATE TABLE telemetry_events_by_device_day (
    tenant_id uuid,
    device_id uuid,
    day_bucket date,
    occurred_at timestamp,
    event_id uuid,
    ingested_at timestamp,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, day_bucket), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC)
  AND default_time_to_live = 604800
  AND compaction = {
      'class': 'TimeWindowCompactionStrategy',
      'compaction_window_unit': 'DAYS',
      'compaction_window_size': '1'
  };
~~~

Đây là **mẫu schema để thử nghiệm**, không phải một bộ thông số tối ưu cho mọi workload. Hãy kiểm tra đúng phiên bản/distribution Cassandra và điều chỉnh window size, TTL, kích thước partition, compaction throughput dựa trên số liệu thực tế.

**Chú ý:** `compaction_window_unit='DAYS'` và `compaction_window_size='1'` mô tả **cửa sổ compaction một ngày**, không buộc mọi partition có `day_bucket` cùng một ngày, cũng không bắt TTL kết thúc ngay ranh giới nửa đêm.

## 7. Chọn cửa sổ compaction dựa vào TTL và write pattern

Không có công thức “TTL bảy ngày ⇒ window một ngày” đúng trong mọi trường hợp, nhưng có những câu hỏi hữu ích:

| Câu hỏi | Gợi ý xem xét |
|---|---|
| Các cell có TTL gần bằng nhau không? | Càng đồng nhất, càng dễ xác định SSTable hết hạn toàn bộ |
| Workload có ghi gần tuần tự theo ingestion time không? | TWCS thường thuận lợi hơn với append-only, ít update cũ |
| Sự kiện đến trễ bao nhiêu? | Backfill/late arrivals tạo overlap và lệch cửa sổ |
| TTL là 1 ngày, 7 ngày hay 365 ngày? | Window quá lớn có thể chứa dữ liệu với thời điểm hết hạn trải rộng |
| Mỗi ngày tạo bao nhiêu SSTable? | Window nhỏ tạo nhiều nhóm; cần cân bằng số file và overhead |
| Có delete/update TTL thường xuyên trên hàng cũ không? | Có thể trì hoãn purge và làm tombstone scan nặng |
| Mức compaction throughput/disk/repair ra sao? | Window size không giải quyết backlog hoặc thiếu tài nguyên |

Lựa chọn cần **benchmark** trên dữ liệu có phân phối giống production: ingestion rate, thiết bị nóng, late-event ratio, phân bố TTL, kích thước payload, tần suất sửa/xóa và các truy vấn quan trọng.

### 7.1. TTL đồng nhất giúp “drop whole SSTable”

Giả sử phần lớn sự kiện ghi gần lúc phát sinh, TTL đều là 7 ngày, và một SSTable chứa gần như toàn bộ cell được ghi trong khoảng 25/11:

~~~text
Cell A: ghi 25/11 09:00, TTL 7 ngày -> hết hạn 02/12 09:00
Cell B: ghi 25/11 09:10, TTL 7 ngày -> hết hạn 02/12 09:10
Cell C: ghi 25/11 10:00, TTL 7 ngày -> hết hạn 02/12 10:00

Khi mọi cell đã hết hiệu lực và điều kiện an toàn thỏa,
SSTable trở thành ứng viên có thể bỏ trọn.
~~~

Nếu cùng SSTable lại chứa một cell không TTL, hoặc TTL 90 ngày, không thể vứt cả tệp chỉ vì 99% dữ liệu đã hết hạn. Đây là lý do **không nên trộn retention quá khác nhau trong cùng bảng/SSTable** mà chưa đánh giá hậu quả.

### 7.2. TTL không cùng tuổi có thể gây giữ dữ liệu quá lâu

~~~text
SSTable S:
    99.999 cell TTL 1 ngày
    1 cell TTL 180 ngày

Sau ngày thứ 2:
    gần như toàn bộ dữ liệu đã hết hạn logic,
    nhưng SSTable S có thể còn cell sống 180 ngày.

=> "Drop whole SSTable" không thực hiện được chỉ vì 99.999 cell hết TTL.
~~~

Compaction vẫn có thể xử lý và loại bỏ dữ liệu theo những điều kiện cụ thể, nhưng **mất lợi thế quan trọng** của việc thu dọn nguyên SSTable đồng tuổi. Nếu có chính sách giữ metadata lâu hơn payload, hãy cân nhắc **tách bảng** với TTL/compaction policy riêng, thay vì gán nhiều tuổi khác nhau vào một nhóm cell.

## 8. Sự kiện đến muộn: hai lựa chọn retention

Một event xảy ra 20/11 nhưng nhận vào 25/11. Nó được ghi vào **partition ngày 20/11** theo `day_bucket=LocalDate(occurred_at)`. Dù vậy, timestamp metadata mặc định của mutation thuộc **thời điểm ghi ngày 25/11**.

### 8.1. Retention theo ingestion time

~~~text
occurred_at = 20/11 12:00
ingested_at = 25/11 09:00
TTL = 604800 giây

Hết TTL xấp xỉ 02/12 09:00,
dù day_bucket vẫn là 20/11.
~~~

Đây có thể là chính sách hợp lý nếu mục tiêu là **giữ mỗi dữ liệu bảy ngày sau khi hệ thống nhận**, chứ không phải “không giữ dữ liệu sự kiện quá bảy ngày tuổi”.

### 8.2. Retention theo event time

Nếu policy là hết hạn bảy ngày từ lúc xảy ra:

~~~text
deadline = occurred_at + 7 ngày
remaining = deadline - trustedIngestionNow

Nếu remaining <= 0:
    bỏ qua sự kiện hoặc xử lý bằng quy trình chính sách riêng.
Nếu remaining > 0:
    ghi với TTL còn lại (giây), sau khi áp giới hạn hợp lệ.
~~~

Phải sử dụng **đồng hồ backend đáng tin cậy** và kiểm tra event time do thiết bị báo. Đừng để mobile/IoT client chỉnh `occurred_at=2099` nhằm kéo dài retention vô hạn. Khi chuyển `Duration` sang TTL nguyên giây cần xác định chính sách làm tròn và sai số chấp nhận được; không dùng số TTL bằng 0 như một cách xóa đại trà nếu chưa kiểm tra semantics theo version.

### 8.3. Lựa chọn này ảnh hưởng TWCS thế nào?

- Retention **theo ingestion time** có thể làm các cell ghi cùng cửa sổ gần như hết TTL cùng thời điểm, thuận lợi cho TWCS.
- Retention **theo event time** khiến các event khác tuổi nhưng đến cùng một ngày có **TTL còn lại khác nhau**. Khi trộn vào cùng SSTable, thời điểm hết hạn có thể rất khác, làm giảm cơ hội drop whole SSTable.
- Nếu dữ liệu quá cũ, **bỏ qua/backfill vào tầng archive riêng** có thể phù hợp hơn đưa vào bảng online có TTL ngắn.

Không nên đánh đổi chính sách lưu giữ bắt buộc chỉ để làm TWCS đẹp; thay vào đó, **tách các luồng dữ liệu/bảng** hoặc thiết kế backfill có kiểm soát.

## 9. Ghi đến muộn và write timestamp quá khứ là hai việc khác nhau

Có hai cách backfill với event time cũ:

**A — Ghi bây giờ, giữ event time trong cột:**

~~~text
occurred_at = 20/11
write timestamp metadata ≈ 25/11 (thời điểm thực sự ghi)
~~~

**B — Ghi bây giờ nhưng ép write timestamp theo event time:**

~~~sql
-- NGUY HIỂM nếu không có protocol metadata được kiểm soát.
INSERT INTO telemetry_events_by_device_day (
    tenant_id, device_id, day_bucket, occurred_at, event_id,
    event_type, payload
) VALUES (?, ?, ?, ?, ?, ?, ?)
USING TIMESTAMP ?;
~~~

Trong B, `USING TIMESTAMP ?` đặt write timestamp **micro giây** từ event time (nếu ứng dụng cố làm như vậy). Điều này có thể:

1. Khiến mutation **thua** một version đã có timestamp lớn hơn của cùng cell.
2. Tạo dữ liệu với write timestamp không khớp với thời điểm SSTable được flush.
3. Đưa giá trị metadata rất cũ/mới bất thường vào các nhóm SSTable, gây **out-of-order write** và khó tối ưu TWCS.
4. Khi replay khác nhau giữa services, gây lỗi LWW và retention khó chẩn đoán.

**Không tự động lấy `Instant eventTime` làm write timestamp**. Cột event time phục vụ query ordering; write timestamp phục vụ replica reconciliation. Chúng giải quyết **hai bài toán khác nhau**.

## 10. Update/delete vào dữ liệu cũ làm TWCS khó hơn

TWCS thường phù hợp với **immutable, append-mostly data**. Khi ứng dụng sửa một hàng cũ:

~~~text
Ngày 20/11: INSERT event E, payload="A"
Ngày 25/11: UPDATE cùng event E, payload="B"
Ngày 27/11: DELETE payload của E
~~~

Cassandra có thể có nhiều phiên bản cell/tombstone của cùng key trong các SSTable được tạo ở những cửa sổ khác nhau. Khi đọc, Cassandra cần hòa giải chúng theo **write timestamp**. Các SSTable chứa dữ liệu cũ và dấu xóa mới có thể không được purge độc lập cho đến khi an toàn.

Một số hệ quả:

- Đọc hàng cũ có thể chạm nhiều SSTable hoặc nhiều version.
- Tombstone quét qua query có thể tăng, dù chỉ trả vài chục live rows.
- Hỗn hợp dữ liệu từ các thời điểm ghi cách xa nhau làm giảm khả năng drop whole SSTable.
- TWCS không tự sửa được hot partition, update-heavy write pattern hoặc thiết kế TTL không nhất quán.

Nếu business yêu cầu sửa dữ liệu lịch sử liên tục, cần cân nhắc **mô hình lưu trữ khác**, tách dữ liệu mutable khỏi immutable time series hoặc chọn compaction strategy khác sau benchmark. Không áp dụng TWCS chỉ vì bảng có cột `occurred_at`.

### 10.1. Repair/streaming cũng cần được tính đến

Các quy trình repair, streaming, rebuild hoặc migration có thể tạo SSTable chứa dữ liệu từ nhiều mốc write timestamp và tuổi TTL. Một số phiên bản/thiết lập Cassandra có cách xử lý để giảm tác động, nhưng **không được giả định** compaction luôn giữ được ranh giới cửa sổ lý tưởng sau các sự kiện vận hành này.

Cần kiểm tra kết quả sau backfill/repair: số SSTable, SSTable timestamps, compaction backlog, tombstone scans và dung lượng thu hồi.

## 11. Tombstone, gc_grace_seconds và khả năng purge

Khi TTL hết hạn, Cassandra không chỉ “đặt giá trị thành null rồi quên”. Thông tin hết hạn/tombstone giúp các replica tránh làm sống lại phiên bản cũ. Dữ liệu vật lý vẫn có thể nằm trong các SSTable cho tới khi compaction và điều kiện an toàn cho phép loại bỏ.

Ba giá trị thường bị lẫn:

| Thông số | Đơn vị | Trả lời câu hỏi |
|---|---|---|
| `USING TTL 604800` | Giây | **Giá trị live** còn được giữ bao lâu? |
| `gc_grace_seconds` | Giây | Cần cân nhắc thời gian bảo vệ dấu xóa để đồng bộ replica trước khi purge như thế nào? |
| `compaction_window_size/unit` | Cửa sổ thời gian | SSTables được nhóm/compact theo những khoảng write timestamp nào? |

**Không có quan hệ đồng nhất** như `gc_grace_seconds = TTL` hay `TWCS window = TTL`. Chúng phục vụ các mục đích khác nhau.

### 11.1. Quy trình hết hạn và thu dọn

~~~text
T0: INSERT payload, TTL 7 ngày
 |
 | Dữ liệu đang live
 v
T1: Đến thời điểm TTL hết hạn
 |
 | Không còn trả payload như giá trị live.
 | Thông tin expiration/tombstone vẫn cần được quản lý.
 v
T2: Repair/replica và các điều kiện an toàn đã được xét
 |
 | SSTable overlap và dữ liệu còn live được kiểm tra.
 v
T3: Compaction có thể bỏ các dữ liệu đã hết hiệu lực,
    thậm chí bỏ nguyên SSTable nếu đủ điều kiện.
~~~

**TWCS không tự cam kết T3 xảy ra đúng lúc T1.** Trễ compaction, SSTable chứa cell lâu sống hơn, overlap, tombstone và điều kiện an toàn có thể khiến dung lượng chưa giảm ngay.

### 11.2. Vì sao không tùy tiện đặt gc_grace_seconds = 0?

Một replica có thể đã offline trong thời gian delete/TTL được áp dụng. Nếu tombstone bị purge trước khi replica đó được đồng bộ đúng cách, dữ liệu cũ có thể quay lại (*zombie data*) trong một số kịch bản.

Vì vậy:

- `gc_grace_seconds` gắn với **repair cadence**, tình trạng replica, cách Cassandra xử lý tombstone và chiến lược compaction.
- Một số workload/kiến trúc có thể có ngoại lệ cho phép grace thấp hơn, nhưng phải căn cứ hướng dẫn **đúng phiên bản/distribution** và đánh giá rủi ro.
- **Không áp dụng `gc_grace_seconds=0` như công thức chung** cho mọi bảng TWCS.
- Compaction không thay thế repair; cũng không xóa bản sao trong backup/snapshot.

### 11.3. TWCS không thay chính sách xóa dữ liệu nhạy cảm

Nếu có yêu cầu pháp lý “xóa dữ liệu người dùng ngay lập tức”, TTL/TWCS **không chứng minh** việc xóa vật lý đồng thời trên mọi SSTable, replica, backup hoặc snapshot. Cần chính sách quản lý dữ liệu cá nhân, backup retention, kiểm soát truy cập và quy trình xóa/đối soát đáp ứng yêu cầu thực tế.

## 12. Java: tạo day_bucket nhất quán bằng UTC

Việc `day_bucket` được tính ở nhiều service khác nhau có thể dẫn tới ghi trùng hai partition nếu service A dùng UTC còn service B dùng múi giờ hệ điều hành.

Một hàm xác định rõ policy:

~~~java
package example.telemetry;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

public final class TimeBuckets {
    private TimeBuckets() {}

    public static LocalDate utcDay(Instant eventTime) {
        if (eventTime == null) {
            throw new IllegalArgumentException("eventTime is required");
        }
        return eventTime.atZone(ZoneOffset.UTC).toLocalDate();
    }
}
~~~

Ví dụ:

~~~text
2026-11-25T23:30:00Z
    UTC day_bucket = 2026-11-25

2026-11-26T06:30:00+07:00
    Cùng một instant, UTC day_bucket = 2026-11-25
~~~

Dùng chung hàm tính bucket cho **ghi, đọc, xóa và replay**. Nếu sản phẩm cần ngày theo timezone địa phương, chọn zone cố định theo tenant với hợp đồng rõ, xử lý DST khi có và không phụ thuộc timezone mặc định của máy.

### 12.1. Kiểm tra event time trước khi tạo key

`Instant` có thể mang precision nano giây, trong khi CQL `timestamp` biểu diễn mili giây. Vì `occurred_at` còn là **clustering column**, hãy chuẩn hóa trước khi tạo key để retry không vô tình ghi ra khóa khác:

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

static Instant normalizeEventTime(Instant original) {
    if (original == null) {
        throw new IllegalArgumentException("event time is required");
    }
    return original.truncatedTo(ChronoUnit.MILLIS);
}
~~~

Đây là chính sách **truncate có chủ đích**. Nếu yêu cầu không được mất nano giây, phải định nghĩa cấu trúc lưu khác hoặc từ chối giá trị không có precision phù hợp. `event_id` vẫn nên ổn định để phân biệt hai event cùng mili giây.

## 13. Entity mapping Spring Data Cassandra

Lớp khóa ghép:

~~~java
package example.telemetry;

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
public class TelemetryEventKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "device_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(name = "day_bucket", ordinal = 2,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate dayBucket;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 4,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.ASCENDING)
    private UUID eventId;

    public TelemetryEventKey() {}

    public TelemetryEventKey(
            UUID tenantId, UUID deviceId, LocalDate dayBucket,
            Instant occurredAt, UUID eventId) {
        this.tenantId = tenantId;
        this.deviceId = deviceId;
        this.dayBucket = dayBucket;
        this.occurredAt = occurredAt;
        this.eventId = eventId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }
    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }
    public LocalDate getDayBucket() { return dayBucket; }
    public void setDayBucket(LocalDate value) { dayBucket = value; }
    public Instant getOccurredAt() { return occurredAt; }
    public void setOccurredAt(Instant value) { occurredAt = value; }
    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    @Override
    public boolean equals(Object candidate) {
        if (this == candidate) return true;
        if (!(candidate instanceof TelemetryEventKey)) return false;
        TelemetryEventKey that = (TelemetryEventKey) candidate;
        return Objects.equals(tenantId, that.tenantId)
                && Objects.equals(deviceId, that.deviceId)
                && Objects.equals(dayBucket, that.dayBucket)
                && Objects.equals(occurredAt, that.occurredAt)
                && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(
                tenantId, deviceId, dayBucket, occurredAt, eventId);
    }
}
~~~

`ordinal` mô tả vị trí trên **toàn bộ primary key**, từ 0 tới 4; ba phần đầu là `PARTITIONED`, hai phần sau là `CLUSTERED`. Package của `PrimaryKeyType` là `org.springframework.data.cassandra.core.cql`.

Entity:

~~~java
package example.telemetry;

import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("telemetry_events_by_device_day")
public class TelemetryEvent {
    @PrimaryKey
    private TelemetryEventKey id;

    @Column("ingested_at")
    private Instant ingestedAt;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    public TelemetryEvent() {}

    public TelemetryEvent(
            TelemetryEventKey id, Instant ingestedAt,
            String eventType, String payload) {
        this.id = id;
        this.ingestedAt = ingestedAt;
        this.eventType = eventType;
        this.payload = payload;
    }

    public TelemetryEventKey getId() { return id; }
    public void setId(TelemetryEventKey value) { id = value; }
    public Instant getIngestedAt() { return ingestedAt; }
    public void setIngestedAt(Instant value) { ingestedAt = value; }
    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }
    public String getPayload() { return payload; }
    public void setPayload(String value) { payload = value; }
}
~~~

Hai class `public` phải đặt trong **hai file Java riêng**, cùng package. Spring Data mapping biểu diễn dữ liệu trong bảng và key; **nó không tự bật TWCS hoặc biến `occurredAt` thành write timestamp**. Schema/compaction/TTL phải được kiểm soát qua migration CQL và chính sách write options phù hợp.

## 14. Repository, CassandraTemplate và paging

Repository cho API đọc theo một bucket:

~~~java
package example.telemetry;

import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface TelemetryEventRepository
        extends CassandraRepository<TelemetryEvent, TelemetryEventKey> {

    @Query("SELECT * FROM telemetry_events_by_device_day " +
           "WHERE tenant_id = ?0 AND device_id = ?1 " +
           "AND day_bucket = ?2")
    Slice<TelemetryEvent> findInDay(
            UUID tenantId, UUID deviceId,
            LocalDate dayBucket, Pageable pageable);
}
~~~

Bắt đầu và tiếp tục phân trang:

~~~java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

Slice<TelemetryEvent> first = repository.findInDay(
        tenantId, deviceId, day,
        CassandraPageRequest.first(50));

if (first.hasNext()) {
    Slice<TelemetryEvent> second = repository.findInDay(
            tenantId, deviceId, day,
            first.nextPageable());
}
~~~

**Không dùng `CassandraPageRequest.first(50)` lại ở trang hai**, vì sẽ quay lại đầu. Không áp paging state của bucket 25/11 cho bucket 24/11; đây là hai câu truy vấn/partition khác nhau.

### 14.1. Đường CassandraTemplate

`CassandraOperations` có thể dùng `Query/Criteria` và trả `Slice`:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public Slice<TelemetryEvent> readBucket(
        CassandraOperations operations, UUID tenantId,
        UUID deviceId, LocalDate day, Pageable pageable) {

    Query base = Query.query(
            Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("device_id").is(deviceId))
            .and(Criteria.where("day_bucket").is(day));

    return operations.slice(
            base.pageRequest(pageable), TelemetryEvent.class);
}
~~~

`Query.pageRequest(pageable)` trả về query được gắn paging state/options; **không bỏ qua giá trị trả về** khi dựng request mới. Query vẫn phải theo **đường khóa** hợp lệ.

### 14.2. Vì sao page size nhỏ không chữa tombstone scan?

Một partition có thể chứa 50.000 cell hết TTL và chỉ 20 cell đang live. Để trả đủ hàng live, Cassandra **có thể phải xét nhiều tombstone** dù client đặt `pageSize=20` hoặc `LIMIT 20`.

Nếu p99 cao, cần xem:

- Tỷ lệ cell hết hạn trong các partition đang đọc.
- Số SSTable, overlap, compaction backlog và repair.
- Time buckets quá lớn, hot partitions hoặc sự kiện đến trễ.
- Cách giữ TTL đồng nhất và chiến lược TWCS.

**Pagination điều khiển kích thước fetch**, không tự làm compaction nhanh hơn hoặc xóa tombstone khỏi disk.

## 15. Ghi với TTL rõ ràng bằng Java Driver

Dùng prepared CQL khi cần điều chỉnh TTL theo từng event (ví dụ retention theo event time). Đoạn writer sau dùng một `PreparedStatement` được chuẩn bị một lần:

~~~java
package example.telemetry;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class TelemetryIngestWriter {
    private final CqlSession session;
    private final PreparedStatement insert;
    private final Clock clock;

    public TelemetryIngestWriter(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.insert = session.prepare(
                "INSERT INTO telemetry_events_by_device_day " +
                "(tenant_id, device_id, day_bucket, occurred_at, " +
                "event_id, ingested_at, event_type, payload) " +
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) USING TTL ?");
    }

    public boolean storeWithinEventRetention(
            UUID tenantId, UUID deviceId, UUID eventId,
            Instant eventTime, String eventType, String payload) {

        Instant occurred = normalizeToMillis(eventTime);
        Instant now = clock.instant();
        Instant deadline = occurred.plus(Duration.ofDays(7));

        // Sự kiện đã quá hạn theo policy: không đưa vào bảng online.
        if (!deadline.isAfter(now)) {
            return false;
        }

        long remainingSeconds =
                Duration.between(now, deadline).getSeconds();

        if (remainingSeconds <= 0 ||
                remainingSeconds > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Unsupported TTL range");
        }

        LocalDate bucket = TimeBuckets.utcDay(occurred);

        session.execute(insert.bind(
                tenantId, deviceId, bucket, occurred, eventId,
                now, eventType, payload, (int) remainingSeconds));
        return true;
    }

    private static Instant normalizeToMillis(Instant value) {
        return value.truncatedTo(
                java.time.temporal.ChronoUnit.MILLIS);
    }
}
~~~

Giả định `eventId` ổn định và dữ liệu đã được validate. Khi dùng `Duration.getSeconds()`, thời gian còn lại bị **lấy phần nguyên giây**. Cần kiểm tra rounding, độ trễ request, server clock và giới hạn TTL của **phiên bản Cassandra** trước khi dùng production. Đoạn ví dụ chỉ đưa ra một policy có chủ đích; **không cam kết hết hạn đúng từng mili giây**.

Nếu policy là retention theo **ingestion time**, thay vì tính TTL còn lại, hãy dùng TTL cố định hoặc `default_time_to_live` của bảng. Không đặt đồng thời những cơ chế TTL chồng chéo mà chưa kiểm chứng precedence của version server.

### 15.1. Vì sao Spring Data repository.save() chưa đủ để diễn đạt TTL khác nhau?

~~~java
repository.save(event);
~~~

`save` làm nhiệm vụ ánh xạ và ghi entity; **không nên mặc định** rằng TTL sẽ được suy ra từ `event.getId().getOccurredAt()`. Nếu dùng `InsertOptions`/`UpdateOptions` của Spring Data, phải xác minh API tương ứng phiên bản dependency, cách áp dụng TTL cho những cột được ghi và kết quả CQL trên test cluster.

Với bài toán TTL tính theo từng event, câu CQL prepared có `USING TTL ?` khiến policy trở nên **tường minh**; repository/`CassandraTemplate` có thể được dùng cho đọc/CRUD khác theo đúng contract.

### 15.2. Tránh refresh TTL ngoài ý muốn khi retry

Giả sử cùng `eventId`, cùng khóa được ghi lại sau 1 giờ:

- Nếu mỗi lần retry dùng **TTL cố định 7 ngày**, TTL của các cell được ghi lại có thể bắt đầu lại và **kéo dài retention**.
- Nếu policy là **event-time deadline cố định**, mỗi retry phải tính **phần TTL còn lại tới cùng deadline** và không tạo event ID mới.
- Dù vậy, việc retry với write timestamp mới có thể ghi đè mutation cạnh tranh; cần chính sách idempotency/sequence và cách phân loại retries phù hợp.

Với dữ liệu có yêu cầu “không bao giờ gia hạn TTL sau lần ghi đầu”, hãy thiết kế một protocol ingestion/deduplication rõ ràng; chỉ tính lại `remaining` không tự giải quyết mọi race giữa nhiều writer.

## 16. Kiểm chứng TTL và write timestamp bằng CQL

Sau khi ghi một event bằng TTL, đọc:

~~~sql
SELECT occurred_at, ingested_at, event_type, payload,
       TTL(payload) AS payload_ttl_seconds,
       WRITETIME(payload) AS payload_write_us
FROM telemetry_events_by_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

Ý nghĩa:

| Giá trị | Diễn giải |
|---|---|
| `occurred_at` | CQL `timestamp` của sự kiện |
| `ingested_at` | CQL `timestamp` lúc backend nhận |
| `TTL(payload)` | Số giây TTL còn lại của **cell live** có TTL |
| `WRITETIME(payload)` | Write timestamp metadata **micro giây** của cell live |

Khi `payload` đã hết hạn hoặc không có giá trị, `TTL(payload)`/`WRITETIME(payload)` không phải công cụ thống kê tombstone trong SSTable. Một `null` khi đọc **không chứng minh** đã thu hồi không gian vật lý.

### 16.1. Đọc config bảng từ system_schema

~~~sql
SELECT table_name, default_time_to_live,
       gc_grace_seconds, compaction
FROM system_schema.tables
WHERE keyspace_name = 'telemetry_ks'
  AND table_name = 'telemetry_events_by_device_day';
~~~

Đối chiếu `compaction` map với `TimeWindowCompactionStrategy`, `compaction_window_unit` và `compaction_window_size`. Thay `telemetry_ks` bằng keyspace của môi trường test/ứng dụng.

**Không chỉ tin file cấu hình Java hoặc annotation**; hãy đọc schema vật lý thực sự. Nhưng `system_schema.tables` chỉ phản ánh DDL **đang áp dụng**, không đo trực tiếp hiệu quả compaction. Hiệu quả cần xem metrics và SSTable statistics trên tập dữ liệu đại diện.

## 17. Integration tests: kiểm tra TTL logic, không đoán thời điểm purge

Các test này cần Cassandra test instance, keyspace/bảng provision qua migration, có sự cô lập fixture; **không chạy trực tiếp trên production**.

### 17.1. Test TTL giảm theo thời gian

Một integration test có thể dùng TTL ngắn (vài giây) và kiểm tra:

1. INSERT có TTL, dùng full primary key.
2. Ngay sau ghi, `TTL(payload)` dương và không vượt TTL được đặt (cho phép sai số giây).
3. Sau khi hết thời hạn với một **polling deadline**, `payload` không còn live.
4. Phân biệt “không còn live” với “SSTable vật lý đã được xóa”.
5. Dùng một fixture mới cho test khác, tránh cell/tombstone còn tồn tại từ phép thử trước.

Ví dụ JUnit + Java Driver, kiểm tra **logic TTL**:

~~~java
package example.telemetry;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class TelemetryTtlIntegrationTest {
    @Autowired CqlSession session;

    @Test
    void payloadExpiresButOtherPermanentCellRemains()
            throws InterruptedException {

        UUID tenant = UUID.randomUUID();
        UUID device = UUID.randomUUID();
        UUID event = UUID.randomUUID();
        LocalDate day = LocalDate.of(2026, 11, 25);
        Instant occurred = Instant.parse("2026-11-25T09:00:00Z");

        PreparedStatement insert = session.prepare(
                "INSERT INTO telemetry_events_by_device_day " +
                "(tenant_id, device_id, day_bucket, occurred_at, " +
                "event_id, event_type) " +
                "VALUES (?, ?, ?, ?, ?, ?)");
        session.execute(insert.bind(
                tenant, device, day, occurred, event, "SCAN"));

        PreparedStatement writePayload = session.prepare(
                "UPDATE telemetry_events_by_device_day " +
                "USING TTL 3 SET payload = ? " +
                "WHERE tenant_id = ? AND device_id = ? " +
                "AND day_bucket = ? AND occurred_at = ? AND event_id = ?");
        session.execute(writePayload.bind(
                "short-lived", tenant, device, day, occurred, event));

        PreparedStatement select = session.prepare(
                "SELECT event_type, payload, TTL(payload) AS ttl_s " +
                "FROM telemetry_events_by_device_day " +
                "WHERE tenant_id = ? AND device_id = ? " +
                "AND day_bucket = ? AND occurred_at = ? AND event_id = ?");

        Row initial = session.execute(
                select.bind(tenant, device, day, occurred, event)).one();
        assertNotNull(initial);
        assertEquals("short-lived", initial.getString("payload"));
        assertNotNull(initial.getObject("ttl_s"));

        boolean expired = false;
        long deadline = System.nanoTime()
                + java.util.concurrent.TimeUnit.SECONDS.toNanos(10);

        while (System.nanoTime() < deadline) {
            Row current = session.execute(
                    select.bind(tenant, device, day, occurred, event)).one();

            if (current != null && current.isNull("payload")) {
                assertEquals("SCAN", current.getString("event_type"));
                expired = true;
                break;
            }
            Thread.sleep(200);
        }

        assertTrue(expired, "TTL cell did not expire before test deadline");
    }
}
~~~

**Điều kiện test:** bảng của test phải **không có default TTL** đang áp dụng cho `event_type` (hoặc test phải cung cấp policy ghi không TTL được hỗ trợ), nếu không cả event có thể hết hạn cùng lúc. Vì trong phần 6 ta có bảng ví dụ bật `default_time_to_live=604800`, khi chạy test này nên provision **bảng test cùng cột nhưng default TTL = 0** hoặc điều chỉnh fixture để tách biệt TTL của `payload`.

Test dùng `Thread.sleep` ngắn trong vòng polling chỉ ở **môi trường integration test**; nó không phải lựa chọn cho service runtime. Cần xem đồng hồ Cassandra, phiên bản TTL, consistency và độ ổn định hạ tầng nếu test flaky. Trong STEP 4 **chưa chạy** JUnit/Gradle.

### 17.2. Test event-time retention và late arrivals

Lập test với `Clock.fixed` và hai event:

~~~text
now = 2026-11-25T09:00:00Z

Event A:
    occurred_at = 2026-11-25T08:00:00Z
    retention = 7 ngày
    remaining TTL ≈ 6 ngày 23 giờ

Event B:
    occurred_at = 2026-11-10T08:00:00Z
    retention = 7 ngày
    remaining TTL < 0
    => writer không đưa vào bảng online
~~~

Kiểm tra `TimeBuckets.utcDay` trả đúng ngày UTC và `eventId` giữ nguyên qua retry. Test kết quả CQL của event A trên test cluster; với event B kiểm tra writer trả trạng thái “đã quá retention” mà không gửi INSERT.

**Đừng nhầm** việc sử dụng `Clock.fixed` để tính TTL trong Java với đồng hồ thực của Cassandra. End-to-end test phải xem deadline/clock skew được cấu hình và phạm vi sai số cho phép.

### 17.3. Test TWCS không phải unit test vài giây

Một test có thể xác nhận DDL đã bật `TimeWindowCompactionStrategy`, nhưng **không thể kết luận chiến lược giảm tombstone scan tốt** chỉ bằng một test ghi năm hàng và đợi TTL 3 giây.

Đánh giá TWCS cần benchmark hoặc staging test với:

- Nhiều SSTables tạo qua flush/compaction tự nhiên hoặc kịch bản được kiểm soát.
- Dữ liệu append-only có TTL đồng nhất so với dữ liệu trộn TTL và nhiều late arrivals.
- Repair/streaming/backfill phù hợp.
- Cửa sổ compaction, backlog, disk usage, read latency, tombstone scan.
- Cấu hình replication/consistency đại diện.

Không ép compaction/flush lặp vô hạn trong production để “chứng minh” một ví dụ học thuật.

## 18. Giám sát hiệu năng và đánh giá lựa chọn TWCS

| Nhóm metric | Điều cần quan sát |
|---|---|
| **Write** | Events/sec, latency, batch size, retry, late-arrival lag, write timeout |
| **Partition** | Rows/partition, bytes/partition, số bucket nóng, hot devices |
| **Read** | p50/p95/p99, SSTables per read, tombstones scanned, timeouts |
| **TTL** | Tỷ lệ cell hết TTL, phân bố TTL, deadline policy violations |
| **Compaction** | SSTables count, pending tasks/backlog, throughput, disk usage |
| **Repair** | Lịch repair, replica unavailable, khoảng thời gian replica bỏ lỡ mutation |
| **Data quality** | Duplicate event IDs, event-time skew, out-of-order ingest, schema mismatch |

Trong môi trường có công cụ phù hợp, `nodetool tablestats` và `nodetool compactionstats` có thể hỗ trợ quan sát bảng/compaction; lệnh cụ thể, quyền truy cập và tên metrics khác nhau theo phiên bản/bản phân phối. **Không chạy công cụ chẩn đoán nặng trên production mà thiếu kiểm soát vận hành.**

### 18.1. Checklist trước khi quyết định window size

Hãy lấy dữ liệu thật hoặc dataset đại diện, sau đó trả lời:

1. Trong mỗi cửa sổ một ngày, bao nhiêu SSTable được tạo, bao nhiêu bị compact?
2. TTL có cùng 7 ngày cho mọi cell không, hay một vài cột tồn tại 30/90 ngày?
3. Tỷ lệ event đến trễ trên 1 giờ/1 ngày/1 tuần là bao nhiêu?
4. Có replay/backfill dùng `USING TIMESTAMP` metadata trong quá khứ không?
5. Các update lên hàng cũ có thường xuyên không?
6. Khi TTL hết hạn, bao lâu disk usage thực sự giảm và vì sao?
7. p99 query theo partition nào bị ảnh hưởng mạnh bởi tombstones?
8. Nếu đổi sang time bucket nhỏ hơn, chi phí đọc nhiều partition tăng thế nào?

**Không chọn window size chỉ theo một công thức tỉ lệ TTL**, và không so sánh chỉ bằng số byte lưu. Cần cân bằng write amplification, read amplification, số SSTable, khả năng purge và vận hành.

## 19. Những lỗi thường gặp

| Hiểu lầm hoặc lỗi | Vì sao sai | Hướng xử lý |
|---|---|---|
| Chia `day_bucket` là TWCS tự hiểu ngày sự kiện | Bucket là khóa, TWCS dựa vào write timestamps/SSTables | Phân biệt ba cơ chế |
| TTL bảy ngày luôn tính từ `occurred_at` | TTL của mutation không tự dùng event time | Chọn retention theo ingest hoặc tính remaining |
| Bật TWCS là tự purge đúng giờ TTL | Purge còn phụ thuộc compaction/overlap/an toàn | Theo dõi disk/repair, không hứa giờ cố định |
| Mixed TTL 1 ngày và 90 ngày trong cùng bảng là miễn phí | SSTable có cell sống lâu khó drop trọn | Tách retention policies khi phù hợp |
| Replay cũ dùng write timestamp event time | Có thể gây LWW bất thường và lệch TWCS windows | Giữ event time trong cột, kiểm soát metadata |
| Mỗi retry INSERT cùng eventId với TTL cố định | TTL của cell có thể bị gia hạn | Giữ deadline/command ID, kiểm tra semantics |
| Update/delete liên tục lên hàng cũ vẫn tối ưu TWCS | Tạo phiên bản/tombstone chồng cửa sổ | Chọn mô hình append-only hoặc strategy phù hợp |
| Giảm `gc_grace_seconds` về 0 để tiết kiệm đĩa | Rủi ro zombie nếu thiếu điều kiện an toàn | Phối hợp repair và quy trình vận hành |
| `SELECT` không thấy payload nghĩa là đã xóa vật lý | Tombstones/SSTables/backups còn tồn tại | Phân biệt logical vs physical expiration |
| Giảm `pageSize` sẽ chữa tombstone scan | Storage vẫn có thể quét nhiều cell hết hạn | Sửa partition/TTL/compaction |
| Dùng `LIMIT 50` để đọc mọi event trên toàn tenant | Query thiếu partition key | Thiết kế access table hoặc điều phối partitions |
| Dùng `LocalDate.now()` cho bucket event | Sai khi event trễ hoặc timezone khác | Tính từ event time bằng zone policy |
| Một device có triệu event/ngày vẫn bucket theo ngày | Partition quá lớn/hot | Phân tách theo giờ/shard và benchmark |
| Dùng `WRITETIME(payload)` làm lịch sử sự kiện | Chỉ metadata của cell live đang thắng | Dùng event time + clustering key |
| Dùng logged batch nhiều partition để ghi nhanh | Tăng batchlog/coordinator overhead | Ghi bất đồng bộ có giới hạn concurrency |

## 20. Bài tập thực hành

Một nền tảng giám sát xe giao hàng thu thập GPS:

~~~sql
CREATE TABLE gps_points_by_vehicle_hour (
    tenant_id uuid,
    vehicle_id uuid,
    hour_bucket timestamp,
    recorded_at timestamp,
    point_id uuid,
    latitude double,
    longitude double,
    ingested_at timestamp,
    PRIMARY KEY (
        (tenant_id, vehicle_id, hour_bucket),
        recorded_at, point_id
    )
) WITH CLUSTERING ORDER BY (recorded_at DESC, point_id ASC);
~~~

**Lưu ý** `hour_bucket` ở đây dùng kiểu `timestamp` nhưng phải chuẩn hóa về **đầu giờ UTC**, không lấy `Instant.now()` của server cho bucket của một point đến trễ. Có thể cân nhắc biểu diễn bucket bằng kiểu khác và policy được xác định, miễn đọc/ghi dùng cùng công thức.

### Bài tập A — chọn retention

Bản ghi X có `recorded_at = 2026-11-20T10:00:00Z`, được server nhận `2026-11-25T12:00:00Z`. Policy giữ dữ liệu **72 giờ từ lúc ghi nhận ở xe**.

1. Sự kiện đã quá hạn chưa?
2. Có nên `INSERT USING TTL 259200` ngay khi nhận?
3. Nếu không, nên làm gì khi dữ liệu đã quá hạn?
4. Việc vẫn muốn lưu payload trong kho lưu trữ lịch sử dài hạn có ảnh hưởng policy bảng online thế nào?

### Bài tập B — chọn TWCS

Một bảng có 7 ngày TTL, mỗi ngày hàng triệu sự kiện gần realtime, chỉ 0,1% đến trễ hơn một ngày; một bảng khác lưu dimension/metadata xe **không TTL**.

Hãy giải thích vì sao nên **tách hai bảng với compaction/retention thích hợp**, thay vì trộn dimension có tuổi thọ vô hạn với GPS points có TTL ngắn vào cùng một bảng TWCS.

### Bài tập C — xử lý update lịch sử

Service A ghi vị trí vào ngày 20/11; service B đính chính payload vào 25/11. Hãy mô tả:

- Vì sao read có thể phải hòa giải hai versions?
- Điều gì xảy ra nếu service B dùng `USING TIMESTAMP` nhỏ hơn write timestamp của A?
- Tại sao sửa dữ liệu cũ thường xuyên có thể làm TWCS kém hiệu quả?
- Nếu cần lưu lịch sử chỉnh sửa, thiết kế các correction events với ID ổn định thế nào?

### Bài tập D — CQL quan sát và kiểm chứng

Viết:

~~~sql
SELECT default_time_to_live, gc_grace_seconds, compaction
FROM system_schema.tables
WHERE keyspace_name = 'your_keyspace'
  AND table_name = 'gps_points_by_vehicle_hour';

SELECT recorded_at, ingested_at,
       TTL(latitude) AS latitude_ttl_seconds,
       WRITETIME(latitude) AS latitude_write_micros
FROM gps_points_by_vehicle_hour
WHERE tenant_id = ?
  AND vehicle_id = ?
  AND hour_bucket = ?
  AND recorded_at = ?
  AND point_id = ?;
~~~

Trả lời: `TTL(latitude)` có cho biết `hour_bucket` không? `WRITETIME(latitude)` có phải `recorded_at` không? Khi TTL hết, có thể kết luận SSTable đã biến mất chưa?

### Bài tập E — paging nhiều bucket

API muốn xem 200 GPS points mới nhất của một xe trong **hai ngày**. Bảng chia theo giờ.

1. Một `Slice.nextPageable()` có dùng được cho mọi `hour_bucket` không?
2. Cần điều phối những partition nào, sắp thứ tự và lưu cursor thế nào?
3. Có nên thay schema bằng bucket ngày để giảm số request không nếu xe ghi 1.000 points/giây?
4. Bảng truy cập khác có cần thiết cho màn hình “vị trí mới nhất” không?

### Câu hỏi tự kiểm tra

1. TWCS dựa trên thời gian nào để gom SSTable: `occurred_at`, `day_bucket` hay write timestamp metadata?
2. TTL có tự lấy timestamp của cột sự kiện làm thời điểm bắt đầu không?
3. Khi nào mixed TTL khiến whole-SSTable drop khó thực hiện?
4. Vì sao backfill lịch sử có thể làm chồng các cửa sổ TWCS?
5. `gc_grace_seconds` có phải là `default_time_to_live` không?
6. Hết TTL có nghĩa dữ liệu đã biến mất khỏi snapshot/backup không?
7. Vì sao ghi lại cùng event với TTL cố định có thể kéo dài retention?
8. Một bảng time-series append-only có cần update hàng cũ liên tục không?
9. Khi nào bucket theo giờ tốt hơn bucket theo ngày?
10. `Slice`/page size có loại bỏ tombstone scan không?
11. CQL `timestamp` khác write timestamp về precision và ý nghĩa thế nào?
12. Tại sao không nên dùng một bảng TWCS cho dữ liệu TTL 7 ngày và metadata sống vô hạn?

**Đáp án ngắn:** (1) write timestamps/SSTable; (2) không; (3) khi còn cell sống dài hạn; (4) cell tuổi khác nhau có thể cùng SSTable hoặc tạo nhiều versions; (5) không; (6) không; (7) refresh TTL của cell được ghi lại; (8) nên hạn chế nếu muốn tận dụng TWCS; (9) khi partition ngày quá lớn/hot; (10) không; (11) CQL value mili giây vs metadata micro giây; (12) làm mất lợi thế bỏ nguyên SSTable hết hạn.

## 21. Checklist trước khi triển khai

- [ ] Đã định nghĩa **event time**, **ingestion time**, **write timestamp** và **TTL deadline**.
- [ ] Chính sách retention được ghi rõ là **từ lúc ghi** hay **từ lúc sự kiện xảy ra**.
- [ ] Không nhầm `day_bucket` (partition key) với `compaction_window` của TWCS.
- [ ] `occurred_at` được chuẩn hóa precision và timezone trước khi tạo clustering key.
- [ ] `event_id`/command ID ổn định qua retry và replay.
- [ ] Partition đủ nhỏ theo dữ liệu thật, không chỉ theo tên ngày/giờ.
- [ ] Query theo đầy đủ partition key; cần nhiều bucket thì có cách điều phối rõ.
- [ ] TTL mặc định và TTL riêng được chọn nhất quán; kiểm tra behavior của các phiên bản Cassandra.
- [ ] Không trộn quá nhiều policy retention trong cùng SSTable mà thiếu benchmark.
- [ ] Sự kiện quá hạn được bỏ qua/xử lý theo quy trình rõ ràng.
- [ ] Backfill/late arrivals không tùy tiện gán `USING TIMESTAMP` theo event time.
- [ ] Dữ liệu mutable được tách hoặc đánh giá riêng nếu TWCS không hiệu quả.
- [ ] Có kế hoạch compaction/repair và chính sách `gc_grace_seconds` an toàn.
- [ ] Không coi TTL/TWCS là xóa vật lý tức thì khỏi mọi backup/snapshot.
- [ ] `system_schema.tables` phản ánh đúng TTL và compaction config mong đợi.
- [ ] Đã kiểm chứng `TTL()`/`WRITETIME()` trên cột thường bằng integration test.
- [ ] Đã đo p95/p99, SSTables/read, tombstones scanned, backlog, disk usage.
- [ ] Không dựa vào pagination để sửa hot partition hoặc tombstone-heavy reads.
- [ ] Có test và giới hạn khi sửa/đổi window size/TTL trên production.
- [ ] Chưa xem bài Markdown là đã QA học thuật/CI hay đã publish.

## 22. Tổng kết

**Mẫu ghi quyết định hiệu quả TTL và TWCS.** Với dữ liệu **append-only, gần thời gian thực, TTL tương đối đồng đều**, TWCS có thể giúp gom SSTable theo write time để thu dọn dữ liệu hết hạn hiệu quả. Với **late arrivals, backfill, overwrite/delete cũ, TTL không đồng nhất**, khả năng bỏ nguyên SSTable có thể giảm và chi phí tombstone/read amplification tăng.

Đừng đánh đồng **event time** với **write timestamp**, **ngày bucket** với **cửa sổ compaction**, hoặc **hết TTL** với **đã xóa vật lý**. Hãy chọn retention theo nghiệp vụ, thiết kế key theo query, giữ idempotency và đo trên workload thực trước khi đưa TWCS vào production.

## Tài liệu tham khảo

- [Apache Cassandra — TimeWindowCompactionStrategy](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/compaction/twcs.html).
- [Apache Cassandra — Compaction](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/compaction/index.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Apache Cassandra — CQL Data Manipulation và TTL](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html).
- [Apache Cassandra — Storage Engine](https://cassandra.apache.org/doc/latest/cassandra/architecture/storage-engine.html).
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).
- [Spring Data Cassandra — Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Apache Cassandra Java Driver 4 — Prepared Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/).
