# Điều chỉnh nhóm kết nối qua thử nghiệm mức tải đồng thời

Connection pool quyết định số kết nối database mà một instance ứng dụng có thể mượn cùng lúc và thời gian request phải chờ khi pool hết connection. Pool quá nhỏ tạo hàng đợi ở ứng dụng, làm tăng connection acquisition latency và giảm throughput dù database còn headroom. Pool quá lớn có thể đẩy quá nhiều truy vấn đồng thời vào database, làm CPU, I/O, lock, memory và tail latency tăng. Vì vậy, kích thước pool cần được chọn bằng thử nghiệm tải đồng thời có kiểm soát.

Trong phạm vi **DATABASE_PERFORMANCE**, tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Điều chỉnh connection pool là một phần của kiểm soát concurrency: cần đo thời gian giữ connection, thời gian chờ pool, số query đang chạy, trạng thái database và chất lượng execution plan. Mục tiêu là tìm điểm cân bằng giữa throughput, latency và mức sử dụng tài nguyên, đồng thời giữ tổng số connection của toàn bộ hệ thống trong ngân sách an toàn.

Bài học này xây dựng một bài thực hành từ baseline đến quyết định cấu hình: hiểu vòng đời connection, tính ngân sách toàn cụm, đo pool wait/hold time, thiết kế concurrency sweep, đọc kết quả theo SLO, cấu hình Java/HikariCP, xác nhận trên workload hỗn hợp và triển khai có giám sát.

## 1. Mục tiêu của bài thực hành

Sau bài thực hành, người học có thể:

- Phân biệt request concurrency, worker concurrency, pool size và số session database.
- Đo thời gian chờ lấy connection và thời gian connection được giữ.
- Ước lượng số connection hoạt động trung bình từ throughput và thời gian giữ connection.
- Tính tổng connection từ nhiều instance, worker và dịch vụ.
- Thiết kế thử nghiệm tải đồng thời để tìm điểm bão hòa của database.
- Phân biệt pool quá nhỏ với database đã hết năng lực phục vụ.
- Chọn maximumPoolSize, minimumIdle và timeout theo số liệu.
- Đọc execution plan và wait metrics khi throughput không tăng theo pool size.
- Triển khai thay đổi theo giai đoạn, có ngưỡng dừng và phương án quay lại.

Bài thực hành dùng Java JDBC và HikariCP làm ví dụ. Các nguyên tắc đo đạc áp dụng cho những connection pool khác; tên metric và cấu hình cụ thể phụ thuộc thư viện.

## 2. Connection pool nằm ở đâu trong đường xử lý?

Ứng dụng thường không tạo TCP connection mới cho từng truy vấn. Thay vào đó, DataSource cấp một connection có sẵn từ pool, ứng dụng thực hiện transaction hoặc query, rồi đóng connection để trả nó về pool.

~~~text
HTTP request / background job
            |
            v
Application worker
            |
            | getConnection()
            v
       Connection pool
       /      |       \
   active   idle    pending
     |                |
     v                |
 Database session     |
     |                |
 query / transaction  |
     |                |
 commit / rollback    |
     |                |
 close Connection ----+
      (return to pool)
~~~

Với pooled connection, gọi close thường trả logical connection về pool; nó không nhất thiết đóng physical connection tới server. Pool có thể kiểm tra và reset trạng thái session trước khi cấp connection cho request tiếp theo.

### Các đại lượng không được nhầm lẫn

| Đại lượng | Ý nghĩa |
|---|---|
| Request concurrency | Số request đang xử lý hoặc đang chờ |
| Worker concurrency | Số thread/task ứng dụng có thể chạy đồng thời |
| Pool maximum size | Số connection tối đa pool cấp đồng thời |
| Active connections | Số connection đang được ứng dụng mượn |
| Idle connections | Số connection đang nằm trong pool và có thể cấp |
| Pending borrowers | Số thread đang chờ connection |
| Database sessions | Số session hiện diện phía server |
| Active SQL statements | Số statement thực sự đang chạy hoặc đang được server xử lý |

Một request có thể không dùng database, dùng một connection trong thời gian ngắn hoặc giữ connection suốt transaction. Một request cũng có thể gọi nhiều database service hoặc fan-out thành nhiều query song song. Do đó, số request đồng thời không bằng số connection cần thiết.

## 3. Pool nhỏ và pool lớn tạo ra vấn đề gì?

### Pool quá nhỏ

Khi mọi connection đang được mượn, request tiếp theo phải chờ. Dấu hiệu thường gặp:

- Pending hoặc số thread chờ connection tăng.
- Connection acquisition p95/p99 tăng.
- Database có CPU/I/O còn headroom và số session hoạt động thấp hơn khả năng phục vụ đã đo.
- Request timeout ở bước lấy connection trước khi SQL bắt đầu.
- Throughput thấp dù database chưa bão hòa.
- Connection hold time tăng do transaction hoặc query chậm, làm pool nhanh cạn.

Trong trường hợp này, tăng pool có thể giúp, nhưng cần xác minh database còn capacity và connection không bị giữ quá lâu do lỗi ứng dụng.

### Pool quá lớn

Pool lớn cho phép nhiều statement cùng đi vào database. Khi database đã gần giới hạn CPU, I/O, lock hoặc log, thêm connection thường làm tăng cạnh tranh thay vì tăng throughput.

Dấu hiệu thường gặp:

- Database CPU hoặc storage utilization tiến gần mức bão hòa.
- Throughput đi ngang dù tăng pool size.
- p95/p99 query latency tăng.
- Lock wait, deadlock hoặc transaction duration tăng.
- Buffer/cache pressure, temp spill hoặc log flush latency tăng.
- Số session active lớn nhưng mỗi session hoàn tất ít công việc hơn.
- Connection acquisition wait giảm nhưng end-to-end latency tăng.

Điểm cần tối ưu là throughput hoàn tất ở mức latency và tài nguyên chấp nhận được, không phải số connection đang mở.

## 4. Ngân sách connection phải tính trên toàn hệ thống

Pool được cấu hình theo từng process/instance, nhưng database nhìn thấy tổng số session từ tất cả nguồn.

Một mô hình ngân sách:

~~~text
Tổng connection cực đại
  = tổng (số instance × pool max mỗi instance)
  + worker/job pools
  + dịch vụ khác
  + công cụ vận hành và monitoring
~~~

Ví dụ, 6 instance ứng dụng, mỗi instance có pool tối đa 24 connection, có thể tạo tối đa 144 connection. Nếu còn 2 worker service có tổng 20 connection và 15 connection dành cho batch/report, tải ứng dụng có thể đạt 179 session. Cần cộng thêm nhu cầu admin, migration, backup tooling, replication và headroom khôi phục.

### Không dùng max_connections làm mục tiêu pool

Giới hạn session của DBMS là mức trần kỹ thuật. Nó không chứng minh database có thể thực thi hiệu quả số query tương ứng. Mỗi session có thể tiêu thụ memory, backend/thread resource và trạng thái transaction. Mức an toàn phải được xác định qua thử nghiệm.

Hãy dành ngân sách cho:

- DBA và thao tác ứng cứu.
- Monitoring, backup và migration.
- Replication hoặc HA theo kiến trúc.
- Job nền và maintenance.
- Kết nối trong quá trình rolling deployment.
- Failover, khi nhiều instance có thể cùng chuyển về một database node.

### Rolling deployment có thể làm số pool tăng tạm thời

Khi triển khai phiên bản mới theo kiểu rolling, instance cũ và mới có thể cùng chạy trong một khoảng thời gian. Nếu cả hai nhóm đều giữ pool đầy, tổng connection tạm thời có thể cao hơn cấu hình steady-state.

Tính cả surge capacity, autoscaling và failover topology. Đặt giới hạn số instance tối đa hoặc điều chỉnh pool theo quy mô cụm nếu hệ thống có autoscaler.

## 5. Đo connection acquisition và connection hold time

Hai metric quan trọng nhất ở tầng pool là:

- **Acquisition time:** thời gian từ lúc gọi getConnection() đến lúc nhận được connection.
- **Hold time:** thời gian từ lúc nhận connection đến lúc trả về pool.

Nếu acquisition time cao nhưng hold time ngắn và database còn headroom, pool có thể quá nhỏ hoặc có burst lớn. Nếu hold time cao, cần tìm nguyên nhân query chậm, transaction dài, ứng dụng xử lý ngoài database trong khi giữ connection hoặc connection leak.

### Đo bằng JDBC

Ví dụ dưới đây minh họa cách đo hai khoảng thời gian. metrics.record đại diện cho thư viện metrics của ứng dụng:

~~~java
long acquireStarted = System.nanoTime();
long acquiredAt = 0L;

try {
    try (Connection connection = dataSource.getConnection()) {
        acquiredAt = System.nanoTime();

        metrics.record(
            "db.connection.acquire",
            acquiredAt - acquireStarted
        );

        orderRepository.loadOrder(connection, orderId);
    }
} catch (SQLException e) {
    if (acquiredAt == 0L) {
        metrics.record(
            "db.connection.acquire.failure",
            System.nanoTime() - acquireStarted
        );
    }
    metrics.increment("db.connection.error");
    throw e;
} finally {
    if (acquiredAt != 0L) {
        metrics.record(
            "db.connection.hold",
            System.nanoTime() - acquiredAt
        );
    }
}
~~~

Khối finally bên ngoài chạy sau khi try-with-resources đóng logical connection, nên hold time bao gồm cả thời gian trả connection về pool. Trong mã production, cần bảo đảm việc ghi metric không ném exception làm thay đổi luồng nghiệp vụ. Dùng System.nanoTime() để đo duration vì nó phù hợp với khoảng thời gian đơn điệu; không dùng currentTimeMillis() để tính latency.

Nếu getConnection() ném timeout, vẫn nên ghi nhận acquisition failure và thời gian chờ trước khi thất bại. Không ghi SQL parameter hoặc dữ liệu nhạy cảm vào metric label.

### Hold time không chỉ là query execution time

Một connection có thể được giữ trong các khoảng:

- Bắt đầu transaction.
- Thực thi một hoặc nhiều query.
- Đọc ResultSet.
- Chuyển đổi dữ liệu.
- Chờ lock.
- Gọi service ngoài hoặc xử lý CPU do code đặt nhầm bên trong transaction.
- Commit hoặc rollback.
- Cleanup/reset session.

Nếu một request giữ connection 500 ms nhưng SQL chỉ chạy 80 ms, 420 ms còn lại cần được giải thích. Giảm thời gian giữ connection có thể hiệu quả hơn tăng pool.

### Ghi nhận phân vị

Thu thập p50, p95 và p99 của acquisition time, hold time và query duration. Average có thể che giấu các request giữ connection rất lâu. Gắn metric với pool name, service, workload class và operation đã được chuẩn hóa; tránh tạo label có cardinality vô hạn như request id.

## 6. Quan sát trạng thái pool

Hầu hết pool cung cấp số liệu về connection active, idle, total và thread đang chờ. Với HikariCP, có thể đọc HikariPoolMXBean hoặc metrics tích hợp với Micrometer tùy cấu hình.

Ví dụ:

~~~java
HikariPoolMXBean poolBean = hikariDataSource.getHikariPoolMXBean();

if (poolBean != null) {
    int active = poolBean.getActiveConnections();
    int idle = poolBean.getIdleConnections();
    int total = poolBean.getTotalConnections();
    int waiting = poolBean.getThreadsAwaitingConnection();

    metrics.gauge("db.pool.active", active);
    metrics.gauge("db.pool.idle", idle);
    metrics.gauge("db.pool.total", total);
    metrics.gauge("db.pool.pending", waiting);
}
~~~

MXBean là snapshot tại thời điểm đọc; không dùng một mẫu đơn lẻ để kết luận. Hãy thu thập theo chu kỳ đủ ngắn để nhìn thấy burst nhưng không tạo overhead lớn.

### Cách diễn giải

| Quan sát | Khả năng cần kiểm tra |
|---|---|
| Active gần max, pending tăng, DB còn headroom | Pool nhỏ, burst hoặc connection hold time cao |
| Active gần max, pending tăng, DB CPU/IO bão hòa | DB đang là giới hạn; tăng pool có thể làm xấu hơn |
| Active thấp, pending cao | Pool metrics hoặc worker behavior bất thường; kiểm tra pool, thread và acquisition |
| Idle cao, pending bằng 0 | Pool đang có dư capacity ở thời điểm đo |
| Total thấp, pending cao | Connection creation chậm, DB từ chối kết nối hoặc pool không mở thêm được |
| Active thấp nhưng hold time cao | Một số connection giữ lâu; xem transaction, ResultSet và code ngoài DB |
| Active cao, DB active SQL thấp | Session idle-in-transaction, connection giữ giữa các bước hoặc app chờ trong transaction |

Cần đối chiếu với số session và trạng thái ở server. Active connection phía pool không nhất thiết tương ứng với statement đang chạy; connection có thể đang idle trong transaction hoặc chờ ứng dụng.

## 7. Ước lượng số connection từ throughput và hold time

Định luật Little cung cấp một ước lượng hữu ích cho số connection trung bình đang được mượn:

~~~text
Số connection đang bận trung bình
  ≈ throughput database operations × thời gian giữ connection trung bình
~~~

Ví dụ, ứng dụng hoàn tất 400 thao tác database mỗi giây và thời gian giữ connection trung bình cho mỗi thao tác là 50 ms (0,05 giây):

~~~text
L ≈ 400 × 0,05 = 20 connection
~~~

Kết quả 20 là số connection đang bận trung bình trong điều kiện workload ổn định và định nghĩa operation/hold time nhất quán. Nó không phải giá trị maximumPoolSize tự động.

Nếu một request thực hiện nhiều query trên cùng connection, throughput cần đo theo đơn vị connection checkout hoặc transaction tương ứng. Nếu một request mượn nhiều connection song song, phải tính số checkout đồng thời chứ không chỉ số HTTP request.

### Dùng phép tính để kiểm tra tính hợp lý

Nếu metric cho thấy trung bình 20 connection bận nhưng pool max chỉ 12, có thể có nhiều instance/pool hoặc phép đo throughput/hold time chưa cùng phạm vi. Nếu pool max là 100 nhưng chỉ 8 connection bận ở peak, cần xem liệu workload có đủ lớn và pool có thực sự là giới hạn.

### Thêm headroom dựa trên biến động

Throughput và hold time không cố định. Burst, query chậm, lock contention và job nền làm nhu cầu connection biến động. Dùng phân phối và thử nghiệm peak để chọn giới hạn, không lấy average nhân một hệ số tùy ý rồi coi đó là đáp án.

## 8. Xác định database capacity trước khi chỉnh pool

Connection pool cần được điều chỉnh theo năng lực phục vụ database. Trước thử nghiệm, xác định database có thể xử lý bao nhiêu concurrency ở mức SLO.

### Các giới hạn thường gặp

- CPU compute hoặc scheduler.
- Data I/O và log I/O.
- Lock/latch contention.
- Buffer pool/shared buffers và memory grants.
- Temp space và sort/hash spill.
- WAL/redo/log flush.
- Số worker, session hoặc process.
- Network bandwidth và round trip.
- Replication lag hoặc giới hạn của primary.

Nếu database đã bão hòa CPU hoặc log flush, pool lớn hơn không tạo thêm năng lực vật lý.

### Đọc query workload trước

Thu thập query fingerprint/digest, calls, total/average duration, rows, logical reads/buffers và plan. Xác định query nào giữ connection lâu nhất hoặc tạo lock wait.

Một truy vấn có execution plan kém có thể làm hold time tăng, khiến pool cạn. Khi đó, tối ưu query hoặc index có thể giảm số connection cần thiết mà không tăng pool.

### Phân biệt app pool wait và database wait

- Pool wait: ứng dụng chưa lấy được connection.
- Lock wait: database session đã tồn tại nhưng chờ khóa.
- I/O wait: session chờ page/file/log.
- CPU runnable: session sẵn sàng chạy nhưng thiếu CPU scheduler capacity.
- Network wait: client/server chờ truyền dữ liệu.

Không gộp các loại wait thành một chỉ số database latency.

## 9. Thiết kế thử nghiệm tải đồng thời

Một thử nghiệm tốt phải trả lời câu hỏi rõ ràng: pool đang giới hạn throughput hay database đã chạm điểm bão hòa?

### Giữ cố định các yếu tố không thử

Trong một vòng thử nghiệm, cố gắng giữ nguyên:

- DBMS version và cấu hình.
- Schema, index và statistics.
- Dataset và data distribution.
- SQL/query mix và parameter groups.
- Số application instance.
- CPU/memory quota của ứng dụng.
- Network path.
- Background jobs.
- Cache state hoặc quy trình warm-up.
- Thời gian đo và cách lấy metric.

Nếu thay pool size, không đồng thời thay index, query shape và DBMS configuration. Nếu không, sẽ không biết thay đổi nào tạo ra kết quả.

### Dùng hai pha thử nghiệm

**Pha A — Tìm vùng concurrency của workload**

Giữ pool size cố định ở mức baseline. Tăng dần số request/worker đồng thời để tìm điểm throughput bắt đầu đi ngang và latency tăng nhanh. Quan sát pool pending cùng database saturation.

**Pha B — Tìm pool size phù hợp**

Chọn một mức tải đại diện gần peak dự kiến. Giữ query mix và offered load như nhau, rồi thay đổi pool max qua các mức. Đo throughput, tail latency, acquisition wait và DB metrics.

Hai pha này giúp tránh thay cả concurrency đầu vào và pool size cùng lúc khiến kết quả khó diễn giải.

## 10. Chọn kiểu tải: closed-loop và open-loop

### Closed-loop / concurrency-based

Load generator giữ một số user/request đồng thời. Khi một request hoàn tất, nó gửi request tiếp theo.

Ưu điểm: dễ mô phỏng số user đang hoạt động và tìm throughput tại từng mức concurrency.

Giới hạn: khi hệ thống chậm, tốc độ gửi request tự giảm. Điều này có thể che giấu mức tải thực mà hệ thống cần chịu.

### Open-loop / arrival-rate-based

Load generator phát request theo tốc độ xác định, ví dụ 500 request/giây, bất kể request trước đã hoàn tất hay chưa.

Ưu điểm: kiểm tra được hệ thống dưới offered load cố định và nhìn rõ queue tăng khi service rate không theo kịp.

Giới hạn: cần giới hạn queue ở load generator và theo dõi request chưa được gửi đúng thời điểm. Nếu generator không đủ capacity, số liệu sẽ sai.

### Dùng cả hai khi có thể

Closed-loop giúp khảo sát đường cong concurrency/throughput. Open-loop giúp kiểm tra SLO ở arrival rate dự kiến và overload. Khi đọc kết quả, ghi rõ loại test và mô hình load; không so sánh số liệu của hai mô hình như nhau.

## 11. Chuẩn bị môi trường và workload

Trước khi chạy:

1. Dùng môi trường staging/performance test có cấu hình gần production.
2. Nạp dataset có kích thước và phân bố gần thực tế.
3. Xác nhận index và statistics đã sẵn sàng.
4. Tắt hoặc cố định job nền không thuộc kịch bản.
5. Xác nhận load generator không phải bottleneck.
6. Đồng bộ thời gian và metric window.
7. Tạo dashboard pool, application, DBMS và storage.
8. Xác định test data có thể reset hoặc replay an toàn.
9. Chuẩn bị ngưỡng dừng khi DB hoặc môi trường test quá tải.
10. Chạy smoke test ở concurrency thấp để xác nhận dữ liệu và kết quả đúng.

### Query mix

Một workload đại diện có thể gồm:

| Nhóm | Tỷ trọng minh họa | Đặc điểm |
|---|---:|---|
| Tra cứu đơn hàng | 45% | SELECT ngắn, index lookup |
| Tìm kiếm theo khách hàng | 20% | Filter/join, tham số có skew |
| Cập nhật trạng thái | 20% | UPDATE, transaction ngắn |
| Ghi audit/event | 10% | INSERT hoặc batch nhỏ |
| Báo cáo nhẹ | 5% | Aggregate, đọc nhiều hơn |

Tỷ trọng là ví dụ. Hãy lấy từ traffic profile thực tế hoặc xác định rõ giả định của bài test. Không chỉ thử một SELECT đơn giản nếu production có transaction ghi và lock contention.

### Transaction scope

Mô phỏng đúng cách ứng dụng dùng connection:

- Autocommit hay explicit transaction.
- Số query trong mỗi transaction.
- Thời gian đọc ResultSet.
- Commit/rollback.
- Retry khi deadlock hoặc timeout.
- Thời gian xử lý ngoài database khi connection đang được giữ.

Nếu test chỉ chạy một câu SELECT rồi trả connection ngay, kết quả không đại diện cho endpoint giữ connection suốt transaction.

## 12. Quy trình chạy concurrency sweep

Một vòng thử có thể gồm các bước:

1. Khởi động ứng dụng và pool với cấu hình baseline.
2. Xác nhận số connection và trạng thái database.
3. Warm-up đến khi throughput và cache ổn định.
4. Chạy concurrency thấp để lấy điểm tham chiếu.
5. Tăng concurrency theo các bậc, ví dụ 8, 16, 24, 32, 48, 64 worker.
6. Ở mỗi bậc, chờ hệ thống ổn định rồi đo trong một cửa sổ cố định.
7. Ghi throughput, p50/p95/p99, pool wait, hold time và DB metrics.
8. Dừng tăng khi latency vượt ngưỡng, error tăng hoặc database chạm giới hạn.
9. Cho hệ thống drain queue và trở về baseline.
10. Lặp lại các điểm quan trọng để kiểm tra độ ổn định.

Thời gian warm-up và steady-state phụ thuộc workload; ví dụ có thể warm-up vài phút và đo 10–15 phút mỗi bậc. Không coi các khoảng này là tiêu chuẩn chung. Job batch, checkpoint hoặc cache warm-up có thể cần cửa sổ dài hơn.

### Tránh coordinated omission

Nếu load generator chỉ gửi request mới sau khi request trước hoàn tất, khi hệ thống chậm nó gửi ít request hơn và có thể báo latency đẹp hơn thực tế. Với kịch bản arrival-rate, hãy ghi nhận request bị trễ hoặc không thể phát đúng lịch; không bỏ qua chúng khỏi báo cáo.

### Lặp lại và kiểm tra nhiễu

Chạy lại các điểm đại diện ít nhất vài lần nếu chi phí cho phép. Nếu kết quả biến động lớn, kiểm tra background task, cache state, autoscaling, noisy neighbor và load generator trước khi chọn cấu hình.

## 13. Ghi metric trong mỗi lần thử

Mỗi cửa sổ thử nghiệm nên lưu cùng một bộ metric.

| Lớp | Metric |
|---|---|
| Load generator | Offered rate, completed rate, concurrency, dropped/late requests |
| API | Throughput, p50/p95/p99, error/timeout |
| Pool | Active, idle, total, pending, acquisition latency |
| Connection | Hold time, checkout count, timeout count |
| Query | Calls, total/average time, rows, logical reads |
| DBMS | CPU, active sessions, runnable/waiting, memory |
| Lock | Lock wait, deadlock, transaction age |
| Storage | IOPS, throughput, read/write latency, queue depth |
| Log | Commit latency, WAL/redo/log flush throughput |
| Memory/temp | Buffer/cache hit, memory grant, temp spill |
| Replication | Lag và apply throughput nếu có |

### Đo theo đúng phạm vi

Nếu pool metric ở từng instance nhưng database metric ở toàn cụm, phải tổng hợp cùng time window. Nếu một instance nhận nhiều traffic hơn, pool active của nó có thể cao hơn; không lấy trung bình các instance mà bỏ qua phân bố.

### Gắn phiên bản và cấu hình vào kết quả

Mỗi run cần có run id, commit/application version, pool settings, DBMS version, dataset version, load profile và thời gian bắt đầu/kết thúc. Không dùng tên "test 3" mà không biết pool max và concurrency tương ứng.

## 14. Cấu hình HikariCP để thử nghiệm

HikariCP là một JDBC connection pool phổ biến. Ví dụ dưới đây dùng giá trị minh họa để tạo một cấu hình có thể thay đổi giữa các lần test:

~~~java
HikariConfig config = new HikariConfig();

config.setJdbcUrl(jdbcUrl);
config.setUsername(databaseUser);
config.setPassword(databasePassword);

config.setPoolName("orders-pool");
config.setMaximumPoolSize(24);
config.setMinimumIdle(8);

config.setConnectionTimeout(3_000);
config.setIdleTimeout(600_000);
config.setMaxLifetime(1_500_000);

HikariDataSource dataSource = new HikariDataSource(config);
~~~

Các giá trị này không phải khuyến nghị chung. maximumPoolSize phải dựa trên ngân sách connection và kết quả benchmark. minimumIdle điều khiển số connection nhàn rỗi mục tiêu khi pool co giãn; nếu đặt bằng maximumPoolSize, pool hoạt động theo kiểu giữ kích thước cố định.

### Maximum pool size

Giới hạn số connection đồng thời mà một pool cấp. Khi tất cả connection đã được mượn, thread mới phải chờ đến khi có connection trả về hoặc hết connectionTimeout.

Không đặt maximumPoolSize bằng số thread của HTTP server theo thói quen. Worker có thể không cần database ở mọi thời điểm, còn database có thể chỉ phục vụ hiệu quả một phần concurrency đó.

### Minimum idle

Số connection nhàn rỗi tối thiểu mà pool cố gắng duy trì. Giá trị cao giúp giảm độ trễ mở connection khi burst nhưng làm tăng session idle. Trong môi trường nhiều instance, tổng minimum idle cũng cần tính vào ngân sách.

### Connection timeout

Thời gian tối đa chờ lấy connection. Timeout cần phù hợp với tổng request deadline. Nếu request chỉ còn 200 ms mà connectionTimeout là 5 giây, thread có thể tiếp tục chờ sau khi client đã bỏ cuộc.

### Max lifetime và idle timeout

maxLifetime nên ngắn hơn giới hạn tuổi connection do database, proxy hoặc hạ tầng áp đặt. idleTimeout chỉ có ý nghĩa co pool khi minimumIdle thấp hơn maximumPoolSize. Cần đọc tài liệu phiên bản HikariCP và giới hạn thực tế của môi trường.

### Leak detection

Leak detection có thể giúp tìm connection được mượn quá lâu, nhưng một transaction hợp lệ dài cũng có thể tạo cảnh báo. Chỉ bật ngưỡng phù hợp trong giai đoạn chẩn đoán, xem stack trace và đối chiếu hold time trước khi kết luận leak.

## 15. Thay đổi một biến tại một thời điểm

Khi thử pool size, giữ các tham số khác cố định. Một trình tự điển hình:

| Run | Pool max | Pool min idle | Offered load | Mục tiêu |
|---|---:|---:|---|---|
| A | 8 | 4 | Cố định | Baseline pool nhỏ |
| B | 16 | 4 | Cố định | Kiểm tra giảm pool wait |
| C | 24 | 8 | Cố định | Kiểm tra throughput và DB saturation |
| D | 32 | 8 | Cố định | Tìm điểm bắt đầu bão hòa |
| E | 48 | 8 | Cố định | Xác nhận lợi ích đã plateau chưa |
| F | 64 | 8 | Cố định | Chỉ chạy nếu DB còn an toàn |

Bảng là kế hoạch minh họa, không phải dãy bắt buộc. Nếu DB đã chạm giới hạn ở run D, không cần cố chạy run F. Dừng theo ngưỡng an toàn đã định.

Sau khi chọn pool max, mới thử điều chỉnh minimumIdle, timeout hoặc số worker riêng biệt. Không thay cả pool max, query index và DB configuration trong cùng một run.

## 16. Ví dụ kết quả thử nghiệm

Giả sử một dịch vụ xử lý đơn hàng chạy trên cùng dataset, cùng query mix và cùng offered load. Chỉ maximumPoolSize được thay đổi.

| Pool max | Throughput (txn/s) | p95 (ms) | Acquire p95 (ms) | DB CPU | Lock wait trung bình |
|---:|---:|---:|---:|---:|---:|
| 8 | 300 | 240 | 85 | 48% | 3 ms |
| 16 | 500 | 250 | 35 | 70% | 5 ms |
| 24 | 625 | 290 | 18 | 84% | 8 ms |
| 32 | 640 | 470 | 7 | 96% | 25 ms |
| 48 | 638 | 900 | 2 | 99% | 80 ms |
| 64 | 610 | 1.450 | 1 | 99% | 150 ms |

Các số liệu trên chỉ là ví dụ minh họa cách đọc kết quả. Giả sử SLO p95 là 300 ms và throughput mục tiêu là ít nhất 600 transaction/giây.

### Diễn giải

- Pool 8: database còn headroom nhưng acquisition wait cao; pool đang hạn chế throughput.
- Pool 16: throughput tăng rõ và p95 vẫn nằm trong SLO.
- Pool 24: throughput đạt mục tiêu, p95 gần ngưỡng và DB CPU đã cao hơn; cần xác nhận thêm với tải peak.
- Pool 32: throughput chỉ tăng rất ít nhưng p95 vượt SLO và CPU gần bão hòa.
- Pool 48/64: throughput đi ngang hoặc giảm, trong khi latency và lock wait tăng mạnh.

Trong ví dụ này, pool 24 là ứng viên cho thử nghiệm tiếp theo vì đáp ứng throughput mục tiêu và p95 còn trong SLO. Nếu workload có burst hoặc biến động lớn, có thể chọn 16 để giữ headroom hoặc cần tối ưu query trước khi chốt 24. Quyết định cuối cùng phải dựa trên nhiều lần chạy và tải peak thực tế.

### Bài học từ bảng

Acquisition wait giảm khi pool tăng, nhưng điều đó không có nghĩa end-to-end latency luôn giảm. Sau điểm bão hòa, request vào database nhanh hơn nhưng phải chờ CPU, lock hoặc I/O lâu hơn. Pool đã chuyển hàng đợi từ ứng dụng sang database.

## 17. Xác định điểm bão hòa của database

Điểm bão hòa là vùng mà thêm concurrency không còn tạo throughput tăng tương ứng, trong khi latency hoặc wait tăng nhanh.

Các dấu hiệu kết hợp:

- Throughput completed gần như đi ngang.
- p95/p99 tăng phi tuyến.
- CPU gần mức tối đa được cấp hoặc runnable queue tăng.
- Storage latency/queue depth tăng.
- Lock wait/deadlock tăng.
- Commit latency hoặc log flush tăng.
- Số active session tăng nhưng tốc độ hoàn tất không tăng.
- Temp spill hoặc memory pressure tăng.

### Không dùng một ngưỡng CPU duy nhất

Database có thể bão hòa ở CPU 65% nếu storage hoặc lock là bottleneck. Ngược lại, CPU 95% trong một workload batch có thể vẫn đáp ứng throughput nếu SLO cho phép và không ảnh hưởng workload khác.

Điểm bão hòa phải được xác định theo tổ hợp throughput, tail latency, wait events và SLO.

### Giữ headroom

Không nên cấu hình pool ở đúng điểm throughput tối đa nếu chỉ cần một burst nhỏ đã làm p99 vượt ngưỡng. Chọn vùng vận hành có headroom để hấp thụ biến động, checkpoint, backup, vacuum/analyze và failover.

## 18. Kiểm tra execution plan khi pool tăng mà throughput không tăng

Khi tăng pool nhưng throughput không tăng, cần kiểm tra truy vấn có đang tiêu thụ nhiều tài nguyên hơn do concurrency.

### Query fingerprint

Xếp hạng query theo calls, total/average duration, CPU/worker time nếu có, logical reads/buffers và rows examined. Xem query nào tăng latency khi concurrency tăng.

### Execution plan

Kiểm tra:

- Estimated rows và actual rows.
- Index seek/scan hoặc table scan.
- Join order và số loops.
- Sort/hash spill.
- Parallel workers.
- Partition pruning.
- Implicit conversion và predicate.
- Locking behavior và transaction duration.

Nếu một truy vấn scan bảng lớn được gọi đồng thời nhiều lần, tăng pool có thể làm tổng I/O và CPU bão hòa. Giảm số dòng đọc hoặc cải thiện index có thể cho phép database xử lý nhiều request hơn với cùng số connection.

### Statistics

Thống kê cũ hoặc data skew có thể làm optimizer chọn plan không phù hợp. Cập nhật statistics khi có bằng chứng, sau đó chạy lại cùng workload vì plan có thể thay đổi.

## 19. Tách workload khi một pool phục vụ nhiều loại truy vấn

Nếu OLTP, report và batch dùng chung pool, các truy vấn dài có thể chiếm connection của request ngắn.

Có thể cân nhắc pool hoặc semaphore riêng theo workload class:

- Interactive OLTP.
- Ghi transaction.
- Report/analytics.
- Background job.
- Maintenance.

Các pool riêng tạo bulkhead ở tầng ứng dụng nhưng không tạo thêm CPU, I/O hoặc memory ở database. Tổng maximum size của chúng vẫn phải nằm trong connection budget.

### Ví dụ phân bổ

Giả sử tổng ngân sách connection của một service instance là 24:

~~~text
Interactive read/write: 18
Report:                  3
Background jobs:         2
Operational reserve:     1
                         --
Total:                  24
~~~

Đây chỉ là minh họa. Có thể tốt hơn khi dùng một pool chung với semaphore theo workload nếu các pool riêng làm tăng idle connection hoặc khó quản lý. Hãy đo fairness, pool wait và database saturation trước khi tách.

### Không để report chiếm hết connection

Giới hạn số report chạy đồng thời và có thể đặt timeout riêng. Query report nên đọc dữ liệu cần thiết, dùng replica hoặc summary table khi kiến trúc cho phép. Nhưng replica cũng có capacity và replication lag; không chuyển tải mù quáng.

## 20. Phân biệt connection leak với connection hold time cao

Một connection leak xảy ra khi ứng dụng mượn connection nhưng không trả lại pool do thiếu close hoặc exception path. Hold time cao có thể là hành vi hợp lệ nhưng chậm.

### Dấu hiệu leak

- Active connection tăng dần và không giảm sau khi tải kết thúc.
- Idle connection giảm về 0.
- Pending thread tăng theo thời gian.
- Connection được mượn lâu hơn nhiều so với transaction bình thường.
- Leak detection chỉ ra stack trace của nơi mượn.

### Dấu hiệu hold time cao nhưng không leak

- Active tăng theo tải rồi giảm khi request hoàn tất.
- Hold time dài có nguyên nhân như query chậm, lock wait hoặc đọc ResultSet.
- Connection được trả về pool sau khi transaction kết thúc.
- Không có xu hướng active tăng mãi.

### Cách điều tra

1. Đo checkout/return time.
2. Gắn operation name hoặc trace id đã chuẩn hóa.
3. Kiểm tra try-with-resources.
4. Xem connection có bị giữ trong khi gọi HTTP hoặc chờ message không.
5. Kiểm tra transaction có mở quá sớm.
6. Đối chiếu stack trace leak detection với trace.
7. Kiểm tra ResultSet/Statement được đóng.
8. Xác nhận pool reset connection state sau exception/rollback.

Không tăng pool để che leak. Pool lớn hơn chỉ kéo dài thời gian trước khi cạn connection.

## 21. Timeout và hàng đợi ở pool

connectionTimeout là thời gian tối đa thread chờ pool cấp connection. Timeout quá dài giữ thread và làm request hết deadline; timeout quá ngắn có thể từ chối request trong burst ngắn dù pool sắp có connection trả về.

### Phân bổ deadline

Ví dụ request có deadline 1.500 ms:

~~~text
Admission wait:              100 ms
Connection acquisition:      200 ms
SQL execution + transaction: 900 ms
Response/cleanup reserve:    300 ms
                             ------
Total:                      1.500 ms
~~~

Các con số chỉ minh họa. Hãy phân bổ theo latency thực tế và SLO. Query timeout nên tương thích với thời gian còn lại sau khi lấy connection.

### Pool timeout không phải query timeout

Nếu không lấy được connection, SQL chưa bắt đầu. Nếu lấy được connection nhưng query chờ lock, đó là timeout ở tầng statement/database. Cần ghi metric riêng để biết request thất bại ở bước nào.

### Retry khi pool timeout

Không retry ngay lập tức khi pool timeout. Retry tạo thêm borrower và làm queue dài hơn. Nếu có retry, dùng budget, backoff, jitter và deadline; thường cần trả lỗi tạm thời hoặc áp dụng admission control sớm.

## 22. Cấu hình pool theo số instance và autoscaling

Giả sử một dịch vụ có thể scale từ 4 lên 10 instance. Nếu mỗi instance có pool max 24:

~~~text
4 instance  × 24 =  96 connections
10 instance × 24 = 240 connections
~~~

Khi autoscaler tăng instance, tổng connection tăng dù mỗi pool không thay đổi. Database có thể bị quá tải ngay sau scale-out.

### Các cách kiểm soát

- Tính pool max theo số instance tối đa.
- Dùng cấu hình pool theo môi trường hoặc theo replica count.
- Giới hạn autoscaling nếu database là bottleneck.
- Dùng connection proxy/pooler khi kiến trúc và protocol hỗ trợ.
- Dùng admission control toàn hệ thống.
- Tách connection budget cho job và service.
- Theo dõi tổng connection trên server, không chỉ từng instance.

Một proxy/pooler có thể multiplex một số mô hình session/transaction nhưng không phải mọi ứng dụng hoặc tính năng đều tương thích. Kiểm tra transaction semantics, prepared statement, session state và vendor support trước khi triển khai.

## 23. Tuning theo từng vòng lặp

Một chu trình điều chỉnh có kiểm soát:

1. **Baseline:** lưu cấu hình pool, query mix, concurrency và metrics.
2. **Giả thuyết:** xác định pool wait hay database saturation là giới hạn.
3. **Thay đổi nhỏ:** điều chỉnh một tham số, thường là maximum pool size.
4. **Load test:** chạy cùng workload và điều kiện.
5. **Đọc kết quả:** throughput, p95/p99, acquisition, hold time, DB waits.
6. **Xác nhận plan:** kiểm tra query có thay đổi access path hoặc cardinality không.
7. **Lặp lại:** chỉ tăng/giảm thêm khi dữ liệu cho thấy lợi ích.
8. **Chọn vùng vận hành:** đáp ứng SLO và còn headroom.
9. **Kiểm tra toàn cụm:** nhân số pool với số instance và worker.
10. **Canary:** triển khai một phần traffic trước khi mở rộng.
11. **Quan sát:** theo dõi đủ chu kỳ peak và job nền.
12. **Ghi quyết định:** lưu cấu hình, dữ liệu test và lý do chọn.

### Khi nào tăng pool?

Cân nhắc tăng khi:

- Pool pending/acquisition wait cao.
- Database còn headroom.
- Query service time ổn định.
- Throughput tăng trong các lần thử trước khi tăng pool.
- Tổng connection budget vẫn an toàn.

### Khi nào giảm pool?

Cân nhắc giảm khi:

- DB CPU/I/O/lock đã bão hòa.
- Throughput không tăng nhưng p95/p99 tăng.
- Active session quá nhiều.
- Tăng pool làm lock wait hoặc log pressure tăng.
- Một workload nặng chiếm connection của workload quan trọng.

### Khi nào không nên chỉnh pool?

Nếu hold time tăng do execution plan regression, query scan quá nhiều hoặc transaction giữ lock lâu, hãy sửa nguyên nhân đó trước. Pool chỉ điều tiết số kết nối; nó không sửa query chậm.

## 24. Triển khai cấu hình mới trong production

Không chuyển toàn bộ instance sang pool size mới cùng lúc nếu chưa có bằng chứng.

### Canary

- Chọn một nhóm instance nhỏ.
- Đảm bảo nhóm canary nhận workload tương đương nhóm đối chứng.
- Theo dõi pool active/idle/pending và acquisition latency.
- Theo dõi database CPU, I/O, lock, session và throughput.
- So sánh p95/p99 theo endpoint và query fingerprint.
- Dừng mở rộng nếu vượt stop condition.

### Ngưỡng dừng

Ví dụ ngưỡng cần định nghĩa trước:

- p95 API hoặc query vượt SLO trong nhiều cửa sổ liên tiếp.
- DB CPU hoặc storage latency vượt giới hạn an toàn.
- Lock wait/deadlock tăng mạnh.
- Pool timeout hoặc error rate vượt error budget.
- Tổng connection tiến sát ngân sách server.
- Replication lag hoặc commit latency vượt giới hạn.

Ngưỡng cụ thể phải lấy từ SLO và baseline của hệ thống, không dùng các giá trị minh họa làm chuẩn chung.

### Rollback

Giữ cấu hình pool trước đó để có thể khôi phục nhanh. Rollback pool size thường ít rủi ro hơn thay đổi schema, nhưng giảm pool quá nhanh có thể làm request mới chờ lâu; cần triển khai có kiểm soát và theo dõi pending/latency sau rollback.

## 25. Ví dụ bài thực hành hoàn chỉnh

Giả sử dịch vụ orders-api có 6 instance, mỗi instance dùng HikariCP. Database phục vụ giao dịch đọc/ghi đơn hàng và một số report nhẹ.

### Bối cảnh ban đầu

- Pool max hiện tại: 12 connection/instance.
- Minimum idle: 4.
- Peak request concurrency: khoảng 180 trên toàn cụm.
- Throughput giờ cao điểm: 450 transaction/giây.
- p95 API: 420 ms.
- Pool pending tăng vào giờ cao điểm.
- Database CPU trung bình giờ cao điểm: 55%.
- Một số query giữ connection lâu do transaction có nhiều bước.

Đây là dữ liệu giả định cho bài thực hành. Không suy ra pool nên tăng lên 24 chỉ từ thông tin này; cần đo hold time và chạy thử.

### Bước 1 — Kiểm tra connection budget

Với 6 instance và pool max 12:

~~~text
Ứng dụng chính: 6 × 12 = 72 connection
Worker import:                 8 connection
Report service:                6 connection
Monitoring/admin reserve:     14 connection
                              --------------
Tổng kế hoạch:               100 connection
~~~

So sánh tổng này với ngân sách session an toàn của database, tính cả autoscaling và failover. Nếu tăng pool max lên 24, ứng dụng chính có thể dùng 144 connection; tổng kế hoạch tăng lên 172.

### Bước 2 — Thu hold time

Đo cho thấy:

- Connection hold time trung bình: 45 ms.
- Acquisition p95 giờ cao điểm: 110 ms.
- Active connection thường xuyên gần max.
- Database CPU còn headroom nhưng lock wait tăng ở một query cập nhật trạng thái.

Ước lượng số connection bận trung bình ở throughput 450 transaction/giây:

~~~text
L ≈ 450 × 0,045 = 20,25 connection
~~~

Nếu mỗi transaction tương ứng một lần checkout, số bận trung bình khoảng 20 connection cho toàn phạm vi đo. Nhưng 6 pool có tổng max 72, nên cần xác nhận số liệu được đo trên toàn cụm và workload có fan-out hay không. Peak demand có thể cao hơn average.

### Bước 3 — Tìm nguyên nhân hold time

Trace cho thấy một số transaction giữ connection trong khi gọi dịch vụ pricing. Tách lời gọi ngoài database ra khỏi transaction và chỉ giữ connection trong thời gian cần query/commit.

Đo lại hold time sau thay đổi trước khi tăng pool. Nếu hold time giảm, số connection cần thiết cũng có thể giảm.

### Bước 4 — Chạy thử pool size

Trong staging, cố định 6 instance tương đương, query mix và offered load. Chạy các cấu hình max 8, 12, 16, 20, 24 cho mỗi instance. Ghi kết quả theo cùng cửa sổ và lặp lại các mức quan trọng.

Dừng thử nếu tổng connection vượt ngân sách thử nghiệm hoặc database chạm ngưỡng CPU/lock/I/O đã đặt.

### Bước 5 — Chọn cấu hình

Chọn cấu hình có throughput đạt mục tiêu, p95/p99 trong SLO, pool wait hợp lý và DB headroom đủ cho burst/background jobs. Nếu pool 20 và 24 cho throughput gần nhau nhưng pool 24 làm lock wait tăng, ưu tiên mức thấp hơn hoặc tối ưu query gây contention.

### Bước 6 — Canary và xác nhận

Triển khai cấu hình mới lên một instance hoặc một nhóm nhỏ. So sánh với instance cũ có traffic tương đương. Sau khi ổn định, mở rộng dần và theo dõi tổng connection toàn cụm.

## 26. Các lỗi thường gặp khi thử tải pool

- **Chỉ tăng pool đến khi pending bằng 0:** có thể chuyển queue sang database và làm p99 tăng.
- **Dùng request concurrency làm pool size:** không tính request không truy cập DB, fan-out và transaction scope.
- **Chỉ đo một instance:** bỏ qua tổng connection của toàn cụm.
- **Chỉ nhìn average:** bỏ qua acquisition/hold p95 và p99.
- **Không đo hold time:** không biết connection bị giữ lâu do đâu.
- **Chỉ chạy SELECT đơn giản:** bỏ qua write, lock, commit và report.
- **Thay pool cùng lúc với query/index:** không xác định được nguyên nhân cải thiện.
- **Dùng closed-loop duy nhất:** có thể che offered load khi response chậm.
- **Không warm-up hoặc không ghi cache state:** kết quả giữa các run không tương đương.
- **Load generator thiếu capacity:** offered load thực thấp hơn kế hoạch.
- **Không tính rolling deployment/autoscaling:** tổng connection có thể vượt ngân sách.
- **Đặt connectionTimeout dài hơn request deadline:** giữ thread chờ vô ích.
- **Tăng pool để chữa connection leak:** chỉ trì hoãn thời điểm cạn pool.
- **Không kiểm tra lock/plan:** query chậm làm hold time tăng và pool cạn.
- **Không có stop condition:** test có thể gây ảnh hưởng hệ thống dùng chung.
- **Chốt cấu hình từ một lần chạy:** nhiễu và background tasks có thể làm sai kết luận.

## 27. Mẫu báo cáo kết quả thử nghiệm

Một báo cáo đủ để nhóm khác lặp lại nên có:

| Trường | Giá trị cần ghi |
|---|---|
| Run ID | Mã duy nhất của lần thử |
| Application build | Commit/version |
| DBMS/driver | Version/build |
| Pool implementation | Tên và version |
| Instance count | Số process/replica |
| Pool max/min idle | Giá trị cấu hình |
| Offered load | Request/s hoặc mô hình concurrency |
| Query mix | Tỷ lệ read/write/report/batch |
| Dataset | Kích thước và data distribution |
| Warm-up/measurement | Khoảng thời gian |
| Throughput | Completed transaction/s |
| Latency | p50/p95/p99 |
| Pool metrics | Active/idle/pending, acquisition, hold |
| DB metrics | CPU, sessions, lock, I/O, log |
| Query evidence | Fingerprint, plan, rows, buffers |
| Errors | Timeout, rejection, deadlock |
| Decision | Chọn/loại cấu hình và lý do |

Ghi cả kết quả không thành công. Một run cho thấy throughput không tăng khi pool tăng là bằng chứng quan trọng để xác định điểm bão hòa.

## 28. Checklist trước khi chốt pool size

- Đã đo acquisition latency và connection hold time.
- Đã đo p50/p95/p99 thay vì chỉ average.
- Đã phân biệt pool wait với DB lock/I/O/CPU wait.
- Đã kiểm tra query fingerprint và execution plan của workload chính.
- Đã thử tải đọc, ghi, transaction và query dài đại diện.
- Đã dùng cùng dataset, query mix và điều kiện cache giữa các run.
- Đã thử concurrency sweep và pool-size sweep riêng biệt.
- Đã theo dõi offered load, completed throughput và dropped/late requests.
- Đã kiểm tra load generator không phải bottleneck.
- Đã tính tổng pool connection trên tất cả instance và worker.
- Đã tính autoscaling, rolling deployment và failover.
- Đã dành ngân sách cho admin, monitoring và maintenance.
- Đã xác định điểm throughput plateau và latency knee.
- Đã chọn cấu hình đáp ứng SLO với headroom.
- Đã đặt connection timeout theo request deadline.
- Đã kiểm tra connection leak và transaction scope.
- Đã có dashboard và stop condition.
- Đã canary và có cấu hình rollback.

## Kết luận

Điều chỉnh connection pool qua thử nghiệm mức tải đồng thời là bài toán cân bằng giữa hàng đợi ở ứng dụng và năng lực thực thi của database. Pool nhỏ có thể làm request chờ connection dù database còn capacity; pool lớn có thể đưa quá nhiều truy vấn vào database, làm CPU, I/O, lock và tail latency tăng. Kích thước phù hợp phải được xác định bằng acquisition/hold time, throughput, execution plan, wait metrics và SLO.

Hãy tính ngân sách trên toàn cụm, tách thử nghiệm concurrency khỏi pool-size sweep, giữ workload và dữ liệu nhất quán, rồi chọn vùng vận hành nơi throughput đạt mục tiêu mà p95/p99 và tài nguyên vẫn an toàn. Sau khi chọn, triển khai theo canary, quan sát tổng connection và giữ phương án rollback. Nếu database đã bão hòa hoặc connection bị giữ lâu do query/transaction kém, sửa nguyên nhân đó trước khi tăng pool.
