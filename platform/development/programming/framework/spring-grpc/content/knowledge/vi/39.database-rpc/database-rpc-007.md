# Timeout database nhỏ hơn deadline RPC

## 1. Vì sao database timeout phải nằm trong deadline RPC?

Trong **SPRING_GRPC**, một RPC thường thực hiện nhiều bước: nhận và validate request, chờ connection từ pool, chạy query, chờ lock, commit transaction, dựng response rồi gửi qua HTTP/2. Client đặt deadline cho toàn bộ lời gọi. Nếu query hoặc pool tiếp tục chờ lâu hơn thời gian client cho phép, server tiêu tốn tài nguyên cho một request mà caller đã không còn chờ kết quả.

Database timeout cần nhỏ hơn phần thời gian còn lại của RPC để server có cơ hội dừng database work, rollback transaction nếu chưa commit, giải phóng connection và trả lỗi có kiểm soát trước khi deadline tổng hết. Đây là một phần của ngân sách thời gian đầu cuối, không phải một con số cố định áp dụng giống nhau cho mọi request.

Bài tập trung vào cách phối hợp:

- RPC deadline ở client và remaining deadline ở server.
- HikariCP connection acquisition timeout.
- Database lock timeout, statement/query timeout và transaction timeout.
- Khoảng dự phòng cho validation, commit, mapping response và network.
- Cancellation, driver query cancellation và transaction rollback.
- Ánh xạ timeout thành gRPC status, retry và idempotency.
- Metrics và integration tests để chứng minh timeout hoạt động.

## 2. Deadline RPC là giới hạn thời gian đầu cuối

Deadline biểu diễn thời điểm tuyệt đối mà RPC không còn được phép tiếp tục chờ. Khi thời gian trôi qua, phần ngân sách còn lại giảm dần; server không nên bắt đầu một bước database mới nếu không còn đủ thời gian cho bước đó và phần xử lý sau query.

Ví dụ client đặt deadline 800 ms. Server nhận request sau khi đã mất 70 ms truyền tải và queueing; ngân sách server còn khoảng 730 ms. Nếu server dành 500 ms chờ pool, 400 ms cho query và thêm thời gian commit/serialize, database work đã vượt deadline trước khi response có thể hoàn tất.

Không nên coi deadline là timeout riêng cho từng bước. Mỗi dependency cần dùng phần ngân sách còn lại của cùng RPC, hoặc một giới hạn dịch vụ thấp hơn.

Ví dụ client stub:

```java
OrderReply reply = blockingStub
    .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
    .getOrder(request);
```

Không tạo deadline mới vô hạn ở mỗi tầng. Khi gọi service khác, truyền remaining budget hoặc deadline phù hợp để tổng thời gian downstream vẫn nằm trong deadline đầu cuối.

## 3. Phân bổ timeout theo tầng

Một mô hình ngân sách:

```text
RPC deadline (giới hạn ngoài)
  ├─ decode / validate / application overhead
  ├─ connection pool acquisition
  ├─ database transaction
  │    ├─ lock wait
  │    ├─ statement/query execution
  │    └─ commit
  └─ response mapping / serialization / network margin
```

Gọi R là thời gian còn lại khi server bắt đầu xử lý. Cần dành một phần cho phần xử lý ngoài database và response:

```text
Database budget < R - application/response reserve
```

Bên trong database budget:

- Pool acquisition phải kết thúc đủ sớm để còn thời gian chạy query.
- Lock timeout nên nhỏ hơn statement timeout nếu database hỗ trợ cấu hình riêng.
- Statement/query timeout phải nằm trong database budget.
- Transaction timeout là giới hạn cho toàn bộ transaction, không nên lớn hơn ngân sách còn lại dành cho transaction.
- Commit và cleanup cần có thời gian dự phòng; đừng đặt query timeout bằng đúng RPC remaining time.

Các timeout có thể lồng nhau hoặc cùng đo trên một khoảng thời gian; không cộng máy móc lock timeout và statement timeout nếu database tính lock wait bên trong statement timeout. Hãy hiểu semantics của database/driver đang dùng.

## 4. Đọc remaining deadline từ gRPC Context

Trong gRPC Java server, deadline hiện tại có thể đọc qua Context:

```java
Deadline deadline = Context.current().getDeadline();

if (deadline == null) {
    // Áp dụng service-level cap nếu RPC không có deadline.
}

long remainingNanos =
    deadline.timeRemaining(TimeUnit.NANOSECONDS);
```

Không giả định mọi client đều gửi deadline. Dịch vụ nên có giới hạn thời gian nội bộ làm trần trên, kể cả khi client không đặt deadline. Nếu deadline đã hết hoặc phần ngân sách còn lại không đủ, fail fast trước khi lấy connection hoặc bắt đầu query.

Ví dụ helper tính query budget:

```java
long remaining = deadline.timeRemaining(TimeUnit.NANOSECONDS);
long reserve = TimeUnit.MILLISECONDS.toNanos(80);
long queryBudget = remaining - reserve;

if (queryBudget < TimeUnit.SECONDS.toNanos(1)) {
    throw Status.DEADLINE_EXCEEDED
        .withDescription("Insufficient time for database operation")
        .asRuntimeException();
}

int queryTimeoutSeconds =
    (int) TimeUnit.NANOSECONDS.toSeconds(queryBudget);
```

JDBC Statement.setQueryTimeout nhận đơn vị giây; giá trị 0 thường có nghĩa không giới hạn. Vì vậy, nếu ngân sách còn dưới một giây, không làm tròn xuống 0 rồi vô tình tắt timeout. Hãy fail fast hoặc dùng timeout độ phân giải nhỏ hơn do database/driver hỗ trợ.

Tính lại remaining deadline ngay trước khi thực thi query, sau khi đã lấy connection. Thời gian chờ pool cũng tiêu thụ ngân sách RPC.

## 5. HikariCP connection acquisition timeout

Trước khi query chạy, ứng dụng có thể phải chờ connection trong HikariCP. Property connection-timeout giới hạn thời gian chờ mượn connection từ pool.

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 500
      validation-timeout: 250
```

Các giá trị trên chỉ minh họa. HikariCP connectionTimeout là cấu hình của pool, không tự động thay đổi theo deadline từng RPC. Vì vậy:

- Chọn giá trị bảo thủ dựa trên ngân sách chờ pool thường gặp.
- Kiểm tra remaining deadline trước khi bắt đầu thao tác cần connection.
- Đặt connectionTimeout đủ nhỏ để không giữ thread quá lâu.
- Sau khi lấy connection, tính lại ngân sách trước query.
- Theo dõi pending threads và acquisition time; nếu pending tăng liên tục, tìm nguyên nhân pool/database thay vì chỉ tăng timeout.

Nếu workload có nhiều RPC deadline rất khác nhau, cần thiết kế guard trước khi acquisition và có thể cần cơ chế acquisition budget-aware riêng. Không tuyên bố một cấu hình HikariCP tĩnh tự hiểu deadline của từng call.

## 6. Đặt JDBC query timeout theo remaining budget

Với JDBC, Statement.setQueryTimeout giới hạn thời gian thực thi statement theo giây. Có thể áp dụng trong StatementCreator của JdbcTemplate; callback tạo statement được gọi sau khi JdbcTemplate đã lấy connection:

```java
public List<OrderRow> findOrders(String customerId) {
    return jdbcTemplate.query(connection -> {
        PreparedStatement statement = connection.prepareStatement(
            "SELECT id, status FROM orders WHERE customer_id = ?"
        );
        statement.setString(1, customerId);

        int timeoutSeconds = queryTimeoutPolicy
            .remainingBudgetSeconds();
        statement.setQueryTimeout(timeoutSeconds);

        return statement;
    }, orderRowMapper);
}
```

remainingBudgetSeconds() cần đọc deadline hiện tại, trừ phần dự phòng và áp dụng service cap. Nếu còn quá ít thời gian, nó phải từ chối thực thi thay vì trả 0.

JDBC timeout là yêu cầu tới driver; mức độ hủy query và thời điểm trả connection phụ thuộc driver/database. Cần xác minh với driver production. Với JPA, query timeout hint và việc áp dụng transaction timeout phụ thuộc provider; kiểm thử thực tế thay vì giả định mọi query đều bị giới hạn giống nhau.

## 7. Database-side statement timeout và lock timeout

Database-side timeout bảo vệ hệ thống ngay cả khi application thread bị treo hoặc driver cancellation không hoạt động như mong đợi.

Ví dụ PostgreSQL hỗ trợ statement_timeout và lock_timeout. Có thể đặt giới hạn theo transaction:

```sql
BEGIN;
SET LOCAL lock_timeout = '150ms';
SET LOCAL statement_timeout = '600ms';

SELECT id, status
FROM orders
WHERE customer_id = 'customer-17';

COMMIT;
```

SET LOCAL chỉ có hiệu lực trong transaction hiện tại và tự hết hiệu lực khi transaction kết thúc; điều này an toàn hơn việc thay đổi session setting lâu dài trên connection pooled. Tránh nối chuỗi SQL từ dữ liệu người dùng; dùng parameterized query hoặc API phù hợp của database để thiết lập giá trị động.

Lock timeout nên nhỏ hơn statement timeout nếu muốn phát hiện lock contention sớm. Statement timeout là trần cho câu lệnh; transaction timeout và RPC deadline vẫn cần giới hạn tổng thể.

Tên setting và đơn vị khác nhau theo database. Ví dụ PostgreSQL, MySQL, SQL Server và Oracle có cơ chế khác nhau; phải dùng tài liệu/driver của database triển khai.

## 8. Spring transaction timeout là lớp bảo vệ bổ sung

Spring cho phép đặt timeout ở transaction boundary:

```java
@Transactional(timeout = 2)
public OrderResult updateOrder(UpdateOrderCommand command) {
    // Database work
}
```

Timeout này thường được khai báo tĩnh theo method và là giới hạn bổ sung cho transaction. Nó không tự động đọc deadline gRPC của từng request. Việc timeout được áp dụng xuống statement phụ thuộc transaction manager, DataSourceUtils/JdbcTemplate và JPA provider.

Không dùng @Transactional(timeout=2) như bằng chứng rằng mọi JDBC operation chắc chắn bị hủy sau đúng hai giây. Kết hợp transaction timeout với statement timeout/database-side timeout và test trên stack thực tế.

Nếu cần transaction budget động theo remaining deadline, có thể tạo transaction definition riêng cho invocation đó, nhưng tránh sửa một TransactionTemplate dùng chung giữa nhiều thread. Cách triển khai phải bảo đảm transaction manager thực sự áp dụng timeout cho resource đang dùng.

## 9. Để lại thời gian cho commit và response

Một lỗi cấu hình là đặt statement timeout bằng đúng RPC deadline. Query có thể hoàn tất sát thời điểm deadline, nhưng server vẫn cần:

- Flush/commit transaction.
- Xử lý constraint hoặc deferred database work.
- Đóng/giải phóng resource.
- Chuyển domain result thành Protobuf.
- Gửi response và terminal signal.

Vì vậy, query budget cần thấp hơn remaining RPC budget một khoảng reserve. Reserve phụ thuộc latency thực tế; đo p95/p99 của commit, mapping và response thay vì chọn tùy tiện.

Với transaction có nhiều statement, không cấp lại toàn bộ deadline cho từng query. Tổng transaction budget phải giảm dần theo thời gian đã tiêu thụ. Một request có 4 query không được phép chạy mỗi query 700 ms nếu toàn RPC chỉ còn 1 giây.

## 10. Cancellation không tự động dừng database query

Khi client deadline hết hoặc client cancel, gRPC server context bị cancel. Tuy nhiên, điều đó không đảm bảo JDBC statement đã dừng ngay hoặc transaction đã rollback tức thì.

Cần kết hợp:

- Kiểm tra Context cancellation trước các bước database mới.
- Query/statement timeout ở JDBC và database.
- Transaction timeout để giới hạn transaction scope.
- Driver/database hỗ trợ cancel statement.
- Rollback khi query timeout hoặc lỗi làm transaction thất bại.
- Không bắt timeout exception rồi trả kết quả bình thường nếu cần rollback.

Nếu công việc chạy ở executor khác, phải truyền cancellation/deadline context phù hợp và mở transaction ở worker thread. Spring imperative transaction thường gắn với thread hiện tại; không giả định transaction tự truyền sang async callback.

## 11. Commit timeout và kết quả không chắc chắn

Nếu client nhận DEADLINE_EXCEEDED, không thể kết luận database chắc chắn chưa commit. Có thể server đã commit thành công nhưng response bị mất; cũng có thể query/commit chưa hoàn tất và transaction rollback.

Đối với command có side effect:

- Dùng idempotency key ổn định cho cùng ý định nghiệp vụ.
- Lưu idempotency record và business update trong cùng transaction.
- Khi retry cùng key, trả lại kết quả đã commit thay vì chạy side effect lần nữa.
- Nếu trạng thái outcome chưa rõ, cung cấp operation/status query hoặc retry cùng key.
- Với event bên ngoài, ghi outbox trong cùng transaction.

Không retry mù quáng một command tạo payment/order chỉ vì client thấy timeout. Timeout mô tả thời gian chờ của caller, không phải bằng chứng rollback.

## 12. Ánh xạ timeout thành gRPC status

Status nên phản ánh nguyên nhân mà caller có thể hành động:

| Tình huống | Status thường dùng | Ghi chú |
| --- | --- | --- |
| Deadline của RPC đã hết | DEADLINE_EXCEEDED | Caller hết ngân sách thời gian |
| Caller chủ động hủy | CANCELLED | Không đồng nghĩa transaction trước đó chưa commit |
| Pool tạm thời không cấp được connection | UNAVAILABLE hoặc RESOURCE_EXHAUSTED | Chọn theo contract quá tải/quota |
| Database query vượt budget của operation | DEADLINE_EXCEEDED | Ghi rõ timeout nội bộ trong log |
| Optimistic locking conflict | ABORTED | Đọc lại và retry toàn bộ use case |
| Request không hợp lệ | INVALID_ARGUMENT | Không retry nguyên request |

Không trả SQL, connection string, stack trace hoặc thông tin nội bộ trong status description. Log server cần correlation ID, RPC method, remaining budget tại từng bước và loại timeout để phân tích.

## 13. Quan sát và kiểm thử timeout hierarchy

Thu thập metrics riêng cho từng tầng:

- RPC deadline remaining khi server bắt đầu xử lý.
- Thời gian chờ connection và acquisition timeout count.
- Query/statement duration và query timeout count.
- Lock wait, transaction duration, commit duration và rollback count.
- Số request bị cancel hoặc hết deadline.
- Số query còn chạy sau khi caller đã cancel.
- Pool active/idle/pending và database CPU/I/O/lock metrics.

Kiểm thử qua gRPC server thật và database cùng loại production khi có thể:

| Test | Điều cần xác nhận |
| --- | --- |
| RPC deadline ngắn | Server không bắt đầu query khi ngân sách không đủ |
| Pool cạn | Acquisition wait bị giới hạn và status đúng |
| Query chậm | Statement/database timeout dừng query trong budget |
| Lock contention | Lock timeout nhỏ hơn statement timeout |
| Commit gần deadline | Query vẫn để lại reserve cho commit/response |
| Client cancel | Query được hủy theo khả năng driver/database; transaction rollback nếu chưa commit |
| Không có client deadline | Service-level cap vẫn giới hạn thời gian |
| Retry sau timeout | Idempotency ngăn side effect trùng |
| Streaming RPC | Mỗi database operation dùng remaining budget mới, không dùng lại budget cũ |

Load test cần có query chậm, lock contention và pool saturation. Chỉ test một query timeout riêng lẻ không chứng minh toàn bộ timeout hierarchy hoạt động.

## 14. Checklist review

- Client đặt deadline phù hợp với SLO của RPC.
- Server đọc remaining deadline từ gRPC Context và có service-level cap khi không có deadline.
- Có reserve cho commit, response mapping và network.
- Pool acquisition timeout phù hợp ngân sách chờ; biết rằng HikariCP timeout là cấu hình pool tĩnh.
- Query/statement timeout được áp dụng sau khi lấy connection và sát thời điểm thực thi.
- Lock timeout nhỏ hơn statement timeout khi database hỗ trợ.
- Transaction timeout là lớp bảo vệ bổ sung, không thay thế query timeout.
- Database-side timeout được cấu hình và reset an toàn trên pooled connection.
- Cancellation được phối hợp với driver/database; không giả định gRPC tự hủy JDBC.
- Timeout exception dẫn tới rollback khi transaction chưa commit.
- Command có side effect dùng idempotency; event dùng outbox.
- Status mapping phân biệt DEADLINE_EXCEEDED, CANCELLED, UNAVAILABLE và ABORTED.
- Metrics đo riêng RPC, pool wait, query, lock và transaction duration.
- Integration tests xác minh timeout trên database/driver thực tế.

Trong **SPRING_GRPC**, deadline RPC là ngân sách đầu cuối; pool acquisition, lock wait, query và transaction phải tiêu thụ các phần nhỏ hơn của ngân sách đó, đồng thời để lại thời gian cho commit và response. Kết hợp timeout ở HikariCP, JDBC/driver, database và Spring transaction theo đúng semantics của từng tầng. Khi timeout xảy ra, xử lý cancellation và rollback có kiểm soát, đồng thời dùng idempotency để bảo vệ command nếu commit đã thành công nhưng response bị mất.
