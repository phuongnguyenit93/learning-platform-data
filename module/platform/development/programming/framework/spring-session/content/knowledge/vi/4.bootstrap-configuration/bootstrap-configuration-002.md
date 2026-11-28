# Phụ thuộc cho Servlet, WebFlux, Redis, JDBC và kiểm thử

## Mục tiêu bài học

Spring Session tách API quản lý phiên khỏi nơi lưu trữ dữ liệu. Để tích hợp vào một ứng dụng Spring, cần chọn đúng thư viện theo mô hình xử lý request, bổ sung driver hoặc client cho kho dữ liệu, cấu hình kết nối và chuẩn bị các dependency kiểm thử phù hợp.

Sau bài học, bạn có thể:

- Phân biệt dependency cho ứng dụng Servlet và WebFlux.
- Chọn Spring Session Redis hoặc Spring Session JDBC theo kiến trúc và hạ tầng.
- Xác định vai trò của Spring Boot starter, module Spring Session và database driver.
- Cấu hình dependency bằng Gradle hoặc Maven mà vẫn giữ phiên bản tương thích.
- Chuẩn bị môi trường kiểm thử session với MockMvc, WebTestClient, H2 và Redis.
- Nhận diện lỗi do chọn sai module, thiếu driver, cấu hình repository chồng lấn hoặc môi trường test khác production.

## 1. Bản đồ các thành phần cần có

Một ứng dụng Spring Session thường có nhiều lớp dependency. Không có một thư viện duy nhất vừa cung cấp web runtime, vừa kết nối kho dữ liệu, vừa thay thế toàn bộ cấu hình ứng dụng.

| Thành phần | Trách nhiệm |
|---|---|
| Web starter | Cung cấp nền tảng nhận và xử lý HTTP request |
| Spring Session module | Tích hợp API session với repository cụ thể |
| Data starter | Cung cấp Spring Data, connection factory và client cho kho dữ liệu |
| Redis hoặc database server | Lưu trữ dữ liệu session thực tế |
| Database driver | Cho phép JDBC kết nối đến hệ quản trị cơ sở dữ liệu |
| Test starter | Cung cấp JUnit, Spring Test, assertion và mock |
| Test repository/server | Giúp kiểm tra hành vi lưu session thực tế |

Ví dụ, ứng dụng Servlet dùng Redis thường cần web stack Servlet, Spring Session Redis và Spring Data Redis. Ứng dụng Servlet dùng JDBC cần web stack Servlet, Spring Session JDBC, Spring JDBC và driver cơ sở dữ liệu. Ứng dụng WebFlux cần web stack reactive và một repository có API reactive tương ứng.

Cần phân biệt **starter** với **module Spring Session**:

- Starter của Spring Boot gom các dependency thường dùng và giúp auto-configuration nhận diện hạ tầng.
- Module Spring Session cung cấp tích hợp session cho một loại repository.
- Redis hoặc PostgreSQL là dịch vụ lưu trữ chạy bên ngoài ứng dụng; dependency Java không tự khởi động máy chủ dữ liệu trong production.

## 2. Chọn đúng web stack: Servlet hay WebFlux

Spring MVC và Spring WebFlux có mô hình xử lý request khác nhau. Việc chọn dependency web ảnh hưởng đến API session và repository có thể sử dụng.

### Ứng dụng Servlet

Các ứng dụng Spring MVC thông thường chạy trên Servlet container như Tomcat, Jetty hoặc Undertow. Ứng dụng làm việc với:

- `HttpServletRequest`
- `HttpServletResponse`
- `HttpSession`
- Filter trong Servlet filter chain

Với Spring Boot, dependency web phổ biến là:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-web")
~~~

Spring Session tích hợp vào Servlet filter chain để thay thế cách phân giải và lưu session mặc định của container. Controller vẫn có thể dùng `HttpSession`, trong khi repository được chuyển sang Redis hoặc JDBC.

Hai module Spring Session phổ biến cho ứng dụng Servlet là:

- `spring-session-data-redis`
- `spring-session-jdbc`

Chọn một repository phù hợp với kiến trúc và hạ tầng của ứng dụng. Không thêm cả hai module chỉ vì muốn có nhiều lựa chọn; nếu cần nhiều repository, phải cấu hình rõ repository nào được sử dụng và cách định tuyến dữ liệu.

### Ứng dụng WebFlux

Spring WebFlux hỗ trợ xử lý reactive. API session trong WebFlux là `WebSession`, được truy cập qua `ServerWebExchange` hoặc cơ chế tương ứng của framework. Ứng dụng không làm việc với `HttpSession` theo cách của Servlet.

Dependency web phổ biến:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-webflux")
~~~

WebFlux cần một `ReactiveSessionRepository`. Spring Session Redis cung cấp tích hợp reactive với Redis, vì vậy module Redis có thể dùng trong cả ứng dụng Servlet và reactive, nhưng cấu hình và API session khác nhau.

Ví dụ, trong WebFlux:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveSessionController {

    @GetMapping("/visit")
    public Mono<String> visit(WebSession session) {
        Integer count = session.getAttribute("count");
        int next = (count == null) ? 1 : count + 1;

        session.getAttributes().put("count", next);
        return Mono.just("Visit: " + next);
    }
}
~~~

Trong ví dụ này, thuộc tính được thao tác qua `WebSession`. Không thể thay `WebSession` bằng `HttpSession` rồi kỳ vọng ứng dụng reactive tự chuyển đổi.

Spring Session JDBC truyền thống cung cấp repository dựa trên JDBC và API Servlet đồng bộ. Không nên chọn module JDBC đó làm reactive repository trực tiếp cho WebFlux. Nếu ứng dụng WebFlux cần session lưu tập trung, hãy chọn repository có API reactive được hỗ trợ, thường là Redis trong cấu hình Spring Session phổ biến.

### Không trộn hai web stack một cách tùy tiện

Không nên thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux` chỉ để dùng được cả hai kiểu session. Spring Boot có quy tắc lựa chọn application type và việc có cả hai stack có thể khiến runtime hoạt động khác kỳ vọng.

Nếu hệ thống thật sự có hai ứng dụng với hai mô hình xử lý khác nhau, nên tách chúng thành hai application hoặc hai tiến trình có cấu hình riêng. Mỗi ứng dụng cần dùng API session và repository phù hợp.

## 3. Dependency cho Spring Session với Redis

Redis là kho key-value phù hợp để lưu dữ liệu session có thời hạn. Redis hỗ trợ TTL ở cấp key, cho phép dữ liệu session tự hết hạn theo chính sách repository.

Trong ứng dụng Spring Boot Servlet, nhóm dependency thường dùng là:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.session:spring-session-data-redis")
}
~~~

Vai trò của từng dependency:

- `spring-boot-starter-web`: cung cấp Spring MVC và Servlet runtime.
- `spring-boot-starter-data-redis`: cung cấp Spring Data Redis, cấu hình kết nối và Redis client được Spring Boot hỗ trợ.
- `spring-session-data-redis`: cung cấp repository Spring Session dùng Redis.

Nếu ứng dụng đã có web starter hoặc Redis starter, không cần khai báo trùng lặp. Cần kiểm tra dependency tree khi một starter đã được đưa vào qua module khác.

### Cấu hình kết nối Redis

Ví dụ với Redis chạy tại máy phát triển:

~~~properties
spring.data.redis.host=localhost
spring.data.redis.port=6379
spring.session.timeout=30m
~~~

Trong môi trường production, thông tin host, port, mật khẩu, TLS và các thông số kết nối cần lấy từ cấu hình triển khai hoặc secret manager. Không commit mật khẩu thật vào repository.

`spring.session.timeout` biểu diễn thời hạn không hoạt động của session theo cấu hình Spring Boot. Repository Redis quản lý dữ liệu phiên cùng thời hạn tương ứng. Cần kiểm tra cấu hình và phiên bản Spring Boot/Spring Session để xác nhận các thuộc tính được hỗ trợ trong dự án.

### Cấu hình Servlet khi không dùng auto-configuration

Trong một ứng dụng Spring cấu hình thủ công, có thể bật tích hợp Redis cho Servlet bằng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1800)
public class SessionConfig {
}
~~~

Cấu hình này đăng ký Spring Session cho Servlet và cần có `RedisConnectionFactory` trong application context. Spring Boot có thể cung cấp factory đó khi Redis starter và các thuộc tính kết nối được cấu hình.

Trong Spring Boot, nếu auto-configuration đã đăng ký repository, không nên thêm annotation kích hoạt thủ công một cách máy móc. Chọn một cơ chế cấu hình rõ ràng, tránh tạo nhiều filter hoặc repository cạnh tranh.

### Cấu hình reactive WebFlux với Redis

Với WebFlux, dependency Redis và Spring Session Redis vẫn có thể được dùng, nhưng tích hợp là reactive. Cấu hình thủ công sử dụng annotation dành cho `WebSession`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration
@EnableRedisWebSession(maxInactiveIntervalInSeconds = 1800)
public class ReactiveSessionConfig {
}
~~~

Không dùng `@EnableRedisHttpSession` cho ứng dụng WebFlux. Annotation đó dành cho Servlet `HttpSession`. Cũng không dùng `@EnableRedisWebSession` trong một ứng dụng MVC chỉ vì dependency Redis đã có mặt.

## 4. Dependency cho Spring Session với JDBC

JDBC phù hợp khi tổ chức đã vận hành cơ sở dữ liệu quan hệ và muốn lưu session trong cùng nhóm hạ tầng dữ liệu. Spring Session JDBC cung cấp repository lưu dữ liệu session trong các bảng do Spring Session quản lý.

Trong ứng dụng Spring Boot Servlet, dependency thường dùng:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.session:spring-session-jdbc")

    runtimeOnly("org.postgresql:postgresql")
}
~~~

Vai trò:

- `spring-boot-starter-web`: cung cấp Servlet runtime.
- `spring-boot-starter-jdbc`: cung cấp Spring JDBC, connection pool và auto-configuration `DataSource`.
- `spring-session-jdbc`: cung cấp JDBC-backed session repository.
- Driver PostgreSQL: cho phép JDBC giao tiếp với PostgreSQL. Thay driver này bằng driver của hệ quản trị mà ứng dụng thực sự sử dụng.

Nếu dự án dùng MySQL, MariaDB, SQL Server hoặc Oracle, cần chọn đúng JDBC driver và cấu hình URL tương ứng. Không thêm nhiều driver nếu ứng dụng chỉ kết nối một hệ quản trị.

### Cấu hình DataSource và schema

Ví dụ cấu hình với PostgreSQL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/app
spring.datasource.username=${DB_USERNAME}
spring.datasource.password=${DB_PASSWORD}

spring.session.jdbc.initialize-schema=always
spring.session.timeout=30m
~~~

Trong file cấu hình thật, thay hai giá trị placeholder bằng biến môi trường hoặc cơ chế quản lý secret của hệ thống. Không lưu mật khẩu thật trong source control.

Spring Session JDBC cần schema tương ứng với phiên bản thư viện. Trong môi trường phát triển hoặc test, có thể cho Spring Boot khởi tạo schema tự động theo cấu hình. Trong production, nên quản lý schema qua công cụ migration và quy trình triển khai cơ sở dữ liệu của tổ chức.

Không tự tạo bảng với tên cột tùy ý. Hãy dùng schema script do đúng phiên bản Spring Session cung cấp và kiểm tra các thay đổi schema khi nâng cấp thư viện.

### Cấu hình Servlet khi không dùng auto-configuration

Với cấu hình thủ công, có thể bật JDBC session bằng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.jdbc.config.annotation.web.http.EnableJdbcHttpSession;

@Configuration
@EnableJdbcHttpSession
public class SessionConfig {
}
~~~

Cấu hình cần một `DataSource` có thể được inject. Nếu dùng Spring Boot và dependency phù hợp, Boot thường tự cấu hình `DataSource` từ các thuộc tính `spring.datasource.*`.

Tương tự Redis, không bật thủ công `@EnableJdbcHttpSession` nếu auto-configuration đã thiết lập cùng repository. Hãy xác nhận chỉ có một cấu hình session chủ đạo trong application context.

## 5. Dùng Spring Boot dependency management để giữ phiên bản tương thích

Spring Session phụ thuộc vào Spring Framework, Spring Data và các thư viện nền tảng khác. Tự chọn phiên bản độc lập cho từng dependency có thể tạo ra xung đột runtime.

Với dự án Spring Boot, nên dùng Spring Boot parent/BOM hoặc plugin dependency management để quản lý phiên bản. Khi đó, có thể khai báo dependency mà không ghi version riêng nếu BOM quản lý artifact đó.

Ví dụ Gradle với plugin Spring Boot và dependency management đã được thiết lập:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.session:spring-session-data-redis")
}
~~~

Nếu dự án không dùng Spring Boot, hãy quản lý phiên bản Spring Session bằng Spring Session BOM và bảo đảm các phiên bản Spring Framework, Spring Data Redis/JDBC tương thích với nhau.

Tránh:

- Ghi một version Spring Session mới hơn tùy ý so với Spring Boot đang dùng.
- Ép phiên bản Spring Data Redis khác với phiên bản được BOM quản lý mà không có lý do.
- Trộn dependency `javax.servlet` cũ với ứng dụng Spring hiện đại sử dụng `jakarta.servlet`.
- Sao chép cấu hình từ một phiên bản Spring Boot khác mà không kiểm tra property đã đổi tên hoặc bị loại bỏ.

### Ví dụ Maven

Với Maven, nếu dự án đã dùng Spring Boot parent hoặc import Spring Boot BOM, có thể khai báo dependency theo cách tương tự:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Để đổi sang JDBC, thay Redis starter và module Spring Session Redis bằng JDBC starter, Spring Session JDBC và driver cơ sở dữ liệu phù hợp. Không thêm cả hai nhóm một cách mặc định.

## 6. Dependency phục vụ kiểm thử

Kiểm thử session cần nhiều mức khác nhau. Unit test kiểm tra logic cập nhật thuộc tính; web test kiểm tra cookie và request; integration test kiểm tra repository thật, serialization, TTL và hành vi khi có nhiều instance.

Dependency test phổ biến:

~~~gradle
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.session:spring-session-test")
}
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test, Mockito và các thư viện assertion thường dùng. `spring-session-test` bổ sung tiện ích hỗ trợ kiểm thử Spring Session theo phiên bản thư viện. Kiểm tra tài liệu phiên bản đang dùng để chọn đúng API hỗ trợ; không nên giả định một helper cụ thể có mặt trong mọi phiên bản.

### Kiểm thử JDBC bằng H2

Đối với test repository JDBC, có thể dùng H2 làm cơ sở dữ liệu nhẹ:

~~~gradle
dependencies {
    testRuntimeOnly("com.h2database:h2")
}
~~~

Cấu hình test có thể dùng URL H2 và yêu cầu Spring Session khởi tạo schema:

~~~properties
spring.datasource.url=jdbc:h2:mem:session_test;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.session.jdbc.initialize-schema=always
spring.session.timeout=5m
~~~

H2 hữu ích cho test nhanh, nhưng không thay thế hoàn toàn PostgreSQL, MySQL hoặc hệ quản trị production. Khác biệt về SQL dialect, kiểu dữ liệu, transaction, isolation và index có thể làm test H2 không phát hiện một số lỗi production.

Với hệ thống phụ thuộc nhiều vào đặc tính của cơ sở dữ liệu thật, hãy chạy thêm integration test với đúng hệ quản trị bằng Testcontainers hoặc môi trường kiểm thử tương đương.

### Kiểm thử Redis bằng Testcontainers hoặc Redis test server

Không nên chỉ mock `RedisTemplate` khi mục tiêu là xác minh Spring Session ghi và đọc session. Mock không mô phỏng đầy đủ:

- Serialization và deserialize dữ liệu session.
- TTL thực tế của key.
- Redis connection factory.
- Hành vi repository khi có nhiều request.
- Namespace và dữ liệu chia sẻ giữa các instance.

Có thể dùng Testcontainers để chạy Redis cô lập trong integration test. Mỗi test suite nên có namespace hoặc key space riêng để tránh dữ liệu của test này ảnh hưởng test khác. Khi kiểm tra TTL, nên chọn thời gian đủ ngắn nhưng vẫn tránh phụ thuộc quá mức vào lịch chạy chính xác từng mili giây.

## 7. Kiểm thử web session qua cookie

Một bài kiểm thử quan trọng là xác minh session được tiếp tục qua nhiều HTTP request.

Với Servlet và MockMvc, quy trình thường là:

1. Gửi request đầu tiên đến endpoint tạo hoặc cập nhật session.
2. Lấy cookie session từ response.
3. Gửi cookie đó trong request tiếp theo.
4. Đọc thuộc tính session và xác minh giá trị đã được khôi phục.
5. Xác minh response sau khi session hết hạn hoặc bị invalidate.

Ví dụ khung kiểm thử:

~~~java
MvcResult first = mockMvc.perform(post("/cart/items")
        .param("productId", "BOOK-01")
        .param("quantity", "1"))
    .andExpect(status().isOk())
    .andReturn();

Cookie sessionCookie = first.getResponse().getCookie("SESSION");

mockMvc.perform(get("/cart")
        .cookie(sessionCookie))
    .andExpect(status().isOk());
~~~

Tên cookie trong ví dụ là `SESSION` để minh họa. Tên thực tế phụ thuộc cấu hình `CookieSerializer` hoặc cấu hình session của ứng dụng. Nếu dùng tên mặc định khác, hãy lấy đúng cookie từ response thay vì cố định tên không phù hợp.

Với WebFlux, có thể dùng `WebTestClient` để gửi request và truyền lại cookie giữa các lần exchange. Điều quan trọng vẫn là giữ cùng cookie session và xác minh dữ liệu qua một request mới.

MockMvc và WebTestClient rất hữu ích cho kiểm tra tầng web. Tuy nhiên, nếu test chỉ dùng session giả trong bộ nhớ, nó chưa xác minh dữ liệu được serialize và lưu qua Redis/JDBC. Hãy kết hợp web test với repository integration test.

## 8. Kiểm thử nhiều instance dùng chung repository

Một mục tiêu quan trọng của Spring Session là cho phép nhiều instance cùng truy cập dữ liệu phiên.

Có thể mô phỏng tình huống:

~~~text
                 Trình duyệt
               Cookie: SESSION
                      |
                Load Balancer
                 /         \
             App A         App B
                \           /
                 \         /
                Redis hoặc JDBC
                Shared Session
~~~

Một integration test có thể thực hiện:

1. Khởi động repository Redis hoặc JDBC dùng chung.
2. Khởi động hai application context hoặc hai server instance với cấu hình tương thích.
3. Gửi request tạo session đến App A.
4. Lấy cookie session từ response.
5. Gửi request tiếp theo kèm cookie đó đến App B.
6. Xác minh App B đọc được thuộc tính đã lưu từ App A.
7. Cập nhật dữ liệu ở App B rồi đọc lại qua App A.

Khi thực hiện test này, cần dùng cùng namespace Redis hoặc cùng schema/bảng session mà hai instance được cấu hình dùng chung. Đồng thời, nên xác minh hai instance không vô tình dùng chung bộ nhớ cục bộ mà không truy cập repository.

Test nhiều instance giúp phát hiện các lỗi như:

- Một instance dùng namespace Redis khác.
- Một instance có serializer không tương thích.
- Cookie name, path hoặc domain khác nhau.
- Một instance đang dùng repository khác.
- Phiên bản ứng dụng không thể deserialize dữ liệu do instance còn lại ghi.

## 9. Phân tách dependency theo môi trường

Không phải mọi dependency đều cần có ở production.

| Dependency | Compile/runtime production | Test |
|---|---|---|
| Web starter | Có | Có thể dùng chung từ main runtime |
| Spring Session Redis/JDBC | Có, theo repository được chọn | Có |
| Redis starter hoặc JDBC starter | Có, theo kho dữ liệu | Có |
| JDBC driver production | Runtime | Có thể dùng driver test riêng |
| H2 | Không cần nếu production không dùng H2 | Test runtime |
| Spring Boot test starter | Không | Test |
| Spring Session test | Không | Test |
| Testcontainers | Không | Test |

Với Gradle, dùng `implementation` cho dependency cần trong mã ứng dụng, `runtimeOnly` cho driver chỉ cần lúc chạy, và `testImplementation` hoặc `testRuntimeOnly` cho thư viện chỉ dùng trong test.

Với Maven, dùng scope `test` cho thư viện test. Driver có thể dùng scope runtime nếu mã nguồn không trực tiếp import lớp driver.

Không nên đưa Testcontainers, H2 hoặc công cụ test vào artifact production nếu ứng dụng không cần chúng lúc chạy.

## 10. Các cấu hình mẫu theo từng lựa chọn

### Servlet + Redis

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.session:spring-session-data-redis")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.session:spring-session-test")
}
~~~

~~~properties
spring.data.redis.host=localhost
spring.data.redis.port=6379
spring.session.timeout=30m
~~~

### Servlet + JDBC

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.session:spring-session-jdbc")

    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("com.h2database:h2")
}
~~~

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/app
spring.datasource.username=${DB_USERNAME}
spring.datasource.password=${DB_PASSWORD}
spring.session.jdbc.initialize-schema=always
spring.session.timeout=30m
~~~

Trong production, schema nên được quản lý theo quy trình migration của hệ thống. `initialize-schema=always` hữu ích cho một số môi trường phát triển hoặc test, nhưng không nên bật tùy tiện trong production.

### WebFlux + Redis

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.session:spring-session-data-redis")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.session:spring-session-test")
}
~~~

~~~properties
spring.data.redis.host=localhost
spring.data.redis.port=6379
spring.session.timeout=30m
~~~

Cấu hình WebFlux phải sử dụng reactive session integration. Nếu cấu hình thủ công, dùng `@EnableRedisWebSession` và API `WebSession`. Không sử dụng cấu hình Servlet `@EnableRedisHttpSession` trong ví dụ WebFlux.

## 11. Các lỗi dependency và cấu hình thường gặp

**Chỉ thêm `spring-session-data-redis` nhưng thiếu Redis connection factory.**  
Module Spring Session cung cấp repository, nhưng ứng dụng vẫn cần Redis client và connection factory. Với Spring Boot, Redis starter thường cung cấp auto-configuration này.

**Thêm Redis starter nhưng quên module Spring Session Redis.**  
Redis starter chỉ cung cấp khả năng truy cập Redis. Nó không tự thay thế `HttpSession` bằng Spring Session Redis.

**Dùng `spring-session-jdbc` nhưng không có DataSource hoặc JDBC driver.**  
Repository JDBC cần kết nối cơ sở dữ liệu. Hãy kiểm tra URL, credential, driver và connection pool.

**Dùng `HttpSession` trong controller WebFlux.**  
WebFlux sử dụng `WebSession`. Hãy dùng đúng API theo web stack.

**Dùng annotation Servlet cho ứng dụng reactive.**  
`@EnableRedisHttpSession` dành cho Servlet. WebFlux dùng `@EnableRedisWebSession` khi cần cấu hình thủ công.

**Cấu hình auto-configuration và annotation thủ công cùng lúc.**  
Có thể tạo ra nhiều bean hoặc filter session không mong muốn. Chọn một cách cấu hình và kiểm tra application context.

**Test chỉ chạy với mock.**  
Mock có thể xác nhận logic Java nhưng không xác nhận TTL, serialization, schema hoặc chia sẻ session giữa nhiều instance. Cần integration test với repository thật.

**Phiên bản Spring Session không tương thích với Spring Boot.**  
Dùng dependency management của Spring Boot hoặc Spring Session BOM, rồi kiểm tra dependency tree nếu gặp lỗi `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi khởi tạo bean.

**Cấu hình schema JDBC tự động trong production mà không kiểm soát migration.**  
Việc tự khởi tạo schema có thể không phù hợp với quy trình quản trị dữ liệu. Nên quản lý schema theo version và quy trình migration.

## 12. Quy trình chọn dependency cho dự án

Có thể ra quyết định theo trình tự sau:

1. Xác định ứng dụng dùng Servlet hay WebFlux.
2. Xác định kho session: Redis hay JDBC.
3. Chọn module Spring Session tương ứng.
4. Bổ sung starter hoặc thư viện truy cập kho dữ liệu.
5. Bổ sung driver nếu repository JDBC cần hệ quản trị cụ thể.
6. Dùng Spring Boot dependency management để đồng bộ phiên bản.
7. Thêm test starter và tiện ích Spring Session test nếu cần.
8. Chọn H2 cho test JDBC nhanh hoặc Testcontainers để kiểm tra hệ quản trị thật.
9. Viết test giữ cookie qua nhiều request.
10. Viết integration test xác minh session có thể được chia sẻ giữa hai instance.

## 13. Tự kiểm tra

1. Spring Session Redis và Spring Boot Redis starter khác nhau ở trách nhiệm nào?
2. Vì sao ứng dụng Servlet dùng `HttpSession`, còn WebFlux dùng `WebSession`?
3. Dependency nào thường cần cho ứng dụng Servlet lưu session bằng JDBC?
4. Vì sao Spring Session JDBC truyền thống không phải lựa chọn reactive repository trực tiếp cho WebFlux?
5. Khi nào cần khai báo JDBC driver bằng `runtimeOnly`?
6. Vì sao nên dùng Spring Boot BOM hoặc Spring Session BOM?
7. H2 có thể thay thế hoàn toàn database production trong mọi integration test không?
8. Vì sao cần giữ cùng cookie session khi kiểm thử nhiều request?
9. Testcontainers giúp xác minh điều gì mà mock Redis không thể xác minh đầy đủ?
10. Khi nào cần kiểm thử hai instance dùng chung repository?

### Gợi ý trả lời

1. Redis starter cung cấp Spring Data Redis và kết nối Redis; Spring Session Redis tích hợp session repository dựa trên Redis.
2. Servlet và WebFlux có mô hình xử lý request khác nhau, nên API session và cách tích hợp cũng khác.
3. Thường cần web starter Servlet, `spring-boot-starter-jdbc`, `spring-session-jdbc` và driver cơ sở dữ liệu.
4. JDBC repository truyền thống dùng API đồng bộ và Servlet session; WebFlux cần `ReactiveSessionRepository`.
5. Khi mã nguồn không cần import lớp driver nhưng ứng dụng cần driver lúc chạy để tạo kết nối JDBC.
6. BOM giữ các phiên bản Spring Boot, Spring Framework, Spring Data và Spring Session tương thích.
7. Không. H2 không đại diện đầy đủ cho SQL dialect, isolation, transaction và hành vi của database production.
8. Cookie mang Session ID; nếu không gửi lại cookie, request tiếp theo có thể tạo session khác.
9. Testcontainers cho phép kiểm tra Redis thật, bao gồm kết nối, serialization, TTL và hành vi repository.
10. Khi cần xác minh request đến instance khác vẫn khôi phục đúng session từ kho dữ liệu dùng chung.

## Kết luận

Việc chọn dependency Spring Session bắt đầu từ web stack. Ứng dụng Servlet thường dùng `HttpSession` và có thể chọn Spring Session Redis hoặc JDBC. WebFlux dùng `WebSession` và cần repository reactive, phổ biến là Spring Session Redis.

Spring Session module chịu trách nhiệm tích hợp session với repository; Spring Boot data starter cung cấp hạ tầng kết nối; driver giúp JDBC giao tiếp với cơ sở dữ liệu; test starter và môi trường test thật giúp xác minh hành vi lưu trữ. Khi quản lý phiên bản bằng BOM, phân tách dependency theo môi trường và kiểm thử bằng cookie qua nhiều request, cấu hình session sẽ dễ duy trì hơn khi triển khai nhiều instance.

