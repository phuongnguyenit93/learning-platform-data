# Không nhận diện dialect và lỗi mở kết nối lúc khởi động

## 1. Vì sao ứng dụng có thể lỗi trước khi chạy repository?

Khi khởi động ứng dụng Spring Data JDBC, Spring cần tạo các thành phần persistence như JdbcConverter, DataAccessStrategy và repository proxy. Một trong những thông tin quan trọng là **database dialect**.

Dialect mô tả những khác biệt SQL theo database và JDBC driver, ví dụ:

- Cách lấy generated key.
- Cú pháp phân trang.
- Cách biểu diễn lock.
- Hỗ trợ array hoặc kiểu dữ liệu đặc thù.
- Cách xử lý một số thao tác SQL do framework tạo.

Spring Data JDBC thường tự xác định dialect bằng cách lấy một JDBC Connection và đọc metadata của database. Vì vậy, một lỗi kết nối có thể xuất hiện trong log như lỗi không xác định được dialect, dù nguyên nhân thật sự là URL, driver, credential, DNS hoặc database chưa sẵn sàng.

Hai nhóm lỗi cần phân biệt:

1. **Không có dialect phù hợp:** kết nối thành công, nhưng database product không có dialect được Spring Data JDBC nhận diện.
2. **Không lấy được connection:** resolver không thể đọc metadata vì DataSource không kết nối được database.

Nếu nhầm hai trường hợp, ứng dụng có thể được sửa bằng custom dialect trong khi lỗi thực tế là sai hostname hoặc thiếu JDBC driver.

## 2. Dialect được Spring Data JDBC xác định như thế nào?

Spring Data JDBC sử dụng interface JdbcDialect để đóng gói các hành vi phụ thuộc database hoặc JDBC driver.

Theo cấu hình mặc định:

1. Spring tạo DataSource và NamedParameterJdbcOperations.
2. AbstractJdbcConfiguration tạo bean dialect.
3. DialectResolver sử dụng JDBC operations để lấy connection.
4. Resolver đọc Connection.getMetaData().
5. Các provider kiểm tra database product và trả về dialect phù hợp.
6. Dialect được dùng khi tạo converter và data access strategy.

Có thể hình dung:

~~~text
Spring ApplicationContext
        |
        v
DataSource
        |
        v
NamedParameterJdbcOperations
        |
        v
DialectResolver
        |
        v
JDBC Connection
        |
        v
DatabaseMetaData
        |
        +--> Database product được hỗ trợ
        |          |
        |          v
        |      JdbcDialect
        |
        +--> Database product chưa được hỗ trợ
                   |
                   v
             NoDialectException
~~~

Nếu resolver không lấy được connection, quá trình đọc metadata cũng thất bại. Khi đó, exception gốc từ JDBC thường quan trọng hơn dòng lỗi ngoài cùng trong stack trace.

## 3. Những database có dialect tích hợp

Tài liệu Spring Data Relational 4.1.1 liệt kê các database có dialect tích hợp trực tiếp:

| Database | Ghi chú |
| --- | --- |
| DB2 | IBM DB2 |
| H2 | Database nhúng thường dùng trong test |
| HSQLDB | Database nhúng |
| MariaDB | Dùng JDBC driver tương ứng |
| Microsoft SQL Server | Dùng Microsoft JDBC driver |
| MySQL | Dùng MySQL Connector/J |
| Oracle | Dùng Oracle JDBC driver |
| PostgreSQL | Dùng PostgreSQL JDBC driver |

Nếu dùng một database khác, Spring Data JDBC không thể mặc định giả định rằng cú pháp SQL của một dialect hiện có sẽ tương thích. Ứng dụng cần dialect do vendor cung cấp hoặc dialect tùy chỉnh.

Tên sản phẩm database mà JDBC driver trả về trong DatabaseMetaData có vai trò trong quá trình nhận diện. Hai database có giao thức tương tự vẫn có thể trả về tên product khác nhau, vì vậy không nên chỉ dựa vào việc chúng cùng hỗ trợ một bộ cú pháp SQL.

## 4. Phân biệt lỗi dialect với lỗi kết nối

### 4.1. Không có dialect phù hợp

Nếu connection thành công và resolver đọc được metadata, nhưng không provider nào trả về dialect, Spring Data JDBC có thể ném DialectResolver.NoDialectException.

Thông điệp có thể cho biết không thể xác định dialect từ DataSource. Khi đó cần kiểm tra:

- Database product name và version.
- Database có nằm trong danh sách hỗ trợ của phiên bản Spring Data Relational đang dùng không.
- JDBC driver có trả metadata chính xác không.
- Database có phải một sản phẩm tương thích nhưng đổi tên hoặc mở rộng từ database khác không.
- Ứng dụng có custom provider hoặc dialect bean phù hợp chưa.

### 4.2. Không lấy được connection

Nếu resolver không thể lấy connection, nguyên nhân thường nằm ở cấu hình hoặc trạng thái database:

- Database chưa khởi động hoặc chưa ready.
- Sai hostname, port hoặc database name.
- DNS không phân giải được hostname.
- Container ứng dụng dùng localhost thay vì service hostname.
- Firewall, security group hoặc network policy chặn kết nối.
- Sai username/password.
- JDBC driver không có trong runtime classpath.
- TLS hoặc certificate không hợp lệ.
- Connection pool không lấy được connection.

Trong trường hợp này, sửa dialect sẽ không giải quyết được vấn đề. Hãy tìm exception gốc như UnknownHostException, ConnectException, SocketTimeoutException, lỗi authentication hoặc lỗi load JDBC driver.

## 5. Kiểm tra JDBC driver và dependency

Spring Boot có thể suy ra driver class từ JDBC URL đối với phần lớn database. Tuy nhiên, driver vẫn phải có trong runtime classpath.

Ví dụ dependency Gradle:

~~~groovy
runtimeOnly("org.postgresql:postgresql")
~~~

Một số driver thường gặp:

| Database | Dependency thường dùng |
| --- | --- |
| PostgreSQL | org.postgresql:postgresql |
| MySQL | com.mysql:mysql-connector-j |
| MariaDB | org.mariadb.jdbc:mariadb-java-client |
| Microsoft SQL Server | com.microsoft.sqlserver:mssql-jdbc |
| Oracle | com.oracle.database.jdbc:ojdbc11 hoặc phiên bản phù hợp |
| H2 | com.h2database:h2 |

Tên artifact và phiên bản cần theo JDK, database và dependency management của dự án.

### 5.1. Lỗi No suitable driver

Lỗi này thường có nghĩa DriverManager không tìm được JDBC driver phù hợp với URL.

Kiểm tra:

- Dependency driver có được đưa vào runtime classpath không.
- URL có bắt đầu bằng prefix đúng không.
- Driver có hỗ trợ URL và database version không.
- Có khai báo driver class sai hoặc cũ không.

Ví dụ URL phổ biến:

~~~text
jdbc:postgresql://db-host:5432/orders
jdbc:mysql://db-host:3306/orders
jdbc:mariadb://db-host:3306/orders
jdbc:sqlserver://db-host:1433;databaseName=orders
jdbc:oracle:thin:@//db-host:1521/orders
~~~

### 5.2. Không cần khai báo driver-class-name trong mọi trường hợp

Spring Boot thường suy ra driver class từ URL. Cấu hình URL và driver dependency đúng thường đã đủ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
~~~

Chỉ đặt spring.datasource.driver-class-name khi cần chỉ định rõ một driver class đặc biệt hoặc Boot không thể suy ra driver từ URL. Nếu khai báo class name, class đó phải tồn tại và có thể load được.

## 6. Kiểm tra DataSource configuration

Spring Boot đọc cấu hình DataSource từ các thuộc tính spring.datasource.*. Những thuộc tính quan trọng:

| Thuộc tính | Mục đích |
| --- | --- |
| spring.datasource.url | JDBC URL |
| spring.datasource.username | Tài khoản database |
| spring.datasource.password | Mật khẩu |
| spring.datasource.driver-class-name | Driver class nếu cần chỉ định tường minh |
| spring.datasource.hikari.connection-timeout | Thời gian chờ lấy connection từ HikariCP |
| spring.datasource.hikari.maximum-pool-size | Số connection tối đa trong pool |
| spring.datasource.hikari.minimum-idle | Số connection idle tối thiểu |

Không đặt password trực tiếp trong source control. Dùng environment variable, secret manager hoặc cơ chế quản lý cấu hình phù hợp.

### 6.1. Kiểm tra active profile

Một nguyên nhân thường gặp là ứng dụng chạy profile khác với profile mà developer đang xem:

- application.yml khai báo database local.
- application-prod.yml khai báo database production.
- Biến môi trường ghi đè URL hoặc username.
- CI/CD truyền giá trị cũ.

Kiểm tra profile đang active và giá trị URL thực tế sau khi resolve. Có thể log hostname, port, database name và driver class, nhưng không log password hoặc toàn bộ secret.

### 6.2. Khi tự khai báo DataSource bean

Nếu ứng dụng tự tạo bean DataSource, Spring Boot thường back off khỏi DataSource auto-configuration. Khi đó, không nên giả định mọi thuộc tính spring.datasource.* sẽ tự động được áp dụng vào bean tự tạo.

Kiểm tra code cấu hình:

- DataSource dùng URL nào?
- Bean nào được đánh dấu Primary?
- NamedParameterJdbcOperations đang dùng DataSource nào?
- TransactionManager có quản lý cùng DataSource không?
- Spring Data JDBC repositories đang được cấu hình với đúng operations/transaction manager không?

## 7. Kiểm tra hostname, port và network

### 7.1. Ứng dụng chạy trên máy host

Nếu database chạy local trên máy developer, URL thường dùng localhost và port được database expose:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
~~~

### 7.2. Ứng dụng chạy trong Docker

Nếu cả ứng dụng và database chạy trong Docker Compose, localhost bên trong container ứng dụng trỏ về chính container ứng dụng, không phải container database.

Ví dụ service database có tên postgres:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/orders
~~~

Tên service thường được Docker Compose đăng ký trong network nội bộ. Từ máy host, developer có thể dùng localhost và port mapping; từ container ứng dụng, nên dùng service hostname và port nội bộ.

### 7.3. Kiểm tra các điểm network

- Hostname có phân giải được từ môi trường chạy ứng dụng không?
- Port database có đang listen không?
- Database chỉ listen trên loopback hay trên interface cần thiết?
- Firewall hoặc network policy có chặn traffic không?
- Container ứng dụng có cùng network với database không?
- Port đang dùng là port host hay port container?
- TLS mode và certificate có đúng với server không?

Không dựa vào việc database client trên laptop kết nối được để kết luận rằng container hoặc máy chủ ứng dụng cũng kết nối được. Hãy thử từ đúng môi trường network mà ứng dụng đang chạy.

## 8. Kiểm tra database đã sẵn sàng chưa?

Một container database có thể đã được tạo nhưng chưa sẵn sàng nhận kết nối. Nếu ứng dụng khởi động ngay khi container vừa chạy, DialectResolver có thể lấy connection quá sớm.

Trong môi trường container:

- Dùng healthcheck cho database.
- Dùng depends_on với điều kiện service healthy nếu runtime hỗ trợ.
- Cấu hình retry/startup orchestration phù hợp.
- Không chỉ kiểm tra process tồn tại; cần kiểm tra database đã accept connection.

Trong môi trường production:

- Xác nhận database endpoint đã ready.
- Kiểm tra failover hoặc maintenance đang diễn ra không.
- Xác nhận DNS/service discovery đã cập nhật sau khi database chuyển node.
- Kiểm tra connection pool có retry hoặc validation theo cấu hình phù hợp không.

Nếu database unavailable lúc startup và Spring Data JDBC cần dialect bằng cách mở connection, ApplicationContext có thể không khởi động được. Cần xử lý readiness và thứ tự triển khai ở tầng vận hành.

## 9. Thử kết nối độc lập với Spring Data JDBC

Để phân biệt lỗi Spring configuration với lỗi JDBC/network, có thể thử DriverManager bằng đúng URL và driver trong cùng môi trường:

~~~java
try (Connection connection =
        DriverManager.getConnection(url, username, password)) {

    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductName());
    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());
}
~~~

Không in URL chứa password hoặc credential ra log. Đoạn kiểm tra này trả lời ba câu hỏi:

1. JDBC driver có mở được connection không?
2. Database product name/version mà driver báo là gì?
3. JDBC driver nào đang thực sự được sử dụng?

Nếu đoạn code trên không kết nối được, hãy xử lý driver, URL, credential hoặc network trước khi điều tra dialect.

Nếu kết nối thành công và metadata cho thấy một database được hỗ trợ nhưng Spring vẫn không tìm được dialect, kiểm tra version dependency, provider discovery và cấu hình DataSource/NamedParameterJdbcOperations.

## 10. Cấu hình dialect tùy chỉnh cho database chưa được hỗ trợ

Nếu database không nằm trong danh sách dialect tích hợp, có hai hướng chính:

1. Yêu cầu vendor cung cấp JdbcDialect tương thích.
2. Tự triển khai JdbcDialect cho database đó.

Không nên chỉ đổi DatabaseMetaData product name hoặc ép dùng dialect của database khác để làm ứng dụng khởi động. Dialect còn mô tả generated key, lock, array support và các hành vi SQL khác; nếu không tương thích, lỗi sẽ xuất hiện ở runtime khi repository thực thi thao tác.

### 10.1. Override jdbcDialect trong AbstractJdbcConfiguration

Nếu ứng dụng luôn chạy trên một database cụ thể và đã có custom dialect, có thể override method jdbcDialect:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.core.dialect.JdbcDialect;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;

@Configuration
public class CustomJdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    public JdbcDialect jdbcDialect(
            NamedParameterJdbcOperations operations) {
        return new CustomVendorDialect();
    }
}
~~~

CustomVendorDialect phải triển khai đầy đủ các semantics cần thiết của JdbcDialect cho database đích. Ví dụ trên chỉ minh họa điểm mở rộng; class dialect thực tế cần được viết và kiểm thử theo vendor.

Override này thay thế bước tự dò dialect mặc định. Vì vậy, chỉ dùng khi ứng dụng biết chắc database đang kết nối và dialect trả về thực sự tương thích.

### 10.2. Đăng ký JdbcDialectProvider

Nếu muốn Spring tự phát hiện dialect thông qua SPI, triển khai DialectResolver.JdbcDialectProvider và đăng ký provider qua SpringFactoriesLoader.

File resource:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung đăng ký:

~~~properties
org.springframework.data.jdbc.core.dialect.DialectResolver$JdbcDialectProvider=com.example.database.CustomVendorDialectProvider
~~~

Provider trả về dialect nếu nhận diện được database; nếu không nhận diện thì trả Optional.empty() để provider khác tiếp tục kiểm tra.

Ví dụ khung provider:

~~~java
public final class CustomVendorDialectProvider
        implements DialectResolver.JdbcDialectProvider {

    @Override
    public Optional<Dialect> getDialect(JdbcOperations operations) {
        return operations.execute((ConnectionCallback<Optional<Dialect>>) connection -> {
            DatabaseMetaData metadata = connection.getMetaData();

            if ("Custom Vendor DB".equals(metadata.getDatabaseProductName())) {
                return Optional.of(new CustomVendorDialect());
            }

            return Optional.empty();
        });
    }
}
~~~

Đây là skeleton. Các import cần dùng gồm JdbcOperations, ConnectionCallback, DatabaseMetaData, Optional, DialectResolver và kiểu Dialect tương ứng trong Spring Data Relational. Provider nên nhận diện theo product/version đủ chính xác để không vô tình chọn dialect cho một database khác.

Từ Spring Data Relational 3.5, DialectResolver mới nằm trong package org.springframework.data.jdbc.core.dialect. API ở package org.springframework.data.jdbc.repository.config đã deprecated và được chuyển đi; khi viết provider mới, dùng package hiện hành của phiên bản dự án.

## 11. Nhiều DataSource và sai dialect

Một ứng dụng có thể kết nối nhiều database:

- Database đơn hàng.
- Database báo cáo.
- Database legacy.

Khi đó, mỗi repository group cần dùng đúng DataSource, NamedParameterJdbcOperations và transaction manager.

Nếu Spring Data JDBC lấy operations của database A nhưng repository thực tế lại dùng database B, dialect có thể được xác định theo A trong khi SQL chạy trên B. Điều này có thể gây lỗi cú pháp hoặc generated key không tương thích.

Khi cấu hình nhiều repository group, kiểm tra:

- Base package của từng nhóm repository.
- DataSource được dùng bởi NamedParameterJdbcOperations.
- Transaction manager tương ứng.
- Bean được đánh dấu Primary.
- JdbcOperations reference mà repository configuration chọn.
- Dialect của từng database.

Không dùng một dialect chung cho nhiều database chỉ vì chúng cùng loại driver hoặc cùng vendor nếu phiên bản/biến thể của chúng có khác biệt SQL quan trọng.

## 12. Các thông báo lỗi thường gặp

| Thông báo hoặc nguyên nhân gốc | Ý nghĩa có thể | Hướng xử lý |
| --- | --- | --- |
| DialectResolver.NoDialectException | Không provider nào nhận diện được database product | Kiểm tra product name, database support và custom dialect |
| Failed to obtain JDBC Connection | DataSource không lấy được connection | Kiểm tra URL, credentials, network, database readiness và pool |
| No suitable driver | Driver không nhận URL hoặc chưa có trong classpath | Thêm đúng driver dependency và sửa JDBC URL |
| Failed to determine a suitable driver class | Boot không tìm thấy driver và không có embedded database phù hợp | Cấu hình URL và dependency driver |
| UnknownHostException | Hostname không phân giải được | Kiểm tra DNS, service name và network |
| Connection refused | Host reachable nhưng port không nhận kết nối | Kiểm tra database process, listen address, port mapping và firewall |
| SocketTimeoutException | Kết nối hoặc phản hồi quá thời gian | Kiểm tra network, database load và timeout |
| Authentication failed | Username/password hoặc authentication policy sai | Kiểm tra secret, account và quyền connect |
| Connection is not available, request timed out | Pool không cấp connection kịp thời | Kiểm tra pool size, connection leak, transaction duration và query chậm |
| SSLHandshakeException | TLS/certificate negotiation thất bại | Kiểm tra truststore, certificate, hostname verification và SSL mode |

Thông báo ngoài cùng có thể chỉ là BeanCreationException hoặc UnsatisfiedDependencyException. Hãy đọc sâu xuống root cause trong stack trace để xác định lỗi thực tế.

## 13. Quy trình chẩn đoán theo thứ tự

Khi ứng dụng không khởi động và log nhắc đến dialect hoặc connection, hãy làm theo trình tự:

1. **Đọc root cause:** xác định lỗi cuối cùng là NoDialectException, driver, authentication hay network.
2. **Kiểm tra profile:** xác nhận profile đang active và DataSource URL thực tế.
3. **Kiểm tra dependency:** xác nhận JDBC driver có trong runtime classpath.
4. **Kiểm tra URL:** scheme, hostname, port, database/service name và tham số TLS.
5. **Thử kết nối trực tiếp:** dùng cùng URL/credential từ môi trường chạy ứng dụng.
6. **Đọc DatabaseMetaData:** xác nhận product name, version và driver name.
7. **Kiểm tra danh sách dialect:** database có được phiên bản Spring Data Relational hỗ trợ không?
8. **Kiểm tra DataSource wiring:** Spring Data JDBC có đang dùng đúng operations và transaction manager không?
9. **Nếu database chưa hỗ trợ:** triển khai JdbcDialect hoặc provider phù hợp.
10. **Khởi động lại và kiểm tra log:** xác nhận dialect được tạo và repository có thể thực thi query cơ bản.

Không thêm custom dialect để che một lỗi connection refused hoặc sai mật khẩu. Dialect chỉ giải quyết khác biệt SQL; nó không mở được socket hoặc xác thực database.

## 14. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Máy developer chạy được, container không kết nối được | URL dùng localhost bên trong container | Dùng service hostname và port nội bộ của database |
| Profile local đúng nhưng production sai | Environment variable ghi đè URL hoặc active profile khác | Kiểm tra resolved configuration và deployment variables |
| Driver class không load được | Khai báo class name cũ hoặc thiếu dependency | Dùng driver class đúng với artifact hiện tại; ưu tiên suy ra từ URL khi có thể |
| Database client kết nối được nhưng ứng dụng không được | Ứng dụng chạy ở network khác hoặc dùng credential khác | Thử kết nối từ đúng container/host và cùng secret |
| H2 chạy nhưng PostgreSQL không chạy | SQL hoặc dialect khác nhau | Test trên database production bằng Testcontainers |
| Có hai DataSource nhưng dialect không đúng | Repository đang inject nhầm NamedParameterJdbcOperations | Kiểm tra bean wiring, Primary và repository configuration |
| Database product mới không được nhận diện | Spring Data Relational cũ chưa có provider phù hợp | Nâng cấp version tương thích hoặc bổ sung dialect provider |
| Ứng dụng fail ngay khi database restart | Dialect/connection được lấy lúc khởi động | Kiểm tra readiness, retry và chiến lược restart/recovery của ứng dụng |

## 15. Kiểm thử cấu hình kết nối và dialect

Nên có một số kiểm tra tự động hoặc smoke test cho môi trường:

### 15.1. Kiểm tra DataSource

- Lấy một connection.
- Đọc DatabaseMetaData.
- Xác nhận product name và version đúng.
- Chạy một câu SELECT đơn giản.

### 15.2. Kiểm tra dialect

Nếu dùng dialect tích hợp, xác nhận ứng dụng khởi động và một repository query đơn giản thực thi được.

Nếu dùng custom dialect, kiểm tra:

- Provider được load từ META-INF/spring.factories.
- Provider nhận diện đúng product/version.
- Provider trả Optional.empty() cho database khác.
- Dialect hỗ trợ generated key, lock, paging và các tính năng ứng dụng thực sự dùng.

### 15.3. Kiểm thử trên database thật

Dùng Testcontainers hoặc database integration tương ứng với production. H2 không thể chứng minh dialect PostgreSQL, MySQL hoặc SQL Server hoạt động đúng.

Kiểm tra cả quá trình khởi động context, tạo repository, save aggregate và query aggregate có quan hệ.

## 16. Bài tập tự thực hành

**Bài tập 1 — Thiếu driver.** Xóa JDBC driver dependency khỏi runtime classpath, chạy ứng dụng và ghi lại root cause. Thêm dependency trở lại và xác nhận kết nối.

**Bài tập 2 — Sai URL.** Đổi port database thành một port không listen. Phân biệt Connection refused với NoDialectException trong stack trace.

**Bài tập 3 — Sai hostname trong Docker.** Dùng localhost từ container ứng dụng, quan sát lỗi, sau đó đổi sang service hostname của database.

**Bài tập 4 — Metadata.** Viết đoạn code dùng DatabaseMetaData để in product name, product version và driver name mà ứng dụng thực sự nhận được.

**Bài tập 5 — Database không được hỗ trợ.** Tạo một JdbcDialectProvider thử nhận diện product name giả lập và trả Optional.empty() cho database khác.

**Bài tập 6 — Override dialect.** Kế thừa AbstractJdbcConfiguration, override jdbcDialect và giải thích vì sao cách này bỏ qua bước autodetect.

**Bài tập 7 — Nhiều DataSource.** Cấu hình hai repository group dùng hai database khác nhau. Xác nhận mỗi group dùng đúng operations và transaction manager.

**Bài tập 8 — Smoke test.** Tạo test khởi động Spring context trên Testcontainers và thực thi một repository query để kiểm tra dialect cùng kết nối.

## 17. Ghi nhớ

Spring Data JDBC cần một JdbcDialect để biểu diễn khác biệt SQL của database. DialectResolver thường lấy JDBC Connection và đọc DatabaseMetaData để xác định database product. Vì bước này cần kết nối thật, lỗi mở connection lúc khởi động có thể xuất hiện như lỗi không xác định dialect.

Hãy phân biệt database product không được hỗ trợ với lỗi URL, driver, credentials, DNS, port, TLS hoặc database chưa ready. Đọc root cause trong stack trace và thử kết nối từ đúng môi trường chạy ứng dụng trước khi thay đổi dialect.

Spring Data Relational 4.1.1 hỗ trợ dialect tích hợp cho DB2, H2, HSQLDB, MariaDB, SQL Server, MySQL, Oracle và PostgreSQL. Với database khác, dùng vendor dialect hoặc triển khai JdbcDialect cùng JdbcDialectProvider; có thể override AbstractJdbcConfiguration.jdbcDialect khi ứng dụng dùng một database cố định.

### Tài liệu tham khảo

- [Spring Data Relational – Getting Started and Dialects](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html)
- [Spring Data Relational – DialectResolver API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/dialect/DialectResolver.html)
- [Spring Data Relational – JdbcDialectProvider API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/dialect/DialectResolver.JdbcDialectProvider.html)
- [Spring Data Relational – AbstractJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/AbstractJdbcConfiguration.html)
- [Spring Boot – SQL Databases and DataSource Configuration](https://docs.spring.io/spring-boot/reference/data/sql.html)
