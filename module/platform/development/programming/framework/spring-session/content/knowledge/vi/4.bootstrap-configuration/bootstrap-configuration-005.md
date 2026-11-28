# Cấu hình tường minh bằng `@Enable*HttpSession` hoặc `@Enable*WebSession`

Spring Session có thể được kích hoạt bằng các annotation `@Enable*` trên một lớp cấu hình Spring. Annotation được chọn theo loại ứng dụng (Servlet hay WebFlux) và kho lưu trữ phiên (Redis, JDBC hoặc repository do ứng dụng cung cấp). Khi bật cấu hình, Spring Session đăng ký thành phần quản lý phiên phù hợp để mã ứng dụng tiếp tục làm việc với `HttpSession` trong Servlet hoặc `WebSession` trong WebFlux, trong khi dữ liệu phiên được lưu qua repository.

Đối với module `SPRING_SESSION`, cấu hình tường minh là phần quan trọng khi ứng dụng cần quản lý session độc lập với một instance. Tất cả instance cần dùng cùng repository và cấu hình tương thích để một request có thể được xử lý ở bất kỳ instance nào mà vẫn khôi phục được trạng thái phiên. Annotation kích hoạt tích hợp; nó không tự tạo hạ tầng Redis, không tự bảo đảm schema JDBC đã tồn tại và cũng không thay thế cấu hình cookie, bảo mật hay kết nối.

## 1. Chọn annotation theo loại ứng dụng

Trước khi thêm annotation, cần xác định ứng dụng đang dùng Servlet hay Reactive WebFlux. Hai stack có API phiên khác nhau và dùng hai loại filter/interceptor tích hợp khác nhau.

| Loại ứng dụng | API phiên | Annotation thường dùng | Repository ví dụ |
|---|---|---|---|
| Spring MVC, Spring Boot Servlet, Servlet container | `HttpSession` | `@EnableRedisHttpSession`, `@EnableJdbcHttpSession` | Redis hoặc JDBC |
| Spring WebFlux | `WebSession` | `@EnableRedisWebSession` | Reactive Redis |
| Servlet với repository tự triển khai | `HttpSession` | `@EnableSpringHttpSession` | Bean `SessionRepository` do ứng dụng cung cấp |
| WebFlux với repository reactive tự triển khai | `WebSession` | `@EnableSpringWebSession` | Bean `ReactiveSessionRepository` do ứng dụng cung cấp |

Không thể thay `@EnableRedisHttpSession` bằng `@EnableRedisWebSession` chỉ để đổi tên cấu hình. Một ứng dụng Servlet dùng `HttpSession`; một ứng dụng WebFlux dùng `WebSession` và API reactive. Chọn sai loại annotation có thể làm cấu hình không khớp với web stack hoặc khiến ứng dụng không có đúng bean quản lý phiên.

## 2. Cấu hình Servlet với Redis

### 2.1. Thêm dependency

Với dự án Spring Boot dùng Gradle Kotlin DSL, cần dependency kết nối Redis và integration Spring Session Redis:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.session:spring-session-data-redis")
}
```

Nếu dự án dùng Maven, khai báo các artifact tương ứng trong `pom.xml`. Nên dùng Spring Boot dependency management hoặc BOM tương thích để quản lý phiên bản Spring Session, Spring Data Redis và Spring Framework. Tránh tự ghép các phiên bản không tương thích.

### 2.2. Bật repository bằng annotation

Tạo một lớp cấu hình trong component scan của ứng dụng:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 30 * 60)
public class HttpSessionConfiguration {
}
```

`@EnableRedisHttpSession` kích hoạt cấu hình Spring Session cho Servlet và tạo các thành phần cần thiết để ánh xạ `HttpSession` sang repository Redis. Thuộc tính `maxInactiveIntervalInSeconds` đặt thời gian không hoạt động mặc định là 30 phút. Một phiên có thể có giá trị riêng nếu ứng dụng gọi `setMaxInactiveInterval`.

Lớp cấu hình phải được Spring phát hiện. Nếu đặt lớp ngoài package được component scan, annotation sẽ không được áp dụng dù mã nguồn đã biên dịch thành công. Với cấu hình Java thuần, có thể import lớp cấu hình này từ lớp `@Configuration` gốc.

### 2.3. Cấu hình kết nối Redis

Trong Spring Boot, có thể cung cấp thông tin kết nối bằng `application.yml`:

```yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      timeout: 2s
```

Spring Boot có thể tự tạo `RedisConnectionFactory` từ các thuộc tính và dependency đang có. Nếu ứng dụng tự tạo `RedisConnectionFactory`, bean đó phải trỏ đến cùng Redis mà các instance khác sử dụng. Tên host, cổng, xác thực, TLS, database index và cấu hình cluster phải phù hợp với môi trường triển khai.

Khi chạy nhiều instance, mỗi instance phải kết nối đến cùng hệ thống Redis và dùng cùng namespace Spring Session. Nếu A ghi phiên vào Redis A còn B đọc Redis B, cookie có thể giống nhau nhưng B vẫn không tìm thấy dữ liệu. Cần quản lý các thuộc tính kết nối bằng cấu hình môi trường hoặc secret store, không commit mật khẩu vào repository mã nguồn.

### 2.4. Namespace và phân tách ứng dụng

Nếu nhiều ứng dụng dùng chung Redis, nên phân tách vùng khóa phiên bằng namespace. Có thể cấu hình namespace trong annotation:

```java
@Configuration
@EnableRedisHttpSession(
    maxInactiveIntervalInSeconds = 30 * 60,
    redisNamespace = "storefront:sessions"
)
public class HttpSessionConfiguration {
}
```

Namespace giúp tránh va chạm khóa giữa các ứng dụng hoặc môi trường. Tất cả instance thuộc cùng một ứng dụng cần dùng cùng namespace. Nếu một instance dùng `storefront:sessions` còn instance khác dùng namespace khác, phiên sẽ không được chia sẻ dù chúng kết nối cùng máy chủ Redis.

## 3. Cấu hình Servlet với JDBC

JDBC là lựa chọn phù hợp khi tổ chức muốn lưu phiên trong cơ sở dữ liệu quan hệ đang vận hành. Các instance cùng sử dụng một `DataSource` logic và truy cập cùng bảng phiên.

### 3.1. Thêm dependency và bật annotation

Ví dụ với Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.session:spring-session-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
```

Thay driver PostgreSQL bằng driver tương ứng với cơ sở dữ liệu của dự án. Sau đó khai báo cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession(maxInactiveIntervalInSeconds = 30 * 60)
public class HttpSessionConfiguration {
}
```

`@EnableJdbcHttpSession` kích hoạt repository phiên JDBC và tích hợp với Servlet `HttpSession`. Cấu hình cần có một bean `DataSource` hợp lệ. Trong Spring Boot, `DataSource` thường được tạo từ `spring.datasource.*`; nếu dự án tự cấu hình nhiều nguồn dữ liệu, phải chỉ rõ nguồn phù hợp cho Spring Session theo cách cấu hình được phiên bản đang dùng hỗ trợ.

### 3.2. Tạo schema trước khi chạy

Spring Session JDBC cần các bảng và chỉ mục theo schema do Spring Session cung cấp cho từng hệ quản trị cơ sở dữ liệu. Việc thêm annotation không có nghĩa bảng tự xuất hiện trong mọi môi trường. Hãy dùng script schema chính thức tương ứng với database và phiên bản Spring Session, triển khai schema bằng công cụ migration hoặc quy trình quản trị cơ sở dữ liệu của tổ chức.

Ví dụ, một cấu hình phát triển có thể khai báo thông tin kết nối:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/appdb
    username: app_user
    password: ${APP_DB_PASSWORD}
```

Biến môi trường hoặc secret store cần cung cấp giá trị mật khẩu ở lúc chạy. Với production, nên quản lý thay đổi schema bằng Flyway, Liquibase hoặc quy trình migration đã được tổ chức phê duyệt; tránh phụ thuộc vào việc tự động tạo bảng khi ứng dụng khởi động.

### 3.3. Quản lý thời hạn và dọn dẹp

Repository JDBC lưu thời điểm hết hạn cùng dữ liệu phiên. Bản ghi hết hạn có thể được loại khỏi kết quả tra cứu trước khi tác vụ cleanup xóa vật lý khỏi bảng. Cần cấu hình và giám sát tác vụ dọn dẹp theo hướng dẫn của phiên bản Spring Session đang dùng, đồng thời theo dõi kích thước bảng, chỉ mục và tải truy vấn.

Không nên tự xóa bảng hoặc thay đổi tên cột theo ý muốn khi chưa điều chỉnh repository tương ứng. Nếu cần thay đổi schema, hãy kiểm tra mapping của phiên bản thư viện và kiểm thử migration trên bản sao dữ liệu trước khi triển khai.

## 4. Cấu hình WebFlux với Redis

WebFlux dùng `WebSession`, thường được truy cập qua `ServerWebExchange.getSession()`. Với Redis reactive, có thể bật Spring Session bằng `@EnableRedisWebSession`.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration
@EnableRedisWebSession(maxInactiveIntervalInSeconds = 30 * 60)
public class WebSessionConfiguration {
}
```

Ứng dụng cần dependency Spring Session Redis và Spring Data Redis phù hợp với WebFlux. Spring Boot thường cấu hình `ReactiveRedisConnectionFactory` từ các thuộc tính Redis nếu dependency và cấu hình ứng dụng phù hợp. Repository reactive phải dùng cùng kho dữ liệu và namespace trên mọi instance.

Trong WebFlux, thao tác với phiên nằm trong pipeline reactive:

```java
@RestController
public class CartController {

    @GetMapping("/cart/session")
    public Mono<String> updateCart(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            session.getAttributes().put("cartId", "CART-908");
            return "Session updated";
        });
    }
}
```

`getSession()` trả về `Mono<WebSession>`, vì vậy mã xử lý tiếp theo cần nằm trong pipeline reactive. Việc thay đổi thuộc tính được lưu theo cơ chế lưu `WebSession` khi response hoàn tất. Không gọi API Servlet như `HttpServletRequest.getSession()` trong controller WebFlux thuần.

Để vô hiệu hóa phiên trong WebFlux, dùng API của `WebSession` và xử lý kết quả reactive:

```java
@PostMapping("/logout")
public Mono<Void> logout(ServerWebExchange exchange) {
    return exchange.getSession()
        .flatMap(WebSession::invalidate);
}
```

Việc invalidation phải được thực thi bằng cách subscribe thông qua pipeline xử lý request; không tự gọi `subscribe()` trong controller để chạy tác vụ tách khỏi vòng đời response.

## 5. Repository tùy chỉnh với annotation tổng quát

Các annotation theo store như `@EnableRedisHttpSession` hoặc `@EnableJdbcHttpSession` phù hợp khi dùng implementation được Spring Session cung cấp. Nếu ứng dụng có một `SessionRepository` riêng cho Servlet, có thể dùng `@EnableSpringHttpSession` và cung cấp bean repository tương ứng.

Ví dụ cấu trúc khái niệm:

```java
@Configuration
@EnableSpringHttpSession
public class CustomHttpSessionConfiguration {

    @Bean
    public SessionRepository<? extends Session> sessionRepository() {
        // Trả về implementation SessionRepository do ứng dụng cung cấp.
        return createCustomRepository();
    }
}
```

`createCustomRepository()` ở đây chỉ biểu thị factory của ứng dụng; cần thay bằng implementation thực tế. Repository phải đáp ứng hợp đồng của Spring Session về tạo, tìm, lưu, cập nhật và xóa session. Với WebFlux, annotation tổng quát tương ứng là `@EnableSpringWebSession` và cần một `ReactiveSessionRepository`.

Annotation tổng quát không tự chọn Redis hoặc JDBC. Trách nhiệm tạo repository, quản lý kết nối, thời hạn, serialization và tính sẵn sàng thuộc về implementation mà ứng dụng cung cấp. Không khai báo annotation tổng quát đồng thời với annotation store-specific cho cùng một web stack nếu cả hai cùng cố đăng ký filter hoặc session manager.

## 6. Tùy chỉnh cookie phiên

Annotation `@Enable*HttpSession` bật cơ chế lưu session; cookie là một phần cấu hình khác. Spring Session Servlet thường dùng cookie để mang session ID. Có thể tùy chỉnh cookie thông qua `CookieSerializer` bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SessionCookieConfiguration {

    @Bean
    public CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SESSION");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");
        return serializer;
    }
}
```

`HttpOnly` ngăn JavaScript phía trình duyệt đọc cookie qua các API thông thường; `Secure` giới hạn cookie gửi qua HTTPS; `SameSite` kiểm soát cách cookie được gửi trong điều hướng cross-site. Giá trị `SameSite` cần phù hợp với luồng đăng nhập, SSO và tích hợp frontend. Nếu ứng dụng chạy HTTP cục bộ, cần cấu hình `Secure` phù hợp môi trường thử nghiệm; production nên dùng HTTPS.

Nếu ứng dụng tự đổi tên cookie hoặc `Path`/`Domain`, mọi instance phải dùng cấu hình giống nhau. Response xóa cookie khi logout cũng cần khớp các thuộc tính định danh cookie đã phát trước đó. Cookie chỉ mang mã phiên, không nên chứa dữ liệu xác thực hoặc thông tin nghiệp vụ nhạy cảm theo cách không được bảo vệ.

Với WebFlux, cookie được quản lý bởi cơ chế phân giải `WebSession` tương ứng. Không sao chép bean Servlet `CookieSerializer` vào cấu hình WebFlux mà không kiểm tra API resolver của phiên bản đang dùng.

## 7. Kết hợp cấu hình annotation với Spring Boot

Spring Boot có thể tự cấu hình Spring Session khi dependency, cấu hình store và phiên bản Boot đáp ứng điều kiện auto-configuration. Cấu hình tường minh bằng annotation là một cách chủ động khai báo repository. Nên chọn một cách cấu hình rõ ràng để tránh tạo nhiều repository hoặc nhiều thành phần filter quản lý cùng một session.

Khi dùng annotation:

1. Kiểm tra dependency có đúng store (Redis hoặc JDBC) và đúng web stack không.
2. Đặt lớp cấu hình trong component scan hoặc import trực tiếp.
3. Cung cấp `RedisConnectionFactory`, `ReactiveRedisConnectionFactory` hoặc `DataSource` tương ứng.
4. Kiểm tra annotation tạo đúng repository và filter/session manager trong application context.
5. Tránh đồng thời khai báo nhiều annotation bật session cho cùng một stack.
6. Kiểm tra các thuộc tính Spring Boot có liên quan để chắc chắn chúng không tạo cấu hình cạnh tranh hoặc ghi đè giá trị dự kiến.

Nếu chuyển từ auto-configuration sang annotation tường minh, hãy kiểm tra điều kiện back-off của auto-configuration theo phiên bản Spring Boot. Không nên dựa vào giả định rằng mọi phiên bản Boot đều có hành vi giống nhau khi xuất hiện một bean hoặc annotation cụ thể.

## 8. Thứ tự filter và tích hợp Spring Security

Trong Servlet, `SessionRepositoryFilter` phải tham gia xử lý request trước các filter cần đọc hoặc ghi `HttpSession`, trong đó có Spring Security. Nếu filter bảo mật chạy trước và truy cập session bằng cơ chế mặc định của container, nó có thể không nhìn thấy session do Spring Session quản lý.

Spring Boot thường hỗ trợ đăng ký filter khi cấu hình Spring Session đúng cách. Với ứng dụng tự đăng ký filter hoặc dùng container bên ngoài Boot, cần kiểm tra cách đăng ký filter và thứ tự thực tế. Không đăng ký thủ công thêm một bản `SessionRepositoryFilter` nếu annotation đã tạo và đăng ký filter đó.

Khi dùng Spring Security, kiểm thử các luồng sau:

- Đăng nhập tạo hoặc cập nhật session theo chính sách bảo mật.
- Session ID được thay đổi sau xác thực nếu chính sách chống session fixation yêu cầu.
- Request tiếp theo ở instance khác khôi phục đúng SecurityContext.
- Logout vô hiệu hóa phiên ở repository và response xử lý cookie.
- Session hết hạn hoặc bị thu hồi không được xem là đã xác thực.

Với WebFlux Security, cơ chế tích hợp chạy trên `WebFilter` và `WebSession`. Không áp dụng thứ tự Servlet filter cho ứng dụng reactive; cần bảo đảm cấu hình WebFlux Session và Security cùng sử dụng `WebSession` được quản lý bởi Spring Session.

## 9. Chọn cấu hình theo tình huống

| Tình huống | Hướng cấu hình |
|---|---|
| Spring MVC nhiều instance, cần lưu phiên nhanh | `@EnableRedisHttpSession` với Redis dùng chung |
| Spring MVC nhiều instance, tổ chức ưu tiên cơ sở dữ liệu quan hệ | `@EnableJdbcHttpSession` với schema Spring Session đã triển khai |
| WebFlux nhiều instance dùng Redis | `@EnableRedisWebSession` với Reactive Redis dùng chung |
| Servlet có kho phiên riêng | `@EnableSpringHttpSession` và `SessionRepository` tùy chỉnh |
| WebFlux có kho phiên reactive riêng | `@EnableSpringWebSession` và `ReactiveSessionRepository` tùy chỉnh |

Không có một annotation duy nhất phù hợp với mọi ứng dụng. Hãy chọn dựa trên web stack, repository, cách vận hành và khả năng tương thích phiên bản. Với ứng dụng Servlet cần JDBC, dùng annotation JDBC Servlet. Với ứng dụng WebFlux, dùng annotation WebFlux và repository reactive được hỗ trợ; không suy ra rằng mọi store Servlet đều có một annotation reactive tương ứng.

## 10. Kiểm thử cấu hình tường minh

Sau khi bật annotation, cần xác nhận cấu hình thực sự hoạt động qua HTTP request và repository. Việc application context khởi động thành công chưa đủ để chứng minh session đã được chia sẻ.

Một bộ kiểm thử cơ bản nên gồm:

1. Khởi động application context với cấu hình annotation và repository tương ứng.
2. Gửi request tạo session, ghi một thuộc tính đơn giản và lưu cookie từ response.
3. Gửi request tiếp theo với cookie đó; xác nhận thuộc tính đã lưu được đọc lại.
4. Khởi động instance thứ hai dùng cùng Redis namespace hoặc cùng database/schema; gửi cookie từ instance đầu và xác nhận dữ liệu phiên được khôi phục.
5. Gọi logout hoặc invalidate; gửi lại cookie cũ đến instance còn lại và xác nhận phiên không còn hiệu lực.
6. Để phiên hết hạn và kiểm tra hành vi theo `maxInactiveIntervalInSeconds`.
7. Thử trường hợp repository mất kết nối để xác nhận ứng dụng không cấp quyền khi không thể xác minh session.

Ngoài ra, kiểm tra cookie thực tế trong response: tên cookie, `Path`, `Domain`, `HttpOnly`, `Secure`, `SameSite` và thời hạn nếu có. Kiểm tra log khởi động để phát hiện thiếu bean, lỗi kết nối, schema không tồn tại hoặc filter đăng ký sai. Trong production, cần theo dõi độ trễ và lỗi truy cập repository.

## 11. Lỗi cấu hình thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy session được lưu trong Redis | Thiếu dependency, annotation không được scan hoặc Redis connection factory sai | Kiểm tra dependency, package cấu hình và kết nối Redis |
| JDBC báo thiếu bảng | Schema Spring Session chưa được triển khai hoặc sai database | Chạy migration schema đúng database và phiên bản |
| Instance A thấy phiên, B không thấy | Khác Redis endpoint, namespace, database hoặc cookie resolver | Đồng bộ cấu hình giữa các instance |
| Có hai repository hoặc filter | Bật nhiều annotation hoặc vừa cấu hình thủ công vừa dùng auto-configuration | Chọn một cơ chế cấu hình và kiểm tra bean/filter đăng ký |
| Spring Security không đọc được session | Thứ tự filter không phù hợp hoặc security dùng session container khác | Kiểm tra thứ tự đăng ký filter và tích hợp security |
| WebFlux không tìm thấy `HttpSession` | Dùng API Servlet trong reactive application | Dùng `WebSession` và `ServerWebExchange.getSession()` |
| Logout xong cookie vẫn được gửi | Cookie xóa sai tên, Path hoặc Domain | Kiểm tra `Set-Cookie` và cấu hình serializer/resolver |
| Redis hoặc database quá tải | Pool, timeout, TTL hoặc lưu quá nhiều dữ liệu phiên | Theo dõi tải repository, tối giản session và điều chỉnh cấu hình |

## 12. Nguyên tắc triển khai

- Xác định rõ Servlet hay WebFlux trước khi chọn annotation.
- Dùng đúng annotation theo repository: Redis HTTP, JDBC HTTP, Redis Web hoặc annotation tổng quát cho repository tùy chỉnh.
- Bảo đảm lớp cấu hình được Spring nạp và dependency tương thích với Spring Boot.
- Cung cấp connection factory hoặc `DataSource` hợp lệ; chuẩn bị schema trước khi dùng JDBC.
- Dùng cùng repository, namespace và cấu hình cookie trên mọi instance.
- Chỉ bật một cơ chế quản lý session cho mỗi web stack; tránh tạo filter hoặc repository trùng lặp.
- Kiểm tra thứ tự tích hợp với Spring Security và dùng đúng API `HttpSession` hoặc `WebSession`.
- Kiểm thử qua nhiều instance, bao gồm tạo phiên, đọc lại, logout, hết hạn và lỗi repository.

Các annotation `@Enable*HttpSession` và `@Enable*WebSession` là điểm vào cấu hình rõ ràng cho Spring Session. Chúng kết nối web stack với repository mà ứng dụng chọn. Khi dependency, bean kết nối, schema, namespace, cookie và filter chain được cấu hình đồng nhất, nhiều instance Spring có thể cùng quản lý một trạng thái phiên thông qua kho lưu trữ chia sẻ.
