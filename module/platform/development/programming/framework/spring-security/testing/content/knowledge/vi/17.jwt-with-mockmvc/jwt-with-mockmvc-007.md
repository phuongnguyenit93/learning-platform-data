# Kiểm tra claim nghiệp vụ như `tenantId` hoặc `userId`

Trong chương **JWT với MockMvc** của **SPRING_SECURITY_TESTING**, mục tiêu là kiểm chứng ứng dụng Servlet dùng Spring Security có thực sự cho phép hoặc từ chối yêu cầu HTTP theo danh tính và quyền của người gọi. Ngoài `sub`, `scope` hay `roles`, JWT thường mang claim riêng của nghiệp vụ, chẳng hạn `tenantId` (đơn vị thuê/khách hàng) và `userId` (người dùng nội bộ). Một endpoint trả dữ liệu đúng cho người đã đăng nhập vẫn có thể sai nghiêm trọng nếu chấp nhận dữ liệu thuộc tenant hoặc người dùng khác.

Bài này trình bày cách dựng JWT giả lập bằng **`spring-security-test` và `MockMvc`**, cách gắn kiểm tra claim vào một chính sách phân quyền thực tế, cách viết test hai chiều **được phép/bị từ chối**, và giới hạn giữa kiểm tra phân quyền với kiểm tra chữ ký, thời hạn hay nguồn phát hành token.

## 1. Phân biệt xác thực, quyền kỹ thuật và quyền nghiệp vụ

Xét API:

- `GET /api/tenants/{tenantId}/reports`: chỉ thành viên của tenant tương ứng mới được đọc báo cáo.
- `GET /api/users/{userId}/profile`: chỉ người dùng sở hữu hồ sơ tương ứng mới được đọc.

JWT sau khi được hệ thống tin cậy có thể chứa payload minh họa:

```json
{
  "sub": "login-42",
  "scope": "reports.read",
  "tenantId": "tenant-a",
  "userId": "user-42"
}
```

Ý nghĩa các lớp kiểm tra khác nhau:

| Lớp | Câu hỏi cần trả lời | Ví dụ kết quả |
| --- | --- | --- |
| Xác thực | Yêu cầu có danh tính được xác thực không? | Không có Bearer token → thường `401 Unauthorized` trong cấu hình resource server |
| Quyền kỹ thuật | Danh tính có authority/scope cần thiết không? | Thiếu `SCOPE_reports.read` → `403 Forbidden` |
| Quyền theo tenant | Claim `tenantId` có khớp tenant đang truy cập không? | JWT `tenant-a`, URL `tenant-b` → `403 Forbidden` |
| Quyền theo người dùng | Claim `userId` có khớp chủ thể của tài nguyên không? | JWT `user-42`, URL `user-99` → `403 Forbidden` |
| Giới hạn dữ liệu | Truy vấn thực sự chỉ lấy dữ liệu của tenant/người dùng đã được phép không? | Tìm tài liệu theo **cả** `tenantId` và `documentId` |

**Một request đã xác thực chưa đồng nghĩa đã được phép xem mọi tài nguyên.** Kiểm thử chỉ dùng `@WithMockUser` hoặc chỉ khẳng định HTTP `200` cho một người dùng đăng nhập sẽ không bắt được lỗi vượt ranh giới tenant. Đồng thời, không mặc định `sub` tương đương `userId`: đó là hai claim riêng, trừ khi hợp đồng token của hệ thống quy định chúng giống nhau.

Trong ví dụ dưới đây, `tenantId` và `userId` được định nghĩa là **chuỗi không rỗng, phân biệt chữ hoa/chữ thường, phải khớp chính xác** với giá trị trên đường dẫn. Hệ thống thật có thể dùng UUID, số nguyên hoặc quan hệ thành viên nhiều tenant; khi đó cần chuyển đổi và kiểm tra theo hợp đồng thực tế, thay vì ép quy tắc ví dụ này cho mọi dự án.

## 2. `jwt()` trong MockMvc kiểm tra điều gì?

Với dependency kiểm thử `spring-security-test`, cú pháp:

```java
mockMvc.perform(get("/api/tenants/{tenantId}/reports", "tenant-a")
        .with(jwt().jwt(builder -> builder
                .claim("tenantId", "tenant-a")
                .claim("userId", "user-42"))))
    .andExpect(status().isOk());
```

`jwt()` là `SecurityMockMvcRequestPostProcessors.jwt()`. Nó dựng một đối tượng `Jwt` và cung cấp một `JwtAuthenticationToken` trong ngữ cảnh bảo mật của request test. Nhờ đó, ứng dụng có thể chạy các rule như `authorizeHttpRequests`, `@PreAuthorize` và logic đọc `Authentication`/`Jwt` với claim đã chỉ định.

Điều kiện để kết quả có ý nghĩa:

1. `MockMvc` phải gắn với Spring Security filter chain. Với Spring Boot, `@SpringBootTest` + `@AutoConfigureMockMvc` là một lựa chọn; với `MockMvcBuilders` dựng thủ công, cần áp dụng `springSecurity()` và cấu hình context phù hợp.
2. Nếu kiểm tra `@PreAuthorize`, ứng dụng phải bật method security (chẳng hạn `@EnableMethodSecurity`) và gọi controller/service qua Spring proxy.
3. Test phải đi qua endpoint thực và assertion cả **status** lẫn dữ liệu/hiệu ứng quan trọng khi cần; kiểm tra thuần method sẽ không xác minh hành vi HTTP.

**Giới hạn quan trọng:** `.with(jwt())` không gửi Bearer JWT được mã hóa/đã ký để pipeline xác thực giải mã. Nó không tự xác minh signature, `iss`, `aud`, `exp`, `nbf`, JWK, `JwtDecoder` hoặc ánh xạ claim của hệ thống phát hành token. Test có thể chủ động cung cấp một claim mà token thực tế không bao giờ được cấp. Để kiểm thử đường đi Bearer token, gửi header `Authorization: Bearer ...` và kiểm soát hoặc tích hợp `JwtDecoder`; để kiểm chứng chữ ký/issuer/audience phải chạy kiểm thử decoder và cấu hình xác thực phù hợp.

## 3. Một chính sách phân quyền mẫu có thể kiểm thử

Để làm rõ hành vi mong đợi, giả sử ứng dụng Spring Security Servlet có cấu hình resource server JWT và method security:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> {}));
        return http.build();
    }
}
```

Cấu hình ví dụ giả định ứng dụng đã cung cấp `JwtDecoder` hoặc các thuộc tính cần thiết để resource server tạo bean decoder. Nếu test context không có decoder, phải cấu hình bean/phương án test tương ứng để khởi động; `.with(jwt())` không thay thế yêu cầu khởi tạo filter chain.

**Đưa quyết định phân quyền vào một thành phần riêng:** đọc claim dưới dạng `Object` và chỉ chấp nhận chuỗi đúng kiểu, không rỗng. Cách này làm rõ trường hợp token thiếu claim hoặc chứa kiểu dữ liệu bất thường.

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("claimGuard")
class ClaimGuard {

    public boolean hasTenant(Authentication authentication, String expectedTenantId) {
        return matchesClaim(authentication, "tenantId", expectedTenantId);
    }

    public boolean isUser(Authentication authentication, String expectedUserId) {
        return matchesClaim(authentication, "userId", expectedUserId);
    }

    private boolean matchesClaim(
            Authentication authentication, String claimName, String expected) {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }
        Object actual = jwtAuth.getToken().getClaims().get(claimName);
        return actual instanceof String value
                && !value.isBlank()
                && expected != null
                && !expected.isBlank()
                && value.equals(expected);
    }
}
```

Ví dụ controller áp dụng hai chính sách này:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ResourceController {

    @GetMapping("/api/tenants/{tenantId}/reports")
    @PreAuthorize("@claimGuard.hasTenant(authentication, #tenantId)")
    public String report(@P("tenantId") @PathVariable String tenantId) {
        return "tenant:" + tenantId;
    }

    @GetMapping("/api/users/{userId}/profile")
    @PreAuthorize("@claimGuard.isUser(authentication, #userId)")
    public String profile(@P("userId") @PathVariable String userId) {
        return "user:" + userId;
    }
}
```

`@P("tenantId")` và `@P("userId")` giúp Spring Security lấy tên tham số trong biểu thức SpEL `#tenantId`, `#userId` mà không phụ thuộc hoàn toàn vào thông tin tên tham số do compiler tạo ra. Trong ứng dụng thực tế, các method controller thường gọi service/repository thay vì trả chuỗi minh họa.

Hai điểm cần giữ đúng:

- Claim `tenantId` phải được kiểm tra tại **ranh giới quyền truy cập**; không chấp nhận một header như `X-Tenant-Id` hoặc query parameter do client tự gửi để thay thế danh tính tenant đã được xác minh, trừ khi có cơ chế ủy quyền riêng.
- Nếu endpoint là `/tenants/{tenantId}/documents/{documentId}`, sau khi xác nhận tenant trên URL khớp JWT, service vẫn phải truy vấn tài liệu theo cả `tenantId` và `documentId`. Việc kiểm tra chỉ URL mà bỏ qua tenant của bản ghi thật có thể gây lộ dữ liệu giữa các tenant.

## 4. Viết kiểm thử MockMvc cho claim nghiệp vụ

Bên dưới là bộ kiểm thử JUnit 5 dùng Spring Boot, `MockMvc` và `jwt()`. Các import tĩnh và đoạn test được viết theo Spring Security Servlet. Ví dụ giả định `ResourceController`, `ClaimGuard` và `SecurityConfig` ở trên đã nằm trong component scan của ứng dụng và test context khởi động thành công.

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BusinessClaimAuthorizationTest {

    private static final String REPORT_URL = "/api/tenants/{tenantId}/reports";
    private static final String PROFILE_URL = "/api/users/{userId}/profile";

    @Autowired
    MockMvc mockMvc;

    @Test
    void tenantTrungKhop_duocDocBaoCao() throws Exception {
        mockMvc.perform(get(REPORT_URL, "tenant-a")
                .with(jwt().jwt(token -> token
                        .claim("tenantId", "tenant-a")
                        .claim("userId", "user-42"))))
            .andExpect(status().isOk())
            .andExpect(content().string("tenant:tenant-a"));
    }

    @Test
    void tenantKhac_biCamTruyCap() throws Exception {
        mockMvc.perform(get(REPORT_URL, "tenant-b")
                .with(jwt().jwt(token -> token
                        .claim("tenantId", "tenant-a"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void thieuTenantId_biCamTruyCap() throws Exception {
        mockMvc.perform(get(REPORT_URL, "tenant-a")
                .with(jwt()))
            .andExpect(status().isForbidden());
    }

    @Test
    void tenantIdRong_biCamTruyCap() throws Exception {
        mockMvc.perform(get(REPORT_URL, "tenant-a")
                .with(jwt().jwt(token -> token.claim("tenantId", ""))))
            .andExpect(status().isForbidden());
    }

    @Test
    void tenantIdSaiKieu_biCamTruyCap() throws Exception {
        mockMvc.perform(get(REPORT_URL, "tenant-a")
                .with(jwt().jwt(token -> token.claim("tenantId", 123))))
            .andExpect(status().isForbidden());
    }

    @Test
    void userIdTrungKhop_duocDocHoSo() throws Exception {
        mockMvc.perform(get(PROFILE_URL, "user-42")
                .with(jwt().jwt(token -> token
                        .subject("login-identifier")
                        .claim("userId", "user-42"))))
            .andExpect(status().isOk())
            .andExpect(content().string("user:user-42"));
    }

    @Test
    void userIdKhac_biCamTruyCap() throws Exception {
        mockMvc.perform(get(PROFILE_URL, "user-99")
                .with(jwt().jwt(token -> token.claim("userId", "user-42"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void thieuUserId_duCoSub_vanBiCam() throws Exception {
        mockMvc.perform(get(PROFILE_URL, "user-42")
                .with(jwt().jwt(token -> token.subject("user-42"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void khongDangNhap_biYeuCauXacThuc() throws Exception {
        mockMvc.perform(get(REPORT_URL, "tenant-a"))
            .andExpect(status().isUnauthorized());
    }
}
```

Kiểm thử cuối cùng kỳ vọng `401` theo `SecurityConfig` resource server trong ví dụ. Nếu ứng dụng thực tế có nhiều `SecurityFilterChain`, form login, entry point tùy chỉnh, hoặc xử lý exception khác, status có thể khác và phải dựa trên hợp đồng HTTP của ứng dụng. Đối với các request **đã xác thực** nhưng claim không đạt chính sách ở trên, mặc định `@PreAuthorize` từ chối bằng `403`.

Một số điều cần nhìn kỹ trong test:

- `tenantTrungKhop_duocDocBaoCao` chứng minh claim đúng cho phép đi qua cả filter chain và method security để tới controller.
- `tenantKhac_biCamTruyCap` kiểm chứng đúng nguy cơ vượt tenant, kể cả khi JWT giả lập là một người dùng hợp lệ.
- `thieuTenantId_biCamTruyCap` cho thấy không được dùng trạng thái "đã xác thực" để mặc định chấp nhận claim thiếu.
- `tenantIdSaiKieu_biCamTruyCap` kiểm tra việc từ chối dữ liệu không đúng hợp đồng trước khi so sánh, thay vì dựa vào phép ép kiểu ngầm.
- `thieuUserId_duCoSub_vanBiCam` đảm bảo mã nguồn không tự động thay `userId` bằng `sub`. Nếu nghiệp vụ chủ động quy định `userId = sub`, cần sửa chính sách và test tương ứng.

## 5. Bảng kịch bản tối thiểu để tránh bỏ sót nhánh

Với chính sách mẫu ở trên, ta có ma trận kiểm thử:

| Request | Claim JWT | Kỳ vọng |
| --- | --- | --- |
| `GET /api/tenants/tenant-a/reports` | `tenantId = tenant-a` | `200` |
| `GET /api/tenants/tenant-b/reports` | `tenantId = tenant-a` | `403` |
| `GET /api/tenants/tenant-a/reports` | Không có `tenantId` | `403` |
| `GET /api/tenants/tenant-a/reports` | `tenantId = ""` | `403` |
| `GET /api/tenants/tenant-a/reports` | `tenantId = 123` (số) | `403` |
| `GET /api/users/user-42/profile` | `userId = user-42` | `200` |
| `GET /api/users/user-99/profile` | `userId = user-42` | `403` |
| `GET /api/users/user-42/profile` | Chỉ có `sub = user-42` | `403` theo chính sách mẫu |
| `GET /api/tenants/tenant-a/reports` | Không có xác thực | `401` theo resource server mẫu |

Trong project sử dụng object ID dạng UUID hoặc người dùng được cấp quyền vào **nhiều tenant**, cần thay test "khớp chuỗi" bằng các tình huống tương ứng. Ví dụ claim `tenantIds` là danh sách thì phải phân biệt **có phần tử khớp**, **danh sách rỗng**, **phần tử khác**, **claim sai kiểu**, và **claim thiếu**. Không nên tự coi claim chứa một danh sách hay chuỗi phân cách dấu phẩy là hợp lệ nếu nhà phát hành token chưa quy định.

## 6. Kết hợp claim với authority/scope

Một endpoint thực tế thường yêu cầu **đúng tenant và đúng quyền**, chẳng hạn quyền đọc báo cáo. Có thể thêm điều kiện:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_reports.read') "
    + "and @claimGuard.hasTenant(authentication, #tenantId)"
)
```

Khi đó, test cần bao phủ ít nhất hai chiều: authority cho phép nhưng sai tenant; đúng tenant nhưng thiếu authority. Với `jwt()`, có thể thiết lập authority rõ ràng:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

mockMvc.perform(get("/api/tenants/{tenantId}/reports", "tenant-b")
        .with(jwt()
            .jwt(token -> token.claim("tenantId", "tenant-a"))
            .authorities(new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isForbidden());
```

Đây là trường hợp **có scope nhưng sai tenant** và vẫn phải `403`. Tương tự, với đúng `tenantId` nhưng không có `SCOPE_reports.read` thì phải `403` theo biểu thức mới.

**Lưu ý về authority:** dùng `.authorities(...)` là đặt trực tiếp authorities trong `JwtAuthenticationToken` giả lập. Nó không chứng minh bộ chuyển đổi `scope`, `scp`, `roles` thành `GrantedAuthority` của ứng dụng đang hoạt động đúng. Nếu production dùng `JwtAuthenticationConverter` tùy chỉnh, hãy có test riêng cho converter hoặc test đi qua đường xử lý Bearer token và converter thực tế.

## 7. Kiểm chứng toàn bộ đường xử lý JWT khi cần

Nhìn vào mục tiêu test trước khi chọn công cụ:

| Mục tiêu | Công cụ/chiến lược phù hợp |
| --- | --- |
| Rule `@PreAuthorize` đọc `tenantId`/`userId` đúng hay không | `MockMvc` + `.with(jwt())` + controller/service có Spring Security |
| Request không có danh tính bị chặn hay không | `MockMvc` không gắn `jwt()`, chạy filter chain thực |
| Request có Bearer token được giải mã và chuyển thành `Authentication` ra sao | Header `Authorization: Bearer ...`, `JwtDecoder` test double hoặc hệ thống kiểm thử |
| JWT bị sửa chữ ký, sai `iss`/`aud` hoặc hết hạn có bị từ chối | Kiểm thử decoder/cấu hình xác thực thật, token có các đặc điểm tương ứng |
| Claim trong token được ánh xạ sang authorities đúng không | Test `JwtAuthenticationConverter` hoặc kiểm thử request qua converter thật |
| Dữ liệu thật có bị truy xuất chéo tenant không | Integration test controller → service → repository với dữ liệu của ít nhất hai tenant |

Chẳng hạn, muốn chứng minh header Bearer đi qua cơ chế xác thực, test sẽ có hình thức:

```java
mockMvc.perform(get("/api/tenants/{tenantId}/reports", "tenant-a")
        .header("Authorization", "Bearer test-token"))
    .andExpect(status().isOk());
```

Để assertion này đúng, phải cấu hình `JwtDecoder` của test cho phép giải mã `test-token` thành `Jwt` có `tenantId = tenant-a` (hoặc dùng một token hợp lệ với cấu hình issuer/JWK thực tế). **Không gắn thêm `.with(jwt())` vào test đó**, vì nó sẽ đưa xác thực giả trực tiếp vào request và làm khó xác định đường Bearer token thực sự được thực thi. Nếu chỉ mock `JwtDecoder.decode(...)`, test xác minh cách filter chain sử dụng kết quả decoder; nó vẫn chưa chứng minh việc kiểm tra chữ ký bằng khóa thật.

## 8. Những lỗi thường gặp khi kiểm thử claim

**Dùng `@WithMockUser` để kiểm thử `Jwt` claim.** `@WithMockUser` tạo authentication giả kiểu username/password cho nhiều ca Spring Security, nhưng không cung cấp `JwtAuthenticationToken` với claim nghiệp vụ. Nếu code yêu cầu `JwtAuthenticationToken`, hãy dùng `jwt()` hoặc tạo đúng authentication của bài test.

**Dùng claim đúng nhưng không kiểm tra nhánh từ chối.** Một test `200` không thể chứng minh cơ chế cô lập tenant. Cần ít nhất một test từ tenant khác và một test claim thiếu; thêm test sai kiểu nếu policy dựa trên dữ liệu token chưa chuẩn hóa.

**Chỉ test service với một chuỗi tenantId đã truyền tay.** Khi đó chưa xác minh controller/filter chain có lấy đúng claim từ Spring Security hay không. Cần kết hợp test HTTP với test chính sách hoặc service khi logic phức tạp.

**Đồng nhất claim nghiệp vụ với dữ liệu client tự khai.** `tenantId` trong body, path hay header có thể được gửi tùy ý. Chỉ sau khi token được xác thực và policy so khớp với tài nguyên phù hợp mới có cơ sở cho phép truy cập.

**Từ chối đúng status nhưng vẫn có side effect.** Với lệnh ghi như `POST /api/tenants/{tenantId}/payments`, ngoài `403` còn nên xác nhận repository/service không ghi bản ghi, không phát sự kiện và không gọi hệ thống ngoài. Nếu CSRF được bật, cần cấp CSRF hợp lệ trong test để không nhầm lỗi CSRF với lỗi claim, ví dụ `.with(csrf())` từ `spring-security-test`.

**Tưởng rằng `jwt()` kiểm tra token bị giả mạo.** Đây là công cụ mô phỏng danh tính sau xác thực, không phải bộ xác minh mật mã. Cần thêm kiểm thử decoder/JWK/issuer/audience/expiry theo cấu hình phát hành token thực.

**Chỉ kiểm tra tenantId trên URL.** Với API đọc theo `documentId` hoặc `reportId`, cần áp ràng buộc tenant cả trong truy vấn dữ liệu, ví dụ `findByTenantIdAndId(tenantId, documentId)`. Việc trả `404` thay cho `403` để hạn chế lộ sự tồn tại tài nguyên là quyết định hợp đồng API; test phải phản ánh chính sách đó một cách nhất quán.

## 9. Checklist khi hoàn thiện bài kiểm thử

- Đã biết chính xác claim nào là nguồn quyền và kiểu dữ liệu của từng claim (`String`/UUID/list), cùng quy tắc đối chiếu với tài nguyên.
- MockMvc thực sự chạy Spring Security; nếu có `@PreAuthorize` thì method security được bật.
- Có cặp test **cho phép** và **từ chối** cho mỗi loại claim nghiệp vụ.
- Có ca claim thiếu, rỗng, sai kiểu và claim hợp lệ nhưng không khớp đối tượng truy cập.
- Nếu endpoint yêu cầu scope/role, đã kiểm thử cả quyền kỹ thuật lẫn quyền tenant/người dùng.
- Phân biệt rõ `401` chưa xác thực với `403` đã xác thực nhưng không đủ quyền, lưu ý handler tùy biến của hệ thống.
- Với API ghi hoặc dữ liệu nhiều tenant, đã kiểm tra **side effect** và ranh giới truy vấn dữ liệu.
- Có test riêng cho decoder, converter và Bearer flow khi yêu cầu bao phủ việc xử lý JWT thực, thay vì suy điều đó từ `.with(jwt())`.

**Kết quả mong đợi:** một JWT giả lập có `tenantId`/`userId` hợp lệ chỉ được phép truy cập đúng phạm vi nghiệp vụ; mọi trường hợp thiếu claim, sai giá trị hoặc sai kiểu phải bị từ chối một cách xác định. `MockMvc` cùng `spring-security-test` giúp kiểm chứng quyết định HTTP và phân quyền của ứng dụng Servlet; việc xác thực mật mã của token cần được kiểm tra ở một lớp test phù hợp khác.
