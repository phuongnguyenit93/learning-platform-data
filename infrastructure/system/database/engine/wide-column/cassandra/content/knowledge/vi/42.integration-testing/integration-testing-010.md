# Kiểm thử phân trang khi dữ liệu thay đổi

## 1. Tình huống: trang đầu đúng nhưng cả hành trình có thể không còn là một tập dữ liệu cũ

Một API Java đọc lịch sử sự kiện thiết bị từ **Apache Cassandra**. Bảng lưu các sự kiện theo `device_id` và bucket ngày; giao diện hiển thị từng trang 20 hàng. Người dùng lấy trang đầu lúc 09:00; cùng lúc, một luồng ingestion chèn sự kiện muộn, một job TTL hết hạn các bản ghi cũ và quản trị viên sửa trạng thái sự kiện. Người dùng nhấn **Next** lúc 09:01.

Trong một test chỉ có 100 hàng bất biến, phân trang có thể chạy đúng. Nhưng khi có mutation giữa hai lần lấy trang, các câu hỏi khó xuất hiện:

- Một sự kiện được chèn **trước vị trí đã lướt qua** có xuất hiện ở các trang sau không?
- Một sự kiện được chèn **sau vị trí ấy** có làm thay đổi số hàng hoặc thứ tự của trang tiếp theo không?
- Sự kiện vừa bị `DELETE`/hết TTL có còn được trả về không?
- Giá trị một hàng đã hiển thị ở trang đầu có nhất thiết giống giá trị khi đọc lại sau đó?
- Nếu mất mạng trước khi lưu cursor, retry trang cũ có trùng hàng không?
- Nếu web client sửa filter/page size trong khi giữ nguyên paging token, có còn hợp lệ không?

**Trọng tâm bài học:** một `paging state` giúp Cassandra và Java Driver **tiếp tục từ vị trí truy vấn**, **không** biến chuỗi request thành snapshot có transaction isolation. Cần kiểm thử cả **tính đúng của API contract**, **các giới hạn mà Cassandra thực sự cung cấp** và **việc quan sát mutation mới** theo thứ tự đã kiểm soát.

Bài thuộc chương **Kiểm thử tích hợp** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, phục vụ mục tiêu hiểu mô hình wide-column, partition key, thiết kế bảng theo truy vấn, replica/coordinator, mức nhất quán đọc/ghi và kết nối Java/CQL.

**Sau bài này, người học có thể:**

1. Phân biệt `LIMIT`, **page size**, **paging state**, cursor API và keyset/seek pagination.
2. Viết dữ liệu fixture có clustering key bất biến và test toàn bộ các trang trên **dữ liệu tĩnh** trước.
3. Chủ động chèn/sửa/xóa/cho hết TTL **giữa trang 1 và trang 2** bằng barrier hoặc điểm dừng xác định, không dựa vào `Thread.sleep` đoán mò.
4. Viết integration test Java Driver 4.x với `ResultSet`, `AsyncResultSet`, `PagingState` và Testcontainers.
5. Thiết kế **keyset pagination** theo clustering key cùng high-water bound, hiểu điều mà bound có và **không có**.
6. Tách kết quả **bắt buộc đúng** khỏi hiện tượng **không được Cassandra bảo đảm** khi có mutation đồng thời.
7. Kiểm thử TTL/tombstone, consistency level, retry/restart/cursor bảo mật và dữ liệu phân nhiều bucket.
8. Tổ chức test matrix một node và multi-node, metrics, property-based/concurrency tests, runbook và checklist production.

**Phạm vi:** Ví dụ dùng Cassandra CQL 4.x, Java Driver 4.x, JUnit 5 và Testcontainers Java. Các API, package Testcontainers 1.x/2.x, cấu hình driver và hành vi thực tế theo phiên bản phải được kiểm tra bằng **resolved dependency graph + cluster integration test**. Không diễn giải các phép đo minh họa thành số liệu benchmark production.

## 2. Ba cơ chế thường bị gọi chung là “phân trang”

| Cơ chế | Ý nghĩa | Điều **không** bảo đảm |
| --- | --- | --- |
| **CQL `LIMIT 100`** | Đặt trần số hàng logic của một statement. | Không tự tạo 5 trang 20 hàng; không giới hạn số cell vật lý replica phải xét vì có tombstone/SSTable versions. |
| **Driver page size = 20** | Mục tiêu số hàng mỗi network page; driver/server có thể trả số hàng khác. | Không phải giới hạn bytes tuyệt đối và **không phải tổng số row của truy vấn**. |
| **Driver paging state** | Token opaque cho vị trí tiếp theo của **cùng statement và bind values**. | Không cung cấp database snapshot, backward paging hay truy cập ngẫu nhiên page 57 theo chi phí cố định. |
| **API cursor (do ứng dụng phát)** | Hợp đồng HTTP gồm scope/query/expiry/continuation. | Không tự bảo đảm consistency nếu chỉ bọc raw paging state. |
| **Keyset/seek cursor** | Lưu last clustering key, ví dụ `seq > lastSeen`. | Không đóng băng giá trị các hàng còn sống hay tự nhìn thấy mọi late insert. |
| **High-water bound** | Giữ trần khóa, ví dụ `seq <= H`. | Không phải snapshot: row cũ vẫn có thể bị xóa/sửa; late insertion có khóa dưới H vẫn có thể xuất hiện. |

### 2.1. `LIMIT` không giống `OFFSET`

Trong Cassandra, **`OFFSET 10000` không phải hình thức phân trang CQL tự nhiên như SQL quan hệ**. Paging state chỉ dùng để tiến **về phía trước**; muốn mở trang 10, thường phải có cursor tương ứng trang 9 hoặc phải quét/bỏ qua các hàng trước đó, gây chi phí tuyến tính.

~~~text
SQL OFFSET mental model (KHÔNG áp nguyên xi cho Cassandra):
  trang 1: OFFSET 0 LIMIT 20
  trang 2: OFFSET 20 LIMIT 20
  ...

Cassandra native paging:
  statement cố định -> page 1 + paging state S1
  cùng statement + S1 -> page 2 + paging state S2

Keyset:
  WHERE seq > lastSeq AND seq <= highWater LIMIT 20
  => mỗi lần query theo clustering key, không cần OFFSET.
~~~

**Chú ý:** `LIMIT` thuộc statement của một truy vấn, còn `page size` điều khiển cách câu trả lời được chia qua nhiều network round-trips. Không đổi `LIMIT` tùy ý trong khi dùng lại paging state cũ.

### 2.2. API đồng bộ và bất đồng bộ Java Driver 4.x

~~~mermaid
flowchart TD
    A["CqlSession + BoundStatement"] --> B{"Cách thực thi"}
    B -->|execute| C["ResultSet"]
    C --> D["Duyệt iterator; driver tự fetch khi cần"]
    B -->|executeAsync| E["CompletionStage<AsyncResultSet>"]
    E --> F["Duyệt currentPage"]
    F --> G{"hasMorePages?"}
    G -->|Có| H["fetchNextPage + thenCompose"]
    H --> F
    G -->|Không| I["Kết thúc workflow"]
    D --> I
~~~

Với API sync, `ResultSet` có thể fetch thêm trang khi iterator đi quá phần đã nhận; với API async, `AsyncResultSet.currentPage()` **chỉ chứa trang hiện tại**, muốn tiếp phải `fetchNextPage()`. `CompletionStage` hoàn tất cho trang đầu **không có nghĩa** đã đọc toàn bộ query.

## 3. Định nghĩa contract kiểm thử trước khi viết assertion

Nếu product không định nghĩa “trang tiếp theo” có ý nghĩa gì khi dữ liệu thay đổi, một test có thể **bắt bug không tồn tại** hoặc **hợp thức hóa mất dữ liệu thật**.

### 3.1. Bốn hợp đồng thường gặp

| Hợp đồng | Mô tả | Cách kiểm thử phù hợp |
| --- | --- | --- |
| **A. Duyệt dữ liệu tĩnh** | Không ai thay bảng trong toàn bộ vòng lướt. | Exact ordered IDs, số hàng, không trùng/không sót, đủ trang. |
| **B. Live feed** | Trang sau được phép phản ánh mutation xảy ra trước lần fetch. | Không hứa set cũ bất biến; kiểm tra scope, order, cursor, không leak tenant, bounded resources. |
| **C. Duyệt một khóa phạm vi cố định** | Chọn `highWater=H`; chỉ nhận khóa `<=H` và `>last`. | Không vượt H, khóa tăng, không quay về khóa đã phát; **không** tự khẳng định mọi hàng ở t0 còn tồn tại. |
| **D. Snapshot chính xác tại t0** | Mọi trang trả đúng ảnh dữ liệu tại cùng một thời điểm. | Phải có **snapshot/materialized versioned view** hoặc kiến trúc cung cấp lịch sử thích hợp. Paging state + QUORUM **không đủ**. |

Một API quản trị có thể chấp nhận B; một job xuất báo cáo theo ngày cố định có thể cần C; nghiệp vụ pháp lý/đối soát có thể cần D. **Không ghi “snapshot-consistent” trong API docs chỉ vì đã ghim page size hoặc CL.**

### 3.2. Định nghĩa các bất biến cần kiểm tra

Giả sử query đọc **một partition ngày** với clustering key `seq` tăng dần:

1. Mọi hàng trả về thuộc đúng `device_id`, `event_day` và khoảng `seq` được chấp nhận.
2. Trong **một response**, keys theo đúng thứ tự CQL; khi keyset dùng `seq > last`, các trang liên tiếp phải tiến lên.
3. Không đưa `payload`/cột nhạy cảm ngoài phạm vi authorization, dù cursor bị thay đổi.
4. Không tự trả 200 “đã đọc hết” nếu còn page và caller yêu cầu toàn bộ.
5. Không fetch vượt số trang, byte, deadline hoặc số partition mà contract cho phép.
6. **Exact equality với baseline** chỉ là assertion đúng khi dữ liệu bất biến hoặc có snapshot thực sự.

### 3.3. “Không có bản sao lưu ảnh” không có nghĩa mọi lần chạy đều sai

Trong một run, trang 2 **có thể** tình cờ giống lúc t0; trong run khác, insert/delete giữa các page có thể làm số hàng hoặc giá trị khác. Test tốt **không cưỡng ép một hiện tượng tình cờ phải xuất hiện trong mọi phiên bản**; nó chứng minh loại guarantee nào thực sự được API cung cấp và phân tích có điều kiện khi có thay đổi.

## 4. CQL fixture: bảng theo một thiết bị và bucket ngày

Để các bài test dễ diễn giải, ví dụ dùng clustering key **`seq bigint`**, do upstream **cấp duy nhất, ổn định và không sửa** trong mỗi cặp `(device_id,event_day)`. Cassandra **không tự sinh số thứ tự tăng dần** cho bạn; đây là một giả định của fixture/app data model, không được dùng counter Cassandra để tạo sequence transaction toàn cục mà không thiết kế.

### 4.1. DDL một node cho Testcontainers

~~~sql
CREATE KEYSPACE IF NOT EXISTS paging_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'datacenter1': 1
};

CREATE TABLE IF NOT EXISTS paging_lab.events_by_device_day (
  device_id text,
  event_day date,
  seq bigint,
  event_id uuid,
  event_time timestamp,
  status text,
  payload text,
  updated_at timestamp,
  PRIMARY KEY ((device_id, event_day), seq)
) WITH CLUSTERING ORDER BY (seq ASC);
~~~

**Cần phân biệt:**

- `(device_id,event_day)` là **partition key**. Cassandra hash để chọn token và natural replica; query một ngày của một thiết bị là đường đọc có scope rõ ràng.
- `seq` là **clustering key** duy nhất và có thứ tự **ASC** trong partition. Do đó keyset `seq > last` và `seq <= highWater` là biểu thức CQL tự nhiên cho fixture này.
- `event_time` là regular column trong lab. Nếu API thật cần range query theo thời gian, hãy thiết kế schema với `event_time`/tie-breaker làm clustering key, rồi xây keyset tuple tương ứng; **không giả định đọc theo time range được tối ưu khi time chỉ là regular column**.
- `status`/`payload` có thể UPDATE không đổi primary key; `DELETE` và TTL có thể tạo tombstone.
- Testcontainers **một node** dùng RF 1/`LOCAL_ONE` để chứng minh behavior client/paging, **không** chứng minh quorum/read repair, replica failure hay multi-DC.

### 4.2. DDL cho test cluster ba replica

~~~sql
-- Chỉ cho cluster test có đủ ba full replicas trong dc1.
CREATE KEYSPACE IF NOT EXISTS paging_lab_ha
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

-- Tạo bảng cùng schema ở trên dưới keyspace paging_lab_ha
-- bằng pipeline DDL test có version; không sao chép vào prod tự động.
~~~

Khi RF = 3, `LOCAL_QUORUM` cần hai replica trong local DC `dc1`. `LOCAL_QUORUM` giúp điều chỉnh mức nhất quán của từng read/write, **không tạo snapshot xuyên nhiều trang**. Một test RF 1 pass không được dùng để kết luận ứng dụng chịu được node down.

### 4.3. Seed tập khóa có khoảng trống có chủ đích

~~~sql
-- Ví dụ một số bản ghi; test Java sẽ tạo đủ 12 hàng.
INSERT INTO paging_lab.events_by_device_day
 (device_id,event_day,seq,event_id,event_time,status,payload,updated_at)
VALUES
 ('device-7','2026-11-21',10,
  123e4567-e89b-42d3-a456-426614174010,
  '2026-11-21T09:00:10Z','NEW','p10','2026-11-21T09:00:10Z');

INSERT INTO paging_lab.events_by_device_day
 (device_id,event_day,seq,event_id,event_time,status,payload,updated_at)
VALUES
 ('device-7','2026-11-21',20,
  123e4567-e89b-42d3-a456-426614174020,
  '2026-11-21T09:00:20Z','NEW','p20','2026-11-21T09:00:20Z');

INSERT INTO paging_lab.events_by_device_day
 (device_id,event_day,seq,event_id,event_time,status,payload,updated_at)
VALUES
 ('device-7','2026-11-21',30,
  123e4567-e89b-42d3-a456-426614174030,
  '2026-11-21T09:00:30Z','NEW','p30','2026-11-21T09:00:30Z');
~~~

Trước khi kiểm thử mutation, seed **12 key** `10,20,30,...,120`. Khoảng trống giữa keys cho phép chèn `35` hoặc `lastSeq+5` giữa các page; không cần thay clustering key của hàng đã có. Mỗi test nên dùng **partition ID riêng** hoặc reset trong test cluster cô lập để không phụ thuộc dữ liệu từ test khác.

## 5. Bản đồ mutation giữa hai lần fetch

~~~mermaid
sequenceDiagram
    participant Reader as Java Reader
    participant Coordinator as Cassandra coordinator
    participant Writer as Ingestion / admin
    Reader->>Coordinator: SELECT partition seq 10..120, page-size=3
    Coordinator-->>Reader: Page 1: 10,20,30 + S1
    Note over Reader: Chặn ở test barrier sau page 1
    Writer->>Coordinator: INSERT seq=35 và seq=130
    Writer->>Coordinator: UPDATE status seq=80
    Writer->>Coordinator: DELETE seq=60
    Coordinator-->>Writer: Mutation ACK theo CL
    Reader->>Coordinator: Fetch page 2 từ S1
    Coordinator-->>Reader: Trang tiếp theo theo trạng thái CQL/replica hiện tại
    Note over Reader,Coordinator: Không phải snapshot bất biến của t0
~~~

### 5.1. Bảng kỳ vọng đúng mức

| Mutation sau trang 1 | Với native paging state | Với keyset `seq > last` + `seq <= H` |
| --- | --- | --- |
| `INSERT seq=35` (sau cursor 30, dưới H=120) | Có thể ảnh hưởng tập trang tiếp; **không tuyên bố một kết quả tất định cho mọi version/cluster**. | Nếu write visible theo CL trước query mới, **có thể/được dự kiến** xuất hiện vì `35>30` và `35<=120`. |
| `INSERT seq=5` (trước cursor 30) | Không có snapshot guarantee; không dựa vào token để “tìm lại” row trước cursor. | **Không xuất hiện** ở các query `seq>30` tiếp theo; đây là semantics được thiết kế. |
| `INSERT seq=130` (cao hơn H) | Có thể nằm trong một query không ghim upper bound. | **Bị loại** nếu mọi page đều giữ `seq<=120`. |
| `UPDATE status seq=80` | Nếu đọc sau update, giá trị có thể phản ánh state mới theo CL. | Trả state mới trong SELECT sau đó; high-water **không đóng băng giá trị**. |
| `DELETE seq=60` | Row có thể không còn trong các page sau; không đòi baseline exact. | Query sau sẽ không trả row đã delete nếu deletion visible theo CL. |
| TTL của seq=100 hết hạn | Thứ tự clustering không đổi, nhưng row sống có thể biến mất. | Tương tự; `H` chỉ giới hạn khóa, không bảo vệ lifetime. |

**Từ “có thể” không phải né tránh assertion:** Cassandra không cung cấp một snapshot giữa nhiều network pages. Test cần chứng minh **đường mutation được chèn đúng thời điểm, thuộc đúng partition, ghi đủ ACK** và sau đó kiểm tra các bất biến của **contract đã chọn**, thay vì đoán một ảnh t0 không tồn tại.

## 6. Keyset pagination: cursor bằng clustering key có định nghĩa

Đối với bảng có `seq` bất biến, endpoint có thể truy vấn:

~~~sql
-- Trang đầu theo keyset: lastSeq = 0, H = 120.
SELECT seq, event_id, event_time, status
FROM paging_lab.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND seq > 0
  AND seq <= 120
LIMIT 3;

-- Khi trang đầu trả 10,20,30, trang sau:
SELECT seq, event_id, event_time, status
FROM paging_lab.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND seq > 30
  AND seq <= 120
LIMIT 3;
~~~

Vì CQL ordering trong partition là ASC, `lastSeq` của trang trước xác định phạm vi trang tiếp. Không dùng `OFFSET`; mỗi query mới có **partition key đầy đủ + clustering range có bound**, dùng CQL `LIMIT` theo kích thước trang nghiệp vụ.

### 6.1. Lấy high-water khi bắt đầu vòng đọc

~~~sql
SELECT seq
FROM paging_lab.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
ORDER BY seq DESC
LIMIT 1;
~~~

Nếu kết quả lớn nhất là `120`, phát cursor với `H=120` và giữ nó qua mọi trang. **Không lấy lại H ở từng trang**, nếu mục tiêu là loại các sequence mới lớn hơn H. Tuy nhiên, những gì chưa thành công/visible tại lúc lấy H nhưng về sau được ghi với `seq<=H` vẫn có thể xuất hiện; những hàng bị xóa hoặc TTL hết hạn có thể biến mất.

### 6.2. High-water không phải “snapshot tại t0”

~~~text
Tại t0:
  Các seq tồn tại: [10,20,30,40,50,60,70,80,90,100,110,120]
  H = 120
  Trang 1: [10,20,30]

Tại t1:
  INSERT seq=35, DELETE seq=60, UPDATE seq=80 status=PROCESSED
  INSERT seq=130

Trang 2 có WHERE 30<seq<=120:
  seq=35 đủ điều kiện
  seq=60 đã xóa không còn hàng sống
  seq=80 có thể mang status mới
  seq=130 bị loại do H
~~~

Hữu ích cho **bounded scrolling**, không phải báo cáo audit bất biến. Nếu phải xuất **đúng dữ liệu tại t0**, cân nhắc **materialize snapshot**, versioned immutable projection hoặc pipeline CDC/event log với mốc commit/offset đã được thiết kế, thay vì gọi cursor là snapshot.

### 6.3. Khi timestamp là clustering key

Nếu bảng thật là `PRIMARY KEY ((device_id,event_day),event_time,event_id)`, một cursor chỉ lưu `event_time` có thể **làm mất hàng có cùng timestamp**. Cần lưu **đủ tuple clustering `(event_time,event_id)`** và dùng phép so CQL tuple phù hợp với thứ tự ASC/DESC của bảng:

~~~sql
-- Chỉ minh họa cho bảng có clustering order ASC cả hai cột:
SELECT event_time, event_id, status
FROM telemetry.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND (event_time, event_id) > (?, ?)
LIMIT 20;
~~~

Trong bảng có `CLUSTERING ORDER BY event_time DESC` hoặc thứ tự hỗn hợp, toán tử cursor và logic merge phải đổi tương ứng. Không sử dụng Java `UUID.compareTo` để tự suy ra thứ tự byte UUID mà CQL dùng khi chưa kiểm chứng; test các trường hợp **nhiều event trùng timestamp** và ranh giới bucket.

## 7. Một test tốt cần phân biệt ba tập giá trị

~~~text
baseline_at_t0:
  Set các seq đã seed và xác nhận trước khi fetch page 1.

observed_pages:
  Những seq/giá trị reader thực sự thấy qua các page.

final_state_at_t2:
  SELECT độc lập sau khi mutations đã ACK.
~~~

- Test **tĩnh**: có thể assert `observed_pages == baseline_at_t0` và thứ tự chính xác.
- Test **live native paging**: assert scope/query identity, giới hạn, lỗi đúng loại; ghi lại diff `observed - baseline` và `baseline - observed` để phân tích, **không coi chúng luôn là bug**.
- Test **keyset với H**: assert không có `seq>H`, keys tăng `seq>last`, không có duplicate key ở các page thành công khi clustering key bất biến; có thể assert insert 130 bị loại.
- **Không suy từ observed == final_state** rằng mutation xảy ra trước page 1; đó là state cuối khi test kiểm tra.

### 7.1. Khi nào được assert chính xác dữ liệu mới?

Nếu test chủ động làm:

1. Fetch xong trang 1 và giữ `lastSeq`.
2. Gửi `INSERT seq=lastSeq+5`, chờ **ACK**.
3. Dùng query keyset `seq > lastSeq AND seq <= H` trên **cùng partition** sau ACK.
4. Không có writer khác/TTL/delete, chọn CL thích hợp với topology,

thì việc mong nhìn thấy `lastSeq+5` trong phần kết quả **phù hợp với hợp đồng**, nếu key trong khoảng. Nhưng trong native paging state, không đặt cùng một assertion cho mọi version mà không có một bảo đảm rõ ràng về ảnh dữ liệu xuyên các page.

## 8. Chuẩn bị Testcontainers, JUnit 5 và Java Driver 4.x

### 8.1. Chọn một bộ thư viện đồng nhất

Ví dụ bên dưới dùng **Testcontainers Java 2.0.x** và import `org.testcontainers.cassandra.CassandraContainer`. Testcontainers 1.x có **tọa độ artifact/package khác** (ví dụ `org.testcontainers:cassandra` và `org.testcontainers.containers.CassandraContainer`). Không trộn file POM của 2.x với import của 1.x.

~~~xml
<!-- Maven dependency snippets cho test Java 17.
     Phiên bản chỉ là mốc lab minh họa; dự án thật dùng BOM,
     patch đã duyệt và dependency graph được kiểm chứng. -->
<dependencies>
  <dependency>
    <groupId>com.datastax.oss</groupId>
    <artifactId>java-driver-core</artifactId>
    <version>4.18.1</version>
  </dependency>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-cassandra</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

**Không có ý khuyên dùng chính xác các patch này cho mọi môi trường 2026**. Kiểm tra repository dependency, tương thích JDK/Spring Boot BOM và security policy của hệ thống. Nếu dùng Testcontainers 1.x, cần đổi **artifact/package** theo release line, không chỉ sửa version.

### 8.2. Những gì Testcontainers một node chứng minh

**Chứng minh được:** Java Driver kết nối native protocol, CQL schema/mapping, read/write/Delete, per-page APIs, cursor reuse, behavior keyset có thể điều khiển và code xử lý lỗi.

**Không chứng minh được:** replica consistency khi có node down, quorum RF=3, topology changes, repair/streaming, multi-DC failover hoặc khác biệt khi replica chưa hội tụ. Các test đó cần **cluster test nhiều node** hoặc môi trường staging cô lập.

> **Lưu ý về tool:** Testcontainers cần Docker/container runtime trong CI. Bài này cung cấp ví dụ, **không chạy Docker/Maven trong workspace Worker**, vì bước hiện tại chỉ viết kiến thức.

## 9. Java fixture: tạo schema và seed dữ liệu tách biệt cho từng test

Đoạn sau là một **class JUnit 5 tự chứa** cho Testcontainers Java 2.0.x theo API được minh họa trong tài liệu của dự án. Dùng partition key riêng cho mỗi test để chúng không tranh nhau một hàng. Trong thực tế, project nên đặt package/import tương ứng.

~~~java
// CassandraPagingIT.java — phần fixture & baseline test
package example.paging;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.stream.LongStream;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.cassandra.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
public class CassandraPagingIT {
    private static final LocalDate DAY = LocalDate.of(2026, 11, 21);
    private static CqlSession session;
    private static PreparedStatement bounded;

    @Container
    static final CassandraContainer CASSANDRA =
        new CassandraContainer(DockerImageName.parse("cassandra:4.1.4"));

    @BeforeAll
    static void setup() {
        session = CqlSession.builder()
            .addContactPoint(CASSANDRA.getContactPoint())
            .withLocalDatacenter(CASSANDRA.getLocalDatacenter())
            .build();

        // 'datacenter1' là local DC của fixture container này;
        // nếu override CASSANDRA_DC thì phải sửa DDL cho phù hợp.
        session.execute(
            "CREATE KEYSPACE IF NOT EXISTS paging_lab " +
            "WITH replication = {'class':'NetworkTopologyStrategy'," +
            "'datacenter1':1}");
        session.execute(
            "CREATE TABLE IF NOT EXISTS paging_lab.events_by_device_day (" +
            "device_id text, event_day date, seq bigint, " +
            "event_id uuid, event_time timestamp, status text, " +
            "payload text, updated_at timestamp, " +
            "PRIMARY KEY ((device_id,event_day),seq)) " +
            "WITH CLUSTERING ORDER BY (seq ASC)");

        bounded = session.prepare(
            "SELECT seq,event_id,event_time,status " +
            "FROM paging_lab.events_by_device_day " +
            "WHERE device_id=? AND event_day=? " +
            "AND seq>? AND seq<=?");
    }

    @AfterAll
    static void close() {
        if (session != null) session.close();
    }

    static String newDevice() {
        return "test-" + UUID.randomUUID();
    }

    static void seed(String deviceId, int count) {
        PreparedStatement insert = session.prepare(
            "INSERT INTO paging_lab.events_by_device_day " +
            "(device_id,event_day,seq,event_id,event_time,status,payload,updated_at) " +
            "VALUES (?,?,?,?,?,?,?,?)");
        for (int i = 1; i <= count; i++) {
            long seq = i * 10L;
            Instant time = Instant.parse("2026-11-21T09:00:00Z")
                .plusSeconds(i);
            session.execute(insert.bind(
                deviceId, DAY, seq, UUID.randomUUID(),
                time, "NEW", "p" + seq, time));
        }
    }

    static BoundStatement query(String device, long after, long highWater) {
        return bounded.bind(device, DAY, after, highWater)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE)
            .setPageSize(3);
    }

    @Test
    void staticDataMustReadAllRowsExactlyOnce() {
        String device = newDevice();
        seed(device, 12);

        List<Long> actual = new ArrayList<>();
        ResultSet result = session.execute(query(device, 0, 120));
        for (Row row : result) {
            actual.add(row.getLong("seq")); // Sync iterator tự fetch thêm.
        }

        List<Long> expected = LongStream.rangeClosed(1, 12)
            .map(i -> i * 10L).boxed().toList();
        assertEquals(expected, actual);
        assertEquals(actual.size(), actual.stream().distinct().count());
    }
}
~~~

**Để dùng các đoạn code ở những mục sau:** có thể thêm các method vào `CassandraPagingIT` hoặc tách thành helper class và inject `CqlSession`. Không chép nhiều định nghĩa `package`/`class` vào cùng một file Java. Seed ở đây dùng row IDs ngẫu nhiên nhưng **clustering key/seq xác định**, vì phép test đang kiểm tra thứ tự theo `seq`, không theo UUID.

### 9.1. Vì sao không dùng một partition chung cho mọi test?

Nếu hai test cùng dùng `device-7` và `event_day=2026-11-21`, test chèn `seq=35` có thể làm test baseline thất bại tùy thứ tự chạy. Testcontainers sạch khi khởi động **không ngăn các test trong cùng lớp/chạy song song phá fixture của nhau**. Dùng partition key có UUID test, tách keyspace/schema version khi cần và không dùng `TRUNCATE` toàn bảng trong test chạy song song.

### 9.2. Điều kiện consistency khi test một node

RF=1 và `LOCAL_ONE` là lựa chọn phù hợp cho test client behavior. Khi `session.execute(insert)` trả ACK, lần read tiếp theo trong cluster test một node có thể quan sát mutation đã hoàn tất, giả định không có write cạnh tranh/timestamp bất thường. Nhưng **đó không phải bằng chứng RF=3/`LOCAL_QUORUM` hay nhất quán toàn DC**.

## 10. Java Driver đồng bộ: lấy paging state rồi chủ động dừng đúng cuối trang

Tài liệu Driver 4.x cảnh báo rằng phải **tiêu thụ hết trang hiện tại** trước khi dùng paging state để chạy tiếp. Nếu bạn lấy state sau trang đầu rồi mới đọc **một nửa số hàng của trang ấy**, khi resume sẽ bắt đầu ở **đầu trang kế**, làm mất phần chưa tiêu thụ của trang cũ.

~~~java
// Thêm method vào class CassandraPagingIT ở mục 9.
import com.datastax.oss.driver.api.core.cql.PagingState;

@Test
void rawPagingStateResumesOnlyAfterFullyConsumedFirstPage() {
    String device = newDevice();
    seed(device, 12);

    BoundStatement statement = query(device, 0, 120);
    ResultSet first = session.execute(statement);
    PagingState next = first.getExecutionInfo().getSafePagingState();

    List<Long> received = new ArrayList<>();
    // Chỉ đọc hàng ĐÃ TẢI của trang hiện tại; không kích hoạt fetch kế.
    while (first.getAvailableWithoutFetching() > 0) {
        Row row = first.one();
        if (row != null) received.add(row.getLong("seq"));
    }

    assertNotNull(next); // Fixture nhiều hơn page-size=3.

    BoundStatement resumed = statement.setPagingState(next);
    for (Row row : session.execute(resumed)) {
        received.add(row.getLong("seq"));
    }

    List<Long> expected = LongStream.rangeClosed(1, 12)
        .map(i -> i * 10L).boxed().toList();
    assertEquals(expected, received);
}
~~~

**Giải thích:**

- `getExecutionInfo().getSafePagingState()` trả **safe wrapper** kiểm tra state có hợp với query/bind values, không phải bằng chứng snapshot hay chữ ký bảo mật.
- `getAvailableWithoutFetching()` và `one()` được dùng để bảo đảm **đã tiêu thụ hết các row hiện tải** trước khi resume.
- `statement.setPagingState(next)` tái dùng **cùng CQL và các bind values**. Nếu đổi `device_id`, `event_day` hoặc range, state cũ không hợp lệ.
- Test có dữ liệu **tĩnh**, nên expected exact đủ 12 seq là hợp lệ.
- Với yêu cầu HTTP, phải lưu cursor **chỉ sau khi đã quyết định những row nào thuộc response**, để không tạo khoảng gap giữa phần đã trả và trang tiếp.

### 10.1. Không gửi raw state sang browser như một ID được tin cậy

Safe wrapper của Driver dùng kiểm tra tương thích câu lệnh, **không phải cryptographic MAC**. Raw paging token không phải proof rằng người dùng được đọc partition. Theo tài liệu Driver, token có thể bị thao tác để chỉ sang những phạm vi khác nếu ứng dụng không xác thực/bảo vệ đúng. **Ký/niêm phong cursor ở tầng API** và luôn kiểm tra authorization cho tenant/device.

## 11. Java Driver async: mỗi page chỉ được xử lý một lần

Ví dụ này minh họa `AsyncResultSet` và chuỗi `thenCompose`. Nó tránh block trong callback và đếm các trang đã fetch; việc chờ `get()` chỉ xảy ra **tại biên JUnit test**.

~~~java
// Helper bổ sung cho CassandraPagingIT.
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

private static CompletionStage<List<Long>> consumePages(
        AsyncResultSet page, List<Long> seen) {
    for (Row row : page.currentPage()) {
        seen.add(row.getLong("seq"));
    }
    if (!page.hasMorePages()) {
        return CompletableFuture.completedFuture(seen);
    }
    return page.fetchNextPage().thenCompose(
        next -> consumePages(next, seen));
}

@Test
void asyncMustFetchAllPagesForStaticData() throws Exception {
    String device = newDevice();
    seed(device, 12);

    CompletionStage<List<Long>> workflow =
        session.executeAsync(query(device, 0, 120))
            .thenCompose(first -> consumePages(first, new ArrayList<>()));

    // JUnit/CLI boundary được phép block; callback không block.
    List<Long> actual = workflow.toCompletableFuture()
        .get(10, TimeUnit.SECONDS);

    List<Long> expected = LongStream.rangeClosed(1, 12)
        .map(i -> i * 10L).boxed().toList();
    assertEquals(expected, actual);
}
~~~

**Bài học:** `executeAsync` hoàn tất với **trang đầu**; nếu `hasMorePages()` mà không `fetchNextPage()`, code sẽ trả thiếu dữ liệu ngay cả khi Cassandra hoàn toàn khỏe. Tính đúng này phải được test **trước** khi thêm writers đồng thời, nếu không một bug Java pagination sẽ bị hiểu nhầm là hệ quả của mutation.

### 11.1. Giới hạn điểm nguy hiểm của ví dụ

Helper `consumePages` tích lũy toàn bộ seq trong một `List`. Với fixture **12 rows** điều đó ổn, nhưng production cần trần **rows, bytes, pages, deadline** và bounded downstream consumer. Không áp dụng method này cho `SELECT` toàn bộ keyspace hay partition nhiều triệu hàng; không tạo `CompletableFuture` vô hạn để fetch đồng thời mọi trang.

### 11.2. Đừng dùng `join()` bên trong completion callback

~~~java
// PHẢN MẪU: có thể chặn driver completion/event-loop thread.
return session.executeAsync(statement).thenApply(page ->
    page.fetchNextPage().toCompletableFuture().join());

// Hướng đúng: compose stage bất đồng bộ.
return session.executeAsync(statement).thenCompose(page ->
    page.hasMorePages()
        ? page.fetchNextPage()
        : CompletableFuture.completedFuture(page));
~~~

Đây là **hai snippet minh họa trong một method**, không phải code đủ import/class; method thứ hai trả về trang thứ hai nếu có, **không chứa lại trang đầu**. Nếu cần dữ liệu từ cả hai, phải xử lý trang đầu trước khi chuyển sang next page.

## 12. Chèn mutation sau khi nhận trang đầu: test tránh suy luận snapshot

### 12.1. Điểm dừng phải nằm giữa hai lần fetch

Trong một test đơn giản, không cần tạo hàng trăm threads để hy vọng race. Ta cố ý:

~~~text
T0: Seed keys 10,20,...120
T1: Reader execute SELECT, nhận first page, lưu safe paging state
T2: Duyệt đúng các row của first page
T3: Writer INSERT seq=(lastSeen+5), INSERT seq=130,
    UPDATE status seq=80, DELETE seq=60; chờ ACK
T4: Reader resume bằng cùng statement + paging state
T5: Log observed keys/values, so contract live paging
~~~

Đây là **deterministic orchestration**, không phải bảo đảm **deterministic visibility semantics** của paging state trên mọi Cassandra version. Ranh giới mutation được kiểm soát; outcome có thể khác theo server paging internals và consistency.

### 12.2. Java test: mutation được ACK trước khi resume

~~~java
// Thêm vào CassandraPagingIT:
@Test
void pagingStateIsNotAnImmutableSnapshotUnderMutations() {
    String device = newDevice();
    seed(device, 12);
    BoundStatement original = query(device, 0, 120);
    ResultSet first = session.execute(original);
    PagingState state = first.getExecutionInfo().getSafePagingState();
    assertNotNull(state);

    List<Long> observed = new ArrayList<>();
    while (first.getAvailableWithoutFetching() > 0) {
        Row row = first.one();
        if (row != null) observed.add(row.getLong("seq"));
    }
    long last = observed.get(observed.size() - 1);
    // Fixture có khoảng 10 giữa các seq; page 1 dự kiến đọc ít hơn 12.
    assertTrue(last + 5 < 120);

    Instant now = Instant.parse("2026-11-21T10:00:00Z");
    PreparedStatement insert = session.prepare(
        "INSERT INTO paging_lab.events_by_device_day " +
        "(device_id,event_day,seq,event_id,event_time,status,payload,updated_at) " +
        "VALUES (?,?,?,?,?,?,?,?)");

    // Mutate sau page 1 nhưng trước khi fetch tiếp.
    session.execute(insert.bind(
        device, DAY, last + 5, UUID.randomUUID(),
        now, "LATE", "late-in-window", now));
    session.execute(insert.bind(
        device, DAY, 130L, UUID.randomUUID(),
        now, "LATE", "beyond-watermark", now));
    session.execute(
        com.datastax.oss.driver.api.core.cql.SimpleStatement.newInstance(
            "UPDATE paging_lab.events_by_device_day " +
            "SET status=? WHERE device_id=? AND event_day=? AND seq=?",
            "PROCESSED", device, DAY, 80L));
    session.execute(
        com.datastax.oss.driver.api.core.cql.SimpleStatement.newInstance(
            "DELETE FROM paging_lab.events_by_device_day " +
            "WHERE device_id=? AND event_day=? AND seq=?",
            device, DAY, 60L));

    // Giữ nguyên query/params; state tiếp từ vị trí cũ, không chụp t0.
    ResultSet resumed = session.execute(original.setPagingState(state));
    for (Row row : resumed) observed.add(row.getLong("seq"));

    assertFalse(observed.isEmpty());
    assertTrue(observed.stream().allMatch(s -> s > 0 && s <= 120));

    // KHÔNG assert exact == [10..120] hoặc bắt buộc có/không có 35/60.
    // Thay vào đó ghi kết quả để so với contract live paging của ứng dụng.
    System.out.println("observed=" + observed);
}
~~~

**Vì sao không dùng `assertEquals(baseline,observed)`?** Chính test vừa thay đổi dữ liệu giữa các request. Paging state **không hứa snapshot**, do đó exact baseline là assertion của hợp đồng khác. Test vẫn chứng minh một điểm quan trọng: code dùng paging state đúng statement, mutation có ACK đúng thời điểm, không trả ra ngoài `seq<=120`. Với query native paging chưa ghim upper bound thì cần thiết kế/assert khác.

### 12.3. Việc UPDATE một regular column không thay đổi khóa thứ tự

`UPDATE status` của `seq=80` không đổi `seq`; nếu row ấy được đọc **sau** UPDATE, payload mới có thể được thấy theo CL. Một UI trước đó đã hiển thị `status=NEW` ở trang đầu có thể thấy `status=PROCESSED` khi refresh. **Không có row version/snapshot** thì test không nên hứa giá trị sẽ bất biến xuyên nhiều trang.

### 12.4. Đừng “chuyển” clustering key bằng UPDATE

Trong Cassandra, primary key không cập nhật tại chỗ. Để “dời” event từ `seq=40` sang `seq=45`, ứng dụng thường phải **INSERT key mới + DELETE key cũ**. Đây là **hai identity/operation** có thể gây gap/trùng khi paging, đặc biệt nếu không có transaction workflow. Test nên có tình huống rekey/late correction riêng và hợp đồng idempotency rõ.

## 13. Test keyset có thể khẳng định chính xác trong điều kiện kiểm soát

Khác native paging-state giữa nhiều pages của một statement, **mỗi keyset page là một CQL query mới** với `WHERE seq > last`. Điều đó cho phép viết **hợp đồng rõ ràng**: hàng chèn sau cursor nhưng trong upper bound có thể được thấy ở trang tiếp; hàng chèn trước cursor **cố ý không được quay lại**.

### 13.1. Helper trả một trang CQL `LIMIT` rõ ràng

~~~java
// Thêm vào CassandraPagingIT ở mục 9.
record EventView(long seq, String status) {}

private static List<EventView> seekPage(
        String device, long after, long highWater, int limit) {
    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException("Invalid page limit");
    }

    PreparedStatement seek = session.prepare(
        "SELECT seq,status FROM paging_lab.events_by_device_day " +
        "WHERE device_id=? AND event_day=? " +
        "AND seq>? AND seq<=? LIMIT ?");

    BoundStatement statement = seek.bind(
            device, DAY, after, highWater, limit)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE)
        .setPageSize(3);

    // LIMIT=limit không đồng nghĩa chỉ có một network page.
    List<EventView> output = new ArrayList<>();
    for (Row row : session.execute(statement)) {
        output.add(new EventView(
            row.getLong("seq"), row.getString("status")));
    }
    return output;
}
~~~

**Trong production**, giữ `PreparedStatement` sống lâu thay vì `prepare` mỗi lần như helper minh họa. Dù CQL có `LIMIT 3`, `page-size` vẫn là hint của network paging; helper này duyệt hết kết quả **bounded** để có đúng số hàng logic theo CQL.

### 13.2. Thử chèn, xóa, update và ghim upper bound

~~~java
// Thêm vào CassandraPagingIT.
@Test
void keysetHasDefinedLiveWindowSemantics() {
    String device = newDevice();
    seed(device, 12);
    long highWater = 120L; // Giá trị xác định trước mọi mutation.

    List<EventView> first = seekPage(device, 0, highWater, 3);
    assertEquals(List.of(10L, 20L, 30L),
        first.stream().map(EventView::seq).toList());
    long last = first.get(first.size() - 1).seq();

    Instant when = Instant.parse("2026-11-21T10:00:00Z");
    PreparedStatement insert = session.prepare(
        "INSERT INTO paging_lab.events_by_device_day " +
        "(device_id,event_day,seq,event_id,event_time,status,payload,updated_at) " +
        "VALUES (?,?,?,?,?,?,?,?)");

    // Một key giữa hai hàng cũ và một key vượt upper bound.
    session.execute(insert.bind(
        device, DAY, 35L, UUID.randomUUID(), when,
        "LATE", "mid-range", when));
    session.execute(insert.bind(
        device, DAY, 130L, UUID.randomUUID(), when,
        "LATE", "outside-upper", when));

    // Một key nhỏ hơn cursor: cố ý sẽ không xuất hiện ở các trang sau.
    session.execute(insert.bind(
        device, DAY, 5L, UUID.randomUUID(), when,
        "LATE", "before-cursor", when));
    session.execute(
        com.datastax.oss.driver.api.core.cql.SimpleStatement.newInstance(
            "DELETE FROM paging_lab.events_by_device_day " +
            "WHERE device_id=? AND event_day=? AND seq=?",
            device, DAY, 60L));
    session.execute(
        com.datastax.oss.driver.api.core.cql.SimpleStatement.newInstance(
            "UPDATE paging_lab.events_by_device_day " +
            "SET status=? WHERE device_id=? AND event_day=? AND seq=?",
            "PROCESSED", device, DAY, 80L));

    List<EventView> all = new ArrayList<>(first);
    while (true) {
        List<EventView> page = seekPage(device, last, highWater, 3);
        if (page.isEmpty()) break;
        assertTrue(page.get(0).seq() > last);
        all.addAll(page);
        last = page.get(page.size() - 1).seq();
    }

    List<Long> actual = all.stream().map(EventView::seq).toList();
    assertEquals(
        List.of(10L,20L,30L,35L,40L,50L,70L,80L,90L,100L,110L,120L),
        actual);
    assertFalse(actual.contains(5L));   // Insert trước cursor.
    assertFalse(actual.contains(60L));  // Delete sau page 1.
    assertFalse(actual.contains(130L)); // Vượt highWater.
    assertTrue(all.stream().anyMatch(
        e -> e.seq() == 80L && "PROCESSED".equals(e.status())));
}
~~~

**Tại sao test này có thể assert chính xác?** Mọi mutation được **ACK trước khi gửi page keyset kế tiếp**, dùng một replica lab, không có writer/TTL khác, `seq` không đổi và mỗi trang có `WHERE seq>last AND seq<=120`. Nó kiểm tra **contract live-keyset mà app định nghĩa**, không cố chứng minh native paging state tạo snapshot.

### 13.3. Một giới hạn hữu ích của test

Nếu thay `seq` bằng `event_time` có độ chính xác mili giây và hai hàng cùng timestamp, một cursor chỉ lưu timestamp có thể gây gap. Cần key phụ `event_id` trong **full clustering tuple**. Nếu dữ liệu cho phép sửa khóa thứ tự hoặc late data có `seq<=last`, **không thể bảo đảm** mọi hàng mới đều được thấy bằng seek forward-only. Các test phải phản ánh chính sách late arrivals.

### 13.4. Không gán nghĩa “không trùng” cho mọi tình huống

Keyset đơn giản với **clustering key bất biến, một partition, duyệt forward, không rekey và không thay query** tránh việc quay về khóa đã đi qua. Nhưng nếu ứng dụng **lặp lại cùng cursor sau HTTP retry rồi append hai page vào cùng kết quả**, duplicate có thể xuất hiện ở **tầng consumer**. Kết quả dedup cần khóa nghiệp vụ/idempotency; chưa kể một logical event có thể được ghi thành **hai primary keys khác nhau** do producer sửa key.

## 14. Test TTL: biến mất giữa các trang không đồng nghĩa thiếu ACK

TTL làm một cell/hàng hết hạn **theo thời gian ghi và semantics Cassandra**, không theo việc client đã fetch trang đầu. Nếu `seq=80` sẽ hết TTL trước khi trang chứa nó được đọc, một vòng scan không snapshot có thể không trả hàng này.

### 14.1. Dữ liệu lab TTL

~~~sql
-- Row mới có TTL ba giây; áp dụng TTL cho các cột được ghi.
INSERT INTO paging_lab.events_by_device_day
 (device_id,event_day,seq,event_id,event_time,status,payload,updated_at)
VALUES
 ('device-ttl','2026-11-21',80,
  123e4567-e89b-42d3-a456-426614174080,
  '2026-11-21T09:01:20Z','EPHEMERAL','short-lived',
  '2026-11-21T09:01:20Z')
USING TTL 3;
~~~

### 14.2. Tổ chức test không dùng sleep mù

~~~text
1. Seed nhiều hàng ổn định ngoài seq=80.
2. Chèn một hàng seq=80 với TTL=3, ACK.
3. Đọc trang đầu có seq thấp hơn 80.
4. Bounded poll đúng key seq=80 đến khi SELECT không còn hàng sống.
   Dừng nếu quá deadline (ví dụ 10 giây), không chờ mãi.
5. Fetch trang chứa khoảng seq=80.
6. Với contract live, không assert seq=80 phải còn như tại t0.
7. Quan sát server tombstone/latency nếu cần, không coi TTL là DROP file.
~~~

Ở test này, **chờ đến khi SELECT xác nhận hàng đã hết hạn** là điểm đồng bộ dựa trên state thực, tốt hơn `Thread.sleep(3000)` rồi giả định TTL và server clock chính xác tuyệt đối tới mili giây. Dùng **Awaitility hoặc bounded polling** trong thread JUnit; không block driver I/O callback.

### 14.3. Tombstone và `gc_grace_seconds`

Hàng bị `DELETE` hoặc TTL hết hạn có thể để lại tombstone trong SSTable. Truy vấn `LIMIT 20` có thể phải duyệt nhiều phiên bản cell/tombstone trước khi tìm đủ 20 hàng sống. Test cần kiểm tra **độ trễ, tombstones scanned, SSTable count và compaction**, không suy rằng page nhỏ luôn có chi phí storage nhỏ.

Đừng giảm `gc_grace_seconds` chỉ để test thấy tombstone biến mất nhanh. Trong cluster nhiều replica, việc thu hồi tombstone trước khi replica vắng mặt được repair phù hợp có thể dẫn tới **zombie data**.

## 15. UPDATE và khóa thứ tự: kiểm tra giá trị, không chỉ row count

Một số test chỉ đếm `rowCount` sau từng trang. Điều đó không phát hiện giá trị **`status`** thay đổi từ `NEW` sang `PROCESSED` giữa hai lần fetch.

| Mutation | Identity/clustering key | Nội dung row | Assertion nên có |
| --- | --- | --- | --- |
| `UPDATE status` | Không đổi | Đổi | Kiểm tra phiên bản/contract giá trị có được phép cập nhật live. |
| `UPDATE payload` | Không đổi | Đổi | Kiểm tra column projection, không log payload nhạy cảm. |
| `DELETE` | Row trở thành không sống | Không còn trong read hiện tại khi deletion visible | Không đòi exact baseline trừ khi snapshot. |
| `INSERT seq` mới | Key mới | Hàng mới | Xem vị trí so với last cursor và H. |
| “Sửa seq” bằng INSERT+DELETE | Identity thay | Một logical event có thể xuất hiện hai key trong khoảng chuyển đổi | Test dedup/ordering/reconciliation. |

### 15.1. Nếu API cần giá trị bất biến trong một vòng duyệt

Phải thiết kế **immutable event versions** hoặc snapshot materialization:

~~~text
Thay đổi status của event v1 -> ghi event v2/version mới

Snapshot manifest tại t0:
  snapshot_id = S
  danh sách row identities + versions hoặc một projection bất biến

Phân trang:
  WHERE snapshot_id = S AND seq > lastSeq LIMIT K
~~~

Đây là **kiến trúc bổ sung**, không phải tính năng tự động của paging state. Manifest/versioned projection cần chính sách lưu trữ, TTL không làm mất snapshot trước khi hết cursor, quyền truy cập và chi phí tạo/đọc, nhất là khi dữ liệu nhiều TB.

## 16. Cursor HTTP: an toàn, có hạn dùng và gắn với quyền truy cập

### 16.1. Nội dung một cursor ở mức nghiệp vụ

~~~json
{
  "cursorVersion": 2,
  "queryName": "events_by_device_day_v2",
  "tenantScope": "tenant-a",
  "deviceId": "device-7",
  "eventDay": "2026-11-21",
  "sort": "seq-asc",
  "lastSeq": 30,
  "highWater": 120,
  "pageLimit": 20,
  "expiresAtUtc": "2026-11-21T09:15:00Z"
}
~~~

Ví dụ minh họa **keyset cursor dạng JSON trước khi niêm phong**, **không** khuyên trả nguyên payload ấy cho browser như token tin cậy. Với native state, cursor còn cần **opaque paging state, query/parameter digest, driver/schema/cursor version và page contract**; tuyệt đối không dùng paging state làm chứng cứ phân quyền.

### 16.2. Niêm phong cursor

~~~mermaid
flowchart TD
    A["Server tạo cursor payload"] --> B["Canonicalize + encode"]
    B --> C["Ký HMAC bằng server-held secret/kid"]
    C --> D["Trả token + expiry cho client"]
    D --> E["Client request Next"]
    E --> F["Server verify signature, expiry, version"]
    F --> G["Authorize user/tenant/device và filter"]
    G --> H["Resume bằng keyset hoặc paging state hợp lệ"]
~~~

**Điểm bảo mật bắt buộc:**

1. `Base64url` **không mã hóa**. Nếu cursor chứa thông tin nhạy cảm, dùng authenticated encryption hoặc chỉ lưu một **server-side cursor ID** trỏ tới state được bảo vệ.
2. `PagingState` safe wrapper dùng check tương thích query, **không phải MAC chống giả mạo**. Ký HMAC-SHA256 (hoặc giải pháp tương đương đã được review) cho envelope; quản lý khóa trong secret manager, có `kid`/rotation/expiry.
3. Bind token với **tenant, user/scope, query name, filters, sort, page size, keyspace/table version** theo hợp đồng. Server luôn **kiểm tra quyền tại mỗi lần Next**, không tin quyền đã cấp ở trang 1.
4. Chặn token quá dài/tampered/expired bằng `400` hoặc `410` theo contract; không chuyển lỗi thành `SELECT` không filter.
5. Không in token raw vào logs/traces công khai: có thể chứa thông tin định vị, là bearer capability hoặc tạo rủi ro truy cập ngoài scope.
6. Thay đổi cluster/schema/protocol có thể làm cursor cũ không dùng được. API cần **cursor versioning**, thời gian sống hợp lý và cách bắt đầu lại an toàn.
7. Replay cùng cursor **không tạo snapshot**, có thể trả nội dung khác khi dữ liệu thay đổi; muốn idempotent page payload, server phải cache phiên bản hoặc materialize snapshot.

### 16.3. Test cursor tampering

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Đổi `deviceId` trong payload | Sửa token mà không có khóa ký. | Signature fail; không chạm Cassandra với scope mới. |
| Tenant B dùng token của tenant A | Giữ signature hợp lệ nhưng khác caller. | Authorization fail, không lộ hàng tenant A. |
| Đổi filter/page size | Giữ paging state cũ. | Reject/đòi trang đầu mới, không tái dùng state trên statement khác. |
| Token hết hạn | Request sau expiry. | 400/410 theo contract, không resume mù. |
| Key `kid` đã rotate | Cursor cũ còn trong grace hay đã revoke. | Quyết định có chủ đích; không chấp nhận chữ ký không hợp lệ. |
| Copy state vào query CQL khác | Dùng safe wrapper. | Fail fast/query error; không fallback sang raw token bỏ kiểm tra. |
| Replay sau DB mutation | Gửi lại token hợp lệ. | Có thể trả state live khác; hệ không hứa idempotent snapshot. |

## 17. Bảo đảm của paging state và những giới hạn ít được để ý

### 17.1. Same query, same bind values

Tài liệu Java Driver 4.x xác nhận paging state phải được dùng với **đúng statement (CQL string + bound parameters)**. `getExecutionInfo().getSafePagingState()` cung cấp một lớp kiểm tra và `PagingState.fromString(...)`/serialization hỗ trợ lưu token; nhưng **thay một parameter hoặc câu CQL** có thể làm state không hợp lệ.

~~~java
// Ví dụ conceptual sau khi đã hoàn tất page hiện tại:
PagingState saved = result.getExecutionInfo().getSafePagingState();
String encoded = saved.toString(); // Chưa đủ để gửi public!

PagingState decoded = PagingState.fromString(encoded);
BoundStatement sameQuery = prepared.bind(
    originalDevice, originalDay, originalAfter, originalHighWater);

BoundStatement continued = sameQuery.setPagingState(decoded);
// Server/app vẫn phải verify cursor HMAC, tenant scope, expiry, schema.
~~~

Đoạn code là **trích đoạn trong method**, với biến `prepared` và parameters định nghĩa trước. Với custom codecs/simple statements, một số API cần `Session` để kiểm tra state; dùng cách được bản driver hỗ trợ.

### 17.2. Đừng lấy paging state trước khi cắt HTTP response ở giữa page

Nếu network page chứa 20 rows nhưng API chỉ gửi 10 rows rồi lưu paging state cho **page kế tiếp**, 10 rows còn lại của network page đầu **bị bỏ qua**. Có hai phương án:

- Thiết kế CQL/paging để **mỗi HTTP response tiêu thụ hết network page** (không giả định page size luôn chính xác), hoặc
- Lưu **leftover rows/cursor nội bộ** với bộ nhớ/cache có TTL hữu hạn, hoặc dùng **keyset cursor theo last row thực đã trả** thay vì raw paging state.

**Nguyên tắc:** cursor phải chỉ tới **ngay sau hàng cuối mà caller đã nhận và xác nhận theo hợp đồng**; không được chỉ tới sau một block mà app chưa đưa ra.

### 17.3. Không chia sẻ paging state giữa các partition khác nhau

Nếu API chuyển từ `device-7, 2026-11-21` sang `device-8, 2026-11-21`, phải chạy **query mới/cursor mới**. Lưu chung một raw state rồi thay bound `device_id` là vừa **sai semantic** vừa có rủi ro bảo mật.

## 18. Test concurrency bằng latch/barrier thay vì đoán thời gian

Một test “writer chạy song song với reader” thường flake vì thực tế writer có thể hoàn tất **trước trang đầu**, **giữa hai page** hoặc **sau toàn bộ scan**. Khi mục tiêu là mutation **sau page 1, trước page 2**, ta phải chủ động điều phối.

### 18.1. Các mốc có thể quan sát

~~~text
reader-thread:
  execute SELECT -> nhận page 1 -> drain page 1
  firstPageReady.countDown()
  writerFinished.await()
  fetch page 2 -> kết thúc

writer-thread:
  firstPageReady.await()
  execute mutations, chờ write ACK
  writerFinished.countDown()

test-thread:
  chờ cả hai, assert test contract và lưu trace nếu fail
~~~

Ở đây, **`CountDownLatch` chứng minh trật tự các bước trong test process**, còn Cassandra write ACK/CL cung cấp trạng thái xác nhận của mutation. Chúng **không** tạo snapshot tại server.

### 18.2. Java JUnit mẫu có điểm dừng rõ

~~~java
// Snippet thêm vào CassandraPagingIT (imports bổ sung như bên dưới).
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

@Test
void mutationHappensStrictlyBetweenPageOneAndTwo() throws Exception {
    String device = newDevice();
    seed(device, 12);
    CountDownLatch firstPageReady = new CountDownLatch(1);
    CountDownLatch writerFinished = new CountDownLatch(1);
    ExecutorService executor = Executors.newSingleThreadExecutor();

    try {
        Future<List<Long>> scan = executor.submit(() -> {
            BoundStatement stmt = query(device, 0, 120);
            ResultSet first = session.execute(stmt);
            PagingState state = first.getExecutionInfo().getSafePagingState();
            if (state == null) {
                throw new IllegalStateException(
                    "Test expected multiple server pages");
            }

            List<Long> rows = new ArrayList<>();
            while (first.getAvailableWithoutFetching() > 0) {
                Row r = first.one();
                if (r != null) rows.add(r.getLong("seq"));
            }

            firstPageReady.countDown();
            if (!writerFinished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Writer did not finish");
            }
            for (Row r : session.execute(stmt.setPagingState(state))) {
                rows.add(r.getLong("seq"));
            }
            return rows;
        });

        assertTrue(firstPageReady.await(10, TimeUnit.SECONDS));
        try {
            session.execute(
                com.datastax.oss.driver.api.core.cql.SimpleStatement.newInstance(
                    "DELETE FROM paging_lab.events_by_device_day " +
                    "WHERE device_id=? AND event_day=? AND seq=?",
                    device, DAY, 80L));
        } finally {
            // Kể cả mutation lỗi, không giữ reader chờ mãi.
            writerFinished.countDown();
        }

        List<Long> observed = scan.get(10, TimeUnit.SECONDS);
        assertTrue(observed.stream().allMatch(s -> s > 0 && s <= 120));
        // Không assert snapshot baseline chính xác dưới mutation.
    } finally {
        writerFinished.countDown();
        executor.shutdownNow();
    }
}
~~~

**Chú ý về đoạn test:**

- Thread reader có thể chờ latch ở JUnit worker thread; không chạy pattern blocking ấy trên **driver I/O callback** trong ứng dụng production.
- Nếu lỗi xảy ra trước `firstPageReady.countDown()`, test sẽ timeout có giới hạn và ghi nguyên nhân trong `Future`/log; có thể cải tiến bằng `CompletableFuture` gửi lỗi trực tiếp để giảm thời gian chờ CI.
- `shutdownNow()` chỉ dọn executor test, **không bảo đảm hủy query đã gửi trên Cassandra server**.
- Dùng **key/partition riêng** cho test; cùng session được dùng cho read/write vì Java Driver hỗ trợ concurrent requests.
- Dùng test này để xác minh **orchestration và không deadlock**, không mặc định delete phải làm row biến mất khỏi một page đã đọc trước đó.

### 18.3. Barrier cho hai writer và một reader

Một workload gần thực tế hơn có:

~~~text
writerA: INSERT key mới sau cursor
writerB: DELETE hoặc UPDATE key sắp được đọc
reader : fetch page sau khi cả hai writer ACK
~~~

Nếu cần tái hiện một thứ tự cụ thể, dùng **latch riêng cho writerA và writerB**, tránh giả định scheduler của JVM thực thi hai futures theo đúng thứ tự gọi. Nếu **cố tình** để writers tranh chấp, test phải định nghĩa outcome nào là hợp lệ (LWT vs unconditional timestamp conflict), **không assert một writer cố định luôn thắng**.

## 19. Nhiều partition/bucket: một cursor Cassandra chưa đủ cho một feed toàn cục

Với bảng time-series thực tế, mỗi ngày tạo một partition `(device_id,event_day)`. API lấy khoảng 23:45 ngày 20/11 tới 00:15 ngày 21/11 UTC phải đọc **hai partition**. Cassandra chỉ đảm bảo clustering order **bên trong từng partition**, không tạo total order xuyên hai ngày.

~~~mermaid
flowchart TD
    A["HTTP GET timeline qua 2 ngày"] --> B["Partition ngày 20/11"]
    A --> C["Partition ngày 21/11"]
    B --> D["Rows theo clustering order trong ngày"]
    C --> E["Rows theo clustering order trong ngày"]
    D --> F["Merge ở Java theo event_time + tie-breaker"]
    E --> F
    F --> G["Top K + cursor chứa state từng bucket"]
~~~

### 19.1. Điều cần nằm trong contract cursor

- **Khoảng thời gian nửa kín** `[startInclusive,endExclusive)`, timezone chuẩn UTC; `LocalDate.now()` của server không thay cho UTC event date.
- Danh sách **bucket cần đọc**, có giới hạn số ngày/partition.
- Với mỗi bucket: **last clustering tuple** hoặc **paging state riêng** và trạng thái chưa tiêu thụ.
- **Global ordering** theo event time, cộng tie-breaker duy nhất/ổn định để tránh mất sự kiện trùng timestamp.
- High-water/cursor version/deadline và các khoản chi phí retry/fan-out.

### 19.2. Mutation làm kết quả merge khác nhau

Một sự kiện **late arrival** có `event_time` thuộc ngày hôm qua nhưng được ghi hôm nay. Nó có thể:

- Nằm trong một partition mà API đã lướt qua → không xuất hiện ở trang sau nếu cursor chỉ đi tới.
- Nằm trong partition đang chuẩn bị fetch → có thể xuất hiện trong live feed.
- Thay đổi thứ tự tổng khi merge các nguồn → có thể cần tái phát/đối soát nếu sản phẩm hứa không bỏ sót mọi event.

**Đừng tuyên bố chỉ cần `thenCombine` hai query là có một snapshot chung.** Hai statement có thể chạy trên coordinator khác và tại các thời điểm khác nhau, kể cả khi cùng dùng `LOCAL_QUORUM`.

### 19.3. Test riêng cho ranh giới ngày

| Dữ liệu | Khóa/bucket | Kỳ vọng |
| --- | --- | --- |
| 2026-11-20 23:59:59.999Z | Ngày 20/11 UTC. | Thuộc bucket cũ khi query range chạm mốc này. |
| 2026-11-21 00:00:00.000Z | Ngày 21/11 UTC. | Thuộc bucket mới, không bị đếm trùng do endpoint inclusive cả hai đầu. |
| Hai event cùng timestamp | Hai ID khác nhau. | Cursor/merge phải có tie-breaker ổn định. |
| Late insert vào ngày đã lướt | Bucket cũ. | Không hứa sẽ xuất hiện nếu contract chỉ forward-only. |
| Delete trong bucket thứ hai khi bucket một đã fetch | Bucket mới. | Không giả định global snapshot. |

**CQL không hỗ trợ** lấy hàng của hai partition ngày bất kỳ và áp `ORDER BY event_time` toàn cục như một câu query SQL với một index bao phủ toàn bảng. Đây là trách nhiệm của data model/projection và tầng service.

## 20. Consistency level: thay RF/CL không biến paging thành snapshot

### 20.1. Matrix môi trường

| Environment | RF / topology | Read/write CL tham khảo | Điều test chứng minh |
| --- | --- | --- | --- |
| **Testcontainers một node** | RF=1 tại `datacenter1`. | `LOCAL_ONE`. | CQL/Java driver/paging, mutations đã ACK, cursor API. |
| **Staging ba full replicas** | RF=3 tại `dc1`. | `LOCAL_QUORUM`. | Số replica cần cho quorum, read/write khi một node chậm/down, timeout và visibility. |
| **Staging hai DC** | Ví dụ `dc1:3, dc2:3`. | Local CL mỗi DC theo policy. | Local vs cross-DC routing, replication delay/failover behavior. |
| **Production-like chaos** | Nhiều node, repair/compaction/network faults. | Theo SLO & consistency contract. | Tài nguyên/recovery, không suy “mọi trang cùng snapshot”. |

### 20.2. RF=3 với `LOCAL_QUORUM` cần gì?

Ở một DC có ba full replicas, `LOCAL_QUORUM` cần hai replica phản hồi theo operation. Cặp đọc/ghi quorum phù hợp giúp những read/write trên cùng partition có mức giao nhau theo lý thuyết quorum, nhưng:

- Hai page là **hai request ở thời điểm khác nhau**.
- Replica có thể nhận mutation mới giữa hai page.
- TTL có thể hết hạn trong lúc quét.
- Batch/workflow nhiều partition **không** tự trở thành một snapshot.
- Tombstone/repair/GC và tải hệ thống có thể làm latency khác nhau.

**Không** hạ `LOCAL_QUORUM` xuống `LOCAL_ONE` trong test rồi dùng kết quả làm bằng chứng production sẽ giống hệt. Cũng không tăng timeout để “sửa” `Unavailable` khi thiếu replica.

### 20.3. Kiểm thử replication lag và repair

Trong cluster test nhiều node, thử:

1. Chạy read baseline của một partition, ghi lại coordinator/replica và CL.
2. Tắt một full replica bằng fault injection được cho phép.
3. Ghi/delete/TTL theo CL có thể đáp ứng, theo dõi mutation acknowledgment.
4. Khôi phục replica, kiểm tra kết quả đọc sau hội tụ/repair theo runbook.
5. Đo p99/page count, tombstones, hints/repair và cảnh báo server.

Không sử dụng **một session Testcontainers RF1** để giả lập những điều này bằng cách chỉ đổi `setConsistencyLevel(LOCAL_QUORUM)`; cluster topology thật phải tồn tại.

## 21. Xử lý retry, timeout và lỗi “unknown page”

### 21.1. Hai rủi ro ngược nhau

~~~text
Client nhận page N nhưng response HTTP bị mất.
  -> Client retry cùng cursor:
     có thể thấy lại page N -> duplicate ở downstream.

Server đã advance paging state trước khi client nhận đủ rows.
  -> Client lấy cursor sau page N dù chưa nhận page N:
     mất toàn bộ page N trong tập kết quả người dùng.
~~~

Hai vấn đề xảy ra ở **tầng delivery/cursor của API**, không cần Cassandra có bug. Cursor chỉ là vị trí truy vấn, **không phải ACK end-to-end từ browser/consumer**.

### 21.2. Chính sách retry đúng mục đích

| Tình huống | Hướng xử lý |
| --- | --- |
| Read timeout một page | Retry có deadline/budget; nếu dùng cùng cursor, chấp nhận có thể nhận trang khác khi mutations xuất hiện. |
| Connection mất sau response được server tạo | Không tự suy page chưa được gửi hoặc client chưa nhận; dùng idempotency/dedup cho workflow downstream. |
| Cursor format khác sau deploy | Version/expiry check, trả lỗi tái bắt đầu hoặc migration cursor được duyệt. |
| `Unauthorized`/scope mismatch | Từ chối ngay; không retry bằng tài khoản quyền rộng hơn. |
| Page size đổi từ 20 sang 200 | Cần xác định contract cursor; không chỉ đổi một option trong khi giữ state cũ. |
| `Unavailable` tại RF/CL | Điều tra topology/availability, không tự downgrade CL. |
| TTL vừa hết hạn | Không retry vô hạn để “đọc lại hàng cũ”; phải theo live/snapshot contract. |

**Retry một SELECT** thường không có side effect ghi, nhưng vẫn tốn CPU/network/replica capacity; retry storm có thể khiến cluster tệ hơn. Tránh `while(true)` khi driver báo timeout; giữ **bounded attempts, exponential backoff + jitter và deadline tổng**.

### 21.3. Cancellation không hồi tác dữ liệu

Nếu client đóng tab sau trang 1, service nên **không fetch trang 2** khi không còn nhu cầu. Nhưng cancel Java `CompletableFuture` hoặc ngắt HTTP **không bảo đảm** Cassandra coordinator đã ngừng request đang chạy. Trong test cần đo số fetch thực, release semaphore/connection resources và không tạo background page fetching vô hạn.

## 22. Spring Data Cassandra: `Slice` là paging tiến về trước, không phải snapshot

Spring Data Cassandra cung cấp `CassandraPageRequest` và `Slice<T>` để đi từ trang này sang trang tiếp theo, theo semantics paging Cassandra. Tài liệu Spring Data nêu rõ các repositories không dùng paging/offset SQL truyền thống để nhảy ngẫu nhiên hiệu quả.

~~~java
// Trích đoạn trong integration test với Spring Data Repository phù hợp:
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

Slice<EventEntity> first =
    repository.findAll(CassandraPageRequest.first(10));

if (first.hasNext()) {
    Slice<EventEntity> second =
        repository.findAll(first.nextPageable());
    // Validate scope and mutations according to your API contract.
}
~~~

**Đây là ví dụ minh họa cách Spring Data paging**, không phải khuyến nghị chạy `repository.findAll()` trên keyspace production lớn. Hãy dùng **query có đầy đủ partition key/limit** phù hợp, hoặc `CassandraTemplate.slice(Query,Class)` với filter đúng, rồi kiểm tra method/return type theo Spring Data version được BOM pin.

### 22.1. Cần test gì khi thay Driver Core bằng Spring Data?

1. Query phát ra có **đúng full partition key và sort** hay không.
2. Có giữ **filter, sort, page size, bound values** khi gọi `nextPageable()` không.
3. `Slice.hasNext()` và việc duyệt hết rows của slice có đúng khi số row/page không cố định không.
4. Entity mapping có load `payload` lớn không cần thiết, gây GC/p99 tăng không.
5. Mutation giữa hai slices được xử lý theo **live view**, không hứa snapshot.
6. Spring Data và Java Driver versions có đồng bộ qua BOM, schema drift đã kiểm tra không.

**Một `Page<T>` có tổng số bản ghi không phù hợp mọi Cassandra query**: tổng count trên dữ liệu đang đổi cũng có thể thay đổi và COUNT trên wide partition có thể tốn chi phí. Ưu tiên `Slice`/continuation khi API chỉ cần “còn trang tiếp không”.

## 23. Ma trận integration test phải chạy trước phát hành

### 23.1. Nhóm test không có mutation

| ID | Fixture | Thao tác | Assertion mạnh |
| --- | --- | --- | --- |
| P01 | 0 hàng. | Query một partition, page size 3. | Kết quả rỗng, workflow kết thúc, không fetch vô hạn. |
| P02 | 1 hàng. | Page size 1 hoặc 20. | Trả đúng một key/value, không tạo next page không cần thiết. |
| P03 | 12 hàng, keys 10..120. | Page size 1/2/3/5/20. | Cùng exact ordered set; không duplicate/gap ở dataset tĩnh. |
| P04 | 12 hàng, `LIMIT 5`. | Page size 2. | Tổng logic tối đa 5, không dùng `LIMIT` như page size. |
| P05 | Hai partition khác `device_id`. | Chỉ query một device. | Không lẫn tenant/device/partition. |
| P06 | Cùng timestamp, nhiều event IDs. | Keyset theo full clustering tuple. | Không bỏ hàng đồng timestamp. |
| P07 | Row payload lớn. | Page size 3. | Đo bytes/heap/timeout, không giả định 3 rows là ít byte. |
| P08 | Partition có nhiều tombstones. | `LIMIT 20`. | Kết quả và p99 bounded theo policy, có cảnh báo scan nếu quá ngưỡng. |
| P09 | Cùng statement, safe paging state. | Fetch page 1 rồi resume. | Tập đủ rows khi đã drain hết page trước. |
| P10 | Đổi bound `device_id` với state cũ. | Resume sai statement. | Fail/reject, không đọc partition khác. |

### 23.2. Nhóm test có mutation giữa page 1 và page 2

| ID | Mutation có ACK giữa hai trang | Contract/điều cần chứng minh |
| --- | --- | --- |
| M01 | Insert key **sau** last cursor, `<=H`. | Keyset query mới có thể thấy key khi write visible; native paging không đòi t0 snapshot. |
| M02 | Insert key **trước** last cursor. | Keyset forward không quay lại; sản phẩm phải xử lý late arrivals bằng chính sách riêng. |
| M03 | Insert key **lớn hơn H**. | Keyset bị chặn bởi upper bound; native query không bound H thì không hứa tương tự. |
| M04 | Update `status` row chưa tới. | Giá trị mới có thể được thấy; nếu cần view bất biến, phải dùng version/snapshot. |
| M05 | Delete row chưa tới. | Đường live không cố buộc row đã bị xóa phải xuất hiện. |
| M06 | TTL hết hạn sau trang đầu. | Không nhầm row biến mất với “driver bỏ sót page”. |
| M07 | Insert+delete để “rekey”. | Có thể xuất hiện hai identity/gap; cần event dedup/reconciliation. |
| M08 | Retry cùng cursor sau HTTP response lost. | Idempotency/dedup ở client/API; không tuyên bố token là ACK. |
| M09 | Schema/query filter đổi giữa page. | Cursor invalid; versioning và error contract rõ. |
| M10 | Một replica down trước page 2. | Read CL/error/timeout theo topology thật; không so exact baseline như snapshot. |
| M11 | Multi-DC writer ở remote DC. | Kiểm tra replication visibility theo local CL, không suy đồng bộ tức thời. |
| M12 | Một partition quá nóng. | Bounded in-flight, timeout/backpressure, không retry storm. |

### 23.3. Kết quả nào nên được coi là lỗi?

**Lỗi chắc chắn của API** nếu:

- Trả row thuộc **tenant/partition ngoài filter**.
- Không trả phần row đã có trong **network page nhận được** dù response đã hứa chứa toàn bộ trang ấy.
- Dùng lại state trên query khác mà bỏ kiểm tra/authorization, dẫn đến rò dữ liệu.
- Mở hàng nghìn fetch/requests không giới hạn, vi phạm byte/deadline budgets.
- Xử lý `hasMorePages()=true` như đã hoàn tất toàn bộ query khi API hứa trả đủ rows.
- Keyset với clustering key bất biến trả ra một `seq<=last` do code tự xây query sai.
- Test với **dataset bất biến** bỏ sót/trùng key, hoặc trái với kết quả CQL tương ứng.

**Không nên gọi bug mặc định** khi trang sau live query **không còn row đã delete**, **có row được chèn muộn sau cursor**, hoặc **giá trị row vừa update khác trang trước**. Những hiện tượng này cần so với **hợp đồng đã công bố**, không phải giả định snapshot ngầm.

## 24. Property-based, fault-injection và stress tests

### 24.1. Nhiều page size trên cùng dataset tĩnh

Một property tốt:

~~~text
Given:
  partition tĩnh với ordered unique seq [10,20,...,120]

For each pageSize in [1,2,3,5,7,20]:
  đọc toàn bộ query native paging
  assert seenSeq == baseline
  assert số key trùng == 0
  assert số key ngoài partition/range == 0

Then:
  không quan tâm driver đã tạo bao nhiêu network pages chính xác;
  mục tiêu là đầy đủ, đúng thứ tự và giới hạn.
~~~

### 24.2. Random mutation schedule có seed tái lập

Đối với contract live-keyset, có thể tạo một **mô hình tham chiếu** trong bộ nhớ khi tất cả ACK được điều phối:

~~~text
randomSeed = 20261121
initialKeys = [10,20,...,120]
pageLimit in [1..10]
mutationOperations = [
  insert(seq=35), update(seq=80), delete(seq=60),
  insert(seq=130), insert(seq=5)
]

For every page boundary:
  chọn một tập mutation và ACK trước query kế tiếp
  cập nhật reference live state
  tính expected keys trong (lastSeq,H] với LIMIT K
  so CQL result với reference (trong điều kiện test một node,
      không có TTL/chưa đồng bộ khác)
~~~

**Luôn log `randomSeed`, version Cassandra/Driver, query name, mutation order, page size, `lastSeq` và `H`** khi fail để tái hiện. Tách **test semantics có guarantee** khỏi “fuzzing native paging behavior” chỉ dùng để tìm bất thường, tránh một test CI luôn đỏ vì tình huống không được snapshot guarantee.

### 24.3. Fault-injection theo mức

- **Client:** mất network trước/sau nhận page, hủy `CompletionStage`, đổi cursor, retry sau expiry, lỗi mapping/codec.
- **Coordinator:** restart node, timeout, dropped messages, driver failover, connection pool saturation.
- **Replica:** chậm GC/disk, một replica down, read repair/anti-entropy repair cần xử lý dữ liệu chưa đồng bộ.
- **Storage:** tombstones nhiều, compaction backlog, TTL expiry, SSTable size và disk full cảnh báo.
- **Schema/deployment:** đổi table/column, driver/cluster upgrade, query version và cursor format cũ.
- **Traffic:** hot partition, thundering herd next-page, hàng nghìn clients giữ cursor quá lâu.

Các test có tắt node/network phải chạy ở **cluster test chuyên biệt** có quyền và cleanup, không chạy phá production. Nếu test cần xác nhận sau repair, phải đợi **hậu điều kiện repair/data convergence** thay vì `sleep` rồi đoán.

## 25. Observability: đo cả đường trang và đường storage

### 25.1. Từ HTTP tới SSTable

~~~mermaid
flowchart TD
    A["HTTP NextPage latency, cursor validation"] --> B["Java app in-flight, queue, heap/GC"]
    B --> C["Driver statement/page latency, retries"]
    C --> D["Coordinator pending work, CL/timeouts"]
    D --> E["Replica read path, SSTables/tombstones"]
    E --> F["Compaction, repair, disk IO, network"]
~~~

| Tầng | Metrics nên có | Câu hỏi |
| --- | --- | --- |
| **API** | p50/p95/p99 từng trang, full traversal time, `next_cursor` errors, invalid/expired cursor. | Người dùng bị ảnh hưởng thế nào? |
| **Pager** | Pages fetched, logical rows returned, bytes decoded, `hasMorePages`, stop reason. | Có fetch thiếu/dư hoặc bỏ trang không? |
| **Java** | Futures/in-flight, wait/queue, heap/direct memory, allocation, GC, thread count. | Callback/collectList gây memory pressure? |
| **Driver** | Request latency, retries, coordinator, connection pool, throttler reject/delay, response size nếu hỗ trợ. | Routing/queue hay network chậm? |
| **Cassandra** | Read latency, tombstones scanned, SSTable count, `tpstats`, dropped messages, compaction backlog. | Replica quét quá nhiều tombstones hay disk nghẽn? |
| **Topology** | RF/CL, DC, node availability, streaming/repair, network RTT. | Kết quả chậm/không nhất quán do topology? |

**Không lấy trung bình p99 của từng node để tạo p99 toàn cluster.** Sử dụng histogram đúng scope và cùng cửa sổ UTC; so client p99 với coordinator/replica metrics, có traffic rate và deployment annotations trên cùng timeline.

### 25.2. Các lệnh hữu ích khi điều tra

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats paging_lab.events_by_device_day
nodetool tablehistograms paging_lab events_by_device_day
~~~

Các lệnh/counters/histogram khác nhau theo phiên bản Cassandra. `nodetool status` báo `UN` chỉ là trạng thái node, không chứng minh dữ liệu các page có snapshot hay partition không hot. Không bật tracing cho mọi query khi hệ đã quá tải; tracing có overhead và lưu metadata có thể nhạy cảm.

### 25.3. Trace một SELECT có chọn lọc

~~~sql
CONSISTENCY LOCAL_ONE;
TRACING ON;
SELECT seq, event_id, status
FROM paging_lab.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND seq > 0 AND seq <= 120
LIMIT 20;
TRACING OFF;
~~~

`CONSISTENCY` và `TRACING` là lệnh **cqlsh**, không gửi nguyên văn qua Java Driver. CQL trace có thể giúp thấy coordinator/replica/scan nhưng **không đo HTTP cursor validation, Java mapping, GC hoặc thời gian chờ consumer ACK**. Phải bổ sung tracing/metrics ở Java.

### 25.4. Không để metrics làm lộ partition keys

Label ổn định nên là `query_name`, `environment`, `local_dc`, `page_path` (native/keyset), `status`, `cursor_version` và `stop_reason`. **Không gắn `device_id`, `tenant_id`, event UUID, raw cursor hoặc payload** vào mỗi mẫu histogram; cardinality và nguy cơ rò dữ liệu tăng mạnh.

## 26. Case study: “Cassandra mất 200 bản ghi” nhưng lỗi nằm ở HTTP cursor

**Bối cảnh giả lập:** một API trả 50 sự kiện/trang. Driver page size 200 để giảm round-trips. Service lấy `ResultSet` page đầu có 200 rows, chỉ serialize **50 rows**, rồi trích raw paging state của trang đầu và trả nó thành `next` cho browser.

### 26.1. Timeline

~~~text
T0: Cassandra trả network page: rows 1..200, state trỏ tới row 201.
T1: Service trả HTTP page 1: rows 1..50 + state trỏ row 201.
T2: Browser nhấn Next, server dùng state đó.
T3: Cassandra trả từ row 201.

Rows 51..200 chưa từng được gửi cho browser.
Không có DELETE nào trong ví dụ này.
~~~

| Quan sát | Kết luận vội | Nguyên nhân đúng |
| --- | --- | --- |
| 150 rows biến mất giữa hai HTTP pages. | “Replica chưa đồng bộ.” | Cursor API đã **skip phần chưa dùng của network page**. |
| `nodetool status` tất cả `UN`. | “Không còn bug.” | Membership không sửa logic slicing ở Java. |
| Đổi `LOCAL_ONE` thành `LOCAL_QUORUM` vẫn thiếu hàng. | “Quorum không đủ.” | Lỗi do biên HTTP page ≠ network page. |
| Tăng page size lên 1000 gây thiếu nhiều hơn. | “Cassandra pagination sai khi page lớn.” | Service bỏ nhiều rows chưa trả hơn. |

### 26.2. Khắc phục

1. Tái hiện với **dataset tĩnh** nhiều hơn driver page size, chạy integration test full traversal.
2. Tách rõ HTTP page size và driver network page size; đảm bảo không bỏ những rows chưa dùng.
3. Dùng **keyset cursor theo last row thực gửi** hoặc giữ leftovers server-side với TTL/limits.
4. Đưa **cursor contract test** vào CI (50 HTTP rows, 200 driver rows; kiểm exact ordered IDs).
5. Chỉ sau khi sửa bug tĩnh, bổ sung mutation test live-feed/TTL/late-arrival.
6. Quan sát retry/duplicate semantics khi browser mất mạng; thêm dedup theo logical event ID.

**Bài học:** trước khi quy lỗi do concurrent mutation, phải chứng minh đường phân trang trên dữ liệu **bất biến** đã đúng. Một số bug “mất dữ liệu” chỉ là lỗi **biên giữa network page và HTTP page**.

## 27. Những quan niệm sai thường gặp

| Nhận định | Kết luận | Giải thích |
| --- | --- | --- |
| “`getSafePagingState()` tạo snapshot.” | **Sai** | Wrapper kiểm tra statement compatibility, không đóng băng dữ liệu. |
| “`LOCAL_QUORUM` trên mọi trang nghĩa cả lần scan là một transaction.” | **Sai** | Mỗi page là một request ở thời điểm khác nhau. |
| “Trang 1 có 20 row thì page size luôn trả đúng 20.” | **Sai** | Page size là hint, server có thể trả ít/nhiều hơn. |
| “CQL `LIMIT 100` và driver page size 100 là cùng một tùy chọn.” | **Sai** | `LIMIT` giới hạn tổng hàng logic, page size chia network responses. |
| “Chỉ cần `hasMorePages()` là đủ; không cần `fetchNextPage()`.” | **Sai** | Async API phải chủ động fetch trang kế. |
| “Duyệt sync `ResultSet` thường có thể tự fetch trang kế.” | **Đúng** | Nhưng iteration có thể block và phải đo full-consume time. |
| “`OFFSET 100000` là cách Cassandra nhảy trang tối ưu.” | **Sai** | Native CQL paging tiến về trước, offset không phải access path rẻ. |
| “Cursor chỉ lưu `event_time` luôn an toàn khi hai hàng cùng timestamp.” | **Sai** | Cần full clustering tuple/tie-breaker. |
| “High-water `seq<=H` giữ nguyên toàn bộ giá trị hàng.” | **Sai** | Update/delete/TTL/late inserts dưới H vẫn ảnh hưởng. |
| “Insert seq nhỏ hơn last cursor phải được xuất hiện ở trang sau.” | **Sai nếu dùng seek forward** | `WHERE seq>last` cố ý không quay lại; late-arrival policy phải riêng. |
| “Clustering key của Cassandra có thể `UPDATE` như regular column.” | **Sai** | Đổi khóa cần write identity mới và cleanup key cũ. |
| “Dùng raw paging token như bằng chứng được truy cập tenant khác.” | **Sai** | Token không thay authorization và cần ký/niêm phong. |
| “Base64 là mã hóa để giấu nội dung cursor.” | **Sai** | Base64 chỉ biểu diễn dữ liệu; dùng encryption khi có thông tin nhạy cảm. |
| “HMAC của cursor tạo ra consistency snapshot.” | **Sai** | Nó bảo vệ authenticity/integrity, không đóng băng hàng CQL. |
| “Gửi lại same cursor luôn trả y hệt page lần trước.” | **Sai** | Live data và TTL có thể đổi; idempotent responses cần cơ chế bổ sung. |
| “`COUNT(*)` làm một vòng paging có tổng bất biến.” | **Sai** | Count ở một thời điểm không khóa mọi mutation tiếp theo. |
| “Testcontainers một node chứng minh failover RF=3.” | **Sai** | Phải test cluster đủ replica thật. |
| “`Slice` của Spring Data Cassandra luôn cho jump page 1000 rẻ.” | **Sai** | Hướng chính là forward paging state, không offset random access. |
| “Một dataset bất biến nhưng test bỏ hàng là lỗi của code/driver cần điều tra.” | **Đúng** | Khi query và data shape không đổi, full traversal phải đủ theo contract. |
| “Không assert exact baseline dưới mutation live nghĩa không có kiểm thử.” | **Sai** | Test invariants, scope, cursor/ACL, budgets và mutation ACK vẫn rất mạnh. |
| “Bật TTL rồi `sleep(3000)` luôn là điểm đồng bộ đáng tin.” | **Sai** | Nên bounded poll cho đến khi giá trị thật hết hạn/không còn sống. |
| “Page nhỏ bảo đảm replica quét rất ít tombstone.” | **Sai** | `LIMIT`/page size không loại chi phí SSTable/tombstone scan. |
| “Fail retry/timeout có thể tạo page duplicate ở consumer.” | **Đúng** | Delivery chưa có ACK end-to-end, cần dedup hoặc cursor protocol rõ. |
| “Đổi code query/filter và giữ raw paging state cũ là vô hại.” | **Sai** | State gắn statement/values; validate version và reject cursor không phù hợp. |

## 28. Bài tập thực hành có đáp án

**Bài 1.** Một partition có 12 hàng, seq `10..120` cách nhau 10, không có writer. Driver page size 3, code duyệt toàn bộ `ResultSet`. Kết quả đúng là gì?

**Đáp án:** Trả đủ ordered seq `[10,20,30,40,50,60,70,80,90,100,110,120]`, không trùng/không sót. Không buộc phải assert chính xác bốn network pages vì page size là hint.

**Bài 2.** `executeAsync()` trả `AsyncResultSet`, `currentPage()` có ba hàng, `hasMorePages()=true`. Nếu API trả luôn ba hàng và báo “toàn bộ dữ liệu”, lỗi ở đâu?

**Đáp án:** Lỗi **Java async pagination** vì chưa dùng `fetchNextPage()` và hợp nhất các trang. Cassandra không hứa trang đầu chứa cả query.

**Bài 3.** Ứng dụng lấy paging state của network page gồm 200 row, chỉ gửi 50 row đầu cho browser, rồi dùng state ấy để lấy trang sau. Hàng nào có thể bị bỏ?

**Đáp án:** 150 hàng còn lại (rows 51–200) của network page hiện tại; state đã trỏ tới **trang network tiếp**, không phải hàng thứ 51. Cần drain/giữ leftovers hoặc dùng keyset theo last row thực trả.

**Bài 4.** Khi dùng `LOCAL_QUORUM`, vì sao hai page vẫn không tạo snapshot?

**Đáp án:** CL điều khiển yêu cầu phản hồi replica **của từng statement**. Mutation xảy ra giữa hai statements vẫn có thể được thấy ở page sau; không có transaction/snapshot xuyên hai page.

**Bài 5.** Trang keyset đầu trả seq `10,20,30`, `H=120`. Sau đó chèn `seq=35` và ACK, trang sau query `seq>30 AND seq<=120 LIMIT 3`. Có thể mong trả key nào trên fixture một node không writer khác?

**Đáp án:** `[35,40,50]`, vì 35 nằm trong khoảng sau cursor, còn 40/50 là các key tiếp. Đây là assertion của **keyset live contract**, không phải bằng chứng native paging state có snapshot.

**Bài 6.** Cùng tình huống trên, chèn thêm `seq=5`. Tại sao trang tiếp không chứa 5?

**Đáp án:** Query chỉ lấy `seq>30`; việc bỏ qua late insertion **trước cursor** là hệ quả thiết kế forward-only. Nếu nghiệp vụ không được bỏ sót late data, cần cơ chế khác (CDC/overlap + dedup/versioned feed).

**Bài 7.** Nếu chèn `seq=130` sau khi đã cố định `H=120`, test cần assert gì?

**Đáp án:** Không page keyset nào được trả `seq=130`, vì tất cả đều có `seq<=120`. Nhưng điều đó không làm status của các key `<=120` bất biến.

**Bài 8.** `seq=60` bị `DELETE` và ACK giữa trang đầu và trang sau. Một test live paging có nên bắt buộc nhìn thấy 60 trong result không?

**Đáp án:** **Không.** Nếu delete visible theo CL trước read, row không còn sống. Chỉ snapshot/materialized view mới có cơ sở hứa hiển thị state cũ.

**Bài 9.** Một row `seq=80` bị `UPDATE status='PROCESSED'` sau trang đầu. Vì sao test chỉ so row count là thiếu?

**Đáp án:** Identity và count không đổi nhưng giá trị thay đổi. Cần kiểm tra **column values**, version/as-of semantics nếu contract yêu cầu bất biến, và test mapping/caching.

**Bài 10.** CQL `LIMIT 20` có bảo đảm Cassandra chỉ đọc 20 physical cells khi bảng có tombstones không?

**Đáp án:** **Không.** Cassandra có thể phải xét thêm SSTable/cell versions/tombstones trước khi tìm đủ hàng sống. Kiểm tra p99/tombstones/compaction, không chỉ kết quả.

**Bài 11.** Tại sao cố chèn writer giữa hai trang bằng `Thread.sleep(100)` là test kém?

**Đáp án:** Scheduling/network/GC biến thiên nên writer có thể xảy ra trước/trong/sau khác dự định. Dùng **latch/barrier** và chờ mutation ACK để kiểm soát thứ tự test.

**Bài 12.** `PagingState` safe wrapper có tự chứng minh người dùng A được đọc partition của người dùng B không?

**Đáp án:** **Không.** Nó chỉ kiểm tra query/bind compatibility (không dùng cryptographic MAC). API phải validate signature/expiry/tenant authorization và không để sửa token sang scope khác.

**Bài 13.** Vì sao `Base64url(JSON cursor)` chưa đủ để chống client sửa `deviceId`?

**Đáp án:** Base64 có thể decode/sửa/encode lại. Cần **HMAC hoặc authenticated encryption** với khóa server giữ, cùng validation scope và quyền mỗi request.

**Bài 14.** Nếu HTTP client replay cùng cursor sau một DELETE, server có phải trả nội dung page cũ y hệt không?

**Đáp án:** **Không** nếu contract là live feed. Cursor không phải snapshot/cache response. Nếu cần idempotent response, phải có snapshot/versioned page cache hoặc cơ chế tương đương.

**Bài 15.** Một API lấy dữ liệu hai ngày, chỉ có một paging state. Vì sao chưa đủ?

**Đáp án:** Hai ngày là **hai partitions**, mỗi query có continuation riêng; thứ tự toàn cục cần merge theo event_time + tie-breaker, giữ per-bucket state và giới hạn fan-out.

**Bài 16.** Spring Data `Slice<T>` có phải mô hình OFFSET/COUNT rẻ cho mọi bảng Cassandra không?

**Đáp án:** **Không.** Spring Data Cassandra sử dụng paging state cho điều hướng forward, không nên dùng full-table `findAll()` trên dữ liệu lớn và giả định jump page bất kỳ rẻ.

**Bài 17.** Testcontainers một node với RF=1/`LOCAL_ONE` pass. Nó đã chứng minh `LOCAL_QUORUM` của RF=3 chịu được một node down và cùng view xuyên mọi trang?

**Đáp án:** **Chưa.** Cần cluster ba full replicas và fault-injection riêng; ngay cả LOCAL_QUORUM cũng không tạo snapshot toàn traversal.

**Bài 18.** Một row có TTL 3 giây, test `sleep(3000)` rồi assert row đã biến mất. Cách cải thiện?

**Đáp án:** Dùng **bounded poll** đúng key tới khi SELECT cho thấy row không còn sống, có deadline/interval rõ. Sau đó mới fetch next page; không phụ thuộc sleep đúng bằng TTL đến mili giây.

**Bài 19.** Client timeout khi fetch page, retry cùng query tăng số requests tới Cassandra. Có cần budget?

**Đáp án:** **Có.** Retry gây tải và có thể trả live view khác; đặt bounded retry, backoff+jitter, API deadline và idempotency/dedup ở downstream.

**Bài 20.** Một service đổi clustering key `seq=40` sang `seq=45` bằng INSERT+DELETE trong lúc scan. Vì sao vẫn có thể thấy duplicate/gap dù cursor theo `seq`?

**Đáp án:** Logic event được biểu diễn bằng **hai primary keys** trong quá trình chuyển. Cursor không hiểu chúng là cùng event; cần immutable logical ID và reconciliation/dedup, hoặc versioned snapshot.

**Bài 21.** Một query native paging state được dùng với cùng CQL text nhưng `device_id` khác. Có hợp lệ?

**Đáp án:** **Không.** State gắn cả **bound parameters**. Dùng safe wrapper để fail fast, validate cursor envelope/authorization; không bỏ kiểm tra và gửi raw state mù quáng.

**Bài 22.** Một test live native paging không assert exact baseline sau mutation, vậy nên assert gì để vẫn có giá trị?

**Đáp án:** Kiểm `filter/partition`, upper bound, giới hạn resource, không bỏ network-page leftovers, cursor identity/security, đúng error contract, writer ACK xảy ra đúng lúc, đồng thời ghi observed set để phân tích divergence theo phiên bản.

**Bài 23.** Vì sao cần lưu random seed khi chạy fuzz test concurrent mutations?

**Đáp án:** Để tái hiện thứ tự writer/page schedule và truy vấn khi fail; không có seed/mutation timeline, test flake rất khó chẩn đoán. Vẫn phải tách assertion được guarantee khỏi hiện tượng không có snapshot.

**Bài 24.** Khi một API báo thiếu hàng sau khi chuyển sang async, thứ tự điều tra hợp lý là gì?

**Đáp án:** Trước tiên test dữ liệu **bất biến** và việc gọi `currentPage/hasMorePages/fetchNextPage`, kiểm HTTP cursor/leftovers; sau đó mới kiểm concurrent mutation, TTL, RF/CL, tombstones và network.

## 29. Checklist triển khai và sơ đồ quyết định

~~~text
QUERY / SCHEMA
[ ] Partition key và clustering range có scope bounded, không ALLOW FILTERING mù.
[ ] Clustering key/tie-breaker ổn định cho thứ tự và cursor.
[ ] LIMIT, driver page size, byte/page và HTTP page size được phân biệt.
[ ] Multi-bucket request giới hạn partition, fan-out và global ordering.
[ ] Late insert/rekey/TTL/delete có hợp đồng riêng, không mặc định snapshot.

TEST FIXTURE / ORCHESTRATION
[ ] Test độc lập partition/key, seed dữ liệu và ID có thể tái hiện.
[ ] Dataset tĩnh được test trước: 0/1/N rows, page size 1..N.
[ ] Test sync và async đọc đủ trang; không block callback.
[ ] Đọc hết network page trước khi dùng paging state để resume.
[ ] Writer có ACK và latch/barrier giữa page 1, page 2.
[ ] Test native live behavior không assert snapshot không được cung cấp.
[ ] Test keyset với H có assertion rõ cho insert trước/sau cursor.
[ ] TTL dùng bounded poll thay sleep mù, đo tombstone/compaction.

CURSOR / API / SECURITY
[ ] Cursor gắn query/filter/sort/tenant/page size/version và expiry.
[ ] Safe PagingState không được coi là chữ ký bảo mật.
[ ] Cursor signed/sealed, token validation, tenant authorization mỗi request.
[ ] Không leak raw token, password, payload hay partition IDs trong logs/metrics.
[ ] API định nghĩa replay/timeout/duplicate, HTTP errors và expiry.
[ ] Không skip leftovers khi HTTP page < driver network page.
[ ] Replay không bị tuyên bố là idempotent snapshot nếu chỉ live query.

TOPOLOGY / RESOURCE
[ ] Testcontainers một node chỉ chứng minh client behavior.
[ ] RF3/LOCAL_QUORUM, node down, repair và multi-DC test ở cluster riêng.
[ ] Bounded in-flight, queue, retries và total API deadline.
[ ] Client p99/pages/bytes được đặt cạnh Cassandra tombstones/disk/GC.
[ ] Không tăng page size/pool/timeout để che query/model sai.

CI / ROLLOUT
[ ] Pin Cassandra/Java Driver/Testcontainers version và dependency graph.
[ ] Có test schema/driver cursor migration giữa các bản triển khai.
[ ] Mutation fuzz seed được lưu, flake được phân loại theo contract.
[ ] Staging load/chaos test, canary, stop criteria và rollback.
~~~

~~~mermaid
flowchart TD
    A["Cần kiểm thử phân trang trên Cassandra"] --> B["Chọn contract: tĩnh/live/high-water/snapshot"]
    B --> C["Thiết kế partition key, clustering key, LIMIT và page size"]
    C --> D["Test fixture bất biến: đọc đủ mọi trang"]
    D --> E{"Baseline exact pass?"}
    E -->|Không| F["Sửa client paging / HTTP cursor / CQL"]
    F --> D
    E -->|Có| G["Chặn sau page 1, mutation có ACK"]
    G --> H{"Contract là gì?"}
    H -->|Live native| I["Assert scope, bounds, cursor/ACL, không giả snapshot"]
    H -->|Keyset + H| J["Assert thứ tự, upper bound và continuation"]
    H -->|Snapshot| K["Cần versioned materialization/CDC snapshot"]
    I --> L["RF/CL, TTL/tombstone, retry/fault test"]
    J --> L
    K --> L
    L --> M["Load test, p99/GC/replica, canary và rollback"]
~~~

## 30. Tài liệu tham khảo chính thức và tổng kết

Cần đối chiếu chi tiết API và hành vi với chính phiên bản của dự án:

1. [Apache Cassandra Java Driver 4.18 — Paging](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/): sync/async paging, page size, paging state và giới hạn offset.
2. [Apache Cassandra Java Driver 4.18 — Async programming](https://apache.github.io/cassandra-java-driver/4.18.0/core/async/): `CompletionStage`, `AsyncResultSet`, `fetchNextPage` và callback.
3. [Apache Cassandra Java Driver 4.18.1 — PagingState Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/PagingState.html): safe state, serialization, match query/bind values và lưu ý security.
4. [Apache Cassandra Java Driver 4.18.1 — ExecutionInfo Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html): raw/safe paging state, trace ID, warnings, coordinator.
5. [Spring Data Cassandra — Repositories and paging](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/repositories.html): `CassandraPageRequest`, `Slice` và forward-only continuation.
6. [Spring Data Cassandra — Template querying](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `CassandraTemplate.slice`, CQL và entity mapping.
7. [Testcontainers Java — Cassandra module](https://java.testcontainers.org/modules/databases/cassandra/): container, contact point, local DC, TLS/auth lab và Maven dependency 2.x.
8. [Apache Cassandra — CQL reference](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): điều kiện `WHERE`, `LIMIT`, TTL, mutation semantics và data access theo khóa.

**Tổng kết:** kiểm thử phân trang khi Cassandra đang thay đổi đòi hỏi phân biệt **“đã tới page kế”** và **“đang đọc một ảnh dữ liệu bất biến”**. `PagingState` của Java Driver chỉ định vị tiếp theo trong **cùng statement**, `AsyncResultSet` cần fetch từng page, còn `LOCAL_QUORUM` chỉ điều khiển từng request theo replica — không tính năng nào tự tạo snapshot xuyên thời gian. Hãy **chứng minh baseline tĩnh không thiếu/trùng trước**, chủ động đặt mutation **sau trang 1 bằng latch + ACK**, chọn contract **live** hay **keyset với high-water**, kiểm tra TTL/tombstone, late arrivals và retry, ký cursor/kiểm quyền tại mỗi request, rồi test RF/CL nhiều node ở môi trường phù hợp. **Nếu nghiệp vụ cần tập dữ liệu đúng tại t0**, phải thiết kế snapshot/versioned data riêng; không nâng page size hoặc gọi paging token là “snapshot” để che thiếu sót đó.
