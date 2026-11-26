# Kiểm tra phản hồi không lộ dữ liệu tài nguyên bị bảo vệ

## 1. Mục tiêu: xác nhận dữ liệu bí mật không xuất hiện trong response

Một endpoint bị bảo vệ có thể trả đúng HTTP 401 hoặc 403 nhưng vẫn để lộ dữ liệu trong response body, header, URL chuyển hướng hoặc thông báo lỗi. Ví dụ, API từ chối người dùng không có quyền nhưng lại trả kèm tên khách hàng, số tài khoản, nội dung báo cáo hoặc thông tin nội bộ trong trường `message`. Một response lỗi cũng có thể vô tình chứa stack trace, câu SQL, đường dẫn file, claim JWT hoặc dữ liệu principal.

Trong module **SPRING_SECURITY_TESTING**, người học sử dụng `spring-security-test` để kiểm chứng xác thực, phân quyền và bảo vệ HTTP trên ứng dụng Servlet và Reactive, với `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập. Bài thuộc chương **Khẳng định kết quả** này tập trung vào một yêu cầu bảo mật quan trọng: **request không được phép phải không làm lộ dữ liệu của tài nguyên được bảo vệ**.

Một test tốt cần chứng minh cả hai mặt:

1. Request bị từ chối đúng theo chính sách: status và trạng thái xác thực phù hợp.
2. Response không chứa dữ liệu mà caller không được phép xem: body, header và redirect không tiết lộ thông tin nhạy cảm.

Đồng thời, cần có test đối chứng cho người dùng được phép truy cập. Nếu endpoint luôn trả body rỗng thì test “không lộ dữ liệu” sẽ xanh nhưng không chứng minh được cơ chế bảo vệ đang hoạt động đúng.

## 2. Những vị trí có thể vô tình làm lộ dữ liệu

Dữ liệu bảo vệ không chỉ xuất hiện trong JSON thành công. Khi kiểm thử, hãy xem xét toàn bộ response mà client nhận được:

| Vị trí | Ví dụ rủi ro | Điều cần khẳng định |
| --- | --- | --- |
| JSON response body | `data`, `accountNumber`, `internalNotes`, `ownerEmail` xuất hiện trong response 403 | Các trường dữ liệu bảo vệ không tồn tại hoặc không chứa giá trị bí mật |
| Error message | Exception message có tên bảng, SQL, đường dẫn hoặc nội dung tài nguyên | Chỉ trả mã lỗi và thông báo công khai, ổn định |
| Stack trace/debug details | Tên class, file, line number, dependency hoặc cấu hình nội bộ | Không trả stack trace và exception detail cho client |
| Response headers | Header tùy chỉnh chứa tenant, token, principal hoặc dữ liệu nội bộ | Chỉ phát hành header thuộc hợp đồng công khai |
| `Location` | URL redirect có access token, mã bí mật hoặc dữ liệu cá nhân trong query | URL chỉ chứa đích điều hướng và tham số cần thiết |
| Cache metadata | Response nhạy cảm có thể được cache và phục vụ nhầm cho user khác | Chính sách cache phù hợp, thường `Cache-Control: no-store` |
| Error cho tài nguyên không tồn tại | Thông báo tiết lộ tài nguyên có tồn tại nhưng caller không có quyền | Tuân thủ chính sách che giấu sự tồn tại nếu hệ thống yêu cầu |

Không phải mọi metadata đều là bí mật. Ví dụ, `WWW-Authenticate: Bearer` là challenge giao thức hợp lệ; status 403 cũng là thông tin client cần. Điều cần tránh là đưa dữ liệu tài nguyên hoặc thông tin nội bộ vào nơi client không được phép nhận.

## 3. Ví dụ ứng dụng: tài liệu chỉ ADMIN được xem

Giả sử một hệ thống quản lý tài liệu có tài nguyên báo cáo chứa dữ liệu nhạy cảm:

```java
public record Report(
        String id,
        String title,
        String customerName,
        String accountNumber,
        String internalNotes) {
}
```

Service lấy báo cáo từ repository:

```java
@Service
class ReportService {

    Report findReport(String id) {
        return new Report(
                id,
                "Quarterly revenue",
                "Nguyen Van A",
                "ACC-9988-SECRET",
                "Internal forecast: acquisition plan");
    }
}
```

Controller:

```java
@RestController
@RequestMapping("/api/reports")
class ReportController {

    private final ReportService reportService;

    ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/{id}")
    Report getReport(@PathVariable String id) {
        return reportService.findReport(id);
    }
}
```

Security policy chỉ cho ADMIN đọc báo cáo:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/reports/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Với policy này, Spring Security URL authorization từ chối user thường trước khi request được chuyển tới controller. Nếu filter chain được tích hợp đúng vào MockMvc, test có thể xác nhận service không bị gọi và response không chứa fixture bí mật.

Dữ liệu trong ví dụ chỉ là fixture giả lập. Không dùng dữ liệu khách hàng hoặc credential thật trong test snapshot, log hoặc nội dung bài học.

Các ví dụ lược bớt import thông thường. Tùy đoạn mã, cần thêm `Authentication`, `GrantedAuthority`, `SimpleGrantedAuthority`, `HttpHeaders`, `MediaType`, `HttpStatus`, `HttpServletResponse`, `MvcResult`, `@MockitoBean`, các matcher Hamcrest `not`/`containsString`, assertion AssertJ và `Mockito.verifyNoInteractions`.

## 4. Kiểm tra body không chứa dữ liệu khi request bị từ chối

### 4.1. Kiểm tra status và danh tính

Dùng `user()` để tạo danh tính thử nghiệm có role USER:

```java
@Test
void ordinaryUserCannotReadReport() throws Exception {
    mockMvc.perform(get("/api/reports/report-42")
                .with(user("mai").roles("USER")))
           .andExpect(status().isForbidden())
           .andExpect(authenticated()
                   .withUsername("mai")
                   .withRoles("USER"));
}
```

Đoạn test xác nhận request bị từ chối trong khi user vẫn được xác thực. Nhưng nó chưa kiểm tra nội dung response. Hãy thêm các assertion bảo đảm fixture không xuất hiện.

### 4.2. Không để lộ giá trị bí mật trong response body

Nếu handler trả JSON error theo hợp đồng API, có thể kiểm tra trường dữ liệu không tồn tại và các giá trị bí mật không xuất hiện:

```java
@Test
void forbiddenResponseDoesNotContainProtectedReportData() throws Exception {
    mockMvc.perform(get("/api/reports/report-42")
                .with(user("mai").roles("USER"))
                .accept(MediaType.APPLICATION_JSON))
           .andExpect(status().isForbidden())
           .andExpect(authenticated().withUsername("mai"))
           .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
           .andExpect(jsonPath("$.data").doesNotExist())
           .andExpect(jsonPath("$.accountNumber").doesNotExist())
           .andExpect(content().string(
                   not(containsString("ACC-9988-SECRET"))))
           .andExpect(content().string(
                   not(containsString("Internal forecast"))));
}
```

Các matcher `jsonPath(...).doesNotExist()` phù hợp khi response là JSON. Nếu ứng dụng trả body rỗng hoặc một định dạng khác, không gọi JSONPath; thay vào đó kiểm tra body theo đúng hợp đồng response.

`content().string(not(containsString(...)))` là kiểm tra phủ định trên toàn bộ response body. Nó hữu ích để bắt trường hợp dữ liệu bị lồng ở một vị trí không dự kiến, kể cả khi schema JSON đã thay đổi.

### 4.3. Không phản chiếu exception message cho client

Một lỗi phổ biến là đưa trực tiếp `exception.getMessage()` vào JSON:

```java
// Không nên trả nguyên exception message cho client
return ResponseEntity.status(HttpStatus.FORBIDDEN)
        .body(Map.of("message", exception.getMessage()));
```

Exception có thể chứa tên tài nguyên, truy vấn, ID nội bộ hoặc chi tiết implementation. Thay vào đó, handler nên trả một mã lỗi và thông báo công khai:

```java
public record ApiError(String code, String message) {
}

ApiError error = new ApiError(
        "ACCESS_DENIED",
        "Bạn không có quyền truy cập tài nguyên này");
```

Test cần xác nhận thông báo công khai có mặt và thông tin nội bộ vắng mặt:

```java
.andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
.andExpect(jsonPath("$.message")
        .value("Bạn không có quyền truy cập tài nguyên này"))
.andExpect(content().string(not(containsString("SQLSyntaxErrorException"))))
.andExpect(content().string(not(containsString("jdbc:"))))
.andExpect(content().string(not(containsString("internalNotes"))));
```

Ví dụ giả định ứng dụng đã cấu hình `AccessDeniedHandler` hoặc exception handler phù hợp để trả `ApiError`. `AccessDeniedHandler` mặc định không bắt buộc trả JSON theo cấu trúc này. Cần cấu hình response contract trước khi thêm các assertion body.

## 5. Chứng minh controller/service không chạy khi URL authorization từ chối

Khi policy được áp dụng ở filter chain, request không đủ quyền thường bị chặn trước khi tới controller. Có thể xác nhận điều đó bằng Mockito.

Với Spring Framework 6.2+/Spring Boot 3.4+, có thể dùng `@MockitoBean` để thay service bằng mock trong test:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ReportService reportService;

    @Test
    void deniedRequestDoesNotLoadProtectedReport() throws Exception {
        mockMvc.perform(get("/api/reports/report-42")
                    .with(user("mai").roles("USER")))
               .andExpect(status().isForbidden())
               .andExpect(authenticated().withUsername("mai"));

        verifyNoInteractions(reportService);
    }
}
```

Test này xác nhận request bị chặn ở URL authorization trước khi controller gọi service. Nếu dùng phiên bản Spring Boot cũ chưa có `@MockitoBean`, sử dụng cơ chế mock bean mà phiên bản đó hỗ trợ, ví dụ `@MockBean` trong các bản tương ứng.

Đây là bằng chứng bổ sung, không thay thế việc kiểm tra response body. Một handler vẫn có thể vô tình tiết lộ dữ liệu lấy từ nơi khác, dù service báo cáo không được gọi.

**Lưu ý về method security:** nếu controller đã chạy rồi mới gọi service có `@PreAuthorize`, controller/service invocation có thể diễn ra trước khi method security ném access-denied exception. Khi đó, kiểm tra `verifyNoInteractions(reportService)` là sai mục tiêu. Hãy kiểm tra repository hoặc component nằm sau method guard, và khẳng định không có thao tác lấy dữ liệu nhạy cảm nào xảy ra trước khi quyền được xác minh.

## 6. Kiểm tra người được phép vẫn nhận đúng dữ liệu

Một bộ test bảo mật cần có ca đối chứng cho ADMIN:

```java
@Test
void adminCanReadReportData() throws Exception {
    mockMvc.perform(get("/api/reports/report-42")
                .with(user("quantri").roles("ADMIN")))
           .andExpect(status().isOk())
           .andExpect(authenticated().withUsername("quantri"))
           .andExpect(jsonPath("$.accountNumber")
                   .value("ACC-9988-SECRET"));
}
```

Test này giả định `ReportService` trả fixture như mục 3. Nó chứng minh endpoint có thể cung cấp dữ liệu khi policy cho phép. Kết hợp với test USER bị từ chối, bộ test thể hiện rõ cả **tính bí mật** và **khả năng truy cập hợp lệ**.

Nếu API chủ ý chỉ trả một DTO rút gọn, test ADMIN cũng cần xác nhận đúng những trường được phép xuất hiện. Không nên kỳ vọng entity nội bộ được serialize toàn bộ nếu hợp đồng công khai chỉ cho phép một phần dữ liệu.

## 7. Không tiết lộ sự tồn tại của tài nguyên nếu policy yêu cầu che giấu

Một số hệ thống không muốn caller biết tài nguyên có tồn tại hay không. Ví dụ, người dùng không thuộc tenant có thể nhận cùng một response cho cả hai trường hợp:

- ID báo cáo không tồn tại.
- ID báo cáo có tồn tại nhưng thuộc tenant khác.

Đây là chính sách che giấu sự tồn tại (resource concealment), thường được triển khai bằng cách trả 404 trong cả hai trường hợp. Không phải ứng dụng nào cũng cần làm vậy; nhiều API công khai 403 khi user đã xác thực nhưng thiếu quyền.

Nếu policy yêu cầu hai tình huống không thể phân biệt, hãy kiểm tra response của cả hai:

Với biến thể này, cấu hình URL phải cho phép user đã xác thực tới lớp xử lý tenant (ví dụ `authenticated()`), còn service/repository kiểm tra quyền sở hữu và chuẩn hóa cả tài nguyên không tồn tại lẫn tài nguyên thuộc tenant khác thành 404. Không áp dụng nguyên rule `hasRole("ADMIN")` ở mục 3 cho hai request này, vì rule đó sẽ chặn cả hai trước khi logic che giấu sự tồn tại được thực thi.

```java
@Test
void inaccessibleAndMissingReportsHaveSamePublicResponse() throws Exception {
    MvcResult forbiddenByTenant = mockMvc.perform(
                    get("/api/reports/tenant-b/report-42")
                        .with(user("mai").roles("USER")))
            .andReturn();

    MvcResult missingReport = mockMvc.perform(
                    get("/api/reports/does-not-exist")
                        .with(user("mai").roles("USER")))
            .andReturn();

    assertThat(forbiddenByTenant.getResponse().getStatus())
            .isEqualTo(HttpStatus.NOT_FOUND.value());
    assertThat(missingReport.getResponse().getStatus())
            .isEqualTo(HttpStatus.NOT_FOUND.value());

    assertThat(forbiddenByTenant.getResponse().getContentAsString())
            .isEqualTo(missingReport.getResponse().getContentAsString());
}
```

Ví dụ này giả định ứng dụng cố ý chuẩn hóa cả hai kết quả thành 404 và cùng error body. Nếu policy dùng 403 cho tài nguyên tồn tại nhưng bị cấm, không áp dụng assertion này. Việc chuẩn hóa response body cũng chưa loại bỏ mọi side channel như thời gian xử lý; MockMvc không phải công cụ đo timing attack.

## 8. Kiểm tra headers và redirect không chứa dữ liệu nhạy cảm

### 8.1. Header chỉ nên chứa thông tin giao thức cần thiết

Một response 401 có thể cần `WWW-Authenticate: Basic` hoặc `Bearer`. Header không nên chứa password, access token, raw claim hay dữ liệu tài nguyên.

```java
@Test
void unauthorizedChallengeDoesNotExposeCredentials() throws Exception {
    mockMvc.perform(get("/api/reports/report-42"))
           .andExpect(status().isUnauthorized())
           .andExpect(unauthenticated())
           .andExpect(header().string(
                   HttpHeaders.WWW_AUTHENTICATE,
                   startsWith("Basic")))
           .andExpect(header().doesNotExist("X-Internal-Account"))
           .andExpect(header().doesNotExist("X-Debug-Token"));
}
```

Hai header `X-Internal-Account` và `X-Debug-Token` là ví dụ về header nội bộ không thuộc hợp đồng công khai. Thay chúng bằng tên header thực tế mà ứng dụng cần bảo vệ. Không nên khẳng định mọi custom header đều phải bị loại bỏ; chỉ kiểm tra các giá trị không được phép phát hành.

### 8.2. Location không được mang token hoặc dữ liệu cá nhân

Form login thường redirect tới một URL nội bộ. OAuth2 authorization redirect có thể chứa `state`, `nonce`, `client_id` và các tham số giao thức cần thiết. Tuy nhiên, không nên đưa access token, refresh token, password, account number hoặc thông tin nhạy cảm vào query string.

Ví dụ kiểm tra URL redirect:

```java
@Test
void loginRedirectDoesNotContainSensitiveValues() throws Exception {
    MvcResult result = mockMvc.perform(get("/account/profile"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

    String location = result.getResponse().getHeader(HttpHeaders.LOCATION);

    assertThat(location).isNotNull();
    assertThat(location).contains("/login");
    assertThat(location).doesNotContain("ACC-9988-SECRET");
    assertThat(location).doesNotContain("access_token");
    assertThat(location).doesNotContain("password");
}
```

Đây là test cho form login redirect, không phải OAuth2 authorization request. Với OAuth2, `state` và PKCE code challenge là tham số giao thức hợp lệ; không nên cấm chúng bằng assertion tổng quát. Thay vào đó, khẳng định URL không chứa credential hoặc dữ liệu tài nguyên, đồng thời xác minh các tham số OAuth2 bắt buộc theo cấu hình.

## 9. Chính sách cache cho response nhạy cảm

Nếu response chứa dữ liệu tài khoản, báo cáo hoặc hồ sơ riêng tư, cache sai có thể làm dữ liệu của user này xuất hiện với user khác. Với dữ liệu nhạy cảm, ứng dụng thường chọn `Cache-Control: no-store` để yêu cầu không lưu response vào cache.

Spring Security có thể thêm cache-control headers mặc định thông qua security headers. Nếu ứng dụng tùy chỉnh cấu hình cache, hãy kiểm tra chính sách thực tế:

```java
@Test
void sensitiveReportResponseIsNotStoredByCaches() throws Exception {
    mockMvc.perform(get("/api/reports/report-42")
                .with(user("quantri").roles("ADMIN")))
           .andExpect(status().isOk())
           .andExpect(header().string(
                   HttpHeaders.CACHE_CONTROL,
                   containsString("no-store")));
}
```

Với response bị từ chối cũng có thể cần chính sách cache tương ứng:

```java
@Test
void forbiddenResponseIsNotCached() throws Exception {
    mockMvc.perform(get("/api/reports/report-42")
                .with(user("mai").roles("USER")))
           .andExpect(status().isForbidden())
           .andExpect(header().string(
                   HttpHeaders.CACHE_CONTROL,
                   containsString("no-store")));
}
```

Các assertion này giả định response thực sự được cấu hình `Cache-Control: no-store`. Không phải mọi endpoint đều cần cùng chính sách cache; hãy xác định theo loại dữ liệu, session, shared cache và cách xác thực. Với response có thể thay đổi theo `Authorization` hoặc cookie, cần thiết kế cache key và `Vary` phù hợp; `Vary` không thay thế `no-store` khi dữ liệu tuyệt đối không được lưu.

## 10. Error response an toàn: ví dụ hợp đồng API

Một error response tốt thường có mã ổn định và thông báo công khai, không phản chiếu đối tượng tài nguyên:

```json
{
  "code": "ACCESS_DENIED",
  "message": "Bạn không có quyền truy cập tài nguyên này"
}
```

Không nên trả:

```json
{
  "code": "ACCESS_DENIED",
  "message": "User mai cannot read account ACC-9988-SECRET from table customer_private",
  "exception": "org.springframework.security.access.AccessDeniedException",
  "stackTrace": "..."
}
```

Response thứ hai làm lộ username, số tài khoản, tên bảng và chi tiết implementation. Test nên kiểm tra cả trường được phép và trường không được phép:

```java
.andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
.andExpect(jsonPath("$.message").isNotEmpty())
.andExpect(jsonPath("$.exception").doesNotExist())
.andExpect(jsonPath("$.stackTrace").doesNotExist())
.andExpect(content().string(not(containsString("ACC-9988-SECRET"))))
.andExpect(content().string(not(containsString("customer_private"))));
```

Nếu ứng dụng dùng RFC 9457 Problem Details, hãy kiểm tra `application/problem+json`, `status`, `title`, `detail` và extension fields. `detail` phải là nội dung công khai; không đưa nguyên exception message hoặc stack trace vào trường này.

## 11. Reactive: kiểm tra body và header với WebTestClient

`SecurityMockMvcResultMatchers` chỉ dành cho Servlet/MockMvc. Với WebFlux, dùng `WebTestClient` và các security configurer Reactive như `mockUser()` hoặc `mockJwt()`.

Ví dụ request user thường bị từ chối:

```java
webTestClient.mutateWith(mockUser("mai").roles("USER"))
        .get()
        .uri("/api/reports/report-42")
        .exchange()
        .expectStatus().isForbidden()
        .expectBody()
        .jsonPath("$.code").isEqualTo("ACCESS_DENIED")
        .jsonPath("$.accountNumber").doesNotExist()
        .jsonPath("$.internalNotes").doesNotExist();
```

Ví dụ giả định ứng dụng Reactive có custom access-denied response JSON với mã `ACCESS_DENIED`. Nếu handler trả body rỗng, hãy dùng `expectBody().isEmpty()` hoặc kiểm tra body theo hợp đồng thực tế.

Kiểm tra header cache:

```java
webTestClient.mutateWith(mockUser("quantri").roles("ADMIN"))
        .get()
        .uri("/api/reports/report-42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueMatches(
                HttpHeaders.CACHE_CONTROL, ".*no-store.*");
```

WebTestClient cho phép kiểm tra status, headers và body theo cách tương tự MockMvc. Tuy nhiên, không dùng result matcher Servlet cho WebFlux. Nếu cần xác minh service/repository không bị gọi, sử dụng mock bean và verify ở test phù hợp với reactive execution; lưu ý subscription có thể trì hoãn việc thực thi cho tới khi body được consume.

## 12. Ma trận kiểm tra chống rò rỉ dữ liệu

| Trường hợp | Status/authentication | Body assertion | Header/side effect |
| --- | --- | --- | --- |
| Anonymous gọi API bảo vệ | `401` + `unauthenticated()` (với Basic/Bearer) | Không có dữ liệu tài nguyên | Challenge đúng scheme, không có custom header bí mật |
| User thường gọi endpoint ADMIN | `403` + `authenticated()` | Không có account number, notes hoặc secret | Cache policy phù hợp |
| JWT thiếu scope | `403` + `JwtAuthenticationToken` | Chỉ error contract công khai | Không đưa token/claim nhạy cảm vào header/body |
| Request bị URL authorization chặn | `403` + danh tính hợp lệ | Error body không có dữ liệu | Service/repository không được gọi |
| Method security từ chối | `403` + danh tính hợp lệ | Không phản chiếu exception detail | Repository không thực hiện thao tác nhạy cảm |
| Tài nguyên không tồn tại và bị che giấu | Cùng status theo policy, thường 404 | Body công khai giống nhau nếu yêu cầu | Không tiết lộ ID/tên tài nguyên qua Location |
| User có quyền | `200` + authenticated | Có đúng trường được phép | Cache theo policy dữ liệu |

Không phải mọi hàng đều bắt buộc cho mọi API. Chọn những kiểm tra tương ứng với chính sách và loại dữ liệu của endpoint.

## 13. Lỗi thường gặp khi viết test

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test 403 pass nhưng vẫn lộ dữ liệu | Chỉ assert status, không kiểm tra body | Thêm JSONPath và kiểm tra phủ định trên toàn body |
| JSONPath fail vì body rỗng | Handler không trả JSON | Dùng assertion body rỗng hoặc kiểm tra đúng content type/contract |
| Test service never invoked fail | Authorization nằm ở method security sau khi controller đã gọi service | Verify repository hoặc thao tác dữ liệu nằm sau method guard |
| Test không phát hiện leak ở field mới | Chỉ kiểm tra vài JSONPath | Kết hợp kiểm tra chuỗi nhạy cảm trên toàn body và schema allowlist khi phù hợp |
| Response lỗi chứa exception message | Handler serialize exception trực tiếp | Trả mã lỗi/thông báo công khai, ghi chi tiết vào log nội bộ có kiểm soát |
| Redirect query chứa dữ liệu nhạy cảm | Đưa credential hoặc dữ liệu cá nhân vào URL | Chỉ truyền state/nonce và tham số điều hướng cần thiết |
| Cache trả dữ liệu user khác | Response nhạy cảm có cache policy không phù hợp | Xem xét `no-store`, cache key và `Vary` |
| 404 concealment test khác body | Hai luồng lỗi có handler hoặc message khác nhau | Chuẩn hóa response nếu chính sách yêu cầu không tiết lộ tồn tại |

Một phép kiểm tra phủ định chỉ có ý nghĩa khi giá trị cần bảo vệ được chọn đúng. Hãy dùng fixture giả lập có dấu hiệu nhận diện rõ, chẳng hạn `ACC-9988-SECRET`, để test có thể phát hiện nếu dữ liệu vô tình xuất hiện.

## 14. Bài tập thực hành

Dùng API báo cáo trong bài để thực hiện:

1. Viết test anonymous và user thường gọi `/api/reports/report-42`. Khẳng định status/authentication tương ứng và response không chứa account number, customer name hoặc internal notes.
2. Tạo custom `AccessDeniedHandler` trả JSON có `code` và `message`. Khẳng định response không chứa exception class, stack trace, SQL hoặc ID tài nguyên bí mật.
3. Dùng mock service/repository để xác minh URL authorization chặn request trước khi dữ liệu được tải.
4. Thêm test ADMIN được phép đọc báo cáo và xác nhận các trường công khai được trả đúng.
5. Nếu hệ thống che giấu sự tồn tại tài nguyên, so sánh status và body giữa ID không tồn tại và ID thuộc tenant khác.
6. Kiểm tra `Cache-Control: no-store` cho response có dữ liệu riêng tư theo chính sách ứng dụng.
7. Viết test WebTestClient tương đương cho API Reactive, kiểm tra status, body và header mà không dùng matcher Servlet.

**Tiêu chí hoàn thành:** Người học chứng minh được request bị từ chối không làm lộ dữ liệu tài nguyên; phân biệt assertion status với assertion bảo mật và nội dung; kiểm tra cả body/header/redirect/cache khi cần; đồng thời giữ test thành công để xác nhận người có quyền vẫn truy cập được đúng dữ liệu.

## Tài liệu tham khảo chính thức

- [Spring Security — Testing Spring MVC Applications](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security — MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
