# Spring Session và lựa chọn kho phiên tương thích từng web stack

## 1. Mục tiêu học tập và câu hỏi cốt lõi

Một ứng dụng Spring Boot có thể ghi một giá trị như `cartId` hoặc `visits` vào phiên (session) để request sau của cùng trình duyệt đọc lại. Khi ứng dụng chạy trên hai instance, câu hỏi khó hơn xuất hiện: **instance nào lưu phiên, phiên được chia sẻ ra sao và API phiên thuộc Spring MVC hay WebFlux?**

**Spring Session** tách cơ chế quản lý phiên khỏi bộ nhớ của từng web server, cung cấp API và tích hợp để lưu phiên vào Redis, cơ sở dữ liệu hoặc kho khác. Tuy nhiên, **Servlet/MVC và WebFlux có hai hợp đồng repository khác nhau**. Không thể chọn backend chỉ dựa vào việc “đã có Redis/JDBC”; phải xét web stack và khả năng hoạt động blocking/reactive của adapter.

Sau bài này, bạn có thể:

1. Phân biệt **session ID trong cookie**, trạng thái phiên trên server và token xác thực stateless.
2. Giải thích Spring Session thay thế `HttpSession` của Servlet bằng `SessionRepositoryFilter` và tích hợp `WebSession` của WebFlux thông qua `WebSessionManager`.
3. Nhận biết `SessionRepository` (đồng bộ) khác `ReactiveSessionRepository` (reactive), chọn kho phiên đúng cho từng web stack.
4. Cấu hình **Spring MVC + Spring Session JDBC** và **Spring WebFlux + Spring Session Data Redis** trong Spring Boot 3.3.x.
5. Quan sát session bằng `curl`, cookie jar, hai request liên tiếp, thay đổi port/instance và thời hạn không hoạt động.
6. Lý giải các trade-off của Redis, JDBC, MongoDB và repository in-memory, cùng vấn đề serialization, TTL, bảo mật, hiệu năng và lỗi vận hành.

Các ví dụ dùng **Java 17+, Spring Boot 3.3.5 và Spring Session 3.3.x** thông qua dependency management của Spring Boot. Tên starter hoặc nhóm kho tự động hỗ trợ có thể đổi ở dòng Spring Boot khác; không sao chép cấu hình của Spring Boot 4.x sang bài lab 3.3.x mà không kiểm tra.

## 2. Session, cookie và dữ liệu thật nằm ở đâu?

HTTP tự thân không nhớ rằng hai request đến từ cùng người dùng. Cơ chế session thường gồm:

- **Session ID**: chuỗi khó đoán, đại diện cho một phiên; ứng dụng thường trao cho browser bằng cookie, ví dụ cookie tên `SESSION` khi dùng Spring Session.
- **Session attributes**: dữ liệu lưu **ở phía server**, chẳng hạn `visits=2` hay mã giỏ hàng. Browser thường không nhận trực tiếp toàn bộ bản đồ attributes.
- **Session repository**: nơi tạo, đọc, cập nhật, hết hạn hoặc xóa session; có thể nằm trong RAM local, Redis, SQL database...
- **Session expiration**: giới hạn thời gian không hoạt động (idle timeout), gắn với lần truy cập cuối và chính sách lưu trữ/cleanup.

Chuỗi minh họa:

~~~text
Request đầu tiên (chưa có cookie phiên)
  Browser -- GET /counter --> Server A
  Server A -- tạo session id S, set visits=1 --> Repository
  Server A -- Set-Cookie: SESSION=<opaque-id> --> Browser

Request tiếp theo
  Browser -- Cookie: SESSION=<opaque-id> --> Server B
  Server B -- đọc session S từ Repository --> visits=1
  Server B -- set visits=2 và lưu phiên --> Repository
  Server B -- response {visits: 2} --> Browser
~~~

Nếu Server A và Server B dùng **cùng cơ chế session và cùng kho được cấu hình đúng**, request thứ hai có thể tiếp tục phiên mặc dù rơi vào instance khác. Nếu mỗi instance chỉ giữ map trong RAM riêng, Server B không tự thấy session của A. Load balancer sticky sessions có thể khiến request quay về A nhưng không giải quyết đầy đủ failover, restart hoặc mất instance.

Một cookie chỉ chứa session ID **không giống JWT**. JWT thường mang claims đã ký, có thể được server xác minh stateless; session ID là khóa tham chiếu tới trạng thái lưu ở server. Spring Session không mặc định biến session thành JWT. Cũng không nên tin cookie là bằng chứng người dùng đã đăng nhập: quyền truy cập phải được xác định bằng cơ chế authentication/authorization.

**Tránh nhầm “session cookie” và “session timeout”:**

- Cookie có thể không ghi `Max-Age`, khi đó browser thường coi là cookie phiên trình duyệt; điều này không có nghĩa session trên server không hết hạn.
- `spring.session.timeout=20m` (trong cấu hình Boot phù hợp) là thời hạn không hoạt động của phiên, không phải cam kết rằng cookie bị browser xóa chính xác sau 20 phút.
- Khi server thấy session ID đã hết hạn, phiên không còn hợp lệ ngay cả khi browser vẫn gửi cookie cũ.
- Thời điểm bản ghi thực sự bị xóa bởi Redis TTL hoặc job cleanup SQL có thể chậm hơn thời điểm phiên trở nên hết hiệu lực về mặt nghiệp vụ.

## 3. Spring Session thay thế cơ chế nào?

### 3.1. Servlet / Spring MVC

Với ứng dụng Servlet truyền thống, API công khai là `jakarta.servlet.http.HttpSession`. Không dùng Spring Session, session thường do servlet container (ví dụ Tomcat) quản lý theo cách cấu hình của container.

Khi thêm Spring Session repository đồng bộ vào Boot MVC, tích hợp trung tâm là **`SessionRepositoryFilter`**: filter bọc request/response và làm cho `request.getSession()` / tham số `HttpSession` sử dụng session do **`SessionRepository<S>`** quản lý. Controller Servlet vẫn đọc/ghi attributes bằng API `HttpSession` quen thuộc.

~~~text
HTTP request + cookie
    |
    v
Servlet Filter chain
    |
    v
SessionRepositoryFilter
    |
    +--> đọc/tạo Session từ SessionRepository
    |
    v
Spring MVC Controller -> HttpSession.setAttribute(...)
    |
    v
SessionRepository (Redis / JDBC / ...)
    |
    v
HTTP response + cookie phiên (khi cần)
~~~

Điều này không đổi controller sang API reactive. Repository JDBC hoặc Redis đồng bộ vẫn có thể làm I/O blocking; với Spring MVC, điều đó phù hợp với mô hình thread-per-request thông dụng nếu cấu hình pool, timeout và database được quản lý đúng.

### 3.2. Reactive / Spring WebFlux

Với Spring WebFlux, API công khai là **`org.springframework.web.server.WebSession`**, không phải `HttpSession` của Servlet. Spring Session cung cấp **`ReactiveSessionRepository<S>`** và tích hợp thông qua **`WebSessionManager`**. Các thao tác đọc/ghi repository được mô hình hóa bằng Reactor `Mono`/`Flux`, giữ phù hợp với pipeline reactive.

~~~text
HTTP request + cookie
    |
    v
WebFlux ServerWebExchange
    |
    v
WebSessionManager
    |
    +--> ReactiveSessionRepository (Redis reactive / Mongo reactive)
    |
    v
Reactive Controller -> WebSession.getAttributes().put(...)
    |
    v
Reactive persistence + hoàn tất response
~~~

WebFlux có thể chạy trên Reactor Netty **hoặc** trên Servlet container với runtime adapter. **Web stack do Spring MVC/WebFlux quyết định, không chỉ tên server.** Chạy WebFlux trên Tomcat vẫn không biến `WebSession` thành `HttpSession`.

### 3.3. Hai repository là hai hợp đồng khác nhau

| Đặc điểm | Servlet / MVC | WebFlux |
| --- | --- | --- |
| Session web API | `HttpSession` | `WebSession` |
| Core repository contract | `SessionRepository<S extends Session>` | `ReactiveSessionRepository<S extends Session>` |
| Phong cách gọi kho | Đồng bộ, trả dữ liệu trực tiếp | Reactive, trả publisher |
| Thành phần tích hợp | `SessionRepositoryFilter` | `WebSessionManager` và WebSessionStore |
| In-memory phục vụ demo/test | `MapSessionRepository` | `ReactiveMapSessionRepository` |
| Redis | `RedisSessionRepository` / indexed Redis repository | `ReactiveRedisSessionRepository` / reactive indexed repository |
| SQL/JDBC phổ biến | `JdbcIndexedSessionRepository` | **Không có adapter Spring Session JDBC reactive tương đương trong cấu hình Boot 3.3 thông thường** |
| Cách đọc/ghi trong controller | `session.getAttribute` / `setAttribute` | `session.getAttribute` / `getAttributes().put`, invalidate trả `Mono<Void>` |

Cần nắm: có `spring-boot-starter-data-r2dbc` hay driver SQL reactive trong project **không tự tạo** một implementation Spring Session repository qua R2DBC. Tương tự, kéo `spring-session-jdbc` vào WebFlux không tự tạo `ReactiveSessionRepository`. Kho dữ liệu và adapter session phải đúng hợp đồng.

## 4. Ma trận lựa chọn kho phiên trong Spring Boot 3.3.x

Với Spring Boot 3.3, những lựa chọn session store auto-configure tiêu biểu được tài liệu của dòng phiên bản này nêu như sau:

| Backend | Servlet/MVC | WebFlux | Nhận xét |
| --- | --- | --- | --- |
| **Redis** | Có, session repository đồng bộ | Có, repository Redis reactive | Lựa chọn phổ biến khi nhiều replica cần chia sẻ phiên, có TTL và độ trễ thấp |
| **JDBC/SQL** | Có, `spring-session-jdbc` | Không có auto-configured reactive JDBC session repository | Phù hợp khi đã vận hành RDBMS và quy mô vừa phải; chú ý SQL connection pool |
| **MongoDB** | Có, khi có module/điều kiện đúng phiên bản | Có, reactive Mongo repository trong dòng hỗ trợ | Phù hợp nếu đã dùng Mongo, phải kiểm tra chỉ mục và expiry |
| **Hazelcast** | Có trong dòng Boot 3.3 khi module phù hợp | Không phải lựa chọn reactive auto-config của Boot 3.3 | Cân nhắc khi hệ thống sẵn dùng data grid |
| **Map in-memory** | Có trong Spring Session core | Có bản reactive cho demo | Dữ liệu mất khi restart, không tự chia sẻ nhiều instance |
| **Apache Geode (tích hợp riêng)** | Tùy module/tích hợp | Không mặc định | Chỉ cân nhắc khi hệ thống đang sử dụng và version tương thích |

**Lưu ý về phiên bản:** tài liệu Spring Boot 3.3/3.4 có nhiều lựa chọn hơn tài liệu của các dòng Boot mới. Không mặc định rằng mọi store trong bảng đều được auto-configure bởi **tất cả** phiên bản Boot hoặc dùng cùng tên starter. Phải xác nhận matrix hỗ trợ cho đúng Spring Boot và Spring Session dependency đang chạy.

**Quy tắc chọn đơn giản:**

1. **Đầu tiên xác định web stack**: MVC/Servlet hay WebFlux thực sự.
2. **Chọn loại repository**: `SessionRepository` đồng bộ cho MVC, `ReactiveSessionRepository` cho WebFlux.
3. **Chọn data store có adapter và driver tương thích**: Redis cho cả hai; JDBC chỉ trong hướng Servlet thông thường.
4. **Xét hệ vận hành**: cơ sở hạ tầng Redis/Mongo/SQL hiện có, ràng buộc latency, quota, eviction, failover, cleanup, metrics và sao lưu.
5. **Xét yêu cầu tính năng**: tra phiên theo principal, session events, session invalidation hàng loạt, bảo mật và serialization. Indexed repository đôi khi cần thiết, nhưng tăng chi phí/config.

Không có quy tắc “Redis luôn nhanh nhất” hay “JDBC luôn an toàn nhất” cho mọi workload. Redis chịu mạng/TTL/eviction; JDBC chịu khóa/transaction, query và connection pool; Mongo chịu index và TTL cleanup. Mỗi lựa chọn phải được đo dưới tải thật.

## 5. Khi chưa cần Spring Session

Một ứng dụng demo chạy một instance có thể dùng mặc định `HttpSession` (MVC) hoặc `WebSession` (WebFlux) và kho local của framework. Nếu chỉ cần một vài session không cần qua restart hay scale, Spring Session thêm hạ tầng có thể chưa đáng.

Ngược lại, các nhu cầu sau thường là lý do cân nhắc Spring Session:

- Nhiều replica phải đọc cùng dữ liệu phiên khi load balancer phân phối request giữa các instance.
- Cần session sống qua việc restart/replace một instance, tùy cơ chế durability của kho phiên.
- Muốn quản lý và đo session thống nhất, tách khỏi cấu hình cụ thể của Tomcat/Netty.
- Muốn tích hợp với Spring Security session management, kiểm soát đồng thời hoặc tra cứu phiên theo người dùng khi repository hỗ trợ index tương ứng.

**API stateless** dùng access token tự xác minh, không có nhu cầu lưu server-side session, có thể **không cần** Spring Session. Đừng cài Spring Session chỉ vì dự án dùng Spring Security: xác thực stateless và stateful là hai quyết định kiến trúc riêng.

## 6. Lifecycle của một phiên phân tán

Một request có session thường đi qua các pha:

~~~text
Request có cookie session ID (hoặc chưa có)
       |
       v
Đọc session từ repository
       |
       +-- ID không có / đã hết hạn -> tạo phiên mới khi ứng dụng cần
       |
       '-- ID hợp lệ -> lấy attributes và metadata
       |
       v
Controller/service đọc/ghi attributes
       |
       v
Lưu thay đổi + lastAccessedTime theo save/flush policy
       |
       v
Gửi response + cookie nếu cần
       |
       v
Idle timeout / logout / invalidation -> session không còn hợp lệ
       |
       v
Backend cleanup/TTL xóa dữ liệu còn lại theo cơ chế riêng
~~~

**Một chi tiết về hiệu năng:** cập nhật `lastAccessedTime`, thay đổi attribute hoặc chính sách save/flush có thể tạo I/O tới kho phiên mỗi request. Với hệ thống RPS lớn, lưu session ở backend từ xa nghĩa là **tăng dependency** và tải mạng/DB, không phải thao tác hoàn toàn miễn phí.

Không giả định một session luôn được ghi đúng **một lần** cho mỗi HTTP request: các loại repository và `FlushMode`, `SaveMode` có thể quyết định tần suất ghi khác nhau. Khi có nhiều request song song từ một browser, phải cân nhắc **race condition** và lost update trên cùng attribute. Ví dụ bộ đếm tăng trong session không phải bộ đếm phân tán atomic.

### 6.1. Một session ID không nói lên dữ liệu có cùng cách serialize

Hai ứng dụng cùng Redis vẫn có thể không đọc được session của nhau nếu:

- Namespace hoặc cookie name khác nhau; session ID từ ứng dụng A trỏ tới namespace không tồn tại ở B.
- Serializer khác nhau (Java serialization và JSON, kiểu class, package name, serialVersionUID).
- Hai framework/version có schema session không tương thích hoặc khác mô hình attributes/security context.
- Cookie `Domain`, `Path`, `Secure` hoặc `SameSite` khiến browser không gửi ID như mong muốn.

Đặc biệt, **không tự giả định MVC và WebFlux chia sẻ session được chỉ vì cùng dùng Redis**. Hai stack có abstraction và dữ liệu được lưu khác nhau; việc liên thông cần được thiết kế, test serialization/cookie/principal, và có thể cần giải pháp SSO/OIDC thay vì chia sẻ trực tiếp session attributes.

## 7. Lab A — Spring MVC + Spring Session JDBC (Java 17+)

Lab A trình bày repository **đồng bộ** trên SQL. Dùng H2 **in-memory** để không cần database riêng khi học. H2 mất toàn bộ dữ liệu khi ứng dụng dừng; đây **không phải** lời hứa persistence sau restart. Nếu cần nhiều replica chung dữ liệu, chuyển sang PostgreSQL/MySQL được cấu hình và migrate schema đúng cách.

### 7.1. Cấu trúc dự án

~~~text
mvc-session-jdbc/
├── pom.xml
└── src/main/
    ├── java/com/example/mvcsession/
    │   ├── MvcSessionApplication.java
    │   └── VisitController.java
    └── resources/
        └── application.properties
~~~

**Tệp `pom.xml`** (Spring Boot 3.3.5; các dependency được quản lý phiên bản bởi parent):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mvc-session-jdbc</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.session</groupId>
            <artifactId>spring-session-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-web` kích hoạt MVC/embedded Tomcat. `spring-boot-starter-jdbc` cung cấp `DataSource` và JDBC infrastructure, `spring-session-jdbc` cung cấp session repository SQL, H2 làm database lab. Không cần thêm `spring-boot-starter-webflux`, vì bài này kiểm tra `HttpSession`.

**Tệp `src/main/resources/application.properties`:**

~~~properties
server.port=8081

spring.datasource.url=jdbc:h2:mem:sessiondemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.session.timeout=20m
spring.session.jdbc.initialize-schema=always
~~~

`spring.session.jdbc.initialize-schema=always` chỉ hợp lý trong lab H2. Trong production, quản lý schema `SPRING_SESSION` và `SPRING_SESSION_ATTRIBUTES` bằng migration tool/quy trình DBA, tránh tự khởi tạo lại bất ngờ khi triển khai. Tên bảng mặc định và chi tiết DDL cần xem đúng dialect/version.

**Tệp `src/main/java/com/example/mvcsession/MvcSessionApplication.java`:**

~~~java
package com.example.mvcsession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcSessionApplication.class, args);
    }
}
~~~

**Tệp `src/main/java/com/example/mvcsession/VisitController.java`:**

~~~java
package com.example.mvcsession;

import java.util.Map;

import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VisitController {

    @GetMapping("/counter")
    public Map<String, Object> counter(HttpSession session) {
        Object stored = session.getAttribute("visits");
        int previous = stored instanceof Integer n ? n : 0;
        int current = previous + 1;
        session.setAttribute("visits", current);

        return Map.of(
                "visits", current,
                "sessionId", session.getId()
        );
    }

    @PostMapping("/reset")
    public Map<String, String> reset(HttpSession session) {
        session.invalidate();
        return Map.of("status", "invalidated");
    }
}
~~~

Đây là **một controller hoạt động với Spring MVC**. Bạn vẫn dùng `jakarta.servlet.http.HttpSession`, không gọi trực tiếp SQL trong controller. Spring Session và Boot liên kết repository JDBC vào lớp session của request.

`visits` là `Integer` nên dễ lưu theo cơ chế serialization của repository. Không ghi `Connection`, `EntityManager`, `HttpServletRequest` hoặc object phụ thuộc request/thread vào session. Bộ đếm này là **demo tuần tự**, không đảm bảo chính xác dưới nhiều request song song vào cùng một session.

### 7.2. Chạy và kiểm tra

Tại thư mục gốc của dự án đã tạo, với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Trong terminal thứ hai, lưu cookie vào file:

~~~bash
curl -i -c mvc-cookies.txt http://localhost:8081/counter
curl -i -b mvc-cookies.txt -c mvc-cookies.txt http://localhost:8081/counter
curl -i -b mvc-cookies.txt -c mvc-cookies.txt http://localhost:8081/counter
~~~

Kỳ vọng các response JSON cùng phiên có `visits` lần lượt **1, 2, 3**; `sessionId` là chuỗi sinh động, nên không có giá trị cố định để sao chép. Phản hồi đầu thường có `Set-Cookie` tương ứng session; những lần sau client gửi cookie từ file. Giá trị cookie có thể được mã hóa khác với chuỗi `sessionId` trả trong ví dụ; hãy so sánh sự liên tục của phiên thay vì đòi hai chuỗi byte giống hệt.

Thử invalidation (không dùng GET cho hành động thay đổi trạng thái):

~~~bash
curl -i -X POST -b mvc-cookies.txt -c mvc-cookies.txt http://localhost:8081/reset
curl -i -b mvc-cookies.txt -c mvc-cookies.txt http://localhost:8081/counter
~~~

Response `/reset` có body JSON:

~~~json
{"status":"invalidated"}
~~~

Lần gọi `/counter` kế tiếp sẽ tạo/ghi session mới và có `visits=1`. Để thử hoàn toàn không cookie, bỏ tùy chọn `-b` và dùng cookie jar mới hoặc gọi request trong client không mang cookie cũ.

**Hạn chế của lab A:** H2 chạy trong memory của **một JVM**. Mở thêm instance sẽ tạo database H2 khác, nên không thể dùng lab này để chứng minh hai replica chia sẻ session. Muốn kiểm chứng multi-instance với JDBC, cấu hình **cùng database SQL server thật**, cùng schema và session serialization tương thích.

## 8. Lab B — Spring WebFlux + Spring Session Redis reactive

Lab B dùng repository **reactive**. Khác lab A, controller nhận `WebSession` và không sử dụng `HttpSession`. Redis phải đang chạy trên `localhost:6379`; có thể dùng Docker hoặc Redis service đã cài.

### 8.1. Cấu trúc và dependencies

~~~text
webflux-session-redis/
├── pom.xml
└── src/main/
    ├── java/com/example/reactivesession/
    │   ├── ReactiveSessionApplication.java
    │   └── ReactiveVisitController.java
    └── resources/
        └── application.properties
~~~

**Tệp `pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-session-redis</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.session</groupId>
            <artifactId>spring-session-data-redis</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các dependency này cung cấp WebFlux, Redis reactive connection infrastructure (thường qua Lettuce) và Spring Session Data Redis; Boot 3.3 có thể auto-configure Redis-backed WebSession repository tương ứng. Không thêm `spring-session-jdbc` vào lab này. Trong Boot 3.3, các module `spring-session-data-redis` và `spring-session-jdbc` được khai báo trực tiếp như ví dụ; không dùng tên starter session mới của phiên bản Boot khác mà không đối chiếu.

**Tệp `src/main/resources/application.properties`:**

~~~properties
server.port=8082

spring.data.redis.host=localhost
spring.data.redis.port=6379
spring.session.timeout=20m
spring.session.redis.namespace=spring:session:webflux-lab
~~~

Namespace giúp các key session của lab không trộn với ứng dụng khác trên cùng Redis. Không lưu Redis password trong file mã nguồn khi dùng production; lấy qua secret manager/environment configuration.

Chạy Redis (nếu Docker có sẵn) trong một terminal riêng:

~~~bash
docker run --rm --name webflux-session-redis -p 6379:6379 redis:7-alpine
~~~

Lệnh chạy container foreground; ứng dụng Spring Boot chạy ở terminal khác. Nếu Redis local đã chiếm port 6379, hãy dùng server đó hoặc đổi cổng một cách nhất quán; không chạy hai server cùng port.

**Tệp `src/main/java/com/example/reactivesession/ReactiveSessionApplication.java`:**

~~~java
package com.example.reactivesession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSessionApplication.class, args);
    }
}
~~~

**Tệp `src/main/java/com/example/reactivesession/ReactiveVisitController.java`:**

~~~java
package com.example.reactivesession;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
public class ReactiveVisitController {

    @GetMapping("/counter")
    public Mono<Map<String, Object>> counter(WebSession session) {
        int previous = session.getAttributeOrDefault("visits", 0);
        int current = previous + 1;
        session.getAttributes().put("visits", current);

        return Mono.just(Map.of(
                "visits", current,
                "sessionId", session.getId()
        ));
    }

    @PostMapping("/reset")
    public Mono<Map<String, String>> reset(WebSession session) {
        return session.invalidate()
                .thenReturn(Map.of("status", "invalidated"));
    }
}
~~~

Ở đây:

- `WebSession` thuộc Spring WebFlux; framework giải quyết argument theo reactive request pipeline.
- Thao tác `getAttributes().put` đánh dấu session có nội dung để được lưu theo lifecycle WebFlux.
- `Mono.just(...)` biểu diễn payload response; Spring WebFlux và `WebSessionManager` phối hợp commit phiên khi xử lý response.
- `session.invalidate()` **trả `Mono<Void>`**, nên `thenReturn` chỉ trả response sau khi operation hoàn tất. Không gọi `block()` trên event-loop thread.
- Counter chỉ minh họa round-trip session; nhiều request cùng lúc có thể tranh chấp giá trị theo kiểu read-modify-write không atomic.

### 8.2. Chạy và kiểm tra

Từ thư mục project, sau khi Redis đã sẵn sàng:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl -i -c reactive-cookies.txt http://localhost:8082/counter
curl -i -b reactive-cookies.txt -c reactive-cookies.txt http://localhost:8082/counter
curl -i -b reactive-cookies.txt -c reactive-cookies.txt http://localhost:8082/counter
~~~

Kỳ vọng `visits` lần lượt **1, 2, 3** và cùng session ID logic. Nếu response đầu chưa đặt cookie hoặc request tiếp theo lại về 1, kiểm tra repository thực sự được auto-configure, Redis có kết nối, headers cookie, namespace và việc session đã được start/modified.

Reset:

~~~bash
curl -i -X POST -b reactive-cookies.txt -c reactive-cookies.txt http://localhost:8082/reset
curl -i -b reactive-cookies.txt -c reactive-cookies.txt http://localhost:8082/counter
~~~

Kỳ vọng response reset có `status=invalidated`; request counter tiếp theo khởi đầu `visits=1`. Dùng `curl.exe` thay `curl` khi PowerShell phiên bản cũ tạo alias không tương thích tham số.

### 8.3. Kiểm tra hai instance dùng chung Redis

Bạn có thể build JAR rồi chạy hai instance **từ hai terminal** (cùng Redis/namespace và cùng code):

~~~bash
mvn clean package
java -jar target/webflux-session-redis-0.0.1-SNAPSHOT.jar --server.port=8082
~~~

Trong terminal thứ hai:

~~~bash
java -jar target/webflux-session-redis-0.0.1-SNAPSHOT.jar --server.port=8083
~~~

Gửi cookie của lần gọi instance thứ nhất sang instance thứ hai:

~~~bash
curl -i -c shared-cookies.txt http://localhost:8082/counter
curl -i -b shared-cookies.txt -c shared-cookies.txt http://localhost:8083/counter
curl -i -b shared-cookies.txt -c shared-cookies.txt http://localhost:8082/counter
~~~

Trong trường hợp Redis hoạt động, ứng dụng cùng code/config và client giữ cookie hợp lệ, giá trị `visits` thường theo thứ tự **1 → 2 → 3**, dù request vào hai process khác nhau. Cookie HTTP không có scope theo **port**, nên hai port trên `localhost` có thể dùng cùng cookie theo domain/path/secure policy. Đừng dùng ví dụ hai port localhost để suy ra các domain production khác nhau tự chia sẻ cookie.

Nếu dùng cùng Redis nhưng đổi `spring.session.redis.namespace` giữa hai instance, kết quả có thể trở thành các session độc lập. Namespace là một phần của mô hình định danh session trong data store.

## 9. Lựa chọn Redis: default, indexed, TTL và sự kiện

Với Spring Session Data Redis, có sự khác nhau giữa repository Redis thông thường và repository **indexed**:

- **Default Redis repository**: phù hợp khi chủ yếu cần tìm session theo ID, tạo/lưu/xóa và hết hạn.
- **Indexed Redis repository**: bổ sung index và các khả năng liên quan tra session theo principal, sự kiện created/deleted/expired (tùy implementation/version); đổi lại cần xem cơ chế Redis keyspace notifications, cleanup và chi phí index.

Trong Spring Boot 3.3, property như sau được tài liệu liệt kê:

~~~properties
spring.session.redis.repository-type=default
# Hoặc chỉ khi ứng dụng thực sự cần indexing:
# spring.session.redis.repository-type=indexed
~~~

Không thêm cấu hình indexed chỉ vì tên nghe “đầy đủ hơn”. Nếu bạn có tính năng “logout mọi phiên của tài khoản”, quản lý concurrent sessions hay đóng kết nối WebSocket khi phiên bị xóa, cần kiểm tra repository có index/event phù hợp, chính sách principal và cấu hình Spring Security.

**Các lưu ý Redis vận hành:**

1. **Expiration:** TTL giúp session hết hạn, nhưng event xóa key không được đảm bảo xảy ra đúng từng giây; đừng dùng keyspace event như đồng hồ nghiệp vụ chính xác.
2. **Eviction:** Redis hết memory có thể xóa key sớm theo `maxmemory-policy`, khiến người dùng mất session trước thời gian timeout.
3. **Persistence và failover:** Redis chạy memory; khả năng khôi phục sau restart phụ thuộc cấu hình persistence/replication/managed service. Redis chia sẻ phiên không mặc nhiên đảm bảo không mất dữ liệu.
4. **Serialization:** attributes có thể dùng Java serialization mặc định; thay class/package/version không tương thích gây lỗi deserialize. Cần chuẩn hóa DTO nhỏ, serializer, namespace/versioning và chiến lược migrate.
5. **Network:** remote store gây thêm RTT; timeout/disconnect có thể khiến cả endpoint phụ thuộc session lỗi. Theo dõi latency Redis, connection pool và tình trạng failover.
6. **Namespace:** tách ứng dụng/test/prod khi dùng chung Redis; không dùng cùng namespace cho các ứng dụng không được thiết kế để chia sẻ session.
7. **Data minimization:** session chỉ nên chứa ID/trạng thái nhỏ, không lưu toàn bộ user object, cache database lớn hay secret/tokens nhạy cảm không cần thiết.

## 10. JDBC: schema, connection pool và cleanup

`spring-session-jdbc` dùng relational tables để lưu session metadata và attributes. Trong Spring Boot 3.3, `spring.session.jdbc.*` có các cấu hình ví dụ:

~~~properties
spring.session.timeout=20m
spring.session.jdbc.table-name=SPRING_SESSION
spring.session.jdbc.initialize-schema=embedded
# Tần suất dọn dữ liệu hết hạn tùy nhu cầu:
# spring.session.jdbc.cleanup-cron=0 * * * * *
~~~

`initialize-schema=embedded` chỉ khởi tạo tự động khi database được xem là embedded theo policy. Trong production, không dùng `initialize-schema=always` bừa bãi; quản lý schema bằng Flyway/Liquibase hoặc migration đã kiểm soát.

**Hiệu năng JDBC repository** phụ thuộc tốc độ SELECT/INSERT/UPDATE/DELETE session, indexing, transaction, HikariCP connection pool, latency DB và cleanup. Chọn `maximumPoolSize` và connection budget cho **tổng** tất cả replica. Nếu DB của nghiệp vụ đã gần bão hòa, chuyển session vào cùng DB có thể tạo contention đáng kể.

**Expired row khác expired session:** application có thể coi session hết hạn dựa vào metadata trước khi job dọn xóa rows. Không lấy số row `SPRING_SESSION` có mặt làm chỉ số “số người dùng online chính xác”.

**Không dùng JDBC repository để giải quyết WebFlux như thể nó là non-blocking.** `JdbcIndexedSessionRepository` truy cập JDBC theo cơ chế đồng bộ; nó không triển khai `ReactiveSessionRepository`. Nếu ứng dụng WebFlux buộc phải lưu session vào SQL, cần thiết kế adapter reactive thật phù hợp và đánh giá blocking/offloading, transaction, serialization và maintenance, thay vì chỉ thêm dependency JDBC rồi gọi `block()` ở controller.

## 11. MongoDB, Hazelcast và in-memory có vai trò gì?

**MongoDB:** trong dòng Spring Boot 3.3, có session integration cho Servlet và repository reactive cho WebFlux khi có module/driver tương ứng. Hợp khi nền tảng đã vận hành MongoDB, nhưng phải xét session document/index, TTL index, cleanup delay, write concern, schema/serializer, startup auto-config và phiên bản Mongo driver. Việc Spring Data Mongo “reactive” không tự bảo đảm Spring Session repository tương thích nếu thiếu đúng module.

**Hazelcast:** có thể là lựa chọn cho Servlet trong dòng Boot 3.3 khi tổ chức đã có data grid. Không coi việc có Hazelcast client trong WebFlux là bằng chứng có session repository reactive auto-configured. Cần đánh giá topology, expiration, cluster discovery và HA.

**MapSessionRepository / ReactiveMapSessionRepository:** hữu ích cho test, demo hoặc ứng dụng local giản đơn. Một map trong memory không có durability, replication hoặc TTL cleanup tự động đầy đủ như dịch vụ chuyên dụng nếu không tự cấu hình. **Không dùng map repository local làm bằng chứng cho clustered session**.

**Tính di động:** Spring Session chuẩn hóa API ở phía ứng dụng, nhưng không khiến dữ liệu của các backend tự chuyển đổi. Chuyển JDBC sang Redis thường yêu cầu policy migration và có thể khiến những session cũ mất hiệu lực; phải chuẩn bị phương án triển khai, cookie và thông báo người dùng tương ứng.

## 12. Những chỗ dễ chọn nhầm stack

### 12.1. Có cả spring-boot-starter-web và spring-boot-starter-webflux

Với Boot 3.3 trong cấu hình thông thường, nếu **cả hai** starter nằm trên classpath, Boot mặc định chọn **Servlet Web Application** để hỗ trợ những tình huống dùng `WebClient` cùng MVC. Không được nhìn thấy Reactor dependency rồi suy ra repository reactive WebSession đã được dùng.

Hãy xác nhận bằng startup logs, `WebApplicationType` và các bean/handler đang active. Khi muốn ứng dụng WebFlux thuần, giữ starter `spring-boot-starter-webflux` và không đưa MVC vào classpath ngoài ý định; khi thực sự cần chọn stack theo cấu hình, nghiên cứu `spring.main.web-application-type` với toàn bộ dependency phù hợp.

### 12.2. Dùng HttpSession trong WebFlux

`HttpSession` là Servlet API; WebFlux handler dùng `WebSession`. Một container Tomcat có thể chạy reactive adapter nhưng không biến `HttpSession` thành WebFlux session chuẩn.

### 12.3. Dùng Redis JDBC driver hoặc RedisTemplate “reactive” không đồng bộ loại

Một thư viện lưu dữ liệu có thể hỗ trợ cả blocking lẫn reactive. Nhưng phải hỏi **Spring Session đang inject loại repository nào**. Nếu WebFlux không tìm được `ReactiveSessionRepository`, việc bổ sung `SessionRepository` đồng bộ không tự làm Spring Session reactive lưu trữ bên ngoài.

### 12.4. Tự thêm @EnableRedisHttpSession / @EnableRedisWebSession khi Boot đã auto-configure

Các annotation này dùng khi bạn chủ động cấu hình Spring Session, nhưng trong ứng dụng Spring Boot có auto-configuration phù hợp thường **không cần thêm**. Khi bạn tự dùng `@Enable*HttpSession` hoặc `@Enable*WebSession`, Boot có thể back off; property và bean tùy biến có thể hoạt động khác bạn tưởng. Giữ một cách cấu hình nhất quán và kiểm tra loại bean được tạo.

### 12.5. Nhầm cookie name, path hoặc hostname

`SESSION` và `JSESSIONID` không phải lúc nào giống nhau. Đừng hardcode tên cookie nếu chưa kiểm tra `Set-Cookie` thực tế và version/config. Cookie bị ràng buộc bởi domain/path/SameSite/Secure, không bởi port. Một redirect qua domain khác, HTTPS proxy hoặc base path thay đổi có thể khiến browser không gửi cookie, dẫn đến session mới.

## 13. Session, Spring Security và an toàn hệ thống

Spring Session không thay thế authentication/authorization. Nếu dùng Spring Security:

- **Session fixation:** sau khi đăng nhập, thông thường cần đổi/rotate session ID; Spring Security có cơ chế bảo vệ session fixation trong ngữ cảnh tương ứng. Với Servlet, có API `HttpServletRequest.changeSessionId()`; với WebFlux, `WebSession.changeSessionId()` trả publisher để compose.
- **Cookie:** dùng HTTPS, `Secure`, `HttpOnly` và `SameSite` theo bối cảnh; không set `Secure=true` trong lab chỉ dùng HTTP rồi tưởng cookie vẫn hoạt động như HTTPS. Reverse proxy phải truyền đúng thông tin scheme/forwarded headers.
- **CSRF:** ứng dụng stateful dựa trên cookie cần đánh giá bảo vệ CSRF cho request thay đổi trạng thái, nhất là khi tích hợp Spring Security. `SameSite` là một lớp giảm rủi ro, không phải thay thế vô điều kiện cho CSRF protection.
- **Authorization:** session có thể chứa user ID, nhưng mỗi thao tác với dữ liệu nhạy cảm vẫn cần phân quyền. Đừng tin các attributes chưa được xác thực.
- **Session ID:** coi như bearer credential. Không log session ID thô, không nhúng nó vào URL hoặc chia sẻ qua analytics/Referer; tránh session hijacking.
- **Logout/invalidation:** ngoài xóa cookie, phải làm mất hiệu lực phiên lưu server; nếu dùng nhiều loại token hoặc SSO, logout có thể cần thêm bước.
- **Timeout:** đặt thời hạn không hoạt động phù hợp rủi ro và trải nghiệm; sự kiện expire/cleanup có thể bất đồng bộ, không dùng làm đồng hồ xác thực chính xác.
- **Serialization:** chỉ lưu dữ liệu cần thiết; tránh lưu password, private key, object chứa resource handle hoặc dữ liệu cá nhân quá mức.

Các property cookie trong Boot 3.3 được chia theo stack: servlet dùng nhóm `server.servlet.session.cookie.*`; reactive có nhóm `server.reactive.session.cookie.*`. Spring Session cũng có cách tùy biến cookie serializer/resolver. **Kiểm tra cấu hình được áp dụng thực tế** khi Spring Session tham gia, không suy ra mọi property của container đều mặc nhiên điều khiển cookie do Spring Session phát hành.

## 14. Các lỗi thường gặp và cách kiểm tra

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Lần nào gọi `/counter` cũng là 1 | Không gửi cookie, cookie bị chặn, session không được lưu, namespace sai | Xem `Set-Cookie`/`Cookie`, cookie jar, repository và Redis/SQL |
| MVC JDBC chạy, WebFlux JDBC không khởi tạo session repository reactive | `spring-session-jdbc` là adapter đồng bộ | Chọn Redis/Mongo reactive hoặc adapter được hỗ trợ cho WebFlux |
| Dùng Redis nhưng session mất sau restart Redis | Persistence/eviction/TTL hoặc Redis failover | Xem Redis config, TTL, maxmemory-policy, durability |
| Hai replica không chia sẻ session | Khác backend/namespace/serializer hoặc cookie domain/path | So cấu hình hai instance, chứng minh read/write cùng key store |
| Lỗi deserialize attribute sau deploy | Class/schema/serializer không tương thích giữa phiên bản | Dùng DTO nhỏ, versioning và chính sách migration |
| MVC trả 500 khi truy vấn session | DB down, connection pool cạn, schema chưa có | Kiểm tra `SPRING_SESSION` tables, Hikari, SQL logs và timeout |
| WebFlux latency cao dù CPU thấp | Blocking call `block()` hoặc dependency remote session chậm | Kiểm tra event-loop stack/trace, Redis latency và boundedElastic |
| Cookie không được gửi sau reverse proxy HTTPS | `Secure`/`SameSite`/domain/path hoặc forwarded scheme sai | Xem browser Network, proxy headers và cookie flags |
| Dữ liệu phiên tồn tại sau idle timeout trong DB | Cleanup job chưa xóa row vật lý | Kiểm tra metadata expiration, cleanup schedule, không chỉ row count |
| Tra session theo principal không hoạt động | Dùng repository không có index hoặc principal index chưa cấu hình | Chọn indexed repository phù hợp và cấu hình Spring Security/events |
| Sau logout vẫn giữ session cũ ở client | Chưa invalidate phía server hoặc vẫn còn cookie/token khác | Kiểm tra server-side invalidation và cookie clearing |
| Thêm cả Web và WebFlux rồi Session hoạt động khác tưởng tượng | Boot chọn Servlet application type | Xác định stack thật từ startup và dependency tree |

**Quy trình debug theo tầng:**

1. **HTTP:** dùng DevTools hoặc `curl -i -c jar -b jar` xác nhận request sau có gửi cookie gì, path/domain/secure có khớp.
2. **Web stack:** MVC nhận `HttpSession` hay WebFlux nhận `WebSession`? Boot đã active auto-config nào?
3. **Repository:** bean `SessionRepository` hay `ReactiveSessionRepository` thực sự có mặt? Backend nào được chọn?
4. **Data store:** xác nhận kết nối, namespace/key/table, serializer, TTL và lỗi timeout.
5. **Ứng dụng:** kiểm tra chỗ cập nhật attributes, logout, session fixation protection và redirect.
6. **Đa instance:** chạy cùng code/config trên hai port/replica, dùng một cookie jar để chứng minh continuity; tránh dùng sticky load balancing khiến test không thực sự chuyển instance.

## 15. Tính năng nào cần indexed repository?

Không phải repository nào cũng có truy vấn thứ cấp và lifecycle events giống nhau. `FindByIndexNameSessionRepository` (đồng bộ) và các indexed repository khác có thể hỗ trợ tìm session theo principal; reactive indexed implementation có API tương ứng khi được version hỗ trợ.

Các tính năng thường cần xem xét:

- Danh sách các session đăng nhập của một người dùng để cho phép “đăng xuất các thiết bị khác”.
- Giới hạn số phiên đồng thời của một tài khoản.
- Nhận sự kiện session deleted/expired để đóng hoặc dọn resource liên quan.
- Phân tích vòng đời phiên theo người dùng mà vẫn bảo vệ dữ liệu cá nhân.

**Giới hạn thực tế:**

- Session event từ Redis có thể phụ thuộc keyspace notifications và không bảo đảm delivery chính xác như event log bền vững.
- Repository mặc định không cung cấp mọi index; thêm thuộc tính `username` vào map session không tự tạo principal index tìm được.
- Khi dùng Spring Security, phải bảo đảm principal và security context được lưu theo cơ chế hỗ trợ tương thích.
- Logout all sessions là một nghiệp vụ bảo mật: còn tùy token ngoài session, cache, WebSocket, đồng bộ và trạng thái phát hành cookie.

## 16. Bài tập và tình huống chọn kho

**Câu 1.** Ứng dụng Spring MVC chạy bốn replica, đã có PostgreSQL và không muốn vận hành Redis. Nên cân nhắc repository nào? Có thể dùng H2 in-memory riêng từng replica không?

**Câu 2.** API reactive WebFlux dùng `WebSession`, đã có Redis và rất nhiều request I/O. Chọn `spring-session-jdbc` hay `spring-session-data-redis`? Tại sao?

**Câu 3.** Một đội vừa thêm `spring-boot-starter-webflux` vào ứng dụng vốn có `spring-boot-starter-web` để dùng `WebClient`. Có được tự kết luận repository WebSession reactive sẽ được auto-configure không?

**Câu 4.** Hai instance WebFlux trên `localhost:8082` và `localhost:8083` dùng Redis chung. Cookie jar mang session ID đúng nhưng `visits` trở về 1 ở instance thứ hai. Cần kiểm tra ba yếu tố nào?

**Câu 5.** Vừa đổi `spring.session.timeout=20m` nhưng thấy row trong SQL còn sau 21 phút. Điều đó có chứng minh phiên vẫn hợp lệ không?

**Câu 6.** Tại sao không đưa nguyên `UserEntity` (chứa collection lười tải, connection hoặc field nhạy cảm) vào session Redis, mà nên giữ một ID/DTO nhỏ?

**Câu 7.** Một người dùng mở hai tab và gửi hai request tăng `visits` cùng lúc. Kết quả cuối có nhất định tăng 2 không? Nếu cần đếm chính xác, nên lưu ở đâu?

**Câu 8.** Khi triển khai chức năng “đăng xuất mọi thiết bị”, vì sao chỉ lưu attributes trong Redis default repository có thể chưa đủ?

**Đáp án định hướng:**

1. `spring-session-jdbc` với `SessionRepository` cho Servlet; dùng PostgreSQL chung, schema/cleanup/connection pool phù hợp. H2 memory riêng từng instance không chia sẻ dữ liệu.
2. Redis repository **reactive** với `ReactiveSessionRepository`; Spring Session JDBC không cung cấp reactive adapter tương đương trong cấu hình này.
3. Không. Spring Boot thông thường ưu tiên Servlet khi cả MVC và WebFlux có trên classpath; phải xác nhận `WebApplicationType` và bean.
4. Kiểm tra cookie domain/path và việc gửi cookie; Redis namespace/backend/TTL; serializer/session schema hoặc khác config/app instance.
5. Không. Expiration logic và vật lý cleanup có thể khác thời điểm; phải kiểm tra hiệu lực lookup/session metadata.
6. Giảm kích thước/chi phí serialization, tránh lỗi version/class và lộ dữ liệu, giảm coupling tới persistence domain.
7. Không, read-modify-write trên session không mặc nhiên atomic dưới concurrency. Dùng kho dữ liệu/operation atomic thích hợp khi nghiệp vụ cần bộ đếm chính xác.
8. Cần truy vấn theo principal/session index và invalidation đầy đủ, có thể cần indexed repository cùng chính sách auth/token.

## 17. Kết luận kỹ thuật

- **Spring Session là lớp quản lý phiên server-side**, không phải thuật toán authentication và không biến cookie ID thành JWT.
- **Servlet MVC:** API `HttpSession`, tích hợp `SessionRepositoryFilter` và repository **`SessionRepository`** đồng bộ; Redis/JDBC là hai lựa chọn phổ biến.
- **Spring WebFlux:** API `WebSession`, tích hợp `WebSessionManager` và **`ReactiveSessionRepository`**; Redis reactive là ví dụ điển hình, Mongo reactive cũng được hỗ trợ trong dòng Boot 3.3 phù hợp.
- **Không trộn adapter**: `spring-session-jdbc` không tự cung cấp ReactiveSessionRepository, Spring Data R2DBC không tự tạo Spring Session R2DBC repository.
- **Chọn kho dựa trên nhu cầu**: scale, failover, TTL, index/session events, serialization, cookie, security, performance và độ phức tạp vận hành.
- **Đo thực tế** bằng cookie jar qua nhiều request/instance và kiểm tra repository, không chỉ xem server trả `200`.
- **Giữ session nhỏ và có kiểm soát**; tính thêm network/DB latency, timeout, concurrency và kế hoạch migration khi đổi phiên bản.

## 18. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Common Application Properties (Spring Session, Redis, JDBC, Servlet/Reactive session settings): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Spring Session (trong Web reference bản 3.3): https://docs.spring.io/spring-boot/docs/3.3.5/reference/htmlsingle/
- Spring Session 3.3 — HttpSession Integration: https://docs.spring.io/spring-session/reference/3.3/http-session.html
- Spring Session 3.3 — WebSession Integration: https://docs.spring.io/spring-session/reference/3.3/web-session.html
- Spring Session 3.3 — JDBC/Spring Boot Guide: https://docs.spring.io/spring-session/reference/3.3/guides/boot-jdbc.html
- Spring Session 3.3 — Redis/Spring Boot Guide: https://docs.spring.io/spring-session/reference/3.3/guides/boot-redis.html
- Spring Session 3.3 — Reactive Redis Indexed Session: https://docs.spring.io/spring-session/reference/3.3/configuration/reactive-redis-indexed.html
- Spring Session APIs (SessionRepository, ReactiveSessionRepository, CookieSerializer): https://docs.spring.io/spring-session/reference/api.html
