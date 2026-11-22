# Cấu hình máy chủ, cổng, tên cơ sở dữ liệu và thông tin xác thực

Để Spring Data R2DBC kết nối được với cơ sở dữ liệu quan hệ, ứng dụng cần biết máy chủ đang chạy ở đâu, cổng nào nhận kết nối, cơ sở dữ liệu nào sẽ được sử dụng và tài khoản nào có quyền truy cập. Trong Spring Boot, các thông tin này thường được khai báo bằng cấu hình `spring.r2dbc` trong `application.yml` hoặc `application.properties`. Spring Boot dùng cấu hình đó để tạo `ConnectionFactory`, thành phần đại diện cho nguồn kết nối R2DBC mà repository, `R2dbcEntityTemplate` và `DatabaseClient` sử dụng.

Việc cấu hình đúng bốn nhóm thông tin này là bước nền tảng của kết nối. Nếu host hoặc port sai, ứng dụng không thể tới được máy chủ. Nếu tên database sai, máy chủ có thể nhận kết nối nhưng từ chối mở cơ sở dữ liệu được yêu cầu. Nếu username hoặc password sai, quá trình xác thực thất bại. Nếu dùng nhầm URL JDBC, thiếu driver R2DBC hoặc cấu hình sai môi trường, Spring Data R2DBC cũng không thể khởi tạo kết nối như mong muốn.

## 1. Bốn thông tin cơ bản của một kết nối

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Host (máy chủ) | Tên DNS hoặc địa chỉ IP của máy chủ cơ sở dữ liệu mà ứng dụng có thể truy cập từ môi trường đang chạy | `localhost`, `db.internal.example`, `10.20.0.15` |
| Port (cổng) | Cổng TCP mà dịch vụ cơ sở dữ liệu lắng nghe | PostgreSQL thường dùng `5432`; MySQL thường dùng `3306` |
| Database (tên cơ sở dữ liệu) | Cơ sở dữ liệu hoặc catalog mà kết nối sẽ sử dụng | `orders`, `customer_service` |
| Credentials (thông tin xác thực) | Tài khoản và mật khẩu được máy chủ dùng để xác thực và phân quyền | username `orders_app`, password lấy từ secret |

Các giá trị mặc định về port trong bảng chỉ là quy ước phổ biến. Quản trị viên có thể cấu hình máy chủ dùng cổng khác. Luôn lấy giá trị từ cấu hình triển khai thực tế, không suy ra port chỉ dựa vào loại database.

Ngoài bốn thông tin trên, môi trường thực tế có thể cần TLS/SSL, timeout, schema, tham số riêng của driver và cấu hình connection pool. Các phần đó bổ sung cho cấu hình kết nối cơ bản; chúng không thay thế host, port, database và credentials.

## 2. Phân biệt URL R2DBC với URL JDBC

R2DBC dùng URL có scheme `r2dbc:`. Ví dụ PostgreSQL:

```text
r2dbc:postgresql://db.example.internal:5432/orders
```

URL này cho biết driver PostgreSQL R2DBC, host `db.example.internal`, port `5432` và database `orders`.

URL JDBC tương ứng thường có dạng:

```text
jdbc:postgresql://db.example.internal:5432/orders
```

Hai URL không thể dùng thay thế cho nhau. Spring Data R2DBC cần driver triển khai R2DBC SPI và một URL `r2dbc:` phù hợp. Cấu hình `spring.datasource.url`, driver JDBC hoặc pool HikariCP thuộc mô hình JDBC truyền thống và không tự cấu hình `ConnectionFactory` cho R2DBC.

Một số scheme R2DBC phổ biến:

| Hệ quản trị | Ví dụ URL |
| --- | --- |
| PostgreSQL | `r2dbc:postgresql://localhost:5432/orders` |
| MySQL | `r2dbc:mysql://localhost:3306/orders` |
| MariaDB | `r2dbc:mariadb://localhost:3306/orders` |

Scheme và các tùy chọn sau dấu `?` phụ thuộc driver cụ thể. Hãy dùng đúng driver tương ứng với hệ quản trị và đối chiếu tài liệu driver khi cần tham số bổ sung như TLS, socket hoặc chế độ xác thực.

## 3. Khai báo kết nối trong `application.yml`

Với Spring Boot, cách thường dùng là khai báo URL, username và password trong nhóm `spring.r2dbc`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
```

Trong ví dụ này:

- `url` chứa scheme của driver, host, port và tên database.
- `username` là tài khoản dùng để xác thực với PostgreSQL.
- `password` được đọc từ biến môi trường `DB_PASSWORD` thay vì ghi trực tiếp mật khẩu vào file cấu hình.

Spring Boot đọc các thuộc tính này và tự cấu hình `ConnectionFactory` nếu driver R2DBC phù hợp có trên classpath. Khi ứng dụng dùng Spring Data R2DBC, repository và `R2dbcEntityTemplate` có thể sử dụng cơ sở kết nối được cấu hình tự động đó.

Có thể tách host, port và database thành các biến môi trường để dùng chung một file cấu hình cho nhiều môi trường:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:orders}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
```

Các biểu thức `${TEN_BIEN:gia_tri_mac_dinh}` yêu cầu Spring đọc biến môi trường nếu có, nếu không thì dùng giá trị mặc định sau dấu `:`. Ví dụ trên thuận tiện cho máy phát triển cục bộ. Với môi trường triển khai, nên cung cấp rõ các biến cần thiết và tránh dùng tài khoản hoặc mật khẩu mặc định có quyền rộng.

Nếu không có biến `DB_PASSWORD`, placeholder `${DB_PASSWORD}` không có giá trị mặc định có thể khiến ứng dụng không phân giải được cấu hình. Đây thường là hành vi mong muốn ở môi trường cần bí mật bắt buộc: ứng dụng dừng sớm và báo cấu hình thiếu thay vì âm thầm dùng mật khẩu rỗng.

## 4. Cấu hình tương đương trong `application.properties`

Nếu dự án dùng file properties thay vì YAML, các thuộc tính có thể được khai báo như sau:

```properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/orders
spring.r2dbc.username=orders_app
spring.r2dbc.password=${DB_PASSWORD}
```

Ví dụ có host, port và database lấy từ biến môi trường:

```properties
spring.r2dbc.url=r2dbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:orders}
spring.r2dbc.username=${DB_USERNAME:orders_app}
spring.r2dbc.password=${DB_PASSWORD}
```

Chọn YAML hoặc properties theo quy ước của dự án. Không cần khai báo cùng một cấu hình ở cả hai file vì điều đó dễ gây nhầm lẫn khi kiểm tra giá trị cuối cùng mà ứng dụng sử dụng.

## 5. Cài đặt dependency của driver R2DBC

Chỉ khai báo URL là chưa đủ. Ứng dụng cần dependency của driver R2DBC dành cho hệ quản trị đang dùng. Ví dụ với Maven và PostgreSQL:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Các phiên bản Spring Boot thường quản lý phiên bản dependency thông qua dependency management/BOM. Nếu dự án dùng Spring Boot, nên để BOM quản lý phiên bản tương thích thay vì tự chọn một phiên bản driver ngẫu nhiên. Với Gradle, khai báo các dependency tương đương bằng `implementation` hoặc cấu hình runtime phù hợp.

Driver R2DBC không phải driver JDBC. Ví dụ `org.postgresql:postgresql` là driver JDBC PostgreSQL; nó không thay thế `org.postgresql:r2dbc-postgresql` khi ứng dụng cần kết nối R2DBC.

Nếu dùng connection pool R2DBC, cần có thư viện pool tương ứng trên classpath. Spring Boot có thể tự cấu hình pool khi dependency pool hiện diện và pool được bật. Cấu hình pool được trình bày ở phần sau.

## 6. Cấu hình theo từng hệ quản trị cơ sở dữ liệu

### PostgreSQL

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:orders}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
```

Driver thường dùng là `org.postgresql:r2dbc-postgresql`. Port mặc định phổ biến của PostgreSQL là `5432`, nhưng phải dùng port được máy chủ hoặc dịch vụ quản lý cơ sở dữ liệu công bố.

### MySQL

```yaml
spring:
  r2dbc:
    url: r2dbc:mysql://${DB_HOST:localhost}:${DB_PORT:3306}/${DB_NAME:orders}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
```

Driver thường dùng là `io.asyncer:r2dbc-mysql` trong các dự án sử dụng driver MySQL R2DBC hiện hành. Hãy kiểm tra tài liệu và dependency management của phiên bản driver mà dự án chọn; không lấy driver JDBC MySQL để thay thế.

### MariaDB

```yaml
spring:
  r2dbc:
    url: r2dbc:mariadb://${DB_HOST:localhost}:${DB_PORT:3306}/${DB_NAME:orders}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
```

MariaDB có driver R2DBC riêng. Không nên mặc định mọi tùy chọn URL của MySQL đều áp dụng giống hệt cho MariaDB; tham số kết nối và TLS phải theo tài liệu của driver được sử dụng.

## 7. Hiểu đúng host trong từng môi trường

Giá trị `localhost` có nghĩa là máy hoặc network namespace nơi tiến trình ứng dụng đang chạy. Vì vậy, host đúng phụ thuộc cách triển khai:

| Môi trường | Host thường dùng | Giải thích |
| --- | --- | --- |
| Ứng dụng chạy trực tiếp trên máy phát triển, database cũng chạy trên máy đó | `localhost` hoặc `127.0.0.1` | Kết nối qua loopback của máy phát triển |
| Ứng dụng và database chạy trong cùng một Docker Compose network | Tên service database, ví dụ `postgres` | Các container trong cùng network phân giải nhau bằng tên service |
| Ứng dụng chạy trong container, database chạy trên máy host | Tên host gateway phù hợp với nền tảng, ví dụ `host.docker.internal` trên các môi trường hỗ trợ | `localhost` bên trong container trỏ về chính container ứng dụng |
| Ứng dụng chạy trong Kubernetes | DNS của Service, ví dụ `postgres.database.svc.cluster.local` | Pod ứng dụng truy cập Service trong cluster bằng DNS |
| Ứng dụng chạy trên máy chủ riêng và database ở máy khác | DNS hoặc IP nội bộ của database | Cần bảo đảm route, firewall và quyền truy cập mạng |

Một lỗi thường gặp là dùng `localhost` trong container hoặc Pod dù database nằm trong container/Pod khác. Khi đó ứng dụng tìm database trên chính môi trường của nó và thường nhận lỗi connection refused. Hãy xác định vị trí thực tế của tiến trình ứng dụng trước khi chọn host.

Trong Docker Compose, ví dụ cấu hình có thể là:

```yaml
services:
  app:
    environment:
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: orders
      DB_USERNAME: orders_app
      DB_PASSWORD: ${DB_PASSWORD}
    depends_on:
      - postgres

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: orders
      POSTGRES_USER: orders_app
      POSTGRES_PASSWORD: ${DB_PASSWORD}
```

Đây là ví dụ cấu trúc để minh họa DNS theo service name. `depends_on` thông thường chỉ điều khiển thứ tự khởi động container; nó không đảm bảo database đã sẵn sàng nhận kết nối. Ứng dụng vẫn cần cơ chế retry/health check phù hợp hoặc cấu hình điều phối chờ dịch vụ sẵn sàng.

## 8. Quản lý username và password an toàn

Username và password là thông tin bí mật. Không nên ghi mật khẩu thật vào Git, file cấu hình được commit, log khởi động, ảnh chụp màn hình hoặc thông báo lỗi. Một số cách cung cấp credentials thường dùng:

- **Biến môi trường:** cung cấp `DB_USERNAME` và `DB_PASSWORD` từ môi trường chạy ứng dụng.
- **Secret của nền tảng triển khai:** dùng Kubernetes Secret, secret manager của cloud hoặc hệ thống quản lý bí mật của tổ chức.
- **Cấu hình ngoài ứng dụng:** cung cấp giá trị thông qua cơ chế externalized configuration của Spring Boot.
- **Tài khoản riêng cho ứng dụng:** tạo user có quyền tối thiểu cần thiết thay vì dùng tài khoản quản trị database.

Ví dụ file YAML chỉ tham chiếu bí mật:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST}:${DB_PORT}/${DB_NAME}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

Các biến này cần được khai báo trong môi trường trước khi ứng dụng khởi động. Không đặt mật khẩu thật làm giá trị mặc định trong placeholder.

Nếu credentials được nhúng trực tiếp trong URL, các ký tự đặc biệt như `@`, `:`, `/`, `?`, `#` hoặc `%` có thể phải URL-encode để không bị hiểu nhầm là dấu phân cách trong URL. Khai báo username và password bằng thuộc tính riêng thường dễ đọc, dễ quản lý secret và ít gặp lỗi encode hơn.

Không dùng cùng một tài khoản có quyền quản trị cho mọi môi trường. Tài khoản của ứng dụng nên chỉ có quyền cần thiết để đọc, ghi hoặc thực hiện migration theo thiết kế. Tài khoản migration có thể được tách riêng với tài khoản chạy ứng dụng để giới hạn quyền lúc runtime.

## 9. Tách cấu hình theo profile

Thông tin kết nối thường khác nhau giữa máy phát triển, kiểm thử và production. Spring Profiles cho phép giữ cấu hình phù hợp trong các file riêng:

`application-dev.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders_dev
    username: orders_dev
    password: ${DB_PASSWORD:dev_only_password}
```

`application-prod.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST}:${DB_PORT}/${DB_NAME}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

Kích hoạt profile bằng biến môi trường hoặc tham số cấu hình, ví dụ:

```text
SPRING_PROFILES_ACTIVE=prod
```

Profile `prod` chỉ được dùng khi môi trường triển khai cung cấp đầy đủ các biến kết nối. Tránh commit mật khẩu phát triển có thể dùng thật; ví dụ `dev_only_password` chỉ là giá trị minh họa và cần được thay bằng secret phù hợp nếu dùng trong một môi trường dùng chung.

Spring Boot có nhiều nguồn cấu hình. Biến môi trường, tham số dòng lệnh và các nguồn cấu hình ngoài có thể ghi đè giá trị trong file. Khi ứng dụng kết nối nhầm database, hãy kiểm tra profile đang hoạt động và nguồn cấu hình cuối cùng, thay vì chỉ đọc `application.yml`.

## 10. Cấu hình connection pool R2DBC

Mở kết nối mới tới database có chi phí. Connection pool giữ một số kết nối có thể tái sử dụng để request không phải thiết lập kết nối mới cho mọi thao tác. Pool R2DBC là pool kết nối database; nó không phải thread pool và không quyết định số event-loop thread của WebFlux.

Ví dụ cấu hình pool trong Spring Boot:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:orders}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 30m
      max-life-time: 30m
      max-acquire-time: 10s
```

Ý nghĩa các thuộc tính tiêu biểu:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `enabled` | Bật cấu hình connection pool khi pool implementation có trên classpath và được hỗ trợ bởi phiên bản Spring Boot đang dùng |
| `initial-size` | Số kết nối ban đầu mà pool cố gắng tạo |
| `max-size` | Giới hạn số kết nối tối đa của pool |
| `max-idle-time` | Thời gian một kết nối có thể ở trạng thái nhàn rỗi trước khi bị loại bỏ theo chính sách pool |
| `max-life-time` | Tuổi thọ tối đa của một kết nối trong pool |
| `max-acquire-time` | Thời gian tối đa chờ lấy được kết nối từ pool |

Các thuộc tính và giá trị mặc định có thể thay đổi theo phiên bản Spring Boot và thư viện pool. Cần có dependency pool R2DBC tương thích, ví dụ `io.r2dbc:r2dbc-pool`, nếu cấu hình pool yêu cầu thư viện đó. Hãy kiểm tra cấu hình metadata và tài liệu của phiên bản đang dùng.

Không đặt `max-size` quá lớn chỉ để giảm thời gian chờ. Mỗi instance ứng dụng có pool riêng, do đó tổng số kết nối có thể mở gần bằng `max-size × số instance` khi tải cao. Ví dụ bốn instance, mỗi instance có `max-size: 20`, có thể tạo nhu cầu tối đa khoảng 80 kết nối, chưa kể tác vụ quản trị, migration và dịch vụ khác. Giá trị này phải nằm trong giới hạn database và phù hợp với khả năng xử lý của máy chủ.

Nếu `max-acquire-time` thường xuyên hết hạn, nguyên nhân có thể là pool quá nhỏ, truy vấn quá chậm, kết nối bị giữ lâu, database quá tải hoặc lưu lượng tăng đột biến. Tăng giới hạn pool mà không điều tra nguyên nhân có thể khiến database quá tải nặng hơn.

## 11. TLS và các thuộc tính riêng của driver

Trong môi trường production, kết nối tới database qua mạng có thể cần mã hóa TLS để bảo vệ dữ liệu và credentials. Cách bật TLS, xác minh chứng chỉ máy chủ, cung cấp CA certificate và lựa chọn chế độ xác thực phụ thuộc driver cùng hệ quản trị cơ sở dữ liệu.

Không có một chuỗi query parameter TLS duy nhất áp dụng cho tất cả URL R2DBC. Ví dụ, tên tùy chọn và cách biểu diễn chế độ xác minh chứng chỉ của PostgreSQL có thể khác MySQL hoặc MariaDB. Hãy tham khảo tài liệu đúng phiên bản driver, dùng CA certificate được tin cậy và ưu tiên xác minh danh tính máy chủ thay vì tắt kiểm tra chứng chỉ.

Spring Boot cho phép truyền thêm các thuộc tính kết nối qua nhóm `spring.r2dbc.properties` trong những phiên bản hỗ trợ. Tên và giá trị của các thuộc tính này do driver quyết định. Chỉ thêm thuộc tính đã được driver xác nhận; cấu hình sai có thể bị bỏ qua hoặc khiến kết nối thất bại.

## 12. Tạo `ConnectionFactory` bằng Java khi cần tùy biến

Trong ứng dụng Spring Boot thông thường, nên ưu tiên externalized configuration để Boot tự tạo `ConnectionFactory`. Một số hệ thống cần chọn cấu hình lúc chạy, kết hợp nhiều nguồn dữ liệu hoặc khởi tạo kết nối theo logic riêng. Khi đó có thể tạo `ConnectionFactory` bằng R2DBC SPI.

Ví dụ với PostgreSQL:

```java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import io.r2dbc.spi.ConnectionFactories;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class R2dbcConfiguration {

    @Bean
    ConnectionFactory connectionFactory(DatabaseSettings settings) {
        ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
                .option(ConnectionFactoryOptions.DRIVER, "postgresql")
                .option(ConnectionFactoryOptions.HOST, settings.host())
                .option(ConnectionFactoryOptions.PORT, settings.port())
                .option(ConnectionFactoryOptions.DATABASE, settings.database())
                .option(ConnectionFactoryOptions.USER, settings.username())
                .option(ConnectionFactoryOptions.PASSWORD, settings.password())
                .build();

        return ConnectionFactories.get(options);
    }
}
```

`DatabaseSettings` ở đây là cấu hình ứng dụng do dự án định nghĩa, có thể được bind từ biến môi trường hoặc `@ConfigurationProperties`. Đoạn mã minh họa cách truyền host, port, database và credentials qua R2DBC SPI; không phải cấu hình hoàn chỉnh cho mọi môi trường production. Tùy chọn bổ sung như TLS và pool phải được cấu hình theo driver và yêu cầu vận hành.

Khi tự khai báo bean `ConnectionFactory`, cấu hình tự động của Spring Boot có thể lùi lại vì ứng dụng đã cung cấp bean tương ứng. Khi đó, cần chủ động bảo đảm cấu hình pool, transaction manager và các thành phần liên quan phù hợp. Tránh vừa tự tạo một `ConnectionFactory` vừa mong Boot sử dụng một URL khác mà không hiểu rõ thứ tự cấu hình.

## 13. Kiểm tra ứng dụng có kết nối đúng database hay không

Sau khi khai báo cấu hình, nên xác minh kết nối từ chính môi trường chạy ứng dụng. Việc ping database từ máy cá nhân không chứng minh container hoặc Pod ứng dụng có cùng khả năng truy cập mạng.

Có thể kiểm tra đơn giản bằng `DatabaseClient`:

```java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

public Mono<Integer> checkDatabase(DatabaseClient databaseClient) {
    return databaseClient.sql("SELECT 1 AS result")
            .map((row, metadata) -> row.get("result", Integer.class))
            .one();
}
```

Khi publisher phát ra `1`, câu truy vấn thử đã thực thi và nhận được kết quả. Hãy subscribe qua một endpoint kiểm tra sức khỏe, health indicator hoặc bài integration test phù hợp. Không gọi `block()` trên event loop chỉ để kiểm tra kết nối.

Một phép thử sâu hơn nên xác minh đúng database và user, ví dụ truy vấn metadata phù hợp với hệ quản trị đang dùng. `SELECT 1` chỉ chứng minh kết nối và truy vấn đơn giản hoạt động; nó không chứng minh user có đủ quyền trên mọi bảng, schema hoặc thao tác nghiệp vụ.

## 14. Chẩn đoán lỗi kết nối thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `Connection refused` | Không có dịch vụ lắng nghe ở host/port đó, database chưa sẵn sàng hoặc firewall từ chối | Kiểm tra host, port, trạng thái database, port mapping và network policy |
| `UnknownHostException` hoặc lỗi phân giải DNS | Hostname sai hoặc môi trường ứng dụng không phân giải được DNS | Kiểm tra tên service, DNS nội bộ, namespace và cấu hình mạng |
| Lỗi authentication / password authentication failed | Username hoặc password sai, tài khoản bị khóa hoặc phương thức xác thực không phù hợp | Kiểm tra secret, profile, tài khoản và chính sách xác thực trên database |
| Database does not exist | Tên database trong URL sai hoặc database chưa được tạo | Kiểm tra phần path của URL và trạng thái khởi tạo database |
| Không tìm thấy driver hoặc không tìm được `ConnectionFactory` | Thiếu dependency driver R2DBC hoặc URL dùng sai scheme | Kiểm tra dependency runtime, BOM và scheme `r2dbc:` |
| Lỗi timeout khi lấy connection | Pool hết kết nối, database quá tải, truy vấn giữ kết nối lâu hoặc mạng chậm | Kiểm tra metric pool, truy vấn, thời gian chờ, số instance và giới hạn database |
| Lỗi SSL/TLS hoặc chứng chỉ | Chế độ TLS, CA, hostname chứng chỉ hoặc thuộc tính driver không khớp | Kiểm tra cấu hình TLS theo đúng driver và chứng chỉ máy chủ |
| Kết nối được nhưng truy vấn bị từ chối | User chưa có quyền trên schema, bảng hoặc thao tác cụ thể | Kiểm tra quyền database và schema của tài khoản ứng dụng |

Quy trình kiểm tra thực tế nên đi từ ngoài vào trong:

1. Xác nhận ứng dụng đang chạy với profile nào và lấy đúng giá trị cấu hình cuối cùng.
2. Kiểm tra hostname có phân giải được từ container hoặc Pod ứng dụng.
3. Kiểm tra có thể mở kết nối TCP tới đúng host và port từ cùng môi trường chạy.
4. Xác nhận database đã khởi động, lắng nghe trên interface phù hợp và cho phép nguồn mạng của ứng dụng truy cập.
5. Kiểm tra tên database, username, password và quyền của tài khoản.
6. Xác nhận driver R2DBC đúng hệ quản trị, URL đúng scheme và các thuộc tính TLS phù hợp.
7. Nếu lỗi xuất hiện khi tải tăng, kiểm tra connection pool, thời gian truy vấn và giới hạn kết nối của database.

Không đưa password, URL chứa credentials hoặc secret vào log khi điều tra. Log nên ghi host, port, database và mã lỗi ở mức đủ để chẩn đoán, đồng thời che thông tin xác thực.

## 15. Checklist cấu hình trước khi chạy ứng dụng

- [ ] Đã chọn đúng driver R2DBC cho hệ quản trị cơ sở dữ liệu.
- [ ] URL dùng scheme `r2dbc:` và đúng protocol của driver.
- [ ] Host là địa chỉ có thể truy cập từ môi trường thực sự chạy ứng dụng.
- [ ] Port khớp với cổng database đang lắng nghe.
- [ ] Tên database đã tồn tại và được khai báo đúng trong URL.
- [ ] Username và password được cung cấp từ nguồn cấu hình phù hợp.
- [ ] Tài khoản có quyền tối thiểu cần thiết cho ứng dụng.
- [ ] Profile đang hoạt động đúng với môi trường triển khai.
- [ ] TLS và các thuộc tính riêng của driver đã được cấu hình khi môi trường yêu cầu.
- [ ] Connection pool có dependency và giới hạn phù hợp nếu được bật.
- [ ] Ứng dụng có thể thực hiện truy vấn kiểm tra từ chính môi trường triển khai.
- [ ] Log và repository không chứa password hoặc secret thật.

## 16. Nguyên tắc thực hành

- Dùng `spring.r2dbc.url`, `spring.r2dbc.username` và `spring.r2dbc.password` để cấu hình kết nối trong Spring Boot.
- Đặt host, port và tên database trong URL theo cú pháp của driver; không dùng URL JDBC cho R2DBC.
- Đưa credentials vào biến môi trường hoặc secret manager, không commit mật khẩu thật.
- Xác định host dựa trên vị trí tiến trình ứng dụng; `localhost` trong container không phải database ở container khác.
- Dùng đúng dependency driver R2DBC và phiên bản tương thích với Spring Boot.
- Tách cấu hình theo profile hoặc externalized configuration để tránh kết nối nhầm môi trường.
- Cấu hình pool theo giới hạn kết nối của database và tổng số instance ứng dụng.
- Cấu hình TLS theo tài liệu của driver và xác minh chứng chỉ máy chủ.
- Kiểm tra kết nối từ đúng môi trường chạy ứng dụng và xác minh cả quyền truy cập cần thiết.
- Không log thông tin xác thực hoặc đưa secret vào mã nguồn.

## 17. Kết luận

Cấu hình kết nối R2DBC xoay quanh bốn thông tin: host xác định máy chủ, port xác định cổng dịch vụ, database xác định nơi dữ liệu được truy cập và credentials xác định danh tính cùng quyền của ứng dụng. Spring Boot cho phép khai báo các giá trị này trong `spring.r2dbc`, sau đó tạo `ConnectionFactory` để Spring Data R2DBC, repository và `R2dbcEntityTemplate` sử dụng.

Kết nối ổn định còn phụ thuộc vào driver đúng hệ quản trị, DNS và mạng của môi trường triển khai, quản lý secret, TLS và connection pool. Khi cấu hình được tách khỏi mã nguồn, kiểm tra từ đúng môi trường chạy và giới hạn quyền của tài khoản hợp lý, ứng dụng sẽ dễ triển khai giữa các môi trường và dễ chẩn đoán khi kết nối gặp sự cố.
