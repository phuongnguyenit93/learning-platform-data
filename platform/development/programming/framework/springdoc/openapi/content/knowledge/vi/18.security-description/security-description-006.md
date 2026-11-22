# API key trong header, query hoặc cookie

## 1. API key là gì trong hợp đồng OpenAPI?

API key là một giá trị do hệ thống cấp cho ứng dụng hoặc client để nhận diện và kiểm soát quyền truy cập API. Client gửi key kèm request; backend kiểm tra key, trạng thái, phạm vi sử dụng và các chính sách liên quan trước khi cho phép xử lý.

Trong OpenAPI, API key được mô tả bằng **Security Scheme Object** có kiểu **apiKey**. Định nghĩa này cho biết key được truyền ở đâu và tên trường nào được dùng:

- **header**: key nằm trong HTTP request header.
- **query**: key nằm trong query string của URL.
- **cookie**: key nằm trong cookie của request.

OpenAPI đặt Security Scheme trong **components.securitySchemes**. Sau đó, **Security Requirement Object** chỉ ra operation nào yêu cầu scheme đó. Springdoc đọc các annotation bảo mật hoặc model OpenAPI để tạo phần này trong tài liệu.

Cần phân biệt hai nhiệm vụ:

- OpenAPI mô tả cách client gửi thông tin xác thực.
- Spring Security hoặc lớp bảo mật của ứng dụng thực sự xác minh API key và quyết định cho phép hay từ chối request.

Khai báo **@SecurityScheme** không tự tạo key, không lưu key và không bật cơ chế kiểm tra key ở backend.

## 2. Cấu trúc API key Security Scheme

Một API key scheme có các thuộc tính cốt lõi:

| Thuộc tính OpenAPI | Ý nghĩa |
|---|---|
| **type** | Phải là **apiKey** |
| **in** | Vị trí truyền key: **header**, **query** hoặc **cookie** |
| **name** | Tên header, query parameter hoặc cookie chứa key |
| **description** | Hướng dẫn cách lấy và gửi key |

Ví dụ OpenAPI YAML cho key trong header:

~~~yaml
components:
  securitySchemes:
    ApiKeyHeaderAuth:
      type: apiKey
      in: header
      name: X-API-Key
      description: API key do hệ thống cấp cho client
security:
  - ApiKeyHeaderAuth: []
~~~

Trong ví dụ:

- **ApiKeyHeaderAuth** là tên scheme được dùng để tham chiếu.
- **type: apiKey** cho biết đây là cơ chế API key.
- **in: header** xác định key nằm trong request header.
- **name: X-API-Key** là tên header mà client phải gửi.
- **security** ở cấp document yêu cầu các operation áp dụng tài liệu này dùng scheme đó, trừ khi operation có security riêng ghi đè.

Tên scheme là định danh nội bộ của tài liệu OpenAPI. Nó có thể khác tên header thực tế. Ví dụ scheme có tên ApiKeyHeaderAuth, nhưng header gửi đi là X-API-Key.

## 3. Khai báo API key trong header bằng annotation

Springdoc hỗ trợ đọc Swagger/OpenAPI annotations. Có thể khai báo API key scheme bằng **@SecurityScheme**:

~~~java
@Configuration
@SecurityScheme(
    name = "ApiKeyHeaderAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key",
    description = "API key do quản trị viên cấp"
)
public class OpenApiSecurityConfiguration {
}
~~~

Các annotation và enum trong ví dụ thuộc những package sau:

~~~java
io.swagger.v3.oas.annotations.security.SecurityScheme
io.swagger.v3.oas.annotations.enums.SecuritySchemeType
io.swagger.v3.oas.annotations.enums.SecuritySchemeIn
~~~

**paramName** trong annotation ánh xạ thành thuộc tính name của Security Scheme Object. Giá trị name ở annotation là tên scheme, còn paramName là tên header mà client gửi.

Sau khi khai báo scheme, tài liệu OpenAPI sẽ có phần tương đương:

~~~yaml
components:
  securitySchemes:
    ApiKeyHeaderAuth:
      type: apiKey
      in: header
      name: X-API-Key
      description: API key do quản trị viên cấp
~~~

Annotation này chỉ định nghĩa scheme. Muốn yêu cầu operation dùng scheme, cần thêm Security Requirement ở cấp document, controller hoặc operation.

## 4. Áp dụng Security Requirement toàn cục

Có thể áp dụng API key cho toàn bộ API bằng **@OpenAPIDefinition**:

~~~java
@Configuration
@OpenAPIDefinition(
    security = {
        @SecurityRequirement(name = "ApiKeyHeaderAuth")
    }
)
@SecurityScheme(
    name = "ApiKeyHeaderAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key"
)
public class OpenApiSecurityConfiguration {
}
~~~

Khi đó, OpenAPI document có Security Requirement ở cấp gốc:

~~~yaml
security:
  - ApiKeyHeaderAuth: []
~~~

Các operation sẽ kế thừa yêu cầu bảo mật toàn cục nếu không khai báo security riêng. Swagger UI có thể hiển thị nút **Authorize** cho scheme này. Người dùng nhập API key ở đó; Swagger UI dùng thông tin đã cấp khi gửi request tới operation được bảo vệ.

Chỉ áp dụng security toàn cục khi mọi operation trong document thực sự yêu cầu key. Nếu có health check, endpoint đăng nhập hoặc API công khai không cần key, cần loại chúng khỏi yêu cầu bảo mật ở cấp operation.

Security Requirement chỉ mô tả yêu cầu của hợp đồng. Backend vẫn phải xác minh key cho từng request.

## 5. Chỉ bảo vệ một controller hoặc operation

Không phải endpoint nào cũng có cùng chính sách truy cập. Có thể đặt **@SecurityRequirement** ở cấp controller:

~~~java
@RestController
@RequestMapping("/api/products")
@SecurityRequirement(name = "ApiKeyHeaderAuth")
public class ProductController {

    @GetMapping
    public List<ProductResponse> findAll() {
        return productService.findAll();
    }

    @GetMapping("/{id}")
    public ProductResponse findById(@PathVariable Long id) {
        return productService.getByIdOrThrow(id);
    }
}
~~~

Các operation trong controller được mô tả là yêu cầu scheme ApiKeyHeaderAuth. Controller khác không có annotation này sẽ không tự động kế thừa yêu cầu từ controller trên.

Có thể khai báo security trực tiếp trên một operation:

~~~java
@GetMapping("/api/reports/summary")
@Operation(
    summary = "Xem báo cáo tổng hợp",
    security = {
        @SecurityRequirement(name = "ApiKeyHeaderAuth")
    }
)
public ReportSummary getSummary() {
    return reportService.getSummary();
}
~~~

Cách khai báo ở operation hữu ích khi chỉ một vài endpoint cần API key. Hãy chọn một cấp phù hợp với ranh giới bảo mật và kiểm tra document sau khi tạo để xác nhận Security Requirement nằm đúng vị trí.

## 6. Loại một endpoint công khai khỏi security toàn cục

Nếu document có Security Requirement toàn cục, operation công khai cần ghi đè yêu cầu đó bằng danh sách security rỗng.

Trong OpenAPI YAML:

~~~yaml
paths:
  /api/health:
    get:
      summary: Kiểm tra trạng thái dịch vụ
      security: []
      responses:
        "200":
          description: Dịch vụ hoạt động
~~~

**security: []** ở operation có nghĩa operation không yêu cầu security scheme nào, kể cả security được kế thừa từ document root.

Đây là điểm khác với việc bỏ thuộc tính security khỏi operation. Nếu operation không khai báo security riêng, nó kế thừa security ở cấp document. Nếu muốn công khai operation, phải biểu diễn override rõ ràng.

Khi dùng annotation, cách biểu diễn security rỗng có thể phụ thuộc cách Springdoc và swagger-annotations phiên bản đang dùng xử lý giá trị mặc định của annotation. Hãy kiểm tra OpenAPI JSON cuối cùng. Nếu cần bảo đảm security: [], có thể dùng OperationCustomizer hoặc OpenApiCustomizer để đặt danh sách security rỗng cho operation được chọn.

Không được nhầm việc ẩn scheme khỏi Swagger UI với việc bỏ bảo vệ ở backend. Nếu endpoint thực sự public, security filter chain cũng phải cho phép request đó.

## 7. API key trong query parameter

Một số API cũ hoặc dịch vụ bên thứ ba yêu cầu key trong query string. Có thể mô tả bằng scheme có **in: query**:

~~~yaml
components:
  securitySchemes:
    ApiKeyQueryAuth:
      type: apiKey
      in: query
      name: api_key
security:
  - ApiKeyQueryAuth: []
~~~

Tương ứng với annotation:

~~~java
@SecurityScheme(
    name = "ApiKeyQueryAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.QUERY,
    paramName = "api_key",
    description = "API key truyền trong query parameter"
)
~~~

Client gửi request dạng:

~~~http
GET /api/products?api_key=CLIENT_KEY
~~~

Không nên dùng key thật trong ví dụ tài liệu. CLIENT_KEY chỉ là placeholder để thể hiện vị trí tham số.

API key trong query có rủi ro bị ghi lại ở nhiều nơi:

- Browser history và bookmark.
- Access log của web server, reverse proxy hoặc API gateway.
- Hệ thống analytics và monitoring.
- URL được sao chép hoặc chia sẻ.
- Referrer trong một số luồng điều hướng.
- Cache hoặc log của các hệ thống trung gian.

HTTPS bảo vệ dữ liệu trên đường truyền nhưng không ngăn URL bị lưu trong log hoặc lịch sử trình duyệt. Vì vậy, nếu thiết kế API mới, nên ưu tiên API key trong header thay vì query string.

## 8. API key trong cookie

OpenAPI cũng cho phép mô tả API key nằm trong cookie:

~~~yaml
components:
  securitySchemes:
    ApiKeyCookieAuth:
      type: apiKey
      in: cookie
      name: API_SESSION
security:
  - ApiKeyCookieAuth: []
~~~

Tương ứng annotation:

~~~java
@SecurityScheme(
    name = "ApiKeyCookieAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.COOKIE,
    paramName = "API_SESSION",
    description = "Cookie phiên do server cấp"
)
~~~

Trình duyệt có thể tự gửi cookie phù hợp với domain, path, thời hạn và chính sách cookie của request. Với cookie xác thực, thường cần cân nhắc các thuộc tính:

- **Secure**: chỉ gửi cookie qua HTTPS.
- **HttpOnly**: ngăn JavaScript đọc cookie.
- **SameSite**: kiểm soát việc gửi cookie trong request cross-site.
- **Path** và **Domain**: giới hạn phạm vi cookie.
- **Max-Age** hoặc **Expires**: kiểm soát thời hạn.

Có một giới hạn quan trọng khi thử API bằng Swagger UI: trình duyệt không cho JavaScript tự đặt header Cookie như một header thông thường. Đây là forbidden request header. Do đó, khai báo scheme in: cookie không bảo đảm nút Authorize có thể tự chèn cookie vào mọi request.

Nếu cookie được server cấp cho đúng domain/path và browser cho phép gửi trong ngữ cảnh đó, trình duyệt có thể tự đính kèm cookie. Nếu Swagger UI và API khác origin, cần kiểm tra credential mode, CORS allowCredentials, origin cụ thể và chính sách SameSite của browser. Hành vi cần được xác minh bằng Network tab trên trình duyệt mục tiêu.

## 9. So sánh header, query và cookie

| Vị trí | Cách gửi | Ưu điểm | Điểm cần lưu ý |
|---|---|---|---|
| Header | X-API-Key: ... | Không nằm trong URL; phù hợp API client và server-to-server | Cần cho phép header trong CORS khi cross-origin |
| Query | ?api_key=... | Tương thích một số API cũ và dịch vụ yêu cầu URL parameter | Dễ xuất hiện trong URL, log, history và analytics |
| Cookie | Cookie: API_SESSION=... do browser gửi | Phù hợp mô hình phiên trình duyệt và cookie do server quản lý | Cần xử lý CSRF, SameSite, CORS credential và giới hạn browser |

Đối với API mới, header thường là lựa chọn dễ kiểm soát hơn. Cookie phù hợp khi ứng dụng sử dụng phiên trình duyệt và có chính sách bảo vệ cookie/CSRF rõ ràng. Query chỉ nên dùng khi có yêu cầu tương thích cụ thể và đã đánh giá rủi ro lộ key.

Không có vị trí nào thay thế được việc quản lý key an toàn ở backend. Hãy cấp key riêng cho từng client, giới hạn quyền, đặt thời hạn khi phù hợp, hỗ trợ thu hồi và luân chuyển key.

## 10. Phân biệt Security Scheme với Parameter Object

Một API key có thể trông giống query parameter hoặc header parameter, nhưng nếu nó dùng để xác thực thì nên mô tả bằng Security Scheme.

Ví dụ khai báo dưới dạng Parameter Object:

~~~java
@Parameter(
    name = "X-API-Key",
    in = ParameterIn.HEADER,
    required = true,
    description = "API key"
)
~~~

Khai báo này chỉ nói rằng operation nhận một header parameter. Nó không thể hiện đầy đủ ngữ nghĩa security scheme và có thể không xuất hiện trong khu vực Authorize của Swagger UI.

Với key dùng để xác thực, nên khai báo:

~~~java
@SecurityScheme(
    name = "ApiKeyHeaderAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key"
)
~~~

Sau đó áp dụng **@SecurityRequirement(name = "ApiKeyHeaderAuth")** cho operation phù hợp.

Chỉ dùng Parameter Object khi giá trị đó là dữ liệu đầu vào nghiệp vụ, không phải credential. Ví dụ X-Tenant-Id có thể là header chọn tenant theo hợp đồng ứng dụng; nếu nó không phải secret hoặc cơ chế xác thực, có thể mô tả như parameter thông thường.

Không nên khai báo cùng một API key vừa là Security Scheme vừa là Parameter Object bắt buộc trên cùng operation nếu không có lý do đặc biệt. Điều này có thể khiến Swagger UI tạo hai cách nhập hoặc tài liệu lặp header.

## 11. Kết hợp nhiều Security Scheme: OR và AND

OpenAPI biểu diễn nhiều lựa chọn bảo mật bằng danh sách Security Requirement Objects. Cần hiểu rõ hai cách kết hợp:

**OR – chấp nhận một trong các scheme:**

~~~yaml
security:
  - ApiKeyHeaderAuth: []
  - ApiKeyQueryAuth: []
~~~

Client có thể dùng API key header hoặc API key query. Mỗi phần tử trong danh sách là một lựa chọn thay thế.

**AND – yêu cầu đồng thời nhiều scheme:**

~~~yaml
security:
  - ApiKeyHeaderAuth: []
    TenantKeyHeaderAuth: []
~~~

Trong cùng một Security Requirement Object, các scheme được liệt kê phải cùng được đáp ứng. Ví dụ, client phải gửi cả API key của ứng dụng và key định danh tenant.

Không nên nhầm hai cấu trúc này. Nếu đặt hai scheme thành hai phần tử riêng trong danh sách, tài liệu có nghĩa OR; nếu đặt chúng thành hai thuộc tính trong cùng object, tài liệu có nghĩa AND.

Khi kết hợp nhiều API key, hãy cân nhắc liệu backend có thực sự kiểm tra tất cả credential theo cùng quy tắc hay không. OpenAPI chỉ mô tả quan hệ; nó không tự tạo logic kết hợp ở Spring Security.

## 12. Security Requirement toàn cục và theo operation

OpenAPI cho phép khai báo security ở hai cấp:

| Vị trí | Phạm vi |
|---|---|
| Root security | Áp dụng mặc định cho các operation trong document |
| Operation security | Ghi đè yêu cầu bảo mật kế thừa ở cấp document |

Ví dụ tài liệu có API key mặc định nhưng endpoint health công khai:

~~~yaml
security:
  - ApiKeyHeaderAuth: []

paths:
  /api/products:
    get:
      summary: Danh sách sản phẩm
      responses:
        "200":
          description: Thành công

  /api/health:
    get:
      summary: Kiểm tra sức khỏe
      security: []
      responses:
        "200":
          description: Dịch vụ hoạt động
~~~

Operation GET /api/products kế thừa API key. Operation GET /api/health có security: [] nên không yêu cầu scheme.

Nếu chỉ bỏ security ở operation health mà không ghi danh sách rỗng, nó vẫn kế thừa yêu cầu toàn cục. Hãy mở /v3/api-docs để kiểm tra trường security ở root và ở operation.

## 13. Swagger UI Authorize và API key

Khi OpenAPI document có Security Scheme và Security Requirement, Swagger UI có thể tạo nút **Authorize**. Với API key header hoặc query, người dùng nhập giá trị key trong giao diện; Swagger UI thêm credential vào request khi gọi operation được bảo vệ.

Một quy trình kiểm tra:

1. Mở Swagger UI.
2. Chọn Authorize.
3. Nhập API key thử nghiệm được cấp cho môi trường development.
4. Xác nhận giao diện hiển thị trạng thái đã authorize.
5. Gọi operation cần key bằng Try it out.
6. Mở Developer Tools → Network để kiểm tra header hoặc query được gửi.
7. Gọi một operation public để xác nhận không gửi key ngoài phạm vi dự kiến.
8. Chọn Logout/Authorize lại hoặc tải lại trang theo cách phù hợp để xóa credential thử nghiệm.

Không đưa API key thật vào mã JavaScript, file OpenAPI, ví dụ công khai hoặc source control. Swagger UI là giao diện phía client; bất kỳ ai có quyền truy cập trình duyệt đều có thể quan sát credential mà họ đã nhập hoặc request được gửi.

Với cookie scheme, hãy kiểm tra khả năng gửi cookie thực tế của browser thay vì giả định Authorize sẽ đặt được header Cookie. Cookie thường cần được thiết lập bởi server hoặc một luồng đăng nhập phù hợp.

## 14. CORS, cookie và CSRF

Khi Swagger UI và API chạy khác origin, trình duyệt áp dụng CORS. Nếu request có header API key tùy chỉnh như X-API-Key, browser có thể gửi preflight OPTIONS trước request thật.

Backend cần cho phép:

- Origin của trang Swagger UI.
- HTTP method cần dùng.
- Header X-API-Key hoặc header xác thực tương ứng.
- Credential nếu ứng dụng thực sự dùng cookie cross-origin.
- Expose response header nếu JavaScript cần đọc header đó.

Với cookie authentication, CORS phải cho phép credential và khai báo origin cụ thể; không thể dùng wildcard origin theo cách thông thường cùng credential. Cookie cross-site còn chịu ảnh hưởng của SameSite và chính sách chặn third-party cookie của browser.

Cookie được browser tự động gửi có thể tạo rủi ro **Cross-Site Request Forgery (CSRF)**. Nếu API dùng cookie để xác thực request thay đổi dữ liệu, cần áp dụng biện pháp CSRF phù hợp như token chống CSRF, kiểm tra Origin/Referer hoặc chính sách SameSite theo mô hình ứng dụng. Chỉ khai báo in: cookie trong OpenAPI không bảo vệ endpoint khỏi CSRF.

## 15. API key và các nguyên tắc bảo vệ ở backend

API key thường là credential có quyền truy cập theo client hoặc tích hợp. Backend cần có cơ chế kiểm tra độc lập với tài liệu:

- Sinh key đủ độ ngẫu nhiên và entropy.
- Cấp key riêng cho từng ứng dụng hoặc đối tác.
- Lưu trữ an toàn; cân nhắc chỉ lưu hash nếu quy trình xác minh cho phép.
- Giới hạn scope, tenant, quota hoặc danh sách API được phép.
- Hỗ trợ thu hồi và luân chuyển key.
- Theo dõi lần sử dụng bất thường và giới hạn tốc độ.
- Không ghi toàn bộ key vào log.
- Dùng HTTPS để bảo vệ credential trên đường truyền.
- Không nhúng secret dài hạn vào ứng dụng frontend công khai.

Nếu dùng Spring Security, API key thường được xác minh trong filter hoặc authentication provider tùy kiến trúc. Khi key hợp lệ, ứng dụng tạo Authentication phù hợp; khi thiếu hoặc sai key, trả status và response lỗi theo chính sách API.

OpenAPI Security Scheme chỉ giúp client biết cách trình bày credential. Nó không xác minh key, không cấp quyền và không thay thế filter chain.

## 16. Các lỗi thường gặp khi mô tả API key

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI không có nút Authorize | Có Security Scheme nhưng operation chưa có Security Requirement |
| Nhập key nhưng request không gửi header | Scheme dùng sai in, sai paramName hoặc operation không áp dụng scheme |
| Backend báo thiếu key | Tên header/query/cookie trong tài liệu khác tên backend đọc |
| API key xuất hiện thành query parameter nghiệp vụ | Đã dùng Parameter Object thay cho Security Scheme |
| Endpoint public vẫn bị khóa trong Swagger UI | Operation chưa override global security bằng security: [] |
| Mọi endpoint đều bị yêu cầu key ngoài ý muốn | Security Requirement được đặt ở root trong khi document có endpoint public |
| Cookie không được browser gửi | Domain, path, Secure, SameSite, credentials hoặc chính sách browser không phù hợp |
| Swagger UI không tự đặt được Cookie header | Browser cấm JavaScript đặt forbidden request header Cookie |
| Request header API key bị CORS chặn | Preflight không cho phép origin, method hoặc header |
| Key bị lộ trong log | API dùng query string hoặc hệ thống log không che credential |
| Hai scheme tạo logic xác thực sai | Nhầm OR giữa nhiều Security Requirement Objects với AND trong cùng object |
| Tài liệu có scheme nhưng backend không kiểm tra | Mới khai báo OpenAPI, chưa triển khai xác thực ở runtime |

Khi gặp lỗi, kiểm tra lần lượt Security Scheme, Security Requirement, request trong Network tab, tên credential mà backend đọc và kết quả xác thực runtime.

## 17. Kiểm tra OpenAPI document và request thực tế

Sau khi cấu hình Springdoc, tải tài liệu:

~~~http
GET /v3/api-docs
~~~

Nếu ứng dụng có document group, kiểm tra endpoint của group tương ứng.

Với API key, xác minh:

1. components.securitySchemes có scheme cần thiết.
2. type là apiKey.
3. in đúng header, query hoặc cookie.
4. name trùng chính xác tên header, query parameter hoặc cookie mà backend đọc.
5. Root security áp dụng đúng phạm vi.
6. Operation public có security: [] nếu cần bỏ yêu cầu toàn cục.
7. Security Requirement OR/AND đúng với chính sách xác thực.
8. Swagger UI hiển thị scheme trong Authorize và gửi credential theo cách dự kiến.
9. Request thiếu key, key sai và key hợp lệ tạo response đúng status.
10. Log không ghi lại toàn bộ credential.

Có thể kiểm thử bằng MockMvc hoặc integration test cho các trường hợp thiếu key, key không hợp lệ, key đã thu hồi và key hợp lệ. Test OpenAPI xác minh hợp đồng; test HTTP xác minh backend thực thi bảo mật.

Không dùng API key thật trong fixture hoặc log kiểm thử. Hãy dùng key giả cho môi trường test và xóa credential khỏi Swagger UI sau khi hoàn thành kiểm tra.

## 18. Nguyên tắc lựa chọn API key location

Khi thiết kế API key cho Springdoc OpenAPI:

1. Ưu tiên header cho API mới, ví dụ X-API-Key.
2. Chỉ dùng query khi cần tương thích với API hoặc nền tảng đã yêu cầu.
3. Dùng cookie khi kiến trúc xác thực dựa trên cookie và có chính sách CSRF phù hợp.
4. Khai báo scheme bằng @SecurityScheme hoặc OpenAPI model.
5. Áp dụng bằng @SecurityRequirement ở đúng cấp document, controller hoặc operation.
6. Dùng security: [] cho operation public cần ghi đè bảo mật toàn cục.
7. Phân biệt Security Scheme với Parameter Object.
8. Hiểu quan hệ OR/AND giữa nhiều security requirement.
9. Không đưa key thật vào tài liệu, code frontend hoặc log.
10. Kiểm tra OpenAPI JSON, Swagger UI Network tab và backend authentication.

API key trong header, query và cookie đều có thể được mô tả bằng OpenAPI Security Scheme, nhưng mỗi vị trí có đặc tính khác nhau. Header thường phù hợp cho tích hợp API; query có nguy cơ lộ credential qua URL; cookie phụ thuộc chính sách trình duyệt và cần xử lý CSRF. Khi Security Scheme, Security Requirement và cơ chế xác thực backend thống nhất, Swagger UI có thể hướng dẫn client gửi key đúng cách mà tài liệu vẫn phản ánh chính xác phạm vi bảo vệ của API.

