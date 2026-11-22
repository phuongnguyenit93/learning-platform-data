# Nguyên tắc cấu hình timeout, mã hóa đường truyền và quản lý mật khẩu

Khi một ứng dụng Java hoặc công cụ SQL kết nối đến **Oracle Database**, việc nhập đúng host, port, service name, username và password mới chỉ là bước đầu. Một kết nối phù hợp cho môi trường thực tế còn phải trả lời ba câu hỏi: **nếu kết nối hoặc câu lệnh bị treo thì chờ bao lâu, dữ liệu trên đường truyền được bảo vệ ra sao, và thông tin đăng nhập được lưu giữ như thế nào?**

Ba chủ đề trong bài này gắn với nhau nhưng xử lý các rủi ro khác nhau:

| Thành phần | Mục tiêu | Tình huống cần tránh |
| --- | --- | --- |
| **Timeout** | Giới hạn thời gian chờ ở những giai đoạn cụ thể, giải phóng tài nguyên và trả lỗi có kiểm soát | Một yêu cầu API giữ luồng xử lý hoặc kết nối quá lâu khi mạng hay máy chủ không phản hồi |
| **Mã hóa đường truyền** | Giữ bí mật và bảo vệ tính toàn vẹn của dữ liệu trao đổi giữa client và Oracle; xác thực máy chủ khi dùng TLS | Dữ liệu hoặc thông tin đăng nhập bị nghe lén, thay đổi, hay gửi nhầm đến máy chủ giả |
| **Quản lý mật khẩu** | Chỉ cấp quyền truy cập cho đúng danh tính, hạn chế lộ bí mật và có khả năng thu hồi hoặc thay đổi | Mật khẩu nằm trong Git, script, log, lệnh terminal hoặc được nhiều hệ thống dùng chung quá rộng |

Ví dụ chủ yếu sử dụng **Oracle JDBC Thin Driver** trong ứng dụng Java. Các nguyên tắc tương tự áp dụng khi dùng SQL Developer, SQLcl, SQL*Plus, công cụ quản trị hoặc kết nối giữa các dịch vụ, nhưng mỗi công cụ có tên thiết lập và cách hỗ trợ TLS khác nhau.

## 1. Nhìn kết nối Oracle theo nhiều giai đoạn

Kết nối đến Oracle không phải một hành động duy nhất. Một yêu cầu có thể đi qua nhiều bước:

```text
HTTP request / tác vụ định kỳ
          |
          v
Ứng dụng Java
          |
          | (1) Mượn Connection từ connection pool
          v
Connection pool
          |
          | (2) Tạo kết nối vật lý nếu cần
          |     DNS -> TCP -> bắt tay TLS nếu dùng TCPS
          v
Oracle Listener / Oracle Database
          |
          | (3) Xác thực tài khoản, thiết lập phiên
          v
Phiên Oracle
          |
          | (4) Gửi SQL / gọi PL/SQL
          | (5) Nhận hàng dữ liệu hoặc lỗi
          v
Ứng dụng trả kết quả và hoàn trả Connection về pool
```

Mỗi giai đoạn có thể gặp một loại chậm hoặc lỗi khác nhau. Chẳng hạn:

- Pool đã hết kết nối rảnh, nên ứng dụng chờ một kết nối được trả về dù máy chủ Oracle vẫn hoạt động.
- DNS, firewall hoặc listener không thể tiếp cận, khiến việc **tạo kết nối vật lý** chậm hoặc thất bại.
- TLS không bắt tay được vì sai chứng chỉ, thiếu CA tin cậy hay sai tên máy chủ.
- Tài khoản bị khóa, sai mật khẩu hoặc không đủ quyền, khiến **xác thực hoặc thực thi SQL** bị từ chối.
- Một câu SQL chậm do khóa, kế hoạch thực thi hoặc lượng dữ liệu lớn, dù kết nối đã thiết lập thành công.

Không có một tham số “timeout tổng” nào tự động giải quyết đúng mọi tình huống ở trên. Cần đặt giới hạn tại **đúng lớp** và hiểu giới hạn đó thực sự đo thời gian nào.

## 2. Phân biệt các lớp timeout

### 2.1. Các loại timeout thường dùng với Java và Oracle

| Loại | Thời gian được giới hạn | Cấu hình/ví dụ | Đơn vị thường dùng |
| --- | --- | --- | --- |
| **Pool acquisition timeout** | Chờ lấy một kết nối từ pool | HikariCP: `connectionTimeout` | Mili giây |
| **Network connect timeout** | Chờ thiết lập kết nối mạng đến Oracle | Oracle JDBC: `oracle.net.CONNECT_TIMEOUT` | Mili giây đối với thuộc tính JDBC minh họa |
| **Socket read timeout** | Chờ một thao tác đọc dữ liệu qua socket sau khi kết nối đã hình thành | Oracle JDBC: `oracle.jdbc.ReadTimeout` | Mili giây |
| **SQL statement/query timeout** | Thời gian driver cho phép một lần thực thi statement trước khi yêu cầu hủy | JDBC: `Statement.setQueryTimeout(seconds)` | Giây |
| **HTTP/request deadline** | Ngân sách thời gian từ góc nhìn API hoặc tác vụ nghiệp vụ | Cấu hình của ứng dụng/gateway | Tùy framework |
| **Idle/lifetime của pool** | Thời gian kết nối vật lý được giữ rảnh hoặc sống trong pool | HikariCP: `idleTimeout`, `maxLifetime` | Mili giây |

**Timeout không đồng nghĩa với thời gian chạy chắc chắn tối đa.** Ví dụ, `ReadTimeout` giới hạn việc chờ đọc trên socket; nó không phải “toàn bộ câu SQL phải kết thúc trong 15 giây”. `setQueryTimeout` phụ thuộc cách driver thực hiện việc hủy lệnh; thời điểm hủy và thời điểm phía cơ sở dữ liệu thực sự ngừng công việc có thể khác nhau. Một HTTP client đã bỏ cuộc cũng không tự động có nghĩa giao dịch Oracle đã bị hủy.

Đơn vị phải được kiểm tra kỹ theo **đúng phiên bản Oracle JDBC, pool và framework** đang sử dụng. Một giá trị `10` ở thuộc tính tính bằng mili giây khác hoàn toàn `10` giây ở API JDBC. Không suy luận ý nghĩa chỉ dựa vào tên “timeout”.

### 2.2. Chọn timeout theo ngân sách xử lý

Giả sử một API thường cần hoàn thành trong khoảng 5 giây. Có thể cân nhắc:

1. Giới hạn thời gian **chờ connection từ pool** ngắn, để ứng dụng sớm phát hiện quá tải.
2. Giới hạn riêng thời gian **tạo kết nối mạng**, tránh treo lâu khi Oracle hoặc đường mạng bị lỗi.
3. Đặt **query timeout** phù hợp với đặc điểm truy vấn; truy vấn nghiệp vụ nhanh khác với báo cáo chạy lâu.
4. Có **read timeout** để tránh chờ socket vô hạn; tránh đặt quá ngắn so với tác vụ hợp lệ.
5. Quản lý **deadline tổng** ở ứng dụng hoặc hệ thống gọi và cách hủy/rollback sau khi hết thời gian.

Các giới hạn này có thể chồng lấn và tác động trong những thời điểm khác nhau, không đơn giản là cộng lại thành một thời gian cố định. Ví dụ, connection đã có sẵn trong pool thì không cần thực hiện bước TCP connect mới cho mỗi request. Ngược lại, một thao tác đang trong giao dịch có thể tốn thời gian chờ khóa hoặc xử lý rollback sau khi nhận lỗi.

Không nên áp dụng một timeout rất ngắn cho mọi truy vấn. Hãy bắt đầu từ nhu cầu người dùng, độ trễ mạng thực tế, phân phối thời gian thực thi SQL và đặc điểm xử lý; sau đó phân loại truy vấn tương tác, batch và báo cáo nếu cần giới hạn khác nhau.

### 2.3. Java JDBC: cấu hình timeout ở từng lớp

Ví dụ sau cho thấy ứng dụng Java truyền các giới hạn khi **tự tạo kết nối JDBC**. Đây là các giá trị minh họa, cần hiệu chỉnh theo môi trường:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Properties;

public class OracleConnectionExample {
    public static void main(String[] args) throws SQLException {
        String url = "jdbc:oracle:thin:@//db.example.test:1521/APP_PDB";

        Properties props = new Properties();
        props.setProperty("user", requiredEnv("ORACLE_DB_USER"));
        props.setProperty("password", requiredEnv("ORACLE_DB_PASSWORD"));

        // Ví dụ thuộc tính Oracle JDBC, đơn vị mili giây.
        props.setProperty("oracle.net.CONNECT_TIMEOUT", "5000");
        props.setProperty("oracle.jdbc.ReadTimeout", "20000");

        try (Connection connection = DriverManager.getConnection(url, props);
             PreparedStatement statement =
                 connection.prepareStatement("SELECT 1 AS ket_qua FROM dual")) {

            // JDBC chuẩn: đơn vị giây.
            statement.setQueryTimeout(10);

            try (ResultSet result = statement.executeQuery()) {
                if (result.next()) {
                    System.out.println(result.getInt(1));
                }
            }
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing required setting: " + name);
        }
        return value;
    }
}
```

Đoạn mã này cần Oracle JDBC Driver thích hợp trong classpath và một Oracle service thực tế. Host `db.example.test`, service `APP_PDB` và hai biến môi trường là giá trị minh họa. **URL dùng `@//host:port/service` ở đây chưa chứng minh rằng đường truyền đã mã hóa**: phần TLS sẽ cấu hình riêng tại mục tiếp theo. Không dùng URL ví dụ này như cấu hình bảo mật hoàn chỉnh của môi trường production.

Một số điểm kỹ thuật:

- `oracle.net.CONNECT_TIMEOUT` giới hạn thời gian thiết lập kết nối mạng trong ngữ cảnh thuộc tính Oracle JDBC; các cách cấu hình timeout qua connect descriptor hoặc các phiên bản driver khác có thể có tên/đơn vị riêng.
- `oracle.jdbc.ReadTimeout` giới hạn chờ đọc socket. Nếu đặt quá ngắn, ứng dụng có thể gặp lỗi mạng ngay cả khi phía Oracle đang thực thi công việc hợp lệ.
- `setQueryTimeout(10)` áp dụng cho statement cụ thể, không cấu hình thời gian chờ lấy connection từ pool.
- Sau lỗi timeout nghiêm trọng ở tầng mạng, không nên giả định connection vẫn dùng lại an toàn. Khi dùng pool, để pool/driver xử lý kiểm tra hoặc loại bỏ connection lỗi.
- Khi một câu lệnh ghi dữ liệu không trả kết quả do timeout mạng, **không thể mặc nhiên kết luận commit đã hay chưa xảy ra**. Phải xác minh trạng thái nghiệp vụ trước khi tự động gửi lại giao dịch có tác dụng phụ.

### 2.4. Timeout của HikariCP trong Spring Boot

Nhiều ứng dụng Java dùng Spring Boot cùng HikariCP. Cấu hình sau minh họa **thời gian chờ lấy kết nối từ pool**:

```yaml
spring:
  datasource:
    url: ${ORACLE_JDBC_URL}
    username: ${ORACLE_DB_USER}
    password: ${ORACLE_DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      connection-timeout: 3000
      validation-timeout: 1000
```

`spring.datasource.hikari.connection-timeout: 3000` có nghĩa là ứng dụng có thể chờ tối đa khoảng **3 giây để lấy được một connection từ pool** trước khi HikariCP báo lỗi. Nó **không thay thế** network connect timeout hay query timeout. `maximum-pool-size` quyết định giới hạn quy mô pool, cần cân đối với khả năng đáp ứng của Oracle và số instance ứng dụng.

Các thuộc tính Oracle JDBC về connect/read timeout cần được cấu hình trên **driver/DataSource** theo cơ chế được phiên bản Spring Boot/HikariCP và driver đang dùng hỗ trợ. Không giả định rằng `connection-timeout` của pool sẽ tự chuyển thành `oracle.net.CONNECT_TIMEOUT`.

Ví dụ trong tầng truy cập dữ liệu, `JdbcTemplate` có cơ chế thiết lập query timeout; với JDBC trực tiếp có thể dùng `Statement.setQueryTimeout`. Nếu dùng JPA/Hibernate, cấu hình timeout có thể đặt bằng query hint hoặc thuộc tính riêng, nhưng phải kiểm tra xem giá trị đó thực sự được chuyển xuống driver thế nào.

## 3. Mã hóa đường truyền: TCP, TCPS và TLS

### 3.1. Mã hóa giải quyết vấn đề gì?

Nếu dữ liệu đi từ ứng dụng đến Oracle qua mạng, cần bảo vệ nội dung như thông tin cá nhân, câu SQL, giá trị tham số, hàng kết quả và thông tin đăng nhập. **TLS** là giao thức phổ biến để tạo kênh truyền được mã hóa và xác thực danh tính phía máy chủ dựa trên chứng chỉ số.

Trong Oracle Net:

- `TCP` biểu thị kết nối Oracle Net qua TCP thông thường; tự riêng ký hiệu này **không nói lên rằng TLS đã được bật**.
- `TCPS` biểu thị Oracle Net sử dụng TLS trên TCP, với listener, chứng chỉ và phía client được cấu hình tương thích.
- Oracle cũng hỗ trợ cơ chế mã hóa mạng khác theo cấu hình Oracle Net. Nếu môi trường yêu cầu **TLS với xác thực chứng chỉ**, hãy kiểm tra rõ việc dùng **TCPS** và thiết lập kiểm tra danh tính máy chủ; đừng chỉ dựa vào việc “kết nối thành công”.

TLS bảo vệ dữ liệu **đang truyền**. Nó không thay thế mã hóa dữ liệu **lưu trên đĩa**, mã hóa backup, kiểm soát quyền Oracle, hay bảo vệ bí mật trong log và bộ nhớ ứng dụng.

### 3.2. TLS cần cả mã hóa lẫn xác thực máy chủ

Một kết nối có thể được mã hóa nhưng vẫn thiếu kiểm tra máy chủ được kết nối có đúng là đích mong muốn hay không. Vì vậy, cấu hình TLS cần đồng thời:

1. **Tin cậy chuỗi chứng chỉ**: client có chứng chỉ CA tin cậy phù hợp để xác minh chứng chỉ máy chủ.
2. **Đối chiếu danh tính máy chủ**: tên hoặc distinguished name được xác minh theo chế độ và quy tắc mà Oracle client hỗ trợ; chứng chỉ phải khớp cấu hình kết nối.
3. **Chỉ chấp nhận giao thức/bộ mã phù hợp**: theo chính sách hiện hành của tổ chức và khả năng tương thích của server, listener, driver/JDK.
4. **Quản lý vòng đời chứng chỉ**: theo dõi thời hạn, gia hạn, triển khai CA mới và đảm bảo ứng dụng tin cậy chuỗi chứng chỉ sau khi thay đổi.

**Không tắt xác minh chứng chỉ hoặc tên máy chủ để chữa lỗi kết nối.** Nếu TLS báo lỗi xác thực, hãy kiểm tra đúng hostname, CA, tên trong chứng chỉ, ngày hết hạn, đồng hồ hệ thống, cổng listener và phiên bản driver.

### 3.3. Ví dụ Oracle JDBC URL dùng TCPS

Ví dụ connect descriptor chỉ ra giao thức TCPS và yêu cầu đối chiếu danh tính máy chủ:

```text
jdbc:oracle:thin:@(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCPS)(HOST=db.example.test)(PORT=2484))
  (CONNECT_DATA=(SERVICE_NAME=app_pdb.example.test))
  (SECURITY=(SSL_SERVER_DN_MATCH=YES))
)
```

Khi đặt trong một chuỗi Java, bỏ các xuống dòng/indentation không cần thiết hoặc dùng một URL TCPS hợp lệ theo đúng cách cấu hình driver:

```java
String secureUrl =
    "jdbc:oracle:thin:@(DESCRIPTION=" +
    "(ADDRESS=(PROTOCOL=TCPS)(HOST=db.example.test)(PORT=2484))" +
    "(CONNECT_DATA=(SERVICE_NAME=app_pdb.example.test))" +
    "(SECURITY=(SSL_SERVER_DN_MATCH=YES)))";
```

**Lưu ý:** `2484` là cổng thường gặp trong ví dụ TCPS, **không phải** cổng bắt buộc của mọi hệ thống. DBA có thể cấu hình cổng khác; `SERVICE_NAME` cũng phải là service thực tế, không lấy tên ví dụ đưa vào production. Phía Oracle Listener phải phục vụ TCPS và có cấu hình chứng chỉ phù hợp. Một URL TCPS riêng lẻ chưa đủ để tạo kết nối hoạt động.

Client còn phải có **vật liệu tin cậy** phù hợp, chẳng hạn CA trong Java truststore hoặc Oracle Wallet được cấu hình cho cách kết nối đang dùng. Việc cài đặt truststore/wallet và thuộc tính chọn nó phụ thuộc JDK, Oracle JDBC Driver, loại wallet và cách triển khai. Không đưa mật khẩu truststore vào URL hay log.

Ví dụ, với triển khai sử dụng **Java truststore**, bộ phận vận hành có thể cung cấp một truststore chỉ đọc chứa CA đã được xác minh. Với triển khai dựa trên **Oracle Wallet**, wallet được đặt trong thư mục bảo mật và cấu hình client được trỏ tới vị trí đó bằng cơ chế thích hợp, chẳng hạn cấu hình Oracle Net. Hai cách triển khai không nên trộn tùy tiện; cần chọn đúng cơ chế tương ứng với phiên bản driver và chứng chỉ của server.

### 3.4. Một chiều TLS và hai chiều TLS (mTLS)

| Cơ chế | Máy chủ chứng minh danh tính bằng | Client chứng minh danh tính bằng | Ứng dụng |
| --- | --- | --- | --- |
| **TLS một chiều** | Chứng chỉ máy chủ được client kiểm tra | Thường vẫn cần phương thức đăng nhập Oracle như username/password hoặc cơ chế xác thực khác | Bảo vệ và xác thực đầu máy chủ |
| **mTLS (mutual TLS)** | Chứng chỉ máy chủ | Client còn trình bày chứng chỉ riêng để máy chủ xác minh | Xác thực hai chiều ở tầng TLS, theo chính sách hệ thống |

mTLS **không mặc nhiên đồng nghĩa đã bỏ được username/password ở tầng cơ sở dữ liệu**. Khả năng xác thực bằng chứng chỉ hay external authentication còn phụ thuộc cấu hình tài khoản, Oracle Net và chính sách của Oracle Database. Phải phân biệt **xác thực TLS** với **xác thực danh tính database user**.

### 3.5. Oracle Wallet chứa những gì?

Tên “Oracle Wallet” có thể xuất hiện trong hai ngữ cảnh:

- **Wallet chứng chỉ/khóa** phục vụ kết nối TLS, có thể chứa chứng chỉ tin cậy và tùy cấu hình có cả chứng chỉ, khóa riêng của client.
- **External Password Store** của Oracle để lưu thông tin đăng nhập cho một kết nối bí danh, giúp công cụ/client không cần ghi password trực tiếp trong lệnh gọi.

Wallet nào cũng phải được bảo vệ theo nội dung thật mà nó lưu. Không nên cho rằng “có wallet” đồng nghĩa dữ liệu đều đã được mã hóa, hoặc “dùng TCPS” đồng nghĩa password đã được loại khỏi toàn bộ hệ thống.

Ví dụ với Oracle client đã được quản trị viên **cấu hình sẵn external password store**, một công cụ như SQL*Plus có thể sử dụng cú pháp đăng nhập theo alias, chẳng hạn `sqlplus /@MYDB`. Cú pháp này chỉ hoạt động khi alias, wallet và thông tin xác thực được thiết lập phù hợp; nó không tự tạo wallet hay tự đăng nhập vào bất kỳ server nào.

## 4. Nguyên tắc quản lý mật khẩu và thông tin xác thực

### 4.1. Điều cần bảo vệ không chỉ là chuỗi password

Vật liệu nhạy cảm của kết nối Oracle có thể bao gồm:

- Mật khẩu database user và mật khẩu quản trị.
- Oracle Wallet chứa credential, khóa riêng hoặc chứng chỉ client; tệp wallet và mật khẩu mở khóa của nó nếu có.
- Secret dùng tạo hoặc truy cập credentials, ví dụ token của hệ thống quản lý bí mật.
- Cấu hình chứa thông tin đăng nhập, file profile, biến môi trường, log và bản sao lưu cấu hình.

**Hostname, service name và username** không phải lúc nào cũng là bí mật, nhưng vẫn có thể là thông tin hạ tầng nội bộ; cần chia sẻ đúng đối tượng. Ngược lại, password hoặc private key phải được xử lý như một **secret** ngay cả khi xuất hiện trong file có tên là `application.yml`, `tnsnames.ora`, script triển khai hay bản ghi debug.

### 4.2. Không nhúng mật khẩu vào code, URL hoặc Git

Tránh các cách cấu hình sau:

```java
// KHÔNG dùng trong ứng dụng thật: thông tin đăng nhập được hardcode.
String user = "app_user";
String password = "mat-khau-that";
```

```text
# KHÔNG đưa thông tin đăng nhập thật vào script, history hay log.
sqlplus app_user/mat-khau-that@MYDB
```

Mật khẩu ở đối số dòng lệnh có thể xuất hiện trong lịch sử shell, nhật ký chạy lệnh hoặc danh sách tiến trình tùy hệ điều hành và cấu hình. Mật khẩu trong repository vẫn có thể tồn tại trong lịch sử commit **sau khi xóa khỏi phiên bản mới nhất**.

Thay vào đó:

1. Trong môi trường dùng dịch vụ quản lý bí mật, **lấy secret từ secret manager/vault** qua cơ chế cấp quyền của workload, rồi đưa vào ứng dụng khi chạy.
2. Nếu môi trường phát triển dùng biến môi trường, chỉ truyền giá trị trong phiên làm việc phù hợp và hạn chế quyền đọc cấu hình, process dump, log, hệ thống giám sát. **Biến môi trường không phải kho bí mật tuyệt đối**.
3. Nếu dùng wallet hoặc file secret được mount, hạn chế quyền đọc ở tài khoản chạy ứng dụng; không đóng gói cùng mã nguồn hay image chia sẻ công khai.
4. Không in `DataSource`, `Properties`, environment dump hoặc JDBC URL có chứa credentials. Thông báo lỗi nên nêu loại kết nối thất bại và mã lỗi phù hợp, không đưa ra mật khẩu.
5. Tách bí mật của **dev, test, staging và production**. Một credential bị lộ trong bài thực hành không được phép truy cập production.

Trong ứng dụng Spring Boot, việc dùng placeholder giúp **không ghi giá trị password trực tiếp vào file nguồn**:

```yaml
spring:
  datasource:
    url: ${ORACLE_JDBC_URL}
    username: ${ORACLE_DB_USER}
    password: ${ORACLE_DB_PASSWORD}
```

Đây là giao diện để nhận cấu hình khi chạy. Cần có một cơ chế an toàn để cấp các giá trị đó; placeholder tự thân **không** mã hóa hoặc quản lý vòng đời secret. Trong production, hệ thống triển khai nên lấy giá trị từ kho secret được kiểm soát thay vì lưu bản sao thủ công trên nhiều máy.

### 4.3. Quyền tối thiểu và tách biệt tài khoản

Một chương trình chỉ đọc dữ liệu không nên dùng tài khoản quản trị như `SYS` hoặc `SYSTEM`. Mỗi loại workload nên có danh tính Oracle và quyền phù hợp:

| Danh tính | Nhu cầu điển hình | Phạm vi nên cấp |
| --- | --- | --- |
| `app_reader` | Dịch vụ truy vấn báo cáo | Quyền `CREATE SESSION` và `SELECT` trên đúng đối tượng cần đọc |
| `app_writer` | Dịch vụ ghi nghiệp vụ | Quyền kết nối và thao tác DML cần thiết trên đúng bảng hoặc thông qua API PL/SQL đã cấp |
| `schema_migrator` | Chạy migration có kiểm soát | Quyền DDL cần thiết trong giai đoạn triển khai; không dùng làm tài khoản API thường trực |
| Tài khoản DBA | Quản trị hạ tầng cơ sở dữ liệu | Quyền quản trị theo cơ chế kiểm soát, giám sát riêng |

Ví dụ minh họa cho DBA hoặc chủ sở hữu schema cấp quyền trên một bảng:

```sql
-- Chỉ minh họa GRANT; cần tồn tại user và schema tương ứng.
GRANT CREATE SESSION TO app_reader;
GRANT SELECT ON sales_owner.don_hang TO app_reader;
```

Điều này yêu cầu người thực thi có quyền cấp tương ứng. Không cấp các quyền hệ thống rộng như `SELECT ANY TABLE` chỉ để giải quyết nhanh lỗi thiếu quyền của ứng dụng. Khi một ứng dụng phải gọi stored procedure, có thể cấp `EXECUTE` trên procedure/package phù hợp và thiết kế rõ quyền của chủ sở hữu cũng như người gọi.

### 4.4. Tạo, thay đổi và thu hồi credential

Mật khẩu mạnh nên có độ dài và độ khó đoán theo chính sách doanh nghiệp; ưu tiên chuỗi được tạo ngẫu nhiên và không tái sử dụng giữa môi trường. Oracle có cơ chế password profile, trạng thái tài khoản và chính sách hết hạn tùy phiên bản/cấu hình.

Quy trình vận hành cần có:

1. **Cấp phát:** ghi nhận chủ sở hữu tài khoản, workload sử dụng, nơi secret được cấp và quyền database tương ứng.
2. **Phân phối:** tải bí mật vào đúng môi trường triển khai bằng kênh được bảo vệ, giới hạn người và dịch vụ có quyền đọc.
3. **Luân chuyển (rotation):** chuẩn bị cách cập nhật client, connection pool và phiên đang hoạt động; giảm tối đa cửa sổ dùng credential cũ. Nếu cần chuyển đổi không gián đoạn, có thể dùng nhiều danh tính/credential theo quy trình được hỗ trợ và kiểm soát rõ quyền.
4. **Thu hồi:** khi dịch vụ ngừng hoạt động, nhân sự thay đổi hoặc có nghi ngờ lộ, loại bỏ credential và quyền truy cập tương ứng.
5. **Kiểm tra:** bảo đảm thông tin cũ không tiếp tục xuất hiện trong bản sao, pipeline, log hoặc image triển khai.

Thay password trong Oracle chưa chắc khiến mọi phiên đang mở bị chấm dứt ngay lập tức; kế hoạch rotation cần tính cả **connection pool đã có kết nối vật lý**, vòng đời phiên và thời điểm tạo kết nối mới. Tránh giả định thay một biến môi trường sẽ tự động làm mọi tiến trình đang chạy dùng mật khẩu mới.

## 5. Phối hợp timeout, TLS và mật khẩu trong một cấu hình

Ba nhóm thiết lập nên được nhìn như những phần độc lập nhưng cùng phục vụ một kết nối:

```text
Java application
  |
  | 1. Lấy credential an toàn khi chạy
  | 2. Có giới hạn chờ pool + connect + read + SQL
  | 3. Có truststore / Oracle Wallet phù hợp
  v
Oracle JDBC Thin Driver
  |
  | Kết nối TCPS, kiểm tra CA và danh tính server
  v
Oracle Listener / Database
  |
  | Kiểm tra user, password hoặc cơ chế xác thực đã cấu hình
  | Áp dụng quyền và chính sách tài khoản
  v
Phiên database được cấp quyền
```

Ví dụ Java kết hợp **TCPS**, timeout và credentials được cung cấp khi chạy:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Properties;

public class SecureOracleExample {
    public static void main(String[] args) throws SQLException {
        String url =
            "jdbc:oracle:thin:@(DESCRIPTION=" +
            "(ADDRESS=(PROTOCOL=TCPS)(HOST=db.example.test)(PORT=2484))" +
            "(CONNECT_DATA=(SERVICE_NAME=app_pdb.example.test))" +
            "(SECURITY=(SSL_SERVER_DN_MATCH=YES)))";

        Properties properties = new Properties();
        properties.setProperty("user", requiredEnv("ORACLE_DB_USER"));
        properties.setProperty("password", requiredEnv("ORACLE_DB_PASSWORD"));
        properties.setProperty("oracle.net.CONNECT_TIMEOUT", "5000");
        properties.setProperty("oracle.jdbc.ReadTimeout", "20000");

        // JVM/Oracle client phải được cấu hình CA tin cậy phù hợp.
        // Không vô hiệu hóa xác minh chứng chỉ khi cấu hình thiếu.
        try (Connection connection =
                 DriverManager.getConnection(url, properties);
             PreparedStatement statement =
                 connection.prepareStatement("SELECT 1 FROM dual")) {

            statement.setQueryTimeout(10);
            try (ResultSet rows = statement.executeQuery()) {
                if (rows.next()) {
                    System.out.println("Oracle query succeeded");
                }
            }
        }
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing required setting: " + key);
        }
        return value;
    }
}
```

Ví dụ này cố ý **không** chứa mật khẩu, truststore, private key hay địa chỉ server thật. Để chạy được, cần một Oracle listener có TCPS, service hợp lệ, chứng chỉ có thể được client xác minh, tài khoản có quyền đăng nhập, Oracle JDBC Driver tương thích và một cơ chế truyền secret an toàn. Để dùng trong dịch vụ Java lâu dài, nên cung cấp `DataSource`/connection pool được quản lý và cấu hình timeout/SSL trên đúng DataSource đó.

Lưu ý thứ tự xử lý: kết nối TCPS xác minh máy chủ trước hoặc trong thiết lập kênh bảo mật theo cơ chế TLS; sau đó thông tin xác thực Oracle được kiểm tra ở tầng database. **Có TLS không đồng nghĩa tài khoản có quyền**, và **đúng mật khẩu không cứu được một kết nối TLS có chứng chỉ sai**.

## 6. Chẩn đoán lỗi theo triệu chứng

Khi kết nối thất bại, cần xác định lớp đang gặp sự cố trước khi đổi cấu hình:

| Biểu hiện | Những khả năng nên kiểm tra | Hành động đúng hướng |
| --- | --- | --- |
| Chờ lâu rồi lỗi ở bước tạo kết nối | DNS, routing, firewall, host/port, listener, connect timeout | Kiểm tra tên đích, khả năng tiếp cận mạng, listener và giới hạn connect |
| Pool báo hết thời gian chờ | Pool đã dùng hết connection, các yêu cầu giữ connection quá lâu, rò rỉ connection hoặc Oracle chậm | Xem số kết nối active/idle/waiting, truy vấn chậm, vòng đời transaction; không tăng pool vô hạn |
| TLS handshake/certificate validation lỗi | CA không tin cậy, chứng chỉ hết hạn, hostname/DN không khớp, listener không phục vụ TCPS | Kiểm tra chứng chỉ, cấu hình trust và địa chỉ đích; giữ nguyên yêu cầu xác minh server |
| Oracle trả `ORA-01017` | Username/password không hợp lệ hoặc cấu hình danh tính sai | Kiểm tra secret được cấp và tên tài khoản; không ghi password vào log để “debug” |
| Oracle trả `ORA-28000` hoặc `ORA-28001` | Tài khoản bị khóa hoặc mật khẩu hết hạn | Làm việc với DBA/quy trình rotation; không tự tắt chính sách tài khoản |
| SQL chạy lâu rồi bị hủy | Khóa, kế hoạch SQL, khối lượng dữ liệu, statement timeout hoặc read timeout | Xem thời gian SQL và trạng thái transaction; chỉnh đúng lớp timeout sau khi tìm nguyên nhân |
| Chỉ lỗi sau khi ứng dụng chạy lâu | Kết nối rảnh bị thiết bị mạng đóng, pool giữ connection đã hỏng, thay đổi mật khẩu/certificate | Kiểm tra khả năng kiểm chứng connection, lifecycle pool, sự kiện thay đổi hạ tầng |

Mã lỗi cụ thể và thông điệp phụ thuộc vào **phiên bản Oracle Database, driver, mạng và công cụ**, nên bảng chỉ giúp khoanh vùng. Ví dụ, lỗi TCP/TLS có thể xuất hiện dưới dạng ngoại lệ Java, lỗi Oracle Net hoặc mã lỗi Oracle khác tùy điểm phát hiện.

### Một quy trình xử lý có thứ tự

1. **Xác định loại kết nối**: TCP hay TCPS, JDBC Thin hay công cụ Oracle khác; phiên bản Oracle JDBC/JDK nào?
2. **Kiểm tra host, port và service name** trong cấu hình triển khai. Một cổng mở không chứng minh chứng chỉ hợp lệ, credential đúng hoặc service có thể truy cập.
3. **Nếu dùng TCPS, kiểm tra trust và danh tính server** trước khi xử lý tiếp tài khoản. Không sửa lỗi bằng việc tắt kiểm tra chứng chỉ.
4. **Kiểm tra danh tính và quyền Oracle** qua thông báo lỗi đã được lọc bí mật; làm rõ tài khoản nào được ứng dụng sử dụng.
5. **Xác định giai đoạn timeout**: đang chờ pool, tạo socket, đọc dữ liệu, thực thi statement hay chờ HTTP?
6. **Đối chiếu số liệu**: latency kết nối, active/waiting connections, thời gian câu SQL, tỷ lệ lỗi theo loại, thay đổi cấu hình, thời điểm rotation.
7. **Thử lại có kiểm soát**, nhất là với giao dịch ghi; chỉ retry tự động khi có quy tắc rõ về tính idempotent và trạng thái commit.

Không cần đưa mật khẩu vào câu lệnh kiểm tra. Khi xác thực đã thành công, một truy vấn nhẹ như sau đủ chứng minh rằng client có thể thực thi SQL:

```sql
SELECT 1 AS ket_noi_ok FROM dual;
```

Truy vấn này **không chứng minh đường truyền đang dùng TLS** và cũng không chứng minh mọi quyền nghiệp vụ đã được cấp. Việc xác nhận TLS cần dựa vào cấu hình client/server, chứng chỉ được kiểm tra và thông tin quan sát phù hợp ở môi trường thực tế.

## 7. Nguyên tắc retry và xử lý giao dịch khi timeout

Timeout và retry có quan hệ chặt chẽ. Một lệnh bị timeout ở client có thể dẫn đến các kết quả khác nhau: server chưa nhận lệnh, đang xử lý, đã rollback hoặc đã hoàn thành một phần/giao dịch khác theo phạm vi mà ứng dụng kiểm soát. Vì vậy:

- **Truy vấn đọc đơn thuần:** Có thể retry giới hạn số lần khi lỗi có tính chất tạm thời, nhưng vẫn cần quan tâm tính nhất quán và tải tăng lên khi nhiều client retry đồng thời.
- **Ghi dữ liệu:** Không retry vô điều kiện. Ví dụ, client gửi lệnh tạo đơn rồi mất kết nối trước khi nhận phản hồi; gửi lại có thể tạo hai đơn nếu không có mã yêu cầu duy nhất và quy tắc chống lặp.
- **Giao dịch nhiều câu SQL:** Phải có một ranh giới transaction và nguyên tắc rollback rõ ràng. Khi không xác định được trạng thái commit, tra cứu bằng khóa nghiệp vụ hoặc idempotency key trước khi thực hiện lại.
- **Lỗi do credential/TLS sai:** Retry liên tục thường vô ích; chỉ làm tăng log và gây tải. Cần sửa cấu hình hoặc chứng chỉ/secret.

Ví dụ một API tạo đơn có thể nhận `request_id` duy nhất, lưu nó với ràng buộc `UNIQUE`, và khi timeout hoặc retry kiểm tra liệu yêu cầu đã được xử lý. Đây chỉ là một phần của thiết kế tính idempotent; cần tính thêm transaction, phản hồi nghiệp vụ và xử lý lỗi cạnh tranh.

## 8. Một vài lựa chọn cấu hình cần tránh

| Cách làm sai | Vì sao có vấn đề | Cách tiếp cận phù hợp hơn |
| --- | --- | --- |
| Chỉ đặt Hikari `connectionTimeout` rồi coi mọi truy vấn đã có timeout | Pool wait và thời gian chạy SQL là hai lớp khác nhau | Đặt timeout theo pool, connect, read và statement phù hợp |
| Đặt mọi timeout bằng một số nhỏ mà không đọc đơn vị | Dễ nhầm mili giây với giây, làm hỏng request hợp lệ | Ghi rõ đơn vị và kiểm tra tài liệu đúng phiên bản |
| Tắt kiểm tra chứng chỉ vì TCPS báo lỗi | Có thể làm mất khả năng xác thực máy chủ | Sửa hostname, CA, chứng chỉ hoặc cấu hình listener |
| Dùng tài khoản DBA cho API | Khi credential lộ, mức ảnh hưởng rất lớn | Tạo tài khoản ứng dụng với quyền tối thiểu |
| Đưa mật khẩu vào JDBC URL hoặc command line | Bí mật dễ lọt vào log, process list, history | Dùng secret manager, wallet hoặc cơ chế cấp secret an toàn |
| Lưu secret thật trong `application.yml` và commit Git | Dữ liệu vẫn có thể tồn tại trong lịch sử Git | Dùng placeholder và cấp secret lúc triển khai |
| Tăng pool size mỗi khi gặp timeout | Có thể tăng tải Oracle và làm trầm trọng tình trạng nghẽn | Điều tra thời gian giữ connection, SQL chậm, transaction và giới hạn DB |
| Retry mọi lệnh `INSERT` sau timeout | Có nguy cơ lặp tác dụng phụ khi kết quả commit chưa rõ | Thiết kế idempotency và kiểm tra trạng thái trước khi retry |
| Chỉ bảo vệ password mà công khai wallet/private key | Kẻ khác vẫn có thể sử dụng thông tin xác thực nhạy cảm | Áp dụng phân quyền, rotation và giám sát cho toàn bộ vật liệu xác thực |

## 9. Bài thực hành với cấu hình giả lập

Không cần mật khẩu thật để luyện cách suy luận cấu hình. Giả sử một API Java có các thiết lập minh họa:

```text
Pool acquisition timeout : 3 giây
Network connect timeout  : 5 giây
Socket read timeout      : 20 giây
SQL statement timeout    : 10 giây
Transport                : TCPS, yêu cầu xác minh máy chủ
Database credentials     : cấp từ secret manager khi khởi động
```

Hãy tự giải thích từng tình huống:

1. **Cả 10 connection trong pool đều đang được sử dụng** và không connection nào được trả về trong 3 giây. Ứng dụng nên nhận lỗi từ lớp nào? Tăng network connect timeout có giúp không?
2. **Server trả về chứng chỉ không khớp danh tính đích**. Đổi mật khẩu có giải quyết lỗi không? Tại sao không nên tắt `SSL_SERVER_DN_MATCH`?
3. **Câu SQL báo timeout sau 10 giây**. Có thể kết luận socket read timeout 20 giây đã bị vượt quá không? Có thể kết luận Oracle đã rollback mọi giao dịch liên quan không?
4. **Password bị thay đổi trong kho secret**, nhưng ứng dụng vẫn giữ nhiều connection cũ trong pool. Cần quản lý vòng đời tiến trình và connection như thế nào để việc rotation có hiệu lực?
5. **Lệnh tạo đơn bị timeout sau khi gửi**. Trước khi retry, ứng dụng nên dùng thông tin nghiệp vụ nào để tránh tạo trùng đơn?

Gợi ý suy luận: tình huống (1) nằm ở pool; (2) nằm ở xác thực máy chủ qua TLS; (3) cần tách statement timeout khỏi socket read timeout và trạng thái transaction; (4) liên quan secret distribution và lifecycle pool; (5) liên quan idempotency cùng xác minh trạng thái sau lỗi kết nối.

## 10. Mô hình vận hành có thể áp dụng

Đối với **môi trường phát triển cá nhân**, có thể dùng một Oracle sandbox với tài khoản có quyền hạn chế, cấu hình timeout có chủ đích và dữ liệu thực hành không nhạy cảm. Nếu kết nối qua mạng, vẫn cần kiểm tra cách mã hóa và xác thực máy chủ thay vì cho rằng môi trường dev không cần bảo vệ.

Đối với **môi trường chạy ứng dụng nhiều người dùng**, nên thiết kế một quy trình thống nhất: cấu hình connection pool có giới hạn, timeout ở đúng lớp, TCPS/TLS với CA và danh tính máy chủ được xác minh, bí mật được cấp bằng cơ chế quản lý tập trung, tài khoản Oracle theo quyền tối thiểu, quy trình rotation và quan sát lỗi không rò rỉ secret.

Nguyên tắc quan trọng là **cấu hình có thể kiểm chứng được**: biết mỗi timeout đang đo điều gì, biết client đang xác thực đúng máy chủ nào, biết credential đến từ đâu và có thể thu hồi ra sao. Khi hiểu được ba điều đó, người học có thể kết nối ứng dụng Java với Oracle một cách có kiểm soát và chẩn đoán sự cố theo nguyên nhân thực tế thay vì thử đổi ngẫu nhiên các tham số.
