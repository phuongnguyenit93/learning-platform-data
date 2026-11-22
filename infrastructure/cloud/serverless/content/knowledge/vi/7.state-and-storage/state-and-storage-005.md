# Connection pooling, database proxy và dịch vụ dữ liệu serverless

Trong chương **Trạng thái và lưu trữ**, một trong những vấn đề vận hành quan trọng của ứng dụng serverless là quản lý kết nối đến cơ sở dữ liệu. Một ứng dụng chạy trên máy chủ dài hạn thường có số lượng tiến trình tương đối ổn định, vì vậy nhóm phát triển có thể tạo một connection pool với kích thước dự đoán được. Với FaaS, số execution environment có thể tăng nhanh theo lưu lượng. Nếu mỗi function invocation tự mở kết nối mới, cơ sở dữ liệu có thể cạn giới hạn kết nối dù lượng truy vấn thực tế chưa lớn.

Connection pooling, database proxy và các dịch vụ dữ liệu serverless giải quyết những phần khác nhau của bài toán. Pool tái sử dụng kết nối trong một tiến trình hoặc execution environment. Proxy quản lý kết nối giữa nhiều client và cơ sở dữ liệu. Dịch vụ dữ liệu serverless cung cấp mô hình truy cập và khả năng mở rộng được quản lý bởi nền tảng. Chọn đúng cách kết hợp giúp Java function xử lý trạng thái bền vững, kiểm soát quyền truy cập, giảm cold start và giữ chi phí trong giới hạn.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Vì function có thể được khởi tạo, tái sử dụng hoặc nhân rộng theo tải, thiết kế kết nối phải tính đến vòng đời instance, concurrency, timeout, retry và giới hạn của hệ thống dữ liệu.

## 1. Vì sao kết nối cơ sở dữ liệu là vấn đề trong serverless?

Kết nối cơ sở dữ liệu quan hệ thường là một phiên làm việc có trạng thái. Để tạo kết nối, ứng dụng có thể phải thực hiện DNS lookup, mở TCP socket, thương lượng TLS, xác thực, thiết lập session và khởi tạo driver. Các bước này tiêu tốn thời gian và tài nguyên.

Trong ứng dụng serverless, một đợt tăng lưu lượng có thể làm nền tảng tạo nhiều execution environment cùng lúc. Nếu mỗi invocation tạo một kết nối riêng, số kết nối tăng theo số invocation đồng thời. Ngay cả khi function chạy nhanh, các kết nối có thể tồn tại lâu hơn thời gian xử lý do pool, timeout hoặc môi trường thực thi được giữ ấm.

Ví dụ, một API nhận 600 request đồng thời. Nếu mỗi execution environment mở 3 kết nối và nền tảng tạo 600 environment, hệ thống có thể cần tới 1.800 kết nối client tiềm năng. Cơ sở dữ liệu có thể chỉ cho phép một phần nhỏ con số đó. Hậu quả thường thấy:

- Database từ chối kết nối mới vì đã đạt max_connections.
- Thời gian mở kết nối tăng do xác thực và TLS handshake.
- Connection storm làm CPU và bộ nhớ database tăng đột biến.
- Function chờ lấy connection lâu, dẫn đến timeout dây chuyền.
- Retry làm lưu lượng tăng thêm đúng lúc database đang quá tải.
- Kết nối nhàn rỗi chiếm tài nguyên dù không có truy vấn.

Vấn đề không chỉ là tổng số truy vấn. Số session đồng thời, thời gian giữ session và cách phân bổ kết nối giữa các function cũng quan trọng.

## 2. Phân biệt connection, connection pool và database proxy

Ba thành phần thường được nhắc cùng nhau nhưng có vai trò khác nhau:

| Thành phần | Quản lý điều gì? | Phạm vi hoạt động | Mục tiêu |
|---|---|---|---|
| Database connection | Một phiên giao tiếp giữa client và database | Một kết nối cụ thể | Gửi query, transaction và nhận kết quả |
| Connection pool | Tập hợp kết nối được tái sử dụng | Trong một process hoặc execution environment | Tránh mở kết nối mới cho mọi thao tác |
| Database proxy | Kết nối client từ ứng dụng và kết nối backend đến database | Giữa nhiều client và database | Tập trung, giới hạn và phân phối kết nối backend |

Một pool trong Java thường được tạo bởi thư viện như HikariCP. Mỗi execution environment có thể có pool riêng. Nếu nền tảng tạo thêm environment, tổng số pool cũng tăng theo.

Proxy nằm giữa ứng dụng và database. Nhiều client có thể kết nối đến proxy, còn proxy quản lý một nhóm kết nối backend đến database. Tùy engine và trạng thái session, proxy có thể tái sử dụng một kết nối backend cho các client khác nhau ở những thời điểm phù hợp.

~~~mermaid
flowchart TB
    subgraph FaaS["Các Java function execution environments"]
      F1["Function A<br/>Pool A"]
      F2["Function B<br/>Pool B"]
      F3["Function C<br/>Pool C"]
    end
    F1 --> P["Database Proxy"]
    F2 --> P
    F3 --> P
    P --> BP["Backend connection pool"]
    BP --> DB[("Relational database")]
~~~

Pool ở phía ứng dụng giảm số lần mở kết nối từ function đến proxy hoặc database. Proxy giúp điều phối kết nối backend và giảm áp lực lên database. Hai lớp có thể bổ trợ nhau, nhưng cần cấu hình tổng thể; tạo pool lớn ở mọi function rồi thêm proxy không tự động làm hệ thống an toàn.

## 3. Connection pooling trong Java

### 3.1. Pool hoạt động như thế nào?

Khi ứng dụng cần truy vấn database, thay vì mở một kết nối mới, nó yêu cầu pool cấp một connection đang rảnh. Sau khi hoàn tất, ứng dụng đóng đối tượng Connection để trả kết nối về pool. Lệnh close trong trường hợp này thường trả connection về pool, không đóng socket vật lý ngay lập tức.

Luồng cơ bản:

1. Ứng dụng khởi tạo pool với giới hạn kết nối.
2. Code nghiệp vụ gọi getConnection.
3. Pool trả về kết nối rảnh hoặc chờ đến khi có kết nối.
4. Ứng dụng thực hiện query hoặc transaction.
5. Ứng dụng đóng Connection để trả về pool.
6. Pool giữ kết nối để tái sử dụng hoặc loại bỏ theo timeout và chính sách vòng đời.

Pool thường quản lý:

- Số kết nối tối đa.
- Số kết nối nhàn rỗi tối thiểu hoặc mục tiêu.
- Thời gian chờ khi pool hết connection.
- Thời gian sống tối đa của connection.
- Kiểm tra kết nối còn hợp lệ.
- Loại bỏ connection bị lỗi hoặc quá hạn.

### 3.2. Lợi ích

Pooling giảm chi phí tạo kết nối lặp đi lặp lại. Với Java, điều này đặc biệt hữu ích khi driver JDBC và TLS handshake có chi phí đáng kể.

Pool cũng giới hạn số kết nối mà một process có thể mở. Nếu pool size là 2, một execution environment chỉ có tối đa 2 connection do pool đó quản lý. Các request đồng thời trong cùng environment sẽ chia sẻ hai connection hoặc chờ lấy kết nối.

Pool không làm giảm tổng kết nối toàn hệ thống một cách tự động. Nếu có 300 environment và mỗi environment có pool size 10, tổng giới hạn vẫn có thể lên đến 3.000 kết nối. Cần tính tổng trên toàn bộ fleet.

### 3.3. Giới hạn của pool trong FaaS

Pool thường là tài nguyên trong bộ nhớ process. Nó không được chia sẻ giữa các execution environment khác nhau. Khi nền tảng scale từ 10 lên 100 environment, hệ thống có thể có 100 pool độc lập.

Một pool được tạo khi environment khởi động có thể được tái sử dụng qua nhiều invocation nếu environment còn sống. Tuy nhiên, không có bảo đảm environment sẽ tồn tại bao lâu. Nền tảng có thể đóng instance bất cứ lúc nào.

Vì vậy:

- Không dùng pool để lưu trạng thái nghiệp vụ.
- Không giả định pool tồn tại sau lần invocation hiện tại.
- Không tạo pool mới trong mỗi lần gọi handler.
- Không mở pool quá lớn với hy vọng giảm thời gian chờ.
- Phải xử lý connection đã bị database hoặc mạng đóng khi environment ngủ lâu.

## 4. Tái sử dụng pool trong Java function

### 4.1. Tạo pool một lần cho mỗi execution environment

Với FaaS, một cách thường dùng là giữ DataSource trong phạm vi static hoặc singleton để các invocation trong cùng execution environment tái sử dụng pool.

Ví dụ HikariCP:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DatabaseResources {
    private static final HikariDataSource DATA_SOURCE = createDataSource();

    private DatabaseResources() {
    }

    private static HikariDataSource createDataSource() {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(System.getenv("DB_JDBC_URL"));
        config.setUsername(System.getenv("DB_USERNAME"));
        config.setPassword(System.getenv("DB_PASSWORD"));

        config.setMaximumPoolSize(2);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(3000);
        config.setValidationTimeout(1000);
        config.setIdleTimeout(60000);
        config.setMaxLifetime(300000);

        return new HikariDataSource(config);
    }

    public static HikariDataSource dataSource() {
        return DATA_SOURCE;
    }
}
~~~

Function lấy connection khi xử lý request:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public final class CustomerRepository {
    public String findName(String customerId) throws Exception {
        String sql = "SELECT name FROM customers WHERE customer_id = ?";

        try (Connection connection =
                     DatabaseResources.dataSource().getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setString(1, customerId);

            try (ResultSet resultSet = statement.executeQuery()) {
                return resultSet.next() ? resultSet.getString("name") : null;
            }
        }
    }
}
~~~

Trong ví dụ này, try-with-resources đóng ResultSet, PreparedStatement và Connection. Connection được trả về pool sau khi sử dụng. DataSource vẫn được giữ để các invocation sau trong cùng environment dùng lại.

Các giá trị cấu hình chỉ là minh họa. URL, username và password cần được lấy từ cấu hình bảo mật của nền tảng, chẳng hạn secret manager hoặc cơ chế cấp danh tính. Không ghi credential vào mã nguồn hoặc log.

### 4.2. Lazy initialization và cold start

Khởi tạo pool trong static initializer có thể làm tăng cold start. HikariCP thường tạo kết nối theo nhu cầu, nhưng việc tạo object, đọc cấu hình và khởi tạo driver vẫn có chi phí. Nếu cấu hình minimumIdle lớn hơn 0, pool có thể tạo kết nối nhàn rỗi ngay khi khởi động.

Với function ít được gọi, minimumIdle bằng 0 có thể giảm kết nối không cần thiết. Với function có tải ổn định, cần đo xem giữ một số connection nhàn rỗi có giúp giảm độ trễ hay không.

Có thể dùng lazy holder để chỉ khởi tạo DataSource khi lần đầu cần truy cập:

~~~java
public final class LazyDatabaseResources {
    private LazyDatabaseResources() {
    }

    private static class Holder {
        private static final HikariDataSource DATA_SOURCE =
                DatabaseResourcesFactory.create();
    }

    public static HikariDataSource dataSource() {
        return Holder.DATA_SOURCE;
    }
}
~~~

Đây là mẫu khởi tạo an toàn theo cơ chế class initialization của Java. Dù vậy, lần gọi đầu tiên vẫn phải trả chi phí tạo DataSource và có thể tạo kết nối vật lý đầu tiên. Hãy đo cold start và latency thực tế thay vì chỉ chuyển thời điểm khởi tạo.

### 4.3. Không đóng DataSource sau mỗi invocation

Nếu đóng DataSource sau mỗi lần xử lý request, các invocation tiếp theo trong cùng environment sẽ phải tạo lại pool. Điều đó làm mất lợi ích tái sử dụng và tăng số lần handshake.

Thông thường, handler chỉ đóng Connection, Statement và ResultSet. DataSource tồn tại trong vòng đời environment. Không nên phụ thuộc vào một shutdown hook để bảo đảm pool luôn được đóng sạch khi FaaS kết thúc, vì nền tảng có thể dừng environment mà không cho ứng dụng thời gian cleanup đáng tin cậy.

## 5. Tính kích thước pool và giới hạn kết nối tổng thể

### 5.1. Công thức ước lượng

Để ước lượng kết nối tối đa, có thể dùng công thức:

\[
C_{total} \approx E \times P + B
\]

Trong đó:

- E là số execution environment có thể xử lý đồng thời.
- P là maximum pool size của mỗi environment.
- B là số kết nối dành cho ứng dụng khác, migration, quản trị, monitoring và các tác vụ nền.

Ví dụ, nếu giới hạn concurrency của function là 120 environment và mỗi environment có pool size 2, số kết nối client tối đa từ function có thể đạt khoảng 240. Nếu database dành 300 connection cho ứng dụng, vẫn cần dành phần còn lại cho các workload khác và headroom.

Đây là ước lượng bảo thủ. Số kết nối thực tế còn phụ thuộc số invocation đồng thời trong mỗi environment, cách pool khởi tạo connection và mức độ hoạt động. Tuy nhiên, không nên dựa vào việc pool có thể không mở hết để bỏ qua giới hạn kết nối.

### 5.2. Chọn pool size

Trong FaaS, pool nhỏ thường là điểm bắt đầu hợp lý. Nhiều function chỉ xử lý một request hoặc một batch tại một thời điểm trong một environment, vì vậy pool lớn có thể không đem lại lợi ích.

Cần chọn pool size dựa trên:

- Số thao tác database đồng thời trong một invocation.
- Khả năng chạy đồng thời trong cùng execution environment.
- Số environment tối đa theo concurrency.
- Giới hạn connection của database hoặc proxy.
- Throughput query và giới hạn CPU, I/O của database.
- Số ứng dụng khác cùng sử dụng database.

Nếu mỗi invocation chỉ thực hiện một transaction tuần tự, pool size 1 hoặc 2 có thể đủ. Nếu một function xử lý nhiều tác vụ song song trong cùng invocation, cần tính số connection có thể được sử dụng đồng thời và giới hạn concurrency của worker pool.

### 5.3. Giới hạn concurrency của function

Pool size và function concurrency phải được thiết kế cùng nhau. Giảm concurrency tối đa có thể bảo vệ database khỏi quá tải, nhưng làm tăng thời gian message chờ hoặc request bị throttling. Tăng concurrency có thể cải thiện throughput của function nhưng không giúp nếu database đã đạt giới hạn.

Nên xác định ngân sách kết nối dành cho từng function hoặc nhóm workload. Ví dụ:

| Workload | Concurrency tối đa | Pool mỗi environment | Kết nối tối đa ước lượng |
|---|---:|---:|---:|
| API đọc khách hàng | 80 | 1 | 80 |
| Consumer xử lý đơn | 40 | 2 | 80 |
| Function đối soát | 5 | 2 | 10 |
| Migration/monitoring và ứng dụng khác | — | — | 30 |
| Tổng dự kiến | | | 200 |

Các con số trên là ví dụ để minh họa ngân sách. Cần xác nhận giới hạn thật từ cấu hình nền tảng và database.

## 6. Timeout và vòng đời connection

Một cấu hình pool tốt phải phối hợp nhiều loại timeout:

| Timeout | Ý nghĩa | Khi quá ngắn | Khi quá dài |
|---|---|---|---|
| Connection timeout | Thời gian chờ lấy connection từ pool | Request lỗi sớm khi pool bận | Request chờ lâu và dễ vượt timeout function |
| Validation timeout | Thời gian kiểm tra connection | Connection tốt có thể bị đánh dấu lỗi khi hệ thống chậm | Phát hiện connection hỏng chậm |
| Idle timeout | Thời gian giữ connection nhàn rỗi trước khi loại bỏ | Tạo/đóng kết nối thường xuyên | Giữ nhiều connection không cần thiết |
| Max lifetime | Tuổi tối đa của connection trong pool | Tăng chi phí tạo lại connection | Connection cũ có thể bị proxy hoặc database đóng trước |
| Function timeout | Thời gian tối đa invocation | Request bị cắt trước khi nghiệp vụ hoàn tất | Giữ tài nguyên và connection quá lâu |

Connection timeout nên nhỏ hơn phần thời gian còn lại của invocation. Nếu function timeout sau 10 giây, không nên để pool chờ 10 giây chỉ để lấy connection rồi không còn thời gian chạy query.

Max lifetime thường nên nhỏ hơn thời gian sống tối đa do proxy hoặc database quy định, có một khoảng đệm. Không có một con số đúng cho mọi nền tảng; hãy dựa vào timeout thực tế và tài liệu dịch vụ.

Sau một thời gian environment không được sử dụng, firewall, NAT, proxy hoặc database có thể đóng connection nhàn rỗi. Pool cần kiểm tra và loại bỏ connection không hợp lệ. Cấu hình keepalive có thể giúp một số trường hợp, nhưng tạo thêm lưu lượng và không thay thế xử lý lỗi kết nối.

## 7. Database proxy là gì?

Database proxy là lớp trung gian nhận kết nối từ ứng dụng và quản lý kết nối đến database. Function kết nối tới endpoint của proxy thay vì trực tiếp tới database.

Proxy có thể cung cấp:

- Tập trung các kết nối backend và tái sử dụng chúng.
- Giới hạn số kết nối mở đến database.
- Phân phối kết nối giữa nhiều client.
- Theo dõi trạng thái kết nối và xử lý một số trường hợp failover.
- Quản lý hoặc tích hợp xác thực theo khả năng của nền tảng.
- Giảm tác động của connection storm lên database.

Proxy không phải là cache query và cũng không tự tối ưu câu SQL. Nếu database chậm vì query nặng, thiếu index hoặc lock contention, proxy không giải quyết nguyên nhân đó.

### 7.1. Frontend và backend connections

Có thể phân biệt hai nhóm kết nối:

- **Client/frontend connection:** từ Java function đến proxy.
- **Backend/database connection:** từ proxy đến database.

Nhiều frontend connection có thể được proxy phục vụ bằng một nhóm backend connection nhỏ hơn, nếu trạng thái session cho phép. Proxy giúp kiểm soát số backend connection và tránh để mọi execution environment mở một session vật lý riêng trực tiếp vào database.

Tuy nhiên, số frontend connection vẫn có thể lớn. Proxy cũng có giới hạn client, bộ nhớ, throughput và số backend connection. Cần theo dõi cả hai phía.

### 7.2. Multiplexing

Multiplexing là khả năng dùng lại một backend connection cho nhiều client ở các thời điểm phù hợp. Một backend connection có thể được trả về pool sau khi transaction kết thúc, rồi phục vụ transaction khác.

Khả năng multiplexing phụ thuộc engine, proxy và trạng thái session. Khi client giữ transaction lâu, thay đổi session state hoặc sử dụng tính năng yêu cầu session affinity, proxy có thể phải gắn backend connection với client trong thời gian dài.

Khi đó connection bị pin hoặc giữ cố định, làm giảm hiệu quả pooling. Vì vậy, proxy không bảo đảm mọi client connection đều được chia sẻ tối ưu.

### 7.3. Session pinning

Một số thao tác có thể khiến proxy không thể chuyển backend connection sang client khác an toàn, ví dụ:

- Transaction mở lâu hoặc không kết thúc.
- Thay đổi session variables hoặc session configuration.
- Dùng temporary table.
- Giữ cursor hoặc trạng thái session đặc thù.
- Một số loại prepared statement hoặc lệnh phụ thuộc trạng thái kết nối, tùy proxy và database engine.

Danh sách cụ thể thay đổi theo dịch vụ. Cần kiểm tra tài liệu của proxy đang dùng và theo dõi metric pinning. Để tăng khả năng multiplexing, nên giữ transaction ngắn, đóng statement và result set đúng lúc, tránh dùng session state toàn cục nếu không cần.

## 8. Khi nào nên dùng database proxy?

Proxy đặc biệt hữu ích khi:

- Có nhiều function environment kết nối đến một database quan hệ.
- Lưu lượng có đợt tăng đột biến và tạo connection storm.
- Database có giới hạn connection thấp hơn tổng số client tiềm năng.
- Cần quản lý kết nối backend tập trung.
- Muốn giảm tác động của failover hoặc thay đổi endpoint theo khả năng của dịch vụ.
- Có nhiều ứng dụng hoặc function chia sẻ một database.

Proxy có thể không cần thiết khi:

- Workload nhỏ và ổn định, số kết nối trực tiếp đã được giới hạn tốt.
- Dịch vụ dữ liệu sử dụng HTTP API hoặc SDK thay vì session JDBC dài hạn.
- Proxy không hỗ trợ engine hoặc tính năng database mà ứng dụng cần.
- Chi phí và độ trễ thêm vào lớn hơn lợi ích.
- Ứng dụng phụ thuộc nhiều vào session pinning khiến multiplexing ít hiệu quả.

Một proxy cũng là một thành phần hạ tầng cần cấu hình, giám sát, bảo mật và tính chi phí. Không nên thêm proxy chỉ vì kiến trúc serverless; cần đo số kết nối và đặc tính tải để quyết định.

## 9. Kết hợp connection pool và database proxy

Một kiến trúc phổ biến là Java function sử dụng pool nhỏ kết nối đến proxy. Proxy quản lý backend pool đến database.

~~~mermaid
flowchart LR
    A["Java Function A<br/>Pool nhỏ"] --> P["Database Proxy"]
    B["Java Function B<br/>Pool nhỏ"] --> P
    C["Java Function C<br/>Pool nhỏ"] --> P
    P --> D["Backend connection pool"]
    D --> DB[("Database")]
~~~

Mỗi lớp có giới hạn riêng:

- Pool ứng dụng giới hạn connection trong một environment.
- Concurrency limit giới hạn số environment hoạt động.
- Proxy giới hạn và điều phối backend connections.
- Database giới hạn số session, CPU, memory và throughput.

Ví dụ, 200 environment có thể mở tổng cộng 400 frontend connection đến proxy nếu mỗi pool có size 2. Proxy có thể chỉ duy trì 50 backend connection nếu transaction ngắn và multiplexing hiệu quả. Nếu nhiều session bị pin, số backend connection cần thiết có thể tăng lên gần số frontend connection đang hoạt động.

Vì vậy, không chỉ theo dõi số connection database. Cần theo dõi:

- Client connections đến proxy.
- Backend connections đang sử dụng và đang rảnh.
- Tỷ lệ connection được multiplex.
- Số session bị pin và thời gian pin.
- Thời gian chờ lấy backend connection.
- Connection errors, timeout và failover.
- Transaction duration và số transaction đang mở.

## 10. Dịch vụ dữ liệu serverless và các mô hình truy cập

Không phải mọi dịch vụ dữ liệu serverless đều cần JDBC connection pool. Cần chọn mô hình truy cập phù hợp với loại dữ liệu và workload.

### 10.1. Cơ sở dữ liệu quan hệ có khả năng serverless

Một số dịch vụ quan hệ quản lý compute và dung lượng theo nhu cầu, ví dụ các dịch vụ database serverless hoặc cluster có khả năng tự điều chỉnh capacity. Chúng vẫn có thể dùng giao thức kết nối quan hệ như PostgreSQL hoặc MySQL.

Đặc điểm:

- Hỗ trợ SQL, transaction và quan hệ dữ liệu.
- Phù hợp khi nghiệp vụ cần join, constraint hoặc giao dịch nhiều bản ghi.
- Vẫn có giới hạn kết nối, CPU, memory và throughput.
- Có thể cần pool hoặc proxy khi số client tăng cao.
- Capacity có thể thay đổi, nhưng không có nghĩa kết nối và truy vấn là vô hạn.

Serverless ở tầng compute không tự loại bỏ vấn đề connection management.

### 10.2. Data API hoặc HTTP database endpoint

Một số dịch vụ quan hệ cung cấp Data API qua HTTPS. Thay vì mở session JDBC dài hạn, function gửi request HTTP chứa câu lệnh hoặc thao tác dữ liệu.

Ưu điểm:

- Không cần quản lý JDBC connection đến database.
- Phù hợp với function ngắn hạn và môi trường có nhiều lần khởi tạo.
- Có thể dùng cơ chế xác thực và connection management do dịch vụ quản lý.
- HTTP client có thể tái sử dụng kết nối keep-alive để giảm handshake.

Giới hạn:

- API có quota, giới hạn payload, timeout và giới hạn số request.
- Cách hỗ trợ transaction và batch có thể khác JDBC.
- Mỗi request có overhead serialization và HTTP.
- Không phải mọi tính năng SQL hoặc driver đều có sẵn.
- Cần kiểm tra khả năng hỗ trợ của engine và vùng triển khai.

Data API giảm nhu cầu quản lý kết nối database trong ứng dụng, nhưng không loại bỏ giới hạn capacity của database hay giới hạn API.

### 10.3. NoSQL managed hoặc serverless

Dịch vụ NoSQL managed thường được truy cập qua SDK hoặc HTTP API, thay vì một kết nối JDBC cho mỗi function. Ví dụ là key-value store hoặc document database có khả năng mở rộng theo request, throughput hoặc cấu hình capacity.

Phù hợp khi:

- Truy vấn chủ yếu dựa trên key hoặc access pattern đã xác định.
- Dữ liệu có cấu trúc linh hoạt.
- Cần scale độc lập theo partition hoặc throughput.
- Không cần các join quan hệ phức tạp.
- Mô hình nhất quán và transaction phù hợp với nghiệp vụ.

SDK client thường nên được tái sử dụng trong execution environment để tận dụng HTTP connection pooling, credential provider và cấu hình retry. Không tạo một SDK client mới cho mọi thao tác nếu không có lý do.

### 10.4. Object storage và cache

Object storage phù hợp với file, ảnh, tài liệu, log archive và dữ liệu lớn không cần truy vấn quan hệ trực tiếp. Function có thể đọc/ghi qua SDK hoặc HTTP API.

Cache phù hợp với dữ liệu đọc nhiều, có thể chấp nhận TTL hoặc chính sách invalidation rõ ràng. Cache không thay thế nguồn dữ liệu chính và không nên trở thành nơi duy nhất lưu trạng thái nghiệp vụ quan trọng nếu dịch vụ không cung cấp bảo đảm phù hợp.

### 10.5. So sánh lựa chọn

| Loại dịch vụ | Cách truy cập phổ biến | Cần JDBC pool? | Phù hợp khi |
|---|---|---|---|
| Database quan hệ managed/serverless | JDBC hoặc driver tương ứng | Thường có ích nếu nhiều thao tác dùng session | SQL, transaction, join, constraint |
| Database quan hệ có Data API | HTTPS request | Không cần JDBC pool; nên tái sử dụng HTTP client | Function ngắn hạn, ít session dài |
| NoSQL managed/serverless | SDK hoặc HTTP API | Không dùng JDBC pool; SDK có thể quản lý HTTP pool | Key-value, document, access pattern rõ |
| Object storage | SDK hoặc HTTP | Không | File, object và dữ liệu phi cấu trúc |
| Cache managed | Client protocol hoặc API | Tùy giao thức; có thể cần connection pool riêng | Dữ liệu đọc nhiều, có TTL |

Không chọn database chỉ vì nhãn serverless. Hãy bắt đầu từ access pattern, tính nhất quán, transaction, kích thước dữ liệu, khả năng truy vấn, throughput và chi phí.

## 11. Java SDK client và HTTP connection reuse

Với dịch vụ truy cập qua SDK hoặc HTTP, không cần JDBC pool nhưng vẫn có thể cần tái sử dụng client. HTTP client thường quản lý connection pool, keep-alive, TLS session và retry.

Ví dụ với Java HttpClient:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

public final class HttpClients {
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .version(HttpClient.Version.HTTP_2)
            .build();

    private HttpClients() {
    }

    public static HttpClient shared() {
        return CLIENT;
    }
}
~~~

Function có thể dùng client này qua nhiều invocation trong cùng environment. Việc tái sử dụng client giúp giảm chi phí tạo socket và TLS handshake. Tuy nhiên, cần cấu hình timeout cho từng request, giới hạn concurrency phù hợp và tuân thủ quota của API.

Với SDK cloud, nên dùng một client được khởi tạo một lần trong environment, tái sử dụng credential provider và HTTP transport theo khuyến nghị của SDK. Không tự tạo một client cho mỗi record trong batch nếu client có thể được dùng an toàn giữa các lần gọi.

## 12. Transaction, trạng thái session và cách sử dụng an toàn

Connection pool và proxy có thể làm việc với transaction, nhưng transaction vẫn là trạng thái gắn với một connection hoặc session trong khoảng thời gian thực thi.

Trong JDBC:

- Bắt đầu transaction bằng cách tắt auto-commit.
- Thực hiện các thao tác cần nguyên tử.
- Commit khi tất cả thao tác thành công.
- Rollback khi có lỗi.
- Đóng Connection để trả về pool.

Ví dụ:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(
            String fromAccount,
            String toAccount,
            long amount) throws Exception {

        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                debit(connection, fromAccount, amount);
                credit(connection, toAccount, amount);
                connection.commit();
            } catch (Exception failure) {
                connection.rollback();
                throw failure;
            }
        }
    }

    private void debit(
            Connection connection,
            String accountId,
            long amount) throws Exception {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE accounts SET balance = balance - ? WHERE account_id = ?")) {
            statement.setLong(1, amount);
            statement.setString(2, accountId);

            if (statement.executeUpdate() != 1) {
                throw new IllegalStateException("Debit failed");
            }
        }
    }

    private void credit(
            Connection connection,
            String accountId,
            long amount) throws Exception {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE accounts SET balance = balance + ? WHERE account_id = ?")) {
            statement.setLong(1, amount);
            statement.setString(2, accountId);

            if (statement.executeUpdate() != 1) {
                throw new IllegalStateException("Credit failed");
            }
        }
    }
}
~~~

Đây là ví dụ minh họa. Trong hệ thống thật, cần kiểm tra số dư không âm, khóa hoặc cập nhật có điều kiện để tránh race condition, xử lý deadlock và đảm bảo ràng buộc tài khoản. Không giữ transaction mở trong lúc gọi HTTP đến dịch vụ bên ngoài vì điều đó giữ connection lâu và làm giảm khả năng multiplexing của proxy.

Với serverless, một invocation có thể bị timeout hoặc dừng giữa transaction. Database thường rollback transaction chưa commit khi connection bị đóng, nhưng không nên dựa vào điều đó để quản lý quy trình nhiều bước. Các nghiệp vụ kéo dài qua nhiều invocation cần trạng thái bền vững và mô hình orchestration hoặc Saga.

## 13. Retry, idempotency và lỗi kết nối

Lỗi kết nối có thể xảy ra khi function bắt đầu cold, proxy failover, database scale capacity, mạng chập chờn hoặc connection trong pool đã hết hạn.

Cần phân loại:

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời trước khi gửi query | Connection timeout, socket reset | Retry có backoff và jitter nếu còn thời gian |
| Connection đã chết | Database đóng session khi environment ngủ lâu | Loại connection khỏi pool và lấy connection mới |
| Query timeout | Query chạy quá lâu hoặc lock | Điều tra query, giới hạn timeout, cân nhắc retry có kiểm soát |
| Transaction outcome không rõ | Mất kết nối khi commit | Tra cứu trạng thái nghiệp vụ trước khi gửi lại |
| Lỗi dữ liệu hoặc constraint | Vi phạm unique key, schema sai | Không retry vô hạn; xử lý theo quy tắc nghiệp vụ |

Đặc biệt, nếu kết nối mất đúng lúc commit, client có thể không biết transaction đã commit hay chưa. Retry toàn bộ thao tác có thể tạo hiệu ứng trùng. Với thao tác ghi quan trọng, cần idempotency key, unique constraint hoặc transaction record để xác định kết quả trước khi thử lại.

Không retry tất cả lỗi SQL một cách mù quáng. Retry nên có giới hạn, thời gian chờ tăng dần và jitter. Nếu function chỉ còn ít thời gian trước timeout, retry thêm có thể làm invocation thất bại và message bị giao lại.

## 14. Bảo mật kết nối và quản lý credential

Kết nối database thường mang quyền truy cập trực tiếp vào dữ liệu quan trọng. Mỗi function nên có quyền tối thiểu phù hợp với trách nhiệm.

Các nguyên tắc cần áp dụng:

- Dùng TLS khi kết nối database hoặc proxy.
- Lấy credential từ secret manager hoặc cơ chế cấp danh tính của nền tảng.
- Xoay vòng password hoặc token theo chính sách.
- Tách user database cho workload đọc và ghi nếu cần.
- Chỉ cấp quyền trên schema, bảng và thao tác mà function cần.
- Không ghi password, token, JDBC URL chứa secret hoặc dữ liệu nhạy cảm vào log.
- Kiểm soát quyền truy cập network giữa function, proxy và database.
- Dùng IAM authentication hoặc token ngắn hạn nếu dịch vụ hỗ trợ và phù hợp với driver.

Nếu proxy hỗ trợ tích hợp secret manager hoặc IAM authentication, cần cấu hình cả quyền client-to-proxy và proxy-to-database. Xác thực thành công ở một chặng không đồng nghĩa chặng còn lại đã được cấp quyền đúng.

Không dùng chung một tài khoản database quyền quản trị cho mọi function. Nếu một function bị khai thác hoặc credential bị lộ, quyền tối thiểu giúp giảm phạm vi ảnh hưởng.

## 15. Quan sát và đo lường

Không thể tối ưu pool hoặc proxy chỉ bằng cách nhìn số connection hiện tại. Cần đo theo thời gian và tương quan với concurrency, latency và lỗi.

Các metric nên theo dõi:

- Active connections và idle connections trong pool.
- Pending threads hoặc số request đang chờ connection.
- Connection acquisition time.
- Connection timeout và validation failure.
- Số client connections đến proxy.
- Số backend connections đang hoạt động và nhàn rỗi.
- Session pinning hoặc tỷ lệ multiplexing nếu dịch vụ cung cấp.
- Database max connection utilization.
- Query latency, transaction duration và lock wait.
- Function concurrency, cold start và invocation duration.
- Tỷ lệ retry, timeout và lỗi database.

Log nên có correlation ID hoặc request ID để liên kết một invocation với query và lỗi tương ứng. Không log toàn bộ câu SQL có dữ liệu nhạy cảm hoặc giá trị bind parameter nếu không được phép.

Cần cảnh báo trước khi database chạm giới hạn kết nối, không đợi đến khi function bắt đầu timeout. Một chỉ số hữu ích là tỷ lệ connection utilization kết hợp với số request đang chờ pool và tuổi của request.

## 16. Các lỗi thiết kế thường gặp

**Tạo pool trong mỗi invocation:** Mỗi request lại tạo DataSource mới, khiến số connection tăng nhanh và mất lợi ích tái sử dụng. Tạo pool một lần cho mỗi environment và dùng lại.

**Pool size quá lớn:** Một pool lớn trên từng environment có thể nhân lên thành hàng nghìn connection. Tính ngân sách toàn fleet trước khi đặt max pool size.

**Chỉ dùng pool mà không giới hạn concurrency:** Pool giới hạn trong từng process nhưng không giới hạn tổng số process. Đặt concurrency cap và xem xét proxy.

**Cho rằng proxy loại bỏ mọi giới hạn:** Proxy vẫn có giới hạn client, backend, throughput và session pinning. Theo dõi cả frontend lẫn backend connection.

**Giữ transaction quá lâu:** Gọi API ngoài trong transaction hoặc chờ xử lý lâu làm giữ connection và giảm khả năng multiplexing. Giữ transaction ngắn và chỉ bao gồm thao tác dữ liệu cần nguyên tử.

**Không xử lý connection stale:** Environment có thể ngủ lâu khiến mạng hoặc database đóng connection. Cấu hình validation, lifetime và xử lý lỗi để pool thay thế connection.

**Đóng DataSource sau mỗi request:** Việc này phá hủy pool và làm invocation tiếp theo phải khởi tạo lại. Chỉ đóng Connection/Statement/ResultSet ở phạm vi thao tác.

**Đặt timeout không đồng bộ:** Pool chờ lâu hơn timeout function hoặc proxy đóng connection trước pool. Phối hợp connection timeout, query timeout, max lifetime và function timeout.

**Dùng JDBC cho mọi loại dữ liệu:** NoSQL, object storage hoặc Data API có thể phù hợp hơn cho một số access pattern. Chọn theo truy vấn, transaction và tính nhất quán.

**Không chống retry khi commit không rõ kết quả:** Gửi lại thao tác ghi có thể tạo dữ liệu trùng. Dùng idempotency key và kiểm tra trạng thái trước khi retry.

## 17. Quy trình thiết kế kết nối cho một Java function

Có thể dùng quy trình sau khi đưa function kết nối dữ liệu vào production:

1. **Xác định access pattern:** Function đọc hay ghi, số query mỗi invocation, transaction có dài không và có cần SQL quan hệ không?
2. **Chọn loại dịch vụ dữ liệu:** Relational, Data API, NoSQL, object storage hay cache dựa trên yêu cầu nghiệp vụ.
3. **Ước lượng concurrency:** Xác định số environment tối đa và số thao tác database song song trong mỗi environment.
4. **Tính ngân sách connection:** Chọn pool size nhỏ, cộng kết nối của các workload khác và dành headroom.
5. **Quyết định dùng proxy:** So sánh connection storm, session pinning, giới hạn backend và chi phí proxy.
6. **Cấu hình pool và timeout:** Đặt connection timeout, idle timeout, max lifetime, validation và query timeout phù hợp.
7. **Quản lý vòng đời:** Tái sử dụng DataSource hoặc SDK client trong environment; đóng tài nguyên theo từng thao tác.
8. **Thiết kế lỗi:** Phân biệt lỗi tạm thời, lỗi dữ liệu và kết quả commit chưa rõ; dùng retry có giới hạn.
9. **Bảo mật:** Dùng TLS, credential ngắn hạn hoặc secret manager, quyền tối thiểu và network policy.
10. **Đo và điều chỉnh:** Theo dõi connection, latency, concurrency, retry và chi phí trên tải đại diện.

## 18. Checklist trước khi triển khai

- [ ] Đã xác định loại dữ liệu và access pattern của function.
- [ ] Đã chọn relational database, Data API, NoSQL, object storage hoặc cache phù hợp.
- [ ] Nếu dùng JDBC, DataSource được tái sử dụng trong cùng execution environment.
- [ ] Pool không được tạo mới trong mỗi invocation.
- [ ] Pool size và concurrency được tính trên toàn bộ fleet.
- [ ] Có ngân sách connection cho migration, monitoring và ứng dụng khác.
- [ ] Đã đánh giá nhu cầu database proxy và khả năng session pinning.
- [ ] Connection timeout nhỏ hơn thời gian còn lại của function.
- [ ] Max lifetime tương thích với timeout của proxy/database.
- [ ] Connection, Statement và ResultSet được đóng đúng cách.
- [ ] Transaction ngắn và không giữ connection khi chờ dịch vụ bên ngoài.
- [ ] Có idempotency cho thao tác ghi có thể được retry.
- [ ] Credential được quản lý an toàn, TLS được bật và quyền database ở mức tối thiểu.
- [ ] Có metric về pool wait, active/idle connection, proxy và database utilization.
- [ ] Đã kiểm tra cold start, burst concurrency, failover và connection timeout.
- [ ] Chi phí pool, proxy, database capacity và API request đã được ước lượng.

## Kết luận

Connection pooling giúp Java tái sử dụng kết nối trong một execution environment, nhưng mỗi environment có pool riêng nên tổng số connection vẫn tăng theo concurrency. Database proxy điều phối kết nối backend và có thể giảm áp lực lên database, nhưng hiệu quả phụ thuộc transaction, session state và khả năng multiplexing. Các dịch vụ dữ liệu serverless hoặc Data API có thể giảm công việc quản lý session, song vẫn có quota, giới hạn throughput và chi phí riêng.

Thiết kế tốt bắt đầu từ access pattern và ngân sách tài nguyên. Hãy giữ pool nhỏ, giới hạn concurrency, phối hợp timeout, quản lý credential an toàn, giữ transaction ngắn và làm cho thao tác ghi chịu được retry. Sau đó đo connection, latency và lỗi trong điều kiện tải thực tế để quyết định có cần proxy hoặc thay đổi loại dịch vụ dữ liệu hay không.

