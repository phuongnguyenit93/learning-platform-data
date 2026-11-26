# Bộ nhớ, page cache và khác biệt giữa lần chạy nguội với chạy nóng

## 1. Vì sao một truy vấn Cypher có thể nhanh hơn ở lần chạy thứ hai?

Xét cùng câu truy vấn Neo4j:

~~~cypher
MATCH (a:Article)
WHERE a.category = 'database'
RETURN count(a) AS total;
~~~

Lần đầu, truy vấn có thể phải đọc các trang dữ liệu hoặc index từ tầng lưu trữ vào bộ nhớ. Khi chạy lại, nhiều trang cần thiết đã có trong **Neo4j page cache**, vì thế thời gian chờ truy cập dữ liệu có thể giảm đáng kể. Tuy nhiên, sự khác biệt giữa hai lần chạy **không chỉ do page cache**: Neo4j còn lưu kế hoạch truy vấn, JVM có thể tối ưu mã đã chạy, hệ điều hành có bộ nhớ đệm tệp và client có thể mất thời gian khởi tạo kết nối.

Trong chương **Kế hoạch thực thi** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, ta học cách đọc `EXPLAIN` và `PROFILE` để phân biệt:

- Truy vấn đang **làm bao nhiêu công việc logic** với graph.
- Bao nhiêu lượt truy cập trang **trúng hoặc trượt Neo4j page cache**.
- Các operator sử dụng bao nhiêu bộ nhớ trung gian.
- Vì sao phép đo chạy **nguội** (*cold run*) khác chạy **nóng** (*warm run*).
- Khi nào cần sửa mô hình, index hoặc Cypher thay vì tăng RAM.

Bài này áp dụng cho truy vấn trên property graph (node, relationship và index), đồng thời hữu ích khi đo hiệu năng qua **Neo4j Java Driver** hoặc **Spring Data Neo4j**.

> **Điều kiện:** Ví dụ Cypher dùng cú pháp Neo4j 5 trở lên. Tên cột, khả năng hiển thị và định dạng `PROFILE` có thể thay đổi theo phiên bản, edition và runtime. Số liệu minh họa về độ trễ ở các bảng dưới đây **không phải kết quả benchmark thực tế**.

## 2. Bản đồ bộ nhớ của Neo4j

Các vùng bộ nhớ liên quan nhưng có chức năng khác nhau:

| Vùng | Lưu gì? | Khi thiếu hoặc có vấn đề |
|---|---|---|
| **JVM heap** | Đối tượng Java, trạng thái giao dịch và phần bộ nhớ trung gian của truy vấn; query plan cache cũng tiêu thụ heap | GC tăng, sort/aggregation phức tạp dễ vượt giới hạn bộ nhớ giao dịch |
| **Neo4j page cache** | Các trang từ file lưu trữ graph và một số index trên đĩa | Nhiều *page cache misses*, phải nạp trang lại, tăng độ trễ I/O |
| **Native/off-heap memory** | Các vùng native do Neo4j hoặc thư viện sử dụng, gồm những cấu trúc ngoài heap | Áp lực lên RAM hệ thống dù `heap used` còn thấp |
| **OS memory / filesystem cache** | Bộ nhớ của hệ điều hành, trang tệp và những cấu trúc khác ngoài vùng JVM heap | Có thể gây swap hoặc cạnh tranh bộ nhớ với Neo4j |
| **JVM code cache / JIT** | Mã máy đã biên dịch và metadata runtime | Một số lượt chạy đầu chịu thêm chi phí khởi động/biên dịch |
| **Bộ nhớ ở ứng dụng/Driver** | Kết nối, buffer mạng, DTO, dữ liệu kết quả phía client | Thời gian từ ứng dụng nhìn thấy có thể lớn dù server xử lý nhanh |

**Page cache không phải là JVM heap.** Việc thấy một phép `Sort` dùng nhiều `Memory (Bytes)` không đồng nghĩa phải tăng `server.memory.pagecache.size`. Ngược lại, việc có nhiều page cache misses không tự chứng minh heap bị thiếu.

Đối với chỉ mục đặc biệt như **vector index**, một phần bộ nhớ làm việc nằm ở OS/native, không nhất thiết nằm trong Neo4j page cache. Vì vậy, ước lượng dung lượng chỉ dựa trên graph store và page cache có thể bỏ sót nhu cầu RAM.

Các tham số phổ biến trong Neo4j 5+:

~~~properties
# Ví dụ cấu hình minh họa, KHÔNG phải khuyến nghị cho mọi máy.
server.memory.heap.initial_size=4G
server.memory.heap.max_size=4G
server.memory.pagecache.size=8G
~~~

Trên máy dành riêng cho Neo4j, còn phải chừa RAM cho hệ điều hành, native buffers, các loại index và tác vụ khác. **Không nên cộng heap và page cache bằng đúng toàn bộ RAM vật lý.** Tham khảo `neo4j-admin server memory-recommendation`, quy mô file dữ liệu/index, tải giao dịch và quan sát thực tế trước khi đặt giá trị.

### Page cache giữ những gì?

Neo4j lưu graph và index trong các file. Khi runtime cần đọc record/property hoặc truy cập index tương ứng, nó làm việc với các **trang** dữ liệu:

- **Hit:** trang đã nằm trong Neo4j page cache, có thể phục vụ mà không cần nạp lại trang đó.
- **Miss:** trang chưa có trong Neo4j page cache, hệ thống cần tìm/nạp nó từ tầng lưu trữ thấp hơn.
- **Eviction:** khi bộ nhớ đệm không đủ cho các trang đang cần, những trang cũ có thể bị đẩy ra để nhường chỗ cho trang mới.
- **Warmup:** cơ chế hoặc lưu lượng truy cập đưa các trang thường dùng trở lại page cache.

Một *miss* không nhất thiết tương đương **một lần đọc vật lý từ SSD**: hệ điều hành có thể còn cache của chính nó; ngoài ra cách đọc bất đồng bộ, đọc trước và cách quản lý trang còn tùy phiên bản/cấu hình.

## 3. Đường đi từ Cypher đến page cache

~~~mermaid
flowchart TD
    A["Java Driver / Browser gửi Cypher"] --> B["Parse, lập kế hoạch hoặc tái sử dụng query plan cache"]
    B --> C["Runtime chạy các operator"]
    C --> D["Truy cập record / property / index (DB Hits)"]
    D --> E{"Trang có sẵn trong Neo4j page cache?"}
    E -->|Hit| F["Dùng trang đã có trong RAM"]
    E -->|Miss| G["Nạp trang cần thiết"]
    G --> H["OS filesystem cache hoặc thiết bị lưu trữ"]
    H --> F
    F --> I["Tính toán / kết quả"]
~~~

Sơ đồ minh họa luồng **khái niệm**; `DB Hits` là đơn vị công việc logic trong tầng lưu trữ, **không phải** số trang mà hệ điều hành phải đọc. Một lần database hit có thể tạo ra số hoạt động page cache khác nhau; và không phải mọi công việc của operator đều đụng đến page cache.

Ví dụ khi tìm theo index:

~~~cypher
MATCH (u:User)
WHERE u.email = $email
RETURN u.name;
~~~

Nếu có index trên `:User(email)`, kế hoạch có thể dùng `NodeIndexSeek`; nếu không có, có thể cần một kiểu scan và lọc. Dù dữ liệu đang nóng hay nguội, lựa chọn index/scan vẫn rất quan trọng: **cache giảm chi phí nạp trang, nhưng không xóa khối lượng công việc logic của kế hoạch kém**.

## 4. Chạy nguội và chạy nóng: cần định nghĩa rõ

### 4.1. “Nguội” là gì?

Trong bài toán page cache, **chạy nguội** nghĩa là phần lớn các trang mà truy vấn cần **chưa nằm trong Neo4j page cache** tại thời điểm bắt đầu. Ở lần đọc đầu, số miss có thể cao hơn và độ trễ I/O có thể lớn hơn.

**Chạy nóng** nghĩa là phần lớn các trang cần truy cập **đã được giữ trong page cache**. Các lần thực thi tiếp theo thường có nhiều hit, ít miss và ít chi phí nạp trang.

Các trạng thái này mô tả **độ nóng của tập trang cần cho truy vấn**, không chỉ tuổi thọ của process.

| Khía cạnh | Tình huống chạy nguội | Tình huống chạy nóng |
|---|---|---|
| Trang cần dùng trong Neo4j page cache | Nhiều trang chưa có | Phần lớn đã có |
| Page cache misses | Có thể cao | Thường thấp hơn |
| Page cache hits | Có thể thấp về tỷ lệ | Thường cao về tỷ lệ |
| Độ trễ | Có thể chịu chờ I/O | Có thể giảm chờ I/O |
| `Rows` và đáp án | Phải đúng theo dữ liệu hiện tại | Phải giống lần nguội nếu dữ liệu/logic không đổi |
| `DB Hits` | Thường gần tương đương nếu cùng kế hoạch | Thường gần tương đương nếu cùng kế hoạch |
| Kế hoạch thực thi | Phụ thuộc schema, thống kê và planner | Không nhất thiết thay đổi chỉ vì cache nóng |

Không khẳng định “lần chạy đầu luôn chậm nhất”. Có thể người dùng khác đã nạp đúng các trang đó, hoặc cache vừa được làm nóng tự động. Ngược lại, lần chạy thứ 10 vẫn có thể chậm nếu working set lớn hơn cache hay dữ liệu đang bị tác vụ khác đẩy ra.

### 4.2. Cold page cache khác cold query plan cache

Neo4j có nhiều lớp tối ưu độc lập:

| Cơ chế | Cache gì? | Có tránh thực thi truy vấn không? |
|---|---|---|
| **Neo4j page cache** | Trang dữ liệu và index | Không; chỉ giúp runtime truy cập trang thuận lợi hơn |
| **Query cache / plan cache** | Các giai đoạn parse, logical plan, executable plan | Không; tránh một phần chi phí lập kế hoạch, **vẫn thực thi** truy vấn |
| **OS filesystem cache** | Trang của file phía hệ điều hành | Không; có thể giúp Neo4j nạp lại trang nhanh hơn |
| **JVM JIT/code cache** | Mã đã tối ưu/biên dịch | Không; giảm chi phí xử lý lặp lại trong một số trường hợp |
| **Connection pool** | Kết nối mạng đã sẵn sàng ở client | Không; giảm chi phí khởi tạo kết nối/handshake |

Đổi một ký tự trong Cypher hoặc đổi kiểu tham số có thể ảnh hưởng reuse của query cache; đổi file index hay schema cũng có thể buộc lập kế hoạch lại. Do đó, không lấy thời gian của “lần 1” và “lần 2” để tuyên bố **chính xác bao nhiêu phần trăm** là do page cache nếu không có metrics đi kèm.

### 4.3. Khởi động lại Neo4j chưa chắc tạo “cold run” sạch

Sau khi restart, bộ nhớ process thay đổi nhưng:

- Hệ điều hành có thể còn filesystem cache từ trước.
- Neo4j Enterprise có khả năng **page cache warmup** dựa trên hồ sơ sử dụng, tùy cấu hình.
- Một số job/traffic khác có thể nạp dữ liệu trước khi bạn thử.
- Các dịch vụ Java/Driver có chi phí khởi động và JIT riêng.

Vì vậy, restart trên môi trường thử nghiệm chỉ tạo một **điều kiện gần nguội**, không bảo đảm dữ liệu được đọc hoàn toàn từ ổ đĩa. Việc cố ý xóa cache của OS hoặc liên tục restart database không nên thực hiện trên hệ thống sản xuất.

## 5. Đọc EXPLAIN và PROFILE để biết đang tốn gì

### EXPLAIN

~~~cypher
EXPLAIN
MATCH (p:Person)
WHERE p.age >= 30
RETURN p.name
ORDER BY p.name;
~~~

`EXPLAIN` tạo **kế hoạch dự kiến** mà không chạy truy vấn. Nó hữu ích để xem operator nào được chọn, ước lượng số dòng và index có khả năng được dùng, nhưng không cung cấp các số đo runtime thực như page cache hits/misses.

### PROFILE

~~~cypher
PROFILE
MATCH (p:Person)
WHERE p.age >= 30
RETURN p.name
ORDER BY p.name;
~~~

`PROFILE` **thực sự chạy** truy vấn và bổ sung số liệu. Nếu gắn trước câu lệnh ghi, lệnh ghi cũng chạy; trong bài học và benchmark, chỉ dùng với các truy vấn **chỉ đọc**.

Các trường quan trọng trong plan (nếu khả dụng):

| Trường | Ý nghĩa | Cách diễn giải |
|---|---|---|
| `Estimated Rows` | Số dòng planner ước lượng trước khi chạy | Sai khác lớn với `Rows` có thể làm planner chọn kế hoạch chưa phù hợp |
| `Rows` | Số dòng thực từng operator xuất ra | Giúp phát hiện phình số dòng do quan hệ một-nhiều |
| `DB Hits` | Số hoạt động truy cập tầng lưu trữ logic | Không đồng nghĩa đĩa đọc bấy nhiêu lần; thấp hơn thường là ít công việc hơn |
| `Page Cache Hits/Misses` | Lượt truy cập trang trúng/trượt cache | Cho thấy mức độ nóng tại lượt chạy; thường chỉ hiển thị trong **Enterprise Edition** |
| `Memory (Bytes)` | **Đỉnh heap** của từng operator được đo | Không phải dung lượng Neo4j page cache; không cộng số đỉnh các operator để suy tổng |
| `Time (ms)` | Thời gian ghi nhận cho operator/pipeline | Một số operator kết hợp (fused) chia sẻ số đo thời gian |
| `Indexes Used` | Các index đã sử dụng nếu runtime cung cấp | Phân biệt kế hoạch seek/scan; không kết luận chỉ từ tên operator |
| Footer `total allocated memory` | Đỉnh bộ nhớ truy vấn do runtime ghi nhận | Không bằng tổng các `Memory (Bytes)` của mọi operator |

**Lưu ý khả năng quan sát:** `Page Cache Hits/Misses` trong plan PROFILE được tài liệu Neo4j mô tả cho **Enterprise Edition**; có những operator hoặc pipeline không hiện số liệu. Dòng trống/không có cột này **không có nghĩa** Neo4j không sử dụng page cache. Có thể xem các metrics cấp DBMS/database qua hệ thống monitoring nếu plan không cung cấp đủ chi tiết.

Ngoài ra, khi runtime gộp nhiều operator thành một pipeline, `Time (ms)` có thể đại diện **cả pipeline**. Không kết luận chỉ một operator là nút thắt khi nhiều operator chia sẻ số đo đó.

### Công thức hit ratio

Nếu có đủ `hits` và `misses` cho cùng phạm vi đo:

\[
\text{Page cache hit ratio}
=\frac{\text{hits}}{\text{hits}+\text{misses}} \times 100\%
\]

Ví dụ tưởng tượng: `995 hits` và `5 misses` tương ứng **99,5%**. Nếu cả hai đều bằng 0, tỷ số không xác định; không tự quy ra “cache tối ưu 100%”.

## 6. Bảng minh họa: cùng DB Hits, khác page cache

Các con số sau **chỉ minh họa cách đọc**, không phải kết quả chạy Neo4j đã đo:

| Chỉ số | Lần gần nguội | Lần đã nóng |
|---|---:|---:|
| Rows ở operator cần xét | 1.000 | 1.000 |
| DB Hits | 4.000 | 4.000 |
| Page Cache Hits | 100 | 995 |
| Page Cache Misses | 900 | 5 |
| Tỷ lệ hit | 10,0% | 99,5% |
| Thời gian từ client (giả định) | 95 ms | 18 ms |

Trong ví dụ, workload logic gần như không đổi (`Rows` và `DB Hits` giống nhau), nhưng trạng thái trang thay đổi. Cách diễn giải phù hợp là **page cache có thể đóng góp đáng kể vào chênh lệch độ trễ**. Không thể suy riêng từ bảng rằng “77 ms chính xác là thời gian disk I/O” vì còn OS cache, network, lập kế hoạch, scheduling và nhiều yếu tố khác.

Nếu lần nóng vẫn có `DB Hits` rất cao, nên xem kế hoạch truy vấn: một lần scan hoặc expand thừa vẫn tốn CPU và tài nguyên, dù không phải đọc lại trang từ đĩa.

## 7. Thực hành có đáp án: dựng dataset riêng

Dùng database thực hành tách biệt; không chạy cleanup trong database chứa dữ liệu thực. Label `QA008PerfDoc` và tên index `qa008_perf_segment` được đặt riêng cho bài này.

### Bước 1 — Xóa fixture cũ nếu có

~~~cypher
DROP INDEX qa008_perf_segment IF EXISTS;
~~~

~~~cypher
MATCH (d:QA008PerfDoc)
DETACH DELETE d;
~~~

### Bước 2 — Tạo 10.000 node có dữ liệu xác định

~~~cypher
UNWIND range(1, 10000) AS i
CREATE (:QA008PerfDoc {
  testId: i,
  segment: i % 100,
  score: i % 10,
  title: 'Tai lieu thu nghiem ' + toString(i)
});
~~~

Đây là dữ liệu nhỏ **để học đọc execution plan**, chưa đủ để tạo chênh lệch cold/warm đáng tin trên mọi cấu hình. Ngay cả việc `CREATE` cũng có thể làm nóng nhiều trang, nên lần `PROFILE` đầu sau bước này **không phải cold run chuẩn**.

Kiểm tra đáp án:

~~~cypher
MATCH (d:QA008PerfDoc)
RETURN
  count(d) AS soNode,
  sum(d.score) AS tongDiem,
  count(DISTINCT d.segment) AS soSegment;
~~~

| soNode | tongDiem | soSegment |
|---:|---:|---:|
| 10.000 | 45.000 | 100 |

Giải thích: `score` nhận các giá trị 0–9, mỗi giá trị xuất hiện đúng 1.000 lần; tổng là `(0+1+...+9) × 1.000 = 45.000`. `segment` nhận các giá trị 0–99, mỗi nhóm có 100 node.

### Bước 3 — Đọc plan của phép scan

~~~cypher
EXPLAIN
MATCH (d:QA008PerfDoc)
RETURN
  count(d.score) AS soNode,
  sum(d.score) AS tongDiem;
~~~

Rồi chạy:

~~~cypher
PROFILE
MATCH (d:QA008PerfDoc)
RETURN
  count(d.score) AS soNode,
  sum(d.score) AS tongDiem;
~~~

Đáp án không đổi: `soNode = 10000`, `tongDiem = 45000`.

Tùy runtime, có thể thấy operator quét label, đọc property và operator tổng hợp. Những cái tên như `NodeByLabelScan` và `EagerAggregation` chỉ là **ví dụ**; phiên bản, định dạng dữ liệu và tối ưu hóa của planner có thể tạo plan khác.

**Làm ba lượt với chính xác câu `PROFILE` trên**, chụp/ghi lại `Rows`, `DB Hits`, `Page Cache Hits/Misses` và thông số thời gian. Sau đó phân tích:

- Nếu `DB Hits` gần ổn định nhưng `misses` giảm, đó là dấu hiệu các trang đang được giữ lại tốt hơn.
- Nếu `misses` vẫn cao, working set có thể vượt cache hoặc các tác vụ khác đang tranh chấp cache.
- Nếu `misses` gần bằng 0 từ lần đầu, fixture có thể đã nóng sẵn hoặc toàn bộ dữ liệu vừa được tạo và còn trong RAM.
- Nếu không có số page cache theo operator, không giả lập số liệu; sử dụng dashboard metrics cấp hệ thống hoặc báo rằng edition/runtime chưa cung cấp.

### Bước 4 — Thêm index để quan sát khác biệt về công việc logic

Tạo index độc lập theo property `segment`:

~~~cypher
CREATE RANGE INDEX qa008_perf_segment IF NOT EXISTS
FOR (d:QA008PerfDoc) ON (d.segment);
~~~

Kiểm tra index có sẵn sàng:

~~~cypher
SHOW INDEXES
YIELD name, type, state, labelsOrTypes, properties
WHERE name = 'qa008_perf_segment'
RETURN name, type, state, labelsOrTypes, properties;
~~~

Chỉ kiểm thử seek sau khi index đã `ONLINE`.

~~~cypher
PROFILE
MATCH (d:QA008PerfDoc)
WHERE d.segment = 42
RETURN
  count(d) AS soNode,
  sum(d.score) AS tongDiem;
~~~

Đáp án: `soNode = 100`, `tongDiem = 200`. Trong mỗi nhóm `segment = 42`, `score = 2`, vì `42 mod 10 = 2`.

Bộ lập kế hoạch **có thể** chọn `NodeIndexSeek` nhờ range index; tuy nhiên, với tập dữ liệu nhỏ, planner đôi khi chọn một phương án khác. Đánh giá plan thực nhận, không ép kết quả phải mang một tên operator cố định.

**Mục đích so sánh:** index có thể giúp giảm `DB Hits` bằng cách thu hẹp số node cần đọc; page cache giúp các trang mà plan cần đọc có sẵn hơn. Đây là **hai trục tối ưu khác nhau**. Không dùng thời gian của truy vấn quét toàn bộ ở bước 3 để so trực tiếp với truy vấn có `WHERE d.segment = 42` vì hai bài toán và số bản ghi xử lý khác nhau.

### Bước 5 — Quan sát bộ nhớ trung gian của aggregation

~~~cypher
PROFILE
MATCH (d:QA008PerfDoc)
WITH d.segment AS segment, collect(d.testId) AS ids
RETURN segment, size(ids) AS members
ORDER BY members DESC, segment
LIMIT 5;
~~~

Dữ liệu tạo ra 100 nhóm, mỗi nhóm 100 phần tử; vì `members` bằng nhau, kết quả là các nhóm `segment = 0, 1, 2, 3, 4`, mỗi nhóm `members = 100`.

Các tập `ids` được dựng trong bộ nhớ truy vấn. Hãy tìm operator tổng hợp/sắp xếp và cột `Memory (Bytes)` nếu runtime hỗ trợ, rồi phân biệt chi phí **giữ dữ liệu trung gian** với chi phí **nạp trang dữ liệu từ page cache**. Có thể tối ưu khi chỉ cần đếm bằng cách thay `collect(d.testId)` và `size(ids)` bằng `count(d)`; không cần materialize từng danh sách `ids`.

## 8. Làm benchmark cold/warm có khả năng lặp lại

Để đưa ra kết luận phục vụ tối ưu sản phẩm, cần một quy trình đo rõ ràng.

### 8.1. Cố định các yếu tố làm sai lệch

1. **Cùng dữ liệu và schema:** không tạo index mới, cập nhật thống kê, import hoặc ghi node/relationship giữa các lượt đo. Index phải `ONLINE`.
2. **Cùng truy vấn và kiểu tham số:** dùng truy vấn tham số hóa với giá trị/kiểu giống nhau để tránh ảnh hưởng từ cache kế hoạch và thay đổi tính chọn lọc.
3. **Cùng môi trường:** phiên bản Neo4j, Cypher runtime, heap, page cache, CPU, RAM, storage, container limit, số kết nối và concurrency nên giữ ổn định.
4. **Cùng cách lấy kết quả:** luôn tiêu thụ hết result stream; không so lần chỉ mở cursor với lần đợi lấy toàn bộ kết quả.
5. **Đo cả server lẫn client:** ghi `PROFILE`/metrics để hiểu nguyên nhân, nhưng đo truy vấn thường (không `PROFILE`) khi báo cáo latency ứng dụng vì `PROFILE` có chi phí theo dõi riêng.
6. **Lưu kế hoạch thực tế:** nếu operator hoặc index sử dụng thay đổi, đó là một phép thử khác; phải phân tích riêng thay vì đổ toàn bộ chênh lệch cho page cache.

### 8.2. Nhóm “gần nguội”

Trên **instance thử nghiệm riêng**, chọn điều kiện nạp dữ liệu từ đầu đã kiểm soát. Nếu dùng restart, ghi rõ rằng filesystem cache của OS và chức năng page cache warmup có thể khiến dữ liệu vẫn nóng một phần. Các bản Neo4j mới có cấu hình `db.memory.pagecache.warmup.enable` ở Enterprise Edition; trạng thái restart có thể được làm nóng tự động theo hồ sơ sử dụng.

Chạy truy vấn đọc **một lần**, lưu độ trễ và cache metrics gần thời điểm thực thi. Để lấy nhiều mẫu near-cold cần khôi phục điều kiện ban đầu cho **từng mẫu**; không gọi các lần liên tiếp trong cùng process là nhiều mẫu độc lập “cold”.

Không thử làm nguội cache bằng các thao tác gây gián đoạn trên production. Nếu không thể cô lập môi trường và xác nhận cache đã nguội, hãy gọi kết quả là **“first observed run”** hoặc **“after restart”**, không khẳng định “cold disk”.

### 8.3. Nhóm chạy nóng

Trong cùng môi trường test:

1. Chạy cùng truy vấn vài lần để làm nóng những trang thường dùng, connection pool và JIT.
2. Bỏ các lượt warmup khỏi tập số liệu đo steady-state.
3. Chạy ít nhất vài chục lượt (tùy mục tiêu), ghi latency từng lượt và thống kê **median**, **p95**, số trang hit/miss, DB Hits, GC và I/O.
4. Thử thêm **tải đồng thời** theo thực tế nếu mục tiêu là vận hành ứng dụng; latency khi một người dùng truy vấn tuần tự thường khác với khi nhiều giao dịch cùng truy cập graph.

Dùng median thay vì chỉ báo “lần nhanh nhất”; p95 giúp phát hiện những lượt bất thường do I/O, GC hoặc cạnh tranh tài nguyên. Không gộp số liệu cold với warm thành một số trung bình duy nhất vì hai nhóm trả lời hai câu hỏi khác nhau.

### 8.4. Mẫu bảng ghi kết quả

| run | Điều kiện | Latency client (ms) | DB Hits | PC Hits | PC Misses | Kế hoạch/index |
|---|---|---:|---:|---:|---:|---|
| 1 | after restart | *(đo)* | *(đo)* | *(nếu có)* | *(nếu có)* | *(ghi)* |
| 2 | warmup | *(đo)* | *(đo)* | *(nếu có)* | *(nếu có)* | *(ghi)* |
| 3..N | steady-state | *(đo)* | *(đo)* | *(nếu có)* | *(nếu có)* | *(ghi)* |

Các ô “*(đo)*” là yêu cầu thu thập, **không phải kết quả giả định**. Nếu metrics theo query không có, có thể dùng metric cấp database/DBMS với cửa sổ thời gian và tải được cô lập, nhưng không gán toàn bộ số liệu hệ thống cho một query trong môi trường nhiều người dùng.

## 9. Đo latency qua Neo4j Java Driver

Trong ứng dụng Java, thời gian từ lúc gửi truy vấn đến khi **tiêu thụ hết kết quả** thường quan trọng hơn thời gian một operator đơn lẻ. Ví dụ tối giản dưới đây giả định `driver` đã được khởi tạo và kết nối sẵn, phiên làm việc dùng database `neo4j`:

~~~java
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

void benchmarkRead(Driver driver) {
    String cypher = """
        MATCH (d:QA008PerfDoc)
        WHERE d.segment = $segment
        RETURN count(d) AS soNode, sum(d.score) AS tongDiem
        """;

    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        // Không tính thời gian tạo driver vào latency truy vấn.
        long start = System.nanoTime();

        // consume() buộc driver nhận hết stream kết quả.
        session.run(cypher, Values.parameters("segment", 42))
               .consume();

        long millis = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - start
        );
        System.out.println("Elapsed ms = " + millis);
    }
}
~~~

Để so sánh chuẩn hơn, gọi truy vấn nhiều lần, bỏ warmup và ghi latency cho từng lượt thay vì in duy nhất một số. Cấu hình database, phiên bản Java Driver, connection pool, network và concurrency cũng cần giữ ổn định.

Trong Spring Data Neo4j, có thể đo ở service/repository tương tự, nhưng thời gian ứng dụng có thể bao gồm thêm mapping entity, transaction interceptor và xử lý phía Spring. Nếu mục tiêu là phân tích page cache, so sánh latency ứng dụng với số liệu server để tìm tầng gây chênh lệch.

## 10. Các chỉ số vận hành nên xem cùng execution plan

`PROFILE` giúp hiểu một câu truy vấn. Khi làm production observability, cần nhìn thêm các chỉ số nhiều truy vấn cùng lúc:

| Chỉ số | Câu hỏi nên hỏi |
|---|---|
| Page cache **hit ratio** | Trong khoảng thời gian đo, tỷ lệ yêu cầu trang được phục vụ từ cache là bao nhiêu? |
| Page cache **usage ratio** | Bao nhiêu phần dung lượng đã được sử dụng? |
| Page cache **hits / misses / page faults** | Tốc độ trúng và phải nạp trang biến đổi ra sao sau deploy hoặc tăng tải? |
| Page cache **bytes read** | Có đợt đọc dữ liệu lớn từ tầng lưu trữ hay không? |
| Heap used / GC pause | Truy vấn chậm do cấp phát/thu gom bộ nhớ thay vì do nạp trang? |
| Query duration, p95/p99 | Người dùng có đang bị chậm, kể cả khi cache hit cao? |
| I/O latency, IOPS, CPU | Giới hạn thực ở thiết bị lưu trữ hay sức tính toán? |
| Transaction memory / query memory | Truy vấn có `Sort`, `EagerAggregation`, `Expand` lớn hoặc bị chặn vì giới hạn bộ nhớ? |

Trong tài liệu vận hành Neo4j, hit ratio **duy trì trên khoảng 98%** thường là một mục tiêu tham khảo cho workload ổn định; đây **không phải quy tắc cứng** cho mọi truy vấn. Một workload quét dữ liệu mới liên tục có thể có cache misses nhiều nhưng vẫn hoạt động đúng; còn hit ratio cao chưa bảo đảm độ trễ thấp nếu CPU bị bão hòa hoặc Cypher tạo quá nhiều dòng trung gian.

`usage ratio = 100%` cùng hit ratio giảm và I/O tăng có thể gợi ý working set không vừa page cache. Nhưng **usage ratio cao một mình** là bình thường với một cache đang tận dụng RAM; cần kết hợp nhiều chỉ số trước khi quyết định tăng dung lượng.

### Kiểm tra cấu hình bằng Cypher

Tùy quyền hạn và bản Neo4j, có thể dùng:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name IN [
  'server.memory.heap.initial_size',
  'server.memory.heap.max_size',
  'server.memory.pagecache.size'
]
RETURN name, value
ORDER BY name;
~~~

Nếu tài khoản không có quyền xem settings hoặc hệ thống do nền tảng managed quản lý, xem cấu hình/monitoring mà nền tảng cho phép. Cần đặc biệt chú ý **giới hạn RAM của container hoặc máy ảo**, chứ không chỉ tổng RAM vật lý của host.

Tài liệu Neo4j cũng có lệnh tham khảo ước lượng bộ nhớ từ máy chủ:

~~~text
neo4j-admin server memory-recommendation
~~~

Đây là **lệnh hệ điều hành**, không phải Cypher. Sử dụng nó để lấy điểm xuất phát và xem kích thước store/index; kết quả cuối cùng vẫn phải dựa trên workload thật.

## 11. Tình huống chẩn đoán và hướng xử lý

| Quan sát | Diễn giải có thể đúng | Bước xác minh/điều chỉnh |
|---|---|---|
| Lần đầu chậm, nhiều page cache misses; sau vài lần nhanh hơn | Nhiều trang được làm nóng | Giữ nguyên query/index, so DB Hits và hits/misses qua các lượt |
| Lần đầu chậm nhưng gần như không có page cache misses | Chưa chắc do page cache | Kiểm tra plan cache, JIT, tạo kết nối, GC và thao tác client |
| Cả nguội và nóng đều chậm, DB Hits rất cao | Kế hoạch có thể làm nhiều việc thừa | Xem scan/expand, điều kiện lọc, cardinality; cân nhắc index/viết lại Cypher |
| Cache hit ratio cao mà `Sort` tốn nhiều memory | Tắc ở bộ nhớ trung gian/CPU | Giảm dữ liệu cần sort, tối ưu lọc, tìm index phù hợp, tránh `collect()` không cần |
| Page cache usage gần 100%, misses và I/O cùng tăng liên tục | Working set có thể vượt cache | Xem dung lượng dữ liệu/index, tải đồng thời, RAM khả dụng; đo trước khi tăng cache |
| Lúc có index mới truy vấn bỗng đổi thời gian | Planner replan, index đang tạo, cache trạng thái mới | Chờ index `ONLINE`, lưu lại kế hoạch và so ở cùng điều kiện |
| `PROFILE` có DB Hits nhưng thiếu Page Cache Hits/Misses | Edition/runtime không xuất stats đó | Xem metrics cấp DBMS; không kết luận page cache không tồn tại |
| Chạy query bằng Java chậm hơn Neo4j Browser | Khác kết nối, serializing, result consumption, network | Đo các pha client/server và tiêu thụ kết quả giống nhau |
| P95 tăng khi load cao dù single-run nhanh | Cạnh tranh CPU/I/O, GC, tx memory, page cache eviction | Benchmark ở concurrency thật và theo dõi chỉ số hệ thống |

**Tình huống đặc biệt:** một truy vấn `MATCH (n) RETURN count(n)` có thể dùng count store hoặc cơ chế tối ưu tương tự, rất khác việc đọc thuộc tính của mọi node. Nếu bạn muốn thử tải truy cập store, hãy chọn truy vấn thực sự phải đọc thuộc tính/quan hệ, chẳng hạn phép `sum(d.score)` ở fixture mục 7. Không lấy truy vấn count đơn giản làm đại diện cho mọi workload graph traversal.

## 12. Những sai lầm trong suy luận hiệu năng

**Sai lầm 1 — “DB Hits càng cao nghĩa là càng nhiều disk reads.”**

`DB Hits` là phép đếm **công việc truy cập logic** của runtime với tầng lưu trữ. Cùng một lượng DB Hits có thể được phục vụ bởi các trang nóng, dẫn tới số disk reads thực thấp hơn nhiều.

**Sai lầm 2 — “Muốn query nhanh thì cứ tăng heap.”**

Nếu truy vấn chủ yếu chậm do page cache misses, tăng heap có thể không giải quyết vấn đề và còn lấy mất RAM dành cho page cache/OS. Ngược lại, nếu truy vấn bị GC hoặc tốn memory cho aggregation thì chỉ tăng page cache có thể vô ích.

**Sai lầm 3 — “Restart là benchmark cold chuẩn.”**

Hệ điều hành có filesystem cache, Neo4j có page cache warmup, và traffic khác có thể đã truy cập trang. Chỉ gọi là cold khi trạng thái cache thực sự được kiểm soát và được mô tả.

**Sai lầm 4 — “PROFILE cho biết chính xác latency mà API sẽ trải nghiệm.”**

`PROFILE` thêm overhead quan sát và có thể được đo trên cùng server, trong khi API còn có network, serialization, entity mapping và thời gian tiêu thụ kết quả. Dùng cả profiling và latency thực khi đánh giá sản phẩm.

**Sai lầm 5 — “Lần chạy nóng nhanh nghĩa là Cypher đã tối ưu.”**

Page cache che một phần chi phí I/O của kế hoạch kém. Trên dữ liệu lớn hơn, working set thay đổi hoặc khi cold start, lỗi scan/expand không cần thiết sẽ bộc lộ trở lại.

**Sai lầm 6 — “Cộng cột Memory (Bytes) của mọi operator là heap cần thiết.”**

Số này là **đỉnh bộ nhớ từng operator**, có thể xảy ra ở các thời điểm khác nhau; tổng cộng không phản ánh đỉnh đồng thời. Xem footer truy vấn và metrics transaction/heap để đánh giá sức chứa thực.

## 13. Bài tập có đáp án

### Bài 1 — Tính tỷ lệ trúng cache

Một lần chạy có `Page Cache Hits = 1.800` và `Misses = 200`. Hit ratio là bao nhiêu?

**Đáp án:** `1.800 / (1.800 + 200) × 100% = 90%`. Đây chỉ mô tả phạm vi và khoảng thời gian của phép đo.

### Bài 2 — Phân biệt tối ưu logic với tối ưu I/O

Hai lần chạy cùng Cypher và cùng dữ liệu có `DB Hits = 12.000` nhưng misses lần 1 bằng `850`, lần 2 bằng `12`. Điều gì có thể giải thích?

**Đáp án:** công việc logic gần như giống nhau; các trang được nạp vào page cache ở lần trước nên lần sau phải nạp ít hơn. Kiểm tra `Rows`/plan và các yếu tố khác trước khi gán toàn bộ chênh lệch thời gian cho disk.

### Bài 3 — Kiểm tra fixture

Với 10.000 node ở mục 7, truy vấn:

~~~cypher
MATCH (d:QA008PerfDoc)
WHERE d.segment = 42
RETURN count(d) AS n, sum(d.score) AS s;
~~~

Kết quả đúng là gì?

**Đáp án:** `n = 100` và `s = 200`. Kết quả phải đúng dù scan hay index seek và dù cache nóng hay nguội.

### Bài 4 — Phân tích thiếu bộ nhớ

Một query `collect()` hàng triệu phần tử khiến bộ nhớ truy vấn tăng và GC hoạt động nhiều, nhưng hit ratio gần 100%. Ưu tiên tăng page cache hay xem lại query?

**Đáp án:** ưu tiên giảm lượng dữ liệu trung gian (`collect`, `Sort`, `Expand`, `EagerAggregation`), kiểm tra giới hạn transaction memory và heap. Hit ratio cao cho thấy cần tìm nguyên nhân ngoài page cache.

### Bài 5 — Thiết kế phép thử công bằng

Nhóm A chạy cùng query ngay sau tạo index; nhóm B chạy sau 20 lượt warmup. Có thể kết luận chênh lệch hoàn toàn do page cache không?

**Đáp án:** không. Tạo index có thể thay đổi execution plan và làm mất hiệu lực query plan cache; thời gian đầu có thể chịu thêm planning/JIT. Cần cố định schema, chờ index `ONLINE`, lưu plan, kiểm soát trạng thái page cache và tách nhóm dữ liệu.

## 14. Dọn bộ dữ liệu thực hành

Trong đúng database thực hành đã dùng ở mục 7:

~~~cypher
DROP INDEX qa008_perf_segment IF EXISTS;
~~~

~~~cypher
MATCH (d:QA008PerfDoc)
DETACH DELETE d;
~~~

Kiểm tra:

~~~cypher
MATCH (d:QA008PerfDoc)
RETURN count(d) AS remaining;
~~~

Kết quả mong đợi: `remaining = 0`.

## 15. Tài liệu chính thức và ghi nhớ

- [Neo4j Cypher Manual — Understanding query plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): ý nghĩa `EXPLAIN`, `PROFILE`, `DB Hits`, `Memory (Bytes)` và các số đo page cache.
- [Neo4j Cypher Manual — Query caches](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/caching/): các tầng cache kế hoạch, kiểu tham số, tác động của thay đổi schema.
- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/): phân chia heap, native/OS memory và page cache; dự toán cấu hình.
- [Neo4j Operations Manual — Disks, RAM and other tips](https://neo4j.com/docs/operations-manual/current/performance/disks-ram-and-other-tips/): làm nóng page cache và tác động I/O.
- [Neo4j Operations Manual — Metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/): các chỉ số page cache, JVM và transaction.
- [Neo4j Operations Manual — Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/): tên setting cụ thể, khả năng hỗ trợ theo phiên bản.

Khi tối ưu Neo4j, hãy đọc đồng thời **kế hoạch thực thi** và **trạng thái bộ nhớ tại thời điểm chạy**. Một kế hoạch tạo ít công việc logic giúp ổn định hiệu năng; page cache đủ cho working set giúp giảm chi phí nạp dữ liệu. Phép đo có kiểm soát, đáp án nhất quán và phân biệt cold/warm mới cho phép xác định thay đổi nào thực sự cải thiện trải nghiệm của ứng dụng.
