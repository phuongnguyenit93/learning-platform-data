# Truy vấn xuyên phân vùng, quét rộng và giới hạn lọc

Trong mô hình NoSQL **cột rộng (wide-column)**, việc đọc dữ liệu nhanh thường phụ thuộc vào khả năng xác định **phân vùng (partition)** cần truy cập trước khi thực thi truy vấn. Một truy vấn có đủ khóa phân vùng và giới hạn một khoảng hàng nhỏ có thể rất hiệu quả. Cùng yêu cầu đó, nếu thiếu khóa phân vùng hoặc đòi hỏi lọc trên hàng triệu hàng thuộc nhiều phân vùng, cơ sở dữ liệu có thể phải đọc và chuyển lượng dữ liệu lớn hơn rất nhiều so với kết quả cuối cùng.

Khó khăn xuất hiện khi nghiệp vụ chuyển từ “cho tôi 100 sự kiện gần đây của **một thiết bị**” sang “tìm mọi sự kiện **CRITICAL** của **mọi thiết bị** trong 30 ngày”. Hai câu đều giống truy vấn theo điều kiện thời gian, nhưng đường truy cập, phân vùng phải đọc, khả năng sắp xếp và chi phí hoàn toàn khác.

Bài học sử dụng **Apache Cassandra và CQL** để minh họa cụ thể. Một số nguyên tắc cũng gặp ở Apache HBase, Google Cloud Bigtable và các hệ lưu trữ phân tán dùng row key/partition key, nhưng **cú pháp truy vấn, index, cách định vị dữ liệu và khả năng lọc không giống nhau**. Không nên mặc định câu lệnh CQL chạy được trên mọi hệ cột rộng.

## 1. Bắt đầu từ ba yêu cầu truy cập khác nhau

Giả sử nền tảng IoT ghi sự kiện từ thiết bị. Mỗi sự kiện có:

~~~text
tenantId    : tổ chức sở hữu thiết bị
deviceId    : định danh thiết bị
eventTime   : thời điểm sự kiện xảy ra (UTC)
eventId     : định danh duy nhất, ổn định khi retry
eventType   : loại sự kiện
severity    : INFO | WARN | CRITICAL
payload     : thông tin chi tiết
~~~

Sản phẩm cần ba màn hình:

| Yêu cầu | Dữ liệu đầu vào ứng dụng có | Kết quả mong muốn |
|---|---|---|
| **A — Nhật ký của thiết bị** | tenantId, deviceId, khoảng thời gian | 100 sự kiện mới nhất của một thiết bị |
| **B — Cảnh báo của tổ chức** | tenantId, mức CRITICAL, 7 ngày gần nhất | 50 cảnh báo mới nhất của toàn tổ chức |
| **C — Điều tra toàn hệ thống** | eventType, khoảng 90 ngày, không biết tenant hay device | Tìm và tổng hợp sự kiện trên tất cả tổ chức |

Yêu cầu A có thể biết chính xác thiết bị và khoảng thời gian. Yêu cầu B không biết thiết bị, nên không thể dùng trực tiếp đường đọc tối ưu theo **deviceId** nếu không bổ sung cấu trúc phục vụ truy vấn. Yêu cầu C còn rộng hơn: có thể là tác vụ phân tích nền hoặc truy vấn kho dữ liệu chuyên dụng, thay vì API tương tác trả kết quả tức thì từ cùng bảng ghi sự kiện.

Sơ đồ tư duy:

~~~mermaid
flowchart TD
    A["Nghiệp vụ cần đọc gì?"] --> B{"Xác định được partition key?"}
    B -->|"Có"| C["Đọc phân vùng cụ thể"]
    C --> D{"Giới hạn clustering range?"}
    D -->|"Có"| E["Đọc dải hàng đã sắp xếp"]
    D -->|"Không"| F["Có thể quét rất nhiều hàng trong một phân vùng"]
    B -->|"Chỉ biết tập nhiều khóa"| G["Truy vấn nhiều phân vùng có giới hạn"]
    G --> H["Fan-out, gộp kết quả, kiểm soát độ đồng thời"]
    B -->|"Không"| I["Quét rộng / index chuyên biệt / read model / analytics"]
    F --> J["Đo lượng hàng đọc và chi phí"]
    H --> J
    I --> J
~~~

Chọn giải pháp cần bắt đầu từ **access pattern**: các điều kiện lọc nào luôn có, giới hạn thời gian là bao nhiêu, mỗi request có thể chạm bao nhiêu phân vùng và người dùng chờ được bao lâu.

## 2. Partition key và clustering key quyết định đường đọc

Ở Cassandra, khóa chính của một bảng có hai phần:

- **Partition key** dùng để xác định phân vùng logic của hàng và định tuyến yêu cầu tới các replica phù hợp theo cơ chế phân phối token.
- **Clustering columns** quyết định thứ tự của các hàng *bên trong cùng một phân vùng* và giúp đọc một dải theo thứ tự đó.

Ví dụ bảng sự kiện theo **thiết bị × giờ**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

-- Keyspace chỉ phục vụ ví dụ học tập trên môi trường thử nghiệm.
-- Production cần chiến lược replication phù hợp topology.

CREATE TABLE IF NOT EXISTS telemetry.events_by_device_hour (
  tenant_id text,
  device_id text,
  hour_bucket text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  severity text,
  payload_json text,
  PRIMARY KEY (
    (tenant_id, device_id, hour_bucket),
    event_time,
    event_id
  )
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
~~~

**(tenant_id, device_id, hour_bucket)** là một **partition key ghép**, vì ba cột nằm trong cặp ngoặc bên trong của **PRIMARY KEY**. **event_time** và **event_id** là clustering columns. **event_id** phá hòa nếu nhiều sự kiện có cùng thời điểm.

Trong ví dụ, **hour_bucket** có quy ước bất biến **YYYY-MM-DDTHH theo UTC**, chẳng hạn **2026-11-14T09**. Dùng chuỗi có ưu điểm dễ nhìn; hệ thống thực tế có thể dùng một kiểu dữ liệu/bucket ID khác, nhưng mọi writer và reader phải cùng tính bucket theo một quy tắc.

Minh họa các phân vùng:

~~~text
Partition ("acme", "device-08", "2026-11-14T09")
  event_time DESC       event_id       severity
  09:59:55              uuid-a         INFO
  09:42:10              uuid-b         CRITICAL
  09:12:03              uuid-c         WARN

Partition ("acme", "device-08", "2026-11-14T10")
  10:49:00              uuid-d         INFO
  10:05:00              uuid-e         CRITICAL

Partition ("acme", "device-09", "2026-11-14T09")
  09:50:00              uuid-f         CRITICAL
~~~

Thứ tự **event_time DESC** áp dụng **trong từng partition**. Cassandra không tự tạo một danh sách sự kiện mới nhất toàn tổ chức chỉ vì nhiều phân vùng đều được sắp xếp cục bộ.

### Đừng nhầm partition với node

**Một partition không đồng nghĩa một máy chủ.** Cassandra đặt các replica của một phân vùng theo token và cấu hình replication; một node chứa dữ liệu của rất nhiều phân vùng. Tuy nhiên, một partition quá lớn vẫn gây áp lực đọc, ghi, sửa và compaction, dù cluster còn nhiều node.

### Cũng đừng nhầm “cột rộng” với quét cột để phân tích

Tên **wide-column** mô tả họ mô hình dữ liệu có hàng được nhóm theo khóa và có cấu trúc cột, thường với số lượng hàng/clustering entries rất lớn trong một phân vùng. Nó **không tự có nghĩa** mọi hệ kiểu này là kho phân tích columnar như các hệ OLAP chuyên quét từng cột trên toàn bảng.

## 3. Truy vấn hiệu quả khi biết đầy đủ phân vùng

Với yêu cầu A, ứng dụng đã biết một tenant, một device và một giờ cụ thể:

~~~sql
SELECT event_time, event_id, event_type, severity, payload_json
FROM telemetry.events_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 'device-08'
  AND hour_bucket = '2026-11-14T09'
  AND event_time >= '2026-11-14T09:00:00Z'
  AND event_time <  '2026-11-14T10:00:00Z'
LIMIT 100;
~~~

Truy vấn có hai ưu điểm:

1. **Định vị được một partition** từ bộ ba khóa.
2. **Đọc được dải clustering** theo **event_time** trong phân vùng đó, dừng sau số hàng cần trả theo điều kiện phù hợp.

Do bảng sắp xếp giảm dần theo **event_time**, các hàng trong một phân vùng được đọc theo thứ tự đó khi không yêu cầu đảo chiều. Ứng dụng có thể đọc lịch sử từ mới đến cũ mà không cần thu toàn bộ một giờ rồi tự sort.

Nếu màn hình cần “100 sự kiện mới nhất trong **24 giờ**”, bảng này có thể liên quan tới **24 hourly partitions** của một thiết bị. Ứng dụng phải xác định các bucket nằm trong khoảng cần đọc và sắp xếp/gộp kết quả theo thời gian.

**LIMIT 100 của một truy vấn trong một partition không tự tương đương “100 sự kiện mới nhất của nhiều partition”.** Với nhiều bucket, cần quy tắc phân trang và kết hợp kết quả trên toàn bộ dải.

## 4. Truy vấn xuyên phân vùng là gì?

**Truy vấn xuyên phân vùng (cross-partition query)** cần dữ liệu ở nhiều partition key. Có ba mức cần phân biệt:

| Trường hợp | Ví dụ | Bản chất chi phí |
|---|---|---|
| **Một phân vùng** | Sự kiện của device-08 trong giờ 09 | Một khóa partition, một khoảng clustering |
| **Nhiều phân vùng xác định trước** | Sự kiện device-08 trong 24 giờ, biết 24 bucket | Nhiều truy vấn có kiểm soát, cần gộp kết quả |
| **Không biết phân vùng nào phù hợp** | Mọi CRITICAL event của tất cả thiết bị trong 30 ngày | Phải tìm đường truy cập khác hoặc quét/tìm rộng |

Giả sử client phải đọc 100 thiết bị trong 24 giờ:

\[
N_{\text{partitions}}
  = N_{\text{devices}} \times N_{\text{hourly buckets}}
  = 100 \times 24
  = 2400
\]

Con số **2.400** là số **partition logic tiềm năng** ứng dụng có thể phải xét, không mặc nhiên là 2.400 kết nối mạng độc lập; driver/coordinator có thể xử lý và gom yêu cầu theo cách riêng. Nhưng đây vẫn là mức **fan-out** cần có ngân sách tải, độ đồng thời, timeout và retry.

Nếu tăng phạm vi lên 10.000 thiết bị trong 30 ngày, số tổ hợp thiết bị–giờ đã ở mức:

\[
10\,000 \times 30 \times 24 = 7\,200\,000
\]

Thiết kế “lặp từng device và từng giờ để truy vấn” không còn phù hợp với một API tương tác cần trả nhanh. Đây là tín hiệu phải xét **bảng được thiết kế cho truy vấn khác**, index phù hợp hoặc hệ phân tích.

### Sắp xếp trên nhiều partition

Một partition có thể được sắp theo **event_time DESC**. Nhưng nếu lấy 10 hàng từ hai partition A và B rồi nối:

~~~text
A: 10:59, 10:50, 10:40
B: 11:00, 10:55, 10:30

Nối A + B:
  10:59, 10:50, 10:40, 11:00, 10:55, 10:30   (sai thứ tự toàn cục)

Gộp theo event_time DESC:
  11:00, 10:59, 10:55, 10:50, 10:40, 10:30
~~~

Ứng dụng có thể **merge các luồng đã sắp xếp**, nhưng phải giữ trạng thái phân trang của **từng partition** và điều kiện phá hòa khi thời gian trùng. Việc gọi **ORDER BY event_time DESC** trong một truy vấn tùy ý trên hàng nghìn partition không tự biến Cassandra thành engine sắp xếp toàn bảng.

Với **N kết quả mới nhất toàn cục**, cần có đủ ứng viên từ các partition liên quan; chỉ đọc trang đầu của một vài partition bất kỳ sẽ bỏ sót dữ liệu mới hơn ở partition khác.

## 5. Quét rộng có ít nhất hai hình thức

### 5.1. Quét nhiều partition

Đây là trường hợp hệ thống không thể định vị chính xác partition key từ điều kiện lọc. Ví dụ người dùng chỉ nhập **severity = CRITICAL** trong một bảng được phân vùng theo **tenant + device + hour**.

Đường đọc muốn trả 20 sự kiện có thể phải kiểm tra lượng dữ liệu lớn trên nhiều partition để tìm 20 bản ghi phù hợp. Một kết quả nhỏ **không nói lên công việc đọc nhỏ**.

### 5.2. Quét quá nhiều hàng trong một partition lớn

Ngay cả khi biết partition key, có thể phải đọc rất nhiều hàng vì điều kiện chỉ nằm ở cột thông thường (**non-key column**).

Ví dụ tìm mọi sự kiện CRITICAL trong một giờ của một device, nhưng khóa clustering của bảng chỉ có **event_time, event_id**. Không có cấu trúc phù hợp để nhảy thẳng đến các hàng có **severity = CRITICAL**; nếu lọc trên hàng thông thường, cơ sở dữ liệu có thể phải đọc nhiều hàng rồi loại bớt.

Một partition còn có thể chứa rất nhiều hàng do chọn bucket quá rộng hoặc một thiết bị ghi quá nhanh. Đây là **wide partition scan**: số lượng partition có thể chỉ là 1 nhưng lượng hàng trong đó rất lớn.

| Đặc điểm | Quét nhiều partition | Quét trong partition quá rộng |
|---|---|---|
| Phạm vi định vị | Nhiều khóa phân vùng hoặc toàn bảng | Một khóa phân vùng xác định |
| Nguyên nhân điển hình | Thiếu điều kiện partition key; query theo chiều khác | Không có clustering range hữu ích; partition tăng quá lớn |
| Biểu hiện | Fan-out, latency theo số partition, nhiều node tham gia | Đọc lượng lớn hàng/tombstone của một key |
| Hướng cải thiện | Access table/index cho truy vấn, giới hạn phạm vi | Bucketing, clustering range, giới hạn kích thước, sửa access pattern |

Hai loại quét có thể cùng xuất hiện: quét hàng rộng trên rất nhiều partition là tình huống đặc biệt đắt.

## 6. Những hạn chế lọc trong Cassandra CQL

CQL trông giống SQL ở các từ khóa **SELECT**, **WHERE**, **ORDER BY**, nhưng **không cung cấp tự do truy vấn tùy ý như một hệ quan hệ có optimizer và index được thiết kế cho nhiều loại join/sort**.

Với bảng **events_by_device_hour**, các điều kiện sau rất khác nhau.

### Điều kiện đủ partition key

~~~sql
SELECT event_time, severity
FROM telemetry.events_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 'device-08'
  AND hour_bucket = '2026-11-14T09'
LIMIT 20;
~~~

Đây là đường đọc thuận tự nhiên của primary key.

### Thiếu một phần composite partition key

~~~sql
-- Minh họa yêu cầu không phù hợp với primary key hiện tại:
SELECT event_time, severity
FROM telemetry.events_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 'device-08';
~~~

Ứng dụng vẫn chưa cung cấp **hour_bucket** để xác định một partition hoàn chỉnh. Trong CQL Cassandra thông thường, truy vấn như vậy không được phục vụ như một truy vấn partition key hoàn chỉnh bằng primary-key lookup; có thể bị từ chối vì đòi hỏi lọc rộng nếu không có đường truy cập khác. Muốn lấy nhiều giờ, hãy **tính các bucket cụ thể** rồi đọc chúng trong phạm vi được giới hạn.

### Lọc bằng cột không thuộc primary key

~~~sql
-- Ví dụ cố ý không phù hợp để làm truy vấn trực tuyến:
SELECT event_time, event_id, severity
FROM telemetry.events_by_device_hour
WHERE severity = 'CRITICAL'
LIMIT 20;
~~~

**severity** là regular column; bảng không có primary-key path cho điều kiện này. Cassandra thường từ chối truy vấn khi nó đòi hỏi lọc dữ liệu có nguy cơ rất lớn, trừ khi có index/khả năng hỗ trợ phù hợp hoặc người gọi chấp nhận lọc bằng cơ chế cho phép.

### ALLOW FILTERING nghĩa là gì?

~~~sql
-- Chỉ minh họa cú pháp; không nên dùng làm đường đọc production:
SELECT event_time, event_id, severity
FROM telemetry.events_by_device_hour
WHERE severity = 'CRITICAL'
ALLOW FILTERING;
~~~

**ALLOW FILTERING** là cách người gọi chấp nhận truy vấn có thể phải lọc sau khi đọc dữ liệu. Nó **không tạo index**, không tối ưu partition key và không biến điều kiện trên cột thường thành một truy vấn truy cập trực tiếp hiệu quả.

Trong một số phiên bản hoặc cách kết hợp điều kiện, truy vấn vẫn có thể bị từ chối hoặc có giới hạn khác dù thêm **ALLOW FILTERING**. Cần đọc lỗi và khả năng của phiên bản Cassandra đang chạy thay vì coi đây là “cờ mở khóa mọi câu SQL”.

### ORDER BY không tạo sắp xếp toàn cục

~~~sql
-- Không thể dùng như một global sort cho mọi tenant và device:
SELECT event_time, device_id
FROM telemetry.events_by_device_hour
ORDER BY event_time DESC
LIMIT 50;
~~~

**ORDER BY** trong Cassandra gắn với thứ tự clustering và các điều kiện hợp lệ trên partition key. Không thể giả định nó sắp xếp mọi hàng của cluster theo một cột thường rồi lấy top 50.

## 7. LIMIT và phân trang không chữa được quét rộng

Một hiểu nhầm phổ biến:

> “Tôi chỉ cần 20 kết quả, cứ đặt LIMIT 20 thì truy vấn sẽ rẻ.”

**LIMIT 20** giới hạn lượng hàng kết quả mà một thao tác trả về theo ngữ nghĩa truy vấn, nhưng **không phải ngân sách cho số hàng phải kiểm tra**. Nếu 20 sự kiện phù hợp nằm rải rác giữa hàng triệu sự kiện, việc tìm chúng vẫn có thể tốn nhiều I/O và CPU.

Phân biệt:

| Khái niệm | Kiểm soát điều gì? | Không bảo đảm điều gì? |
|---|---|---|
| **LIMIT 20** | Tối đa 20 hàng kết quả cho truy vấn phù hợp | Không bảo đảm chỉ đọc 20 hàng vật lý |
| **Driver page size** | Số hàng/khối lượng phản hồi mỗi trang theo cơ chế phân trang driver | Không biến một truy vấn khó thành rẻ hơn về tổng công việc |
| **Paging state** | Cho phép tiếp tục đọc từ trạng thái phân trang | Không tạo thứ tự toàn cục ổn định nếu nhiều truy vấn độc lập và dữ liệu đang thay đổi |
| **Timeout** | Chặn yêu cầu chờ vô hạn | Không khắc phục data model không phù hợp |
| **Giới hạn fan-out** | Kiểm soát số partition được xử lý đồng thời | Có thể tăng tổng thời gian hoàn tất; không làm biến mất lượng dữ liệu cần đọc |

Khi tải lớn, phân trang cần **có giới hạn đồng thời, kích thước trang và khả năng hủy yêu cầu**. Với lịch sử tương tác, nên dùng cursor gắn với partition/time bucket và sắp xếp ổn định thay vì yêu cầu offset rất sâu.

Trong Cassandra, **paging state** từ driver là dữ liệu trạng thái thực thi cần được bảo vệ và dùng đúng với truy vấn tương ứng; không nên tự xem nó như khóa phân trang phổ quát có thể chia sẻ giữa các query khác điều kiện.

## 8. Dung lượng partition và tác động của bucketing

Giả sử một thiết bị đẩy **15 sự kiện/giây**, mỗi event có payload và metadata trung bình **500 byte** trước overhead/nén:

\[
15 \times 3600 = 54\,000\ \text{events/giờ}
\]

\[
54\,000 \times 500 = 27\,000\,000\ \text{byte}
\approx 27\ \text{MB thô/giờ}
\]

Nếu dùng **một partition theo ngày** cho thiết bị này:

\[
15 \times 86\,400 = 1\,296\,000\ \text{events/ngày}
\]

\[
1\,296\,000 \times 500 = 648\,000\,000\ \text{byte}
\approx 648\ \text{MB thô/ngày}
\]

Với bucket **theo giờ**, lượng dữ liệu thô trung bình mỗi partition còn khoảng **27 MB**; với bucket **theo ngày**, partition có thể đạt **648 MB** trước khi tính overhead và cách lưu vật lý.

Đây là ví dụ về lý do thiết kế **bucket**: giới hạn sự tăng trưởng theo thời gian của một partition. Kích thước mục tiêu thực tế phải xác định bằng workload, compaction strategy, cấu hình cluster, phần cứng và đo đạc; **không tồn tại một ngưỡng MB duy nhất đúng cho mọi hệ Cassandra**.

Đổi lại, chia bucket nhỏ hơn làm **số partition của truy vấn khoảng thời gian tăng**. Đọc 24 giờ khi bucket theo giờ có thể phải xử lý 24 partition; theo ngày có thể chỉ cần 1–2 partition, nhưng mỗi partition lớn hơn. Chọn bucket là bài toán cân bằng:

~~~text
Bucket quá lớn:
  ít partition hơn, nhưng mỗi partition nhiều hàng,
  đọc/quét/compaction có thể nặng hơn

Bucket quá nhỏ:
  mỗi partition gọn, nhưng truy vấn khoảng dài
  phải fan-out đến rất nhiều partition
~~~

Nếu có thiết bị phát sinh sự kiện nhiều gấp 100 lần thiết bị thông thường, cùng bucket theo giờ cũng có thể tạo partition quá lớn hoặc rất nóng. Khi đó cần xem mức độ lệch tải (*skew*) giữa các device và có thể bổ sung shard/bucket theo tải, đồng thời chấp nhận việc đọc phải ghép nhiều nhánh.

## 9. Thiết kế bảng khác để phục vụ truy vấn xuyên thiết bị

Yêu cầu B là: “Liệt kê 50 cảnh báo **CRITICAL** mới nhất của tenant **acme** trong 7 ngày.” Với bảng **events_by_device_hour**, truy vấn sẽ phải duyệt nhiều device và nhiều hour bucket.

Một lựa chọn là tạo **bảng truy cập riêng theo tenant, severity và ngày**, thay vì cố tìm trong bảng theo device:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.alerts_by_tenant_severity_day (
  tenant_id text,
  severity text,
  bucket_day date,
  event_time timestamp,
  alert_id uuid,
  device_id text,
  message text,
  PRIMARY KEY (
    (tenant_id, severity, bucket_day),
    event_time,
    alert_id
  )
) WITH CLUSTERING ORDER BY (event_time DESC, alert_id DESC);
~~~

Truy vấn cho một ngày:

~~~sql
SELECT event_time, alert_id, device_id, message
FROM telemetry.alerts_by_tenant_severity_day
WHERE tenant_id = 'acme'
  AND severity = 'CRITICAL'
  AND bucket_day = '2026-11-14'
LIMIT 50;
~~~

Để lấy 7 ngày, ứng dụng biết tối đa **7 partition theo ngày** cho tenant và severity đó. Có thể đọc theo từng ngày từ mới nhất đến cũ nhất rồi ghép theo **event_time DESC, alert_id DESC**, dừng khi đủ 50 kết quả và xử lý các trường hợp đồng thời/ties theo hợp đồng phân trang.

**Đây là data modeling theo truy vấn**: cùng một sự kiện có thể được ghi vào bảng lịch sử thiết bị và, nếu là cảnh báo, bảng cảnh báo theo tenant. Bảng thứ hai cung cấp đường đọc nghiệp vụ khác.

### Sơ đồ hai đường truy cập

~~~mermaid
flowchart TD
    E["Sự kiện phát sinh từ thiết bị"] --> W["Dịch vụ ghi sự kiện"]
    W --> D["events_by_device_hour"]
    W --> A["alerts_by_tenant_severity_day, nếu là alert"]
    D --> P["API: nhật ký một thiết bị"]
    A --> Q["API: cảnh báo toàn tenant"]
    E --> R["Luồng dữ liệu phân tích khi cần"]
    R --> S["Kho phân tích / báo cáo nhiều tenant"]
~~~

Việc ghi vào hai bảng **không tự động bảo đảm tính nguyên tử đa bảng**. Nếu ghi bảng thiết bị thành công nhưng ghi bảng alert thất bại, hai màn hình sẽ tạm thời không nhất quán. Cần xác định:

1. Nguồn dữ liệu nào là **sự thật nghiệp vụ**.
2. Retry và idempotency khi ghi sự kiện; **event_id/alert_id** phải ổn định qua các lần thử lại.
3. Cách ghi lại hoặc dựng lại bảng alert nếu một consumer thất bại.
4. Độ trễ đồng bộ được chấp nhận và cách giám sát backlog.
5. Chính sách TTL/xóa để hai bảng không giữ dữ liệu quá thời hạn khác nhau một cách vô ý.

Không nên mặc định một **Cassandra batch** là giải pháp tăng tốc cho ghi vào nhiều partition. Batch nhiều partition có chi phí và ngữ nghĩa riêng; nó không tương đương transaction quan hệ với isolation đầy đủ, và không thay thế thiết kế nhất quán theo nghiệp vụ.

### Điều kiện phải cân nhắc lại

Nếu tenant rất lớn tạo hàng triệu cảnh báo CRITICAL mỗi ngày, partition **(tenant, severity, day)** vẫn có thể quá rộng hoặc quá nóng. Có thể chuyển sang bucket theo giờ, hoặc phân mảnh thêm bằng **shard_id**:

~~~text
(tenant_id, severity, bucket_hour, shard_id)
~~~

Lúc đó đọc top 50 phải hỏi nhiều shard của các giờ liên quan rồi gộp; cần tính trước **số shard × số bucket**. Sharding tăng khả năng phân tán ghi nhưng làm phức tạp đường đọc, nên phải dựa trên số liệu tải và ngân sách fan-out.

## 10. Có thể dùng index thay vì tạo bảng riêng không?

Cassandra và các wide-column database có những khả năng index khác nhau. Trong một số phiên bản/cấu hình Cassandra, **secondary index** hoặc **Storage-Attached Indexing (SAI)** có thể hỗ trợ truy vấn theo cột không nằm trong partition key.

Nhưng câu hỏi đúng không phải “có tạo index được không?” mà là:

- Index có được hỗ trợ trên phiên bản/phân phối đang chạy không?
- Bộ lọc có **độ chọn lọc (selectivity)** phù hợp không?
- Index có phải tìm qua nhiều node/partition trước khi có đủ kết quả không?
- Query cần **ORDER BY mới nhất toàn cục** hay chỉ tìm candidate rồi xử lý ở ứng dụng?
- Tải ghi, cập nhật, tombstone và chi phí lưu index tăng bao nhiêu?
- Khả năng kết hợp nhiều điều kiện lọc và mức nhất quán của index có đáp ứng hợp đồng không?

Ví dụ **severity = CRITICAL** có thể là một thuộc tính ít giá trị phân biệt nếu số sự kiện CRITICAL rất lớn. Index không mặc nhiên biến truy vấn “top 50 mới nhất trên 90 ngày toàn cluster” thành truy vấn rẻ, đặc biệt khi thứ tự theo thời gian không được phục vụ trực tiếp bởi đường truy cập đó.

### Các lựa chọn theo mục đích

| Mục đích | Phương án ứng viên | Đánh đổi |
|---|---|---|
| Lấy sự kiện một thiết bị trong vài giờ | Bảng partition theo thiết bị × giờ | Tốt cho đường đọc cụ thể; nhiều bucket khi tra rất dài |
| Lấy cảnh báo theo tenant và mức độ | Bảng theo tenant × severity × bucket thời gian | Nhân bản dữ liệu theo access pattern; cần đồng bộ |
| Lọc theo một số thuộc tính khác trên dữ liệu lớn | Secondary index/SAI nếu sản phẩm hỗ trợ và benchmark đạt | Chi phí index; hạn chế truy vấn tùy phiên bản |
| Tìm văn bản và nhiều trường linh hoạt | Search engine được đồng bộ từ nguồn dữ liệu | Chi phí vận hành, độ trễ đồng bộ |
| Quét, tổng hợp toàn hệ thống nhiều tháng | Kho analytics / batch processing | Dữ liệu có thể trễ, truy vấn khác với API giao dịch |
| Truy vấn ad hoc của quản trị viên | Job nền có giới hạn tài nguyên và truy vết tiến độ | Không đáp ứng luôn yêu cầu trả kết quả tức thì |

**Materialized view** hoặc một tập read model có thể hữu ích trong những hệ hỗ trợ, nhưng cần hiểu ngữ nghĩa đồng bộ, hạn chế vận hành và khả năng sửa lỗi trước khi dùng làm nguồn dữ liệu quan trọng.

## 11. Quét toàn bảng và token range chỉ phù hợp khi đã hiểu chi phí

Cassandra cho phép những kiểu thao tác quét dữ liệu như đọc theo **token ranges** trong công cụ chuyên dụng hoặc tác vụ nền. Điều này khác với truy vấn trực tuyến theo một partition key xác định.

Trong cơ chế partitioning theo hash/token:

~~~text
Toàn bộ token ring:
  [dải token A] [dải token B] [dải token C] ...

Partition của từng (tenant, device, hour):
  -> token tương ứng
  -> replica theo topology cluster
~~~

Một job toàn bảng có thể chia việc theo dải token cho nhiều worker, quản lý checkpoint và đọc theo batch. Nhưng:

- **Thứ tự token không phải thứ tự thời gian**; không thể coi quét token tăng dần là đọc sự kiện cũ tới mới.
- Quét lớn có thể tranh I/O, cache và network với workload ứng dụng.
- Việc dừng giữa chừng, restart, đọc trùng hoặc dữ liệu thay đổi trong lúc quét cần có quy tắc xử lý.
- Cần giới hạn concurrency, tốc độ và ưu tiên tác vụ để không làm giảm dịch vụ trực tuyến.
- Xóa TTL/tombstone và compaction có thể khiến lượng dữ liệu thực tế phải đi qua lớn hơn số kết quả cần xuất.

Với quét phục vụ analytics, cách tiếp cận thường là **job có kiểm soát, có checkpoint, có giới hạn tài nguyên**. Không nên đưa một truy vấn quét toàn cluster vào API mà người dùng mong phản hồi trong vài trăm mili giây.

## 12. Tombstone làm chi phí đọc và lọc khó nhìn thấy

Cassandra sử dụng **tombstone** để biểu thị dữ liệu đã bị xóa hoặc hết hạn theo TTL trong mô hình lưu trữ phân tán. Tombstone có vai trò giúp đồng bộ trạng thái xóa giữa replica; dữ liệu cũ/tombstone có thể còn tồn tại trong SSTable cho tới các quá trình dọn nền thích hợp.

Một truy vấn trả 10 hàng hợp lệ có thể phải đi qua rất nhiều dữ liệu đã bị xóa hoặc hết hạn. Vì thế, số hàng trả về nhỏ **không chứng minh** lượng I/O nhỏ.

Ví dụ dữ liệu sự kiện có TTL:

~~~sql
-- Ví dụ minh họa cú pháp TTL khi ghi.
-- Các giá trị key cần trùng chính xác theo thiết kế bảng.
INSERT INTO telemetry.events_by_device_hour (
  tenant_id, device_id, hour_bucket,
  event_time, event_id, event_type, severity, payload_json
)
VALUES (
  'acme', 'device-08', '2026-11-14T09',
  '2026-11-14T09:42:10Z', 11111111-1111-4111-8111-111111111111,
  'TEMPERATURE_ALERT', 'CRITICAL', '{"celsius":95}'
)
USING TTL 2592000;
~~~

Giá trị **2592000 giây** tương đương 30 ngày. TTL giúp dữ liệu hết hạn logic theo chính sách, nhưng không có nghĩa các byte vật lý biến mất đúng thời điểm, hay compaction sẽ ngay lập tức giảm kích thước ổ đĩa.

Khi thiết kế truy vấn có quét rộng, cần tính đến:

- Số tombstone đi qua khi đọc range dài.
- Sự phân bố TTL/xóa, cách ứng dụng cập nhật và ghi đè.
- Compaction strategy và chu kỳ dữ liệu.
- gc_grace_seconds, cơ chế repair và các điều kiện cần thiết để xử lý xóa an toàn trong cấu hình cụ thể.
- Khả năng query hoặc batch lớn gặp latency tăng, timeout hay cảnh báo tombstone.

Không nên giảm các tham số an toàn của tombstone/repair chỉ để “làm truy vấn nhanh hơn” khi chưa hiểu cơ chế phục hồi replica và nguy cơ dữ liệu đã xóa xuất hiện lại.

## 13. Định lượng fan-out, selectivity và read amplification

Để nhận biết truy vấn khó, không chỉ đo latency mà còn cần định lượng lượng dữ liệu đã được xem xét.

### Fan-out của truy vấn

Với truy vấn đọc tất cả thiết bị trong một khoảng:

\[
\text{Partitions dự kiến}
\approx \text{Devices cần xét}
\times \text{Buckets/device}
\times \text{Shards/bucket}
\]

Nếu có 200 thiết bị × 24 giờ × 2 shard, kết quả tối đa là:

\[
200 \times 24 \times 2 = 9600\ \text{partitions}
\]

Đây là số partition logic ứng viên theo thiết kế ví dụ. Partition có thể rỗng, nhiều replica phục vụ và driver có thể gom hoạt động thành những yêu cầu mạng khác nhau. Con số hữu ích để đặt **ngân sách đường đọc**, nhưng không thay thế metrics thực tế.

### Độ chọn lọc và lượng hàng cần đọc

Giả sử trong một dải có 1.000.000 sự kiện, chỉ 500 sự kiện là CRITICAL:

\[
\text{Selectivity}=\frac{500}{1\,000\,000}=0{,}05\%
\]

Nếu không có đường truy cập/index giúp định vị 500 sự kiện, cơ sở dữ liệu có thể phải xem xét lượng dữ liệu gần với toàn bộ dải mới lấy đủ kết quả, ngay cả khi kết quả chỉ chiếm 0,05%.

Một phép đo ý niệm:

\[
\text{Read amplification}
=\frac{\text{hàng/byte phải đọc hoặc xét}}{\text{hàng/byte có ích trả về}}
\]

Đây là **thước đo tư duy**; công thức cụ thể phải dựa trên metrics hiện có của hệ thống. Không phải mọi database đều xuất sẵn một chỉ số read amplification cùng đơn vị.

### Giới hạn tài nguyên cần đặt từ đầu

| Ngân sách | Câu hỏi thiết kế |
|---|---|
| Khoảng thời gian tối đa | API được phép đọc 24 giờ, 7 ngày hay 90 ngày? |
| Số partition tối đa mỗi request | Bao nhiêu bucket/device/shard được phép chạm? |
| Độ đồng thời | Tối đa bao nhiêu truy vấn con chạy song song để tránh nghẽn? |
| Page size và số hàng tối đa | Mỗi response trả bao nhiêu hàng/byte? |
| Timeout và retry | Request nào được retry, bao nhiêu lần, có tạo bão tải không? |
| Độ trễ p95/p99 | Khi hệ thống ở tải định mức, bao nhiêu người dùng bị chậm? |
| Độ trễ dữ liệu dẫn xuất | Bảng alert/read model chậm bao lâu là được chấp nhận? |

Giới hạn kỹ thuật phải phù hợp trải nghiệm nghiệp vụ. Nếu người dùng thật sự cần tra cứu 90 ngày, giải pháp có thể là **đặt một tác vụ nền và trả link kết quả sau khi hoàn tất**, thay vì silently cắt dải xuống 7 ngày rồi coi đó là kết quả đúng.

## 14. Quan sát truy vấn: cần nhìn nhiều hơn thời gian chạy

Với Cassandra, công cụ và phiên bản có thể cung cấp **tracing**, thống kê bảng, JMX/metrics, log cảnh báo, công cụ quan sát driver và giám sát các node.

Ví dụ trong **cqlsh**:

~~~sql
TRACING ON;

SELECT event_time, severity
FROM telemetry.events_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 'device-08'
  AND hour_bucket = '2026-11-14T09'
LIMIT 20;

TRACING OFF;
~~~

Tracing được dùng có chọn lọc trong môi trường cho phép; nó có chi phí và không nên bật bừa bãi cho mọi truy vấn production. Nếu đang tối ưu, đối chiếu các thông tin:

| Tín hiệu | Điều cần suy ra |
|---|---|
| **Partition key và clustering range trong yêu cầu** | Driver có định vị đúng partition và giới hạn dải không? |
| **Số partition/bucket ứng dụng truy vấn** | Fan-out thực tế có đúng ngân sách không? |
| **Truy vấn theo token hoặc filtering** | Có đang đi qua tập dữ liệu rộng hơn kết quả không? |
| **Rows/bytes trả về, page size** | Response có phù hợp khả năng tải và UI không? |
| **Read latency p95/p99** | Phần lớn request và đuôi chậm phản ứng thế nào dưới tải? |
| **Read timeout, unavailable, retry** | Truy vấn quá nặng, network hoặc replication có gặp vấn đề không? |
| **Partition size / số hàng theo partition** | Có một device/bucket/tenant quá lớn không? |
| **Tombstones scanned / cảnh báo tombstone** | Hàng đã xóa/hết hạn có làm đọc chậm không? |
| **Compaction, disk I/O, cache hit, CPU** | Chi phí vật lý và vận hành có tăng theo kiểu truy vấn không? |
| **Độ trễ đồng bộ bảng dẫn xuất** | API B có đang hiển thị thiếu các alert mới nhất không? |

Không thể kết luận “truy vấn tốt” từ một lần chạy trên ba partition mẫu. Cần mô phỏng kích thước lớn, tenant lệch tải, số device thực tế, tỷ lệ severity, TTL và độ đồng thời gần với production.

### Trường hợp điển hình: truy vấn trả ít hàng nhưng vẫn timeout

~~~text
Yêu cầu:
  20 cảnh báo CRITICAL mới nhất toàn hệ thống

Bảng có:
  partition theo tenant + device + hour
  severity chỉ là regular column

Truy vấn:
  không định vị partition, lọc nhiều hàng

Kết quả:
  có thể chỉ tìm thấy 20 hàng sau khi đọc rất nhiều dữ liệu,
  gây timeout hoặc latency cao
~~~

Thay đổi **LIMIT 20** thành **LIMIT 10** không sửa bản chất vấn đề. Cần sửa **đường truy cập**: bảng alert theo chiều truy vấn, index đã đánh giá hiệu quả, hoặc pipeline phân tích/tìm kiếm.

## 15. Đối chiếu với Bigtable, HBase và các hệ khác

Tên “mô hình cột rộng” là một nhóm khái niệm; cách tối ưu truy vấn phải dựa vào cơ chế từng sản phẩm.

| Hệ | Cách định vị điển hình | Hành vi cần nhớ khi quét rộng |
|---|---|---|
| **Apache Cassandra** | Partition key định tuyến token; clustering columns sắp thứ tự trong partition | CQL có giới hạn trên partition/clustering restrictions; lọc rộng có thể bị từ chối hoặc đắt |
| **Google Cloud Bigtable** | Row key có thứ tự từ điển; đọc một row hoặc dải row key | Quét prefix/range thuận lợi nếu row key được thiết kế đúng; lọc trên cell không thay thế row-key locality |
| **Apache HBase** | Row key được sắp theo thứ tự, region phục vụ các dải key | Scan theo start/stop row là đường quan trọng; filter có thể loại dữ liệu nhưng vẫn phát sinh I/O |
| **Amazon DynamoDB** | Partition key và sort key của table/index; Query hoặc Scan | Query theo key hữu ích; Scan có thể đọc rộng, FilterExpression không làm giảm dữ liệu đọc trước lọc theo cùng cách như key lookup |

Ở Bigtable/HBase, **row key có thứ tự** làm cho việc thiết kế prefix và range mang ý nghĩa khác với Cassandra partition token hashing. Chẳng hạn, key **tenant#date#device#event** có thể giúp quét dải theo prefix phù hợp, nhưng còn có nguy cơ hotspot khi giá trị thời gian tăng tuần tự. Không thể áp dụng nguyên xi quy tắc “một hourly partition Cassandra” sang row-key range scan của Bigtable.

Trong DynamoDB, **FilterExpression** trên kết quả Query/Scan không biến truy vấn Scan thành đọc trực tiếp bằng index. Nó có thể làm số item trả ít hơn số item đã đọc để đánh giá filter; cần quan sát read capacity và pagination của sản phẩm đó. Các ngữ nghĩa và giới hạn này khác **ALLOW FILTERING** của Cassandra.

## 16. Các lỗi thiết kế thường gặp

| Lỗi | Vì sao không đạt yêu cầu | Hướng xử lý |
|---|---|---|
| Chọn partition key theo trường ít khi được gửi trong API | Truy vấn không xác định được phân vùng | Bắt đầu từ access pattern và đầu vào thực tế |
| Lưu mọi sự kiện của một device vào một partition không có bucket | Partition tăng vô hạn, khó quét range dài | Time bucketing theo tải và nhu cầu đọc |
| Đặt bucket quá nhỏ cho mọi dữ liệu | Truy vấn nhiều ngày phát sinh fan-out lớn | Tính số bucket trên mỗi query |
| Thêm **ALLOW FILTERING** để mọi query chạy được | Chỉ chấp nhận nguy cơ quét, không tạo đường đọc tốt | Thiết kế bảng/index theo truy vấn |
| Thấy **LIMIT** nhỏ nên cho rằng truy vấn rẻ | Có thể đọc rất nhiều hàng rồi mới lấy vài hàng | Quan sát công việc đọc, selectivity và tombstone |
| Tin **ORDER BY** sắp toàn cluster | Clustering order chỉ có ý nghĩa trong phạm vi được hỗ trợ | Merge các partition hoặc tạo bảng theo đường đọc |
| Tạo một bảng duy nhất cho mọi màn hình | Query theo device và query theo tenant cần khóa khác nhau | Cân nhắc nhiều bảng truy cập/read model |
| Nhân bản bảng mà không có retry/đối soát | Các đường đọc có thể hiển thị dữ liệu không nhất quán | Event ID ổn định, idempotency, replay và metrics |
| Xử lý 10.000 partition cùng lúc | Tạo spike tải, timeout, bão retry | Giới hạn fan-out và concurrency, hoặc đổi kiến trúc |
| Bỏ qua tombstone khi tối ưu | Quét ít kết quả vẫn có thể nặng | Đo tombstone, TTL, compaction và kích thước partition |
| Dùng bảng giao dịch cho báo cáo ad hoc toàn hệ thống | Gây cạnh tranh tài nguyên với API chính | Data pipeline và kho analytics phù hợp |

## 17. Quy trình thiết kế truy vấn khi phạm vi đọc mở rộng

Một quy trình có thể tái sử dụng:

**Bước 1 — Viết hợp đồng truy vấn.** Người gọi biết tenant, device, khoảng thời gian, loại sự kiện hay severity? Cần lấy chi tiết hay tổng hợp? Cần kết quả mới đến mức nào?

**Bước 2 — Từ hợp đồng suy ra partition key.** Nếu có thể dựng chính xác key, query có thể định vị dữ liệu. Nếu chỉ dựng được nhiều key, phải tính số lượng. Nếu không dựng được, cần tìm đường truy cập khác.

**Bước 3 — Đánh giá clustering.** Dữ liệu trong mỗi partition được sắp theo chiều cần đọc chưa? Có thể dùng time range và LIMIT trước khi tải payload không?

**Bước 4 — Ước lượng kích thước và số partition.** Dùng lưu lượng ghi × kích thước × thời gian bucket; xét tenant/device có tải cao hơn trung bình.

**Bước 5 — Chọn đường đọc.** Một bảng hiện tại, một số partition có kiểm soát, một bảng dữ liệu dẫn xuất, index thích hợp hay dịch vụ phân tích riêng?

**Bước 6 — Chốt đồng bộ và lifecycle.** Nếu có bảng dẫn xuất, xác định source of truth, retry, deduplication, TTL, xóa và đối soát.

**Bước 7 — Đặt ngân sách và đo.** Fan-out, page size, p95/p99 latency, tombstone, throughput, disk/compaction và chi phí vận hành.

~~~mermaid
flowchart TD
    A["Đầu vào truy vấn"] --> B{"Dựng được một partition key?"}
    B -->|Có| C["Bounded clustering range + LIMIT"]
    B -->|Không| D{"Dựng được ít partition cụ thể?"}
    D -->|Có| E["Bounded fan-out + merge + paging"]
    D -->|Không| F{"Có query/index phù hợp được hỗ trợ?"}
    F -->|Có| G["Benchmark index trên workload thật"]
    F -->|Không| H["Thiết kế access table hoặc analytics"]
    C --> I["Đo latency, số hàng và tombstone"]
    E --> I
    G --> I
    H --> I
    I --> J{"Đạt SLO và chi phí?"}
    J -->|Chưa| A
    J -->|Có| K["Giám sát khi tải và dữ liệu tăng"]
~~~

## 18. Bài tập áp dụng

### Bài tập 1 — Nhận diện phân vùng

Với bảng **events_by_device_hour**, hãy chỉ ra partition key, clustering columns và thứ tự vật lý bên trong một partition. Đánh giá ba truy vấn:

1. Lấy 20 sự kiện của **acme/device-08** trong giờ **2026-11-14T09**.
2. Lấy 20 sự kiện của **acme/device-08** trong 7 ngày, không nêu hour_bucket.
3. Lấy 20 sự kiện CRITICAL mới nhất toàn tenant **acme**.

Truy vấn nào dùng trực tiếp đường primary key? Với hai truy vấn còn lại, cần bao nhiêu bucket hoặc cần đổi access pattern?

### Bài tập 2 — Chọn kích thước bucket

Một thiết bị ghi 8 sự kiện/giây, mỗi sự kiện 700 byte trước overhead/nén. Hãy tính số hàng và số byte thô của partition theo **giờ** và theo **ngày**. Nếu API thường đọc 6 giờ nhưng thỉnh thoảng đọc 30 ngày, giải thích đánh đổi giữa kích thước partition và số partition phải truy vấn.

### Bài tập 3 — Vì sao LIMIT chưa đủ?

Một bảng có 5 triệu sự kiện và chỉ 0,01% phù hợp với severity cần tìm. Người phát triển dùng **ALLOW FILTERING LIMIT 10** rồi cho rằng cơ sở dữ liệu chỉ cần đọc 10 hàng. Hãy chỉ ra sự khác nhau giữa hàng phải đọc và hàng trả về, đồng thời đề xuất cách xác định đường truy cập mới.

### Bài tập 4 — Màn hình cảnh báo toàn tenant

Thiết kế một bảng giúp truy vấn 50 CRITICAL event mới nhất trong 7 ngày theo tenant. Nếu tenant lớn tạo 5 triệu cảnh báo/ngày, hãy đề xuất time bucket/shard phù hợp, nêu số partition tối đa phải xét khi đọc 7 ngày và cách gộp thứ tự thời gian.

### Bài tập 5 — Tránh sai lệch dữ liệu nhân bản

Một sự kiện được ghi vào **events_by_device_hour** nhưng việc ghi **alerts_by_tenant_severity_day** thất bại do timeout. Hãy mô tả cách retry idempotent, phát hiện bảng alert bị thiếu dữ liệu và xử lý event được phát lại sau nhiều giờ.

### Bài tập 6 — Truy vấn phân tích nhiều tháng

Đội phân tích cần tổng hợp tỷ lệ CRITICAL theo từng loại thiết bị trên tất cả tenant trong 180 ngày. Đánh giá vì sao fan-out từ API giao dịch không phù hợp. Hãy đề xuất các bước từ nguồn dữ liệu đến kho phân tích, xác định độ mới dữ liệu, cơ chế backfill và cách kiểm chứng số liệu.

### Bài tập 7 — Chẩn đoán thời gian chậm bất thường

Hai truy vấn cùng trả 20 hàng, cùng partition key, nhưng một truy vấn nhanh và truy vấn còn lại rất chậm. Hãy điều tra sự khác biệt về clustering range, số hàng cần đi qua, số tombstone, kích thước partition, cache và compaction. Nêu metrics hoặc tracing nào giúp kiểm chứng từng giả thuyết.

Khi giải bài, hãy trình bày chuỗi **đầu vào nghiệp vụ → partition/clustering key → số partition và số hàng cần xét → cách lọc, sắp xếp, phân trang → chi phí đo được**. Đây là kỹ năng cốt lõi khi thiết kế mô hình cột rộng: hiểu chính xác phạm vi dữ liệu mà một truy vấn buộc hệ thống phải đọc, từ đó chọn đường truy cập phù hợp thay vì dựa vào cú pháp **WHERE** hoặc **LIMIT** để hy vọng database tự tối ưu.
