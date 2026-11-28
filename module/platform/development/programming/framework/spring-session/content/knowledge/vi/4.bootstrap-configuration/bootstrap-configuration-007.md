# Thuộc tính timeout, repository và kết nối theo phiên bản Spring Boot

Spring Session cho phép ứng dụng Spring lưu session trong một kho dùng chung như Redis hoặc JDBC. Khi dùng Spring Boot, phần lớn cấu hình được khai báo trong `application.yml` hoặc `application.properties`; Boot đọc các thuộc tính, tạo kết nối đến kho dữ liệu và tự cấu hình repository cùng filter quản lý session cho ứng dụng Servlet.

Điểm cần chú ý là tên dependency và một số tiền tố thuộc tính thay đổi theo thế hệ Spring Boot. Một cấu hình đúng ở Boot 2.x có thể không còn đúng ở Boot 3.x hoặc Boot 4.x. Bài học này tập trung vào ba nhóm thiết lập: thời hạn không hoạt động của session (`timeout`), lựa chọn repository và cấu hình kết nối tới Redis hoặc cơ sở dữ liệu.

## 1. Phân biệt ba nhóm timeout

Trong một ứng dụng web, từ “timeout” có thể chỉ nhiều khoảng thời gian khác nhau. Cần xác định đúng loại trước khi thay đổi cấu hình.

| Loại thời gian | Ví dụ thuộc tính | Điều khiển điều gì? |
|---|---|---|
| Session timeout | `spring.session.timeout` | Khoảng thời gian session không được truy cập trước khi hết hạn |
| Cookie max-age | `DefaultCookieSerializer.cookieMaxAge` trong Spring Session | Thời gian trình duyệt giữ cookie session; giá trị mặc định `-1` thường có nghĩa cookie theo phiên trình duyệt |
| Timeout kết nối kho dữ liệu | `spring.data.redis.connect-timeout`, `spring.data.redis.timeout` | Thời gian chờ khi thiết lập kết nối hoặc đọc phản hồi từ Redis |

Session timeout không phải thời gian tối đa của một request HTTP và cũng không phải thời gian chờ kết nối Redis. Ví dụ, đặt session timeout là `30m` có nghĩa phiên có thể hết hạn sau 30 phút không hoạt động; nó không buộc một request đang chạy phải kết thúc trong 30 phút.

Spring Session ghi cookie thông qua `CookieSerializer` (mặc định là `DefaultCookieSerializer`). Vì vậy, khi cần điều chỉnh cookie max-age cho Spring Session, hãy cấu hình cookie serializer phù hợp. Một số thuộc tính cookie của Spring Boot, chẳng hạn `server.servlet.session.cookie.same-site`, cũng được áp dụng cho `SessionRepository` Servlet được auto-configure; không nên mặc định mọi thiết lập cookie của servlet container đều được chuyển sang Spring Session theo cùng một cách.

Với ứng dụng Servlet sử dụng Spring Session auto-configuration, có thể đặt:

```yaml
spring:
  session:
    timeout: 30m
```

Nếu không khai báo `spring.session.timeout`, Spring Boot dùng giá trị `server.servlet.session.timeout` làm giá trị dự phòng cho ứng dụng Servlet. Vì vậy, cấu hình dưới đây cũng có thể xác định thời hạn session khi không có thuộc tính Spring Session riêng:

```yaml
server:
  servlet:
    session:
      timeout: 30m
```

Khi cả hai thuộc tính cùng có giá trị, `spring.session.timeout` là giá trị dành riêng cho Spring Session và được ưu tiên trong auto-configuration. Nên chọn một nơi làm nguồn cấu hình chính để tránh người vận hành phải suy luận giữa hai giá trị khác nhau. Nếu tự bật cấu hình bằng `@EnableRedisHttpSession` hoặc `@EnableJdbcHttpSession`, Boot auto-configuration sẽ lùi lại; khi đó cần đặt thời hạn qua thuộc tính của annotation hoặc cơ chế cấu hình session tương ứng.

Các giá trị kiểu `Duration` có thể dùng hậu tố như `s`, `m`, `h`, `d`; ví dụ `900s`, `15m`, `2h`. Nếu không ghi hậu tố ở những thuộc tính quy định đơn vị mặc định là giây, giá trị số sẽ được hiểu là giây. Ghi rõ đơn vị giúp cấu hình dễ đọc và giảm nhầm lẫn khi chuyển môi trường.

## 2. Repository được chọn như thế nào?

Repository là thành phần Spring Session dùng để tạo, tìm, lưu và xóa dữ liệu phiên. Trong ứng dụng Servlet, Spring Session thường cung cấp `SessionRepositoryFilter`, nhờ đó controller vẫn làm việc với `HttpSession` trong khi dữ liệu được lưu trong Redis hoặc JDBC.

Spring Boot có thể tự cấu hình repository dựa trên dependency có trong classpath. Vì vậy, cấu hình gồm hai phần:

1. Thêm module hoặc starter Spring Session phù hợp với kho lưu trữ.
2. Cung cấp thông tin kết nối cho Redis hoặc `DataSource`.

Nếu chỉ có một implementation Spring Session phù hợp trên classpath, Boot thường nhận diện implementation đó. Nếu ứng dụng đưa nhiều implementation vào cùng lúc, quy tắc chọn repository phụ thuộc phiên bản Boot. Với Boot 3.4/3.5, tài liệu mô tả thứ tự auto-detection cho Servlet là Redis, JDBC, Hazelcast rồi MongoDB. Không nên thêm nhiều module chỉ vì nghĩ Boot sẽ tự hiểu ý định của ứng dụng; hãy giữ dependency cần thiết hoặc cấu hình rõ repository mong muốn.

### 2.1. Các thế hệ Spring Boot

| Thế hệ | Dependency Spring Session thường dùng | Thuộc tính kết nối Redis | Thuộc tính riêng cho Redis Session |
|---|---|---|---|
| Spring Boot 2.x | `org.springframework.session:spring-session-data-redis` hoặc `spring-session-jdbc` | `spring.redis.*` | `spring.session.redis.*` |
| Spring Boot 3.x | `org.springframework.session:spring-session-data-redis` hoặc `spring-session-jdbc` | `spring.data.redis.*` | `spring.session.redis.*` |
| Spring Boot 4.x | Starter Boot `spring-boot-starter-session-data-redis` hoặc `spring-boot-starter-session-jdbc` | `spring.data.redis.*` | `spring.session.data.redis.*` |

Một thay đổi dễ gây lỗi khi nâng cấp là tiền tố Redis Session ở Boot 4.x: cấu hình `spring.session.redis.*` của Boot 2.x/3.x được chuyển sang `spring.session.data.redis.*` trong tài liệu Boot 4.x. Cấu hình kết nối Redis vẫn thuộc nhóm `spring.data.redis.*` ở Boot 3.x và 4.x; với Boot 2.x thường là `spring.redis.*`.

Boot 2.x có thuộc tính `spring.session.store-type` để chọn `redis`, `jdbc` hoặc `none`, đặc biệt hữu ích khi có nhiều store module trên classpath. Trong Boot 3.x, tài liệu cấu hình chuyển sang auto-detection và mô tả thứ tự ưu tiên theo implementation; không sao chép máy móc thuộc tính `store-type` từ dự án Boot 2.x. Boot 4.x dùng các starter Spring Session chuyên biệt và auto-configuration tương ứng. Với mọi phiên bản, hãy kiểm tra đúng tài liệu theo minor version đang chạy thay vì dựa vào một ví dụ cũ.

## 3. Chọn dependency phù hợp

### 3.1. Redis

Với Spring Boot 2.x và 3.x, dependency Spring Session Redis thường là:

```xml
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
</dependency>
```

Hoặc với Gradle:

```kotlin
implementation("org.springframework.session:spring-session-data-redis")
```

Với Spring Boot 4.x, dùng starter do Boot cung cấp:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
```

```kotlin
implementation("org.springframework.boot:spring-boot-starter-session-data-redis")
```

### 3.2. JDBC

Với Spring Boot 2.x và 3.x, dùng module:

```xml
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-jdbc</artifactId>
</dependency>
```

Với Spring Boot 4.x, dùng starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-jdbc</artifactId>
</dependency>
```

JDBC cũng cần driver của cơ sở dữ liệu mà ứng dụng sử dụng và cấu hình `DataSource`. Không nên khai báo phiên bản Spring Session tùy ý bên cạnh phiên bản Spring Boot. Hãy để Spring Boot dependency management hoặc BOM quản lý các phiên bản tương thích, trừ khi dự án có quy trình quản lý dependency riêng đã được kiểm chứng.

## 4. Cấu hình Redis: kết nối và repository là hai phần riêng

Spring Boot tạo `RedisConnectionFactory` từ cấu hình Redis nếu các dependency cần thiết có mặt. Spring Session sử dụng connection factory đó để đọc và ghi session. Các thuộc tính host, port, thông tin xác thực và timeout kết nối nằm trong namespace của Spring Data Redis; namespace riêng của Spring Session dùng để cấu hình cách repository lưu session.

### 4.1. Ví dụ cho Spring Boot 3.x

```yaml
spring:
  session:
    timeout: 30m
    redis:
      namespace: shop:session
      flush-mode: on-save
      save-mode: on-set-attribute

  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME:}
      password: ${REDIS_PASSWORD:}
      connect-timeout: 2s
      timeout: 2s
```

Trong ví dụ này:

- `spring.session.timeout` đặt thời gian không hoạt động của session.
- `spring.session.redis.namespace` tạo tiền tố riêng cho key session, giúp phân tách dữ liệu giữa các ứng dụng dùng chung Redis.
- `flush-mode` quyết định thời điểm thay đổi session được ghi vào kho; `on-save` thường gom thay đổi để ghi khi session được lưu.
- `save-mode` quyết định cách theo dõi thay đổi attributes; `on-set-attribute` theo dõi các lần đặt attribute.
- `spring.data.redis.*` xác định endpoint và timeout kết nối Redis.

Nếu đang dùng Boot 2.x, nhóm thuộc tính kết nối thường có dạng `spring.redis.host`, `spring.redis.port`, `spring.redis.password`; các thuộc tính Spring Session vẫn nằm dưới `spring.session.redis.*`. Không đổi riêng tên một thuộc tính mà không kiểm tra toàn bộ namespace của phiên bản.

### 4.2. Ví dụ cho Spring Boot 4.x

Boot 4.x sử dụng starter mới và namespace Redis Session có thêm nhánh `data`:

```yaml
spring:
  session:
    timeout: 30m
    data:
      redis:
        namespace: shop:session
        flush-mode: on-save
        save-mode: on-set-attribute

  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME:}
      password: ${REDIS_PASSWORD:}
      connect-timeout: 2s
      timeout: 2s
```

Hai nhánh `spring.session.data.redis` và `spring.data.redis` phục vụ hai mục đích khác nhau. Nhánh thứ nhất điều khiển repository session; nhánh thứ hai cấu hình client kết nối đến Redis. Không chuyển `namespace` hoặc `flush-mode` sang `spring.data.redis`, vì đó không phải thuộc tính kết nối.

### 4.3. Namespace và kết nối nhiều instance

Mọi instance của cùng một ứng dụng phải dùng namespace tương thích để tìm cùng tập session. Nếu ứng dụng A dùng `shop:session` còn ứng dụng B dùng `other:session`, hai ứng dụng có thể cùng kết nối một Redis nhưng không tìm thấy dữ liệu của nhau. Namespace cũng hữu ích khi nhiều ứng dụng chia sẻ một Redis database.

Các instance cần thống nhất cấu hình serialization và cách diễn giải attributes. Nếu triển khai rolling update với nhiều phiên bản ứng dụng cùng chạy, thay đổi class lưu trong session hoặc thay serializer có thể khiến instance mới không đọc được session cũ. Nên giữ kiểu dữ liệu session đơn giản, tương thích qua các phiên bản và có kế hoạch chuyển đổi nếu cấu trúc attributes thay đổi.

Không ghi mật khẩu Redis trực tiếp vào file cấu hình được commit. Dùng biến môi trường, secret manager hoặc cơ chế quản lý bí mật của nền tảng. Trong môi trường thật, cấu hình TLS, username/password, network policy và giới hạn truy cập Redis phù hợp với hạ tầng.

## 5. Cấu hình JDBC: DataSource, schema và timeout

Với JDBC, Spring Session sử dụng `DataSource` do Spring Boot cung cấp. `spring.datasource.*` là cấu hình kết nối database của ứng dụng; `spring.session.jdbc.*` là cấu hình riêng cho repository session.

```yaml
spring:
  session:
    timeout: 30m
    jdbc:
      initialize-schema: never
      table-name: APP_SESSION
      cleanup-cron: "0 * * * * *"

  datasource:
    url: ${SESSION_DB_URL:jdbc:postgresql://localhost:5432/app}
    username: ${SESSION_DB_USERNAME:app}
    password: ${SESSION_DB_PASSWORD:}
```

Trong ví dụ này, ứng dụng dùng `DataSource` đã cấu hình để kết nối PostgreSQL. `table-name` tùy chỉnh bảng session; implementation JDBC cũng dùng bảng attributes có tên liên quan đến bảng session. `cleanup-cron` điều khiển lịch dọn các session hết hạn theo khả năng của implementation. `initialize-schema: never` phù hợp khi schema đã được tạo và quản lý bởi công cụ migration như Flyway hoặc Liquibase.

Khi phát triển với database nhúng, `initialize-schema: embedded` có thể giúp Boot tự khởi tạo schema. Với database ngoài, cần chủ động kiểm tra schema đúng với phiên bản Spring Session và dialect đang dùng. Có thể chọn `always` nếu chủ đích muốn Spring Session chạy script khởi tạo theo cấu hình, nhưng cần đánh giá cách script tương tác với schema đã tồn tại. Trong production, migration có kiểm soát thường dễ kiểm toán và dự đoán hơn.

Ví dụ trên không chứa thông tin kết nối thật. Khi dùng PostgreSQL, cần có JDBC driver tương ứng. Với nhiều `DataSource`, cần chỉ định đúng nguồn dữ liệu cho Spring Session theo cơ chế hỗ trợ của phiên bản Spring Session, ví dụ qualifier `@SpringSessionDataSource` khi dùng cấu hình JDBC thủ công. Nếu không chỉ định, repository thường sử dụng `DataSource` chính được Spring quản lý.

## 6. Tự cấu hình repository bằng annotation

Trong ứng dụng Spring Boot thông thường, dependency phù hợp cùng cấu hình properties là đủ. Boot tự đăng ký `SessionRepositoryFilter` cho Servlet và kết nối repository với `HttpSession`.

Khi cần kiểm soát cấu hình ở mức Spring Session, có thể bật annotation thủ công:

```java
@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1800)
class RedisSessionConfiguration {
}
```

Hoặc với JDBC:

```java
@Configuration
@EnableJdbcHttpSession(maxInactiveIntervalInSeconds = 1800)
class JdbcSessionConfiguration {
}
```

Các annotation trên dành cho ứng dụng Servlet. Với WebFlux dùng Redis, annotation tương ứng là `@EnableRedisWebSession`. Khi khai báo annotation để tự cấu hình, Spring Boot Spring Session auto-configuration sẽ back off. Khi đó cần đảm bảo các bean kết nối như `RedisConnectionFactory` hoặc `DataSource` đã tồn tại và cấu hình timeout, repository, filter phù hợp.

Tránh vừa bật auto-configuration bằng starter vừa tạo thêm một repository/filter thủ công mà không hiểu điều kiện back-off. Hai cấu hình cạnh tranh có thể dẫn đến nhiều bean cùng loại, filter đăng ký sai hoặc ứng dụng dùng nhầm kho session. Chọn một cách cấu hình cho mỗi ứng dụng và xác minh các bean được tạo khi khởi động.

## 7. Quan hệ giữa timeout của session và TTL trong kho dữ liệu

Spring Session biểu diễn thời hạn không hoạt động trên session. Repository chuyển thông tin đó thành chính sách lưu trữ phù hợp. Với Redis, key session có thể được đặt TTL; với JDBC, session có metadata hết hạn và các bản ghi cũ được dọn theo cơ chế cleanup.

Không nên chỉ dựa vào thời điểm bản ghi vật lý biến mất để xác định session còn hiệu lực. Một bản ghi JDBC đã hết hạn có thể vẫn tồn tại trước lần chạy cleanup tiếp theo; repository phải xem session đó là hết hạn khi đọc. Tương tự, cookie có thể còn được trình duyệt gửi sau khi dữ liệu session đã hết hạn. Khi đó ứng dụng cần xử lý request như một request không có session hợp lệ.

Hãy chọn timeout dựa trên thời gian người dùng có thể không hoạt động, mức nhạy cảm của dữ liệu và yêu cầu xác thực. Thời hạn quá ngắn làm người dùng phải đăng nhập lại thường xuyên; thời hạn quá dài làm tăng khoảng thời gian một session bị đánh cắp có thể còn hữu ích. Các luồng nhạy cảm có thể cần xác thực lại dù session vẫn còn hiệu lực.

## 8. Cấu hình theo môi trường

Không nên dùng một cấu hình kết nối cố định cho local, test, staging và production. Có thể giữ cấu trúc thuộc tính giống nhau nhưng lấy giá trị từ biến môi trường hoặc profile:

```yaml
spring:
  config:
    activate:
      on-profile: production
  session:
    timeout: 20m
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      password: ${REDIS_PASSWORD}
      connect-timeout: 2s
      timeout: 2s
```

Đây là ví dụ cấu hình cho Boot 3.x; nếu dùng Boot 4.x, phần repository Redis Session cần namespace `spring.session.data.redis` như phần trước. Trong triển khai thực tế, có thể đặt cấu hình chung trong `application.yml` và giá trị riêng từng môi trường trong file profile hoặc biến môi trường của nền tảng.

Các điểm cần đồng nhất giữa các instance:

- Cùng kho dữ liệu, database hoặc Redis cluster.
- Cùng namespace repository session.
- Cùng serializer và khả năng đọc attributes giữa các phiên bản đang chạy.
- Cùng chính sách timeout, cookie name và cách phân giải session ID.
- Cấu hình TLS, thông tin xác thực và quyền truy cập tương thích.

Nếu các instance dùng kho khác nhau hoặc namespace khác nhau, request tiếp theo có thể được định tuyến đến instance không tìm thấy session. Đây thường là lỗi cấu hình phân tán, không phải lỗi controller.

## 9. Kiểm tra cấu hình sau khi khởi động

Không nên kết luận cấu hình đúng chỉ vì ứng dụng khởi động thành công. Hãy xác minh đường đi đầy đủ của session:

1. Kiểm tra dependency tree để xác nhận chỉ có các module Spring Session mong muốn và phiên bản được Boot quản lý.
2. Xác nhận ứng dụng tạo được kết nối đến Redis hoặc database; kiểm tra log khởi động và health indicator phù hợp.
3. Tạo session qua một request và xác nhận response trả cookie session theo resolver đang dùng.
4. Gửi request tiếp theo kèm cookie và kiểm tra ứng dụng đọc lại được attribute đã lưu.
5. Thử qua hai instance khác nhau để xác nhận dữ liệu session dùng chung.
6. Đặt timeout ngắn trong môi trường kiểm thử, chờ quá hạn và xác nhận session không còn được khôi phục như một phiên hợp lệ.
7. Kiểm tra đăng xuất, xóa session và hành vi khi kho dữ liệu tạm thời không truy cập được.

Một số lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không có `SessionRepository` | Thiếu module/starter, nhầm stack Servlet và reactive, hoặc auto-configuration không thỏa điều kiện | Kiểm tra dependency, log điều kiện auto-config và loại ứng dụng web |
| Không kết nối được Redis | Sai host/port, thông tin xác thực, TLS, DNS hoặc network policy | Kiểm tra `spring.redis.*` ở Boot 2.x hay `spring.data.redis.*` ở Boot 3.x/4.x |
| Session không được chia sẻ giữa instance | Khác namespace, database, cluster hoặc serializer | So sánh cấu hình giữa các instance và kiểm thử cùng session ID |
| JDBC báo thiếu bảng hoặc cột | Schema chưa được tạo hoặc không khớp phiên bản | Kiểm tra migration, `initialize-schema`, `schema` và `table-name` |
| Session hết hạn sớm | Timeout đặt ở đơn vị sai hoặc cấu hình fallback khác dự kiến | Kiểm tra `spring.session.timeout`, `server.servlet.session.timeout` và đơn vị duration |
| Thay đổi attribute không được lưu | Cấu hình save/flush, cách thay đổi object mutable hoặc lỗi serialization | Kiểm tra `flush-mode`, `save-mode`, serializer và thời điểm hoàn tất request |

Khi nâng cấp Boot, cần kiểm tra cả dependency và cấu hình properties. Việc đổi tên package Servlet từ `javax.servlet` sang `jakarta.servlet` khi chuyển từ Boot 2.x sang Boot 3.x cũng ảnh hưởng đến filter, thư viện tích hợp và mã cấu hình tự viết. Hãy nâng cấp theo ma trận tương thích của Spring Boot, Spring Framework và Spring Session, sau đó kiểm thử session cũ nếu các instance mới phải đọc dữ liệu do phiên bản cũ ghi.

## 10. Quy trình chọn cấu hình

Khi bắt đầu một dự án hoặc nâng cấp phiên bản, có thể đi theo trình tự sau:

1. Xác định phiên bản Spring Boot và loại ứng dụng: Servlet hay WebFlux.
2. Chọn Redis hoặc JDBC theo yêu cầu vận hành và thêm đúng module/starter dành cho phiên bản đó.
3. Cấu hình kết nối bằng namespace Spring Data tương ứng: `spring.redis.*` với Boot 2.x, `spring.data.redis.*` với Boot 3.x/4.x, hoặc `spring.datasource.*` với JDBC.
4. Đặt `spring.session.timeout` và xác nhận giá trị fallback của Servlet nếu thuộc tính này chưa được khai báo.
5. Cấu hình repository: namespace/flush/save mode cho Redis; schema/table/cleanup cho JDBC.
6. Để Boot auto-configure khi dùng cấu hình chuẩn; chỉ bật annotation thủ công khi cần kiểm soát trực tiếp và hiểu rằng auto-configuration sẽ back off.
7. Kiểm thử tạo, đọc, cập nhật, hết hạn và chia sẻ session qua nhiều instance.

## 11. Tài liệu chính thức để đối chiếu phiên bản

Tên thuộc tính và starter là API cấu hình của từng dòng Spring Boot. Khi nâng cấp minor hoặc major version, hãy đối chiếu tài liệu tương ứng:

- [Spring Boot 2.7 — Spring Session](https://docs.spring.io/spring-boot/docs/2.7.18/reference/htmlsingle/#web.spring-session)
- [Spring Boot 3.5 — Spring Session](https://docs.spring.io/spring-boot/3.5/reference/web/spring-session.html)
- [Spring Boot 4.x — Spring Session](https://docs.spring.io/spring-boot/reference/web/spring-session.html)
- [Spring Session — Redis configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)

Timeout xác định thời gian session có thể không hoạt động; repository quyết định nơi và cách dữ liệu phiên được lưu; connection properties giúp từng instance truy cập kho dữ liệu đó. Khi ba lớp cấu hình này được đặt đúng theo phiên bản Spring Boot, các instance có thể chia sẻ session một cách nhất quán và ứng dụng có thể kiểm soát rõ thời hạn cũng như hành vi lưu trữ của phiên.
