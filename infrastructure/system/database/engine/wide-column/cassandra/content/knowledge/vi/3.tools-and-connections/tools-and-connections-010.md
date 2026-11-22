# COPY trong cqlsh, giới hạn quy mô và công cụ nạp dữ liệu thay thế

## 1. COPY là gì và dùng trong trường hợp nào?

**Apache Cassandra** là cơ sở dữ liệu **wide-column phân tán**. Trong môi trường thực tế, việc nạp dữ liệu cần xét đến partition key, clustering columns, replication factor, consistency level, số node đang phục vụ và tải compaction/streaming. Ở chương **Công cụ và kết nối** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, lệnh `COPY` trong **cqlsh** giúp thực hành nhập/xuất CSV và nhận biết giới hạn khi vận hành hệ thống nhiều node.

`COPY` là **lệnh tiện ích của cqlsh**, không phải cú pháp CQL tổng quát mà ứng dụng Java có thể gửi qua `CqlSession.execute("COPY ...")`. Nó có hai hướng:

- **`COPY ... FROM 'file.csv'`:** cqlsh đọc CSV từ nơi **tiến trình cqlsh đang chạy**, chuyển các dòng thành thao tác ghi vào một **bảng đã tồn tại** trong Cassandra.
- **`COPY ... TO 'file.csv'`:** cqlsh đọc dữ liệu của bảng qua Cassandra native protocol rồi ghi CSV ra nơi **tiến trình cqlsh đang chạy**.

Hai thao tác dùng cùng đường kết nối ứng dụng → native protocol, thường TCP **9042**. Coordinator và replica vẫn xử lý CQL theo schema, replication và consistency; `COPY` không tạo một đường truyền riêng “bỏ qua” Cassandra.

| Tình huống | COPY có phù hợp? | Lưu ý |
| --- | --- | --- |
| Thử 50–1.000 dòng dữ liệu mẫu trong lab | **Có** | Tệp CSV dễ kiểm tra, số lỗi dễ đối chiếu. |
| Nhập một tập CSV nhỏ/vừa đã biết schema | **Có thể** | Đánh giá tải và xác minh từng partition. |
| Xuất dữ liệu nhỏ để khảo sát hoặc kiểm tra thủ công | **Có thể** | CSV là bản xuất dữ liệu, không phải backup hoàn chỉnh. |
| Di chuyển dữ liệu rất lớn giữa cluster | **Thường không phải lựa chọn đầu tiên** | Dùng công cụ bulk/streaming chuyên dụng hoặc pipeline phân tán. |
| Sao lưu và khôi phục chính xác schema, TTL, tombstone, quyền, dữ liệu tại một thời điểm | **Không** | Cân nhắc snapshot/SSTable và quy trình backup/restore phù hợp. |
| Đồng bộ thay đổi liên tục giữa các hệ thống | **Không** | Cần pipeline CDC/streaming hoặc connector có checkpoint. |

**Mục tiêu bài học:** chạy được `COPY FROM` và `COPY TO` có kiểm soát; hiểu ánh xạ cột, CSV, lỗi dữ liệu và primary key; biết chọn công cụ khác khi vượt quá quy mô của cqlsh.

## 2. COPY tác động tới đâu trong kiến trúc Cassandra?

~~~mermaid
flowchart LR
    CSV["File CSV trên máy chạy cqlsh"] -->|"COPY FROM: đọc và chuyển dòng"| SH["cqlsh"]
    SH -->|"Native CQL / TCP 9042"| CO["Node coordinator"]
    CO -->|"Ghi theo token/partition và CL"| R1["Replica A"]
    CO -->|"Ghi theo token/partition và CL"| R2["Replica B"]
    CO -->|"Ghi theo token/partition và CL"| R3["Replica C"]
    R1 -.->|"Đọc qua coordinator"| CO
    R2 -.->|"Đọc qua coordinator"| CO
    CO -.->|"COPY TO: kết quả CQL"| SH
    SH -.->|"Ghi CSV"| OUT["File xuất trên máy chạy cqlsh"]
~~~

Sơ đồ mô tả cluster nhiều replica. Với lab **một node RF = 1**, chỉ có replica tương ứng; với cluster nhiều datacenter, replica và consistency được xác định theo cấu hình thật.

Hệ quả quan trọng:

1. `COPY FROM` **không quyết định node lưu dữ liệu**. Cassandra xác định token từ **partition key** và chọn replica theo replication strategy.
2. `COPY` vẫn chịu **network latency, native protocol, authentication, authorization và consistency** như các thao tác CQL thông thường.
3. `COPY TO` đọc qua các request thông thường; nó **không bảo đảm snapshot nhất quán trong toàn bộ thời gian xuất** khi dữ liệu vẫn đang thay đổi.
4. File CSV tồn tại ở phía **client cqlsh**, không tự sinh trên tất cả node Cassandra.
5. `COPY` không tự tạo keyspace, bảng, index, role, quyền hay chính sách replication. Schema phải được chuẩn bị trước.

## 3. Chuẩn bị lab: thiết kế bảng theo truy vấn trước khi nhập

### 3.1. Điều kiện

Ví dụ giả định:

- Có Cassandra đơn node cho lab, cqlsh kết nối được `127.0.0.1:9042`.
- Có quyền tạo keyspace/bảng và đọc ghi dữ liệu mẫu.
- File CSV có định dạng UTF-8 đơn giản, header và thứ tự cột được kiểm tra.
- Các lệnh chỉ chạy trong **môi trường lab**, không áp dụng vô điều kiện cho production.

Mở cqlsh từ terminal:

~~~bash
cqlsh 127.0.0.1 9042
~~~

Ở dấu nhắc cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS cqlsh_copy_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS cqlsh_copy_lab.readings_by_device_day (
  device_id text,
  reading_day date,
  read_at timestamp,
  reading_id uuid,
  metric text,
  value double,
  PRIMARY KEY ((device_id, reading_day), read_at, reading_id)
) WITH CLUSTERING ORDER BY (read_at DESC, reading_id ASC);

DESCRIBE KEYSPACE cqlsh_copy_lab;
DESCRIBE TABLE cqlsh_copy_lab.readings_by_device_day;
~~~

Với bảng này:

- **Composite partition key**: `(device_id, reading_day)`. Các bản ghi của một thiết bị trong một ngày cùng partition.
- **Clustering columns**: `read_at` và `reading_id`. Chúng giúp sắp xếp bản ghi theo thời gian và đảm bảo primary key không trùng khi có nhiều sự kiện tại một thời điểm.
- **Truy vấn đích**: đọc bản ghi của **một thiết bị trong một ngày**, có thể giới hạn thời gian dựa trên clustering column.
- **RF = 1 và SimpleStrategy**: chỉ để thực hành trên một node. Trong hệ nhiều datacenter thường dùng `NetworkTopologyStrategy` và replication factor thích hợp theo DC.

Khi thiết kế dữ liệu lớn, cần xét số bản ghi **mỗi partition**. Một partition key như `device_id` đơn lẻ có thể dẫn tới partition tăng không kiểm soát; thêm `reading_day` là một ví dụ **time bucketing**, nhưng độ rộng bucket cần dựa trên tốc độ sinh dữ liệu thực tế.

### 3.2. Tạo file CSV đúng cột và kiểu

Tạo file văn bản tên `readings.csv` ở **máy chạy cqlsh**, với nội dung:

~~~csv
device_id,reading_day,read_at,reading_id,metric,value
sensor-01,2026-11-21,2026-11-21T01:00:00Z,11111111-1111-4111-8111-111111111111,temperature,25.1
sensor-01,2026-11-21,2026-11-21T01:05:00Z,22222222-2222-4222-8222-222222222222,temperature,25.3
sensor-02,2026-11-21,2026-11-21T01:02:00Z,33333333-3333-4333-8333-333333333333,humidity,60.0
sensor-02,2026-11-22,2026-11-22T01:02:00Z,44444444-4444-4444-8444-444444444444,humidity,61.0
~~~

Kiểm tra trước khi nhập:

| Cột CSV | Kiểu Cassandra | Điều kiện |
| --- | --- | --- |
| `device_id` | `text` | Không bỏ trống vì là một phần partition key. |
| `reading_day` | `date` | Định dạng ngày hợp lệ, ví dụ `2026-11-21`. |
| `read_at` | `timestamp` | Nên ghi rõ múi giờ, ví dụ hậu tố `Z` (UTC). |
| `reading_id` | `uuid` | UUID hợp lệ; xác định duy nhất row cùng thời gian. |
| `metric` | `text` | Chuỗi mô tả loại phép đo. |
| `value` | `double` | Số dùng dấu chấm thập phân theo cú pháp dữ liệu ví dụ. |

**Không mặc định header CSV là lệnh tạo schema.** Bảng đã có cấu trúc xác định. Danh sách cột trong `COPY` cần tương ứng với thứ tự dữ liệu của file; `HEADER = TRUE` dùng để nhận biết/bỏ qua dòng tiêu đề, không phải cam kết có thể tự hoán đổi mọi cột theo tên.

## 4. COPY FROM: nạp CSV vào bảng có sẵn

### 4.1. Cú pháp

Tại dấu nhắc `cqlsh>`:

~~~sql
COPY cqlsh_copy_lab.readings_by_device_day
  (device_id, reading_day, read_at, reading_id, metric, value)
FROM 'readings.csv'
WITH HEADER = TRUE;
~~~

Lệnh này chỉ chạy sau khi file `readings.csv` tồn tại và đường dẫn đọc được từ **tiến trình cqlsh**. Tên keyspace và bảng được ghi đầy đủ để tránh nhầm ngữ cảnh `USE`.

Nếu file không nằm trong thư mục làm việc, hãy truyền **đường dẫn tuyệt đối** phù hợp môi trường:

~~~sql
-- Ví dụ trên môi trường Linux có file thực sự ở đường dẫn này.
COPY cqlsh_copy_lab.readings_by_device_day
  (device_id, reading_day, read_at, reading_id, metric, value)
FROM '/workspace/import/readings.csv'
WITH HEADER = TRUE;
~~~

Trên Windows, đường dẫn và cách quote cần tương ứng với cqlsh/Python và shell đang chạy. Không suy ra cqlsh sẽ đọc file trên **server Cassandra** chỉ vì câu lệnh chạy trong cqlsh kết nối tới server đó.

### 4.2. Kiểm tra dữ liệu theo partition key

~~~sql
-- Kiểm tra sensor-01 trong ngày 2026-11-21.
SELECT read_at, metric, value
FROM cqlsh_copy_lab.readings_by_device_day
WHERE device_id = 'sensor-01'
  AND reading_day = '2026-11-21';

-- Kiểm tra sensor-02 trong ngày 2026-11-21.
SELECT read_at, metric, value
FROM cqlsh_copy_lab.readings_by_device_day
WHERE device_id = 'sensor-02'
  AND reading_day = '2026-11-21';

-- Kiểm tra sensor-02 sang ngày 2026-11-22.
SELECT read_at, metric, value
FROM cqlsh_copy_lab.readings_by_device_day
WHERE device_id = 'sensor-02'
  AND reading_day = '2026-11-22';
~~~

Kết quả kỳ vọng:

| Partition | Số row mong đợi | Giá trị |
| --- | ---: | --- |
| `('sensor-01', '2026-11-21')` | 2 | `25.3` và `25.1`, theo `read_at` giảm dần. |
| `('sensor-02', '2026-11-21')` | 1 | `60.0`. |
| `('sensor-02', '2026-11-22')` | 1 | `61.0`. |

Kiểm tra từng partition biết trước giúp tránh truy vấn `SELECT COUNT(*) FROM keyspace.table` toàn bảng trên dataset lớn. **COUNT(*) toàn bảng không phải phép kiểm tra bulk migration miễn phí**; nó có thể quét rất nhiều partition và tạo tải đáng kể.

### 4.3. Chạy lại COPY FROM có tạo dữ liệu trùng không?

Trong Cassandra, `INSERT` theo cùng primary key thường có hành vi **upsert**. Với file có UUID và timestamp **cố định**, chạy lại `COPY FROM` có thể ghi đè các cell của cùng row thay vì tạo row mới. Tuy nhiên:

- Nếu CSV tạo `reading_id` mới mỗi lần, các dòng đó thành **row khác**.
- Nếu giá trị, timestamp ghi, TTL hoặc dữ liệu khác thay đổi, tác động của lần nhập lại cần được đánh giá.
- Nếu có nhiều writer cùng sửa một primary key, thứ tự chạy file không bảo đảm dữ liệu cuối cùng phản ánh “dòng được nhập sau cùng” theo thời gian đồng hồ. Cassandra xử lý xung đột theo cơ chế timestamp của dữ liệu.
- `COPY FROM` **không** biến cả file thành transaction. Những dòng đã ghi thành công không tự rollback khi một dòng khác lỗi.

Do đó, hãy thiết kế **primary key ổn định, tính idempotent của pipeline** và cơ chế tái chạy sau lỗi **trước** khi nạp dữ liệu lớn.

## 5. COPY TO: xuất CSV và kiểm tra giới hạn của bản xuất

### 5.1. Xuất toàn bảng trong lab

~~~sql
COPY cqlsh_copy_lab.readings_by_device_day
  (device_id, reading_day, read_at, reading_id, metric, value)
TO 'readings-export.csv'
WITH HEADER = TRUE;
~~~

File `readings-export.csv` được ghi ở **máy/môi trường chạy cqlsh**. Số dòng dữ liệu trong lab kỳ vọng là 4 (không tính header), nếu trước đó không có dữ liệu cũ trong cùng bảng. Cách biểu diễn timestamp, số và quote có thể khác file nhập ban đầu; nên so sánh **giá trị đã parse**, không yêu cầu so khớp chuỗi byte-for-byte.

### 5.2. Xuất một phần cột

~~~sql
COPY cqlsh_copy_lab.readings_by_device_day
  (device_id, reading_day, read_at, metric, value)
TO 'readings-summary.csv'
WITH HEADER = TRUE;
~~~

Khi xuất để nhập vào bảng khác, kiểm tra kỹ **primary key bên đích**. Ví dụ file `readings-summary.csv` không có `reading_id`: nó **không đủ** để nhập trở lại đúng bảng gốc vì thiếu thành phần primary key. “CSV hợp lệ” chưa đồng nghĩa “dữ liệu đủ thông tin để khôi phục”.

### 5.3. COPY TO không phải SELECT có WHERE

`COPY ... TO` được thiết kế để xuất dữ liệu của bảng và chọn **các cột**, không phải thay thế một câu `SELECT ... WHERE ...` tùy ý. Nếu chỉ muốn xem một partition nhỏ, hãy dùng `SELECT` theo partition key hoặc ứng dụng xuất kết quả có kiểm soát; không mặc định lệnh `COPY TO` có thể gắn `WHERE` rồi lọc theo cách của CQL.

**Không dựa vào thứ tự các dòng CSV xuất ra** làm thứ tự toàn cục của cluster. Clustering order chỉ quy định thứ tự bên trong partition; Cassandra không hứa các partition sẽ được quét theo một thứ tự có ý nghĩa nghiệp vụ.

### 5.4. COPY TO khác sao lưu nhất quán

Một file CSV tạo từ `COPY TO` không bảo toàn đầy đủ:

- Cấu trúc keyspace/bảng, replication strategy, các index, role và `GRANT`.
- Metadata cấp cell như **write timestamp**, **TTL còn lại** hoặc toàn bộ semantics tombstone/xóa dữ liệu.
- Một **thời điểm chụp toàn cục** trong khi nhiều ứng dụng đang ghi song song; các page của quá trình xuất có thể phản ánh những thời điểm khác nhau.
- Toàn bộ chi tiết định dạng/dữ liệu đặc biệt như collection/UDT/blob nếu không có quy trình mã hóa và kiểm thử tương ứng.

Vì vậy, dùng `COPY TO` cho kiểm thử hoặc xuất có mục tiêu là hợp lý, nhưng **không sử dụng một file CSV như bản thay thế trực tiếp của backup/snapshot phục hồi đầy đủ cluster**.

## 6. CSV: các lỗi dễ gây sai dữ liệu âm thầm

### 6.1. Trường chứa dấu phẩy, dấu nháy và dòng mới

CSV phải có quy tắc escape/quote thống nhất. Với dấu phẩy làm delimiter, dữ liệu như `"sensor, north"` cần được quote đúng. Ví dụ:

~~~csv
device_id,reading_day,read_at,reading_id,metric,value
"sensor,north",2026-11-21,2026-11-21T01:00:00Z,55555555-5555-4555-8555-555555555555,temperature,23.4
~~~

Không tự dùng `String.split(",")` để parse CSV thực tế nếu dữ liệu có dấu phẩy, quote hoặc newline nằm trong field. Dùng parser CSV hiểu đúng tiêu chuẩn và kiểm thử encoding/escape.

Trong cqlsh có các tùy chọn `COPY` cho delimiter, quote, escape, header và một số thông số khác. Ví dụ khi dùng dấu chấm phẩy:

~~~sql
-- Chỉ dùng khi file nhập thực sự phân tách bằng dấu ';'.
COPY cqlsh_copy_lab.readings_by_device_day
  (device_id, reading_day, read_at, reading_id, metric, value)
FROM 'readings-semicolon.csv'
WITH HEADER = TRUE AND DELIMITER = ';';
~~~

File `readings-semicolon.csv` ở ví dụ này phải được **tạo với delimiter `;`** trước đó. Không chạy lệnh trên file `readings.csv` ban đầu dùng dấu phẩy.

### 6.2. Giá trị rỗng, NULL và kiểu dữ liệu

Những trường hợp phải thiết kế rõ:

- **Ô trống**: cần quyết định nó là chuỗi rỗng hay `null`; hành vi phụ thuộc tùy chọn `NULL` và cột/phiên bản cqlsh. Không mặc định mọi ô trống đều có nghĩa như nhau.
- **Partition key/clustering columns không có giá trị**: row không thể được xác định bằng primary key hợp lệ.
- **Timestamp không có timezone**: dễ bị diễn giải không nhất quán giữa môi trường. Ưu tiên thời điểm có offset/Z nếu phù hợp.
- **Số thập phân**: định dạng `25.1` khác `25,1` khi delimiter đang là dấu phẩy.
- **UUID**: `reading_id` sai định dạng hoặc thiếu có thể khiến row không được ghi.
- **Text/UTF-8**: dữ liệu tiếng Việt, ký tự xuống dòng, BOM hoặc encoding khác UTF-8 có thể làm parser xử lý không như mong muốn.
- **Collection/UDT/blob**: cần xác định format biểu diễn đúng của phiên bản CQL/cqlsh; không coi mọi giá trị phức tạp là một chuỗi đơn giản.

Trước khi nhập lớn, thử một file nhỏ có các tình huống **null, quote, Unicode, timestamp, số âm và duplicate key** để biết cách cqlsh thực tế diễn giải.

### 6.3. Kiểm tra mapping và lỗi nhập

| Triệu chứng | Nghi ngờ đầu tiên | Hướng khắc phục |
| --- | --- | --- |
| `File not found` / `No such file` | Đường dẫn tồn tại trên host nhưng cqlsh chạy trong container, hoặc working directory khác | Kiểm tra file tại đúng môi trường cqlsh; dùng đường dẫn tuyệt đối hợp lệ. |
| Không có quyền đọc/ghi file | Quyền hệ điều hành hoặc mount read-only | Kiểm tra quyền user chạy cqlsh, mount, dung lượng đĩa. |
| Lỗi `InvalidRequest`, kiểu dữ liệu không hợp lệ | Cột/kiểu trong CSV không khớp bảng | `DESCRIBE TABLE`, sửa parse/format từng cột. |
| Header bị nhập như một dòng dữ liệu | Thiếu hoặc sai `HEADER = TRUE` | Kiểm tra dòng đầu, chỉ định header phù hợp. |
| Giá trị rơi sang cột khác | Sai thứ tự column list, delimiter/quote sai | Đối chiếu header, thứ tự cột, trích một vài dòng test. |
| Nhiều dòng lỗi nhưng một số dòng đã vào DB | Import không nguyên tử ở cấp file | Xem thông báo/lịch sử lỗi, xác định các row đã ghi và chính sách chạy lại. |
| `Unauthorized` | Tài khoản không có quyền `MODIFY`/`SELECT` phù hợp | Kiểm tra role/GRANT, không tắt bảo mật. |
| `Unavailable` hoặc timeout | Không đủ replica/CL, node chậm, tải hoặc mạng | Xem replication factor, CL, topology và metrics; giảm tốc độ nhập có kiểm soát. |

Không nên phán đoán thành công chỉ từ exit code hoặc dòng “processed” tổng quát. Cần đối chiếu **số record nguồn, số record lỗi, sample chính xác theo primary key và tính hợp lệ của dữ liệu**.

## 7. Giới hạn quy mô: tại sao COPY không phải bulk loader đa dụng?

`COPY` hữu ích vì dễ bắt đầu, nhưng có những giới hạn khi số dòng tăng cao.

### 7.1. Máy chạy cqlsh trở thành một điểm chịu tải

Khi nhập, dữ liệu CSV được đọc và parse ở phía client cqlsh, rồi gửi qua mạng. Khi xuất, kết quả đọc đi qua cqlsh trước khi được ghi ra file. Vì vậy CPU, RAM, disk throughput, network, tiến trình Python/cqlsh và timeout phía client có thể là **nút cổ chai**.

Những vấn đề có thể xuất hiện:

- Nạp hoặc xuất nhiều triệu dòng có thể mất rất lâu và khó quản lý checkpoint/khôi phục đúng từ dòng lỗi.
- Điều chỉnh song song quá cao có thể gây **backpressure, timeout, dropped messages hoặc compaction backlog** ở Cassandra.
- Kích thước row/partition lớn làm các thao tác đọc/ghi nặng, kể cả khi “số dòng mỗi file” không lớn.
- Cluster nhiều node không tự biến một tiến trình cqlsh duy nhất thành hệ xử lý dữ liệu phân tán quy mô lớn.
- `COPY TO` trên bảng lớn có thể tiêu thụ I/O và băng thông đáng kể vì cần đi qua nhiều partition.

**Không có một ngưỡng “COPY luôn nhanh nếu dưới N GB” áp dụng mọi môi trường.** Hiệu suất phụ thuộc phần cứng, phiên bản Cassandra/cqlsh, network, partition distribution, kích thước row, RF, CL và tác vụ nền. Đánh giá bằng **thử tải đại diện**, không chỉ ước lượng số dòng.

### 7.2. Tối ưu bằng tăng concurrency có giới hạn

Một số bản cqlsh có tùy chọn cấu hình song song, batch, timeout và kích thước page cho `COPY`. Tên và ý nghĩa cụ thể khác theo phiên bản; xác minh trong tài liệu `cqlsh/COPY` hiện hành trước khi đặt thông số.

Nguyên tắc:

1. Bắt đầu từ **dataset nhỏ** có key phân bổ đều, đo throughput/latency/lỗi.
2. Tăng concurrency **từng bước**, quan sát CPU, GC, disk I/O, compaction, memtable/flush, queue và network của từng node.
3. Tránh gửi batch chứa nhiều partition với kỳ vọng “một batch = một transaction SQL” hoặc luôn nhanh hơn nhiều ghi đơn lẻ.
4. Khi đã gây timeout hoặc backlog, **giảm tốc độ nhập**, không mở rộng số worker vô hạn.
5. Không hạ consistency production chỉ để làm bài test nhập nhanh; cần thống nhất yêu cầu dữ liệu và khả năng chịu lỗi.

Nếu thao tác có thể phải chạy lại, hãy lưu **manifest file, checksum, số dòng hợp lệ, danh sách key và checkpoint bên ngoài**. `COPY` không tự cung cấp một hệ thống orchestration có checkpoint bảo đảm end-to-end.

### 7.3. Các giới hạn về tính nhất quán và thời gian

- **Không có snapshot transaction toàn file:** bảng có thể tiếp tục nhận ghi/xóa khi `COPY TO` đang chạy. Export không tự cam kết tất cả dòng đều phản ánh cùng một thời điểm.
- **Không nguyên tử khi import:** mất kết nối giữa file làm một phần row đã được ghi.
- **Không bảo toàn TTL/writetime như bản sao vật lý:** nhập lại CSV có thể tạo timestamp/TTL khác so với dữ liệu gốc.
- **Không tự khắc phục schema sai:** bảng được thiết kế theo truy vấn không phù hợp có thể xuất hiện hotspot dù CSV được parse đúng.
- **Không bảo đảm đúng nghiệp vụ khi retry:** primary key và idempotency phải được thiết kế, đặc biệt với giá trị tổng hợp/counter.

Đó là lý do cần chọn công cụ phù hợp với **nguồn dữ liệu, mục tiêu migration, consistency, kiểm tra và phục hồi**.

## 8. Công cụ nạp dữ liệu thay thế: chọn theo dạng nguồn và mục đích

| Công cụ/phương án | Phù hợp khi | Đầu vào điển hình | Điều cần lưu ý |
| --- | --- | --- | --- |
| **cqlsh COPY FROM/TO** | Lab, kiểm tra và CSV nhỏ/vừa | CSV | Dễ dùng nhưng quy mô/kiểm soát checkpoint hạn chế. |
| **DataStax Bulk Loader (DSBulk)** | Nạp/xuất dữ liệu lớn hơn, có nhu cầu mapping/tuning và xử lý lỗi tốt hơn | CSV, JSON và một số nguồn/sink được hỗ trợ | Kiểm tra **phiên bản, license, tính tương thích** với Apache Cassandra/cluster đang dùng; không giả định mọi bản hỗ trợ mọi schema/kiểu dữ liệu. |
| **Spark Cassandra Connector** | Đã có pipeline Spark và muốn đọc/ghi dataset phân tán | DataFrame/Dataset, nguồn ETL Spark | Cần quản lý partitioning, write throughput, version Spark/Scala/Cassandra và tài nguyên cluster. |
| **SSTableLoader / streaming SSTable** | Chuyển dữ liệu đã ở định dạng **SSTable Cassandra** | SSTable được tạo đúng định dạng/phiên bản | **Không nhận CSV trực tiếp**; cần schema, topology, phiên bản tương thích và runbook streaming. |
| **Java Driver + prepared statements** | Tích hợp ứng dụng, cần validation, biến đổi và logic idempotency riêng | Record từ file/DB/API sau parse | Phải quản lý giới hạn concurrency, retry, paging, backpressure và batch semantics. |
| **Kafka Connect/NiFi hoặc pipeline streaming** | Nạp dữ liệu **liên tục** với checkpoint/monitoring | Topic sự kiện, luồng CDC, source systems | Semantics at-least-once/exactly-once phụ thuộc connector và thiết kế key, không mặc nhiên do Cassandra bảo đảm. |

### 8.1. DSBulk: hướng nâng cấp phổ biến từ COPY

DSBulk là công cụ bulk loading/unloading có khả năng xử lý source/sink và mapping, thường được dùng cho công việc lớn hơn cqlsh `COPY`. Khi chọn DSBulk, cần đọc tài liệu **đúng bản DSBulk** và tương thích server/driver của tổ chức.

Ví dụ **mang tính cấu trúc** (không phải lệnh có thể copy chạy nếu chưa thiết lập công cụ, file và cấu hình cluster):

~~~bash
# Kiểm tra DSBulk đã được cài và phiên bản/cú pháp thực tế.
dsbulk --version
dsbulk help
~~~

Một công việc nạp DSBulk thực tế còn cần **contact points/native port**, local datacenter, credentials/TLS, keyspace/table, đường dẫn dữ liệu, mapping cột, chế độ xử lý lỗi, timeout và mức concurrency phù hợp. Không đặt mật khẩu thật vào command history. Trước khi nạp toàn bộ dataset, chạy dry-run/nhập thử một phân đoạn nhỏ theo tính năng bản công cụ đang dùng.

**Lưu ý:** DSBulk thường có cú pháp `dsbulk load`/`dsbulk unload`, nhưng các option mapping, connector, auth và tên tham số có thể thay đổi theo phiên bản. Đối chiếu hướng dẫn chính thức thay vì sao chép lệnh thiếu ngữ cảnh từ một cluster khác.

### 8.2. Spark Cassandra Connector: nạp phân tán có kiểm soát

Nếu dữ liệu đã ở trong Spark, connector có thể chuyển DataFrame thành các thao tác ghi Cassandra. Ưu điểm là phân tán việc đọc/biến đổi; rủi ro là **nhiều executor có thể cùng dồn ghi vào một vài partition nóng** nếu data modeling không phù hợp.

Cần:

- Tương thích phiên bản Spark, Scala, Java, connector và Cassandra.
- Thiết kế partition key và tránh một khóa nhận phần lớn record.
- Kiểm soát số task, connection, throughput, retry và lỗi từng partition.
- Đo latency/compaction backlog trước và sau khi tăng parallelism.

Không kết luận “Spark là phân tán nên nạp Cassandra nhanh vô hạn”; Cassandra vẫn chịu giới hạn replica, network, disk và compaction.

### 8.3. SSTableLoader: khác hoàn toàn nhập CSV

**SSTable** là định dạng lưu trữ trên đĩa của Cassandra. Các công cụ như `sstableloader` có thể stream dữ liệu SSTable vào cluster dựa trên topology; đây là phương án khác với parse CSV qua native CQL.

Nếu dữ liệu nguồn là CSV, không thể đổi đuôi `.csv` thành `.db` hoặc chạy `sstableloader` trực tiếp lên CSV. Muốn dùng luồng SSTable phải có quy trình **tạo SSTable hợp lệ** cho schema/phiên bản đích và kiểm tra tương thích. Snapshot/SSTable restoration là một quy trình vận hành riêng, có thể liên quan schema, token range và repair sau di chuyển.

### 8.4. Java Driver: dùng khi cần kiểm tra và biến đổi từng record

Java Driver phù hợp nếu dữ liệu đầu vào phải được xác thực nghiệp vụ, chuẩn hóa timestamp, map kiểu dữ liệu, tính khóa phân vùng hay áp dụng idempotency policy.

Ví dụ **một thao tác ghi có tham số**, không phải chương trình nhập hàng triệu CSV:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class CassandraPreparedInsertDemo {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1") // Thay bằng DC thực.
                .build()) {

            PreparedStatement prepared = session.prepare(
                "INSERT INTO cqlsh_copy_lab.readings_by_device_day " +
                "(device_id, reading_day, read_at, reading_id, metric, value) " +
                "VALUES (?, ?, ?, ?, ?, ?)");

            BoundStatement statement = prepared.bind(
                    "sensor-03",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T01:00:00Z"),
                    UUID.fromString("55555555-5555-4555-8555-555555555555"),
                    "temperature",
                    22.5)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE);

            session.execute(statement);
        }
    }
}
~~~

Trong ứng dụng thật:

- Đọc CSV bằng **parser hiểu quote/escape**, kiểm tra schema và chuyển đổi sang kiểu Java trước khi `bind`.
- Tái sử dụng `CqlSession` và `PreparedStatement`; không mở session mới cho mỗi dòng.
- Dùng **async/bounded concurrency** hoặc cơ chế backpressure có số request đang chờ bị giới hạn; chỉ tăng concurrency khi metrics cho thấy cluster còn dư năng lực.
- Ghi lại lỗi theo primary key/checkpoint, thiết kế retry cho thao tác **idempotent**. Timeout ghi có thể đã ghi một phần; không retry mù.
- Dùng credentials, TLS, local datacenter, CL và timeout theo topology thực tế. `datacenter1` trong ví dụ chỉ là tên minh họa.

### 8.5. Chọn nhanh theo mục đích

~~~mermaid
flowchart TD
    A["Cần nhập hoặc xuất dữ liệu Cassandra"] --> B{"Nguồn ở định dạng SSTable?"}
    B -->|"Có"| C["Đánh giá SSTableLoader / restore theo phiên bản và topology"]
    B -->|"Không"| D{"Dữ liệu liên tục hay một lần?"}
    D -->|"Liên tục"| E["Kafka Connect / NiFi / pipeline có checkpoint"]
    D -->|"Một lần"| F{"Nguồn đã nằm trong Spark?"}
    F -->|"Có"| G["Spark Cassandra Connector"]
    F -->|"Không"| H{"CSV nhỏ/vừa, thao tác thủ công?"}
    H -->|"Có"| I["cqlsh COPY + kiểm tra dữ liệu"]
    H -->|"Không"| J["DSBulk hoặc Java Driver pipeline có giới hạn tải"]
~~~

Đây là gợi ý **phân loại ban đầu**, không phải lựa chọn bắt buộc. Cần xem schema, lượng dữ liệu, quy mô cluster, tính tương thích, nhu cầu hồi phục và năng lực vận hành.

## 9. Runbook nạp dữ liệu có kiểm soát

### 9.1. Trước khi nạp

1. **Xác nhận mục tiêu**: cluster, datacenter, keyspace/table, phiên bản Cassandra và nơi tiến trình nhập sẽ chạy.
2. **Kiểm tra schema**: partition key, clustering columns, kiểu dữ liệu, index và câu truy vấn nghiệp vụ.
3. **Kiểm tra khả năng chịu tải**: RF, CL, node Up/Down, dung lượng disk, CPU/GC, compaction backlog và băng thông mạng.
4. **Làm sạch dữ liệu đầu vào**: normalize timezone, UUID, null/empty, Unicode, duplicate business keys, file encoding và quote.
5. **Bảo vệ truy cập**: credentials/TLS, quyền `MODIFY` trên bảng đích, bảo vệ CSV có dữ liệu nhạy cảm.
6. **Đặt tiêu chí đối soát**: số dòng đầu vào, số key kỳ vọng, sample theo từng partition, checksum/manifest, log lỗi và kế hoạch nạp lại.
7. **Chạy thử nhỏ**: kiểm tra vài partition khác nhau và một số trường hợp có giá trị đặc biệt, không chạy ngay toàn bộ file lớn.

### 9.2. Trong khi nạp

Theo dõi ở cả client và cluster:

| Phía client/công cụ | Phía Cassandra |
| --- | --- |
| Tốc độ record/giây, số record thành công/lỗi | Read/write latency, queue, dropped messages |
| CPU/RAM và khả năng đọc file của cqlsh/loader | CPU, GC, memtable/flush, disk I/O |
| Connect timeout, retry và file lỗi | Replica availability, compaction backlog |
| Connection pool, in-flight requests | Network throughput, disk space, streaming/repair đang chạy |

Nếu lỗi timeout tăng cùng CPU/disk/compaction backlog, hãy **giảm tải và điều tra**, không tự động tăng timeout và concurrency vô hạn. Nếu lỗi là `Unauthorized` hoặc kiểu dữ liệu sai, dừng để sửa nguyên nhân; retry cùng dòng sẽ không tự chữa được.

### 9.3. Sau khi nạp

1. Đối chiếu số dòng đã parse, số dòng ghi lỗi và số dòng thực tế mong đợi theo các partition mẫu.
2. Chạy các **truy vấn nghiệp vụ đúng partition key** và kiểm tra kiểu dữ liệu/định dạng thời gian.
3. Nếu có yêu cầu tính nhất quán, kiểm tra kết quả theo CL phù hợp và tình trạng replica; đừng đánh đồng “tool báo hoàn tất” với dữ liệu đã được đối soát trên mọi replica.
4. Lưu báo cáo/manifest, nguồn đã dùng, tool version, thông số cấu hình, thời gian nạp và lỗi để có thể truy vết.
5. Với thay đổi topology/RF hoặc backup/restore ở mức SSTable, thực hiện quy trình vận hành/repair riêng khi tài liệu phiên bản yêu cầu; **không chạy repair chỉ vì COPY vừa kết thúc**.

## 10. Ví dụ tình huống: từ CSV lab tới pipeline hàng chục triệu record

**Bối cảnh:** hệ thống ghi nhiệt độ/độ ẩm của vài nghìn thiết bị mỗi phút; dữ liệu lịch sử cần nhập vào Cassandra trước khi dịch vụ Java bắt đầu đọc.

### 10.1. Vì sao không dùng một partition cho từng thiết bị vĩnh viễn?

Nếu bảng có `PRIMARY KEY (device_id, read_at)` và một thiết bị có hàng triệu sự kiện, partition có thể tăng rất lớn. Thiết kế như `PRIMARY KEY ((device_id, reading_day), read_at, reading_id)` là một cách chia theo ngày. Với tốc độ cực cao, bucket có thể phải ngắn hơn; với tốc độ thấp, bucket dài hơn có thể hợp lý.

Partition key ảnh hưởng trực tiếp tới **phân bố token và tải replica**. Một file CSV được xử lý nhanh vẫn có thể làm cluster nghẽn nếu phần lớn record rơi vào cùng một vài partition nóng.

### 10.2. Chọn công cụ theo giai đoạn

| Giai đoạn | Dữ liệu | Phương án gợi ý |
| --- | --- | --- |
| Kiểm thử schema | 4–100 record | `cqlsh COPY FROM` và `SELECT` theo partition. |
| Chạy thử đại diện | Tập nhỏ chứa đầy đủ kiểu record | DSBulk hoặc pipeline Java, kèm validation/metrics. |
| Nhập lịch sử lớn | Hàng triệu đến hàng chục triệu record | DSBulk/Spark hoặc pipeline Java phân mảnh/bounded concurrency, theo năng lực thực tế. |
| Nạp dữ liệu phát sinh tiếp theo | Dữ liệu liên tục từ service/event bus | Java Driver hoặc streaming connector với checkpoint và idempotency. |
| Chuyển dữ liệu vật lý cùng định dạng Cassandra | SSTable/snapshot phù hợp | Runbook SSTable loader/restore, không phải `COPY FROM` CSV. |

Các mốc ở bảng mang tính **phân loại công việc**, không phải benchmark hay ngưỡng tuyệt đối của mỗi công cụ. Việc quyết định phải dựa trên thử tải và kết quả quan sát cluster.

### 10.3. Một số nguyên tắc chống lỗi nghiệp vụ

- **Không dùng số thứ tự sinh ngẫu nhiên mỗi lần retry** nếu cần nạp lại cùng record; hãy chọn primary key ổn định từ nguồn dữ liệu.
- **Không dùng Cassandra `BATCH` lớn xuyên nhiều partition chỉ để tăng tốc**: batch trong Cassandra có semantics khác transaction SQL nhiều dòng và có thể gây thêm tải.
- **Không coi bản xuất `COPY TO` khi hệ thống đang ghi là một snapshot toàn cục**; muốn backup/restore nhất quán cần quy trình riêng.
- **Không trộn dữ liệu staging/production**: ghi tên bảng đủ định danh và kiểm tra endpoint trước lệnh `COPY`.
- **Không giảm consistency hay tắt TLS/auth khi import chậm** nếu chưa đánh giá yêu cầu bảo mật/nhất quán.

## 11. Bài tập thực hành và tự đánh giá

1. Tạo bảng `cqlsh_copy_lab.readings_by_device_day` theo mục 3, chép nội dung CSV mẫu vào `readings.csv` ở đúng môi trường chạy cqlsh.
2. Chạy `COPY ... FROM` với `HEADER = TRUE`. Kiểm tra từng partition đã biết bằng `SELECT` đầy đủ partition key.
3. Chạy `COPY ... TO` ra `readings-export.csv`. So sánh giá trị thực tế thay vì thứ tự row hoặc format chuỗi timestamp.
4. Cố ý đảo thứ tự `metric` và `value` trong danh sách cột của lệnh `COPY FROM` trên một file lab khác. Dự đoán kiểu lỗi hoặc dữ liệu sai và nêu bước kiểm tra để phát hiện.
5. Tạo một dòng CSV có dấu phẩy nằm trong text được quote đúng. Giải thích vì sao parser CSV phải hiểu dấu quote chứ không dùng `split(",")`.
6. Giả sử `COPY FROM` lỗi sau khi ghi thành công 60% file. Đề xuất cách đối soát và tái chạy dựa trên **primary key cố định**, không yêu cầu rollback cả file.
7. Giải thích vì sao `COPY TO` không sao lưu đầy đủ schema, replication, TTL, tombstone và trạng thái dữ liệu tại một thời điểm.
8. Với dữ liệu 30 triệu record từ CSV và cluster nhiều node, so sánh `COPY`, DSBulk, Spark Connector và Java Driver theo tải, kiểm soát lỗi và vận hành.
9. Cho nguồn là bộ SSTable có sẵn, giải thích vì sao `sstableloader` phù hợp hơn `COPY FROM` CSV và các điều kiện tương thích cần kiểm tra.
10. Một tiến trình Java muốn nạp hàng trăm nghìn record có logic kiểm tra dữ liệu. Nêu cách dùng prepared statements, bounded concurrency, metrics và chính sách idempotency.
11. Sau import, `SELECT COUNT(*)` toàn bảng mất rất lâu. Đề xuất cách kiểm tra chất lượng dựa trên sample partition, manifest và số record có kiểm soát.

**Tiêu chí hoàn thành:** bạn có thể nhập/xuất CSV với `COPY`, giải thích rõ nơi file được đọc/ghi, xác nhận mapping kiểu dữ liệu và partition key, nêu giới hạn không nguyên tử/không snapshot, và lựa chọn đúng một phương án thay thế cho dữ liệu lớn hoặc nạp liên tục.

## Tài liệu tham khảo

- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): cú pháp `COPY FROM`, `COPY TO`, các tùy chọn CSV và yêu cầu môi trường chạy cqlsh.
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): kiểu dữ liệu, primary key, `INSERT`/`SELECT` và mô hình bảng theo truy vấn.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html): phân vùng dữ liệu, truy vấn và thiết kế partition key.
- [DataStax Bulk Loader (DSBulk)](https://docs.datastax.com/en/dsbulk/): bulk import/export, mapping và cấu hình theo bản công cụ.
- [Spark Cassandra Connector](https://github.com/datastax/spark-cassandra-connector): tài liệu triển khai và tương thích connector.
- [Apache Cassandra — SSTable tools](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/index.html): các công cụ liên quan đến SSTable và streaming/migration.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): prepared statements, consistency, async API và retry.
