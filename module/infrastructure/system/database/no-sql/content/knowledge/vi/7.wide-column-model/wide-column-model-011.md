# Ví dụ Cassandra hoặc HBase và những khác biệt cần đối chiếu

**Apache Cassandra** và **Apache HBase** đều thường được xếp vào nhóm cơ sở dữ liệu NoSQL **cột rộng (wide-column)**. Cả hai có thể lưu lượng dữ liệu lớn, phân tán dữ liệu trên nhiều máy và phục vụ những đường truy cập dựa trên khóa. Tuy nhiên, chúng khác đáng kể về **mô hình khóa, cách tổ chức dữ liệu trên đĩa, cơ chế phân vùng, cách đọc/ghi, tính nhất quán, giao diện truy vấn và trách nhiệm vận hành**.

Vì vậy, không nên chọn một trong hai chỉ vì mô tả chung “NoSQL dạng cột, mở rộng ngang”. Bài học sử dụng một bài toán dữ liệu cảm biến để xây dựng hai phương án, sau đó đối chiếu những đánh đổi cần xác minh khi thiết kế thực tế.

> **Phạm vi:** Các câu lệnh Cassandra CQL và HBase shell/API trong bài là ví dụ hướng dẫn. Phiên bản, cấu hình cluster và driver có thể làm thay đổi những tính năng hoặc giới hạn cụ thể. Các con số tải và dung lượng chỉ là tình huống giả định, không phải benchmark sản phẩm.

## 1. Cùng thuộc nhóm cột rộng nhưng không có cùng “schema”

Một bảng quan hệ thường được hình dung như những hàng có bộ cột được khai báo trước. Trong hệ cột rộng, dữ liệu được tổ chức quanh **khóa truy cập**, còn cách gom và sắp xếp giá trị có thể linh hoạt hoặc phân tán hơn.

Cách hình dung khái niệm:

~~~text
Khóa: device-42
  thời điểm 10:01
    temperature = 24.1
    humidity    = 65
  thời điểm 10:02
    temperature = 24.3
    humidity    = 64

Khóa: device-57
  thời điểm 10:01
    temperature = 26.0
~~~

Điều cần phân biệt là **Cassandra không lưu mọi thứ theo cùng mô hình vật lý với HBase**:

- **Cassandra** cung cấp bảng có schema theo **CQL (Cassandra Query Language)**. Mỗi hàng CQL có các cột được khai báo; **partition key** quyết định nhóm dữ liệu cùng phân vùng logic và **clustering columns** quyết định thứ tự các hàng bên trong partition. Dữ liệu vẫn có thể phân bố thưa (sparse) và mở rộng bảng theo nhu cầu, nhưng không phải “mỗi hàng muốn có field gì cũng được”.
- **HBase** mô hình hóa một bảng như một tập **row key sắp thứ tự**, trong đó mỗi row chứa các **column family**. Trong mỗi family, những **column qualifier** có thể xuất hiện khác nhau giữa các row; giá trị được lưu thành những **cell có phiên bản theo timestamp**. Family cần được định nghĩa trước; qualifier không nhất thiết phải được khai báo như cột CQL.

Tên “wide-column” vì vậy giúp nhận diện họ công nghệ, **không phải hợp đồng API giống nhau**. Muốn so sánh chính xác, phải đi từ kiểu truy vấn và khóa của từng engine.

### 1.1. Hình dung hai cấu trúc

~~~text
CASSANDRA (mô hình logic)

Partition key = (device_id, day)
┌─────────────────────────────────────────────────┐
│ device-42, 2026-11-14                           │
│ clustering: event_time DESC, event_id DESC      │
│ 10:02:00, e2  → temperature=24.3; humidity=64    │
│ 10:01:00, e1  → temperature=24.1; humidity=65    │
└─────────────────────────────────────────────────┘

HBASE (mô hình logic)

Row key = device-42#20261114#<reversed-time>#e2
  family m
    qualifier temp   → cell(value=24.3, version=...)
    qualifier humid  → cell(value=64,   version=...)

Row key = device-42#20261114#<reversed-time>#e1
  family m
    qualifier temp   → cell(value=24.1, version=...)
    qualifier humid  → cell(value=65,   version=...)
~~~

Ký hiệu **reversed-time** là một giá trị thời gian được đảo theo công thức ở phần HBase. Cell timestamp của HBase là metadata phiên bản cell; nó không mặc nhiên bằng thời gian cảm biến đo hay thời điểm sự kiện được hệ thống tiếp nhận.

## 2. Bài toán chung: lưu sự kiện đo từ thiết bị

Giả sử một dịch vụ nhận dữ liệu:

~~~json
{
  "deviceId": "device-42",
  "eventId": "evt-a93",
  "eventTime": "2026-11-14T10:02:00Z",
  "temperature": 24.3,
  "humidity": 64,
  "quality": "OK"
}
~~~

Ứng dụng có các đường truy cập:

1. Ghi mỗi sự kiện một lần, có thể nhận bản tin lặp do retry.
2. Đọc **100 sự kiện mới nhất của một thiết bị**.
3. Đọc dữ liệu của một thiết bị trong **một khoảng thời gian xác định**.
4. Đôi lúc đọc thống kê trên nhiều thiết bị, theo ngày hoặc vị trí.
5. Có chính sách giữ dữ liệu nóng trong 30 ngày; dữ liệu dài hạn có thể được chuyển sang nơi lưu trữ khác theo thiết kế.

Giả định 50.000 thiết bị, trung bình 1.000 sự kiện mỗi ngày cho mỗi thiết bị:

~~~text
50.000 × 1.000 = 50.000.000 sự kiện/ngày

Nếu payload trung bình 1 KiB:
50.000.000 × 1.024 byte ≈ 47,7 GiB dữ liệu thô/ngày
~~~

Con số **47,7 GiB/ngày chỉ là payload thô**. Dung lượng thật phụ thuộc replication, khóa và metadata, index, nén, tombstone, compaction, WAL, dữ liệu trùng, backup và các thành phần vận hành. Quan trọng hơn, **trung bình 1.000 sự kiện/ngày không cho biết đỉnh tải**: một thiết bị có thể gửi hàng nghìn sự kiện trong một phút, và một số thiết bị có thể chiếm phần lớn lưu lượng.

Hai hệ thống đều có thể giải quyết một phần bài toán, nhưng cách xây khóa và những rủi ro phải đo sẽ khác nhau.

## 3. Phương án Cassandra: thiết kế partition key và clustering key

Trong Cassandra, **khóa chính CQL (PRIMARY KEY)** có thể gồm:

- **Partition key:** một hoặc nhiều cột, xác định partition logic và được dùng để tính token/định tuyến qua cơ chế partitioner.
- **Clustering columns:** sắp xếp các hàng **trong cùng một partition** và hỗ trợ truy vấn theo thứ tự/range đã thiết kế.

Với dữ liệu theo thiết bị và ngày, có thể chọn:

~~~sql
CREATE KEYSPACE telemetry
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE telemetry.events_by_device_day (
  device_id text,
  day_bucket date,
  event_time timestamp,
  event_id uuid,
  temperature double,
  humidity int,
  quality text,
  PRIMARY KEY ((device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
~~~

**Lưu ý triển khai:** Tên datacenter **dc1**, hệ số nhân bản **3** và cách khai báo bảng chỉ minh họa. Cluster phải có datacenter thực với tên tương ứng và đủ node theo topology. Chọn replication factor, consistency level và số datacenter là quyết định dựa trên yêu cầu availability/độ trễ/chi phí.

### 3.1. Tại sao partition key chứa ngày?

Nếu chỉ dùng **device_id** làm partition key, mọi sự kiện trong nhiều năm của một thiết bị có thể tích tụ vào một partition logic rất lớn. Partition quá lớn làm tăng chi phí đọc, streaming, compaction và sửa chữa.

Thêm **day_bucket** chia dữ liệu mỗi thiết bị theo ngày:

~~~text
(device-42, 2026-11-13) → partition A
(device-42, 2026-11-14) → partition B
(device-42, 2026-11-15) → partition C
~~~

Các partition này được hash theo khóa ghép và có thể nằm trên những replica khác nhau. **Không phải cứ một ngày thì luôn đúng kích thước**: nếu một thiết bị nóng ghi hàng triệu sự kiện mỗi ngày, cần bucket nhỏ hơn hoặc một cách phân phối khác.

### 3.2. Tại sao dùng event_time và event_id làm clustering key?

**event_time DESC** giúp các hàng trong một partition được tổ chức theo thời gian giảm dần. **event_id** làm thành phần phân biệt khi có nhiều sự kiện cùng thời điểm và giúp xác định một hàng CQL duy nhất theo toàn bộ primary key.

Nếu chỉ dùng **event_time** làm clustering key, hai sự kiện của cùng thiết bị trong cùng ngày có cùng timestamp sẽ có cùng khóa chính và một ghi có thể ghi đè dữ liệu logic của ghi trước. **Timestamp không mặc nhiên là ID duy nhất.**

Ví dụ ghi:

~~~sql
INSERT INTO telemetry.events_by_device_day (
  device_id,
  day_bucket,
  event_time,
  event_id,
  temperature,
  humidity,
  quality
) VALUES (
  'device-42',
  '2026-11-14',
  '2026-11-14T10:02:00Z',
  550e8400-e29b-41d4-a716-446655440000,
  24.3,
  64,
  'OK'
);
~~~

Ví dụ truy vấn **100 sự kiện gần nhất trong một ngày**:

~~~sql
SELECT event_time, event_id, temperature, humidity
FROM telemetry.events_by_device_day
WHERE device_id = 'device-42'
  AND day_bucket = '2026-11-14'
LIMIT 100;
~~~

Ví dụ đọc một khoảng thời gian **bên trong cùng partition ngày**:

~~~sql
SELECT event_time, event_id, temperature
FROM telemetry.events_by_device_day
WHERE device_id = 'device-42'
  AND day_bucket = '2026-11-14'
  AND event_time >= '2026-11-14T09:00:00Z'
  AND event_time <  '2026-11-14T10:00:00Z';
~~~

Nếu truy vấn kéo dài qua nhiều ngày, ứng dụng cần đọc **nhiều day_bucket** rồi hợp nhất. Kết quả không tự được sắp toàn cục nếu chỉ nhìn thứ tự nội bộ từng partition.

### 3.3. Một bảng cho một đường truy cập quan trọng

Thiết kế bảng trên tối ưu:

- Tìm sự kiện **theo thiết bị và ngày**.
- Lấy dữ liệu theo thứ tự thời gian **trong partition**.

Nó **không mặc nhiên hỗ trợ hiệu quả**:

- Tìm “tất cả thiết bị có temperature > 40 trong ngày”.
- Tìm toàn bộ sự kiện của một vị trí mà không biết device_id.
- Tìm 100 sự kiện mới nhất **trên toàn bộ thiết bị**.

Với Cassandra, thường phải thiết kế thêm **bảng truy cập theo đường đọc**, pipeline tổng hợp hoặc hệ thống analytics/search phù hợp. CQL nhìn giống SQL, nhưng không có nghĩa có thể tùy ý JOIN, GROUP BY và lọc mọi cột như một hệ quan hệ có bộ tối ưu truy vấn tổng quát. Tính năng index và truy vấn phụ thuộc phiên bản/khả năng cụ thể; không nên xem việc bật **ALLOW FILTERING** là giải pháp mặc định để quét dữ liệu lớn.

## 4. Cassandra thực thi ghi và đọc như thế nào?

Ở mức khái quát:

~~~mermaid
flowchart LR
    A["Ứng dụng / Driver"] --> C["Coordinator"]
    C --> R1["Replica 1"]
    C --> R2["Replica 2"]
    C --> R3["Replica 3"]
    R1 --> M1["Commit log + Memtable"]
    R2 --> M2["Commit log + Memtable"]
    R3 --> M3["Commit log + Memtable"]
    M1 --> S1["SSTables"]
    M2 --> S2["SSTables"]
    M3 --> S3["SSTables"]
~~~

Cassandra theo kiến trúc phân tán ngang hàng (*peer-to-peer*). Driver thường nhận biết topology/token để gửi yêu cầu thích hợp; một node có thể đóng vai trò **coordinator** cho request. Dữ liệu được nhân bản theo strategy và replication factor.

Trên mỗi replica, ghi đi qua **commit log** phục vụ phục hồi và **memtable** trong bộ nhớ; dữ liệu sau đó được flush thành **SSTable**. Các SSTable được hợp nhất/thu hồi dữ liệu cũ qua **compaction**. Vì thế:

- Ghi có thể phù hợp workload lớn có cấu trúc truy cập dự kiến, nhưng độ trễ vẫn phụ thuộc replication, consistency level, disk/network và compaction.
- Một giá trị cũ hoặc đã xóa có thể còn trong các SSTable cho đến khi compaction và điều kiện dọn cho phép.
- Đọc có thể phải xét nhiều SSTable, tombstone và kết quả từ replica; thiết kế partition và clustering key rất quan trọng.
- Kích thước partition, loại compaction, tombstone và repair ảnh hưởng trực tiếp tới vận hành.

### 4.1. Tính nhất quán của Cassandra phải đọc theo request

Cassandra cho phép chọn các mức nhất quán khi đọc/ghi như **ONE, QUORUM, LOCAL_QUORUM, ALL** (tùy loại yêu cầu và topology). Ví dụ với **RF=3 trong một datacenter**, ghi ở quorum thường cần xác nhận từ **2 replica**; đọc quorum cũng liên hệ tới **2 replica**.

Trong điều kiện các replica và thao tác cùng phạm vi phù hợp, đọc/ghi quorum có giao nhau về replica để giảm nguy cơ nhìn bản cũ. Tuy nhiên, **không được suy rộng thành mọi thao tác đều linearizable**: concurrent writes, timestamp/conflict resolution, topology nhiều datacenter và đường xử lý riêng vẫn phải được xem xét. Khi cần ghi có điều kiện, Cassandra có **lightweight transactions (LWT)** với cơ chế đồng thuận, đổi lại độ trễ và chi phí phối hợp cao hơn ghi thông thường.

Các câu hỏi thiết kế:

- Người dùng vừa ghi một sự kiện có phải đọc lại thấy ngay không?
- Hệ thống chấp nhận mất một replica nhưng vẫn ghi thành công không?
- Có cần chống ghi đè cùng khóa/event_id khi dữ liệu đến lặp hoặc cạnh tranh?
- Mức consistency của dữ liệu bình thường và thao tác điều kiện có được cấu hình đúng ở **driver** không?

Một bảng CQL có schema đúng **không bảo đảm quy tắc chống trùng nghiệp vụ** nếu ứng dụng sinh event_id mới mỗi lần retry. Cần giữ ID ổn định giữa các lần gửi cùng một sự kiện hoặc thiết kế idempotency phù hợp.

## 5. Phương án HBase: row key, column family, qualifier và version

HBase chịu ảnh hưởng từ mô hình **Google Bigtable**: một bảng được tổ chức theo **row key có thứ tự từ điển của byte**, trong mỗi row là các column family/qualifier với giá trị cell có phiên bản.

Với một thiết bị và thời gian, có thể tạo row key:

~~~text
device-42#20261114#<reverse-time-padded>#evt-a93
└─ device ─┘└─ ngày ┘└── sắp mới trước ───┘└─ ID ┘
~~~

Lưu ý:

- **Row key là byte sequence.** Muốn thứ tự đúng, phải encode các phần theo độ dài/quy tắc thống nhất, đặc biệt giá trị số thời gian.
- Một row key mô tả **một sự kiện**, không phải toàn bộ lịch sử thiết bị trong một row vô hạn.
- Sử dụng **event_id** làm tie-breaker để tránh hai sự kiện cùng thời điểm va vào một row key.
- Row key có thể thay đổi theo phiên bản thiết kế; việc thay đổi đòi migration/dual-read nếu dữ liệu cũ vẫn đang phục vụ.

### 5.1. Thiết kế column family

Ví dụ dùng một family **m** (*measurements*) chứa các qualifier:

~~~text
row key: device-42#20261114#...#evt-a93

family m:
  m:temperature → 24.3
  m:humidity    → 64
  m:quality     → "OK"
~~~

Family là đơn vị cấu hình lưu trữ quan trọng của HBase. Các family khác nhau có thể có cấu hình version, compression, TTL và cách phục vụ riêng. **Không nên tạo một column family cho mỗi sensor hoặc mỗi thuộc tính tùy ý**. Số family thường được giữ ít và ổn định; trong khi **qualifier** mới có thể xuất hiện mà không phải thêm một cột CQL vào bảng.

Mỗi cell HBase được nhận diện về mặt logic bởi:

~~~text
(row key, column family, qualifier, timestamp) → value
~~~

Timestamp là **phiên bản cell**. Có thể lưu nhiều phiên bản nếu cấu hình column family cho phép. Điều đó khác với việc dùng **eventTime như một thành phần row key**:

- **Nhiều phiên bản cùng cell** hữu ích khi muốn giữ các trạng thái cũ của chính giá trị đó.
- **Nhiều sự kiện độc lập** thường nên có nhiều row key hoặc cấu trúc riêng, nếu cần liệt kê/query từng sự kiện.

Không nên nhồi mọi sự kiện vào một cell với nhiều version rồi cho rằng HBase tự biến chúng thành bảng thời gian có truy vấn phong phú.

### 5.2. Lệnh HBase shell minh họa

Tạo bảng với một family:

~~~ruby
create 'telemetry_events', { NAME => 'm', VERSIONS => 1 }
~~~

Ghi ba giá trị vào cùng row key:

~~~ruby
put 'telemetry_events',
    'device-42#20261114#99999999999999999#evt-a93',
    'm:temperature', '24.3'

put 'telemetry_events',
    'device-42#20261114#99999999999999999#evt-a93',
    'm:humidity', '64'

put 'telemetry_events',
    'device-42#20261114#99999999999999999#evt-a93',
    'm:quality', 'OK'
~~~

Giá trị **99999999999999999** ở đây chỉ là chuỗi minh họa độ dài của trường thời gian đảo; **không phải thời điểm tính từ 2026-11-14**. Trong triển khai thật phải sinh row key bằng encoder xác định, giữ độ dài và thứ tự đúng. HBase shell xem các giá trị chuỗi ở ví dụ như byte của chuỗi; ứng dụng thực có thể sử dụng serialization nhị phân khác.

Đọc theo row key chính xác:

~~~ruby
get 'telemetry_events',
    'device-42#20261114#99999999999999999#evt-a93'
~~~

Quét row trong một khoảng tiền tố:

~~~ruby
scan 'telemetry_events',
     { STARTROW => 'device-42#20261114#',
       STOPROW  => 'device-42#20261115#',
       LIMIT => 100 }
~~~

**STARTROW và STOPROW** giới hạn theo thứ tự byte của row key; việc dùng prefix ngày tiếp theo làm cận trên ở đây phụ thuộc vào format đã quy ước và chỉ đúng khi khoảng khóa được thiết kế như vậy. Trong HBase, scan đọc theo thứ tự row key; LIMIT nêu trên là giới hạn kết quả của thao tác scan minh họa. Muốn đọc dữ liệu nhiều ngày hoặc của nhiều thiết bị, phải thiết kế các scan thích hợp, tránh quét toàn bảng ngoài dự kiến.

### 5.3. Vì sao phải đảo thời gian?

Nếu row key được sắp tăng theo **timestamp thời gian thực**, scan theo một tiền tố thiết bị thường gặp dữ liệu cũ trước. Để đưa sự kiện mới lên đầu theo thứ tự byte, có thể dùng:

~~~text
reverseTime = MAX_TIME_VALUE - epochMillis
rowKey = deviceId + "#" + day + "#" +
         fixedWidthUnsigned(reverseTime) + "#" + eventId
~~~

Trong phạm vi có cùng tiền tố device/day, **eventTime càng mới thì reverseTime càng nhỏ**. Scan từ đầu khoảng sẽ gặp dữ liệu mới trước nếu encoding byte giữ thứ tự số và các trường có độ dài cố định.

Nhưng **reverseTime không bảo đảm sự kiện mới được commit gần nhất**. Một sự kiện đến muộn mang eventTime cũ vẫn xuất hiện theo thời gian sự kiện, không theo thời điểm server nhận. Nếu yêu cầu theo thứ tự tiếp nhận, cần chọn serverAcceptedAt hoặc một sequence có thẩm quyền.

Hơn nữa, mọi ghi mới liên tục rơi vào phần đầu/đuôi của dải cùng device/day có thể tạo vùng nóng trong cơ chế **range partition**. Thiết kế sắp xếp thuận tiện cho đọc phải được đánh giá cùng khả năng chịu ghi.

## 6. HBase phân vùng dữ liệu theo region

Trong triển khai HBase thông dụng, row key được chia thành các **region liên tiếp theo khoảng khóa**. **RegionServer** phục vụ các region, còn HDFS thường giữ file dữ liệu **HFile**; dữ liệu ghi được ghi vào **WAL (write-ahead log)** và **MemStore**, rồi flush ra file lưu trữ. Các file được compaction theo cơ chế của HBase.

~~~mermaid
flowchart LR
    C["Ứng dụng HBase Client"] --> R["RegionServer chứa region của row key"]
    R --> W["WAL"]
    R --> M["MemStore"]
    M --> F["HFiles trong storage/HDFS"]
    F --> K["Compaction"]
~~~

**Điểm khác quan trọng với Cassandra:**

- HBase **chia theo khoảng row key**; những khóa có prefix/số tăng liên tục có thể đẩy lưu lượng mới vào một region nóng, ngay cả khi tổng số RegionServer lớn.
- Khi region lớn, hệ thống có thể **split** thành các region nhỏ hơn và di chuyển region giữa máy để cân bằng. Tuy nhiên, tự động split **không luôn giải quyết moving hotspot** nếu mọi ghi mới tiếp tục đi vào một đầu dải.
- HBase có metadata và thành phần điều phối region; khách hàng truy cập đúng RegionServer theo vị trí hiện tại của region. Đây là mô hình quản lý khác với Cassandra dùng token và replica.
- Vì dữ liệu theo row key nằm trong range, HBase phù hợp các **Get/Scan theo row key hoặc tiền tố** được thiết kế cẩn thận. Scan không giới hạn vẫn có thể tốn chi phí lớn.

Có thể thêm **salt/bucket** vào row key để phân tán ghi:

~~~text
bucket#deviceId#day#reverseTime#eventId

bucket = stableHash(eventId) % 16
~~~

Với một thiết bị rất nóng, bucket dựa trên **eventId** có thể giúp phân phối nhiều sự kiện khác nhau qua nhiều tiền tố. Nếu bucket chỉ dựa vào **deviceId**, toàn bộ sự kiện cùng một thiết bị vẫn vào một bucket; cách đó không giải quyết hot device.

Đánh đổi là để tìm 100 sự kiện mới nhất của một thiết bị, ứng dụng phải truy vấn **nhiều bucket** rồi hợp nhất theo thời gian. Việc thêm bucket, thay số bucket và xác định cận scan đều cần được xử lý trong định dạng khóa và logic ứng dụng.

## 7. So sánh trực diện Cassandra và HBase

| Khía cạnh | Cassandra | HBase |
| --- | --- | --- |
| **Mô hình logic** | Bảng CQL với schema cột, partition key và clustering columns | Row key, column family, qualifier, cell timestamp/versions |
| **Khóa định tuyến** | Partition key được ánh xạ qua partitioner/token tới replica | Khoảng row key quyết định region và RegionServer |
| **Thứ tự** | Clustering order **trong một partition** | Row key sắp **theo thứ tự byte** trên toàn bảng logic qua các region |
| **Giao diện chính** | CQL và driver tương ứng | HBase client API, Get/Put/Scan, shell; SQL thường qua lớp bổ sung |
| **Đường ghi** | Coordinator/replicas, commit log, memtable, SSTable | RegionServer, WAL, MemStore, HFile |
| **Nhân bản/availability** | Replica phân tán theo replication strategy; consistency level theo request | Region có đầu mối phục vụ trong cluster; dữ liệu HDFS và cơ chế failover; replication giữa cluster có hợp đồng riêng |
| **Nhất quán cơ bản** | Có nhiều mức nhất quán đọc/ghi; LWT cho điều kiện đặc biệt | Các thao tác trên một row thường có tính nguyên tử và nhất quán mạnh trong cấu hình phục vụ row chính |
| **Tìm theo ID/khóa** | Hiệu quả khi có đầy đủ partition key | Hiệu quả với Get theo row key |
| **Quét range** | Thuận lợi **trong partition** qua clustering key; không mặc nhiên quét toàn cụm theo thứ tự clustering toàn cục | Thuận lợi với dải row key đã sắp; có thể qua nhiều region |
| **Trường linh hoạt** | Các cột CQL thuộc schema khai báo; xử lý field bổ sung tùy cấu trúc/map/UDT/version | Column qualifier trong family có thể thưa và biến động theo row |
| **Phiên bản giá trị** | Timestamp của mutation phục vụ reconciliation, không phải giao diện versioned-cell như HBase | Cell có timestamp phiên bản, số version giữ lại được cấu hình |
| **TTL/xóa** | TTL trên dữ liệu, tombstone, compaction/repair ảnh hưởng dọn vật lý | TTL/versions theo family và quy tắc cell, delete markers, compaction |
| **Nhiều đường truy vấn** | Thường tạo bảng theo đường đọc; có các tính năng index phụ tùy phiên bản | Thường thiết kế row key hoặc bảng/index phụ; có thể dùng lớp như Phoenix |
| **Vận hành** | Quản lý cluster Cassandra, compaction, repair, token/replica, coordinator | Quản lý HBase và thành phần hạ tầng (thường HDFS), region, WAL, compaction, split/balance |
| **Tình huống hay cân nhắc** | Lượng ghi và đọc phân tán lớn với truy vấn biết trước theo partition | Get và scan theo dải row key, dữ liệu rất thưa hoặc cần version cell |

Đây là bảng so sánh **kiến trúc điển hình**, không phải khẳng định rằng sản phẩm không có ngoại lệ. Các phiên bản, tùy chọn cloud managed, feature index, lớp SQL, hệ lưu trữ nền và cách triển khai có thể thay đổi chi tiết.

### 7.1. Đừng hiểu sai “Cassandra có CQL nên giống SQL”

CQL giống SQL ở cú pháp SELECT, INSERT và CREATE TABLE, nhưng quyền truy vấn bị ràng buộc mạnh bởi khóa và đường truy cập. Ví dụ:

~~~sql
SELECT *
FROM telemetry.events_by_device_day
WHERE device_id = 'device-42'
  AND day_bucket = '2026-11-14';
~~~

Truy vấn này phù hợp mô hình khóa.

~~~sql
SELECT *
FROM telemetry.events_by_device_day
WHERE temperature > 35;
~~~

Truy vấn thứ hai không thể được coi là truy vấn tối ưu trên bảng đã thiết kế chỉ vì cột temperature tồn tại. Cần cân nhắc thiết kế bảng khác, index phù hợp với phiên bản/giới hạn, pipeline tổng hợp hoặc search/analytics chuyên dụng.

### 7.2. Đừng hiểu sai “HBase sắp xếp dữ liệu nên truy vấn tùy ý rất nhanh”

HBase sắp **row key**, không tự sắp mọi qualifier hoặc hỗ trợ bộ tối ưu truy vấn trên tất cả trường. Nếu row key bắt đầu bằng **deviceId**, một truy vấn lấy sự kiện theo **temperature > 35 trên toàn hệ thống** vẫn không có đường truy cập chọn lọc tốt từ row key. Filter phía HBase có thể giảm dữ liệu trả về trong một số trường hợp nhưng không mặc nhiên biến một full scan thành tra cứu theo index.

Truy vấn mới đòi **thiết kế row key/bảng thứ cấp**, hệ thống xử lý dữ liệu khác hoặc lớp lập chỉ mục được chọn có chủ đích.

## 8. Tính nhất quán: cần xét đơn vị nguyên tử

Một câu hỏi thường gặp là “Cassandra eventually consistent còn HBase strongly consistent, đúng không?”. Phân biệt này có ích như một điểm bắt đầu, nhưng **quá đơn giản nếu dùng để quyết định nghiệp vụ**.

### 8.1. Với Cassandra

- Ứng dụng chọn consistency level trên thao tác đọc/ghi theo topology và yêu cầu.
- Phản hồi thành công ở ONE, QUORUM hay ALL có nghĩa khác nhau về số replica đáp ứng và khả năng sẵn sàng.
- Cơ chế reconciliation, read repair/repair và conflict resolution ảnh hưởng việc đồng bộ replica.
- Ghi có điều kiện cần cân nhắc **LWT**, với chi phí phối hợp lớn hơn các thao tác thường.
- **BATCH** trong CQL không nên được hiểu là một giao dịch SQL tổng quát có đầy đủ isolation trên nhiều partition. Batching chủ yếu phải được sử dụng phù hợp với phạm vi, semantics và workload.

Ví dụ nghiệp vụ “chỉ tạo sự kiện nếu eventId chưa tồn tại” cần được thiết kế khác với INSERT thông thường khi nhiều tác giả có thể ghi cùng khóa. Hãy xác định rõ chính sách cập nhật lặp: ghi lại cùng giá trị idempotent, từ chối duplicate, hay chỉ chấp nhận phiên bản mới.

### 8.2. Với HBase

- Với thiết lập phục vụ row chính thông thường, những thao tác như **Put/Get**, **CheckAndMutate**, hoặc biến đổi nhiều cell trong **cùng một row** có thể dựa vào bảo đảm nguyên tử và nhất quán ở phạm vi row theo API.
- Bảo đảm trên một row **không tự mở rộng thành transaction nguyên tử trên nhiều row/region**.
- Cross-cluster replication hoặc secondary replica reads có thể có độ trễ, nên không mặc định rằng mọi đường đọc ở mọi nơi đều thấy ngay trạng thái mới.
- Nếu cần kiểm tra điều kiện trên dữ liệu ở một row khác hoặc liên quan một dịch vụ khác, phải có một cơ chế xử lý nhất quán riêng.

Ví dụ:

~~~text
Yêu cầu: device-42 chỉ được có 1 record trạng thái ACTIVE
trong một khoảng thời gian.

Nếu điều kiện phụ thuộc 2 row key khác nhau:
  kiểm tra từng row độc lập
  + ghi từng row độc lập
không tự bảo đảm bất biến khi 2 request đồng thời.
~~~

Hãy xem **ranh giới nguyên tử là row hay nhiều row, partition hay nhiều partition, một datacenter hay nhiều datacenter**, thay vì gắn một nhãn consistency cho toàn bộ sản phẩm.

## 9. Các thao tác xóa, TTL và dữ liệu phiên bản

### 9.1. Cassandra: TTL, tombstone và compaction

Một số dữ liệu sự kiện có thể có thời hạn lưu tại bảng:

~~~sql
INSERT INTO telemetry.events_by_device_day (
  device_id, day_bucket, event_time, event_id,
  temperature, humidity, quality
) VALUES (
  'device-42',
  '2026-11-14',
  '2026-11-14T10:02:00Z',
  550e8400-e29b-41d4-a716-446655440000,
  24.3, 64, 'OK'
) USING TTL 2592000;
~~~

**2.592.000 giây = 30 ngày** là ví dụ đơn vị TTL. Trong Cassandra, TTL và thao tác xóa làm phát sinh cơ chế **tombstone**/đánh dấu dữ liệu không còn hiệu lực; dung lượng không nhất thiết được trả lại ngay khi TTL chạm hạn. Số lượng tombstone lớn có thể gây tác động tới đọc và compaction.

Một điểm vận hành quan trọng là phải hiểu **repair và thời gian giữ tombstone**. Xóa tombstone quá sớm khi còn replica lâu ngày chưa được đồng bộ có thể gây nguy cơ dữ liệu xóa “sống lại” (*zombie data*) trong một số kịch bản. Không điều chỉnh các tham số như **gc_grace_seconds** chỉ để tiết kiệm dung lượng khi chưa có chiến lược repair và điều kiện triển khai tương ứng.

Chính sách TTL nên được đối chiếu với:

- Cách dữ liệu đến trễ hoặc được cập nhật lại.
- Cửa sổ query và chính sách lưu dữ liệu dài hạn.
- Kích thước partition, chiến lược compaction (ví dụ các lựa chọn phù hợp workload thời gian), tốc độ dọn/repair.
- Chi phí lưu trữ thực tế, bao gồm bản sao và dữ liệu không còn hiển thị.

### 9.2. HBase: TTL/versions theo family và delete markers

HBase thường cấu hình **TTL và số phiên bản được giữ** ở mức **column family**. Ví dụ minh họa khi tạo family:

~~~ruby
create 'telemetry_history',
       { NAME => 'm', VERSIONS => 3, TTL => 2592000 }
~~~

Điều này khác Cassandra ở chỗ HBase có khái niệm **nhiều phiên bản cell**:

~~~text
row:  device-42#...
cell: m:temperature

version timestamp T3 → "24.3"
version timestamp T2 → "24.1"
version timestamp T1 → "24.0"
~~~

Nếu ứng dụng chỉ muốn một sự kiện bất biến, lưu 3 version của cùng cell **không mặc nhiên cần thiết**. Nếu ứng dụng muốn lịch sử cập nhật cùng một field, khả năng cell version mới đáng cân nhắc.

TTL và việc dọn vật lý trong HBase còn phụ thuộc compaction và các quy tắc version retention. **Không dùng TTL làm đồng hồ chính xác để kích hoạt một nghiệp vụ**, cũng không suy ra “giá trị đã hết hạn thì lập tức biến mất khỏi mọi file, backup và replica”.

### 9.3. Câu hỏi cần đặt trước khi bật TTL

1. TTL tính theo thời gian **ghi vào kho**, theo timestamp cell, hay theo timestamp mà ứng dụng gắn vào sự kiện?
2. Nếu sự kiện đến trễ một ngày thì sẽ sống thêm 30 ngày từ lúc ghi hay hết hạn theo ngày nghiệp vụ?
3. Bản ghi vừa cập nhật có gia hạn TTL không? Có cột nào bị quên TTL sau update?
4. Có truy vấn nào cần dữ liệu quá 30 ngày và phải đọc từ kho lưu trữ lạnh không?
5. Bao lâu sau hết hạn mới thu hồi dung lượng vật lý? Chi phí compaction/repair là bao nhiêu?

Hai công nghệ có thể cùng hỗ trợ “TTL 30 ngày” nhưng **ngữ nghĩa và chi phí dọn dữ liệu không giống nhau**.

## 10. Hot partition và hot region: cùng một triệu chứng, khác cách sửa

Giả sử một thiết bị trong đợt thử nghiệm gửi **10.000 sự kiện/giây**, trong khi các thiết bị còn lại gửi rất ít.

### 10.1. Cassandra: partition quá lớn hoặc quá nóng

Với khóa **(device_id, day_bucket)**, mọi sự kiện của thiết bị đó trong ngày đi vào cùng một **partition logic**, được phục vụ bởi tập replica của partition ấy. Dù toàn bộ cluster có 100 node, không có nghĩa 100 node cùng chia đều một partition rất nóng.

Một cách giảm tải là chia nhỏ theo giờ hoặc thêm bucket:

~~~text
partition key = (device_id, day_bucket, bucket)
bucket = stableHash(event_id) mod 16
~~~

Khi đó một thiết bị/ngày có 16 partition logic. Nhưng truy vấn “100 sự kiện mới nhất của device-42 trong ngày” phải đọc nhiều bucket và **merge theo (event_time, event_id)**; việc đổi từ 16 sang 32 bucket cũng cần xử lý dữ liệu cũ. Nếu chỉ hash **device_id** để tính bucket, mọi sự kiện cùng một thiết bị vẫn vào cùng bucket, không giải quyết hot device.

Đừng tăng số bucket theo cảm tính: thử nghiệm kích thước partition, độ phân bố token, write throughput, p99 đọc và chi phí fan-out trước khi chốt.

### 10.2. HBase: prefix/range đang nhận quá nhiều ghi

Với row key:

~~~text
device-42#20261114#reverseTime#eventId
~~~

những key của thiết bị này cùng tiền tố và ghi mới tiếp tục dồn vào phần gần nhau của không gian khóa. Một **region** có thể trở nên nóng. HBase split/balance có thể giúp chia tải giữa các khoảng, nhưng nếu toàn bộ ghi mới luôn vào một dải đang tăng/giảm, điểm nóng có thể tiếp tục dịch sang một region ở đầu/đuôi dải.

Giải pháp có thể là thêm **prefix bucket** từ eventId hoặc một giá trị phân phối đủ tốt:

~~~text
00#device-42#20261114#reverseTime#eventId
01#device-42#20261114#reverseTime#eventId
...
15#device-42#20261114#reverseTime#eventId
~~~

Lúc này đọc dữ liệu thiết bị phải scan 16 prefix. HBase không tự hợp nhất những dải này theo thời gian nghiệp vụ thành một danh sách duy nhất; logic ứng dụng hoặc một read model sẽ làm việc đó.

### 10.3. Đừng bỏ qua khóa nóng khi tất cả ghi vào cùng ID

Chia bucket theo **event_id** có thể phân tán nhiều sự kiện khác nhau. Nhưng nếu workload thực ra là cập nhật liên tục **cùng một row** hoặc cùng một counter, hashing ID không phân tán các yêu cầu ấy vì tất cả vẫn cùng một khóa. Cần nghĩ lại **đơn vị ghi**, chiến lược gom, counter phân tán hoặc thay đổi mô hình nghiệp vụ; không chỉ đổi thuật toán ID.

## 11. Đường đọc khi cần nhiều thiết bị hoặc nhiều ngày

Hai ví dụ ban đầu ưu tiên đọc theo thiết bị/ngày. Một dashboard lại muốn:

> Đếm số lần nhiệt độ vượt 40°C trong từng thành phố trong 7 ngày gần nhất.

Không có lý do để kỳ vọng bảng theo device/day tự trả lời truy vấn này hiệu quả ở cả Cassandra lẫn HBase. Các lựa chọn kiến trúc có thể gồm:

- **Read model/tổng hợp định kỳ:** giữ số đếm theo city/day đã được tính từ luồng sự kiện.
- **Bảng truy cập thứ hai:** ví dụ theo city/day và bucket nếu khối lượng phù hợp, được cập nhật bởi pipeline.
- **Data lake/OLAP:** lưu dữ liệu thô theo partition phục vụ phân tích hàng loạt, kiểm soát độ mới yêu cầu.
- **Search/analytics engine:** dùng khi truy vấn linh hoạt theo nhiều thuộc tính hoặc full-text, có quy trình đồng bộ và đối soát.

Một bản dữ liệu dẫn xuất có thể chậm vài giây hoặc vài phút. Cần ghi rõ **độ mới cho dashboard** và giữ nguồn có thẩm quyền ở đường ghi. Đừng bổ sung hàng loạt bảng phụ/secondary index trước khi xác định truy vấn nào là đường nóng và chi phí cập nhật mọi bản sao.

### 11.1. Cassandra và mô hình truy vấn trước

Với Cassandra, thiết kế bảng thường bắt đầu từ câu truy vấn cụ thể:

~~~text
Tôi cần: Lấy sự kiện device X trong ngày D, mới nhất trước.

Partition key: (device_id, day_bucket)
Clustering:    (event_time DESC, event_id DESC)
Query:         device_id = X AND day_bucket = D
~~~

Nếu thêm yêu cầu “thiết bị trong thành phố H”, thông tin city trong row không tự tạo một đường truy cập hiệu quả. Có thể thêm bảng, kết hợp source mapping hoặc tối ưu đường đọc khác.

### 11.2. HBase và thứ tự row key

Với HBase, câu hỏi tương tự:

~~~text
Tôi cần: Scan các sự kiện của device X trong ngày D.

Row key prefix: deviceId#day
Sort suffix:    reversedTime#eventId
Scan bounds:    đúng dải prefix, giới hạn số row
~~~

Nếu đổi sang “mọi thiết bị trong city H”, row key theo device không còn phù hợp để scan trực tiếp. Thiết kế một bảng/index khác cần cân nhắc độ phức tạp khi ghi đồng bộ, khôi phục và cập nhật khi thiết bị đổi city.

## 12. Chọn theo workload và năng lực vận hành

Khi hai hệ đều đáp ứng truy cập theo khóa, lựa chọn phụ thuộc các điều kiện **ngoài tên công nghệ**.

### 12.1. Những điểm khiến Cassandra đáng khảo sát

- Hệ thống cần **đọc/ghi phân tán theo những partition key đã biết**, quy mô lớn và có chiến lược nhân bản theo datacenter.
- Nhóm muốn khai báo bảng và thao tác qua **CQL** với các query pattern rõ ràng.
- Cần cân bằng **latency/availability/consistency** theo từng đường request và có thể vận hành repair, compaction, replica, tombstone.
- Chấp nhận phi chuẩn hóa thành các bảng theo đường đọc và chủ động quản lý cập nhật giữa những bản sao dữ liệu đó.

Đây là **đặc điểm để kiểm chứng**, không phải cam kết Cassandra luôn đạt throughput/latency tốt hơn một hệ khác.

### 12.2. Những điểm khiến HBase đáng khảo sát

- Workload tập trung vào **Get theo row key**, **Scan theo dải row key** và dữ liệu có cách sắp xếp phù hợp.
- Dữ liệu **thưa**, có nhiều qualifier biến động trong một số family ổn định, hoặc nghiệp vụ thực sự cần **cell versions**.
- Hạ tầng/năng lực đội ngũ phù hợp với mô hình region, RegionServer và storage phía dưới (thường HDFS) hoặc một dịch vụ managed triển khai tương đương.
- Có thể thiết kế row key để kiểm soát tốt locality, region hotspot và phạm vi scan.

Không nên suy ra “HBase mạnh hơn Cassandra vì dùng HDFS” hay “Cassandra dễ vận hành hơn trong mọi môi trường”. Cần tính cả phiên bản sản phẩm, mức hỗ trợ managed service, kỹ năng đội ngũ, công cụ backup/monitoring, quy trình nâng cấp và chi phí khi lỗi.

### 12.3. Ma trận quyết định sơ bộ

| Câu hỏi về yêu cầu | Cần đối chiếu ở Cassandra | Cần đối chiếu ở HBase |
| --- | --- | --- |
| Tra cứu theo một khóa | Partition key và coordinator/replica latency | Get theo row key và vị trí region |
| Liệt kê theo thời gian | Clustering order trong partition, số partition phải fan-out | Row-key order, scan bounds, số region phải đi qua |
| Một nguồn ghi cực nóng | Partition size/tốc độ ghi trên tập replica, bucketing | Region hotspot, prefix salting, split và balance |
| Ghi đồng thời cùng khóa | Write resolution, LWT/conditional writes | Atomic row mutation, CheckAndMutate |
| Dữ liệu đến trễ hoặc xóa hàng loạt | TTL, tombstone, compaction, repair | TTL, cell versions, delete marker, compaction |
| Đọc sau ghi cần trạng thái mới | Chọn consistency level và đường đọc; test concurrency | Xác định row chính hay replica/cluster khác, bảo đảm theo API |
| Query theo thuộc tính không nằm trong khóa | Bảng theo query, index phù hợp, analytics | Secondary structure, row-key redesign, Phoenix/analytics |
| Khôi phục sau lỗi | Replica, repair, snapshot/restore và thời gian phục hồi | WAL, region recovery, HDFS/backup, khôi phục bảng/region |
| Giảm chi phí lưu trữ | Compaction, replication, nén, tombstone | HFile, versions, nén, compaction, HDFS replication |

Nếu chưa có bằng chứng cho những hàng quyết định của bảng, kết luận phù hợp là **cần thử nghiệm**, không phải tự chọn hệ được mô tả hấp dẫn hơn.

## 13. Thiết kế thử nghiệm đối chiếu công bằng

Để so sánh hai phương án, **không thể dùng cùng một schema vật lý rồi mặc định công bằng**. Hai hệ có cơ chế định tuyến khác nhau nên cần **thiết kế schema tối ưu hợp lý cho cùng yêu cầu**, rồi đo trên cùng workload, SLO và mức chi phí.

### 13.1. Bộ dữ liệu và tải thử

Một workload minh họa:

~~~yaml
dataset:
  devices: 50000
  eventsPerDay: 50000000
  payloadBytesAverage: 1024
  hotDeviceShareOfWritesPercent: 30
  eventTimeOutOfOrderPercent: 10
queries:
  - "point lookup by event identifier and device"
  - "latest 100 events of one device"
  - "device events in 1-hour range"
  - "device events across 7 days"
workload:
  writesPerSecond: 15000
  readsPerSecond: 20000
  peakMultiplier: 3
  durationMinutes: 45
consistency:
  - "define acknowledged-write contract"
  - "define read-after-write requirement"
  - "define allowable replication/index lag"
measure:
  - "p50/p95/p99 end-to-end latency"
  - "offered and achieved throughput"
  - "error rate, throttling, retries"
  - "hottest partition/region load"
  - "disk, CPU, memory, network"
  - "storage amplification and compaction"
  - "read fan-out and scan bytes"
  - "recovery time and data correctness"
~~~

Tất cả số là **kịch bản để xây phép thử**. Nếu dữ liệu production có phân bố khác, phải điều chỉnh. Đồng thời cần ghi cấu hình driver, số node/RegionServer, loại disk, network, replication, consistency, nén, cache, giới hạn kết nối và môi trường chạy benchmark.

### 13.2. Các bài thử cần có

1. **Baseline:** tải bình thường, dữ liệu đã làm ấm theo cùng điều kiện.
2. **Ramp:** tăng dần lưu lượng đến khi vi phạm p99 hoặc tỷ lệ lỗi.
3. **Skew/hot device:** cùng tổng request/s nhưng tăng tỷ trọng request vào một thiết bị.
4. **Growth:** tăng dữ liệu từ 1× lên 5× hoặc 10×, đo tác động lên partition/region và scan.
5. **Cross-day reads:** đo chi phí fan-out/merge khi đọc nhiều ngày/bucket.
6. **Delete/TTL:** chạy workload hết hạn với thời gian đủ thấy tombstone/compaction và đo độ trễ đọc.
7. **Failure:** mô phỏng mất node/RegionServer trong môi trường thử nghiệm có kiểm soát, đo lỗi và thời gian hồi phục.
8. **Recovery:** kiểm chứng backup/restore, repair/replay và đối soát dữ liệu.
9. **Maintenance load:** thử compaction, repair/snapshot hoặc region split/balance cùng traffic.

**Đo ở cả client lẫn server.** Đừng chỉ lấy số “lệnh/giây” mà bỏ qua request timeout, lỗi ghi, thời gian scan, tail latency hoặc độ trễ dữ liệu. Với thử nghiệm đa node, đo tải từng node/partition/region để phát hiện một điểm nghẽn bị số trung bình cụm che khuất.

### 13.3. Đọc kết quả thế nào?

Giả sử sau thử nghiệm, Cassandra đạt p99 đọc 60 ms ở workload đọc theo device/day, còn HBase đạt 35 ms ở scan một dải row key. Điều đó **chưa đủ** kết luận HBase tốt hơn, nếu:

- Hai bên không dùng cùng số replica hoặc cùng yêu cầu durability.
- Dữ liệu/độ lệch thiết bị khác nhau.
- Cassandra đang chạy compaction/repair còn HBase không, hoặc ngược lại.
- HBase quét một region còn Cassandra phải đọc nhiều partition ngày.
- Một bên chỉ báo latency request thành công và bỏ timeout.
- Chi phí vận hành/storage lớn hơn nhiều so với ngưỡng dự án.

Ngược lại, HBase quét nhanh một prefix không tự chứng minh nó phù hợp cho mọi truy vấn trên mọi trường. So sánh chỉ có giá trị **trong điều kiện, phạm vi dữ liệu, truy vấn và bảo đảm đã ghi rõ**.

## 14. Các sai lầm dễ gặp khi chuyển từ hệ này sang hệ kia

### 14.1. Mang nguyên tư duy CQL sang HBase

Trong Cassandra, ta nghĩ đến **partition key + clustering order** để thỏa câu query. Trong HBase, ta phải encode **row key có thứ tự byte**, dự kiến cận Get/Scan và cách region phân bố. Không có mapping 1-1 tự nhiên từ một CQL table sang HBase table mà vẫn giữ nguyên tất cả đặc tính đọc/ghi.

### 14.2. Mang nguyên cách thiết kế row key HBase sang Cassandra

Trong HBase, một chuỗi row key tăng/giảm giúp scan theo range nhưng có thể gây hot region. Trong Cassandra, nếu lấy cả chuỗi ấy làm partition key rồi hash, dữ liệu sẽ phân tán trên token; **không còn bảo đảm scan một dải toàn cục** chỉ nhờ thứ tự chuỗi khóa. Muốn đọc thời gian theo device cần chọn partition/clustering đúng mục tiêu.

### 14.3. Hiểu “cột rộng” là không cần schema hay ràng buộc

Cassandra có schema CQL; HBase có family được định nghĩa trước và qualifier linh hoạt. Cả hai vẫn cần:

- Hợp đồng encoding kiểu giá trị, null/missing và thời gian.
- Cách tạo ID duy nhất và xử lý retry.
- Quy tắc không ghi đè sự kiện có cùng timestamp.
- Quy tắc cập nhật nhiều bản ghi/đối chiếu dữ liệu dẫn xuất.
- Cơ chế phát hiện dữ liệu sai và migration schema.

Không có một database wide-column nào tự suy ra đúng nghiệp vụ chỉ vì dữ liệu có thể mở rộng theo nhiều cột.

### 14.4. Tối ưu ghi mà quên đọc

Salting 16 bucket có thể phân tán ghi tốt, nhưng biến một scan thành 16 scan và bước merge. Ngược lại, xếp tất cả dữ liệu thiết bị liền nhau cho scan thuận tiện có thể làm một partition/region quá nóng. **Đơn vị phân vùng phải được chọn cùng truy vấn và phân bố tải**, không chỉ theo số bản ghi.

### 14.5. Coi xóa và TTL là giải phóng đĩa tức thì

Cassandra có tombstone/compaction/repair; HBase có delete marker/TTL/versions/compaction. Lập dự toán chỉ bằng “30 ngày × dữ liệu mỗi ngày” có thể thiếu chi phí đáng kể. Cần đo dữ liệu đã nhân bản, index, WAL, file lịch sử và tiến độ dọn thực tế.

### 14.6. Coi mọi hệ đều hỗ trợ cùng kiểu transaction

Một câu lệnh UPDATE hợp lệ chưa bảo đảm bất biến giữa nhiều partition/row. Hãy xác định rõ **ranh giới atomicity**, các thao tác điều kiện mà engine hỗ trợ và trường hợp lỗi/retry trước khi xây chức năng giao dịch quan trọng.

## 15. Bài tập tình huống

Một hệ thống giám sát xe giao hàng có:

- 120.000 xe, mỗi xe gửi vị trí GPS từ 1 đến 10 lần/giây tùy trạng thái.
- 1% xe hoạt động rất mạnh trong khu vực đô thị và có thể tạo phần lớn lưu lượng.
- Màn hình cần xem **50 vị trí mới nhất của một xe**.
- Bộ phận vận hành cần xem **lịch sử một xe trong 24 giờ**.
- Nhà phân tích cần thống kê **số xe đi qua từng khu vực trong một giờ**, nhưng có thể chấp nhận độ trễ dữ liệu vài phút.
- Dữ liệu có thể gửi lặp hoặc đến trễ khi xe mất mạng rồi kết nối lại.

**Nhiệm vụ A — Thiết kế Cassandra**

Đề xuất partition key và clustering key cho bảng lịch sử vị trí. Giải thích tại sao một partition theo **vehicle_id** không chia thời gian có thể quá lớn và khi nào phải thêm bucket. Viết một SELECT để lấy vị trí của một xe trong một ngày; nêu cách đọc qua nhiều ngày và cách xử lý nhiều sự kiện có cùng timestamp.

**Nhiệm vụ B — Thiết kế HBase**

Đề xuất row key phục vụ scan 50 vị trí mới nhất và range 24 giờ. Giải thích tác động khi tất cả ghi mới tập trung vào cuối một dải row key. Nếu thêm prefix salt, nêu số nhánh phải scan và cách hợp nhất kết quả.

**Nhiệm vụ C — Đối chiếu tính đúng**

Xác định khóa idempotency/eventId để retry không tạo sự kiện trùng. Phân biệt **eventTime** (GPS đo trên xe) với **serverAcceptedAt** (máy chủ nhận/commit). Nếu xe gửi dữ liệu cũ sau 30 phút offline, các màn hình nên sắp theo thời gian nào?

**Nhiệm vụ D — Thiết kế dashboard**

Vì sao truy vấn “đếm số xe theo khu vực trong một giờ” không nhất thiết phù hợp với bảng/bố cục tối ưu cho **vehicleId + time**? Hãy thiết kế một projection hoặc pipeline tổng hợp riêng và chỉ ra độ trễ đồng bộ cho phép.

**Nhiệm vụ E — Kiểm chứng bằng benchmark**

Đưa ra tối thiểu năm chỉ số cần đo: offered/achieved writes per second, p99 đọc 50 vị trí, p99 ghi, tải partition/region nóng nhất, dung lượng sau TTL, fan-out scan, lỗi khi mất node/RegionServer hoặc thời gian khôi phục. Đặt ngưỡng dựa trên yêu cầu hệ thống rồi thử với cả tải bình thường lẫn tải lệch.

### Gợi ý cách lập câu trả lời

| Yêu cầu | Gợi ý Cassandra | Gợi ý HBase |
| --- | --- | --- |
| 50 vị trí mới nhất của xe | Partition theo vehicle + bucket thời gian, clustering giảm theo eventTime + eventId | Row key vehicle + bucket thời gian + reverseTime + eventId |
| Lịch sử xe 24 giờ | Đọc các partition theo ngày/giờ và merge | Scan các dải row key tương ứng; có thể qua nhiều region |
| Xe nóng | Chia partition nhỏ hơn hoặc thêm hash bucket nếu cần | Salting prefix hoặc phân phối row key, xử lý scan fan-out |
| Sự kiện lặp | Event ID ổn định và chính sách ghi idempotent | Row key/event ID ổn định và điều kiện ghi phù hợp |
| Thống kê theo khu vực | Bảng/projection theo khu vực hoặc hệ phân tích riêng | Bảng/projection theo khu vực hoặc hệ phân tích riêng |

**Thông điệp cần ghi nhớ:** Cassandra và HBase cùng thuộc nhóm cột rộng nhưng yêu cầu tư duy khóa khác nhau. **Cassandra** tổ chức truy cập quanh partition key và clustering columns, có các mức consistency theo request. **HBase** tổ chức dữ liệu theo row key có thứ tự byte và các region theo dải, với column family, qualifier và cell versions. Chọn đúng hệ thống không phải tìm cái tên “nhanh hơn”, mà là chứng minh **đường đọc/ghi, phân phối tải, tính nhất quán, chi phí lưu trữ và khả năng vận hành** phù hợp yêu cầu thực tế.
