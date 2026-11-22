# Cô lập lỗi và tránh khuếch đại tải khi kho dữ liệu chậm

Khi cơ sở dữ liệu trả lời chậm, ứng dụng Java thường phải giữ kết nối lâu hơn, request HTTP xếp hàng nhiều hơn và số lần timeout tăng. Nếu các tầng tự động thử lại, một đợt chậm ngắn có thể biến thành sự cố rộng: kho dữ liệu càng bận vì phải xử lý nhiều lượt truy vấn giống nhau. **Cô lập lỗi** nhằm giới hạn vùng bị ảnh hưởng và giữ các chức năng quan trọng hoạt động trong khả năng thực tế.

Bài thuộc chương **Lỗi và thử lại** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, tập trung vào tầng persistence trong Java: kiểm soát đồng thời, hạn mức tài nguyên, timeout, retry, kết quả commit chưa rõ, giám sát và phục hồi. Các ví dụ JDBC sử dụng PostgreSQL khi cần mã SQLSTATE cụ thể; các DBMS và thư viện khác có thể có hành vi khác nhau.

## 1. Khi độ trễ tăng, vì sao tải có thể khuếch đại?

Giả sử một service xử lý ổn định **100 yêu cầu/giây**. Một truy vấn thường mất **50 ms**, nên số công việc trung bình đang xử lý khoảng:

\[
L = \lambda \times W = 100 \times 0{,}05 = 5
\]

Đây là trực giác từ **định luật Little** trong một hệ thống ổn định: \(L\) là số công việc đang có, \(\lambda\) là thông lượng hoàn tất và \(W\) là thời gian trung bình của công việc. Khi thời gian tăng lên **500 ms**, cùng thông lượng đó có thể cần khoảng **50 lượt đồng thời**. Phép tính không phải dự báo chính xác khi hệ thống đã bão hòa, bỏ request hoặc mất ổn định.

~~~text
Database chậm
    |
    v
Connection bị giữ lâu -> pool ít connection rảnh
    |
    v
Request chờ -> timeout -> client và service thử lại
    |
    v
SQL/connection tăng, khóa và I/O tranh chấp nhiều hơn
    |
    +----------------------------> Database càng chậm
~~~

Nếu pool của một instance chỉ chứa 12 connection, các request dư phải chờ. Khi nhiều service instance cùng retry, lượng truy vấn và số kết nối tổng có thể lớn hơn nhiều so với nhu cầu nghiệp vụ ban đầu.

**Nguyên tắc:** lúc phụ thuộc suy yếu, phải giới hạn lượng việc mới gửi tới nó; chỉ retry khi vừa **đúng về nghiệp vụ** vừa **có ngân sách tài nguyên**.

## 2. Nhận diện đúng dạng lỗi

| Hiện tượng | Có thể do | Hướng giải quyết |
|---|---|---|
| Query chậm | SQL thiếu chỉ mục, I/O, khóa, tranh chấp CPU | Phân tích kế hoạch truy vấn, giới hạn thời gian và đồng thời |
| Pool acquisition timeout | Hết connection rảnh, leak, transaction dài | Quan sát active/idle/pending, giảm tải và sửa gốc |
| Connection failure | DB restart, failover, socket stale, sự cố mạng | Loại connection hỏng; đánh giá an toàn trước retry |
| Deadlock | Các transaction lấy khóa theo thứ tự xung đột | Rollback, có thể retry toàn transaction; thống nhất thứ tự khóa |
| Serialization failure | Lịch giao dịch đồng thời không được DB chấp nhận | Retry toàn transaction trên dữ liệu mới |
| Lỗi kiểm tra ràng buộc | UNIQUE, CHECK hoặc FOREIGN KEY | Thường báo lỗi nghiệp vụ, không retry nguyên xi |
| COMMIT timeout/mất mạng | Phản hồi bị mất dù server có thể đã commit | Đối soát idempotency key, không ghi lại vô điều kiện |

Với PostgreSQL, **40001** thường là serialization failure, **40P01** là deadlock và nhóm **08xxx** phản ánh vấn đề kết nối. Đặc biệt, **08xxx không chứng minh COMMIT đã thất bại**. Cần phân loại thêm **giai đoạn xảy ra lỗi**: lúc mượn connection, chạy SQL, hay gửi COMMIT.

## 3. Cô lập lỗi là giới hạn những tài nguyên nào?

Cô lập lỗi (*fault isolation*) ngăn một nhóm công việc quá chậm tiêu thụ tất cả tài nguyên dùng chung. Những ngân sách cần xác định gồm:

1. **Số thao tác DB đồng thời:** hạn mức riêng cho API đọc thường, API ghi quan trọng và báo cáo nền.
2. **Số connection:** pool tối đa của mỗi instance và tổng ngân sách session toàn cụm.
3. **Hàng đợi:** lượng request được phép chờ và thời gian chờ tối đa.
4. **Thời gian:** deadline đầu cuối và timeout từng chặng.
5. **Retry:** số lần thử lại, tổng thời gian và tỷ lệ lượt thử thêm so với request gốc.
6. **Tác động nghiệp vụ:** thao tác tài chính cần tính đúng và idempotency, trong khi một số truy vấn danh mục có thể dùng cache trễ.

Một cơ chế không thay thế tất cả cơ chế còn lại. **Bulkhead** giới hạn từ đầu, **deadline** hạn chế thời gian, **circuit breaker** hạn chế gọi khi đã quan sát lỗi, còn **load shedding** chủ động từ chối phần việc vượt sức chứa.

## 4. Bulkhead: ngăn báo cáo nặng làm nghẽn đặt hàng

Giả sử cùng database nhận hai loại công việc: đặt hàng (ngắn, ưu tiên cao) và báo cáo (đọc nhiều, đôi khi chạy lâu). Nếu 20 báo cáo chiếm hết pool 20 connection, API đặt hàng cũng không thể mượn connection.

~~~text
                    Service
                       |
            +----------+----------+
            |                     |
        Đặt hàng              Báo cáo
    giới hạn 8 lượt        giới hạn 3 lượt
            |                     |
      Quota/pool A           Quota/pool B
            \                     /
             +--- PostgreSQL ----+
~~~

**Bulkhead** là giới hạn đồng thời riêng cho nhóm công việc, chẳng hạn semaphore của Java hoặc tính năng bulkhead trong thư viện resilience. Khi hết quota, request mới bị từ chối nhanh hoặc chờ trong hàng đợi rất ngắn có giới hạn.

Hai pool riêng có thể cô lập **khả năng mượn connection**, nhưng **không tách CPU, I/O hay khóa** trên cùng database. Nếu cần tách tài nguyên sâu hơn, có thể cân nhắc replica chuyên đọc hoặc database/workload riêng, sau khi kiểm tra yêu cầu nhất quán.

Với **N instance** và giới hạn mỗi instance **K**, tổng số request đồng thời có thể lên tới **N × K**. Không được coi semaphore trong một JVM là giới hạn toàn cụm.

## 5. Deadline, timeout và ngân sách end-to-end

**Deadline** là thời điểm muộn nhất còn chấp nhận kết quả. **Timeout** là ngân sách dành cho một bước. Ví dụ API có deadline 1.500 ms:

~~~text
Tiếp nhận / xác thực           khoảng 100 ms
Mượn connection                tối đa 300 ms
Thực thi SQL                   tối đa 800 ms
Xử lý kết quả / phản hồi       khoảng 100 ms
Dự phòng + retry               phần thời gian còn lại
~~~

Đây là ngân sách minh họa, không phải các khoản luôn tiêu hết hay bảo đảm phối hợp tự động. Nếu bước đầu chạy lâu hơn dự kiến, bước sau phải căn cứ **thời gian còn lại**.

| Giới hạn | Vai trò | Điểm dễ nhầm |
|---|---|---|
| HTTP/gRPC deadline | Toàn bộ vòng đời request và retries | Không tự động hủy mọi SQL đang chạy |
| Pool connection timeout | Thời gian chờ mượn connection | Khác thời gian thực thi SQL |
| Connect/login timeout | Thời gian mở phiên mới | Khác thời gian kết thúc transaction |
| JDBC query timeout | Giới hạn cho Statement theo driver | Không bảo đảm cắt mọi đợi socket chính xác |
| DB statement/lock timeout | Giới hạn công việc/chờ khóa phía DB | Có thể hủy transaction hoặc statement tùy DBMS |
| Socket read timeout | Thời gian chờ phản hồi mạng | Có thể tạo kết quả ghi chưa rõ phía client |

**Timeout phía client không chứng minh database đã ngừng xử lý câu lệnh.** Với SELECT thuần đọc, có thể bỏ kết quả cũ và chạy lại nếu còn ngân sách. Với thao tác ghi hoặc COMMIT, phải biết chính sách idempotency và trạng thái nghiệp vụ.

Không **sleep** để backoff khi còn giữ connection hoặc transaction. Sau một lỗi an toàn để retry, trước hết phải dọn transaction, đóng tài nguyên rồi mới chờ.

## 6. Connection pool có giới hạn, không phải bộ tăng tốc vô hạn

Các tham số quan trọng của HikariCP thường gồm **maximumPoolSize**, **connectionTimeout**, **validationTimeout**, **maxLifetime**, **keepaliveTime** và **leakDetectionThreshold**.

Ví dụ tham khảo với Spring Boot/HikariCP:

~~~properties
spring.datasource.hikari.maximum-pool-size=12
spring.datasource.hikari.connection-timeout=500
spring.datasource.hikari.validation-timeout=250
spring.datasource.hikari.max-lifetime=1500000
~~~

Các giá trị thời gian HikariCP trên tính bằng **mili giây**. Những giá trị này chỉ minh họa cách đặt hạn mức; cấu hình thật phụ thuộc lượng request, thời gian giữ connection, số instance, DBMS và timeout mạng. Cần tuân thủ các giá trị tối thiểu/quan hệ ràng buộc trong phiên bản pool đang sử dụng.

Nếu có **20 instance**, mỗi pool tối đa **30 connection**, riêng ứng dụng có khả năng tạo **600 session** tới DB, chưa kể job, công cụ quản trị và replication. Khi DB thiếu CPU hoặc I/O, tăng pool có thể làm tải nặng hơn.

Mượn và trả connection bằng **try-with-resources**. Giao dịch dài, quên close ResultSet/Connection hoặc gọi dịch vụ HTTP trong transaction có thể làm pool cạn, ngay cả khi database vẫn khỏe.

## 7. Backpressure, queue hữu hạn và từ chối sớm

Khi database giảm năng lực, không thể nhận mọi request và cho xếp hàng vô hạn mà vẫn có độ trễ hữu hạn.

- **Backpressure:** upstream giảm tốc độ gửi việc khi downstream không theo kịp.
- **Bounded queue:** hàng đợi có sức chứa và thời gian chờ tối đa.
- **Admission control:** chỉ nhận công việc khi còn quota và đủ thời gian để hoàn thành.
- **Load shedding:** từ chối bớt request ít ưu tiên hoặc không còn khả năng phục vụ đúng hạn.

~~~text
Request tới
   |
   +--> Đã quá deadline? --------> Từ chối/timeout
   |
   +--> Hết quota bulkhead? -----> Từ chối nhanh
   |
   +--> Còn quota? -> Mượn connection trong timeout
                          |
                          v
                    Thực thi SQL
                          |
                          v
                 Đóng tài nguyên + trả quota
~~~

Nếu một request chỉ còn **200 ms** nhưng dự kiến chờ pool **800 ms**, việc cho nó thực thi sau khi hết hạn chỉ thêm tải vô ích. Trả **503 Service Unavailable** có thể phù hợp khi dependency đang quá tải; **429 Too Many Requests** thường dùng khi client vượt quota công bố. Nếu có **Retry-After**, giá trị cần có cơ sở; tránh khiến tất cả client retry đồng loạt.

Hàng đợi bền vững cho job nền cần có dung lượng, retention, chính sách xử lý trùng và khả năng tăng/giảm tốc worker. Không dùng một queue trong RAM vô hạn làm nơi chứa việc khi DB chậm.

## 8. Circuit breaker: để phụ thuộc có cơ hội hồi phục

**Circuit breaker** quan sát lỗi/độ chậm và tạm thời từ chối gọi khi phụ thuộc không còn đáp ứng.

~~~mermaid
flowchart LR
    A["CLOSED: gọi bình thường"] -->|"Lỗi/chậm vượt ngưỡng"| B["OPEN: từ chối nhanh"]
    B -->|"Hết thời gian chờ"| C["HALF-OPEN: thăm dò ít lượt"]
    C -->|"Kết quả tốt"| A
    C -->|"Vẫn không ổn"| B
~~~

- **Closed:** chấp nhận request và thu thập kết quả.
- **Open:** fail fast, hạn chế tạo tải lên DB đang lỗi.
- **Half-open:** cho một lượng nhỏ request thử xem DB đã phục hồi hay chưa.

Breaker không sửa query chậm, thiếu index hay thiếu connection. Nó cần cấu hình hợp lý về **cửa sổ thống kê**, số mẫu tối thiểu, lỗi/độ chậm được tính, khoảng open và số probe half-open.

Đừng tính mọi lỗi nghiệp vụ như **UNIQUE violation** thành tín hiệu database hỏng. Lỗi serialization do workload tranh chấp cũng khác outage của network. Breaker nên đi cùng **bulkhead**: bulkhead chặn quá tải từ sớm, còn breaker phản ứng theo tín hiệu lỗi/độ chậm đã quan sát.

## 9. Retry vô tình nhân số truy vấn như thế nào?

Nếu ba tầng **HTTP client**, **application service** và **repository** đều tự thực hiện tối đa **3 attempts** (tính cả lần đầu), một request gốc có thể sinh tối đa:

\[
3 \times 3 \times 3 = 27
\]

lượt thao tác ở tầng thấp, chưa kể retry nội bộ của driver hoặc proxy. Khi database chậm, 27 lượt nỗ lực đó có thể chỉ làm mọi thứ chậm hơn.

Chính sách retry cần rõ:

1. **Một retry owner hoặc ngân sách chung:** tránh các tầng nhân chồng attempts.
2. **Allowlist lỗi:** chỉ thử lại những lỗi có thể khôi phục và an toàn với nghiệp vụ.
3. **Max attempts:** ví dụ tối đa 3 lượt, gồm cả lượt đầu.
4. **Deadline tổng:** không bắt đầu lượt mới khi không còn thời gian hữu ích.
5. **Backoff + jitter:** giảm các đợt retry đồng thời.
6. **Retry budget:** giới hạn tổng số lượt thử thêm theo cửa sổ thời gian hoặc token, không để retry lấn át request mới.
7. **Tôn trọng overload:** nếu bulkhead đã đầy hoặc circuit breaker open, thường nên từ chối thay vì retry ngay trong cùng tầng.

Ví dụ backoff minh họa:

~~~text
Attempt 1: thực thi ngay
Nếu lỗi transient và còn ngân sách: ngẫu nhiên 0..50 ms
Attempt 2: mở transaction mới / chạy lại công việc thích hợp
Nếu vẫn lỗi và còn ngân sách: ngẫu nhiên 0..100 ms
Attempt 3: lượt cuối, thất bại thì trả lỗi có ngữ cảnh
~~~

**Backoff phải chạy ngoài transaction**, sau khi đã đóng connection/statement/result set của attempt trước. Retry budget cần dựa vào năng lực thực của kho dữ liệu; không có tỷ lệ “đúng với mọi ứng dụng”.

### 9.1. Khi nào được retry?

| Công việc | Hướng xử lý |
|---|---|
| SELECT thuần đọc, chưa gửi kết quả một phần cho client | Có thể chạy lại truy vấn trên connection mới, trong deadline |
| Transaction đã bị DB từ chối bằng **40001** | Retry **toàn bộ transaction**, kể cả các lần đọc và quyết định |
| Deadlock đã được xác định (**40P01**) | Có thể retry toàn transaction; đồng thời sửa thứ tự khóa |
| Query chậm do DB đang quá tải | Ưu tiên giới hạn concurrency, giảm tải và sửa truy vấn |
| Vi phạm CHECK/UNIQUE ổn định | Thường trả lỗi nghiệp vụ |
| INSERT/UPDATE hoặc COMMIT có kết quả chưa rõ | Đối soát idempotency key trước khi quyết định thực hiện lại |

Một SELECT gọi stored function có side effect hoặc API đã streaming ra một phần dữ liệu không thể coi là thao tác đọc thuần dễ retry.

## 10. Java JDBC: giới hạn truy vấn đồng thời bằng Semaphore

Giả sử bảng **customers** có cột **id BIGINT PRIMARY KEY** và **name**. Đoạn Java 17 sau dùng **Semaphore** để cho tối đa tám thao tác đọc khách hàng đồng thời trên một instance. Lượt thứ chín bị từ chối trước khi mượn connection.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import java.util.concurrent.Semaphore;
import javax.sql.DataSource;

public final class CustomerReadGateway {
    private final DataSource dataSource;
    private final Semaphore permits = new Semaphore(8);

    public CustomerReadGateway(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<CustomerView> findById(long customerId)
            throws SQLException {
        if (customerId <= 0) {
            throw new IllegalArgumentException("customerId phải dương");
        }
        if (!permits.tryAcquire()) {
            throw new DatabaseBusyException(
                    "Không còn quota truy vấn khách hàng");
        }

        try {
            String sql = "SELECT id, name FROM customers WHERE id = ?";
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement stmt =
                         connection.prepareStatement(sql)) {
                stmt.setLong(1, customerId);
                stmt.setQueryTimeout(1); // giây; hành vi tùy driver

                try (ResultSet rows = stmt.executeQuery()) {
                    if (!rows.next()) {
                        return Optional.empty();
                    }
                    return Optional.of(new CustomerView(
                            rows.getLong("id"), rows.getString("name")));
                }
            }
        } finally {
            // JDBC đã đóng hoặc đã ném exception trước khi trả permit.
            permits.release();
        }
    }

    public record CustomerView(long id, String name) {}

    public static final class DatabaseBusyException
            extends RuntimeException {
        public DatabaseBusyException(String message) {
            super(message);
        }
    }
}
~~~

Điểm cần hiểu:

- **tryAcquire()** không chờ lâu và giúp từ chối sớm khi hết quota.
- Connection, PreparedStatement và ResultSet được đóng trong try-with-resources; **finally** luôn trả permit.
- **PreparedStatement** bind tham số an toàn; không ghép chuỗi SQL với dữ liệu người dùng.
- **setQueryTimeout(1)** không thay thế pool timeout, socket timeout hoặc deadline HTTP.
- Giới hạn tám lượt chỉ có hiệu lực **trong một JVM**. Mười instance vẫn có thể tạo tối đa 80 lượt đọc thuộc nhóm này, ngoài workload khác.
- Nếu dùng cùng pool cho cả đọc và ghi, semaphore không tự dành slot DB cố định cho ghi; các quota và pool phải được thiết kế chung.

Gateway chỉ minh họa **một attempt**. Vòng retry nếu cần nên đặt ở lớp sở hữu chính sách retry, với phân loại lỗi, deadline và ngân sách tổng. **DatabaseBusyException** do bulkhead đầy thường nên được ánh xạ thành lỗi quá tải ngay, tránh retry tức thời khiến quá tải nặng hơn.

## 11. Lỗi SQL và lỗi nghiệp vụ cần biên xử lý khác nhau

Một adapter persistence có thể chuẩn hóa lỗi thành nhóm do ứng dụng định nghĩa:

| Nhóm ứng dụng | Ý nghĩa | Tầng phía trên xử lý |
|---|---|---|
| **DEPENDENCY_OVERLOADED** | Bulkhead/pool hết ngân sách | Trả lỗi tạm thời hoặc giảm cấp |
| **DEPENDENCY_UNAVAILABLE** | Connection/database chưa sẵn sàng | Circuit breaker, chờ phục hồi có giới hạn |
| **TRANSACTION_CONFLICT** | DBMS đã hủy transaction có thể retry | Retry toàn transaction khi an toàn |
| **BUSINESS_CONSTRAINT** | Dữ liệu/ràng buộc nghiệp vụ không hợp lệ | Trả lỗi 4xx phù hợp, không retry mù quáng |
| **UNKNOWN_COMMIT_OUTCOME** | Không biết giao dịch ghi đã commit chưa | Đối soát operation ID |

Các tên nhóm là **quy ước minh họa**, không phải mã SQLSTATE chuẩn. Việc ánh xạ phải dựa trên SQLSTATE, mã vendor, loại transaction và **vị trí xảy ra lỗi**. Không nên bắt mọi **SQLException** rồi coi đó là lỗi có thể retry.

Một API bị giới hạn quota client thường trả **429**. Khi dependency tạm thời quá tải, **503** có thể phù hợp. **504** thường do gateway/proxy đợi upstream quá hạn; mã cụ thể phụ thuộc hợp đồng của hệ thống. Với COMMIT chưa rõ, không trả “giao dịch thất bại” khi chưa có chứng cứ, mà cung cấp **operation_id** để đối soát.

## 12. COMMIT chưa rõ: trường hợp không được thử lại ghi vô điều kiện

Giả sử Java chuyển 100.000 đồng giữa hai tài khoản trong một transaction:

~~~text
BEGIN
UPDATE accounts SET balance = balance - 100000 WHERE id = A;
UPDATE accounts SET balance = balance + 100000 WHERE id = B;
INSERT INTO transfers(operation_id, ...) VALUES ('PAY-001', ...);
COMMIT
~~~

Database có thể **đã commit**, sau đó kết nối bị mất trước khi Java nhận phản hồi. Nếu client thấy timeout rồi gửi lại bằng **operation_id mới**, người dùng có thể bị trừ tiền hai lần.

Quy trình an toàn cần:

1. **operation_id/idempotency key ổn định** cho cùng một nghiệp vụ.
2. Ràng buộc **UNIQUE** và lưu operation_id **trong cùng transaction** với thay đổi dữ liệu.
3. Sau lỗi COMMIT không rõ, đối soát trên nguồn dữ liệu có thẩm quyền, kiểm tra kết quả và dữ liệu khớp.
4. Nếu operation_id tồn tại với dữ liệu đúng, trả kết quả trước đó; nếu khác dữ liệu, báo xung đột.
5. Nếu chưa thấy bản ghi nhưng transaction cũ có thể còn chạy hoặc replica trễ, không kết luận ngay chưa commit; cần giao thức đồng bộ/đối soát phù hợp.

**Rollback sau lỗi kết nối không thể hoàn tác một COMMIT đã thật sự hoàn tất.** Chạy lại toàn transaction chỉ phù hợp khi DBMS xác nhận lần trước bị hủy, ví dụ serialization failure, và nghiệp vụ được thiết kế idempotent.

Gửi email, gọi cổng thanh toán hay publish message trong một attempt có thể retry sẽ tạo side effect trùng. Có thể dùng **transactional outbox**: lưu ý định gửi trong cùng giao dịch, một worker sau commit xử lý, phía nhận vẫn cần khả năng idempotent.

## 13. Graceful degradation và tránh cache stampede

Khi database chậm, một số chức năng **đọc** có thể giảm cấp mà vẫn đáp ứng hợp đồng dữ liệu:

| Chức năng | Có thể giảm cấp thế nào? | Giới hạn cần công bố |
|---|---|---|
| Danh mục sản phẩm | Trả cache hợp lệ hoặc dữ liệu stale có kiểm soát | Thời gian tối đa được phép trễ |
| Dashboard thống kê | Trả snapshot gần nhất | Hiển thị thời điểm dữ liệu |
| Báo cáo nền | Hoãn tác vụ qua queue bền vững có giới hạn | Chỉ báo “đang xử lý”, không báo hoàn tất |
| Kiểm tra số dư để chuyển tiền | Không dùng cache cũ để quyết định cho phép ghi | Cần nguồn có thẩm quyền và transaction |
| Tạo đơn hàng | Từ chối có kiểm soát hoặc nhận xử lý bất đồng bộ nếu giao thức hỗ trợ | Không nói đã tạo đơn khi chưa commit |

**Fallback không được bịa dữ liệu thành công.** Trả danh sách rỗng thay cho lỗi DB timeout có thể khiến ứng dụng tưởng rằng thật sự không có bản ghi và đưa ra quyết định sai.

Cache cũng có thể gây **cache stampede**: khi nhiều khóa đồng loạt hết hạn, hàng nghìn request quay về DB. Có thể kết hợp TTL có jitter, single-flight per key, giới hạn số lượt refresh và stale-while-revalidate khi hợp đồng cho phép.

## 14. Quan sát để phát hiện khuếch đại tải sớm

Các metric cần theo dõi không chỉ là số HTTP 5xx:

| Metric gợi ý | Tín hiệu |
|---|---|
| **db_query_duration_p95/p99** | Tail latency truy vấn tăng |
| **db_pool_active / idle / pending** | Pool gần cạn và hàng đợi lớn |
| **db_pool_acquire_duration** | Thời gian mượn connection tăng |
| **bulkhead_rejected_total** | Số lượt bị từ chối sớm |
| **circuit_breaker_state** | Breaker open/half-open/closed |
| **db_retry_attempts_total** | Số nỗ lực SQL, gồm lượt thử thêm |
| **db_retry_exhausted_total** | Request hết ngân sách retry |
| **db_timeout_total{stage}** | Phân loại pool, query, lock, socket, request |
| **transaction_duration** | Transaction giữ connection/khóa quá lâu |
| **commit_outcome_unknown_total** | Các nghiệp vụ cần đối soát |

Đây là **tên metric gợi ý**, không phải mặc định của mọi thư viện. Không đưa mỗi customer_id hay SQL có tham số nhạy cảm vào metric label vì vừa tạo cardinality lớn vừa có thể làm lộ dữ liệu.

PostgreSQL có các truy vấn chẩn đoán hữu ích:

~~~sql
SELECT state, COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state;

SELECT pid, state,
       now() - xact_start AS transaction_age,
       wait_event_type, wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;

SELECT datname, xact_commit, xact_rollback, deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

**xact_rollback** không chỉ đếm serialization failure. Để đo đúng retry storm, cần ghi lỗi SQLSTATE và số lần retry tại ứng dụng. Quyền xem các session và mức chi tiết thống kê phụ thuộc quyền truy cập/phiên bản PostgreSQL.

### Khi điều tra sự cố

Xem thời điểm nào tăng trước: query p99, lock wait, I/O, pool pending hay retry attempts. Kiểm tra xem job nền, báo cáo dài hoặc connection leak có chiếm pool không. Nếu chỉ tăng timeout và maximumPoolSize mà không xác định nút thắt, hệ thống có thể cho **nhiều request hơn nằm chờ lâu hơn** rồi mới thất bại.

## 15. Kiểm thử tình huống xuống cấp

Thử các kịch bản sau trong **staging tách biệt, dữ liệu giả**, với tải đại diện:

1. Tăng độ trễ SQL từ 50 ms lên 500 ms; xác nhận số công việc in-flight và độ dài hàng đợi vẫn bị giới hạn.
2. Chạy báo cáo dài cùng API ghi; xác nhận báo cáo không chiếm hết tài nguyên của chức năng ưu tiên.
3. Cho database tạm thời từ chối connection mới; xác nhận breaker/load shedding không tạo cơn bão kết nối khi DB phục hồi.
4. Gây tranh chấp tạo 40001/40P01; kiểm tra chỉ retry **toàn transaction**, hữu hạn, với backoff.
5. Mô phỏng mất phản hồi COMMIT ở môi trường test; xác nhận operation_id ngăn ghi nghiệp vụ trùng.
6. Làm nhiều cache key hết hạn; kiểm tra không có stampede gây đột biến request tới DB.
7. Giữ connection lâu có kiểm soát; kiểm tra pool acquire timeout, metric và cách hệ thống từ chối sớm.

**Tiêu chí đạt:** không sai bất biến nghiệp vụ, không có queue vô hạn, số lượt retry trong ngân sách, latency p95/p99 và lượng request bị từ chối được quan sát, dịch vụ phục hồi sau khi DB trở lại bình thường. Không cần ép tất cả request đều thành công nếu điều đó gây sập hệ thống.

## 16. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Retry mọi SQLException | Lặp lỗi nghiệp vụ và tăng tải | Phân loại theo DBMS, nghiệp vụ và giai đoạn lỗi |
| Nhiều tầng retry độc lập | Số attempts nhân lên | Một retry owner/ngân sách chung |
| Tăng pool vô hạn | Thêm session và tranh chấp DB | Giới hạn theo tổng workload toàn cụm |
| Hàng đợi không giới hạn | Memory/thread bị giữ, nhiều request quá deadline | Bounded queue và load shedding |
| Sleep trong transaction | Giữ connection/khóa không cần thiết | Dọn connection trước backoff |
| Chỉ tăng timeout | Request chờ lâu, pool cạn nặng hơn | Phân tích nút thắt và đặt deadline |
| Tính UNIQUE violation vào circuit breaker | Từ chối sai khi DB vẫn khỏe | Chọn tín hiệu đúng phản ánh phụ thuộc |
| Semaphore per-instance được coi là quota toàn cụm | Tổng tải vẫn vượt năng lực DB | Tính theo số instance và các workload |
| Trả cache cũ để quyết định chuyển tiền | Vi phạm tính đúng | Dùng transaction/nguồn có thẩm quyền |
| Retry sau COMMIT timeout | Có thể thực hiện nghiệp vụ hai lần | Idempotency và đối soát |
| Không đo retry attempts | Che giấu tải nhân đôi | Theo dõi attempts/request và retry budget |

## 17. Bài tập tự kiểm tra

**Bài 1.** API nhận ổn định 80 request/giây, thời gian trung bình tăng từ 0,05 s lên 0,4 s. Số công việc in-flight xấp xỉ thay đổi ra sao?

*Gợi ý:* từ khoảng \(80 \times 0{,}05 = 4\) lên \(80 \times 0{,}4 = 32\), trong giả định hệ thống ổn định.

**Bài 2.** Ba tầng cùng retry tối đa ba attempts. Một request có thể gây bao nhiêu lượt ở tầng cuối?

*Gợi ý:* \(3^3=27\). Cần chọn retry owner/ngân sách tổng.

**Bài 3.** Pool có 20 connection, 20 báo cáo dài chiếm hết. API thanh toán không mượn được connection. Nêu hai phương án cô lập.

*Gợi ý:* bulkhead/quota riêng cho report và pool/workload phân tách có tổng ngân sách DB hợp lý; đồng thời tối ưu/timeout báo cáo.

**Bài 4.** Circuit breaker mở vì ứng dụng nhận nhiều lỗi UNIQUE do input trùng. Có hợp lý không?

*Gợi ý:* không nên xem lỗi ràng buộc nghiệp vụ là bằng chứng DB hỏng.

**Bài 5.** SQLSTATE 40001 xuất hiện ở COMMIT. Có thể retry riêng INSERT cuối cùng không?

*Gợi ý:* phải retry từ đầu transaction, gồm những lần đọc/kiểm tra tạo quyết định.

**Bài 6.** Mạng ngắt sau khi gửi COMMIT chuyển tiền. Client định thử lại với operation_id mới. Vấn đề gì?

*Gợi ý:* commit cũ có thể đã thành công; cần đối soát bằng operation_id cũ.

**Bài 7.** Có cache danh mục sản phẩm trễ hai phút và cache số dư trễ hai phút. Trường hợp nào có thể dùng để giảm tải?

*Gợi ý:* danh mục nếu hợp đồng cho phép stale; không dùng số dư cũ làm căn cứ cho phép chuyển tiền.

**Bài 8.** HTTP 200 vẫn gần 100%, nhưng số attempts/request tăng lên 2,5 và p99 tăng mạnh. Có thể xem hệ thống vẫn khỏe không?

*Gợi ý:* không; đây là dấu hiệu khuếch đại tải và tài nguyên đang tiến gần giới hạn, cần tìm nguyên nhân và giảm retry.

## 18. Ghi nhớ và áp dụng

Khi kho dữ liệu chậm, hãy **giới hạn công việc mới**, giữ hàng đợi hữu hạn và bảo vệ tài nguyên bằng **bulkhead, deadline, load shedding và circuit breaker**. Retry có ích cho lỗi thật sự tạm thời nhưng phải có **ngân sách, backoff, jitter và một ranh giới retry rõ ràng**. Ngay cả những request cuối cùng thành công cũng có thể gây tải nhân lên nếu phía dưới phải chạy SQL nhiều lần.

Trong tầng persistence Java, đóng tài nguyên đúng cách, giữ transaction ngắn và phân loại lỗi theo DBMS. Với transaction đã bị hủy, retry **toàn bộ nghiệp vụ** khi an toàn; với kết quả COMMIT chưa rõ, **đối soát idempotency key** trước khi quyết định thực hiện lại. Dùng cache hoặc kết quả stale chỉ khi hợp đồng dữ liệu cho phép.

Một hệ thống biết từ chối sớm những công việc không thể hoàn tất và tự giảm tải khi DB yếu thường phục hồi ổn định hơn hệ thống cố nhận mọi request rồi retry liên tục.
