# Thiết kế bảng theo truy vấn và thứ tự đọc trong một phân vùng

Trong mô hình NoSQL **cột rộng** (*wide-column*), câu hỏi đầu tiên khi thiết kế dữ liệu thường không phải là “có những thực thể nào?” mà là **“ứng dụng sẽ đọc dữ liệu theo những khóa nào, theo thứ tự nào và với tần suất bao nhiêu?”**. Với các hệ kiểu Apache Cassandra và ScyllaDB, một bảng được tổ chức quanh **partition key** và **clustering columns**: partition key xác định nhóm dữ liệu cần truy cập, còn clustering columns xác định thứ tự các hàng bên trong nhóm ấy.

Thiết kế phù hợp giúp một truy vấn đọc được vài hàng đầu tiên của một phân vùng mà không phải quét toàn bộ dữ liệu. Thiết kế không phù hợp có thể khiến một dashboard “20 sự kiện mới nhất” phải quét nhiều phân vùng, đọc quá nhiều hàng hoặc dựa vào bộ lọc tốn kém.

Bài học này xây dựng một ví dụ xuyên suốt: **lưu các bản ghi đo của thiết bị IoT để xem dữ liệu mới nhất, tìm dữ liệu theo khoảng thời gian và tra cứu sự kiện theo ID**. Qua đó, chúng ta sẽ lựa chọn partition key, clustering key, thứ tự sắp xếp, cách chia bucket và các bảng phục vụ từng truy vấn.

> **Phạm vi:** Ví dụ dùng cú pháp CQL theo phong cách Cassandra. Một số lựa chọn về giao dịch, phân vùng vật lý, index và giới hạn vận hành khác nhau giữa các sản phẩm wide-column. Các câu lệnh là ví dụ thiết kế để học, không phải kết quả benchmark của một cluster cụ thể.

## 1. Đọc yêu cầu nghiệp vụ trước khi vẽ schema

Giả sử một nền tảng giám sát có nhiều tổ chức (*tenant*). Mỗi tổ chức có nhiều thiết bị. Một thiết bị có thể gửi các chỉ số nhiệt độ, pin và mức cảnh báo mỗi vài giây.

Một bản ghi đo:

~~~json
{
  "tenantId": "factory-a",
  "deviceId": "sensor-17",
  "readingId": "85c1bdc5-9367-4648-a283-408cfc74e5db",
  "observedAt": "2026-11-14T12:05:23Z",
  "temperatureC": 28.4,
  "batteryPercent": 83,
  "severity": "NORMAL"
}
~~~

Giữ **\`observedAt\`** là thời gian thiết bị ghi nhận dữ liệu, có thể khác thời gian server nhận \`receivedAt\`. Nếu dữ liệu gửi đến trễ hoặc sai thứ tự, dashboard vẫn phải xác định dùng thời gian nào để sắp xếp.

Các yêu cầu đọc quan trọng:

| Mã | Câu hỏi từ ứng dụng | Điều kiện lọc | Thứ tự, giới hạn |
| --- | --- | --- | --- |
| **Q1** | Lấy 20 bản ghi mới nhất của một thiết bị | \`tenantId\`, \`deviceId\` | Mới nhất trước, \`LIMIT 20\` |
| **Q2** | Xem dữ liệu thiết bị trong 30 phút | Tenant, thiết bị, khoảng thời gian | Theo thời gian, có phân trang |
| **Q3** | Tìm chi tiết bản ghi khi chỉ biết \`readingId\` | Tenant và ID bản ghi | Trả về một bản ghi |
| **Q4** | Liệt kê cảnh báo CRITICAL mới nhất của một tenant | Tenant, mức cảnh báo | Mới nhất trước, trên nhiều thiết bị |
| **Q5** | Xem nhiệt độ trung bình theo từng giờ của thiết bị | Tenant, thiết bị, khoảng giờ | Theo giờ |

Mỗi truy vấn có đường truy cập khác nhau. Đặc biệt, Q1 và Q2 luôn biết **thiết bị**, còn Q4 cần đọc **nhiều thiết bị**. Vì vậy không nên mặc định một bảng duy nhất sẽ phục vụ tốt tất cả.

### 1.1. Hình dung đường đọc

~~~mermaid
flowchart LR
    A["Dashboard: thiết bị sensor-17"] --> B["Tenant + Device + khoảng giờ"]
    B --> C["Định vị phân vùng"]
    C --> D["Đọc các hàng theo observedAt DESC"]
    D --> E["Trả 20 bản ghi mới nhất"]
~~~

Điểm đáng chú ý: nếu đầu vào đã cho biết nhóm khóa cần truy cập và các hàng trong nhóm được lưu theo thứ tự thích hợp, cơ sở dữ liệu có thể phục vụ truy vấn mà không phải sắp xếp một tập dữ liệu toàn hệ thống.

## 2. Partition key, clustering key và primary key

Trong CQL, khóa chính (*primary key*) có thể gồm hai phần:

~~~sql
PRIMARY KEY ((partition_key_columns), clustering_columns)
~~~

**Partition key** xác định phân vùng logic chứa các hàng. **Clustering columns** xác định thứ tự hàng bên trong phân vùng và giúp truy cập một đoạn có điều kiện theo các cột sắp xếp.

Ví dụ ngắn:

~~~sql
CREATE TABLE readings_demo (
    device_id text,
    event_time timestamp,
    reading_id uuid,
    value double,
    PRIMARY KEY ((device_id), event_time, reading_id)
) WITH CLUSTERING ORDER BY (event_time DESC, reading_id ASC);
~~~

Ở đây:

- \`device_id\` là **partition key**: các bản ghi cùng thiết bị thuộc một phân vùng logic.
- \`event_time\` là clustering column thứ nhất: bản ghi mới hơn được xếp trước.
- \`reading_id\` là clustering column thứ hai: phân biệt các bản ghi cùng thời điểm và tạo thứ tự xác định cho trường hợp trùng thời gian.
- \`value\` là cột dữ liệu bình thường, không quyết định vị trí của hàng trong partition.

Một partition có thể hình dung:

~~~text
partition: device_id = sensor-17
┌────────────────────────┬──────────────────┬───────┐
│ event_time (DESC)      │ reading_id (ASC) │ value │
├────────────────────────┼──────────────────┼───────┤
│ 2026-11-14 12:05:23    │ 85c1...          │ 28.4  │
│ 2026-11-14 12:02:00    │ 0a12...          │ 28.1  │
│ 2026-11-14 12:02:00    │ 9d20...          │ 28.2  │
│ 2026-11-14 12:01:10    │ 51a2...          │ 27.9  │
└────────────────────────┴──────────────────┴───────┘
~~~

Với \`ORDER BY event_time DESC, reading_id ASC\`, bản ghi \`12:05:23\` đứng trước \`12:02:00\`; trong các bản ghi cùng \`12:02:00\`, \`reading_id\` phân biệt thứ tự.

### 2.1. Khóa chính không đồng nghĩa một cột ID duy nhất

Trong mô hình quan hệ, người học thường quen dùng \`id\` để định danh một hàng. Trong wide-column, một hàng có thể được nhận diện bởi **tổ hợp partition key và các clustering columns**. Hai hàng được phép có cùng \`device_id\` và \`event_time\` nếu \`reading_id\` khác nhau.

Tổ hợp khóa:

~~~text
(device_id, event_time, reading_id)
~~~

phải định danh chính xác một hàng. Nếu thiết kế chỉ dùng:

~~~sql
PRIMARY KEY ((device_id), event_time)
~~~

thì hai lần ghi cùng thiết bị và cùng timestamp sẽ cùng nhắm vào một hàng. Vì Cassandra dùng ngữ nghĩa ghi kiểu *upsert* với khóa đó, một phép ghi có thể cập nhật/ghi đè giá trị theo quy tắc giải quyết phiên bản ghi thay vì tạo một bản ghi độc lập. Thêm \`reading_id\` khi cần lưu nhiều sự kiện tại cùng thời điểm giúp tránh lỗi mất dữ liệu do khóa không đủ phân biệt.

### 2.2. Khóa phân vùng kết hợp

Ví dụ:

~~~sql
PRIMARY KEY ((tenant_id, device_id, hour_bucket), observed_at, reading_id)
~~~

Ba cột \`tenant_id\`, \`device_id\`, \`hour_bucket\` **cùng tạo thành một partition key**. Đây không phải ba cấp sắp xếp độc lập.

Để truy cập một partition hiệu quả, truy vấn thông thường phải cung cấp **đủ các thành phần partition key** theo phép bằng; ví dụ không thể chỉ cung cấp \`tenant_id\` rồi kỳ vọng cơ sở dữ liệu sẽ tự tìm và sắp xếp dữ liệu mọi thiết bị theo thời gian.

### 2.3. Phân biệt thứ tự trong partition với thứ tự toàn bộ bảng

Các phân vùng được phân phối qua các node theo cơ chế phân vùng của hệ thống. **Clustering order chỉ quy định thứ tự hàng bên trong một partition**, không bảo đảm rằng tất cả hàng ở các phân vùng được trả về theo một trật tự thời gian toàn cục.

~~~text
Partition (factory-a, sensor-17, 2026-11-14T12)
  12:59 -> 12:58 -> 12:57 -> ...

Partition (factory-a, sensor-17, 2026-11-14T11)
  11:59 -> 11:58 -> 11:57 -> ...

Partition (factory-a, sensor-18, 2026-11-14T12)
  12:59 -> 12:56 -> 12:55 -> ...
~~~

Nếu API cần “20 bản ghi mới nhất trên **mọi thiết bị**”, chỉ có bảng theo thiết bị chưa đủ. Ứng dụng phải ghép dữ liệu từ nhiều partition hoặc xây bảng dành riêng cho mẫu truy vấn đó.

## 3. Từ Q1/Q2 đến bảng chính: readings_by_device_hour

Vì truy vấn thường lấy bản ghi của **một thiết bị trong một khoảng thời gian**, ta chọn:

- Partition key: \`(tenant_id, device_id, hour_bucket)\`.
- Clustering column thứ nhất: \`observed_at DESC\`.
- Clustering column thứ hai: \`reading_id ASC\` để phân biệt bản ghi cùng thời điểm.
- Các trường chỉ dùng để hiển thị: \`temperature_c\`, \`battery_percent\`, \`severity\`.

\`hour_bucket\` là chuỗi UTC dạng \`YYYY-MM-DDTHH\`, ví dụ \`2026-11-14T12\`. Dùng chuỗi như vậy giúp ví dụ dễ nhìn; sản phẩm thật có thể chọn kiểu dữ liệu/kỹ thuật bucket khác miễn là **cách tạo bucket nhất quán giữa ghi và đọc**.

### 3.1. CQL tạo bảng

~~~sql
CREATE TABLE readings_by_device_hour (
    tenant_id text,
    device_id text,
    hour_bucket text,
    observed_at timestamp,
    reading_id uuid,
    temperature_c double,
    battery_percent int,
    severity text,
    received_at timestamp,
    PRIMARY KEY (
        (tenant_id, device_id, hour_bucket),
        observed_at,
        reading_id
    )
) WITH CLUSTERING ORDER BY (
    observed_at DESC,
    reading_id ASC
);
~~~

Trong bảng này, một partition chứa dữ liệu của **đúng một tenant, một thiết bị và một giờ UTC**. Các hàng bên trong được truy cập theo \`observed_at\` giảm dần.

### 3.2. Dữ liệu minh họa

~~~sql
INSERT INTO readings_by_device_hour (
    tenant_id, device_id, hour_bucket,
    observed_at, reading_id,
    temperature_c, battery_percent, severity, received_at
) VALUES (
    'factory-a', 'sensor-17', '2026-11-14T12',
    '2026-11-14T12:01:10Z',
    51a2b1a0-7b56-4afc-bddb-7519c13af175,
    27.9, 84, 'NORMAL', '2026-11-14T12:01:11Z'
);

INSERT INTO readings_by_device_hour (
    tenant_id, device_id, hour_bucket,
    observed_at, reading_id,
    temperature_c, battery_percent, severity, received_at
) VALUES (
    'factory-a', 'sensor-17', '2026-11-14T12',
    '2026-11-14T12:05:23Z',
    85c1bdc5-9367-4648-a283-408cfc74e5db,
    28.4, 83, 'NORMAL', '2026-11-14T12:05:24Z'
);

INSERT INTO readings_by_device_hour (
    tenant_id, device_id, hour_bucket,
    observed_at, reading_id,
    temperature_c, battery_percent, severity, received_at
) VALUES (
    'factory-a', 'sensor-17', '2026-11-14T12',
    '2026-11-14T12:02:00Z',
    0a128a16-0c9d-422a-b28d-a0a58e173cc1,
    28.1, 84, 'NORMAL', '2026-11-14T12:02:03Z'
);

INSERT INTO readings_by_device_hour (
    tenant_id, device_id, hour_bucket,
    observed_at, reading_id,
    temperature_c, battery_percent, severity, received_at
) VALUES (
    'factory-a', 'sensor-17', '2026-11-14T12',
    '2026-11-14T12:02:00Z',
    9d205f51-ac25-4317-b8c6-904e0371f94b,
    28.2, 84, 'NORMAL', '2026-11-14T12:02:06Z'
);
~~~

Dù các lệnh \`INSERT\` không chạy theo thứ tự thời gian, kết quả khi đọc một partition vẫn tuân theo clustering order. **Thứ tự ghi vào CSDL không phải yếu tố quyết định thứ tự đọc trong partition**.

### 3.3. Truy vấn Q1: 20 bản ghi mới nhất

~~~sql
SELECT observed_at, reading_id, temperature_c,
       battery_percent, severity
FROM readings_by_device_hour
WHERE tenant_id = 'factory-a'
  AND device_id = 'sensor-17'
  AND hour_bucket = '2026-11-14T12'
LIMIT 20;
~~~

Vì khóa phân vùng được cung cấp đầy đủ và clustering order mặc định đã là thời gian giảm dần, truy vấn không cần tự sắp xếp sau khi nhận toàn bộ phân vùng.

Có thể thể hiện rõ ý định:

~~~sql
SELECT observed_at, reading_id, temperature_c
FROM readings_by_device_hour
WHERE tenant_id = 'factory-a'
  AND device_id = 'sensor-17'
  AND hour_bucket = '2026-11-14T12'
ORDER BY observed_at DESC, reading_id ASC
LIMIT 20;
~~~

Trong mô hình Cassandra, \`ORDER BY\` bị giới hạn bởi clustering order và điều kiện partition key; nó **không phải một phép sắp xếp tự do trên trường bất kỳ** như người học có thể mong đợi từ một truy vấn SQL tổng quát.

Với các dữ liệu mẫu, thứ tự kỳ vọng là:

| Vị trí | observed_at | reading_id (rút gọn) | temperature_c |
| --- | --- | --- | ---: |
| 1 | 12:05:23 | 85c1… | 28.4 |
| 2 | 12:02:00 | 0a12… | 28.1 |
| 3 | 12:02:00 | 9d20… | 28.2 |
| 4 | 12:01:10 | 51a2… | 27.9 |

Hai bản ghi \`12:02:00\` được phân biệt bằng \`reading_id\` tăng dần. Đây là lý do thứ tự phụ nên được thiết kế ngay khi có thể trùng timestamp.

### 3.4. Truy vấn Q2: khoảng thời gian trong cùng một partition

Ví dụ tìm dữ liệu từ 12:02 đến trước 12:04:

~~~sql
SELECT observed_at, reading_id, temperature_c
FROM readings_by_device_hour
WHERE tenant_id = 'factory-a'
  AND device_id = 'sensor-17'
  AND hour_bucket = '2026-11-14T12'
  AND observed_at >= '2026-11-14T12:02:00Z'
  AND observed_at <  '2026-11-14T12:04:00Z';
~~~

Điều kiện \`observed_at\` là một **clustering slice** trong partition đã xác định. Nó phù hợp vì \`observed_at\` đứng đầu danh sách clustering columns.

Nếu cần lọc tiếp \`temperature_c > 30\`, cột \`temperature_c\` không nằm trong partition key hay clustering key. Cơ sở dữ liệu không tự có đường truy cập hiệu quả cho điều kiện ấy. Nếu đây là truy vấn quan trọng, cần xét mô hình hoặc chỉ mục riêng phù hợp với sản phẩm và workload.

## 4. Vì sao không đặt tất cả dữ liệu của thiết bị vào một partition?

Một lựa chọn ban đầu dễ nghĩ:

~~~sql
PRIMARY KEY ((tenant_id, device_id), observed_at, reading_id)
~~~

Tất cả lịch sử của thiết bị \`sensor-17\` sẽ thuộc cùng một partition logic, dù được ghi trong nhiều năm. Điều này cho phép lấy bản ghi mới nhất trực tiếp, nhưng partition có thể tăng rất lớn.

Giả sử thiết bị tạo **5 bản ghi/giây**, mỗi hàng có kích thước dữ liệu logic trung bình khoảng **800 byte**:

~~~text
Bản ghi/ngày = 5 × 86.400 = 432.000
Dữ liệu logic/ngày = 432.000 × 800 byte
                  = 345.600.000 byte
                  ≈ 329,6 MiB

Bản ghi/giờ = 5 × 3.600 = 18.000
Dữ liệu logic/giờ = 18.000 × 800 byte
                  = 14.400.000 byte
                  ≈ 13,7 MiB
~~~

Các số này chưa tính metadata, tombstone, cấu trúc lưu trữ, nén và bản sao. Chia **theo giờ** giảm đáng kể lượng dữ liệu logic nằm trong một partition đối với giả định này.

Không có một giới hạn kích thước partition tối ưu áp dụng cho tất cả cluster Cassandra. Kích thước phù hợp còn phụ thuộc dung lượng hàng, tần suất cập nhật, tombstone, mô hình truy vấn, phiên bản engine, compaction, dung lượng bộ nhớ và SLA. Vì vậy **bucket theo giờ chỉ là giả thuyết thiết kế được rút ra từ workload ví dụ**, cần kiểm chứng với dữ liệu và cluster thực tế.

### 4.1. Chọn kích thước bucket dựa trên tốc độ tăng

| Bucket | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Không chia bucket | Truy vấn lịch sử của một thiết bị có thể nhắm một partition | Partition tăng không giới hạn, rủi ro rất lớn khi dữ liệu dài hạn |
| Theo ngày | Ít partition, dễ lấy dữ liệu trong ngày | Với thiết bị ghi dày, partition có thể lớn |
| Theo giờ | Hạn chế số hàng trong partition ở workload nhiều sự kiện | Truy vấn qua nhiều giờ phải đọc nhiều partition |
| Theo 5 phút | Mỗi partition nhỏ hơn nữa | Nhiều partition và truy vấn qua khoảng dài cần fan-out nhiều hơn |
| Theo số shard cùng thời gian | Có thể chia tải cho thiết bị cực nóng | Phải truy vấn, trộn và sắp xếp kết quả từ nhiều shard |

Một công thức sơ bộ:

~~~text
Hàng/bucket ≈ tốc độ ghi của một thiết bị (hàng/giây)
              × số giây trong bucket

Dữ liệu logic/bucket ≈ hàng/bucket
                      × kích thước hàng trung bình
~~~

Đừng quên đo **p95/p99 kích thước hàng** và **thiết bị ghi nhiều nhất**, không chỉ tốc độ trung bình của toàn bộ thiết bị.

### 4.2. Quy tắc tạo bucket phải thống nhất

Ví dụ dữ liệu ở \`2026-11-14T12:59:59Z\` thuộc \`hour_bucket = 2026-11-14T12\`; dữ liệu ở \`13:00:00Z\` thuộc \`2026-11-14T13\`.

Một hàm pseudo:

~~~python
from datetime import datetime, timezone

def utc_hour_bucket(observed_at: datetime) -> str:
    if observed_at.tzinfo is None:
        raise ValueError("Timestamp phải có timezone")
    return observed_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
~~~

Nếu service A tạo bucket theo UTC còn service B tạo theo giờ địa phương, cùng một sự kiện có thể được ghi vào partition khác với partition mà bên đọc tìm kiếm. Đây là lỗi mô hình khóa, không phải lỗi tính năng \`SELECT\`.

### 4.3. Dữ liệu đến muộn

Một sự kiện được ghi nhận lúc 11:58 nhưng được server nhận lúc 12:10 vẫn thuộc **bucket 11** nếu thiết kế sắp xếp theo \`observed_at\`. Vì vậy ghi không nhất thiết chỉ xảy ra ở partition giờ hiện tại.

Nếu đồng hồ thiết bị không đáng tin, phải định nghĩa rõ sử dụng \`observed_at\`, \`received_at\` hay cả hai, kèm cách xử lý timestamp sai lệch. Thứ tự đọc theo một cột chỉ đúng với **ý nghĩa thời gian được chọn**.

## 5. Khi truy vấn đi qua ranh giới nhiều partition

Q1 yêu cầu “20 bản ghi mới nhất”, nhưng trong giờ hiện tại có thể mới có 3 bản ghi. Truy vấn đúng một bucket chỉ trả được 3, dù giờ trước còn hàng nghìn bản ghi.

Một thuật toán ứng dụng:

~~~text
INPUT: tenant_id, device_id, now, limit=20
results = []
bucket = UTC_HOUR(now)

WHILE len(results) < 20 AND bucket còn nằm trong khoảng lưu trữ:
    need = 20 - len(results)
    batch = QUERY readings_by_device_hour
            WHERE partition=(tenant_id, device_id, bucket)
            ORDER BY observed_at DESC
            LIMIT need
    APPEND batch vào results
    bucket = previous_utc_hour(bucket)

RETURN results[:20]
~~~

Vì các bucket là những **khoảng thời gian rời nhau và liên tiếp**, nếu dữ liệu được gán bucket đúng theo \`observed_at\`, ta có thể đọc giờ hiện tại trước rồi giờ trước để xây thứ tự mới nhất trước.

Nếu dữ liệu được phân tán thêm trên nhiều **shard trong cùng giờ**, không thể chỉ nối kết quả của shard 0 rồi shard 1: phải **merge theo khóa sắp xếp** để bảo đảm global top-20.

### 5.1. Truy vấn khoảng thời gian băng qua hai giờ

Ví dụ cần xem từ \`11:45\` đến \`12:15\`. Ứng dụng phải đọc hai partition:

~~~text
(factory-a, sensor-17, 2026-11-14T11)
  observed_at >= 11:45 và < 12:00

(factory-a, sensor-17, 2026-11-14T12)
  observed_at >= 12:00 và < 12:15
~~~

Ứng dụng kết hợp kết quả theo \`observed_at\` và \`reading_id\`. Một câu truy vấn \`WHERE hour_bucket >= ...\` không phải lời giải tổng quát vì \`hour_bucket\` là **thành phần của partition key**; Cassandra không cung cấp sắp xếp toàn cục tự do trên dải partition key theo cách một hệ quan hệ có thể thực hiện với một index khác.

### 5.2. Chọn chiến lược phân trang

Nếu đọc nhiều trang trong **một partition**, Cassandra driver thường hỗ trợ **paging state** để tiếp tục kết quả query:

~~~python
# Mã minh họa theo mô hình Cassandra Python driver.
statement = session.prepare("""
    SELECT observed_at, reading_id, temperature_c
    FROM readings_by_device_hour
    WHERE tenant_id = ?
      AND device_id = ?
      AND hour_bucket = ?
""")

bound = statement.bind(("factory-a", "sensor-17", "2026-11-14T12"))
bound.fetch_size = 100
result = session.execute(bound)

for row in result:
    consume(row)
~~~

\`fetch_size\` chỉ định kích thước trang trao đổi giữa driver và server; nó **không phải giới hạn tổng số hàng**. Đoạn loop có thể làm driver tải nhiều trang. Nếu API chỉ cần 20 hàng, hãy dùng \`LIMIT 20\`; nếu API cho phép “trang tiếp theo”, cần thiết kế việc lưu và dùng paging state phù hợp với driver và quyền truy cập.

**Paging state không phải snapshot bất biến.** Khi có ghi hoặc xóa đồng thời, một lượt phân trang nhiều request có thể quan sát tập dữ liệu thay đổi. Với API yêu cầu kết quả ổn định, có thể cố định một **mốc thời gian trên** (*high-water mark*) và thiết kế cursor chứa khóa sắp xếp cuối cùng, bucket hiện tại cùng thông tin truy vấn. Cursor là dữ liệu điều khiển truy cập cần kiểm tra tính toàn vẹn và phạm vi tenant.

### 5.3. Phân trang đa bucket cần nhớ nhiều trạng thái

Khi một trang kết thúc giữa \`hour_bucket=12\`, trang sau phải tiếp tục từ vị trí còn lại **trong bucket đó** trước khi chuyển sang bucket 11. Tối thiểu cursor phải biết:

- Tenant/thiết bị và các điều kiện lọc đã xác thực.
- Bucket đang đọc.
- Vị trí cuối cùng hoặc paging state tương ứng.
- Mốc thời gian trên nếu cần duy trì sự ổn định giữa các trang.

Không nên sử dụng một offset lớn \`OFFSET 100000\` theo thói quen SQL: kiểu truy vấn wide-column thông thường được tối ưu cho **đọc tuần tự theo khóa và cursor**, không phải bỏ qua một lượng hàng tùy ý trên toàn bộ tập dữ liệu.

## 6. Thiết kế bảng riêng cho Q3: truy cập theo readingId

Giả sử một trang chi tiết nhận URL:

~~~text
/readings/85c1bdc5-9367-4648-a283-408cfc74e5db
~~~

Ứng dụng chỉ biết \`readingId\` và tenant được xác thực; không biết \`deviceId\`, \`hourBucket\`, \`observedAt\`. Bảng \`readings_by_device_hour\` **không có đường tra cứu theo readingId đơn độc** vì \`reading_id\` là clustering column đứng sau \`observed_at\`.

Một hướng thiết kế là tạo bảng phục vụ trực tiếp Q3:

~~~sql
CREATE TABLE reading_by_id (
    tenant_id text,
    reading_id uuid,
    device_id text,
    observed_at timestamp,
    hour_bucket text,
    temperature_c double,
    battery_percent int,
    severity text,
    PRIMARY KEY ((tenant_id, reading_id))
);
~~~

Truy vấn:

~~~sql
SELECT *
FROM reading_by_id
WHERE tenant_id = 'factory-a'
  AND reading_id = 85c1bdc5-9367-4648-a283-408cfc74e5db;
~~~

**Tại sao \`(tenant_id, reading_id)\` được đặt trong cặp ngoặc kép của partition key?** Vì muốn định vị trực tiếp theo *cả* tenant và ID; nếu viết \`PRIMARY KEY (tenant_id, reading_id)\` thì \`tenant_id\` là partition key, còn \`reading_id\` trở thành clustering column, khiến mọi bản ghi của một tenant có thể dồn vào một partition rất lớn.

Bảng mới **lặp một phần dữ liệu** từ bảng đầu tiên để hỗ trợ Q3. Đây là kiểu thiết kế *query-first* thường gặp ở wide-column: nhiều bảng có các cách sắp khóa khác nhau cho các truy vấn khác nhau.

### 6.1. Ghi vào hai bảng

~~~text
Khi nhận reading R:
  1. Tính hour_bucket từ observedAt theo UTC.
  2. Ghi R vào readings_by_device_hour.
  3. Ghi R vào reading_by_id.
~~~

Với hai thao tác ghi độc lập, có khả năng bước 1 thành công còn bước 2 thất bại. Ứng dụng cần chiến lược **retry an toàn, sự kiện/outbox, đồng bộ hoặc tái xây dữ liệu phụ**, tùy mức nhất quán nghiệp vụ yêu cầu. Không được kết luận hai bảng nhất thiết luôn đồng bộ chỉ vì chúng cùng nằm trong một cluster.

Sử dụng cùng \`reading_id\` và các khóa xác định ổn định khi retry giúp tránh tạo thêm hàng logic trong mỗi bảng. Tuy nhiên, ghi CQL thông thường có ngữ nghĩa upsert theo primary key; nếu nội dung khác hoặc hai writer có thời điểm ghi khác nhau, còn phải xử lý quy tắc giải quyết xung đột. “Cùng khóa” chỉ là một phần của thiết kế idempotency.

## 7. Q4: cảnh báo CRITICAL trên nhiều thiết bị

Truy vấn:

~~~text
Cho tenant factory-a, lấy 50 cảnh báo CRITICAL
mới nhất từ tất cả thiết bị trong 1 giờ gần đây.
~~~

Bảng theo thiết bị **không thuận lợi** để trả lời. Nếu tenant có 100.000 thiết bị, quét từng thiết bị để tìm cảnh báo là quá tốn kém.

Vì Q4 là đường truy cập quan trọng, có thể lưu thêm **bảng chỉ chứa các cảnh báo CRITICAL** và định vị theo tenant + bucket giờ:

~~~sql
CREATE TABLE critical_readings_by_tenant_hour (
    tenant_id text,
    hour_bucket text,
    shard_no smallint,
    observed_at timestamp,
    reading_id uuid,
    device_id text,
    temperature_c double,
    PRIMARY KEY (
        (tenant_id, hour_bucket, shard_no),
        observed_at,
        reading_id
    )
) WITH CLUSTERING ORDER BY (
    observed_at DESC,
    reading_id ASC
);
~~~

\`shard_no\` là cách phân tán tải nếu một tenant có quá nhiều cảnh báo trong một giờ. Ví dụ ứng dụng tính:

~~~text
shard_no = stable_hash(reading_id) mod 8
~~~

Truy vấn phải đọc các shard phù hợp rồi **merge kết quả theo thời gian**:

~~~sql
SELECT observed_at, reading_id, device_id, temperature_c
FROM critical_readings_by_tenant_hour
WHERE tenant_id = 'factory-a'
  AND hour_bucket = '2026-11-14T12'
  AND shard_no = 0
LIMIT 50;
~~~

Lặp theo các shard cần thiết, rồi dùng thuật toán merge top-50 ở ứng dụng để lấy đúng 50 cảnh báo toàn tenant. Nếu cần cả giờ trước, tiếp tục ở các bucket trước theo logic thời gian.

**Đánh đổi rõ ràng:**

- Không chia shard: ít lượt đọc hơn, nhưng một tenant đông thiết bị có thể có partition nóng hoặc quá lớn.
- Chia shard: phân tán ghi hơn, nhưng phải fan-out đọc và merge, phát sinh chi phí và độ phức tạp.
- Nếu Q4 ít dùng, cân nhắc phân tích không đồng bộ hoặc hệ truy vấn khác; không cần tạo bảng phụ cho mọi câu hỏi có thể tưởng tượng.

Trường \`severity\` có giá trị CRITICAL được **lọc tại bước ghi vào bảng**; bảng này là một *materialized read model* do ứng dụng hoặc pipeline quản lý. Nếu severity của một reading thay đổi, quy trình phải biết cách thêm/xóa hoặc điều chỉnh bản ghi ở read model để không hiển thị cảnh báo đã giải quyết như cảnh báo mới.

## 8. Q5: thống kê theo giờ khác với đọc từng sự kiện

Một dashboard cần nhiệt độ trung bình của \`sensor-17\` theo từng giờ trong 30 ngày. Nếu tính bằng cách quét toàn bộ bản ghi thô của từng giờ, số hàng cần đọc rất lớn.

Có thể thiết kế bảng tổng hợp:

~~~sql
CREATE TABLE temperature_stats_by_device_day (
    tenant_id text,
    device_id text,
    day_bucket date,
    hour_start timestamp,
    sample_count bigint,
    temperature_sum double,
    min_temperature double,
    max_temperature double,
    PRIMARY KEY (
        (tenant_id, device_id, day_bucket),
        hour_start
    )
) WITH CLUSTERING ORDER BY (hour_start DESC);
~~~

Truy vấn dữ liệu tổng hợp theo ngày:

~~~sql
SELECT hour_start, sample_count, temperature_sum,
       min_temperature, max_temperature
FROM temperature_stats_by_device_day
WHERE tenant_id = 'factory-a'
  AND device_id = 'sensor-17'
  AND day_bucket = '2026-11-14';
~~~

Ứng dụng tính:

~~~text
average_temperature = temperature_sum / sample_count
                      (nếu sample_count > 0)
~~~

Nếu có các sự kiện đến trễ hoặc thay đổi, phải xác định cách cập nhật thống kê **không đếm trùng khi retry**. Tách \`sum\` và \`count\` giúp cộng gộp có giải thích được, nhưng các phép tăng bộ đếm độc lập trên hai trường chưa mặc nhiên có tính exactly-once. Với workload phức tạp, cần pipeline xử lý sự kiện, state theo \`readingId\` và chiến lược sửa kết quả khi có dữ liệu muộn.

Ở đây ta đã có ba dạng bảng cho ba nhu cầu khác nhau:

~~~mermaid
flowchart TD
    W["Một bản ghi đo mới"] --> A["readings_by_device_hour<br/>Q1/Q2: lịch sử theo thiết bị"]
    W --> B["reading_by_id<br/>Q3: tra cứu theo readingId"]
    W --> C{"Có CRITICAL?"}
    C -->|Có| D["critical_readings_by_tenant_hour<br/>Q4: cảnh báo mới nhất"]
    W --> E["Luồng tổng hợp<br/>Q5: thống kê theo giờ"]
    E --> F["temperature_stats_by_device_day"]
~~~

Không có quy tắc “một bảng bằng một thực thể” bất biến. Một thực thể có thể xuất hiện trong nhiều bảng để đường truy cập thường dùng không phải trả giá quét hoặc lọc ngoài ý muốn.

## 9. Quy tắc quan trọng khi dùng clustering columns

### 9.1. Thứ tự cột trong khóa rất quan trọng

So sánh hai schema:

~~~sql
-- Thiết kế A: ưu tiên lọc thời gian, sau đó phân biệt reading
PRIMARY KEY ((tenant_id, device_id, hour_bucket), observed_at, reading_id)

-- Thiết kế B: ưu tiên reading_id rồi mới tới thời gian
PRIMARY KEY ((tenant_id, device_id, hour_bucket), reading_id, observed_at)
~~~

Thiết kế A phục vụ truy vấn theo khoảng \`observed_at\`. Thiết kế B không có cùng đường truy cập hiệu quả để lấy “20 bản ghi mới nhất”, vì clustering column đầu tiên là \`reading_id\` và các hàng được xếp theo ID trước khi xét thời gian.

**Không thể đổi vị trí hai clustering columns mà vẫn kỳ vọng khả năng truy vấn giữ nguyên.**

### 9.2. Điều kiện trên clustering columns có tính tiền tố

Giả sử:

~~~sql
PRIMARY KEY ((tenant_id, device_id), reading_type, observed_at, reading_id)
~~~

Các hàng trong partition sẽ nhóm theo \`reading_type\` trước, rồi mới theo \`observed_at\`. Cách này thuận lợi cho:

~~~sql
SELECT *
FROM some_readings_table
WHERE tenant_id = 'factory-a'
  AND device_id = 'sensor-17'
  AND reading_type = 'TEMPERATURE'
  AND observed_at >= '2026-11-14T12:00:00Z';
~~~

Nhưng nếu Q1 cần **mọi loại reading mới nhất** của thiết bị, \`reading_type\` đứng trước sẽ chia dữ liệu thành nhiều nhóm và không cung cấp một thứ tự thời gian tổng thể như mong muốn.

Điểm thiết kế nằm ở chỗ: **mỗi cột clustering đứng trước sẽ ảnh hưởng đến những cột phía sau có thể được đọc theo dải như thế nào**. Người thiết kế phải sắp thứ tự cột theo truy vấn thực tế.

### 9.3. Thứ tự tăng và giảm không thay cho lọc

\`CLUSTERING ORDER BY (observed_at DESC)\` khiến dữ liệu mới hơn đứng trước trong partition, rất thích hợp cho Q1. Nó không tự trả lời “tất cả bản ghi mà nhiệt độ lớn hơn 35 độ”. \`ORDER BY\` là cơ chế sắp xếp trên **clustering columns**, không làm mọi cột thành cột tìm kiếm.

### 9.4. Điều kiện bao phủ nhiều partition không cho kết quả sort toàn cục

Ngay cả khi mỗi partition đã có \`observed_at DESC\`, kết hợp dữ liệu từ nhiều thiết bị hoặc bucket vẫn cần quy tắc xử lý tại ứng dụng/công cụ truy vấn. Đừng nhầm “từng danh sách con đã được sắp xếp” với “toàn bộ danh sách đã được sắp xếp”.

## 10. Vì sao ALLOW FILTERING không phải cách sửa mô hình khóa

Khi gặp truy vấn không khớp partition/clustering key, người học đôi khi thử thêm \`ALLOW FILTERING\` để CQL cho phép chạy. Điều này không tạo ra chỉ mục có thể truy cập trực tiếp; CSDL có thể phải đọc hoặc xem xét nhiều dữ liệu để lọc lấy vài hàng.

Ví dụ:

~~~sql
-- Một kiểu truy vấn có thể bị từ chối, hoặc yêu cầu lọc tốn kém:
SELECT *
FROM readings_by_device_hour
WHERE severity = 'CRITICAL'
ALLOW FILTERING;
~~~

Nếu bảng có hàng tỷ bản ghi và chỉ 0,01% là CRITICAL, số hàng phải xem xét có thể vượt xa số hàng thực sự trả về. Dù truy vấn có \`LIMIT 50\`, không thể mặc định server chỉ cần xem đúng 50 hàng là tìm đủ 50 kết quả phù hợp.

Để xử lý:

1. Xác định đây có phải truy vấn **thường xuyên và quan trọng** hay không.
2. Nếu có, xây đường truy cập như \`critical_readings_by_tenant_hour\` hoặc index phù hợp với công nghệ và workload.
3. Nếu chỉ dùng cho phân tích định kỳ, cân nhắc pipeline/export sang hệ phân tích phù hợp.
4. Dùng \`ALLOW FILTERING\` chỉ khi biết rõ chi phí và phạm vi dữ liệu mà truy vấn phải xét, không coi đó là cách thiết kế bảng mặc định.

Một số phiên bản Cassandra có các loại secondary index, Storage-Attached Index hoặc khả năng khác để hỗ trợ điều kiện truy vấn. Sự tồn tại của tính năng đó không thay thế việc đánh giá selectivity, phân bố dữ liệu, kích thước kết quả và đường đọc quan trọng.

## 11. Truy vấn nhanh cần phân vùng vừa phải và phân bố tải cân bằng

Thiết kế partition key phù hợp không chỉ về **hình dạng truy vấn** mà còn về **quy mô dữ liệu và độ lệch lưu lượng**.

### 11.1. Partition quá lớn

Với một thiết bị ghi liên tục nhiều năm, partition \`(tenant_id, device_id)\` không có bucket có thể tăng rất lớn. Hậu quả có thể gồm:

- Tốn tài nguyên khi đọc/compact/repair dữ liệu.
- Đọc dải rộng dễ kéo theo nhiều SSTable và nhiều tombstone.
- Một số truy vấn mất nhiều thời gian hoặc tạo nhiều phân trang.
- Tác vụ bảo trì và phân phối tải khó khăn hơn.

Việc dùng bucket thời gian giúp giới hạn số hàng logic/partition, nhưng còn phải kiểm tra **dữ liệu thực tế và mục tiêu latency**.

### 11.2. Partition nóng

Giả sử \`sensor-17\` gửi 50.000 sự kiện/giây, còn phần lớn thiết bị chỉ gửi một sự kiện/phút. Dù partition key có nhiều thiết bị khác nhau, dòng ghi của \`sensor-17\` có thể tạo **điểm nóng** trong bucket hiện tại.

Các phương án cân nhắc:

- Chia bucket thời gian nhỏ hơn nếu lượng dữ liệu/partition tăng quá nhanh.
- Phân shard thêm một thành phần vào partition key để phân tán ghi khi cần.
- Dùng buffering/batching phù hợp để hấp thụ đỉnh.
- Thiết kế lại truy vấn để chấp nhận fan-out và merge nếu sử dụng shard.
- Đo mức tải theo partition/tenant/device và giờ cao điểm, không chỉ tổng QPS của cluster.

Tăng số node không tự giải quyết mọi hot partition: nếu một partition logic đang nhận quá nhiều thao tác, chiến lược key vẫn có thể là nút thắt.

### 11.3. Partition quá nhỏ

Chia mỗi giây thành một bucket riêng cho một thiết bị ghi vài lần/ngày có thể tạo rất nhiều partition nhỏ. Điều này tăng metadata, số partition cần quét ở truy vấn dài, và độ phức tạp quản lý cursor.

Mục tiêu là **kích thước và lưu lượng partition phù hợp**, không phải cứ nhỏ nhất có thể.

## 12. TTL, xóa dữ liệu và tombstone ảnh hưởng tới thứ tự đọc

Thiết bị IoT có thể chỉ cần giữ bản ghi thô 30 ngày. Cassandra có thể hỗ trợ TTL:

~~~sql
INSERT INTO readings_by_device_hour (
    tenant_id, device_id, hour_bucket,
    observed_at, reading_id, temperature_c, battery_percent, severity
) VALUES (
    'factory-a', 'sensor-17', '2026-11-14T12',
    '2026-11-14T12:06:00Z',
    12345678-1234-4234-8234-1234567890ab,
    28.6, 82, 'NORMAL'
) USING TTL 2592000;
~~~

\`2592000\` giây tương đương **30 ngày × 24 giờ × 3600 giây**. TTL thể hiện thời gian tồn tại tính từ khi ghi theo cách mà hệ quản trị thực thi; nếu yêu cầu **30 ngày kể từ thời điểm thiết bị quan sát**, cần kiểm tra cách áp dụng chính sách cho dữ liệu đến muộn thay vì chỉ dùng cùng TTL từ lúc nhận.

Dữ liệu đã hết hạn hoặc được xóa có thể để lại **tombstone** cho tới khi compaction và điều kiện an toàn cho phép thu hồi. Khi truy vấn một đoạn thời gian chứa nhiều hàng hết hạn, hệ thống có thể phải đọc qua nhiều dấu xóa để tìm số hàng còn hiệu lực.

Những lưu ý thiết kế:

- Nếu toàn bộ dữ liệu trong một bucket có vòng đời gần nhau, có thể nghiên cứu chiến lược compaction phù hợp với dữ liệu theo thời gian.
- Tránh cập nhật/xóa ngẫu nhiên khối lượng lớn trong các partition mà ứng dụng thường đọc liên tục, nếu có thể thiết kế retention theo bucket.
- Cần quan sát tombstones, thời gian đọc và compaction metrics khi retention hoạt động lâu dài.
- Nếu cùng một reading xuất hiện trong nhiều bảng phụ, chính sách TTL/xóa và cơ chế làm sạch phải bao phủ mọi biểu diễn.

\`LIMIT 20\` chỉ giới hạn hàng trả về theo truy vấn; nó **không đảm bảo storage engine không phải xét thêm dữ liệu đã hết hạn hoặc không thỏa điều kiện**.

## 13. Consistency, ghi lặp và dữ liệu thứ tự thời gian

### 13.1. Cassandra chấp nhận upsert theo primary key

Một lệnh \`INSERT\` vào khóa đã tồn tại thường mang ngữ nghĩa *upsert*, không giống ràng buộc unique điển hình của SQL được kiểm tra mặc định.

Vì thế:

- Nếu hai bản ghi thực sự khác nhau vô tình có cùng \`partition + clustering key\`, một bản ghi có thể ghi đè/cập nhật giá trị của bản kia.
- Nếu muốn **idempotent ingest**, \`reading_id\` phải ổn định qua retry, và ứng dụng phải giữ cùng giá trị partition/clustering key.
- Nếu dữ liệu có thể sửa, cần chính sách version, timestamp và xung đột rõ ràng; không thể chỉ dựa trên thứ tự đến của HTTP requests để suy ra phiên bản cuối trong mọi tình huống phân tán.

### 13.2. Read consistency và replica

Việc một hàng có clustering key xác định không đảm bảo mọi replica đã chứa ngay giá trị mới. Độ mới của dữ liệu đọc còn phụ thuộc consistency level, replication, topology và tình trạng cluster.

Với dashboard giám sát, có thể chấp nhận một khoảng trễ hiển thị. Với thao tác điều khiển thiết bị hoặc quyết định an toàn, yêu cầu nhất quán có thể khác. Chọn consistency là quyết định cùng lúc về **độ mới, độ trễ và mức chịu lỗi**, phải gắn với đặc tả sản phẩm đang dùng.

### 13.3. Không trộn thứ tự sự kiện với thứ tự commit

Nếu một bản ghi quan sát lúc 12:01 đến sau bản ghi 12:05, clustering order theo \`observed_at\` vẫn đặt 12:05 trước. Điều này đúng với yêu cầu “dữ liệu theo thời điểm thiết bị quan sát”.

Nhưng nếu API cần “những bản ghi mới **vừa được nhận vào hệ thống**”, hãy thiết kế theo \`received_at\` hoặc tạo bảng riêng theo thời gian ingest. **Một lựa chọn clustering order phản ánh một định nghĩa cụ thể về 'mới nhất'**.

## 14. Thực hành: tự kiểm chứng thứ tự trong một partition

Phần này dùng \`cqlsh\` và một cluster Cassandra thử nghiệm đã chạy. Các lệnh dưới đây minh họa kiểu thao tác mà người học có thể thực hiện; cần dùng keyspace và môi trường của mình.

### 14.1. Tạo keyspace thử nghiệm

Ví dụ dành cho **một node lab**, không dùng cấu hình replication này cho production:

~~~sql
CREATE KEYSPACE IF NOT EXISTS nosql_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE nosql_lab;
~~~

Sau đó chạy \`CREATE TABLE readings_by_device_hour ...\` ở mục 3.1 và các lệnh \`INSERT\` tại mục 3.2.

### 14.2. Đọc partition theo thứ tự đã khai báo

~~~sql
SELECT observed_at, reading_id, temperature_c
FROM readings_by_device_hour
WHERE tenant_id = 'factory-a'
  AND device_id = 'sensor-17'
  AND hour_bucket = '2026-11-14T12';
~~~

Kết quả cần quan sát:

~~~text
12:05:23  85c1...  28.4
12:02:00  0a12...  28.1
12:02:00  9d20...  28.2
12:01:10  51a2...  27.9
~~~

Hãy ghi lại quan hệ giữa thứ tự này và \`CLUSTERING ORDER BY (observed_at DESC, reading_id ASC)\`. Các lệnh \`INSERT\` đã cố tình chạy không theo thứ tự thời gian, nhưng đọc vẫn trả theo clustering order.

### 14.3. Đổi truy vấn, không đổi bảng

Thử:

~~~sql
SELECT observed_at, reading_id, temperature_c
FROM readings_by_device_hour
WHERE tenant_id = 'factory-a'
  AND device_id = 'sensor-17'
  AND hour_bucket = '2026-11-14T12'
  AND observed_at >= '2026-11-14T12:02:00Z'
  AND observed_at < '2026-11-14T12:06:00Z'
LIMIT 2;
~~~

Với dữ liệu mẫu, hai hàng trả về có thời gian 12:05:23 và 12:02:00 (reading ID 0a12…). Hãy giải thích vì sao \`LIMIT 2\` chọn đúng hai hàng ấy theo thứ tự khóa, thay vì chọn hai lệnh \`INSERT\` đầu tiên.

### 14.4. Thử truy vấn trái với partition key

~~~sql
-- Dùng để hiểu giới hạn truy vấn:
SELECT *
FROM readings_by_device_hour
WHERE device_id = 'sensor-17';
~~~

Truy vấn này **thiếu \`tenant_id\` và \`hour_bucket\`**; với Cassandra CQL thông thường, nó không khớp đường đọc theo partition key và có thể bị từ chối. Không nên thêm \`ALLOW FILTERING\` ngay chỉ để làm câu truy vấn chạy: hãy quay lại câu hỏi nghiệp vụ và thiết kế một bảng khác nếu truy vấn ấy thật sự cần thiết.

### 14.5. Một bài thử có thêm dữ liệu cùng timestamp

Thêm bản ghi thứ năm lúc 12:02:00 với \`reading_id\` khác, rồi đọc lại. Quan sát rằng \`reading_id\` quyết định vị trí **trong nhóm cùng thời gian**. Thay đổi \`temperature_c\` không thay đổi thứ tự vì nó không phải clustering column.

## 15. Đánh giá schema qua các chỉ số thực tế

Thiết kế theo truy vấn cần được kiểm tra bằng workload thật; lý thuyết khóa đúng không tự bảo đảm đáp ứng SLA khi dữ liệu và lưu lượng tăng.

| Chỉ số | Câu hỏi kiểm chứng |
| --- | --- |
| **p50/p95/p99 latency** của Q1–Q5 | Những đường đọc quan trọng có đạt mục tiêu không? |
| **Rows read / rows returned** | Có đang xét quá nhiều hàng để trả về ít kết quả không? |
| **Partition size distribution** | p95/p99 partition có quá lớn, hay chỉ một số thiết bị bất thường? |
| **Hot partition / hot key** | Thiết bị hoặc tenant nào tập trung ghi/đọc quá nhiều? |
| **Số partition/query** | Q2 hoặc Q4 phải đọc bao nhiêu bucket/shard mỗi lần gọi? |
| **Tombstones scanned** | TTL/xóa có làm query chậm dù \`LIMIT\` nhỏ không? |
| **Read/write throughput** | Số bảng read model làm tăng lượng ghi và dung lượng bao nhiêu? |
| **Consistency lag của bảng phụ** | Q1, Q3 và Q4 có thể cho kết quả khác nhau trong bao lâu? |
| **Compaction/repair/GC metrics** | Kích thước partition và churn có gây áp lực vận hành không? |

### 15.1. Ba kịch bản nên chạy thử

1. **Thiết bị bình thường:** vài bản ghi/giây, đa số request là Q1 với \`LIMIT 20\`.
2. **Thiết bị nóng:** một nhóm rất nhỏ thiết bị gửi nhiều nghìn bản ghi/giây; kiểm tra hot partition và nhu cầu shard.
3. **Dữ liệu lưu giữ lâu:** 30–90 ngày có TTL, trễ ghi, truy vấn xuyên nhiều bucket; kiểm tra tombstone, compaction và pagination.

Khi benchmark, cần phát sinh khóa theo **phân bố truy cập thực tế**. Nếu cứ ghi ngẫu nhiên đều khắp hàng triệu thiết bị, phép thử có thể bỏ qua đúng điểm nóng mà production gặp phải.

## 16. Những sai lầm thường gặp

| Thiết kế hoặc nhận định | Vấn đề | Hướng khắc phục |
| --- | --- | --- |
| “Một bảng lưu tất cả readings là đủ cho mọi truy vấn.” | Truy vấn khác key phải quét, lọc hoặc fan-out | Liệt kê query quan trọng và thêm read model phù hợp |
| \`PRIMARY KEY ((tenant_id), device_id, observed_at)\` cho toàn tenant | Một partition tenant có thể khổng lồ và nóng | Đưa device/time bucket vào partition key theo workload |
| \`PRIMARY KEY ((device_id), reading_id, observed_at)\` để lấy dữ liệu mới nhất | Hàng xếp theo reading ID, không ưu tiên thời gian | Đặt \`observed_at\` trước khi Q1 đọc theo thời gian |
| Chỉ dùng timestamp làm định danh hàng | Hai sự kiện cùng timestamp có thể cùng một primary key | Thêm reading ID hoặc thành phần phân biệt phù hợp |
| Dùng \`ORDER BY\` tùy ý trên một cột non-key | Không khớp cơ chế sắp xếp theo clustering | Thiết kế bảng/khóa theo thứ tự truy vấn |
| Dùng \`ALLOW FILTERING\` cho mọi bộ lọc | Có nguy cơ quét lượng lớn dữ liệu | Xây bảng theo truy vấn hoặc dùng index/analytics phù hợp |
| Chỉ đọc bucket giờ hiện tại cho “20 mới nhất” | Mất kết quả khi giờ hiện tại có ít hàng | Truy vấn lùi bucket theo thời gian và ghép kết quả |
| Dùng một \`LIMIT 20\` trên mỗi shard rồi nối danh sách | Kết quả cuối có thể không đúng global top-20 | Merge theo timestamp và tie-breaker |
| Xem nhiều bảng denormalized như một transaction mặc định | Có thể xảy ra trạng thái không đồng bộ | Thiết kế retry, đồng bộ, consistency và kiểm tra dữ liệu |
| Chọn bucket rất nhỏ mà không kiểm tra đường đọc | Tăng fan-out, metadata và chi phí phân trang | Cân bằng kích thước partition với số partition/truy vấn |

## 17. Bài tập thiết kế

### Bài 1 — Thay đổi mẫu truy vấn

Ban đầu hệ thống cần Q1: “20 bản ghi mới nhất theo thiết bị”. Sau đó sản phẩm thêm yêu cầu:

> “Trong 24 giờ qua, liệt kê 100 bản ghi nhiệt độ trên 40°C của tất cả thiết bị thuộc tenant factory-a, mới nhất trước.”

Hãy:

1. Giải thích tại sao \`readings_by_device_hour\` chưa có đường truy cập trực tiếp tốt cho yêu cầu mới.
2. Đề xuất một bảng read model theo tenant, thời gian và phân loại cảnh báo.
3. Xác định partition key, clustering columns, cách chia bucket và cách xử lý tenant cực lớn.
4. Xác định đường ghi làm mới bảng phụ khi event mới hoặc event được sửa.

### Bài 2 — Điều chỉnh bucket theo tải

Thiết bị A ghi 1 bản ghi/phút, thiết bị B ghi 2.000 bản ghi/giây, mỗi hàng logic 500 byte.

Hãy tính số bản ghi và byte logic trong một **bucket 1 giờ** của mỗi thiết bị. Từ đó giải thích vì sao dùng một độ rộng bucket cho mọi thiết bị có thể không hiệu quả. Nêu khi nào cần chuyển sang bucket nhỏ hơn hoặc thêm shard và hệ quả đối với Q1/Q2.

### Bài 3 — Chọn thứ tự clustering

Ứng dụng có yêu cầu:

- Xem dữ liệu của một thiết bị theo \`reading_type\`, mới nhất trước.
- Xem dữ liệu của một thiết bị thuộc **mọi loại**, mới nhất trước.

So sánh hai khóa:

~~~sql
PRIMARY KEY ((tenant_id, device_id, hour_bucket),
             reading_type, observed_at, reading_id)

PRIMARY KEY ((tenant_id, device_id, hour_bucket),
             observed_at, reading_id)
~~~

Khóa nào thuận lợi cho yêu cầu nào? Nếu cả hai yêu cầu đều quan trọng và thường xuyên, có nên tạo hai bảng hoặc một cơ chế chỉ mục khác? Giải thích chi phí ghi và dung lượng bổ sung.

### Bài 4 — Thứ tự khi dữ liệu đến trễ

Một thiết bị gửi:

~~~text
receivedAt=12:08, observedAt=12:05, readingId=R1
receivedAt=12:06, observedAt=12:06, readingId=R2
receivedAt=12:09, observedAt=12:04, readingId=R3
~~~

Nếu clustering order là \`observed_at DESC\`, hãy cho biết kết quả Q1 là R2, R1, R3 theo thứ tự nào. Nếu sản phẩm đổi yêu cầu thành “sự kiện mới được server nhận”, cần thay đổi hoặc bổ sung đường truy cập ra sao?

## Kết luận

Thiết kế wide-column theo truy vấn bắt đầu bằng việc xác định **đúng partition để đọc** và **đúng thứ tự clustering bên trong partition**:

- **Partition key** trả lời “nhóm dữ liệu nào cần được định vị?” và quyết định phần lớn chiến lược phân bố dữ liệu, tải.
- **Clustering columns** trả lời “trong nhóm đó, hàng nào đứng trước, và khoảng nào có thể được đọc hiệu quả?”.
- **Clustering order** giúp \`LIMIT\`, truy vấn mới nhất và range query hoạt động theo cấu trúc có sẵn, nhưng chỉ trong phạm vi partition.
- **Bucketing** giới hạn kích thước partition theo thời gian, đổi lại phải xử lý truy vấn qua nhiều bucket.
- **Bảng theo truy vấn** cho phép phục vụ Q1–Q5 bằng các khóa phù hợp, đồng thời yêu cầu kế hoạch đồng bộ dữ liệu lặp, kiểm soát dung lượng và tính nhất quán.

Một schema tốt không đơn giản là “lưu đúng dữ liệu”; nó còn phải **trả đúng dữ liệu theo thứ tự ứng dụng cần, với chi phí đọc/ghi ổn định khi khối lượng dữ liệu và tải truy cập tăng**.
