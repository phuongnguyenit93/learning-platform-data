# Range tombstone và truy vấn theo khoảng

## 1. Đọc ít hàng nhưng phải xử lý nhiều dấu xóa: tại sao?

Trong **Apache Cassandra**, một `DELETE` không nhất thiết xóa ngay byte dữ liệu cũ khỏi ổ đĩa. Cassandra ghi **tombstone** để đánh dấu những giá trị/hàng không còn được trả về; các phiên bản cũ vẫn có thể nằm ở memtable hoặc SSTable khác cho tới khi compaction loại bỏ chúng an toàn.

**Range tombstone** là dạng tombstone dùng để xóa **một khoảng hàng theo clustering key bên trong một partition**, thay vì phải tạo từng lệnh xóa cho từng hàng. Nó đặc biệt liên quan đến những bảng wide-column có nhiều sự kiện được sắp theo thời gian.

Ví dụ nghiệp vụ: một ứng dụng cảm biến muốn xóa mọi phép đo từ **08:00 đến trước 09:00** trong ngày 21/11/2026 nhưng giữ lại các phép đo sau 09:00. Ở Cassandra, một range deletion có thể ghi thông tin “khoảng clustering key này đã bị xóa” vào hệ thống. Khi đọc một khoảng thời gian giao với vùng bị xóa, Cassandra phải đối chiếu cả **dữ liệu cũ** và **range tombstone** để quyết định hàng nào còn hợp lệ.

**Mục tiêu của bài:**

- Phân biệt **range tombstone**, **row/partition/cell tombstone**, **TTL** và **token-range scan**.
- Viết được CQL xóa một khoảng clustering key và đọc đúng những hàng còn sống.
- Giải thích marker mở/đóng, write timestamp và điều kiện một bản ghi cũ bị che khuất.
- Hiểu tác động đến read path, cache, SSTable, compaction, `gc_grace_seconds` và repair.
- Thiết kế bảng theo truy vấn, quan sát tombstone scan và sử dụng Java Driver an toàn.

**Phạm vi:** các full replica thông thường của Cassandra; chi tiết biểu diễn range tombstone trên đĩa, ngưỡng cảnh báo và chiến lược loại bỏ có thể thay đổi theo phiên bản.

## 2. Nền tảng: partition key khác clustering range

Xét bảng đo nhiệt độ của từng thiết bị theo ngày:

~~~sql
CREATE KEYSPACE IF NOT EXISTS sensors_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS sensors_lab.readings_by_device_day (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    temperature decimal,
    quality text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Để chạy ví dụ, thay `dc1` bằng tên data center thực tế và bảo đảm đủ node phù hợp nếu dùng RF = 3 và `LOCAL_QUORUM`.

| Thành phần | Vai trò | Quan hệ với range tombstone |
| --- | --- | --- |
| `(device_id, event_day)` | **Partition key kép**: xác định token và tập replica lưu partition | Một range tombstone được giới hạn **trong partition đã xác định**, không tự lan sang partition khác. |
| `event_time` | **Clustering column thứ nhất**, sắp xếp giảm dần | Cho phép mô tả khoảng thời gian gồm nhiều hàng **trong cùng partition**. |
| `event_id` | **Clustering column thứ hai**, phân biệt các sự kiện cùng thời điểm | Nếu chỉ giới hạn `event_time`, có thể xóa nhiều `event_id` tương ứng trong khoảng. |
| `temperature`, `quality` | Regular columns | Không phải khóa dùng để xác định phạm vi clustering của range tombstone trong ví dụ. |

Với `device_id='device-7'` và `event_day='2026-11-21'`, các hàng có thời điểm 08:05, 08:30 và 09:10 đều ở **cùng một partition**, bất kể có bao nhiêu SSTable. Nếu đổi ngày hoặc thiết bị, Cassandra tính một partition key khác.

**Điểm dễ nhầm:** `CLUSTERING ORDER BY (event_time DESC)` thay đổi **thứ tự lưu/trả hàng**, không làm các toán tử so sánh trong CQL đổi nghĩa: `event_time >= 08:00 AND event_time < 09:00` vẫn có nghĩa khoảng **[08:00, 09:00)**.

## 3. So sánh các loại tombstone

Tombstone là **thông tin xóa có timestamp**, không chỉ là một “ô rỗng”. Tùy câu lệnh và phạm vi, Cassandra sử dụng những cơ chế đánh dấu xóa khác nhau.

| Loại xóa | Ví dụ ý tưởng CQL | Phạm vi logic |
| --- | --- | --- |
| **Cell tombstone** | `DELETE quality ... WHERE` kèm đủ primary key | Một giá trị cột thông thường trong một hàng cụ thể. |
| **Row tombstone** | `DELETE FROM ... WHERE` với đầy đủ partition key và clustering key của một hàng | Các cột của một hàng/row tương ứng. |
| **Partition tombstone** | `DELETE FROM ... WHERE device_id=? AND event_day=?` | Mọi hàng/giá trị thuộc partition theo semantics timestamp. |
| **Range tombstone** | `DELETE FROM ... WHERE partition_key = ... AND event_time >= ... AND event_time < ...` | Những hàng trong khoảng clustering key thuộc partition đã xác định. |
| **Tombstone do TTL hết hạn** | `INSERT/UPDATE ... USING TTL` rồi đến thời điểm hết hạn | Giá trị có TTL không còn sống; thời gian kết thúc và metadata xóa tham gia hòa giải. |

Một phần chi tiết nội bộ có thể khác theo loại cột và phiên bản. Ý nghĩa quan trọng cho người viết CQL là **phạm vi bị che**: toàn partition, một hàng, một cell hay **một đoạn liên tục theo clustering key**.

### Không phải xóa theo khoảng token

Hai khái niệm “range” rất khác nhau:

- **Clustering range**: ví dụ `WHERE device_id='device-7' AND event_day='2026-11-21' AND event_time >= ...`; thao tác trong **một partition**. Range tombstone thuộc loại này.
- **Token range**: ví dụ `WHERE token(device_id, event_day) > ... AND token(device_id, event_day) <= ...`; dùng để **quét nhiều partition** theo token trên vòng phân phối.

Không được giả định rằng `DELETE ... WHERE token(partition_key) BETWEEN ...` sẽ tạo một range tombstone xuyên toàn cluster. Range tombstone không phải “xóa mọi partition trong một đoạn token”; muốn xóa diện rộng theo nhiều partition cần quy trình riêng, xác định từng khóa/phạm vi và đánh giá chi phí, tính nhất quán.

## 4. Thực hành: tạo và xóa một khoảng sự kiện

### 4.1. Nạp bốn hàng

Chạy trong `cqlsh` sau khi tạo bảng:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO sensors_lab.readings_by_device_day
  (device_id, event_day, event_time, event_id, temperature, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T07:50:00Z',
   123e4567-e89b-42d3-a456-426614174001, 20.10, 'OK');

INSERT INTO sensors_lab.readings_by_device_day
  (device_id, event_day, event_time, event_id, temperature, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T08:05:00Z',
   123e4567-e89b-42d3-a456-426614174002, 20.30, 'OK');

INSERT INTO sensors_lab.readings_by_device_day
  (device_id, event_day, event_time, event_id, temperature, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T08:30:00Z',
   123e4567-e89b-42d3-a456-426614174003, 20.50, 'BAD');

INSERT INTO sensors_lab.readings_by_device_day
  (device_id, event_day, event_time, event_id, temperature, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:10:00Z',
   123e4567-e89b-42d3-a456-426614174004, 21.00, 'OK');
~~~

Truy vấn kiểm tra ban đầu:

~~~sql
SELECT event_time, event_id, temperature, quality
FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';
~~~

Kỳ vọng bốn hàng (theo thứ tự thời gian giảm dần), nếu không có thao tác ghi khác trên cùng khóa.

### 4.2. Xóa mọi hàng trong khoảng [08:00, 09:00)

~~~sql
DELETE FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';
~~~

Đây là **range deletion theo clustering column `event_time`**. Với bảng trên, nó bao phủ toàn bộ các `event_id` có `event_time` rơi vào khoảng: cụ thể là hàng **08:05** và **08:30**.

Hàng **07:50** và **09:10** nằm ngoài khoảng nên không bị lệnh xóa này nhắm tới. Để kiểm chứng:

~~~sql
SELECT event_time, event_id, temperature
FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';

SELECT event_time, event_id, temperature
FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';
~~~

Với trạng thái lab không có ghi đồng thời, câu thứ nhất trả **07:50 và 09:10**, câu thứ hai **không trả hàng sống**. Không có hàng trả về **không có nghĩa các byte 08:05 và 08:30 đã biến mất khỏi SSTable**.

### 4.3. Vì sao phải có toàn bộ partition key?

Sai lầm phổ biến là thử:

~~~sql
-- Không xác định một partition; không phải cách thực hiện range delete hợp lệ.
DELETE FROM sensors_lab.readings_by_device_day
WHERE event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';
~~~

Trong schema này, chỉ `event_time` không đủ để định tuyến partition. Cassandra không được thiết kế để thực thi một câu `DELETE` CQL tùy ý chạy qua mọi thiết bị/ngày như `DELETE ... WHERE` trên bảng SQL quan hệ. Muốn xóa theo ngày trên toàn bộ thiết bị, phải thiết kế bảng/quy trình bảo trì để xác định các partition cần xử lý, hoặc dùng TTL và vòng đời dữ liệu phù hợp ngay từ lúc ghi.

## 5. Range tombstone hoạt động bên trong read path

### 5.1. Dấu mốc bắt đầu và kết thúc

Ở cấp lưu trữ, một range deletion có thể được biểu diễn bằng **các marker ranh giới** (mở/đóng khoảng) gắn với **deletion timestamp** và thời gian xóa cục bộ; Cassandra sử dụng thông tin đó khi đi qua những hàng có clustering key được sắp thứ tự.

~~~text
Clustering key theo thời gian tăng (minh họa logic):

07:50        08:00          08:05      08:30       09:00        09:10
  |------------|--------------|----------|------------|------------|
               [========== khoảng bị xóa ==========)
               ^ range start                         ^ range end
  còn sống                        bị che                            còn sống
~~~

Nếu xét thứ tự lưu thật của bảng `DESC`, Cassandra duyệt theo chiều ngược lại trên trục thời gian; ý nghĩa **đầu/đuôi khoảng CQL** vẫn là `>= 08:00` và `< 09:00`. Đừng tự suy ra thứ tự marker vật lý chỉ từ hình minh họa theo thời gian tăng.

**Một range tombstone không nhất thiết biến thành một tombstone riêng biệt cho mỗi hàng**: nó có thể biểu diễn phạm vi liên tục. Tuy nhiên, chi phí đọc vẫn có thể cao nếu partition có rất nhiều range tombstone, các khoảng chồng nhau và dữ liệu cũ phân tán trên nhiều SSTable.

### 5.2. Read phải hòa giải nhiều nguồn dữ liệu

Khi client đọc `WHERE device_id=? AND event_day=? AND event_time >= ...`, coordinator chọn replica theo token và consistency level. Mỗi replica có thể cần đọc **memtable** cùng nhiều **SSTable**, rồi hòa giải:

1. Những giá trị có timestamp ghi khác nhau ở cùng khóa.
2. Row/cell tombstone hoặc range tombstone ảnh hưởng đến khóa đó.
3. Dữ liệu đã hết TTL, marker xóa và các điều kiện hòa giải.
4. Những phiên bản nằm ở SSTable mới/cũ khác nhau.

~~~mermaid
flowchart TD
    Q["SELECT trong khoảng 08:00–09:00"] --> P["Coordinator tìm các replica của partition"]
    P --> R["Replica đọc memtable + các SSTable liên quan"]
    R --> D1["SSTable A: hàng 08:05 và 08:30 trước khi xóa"]
    R --> D2["SSTable B: range tombstone [08:00, 09:00)"]
    D1 --> H["Hòa giải theo timestamp và phạm vi xóa"]
    D2 --> H
    H --> O["Không trả những hàng bị tombstone che"]
    O --> C["Coordinator trả kết quả theo CL"]
~~~

**Các cache và chỉ mục không loại bỏ nghĩa vụ hòa giải:** Bloom filter và partition index giúp tìm/loại trừ SSTable theo partition key; key cache có thể giảm thời gian định vị; nhưng một truy vấn chạm vùng range tombstone vẫn phải áp dụng thông tin xóa đúng. Cache hit không được phép làm hiện lại một hàng đã xóa.

## 6. Timestamp quyết định xóa nào thắng

Cassandra sử dụng **write timestamp** trong cơ chế hòa giải last-write-wins, không chỉ so thời gian request đến máy. Một range tombstone có deletion timestamp `t_del` thường che các dữ liệu trong phạm vi của nó có timestamp không mới hơn `t_del` (quy tắc hòa giải cụ thể áp dụng cho các trường hợp bằng timestamp).

### Ví dụ theo thời gian logic

~~~text
t1: INSERT event 08:05, temperature = 20.30
t2: DELETE khoảng [08:00, 09:00)          (t2 > t1)
t3: INSERT lại event 08:05, temperature = 21.10 (t3 > t2)
~~~

- Sau `t2`, bản ghi từ `t1` không được trả về.
- Một bản ghi mới hợp lệ có timestamp **lớn hơn** deletion timestamp có thể xuất hiện ở chính khoảng trước đó đã xóa.
- Nếu client cấp `USING TIMESTAMP` sai, đồng hồ lệch hoặc thao tác nhập dữ liệu cũ dùng timestamp không phù hợp, kết quả có thể khác kỳ vọng “lệnh nào chạy sau thì thắng”.

**Quan trọng:** range tombstone không phải luật cấm vĩnh viễn mọi bản ghi mới có cùng clustering key. Nó là thông tin xóa có timestamp, cần được đối chiếu với các write mới và cũ.

Ví dụ kiểm soát timestamp trong lab (chỉ để minh họa nguyên tắc, **không** dùng giá trị cố định này cho ứng dụng thực):

~~~sql
-- Dùng một timestamp tương ứng sự kiện thử nghiệm ở lab độc lập.
-- Không áp dụng nếu đã có dữ liệu với timestamp khác trên cùng khóa.
DELETE FROM sensors_lab.readings_by_device_day
USING TIMESTAMP 1795200000000000
WHERE device_id = 'device-lab'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';
~~~

Nếu ứng dụng tự cấp timestamp, phải có chính sách đồng hồ, ordering và idempotency nhất quán; việc sử dụng cùng timestamp cho xóa và ghi mới có semantics giải quyết xung đột riêng. Không dựa vào `WRITETIME(temperature)` để suy rằng một dòng đã xóa chắc chắn không còn marker trên đĩa: CQL thường chỉ trả các giá trị đang sống.

## 7. Vì sao truy vấn theo khoảng có thể chậm hơn sau nhiều lần DELETE?

Một `SELECT` có đủ partition key và chỉ yêu cầu vài hàng vẫn có thể phải đọc **nhiều marker tombstone**. Các yếu tố hay đi cùng nhau là:

- **Nhiều phạm vi xóa nhỏ** trong cùng partition, ví dụ xóa 5 phút một lần trong 180 ngày.
- **Các khoảng xóa chồng nhau** và có timestamp khác nhau.
- **SSTable cũ còn hàng bị che** trong khi SSTable mới chứa range tombstone.
- **Memtable mới và SSTable cũ** phải hòa giải, kèm tombstone do TTL.
- **Partition quá lớn** khiến một slice query hoặc quét partition đọc rất nhiều dữ liệu để tìm vài hàng sống.

| Truy vấn | Kết quả nhìn thấy | Công việc ngầm có thể phải làm |
| --- | --- | --- |
| `SELECT ... WHERE pk=? AND event_time >= 08:00 AND event_time < 09:00` | 0 hàng sau khi xóa | Duyệt các nguồn chứa hàng cũ và thông tin range tombstone trên đoạn đó. |
| `SELECT ... WHERE pk=? LIMIT 10` | 10 hàng sống | Có thể phải bỏ qua nhiều hàng đã bị xóa để tìm được 10 hàng còn sống. |
| `SELECT COUNT(*) WHERE pk=?` | Một con số | Có thể phải xử lý rất nhiều hàng, TTL và tombstone; không phải phép đếm metadata tức thời. |
| Quét nhiều partition bằng `token(pk)` | Nhiều hàng thuộc nhiều partition | Mỗi partition vẫn có thể mang các range tombstone riêng, tăng tổng lượng xử lý. |

Trong hệ thống production, số tombstone được duyệt có thể liên quan tới cảnh báo/giới hạn bảo vệ truy vấn; các tham số như `tombstone_warn_threshold` và `tombstone_failure_threshold` (nếu có ở phiên bản dùng) **không phải bộ tối ưu dữ liệu**. Chỉ tăng ngưỡng để “hết lỗi” có thể làm tăng độ trễ, memory pressure và tải replica.

### 7.1. `LIMIT` không chữa được tombstone scan

~~~sql
SELECT event_time, temperature
FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

`LIMIT 10` giới hạn tối đa **10 hàng được trả về**, không bảo đảm Cassandra chỉ đọc 10 mục trên SSTable. Nếu hàng đầu tiên còn sống nằm sau nhiều hàng đã bị xóa, replica vẫn cần đi qua những marker và dữ liệu liên quan để cho kết quả đúng.

**Paging** trong Java Driver chia kết quả thành từng trang, nhưng không giảm số hàng nguồn phải xét để hoàn thành cả một truy vấn dài. Truy vấn có CL cao hơn còn có thể cần đối chiếu các phiên bản từ nhiều replica, tùy trạng thái nhất quán của dữ liệu.

## 8. Thu hồi range tombstone: grace, repair và compaction

### 8.1. Vì sao không xóa tombstone ngay?

Một replica có thể đang offline khi range deletion được ghi. Nếu các replica đang hoạt động xóa thông tin tombstone quá sớm, replica từng vắng mặt có thể mang **hàng cũ** trở lại khi tham gia và được đồng bộ, tạo hiện tượng **zombie data**.

~~~mermaid
sequenceDiagram
    participant App as Client
    participant N1 as Replica N1
    participant N2 as Replica N2
    participant N3 as Replica N3 (offline)
    Note over N1,N3: RF = 3, N3 chưa nhận xóa
    App->>N1: DELETE range [08:00, 09:00)
    N1->>N2: Truyền mutation/tombstone
    N2-->>N1: ACK
    N1-->>App: Có thể thành công ở LOCAL_QUORUM
    Note over N1,N2: Tombstone còn cần để che bản ghi cũ
    Note over N3: Vẫn có dữ liệu 08:05, 08:30
    Note over N1,N3: Repair/đồng bộ đúng hạn giúp lan truyền thông tin xóa
~~~

**`gc_grace_seconds`** là khoảng thời gian bảo vệ quan trọng cho việc dọn tombstone và khả năng một replica vắng mặt nhận được thông tin xóa. Nhưng điều này **không tự thực hiện repair**, cũng không bảo đảm tombstone bị xóa đúng thời điểm grace hết.

### 8.2. Ba điều kiện cần nghĩ đến trước khi purge

1. **Độ tuổi tombstone:** metadata xóa đã đủ điều kiện về thời gian hay chưa?
2. **Tính an toàn với dữ liệu chồng lấn:** SSTable khác có chứa phiên bản cũ mà tombstone này còn phải che hay không?
3. **Độ hội tụ giữa replica:** replica/offline và lịch repair có khiến xóa marker sớm gây nguy cơ zombie hay không?

**Compaction** có thể hợp nhất dữ liệu và marker xóa, loại những dữ liệu/tombstone an toàn để purge, hoặc giữ lại thông tin vẫn cần thiết. Không được xóa thủ công file SSTable chỉ vì `SELECT` không còn thấy dữ liệu. `nodetool compact` hay major compaction cũng **không bảo đảm** mọi tombstone sẽ biến mất và có thể gây I/O lớn.

Các cơ chế liên quan:

| Cơ chế | Vai trò | Không được suy ra |
| --- | --- | --- |
| **Hinted handoff** | Ghi nhận một số mutation để chuyển lại replica tạm không khả dụng, với giới hạn vận hành | Không thay thế repair hoặc lưu xóa vô hạn. |
| **Read repair** | Có thể sửa lệch replica trên phần dữ liệu đã được đọc, tùy phiên bản/chế độ | Không bảo đảm mọi khoảng chưa được đọc sẽ tự hội tụ. |
| **Anti-entropy repair** | Đồng bộ dữ liệu/tombstone giữa các replica cho những vùng dữ liệu liên quan | Không phải công tắc xóa tombstone tức thời. |
| **Compaction** | Giảm SSTable và dọn phiên bản/marker đủ điều kiện trên từng node | Không gửi delete đến replica khác và không thay repair. |
| **Backup/snapshot** | Phục hồi trước thao tác xóa nhầm/lỗi logic theo chính sách retention | Replication không tự hoàn tác một delete đã lan tới các replica. |

### 8.3. Range tombstone và TWCS/TTL

**TimeWindowCompactionStrategy** thường hữu ích cho dữ liệu time series append-only có TTL gần đồng nhất. Nhưng một loạt **range delete trên dữ liệu cũ**, backfill hoặc update cũ có thể tạo marker và phiên bản trải qua nhiều SSTable/window, khiến việc thu hồi khó hơn.

Với dữ liệu chỉ cần giữ 30 ngày, một **TTL được thiết kế ngay khi ghi** có thể phù hợp hơn quy trình xóa thủ công từng khoảng mỗi ngày. Tuy nhiên, TTL cũng tạo tombstone khi hết hạn; nó **không** cho phép bỏ qua `gc_grace_seconds`, repair hay điều kiện compaction. Nếu nghiệp vụ phải xóa chọn lọc một đoạn trong partition, range tombstone có thể cần thiết.

## 9. Hướng dẫn quan sát trong lab

### 9.1. Bật tracing cho một truy vấn nhỏ

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, temperature
FROM sensors_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';

TRACING OFF;
~~~

Tùy phiên bản và tracing events, có thể quan sát một số hoạt động đọc, endpoint, thời gian hoặc số tombstone được xử lý. **Trace là công cụ chẩn đoán**, không phải bản chứng nhận rằng mọi replica đã repair hay file SSTable đã được xóa.

### 9.2. Quan sát metrics và tình trạng cluster

Trên node có quyền `nodetool`:

~~~bash
nodetool tablestats sensors_lab.readings_by_device_day
nodetool compactionstats
nodetool status
~~~

Các thông tin thường hữu ích (tên metric có thể khác theo phiên bản):

- **Tombstones scanned per read/slice**: số tombstone đi qua đường đọc, đặc biệt ở partition/time range nóng.
- **SSTable count/size**: một truy vấn phải hòa giải bao nhiêu file, dung lượng đĩa đang tăng hay giảm?
- **Read latency/timeouts**: tombstone scan có ảnh hưởng API hay tạo cảnh báo?
- **Pending/active compactions**: có backlog khiến file cũ chưa được hợp nhất?
- **Replica up/down và repair status**: liệu có replica bỏ lỡ delete lâu ngày?

Không nên kết luận “range tombstone chính là thủ phạm” chỉ từ một chỉ số. Cần kết hợp CQL truy vấn thực tế, kích thước partition, số SSTable, TTL, tombstone metrics, CL, mô hình ghi và thời gian.

### 9.3. Nếu cần xem marker trên đĩa

Trong một môi trường thử nghiệm biệt lập, có thể sử dụng công cụ kiểm tra SSTable đi kèm **đúng phiên bản Cassandra** và metadata của bảng để xem range tombstone marker/partition. Cần tuân thủ yêu cầu vận hành của công cụ về việc node có cần dừng hay không; không chạy các thao tác sửa/xóa SSTable trên production chỉ để “dọn tombstone”. CQL `SELECT` hiển thị **dữ liệu logic đang sống**, không hiển thị trực tiếp toàn bộ marker xóa.

## 10. Ứng dụng Java: xóa khoảng theo prepared statement

Ví dụ dùng **Apache Cassandra Java Driver 4.x**, với bảng `readings_by_device_day` đã tạo. Hai biên thời gian được cấp như `Instant` và cùng thuộc một partition đã xác định:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;

public final class DeleteDeviceReadingsRange {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement deleteRange = session.prepare(
                    "DELETE FROM sensors_lab.readings_by_device_day " +
                    "WHERE device_id = ? AND event_day = ? " +
                    "AND event_time >= ? AND event_time < ?");

            BoundStatement stmt = deleteRange.bind(
                    "device-7",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T08:00:00Z"),
                    Instant.parse("2026-11-21T09:00:00Z"))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(stmt);
        }
    }
}
~~~

**Các điểm cần nhớ với Java:**

1. **Bắt buộc truyền đầy đủ partition key** `device_id` và `event_day`; prepared statement cho phép bind đúng kiểu `date`/`timestamp`.
2. Biên `>= start`, `< end` là khoảng **nửa kín**. Nếu hai lệnh xóa các khoảng liền nhau, cách chọn biên cần thống nhất để không sót/nhầm bản ghi ở mốc giao.
3. `LOCAL_QUORUM` kiểm soát **ngưỡng ACK replica** tại local DC; nó **không** có nghĩa tombstone đã được compaction hoặc đã tới mọi replica.
4. **Timeout là kết quả chưa chắc chắn**: một hoặc nhiều replica có thể đã áp dụng mutation xóa. Thử lại phải dùng cùng phạm vi và chính sách idempotency/timestamp phù hợp; đặc biệt tránh cho dữ liệu mới ghi sau đó bị một lệnh xóa thử lại có timestamp mới hơn che mất.
5. Để chống delete ngoài ý muốn, phân quyền tài khoản ứng dụng, kiểm tra khoảng thời gian/thiết bị, ghi audit và dùng cơ chế duyệt đối với xóa dữ liệu số lượng lớn.

`127.0.0.1` và `dc1` chỉ dành cho lab; production cần cấu hình contact point, local DC, TLS/authentication, timeout và retry policy theo topology thực tế.

## 11. Cách thiết kế giảm range tombstone và chi phí đọc

Không phải luôn có thể bỏ `DELETE`. Nhưng nếu hệ thống tạo hàng triệu khoảng xóa nhỏ, nên xem lại **hợp đồng dữ liệu và bảng phục vụ truy vấn**.

| Nhu cầu | Thiết kế cân nhắc | Đánh đổi |
| --- | --- | --- |
| Dữ liệu cảm biến chỉ giữ 30 ngày | TTL nhất quán, partition theo ngày/bucket, TWCS khi workload phù hợp | TTL vẫn sinh tombstone, phải chờ purge an toàn. |
| Hủy nguyên một ngày dữ liệu của thiết bị | Partition key theo `(device_id, event_day)`; cân nhắc partition deletion thay vì nhiều range deletion | Một partition deletion vẫn cần tombstone và repair. |
| Chỉ xóa một đoạn thời gian vì dữ liệu hỏng | Range deletion trên clustering prefix tương ứng | Đúng phạm vi, nhưng marker và phiên bản cũ có thể tăng chi phí đọc. |
| Thường xuyên đổi/xóa nhiều đoạn rời rạc | Xem lại bucketing, mô hình append-only hoặc bảng dữ liệu “đã xác nhận” | Cần đồng bộ bảng phục vụ truy vấn và quy tắc trạng thái. |
| Kiểm kê/xóa nhiều partition theo đợt | Job theo danh sách partition key, giới hạn tốc độ và checkpoint | Không nhầm token-range scan với một lệnh range tombstone xuyên partition. |
| Cần hoàn tác xóa nhầm | Backup/snapshot và quy trình restore đã kiểm chứng | Replica khác cũng có thể nhận cùng tombstone, không tự khôi phục được. |

**Lưu ý riêng cho bucketing:** nếu phải xóa nhiều hàng theo một khoảng business time, chọn bucket trùng với đơn vị lưu giữ/xóa có thể đơn giản hóa đường thao tác. Song cũng phải tránh **partition quá lớn**, số partition quá nhỏ hoặc nhân bản dữ liệu quá nhiều.

### Checklist trước khi triển khai một lệnh xóa khoảng

1. **Phạm vi:** đã biết chính xác partition key, clustering prefix và ý nghĩa hai đầu khoảng?
2. **Timestamp:** dữ liệu có các write client-supplied timestamp hay ghi muộn có thể xung đột?
3. **Replication:** RF, DC, CL và replica health có phù hợp yêu cầu xóa không?
4. **Recovery:** đã có backup/audit/khả năng phục hồi nếu xóa nhầm?
5. **Read path:** dự kiến còn bao nhiêu dữ liệu sống, bao nhiêu tombstone, truy vấn nào sẽ cắt qua khoảng đã xóa?
6. **Maintenance:** lịch repair, `gc_grace_seconds`, compaction strategy và số SSTable có được giám sát?
7. **Load:** xóa theo đợt đã có rate limit và cơ chế retry an toàn, tránh tạo quá nhiều tombstone cùng lúc?

## 12. Những nhận định đúng và sai

| Nhận định | Kết luận | Giải thích |
| --- | --- | --- |
| “Range tombstone là xóa một dải token trên toàn cluster.” | **Sai** | Nó biểu diễn xóa một khoảng **clustering key trong một partition**. |
| “Một range tombstone luôn biến thành N tombstone cho N hàng.” | **Sai** | Nó có thể được biểu diễn bằng marker ranh giới khoảng. |
| “`CLUSTERING ORDER BY ... DESC` làm dấu `>=` thành `<=`.” | **Sai** | So sánh CQL giữ ý nghĩa giá trị; thứ tự hiển thị/lưu khác với nghĩa điều kiện. |
| “Xóa khoảng có thể che dữ liệu cũ ở SSTable khác.” | **Đúng** | Trình đọc hòa giải marker với phiên bản ghi theo timestamp. |
| “Không có hàng trả về tức tombstone đã xóa vật lý.” | **Sai** | Dữ liệu cũ/marker có thể còn đến compaction/purge. |
| “`LIMIT 10` chắc chắn chỉ quét 10 hàng nguồn.” | **Sai** | Có thể cần vượt qua nhiều tombstone để tìm 10 hàng sống. |
| “Grace đã hết là compaction chắc chắn xóa mọi marker.” | **Sai** | Còn cần điều kiện purge an toàn, chồng lấn và thời điểm compaction. |
| “Repair giúp tombstone đến replica từng vắng mặt.” | **Đúng, khi thực hiện đúng** | Repair hỗ trợ hội tụ; không tự động xảy ra chỉ vì đặt `gc_grace_seconds`. |
| “Tăng RF làm tombstone trong mỗi SSTable biến mất nhanh hơn.” | **Sai** | RF tăng số replica, không trực tiếp quyết định purge trên từng node. |

## 13. Bài tập tự kiểm tra có đáp án

**Bài 1.** Bảng có `PRIMARY KEY ((device_id, event_day), event_time, event_id)`. Nếu xóa với `event_time >= 08:00 AND event_time < 09:00`, nó ảnh hưởng tới hàng nào khi partition có các mốc 07:59, 08:00, 08:30 và 09:00?

**Đáp án:** Ảnh hưởng tới các hàng **08:00 và 08:30** (và mọi `event_id` của những thời điểm ấy). 07:59 ngoài khoảng, 09:00 bị loại bởi biên `< 09:00`.

**Bài 2.** Một range tombstone có timestamp `t2`, hàng cũ trong phạm vi có timestamp `t1 < t2`. Khi đọc, hàng cũ có nên hiện lên không?

**Đáp án:** **Không.** Range tombstone che bản ghi cũ trong phạm vi. Một write hợp lệ với timestamp lớn hơn `t2` có thể lại hiện lên.

**Bài 3.** Vì sao `SELECT ... LIMIT 5` đôi khi vẫn gây cảnh báo tombstone?

**Đáp án:** Cassandra cần xét những marker/hàng bị xóa khi đi tìm **năm hàng còn sống**. Nếu nhiều hàng đầu đã bị xóa, lượng công việc nguồn có thể lớn hơn nhiều năm hàng.

**Bài 4.** Dữ liệu của một partition đã bị xóa theo khoảng tại RF = 3, `LOCAL_QUORUM` thành công, nhưng một replica đang offline. Có nên hạ `gc_grace_seconds` xuống 0 ngay để dọn đĩa?

**Đáp án:** **Không.** Replica chưa nhận tombstone có thể đưa dữ liệu cũ trở lại. Cần xử lý trạng thái replica và repair, đánh giá an toàn theo vận hành trước khi điều chỉnh grace.

**Bài 5.** Tổ chức muốn xóa mọi bản ghi của một cảm biến trong đúng ngày 21/11. Có cần tạo hàng trăm range tombstone theo từng giờ không?

**Đáp án:** **Không nhất thiết.** Với partition key `(device_id, event_day)`, có thể cân nhắc **partition deletion** cho đúng ngày đó. Dù vậy, thao tác xóa partition vẫn tạo tombstone và cần bảo đảm replica/repair.

**Bài 6.** Hệ thống đã có hai kiểu truy vấn: đọc theo partition key và quét theo token. Một range tombstone trong partition được xử lý ở kiểu nào?

**Đáp án:** **Cả hai**, nếu dữ liệu được đọc chạm phạm vi đã xóa. Token scan duyệt nhiều partition, nhưng bên trong mỗi partition vẫn phải tôn trọng row/cell/range/partition tombstone.

## 14. Tổng kết đường quyết định

~~~mermaid
flowchart TD
    A["Muốn xóa dữ liệu Cassandra"] --> B{"Xóa toàn partition?"}
    B -->|Có| P["Partition deletion theo đầy đủ partition key"]
    B -->|Không| C{"Xóa khoảng liên tục theo clustering key?"}
    C -->|Có| R["Range deletion trong một partition"]
    C -->|Không| D["Xóa row/cell hoặc thiết kế lại đường dữ liệu"]
    R --> T["Ghi range tombstone có timestamp"]
    P --> T2["Ghi partition tombstone"]
    T --> Q["Read phải hòa giải marker với dữ liệu ở memtable/SSTable"]
    T2 --> Q
    Q --> E["Repair hỗ trợ đồng bộ xóa giữa replica"]
    E --> F["Compaction chỉ purge khi đủ điều kiện an toàn"]
    F --> G["Theo dõi tombstone scan, latency, SSTable và dung lượng"]
~~~

**Ghi nhớ:** Range tombstone là **thông tin xóa một khoảng clustering key thuộc một partition**, không phải khoảng token. Nó làm các hàng cũ **biến mất về mặt logic**, nhưng dữ liệu và marker có thể vẫn tồn tại trên SSTable để giữ đúng thứ tự timestamp và bảo vệ trước replica bị chậm. Truy vấn theo khoảng phải hòa giải tất cả dữ liệu và marker liên quan; vì thế việc thiết kế partition/bucket, lựa chọn TTL hay DELETE, quản lý repair/compaction và quan sát tombstone scan quan trọng hơn chỉ nhìn số hàng mà `SELECT` trả về.
