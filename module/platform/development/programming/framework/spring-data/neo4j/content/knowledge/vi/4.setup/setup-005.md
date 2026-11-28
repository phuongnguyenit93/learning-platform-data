# Cấu hình spring.neo4j và spring.data.neo4j.database

Để ứng dụng Spring Data Neo4j kết nối đúng máy chủ và làm việc với đúng cơ sở dữ liệu, cần cấu hình hai nhóm thuộc tính chính. `spring.neo4j` mô tả kết nối Bolt, thông tin xác thực và các tùy chọn của Neo4j Java Driver. `spring.data.neo4j.database` chọn database mà Spring Data Neo4j sử dụng khi thực hiện thao tác dữ liệu.

Hai nhóm thuộc tính có vai trò khác nhau: URI cho biết ứng dụng kết nối đến máy chủ nào và bằng giao thức nào, còn tên database cho biết ứng dụng thao tác trên database nào bên trong máy chủ đó. Cấu hình rõ cả hai giúp môi trường local, test và production hoạt động nhất quán.

## 1. Chuẩn bị dependency và thông tin kết nối

Ứng dụng Spring Boot thường sử dụng starter `spring-boot-starter-data-neo4j`. Starter này đưa Spring Data Neo4j và các thành phần tích hợp cần thiết vào ứng dụng, đồng thời cho phép Spring Boot tự cấu hình Neo4j Java Driver dựa trên các thuộc tính `spring.neo4j`.

Ví dụ khai báo dependency Gradle khi dự án đã dùng Spring Boot dependency management:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-neo4j")
}
```

Trước khi cấu hình, cần biết các thông tin sau:

- **URI kết nối:** hostname, port và scheme mà Neo4j Driver sử dụng.
- **Username:** tài khoản Neo4j của ứng dụng.
- **Password:** mật khẩu tương ứng.
- **Database:** tên database mà ứng dụng sẽ truy cập, ví dụ `neo4j`.
- **TLS và định tuyến:** môi trường có yêu cầu mã hóa kết nối hoặc dùng cluster hay không.

Với Neo4j cài trên máy local, Bolt thường lắng nghe ở cổng `7687`. Neo4j Browser mặc định thường truy cập qua HTTP ở cổng `7474`; đây là giao diện quản trị, không phải URI Bolt để cấu hình Neo4j Driver.

## 2. Cấu hình cơ bản trong application.yml

Hai nhóm thuộc tính quan trọng có thể đặt trong `src/main/resources/application.yml`:

```yaml
spring:
  neo4j:
    uri: ${NEO4J_URI:bolt://localhost:7687}
    authentication:
      username: ${NEO4J_USERNAME:neo4j}
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: ${NEO4J_DATABASE:neo4j}
```

Ý nghĩa từng thuộc tính:

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| `spring.neo4j.uri` | Địa chỉ kết nối mà Neo4j Driver sử dụng | `bolt://localhost:7687` |
| `spring.neo4j.authentication.username` | Tên tài khoản xác thực với Neo4j | `neo4j` |
| `spring.neo4j.authentication.password` | Mật khẩu tài khoản | Lấy từ biến môi trường `NEO4J_PASSWORD` |
| `spring.data.neo4j.database` | Database đích cho hoạt động của Spring Data Neo4j | `neo4j` |

Cú pháp `${TEN_BIEN:gia_tri_mac_dinh}` cho phép Spring lấy giá trị từ biến môi trường và dùng giá trị sau dấu `:` nếu biến chưa được đặt. Ví dụ, nếu không đặt `NEO4J_URI`, ứng dụng dùng `bolt://localhost:7687`. Trong cấu hình trên, mật khẩu không có giá trị mặc định; cần cung cấp `NEO4J_PASSWORD` khi chạy ứng dụng.

Không ghi mật khẩu thật vào file cấu hình được commit lên Git. Dùng biến môi trường, secret manager hoặc cơ chế cấp secret của nền tảng triển khai. Giá trị `neo4j` và địa chỉ localhost trong ví dụ chỉ phù hợp cho môi trường phát triển có kiểm soát.

## 3. Phân biệt URI kết nối và tên database

`spring.neo4j.uri` và `spring.data.neo4j.database` không thay thế cho nhau.

- URI định tuyến kết nối đến một máy chủ hoặc cụm Neo4j. Nó chứa scheme, hostname và có thể có port.
- Database là tên database logic ở bên trong máy chủ Neo4j. Một máy chủ có thể quản lý nhiều database, tùy phiên bản và edition được triển khai.

Ví dụ, ứng dụng có thể kết nối đến `bolt://db.internal:7687` nhưng chọn database `orders`. Khi đó, URI vẫn giữ nguyên nếu chỉ đổi database đích sang `catalog`; chỉ thuộc tính `spring.data.neo4j.database` thay đổi.

Nếu không chỉ định database, driver hoặc cấu hình tích hợp có thể sử dụng database mặc định của máy chủ hoặc tài khoản. Không nên phụ thuộc vào mặc định khi ứng dụng có nhiều database hoặc có nhiều môi trường. Hãy cấu hình tên database tường minh và bảo đảm database đó tồn tại, đồng thời user ứng dụng có quyền truy cập.

Một số ví dụ tên database thường gặp:

```yaml
spring:
  data:
    neo4j:
      database: orders
```

Hoặc truyền qua biến môi trường:

```text
NEO4J_DATABASE=orders
```

Tên database cần tuân theo quy tắc đặt tên của Neo4j. Với môi trường triển khai thực tế, nên thống nhất tên database theo vai trò và môi trường, tránh dùng cùng một database cho các ứng dụng không liên quan nếu không có chủ đích chia sẻ dữ liệu.

## 4. Chọn scheme URI phù hợp

Neo4j Java Driver hỗ trợ các scheme kết nối phổ biến sau:

| Scheme | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| `bolt://` | Kết nối Bolt trực tiếp, không bật TLS theo scheme | Máy local hoặc mạng phát triển được bảo vệ |
| `neo4j://` | Kết nối Bolt có hỗ trợ routing | Cụm Neo4j hoặc môi trường cần định tuyến |
| `bolt+s://` | Bolt trực tiếp qua TLS với xác minh chứng chỉ | Kết nối trực tiếp được mã hóa |
| `neo4j+s://` | Kết nối routing qua TLS với xác minh chứng chỉ | Cụm hoặc dịch vụ Neo4j yêu cầu TLS |

Ví dụ cấu hình cho một dịch vụ Neo4j có TLS:

```yaml
spring:
  neo4j:
    uri: neo4j+s://graph.example.com
    authentication:
      username: ${NEO4J_USERNAME}
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: ${NEO4J_DATABASE:orders}
```

Scheme `+s` yêu cầu kết nối TLS và xác minh chứng chỉ theo trust configuration của môi trường. Máy chủ cần cung cấp chứng chỉ hợp lệ và hostname phải khớp. Không hạ mức xác minh chứng chỉ chỉ để làm biến mất lỗi kết nối trong production. Nếu hệ thống dùng chứng chỉ nội bộ, hãy cấu hình trust store hoặc chứng chỉ CA theo hướng dẫn triển khai của tổ chức.

Không đưa `http://localhost:7474` vào `spring.neo4j.uri`. Driver dùng giao thức Bolt, không dùng địa chỉ trang Neo4j Browser hoặc HTTP endpoint quản trị.

## 5. Tách cấu hình theo môi trường

Mỗi môi trường có thể có URI và database khác nhau. Spring Boot hỗ trợ profile để tách cấu hình local, test và production.

Ví dụ `application-local.yml`:

```yaml
spring:
  neo4j:
    uri: bolt://localhost:7687
    authentication:
      username: neo4j
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: neo4j
```

Ví dụ `application-prod.yml`:

```yaml
spring:
  neo4j:
    uri: ${NEO4J_URI}
    authentication:
      username: ${NEO4J_USERNAME}
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: ${NEO4J_DATABASE}
```

Kích hoạt profile bằng biến môi trường `SPRING_PROFILES_ACTIVE=local` hoặc `SPRING_PROFILES_ACTIVE=prod`. Profile chỉ chọn tập cấu hình tương ứng; các biến môi trường vẫn cần được cung cấp nếu file cấu hình tham chiếu đến chúng.

Spring Boot cũng hỗ trợ đặt trực tiếp các thuộc tính bằng biến môi trường theo quy tắc relaxed binding. Những tên biến thường dùng gồm:

| Property | Environment variable |
|---|---|
| `spring.neo4j.uri` | `SPRING_NEO4J_URI` |
| `spring.neo4j.authentication.username` | `SPRING_NEO4J_AUTHENTICATION_USERNAME` |
| `spring.neo4j.authentication.password` | `SPRING_NEO4J_AUTHENTICATION_PASSWORD` |
| `spring.data.neo4j.database` | `SPRING_DATA_NEO4J_DATABASE` |

Khi dùng biến môi trường theo tên property trực tiếp, hãy bảo đảm không đồng thời đặt nhiều nguồn cấu hình có giá trị khác nhau mà khó xác định nguồn nào đang được áp dụng. Có thể kiểm tra cấu hình hiệu lực qua log khởi động phù hợp hoặc Spring Boot Actuator trong môi trường phát triển được bảo vệ; tránh công khai endpoint chứa thông tin nhạy cảm.

## 6. Cấu hình connection pool ở mức cần thiết

Neo4j Java Driver quản lý pool các kết nối để tái sử dụng session và connection hiệu quả. Spring Boot cung cấp một số thuộc tính dưới `spring.neo4j.pool`, ví dụ giới hạn số connection và thời gian chờ lấy connection:

```yaml
spring:
  neo4j:
    pool:
      max-connection-pool-size: 40
      connection-acquisition-timeout: 30s
```

Các con số trên chỉ là ví dụ cấu hình, không phải giá trị tối ưu cho mọi hệ thống. Kích thước pool cần cân nhắc số instance ứng dụng, số request đồng thời, giới hạn kết nối của Neo4j và thời gian truy vấn. Tăng pool quá lớn có thể làm database chịu thêm tải mà không cải thiện throughput.

Hãy đo số connection đang sử dụng, thời gian chờ lấy connection và latency truy vấn trước khi điều chỉnh. Kiểm tra danh sách thuộc tính được hỗ trợ theo phiên bản Spring Boot mà dự án sử dụng, vì các tùy chọn và giá trị mặc định có thể thay đổi giữa các phiên bản.

## 7. Spring Boot tự cấu hình Driver và repository

Khi starter được khai báo và các thuộc tính kết nối hợp lệ, Spring Boot có thể tự cấu hình `org.neo4j.driver.Driver`, tích hợp Spring Data Neo4j và repository. Ứng dụng thông thường không cần tự tạo Driver chỉ để đổi URI, username, password hoặc database.

Ví dụ repository:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
    Optional<Person> findByEmail(String email);
}
```

Repository sử dụng cấu hình kết nối do Spring quản lý. Database được chọn bởi `spring.data.neo4j.database`, còn entity mapping và truy vấn được xử lý bởi Spring Data Neo4j.

Chỉ tạo `Driver` bean tùy chỉnh khi cần thiết lập đặc biệt mà auto-configuration không đáp ứng. Khi tự cấu hình Driver, cần chịu trách nhiệm về cấu hình xác thực, lifecycle và đóng Driver khi ứng dụng dừng. Cũng cần kiểm tra tương tác với các bean tự cấu hình khác để tránh vô tình làm mất cấu hình database hoặc transaction manager.

## 8. Kiểm tra kết nối và database đã chọn

Kiểm tra kết nối nên được thực hiện từ chính ứng dụng Spring Boot vì mở được Neo4j Browser chưa chứng minh ứng dụng dùng đúng URI, thông tin xác thực hoặc database.

Có thể dùng Neo4j Browser để kiểm tra thông tin phía máy chủ:

```cypher
SHOW DATABASES;
```

Lệnh này giúp xác nhận database cần dùng có tồn tại và đang ở trạng thái phù hợp. Tài khoản thực hiện cần có quyền xem thông tin database. Tiếp theo, chạy một truy vấn đơn giản qua repository hoặc `Neo4jClient` của ứng dụng để xác nhận cấu hình thực tế.

Ví dụ dùng `Neo4jClient` để kiểm tra truy vấn đọc:

```java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Component;

@Component
public class Neo4jConnectionCheck {

    private final Neo4jClient neo4jClient;

    public Neo4jConnectionCheck(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public long check() {
        return neo4jClient.query("RETURN 1 AS value")
                .fetchAs(Long.class)
                .mappedBy((typeSystem, record) -> record.get("value").asLong())
                .one()
                .orElseThrow();
    }
}
```

Nếu phương thức trả về `1`, ứng dụng đã thực hiện được truy vấn qua cấu hình Neo4j hiện tại. Để xác nhận đúng database, có thể kiểm tra tên database hiện hành bằng truy vấn Cypher phù hợp với phiên bản Neo4j và quyền của tài khoản, hoặc kiểm tra một dữ liệu kiểm thử chỉ có trong database mục tiêu.

## 9. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Connection refused | Sai host/port, Neo4j chưa chạy hoặc port chưa được publish | Kiểm tra `spring.neo4j.uri`, trạng thái máy chủ và cổng Bolt `7687` |
| Authentication failure | Username hoặc password sai, secret chưa được truyền | Kiểm tra biến môi trường và tài khoản Neo4j; không ghi password ra log |
| Database not found | `spring.data.neo4j.database` trỏ đến database không tồn tại | Kiểm tra tên bằng `SHOW DATABASES` và sửa cấu hình |
| Not authorized | Tài khoản đăng nhập được nhưng thiếu quyền trên database | Cấp quyền tối thiểu cần thiết cho database mục tiêu |
| TLS handshake hoặc certificate error | Scheme TLS, CA hoặc hostname không khớp | Kiểm tra `+s`, chứng chỉ máy chủ, hostname và trust store |
| Ứng dụng kết nối được nhưng đọc dữ liệu rỗng | Đang chọn nhầm database hoặc dữ liệu nằm ở môi trường khác | Xác nhận database được chọn và kiểm tra dữ liệu tại đúng database |
| Request chờ lâu trước khi chạy query | Pool hết connection hoặc truy vấn giữ connection lâu | Theo dõi pool, thời gian truy vấn và mức đồng thời trước khi tăng giới hạn |

Khi xử lý lỗi, hãy đọc nguyên nhân gốc trong exception và log của Neo4j Driver. Tránh đưa password, token hoặc thông tin kết nối nhạy cảm vào log, ảnh chụp màn hình hay báo cáo lỗi.

## 10. Bài tập thực hành

Thực hiện các bước sau trong môi trường Neo4j phát triển:

1. Khởi động Neo4j và xác nhận Bolt đang lắng nghe tại `localhost:7687`.
2. Tạo hoặc xác nhận database `neo4j` tồn tại và tài khoản ứng dụng có quyền truy cập.
3. Đặt `NEO4J_PASSWORD` trong môi trường chạy ứng dụng.
4. Cấu hình `spring.neo4j.uri`, `spring.neo4j.authentication.username`, `spring.neo4j.authentication.password` và `spring.data.neo4j.database` trong `application.yml`.
5. Khởi động Spring Boot và gọi một repository method hoặc `Neo4jClient` để chạy `RETURN 1 AS value`.
6. Thay `NEO4J_DATABASE` thành một database khác đã được tạo, khởi động lại ứng dụng và xác nhận dữ liệu được đọc từ database mới.
7. Thử cấu hình sai port, password và database trong môi trường phát triển để nhận biết các nhóm lỗi tương ứng.

Sau bài tập, cần giải thích được vì sao đổi `spring.neo4j.uri` có thể chuyển ứng dụng sang máy chủ khác, trong khi đổi `spring.data.neo4j.database` chỉ chuyển database đích trên máy chủ được kết nối. Đồng thời, nêu được cách truyền secret an toàn và cách xác nhận ứng dụng đang dùng đúng database.

## Kết luận

`spring.neo4j` cấu hình kết nối Neo4j Driver, gồm URI và thông tin xác thực; `spring.data.neo4j.database` chọn database cho Spring Data Neo4j. Hãy cấu hình hai phần này tường minh, tách giá trị theo profile hoặc biến môi trường, bảo vệ thông tin xác thực và chọn scheme URI phù hợp với TLS cũng như topology của hệ thống. Kiểm tra kết nối từ chính ứng dụng giúp phát hiện sớm lỗi host, quyền truy cập và database đích trước khi phát triển các repository và truy vấn Cypher phức tạp.
