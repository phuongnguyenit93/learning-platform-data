# Bảo vệ endpoint đặc tả theo nhóm

Một ứng dụng Spring Boot có thể công bố nhiều OpenAPI document: tài liệu public cho đối tác, tài liệu nội bộ cho đội phát triển và tài liệu quản trị cho vận hành. Mỗi nhóm có URL riêng, nhưng nếu mọi endpoint `/v3/api-docs/**` đều được mở công khai thì người ngoài vẫn có thể tải các tài liệu nội bộ bằng cách gọi trực tiếp URL của nhóm.

`GroupedOpenApi` chỉ quyết định operation nào xuất hiện trong từng tài liệu. Nó không kiểm tra người gọi có quyền tải tài liệu hay không. Muốn giới hạn quyền đọc theo nhóm, cần bảo vệ các endpoint tài liệu bằng Spring Security, gateway hoặc reverse proxy. Quy tắc bảo vệ phải áp dụng cho cả JSON và YAML, đồng thời xem xét endpoint `swagger-config` mà Swagger UI dùng để tìm các document.

## 1. Những endpoint cần được bảo vệ

Với cấu hình springdoc mặc định, các URL thường gặp gồm:

| Endpoint | Mục đích |
| --- | --- |
| `/v3/api-docs` | OpenAPI JSON mặc định. |
| `/v3/api-docs.yaml` | OpenAPI YAML mặc định. |
| `/v3/api-docs/{group}` | OpenAPI JSON của một nhóm. |
| `/v3/api-docs/{group}.yaml` | OpenAPI YAML của một nhóm. |
| `/v3/api-docs/swagger-config` | Cấu hình mà Swagger UI dùng để tìm URL tài liệu và tùy chọn giao diện. |
| `/swagger-ui.html` | Điểm vào giao diện Swagger UI. |
| `/swagger-ui/**` | HTML, JavaScript, CSS, font và các tài nguyên tĩnh của giao diện. |

Ví dụ với hai nhóm:

- `public-v1`: `/v3/api-docs/public-v1` và `/v3/api-docs/public-v1.yaml`.
- `internal-v1`: `/v3/api-docs/internal-v1` và `/v3/api-docs/internal-v1.yaml`.

Nếu ứng dụng cấu hình `springdoc.api-docs.path`, ví dụ đổi thành `/api-docs`, hãy dùng base path mới trong tất cả security matcher. Context path hoặc prefix của reverse proxy cũng cần được tính đến khi kiểm tra URL công khai.

## 2. Phân biệt lọc tài liệu với bảo vệ endpoint

Một cấu hình nhóm có thể chỉ đưa controller public vào tài liệu:

```java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public-v1")
        .pathsToMatch("/api/public/**")
        .build();
}

@Bean
GroupedOpenApi internalApi() {
    return GroupedOpenApi.builder()
        .group("internal-v1")
        .pathsToMatch("/api/internal/**")
        .build();
}
```

Hai bean trên tạo hai OpenAPI document khác nhau. Chúng không tạo rule truy cập cho `/v3/api-docs/public-v1` hoặc `/v3/api-docs/internal-v1`.

Tương tự, các annotation như `@SecurityScheme`, `@SecurityRequirement` và `@SecurityRequirements` mô tả cơ chế xác thực của operation trong hợp đồng OpenAPI. Chúng không tự bảo vệ endpoint phân phối tài liệu. Muốn chỉ quản trị viên tải được tài liệu nội bộ, cần có rule runtime như `hasRole(...)`, `hasAuthority(...)` hoặc chính sách tương ứng ở gateway.

## 3. Bảo vệ toàn bộ endpoint tài liệu

Các đoạn `SecurityFilterChain` trong bài là những phương án cấu hình thay thế nhau. Trong một ứng dụng, hãy chọn và kết hợp rule thành cấu hình phù hợp; không khai báo nhiều bean có cùng mục đích matcher nếu chúng không được tách thành các chain có `securityMatcher` và `@Order` rõ ràng.

Nếu tất cả tài liệu chỉ dành cho người dùng đã đăng nhập, có thể bảo vệ cả base path của API docs:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/v3/api-docs/**", "/v3/api-docs.yaml")
                .hasRole("DOCS_READER")
            .requestMatchers("/swagger-ui.html", "/swagger-ui/**")
                .hasRole("DOCS_READER")
            .anyRequest().authenticated()
        )
        .build();
}
```

Trong ví dụ này, người dùng cần authority `ROLE_DOCS_READER` để tải JSON/YAML, `swagger-config` và tài nguyên giao diện. `hasRole("DOCS_READER")` tự thêm tiền tố `ROLE_`; nếu ứng dụng dùng authority có tên khác, có thể dùng `hasAuthority("docs.read")`.

Nếu muốn giao diện có thể tải nhưng nội dung tài liệu cần xác thực, có thể cho phép tài nguyên tĩnh và bảo vệ endpoint docs:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/swagger-ui.html", "/swagger-ui/**").permitAll()
            .requestMatchers("/v3/api-docs/**", "/v3/api-docs.yaml")
                .hasAuthority("docs.read")
            .anyRequest().authenticated()
        )
        .build();
}
```

Lưu ý: trong cấu hình thứ hai, trang giao diện có thể mở được nhưng Swagger UI vẫn không tải tài liệu nếu trình duyệt chưa có thông tin xác thực phù hợp. Cho phép HTML/JavaScript không đồng nghĩa cho phép `swagger-config` hoặc OpenAPI JSON.

## 4. Phân quyền riêng cho từng group

Khi tài liệu public và internal có đối tượng sử dụng khác nhau, khai báo matcher cụ thể trước matcher tổng quát:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            // swagger-config được xử lý riêng trước matcher group.
            .requestMatchers(HttpMethod.GET, "/v3/api-docs/swagger-config")
                .permitAll()

            // Chỉ người có quyền đọc tài liệu nội bộ mới tải được group này.
            .requestMatchers(HttpMethod.GET,
                "/v3/api-docs/internal-v1",
                "/v3/api-docs/internal-v1.yaml")
                .hasAuthority("docs.internal.read")

            // Tài liệu public cho phép tải ẩn danh.
            .requestMatchers(HttpMethod.GET,
                "/v3/api-docs/public-v1",
                "/v3/api-docs/public-v1.yaml")
                .permitAll()

            // Tài liệu mặc định không được công bố trong ví dụ này.
            .requestMatchers(HttpMethod.GET,
                "/v3/api-docs",
                "/v3/api-docs.yaml")
                .denyAll()

            // Mọi đường dẫn docs khác đều bị từ chối nếu chưa có rule cụ thể.
            .requestMatchers("/v3/api-docs/**").denyAll()
            .anyRequest().authenticated()
        )
        .build();
}
```

Thứ tự matcher rất quan trọng: Spring Security áp dụng rule đầu tiên khớp request. Vì `swagger-config` nằm dưới `/v3/api-docs/`, cần đặt rule riêng trước matcher rộng `/v3/api-docs/**`. Nếu matcher rộng xuất hiện trước, rule cụ thể phía sau sẽ không được áp dụng.

Ví dụ dùng `hasAuthority("docs.internal.read")` để minh họa quyền đọc tài liệu nội bộ. Có thể ánh xạ quyền này từ JWT claim, LDAP, database hoặc hệ thống phân quyền của tổ chức. Nếu dùng OAuth2 Resource Server với scope, authority thường có dạng `SCOPE_docs.internal.read`; khi đó matcher cần dùng đúng tên authority đã được converter tạo ra.

Các matcher trong ví dụ giới hạn HTTP GET vì endpoint tài liệu được đọc bằng GET. Nếu ứng dụng có matcher hoặc filter riêng cho các method khác, vẫn nên bảo đảm request không mong muốn đến base path docs bị từ chối.

## 5. Vì sao phải xử lý `swagger-config` riêng?

Swagger UI thường tải `/v3/api-docs/swagger-config` trước, sau đó mới tải URL document được liệt kê trong cấu hình. Endpoint này có thể chứa danh sách nhóm tài liệu, ví dụ `public-v1` và `internal-v1`.

Nếu `swagger-config` được mở công khai nhưng tài liệu internal bị bảo vệ, người ngoài có thể biết tên group và URL của tài liệu nội bộ, nhưng vẫn phải vượt qua security rule mới tải được nội dung. Việc lộ tên nhóm có thể tiết lộ một phần cấu trúc hệ thống; nếu không muốn công bố thông tin đó, hãy giới hạn danh sách group trong cấu hình Swagger UI public hoặc bảo vệ luôn `swagger-config`.

Ví dụ chỉ công bố nhóm public trong Swagger UI dành cho người dùng bên ngoài:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public-v1
    urls-primary-name: Public API
    disable-swagger-default-url: true
```

Danh sách `urls` giúp giao diện public chỉ hiển thị tài liệu `public-v1`. Endpoint `internal-v1` vẫn cần rule bảo vệ riêng vì người dùng có thể gọi trực tiếp URL đó. Ẩn một lựa chọn khỏi giao diện không phải là biện pháp kiểm soát truy cập.

Nếu cần giao diện nội bộ, có thể cung cấp cấu hình Swagger UI riêng cho người dùng đã xác thực hoặc triển khai trang tài liệu nội bộ độc lập. Trong mọi trường hợp, endpoint tài liệu phía server vẫn phải được bảo vệ.

## 6. Xác thực cho người tải tài liệu

Chọn cơ chế xác thực phù hợp với cách người dùng truy cập Swagger UI:

| Cơ chế | Cách hoạt động | Lưu ý khi dùng với Swagger UI |
| --- | --- | --- |
| Session/cookie | Người dùng đăng nhập vào ứng dụng hoặc cổng nội bộ; trình duyệt gửi cookie khi tải docs | Phù hợp với UI cùng origin; kiểm tra cookie, SameSite, Secure và CSRF theo cấu hình. |
| HTTP Basic | Trình duyệt hoặc client gửi thông tin Basic Auth | Có thể phù hợp cho tài liệu nội bộ qua HTTPS; không dùng mật khẩu yếu hoặc truyền qua HTTP. |
| Bearer token | Client gửi `Authorization: Bearer ...` | Cần có cách cung cấp token cho request tải `swagger-config` và OpenAPI document. Nút Authorize của API chưa chắc xử lý được request tải document ban đầu. |
| Gateway/SSO | Reverse proxy hoặc cổng xác thực bảo vệ đường dẫn docs | Hữu ích khi tài liệu dùng chung cơ chế đăng nhập doanh nghiệp; cần chuyển tiếp danh tính/quyền một cách tin cậy. |

Một điểm dễ nhầm: security scheme trong OpenAPI thường được Swagger UI dùng cho request **Try it out**. Nó không tự động bảo vệ request tải `swagger-config` và OpenAPI document. Nếu chính các request tải tài liệu cần bearer token, phải cấu hình cơ chế xác thực cho chúng độc lập; không giả định nút **Authorize** đã được hiển thị và sử dụng trước khi document được tải.

Với UI nội bộ dùng session, hãy bảo đảm trình duyệt gửi cookie đến các endpoint docs và response không bị CORS chặn. Với UI khác origin, cần cấu hình CORS và credentials chính xác. Không đưa client secret hoặc token cố định vào JavaScript, file YAML hay cấu hình Swagger UI được phát công khai.

## 7. Tùy chỉnh base path của OpenAPI

Nếu đổi endpoint đặc tả:

```yaml
springdoc:
  api-docs:
    path: /api-docs
```

Các matcher cũng phải đổi tương ứng, ví dụ:

```java
.requestMatchers(HttpMethod.GET,
    "/api-docs/internal-v1",
    "/api-docs/internal-v1.yaml")
    .hasAuthority("docs.internal.read")
.requestMatchers(HttpMethod.GET,
    "/api-docs/public-v1",
    "/api-docs/public-v1.yaml")
    .permitAll()
.requestMatchers("/api-docs/**").denyAll()
```

Nếu ứng dụng có context path như `/service`, URL bên ngoài có thể là `/service/api-docs/internal-v1`. Cách matcher nhận path phụ thuộc vị trí context path và cấu hình Spring Security; thường matcher được áp dụng trên path bên trong ứng dụng, không tự bao gồm context path. Hãy kiểm tra request thực tế và matcher của phiên bản Spring Security đang dùng thay vì thêm prefix một cách máy móc.

Khi chạy sau reverse proxy, bảo đảm proxy chuyển tiếp request đến đúng ứng dụng và không tạo route công khai khác bỏ qua security filter chain. Nếu gateway có rule riêng, quyền truy cập cần được bảo vệ nhất quán ở cả gateway và ứng dụng.

## 8. Bảo vệ Swagger UI và tài nguyên tĩnh

Có hai quyết định độc lập:

- Ai được mở giao diện Swagger UI?
- Ai được tải từng OpenAPI document?

Nếu tài liệu nội bộ chỉ dành cho nhân viên, thường nên bảo vệ cả trang UI, tài nguyên tĩnh, `swagger-config` và các document. Nếu giao diện public chỉ hiển thị một nhóm public, có thể mở UI nhưng vẫn bảo vệ document internal bằng matcher riêng.

Không mở toàn bộ `/v3/api-docs/**` chỉ vì `/swagger-ui.html` cần tải tài nguyên. Tương tự, không bảo vệ tài nguyên JavaScript/CSS bằng một rule khiến người dùng không thể tải trang, rồi lại kỳ vọng giao diện có thể hoạt động.

Nếu không cần Swagger UI ở production, có thể tắt giao diện bằng cấu hình phù hợp hoặc không đóng gói starter UI. Nếu không muốn công bố OpenAPI endpoint trong môi trường production, có thể tắt endpoint tài liệu bằng `springdoc.api-docs.enabled=false` theo profile. Tắt tài liệu là quyết định triển khai; không thay thế việc bảo vệ các endpoint nghiệp vụ.

## 9. Kiểm thử quyền truy cập từng group

Nên kiểm tra ít nhất ba trường hợp cho mỗi tài liệu được bảo vệ:

1. Người chưa xác thực gọi tài liệu nội bộ phải bị từ chối.
2. Người đã xác thực nhưng thiếu authority đọc docs phải bị từ chối.
3. Người có authority phù hợp phải tải được JSON và YAML.

Ví dụ MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class DocumentationProtectionTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotReadInternalDocs() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousCannotReadInternalYaml() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1.yaml"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void authenticatedUserWithoutDocsAuthorityIsForbidden() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "docs.internal.read")
    void authorizedUserCanReadInternalJson() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists());
    }

    @Test
    @WithMockUser(authorities = "docs.internal.read")
    void authorizedUserCanReadInternalYaml() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1.yaml"))
            .andExpect(status().isOk());
    }

    @Test
    void publicDocsRemainAvailable() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists());
    }
}
```

Ví dụ giả định ứng dụng cấu hình entry point trả `401` khi chưa xác thực. Một số ứng dụng chuyển hướng đến trang đăng nhập hoặc trả status khác; hãy kiểm tra đúng chính sách thực tế. Nên có thêm test cho người dùng đã đăng nhập nhưng thiếu authority để xác nhận bị `403`.

Nếu `swagger-config` được mở công khai, kiểm tra response của nó không vô tình công bố danh sách nhóm nội bộ ngoài chính sách. Nếu được bảo vệ, kiểm tra người dùng hợp lệ có thể tải cấu hình và Swagger UI hoạt động với cơ chế đăng nhập đã chọn.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Group internal tải được khi chưa đăng nhập | Chỉ lọc bằng `GroupedOpenApi`, chưa bảo vệ URL docs | Thêm matcher runtime cho JSON và YAML của group. |
| JSON bị chặn nhưng YAML vẫn tải được | Matcher chỉ bao phủ URL không có hậu tố `.yaml` | Thêm route YAML vào cùng rule và kiểm thử cả hai. |
| Rule bảo vệ group không có tác dụng | Matcher tổng quát xuất hiện trước matcher cụ thể | Đặt rule group cụ thể trước rule `/v3/api-docs/**`. |
| `swagger-config` bị chặn ngoài dự kiến | Matcher rộng bắt endpoint config trước rule riêng | Đặt matcher `swagger-config` trước matcher group hoặc matcher tổng. |
| UI mở được nhưng báo lỗi tải API definition | Tài nguyên UI public nhưng docs/config yêu cầu đăng nhập | Cấu hình xác thực trình duyệt cho docs/config hoặc bảo vệ toàn bộ UI theo session/SSO. |
| UI public vẫn liệt kê tên group internal | `swagger-config` công bố tất cả nhóm đã đăng ký | Cấu hình danh sách `springdoc.swagger-ui.urls` public riêng hoặc bảo vệ config. |
| Đã ẩn group trong Swagger UI nhưng URL direct vẫn truy cập được | Chỉ ẩn lựa chọn trên giao diện, không có security rule | Bảo vệ endpoint docs ở Spring Security/gateway. |
| Người có token vẫn không tải được docs | Token không có authority cần thiết hoặc docs fetch không gửi token | Kiểm tra authority mapping và cơ chế xác thực request tải tài liệu. |
| Custom auth filter chặn endpoint public | Filter từ chối request trước authorization rule | Cấu hình filter bỏ qua path public hoặc xử lý credential đúng thiết kế. |
| Đổi `springdoc.api-docs.path` nhưng docs trả `404`/không bảo vệ | Security matcher và proxy vẫn dùng path cũ | Đồng bộ cấu hình springdoc, matcher, gateway và URL Swagger UI. |
| Test mong `401` nhưng nhận `302` | Entry point chuyển hướng đến trang đăng nhập | Điều chỉnh assertion theo chính sách authentication của ứng dụng. |

## 11. Checklist triển khai

Trước khi công bố tài liệu theo nhóm, hãy xác nhận:

- Group id có tên ổn định và các URL JSON/YAML đã được xác định.
- Tài liệu public và internal có rule truy cập riêng.
- Matcher cụ thể đứng trước matcher tổng quát.
- Endpoint `swagger-config` được bảo vệ hoặc chỉ liệt kê các nhóm được phép công bố.
- Swagger UI và tài nguyên tĩnh có chính sách truy cập phù hợp.
- Cơ chế session, Basic Auth, bearer token hoặc SSO phù hợp với cách trình duyệt tải tài liệu.
- Base path, context path và reverse proxy khớp với matcher thực tế.
- Test xác nhận anonymous, authenticated-without-authority và authorized access cho cả JSON lẫn YAML.
- Các group document không chứa thông tin bí mật, token, password hoặc dữ liệu môi trường nhạy cảm.
- Nếu không cần tài liệu ở production, cân nhắc tắt OpenAPI endpoint hoặc không đóng gói Swagger UI trong profile đó.

## 12. Nguyên tắc áp dụng

- Dùng `GroupedOpenApi` để chia nội dung tài liệu và Spring Security/gateway để kiểm soát người được tải tài liệu.
- Bảo vệ cả JSON và YAML của từng group.
- Đặt matcher cho `swagger-config` và group cụ thể trước matcher tổng quát `/v3/api-docs/**`.
- Chỉ mở công khai những group được chủ đích công bố; từ chối mặc định các group còn lại.
- Nhớ rằng `swagger-config` có thể tiết lộ tên và URL nhóm dù document đã được bảo vệ.
- Không xem việc ẩn group khỏi Swagger UI là biện pháp bảo mật.
- Chọn cơ chế xác thực mà trình duyệt có thể dùng ngay khi tải cấu hình và OpenAPI document.
- Đồng bộ `springdoc.api-docs.path`, context path, reverse proxy và security matcher.
- Kiểm thử truy cập trực tiếp URL JSON/YAML, không chỉ thao tác qua Swagger UI.

Bảo vệ endpoint đặc tả theo nhóm yêu cầu hai phần cấu hình phối hợp: springdoc tạo các document riêng theo group id, còn Spring Security hoặc gateway quyết định ai được tải từng document. Khi bảo vệ đúng JSON, YAML và `swagger-config`, đồng thời kiểm tra URL trực tiếp bằng các vai trò khác nhau, tài liệu public có thể được phân phối thuận tiện trong khi tài liệu nội bộ vẫn nằm sau cơ chế kiểm soát truy cập.

## Tài liệu tham khảo

- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)
- [Springdoc OpenAPI FAQ – GroupedOpenApi và Swagger UI](https://springdoc.org/faq.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [OpenAPI Specification – Security Requirements](https://spec.openapis.org/oas/latest.html)
