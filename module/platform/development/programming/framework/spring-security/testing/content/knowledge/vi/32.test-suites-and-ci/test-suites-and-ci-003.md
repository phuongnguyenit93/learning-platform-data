# Tên test mô tả danh tính, hành động và quyết định mong đợi

Một bài test bảo mật thất bại trên CI phải cho người đọc biết ngay: **ai đang gửi yêu cầu, người đó làm gì và hệ thống phải cho phép hay từ chối theo chính sách nào**. Nếu tên chỉ là `testSecurity()`, `shouldReturn403()` hoặc `accessTest2()`, nhóm phát triển phải mở source code mới biết đây là người dùng ẩn danh, một người đã đăng nhập nhưng thiếu quyền, hay request có token CSRF không hợp lệ.

Trong chương **Bộ kiểm thử và CI** của module **SPRING_SECURITY_TESTING**, mục tiêu là tổ chức các phép kiểm chứng xác thực, phân quyền và bảo vệ HTTP sao cho có thể đọc, bảo trì và phân tích kết quả ổn định. Kỹ thuật được dùng trải từ `MockMvc`, `@WithMockUser`, `SecurityContext`, `WebTestClient` đến JWT/OAuth2/OIDC giả lập. Bài học này tập trung vào một quy tắc rất thực dụng:

> **Tên test = danh tính/điều kiện bảo mật + hành động + quyết định mong đợi.**

Quy tắc không ép mọi nhóm phải dùng đúng một kiểu đặt tên, nhưng ba thông tin trên cần hiện rõ trong **tên phương thức hoặc display name**. Ví dụ:

```java
anonymous_whenReadingReports_isUnauthorized()
reader_whenReadingReports_isAllowed()
reader_whenCreatingReportWithCsrf_isForbidden()
editor_whenCreatingReportWithoutCsrf_isForbidden()
editor_whenCreatingReportWithCsrf_isCreated()
```

Năm tên này mô tả các nhánh khác nhau của **cùng một hợp đồng bảo mật** mà không cần nhìn vào thân phương thức test.

## 1. Test name là một phần của security contract

Một hệ thống có thể có hàng trăm test trả về `200`, `401`, `403` và redirect. Khi test được gom trong JUnit XML hoặc CI, tên phương thức chính là “nhãn” đầu tiên giúp nhận biết rủi ro hồi quy.

So sánh:

| Tên mơ hồ | Tên phản ánh hợp đồng | Lợi ích |
| --- | --- | --- |
| `testGet()` | `anonymous_whenReadingReports_isUnauthorized()` | Biết danh tính và hành động bị chặn |
| `testRole()` | `readerWithoutWriteRole_whenCreatingReport_isForbidden()` | Phân biệt người đã đăng nhập nhưng thiếu quyền |
| `shouldBe403()` | `editorWithoutCsrf_whenCreatingReport_isForbidden()` | Biết nguyên nhân dự kiến là CSRF, không phải role |
| `testAdmin()` | `admin_whenDeletingAnotherUsersRecord_isForbidden()` | Không ngầm hiểu admin được phép xóa mọi dữ liệu |
| `jwtTest()` | `jwtWithInvalidIssuer_whenReadingReports_isUnauthorized()` | Diễn đạt điều kiện token đang được kiểm chứng |
| `oauthTest()` | `oauth2CallbackWithWrongState_whenCompletingLogin_isRejected()` | Cho biết nhánh kiểm tra luồng OAuth2 |
| `testReactive()` | `anonymous_whenCallingReactiveAdminEndpoint_isUnauthorized()` | Có ngữ cảnh công nghệ và quyết định |

Đặc biệt, **`403` không phải một nguyên nhân**: request có thể bị từ chối vì thiếu authority, thiếu CSRF, ownership không phù hợp hoặc policy khác. Một tên như `shouldReturn403()` chỉ mô tả mã HTTP; nó chưa nói **vì sao đó là quyết định đúng**.

Ở phía ngược lại, tên `adminCanDoEverything()` là một hợp đồng nguy hiểm: role quản trị vẫn có thể bị hạn chế bởi tenant, phạm vi dữ liệu, policy nhạy cảm và điều kiện xác thực lại. Chọn tên đủ cụ thể để các giới hạn ấy được nhìn thấy.

## 2. Công thức gợi ý: identity_whenAction_expectedDecision

Ta chọn công thức Java lowerCamelCase với ba phần:

```text
<identityOrSecurityState>_when<ActionAndContext>_<expectedDecision>
          |                    |                   |
          |                    |                   +-- quyết định bảo mật
          |                    +-- HTTP operation + tài nguyên + điều kiện
          +-- danh tính, quyền, token, session hoặc trạng thái ẩn danh
```

Ví dụ:

```java
anonymous_whenReadingPrivateProfile_isUnauthorized()
authenticatedUser_whenReadingOwnProfile_isAllowed()
authenticatedUser_whenReadingAnotherUsersProfile_isForbidden()
jwtWithoutOrdersReadScope_whenListingOrders_isForbidden()
expiredJwt_whenListingOrders_isUnauthorized()
loggedInUserWithoutCsrf_whenUpdatingProfile_isForbidden()
validOidcUser_whenReadingDashboard_isAllowed()
```

Quy ước này không bắt buộc phải ghi cả URL, phương thức HTTP, role và status code vào mọi tên. **Giữ phần có ý nghĩa bảo mật** là quan trọng nhất.

### Phần 1 — Danh tính hoặc trạng thái xác thực

Các tên hữu ích gồm:

- `anonymous`, `unauthenticated`: chưa có Authentication được chấp nhận.
- `reader`, `editor`, `tenantAdmin`: role nghiệp vụ cụ thể; cần định nghĩa rõ trong security config.
- `authenticatedUserWithoutWriteScope`: đã xác thực nhưng thiếu authority cần thiết.
- `jwtWithExpiredSignature` là một tên **sai về khái niệm**: token có thời điểm hết hạn, còn chữ ký thì hợp lệ hoặc không. Nên tách `expiredJwt` và `jwtWithInvalidSignature`.
- `oauth2UserWithoutRequiredAuthority`, `oidcUserWithVerifiedEmail`: dùng khi test thật sự kiểm tra đúng điều kiện đó, không chỉ giả lập claim tùy ý.
- `otherTenantUser`: nhấn mạnh sự khác biệt về ownership/tenant dù role có thể giống nhau.

Tên identity không nhất thiết là tên riêng `alice` hay `bob`; nếu hai tên chỉ là dữ liệu ví dụ, `reader` và `editor` giúp người đọc hiểu policy hơn. Tên riêng vẫn hữu ích khi chính **sự khác nhau giữa principal** là điều đang kiểm tra.

### Phần 2 — Hành động có bối cảnh

Tốt:

```text
whenReadingReports
whenCreatingReportWithCsrf
whenDeletingAnotherTenantsInvoice
whenCompletingOauth2CallbackWithWrongState
whenCallingResourceServerWithInvalidAudience
```

Kém thông tin:

```text
whenRequest
whenCall
whenGet
whenTest
```

Nếu `GET /api/reports` và `POST /api/reports` có policy khác nhau, tên `whenReadingReports` và `whenCreatingReport` tốt hơn việc cùng đặt `whenAccessingReports`. Với method-level security, tên có thể dựa vào hành động nghiệp vụ như `whenApprovingTransfer` thay vì nói chung `whenCallingService`.

### Phần 3 — Quyết định mong đợi

Có thể chọn từ vựng:

| Hậu tố | Khi dùng | Dạng kiểm chứng thường gặp |
| --- | --- | --- |
| `isAllowed` | Request hợp lệ theo policy | `200 OK`, `204 No Content` hoặc phản hồi nghiệp vụ phù hợp |
| `isCreated` | Thao tác tạo tài nguyên được phép và thành công | `201 Created` |
| `isUnauthorized` | Server yêu cầu authentication hoặc từ chối credential | `401 Unauthorized` |
| `isForbidden` | Request bị policy/CSRF chặn | `403 Forbidden` |
| `redirectsToLogin` | Ứng dụng web chuyển sang trang login | `302/303` và Location hợp lệ |
| `isNotFoundToHideExistence` | Policy cố ý trả 404 để tránh lộ sự tồn tại tài nguyên | `404 Not Found` |
| `isRejectedAsInvalidRequest` | Cú pháp/tham số xác thực không hợp lệ theo hợp đồng | Thường `400 Bad Request` |
| `keepsSessionUnauthenticated` | Callback SSO thất bại không được tạo đăng nhập | Kiểm tra request tiếp theo vẫn không được vào route bảo vệ |

**Chọn quyết định từ security policy đang được kiểm thử**, không suy diễn máy móc từ danh tính. Một ứng dụng browser dùng form login có thể redirect khi anonymous thay vì trả 401; Resource Server với HTTP Bearer thường trả 401 cho request thiếu authentication; API có thể chủ động trả 404 khi không muốn tiết lộ tài nguyên.

## 3. Ma trận đặt tên theo nguyên nhân bị chặn

Một bộ kiểm thử tốt không chỉ có test “happy path” mà phân biệt những kiểu từ chối sau:

| Chủ thể / điều kiện | Hành động | Kỳ vọng khi cấu hình tương ứng |
| --- | --- | --- |
| Anonymous | GET tài nguyên cần login | 401 hoặc redirect tới login |
| Đã đăng nhập, đủ role | GET tài nguyên được phép | 200 |
| Đã đăng nhập, thiếu role | GET tài nguyên cần role khác | 403 |
| Đã đăng nhập, đúng role nhưng không phải owner | GET tài nguyên người khác | 403 hoặc 404 theo policy |
| Đủ role, thiếu CSRF | POST form có CSRF protection | 403 |
| Đủ role, có CSRF hợp lệ | POST form hợp lệ | 200/201/204 theo API |
| JWT giả lập có scope đúng | GET Resource Server route | Cho phép theo scope, **chưa đo chữ ký JWT** |
| JWT đã ký nhưng sai issuer | GET Resource Server route | 401 khi decoder thật từ chối |
| Token hợp lệ nhưng thiếu scope | GET Resource Server route | 403 |
| OAuth2 callback sai `state` | Hoàn tất login | Không đăng nhập thành công |
| OIDC ID token sai issuer/audience/nonce | Hoàn tất OIDC login | Không được tạo session tin cậy |
| User từ tenant A | Sửa tài nguyên tenant B | Bị từ chối theo ownership policy |

Tên test cần giúp phân biệt **phép thử dùng principal giả** với phép thử đi qua **cơ chế xác thực thật**. Nếu dùng `jwt()` để gắn authentication giả, không đặt tên `invalidSignatureIsRejected()` vì decoder **không có cơ hội xác minh chữ ký**. Điều kiện trong tên phải thật sự được fixture và assertion kiểm tra.

## 4. Ví dụ Servlet: một SecurityFilterChain để đặt tên nhất quán

Ta xây dựng ứng dụng tối thiểu dùng Spring Boot 3.x, Spring Security 6.x và Spring MVC. Endpoint đọc báo cáo cần `ROLE_READER`; endpoint tạo báo cáo cần `ROLE_EDITOR` và token CSRF hợp lệ. HTTP Basic được bật để request thiếu chứng thực nhận `401` trong ví dụ. Các test với `user(...)` tập trung vào policy; không phải test password thực.

Dependency Gradle:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Cấu hình bảo mật:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ReportsSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasRole("READER")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasRole("EDITOR")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            // CSRF vẫn bật theo cấu hình mặc định.
            .build();
    }
}
```

Controller minh họa:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reports")
class ReportsController {

    @GetMapping
    String list() {
        return "reports-visible";
    }

    @PostMapping
    ResponseEntity<String> create() {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body("report-created");
    }
}
```

Ví dụ không truy cập database; mục đích là đo quyết định security qua HTTP. Nếu hệ thống thật ghi dữ liệu, cần bổ sung assertion rằng request bị từ chối **không tạo bản ghi** và kiểm soát transaction/test isolation theo chính sách dữ liệu của dự án.

## 5. MockMvc: tên test đọc được hợp đồng chỉ qua báo cáo CI

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportsSecurityContractTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymous_whenReadingReports_isUnauthorized()
            throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void reader_whenReadingReports_isAllowed()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("alice").roles("READER")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports-visible"));
    }

    @Test
    void editorWithoutReadRole_whenReadingReports_isForbidden()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("bob").roles("EDITOR")))
            .andExpect(status().isForbidden());
    }

    @Test
    void reader_whenCreatingReportWithCsrf_isForbidden()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(user("alice").roles("READER"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void editor_whenCreatingReportWithoutCsrf_isForbidden()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(user("bob").roles("EDITOR")))
            .andExpect(status().isForbidden());
    }

    @Test
    void editor_whenCreatingReportWithCsrf_isCreated()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(user("bob").roles("EDITOR"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("report-created"));
    }
}
```

Điều quan trọng không chỉ là tên dễ đọc mà còn là cách **cố định các điều kiện khác** để test đo đúng nguyên nhân:

- `reader_whenCreatingReportWithCsrf_isForbidden`: cung cấp **CSRF hợp lệ**, nên request bị từ chối vì thiếu role `EDITOR`, không bị chặn sớm do CSRF.
- `editor_whenCreatingReportWithoutCsrf_isForbidden`: cung cấp **role đúng**, nên 403 là bằng chứng về chính sách CSRF trong cấu hình này.
- `editor_whenCreatingReportWithCsrf_isCreated`: có role và CSRF phù hợp, giúp xác nhận endpoint thực sự cho phép trường hợp hợp lệ.
- `anonymous_whenReadingReports_isUnauthorized`: chọn GET để không có CSRF làm sai lệch kết luận về authentication.
- `editorWithoutReadRole_whenReadingReports_isForbidden`: chứng minh một người có role khác không mặc nhiên có quyền đọc.

Sáu test tạo thành một ma trận nhỏ nhưng nhiều thông tin: cùng URL, hai HTTP method, ba trạng thái danh tính và hai điều kiện CSRF.

### Tên test chính xác không đồng nghĩa test đã kiểm toàn bộ lớp bảo mật

`user("alice").roles("READER")` là request postprocessor của `spring-security-test`: nó cung cấp principal/authorities cho MockMvc, **không kiểm tra HTTP Basic password**. Một bài test riêng dùng `.with(httpBasic("alice", "wrong-password"))` chỉ phù hợp khi application context có `UserDetailsService` và password encoder thật để xác thực.

Không gọi những phương thức sử dụng `user()` là “real login authentication test”. Có thể đặt tên:

```text
readerWithMockAuthentication_whenReadingReports_isAllowed
wrongBasicPassword_whenReadingReports_isUnauthorized
```

nếu nhóm cần phân biệt **fixture giả lập** và **credential được xử lý thật** ngay trong tên; không nhất thiết thêm chữ `mock` vào mọi test authorization nếu scope của class và tài liệu đã làm rõ điều đó.

## 6. Phân biệt authentication, authorization, CSRF và nghiệp vụ

Một mã HTTP có thể được tạo ở nhiều tầng. Nếu tên test chỉ nói status code, sau khi refactor security chain ta có thể nhận cùng mã nhưng vì **nguyên nhân khác**.

```text
HTTP request
    |
    +-- CSRF filter: POST thiếu token -> có thể 403
    |
    +-- Authentication filter: credential sai -> có thể 401
    |
    +-- Authorization: có Authentication nhưng thiếu role -> 403
    |
    +-- Controller / service: rule nghiệp vụ -> 400, 403, 404...
```

Khi test nguyên nhân cụ thể:

1. **Cố định prerequisites.** Ví dụ test “thiếu role” cần gửi CSRF hợp lệ nếu request dùng POST, và có Authentication hợp lệ.
2. **Assert hành vi quan sát được.** Status, redirect, header `WWW-Authenticate`, body hoặc dữ liệu không thay đổi theo contract.
3. **Không suy nguyên nhân chỉ từ status.** Khi cần, kiểm tra event, mock interaction hoặc handler bằng cách cô lập thành phần đúng mức; đừng viết test yếu mà có tên tuyên bố quá mạnh.
4. **Tạo cặp đối chứng.** Có role và thiếu role; có CSRF và thiếu CSRF; token hợp lệ và token sai.
5. **Giữ mã phản hồi đúng policy.** Không ép form login trả 401 nếu ứng dụng được thiết kế redirect; không ép API cần giấu existence phải trả 403 khi policy chọn 404.

Ví dụ tên quá mạnh:

```java
// Sai mục đích: không thể chứng minh JWT signature từ .with(jwt()).
void invalidJwtSignature_whenReadingReports_isUnauthorized() {
    // mvc.perform(... .with(jwt())) ...
}
```

Trong trường hợp đó, hãy đổi **fixture và loại test** để dùng JWT ký thật qua `Authorization: Bearer ...`, cho `JwtDecoder`/validator chạy; hoặc đổi tên theo điều đang đo, ví dụ `jwtWithoutReadScope_whenReadingReports_isForbidden()`.

## 7. Dùng @DisplayName để phù hợp tiếng Việt và báo cáo JUnit

Tên phương thức Java có thể giữ ổn định theo quy ước của codebase, còn `@DisplayName` giúp người đọc báo cáo CI nhìn thấy câu mô tả tự nhiên:

```java
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

@DisplayName("Bảo mật báo cáo: danh tính, hành động, quyết định")
class ReportsSecurityDisplayNameTests {

    @Test
    @DisplayName("Ẩn danh đọc danh sách báo cáo → 401 Unauthorized")
    void anonymous_whenReadingReports_isUnauthorized() {
        // Gọi MockMvc như phần trước.
    }

    @Test
    @DisplayName("Editor tạo báo cáo nhưng thiếu CSRF → 403 Forbidden")
    void editor_whenCreatingReportWithoutCsrf_isForbidden() {
        // Gọi MockMvc như phần trước.
    }
}
```

Đoạn mã minh họa cách đặt tên; **đừng sao chép các method body rỗng thành phép kiểm thử thực tế**. Trong project, các method có `@Test` phải chứa assertion hoặc gọi một helper assertion thực sự.

Ưu điểm và giới hạn:

- Tên method nhất quán hỗ trợ IDE search, Git blame, `--tests` filter và thảo luận trong code review.
- `@DisplayName` giúp người đọc kết quả JUnit dễ hiểu; một số công cụ CI dùng `display-name`, một số dùng `className + methodName`. Nên giữ **cả hai** có ý nghĩa, không phụ thuộc hoàn toàn vào một báo cáo.
- Không đưa access token, SAML assertion, email cá nhân hoặc dữ liệu nhạy cảm vào `@DisplayName` hay tên `@ParameterizedTest`: chúng có thể được ghi vào artifact CI lưu trữ lâu dài.

Nên quy ước thống nhất một ngôn ngữ cho tên method (`lowerCamelCase` tiếng Anh trong bài này) và display name bằng tiếng Việt nếu nhóm cần. Điều quan trọng là đọc tên không phải đoán điều kiện bảo mật.

## 8. Parameterized test: tên mỗi trường hợp phải giữ identity rõ ràng

Parameterized tests rất phù hợp khi nhiều danh tính thực hiện cùng hành động. Nhưng tên `testAccessParameterized[1]`, `testAccessParameterized[2]` không hữu ích trong CI nếu không có label cho từng row.

Ví dụ với cùng security config ở mục 4:

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ParameterizedTest(name =
    "Danh tính role={0} đọc báo cáo: quyết định HTTP {1}")
@CsvSource({
    "READER, 200",
    "EDITOR, 403"
})
void authenticatedRole_whenReadingReports_matchesExpectedDecision(
        String role, int expectedStatus) throws Exception {

    mvc.perform(get("/api/reports")
            .with(user("test-user").roles(role)))
        .andExpect(status().is(expectedStatus));
}
```

Đặt phương thức này **trong class `ReportsSecurityContractTests`** đã có `mvc`. Tên hiển thị JUnit của mỗi row sẽ chứa role, hành động và status mong đợi. Không dùng cùng phương thức với nhiều vai trò mà đặt tên `reader_whenReadingReports_isAllowed()`: điều đó không đúng với row `EDITOR`.

Những thực hành nên áp dụng:

- Đặt `@ParameterizedTest(name = "...")` có danh tính và quyết định; tránh chỉ dùng `{index}`.
- Với nhiều điều kiện như `principal`, `scope`, `tenant`, `csrf`, dùng `@MethodSource` trả về **case label có ý nghĩa** thay vì nhồi nhiều chuỗi khó đọc vào một `CsvSource`.
- Đảm bảo mỗi case có fixture độc lập; không tái sử dụng `SecurityContext`, session hoặc database state không được reset.
- Không tạo dữ liệu ngẫu nhiên không có seed/trace rõ ràng trong tên test; CI phải tái hiện được trường hợp thất bại.

## 9. JWT, opaque token và OAuth2/OIDC: tên phải nói mức độ xác minh

Trong module **SPRING_SECURITY_TESTING**, có nhiều helper giả lập Authentication. Tên test phải phản ánh đúng **lớp được đo**:

| Cơ chế | Helper phổ biến | Tên test đúng mục tiêu | Không nên tuyên bố |
| --- | --- | --- | --- |
| Servlet mock principal | `user()`, `@WithMockUser` | `reader_whenReadingReports_isAllowed` | Đã xác minh password thực |
| Servlet JWT authorization | `jwt()` | `jwtWithoutReadScope_whenReadingReports_isForbidden` | Chữ ký JWT đã được kiểm |
| Servlet opaque-token authorization | `opaqueToken()` | `opaquePrincipalWithoutPermission_whenReadingReports_isForbidden` | Introspection đã chạy |
| OAuth2 Client | `oauth2Client("catalog")` | `catalogAuthorizedClientWithReadScope_whenCallingCatalog_isAllowed` | Authorization Code đã trao đổi |
| OAuth2 Login | `oauth2Login()` | `oauth2PrincipalWithoutAdminRole_whenReadingAdminPage_isForbidden` | Callback/state/token endpoint đã chạy |
| OIDC Login | `oidcLogin()` | `oidcPrincipalWithProfileClaim_whenReadingProfile_isAllowed` | ID token/JWKS/nonce đã được xác minh |
| Reactive | `mockUser()`, `mockJwt()`, `mockOAuth2Login()` | `jwtPrincipalWithoutScope_whenCallingReactiveApi_isForbidden` | Request đã gửi JWT ký thật qua HTTP |

Ví dụ **mã kiểm thử scope** riêng cho ứng dụng Resource Server Servlet có rule `hasAuthority("SCOPE_reports:read")`:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void jwtWithoutReportsReadScope_whenReadingReports_isForbidden()
        throws Exception {

    mvc.perform(get("/api/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_other:read"))))
        .andExpect(status().isForbidden());
}
```

**Đây là ví dụ cho cấu hình Resource Server khác cấu hình HTTP Basic ở mục 4**. Khi áp dụng, phải cấu hình `oauth2ResourceServer().jwt()` và rule scope tương ứng. `jwt()` gắn Authentication giả; test trên **không** đi qua chữ ký JWT, `issuer`, `audience` hoặc clock validation.

Đối với test thật, tên cần khớp với fixture:

```text
jwtWithWrongSignature_whenReadingReports_isUnauthorized
jwtWithWrongIssuer_whenReadingReports_isUnauthorized
expiredJwt_whenReadingReports_isUnauthorized
validJwtWithoutReadScope_whenReadingReports_isForbidden
oidcCallbackWithInvalidNonce_whenCompletingLogin_isRejected
oauth2CallbackWithWrongState_whenCompletingLogin_isRejected
opaqueTokenWithInactiveIntrospection_whenReadingReports_isUnauthorized
```

Những test này chỉ có ý nghĩa nếu **gửi credential/protocol response thật** vào filter và để decoder, introspector hoặc login handler thực sự kiểm tra. Không đặt tên `wrongIssuer` nếu token cũng sai chữ ký: test có thể bị từ chối vì lý do khác.

## 10. WebTestClient Reactive: giữ nguyên ba thành phần của tên

Với WebFlux, dùng `SecurityWebFilterChain` và `WebTestClient` đã gắn vào ApplicationContext. `mockUser()` giúp kiểm chứng authorization khi request đã có principal giả:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ReactiveReportsSecurityContractTests {

    @Autowired ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void reactiveReader_whenReadingReports_isAllowed() {
        client.mutateWith(mockUser("alice").roles("READER"))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void reactiveUserWithoutReadRole_whenReadingReports_isForbidden() {
        client.mutateWith(mockUser("bob").roles("EDITOR"))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**Điều kiện tiên quyết:** đây là ví dụ dành riêng cho một ứng dụng WebFlux có `SecurityWebFilterChain` với route `GET /api/reports` yêu cầu `hasRole("READER")`, controller trả thành công và test dùng `spring-security-test`. Nó **không chạy nguyên xi trong project Servlet** của mục 4 nếu không thay ứng dụng sang WebFlux.

Trong remote integration test `WebTestClient.bindToServer()`, mock mutator không truyền một đối tượng Authentication Java sang server HTTP ngoài tiến trình. Phải gửi Basic/Bearer/cookie thật. Vì thế tên `validJwt_whenCallingRemoteReportsApi_isAllowed()` phải gắn với JWT đã ký và decoder/validator thật; không thể chứng minh chỉ nhờ `mockJwt()`.

## 11. Tên class và cấu trúc suite hỗ trợ tìm lỗi

Tên method có ba thành phần, còn **tên class** giúp định vị phạm vi:

```text
ReportsAuthorizationMockMvcTests
ReportsAuthenticationHttpIntegrationTests
ReportsCsrfMockMvcTests
JwtSignatureValidationIntegrationTests
Oauth2LoginCallbackIntegrationTests
OidcTokenValidationIntegrationTests
ReactiveReportsAuthorizationWebTestClientTests
```

Không cần thêm mọi chi tiết vào cả class và method. Một class tên `ReportsCsrfMockMvcTests` có thể có phương thức `editor_whenCreatingWithoutCsrf_isForbidden`, vì danh tính và hành động vẫn rõ.

Nên tách test dựa trên **hợp đồng và mức độ tích hợp**, không chỉ dựa trên file nào thuận tiện:

1. **Authorization tests**: MockMvc/WebTestClient với `user()`, `mockUser()`, `jwt()`, `oauth2Login()`; chạy nhanh, cô lập.
2. **Authentication mechanism tests**: decoder JWT, opaque introspection, HTTP Basic/form login, OAuth2/OIDC callback, SAML2 validation; cần fixture thật và assertions phù hợp.
3. **HTTP integration tests**: port thật, cookie/session/CSRF, persistence và các boundary của network/transaction.
4. **End-to-end tests**: browser, IdP test, reverse proxy, CORS/cookie/SameSite và đường đi deploy gần thực tế.

Một test thất bại tên `jwtWithWrongIssuer_whenReadingReports_isUnauthorized` trong class `JwtSignatureValidationIntegrationTests` định vị vấn đề rõ hơn nhiều so với một tên `test4` dưới class `SecurityTests`.

## 12. CI: thông tin cần có khi test thất bại

Trong CI, kết quả thường được đọc dưới dạng **JUnit XML**, summary và report HTML. Bộ test nên cung cấp đủ ngữ cảnh để người không vừa viết code cũng triage được.

| Thông tin | Nguồn | Ví dụ |
| --- | --- | --- |
| Class test | Package/class JUnit | `ReportsSecurityContractTests` |
| Method/display name | `@Test`, `@DisplayName` | `editor_whenCreatingReportWithoutCsrf_isForbidden` |
| Điều kiện hiện tại | Fixture và assertions | Editor đã xác thực, thiếu CSRF |
| Mong đợi | Matcher | HTTP 403 |
| Thực tế | Assertion failure | HTTP 201 |
| Tác động bảo mật | Phân tích sau khi đọc test | Request thay đổi trạng thái vượt CSRF |
| Cách tái hiện | Lệnh Gradle/JUnit filter và fixture | Chạy đúng class/method test |

Ví dụ lệnh cục bộ *minh họa*, không phải bước thực thi trong bài viết:

```bash
# Chạy toàn bộ unit và integration tests gắn với task test.
./gradlew test

# Chạy một lớp có hợp đồng bảo mật rõ ràng.
./gradlew test --tests '*ReportsSecurityContractTests'

# Chạy một case cụ thể khi cần phân tích.
./gradlew test --tests \
  '*ReportsSecurityContractTests.editor_whenCreatingReportWithoutCsrf_isForbidden'
```

Tên method ổn định giúp chạy lại một case bằng `--tests` dễ hơn. `@DisplayName` hỗ trợ người xem report, nhưng việc filter test theo display name có thể khác giữa công cụ; hãy dùng method/class name khi chạy Gradle để tránh phụ thuộc giao diện báo cáo.

### Ví dụ cấu hình Gradle test report

```gradle
tasks.named("test", Test) {
    useJUnitPlatform()

    reports {
        junitXml.required = true
        html.required = true
    }

    testLogging {
        events("FAILED", "SKIPPED")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
```

Tùy cấu hình Gradle, report XML thường ở `build/test-results/test/`, report HTML ở `build/reports/tests/test/`. Không để report in access token, password, session cookie hoặc raw authorization code: tên test và exception message cũng có thể là **artifact lưu trữ** trên CI.

### Ví dụ quy trình CI

Đây là workflow mẫu cho GitHub Actions chạy build/test và giữ report ngay cả khi test thất bại. Phần `gradle/actions/setup-gradle` hỗ trợ cache Gradle; version của Java cần khớp dự án thực.

```yaml
name: Security test suite

on:
  pull_request:
  push:
    branches: [main]

jobs:
  security-tests:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v4
      - name: Run tests
        run: ./gradlew test
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-security-results
          path: |
            build/test-results/test/
            build/reports/tests/test/
          if-no-files-found: warn
```

Workflow trên là **mẫu giảng dạy**, không phải file cần tạo trong STEP 4 NEW này. Trong dự án thực, chú ý wrapper executable, dependency proxy/registry, version workflow actions, tách các task test nếu có nhiều source set, và quyền truy cập artifact. Không thêm test secrets vào output report; nếu bài integration test bắt buộc dùng IdP, tạo test credentials riêng qua secrets/fixtures bảo mật.

## 13. Tránh tên “xanh giả” và test dễ vỡ trên CI

Tên mô tả chính xác là cần thiết nhưng **chưa đủ** nếu test không kiểm soát điều kiện.

### Tránh nhầm nguyên nhân 403

Test `reader_whenCreatingReport_isForbidden` có thể trả 403 ngay vì thiếu CSRF, **chứ không phải** thiếu role. Nếu muốn đo rule `ROLE_EDITOR`, dùng `.with(csrf())` và đặt tên `reader_whenCreatingReportWithCsrf_isForbidden`.

### Tránh dùng mock identity khi muốn test authentication thật

`@WithMockUser` làm cho nhiều test trông như đã “login thành công”, nhưng không kiểm chứng mật khẩu, JWT signature hoặc OAuth2/OIDC. Đặt class theo phạm vi và viết thêm integration test với credentials/protocol thật khi cần.

### Tránh chia sẻ SecurityContext giữa các test

`SecurityContextHolder` thường dựa trên ThreadLocal trong Servlet. Đừng gọi `SecurityContextHolder.setContext(...)` thủ công rồi bỏ quên `clearContext()`; JUnit test sau có thể “được phép” vì danh tính từ test trước. Spring Security Test cung cấp listener phù hợp cho `@WithMockUser`, nhưng những thread/task tự tạo vẫn cần cleanup. Một suite có tên tốt mà bị nhiễm danh tính giữa test vẫn không đáng tin.

### Tránh chia sẻ session/cookie/token giữa các scenario

Test anonymous phải thật sự **không có session đã đăng nhập**. Nếu dùng một `MockHttpSession` hoặc client mutable dùng chung sau ca đăng nhập, test `anonymous_whenReadingReports_isUnauthorized` có thể không còn anonymous. Với WebTestClient/MockMvc, tạo request độc lập và kiểm tra fixture mỗi case.

### Tránh để dữ liệu của test trước quyết định outcome

Authorization có thể dựa vào owner và tenant trong database. Với HTTP integration test, transaction của JUnit không nhất thiết rollback transaction ở server thread. Cleanup dữ liệu đã commit cần chạy đúng nơi; không mặc định `@Transactional` trên test sẽ xóa mọi row được HTTP request tạo ra.

### Tránh tên dựa trên implementation thay vì hợp đồng

Tên `filter3_callsMethodX()` dễ lỗi thời khi refactor code. Một tên `anonymous_whenReadingReports_isUnauthorized()` mô tả policy còn giá trị dù controller hoặc filter được tổ chức lại. Đặt tên theo behavior trừ khi chính unit test đang đo tương tác của một collaborator cụ thể.

### Tránh nuốt lỗi và retry vô điều kiện

Security test thất bại vì thực sự cho phép request đáng lẽ bị chặn là lỗi cần xử lý, không phải lý do để thêm `Thread.sleep()` hoặc retry liên tục. Với các ca có network/clock/IdP, dùng timeout và test fixtures xác định được; khi cần retry ở tầng hạ tầng, phân biệt rõ lỗi môi trường với lỗi policy và vẫn giữ kết quả thất bại có thể điều tra.

## 14. Checklist review tên test trước khi merge

Với từng test mới hoặc được sửa, hãy tự hỏi:

- [ ] Tên nói rõ **danh tính hoặc trạng thái bảo mật**: anonymous, role nào, token/authority nào, tenant nào?
- [ ] Tên nói rõ **hành động**: đọc, tạo, sửa, xóa, callback, gọi API nào?
- [ ] Tên nói rõ **quyết định**: allowed, forbidden, unauthorized, redirect, rejected?
- [ ] Nếu trả 403, test đã cố định CSRF/role/ownership để **không đo nhầm nguyên nhân** chưa?
- [ ] Nếu tên nói JWT invalid signature/issuer, fixture có gửi **JWT thực qua decoder** không?
- [ ] Nếu tên nói OAuth2/OIDC login, test có thật sự đi qua state/callback/token/nonce hay chỉ gắn principal giả?
- [ ] Nếu test parameterized, tên từng row có chứa identity và expected decision thay vì chỉ index không?
- [ ] Nếu test chạy qua HTTP thật, request có credential/session/cookie phù hợp và dữ liệu được cleanup độc lập không?
- [ ] Tên và display name không lộ token, mật khẩu, email, PII hoặc thông tin nhạy cảm trong CI artifact chứ?
- [ ] Khi test thất bại, kỹ sư khác có thể hiểu lý do dự kiến **chỉ từ tên, assert và failure output** không?

Đừng đổi tên chỉ để đẹp hình thức. Nếu đổi tên khiến ta nhận ra mình **chưa thiết lập đúng điều kiện của ca test**, hãy sửa cả fixture/assertion để khớp contract.

## 15. Bài tập thực hành

1. Đổi tên `testCreate()`, `testRead()`, `forbiddenTest()` trong một suite thành tên theo `identity_whenAction_expectedDecision`; ghi rõ thông tin trước đó bị thiếu.
2. Viết ba test cho `GET /api/reports`: anonymous bị 401, reader được 200, editor thiếu role đọc bị 403. Không thay đổi security config giữa các ca.
3. Viết hai test `POST /api/reports` đều trả 403 nhưng vì nguyên nhân khác nhau: reader **có CSRF** vẫn thiếu role; editor **không có CSRF** bị chặn. Đặt tên để report phân biệt rõ.
4. Bổ sung ca editor **có CSRF** tạo thành công với 201. Giải thích vì sao đây là đối chứng cần thiết cho hai ca âm.
5. Chuyển cặp reader/editor sang `@ParameterizedTest` có `name = "..."`, bảo đảm từng invocation trong report chứa role và expected HTTP decision.
6. Với Resource Server, tạo hai nhóm test: `jwtWithoutReadScope_whenReadingReports_isForbidden` dùng `jwt()`; `jwtWithInvalidSignature_whenReadingReports_isUnauthorized` gửi bearer token ký sai qua decoder thật. Viết rõ bằng chứng của mỗi nhóm.
7. Viết `oauth2CallbackWithWrongState_whenCompletingLogin_isRejected` bằng HTTP flow thật và đối chiếu với `oauth2PrincipalWithoutAdminRole_whenReadingAdminPage_isForbidden` dùng `oauth2Login()`.
8. Trên WebFlux, dùng `WebTestClient.bindToApplicationContext(...)` và `mockUser()` để kiểm tra rule role. Đổi sang `bindToServer()`, gửi credential thật và giải thích vì sao tên test phải phản ánh phạm vi đó.
9. Xem một report JUnit XML hoặc HTML trong CI. Chỉ dựa vào tên failed test, xác định identity, action, expected decision; những trường hợp chưa rõ hãy sửa tên/fixture.
10. Tạo một bảng review các ca 401, 403, 404, redirect login và CSRF; xác định response nào là contract của hệ thống, tránh ép mọi app trả cùng một status.

## 16. Ghi nhớ

- **Tên test là phần đọc được của security contract:** danh tính nào, hành động gì, quyết định nào.
- **Quy ước `identity_whenAction_expectedDecision` giúp báo cáo CI tự giải thích**, nhưng cần thống nhất từ vựng và viết tên đủ ngữ cảnh.
- **401, 403, redirect và 404 không thay thế được nguyên nhân.** Tên phải diễn đạt điều kiện bảo mật, còn fixture phải cô lập đúng nhánh được đo.
- **Dùng tên phù hợp với mức độ test:** `user()`, `jwt()`, `oauth2Login()` mô phỏng authentication; decoder, introspector và callback thật cần integration test riêng.
- **`@DisplayName` và tên parameterized invocation tăng khả năng triage**, nhưng cả method name vẫn cần ổn định để IDE/Gradle/CI tìm được test.
- **Có cả ca bị từ chối và ca được phép.** Một test chỉ nhìn thấy 403 có thể qua do thiếu CSRF, route sai hoặc lỗi config khác.
- **Giữ test độc lập và không rò credential.** SecurityContext, session, JWT/token, database và report CI cần được cách ly, cleanup và bảo vệ.
- **Tên tốt phải đi cùng assertion có giá trị.** Đừng đặt tên tuyên bố đã xác minh chữ ký, role hoặc login thật khi test chưa chạy cơ chế tương ứng.

Trong **SPRING_SECURITY_TESTING**, một kỹ sư đọc dòng test thất bại như `editor_whenCreatingReportWithoutCsrf_isForbidden` cần biết ngay **ai đang làm gì và quyết định bảo mật mong đợi là gì**. Khi tên, fixture và assertion cùng kể một câu chuyện, các bộ kiểm thử bảo mật mới thực sự có ích trong code review, hồi quy và CI.

