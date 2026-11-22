# AuthorizationGrantedEvent và kiểm soát lượng sự kiện thành công

> **Chủ đề:** Spring Security – authorization. **Nhóm kiến thức:** Sự kiện và audit. Bài học tập trung vào `AuthorizationGrantedEvent`, lý do không nên phát mọi sự kiện cấp quyền thành công, cách chọn sự kiện quan trọng và cách kiểm thử lượng sự kiện. Ví dụ chính sử dụng **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Servlet API**; cuối bài có lưu ý API ở các phiên bản mới hơn.

## 1. Tại sao cần biết về sự kiện cấp quyền thành công?

Một request tới `GET /api/admin/report` có thể qua nhiều bước: xác thực người gọi, kiểm tra role, kiểm tra quyền ở method, truy vấn dữ liệu, rồi tạo HTTP response. Tại bước kiểm tra quyền, Spring Security có thể có **quyết định**: được phép (`granted`), từ chối (`denied`) hoặc cơ chế đánh giá không đưa ra một quyết định xác định (`null` trong một số API).

`AuthorizationGrantedEvent` diễn tả **một lần kiểm tra authorization cho kết quả được phép**. Nó **không** khẳng định toàn bộ nghiệp vụ đã hoàn tất, không khẳng định giao dịch DB đã commit, và không phải sự kiện “đăng nhập thành công”.

Bạn sẽ học cách:

1. Phân biệt `AuthorizationGrantedEvent`, `AuthorizationDeniedEvent`, `AuthenticationSuccessEvent` và audit nghiệp vụ.
2. Biết khi nào Spring Security có thể phát sự kiện, đối tượng nào nằm trong event, và vì sao **success không được phát mặc định**.
3. Thiết kế chính sách thu thập **đúng mục đích**: giữ các lần cấp quyền quan trọng, hạn chế các lần cấp quyền thông thường, duy trì visibility đối với sự kiện từ chối.
4. Triển khai `AuthorizationEventPublisher` có chọn lọc, lắng nghe bằng `@EventListener` và kiểm thử bằng `MockMvc`/`ApplicationEvents`.
5. Quản lý lượng event, cardinality, chi phí xử lý, bảo mật dữ liệu và giới hạn của audit.

## 2. Các loại sự kiện và phạm vi ý nghĩa

| Sự kiện | Khi nào có ý nghĩa? | Có thay thế sự kiện khác được không? |
|---|---|---|
| `AuthenticationSuccessEvent` | Credential được xác thực thành công bởi cơ chế authentication tương ứng | Không nói user được phép truy cập resource cụ thể |
| `AuthenticationFailure...Event` | Xác thực thất bại, tùy cơ chế và publisher | Không nhất thiết tạo `AuthorizationDeniedEvent` |
| `AuthorizationGrantedEvent<T>` | Một lần đánh giá authorization cho kết quả **granted**, khi publisher **chọn phát** | Không chứng minh business operation thành công |
| `AuthorizationDeniedEvent<T>` | Một lần đánh giá authorization cho kết quả **denied**, khi publisher phát | Không phải mọi HTTP 401/403 đều sinh đúng một event |
| **Audit nghiệp vụ** do ứng dụng định nghĩa | Ví dụ lệnh chuyển tiền đã được ghi nhận/commit, tài liệu đã chia sẻ | Cần phát tại ranh giới nghiệp vụ thích hợp, có thể sau commit |

Ví dụ: nhân viên có `ROLE_ADMIN` truy cập `/api/admin/report`. `AuthorizationGrantedEvent` ghi nhận authorization rule cho phép request đi tiếp. Controller vẫn có thể trả 500 khi kết nối DB lỗi. Nếu coi grant là “đã đọc báo cáo thành công”, lịch sử audit sẽ sai.

### Luồng của Servlet request

```text
HTTP request
    │
    ▼
Authentication filter / SecurityContext
    │
    ▼
AuthorizationFilter
    │  └─ AuthorizationManager đánh giá:
    │       ├─ DENIED  → AuthorizationEventPublisher
    │       │             → AuthorizationDeniedEvent (nếu được phát)
    │       │             → AccessDeniedException → xử lý từ chối
    │       └─ GRANTED → AuthorizationEventPublisher
    │                     → AuthorizationGrantedEvent
    │                       CHỈ KHI publisher chủ động cho phép
    ▼
Controller → Service → Database
    │
    └─ kết quả nghiệp vụ và audit nghiệp vụ riêng
```

`AuthorizationFilter` sử dụng `Supplier<Authentication>` và `HttpServletRequest` để đánh giá rule trong `authorizeHttpRequests`. Với method security như `@PreAuthorize`, đối tượng được kiểm tra có thể là `MethodInvocation`, không phải `HttpServletRequest`. Vì thế code đọc `event.getObject()` phải kiểm tra kiểu, không ép kiểu một cách mù quáng.

**Một HTTP request có thể dẫn đến nhiều lần đánh giá quyền:** ở URL, ở service method, khi forward/error dispatch, hoặc khi code gọi một method được bảo vệ nhiều lần. Số authorization event không nhất thiết bằng số request hay số lần user thao tác.

## 3. Mặc định: vì sao không nhìn thấy AuthorizationGrantedEvent?

Để nhận sự kiện authorization qua Spring Application Events, ứng dụng cần một `AuthorizationEventPublisher` được cấu hình. Spring Security cung cấp `SpringAuthorizationEventPublisher` để chuyển kết quả authorization sang Spring event.

Điều quan trọng của phiên bản 6.x: **`SpringAuthorizationEventPublisher` phát các sự kiện denied và bỏ qua granted theo mặc định.** Nó không tự bật thu thập mọi lần success, vì ứng dụng bình thường có thể kiểm tra quyền trong gần như mọi request và nhiều method.

Ví dụ cấu hình publisher mặc định để theo dõi deny:

```java
// Ví dụ cấu hình ngắn trong @Configuration, Spring Security 6.x.
@Bean
AuthorizationEventPublisher authorizationEventPublisher(
        ApplicationEventPublisher applicationEventPublisher) {
    return new SpringAuthorizationEventPublisher(applicationEventPublisher);
}
```

Bean này **chưa** khiến `@EventListener(AuthorizationGrantedEvent)` nhận các lần thành công. Bạn phải chủ động xây dựng publisher biết lúc nào phát grant, hoặc dùng API lọc event tương ứng với đúng phiên bản đang chạy.

### Đừng nhầm ba tầng

- **Quyết định authorization:** ví dụ `hasRole("ADMIN")` trả granted. Quyết định này xảy ra dù có bật audit hay không.
- **Công bố authorization event:** publisher cân nhắc có tạo sự kiện hay bỏ qua. Bỏ qua **không** biến request từ allowed thành denied.
- **Tiêu thụ event:** `@EventListener`, metrics hoặc audit sink tiếp nhận event đã phát. Listener không nên được dùng để quyết định quyền lần nữa.

Không thể “bật `@EventListener`” để bắt một event mà publisher không tạo. Ngược lại, tạo mọi event rồi mới lọc ở listener vẫn phát sinh chi phí tạo object, dispatch và những listener khác.

## 4. Dữ liệu bên trong một AuthorizationGrantedEvent

Trong Spring Security 6.3, `AuthorizationGrantedEvent<T>` nằm ở package `org.springframework.security.authorization.event`. Constructor nhận:

```java
new AuthorizationGrantedEvent<>(
    Supplier<Authentication> authentication,
    T securedObject,
    AuthorizationDecision decision
);
```

Các thành phần cần hiểu:

| Thành phần | Ý nghĩa | Lưu ý khi ghi log |
|---|---|---|
| `getAuthentication()` | `Supplier<Authentication>` gắn với principal trong lần kiểm tra | Chỉ lấy trường cần dùng; không serialize Authentication/token/credentials |
| `getObject()` | Đối tượng được kiểm tra: request hoặc method invocation, tùy cơ chế | Có thể chứa URI với ID, body, header hoặc tham số nhạy cảm |
| `getAuthorizationDecision()` | Kết quả cấp quyền ở API 6.3; `isGranted()` phải là `true` với grant | Không suy ra kết quả HTTP hay commit |
| Thời điểm phát | Tại ranh giới đánh giá authorization | Có thể trước khi controller thực thi |

`T` là kiểu object được bảo vệ, không phải kiểu ID hay user. Không nên lưu `event.toString()`, dump toàn bộ request hoặc gửi nguyên event qua message broker. Một số object có thể giữ reference tới request và security context; trích xuất DTO audit nhỏ, có schema rõ ràng trước khi chuyển sang xử lý bất đồng bộ.

## 5. Bài toán lưu lượng: một success event “rẻ” cũng có thể rất đắt

Giả sử một API xử lý **2.000 request/giây**, trung bình **hai kiểm tra authorization/request**, và **99%** kết quả được cho phép. Nếu phát mọi thành công:

```text
2.000 × 2 × 0,99 = 3.960 grant events / giây
3.960 × 86.400 = 342.144.000 grant events / ngày
```

Đây là ví dụ minh họa để ước tính quy mô, không phải con số mặc định của Spring Security. Nếu mỗi bản ghi được lưu sau khi serialize chiếm trung bình khoảng 1 KB, riêng thành công có thể tạo **hàng trăm GB/ngày** trước nhân bản, chỉ mục, retention và mạng.

Tác động không chỉ ở dung lượng:

- **CPU và allocation:** khởi tạo event, xây dựng bản ghi, JSON serialization và logic xử lý listener.
- **Độ trễ request:** Spring `@EventListener` thông thường chạy đồng bộ trong thread publish event; listener chậm có thể khiến API chậm.
- **Cardinality:** metric gắn `userId`, tài liệu ID hoặc URL có tham số động có thể tạo lượng time series rất lớn.
- **Queue và downstream:** burst có thể làm đầy hàng đợi, tăng retry, làm nghẽn logging pipeline.
- **Độ hữu ích:** hàng triệu dòng “GET thông thường được phép” có thể che lấp vài sự kiện đặc quyền thực sự cần điều tra.

**Thước đo phù hợp là giá trị của event so với chi phí và rủi ro**, không phải số sự kiện càng nhiều càng tốt.

## 6. Chính sách thu thập thực tế

Một chính sách có thể chia thành ba nhóm:

| Nhóm | Ví dụ | Chiến lược |
|---|---|---|
| **Deny có ý nghĩa bảo mật** | Rule chặn truy cập tài liệu/endpoint | Thông thường giữ toàn bộ `AuthorizationDeniedEvent` nếu hệ thống cần giám sát; xử lý lặp/burst ở pipeline mà không đánh mất tín hiệu |
| **Grant đặc quyền/nhạy cảm** | Truy cập báo cáo quản trị, phê duyệt quyền, chức năng tài chính | **Allowlist**, ghi lại có chọn lọc đầy đủ với chính sách retention |
| **Grant thông thường, tần suất cao** | Xem trang cá nhân, đọc catalog, request đọc thông dụng | Bỏ qua, thu metric tổng hợp, hoặc **sampling** nhỏ nếu cần quan sát |

Cần quyết định từ đầu event là **audit evidence bắt buộc**, **telemetry để giám sát**, hay **debug signal**. Với audit bắt buộc, sampling hoặc drop âm thầm không phù hợp. Với telemetry, 1% sampling có thể đủ để nhìn xu hướng; kết quả sample không thể dùng như danh sách đầy đủ người đã truy cập.

### Năm nguyên tắc thiết kế publisher

1. **Không làm thay đổi quyết định quyền.** Publisher chỉ quan sát, không cấp/quản lý quyền cho user.
2. **Lọc trước khi phát.** Chỉ tạo `AuthorizationGrantedEvent` khi một rule quan sát được chấp nhận.
3. **Giữ đường denied.** Khi custom publisher, tiếp tục ủy quyền denied cho `SpringAuthorizationEventPublisher` hoặc triển khai tương đương có kiểm thử.
4. **Chọn key ổn định.** Phân loại theo policy/route template (ví dụ `admin-report`), tránh URL thực chứa ID.
5. **Phân biệt nguồn sự kiện.** Publisher chỉ lọc request-level khi object là `HttpServletRequest`. Nếu cần giám sát method security, xây chính sách riêng cho `MethodInvocation`.

## 7. Ví dụ chạy được: chỉ phát grant cho endpoint quản trị

Ví dụ sau thiết lập một ứng dụng web nhỏ với hai endpoint. Mỗi request đã xác thực đều được Spring Security đánh giá quyền, nhưng **chỉ các quyết định granted trên `GET /api/admin/report`** được phát dưới dạng `AuthorizationGrantedEvent`. Quyết định denied vẫn được delegate xử lý.

### 7.1. Cấu trúc source

```text
settings.gradle
build.gradle
src/main/java/demo/AuthorizationEventDemoApplication.java
src/main/java/demo/SecurityConfiguration.java
src/main/java/demo/SelectiveAuthorizationEventPublisher.java
src/main/java/demo/DemoController.java
src/main/java/demo/GrantLogListener.java
src/test/java/demo/AuthorizationEventDemoTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'authorization-event-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các phiên bản được ghim để mô tả một API cụ thể trong ví dụ; dự án thực tế cần cập nhật các bản vá được hỗ trợ và kiểm tra compatibility của Spring Boot/Spring Security.

`src/main/java/demo/AuthorizationEventDemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationEventDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationEventDemoApplication.class, args);
    }
}
```

`src/main/java/demo/SecurityConfiguration.java`:

```java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/api/admin/report").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET,
                    "/api/profile").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher springEvents) {
        return new SelectiveAuthorizationEventPublisher(springEvents);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("admin")
                .password("{noop}adminpass")
                .roles("ADMIN")
                .build(),
            User.withUsername("reader")
                .password("{noop}readerpass")
                .roles("USER")
                .build()
        );
    }
}
```

`{noop}` chỉ phù hợp demo trong bộ nhớ: không lưu plaintext password trong ứng dụng thật. HTTP Basic trên hệ thống thực tế phải sử dụng HTTPS.

`src/main/java/demo/SelectiveAuthorizationEventPublisher.java`:

```java
package demo;

import java.util.function.Supplier;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.authorization.event.AuthorizationGrantedEvent;
import org.springframework.security.core.Authentication;

public final class SelectiveAuthorizationEventPublisher
        implements AuthorizationEventPublisher {

    private final ApplicationEventPublisher events;
    private final AuthorizationEventPublisher deniedDelegate;

    public SelectiveAuthorizationEventPublisher(
            ApplicationEventPublisher events) {
        this.events = events;
        this.deniedDelegate = new SpringAuthorizationEventPublisher(events);
    }

    @Override
    public <T> void publishAuthorizationEvent(
            Supplier<Authentication> authentication,
            T securedObject,
            AuthorizationDecision decision) {

        // Một số AuthorizationManager có thể không trả quyết định.
        if (decision == null) {
            return;
        }

        if (!decision.isGranted()) {
            // Tuyệt đối không làm mất đường published denied khi custom.
            deniedDelegate.publishAuthorizationEvent(
                authentication, securedObject, decision);
            return;
        }

        // Ví dụ này chỉ theo dõi request-level Servlet.
        if (!(securedObject instanceof HttpServletRequest request)) {
            return;
        }

        // Không phát thêm do forward/error dispatch.
        if (request.getDispatcherType() != DispatcherType.REQUEST) {
            return;
        }

        boolean criticalGrant = "GET".equals(request.getMethod())
            && "/api/admin/report".equals(request.getServletPath());

        if (criticalGrant) {
            events.publishEvent(new AuthorizationGrantedEvent<>(
                authentication, securedObject, decision));
        }
    }
}
```

Giải thích các quyết định:

- **Denied:** delegate xử lý với hành vi mặc định của Spring Security. Không ép chuyển denied thành granted, không đổi HTTP 403.
- **Granted cho route thường:** kết thúc ngay trong publisher, không tạo `AuthorizationGrantedEvent`.
- **Granted cho route quản trị:** phát một Spring event để listener xử lý.
- **Dispatcher type:** chỉ quan tâm `REQUEST`, tránh ghi lặp chỉ vì dispatch lại.
- **Kiểu object:** với method security, object thường không phải `HttpServletRequest`; mẫu này cố ý không phát grant method-level. Một quyết định thành công trên route không khẳng định method phía sau chắc chắn được phép.

Điều kiện `getServletPath()` phù hợp với hai route cố định của demo. Ứng dụng thực tế có context path, servlet mapping đặc biệt, versioned API hoặc route động nên xác định **policy ID/template chuẩn hóa** trong lớp authorization, không so sánh URI raw hoặc đem ID nhạy cảm vào log.

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/admin/report")
    String report() {
        return "report-ok";
    }

    @GetMapping("/api/profile")
    String profile() {
        return "profile-ok";
    }
}
```

`src/main/java/demo/GrantLogListener.java`:

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.event.AuthorizationGrantedEvent;
import org.springframework.stereotype.Component;

@Component
public class GrantLogListener {

    private static final Logger log =
        LoggerFactory.getLogger(GrantLogListener.class);

    @EventListener
    public void onGranted(AuthorizationGrantedEvent<?> event) {
        // Publisher đã giới hạn vào một route nhạy cảm.
        // Không serialize Authentication hay HttpServletRequest.
        log.info("authorization_granted policy=admin-report");
    }
}
```

Listener này chỉ minh họa một log an toàn và chi phí nhỏ. Khi ghi audit thực, thêm correlation ID và thời gian theo cơ chế chuẩn của ứng dụng, nhưng **không** log mật khẩu, bearer token, cookie, request body hoặc toàn bộ `event.getObject()`.

### 7.2. Chạy và quan sát

Trong thư mục có Gradle wrapper (hoặc dùng Gradle phù hợp), chạy:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Với Bash/curl:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:adminpass http://localhost:8080/api/admin/report

curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:readerpass http://localhost:8080/api/profile

curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:readerpass http://localhost:8080/api/admin/report

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/admin/report
```

Kết quả HTTP **dự kiến**, theo đúng thứ tự: `200`, `200`, `403`, `401`. Sau yêu cầu đầu tiên, logger **dự kiến** có dòng `authorization_granted policy=admin-report`. Yêu cầu profile thành công không tạo grant event do chính sách allowlist. Yêu cầu denied không tạo grant event; publisher tiếp tục chuyển đường denied cho Spring.

Các kết quả trên là kỳ vọng của ví dụ, không phải log của môi trường đã được chạy trong bài viết.

### 7.3. Test tự động với MockMvc và ApplicationEvents

`src/test/java/demo/AuthorizationEventDemoTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.authorization.event.AuthorizationGrantedEvent;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
class AuthorizationEventDemoTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationEvents events;

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void privilegedGrantIsPublished() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isOk());

        assertThat(events.stream(AuthorizationGrantedEvent.class).count())
            .isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void ordinaryGrantIsFilteredBeforePublishing() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isOk());

        assertThat(events.stream(AuthorizationGrantedEvent.class).count())
            .isZero();
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void denialStillProducesDeniedEvent() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());

        assertThat(events.stream(AuthorizationDeniedEvent.class).count())
            .isGreaterThanOrEqualTo(1);
    }

    @Test
    void anonymousAdminRequestIsRejected() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isUnauthorized());
    }
}
```

Chạy `./gradlew test`. `@WithMockUser` tạo security context cho test, không xác minh password thật; các test về event/status đang kiểm tra authorization và publisher. Nếu cần kiểm tra authentication thật, bổ sung test `httpBasic(...)` hoặc request qua server thực.

**Các giả định của ví dụ:** chỉ có một `SecurityFilterChain`; không có thêm `@PreAuthorize`, filter riêng hoặc dispatch bất thường làm phát nhiều quyết định; handler và publisher dùng cùng Spring ApplicationContext. Trong ứng dụng thực, cần lọc event theo loại secured object/policy và kiểm chứng số lượng khi có nhiều chain hoặc method security.

## 8. Nếu muốn quan sát 1% grant thông thường

Một hệ thống có thể cần biết mẫu của các quyết định thông thường. Khi đó mở rộng **nhánh granted** của publisher trước lệnh `publishEvent`:

```java
// Đoạn minh họa bên trong publishAuthorizationEvent,
// sau kiểm tra object là HttpServletRequest và DispatcherType.REQUEST.
boolean important = "GET".equals(request.getMethod())
    && "/api/admin/report".equals(request.getServletPath());

boolean sampledOrdinary = "GET".equals(request.getMethod())
    && "/api/profile".equals(request.getServletPath())
    && java.util.concurrent.ThreadLocalRandom.current()
        .nextInt(100) == 0; // Xấp xỉ 1% mỗi quyết định.

if (important || sampledOrdinary) {
    events.publishEvent(new AuthorizationGrantedEvent<>(
        authentication, securedObject, decision));
}
```

Đoạn này **thay thế** điều kiện `criticalGrant` trong ví dụ đầy đủ, không chạy độc lập. Kết quả 1% là xác suất kỳ vọng, không đảm bảo cứ đúng 100 event có một event. Các test cho phần sampling nên inject một bộ chọn có thể điều khiển bằng seed/fake, tránh test phụ thuộc may rủi; vẫn giữ test riêng rằng critical luôn được phát và denied không bị lọc.

### Sampling khác giới hạn tốc độ

- **Probability sampling (1%)**: giảm tỷ lệ trung bình, nhưng một burst rất lớn vẫn có thể vượt sức chứa sink.
- **Rate limit/quota**: đặt trần event/giây cho telemetry, có thể drop thông tin dưới tải; phải định nghĩa hành vi khi quá tải.
- **Bounded queue + backpressure**: kiểm soát memory và chặn bùng nổ, có chính sách drop/flush/retry rõ ràng.
- **Aggregation**: thay hàng triệu dòng chi tiết bằng counter theo policy/decision và cửa sổ thời gian.
- **Allowlist**: chọn loại quyết định quan trọng trước, thường hữu ích nhất cho audit nhạy cảm.

Đối với sự kiện mang yêu cầu lưu trữ bắt buộc, phải có hạ tầng durable và quy trình vận hành khi sink không khả dụng; không áp sampling chỉ để giảm chi phí rồi khẳng định audit đầy đủ. Ngược lại, không nên bắt API đợi một hệ thống phân tích tùy chọn ở mỗi request.

## 9. Đếm đúng: metrics, tracing và audit không giống nhau

Nếu chỉ có event cấp quyền đã lọc, biểu đồ “số `AuthorizationGrantedEvent` nhận được” là **số event được phát**, không nhất thiết là tổng lượt cấp quyền thật.

Một thiết kế quan sát hợp lý:

1. Tại điểm đưa ra quyết định, cập nhật **counter tổng hợp** theo tập nhãn hữu hạn: `decision=granted|denied`, `policy=admin-report|profile|other`, `surface=request|method`. Nếu metric thật sự cần tổng đầy đủ, phải đếm **trước sampling** và biết phạm vi các điểm kiểm tra.
2. Chỉ phát **grant event chi tiết** cho chính sách được chọn. Nếu có sampling, gắn `sample_rate` ở metadata cho pipeline biết cách diễn giải; không nội suy thành audit từng người.
3. Gắn trace/correlation ID để nối sự kiện với request, nhưng kiểm soát retention và quyền xem. Không dùng trace ID hay user ID làm nhãn Prometheus/Micrometer có cardinality cao.
4. Ghi **business audit** riêng cho hành động đã thành công (ví dụ thay đổi quyền của tài liệu sau commit), sử dụng transactional outbox hoặc cách bảo đảm giao hàng phù hợp; grant event ở filter không đủ.
5. Có metric cho số event **bị lọc**, số event **đã gửi**, số event **bị drop vì queue đầy**, queue depth, lỗi downstream. Dùng các metric này để nhận ra “không có event” là do traffic thấp hay pipeline lỗi.

Ví dụ tên metric với nhãn ổn định:

```text
security_authorization_decisions_total{surface="request",policy="admin-report",decision="granted"}
security_authorization_events_published_total{kind="granted",policy="admin-report"}
security_authorization_event_queue_dropped_total{kind="granted"}
```

Đây là **đề xuất schema metric** để học, không phải tên metric được Spring Security tự tạo sẵn. Hãy khai báo metric thực tế trong Micrometer/observability pipeline của dự án; đặc biệt, tuyệt đối không tạo metric series theo raw document ID, email hay URL chứa token.

## 10. Vấn đề hiệu năng và bảo mật khi xử lý listener

### Đồng bộ hay bất đồng bộ?

Theo mặc định, Spring application events thường được dispatch đồng bộ. Nếu listener ghi DB hoặc gọi HTTP tới SIEM ngay trong `@EventListener`, request thành công có thể bị chậm hoặc thậm chí lỗi nếu listener ném exception.

Không nên hiểu `@Async` là giải pháp hoàn chỉnh: muốn dùng nó cần bật async processing, cấp executor có số thread/queue hữu hạn, hiểu propagation của security context và thiết kế failure handling. Đẩy nguyên `AuthorizationGrantedEvent` sang thread khác đặc biệt nguy hiểm vì object có thể giữ `HttpServletRequest` và `Supplier<Authentication>` gắn với ngữ cảnh request.

Cách xử lý an toàn hơn là **trích xuất DTO nhỏ ngay lúc có context**, ví dụ `timestamp, policyId, decision, correlationId, principalRef đã ẩn danh`, rồi đưa DTO qua bounded queue; công việc nặng thực hiện ngoài đường xử lý request. Không serialize context bảo mật hay entity chứa dữ liệu riêng tư.

### Khi nào bắt buộc phải ghi đầy đủ?

Những hành động như cấp role quản trị, thay đổi ACL, ký duyệt hoặc xuất dữ liệu nhạy cảm thường cần audit **nghiệp vụ** chi tiết. Khi đó:

- Cần định nghĩa **mốc nghiệp vụ** ghi nhận thành công: command được chấp nhận, giao dịch commit hay external side effect hoàn tất.
- Phải có delivery semantics rõ: at-most-once, at-least-once, retry, deduplication.
- Cần đáp ứng retention, truy cập audit, mã hóa và tuân thủ chính sách của hệ thống.
- `AuthorizationGrantedEvent` có thể là tín hiệu phụ ở tầng security, nhưng **không được coi là bằng chứng đã hoàn thành giao dịch**.

### Không để listener làm hỏng luồng authorization

Publisher và listener quan sát cần nhẹ và ổn định. Nếu log collector ngắt kết nối, chính sách lỗi phải được xác định trước: với telemetry tùy chọn có thể drop có metric; với audit bắt buộc, ứng dụng cần thiết kế bảo đảm dữ liệu cụ thể. Không ngầm nuốt lỗi của nghiệp vụ, không âm thầm biến request thành allowed/denied vì một hệ thống báo cáo phụ gặp sự cố.

## 11. Sự kiện grant có thể “nhân bản” theo nhiều cơ chế

| Tình huống | Hiện tượng | Hướng xử lý |
|---|---|---|
| URL authorization và `@PreAuthorize` cùng kiểm tra | Một request có nhiều kết quả granted | Gắn `surface`, chọn điểm quan sát và policy phù hợp; đừng giả định một request một event |
| FORWARD/ERROR dispatch | Có thể có thêm lần đánh giá bởi `AuthorizationFilter` | Cân nhắc dispatcher type, security config và thực tế dispatch |
| Dùng `permitAll()` | Request vẫn có thể đi qua điểm đánh giá authorization | Không bật grant event toàn cục chỉ để đếm HTTP request |
| Batch gọi hàng nghìn method có security | Event method-level tăng theo số lần gọi | Giảm scope, aggregate hoặc lấy audit ở ranh giới batch |
| API có nhiều node/pod | Mỗi node tự đếm và sample | Tổng hợp theo metric tập trung; policy nhất quán giữa phiên bản |
| Một request có nhiều lần retry | Cùng người dùng có thể lặp lại quyền kiểm tra | Dùng correlation và idempotency key nếu nghiệp vụ đòi đối chiếu |

Thực tế quan trọng: **“grant event count” là số lần quyết định quyền được chọn để phát event**, không phải “số người dùng”, “số HTTP 200” hay “số thao tác đã hoàn tất”.

## 12. Tương thích API theo phiên bản

Ví dụ `SelectiveAuthorizationEventPublisher` ở trên dùng interface của **Spring Security 6.3.x**, nơi phương thức chính là:

```java
<T> void publishAuthorizationEvent(
    Supplier<Authentication> authentication,
    T securedObject,
    AuthorizationDecision decision);
```

Ở **Spring Security 6.4–6.5**, xuất hiện API `AuthorizationResult` bên cạnh `AuthorizationDecision`. Một số overload có thể được đánh dấu deprecated; khi nâng cấp, kiểm tra đúng Javadoc của phiên bản đang chạy trước khi đổi signature.

Ở **Spring Security 7.x**, `SpringAuthorizationEventPublisher` có API để thiết lập predicate chọn kết quả được phát (ví dụ `setShouldPublishResult` trên các bản 7.0/7.1). Khi dùng phiên bản đó, có thể chọn cách cấu hình predicate thay cho custom publisher. Đừng chép API 7.x vào project 6.3 vì sẽ không biên dịch. Tương tự, ví dụ method-level và request-level phải dùng đúng overload/type sự kiện của phiên bản.

**Điều không đổi về ý tưởng:** không phát mọi grant mặc định; chỉ thu những kết quả đáng quan sát, giữ đường deny, giới hạn chi phí, bảo vệ dữ liệu nhạy cảm và kiểm thử đúng behavior.

## 13. Các lỗi phổ biến

1. **Mặc định nghĩ mọi 200 đều tạo grant event.** Sai: HTTP response, authorization decision và event publication là ba lớp khác nhau.
2. **Tạo bean `@EventListener` rồi không thấy grant.** Thiếu publisher có chủ đích cho success; publisher mặc định chỉ tạo denied.
3. **Custom publisher chỉ xử lý granted.** Vô tình làm mất `AuthorizationDeniedEvent` và giảm visibility đối với truy cập trái phép.
4. **Lọc ở listener thay vì publisher.** Event vẫn được phát, tốn CPU và có thể đi vào listener/sink khác.
5. **Ghi raw principal, token hoặc URL.** Dễ rò rỉ PII và secret, tăng cardinality, rủi ro khi chia sẻ log.
6. **Bật event cho mọi lần check `@PreAuthorize`.** Tạo số bản ghi lớn hơn nhiều so với số HTTP request.
7. **Dùng sampling cho audit bắt buộc.** Không còn bằng chứng đầy đủ; khó điều tra theo từng user.
8. **Suy ra successful business action từ granted.** Controller hoặc transaction vẫn có thể thất bại.
9. **Gọi hệ thống log từ listener đồng bộ không giới hạn.** Sự cố downstream làm tăng latency API.
10. **Viết test chỉ kiểm tra status 200/403.** Không phát hiện chính sách event mới vô tình thu mọi success hoặc làm mất denied.

## 14. Checklist trước khi đưa vào vận hành

- [ ] Xác định loại grant thực sự cần ghi (ví dụ elevated privilege, quyền đọc dữ liệu nhạy cảm).
- [ ] Định nghĩa policy ID ổn định; không dùng raw URL, ID bản ghi hoặc thông tin cá nhân làm metric labels.
- [ ] Giữ deny path và có test rằng denied không biến mất.
- [ ] Test grant quan trọng được phát; grant thông thường được bỏ qua hoặc sampled đúng logic.
- [ ] Phân biệt request-level, method-level và dispatch; tránh đếm trùng theo giả định sai.
- [ ] Kiểm tra listener không làm thay đổi kết quả authorization, latency và bảo mật của response.
- [ ] Có giới hạn throughput, queue, retention, retry và cảnh báo drop cho event pipeline.
- [ ] Có audit nghiệp vụ riêng nếu cần chứng minh hành động thành công/commit.
- [ ] Xác định version Spring Security, compile test trên bản thực tế, kiểm tra behavior sau nâng cấp.

## 15. Tài liệu đối chiếu

- [Spring Security 6.5 – Authorization Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/events.html): publisher, denied, granted và ví dụ lọc sự kiện thành công.
- [Spring Security 6.3 – AuthorizationEventPublisher Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authorization/AuthorizationEventPublisher.html): contract dùng `AuthorizationDecision`.
- [Spring Security 6.3 – SpringAuthorizationEventPublisher Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authorization/SpringAuthorizationEventPublisher.html): chỉ phát denied theo mặc định.
- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, đối tượng `HttpServletRequest` và dispatch.
- [Spring Security 7.1 – SpringAuthorizationEventPublisher Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/SpringAuthorizationEventPublisher.html): API chọn kết quả phát event ở các bản mới.
- [Spring Framework – Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events): `ApplicationEventPublisher` và `@EventListener`.