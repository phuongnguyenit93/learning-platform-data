# Các chỉ số độ trễ, thông lượng, khóa và giao dịch lỗi

Một ứng dụng dùng Neo4j có thể vẫn trả dữ liệu đúng nhưng dần chậm đi: API mất 2 giây thay vì 100 ms, giao dịch ghi phải chờ khóa, hoặc các lần thử lại của Java Driver làm độ trễ tăng dù người dùng cuối không thấy exception. Để tìm nguyên nhân, chỉ xem CPU hoặc số kết nối Bolt là không đủ. Cần kết hợp **độ trễ (latency)**, **thông lượng (throughput)**, **tranh chấp khóa (lock contention)** và **giao dịch thất bại/rollback**, rồi đối chiếu chúng với **truy vấn Cypher thực tế**.

Đây là bài trong chương **Giám sát** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module bao quát property graph, node, relationship, Cypher, index, constraint, nhập dữ liệu, Java Driver, Spring Data Neo4j và vận hành Neo4j. Bốn nhóm tín hiệu dưới đây giúp kết nối hiệu năng ở lớp ứng dụng với hoạt động truy vấn và transaction trong database, từ đó xác định nên sửa Cypher, mô hình liên kết, chỉ mục, thời hạn transaction hay cấu hình tài nguyên.

> **Lưu ý phiên bản và môi trường:** Ví dụ dựa trên khả năng của Neo4j 5 và họ bản phát hành mới hơn. **Neo4j Enterprise Edition** có hệ thống metrics phong phú (CSV/JMX/Prometheus/Graphite); Neo4j Community và các gói Aura có phạm vi quan sát, cách xuất dữ liệu và quyền khác nhau. Tên metric, trường `SHOW TRANSACTIONS` và cấu hình log có thể thay đổi giữa các bản. Trước khi tạo dashboard, kiểm tra **metrics thực sự được xuất** và tài liệu đúng phiên bản đang chạy.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt độ trễ **từ góc nhìn ứng dụng**, độ trễ thực thi **phía Neo4j**, thời gian chờ khóa và thời gian lấy kết nối.
2. Tính queries/second và transactions/second đúng cách từ **counter**, không lấy giá trị counter tích lũy làm tốc độ tức thời.
3. Đọc `SHOW TRANSACTIONS` để tìm giao dịch chạy lâu, chờ khóa và giữ nhiều khóa.
4. Phân biệt **failed query**, **rolled-back transaction**, **terminated transaction** và **deadlock**.
5. Kết hợp query log, metrics, `EXPLAIN`/`PROFILE` và đo đạc Java Driver/SDN để điều tra truy vấn chậm.
6. Thiết lập bảng điều khiển và cảnh báo có căn cứ vào baseline, SLO, phiên bản Neo4j và đặc điểm workload.

## 2. Nhìn tín hiệu từ ba lớp khác nhau

Một yêu cầu `GET /orders/{id}` có thể đi qua:

~~~mermaid
flowchart LR
    U["Client / API"] --> A["Java Service / Spring Data Neo4j"]
    A --> P["Java Driver<br/>connection pool, retry, routing"]
    P --> B["Bolt / Neo4j Server"]
    B --> Q["Cypher planner + execution"]
    Q --> L["Graph store<br/>index, relationship, khóa"]
    L --> Q --> B --> P --> A --> U
~~~

**Độ trễ người dùng cảm nhận** có thể bao gồm xếp hàng ở web server, logic Java, lấy kết nối, DNS/TLS, network, routing, retry, chạy Cypher, trả dữ liệu qua Bolt và mapping đối tượng. Trong khi đó, **metrics query latency phía Neo4j** đo giai đoạn cụ thể của server; nó không thay thế độ trễ API end-to-end.

| Lớp đo | Thường đo gì? | Khi nào hữu ích? |
|---|---|---|
| **Ứng dụng / API** | Request latency, tỷ lệ lỗi, thời gian repository, số lần thử lại | Xác định tác động đến người dùng và SLO |
| **Driver / kết nối** | Chờ lấy connection, connection timeout, retry, số kết nối đang sử dụng | Phân biệt DB chậm với việc chờ pool, network hoặc routing |
| **Neo4j Server** | Query latency, query success/failure, transaction active/committed/rollbacks, locks, CPU, heap, page cache | Tìm nút thắt bên trong database |

Không thể đồng nhất ba số đo chỉ vì chúng cùng dùng đơn vị mili giây.

## 3. Bốn nhóm tín hiệu cốt lõi

| Nhóm | Câu hỏi vận hành | Chỉ số nên quan sát | Hành động phân tích tiếp theo |
|---|---|---|---|
| **Latency** | Người dùng có chậm không? Query nào chậm? | p50, p95, p99 theo endpoint/query; server execution histogram | So client/server, phân loại query, `PROFILE` |
| **Throughput** | Có bao nhiêu truy vấn và giao dịch hoàn tất mỗi giây? | Queries/s, commits/s, writes/s, concurrent transactions | So với mức tải và tài nguyên |
| **Locks** | Transaction nào đang chờ nhau hoặc giữ khóa lâu? | `waitTime`, `currentQueryWaitTime`, `activeLockCount`, số transaction active | Dò query và tài nguyên nóng, giảm tranh chấp |
| **Failed transactions** | Những transaction nào rollback, bị terminate hay deadlock? | `rollbacks`, `rollbacks_write`, `terminated`, `rollbacks_deadlocked` nếu có, mã lỗi | Phân loại lỗi, xem retry/timeout/idempotency |

Một **đợt tăng độ trễ** có thể do tranh chấp khóa, nhưng cũng có thể do thiếu index, query mở rộng quá nhiều relationship, heap/GC, page-cache miss hay bão hòa CPU. Cần quan sát **tương quan giữa các chỉ số** thay vì kết luận từ một đường biểu đồ.

## 4. Độ trễ: phải đo đúng ranh giới

### 4.1. Latency phía ứng dụng và phía database

Ví dụ một request thực tế mất 260 ms:

~~~text
Request /orders/O01       = 260 ms end-to-end (ví dụ giả định)
  Java và validation      = 25 ms
  Lấy kết nối / routing   = 35 ms
  Neo4j query execution   = 100 ms
  Truyền + ánh xạ kết quả = 70 ms
  Các bước khác           = 30 ms
~~~

Đây là **số minh họa**, không phải số đo Neo4j cụ thể. Nó chỉ ra tại sao một truy vấn mất 100 ms ở server vẫn có thể tạo API 260 ms. Trong thực tế, các pha có thể **chồng lấn**, vì driver lấy record theo luồng và ứng dụng xử lý đồng thời, nên không luôn cộng được các số phase một cách đơn giản.

Đặt tên số đo rõ:

- `http.request.duration`: thời gian hoàn tất HTTP request theo endpoint, từ góc nhìn ứng dụng.
- `repository.operation.duration`: thời gian gọi repository/service đến khi đã xử lý kết quả cần thiết.
- `driver.connection.acquire.duration`: thời gian chờ lấy kết nối từ pool, **nếu ứng dụng có instrumentation đo được**.
- `neo4j.query.execution.latency`: thời gian server đo theo định nghĩa của metric tương ứng.

Tên ở ba dòng đầu là **tên metric ví dụ do ứng dụng tự đặt**, không phải metric mặc định bắt buộc của Neo4j Driver. Khi triển khai với Micrometer/OpenTelemetry, hãy sử dụng tên và đơn vị thực tế do instrumentation cung cấp.

### 4.2. p50, p95 và p99 không phải trung bình

**Percentile** mô tả phân bố thời gian:

- **p50:** khoảng một nửa số yêu cầu có latency không vượt quá mốc này; xấp xỉ trung vị.
- **p95:** khoảng 95% yêu cầu hoàn tất ở hoặc dưới mốc; 5% còn lại chậm hơn.
- **p99:** tập trung vào phần đuôi chậm nhất, thường quan trọng đối với trải nghiệm không ổn định.

Ví dụ (dữ liệu giả định):

| Endpoint | p50 | p95 | p99 | Nhận xét |
|---|---:|---:|---:|---|
| `GET /orders/{id}` | 25 ms | 95 ms | 320 ms | Phần đuôi chậm đáng quan sát |
| `POST /orders` | 50 ms | 180 ms | 1.200 ms | Có thể chịu ảnh hưởng ghi/khóa/retry |
| `GET /recommendations` | 130 ms | 490 ms | 2.100 ms | Cần xem độ rộng traversal và kết quả trả |

Nếu tất cả số liệu được đo trong những khung thời gian khác nhau hoặc trên những nhóm request khác nhau, so sánh sẽ sai. Luôn ghi rõ **cửa sổ đo**, đơn vị, số lượng mẫu, endpoint và phân đoạn theo kết quả thành công/thất bại.

**Không lấy trung bình số học của các p95 theo từng máy để tính p95 toàn hệ thống.** Để tổng hợp percentile đúng, phải hợp nhất phân bố/histogram hoặc dữ liệu mẫu theo cách công cụ hỗ trợ.

### 4.3. Histogram Neo4j và giới hạn diễn giải

Trong họ metric Enterprise được Neo4j công bố, metric query latency có dạng logic:

~~~text
<prefix>.db.query.execution.latency.millis
~~~

Đây là **histogram thời gian thực thi của các query thành công** tính bằng mili giây. Các metric liên quan có thể gồm:

~~~text
<prefix>.db.query.execution.success
<prefix>.db.query.execution.failure
~~~

Hai dòng cuối là **counter**; khác với histogram đo latency. Đừng dùng chỉ số latency của **query thành công** để kết luận rằng query lỗi không làm người dùng chờ lâu: lỗi timeout hoặc truy vấn thất bại sau thời gian dài vẫn có thể tác động mạnh tới API và không được phản ánh đầy đủ trong histogram thành công đó.

**Metric query** và **metric transaction** cũng khác đơn vị đếm: một transaction có thể chạy nhiều câu Cypher. Với `CALL { ... } IN TRANSACTIONS`, một lệnh ngoài có thể khởi tạo nhiều giao dịch con. Không ép “1 API call = 1 Cypher query = 1 transaction”.

## 5. Thông lượng: tính tốc độ từ bộ đếm

**Throughput** là khối lượng công việc hoàn thành trên một đơn vị thời gian, ví dụ `queries/s`, `transactions/s` hoặc `rows/s`. Trước hết hãy xác định **thành công** hay **đã bắt đầu**, **đọc** hay **ghi**, và bộ đếm thuộc một DBMS hay một database cụ thể.

| Đại lượng | Cách tính khái niệm | Đơn vị |
|---|---|---|
| Successful query throughput | `ΔsuccessfulQueries / Δseconds` | query/s |
| Failed query rate | `ΔfailedQueries / Δseconds` | failed query/s |
| All completed query rate | `(Δsuccess + Δfailure) / Δseconds` | query/s |
| Committed transaction throughput | `ΔcommittedTransactions / Δseconds` | committed tx/s |
| Committed writes throughput | `ΔcommittedWriteTransactions / Δseconds` | committed write tx/s |
| Rollback rate | `ΔrolledBackTransactions / Δseconds` | rolled-back tx/s |

`Δcounter = counter(t2) − counter(t1)` trong cùng nguồn và cùng epoch hoạt động; **không lấy giá trị counter hiện tại chia cho một giây**. Counter có thể reset khi server khởi động lại, metric exporter đổi hoặc database tái tạo; khi dùng Prometheus, hàm `rate(...)`/`increase(...)` có xử lý những trường hợp reset mà dữ liệu thu thập cho phép.

### Ví dụ tính theo cửa sổ năm phút

Giả sử một hệ thống chỉ có một database nghiệp vụ và các bộ đếm được đo trong **cùng cửa sổ 300 giây**:

| Counter | Đầu cửa sổ | Cuối cửa sổ | Chênh lệch |
|---|---:|---:|---:|
| Query success | 120.000 | 121.800 | 1.800 |
| Query failure | 700 | 760 | 60 |
| Transaction started | 43.000 | 43.950 | 950 |
| Transaction committed | 42.000 | 42.900 | 900 |
| Transaction rolled back | 900 | 950 | 50 |

Các phép tính:

~~~text
Successful query throughput = 1800 / 300           = 6.0 query/s
All completed query rate    = (1800 + 60) / 300    = 6.2 query/s
Query failure ratio         = 60 / (1800 + 60)     ≈ 3.23%
Committed tx throughput     = 900 / 300            = 3.0 tx/s
Rolled-back tx rate         = 50 / 300             ≈ 0.167 tx/s
Rollback fraction (tham khảo) = 50 / (900 + 50)    ≈ 5.26%
~~~

**Đây là dữ liệu minh họa, không phải kết quả đã đo.** Trong hệ thống thật, mối quan hệ giữa `started`, `committed` và `rollbacks` có thể lệch ở ranh giới cửa sổ vì transaction bắt đầu trước, kết thúc sau hoặc còn hoạt động. Số `query failures` không nhất thiết bằng số `rolled-back transactions`.

### Throughput không tự chứng minh hệ thống khỏe

Khi throughput giảm, có ít nhất hai kịch bản khác nhau:

1. **Nhu cầu giảm:** API nhận ít request hơn, latency vẫn thấp, lỗi không tăng.
2. **Hệ thống nghẽn:** lượng request đầu vào cao nhưng số request/tx **hoàn thành** giảm, hàng đợi và latency tăng.

Muốn phân biệt, cần so **request arrival rate ở ứng dụng** với **completion rate**, concurrent transactions, pool wait, CPU, GC và số request bị timeout.

### Concurrency khác throughput

`transaction.active` là **gauge** cho số transaction đang hoạt động tại thời điểm lấy mẫu. Nó không phải `transactions/s`. Concurrency cao có thể là truy vấn đọc dài, import lớn hoặc contention; cần xem cả phân bố latency.

Một trực giác hữu ích cho hệ thống ổn định là **Little's Law**: số công việc trung bình trong hệ thống xấp xỉ `arrival rate × average time in system`, miễn là cùng biên đo và điều kiện thích hợp. Ví dụ 20 request/s với thời gian trung bình 0,2 giây tương ứng khoảng 4 request đang được phục vụ ở biên đó. Không áp công thức này trực tiếp cho số active transaction nếu request còn có nhiều pha ngoài Neo4j.

## 6. Những metric Neo4j quan trọng

Neo4j phân biệt metric **global** của DBMS và metric **theo database**. Với prefix mặc định `neo4j` và database ví dụ `orders`, một transaction metric có dạng:

~~~text
neo4j.database.orders.transaction.committed
~~~

Prefix có thể cấu hình bằng `server.metrics.prefix`; exporter Prometheus sẽ **chuyển đổi tên** (ví dụ dấu chấm thành dấu gạch dưới, hậu tố theo loại metric). **Không tự hard-code** một tên Prometheus chưa xem dữ liệu thực của `/metrics`.

| Metric logic trong tài liệu | Kiểu | Diễn giải |
|---|---|---|
| `<prefix>.dbms.bolt.connections_running` | Gauge | Số kết nối Bolt đang xử lý Cypher và trả kết quả |
| `<prefix>.db.query.execution.success` | Counter | Số truy vấn chạy thành công |
| `<prefix>.db.query.execution.failure` | Counter | Số truy vấn thất bại |
| `<prefix>.db.query.execution.latency.millis` | Histogram | Phân bố độ trễ thực thi query thành công |
| `<prefix>.database.<db>.transaction.started` | Counter | Transaction đã bắt đầu |
| `<prefix>.database.<db>.transaction.active` | Gauge | Transaction hiện hoạt động |
| `<prefix>.database.<db>.transaction.active_read` | Gauge | Transaction đọc hiện hoạt động |
| `<prefix>.database.<db>.transaction.active_write` | Gauge | Transaction ghi hiện hoạt động |
| `<prefix>.database.<db>.transaction.committed` | Counter | Transaction đã commit |
| `<prefix>.database.<db>.transaction.committed_write` | Counter | Transaction ghi đã commit |
| `<prefix>.database.<db>.transaction.rollbacks` | Counter | Transaction rollback |
| `<prefix>.database.<db>.transaction.rollbacks_write` | Counter | Transaction ghi rollback |
| `<prefix>.database.<db>.transaction.terminated` | Counter | Transaction bị chấm dứt |
| `<prefix>.database.<db>.transaction.peak_concurrent` | Counter/gauge ý nghĩa đỉnh theo tài liệu | Giá trị đỉnh đồng thời được ghi nhận; không phải số hiện hoạt |

**Metric `transaction.rollbacks_deadlocked`** ghi các transaction rollback vì deadlock **chỉ được giới thiệu từ Neo4j 2026.01**. Nếu ứng dụng còn Neo4j 5.x cũ, metric này có thể **không tồn tại**; dùng log/mã lỗi deadlock và phiên bản metrics phù hợp thay vì biểu đồ trống để kết luận không có deadlock.

Đừng biến từng dòng metric thành giả thiết “server có lỗi”: `active` tăng có thể do công việc nhập dữ liệu hợp lệ; `rollbacks` có thể gồm rollback có chủ đích; `terminated` có thể do quản trị viên chủ động dừng giao dịch. **Cần liên hệ với workload và ngữ cảnh.**

## 7. Khóa: nhận diện tranh chấp bằng giao dịch đang chạy

Neo4j sử dụng cơ chế khóa để bảo vệ các thao tác cập nhật node/relationship. Nếu hai transaction cùng cần cập nhật một node đang bị khóa, một transaction có thể **phải chờ**. Thời gian chờ thường biểu hiện thành latency cao dù query không có phép quét dữ liệu lớn.

### 7.1. Kiểm tra transaction bằng Cypher

Với tài khoản được phép xem thông tin transaction tương ứng:

~~~cypher
SHOW TRANSACTIONS
YIELD database, transactionId, username, status,
      elapsedTime, waitTime, activeLockCount,
      currentQuery, currentQueryWaitTime
RETURN database, transactionId, username, status,
       elapsedTime, waitTime, activeLockCount,
       currentQueryWaitTime, currentQuery
ORDER BY waitTime DESC
LIMIT 20;
~~~

Các trường có ý nghĩa:

| Trường | Cách hiểu | Giới hạn |
|---|---|---|
| `transactionId` | Định danh transaction đang quan sát | Không phải khóa nghiệp vụ; không dùng làm ID dài hạn |
| `username` | Người dùng đang chạy transaction | Chỉ thấy thông tin phù hợp quyền hiện tại |
| `status` | Trạng thái server báo tại lúc lấy mẫu | Là snapshot; có thể đổi ngay sau khi query `SHOW` |
| `elapsedTime` | Thời gian transaction đã tồn tại | Bao gồm nhiều pha, không phải toàn bộ thời gian chờ khóa |
| `waitTime` | **Thời gian tích lũy chờ lấy khóa** trong transaction | Không chắc transaction **đang** bị chặn tại thời điểm xem |
| `currentQueryWaitTime` | Thời gian chờ khóa của truy vấn hiện tại, nếu có | Có thể `null` khi không có query hiện tại |
| `activeLockCount` | Số khóa mà transaction đang giữ | **Nhiều khóa không tự đồng nghĩa** bị nghẽn hoặc là blocker |
| `currentQuery` | Cypher đang chạy | Có thể chứa thông tin nhạy cảm; cần quyền và quy tắc log phù hợp |

Lọc những giao dịch có thời gian chờ khóa đáng kể **trong bản chụp hiện tại**:

~~~cypher
SHOW TRANSACTIONS
YIELD database, transactionId, username, status,
      elapsedTime, waitTime, activeLockCount, currentQuery
WHERE database = 'neo4j'
  AND waitTime > duration({seconds: 1})
RETURN transactionId, username, status,
       elapsedTime, waitTime, activeLockCount, currentQuery
ORDER BY waitTime DESC;
~~~

Đây là **truy vấn chỉ quan sát**, không chặn hoặc kết thúc transaction. `waitTime > 1s` nghĩa là transaction đã tích lũy hơn một giây chờ khóa, **không nhất thiết đang chờ**. Muốn xác định trạng thái bị chặn ở thời điểm đó, kết hợp `status`, các chi tiết transaction được phiên bản hỗ trợ, nhiều lần lấy mẫu và query log.

### 7.2. Chẩn đoán tranh chấp khóa bằng nhiều bằng chứng

Giả sử nhiều request đồng thời cập nhật cùng `:Account {accountId:'A01'}`. Một giao dịch giữ khóa ghi, các giao dịch khác phải chờ:

~~~text
TX-1: cập nhật A01 ---- giữ khóa ghi ----- COMMIT
TX-2: cập nhật A01 .... đợi khóa ......... cập nhật / COMMIT
TX-3: cập nhật A01 .... đợi khóa ................. cập nhật / COMMIT
~~~

Các dấu hiệu hỗ trợ giả thuyết contention:

1. **p95/p99 của API ghi tăng** trong cùng thời gian.
2. `SHOW TRANSACTIONS` cho thấy một số transaction có `waitTime`/`currentQueryWaitTime` cao.
3. Có transaction đang giữ khóa lâu, transaction ghi active tăng hoặc backlog ở ứng dụng.
4. Query log chỉ ra các câu `SET`/`MERGE` cùng đánh vào những khóa nghiệp vụ.
5. Nếu deadlock xảy ra, log/status code hoặc metric `rollbacks_deadlocked` (ở bản hỗ trợ) tăng.

**Không suy luận** rằng mọi transaction có `activeLockCount` lớn là nguyên nhân gây nghẽn. Transaction import hợp lệ có thể giữ nhiều khóa nhưng không có request khác chờ chúng.

### 7.3. Biện pháp giảm contention thường hiệu quả

- **Rút ngắn transaction:** không gọi HTTP API, gửi email hoặc xử lý dữ liệu lâu trong transaction đang giữ khóa.
- **Giảm “hot node”:** thiết kế lại thao tác cộng dồn vào một node cực kỳ phổ biến nếu mức ghi đồng thời quá cao.
- **Ổn định thứ tự khóa:** khi ghi nhiều node, truy cập chúng theo thứ tự nhất quán để giảm nguy cơ deadlock.
- **Điều chỉnh batch size:** import lô rất lớn có thể giữ khóa và dùng nhiều bộ nhớ lâu.
- **Không tăng song song vô hạn:** quá nhiều writer trên cùng tập khóa có thể làm throughput giảm và latency tăng.
- **Tối ưu truy vấn xác định tập node trước khi cập nhật:** dùng index và điều kiện lọc chọn lọc, nhưng nhớ rằng index nhanh **không loại bỏ** cạnh tranh ghi vào cùng node.

## 8. Deadlock và transaction lỗi: đừng gộp tất cả thành một số

### 8.1. Các trạng thái kết thúc khác nhau

| Hiện tượng | Ý nghĩa | Có phải lỗi luôn không? |
|---|---|---|
| Query success | Một câu Cypher thực thi thành công | Không nói toàn transaction đã commit nếu còn bước sau |
| Query failure | Một câu Cypher thất bại | Có thể dẫn đến rollback transaction |
| Transaction committed | Transaction kết thúc bằng commit | Có thể chỉ gồm đọc; không đồng nghĩa số node được tạo |
| Transaction rolled back | Transaction hủy những thay đổi chưa commit | Có thể do lỗi, cancellation hoặc rollback có chủ đích |
| Transaction terminated | Transaction bị chấm dứt | Cần xem lý do: timeout, quản trị, hủy theo chính sách, ... |
| Deadlock detected | Các transaction giữ/chờ khóa theo vòng khiến Neo4j phải hủy một transaction | Là tình huống transient trong nhiều trường hợp; cần xử lý retry đúng |

Khi Neo4j phát hiện deadlock, một mã lỗi quen thuộc là:

~~~text
Neo.TransientError.Transaction.DeadlockDetected
~~~

Trên driver/server mới, có thể có thêm GQLSTATUS, thông tin cause và classification. Ghi nhận **exception class, Neo4j code, GQLSTATUS (nếu có)** và transaction/query ID; không phân loại chỉ bằng văn bản `getMessage()`.

### 8.2. Vì sao số query failure không bằng số transaction rollback?

Một transaction có thể thực thi nhiều câu Cypher; một câu bị lỗi có thể khiến cả transaction rollback. Ngược lại, ứng dụng có thể chủ động rollback transaction **mà không có lỗi query**. Ngoài ra:

- Một transaction **đã bắt đầu** trong cửa sổ đo có thể chỉ **commit** ở cửa sổ sau.
- Một transaction có thể chứa nhiều **query**.
- Java Driver có thể **retry managed transaction**, nên các lần thử ở server có thể nhiều hơn số request lỗi cuối cùng ở API.
- Với lệnh `CALL { ... } IN TRANSACTIONS`, có thể đã có nhiều transaction con commit trước khi job ngoài gặp lỗi.

Vì vậy, dashboard nên hiển thị **riêng** số query failure, transaction rollbacks và error rate ứng dụng; không cộng chúng lại để gọi là “tổng lỗi”.

### 8.3. Phân loại lỗi để quyết định retry

| Nhóm lỗi | Ví dụ | Cách xử lý ban đầu |
|---|---|---|
| Sai yêu cầu | Cypher syntax, không đủ quyền, vi phạm constraint | Sửa query/role/dữ liệu; không retry y nguyên |
| Lỗi tạm thời | Deadlock, leader switch, mất kết nối ngắn | Có thể retry có giới hạn khi callback/idempotency phù hợp |
| Tài nguyên quá tải | Transaction timeout, heap/GC, disk full | Điều tra nguyên nhân và giới hạn retry |
| Hủy có chủ đích | Application cancellation, admin terminate | Phân biệt với lỗi hệ thống; ghi lý do |
| Không rõ commit | Kết nối mất ngay lúc server commit | Kiểm tra khóa idempotency trước khi chạy lại tác vụ ghi |

Khi dùng `session.executeRead(...)` hoặc `session.executeWrite(...)`, driver có thể tự retry các lỗi được coi là transient theo ngân sách thời gian đã cấu hình. **Không thêm vòng retry vô hạn** ở tầng API mà không xét retry đã có. Với lệnh ghi, bảo vệ thao tác bằng **khóa nghiệp vụ/constraint** để tránh ghi trùng trong tình huống kết quả commit không rõ.

## 9. Xuất metrics cho hệ thống quan sát

Trong **Neo4j Enterprise self-managed**, các kênh xuất metrics có thể gồm CSV, JMX, Graphite và Prometheus. Với Prometheus, ví dụ cấu hình trong `neo4j.conf`:

~~~properties
# Enterprise self-managed - minh họa cấu hình endpoint trên localhost.
server.metrics.prometheus.enabled=true
server.metrics.prometheus.endpoint=localhost:2004
~~~

Sau khi áp dụng và khởi động lại theo yêu cầu phiên bản, Prometheus scraper có thể thu thập endpoint từ vị trí được phép. **Không mở `0.0.0.0:2004` ra Internet**; nếu cần monitor qua mạng, sử dụng mạng nội bộ/tunnel/proxy có xác thực, TLS và firewall phù hợp. Endpoint metrics có thể tiết lộ trạng thái hoạt động, mức tải và thông tin hạ tầng.

### Gauge, counter và histogram phải được xử lý khác nhau

| Loại | Ví dụ | Cách vẽ đúng |
|---|---|---|
| **Gauge** | Transaction `active`, Bolt `connections_running` | Vẽ giá trị theo thời gian, xem mức hiện tại/đỉnh |
| **Counter** | `committed`, `rollbacks`, query `success`/`failure` | Tính `rate` hoặc `increase` theo cửa sổ; lưu ý reset |
| **Histogram** | Query execution latency | Dùng phép tính phân vị/quantile đúng với kiểu histogram và exporter |

Tên metric trong tài liệu Neo4j dùng dấu chấm; tên được xuất sang Prometheus có thể đổi dấu và thêm hậu tố tùy loại. Trước khi viết truy vấn PromQL:

1. Kiểm tra endpoint đang trả metrics nào và loại nào.
2. Đọc dòng `HELP`/`TYPE` trong payload Prometheus.
3. Phân biệt prefix, tên database, server instance và các nhãn do exporter gắn.
4. Xác định query rate là **server-wide** hay theo database/cluster; tránh đếm cùng hoạt động nhiều lần ở tầng routing/replication.
5. Đánh giá ảnh hưởng khi exporter/Neo4j cập nhật hoặc counter reset.

**Đừng gộp các quantile của từng instance bằng phép `avg`**. Khi muốn p95 toàn hệ thống, cần histogram có thể tổng hợp hợp lệ hoặc tính từ dữ liệu gốc đủ thông tin.

## 10. Query log: liên kết biểu đồ với câu Cypher cụ thể

Các metrics cho biết **có vấn đề**, còn query log giúp tìm **truy vấn nào** liên quan. Với bản Neo4j hỗ trợ query logging, ví dụ cấu hình `neo4j.conf` cho môi trường kiểm tra:

~~~properties
# Chỉ log query hoàn tất lâu hơn ngưỡng; điều chỉnh theo chính sách.
db.logs.query.enabled=INFO
db.logs.query.threshold=250ms
db.logs.query.parameter_logging_enabled=false
~~~

Ở nhiều bản Neo4j hiện đại, `INFO` log query kết thúc vượt ngưỡng, còn `VERBOSE` có thể log bắt đầu/kết thúc. **Không giả định** mọi phiên bản có mặc định giống nhau. Nếu cần phân tích giao dịch mở lâu sau khi câu query đã chạy xong, tài liệu hỗ trợ log vòng đời transaction:

~~~properties
# Minh họa, chỉ bật có kiểm soát khi cần chẩn đoán.
db.logs.query.transaction.enabled=INFO
db.logs.query.transaction.threshold=1s
~~~

**Query log không giống transaction log (WAL).** Transaction log phục vụ durability/recovery và ghi thay đổi dữ liệu; query log phục vụ quan sát truy vấn/thời gian/lỗi, không phải bản sao đầy đủ tất cả transaction đã commit.

### Chỉ số có thể đọc từ query log

Tùy format và phiên bản, log có thể cho biết query ID, transaction ID, database, người dùng, elapsed time, planning time, CPU time, page hits/faults, thời gian chờ, trạng thái thành công/thất bại và mã lỗi. Những trường này rất hữu ích để trả lời:

- **Chậm vì planning**, **execution**, **chờ khóa** hay sau khi query xong vẫn chờ commit?
- Có **truy vấn nào lặp rất nhiều lần** (N+1) từ Spring Data Neo4j không?
- Cùng một query template chạy chậm ở một số bộ tham số có độ chọn lọc thấp hay không?
- Một khoảng tăng p99 có trùng với **rollback/deadlock** hoặc **thay đổi index/schema** không?

Đừng bật log tất cả parameters/literals tùy tiện, vì tham số Cypher có thể chứa email, token và dữ liệu khách hàng. Ngoài `parameter_logging_enabled=false`, các phiên bản mới có tùy chọn che literal/lỗi; vẫn cần hạn chế quyền đọc log và thời gian lưu. Không bao giờ ghi credential từ connection string vào dashboard.

## 11. Đo thời gian từ Java Driver và Spring Data Neo4j

Metrics server không thay thế số đo **của lời gọi repository thật**. Một ví dụ đơn giản đo toàn bộ thao tác đọc có `executeRead`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderMonitor {
    private final Driver driver;

    public OrderMonitor(Driver driver) {
        this.driver = driver;
    }

    public List<String> findOrderIds(String customerId) {
        long startedAt = System.nanoTime();
        boolean success = false;
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {

            List<String> ids = session.executeRead(tx -> tx.run("""
                    MATCH (c:Customer {customerId: $customerId})
                          -[:PLACED]->(o:Order)
                    RETURN o.orderId AS id
                    ORDER BY id
                    """, Map.of("customerId", customerId))
                    .list(record -> record.get("id").asString()));

            success = true;
            return ids;
        } finally {
            long elapsedNanos = System.nanoTime() - startedAt;
            long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
            // Thay bằng Micrometer/OTel trong ứng dụng thực tế:
            System.out.printf("operation=findOrderIds,success=%s,elapsedMs=%d%n",
                    success, elapsedMillis);
        }
    }
}
~~~

Ví dụ **minh họa** cách đặt timer, không phải hệ thống giám sát production. Trong production, thay `System.out.printf` bằng hệ thống metrics có giới hạn cardinality và log phù hợp; không ghi `customerId` trực tiếp thành metric label (sẽ tạo cardinality rất cao và có thể chứa PII).

Những điều cần lưu ý:

1. `startedAt` trước khi mở session nên thời gian **bao gồm** lấy kết nối, quản lý transaction, thực thi query, đọc hết record và đóng session.
2. `executeRead` là **managed transaction**, nên các lần retry được driver thực hiện trong callback có thể làm **latency một request** tăng dù cuối cùng vẫn thành công.
3. `.list(...)` đọc hết dữ liệu trả về trong callback; chỉ gọi `tx.run(...)` rồi bỏ `Result` có thể đo sai phạm vi xử lý mong đợi.
4. Nếu dùng Spring Data Neo4j, hãy đo quanh **service/repository thật**, đồng thời log query được SDN thực thi để không bỏ sót truy vấn phụ, mapping relationship hoặc transaction khác.
5. Đặt timeout và retry budget phù hợp; **timeout client**, timeout kết nối và **transaction timeout** là các cơ chế khác nhau.

### Kết hợp trace và lỗi

Đoạn instrumentation production nên ghi **operation**, tên service, tên database, loại truy vấn read/write và **status thành công/thất bại**, có thể kèm exception class và mã Neo4j. Không để giá trị `queryText` hoặc `customerId` tùy ý trở thành label của time series; với query chi tiết, dùng trace/log có bảo vệ và ID tương quan.

Nếu sử dụng Micrometer/Prometheus, áp dụng histogram/buckets phù hợp với SLO. Khi muốn xem **query nào** chậm, log/trace có sampling tốt thường phù hợp hơn việc tạo một time series riêng cho từng chuỗi Cypher khác nhau.

## 12. Tìm gốc của một đợt tăng p99: quy trình có thứ tự

Giả sử p99 của `POST /orders` tăng từ khoảng 180 ms lên hơn 1.000 ms trong 15 phút. Để phân tích:

1. **Xác nhận ảnh hưởng:** biểu đồ p50/p95/p99, request arrival/completion rate, số request thất bại và các endpoint bị ảnh hưởng.
2. **Đối chiếu database và instance:** có đổi leader, deploy, migration index, import lớn hoặc mở rộng cluster đúng thời điểm không?
3. **Xem mức tải:** successful/failed queries/s, committed write tx/s, active read/write tx, Bolt connections, CPU, heap, GC, page-cache hit ratio.
4. **Tìm chờ khóa:** chạy `SHOW TRANSACTIONS` ở thời điểm bị chậm, xem `waitTime`, `currentQueryWaitTime`, `status` và `activeLockCount`.
5. **Phân loại lỗi:** theo dõi query failures, transaction rollbacks/terminated, deadlock code và lỗi service. Đừng coi tất cả rollback đều là deadlock.
6. **Chụp query thật:** từ query log/trace, ghi câu Cypher, tham số đã làm sạch, database và phiên bản ứng dụng.
7. **Phân tích kế hoạch:** thử `EXPLAIN`, `PROFILE` trên bản sao dữ liệu đại diện để đọc `Rows`, `DB Hits`, `Sort`, mở rộng relationship và index. `PROFILE` **có thực thi query** nên không dùng tùy tiện với câu ghi trên production.
8. **Đưa ra giả thuyết có thể kiểm chứng:** ví dụ lô import giữ khóa lâu trên `:Order`, hoặc truy vấn mở quá nhiều quan hệ khiến số hàng nhân lên.
9. **Chỉ thay một biến:** giảm batch size, ổn định thứ tự cập nhật, thêm index phù hợp hoặc viết lại query, sau đó đo lại trong điều kiện tương đương.
10. **Đối chiếu tính đúng đắn:** sau tối ưu vẫn phải trả đúng node, relationship, tổng tiền, thứ tự và số hàng yêu cầu.

### Bảng phân biệt các giả thuyết

| Quan sát đồng thời | Giả thuyết nên kiểm tra | Bước xác minh |
|---|---|---|
| Latency tăng, `waitTime` tăng, write tx nhiều | Khóa bị tranh chấp | `SHOW TRANSACTIONS`, query log và pattern cập nhật |
| Latency tăng, `DB Hits` và `Rows` tăng, lock wait thấp | Query plan hoặc cardinality bất lợi | `PROFILE`, index, quan hệ 1-nhiều |
| API latency tăng nhưng server query latency ổn | Pool wait, network, mapping, retry, service khác | Trace/metric Java Driver/SDN |
| Rollbacks tăng cùng deadlock errors | Deadlock/ghi đồng thời | Mã lỗi, thứ tự lock, kích thước tx |
| Throughput giảm, CPU/GC tăng, page-cache miss tăng | Bão hòa tài nguyên | Metrics heap, GC, page cache, disk và workload |
| `transaction.active` tăng nhưng không có lỗi | Query dài, import hoặc nhiều request | Đối chiếu throughput, latency, transaction snapshot |

## 13. Thiết kế dashboard và alert có ích

Dashboard nên tách rõ **mỗi database**, **mỗi server/cluster member** và **mỗi loại workload**. Bảng dưới đây là gợi ý bố cục:

| Panel | Dữ liệu | Vì sao cần |
|---|---|---|
| API latency p50/p95/p99 | Endpoint/service, rolling window | Đo tác động đến người dùng |
| API requests/s và error ratio | Số request thành công/thất bại | Phân biệt ít tải với bão hòa |
| Server query latency histogram | Successful query execution | Thấy chậm trong Neo4j |
| Query success/failure rate | Counter `db.query.execution.*` | Nhìn lỗi query riêng khỏi lỗi API |
| Transaction commit/rollback rate | Counter theo database | Thấy tải giao dịch và rollback |
| Active read/write transactions | Gauge theo database | Quan sát concurrency |
| Transaction chờ khóa | `SHOW TRANSACTIONS` định kỳ/sự kiện | Điều tra contention tại thời điểm cụ thể |
| Deadlock events | Mã lỗi hoặc metric phiên bản hỗ trợ | Cảnh báo tranh chấp khó |
| CPU/heap/GC/page-cache | System/DBMS metrics | Loại trừ nghẽn tài nguyên |
| Bolt/pool utilization | DBMS Bolt + ứng dụng | Nhận biết vấn đề kết nối |

### Đặt ngưỡng cảnh báo theo SLO, không theo số tùy ý

Ví dụ **chỉ mang tính giả định**: API đọc có SLO p95 dưới 200 ms; nếu p95 vượt mốc nhiều cửa sổ liên tiếp và tỷ lệ lỗi tăng, có thể phát cảnh báo mức cao hơn. Với rollback, mức nền của hệ thống import có thể khác hệ thống giao dịch tương tác, nên “`rollbacks > 0`” không phải cảnh báo mặc định tốt.

Chọn cảnh báo theo:

- **SLO** và tác động người dùng, không chỉ CPU/counter đơn lẻ.
- **Baseline của cùng loại workload** (read-heavy, write-heavy, batch import).
- **Cửa sổ đo đủ dài** để tránh nhiễu nhưng đủ nhanh để phản ứng.
- **Ngưỡng tuyệt đối + tỷ lệ**, ví dụ failure ratio tăng rõ khi đã có lưu lượng đủ lớn.
- **Liên kết nhiều tín hiệu**, như latency p95 cao **và** queue/lock wait tăng.
- **Ownership/runbook** rõ ai xử lý và kiểm tra gì trước tiên.

Đừng tạo alert từ percentile trong cửa sổ có quá ít request; một hoặc hai request chậm có thể làm p95 không đại diện cho tình trạng chung.

## 14. Thực hành quan sát trên graph nhỏ

Để tránh tạo tải hoặc khóa trong hệ thống thật, chạy thử trên **Neo4j riêng**. Khởi tạo node đơn hàng giả:

~~~cypher
CREATE CONSTRAINT mon_order_id_unique IF NOT EXISTS
FOR (o:MonOrder)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
UNWIND range(1, 100) AS n
MERGE (o:MonOrder {orderId: 'MON-' + toString(n)})
SET o.customerId = 'C' + toString(n % 10),
    o.totalAmount = 100000 + n * 1000,
    o.createdAt = date('2026-01-01') + duration({days: n % 30});
~~~

Đối với dữ liệu mẫu, đây là bài đo **truy vấn đọc**, không phải test cố ý gây deadlock:

~~~cypher
MATCH (o:MonOrder)
WHERE o.customerId = $customerId
RETURN o.orderId AS orderId,
       o.totalAmount AS amount,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId ASC
LIMIT 10;
~~~

Trên Neo4j Browser, đặt tham số bằng `:param customerId => 'C1'`. Để xem kế hoạch:

~~~cypher
PROFILE
MATCH (o:MonOrder)
WHERE o.customerId = $customerId
RETURN o.orderId AS orderId,
       o.totalAmount AS amount,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId ASC
LIMIT 10;
~~~

Kiểm tra `Rows`, `DB Hits`, `Sort`/`Top` và số bản ghi thực tế trước khi suy luận tối ưu. Có thể thử index phù hợp, **chỉ trên database thực hành**:

~~~cypher
CREATE RANGE INDEX mon_order_customer_created IF NOT EXISTS
FOR (o:MonOrder)
ON (o.customerId, o.createdAt);
~~~

Chờ index ở trạng thái `ONLINE`, chạy lại cùng query/tham số, đối chiếu kết quả và kế hoạch. Với chỉ 100 node, planner **có thể không chọn index**, bởi scan toàn bộ tập nhỏ có thể rẻ hơn; bài học là đọc dữ liệu đo, không ép kế hoạch phải thay đổi.

### Mô phỏng tranh chấp khóa có kiểm soát

Khi cần xem `waitTime` tăng, có thể tổ chức **hai transaction ghi đồng thời** trên **cùng một node kiểm thử** bằng hai session riêng, trong môi trường cô lập:

~~~cypher
// Chạy một lần, không dùng cùng label/id trong dữ liệu thật.
MERGE (a:MonAccount {accountId: 'A01'})
SET a.balance = 1000;
~~~

Tại session A, mở explicit transaction, cập nhật `A01` rồi **giữ transaction chưa commit** trong thời gian ngắn có kiểm soát; ở session B, bắt đầu transaction khác và thử cập nhật `A01`. Session B có thể phải chờ khóa. Trong một session quan sát thứ ba có quyền phù hợp, chạy `SHOW TRANSACTIONS` và xem `waitTime`/`currentQueryWaitTime`.

Không cần viết `sleep` lâu trong giao dịch và không dùng thao tác ghi production để chứng minh lock contention. Sau thử nghiệm, **commit hoặc rollback cả hai transaction** và đóng session, sau đó xác minh số dư theo kết quả đã chọn. Tránh tạo deadlock thật nếu bài chỉ cần quan sát thời gian chờ.

## 15. Bài tập kiểm tra hiểu biết

### Bài 1 — Tính queries/s và rollback rate

Trong 60 giây, `query.success` tăng từ 5.000 lên 5.900; `query.failure` tăng từ 200 lên 230. Cùng cửa sổ, `transaction.committed` tăng 450 và `transaction.rollbacks` tăng 30. Hãy tính:

1. Số query đã hoàn thành mỗi giây.
2. Query failure ratio.
3. Committed transactions/s và rolled-back transactions/s.
4. Có thể kết luận 30 rollback chính là 30 failed query không?

**Đáp án tham khảo:** `(900+30)/60 = 15,5 query/s`; `30/930 ≈ 3,23%`; `450/60 = 7,5 committed tx/s`; `30/60 = 0,5 rolled-back tx/s`. Không được kết luận 30 rollback trùng 30 failed query nếu không có dữ liệu tương quan từng transaction.

### Bài 2 — Vì sao p99 API cao mà server query bình thường?

API p99 tăng từ 120 ms lên 1.000 ms, nhưng histogram query execution phía server ít thay đổi. Nêu ít nhất bốn thứ cần kiểm tra.

**Đáp án tham khảo:** thời gian chờ connection pool, network/TLS/routing, số lần retry của driver, thời gian Java mapping/result consumption, hàng đợi HTTP và các dịch vụ ngoài. Cần trace theo request, không kết luận ngay Neo4j cần thêm index.

### Bài 3 — Đọc lock wait đúng nghĩa

Một transaction hiển thị `activeLockCount = 300`, `waitTime = 0s`; transaction khác có `activeLockCount = 2`, `waitTime = 8s`. Transaction nào chắc chắn đang chặn người khác?

**Đáp án:** Chưa có đủ chứng cứ để kết luận. Transaction thứ hai đã **tích lũy** 8 giây chờ khóa, nhưng có thể không còn đang chờ. Transaction thứ nhất giữ nhiều khóa nhưng chưa chắc chặn ai. Cần xem `status`, giao dịch liên quan, query log và nhiều lần lấy mẫu.

### Bài 4 — Lỗi query và rollback

Ứng dụng dùng `session.executeWrite`, khi deadlock driver retry và cuối cùng request thành công. Dashboard API ghi 0 lỗi, nhưng metric transaction rollback tăng. Có mâu thuẫn không?

**Đáp án:** Không. Các lần thử thất bại ở server có thể rollback, sau đó driver retry thành công và tầng API chỉ thấy kết quả cuối. Nên đo tách biệt **server rollback/error** và **request failure sau retry**.

### Bài 5 — Chọn hướng xử lý

Khi `POST /orders` chậm, `waitTime` tăng, write transactions active tăng và query log cho thấy nhiều thao tác cùng cập nhật một node tổng doanh thu. Bạn sẽ thay đổi gì trước?

**Đáp án gợi ý:** Kiểm tra mô hình **hot node**, rút ngắn transaction, giảm độ song song tranh chấp, tách/batch thao tác tổng hợp và ổn định thứ tự ghi. Chỉ thêm index sẽ không giải quyết việc nhiều transaction vẫn phải ghi cùng một node.

### Bài 6 — Bẫy với histogram

Một nhóm tính p95 toàn cluster bằng cách lấy `avg(p95_instance_1, p95_instance_2)`. Vì sao sai?

**Đáp án:** Percentile của các phân bố không cộng tuyến tính; mỗi instance có thể phục vụ lượng request khác nhau và histogram khác nhau. Cần hợp nhất bucket/distribution hợp lệ hoặc dữ liệu mẫu theo cùng định nghĩa thời gian/mẫu rồi mới tính quantile.

## 16. Tài liệu chính thức để đối chiếu

- [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Essential metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/essential/)
- [Metrics reference: query execution và transaction metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/)
- [Expose metrics: Prometheus/CSV/JMX/Graphite](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/expose/)
- [Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/)
- [Concurrent data access và deadlocks](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Logging và query log](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
- [Cypher query tuning với EXPLAIN/PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)

Các trang `current` được cập nhật theo release. Khi vận hành phiên bản Neo4j cũ hơn, đặc biệt Neo4j 5.x, hãy **đối chiếu tên metric, các trường hỗ trợ, tính năng Enterprise, giá trị cấu hình và khả năng xuất Prometheus** trước khi triển khai dashboard hoặc automation.

## 17. Ghi nhớ

- **Độ trễ có nhiều lớp:** API p95/p99, thời gian chờ driver/pool, server query latency và lock wait không phải cùng một số đo.
- **Thông lượng là tốc độ theo thời gian**, tính từ delta/rate của counter; `active transactions` là gauge về concurrency chứ không phải transactions/s.
- **`SHOW TRANSACTIONS` cho ảnh chụp trạng thái khóa:** `waitTime` là thời gian tích lũy chờ khóa; `activeLockCount` không tự chứng minh transaction đang chặn ai.
- **Query failure, transaction rollback, termination và deadlock là các khái niệm khác nhau**; driver retry có thể che lỗi tạm thời khỏi API nhưng vẫn để lại sự kiện ở server.
- **Kết hợp metrics, query log, Java Driver/SDN instrumentation và `PROFILE`** để xác định nguyên nhân thay vì tự suy từ một biểu đồ.
- **Cảnh báo theo SLO và baseline của workload**, đồng thời bảo vệ endpoint metrics, query log và tham số nhạy cảm trong quá trình quan sát.
