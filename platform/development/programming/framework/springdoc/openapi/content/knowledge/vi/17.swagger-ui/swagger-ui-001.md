# Vai trò của Swagger UI như công cụ đọc và gọi thử API

Swagger UI là giao diện web giúp người phát triển đọc đặc tả OpenAPI và gửi thử request đến API. Khi tích hợp với springdoc-openapi trong Spring Boot, ứng dụng có thể tự sinh đặc tả từ controller, DTO và annotation, sau đó cung cấp đặc tả đó cho Swagger UI hiển thị. Người dùng xem được endpoint, tham số, request body, response và có thể thực hiện request ngay trên trình duyệt.

Swagger UI giúp khám phá và thử nghiệm hợp đồng HTTP thuận tiện hơn. Nó không thay thế đặc tả OpenAPI, không triển khai endpoint và không tự bảo đảm API hoạt động đúng. Request được gửi qua mạng đến server thật, vì vậy kết quả còn phụ thuộc URL đích, xác thực, quyền truy cập, CORS và trạng thái của ứng dụng.

## 1. Phân biệt OpenAPI, springdoc-openapi và Swagger UI

Ba thành phần thường xuất hiện cùng nhau nhưng đảm nhiệm ba vai trò khác nhau:

| Thành phần | Vai trò | Kết quả |
|---|---|---|
| OpenAPI Specification | Định dạng chuẩn để mô tả hợp đồng HTTP | Tài liệu JSON hoặc YAML |
| springdoc-openapi | Đọc cấu trúc Spring Boot và sinh đặc tả OpenAPI | Endpoint cung cấp tài liệu API |
| Swagger UI | Đọc đặc tả và hiển thị giao diện tương tác | Trang web để xem và gọi thử operation |

Ví dụ, controller có endpoint <code>GET /products/{productId}</code>. springdoc-openapi đọc mapping, kiểu tham số và DTO để tạo operation tương ứng trong tài liệu. Swagger UI tải tài liệu đó, hiển thị operation và cung cấp biểu mẫu để người dùng nhập <code>productId</code>, nhấn Execute rồi xem response.

Chu trình tổng quát:

~~~mermaid
flowchart LR
    A["Spring Controller và DTO"] --> B["springdoc-openapi"]
    B --> C["OpenAPI JSON hoặc YAML"]
    C --> D["Swagger UI"]
    D --> E["Người dùng chọn operation"]
    E --> F["Try it out / Execute"]
    F --> G["HTTP request đến API"]
    G --> H["HTTP response"]
    H --> D
~~~

Swagger UI không tự quét mọi URL trong server để tìm endpoint. Nó hiển thị những operation có trong tài liệu OpenAPI mà nó được cấu hình để tải.

## 2. Cài Swagger UI cùng springdoc-openapi

Với ứng dụng Spring MVC, thêm UI starter:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Đặt phiên bản ở Maven properties hoặc dependency management bằng phiên bản tương thích với Spring Boot của dự án. Không sao chép một phiên bản bất kỳ mà bỏ qua ma trận tương thích.

Với ứng dụng Spring WebFlux, dùng artifact tương ứng:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Nếu ứng dụng chỉ cần xuất đặc tả cho API Portal hoặc công cụ khác, có thể chọn starter API tương ứng. Starter API cung cấp tài liệu OpenAPI nhưng không đóng gói giao diện Swagger UI. Khi muốn xem và gọi thử API bằng trình duyệt, chọn starter UI.

Sau khi thêm dependency và khởi động ứng dụng, các đường dẫn mặc định thường dùng là:

| Đường dẫn | Nội dung |
|---|---|
| <code>/v3/api-docs</code> | Đặc tả OpenAPI dạng JSON |
| <code>/v3/api-docs.yaml</code> | Đặc tả OpenAPI dạng YAML |
| <code>/swagger-ui.html</code> | Điểm vào Swagger UI, thường chuyển hướng đến tài nguyên giao diện |
| <code>/swagger-ui/**</code> | Tài nguyên tĩnh của giao diện Swagger UI |

Đường dẫn có thể thay đổi theo cấu hình, context path hoặc reverse proxy. Nếu dự án đã tùy chỉnh <code>springdoc.api-docs.path</code> hay <code>springdoc.swagger-ui.path</code>, hãy dùng URL thực tế được cấu hình.

## 3. Ví dụ controller để Swagger UI hiển thị

Xét một API quản lý sản phẩm:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
class ProductController {

    @Operation(
        operationId = "getProductById",
        summary = "Lấy sản phẩm theo mã"
    )
    @GetMapping("/{productId}")
    ProductResponse getById(
            @Parameter(description = "Mã sản phẩm")
            @PathVariable("productId") String productId) {
        return new ProductResponse(productId, "Wireless Mouse", 299000);
    }

    @Operation(
        operationId = "createProduct",
        summary = "Tạo sản phẩm mới"
    )
    @PostMapping
    ResponseEntity<ProductResponse> create(
            @RequestBody CreateProductRequest request) {
        ProductResponse response = new ProductResponse(
            "SKU-200",
            request.name(),
            request.price()
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}

record CreateProductRequest(
    @Schema(example = "Mechanical Keyboard")
    String name,
    @Schema(example = "1599000")
    Integer price
) {}

record ProductResponse(
    String productId,
    String name,
    Integer price
) {}
~~~

springdoc-openapi dùng các mapping và kiểu dữ liệu trên để tạo hai operation. <code>@Operation</code> bổ sung định danh và tiêu đề; <code>@Parameter</code> bổ sung mô tả tham số; <code>@Schema</code> bổ sung ví dụ cho thuộc tính DTO.

Một phần tài liệu JSON có thể tương tự:

~~~yaml
paths:
  /products/{productId}:
    get:
      operationId: getProductById
      summary: Lấy sản phẩm theo mã
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: OK
  /products:
    post:
      operationId: createProduct
      summary: Tạo sản phẩm mới
      requestBody:
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateProductRequest"
      responses:
        "201":
          description: Created
~~~

Swagger UI không đọc trực tiếp mã Java trong ví dụ. Nó đọc operation và schema đã được springdoc-openapi đưa vào tài liệu.

## 4. Đọc tài liệu trong Swagger UI

Khi mở Swagger UI, người dùng thường thấy các nhóm tag và danh sách operation. Mỗi operation có thể mở rộng để xem:

- HTTP method và path.
- <code>summary</code>, <code>description</code>, <code>operationId</code> và tag.
- Path, query, header hoặc cookie parameter.
- Request body và các media type được hỗ trợ.
- Schema, enum, giới hạn và ví dụ.
- Các mã response, header và response body.
- Thông tin bảo mật nếu đặc tả khai báo security scheme.

Người đọc có thể dùng phần schema để hiểu cấu trúc dữ liệu trước khi gọi API. Nếu operation có ví dụ request hoặc response, Swagger UI có thể hiển thị các ví dụ đó để người dùng chọn và tham khảo.

Đây là giao diện đọc hợp đồng: nội dung hiển thị phụ thuộc vào chất lượng đặc tả. Nếu controller thiếu mô tả, response schema không chính xác hoặc ví dụ chưa được khai báo, Swagger UI không thể tự suy ra ý nghĩa nghiệp vụ còn thiếu.

## 5. Dùng Try it out để gọi thử API

Với operation hỗ trợ tương tác, Swagger UI có nút **Try it out**. Khi bật chế độ này, người dùng có thể nhập tham số, sửa request body, chọn content type và thực hiện request bằng **Execute**.

Quy trình thông thường:

1. Mở nhóm tag chứa endpoint cần thử.
2. Mở operation, ví dụ <code>GET /products/{productId}</code>.
3. Chọn Try it out.
4. Nhập giá trị cho <code>productId</code>.
5. Chọn Execute để gửi request.
6. Đọc request URL, curl mẫu, HTTP status, response headers và response body mà giao diện hiển thị.

Với <code>POST /products</code>, người dùng có thể nhập JSON:

~~~json
{
  "name": "Mechanical Keyboard",
  "price": 1599000
}
~~~

Swagger UI dựng request dựa trên operation và schema trong OpenAPI. Request sau đó được gửi từ trình duyệt đến URL server được chọn trong tài liệu. Server xử lý request theo controller, filter, security, validation và nghiệp vụ như các client HTTP khác.

Nhấn Execute là một request thật. Với <code>POST</code>, <code>PUT</code>, <code>PATCH</code> hoặc <code>DELETE</code>, thao tác có thể tạo, sửa hoặc xóa dữ liệu. Nên thử các operation thay đổi trạng thái trên môi trường local, development hoặc staging với dữ liệu thử nghiệm.

## 6. Server URL quyết định request đi đâu

OpenAPI có thể khai báo một hoặc nhiều server. Swagger UI sử dụng server URL đã chọn để tạo URL gửi request:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "http://localhost:8080",
            description = "Môi trường local"
        ),
        @Server(
            url = "https://api.example.com",
            description = "API staging"
        )
    }
)
class OpenApiServerConfiguration {
}
~~~

Swagger UI có thể hiển thị danh sách server để người dùng chọn. Cần bảo đảm server URL khớp môi trường hiện tại và base path thực tế.

Không nên để tài liệu production vô tình trỏ về localhost của máy người xem. Cũng không nên công bố server production làm lựa chọn mặc định trong tài liệu dành cho môi trường phát triển nếu Try it out có thể gửi dữ liệu ghi thật.

Khi ứng dụng chạy sau reverse proxy hoặc gateway, URL công khai có thể khác địa chỉ nội bộ mà Spring Boot nhìn thấy. Cần cấu hình forwarded headers, context path và server URL để Swagger UI tạo request đúng host, scheme và prefix.

## 7. Xác thực trong Swagger UI

Swagger UI có thể hiển thị nút **Authorize** khi tài liệu OpenAPI khai báo security scheme. Ví dụ HTTP Bearer:

~~~java
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
class ApiSecurityDocumentation {
}
~~~

Operation hoặc controller có thể yêu cầu scheme đó:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@RestController
@RequestMapping("/profile")
@SecurityRequirement(name = "bearerAuth")
class ProfileController {
    // Các operation yêu cầu Bearer token
}
~~~

Khi người dùng nhập token trong hộp thoại Authorize, Swagger UI có thể gắn header <code>Authorization: Bearer ...</code> vào các request thuộc phạm vi bảo mật được mô tả. Cách giao diện lưu và sử dụng thông tin xác thực phụ thuộc cấu hình Swagger UI.

Security scheme chỉ mô tả cơ chế cho công cụ đọc tài liệu. Nó không bật xác thực trong Spring Security và không cấp quyền cho request. Ứng dụng vẫn phải cấu hình authentication, authorization và kiểm tra quyền ở server. Nếu token không hợp lệ, server có thể trả <code>401</code>; nếu người dùng đã xác thực nhưng thiếu quyền, server có thể trả <code>403</code>.

Chỉ dùng token thử nghiệm trên môi trường phù hợp. Không nhập thông tin xác thực production vào máy tính dùng chung hoặc chia sẻ ảnh chụp màn hình có chứa token.

## 8. CORS khi Swagger UI và API khác origin

Trình duyệt áp dụng Same-Origin Policy. Nếu Swagger UI được phục vụ từ một origin nhưng API ở origin khác, request có thể bị chặn bởi CORS nếu server không cho phép origin, method và header tương ứng.

Ví dụ:

- Swagger UI: <code>https://docs.example.com</code>
- API: <code>https://api.example.com</code>

Hai host khác nhau nên đây là hai origin khác nhau. Khi Swagger UI gọi API, server API phải trả các CORS header phù hợp. Với Bearer token, preflight có thể cần cho phép header <code>Authorization</code>.

Nếu Swagger UI được phục vụ cùng origin với API, vấn đề CORS thường đơn giản hơn vì request thuộc cùng origin. Dù vậy, proxy hoặc domain alias vẫn có thể khiến browser xem đó là origin khác.

Không giải quyết lỗi CORS bằng cách mở tất cả origin trong production. Chỉ cho phép các origin tài liệu đáng tin cậy và những method/header thực sự cần thiết.

## 9. Cấu hình đường dẫn Swagger UI và OpenAPI

Có thể thay đổi đường dẫn mặc định trong <code>application.yml</code>:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

Sau cấu hình này, tài liệu JSON dùng đường dẫn <code>/openapi</code>; giao diện Swagger UI dùng <code>/docs</code>. Bản YAML có thể truy cập theo đường dẫn tài liệu tương ứng nếu endpoint YAML được bật.

Một số thuộc tính khác có thể điều chỉnh giao diện:

~~~yaml
springdoc:
  swagger-ui:
    operationsSorter: method
    tagsSorter: alpha
    displayRequestDuration: true
    docExpansion: none
~~~

Các thuộc tính trên thay đổi cách trình bày và sắp xếp operation. Chúng không thay đổi mapping controller hoặc hợp đồng HTTP. Tên và giá trị cấu hình cần được kiểm tra theo phiên bản springdoc đang sử dụng.

## 10. Giới hạn của Swagger UI

Swagger UI hữu ích cho việc đọc và gọi thử, nhưng cần hiểu rõ giới hạn:

| Swagger UI làm được | Swagger UI không tự làm |
|---|---|
| Hiển thị operation theo OpenAPI | Tự khám phá mọi endpoint không có trong tài liệu |
| Hiển thị schema, parameter và examples | Bảo đảm schema phản ánh đúng runtime |
| Tạo request mẫu và gửi qua trình duyệt | Thay thế kiểm thử tự động hoặc contract test |
| Hiển thị status, header và response body | Sửa lỗi backend hoặc dữ liệu |
| Gắn thông tin xác thực theo security scheme | Cấu hình Spring Security hoặc cấp quyền |
| Hỗ trợ người dùng thử API | Thay thế Postman, curl, test suite hoặc monitoring trong mọi tình huống |

Swagger UI cũng chịu ảnh hưởng bởi browser, mạng, TLS certificate, DNS, proxy và CORS. Một request thất bại trên giao diện chưa đủ để kết luận endpoint bị lỗi; cần kiểm tra request URL, console/network của trình duyệt và log server.

## 11. Bảo vệ và vận hành Swagger UI

Tài liệu API có thể tiết lộ cấu trúc endpoint, tên field, luồng nghiệp vụ và các response nội bộ. Trước khi bật Swagger UI trên môi trường dùng chung, hãy xác định ai được phép truy cập:

- Môi trường phát triển có thể mở cho nhóm phát triển.
- Staging có thể yêu cầu đăng nhập hoặc giới hạn qua mạng nội bộ.
- Production có thể tắt giao diện, giới hạn quyền hoặc chỉ cung cấp tài liệu đã được phê duyệt.

Có thể dùng Spring Security để bảo vệ các đường dẫn tài liệu và giao diện theo chính sách của hệ thống. Cần xem xét cả <code>/swagger-ui/**</code>, điểm vào <code>/swagger-ui.html</code> hoặc đường dẫn tùy chỉnh, <code>/v3/api-docs</code> và endpoint YAML. Nếu chỉ bảo vệ trang UI nhưng để tài liệu JSON công khai, người dùng vẫn có thể tải trực tiếp đặc tả.

Không coi việc ẩn nút Swagger UI là biện pháp bảo mật cho API. Endpoint nghiệp vụ phải được bảo vệ độc lập bằng authentication và authorization.

## 12. Sự cố thường gặp

**Swagger UI không mở được.** Kiểm tra đã dùng UI starter phù hợp với MVC/WebFlux chưa, ứng dụng có khởi động thành công không, context path và <code>springdoc.swagger-ui.path</code> có đúng không. Nếu chỉ cài API starter, không có giao diện UI đi kèm.

**Trang mở được nhưng không có operation.** Kiểm tra URL tài liệu mà UI tải, phản hồi <code>/v3/api-docs</code>, cấu hình nhóm tài liệu và controller có được springdoc quét hay không.

**Try it out gửi đến sai host hoặc path.** Kiểm tra <code>servers</code>, context path, reverse proxy, forwarded headers và server URL đang được chọn trong giao diện.

**Request trả 401 hoặc 403.** Kiểm tra token, security scheme, security requirement và chính sách Spring Security. Authorize trong Swagger UI không tự cấp quyền.

**Trình duyệt báo CORS.** Kiểm tra origin của trang UI, CORS policy của API, preflight request và các header được phép.

**Request thành công nhưng response không giống tài liệu.** Đối chiếu controller, DTO, Jackson serializer/deserializer, exception handler và schema được sinh tại <code>/v3/api-docs</code>.

**Execute gây thay đổi dữ liệu.** Đó là hành vi của HTTP operation được gọi. Dùng môi trường và dữ liệu thử nghiệm, đặc biệt với operation ghi hoặc xóa.

## 13. Quy trình thử một API bằng Swagger UI

1. Khởi động Spring Boot với UI starter và kiểm tra endpoint OpenAPI JSON.
2. Mở Swagger UI theo đường dẫn đang cấu hình.
3. Xác nhận giao diện tải đúng tài liệu và đúng server URL.
4. Chọn một operation đọc dữ liệu trước, kiểm tra path/query/header parameter.
5. Dùng Try it out, nhập giá trị hợp lệ rồi Execute.
6. Đọc request URL, status, response headers và body.
7. Thử một dữ liệu không hợp lệ để quan sát response validation nếu môi trường cho phép.
8. Với operation cần xác thực, dùng token thử nghiệm và xác nhận server áp dụng đúng quyền.
9. Với operation thay đổi dữ liệu, dùng tài nguyên thử nghiệm và kiểm tra trạng thái sau request.
10. Ghi nhận khác biệt giữa tài liệu, response thực tế và quy tắc nghiệp vụ để cập nhật hợp đồng hoặc triển khai.

## 14. Danh sách rà soát trước khi chia sẻ Swagger UI

- [ ] Ứng dụng dùng đúng starter UI theo Spring MVC hoặc WebFlux.
- [ ] <code>/v3/api-docs</code> hoặc đường dẫn tài liệu tùy chỉnh trả về OpenAPI hợp lệ.
- [ ] Swagger UI tải đúng tài liệu và hiển thị operation mong muốn.
- [ ] Server URL trỏ đúng môi trường.
- [ ] Security scheme và requirement khớp với cấu hình bảo mật thực tế.
- [ ] CORS cho phép đúng origin nếu UI và API khác origin.
- [ ] Các operation ghi/xóa được thử trên môi trường phù hợp.
- [ ] Đã xác định quyền truy cập vào UI và cả endpoint JSON/YAML.
- [ ] Response thực tế được đối chiếu với schema và examples.

## Tài liệu tham khảo

- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html): dependency và endpoint mặc định cho OpenAPI, Swagger UI.
- [springdoc-openapi – Properties](https://springdoc.org/properties.html): cấu hình đường dẫn tài liệu và giao diện.
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): cách cấu hình giao diện Swagger UI.
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object): khai báo server URL trong đặc tả.
- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/latest.html#security-scheme-object): mô tả cơ chế xác thực và security requirement.
- [MDN – CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): cách trình duyệt kiểm soát request cross-origin.
