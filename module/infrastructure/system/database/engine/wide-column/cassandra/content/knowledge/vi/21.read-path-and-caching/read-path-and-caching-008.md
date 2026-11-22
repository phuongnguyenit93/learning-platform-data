# Đọc gặp nhiều SSTable, tombstone và dữ liệu phân mảnh trong Apache Cassandra

## 1. Vấn đề: trả vài dòng nhưng phải đọc rất nhiều dữ liệu

Trong Apache Cassandra, cơ sở dữ liệu phân tán kiểu **wide-column**, ứng dụng thường đọc bằng **partition key** và một dải **clustering key**. Thiết kế bảng theo truy vấn giúp định tuyến nhanh đến replica, nhưng **đến đúng partition không có nghĩa chỉ cần đọc một tệp hoặc một phiên bản dữ liệu**.

Cùng một partition có thể được cập nhật qua nhiều lần flush. Dữ liệu của nó xuất hiện ở **memtable** đang hoạt động và nhiều **SSTable** bất biến trên đĩa. Các lần cập nhật, xóa và hết hạn TTL còn sinh ra **tombstone**. Khi xử lý truy vấn, Cassandra phải tìm các nguồn chứa partition, kết hợp những bản ghi/tombstone theo thứ tự và timestamp phù hợp, rồi mới trả về hàng còn hiệu lực.

Một trường hợp điển hình:

- Ứng dụng yêu cầu `LIMIT 20` sự kiện mới nhất của thiết bị.
- Partition của thiết bị nằm trên nhiều SSTable do ghi liên tục và compaction chưa gom xong.
- Nhiều hàng mới đã hết hạn TTL hoặc bị xóa nên còn tombstone.
- Cassandra có thể phải đọc, đối chiếu và bỏ qua rất nhiều entry trước khi tìm được 20 hàng sống.

Đây là **read amplification**: lượng dữ liệu và thao tác phải xử lý lớn hơn nhiều so với kết quả ứng dụng cần. Nó có thể làm tăng độ trễ đọc p95/p99, số lần truy cập đĩa, CPU, bộ nhớ tạm và tải compaction.

Mục tiêu bài học trong chương **Đường đọc và bộ đệm** là hiểu nguyên nhân của hiện tượng này, phân biệt **nhiều SSTable**, **tombstone** và **dữ liệu phân mảnh**, rồi chọn cách đo, tối ưu CQL, mô hình partition và vận hành an toàn.

## 2. Những thành phần có thể tham gia một lần đọc

### 2.1. Các lớp lưu trữ cần biết

| Thành phần | Vai trò đối với đường đọc |
|---|---|
| **Memtable** | Chứa mutation chưa flush; dữ liệu mới ở RAM cũng phải được xét khi đọc |
| **SSTable** | Tệp bất biến được tạo sau flush hoặc compaction; một partition có thể xuất hiện trong nhiều SSTable |
| **Bloom filter** | Trả lời nhanh “partition chắc chắn không có trong SSTable này” hoặc “có thể có”; trường hợp có thể có vẫn phải kiểm tra tiếp |
| **Partition key cache / key cache** | Giảm công tìm vị trí partition trong SSTable khi khóa được cache; không tự loại bỏ việc đọc dữ liệu |
| **Index summary và partition index** | Hỗ trợ tìm offset trên SSTable, giảm số lần dò đĩa |
| **Compression metadata/chunk** | Hỗ trợ truy cập các đoạn dữ liệu nén thích hợp; có thể cần giải nén chunk dù chỉ lấy một phần dữ liệu |
| **Row cache** (nếu bật) | Có thể phục vụ một số lần đọc từ cache; hữu ích tùy workload và chiến lược cập nhật |

**Lưu ý:** Bloom filter **âm tính** loại trừ SSTable cho một partition; **dương tính** chỉ nói *có thể chứa*, bởi có xác suất dương tính giả. Bloom filter giúp giảm SSTable không liên quan, nhưng **không xóa bản ghi cũ, tombstone hay số phiên bản hợp lệ** của partition.

### 2.2. Luồng đọc từ client tới replica

~~~mermaid
flowchart TD
    A["Ứng dụng Java / CQL"] --> B["Coordinator: chọn replica theo partition key và read CL"]
    B --> C["Replica: kiểm tra bộ đệm và memtable"]
    C --> D["Xác định SSTable ứng viên theo metadata / Bloom filter"]
    D --> E["Đọc index và chunk dữ liệu cần thiết"]
    E --> F["Hợp nhất phiên bản, TTL và tombstone"]
    F --> G["Trả hàng còn hiệu lực / digest tới coordinator"]
    G --> H["Coordinator đối chiếu replica theo read CL"]
    H --> I["Trả kết quả cho ứng dụng"]
~~~

Đây là mô hình **khái niệm**. Trong thực tế, replica có thể có tối ưu đọc và thứ tự truy cập khác nhau tùy phiên bản Cassandra, cache, partition index, clustering filter và compaction strategy. Coordinator cũng có thể dùng data/digest request, đối chiếu khác biệt và những cơ chế đọc bổ sung tùy phiên bản.

Với truy vấn đã có đủ khóa định tuyến, nút thắt có thể nằm **bên trong replica**, khi phải hợp nhất nhiều phiên bản/tombstone. Tăng read consistency level không xóa được việc xử lý những nguồn dữ liệu cục bộ đó.

## 3. Tại sao một partition trải trên nhiều SSTable?

SSTable bất biến sau khi tạo. Một lần ghi mới lên khóa đã tồn tại **không sửa trực tiếp SSTable cũ**; mutation mới được ghi qua commit log/memtable, rồi được flush thành SSTable mới. Compaction về sau mới hợp nhất những tệp thích hợp.

Ví dụ một partition `device_id = D`:

| Thời điểm | Mutation | Nơi lưu có thể gặp khi đọc |
|---|---|---|
| `t0` | Ghi sensor sample 1–100 | SSTable A sau flush |
| `t1` | Ghi sample 101–200 | SSTable B |
| `t2` | Cập nhật sample 125 | SSTable C chứa phiên bản mới |
| `t3` | Xóa sample 80 | SSTable D chứa tombstone |
| `t4` | Thêm sample 201–230 | Memtable hoặc SSTable E |

Một SELECT đụng tới cùng partition có thể phải tham khảo cả A, B, C, D, E. Cassandra cần xác định giá trị hợp lệ theo timestamp và tombstone; không thể chỉ trả hàng nhìn thấy ở một SSTable bất kỳ.

**Dữ liệu phân mảnh** trong bài này nghĩa là **các hàng, phiên bản hoặc dấu xóa của cùng partition nằm rải trên nhiều SSTable và vùng lưu trữ**, không nhất thiết nghĩa là phân mảnh block của hệ thống tệp. Các nguyên nhân hay gặp:

1. Ghi đều đặn tạo nhiều lần flush; nhiều SSTable chưa được compact.
2. Cập nhật thường xuyên cùng partition/cell sinh nhiều phiên bản.
3. Tombstone từ `DELETE` hoặc TTL nằm trong SSTable khác với dữ liệu cũ.
4. Compaction chậm hơn tốc độ ghi hoặc cấu hình strategy không phù hợp.
5. Partition quá lớn, phạm vi clustering rộng và dữ liệu bị đọc qua nhiều chunk.
6. Ghi trễ/out-of-order vào dữ liệu cũ (đặc biệt với bảng thời gian) khiến SSTable thuộc các thời điểm khác nhau cùng chứa partition liên quan.

Dữ liệu phân mảnh là đặc điểm có thể xảy ra của kiến trúc LSM; điều cần kiểm soát là **chi phí đọc thực tế** và khả năng compaction theo kịp.

## 4. Tombstone là gì và vì sao đường đọc phải xét chúng?

Cassandra không thể coi xóa dữ liệu là lập tức xóa sạch mọi bản sao cũ. Thay vào đó, xóa thường được biểu diễn bằng **tombstone**, một dấu ghi có metadata thời gian để che những giá trị cũ tương ứng.

Tombstone có thể xuất hiện từ:

- `DELETE` một cell, một row hoặc cả partition.
- `UPDATE` đặt một cột thành `null` trong ngữ cảnh CQL phù hợp.
- TTL của cell hoặc row hết hạn: dữ liệu hết hiệu lực và cần được xử lý như đã xóa.
- Thao tác xóa phần tử/range hay thay thế một số kiểu collection, tùy mô hình dữ liệu và CQL.

Ví dụ:

~~~cql
CREATE TABLE demo.readings_by_device (
    device_id uuid,
    observed_at timestamp,
    value double,
    PRIMARY KEY (device_id, observed_at)
);

INSERT INTO demo.readings_by_device (device_id, observed_at, value)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21T08:00:00Z',
    36.5
);

DELETE FROM demo.readings_by_device
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND observed_at = '2026-11-21T08:00:00Z';
~~~

Lệnh `DELETE` tạo dấu xóa. Nếu một SSTable cũ vẫn chứa `value=36.5`, đường đọc phải **xét tombstone** để tránh trả lại dữ liệu đã bị xóa. Chỉ bỏ qua SSTable chứa tombstone có thể làm giá trị cũ xuất hiện trở lại.

### 4.1. Tombstone có nhiều phạm vi

| Loại/phạm vi | Ý nghĩa trên đường đọc |
|---|---|
| **Cell tombstone** | Che giá trị một cột/cell cũ |
| **Row tombstone** | Che row theo khóa clustering tương ứng |
| **Range tombstone** | Che một dải row theo clustering; phạm vi quét có thể giao với nhiều dữ liệu sống |
| **Partition tombstone** | Che dữ liệu cũ trong toàn bộ partition |

Chi tiết lưu trữ và hiển thị tombstone phụ thuộc phiên bản Cassandra. Điểm chung là **đọc phải hòa giải cả dữ liệu còn sống lẫn dấu xóa**, không thể đơn giản coi tombstone như hàng trả về client.

### 4.2. Vì sao `LIMIT 10` vẫn có thể quét rất nhiều?

Giả sử partition có 5.000 entry theo thứ tự đọc, nhưng 4.900 entry đầu đã bị xóa/hết TTL. Truy vấn `LIMIT 10` không trả 4.900 entry đó; Cassandra vẫn có thể phải duyệt qua dấu xóa và giá trị liên quan để tìm 10 row hợp lệ.

Sơ đồ minh họa:

~~~text
Bộ quét tại replica:
[T][T][T][T][T] ... [T] [LIVE-1] [LIVE-2] ... [LIVE-10]
 \_______________/
    Rất nhiều tombstone

Ứng dụng chỉ nhìn thấy 10 row sống.
~~~

Hệ quả có thể là **tombstone scan**, độ trễ tăng, bộ nhớ/chunk đọc tăng và, khi vượt ngưỡng bảo vệ theo cấu hình/phiên bản, Cassandra có thể ghi cảnh báo hoặc từ chối truy vấn. Một `LIMIT` nhỏ **không bảo đảm khối lượng quét nhỏ**.

### 4.3. TTL không đồng nghĩa “tự dọn sạch ngay”

Ví dụ:

~~~cql
INSERT INTO demo.readings_by_device (device_id, observed_at, value)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21T08:05:00Z',
    37.0
)
USING TTL 86400;
~~~

Sau TTL 86.400 giây, dữ liệu không còn hiệu lực cho truy vấn bình thường, nhưng quá trình thu hồi không nhất thiết xảy ra ngay tại thời điểm hết hạn. Thông tin xóa/hết hạn còn phải được giữ và xử lý an toàn qua compaction, theo điều kiện đủ để không làm hồi sinh dữ liệu cũ.

Vì thế “bảng chỉ giữ dữ liệu 24 giờ” **không có nghĩa** sau 24 giờ ổ đĩa không còn dấu vết vật lý của dữ liệu hay truy vấn sẽ không gặp tombstone.

## 5. Ba nguồn read amplification cộng hưởng như thế nào?

Có thể phân tích một lần đọc theo ba trục:

**(A) Nhiều SSTable ứng viên:** replica phải kiểm tra metadata/index và có thể đọc dữ liệu ở nhiều tệp để dựng phiên bản hợp lệ.

**(B) Nhiều tombstone trong phạm vi truy vấn:** bộ quét phải xem nhiều dấu xóa trước khi tìm thấy row còn sống; số hàng trả về nhỏ không phản ánh lượng công việc đã làm.

**(C) Partition hoặc dải clustering lớn, nhiều phiên bản:** đọc qua nhiều block/chunk và đối chiếu nhiều mutation trên cùng khóa; cache ít hiệu quả hơn nếu tập dữ liệu nóng quá lớn.

Ví dụ minh họa (không phải số đo mặc định của Cassandra):

| Chỉ số | Truy vấn khỏe | Truy vấn gặp vấn đề |
|---|---:|---:|
| SSTable cần xét ở một replica | 2 | 14 |
| Entry/tombstone phải xem xét | 40 | 8.000 |
| Hàng hợp lệ trả về | 20 | 20 |
| Dữ liệu phân bố trong partition | Vài chunk | Nhiều chunk rải giữa các SSTable |

Hai truy vấn cùng trả 20 hàng, nhưng khối lượng làm việc có thể chênh lệch lớn. Con số thực tế cần được xác nhận bằng **metrics và tracing**, không suy từ `LIMIT` hay tổng số SSTable của bảng.

### Một công thức tư duy

Có thể coi chi phí đọc tăng theo số SSTable liên quan, số entry/tombstone phải quét, lượng dữ liệu cần giải nén/đối chiếu và số replica cần liên hệ. Đây là **các yếu tố giải thích**, không phải một công thức tính latency tuyến tính có thể dùng để dự báo chính xác.

Khi CPU thấp nhưng p99 đọc cao, hãy kiểm tra disk I/O và SSTable/chunk access. Khi GC/CPU tăng đồng thời với tombstone scanned, hãy chú ý lượng entry phải hợp nhất. Khi compaction tồn đọng, nhiều SSTable có thể là triệu chứng đang kéo dài.

## 6. Read consistency và bộ đệm không chữa gốc của vấn đề

Read consistency level như `ONE`, `LOCAL_QUORUM` hay `QUORUM` xác định mức tham gia replica cần thiết theo topology và yêu cầu nhất quán. **Một replica vẫn phải tự dựng kết quả từ memtable và SSTable của nó**. Tăng consistency level có thể làm coordinator thực hiện thêm trao đổi/đối chiếu replica, nhưng không làm biến mất tombstone hoặc hợp nhất vật lý các SSTable.

Bộ đệm cũng có giới hạn:

- **Key cache** giúp tìm partition trong SSTable nhanh hơn nhưng không làm SSTable cũ biến mất.
- **Bloom filter** loại trừ SSTable không thể chứa partition; khi partition thực sự có mặt ở nhiều SSTable, vẫn cần xử lý.
- **Row cache** có thể tăng tốc một số truy vấn lặp lại nếu workload phù hợp và cache có hiệu quả; cập nhật thường xuyên, các partition rất lớn hoặc query quét rộng làm lợi ích giảm.

Tối ưu cache trước khi sửa partition quá lớn hoặc nhiều tombstone thường chỉ cải thiện bề mặt. Hãy xác định read amplification nằm ở **định tuyến**, **đọc dữ liệu**, hay **hòa giải tombstone/phiên bản**.

## 7. Thiết kế bảng theo truy vấn để thu hẹp phạm vi đọc

Giả sử ứng dụng lưu telemetry và truy vấn thường gặp là:

> “Lấy tối đa 100 sự kiện gần nhất của thiết bị D trong khoảng một giờ của ngày N.”

Thiết kế nên có partition key mà truy vấn xác định được; tránh dồn toàn bộ lịch sử nhiều năm của một thiết bị vào một partition khổng lồ.

~~~cql
-- Giả sử keyspace telemetry đã tồn tại.
CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id timeuuid,
    metric_value double,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC)
  AND default_time_to_live = 604800;
~~~

Ở đây:

- `(device_id, event_day)` là **composite partition key**, chia dữ liệu theo thiết bị và ngày để tránh partition tăng mãi.
- `event_time` và `event_id` là **clustering columns**; thứ tự giảm dần hỗ trợ lấy sự kiện gần nhất.
- `event_id` giúp phân biệt các sự kiện cùng timestamp.
- TTL mặc định 604.800 giây (7 ngày) phù hợp nếu chính sách lưu trữ thực sự là 7 ngày; TTL có chi phí tombstone, nên cần kiểm soát.

Truy vấn có khóa định tuyến và khoảng clustering rõ:

~~~cql
SELECT event_time, event_id, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T10:00:00Z'
  AND event_time < '2026-11-21T11:00:00Z'
LIMIT 100;
~~~

Cassandra có thể đi tới **một partition xác định** và **một khoảng clustering** thay vì quét rộng trên nhiều partition. Điều này giảm khối lượng dữ liệu ứng viên, nhưng nếu partition được cập nhật/xóa nhiều lần, nhiều SSTable và tombstone trong khoảng đó vẫn tạo read amplification.

### 7.1. Đừng xem `ALLOW FILTERING` là cách chữa chậm

Một truy vấn lọc trên cột không thuộc khóa phù hợp, ví dụ quét bảng tìm `metric_value > 80`, có thể đẩy việc chọn lọc xuống server theo cách phải đọc rộng:

~~~cql
-- Ví dụ kiểu truy vấn cần xem lại thiết kế:
SELECT *
FROM telemetry.events_by_device_day
WHERE metric_value > 80
ALLOW FILTERING;
~~~

`ALLOW FILTERING` không gộp SSTable, xóa tombstone hoặc đổi truy vấn thành truy cập theo partition key hiệu quả. Nếu nghiệp vụ thật sự cần truy vấn theo ngưỡng, hãy cân nhắc **bảng phục vụ truy vấn đó**, pipeline tổng hợp hoặc cơ chế index thích hợp với phiên bản và workload; đo chi phí thực tế trước khi chọn.

### 7.2. Chọn bucket theo mô hình truy vấn, không theo một công thức cố định

Bucket theo ngày, giờ hoặc khoảng khác là đánh đổi:

- Bucket **quá lớn**: partition rộng, nhiều dữ liệu/hết TTL cùng nằm trong phạm vi đọc.
- Bucket **quá nhỏ**: một truy vấn có thể phải đọc nhiều partition/bucket và ghép kết quả ở ứng dụng.
- Bucket phải khớp khối lượng ghi, kích cỡ partition, cửa sổ truy vấn và thời gian giữ dữ liệu.

Không có kích cỡ bucket đúng cho mọi hệ thống. Hãy đo phân bố **partition size**, tốc độ ghi và tỷ lệ truy vấn xuyên bucket.

## 8. Compaction giảm phân mảnh ra sao?

**Compaction** đọc những SSTable được chọn, hợp nhất các phiên bản tương ứng, viết SSTable mới và thu hồi tệp cũ khi an toàn. Nó có thể giảm số tệp phải xét khi đọc, xử lý dữ liệu trùng/lỗi thời và thu hồi tombstone đã đủ điều kiện.

Tuy nhiên compaction tiêu tốn I/O, CPU và dung lượng tạm. Nếu tốc độ mutation liên tục vượt khả năng compaction, backlog làm hiện tượng đọc qua nhiều SSTable kéo dài.

| Strategy | Đặc điểm liên quan read amplification | Thích hợp khi |
|---|---|---|
| **SizeTieredCompactionStrategy (STCS)** | Gom các SSTable cùng cỡ; có thể còn nhiều SSTable có khoảng khóa chồng lấn, làm đọc phải xét nhiều tệp | Workload thiên ghi, yêu cầu đọc phù hợp |
| **LeveledCompactionStrategy (LCS)** | Tổ chức theo level để hạn chế chồng lấn khóa trong từng level (ngoại lệ như L0); thường giảm SSTable phải xét cho point read, đổi lại chi phí compaction/ghi cao hơn | Đọc nhạy latency, cập nhật nhiều, có đủ tài nguyên I/O |
| **TimeWindowCompactionStrategy (TWCS)** | Gom dữ liệu theo cửa sổ thời gian; với dữ liệu append-only và TTL tương đối đồng đều, SSTable đã hết hạn toàn bộ có thể được thu hồi hiệu quả khi đủ điều kiện | Time series, dữ liệu chủ yếu ghi theo thời gian và hết hạn đồng đều |

Cần đánh giá chiến lược theo **phiên bản Cassandra đang chạy** và workload thực tế. Chuyển compaction strategy trên bảng lớn không đồng nghĩa phân mảnh lập tức biến mất; quá trình chuyển và backlog có thể tiêu tốn nhiều I/O.

### 8.1. TWCS và TTL: thuận lợi nhưng có điều kiện

TWCS có thể giảm chi phí giữ tombstone khi dữ liệu nằm trong các cửa sổ thời gian và toàn bộ SSTable trở nên hết hạn. Tuy nhiên hiệu quả giảm mạnh nếu:

- Dữ liệu cũ thường xuyên bị cập nhật/ghi trễ vào cửa sổ đã đóng.
- Gộp dữ liệu TTL rất khác nhau hoặc dữ liệu **không TTL** vào cùng nhóm SSTable.
- Có nhiều xóa tùy ý hoặc partition trải qua nhiều cửa sổ.
- Compaction không đủ tài nguyên, hoặc điều kiện an toàn để loại bỏ tombstone chưa đạt.

Không nên chỉ nhìn tên “time window” rồi mặc định cấu hình TWCS là tối ưu. Phải kiểm tra phân bố timestamp, TTL, khối lượng ghi trễ và mức đọc thực tế.

### 8.2. Vì sao không xóa tombstone ngay?

Nếu một replica mất kết nối vào lúc xóa và vẫn giữ dữ liệu cũ, việc thu hồi tombstone quá sớm có thể khiến giá trị cũ **xuất hiện trở lại (zombie data)** khi replica quay lại và đồng bộ. `gc_grace_seconds` cùng cơ chế repair/điều kiện purge giúp giới hạn rủi ro này.

Vì vậy:

- Đừng đặt `gc_grace_seconds = 0` chỉ để giảm tombstone scan nếu chưa có thiết kế vận hành được chứng minh an toàn.
- Thực hiện repair theo lịch phù hợp với replication, cửa sổ khôi phục và cấu hình; replica ngắt lâu quá lâu cần quy trình xử lý đặc biệt.
- **Repair** giúp đồng bộ replica, nhưng bản thân nó không tự quyết định xóa hết tombstone ngay. **Compaction** mới xử lý các tệp trên đĩa khi điều kiện cho phép.
- Đừng ép compaction toàn bảng trong production chỉ vì một truy vấn chậm; hãy kiểm tra tác động I/O, dung lượng tạm, chiến lược và giải pháp thiết kế dữ liệu trước.

## 9. Chẩn đoán: phân biệt nhiều SSTable với nhiều tombstone

### 9.1. Các câu hỏi điều tra theo thứ tự

1. **Truy vấn nào chậm?** Lấy đúng CQL/binding, partition key, clustering range, `LIMIT`, read CL và p95/p99 latency.
2. **Truy vấn đang định tuyến thế nào?** Có đủ partition key? Có phải quét cả partition/khung thời gian rộng? Có `ALLOW FILTERING`?
3. **Một lần đọc đụng bao nhiêu SSTable?** Xem thống kê “SSTables per read” theo table/replica và tỷ lệ cache hit.
4. **Có quét nhiều tombstone không?** So cảnh báo, tombstones scanned và số hàng sống trả về; chú ý các query chỉ xuất hiện chậm với dữ liệu cũ.
5. **Compaction có theo kịp không?** Xem pending compactions, backlog, disk I/O, kích cỡ partition và workload ghi/xóa/TTL.
6. **Có vấn đề xuyên replica không?** Kiểm tra slow replica, read timeout, read repair, network và tình trạng node riêng biệt với read amplification tại một replica.

### 9.2. Công cụ quan sát

Trên môi trường có quyền vận hành Cassandra và phiên bản hỗ trợ:

~~~bash
# Thống kê theo bảng: số SSTable, latency, partition size,
# tombstone/cell per slice (tên chỉ số tùy phiên bản).
nodetool tablestats telemetry.events_by_device_day

# Phân bố SSTables per read, read latency, partition size...
nodetool tablehistograms telemetry events_by_device_day

# Tình trạng các compaction đang chạy và backlog.
nodetool compactionstats
~~~

Trong `cqlsh`, có thể dùng tracing chọn lọc để xem một truy vấn mẫu:

~~~cql
TRACING ON;
SELECT event_time, event_id, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T10:00:00Z'
  AND event_time < '2026-11-21T11:00:00Z'
LIMIT 100;
TRACING OFF;
~~~

Tracing tạo thêm tải và không phản ánh hoàn hảo workload production. Chỉ dùng có chọn lọc, đọc đối chiếu với metrics per node/table. Các tên metric và ngưỡng tombstone warning/failure thay đổi theo phiên bản/cấu hình; hãy kiểm tra bộ metric của cluster thực tế trước khi so sánh tuyệt đối.

| Triệu chứng | Giả thuyết cần kiểm chứng | Hành động tiếp theo |
|---|---|---|
| SSTables per read cao, tombstone scan không cao | SSTable chồng lấn/compaction backlog, cache/index kém hiệu quả | Kiểm tra strategy, compactionstats, I/O, workload cập nhật |
| Tombstones scanned rất cao dù `LIMIT` nhỏ | TTL/deletion dày đặc ở đầu dải clustering | Giảm dải quét, chỉnh bucket/TTL, hạn chế xóa hàng loạt |
| Partition size lớn, chỉ một số khóa rất chậm | Hot/wide partition, quá nhiều row/chunk | Chia bucket hợp lý, giới hạn khung thời gian truy vấn |
| Mọi read chậm cùng lúc | Tải node, ổ đĩa, GC, network hoặc compaction giành I/O | Kiểm tra metrics hạ tầng và replica |
| Chậm sau khi backfill dữ liệu cũ | Ghi ngoài cửa sổ, SSTable nhiều phiên bản | So chiến lược compaction với mẫu ghi trễ, đánh giá phân bố SSTable |

## 10. Ví dụ Java: đọc đúng partition và giới hạn kích thước mỗi lần lấy

Với **DataStax Java Driver 4.x**, ưu tiên prepared statement có đủ partition key và dải clustering. Giả sử `CqlSession session` đã được cấu hình đúng datacenter và keyspace/table ở ví dụ trên đã tồn tại:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement select = session.prepare(
    "SELECT event_time, event_id, metric_value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "AND event_time >= ? AND event_time < ? " +
    "LIMIT 100"
);

UUID deviceId =
    UUID.fromString("11111111-1111-1111-1111-111111111111");

BoundStatement query = select.bind(
        deviceId,
        LocalDate.of(2026, 11, 21),
        Instant.parse("2026-11-21T10:00:00Z"),
        Instant.parse("2026-11-21T11:00:00Z"))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(50);

for (Row row : session.execute(query)) {
    Instant eventTime = row.getInstant("event_time");
    UUID eventId = row.getUuid("event_id"); // CQL timeuuid
    double value = row.getDouble("metric_value");
    // Xử lý hoặc đưa dữ liệu sang trang hiển thị.
}
~~~

`setPageSize(50)` giới hạn số hàng driver yêu cầu theo trang; `LIMIT 100` giới hạn tổng số hàng trong truy vấn. Driver có thể lấy thêm trang khi vòng lặp tiếp tục. **Phân trang giảm dữ liệu trả về và bộ nhớ client mỗi đợt**, nhưng không bảo đảm server không phải quét nhiều tombstone để tạo đủ số hàng sống. Để hỗ trợ duyệt nhiều hơn 100 hàng, ứng dụng có thể sử dụng cơ chế paging state/cursor phù hợp thay vì dùng OFFSET như SQL quan hệ.

Trong ví dụ này, `LOCAL_QUORUM` chỉ là lựa chọn minh họa cho topology phù hợp; read CL thực tế phải theo yêu cầu tính nhất quán và replication. Đổi read CL không thay một truy vấn quét tombstone thành truy vấn rẻ.

### Những việc driver không thể tự chữa

- Không làm một partition quá lớn nhỏ lại.
- Không tránh scan tombstone nếu query yêu cầu các row nằm sau vùng đã xóa.
- Không ép compaction hoàn thành.
- Không biến `ALLOW FILTERING` thành index theo partition/clustering.

Tầng Java nên hỗ trợ **timeout hợp lý, quan sát latency theo truy vấn, giới hạn dải thời gian, paging, backpressure và retry có kiểm soát**. Nếu truy vấn chậm có tính hệ thống, cần sửa data model hoặc vận hành Cassandra.

## 11. Quy trình xử lý một sự cố thực tế

Giả sử API “20 sự kiện mới nhất” của một thiết bị tăng từ vài chục mili giây lên vài giây sau đợt dọn dữ liệu.

1. **Lấy bằng chứng:** lưu query/binding và latency; xác định node/replica chậm, metrics SSTables per read/tombstones scanned, bảng bị ảnh hưởng.
2. **Tách nguyên nhân:** nếu nhiều tombstone sau một đợt `DELETE` lớn, vấn đề khác với SSTable chồng lấn do compaction backlog. Có thể cả hai cùng tồn tại.
3. **Giảm phạm vi đọc trước:** dùng partition theo ngày/giờ và khoảng clustering, kiểm tra `LIMIT`/paging. Không dùng full scan vì tiện viết API.
4. **Đánh giá chính sách lưu trữ:** nếu xóa hàng loạt mỗi ngày, cân nhắc schema/time bucket + TTL phù hợp; kiểm tra tác động tombstone mới và yêu cầu retention.
5. **Đánh giá compaction strategy:** quan sát write amplification, backlog, SSTables per read, phân bố TTL. Với time series append-only, thử nghiệm TWCS nếu đặc tính workload phù hợp; với nhiều cập nhật và nhạy read latency, cân nhắc LCS.
6. **Giữ an toàn xóa dữ liệu:** repair và `gc_grace_seconds` phải theo chính sách nhất quán replica; không hạ ngưỡng an toàn tùy tiện chỉ để giảm dung lượng.
7. **Đo lại trên workload đại diện:** so p50/p95/p99, SSTables per read, tombstones scanned, disk I/O, CPU, pending compactions và số hàng thực sự trả về.

Đừng kết luận “thêm RAM/cache là xong” nếu chưa tìm được **vì sao replica phải hợp nhất nhiều tệp/dấu xóa**. Trường hợp cần thay schema, thực hiện backfill/migration có kiểm soát và tránh tạo đợt ghi làm nghẽn compaction.

## 12. Bài tập tự kiểm tra

**Câu 1.** Một `SELECT ... LIMIT 10` chạm 20 SSTable và quét hàng nghìn tombstone. Vì sao trả 10 hàng mà vẫn chậm?

**Giải thích:** `LIMIT` chỉ giới hạn hàng sống trong kết quả; server có thể phải dò nhiều SSTable và bỏ qua dấu xóa để xác định 10 hàng hợp lệ.

**Câu 2.** Bloom filter của SSTable S trả “không có partition P”. Replica có cần mở data file S để kiểm tra P không?

**Giải thích:** Không cần cho P; Bloom filter âm tính loại trừ chắc chắn. Trường hợp filter dương tính có thể là dương tính giả và cần kiểm tra tiếp.

**Câu 3.** Một row bị xóa, nhưng SSTable cũ vẫn chứa row đó. Vì sao Cassandra không thể bỏ qua tombstone ngay?

**Giải thích:** Tombstone che dữ liệu cũ trong hợp nhất, đồng thời hỗ trợ truyền việc xóa tới replica chưa nhận mutation. Xóa dấu quá sớm có rủi ro zombie data.

**Câu 4.** Thêm `LOCAL_QUORUM` cho một truy vấn đọc nhiều tombstone có làm biến mất tombstone scan?

**Giải thích:** Không. Read CL quy định replica tham gia; mỗi replica vẫn cần xử lý nguồn dữ liệu hợp lệ của mình.

**Câu 5.** Vì sao TWCS thường phù hợp dữ liệu time series có TTL đồng đều hơn bảng cập nhật phiên bản cũ liên tục?

**Giải thích:** Trong trường hợp append-only, các cửa sổ thời gian được compact tách biệt và SSTable có thể hết hạn gần nhau. Ghi trễ/cập nhật quá khứ và TTL không đồng đều làm tệp chồng lấn hoặc không thể thu hồi trọn vẹn hiệu quả.

**Câu 6.** Thấy warning tombstone, có nên lập tức đặt `gc_grace_seconds = 0` và force compaction?

**Giải thích:** Không. Cần phân tích query, retention, chiến lược compaction, tình trạng replica/repair và rủi ro hồi sinh dữ liệu trước khi thay đổi vận hành.

## 13. Ghi nhớ

Một lần đọc Cassandra không chỉ đọc hàng “mới nhất”: nó phải **tìm partition trên memtable/SSTable, hợp nhất các phiên bản và áp dụng tombstone**, đôi khi qua nhiều tệp, nhiều chunk và nhiều replica. Vì thế:

- **Nhiều SSTable** làm tăng số nguồn cần kiểm tra và hòa giải.
- **Nhiều tombstone** làm tăng lượng entry phải quét dù kết quả nhỏ.
- **Partition lớn hoặc dữ liệu phân mảnh** làm tăng phạm vi đọc và giảm hiệu quả locality/cache.
- **Compaction và repair** có vai trò khác nhau; chỉ thu hồi tombstone khi đủ điều kiện an toàn.
- **Thiết kế theo truy vấn** — partition/bucket hợp lý, clustering range giới hạn, TTL phù hợp — là nền tảng để đường đọc giữ độ trễ ổn định.

Khi xử lý sự cố, ưu tiên **đo SSTables per read và tombstones scanned**, liên hệ chúng với mẫu ghi/TTL, rồi thay đổi schema hoặc compaction theo dữ liệu quan sát. Đó là cách tránh một truy vấn “trả 20 hàng” tiêu tốn công sức như quét hàng nghìn bản ghi.
