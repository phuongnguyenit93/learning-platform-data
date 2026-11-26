# Gán authorities tường minh cho từng ca kiểm thử

> **Chương:** JWT với MockMvc  
> **Module:** `SPRING_SECURITY_TESTING` — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào việc gán `GrantedAuthority` trực tiếp qua `jwt().authorities(...)` để kiểm thử từng quyết định authorization bằng `MockMvc`.

## 1. Mục đích của jwt().authorities(...)

Một API resource server thường bảo vệ endpoint bằng scope hoặc quyền được ánh xạ từ JWT. Ví dụ `GET /api/reports` yêu cầu authority `SCOPE_reports.read`. Khi muốn kiểm tra chính sách này, ta có thể dựng một JWT authentication giả lập và gán authority trực tiếp cho request:

```java
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

Cách này giúp kiểm tra những câu hỏi cụ thể:

- Authority nào được phép gọi endpoint?
- Authority nào không liên quan và phải bị từ chối?
- Một request có nhiều authority được xử lý ra sao?
- Rule dùng `hasAuthority` hay `hasRole` có khớp chính xác với chuỗi được cấp không?
- Method được bảo vệ bằng `@PreAuthorize` có nhận đúng authority không?

`jwt().authorities(...)` tạo JWT authentication cho request test và đặt danh sách `GrantedAuthority` được chỉ định vào authentication đó. Đây là cách cô lập authorization policy khỏi bước đọc claim và chuyển claim thành authority.

**Giới hạn bằng chứng:** helper này không chứng minh issuer đã phát claim đúng, converter production đã ánh xạ đúng, Bearer token có chữ ký hợp lệ hoặc decoder đã kiểm tra expiration. Nó kiểm tra quyết định phân quyền với authentication đã được dựng trong test.

## 2. Phân biệt JWT claim, OAuth2 scope và GrantedAuthority

Ba khái niệm có liên quan nhưng khác nhau:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| JWT claim | Dữ liệu trong payload token | `scope = "reports.read"` |
| OAuth2 scope | Quyền được issuer biểu diễn trong token | `reports.read` |
| `GrantedAuthority` | Quyền Spring Security dùng để ra quyết định | `SCOPE_reports.read` |

Với converter mặc định, scope `reports.read` thường được ánh xạ thành authority `SCOPE_reports.read`. Tuy nhiên, khi dùng `jwt().authorities(...)`, test có thể cấp authority cuối cùng trực tiếp mà không cần đặt claim scope.

**Dựa trên claim:**

```java
mvc.perform(get("/api/reports")
        .with(jwt().jwt(jwt -> jwt
            .subject("partner-42")
            .claim("scope", "reports.read"))))
    .andExpect(status().isOk());
```

**Gán authority trực tiếp:**

```java
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

Cách thứ nhất hữu ích khi muốn kiểm tra claim-to-authority mapping mặc định của helper. Cách thứ hai hữu ích khi chỉ muốn kiểm tra policy với một authority đã biết. Nếu test gán authority trực tiếp rồi kết luận converter production hoạt động đúng, kết luận đó vượt quá phạm vi test.

## 3. Cú pháp và import cần thiết

Helper được cung cấp bởi `SecurityMockMvcRequestPostProcessors`:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
```

Các kiểu thường dùng:

```java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
```

Gán một authority:

```java
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

Gán nhiều authority:

```java
mvc.perform(get("/api/admin/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"),
            new SimpleGrantedAuthority("REPORT_ADMIN"),
            new SimpleGrantedAuthority("TENANT_acme"))))
    .andExpect(status().isOk());
```

Overload varargs nhận một hoặc nhiều đối tượng `GrantedAuthority`. `SimpleGrantedAuthority` là lựa chọn thông dụng khi quyền được biểu diễn bằng một chuỗi chính xác.

Hãy khớp authority với policy thực tế. `REPORT_ADMIN`, `ROLE_REPORT_ADMIN` và `SCOPE_reports.admin` là ba giá trị khác nhau; Spring Security không tự coi chúng tương đương.

## 4. Một request, một tập authority độc lập

Mỗi lần gọi `MockMvc.perform(...)` có thể dựng một authentication khác. Không cần tạo nhiều user trong database hoặc sửa cấu hình ứng dụng để thay quyền cho từng ca.

```java
@Test
void readerCanReadReport() throws Exception {
    mvc.perform(get("/api/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
        .andExpect(status().isOk());
}

@Test
void exporterCannotReadReport() throws Exception {
    mvc.perform(get("/api/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.export"))))
        .andExpect(status().isForbidden());
}
```

Hai test giữ nguyên endpoint và chỉ thay authority. Nếu policy bị nới từ `hasAuthority("SCOPE_reports.read")` thành `authenticated()`, ca thứ hai sẽ thất bại vì JWT authentication vẫn hợp lệ nhưng thiếu scope đọc.

Ma trận quyền cho một số endpoint:

| Endpoint | Authority được cấp | Kỳ vọng |
|---|---|---|
| `GET /api/reports` | `SCOPE_reports.read` | Cho phép |
| `GET /api/reports` | `SCOPE_reports.export` | Từ chối |
| `POST /api/reports/export` | `SCOPE_reports.export` | Cho phép |
| `POST /api/reports/export` | `SCOPE_reports.read` | Từ chối |
| `DELETE /api/reports/42` | `REPORT_ADMIN` | Cho phép nếu policy quy định |
| `DELETE /api/reports/42` | `TENANT_acme` | Từ chối nếu tenant authority không bao hàm quyền xóa |

Đừng cấp một authority rộng như `ADMIN` cho mọi test chỉ để request đi qua controller. Mỗi ca nên mô tả quyền tối thiểu cần có.

## 5. Kết hợp subject, claims và authorities

Có thể vừa tùy chỉnh subject/claims, vừa gán authority trực tiếp. Cách này hữu ích khi controller hoặc service cần đọc claim, trong khi authorization matcher kiểm tra authority.

```java
mvc.perform(get("/api/reports")
        .with(jwt()
            .jwt(jwt -> jwt
                .subject("partner-42")
                .claim("tenant_id", "acme")
                .claim("partner_type", "reseller"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"),
                new SimpleGrantedAuthority("TENANT_acme"))))
    .andExpect(status().isOk());
```

Request này có:

- Subject `partner-42`.
- Custom claim `tenant_id = acme`.
- Hai authority `SCOPE_reports.read` và `TENANT_acme`.

Rule HTTP có thể kiểm tra scope authority; policy trong service có thể đọc tenant claim hoặc principal. Khi đã gọi `authorities(...)`, tập quyền của authentication được đặt theo danh sách chỉ định. Không giả định scope trong claim sẽ tự động được cộng thêm.

Nếu mục tiêu là kiểm tra converter đọc claim `scope`, hãy bỏ `authorities(...)` và để converter mặc định thực hiện mapping.

## 6. Khớp ROLE_, SCOPE_ và authority tùy chỉnh

Spring Security so sánh authority theo chuỗi. Các prefix phổ biến không tự đồng nhất:

| Policy | Authority cần có | Giá trị test |
|---|---|---|
| `hasAuthority("REPORT_ADMIN")` | `REPORT_ADMIN` | `REPORT_ADMIN` |
| `hasRole("ADMIN")` | Thường là `ROLE_ADMIN` | `ROLE_ADMIN` |
| `hasAuthority("SCOPE_reports.read")` | `SCOPE_reports.read` | `SCOPE_reports.read` |
| `hasAuthority("TENANT_acme")` | `TENANT_acme` | `TENANT_acme` |

Ví dụ cấu hình:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/reports/**")
        .hasAuthority("SCOPE_reports.read")
    .anyRequest().denyAll()
)
```

Test tương ứng:

```java
mvc.perform(get("/api/admin/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("ROLE_ADMIN"))))
    .andExpect(status().isOk());

mvc.perform(get("/api/reports/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

Nếu cấp `ADMIN` trong test đầu tiên, `hasRole("ADMIN")` sẽ không khớp với prefix role mặc định `ROLE_`. Nếu ứng dụng tùy chỉnh `GrantedAuthorityDefaults`, hãy dùng prefix thật của ứng dụng.

Scope `reports.read` theo converter mặc định thành `SCOPE_reports.read`; nó không tự trở thành `ROLE_REPORTS_READ`.

## 7. Kiểm tra user đã xác thực nhưng thiếu quyền

Một ca authorization từ chối nên phân biệt được với authentication failure. `jwt()` tạo JWT authentication giả lập; nếu authority không đủ, request thường bị từ chối bằng `403` theo API contract.

```java
@Test
void authenticatedPartnerWithoutReadScopeIsForbidden()
        throws Exception {

    mvc.perform(get("/api/reports")
            .with(jwt()
                .jwt(jwt -> jwt.subject("partner-42"))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isForbidden())
        .andExpect(authenticated().withUsername("partner-42")
            .withAuthorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")));
}
```

Matcher `authenticated()` xác nhận request có authentication với subject và authority đã dựng. Nó không chứng minh password hoặc Bearer token đã được xác minh thật.

Phân biệt các tình huống:

- Không có token hoặc token không hợp lệ: thường `401` theo contract.
- JWT authentication đã có nhưng thiếu authority: thường `403`.
- Ứng dụng có thể tùy chỉnh entry point, access-denied handler hoặc dùng `404` để che giấu tài nguyên; status cần khớp contract thực tế.

Đừng đặt tên test thiếu authority là `invalidJwtIsRejected`. Token trong test này không bị xác minh là invalid; request bị từ chối do authorization.

## 8. Assert authorities trong kết quả MockMvc

Có thể kiểm tra chính xác tập authority được gắn vào request:

```java
mvc.perform(get("/api/reports")
        .with(jwt()
            .jwt(jwt -> jwt.subject("partner-42"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"),
                new SimpleGrantedAuthority("TENANT_acme"))))
    .andExpect(status().isOk())
    .andExpect(authenticated().withUsername("partner-42")
        .withAuthorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"),
            new SimpleGrantedAuthority("TENANT_acme")));
```

Assertion này giúp phát hiện lỗi gán nhầm role, scope hoặc tenant authority. Nếu test nhận `403` ngoài dự kiến, kiểm tra:

1. Authority có đúng chuỗi policy yêu cầu không?
2. Rule dùng `hasRole` hay `hasAuthority`?
3. Prefix `ROLE_` hoặc `SCOPE_` có bị thiếu/thừa không?
4. Request có khớp matcher khác đứng trước không?
5. Method security hoặc policy owner/tenant có bổ sung điều kiện không?

Matcher authentication chỉ quan sát security context trong request test. Nó không thay thế kiểm tra decoder hoặc authentication provider.

## 9. Tạo helper theo vai trò của từng ca

Khi nhiều test dùng cùng một tập quyền, helper nhỏ có thể giảm lặp mà vẫn giữ rõ quyền được cấp.

```java
private static RequestPostProcessor jwtAs(
        String subject,
        String... authorities) {

    GrantedAuthority[] granted =
        Arrays.stream(authorities)
            .map(SimpleGrantedAuthority::new)
            .toArray(GrantedAuthority[]::new);

    return jwt()
        .jwt(jwt -> jwt.subject(subject))
        .authorities(granted);
}
```

Dùng helper:

```java
mvc.perform(get("/api/reports")
        .with(jwtAs("partner-42", "SCOPE_reports.read")))
    .andExpect(status().isOk());

mvc.perform(get("/api/reports")
        .with(jwtAs("partner-99", "SCOPE_reports.export")))
    .andExpect(status().isForbidden());
```

Có thể tạo helper mang tên theo policy:

```java
private static RequestPostProcessor reportReader(String subject) {
    return jwtAs(subject, "SCOPE_reports.read");
}

private static RequestPostProcessor reportExporter(String subject) {
    return jwtAs(subject, "SCOPE_reports.export");
}
```

Tránh helper chung tên `authenticatedUser()` tự động cấp mọi authority. Helper quá rộng làm test khó phát hiện endpoint vô tình yêu cầu quyền quá rộng hoặc bị mở policy.

## 10. Data-driven tests cho ma trận authority

`@ParameterizedTest` giúp kiểm tra nhiều tập quyền theo cùng một quy tắc:

```java
static Stream<Arguments> reportReadCases() {
    return Stream.of(
        Arguments.of(
            "reader",
            List.of("SCOPE_reports.read"),
            200),
        Arguments.of(
            "exporter",
            List.of("SCOPE_reports.export"),
            403),
        Arguments.of(
            "order-reader",
            List.of("SCOPE_orders.read"),
            403),
        Arguments.of(
            "admin",
            List.of("ROLE_ADMIN"),
            403)
    );
}

@ParameterizedTest(name = "{0} -> {2}")
@MethodSource("reportReadCases")
void reportEndpointRequiresReadAuthority(
        String subject,
        List<String> authorities,
        int expectedStatus) throws Exception {

    GrantedAuthority[] granted = authorities.stream()
        .map(SimpleGrantedAuthority::new)
        .toArray(GrantedAuthority[]::new);

    mvc.perform(get("/api/reports")
            .with(jwt()
                .jwt(jwt -> jwt.subject(subject))
                .authorities(granted)))
        .andExpect(status().is(expectedStatus));
}
```

Ví dụ giả định endpoint chỉ yêu cầu `SCOPE_reports.read` và không có rule đặc biệt cho admin. Nếu admin được phép đọc, policy và test phải thể hiện quyền đó một cách tường minh.

Mỗi row nên chỉ thay đổi một điều kiện quan trọng. Nếu đồng thời thay subject, tenant, authority và resource ID, status từ chối sẽ khó giải thích.

## 11. Dùng authorities trong @WebMvcTest

`@WebMvcTest` có thể kiểm tra controller và request authorization trong MVC slice. Cần nạp security configuration thật của route và giữ filters hoạt động.

```java
@WebMvcTest(ReportController.class)
@Import(ApiSecurityConfiguration.class)
class ReportAuthorityMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ReportService reports;

    @Test
    void readerCanReachController() throws Exception {
        when(reports.read()).thenReturn("report-acme");

        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read"))))
            .andExpect(status().isOk())
            .andExpect(content().string("report-acme"));

        verify(reports).read();
    }

    @Test
    void unrelatedAuthorityCannotReachController() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());

        verifyNoInteractions(reports);
    }
}
```

Ví dụ dùng `@MockitoBean` trên các phiên bản Spring Framework hỗ trợ; dự án cũ có thể dùng annotation mock bean tương ứng. Service được mock vì mục tiêu là request authorization; filter chain và matcher vẫn phải thật.

Không dùng `@AutoConfigureMockMvc(addFilters = false)` trong bài test này. Nếu slice cần bean `JwtDecoder` để khởi tạo resource server configuration, có thể cung cấp bean test/mock khi request dùng `jwt()`; việc đó không biến test thành decoder test.

## 12. Dùng authorities trong @SpringBootTest

Khi cần application context rộng hơn, có thể dùng `@SpringBootTest` và `@AutoConfigureMockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void readAuthorityIsAllowed() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void exportOnlyAuthorityIsDeniedForReadEndpoint()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.export"))))
            .andExpect(status().isForbidden());
    }
}
```

Đây là test tích hợp application context nhưng authentication vẫn được dựng giả lập. Nó có thể chứng minh filter chain, controller và bean được nạp đã áp dụng authority đúng nếu request đi qua các thành phần đó. Nó không chứng minh Bearer header, decoder hoặc converter production đã xử lý token thật.

## 13. Dùng authorities với method security

`jwt().authorities(...)` cũng có thể kiểm tra service được bảo vệ bằng `@PreAuthorize` nếu request đi qua controller gọi service bean thật.

Ví dụ:

```java
@Service
class RefundService {

    @PreAuthorize("hasAuthority('PAYMENT_REFUND')")
    public String refund(Long paymentId) {
        return "refund-" + paymentId;
    }
}
```

Test qua HTTP:

```java
@Test
void refundAuthorityCanCallService() throws Exception {
    mvc.perform(post("/api/payments/42/refund")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("PAYMENT_REFUND")))
            .with(csrf()))
        .andExpect(status().isOk());
}

@Test
void reportReadCannotRefund() throws Exception {
    mvc.perform(post("/api/payments/42/refund")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")))
            .with(csrf()))
        .andExpect(status().isForbidden());
}
```

Các test này chỉ chứng minh method security nếu:

- `@EnableMethodSecurity` được bật.
- `RefundService` là bean Spring thật.
- Controller gọi bean đó qua proxy.
- CSRF hợp lệ được cấp nếu endpoint/session policy yêu cầu.
- Dependency phía sau được kiểm tra để bảo đảm request bị từ chối không gây side effect.

Nếu kiểm tra trực tiếp service, inject bean Spring-managed và gọi qua proxy; không tạo service bằng `new` và không mock chính service.

## 14. Direct assignment và converter overload

`JwtRequestPostProcessor` có thể nhận authority gán trực tiếp hoặc một converter để tạo authority từ JWT.

**Gán trực tiếp:**

```java
.with(jwt().authorities(
    new SimpleGrantedAuthority("SCOPE_reports.read")))
```

Cách này đặt rõ tập quyền cho test case và bỏ qua bước claim mapping.

**Cung cấp converter:**

```java
.with(jwt().authorities(new JwtGrantedAuthoritiesConverter()))
```

Overload nhận converter hữu ích khi muốn test post-processor sử dụng converter cụ thể. Tuy nhiên, nếu mục tiêu là xác minh converter bean production được resource server cấu hình sử dụng, truyền một converter mới trong test không chứng minh bean production đã được gắn vào chain.

Với custom converter, nên có ba lớp test:

1. Unit test converter nhận JWT fixture và trả authority mong đợi.
2. Authorization test dùng authority trực tiếp để cô lập policy.
3. Integration test Bearer token thật qua decoder và converter production để kiểm tra wiring.

## 15. Những điều gán authorities trực tiếp không chứng minh

| Điều muốn chứng minh | Direct assignment có đủ không? | Bằng chứng cần thêm |
|---|---|---|
| Matcher yêu cầu đúng authority | Có | Cặp allow/deny |
| Method security kiểm tra đúng authority | Có, nếu gọi qua proxy thật | Test method security |
| Controller đọc subject hoặc claim | Có thể kết hợp `jwt().jwt(...)` | Assertion principal/response |
| Scope claim thành `SCOPE_` | Không | Claim-driven test và converter test |
| Custom role claim được ánh xạ | Không | Unit test custom converter |
| Bearer header được parse | Không | Authorization header qua filter chain |
| Chữ ký JWT hợp lệ | Không | Decoder thật và token ký bằng test key |
| `iss`/`aud`/`exp` được xác minh | Không | Validators thật với token tương ứng |
| Token bị revoke/introspect | Không | Introspection/revocation integration test |
| User tồn tại trong database | Không | Test user store/authentication provider |
| Password đúng/sai | Không | Credentials qua authentication provider |

Một test tên `invalidJwtIsRejected` nhưng dùng `jwt().authorities(...)` không phải test token invalid. Helper đã cung cấp authentication cho request; test đang kiểm tra authorization.

## 16. Lỗi thường gặp khi gán authority

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Dùng `reports.read` thay `SCOPE_reports.read` | Matcher mặc định không khớp | Gán authority đúng prefix |
| Dùng `ROLE_ADMIN` cho `hasAuthority("ADMIN")` | Sai chuỗi | Khớp chính xác policy |
| Dùng `ADMIN` cho `hasRole("ADMIN")` | Thiếu role prefix mặc định | Gán `ROLE_ADMIN` |
| Gán authority trực tiếp rồi kết luận converter đúng | Bỏ qua claim mapping | Dùng claim-driven test và converter test |
| Chỉ test ca đủ quyền | Policy có thể bị mở rộng mà test vẫn xanh | Thêm authority không liên quan |
| Cấp mọi quyền trong helper dùng chung | Test không phát hiện quyền thừa | Helper theo từng vai trò/policy |
| Dùng `jwt()` để kiểm tra password/chữ ký | Không chạy authentication mechanism | Credentials/token thật qua provider/decoder |
| Tắt filters trong MockMvc | Bỏ qua request authorization | Giữ filter chain thật |
| Mock service có `@PreAuthorize` | Method-security interceptor không chạy | Dùng service bean thật |
| Không kiểm tra side effect | Có thể vẫn ghi dữ liệu/gọi gateway | Verify collaborator và trạng thái dữ liệu |

## 17. Bài tập: ma trận authority cho API báo cáo

Một resource server có các endpoint:

- `GET /api/reports` yêu cầu `SCOPE_reports.read`.
- `POST /api/reports/export` yêu cầu `SCOPE_reports.export`.
- `DELETE /api/reports/{id}` yêu cầu `REPORT_ADMIN`.
- `GET /api/tenant/reports` yêu cầu `SCOPE_reports.read` và tenant authority phù hợp.
- `ReportExportService.export()` được bảo vệ bằng `@PreAuthorize("hasAuthority('SCOPE_reports.export')")`.

Hãy viết các test:

1. Gán `SCOPE_reports.read` và xác minh GET reports được phép.
2. Gán `SCOPE_reports.export` và xác minh GET reports bị từ chối.
3. Gán `SCOPE_reports.export` và xác minh POST export được phép.
4. Gán `SCOPE_reports.read` và xác minh POST export bị từ chối.
5. Gán `REPORT_ADMIN` và xác minh DELETE được phép.
6. Gán `ROLE_ADMIN` nhưng không có `REPORT_ADMIN` và xác minh kết quả theo policy.
7. Gán scope đúng nhưng tenant authority sai và xác minh tenant endpoint bị từ chối.
8. Kết hợp subject/tenant claims với authority trực tiếp để kiểm tra principal và resource policy.
9. Gọi method được bảo vệ qua Spring proxy với authority đủ/thiếu.
10. Thêm converter test riêng để chứng minh claim-to-authority mapping; giải thích vì sao direct assignment không thay thế nó.
11. Thêm token thật qua decoder để kiểm tra chữ ký, issuer, audience và expiration nếu các nội dung đó nằm trong phạm vi xác minh.

Với mỗi test, ghi rõ authority được gán, rule mong đợi, status, service nào được gọi và điều mà test không chứng minh.

**Tiêu chí hoàn thành:** Bạn có thể gán chính xác một hoặc nhiều `GrantedAuthority` cho từng JWT request trong MockMvc, tạo cặp allow/deny rõ ràng, khớp đúng prefix `ROLE_`/`SCOPE_` và dùng assertion security context để kiểm tra principal. Đồng thời, bạn biết khi nào direct assignment là cách cô lập authorization phù hợp và khi nào phải kiểm tra claim converter hoặc decoder bằng một test riêng.
