# supportedSubmitMethods và giới hạn gọi thử từ giao diện

Swagger UI không chỉ hiển thị tài liệu OpenAPI mà còn cung cấp nút **Try it out** để người dùng nhập tham số, gửi request và xem response ngay trong trình duyệt. Trong môi trường phát triển, tính năng này giúp kiểm tra API nhanh. Với môi trường dùng chung hoặc production, việc cho phép gọi thử mọi HTTP method có thể tạo rủi ro khi người dùng vô tình thực hiện thao tác ghi, cập nhật hoặc xóa dữ liệu.

springdoc-openapi cung cấp cấu hình **supportedSubmitMethods** để kiểm soát những HTTP method mà Swagger UI được phép gửi qua Try it out. Có thể chỉ bật các method đọc dữ liệu, hoặc tắt toàn bộ thao tác gọi thử. Cấu hình này giới hạn khả năng tương tác của giao diện; quyền truy cập và tính an toàn của API vẫn phải được bảo vệ ở backend.

## 1. Try it out hoạt động như thế nào?

Trong Swagger UI, mỗi operation được hiển thị cùng HTTP method, path, mô tả, parameters, request body và responses. Khi người dùng chọn **Try it out**, giao diện mở các trường nhập dữ liệu và cho phép gửi request.

Một luồng gọi thử điển hình:

1. Người dùng mở Swagger UI và chọn operation.
2. Swagger UI đọc mô tả operation từ tài liệu OpenAPI.
3. Người dùng nhập path/query parameter, header hoặc request body.
4. Người dùng bấm Execute.
5. Trình duyệt gửi HTTP request tới server được xác định bởi OpenAPI servers hoặc cấu hình Swagger UI.
6. Swagger UI hiển thị status, headers và response body nhận được.

Ví dụ, một tài liệu có thể chứa:

~~~yaml
paths:
  /api/products:
    get:
      summary: Liệt kê sản phẩm
      responses:
        '200':
          description: Danh sách sản phẩm
    post:
      summary: Tạo sản phẩm
      responses:
        '201':
          description: Đã tạo sản phẩm
  /api/products/{id}:
    delete:
      summary: Xóa sản phẩm
      responses:
        '204':
          description: Đã xóa sản phẩm
~~~

Swagger UI có thể hiển thị cả GET, POST và DELETE. Nếu người dùng có quyền và server cho phép, Try it out có thể gửi các request tương ứng. Việc operation xuất hiện trong tài liệu không có nghĩa người dùng được phép thực hiện nó; authorization được quyết định ở backend.

## 2. supportedSubmitMethods là gì?

supportedSubmitMethods là cấu hình của Swagger UI, được springdoc-openapi đưa vào cấu hình giao diện. Giá trị là danh sách HTTP method được phép sử dụng qua nút Try it out.

Các method thường gặp:

- get
- post
- put
- delete
- patch
- options
- head
- trace

Khi cấu hình, tên method nên viết thường và khớp với method trong OpenAPI. Nếu danh sách chỉ có get và head, Swagger UI cho phép gọi thử các operation GET và HEAD; các method khác không có nút gọi thử tương ứng.

Theo mặc định của Swagger UI, các method phổ biến đều được hỗ trợ. Nếu muốn thay đổi chính sách, cần khai báo danh sách rõ ràng thay vì dựa vào mặc định có thể khác giữa phiên bản hoặc cấu hình.

Cấu hình này tác động tới giao diện Swagger UI. Nó không thay đổi HTTP method được khai báo trong OpenAPI, không xóa operation khỏi tài liệu và không ngăn một client khác gọi trực tiếp endpoint.

## 3. Chỉ cho phép gọi thử các method đọc dữ liệu

Một lựa chọn thường dùng cho môi trường demo hoặc tài liệu production là chỉ bật các method đọc dữ liệu. Ví dụ, chỉ cho phép GET:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
~~~

Nếu API có endpoint HEAD để kiểm tra metadata hoặc tồn tại tài nguyên, có thể bật thêm:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - head
~~~

Cấu hình tương đương trong application.properties:

~~~properties
springdoc.swagger-ui.supportedSubmitMethods=get,head
~~~

Sau khi cấu hình, Swagger UI vẫn hiển thị operation POST, PUT, PATCH và DELETE trong tài liệu. Tuy nhiên, các operation này không được cung cấp khả năng Execute qua Try it out.

Điều này hữu ích khi muốn người dùng đọc hợp đồng API, xem schema và response mẫu, đồng thời giảm nguy cơ thao tác ghi dữ liệu ngay từ giao diện tài liệu.

Chỉ bật GET/HEAD không bảo đảm request đọc dữ liệu hoàn toàn vô hại. Một endpoint GET được thiết kế sai vẫn có thể gây side effect. Backend cần tuân thủ ngữ nghĩa HTTP và không thực hiện thay đổi dữ liệu chỉ vì nhận GET.

## 4. Tắt Try it out cho tất cả HTTP method

Để tắt hoàn toàn khả năng gửi request từ Swagger UI, cấu hình danh sách rỗng:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods: []
~~~

Danh sách rỗng có nghĩa không method nào được bật cho Try it out. Người dùng vẫn có thể xem:

- Danh sách endpoint.
- HTTP method và path.
- Summary, description và tags.
- Query/path/header parameters.
- Request body schema.
- Response schema và mã trạng thái.
- Security scheme và mô tả xác thực.

Giao diện tài liệu vẫn hữu ích cho việc tra cứu hợp đồng, nhưng không còn cung cấp nút Execute để gửi request.

Cấu hình YAML với danh sách rỗng là cách thể hiện rõ ràng. Nếu dự án chỉ dùng application.properties, hãy xác minh cách binder của phiên bản Spring Boot/springdoc đang dùng biểu diễn danh sách rỗng; không mặc định một giá trị chuỗi trống sẽ luôn được chuyển thành list rỗng. Nếu file cấu hình, biến môi trường hoặc config server ghi đè giá trị, kết quả runtime có thể khác với nội dung application.yml.

## 5. Bật một tập method cụ thể

Có thể cho phép một tập method theo chính sách của môi trường. Ví dụ môi trường thử nghiệm cho phép GET, POST và PATCH:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
      - patch
~~~

Môi trường staging có thể cho phép thêm PUT nhưng vẫn tắt DELETE:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
      - put
      - patch
~~~

Trong application.properties:

~~~properties
springdoc.swagger-ui.supportedSubmitMethods=get,post,put,patch
~~~

Đây là chính sách ở mức HTTP method, áp dụng cho tất cả operation cùng method được hiển thị trong giao diện. Cấu hình không phân biệt endpoint nào là an toàn hoặc nguy hiểm trong cùng một method.

Ví dụ, nếu bật POST, mọi operation POST trong tài liệu đều có thể hiển thị Try it out, kể cả endpoint tạo đơn hàng, gửi thanh toán hoặc kích hoạt tác vụ. Hãy xem xét danh sách operation thực tế trước khi bật một method có khả năng thay đổi dữ liệu.

## 6. Cấu hình theo môi trường

Chính sách gọi thử thường khác nhau giữa local, development, staging và production. Có thể dùng Spring profile để đặt cấu hình riêng.

application.yml:

~~~yaml
spring:
  profiles:
    active: dev

springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
      - put
      - patch
      - delete
~~~

application-dev.yml:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
      - put
      - patch
      - delete
~~~

application-prod.yml:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - head
~~~

Khi chạy với profile production:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Swagger UI ở production chỉ cho phép gọi thử GET và HEAD. Tài liệu OpenAPI vẫn có thể chứa các operation ghi/xóa để client tham khảo.

Cấu hình mẫu ở trên minh họa chính sách theo profile. Trong dự án thật, tránh đặt profile active mặc định trong application.yml nếu deployment đã quản lý profile qua biến môi trường hoặc tham số khởi chạy. Điều quan trọng là xác định rõ nguồn cấu hình cuối cùng được Spring Boot nạp.

## 7. Tên thuộc tính YAML và properties

Spring Boot hỗ trợ relaxed binding, vì vậy cấu hình YAML có thể viết theo kebab-case:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
~~~

Trong application.properties, dùng tên thuộc tính springdoc:

~~~properties
springdoc.swagger-ui.supportedSubmitMethods=get,post
~~~

Một số điểm cần chú ý:

- YAML dùng danh sách để thể hiện từng method rõ ràng.
- Properties có thể dùng chuỗi phân tách bằng dấu phẩy.
- Tên method viết thường để phù hợp với cấu hình Swagger UI.
- Không thêm khoảng trắng hoặc ký tự phân tách sai vào tên method.
- Không khai báo cùng một thuộc tính ở nhiều nguồn cấu hình với các giá trị khó kiểm soát.
- Kiểm tra profile, environment variable, command-line argument và config server nếu giá trị không như mong đợi.

Tên property và cách bind cần được đối chiếu với phiên bản springdoc trong dự án. Nếu ứng dụng đang dùng một major version cũ, hãy kiểm tra reference documentation tương ứng thay vì suy ra chỉ từ ví dụ của phiên bản mới.

## 8. supportedSubmitMethods khác tryItOutEnabled

Hai cấu hình có tên gần nhau nhưng mục đích khác nhau:

| Cấu hình | Vai trò |
|---|---|
| supportedSubmitMethods | Danh sách HTTP method được phép gửi bằng Try it out |
| tryItOutEnabled | Bật Try it out mặc định cho các operation, tùy phiên bản Swagger UI |

supportedSubmitMethods quyết định method nào được phép gọi thử. tryItOutEnabled bật Try it out mặc định cho các operation; nó không tạo allowlist method và không thay thế supportedSubmitMethods.

Ví dụ:

~~~yaml
springdoc:
  swagger-ui:
    try-it-out-enabled: true
    supported-submit-methods:
      - get
~~~

Cấu hình này bật Try it out mặc định cho các operation mà Swagger UI hỗ trợ, nhưng danh sách method vẫn chỉ cho phép GET được gửi.

Nếu danh sách supportedSubmitMethods rỗng, việc bật tryItOutEnabled không làm các method xuất hiện trở lại. Hai thuộc tính cần được xem xét cùng nhau khi thiết kế trải nghiệm.

Hành vi và tên cấu hình có thể thay đổi theo phiên bản Swagger UI được springdoc đóng gói. Hãy xác minh bằng giao diện và cấu hình runtime thực tế.

## 9. supportedSubmitMethods không phải cơ chế bảo mật backend

Đây là giới hạn quan trọng nhất của cấu hình.

Nếu production chỉ bật GET trong Swagger UI, client vẫn có thể gửi POST, PUT hoặc DELETE bằng:

- curl.
- Postman.
- HTTP client trong ứng dụng.
- JavaScript chạy ngoài Swagger UI.
- Một công cụ hoặc script khác.

supportedSubmitMethods chỉ ẩn hoặc vô hiệu hóa khả năng gọi thử từ giao diện Swagger UI. Nó không phải firewall, authorization rule, CSRF protection hay server-side allowlist.

Nếu endpoint DELETE cần bị cấm với người dùng thông thường, phải kiểm soát ở backend bằng Spring Security, phân quyền method, service authorization hoặc API gateway. Nếu endpoint không được triển khai, controller không nên ánh xạ method đó.

Không dùng supportedSubmitMethods như biện pháp duy nhất để bảo vệ dữ liệu production.

## 10. Phân biệt ẩn thao tác với ẩn tài liệu

Có ba quyết định khác nhau:

1. **Giữ operation trong OpenAPI nhưng tắt Try it out:** người đọc vẫn thấy endpoint, schema và response, nhưng không thể gửi request từ Swagger UI.
2. **Ẩn operation khỏi tài liệu:** operation không xuất hiện trong tài liệu được công bố. Có thể dùng cơ chế như @Hidden hoặc lọc operation theo group khi phù hợp.
3. **Chặn operation ở backend:** request thực tế bị từ chối theo security rule, authorization, routing hoặc gateway policy.

Ba quyết định này không thay thế cho nhau. Nếu muốn đối tác đọc endpoint nhưng không thử thao tác ghi, có thể giữ operation trong tài liệu và giới hạn supportedSubmitMethods. Nếu endpoint nội bộ không được công bố, hãy kiểm soát tài liệu. Nếu endpoint cần được bảo vệ, hãy kiểm soát runtime.

## 11. Rủi ro khi cho phép gọi thử method ghi dữ liệu

POST, PUT, PATCH và DELETE thường có thể làm thay đổi trạng thái hệ thống. Khi mở Try it out trên môi trường dùng dữ liệu thật, người dùng có thể vô tình:

- Tạo đơn hàng hoặc giao dịch trùng.
- Cập nhật thông tin khách hàng.
- Thay đổi trạng thái đơn hàng.
- Xóa tài nguyên.
- Gửi email hoặc kích hoạt tác vụ nền.
- Gọi dịch vụ thanh toán hoặc tích hợp bên ngoài.

Để giảm rủi ro:

- Chỉ bật method cần thiết trong môi trường tương ứng.
- Dùng tài khoản thử nghiệm với quyền tối thiểu.
- Dùng dữ liệu giả lập hoặc sandbox khi có thể.
- Yêu cầu xác nhận nghiệp vụ trước các thao tác không thể đảo ngược.
- Bảo vệ endpoint bằng authentication và authorization.
- Kiểm tra audit log cho thao tác thay đổi dữ liệu.
- Có cơ chế idempotency cho các request tạo giao dịch nếu phù hợp.

Không nên dựa vào giao diện để ngăn lỗi thao tác. Backend phải kiểm tra quyền và điều kiện nghiệp vụ trước khi thực hiện thay đổi.

## 12. CORS khi Swagger UI gọi API khác origin

Swagger UI thường được tải từ một origin, trong khi API server có thể ở origin khác. Ví dụ:

- Swagger UI: https://docs.example.com
- API: https://api.example.com

Khi trình duyệt gửi request cross-origin, chính sách CORS của server quyết định origin nào được phép truy cập và method/header nào được chấp nhận.

Nếu Try it out báo lỗi CORS, kiểm tra:

- Access-Control-Allow-Origin có cho phép origin của Swagger UI không?
- Access-Control-Allow-Methods có bao gồm method cần gọi không?
- Access-Control-Allow-Headers có cho phép Authorization, Content-Type hoặc header tùy chỉnh không?
- Request có phát sinh preflight OPTIONS không?
- Cấu hình CORS của Spring Security có được áp dụng đúng thứ tự không?

Ví dụ cấu hình Spring MVC CORS minh họa:

~~~java
@Configuration
class WebCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://docs.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
            .allowedHeaders("Authorization", "Content-Type", "X-Request-Id");
    }
}
~~~

Nếu dùng Spring Security, cần cấu hình CORS tích hợp với SecurityFilterChain và kiểm tra preflight request. Cấu hình CORS chỉ cho phép trình duyệt đọc response từ origin hợp lệ; nó không thay thế authentication hoặc authorization.

Không dùng wildcard origin kết hợp credential nếu chính sách bảo mật của ứng dụng không cho phép. Hãy chỉ khai báo các origin thực sự cần truy cập.

## 13. Authentication và authorization trong Try it out

Nếu operation yêu cầu bearer token, Swagger UI có thể cung cấp nút Authorize dựa trên security scheme trong OpenAPI. Người dùng nhập token rồi gửi request qua Try it out.

Ví dụ khai báo bearer scheme:

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

Operation được bảo vệ:

~~~java
@Operation(
    summary = "Lấy hồ sơ hiện tại",
    security = @SecurityRequirement(name = "bearerAuth")
)
@GetMapping("/api/me")
public ProfileResponse getProfile() {
    return profileService.current();
}
~~~

Cần phân biệt:

- OpenAPI security scheme giúp Swagger UI biết cách gửi credential.
- Authentication xác minh danh tính người gọi.
- Authorization quyết định người gọi có quyền thực hiện operation hay không.
- supportedSubmitMethods chỉ kiểm soát method có thể gọi qua Try it out.

Nếu người dùng nhập token không hợp lệ, backend vẫn phải trả 401. Nếu token hợp lệ nhưng thiếu quyền, backend phải trả 403 theo chính sách API. Không giả định Swagger UI đã ẩn method thì backend không cần kiểm tra quyền.

## 14. CSRF và cookie-based authentication

Nếu ứng dụng dùng session cookie hoặc xác thực dựa trên cookie, request thay đổi dữ liệu có thể chịu bảo vệ CSRF của Spring Security.

Khi Try it out gửi POST, PUT, PATCH hoặc DELETE, request có thể bị từ chối nếu thiếu CSRF token hợp lệ. Đây là hành vi bảo vệ runtime, không phải lỗi supportedSubmitMethods.

Hãy xác định cơ chế xác thực của API:

- Với bearer token gửi qua Authorization header, cách cấu hình CSRF có thể khác với ứng dụng session-based.
- Với cookie session, cần quản lý CSRF token và cookie theo đúng chính sách.
- Nếu Swagger UI chạy khác origin, CORS và cookie SameSite/credential policy cũng ảnh hưởng request.

Không tắt CSRF chỉ để làm nút Execute hoạt động. Hãy cấu hình bảo vệ phù hợp với mô hình xác thực và bề mặt tấn công của ứng dụng.

## 15. Kiểm tra cấu hình Swagger UI sau khi khởi động

Sau khi thay đổi application.yml hoặc application.properties, khởi động lại ứng dụng theo cấu hình môi trường cần kiểm tra.

Mở Swagger UI tại đường dẫn mặc định, thường là:

~~~text
http://localhost:8080/swagger-ui.html
~~~

Trong nhiều cấu hình, URL này chuyển hướng tới giao diện dưới /swagger-ui/index.html. Nếu dự án đã đổi springdoc.swagger-ui.path hoặc có context path, hãy dùng URL thực tế.

Kiểm tra:

1. Operation GET có nút Try it out không?
2. Operation POST có nút Try it out không?
3. Operation PUT/PATCH/DELETE có được phép thử theo danh sách không?
4. Khi danh sách rỗng, tất cả nút Execute có bị vô hiệu hóa không?
5. Tài liệu, schema và response vẫn hiển thị đầy đủ?
6. Cấu hình có đúng với profile đang chạy không?

Nếu kết quả không thay đổi, hãy kiểm tra cấu hình đã được nạp, profile, biến môi trường và cache trình duyệt. Thử tải lại trang không dùng cache để tránh nhìn thấy bundle hoặc config cũ.

## 16. Kiểm tra Swagger UI config endpoint

springdoc thường công bố cấu hình Swagger UI qua endpoint cấu hình, mặc định là:

~~~text
GET /v3/api-docs/swagger-config
~~~

Có thể kiểm tra bằng curl:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/swagger-config
~~~

Tùy phiên bản springdoc và cách serialize cấu hình, response có thể chứa các thiết lập UI như URL tài liệu, config URL, OAuth redirect và danh sách submit method. Tìm thuộc tính tương ứng để xác minh giá trị được backend cung cấp cho giao diện.

Nếu config endpoint không hiển thị thuộc tính theo cách mong đợi, điều đó chưa đủ để kết luận cấu hình bị bỏ qua. Hãy kiểm tra tài liệu cấu hình của phiên bản đang dùng và quan sát hành vi thật trong Swagger UI.

Không sửa trực tiếp file JavaScript bundle được springdoc phục vụ chỉ để thay danh sách method. Cấu hình Spring Boot hoặc custom Swagger UI config phù hợp sẽ dễ duy trì hơn khi nâng phiên bản.

## 17. Phân biệt lỗi cấu hình với lỗi gọi API

Khi Try it out không hoạt động, xác định lỗi thuộc giao diện hay backend:

| Hiện tượng | Hướng kiểm tra |
|---|---|
| Không có nút Try it out | supportedSubmitMethods không bao gồm method, hoặc cấu hình UI khác đã vô hiệu hóa |
| Nút có nhưng Execute bị lỗi | Xem console và Network của trình duyệt |
| Browser báo CORS | Kiểm tra CORS, preflight và origin |
| Response 401 | Kiểm tra token, security scheme và authentication |
| Response 403 | Kiểm tra authorization hoặc CSRF |
| Response 404 | Kiểm tra server URL, context path và operation path |
| Response 405 | Kiểm tra HTTP method được controller/gateway hỗ trợ |
| Response 415 | Kiểm tra Content-Type và consumes |
| Response 400 | Kiểm tra request parameter, body và validation |
| Swagger UI vẫn hiện method đã tắt | Kiểm tra cấu hình runtime, profile, config endpoint và cache |

Nút Try it out bị ẩn không có nghĩa endpoint không tồn tại. Ngược lại, nút hiện ra cũng không đảm bảo request sẽ được server chấp nhận.

## 18. Kiểm tra server vẫn bảo vệ endpoint

Sau khi giới hạn supportedSubmitMethods, vẫn cần test backend độc lập. Ví dụ, nếu Swagger UI chỉ bật GET, gửi request DELETE trực tiếp tới endpoint cần được đánh giá theo security policy thực tế.

~~~bash
curl -i -X DELETE http://localhost:8080/api/products/123
~~~

Kết quả mong đợi phụ thuộc authorization và thiết kế API:

- Có thể trả 401 nếu chưa xác thực.
- Có thể trả 403 nếu không đủ quyền.
- Có thể trả 404 nếu tài nguyên hoặc route không tồn tại.
- Có thể trả 204 nếu người gọi có quyền và thao tác xóa thành công.

Nếu policy yêu cầu người dùng hiện tại không được xóa, test phải chứng minh backend trả 403 hoặc phản hồi phù hợp ngay cả khi request được gửi ngoài Swagger UI.

Không dùng một status code cố định làm kỳ vọng cho mọi ứng dụng. Hãy xác định quyền của principal, trạng thái tài nguyên và policy đang kiểm tra.

## 19. Chính sách gợi ý theo môi trường

Có thể xây dựng chính sách như sau:

| Môi trường | supportedSubmitMethods gợi ý | Mục đích |
|---|---|---|
| Local | GET, POST, PUT, PATCH, DELETE | Phát triển và kiểm thử với dữ liệu local |
| Development | GET, POST, PUT, PATCH | Kiểm tra luồng ghi trên dữ liệu thử nghiệm |
| Staging | GET, POST, PUT, PATCH | UAT có kiểm soát; chỉ bật DELETE khi cần |
| Production | GET hoặc danh sách rỗng | Tra cứu tài liệu, giảm thao tác ghi từ UI |

Đây chỉ là chính sách tham khảo. Nếu production cần cho phép đối tác thử endpoint trong sandbox, hãy cung cấp môi trường sandbox riêng với dữ liệu và quyền hạn phù hợp.

Một số nhóm có thể tắt toàn bộ Try it out ở production nhưng vẫn công bố OpenAPI JSON cho client generator. Việc phân phối spec và việc cho phép gửi request là hai quyết định độc lập.

## 20. Những lỗi thường gặp

| Sai sót | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ supportedSubmitMethods chặn API trên server | Client ngoài Swagger UI vẫn gọi được endpoint | Bảo vệ backend bằng Security/gateway |
| Để mặc định mọi method ở production | Người xem tài liệu có thể thử thao tác ghi/xóa | Chỉ bật method thực sự cần |
| Dùng sai chữ hoa/chữ thường | Giao diện không áp dụng đúng method mong muốn | Dùng tên method viết thường |
| Khai báo danh sách rỗng sai cú pháp YAML | Binder có thể không nhận giá trị rỗng như dự kiến | Dùng danh sách rỗng YAML và xác minh runtime |
| Chỉ sửa application.yml nhưng profile khác ghi đè | UI vẫn hiển thị cấu hình cũ | Kiểm tra nguồn cấu hình cuối cùng |
| Nhầm tryItOutEnabled với supportedSubmitMethods | Kỳ vọng sai về nút Execute | Kiểm tra riêng trạng thái mặc định và danh sách method |
| Tắt method ghi nhưng quên CORS | GET hoặc method được bật vẫn có thể bị browser chặn | Cấu hình CORS đúng origin/method |
| Tắt CSRF để sửa lỗi Execute | Làm yếu bảo vệ session-based app | Xử lý CSRF token đúng mô hình xác thực |
| Ẩn operation thay vì chỉ tắt Try it out | Người đọc không còn thấy hợp đồng endpoint | Chọn đúng cơ chế: UI submit, ẩn tài liệu hoặc backend security |
| Tin rằng GET luôn an toàn | Endpoint GET có side effect vẫn có thể bị gọi | Thiết kế GET chỉ đọc và kiểm tra runtime |

## 21. Checklist cấu hình supportedSubmitMethods

- [ ] Đã xác định method nào cần gọi thử trong từng môi trường.
- [ ] supportedSubmitMethods chỉ chứa HTTP method cần thiết.
- [ ] Tên method được viết thường.
- [ ] Đã biết danh sách rỗng dùng để tắt Try it out.
- [ ] Đã phân biệt supportedSubmitMethods với tryItOutEnabled.
- [ ] Đã kiểm tra cấu hình YAML/properties theo phiên bản springdoc.
- [ ] Đã xác minh profile và nguồn cấu hình cuối cùng.
- [ ] Swagger UI vẫn hiển thị operation và schema cần công bố.
- [ ] Đã kiểm tra nút Try it out trên từng method đại diện.
- [ ] CORS cho phép đúng origin và method nếu UI khác origin.
- [ ] Authentication, authorization và CSRF vẫn được cấu hình phù hợp.
- [ ] Backend test chứng minh method bị hạn chế vẫn không thể vượt qua security policy.
- [ ] Đã kiểm tra cấu hình Swagger UI sau khi khởi động lại ứng dụng.

## 22. Nguồn tra cứu

- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Swagger UI – Try it out](https://swagger.io/docs/open-source-tools/swagger-ui/usage/overview/)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Security – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Framework – CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)

supportedSubmitMethods giúp kiểm soát HTTP method được phép gọi thử trong Swagger UI. Đây là thiết lập trải nghiệm và giảm thao tác nhầm từ giao diện; API vẫn cần xác thực, phân quyền, CSRF/CORS và kiểm tra nghiệp vụ ở runtime. Sau khi thay đổi cấu hình, hãy xác minh Swagger UI, config endpoint và phản hồi thực tế của backend trước khi áp dụng cho môi trường dùng chung.
