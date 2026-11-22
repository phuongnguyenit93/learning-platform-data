# AuthorizationEventPublisher và SpringAuthorizationEventPublisher

> Chủ đề: **Spring Security – authorization**, nhóm **Sự kiện và audit**. Bài học tập trung vào API xuất bản **sự kiện phân quyền** khi `AuthorizationManager` đưa ra quyết định, cách kích hoạt `SpringAuthorizationEventPublisher`, cách lắng nghe, kiểm thử và sử dụng dữ liệu sự kiện đúng giới hạn. Ví dụ chạy với **Java 17, Spring Boot 3.5.6 và Spring Security 6.5.x** (Servlet/Spring MVC). Khác biệt API của Spring Security 7.x được ghi rõ riêng ở cuối bài.

## 1. Vì sao cần sự kiện phân quyền?

Hệ thống có đường dẫn `GET /api/management/report` yêu cầu vai trò `MANAGER`. Người dùng `analyst` đã đăng nhập nhưng chỉ có `ROLE_ANALYST`: yêu cầu bị từ chối. HTTP client cần nhận **403 Forbidden**; đội vận hành còn cần biết đã có **một quyết định từ chối quyền** để phục vụ theo dõi hoặc kiểm toán. Đó là hai trách nhiệm khác nhau:

- **AuthorizationManager** kiểm tra quyền và tạo kết quả cho phép/từ chối.
- **AuthorizationEventPublisher** là hợp đồng đưa kết quả phân quyền ra cơ chế sự kiện. Nó không tự cấp quyền, không kiểm tra mật khẩu và không quyết định HTTP status.
- **SpringAuthorizationEventPublisher** là implementation sẵn có sử dụng **Spring `ApplicationEventPublisher`** để phát sự kiện tới các listener như `@EventListener`.
- **ExceptionTranslationFilter / AccessDeniedHandler / AuthenticationEntryPoint** xử lý đường đi lỗi bảo mật thành phản hồi HTTP phù hợp. Sự kiện authorization không thay thế chúng.

Khi có khả năng quan sát quyết định từ chối, ứng dụng có thể đo số lần bị từ chối tại một nhóm tài nguyên, phát hiện cấu hình role sai, gắn trace ID cho request hoặc gửi bản ghi audit đã làm sạch tới hệ thống bên ngoài.

**Lưu ý:** Một `AuthorizationDeniedEvent` chỉ nói rằng *một lần kiểm tra quyền* đã bị từ chối. Nó **không bảo đảm** client sẽ thấy HTTP 403: caller chưa xác thực có thể nhận 401/chuyển trang đăng nhập; ngược lại, HTTP 403 do CSRF hay thành phần khác có thể không tạo `AuthorizationDeniedEvent` tương ứng.

## 2. Phân biệt hai API trọng tâm

### 2.1. `AuthorizationEventPublisher` — hợp đồng phát sự kiện

Package: `org.springframework.security.authorization`. Ý nghĩa của phương thức công bố sự kiện theo API hiện đại:

```java
// Dạng chữ ký khái niệm của API AuthorizationResult.
// Trong Spring Security 6.5, đây là overload mặc định; API cũ
// nhận AuthorizationDecision vẫn tồn tại nhưng đã deprecated.
<T> void publishAuthorizationEvent(
    Supplier<Authentication> authentication,
    T object,
    AuthorizationResult result
);
```

Ba đầu vào:

| Đầu vào | Ý nghĩa thực tế | Điểm cần chú ý |
|---|---|---|
| `Supplier<Authentication> authentication` | Cách lấy thông tin caller khi cần | Supplier có thể trì hoãn truy xuất SecurityContext. Không giữ supplier lại để dùng sau request hoặc trên thread khác |
| `T object` | Đối tượng đang được bảo vệ | Ở request authorization thường là `HttpServletRequest`; ở method security có thể là lời gọi method. Đừng mặc định mọi event đều là HTTP |
| `AuthorizationResult result` | Kết quả kiểm tra, có `isGranted()` | `true`: cho phép; `false`: từ chối. Nếu không có quyết định (`null`/abstain trong nhánh hỗ trợ), không được mặc định phát một sự kiện từ chối |

`AuthorizationEventPublisher` là **điểm mở rộng** để thay đổi *cách phát hoặc lọc sự kiện*, trong khi policy vẫn nằm ở `AuthorizationManager`. Hợp đồng không hứa giao sự kiện bền vững, thứ tự toàn cục, hoặc giao đúng một lần đến hệ thống ngoài.

**Lưu ý phiên bản:** Spring Security **6.5** còn chữ ký abstract cũ nhận `AuthorizationDecision` và overload mặc định nhận `AuthorizationResult`; chữ ký cũ đã bị đánh dấu deprecated. Spring Security **7.x** tập trung vào chữ ký nhận `AuthorizationResult`. Khi tự triển khai interface, phải đối chiếu chữ ký đúng phiên bản trên classpath; không chép implementation 7.x nguyên xi vào 6.5.

### 2.2. `SpringAuthorizationEventPublisher` — adapter vào Spring Events

Đây là implementation `final`, được cấp `ApplicationEventPublisher` của Spring thông qua constructor. Mặc định nó phát **`AuthorizationDeniedEvent`** khi kết quả bị từ chối, còn **không phát `AuthorizationGrantedEvent` cho mọi lần thành công**, vì số lượng sự kiện thành công có thể rất lớn. Đây là hành vi có chủ ý nhằm tránh ngập log hoặc hệ thống audit.

Đối tượng event thuộc package `org.springframework.security.authorization.event`:

- `AuthorizationDeniedEvent<T>`: một quyết định bị từ chối.
- `AuthorizationGrantedEvent<T>`: một quyết định được chấp thuận, chỉ thấy nếu publisher/cấu hình phù hợp có phát.
- Cả hai có các thông tin qua `getAuthentication()` (trả về supplier), `getObject()` và `getAuthorizationResult()`. Với kết quả `AuthorizationResult`, `isGranted()` biểu diễn quyết định.

**Tên lớp dễ nhầm:** `AuthenticationEventPublisher` và `DefaultAuthenticationEventPublisher` liên quan **đăng nhập/xác thực thành công hoặc thất bại**. Chúng khác hoàn toàn `AuthorizationEventPublisher` và `SpringAuthorizationEventPublisher` liên quan **quyền truy cập**.

## 3. Luồng sự kiện trên Spring Security Servlet

```text
Request GET /api/management/report
       |
       v
SecurityFilterChain
       |
       +--> Authentication filter: thiết lập Authentication phù hợp
       |
       +--> ExceptionTranslationFilter
                 |
                 v
            AuthorizationFilter
                 |
                 +--> AuthorizationManager kiểm tra ROLE_MANAGER
                 |         |
                 |         +--> AuthorizationResult (granted=false)
                 |
                 +--> AuthorizationEventPublisher
                 |         |
                 |         +--> SpringAuthorizationEventPublisher
                 |                   |
                 |                   +--> ApplicationEventPublisher
                 |                            |
                 |                            +--> @EventListener nhận AuthorizationDeniedEvent
                 |
                 +--> ném AccessDeniedException
                               |
                               v
                         ExceptionTranslationFilter
                               |
                               +--> AccessDeniedHandler (đã xác thực) --> 403
                               +--> AuthenticationEntryPoint (cần xác thực) --> 401/redirect
```

Có một số chi tiết quan trọng:

1. `AuthorizationFilter` sử dụng `AuthorizationManager` từ `authorizeHttpRequests`. Nếu từ chối, nó có thể **phát event rồi ném ngoại lệ**, cho nên listener nhận event không đồng nghĩa request đã kết thúc.
2. `ExceptionTranslationFilter` phản hồi HTTP theo trạng thái xác thực; **event publisher không chọn 401 hay 403**.
3. Event thường được chuyển tới listener trong cùng luồng khi dùng `ApplicationEventMulticaster` mặc định đồng bộ. Nếu ứng dụng tự cấu hình bất đồng bộ, thời điểm và SecurityContext có thể khác.
4. Một request có thể kích hoạt **nhiều lần kiểm tra** (request, method, dispatch `ERROR`/`FORWARD`), nên số lượng event không nhất thiết bằng số lượng HTTP requests.
5. Không phải mọi cơ chế bảo mật/đoạn mã tự viết đều xuất bản qua `AuthorizationEventPublisher`. Ví dụ custom filter tự `sendError(403)` thì listener của publisher không tự động biết việc này.

## 4. Ví dụ chạy được: nhận event khi thiếu ROLE_MANAGER

Ta xây dựng API nhỏ với hai tài khoản lưu trong bộ nhớ để dễ kiểm thử. HTTP Basic và `{noop}` trong ví dụ chỉ phục vụ học tập; hệ thống thực tế phải dùng lưu mật khẩu được mã hóa, quản lý danh tính và vận chuyển qua HTTPS.

### 4.1. Cấu trúc dự án

```text
authorization-events-demo/
├── pom.xml
├── src/main/java/com/example/authzevents/
│   ├── AuthorizationEventsApplication.java
│   ├── SecurityConfig.java
│   ├── ReportController.java
│   └── AuthorizationAuditListener.java
└── src/test/java/com/example/authzevents/
    └── AuthorizationEventsTest.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>authorization-events-demo</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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
```

Starter Web cung cấp Spring MVC và logging; Starter Security cung cấp Spring Security; hai dependency `test` dùng JUnit/MockMvc và test support của Spring Security.

### 4.2. Entry point

`src/main/java/com/example/authzevents/AuthorizationEventsApplication.java`:

```java
package com.example.authzevents;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationEventsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationEventsApplication.class, args);
    }
}
```

### 4.3. Bean phát sự kiện và rule truy cập

`src/main/java/com/example/authzevents/SecurityConfig.java`:

```java
package com.example.authzevents;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher springEvents) {
        return new SpringAuthorizationEventPublisher(springEvents);
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/management/**").hasRole("MANAGER")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        var analyst = User.withUsername("analyst")
            .password("{noop}analyst123")
            .roles("ANALYST")
            .build();
        var manager = User.withUsername("manager")
            .password("{noop}manager123")
            .roles("MANAGER")
            .build();
        return new InMemoryUserDetailsManager(analyst, manager);
    }
}
```

**Tại sao chỉ cần bean `AuthorizationEventPublisher`?** Trong cấu hình Spring Security dùng `AuthorizationManager` hiện đại, Spring Security có thể lấy bean publisher từ application context và gắn vào thành phần authorization tương ứng. Khi quyết định bị từ chối và thành phần đó có phát event, `SpringAuthorizationEventPublisher` chuyển nó sang Spring event infrastructure. Không cần gọi publisher thủ công từ controller.

- `hasRole("MANAGER")` tìm `ROLE_MANAGER` theo tiền tố mặc định.
- `User.roles("MANAGER")` tạo authority phù hợp; `analyst` chỉ có `ROLE_ANALYST`.
- `.anyRequest().authenticated()` yêu cầu xác thực với các đường dẫn khác.
- Handler HTTP 403 mặc định vẫn hoạt động. Tạo event không làm đổi mã phản hồi.

### 4.4. Controller có tài nguyên được bảo vệ

`src/main/java/com/example/authzevents/ReportController.java`:

```java
package com.example.authzevents;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    @GetMapping("/api/management/report")
    public Map<String, String> managementReport() {
        return Map.of("report", "ready");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile() {
        return Map.of("profile", "visible");
    }
}
```

### 4.5. Listener nhận quyết định từ chối

`src/main/java/com/example/authzevents/AuthorizationAuditListener.java`:

```java
package com.example.authzevents;

import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class AuthorizationAuditListener {
    private static final Logger log =
            LoggerFactory.getLogger(AuthorizationAuditListener.class);

    @EventListener
    public void onAuthorizationDenied(AuthorizationDeniedEvent<?> event) {
        Object securedObject = event.getObject();
        String target;

        if (securedObject instanceof HttpServletRequest request) {
            target = request.getMethod() + " " + request.getRequestURI();
        } else if (securedObject != null) {
            target = securedObject.getClass().getSimpleName();
        } else {
            target = "unknown";
        }

        Authentication current =
                SecurityContextHolder.getContext().getAuthentication();
        String actor = current == null ? "unknown" : current.getName();

        log.warn("authorization_denied actor={} target={} granted={}",
                actor, target, event.getAuthorizationResult().isGranted());
    }
}
```

Trong nhánh request thông thường, listener thấy đối tượng được bảo vệ có thể là `HttpServletRequest`; trong method security hoặc extension khác, kiểu của `event.getObject()` có thể khác. Vì vậy đoạn mã **kiểm tra kiểu trước khi dùng**. Dùng `SecurityContextHolder` tại listener đồng bộ để lấy actor theo ngữ cảnh hiện tại; điều này là lựa chọn cho ví dụ, không phải lời hứa rằng ở mọi kiểu listener bất đồng bộ đều có SecurityContext.

Một dòng log có thể có phần thông điệp tương tự sau (timestamp, thread, logger prefix do cấu hình logging quyết định):

```text
authorization_denied actor=analyst target=GET /api/management/report granted=false
```

Chú ý `granted=false` được đọc từ `AuthorizationResult`. Có thể bỏ trường đó vì sự kiện đã là `AuthorizationDeniedEvent`, nhưng để lại trong ví dụ giúp người học nhận ra quan hệ giữa loại event và kết quả. Trong sản phẩm thực tế, thay log demo bằng sự kiện audit có schema rõ ràng và loại bỏ dữ liệu nhạy cảm.

**Không sử dụng `event.getObject().toString()` để ghi toàn bộ đối tượng**: payload, đường dẫn và context có thể chứa thông tin cá nhân, ID nội bộ hoặc token. Ngay cả `getRequestURI()` cũng cần quy tắc ẩn/mã hóa tham số định danh theo yêu cầu bảo mật của hệ thống. Không đưa `Authentication.getCredentials()`, header `Authorization` hoặc stack trace vào audit log.

## 5. Chạy ứng dụng và quan sát

Trong thư mục dự án, cần JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Gọi thử ở terminal khác:

```bash
# A. Đã xác thực, thiếu ROLE_MANAGER
curl -i -u analyst:analyst123 http://localhost:8080/api/management/report

# B. Đã xác thực, có ROLE_MANAGER
curl -i -u manager:manager123 http://localhost:8080/api/management/report

# C. Chưa xác thực
curl -i http://localhost:8080/api/management/report

# D. Analyst vẫn đọc được profile
curl -i -u analyst:analyst123 http://localhost:8080/api/profile
```

Trên Windows PowerShell, có thể dùng `curl.exe` để gọi chương trình curl thật. Các status dự kiến:

| Trường hợp | HTTP status | Kỳ vọng về sự kiện |
|---|---|---|
| A: `analyst` truy cập report | **403** | `AuthorizationDeniedEvent` cho quyết định quyền bị từ chối |
| B: `manager` truy cập report | **200** | `SpringAuthorizationEventPublisher` mặc định **không** phát `AuthorizationGrantedEvent` |
| C: Chưa có thông tin xác thực | **401** với HTTP Basic | Không nên đồng nhất 401 với một `AuthorizationDeniedEvent`. Tùy nhánh đánh giá, thiếu authentication có thể ném lỗi trước khi một kết quả phân quyền được xuất bản |
| D: `analyst` truy cập profile | **200** | Không có event từ chối do rule này |

HTTP `200` của trường hợp B có JSON body dạng `{"report":"ready"}`. Mỗi request HTTP Basic có thể liên quan thêm các thành phần xác thực. Quan sát **sự kiện authorization riêng**, không suy ra mọi log bảo mật đều phát từ publisher này.

## 6. Kiểm thử: event thực sự được xuất bản

Một unit test tự gọi `ApplicationEventPublisher.publishEvent(new AuthorizationDeniedEvent(...))` **chỉ kiểm tra listener**, không chứng minh Spring Security đã tự xuất bản event khi rule từ chối. Kiểm thử tích hợp phù hợp hơn: dùng `MockMvc` đi qua security filters, và `@RecordApplicationEvents` của Spring Test để kiểm tra các event phát ra trong mỗi test.

`src/test/java/com/example/authzevents/AuthorizationEventsTest.java`:

```java
package com.example.authzevents;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
class AuthorizationEventsTest {
    @Autowired
    MockMvc mvc;

    @Test
    void deniedRequestProducesAuthorizationEvent(ApplicationEvents events)
            throws Exception {
        mvc.perform(get("/api/management/report")
                .with(user("analyst").roles("ANALYST")))
            .andExpect(status().isForbidden());

        assertThat(events.stream(AuthorizationDeniedEvent.class)
                .anyMatch(event ->
                    !event.getAuthorizationResult().isGranted()))
            .isTrue();
    }

    @Test
    void allowedRequestDoesNotProduceDeniedEvent(ApplicationEvents events)
            throws Exception {
        mvc.perform(get("/api/management/report")
                .with(user("manager").roles("MANAGER")))
            .andExpect(status().isOk());

        assertThat(events.stream(AuthorizationDeniedEvent.class).count())
            .isZero();
    }

    @Test
    void unauthenticatedRequestIsChallenged() throws Exception {
        mvc.perform(get("/api/management/report"))
            .andExpect(status().isUnauthorized());
    }
}
```

Chạy:

```bash
mvn test
```

Ba ca kiểm tra:

1. Với analyst, request bị 403 **và** có ít nhất một event từ chối. Tránh kiểm tra cứng “chính xác 1 event” vì các interceptor hoặc dispatcher bổ sung có thể tạo nhiều lần kiểm tra khi cấu hình mở rộng.
2. Với manager, request được phép và không phát event **từ chối** trong test đơn giản này. Điều này khác với khẳng định luôn có event **thành công**.
3. Với anonymous, HTTP Basic yêu cầu xác thực trả 401; test cố ý không áp đặt số event vì chi tiết phụ thuộc đường đi xác thực/ủy quyền.

`with(user(...))` tạo authentication giả lập cho request kiểm thử và không kiểm tra mật khẩu thật. Lệnh `curl -u` ở phần trước là bài kiểm tra đường đi HTTP Basic qua `UserDetailsService`. `@RecordApplicationEvents` ghi event theo từng test method; không cần lưu event vào một danh sách static dễ bị rò rỉ trạng thái giữa các ca test.

## 7. Chọn đúng hook cho audit

Ba cách thường được nhắc đến cùng nhau nhưng không hoán đổi cho nhau:

| Nhu cầu | Hook nên cân nhắc | Giới hạn |
|---|---|---|
| Ghi nhận rule phân quyền từ chối tại `AuthorizationManager` | `AuthorizationEventPublisher` + `AuthorizationDeniedEvent` | Chỉ bao phủ nguồn quyết định thực sự đi qua publisher |
| Trả JSON/HTML 403 cho client | `AccessDeniedHandler` | Là phần **xử lý response**, không phải kênh phân quyền hay nguồn audit tổng quát |
| Theo dõi đăng nhập thành công/thất bại | `AuthenticationEventPublisher` + các authentication events | Liên quan xác thực, không biểu diễn việc có quyền vào từng tài nguyên |
| Ghi nhận nghiệp vụ đã thực hiện (ví dụ duyệt đơn) | Business/domain event hoặc transactional outbox | Không thay thế quyết định permission trước khi thực hiện hành động |

Ví dụ, với `@EnableMethodSecurity` và `@PreAuthorize`, một lời gọi service cũng có thể tạo `AuthorizationDeniedEvent` khi interceptor được cấu hình với publisher. Đối tượng event có thể là lời gọi method, **không phải `HttpServletRequest`**. Không áp dụng giả định HTTP cho mọi `event.getObject()`; kiểm tra riêng những điểm kiểm soát quyền thật sự trong ứng dụng.

Trong hệ thống có nhiều `SecurityFilterChain`, các endpoint có thể dùng chain khác nhau. Một event được ghi nhận cần gắn với **rule/nguồn kiểm tra thực sự**, không suy từ URL đơn thuần nếu có nhiều lớp bảo vệ. Với authorization do code nghiệp vụ tự xử lý ngoài Spring Security, phải chủ động tạo domain audit phù hợp; tự phát `AuthorizationDeniedEvent` một cách tùy tiện có thể khiến dữ liệu kiểm toán gây hiểu nhầm.

## 8. Khi nào phát `AuthorizationGrantedEvent`?

Mọi request hoặc method call được cho phép đều có thể tạo lượng lớn thành công. Vì vậy `SpringAuthorizationEventPublisher` **chỉ phát event từ chối theo mặc định**. Trong các hệ thống lưu lượng cao, bật phát mọi lần thành công có thể:

- tăng chi phí CPU, I/O, bộ nhớ và storage;
- làm ngập pipeline giám sát, khó phân biệt sự kiện rủi ro;
- làm lộ các metadata của truy cập thành công nếu ghi log không kiểm soát.

Chỉ nên chọn những quyết định cho phép **cần có dấu vết riêng** (chẳng hạn truy cập chức năng quản trị nhạy cảm), hoặc thực hiện sampling có kiểm soát. Vẫn phải xác định audit nào bắt buộc bền vững và có cách giao nhận phù hợp.

### 8.1. Sự khác nhau giữa Spring Security 6.5 và 7.x

- Ở **6.5.x**, `SpringAuthorizationEventPublisher` không cung cấp setter `setShouldPublishResult(...)`. Nếu cần sự kiện thành công chọn lọc, cần một publisher tùy biến tương thích API 6.5 hoặc instrumentation riêng, và kiểm thử kỹ các overload `AuthorizationDecision`/`AuthorizationResult`.
- Ở **7.x**, `SpringAuthorizationEventPublisher` cung cấp `setShouldPublishResult(Predicate<AuthorizationResult>)`. Có thể đặt predicate để chọn những kết quả cần phát. Đừng sao chép setter này vào source đang dùng Spring Security 6.5.

Ví dụ **chỉ dành cho Spring Security 7.x**, được đặt trong một class `@Configuration` và thay thế bean publisher mặc định ở phần 4.3 (đoạn code độc lập về phương thức, không ghép vào project 6.5):

```java
@Bean
AuthorizationEventPublisher authorizationEventPublisher(
        ApplicationEventPublisher springEvents) {
    var publisher = new SpringAuthorizationEventPublisher(springEvents);
    publisher.setShouldPublishResult(result -> {
        if (!result.isGranted()) {
            return true; // Giữ mọi kết quả từ chối
        }
        if (result instanceof AuthorityAuthorizationDecision authorityResult) {
            return authorityResult.getAuthorities().stream()
                    .anyMatch(a -> "ROLE_MANAGER".equals(a.getAuthority()));
        }
        return false; // Không phát những lần cho phép khác
    });
    return publisher;
}
```

Các type dùng trong đoạn code 7.x nằm ở `org.springframework.security.authorization`: `AuthorizationEventPublisher`, `SpringAuthorizationEventPublisher` và `AuthorityAuthorizationDecision`; `ApplicationEventPublisher` nằm trong `org.springframework.context`, `@Bean` trong `org.springframework.context.annotation`. Đoạn trên chủ ý chỉ là phần method để minh họa khác biệt 7.x; cần import tương ứng và kiểm tra phiên bản classpath khi triển khai.

Ý nghĩa predicate: luôn giữ deny, chỉ phát thêm một số grant có đối tượng kết quả thuộc `AuthorityAuthorizationDecision` với authority cần quan sát. Tùy cấu hình thực tế, một `AuthorizationManager` có thể trả loại `AuthorizationResult` khác, nên predicate không bảo đảm bắt được mọi lần truy cập chức năng “quản trị” nếu chỉ dựa vào loại kết quả/authority. Nên có test chứng minh đúng loại quyết định từ endpoint quan trọng và đo lưu lượng event trước khi bật production.

## 9. Thiết kế audit an toàn và có thể vận hành

### 9.1. Schema khuyến nghị

Nếu đẩy dữ liệu sang hệ thống audit riêng, có thể chuyển event thành bản ghi tối thiểu:

```json
{
  "eventType": "AUTHORIZATION_DENIED",
  "occurredAt": "2026-11-05T11:00:00Z",
  "actorId": "user-42",
  "resourceType": "MANAGEMENT_REPORT",
  "action": "READ",
  "result": "DENIED",
  "requestId": "req-abc123",
  "source": "SPRING_SECURITY_AUTHORIZATION"
}
```

Đây là **schema minh họa**, không phải JSON mà Spring Security tự phát và cũng không phải output chính xác của ví dụ ở phần 4. Trong sản phẩm, các giá trị `actorId`, `resourceType`, `action` và `requestId` phải lấy từ ngữ cảnh đã được xác minh; không suy diễn quyền từ chuỗi URL thiếu kiểm soát.

### 9.2. Những quyết định thiết kế cần chốt

1. **Định nghĩa loại sự kiện:** phân biệt authentication, authorization, CSRF và business audit. Đếm `AuthorizationDeniedEvent` không đồng nghĩa đếm mọi HTTP 403.
2. **Tối thiểu dữ liệu:** chỉ lưu định danh tài khoản được phép, mã tài nguyên/hoạt động, kết quả, thời điểm và trace/correlation ID. Không ghi credentials, cookies, access token, response body hoặc nguyên object đang bảo vệ.
3. **Độ tin cậy:** Spring application event trong process không phải audit trail bền vững. Nếu bắt buộc lưu trước khi xác nhận nghiệp vụ, cần thiết kế lưu durable phù hợp (ví dụ hàng đợi được bảo đảm hoặc transactional outbox tùy nghiệp vụ).
4. **Ảnh hưởng hiệu năng:** listener đồng bộ xử lý chậm có thể làm request chậm. Listener ném runtime exception cũng có thể làm lỗi request. Đặt ranh giới failure handling, batch/queue/timeout và chính sách backpressure rõ ràng.
5. **Bất đồng bộ:** `Supplier<Authentication>` và `HttpServletRequest` phụ thuộc ngữ cảnh thời điểm gọi. Nếu đưa audit qua queue, **chụp các giá trị nguyên thủy đã làm sạch trong luồng xử lý ban đầu**, không chuyển nguyên supplier, request hay SecurityContext sang thread khác.
6. **Thứ tự và trùng lặp:** nhiều tầng authorization hoặc multiple dispatch có thể phát nhiều event. Dùng khóa correlation và loại kiểm tra để phân biệt; không mặc định exactly-once.
7. **Kiểm soát truy cập audit:** log/sự kiện chứa thông tin an ninh; cần giới hạn quyền đọc, thời gian lưu, phân loại dữ liệu và kiểm soát xuất dữ liệu.

## 10. Sự cố thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh |
|---|---|---|
| Client nhận 403 nhưng listener không chạy | Chưa tạo bean publisher, endpoint vào chain khác, CSRF chặn request hoặc một thành phần tự trả 403 | Kiểm tra bean `AuthorizationEventPublisher`; test GET thiếu role với `@RecordApplicationEvents`; phân biệt nguồn 403 |
| Client nhận 401 và không có event | Xác thực không thành công hoặc authentication entry point được gọi trước khi có quyết định phân quyền | Kiểm thử bằng một user **đã đăng nhập** nhưng thiếu quyền |
| Không thấy `AuthorizationGrantedEvent` | `SpringAuthorizationEventPublisher` mặc định bỏ qua grant | Đây là mặc định; cân nhắc grant chọn lọc theo phiên bản |
| Compile lỗi `setShouldPublishResult` | Đang dùng Spring Security 6.5 trở xuống | Setter có ở 7.x; dùng implementation đúng version |
| Đọc actor sai/null trong listener async | SecurityContext/request đã đổi hoặc mất sau request | Trích xuất actor và metadata an toàn ở listener đồng bộ trước khi queue |
| Lượng event lớn hơn số request | Nhiều check quyền, method security hoặc dispatcher `ERROR/FORWARD` | Gắn request ID, loại check và so sánh từng nhánh |
| Chỉ dùng `@ControllerAdvice` mà không thấy lỗi HTTP filter | Exception từ security filter không nhất thiết qua MVC exception resolver | Dùng `ExceptionTranslationFilter`/`AccessDeniedHandler` cho HTTP; listener cho audit |
| Audit làm API chậm hoặc phát sinh 500 | Listener đồng bộ tốn thời gian/throw exception | Giới hạn tác vụ listener, kiểm thử lỗi sink, dùng queue và fallback |
| Event được phát thủ công dù không có check thật | Ghi audit giả bằng cách tự phát event không gắn với AuthorizationManager | Ghi domain event riêng hoặc xuất bản từ điểm kiểm soát quyền thật sự |

## 11. Checklist thực hành

- [ ] Giải thích được vai trò của `AuthorizationManager`, `AuthorizationEventPublisher` và `SpringAuthorizationEventPublisher`.
- [ ] Xác nhận đã đăng ký đúng bean `AuthorizationEventPublisher` trong application context.
- [ ] Với analyst thiếu `ROLE_MANAGER`, kiểm tra HTTP **403** *và* `AuthorizationDeniedEvent`.
- [ ] Với manager có quyền, kiểm tra HTTP **200**; hiểu vì sao mặc định không phát grant.
- [ ] Không nhầm `AuthorizationDeniedEvent` với `AuthenticationFailureEvent` và `AccessDeniedHandler`.
- [ ] Trích xuất metadata audit an toàn; không lưu trực tiếp `HttpServletRequest` hoặc `Supplier<Authentication>` để xử lý async.
- [ ] Đối chiếu API 6.5/7.x trước khi viết custom publisher hoặc bật grant.
- [ ] Có test cho nguồn sự kiện, bảo vệ dữ liệu và tác động của listener khi lỗi.

## Tài liệu tham khảo chính thức

- [Spring Security – Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html) – cách tạo `SpringAuthorizationEventPublisher` và lắng nghe sự kiện.
- [Spring Security 6.5 – `AuthorizationEventPublisher` API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationEventPublisher.html) – chữ ký cũ và overload `AuthorizationResult`.
- [Spring Security 6.5 – `SpringAuthorizationEventPublisher` API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/SpringAuthorizationEventPublisher.html) – implementation mặc định chỉ phát denial.
- [Spring Security 7.x – `SpringAuthorizationEventPublisher` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/SpringAuthorizationEventPublisher.html) – setter `setShouldPublishResult(...)`.
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) – `AuthorizationFilter`, `AuthorizationManager` và luồng lỗi.
- [Spring Framework – Application Events in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html) – `@RecordApplicationEvents` và `ApplicationEvents`.
