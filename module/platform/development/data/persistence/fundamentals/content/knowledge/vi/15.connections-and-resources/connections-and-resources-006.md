# Phân biệt thời gian chờ kết nối, chờ truy vấn và chờ giao dịch

Một API Java báo “database timeout” chưa cho biết hệ thống đang gặp lỗi gì. Có thể request **chưa lấy được kết nối từ pool**, đã kết nối nhưng **câu SQL đang đợi khóa**, hoặc nhiều câu SQL riêng lẻ đều nhanh nhưng **giao dịch bị giữ mở quá lâu**. Ba tình huống cần ba cách quan sát, giới hạn thời gian và khắc phục khác nhau.

Bài học thuộc chương **Kết nối và tài nguyên** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu của module là hiểu lưu trữ dữ liệu bền vững trong ứng dụng Java, từ mô hình dữ liệu, truy vấn và chỉ mục đến giao dịch, cô lập, xử lý lỗi kết nối, bảo mật và hiệu năng. Bài này tập trung vào **ranh giới thời gian** và **vòng đời tài nguyên JDBC**, minh họa bằng **HikariCP, PostgreSQL, Spring**. Tên tham số, đơn vị và cách hủy thao tác tùy driver, pool, transaction manager và phiên bản cơ sở dữ liệu; cần kiểm tra hệ thống đang dùng thay vì áp một cấu hình cho mọi nền tảng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Chỉ ra điểm bắt đầu và kết thúc của **timeout chờ connection**, **timeout câu truy vấn** và **timeout giao dịch**.
- Phân biệt **đợi lấy connection từ pool**, **thiết lập kết nối mạng tới DB**, **chờ khóa**, **chờ kết quả SQL** và **connection bị bỏ không trong giao dịch**.
- Chọn vị trí áp dụng timeout trong **HikariCP**, **JDBC**, **Spring** và **PostgreSQL**.
- Dự đoán điều gì xảy ra với **transaction đang mở** sau khi một câu SQL hoặc kết nối bị timeout.
- Thiết kế giới hạn thời gian có tính đến deadline HTTP và xử lý lỗi an toàn trước khi retry.
- Dùng metrics, log và một số truy vấn chẩn đoán để xác định nguyên nhân thực tế, tránh tăng timeout một cách tùy tiện.

## 2. Một request đi qua những giai đoạn nào?

Xét API **POST /orders**: service cần lấy một connection, kiểm tra và trừ tồn kho, ghi đơn hàng, rồi commit.

~~~text
HTTP request
    |
    v
[ Chờ pool cấp connection ] ------ timeout lấy connection từ pool
    |
    v
[ Mở TCP/TLS + xác thực ] -------- timeout thiết lập kết nối vật lý
    |        (nếu pool cần tạo connection mới)
    v
[ BEGIN / transaction bắt đầu ]
    |
    +--> [ SQL 1: chờ khóa + thực thi + nhận kết quả ] -- query/statement timeout
    |
    +--> [ Logic Java / SQL 2 / SQL 3 ... ]
    |
    +--> [ COMMIT, gồm các bước đồng bộ cần thiết ]
    |
    v
[ Đóng hoặc trả connection về pool ]
    |
    v
HTTP response
~~~

Sơ đồ là đường đi **khả dĩ**, không phải mọi request đều mở kết nối mạng mới. Pool thường tái sử dụng connection đã mở; với một số transaction manager, việc lấy connection vật lý có thể diễn ra lúc bắt đầu giao dịch hoặc được trì hoãn tới câu SQL đầu tiên. Cần biết điểm khởi đầu thực tế trước khi đặt timeout.

Ba ngân sách thời gian không nhất thiết bắt đầu cùng lúc:

| Loại | Khoảng thời gian chính | Thường do ai cấu hình? | Khi hết thời gian |
| --- | --- | --- | --- |
| **Chờ kết nối từ pool** | Từ lúc mượn connection đến khi pool cấp được | Pool, ví dụ HikariCP **connectionTimeout** | Không mượn được connection đúng hạn; thường chưa chạy câu SQL mới |
| **Thiết lập kết nối vật lý** | TCP/TLS/đăng nhập khi phải tạo connection | Driver/OS, ví dụ PostgreSQL JDBC **connectTimeout** và các timeout đăng nhập liên quan | Kết nối mới không được tạo; pool có thể tiếp tục chiến lược thử tới giới hạn riêng |
| **Chờ truy vấn (statement/query)** | Một câu SQL được gửi/thực thi đến khi hoàn tất theo hợp đồng của thành phần giới hạn | JDBC **Statement.setQueryTimeout**, PostgreSQL **statement_timeout** | Câu SQL bị yêu cầu hủy hoặc DB chấm dứt theo cơ chế của nó; transaction có thể cần rollback |
| **Chờ giao dịch (transaction)** | Một giao dịch từ lúc bắt đầu đến khi kết thúc hoặc vượt deadline | Transaction manager hoặc chính DBMS nếu hỗ trợ | Có thể bị đánh dấu rollback-only, từ chối thao tác hoặc hủy theo cách triển khai; không mặc định ngắt ngay mọi đoạn Java |

**Timeout chờ khóa** là một giới hạn riêng, chỉ tính lúc câu SQL phải đợi lấy lock; nó là một phần có thể có của thời gian câu truy vấn. **Socket read timeout** và **idle-in-transaction timeout** cũng là những cơ chế riêng, không được gộp tên cho tiện.

## 3. Timeout chờ kết nối từ pool

Ứng dụng Java thường dùng **DataSource** với connection pool, ví dụ HikariCP. Pool giữ một số connection vật lý để nhiều request mượn và trả về.

Giả sử pool có tối đa 10 connection. Cả 10 đang bị những request khác giữ, request thứ 11 gọi **dataSource.getConnection()**. Nó phải đợi một connection được trả lại hoặc được pool cấp, trong giới hạn cấu hình. Trong HikariCP, **connectionTimeout** là **thời gian tối đa client đợi để lấy một connection từ pool**, đơn vị **mili giây**.

Ví dụ cấu hình Spring Boot sử dụng HikariCP:

~~~properties
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=2000
~~~

Ở cấu hình này, một request thường không đợi vô hạn trong **getConnection()**: nếu pool không cấp được connection trong giới hạn, nó báo lỗi. Điều đó **không có nghĩa câu SQL được phép chạy tối đa hai giây** và **không có nghĩa mạng tới DB có connect timeout là hai giây**.

### 3.1. Vì sao pool hết connection?

Các nguyên nhân có thể xảy ra:

- Nhiều request đồng thời hơn khả năng phục vụ của pool.
- Câu SQL chạy lâu hoặc chờ khóa, giữ connection quá lâu.
- Giao dịch mở khi service đang gọi HTTP API, gửi email hoặc thực hiện công việc ngoài DB.
- Không đóng **Connection/ResultSet/Statement** đúng cách hoặc framework giữ tài nguyên ngoài phạm vi mong đợi.
- Database chậm hoặc giới hạn số connection, khiến việc tạo/kiểm tra connection mới bị chậm.
- Pool được cấu hình quá nhỏ so với lưu lượng **hoặc** quá lớn so với năng lực database.

Điểm cần nhớ: **pool timeout thường là triệu chứng thiếu connection sẵn dùng**, không tự khẳng định máy database không thể nhận TCP connection. Khi đã có 10 connection đang chờ khóa, tăng pool từ 10 lên 50 có thể làm **nhiều giao dịch cùng tranh khóa hơn**, không khắc phục nguyên nhân.

### 3.2. Vòng đời tài nguyên liên quan trực tiếp đến pool timeout

Trong JDBC thuần, dùng **try-with-resources**:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT id FROM orders WHERE tenant_id = ?")) {

    statement.setLong(1, tenantId);
    try (ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            // Đọc kết quả cần thiết.
        }
    }
} // Đóng tài nguyên; với pool thường trả logical connection cho pool.
~~~

Khi dùng **@Transactional** do Spring quản lý, connection có thể được gắn với transaction hiện tại và được transaction manager trả về pool sau khi kết thúc. Không tự **close()** một connection do framework sở hữu và không mở connection khác bằng **DriverManager** rồi mong nó tham gia transaction hiện có.

Các tên **idleTimeout**, **maxLifetime**, **keepaliveTime**, **validationTimeout**, **leakDetectionThreshold** trong HikariCP không đồng nghĩa **connectionTimeout**:

| Tên tham số | Tác dụng khái quát |
| --- | --- |
| **connectionTimeout** | Giới hạn thời gian đợi mượn connection |
| **validationTimeout** | Giới hạn kiểm tra kết nối còn dùng được |
| **idleTimeout** | Điều chỉnh vòng đời connection nhàn rỗi khi pool có thể co lại |
| **maxLifetime** | Giới hạn tuổi của connection trước khi được thay thế theo chính sách pool; thường không chủ động giết connection đang được sử dụng |
| **keepaliveTime** | Giúp kiểm tra/giữ kết nối nhàn rỗi theo cơ chế pool |
| **leakDetectionThreshold** | Chẩn đoán connection bị giữ quá lâu; cảnh báo không tự kết luận chắc chắn có leak |

Không nên tăng **maximumPoolSize** trước khi xem metrics **active, idle, pending**, độ trễ SQL và tình trạng DB.

## 4. Timeout kết nối mạng: khác timeout mượn connection

Pool có thể phải tạo connection vật lý, nhất là lúc ứng dụng khởi động, connection cũ bị ngắt hoặc tải tăng. Khi đó còn các bước:

~~~text
getConnection()
   |
   +--> chờ một slot/connection trong pool
   |
   +--> nếu pool cần tạo mới:
          DNS -> TCP connect -> TLS -> authentication -> session setup
~~~

Với PostgreSQL JDBC, **connectTimeout** là tham số cho thao tác kết nối socket, tính bằng **giây**. Ví dụ URL minh họa:

~~~text
jdbc:postgresql://db.example.internal:5432/app?connectTimeout=3
~~~

Hãy phân biệt:

- **HikariCP connectionTimeout=2000** là **2.000 ms chờ pool cấp connection**.
- **PostgreSQL JDBC connectTimeout=3** là **3 giây cho thiết lập kết nối socket** trong phạm vi driver hỗ trợ.
- **DataSource/DriverManager loginTimeout** là cơ chế/giới hạn khác liên quan đến việc thiết lập kết nối, mức độ hỗ trợ tùy driver và cách DataSource được tạo.
- **TCP keepalive**, DNS timeout, TLS handshake và các thành phần mạng khác có thể có quy tắc thời gian riêng. Không suy ra chỉ một tham số connectTimeout kiểm soát mọi bước và mọi cách thử host.

Khi xuất hiện lỗi kết nối, log nên cho biết request đang **chờ pool**, **mở TCP**, **xác thực** hay **đã chạy SQL**. Phân loại sai dễ dẫn tới cách sửa vô ích: tăng query timeout không giúp gì nếu request chưa mượn được connection.

## 5. Timeout truy vấn: thời gian của một statement

Sau khi có connection, một câu SQL vẫn có thể chậm vì:

1. **Chờ khóa** của transaction khác.
2. **Quét, join, sort, aggregate** quá nhiều dữ liệu hoặc kế hoạch thực thi không phù hợp.
3. **Truy cập đĩa/mạng** chậm.
4. **Trả quá nhiều kết quả** khiến việc truyền và tiêu thụ dữ liệu kéo dài, tùy cơ chế timeout.

Trong JDBC, có thể đặt **Statement.setQueryTimeout(int seconds)** trước khi chạy câu lệnh:

~~~java
String sql = """
    SELECT id, created_at
    FROM orders
    WHERE tenant_id = ?
    ORDER BY created_at DESC
    LIMIT 50
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, tenantId);
    statement.setQueryTimeout(2); // JDBC: giây, áp dụng cho statement này.
    try (ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            // Chuyển từng hàng sang đối tượng kết quả.
        }
    }
}
~~~

Theo hợp đồng JDBC, **setQueryTimeout(0)** thường có nghĩa không giới hạn thời gian từ phía thuộc tính này. Việc driver **thực thi, hủy và báo lỗi** khi hết timeout có thể khác nhau. Đây không phải cam kết rằng mọi blocking I/O hoặc toàn bộ đoạn code xử lý ResultSet trong Java luôn bị ngắt sau đúng hai giây.

### 5.1. Timeout phía database: PostgreSQL statement_timeout

PostgreSQL cung cấp **statement_timeout** để giới hạn thời gian câu lệnh ở phía server:

~~~sql
-- Ví dụ trên một phiên thử nghiệm.
SET statement_timeout = '2s';

SELECT pg_sleep(3);
-- PostgreSQL thường hủy câu lệnh do vượt statement_timeout.
~~~

Với một transaction cụ thể, nên giới hạn phạm vi cấu hình:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '2s';

-- Những statement tiếp theo trong transaction chịu giới hạn đó.
SELECT count(*) FROM orders;
COMMIT;
~~~

**SET LOCAL** chỉ có hiệu lực trong transaction hiện tại và trở lại cấu hình trước sau khi transaction kết thúc. Tránh **SET** ở mức session rồi trả connection về pool khi chưa bảo đảm reset; request sau có thể thừa hưởng timeout không mong muốn.

**statement_timeout** tính ở phía PostgreSQL theo vòng đời statement được server xử lý; thời điểm bắt đầu và kết thúc có khác biệt kỹ thuật giữa simple query và extended query protocol. Không sử dụng nó như đồng hồ tổng cho toàn bộ request HTTP hoặc cho mọi công việc Java ở giữa các SQL statement.

### 5.2. Query timeout và socket timeout không phải một

PostgreSQL JDBC cũng có thuộc tính **socketTimeout** (đơn vị giây), có liên quan đến thời gian đợi **đọc dữ liệu trên socket**. Đây là bảo vệ ở tầng I/O mạng; nó không phải công tắc “cho SQL chạy trong N giây rồi hủy an toàn”, và khi kích hoạt có thể khiến connection không thể tiếp tục dùng được.

Một statement timeout được server xử lý có thể hủy chính câu SQL mà kết nối vẫn sống; một socket timeout có thể xuất phát từ mạng không truyền được dữ liệu dù server còn đang chạy. Cách xử lý connection và transaction sau lỗi phải dựa trên trạng thái thực tế.

## 6. Lock timeout: một nguyên nhân riêng khiến SQL “đứng”

Giả sử T1 cập nhật đơn hàng rồi giữ giao dịch mở. T2 cố sửa đúng hàng đó:

~~~text
T1                              T2
BEGIN;
UPDATE orders WHERE id=100;
                                BEGIN;
                                UPDATE orders WHERE id=100;
                                --> chờ lock do T1 giữ
   ... chưa COMMIT ...
~~~

Đối với T2, tổng thời gian statement gồm cả thời gian chờ lock. PostgreSQL có **lock_timeout** để chỉ giới hạn thời gian đợi lấy khóa:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '3s';

UPDATE orders
SET status = 'PROCESSING'
WHERE id = 100;

COMMIT;
~~~

Nếu câu UPDATE phải đợi khóa quá **500 ms**, PostgreSQL có thể hủy câu lệnh vì **lock_timeout** trước khi đạt **statement_timeout**. Nếu không chờ khóa mà chỉ chạy chậm, **statement_timeout** mới là giới hạn có ý nghĩa. Thông thường việc đặt **lock_timeout >= statement_timeout** không hữu ích, vì statement timeout có thể xảy ra trước.

Trong PostgreSQL, **lock_timeout** không phải “chờ tới khi toàn giao dịch hết khóa” và cũng không phải thông số điều chỉnh timeout khi mượn connection. Một statement có thể phải lấy nhiều khóa; timeout liên quan tới các lượt chờ khóa theo quy tắc của server.

**Phản ứng sau lỗi:** ở PostgreSQL, nếu một statement bên trong giao dịch thất bại, giao dịch thường chuyển sang trạng thái **aborted**. Các statement tiếp theo bị từ chối cho đến khi **ROLLBACK** (hoặc phục hồi phù hợp qua savepoint đã thiết lập). Không bắt lỗi timeout rồi tiếp tục COMMIT như thể không có gì xảy ra.

## 7. Timeout giao dịch: ranh giới bao trùm nhiều statement

Một nghiệp vụ đặt hàng cần ba bước:

~~~text
BEGIN transaction
    UPDATE inventory             1,2 giây
    INSERT orders                0,7 giây
    INSERT order_audit           1,4 giây
COMMIT
~~~

Nếu mỗi statement có **query timeout = 2 giây**, cả ba câu SQL vẫn có thể thành công; tổng thời gian phần SQL đã là **3,3 giây**, chưa kể thời gian Java, commit hoặc chờ giữa các lệnh. **Giới hạn hai giây trên từng statement không phải giới hạn hai giây cho cả giao dịch.**

**Transaction timeout** nhằm đặt một deadline cho **phạm vi giao dịch**, có thể bao gồm nhiều câu SQL và khoảng thời gian giữa chúng. Tuy vậy, cơ chế thực thi khác nhau:

- Một **transaction manager** có thể lưu deadline, áp giới hạn còn lại lên các statement, rồi đánh dấu rollback-only hoặc báo lỗi nếu đã quá thời hạn.
- Một **DBMS** có thể có tham số timeout cho toàn transaction hoặc chỉ cho tình huống **idle trong transaction**; phạm vi và hành vi cắt kết nối tùy hệ.
- Không nên giả định timeout giao dịch trong framework có khả năng **ngắt ngay một vòng lặp Java đang chạy CPU** hoặc hủy chắc chắn mọi lệnh gọi dịch vụ bên ngoài. Những bước đó cần timeout/cancellation riêng.

### 7.1. Spring @Transactional(timeout = ...)

Với Spring transaction manager phù hợp:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderDao dao;

    public OrderService(OrderDao dao) {
        this.dao = dao;
    }

    @Transactional(timeout = 5)
    public void placeOrder(long tenantId, long productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải > 0");
        }

        int changed = dao.decreaseStockIfAvailable(
                tenantId, productId, quantity);
        if (changed != 1) {
            throw new IllegalStateException("Không đủ tồn kho");
        }

        dao.insertOrder(tenantId, productId, quantity);
    }
}
~~~

Annotation trên yêu cầu deadline **5 giây** cho **transaction mới** được quản lý theo hợp đồng của transaction manager. Nó **không** biến riêng từng SQL thành câu lệnh có query timeout cố định bằng năm giây trong mọi driver, cũng không bảo đảm timer sẽ bất ngờ dừng ngay mọi đoạn Java đang chạy.

Những điểm dễ bỏ sót:

- Nếu method tham gia một giao dịch cha đã mở theo propagation **REQUIRED**, timeout của method con thường **không thay deadline** của transaction cha. Cấu hình timeout tại **ranh giới mở transaction thực tế**.
- Với Spring proxy thông dụng, **self-invocation** như **this.placeOrder(...)** có thể bỏ qua interceptor **@Transactional**.
- DAO cần tham gia cùng transaction manager; nếu tự mở connection độc lập, giới hạn của transaction cha có thể không bao phủ truy vấn đó.
- Sau timeout/rollback-only, việc cố commit có thể báo lỗi tại cuối method; tùy manager và hành vi driver, exception có thể xuất hiện khi thực thi statement hoặc khi kết thúc transaction.
- Timeout không thay thế rollback rule: Spring thường rollback với **RuntimeException**/**Error** theo mặc định; cần xác định cách xử lý checked exception và tránh nuốt lỗi rồi trả kết quả “thành công”.

### 7.2. Idle-in-transaction timeout không phải tổng thời gian transaction

PostgreSQL có **idle_in_transaction_session_timeout** để kết thúc session **nằm ở trạng thái idle trong một transaction** lâu hơn ngưỡng. Ví dụ:

~~~sql
SET idle_in_transaction_session_timeout = '10s';
~~~

Giới hạn này hữu ích khi ứng dụng mở transaction, chạy một câu SELECT rồi **để kết nối chờ không chạy lệnh SQL**. Nó **không** đồng nghĩa “mọi transaction phải hoàn tất trong 10 giây”: một statement đang chạy lâu không được đo như thời gian *idle in transaction*. Khi session bị đóng, transaction chưa commit bị rollback theo cơ chế DB; connection pool phải phát hiện và thay thế connection hỏng.

Một số phiên bản hoặc hệ quản trị có tính năng **transaction_timeout** riêng. Trước khi sử dụng, phải kiểm tra phiên bản PostgreSQL thực tế và phạm vi tham số; không coi **idle_in_transaction_session_timeout**, **statement_timeout** và transaction timeout là ba tên gọi tương đương.

## 8. So sánh trên một tình huống thực tế

Giả sử request tạo đơn hàng từ một service có pool tối đa 20 connection:

| Diễn biến | Timeout có khả năng liên quan nhất | Nguyên nhân nên tìm |
| --- | --- | --- |
| Request đợi **getConnection()** rồi thất bại | **Pool acquisition timeout** | Pool active/pending, leak, transaction dài, SQL chậm |
| Pool cố mở connection mới nhưng host DB không trả lời TCP | **Physical connect timeout** | DNS, firewall, route, DB listener, giới hạn kết nối |
| SQL UPDATE đang chờ hàng bị giao dịch khác khóa | **Lock timeout** hoặc **statement timeout** | Transaction nào đang giữ lock; vì sao commit chậm |
| SQL SELECT chạy full scan hoặc sort lớn | **Statement/query timeout** | Index, execution plan, dữ liệu và thống kê |
| SQL đã gửi nhưng client không nhận được dữ liệu qua mạng | **Socket read/network timeout** | Network, driver, server; tính là kết nối còn dùng được không |
| Ba câu SQL đều hoàn tất nhưng transaction bị giữ mở quá lâu | **Transaction timeout** hoặc **idle-in-transaction timeout** tùy trạng thái | Công việc ngoài DB, logic giữa các câu, ranh giới service |
| Client timeout khi gửi COMMIT | **Network/commit uncertainty** | Xác định server đã commit hay chưa bằng request ID |

Ví dụ, cùng lỗi “request quá 5 giây” có thể do **pool wait 4 giây + SQL 1 giây** hoặc **pool wait 0 giây + lock wait 5 giây**. Mở thêm index có thể giúp tình huống SQL full scan, nhưng không giải quyết giao dịch giữ khóa quá lâu; tăng connection pool có thể không giải quyết deadlock hoặc hàng nóng.

## 9. Cách chọn ngân sách thời gian cho API

Giả sử mục tiêu phục vụ API là **không quá 6 giây** trong trường hợp thông thường và reverse proxy/client có deadline tương ứng. Một bộ giới hạn **minh họa**, cần điều chỉnh bằng số liệu:

~~~text
Deadline HTTP tổng:                       6,0 s
   |
   +-- Chờ pool tối đa:                   0,8 s
   +-- Mở kết nối vật lý:                 có giới hạn riêng theo driver
   +-- Transaction của nghiệp vụ:        4,0 s
          |
          +-- Lock wait mỗi lần:          0,5 s
          +-- Mỗi SQL statement:          2,0 s
          +-- Logic và commit:            phần thời gian còn lại
   |
   +-- Dự phòng serialization, logging, phản hồi HTTP
~~~

**Các con số là giới hạn lồng nhau, không phải các thời gian cần cộng tất cả**. Một query timeout 2 giây có thể áp nhiều lần trong giao dịch 4 giây; transaction timeout không mặc định ngắt mọi đoạn Java, nên deadline HTTP và timeout các call ngoài DB vẫn phải được quản lý riêng.

Khi thiết kế, nên:

1. Xác định **SLO và deadline end-to-end** của request, sau đó lập ngân sách cho từng chặng có tài nguyên bị giữ.
2. Đặt **pool acquisition timeout** đủ ngắn để hệ thống fail fast khi pool đã quá tải nhưng không quá thấp so với thời gian mượn/trả thực tế.
3. Đặt **statement timeout** dựa trên độ trễ truy vấn bình thường và trường hợp tải cao có thể chấp nhận; đo cả p95/p99.
4. Đặt **lock timeout** khi nghiệp vụ ưu tiên trả lỗi/retry hơn là chờ một khóa quá lâu.
5. Đặt **transaction timeout** ở service boundary, phù hợp tổng chuỗi thao tác và mức cô lập.
6. Giữ khoảng dự phòng cho **commit**, phản hồi và xử lý lỗi, tránh để HTTP timeout xảy ra trước lúc DB kết luận giao dịch.
7. Định nghĩa **retry/backoff/idempotency** cho lỗi có thể hồi phục; không biến một timeout thành cơn bão retry.

Các deadline ở nhiều lớp có thể tranh nhau: client có thể bỏ cuộc trước khi JDBC hoặc DB dừng việc đang làm. Cần thiết kế cancellation, transaction cleanup và correlation ID để request bị hủy không giữ connection/khóa vô hạn.

## 10. Chạy một giao dịch JDBC có statement timeout và rollback rõ ràng

Đoạn sau minh họa **một giao dịch chứa hai bước**, trong đó câu UPDATE được đặt query timeout, và mọi lỗi đều dẫn đến cố gắng rollback. Ví dụ giả định bảng **inventory** và **orders** đã tồn tại, khóa tenant/sản phẩm duy nhất và số lượng phải dương.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void createOrder(long tenantId, long productId, int quantity)
            throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                String decrease = """
                    UPDATE inventory
                    SET available = available - ?
                    WHERE tenant_id = ?
                      AND product_id = ?
                      AND available >= ?
                    """;
                try (PreparedStatement st = connection.prepareStatement(decrease)) {
                    st.setQueryTimeout(2);
                    st.setInt(1, quantity);
                    st.setLong(2, tenantId);
                    st.setLong(3, productId);
                    st.setInt(4, quantity);
                    if (st.executeUpdate() != 1) {
                        throw new IllegalStateException("Không đủ tồn kho");
                    }
                }

                String insert = """
                    INSERT INTO orders(tenant_id, product_id, quantity)
                    VALUES (?, ?, ?)
                    """;
                try (PreparedStatement st = connection.prepareStatement(insert)) {
                    st.setQueryTimeout(2);
                    st.setLong(1, tenantId);
                    st.setLong(2, productId);
                    st.setInt(3, quantity);
                    st.executeUpdate();
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

**Đọc đúng giới hạn ví dụ:** đây là **hai statement có setQueryTimeout(2)**, không phải một transaction được đảm bảo kết thúc sau hai giây hoặc bốn giây. Muốn giới hạn toàn giao dịch, dùng transaction manager và/hoặc tính năng của DBMS phù hợp. Với connection từ pool, đoạn code sở hữu connection cho lời gọi này và đóng nó khi kết thúc; nếu một framework đã sở hữu connection, phải để framework điều phối.

Nếu timeout xảy ra bên trong PostgreSQL transaction, rollback là bước quan trọng trước khi trả connection về pool. Khi **rollback cũng thất bại**, connection có thể không còn đáng tin cậy; không cố dùng nó cho truy vấn tiếp theo. Pool phải phát hiện và loại bỏ/khôi phục kết nối theo khả năng của mình.

**Không retry mù quáng** cả phương thức **createOrder()** sau khi lỗi kết nối xảy ra tại **commit()**: server có thể đã commit và phản hồi bị mất. Nghiệp vụ đặt hàng cần thêm **request_id**/idempotency key và unique constraint để xác minh trạng thái trước khi thực hiện lại.

## 11. Quy tắc timeout khi dùng Spring, JPA và ORM

Một ứng dụng Spring thường có nhiều lớp cấu hình:

~~~text
HTTP client/reverse proxy deadline
          |
Service @Transactional(timeout = ...)
          |
Repository / JPA query hints / JdbcTemplate
          |
HikariCP / DataSource
          |
PostgreSQL JDBC driver
          |
PostgreSQL server statement_timeout, lock_timeout, ...
~~~

Không có một thuộc tính duy nhất ở trên tự bao phủ và chấm dứt chắc chắn mọi giai đoạn bên dưới. Ví dụ:

- **@Transactional(timeout = 5)** gắn với giao dịch được transaction manager quản lý. Khả năng truyền thời gian còn lại xuống SQL tùy **Spring JDBC/JPA**, transaction manager và các API tham gia.
- **JPA query timeout hint** (ví dụ **jakarta.persistence.query.timeout**, tính bằng mili giây theo JPA) có phạm vi truy vấn và mức hỗ trợ tùy provider/driver; cần xác minh bản dịch cuối cùng tới JDBC hoặc DB.
- **JdbcTemplate.setQueryTimeout(...)** đặt giới hạn cho các statement mà template tạo theo hợp đồng Spring/JDBC; khi có transaction timeout, Spring có thể áp thời gian còn lại phù hợp lên statement.
- **HikariCP connectionTimeout** chỉ điều phối việc mượn connection, không phải thời gian chạy query JPA.
- **PostgreSQL statement_timeout** chạy ở DB và có thể chặn những statement gửi từ các client khác, nếu thiết lập ở phạm vi database/role/session. Với pool, tránh session setting rò từ request này sang request khác.

Khi đọc cấu hình Spring, luôn kiểm tra **đường thực thi thực tế**: lời gọi có đi qua proxy @Transactional không, DAO có dùng đúng DataSource/EntityManager tham gia giao dịch không, và log SQL có được gửi tới DB trước thời điểm deadline không?

### 11.1. Timeout không tự động chuyển thành HTTP 504

Một timeout của pool, JDBC hoặc DB thường phát sinh **exception ở tầng persistence**. Service/controller cần chuyển thành phản hồi API phù hợp với hợp đồng sản phẩm, ghi nhận trace và có chính sách retry ở phía client. HTTP **504 Gateway Timeout** thường là quyết định của gateway/proxy khi không nhận phản hồi kịp, không phải mã mặc định của mọi lỗi SQL timeout.

## 12. Timeout khác cancellation và rollback

Các khái niệm này liên quan nhưng không đồng nhất:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Timeout** | Đã vượt ngưỡng thời gian mà một tầng cho phép |
| **Cancellation** | Một thành phần yêu cầu hủy câu SQL hoặc tác vụ |
| **Rollback** | Hủy các thay đổi chưa commit thuộc một transaction |
| **Connection close / invalidate** | Đóng hoặc loại bỏ phiên kết nối, có thể khiến transaction chưa commit bị hủy |
| **HTTP request canceled** | Client/gateway ngừng chờ; DB có thể vẫn đang xử lý nếu không được truyền tín hiệu hủy |

Ví dụ PostgreSQL báo lỗi **statement timeout**, câu SQL đang chạy bị hủy. Nếu bên trong transaction, transaction thường ở trạng thái aborted và phải rollback. Việc client HTTP ngừng nhận phản hồi không tự bảo đảm câu SQL và transaction đã bị dừng; ứng dụng phải có cơ chế đóng vòng đời tài nguyên phù hợp.

Khi một **socket timeout** khiến client không biết trạng thái kết nối, phải thận trọng với transaction đã gửi commit. Nếu mất kết nối **trước khi bắt đầu transaction**, chưa có thay đổi nghiệp vụ nào để rollback; nếu lỗi ở **thời điểm COMMIT**, kết quả có thể chưa rõ từ phía client.

## 13. Phân loại lỗi trước khi retry

Không phải mọi timeout đều nên được xử lý bằng “thử lại ngay”:

| Lỗi/tình huống | Điều đã biết | Cách phản ứng phù hợp |
| --- | --- | --- |
| Pool acquisition timeout trước khi chạy SQL | Request chưa mượn được connection để thực hiện thao tác mới | Fail fast, backpressure, điều chỉnh tải/pool, retry có jitter nếu phù hợp |
| Connect timeout khi tạo connection mới | Không kết nối tới DB thành công | Kiểm tra mạng/DB, retry có giới hạn và circuit breaker |
| PostgreSQL **statement_timeout** | Statement bị server hủy theo timeout | Rollback transaction đang lỗi, tối ưu truy vấn hoặc chọn timeout hợp lý; chỉ retry nếu an toàn |
| PostgreSQL **lock_timeout** | Không lấy được lock đúng hạn | Tìm transaction giữ lock, giảm thời gian giữ khóa; retry có backoff nếu nghiệp vụ cho phép |
| Transaction timeout/rollback-only | Unit of work không đạt thời gian cho phép | Kết thúc/rollback, xem phạm vi transaction và các bước kéo dài |
| Mất kết nối trong lúc COMMIT | Client không chắc server đã commit hay chưa | Đối soát qua request ID, unique constraint, idempotency trước khi retry |
| Deadlock/serialization failure | Hệ quản trị có thể hủy một transaction để bảo vệ tính đúng đắn | Retry **toàn bộ transaction** với giới hạn và backoff |

Trong PostgreSQL, một số SQLSTATE hữu ích khi chẩn đoán gồm **57014** (query canceled, có thể từ statement timeout hoặc cancellation), **55P03** (lock not available, có thể liên quan lock timeout), **40001** (serialization failure), **40P01** (deadlock detected). Không suy nguyên nhân chỉ từ một mã khi có nhiều cách kích hoạt; đọc cả message, metadata, log server và trace tương ứng.

Nếu transaction đang giữ nhiều bước nghiệp vụ, retry một câu UPDATE cuối cùng trong transaction đã abort **không** phải cách phục hồi đúng. Cần khởi tạo transaction mới, đọc lại trạng thái liên quan và xử lý tác dụng phụ ngoài DB bằng cơ chế idempotent hoặc outbox thích hợp.

## 14. Quan sát đúng tín hiệu của pool và database

Để tìm nguyên nhân gốc, ghi nhận độ trễ từng chặng:

~~~text
request_latency
  pool_acquire_latency
  sql_execute_latency
    lock_wait_latency (nếu đo được)
    db_execution/IO
  transaction_duration
  response_latency
~~~

Các chỉ số có ý nghĩa:

- **Pool:** số connection **active/idle/pending**, thời gian mượn, timeout cấp connection, số connection được tạo/đóng, cảnh báo giữ connection lâu.
- **JDBC/ORM:** độ trễ từng câu SQL, số lần retry, số hàng đọc/trả về, statement bị hủy và exception.
- **Transaction:** thời gian từ BEGIN đến COMMIT/ROLLBACK, số giao dịch idle, giao dịch bị rollback do timeout, tỷ lệ deadlock và serialization failure.
- **Database:** lock wait, wait event, thống kê statement, bloat/IO khi có giao dịch dài, số connection hiện tại và giới hạn cấu hình.
- **HTTP:** deadline, cancellation và thời gian còn lại khi bắt đầu truy cập DB.

### 14.1. Ví dụ chẩn đoán PostgreSQL

Trên môi trường có quyền quan sát phù hợp:

~~~sql
SELECT pid,
       state,
       wait_event_type,
       wait_event,
       now() - xact_start AS transaction_age,
       now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Trường **state = 'idle in transaction'** có thể chỉ một connection đang giữ transaction mở dù không chạy SQL. **wait_event_type = 'Lock'** giúp nhận biết một số trường hợp đang chờ lock. **query_age** và **transaction_age** dùng mốc khác nhau; không coi mọi dòng có query_age lớn là câu SQL đang chạy liên tục vì **query_start** còn có ý nghĩa theo trạng thái session.

Xem PID nào đang chờ và PID nào chặn (hàm PostgreSQL trả mảng PID blocker):

~~~sql
SELECT pid,
       pg_blocking_pids(pid) AS blocking_pids,
       state,
       wait_event_type,
       wait_event
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
~~~

Không nên tự động **terminate backend** chỉ dựa trên một snapshot thống kê. Cần xác định transaction chủ sở hữu, yêu cầu nghiệp vụ liên quan và tác động của việc hủy.

### 14.2. Đừng ghi dữ liệu nhạy cảm vào log timeout

Log nên có **request ID, transaction/correlation ID, loại timeout, giai đoạn xảy ra, độ trễ và mã lỗi**. Việc log toàn bộ SQL cùng tham số có thể làm lộ định danh khách hàng, token hoặc dữ liệu cá nhân; cần dùng log chuẩn hóa, che dữ liệu nhạy cảm và giới hạn quyền truy cập.

## 15. Bảng quyết định nhanh để xử lý sự cố

| Triệu chứng ban đầu | Câu hỏi đầu tiên | Hướng điều tra tiếp |
| --- | --- | --- |
| “Connection is not available, request timed out” từ Hikari | Có connection nào active quá lâu không? | Metrics pool, code không trả connection, transaction dài |
| Lỗi khi ứng dụng vừa khởi động | DB host/port/DNS/auth có hoạt động không? | Driver connect/login, giới hạn kết nối, mạng |
| SELECT thường nhanh nhưng thỉnh thoảng đứng | Có lock, I/O hoặc kế hoạch truy vấn khác không? | pg_stat_activity, wait event, EXPLAIN phù hợp |
| UPDATE bị hủy sau 500 ms | Có đặt lock_timeout không? | Transaction giữ khóa, thứ tự cập nhật, độ dài transaction |
| Nhiều SQL đều nhanh nhưng service timeout | Transaction chờ gì giữa các statement? | Logging theo bước, API bên ngoài, CPU, @Transactional boundary |
| API báo lỗi nhưng bản ghi đã tạo | Lỗi có xảy ra đúng lúc nhận kết quả COMMIT không? | Trạng thái request ID, idempotency, tránh thực hiện lại |
| Hết connection khi tải tăng | Pool bận vì query/lock hay vì cấu hình? | Số active/pending, tài nguyên DB, backpressure |

## 16. Các lỗi thiết kế cần tránh

1. **Dùng một từ “connection timeout” cho hai thứ khác nhau.** Thời gian mượn connection từ HikariCP là mili giây, còn PostgreSQL JDBC **connectTimeout** thường là giây và áp dụng cho socket connect.
2. **Tăng query timeout để sửa pool exhausted.** Nếu request chưa chạy SQL, tăng query timeout chỉ có thể khiến những request đang giữ connection lâu hơn.
3. **Cho rằng mọi timeout là do truy vấn không có index.** Câu SQL có thể đang chờ khóa, session bị mất mạng hoặc transaction bị để idle.
4. **Coi ba statement timeout 2 giây như transaction timeout 2 giây.** Các statement có thể chạy lần lượt; thời gian transaction còn bao gồm logic Java và commit.
5. **Dùng idle-in-transaction timeout để hạn chế tổng thời gian chạy transaction.** Nó chỉ xử lý khoảng idle bên trong một transaction theo quy tắc server.
6. **Nuốt exception rồi cố commit sau statement timeout.** PostgreSQL thường cần rollback transaction bị abort.
7. **Cấu hình SET statement_timeout ở session nhưng không reset trước khi trả connection về pool.** Request sau có thể nhận giới hạn còn sót lại.
8. **Đặt @Transactional(timeout) trên method gọi nội bộ rồi mặc định có tác dụng.** Với Spring proxy thường gặp, self-invocation bỏ qua interceptor.
9. **Retry giao dịch sau lỗi commit chưa rõ trạng thái mà không có idempotency.** Có nguy cơ tạo đơn, chuyển tiền hoặc gửi sự kiện hai lần.
10. **Tăng kích thước pool theo lưu lượng mà không xét giới hạn DB.** Quá nhiều connection có thể tăng tranh chấp và dùng thêm bộ nhớ trên server.
11. **Giữ giao dịch mở trong lúc gọi API ngoài hoặc chờ người dùng.** Pool bị chiếm và khóa tồn tại lâu; cần thiết kế ranh giới giao dịch ngắn.
12. **Đặt timeout HTTP ngắn hơn đường commit cần thiết mà không có đối soát.** Client bỏ cuộc không có nghĩa DB rollback.

## 17. Bài tập thực hành

### Bài 1. Đợi pool hay đợi database?

HikariCP có **maximumPoolSize=5**, cả năm connection đang được request khác sử dụng. Request thứ sáu đợi **getConnection()** trong hai giây rồi lỗi. Loại timeout nào đã xảy ra? Có nên tăng **statement_timeout** trên PostgreSQL để sửa ngay không?

**Gợi ý:** Đó là **pool acquisition timeout**, chưa đủ bằng chứng request đã chạy SQL. Kiểm tra active/pending, connection bị giữ lâu, query/transaction latency trước khi điều chỉnh pool. Tăng statement timeout không giải quyết việc mượn connection và có thể làm tình hình tệ hơn.

### Bài 2. Ba truy vấn đều dưới ngưỡng

Một transaction chạy SQL A mất 1,8 giây, SQL B mất 1,5 giây và SQL C mất 1,7 giây. Mỗi statement được đặt query timeout 2 giây. Có thể khẳng định toàn transaction luôn dưới hai giây không?

**Gợi ý:** **Không**. Riêng tổng thời gian SQL đã là 5 giây, chưa tính logic Java và commit. Cần transaction timeout hoặc deadline ở tầng service nếu có yêu cầu giới hạn toàn đơn vị nghiệp vụ.

### Bài 3. Chờ khóa

T1 mở transaction, UPDATE hàng 10, chờ 20 giây mới COMMIT. T2 UPDATE cùng hàng với **lock_timeout='500ms'**, **statement_timeout='5s'**. T2 nhiều khả năng gặp timeout nào trước?

**Gợi ý:** Nếu T2 phải đợi lock, **lock_timeout** 500 ms thường xảy ra trước statement timeout 5 giây. Cần tìm và rút ngắn giao dịch T1, không chỉ tăng ngưỡng của T2.

### Bài 4. Spring transaction timeout

Một service **@Transactional(timeout=5)** gọi phương thức DAO mất 1 giây, sau đó gọi HTTP API ngoài mất 10 giây. Có thể tin rằng transaction manager chắc chắn ngắt lệnh HTTP ngay giây thứ năm không?

**Gợi ý:** **Không**. Transaction timeout không phải timer có khả năng ngắt mọi đoạn code Java hay HTTP call. Đặt timeout riêng cho HTTP client và hạn chế thực hiện call ngoài DB trong transaction.

### Bài 5. Statement lỗi trong PostgreSQL

Trong transaction T1, một SELECT bị PostgreSQL hủy do **statement_timeout**. Ứng dụng catch SQLException rồi chạy INSERT tiếp, sau đó COMMIT. Vì sao cách này sai?

**Gợi ý:** Trong PostgreSQL, lỗi câu lệnh thường khiến transaction ở trạng thái aborted. Phải rollback hoặc xử lý bằng savepoint đã tạo hợp lệ; không tiếp tục như transaction vẫn bình thường.

### Bài 6. Timeout khi commit

Ứng dụng gửi COMMIT cho việc thanh toán, mạng đứt và HTTP client nhận lỗi. Có nên chạy lại toàn bộ giao dịch ngay?

**Gợi ý:** **Không** nếu chưa có cơ chế đảm bảo không lặp. DB có thể đã commit. Cần request ID duy nhất, unique constraint, kiểm tra trạng thái và chiến lược retry an toàn.

### Bài 7. Phân biệt idle timeout

Một transaction PostgreSQL mở 30 giây, trong đó câu SQL đầu chạy 25 giây và sau đó session idle 5 giây. Nếu chỉ bật **idle_in_transaction_session_timeout='10s'**, có chắc session bị ngắt ở giây thứ 10 kể từ BEGIN không?

**Gợi ý:** **Không**. Tham số này đo khoảng **idle trong transaction** theo quy tắc server; thời gian câu SQL đang chạy không được tính như idle. Cần một cơ chế giới hạn toàn transaction khác nếu đó là mục tiêu.

### Bài 8. Thiết kế ngân sách

API có deadline 4 giây, nhưng pool timeout 10 giây và statement timeout 15 giây. Điều gì có thể xảy ra khi client bỏ cuộc?

**Gợi ý:** DB hoặc service có thể tiếp tục giữ connection, chạy SQL hoặc transaction sau khi client đã ngừng chờ. Nên thiết kế timeout từng giai đoạn ngắn hơn deadline phù hợp, truyền cancellation nếu có thể, và xử lý trường hợp commit không rõ kết quả.

## 18. Ghi nhớ

**Timeout kết nối** trả lời “ứng dụng có lấy/mở được connection đúng hạn không?”. **Timeout truy vấn** trả lời “một câu SQL có hoàn thành đúng hạn không?”. **Timeout giao dịch** trả lời “toàn bộ đơn vị công việc nhiều bước có được kết thúc trong thời gian cho phép không?”. Ba ranh giới này liên quan đến nhau nhưng **khác phạm vi, khác thời điểm bắt đầu, khác tầng cấu hình và khác cách xử lý lỗi**.

Khi thiết kế tầng persistence Java, hãy quan sát **pool wait, network connect, lock wait, statement execution, transaction duration và HTTP deadline** như những tín hiệu riêng. Dùng timeout để giới hạn việc chiếm tài nguyên và trả lỗi đúng lúc; sau lỗi phải **rollback/đóng tài nguyên đúng cách**, xác định trạng thái giao dịch khi commit không chắc chắn và chỉ retry khi an toàn. Độ tin cậy đến từ ranh giới tài nguyên rõ ràng, số đo thực tế và các bất biến nghiệp vụ được bảo vệ, chứ không chỉ từ một con số timeout lớn hơn.
