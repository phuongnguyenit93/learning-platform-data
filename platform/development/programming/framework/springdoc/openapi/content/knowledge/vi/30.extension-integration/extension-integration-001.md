# Scalar như lựa chọn giao diện bên cạnh Swagger UI

## 1. Scalar trong hệ sinh thái Springdoc

Springdoc OpenAPI phân tích controller, DTO, annotation, validation và cấu hình ứng dụng để tạo OpenAPI document. Swagger UI hoặc Scalar dùng document đó để hiển thị API reference trong trình duyệt.

Scalar là một giao diện API reference có thể đọc OpenAPI JSON/YAML và trình bày endpoint, schema, parameter, request body, response cùng thông tin bảo mật. Khi tích hợp với Spring Boot, Scalar đóng vai trò giao diện cho tài liệu; Springdoc vẫn chịu trách nhiệm sinh hợp đồng OpenAPI từ ứng dụng.

Có thể hình dung luồng xử lý:

~~~text
Spring MVC / WebFlux controllers
             |
             v
       Springdoc OpenAPI
             |
             v
       /v3/api-docs
             |
       +-----+------+
       |            |
       v            v
   Swagger UI     Scalar
       |            |
       +-----+------+
             |
             v
      API endpoints
~~~

Scalar không tự phát hiện controller, không tạo schema từ Java DTO và không thay thế Springdoc. Nó đọc OpenAPI document mà Springdoc công bố. Vì vậy, nếu /v3/api-docs thiếu operation hoặc schema sai, đổi giao diện sang Scalar không tự sửa được hợp đồng.

## 2. Khi nào chọn Scalar bên cạnh Swagger UI?

Cả Scalar và Swagger UI đều có thể hiển thị OpenAPI document và hỗ trợ người dùng khám phá API. Việc chọn giao diện phụ thuộc nhu cầu của nhóm phát triển, người tích hợp và hệ thống tài liệu hiện tại.

| Tiêu chí | Swagger UI | Scalar |
|---|---|---|
| Nguồn dữ liệu | OpenAPI JSON/YAML | OpenAPI JSON/YAML |
| Vai trò | API documentation UI | API reference UI |
| Khám phá operation | Có | Có |
| Hiển thị schema | Có | Có |
| Thử request | Try it out | API client/try request theo khả năng phiên bản |
| Tùy biến | Configuration, plugin và custom assets | Configuration và theme của Scalar |
| Tích hợp Springdoc | Starter UI tích hợp trực tiếp | Có thể nhúng giao diện Scalar riêng hoặc dùng integration phù hợp |
| Phụ thuộc hợp đồng | Cần OpenAPI document hợp lệ | Cần OpenAPI document hợp lệ |

Scalar có thể phù hợp khi nhóm muốn một giao diện API reference khác, cách điều hướng và trình bày khác, hoặc muốn dùng cùng một OpenAPI contract trên website developer portal.

Không cần loại bỏ Swagger UI ngay khi thêm Scalar. Hai giao diện có thể cùng tồn tại ở các URL khác nhau để nhóm so sánh, kiểm thử và chuyển đổi theo từng giai đoạn.

## 3. Kiến trúc tích hợp tối thiểu

Một cách tích hợp ít phụ thuộc là để Spring Boot phục vụ một trang HTML tĩnh, còn trang đó tải Scalar JavaScript và đọc OpenAPI document từ Springdoc.

Luồng request:

1. Người dùng mở /scalar/.
2. Spring Boot trả về trang HTML tĩnh.
3. Trình duyệt tải Scalar API Reference bundle.
4. Scalar gọi /v3/api-docs.
5. Scalar render API reference dựa trên document.
6. Khi người dùng thử một operation, trình duyệt gọi API server được mô tả trong trường servers hoặc URL được chọn.

Cách này không yêu cầu controller Java riêng cho Scalar. Nó cũng giữ cho nguồn contract duy nhất là OpenAPI document do Springdoc tạo.

Trong môi trường production, có thể self-host Scalar assets hoặc dùng integration/starter chính thức tương thích với phiên bản Spring Boot đang chạy. Hãy kiểm tra artifact coordinates và cấu hình theo release của Scalar thay vì sao chép version từ một ví dụ cũ.

## 4. Bảo đảm Springdoc vẫn xuất OpenAPI document

Scalar cần một URL OpenAPI có thể truy cập. Với cấu hình mặc định, Springdoc thường cung cấp:

~~~http
GET /v3/api-docs
GET /v3/api-docs.yaml
~~~

Có thể giữ cấu hình mặc định:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
~~~

api-docs.enabled điều khiển việc tạo endpoint OpenAPI. swagger-ui.enabled điều khiển Swagger UI tích hợp. Hai chức năng này độc lập: có thể tắt Swagger UI nhưng vẫn giữ OpenAPI JSON/YAML để Scalar hoặc công cụ khác sử dụng.

Nếu tắt springdoc.api-docs.enabled, Scalar không còn nguồn dữ liệu ở /v3/api-docs. Trang Scalar có thể vẫn tải được, nhưng phần API reference sẽ báo lỗi khi fetch document.

## 5. Tạo trang Scalar tĩnh trong Spring Boot

Tạo file:

~~~text
src/main/resources/static/scalar/index.html
~~~

Spring Boot tự phục vụ static resource trong classpath. File trên thường có thể truy cập tại /scalar/.

Ví dụ nội dung:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Catalog API Reference</title>
</head>
<body>
  <script
    id="api-reference"
    data-url="/v3/api-docs"
    data-configuration='{"theme":"purple"}'
    src="https://cdn.jsdelivr.net/npm/@scalar/api-reference">
  </script>
</body>
</html>
~~~

Scalar bundle đọc data-url để biết nơi lấy OpenAPI document. data-configuration truyền cấu hình giao diện. Ví dụ dùng theme purple; các theme và option có thể thay đổi theo phiên bản Scalar.

Đây là cách nhúng qua CDN, thuận tiện cho thử nghiệm và triển khai nhanh. Trước khi dùng production, nên pin version package thay vì tham chiếu URL không có version, hoặc self-host assets để kiểm soát phiên bản và chính sách bảo mật.

## 6. Pin version của Scalar bundle

URL CDN không có version có thể trỏ tới release mới hơn trong tương lai. Khi Scalar cập nhật, giao diện hoặc hành vi có thể thay đổi mà không có commit nào trong repository ứng dụng.

Có thể pin một version cụ thể trong URL:

~~~html
<script
  id="api-reference"
  data-url="/v3/api-docs"
  data-configuration='{"theme":"purple"}'
  src="https://cdn.jsdelivr.net/npm/@scalar/api-reference@<PINNED_VERSION>">
</script>
~~~

Thay <PINNED_VERSION> bằng version đã được kiểm thử trong dự án. Lưu version này trong code review và quy trình nâng cấp frontend dependency.

Không nên dùng latest hoặc URL không pin version cho một tài liệu production quan trọng nếu nhóm cần khả năng tái lập. Hãy kiểm tra release notes và chạy smoke test trước khi nâng Scalar.

## 7. Cấu hình URL OpenAPI cho Scalar

data-url phải trỏ tới document mà trình duyệt có thể tải. Các trường hợp phổ biến:

| Trường hợp | URL tham khảo |
|---|---|
| Springdoc mặc định | /v3/api-docs |
| Springdoc xuất YAML | /v3/api-docs.yaml |
| Document group partner | /v3/api-docs/partner |
| Document group internal | /v3/api-docs/internal |
| API docs path tùy chỉnh | Đường dẫn được cấu hình trong springdoc.api-docs.path |

Nếu Scalar được phục vụ cùng origin với Springdoc, dùng relative/root-relative URL thường tránh được cấu hình CORS bổ sung.

Nếu UI và OpenAPI document nằm ở hai origin khác nhau, trình duyệt áp dụng same-origin policy. Khi đó server cung cấp document phải cho phép origin của Scalar page theo CORS policy; không bật wildcard credentials để giải quyết nhanh.

Hãy kiểm tra URL từ góc nhìn trình duyệt, không chỉ kiểm tra URL gọi được từ máy chủ Spring Boot.

## 8. Dùng Scalar với document groups

Springdoc hỗ trợ tạo nhiều OpenAPI document bằng GroupedOpenApi. Ví dụ:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .build();
}

@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}
~~~

Mỗi group có document endpoint riêng. Scalar page có thể trỏ tới group tương ứng.

Ví dụ trang src/main/resources/static/scalar/partner.html:

~~~html
<script
  id="api-reference"
  data-url="/v3/api-docs/partner"
  data-configuration='{"theme":"purple"}'
  src="https://cdn.jsdelivr.net/npm/@scalar/api-reference@<PINNED_VERSION>">
</script>
~~~

Trang public.html có thể dùng /v3/api-docs/public.

Tách group giúp tránh đưa operation internal vào tài liệu public. Tuy nhiên, group filter chỉ điều khiển nội dung document; nó không tự bảo vệ endpoint runtime. Security phải được cấu hình riêng cho trang Scalar, OpenAPI document và API operation.

## 9. Cho Swagger UI và Scalar cùng tồn tại

Trong giai đoạn đánh giá, có thể giữ Swagger UI và thêm Scalar:

- Swagger UI: /swagger-ui/index.html
- Scalar: /scalar/
- OpenAPI JSON: /v3/api-docs
- OpenAPI YAML: /v3/api-docs.yaml

Cấu hình Springdoc có thể tiếp tục bật Swagger UI:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
  api-docs:
    enabled: true
~~~

Sau khi nhóm quyết định dùng Scalar làm giao diện chính, có thể tắt Swagger UI:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
~~~

Scalar page là static resource riêng nên không bị tắt cùng Swagger UI tích hợp, miễn là static resource vẫn được phục vụ và OpenAPI endpoint vẫn bật.

Không xóa dependency Swagger UI ngay nếu một số nhóm hoặc môi trường vẫn đang dùng nó. Có thể triển khai song song, thu thập phản hồi và chuyển dần.

## 10. Dùng npm khi trang tài liệu có frontend build riêng

Nếu developer portal được xây bằng Vite, React hoặc một frontend framework khác, có thể quản lý Scalar như dependency frontend thay vì tải CDN.

Cài package:

~~~bash
npm install @scalar/api-reference
~~~

Ví dụ entry point JavaScript:

~~~javascript
import { ApiReference } from '@scalar/api-reference'
import '@scalar/api-reference/style.css'

ApiReference('#app', {
  url: '/v3/api-docs',
})
~~~

HTML chứa mount point:

~~~html
<div id="app"></div>
~~~

Cách import cụ thể cần theo tài liệu của version package đã pin. Đảm bảo bundler xử lý CSS và assets đúng. Nếu frontend được deploy ở domain khác Spring Boot, cấu hình CORS và authentication cho OpenAPI endpoint.

Dùng package manager lockfile để cố định dependency tree. Khi nâng Scalar, cập nhật lockfile và chạy kiểm tra giao diện cùng các request thử nghiệm.

## 11. Tích hợp bằng Spring Boot starter hoặc module có sẵn

Scalar có thể cung cấp các integration package dành cho framework hoặc Spring Boot tùy dòng release. Nếu chọn starter, hãy xác minh:

- Artifact groupId/artifactId và version từ tài liệu Scalar chính thức.
- Phiên bản Spring Boot và Java được hỗ trợ.
- Cách cấu hình URL OpenAPI.
- Default path mà integration tạo ra.
- Cách tùy chỉnh theme, layout và authentication.
- Tài nguyên static được đóng gói hay tải từ CDN.
- Cách integration tương tác với Spring Security và context path.

Không giả định mọi starter có cùng property names hoặc URL. Các package có thể thay đổi theo release. Hãy pin version và kiểm tra endpoint thực tế sau khi khởi động.

Nếu chỉ cần một trang API reference, static HTML embed thường đủ và không làm tăng số dependency backend. Starter phù hợp khi dự án muốn framework integration được quản lý sẵn và có yêu cầu tùy biến sâu hơn.

## 12. Authentication và security schemes

Scalar đọc security schemes được mô tả trong OpenAPI document để hiển thị thông tin xác thực phù hợp với operation. Ví dụ bearer JWT:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

security:
  - bearerAuth: []
~~~

Springdoc có thể tạo metadata tương ứng bằng @SecurityScheme và @SecurityRequirement hoặc OpenAPI bean.

Ví dụ:

~~~java
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
@Configuration
class OpenApiSecurityConfiguration {
}
~~~

Khai báo security scheme chỉ mô tả cách client gửi credential. Nó không tự bật authentication trong Spring Security và không làm endpoint an toàn hơn.

Người dùng nhập token vào Scalar có thể gửi token tới API khi dùng chức năng thử request. Không nhúng token thật trong HTML, data-configuration, query string hoặc OpenAPI example.

## 13. Bảo vệ trang Scalar và OpenAPI document

Cần xem đây là các tài nguyên riêng:

- /scalar/**: giao diện Scalar.
- /v3/api-docs và các group: hợp đồng OpenAPI.
- /api/**: endpoint nghiệp vụ.

Có thể yêu cầu role xem tài liệu bằng Spring Security:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
            "/scalar/**",
            "/v3/api-docs",
            "/v3/api-docs/**"
        ).hasRole("API_DOCS")
        .anyRequest().authenticated()
    );

    return http.build();
}
~~~

Ví dụ này minh họa chính sách Servlet Security. Ứng dụng thực tế cần kết hợp cơ chế login/token, CSRF, CORS và các filter chain hiện có.

Nếu Scalar page công khai nhưng OpenAPI document được bảo vệ, browser cần có cách xác thực khi tải document. Nếu cả hai đều yêu cầu login, đảm bảo static resource và API docs dùng cùng cơ chế session hoặc token mà trình duyệt hỗ trợ.

Ẩn link Scalar không phải biện pháp bảo mật. Người dùng vẫn có thể gọi trực tiếp /v3/api-docs nếu endpoint chưa được bảo vệ.

## 14. CORS khi Scalar và Springdoc khác origin

Nếu Scalar page được host tại https://developer.example.com còn OpenAPI document nằm tại https://api.example.com, trình duyệt gửi request cross-origin để tải document.

Cần cấu hình CORS ở server tài liệu cho đúng origin, method và header. Ví dụ về mặt chính sách:

- Allowed origin: https://developer.example.com
- Allowed method: GET
- Allowed headers: những header thực sự cần như Authorization
- Allow credentials: chỉ bật khi dùng cookie/session và origin được chỉ định cụ thể

Không dùng * cùng credentialed requests. Nếu cần gửi Authorization header, browser preflight có thể xảy ra và server phải xử lý OPTIONS phù hợp.

Try it out của Scalar còn gọi API server được mô tả trong servers. Nếu API server ở origin khác, CORS của endpoint nghiệp vụ cũng phải cho phép origin của trang Scalar.

## 15. Reverse proxy và context path

Khi ứng dụng chạy sau reverse proxy hoặc có context path, data-url phải khớp URL công khai.

Ví dụ ứng dụng được công bố dưới prefix /catalog:

- Scalar page: /catalog/scalar/
- OpenAPI JSON: /catalog/v3/api-docs
- API: /catalog/api/**

Khi đó HTML có thể cần:

~~~html
<script
  id="api-reference"
  data-url="/catalog/v3/api-docs"
  data-configuration='{"theme":"purple"}'
  src="https://cdn.jsdelivr.net/npm/@scalar/api-reference@<PINNED_VERSION>">
</script>
~~~

Nếu cùng một artifact được triển khai dưới nhiều context path, không hard-code prefix trong HTML. Có thể dùng template engine để sinh URL từ cấu hình deployment hoặc phục vụ một cấu hình Scalar riêng theo môi trường.

Kiểm tra cả forwarded headers, server URL trong OpenAPI document và path của tài nguyên static. Một trang Scalar tải thành công nhưng fetch /v3/api-docs sai prefix vẫn không thể hiển thị API.

## 16. CSP và nguồn JavaScript/CSS

Khi tải Scalar từ CDN, Content Security Policy cần cho phép những nguồn mà bundle thực sự sử dụng. Tùy version và cấu hình, trình duyệt có thể tải script, style, font hoặc gửi fetch tới OpenAPI/API origin.

Không nên mở rộng CSP thành * chỉ để Scalar hoạt động. Hãy dùng Browser Console để xác định resource bị chặn, sau đó chỉ thêm origin cần thiết vào script-src, style-src, font-src hoặc connect-src.

Với môi trường có CSP nghiêm ngặt hoặc không có Internet:

- Self-host Scalar assets.
- Pin version và kiểm tra checksum package.
- Phục vụ JS/CSS cùng origin nếu có thể.
- Tránh inline script không nonce/hash khi CSP không cho phép.
- Kiểm tra asset URL sau khi đóng gói và deploy.

CDN giúp cập nhật nhanh nhưng tạo thêm phụ thuộc bên ngoài và một phần supply-chain risk. Self-host giúp kiểm soát version, availability và chính sách bảo mật.

## 17. Tùy biến theme và giao diện

Scalar hỗ trợ cấu hình giao diện qua configuration object. Ví dụ nhúng:

~~~html
<script
  id="api-reference"
  data-url="/v3/api-docs"
  data-configuration='{"theme":"purple"}'
  src="https://cdn.jsdelivr.net/npm/@scalar/api-reference@<PINNED_VERSION>">
</script>
~~~

Theme chỉ thay đổi cách trình bày. Nó không thay đổi OpenAPI schema, path, security hoặc runtime behavior.

Các option như theme, layout, default HTTP client, hidden clients, search hoặc authentication behavior phụ thuộc version Scalar. Hãy lấy option từ tài liệu của đúng release đã pin, không sao chép một cấu hình cũ mà không kiểm tra.

Nên giữ cấu hình UI gọn. Những thay đổi có ảnh hưởng tới cách client gửi request cần được review như thay đổi trải nghiệm tích hợp, không chỉ là thay đổi thẩm mỹ.

## 18. OpenAPI version và khả năng tương thích Scalar

Scalar đọc OpenAPI document, nhưng khả năng hiển thị một feature phụ thuộc phiên bản Scalar đang dùng. Các cấu trúc như callbacks, webhooks, OpenAPI 3.1 schema và JSON Schema dialect có thể có mức hỗ trợ khác nhau giữa các phiên bản.

Khi nâng OpenAPI version:

1. Kiểm tra trường openapi trong document.
2. Validate document bằng validator hỗ trợ phiên bản đó.
3. Kiểm tra Scalar release đang pin có hỗ trợ feature cần dùng.
4. Mở document và kiểm tra operation, schema, security.
5. Thử request với các media type và authentication quan trọng.
6. Kiểm tra Swagger UI hoặc code generator khác nếu chúng vẫn nằm trong workflow.

Không kết luận document sai chỉ vì UI không render một phần mở rộng. Hãy kiểm tra raw JSON/YAML để phân biệt lỗi sinh contract với giới hạn renderer.

## 19. Vendor extensions và metadata riêng

OpenAPI cho phép vendor extensions có tên bắt đầu bằng x-, ví dụ x-logo, x-tagGroups hoặc extension riêng của tổ chức. Scalar có thể hỗ trợ một số extension để tùy chỉnh cách hiển thị, nhưng mức hỗ trợ phụ thuộc release và loại extension.

Ví dụ extension trong document:

~~~yaml
info:
  title: Catalog API
  version: "1.4.0"
  x-logo:
    url: https://developer.example.com/assets/catalog-logo.svg
    altText: Catalog API
~~~

Không phải mọi UI đều xử lý cùng một vendor extension giống nhau. Swagger UI, Scalar, generator và validator có thể bỏ qua extension không biết.

Dùng extension chỉ cho metadata bổ sung. Không đặt thông tin bắt buộc để hiểu request/response vào extension riêng nếu có thể mô tả bằng trường OpenAPI chuẩn.

## 20. Kiểm tra Scalar hoạt động cùng Springdoc

Sau khi triển khai, kiểm tra lần lượt:

1. Mở /v3/api-docs và xác nhận JSON trả về.
2. Mở /v3/api-docs.yaml nếu trang dùng YAML.
3. Mở /scalar/ và xác nhận HTML được phục vụ.
4. Kiểm tra Browser Network để chắc chắn Scalar tải đúng document URL.
5. Kiểm tra Console để phát hiện CSP, CORS hoặc JavaScript errors.
6. Kiểm tra title, operation, schema, security và server URL.
7. Thử một operation an toàn trên môi trường test.
8. Kiểm tra endpoint group nếu có nhiều tài liệu.
9. Kiểm tra hành vi khi chưa đăng nhập và khi có quyền xem docs.
10. Kiểm tra URL sau reverse proxy/context path.

Có thể dùng MockMvc kiểm tra endpoint tài liệu và static page:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ));

mockMvc.perform(get("/scalar/"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.TEXT_HTML
    ));
~~~

Static resource mapping có thể thay đổi theo context path và cấu hình web. Nếu ứng dụng redirect /scalar/ hoặc dùng trang khác, điều chỉnh test theo URL runtime thực tế.

## 21. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Scalar page trắng hoặc báo không tải được API | data-url sai hoặc OpenAPI endpoint không truy cập được |
| HTML tải được nhưng document trả 401 | Security policy yêu cầu xác thực cho /v3/api-docs |
| Browser báo CORS | Scalar và OpenAPI document khác origin |
| JavaScript bị CSP chặn | CDN/script/style/font/connect origin chưa được cho phép |
| Scalar hiển thị URL localhost | servers trong OpenAPI document sai |
| Group page không có operation | URL group sai hoặc Springdoc filter không khớp |
| Swagger UI hoạt động nhưng Scalar không | Bundle version, JS error hoặc feature compatibility |
| Scalar hoạt động local nhưng lỗi sau deploy | Context path, reverse proxy prefix hoặc CDN policy |
| Tắt Swagger UI làm mất luôn Scalar | api-docs.enabled bị tắt hoặc static resource không được phục vụ |
| Scalar không hiển thị webhook/extension | Renderer version chưa hỗ trợ đầy đủ cấu trúc đó |
| Try request bị browser chặn | CORS của API server hoặc security token không đúng |
| Theme không áp dụng | Cấu hình data-configuration sai định dạng hoặc option không hỗ trợ |

Khi debug, tách lỗi thành ba lớp: trang Scalar, OpenAPI document và API server. Kiểm tra từng URL trực tiếp trước khi thay đổi Springdoc configuration.

## 22. Quy trình chuyển từ Swagger UI sang Scalar

Nếu đang dùng Swagger UI, có thể chuyển theo từng bước:

1. Giữ /v3/api-docs làm nguồn contract.
2. Thêm Scalar page ở URL riêng.
3. Pin Scalar version và kiểm tra license/policy của package theo tổ chức.
4. So sánh cách hiển thị operation, schema và security với Swagger UI.
5. Kiểm tra các workflow Try it out/API client mà nhóm đang dùng.
6. Kiểm tra CORS, CSP, authentication và reverse proxy.
7. Cho nhóm tích hợp dùng thử trên staging.
8. Cập nhật link trong developer portal.
9. Chỉ tắt Swagger UI nếu không còn consumer cần nó.
10. Giữ OpenAPI JSON/YAML endpoint theo chính sách phân phối tài liệu.

Không cần thay đổi controller hoặc DTO chỉ để chuyển giao diện. Nếu hai UI hiển thị khác nhau, trước tiên hãy kiểm tra document OpenAPI; sau đó xác định khác biệt thuộc renderer hay contract.

## 23. Nguyên tắc tích hợp Scalar với Springdoc

Khi dùng Scalar bên cạnh Swagger UI:

1. Giữ Springdoc làm nguồn tạo OpenAPI contract.
2. Xem Scalar là renderer/API reference UI, không phải schema generator.
3. Giữ springdoc.api-docs.enabled=true khi Scalar cần document runtime.
4. Dùng data-url trỏ đúng JSON/YAML endpoint hoặc document group.
5. Có thể giữ Swagger UI và Scalar song song trong giai đoạn chuyển đổi.
6. Pin Scalar package version hoặc self-host assets.
7. Bảo vệ Scalar page và OpenAPI endpoint bằng Spring Security theo audience.
8. Cấu hình CORS khi UI và document khác origin.
9. Điều chỉnh CSP theo các asset origin thực sự cần thiết.
10. Kiểm tra reverse proxy, context path và public server URL.
11. Xác minh khả năng hỗ trợ OpenAPI 3.1, webhook và vendor extensions.
12. Test cả document fetch lẫn API request thực tế trong browser.

Scalar mang lại một lựa chọn giao diện khác cho OpenAPI document mà Springdoc tạo ra. Giữ contract ở một nguồn chuẩn, quản lý rõ URL, version, security và asset policy sẽ giúp nhóm thay đổi trải nghiệm tài liệu mà không làm thay đổi hợp đồng API hoặc gây gián đoạn client tích hợp.

## 24. Tài liệu tham khảo

- [Scalar API Reference](https://github.com/scalar/scalar)
- [Scalar Documentation](https://scalar.com/)
- [Springdoc OpenAPI Documentation](https://springdoc.org/)
- [Springdoc Configuration Properties](https://springdoc.org/properties.html)

