# Đọc đặc tả tại /v3/api-docs

Khi tích hợp springdoc-openapi vào ứng dụng Spring Boot, endpoint **/v3/api-docs** là nơi ứng dụng công bố đặc tả OpenAPI dưới dạng JSON. Đặc tả này mô tả các đường dẫn HTTP, phương thức, tham số, request body, response, schema dữ liệu và cơ chế bảo mật mà ứng dụng khai báo. Công cụ như Swagger UI, cổng API, bộ sinh client và pipeline kiểm thử hợp đồng có thể đọc cùng tài liệu này.

Điểm quan trọng là **/v3/api-docs trả về mô tả của API**, không thực thi nghiệp vụ của từng endpoint. Ví dụ, gọi `/api/orders/42` có thể trả về đơn hàng số 42; gọi `/v3/api-docs` trả về cấu trúc mô tả rằng API có đường dẫn `/api/orders/{id}`, nhận tham số `id` và có thể trả về một schema đơn hàng.

## 1. Endpoint /v3/api-docs được tạo như thế nào?

Springdoc đọc các thành phần Spring được đăng ký trong ApplicationContext, đặc biệt là các controller và mapping HTTP của Spring MVC hoặc Spring WebFlux. Từ thông tin đó, thư viện tạo ra mô hình OpenAPI và chuyển mô hình thành JSON để trả về tại endpoint tài liệu.

Thông tin được suy ra thường bao gồm:

- Đường dẫn và HTTP method từ các annotation mapping như `@GetMapping`, `@PostMapping`, `@PutMapping` và `@DeleteMapping`.
- Path variable, query parameter, header và cookie parameter từ chữ ký method và annotation Spring.
- Request body từ kiểu tham số được đánh dấu `@RequestBody`.
- Response từ kiểu trả về, `ResponseEntity` và các metadata phản hồi được khai báo.
- Schema từ DTO, record, generic type, enum và các annotation mô tả schema.
- Metadata bổ sung từ annotation của OpenAPI như `@Operation`, `@ApiResponse`, `@Parameter`, `@Schema` và `@SecurityRequirement`.

Springdoc kết hợp thông tin suy ra với metadata do lập trình viên khai báo. Vì vậy, một controller có thể xuất hiện trong tài liệu ngay cả khi chưa viết nhiều annotation OpenAPI; tuy nhiên, mô tả nghiệp vụ, response lỗi, điều kiện dữ liệu và yêu cầu bảo mật thường cần được bổ sung tường minh.

Quá trình tạo tài liệu diễn ra trong ứng dụng đang chạy. Khi controller hoặc cấu hình OpenAPI thay đổi và ứng dụng được khởi động lại hoặc nạp lại cấu hình, nội dung tài liệu được tạo từ trạng thái ứng dụng tương ứng. Endpoint không tự đọc mã nguồn từ Git và cũng không lấy hợp đồng từ một file YAML bên ngoài, trừ khi dự án chủ động xây dựng cơ chế khác.

## 2. Gọi endpoint và lưu JSON

Với cấu hình mặc định, ứng dụng phục vụ tài liệu tại:

```text
GET http://localhost:8080/v3/api-docs
```

Dùng curl để xem phản hồi:

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/v3/api-docs
```

Nếu chỉ muốn lưu nội dung JSON vào file:

```bash
curl -sS -H "Accept: application/json" \
  http://localhost:8080/v3/api-docs \
  -o openapi.json
```

Trên Windows PowerShell, có thể gọi rõ chương trình `curl.exe` để tránh alias của PowerShell:

```powershell
curl.exe -i -H "Accept: application/json" http://localhost:8080/v3/api-docs
curl.exe -sS -H "Accept: application/json" http://localhost:8080/v3/api-docs -o openapi.json
```

Phản hồi thành công thường có HTTP status **200 OK** và Content-Type JSON. Nếu ứng dụng có context path, ví dụ `server.servlet.context-path=/shop`, URL thực tế sẽ bao gồm context path:

```text
http://localhost:8080/shop/v3/api-docs
```

Nếu đã thay đổi `springdoc.api-docs.path`, hãy dùng đường dẫn mới thay cho mặc định. Endpoint cũng có thể bị chặn bởi Spring Security hoặc reverse proxy.

## 3. Nhận diện cấu trúc của tài liệu OpenAPI

Phản hồi là một JSON object theo cấu trúc OpenAPI. Ví dụ rút gọn sau minh họa những phần thường gặp; tên ứng dụng, đường dẫn và schema chỉ mang tính minh họa:

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Order API",
    "description": "API quản lý đơn hàng",
    "version": "v1"
  },
  "servers": [
    {
      "url": "http://localhost:8080",
      "description": "Generated server url"
    }
  ],
  "paths": {
    "/api/orders/{id}": {
      "get": {
        "tags": ["orders"],
        "operationId": "getOrder",
        "summary": "Lấy thông tin đơn hàng",
        "parameters": [
          {
            "name": "id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Tìm thấy đơn hàng",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OrderResponse"
                }
              }
            }
          }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "OrderResponse": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "status": { "type": "string" }
        }
      }
    }
  }
}
```

Các trường chính cần nhận diện:

| Trường | Ý nghĩa |
|---|---|
| `openapi` | Phiên bản đặc tả OpenAPI được dùng để biểu diễn tài liệu, ví dụ 3.1.0. Đây không phải phiên bản Spring Boot hay springdoc. |
| `info` | Thông tin API như tiêu đề, mô tả, phiên bản và thông tin liên hệ hoặc giấy phép nếu có. |
| `servers` | Các URL gốc mà client có thể dùng để gọi API. |
| `tags` | Nhãn nhóm các operation để tài liệu dễ điều hướng. |
| `paths` | Các đường dẫn và operation tương ứng như GET, POST, PUT, PATCH hoặc DELETE. |
| `components` | Các thành phần có thể tái sử dụng, thường gồm schemas, parameters, responses, requestBodies và securitySchemes. |
| `security` | Yêu cầu bảo mật áp dụng ở cấp tài liệu hoặc operation. |

Trong `paths`, mỗi path item có thể chứa nhiều operation. Một operation thường có `operationId`, `summary`, `description`, `parameters`, `requestBody`, `responses`, `tags` và `security`. Không phải operation nào cũng có đầy đủ tất cả các trường này.

## 4. Đọc paths, parameters và requestBody

Để hiểu một API cụ thể, bắt đầu từ khóa trong `paths`, sau đó xem HTTP method bên dưới.

Ví dụ:

```json
{
  "/api/orders": {
    "post": {
      "summary": "Tạo đơn hàng",
      "requestBody": {
        "required": true,
        "content": {
          "application/json": {
            "schema": {
              "$ref": "#/components/schemas/CreateOrderRequest"
            }
          }
        }
      },
      "responses": {
        "201": {
          "description": "Đã tạo đơn hàng"
        },
        "400": {
          "description": "Dữ liệu không hợp lệ"
        }
      }
    }
  }
}
```

Phần `parameters` mô tả dữ liệu truyền qua URL hoặc header. Trường `in` cho biết vị trí:

- `path`: một phần của đường dẫn, ví dụ `/orders/{id}`.
- `query`: tham số truy vấn, ví dụ `?page=0&size=20`.
- `header`: HTTP header, ví dụ `X-Request-Id`.
- `cookie`: cookie gửi kèm request.

Path parameter phải được đánh dấu bắt buộc trong OpenAPI. Query parameter có thể bắt buộc hoặc tùy chọn tùy chữ ký method và metadata.

Phần `requestBody` mô tả nội dung gửi trong body. `required` cho biết body có bắt buộc hay không; `content` liệt kê media type như `application/json`; `schema` mô tả cấu trúc payload. Một endpoint có thể nhận nhiều media type và mỗi media type có schema tương ứng.

Phần `responses` mô tả kết quả theo mã HTTP. Ví dụ `200`, `201`, `204`, `400`, `401`, `403` hoặc `404`. Một response có thể có `description`, `headers`, `content` và schema. Hãy kiểm tra cả response thành công lẫn lỗi; nếu chỉ mô tả response 200, người dùng API có thể không biết hợp đồng khi gửi dữ liệu sai hoặc thiếu quyền.

## 5. Hiểu components và $ref

Các schema được dùng lại thường được đặt trong `components.schemas`. Thay vì lặp lại toàn bộ định nghĩa của một DTO trong từng operation, tài liệu có thể tham chiếu bằng `$ref`:

```json
{
  "schema": {
    "$ref": "#/components/schemas/OrderResponse"
  }
}
```

Đường dẫn `#/components/schemas/OrderResponse` là JSON Pointer trỏ đến schema có tên `OrderResponse` bên trong tài liệu hiện tại. Khi đọc một operation, nếu gặp `$ref`, hãy mở phần tương ứng trong `components` để hiểu các field, kiểu dữ liệu, required, enum, format và ràng buộc.

Ví dụ DTO:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "OrderResponse", description = "Thông tin đơn hàng")
public record OrderResponse(
    @Schema(description = "Mã đơn hàng", example = "ORD-1001")
    String id,

    @Schema(description = "Trạng thái đơn hàng", example = "CONFIRMED")
    String status
) {}
```

Schema phản ánh cấu trúc dữ liệu mà thư viện phân tích được. Những quy tắc nghiệp vụ phức tạp như “khách hàng chỉ được hủy đơn trong 15 phút” không thể suy ra từ kiểu Java đơn thuần; cần diễn đạt trong mô tả hoặc tài liệu nghiệp vụ thích hợp.

## 6. Bổ sung metadata để đặc tả có ý nghĩa

Ví dụ controller sau minh họa cách kết hợp mapping của Spring với annotation OpenAPI:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    @Operation(
        summary = "Lấy thông tin đơn hàng",
        description = "Tra cứu đơn hàng theo mã định danh."
    )
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy đơn hàng",
        content = @Content(
            schema = @Schema(implementation = OrderResponse.class)
        )
    )
    @ApiResponse(responseCode = "404", description = "Không tìm thấy đơn hàng")
    ResponseEntity<OrderResponse> getOrder(
        @Parameter(description = "Mã đơn hàng", example = "ORD-1001")
        @PathVariable String id
    ) {
        // Gọi service và trả về kết quả thực tế.
        return ResponseEntity.notFound().build();
    }
}
```

Ví dụ này tập trung minh họa metadata. Trong ứng dụng thật, nhánh trả về 200 phải tương ứng với logic service thực tế. Annotation `@ApiResponse` bổ sung mô tả response cho hợp đồng; nó không tự tạo ra response đó và cũng không thay đổi hành vi HTTP của controller.

Một số annotation thường dùng:

| Annotation | Vai trò |
|---|---|
| `@Operation` | Mô tả một operation, gồm summary, description, operationId và tag. |
| `@Parameter` | Mô tả tham số, ví dụ, vị trí và ràng buộc. |
| `@ApiResponse` / `@ApiResponses` | Mô tả các mã phản hồi và nội dung tương ứng. |
| `@Schema` | Mô tả schema, field, kiểu, ví dụ, enum và các ràng buộc. |
| `@OpenAPIDefinition` | Khai báo metadata ở cấp tài liệu như info, servers, tags và security. |
| `@SecurityScheme` | Định nghĩa cơ chế xác thực có thể tái sử dụng. |
| `@Hidden` | Ẩn operation hoặc thành phần khỏi tài liệu trong phạm vi áp dụng. |

Không cần thêm annotation cho mọi field nếu kiểu Java đã mô tả chính xác. Hãy bổ sung khi tên, ý nghĩa, ví dụ hoặc ràng buộc không thể hiện rõ từ mã nguồn.

## 7. Kiểm tra nhanh JSON bằng jq

Nếu máy có cài jq, có thể đọc các trường quan trọng mà không phải mở toàn bộ file:

```bash
# Phiên bản OpenAPI và metadata
jq '{openapi, info, servers}' openapi.json

# Liệt kê toàn bộ path
jq -r '.paths | keys[]' openapi.json

# Liệt kê HTTP method dưới từng path
jq -r '
  .paths
  | to_entries[]
  | .key as $path
  | .value
  | to_entries[]
  | select(.key | IN("get","post","put","patch","delete","options","head","trace"))
  | "\(.key | ascii_upcase) \($path)"
' openapi.json

# Liệt kê schema có thể tái sử dụng
jq -r '.components.schemas // {} | keys[]' openapi.json
```

Nếu không có jq, có thể mở JSON bằng IDE hoặc trình định dạng JSON. Với tài liệu lớn, nên tìm theo path, operationId hoặc tên schema thay vì đọc từ đầu đến cuối.

Một số câu hỏi hữu ích khi kiểm tra:

- Path mong đợi có xuất hiện trong `paths` không?
- HTTP method có đúng không?
- Path/query parameter có đúng tên, kiểu và required không?
- Request body có đúng media type và schema không?
- Response có đủ status code và nội dung không?
- Schema có field bắt buộc, enum, format và mô tả đúng không?
- Các operation cần xác thực có security requirement phù hợp không?

## 8. Đường dẫn YAML, Swagger UI và cấu hình endpoint

Ngoài JSON, springdoc thường cung cấp tài liệu YAML tại:

```text
GET /v3/api-docs.yaml
```

Swagger UI là giao diện đọc và thử tài liệu, thường truy cập tại:

```text
/swagger-ui.html
```

Ba URL này có mục đích khác nhau:

| URL mặc định | Nội dung |
|---|---|
| `/v3/api-docs` | Đặc tả OpenAPI dạng JSON. |
| `/v3/api-docs.yaml` | Đặc tả OpenAPI dạng YAML. |
| `/swagger-ui.html` | Trang giao diện Swagger UI. |

Có thể thay đổi đường dẫn JSON bằng cấu hình:

```properties
springdoc.api-docs.path=/openapi
```

Sau thay đổi, endpoint JSON được phục vụ ở `/openapi`. Đường dẫn YAML và Swagger UI có các thuộc tính cấu hình riêng; hãy tra đúng property của phiên bản springdoc đang dùng nếu cần tùy chỉnh toàn bộ URL.

Có thể tắt endpoint tài liệu bằng:

```properties
springdoc.api-docs.enabled=false
```

Khi thuộc tính này bị tắt, yêu cầu tới endpoint tài liệu mặc định sẽ không còn trả về đặc tả. Cần kiểm tra cấu hình theo profile, ví dụ `application-dev.yml` và `application-prod.yml`, để biết môi trường nào bật hoặc tắt tài liệu.

## 9. Giới hạn phạm vi endpoint và nhóm tài liệu

Một ứng dụng có thể có nhiều controller, hoặc cần cung cấp tài liệu riêng cho từng nhóm API. Springdoc hỗ trợ lọc theo package và path, ví dụ:

```properties
springdoc.packages-to-scan=com.example.shop.api
springdoc.paths-to-match=/api/**
springdoc.paths-to-exclude=/api/internal/**
```

Các thuộc tính lọc giúp giới hạn những handler được đưa vào tài liệu mặc định. Nếu một endpoint không xuất hiện, hãy kiểm tra package scan, path filter, annotation ẩn và việc controller có thực sự được Spring đăng ký hay không.

Đối với tài liệu chia nhóm, có thể khai báo `GroupedOpenApi`:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
```

Sau khi khai báo group, tài liệu của từng nhóm có thể được truy cập theo dạng:

```text
/v3/api-docs/public
/v3/api-docs/admin
```

Tên group là một phần của URL. Nếu một group không có path phù hợp hoặc không được đăng ký, endpoint nhóm có thể trả về lỗi hoặc tài liệu rỗng tùy cấu hình và phiên bản. Hãy xác minh từng group trực tiếp.

## 10. Security và quyền truy cập tài liệu

Endpoint `/v3/api-docs` là một endpoint HTTP của ứng dụng. Vì vậy, Spring Security, gateway và reverse proxy có thể áp dụng chính sách truy cập giống các endpoint khác. Khi gọi từ trình duyệt hoặc pipeline, cần xác định tài liệu được phép truy cập công khai hay phải xác thực.

Ví dụ dưới đây cho phép truy cập các URL tài liệu trong một cấu hình Spring Security; chỉ áp dụng khi chính sách của hệ thống cho phép:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        "/v3/api-docs/**",
        "/swagger-ui/**",
        "/swagger-ui.html"
    ).permitAll()
    .anyRequest().authenticated()
);
```

Nếu tài liệu chỉ dành cho nội bộ, hãy bảo vệ endpoint bằng cơ chế xác thực phù hợp. Không bật `permitAll` theo thói quen vì tài liệu có thể tiết lộ cấu trúc endpoint, tên thao tác và mô hình dữ liệu nội bộ. Dù OpenAPI không chứa dữ liệu nghiệp vụ thực tế, nội dung của nó vẫn có thể hữu ích cho người muốn dò tìm bề mặt API.

Khi dùng OAuth2, JWT hoặc HTTP Basic, các thành phần bảo mật cần được mô tả trong OpenAPI bằng security scheme và security requirement. Chỉ mở được endpoint JSON không chứng minh rằng tài liệu đã mô tả đúng cơ chế xác thực.

## 11. Kiểm tra hợp đồng thay vì chỉ kiểm tra HTTP 200

Một phản hồi 200 từ `/v3/api-docs` chứng minh endpoint tài liệu có thể được truy cập. Nó chưa chứng minh tài liệu đầy đủ hoặc đúng với hợp đồng mà đội phát triển mong đợi.

Nên kiểm tra ít nhất ba lớp:

1. **Tính sẵn sàng:** endpoint có trả về JSON hợp lệ, đúng Content-Type và status code không?
2. **Tính đầy đủ:** các path, method, request, response, schema và security requirement cần thiết có xuất hiện không?
3. **Tính chính xác:** tên field, kiểu dữ liệu, required, enum, response code và mô tả có khớp với hành vi API không?

Có thể lưu đặc tả thành artifact trong CI rồi so sánh với bản đã được duyệt. Nếu hợp đồng thay đổi, nhóm cần xem đó là thay đổi API có thể ảnh hưởng client. Những công cụ kiểm tra OpenAPI có thể phát hiện lỗi cấu trúc, quy tắc đặt tên hoặc thay đổi không tương thích; kiểm thử tích hợp vẫn cần để xác minh hành vi runtime.

Một quy trình kiểm tra đơn giản:

```bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
jq -e '.openapi and .info.title and (.paths | type == "object")' openapi.json
```

Lệnh thứ hai kiểm tra một số trường cơ bản. Để kiểm tra hợp đồng sâu hơn, hãy bổ sung assertion cho path và schema quan trọng của hệ thống, hoặc dùng validator OpenAPI trong pipeline.

## 12. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| `404 Not Found` tại `/v3/api-docs` | Đã đổi `springdoc.api-docs.path`, cấu hình context path, tắt `springdoc.api-docs.enabled`, hoặc request đi qua proxy với prefix khác. |
| `401 Unauthorized` hoặc `403 Forbidden` | Spring Security, gateway hoặc proxy yêu cầu xác thực hay chặn URL tài liệu. |
| JSON trả về 200 nhưng `paths` rỗng hoặc thiếu endpoint | Controller chưa được đăng ký, package/path filter loại endpoint, endpoint bị ẩn hoặc ứng dụng chưa nạp đúng cấu hình. |
| Path xuất hiện nhưng thiếu tham số hoặc schema | Kiểu dữ liệu, annotation mapping, metadata tên tham số hoặc generic type chưa đủ rõ. |
| Swagger UI không hiển thị tài liệu | Kiểm tra URL JSON mà UI đang gọi, group name, context path, CORS và quyền truy cập. |
| Trường `servers` chứa URL không đúng khi chạy sau proxy | Kiểm tra forwarded headers, cấu hình proxy và cách ứng dụng xác định URL gốc. |
| Lỗi 500 khi sinh tài liệu | Xem stack trace để xác định kiểu dữ liệu hoặc cấu hình không được xử lý; kiểm tra dependency tree và tương thích phiên bản springdoc với Spring Boot. |

Khi điều tra, hãy gọi trực tiếp endpoint JSON bằng curl trước. Nếu curl cũng nhận lỗi, tập trung vào ứng dụng, security và routing. Nếu JSON trả về đúng nhưng Swagger UI lỗi, kiểm tra request mà trình duyệt gửi tới endpoint tài liệu, bao gồm URL, group và header xác thực.

## 13. Checklist đọc /v3/api-docs trong dự án

- [ ] Đã gọi đúng URL, bao gồm context path và đường dẫn tùy chỉnh nếu có.
- [ ] Phản hồi có status code phù hợp và Content-Type JSON.
- [ ] Trường `openapi` và `info` có giá trị đúng.
- [ ] Các path và HTTP method quan trọng xuất hiện.
- [ ] Parameter và requestBody có tên, kiểu, required và media type chính xác.
- [ ] Responses mô tả đủ status code và schema cần thiết.
- [ ] Các schema được tham chiếu qua `$ref` có định nghĩa trong components.
- [ ] Security scheme và security requirement phản ánh đúng chính sách.
- [ ] Group endpoint, nếu có, trả về đúng tập API.
- [ ] Tài liệu đã được kiểm tra bằng validator hoặc assertion trong CI.

## 14. Nguồn tra cứu

- [Tài liệu chính thức springdoc-openapi](https://springdoc.org/)
- [springdoc-openapi – FAQ và các thuộc tính cấu hình](https://springdoc.org/#properties)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Swagger – OpenAPI Specification overview](https://swagger.io/specification/)

Các đường dẫn mặc định và thuộc tính cấu hình có thể thay đổi theo phiên bản springdoc. Khi nâng cấp thư viện, hãy đối chiếu tài liệu của đúng dòng phiên bản và kiểm tra lại endpoint trong ứng dụng đang chạy.
