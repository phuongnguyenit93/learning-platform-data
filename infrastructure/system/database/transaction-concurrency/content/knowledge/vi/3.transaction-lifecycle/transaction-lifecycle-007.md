# Thiết lập đặc tính giao dịch theo kết nối, phiên và từng giao dịch

Khi xây dựng ứng dụng nhiều người dùng truy cập cơ sở dữ liệu đồng thời, chúng ta thường cần điều chỉnh **mức cô lập**, **chế độ chỉ đọc**, **thời gian chờ khóa** hoặc cách bắt đầu và kết thúc một giao dịch. Một thay đổi cấu hình có hiệu lực ở đâu và kéo dài bao lâu là vấn đề quan trọng không kém giá trị được thiết lập.

Chẳng hạn, ứng dụng muốn một giao dịch lập báo cáo đọc dữ liệu bằng mức cô lập REPEATABLE READ, trong khi các giao dịch cập nhật bình thường vẫn dùng READ COMMITTED. Nếu thiết lập REPEATABLE READ cho **toàn phiên** rồi trả kết nối về pool mà không khôi phục, một yêu cầu khác có thể kế thừa thiết lập đó. Ngược lại, nếu thay đổi mức cô lập sau khi giao dịch đã chạy truy vấn, DBMS có thể từ chối thay đổi hoặc xử lý theo quy tắc riêng.

Bài này trình bày cách xác định **phạm vi (scope)** và **vòng đời (lifetime)** của đặc tính giao dịch trên ba tầng: kết nối của ứng dụng, phiên làm việc phía cơ sở dữ liệu và từng giao dịch cụ thể.

## 1. Phân biệt ba phạm vi cấu hình

Một ứng dụng Java thường lấy đối tượng **java.sql.Connection** từ **DataSource**, sau đó thực hiện các giao dịch qua đối tượng này. Phía DBMS có thể duy trì một **database session** cùng những thiết lập riêng cho phiên. Trong phiên ấy, từng giao dịch có thể dùng các đặc tính của phiên hoặc ghi đè chúng trong một khoảng thời gian giới hạn.

~~~mermaid
flowchart TD
    G["Cấu hình mặc định DBMS / cơ sở dữ liệu / tài khoản"]
    G --> S["Phiên DB: các mặc định của session"]
    A["Ứng dụng lấy JDBC Connection từ pool"] --> S
    S --> T1["Giao dịch T1: dùng mặc định phiên"]
    S --> T2["Giao dịch T2: đặt riêng đặc tính"]
    S --> T3["Giao dịch T3: trở lại mặc định phiên"]
    T1 --> C1["SELECT / UPDATE / COMMIT"]
    T2 --> C2["BEGIN / SET TRANSACTION / SELECT / COMMIT"]
    T3 --> C3["SELECT / COMMIT"]
~~~

Sơ đồ mang tính khái niệm. Khi có proxy, pool hoặc bộ ghép kênh kết nối, một đối tượng kết nối ở phía ứng dụng không nhất thiết ánh xạ cố định một-một tới một session trên máy chủ trong mọi thời điểm.

| Phạm vi | Ai thường thiết lập? | Thời hạn thường gặp | Ý nghĩa thực tế |
| --- | --- | --- | --- |
| **Mặc định DBMS/database/role** | Người quản trị, cấu hình triển khai | Đến khi cấu hình thay đổi hoặc phiên mới nhận cấu hình | Giá trị ban đầu khi phiên được tạo; chi tiết phụ thuộc hệ quản trị |
| **Phiên (session)** | SQL SET SESSION, ALTER SESSION hoặc driver | Nhiều giao dịch nối tiếp trong cùng phiên | Các giao dịch sau có thể kế thừa giá trị phiên |
| **Kết nối (Connection)** | JDBC, connection pool, transaction manager | Từ lúc mượn/thiết lập đến khi được khôi phục hoặc đóng logic | API Java điều khiển trạng thái kết nối; driver có thể ánh xạ nó sang trạng thái phiên DB |
| **Giao dịch (transaction)** | SQL hoặc transaction manager khi mở giao dịch | Đến khi COMMIT/ROLLBACK hoặc giao dịch kết thúc | Chỉ áp dụng cho giao dịch được chọn; giao dịch sau dùng mặc định tiếp theo |

**Kết nối** là đối tượng/tài nguyên mà ứng dụng sử dụng; **phiên** là ngữ cảnh DBMS quản lý. Chúng có liên hệ chặt chẽ nhưng không phải hai tên bắt buộc đồng nghĩa. Với pool truyền thống, một kết nối vật lý có thể giữ cùng một session trong thời gian dài; với hạ tầng trung gian, quan hệ này có thể khác.

Khái niệm **phiên DB** ở đây cũng khác phiên đăng nhập HTTP của người dùng cuối. Hai HTTP request khác nhau có thể lần lượt sử dụng cùng một session DB nhờ connection pool.

## 2. Những đặc tính giao dịch thường được cấu hình

Không phải tất cả thuộc tính dưới đây đều có cùng API hoặc cùng phạm vi trên mọi DBMS.

| Đặc tính | Mục đích | Điểm cần chú ý |
| --- | --- | --- |
| **Isolation level** | Kiểm soát tương tác và khả năng quan sát giữa các giao dịch đồng thời | Cấp độ hỗ trợ và cơ chế thực hiện khác nhau giữa DBMS |
| **Read-only / read-write** | Khai báo giao dịch dự định chỉ đọc hay có ghi | Có DBMS cưỡng chế bằng SQL, trong khi JDBC readOnly có thể chỉ là gợi ý |
| **Auto-commit** | Quyết định các câu lệnh JDBC có tự được commit khi hoàn tất hay không | Thuộc tính Connection, không phải một mức cô lập |
| **Deferrable** | Cho phép một số giao dịch đọc chờ thời điểm tạo snapshot an toàn | Tính năng chuyên biệt, ví dụ PostgreSQL SERIALIZABLE READ ONLY DEFERRABLE |
| **Thời gian chờ khóa** | Giới hạn thời gian đợi tài nguyên bị giao dịch khác khóa | Phạm vi và cú pháp SQL tùy DBMS |
| **Statement/transaction timeout** | Giới hạn thời gian chạy câu lệnh hoặc giao dịch | Timeout phía framework, driver và DBMS có thể là những cơ chế khác nhau |

### Các mức cô lập

Bốn tên mức cô lập thường thấy trong SQL/JDBC là:

- **READ UNCOMMITTED:** mức tên gọi cho phép ít cách ly nhất trong mô hình chuẩn; một số DBMS vẫn ngăn dirty read dù được yêu cầu mức này.
- **READ COMMITTED:** một câu lệnh đọc không nhìn thấy dữ liệu chưa commit của giao dịch khác; các lần đọc ở thời điểm khác nhau có thể quan sát kết quả mới.
- **REPEATABLE READ:** tăng tính ổn định của những lần đọc trong cùng giao dịch; bảo đảm cụ thể đối với phantom và xung đột ghi phụ thuộc DBMS.
- **SERIALIZABLE:** hướng tới kết quả tương đương một lịch thực thi tuần tự hợp lệ của các giao dịch; có thể phải chờ hoặc hủy rồi thử lại khi xung đột.

Tên isolation level cho biết **yêu cầu về ngữ nghĩa**, không mô tả duy nhất một thuật toán khóa hay MVCC. Ví dụ, cùng tên REPEATABLE READ có thể khác biệt đáng kể giữa các hệ quản trị.

### Read-only không đồng nghĩa với isolation

**Read-only** nói về ý định hoặc ràng buộc cho phép thay đổi dữ liệu; **isolation** nói về tương tác giữa các giao dịch. Một giao dịch READ ONLY ở READ COMMITTED không đương nhiên nhìn thấy cùng một snapshot suốt cả giao dịch. Muốn một snapshot đọc ổn định cần xét thêm mức cô lập và cơ chế của DBMS.

Tương tự, **setAutoCommit(false)** không tự động tăng isolation level. Nó chỉ giúp ứng dụng chủ động gom nhiều câu lệnh vào phạm vi một giao dịch do mình commit hoặc rollback.

## 3. Thiết lập ở cấp phiên: ảnh hưởng đến nhiều giao dịch

Một thiết lập cấp **session** thường có hiệu lực cho các giao dịch tiếp theo trong phiên đó cho đến khi được đổi hoặc phiên kết thúc. Đây là lựa chọn phù hợp khi toàn bộ công việc của phiên cần chung một đặc tính, nhưng dễ gây tác động ngoài ý muốn nếu kết nối được tái sử dụng.

Ví dụ với **PostgreSQL**:

~~~sql
-- Đặt mặc định cho những giao dịch sẽ bắt đầu trong phiên này.
SET SESSION CHARACTERISTICS AS TRANSACTION
    ISOLATION LEVEL READ COMMITTED,
    READ WRITE;

BEGIN;
SELECT COUNT(*) FROM orders;
COMMIT;

-- Giao dịch tiếp theo vẫn kế thừa mặc định của session.
BEGIN;
UPDATE orders
SET status = 'PROCESSING'
WHERE id = 101;
COMMIT;
~~~

Lệnh **SET SESSION CHARACTERISTICS AS TRANSACTION** cấu hình đặc tính mặc định cho những giao dịch sau trong phiên PostgreSQL. Đặt nó không có nghĩa giao dịch đang chạy luôn có thể đổi isolation level giữa chừng.

Ở các DBMS khác, cú pháp có thể là **SET SESSION TRANSACTION ...**, **ALTER SESSION ...** hoặc một lệnh **SET** có phạm vi session ngầm định. Tên lệnh giống nhau không đảm bảo thời điểm áp dụng giống nhau.

### Ví dụ cấp session trong MySQL

~~~sql
-- MySQL: đặt mức cô lập mặc định cho các transaction tiếp theo
-- trong session hiện tại.
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;
SELECT COUNT(*) FROM orders;
COMMIT;

START TRANSACTION;
SELECT COUNT(*) FROM orders;
COMMIT;
~~~

Cả hai giao dịch trong ví dụ kế thừa mặc định phiên được đặt bằng **SET SESSION**, trừ khi có thiết lập riêng cho giao dịch phù hợp với quy tắc của MySQL.

Với MySQL, **SET GLOBAL TRANSACTION ...** có phạm vi khác: nó ảnh hưởng mặc định cho các phiên mới theo quy tắc của phiên bản/triển khai, chứ không phải cách thay đổi tùy ý giao dịch hiện đang chạy trong một connection khác.

### Session sống lâu hơn request

~~~text
Request A mượn Connection X
    |
    +-- Đổi isolation mặc định của session thành SERIALIZABLE
    +-- Chạy giao dịch và COMMIT
    +-- Trả Connection X về pool
              |
Request B mượn lại Connection X
    |
    +-- Nếu pool không khôi phục session:
        có thể tiếp tục chạy với SERIALIZABLE
~~~

Một kết nối từ pool không nhất thiết mất trạng thái session khi ứng dụng gọi **close()**: thông thường đó chỉ là thao tác trả kết nối logic về pool. Vì vậy, sửa session trực tiếp bằng SQL rồi quên khôi phục là nguồn gây lỗi khó phát hiện, nhất là khi chương trình đôi khi chạy chậm hoặc phát sinh tranh chấp khóa khác thường.

## 4. Thiết lập riêng cho từng giao dịch

Thiết lập ở cấp **transaction** giúp yêu cầu đặc tính khác với mặc định phiên trong đúng một đơn vị công việc. Sau khi giao dịch kết thúc, đặc tính được đặt riêng cho giao dịch đó không nên được xem như mặc định vĩnh viễn của các giao dịch sau.

Cần lưu ý **thời điểm thiết lập**. Nhiều DBMS yêu cầu chọn isolation level ngay trước hoặc ở đầu giao dịch, trước khi thực hiện các câu lệnh truy cập dữ liệu. Không thể dựa vào việc chạy một câu SQL giữa giao dịch để thay đổi ngữ nghĩa của những truy vấn đã thực hiện trước đó.

### PostgreSQL: SET TRANSACTION sau BEGIN và trước truy vấn

~~~sql
-- Mặc định session giả sử là READ COMMITTED.
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY;

SELECT COUNT(*) AS total_orders
FROM orders;

SELECT SUM(total_amount) AS total_amount
FROM orders;

COMMIT;

-- Giao dịch tiếp theo quay lại mặc định của session.
BEGIN;
SELECT COUNT(*) FROM orders;
COMMIT;
~~~

Trong PostgreSQL, các đặc tính có thể được khai báo ngay trong **BEGIN**:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE,
    READ ONLY,
    DEFERRABLE;

SELECT COUNT(*) FROM orders;
COMMIT;
~~~

**DEFERRABLE** trong PostgreSQL chỉ có ý nghĩa theo cơ chế được hỗ trợ, đặc biệt khi đi cùng **SERIALIZABLE, READ ONLY**. DBMS có thể chờ để tạo snapshot an toàn cho giao dịch đọc; đây không phải tùy chọn chung của mọi hệ quản trị.

**SET LOCAL** là một cơ chế khác của PostgreSQL để đặt một tham số cấu hình trong phạm vi giao dịch hiện tại, ví dụ:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

SELECT *
FROM orders
WHERE id = 101
FOR UPDATE;

COMMIT;
~~~

Trong trường hợp này, **lock_timeout** được thiết lập cục bộ cho giao dịch hiện tại. Cần phân biệt **SET LOCAL tham số cấu hình** với **SET TRANSACTION đặc tính giao dịch**: cả hai có thể hữu ích trong một transaction nhưng mục đích và quy tắc hợp lệ không hoàn toàn giống nhau.

### MySQL: SET TRANSACTION áp dụng cho giao dịch kế tiếp

Trong MySQL, thứ tự thường dùng khác PostgreSQL:

~~~sql
-- MySQL: cấu hình cho transaction tiếp theo của session.
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

START TRANSACTION;
SELECT COUNT(*) FROM orders;
COMMIT;

-- Giao dịch tiếp theo sau đó trở lại mặc định session,
-- nếu không có thiết lập riêng mới.
START TRANSACTION;
SELECT COUNT(*) FROM orders;
COMMIT;
~~~

**SET TRANSACTION** không có từ khóa SESSION/GLOBAL trong ví dụ MySQL thường đặt đặc tính cho **giao dịch kế tiếp**. Đừng lấy đúng chuỗi lệnh của PostgreSQL (BEGIN rồi SET TRANSACTION) áp trực tiếp vào MySQL và giả định nó có ý nghĩa tương đương.

MySQL cũng cho phép chỉ rõ ý định read-only ở điểm bắt đầu, khi phù hợp với phiên bản và storage engine:

~~~sql
START TRANSACTION READ ONLY;

SELECT COUNT(*) FROM orders;

COMMIT;
~~~

Read-only là đặc tính của giao dịch này. Mức cô lập của nó vẫn cần được xác định riêng nếu muốn khác mặc định.

### SQL Server: lệnh SET tác động đến session

Trong SQL Server, cú pháp điển hình là:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

BEGIN TRANSACTION;

SELECT COUNT(*) FROM dbo.Orders;

COMMIT TRANSACTION;

-- Lệnh SET có tính chất session;
-- không tự trở về READ COMMITTED chỉ vì COMMIT.
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
~~~

Dù tên lệnh chứa chữ “TRANSACTION”, **SET TRANSACTION ISOLATION LEVEL** của SQL Server thiết lập mức cô lập cho **session/connection hiện tại** theo quy tắc của SQL Server. Nó không tương đương với **SET TRANSACTION** chỉ có hiệu lực cho một giao dịch ở hệ quản trị khác. Đây là lý do luôn phải xác minh **cú pháp, thời điểm áp dụng, thời điểm hết hiệu lực và cơ chế khôi phục** cho DBMS đang dùng.

## 5. Thiết lập qua JDBC Connection

Với Java, giao diện **java.sql.Connection** cung cấp các thao tác quen thuộc:

| Phương thức JDBC | Ý nghĩa | Lưu ý về vòng đời |
| --- | --- | --- |
| **setTransactionIsolation(level)** | Yêu cầu mức cô lập khi làm việc qua connection | Tác động theo connection và cách driver/DBMS triển khai; cần thiết lập trước giao dịch |
| **getTransactionIsolation()** | Đọc mức cô lập được driver báo trên connection | Hữu ích để lưu và khôi phục giá trị ban đầu |
| **setReadOnly(boolean)** | Gợi ý hoặc cấu hình chế độ chỉ đọc cho connection | JDBC mô tả đây là hint để tối ưu, DBMS có thể áp dụng mức cưỡng chế khác nhau |
| **setAutoCommit(boolean)** | Bật/tắt chế độ tự động xác nhận câu lệnh | Chuyển từ false sang true khi đang trong giao dịch có thể khiến giao dịch hiện tại được commit theo hợp đồng JDBC |
| **commit() / rollback()** | Kết thúc giao dịch JDBC đang quản lý | Không phải thao tác đổi mặc định isolation của session |
| **setSchema(...), setCatalog(...)** | Đổi ngữ cảnh schema/catalog khi được driver hỗ trợ | Là trạng thái kết nối, không phải thay đổi isolation |

Các hằng số JDBC thường dùng:

~~~java
Connection.TRANSACTION_READ_UNCOMMITTED
Connection.TRANSACTION_READ_COMMITTED
Connection.TRANSACTION_REPEATABLE_READ
Connection.TRANSACTION_SERIALIZABLE
~~~

Ngoài ra có **Connection.TRANSACTION_NONE**, thể hiện rằng giao dịch không được hỗ trợ; không nên xem nó là một mức cô lập dùng thay các cấp độ thông thường.

Một driver có thể không hỗ trợ mọi isolation level. Ứng dụng có thể xem metadata của kết nối hoặc kiểm tra lỗi khi yêu cầu mức không được hỗ trợ. Không nên giả định DBMS luôn thực thi chính xác cùng một tập hiện tượng đọc/ghi chỉ vì hằng số JDBC có cùng tên.

### Ví dụ JDBC: dùng một mức cô lập cho một lần xử lý

Trong ví dụ sau, ứng dụng lấy một connection từ pool, lưu trạng thái ban đầu, thiết lập isolation trước khi mở giao dịch và cố gắng đưa connection về trạng thái trước khi trả pool. Ví dụ giả định pool cấp connection đang ở chế độ auto-commit.

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderReader {
    private final DataSource dataSource;

    public OrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long countOrders() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            int previousIsolation = connection.getTransactionIsolation();
            boolean previousReadOnly = connection.isReadOnly();
            boolean previousAutoCommit = connection.getAutoCommit();

            if (!previousAutoCommit) {
                throw new SQLException(
                    "Expected a pooled connection with auto-commit enabled"
                );
            }

            boolean transactionOpened = false;
            try {
                // Đặt đặc tính trước khi chạy câu lệnh của transaction.
                connection.setTransactionIsolation(
                    Connection.TRANSACTION_REPEATABLE_READ
                );
                connection.setReadOnly(true);
                connection.setAutoCommit(false);
                transactionOpened = true;

                long count;
                try (PreparedStatement statement = connection.prepareStatement(
                        "SELECT COUNT(*) FROM orders");
                     ResultSet rs = statement.executeQuery()) {
                    rs.next();
                    count = rs.getLong(1);
                }

                connection.commit();
                transactionOpened = false;
                return count;
            } catch (SQLException | RuntimeException error) {
                if (transactionOpened) {
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackError) {
                        error.addSuppressed(rollbackError);
                    }
                }
                throw error;
            } finally {
                // Sau ranh giới giao dịch, khôi phục trạng thái Connection.
                // Nếu khôi phục lỗi, connection pool phải xử lý connection
                // không còn an toàn để tái sử dụng.
                connection.setAutoCommit(previousAutoCommit);
                connection.setReadOnly(previousReadOnly);
                connection.setTransactionIsolation(previousIsolation);
            }
        }
    }
}
~~~

Ví dụ cho thấy **isolation và readOnly được chọn trước các câu lệnh**, còn **commit()** xác nhận công việc đã làm. Trạng thái được khôi phục sau khi transaction kết thúc vì đối tượng connection có thể được tái sử dụng.

Đây là ví dụ cơ chế mức thấp. Trong mã ứng dụng sản xuất, nên để transaction manager và connection pool xử lý đầy đủ việc khôi phục, loại bỏ connection lỗi và bảo toàn ngoại lệ khi cleanup thất bại. Tùy driver và DBMS, **setReadOnly(true)** có thể tối ưu đường đọc hoặc kích hoạt ràng buộc read-only; nó **không phải cam kết phổ quát rằng mọi SQL ghi sẽ bị chặn**.

### Một cảnh báo quan trọng về thời điểm đổi isolation

JDBC không đặt ra một hành vi di động tuyệt đối cho mọi driver nếu ứng dụng gọi **setTransactionIsolation(...) trong lúc một giao dịch đã hoạt động**. Kết quả có thể phụ thuộc DBMS hoặc driver và có thể kéo theo ranh giới giao dịch không mong muốn. Cách an toàn là **chọn isolation trước thao tác đầu tiên của transaction**, rồi để một thành phần quản lý nhất quán ranh giới begin/commit/rollback.

Tương tự, việc gọi **setAutoCommit(true)** để “dọn dẹp” khi giao dịch vẫn còn hoạt động có thể tạo **commit ngoài ý muốn**. Luôn commit hoặc rollback rõ ràng trước khi khôi phục auto-commit.

## 6. Spring @Transactional quản lý phạm vi ra sao?

Trong ứng dụng Spring sử dụng transaction manager thích hợp, có thể khai báo:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SalesReportService {
    @Transactional(
        isolation = Isolation.REPEATABLE_READ,
        readOnly = true
    )
    public long countOrders() {
        // Thực thi truy vấn qua Repository/JdbcTemplate đang tham gia
        // cùng transaction do Spring quản lý.
        return 0L; // Placeholder minh họa chữ ký phương thức.
    }
}
~~~

Khi lời gọi thực sự đi qua cơ chế interceptor/proxy giao dịch của Spring và **một transaction mới được tạo**, transaction manager có thể chọn mức cô lập được yêu cầu, chuẩn bị connection, mở ranh giới giao dịch và dọn trạng thái khi giao dịch kết thúc. Ý nghĩa thực tế còn phụ thuộc loại transaction manager, driver và DBMS.

Với **propagation = REQUIRED** (mặc định thông thường), nếu phương thức được gọi khi đã có một transaction tương thích đang hoạt động, nó thường **tham gia giao dịch hiện tại** thay vì mở giao dịch vật lý mới. Khi đó, khai báo isolation ở phương thức bên trong **không tự ghi đè mức cô lập của giao dịch đã tồn tại**. Cấu hình kiểm tra thuộc tính giao dịch của transaction manager có thể phát hiện một số xung đột.

Ví dụ:

~~~text
Service A: @Transactional(isolation = READ_COMMITTED)
    |
    +-- gọi Service B: @Transactional(isolation = SERIALIZABLE)
            |
            +-- Nếu B tham gia cùng transaction hiện có theo REQUIRED,
                không thể suy rằng các truy vấn của B đã chạy SERIALIZABLE.
~~~

Một transaction mới với propagation **REQUIRES_NEW** có vòng đời độc lập với transaction đang tạm dừng; nó có thể phải mượn connection khác và cần tính tới giới hạn connection pool. Không sử dụng REQUIRES_NEW chỉ để “ép” một mức cô lập mới nếu nghiệp vụ không cho phép tách ranh giới commit.

Các lưu ý quan trọng:

- **@Transactional** chỉ có tác dụng khi phương thức thực sự được cơ chế quản lý giao dịch của Spring intercept. Lời gọi nội bộ trực tiếp giữa các phương thức cùng đối tượng có thể không đi qua proxy theo cấu hình phổ biến.
- **readOnly = true** thường là hint từ framework tới tài nguyên, dù một số tích hợp DB có thể thực thi ràng buộc mạnh hơn. Không coi nó là thay thế cho quyền DB hoặc cơ chế cấm ghi bắt buộc.
- **timeout** của Spring không mặc nhiên đồng nghĩa với lệnh thay đổi thời gian chờ khóa của DBMS. Nên xem tài liệu transaction manager và đường thực thi SQL.
- Khi dùng Spring quản lý transaction, tránh đồng thời tự gọi **commit()**, **rollback()** hoặc đổi auto-commit trên cùng connection đang được Spring quản lý.

## 7. Quy tắc kế thừa, ghi đè và trả lại mặc định

Có thể hình dung thứ tự chọn thuộc tính như sau, với điều kiện DBMS có hỗ trợ các phạm vi này:

~~~text
Mặc định khi tạo session
    |
    +-- Thiết lập mới ở cấp session
            |
            +-- Transaction A: kế thừa session
            |
            +-- Transaction B: ghi đè cho riêng nó
            |
            +-- Transaction C: lại kế thừa session
~~~

Bảng ví dụ dưới đây dùng PostgreSQL để minh họa:

| Thời điểm | Hành động | Mức cô lập được kỳ vọng |
| --- | --- | --- |
| 1 | Session mặc định READ COMMITTED | READ COMMITTED |
| 2 | Bắt đầu transaction A, không ghi đè | READ COMMITTED |
| 3 | COMMIT A | Transaction A kết thúc |
| 4 | Bắt đầu transaction B, đặt REPEATABLE READ trước câu lệnh đầu | REPEATABLE READ trong B |
| 5 | COMMIT B | Thiết lập riêng của B hết hiệu lực |
| 6 | Bắt đầu transaction C, không ghi đè | READ COMMITTED |

Không nên biến bảng này thành một quy luật cú pháp thống nhất cho mọi DBMS. Với SQL Server, lệnh SET TRANSACTION ISOLATION LEVEL có vòng đời cấp session; với MySQL, SET TRANSACTION có thể áp dụng cho giao dịch kế tiếp; với PostgreSQL, SET TRANSACTION thường áp dụng cho giao dịch hiện tại.

**“Giá trị ghi đè” cần gắn với đúng thời gian hiệu lực.** Nếu không, ứng dụng có thể chạy giao dịch thứ hai bằng cấu hình của giao dịch thứ nhất mà không nhận ra.

### COMMIT và ROLLBACK đặt lại những gì?

**COMMIT/ROLLBACK kết thúc giao dịch** và làm các thiết lập thật sự giới hạn trong giao dịch hết hiệu lực theo quy tắc DBMS. Chúng **không tự động reset mọi thuộc tính session hoặc connection**. Chẳng hạn, một tham số session được thay đổi trước đó có thể vẫn hiện diện sau khi giao dịch hoàn tất.

Ngoài ra, một số hệ CSDL cho phép thay đổi tham số session bên trong transaction với quy tắc rollback riêng. Ví dụ PostgreSQL có sự khác biệt giữa **SET** và **SET LOCAL**, cũng như tình huống SET được thực hiện trong giao dịch rồi rollback. Cần kiểm tra tài liệu DBMS thay vì mặc định “mọi lệnh SET ở trong BEGIN đều chỉ sống đến COMMIT”.

## 8. Connection pool và nguy cơ rò rỉ trạng thái

Trong hệ thống web, số request thường lớn hơn số kết nối vật lý của pool. Vì vậy, mỗi connection có thể phục vụ nhiều request khác nhau theo thời gian.

~~~mermaid
sequenceDiagram
    participant R1 as Request A
    participant P as Connection Pool
    participant DB as DB session
    participant R2 as Request B

    R1->>P: Mượn Connection X
    R1->>DB: Đổi session isolation thành SERIALIZABLE
    R1->>DB: Giao dịch và COMMIT
    R1->>P: Trả X về pool
    R2->>P: Mượn lại X
    R2->>DB: BEGIN giao dịch mới
    Note over R2,DB: Nếu không reset: có thể kế thừa SERIALIZABLE
~~~

Đây là ví dụ về **state leakage** giữa các lượt sử dụng cùng kết nối. Nó có thể làm tăng thời gian chờ khóa, tăng số transaction phải retry hoặc khiến các truy vấn chạy với hành vi khác dự kiến.

Một số pool tự theo dõi và khôi phục các thuộc tính JDBC tiêu chuẩn như auto-commit, isolation và read-only. Tuy nhiên, việc chạy **SET** trực tiếp trên SQL có thể vượt ngoài khả năng theo dõi của pool. Không được mặc định rằng pool nhận biết mọi thay đổi cấp session, đặc biệt khi dùng biến tùy biến, role, schema, timeout hoặc tham số riêng của DBMS.

Khi thiết kế việc sử dụng pool:

1. **Ưu tiên phạm vi nhỏ nhất phù hợp với nghiệp vụ:** nếu chỉ một giao dịch cần thay đổi, sử dụng cơ chế riêng cho transaction khi DBMS hỗ trợ.
2. **Để transaction manager quản lý trạng thái** khi có Spring, JTA hoặc framework tương đương.
3. **Khôi phục giá trị ban đầu** khi tự thay đổi thuộc tính connection và transaction đã hoàn tất.
4. **Không tùy tiện gửi SQL đổi session** trên kết nối dùng chung nếu không có cơ chế reset đáng tin cậy.
5. **Biết trạng thái khởi tạo của pool:** auto-commit, isolation mặc định, read-only và các SQL khởi tạo session nếu có.
6. **Loại bỏ connection không an toàn** nếu rollback, reset hoặc phiên máy chủ thất bại; đừng đưa trạng thái không xác định quay lại phục vụ request khác.

Với **transaction pooling** ở một proxy, connection client có thể không gắn liên tục với một server session giữa các giao dịch. Các thiết lập cấp session còn có thể không tương thích với mô hình này hoặc bị giới hạn. Vì thế, cần xem hợp đồng cụ thể của proxy và pool trước khi dựa vào session state để duy trì đặc tính giao dịch.

## 9. Khi nào nên chọn cấp connection/session, khi nào chọn từng transaction?

Hãy xét một ứng dụng có ba loại công việc:

- **Trang danh sách đơn hàng:** nhiều truy vấn ngắn, thông thường dùng mặc định READ COMMITTED của DBMS.
- **Báo cáo doanh thu:** cần một cách đọc dữ liệu nhất quán trong cả báo cáo; có thể chọn mức cô lập cao hơn cho đúng transaction đọc báo cáo.
- **Cập nhật đặt chỗ đồng thời:** cần chống overbooking; có thể kết hợp isolation phù hợp, câu lệnh UPDATE có điều kiện, khóa hoặc kiểm tra xung đột rồi retry.

Không nhất thiết tăng isolation của toàn bộ pool lên SERIALIZABLE chỉ vì một đường nghiệp vụ cần bảo đảm mạnh hơn. Ngược lại, nếu toàn bộ một ứng dụng chuyên dụng yêu cầu cùng mức cô lập và đã kiểm tra tác động, cấu hình mặc định ở cấp connection/session có thể hợp lý.

| Nhu cầu | Phạm vi thường nên xem xét | Vì sao |
| --- | --- | --- |
| Thiết lập chính sách chung cho một database hoặc loại phiên chuyên biệt | Mặc định DBMS/role hoặc session lúc khởi tạo | Giảm cấu hình lặp lại, nhưng phải quản lý tác động chung |
| Chỉ một transaction cần snapshot đọc ổn định | Transaction | Tránh làm thay đổi các giao dịch khác |
| Chỉ một transaction cần hạn chế thời gian chờ khóa | Transaction-local khi DBMS hỗ trợ | Tránh timeout lan sang request kế tiếp |
| Mọi transaction trên connection chuyên dụng dùng cùng isolation | Connection/session | Có thể hợp lý với connection không chia sẻ đa mục đích |
| Request sử dụng pool đa nhiệm | Transaction manager với trạng thái được khôi phục | Giảm nguy cơ thừa hưởng session state từ request trước |
| Tăng bảo đảm chống ghi trùng/đặt chỗ trùng | Ràng buộc DB + transaction + logic retry | Isolation không thay thế unique constraint và quy tắc nghiệp vụ |

### Ví dụ chống ghi vượt tồn kho

Nếu ứng dụng cần đảm bảo không bán vượt số lượng còn lại, câu lệnh cập nhật có điều kiện trên DBMS phù hợp thường là một thành phần quan trọng:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'BOOK-01'
  AND quantity >= 1;
~~~

Ứng dụng kiểm tra số hàng cập nhật: nếu bằng 0, không còn số lượng đủ điều kiện. Câu lệnh này có thể tránh một số lỗi của cách đọc số lượng về ứng dụng rồi ghi lại giá trị cũ, nhưng độ đúng đắn tổng thể vẫn phụ thuộc các bất biến nghiệp vụ, các câu lệnh khác và hành vi transaction. Thiết lập isolation level nên xuất phát từ loại xung đột thực tế cần ngăn chặn.

## 10. Thứ tự thiết lập theo vòng đời giao dịch

Một thứ tự triển khai có ý nghĩa trong JDBC cục bộ:

~~~text
Mượn Connection từ DataSource
        |
        v
Đọc/cấu hình các thuộc tính connection cần thiết
        |
        v
Chọn isolation, read-only trước các SQL thuộc giao dịch
        |
        v
Tắt auto-commit khi quản lý transaction thủ công
        |
        v
Thực thi câu lệnh thuộc cùng giao dịch
        |
        +--> Thành công: COMMIT
        |
        +--> Thất bại: ROLLBACK (nếu còn có thể)
        |
        v
Khôi phục trạng thái connection / transaction manager cleanup
        |
        v
Trả Connection về pool
~~~

Đây là luồng mẫu, không phải tuyên bố rằng chỉ có một cách hợp lệ để DBMS bắt đầu giao dịch. Trong JDBC, việc tắt auto-commit có thể cho phép giao dịch bắt đầu ngầm khi thực thi câu lệnh đầu tiên; trong SQL, BEGIN/START TRANSACTION có thể tạo ranh giới tường minh. Điều quan trọng là **đặc tính đã được chọn tại thời điểm DBMS bắt đầu áp dụng ngữ nghĩa giao dịch**.

### Các tình huống dễ lỗi

**Đổi isolation khi transaction đã đọc dữ liệu.** Truy vấn đầu đã quan sát theo mức cũ. Một số DBMS cấm thay đổi sau truy vấn đầu, số khác có quy tắc riêng. Cần chọn mức cô lập ngay khi mở transaction.

**Tưởng COMMIT sẽ reset session.** COMMIT kết thúc một transaction, trong khi thiết lập session có thể còn tồn tại qua nhiều lần COMMIT.

**Tưởng readOnly = true ngăn tuyệt đối mọi lệnh ghi.** Với JDBC/Spring, read-only có thể chỉ là hint. Nếu cần cưỡng chế, phải kiểm tra khả năng thực thi read-only của DBMS và quyền của tài khoản.

**Tưởng mỗi Connection đại diện cho một giao dịch.** Một Connection có thể được tái sử dụng cho nhiều transaction liên tiếp.

**Tưởng cùng tên isolation là cùng hành vi giữa các DBMS.** Mức READ COMMITTED/REPEATABLE READ và việc dùng MVCC/locking có thể cho những hiện tượng thực tế khác nhau.

**Tưởng một giao dịch con được khai báo isolation riêng sẽ được áp dụng ngay.** Nếu nó chỉ tham gia transaction bên ngoài, các thuộc tính cấp transaction không nhất thiết có hiệu lực mới.

**Tưởng retry luôn an toàn sau timeout.** Nếu timeout xảy ra quanh COMMIT, kết quả transaction có thể chưa xác định ở phía client; cần định danh nghiệp vụ và chiến lược idempotency phù hợp.

## 11. Quan sát đặc tính đang có hiệu lực

Khi phân tích một sự cố concurrency, đừng chỉ nhìn vào annotation hoặc lệnh cấu hình trong source. Nên xác định **giao dịch thực tế** đã chạy ở isolation level nào và thông qua session/connection nào.

Có thể tiến hành theo thứ tự:

1. Ghi lại **thời điểm mượn connection** và transaction được bắt đầu.
2. Xác định **cấu hình mặc định** của pool/driver/DBMS, cùng mọi SQL khởi tạo session.
3. Kiểm tra xem lệnh thiết lập đã chạy **trước câu lệnh đầu tiên** của transaction hay chưa.
4. Đối chiếu **giá trị được DBMS báo** trong chính transaction cần kiểm tra nếu hệ quản trị cung cấp cách truy vấn phù hợp.
5. Xem thời điểm **COMMIT/ROLLBACK**, thời điểm trả connection và khả năng khôi phục trạng thái.
6. Nếu có proxy hoặc replica, xác nhận **server session thực tế** cùng nơi truy vấn đã được thực thi.

Ví dụ, PostgreSQL hỗ trợ kiểm tra mức cô lập hiện hành bằng:

~~~sql
SHOW transaction_isolation;
SHOW default_transaction_isolation;
~~~

Hai giá trị có thể khác nhau khi transaction hiện tại ghi đè mặc định. Việc kiểm tra phải nằm trong **đúng session/transaction**: chạy lệnh ở một connection khác không chứng minh được hành vi của giao dịch đang điều tra.

Trong JDBC, có thể hỏi **getTransactionIsolation()**, nhưng muốn kết luận chính xác về ngữ nghĩa đang áp dụng trong một transaction, vẫn cần đối chiếu tài liệu driver/DBMS và phạm vi giao dịch thực tế. Các giá trị cấu hình do ứng dụng ghi log cũng có thể không phản ánh những thay đổi SQL session được chạy ngoài cơ chế mà pool theo dõi.

## 12. Tự kiểm tra

**Câu 1.** Session mặc định READ COMMITTED. Trong PostgreSQL, transaction T1 đặt REPEATABLE READ rồi COMMIT. Transaction T2 bắt đầu sau đó mà không ghi đè. T2 dùng isolation nào?

**Trả lời:** Thông thường T2 trở lại READ COMMITTED theo mặc định session, vì REPEATABLE READ được thiết lập riêng cho T1.

**Câu 2.** Request A chạy một SQL thay đổi mức cô lập của session trên connection lấy từ pool, sau đó COMMIT và trả connection. Request B mượn lại connection này. B có chắc dùng mặc định ban đầu không?

**Trả lời:** Không. Nếu thiết lập session chưa được khôi phục và connection vật lý/session tiếp tục được dùng lại, B có thể kế thừa cấu hình của A. Pool không nhất thiết nhận biết SQL SET riêng của DBMS.

**Câu 3.** Trong MySQL, lệnh SET TRANSACTION ISOLATION LEVEL SERIALIZABLE đặt trước START TRANSACTION thường tác động khi nào?

**Trả lời:** Cho giao dịch kế tiếp của session theo cú pháp này; không có nghĩa mọi giao dịch về sau đều SERIALIZABLE.

**Câu 4.** Một phương thức Spring dùng @Transactional(isolation = SERIALIZABLE) được gọi trong một transaction REQUIRED đã hoạt động với READ COMMITTED. Có chắc nó tạo transaction SERIALIZABLE mới không?

**Trả lời:** Không. Với REQUIRED, lời gọi thường tham gia giao dịch hiện tại. Muốn biết hiệu lực phải xét transaction manager và ranh giới giao dịch vật lý.

**Câu 5.** Vì sao không nên gọi setAutoCommit(true) để reset connection khi chưa biết giao dịch đã kết thúc?

**Trả lời:** Theo hợp đồng JDBC, thay đổi từ auto-commit false sang true có thể commit giao dịch đang hoạt động, làm thay đổi dữ liệu ngoài ý định của ứng dụng.

**Câu 6.** Một giao dịch có read-only nhưng isolation READ COMMITTED. Có chắc hai lần SELECT liên tiếp trả cùng một kết quả không?

**Trả lời:** Không. Read-only không tự nâng mức cô lập; những commit từ giao dịch khác có thể làm kết quả đọc thay đổi tùy DBMS và kiểu truy vấn.

## 13. Ghi nhớ để sử dụng đúng

Có thể diễn đạt mối quan hệ như sau: **mặc định của DBMS khởi tạo phiên; phiên có thể cung cấp mặc định cho nhiều giao dịch; Connection là phương tiện ứng dụng điều khiển phiên/giao dịch; và từng transaction có thể có các đặc tính riêng trong thời hạn của nó**.

Để thiết lập an toàn, trước hết trả lời bốn câu hỏi: **thiết lập gì**, **trên thành phần nào**, **bắt đầu có hiệu lực từ lúc nào** và **khi nào giá trị được khôi phục**. Khi sử dụng Spring hoặc JDBC với connection pool, cần quan tâm thêm ranh giới transaction thực sự và cách pool xử lý trạng thái khi tái sử dụng connection.

Sự phân biệt này là nền tảng của vòng đời giao dịch: nó quyết định cách các câu lệnh quan sát dữ liệu, cách những giao dịch cạnh tranh và lý do một cấu hình tưởng chỉ dành cho một request có thể ảnh hưởng đến các request về sau.
