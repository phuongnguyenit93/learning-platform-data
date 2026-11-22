# Đọc qua dấu xóa và chi phí hợp nhất dữ liệu

Một truy vấn Cassandra có thể **trả về 20 hàng nhưng phải xem xét hàng nghìn hoặc hàng triệu giá trị đã bị xóa**. Lý do nằm ở cách Apache Cassandra lưu dữ liệu theo mô hình LSM (*log-structured merge*): dữ liệu được ghi vào memtable và SSTable bất biến; cập nhật, xóa và giá trị hết TTL có thể cùng tồn tại với các phiên bản cũ cho đến khi compaction dọn được chúng an toàn. Trong lúc đó, đường đọc phải **hợp nhất các phiên bản**, áp dụng **tombstone** và trả về trạng thái logic mới nhất.

Bài học thuộc chương **Tombstone và thu hồi** của module hệ quản trị wide-column Apache Cassandra. Chủ đề liên quan trực tiếp đến partition key, clustering columns, replication, consistency level, CQL, compaction, repair, xử lý lỗi và cách Java Driver phân trang truy vấn.

Trọng tâm không chỉ là câu hỏi “tombstone được tạo như thế nào?”, mà là:

- Cassandra phải làm gì khi **đọc xuyên qua các dấu xóa**?
- Vì sao lượng dữ liệu **phải duyệt** có thể lớn hơn rất nhiều so với lượng dữ liệu **trả về**?
- Một replica hợp nhất memtable/SSTable khác gì coordinator hòa giải kết quả giữa các replica?
- Vì sao `LIMIT`, paging, tăng consistency level hay ép compaction không phải cách chữa chung cho truy vấn quét tombstone?
- Làm thế nào đo, tái hiện, giải thích và giảm **read amplification** mà vẫn bảo toàn ngữ nghĩa xóa?

Sau bài học, bạn có thể giải thích read path qua tombstone, phân tích một tình huống latency cao, sử dụng CQL và công cụ quan sát một cách an toàn, viết truy vấn Java có giới hạn và chọn cách sửa ở mức schema/TTL/compaction/ứng dụng phù hợp.

## 1. Hai sự thật cần nhớ khi đọc Cassandra

**Sự thật thứ nhất:** Cassandra không nhất thiết ghi đè dữ liệu cũ tại chỗ. Một giá trị mới và một tombstone có thể nằm trên **những SSTable khác nhau**, hoặc một phiên bản ở memtable và phiên bản cũ trên SSTable.

**Sự thật thứ hai:** kết quả `SELECT` là **trạng thái logic được hòa giải**, không phải phép nối nguyên văn tất cả bản ghi trên đĩa.

Ví dụ minh họa một cell `payload` của cùng một full primary key:

```text
SSTable cũ:   payload = "A"          write timestamp = 100
SSTable mới:  payload = "B"          write timestamp = 200
Memtable:     DELETE payload         write timestamp = 300

SELECT payload:
  so sánh các phiên bản và dấu xóa
  -> tombstone 300 che A và B
  -> kết quả không thấy payload hiện hành
```

Bản A và B có thể vẫn chiếm byte trong SSTable. Điều đó không có nghĩa Cassandra sẽ trả A hoặc B khi đọc một cách hợp lệ. **Dấu xóa mới hơn ngăn các phiên bản cũ được hiển thị**, cho đến khi điều kiện thu hồi vật lý được bảo đảm.

### Ba lớp công việc dễ bị trộn lẫn

| Lớp | Nhiệm vụ | Không nên hiểu nhầm |
| --- | --- | --- |
| **Lưu trữ trên một replica** | Tìm partition/slice qua memtable và các SSTable có thể liên quan; hợp nhất phiên bản, TTL và tombstone. | Không phải cứ `SELECT LIMIT 20` là mở đúng 20 cell. |
| **Hòa giải giữa các replica** | Theo consistency level và read protocol, so sánh/đối chiếu trạng thái từ các replica được hỏi, xử lý sai khác theo cơ chế phiên bản. | Không giống compaction SSTable hoặc chạy `nodetool repair`. |
| **Thu hồi vật lý** | Compaction có thể loại dữ liệu cũ và tombstone khi đủ điều kiện an toàn. | Không xảy ra tức thì sau DELETE hoặc TTL hết hạn. |

Đọc qua dấu xóa là công việc **bình thường và cần thiết**; vấn đề hiệu năng xuất hiện khi lượng dữ liệu phải xét quá lớn so với kết quả có ích.

## 2. Đi theo read path: từ CQL tới các SSTable

Xét yêu cầu lấy sự kiện mới nhất của một thiết bị. Cassandra trước hết cần xác định **partition key hoàn chỉnh**, sau đó dùng **clustering range** để thu hẹp vùng dữ liệu cần đọc.

Sơ đồ khái niệm:

```text
Ứng dụng Java / cqlsh
         |
         | SELECT ... WHERE full partition key AND clustering range
         v
   Coordinator node
         |
         | Chọn replica theo token, topology và consistency level
         v
   Replica phục vụ đọc
         |
         +--> Memtable: giá trị mới, tombstone chưa flush
         |
         +--> SSTable-1: giá trị cũ
         |
         +--> SSTable-2: tombstone mới hơn
         |
         +--> SSTable-3: giá trị/TTL khác
         |
         v
   Hợp nhất theo partition + clustering order
   và hòa giải theo write timestamp, TTL, deletion markers
         |
         v
   Hàng/cell còn sống đáp ứng WHERE và LIMIT
         |
         v
 Coordinator đối chiếu các phản hồi cần thiết
         |
         v
   Kết quả CQL được phân trang về client
```

Trên mỗi replica, Cassandra dùng cấu trúc như **Bloom filter, partition index, partition summary, cache** và thông tin SSTable để tránh đọc những tệp hoặc đoạn không liên quan khi có thể. Không phải truy vấn nào cũng phải quét **toàn bộ SSTable**. Nhưng khi một partition có dữ liệu/phiên bản ở nhiều nguồn hoặc có tombstone trong đoạn đang đọc, replica vẫn phải xét đủ thông tin để xác định trạng thái đúng.

### Mỗi bước tốn tài nguyên gì?

| Bước | Công việc | Chi phí nổi bật |
| --- | --- | --- |
| Xác định partition | Hash partition key, chọn token và replica | Định tuyến, mạng/coordinator. |
| Định vị trong một SSTable | Kiểm tra chỉ mục/filter và vị trí partition | CPU, I/O, cache misses. |
| Duyệt clustering slice | Đọc các vị trí dữ liệu nằm trong phạm vi cần thiết | I/O, giải mã, byte được quét. |
| Merge các nguồn | Hợp nhất thứ tự clustering từ memtable/SSTable | CPU, bộ nhớ tạm, nhiều iterator. |
| Áp dụng deletion/TTL | So write timestamp, row/range/partition tombstone, cell expiry | CPU, số marker và phiên bản cần xét. |
| Hòa giải replica | So sánh trạng thái theo read protocol/consistency | Mạng, latency và công việc đọc bổ sung tùy trường hợp. |
| Phân trang phản hồi | Serialize hàng sống và truyền về client | Mạng, heap, thời gian fetch trang. |

**Read amplification** là khi công việc thực tế cao hơn nhiều so với lượng dữ liệu hữu ích được trả về. Tombstone là một nguồn amplification; nhiều SSTable, cell lớn, truy vấn range rộng và replica chậm còn có thể làm vấn đề nặng hơn.

## 3. Schema minh họa: sự kiện của thiết bị theo ngày

Dùng một bảng có partition key ghép và clustering key theo thời gian:

```sql
CREATE TABLE device_events_by_day (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_kind  text,
    payload     text,
    source_app  text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
```

Phân tích:

- **Partition key:** `(tenant_id, device_id, event_day)`. Mỗi thiết bị trong mỗi ngày có một phân vùng logic.
- **Clustering columns:** `occurred_at` và `event_id`. Hàng mới hơn được truy vấn theo thứ tự thời gian giảm dần; `event_id` phân biệt các sự kiện trùng thời điểm.
- **Regular columns:** `event_kind`, `payload` và `source_app`. Chúng có thể có giá trị và TTL/write timestamp riêng.
- Hai ngày của cùng thiết bị là **hai partition keys khác nhau**, dù có cùng các giá trị cột còn lại.

Ghi một số dữ liệu thử nghiệm vào một partition:

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_kind, payload, source_app
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'reading', 'temperature=38.1', 'gateway-1'
);

INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_kind, payload, source_app
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    7c2c4f75-5c44-4be4-99a0-08688b465200,
    'reading', 'temperature=38.4', 'gateway-1'
);

INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_kind, payload, source_app
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:10:00Z',
    4e52e99a-178e-4d5b-9a31-027d5956e5b8,
    'reading', 'temperature=38.7', 'gateway-2'
);
```

Đây là dữ liệu lab. Phần tiếp theo giả sử lệnh DELETE được thực hiện **sau khi** có các phiên bản giá trị nói trên và được quan sát ở mức nhất quán thích hợp. Khi nghiên cứu hiệu năng, phải tách tình trạng sau DELETE với trường hợp các thao tác chạy chồng chéo.

## 4. Đọc một cell có tombstone: merge theo write timestamp

Giả sử xóa `payload` của sự kiện lúc 08:05:

```sql
DELETE payload
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

Khi đọc:

```sql
SELECT occurred_at, event_id, event_kind, payload, source_app
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

Giá trị `payload` không còn sống; nhưng `event_kind` và `source_app` có thể còn tồn tại. Đó là khác biệt giữa **cell deletion** và **row deletion**.

### Minh họa hòa giải một cell

```text
SSTable-1:
   payload = "temperature=38.4", timestamp 100

SSTable-2:
   payload = "temperature=38.5", timestamp 150

Memtable:
   DELETE payload, timestamp 200

Kết quả đọc:
   payload = null, vì tombstone ở 200 che hai phiên bản cũ

Nhưng:
   event_kind = "reading" vẫn sống
   source_app = "gateway-1" vẫn sống
   -> hàng E2 có thể tiếp tục xuất hiện
```

Các timestamp 100/150/200 chỉ là số thứ tự minh họa, không phải đơn vị thực tế của thao tác lab. Cassandra dùng write timestamp và quy tắc giải quyết xung đột của nó; **thứ tự trả lời của hai request không tự thay thế cho thứ tự write timestamp**.

Một lần ghi lại `payload` có timestamp mới hơn tombstone có thể tạo giá trị sống tại cùng full primary key. Tombstone không phải khóa cấm vĩnh viễn.

## 5. Row, range và partition tombstone khi đọc

Dấu xóa có thể che phạm vi lớn hơn một cell:

| Dạng xóa | Dữ liệu bị che khi đọc | Có xóa các hàng ngoài phạm vi không? |
| --- | --- | --- |
| **Cell tombstone** | Một cell regular hoặc static | Không. |
| **Collection element/complex deletion** | Một phần tử hoặc một collection không frozen | Không tự xóa regular columns khác. |
| **Row tombstone** | Các cell/hàng tại một full clustering key | Không tự xóa các hàng clustering khác hoặc static data. |
| **Range tombstone** | Các hàng/cell cũ thuộc một đoạn clustering của partition | Không xóa hàng ngoài khoảng hay partition khác. |
| **Partition tombstone** | Các hàng và static data cũ trong một partition key hoàn chỉnh | Không tự xóa partition keys khác. |

### Row deletion

```sql
DELETE FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:05:00Z'
  AND event_id = 7c2c4f75-5c44-4be4-99a0-08688b465200;
```

Khác với xóa `payload`, lệnh này xóa **hàng E2**. Khi đọc partition theo clustering order, replica phải so row deletion với các cell cũ thuộc cùng clustering key.

### Range deletion

Trong những phiên bản/ngữ cảnh CQL hỗ trợ phép xóa theo **đoạn clustering**, một range tombstone có thể che nhiều hàng mà không cần phát một DELETE riêng cho từng hàng.

Ví dụ khái niệm:

```text
Phân vùng của ngày 2026-11-21:

08:00 E1     <- range xóa bắt đầu
08:05 E2     <- nằm trong range bị xóa
08:10 E3     <- nằm trong range bị xóa
08:15 E4     <- range xóa kết thúc
08:20 E5     <- ngoài range, vẫn sống

Range tombstone có thể lưu phạm vi [08:00, 08:15)
theo điều kiện và thứ tự clustering được hỗ trợ.
```

Khi đọc một slice giao với khoảng này, replica cần **áp dụng phạm vi xóa** trong lúc duyệt các hàng và marker tương ứng. Điều đó không có nghĩa mỗi hàng trong range luôn có một row tombstone vật lý riêng.

### Partition deletion

```sql
DELETE FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

Một partition-level tombstone che tất cả dữ liệu cũ thuộc **partition ngày đó** ở write timestamp của thao tác xóa. Các sự kiện ngày khác có partition key khác nên không bị xóa bởi lệnh này.

**Đừng chạy các DELETE minh họa liên tiếp trên cùng bộ dữ liệu nếu muốn so sánh từng loại xóa.** Hãy khởi tạo lại dữ liệu hoặc dùng các partition keys thử nghiệm riêng.

## 6. Vì sao dữ liệu đã xóa vẫn được đọc qua trước khi trả kết quả?

Ở mức logic, nếu E2 bị xóa, một `SELECT` không được trả E2 như hàng sống. Nhưng ở mức lưu trữ, có thể xảy ra:

```text
Memtable:      tombstone cho E2 (timestamp 300)
SSTable-A:     E1 và E2 cũ (timestamp 100)
SSTable-B:     E2 và E3 cũ (timestamp 200)
SSTable-C:     E3 được sửa mới hơn (timestamp 350)

Một replica đọc slice chứa E1..E3:
- tìm các nguồn liên quan;
- merge theo clustering order;
- xét tombstone E2 với các phiên bản cũ của E2;
- xét phiên bản E3 hợp lệ;
- chỉ trả E1/E3 nếu vẫn sống và khớp WHERE.
```

Cassandra không thể bỏ qua tombstone chỉ vì ở SSTable khác đã có một giá trị. Nếu bỏ thông tin xóa trong khi phiên bản cũ còn tồn tại, dữ liệu đã xóa có nguy cơ trở lại kết quả.

### Một tombstone có thể che rất nhiều dữ liệu

Từ góc độ CQL, `DELETE FROM ... WHERE partition_key` là một mutation ở cấp partition. Nhưng nó có thể che **hàng triệu clustering rows cũ**, và các SSTable chứa các hàng ấy có thể vẫn chiếm dung lượng đáng kể.

Điểm cần phân biệt:

- **Số lệnh DELETE:** số mutation mà ứng dụng phát.
- **Số tombstone/marker trong lưu trữ:** phụ thuộc phạm vi deletion, TTL, collection, phiên bản và compaction.
- **Số cell/marker phải xét khi đọc:** phụ thuộc truy vấn, dữ liệu sống/xóa, SSTable overlap, index/filter và kế hoạch đọc.
- **Số hàng trả về:** có thể chỉ bằng 0, 10 hoặc 20.

Các đại lượng này **không bằng nhau**. Không thể dùng số hàng trả về để suy ra chính xác chi phí read path.

## 7. Read amplification: đo chi phí của một kết quả nhỏ

Giả sử API cần **20 sự kiện mới nhất còn sống** nhưng nhiều hàng trong cùng dải clustering đã bị xóa.

```text
Clustering order (mới -> cũ):

E1000  deleted
E0999  expired
E0998  deleted
E0997  deleted
...
E0801  deleted
E0800  live #1
...
E0300  live #20

Kết quả trả về:   20 hàng sống
Số vị trí/marker phải xét: có thể rất lớn
```

Một thước đo **khái niệm**:

```text
read_amplification_ratio
  = số đơn vị dữ liệu hoặc marker cần xử lý
    / số đơn vị dữ liệu có ích được trả về
```

Tỷ lệ này dùng để diễn giải, **không phải metric chuẩn thống nhất** mà mọi phiên bản Cassandra xuất trực tiếp. Đơn vị đo có thể là cell, byte đọc từ disk, SSTable fragments hay số hàng, nên phải ghi rõ định nghĩa khi so sánh.

Ví dụ workload đo được **2.020 vị trí liên quan** để trả về **20 hàng** có tỷ lệ 101 theo phép đếm vị trí. Điều đó không có nghĩa mỗi hàng sống tương ứng đúng một cell hoặc số byte đọc gấp 101 lần. Mỗi hàng có thể gồm nhiều cell, tombstone và phiên bản trên nhiều SSTable.

### Vì sao p99 có thể cao dù p50 tốt?

- Phần lớn partition keys có ít tombstone, nhưng vài tenant hoặc thiết bị có rất nhiều.
- Một số dải clustering mới nhất bị DELETE hoặc TTL hết hạn dày đặc.
- Các replica khác nhau có số SSTable và cache state không giống nhau.
- Compaction/repair hoặc I/O nền làm tăng độ trễ của một số request.
- Truy vấn fan-out tới nhiều partition/shard chỉ cần **một nguồn chậm** để kéo tổng thời gian lên cao.

Vì vậy phải quan sát **p95/p99, outlier keys và công việc đọc thực tế**, không chỉ trung bình độ trễ hay số hàng được trả.

## 8. `LIMIT` làm gì và không làm gì?

`LIMIT` hạn chế số **hàng kết quả**, không trực tiếp giới hạn số tombstone phải quét.

```sql
SELECT occurred_at, event_id, event_kind
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

Khi các hàng sống nằm sát đầu dải clustering, Cassandra có thể dừng sớm sau khi đủ 20 hàng. Khi đầu dải có nhiều dữ liệu xóa hoặc hết TTL, replica có thể phải đọc lâu hơn để tìm được 20 hàng hợp lệ.

So sánh:

| Câu truy vấn | Phạm vi | Cần lưu ý |
| --- | --- | --- |
| Đủ partition key, `LIMIT 20` | Hàng mới nhất của một partition ngày | Có thể tốt nếu ít tombstone ở đầu dải. |
| Đủ partition key, khoảng clustering 5 phút | Slice hẹp theo thời gian | Phù hợp nếu khoảng ít hàng/tombstone. |
| Đủ partition key nhưng khoảng 24 giờ | Một slice lớn trong partition ngày | Có thể phải xét rất nhiều hàng/cell/tombstone. |
| `COUNT(*)` trên partition rất lớn | Đếm hàng hợp lệ | Có thể đọc nhiều dữ liệu; không đo được số tombstone vật lý. |
| Thiếu partition key và thêm `ALLOW FILTERING` | Có thể cần lọc quét nhiều dữ liệu | Không chữa read amplification, có thể làm tệ hơn. |

### Một truy vấn có `LIMIT 20` vẫn có thể thất bại

Tùy phiên bản và cấu hình, Cassandra có cơ chế **warning/failure threshold** khi lượng tombstone quét trong một truy vấn vượt ngưỡng. Một truy vấn cần rất nhiều tombstone để trả về 20 hàng có thể chậm, timeout hoặc gặp giới hạn bảo vệ. Không nên đơn giản tăng ngưỡng để “cho phép trả 20 hàng”; trước tiên phải xác định vì sao query phải quét quá nhiều dấu xóa.

## 9. Paging không phải quá trình thu hồi tombstone

Cassandra Java Driver có thể phân trang: thay vì tải hàng nghìn hàng trong một lần phản hồi, nó fetch dữ liệu theo các **trang kết quả**. Page size hỗ trợ giới hạn khối lượng phản hồi và bộ nhớ phía client.

```text
SELECT ... LIMIT 200
        |
        v
    Page 1: 50 hàng sống
    Page 2: 50 hàng sống
    Page 3: 50 hàng sống
    Page 4: 50 hàng sống
```

Trên thực tế số hàng mỗi trang và cách truy xuất có thể chịu ảnh hưởng giao thức/cấu hình và tình trạng dữ liệu. Điều cần giữ là:

- **`LIMIT 200`** giới hạn tổng kết quả của câu SELECT.
- **Page size 50** là kích thước trang driver yêu cầu, không phải một hard limit cho mọi công việc nội bộ tại replica.
- **Paging state** giúp tiếp tục truy vấn, không dọn SSTable hay tombstone.
- Nếu mỗi trang cần bỏ qua nhiều tombstone, tổng thời gian fetch các trang vẫn có thể cao.
- Khi ứng dụng tự động duyệt hết `ResultSet`, các trang tiếp theo có thể được fetch; tránh gọi `all()` cho truy vấn có thể trả khối lượng lớn mà không có ngân sách bộ nhớ.

**Đo riêng first-page latency và toàn bộ thời gian duyệt kết quả**. Một trang đầu nhanh không đảm bảo truy vấn lịch sử dài hoặc những trang tiếp theo cũng nhanh.

## 10. Clustering range: thu hẹp phạm vi phải duyệt

Thiết kế bảng theo truy vấn là biện pháp hiệu quả để giảm số hàng/tombstone mà replica phải xét.

Ví dụ chỉ muốn sự kiện 08:00–08:10 trong một ngày:

```sql
SELECT occurred_at, event_id, event_kind, payload
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T08:10:00Z'
LIMIT 100;
```

Đây là **một partition lookup và một khoảng clustering**. Khoảng đóng–mở `[start, end)` giúp tránh trùng dữ liệu tại ranh giới khi ghép các lát thời gian liền nhau.

Tuy nhiên:

1. Một khoảng 10 phút chứa 1.000 sự kiện xóa vẫn có thể tốn chi phí lớn.
2. `LIMIT` không loại bỏ tombstone bên trong slice.
3. Clustering key `occurred_at` giúp tìm đúng vị trí thời gian, nhưng **không phân phối các hàng trong cùng partition sang token khác**.
4. Thêm điều kiện lọc trên `payload` hoặc `event_kind` mà không có mô hình truy vấn thích hợp không tự tạo chỉ mục hiệu quả.

### Partition key đầy đủ là điều kiện quan trọng

Các cột `tenant_id`, `device_id` và `event_day` **cùng** tạo partition key. Truy vấn chỉ biết `tenant_id` và `device_id` không thể định vị một partition ngày duy nhất:

```sql
-- Không đủ partition key của bảng ví dụ:
SELECT *
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Đây không phải truy vấn đọc history “toàn ngày” hiệu quả bằng primary key. Muốn đọc nhiều ngày, tầng dịch vụ phải xác định các bucket ngày cần đọc, truy vấn từng partition và merge kết quả.

## 11. Tombstone từ TTL: khi hết hạn không có DELETE mới

TTL (*time to live*) là một nguồn lớn của dữ liệu đã hết hạn trong Cassandra. Một cell được ghi với TTL mang thông tin hết hạn; khi hết hạn, nó **không còn sống** trong quá trình đọc và được xử lý như dấu xóa, nhưng **không cần có lệnh `DELETE` mới** phát đúng thời điểm hết hạn.

Ví dụ:

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_kind, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    142dd6ae-6706-4f2c-a5e8-61cdd9c22cad,
    'temporary',
    'expire-after-60-seconds'
) USING TTL 60;
```

Trước khi hết hạn, cell được ghi có thể còn sống. Sau khi hết hạn, Cassandra không trả giá trị đó như dữ liệu hiện hành; trong SSTable nó vẫn có thể cần được xét trong lúc hòa giải và compaction.

### TTL của cell không tự xóa toàn partition

Nếu một hàng có nhiều cột, chúng có thể có **TTL/write timestamp khác nhau**. Hết TTL của `payload` không mặc nhiên xóa `source_app`, mọi hàng clustering khác hoặc partition ngày. Ngược lại, khi tất cả dữ liệu quyết định liveness của hàng đã hết hạn, hàng có thể không còn xuất hiện như hàng sống.

Không nên diễn giải mỗi TTL expiry là một **partition tombstone**. TTL hết hạn có tác động ở phạm vi những cell/row liveness được ghi với TTL tương ứng.

### TTL tính từ khi ghi, không tự tính từ `occurred_at`

Sự kiện được tạo vào thứ Hai nhưng backfill vào thứ Tư với `USING TTL 604800` thường hết hạn theo thời gian ghi thứ Tư, không phải “bảy ngày sau event time” nếu ứng dụng không tính TTL còn lại. Nếu retention gắn với event time, phải có chính sách backfill và TTL rõ ràng.

### Xem TTL và write timestamp

```sql
SELECT occurred_at, event_id,
       payload, TTL(payload), WRITETIME(payload)
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 142dd6ae-6706-4f2c-a5e8-61cdd9c22cad;
```

`TTL(payload)` cho thời gian còn lại khi cell sống và có TTL; `WRITETIME(payload)` cho timestamp của cell khi khả dụng. Hai hàm này **không liệt kê tombstone vật lý**, và `null` ở kết quả SELECT không tự nói được cell bị DELETE, hết TTL hay chưa từng ghi.

## 12. Merge ở replica khác hòa giải ở coordinator

Đường đọc có **hai cấp hợp nhất** cần phân biệt.

### Cấp 1: một replica hợp nhất phiên bản từ memtable/SSTable

Replica cần giải quyết các bản ghi cùng full primary key nhưng khác write timestamp, một số chứa tombstone/expired cell. Đây là công việc trực tiếp của LSM read path.

```text
Replica A:
  memtable      -> DELETE payload @300
  SSTable-1     -> payload='A' @100
  SSTable-2     -> payload='B' @200
  Kết quả logic -> payload bị xóa
```

Nếu có nhiều SSTable chứa cùng partition, read path có thể tốn công việc lớn hơn khi tìm, merge và lọc. Bloom filter/index và caching giúp giảm công việc không cần thiết nhưng không thể bỏ quy tắc hòa giải.

### Cấp 2: coordinator xử lý kết quả từ các replica

Khi một request cần đọc theo consistency level như `LOCAL_QUORUM`, coordinator có thể liên hệ nhiều replica, nhận dữ liệu/digest và xử lý sai khác theo cơ chế đọc của phiên bản Cassandra. Có thể phải làm thêm công việc khi replica chậm hoặc trả trạng thái khác nhau.

```text
Replica A: tombstone @300 (payload đã xóa)
Replica B: tombstone @300
Replica C: payload='A' @100 (bỏ lỡ DELETE)

Coordinator/đọc theo CL:
  các replica được hỏi và cách phản hồi tùy CL/read protocol
  trạng thái mới hơn có thể thắng khi được hòa giải
```

Đây là **hòa giải khi đọc**, không đồng nhất với **anti-entropy repair định kỳ**. Hành vi *read repair* khi phát hiện sai khác có thể tùy phiên bản, cấu hình và phạm vi truy vấn. Không nên khẳng định rằng chỉ cần một SELECT là **mọi replica chắc chắn được sửa vĩnh viễn**.

### Consistency level giải quyết điều gì?

| Mức/khía cạnh | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| `LOCAL_ONE` | Thành công với mức đọc/ghi yêu cầu một replica trong data center liên quan. | Có thể thấy trạng thái cũ nếu replica được hỏi chưa nhận cập nhật/xóa. |
| `LOCAL_QUORUM` | Yêu cầu số replica đáp ứng quorum trong data center; tăng cơ hội hội tụ theo giả định tương ứng. | Không dọn tombstone vật lý, không thay đổi partition key hoặc sửa mọi replica. |
| Repair | Đồng bộ sai khác giữa replica theo phạm vi/chiến lược repair. | Không giống compaction, và không thể bỏ qua kế hoạch sửa replica mất kết nối lâu. |
| Compaction | Hợp nhất SSTable, có thể dọn tombstone/phiên bản cũ khi an toàn. | Không tự thực hiện anti-entropy giữa mọi replica. |

Chọn CL phải cân bằng tính nhất quán, latency và tính sẵn sàng. **Tăng CL không làm tombstone biến mất khỏi SSTable**; một số truy vấn còn phải chờ nhiều replica hơn.

## 13. `gc_grace_seconds`, repair và nguy cơ zombie data

Cassandra cần giữ dấu xóa đủ lâu để một replica từng bỏ lỡ DELETE không mang dữ liệu cũ quay lại sau khi các replica khác đã thu hồi marker.

```text
T0: A, B, C có payload='A' @100
T1: C mất kết nối
T2: DELETE payload @200 được A, B lưu
T3: A/B vẫn giữ tombstone, đọc có thể che 'A'
T4: Repair/đồng bộ đủ điều kiện giúp C nhận deletion
T5: Compaction được phép dọn tombstone/phiên bản cũ khi an toàn
```

Nếu C tiếp tục giữ `'A'` trong khi dấu xóa trên A/B bị purge **quá sớm**, trạng thái cũ có nguy cơ xuất hiện lại khi C quay về và dữ liệu được hòa giải. Hiện tượng này được gọi là **zombie data**.

`gc_grace_seconds` là cấu hình liên quan **khoảng bảo vệ trước khi tombstone đủ điều kiện thu hồi**, không phải lịch hẹn xóa vật lý chắc chắn. Điều kiện purge còn phụ thuộc SSTable overlap, compaction strategy, trạng thái và cơ chế của phiên bản Cassandra. Repair cần được vận hành phù hợp với chính sách xóa và khoảng mất kết nối có thể xảy ra.

Không nên:

- Giảm `gc_grace_seconds` xuống rất thấp chỉ để giảm cảnh báo read latency.
- Coi một lần `nodetool compact` là bằng chứng mọi dấu xóa đã được dọn an toàn.
- Cho rằng `LOCAL_QUORUM` hay RF lớn khiến mọi replica không bao giờ bỏ lỡ mutation.
- Xóa dữ liệu vật lý/khôi phục SSTable tùy tiện khi chưa hiểu tombstone và timestamp.

**An toàn xóa là yêu cầu tính đúng dữ liệu**, không phải chỉ là mục tiêu tiết kiệm đĩa.

## 14. Compaction có giảm chi phí đọc qua tombstone không?

Có thể, nhưng **không tức thì và không vô điều kiện**.

Compaction hợp nhất các phiên bản trong SSTable và có thể loại bỏ một số giá trị bị che hoặc tombstone khi các điều kiện an toàn được đáp ứng. Khi số SSTable chứa cùng partition giảm và các phiên bản lỗi thời được xử lý, read path có thể ít việc hơn.

Tuy nhiên:

1. Tombstone còn trong grace hoặc cần che dữ liệu cũ ở SSTable khác có thể chưa được purge.
2. Compaction tạo tải CPU, disk I/O và cần disk headroom; chạy cưỡng bức không đúng lúc có thể làm p99 production tăng.
3. Dữ liệu ghi/xóa liên tục có thể tạo tombstone mới nhanh hơn tốc độ dọn.
4. Một partition key quá lớn hoặc quá nóng vẫn lớn/nóng sau compaction; compaction **không chia lại partition key**.
5. Compaction strategy phải được chọn theo **kiểu ghi/đọc, update/delete và TTL**, không chỉ vì một lần cảnh báo tombstone.

### STCS, LCS và TWCS ở mức ý tưởng

| Chiến lược | Khía cạnh thường đánh giá | Lưu ý khi có tombstone |
| --- | --- | --- |
| **SizeTieredCompactionStrategy (STCS)** | Nhóm SSTable theo kích thước, phù hợp một số mẫu ghi append/update. | Có thể có nhiều SSTable overlap trước khi được hợp nhất. |
| **LeveledCompactionStrategy (LCS)** | Tổ chức SSTable theo mức với mục tiêu hạn chế overlap cho nhiều kiểu read-heavy. | Đánh đổi write amplification/compaction I/O; không tự xóa tombstone đang cần thiết. |
| **TimeWindowCompactionStrategy (TWCS)** | Dữ liệu time-series append-mostly và TTL gần đồng đều theo cửa sổ thời gian. | Ghi muộn, sửa bản ghi cũ, TTL không đồng đều có thể làm khó thu hồi dữ liệu; không phải lựa chọn mặc định cho mọi bảng. |

Đây là khung tư duy, không thay thế thử tải theo phiên bản Cassandra. TWCS có thể giúp SSTable chứa dữ liệu cùng vòng đời được dọn thuận lợi hơn trong một số workload, nhưng **không hứa hẹn** mọi tombstone hết grace sẽ được xóa ngay.

## 15. Chẩn đoán bằng `nodetool`: nhìn số liệu đúng cấp

Khi nghi một truy vấn đang đọc qua nhiều tombstone, hãy bắt đầu với số liệu ở **bảng và node**:

```bash
nodetool tablestats app_ks.device_events_by_day
nodetool tablehistograms app_ks device_events_by_day
```

Tùy phiên bản Cassandra, các số liệu hữu ích gồm:

| Nhóm metric | Ý nghĩa chẩn đoán |
| --- | --- |
| **Average tombstones per slice** | Mức tombstone được gặp trong các lát đọc đã quan sát, theo thống kê của phiên bản. |
| **Average live cells per slice** | Ước lượng công việc đọc dữ liệu sống; so với tombstones per slice để thấy chênh lệch. |
| **Read latency và SSTables per read** | Read amplification có thể đến từ số nguồn phải merge. |
| **Partition size / cell count histogram** | Tìm phần đuôi lớn và các partition ngoại lệ. |
| **Pending compactions / SSTable count** | Hệ thống nền có đang bắt kịp tốc độ ghi/xóa không? |
| **CPU, disk I/O, network, GC theo replica** | Xác định khả năng quá tải tài nguyên khi query chậm. |
| **Read timeouts/errors và p95/p99 từ ứng dụng** | Đánh giá ảnh hưởng thật đến SLO. |

`tablestats` không tự tạo danh sách đầy đủ `partition_key → số tombstone chính xác`. Các con số có thể là trung bình/histogram tại **node đang hỏi** và phản ánh phạm vi đo khác nhau. Cần ghi rõ node, phiên bản, thời điểm, khoảng quan sát khi so sánh.

Không thể suy số tombstone chỉ từ `COUNT(*)`. Ví dụ:

```sql
-- Chỉ dùng trong lab hoặc khi đã đánh giá chi phí:
SELECT COUNT(*)
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

Câu lệnh này đếm **hàng logic mà truy vấn quan sát**; nó không liệt kê các marker đã xóa trong SSTable và có thể gây tải đáng kể nếu partition quá lớn.

## 16. Tracing một truy vấn đọc bị nghi ngờ

Trong `cqlsh` trên môi trường có kiểm soát, có thể bật tracing quanh **một truy vấn đại diện**:

```sql
TRACING ON;

SELECT occurred_at, event_id, event_kind, payload
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;

TRACING OFF;
```

Trace có thể cung cấp thông tin về các bước replica/coordinator tham gia, thời gian và những dấu hiệu liên quan dữ liệu/tombstone được duyệt, tùy phiên bản và truy vấn. Đọc trace như **bằng chứng về read path**, không coi nó là phép đếm toàn bộ tombstone vật lý.

**Tracing có overhead**, đặc biệt nếu dùng trên nhiều truy vấn production. Chỉ bật cho mẫu nhỏ, với quyền phù hợp, rồi tắt.

### Cảnh báo/ngưỡng tombstone

Một số phiên bản Cassandra có cấu hình như `tombstone_warn_threshold` và `tombstone_failure_threshold`. Chúng có thể giúp phát hiện/tránh các truy vấn đọc phải duyệt quá nhiều tombstone. Tên, mặc định, phạm vi và hành vi chính xác cần được xác nhận trên phiên bản/phân phối đang chạy.

Nếu thấy warning hoặc failure:

1. Xác định **query text và partition key**.
2. Tìm nguồn dấu xóa: cell DELETE, row/range deletion, partition deletion, TTL, NULL/collection replacement.
3. Đo phần dữ liệu sống thực sự được trả về.
4. Kiểm tra clustering range, số SSTable, compaction backlog và tải replica.
5. Thử thay đổi schema/TTL/query trước khi xem xét điều chỉnh ngưỡng.

**Nới ngưỡng không xóa được tombstone**. Nó có thể cho phép query tiếp tục quét thêm marker, tăng tải hoặc latency.

## 17. Quy trình phân tích nguyên nhân có thể lặp lại

Một ca điển hình: dashboard cần 20 event gần nhất nhưng thỉnh thoảng timeout.

| Bước | Kiểm tra | Kết luận có thể đưa ra |
| --- | --- | --- |
| 1 | Query có đủ partition key không? | Phân biệt single-partition read với quét nhiều partition. |
| 2 | Khoảng clustering và `LIMIT` thế nào? | Có thể cần duyệt quá rộng hoặc quá nhiều hàng đã xóa. |
| 3 | Response có bao nhiêu hàng sống? | Phân biệt ít kết quả với ít công việc đọc. |
| 4 | Tracing/metric có tombstones per slice cao không? | Xác định read path thực sự gặp nhiều dấu xóa. |
| 5 | SSTables per read, compaction pending ra sao? | Xem chi phí merge do nhiều SSTable/phiên bản. |
| 6 | Source deletion/TTL là gì? | Tìm nguyên nhân sinh tombstone, không chỉ triệu chứng. |
| 7 | Replica, RF, CL và repair có gì bất thường? | Kiểm tra sai khác phiên bản và điểm nghẽn mạng/replica. |
| 8 | Thử cải thiện query/partition/bucket/TTL ở workload giống production | Xác nhận p95/p99, timeout và tính đúng dữ liệu sau sửa. |

Một giả thuyết **phải được kiểm chứng**: “Đầu dải clustering vừa bị xóa nhiều hàng nên query LIMIT 20 phải quét sâu.” Nếu trace cho thấy ít tombstone nhưng nhiều SSTables per read hoặc node disk I/O cao, nguyên nhân có thể khác. Đừng khẳng định tombstone là thủ phạm chỉ vì bảng có TTL.

## 18. Thiết kế để giảm đọc qua dấu xóa

Có ba hướng xử lý chính: **giảm phạm vi truy vấn**, **giảm tốc độ sinh dấu xóa không cần thiết**, và **cải thiện vòng đời dữ liệu trên SSTable**.

### 18.1. Thu hẹp partition key và clustering range

Nếu mọi sự kiện của thiết bị tích lũy trong một partition nhiều tháng:

```sql
-- Ví dụ khóa khiến toàn bộ lịch sử một thiết bị cùng một partition:
PRIMARY KEY ((tenant_id, device_id), occurred_at, event_id)
```

Thêm time bucket ngày/giờ giúp cô lập lịch sử thành các partition nhỏ hơn:

```sql
-- Ví dụ khóa theo ngày:
PRIMARY KEY (
    (tenant_id, device_id, event_day),
    occurred_at, event_id
)
```

Đây không chỉ là thay `WHERE`: đổi partition key cần tạo **bảng mới và migration**. Tầng đọc phải biết bucket và lập kế hoạch fan-out khi truy vấn qua nhiều ngày.

**Bucket không tự xóa tombstone**, nhưng giới hạn lượng dữ liệu và marker mà một truy vấn theo ngày phải xét. Nếu một ngày vẫn ghi quá dày, bucket giờ hoặc shard có thể phù hợp hơn; cần cân nhắc chi phí truy vấn nhiều partition.

### 18.2. Tránh tạo tombstone ngoài ý muốn

- Đừng tự động bind `null` cho mọi trường không có trong API PATCH; phân biệt **absent/UNSET** với **explicit delete**.
- Không thực hiện hàng triệu lệnh xóa riêng lẻ khi có mô hình vòng đời tốt hơn và phạm vi nghiệp vụ cho phép.
- Không dùng collection không frozen rất lớn rồi liên tục thay toàn bộ collection; xem xét các cập nhật theo phần tử hoặc bảng con theo truy vấn.
- Cân nhắc TTL hợp lý thay vì vừa TTL rất ngắn vừa quét thường xuyên một dải toàn giá trị đã hết hạn.
- Không tái tạo `event_id` hoặc time bucket khi retry, vì có thể sinh thêm hàng không mong muốn.

### 18.3. Tổ chức TTL và compaction phù hợp

Với dữ liệu time-series append-mostly có TTL/retention tương đối đồng đều, có thể đánh giá TWCS và tổ chức time bucket theo vòng đời dữ liệu. Khi có dữ liệu đến trễ, update/xóa thường xuyên hoặc nhiều TTL khác nhau, cần kiểm thử kỹ vì các giả định của compaction strategy có thể không phù hợp.

Không giảm `gc_grace_seconds` tùy tiện. Bất kỳ thay đổi nào liên quan thu hồi tombstone phải xét tính an toàn repair/replica và nguy cơ zombie data.

### 18.4. Phục vụ truy vấn top-N bằng một đường dữ liệu thích hợp

Nếu dashboard luôn muốn “20 event sống mới nhất” nhưng nguồn lưu thô có hàng triệu sự kiện TTL rất ngắn hoặc bị xóa hàng loạt, có thể cân nhắc **bảng phục vụ truy vấn** hoặc cơ chế tổng hợp/định tuyến riêng theo yêu cầu sản phẩm. Tuy nhiên, bảng phụ phải có quy tắc đồng bộ cập nhật/xóa, TTL và xử lý partial failure; nó không tự được cập nhật nguyên tử chỉ vì cùng tenant.

## 19. Java Driver 4.x: đọc một slice có giới hạn

Repository dưới đây truy vấn **một partition ngày** với **đoạn clustering cụ thể**. Ví dụ dùng Java Driver 4.x và giả định `CqlSession` đã kết nối với keyspace chứa bảng `device_events_by_day`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class DeviceEventReader {
    private final CqlSession session;
    private final PreparedStatement byDayRange;

    public DeviceEventReader(CqlSession session) {
        this.session = session;
        this.byDayRange = session.prepare(
            "SELECT occurred_at, event_id, event_kind, payload " +
            "FROM device_events_by_day " +
            "WHERE tenant_id = ? AND device_id = ? AND event_day = ? " +
            "AND occurred_at >= ? AND occurred_at < ? LIMIT ?"
        );
    }

    // Chỉ đọc một ngày UTC, trả tối đa limit hàng sống.
    public List<EventRow> readSlice(
            String verifiedTenantId,
            UUID deviceId,
            Instant startInclusive,
            Instant endExclusive,
            int limit) {

        if (limit < 1 || limit > 200) {
            throw new IllegalArgumentException("limit must be 1..200");
        }
        if (!startInclusive.isBefore(endExclusive)) {
            throw new IllegalArgumentException("empty time range");
        }

        LocalDate day = startInclusive.atZone(ZoneOffset.UTC).toLocalDate();
        LocalDate lastDay = endExclusive.minusNanos(1)
            .atZone(ZoneOffset.UTC).toLocalDate();

        if (!day.equals(lastDay)) {
            throw new IllegalArgumentException(
                "range must stay inside one UTC day");
        }

        BoundStatement statement = byDayRange.bind(
            verifiedTenantId,
            deviceId,
            day,
            startInclusive,
            endExclusive,
            limit
        ).setPageSize(50);

        List<EventRow> events = new ArrayList<>();

        for (Row row : session.execute(statement)) {
            events.add(new EventRow(
                row.getInstant("occurred_at"),
                row.getUuid("event_id"),
                row.getString("event_kind"),
                row.getString("payload")
            ));
        }

        return events;
    }

    public static final class EventRow {
        public final Instant occurredAt;
        public final UUID eventId;
        public final String eventKind;
        public final String payload;

        EventRow(Instant occurredAt, UUID eventId,
                 String eventKind, String payload) {
            this.occurredAt = occurredAt;
            this.eventId = eventId;
            this.eventKind = eventKind;
            this.payload = payload;
        }
    }
}
```

### Điều đoạn mã làm được

1. Bind đủ **partition key** (`tenant_id`, `device_id`, `event_day`) và khoảng clustering.
2. Tính bucket ngày UTC từ thời điểm đầu; bảo đảm khoảng đóng–mở nằm trong **một ngày**.
3. Giới hạn số hàng **logic trả về** bằng `LIMIT ?` tối đa 200 theo policy minh họa.
4. Dùng page size 50 để tránh yêu cầu một phản hồi quá lớn.
5. Phân biệt `payload == null` là **không thấy giá trị sống hiện hành**; code không tự kết luận vì tombstone hay TTL.

### Điều đoạn mã không giải quyết

- Nó **không ép Cassandra chỉ đọc tối đa 200 tombstone**; workload có dải xóa dày vẫn có thể chậm.
- Kích thước trang 50 không xóa tombstone hoặc giảm số bản sao dữ liệu cũ trên SSTable.
- Truy vấn nhiều ngày phải lập danh sách bucket, đọc các partition liên quan và merge theo `occurred_at DESC, event_id ASC`.
- Một API gọi nhiều bucket/shard cần **giới hạn concurrency/backpressure**; fan-out vô hạn có thể biến một truy vấn chậm thành nhiều truy vấn chậm.
- `verifiedTenantId` phải đến từ ngữ cảnh đã xác thực/ủy quyền; đưa tenant ID vào khóa không tự cung cấp row-level security.

Nếu cần xác minh performance, ứng dụng nên đo thời gian **first page**, **total fetch**, số hàng trả về, p95/p99 và correlation/tracing có kiểm soát. Không log payload hoặc định danh nhạy cảm tùy tiện để chẩn đoán.

## 20. Lab: tạo dữ liệu sống, xóa, TTL và quan sát read path

Mục đích thí nghiệm là **quan sát ngữ nghĩa logic và dấu hiệu vận hành** — không giả định một câu DELETE nhỏ sẽ làm metrics thay đổi rõ trên bảng production.

### Bước 1 — Tạo bảng lab và ba hàng

Dùng schema `device_events_by_day` ở phần 3 trong một keyspace thử nghiệm, ghi ba hàng với cùng partition key. Đọc lại:

```sql
SELECT occurred_at, event_id, event_kind, payload
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 10;
```

Kết quả ban đầu có ba sự kiện; thứ tự theo `occurred_at DESC`.

### Bước 2 — So sánh cell deletion và row deletion

**Lượt A:** xóa `payload` của E2 bằng câu `DELETE payload` ở phần 4 rồi đọc lại. E2 có thể còn được trả về vì `event_kind` và `source_app` vẫn sống.

**Lượt B:** khởi tạo lại dữ liệu mẫu, sau đó xóa cả E2 bằng `DELETE FROM ... WHERE full_primary_key` ở phần 5. E2 không còn là hàng sống được trả về theo trạng thái xóa đã được quan sát.

**Đừng dùng một lượt xóa cell rồi xóa row để suy ra sự khác biệt nếu không kiểm tra trạng thái trung gian.**

### Bước 3 — Ghi một cell có TTL

Chạy `INSERT ... USING TTL 60` ở phần 11 trên **một hàng khác**. Kiểm tra `TTL(payload)` khi giá trị còn sống. Sau khi TTL hết hạn trong môi trường lab, kiểm tra lại: payload không còn được xem là sống.

Không kết luận “TTL không hoạt động” chỉ vì dung lượng SSTable không giảm tức thì.

### Bước 4 — Xem traces và thống kê

Bật tracing **chỉ cho một vài query** như phần 16. Sau đó đọc `nodetool tablestats` và `tablehistograms` nếu có quyền vận hành lab.

Một thí nghiệm chỉ vài hàng **không đủ** để tái hiện warning tombstone hay thay đổi histogram đáng kể. Muốn đo hiệu năng, phải có generator workload kiểm soát được tỷ lệ DELETE/TTL, clustering range, số SSTable và tải đọc/ghi, và chạy trong môi trường thử nghiệm chứ không tạo thêm tải vào production.

### Bước 5 — Tạo một giả thuyết và kiểm chứng

Ví dụ:

> “Khi 90% sự kiện mới nhất trong một partition đã hết TTL, query lấy 20 sự kiện sống mới nhất sẽ phải xét nhiều dữ liệu hơn.”

Thay đổi **một yếu tố một lần** (tỷ lệ hết TTL, kích thước partition, page size, compaction strategy hoặc độ rộng range), đo p95/p99 và traces. Mục tiêu là chứng minh **nguyên nhân read amplification** chứ không chỉ đo một query chậm ngẫu nhiên.

## 21. Tình huống định lượng: ít kết quả, nhiều tombstone

Một dịch vụ IoT có một thiết bị tạo **200 sự kiện/giây**. Payload trung bình **400 byte/event**. Thiết kế ban đầu:

```sql
PRIMARY KEY (
    (tenant_id, device_id),
    occurred_at, event_id
)
```

Tất cả sự kiện của một thiết bị đi vào **một partition logic**. Trong một ngày ghi liên tục:

```text
200 event/s × 86.400 s = 17.280.000 hàng/ngày

Payload logic/ngày:
17.280.000 × 400 byte
= 6.912.000.000 byte ≈ 6,44 GiB
```

Giả sử một tác vụ nghiệp vụ xóa nhiều sự kiện gần nhất trong cùng partition, khiến chỉ **một phần nhỏ** các hàng gần đầu clustering range còn sống. Truy vấn:

```sql
SELECT occurred_at, event_id, event_kind
FROM device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

Có thể phải xét qua một dải lớn các hàng/tombstone để tìm 20 hàng hợp lệ. Đây là rủi ro do **hình dạng dữ liệu và nguồn tạo tombstone**, không phải vì Cassandra “quên” thực hiện DELETE.

Cần lưu ý ví dụ trên dùng hai schema để so sánh: thiết kế **không bucket** tạo một partition lịch sử lớn, còn truy vấn CQL đang minh họa thiết kế **có `event_day`**. Mặc dù bucket ngày giảm kích thước tương đối, **17.280.000 hàng trong một ngày** vẫn có thể lớn hoặc nóng; muốn áp dụng vào hệ thống thật cần thử bucket giờ/phút và giới hạn truy vấn phù hợp.

### Nếu chọn bucket 5 phút

```text
200 event/s × 300 s = 60.000 hàng/bucket

Payload logic:
60.000 × 400 byte = 24.000.000 byte ≈ 22,9 MiB
```

Bucket 5 phút giảm kích thước một partition theo giả định lưu lượng, nhưng truy vấn lịch sử 24 giờ có thể cần tới **288–289 bucket**, tùy ranh giới. Nó cũng không tự xử lý mọi tombstone phát sinh trong bucket đang hoạt động.

**Đánh đổi:** giảm kích thước/phạm vi đọc trong từng partition, tăng số partition lookup và chi phí merge khi truy vấn qua thời gian dài. Không chọn bucket mới chỉ dựa trên số hàng; phải đo p95/p99, read amplification, write hotspot và fan-out.

## 22. Các hiểu lầm cần loại bỏ

| Khẳng định | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “DELETE đã thành công nên dữ liệu cũ không còn trong SSTable.” | DELETE ghi tombstone logic; thu hồi vật lý là bước sau. | Phân biệt kết quả đọc và footprint trên đĩa. |
| “Có LIMIT 20 nên replica chỉ xét 20 cell.” | Nhiều cell/row/tombstone có thể bị bỏ qua trước khi có 20 hàng sống. | Đo scanned tombstones và clustering range. |
| “Paging sẽ dọn tombstone qua từng trang.” | Paging chỉ chia kết quả và tiếp tục truy vấn. | Dùng paging cho bộ nhớ/mạng, không coi là GC. |
| “COUNT(*) cho biết số tombstone.” | Đếm hàng logic, không đếm marker vật lý. | Dùng metrics/tracing/công cụ SSTable phù hợp. |
| “Mỗi SELECT luôn quét mọi SSTable từ đầu đến cuối.” | Cassandra có filter/index/cache và định vị partition/slice. | Chi phí tùy SSTables liên quan, tombstone và phạm vi query. |
| “Tăng RF hoặc LOCAL_QUORUM sẽ xóa tombstone nhanh hơn.” | RF/CL liên quan replica và xác nhận, không purge tombstone. | Xem compaction, repair, retention và schema. |
| “Cứ chạy repair là compaction tự dọn tất cả tombstone.” | Repair đồng bộ replica, không thay thế điều kiện purge. | Theo dõi grace, overlap, compaction và phiên bản. |
| “Giảm gc_grace_seconds luôn giảm latency mà không có rủi ro.” | Có thể tăng nguy cơ zombie data. | Đặt chính sách theo repair và thời gian replica có thể vắng mặt. |
| “TWCS là cách chữa mọi query có tombstone.” | Có các giả định về kiểu ghi/TTL, không đổi partition key. | Benchmark với workload thực. |
| “Một partition nhỏ không thể bị read amplification.” | TTL/xóa dày, nhiều SSTable vẫn gây tốn đọc. | Đo lượng marker/byte phải xét. |
| “Tombstone chính là giá trị NULL đọc được.” | NULL có thể là chưa từng ghi hoặc đã bị xóa/hết TTL. | Không suy nguyên nhân từ SELECT null. |
| “Quét toàn tenant bằng ALLOW FILTERING giải quyết query chậm.” | Có thể tăng số partition/cell phải xét. | Thiết kế bảng theo truy vấn/khóa đầy đủ. |

## 23. Bài tập và đáp án

Một ứng dụng theo dõi phiên hoạt động có bảng:

```sql
CREATE TABLE activities_by_user_day (
    tenant_id   text,
    user_id     uuid,
    activity_day date,
    occurred_at timestamp,
    activity_id uuid,
    action      text,
    details     text,
    PRIMARY KEY (
        (tenant_id, user_id, activity_day),
        occurred_at, activity_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC, activity_id ASC
);
```

Trong một ngày, người dùng U tạo **50.000 hàng**. Một tác vụ xóa 30.000 hàng gần đây, 10.000 hàng khác mang TTL ngắn và đã hết hạn. Dashboard muốn **20 hoạt động sống mới nhất**.

**Câu hỏi:**

1. Partition key của bảng là gì? `occurred_at` có làm thay đổi token khi tăng không?
2. Nếu `SELECT ... LIMIT 20` trả đúng 20 hàng, có chứng minh replica chỉ đọc 20 hàng không?
3. Vì sao một tombstone trên memtable có thể che giá trị trên SSTable cũ?
4. Khi đọc từ nhiều SSTable, replica phải dựa vào thông tin gì để quyết định một cell còn sống?
5. Hòa giải trong một replica khác hòa giải giữa các replica ở điểm nào?
6. Nếu `details` bị DELETE nhưng `action` còn sống, cả hàng có nhất thiết biến mất không?
7. Nếu 10.000 hàng có cell hết TTL, ứng dụng có phải phát 10.000 lệnh DELETE tại thời điểm hết hạn không?
8. Chạy `COUNT(*)` sẽ cho số tombstone trong partition hay không?
9. Page size 50 làm số lượng tombstone Cassandra phải xét tối đa là 50 hay không?
10. Hai nguyên nhân khác ngoài tombstone khiến p99 của SELECT tăng là gì?
11. Nếu một replica offline khi DELETE được ghi và quay lại sau khi tombstone đã bị purge không an toàn, có rủi ro gì?
12. Một biện pháp ở **mức schema** và một biện pháp ở **mức mutation/query** để giảm read amplification là gì?
13. Nếu 1.000 sự kiện mới nhất đều bị xóa, việc chọn `CLUSTERING ORDER BY DESC` có bảo đảm truy vấn lấy 20 hàng mới nhất nhanh không?
14. Vì sao không nên khắc phục ngay bằng cách tăng `tombstone_failure_threshold`?
15. Khi đánh giá chiến lược compaction, phải xem thêm yếu tố nào ngoài số tombstone hiện tại?

**Đáp án giải thích:**

1. `(tenant_id, user_id, activity_day)` là partition key ghép; `occurred_at` là clustering column, không tham gia tính token.
2. **Không.** LIMIT ràng buộc kết quả sống, không giới hạn chính xác số cell/tombstone/SSTable cần xét.
3. Vì tombstone có write timestamp mới hơn có thể che giá trị cũ trong quá trình merge.
4. Cần hòa giải theo partition/clustering key, write timestamp, tombstone, TTL và quy tắc liveness/xung đột.
5. Replica merge các nguồn dữ liệu cục bộ; coordinator xử lý phản hồi/sai khác giữa replica theo read protocol và consistency.
6. **Không.** Xóa một regular column không đồng nghĩa row deletion nếu hàng vẫn có dữ liệu sống phù hợp.
7. **Không.** Giá trị mang TTL tự hết hạn theo thông tin lưu trữ, được xem như dữ liệu đã xóa khi đọc.
8. **Không.** COUNT(*) đếm hàng logic được truy vấn nhìn thấy, không liệt kê marker vật lý.
9. **Không.** Page size liên quan số hàng trang kết quả, không giới hạn tombstone scan nội bộ.
10. Ví dụ: nhiều SSTable cùng chứa partition, disk I/O cao, replica/coordinator quá tải, mạng chậm hoặc compaction đang chạy.
11. Có nguy cơ **zombie data** vì bản cũ ở replica chậm có thể xuất hiện lại.
12. Schema: chia bucket theo thời gian/đường truy vấn. Mutation/query: không ghi NULL ngoài ý muốn, giảm DELETE lẻ hoặc thu hẹp khoảng clustering.
13. **Không.** Cassandra có thể phải xét 1.000 vị trí bị xóa trước khi tìm được hàng sống.
14. Nới ngưỡng có thể che triệu chứng và khiến query tiêu tốn nhiều CPU/I/O hơn; cần tìm nguồn tombstone trước.
15. Cần xem TTL/retention, update/delete pattern, SSTable overlap, dữ liệu đến trễ, repair/grace, I/O, tải và phiên bản Cassandra.

## 24. Checklist xử lý một truy vấn đọc qua nhiều dấu xóa

- [ ] Xác định **đúng full partition key** và clustering range của truy vấn chậm.
- [ ] So sánh số hàng **trả về** với số tombstone/dữ liệu được quét qua tracing hoặc metrics.
- [ ] Phân biệt tombstone từ **DELETE cell/row/range/partition**, NULL, collection hay TTL.
- [ ] Đo p95/p99, timeout, SSTables per read, CPU/I/O, compaction backlog và các outlier keys.
- [ ] Kiểm tra liệu truy vấn đang đọc **một partition**, nhiều bucket hay fan-out nhiều shard.
- [ ] Không dùng `COUNT(*)`/quét toàn bảng để đo số tombstone trên production.
- [ ] Đối chiếu consistency level, replica health và lịch repair khi có dữ liệu cũ/sai khác replica.
- [ ] Không hạ `gc_grace_seconds` tùy tiện hoặc ép compaction quy mô lớn khi chưa hiểu điều kiện an toàn.
- [ ] Kiểm tra TTL, sự kiện đến trễ, update/delete pattern và mức đồng đều của vòng đời dữ liệu.
- [ ] Thử thiết kế partition key/bucket, clustering range và đường truy vấn hợp lý ở workload đại diện.
- [ ] Dùng Java prepared statements, paging, giới hạn kết quả, bounded concurrency và tính bucket UTC nhất quán.
- [ ] Xác nhận **tính đúng dữ liệu** sau mọi thay đổi: DELETE có còn hiệu lực, có tombstone/zombie data, có thiếu dữ liệu khi fan-out hay không.
- [ ] Chỉ kết luận đã xử lý khi độ trễ, tải replica và khả năng thu hồi đều đạt tiêu chí kiểm chứng.

## 25. Ghi nhớ

- Đọc Cassandra là quá trình **định vị partition và slice**, hợp nhất dữ liệu từ memtable/SSTable, áp dụng write timestamp, tombstone, TTL và trả các hàng còn sống.
- **Tombstone tồn tại để bảo vệ ngữ nghĩa xóa** trong môi trường có nhiều SSTable và replica; không thể bỏ qua dấu xóa chỉ vì muốn đọc nhanh.
- **Read amplification** xuất hiện khi chi phí merge/scan cao hơn nhiều so với dữ liệu hữu ích. Một kết quả 20 hàng có thể đòi hỏi xét rất nhiều tombstone.
- **`LIMIT` và paging** giới hạn lượng dữ liệu trả về, không thu nhỏ partition hay dọn tombstone.
- **Replica merge cục bộ** khác **coordinator hòa giải giữa replica**; repair và compaction có chức năng riêng, không thay thế nhau.
- **TTL hết hạn** làm cell không còn sống mà không cần mutation DELETE mới, nhưng dấu xóa/dữ liệu cũ có thể tồn tại trên SSTable đến khi được thu hồi an toàn.
- **`gc_grace_seconds`, SSTable overlap và repair** quyết định an toàn của tombstone reclamation; giảm grace vô căn cứ có thể dẫn đến zombie data.
- **Thay đổi schema/partition key, clustering range, mutation pattern và vòng đời TTL** thường bền vững hơn việc chỉ nới ngưỡng tombstone.
- Sử dụng **metrics, tracing, histogram và benchmark** để giải thích p99 và chứng minh cải thiện, thay vì kết luận từ số hàng SELECT trả về.

Hiểu được công việc Cassandra thực hiện **trước khi trả những hàng còn sống** là nền tảng để chẩn đoán truy vấn chậm vì tombstone. Nó giúp bạn thiết kế bảng wide-column theo truy vấn, chọn mức nhất quán hợp lý, phối hợp compaction và repair an toàn, đồng thời viết ứng dụng Java có kiểm soát tài nguyên và hành vi khi dữ liệu bị xóa hoặc hết hạn.

