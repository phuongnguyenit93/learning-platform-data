# Đọc sự kiện đăng nhập, đăng nhập thất bại và từ chối truy cập

## 1. Ba câu hỏi khác nhau khi kiểm toán bảo mật

Trong chương HTTP và kiểm toán của Spring Boot Actuator, sự kiện kiểm toán (audit event) giúp trả lời: danh tính nào vừa được xác thực, lần xác thực nào thất bại, và ai bị chặn khi yêu cầu một tài nguyên. Đây là những mốc quyết định bảo mật; chúng bổ sung ngữ cảnh mà một mã HTTP đơn lẻ không thể diễn tả.

**Xác thực (authentication)** kiểm tra “bạn là ai?”. **Phân quyền (authorization)** kiểm tra “bạn có được thực hiện việc này không?”. Vì hai phép kiểm tra có mục đích khác nhau, một người có thể xác thực thành công rồi vẫn bị từ chối truy cập.

| Tình huống | Loại audit mặc định cần tìm | Cách hiểu đúng |
| --- | --- | --- |
| Thông tin xác thực được chấp nhận | `AUTHENTICATION_SUCCESS` | Bước xác thực thành công; chưa chứng minh yêu cầu nghiệp vụ thành công |
| Thông tin xác thực bị bác bỏ | `AUTHENTICATION_FAILURE` | Một lần xác thực thất bại; cần đọc thêm nguyên nhân |
| Quyết định phân quyền không cho phép truy cập | `AUTHORIZATION_FAILURE` | Yêu cầu không đáp ứng quyền truy cập; không đồng nghĩa sai mật khẩu |

Ví dụ: Alice nhập đúng mật khẩu và gọi tài nguyên chỉ dành cho quản trị viên. Có thể có cả `AUTHENTICATION_SUCCESS` và `AUTHORIZATION_FAILURE` cho Alice. Hai bản ghi này mô tả hai giai đoạn của cùng tình huống, không mâu thuẫn nhau.

Spring Boot cung cấp các listener chuyển sự kiện Spring Security thành audit. Khung audit cần một bean `AuditEventRepository`; không nên giả định chỉ thêm starter Actuator là đã có kho lịch sử bảo mật. [Tài liệu Auditing của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

## 2. Sự kiện đi từ Spring Security đến Actuator như thế nào?

```text
Yêu cầu HTTP
  -> Spring Security kiểm tra xác thực / phân quyền
  -> Phát sự kiện bảo mật tương ứng
  -> AuthenticationAuditListener / AuthorizationAuditListener
  -> AuditApplicationEvent chứa AuditEvent
  -> AuditListener lưu vào AuditEventRepository
  -> GET /actuator/auditevents đọc các bản ghi phù hợp bộ lọc
```

Có thể đọc bằng HTTP qua endpoint, đọc trực tiếp repository trong Java, hoặc quan sát `AuditApplicationEvent` khi nó được phát. Ba cách này phục vụ các thời điểm khác nhau: endpoint/repository truy vấn dữ liệu đã lưu, còn listener quan sát sự kiện đang diễn ra.

Trong Spring Boot 3.3, `AuthenticationAuditListener` chuyển sự kiện xác thực thành công và các sự kiện thất bại sang hai loại audit tương ứng. `AuthorizationAuditListener` xử lý `AuthorizationDeniedEvent` để tạo `AUTHORIZATION_FAILURE`; không có quy tắc rằng mọi HTTP 403 đều tự động biến thành audit này. [Mã nguồn AuthorizationAuditListener 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/security/AuthorizationAuditListener.java).

Với cơ chế `authorizeHttpRequests` của Spring Security 6.3, bộ cấu hình gắn publisher cho `AuthorizationFilter`: dùng bean `AuthorizationEventPublisher` nếu có, hoặc tạo `SpringAuthorizationEventPublisher`. Vì thế không được kết luận rằng cấu hình chuẩn này luôn thiếu sự kiện nếu chưa khai báo bean publisher riêng. Khi tự tạo filter/manager/luồng xác thực, phải kiểm tra việc nối publisher thực tế. [Mã nguồn AuthorizeHttpRequestsConfigurer 6.3.0](https://github.com/spring-projects/spring-security/blob/6.3.0/config/src/main/java/org/springframework/security/config/annotation/web/configurers/AuthorizeHttpRequestsConfigurer.java).

`SpringAuthorizationEventPublisher` 6.3 mặc định chỉ phát quyết định từ chối; việc không thấy bản ghi “phân quyền thành công” là phù hợp với cơ chế này. Không tự suy diễn một loại `AUTHORIZATION_SUCCESS` từ `AUTHENTICATION_SUCCESS`. [Mã nguồn SpringAuthorizationEventPublisher 6.3.0](https://github.com/spring-projects/spring-security/blob/6.3.0/core/src/main/java/org/springframework/security/authorization/SpringAuthorizationEventPublisher.java).

## 3. Đọc các trường của một bản ghi

Phản hồi có mảng `events`. Ví dụ dưới đây là **dữ liệu minh họa đã lược bớt trường**, không phải kết quả nguyên văn bắt buộc của mọi lần chạy:

```json
{
  "events": [
    {
      "timestamp": "2026-01-01T10:00:00Z",
      "principal": "alice",
      "type": "AUTHENTICATION_SUCCESS"
    },
    {
      "timestamp": "2026-01-01T10:00:10Z",
      "principal": "alice",
      "type": "AUTHENTICATION_FAILURE",
      "data": {
        "type": "org.springframework.security.authentication.BadCredentialsException",
        "message": "Bad credentials"
      }
    },
    {
      "timestamp": "2026-01-01T10:00:20Z",
      "principal": "alice",
      "type": "AUTHORIZATION_FAILURE"
    }
  ]
}
```

| Trường | Ý nghĩa | Điểm cần kiểm tra |
| --- | --- | --- |
| `timestamp` | Thời điểm sự kiện | Đọc kèm múi giờ; `Z` là UTC, không phải giờ địa phương |
| `principal` | Tên chủ thể gắn với lần kiểm tra | Với xác thực thất bại, có thể là tên người gửi tự khai, chưa được xác minh |
| `type` ở cấp sự kiện | Loại audit | Dùng để phân loại thành công xác thực, thất bại xác thực, hoặc thất bại phân quyền |
| `data` | Dữ liệu bổ sung tùy listener và hoàn cảnh | Có thể có `type`, `message`, `details`; không giả định mọi bản ghi đều có cùng cấu trúc |

**Phân biệt hai trường cùng tên:** `events[i].type` có thể là `AUTHENTICATION_FAILURE`, còn `events[i].data.type` có thể là tên lớp ngoại lệ như `BadCredentialsException`. Tham số truy vấn `type=AUTHENTICATION_FAILURE` lọc loại audit cấp ngoài, không lọc tên ngoại lệ bên trong.

Ở listener xác thực mặc định của Boot 3.3, thất bại có thông tin ngoại lệ và thông điệp; `details` được bổ sung khi đối tượng xác thực có dữ liệu này. `BadCredentialsException` cho biết thông tin xác thực không được chấp nhận, nhưng không đủ để kết luận tên tài khoản có tồn tại hay không. Một tài khoản bị khóa, hết hạn hoặc lỗi dịch vụ xác thực cũng không nên bị gom thành “nhập sai mật khẩu”.

`data.details` của một luồng web có thể chứa địa chỉ kết nối và mã phiên. Đây không phải hợp đồng rằng mọi sự kiện đều có IP, URL, mã HTTP hay session ID. Đặc biệt, audit từ chối truy cập mặc định không bảo đảm chứa tài nguyên bị chặn; cần đối chiếu với thông tin HTTP hoặc cơ chế bổ sung ngữ cảnh đã thiết kế.

Với truy cập ẩn danh, chủ thể có thể là `anonymousUser`; một số trường hợp không lấy được thông tin xác thực có thể là `<unknown>`. Không biến các giá trị này thành danh tính người dùng đã đăng nhập.

## 4. Thí nghiệm cục bộ với Spring Boot 3.3 và Java 17+

Ví dụ sau là một ứng dụng Spring MVC độc lập để quan sát ba tình huống. Mã dùng Spring Boot **3.3.0** và Spring Security **6.3.0** theo quản lý phụ thuộc của Boot; đây là mốc tái hiện ví dụ, không phải khuyến nghị chọn bản vá cho triển khai. Có thể chạy bằng JDK 17 hoặc JDK 21.

Tạo dự án Gradle Java có wrapper tương thích với Boot 3.3. Đặt các tệp theo cấu trúc:

```text
audit-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat và gradle/wrapper/
  src/main/java/example/audit/AuditDemoApplication.java
  src/main/resources/application.yml
```

`settings.gradle`:

```groovy
rootProject.name = 'audit-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

`src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  auditevents:
    enabled: true
  endpoint:
    auditevents:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,auditevents
```

Ba công tắc có vai trò khác nhau: `management.auditevents.enabled` điều khiển cấu hình khung audit; `management.endpoint.auditevents.enabled` điều khiển endpoint; `management.endpoints.web.exposure.include` quyết định endpoint có được đưa ra HTTP hay không. Thu thập sự kiện và công khai endpoint là hai việc riêng. Endpoint `auditevents` còn cần repository. [AuditAutoConfiguration 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/audit/AuditAutoConfiguration.html), [cấu hình endpoint của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

`src/main/java/example/audit/AuditDemoApplication.java`:

```java
package example.audit;

import java.security.Principal;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.AuditEventsEndpoint;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@RestController
public class AuditDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuditDemoApplication.class, args);
    }

    @Bean
    AuditEventRepository auditEventRepository() {
        return new InMemoryAuditEventRepository(1000);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-demo"))
                .roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-demo"))
                .roles("USER", "ADMIN").build(),
            User.withUsername("auditor")
                .password(encoder.encode("audit-demo"))
                .roles("AUDIT").build()
        );
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher publisher) {
        return new DefaultAuthenticationEventPublisher(publisher);
    }

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher publisher) {
        return new SpringAuthorizationEventPublisher(publisher);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(EndpointRequest.to(AuditEventsEndpoint.class))
                    .hasRole("AUDIT")
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/admin/report").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @GetMapping("/profile")
    String profile(Principal principal) {
        return "profile:" + principal.getName();
    }

    @GetMapping("/admin/report")
    String report() {
        return "admin-report";
    }
}
```

Các lựa chọn trong ví dụ:

- `alice` có quyền `USER`; `bob` có thêm `ADMIN`; `auditor` chỉ có `AUDIT` để đọc lịch sử. Có quyền quản trị nghiệp vụ không tự động có quyền kiểm toán.
- `InMemoryAuditEventRepository(1000)` lưu tối đa 1.000 sự kiện trong bộ nhớ của tiến trình. Nó phù hợp cho thí nghiệm; khởi động lại sẽ mất dữ liệu và khi đầy sẽ thay thế sự kiện cũ.
- Hai bean publisher được khai báo rõ để nhìn thấy điểm nối với hệ thống sự kiện. Trong ứng dụng có cấu hình chuẩn sẵn, kiểm tra bean hiện có trước khi thêm; không tạo thêm một đường phát/lưu trùng lặp.
- Cấu hình `STATELESS` khiến các yêu cầu Basic của thí nghiệm không dựa vào phiên đăng nhập trước đó. Một yêu cầu mới mang thông tin đúng có thể phát một sự kiện xác thực thành công mới.
- Chỉ những yêu cầu được phân phối nội bộ theo kiểu `ERROR` được bỏ qua bước phân quyền lần nữa trong ví dụ; điều này tránh làm lần xử lý trang lỗi che mất kết quả quan sát ban đầu. Quyền của yêu cầu HTTP gốc vẫn được kiểm tra.
- Toàn bộ phép thử dùng GET, không cần tắt CSRF. Không sao chép cách tắt CSRF chỉ để sửa một HTTP 403 chưa rõ nguyên nhân.

Ứng dụng chỉ lắng nghe trên `127.0.0.1`. Các mật khẩu trong mã là dữ liệu mẫu dành cho máy cá nhân. Khi dùng Basic qua mạng thực, cần HTTPS và cơ chế quản lý thông tin xác thực phù hợp.

Khởi động tại thư mục dự án:

```bash
./gradlew bootRun
```

Trên Windows PowerShell dùng `.\gradlew.bat bootRun`. Các lệnh HTTP bên dưới dùng curl; trên PowerShell có alias `curl`, hãy gọi `curl.exe`. Ứng dụng này cần các phụ thuộc Spring nên không chạy bằng `javac AuditDemoApplication.java` đơn lẻ.

## 5. Tạo và kiểm chứng ba loại sự kiện

Giữ ứng dụng chạy, dùng cửa sổ terminal khác. Không gửi cookie phiên từ các phép thử khác.

### 5.1. Xác thực thành công

```bash
curl -i -u alice:alice-demo http://127.0.0.1:8080/profile
```

Kỳ vọng HTTP 200, phần thân chính xác là `profile:alice`. Yêu cầu đã xác thực và được phép gọi `/profile`; tra audit của Alice sẽ thấy `AUTHENTICATION_SUCCESS`. Không lấy loại sự kiện này làm bằng chứng rằng mọi API Alice gọi sau đó đều được phép.

### 5.2. Xác thực thất bại

```bash
curl -i -u alice:wrong-demo http://127.0.0.1:8080/profile
```

Kỳ vọng HTTP 401 và có `AUTHENTICATION_FAILURE` cho tên `alice`. Cần đọc thêm `data.type` và `data.message`; ở ví dụ sai mật khẩu này thường là `BadCredentialsException` với thông điệp `Bad credentials`. Ngôn ngữ/thông điệp lỗi có thể thay đổi khi tùy biến.

### 5.3. Xác thực đúng nhưng thiếu quyền

```bash
curl -i -u alice:alice-demo http://127.0.0.1:8080/admin/report
```

Kỳ vọng HTTP 403. Alice có thể có thêm một `AUTHENTICATION_SUCCESS` vì mật khẩu đúng, rồi `AUTHORIZATION_FAILURE` vì thiếu `ROLE_ADMIN`. Đối chiếu bằng tài khoản có quyền:

```bash
curl -i -u bob:bob-demo http://127.0.0.1:8080/admin/report
```

Kỳ vọng HTTP 200, phần thân chính xác là `admin-report`. Không yêu cầu xuất hiện `AUTHORIZATION_SUCCESS` để công nhận kết quả này.

| Phép thử | HTTP kỳ vọng trong cấu hình mẫu | Dấu hiệu audit chính |
| --- | --- | --- |
| Alice gọi `/profile`, đúng mật khẩu | 200 | `AUTHENTICATION_SUCCESS` |
| Alice gọi `/profile`, sai mật khẩu | 401 | `AUTHENTICATION_FAILURE` |
| Alice gọi `/admin/report`, đúng mật khẩu | 403 | `AUTHENTICATION_SUCCESS` và `AUTHORIZATION_FAILURE` |
| Bob gọi `/admin/report`, đúng mật khẩu | 200 | `AUTHENTICATION_SUCCESS` |

Đây là kết quả của cấu hình mẫu, không phải bảng quy đổi phổ quát giữa HTTP và audit. Đăng nhập bằng biểu mẫu có thể dùng chuyển hướng 302; cổng trung gian có thể trả lỗi trước khi yêu cầu tới ứng dụng; CSRF có thể chặn yêu cầu; mã ứng dụng có thể tự trả 403 mà không có quyết định phân quyền tương ứng.

Yêu cầu không mang thông tin xác thực cũng khác yêu cầu mang mật khẩu sai. Chẳng hạn, một người ẩn danh truy cập tài nguyên được bảo vệ có thể bị từ chối phân quyền và nhận 401 từ cơ chế yêu cầu xác thực, dù chưa có lần kiểm tra mật khẩu nào thất bại.

## 6. Đọc bằng endpoint và dùng bộ lọc

Đọc toàn bộ những sự kiện còn được repository giữ:

```bash
curl -s -u auditor:audit-demo http://127.0.0.1:8080/actuator/auditevents
```

Để tập trung vào Alice, lọc theo `principal`:

```bash
curl -s -u auditor:audit-demo -G http://127.0.0.1:8080/actuator/auditevents --data-urlencode "principal=alice"
```

Lọc riêng các lần xác thực thất bại của Alice sau một mốc thời gian:

```bash
curl -s -u auditor:audit-demo -G http://127.0.0.1:8080/actuator/auditevents --data-urlencode "principal=alice" --data-urlencode "type=AUTHENTICATION_FAILURE" --data-urlencode "after=1970-01-01T00:00:00Z"
```

Mốc 1970 trong lệnh giúp ví dụ không bỏ sót dữ liệu của lần chạy hiện tại. Khi điều tra thực tế, dùng mốc sát khoảng thời gian cần tìm để thu hẹp kết quả. Đổi loại thành `AUTHENTICATION_SUCCESS` hoặc `AUTHORIZATION_FAILURE` để kiểm chứng hai nhóm còn lại.

| Tham số | Cách sử dụng |
| --- | --- |
| `principal` | Tên chủ thể; với kho in-memory của ví dụ là khớp chính xác, không phải tìm chuỗi con |
| `type` | Một loại audit cụ thể; phân biệt hoa/thường trong ví dụ |
| `after` | Mốc ISO-8601 có múi giờ; kho in-memory lấy sự kiện có thời điểm **sau**, không gồm sự kiện đúng tại mốc |

Các tham số là tùy chọn và khi kết hợp thì cùng thu hẹp tập kết quả. Endpoint không cung cấp sẵn bộ lọc `before`, số trang hay tổng số bản ghi lịch sử toàn hệ thống. Đừng tự thêm `page`/`size` rồi cho rằng dữ liệu đã được phân trang. [Hợp đồng HTTP của auditevents](https://docs.spring.io/spring-boot/api/rest/actuator/auditevents.html).

`after` có thể dùng `Z` hoặc độ lệch múi giờ hợp lệ. Dùng `--data-urlencode` đặc biệt hữu ích với độ lệch như `+07:00`, vì ký tự `+` trong query string có thể bị diễn giải thành khoảng trắng nếu ghép URL thủ công.

**Bản thân người đọc cũng tạo dấu vết:** trong cấu hình Basic stateless, yêu cầu của `auditor` có thể tạo thêm `AUTHENTICATION_SUCCESS` trước khi endpoint trả dữ liệu. Vì vậy không khẳng định mảng sẽ có đúng bốn hay năm phần tử. Lọc `principal=alice` giúp tách các phép thử khỏi hoạt động truy vấn của người kiểm toán.

Có thể kiểm tra ranh giới quyền đọc bằng lệnh sau:

```bash
curl -i -u alice:alice-demo http://127.0.0.1:8080/actuator/auditevents
```

Kỳ vọng 403 vì Alice không có `AUDIT`. Phép thử này lại tạo thêm sự kiện của Alice; nếu cần một tập dữ liệu thí nghiệm sạch, khởi động lại ứng dụng rồi chỉ thực hiện đúng chuỗi yêu cầu đã chọn.

## 7. Đọc trong Java và quan sát sự kiện mới

Khi viết thành phần nội bộ cần truy vấn audit, tiêm `AuditEventRepository` và gọi `find(principal, after, type)`. Ví dụ dưới đây là một Spring component bổ sung cho ứng dụng phía trên, không phải chương trình có `main` riêng:

```java
package example.audit;

import java.time.Instant;
import java.util.List;

import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.stereotype.Service;

@Service
public class AuditReader {
    private final AuditEventRepository repository;

    public AuditReader(AuditEventRepository repository) {
        this.repository = repository;
    }

    public List<AuditEvent> failedAuthentications(String principal, Instant after) {
        return repository.find(principal, after, "AUTHENTICATION_FAILURE");
    }
}
```

`after` trong API repository là `Instant`; endpoint HTTP nhận thời gian có múi giờ rồi chuyển về thời điểm tương ứng. Không nhầm thứ tự đối số thành `find(type, after, principal)`. `null` ở một tiêu chí của kho in-memory có nghĩa bỏ lọc tiêu chí đó.

Muốn quan sát ngay khi audit được phát, có thể thêm component sau. Nó chỉ ghi thời gian và loại sự kiện, tránh in toàn bộ dữ liệu của người dùng:

```java
package example.audit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.listener.AuditApplicationEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AuditObserver {
    private static final Logger log = LoggerFactory.getLogger(AuditObserver.class);

    @EventListener
    public void onAudit(AuditApplicationEvent applicationEvent) {
        AuditEvent event = applicationEvent.getAuditEvent();
        if ("AUTHENTICATION_FAILURE".equals(event.getType())
                || "AUTHORIZATION_FAILURE".equals(event.getType())) {
            log.info("Security audit at={} type={}",
                event.getTimestamp(), event.getType());
        }
    }
}
```

Listener trên không đọc lại các sự kiện đã xảy ra trước khi nó hoạt động và không thay thế repository. Đừng gọi `repository.add(event)` thêm trong listener này khi listener lưu trữ mặc định của Boot đang chạy: có thể lưu hai lần cùng một sự kiện. Cũng không thực hiện gửi mạng hoặc xử lý nặng đồng bộ trong đường xử lý đăng nhập chỉ để xem một bản ghi.

## 8. Điều tra theo bằng chứng thay vì suy đoán

Một cách đọc có hệ thống là chọn khoảng thời gian, lọc chủ thể/loại sự kiện, đọc nguyên nhân, rồi đối chiếu với dữ liệu HTTP và cấu hình quyền tại thời điểm xảy ra:

1. **Xác định thời gian và phiên bản cấu hình.** Quy đổi UTC/giờ địa phương trước khi ghép sự kiện; không chỉ so tên giờ.
2. **Phân biệt danh tính đã xác thực và tên được khai báo.** Với thất bại xác thực, `principal=alice` chưa chứng minh chính Alice là người thao tác.
3. **Đọc nguyên nhân xác thực.** Sai thông tin, tài khoản bị khóa và dịch vụ xác thực gặp lỗi đòi hỏi các bước xử lý khác nhau.
4. **Kiểm tra quyền khi bị từ chối.** Xem các quyền thực sự được cấp, quy tắc khớp đường dẫn, và cơ chế bảo vệ phương thức nếu có. Không xử lý mọi `AUTHORIZATION_FAILURE` bằng đổi mật khẩu.
5. **Đối chiếu thêm ngữ cảnh.** Audit mặc định không bảo đảm có URL/mã HTTP/request ID; dùng dữ liệu HTTP hoặc ngữ cảnh đã bổ sung để xác nhận tài nguyên cụ thể. Không gán hai bản ghi cho cùng một yêu cầu chỉ vì cùng tên người dùng và gần thời gian.
6. **Diễn đạt kết luận đúng mức.** “Có nhiều lần xác thực thất bại cho tên Alice” là bằng chứng; “Alice bị tấn công dò mật khẩu” còn cần ngữ cảnh, tần suất và xác minh thêm.

Các yêu cầu đồng thời có thể đan xen sự kiện. Không mặc định hai phần tử đứng cạnh nhau trong mảng là một cặp xác thực/phân quyền của cùng yêu cầu, và không mặc định thứ tự trả về của mọi repository đều giống nhau.

## 9. Khi không thấy sự kiện mong đợi

| Hiện tượng | Cần kiểm tra trước |
| --- | --- |
| Endpoint không truy cập được / 404 | Có bean repository không; endpoint có được bật và expose không; đúng cổng, base path, context path và instance không |
| Endpoint trả 401/403 | Quyền của người **đọc audit**; không vội kết luận kho audit hỏng |
| `events` rỗng | Bộ lọc thời gian/loại/tên có đúng không; đã thực sự tạo sự kiện chưa; tiến trình có vừa khởi động lại không |
| HTTP 401 nhưng không có `AUTHENTICATION_FAILURE` | Yêu cầu có gửi thông tin xác thực không; lỗi phát sinh ở ứng dụng hay cổng trung gian; có dùng publisher trong luồng xác thực thực tế không |
| HTTP 403 nhưng không có `AUTHORIZATION_FAILURE` | Có phải quyết định từ chối qua cơ chế authorization đang phát sự kiện không; hay CSRF, mã nghiệp vụ, proxy hoặc một cơ chế khác trả lỗi |
| Thiếu bản ghi cũ | Giới hạn kho in-memory, khởi động lại, hoặc đang đọc nhầm instance |
| Một thao tác có nhiều bản ghi | Basic stateless, nhiều yêu cầu từ trình duyệt, error dispatch, nhiều tầng phân quyền, hoặc listener lưu trùng |
| Không có URL hay nguyên nhân trong bản ghi từ chối | Không phải mọi trường đều được listener mặc định cung cấp; xác minh hợp đồng dữ liệu thay vì đoán |

Không sửa bằng cách expose toàn bộ Actuator hoặc cho phép mọi người đọc audit. Trước tiên tách ba bước: **sự kiện có được phát không → có được lưu không → người đọc có truy vấn đúng và đủ quyền không**.

## 10. Giới hạn khi áp dụng ngoài thí nghiệm

`InMemoryAuditEventRepository` là kho cục bộ, dung lượng hữu hạn và không bền vững. Nếu có nhiều instance, mỗi instance giữ một phần lịch sử riêng; một lần truy vấn qua bộ cân bằng tải không đại diện toàn bộ hệ thống. Cần repository/lưu trữ tập trung phù hợp nếu yêu cầu điều tra đòi hỏi dữ liệu qua lần khởi động và qua nhiều instance.

Quyền đọc audit nên được cấp theo nhiệm vụ. Tên tài khoản, địa chỉ kết nối, mã phiên và thông điệp lỗi có thể nhạy cảm; không xuất tùy tiện toàn bộ `data`, không lưu mật khẩu hay token vào sự kiện tùy biến, và không giả định endpoint tự che mọi thông tin này. Với IP sau proxy, chỉ tin thông tin chuyển tiếp khi chuỗi proxy và chính sách tin cậy đã được cấu hình.

Đếm thất bại để cảnh báo hay khóa tài khoản cần thêm chính sách, cửa sổ thời gian và xử lý đồng thời. Repository in-memory cùng ba loại sự kiện không tự tạo một cơ chế chống dò mật khẩu hoàn chỉnh. Khóa theo tên chưa xác minh còn có thể bị lợi dụng để làm tài khoản người khác không sử dụng được.

## 11. Tự kiểm tra

1. Alice gọi `/admin/report` bằng mật khẩu đúng nhưng nhận 403. Giải thích vì sao `AUTHENTICATION_SUCCESS` và `AUTHORIZATION_FAILURE` có thể cùng xuất hiện.
2. Đọc một `AUTHENTICATION_FAILURE` của Alice: trường nào là loại audit, trường nào có thể là tên ngoại lệ? Vì sao chưa thể nói Alice thực sự là người gửi?
3. Truy vấn riêng các lần Alice bị từ chối quyền, rồi truy vấn riêng các lần xác thực thất bại. Không trộn hai nhóm thành “đăng nhập sai”.
4. Đọc audit bằng `auditor` hai lần. Giải thích vì sao số bản ghi thành công có thể tăng dù không gọi thêm API nghiệp vụ.
5. Khởi động lại ứng dụng và truy vấn lại. Nêu lý do tập dữ liệu cũ mất và hệ quả khi cần điều tra sự cố nhiều ngày.
6. Gặp HTTP 403 nhưng không có audit tương ứng: kiểm tra nguồn trả lỗi và đường phát sự kiện trước khi đổi mật khẩu hay nới quyền.

Các phép thử đạt mục tiêu khi người học phân biệt được **kết quả xác thực**, **quyết định phân quyền** và **kết quả HTTP**, đồng thời truy vấn được đúng bản ghi cùng giới hạn dữ liệu của nó.
