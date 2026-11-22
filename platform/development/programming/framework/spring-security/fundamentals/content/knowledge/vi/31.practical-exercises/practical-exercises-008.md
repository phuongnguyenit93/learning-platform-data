# Viết kiểm thử chứng minh endpoint mới không bị bỏ sót

## 1. Vấn đề: thêm endpoint là thêm một bề mặt truy cập

Giả sử hệ thống đã có API đọc và tạo tài liệu. Sau vài tuần, một lập trình viên bổ sung `GET /api/reports/export` để xuất báo cáo. Phương thức controller có thể chạy được ngay, nhưng **ai được phép gọi endpoint đó** vẫn là một quyết định bảo mật cần được xem xét.

Có ít nhất ba kiểu lỗi:

1. **Endpoint mới được mở ngoài ý muốn:** cấu hình có quy tắc quá rộng như `/api/**.permitAll()` hoặc `anyRequest().authenticated()`, khiến người dùng không đủ quyền vẫn truy cập được.
2. **Endpoint mới bị chặn nhưng không ai phát hiện:** `anyRequest().denyAll()` giúp từ chối mặc định, song chức năng mới có thể bị `403` trong sản xuất vì lập trình viên quên khai báo chính sách. Chỉ có fallback an toàn chưa đủ chứng minh mọi endpoint đã được rà soát.
3. **Test cho cảm giác an toàn giả:** request đến URL không có controller bị `404`, hoặc thiếu CSRF token đã bị `403` trước khi kiểm tra authority. Test chỉ kiểm tra một status mà không xác minh route và nguyên nhân có thể bỏ sót lỗi thật.

Bài thực hành kết hợp **hai lớp bảo đảm có mục tiêu khác nhau**:

- **Chặn mặc định (fail closed):** mọi HTTP request không có chính sách rõ ràng đều bị `denyAll()`.
- **Kiểm kê endpoint (route coverage):** kiểm thử tự động đọc những route MVC thực sự được Spring đăng ký và so với danh sách route đã được phân loại quyền. Khi thêm một route mà quên duyệt chính sách, bài test phải **đỏ ngay khi chạy CI**.

Sau đó viết test phân quyền hành vi cho chính endpoint mới: khách chưa đăng nhập nhận `401`, tài khoản không có quyền nhận `403`, tài khoản có quyền nhận `200`. Bài học không chỉ hỏi “endpoint có bị chặn không?” mà còn hỏi “endpoint đã có chính sách đúng, có thể kiểm chứng không?”.

**Phạm vi triển khai:** Spring Boot 3.5.x, Java 17+, Spring MVC/Servlet và Spring Security 6.x; các tài khoản và dữ liệu đều là ví dụ học tập. Nếu dự án dùng WebFlux, cần áp dụng mô hình kiểm kê router và bộ kiểm thử `WebTestClient` tương ứng, không sao chép code MVC một cách máy móc.

## 2. Thiết kế ma trận quyền trước khi tạo route

Ứng dụng demo có ba người dùng:

| Tài khoản | Authority | Mục đích |
| --- | --- | --- |
| `alice` | `document:read` | Chỉ đọc tài liệu |
| `bob` | `document:read`, `document:write` | Đọc và tạo tài liệu |
| `eva` | `report:export` | Chỉ được xuất báo cáo |

**Route mới** là `GET /api/reports/export` và đòi hỏi chính xác `report:export`. Tài khoản `bob` có quyền viết tài liệu nhưng **không** có quyền xuất báo cáo; không có quan hệ kế thừa ngầm giữa những authority khác nhau.

| HTTP route | Anonymous | `alice` | `bob` | `eva` |
| --- | --- | --- | --- | --- |
| `GET /public/ping` | `200` | `200` | `200` | `200` |
| `GET /api/documents/42` | `401` | `200` | `200` | `403` |
| `POST /api/documents`, có CSRF hợp lệ | `401` | `403` | `201` | `403` |
| **`GET /api/reports/export` (mới)** | **`401`** | **`403`** | **`403`** | **`200`** |
| `GET /api/unknown` | Bị chặn | `403` | `403` | `403` |
| `POST /api/reports/export`, có CSRF hợp lệ | Bị chặn | `403` | `403` | `403` |

Trong hai dòng cuối, “bị chặn” có thể thể hiện qua `401`/`403` tùy entry point, method và cơ chế bảo mật. Bộ test chủ yếu kiểm chứng người **đã xác thực** để xác nhận quy tắc `denyAll`. Ví dụ dùng HTTP Basic nên request GET thiếu xác thực tới endpoint cần quyền nhận `401`. Request POST của người đã đăng nhập phải mang CSRF token hợp lệ để lỗi `403` phản ánh **quyền** thay vì bị CSRF chặn trước.

Đặt tên cho từng loại chính sách: `PUBLIC` (ai cũng được), `DOC_READ`, `DOC_WRITE` và `REPORT_EXPORT`. Danh sách các route gắn với chính sách này là **danh mục đã rà soát** (reviewed inventory), không nên được tạo tự động từ controller; nếu tạo tự động, phép so sánh coverage không còn khả năng phát hiện route mới.

## 3. Cấu trúc dự án và phụ thuộc

Khởi tạo dự án Java 17+, Spring Boot 3.5.x với **Spring Web (MVC)**, **Spring Security**. Trong `build.gradle` của skeleton Spring Boot bảo đảm có các dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là đoạn `dependencies` và `tasks` của dự án đã được Spring Initializr tạo, không phải toàn bộ `build.gradle`. Ví dụ dùng package `com.example.routeaudit` và hai tệp:

- `src/main/java/com/example/routeaudit/RouteAuditApplication.java` — ứng dụng, danh mục route đã rà soát, cấu hình Security và controller.
- `src/test/java/com/example/routeaudit/RouteAuditApplicationTests.java` — kiểm thử đối chiếu danh mục với mapping thật và ma trận truy cập.

Ở đây toàn bộ lớp phụ trợ trong tệp Java chính là **package-private**; chỉ `RouteAuditApplication` là `public`. Vì thế chúng có thể cùng nằm trong một tệp Java duy nhất và được test trong cùng package truy cập.

## 4. Mã ứng dụng: danh mục chính sách, deny-all và endpoint mới

Tệp `src/main/java/com/example/routeaudit/RouteAuditApplication.java`:

~~~java
package com.example.routeaudit;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RouteAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(RouteAuditApplication.class, args);
    }
}

// Định danh route: HTTP method và path pattern phải khớp nhau.
record RouteKey(HttpMethod method, String path) {}

enum PermissionRule {
    PUBLIC, DOC_READ, DOC_WRITE, REPORT_EXPORT
}

record RoutePolicy(RouteKey route, PermissionRule rule) {}

// Được cập nhật sau khi rà soát quyền; không sinh từ controller.
final class ReviewedEndpointPolicies {
    private ReviewedEndpointPolicies() {}

    static final List<RoutePolicy> ALL = List.of(
        new RoutePolicy(
            new RouteKey(HttpMethod.GET, "/public/ping"),
            PermissionRule.PUBLIC),
        new RoutePolicy(
            new RouteKey(HttpMethod.GET, "/api/documents/{id}"),
            PermissionRule.DOC_READ),
        new RoutePolicy(
            new RouteKey(HttpMethod.POST, "/api/documents"),
            PermissionRule.DOC_WRITE),
        // Route mới đã được phân loại quyền rõ ràng:
        new RoutePolicy(
            new RouteKey(HttpMethod.GET, "/api/reports/export"),
            PermissionRule.REPORT_EXPORT)
    );

    static Set<RouteKey> keys() {
        return ALL.stream()
            .map(RoutePolicy::route)
            .collect(Collectors.toUnmodifiableSet());
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .authorities("document:read")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .authorities("document:read", "document:write")
                .build(),
            User.withUsername("eva")
                .password(encoder.encode("eva-pass"))
                .authorities("report:export")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> {
            // Mọi rule được lấy từ danh mục đã rà soát.
            for (RoutePolicy policy : ReviewedEndpointPolicies.ALL) {
                RouteKey route = policy.route();
                var match = auth.requestMatchers(
                    route.method(), route.path());

                switch (policy.rule()) {
                    case PUBLIC -> match.permitAll();
                    case DOC_READ ->
                        match.hasAuthority("document:read");
                    case DOC_WRITE ->
                        match.hasAuthority("document:write");
                    case REPORT_EXPORT ->
                        match.hasAuthority("report:export");
                }
            }

            // Không có policy: không được phép đi qua.
            auth.anyRequest().denyAll();
        });

        // Demo HTTP Basic; CSRF protection vẫn hoạt động mặc định.
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}

@RestController
class ApiController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/documents/{id}")
    String readDocument(@PathVariable("id") long id) {
        return "document:" + id;
    }

    @PostMapping("/api/documents")
    @ResponseStatus(HttpStatus.CREATED)
    String createDocument(@RequestParam("title") String title) {
        return "created:" + title;
    }

    // Endpoint được thêm sau ba endpoint có sẵn.
    @GetMapping("/api/reports/export")
    String exportReport() {
        return "report-exported";
    }
}
~~~

### Vì sao mẫu này có hai lớp bảo đảm?

**Thứ nhất, có chính sách cho từng route.** `ReviewedEndpointPolicies.ALL` lưu cả phương thức HTTP và mẫu đường dẫn. Trong `SecurityFilterChain`, mỗi phần tử được chuyển thành đúng matcher và yêu cầu quyền. `GET /api/reports/export` chỉ nhận `report:export`; `bob` không được coi là “quản trị” chỉ vì có `document:write`.

**Thứ hai, fallback chặn mọi request khác.** `anyRequest().denyAll()` đứng cuối danh sách rule, nên một endpoint mới chưa được thêm vào danh mục sẽ không được mở chỉ vì có tài khoản đăng nhập. Chúng ta chủ động chọn **một filter chain áp dụng toàn bộ ứng dụng MVC**: ví dụ không khai báo `securityMatcher("/api/something/**")` để giới hạn chain, vì phạm vi chain bị thu hẹp có thể khiến một route khác không được bảo vệ nếu không có chain dự phòng.

**Thứ ba, danh mục là đầu vào độc lập với controller.** Nếu ai đó thêm `@GetMapping("/api/internal/debug")` vào `ApiController` mà không thêm `RoutePolicy` tương ứng, route vẫn được Spring MVC đăng ký. Lúc đó:

- Về hành vi runtime, `anyRequest().denyAll()` từ chối request đến route vừa tạo.
- Về quy trình phát triển, bài test **kiểm kê mapping** ở phần tiếp theo thấy route mới xuất hiện trong MVC mà không có trong `ReviewedEndpointPolicies.ALL`, nên thất bại và buộc người viết xác định policy.

Nếu chỉ kiểm tra `/api/unknown` trả `403`, ta mới chứng minh **fallback**, chưa chứng minh tất cả controller route đã được rà soát. Vì thế cần cả hai kiểu test.

### Những chi tiết cần hiểu trước khi test

- `HttpMethod.GET` và `HttpMethod.POST` là một phần của khóa route: POST vào path chỉ có quyền GET phải bị chặn.
- `@GetMapping`, `@PostMapping` đăng ký route thật trong Spring MVC; trong bài này có bốn route và bốn `RoutePolicy`.
- Mật khẩu lưu trong bộ nhớ chỉ phục vụ bài thực hành. `PasswordEncoderFactories` mã hóa trước khi lưu, nhưng các mật khẩu mẫu vẫn nằm trong source; ứng dụng thật phải dùng nguồn danh tính và quản lý bí mật thích hợp.
- `GET` không yêu cầu CSRF token theo cấu hình mặc định; `POST` thường yêu cầu token. Bài test POST hợp lệ sẽ dùng `csrf()` để phép thử authority không bị lẫn với lỗi CSRF.
- Các route trả chuỗi cố định nên có thể kiểm tra cả **status** và **body**. Việc trả `200`/`201` không có nghĩa đã có dữ liệu được lưu ở database.

## 5. Viết kiểm thử: tự phát hiện mọi mapping MVC mới

Tệp `src/test/java/com/example/routeaudit/RouteAuditApplicationTests.java`:

~~~java
package com.example.routeaudit;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RouteAuditApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    RequestMappingHandlerMapping handlerMapping;

    @Test
    void everyApplicationRouteHasExplicitReviewedPolicy() {
        // Chỉ xét controller thuộc ứng dụng demo;
        // không so với /error và các endpoint của framework.
        var mappings = handlerMapping.getHandlerMethods()
            .entrySet().stream()
            .filter(entry -> entry.getValue().getBeanType()
                .getPackageName().equals("com.example.routeaudit"))
            .toList();

        assertThat(mappings).isNotEmpty();

        // Cấm @RequestMapping không khai báo rõ HTTP method.
        for (var entry : mappings) {
            RequestMappingInfo info = entry.getKey();
            assertThat(info.getMethodsCondition().getMethods())
                .as("HTTP method chưa rõ: %s", entry.getValue())
                .isNotEmpty();

            assertThat(info.getPatternValues())
                .as("Path chưa rõ: %s", entry.getValue())
                .isNotEmpty();
        }

        // Lấy (method, path) trực tiếp từ mapping Spring MVC.
        Set<RouteKey> registered = mappings.stream()
            .flatMap(entry -> entry.getKey()
                .getPatternValues().stream()
                .flatMap(path -> entry.getKey()
                    .getMethodsCondition().getMethods().stream()
                    .map(method -> new RouteKey(
                        HttpMethod.valueOf(method.name()), path))))
            .collect(Collectors.toSet());

        // Ngăn lặp cùng một khóa trong danh mục chính sách.
        assertThat(ReviewedEndpointPolicies.keys())
            .hasSize(ReviewedEndpointPolicies.ALL.size());

        // Thêm route mà chưa khai báo policy => kiểm thử FAIL.
        // Khai báo policy nhưng quên controller => cũng FAIL.
        assertThat(registered).containsExactlyInAnyOrderElementsOf(
            ReviewedEndpointPolicies.keys());
    }

    @Test
    void publicEndpointWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void documentReadStillChecksItsOwnAuthority()
            throws Exception {
        mvc.perform(get("/api/documents/42"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/documents/42")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("document:42"));

        mvc.perform(get("/api/documents/42")
                .with(httpBasic("eva", "eva-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void documentWriteNeedsAuthorityAndCsrf()
            throws Exception {
        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("bob", "bob-pass"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:Note"));

        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void newlyAddedExportHasItsOwnPermission()
            throws Exception {
        mvc.perform(get("/api/reports/export"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports/export")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/export")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/export")
                .with(httpBasic("eva", "eva-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-exported"));
    }

    @Test
    void unlistedPathsAndMethodsAreDenied()
            throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("eva", "eva-pass")))
            .andExpect(status().isForbidden());

        // POST vào URL chỉ có policy GET không được đi qua.
        // Cung cấp CSRF để loại trừ lỗi do thiếu CSRF.
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("eva", "eva-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
~~~

### Tại sao test kiểm kê route quan trọng?

`handlerMapping.getHandlerMethods()` trả về các mapping MVC **được Spring đăng ký trong ngữ cảnh ứng dụng thật**. Ta lọc controller theo package demo để tránh đếm `/error` hoặc mapping nội bộ của framework. Mỗi mapping cần khai báo HTTP method cụ thể; nếu một phương thức chỉ dùng `@RequestMapping("/api/example")` mà không chỉ định method, bài test chủ động **thất bại** thay vì âm thầm bỏ sót.

Tiếp theo, test tạo tập khóa `(HttpMethod, path)` từ `getPatternValues()` và `getMethodsCondition().getMethods()`; so với `ReviewedEndpointPolicies.keys()`. Hai tập phải **bằng nhau**:

- **Registered mà chưa reviewed:** có endpoint mới chưa được phân loại và chưa được mở có chủ đích.
- **Reviewed mà chưa registered:** có khai báo policy cho endpoint không tồn tại, hoặc endpoint đã đổi URL mà quên sửa danh mục.
- **Trùng route trong danh mục:** số lượng phần tử `ALL` khác số lượng khóa phân biệt nên phép thử thất bại.

Đây không phải phép thử mô phỏng chính danh sách route mà ta đã tự định nghĩa: **phía trái là sự thật từ Spring MVC; phía phải là danh sách chính sách do lập trình viên chủ động duy trì**. Điểm khác nhau đó giúp phát hiện endpoint bị bỏ sót.

### Vì sao vẫn cần MockMvc?

Kiểm kê chỉ xác minh mỗi route có **một chính sách được khai báo**; nó chưa chứng minh policy chọn đúng authority hay matcher thực sự chặn đúng người. `MockMvc` thực thi request qua Spring Security filter chain rồi đến MVC, nên có thể xác minh hành vi độc lập:

- Anonymous gọi `GET /api/reports/export` → `401`.
- `alice` có `document:read`, `bob` có `document:write` nhưng cả hai thiếu `report:export` → `403`.
- `eva` có `report:export` → `200` với body `report-exported`.
- `eva` không thể dùng POST trên path xuất báo cáo → `403` khi request có CSRF token; chứng minh **HTTP method** cũng được bao phủ.
- Người đã đăng nhập gọi `GET /api/unknown` → `403` nhờ fallback.

Khi một endpoint được phép đi qua chain nhưng không tồn tại controller, request có thể trả `404`. Vì vậy **test 403 trên một URL bất kỳ không đủ chứng minh route mới có thật**. Test kiểm kê Spring MVC kết hợp test body của endpoint mới loại bỏ sự nhập nhằng đó.

## 6. Chạy kiểm thử và làm thí nghiệm đỏ–xanh

Trong thư mục dự án Gradle đã được khởi tạo, chạy:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows PowerShell dùng `.\gradlew.bat test`, sau đó `.\gradlew.bat bootRun` nếu muốn thử request thật. Lệnh `test` tự dựng ngữ cảnh test, không yêu cầu bạn chạy server bên ngoài.

**Kết quả dự kiến:** cả **sáu phương thức test** thành công với cấu hình nguyên bản. Log chạy có thể khác giữa các máy; không gán sẵn thời gian hoặc số dòng log cụ thể.

### Thí nghiệm A — Thêm endpoint mới nhưng quên chính sách

Thêm một phương thức sau vào lớp `ApiController` (cùng ứng dụng):

~~~java
@GetMapping("/api/internal/debug")
String debug() {
    return "debug";
}
~~~

**Dự đoán trước khi chạy:**

1. Spring MVC đã đăng ký `GET /api/internal/debug`, nhưng `ReviewedEndpointPolicies.ALL` vẫn chỉ có bốn route.
2. `everyApplicationRouteHasExplicitReviewedPolicy` **FAIL** vì tập route thực tế có thêm khóa `(GET, /api/internal/debug)`.
3. Request từ `eva` vào endpoint debug bị `403` do `anyRequest().denyAll()`, nên endpoint vừa tạo chưa bị mở công khai.

Đây là trạng thái mong muốn của quá trình bảo vệ: thêm endpoint cần kích hoạt xem xét chính sách. Nếu endpoint phải tiếp tục khóa nội bộ, có thể đưa một loại rule `DENY` vào danh mục và xử lý `match.denyAll()`, kèm test từ chối; nếu được mở, cần định nghĩa authority riêng và test đủ người có/không có quyền. **Không thêm `permitAll` để làm test xanh nếu endpoint chưa được cho phép.**

### Thí nghiệm B — Quên chính sách của endpoint xuất báo cáo

Xóa tạm phần tử `GET /api/reports/export` khỏi danh sách `REVIEWED`, giữ nguyên controller và test.

Kỳ vọng: test kiểm kê fail vì route đang tồn tại nhưng chưa được phân loại. Đồng thời `newlyAddedExportHasItsOwnPermission` fail: `eva` trước đây được phép xuất báo cáo, nay request rơi xuống `denyAll()` và trả `403` thay cho `200`. Như vậy **một lần quên khai báo quyền bị phát hiện ở hai góc nhìn khác nhau**.

Khôi phục entry, chạy lại test, xác minh các ca đều xanh. Thực hành này cho thấy chính sách có thể giữ hệ thống an toàn khi bị bỏ quên, trong khi kiểm thử vẫn buộc đội phát triển giải quyết lỗi thiếu phân loại.

### Thí nghiệm C — Thêm rule quá rộng

Chỉ trong nhánh thí nghiệm, thay `anyRequest().denyAll()` thành `anyRequest().authenticated()`. Lúc này người có tài khoản có thể gọi URL chưa phân loại. Test `unlistedPathsAndMethodsAreDenied` phải fail: ví dụ `GET /api/unknown` không còn bị Security chặn (thường trả `404` do không có controller) thay vì `403`; một endpoint controller mới chưa có policy có thể bị mở cho mọi người đã đăng nhập.

Khôi phục `denyAll()` và chạy lại test. Kiểm thử này chứng minh fallback **có hiệu lực thật**, chứ không chỉ có mặt trong file cấu hình.

### Thí nghiệm D — Cấp nhầm quyền xuất báo cáo

Thêm `"report:export"` vào authorities của `bob` nhưng giữ nguyên ma trận kỳ vọng. Test `newlyAddedExportHasItsOwnPermission` sẽ fail vì `bob` nhận `200` thay vì `403`. Nếu đây là thay đổi nghiệp vụ hợp lệ, cần chủ động cập nhật ma trận quyền và kiểm thử; nếu không, trả lại quyền tối thiểu.

### Thứ tự xử lý khi bài test đỏ

1. Đọc thông báo khác biệt của tập `registered` và `ReviewedEndpointPolicies.keys()`; xác định đúng route mới, phương thức HTTP và path pattern.
2. Kiểm tra người viết endpoint đã xác định chủ sở hữu và loại dữ liệu được truy cập hay chưa, quyền tối thiểu cần có, có phân biệt tenant/bản ghi hay không.
3. Thêm hoặc sửa policy theo quyết định đó; giữ fallback `denyAll()`. Nếu route không nên được mở, vẫn ghi nhận `DENY` có chủ đích trong danh mục.
4. Viết ca MockMvc cho người chưa đăng nhập, người thiếu quyền, người có quyền, sai method và (nếu request gây thay đổi trạng thái) CSRF.
5. Chạy lại toàn bộ suite; chỉ kết luận hoàn tất khi **route coverage và hành vi phân quyền** đều qua.

## 7. Giới hạn của kiểm kê và cách mở rộng đúng

Cách triển khai ở trên cố ý kiểm kê **controller của package `com.example.routeaudit`**. Khi áp dụng cho dự án thật, phải xác định đủ bề mặt HTTP:

- **Controller ở package khác:** mở rộng bộ lọc để bao phủ toàn bộ package ứng dụng, không chỉ một package demo. Đừng vô tình bỏ qua controller do module khác thêm.
- **WebFlux hoặc functional routing:** các route khai báo bằng `RouterFunction` không nhất thiết xuất hiện trong `RequestMappingHandlerMapping` của MVC. Hãy kiểm kê API đúng runtime và test qua `WebTestClient`.
- **Actuator, framework, GraphQL, WebSocket, management port hoặc route do starter cung cấp:** có thể được quản lý bằng hệ thống mapping khác. Cần đánh giá riêng, tránh khẳng định test MVC đã bao phủ toàn bộ hệ thống.
- **Nhiều `SecurityFilterChain`:** một chain có `securityMatcher` quá hẹp có thể để route nằm ngoài phạm vi. Kiểm thử phải chứng minh chain phù hợp xử lý từng route và luôn có bảo vệ dự phòng cho phần còn lại.
- **HTTP `HEAD`/`OPTIONS`, CORS và tiền xử lý proxy:** Spring MVC có thể hỗ trợ các method ngầm ngoài khai báo `@GetMapping`. Danh mục bài tập chỉ liệt kê method khai báo tường minh; khi cần hỗ trợ HEAD, preflight CORS hoặc reverse proxy, kiểm thử riêng những đường truy cập đó.
- **Phân quyền theo tài nguyên:** `hasAuthority("document:read")` không quyết định `alice` có được đọc tài liệu thuộc `bob` hay tenant khác. Cần kiểm tra ở lớp nghiệp vụ và test dữ liệu xuyên người sở hữu/tenant.
- **Chính sách động:** danh mục tĩnh đơn giản giúp minh họa. Khi nhiều nhóm và tài nguyên hơn, có thể trích xuất manifest/bộ phân loại endpoint hoặc `AuthorizationManager` tương ứng; hãy giữ tính chất **route thực tế và chính sách được rà soát là hai nguồn có thể đối chiếu độc lập**.

Không coi test này là bằng chứng thay thế cho đánh giá rủi ro và kiểm thử quyền trên dữ liệu thật. Nó giải quyết rất cụ thể lỗi **thêm endpoint MVC mà không khai báo hoặc kiểm chứng chính sách truy cập**.

## 8. Những lỗi phổ biến

- **Chỉ viết test cho endpoint cũ:** test suite có thể xanh khi endpoint mới không hề được đề cập. Hãy dùng kiểm kê mapping động.
- **Chỉ thử `/api/unknown`:** `403` ở URL không tồn tại chứng minh fallback nhưng không chứng minh route mới đã được duyệt quyền.
- **Tự sinh danh mục policy từ tất cả controller:** hai vế so sánh lúc nào cũng trùng, nên thêm endpoint không làm test fail. Danh mục phải được cập nhật sau khi con người xác định chính sách.
- **Dùng `anyRequest().authenticated()`:** bất kỳ người đăng nhập nào cũng có thể vào URL mới chưa phân loại. Khi chưa có quyết định cho phép, giữ `denyAll()`.
- **Chỉ so path, bỏ qua HTTP method:** GET đã duyệt không có nghĩa POST/DELETE cùng đường dẫn cũng được duyệt.
- **Nhầm `401`, `403`, `404`:** thiếu xác thực, bị cấm và không có handler là ba nguyên nhân khác nhau. Phối hợp kiểm kê mapping, status và body để tìm nguyên nhân.
- **POST thiếu CSRF làm test “đúng” giả:** phải thêm `csrf()` khi mục tiêu test là quyền ghi; tách thêm ca âm tính chuyên kiểm tra CSRF.
- **Kiểm kê một phần ứng dụng mà kết luận toàn hệ thống an toàn:** nhớ bao phủ mọi controller, chain, gateway và cơ chế routing phù hợp kiến trúc.

## 9. Tiêu chí hoàn thành và tài liệu chính thức

Có thể coi bài thực hành hoàn thành khi người học:

1. Trình bày được tình huống cụ thể endpoint mới bị bỏ sót, phân biệt **không được mở nhầm** và **chưa được rà soát**.
2. Giải thích được vai trò của `ReviewedEndpointPolicies.ALL`, matcher theo method/path, và `anyRequest().denyAll()`.
3. Chạy được test kiểm kê `RequestMappingHandlerMapping`; biết vì sao thêm `@GetMapping("/api/internal/debug")` nhưng không thêm policy khiến test fail.
4. Kiểm chứng bằng MockMvc đủ anonymous, người thiếu quyền, người có quyền, sai HTTP method, quyền cũ và fallback; giải thích status/body kỳ vọng.
5. Chạy thí nghiệm đỏ–xanh (thêm route, bỏ policy, đổi fallback, cấp nhầm authority), dự đoán kết quả **trước** khi chạy và phục hồi để toàn bộ suite xanh.
6. Nêu rõ giới hạn phạm vi của kiểm kê MVC, CSRF, nhiều filter chain, functional routes và quyền sở hữu bản ghi.

Đọc thêm ở tài liệu chính thức:

- [Spring Security: Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security: Security Filter Chain](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security: MockMvc Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security: MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Framework: RequestMappingHandlerMapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)

**Nguyên tắc giữ lại:** endpoint mới phải đi qua hai phép kiểm tra độc lập — **runtime chặn khi chưa có policy**, và **CI yêu cầu mọi mapping thực tế đều được phân loại, kiểm thử quyền trước khi phát hành**.
