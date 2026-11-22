# Kiểm tra kết nối hỏng và phục hồi sau gián đoạn

Một ứng dụng Java có thể đang chạy ổn định rồi đột nhiên không lấy được JDBC Connection, gặp lỗi khi thực thi SQL, hoặc mất kết nối ngay lúc **COMMIT**. Nguyên nhân có thể là database khởi động lại, mạng chập chờn, firewall đóng kết nối nhàn rỗi, pool trả về phiên đã hỏng, hết số connection được phép, hoặc transaction giữ tài nguyên quá lâu. Cách xử lý đúng phụ thuộc **giao dịch đang ở giai đoạn nào** và **ta có biết kết quả trên cơ sở dữ liệu hay không**.

Bài học thuộc chương **Kết nối và tài nguyên** trong mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ biết kiểm tra connection bằng JDBC và connection pool, phân biệt các loại timeout/lỗi, tổ chức reconnect, retry an toàn, xử lý transaction có kết quả chưa rõ, đồng thời theo dõi tài nguyên để giảm gián đoạn ở tầng persistence. Ví dụ dùng Java JDBC và PostgreSQL; các tham số pool/driver được ghi rõ là minh họa vì hành vi cụ thể thay đổi theo phiên bản và DBMS.

## 1. Kết nối JDBC là gì và có thể hỏng ở đâu?

**Connection** trong JDBC là phiên giao tiếp logic giữa ứng dụng và hệ quản trị cơ sở dữ liệu. Nó thường gắn với một kết nối mạng và trạng thái phiên ở server: transaction hiện tại, isolation level, session variables, temporary tables, prepared statements, khóa hoặc cursor đang mở.

~~~text
HTTP request
      |
      v
Java service / repository
      |
      v
DataSource / Connection Pool
      |          +-- connection 1 -> DB session 1
      |          +-- connection 2 -> DB session 2
      |          +-- connection 3 -> DB session 3
      v
Network / proxy / load balancer
      |
      v
PostgreSQL primary / database server
      |
      v
Transaction log + data files
~~~

Khi ứng dụng gọi **dataSource.getConnection()** từ pool, nó thường **mượn** một connection được quản lý; khi gọi **close()**, nó thường **trả** connection cho pool thay vì đóng socket vật lý ngay. Pool quyết định tái sử dụng hay loại bỏ connection bị hỏng theo kết quả kiểm tra và chính sách của pool.

Điểm cần phân biệt:

- **Connection còn sống:** có thể giao tiếp với DBMS tại thời điểm kiểm tra.
- **Transaction còn hợp lệ:** server vẫn công nhận transaction hiện tại và cho phép tiếp tục. Một connection sống vẫn có thể chứa transaction đã ở trạng thái lỗi.
- **Yêu cầu nghiệp vụ đã hoàn tất:** transaction đã commit và đáp ứng điều kiện nghiệp vụ. Việc connection bị hỏng không tự trả lời câu hỏi này.
- **Database sẵn sàng phục vụ:** một connection thành công không chứng minh mọi truy vấn, mọi replica hoặc mọi chức năng của DB đều khỏe.

Một cơ chế kiểm tra connection chỉ giúp phát hiện lỗi ở **một thời điểm**, không thể bảo đảm mạng sẽ không hỏng ngay sau đó.

## 2. Các dạng gián đoạn và dấu hiệu thường gặp

| Tình huống | Biểu hiện tại Java | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|---|
| DBMS restart hoặc failover | Connection cũ báo lỗi I/O hoặc bị đóng | Server session cũ mất | Bỏ connection lỗi, đợi endpoint phục hồi, mượn connection mới |
| Firewall/NAT hết hạn phiên nhàn rỗi | Câu SQL đầu tiên sau thời gian idle gặp lỗi | Socket stale, kết nối bị đóng ngầm | Pool validation/keepalive phù hợp, cấu hình vòng đời |
| Mạng mất trong lúc query | Timeout, socket reset, SQL exception | Kết quả query có thể không về đủ | Dọn tài nguyên, phân loại read/write trước khi retry |
| Mạng mất đúng lúc COMMIT | Client không nhận được xác nhận | Commit có thể đã xảy ra ở server | **Đối soát operation ID**, không retry ghi vô điều kiện |
| Pool cạn connection | getConnection() chờ rồi timeout | Transaction dài, connection leak, tải tăng | Đo active/idle/pending, sửa giữ connection quá lâu |
| DB từ chối connection mới | Lỗi giới hạn connection, xác thực hoặc startup | Server quá tải, cấu hình hoặc quyền | Khắc phục nguyên nhân; retry có giới hạn nếu lỗi tạm thời |
| Giao dịch bị hủy do deadlock/serialization | SQLSTATE xung đột, transaction aborted | Lịch thực thi đồng thời không được chấp nhận | Rollback và retry **toàn bộ** transaction nếu an toàn |

**Connection lỗi**, **pool timeout** và **SQL timeout** là ba lớp sự cố khác nhau. Chúng có thể xuất hiện đồng thời nhưng cần được đo và phân loại riêng.

### 2.1. Khởi động lại database và failover

Khi PostgreSQL primary restart, các backend session đang mở thường kết thúc. Connection cũ của ứng dụng có thể vẫn hiện diện như một object trong pool cho đến khi pool hoặc một lần I/O tiếp theo phát hiện nó không còn dùng được. Nếu hạ tầng thay primary bằng standby được promote, kết nối mới có thể phải tới endpoint mới; DNS, proxy hoặc driver đa host phải hỗ trợ cập nhật tuyến phù hợp.

Một transaction đang mở trên primary cũ **không được tiếp tục** trên connection mới. Sau failover phải xác định transaction đã commit hay chưa, mở transaction mới cho công việc tiếp theo và xem khả năng mất dữ liệu dựa trên cấu hình replication thực tế.

### 2.2. Connection nhàn rỗi bị đóng ở tầng mạng

Một firewall hoặc load balancer có thể đóng socket lâu không hoạt động mà ứng dụng chưa biết ngay. Khi pool trả lại connection đó, SQL đầu tiên có thể lỗi. Pool hiện đại thường kiểm tra connection khi cho mượn nếu cần, quản lý tuổi thọ, và có thể keepalive với connection idle.

Cần phân biệt việc một socket stale bị bỏ đi với tình huống **database thực sự không sẵn sàng**. Nếu chỉ một connection đã chết, mượn connection mới có thể giải quyết; nếu server chưa phục hồi, việc mở thêm hàng nghìn connection sẽ làm tình hình tệ hơn.

## 3. Kiểm tra connection hỏng bằng JDBC

### 3.1. isClosed() chỉ kiểm tra trạng thái ở phía JDBC

~~~java
boolean closed = connection.isClosed();
~~~

**isClosed()** cho biết object JDBC đã được đánh dấu đóng hoặc không còn sử dụng theo cách driver nhận biết. Nó **không phải phép thử mạng đầy đủ**. Một socket mất kết nối ở phía server có thể chưa bị driver phát hiện ngay; **isClosed() == false** không đồng nghĩa query tiếp theo chắc chắn chạy được.

### 3.2. isValid(timeoutSeconds) để xác nhận có thể giao tiếp

JDBC cung cấp:

~~~java
try (Connection connection = dataSource.getConnection()) {
    boolean usable = connection.isValid(2); // tối đa khoảng 2 giây theo JDBC API
    if (!usable) {
        throw new SQLException("Connection không hợp lệ");
    }
}
~~~

**Connection.isValid(int timeoutSeconds)** cho driver cơ hội kiểm tra trạng thái kết nối với DBMS. Tham số thời gian là **giây**, phải không âm; driver có thể dùng yêu cầu protocol thích hợp hoặc cơ chế khác. Hàm có thể trả **false** hoặc ném SQLException nếu kiểm tra thất bại; chi tiết về timeout và việc thực thi phụ thuộc driver.

**Không nên gọi isValid() trước mọi câu SQL** như một bảo đảm tuyệt đối: sau khi isValid trả true, mạng vẫn có thể ngắt trước câu lệnh tiếp theo. Đây là vấn đề **time of check / time of use**. Thông thường, để pool quản lý validation và vẫn bắt SQLException khi thao tác thật.

### 3.3. Validation query

Một số pool/driver cũ hoặc cấu hình đặc thù dùng câu lệnh nhẹ để kiểm tra:

~~~sql
SELECT 1;
~~~

Một lệnh SELECT kiểm tra được server có trả lời, nhưng vẫn là **một round trip**, không bảo đảm transaction đang mở là hợp lệ và không chứng minh mọi bảng/ổ đĩa đều khỏe. Nếu driver hỗ trợ **isValid()** tốt, nhiều pool có thể sử dụng cách kiểm tra của JDBC thay cho validation query tùy chỉnh.

### 3.4. Không chạy health check trong giao dịch nghiệp vụ đang lỗi

Một transaction PostgreSQL có thể bị đánh dấu **aborted** sau một lỗi SQL. Connection có thể còn sống, nhưng câu SQL mới trong transaction ấy bị từ chối cho tới khi **ROLLBACK**. Việc thử **SELECT 1** trên đúng transaction lỗi có thể không cho kết quả mong muốn; nó không chứng minh máy chủ hỏng.

Quy trình đúng là phát hiện lỗi, rollback hoặc loại bỏ connection theo tình huống, rồi **bắt đầu transaction mới** nếu cần. Pool nên nhận về một connection đã được dọn transaction, isolation và session state theo hợp đồng của nó.

## 4. Phân loại lỗi và chọn hành động

Java JDBC báo lỗi thông qua **SQLException**, trong đó có **getSQLState()**, **getErrorCode()** và các subclass như **SQLTransientConnectionException**, **SQLNonTransientConnectionException**. Không có một tiêu chí duy nhất chính xác với mọi driver và DBMS.

### 4.1. Mã SQLSTATE quan trọng

| SQLSTATE hoặc nhóm | Ý nghĩa thường gặp trong PostgreSQL | Hành động gợi ý |
|---|---|---|
| **08xxx** | Lớp lỗi kết nối, ví dụ không thể thiết lập hoặc mất connection | Bỏ connection hỏng, xác định vị trí thất bại; chỉ retry theo tính an toàn của nghiệp vụ |
| **08001** | SQL client không thiết lập được kết nối | Kiểm tra endpoint, mạng, DNS, giới hạn connection, lỗi xác thực liên quan |
| **08006** | Connection failure | Không tiếp tục transaction trên connection này |
| **40001** | Serialization failure | Rollback/dọn transaction và retry **toàn bộ** giao dịch nếu còn ngân sách |
| **40P01** | Deadlock detected | Thường retry toàn transaction; đồng thời điều chỉnh thứ tự khóa |
| **57014** | Query canceled, có thể do statement timeout hoặc yêu cầu hủy | Kiểm tra deadline/nguyên nhân, không mặc định retry |
| **57P01** | Admin shutdown (PostgreSQL) | Có thể xảy ra khi DB dừng; kiểm tra tình trạng dịch vụ trước retry |
| **53300** | Too many connections | Giảm tải, kiểm tra pool/giới hạn; thêm retry ồ ạt sẽ phản tác dụng |
| **28xxx** | Lỗi xác thực/quyền | Sửa credential/quyền, không retry tự động như lỗi mạng |

Lưu ý **08xxx** mô tả lỗi kết nối, **không tự cho biết SQL hoặc COMMIT có xảy ra ở server hay chưa**. Ví dụ COMMIT có thể thành công trước khi phản hồi bị mất, nên cùng mã lỗi 08006 vẫn phải áp dụng quy trình đối soát cho thao tác ghi.

Với DBMS khác, mã vendor và các trạng thái có thể khác. Adapter persistence có thể đóng gói việc phân loại lỗi cho từng driver; tránh rải các phép so chuỗi SQLSTATE trong mọi repository.

### 4.2. Phân biệt ba nhóm quyết định

1. **Thất bại trước khi có transaction hoặc SQL nào được gửi:** có thể thử lấy connection mới sau chờ hữu hạn nếu không có tác dụng nghiệp vụ đã xảy ra.
2. **Giao dịch bị DB xác nhận hủy:** ví dụ lỗi serialization được phân loại rõ; có thể chạy lại toàn transaction với điều kiện không có side effect ngoài DB không thể hoàn tác.
3. **Thất bại trong lúc thao tác đã gửi nhưng kết quả không rõ:** đặc biệt COMMIT, INSERT hoặc cập nhật có thể đã chạy; cần idempotency và đối soát, không mặc định tự gửi lại.

**Lỗi tạm thời về hạ tầng không đồng nghĩa thao tác nghiệp vụ được phép chạy lại vô điều kiện.**

## 5. Timeout ở từng tầng khác nhau

Một request có thể gặp nhiều cơ chế timeout; đặt một giá trị duy nhất cho tất cả là chưa đủ.

~~~text
HTTP request deadline
   └── Connection pool acquisition timeout
         └── Connect / login timeout khi mở socket mới
               └── JDBC statement/query timeout
                     └── DB lock wait / statement execution
                           └── Network socket read timeout
~~~

Các timeout ở trên **không nhất thiết chạy lồng nhau theo đúng từng mili giây**; đây là sơ đồ quan hệ để định vị nơi có thể bị chờ.

| Timeout | Bảo vệ điều gì | Cần lưu ý |
|---|---|---|
| **Pool connectionTimeout** | Giới hạn thời gian chờ mượn một connection từ pool | Hết thời gian thường nói về pool bận hoặc không tạo được connection kịp |
| **Connect/login timeout** | Giới hạn thời gian thiết lập kết nối, đăng nhập | Có thể phụ thuộc driver, DNS, TLS và OS |
| **Statement/query timeout** | Giới hạn thời gian chạy SQL theo JDBC/DBMS | Không phải driver nào cũng bảo đảm ngắt mọi loại chờ socket |
| **Socket read timeout** | Giới hạn chờ phản hồi qua kết nối mạng | Timeout có thể khiến tình trạng kết quả phía server không rõ |
| **Lock timeout** | Giới hạn thời gian chờ khóa tại database | Khác với tổng thời gian transaction |
| **Transaction timeout** | Giới hạn thời gian hoặc tuổi của transaction theo framework/DB | Transaction dài vẫn tiêu tốn connection và có thể giữ khóa |
| **HTTP deadline** | Giới hạn thời gian xử lý yêu cầu đầu cuối | Tổng các lần retry/backoff phải nằm trong ngân sách |

Đối với PostgreSQL có thể cân nhắc cấu hình **statement_timeout**, **lock_timeout**, **idle_in_transaction_session_timeout**, **transaction_timeout** (tùy phiên bản). Với JDBC, **Statement.setQueryTimeout(seconds)** là một cơ chế cấp câu lệnh; nó không thay cho timeout kết nối hoặc deadline từ HTTP.

Chọn các giá trị theo SLO, độ trễ thực tế và độ dài nghiệp vụ. Nếu API chỉ có ngân sách 2 giây thì ba lượt thử, mỗi lượt query 3 giây cộng backoff là chính sách không hợp lý.

## 6. Connection pool: xác thực, loại bỏ và tạo lại kết nối

Một pool như **HikariCP** thường đảm nhận mượn/trả connection, giới hạn số kết nối đồng thời, kiểm tra trạng thái và quản lý vòng đời. Ứng dụng vẫn chịu trách nhiệm đóng tài nguyên JDBC đúng cách và xác định transaction nào còn an toàn để thử lại.

### 6.1. Vòng đời connection khi hệ thống khỏe

~~~text
Tạo connection mới -> kiểm tra -> trạng thái idle trong pool
                            |
Request mượn <--------------+
   |
   +-> SQL / transaction
   |
   +-> close() trên wrapper JDBC
            |
            +-> Pool dọn trạng thái/kiểm tra theo chính sách
                      |
              +-------+-------+
              |               |
         Trả về idle       Hủy connection hỏng/quá tuổi
                                  |
                            Tạo connection mới khi cần
~~~

**close()** trong try-with-resources là điều kiện cơ bản để tránh connection leak. Với pool, nó trả lại tài nguyên logic; pool có thể quyết định giữ, reset hoặc đóng connection vật lý.

### 6.2. Những tham số cần hiểu

| Tham số (ví dụ HikariCP) | Mục đích | Lựa chọn cần cân nhắc |
|---|---|---|
| **maximumPoolSize** | Chặn số connection đồng thời từ một instance | Phụ thuộc giới hạn DB, số instance, tải và thời gian giữ connection |
| **connectionTimeout** | Thời gian chờ mượn connection | Phải phù hợp deadline API và khả năng xử lý sự cố |
| **validationTimeout** | Ngân sách xác nhận connection còn hợp lệ | Nên ngắn hơn thời gian lấy connection theo ràng buộc của pool |
| **maxLifetime** | Tuổi tối đa của connection trong pool | Nên nhỏ hơn giới hạn tuổi do mạng/DB áp đặt, có biên an toàn |
| **idleTimeout** | Giới hạn thời gian connection dư thừa được giữ idle | Không tự có hiệu lực với mọi cấu hình số connection tối thiểu |
| **keepaliveTime** | Kiểm tra định kỳ các connection idle khi đủ điều kiện | Có thêm traffic; phải phù hợp timeout mạng và giới hạn pool |
| **leakDetectionThreshold** | Hỗ trợ chẩn đoán connection giữ quá lâu | Cảnh báo không đồng nghĩa leak thật; transaction hợp lệ dài cũng có thể gây cảnh báo |

Ví dụ **chỉ để minh họa tham số**, không phải cấu hình tối ưu chung:

~~~properties
# Spring Boot + HikariCP: cần kiểm tra phiên bản và hạ tầng cụ thể.
spring.datasource.hikari.maximum-pool-size=12
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.validation-timeout=2000
spring.datasource.hikari.max-lifetime=1500000
spring.datasource.hikari.keepalive-time=300000
~~~

Các thời gian trên tính bằng **mili giây** theo cấu hình HikariCP. **maxLifetime=1.500.000 ms** là 25 phút, **keepaliveTime=300.000 ms** là 5 phút. Giá trị chỉ có ý nghĩa khi so với tuổi thọ connection ở DB, timeout của proxy/NAT và số lượng instance cùng kết nối tới một database.

**Không nhân đôi mù quáng maximumPoolSize theo số CPU.** Nếu có 20 instance ứng dụng, mỗi instance có pool 30 thì chỉ riêng ứng dụng có thể tạo tới 600 connection, vượt khả năng của database. Giới hạn DB cần trừ connection quản trị, replication, job nền và phần mềm khác.

### 6.3. Connection lỗi nên bị loại bỏ khi nào?

Một kết nối có lỗi mạng/I/O khiến protocol hoặc transaction state không còn tin cậy thường cần được **loại khỏi vòng tái sử dụng**. Pool/driver thường nhận diện các ngoại lệ đủ nghiêm trọng và hủy connection vật lý. Ứng dụng không nên tự viết logic đóng socket nội bộ hoặc giả định bất kỳ SQLException nào cũng làm connection không thể dùng tiếp.

**Validation trước khi mượn** giảm xác suất gặp socket stale, nhưng không thay cho **exception handling khi query**. Với gián đoạn mạng giữa transaction, connection mới cũng không kế thừa transaction cũ.

### 6.4. Lưu ý về trạng thái phiên

Một connection có thể chứa trạng thái phiên mà request trước đã đặt: **autoCommit**, isolation level, read-only, schema/search path, temporary objects hoặc biến phiên. Sau khi trả vào pool, các trạng thái phải được reset theo hợp đồng pool và cách ứng dụng quản lý transaction.

Không truyền một JDBC Connection giữa nhiều thread yêu cầu rồi cùng thực thi statement; hãy để mỗi transaction/request mượn và trả connection theo phạm vi được thiết kế. PreparedStatement và ResultSet phải được đóng kịp thời.

## 7. Java JDBC: thử lại an toàn cho một truy vấn chỉ đọc

Với một SELECT thuần đọc, không có tác dụng ngoài cơ sở dữ liệu và kết quả có thể lấy lại, việc gặp lỗi connection trước khi nhận kết quả thường có thể xử lý bằng cách **bỏ attempt**, mượn connection mới và chạy lại truy vấn. Retry vẫn cần **giới hạn**, **backoff có jitter** và **deadline**.

Ví dụ dưới đây giả định bảng **orders** có các cột **id**, **customer_id**, **created_at**; DataSource đã được cấu hình pool và driver. Dùng JDBC 4.x:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;
import javax.sql.DataSource;

public final class OrderReader {
    private static final int MAX_ATTEMPTS = 3;
    private final DataSource dataSource;

    public OrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<Long> findRecentOrderIds(long customerId)
            throws SQLException, InterruptedException {
        if (customerId <= 0) {
            throw new IllegalArgumentException("customerId phải dương");
        }

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                return queryOnce(customerId);
            } catch (SQLException failure) {
                if (!isConnectionFailure(failure)
                        || attempt == MAX_ATTEMPTS) {
                    throw failure;
                }

                // Mỗi lần thử đã đóng Connection/Statement/ResultSet.
                // Chờ ở ngoài transaction và không giữ connection.
                long capMillis = Math.min(250L, 50L << (attempt - 1));
                long delay = ThreadLocalRandom.current()
                        .nextLong(capMillis + 1);
                try {
                    Thread.sleep(delay);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw interrupted;
                }
            }
        }
        throw new IllegalStateException("Không thể tới nhánh này");
    }

    private List<Long> queryOnce(long customerId) throws SQLException {
        String sql = "SELECT id FROM orders "
                + "WHERE customer_id = ? "
                + "ORDER BY created_at DESC, id DESC LIMIT 20";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            // Timeout câu SQL; socket và pool cần cấu hình riêng.
            statement.setQueryTimeout(3);
            statement.setLong(1, customerId);

            List<Long> ids = new ArrayList<>();
            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    ids.add(rows.getLong("id"));
                }
            }
            return ids;
        }
    }

    private static boolean isConnectionFailure(SQLException exception) {
        // Ví dụ phạm vi hẹp cho driver dùng SQLSTATE chuẩn.
        String state = exception.getSQLState();
        return state != null && state.startsWith("08");
    }
}
~~~

**Tại sao ví dụ an toàn để retry hơn một lệnh ghi?** SELECT này chỉ trả danh sách ID và không thực hiện thay đổi dữ liệu hoặc side effect. Khi mất connection, kết quả từ attempt đó bị bỏ; lần mới tạo toàn bộ ResultSet từ đầu. **Không được mặc định mọi SELECT là thuần đọc**: một số hàm hoặc thủ tục trong SQL có thể ghi dữ liệu, và truy vấn đọc snapshot khác có thể trả kết quả mới hơn.

Hạn chế của ví dụ:

- Nó chỉ nhận diện lỗi class **08** theo SQLSTATE; một số driver/pool còn phát tín hiệu transient khác. Bản production cần adapter phân loại theo DBMS và thêm ngân sách thời gian toàn request.
- Nó không xử lý giao dịch ghi, COMMIT không rõ trạng thái hoặc lỗi SQL không thuộc lớp connection. Lỗi **40001** ở transaction ghi đòi hỏi retry toàn transaction theo chính sách riêng.
- **statement.setQueryTimeout(3)** không bảo đảm mọi chờ mạng sẽ kết thúc sau đúng 3 giây. Cần cấu hình socket timeout/login timeout và deadline của request.
- **Thread.sleep** là ví dụ cho xử lý đồng bộ; trong hệ thống reactive/non-blocking nên dùng cơ chế delay phù hợp thay vì giữ worker thread chờ.
- Sau một failover, một request đọc lại có thể thấy dữ liệu khác phiên trước. Nếu hợp đồng API yêu cầu đọc nhất quán theo snapshot hoặc read-your-writes, phải bổ sung chính sách phân tuyến và consistency.

### 7.1. Không dùng reconnect để tiếp tục transaction đang dở

Sai lầm:

~~~text
Connection A:
  BEGIN
  UPDATE accounts SET balance = balance - 100 WHERE id = 1
  -> mất connection

Connection B (mới):
  UPDATE accounts SET balance = balance + 100 WHERE id = 2
  COMMIT
~~~

Hai lệnh đã thực thi trên hai transaction khác nhau. Không có bảo đảm nguyên tử giữa chúng. Phải xác định transaction A đã kết thúc ra sao, rồi **chạy lại cả nghiệp vụ bằng transaction mới** nếu an toàn. Nếu mất connection ở giai đoạn COMMIT, cần đối soát trước khi thử lại.

## 8. Giao dịch ghi: kết quả COMMIT không xác định

Đây là tình huống cần xử lý cẩn thận nhất.

~~~text
Java service                  Database
    |                            |
    |--- INSERT order ---------->|
    |<-- SQL thành công ----------|
    |--- COMMIT ----------------->|
    |                      COMMIT hoàn tất
    |                     (ghi transaction)
    |       X mất kết nối         |
    |<-- phản hồi không tới ------X
    |
    +--> SQLException: Java KHÔNG BIẾT commit đã thành công hay chưa
~~~

Một exception từ **connection.commit()** **không chứng minh transaction chưa commit**. Có thể DB đã commit và mất phản hồi; cũng có thể giao dịch đã bị hủy. **Rollback trên connection còn lại hoặc connection mới không thể hoàn tác một commit đã thực sự hoàn tất.**

Do đó phải phân biệt:

- **Trạng thái chắc chắn chưa gửi thao tác ghi:** có thể retry sau reconnect theo chính sách.
- **DBMS trả rõ một lỗi transaction đã bị hủy** (ví dụ serialization failure): rollback/dọn transaction và retry toàn nghiệp vụ nếu an toàn.
- **Lỗi I/O/timeout ở hoặc sau COMMIT:** **unknown outcome**; đối soát nghiệp vụ trên nguồn có thẩm quyền trước khi quyết định.

### 8.1. Thiết kế idempotency với operation_id

Một mẫu thường dùng cho tạo đơn hàng:

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation_id VARCHAR(80) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

**operation_id** phải ổn định cho **cùng một yêu cầu**, kể cả khi client gửi lại sau timeout. Ghi operation_id **trong cùng transaction** với thay đổi dữ liệu chính.

Sau reconnect, dùng một connection mới đọc từ **primary hoặc nguồn đọc có bảo đảm thích hợp**:

~~~sql
SELECT id, customer_id, amount
FROM orders
WHERE operation_id = ?;
~~~

Ba tình huống cần giải quyết:

1. **Đã có hàng và dữ liệu khớp yêu cầu:** trả kết quả của thao tác đã hoàn tất; tránh chèn lần hai.
2. **Có hàng nhưng dữ liệu không khớp:** báo xung đột khóa idempotency; không coi là cùng yêu cầu.
3. **Chưa thấy hàng:** chưa được phép kết luận ngay DB chắc chắn chưa commit, nếu request cũ còn đang giải quyết hoặc replica trễ; phải làm rõ trạng thái transaction cũ, dùng ràng buộc UNIQUE và chính sách đối soát/timeout phù hợp.

Đối với hệ thống thanh toán hoặc chuyển tiền, operation_id cũng cần gắn với hệ thống bên ngoài và trạng thái nghiệp vụ để tránh thực hiện lại tác dụng đã thành công.

### 8.2. Không đánh đồng “reconnect” và “retry”

**Reconnect** chỉ tạo kênh giao tiếp mới. **Retry** là quyết định chạy lại công việc nghiệp vụ. Một hệ thống có thể reconnect thành công nhưng **không được phép** chạy lại thao tác trừ tiền nếu commit trước đó chưa được xác minh.

Nếu transaction có phát email, publish message hoặc gọi HTTP API ngoài DB, các tác dụng ấy **không tự rollback** theo giao dịch database. Dùng **transactional outbox**, idempotency key của đối tác hoặc quy trình bù trừ phù hợp thay vì phát lại side effect trong mỗi attempt.

## 9. Phục hồi sau database restart, failover hoặc mất mạng

Một ứng dụng resilient nên có quy trình phục hồi rõ ràng hơn việc chỉ lặp vô hạn **getConnection()**.

~~~mermaid
flowchart TD
    A["Phát hiện lỗi connection hoặc pool timeout"] --> B["Ghi nhận loại lỗi và vị trí thất bại"]
    B --> C["Đóng tài nguyên, loại connection lỗi theo pool"]
    C --> D{"DB endpoint đã sẵn sàng?"}
    D -->|Chưa| E["Giới hạn tải + backoff/circuit breaker"]
    E --> D
    D -->|Rồi| F["Mượn connection mới"]
    F --> G{"Yêu cầu là loại gì?"}
    G -->|SELECT thuần đọc| H["Retry có giới hạn theo deadline"]
    G -->|Transaction chắc chắn đã bị hủy| I["Tạo transaction mới, chạy lại toàn bộ"]
    G -->|Ghi/COMMIT chưa rõ kết quả| J["Đối soát operation_id"]
    H --> K["Trả kết quả hoặc lỗi cuối cùng"]
    I --> K
    J --> K
~~~

Sơ đồ tóm tắt quyết định; trong production không chạy vòng kiểm tra DB liên tục không giới hạn. Thay vì mỗi request đều tự dò database theo nhịp riêng, ứng dụng có thể dùng **circuit breaker**, health probe và chính sách giới hạn concurrency để tránh tạo bão kết nối trong lúc DB đang khởi động lại.

### 9.1. Trạng thái startup/recovery của DBMS

DB có thể mở cổng TCP nhưng chưa sẵn sàng xử lý giao dịch ghi vì vẫn đang recovery hoặc node hiện là standby read-only. Kiểm tra endpoint, vai trò node và truy vấn có quyền phù hợp trước khi chuyển traffic ghi vào.

Trong PostgreSQL, có thể kiểm tra vai trò instance với:

~~~sql
SELECT pg_is_in_recovery() AS is_in_recovery;
~~~

- **TRUE**: instance đang ở chế độ recovery/standby và thông thường không nhận ghi dữ liệu ứng dụng.
- **FALSE**: instance không ở recovery; vẫn phải kiểm tra quyền, tính sẵn sàng của DB mục tiêu và chính sách định tuyến trước khi coi nó là primary phù hợp.

Không dùng mỗi kết quả này để xây thuật toán failover; việc xác định primary hợp lệ và tránh split-brain là nhiệm vụ của cơ chế điều phối cluster.

### 9.2. Chuyển hướng sau failover

Khi primary thay đổi, pool phải dần thay các connection trỏ tới node cũ bằng connection tới endpoint mới. Có thể cần cấu hình DNS/driver/proxy, thời gian TTL và timeout phù hợp; không phải mọi driver tự phát hiện cluster topology theo cùng một cách.

Dù kết nối tới primary mới thành công, **transaction trước failover không di chuyển theo**. Với replication bất đồng bộ, primary mới có thể chưa nhận các transaction vừa commit ở primary cũ; RPO thực tế phụ thuộc kiến trúc. Những nghiệp vụ quan trọng phải đối soát idempotency với hệ thống có thẩm quyền.

### 9.3. Tránh reconnect storm

Giả sử 50 instance cùng có pool tối đa 20 connection. Khi DB quay lại, nếu tất cả mở đủ pool và retry ngay, database có thể nhận tới **1.000 lượt kết nối** cùng thời điểm.

Các biện pháp cần cân nhắc:

- Giới hạn kích thước pool trên mỗi instance theo tổng ngân sách DB.
- Dùng backoff có jitter cho thao tác retry và tạo kết nối, theo cơ chế được thư viện cho phép.
- Giới hạn số request đồng thời chờ DB; từ chối sớm khi dependency vẫn chưa phục hồi.
- Dùng circuit breaker có half-open probing hạn chế để tránh mọi request cùng thử.
- Theo dõi tỷ lệ kết nối mới, pool pending và lỗi too many connections.
- Kiểm tra connection leak và transaction giữ connection quá lâu trước khi chỉ tăng pool.

## 10. Connection leak và tình trạng “DB hỏng giả”

Không phải lần nào **getConnection() timeout** cũng do mạng hỏng. Một số lỗi phổ biến của ứng dụng:

~~~java
// Sai: method mượn connection nhưng quên đóng khi có exception.
Connection connection = dataSource.getConnection();
PreparedStatement statement = connection.prepareStatement(sql);
ResultSet resultSet = statement.executeQuery();
// Nếu exception xảy ra, nhiều tài nguyên có thể không được trả.
~~~

Sửa bằng **try-with-resources**:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Xử lý từng dòng; không giữ ResultSet sang request khác.
        }
    }
}
~~~

Đoạn sau giả định **sql** là chuỗi SQL hợp lệ đã được chuẩn bị và các parameter cần thiết đã được bind nếu có. Trong code thực tế, dùng **PreparedStatement** với placeholder cho dữ liệu đầu vào, tránh ghép trực tiếp giá trị người dùng vào câu SQL.

**Connection leak** có thể do quên close, giữ ResultSet khi streaming response lâu, hoặc transaction chạy xuyên qua bước gọi HTTP chậm. Khi pool hết tài nguyên, những request mới liên tục timeout dù PostgreSQL vẫn hoạt động bình thường.

### 10.1. Giao dịch dài và idle in transaction

Một connection ở trạng thái **idle in transaction** có thể vẫn giữ transaction, snapshot và đôi khi khóa. Nếu nhiều session như vậy tồn tại, pool có thể cạn và DB phải giữ phiên bản dữ liệu lâu hơn cần thiết.

Quy tắc thực hành: đặt transaction quanh **phần đọc/ghi cần tính nguyên tử**, không mở transaction từ đầu request rồi giữ nó qua xử lý JSON, gọi service ngoài, chờ người dùng hoặc upload file.

## 11. Kiểm tra sự cố ở tầng ứng dụng và PostgreSQL

Để tìm đúng nguyên nhân, cần dữ liệu từ cả Java/pool và DBMS.

### 11.1. Metric ứng dụng

| Chỉ số | Dấu hiệu |
|---|---|
| **pool.active / pool.idle / pool.pending** | Active cao, idle bằng 0 và pending tăng: pool đang cạn |
| **connection.acquire.duration** | Thời gian chờ mượn connection tăng |
| **connection.creation.failures** | DB không nhận connection mới hoặc mạng/auth hỏng |
| **connection.validation.failures** | Nhiều connection stale được phát hiện |
| **jdbc.query.duration** | SQL chậm khác với chậm lấy connection |
| **jdbc.sqlstate.errors{class}** | Phân loại lỗi 08, 40, 53, 57... |
| **transaction.commit.unknown_total** | Số lần COMMIT không xác định kết quả |
| **transaction.retry_total{reason}** | Số lần thử lại theo nguyên nhân, không chỉ kết quả cuối |
| **pool.connection.hold.duration** | Connection bị giữ quá lâu, có thể do transaction dài hoặc leak |

Tên metric là **gợi ý thiết kế**, không phải những metric mặc định mà mọi thư viện xuất ra đúng chính tả này. Khi log lỗi, ghi mã SQLSTATE, thao tác, thời điểm, pool/DB endpoint và correlation ID; tránh log password, connection string chứa credentials hoặc tham số nhạy cảm.

### 11.2. Các câu SQL quan sát PostgreSQL

Xem giới hạn số connection:

~~~sql
SHOW max_connections;
~~~

Đếm session theo trạng thái trong database hiện tại:

~~~sql
SELECT state, COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state
ORDER BY sessions DESC;
~~~

Xem transaction đang mở lâu:

~~~sql
SELECT pid,
       state,
       now() - xact_start AS transaction_age,
       wait_event_type,
       wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Xem tổng số giao dịch và lỗi deadlock ở mức database:

~~~sql
SELECT datname, xact_commit, xact_rollback, deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

**xact_rollback** gồm nhiều nguyên nhân, không chỉ lỗi connection hay serialization. **deadlocks** không phải số connection bị mất. Cần kết hợp với metric SQLSTATE và log ở ứng dụng.

**Lưu ý về quyền:** trong PostgreSQL, khả năng xem thông tin phiên của người dùng khác phụ thuộc quyền và phiên bản; chỉ hiển thị những thông tin được cấp phép.

### 11.3. Quy trình chẩn đoán nhanh

1. **Phân loại lần thất bại:** getConnection, executeQuery/executeUpdate, commit hay close.
2. **Kiểm tra phạm vi:** lỗi ở một pod, một vùng mạng hay mọi instance?
3. **Xem pool:** active/idle/pending và thời gian giữ connection.
4. **Xem DBMS:** có restart/recovery/failover, quá nhiều session, khóa hoặc truy vấn dài không?
5. **Kiểm tra hạ tầng:** DNS, TLS, firewall idle timeout, proxy, routing và giới hạn mạng.
6. **Đánh giá tác động dữ liệu:** có request ghi hoặc COMMIT chưa rõ trạng thái cần đối soát không?
7. **Khôi phục có kiểm soát:** sửa nguyên nhân, xác nhận endpoint mới và retry theo ngân sách.
8. **Theo dõi sau sự cố:** tỷ lệ lỗi giảm, pool ổn định, request idempotent không nhân đôi tác dụng.

## 12. Tình huống thực tế để chọn phương án

### Tình huống A — Connection cũ chết sau 30 phút idle

**Hiện tượng:** request đầu tiên sau giờ nghỉ gặp SQLSTATE 08006; request tiếp theo bình thường.

**Phân tích:** có thể do firewall/NAT hoặc DB đóng idle socket. Kiểm tra timeout giữa pool, DB và mạng. Cho pool validation hoặc keepalive/giới hạn tuổi thọ connection phù hợp. Vẫn bắt lỗi I/O trong SQL vì validation không loại bỏ được mọi race.

**Tránh:** cứ mỗi request lại gọi SELECT 1 hai lần hoặc tăng pool mà không tìm nguyên nhân.

### Tình huống B — Pool cạn nhưng PostgreSQL vẫn sống

**Hiện tượng:** getConnection timeout, DB không restart; pool active bằng maximumPoolSize, pending tăng.

**Phân tích:** đo transaction/connection hold duration, tìm leak hoặc truy vấn lâu, cân nhắc tăng năng lực DB/điều chỉnh concurrency. Có thể tăng pool sau khi đo tổng số connection từ mọi instance, nhưng nếu root cause là leak, tăng pool chỉ trì hoãn sự cố.

### Tình huống C — Failover lúc tạo đơn hàng

**Hiện tượng:** Java gọi COMMIT rồi nhận SQLException, endpoint mới hoạt động sau vài giây.

**Phân tích:** không thể tự khẳng định transaction thất bại. Dùng operation_id đã lưu trong cùng transaction, kết nối primary có thẩm quyền mới để đối soát, kiểm tra dữ liệu khớp. Nếu replication bất đồng bộ, cần tính tới RPO và chính sách xử lý request trên cluster mới.

**Tránh:** tạo order với operation_id mới để “thử lại cho chắc”.

### Tình huống D — Deadlock trong chuyển tiền

**Hiện tượng:** SQLSTATE 40P01, hai giao dịch chờ hai hàng theo thứ tự ngược nhau.

**Phân tích:** đây là xung đột transaction, chưa chắc là connection hỏng. Cần rollback và chạy lại **toàn bộ transaction** nếu không có side effect gây trùng, đồng thời chuẩn hóa thứ tự lấy khóa để giảm deadlock.

**Tránh:** đóng hàng loạt connection chỉ vì một deadlock hoặc retry riêng lệnh cộng tiền cuối cùng.

### Tình huống E — Truy vấn chậm hơn HTTP deadline

**Hiện tượng:** người dùng thấy timeout, nhưng DB vẫn tiếp tục thực thi SQL một lúc sau đó.

**Phân tích:** timeout client không nhất thiết hủy thành công SQL phía server ngay lập tức. Xem statement timeout, socket timeout, transaction timeout và quy trình cancel. Với thao tác ghi, sau timeout phải đánh giá kết quả chưa rõ và đối soát thay vì gửi lại một cách vô điều kiện.

## 13. Bảo mật và khả năng phục hồi

Khi hệ thống reconnect, không dùng cách khắc phục “tạm thời” như tắt TLS, bỏ kiểm tra chứng chỉ, cấp quyền database quá rộng hoặc đặt password trong mã nguồn. Lỗi xác thực không thuộc nhóm cần retry vô hạn.

Một ứng dụng tốt cần:

- Cấu hình credentials từ cơ chế secrets phù hợp, hỗ trợ rotation.
- Bảo vệ kết nối bằng TLS khi mô hình triển khai yêu cầu; kiểm tra chứng chỉ/hostname theo policy.
- Ghi log lỗi mà không để lộ URI có password hoặc dữ liệu truy vấn nhạy cảm.
- Định nghĩa tài khoản/role tối thiểu quyền cho từng service.
- Bảo đảm pool và driver nạp lại cấu hình hợp lệ khi credentials thay đổi.
- Dùng operation ID để đối soát nhưng không để lộ dữ liệu khách hàng trong khóa hoặc log.
- Có kế hoạch xử lý khi DB đang recovery hoặc không thể truy cập nguồn có thẩm quyền: trả lỗi tạm thời, giữ thông tin để đối soát, không công bố thành công giả.

Lỗi kết nối cũng là một tín hiệu hạ tầng; làm quá nhiều thao tác không giới hạn khi hệ thống chưa phục hồi có thể gây **retry storm**, làm hỏng khả năng phục hồi chung.

## 14. Bài tập tự kiểm tra

### Bài 1 — isClosed và isValid

Một Connection trả **isClosed() == false**. Kỹ sư kết luận mọi SQL tiếp theo sẽ chạy ổn. Lập luận có đúng không?

**Gợi ý:** không. isClosed chủ yếu phản ánh trạng thái driver biết được; socket có thể đã stale. isValid hoặc pool validation kiểm tra tốt hơn tại thời điểm đó, nhưng kết nối vẫn có thể hỏng sau kiểm tra.

### Bài 2 — Connection pool timeout

Ứng dụng báo timeout khi gọi **getConnection()**. PostgreSQL vẫn cho truy vấn trực tiếp nhanh, nhưng pool active đạt tối đa và pending liên tục tăng. Nên kiểm tra gì trước?

**Gợi ý:** tìm connection giữ lâu, transaction idle, ResultSet/Connection chưa close hoặc request chờ dịch vụ ngoài trong transaction. Không mặc định nguyên nhân là DB đã mất kết nối.

### Bài 3 — Retry sau SQLSTATE 08006

Một SELECT thuần đọc gặp 08006; request còn thời gian và chính sách cho phép ba attempts. Có thể làm gì?

**Gợi ý:** đóng/dọn connection lỗi, đợi backoff có jitter nếu còn ngân sách, mượn connection mới và chạy lại toàn bộ SELECT. Không tiếp tục dùng ResultSet cũ.

### Bài 4 — COMMIT thất bại ở phía Java

Service tạo đơn hàng rồi gọi COMMIT; client nhận timeout và không biết DB đã commit chưa. Có thể lập tức dùng operation_id mới để INSERT lại không?

**Gợi ý:** không. Đối soát operation_id cũ trên nguồn có thẩm quyền và kiểm tra dữ liệu; idempotency cùng ràng buộc UNIQUE ngăn tạo trùng.

### Bài 5 — Deadlock hay connection hỏng?

Giao dịch nhận **40P01** của PostgreSQL. Có thể kết luận socket bị hỏng không?

**Gợi ý:** không. Đây là deadlock; cần rollback và retry toàn transaction (nếu an toàn) và sửa thứ tự lấy khóa. Socket có thể vẫn dùng được sau rollback tùy trạng thái transaction/driver.

### Bài 6 — Kích thước pool

Một DB cho phép khoảng 200 session ứng dụng sau khi trừ các kết nối khác. Có 20 instance, mỗi instance đặt maximumPoolSize=20. Rủi ro là gì?

**Gợi ý:** tổng lý thuyết 400 connection, vượt ngân sách DB. Phải tính tổng các instance, mức sử dụng thực và dự phòng thay vì chỉ nhìn pool một instance.

### Bài 7 — Failover và consistency

Ứng dụng reconnect thành công tới primary mới sau failover bất đồng bộ. Có được mặc định mọi COMMIT vừa xác nhận trên primary cũ đều có mặt ở primary mới không?

**Gợi ý:** không. Cần xem RPO, replication lag và giao thức failover; với thao tác quan trọng phải đối soát.

### Bài 8 — Timeout ở nhiều lớp

Statement timeout được đặt 3 giây nhưng pool acquisition timeout là 10 giây và request HTTP deadline là 5 giây. Điều gì có thể xảy ra?

**Gợi ý:** request có thể hết deadline trước khi lấy được connection hoặc trước khi câu SQL được chạy. Timeout theo từng lớp phải được phối hợp với ngân sách đầu cuối.

## 15. Ghi nhớ để áp dụng

**Kiểm tra kết nối hỏng** gồm nhiều tầng: trạng thái object JDBC, xác thực tới DBMS qua **isValid()** hoặc pool validation, kiểm tra tình trạng transaction và quan sát endpoint hạ tầng. Không có kiểm tra nào đảm bảo connection sẽ sống mãi; luôn xử lý SQLException ở thao tác thực tế.

**Phục hồi sau gián đoạn** bắt đầu bằng việc dọn connection lỗi, trả tài nguyên đúng cách, giới hạn tải, mượn connection mới khi DB sẵn sàng và quyết định retry dựa trên **loại công việc**. Truy vấn thuần đọc có thể thử lại trong ngân sách hữu hạn; transaction bị xác nhận hủy phải chạy lại từ đầu; còn **COMMIT không rõ kết quả** cần idempotency và đối soát trước khi làm lại thao tác ghi.

Trong tầng persistence Java, đặt ranh giới transaction rõ ràng, dùng try-with-resources hoặc transaction manager, cấu hình pool và timeout theo SLO, giám sát lỗi SQLSTATE và thời gian giữ connection. Cách kết hợp này giúp giảm lỗi kết nối, tránh nhân đôi tác dụng nghiệp vụ và đưa dịch vụ trở lại trạng thái hoạt động ổn định sau restart, failover hoặc gián đoạn mạng.
