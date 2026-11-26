# Vì sao mã HTTP thành công chưa đủ chứng minh cấu hình bảo mật đúng

## Mục tiêu học tập

Một test nhận `200 OK` thường tạo cảm giác endpoint đang hoạt động đúng. Nhưng nếu mục tiêu là kiểm chứng bảo mật, status thành công chỉ cho biết request cụ thể đã nhận phản hồi thành công trong cấu hình test đang chạy. Nó chưa chứng minh request đã đi qua đúng security filter chain, đã bị kiểm tra đúng role/authority hay dữ liệu trả về không vượt quá quyền của người gọi.

Sau bài học này, bạn có thể:

- Giải thích vì sao một test nhận `2xx` vẫn có thể bỏ sót lỗi xác thực hoặc phân quyền.
- Nhận diện trường hợp filter chain không được gắn, request matcher sai, nhầm thứ tự nhiều `SecurityFilterChain` hoặc test slice nạp thiếu cấu hình.
- Thiết kế cặp test cho phép và từ chối để chứng minh một chính sách thực sự có hiệu lực.
- Kiểm tra method security qua bean Spring được proxy, response body, headers và tác động dữ liệu.
- Dùng `MockMvc` và `WebTestClient` để xác nhận test thực sự đi qua lớp bảo mật của Servlet hoặc Reactive.
- Tạo negative control để chứng minh test sẽ thất bại nếu quy tắc bảo vệ bị gỡ bỏ hoặc cấu hình sai.

Bài này thuộc module **SPRING_SECURITY_TESTING**, tập trung kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Status thành công chứng minh điều gì?

Giả sử endpoint `GET /api/admin/reports` chỉ dành cho người có `ROLE_ADMIN`. Test sau đây nhận `200 OK`:

~~~java
@Test
@WithMockUser(username = "mai", roles = "ADMIN")
void adminCanReadReports() throws Exception {
    mvc.perform(get("/api/admin/reports"))
        .andExpect(status().isOk());
}
~~~

Test chứng minh rằng trong lần chạy này, người dùng giả lập tên `mai` với authority tương ứng đã nhận status `200` khi gọi đường dẫn đó. Test chưa trả lời các câu hỏi quan trọng:

- Người có `ROLE_USER` có bị từ chối không?
- Người chưa đăng nhập có bị từ chối không?
- `MockMvc` có thực sự chạy filter chain của ứng dụng không?
- Đường dẫn có khớp với `SecurityFilterChain` dự kiến không?
- Có một chain khác với quy tắc rộng hơn được chọn trước không?
- Controller có được bảo vệ ở method security nếu được gọi từ một đường khác không?
- Response có chứa dữ liệu mà người gọi không được phép xem không?

Một endpoint bị cấu hình thành `permitAll()` vẫn trả `200` cho quản trị viên. Một test client không gắn security filter cũng có thể gọi controller và nhận `200`. Vì vậy, **test cho phép là cần thiết nhưng không đủ** để chứng minh một quy tắc từ chối hoạt động.

### 1.1. Mã 2xx không nói lên nguyên nhân bảo mật

~~~mermaid
flowchart TD
    T["Test gửi request"] --> C{"Test client có gắn security chain?"}
    C -->|Không| H["Controller có thể trả 2xx trực tiếp"]
    C -->|Có| F["Security filter / WebFilter chain"]
    F --> M{"Matcher và chain có đúng?"}
    M -->|Sai chain hoặc permitAll| H
    M -->|Đúng| A{"Authentication hợp lệ?"}
    A -->|Không| X["401 / redirect"]
    A -->|Có| Z{"Authorization cho phép?"}
    Z -->|Không| Y["403 / 404 theo policy"]
    Z -->|Có| H
    H --> O["Response 2xx"]
~~~

Nhiều đường đi khác nhau có thể dẫn tới cùng một status thành công. Chỉ nhìn vào `200` không thể phân biệt request được phép vì chính sách đúng hay vì chính sách chưa được áp dụng.

## 2. Những nguyên nhân tạo ra test xanh giả

### 2.1. Filter chain không chạy trong MockMvc

Khi tự dựng `MockMvc` bằng builder, nếu không tích hợp Spring Security, test có thể gọi controller mà bỏ qua các filter cần kiểm chứng.

Ví dụ cách dựng client cần áp dụng security configurer:

~~~java
MockMvc mvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
~~~

Với `@SpringBootTest` và `@AutoConfigureMockMvc` thông thường, Spring Boot tích hợp các filter từ application context. Tuy nhiên, cấu hình test có thể chủ động tắt filter, ví dụ dùng `@AutoConfigureMockMvc(addFilters = false)`. Khi đó, một test nhận `200` không chứng minh filter chain đã bảo vệ request.

Hãy kiểm tra cách client được tạo và cấu hình thực tế trong test context, thay vì chỉ dựa vào tên class test.

### 2.2. Test slice không nạp security configuration mong muốn

`@WebMvcTest` tập trung vào lớp web và chỉ nạp một phần application context. Tùy cấu trúc dự án, security configuration có thể không được nạp tự động hoặc có thể bị thay bởi cấu hình test.

Nếu test slice không chứa `SecurityFilterChain` mà production đang dùng, kết quả không đại diện cho chính sách thật. Có thể import cấu hình cần thiết bằng `@Import(...)` hoặc dùng `@SpringBootTest` khi cần kiểm tra tích hợp rộng hơn.

Điều cần xác minh là **chain và các bean bảo mật nào đang tồn tại trong context của test**. Không mặc định mọi `@WebMvcTest` đều bỏ security hoặc mọi `@WebMvcTest` đều tự nạp đúng cấu hình production.

### 2.3. Request matcher không khớp đường dẫn thực tế

Ví dụ cấu hình:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated())
~~~

Nếu endpoint thật nằm ở `/internal/admin/reports` hoặc ứng dụng dùng context path khác với giả định của test, request có thể không đi vào quy tắc `/api/admin/**`.

Khi matcher không khớp, request rơi xuống quy tắc tiếp theo. Nếu quy tắc cuối là `authenticated()`, bất kỳ user đã đăng nhập nào cũng có thể gọi được endpoint, dù thiết kế yêu cầu admin.

Hãy kiểm tra đúng HTTP method, path, servlet path, context path và các matcher khác nhau trong cấu hình. Test phải gọi chính xác URL production công bố.

### 2.4. Nhiều SecurityFilterChain và thứ tự lựa chọn

Một ứng dụng có thể có nhiều `SecurityFilterChain`, ví dụ một chain cho API, một chain cho form login và một chain cho actuator. Spring chọn chain đầu tiên có matcher phù hợp với request.

Nếu chain rộng như `/**` được đặt trước chain dành cho `/api/admin/**`, request có thể được xử lý bởi chain rộng và không bao giờ đến chain dự kiến.

Cần kiểm tra:

- `@Order` của từng chain.
- `securityMatcher(...)` dùng để chọn chain.
- `requestMatchers(...)` bên trong chain dùng để quyết định quyền.
- Chain nào thực sự áp dụng cho URL và HTTP method của test.

Đừng chỉ nhìn thấy một quy tắc `hasRole("ADMIN")` ở đâu đó trong cấu hình rồi kết luận endpoint được bảo vệ.

### 2.5. Quy tắc permitAll hoặc fallback quá rộng

Một quy tắc như:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN"))
~~~

có thể làm quy tắc admin phía sau không bao giờ được áp dụng, vì matcher rộng đã khớp trước. Thứ tự matcher trong cùng chain có ý nghĩa: quy tắc cụ thể cần đứng trước quy tắc bao phủ rộng.

Test chỉ với admin vẫn nhận `200` và không phát hiện lỗi. Cần có test user thường và anonymous để xác nhận chính sách từ chối.

### 2.6. @WithMockUser tạo sẵn authentication

`@WithMockUser` tạo security context đã xác thực cho test. Nó không kiểm tra username/password, không gọi login endpoint và không xác minh JWT/OIDC token.

Do đó, test:

~~~java
@Test
@WithMockUser(roles = "ADMIN")
void adminCanReadReports() throws Exception {
    mvc.perform(get("/api/admin/reports"))
        .andExpect(status().isOk());
}
~~~

không chứng minh quy trình đăng nhập hoạt động. Nó hữu ích để kiểm tra quyền của một principal đã xác thực. Muốn kiểm tra credential, cần gửi credential qua cơ chế xác thực thật, ví dụ HTTP Basic hoặc form login trong test context.

### 2.7. Method security chưa được bật hoặc không đi qua proxy

Có thể một service có annotation:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Report readSensitiveReport() {
    return repository.loadSensitiveReport();
}
~~~

nhưng cấu hình chưa bật `@EnableMethodSecurity`. Hoặc test tự tạo service bằng `new ReportService(...)`, nên lời gọi không đi qua proxy/interceptor của Spring.

Một test HTTP của controller có thể nhận `200` nếu URL chain chỉ yêu cầu đăng nhập, trong khi method security không hoạt động. Hãy test trực tiếp bean Spring được inject với một principal thiếu quyền và xác minh bị từ chối.

Lưu ý thêm: lời gọi nội bộ qua `this.readSensitiveReport()` trong cùng bean có thể bỏ qua proxy. Test phải mô phỏng đường gọi thực tế cần bảo vệ.

## 3. Cặp test allow/deny là bằng chứng tối thiểu

Để kiểm tra endpoint admin, cần ít nhất ba trường hợp:

1. Admin đã xác thực: được phép.
2. User thường đã xác thực: bị từ chối vì thiếu role.
3. Anonymous: bị từ chối vì chưa xác thực.

Ví dụ cấu hình:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Ví dụ test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AdminEndpointSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "mai", roles = "ADMIN")
    void adminCanReadReport() throws Exception {
        mvc.perform(get("/api/admin/reports"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.reportName").value("monthly"));
    }

    @Test
    @WithMockUser(username = "linh", roles = "USER")
    void regularUserCannotReadReport() throws Exception {
        mvc.perform(get("/api/admin/reports"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousCannotReadReport() throws Exception {
        mvc.perform(get("/api/admin/reports"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Ví dụ giả định endpoint trả JSON có trường `reportName` và HTTP Basic là entry point cho request anonymous. Với form login, anonymous có thể nhận `302 Redirect`; hãy điều chỉnh assertion theo cấu hình ứng dụng.

Nếu xóa quy tắc `hasRole("ADMIN")` và chỉ còn `authenticated()`, test admin vẫn xanh nhưng test user thường sẽ thất bại. Chính ca từ chối này cho thấy bộ test có khả năng phát hiện lỗi mở rộng quyền.

### 3.1. Test không có quyền cần giữ các điều kiện khác hợp lệ

Với request POST khi CSRF đang bật, test user thường phải gửi token CSRF hợp lệ nếu mục tiêu là kiểm tra role:

~~~java
mvc.perform(post("/api/admin/reports/export")
        .with(user("linh").roles("USER"))
        .with(csrf()))
    .andExpect(status().isForbidden());
~~~

Nếu bỏ `csrf()`, `403` có thể đến từ CSRF filter trước khi kiểm tra role. Test sẽ xanh dù quy tắc phân quyền bị xóa.

Tương tự, khi kiểm tra scope JWT, cần phân biệt test dùng `jwt().authorities(...)` (truyền thẳng quyền) với test dùng claim và converter. Không thể dùng test truyền authority trực tiếp để khẳng định converter ánh xạ claim đúng.

## 4. Một test thành công cần kiểm tra đúng endpoint và đúng dữ liệu

Ngay cả khi filter chain đã chạy và admin được phép, status `200` vẫn chưa đủ để chứng minh response an toàn.

Ví dụ endpoint có thể trả cả dữ liệu quản trị lẫn trường nội bộ:

~~~json
{
  "reportName": "monthly",
  "total": 120,
  "internalNotes": "confidential",
  "databaseQuery": "select ..."
}
~~~

Nếu hợp đồng chỉ cho phép trả tên báo cáo và tổng số, test thành công cần xác minh nội dung mong đợi và sự vắng mặt của trường nhạy cảm:

~~~java
mvc.perform(get("/api/admin/reports")
        .with(user("mai").roles("ADMIN")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.reportName").value("monthly"))
    .andExpect(jsonPath("$.total").value(120))
    .andExpect(jsonPath("$.internalNotes").doesNotExist())
    .andExpect(jsonPath("$.databaseQuery").doesNotExist());
~~~

Đây là một phần của security contract: người có quyền được nhận đúng dữ liệu cần thiết, không đồng nghĩa họ được nhận mọi dữ liệu nội bộ.

Tùy endpoint, còn có thể kiểm tra:

- `Content-Type` đúng.
- `Cache-Control` phù hợp với dữ liệu nhạy cảm.
- Cookie và session flags theo chính sách.
- Không có stack trace, token, secret hoặc thông tin debug.
- Response không tiết lộ tài nguyên thuộc tenant khác.

## 5. Kiểm thử side effect để xác nhận hành vi bảo mật hoàn chỉnh

Một endpoint trả `403` vẫn có thể gây tác dụng phụ nếu ứng dụng ghi dữ liệu trước khi kiểm tra quyền hoặc có đường xử lý khác. Với thao tác thay đổi trạng thái, cần kiểm tra dữ liệu sau request.

Ví dụ:

~~~java
@Test
@WithMockUser(username = "linh", authorities = "orders:read")
void readerCannotApproveAndOrderRemainsPending() throws Exception {
    orders.save(Order.pending("ORD-42"));

    mvc.perform(post("/api/orders/ORD-42/approve")
            .with(csrf()))
        .andExpect(status().isForbidden());

    assertThat(orders.findById("ORD-42").orElseThrow().getStatus())
        .isEqualTo(OrderStatus.PENDING_REVIEW);

    verify(orderEventPublisher, never())
        .publish(any(OrderApproved.class));
}
~~~

Ví dụ giả định repository, event publisher và fixture đã được cấu hình trong test. Ngoài trạng thái database, hãy kiểm tra những tác động phù hợp với kiến trúc:

- Không ghi bản ghi nghiệp vụ hoặc lịch sử phê duyệt.
- Không tạo event `OrderApproved` trong outbox.
- Không gửi email xác nhận.
- Không gọi payment hoặc downstream service.
- Không cập nhật quota hoặc số dư.

Một security audit event ghi nhận lần truy cập bị từ chối có thể vẫn được phép. Phân biệt audit event với event nghiệp vụ bị cấm để assertion không loại bỏ hành vi giám sát hợp lệ.

## 6. Reactive: 2xx cũng có thể đến từ test client thiếu WebFilter chain

Trong WebFlux, `WebTestClient` cần được gắn với security WebFilter chain của ứng dụng nếu mục tiêu là kiểm tra bảo mật HTTP.

Ví dụ:

~~~java
@BeforeEach
void setUp() {
    client = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
}
~~~

Nếu chỉ dựng client bằng `bindToController(...)` mà không đưa security filters vào, test có thể gọi handler trực tiếp và nhận `200` dù production yêu cầu xác thực.

Với ứng dụng WebFlux, cặp test nên bao gồm user có role và user không có role:

~~~java
@Test
void adminCanReadAudit() {
    client.mutateWith(mockUser("mai").roles("ADMIN"))
        .get().uri("/api/admin/audit")
        .exchange()
        .expectStatus().isOk();
}

@Test
void regularUserCannotReadAudit() {
    client.mutateWith(mockUser("linh").roles("USER"))
        .get().uri("/api/admin/audit")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Hai test giả định `SecurityWebFilterChain` bảo vệ `/api/admin/**` bằng `hasRole("ADMIN")` và client đã áp dụng `springSecurity()`.

Khi client gọi server ở cổng thật, mock principal trong test process không tự truyền qua mạng. Khi đó, cần gửi credential/token qua HTTP để server tự xác thực.

## 7. Test slice và test context: xác minh cấu hình nào đang chạy

Để tránh test xanh giả, hãy xác định rõ test đang khởi tạo thành phần nào.

| Loại test | Cần kiểm tra |
| --- | --- |
| `@WebMvcTest` | Security configuration có được import không; filter chain nào có mặt; filter có được bật không. |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Có đang dùng chain thực tế của ứng dụng không; có cấu hình nào tắt filters không. |
| MockMvc tự dựng | Đã áp dụng `springSecurity()` chưa. |
| `WebTestClient` gắn context | Đã áp dụng `springSecurity()` và đúng WebFilter chain chưa. |
| `WebTestClient.bindToController(...)` | Có cố ý đưa security config vào client không; nếu không, test chỉ đang kiểm tra handler. |
| Test method security | `@EnableMethodSecurity`/Reactive tương ứng có bật không; đang gọi bean proxy hay object tự tạo. |

Không có một annotation test duy nhất bảo đảm mọi cấu hình bảo mật đều được nạp. Hãy coi test context là một phần của đối tượng cần kiểm chứng.

## 8. Negative control: chứng minh test sẽ đỏ khi quy tắc bị gỡ

Một bộ test có giá trị phải nhạy với thay đổi bảo mật. Cách kiểm tra đơn giản là tạo một **negative control** trong môi trường phát triển hoặc nhánh thử nghiệm:

1. Chạy bộ test với quy tắc `hasRole("ADMIN")` đang bật. Admin được phép, user thường bị từ chối.
2. Tạm thời thay quy tắc bằng `authenticated()` hoặc `permitAll()` trong bản thử nghiệm.
3. Chạy lại test.
4. Xác nhận test user thường hoặc anonymous thất bại.
5. Khôi phục cấu hình đúng và xác nhận bộ test trở lại xanh.

Đây là kỹ thuật kiểm tra độ nhạy của test. Không cần thực hiện thay đổi này trong môi trường production. Nếu test từ chối vẫn xanh sau khi bỏ quy tắc, hãy kiểm tra xem request có đang bị chặn bởi CSRF, sai endpoint, mock setup hoặc filter khác hay không.

Có thể áp dụng nguyên tắc tương tự cho:

- Bỏ `springSecurity()` khỏi test client để xác nhận cấu hình test phát hiện thiếu filter.
- Bỏ `@EnableMethodSecurity` để xem test gọi bean có phát hiện annotation không còn hiệu lực.
- Đổi matcher cụ thể thành matcher rộng để xác nhận test user thường phát hiện quyền bị mở.
- Thay converter scope bằng converter trả authority sai để xác nhận test mapping/integration phát hiện lỗi.

## 9. Ma trận assertion: điều gì phải được chứng minh?

| Nhóm | Ca được phép | Ca bị từ chối |
| --- | --- | --- |
| Authentication | Credential/token hợp lệ tạo principal đúng. | Anonymous, mật khẩu sai hoặc token không hợp lệ bị từ chối. |
| URL authorization | Admin hoặc scope phù hợp gọi được endpoint. | User thiếu role/scope không gọi được. |
| Method security | Principal đủ quyền gọi bean proxy thành công. | Principal thiếu quyền bị `AccessDeniedException` hoặc lỗi Reactive tương ứng. |
| HTTP contract | Status, body, header đúng và không dư dữ liệu. | Status/error body đúng, không rò rỉ thông tin nhạy cảm. |
| Side effect | Có đúng cập nhật/event/downstream theo nghiệp vụ. | Không có tác động nghiệp vụ trái phép. |
| Test wiring | Đúng filter chain/WebFilter chain đang chạy. | Negative control phát hiện khi chain hoặc rule bị gỡ. |

Với JWT/OAuth2/OIDC mock, cần ghi rõ test đang kiểm tra authorization sau khi đã có principal giả lập. Khi cần chứng minh chữ ký JWT, introspection hoặc protocol login, phải bổ sung test đi qua xác thực thực tế.

## 10. Quy trình rà soát một test đang chỉ assert 200

Khi gặp test bảo mật chỉ có `status().isOk()`, hãy rà soát theo trình tự:

1. Xác định chính sách của endpoint: public, authenticated, role, authority hay scope.
2. Xác nhận URL và HTTP method trong test trùng với endpoint thật.
3. Xác nhận filter chain hoặc WebFilter chain mong muốn đã được gắn vào test client.
4. Xác nhận principal mock có đúng role/authority; nếu test xác thực thật thì gửi credential/token qua đúng cơ chế.
5. Thêm ca user thiếu quyền và anonymous nếu endpoint không public.
6. Kiểm tra body, header và dữ liệu nhạy cảm trong response.
7. Với thao tác ghi, kiểm tra database, event/outbox và downstream call.
8. Thử negative control để chắc chắn test thất bại khi quy tắc bảo vệ bị gỡ bỏ.

Không phải endpoint nào cũng cần đủ mọi loại assertion. Một endpoint public không cần test anonymous bị từ chối; thay vào đó cần xác nhận nó không vô tình trả dữ liệu riêng tư. Phạm vi assertion phải theo hợp đồng của endpoint.

## 11. Bài thực hành tổng hợp

Tạo endpoint `GET /api/admin/reports` chỉ dành cho `ROLE_ADMIN` và endpoint `POST /api/orders/{id}/approve` cần authority `orders:approve`.

1. Viết test admin nhận `200` và kiểm tra body chỉ chứa các trường được phép.
2. Viết test user thường nhận `403` và anonymous nhận `401` hoặc redirect theo entry point.
3. Kiểm tra test client đã chạy đúng security filter chain; thử dựng một MockMvc thiếu `springSecurity()` để quan sát khác biệt.
4. Với POST, thêm CSRF token vào test phân quyền để loại trừ nguyên nhân từ CSRF filter.
5. Gọi service qua bean Spring với `@WithMockUser` để xác minh method security.
6. Kiểm tra sau request bị từ chối: trạng thái đơn không đổi, không tạo event duyệt và không gọi dịch vụ thông báo.
7. Nếu dùng WebFlux, tạo cặp test WebTestClient và xác nhận client đã áp dụng `springSecurity()`.
8. Tạm thời nới quy tắc admin trong môi trường thử nghiệm; xác nhận test user thường thất bại rồi khôi phục cấu hình.
9. Ghi rõ mỗi test chứng minh điều gì và phần nào vẫn cần test credential/token thật.

**Tiêu chí hoàn thành:** không chỉ có test cho phép thành công. Bộ test phải phát hiện được endpoint bị mở sai, filter chain bị bỏ qua, method security không hoạt động và response/tác động vượt quyền.

## 12. Ghi nhớ

Status `200` chỉ là một phần của bằng chứng. Nó không cho biết request có đi qua đúng filter chain hay không, matcher có chọn đúng quy tắc không, method security có được thực thi không hoặc response có chứa dữ liệu vượt quyền không.

Một bộ test đáng tin cậy phải có cả ca cho phép và ca từ chối, xác nhận test wiring, kiểm tra response và side effect phù hợp, đồng thời nhạy với việc quy tắc bảo mật bị gỡ bỏ. Với Servlet dùng `MockMvc`, với Reactive dùng `WebTestClient` và security configurer tương ứng; với method security, gọi bean Spring đã được bảo vệ.

Kết luận cần dựa trên bằng chứng rằng **chính sách đã được áp dụng đúng và một thay đổi làm suy yếu chính sách sẽ khiến test thất bại**, chứ không chỉ dựa vào một status thành công.
