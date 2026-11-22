# SSTable hết hạn toàn bộ và những dữ liệu còn chặn thu hồi

## 1. Vấn đề: TTL đã hết nhưng ổ đĩa chưa trống

Trong **Apache Cassandra**, một giá trị có TTL (*time to live*) sẽ hết hiệu lực đối với truy vấn khi đến hạn. Tuy nhiên, **dữ liệu không nhất thiết được xóa vật lý ngay**. SSTable là file bất biến; các phiên bản cũ, marker xóa và metadata có thể còn trên đĩa cho đến khi compaction cho phép loại bỏ an toàn.

Một trường hợp đặc biệt quan trọng là **SSTable hết hạn toàn bộ** (*fully expired SSTable*): Cassandra có thể **bỏ cả file** thay vì đọc và viết lại từng hàng nếu xác định được rằng việc bỏ file không làm lộ dữ liệu cũ hoặc phá vỡ tính đúng đắn của thao tác xóa.

Bài học thuộc chương **SSTable và compaction**, tập trung vào ba câu hỏi thực tế:

1. Khi nào **mọi dữ liệu của một SSTable** được coi là đã hết hạn và vượt qua thời gian bảo vệ tombstone?
2. Những gì ở **SSTable khác**, hoặc trong chính SSTable ấy, khiến Cassandra **chưa thể thu hồi** file?
3. Làm sao thiết kế TTL, `TimeWindowCompactionStrategy` (TWCS), partition key, repair và quy trình quan sát để việc thu hồi vừa hiệu quả vừa an toàn?

Đây là kiến thức cần thiết khi vận hành mô hình wide-column phân tán: dữ liệu được chọn replica theo partition key/token, ghi nối tiếp thành nhiều SSTable, đọc hòa giải các phiên bản theo timestamp và xóa/TTL phải được truyền tới các bản sao.

**Sau bài này**, người học có thể giải thích điều kiện thu hồi một SSTable, phân tích một ví dụ có dữ liệu cũ bị che khuất, dự đoán vì sao dung lượng không giảm dù TTL đã hết, và thực hành kiểm tra bằng CQL/`nodetool`.

> Phạm vi: các **full replica** thông thường, TTL/tombstone và quy trình compaction. Các tối ưu và điều kiện nội bộ của bộ kiểm tra SSTable hết hạn có thể khác theo phiên bản Cassandra; các sơ đồ là mô hình giải thích, không thay thế việc kiểm chứng trên phiên bản đang chạy.

## 2. Ôn lại SSTable, TTL và tombstone

### 2.1. Vì sao có nhiều SSTable cho cùng một partition?

Replica nhận mutation, ghi vào **commit log** và cập nhật **memtable**. Khi memtable được flush, Cassandra tạo **SSTable bất biến**. Các lần ghi sau không sửa tại chỗ SSTable cũ mà tạo các dữ liệu mới trong memtable và SSTable khác; compaction về sau hợp nhất những file phù hợp.

~~~mermaid
flowchart TD
    C["Client INSERT / UPDATE / DELETE"] --> K["Coordinator chọn replica"]
    K --> R["Replica: commit log + memtable"]
    R --> F1["Flush → SSTable A"]
    R --> F2["Flush sau → SSTable B"]
    R --> F3["Flush sau nữa → SSTable C"]
    F1 --> Q["Read: hòa giải các version/tombstone"]
    F2 --> Q
    F3 --> Q
    F1 --> P["Compaction: kiểm tra dữ liệu có thể bỏ"]
    F2 --> P
    F3 --> P
~~~

Một partition có thể xuất hiện trong nhiều SSTable. Trong quá trình đọc, Cassandra dùng timestamp và tombstone để quyết định trạng thái logic còn hiển thị. **SSTable nằm trên đĩa** không có nghĩa tất cả giá trị trong đó còn được trả về cho client.

### 2.2. TTL không phải thao tác xóa file tức thì

`TTL` chỉ định thời gian sống của giá trị tính từ lúc ghi theo semantics CQL. Khi TTL hết, dữ liệu được coi như bị xóa, để lại thông tin xóa phục vụ việc hòa giải các bản ghi cũ. Tombstone cũng xuất hiện từ `DELETE` và một số thao tác cập nhật có tính xóa.

| Thời điểm | Trạng thái logic | Trạng thái lưu trữ |
| --- | --- | --- |
| Vừa ghi có TTL | Giá trị có thể đọc được theo CL đã chọn | Có thể đang ở memtable/commit log; về sau thành SSTable |
| TTL đến hạn | Giá trị không còn được trả về như dữ liệu sống | Metadata/tombstone và byte dữ liệu có thể vẫn nằm trong SSTable |
| Hết thời gian an toàn và điều kiện compaction thỏa | Marker xóa/dữ liệu cũ có thể được loại bỏ | Compaction có thể bỏ từng phần hoặc toàn bộ SSTable |
| File được thu hồi an toàn | Không còn file SSTable đó trong tập file đang phục vụ bảng | Dung lượng filesystem còn phụ thuộc snapshot/backup và file đang được tham chiếu |

**Hai loại “hết hạn” phải tách bạch:**

- **Hết hạn logic:** qua TTL, client không nên thấy giá trị cũ trong truy vấn bình thường.
- **Đủ điều kiện xóa vật lý:** Cassandra đã có cơ sở an toàn để bỏ byte/tombstone; có thể còn phải chờ compaction, kiểm tra dữ liệu chồng lấn và thời gian grace.

### 2.3. `gc_grace_seconds` bảo vệ điều gì?

`gc_grace_seconds` là khoảng thời gian được cấu hình cho bảng, liên quan đến việc **giữ tombstone đủ lâu** để replica từng vắng mặt còn cơ hội nhận thông tin xóa thông qua đồng bộ/repair. Trong ví dụ đơn giản, với TTL 30 ngày và grace 10 ngày, **không được suy rằng** file sẽ mất ngay ở ngày 30; cần xem xét mốc bảo vệ tombstone và những điều kiện khác.

`gc_grace_seconds` **không** phải TTL, cũng không tự chạy repair. Rút ngắn grace trong khi replica đã offline lâu hoặc repair không được thực hiện đúng chu kỳ có thể làm **dữ liệu đã xóa xuất hiện lại** (*zombie data*). Không chọn giá trị này chỉ để giải phóng dung lượng nhanh.

## 3. “SSTable hết hạn toàn bộ” nghĩa là gì?

Xét một SSTable X chỉ gồm dữ liệu có TTL. Nếu toàn bộ dữ liệu có liveness đã hết hiệu lực và các marker xóa đã qua giới hạn có thể thu hồi, X là **ứng viên** cho việc loại bỏ nguyên file. Nhưng **“ứng viên” chưa đồng nghĩa “được phép xóa”**.

Về mặt thực hành, phải đặt ít nhất ba câu hỏi:

1. **Có dữ liệu vẫn còn sống không?** Một giá trị chưa hết TTL, một giá trị không TTL, một marker liveness còn hiệu lực hoặc dữ liệu sống khác trong X có thể buộc giữ file.
2. **Thông tin xóa đã đủ an toàn để loại bỏ chưa?** Tombstone chưa qua ngưỡng bảo vệ, cùng rủi ro replica chưa nhận delete, là lý do không nên thu hồi.
3. **Dữ liệu trong file này đang che một phiên bản cũ ở file khác không?** Nếu có khả năng bỏ X làm bản ghi cũ từ SSTable khác hiện trở lại, Cassandra cần giữ thông tin cần thiết để duy trì kết quả đọc đúng.

Có thể mô tả **logic an toàn khái quát** bằng:

~~~text
Đủ điều kiện bỏ cả SSTable
    = toàn bộ nội dung đã hết hiệu lực
    + tombstone đủ điều kiện dọn theo thời gian/chính sách
    + không làm lộ dữ liệu cũ bị che khuất ở SSTable khác
    + có lượt xử lý/compaction nhận diện và thu hồi file.
~~~

Đây **không phải công thức thay thế cho thuật toán nội bộ**: Cassandra dùng thông tin tóm tắt trong SSTable và các kiểm tra liên quan đến thời gian, timestamp, phạm vi token/partition, những SSTable đang tồn tại và chiến lược compaction. Các điều kiện cụ thể phụ thuộc phiên bản và loại compaction.

### 3.1. Phân biệt “một số hàng đã hết TTL” và “cả file đã hết TTL”

| Nội dung SSTable | Có thể bỏ nguyên file ngay khi một vài TTL hết không? | Lý do |
| --- | --- | --- |
| 100% dữ liệu TTL đã hết, tombstone đã đủ tuổi, không đe dọa dữ liệu ở file khác | **Có thể**, khi bộ kiểm tra của Cassandra xác nhận đủ điều kiện | Không còn dữ liệu cần giữ trong file |
| 99% dữ liệu đã hết, 1% còn TTL | **Chưa thể bỏ nguyên file** | Một phần còn sống phải được lưu |
| Nhiều giá trị TTL, xen một giá trị **không TTL** | **Không thể coi file hết hạn toàn bộ** | Giá trị không TTL vẫn có thể cần cho read |
| Tất cả TTL đã hết nhưng tombstone chưa đủ điều kiện dọn | **Chưa thể** | Còn nghĩa vụ giữ marker xóa |
| Tất cả TTL đã hết nhưng dữ liệu ở file này đang che phiên bản cũ ở SSTable khác | **Không thể kết luận an toàn** | Bỏ file có thể làm lộ dữ liệu cũ |

Mấu chốt: **tỷ lệ tombstone cao không đồng nghĩa cả SSTable an toàn để xóa**. Một vài byte dữ liệu sống hoặc một quan hệ chồng lấn cần bảo toàn vẫn có thể giữ lại file rất lớn.

## 4. Dữ liệu ở SSTable khác có thể chặn việc thu hồi như thế nào?

### 4.1. Ví dụ “dữ liệu cũ sống lại” sau TTL

Giả sử trên **cùng một replica** có hai SSTable chứa cùng một partition key và cùng một cell:

- **SSTable A:** ghi cũ `status = 'ACTIVE'` không TTL, timestamp ghi nhỏ hơn.
- **SSTable B:** ghi mới `status = 'INACTIVE'` có TTL. Khi ghi B còn sống, B che khuất A vì có timestamp mới hơn.
- Khi TTL của B hết, thông tin hết hạn/xóa của B vẫn cần **che A** theo semantics timestamp, nếu A còn nằm trong một file khác.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant A as SSTable A
    participant B as SSTable B
    participant R as Replica read
    App->>A: Ghi status=ACTIVE (timestamp t1, không TTL)
    App->>B: Ghi status=INACTIVE (t2 > t1, TTL)
    Note over B: TTL hết; còn marker hết hạn
    R->>A: Đọc dữ liệu cũ ACTIVE
    R->>B: Đọc marker hết hạn của giá trị mới
    B-->>R: Che phiên bản t1
    R-->>App: Không trả lại ACTIVE cũ
    Note over A,B: Bỏ B quá sớm có nguy cơ làm ACTIVE xuất hiện lại
~~~

Vì vậy, **ngay cả khi mọi giá trị sống từng nằm trong B đã hết TTL**, việc thu hồi **toàn bộ B** vẫn phải xét những SSTable khác. Nếu B bị xóa sai trong khi A còn hiện hữu, lần đọc sau có thể chỉ còn thấy `ACTIVE` từ A, trái với trạng thái logic đã hết hạn/xóa.

**Không phải cứ hai SSTable cùng khoảng token là chắc chắn có zombie.** Chồng lấn chỉ là tín hiệu cần kiểm tra. Các quy tắc an toàn có thể dùng thêm timestamp, tuổi tombstone, metadata và ngữ cảnh compaction để xác định liệu file còn che dữ liệu nào hay không.

### 4.2. Những dạng chồng lấn khác cần xét

| Dữ liệu/tình huống | Vì sao là rào cản tiềm năng? | Hành động hợp lý |
| --- | --- | --- |
| SSTable cũ chứa cùng partition/cell | Marker trong file hết TTL có thể đang che giá trị cũ | Để compaction đánh giá chồng lấn; không xóa thủ công |
| Range tombstone hoặc `DELETE` trong file ứng viên | Delete có thể che nhiều hàng/phiên bản của SSTable khác | Giữ tombstone đến khi điều kiện purge an toàn |
| Một SSTable có thời điểm ghi/TTL rất khác nhau | Dữ liệu ghi trễ hoặc TTL dài sống lâu hơn phần còn lại | Tránh trộn dữ liệu ngoài window khi dùng TWCS |
| Một regular/static cell không TTL | Một phần dữ liệu có thể tồn tại vô thời hạn | Thiết kế schema/chính sách TTL nhất quán với vòng đời bảng |
| Replica từng offline lâu, repair bị bỏ lỡ | Xóa marker quá sớm có thể cho dữ liệu cũ từ replica đó quay lại | Xem `gc_grace_seconds`, lịch repair và quy trình phục hồi |
| Snapshot/backup giữ file cũ | File có thể đã rời tập SSTable hoạt động nhưng vẫn chiếm đĩa | Kiểm tra snapshot retention theo chính sách backup, không xóa tùy tiện |

Hai vấn đề cuối khác nhau: **chồng lấn SSTable** liên quan đến **đúng/sai của dữ liệu được đọc**; **snapshot/backup** liên quan đến **khi nào dung lượng vật lý thực sự được giải phóng**. Một SSTable được compaction loại khỏi tập file hoạt động vẫn có thể còn byte trên ổ do snapshot sử dụng liên kết file.

## 5. TWCS: chiến lược phù hợp khi dữ liệu có vòng đời theo thời gian

**TimeWindowCompactionStrategy (TWCS)** tổ chức compaction dựa trên các **cửa sổ thời gian**. Nó thường phù hợp các bảng time series có tốc độ ghi mới liên tục và TTL tương đối đồng nhất, ví dụ telemetry, log, metrics hoặc sự kiện có thời hạn lưu giữ.

Ý tưởng:

1. Các SSTable chứa dữ liệu ghi trong cùng một cửa sổ được compaction theo quy tắc của TWCS.
2. Khi cửa sổ đã đóng, file trong cửa sổ đó có thể trở nên tương đối ổn định nếu ứng dụng không thường xuyên cập nhật lại dữ liệu cũ.
3. Khi **toàn bộ dữ liệu trong một SSTable** hết hạn và việc thu hồi được kiểm tra là an toàn, Cassandra có cơ hội **bỏ cả SSTable**, tránh chi phí đọc/ghi lại từng hàng chỉ để loại dữ liệu hết hạn.

~~~mermaid
flowchart LR
    W1["Window D1: SSTable A"] --> E1["TTL đã hết; kiểm tra an toàn"]
    W2["Window D2: SSTable B"] --> E2["Một số hàng chưa hết TTL"]
    W3["Window D3: SSTable C"] --> E3["Còn dữ liệu sống"]
    E1 --> X{"Không chồng lấn nguy hiểm và đủ điều kiện?"}
    X -->|Có| D["Có thể drop toàn bộ A"]
    X -->|Không| K["Giữ A / compaction khác"]
    E2 --> Y["Giữ B"]
    E3 --> Z["Giữ C"]
~~~

**TWCS không bảo đảm rằng “qua một cửa sổ là file bị xóa”.** Cửa sổ compaction khác với TTL. Dữ liệu trong file vẫn phải hết hạn theo đồng hồ ghi/TTL thực tế và vượt các điều kiện thu hồi.

### 5.1. Lab: table có TTL và TWCS

Ví dụ lưu phép đo trong 30 ngày, cửa sổ compaction một ngày, replication factor 3 tại DC tên `dc1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_lab.readings_by_sensor_day (
    sensor_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    reading decimal,
    PRIMARY KEY ((sensor_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 2592000
  AND gc_grace_seconds = 864000
  AND compaction = {
      'class': 'TimeWindowCompactionStrategy',
      'compaction_window_unit': 'DAYS',
      'compaction_window_size': '1'
  };
~~~

`2592000` giây = **30 ngày**, `864000` giây = **10 ngày**. Đây là ví dụ giảng dạy, **không phải cấu hình chung cho mọi hệ thống**. `gc_grace_seconds` phải phù hợp khả năng repair, thời gian replica có thể ngừng hoạt động và yêu cầu an toàn dữ liệu.

**Vì sao partition key là `(sensor_id, event_day)`?** Mỗi cảm biến có một partition theo ngày để giới hạn độ lớn partition và truy vấn nhanh theo cảm biến/ngày. Nó **không trực tiếp bắt buộc SSTable chia theo ngày**: SSTable được tạo từ memtable flush và được TWCS tổ chức theo thời gian/timestamp ghi.

### 5.2. Minh họa thời gian nhưng không hứa ngày xóa

Giả sử một giá trị được ghi ở **ngày 0**, TTL đúng **30 ngày**, không có write muộn và không có dữ liệu sống khác trong SSTable:

~~~text
Ngày 0            Ngày 30                Ngày 40                Sau đó
  |------------------|----------------------|----------------------|
  Ghi có TTL        Hết TTL logic          Qua thêm 10 ngày        Có cơ hội được
  còn sống          xuất hiện marker       gc_grace minh họa       compaction thu hồi
~~~

Ở ngày 30, `SELECT` không còn thấy giá trị đã hết TTL. **Không thể kết luận chính xác ngày 40 file được xóa**, vì phải còn xét thời điểm các dữ liệu khác hết hạn, marker xóa, chồng lấn SSTable và lịch compaction. `gc_grace_seconds` không phải bộ hẹn giờ xóa file.

### 5.3. Những kiểu ghi làm TWCS khó bỏ nguyên file

- **Ghi muộn/backfill:** một mutation có timestamp thuộc quá khứ được viết hiện tại có thể trộn các đời dữ liệu theo cách bất lợi cho việc chia cửa sổ; đặc biệt cần cân nhắc khi dùng client-supplied timestamp.
- **TTL không đồng nhất:** một số cell TTL 7 ngày, số khác TTL 90 ngày trong cùng SSTable khiến file phải đợi phần sống lâu nhất.
- **Dữ liệu không TTL:** một cell tồn tại lâu có thể giữ nguyên file trong khi hàng loạt cell khác đã hết hạn.
- **Update/delete vào partition cũ:** phiên bản mới và marker xóa có thể trải trên nhiều SSTable/window, làm tăng chồng lấn và yêu cầu hòa giải.
- **Dùng compaction không phù hợp và ép major compaction tùy tiện:** có thể làm dữ liệu từ các thời điểm khác nhau bị gộp vào file lớn, giảm cơ hội drop nguyên file sớm.

Với workload nhiều update hoặc TTL trộn lẫn, cần cân nhắc lại chiến lược compaction và cách thiết kế bảng. TWCS đặc biệt phù hợp kiểu ghi **phần lớn append-only** và vòng đời dữ liệu dễ dự đoán, không phải giải pháp tự động cho mọi bảng CQL.

## 6. Điều gì sẽ xảy ra khi một file không đủ điều kiện?

Có hai đường xử lý khác nhau:

1. **Bỏ nguyên file (*whole-SSTable drop*):** nếu toàn bộ file đã hết hạn và an toàn, Cassandra có thể loại file khỏi tập SSTable hoạt động mà không tạo lại mọi hàng.
2. **Compaction có chọn lọc:** hệ thống đọc/merge những SSTable được chọn và có thể bỏ dữ liệu/tombstone **được phép purge**, trong khi vẫn giữ dữ liệu sống và thông tin xóa còn cần thiết.

Nếu còn một cell sống hoặc một marker phải giữ, không thể bỏ nguyên file ngay; nhưng compaction vẫn **có thể giảm một phần dung lượng** nếu các điều kiện purge ở mức dữ liệu thỏa. Không nên đánh đồng “file chưa drop” với “Cassandra không bao giờ thu hồi byte nào”.

### Vì sao “chạy compaction lớn” không chắc giải quyết được?

- Compaction tạo I/O đọc/ghi và dùng CPU/disk space tạm thời; ép compaction trên production có thể gây ảnh hưởng lớn.
- Marker tombstone chưa đủ tuổi hoặc còn cần để che dữ liệu cũ vẫn không thể tùy tiện xóa.
- TWCS phụ thuộc tách các cửa sổ; trộn dữ liệu cũ mới có thể tạo SSTable sống lâu hơn.
- Sau khi compaction, **snapshot hoặc hard link** vẫn có thể giữ byte của file cũ.

**Đích đúng là thiết kế vòng đời dữ liệu và an toàn khi purge**, không phải tìm một lệnh “xóa hết SSTable quá hạn” rồi chạy trên mọi node.

## 7. Thực hành CQL: kiểm tra dữ liệu sống và TTL

### 7.1. Viết dữ liệu có TTL, đọc TTL còn lại

Trên một cluster lab có DC tên `dc1` và đủ node để thỏa RF = 3, dùng table ở mục 5:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-9', '2026-11-21', '2026-11-21T03:00:00Z',
     123e4567-e89b-42d3-a456-426614174001, 21.75);

SELECT event_time,
       reading,
       TTL(reading) AS remaining_seconds,
       WRITETIME(reading) AS write_time_us
FROM telemetry_lab.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21';
~~~

`TTL(reading)` cho biết **số giây còn lại của cột** khi đang sống. `WRITETIME(reading)` cho biết write timestamp của cell (microsecond), **không phải** ngày Cassandra sẽ xóa SSTable. Sau khi cell hết TTL, câu `SELECT` có thể không còn trả về hàng đó; không thể dùng `TTL()` để xem tombstone đã được purge hay chưa.

`CONSISTENCY` là lệnh của **cqlsh**, không phải CQL gửi nguyên văn qua Java Driver. RF = 3 quyết định nơi lưu partition; `LOCAL_QUORUM` yêu cầu hai phản hồi replica trong DC cục bộ đối với read/write, **không ép SSTable drop trên tất cả replica cùng thời điểm**.

### 7.2. Tạo tình huống một giá trị sống lâu hơn

Cùng bảng có default TTL 30 ngày, ghi một bản ghi có TTL riêng dài hơn:

~~~sql
INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-9', '2026-11-21', '2026-11-21T03:05:00Z',
     123e4567-e89b-42d3-a456-426614174002, 22.10)
USING TTL 7776000;
~~~

`7776000` giây tương đương **90 ngày**. Dù phần lớn giá trị khác trong SSTable có TTL 30 ngày, **nếu** giá trị 90 ngày cùng nằm trong SSTable đó, SSTable **không hết hạn toàn bộ** ở mốc 30 ngày. Điều này minh họa tại sao chỉ nhìn TTL mặc định của bảng là chưa đủ.

Một write có `USING TTL 0` có thể được dùng để bỏ TTL cho dữ liệu ghi mới theo semantics CQL và cấu hình phù hợp; cell không còn TTL cũng là lý do khiến file chứa nó không thể được coi là hết hạn toàn bộ. Không nên pha dữ liệu cần lưu lâu vô hạn vào cùng luồng time series TTL nếu mục tiêu là whole-SSTable expiration.

### 7.3. Hạn chế của phép thử chỉ dùng CQL

`SELECT` cho biết dữ liệu **còn hiển thị logic** theo consistency level, **không cho biết** những file SSTable nào hiện tồn tại trên đĩa hoặc vì sao một file không được drop. Ngược lại, một chỉ số “tỷ lệ tombstone cao” **không bảo đảm** mọi partition/marker trong SSTable đã đủ điều kiện purge.

Để chẩn đoán cần kết hợp dữ liệu truy vấn, metadata/cấu hình table, metrics SSTable, thời gian ghi/TTL và tình trạng compaction/repair.

## 8. Quan sát thực tế: khi TTL hết mà dung lượng vẫn tăng

Trên node Cassandra có quyền chạy `nodetool`, các lệnh thường dùng:

~~~bash
nodetool tablestats telemetry_lab.readings_by_sensor_day
nodetool compactionstats
nodetool status
~~~

**Cách đọc:**

- `tablestats` cho các chỉ số như số SSTable, dung lượng dữ liệu được dùng, ước lượng tombstone/droppable tombstone và số liệu read; trường/cách đặt tên phụ thuộc phiên bản.
- `compactionstats` cho biết compaction đang chạy hoặc đang chờ, từ đó phân biệt “chưa có cơ hội xử lý” với “đã xử lý nhưng chưa đủ điều kiện”.
- `status` giúp biết node và data center nào đang up/down. Nếu một replica thiếu repair lâu ngày, đây là tín hiệu phải xem lại **an toàn xóa tombstone**, không phải chỉ tập trung dọn đĩa.

Ngoài `nodetool`, quản trị viên có thể dùng công cụ xem **metadata SSTable** được phân phối với đúng phiên bản Cassandra để kiểm tra thông tin timestamp, local deletion time và các file hiện có. Cần dùng công cụ theo quy trình vận hành an toàn; không chỉnh sửa hoặc xóa SSTable thủ công để thử nghiệm trên node production.

### Quy trình chẩn đoán có thứ tự

1. **Xác nhận hợp đồng lưu trữ:** bảng có TTL mặc định không; có write với TTL riêng, TTL 0, static column hoặc update cũ không?
2. **So thời điểm:** TTL của **giá trị được ghi muộn nhất** và ngưỡng an toàn tombstone đã qua chưa? Không suy từ ngày trong partition key nếu timestamp ghi khác ngày sự kiện.
3. **Xem compaction strategy:** TWCS có cửa sổ phù hợp hay đang trộn dữ liệu từ nhiều đời? Dữ liệu cũ có bị cập nhật/backfill thường xuyên không?
4. **Kiểm tra chồng lấn:** SSTable đang xét có khả năng che dữ liệu ở SSTable khác không? Không dùng một mình tỷ lệ tombstone làm điều kiện drop.
5. **Xem repair và trạng thái replica:** grace có được chọn đúng với lịch repair, thời gian offline tối đa và quy trình thay node không?
6. **Xem snapshot/backup:** file đã ra khỏi tập SSTable hoạt động nhưng dung lượng filesystem chưa giảm vì snapshot, backup hoặc file đang mở không?
7. **Đo lại theo thời gian:** số SSTable, dung lượng live/total, backlog compaction và hiệu năng đọc/ghi có thay đổi như mong đợi không?

### Bảng phân biệt nguyên nhân và hành động

| Triệu chứng | Giả thuyết cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Hầu hết dữ liệu hết TTL, SSTable count không giảm | Một vài cell sống lâu hơn hoặc thiếu cơ hội compaction | Xem TTL thực tế, số SSTable, window và backlog |
| TWCS giữ các file rất cũ | Ghi trễ, TTL trộn, marker che dữ liệu khác hoặc chồng lấn | Kiểm tra mẫu ghi, thời gian, metadata và bố trí window |
| Dung lượng ổ không giảm dù live SSTable ít hơn | Snapshot/backup vẫn giữ file | Đối chiếu retention/backup, chỉ dọn theo chính sách đã phê duyệt |
| Replica từng mất kết nối lâu | Tombstone chưa thể thu hồi an toàn hoặc repair quá hạn | Xử lý repair/khôi phục đúng quy trình trước khi thay grace |
| Đọc nhiều tombstone, latency cao | TTL/delete dày đặc và SSTable chồng lấn | Kiểm tra thiết kế partition, TTL, compaction và tombstone metrics |
| Ép compaction nhưng file mới vẫn lớn | Dữ liệu chưa hết hạn hoặc một phần sống bị gộp với phần cũ | Không ép tiếp vô hạn; sửa mô hình dữ liệu/vòng đời trước |

## 9. Góc nhìn Java: TTL, prepared statement và kỳ vọng của ứng dụng

Ứng dụng Java thường gán TTL theo sự kiện hoặc dựa vào `default_time_to_live` của bảng. Ví dụ dưới đây dùng **Apache Cassandra Java Driver 4.x** để ghi một phép đo TTL 30 ngày:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class WriteReadingWithTtl {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                    "INSERT INTO telemetry_lab.readings_by_sensor_day " +
                    "(sensor_id, event_day, event_time, event_id, reading) " +
                    "VALUES (?, ?, ?, ?, ?) USING TTL ?");

            BoundStatement write = insert.bind(
                    "sensor-9",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T03:10:00Z"),
                    UUID.fromString("123e4567-e89b-42d3-a456-426614174003"),
                    new BigDecimal("22.35"),
                    2_592_000)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(write);
        }
    }
}
~~~

**Các điểm cần hiểu:**

1. `USING TTL ?` là TTL **của dữ liệu được ghi**, không phải lời hẹn “SSTable sẽ được xóa sau đúng 30 ngày”.
2. `LOCAL_QUORUM` yêu cầu đủ phản hồi replica cho write tại DC cục bộ; nó **không điều khiển** compaction, grace hay thời điểm bỏ file.
3. Partition key gồm **`sensor_id` và `event_day`**. Thêm một cột bucket giúp quản lý kích thước partition, còn TTL và chiến lược compaction quyết định vòng đời file trên từng replica.
4. Ghi với event timestamp cũ, dùng TTL khác nhau hoặc sửa lại một khóa cũ có thể khiến SSTable/window còn nhiều đời dữ liệu; ứng dụng nên có quy ước thời gian và TTL rõ ràng.
5. `127.0.0.1` và `dc1` chỉ là ví dụ lab. Hệ thống thực tế cần cấu hình đúng contact points, local DC, authentication, TLS và giới hạn retry.

Khi ứng dụng cần **truy vấn các dòng đã hết TTL cho mục đích kiểm toán**, không thể trông chờ SSTable/tombstone còn tồn tại để đọc bằng CQL. Hãy giữ lịch sử/backup theo yêu cầu nghiệp vụ trước khi dữ liệu hết hiệu lực, hoặc dùng hệ lưu trữ lưu trữ dài hạn thích hợp.

## 10. Những nhận định đúng và sai

| Nhận định | Đánh giá | Lý do |
| --- | --- | --- |
| “TTL = 30 ngày nên file SSTable biến mất đúng ngày thứ 30.” | **Sai** | TTL hết ở cấp logic; file còn phụ thuộc grace, dữ liệu khác, chồng lấn và compaction. |
| “99% dữ liệu hết TTL thì có thể xóa nguyên file.” | **Sai** | Một cell còn sống hoặc marker cần giữ có thể chặn whole-SSTable drop. |
| “Không còn hàng CQL nào trả về nghĩa là SSTable rỗng và được xóa an toàn.” | **Sai** | Tombstone và dữ liệu cũ vẫn có thể nằm trên đĩa, giữ nghĩa vụ che phiên bản cũ. |
| “Tombstone trong SSTable mới có thể ngăn dữ liệu cũ ở file khác sống lại.” | **Đúng** | Cần giữ thông tin xóa cho tới khi an toàn để purge. |
| “Tăng RF làm SSTable trên từng node hết TTL nhanh hơn.” | **Sai** | RF tăng số replica; TTL/compaction hoạt động trên từng replica. |
| “TWCS giúp bỏ nguyên SSTable khi dữ liệu theo lứa thời gian đồng nhất.” | **Đúng, có điều kiện** | File phải hết hạn toàn bộ và vượt kiểm tra an toàn. |
| “`gc_grace_seconds = 0` luôn an toàn nếu TTL ngắn.” | **Sai** | Có nguy cơ dữ liệu cũ từ replica hoặc SSTable khác xuất hiện lại khi marker xóa mất quá sớm. |
| “Major compaction chắc chắn xóa mọi tombstone.” | **Sai** | Tombstone chưa đủ điều kiện purge vẫn phải giữ; compaction còn gây I/O và chiếm đĩa tạm. |
| “Dung lượng không giảm có thể do snapshot còn giữ SSTable cũ.” | **Đúng** | Dung lượng filesystem khác dung lượng của tập SSTable hoạt động. |

## 11. Bài tập tự kiểm tra có lời giải

**Bài 1.** Một SSTable chứa 10.000 dòng TTL 30 ngày và **một dòng TTL 90 ngày**. Sau 45 ngày, có thể coi file đã hết hạn toàn bộ không?

**Lời giải:** **Không.** Nếu dòng 90 ngày vẫn ở trong file, file còn dữ liệu sống. Dù phần lớn dòng khác đã hết hạn, không được bỏ nguyên file lúc này.

**Bài 2.** SSTable A có `value = 'OLD'` không TTL với timestamp `t1`. SSTable B có `value = 'NEW'` với TTL và timestamp `t2 > t1`. B đã hết TTL. Vì sao cần xét A trước khi bỏ B?

**Lời giải:** B có thể mang thông tin hết hạn/tombstone đang che phiên bản `OLD`. Bỏ B quá sớm khi A còn tồn tại có thể khiến `OLD` xuất hiện lại. Compaction phải kiểm tra an toàn chồng lấn.

**Bài 3.** Bảng TWCS có TTL 7 ngày và `gc_grace_seconds = 10 ngày`. Có thể khẳng định vào đúng ngày thứ 17 mọi file cũ đã bị xóa không?

**Lời giải:** **Không.** Ngay cả khi lấy mốc 7 + 10 ngày để minh họa yêu cầu thời gian, còn dữ liệu TTL khác, thời điểm ghi khác, tombstone, chồng lấn, lịch compaction và snapshot/backup.

**Bài 4.** Một nhóm giảm `gc_grace_seconds` xuống 0 để dọn đĩa, trong khi một replica đã offline nhiều ngày và repair chưa chạy. Nguy cơ là gì?

**Lời giải:** Marker xóa có thể bị loại trước khi replica vắng mặt nhận thông tin xóa; khi replica trở lại, dữ liệu cũ có thể lan truyền và **sống lại**. Phải đánh giá lịch repair, phục hồi replica và mô hình lỗi trước khi thay grace.

**Bài 5.** Metrics cho thấy số SSTable hoạt động giảm sau compaction, nhưng dung lượng filesystem gần như không giảm. Cần kiểm tra gì?

**Lời giải:** Kiểm tra **snapshot, backup, hard link**, file đang được tham chiếu và khả năng dung lượng khác tăng lên. Không tự xóa dữ liệu bên ngoài cơ chế retention/backup của tổ chức.

**Bài 6.** Tại sao một bảng time series thường append-only, TTL đồng nhất thường có cơ hội thu hồi tốt hơn với TWCS so với bảng liên tục sửa các hàng cũ?

**Lời giải:** Khi dữ liệu ít bị sửa và có tuổi gần nhau, SSTable thuộc window cũ có thể hết hạn theo lứa, ít chồng lấn với dữ liệu mới. Update/backfill cũ và TTL hỗn hợp tạo nhiều version sống ở các file/window khác nhau, có thể kéo dài thời gian cần giữ file.

## 12. Mô hình quyết định trước khi kết luận “file phải được xóa”

~~~mermaid
flowchart TD
    A["SSTable cũ và dung lượng chưa giảm"] --> B{"Mọi dữ liệu trong file đã hết TTL/hiệu lực?"}
    B -->|Không| C["Còn dữ liệu sống: không thể drop nguyên file"]
    B -->|Có| D{"Tombstone đã đủ điều kiện purge?"}
    D -->|Không| E["Giữ để bảo vệ xóa/repair"]
    D -->|Có| F{"Dữ liệu trong file đang che dữ liệu ở file khác?"}
    F -->|Có / chưa rõ| G["Cần kiểm tra chồng lấn; không xóa thủ công"]
    F -->|Không| H["Có thể đủ điều kiện whole-SSTable drop"]
    H --> I["Chờ cơ chế compaction/cleanup phù hợp"]
    I --> J{"Dung lượng filesystem đã giảm?"}
    J -->|Có| K["Đo lại hiệu năng và retention"]
    J -->|Chưa| L["Kiểm tra snapshot/backup/file reference"]
~~~

**Điểm cần ghi nhớ:** `TTL` quyết định **khi nào dữ liệu ngừng hiển thị**; `gc_grace_seconds` và cơ chế tombstone/repair góp phần bảo đảm **việc xóa không bị đảo ngược**; compaction và kiểm tra chồng lấn quyết định **khi nào byte trên SSTable có thể bị thu hồi**. Một SSTable chỉ có thể được bỏ nguyên file khi **không còn dữ liệu cần giữ và không còn chức năng che dữ liệu cũ**. Điều này quan trọng hơn mọi phép tính đơn giản kiểu “TTL đã qua nên file chắc chắn phải biến mất”.
