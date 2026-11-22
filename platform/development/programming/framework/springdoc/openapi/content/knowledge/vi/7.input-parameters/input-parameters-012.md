# Ẩn tham số hạ tầng như principal hoặc thông tin request

Một controller Spring Boot có thể nhận các đối tượng do framework cung cấp để xử lý request, chẳng hạn người dùng đang đăng nhập, thông tin xác thực, servlet request hoặc response. Những đối tượng này phục vụ việc thực thi endpoint, nhưng không nhất thiết là dữ liệu mà client phải gửi. Nếu chúng xuất hiện như tham số đầu vào trong OpenAPI, Swagger UI có thể hiển thị những trường không có ý nghĩa với người gọi API và client được sinh từ đặc tả có thể hiểu sai hợp đồng.

Với **springdoc-openapi**, có thể ẩn một tham số khỏi tài liệu bằng **@Parameter(hidden = true)**. Springdoc cũng tự loại một số kiểu tham số đặc biệt của Spring MVC, ví dụ **Principal**, **Locale**, **HttpServletRequest** và **HttpServletResponse**. Tuy vậy, tham số tùy biến hoặc principal được đưa vào bằng Spring Security có thể cần khai báo ẩn tường minh.

Điều quan trọng là phân biệt dữ liệu nội bộ do framework inject với tham số thực sự thuộc hợp đồng HTTP. Một header do client gửi vẫn cần được mô tả dù controller đọc nó thông qua **HttpServletRequest**.

## 1. Nhận diện tham số hạ tầng

Tham số hạ tầng là dữ liệu hoặc đối tượng được Spring, servlet container, Spring Security hay một argument resolver cung cấp trong lúc xử lý request. Chúng thường không phải field mà client cần nhập trong Swagger UI.

| Kiểu tham số | Nguồn cung cấp | Vai trò trong controller |
| --- | --- | --- |
| **Principal** | Servlet container hoặc cơ chế xác thực | Danh tính của người gọi |
| **Authentication** | Spring Security | Principal, authorities và trạng thái xác thực |
| **@AuthenticationPrincipal** | Spring Security | Lấy principal hiện tại hoặc một kiểu principal tùy biến |
| **HttpServletRequest** | Servlet container | Đọc header, URI, session, request attribute và thông tin HTTP |
| **HttpServletResponse** | Servlet container | Ghi header, cookie hoặc điều khiển response |
| **Locale** | Cơ chế locale của Spring hoặc request | Xác định ngôn ngữ hoặc vùng định dạng |
| **HttpSession** | Servlet container | Truy cập session của người dùng |
| Kiểu context tùy biến | HandlerMethodArgumentResolver hoặc lớp tích hợp | Cung cấp tenant, người dùng hiện tại hoặc request context |

Springdoc mặc định loại một số tham số đặc biệt mà Spring MVC hỗ trợ inject khỏi tài liệu. Danh sách được tài liệu FAQ nêu rõ gồm **Principal**, **Locale**, **HttpServletRequest**, **HttpServletResponse** và các kiểu injectable khác. Khi thêm Spring Security hoặc một argument resolver riêng, không nên giả định mọi kiểu tùy biến đều tự động được loại khỏi OpenAPI.

Hãy tự hỏi hai điều trước khi ẩn tham số:

1. Client có phải gửi giá trị này trong request không?
2. Giá trị có phải một phần của hợp đồng API mà client cần biết không?

Nếu câu trả lời cho cả hai đều là không, tham số thường là chi tiết hạ tầng và có thể ẩn khỏi tài liệu. Nếu client cần truyền giá trị, phải mô tả nó dù controller đang đọc giá trị đó từ một đối tượng request tổng quát.

## 2. Dùng @Parameter(hidden = true) cho một tham số

Annotation **@Parameter** thuộc package **io.swagger.v3.oas.annotations**. Đặt **hidden = true** trên đúng tham số muốn loại khỏi OpenAPI:

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/profile")
    ProfileView currentProfile(
        @Parameter(hidden = true)
        @AuthenticationPrincipal AppPrincipal principal
    ) {
        return profileService.findByUserId(principal.userId());
    }
}
~~~

Trong ví dụ, **AppPrincipal** là kiểu principal do ứng dụng định nghĩa. Spring Security lấy principal từ **SecurityContext** và inject vào tham số nhờ **@AuthenticationPrincipal**. Client không cần gửi một field có tên principal trong request body hoặc query string; danh tính đã được xác định từ cơ chế xác thực. Vì vậy, tham số này được đánh dấu ẩn.

Có thể ẩn thêm đối tượng request nếu muốn thể hiện rõ ý định trong mã nguồn:

~~~java
import jakarta.servlet.http.HttpServletRequest;

@GetMapping("/api/profile/details")
ProfileDetailsView details(
    @Parameter(hidden = true)
    @AuthenticationPrincipal AppPrincipal principal,

    @Parameter(hidden = true)
    HttpServletRequest request
) {
    String traceId = request.getHeader("X-Trace-Id");
    return profileService.loadDetails(principal.userId(), traceId);
}
~~~

Springdoc vốn đã tự bỏ qua một số kiểu servlet phổ biến. Annotation tường minh giúp người đọc controller nhận ra tham số chỉ phục vụ nội bộ và hữu ích với các kiểu tùy biến hoặc trường hợp phiên bản/cấu hình khiến tham số xuất hiện ngoài dự kiến.

**@Parameter(hidden = true)** chỉ thay đổi tài liệu OpenAPI. Nó không xóa tham số khỏi chữ ký phương thức, không thay đổi cách Spring inject giá trị và không bỏ qua logic xác thực hoặc phân quyền.

## 3. Principal, Authentication và @AuthenticationPrincipal

Ba cách lấy danh tính người gọi thường gặp có ý nghĩa khác nhau:

- **Principal** là abstraction của danh tính đang được xác thực. Nó có thể được Spring MVC inject trực tiếp.
- **Authentication** là đối tượng của Spring Security chứa principal, authorities và trạng thái xác thực.
- **@AuthenticationPrincipal** lấy principal hiện tại hoặc một giá trị được chọn từ principal theo cấu hình annotation.

Ví dụ controller nhận **Authentication**:

~~~java
import org.springframework.security.core.Authentication;

@GetMapping("/api/account")
AccountView account(
    @Parameter(hidden = true) Authentication authentication
) {
    AppPrincipal principal = (AppPrincipal) authentication.getPrincipal();
    return accountService.findByUserId(principal.userId());
}
~~~

Ví dụ nhận **Principal**:

~~~java
import java.security.Principal;

@GetMapping("/api/account/summary")
AccountSummary summary(
    @Parameter(hidden = true) Principal principal
) {
    return accountService.summaryFor(principal.getName());
}
~~~

Các tham số trên biểu diễn ngữ cảnh xác thực đã được server thiết lập. Client tương tác với cơ chế xác thực thông qua cookie session, bearer token hoặc một cơ chế bảo mật khác được công bố trong hợp đồng.

Không đưa principal, đối tượng Authentication hoặc giá trị nội bộ của SecurityContext thành query parameter hay request body chỉ để Swagger UI hiển thị chúng. Việc đó biến chi tiết triển khai thành một phần của API và có thể gây hiểu lầm rằng client được phép tự chọn danh tính người dùng.

## 4. Ẩn HttpServletRequest và HttpServletResponse

**HttpServletRequest** cho phép controller đọc thông tin request tổng quát. **HttpServletResponse** cho phép ghi header, cookie hoặc điều khiển response. Bản thân các đối tượng này không phải tham số HTTP đơn lẻ.

Ví dụ:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@GetMapping("/api/download-link")
DownloadLinkView createDownloadLink(
    @Parameter(hidden = true) HttpServletRequest request,
    @Parameter(hidden = true) HttpServletResponse response
) {
    String requestId = request.getHeader("X-Request-Id");
    response.setHeader("X-Processed-By", "document-service");
    return documentService.createLink(requestId);
}
~~~

Trong ứng dụng Spring Boot dùng servlet stack hiện đại, các lớp này thuộc **jakarta.servlet.http**. Ứng dụng Spring Boot 2 cũ có thể dùng namespace **javax.servlet.http**. Chọn import theo thế hệ Spring Boot và servlet API mà dự án sử dụng.

Springdoc thường bỏ qua **HttpServletRequest** và **HttpServletResponse** mặc định. Nếu chúng xuất hiện trong **parameters** của operation, kiểm tra xem có annotation hoặc wrapper tùy biến nào khiến springdoc diễn giải chúng thành dữ liệu API hay không. Có thể đánh dấu tham số ẩn để làm rõ ý định.

Với Spring WebFlux, controller có thể nhận các đối tượng như **ServerWebExchange**, **ServerHttpRequest** hoặc **ServerHttpResponse**. Đây là các abstraction của reactive stack, không phải tham số nghiệp vụ thông thường. Nếu chúng bị đưa vào danh sách parameter của OpenAPI, đánh dấu ẩn bằng **@Parameter(hidden = true)** và kiểm tra tài liệu của endpoint WebFlux sau khi sinh.

## 5. Không ẩn header hoặc cookie thuộc hợp đồng API

Một điểm dễ nhầm là controller đọc dữ liệu thông qua **HttpServletRequest** nên người viết có thể cho rằng mọi thông tin đọc từ request đều là nội bộ. Cần phân biệt:

- **Request object** là đối tượng hạ tầng do servlet container inject.
- **Header, cookie, query parameter hoặc path parameter** có thể là đầu vào công khai do client gửi.

Ví dụ, nếu client phải gửi **X-Tenant-Id** để chọn tenant, header đó là một phần của hợp đồng. Có thể bind trực tiếp bằng **@RequestHeader**:

~~~java
@GetMapping("/api/reports")
ReportView report(
    @RequestHeader("X-Tenant-Id") String tenantId
) {
    return reportService.createForTenant(tenantId);
}
~~~

Springdoc có thể suy ra đây là header parameter. Nếu controller cần giữ **HttpServletRequest** để đọc header, hãy khai báo header công khai bằng metadata OpenAPI:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.Parameter;

@GetMapping("/api/reports")
@Operation(parameters = {
    @Parameter(
        name = "X-Tenant-Id",
        in = ParameterIn.HEADER,
        required = true,
        description = "Mã tenant do client yêu cầu",
        example = "tenant-42"
    )
})
ReportView report(
    @Parameter(hidden = true) HttpServletRequest request
) {
    String tenantId = request.getHeader("X-Tenant-Id");
    return reportService.createForTenant(tenantId);
}
~~~

Trong trường hợp này, đối tượng **HttpServletRequest** được ẩn nhưng **X-Tenant-Id** vẫn xuất hiện trong OpenAPI như một header parameter. Hãy xác thực và phân quyền tenant ở server; việc công bố header không có nghĩa client được phép truy cập mọi tenant.

### Authorization là trường hợp đặc biệt

Không mô tả header **Authorization** bằng một **@Parameter(in = HEADER)** thông thường. OpenAPI có cơ chế security scheme dành riêng cho xác thực. Với bearer token, định nghĩa security scheme và gắn requirement vào operation:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {}
~~~

~~~java
@Operation(
    summary = "Lấy hồ sơ hiện tại",
    security = @SecurityRequirement(name = "bearerAuth")
)
@GetMapping("/api/profile")
ProfileView currentProfile(
    @Parameter(hidden = true)
    @AuthenticationPrincipal AppPrincipal principal
) {
    return profileService.findByUserId(principal.userId());
}
~~~

Swagger UI sẽ hiểu endpoint cần cơ chế bearer authentication đã định nghĩa. Client nhập hoặc cấp token qua chức năng Authorize; tài liệu không cần tạo một field Authorization header riêng trong danh sách parameters. Nếu API dùng OAuth2 hoặc OpenID Connect, hãy mô tả flow tương ứng bằng security scheme phù hợp.

Cookie xác thực cũng cần được phân biệt với cookie nghiệp vụ. Nếu cookie session được dùng làm cơ chế bảo mật, mô tả security scheme dạng **apiKey** đặt trong **cookie** khi phù hợp với hợp đồng OpenAPI. Nếu cookie như **language** hoặc **viewMode** là dữ liệu tùy chọn do client gửi, hãy mô tả nó như cookie parameter thay vì ẩn.

## 6. Ẩn context tùy biến từ HandlerMethodArgumentResolver

Nhiều ứng dụng tạo argument resolver để inject context vào controller. Ví dụ, annotation **@CurrentTenant** có thể lấy tenant từ token hoặc header rồi cung cấp một đối tượng **TenantContext**:

~~~java
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CurrentTenant {}
~~~

Controller nhận context:

~~~java
@GetMapping("/api/tenant/summary")
TenantSummaryView summary(
    @Parameter(hidden = true)
    @CurrentTenant TenantContext tenantContext
) {
    return tenantService.summary(tenantContext.tenantId());
}
~~~

**TenantContext** được resolver tạo ra trong server, nên client không gửi trực tiếp object này. Nếu client cần chỉ định tenant qua header, query hoặc token claim, mô tả đúng cơ chế đầu vào đó trong OpenAPI. Không biến **TenantContext** thành schema request chỉ vì nó xuất hiện trong chữ ký controller.

Nếu một kiểu context tùy biến được dùng ở nhiều controller, có thể tạo một quy ước trong nhóm phát triển: mọi tham số được resolver inject phải được đánh dấu **@Parameter(hidden = true)**, trừ khi tham số đó đại diện cho đầu vào HTTP công khai. Quy ước này giúp code review dễ nhận biết và tránh phụ thuộc vào suy luận mặc định của thư viện.

## 7. Phân biệt @Parameter, @Hidden và @Schema

Các annotation có tên gần nhau nhưng tác động lên những phần khác nhau của OpenAPI:

| Annotation | Tác dụng | Dùng khi |
| --- | --- | --- |
| **@Parameter(hidden = true)** | Ẩn một parameter của operation | Principal, request context hoặc custom resolver argument |
| **@Hidden** | Ẩn operation hoặc thành phần được hỗ trợ khỏi tài liệu | Endpoint nội bộ không công bố |
| **@Operation(hidden = true)** | Ẩn toàn bộ operation | Một handler không thuộc API công khai |
| **@Schema(hidden = true)** | Ẩn một thuộc tính hoặc schema element | Field nội bộ trong DTO không nên xuất hiện trong schema |

Không dùng **@Hidden** ở cấp controller chỉ để loại một tham số hạ tầng. Làm vậy có thể khiến toàn bộ endpoint biến mất khỏi tài liệu. Cũng không dùng **@Schema(hidden = true)** thay cho **@Parameter(hidden = true)** trên tham số phương thức; một bên điều khiển schema, bên kia điều khiển Parameter Object.

## 8. Kiểm tra tham số đã được ẩn trong tài liệu sinh ra

Sau khi khởi động ứng dụng, lấy đặc tả JSON:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Kiểm tra danh sách parameters của endpoint:

~~~bash
jq '.paths["/api/profile"].get.parameters' openapi.json
~~~

Nếu endpoint chỉ dùng principal và request context nội bộ, các tham số đó không nên xuất hiện trong danh sách **parameters** hoặc schema request body. Nếu endpoint có header công khai như **X-Tenant-Id**, header này vẫn phải xuất hiện.

Kiểm tra security scheme:

~~~bash
jq '{
  schemes: .components.securitySchemes,
  operationSecurity: .paths["/api/profile"].get.security
}' openapi.json
~~~

Kết quả cần thể hiện:

- Principal, Authentication, request/response context và custom context nội bộ không xuất hiện như đầu vào mà client phải cung cấp.
- Header hoặc cookie nghiệp vụ mà client cần gửi vẫn được mô tả.
- Cơ chế bearer token, OAuth2 hoặc session được biểu diễn bằng security scheme phù hợp.
- Operation vẫn xuất hiện trong tài liệu nếu chỉ một tham số của nó được ẩn.
- Request body và schema không bị sinh ra từ những kiểu context nội bộ.

Hãy mở Swagger UI và kiểm tra cùng operation. Nếu một field vẫn xuất hiện, xem JSON OpenAPI trước để xác định đó là parameter, thuộc tính schema hay security scheme; mỗi loại cần cách xử lý khác nhau.

## 9. Những lỗi thường gặp

**Principal xuất hiện như query parameter hoặc request body.** Đánh dấu tham số bằng **@Parameter(hidden = true)**, kiểm tra import annotation từ **io.swagger.v3.oas.annotations.Parameter**, sau đó lấy lại **/v3/api-docs**.

**@AuthenticationPrincipal xuất hiện trong Swagger UI.** Đây là trường hợp được FAQ của springdoc hướng dẫn dùng **@Parameter(hidden = true)**. Kiểm tra đúng annotation được đặt trên tham số có **@AuthenticationPrincipal**.

**Ẩn cả endpoint khi chỉ muốn ẩn một tham số.** Kiểm tra xem **@Hidden** hoặc **@Operation(hidden = true)** có được đặt ở cấp controller/phương thức hay không. Dùng **@Parameter(hidden = true)** cho đúng tham số.

**Header nghiệp vụ biến mất khỏi tài liệu.** Nếu controller đọc header từ **HttpServletRequest**, hãy bind bằng **@RequestHeader** hoặc khai báo parameter tường minh bằng **@Operation(parameters = ...)**. Đừng ẩn một giá trị mà client phải gửi.

**Authorization hiển thị như một header parameter.** Chuyển sang **SecurityScheme** và **SecurityRequirement**. OpenAPI dành cơ chế security riêng cho Authorization header.

**Kiểu context tùy biến xuất hiện trong schema.** Đánh dấu tham số resolver bằng **@Parameter(hidden = true)** và kiểm tra xem nó có đang bị coi là request body hoặc model attribute hay không.

## 10. Checklist

- [ ] Xác định tham số nào do framework hoặc server inject.
- [ ] Dùng **@Parameter(hidden = true)** cho principal, authentication hoặc context tùy biến cần ẩn.
- [ ] Không tạo parameter cho **HttpServletRequest** hoặc **HttpServletResponse** như thể client phải gửi object.
- [ ] Giữ các header, cookie và query parameter thực sự thuộc hợp đồng.
- [ ] Mô tả Authorization bằng security scheme, không bằng header parameter thông thường.
- [ ] Dùng **@Hidden** hoặc **@Operation(hidden = true)** chỉ khi muốn ẩn cả operation.
- [ ] Kiểm tra **/v3/api-docs** và Swagger UI sau khi thay đổi annotation.
- [ ] Xác nhận endpoint vẫn hoạt động và Spring vẫn inject đúng principal/context lúc runtime.

## 11. Nguồn tham khảo

- [Springdoc OpenAPI v2 FAQ](https://springdoc.org/v2/faq.html): cách ẩn tham số, xử lý **@AuthenticationPrincipal**, các kiểu injectable Spring MVC được loại khỏi tài liệu và mô tả Authorization bằng security requirement.
- [Spring Framework — Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): các kiểu đối số đặc biệt mà Spring MVC có thể cung cấp cho handler method.
- [OpenAPI — Describing Parameters](https://swagger.io/docs/specification/describing-parameters/): quy tắc mô tả parameter và các header dành riêng cho cơ chế xác thực.

Ẩn tham số hạ tầng giúp OpenAPI tập trung vào những gì client thực sự cần gửi. Hãy giữ ranh giới rõ giữa context do server cung cấp và dữ liệu thuộc hợp đồng HTTP, sau đó kiểm tra đặc tả được sinh ra để bảo đảm Swagger UI phản ánh đúng ranh giới đó.
