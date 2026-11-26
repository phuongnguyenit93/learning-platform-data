# Kết hợp khẳng định trạng thái, nội dung, header và trạng thái bảo mật

> **Chương:** Chiến lược kiểm thử  
> **Module:** `SPRING_SECURITY_TESTING` — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài sử dụng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và các danh tính JWT/OAuth2/OIDC giả lập.

## 1. Vì sao một status code chưa đủ?

Một test bảo mật thường bắt đầu bằng assertion như `status().isForbidden()` hoặc `expectStatus().isUnauthorized()`. Đây là tín hiệu quan trọng, nhưng nó chỉ trả lời một phần câu hỏi: request nhận status nào?

Ví dụ `GET /api/reports` trả `403` có thể là kết quả đúng khi user thiếu `REPORT_READ`. Nhưng cùng status đó cũng có thể xuất hiện vì:

- Request POST bị CSRF filter chặn trước khi authorization rule được kiểm tra.
- User đủ quyền nhưng URL matcher hoặc HTTP method sai.
- Một access-denied handler tùy chỉnh trả `403` cho lỗi nghiệp vụ không liên quan.
- Controller hoặc service đã chạy, đọc dữ liệu nhạy cảm, rồi mới phát sinh lỗi.
- Response body vô tình chứa dữ liệu báo cáo dù status là `403`.

Một kiểm thử đáng tin cần kết hợp nhiều loại bằng chứng:

1. **Status:** quyết định HTTP có đúng hợp đồng không?
2. **Nội dung:** response có đúng dữ liệu được phép và không làm lộ dữ liệu bị cấm không?
3. **Header:** challenge, redirect, cache policy, security headers và CORS có đúng cấu hình không?
4. **Trạng thái bảo mật:** request được xử lý dưới principal/authority nào; anonymous, authenticated hay bị từ chối?
5. **Tác động phụ:** service, repository, gateway hoặc event publisher có bị gọi khi request bị chặn không?

```text
Security test result
  = HTTP decision
  + response representation
  + protocol/security metadata
  + authenticated identity state
  + observable side effects
```

Không phải mọi test đều phải assert tất cả các chiều. Hãy chọn assertion theo rủi ro và mục tiêu của từng ca. Với một endpoint công khai đơn giản, status và body có thể đủ. Với API chứa dữ liệu cá nhân hoặc thao tác ghi, cần kiểm tra thêm dữ liệu, trạng thái bảo mật và side effect.

## 2. Xác định response contract trước khi viết assertion

Giả sử API báo cáo có các quy tắc:

- `GET /public/status` cho phép anonymous.
- `GET /api/reports` yêu cầu authority `REPORT_READ`.
- `POST /api/reports/export` yêu cầu `REPORT_EXPORT` và CSRF hợp lệ trên nhánh session/cookie.
- `GET /partner/reports` yêu cầu Bearer JWT hợp lệ có scope `reports.read`.
- API dùng HTTP Basic hoặc Bearer entry point trả `401` khi chưa xác thực; principal đã xác thực nhưng thiếu quyền nhận `403`.

Một contract tối thiểu:

| Trường hợp | Status ví dụ | Body | Header / security state |
|---|---:|---|---|
| Anonymous vào API bảo vệ bằng Basic | `401` | Không có báo cáo | `WWW-Authenticate: Basic`; unauthenticated |
| User có `REPORT_READ` | `200` | Báo cáo trong phạm vi cho phép | Authenticated với principal đúng |
| User thiếu `REPORT_READ` | `403` | Không có nội dung báo cáo | Authenticated; giữ đúng identity |
| JWT hợp lệ thiếu scope | `403` | Không có dữ liệu đối tác | Bearer authentication đã thành công |
| JWT hết hạn/sai chữ ký | `401` | Không có dữ liệu | Decoder từ chối; không tạo authenticated principal |
| POST thiếu CSRF | `403` | Không có xác nhận export | Token bị từ chối; export không chạy |
| Form login thành công | Thường `302` | Thường không cần body | `Location` theo cấu hình; session/cookie được tạo |

Status và header trong bảng là ví dụ theo cấu hình đã chọn. Form login có thể redirect; API có thể dùng handler khác; ứng dụng che giấu tài nguyên có thể trả `404` thay `403`. Hãy ghi rõ contract thật của ứng dụng thay vì áp một status cho mọi hệ thống.

### Một response có thể cần nhiều assertion

Với anonymous request vào API Basic, các bằng chứng có thể gồm:

- HTTP status là `401`.
- Header `WWW-Authenticate` chỉ ra challenge Basic.
- Response không chứa dữ liệu báo cáo.
- Security context không có authenticated principal.
- Service đọc báo cáo không được gọi.

Mỗi assertion bảo vệ một thuộc tính khác nhau. Nếu chỉ assert `401`, ta chưa phát hiện được việc body lộ dữ liệu hoặc service đã bị gọi.

## 3. Khẳng định status đúng loại từ chối

Các status thường gặp:

| Status | Ý nghĩa thường dùng | Câu hỏi cần xác minh |
|---|---|---|
| `200 OK` | Request đọc/xử lý thành công | Có đúng dữ liệu, đúng principal và đúng phạm vi không? |
| `201 Created` | Tạo tài nguyên thành công | Location/body có định danh tài nguyên mới không? |
| `204 No Content` | Thành công không có response body | Tài nguyên có thực sự thay đổi đúng không? |
| `302 Found` | Redirect, thường gặp ở form login | `Location` có đúng trang đích không? |
| `401 Unauthorized` | Chưa có authentication hợp lệ | Có challenge/redirect theo entry point không? |
| `403 Forbidden` | Đã xác thực nhưng không được phép, hoặc request bị CSRF từ chối | Có xác định đúng lớp đã từ chối không? |
| `404 Not Found` | Không tồn tại hoặc cố ý che giấu tài nguyên | Có tránh tiết lộ sự tồn tại của tài nguyên không? |
| `405 Method Not Allowed` | HTTP method không được endpoint hỗ trợ | Header `Allow` có liệt kê method hợp lệ không? |
| `409 Conflict` | Xung đột trạng thái nghiệp vụ | Dữ liệu có giữ nguyên sau thao tác thất bại không? |

`401` và `403` không thể thay thế nhau trong mọi contract. Một request anonymous có thể bị chuyển hướng `302` trong ứng dụng form login. Một tài nguyên của tenant khác có thể trả `404` để tránh lộ việc tài nguyên tồn tại. Một request POST thiếu CSRF có thể trả `403` trước khi quyền nghiệp vụ được đánh giá.

### Ví dụ assertion status với MockMvc

```java
mvc.perform(get("/api/reports"))
    .andExpect(status().isUnauthorized());

mvc.perform(get("/api/reports")
        .with(user("binh").authorities(
            new SimpleGrantedAuthority("ORDER_READ"))))
    .andExpect(status().isForbidden());

mvc.perform(get("/api/reports")
        .with(user("an").authorities(
            new SimpleGrantedAuthority("REPORT_READ"))))
    .andExpect(status().isOk());
```

### Ví dụ assertion status với WebTestClient

```java
client.get().uri("/api/reports")
    .exchange()
    .expectStatus().isUnauthorized();

client.mutateWith(mockUser("binh")
        .authorities(new SimpleGrantedAuthority("ORDER_READ")))
    .get().uri("/api/reports")
    .exchange()
    .expectStatus().isForbidden();

client.mutateWith(mockUser("an")
        .authorities(new SimpleGrantedAuthority("REPORT_READ")))
    .get().uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

Hai nhóm ví dụ giả định security filter chain tương ứng đã được nạp và áp dụng. `user()`/`mockUser()` giả lập danh tính để kiểm tra authorization; chúng không kiểm tra password hoặc token thật.

## 4. Khẳng định nội dung: đúng dữ liệu và không rò rỉ dữ liệu

Status thành công không đảm bảo body đúng. User có `REPORT_READ` có thể nhận báo cáo của tenant khác; controller có thể serialize cả trường nội bộ không được công bố. Ngược lại, status từ chối nhưng body vẫn có dữ liệu nhạy cảm cũng là lỗi bảo mật.

### 4.1. Kiểm tra body thành công

Giả sử API trả JSON:

```json
{
  "reportId": "R-100",
  "tenant": "acme",
  "total": 125000,
  "currency": "VND"
}
```

MockMvc:

```java
mvc.perform(get("/api/reports/R-100")
        .with(user("an").authorities(
            new SimpleGrantedAuthority("REPORT_READ"))))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.reportId").value("R-100"))
    .andExpect(jsonPath("$.tenant").value("acme"))
    .andExpect(jsonPath("$.total").value(125000))
    .andExpect(jsonPath("$.currency").value("VND"));
```

WebTestClient:

```java
client.mutateWith(mockUser("an")
        .authorities(new SimpleGrantedAuthority("REPORT_READ")))
    .get().uri("/api/reports/R-100")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.reportId").isEqualTo("R-100")
    .jsonPath("$.tenant").isEqualTo("acme")
    .jsonPath("$.total").isEqualTo(125000);
```

Những assertion này chứng minh nội dung trả về khớp dữ liệu fixture và contract. Khi dữ liệu có thể thay đổi, tạo fixture ổn định trong test thay vì hardcode giá trị phụ thuộc môi trường.

### 4.2. Kiểm tra body không chứa dữ liệu bị cấm

Với user thiếu quyền, ngoài status `403`, kiểm tra response không có trường bí mật:

```java
mvc.perform(get("/api/reports/R-100")
        .with(user("binh").authorities(
            new SimpleGrantedAuthority("ORDER_READ"))))
    .andExpect(status().isForbidden())
    .andExpect(content().string(not(containsString("125000"))))
    .andExpect(jsonPath("$.customerEmail").doesNotExist());
```

Nếu response từ chối là body rỗng hoặc error JSON, assertion phải phù hợp contract thực. Không ép JSONPath lên response không phải JSON. Có thể kiểm tra một chuỗi bí mật đã biết không xuất hiện, nhưng tốt hơn là kiểm tra schema/error representation và dữ liệu nhạy cảm quan trọng.

Một test denial có giá trị nên kiểm tra:

- Không có tên, email, số tài khoản, nội dung báo cáo hoặc dữ liệu tenant không được phép.
- Không trả metadata cho phép suy ra tài nguyên bị che giấu, nếu policy yêu cầu che giấu.
- Error response không chứa stack trace, SQL, token hoặc chi tiết cấu hình nội bộ.

Đừng dùng một assertion quá chung như “body không rỗng” cho mọi response lỗi; thông báo lỗi có thể hữu ích nhưng cần bảo đảm không lộ thông tin.

### 4.3. Kiểm tra đúng chủ thể và phạm vi dữ liệu

Nếu principal `an` thuộc tenant `acme`, body trả về phải thuộc tenant đó. Một test status `200` mà không kiểm tra tenant có thể bỏ sót lỗi IDOR/BOLA hoặc tenant isolation.

Tạo ít nhất hai bản ghi khác tenant và assert rõ tài nguyên trả về. Nếu API trả danh sách, kiểm tra mọi phần tử nằm trong phạm vi cho phép, không chỉ kiểm tra phần tử đầu tiên.

## 5. Khẳng định header: challenge, redirect và security policy

Header là một phần của HTTP contract. Một số header cho biết cách client tiếp tục, một số hạn chế hành vi trình duyệt, và một số phản ánh chính sách bảo mật.

| Header | Tình huống cần kiểm tra | Ghi chú |
|---|---|---|
| `WWW-Authenticate` | API yêu cầu Basic/Bearer authentication | Challenge phải khớp cơ chế được cấu hình |
| `Location` | Form login hoặc redirect | URL đích đúng theo contract |
| `Content-Type` | JSON, HTML, problem response | Định dạng khớp body |
| `Cache-Control` | Response có dữ liệu nhạy cảm | Kiểm tra cache policy theo cấu hình |
| `X-Content-Type-Options` | Browser hardening | Ví dụ giá trị `nosniff` nếu cấu hình yêu cầu |
| `X-Frame-Options` | Chống clickjacking | Có thể là `DENY`/`SAMEORIGIN` hoặc CSP frame-ancestors |
| `Strict-Transport-Security` | HTTPS deployment | Chỉ kiểm tra trong request HTTPS và cấu hình HSTS bật |
| `Content-Security-Policy` | Chính sách nội dung trình duyệt | Kiểm tra directive cụ thể của ứng dụng |
| `Access-Control-Allow-Origin` | CORS response/preflight | Chỉ origin được phép mới được cấp |
| `Allow` | Method không được hỗ trợ | Liệt kê method endpoint cho phép |

Không nên assert một header chỉ vì nó thường xuất hiện trong cấu hình mặc định của Spring Security. Header có thể bị thay đổi hoặc tắt theo profile; HSTS còn phụ thuộc request được nhận diện là HTTPS.

### 5.1. Basic challenge cho anonymous request

```java
mvc.perform(get("/api/reports"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        startsWith("Basic")));
```

Với API Bearer, challenge có thể chứa scheme `Bearer` và các tham số như `error` tùy trường hợp. Hãy assert phần contract cần thiết thay vì so sánh nguyên chuỗi header nếu thứ tự/tham số không phải yêu cầu.

### 5.2. Redirect của form login

```java
mvc.perform(get("/admin/reports"))
    .andExpect(status().is3xxRedirection())
    .andExpect(redirectedUrlPattern("**/login"));
```

Đây là ví dụ cho ứng dụng form login có entry point redirect anonymous user đến login page. Nếu app dùng context path hoặc URL login tùy chỉnh, thay matcher cho đúng contract. Với REST API, redirect HTML login có thể là hành vi sai nếu client mong `401`.

### 5.3. Security headers

```java
mvc.perform(get("/public/status"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "X-Content-Type-Options", "nosniff"));
```

Chỉ giữ assertion nếu header là một yêu cầu cấu hình của ứng dụng. Với HSTS, hãy chạy request qua HTTPS hoặc mô phỏng request được đánh dấu secure theo cách phù hợp; request HTTP thuần không đủ để kết luận HSTS đang sai nếu header được cấu hình chỉ thêm trên secure request.

### 5.4. CORS preflight

Một browser preflight thường là `OPTIONS` với `Origin` và `Access-Control-Request-Method`. Test nên kiểm tra origin được phép và origin bị cấm:

```java
mvc.perform(options("/api/reports")
        .header(HttpHeaders.ORIGIN, "https://console.example.test")
        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
        "https://console.example.test"));
```

Ví dụ giả định origin trên đã được khai báo cho phép và cấu hình CORS được áp dụng cho security chain. Với origin không được phép, assert không có header allow-origin phù hợp; status có thể phụ thuộc cấu hình CORS và cách server xử lý preflight. CORS không thay thế authorization: một client không phải browser vẫn có thể gọi API, nên rule quyền phải được kiểm tra riêng.

## 6. Khẳng định trạng thái bảo mật của request

Một test authorization cần biết request đang chạy với principal nào và authorities nào. Chỉ assert status đôi khi chưa đủ để xác định request bị từ chối ở bước nào.

### 6.1. SecurityMockMvcResultMatchers

`spring-security-test` cung cấp matcher cho trạng thái authentication của request:

- `authenticated()`: request được xử lý dưới một authentication hợp lệ trong test.
- `unauthenticated()`: request không được xác thực.
- Có thể nối matcher username, roles hoặc authorities để kiểm tra principal theo contract.

Ví dụ:

```java
mvc.perform(get("/api/reports")
        .with(user("an").authorities(
            new SimpleGrantedAuthority("REPORT_READ"))))
    .andExpect(status().isOk())
    .andExpect(authenticated().withUsername("an")
        .withAuthorities(
            new SimpleGrantedAuthority("REPORT_READ")));

mvc.perform(get("/api/reports"))
    .andExpect(status().isUnauthorized())
    .andExpect(unauthenticated());
```

Với user thiếu quyền:

```java
mvc.perform(get("/api/reports")
        .with(user("binh").authorities(
            new SimpleGrantedAuthority("ORDER_READ"))))
    .andExpect(status().isForbidden())
    .andExpect(authenticated().withUsername("binh")
        .withAuthorities(
            new SimpleGrantedAuthority("ORDER_READ")));
```

Điểm quan trọng: request `403` vẫn có thể có authentication hợp lệ. Assertion `authenticated()` giúp phân biệt “đã xác thực nhưng bị từ chối” với “không có danh tính”. Matcher này kiểm tra trạng thái security trong request test; nó không chứng minh password hoặc JWT signature được xác minh thật nếu principal được tạo bằng helper.

### 6.2. SecurityContext trong Servlet

Trong Servlet, `SecurityContextHolder` thường cung cấp context trong quá trình xử lý request; cơ chế lưu context qua request/session phụ thuộc `SecurityContextRepository` và cấu hình ứng dụng.

Không nên kiểm tra một biến static/thread-local ngoài lifecycle request rồi kết luận session persistence hoạt động. Hãy:

- Dùng `authenticated()`/`unauthenticated()` cho trạng thái authentication của request hiện tại.
- Nếu cần kiểm tra session, thực hiện login thật, giữ session/cookie rồi gửi request tiếp theo.
- Nếu cần kiểm tra logout, gửi logout request theo cấu hình và xác minh session cũ không còn truy cập được endpoint bảo vệ.

### 6.3. SecurityContext trong Reactive

WebFlux sử dụng `ReactiveSecurityContextHolder` và Reactor context. Không thể giả định `SecurityContextHolder` dựa trên ThreadLocal phản ánh principal trong pipeline Reactive.

Một endpoint profile có thể lấy principal từ reactive context để trả về tên hiển thị:

```java
@RestController
class CurrentUserController {

    @GetMapping("/api/me")
    Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> Map.of(
                "username",
                context.getAuthentication().getName()));
    }
}
```

Test với `WebTestClient`:

```java
client.mutateWith(mockUser("an")
        .authorities(new SimpleGrantedAuthority("REPORT_READ")))
    .get().uri("/api/me")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.username").isEqualTo("an");
```

Đây là ví dụ minh họa cách một handler sử dụng security context; trong ứng dụng thực, không nên trả toàn bộ authorities hoặc claims nhạy cảm ra endpoint chỉ để test. Có thể kiểm tra principal ở service/handler hoặc dùng response profile đã được thiết kế công khai.

## 7. Khẳng định cookie, session và redirect trong hành trình đăng nhập

Với form login, status `302` một mình chưa chứng minh người dùng đã đăng nhập thành công. Cần kiểm tra:

- Redirect đến trang đích đúng.
- Security context chứa principal mong đợi.
- Session/cookie được tạo theo cấu hình.
- Request kế tiếp dùng session đó truy cập được tài nguyên bảo vệ.
- Logout hoặc hết hạn session làm request tiếp theo mất authentication.

Một ví dụ Servlet sử dụng login endpoint mặc định `/login` và parameter mặc định `username`/`password`; điều chỉnh theo cấu hình thực tế:

```java
MvcResult login = mvc.perform(post("/login")
        .param("username", "an")
        .param("password", "correct-password")
        .with(csrf()))
    .andExpect(status().is3xxRedirection())
    .andExpect(authenticated().withUsername("an"))
    .andReturn();

MockHttpSession session =
    (MockHttpSession) login.getRequest().getSession(false);

assertThat(session).isNotNull();

mvc.perform(get("/admin/reports").session(session))
    .andExpect(status().isOk())
    .andExpect(authenticated().withUsername("an"));
```

Đoạn này giả định login thành công, CSRF bật, session-based security context được cấu hình và user `an` có quyền truy cập `/admin/reports`. Nếu app dùng stateless session policy hoặc custom security context repository, cách giữ danh tính qua request sẽ khác.

Cookie session có thể được assert qua response cookie nếu test qua server HTTP hoặc container hỗ trợ. Đừng hardcode tên cookie `JSESSIONID` nếu ứng dụng đổi tên hoặc dùng session cookie khác. Điều quan trọng là cookie/session thực sự được tái sử dụng ở request kế tiếp.

Để kiểm tra logout, gửi request đến logout endpoint với session đang dùng và CSRF token nếu logout yêu cầu; sau đó dùng session/cookie cũ truy cập tài nguyên bảo vệ và xác minh request không còn authenticated. Test chỉ assert redirect sau logout mà không thử session cũ chưa chứng minh session đã bị vô hiệu hóa.

## 8. Khẳng định CSRF cùng với quyền và side effect

CSRF là một điều kiện request độc lập. Khi kiểm tra quyền của POST/DELETE trên nhánh session/cookie, hãy cấp token hợp lệ để chỉ quyền là biến thay đổi. Khi kiểm tra CSRF, giữ user và authority đủ để request có thể đi tiếp nếu token hợp lệ.

Servlet:

```java
@Test
@WithMockUser(username = "an", authorities = "REPORT_EXPORT")
void authorizedExportWithCsrfSucceeds() throws Exception {
    mvc.perform(post("/api/reports/export")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"format\":\"CSV\"}"))
        .andExpect(status().isAccepted())
        .andExpect(header().string("X-Export-Status", "queued"));
}

@Test
@WithMockUser(username = "an", authorities = "REPORT_EXPORT")
void missingCsrfIsRejectedAndExportIsNotQueued() throws Exception {
    mvc.perform(post("/api/reports/export")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"format\":\"CSV\"}"))
        .andExpect(status().isForbidden());

    verifyNoInteractions(exportService);
}
```

Ví dụ giả định export được chấp nhận trả `202 Accepted` và header `X-Export-Status`. Nếu handler thực tế trả status khác, cập nhật theo contract. Ca bị từ chối xác minh service không được gọi, giúp phát hiện lỗi request đi qua quá sâu trước khi bị chặn.

Reactive dùng `mutateWith(csrf())` cho request có token hợp lệ. Với ca thiếu token, không gọi helper CSRF:

```java
client.mutateWith(mockUser("an")
        .authorities(new SimpleGrantedAuthority("REPORT_EXPORT")))
    .post().uri("/api/reports/export")
    .bodyValue(Map.of("format", "CSV"))
    .exchange()
    .expectStatus().isForbidden();
```

Cần xác minh thêm side effect bằng mock collaborator hoặc dữ liệu tích hợp. Status `403` không tự bảo đảm export queue không nhận lệnh nếu application code có thứ tự xử lý sai.

## 9. JWT: status, body, header và authentication state

Với Bearer resource server, các assertion nên phân biệt:

| Trường hợp | Status | Header | Security state | Body |
|---|---:|---|---|---|
| Không có token | `401` | Challenge Bearer theo cấu hình | Unauthenticated | Không có dữ liệu |
| Token sai chữ ký/hết hạn | `401` | Challenge/error theo handler | Không có authenticated principal | Không lộ thông tin |
| Token hợp lệ thiếu scope | `403` | Có thể không có challenge mới | Authenticated với authorities thiếu | Không có dữ liệu |
| Token hợp lệ đủ scope | `200` | Content-Type đúng | Authenticated với scope được ánh xạ | Dữ liệu trong phạm vi |

Mock JWT test:

```java
mvc.perform(get("/partner/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk())
    .andExpect(authenticated());

mvc.perform(get("/partner/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.write"))))
    .andExpect(status().isForbidden())
    .andExpect(authenticated());
```

Hai ca trên chứng minh authorization theo authorities được dựng. Chúng không chứng minh chữ ký, issuer, audience hoặc expiration. Để kiểm tra token lỗi, gửi Bearer token qua decoder thật và assert `401` cùng body/header phù hợp.

Nếu response chứa lỗi OAuth2 chuẩn, kiểm tra error code theo contract nhưng tránh khóa cứng các chi tiết triển khai không ổn định. Không phản chiếu token nguyên vẹn hoặc claims nhạy cảm vào error body/log.

## 10. Khẳng định side effect và trạng thái dữ liệu

Đối với thao tác thay đổi dữ liệu, response status chỉ là một nửa contract. Một request bị từ chối phải để dữ liệu và các hệ thống liên quan ở trạng thái an toàn.

Ví dụ `DELETE /api/orders/42` bị từ chối vì user không phải chủ đơn:

```java
@Test
@WithMockUser(username = "binh", authorities = "ORDER_DELETE")
void anotherOwnerCannotDeleteOrder() throws Exception {
    // Fixture: order 42 thuộc về an.
    mvc.perform(delete("/api/orders/42")
            .with(csrf()))
        .andExpect(status().isForbidden());

    assertThat(orderRepository.findById(42L)).isPresent();
    verifyNoInteractions(orderDeletionGateway);
}
```

Đây là ví dụ integration test; repository phải được seed bằng order có owner `an`, còn gateway mock giúp xác minh lệnh xóa ngoài hệ thống không được gửi. Nếu nghiệp vụ dùng event publisher hoặc queue, kiểm tra collaborator tương ứng.

Các loại side effect nên cân nhắc:

- Bản ghi không được tạo, xóa hoặc cập nhật khi request bị từ chối.
- Không phát domain event, message hoặc webhook.
- Không gọi payment/refund/export gateway.
- Không tăng bộ đếm hoặc ghi audit “thành công” sai.
- Không trả file/download stream trước khi xác minh quyền.

Với test transaction, nhớ rằng assertion trong cùng transaction có thể không phát hiện được một số vấn đề commit/flush. Chọn chiến lược kiểm tra persistence phù hợp với cách ứng dụng ghi dữ liệu.

## 11. Bảng kết hợp assertion theo từng loại ca

| Ca | Status | Body | Header | Security state | Side effect |
|---|---|---|---|---|---|
| Anonymous vào API Basic | `401` | Không có báo cáo | `WWW-Authenticate` Basic | Unauthenticated | Service không gọi |
| User đủ quyền đọc báo cáo | `200` | Đúng report/tenant | JSON content type | Authenticated đúng user/authority | Service được gọi |
| User thiếu quyền | `403` | Không có dữ liệu nhạy cảm | Theo error contract | Authenticated nhưng authority thiếu | Service không gọi |
| JWT hết hạn | `401` | Error không lộ token | Bearer challenge theo config | Không có authenticated principal | Controller/service không chạy |
| Form login thành công | `302` | Thường không có body | `Location` đúng | Authenticated | Session/cookie được tạo |
| POST thiếu CSRF | `403` | Error theo contract | Có thể có cache headers | Principal có thể vẫn authenticated | Export/refund không chạy |
| Tài nguyên sai tenant | `403`/`404` | Không lộ tài nguyên | Theo contract | Authenticated đúng user | Không đọc/ghi vượt tenant |
| Method không hỗ trợ | `405` | Error theo contract | `Allow` | Có thể authenticated | Handler nghiệp vụ không chạy |

Không phải test nào cũng cần cả năm cột. Bảng là gợi ý để không bỏ quên bằng chứng quan trọng khi rủi ro cao. Chọn các assertion tối thiểu nhưng đủ để phân biệt nguyên nhân.

## 12. Tránh assertion mong manh và kết luận sai

**So sánh nguyên văn cả body lỗi** có thể làm test gãy khi message được bản địa hóa hoặc đổi wording. Ưu tiên assert error code/schema và sự vắng mặt của dữ liệu nhạy cảm.

**Hardcode header mặc định** có thể làm test phụ thuộc profile hoặc phiên bản framework. Assert giá trị được quy định trong contract của ứng dụng; với header chỉ xuất hiện qua HTTPS, test phải dùng request secure.

**Chỉ kiểm tra status** không phát hiện body rò rỉ, principal sai, response sai tenant hoặc side effect đã xảy ra.

**Dùng authenticated matcher với mock principal rồi tuyên bố login thành công** là kết luận quá mức. Matcher chứng minh trạng thái authentication trong request test; credentials đã được xác minh thật hay chưa phụ thuộc cách tạo principal.

**Kiểm tra SecurityContext sau khi request kết thúc bằng ThreadLocal** có thể sai vì context được dọn theo lifecycle. Dùng matcher trong request hoặc kiểm tra request tiếp theo với session/cookie thực.

**Dùng cùng một assertion `403` cho mọi nguyên nhân** khiến test không rõ nó đang kiểm tra authorization, CSRF, tenant policy hay business state. Thiết kế fixture sao cho chỉ một điều kiện chủ ý sai, rồi assert thêm trạng thái bảo mật và side effect.

**Khẳng định HSTS trong HTTP test thuần** có thể tạo false failure. HSTS được áp dụng trên HTTPS; test cần request được đánh dấu secure hoặc môi trường HTTPS phù hợp.

**CORS không phải authorization.** Preflight được chấp nhận không có nghĩa user có quyền đọc dữ liệu. Test CORS và test authority phải độc lập.

## 13. Quy trình viết một test bảo mật nhiều chiều

Khi thêm endpoint `GET /api/invoices/{id}`, thực hiện:

1. **Ghi contract:** anonymous nhận gì; owner và authority nào được phép; user sai tenant bị từ chối theo status nào.
2. **Tạo fixture:** hai invoice khác owner/tenant, principal có quyền và principal thiếu quyền.
3. **Chọn danh tính:** dùng `@WithMockUser`/`user()` để kiểm tra authorization; dùng login/credentials thật nếu mục tiêu là authentication.
4. **Assert status:** đúng theo entry point, access-denied handler và contract.
5. **Assert body:** đúng invoice khi cho phép; không có dữ liệu invoice khi bị từ chối.
6. **Assert header:** challenge, content type, cache/security headers hoặc CORS nếu thuộc yêu cầu.
7. **Assert security state:** authenticated principal và authority đúng; anonymous request không có principal được xác thực.
8. **Assert side effect:** truy vấn không chạy khi bị chặn; thao tác ghi không làm đổi dữ liệu.
9. **Kiểm tra cặp đối chứng:** user đủ quyền được phép; user thiếu quyền bị từ chối; thay đúng một biến để giải thích khác biệt.

Tên test có thể mô tả đầy đủ contract:

```text
anonymousRequest_returns401AndNoReport
reportReader_returns200WithExpectedTenantData
authenticatedUserWithoutReportAuthority_returns403
wrongBasicPassword_returns401AndUnauthenticated
forbiddenDelete_doesNotChangeOrder
formLogin_successRedirectsAndPersistsSession
expiredJwt_returns401WithoutCallingService
```

## 14. Bài tập: hoàn thiện assertion cho API thanh toán

Ứng dụng có các endpoint:

- `GET /api/payments/{id}`: user cùng tenant có `PAYMENT_READ` được xem.
- `POST /api/payments/{id}/refund`: user cùng tenant có `PAYMENT_REFUND` được refund khi payment ở trạng thái `SETTLED`; web session bật CSRF.
- `GET /partner/payments`: Bearer JWT cần scope `payments.read`.
- API dùng error response JSON theo schema riêng, có correlation ID trong header.

**Nhiệm vụ:**

1. Viết ca anonymous đọc payment: assert status, challenge header, body không có dữ liệu payment và service không được gọi.
2. Viết ca user đủ quyền: assert status, content type, payment ID, tenant và security principal.
3. Viết ca user đã xác thực thiếu `PAYMENT_READ`: assert `403`, body không lộ số tài khoản, principal vẫn authenticated và service không được gọi.
4. Viết ca refund thiếu CSRF: assert `403` và payment vẫn `SETTLED`; sau đó thêm ca thiếu quyền nhưng có CSRF hợp lệ để chứng minh authorization riêng.
5. Viết ca JWT scope đúng/thiếu: assert status và body; giải thích vì sao `mockJwt()` không chứng minh signature/expiry.
6. Viết ca token hết hạn qua decoder thật: assert `401`, body theo error schema, không có dữ liệu và refund/report service không chạy.
7. Kiểm tra correlation ID được giữ trong response theo contract; không assert một giá trị ngẫu nhiên cố định nếu hệ thống sinh ID mới mỗi request.

**Tiêu chí hoàn thành:** Mỗi test phải trả lời được: status đúng không, body đúng/không lộ gì, header nào thuộc contract, request có principal/authority nào, và hệ thống có thực hiện tác động phụ nào không? Khi kết hợp được những bằng chứng đó, bộ test mới mô tả đầy đủ cách Spring Security bảo vệ một request qua HTTP chứ không chỉ ghi nhận một con số status.
