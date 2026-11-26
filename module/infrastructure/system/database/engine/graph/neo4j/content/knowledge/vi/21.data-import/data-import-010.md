# Đo tốc độ nhập và xác định nút thắt ở nguồn, mạng hoặc máy chủ

## 1. Tại sao phải đo theo từng chặng nhập dữ liệu?

Nhập dữ liệu vào Neo4j có thể bắt đầu từ CSV, API, message broker, cơ sở dữ liệu quan hệ hoặc một chương trình Java. Đích cuối là các **node**, **relationship** và **property** trong property graph. Một pipeline nhập chậm có thể do:

- Nguồn sinh hoặc đọc bản ghi chậm, dữ liệu phải giải nén hay chuyển đổi phức tạp.
- Đường mạng chuyển dữ liệu giữa ứng dụng, nguồn tệp và Neo4j bị giới hạn bởi độ trễ, băng thông hoặc lỗi kết nối.
- Máy chủ Neo4j cần nhiều CPU, heap, page cache, I/O đĩa, transaction log hoặc phải xử lý khóa, ràng buộc và index.

Trong mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, chủ đề **Nhập dữ liệu** này hướng dẫn cách đo **tốc độ nhập và xác định nút thắt ở nguồn, mạng hoặc máy chủ**, áp dụng cho `LOAD CSV`, Cypher `UNWIND` qua Neo4j Java Driver và các trường hợp nhập dữ liệu số lượng lớn.

Ví dụ thực hành sử dụng database thử nghiệm riêng, tên label có tiền tố `QA010` và dữ liệu nhỏ có đáp án. Đây là bài đo hiệu năng có kiểm soát: số liệu thời gian chỉ xuất hiện khi bạn tự chạy; các con số mang nhãn **giả định** dùng để luyện cách diễn giải, không được xem như kết quả benchmark Neo4j thực tế.

Sau bài học, bạn sẽ biết cách:

1. Định nghĩa đúng throughput, latency, tỷ lệ lỗi và số bản ghi đã commit.
2. Đo riêng từng chặng nguồn, mạng, xử lý Cypher và commit.
3. Tổ chức thí nghiệm để phân biệt các nguyên nhân gây chậm.
4. Chọn batch size, concurrency và cách nhập phù hợp dựa trên bằng chứng.
5. Kiểm tra số lượng dữ liệu và tính idempotent, tránh “nhập nhanh nhưng nhập sai”.

## 2. Sơ đồ các đường nhập: nguồn và mạng nằm ở đâu?

Đường nhập dữ liệu không giống nhau giữa `LOAD CSV` và Java Driver.

### 2.1. Ứng dụng Java gửi bản ghi qua Bolt

~~~mermaid
flowchart LR
    A["CSV/API/Database nguồn"] --> B["Ứng dụng Java: đọc, parse, chuẩn hóa"]
    B --> C["Serialize và batch"]
    C --> D["Mạng ứng dụng ↔ Neo4j (Bolt/TLS)"]
    D --> E["Neo4j: Cypher, index/constraint, khóa"]
    E --> F["Page cache, transaction log, ổ đĩa"]
~~~

Ở cách này, **ứng dụng** đọc nguồn và truyền một batch bản ghi thành tham số Cypher, thường dùng `UNWIND $rows`. Chậm ở nguồn làm ứng dụng không có bản ghi để gửi; chậm ở Bolt có thể khiến thời gian truyền/nhận dài; chậm ở Neo4j khiến nhiều request tồn đọng dù dữ liệu đã sẵn sàng.

### 2.2. Neo4j chạy LOAD CSV

~~~mermaid
flowchart LR
    A["CSV local trong import directory hoặc HTTP(S)"] --> B["Neo4j server: LOAD CSV"]
    B --> C["Parse và chuyển kiểu dữ liệu"]
    C --> D["Cypher: CREATE/MERGE"]
    D --> E["Index/constraint, transaction log, page cache/đĩa"]
    F["Browser/Java client"] -. "Gửi câu lệnh và nhận kết quả" .-> B
~~~

Với `LOAD CSV`, **Neo4j server đọc tệp CSV**. Khi URL là `file:///...`, đường dẫn được giải quyết ở **máy chủ Neo4j**, thường dưới thư mục import được cấu hình; đó không phải đường dẫn máy tính người dùng. Khi URL là HTTP(S), chính **Neo4j server tải CSV qua mạng**. Client chỉ gửi câu lệnh và nhận kết quả, nên băng thông Bolt giữa client và Neo4j thường không phải chặng truyền toàn bộ dữ liệu CSV.

> **Câu hỏi đầu tiên khi gặp nhập chậm:** dữ liệu thực sự đang chạy qua đường mạng nào? Kết luận “mạng Java ↔ Neo4j chậm” sẽ sai nếu dữ liệu chủ yếu đi theo đường “HTTP CSV → Neo4j server”.

## 3. Chọn đúng đơn vị tốc độ và mốc bắt đầu/kết thúc

Đo đủ **khối lượng công việc**, **thời gian** và **tính đúng đắn**:

| Chỉ số | Định nghĩa | Lưu ý |
|---|---|---|
| Input rows/s | Số dòng nguồn đọc/giải mã mỗi giây | Có thể gồm dòng trùng hoặc bị loại |
| Committed rows/s | Số dòng nguồn được xử lý thành công và commit mỗi giây | Không luôn bằng số node tạo mới |
| Created nodes/s | Số node mới thực tạo mỗi giây | Có thể bằng 0 khi chạy lại `MERGE` |
| Created relationships/s | Số relationship mới tạo mỗi giây | Cần đo riêng khi nhập cạnh |
| MiB/s | Số byte dữ liệu thực được chuyển/đọc mỗi giây | Khác với rows/s vì kích thước record không đều |
| Batch latency | Thời gian xử lý và commit của một batch | Nên đo median, p95, không chỉ trung bình |
| Error/reject rate | Tỷ lệ dòng hoặc batch lỗi | Không tính bản ghi lỗi thành dữ liệu nhập thành công |
| Backlog / queue depth | Bản ghi đang chờ giữa các chặng | Queue liên tục tăng giúp xác định chặng tiêu thụ chậm hơn |

Các công thức cơ bản:

\[
\text{rows/s}=\frac{\text{số dòng đã xử lý thành công}}{\text{số giây đo}}
\]

\[
\text{MiB/s}=\frac{\text{byte đã truyền hoặc đọc}}{1024^2\times \text{số giây đo}}
\]

\[
\text{Tỷ lệ lỗi}=\frac{\text{số dòng bị loại hoặc thất bại}}{\text{số dòng nguồn}}\times100\%
\]

**Ví dụ giả định:** một đợt có 120.000 dòng nguồn, 118.800 dòng được xử lý thành công trong 60 giây. Throughput là **1.980 committed rows/s**, tỷ lệ dòng thất bại là **1%**. Nếu mỗi 100 dòng tạo 30 node và cập nhật 70 node cũ, **created nodes/s** khác hẳn **rows/s**; không dùng hai chỉ số thay cho nhau.

### 3.1. Phân biệt “xong gửi” với “xong commit”

Một request gửi đủ bytes chưa đồng nghĩa các transaction đã commit. Với ứng dụng Java, chỉ kết thúc phép đo batch sau khi nhận xác nhận giao dịch thành công, ví dụ sau khi `session.executeWrite(...)` trả về. Với `CALL { ... } IN TRANSACTIONS`, các batch có thể commit riêng; khi batch cuối lỗi, những batch trước có thể đã commit.

Để báo cáo end-to-end, tính thời gian từ khi bắt đầu đọc dữ liệu đầu vào (hoặc bắt đầu job đã định nghĩa rõ) đến khi **tất cả transaction cần thiết được xác nhận và kết quả được đối soát**. Khi báo cáo chỉ “thời gian ghi vào Neo4j”, loại trừ thời gian phát hiện/tải nguồn nhưng phải ghi rõ ranh giới.

### 3.2. Tổng thời gian pipeline có chồng lấp

Một pipeline có thể vừa đọc batch N+1, vừa truyền batch N, vừa để Neo4j xử lý batch N−1. Vì vậy:

\[
T_{\text{end-to-end}}\neq
T_{\text{source}}+T_{\text{network}}+T_{\text{server}}
\]

trong mọi trường hợp. Phép cộng chỉ thích hợp nếu các bước chạy tuần tự, không chồng lấp. Với pipeline song song, phải xem **throughput của từng chặng**, độ dài hàng chờ và thời gian đợi tại ranh giới. Chặng có tốc độ tiêu thụ thấp nhất trong điều kiện ổn định thường giới hạn throughput tổng thể.

## 4. Thiết kế phép đo đáng tin cậy

Trước khi tối ưu, cần cố định điều kiện và biết “nhập thành công” nghĩa là gì.

1. **Định nghĩa workload:** loại node/relationship, số property, kích thước bản ghi, số dòng, tỷ lệ trùng ID, tỷ lệ cần `MERGE` so với `CREATE`, mức ràng buộc và index.
2. **Tách lượt nhập mới và cập nhật:** lần đầu tạo dữ liệu thường khác hẳn lần chạy thứ hai chỉ khớp node cũ. Không so hai lượt như cùng một phép thử.
3. **Ổn định schema:** tạo constraint/index trước phép đo, xác nhận trạng thái `ONLINE`. Không tạo hoặc xóa index giữa hai nhóm kết quả rồi kết luận về mạng.
4. **Ổn định môi trường:** ghi lại phiên bản Neo4j, edition, runtime, Java Driver, heap, page cache, CPU, RAM, IOPS, giới hạn container và tải đồng thời.
5. **Cố định đầu vào:** giữ nguyên file/record/bytes; cùng mã hóa UTF-8, định dạng ngày, quy tắc chuyển kiểu và xử lý null.
6. **Đo đủ vòng đời:** thời gian mở nguồn, parse/biến đổi, tạo batch, gửi, server chấp nhận/commit, xác nhận; lưu số lỗi và retry.
7. **Lặp lại và ghi phân bố:** có lượt warmup, thực hiện nhiều lượt độc lập, báo median/p95 cho latency; ghi tổng thời gian và throughput cả job.
8. **Cô lập khi thử nghiệm:** tránh job sản xuất cạnh tranh CPU, đĩa, heap hay khóa. Không xóa dữ liệu hoặc restart trên production để “làm nguội” cache.

Ngay cả khi dùng cùng mã nguồn, **warm run** thường khác **cold run** do page cache, query plan cache, JVM JIT, connection pool và OS filesystem cache. Nếu không điều khiển được trạng thái cache, báo rõ “lần đầu quan sát” và “sau warmup”, tránh tuyên bố chúng là các phép đo disk-cold thuần túy.

## 5. Bộ dữ liệu nhỏ có đáp án để xác nhận phép đo

Tạo tệp **`qa010_people.csv`** mã hóa UTF-8 trong thư mục import được Neo4j cho phép truy cập. Dữ liệu ví dụ:

~~~csv
personId,name,city
P001,An,Ha Noi
P002,Binh,Da Nang
P003,Chi,Ha Noi
P004,Dung,Ho Chi Minh
P005,Ha,Da Nang
P006,Giang,Ha Noi
P003,Chi,Ha Noi
~~~

File có **7 dòng dữ liệu**, nhưng chỉ **6 ID duy nhất** vì `P003` xuất hiện hai lần. Việc có một dòng trùng giúp kiểm tra xem pipeline đo “số dòng nguồn” hay “số node tạo ra”.

Dữ liệu mong đợi sau khi nhập bằng `MERGE` theo `personId`:

| Chỉ số | Đáp án |
|---|---:|
| Dòng CSV đầu vào (không tính header) | 7 |
| ID khác nhau | 6 |
| Node `QA010Person` sau lần nhập đầu | 6 |
| Node mới sau lần nhập lại cùng file | 0 |
| Node có `city = 'Ha Noi'` | 3 |
| Node có `city = 'Da Nang'` | 2 |
| Node có `city = 'Ho Chi Minh'` | 1 |

Nên chạy trong **database thực hành riêng**. Trước khi tạo dữ liệu, có thể dọn đúng label/constraint của bài này nếu không có dữ liệu khác dùng chung tên:

~~~cypher
DROP CONSTRAINT qa010_person_id IF EXISTS;
~~~

~~~cypher
MATCH (p:QA010Person)
DETACH DELETE p;
~~~

Tạo ràng buộc để `MERGE` theo ID có đường tra cứu phù hợp và chống trùng:

~~~cypher
CREATE CONSTRAINT qa010_person_id IF NOT EXISTS
FOR (p:QA010Person)
REQUIRE p.personId IS UNIQUE;
~~~

Xác nhận trạng thái index phục vụ constraint:

~~~cypher
SHOW INDEXES
YIELD name, type, state, owningConstraint
WHERE owningConstraint = 'qa010_person_id'
RETURN name, type, state, owningConstraint;
~~~

Chỉ bắt đầu phép thử khi index đã `ONLINE`. Nếu bỏ qua constraint, kết quả song song `MERGE` có thể khác về hiệu năng và tính toàn vẹn; không dùng cấu hình thiếu constraint để đại diện cho hệ thống thật đang yêu cầu uniqueness.

> **Kích thước fixture:** bảy dòng chỉ đủ kiểm tra **tính đúng và cách đo**, chưa đủ làm kết quả hiệu năng đại diện. Để benchmark nghiêm túc, dùng dữ liệu lớn hơn có phân bố ID, số property, độ dài chuỗi và tỷ lệ cập nhật gần với thực tế.

## 6. Đo riêng chặng nguồn: đọc và parse nhưng chưa ghi

### 6.1. Với LOAD CSV

Bắt đầu bằng phép kiểm tra chỉ đọc:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///qa010_people.csv' AS row
RETURN count(row) AS inputRows;
~~~

Đáp án: `inputRows = 7`. Phép đo này bao gồm công việc đọc/parse CSV của Neo4j, nhưng **chưa** tạo node, relationship hay ghi transaction log như một lượt nhập thật.

Để buộc truy cập các cột dữ liệu, có thể đo:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///qa010_people.csv' AS row
RETURN
  count(row) AS inputRows,
  sum(size(row.personId)) AS totalIdChars;
~~~

Với fixture này, `totalIdChars = 28` vì bảy ID đều dài bốn ký tự. Điều này vẫn không mô phỏng toàn bộ xử lý/chuẩn hóa/ghi, nhưng cho một **baseline đọc nguồn** có thể kiểm chứng.

**Phân tích kết quả:**

- Nếu `LOAD CSV ... RETURN count(row)` đã chậm, tập trung kiểm tra tệp nguồn, khả năng đọc, cách cung cấp file và đường mạng của **server → nguồn** (với HTTP(S)).
- Nếu đọc/parse nhanh nhưng nhập thật chậm, nghi ngờ chuyển kiểu, `MERGE`, index, ghi transaction log, khóa hoặc cấu hình batch.
- Nếu là `file:///`, thời gian đọc phụ thuộc filesystem của **máy chủ Neo4j**. Không quy thời gian này cho mạng Bolt giữa Browser/Java client và database.

Một URL HTTPS có thể thay cho `file:///` khi được cấu hình cho phép. Khi đó phép thử “chỉ đọc CSV” đo gộp **tải nguồn qua mạng + parse phía Neo4j**. Để tách hai thành phần, đo ở máy chủ nguồn hoặc dùng bản sao cùng file đặt gần Neo4j trong một phép đối chứng có kiểm soát.

### 6.2. Với nguồn do ứng dụng Java đọc

Ở ứng dụng Java, đo riêng:

- Thời gian đọc bytes từ nguồn (đĩa, API, JDBC, Kafka, object storage).
- Thời gian giải nén, parse, kiểm tra schema, chuyển kiểu, chuẩn hóa chuỗi.
- Số dòng/s và MiB/s mà ứng dụng có thể cung cấp **khi tạm không gọi Neo4j**.
- Tỷ lệ dòng lỗi và số byte đã xử lý.

Nếu nguồn chỉ cung cấp 800 dòng/s trong một test không ghi DB, còn Neo4j có thể chấp nhận 5.000 dòng/s ở workload tương tự, **nguồn** là ứng viên nút thắt mạnh. Nhưng kết luận này chỉ vững khi test có cùng chi phí chuyển đổi và không bị thay đổi cache nguồn, số luồng hoặc kích thước record.

## 7. Đo mạng giữa ứng dụng và Neo4j mà không ghi dữ liệu

Với Java Driver/Bolt, gửi một **batch tham số** nhưng chỉ đếm số phần tử thay vì ghi:

~~~cypher
UNWIND $rows AS row
RETURN count(row) AS receivedRows;
~~~

Ví dụ `$rows`:

~~~json
[
  {"personId": "P001", "name": "An", "city": "Ha Noi"},
  {"personId": "P002", "name": "Binh", "city": "Da Nang"}
]
~~~

Kết quả phải là `receivedRows = 2`. Đây là phép đo **vận chuyển/serialize/deserialize tham số cộng với thực thi Cypher rất nhẹ**, không phải phép đo băng thông TCP thuần túy. Nó cũng chưa có chi phí khóa và commit ghi.

Cách cô lập hợp lý:

1. Tạo sẵn batch trong bộ nhớ ứng dụng **trước khi bấm giờ**, để bỏ chi phí đọc nguồn.
2. Gọi query trên nhiều batch bằng **connection pool đã warmup** và tiêu thụ hết kết quả.
3. Ghi kích thước payload sau serialize nếu bộ thư viện/hạ tầng hỗ trợ, latency p50/p95, CPU client và lưu lượng mạng.
4. Giữ cùng Neo4j server và cùng tham số, so kết quả khi ứng dụng chạy **gần server** với khi chạy tại môi trường kết nối từ xa.
5. Tăng kích thước batch từng bước để quan sát liệu throughput có bão hòa theo băng thông, round-trip time (RTT) hay CPU serialize.

Dấu hiệu mạng có vấn đề thường là **latency tăng theo khoảng cách mạng hoặc payload**, lượng bytes/s gần trần đường truyền, nhiều retransmission/timeouts hoặc server còn dư CPU/đĩa nhưng không nhận đủ yêu cầu. Trên hệ thống dùng `neo4j://`, Bolt có thể qua routing giữa các server; cần ghi rõ địa chỉ endpoint và đường đi thực, không giả định mọi request đi tới cùng một máy.

**Chú ý an toàn:** gửi đi gửi lại một batch trong phép thử read-only có thể làm nóng connection pool/JVM. Đừng tự suy rằng độ trễ giảm là do Neo4j page cache; truy vấn `count(row)` không đọc các node của graph.

## 8. Đo baseline máy chủ Neo4j mà không phụ thuộc CSV

Để kiểm tra riêng năng lực thực thi ghi ở server, có thể sinh một tập node thử nghiệm ngay bằng Cypher. Ví dụ dưới đây dành cho bản hỗ trợ **variable scope clause `CALL (i) { ... }` (Neo4j 5.23+ / Cypher hiện hành)**; chạy trong **implicit/auto-commit transaction**, không bọc bằng managed/explicit transaction:

~~~cypher
UNWIND range(1, 10000) AS i
CALL (i) {
  CREATE (:QA010Synthetic {
    runId: 'R01',
    seq: i,
    payload: 'fixed-payload'
  })
} IN TRANSACTIONS OF 1000 ROWS;
~~~

Kỳ vọng lần chạy đầu là **10.000 node mới**, chia thành các transaction con khoảng 1.000 dòng. Kiểm tra:

~~~cypher
MATCH (n:QA010Synthetic {runId: 'R01'})
RETURN count(n) AS created;
~~~

Đáp án: `created = 10000` nếu toàn bộ câu lệnh thành công và vùng test ban đầu không có node `runId='R01'`.

So sánh phép thử này với nhập CSV giúp phát hiện khi chi phí nguồn/network có thể đóng vai trò lớn, nhưng **không thể coi đây là phép đo ghi thuần túy tuyệt đối**: server vẫn phải sinh `range`, tạo property, tạo transaction log và cập nhật các index hiện có. Đồng thời, nếu test CSV dùng `MERGE` còn synthetic dùng `CREATE`, mức chi phí ghi là **khác nhau**. Chỉ dùng đối chứng để đặt giả thuyết; muốn so sánh trực tiếp phải giữ tương đương số property, constraint/index và thao tác CREATE/MERGE.

**Lưu ý phiên bản:** trên các phiên bản trước 5.23 vẫn có `CALL { WITH i ... } IN TRANSACTIONS`; cú pháp scope clause mới có thể chưa được parser nhận. `CALL ... IN TRANSACTIONS` không chạy bên trong một explicit transaction mở bởi ứng dụng hoặc `session.executeWrite`. Neo4j Browser có thể cần chế độ auto-commit tương ứng khi chạy câu lệnh này.

Nếu một batch lỗi, các batch trước có thể đã commit. Muốn thử lại, dọn đúng các node test hoặc đặt `runId` khác và ghi rõ trong báo cáo. Tránh coi số dòng cuối cùng trong database là counter của riêng một lượt khi dữ liệu đã tồn tại từ trước.

## 9. Nhập fixture bằng LOAD CSV và chia transaction

Với file ở mục 5, nhập bằng `MERGE`:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///qa010_people.csv' AS row
CALL (row) {
  MERGE (p:QA010Person {personId: trim(row.personId)})
  SET p.name = trim(row.name),
      p.city = trim(row.city)
} IN TRANSACTIONS OF 1000 ROWS;
~~~

Trên Neo4j 5.23+ (và Cypher tương ứng), `CALL (row)` truyền biến `row` vào subquery. `IN TRANSACTIONS OF 1000 ROWS` chia công việc thành các transaction con và giảm nguy cơ một transaction khổng lồ giữ quá nhiều trạng thái. Với bảy dòng của fixture, lệnh chỉ cần một transaction con; **batch size 1000 không tự làm ví dụ nhỏ nhanh hơn**.

Để chạy trên Neo4j 5.x cũ hơn, thay subquery bằng mẫu khai báo biến kiểu cũ, và kiểm tra phiên bản thực:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///qa010_people.csv' AS row
CALL {
  WITH row
  MERGE (p:QA010Person {personId: trim(row.personId)})
  SET p.name = trim(row.name),
      p.city = trim(row.city)
} IN TRANSACTIONS OF 1000 ROWS;
~~~

Trước khi áp dụng cho dataset lớn, thử cú pháp trên phiên bản Neo4j cụ thể. Khi lỗi file URL, cần kiểm tra **thư mục import và quyền file của server**, không chỉ đường dẫn trên laptop đang mở Browser.

### 9.1. Kiểm chứng dữ liệu sau nhập

~~~cypher
MATCH (p:QA010Person)
RETURN
  count(p) AS persistedNodes,
  count(DISTINCT p.personId) AS uniqueIds,
  count(CASE WHEN p.city = 'Ha Noi' THEN 1 END) AS haNoi
;
~~~

| persistedNodes | uniqueIds | haNoi |
|---:|---:|---:|
| 6 | 6 | 3 |

Chạy lại lệnh `LOAD CSV` một lần nữa và kiểm tra: số node vẫn **6** vì `MERGE` theo ID. Nhưng **số dòng đã xử lý là 7**, còn **số node mới của lượt thứ hai bằng 0**. Đây là lý do báo cáo phải tách `inputRows`, `processedRows` và `nodesCreated`.

### 9.2. CREATE hay MERGE?

| Trường hợp | Hành vi | Tác động lên đo |
|---|---|---|
| `CREATE` | Tạo mới node/quan hệ mỗi lần chạy | Nhanh trong một số trường hợp nhưng sẽ nhân bản khi chạy lại |
| `MERGE` theo ID có constraint/index | Tìm/khớp hoặc tạo theo định danh | Có chi phí lookup, constraint, đôi khi khóa; dễ thiết kế nhập lặp an toàn |
| `MERGE` theo mẫu dài nhiều quan hệ | Có thể khớp/tạo nhiều cấu trúc phức tạp | Dễ tăng DB hits, lock contention; nên cân nhắc tách nhập node và relationship |

Đừng cải thiện throughput bằng cách bỏ hết uniqueness constraint nếu nghiệp vụ cần chống trùng. Giữ nguyên tính đúng đắn rồi tối ưu cách batch, chỉ mục và cấu trúc Cypher.

## 10. Đo batch và commit từ Neo4j Java Driver

Với ứng dụng truyền CSV/JSON qua Bolt, mẫu phổ biến là `UNWIND $rows` kết hợp `MERGE`. Ví dụ Java Driver 5+ dưới đây giả định `driver` đã khởi tạo, và `rows` là danh sách bản ghi **đã đọc sẵn**. Mỗi lời gọi xử lý một batch; phần đo từ `System.nanoTime()` đến khi `executeWrite` trả về **bao gồm thực thi transaction và commit**, cùng phần chi phí client/transport.

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import java.util.List;
import java.util.Map;

public final class ImportMeasure {
    public static double writeBatch(
            Driver driver, List<Map<String, Object>> rows) {
        String query = """
            UNWIND $rows AS row
            MERGE (p:QA010Person {personId: row.personId})
            SET p.name = row.name, p.city = row.city
            """;

        long start = System.nanoTime();
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWrite(tx -> {
                tx.run(query, Map.of("rows", rows)).consume();
                return null;
            });
        }
        double seconds = (System.nanoTime() - start) / 1e9;
        System.out.printf(
            "batchRows=%d, elapsedSeconds=%.4f, rowsPerSecond=%.1f%n",
            rows.size(), seconds, rows.size() / seconds
        );
        return seconds;
    }
}
~~~

**Cách đọc số đo:**

- Nếu `rows` đã được chuẩn bị trước, đoạn này đo **driver + mạng Bolt + Neo4j xử lý/commit**. Đọc nguồn/parse nằm ngoài khoảng đo.
- Nếu muốn đo end-to-end, hãy bấm giờ **trước khi lấy batch từ nguồn**, kết thúc sau khi commit, rồi cộng số dòng thành công của toàn bộ job.
- `executeWrite` có thể **retry giao dịch** khi gặp lỗi transient. Vì vậy, elapsed time của một batch có thể bao gồm nhiều lần thử; ghi cả số retry hoặc phân loại lỗi khi cần chẩn đoán.
- Mỗi batch phải đủ nhỏ để phù hợp giới hạn bộ nhớ/transaction và đủ lớn để giảm chi phí request/commit quá nhiều lần.
- Để làm phép thử read-only của mục 7, dùng `session.run("UNWIND $rows AS row RETURN count(row)", ...)` và tiêu thụ kết quả, rồi so với phép đo ghi. Hai phép đo chia sẻ một phần chi phí client/network nhưng không chỉ khác nhau ở I/O đĩa.

Trong Spring Data Neo4j, có thể đo tại service trước/sau lời gọi repository. Khi đo nhiều lớp, ghi rõ thời gian bao gồm mapping entity, transaction interceptor và retry ở tầng nào. Một bulk Cypher `UNWIND` thường tạo ít round trip hơn so với gọi repository `save()` từng đối tượng, nhưng kết quả thực tế còn phụ thuộc schema, cascade mapping và workload.

## 11. Phân tích nút thắt ở máy chủ Neo4j

Nếu source parse và đường truyền hoạt động nhanh, nhưng latency commit tăng hoặc hàng chờ ghi lớn dần, hãy quan sát các tài nguyên máy chủ.

| Tài nguyên | Chỉ số cần xem | Dấu hiệu và cách xác minh |
|---|---|---|
| **CPU** | CPU sử dụng, runnable threads, thời gian của query | CPU gần bão hòa khi tăng số luồng; xem chi phí parse, `MERGE`, chuyển kiểu, logic Cypher |
| **Heap / GC** | Heap used, GC pause, transaction memory, OOM/throttling | Batch lớn, tạo nhiều list/map hoặc transaction dài gây tăng cấp phát |
| **Page cache** | Hit/miss ratio, page faults, working set, I/O đọc | Nhiều lookup `MERGE`/index miss; kiểm tra index và RAM dành cho page cache |
| **Đĩa và transaction log** | Write latency, IOPS, throughput, fsync/commit latency, log/checkpoint pressure | Disk bão hòa, batch commit chậm dù CPU chưa cao |
| **Khóa và giao dịch** | Wait time, active/blocked transactions, retries/deadlocks | Nhiều worker cùng `MERGE` hoặc cập nhật cùng ID làm tranh chấp |
| **Index và constraint** | `SHOW INDEXES`, state, số index, schema | Index thiếu/chưa `ONLINE` hoặc phải cập nhật quá nhiều index cho mỗi record |
| **Mạng phía Neo4j** | Bytes/s, TCP retransmits, Bolt connection/timeout | Server không nhận đủ payload hoặc response muộn dù tài nguyên khác chưa căng |
| **Container / nền tảng** | CPU quota, memory limit, storage throttling, noisy neighbors | Host còn tài nguyên nhưng container/VM bị giới hạn |

Không có chỉ số đơn lẻ khẳng định nguyên nhân. Ví dụ **CPU sử dụng thấp** không đảm bảo máy chủ rảnh: một request có thể đang chờ khóa hoặc disk. **Page cache hit ratio cao** không đảm bảo nhập nhanh nếu transaction log ghi chậm. **Đĩa có nhiều write bytes** chưa đủ để nói đĩa đã đạt giới hạn IOPS hoặc latency.

### 11.1. Dùng EXPLAIN và PROFILE đúng mục đích

~~~cypher
EXPLAIN
UNWIND $rows AS row
MERGE (p:QA010Person {personId: row.personId})
SET p.name = row.name, p.city = row.city;
~~~

`EXPLAIN` không chạy lệnh ghi, giúp kiểm tra planner có dự kiến dùng index để khớp ID hay không. Trong môi trường **test**, bạn có thể dùng `PROFILE` để xem `Rows`, `DB Hits`, operator và kế hoạch thực tế, nhưng `PROFILE` **sẽ thực thi lệnh ghi** và có overhead quan sát. Do đó, không dùng số latency có `PROFILE` làm throughput ứng dụng; không chạy `PROFILE` trên production nếu không kiểm soát tác động.

`DB Hits` là công việc logic của query engine, **không phải số lần đọc/ghi SSD**. Page cache misses và chi phí transaction log phải được đo riêng qua execution plan/metrics của phiên bản tương ứng.

### 11.2. Kiểm tra giao dịch đang chậm

Tài khoản có đủ quyền có thể xem các transaction đang hoạt động:

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, currentQuery, elapsedTime, status
RETURN transactionId, currentQuery, elapsedTime, status
ORDER BY elapsedTime DESC;
~~~

Đây chỉ là ảnh chụp tại một thời điểm. Để xác định lock contention, xem thêm monitoring, log giao dịch, retry và các trường khóa/chờ mà phiên bản Neo4j cung cấp. Không coi một query đang chạy lâu là bằng chứng tự thân của deadlock.

## 12. Thí nghiệm kiểm chứng nút thắt theo kiểu đối chứng

Khi các yếu tố khác giữ nguyên, **thay đúng một biến** và so với baseline:

| Phép đối chứng | Nếu nhanh lên đáng kể | Điều vẫn cần kiểm tra |
|---|---|---|
| Đọc nguồn → đếm dòng, bỏ ghi Neo4j | Việc ghi/commit có thể là phần chi phí lớn | Chưa tách mạng và chuyển kiểu nếu nguồn HTTP |
| Tạo sẵn batch trong RAM rồi gửi `UNWIND` | Nếu cải thiện mạnh so end-to-end, nguồn/parse là ứng viên | Workload `MERGE` và tỷ lệ trùng phải giống nhau |
| Đọc CSV từ local server thay vì HTTP remote (cùng bytes) | Mạng/server nguồn HTTP có thể hạn chế throughput | Local disk và cache cũng khác; cần nhiều lượt |
| Đưa ứng dụng Java gần Neo4j, cùng batch/đường query | Bolt RTT/băng thông hoặc routing có thể là vấn đề | Không kết luận nếu đồng thời thay CPU/runtime client |
| Tăng batch 100 → 500 → 1000 → 5000 | Nếu tăng throughput và giảm request/s, overhead batch/commit đáng kể | Chú ý heap, p95, lock, transaction memory |
| Tăng workers 1 → 2 → 4 → 8 | Nếu throughput tăng gần tuyến tính, còn dư năng lực | Dừng khi p95/retries/CPU/I/O tăng nhưng throughput chững |
| Thay `CREATE` bằng `MERGE` hoặc ngược lại | Chi phí lookup/uniqueness có thể chiếm lớn | Phải giữ mục tiêu đúng của nghiệp vụ; đây là workload khác |
| Thêm index phù hợp trước khi `MERGE` theo ID | Giảm lookup/scan trên dữ liệu lớn | Chi phí cập nhật index khi ghi cũng tăng; đo tổng thể |

Một cách ước lượng **đỉnh throughput** hữu ích là thử cùng tập dữ liệu ở các mức concurrency, ghi:
- `X`: committed rows/s;
- `L50` và `L95`: latency batch;
- `E`: lỗi/retry;
- CPU, RAM/GC, cache miss, write latency và queue depth.

Chọn cấu hình gần vùng có throughput tốt **mà latency/retry vẫn chấp nhận được**, không chạy nhiều worker nhất có thể. Khi tăng workers mà `X` không tăng, nhưng `L95` và lock waits tăng, thêm concurrency chỉ khuếch đại ùn tắc.

## 13. Bảng chẩn đoán nhanh theo triệu chứng

| Quan sát | Nút thắt có khả năng | Phép kiểm tra kế tiếp |
|---|---|---|
| Không bật ghi Neo4j mà nguồn vẫn chỉ đọc được ít rows/s | Nguồn/parse | Đo tách I/O, giải nén, chuyển kiểu, lỗi schema |
| Java chuẩn bị batch rất lâu, trong khi Bolt/commit nhanh | CPU hoặc I/O ở ứng dụng nguồn | Đo serialization, parse, GC phía client; lấy batch sẵn trong RAM |
| Thay local/remote network làm throughput khác rõ, Neo4j còn dư CPU/đĩa | Network/RTT/routing | So bytes/s, RTT, retransmission, payload size và TLS |
| `LOAD CSV` từ HTTP chậm, bản sao file trên server nhanh | Nguồn HTTP hoặc đường mạng server → nguồn | Đo HTTP response/chunk, thời gian download, CPU host cung cấp |
| Rows/s không tăng khi thêm workers, CPU Neo4j bão hòa | CPU server | `PROFILE` trên fixture, số operator/DB Hits, chuyển kiểu và MERGE |
| Commit p95 tăng, CPU thấp, disk write latency cao | Transaction log/đĩa | Kiểm tra write IOPS, fsync, log/checkpoint, storage throttle |
| Batch lớn khiến GC/OOM hoặc tx memory tăng | Bộ nhớ giao dịch | Giảm batch, kiểm tra collect/list/transaction overhead |
| Nhiều workers cùng cập nhật ID, retry/deadlock tăng | Lock contention | Phân vùng khóa theo ID, giảm đồng ghi cùng nhóm dữ liệu |
| `MERGE` chậm trên dữ liệu lớn, thiếu index theo ID | Truy vấn lookup | Tạo unique constraint/index thích hợp và đợi `ONLINE` |
| Input rows/s cao nhưng node count không tăng như kỳ vọng | Dòng trùng, cập nhật, bỏ qua lỗi hoặc phép đếm sai | So ID distinct, counters created/matched, errors và quy tắc MERGE |
| Lần đầu chậm, lần sau nhanh, số lượng và plan không đổi | Cache/warmup có thể góp phần | Đo page cache misses, plan cache, JIT và connection pool |

Dùng **quan sát → giả thuyết → phép đối chứng → kết luận có giới hạn**, thay vì chọn trước một giả thuyết rồi tìm chỉ số xác nhận.

## 14. Batch, transaction và concurrency: những đánh đổi chính

### 14.1. Batch quá nhỏ

Mỗi batch tạo thêm round trip và overhead transaction/commit; nếu mỗi batch chỉ có một node, network RTT và overhead có thể lấn át thời gian ghi. Tăng batch có thể cải thiện rows/s.

### 14.2. Batch quá lớn

Một batch rất lớn tăng nhu cầu heap/transaction memory, giữ khóa lâu, tạo p95 cao và có thể khiến một retry phải thực hiện lại quá nhiều việc. Trong Cypher, tạo danh sách lớn rồi `collect()` cũng có thể làm bộ nhớ tăng đáng kể.

Điểm bắt đầu để **đo thử**, không phải “giá trị tối ưu của Neo4j”: `100`, `500`, `1.000` và `5.000` dòng/batch. Tùy dung lượng property/relationship, 100 dòng có thể đã lớn, hoặc 5.000 dòng vẫn nhỏ. Theo dõi cả bytes/batch và thời gian commit.

### 14.3. Concurrency quá cao

Đa luồng giúp tận dụng CPU/đĩa nhưng có thể gây cạnh tranh tài nguyên, tăng lock waits và transaction retries. Đặc biệt với `MERGE` trên cùng khóa, hai worker có thể chờ nhau. Phân chia ID nhất quán cho workers và đảm bảo uniqueness constraints khi cần.

### 14.4. Chiến lược nhập node rồi relationship

Với graph lớn, nên xem xét nhập **node theo ID duy nhất trước**, sau đó tạo relationship sau khi đích và nguồn đã có. Tạo relationship thường phải tìm hai đầu mút bằng khóa/index; thiếu index có thể gây scan nhiều lần. Khi dùng hai giai đoạn, cần đo và đối soát cả **nodes/s** lẫn **relationships/s**; không cộng hai số rồi gọi chung “rows/s” nếu đơn vị khác nhau.

### 14.5. Nạp dữ liệu bằng công cụ offline

`neo4j-admin database import` phù hợp cho một số kịch bản **nhập CSV khối lượng rất lớn vào database mới hoặc offline**. Nó không có cùng đặc tính giao dịch trực tuyến với `LOAD CSV`/Java Driver; yêu cầu vị trí dữ liệu, quyền truy cập, downtime/điều kiện database và cú pháp tùy phiên bản.

Khi cân nhắc offline import, so sánh tổng thời gian **chuẩn bị file, tắt/khởi tạo database theo quy trình, chạy import, kiểm tra dữ liệu, xây index/constraint và đưa hệ thống vào phục vụ**, không chỉ tốc độ ghi của tiện ích. Không dùng lệnh import có tùy chọn ghi đè database hiện có trong bài thực hành.

## 15. Nhật ký benchmark: dữ liệu tối thiểu cần lưu

Mỗi lần chạy nên có thông tin để người khác tái lập:

~~~text
run_id:
timestamp / neo4j_version / driver_version:
import_mode: LOAD_CSV | JAVA_DRIVER | OFFLINE
source_location: file_local | HTTP(S) | API | JDBC ...
source_rows / source_bytes:
success_rows / created_nodes / created_relationships:
failed_rows / retries:
batch_size / workers:
query_or_import_command:
constraint_and_index_state:
elapsed_source_ms / elapsed_transform_ms:
elapsed_send_and_commit_ms / elapsed_total_ms:
rows_per_second / MiB_per_second:
batch_latency_p50_ms / batch_latency_p95_ms:
client_CPU / server_CPU / heap_GC / pagecache:
disk_write_latency / IOPS / network_bytes / RTT:
notes: warmup, cache, concurrency, dataset fingerprint
~~~

Không nhất thiết hệ thống nào cũng thu thập đủ mọi trường; khi không có metric, ghi **N/A** thay vì tự điền số. Tối thiểu phải có **khối lượng dữ liệu, thời gian, bản ghi thành công, số lỗi và thiết lập workload**. Một ảnh chụp màn hình “query completed in 1.2 s” không đủ để chứng minh tốc độ nhập tốt hơn nếu nó không cho biết 1.2 s đó bao gồm gì và bao nhiêu dữ liệu đã commit.

Một ví dụ **giả định** để luyện kết luận:

| Chặng/thử nghiệm | Throughput | Chỉ số quan sát |
|---|---:|---|
| Nguồn đọc + parse, không DB | 8.000 rows/s | CPU nguồn 35% |
| Java gửi batch và chỉ `RETURN count(row)` | 12.000 rows/s | Network còn dư |
| Server synthetic `CREATE` | 6.000 rows/s | Disk write latency cao |
| End-to-end `MERGE` thực | 3.500 rows/s | CPU + lock waits cao |

Không kết luận thô rằng end-to-end nhất định đạt `min(8.000,12.000,6.000)=6.000`: phép thử `CREATE` khác `MERGE`, có ràng buộc/index và contention khác. Kết luận hợp lý là **nguồn và phép truyền no-write chưa có dấu hiệu chậm nhất**; cần profile `MERGE`/khóa/log/đĩa trên workload tương đồng trước khi quyết định tối ưu.

## 16. Kiểm tra tính đúng và an toàn khi thử lại

Đo nhập dữ liệu cần hai kết quả song song: **hiệu năng** và **tính đúng**.

- So tổng dòng đầu vào với tổng dòng đã xử lý, dòng bị loại, batch lỗi và số lần retry. Giữ danh sách lỗi để nạp lại khi cần.
- Kiểm tra số ID khác nhau, số node mới và số node có sẵn được cập nhật. Với fixture, `7 dòng nguồn → 6 node` là **đúng**, không phải tự động mất một dòng.
- Đặt unique constraint trên các khóa nghiệp vụ quan trọng; `MERGE` theo khóa để có hành vi lặp lại dự kiến.
- Tránh coi mọi lỗi là “bỏ qua được”. Nếu chỉ một phần batch được commit rồi job dừng, cần biết checkpoint và vị trí tiếp tục.
- Không đưa thông tin cá nhân, secret, token hay payload nhạy cảm vào log benchmark. Chỉ cần số liệu tổng hợp và mã lỗi hữu ích.
- Giữ query, schema, dataset và edition cố định giữa các phép đo so sánh; báo rõ khi thay đổi.

Để kiểm tra fixture sau hai lần nhập:

~~~cypher
MATCH (p:QA010Person)
RETURN
  count(p) AS persisted,
  count(DISTINCT p.personId) AS distinctIds,
  sum(CASE WHEN p.city = 'Ha Noi' THEN 1 ELSE 0 END) AS haNoi,
  sum(CASE WHEN p.city = 'Da Nang' THEN 1 ELSE 0 END) AS daNang;
~~~

Đáp án: `persisted = 6`, `distinctIds = 6`, `haNoi = 3`, `daNang = 2`. Dữ liệu từ sáu ID của fixture không thay đổi dù chạy lại `MERGE` với cùng nội dung.

## 17. Bài tập có đáp án

**Bài 1 — Tính throughput.** Một đợt nhập có 25 batch, mỗi batch 800 dòng, toàn bộ commit trong 50 giây, không có lỗi. Throughput bao nhiêu?

**Đáp án:** `25 × 800 = 20.000` dòng đã commit; `20.000 / 50 = 400 rows/s`. Nếu batch bị retry, chỉ tính mỗi dòng thành công một lần.

**Bài 2 — Phân biệt nguồn và mạng.** Java đọc API nguồn đạt 500 rows/s, còn gửi batch có sẵn trong RAM và `MERGE` vào Neo4j đạt 3.000 rows/s. Điểm cần tối ưu trước là gì?

**Đáp án:** nguồn API/parse là ứng viên nút thắt. Đo kỹ thời gian API, giới hạn rate, parse và biến đổi; không vội tăng heap Neo4j. Cần xác nhận dữ liệu và truy vấn hai phép đo đủ tương đồng.

**Bài 3 — Đọc triệu chứng máy chủ.** Thêm workers từ 2 lên 8 làm rows/s gần như không đổi, nhưng p95 commit tăng gấp bốn, lock waits và retries tăng. Giải pháp hợp lý?

**Đáp án:** giảm concurrency hoặc phân vùng ID/khóa để hạn chế tranh chấp, xem lại `MERGE` và constraint/index. Tăng thêm worker nhiều khả năng làm tắc nặng hơn.

**Bài 4 — Đếm dữ liệu đúng.** File fixture có 7 dòng, chạy hai lượt `MERGE` theo `personId`. Kết quả số node sau từng lượt và số node mới ở lượt hai?

**Đáp án:** sau lượt đầu **6 node**, sau lượt hai vẫn **6 node**; lượt hai **0 node mới**. Cần dùng `processed rows` để phản ánh 7 dòng đã được xử lý của mỗi lượt.

**Bài 5 — Vẽ đường mạng.** Một lệnh `LOAD CSV FROM 'https://...'` chạy trong Neo4j Browser ở laptop. Ai tải toàn bộ CSV qua mạng?

**Đáp án:** **Neo4j server** gửi HTTP(S) request tới nguồn CSV và nhận nội dung; Browser chỉ gửi Cypher và nhận kết quả. Để chẩn đoán, đo đường **server → HTTP source** thay vì mặc định đổ lỗi cho đường **laptop → Neo4j**.

**Bài 6 — Kết luận từ phép đối chứng.** `LOAD CSV RETURN count(row)` chỉ mất 2 giây, nhưng nhập `MERGE` 100.000 dòng mất 180 giây. Có thể khẳng định đĩa là nút thắt?

**Đáp án:** chưa. Các phép thử chỉ gợi ý **phần ghi/lookup/commit** chiếm nhiều thời gian; cần xem CPU, `PROFILE`, index, transaction log I/O, locking, GC và lỗi/retry để xác định nguyên nhân cụ thể.

## 18. Dọn dữ liệu thực hành

Trong đúng database test của bài này, sau khi đã ghi nhận số liệu:

~~~cypher
DROP CONSTRAINT qa010_person_id IF EXISTS;
~~~

~~~cypher
MATCH (p:QA010Person)
DETACH DELETE p;
~~~

~~~cypher
MATCH (n:QA010Synthetic)
DETACH DELETE n;
~~~

Kiểm tra:

~~~cypher
MATCH (n)
WHERE n:QA010Person OR n:QA010Synthetic
RETURN count(n) AS remaining;
~~~

Kỳ vọng `remaining = 0`. Các lệnh `DETACH DELETE` sẽ xóa quan hệ gắn với node có label test; không chạy nếu môi trường đã dùng các label này cho dữ liệu khác.

## 19. Tài liệu tham khảo và checklist kết luận

- [Neo4j Cypher Manual — LOAD CSV](https://neo4j.com/docs/cypher-manual/current/clauses/load-csv/): cấu hình đường dẫn, đọc file/URL và yêu cầu nhập CSV.
- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/): xử lý theo batch và hành vi commit độc lập.
- [Neo4j Java Driver Manual — Performance recommendations](https://neo4j.com/docs/java-manual/current/performance/): batch, transaction, truy vấn tham số và cách tối ưu client.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): `EXPLAIN`, `PROFILE`, `Rows` và `DB Hits`.
- [Neo4j Operations Manual — Monitoring metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/): theo dõi page cache, JVM, transaction và I/O.
- [Neo4j Operations Manual — Import](https://neo4j.com/docs/operations-manual/current/import/): cơ chế nhập offline bằng `neo4j-admin database import`.

Trước khi tuyên bố đã tìm ra nút thắt, hãy trả lời được bốn câu hỏi: **(1)** bao nhiêu bản ghi thực được commit và đáp án có đúng không; **(2)** chặng nào đang tiêu thụ chậm nhất hoặc khiến queue tăng; **(3)** đối chứng nào cho thấy khi cải thiện chặng đó thì tốc độ toàn pipeline tăng; **(4)** cải thiện có còn hiệu quả khi thay đổi batch, concurrency và kích thước dữ liệu trong điều kiện gần thực tế không?

Đo đúng ranh giới giữa **nguồn, mạng và máy chủ Neo4j** giúp lựa chọn tối ưu hóa có bằng chứng: chỉnh parser/nguồn, đặt ứng dụng gần database, điều chỉnh batch, sửa `MERGE`/index hoặc nâng tài nguyên server khi thực sự cần.
