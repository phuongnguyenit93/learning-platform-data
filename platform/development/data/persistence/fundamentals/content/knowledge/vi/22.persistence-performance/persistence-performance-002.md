# Phân biệt nút thắt CPU, bộ nhớ, I/O, mạng và chờ khóa

Một API Java lấy danh sách đơn hàng bỗng tăng thời gian phản hồi từ 80 ms lên 2 giây. Nhóm phát triển thấy SQL “chạy chậm” và định tăng connection pool, thêm index hoặc nâng cấp máy chủ database. Nhưng nếu nguyên nhân thật là 30 request đang chờ **khóa hàng**, tăng pool có thể làm nhiều transaction cùng tranh chấp hơn. Nếu nguyên nhân là **100 câu SQL nhỏ** do ORM N+1, thêm index không giải quyết số vòng đi-về mạng. Nếu database đang phải đọc quá nhiều trang từ đĩa, tăng heap JVM lại không có tác dụng.

**Nút thắt hiệu năng** (*bottleneck*) là tài nguyên, hàng đợi hoặc phần việc đang giới hạn throughput hoặc làm tăng latency trong một điều kiện tải cụ thể. Trong persistence, cần phân biệt ít nhất năm nhóm: **CPU, bộ nhớ, I/O lưu trữ, mạng và chờ khóa**. Còn một nguồn chờ rất hay bị nhầm là **chờ mượn connection từ pool**.

Bài học thuộc chương **Hiệu năng** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ áp dụng tư duy đo lường cho Java/JDBC/ORM và PostgreSQL: chia nhỏ thời gian, đọc bằng chứng từ query plan và wait event, phân biệt concurrency với công việc thực, rồi chọn một thay đổi tối ưu có thể kiểm chứng mà không làm mất tính đúng đắn giao dịch hay độ bền dữ liệu.

## 1. Phân biệt “chạy chậm” với nguyên nhân gây chậm

Một request mất 2 giây **không có nghĩa CPU làm việc 2 giây**. Nó có thể dành phần lớn thời gian:

- Đợi một thread Java có thể chạy hoặc đợi garbage collector.
- Đợi connection trong pool.
- Gửi truy vấn qua mạng và đợi phản hồi.
- Đợi database lấy dữ liệu từ bộ nhớ hoặc đĩa.
- Đợi một transaction khác nhả khóa.
- Đọc từng hàng qua mạng rồi chuyển thành object Java.
- Gọi thêm nhiều truy vấn nhỏ liên tiếp.

Ba khái niệm cần tách:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Latency** | Một thao tác mất bao lâu từ đầu đến cuối? | p95 API = 1,8 s |
| **Throughput** | Hoàn thành bao nhiêu thao tác trong một đơn vị thời gian? | 350 request/giây |
| **Resource utilization / waiting** | Tài nguyên nào bận, ai đang chờ ai? | CPU DB 35%, 80 session đợi row lock |

Latency cao khi CPU thấp **không mâu thuẫn**: request có thể nằm trong hàng đợi pool, đợi lock, đợi network hoặc I/O. CPU cao cũng không tự chứng minh CPU là nguyên nhân duy nhất; một hệ thống có thể cùng lúc có CPU cao và hàng đợi khóa lớn.

Một bottleneck là **phụ thuộc workload**. Query A có thể bị CPU giới hạn khi dữ liệu nằm trong RAM, nhưng trở thành I/O-bound sau khi working set lớn hơn khả năng cache. Nhiều nguyên nhân có thể nối tiếp nhau: CPU chậm làm transaction kéo dài, từ đó các request khác đợi khóa lâu hơn.

## 2. Phân rã đường đi của một request persistence

Đối với Java API dùng JDBC, một bức tranh chẩn đoán cơ bản:

~~~mermaid
flowchart LR
    A[HTTP Request] --> B[Java worker / thread]
    B --> C[Chờ mượn connection]
    C --> D[JDBC driver + mạng]
    D --> E[DB: parse / plan / execute]
    E --> F[CPU / buffer / disk I-O / locks]
    F --> G[DB trả các hàng]
    G --> H[Network transfer + JDBC fetch]
    H --> I[Java map DTO / serialize JSON]
    I --> J[HTTP Response]
~~~

Để tìm nút thắt, nên đo những đoạn có ý nghĩa:

| Đoạn | Đồng hồ/metric hữu ích | Nếu cao, nên kiểm tra |
| --- | --- | --- |
| Xử lý trước truy vấn | Trace span của API, CPU/GC Java | Tính toán, serialize, contention, thread starvation |
| **Mượn connection** | Acquisition/await time của connection pool | Pool hết slot, connection leak, transaction giữ quá lâu |
| **Thực thi statement** | Driver timing + DB query statistics | SQL plan, wait events, I/O, CPU, lock |
| **Duyệt ResultSet** | Số hàng, byte dữ liệu, fetch duration | Nhiều row, network, fetch size, mapping |
| **Đóng transaction** | Commit duration, lock hold time | WAL/fsync, replication, contention, network |
| Xử lý sau truy vấn | Java CPU/allocation, JSON size | Mapping, object allocation, serialization |

**Không cộng máy móc** các metric lấy từ những hệ có đồng hồ/điểm đo khác nhau rồi giả định tổng khớp tuyệt đối. Ví dụ thời gian JDBC `executeQuery()` có thể chỉ bao gồm chặng nhận batch kết quả đầu, còn phần fetch các hàng sau nằm ở `ResultSet.next()` tùy driver. Thời gian database báo cáo cũng không nhất thiết gồm chờ pool ở phía Java hoặc serialize HTTP response.

### Phân biệt ba hàng đợi thường gặp

~~~text
Java request queue -> connection pool queue -> DB lock/I-O/CPU queues
~~~

Một request có thể đợi 700 ms trong pool **trước khi** database nhìn thấy câu SQL. Khi quan sát DB thấy query hoàn thành trong 20 ms, không thể kết luận người dùng chỉ chờ 20 ms. Ngược lại, pool acquisition 2 ms nhưng SQL span 1 s chưa nói rõ bên trong DB đang dùng CPU hay bị khóa.

## 3. Quy trình chẩn đoán: đo trước, đặt giả thuyết sau

Một quy trình thực tế có thể lặp lại:

1. **Xác định triệu chứng:** endpoint nào chậm, từ khi nào, trên tenant/kích thước dữ liệu nào, p50/p95/p99 thay đổi ra sao?
2. **Chốt điều kiện tải:** requests/giây, số request đồng thời, loại truy vấn, kích thước payload và tỷ lệ read/write.
3. **Chia nhỏ latency:** đo pool wait, JDBC execute/fetch, transaction duration, Java CPU/GC, thời gian DB thấy câu SQL.
4. **Đo ở nơi có nghi vấn:** CPU process, GC, heap/RSS, DB wait event, disk latency, network RTT/throughput, lock blockers.
5. **Đưa ra một giả thuyết kiểm chứng được:** “80% p99 do đợi khóa của transaction cập nhật cùng một hàng”.
6. **Thử một thay đổi có kiểm soát:** giảm transaction duration, sửa query, tăng selectivity của index hoặc giới hạn concurrency.
7. **So lại kết quả cùng điều kiện:** latency, throughput, CPU, lock wait, query plan, error rate và tính đúng đắn nghiệp vụ.

Ví dụ một giả thuyết có thể kiểm chứng:

> “API chậm vì thiếu index trên điều kiện lọc `tenant_id` và `created_at`; nếu thêm index phù hợp, query sẽ đọc ít buffer hơn, thời gian DB giảm và API p95 giảm trong cùng tải.”

Đây là **giả thuyết**, chưa phải kết luận. Nếu `EXPLAIN` cho thấy query chỉ mất 5 ms nhưng request đợi pool 900 ms, index mới khó giải quyết nút thắt.

Không tối ưu khi chưa có baseline. Tốc độ “cảm thấy nhanh hơn” trên máy dev không đủ để ra quyết định production.

## 4. Nút thắt CPU: xử lý tính toán thay vì chờ

**CPU-bound** nghĩa thời gian đáng kể dành cho tính toán trên CPU. Với persistence, cả **JVM** và **database process** đều có thể CPU-bound.

Ví dụ ở Java:

- Ánh xạ hàng triệu dòng thành object, chuyển đổi kiểu dữ liệu hoặc tính toán đắt trong vòng `ResultSet.next()`.
- Serialize JSON rất lớn, nén dữ liệu, mã hóa hoặc xử lý regex phức tạp.
- ORM tạo quá nhiều entity, dirty checking trên persistence context lớn.
- Garbage collection và allocation pressure khiến CPU tăng.

Ví dụ ở database:

- JOIN, sort, aggregate trên lượng hàng lớn.
- Predicate/biểu thức tính toán tốn CPU, nhiều phép so chuỗi/JSON.
- Truy vấn quét nhiều bản ghi trong bộ nhớ dù không cần đọc đĩa nhiều.
- Nhiều query nhỏ đồng thời gây parse/plan/execute overhead.

| Tín hiệu | Diễn giải thận trọng |
| --- | --- |
| CPU process Java liên tục cao, Java thread đang RUNNABLE và tiêu tốn CPU | Có thể phần xử lý ở JVM là bottleneck |
| CPU database liên tục cao, nhiều query đang thực thi không chủ yếu đợi lock/I/O | Có thể engine xử lý quá nhiều phép toán |
| p95 tăng mạnh khi request concurrency vượt một ngưỡng | Hàng đợi CPU hoặc contention có thể bắt đầu tăng |
| DB `shared_blks_hit` lớn và `shared_blks_read` nhỏ trong plan | Nhiều truy cập qua shared buffers; vẫn có thể tốn CPU |
| Đổi query để đọc ít hàng hơn giảm CPU và latency | Bằng chứng ủng hộ giả thuyết xử lý quá nhiều dữ liệu |

**Đừng đồng nhất `RUNNABLE` với đang chiếm CPU thực sự**: trạng thái thread Java có thể bao gồm những đoạn chờ hệ điều hành/native I/O tùy ngữ cảnh. Để xác nhận CPU, cần CPU profiling hoặc sampling; thread dump chỉ cho biết một lát cắt.

### Ví dụ query tốn CPU dù dữ liệu ở RAM

~~~sql
SELECT customer_id, COUNT(*), SUM(total_amount)
FROM orders
WHERE created_at >= :fromTime
GROUP BY customer_id
ORDER BY SUM(total_amount) DESC
LIMIT 100;
~~~

Nếu query phải xử lý hàng chục triệu dòng, sort/hash aggregate vẫn có thể tiêu tốn CPU lớn dù phần lớn buffer hit. Hướng xử lý có thể là lọc đúng nhu cầu, index phù hợp, lưu aggregate đã được cập nhật có kiểm soát hoặc thay đổi yêu cầu truy vấn. Không tự suy rằng “thấy `LIMIT 100` là chỉ xử lý 100 dòng”: database có thể phải xem rất nhiều dòng **trước khi** chọn được top 100.

## 5. Nút thắt bộ nhớ: JVM, database và hệ điều hành

**Memory pressure** không chỉ là “heap gần đầy”. Một ứng dụng có nhiều lớp bộ nhớ:

~~~text
Java process:
  heap (entity, DTO, collection, cache)
  metaspace, thread stacks, direct/native buffers

Database host:
  shared buffers / buffer cache
  per-query memory (sort, hash, aggregation ...)
  connection/process memory

Operating system:
  page cache và bộ nhớ của các tiến trình khác
~~~

Khi working set vượt dung lượng cache/heap khả dụng, hệ thống có thể gặp nhiều GC, allocation stalls, spill tạm ra đĩa, swap, thiếu RAM hệ điều hành hoặc OOM. Memory pressure vì thế **có thể biểu hiện thành CPU cao, I/O cao hoặc latency tăng**.

### Dấu hiệu trong JVM

| Quan sát | Khả năng | Công cụ/hướng kiểm tra |
| --- | --- | --- |
| Heap sử dụng tăng mãi sau GC | Có thể giữ object lâu, leak hoặc cache không giới hạn | Heap dump/retained object analysis |
| Allocation rate rất cao, GC xảy ra dày | Mapping/serialization tạo nhiều object tạm | Java Flight Recorder (JFR), allocation profiling, GC logs |
| Pause time tăng khi tải lớn | GC/heap pressure ảnh hưởng tail latency | GC pause histogram, p99 và CPU |
| RSS lớn hơn heap đáng kể | Native/direct memory, stacks, mappings, runtime overhead | Process metrics, Native Memory Tracking khi được bật |
| Service OOM trong lúc đọc kết quả | Load toàn bộ dữ liệu thay vì phân trang/streaming | Số row, page size, vòng đời persistence context |

Không tự “chữa” bằng tăng `-Xmx`. Heap lớn hơn có thể giúp nếu heap thực sự là giới hạn, nhưng cũng có thể làm giảm RAM cho OS page cache hoặc tăng khả năng memory contention với database đồng máy.

### Bộ nhớ trong database và spill

Ví dụ PostgreSQL có thể dùng RAM cho sort/hash. Nếu dữ liệu vượt ngân sách phù hợp, một số thao tác tạo **temporary files** và thực hiện I/O:

~~~text
EXPLAIN (ANALYZE, BUFFERS):
  Sort Method: external merge  Disk: 256000kB
  Buffers: temp read=..., written=...
~~~

Đây là dấu hiệu đáng kiểm tra, không phải chỉ dẫn luôn tăng `work_mem`. Tham số bộ nhớ query có thể được sử dụng **nhiều lần trong một plan, trên nhiều session song song**; tăng quá mạnh có nguy cơ làm cạn RAM khi concurrency cao.

**Phân biệt hết RAM với thiếu cache:** database có thể bị I/O cao vì working set lớn hơn OS/shared cache mà hệ thống chưa hề OOM. Giải pháp đôi khi là giảm dữ liệu đọc, thay index/query, phân vùng hoặc giảm số truy vấn, không nhất thiết tăng memory limit.

## 6. Nút thắt I/O lưu trữ: đọc/ghi đĩa, WAL và fsync

**Storage I/O-bound** xảy ra khi thời gian chờ đọc/ghi dữ liệu hoặc nhật ký giao dịch là yếu tố giới hạn. Trong database, hoạt động I/O bao gồm:

- Đọc data/index pages không sẵn trong bộ đệm.
- Ghi dirty pages, checkpoint và nền lưu trữ.
- Ghi transaction log như PostgreSQL WAL.
- Đồng bộ bền vững (`fsync` và cơ chế tương ứng).
- Ghi/đọc temporary files do sort/hash không đủ bộ nhớ.
- I/O sao lưu, replication hoặc maintenance cạnh tranh cùng thiết bị.

Một SQL query có thể chậm sau khi restart vì cache lạnh, nhưng nhanh trở lại khi pages được cache. Ngược lại, query có pattern đọc quá nhiều blocks có thể luôn tốn I/O dưới tải.

### Các số đo nên xem cùng nhau

| Metric | Gợi ý | Vì sao một metric chưa đủ |
| --- | --- | --- |
| Device read/write latency, queue depth | Thiết bị lưu trữ đang bận/chờ | I/O latency còn phụ thuộc host, cloud tier và tải khác |
| IOPS/throughput | Cường độ read/write | IOPS cao không tự chứng minh đã chạm giới hạn |
| DB wait event loại I/O | Backend đang chờ thao tác I/O được ghi nhận | Wait event là snapshot; cần xem tỷ lệ theo thời gian |
| `EXPLAIN ... BUFFERS` shared read/hit | Plan động chạm bao nhiêu trang | Shared read không đồng nhất với physical disk read |
| Temporary block read/written | Có thể có spill do sort/hash | Cần xem plan node, `work_mem` và row count |
| WAL bytes/write/sync latency | Tải và độ trễ commit liên quan WAL | Commit còn phụ thuộc locks, replica, CPU và network |

Trong PostgreSQL, `shared_blks_read` hoặc `Buffers: shared read` phản ánh blocks được lấy vào shared buffers khi chưa có sẵn tại đó. **Các lần đọc này vẫn có thể được phục vụ từ OS page cache**, nên không thể coi chúng trực tiếp là số physical disk reads.

Ví dụ tạo index phù hợp có thể giảm số pages cần quét; nhưng thêm quá nhiều index lại **tăng I/O ghi** và chi phí vacuum/maintenance. Cần đo trade-off read–write.

### Vì sao commit chậm dù UPDATE nhanh?

Lệnh `UPDATE` có thể chạy nhanh nhưng `COMMIT` phải chờ WAL durability hoặc acknowledgement theo cấu hình hệ thống. Nếu đồng thời có replication, checkpoint hoặc storage latency tăng, transaction duration kéo dài. Ứng dụng phải phân biệt **thời gian SQL statement** với **thời gian commit**; không nên chỉ đo đến `executeUpdate()` rồi kết luận ghi đã hoàn tất.

## 7. Nút thắt mạng: độ trễ và số lần đi-về

Một request truy cập database qua mạng có ít nhất hai yếu tố:

1. **Latency/RTT**: thời gian một vòng giao tiếp.
2. **Bandwidth và payload size**: thời gian chuyển lượng dữ liệu qua mạng, cùng overhead protocol/driver.

Hãy xét một service mà RTT giữa Java và database khoảng 8 ms. Nếu code thực hiện **100 query tuần tự** và mỗi query cần ít nhất một vòng trao đổi, riêng network latency đã có thể đóng góp cỡ 800 ms, chưa tính database xử lý và các vòng trao đổi bổ sung. Đây là tính toán minh họa; số round trip thật phụ thuộc driver/protocol, pipeline, prepared statement và cách fetch.

~~~mermaid
sequenceDiagram
    participant J as Java Service
    participant DB as Database
    loop 100 đơn hàng
        J->>DB: SELECT lines WHERE order_id = ?
        DB-->>J: ResultSet
    end
    Note over J,DB: N+1: nhiều vòng đi-về nối tiếp
~~~

**Network-bound** có thể xảy ra ngay cả khi SQL ở DB dùng CPU rất ít:

- ORM N+1 phát nhiều statement thay vì query theo tập ID.
- Fetch size nhỏ khiến `ResultSet.next()` kích hoạt nhiều lượt lấy batch.
- Response trả quá nhiều cột/row, truyền payload lớn.
- Service và database nằm khác vùng/region, latency và jitter tăng.
- TLS handshake, DNS, connection establishment lặp lại vì tạo connection mới thay vì dùng pool.
- Packet loss hoặc băng thông bị giới hạn làm tăng thời gian truyền.

### Nhận diện network-bound

Nếu DB báo thời gian xử lý mỗi SQL 2 ms nhưng JDBC span thường dài 20 ms, cần kiểm tra **pool wait, fetch/mapping và round trips** trước khi kết luận do mạng. Độ chênh này không phải một phép đo network thuần: driver deserialize, scheduler và thời gian Java cũng nằm trong đó.

Thử nghiệm có kiểm soát có thể so sánh:

- Truy vấn từ Java application host và từ một host gần database, cùng payload.
- Số SQL statements và số hàng/byte trả về trên một request.
- Latency theo số lần round trip và page/fetch size.
- Connection acquisition và số lần mở mới.

Đừng giảm bảo mật TLS hoặc chuyển database sang host không phù hợp chỉ để giảm một phép đo mạng. Chọn mạng và topology phải xét thêm độ bền, HA, quyền truy cập và chi phí.

## 8. Chờ khóa: đang đợi transaction khác, không phải tính toán

Một transaction có thể chờ **row lock, table lock hoặc loại lock khác** mà không dùng nhiều CPU. Ví dụ:

~~~sql
-- Transaction A:
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 42;
-- A chưa COMMIT hoặc ROLLBACK.

-- Transaction B, connection khác:
BEGIN;
UPDATE accounts SET balance = balance + 50 WHERE id = 42;
-- B có thể phải chờ khóa mà A đang giữ.
~~~

Nếu A giữ transaction trong vài giây vì gọi HTTP trước khi commit, B có thể chậm vài giây dù bản thân SQL `UPDATE` chỉ mất vài mili giây CPU khi được chạy.

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as Database
    participant B as Transaction B
    A->>DB: UPDATE accounts id=42
    DB-->>A: Row cập nhật, lock giữ đến cuối transaction
    B->>DB: UPDATE accounts id=42
    Note over B,DB: B chờ khóa
    A->>DB: COMMIT
    DB-->>B: B tiếp tục UPDATE
    B->>DB: COMMIT
~~~

**Lock wait khác deadlock.** Một chuỗi chờ có thể tự kết thúc khi transaction giữ khóa commit. **Deadlock** là chu trình chờ nhau; DB thường phát hiện và hủy một transaction để phá chu trình. Số deadlock thấp không chứng minh không có lock contention: nhiều yêu cầu vẫn có thể chờ khóa rất lâu mà không tạo chu trình.

### Dấu hiệu khóa

- PostgreSQL `pg_stat_activity.wait_event_type = 'Lock'` tại thời điểm lấy mẫu.
- `pg_blocking_pids(pid)` trả các PID đang chặn backend (có ngữ nghĩa theo engine).
- Transaction `idle in transaction` giữ trạng thái/khóa qua thời gian không chạy SQL.
- p99 tăng khi nhiều request cùng sửa một account, inventory row hoặc sequence of resources.
- Khi giảm thời gian transaction hoặc tránh hot row, throughput tăng và lock wait giảm.

**Không phải mọi trường hợp `wait_event_type` khác null đều là row lock.** PostgreSQL còn có các loại wait như `LWLock` (đồng bộ nội bộ), `IO`, `Client`, `BufferPin`, v.v. Phải đọc đúng loại và event trước khi kết luận.

## 9. Chờ connection pool không phải chờ khóa database

Một connection pool chỉ cho mượn số kết nối tối đa đã cấu hình. Nếu tất cả đang được giữ, thread mới phải **chờ pool**, ngay cả khi database CPU còn rất thấp.

Ví dụ pool có 20 connection:

~~~text
20 request đầu đã mượn connection.
  5 đang chạy SQL.
  5 đang chờ lock.
 10 đang chờ HTTP khác nhưng vẫn giữ transaction/connection.

Request thứ 21: chờ tại getConnection().
Database không biết request thứ 21 đang đợi.
~~~

Một lỗi phổ biến là tăng pool từ 20 lên 100 để giảm chờ. Nếu 80 kết nối mới cùng lao vào một hot row lock, DB chịu nhiều session và context hơn trong khi throughput thực tế có thể không tăng.

| Đo lường | Cần phân biệt |
| --- | --- |
| `active connections` của pool | Số connection đang được mượn, không phải số query đang dùng CPU |
| `idle connections` | Kết nối vật lý sẵn trong pool |
| `pending/awaiting connections` | Request đang chờ mượn connection |
| `connection acquisition time` | Chi phí từ lúc xin đến lúc lấy được connection |
| `connection usage/hold time` | Thời gian một request giữ connection |
| `db sessions` | Session đang kết nối; có thể active, idle hoặc đang chờ |

Khắc phục cần xác định **ai giữ connection quá lâu**: thiếu `close()`, transaction kéo dài, mở connection trước khi làm việc ngoài DB, stream ResultSet lâu hay query/lock thực sự chậm. Với JDBC tự quản lý, dùng `try-with-resources` để trả connection đúng phạm vi. Với Spring, không tự đóng connection do transaction manager quản lý.

## 10. Công thức hàng đợi: vì sao p99 có thể bùng lên?

Một hệ gần giới hạn công suất thường có **hàng đợi tăng phi tuyến** khi lưu lượng tiến sát khả năng xử lý. Tốc độ query trung bình 10 ms không chứng minh latency còn 10 ms khi có nhiều request đến cùng lúc.

**Định luật Little** ở trạng thái ổn định:

\[
L = \lambda W
\]

Trong đó:

- `L`: số công việc trung bình **đang ở trong hệ** (bao gồm chạy và chờ).
- `\lambda`: throughput trung bình (công việc/giây).
- `W`: thời gian trung bình một công việc ở trong hệ (giây).

Ví dụ một endpoint hoàn thành 200 request/giây với thời gian trung bình 0,2 giây, thì có khoảng `L = 200 × 0,2 = 40` request trung bình đang được xử lý hoặc chờ trong **phạm vi hệ được đo**. Con số 40 **không phải** khuyến nghị đặt pool size 40: một request có thể giữ connection trong một phần rất nhỏ thời gian 0,2 giây; hệ có nhiều hàng đợi ở các tầng khác nhau.

Các giả định ổn định, cùng phạm vi và tính theo trung bình rất quan trọng. Không dùng công thức với p99 thay cho trung bình rồi tính pool size. Muốn sizing pool phải đo **thời gian thật giữ connection, số query đồng thời, DB capacity và đòi hỏi throughput**.

## 11. Dùng PostgreSQL để phân biệt đang chờ gì

Nếu hệ dùng PostgreSQL, `pg_stat_activity` cho biết trạng thái và wait event của các backend **tại thời điểm truy vấn**. Ví dụ chỉ đọc:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    NOW() - xact_start AS transaction_age,
    NOW() - query_start AS query_age,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY query_start NULLS LAST
LIMIT 50;
~~~

Lưu ý:

- Truy cập chi tiết session khác có thể bị giới hạn bởi quyền; cần quyền giám sát phù hợp.
- `query_age` tính từ `query_start` không nhất thiết là “thời gian SQL hiện tại đang sử dụng CPU”; với session idle, query text/time có thể liên quan lệnh trước đó. Luôn đọc cùng `state`.
- `state='active'` có thể đang thực thi **hoặc đang chờ wait event**.
- `state='idle in transaction'` nghĩa transaction còn mở; có thể giữ khóa/snapshot dù không chạy SQL.
- `pg_blocking_pids(pid)` hữu ích khi phân tích lock, nhưng không thể thay thế hiểu biết về loại lock và transaction.
- Truy vấn này là **snapshot**, các wait có thể thay đổi ngay sau khi lấy mẫu. Nên kết hợp sampling/metrics theo thời gian.

### Nhìn tỷ lệ session theo wait

~~~sql
SELECT
    state,
    COALESCE(wait_event_type, 'CPU/khác/không-chờ') AS wait_category,
    COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type
ORDER BY sessions DESC;
~~~

Nhãn `CPU/khác/không-chờ` chỉ có nghĩa **không quan sát được wait event ở snapshot**, **không** khẳng định session đang sử dụng CPU. Có thể đang được OS lên lịch, đang xử lý trong engine hoặc đang ở trạng thái khác.

### Truy vấn thấy blocker

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.wait_event_type,
    blocked.wait_event,
    blocker.pid AS blocker_pid,
    blocker.state AS blocker_state,
    NOW() - blocker.xact_start AS blocker_xact_age
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    UNNEST(pg_blocking_pids(blocked.pid)) AS blocking(blocker_pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = blocking.blocker_pid
WHERE blocked.datname = current_database()
ORDER BY blocker.xact_start NULLS LAST;
~~~

Đây là công cụ **chẩn đoán**, không phải hướng dẫn tự động `pg_terminate_backend` ở production. Trước khi hủy transaction phải xác định tác động nghiệp vụ, quyền và phương án khôi phục. Một PID đang chặn nhiều session có thể là transaction quan trọng.

## 12. Đọc `EXPLAIN (ANALYZE, BUFFERS)` mà không suy diễn quá mức

Với một câu `SELECT`, kiểm tra query plan và thời gian thực thi:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT id, total_amount
FROM orders
WHERE tenant_id = 501
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
ORDER BY created_at DESC, id DESC
LIMIT 100;
~~~

Những thông tin quan trọng:

| Dòng trong plan | Ý nghĩa | Gợi ý kiểm tra |
| --- | --- | --- |
| `Seq Scan` | Quét tuần tự; **không mặc định xấu** | Số hàng, tỷ lệ chọn lọc, bảng lớn/nhỏ |
| `Index Scan` / `Index Only Scan` | Dùng index, có thể vẫn cần heap fetch | Index keys, ordering, visibility map, heap fetches |
| `actual rows` so với `rows` ước lượng | Sai lệch thống kê hoặc predicate/selectivity | `ANALYZE` stats, correlation, data skew |
| `loops` | Một node bị lặp bao nhiêu lần | N+1 trong plan/nested-loop, nhân row-count |
| `Sort Method` / `Disk` | Sort trong RAM hay spill ra disk | Query/index/order, work memory |
| `Buffers: shared hit/read` | Truy cập buffer có sẵn hay phải nạp vào shared buffers | Tập dữ liệu chạm tới, chưa phải physical I/O trực tiếp |
| `temp read/written` | Tệp tạm từ những thao tác cần spill | Aggregate/sort/hash và kích thước dữ liệu |
| `Execution Time` | Thời gian server thực thi có instrumentation | Không bao gồm toàn bộ Java pool/network/HTTP |

**`EXPLAIN ANALYZE` thực thi câu SQL thật.** Với `INSERT`, `UPDATE`, `DELETE`, nó có thể thay đổi dữ liệu; không chạy trên production nếu không hiểu tác động. Khi cần thử câu DML trong một môi trường thích hợp, có thể bọc transaction và `ROLLBACK`, nhưng điều đó vẫn gây khóa, I/O, trigger và có thể có side effect ngoài database không rollback được. Đối với workload nhạy cảm, ưu tiên bản sao/môi trường test hoặc dùng `EXPLAIN` không `ANALYZE`.

Một plan trên database nhỏ của máy dev không đại diện chắc chắn cho production. Kích thước bảng, dữ liệu lệch, statistics, parameter values, cache nóng/lạnh và concurrency đều ảnh hưởng. Cũng cần nhớ chi phí đo đạc `EXPLAIN ANALYZE` có overhead.

### Khi muốn nhìn I/O timing

PostgreSQL có các metric I/O chuyên biệt và có thể cho biết thời gian read/write trong plan khi cấu hình thống kê I/O timing phù hợp (ví dụ `track_io_timing` được bật). Các thống kê I/O ở mức hệ thống và view như `pg_stat_io` còn phụ thuộc **phiên bản PostgreSQL**. Không dùng một truy vấn chỉ dành cho bản mới rồi giả định bản cũ có cùng cột/view.

## 13. Thống kê workload thay vì chỉ nhìn một query

Một query tự nó nhanh nhưng bị gọi hàng nghìn lần trên mỗi giây cũng có thể chiếm phần lớn tài nguyên. Nếu PostgreSQL được cấu hình extension `pg_stat_statements` và quyền truy cập phù hợp, có thể lấy cái nhìn tổng hợp:

~~~sql
SELECT
    queryid,
    calls,
    ROUND(total_exec_time::numeric, 2) AS total_exec_ms,
    ROUND(mean_exec_time::numeric, 2) AS mean_exec_ms,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

`pg_stat_statements` cần được cài đặt và bật phù hợp; cột có thể khác theo phiên bản. Đây không phải view luôn có sẵn trong mọi database. Query được tổng hợp theo fingerprint/nội dung chuẩn hóa; một số tham số cụ thể có thể tạo plan và latency khác nhau.

Nhìn **total time, calls, mean, rows và blocks** cùng nhau:

- Query A trung bình 100 ms, gọi 2 lần/phút → có thể không phải nguồn tải lớn.
- Query B trung bình 3 ms, gọi 20.000 lần/phút → có thể tiêu tốn tổng tài nguyên nhiều hơn.
- Query C chỉ chậm khi tham số trả về nhiều hàng → cần xem data skew, plan và access pattern.

Các counter cộng dồn cần xét khoảng lấy mẫu và thời điểm reset. **Không lấy total từ đầu tháng so trực tiếp với p95 của 5 phút gần nhất** để kết luận nguyên nhân sự cố vừa xảy ra.

## 14. Đo phía Java: tách pool, execute, fetch và close

Một repository có thể đo thời gian theo từng chặng mà không log nội dung nhạy cảm:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class OrderReader {
    private final DataSource dataSource;

    public OrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findStatus(long orderId) throws SQLException {
        long started = System.nanoTime();
        long acquired = -1;
        long executeStarted = -1;
        long executeReturned = -1;
        long consumed = -1;

        try (Connection connection = dataSource.getConnection()) {
            acquired = System.nanoTime();
            try (PreparedStatement statement =
                         connection.prepareStatement(
                                 "SELECT status FROM orders WHERE id = ?")) {
                statement.setLong(1, orderId);
                executeStarted = System.nanoTime();
                try (ResultSet rs = statement.executeQuery()) {
                    executeReturned = System.nanoTime();
                    Optional<String> status = rs.next()
                            ? Optional.ofNullable(rs.getString("status"))
                            : Optional.empty();
                    consumed = System.nanoTime();
                    return status;
                }
            }
        } finally {
            long ended = System.nanoTime();
            // Demo log; production nên dùng histogram/metrics/tracing.
            if (acquired > 0) {
                System.out.printf(
                        "poolWaitMs=%.3f%n",
                        millis(acquired - started));
            }
            if (executeStarted > 0 && executeReturned > 0) {
                System.out.printf(
                        "executeCallMs=%.3f%n",
                        millis(executeReturned - executeStarted));
            }
            if (executeReturned > 0 && consumed > 0) {
                System.out.printf(
                        "consumeMs=%.3f%n",
                        millis(consumed - executeReturned));
            }
            System.out.printf("totalWithCloseMs=%.3f%n",
                    millis(ended - started));
        }
    }

    private static double millis(long nanos) {
        return nanos / 1_000_000.0;
    }
}
~~~

**Cách hiểu đúng:**

- `poolWaitMs` đo đến khi `getConnection()` trả về: có thể gồm chờ pool **và cả công việc tạo/kiểm tra connection**, không phải metric chờ hàng đợi thuần của pool.
- `executeCallMs` là thời gian lời gọi driver trả về, **không đảm bảo** đã fetch hết tất cả rows hay chỉ là server execution time.
- `consumeMs` gồm fetch bổ sung, giải mã và Java mapping trong vòng đọc.
- `totalWithCloseMs` còn gồm preparation, dọn dẹp, resource closing và overhead Java; các số trên **không tạo thành bảng phân bổ toàn bộ thời gian không chồng lấn** nếu không đo thêm những đoạn còn lại.
- Nếu lỗi xảy ra trước khi đồng hồ một đoạn được gán, đoạn đó không có số; không ghi thời gian âm như một kết quả hợp lệ.

Trong sản xuất, hãy ghi **histogram** và trace span theo loại operation, số rows và trạng thái thành công/lỗi, nhưng không dùng `orderId`, SQL parameters hoặc dữ liệu cá nhân làm metric label cardinality cao. Logging từng request bằng `System.out.printf` là mã minh họa; tải logging lớn có thể trở thành bottleneck mới.

### Với ORM/JPA

Nên đo số câu SQL trên mỗi request và tìm N+1, lazy-load ngoài dự kiến, dirty checking, flush/commit duration và kích thước persistence context. `repository.findById()` chạy nhanh chưa chắc là toàn bộ chi phí: khi serialize một entity có association lazy, framework có thể phát thêm query hoặc ném lỗi ngoài transaction.

## 15. Ma trận chẩn đoán nhanh năm nhóm nút thắt

| Nút thắt nghi vấn | Dấu hiệu mạnh hơn | Dấu hiệu dễ gây nhầm | Thử nghiệm phân biệt |
| --- | --- | --- | --- |
| **CPU** | CPU process cao, profiler chỉ rõ method/node tốn CPU, hàng đợi tăng theo tải | Chỉ thấy thread RUNNABLE | Giảm row count/algorithm cost, đo CPU time và throughput |
| **Bộ nhớ** | GC/allocation cao, heap/RSS pressure, DB temp spill, cache miss tăng | Chỉ nhìn free memory nhỏ | Profile allocation, đo temp files, hạn chế materialization |
| **Storage I/O** | Storage read/write latency cao, DB I/O waits, plan đọc nhiều pages/temp | Chỉ thấy shared read cao | Đo thiết bị + buffers + cold/warm behavior |
| **Mạng** | RTT/loss/throughput, nhiều vòng JDBC, payload lớn | JDBC elapsed lớn hơn DB elapsed | Đếm round trips, bytes, compare network paths |
| **Chờ khóa** | Lock wait event, blocker, long transaction, hot row | CPU DB thấp hoặc `UPDATE` chậm | Đo wait/block chain, kết thúc transaction ngắn hơn |

**Connection pool wait** nên được theo dõi riêng: nó là **hàng đợi trước database** và có thể bắt nguồn từ bất kỳ một trong năm nhóm, connection leak hoặc cấu hình pool/concurrency không phù hợp.

Không được biến ma trận thành quy tắc “một metric = một nguyên nhân”. Ví dụ cùng lúc có bộ nhớ DB thiếu, sort spill và I/O waits; phải chỉ rõ **cơ chế nhân quả** trước khi đổi cấu hình.

## 16. Tình huống 1: p99 cao nhưng CPU DB thấp

Một API cập nhật số dư có:

~~~text
API p99:                  2.4 s
JDBC connection acquire:  6 ms
SQL UPDATE duration:      2.3 s
DB CPU usage:             25%
pg_stat_activity:         nhiều session wait_event_type = Lock
Blocker:                  transaction idle in transaction 2.1 s
~~~

**Giả thuyết chính:** câu `UPDATE` đợi một transaction khác giữ khóa. Tăng CPU hoặc thêm RAM khó giải quyết. Hướng xử lý:

1. Xác định transaction đang chặn, use case nào mở và giữ nó.
2. Tránh gọi HTTP, gửi email hoặc chờ người dùng **khi transaction đang mở**.
3. Rút ngắn critical section, đặt thứ tự cập nhật nhiều hàng nhất quán để giảm deadlock.
4. Kiểm tra index cho điều kiện `UPDATE` để hạn chế thời gian tìm và phạm vi thao tác cần thiết.
5. Định nghĩa lock timeout và retry transaction **có giới hạn, an toàn về idempotency** nếu nghiệp vụ cho phép.

**Không** tự tăng pool từ 20 lên 200 vì nhiều request đang chờ lock; điều đó có thể tăng cạnh tranh. **Không** tự động terminate blocker ở production khi chưa xác định tính an toàn nghiệp vụ.

## 17. Tình huống 2: DB CPU cao, query có index nhưng vẫn chậm

Hệ thống báo cáo truy vấn:

~~~text
DB CPU:           thường xuyên 90-100%
Shared buffer hit: rất cao
Shared read:      thấp
Query calls:      35.000/phút
Rows fetched:     1.500.000/phút
DB Lock waits:    hiếm
~~~

Truy vấn có thể đang tốn CPU vì **gọi quá nhiều lần** hoặc xử lý nhiều hàng/biểu thức. Cần kết hợp:

- `pg_stat_statements` xem total_exec_time/calls, không chỉ query chậm nhất.
- `EXPLAIN` xem rows, loops, filter và sort.
- Java tracing xem một request phát bao nhiêu SQL.
- CPU profiling DB/Java phù hợp môi trường.

Ví dụ ORM N+1:

~~~java
List<Order> orders = orderRepository.findRecentOrders(100);
for (Order order : orders) {
    // Có thể kích hoạt truy vấn riêng khi lazy association chưa load.
    int lineCount = order.getLines().size();
    summarize(order, lineCount);
}
~~~

Nếu phát 1 query lấy orders và 100 query lấy order lines, hiệu năng có thể bị cả **CPU overhead tại DB** và **network round trips**. Giải pháp có thể là fetch theo tập ID, query projection hoặc batching phù hợp; không vội bật eager load toàn bộ association vì có thể sinh **cartesian product** và trả dữ liệu rất lớn.

## 18. Tình huống 3: Heap cao, disk/temp I/O cao và throughput giảm

Một endpoint export xử lý 200.000 bản ghi:

~~~text
Java heap:       tăng mạnh mỗi lần export
GC pauses:       dày khi có nhiều request
DB EXPLAIN:      Sort Method: external merge
DB temp writes:  tăng trong thời gian export
HTTP response:   hàng chục MB
~~~

Đây có thể là **nhiều bottleneck liên quan nhau**:

1. Query sort quá nhiều dữ liệu, dùng temp disk.
2. JDBC/materialization tải nhiều hàng vào heap.
3. JSON/CSV serialization và network transfer lớn.

Hướng xử lý:

- Dùng phân trang/keyset hoặc xử lý theo batch có giới hạn.
- Giảm cột/row, tránh `SELECT *` khi export chỉ cần vài trường.
- Dùng stream với backpressure và **quản lý vòng đời ResultSet/transaction**, không giữ connection vô hạn.
- Xem xét index hỗ trợ `ORDER BY` và filter nếu phù hợp.
- Nếu thật sự cần điều chỉnh memory cho sort, đo đồng thời workload/concurrency trước khi đổi `work_mem`.
- Với export lớn, cân nhắc job bất đồng bộ tạo file và object storage, tách khỏi request đồng bộ dài.

Chỉ tăng `-Xmx` không sửa query spill; chỉ tăng `work_mem` cũng không sửa Java đang giữ toàn bộ 200.000 entity.

## 19. Tối ưu có thứ tự và không đánh đổi tính đúng đắn

Nhiều cách “làm nhanh” vô tình phá transaction hoặc dữ liệu:

| Ý tưởng tối ưu | Lợi ích tiềm năng | Cần cảnh giác |
| --- | --- | --- |
| Thêm index đúng predicate/order | Ít block đọc, nhanh tìm hàng | Chi phí ghi, dung lượng, index maintenance |
| Dùng projection thay vì full entity | Ít network/heap, ít mapping | Bảo đảm trường trả đúng nhu cầu |
| Batch nhiều câu INSERT/UPDATE | Giảm round trips và overhead | Giới hạn transaction, rollback, constraint, idempotency |
| Rút ngắn transaction | Giảm lock hold time và pool usage | Phải giữ cùng transaction những cập nhật thuộc bất biến |
| Tăng pool size | Có thể phục vụ nhiều yêu cầu đồng thời | Nếu DB đã giới hạn CPU/lock/I/O, có thể tệ hơn |
| Tăng bộ nhớ DB/JVM | Giảm cache miss/spill hoặc GC trong một số trường hợp | OOM, mất OS page cache, contention |
| Cache kết quả đọc | Giảm query repeat | Staleness, invalidation, tenant isolation |
| Dùng read replica | Tách tải đọc | Replication lag, read-your-writes, query consistency |
| Retry query lỗi | Phục hồi lỗi tạm | Retry storm, transaction outcome chưa rõ, duplicate side effect |
| Giảm isolation hoặc bỏ constraint | Có thể giảm chờ trong vài trường hợp | **Có thể phá bất biến nghiệp vụ**, không là tối ưu mặc định |

Đặc biệt, không dùng `NOLOCK`-style dirty reads, giảm isolation tùy tiện hoặc tắt durability chỉ để “qua bài benchmark”. Nếu mục tiêu là quản lý tiền, đơn hàng, tồn kho hay idempotency, hiệu năng phải được đánh giá **cùng tính đúng đắn**.

Sau mỗi thay đổi, đo cả throughput, p95/p99, errors, DB utilization, lock wait, pool acquisition và dấu hiệu dữ liệu bị sai. Một cải thiện local có thể đẩy bottleneck sang tầng khác.

## 20. Thiết kế load test có thể phân biệt nguyên nhân

Một bài load test hữu ích phải có điều kiện kiểm soát:

1. **Dữ liệu đại diện:** kích thước, phân bố khóa nóng, số tenant, index, phân vùng, cache nóng/lạnh.
2. **Workload đại diện:** tỷ lệ đọc/ghi, số hàng trả, những thao tác dài, transaction và batch.
3. **Mức tải tăng dần:** đo nhiều điểm concurrency/arrival rate, xác định knee của latency.
4. **Công cụ quan sát trước khi chạy:** JVM GC/CPU, pool, DB CPU, I/O, wait events, network và tracing.
5. **So sánh thay đổi một yếu tố:** giữ tương đương data/cache/concurrency khi thử query/index/pool khác nhau.
6. **Kiểm tra correctness:** tổng tiền, số tồn kho, duplicate, missing event, commit/rollback, không chỉ HTTP 200.
7. **Warmup và ghi nhận trạng thái:** JIT, connection pool, page cache và thống kê DB ảnh hưởng kết quả.

### Closed-loop so với open-loop

- **Closed-loop:** client chờ response rồi mới gửi request tiếp theo. Khi server chậm, tải gửi cũng có thể giảm; cần tránh **coordinated omission** làm thiếu những lần chờ dài trong thống kê.
- **Open-loop:** phát request theo arrival rate định trước. Tốt để kiểm tra hàng đợi/overload nhưng phải giới hạn để không gây sự cố ngoài ý muốn.

Không áp dụng stress test phá hủy trên production nếu chưa có kế hoạch kiểm soát và phê duyệt. Với workload quan trọng, hãy dùng môi trường dữ liệu được ẩn danh và mô phỏng điều kiện tài nguyên gần thực tế.

### Đọc p95 và p99

Nếu p50 vẫn 70 ms nhưng p99 tăng lên 3 giây, có thể một số request bị chờ khóa, GC pause, network jitter hoặc pool queue — **trung bình** sẽ che vấn đề. Nên phân nhóm latency theo operation, endpoint, DB instance, kích thước response, tenant tier và thời điểm; không tạo metric label chứa user ID hoặc SQL parameter nhạy cảm.

## 21. Những sai lầm thường gặp

| Sai lầm | Vì sao dễ sai | Cách sửa |
| --- | --- | --- |
| Thấy SQL chậm thì thêm index ngay | Có thể đang chờ pool/lock/network | Chia latency và đọc plan/wait event trước |
| Thấy DB CPU thấp thì kết luận DB khỏe | Session có thể chờ lock/I/O hoặc nghẽn throughput | Đo waits, pool và storage |
| Coi `shared_blks_read` là physical disk reads | OS page cache có thể đáp ứng | Kết hợp I/O device và DB stats |
| Thấy thread RUNNABLE thì chắc chắn CPU-bound | Thread state không phải CPU sample | Dùng CPU profiler/JFR |
| Tăng connection pool không giới hạn | Tăng contention, session memory, lock wait | Sizing dựa trên DB capacity và hold time |
| Tăng JVM heap để chữa mọi lỗi memory | DB spill/OS cache không được khắc phục | Tách heap, native memory, DB và OS memory |
| Chỉ đo `executeQuery()` | Fetch/commit/GC/network có thể ở chặng khác | Đo execute, consume, commit, pool và toàn request |
| Coi `EXPLAIN ANALYZE` là chỉ đọc cho mọi SQL | DML vẫn được thực thi | Cẩn trọng; dùng test DB và rollback có cân nhắc |
| Tối ưu query riêng lẻ mà không xem `calls` | Query nhỏ nhưng gọi quá nhiều có thể tốn nhiều nhất | Xem tổng chi phí và N+1 |
| Chạy benchmark với bảng rất nhỏ | Plan/working set sai production | Dữ liệu, phân bố và tải đại diện |
| Thấy `LIMIT 100` thì nghĩ DB chỉ xử lý 100 rows | Sort/aggregate có thể phải xử lý hàng triệu dòng | Đọc actual rows/loops của plan |
| Bỏ transaction/constraint để giảm lock | Làm sai dữ liệu | Giữ bất biến, tối ưu critical section |
| Retry vô hạn khi timeout | Khuếch đại tải và có thể tạo tác động trùng | Retry hữu hạn, backoff, idempotency |
| Chỉ đo trung bình | Che p99, queue và trường hợp hot key | Dùng histogram, p95/p99 và breakdown |
| Tối ưu một metric nhưng không kiểm tra after-effect | Bottleneck dịch sang tầng khác | Re-run test và đo end-to-end |

## 22. Bài tập chẩn đoán ba API

Ba endpoint Java có những chỉ số giả định dưới tải cao:

| Chỉ số | API A: `GET /orders` | API B: `POST /transfer` | API C: `GET /report` |
| --- | ---: | ---: | ---: |
| API p95 | 850 ms | 1.800 ms | 3.200 ms |
| Pool wait p95 | 5 ms | 12 ms | 600 ms |
| JDBC SQL p95 | 700 ms | 1.700 ms | 2.200 ms |
| DB CPU | 92% | 18% | 70% |
| Lock wait | Hiếm | Rất nhiều | Ít |
| DB temp spill | Không rõ | Thấp | Rất cao |
| Số SQL/request | 101 | 3 | 2 |
| Dữ liệu trả về | Nhỏ, nhiều request riêng | Rất nhỏ | Rất lớn |

**Câu hỏi:**

1. API A nên kiểm tra vấn đề gì trước: thiếu index, N+1, hay tăng connection pool? Giải thích.
2. API B có thể chậm dù DB CPU 18% vì sao? Bạn dùng những view/metric nào để tìm blocker?
3. API C có khả năng gặp nhiều nút thắt nào cùng lúc? Bạn có tăng `work_mem` ngay không?
4. Nếu tăng pool từ 20 lên 80 mà API B không nhanh hơn, điều này có phù hợp giả thuyết lock contention không?
5. Tại sao không thể lấy `SQL p95` và `pool wait p95` cộng lại để ra chính xác `API p95`?
6. Một tối ưu giảm CPU DB 20% nhưng tăng lỗi ghi đè dữ liệu đồng thời có được chấp nhận không?

### Gợi ý lời giải

**API A:** 101 SQL/request là tín hiệu mạnh của **N+1**. Trước hết đo số statement và truy vấn từng loại; cân nhắc batch-fetch/projection/query theo tập ID. CPU cao có thể do tổng số câu SQL hoặc mapping, network round trips cũng góp phần. Vẫn cần plan trước khi loại trừ index, nhưng không tăng pool mù.

**API B:** nhiều session đợi row/table lock có thể khiến `UPDATE` mất hàng giây dù CPU thấp. Dùng `pg_stat_activity`, `wait_event_type`, `pg_blocking_pids`, transaction age, lock duration và tracing để xác định blocker. Sửa transaction dài/hot row; pool lớn hơn không làm blocker nhả lock.

**API C:** pool wait cao, temp spill cao và payload lớn gợi ý nhiều chặng: DB sort/aggregate spill, connection bị giữ lâu và network/mapping hàng lớn. Ưu tiên query plan, giảm dữ liệu trả, phân trang/batch và đo storage/GC. Chỉ xét `work_mem` sau khi biết memory budget và concurrency.

**Câu 5:** percentile của tổng **không bằng tổng percentile** của các thành phần nói chung; chúng có tương quan và thời điểm khác nhau. Cần trace end-to-end cùng request và phân tích phân bố, không cộng riêng hai p95.

**Câu 6:** Không. Hiệu năng chỉ là một mục tiêu của persistence; transaction, isolation và bất biến miền phải vẫn đúng.

## 23. Checklist xử lý một sự cố performance persistence

1. **Triệu chứng:** endpoint, thời điểm, loại tải, p50/p95/p99 và mức lỗi nào thay đổi?
2. **Ranh giới đo:** Java trước DB, pool acquisition, statement, fetch, commit và response serialization đã tách chưa?
3. **CPU:** process nào bận, profiler/plan cho thấy công việc gì?
4. **Bộ nhớ:** heap, GC, RSS, DB working set và temp spill có vấn đề không?
5. **Storage I/O:** đọc/ghi/WAL/temp, device latency và wait event có bất thường không?
6. **Mạng:** RTT, số round trip, packet loss, bytes/rows transferred và topology DB đã xem chưa?
7. **Khóa:** blocker, `idle in transaction`, hot row, deadlock và transaction duration có bất thường không?
8. **Pool:** active/idle/pending, acquisition time và connection hold time có khớp với DB sessions không?
9. **Query:** `EXPLAIN`, estimated/actual rows, `BUFFERS`, index selectivity, số calls và N+1 đã đo chưa?
10. **Tính đúng đắn:** thay đổi dự kiến có ảnh hưởng isolation, consistency, commit, durability hoặc idempotency không?
11. **Thử nghiệm:** workload và dữ liệu có đại diện, đã đổi một yếu tố và đo lại không?
12. **Theo dõi sau triển khai:** có baseline mới, guardrail, rollback và alert về p99/lock/IO/GC/pool không?

**Kết luận:** đừng đồng nhất “database chậm” với “thiếu CPU” hoặc “thiếu index”. Một API persistence Java đi qua nhiều hàng đợi và nhiều dạng công việc; **CPU, bộ nhớ, I/O, mạng và chờ khóa** để lại dấu hiệu khác nhau nhưng có thể tương tác. Cách tối ưu đáng tin cậy là **đo độ trễ theo chặng, đối chiếu bằng chứng từ JVM, pool và database, kiểm chứng một giả thuyết bằng thử nghiệm có kiểm soát**, rồi giữ nguyên các bảo đảm về giao dịch và dữ liệu khi triển khai cải thiện.
