# Xác định chính sách bảo mật cần chứng minh trước khi chọn công cụ

> **Chương:** Chiến lược kiểm thử  
> **Phạm vi:** Spring Security Testing — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Bắt đầu từ điều cần bảo vệ

Khi xây dựng kiểm thử bảo mật cho ứng dụng Spring Security, câu hỏi đầu tiên không phải là “dùng `MockMvc` hay `WebTestClient`?”, cũng không phải là “viết `@WithMockUser` ở đâu?”. Câu hỏi đầu tiên là:

**Với một danh tính, một hành động, một tài nguyên và một ngữ cảnh cụ thể, hệ thống phải cho phép hay từ chối điều gì, và bằng chứng nào cho thấy quyết định đó thực sự được thực thi?**

Câu trả lời tạo thành **chính sách bảo mật cần chứng minh** (*security policy under test*). Công cụ kiểm thử chỉ là phương tiện đưa các điều kiện ấy vào hệ thống và quan sát kết quả.

Sau bài này, người học có thể:

- Chuyển yêu cầu bảo mật của một API/web app thành các quy tắc có thể kiểm thử được.
- Phân biệt **xác thực** (*authentication*), **phân quyền** (*authorization*), **kiểm soát tài nguyên** và **bảo vệ yêu cầu HTTP**.
- Xây dựng ma trận kiểm thử gồm trường hợp được phép, bị từ chối và các ranh giới dễ sai.
- Chọn lớp kiểm thử phù hợp giữa unit test, kiểm thử với `MockMvc`/`WebTestClient` và kiểm thử tích hợp thực tế.
- Nhận diện giới hạn của `@WithMockUser`, `jwt()`, `mockJwt()`, `oauth2Login()` và `oidcLogin()`.

## 2. Viết chính sách như một hợp đồng có thể kiểm chứng

Một quy tắc đủ rõ để kiểm thử thường phải xác định được các thành phần sau:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Chủ thể (*subject*) | Ai gửi yêu cầu? Đã được xác thực bằng cách nào? | Khách ẩn danh, người dùng `an`, tài khoản đối tác dùng JWT |
| Hành động (*action*) | Muốn làm gì? | `GET`, `POST`, `DELETE`, gọi phương thức nghiệp vụ |
| Tài nguyên (*resource*) | Tác động đến đối tượng nào? | `/api/reports`, đơn hàng `42` |
| Ngữ cảnh (*context*) | Điều kiện nào ảnh hưởng quyết định? | Quyền trong `GrantedAuthority`, người sở hữu đơn hàng, CSRF token, loại phiên |
| Quyết định (*decision*) | Cho phép hay từ chối? | `ALLOW` / `DENY` |
| Kết quả quan sát (*observable outcome*) | Nhìn vào đâu để kết luận? | Mã HTTP, dữ liệu trả về, bản ghi không bị sửa, không lộ dữ liệu nhạy cảm |

Có thể diễn đạt ngắn gọn:

```text
Quyết định truy cập = Policy(chủ thể, hành động, tài nguyên, ngữ cảnh)

Kiểm thử tốt = dựng đúng đầu vào
              + gọi đúng đường đi có áp dụng bảo mật
              + xác minh quyết định và tác động có thể quan sát
```

Một phát biểu như “người dùng đã đăng nhập được xem báo cáo” còn mơ hồ: mọi người dùng hay chỉ người có quyền đọc báo cáo? Một phát biểu kiểm thử được sẽ là:

> Người dùng đã xác thực nhưng **không có** authority `REPORT_READ` phải bị từ chối khi `GET /api/reports`; phản hồi không chứa nội dung báo cáo. Người dùng có `REPORT_READ` được phép truy cập.

Ở đây, `REPORT_READ` là **authority**, không phải tên vai trò. Nếu chính sách chọn `hasRole("ADMIN")`, Spring Security thường đối chiếu authority `ROLE_ADMIN`; bởi vậy phải ghi rõ chính sách dùng **role**, **authority** hay **OAuth2 scope**, không xem chúng là các chuỗi tương đương.

Một nguyên tắc hữu ích là **từ chối mặc định** (*deny by default*): tuyến, hành động hoặc tài nguyên chưa được định nghĩa quyền truy cập không nên tự nhiên trở thành công khai. Tuy nhiên, phải kiểm tra hành vi thực tế của `SecurityFilterChain`/`SecurityWebFilterChain`, thứ tự matcher và kiểm soát ở tầng phương thức thay vì chỉ dựa vào nguyên tắc trên giấy.

## 3. Tình huống xuyên suốt: ứng dụng quản lý đơn hàng

Giả sử ứng dụng có giao diện web dùng đăng nhập theo phiên và một nhánh tích hợp đối tác xác thực bằng Bearer JWT. Đây là **hai bề mặt truy cập với cơ chế bảo vệ khác nhau**; ví dụ mã Servlet ở phần sau chỉ minh họa nhánh web, còn nhánh JWT cần cấu hình resource server riêng.

Quy ước nghiệp vụ:

- Khách chưa đăng nhập có thể xem danh mục công khai.
- Người dùng đã đăng nhập có thể xem thông tin của **chính mình** và tạo đơn hàng.
- Chỉ người có authority `REPORT_READ` được xem báo cáo.
- Chỉ chủ đơn hàng hoặc người có role `ADMIN` được xóa đơn hàng; phải kiểm tra quyền trên **từng đơn cụ thể**, không chỉ URL.
- Yêu cầu thay đổi trạng thái đi qua phiên/cookie phải có CSRF token hợp lệ theo chính sách của ứng dụng.
- Tài khoản đối tác phải có Bearer JWT hợp lệ và scope `data.read` để đọc dữ liệu tích hợp.

Từ đó xây dựng ma trận hợp đồng bảo mật. Những mã HTTP sau là **kỳ vọng của thiết kế ví dụ**: nhánh web/API sử dụng `401` cho yêu cầu thiếu xác thực, `403` cho yêu cầu đã xác thực nhưng thiếu quyền. Nếu ứng dụng dùng form login, yêu cầu ẩn danh có thể được chuyển hướng `302` đến trang đăng nhập; đó phải là kỳ vọng được ghi rõ trong hợp đồng riêng.

| ID | Điều kiện đầu vào | Yêu cầu | Kết quả cần chứng minh |
|---|---|---|---|
| P01 | Không đăng nhập | `GET /public/products` | Được phép, `200` và danh sách sản phẩm công khai |
| P02 | Không đăng nhập | `GET /api/me` | Bị yêu cầu xác thực, `401` |
| P03 | Người dùng `an` đã xác thực | `GET /api/me` | `200`; dữ liệu thuộc về `an`, không phải tài khoản khác |
| P04 | Đã xác thực, **thiếu** `REPORT_READ` | `GET /api/reports` | `403`; không nhận nội dung báo cáo |
| P05 | Đã xác thực, **có** `REPORT_READ` | `GET /api/reports` | Được phép; trả đúng báo cáo được quyền xem |
| P06 | Đã xác thực, **không có CSRF token**, trên nhánh phiên | `POST /api/orders` | `403`; không tạo đơn mới |
| P07 | Đã xác thực, **có CSRF token hợp lệ**, dữ liệu hợp lệ | `POST /api/orders` | Được phép tạo đơn, ví dụ `201`; chủ đơn là người đang đăng nhập |
| P08 | Chủ thể không sở hữu đơn `42`, không có `ROLE_ADMIN` | `DELETE /api/orders/42`, kèm CSRF hợp lệ | Bị từ chối theo chính sách sở hữu; đơn không bị xóa |
| P09 | Chủ đơn `42` hoặc người có `ROLE_ADMIN`, CSRF hợp lệ | `DELETE /api/orders/42` | Được xóa nếu thỏa các điều kiện nghiệp vụ khác |
| P10 | Không có Bearer JWT | `GET /partner/data` | `401` từ nhánh resource server |
| P11 | JWT hợp lệ nhưng thiếu `SCOPE_data.read` | `GET /partner/data` | `403` |
| P12 | JWT hợp lệ có `SCOPE_data.read` | `GET /partner/data` | Được phép; chỉ trả dữ liệu đối tác được cấp quyền |

Bảng này chưa ràng buộc ta phải viết `@WithMockUser` hay `jwt()`. Nó ràng buộc **hành vi** cần chứng minh. Nhờ vậy, cùng một hợp đồng có thể được kiểm thử trên Servlet với `MockMvc` hoặc Reactive với `WebTestClient`, miễn là chính sách ở hai hệ thống thực sự giống nhau.

### Không chỉ có “được phép” và “bị từ chối”

Với mỗi quy tắc, cần bổ sung trường hợp ở ranh giới:

1. **Chưa xác thực:** không có session, không có Authorization header, hoặc thông tin đăng nhập không hợp lệ.
2. **Đã xác thực nhưng thiếu quyền:** người dùng tồn tại nhưng authority/role/scope không đáp ứng điều kiện.
3. **Đủ quyền:** được truy cập đúng tài nguyên, đúng dữ liệu.
4. **Đúng quyền nhưng sai tài nguyên:** người dùng có quyền thao tác chung nhưng cố truy cập tài nguyên của người khác (ngăn IDOR/BOLA).
5. **Đúng quyền nhưng sai ngữ cảnh:** thiếu CSRF token, dùng sai HTTP method, tài nguyên ở trạng thái không cho thao tác, hoặc phiên hết hạn.
6. **Chênh lệch giữa các tuyến:** đường dẫn tương tự, phương thức HTTP khác, tham số path khác hoặc một tuyến mới chưa có matcher.

Trường hợp từ chối cần kiểm tra cả **không có tác động phụ**. Chỉ thấy `403` chưa đủ nếu hệ thống đã ghi dữ liệu trước khi phản hồi lỗi.

## 4. Tách bốn nhóm điều cần chứng minh

### 4.1. Xác thực: hệ thống biết ai đang gửi yêu cầu?

Xác thực trả lời “chủ thể này là ai?” và “bằng chứng danh tính có hợp lệ không?”. Các tình huống tiêu biểu gồm:

- Thiếu danh tính: phải nhận hành vi thử thách xác thực theo hợp đồng (`401` hoặc chuyển hướng đăng nhập).
- Đăng nhập thành công: `SecurityContext` có principal và authorities mong đợi.
- Thông tin xác thực sai/hết hạn: không được trở thành người dùng hợp lệ.
- Bearer token sai chữ ký, hết hạn, sai issuer hoặc audience: phải bị xử lý bởi tầng xác minh token thật **nếu ứng dụng yêu cầu các ràng buộc này**.

**Giới hạn quan trọng:** `@WithMockUser` và request post-processor `user()` đưa danh tính giả lập vào ngữ cảnh kiểm thử. Chúng rất tốt để kiểm chứng phân quyền, nhưng **không** chứng minh password encoder, login endpoint hoặc cơ chế xác thực ngoài đời đã hoạt động. Tương tự, `jwt()` của `spring-security-test` trên Servlet và `mockJwt()` trên Reactive **không kiểm tra chữ ký JWT thật**. Nếu mục tiêu là kiểm tra xác minh JWT, phải có bài test khác đi qua decoder/validator thực hoặc cấu hình tích hợp tương đương.

### 4.2. Phân quyền: đúng danh tính có được làm việc này không?

Phân quyền trả lời “ai được làm gì với tài nguyên nào?”. Tách ít nhất hai cấp:

- **Cấp yêu cầu HTTP:** `authorizeHttpRequests` (Servlet) hoặc `authorizeExchange` (Reactive) có bảo vệ URL/method theo đúng rule không?
- **Cấp phương thức và đối tượng:** `@PreAuthorize`, `@PostAuthorize` hoặc lớp dịch vụ kiểm soát quyền sở hữu, tenant, thuộc tính bản ghi có đúng không?

Ví dụ, một người có quyền `ORDER_READ` không đương nhiên được đọc **mọi** đơn hàng. Nếu quy tắc yêu cầu cùng chủ sở hữu, test phải dùng ít nhất hai tài nguyên có chủ khác nhau. Việc sửa ID từ `42` sang `43` là ca kiểm thử chính sách quan trọng, dù cả hai yêu cầu cùng là `GET /api/orders/{id}`.

Trong method security, mock principal phải đại diện đúng cách mà mã ứng dụng truy cập danh tính: `Authentication#getName()`, custom principal, JWT subject hoặc claim cụ thể. Không thể khẳng định kiểm chứng thành công nếu bài test sử dụng loại principal khác khiến nhánh kiểm tra thực không chạy.

### 4.3. Bảo vệ HTTP: request hợp lệ về danh tính vẫn có thể nguy hiểm

Một yêu cầu đã xác thực và đủ quyền vẫn có thể bị từ chối vì chính sách HTTP:

- **CSRF:** áp dụng cho các thao tác có khả năng đổi trạng thái trên hệ thống dựa vào credentials tự động gửi kèm như cookie/session; kiểm tra cả token thiếu/sai và token đúng. Spring Security có CSRF protection mặc định trong nhiều cấu hình Servlet. Với API Bearer token thuần stateless, việc vô hiệu hóa CSRF phải là quyết định thiết kế có căn cứ, không phải giả định mặc nhiên.
- **CORS:** origin, method, header nào được trình duyệt phép dùng? Kiểm tra `OPTIONS` preflight khi ứng dụng công bố chính sách CORS. CORS **không thay thế phân quyền máy chủ**.
- **Security headers và vận chuyển:** kiểm tra những header thực sự được yêu cầu, ví dụ `Content-Security-Policy`, `X-Content-Type-Options`; HTTPS/HSTS cần môi trường phù hợp để xác minh. Không áp đặt mọi header làm tiêu chí cho mọi ứng dụng.
- **Session/logout:** phiên sau logout hoặc hết hạn có còn được dùng cho tài nguyên bảo vệ không? Có cần chống session fixation và giới hạn số phiên không?
- **Bảo vệ từ chối:** có trả dữ liệu nhạy cảm trong `401`/`403` hay để request thất bại gây tác dụng phụ không?

**Lưu ý về thứ tự kiểm tra:** với `POST` thiếu CSRF token, bộ lọc CSRF có thể trả `403` trước khi truy cập rule phân quyền. Vì thế, để chứng minh “khách chưa đăng nhập không được tạo đơn”, phải cung cấp CSRF hợp lệ trong ca test dành riêng cho xác thực; còn để chứng minh “thiếu CSRF bị chặn”, phải tạo một chủ thể đã xác thực và không cung cấp CSRF token.

### 4.4. Cấu hình và khoảng trống bao phủ

Một endpoint có thể hoạt động đúng trong controller nhưng bị bỏ ngoài security filter chain do matcher sai. Các tình huống phải rà soát là:

- Thứ tự của các `SecurityFilterChain`/`SecurityWebFilterChain` và rule matcher đặc thù so với matcher rộng.
- Mỗi HTTP method có cùng chính sách hay khác nhau.
- Các endpoint management, actuator, upload/download, WebSocket handshake hoặc tài nguyên tĩnh có thuộc phạm vi bảo vệ nào.
- Cấu hình test có tải đúng filter chain hay đã bỏ bộ lọc để test “dễ xanh”.

Kiểm thử hợp đồng không thể thay thế việc rà soát tổng thể các route thực có. Khi xuất hiện endpoint mới, phải quyết định chính sách của nó và thêm test tương ứng.

## 5. Từ yêu cầu nghiệp vụ thành ca kiểm thử

Một cách thực hành là viết từng quy tắc ở dạng **Given – When – Then – Evidence**:

```text
POLICY P04 — Chỉ người có REPORT_READ được xem báo cáo

Given:
  Principal an đã xác thực
  Authorities = [ORDER_READ]
  Không có REPORT_READ

When:
  GET /api/reports

Then:
  HTTP 403
  Không có dữ liệu báo cáo trong body

Evidence:
  Yêu cầu đi qua Spring Security filter chain thực của ứng dụng
  Controller/repository không tiết lộ dữ liệu trong nhánh bị từ chối
```

Với một quy tắc, nên có **cặp đối chứng**: ca thiếu quyền bị từ chối và ca đủ quyền được phép. Nếu cả hai đều trả `403`, có thể hệ thống đang chặn vì cấu hình khác (ví dụ CSRF, sai route, sai principal) chứ chưa chứng minh được rule phân quyền mong muốn.

Khi chuẩn bị fixture, cố định các giả định ảnh hưởng đến kết quả: principal, authorities, chủ sở hữu bản ghi, trạng thái dữ liệu, HTTP method, CSRF, các claims và nơi cấu hình security được nạp. Test phải thất bại khi rule bị nới lỏng ngoài ý muốn, chẳng hạn thay `hasAuthority("REPORT_READ")` bằng `authenticated()`.

## 6. Chọn tầng kiểm thử sau khi đã có chính sách

| Tầng kiểm thử | Bằng chứng mạnh nhất | Không tự chứng minh được |
|---|---|---|
| Unit test cho policy/authorization service | Logic quyền sở hữu, tenant, role, trạng thái và nhánh điều kiện phức tạp | Matcher, filter chain, HTTP status, CSRF, token decoder |
| Servlet test với `MockMvc` + Spring Security filters | Matcher, request authorization, `401`/`403`, CSRF, xử lý principal, ánh xạ HTTP | Toàn bộ hạ tầng mạng/proxy; xác thực token thật nếu dùng `jwt()` giả lập |
| Reactive test với `WebTestClient` + `springSecurity()` | `SecurityWebFilterChain`, reactive security context, matcher, `mockUser()`/`mockJwt()`, HTTP contract | Token signature thật nếu dùng token giả lập; toàn bộ kiến trúc triển khai |
| Integration test dùng stack thật | Kết nối decoder/provider/cấu hình, hành vi qua nhiều lớp, persistence và side effects | Không tự bao phủ mọi cặp role × resource × endpoint |

Đây không phải thang bậc “test nào cao hơn là luôn tốt hơn”. Chọn tầng dựa trên **lỗi mà từng yêu cầu cần phát hiện**:

- Logic “chủ sở hữu hoặc admin” có nhiều nhánh? Viết unit tests cho rule và vài kiểm thử HTTP để chứng minh rule thực sự được nối vào đường đi của request.
- Muốn chứng minh `GET /api/reports` cần `REPORT_READ`? Gửi request qua Spring Security bằng `MockMvc` hoặc `WebTestClient`.
- Muốn chứng minh JWT hết hạn/sai chữ ký bị chặn? Kiểm thử với decoder/validator thực, dùng token hợp lệ và không hợp lệ được tạo đúng mục tiêu.
- Muốn chứng minh DELETE bị từ chối không xóa bản ghi? Xác minh trạng thái dữ liệu sau request qua integration test có repository/DB phù hợp.

Với `@WebMvcTest` hoặc `@WebFluxTest`, kiểm tra cấu hình security cần thiết đã được đưa vào slice bằng auto-configuration/import thích hợp. Với `@SpringBootTest`, kiểm tra filter chain thật đã được bật và không có cấu hình test lặng lẽ cho phép mọi request. Riêng `@AutoConfigureMockMvc(addFilters = false)` sẽ làm vô hiệu mục tiêu kiểm thử filter-based security.

## 7. Ví dụ Servlet: biến quy tắc thành MockMvc test

Dưới đây là **cấu hình minh họa** cho nhánh HTTP Basic + CSRF của ứng dụng ví dụ. HTTP Basic được chọn để yêu cầu chưa xác thực trả `401`; Spring Security để CSRF protection bật theo mặc định. Các controller trả `200`, `201` tương ứng được giả định đã tồn tại.

```java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
class WebSecurityConfig {

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/products").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.POST, "/api/orders").authenticated()
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Rule `authenticated()` cho `DELETE /api/orders/**` chỉ bảo vệ bước đầu. Kiểm soát chủ sở hữu hoặc admin **phải được thực thi bổ sung** ở service/method security, ví dụ một phương thức được bảo vệ bằng `@PreAuthorize` hoặc qua `AuthorizationManager` có đủ dữ liệu đơn hàng. Nếu chỉ kiểm tra `authenticated()`, P08 chưa được chứng minh.

Để test đường đi HTTP thực sự có bộ lọc, dùng `@SpringBootTest` và `@AutoConfigureMockMvc`. Ví dụ sau bỏ các câu `import` cho gọn, dùng static imports từ `MockMvcRequestBuilders`, `MockMvcResultMatchers`, `SecurityMockMvcRequestPostProcessors` và JUnit 5:

```java
@SpringBootTest
@AutoConfigureMockMvc
class WebSecurityPolicyTest {

    @Autowired
    MockMvc mvc;

    @Test
    void p02_anonymousCannotReadProfile() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "an", authorities = "ORDER_READ")
    void p04_userWithoutReportPermissionIsForbidden() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "an", authorities = "REPORT_READ")
    void p05_userWithReportPermissionMayRead() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk());
    }

    @Test
    void p06_authenticatedPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("an"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"A-1\",\"quantity\":1}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void p07_authenticatedPostWithCsrfMayCreateOrder() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("an"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"A-1\",\"quantity\":1}"))
            .andExpect(status().isCreated());
    }
}
```

Phần `p07` chỉ đạt `201` nếu controller, dữ liệu đầu vào và nghiệp vụ tạo đơn hợp lệ. Trong dự án thật, nên kiểm tra thêm body hoặc bản ghi được tạo và `ownerId` được lấy từ danh tính đã xác thực, không tin vào `ownerId` do client tự gửi. Với `p06`, kiểm tra repository không tăng số đơn để xác nhận yêu cầu bị chặn trước khi ghi dữ liệu.

`@WithMockUser(username = "an", authorities = "REPORT_READ")` thích hợp vì điều cần chứng minh là **quyền**. Khi cần thay đổi danh tính ngay trên từng request hoặc mô phỏng nhiều người trong một test, dùng `.with(user("an").authorities(...))`. Nếu cấu hình sử dụng `hasRole("ADMIN")`, có thể dùng `@WithMockUser(roles = "ADMIN")`; khi đó authority hiệu dụng là `ROLE_ADMIN`.

### JWT/OAuth2/OIDC: chỉ giả lập những phần cần thiết

Với nhánh resource server riêng đã cấu hình yêu cầu `SCOPE_data.read`, `spring-security-test` cung cấp một đường đi tiện lợi trên Servlet:

```java
mvc.perform(get("/partner/data")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_data.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/partner/data")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_data.write"))))
    .andExpect(status().isForbidden());
```

Hai ca này chứng minh **quy tắc scope** khi request đi qua đúng nhánh security của ứng dụng; chúng **không** chứng minh JWT đã được xác thực chữ ký, hạn dùng, issuer hay audience. Với OAuth2 login có thể dùng `oauth2Login()`, với OpenID Connect login dùng `oidcLogin()` để cung cấp authentication/principal giả lập và claims phục vụ kiểm thử phân quyền. Kiểm thử login redirect, OAuth2 authorization code flow, OIDC discovery hoặc validator token thực phải được thiết kế riêng nếu thuộc chính sách.

Khi dùng JWT, cần ghi rõ ánh xạ giữa scope và authority: Spring Security resource server thường chuyển scope `data.read` thành authority `SCOPE_data.read`, nhưng ứng dụng có thể tùy chỉnh converter. Test phải phản ánh đúng converter được cấu hình.

## 8. Ví dụ Reactive: cùng hợp đồng trên WebTestClient

Ứng dụng WebFlux dùng `SecurityWebFilterChain` và security context phản ứng. Nếu bind `WebTestClient` vào application context để kiểm tra chuỗi filter tại chỗ, phải áp dụng cấu hình Spring Security cho test client. Ví dụ giả định ứng dụng Reactive có tuyến `GET /api/reports` bảo vệ bằng `REPORT_READ`:

```java
@SpringBootTest(properties = "spring.main.web-application-type=reactive")
class ReactiveSecurityPolicyTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void p04_userWithoutReportPermissionIsForbidden() {
        client.mutateWith(mockUser("an")
                .authorities(new SimpleGrantedAuthority("ORDER_READ")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void p05_userWithReportPermissionMayRead() {
        client.mutateWith(mockUser("an")
                .authorities(new SimpleGrantedAuthority("REPORT_READ")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk();
    }
}
```

Các hàm `springSecurity()`, `mockUser()` và `mockJwt()` ở ngữ cảnh này thuộc `SecurityMockServerConfigurers` và `SecurityMockServerRequestPostProcessors` của `spring-security-test`, khác loại request post-processor dùng cho Servlet. Với yêu cầu thay đổi trạng thái trên ứng dụng Reactive có CSRF, sử dụng `mutateWith(csrf())` theo API Reactive. Với resource server Reactive, dùng `mutateWith(mockJwt().authorities(...))` để test rule scope.

Nếu `WebTestClient` thực sự gửi HTTP đến **máy chủ đang chạy qua mạng**, các mock request post-processor chỉ hoạt động theo cơ chế kiểm thử mock exchange và không thể được coi là xác thực đã đi qua giao thức HTTP thật. Để kiểm thử đăng nhập, JWT decoder hay hành vi qua mạng, hãy gửi credentials/token thực đến server và kiểm tra kết quả.

## 9. Thiết kế assertions có sức phát hiện lỗi

Với một hợp đồng bảo mật, xác minh theo thứ tự ưu tiên:

1. **Quyết định truy cập:** status/redirect/challenge có khớp hợp đồng không? Ví dụ `401` cho API thiếu xác thực, `403` cho user thiếu quyền.
2. **Không lộ thông tin:** response bị từ chối không chứa trường nhạy cảm, chi tiết đơn hàng hoặc dữ liệu báo cáo.
3. **Không đổi trạng thái:** thao tác bị từ chối không ghi/xóa dữ liệu, không phát sự kiện nghiệp vụ hoặc gọi dịch vụ ngoài nếu đó là ràng buộc cần bảo đảm.
4. **Kết quả được phép là đúng:** không chỉ `2xx`; đúng principal, đúng bản ghi, đúng tenant, đúng quyền hạn và đúng dữ liệu trả về.
5. **Đường thực thi bảo mật:** test phải chạy qua đúng filter chain và, nếu liên quan, method security; không dùng stub hoặc config vô tình bỏ qua policy.

Ví dụ P08/P09 nên có ít nhất hai đơn cùng trạng thái nhưng khác `ownerId`. Đăng nhập với cùng người dùng, thử xóa đơn của mình và đơn của người khác. Kết quả khác nhau mới là bằng chứng có ý nghĩa về kiểm soát quyền sở hữu.

Không nên gắn cứng mã `403` cho mọi tình huống từ chối: một ứng dụng có thể cố ý trả `404` để không tiết lộ sự tồn tại tài nguyên, hoặc `302` khi dùng form login. Điều quan trọng là **chính sách đã định nghĩa hành vi nào** và hệ thống thực thi nhất quán hay không.

## 10. Những cách viết test cho cảm giác an toàn giả

| Cách làm dễ mắc | Vì sao chưa chứng minh chính sách | Cách cải thiện |
|---|---|---|
| Chỉ kiểm tra user admin nhận `200` | Mọi người dùng khác có thể cũng được phép | Thêm ca authenticated thiếu quyền và anonymous |
| Dùng `@WithMockUser` để “chứng minh login/JWT hợp lệ” | Authentication đã được giả lập | Test login/decoder với dữ liệu xác thực thật trong tầng tích hợp |
| Chỉ kiểm tra `403` khi thiếu CSRF | Có thể chứng minh CSRF, chưa chứng minh rule role | Bổ sung CSRF hợp lệ trong ca test phân quyền |
| Chỉ kiểm tra URL, bỏ qua owner/tenant | Dễ bỏ sót IDOR/BOLA | Tạo tài nguyên khác chủ và kiểm tra không truy cập được |
| Dùng `addFilters = false` hoặc mock bỏ qua security | Request không đi qua hàng rào cần kiểm tra | Nạp và giữ security filter chain trong test |
| Chỉ assert status, không assert dữ liệu/side effect | Response có thể rò rỉ hoặc hành động vẫn xảy ra | Kiểm tra body, repository và sự kiện khi cần |
| Gộp mọi endpoint vào `authenticated()` | Quyền chi tiết mất tác dụng | Ma trận hóa từng hành động và quyền tương ứng |
| Dùng `roles = "ADMIN"` khi policy đòi authority `ADMIN` | `ROLE_ADMIN` và `ADMIN` khác nhau | Dùng đúng role/authority/scope theo hợp đồng |

Một test hữu ích phải có khả năng **đỏ** khi một rào chắn an ninh cụ thể bị gỡ. Hãy tự hỏi: “Nếu nhà phát triển xóa `hasAuthority("REPORT_READ")` khỏi rule, test nào sẽ thất bại?” Nếu không có câu trả lời rõ ràng, độ bao phủ của chính sách đó vẫn thiếu.

## 11. Quy trình áp dụng cho một endpoint mới

Khi thêm `PATCH /api/orders/{id}/address`, không cần chọn framework kiểm thử ngay. Trước hết:

1. **Liệt kê tài sản và rủi ro:** địa chỉ giao hàng có chứa dữ liệu cá nhân; người dùng có thể cố đổi địa chỉ của đơn người khác.
2. **Ghi chủ thể và quyền:** người dùng đã xác thực; chỉ chủ đơn hoặc bộ phận hỗ trợ có quyền rõ ràng mới được cập nhật; đơn đã giao không được đổi địa chỉ.
3. **Chốt điều kiện HTTP:** dùng PATCH; nếu phiên cookie thì yêu cầu CSRF hợp lệ; nếu API Bearer thì áp dụng yêu cầu token và scope đã thiết kế.
4. **Định nghĩa kết quả:** chủ đơn đang xử lý được cập nhật; người khác bị từ chối và dữ liệu giữ nguyên; thiếu danh tính bị challenge; đơn đã giao không cập nhật dù người dùng là chủ.
5. **Chọn tầng kiểm thử:** unit test cho rule “chủ sở hữu + trạng thái đơn”; `MockMvc`/`WebTestClient` cho xác thực, phân quyền, CSRF và HTTP response; integration test xác minh dữ liệu không bị sửa.
6. **Ghi ca kiểm thử vào ma trận:** mỗi kết hợp có ý nghĩa của danh tính, quyền, chủ sở hữu, trạng thái đơn và CSRF đều có quyết định mong đợi.

Cách làm này giúp test bám vào yêu cầu nghiệp vụ, kể cả khi dự án đổi từ `MockMvc` sang `WebTestClient` hoặc từ session sang JWT.

## 12. Tự kiểm tra hiểu biết

**Bài tập:** Một endpoint `GET /api/invoices/{id}` yêu cầu người dùng đã đăng nhập và chỉ được xem hóa đơn thuộc tài khoản của họ; quản trị viên có thể xem tất cả. Hãy viết tối thiểu năm ca kiểm thử mà mỗi ca có *Given – When – Then*:

- Khách ẩn danh truy cập hóa đơn.
- Chủ hóa đơn truy cập hóa đơn của mình.
- Người dùng khác truy cập hóa đơn đó.
- Người dùng có `ROLE_ADMIN` truy cập hóa đơn của bất kỳ tài khoản nào.
- Người dùng có `ROLE_USER` nhưng giả mạo `accountId` ở URL/query/body.

Mỗi ca phải nêu kết quả HTTP theo hợp đồng hệ thống và, đối với các ca bị từ chối, khẳng định không lộ dữ liệu hóa đơn. Sau đó xác định test nào có thể dùng `@WithMockUser`/`mockUser()` và test nào cần môi trường xác thực thực để chứng minh token/session hợp lệ.

**Tiêu chí hoàn thành:** Trước khi viết bất kỳ dòng `MockMvc` hoặc `WebTestClient` nào, bạn có thể giải thích chính xác **ai**, **làm gì**, **với tài nguyên nào**, **trong điều kiện nào**, **được phép hay bị từ chối**, và **sẽ quan sát điều gì**. Khi câu trả lời rõ ràng, việc chọn `spring-security-test` và cách tạo authentication giả lập mới trở thành quyết định kỹ thuật có căn cứ.
