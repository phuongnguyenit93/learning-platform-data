# Debezium hoặc công cụ CDC khác: snapshot, offset và schema change

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích Change Data Capture (CDC) và vai trò của MySQL binary log trong việc chuyển thay đổi dữ liệu sang hệ thống khác.
- Phân biệt snapshot ban đầu với luồng change event liên tục.
- Mô tả cách Debezium ghi nhận binlog position/GTID và lưu source offset để tiếp tục sau restart.
- Nhận diện rủi ro duplicate, mất binlog, offset reset và thời gian downtime kéo dài.
- Giải thích schema history và ảnh hưởng của DDL đến việc giải mã row event.
- Thiết kế consumer chịu được schema evolution, thứ tự sự kiện và xử lý lặp.
- So sánh Debezium với một số lựa chọn CDC khác và xây dựng quy trình vận hành, giám sát, phục hồi.

## 1. CDC là gì và giải quyết bài toán nào?

Change Data Capture (CDC) là cách ghi nhận các thay đổi xảy ra trong database rồi chuyển chúng đến hệ thống khác. Thay vì định kỳ chạy truy vấn để quét toàn bộ bảng và tìm hàng mới, CDC đọc luồng thay đổi ở nguồn để phát hiện INSERT, UPDATE và DELETE.

Trong kiến trúc MySQL, binary log (binlog) là nguồn dữ liệu quan trọng cho CDC. Khi MySQL ghi transaction vào binlog, một connector có thể đọc các sự kiện này, giải mã thay đổi hàng và phát chúng đến Kafka, message broker, data warehouse, search index hoặc dịch vụ khác.

Các trường hợp sử dụng thường gặp:

- Đồng bộ dữ liệu từ MySQL sang data lake hoặc data warehouse.
- Cập nhật Elasticsearch/OpenSearch hoặc cache tìm kiếm.
- Phát sự kiện thay đổi cho microservice khác.
- Dựng read model hoặc materialized view ở hệ thống downstream.
- Tạo pipeline phân tích gần thời gian thực.
- Di chuyển dữ liệu giữa các hệ quản trị mà không phải quét bảng liên tục.

CDC không phải bản sao lưu và không thay thế replication của MySQL. Nó là luồng sự kiện thay đổi dành cho tích hợp dữ liệu. Downstream cần tự quản lý schema, retry, duplicate, thứ tự và khả năng xử lý khi mất kết nối.

## 2. Kiến trúc tổng thể với Debezium

Debezium là nền tảng CDC mã nguồn mở. Trong triển khai phổ biến, Debezium chạy như một Kafka Connect source connector. Connector kết nối MySQL, chụp snapshot ban đầu nếu được cấu hình, sau đó đọc binlog và phát record vào Kafka.

~~~mermaid
flowchart LR
    APP[Ứng dụng ghi dữ liệu] --> MYSQL[(MySQL)]
    MYSQL --> BINLOG[Binary log]
    SNAP[Snapshot reader] --> MYSQL
    BINLOG --> DBZ[Debezium MySQL Connector]
    SNAP --> DBZ
    DBZ --> KC[Kafka Connect]
    KC --> DATA[Kafka data topics]
    KC --> HIST[Schema history topic]
    KC --> OFF[Connect offset storage]
    DATA --> CONSUMER[Consumer / Stream processor]
    CONSUMER --> DW[Warehouse / Search / Service]
~~~

Các thành phần có vai trò riêng:

| Thành phần | Vai trò |
|---|---|
| MySQL source | Database nguồn, tạo binlog từ transaction |
| Snapshot | Đọc trạng thái hiện tại của bảng tại một thời điểm nhất quán |
| Debezium connector | Giải mã binlog, tạo change event và quản lý source position |
| Kafka Connect | Quản lý lifecycle connector/task, lưu source offset và chuyển record |
| Data topics | Chứa event theo database/table hoặc quy tắc đặt tên |
| Schema history | Lưu lịch sử DDL cần để hiểu cấu trúc hàng tại từng thời điểm |
| Offset storage | Lưu tiến độ đọc nguồn để connector có thể tiếp tục |
| Consumer | Áp dụng hoặc biến đổi change event ở downstream |

Data topic, schema history topic và offset storage không phải cùng một loại dữ liệu. Không dùng data topic thay cho schema history hoặc tự chỉnh offset nội bộ khi chưa có kế hoạch phục hồi.

## 3. Debezium đọc MySQL như thế nào?

MySQL ghi các thay đổi đã commit vào binary log. Với row-based logging, binlog chứa thông tin thay đổi ở mức hàng thay vì chỉ lưu câu SQL ban đầu. Debezium đọc các sự kiện binlog, dùng metadata schema để giải mã kiểu dữ liệu và tạo record có key/value.

Luồng đơn giản:

1. Ứng dụng thực hiện INSERT, UPDATE hoặc DELETE.
2. MySQL thực thi transaction và ghi các thay đổi vào binlog khi transaction commit.
3. Debezium đọc binlog từ vị trí đã lưu hoặc vị trí khởi tạo.
4. Connector giải mã row event theo schema tương ứng.
5. Connector tạo change event và gửi vào Kafka Connect.
6. Kafka Connect chuyển record tới Kafka topic.
7. Offset được lưu theo cơ chế của Kafka Connect để lần chạy sau biết vị trí nguồn đã xử lý.

Debezium không truy vấn lại toàn bộ bảng cho mỗi thay đổi. Khi streaming, nó theo dõi binlog liên tục và xử lý các row event theo thứ tự nguồn.

### 3.1. Yêu cầu cấu hình MySQL cơ bản

Một cấu hình MySQL thường cần các điều kiện sau:

- Binary logging được bật.
- binlog_format là ROW.
- binlog_row_image nên đặt FULL để connector có đủ thông tin hàng trước/sau cho nhiều loại thao tác và schema; cấu hình này làm binlog lớn hơn so với MINIMAL.
- server_id duy nhất trong topology replication.
- Binlog được giữ đủ lâu để connector có thể phục hồi sau thời gian gián đoạn.
- User CDC có quyền đọc dữ liệu khi snapshot và quyền replication cần thiết để đọc binlog.
- Nếu đọc từ replica, cấu hình replication và log_replica_updates phải phù hợp với kiến trúc.

Ví dụ các thiết lập nền trong file cấu hình:

~~~ini
[mysqld]
server_id=301
log_bin=mysql-bin
binlog_format=ROW
binlog_row_image=FULL
binlog_expire_logs_seconds=604800
~~~

Ví dụ retention 604800 giây tương đương 7 ngày, chỉ để minh họa. Thời gian thực tế phải lớn hơn thời gian downtime tối đa dự kiến cộng với thời gian điều tra, phục hồi và catch-up. Với hệ thống có cửa sổ bảo trì dài hoặc connector có thể ngừng nhiều ngày, cần retention lớn hơn.

Có thể kiểm tra biến:

~~~sql
SHOW VARIABLES
WHERE Variable_name IN (
  'log_bin',
  'binlog_format',
  'binlog_row_image',
  'binlog_expire_logs_seconds',
  'gtid_mode',
  'server_id'
);
~~~

GTID không phải điều kiện bắt buộc cho mọi cấu hình Debezium, nhưng có thể giúp theo dõi lịch sử transaction và xử lý failover nguồn thuận tiện hơn. Khi dùng GTID, cần hiểu cách connector nhận diện source và bảo đảm các server trong topology có GTID history nhất quán.

### 3.2. Quyền của tài khoản CDC

Connector cần quyền khác nhau tùy thao tác:

- Đọc schema/table và dữ liệu khi tạo snapshot.
- Đọc thông tin database và metadata cần thiết.
- Đăng ký/đọc binlog như một replication client.
- Có thể cần quyền khóa hoặc flush trong chế độ snapshot cụ thể.

Không cấp quyền quản trị toàn cục chỉ để làm connector chạy được. Tạo user CDC riêng, giới hạn database/table, host kết nối và quyền đúng theo phiên bản Debezium, MySQL và snapshot locking mode đang sử dụng. Tài liệu Debezium cho từng phiên bản liệt kê quyền chính xác; hãy đối chiếu trước khi triển khai.

Ví dụ tạo user minh họa:

~~~sql
CREATE USER 'debezium'@'10.%'
IDENTIFIED BY 'REPLACE_WITH_SECRET';

GRANT SELECT, SHOW DATABASES, REPLICATION SLAVE,
      REPLICATION CLIENT
ON *.* TO 'debezium'@'10.%';
~~~

Đây không phải danh sách quyền production dùng chung cho mọi phiên bản. Một số snapshot mode hoặc MySQL version cần thêm quyền như RELOAD hoặc LOCK TABLES; một số phiên bản MySQL mới thay đổi tên/quyền replication. Chỉ cấp phần cần thiết sau khi kiểm tra yêu cầu của connector và kiểm thử snapshot thực tế.

Không lưu password dạng rõ trong source control hoặc connector configuration không được bảo vệ. Dùng Kafka Connect ConfigProvider, secret manager hoặc cơ chế bảo mật cấu hình của nền tảng.

## 4. Snapshot ban đầu

Khi một connector bắt đầu theo chế độ snapshot ban đầu, nó cần lấy trạng thái hiện tại của các bảng được chọn. Snapshot giúp downstream có dữ liệu nền trước khi nhận các thay đổi tiếp theo.

Quy trình khái quát:

1. Connector kết nối MySQL và xác định bảng/schema nằm trong phạm vi capture.
2. Connector phối hợp việc lấy binlog position hoặc GTID với snapshot nhất quán.
3. Connector đọc dữ liệu bảng tại snapshot view và phát các record dạng snapshot.
4. Sau khi hoàn tất snapshot, connector tiếp tục streaming từ vị trí binlog đã phối hợp.

Điểm cốt lõi là không được có khoảng trống giữa trạng thái snapshot và luồng binlog. Nếu snapshot chụp dữ liệu ở thời điểm T nhưng streaming bắt đầu từ một vị trí sau T mà không có cơ chế phối hợp đúng, thay đổi phát sinh trong khoảng giữa có thể bị mất. Nếu streaming bắt đầu quá sớm hoặc snapshot không nhất quán, một số thay đổi có thể xuất hiện lặp. Debezium quản lý sự phối hợp này theo snapshot mode và phiên bản connector.

### 4.1. Snapshot nhất quán

Với InnoDB, snapshot thường dựa trên consistent read trong transaction. Cơ chế khóa được dùng để xác định schema và binlog coordinate có thể khác theo snapshot locking mode. Bảng dùng engine không hỗ trợ consistent transactional read như MyISAM không nhận được cùng mức đảm bảo snapshot; có thể cần khóa để giữ dữ liệu ổn định trong lúc đọc.

Một số khái niệm:

- **Consistent snapshot:** các hàng được đọc theo cùng một ảnh dữ liệu logic.
- **Global read lock:** khóa toàn cục ngắn có thể được dùng để đồng bộ metadata/position và bảo đảm điểm bắt đầu.
- **Table lock:** khóa bảng có thể ảnh hưởng trực tiếp đến thao tác ghi trên bảng được capture.
- **Snapshot locking mode:** điều khiển cách connector lấy khóa trong snapshot; lựa chọn cụ thể phụ thuộc phiên bản Debezium và quyền user.

Chế độ khóa tối thiểu có thể giảm thời gian chặn ghi nhưng yêu cầu điều kiện phù hợp về storage engine, DDL và quyền. Chế độ không khóa có rủi ro nếu có DDL đồng thời hoặc engine không hỗ trợ snapshot transaction. Đừng chọn chế độ chỉ dựa trên tên; đọc tài liệu phiên bản và thử với workload thực tế.

### 4.2. Snapshot event và streaming event

Debezium thường biểu diễn record snapshot với operation code là r (read). Các thay đổi binlog thường có operation code:

| Operation | Ý nghĩa |
|---|---|
| r | Hàng được phát từ snapshot |
| c | INSERT |
| u | UPDATE |
| d | DELETE |

Consumer phải hiểu rằng record r là trạng thái ban đầu được đọc từ bảng, không phải một INSERT mới do ứng dụng vừa thực hiện. Nếu consumer tăng số lượng đơn hàng hoặc gửi thông báo cho mỗi event mà không phân biệt snapshot với c, dữ liệu nền có thể bị tính như giao dịch mới.

Ví dụ event envelope rút gọn:

~~~json
{
  "before": null,
  "after": {
    "order_id": 9001,
    "status": "PAID",
    "total_amount": 125.50
  },
  "source": {
    "db": "sales",
    "table": "orders",
    "snapshot": "true"
  },
  "op": "r"
}
~~~

Envelope thực tế có thêm timestamp, transaction metadata, connector version và cấu trúc schema tùy converter. Không hard-code consumer theo một payload rút gọn nếu chưa xác định converter và phiên bản Debezium.

### 4.3. Chọn snapshot mode

Debezium MySQL có nhiều snapshot mode theo phiên bản. Các mode thường gặp có ý nghĩa khái quát:

- Snapshot ban đầu rồi streaming: phù hợp khi cần seed toàn bộ trạng thái hiện có.
- Snapshot một lần rồi dừng: dùng để xuất trạng thái hiện tại mà không tiếp tục CDC.
- Chỉ lấy schema, không lấy dữ liệu: dùng trong một số tình huống khởi tạo/khôi phục có chủ đích.
- Không snapshot: chỉ streaming từ vị trí được cấu hình hoặc offset đã có.
- Snapshot khi cần: có thể yêu cầu snapshot lại khi offset cũ không còn dùng được.
- Incremental snapshot: chụp các chunk trong lúc connector vẫn streaming.

Tên property và danh sách mode thay đổi giữa các thế hệ Debezium. Không copy giá trị snapshot.mode từ một bài hướng dẫn cũ mà chưa đối chiếu tài liệu của phiên bản đang chạy. Snapshot mode là quyết định dữ liệu nền và vị trí bắt đầu; thay đổi nó có thể tạo bản phát lại lớn hoặc làm thay đổi cách connector phục hồi.

## 5. Incremental snapshot

Snapshot ban đầu có thể kéo dài nhiều giờ với bảng lớn. Trong lúc đó, connector cần giữ binlog để không bỏ lỡ các thay đổi phát sinh. Incremental snapshot cho phép đọc bảng theo từng chunk trong khi luồng binlog vẫn tiếp tục.

Quy trình khái quát:

1. Connector nhận tín hiệu bắt đầu incremental snapshot cho một bảng.
2. Bảng được chia thành các chunk theo khóa hoặc cơ chế phân đoạn được hỗ trợ.
3. Connector đọc từng chunk và phát snapshot record.
4. Các thay đổi binlog trong thời gian snapshot vẫn được xử lý.
5. Connector phối hợp watermark/chunk state để xử lý tình huống cùng một hàng vừa xuất hiện trong snapshot vừa có thay đổi mới.
6. Khi tất cả chunk hoàn tất, snapshot được đánh dấu hoàn tất và streaming tiếp tục bình thường.

Incremental snapshot hữu ích khi cần bổ sung bảng hoặc chụp lại một tập dữ liệu mà không dừng connector lâu. Nó vẫn tạo tải đọc lên MySQL và có thể phát lại nhiều record, vì vậy downstream phải idempotent.

Tín hiệu incremental snapshot có thể được gửi qua signaling table trong MySQL hoặc signal channel mà connector hỗ trợ. Cơ chế và cấu hình cụ thể phụ thuộc phiên bản. Bảo vệ quyền ghi tín hiệu; một consumer hoặc người vận hành không được quyền tùy tiện kích hoạt snapshot toàn bảng trên production.

### 5.1. Khóa phân đoạn

Chunk thường cần khóa ổn định để chia phạm vi. Primary key đơn giản là lựa chọn tốt. Nếu bảng không có primary key hoặc unique key phù hợp, connector có thể khó xác định chunk và key của event.

Trước incremental snapshot:

- Kiểm tra primary key và unique key.
- Đánh giá phân bố dữ liệu và kích thước chunk.
- Tránh thay đổi khóa hoặc cấu trúc bảng trong lúc snapshot nếu chưa có quy trình tương thích.
- Theo dõi tải SELECT, buffer pool, I/O và replication lag.
- Đảm bảo tín hiệu snapshot không bị gửi lặp ngoài ý muốn.

### 5.2. Xử lý thay đổi đồng thời

Giả sử snapshot đang đọc chunk chứa order 9001 trong khi ứng dụng cập nhật trạng thái đơn hàng. Connector có thể nhận một row event từ binlog và một snapshot row liên quan đến cùng khóa. Watermark và cơ chế đối chiếu chunk giúp Debezium xác định bản ghi nào cần phát để giữ trạng thái cuối nhất quán.

Consumer vẫn nên dùng key và version/source position để xử lý lặp. Không giả định incremental snapshot chỉ phát mỗi hàng đúng một lần trong mọi lần retry hoặc restart.

## 6. Binlog position, GTID và source offset

Offset là tiến độ của connector tại nguồn MySQL. Với binlog file/position, vị trí thường gồm tên file binlog và byte position. Với GTID, tiến độ có thể được biểu diễn bằng tập GTID đã xử lý. Debezium có thể lưu thêm thông tin partition, server identity, snapshot state hoặc chi tiết nội bộ khác.

Ví dụ tọa độ binlog:

~~~text
mysql-bin.000127 : 845921
~~~

Điều này biểu thị connector đã xử lý đến vị trí byte tương ứng trong file binlog. Cấu trúc offset nội bộ không phải API để ứng dụng tự xây logic phụ thuộc; nó có thể thay đổi theo phiên bản connector.

### 6.1. Offset được lưu ở đâu?

Trong Kafka Connect distributed mode, source offset được lưu trong Kafka topic nội bộ do worker cấu hình, thường là offset storage topic. Trong standalone mode, offset có thể được lưu trong file. Connector sử dụng offset storage để biết vị trí nguồn cần tiếp tục sau restart.

Phân biệt:

- **Source offset:** vị trí đã đọc/được ghi nhận ở MySQL.
- **Kafka record offset:** vị trí record trong một Kafka partition.
- **Consumer offset:** vị trí mà một consumer group đã xử lý trong Kafka.

Ba loại offset này độc lập. Consumer đã commit Kafka offset không có nghĩa MySQL source offset đã tiến lên cùng thời điểm, và ngược lại.

### 6.2. Cách resume sau restart

Khi connector restart bình thường:

1. Kafka Connect tải source offset đã lưu.
2. Debezium xác định binlog position/GTID và snapshot state tương ứng.
3. Connector kiểm tra binlog cần thiết còn tồn tại.
4. Connector tiếp tục đọc từ vị trí đã ghi nhận.
5. Record có thể được phát lại nếu sự cố xảy ra quanh thời điểm record đã được gửi nhưng offset chưa được lưu bền vững.

Vì vậy, consumer nên xử lý event theo hướng idempotent. CDC pipeline thường cần thiết kế chịu duplicate thay vì giả định mỗi record chỉ xuất hiện đúng một lần xuyên suốt mọi failure mode.

### 6.3. Kafka offset không phải bằng chứng dữ liệu downstream đã hoàn tất

Connector có thể đã phát record vào Kafka nhưng consumer còn chưa xử lý. Ngược lại, consumer có thể xử lý record nhưng crash trước khi commit consumer offset, dẫn đến nhận lại record.

Nếu consumer ghi sang một database khác, cần cân nhắc transaction giữa việc cập nhật đích và commit Kafka offset. Không có transaction chung giữa MySQL source, Kafka và database downstream theo mặc định.

Một mẫu an toàn thường là:

- Dùng primary key nguồn làm message key.
- Áp dụng upsert ở đích.
- Ghi nhận source position/version nếu cần loại bỏ event cũ.
- Commit consumer offset sau khi thao tác đích thành công.
- Thiết kế thao tác đích có thể chạy lại mà không tạo side effect trùng.

## 7. Vì sao binlog retention rất quan trọng?

Offset chỉ có ích nếu binlog chứa vị trí cần tiếp tục vẫn còn trên MySQL. Nếu connector ngừng lâu hơn thời gian giữ binlog, MySQL có thể purge file cũ. Khi connector trở lại, nó không thể tiếp tục từ vị trí đã lưu.

Ví dụ:

- Connector đã xử lý đến mysql-bin.000127.
- Connector dừng trong 5 ngày.
- MySQL chỉ giữ binlog 3 ngày và đã purge file chứa offset.
- Connector restart không thể đọc tiếp từ vị trí cũ.

Lúc này cần quy trình phục hồi: khôi phục binlog từ archive nếu có, hoặc tạo snapshot/rebootstrap có kiểm soát. Không tự đặt offset sang file mới nhất vì có thể bỏ qua toàn bộ thay đổi trong khoảng bị mất.

### 7.1. Chọn retention

Retention phải tính:

- Downtime tối đa có thể chấp nhận của connector.
- Thời gian phát hiện cảnh báo và xử lý sự cố.
- Thời gian connector cần để catch up backlog.
- Tốc độ sinh binlog khi workload cao điểm.
- Dung lượng ổ đĩa dành cho binlog và tốc độ tăng dữ liệu.
- Thời gian bảo trì hoặc nâng cấp Kafka Connect.

Nếu MySQL tạo 50 GB binlog mỗi ngày và cần giữ 7 ngày, dung lượng lý thuyết cho riêng binlog đã khoảng 350 GB, chưa tính log khác và headroom. Dùng tốc độ thực tế cao điểm để tính dung lượng, không chỉ lấy trung bình thấp.

Theo dõi:

- Dung lượng binlog đang giữ.
- File binlog cũ nhất còn tồn tại.
- Offset của connector so với vị trí binlog mới nhất.
- Thời gian lag và tốc độ catch-up.
- Sự kiện purge hoặc cảnh báo hết dung lượng.

Không purge thủ công binlog mà connector đang cần. Nếu cần dọn log, xác minh offset của mọi replica và CDC consumer trước.

## 8. Schema change và schema history

Binlog row event chứa dữ liệu hàng, nhưng để giải mã đúng, connector cần biết cấu trúc bảng tại thời điểm event được tạo. Nếu schema thay đổi theo thời gian, chỉ dùng schema hiện tại có thể giải mã sai các row event cũ.

Ví dụ bảng orders ban đầu:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);
~~~

Sau đó thêm cột:

~~~sql
ALTER TABLE orders
  ADD COLUMN currency CHAR(3) NOT NULL DEFAULT 'VND';
~~~

Row event trước DDL có hai cột; event sau DDL có thêm currency. Connector cần biết schema cũ và schema mới tương ứng với vị trí binlog để diễn giải các bytes trong row event.

Debezium MySQL connector duy trì schema history nội bộ. Schema history ghi nhận các thay đổi cấu trúc theo thứ tự để connector có thể tái tạo schema cần thiết khi đọc binlog hoặc phục hồi từ offset cũ.

### 8.1. Schema history topic khác data topic

Schema history topic là trạng thái nội bộ phục vụ connector. Nó không phải topic business event dành cho consumer. Data topic chứa change event của bảng; schema history lưu các thay đổi DDL/schema cần cho quá trình giải mã.

Schema history cần giữ thứ tự đầy đủ của DDL và phải được cấu hình theo yêu cầu của Debezium, thường là topic một partition để duy trì thứ tự lịch sử. Bảo đảm topic có độ bền và retention phù hợp; không áp dụng compaction, xóa log cũ hoặc thay đổi partition count theo thói quen quản trị Kafka nếu chưa xác minh yêu cầu của phiên bản connector.

Không:

- Xóa schema history topic như một thao tác dọn Kafka thông thường.
- Đổi tên hoặc thay topic history mà không có kế hoạch phục hồi.
- Dùng schema history topic làm nguồn dữ liệu downstream.
- Giả định Schema Registry thay thế schema history nội bộ của Debezium.

Schema Registry (nếu dùng Avro, Protobuf hoặc JSON Schema) quản lý schema của record được phát ra cho consumer. Schema history nội bộ quản lý cách connector hiểu schema MySQL theo lịch sử binlog. Hai thành phần giải quyết hai bài toán khác nhau.

### 8.2. DDL và thời điểm thay đổi schema

MySQL ghi DDL vào binlog theo cơ chế statement/query event. Debezium cần xử lý DDL đúng thứ tự với row event để cập nhật schema history.

Các thay đổi cần kiểm thử:

- Thêm cột nullable hoặc cột có default.
- Xóa cột.
- Đổi tên cột.
- Đổi kiểu dữ liệu, độ dài, precision hoặc scale.
- Đổi charset/collation.
- Thêm/xóa index hoặc constraint.
- Rename table hoặc move table giữa schema.
- Drop và recreate table.

Một số DDL được MySQL thực hiện bằng implicit commit và metadata lock. Không chạy migration schema tùy tiện giữa snapshot dài nếu chưa đánh giá cách connector xử lý. Đặc biệt, đổi tên cột có thể được downstream nhìn như field cũ biến mất và field mới xuất hiện; không phải mọi converter hoặc schema registry đều hiểu đó là một rename tương thích.

### 8.3. Consumer phải chịu được schema evolution

Một consumer tốt không giả định mọi record luôn có chính xác tập field cố định. Khi schema thêm cột:

- Consumer cũ phải bỏ qua field không biết hoặc dùng schema compatibility phù hợp.
- Field mới có thể nullable hoặc có default rõ ràng.
- Consumer cần xử lý record không có field mới trong event lịch sử.

Khi xóa hoặc đổi tên cột:

- Xác định consumer nào còn đọc field cũ.
- Triển khai consumer hiểu cả schema cũ và mới trước khi DDL contract.
- Dùng expand/contract cho thay đổi phá vỡ tương thích.
- Không coi đổi tên cột là thao tác vô hại chỉ vì SQL ALTER thành công.

Schema compatibility của Avro/Protobuf/JSON Schema phụ thuộc converter và policy của Schema Registry. Kiểm tra quy tắc backward/forward/full compatibility bằng schema thực tế trước rollout.

## 9. Ví dụ cấu hình Debezium MySQL connector

Ví dụ cấu hình minh họa cho Kafka Connect distributed mode:

~~~json
{
  "name": "sales-mysql-cdc",
  "config": {
    "connector.class": "io.debezium.connector.mysql.MySqlConnector",
    "tasks.max": "1",
    "database.hostname": "mysql-source.internal",
    "database.port": "3306",
    "database.user": "debezium",
    "database.password": "INJECT_FROM_SECRET_PROVIDER",
    "topic.prefix": "sales",
    "database.include.list": "sales_app",
    "table.include.list": "sales_app.orders,sales_app.order_items",
    "snapshot.mode": "initial",
    "include.schema.changes": "true",
    "schema.history.internal.kafka.bootstrap.servers": "kafka:9092",
    "schema.history.internal.kafka.topic": "schema-history.sales"
  }
}
~~~

Đây là ví dụ cho các phiên bản Debezium hiện đại dùng topic.prefix và schema.history.internal.*. Tên thuộc tính, snapshot mode và các lựa chọn cấu hình có thể thay đổi giữa các phiên bản. Hãy dùng reference guide khớp chính xác connector version.

Giải thích:

- connector.class chọn MySQL source connector.
- database.hostname/port xác định MySQL nguồn.
- database.user/password là tài khoản CDC; password phải được inject an toàn.
- topic.prefix tạo namespace topic cho các record nguồn.
- database.include.list và table.include.list giới hạn phạm vi capture.
- snapshot.mode xác định hành vi snapshot ban đầu.
- include.schema.changes điều khiển việc phát thông tin schema change theo khả năng phiên bản.
- schema.history.internal.* cấu hình nơi lưu schema history nội bộ.

Kafka Connect worker còn cần cấu hình riêng cho bootstrap server, key/value converter, offset storage, config storage, status storage và security. Những thuộc tính worker này không thay thế connector property.

Nếu downstream cần biết ranh giới transaction, kiểm tra thuộc tính cung cấp transaction metadata của phiên bản Debezium đang dùng (thường là provide.transaction.metadata) và cấu hình consumer tương ứng. Chỉ bật khi có yêu cầu rõ ràng vì transaction metadata làm tăng số record và logic xử lý downstream.

### 9.1. Topic dữ liệu

Với topic.prefix là sales, tên topic mặc định thường theo dạng:

~~~text
sales.sales_app.orders
sales.sales_app.order_items
~~~

Tên topic có thể thay đổi nếu cấu hình topic naming strategy hoặc transform. Không hard-code tên topic khi connector được cấu hình bằng naming strategy tùy chỉnh; hãy xác nhận topic thực tế trong môi trường triển khai.

### 9.2. Key và value của record

Với bảng có primary key, Debezium thường dùng giá trị khóa chính làm message key. Điều này giúp các event của cùng một hàng được gửi về cùng Kafka partition khi key partitioning chuẩn được dùng.

Ví dụ event update rút gọn:

~~~json
{
  "before": {
    "order_id": 9001,
    "status": "PENDING"
  },
  "after": {
    "order_id": 9001,
    "status": "PAID"
  },
  "op": "u"
}
~~~

Delete event thường có operation d và before chứa dữ liệu trước khi xóa; sau đó Kafka Connect/Debezium có thể phát tombstone record với key tương ứng và value null tùy cấu hình. Tombstone hỗ trợ compaction ở Kafka. Consumer cần hiểu khác biệt giữa delete event có envelope và tombstone.

Nếu bảng không có primary key hoặc unique key phù hợp, message key có thể không ổn định hoặc null. Điều này ảnh hưởng khả năng partition theo hàng, upsert, delete và compact. Thiết kế CDC nên ưu tiên bảng có khóa duy nhất ổn định.

## 10. Đảm bảo thứ tự và xử lý duplicate

Binlog của MySQL có thứ tự transaction. Debezium phát event theo thứ tự nguồn trong phạm vi connector, nhưng thứ tự consumer quan sát còn phụ thuộc Kafka partition và cách xử lý song song.

Các điểm cần nhớ:

- Event cùng key thường được giữ cùng partition nếu dùng partitioner theo key.
- Thứ tự giữa hai key khác nhau không được bảo đảm toàn cục khi có nhiều partition.
- Consumer xử lý song song có thể hoàn tất event sau trước event trước nếu không giữ thứ tự trong partition.
- Snapshot event và streaming event có thể được xử lý ở thời điểm khác nhau; không suy ra thứ tự nghiệp vụ chỉ từ timestamp.
- Retry và restart có thể phát lại record.

### 10.1. Idempotent consumer

Consumer nên áp dụng upsert theo primary key nguồn thay vì INSERT mù quáng. Với event update, cập nhật trạng thái đích theo key. Với delete, xóa hoặc đánh dấu bản ghi đã xóa.

Nếu downstream cần chống event cũ ghi đè event mới, lưu thêm source position, GTID hoặc transaction metadata phù hợp và chỉ áp dụng event mới hơn theo quy tắc đã định nghĩa. Không dùng ts_ms đơn lẻ làm thứ tự tuyệt đối vì đồng hồ, độ chính xác timestamp và transaction có thể làm thứ tự không rõ.

Ví dụ bảng đích lưu source version:

~~~sql
CREATE TABLE order_projection (
    order_id BIGINT NOT NULL PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    source_version BIGINT NOT NULL
) ENGINE=InnoDB;
~~~

Trường source_version ở đây là ví dụ khái niệm. Trong hệ thống thật, phải chọn một token thứ tự có ý nghĩa và so sánh được từ envelope/source metadata. Binlog position dạng file/position không phải số nguyên đơn giản; có thể cần lưu cấu trúc position hoặc dùng transaction metadata được chuẩn hóa.

### 10.2. Xử lý delete và tombstone

Consumer cần phân biệt:

- Delete envelope: event mô tả thao tác xóa, có thể chứa before.
- Tombstone: record cùng key nhưng value null.

Nếu consumer bỏ qua tombstone nhưng xử lý delete envelope đúng, projection vẫn có thể được cập nhật. Nếu consumer dùng compacted topic để dựng trạng thái cuối, tombstone giúp Kafka xóa key khỏi log compacted theo semantics của broker.

Không coi value null luôn là dữ liệu lỗi; đó có thể là tombstone có chủ đích.

## 11. Transaction metadata và tính nhất quán

Một transaction MySQL có thể thay đổi nhiều hàng hoặc nhiều bảng. Debezium có thể phát transaction metadata nếu bật cấu hình phù hợp; record có thể chứa transaction identifier và thông tin thứ tự trong transaction tùy connector version.

Nếu downstream cần áp dụng một nhóm thay đổi như một đơn vị logic, phải đánh giá transaction metadata và cách consumer xử lý ranh giới transaction. Không giả định Kafka nhận toàn bộ event của transaction như một message duy nhất.

Các lựa chọn:

- Chấp nhận cập nhật từng hàng và thiết kế projection có thể tạm thời ở trạng thái trung gian.
- Dùng transaction metadata để gom các event liên quan trước khi áp dụng.
- Đưa dữ liệu vào staging rồi commit projection sau khi nhận marker kết thúc transaction.

Giữ transaction quá lớn ở downstream có thể tăng latency và bộ nhớ. Cân bằng tính nhất quán nghiệp vụ với khả năng xử lý streaming.

## 12. Failover MySQL và connector

Nếu source MySQL là primary trong replication topology, khi failover sang một server khác, connector cần tiếp tục đọc cùng lịch sử dữ liệu. GTID có thể hỗ trợ xác định transaction đã xử lý giữa các server, nhưng failover chỉ an toàn nếu topology duy trì GTID/binlog history phù hợp.

Trước khi cho connector đọc từ node mới:

- Xác nhận node mới có dữ liệu và GTID history đầy đủ.
- Xác nhận binlog cần thiết còn tồn tại.
- Xác nhận server identity và quyền replication.
- Kiểm tra cấu hình connector có thể nhận diện source mới.
- Không để connector đồng thời đọc hai source không đồng bộ.
- Kiểm tra schema history vẫn nhất quán với dòng sự kiện.

Nếu failover làm mất binlog chứa offset, connector có thể không thể resume bình thường. Khi đó cần restore log archive hoặc thực hiện quy trình snapshot/rebootstrap. Không reset offset chỉ để connector chuyển sang RUNNING nếu chưa biết dữ liệu nào sẽ bị bỏ qua hoặc phát lại.

## 13. Công cụ CDC khác và cách lựa chọn

Debezium không phải lựa chọn duy nhất. Một số hướng tiếp cận:

| Lựa chọn | Đặc điểm | Phù hợp khi |
|---|---|---|
| Debezium | Connector CDC dựa trên binlog, tích hợp Kafka Connect, schema history và snapshot | Cần pipeline Kafka, nhiều connector và consumer |
| Maxwell | MySQL binlog reader nhẹ, phát event JSON vào Kafka hoặc message stream theo cách triển khai | Muốn pipeline MySQL CDC tương đối đơn giản và chấp nhận mô hình tính năng của công cụ |
| Canal | Hệ sinh thái CDC MySQL phổ biến trong một số môi trường, có parser binlog và adapter | Hạ tầng đã dùng Canal hoặc cần tích hợp với ecosystem tương ứng |
| AWS DMS | Dịch vụ quản lý migration và CDC trên AWS | Muốn vận hành dịch vụ managed và tích hợp đích được hỗ trợ |
| Native binlog client | Tự đọc replication protocol/binlog qua thư viện hoặc code riêng | Có yêu cầu đặc biệt và đội ngũ đủ năng lực duy trì parser, offset, schema và recovery |
| MySQL replication | Sao chép transaction giữa MySQL server | Mục tiêu là replica MySQL, read scaling hoặc HA thay vì phát sự kiện cho nhiều loại consumer |

Tiêu chí lựa chọn:

- Nguồn và đích được hỗ trợ.
- Cơ chế snapshot và khả năng chụp lại dữ liệu.
- Offset storage và khả năng phục hồi.
- Cách quản lý DDL/schema history.
- Khả năng xử lý transaction, delete, key và schema evolution.
- Tích hợp broker, security, monitoring và vận hành.
- Tốc độ catch-up, throughput và độ trễ.
- Cộng đồng, tài liệu, phiên bản và năng lực đội ngũ.

Không chọn công cụ chỉ dựa trên throughput benchmark. Một pipeline có thể nhanh nhưng thiếu khả năng phục hồi schema change hoặc offset sẽ tạo rủi ro dữ liệu lớn hơn khi sự cố xảy ra.

## 14. Giám sát CDC pipeline

Một pipeline CDC cần theo dõi cả source, connector, broker và consumer.

| Nhóm | Chỉ số/điều kiện |
|---|---|
| Connector health | Trạng thái RUNNING/FAILED, task restart, lỗi gần nhất |
| Snapshot | Tiến độ bảng/chunk, số hàng đọc, thời gian snapshot, lỗi khóa |
| Source lag | Khoảng cách giữa binlog position mới nhất và position connector đã xử lý |
| Binlog retention | File cũ nhất còn tồn tại, dung lượng log, nguy cơ purge offset cần thiết |
| Kafka | Produce error, broker availability, topic partition, replication và disk |
| Schema history | Topic tồn tại, có thể đọc/ghi, không bị xóa hoặc thay đổi ngoài quy trình |
| Consumer | Consumer lag, retry, dead-letter, lỗi schema và thời gian xử lý |
| Data quality | Duplicate, missing key, NULL mới, row count và checksum đối soát |

Đừng chỉ dùng trạng thái connector RUNNING làm chỉ báo pipeline khỏe. Connector có thể RUNNING nhưng source lag tăng liên tục, consumer downstream bị nghẽn hoặc schema history sắp hết dung lượng.

### 14.1. Ước lượng lag

Lag có thể đo bằng chênh lệch vị trí binlog, thời điểm commit nguồn và thời điểm event đến broker. Mỗi cách đo có hạn chế:

- Timestamp chịu ảnh hưởng đồng hồ và độ trễ giữa server.
- Binlog position chỉ có ý nghĩa trong cùng file/chuỗi log và cần xử lý rollover.
- GTID set giúp so sánh lịch sử transaction nhưng không trực tiếp biểu diễn thời gian xử lý.
- Consumer lag phản ánh tiến độ Kafka consumer, không phải source connector.

Theo dõi nhiều chỉ số cùng lúc để phân biệt connector chậm với consumer chậm.

## 15. Xử lý sự cố thường gặp

### 15.1. Connector không khởi động

Kiểm tra:

1. DNS, TCP, TLS và firewall từ Kafka Connect worker đến MySQL.
2. User/password, host grant và quyền snapshot/replication.
3. log_bin, binlog_format, binlog_row_image và server_id.
4. Connector class và version dependency.
5. Tên property đúng với phiên bản Debezium.
6. Topic schema history và quyền Kafka.

Đọc lỗi gốc trong connector log. Không đổi hàng loạt cấu hình cùng lúc vì sẽ khó xác định nguyên nhân.

### 15.2. Connector báo binlog không còn tồn tại

Nguyên nhân thường là MySQL đã purge file mà offset cần. Hướng xử lý:

- Kiểm tra offset hiện tại và binlog file/position cần đọc.
- Kiểm tra archive binlog có thể khôi phục không.
- Nếu không có log, xác định snapshot/rebootstrap sẽ tạo khoảng thời gian nào bị phát lại hoặc cần đối soát.
- Lập kế hoạch dừng consumer hoặc xử lý duplicate khi tạo lại baseline.
- Tăng retention và cảnh báo để tránh lặp lại.

Không đặt connector bắt đầu ở binlog mới nhất để xóa lỗi. Làm vậy có thể bỏ qua thay đổi trong thời gian connector dừng.

### 15.3. Snapshot bị chậm

Kiểm tra:

- Kích thước bảng và index.
- Tốc độ đọc, buffer pool và I/O.
- Lock mode và transaction dài.
- Mức độ ảnh hưởng tới workload ứng dụng.
- Network throughput đến Kafka Connect.
- Consumer/broker có tạo backpressure không.

Với bảng lớn, cân nhắc incremental snapshot, tăng tài nguyên đọc có kiểm soát hoặc chia phạm vi capture. Không giảm lock mode trong production mà chưa thử tính nhất quán.

### 15.4. Schema history không khớp hoặc không đọc được

Kiểm tra:

- Schema history topic còn tồn tại và không bị xóa.
- Connector đang dùng đúng topic của deployment đó.
- Topic có cấu hình và quyền phù hợp.
- Offset đang trỏ đến binlog position có schema history tương ứng.
- Có DDL nào chạy ngoài quy trình hoặc bị lọc khỏi connector không.

Không tự tạo lại schema history topic rỗng rồi restart connector với offset cũ. Connector có thể không giải mã được row event đã tồn tại hoặc có thể tạo sai schema. Thực hiện recovery theo hướng dẫn đúng phiên bản Debezium.

### 15.5. Consumer nhận duplicate

Duplicate có thể xuất hiện do:

- Connector restart quanh thời điểm gửi record và lưu source offset.
- Kafka consumer xử lý xong nhưng chưa commit consumer offset.
- Snapshot được chạy lại hoặc incremental snapshot phát lại chunk.
- Consumer retry sau lỗi không rõ trạng thái commit ở đích.

Dùng upsert/idempotency key, ghi nhận source version và theo dõi duplicate rate. Không xóa record trùng thủ công khỏi Kafka mà chưa hiểu ảnh hưởng đến offset và thứ tự.

## 16. Quy trình thay đổi schema an toàn với CDC

Thay đổi schema cần phối hợp MySQL, Debezium, converter/schema registry và tất cả consumer.

Một ví dụ đổi tên cột status thành order_status:

1. **Expand:** thêm order_status nullable, giữ status.
2. Triển khai ứng dụng ghi cả hai cột trong cùng transaction.
3. Backfill các hàng cũ theo batch, đồng thời để connector tiếp tục đọc binlog.
4. Kiểm tra event có cả field mới và field cũ; cập nhật consumer hiểu schema mới.
5. Chuyển consumer đọc order_status sau khi dữ liệu đã được đối soát.
6. Chờ mọi consumer và ứng dụng cũ ngừng phụ thuộc status.
7. **Contract:** drop status trong migration riêng.
8. Kiểm tra schema history, DDL event và consumer sau khi contract.

Không đổi tên cột trực tiếp khi consumer đang kỳ vọng field cũ. DDL có thể được connector ghi nhận, nhưng không bảo đảm mọi downstream tự động ánh xạ field cũ sang field mới.

### 16.1. Thay đổi kiểu dữ liệu

Khi đổi DECIMAL precision/scale, VARCHAR length, ENUM hoặc kiểu số:

- Kiểm tra dữ liệu cũ có nằm trong phạm vi kiểu mới không.
- Kiểm tra converter và schema registry có chấp nhận thay đổi không.
- Kiểm tra consumer xử lý precision, scale và NULL.
- Kiểm tra event lịch sử vẫn giải mã theo schema cũ.
- Dùng migration expand/contract nếu thay đổi không tương thích.

Không chỉ kiểm thử record mới. Consumer có thể cần replay dữ liệu cũ từ Kafka, vì vậy schema mới phải tương thích với record đã lưu theo retention của topic.

## 17. Kiểm thử pipeline CDC

Một test CDC nên chạy với MySQL thật và broker thật hoặc môi trường tích hợp tương đương. Hãy kiểm tra từ thao tác nguồn đến kết quả consumer, không chỉ kiểm tra connector báo RUNNING.

Các test quan trọng:

1. Snapshot bảng có dữ liệu sẵn và xác minh record r.
2. INSERT, UPDATE, DELETE sau snapshot và xác minh op/key/before/after.
3. Restart connector và xác minh resume từ offset.
4. Dừng connector trong một khoảng thời gian ngắn rồi restart, xác minh catch-up.
5. Thực hiện DDL thêm cột và xác minh schema history cùng record mới.
6. Chạy incremental snapshot cho bảng lớn và cập nhật cùng hàng trong lúc snapshot.
7. Mô phỏng consumer restart để kiểm tra idempotency.
8. Kiểm tra bảng không có primary key và quyết định cách xử lý key.
9. Mô phỏng binlog retention hết hạn trong môi trường lab và diễn tập recovery.
10. Kiểm tra TLS, credential rotation và quyền user CDC.

### 17.1. Đối soát dữ liệu

Sau khi CDC hoạt động, đối soát theo:

- Số hàng theo bảng hoặc partition logic.
- Aggregate theo ngày, trạng thái hoặc tenant.
- Checksum theo dải primary key.
- Số lượng insert/update/delete đã xử lý.
- Bản ghi thiếu key, duplicate hoặc schema conversion error.

Không dùng row count đơn lẻ làm bằng chứng đầy đủ. Hai bảng có cùng số hàng vẫn có thể chứa dữ liệu khác nhau. Đối soát cần tính đến snapshot boundary và các transaction đang tiếp tục phát sinh.

## 18. Runbook triển khai và vận hành

### Trước khi bật connector

- [ ] Chọn công cụ CDC và phiên bản connector.
- [ ] Kiểm tra MySQL binlog và server identity.
- [ ] Chọn binlog retention dựa trên downtime và catch-up.
- [ ] Tạo user CDC với quyền tối thiểu.
- [ ] Chuẩn bị TLS và secret management.
- [ ] Xác định database/table include list.
- [ ] Chuẩn bị schema history topic và Kafka Connect offset storage.
- [ ] Kiểm tra consumer có xử lý snapshot, delete và schema change.

### Khi chạy snapshot

- [ ] Theo dõi lock, query load, I/O và tiến độ bảng.
- [ ] Kiểm tra snapshot record và row count.
- [ ] Không chạy DDL phá vỡ tương thích trong cửa sổ snapshot nếu chưa có kế hoạch.
- [ ] Xác nhận connector chuyển sang streaming sau snapshot.
- [ ] Theo dõi source lag và Kafka consumer lag.

### Khi vận hành streaming

- [ ] Cảnh báo connector/task FAILED hoặc restart liên tục.
- [ ] Cảnh báo binlog retention sắp ngắn hơn downtime dự kiến.
- [ ] Theo dõi schema history và offset storage.
- [ ] Theo dõi duplicate, conversion error và dead-letter.
- [ ] Kiểm tra consumer idempotency và thứ tự theo key.
- [ ] Kiểm thử failover MySQL định kỳ.

### Khi phục hồi

- [ ] Xác định source offset và binlog còn tồn tại hay không.
- [ ] Giữ nguyên schema history và offset trong quá trình điều tra.
- [ ] Nếu cần re-snapshot, xác định phạm vi duplicate và baseline.
- [ ] Chuẩn bị đối soát downstream trước khi mở lại traffic.
- [ ] Ghi nhận thời điểm bắt đầu/kết thúc khoảng gián đoạn.
- [ ] Cập nhật retention, alert và runbook sau sự cố.

## 19. Tình huống thực hành

Một hệ thống bán hàng có MySQL database sales_app với các bảng orders, order_items và customers. Data warehouse cần nhận dữ liệu gần thời gian thực. Nhóm triển khai Debezium MySQL Connector qua Kafka Connect. Ban đầu connector chụp snapshot, sau đó streaming binlog.

Trong tuần đầu, connector bị dừng 30 giờ do bảo trì Kafka Connect. MySQL chỉ giữ binlog 24 giờ. Sau khi restart, connector báo không tìm thấy binlog chứa offset đã lưu. Cùng thời điểm, nhóm ứng dụng muốn đổi cột orders.status thành orders.order_status.

Hãy lập kế hoạch xử lý:

1. Xác định source offset, binlog file/position hoặc GTID cuối cùng connector đã lưu.
2. Kiểm tra binlog archive có chứa phần log đã bị purge hay không.
3. Nếu có archive, đánh giá cách khôi phục và tiếp tục từ đúng lịch sử.
4. Nếu không có archive, lập kế hoạch snapshot/rebootstrap và xác định dữ liệu downstream có thể bị duplicate.
5. Giữ schema history hiện tại cho đến khi xác định được phương án recovery.
6. Tạm hoãn DDL đổi tên cột, triển khai expand/contract bằng cách thêm cột mới và dual-write.
7. Cập nhật consumer để hiểu schema mới, đối soát dữ liệu rồi mới contract cột cũ.
8. Tăng binlog retention đủ cho downtime tối đa, thời gian khắc phục và catch-up.
9. Thêm cảnh báo source lag, binlog oldest file, connector status và consumer lag.
10. Diễn tập lại kịch bản connector dừng lâu hơn retention trong môi trường lab.

**Câu hỏi tự kiểm tra:**

1. Snapshot ban đầu giải quyết bài toán gì trước khi streaming binlog?
2. Vì sao phải phối hợp snapshot boundary với binlog position?
3. Operation r khác c như thế nào?
4. Source offset khác Kafka record offset và consumer offset ra sao?
5. Vì sao binlog retention phải lớn hơn thời gian connector có thể dừng?
6. Schema history nội bộ của Debezium khác Schema Registry như thế nào?
7. Vì sao đổi tên cột có thể làm consumer cũ lỗi dù connector vẫn đọc được binlog?
8. Consumer nên xử lý duplicate và delete/tombstone như thế nào?
9. Khi nào incremental snapshot hữu ích và tại sao cần khóa ổn định?
10. Nếu offset cần thiết đã bị purge, vì sao không nên đặt connector bắt đầu ở binlog mới nhất?

## Kết luận

CDC với Debezium biến binlog MySQL thành luồng sự kiện cho hệ thống downstream. Snapshot cung cấp trạng thái nền, binlog streaming ghi nhận thay đổi tiếp theo, source offset giúp connector tiếp tục sau restart và schema history giúp giải mã row event qua các lần DDL. Độ tin cậy của pipeline phụ thuộc vào snapshot nhất quán, binlog retention, offset storage, schema evolution và consumer idempotency. Hãy vận hành CDC như một hệ thống dữ liệu có trạng thái: giám sát source lag, bảo vệ schema history, kiểm thử restart/failover và có runbook re-snapshot trước khi đưa pipeline vào production.

## Tài liệu tham khảo

- [Debezium Documentation — MySQL Connector](https://debezium.io/documentation/reference/stable/connectors/mysql.html)
- [Debezium Documentation — MySQL Connector Snapshot](https://debezium.io/documentation/reference/stable/connectors/mysql.html#mysql-snapshots)
- [Debezium Documentation — MySQL Connector Schema History](https://debezium.io/documentation/reference/stable/connectors/mysql.html#mysql-schema-history)
- [Debezium Documentation — Incremental Snapshots](https://debezium.io/documentation/reference/stable/incremental-snapshots.html)
- [Kafka Connect Documentation — Source Connector Offsets](https://kafka.apache.org/documentation/#connectconfigs)
- [MySQL 8.4 Reference Manual — The Binary Log](https://dev.mysql.com/doc/refman/8.4/en/binary-log.html)
- [MySQL 8.4 Reference Manual — Replication and Binary Logging Options](https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html)
