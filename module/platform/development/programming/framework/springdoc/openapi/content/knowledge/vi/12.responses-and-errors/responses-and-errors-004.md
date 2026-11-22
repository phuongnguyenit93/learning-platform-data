# Phản hồi không có thân như 204 và cách tránh schema suy luận sai

Không phải mọi request thành công đều cần trả JSON. Khi client xóa một tài nguyên, cập nhật dữ liệu nhưng không cần representation mới, hoặc gửi một thao tác chỉ cần xác nhận đã hoàn tất, server có thể trả response không có message body. HTTP `204 No Content` là lựa chọn phổ biến cho trường hợp này.

Trong Spring Boot, kiểu trả về của controller ảnh hưởng đến cách Spring xử lý response và cách Springdoc suy luận schema. Nếu một endpoint thực tế không trả body nhưng method lại khai báo DTO, `String`, `Object` hoặc wrapper generic, tài liệu OpenAPI có thể xuất hiện schema không đúng. Cần làm cho HTTP status, kiểu trả về Java, annotation response và OpenAPI Response Object cùng thể hiện một hợp đồng nhất quán.

## 1. Response không có body có nghĩa gì?

Một HTTP response gồm status line, header và có thể có message content (body). Response không có body vẫn có thể chứa header để cung cấp metadata, nhưng client không nhận representation JSON/XML trong phần content.

Một số trường hợp thường gặp:

| Trường hợp | Status hoặc method | Ý nghĩa |
|---|---|---|
| Xóa tài nguyên thành công | `204 No Content` | Thao tác hoàn tất, không trả representation |
| Cập nhật thành công nhưng không trả dữ liệu mới | `204 No Content` | Client biết thao tác đã hoàn tất |
| Yêu cầu đã được nhận và đang xử lý | `202 Accepted` | Có thể trả body mô tả trạng thái xử lý; cũng có thể không có body nếu hợp đồng quy định |
| Client gửi request HEAD | `HEAD` | Response không có content; header mô tả tương ứng với GET có thể vẫn xuất hiện |
| Representation không thay đổi theo điều kiện request | `304 Not Modified` | Client dùng bản cache; response không có content |
| Server yêu cầu client đặt lại trạng thái hiển thị | `205 Reset Content` | Response không có content và có semantics riêng của 205 |

Không nên dùng tất cả các status này thay thế cho nhau. `204` thường phù hợp khi thao tác đã hoàn tất và không cần representation. `202` nói rằng xử lý đã được chấp nhận nhưng chưa chắc đã hoàn tất. `304` chỉ phù hợp với conditional request như `If-None-Match` hoặc `If-Modified-Since`. `205` có ý nghĩa reset nội dung hiển thị của client và ít gặp hơn trong API nghiệp vụ.

## 2. Quy tắc HTTP của 204 No Content

Theo HTTP Semantics, `204 No Content` biểu thị request đã được thực hiện thành công và không có content để gửi trong response. Response kết thúc sau phần header. Server không được gửi message content hoặc trailer field trong response 204 và không được gửi header `Content-Length` trong response này.

Một response 204 vẫn có thể mang metadata header có ích. Ví dụ:

- `ETag` cho biết validator mới của tài nguyên sau khi cập nhật.
- `Cache-Control` điều khiển hành vi cache.
- Header nghiệp vụ được API công bố, nếu phù hợp với semantics HTTP.

Ví dụ:

```http
HTTP/1.1 204 No Content
ETag: "product-42-v8"
Cache-Control: no-store
```

Response trên không có JSON body nhưng vẫn cung cấp ETag để client dùng cho lần cập nhật tiếp theo. Nếu cần trả dữ liệu mới như tên, giá hoặc trạng thái tài nguyên, hãy dùng response có body, thường là `200 OK`.

## 3. Trả 204 đúng cách trong Spring Boot

Với Spring MVC, có hai cách phổ biến để tạo response 204.

### Cách 1: Dùng `ResponseEntity<Void>`

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(@PathVariable Long id) {
        productService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

`ResponseEntity.noContent().build()` đặt status thành `204` và tạo response không có body. `Void` diễn tả rõ rằng method không trả representation. Cách này thuận tiện khi controller cần thiết lập status hoặc header theo từng nhánh xử lý.

### Cách 2: Dùng `void` kết hợp `@ResponseStatus`

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.ResponseStatus;

@DeleteMapping("/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
void delete(@PathVariable Long id) {
    productService.delete(id);
}
```

`@ResponseStatus(HttpStatus.NO_CONTENT)` yêu cầu Spring trả status 204; kiểu `void` thể hiện method không cung cấp response body. Đây là cách ngắn gọn khi status cố định và không cần xây dựng `ResponseEntity`.

### Khi cần trả header cùng 204

Có thể dùng `ResponseEntity` để thêm metadata:

```java
@PutMapping("/{id}/activate")
ResponseEntity<Void> activate(@PathVariable Long id) {
    String newVersion = productService.activate(id);

    return ResponseEntity.noContent()
        .eTag(newVersion)
        .build();
}
```

Giá trị ETag cần tuân theo định dạng entity-tag HTTP mà ứng dụng sử dụng. Response vẫn không có body; header chỉ cung cấp metadata về phiên bản tài nguyên.

Không nên trả DTO với mọi field đều null rồi xem đó là response rỗng. JSON `{}` hoặc `{"data":null}` vẫn là message content và có semantics khác 204.

## 4. Mô tả response 204 trong OpenAPI

Trong OpenAPI Response Object, trường `description` là bắt buộc; `content` là tùy chọn. Với response không có body, hãy bỏ hẳn `content`.

Ví dụ OpenAPI YAML:

```yaml
paths:
  /api/products/{id}:
    delete:
      summary: Xóa sản phẩm
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '204':
          description: Sản phẩm đã được xóa thành công; response không có body.
        '404':
          description: Không tìm thấy sản phẩm.
```

Ở đây, response 204 không có `content`, không có media type và không có schema. Đây là cách biểu diễn đúng cho response không có message body.

Không nên mô tả 204 bằng một schema giả như:

```yaml
'204':
  description: Thành công
  content:
    application/json:
      schema:
        type: object
```

Schema trên nói rằng server trả một JSON object. Nó mâu thuẫn với semantics của 204 và có thể khiến Swagger UI hoặc client generator tạo code đọc body không tồn tại.

Tương tự, không cần tạo `type: string`, `type: null` hoặc một DTO rỗng để đại diện cho response 204. Nếu không có content, hãy thể hiện đúng bằng việc không khai báo `content`.

## 5. Khai báo 204 bằng Swagger annotations trong Springdoc

Với Springdoc, có thể dùng `@ApiResponse` để mô tả status code và description. Không khai báo `content` cho response 204.

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;

@DeleteMapping("/{id}")
@Operation(summary = "Xóa sản phẩm theo mã")
@ApiResponses({
    @ApiResponse(
        responseCode = "204",
        description = "Sản phẩm đã được xóa; không có response body."
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Không tìm thấy sản phẩm."
    )
})
ResponseEntity<Void> delete(@PathVariable Long id) {
    productService.delete(id);
    return ResponseEntity.noContent().build();
}
```

Annotation 204 chỉ khai báo `responseCode` và `description`. Không thêm `@Content`, `@Schema(implementation = Void.class)` hoặc media type cho response này. Kiểu trả về `ResponseEntity<Void>` cũng giúp Springdoc hiểu method không có payload thành công.

Nếu muốn mô tả response header, có thể khai báo header trong `@ApiResponse` mà vẫn không cần `content`:

```java
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Schema;

@ApiResponse(
    responseCode = "204",
    description = "Đã cập nhật trạng thái sản phẩm; không có body.",
    headers = @Header(
        name = "ETag",
        description = "Validator mới của tài nguyên",
        schema = @Schema(type = "string")
    )
)
```

OpenAPI sẽ mô tả ETag trong `responses.204.headers`. Header không phải response body và không làm xuất hiện schema content.

## 6. Endpoint có cả response có body và response không có body

Một operation có thể trả nhiều status code với cấu trúc khác nhau. Ví dụ, endpoint cập nhật có thể trả `200 OK` kèm representation khi client yêu cầu dữ liệu mới, hoặc `204 No Content` khi chỉ xác nhận cập nhật.

OpenAPI phải mô tả từng response độc lập:

```yaml
responses:
  '200':
    description: Cập nhật thành công; trả về sản phẩm sau khi cập nhật.
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ProductResponse'
  '204':
    description: Cập nhật thành công; không trả representation.
  '404':
    description: Không tìm thấy sản phẩm.
```

Ví dụ controller có nhiều nhánh:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;

@PatchMapping("/{id}")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Đã cập nhật và trả về representation mới",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "204",
        description = "Đã cập nhật; không trả body"
    )
})
ResponseEntity<ProductResponse> patch(
    @PathVariable Long id,
    @RequestBody ProductPatchRequest request,
    @RequestParam(defaultValue = "true") boolean returnRepresentation
) {
    ProductResponse updated = productService.patch(id, request);

    if (returnRepresentation) {
        return ResponseEntity.ok(updated);
    }
    return ResponseEntity.noContent().build();
}
```

Ví dụ này dùng kiểu generic `ResponseEntity<ProductResponse>` vì một nhánh thực sự trả body. Với operation có nhiều response, Springdoc có thể suy luận schema từ kiểu trả về và kết hợp với các annotation response. Cần kiểm tra JSON OpenAPI được sinh ra để bảo đảm schema chỉ nằm dưới response 200 và response 204 không có `content`. Nếu tài liệu vẫn thêm schema vào 204, hãy kiểm tra annotation ở interface/controller, customizer, response dùng chung và phiên bản Springdoc đang sử dụng.

Nếu operation chỉ có thể trả 204, hãy dùng `ResponseEntity<Void>` hoặc `void` với `@ResponseStatus`, thay vì khai báo DTO rồi trả null.

## 7. Tránh suy luận schema sai từ kiểu trả về Java

Springdoc thường dùng kiểu trả về của controller để suy luận schema response khi không có metadata tường minh hoặc khi cần hoàn thiện response. Do đó, kiểu Java cần phản ánh đúng hành vi HTTP.

| Kiểu trả về | Ý nghĩa thường được suy luận | Phù hợp với 204? |
|---|---|---|
| `ResponseEntity<Void>` | Không có payload response | Có |
| `void` | Method không trả representation | Có, khi status được đặt thành 204 |
| `ResponseEntity<ProductResponse>` | Có thể trả `ProductResponse` | Không phù hợp nếu mọi nhánh đều không có body |
| `ProductResponse` | Có response body kiểu `ProductResponse` | Không phù hợp với operation chỉ trả 204 |
| `String` | Có response body dạng chuỗi | Không phù hợp với operation chỉ trả 204 |
| `ResponseEntity<Object>` | Payload không xác định rõ, có thể suy luận thành schema rộng | Nên tránh nếu không thực sự trả body động |
| `ResponseEntity<ApiEnvelope<Void>>` | Có body envelope, dù `data` có kiểu Void | Không phải response rỗng |

### `Void` khác `ApiEnvelope<Void>`

Hai kiểu này không có cùng semantics:

```java
ResponseEntity<Void>
```

Biểu thị response không có body.

```java
ResponseEntity<ApiEnvelope<Void>>
```

Biểu thị response có body là một JSON object envelope. Ví dụ:

```json
{
  "requestId": "req-42",
  "data": null
}
```

Nếu API trả JSON envelope, hãy mô tả schema envelope và dùng status phù hợp như 200. Nếu API không trả content, dùng 204 và không khai báo envelope.

### Không dựa vào giá trị null để quyết định status

Trả `null` từ một controller có kiểu DTO không tự động có nghĩa server trả 204. Kết quả phụ thuộc mapping, message converter, cấu hình và cách Spring xử lý return value. Hãy đặt status rõ ràng bằng `ResponseEntity.noContent()` hoặc `@ResponseStatus(HttpStatus.NO_CONTENT)`.

## 8. Generic response và response dùng chung từ ControllerAdvice

Một dự án có thể dùng wrapper chung như `ApiResponse<T>` hoặc khai báo response lỗi dùng chung bằng `@RestControllerAdvice`. Những cơ chế này hữu ích với response có body, nhưng không nên áp dụng một cách máy móc cho response 204.

Ví dụ một wrapper:

```java
public record ApiResponse<T>(
    String code,
    String message,
    T data
) {
}
```

Nếu method trả `ApiResponse<Void>`, response vẫn có JSON body chứa `code`, `message` và `data: null`. Đây không phải no-content response.

Springdoc có thể đưa response tổng quát từ `@ControllerAdvice` vào các operation. Thuộc tính `springdoc.override-with-generic-response` điều khiển việc áp dụng response tổng quát theo cơ chế Springdoc. Khi dự án dùng cấu hình này, kiểm tra các response của operation 204 để bảo đảm không có content không phù hợp bị thêm vào.

Ví dụ một error response có body vẫn có thể được mô tả riêng:

```java
@ApiResponse(
    responseCode = "404",
    description = "Không tìm thấy sản phẩm",
    content = @Content(
        mediaType = "application/problem+json",
        schema = @Schema(implementation = ProblemDetail.class)
    )
)
```

Response 404 có content không làm cho response 204 cũng cần content. Mỗi status code có Response Object riêng và phải được mô tả theo hành vi thực tế.

## 9. Mô tả status 205, 304 và HEAD mà không thêm schema body

### 205 Reset Content

`205 Reset Content` thông báo rằng server đã thực hiện request và yêu cầu user agent reset nội dung hiển thị. Server không được tạo content trong response 205 và phải thể hiện response có độ dài bằng zero theo quy tắc HTTP.

OpenAPI:

```yaml
'205':
  description: Request hoàn tất; client cần reset nội dung hiển thị.
```

Không thêm `content` nếu response không có body.

### 304 Not Modified

`304 Not Modified` được dùng trong conditional GET hoặc HEAD khi representation chưa thay đổi so với validator client gửi. Response không có content; client sử dụng representation đã lưu trong cache.

OpenAPI:

```yaml
'304':
  description: Representation chưa thay đổi; client có thể dùng bản cache.
  headers:
    ETag:
      description: Validator của representation hiện tại.
      schema:
        type: string
```

304 thường được tạo bởi cơ chế conditional request hoặc tầng web/cache. Không mô tả nó như một response JSON rỗng.

### HEAD

Request HEAD yêu cầu metadata tương ứng với GET nhưng không nhận response content. Nếu tài liệu mô tả operation HEAD, không khai báo schema body cho response. Header như `Content-Type` hoặc `Content-Length` có thể mang ý nghĩa metadata tương ứng với representation của GET theo quy tắc HTTP HEAD; điều đó không có nghĩa HEAD trả body.

## 10. Cách đọc OpenAPI để xác nhận response không có content

Sau khi ứng dụng chạy, mở `/v3/api-docs` hoặc URL group tương ứng. Response 204 mong đợi có dạng:

```json
{
  "description": "Sản phẩm đã được xóa thành công; response không có body."
}
```

Đối tượng response có thể chứa thêm `headers`, `links` hoặc extension phù hợp, nhưng không nên có trường `content`.

Có thể dùng `curl` và `jq` để kiểm tra:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/products/{id}"].delete.responses["204"]'
```

Kiểm tra `content` không tồn tại:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/products/{id}"].delete.responses["204"] | has("content")'
```

Kết quả mong đợi là `false`. Nếu kết quả là `true`, mở object response để xác định schema hoặc media type nào đã được thêm vào.

## 11. Kiểm thử cả HTTP response và tài liệu OpenAPI

Một kiểm thử controller nên xác nhận status 204 và body rỗng:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ProductService productService;

    @Test
    void deleteReturnsNoContentWithoutBody() throws Exception {
        mockMvc.perform(delete("/api/products/42"))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""));
    }
}
```

`@MockitoBean` thuộc Spring Test 6.2 trở lên (thường dùng với Spring Boot 3.4+ hoặc 4). Với phiên bản cũ hơn, dùng `@MockBean` từ `org.springframework.boot.test.mock.mockito.MockBean`. Test cần mock service và cấu hình security phù hợp với ứng dụng.

Ngoài kiểm thử runtime, cần kiểm tra OpenAPI document:

```java
@Test
void deleteOperationDocuments204WithoutContent() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/api/products/{id}'].delete.responses['204'].content"
        ).doesNotExist());
}
```

Nếu ứng dụng bảo vệ endpoint API Docs bằng Spring Security, test cần cấu hình authentication hoặc test security phù hợp. Với nhiều group, kiểm tra URL tài liệu của group chứa operation đang xét.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tài liệu 204 có schema `ProductResponse` | Method trả DTO dù runtime dự định không có body | Đổi sang `ResponseEntity<Void>` hoặc `void` với status 204 |
| Swagger UI hiển thị JSON body cho DELETE 204 | Annotation có `@Content` hoặc schema suy luận từ return type | Bỏ content khỏi response 204 và kiểm tra JSON OpenAPI |
| API trả 200 rỗng thay vì 204 | Không đặt status rõ ràng | Dùng `ResponseEntity.noContent()` hoặc `@ResponseStatus(NO_CONTENT)` |
| API trả `{}` hoặc `data: null` | Controller trả DTO/wrapper có body | Dùng `Void` nếu hợp đồng thực sự không có content |
| Response 204 có `Content-Length` hoặc body | Response bị xử lý như response thông thường hoặc có filter ghi content | Kiểm tra filter, advice, servlet response và test ở HTTP layer |
| Response 204 không có mô tả | Chỉ dựa vào suy luận tự động hoặc thiếu annotation | Khai báo `@ApiResponse(responseCode = "204", description = "...")` |
| 204 bị gắn response lỗi chung không phù hợp | Generic response/customizer áp dụng quá rộng | Kiểm tra `@ControllerAdvice`, `override-with-generic-response` và customizer |
| Schema chỉ sai ở một group | Group có customizer hoặc endpoint khác kiểu trả về | Kiểm tra trực tiếp OpenAPI document của group đó |

## 13. Checklist cho response không có body

- [ ] Đã chọn status code đúng với semantics HTTP; không dùng 204 cho thao tác còn đang xử lý.
- [ ] Controller dùng `ResponseEntity<Void>` hoặc `void` với `@ResponseStatus(NO_CONTENT)` khi chỉ trả 204.
- [ ] Không trả DTO rỗng, wrapper generic hoặc `null` để giả lập no-content.
- [ ] `@ApiResponse` của 204 có `responseCode` và `description`, không khai báo `content`.
- [ ] OpenAPI Response Object 204 không có `content` hoặc schema giả.
- [ ] Nếu cần header metadata, mô tả trong `responses.204.headers`.
- [ ] Response có body ở status khác được mô tả riêng bằng media type và schema phù hợp.
- [ ] Đã kiểm tra ảnh hưởng của generic response, `@ControllerAdvice` và customizer.
- [ ] Test runtime xác nhận status 204 và body rỗng.
- [ ] Test OpenAPI xác nhận response 204 không có trường `content`.
- [ ] Đã kiểm tra từng group tài liệu được công bố.

Một response không có body cần được thể hiện rõ từ controller đến tài liệu. Dùng `ResponseEntity<Void>` hoặc `void` với status phù hợp để Spring trả đúng HTTP semantics; dùng `@ApiResponse` không có `content` để OpenAPI không tạo schema giả. Kiểm thử cả response HTTP và JSON OpenAPI giúp tránh tình trạng tài liệu yêu cầu client đọc một payload mà server không bao giờ gửi.
