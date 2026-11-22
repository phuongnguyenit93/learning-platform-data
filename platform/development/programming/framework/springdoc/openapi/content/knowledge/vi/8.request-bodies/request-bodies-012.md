# Chọn mô hình tài liệu rõ ràng cho yêu cầu PATCH và cập nhật từng phần

HTTP `PATCH` được dùng khi client chỉ muốn thay đổi một phần tài nguyên. Tuy nhiên, từ “một phần” chưa đủ để xác định request body có ý nghĩa gì. Khi client bỏ qua một field, server giữ nguyên giá trị hiện tại hay xóa field đó? Khi client gửi `null`, server hiểu là xóa giá trị, lưu giá trị null hay từ chối? Nếu body là một mảng thao tác, thứ tự áp dụng từng thao tác ra sao?

Một API PATCH cần chọn và công bố rõ mô hình cập nhật. Những lựa chọn phổ biến là JSON Merge Patch theo RFC 7396, JSON Patch theo RFC 6902 hoặc DTO cập nhật từng phần do ứng dụng tự định nghĩa. Springdoc có thể mô tả media type, schema, field và response của từng mô hình. Tài liệu chỉ hữu ích khi semantics trong OpenAPI khớp với cách controller thực sự áp dụng request.

## 1. PATCH khác PUT ở đâu?

`PUT` thường biểu diễn việc thay thế trạng thái của tài nguyên tại URI bằng representation mà client gửi. `PATCH` biểu diễn một tập thay đổi cần áp dụng lên tài nguyên hiện tại. Khác biệt này ảnh hưởng trực tiếp đến schema request và ý nghĩa của field bị thiếu.

Ví dụ tài nguyên hiện tại:

```json
{
  "id": 42,
  "name": "Keyboard",
  "description": "Mechanical keyboard",
  "price": 1290000,
  "active": true
}
```

Một request PUT có thể gửi representation đầy đủ:

```http
PUT /api/products/42
Content-Type: application/json
```

```json
{
  "name": "Keyboard Pro",
  "description": "Wireless mechanical keyboard",
  "price": 1590000,
  "active": true
}
```

Trong khi đó, một request PATCH có thể chỉ gửi field cần thay đổi:

```http
PATCH /api/products/42
Content-Type: application/merge-patch+json
```

```json
{
  "price": 1590000
}
```

Client cần biết chính xác quy tắc của body PATCH. Nếu không, việc bỏ qua `description` hoặc gửi `description: null` có thể dẫn đến kết quả khác với kỳ vọng.

## 2. Ba trạng thái cần phân biệt trong cập nhật từng phần

Đối với một field có thể chỉnh sửa, request thường cần thể hiện ba ý định:

| Trạng thái trong request | Ý nghĩa thường dùng |
|---|---|
| Field không xuất hiện | Giữ nguyên giá trị hiện tại |
| Field xuất hiện với giá trị khác null | Cập nhật thành giá trị mới |
| Field xuất hiện với `null` | Xóa giá trị, đặt null hoặc từ chối theo quy tắc API đã công bố |

Vấn đề là nhiều DTO Java thông thường không giữ được sự khác biệt giữa “field bị bỏ qua” và “field được gửi rõ ràng là null”. Khi Jackson deserialize JSON vào một property có kiểu `String`, cả hai trường hợp có thể trở thành Java `null`.

Ví dụ DTO đơn giản:

```java
public record ProductPatchRequest(
    String name,
    String description
) {
}
```

Với DTO này, sau khi deserialize, `description == null` không cho biết client đã bỏ qua field hay gửi:

```json
{
  "description": null
}
```

Nếu nghiệp vụ cần phân biệt hai ý định đó, cần một mô hình dữ liệu có thể biểu diễn trạng thái “không được cung cấp” riêng với “được cung cấp nhưng null”.

## 3. Chọn một trong ba mô hình request body

| Mô hình | Media type điển hình | Cấu trúc body | Phù hợp khi |
|---|---|---|---|
| JSON Merge Patch | `application/merge-patch+json` | Object thể hiện những field cần merge; null có nghĩa xóa member | Muốn cập nhật object theo quy tắc merge đơn giản, phổ biến |
| JSON Patch | `application/json-patch+json` | Mảng thao tác như `add`, `remove`, `replace`, `move`, `copy`, `test` | Cần chỉ định chính xác đường dẫn, thứ tự hoặc thao tác trên array/nested value |
| DTO PATCH tùy chỉnh | Thường là `application/json` | Object riêng chỉ chứa những field được phép cập nhật | Muốn hợp đồng đơn giản, giới hạn field và áp dụng quy tắc nghiệp vụ riêng |

Không nên dùng cùng một media type cho các body có semantics khác nhau mà không mô tả rõ. `application/json` tự nó không nói body là JSON Merge Patch hay JSON Patch. Nếu API dùng DTO riêng, hãy nói rõ ý nghĩa của field bị thiếu và field null trong description/schema.

## 4. JSON Merge Patch theo RFC 7396

JSON Merge Patch dùng media type `application/merge-patch+json`. Body thường là một JSON object chứa những field muốn thay đổi. Quy tắc cốt lõi:

- Field không có trong patch giữ nguyên giá trị hiện tại.
- Field có giá trị khác null được thêm hoặc thay thế trong tài nguyên đích.
- Field có giá trị null bị xóa khỏi object đích.
- Object lồng nhau được merge đệ quy.
- Array được thay thế như một giá trị hoàn chỉnh; Merge Patch không cập nhật từng phần tử array theo index.

Ví dụ tài nguyên hiện tại:

```json
{
  "name": "Keyboard",
  "description": "Mechanical keyboard",
  "manufacturer": {
    "name": "Acme",
    "country": "VN"
  },
  "tags": ["office", "wireless"]
}
```

Patch:

```json
{
  "name": "Keyboard Pro",
  "description": null,
  "manufacturer": {
    "country": "JP"
  },
  "tags": ["wireless", "gaming"]
}
```

Kết quả sau khi áp dụng:

```json
{
  "name": "Keyboard Pro",
  "manufacturer": {
    "name": "Acme",
    "country": "JP"
  },
  "tags": ["wireless", "gaming"]
}
```

`description` bị xóa; `manufacturer.name` được giữ nguyên vì không có trong patch; `manufacturer.country` được cập nhật; toàn bộ `tags` được thay thế.

### Giới hạn của JSON Merge Patch

Theo RFC 7396, null mang nghĩa xóa member. Vì vậy, JSON Merge Patch không thể phân biệt một cách trực tiếp giữa “đặt field thành JSON null” và “xóa field khỏi object”. Nếu nghiệp vụ cần lưu một giá trị null có ý nghĩa riêng, hãy chọn JSON Patch hoặc một DTO tùy chỉnh có semantics rõ ràng.

Ngoài ra, patch document ở cấp gốc có thể là bất kỳ JSON value nào theo RFC; nếu API chỉ cho phép cập nhật một resource object, server nên xác thực body là object và từ chối kiểu dữ liệu khác. Điều này cần được thể hiện trong schema và mô tả endpoint.

## 5. Mô tả JSON Merge Patch trong Springdoc

Trong Spring MVC, có thể nhận body dạng `JsonNode` để giữ nguyên cấu trúc và phân biệt field không có với field có giá trị null. `JsonNode` cũng phù hợp khi cần chuyển patch document cho một thư viện hoặc bộ xử lý tuân theo RFC 7396.

Ví dụ mô tả schema dành cho tài liệu:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "ProductMergePatch", description = "Các field sản phẩm có thể cập nhật theo JSON Merge Patch")
public class ProductMergePatchDocument {

    @Schema(
        description = "Tên mới; bỏ qua để giữ nguyên, null xóa field nếu nghiệp vụ cho phép",
        nullable = true
    )
    public String name;

    @Schema(
        description = "Mô tả mới; bỏ qua để giữ nguyên, null xóa mô tả",
        nullable = true
    )
    public String description;

    @Schema(
        description = "Giá mới; bỏ qua để giữ nguyên",
        nullable = true,
        example = "1590000"
    )
    public Long price;
}
```

Controller có thể khai báo media type và schema request một cách tường minh:

```java
import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @PatchMapping(
        value = "/{id}",
        consumes = "application/merge-patch+json"
    )
    @Operation(
        summary = "Cập nhật một phần sản phẩm",
        description = "Áp dụng JSON Merge Patch theo RFC 7396. Field bị bỏ qua giữ nguyên; field null bị xóa theo quy tắc Merge Patch."
    )
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        description = "JSON Merge Patch document",
        content = @Content(
            mediaType = "application/merge-patch+json",
            schema = @Schema(implementation = ProductMergePatchDocument.class)
        )
    )
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Cập nhật thành công"),
        @ApiResponse(responseCode = "400", description = "Patch document không hợp lệ"),
        @ApiResponse(responseCode = "404", description = "Không tìm thấy sản phẩm"),
        @ApiResponse(responseCode = "409", description = "Xung đột với trạng thái hiện tại"),
        @ApiResponse(responseCode = "415", description = "Media type không được hỗ trợ")
    })
    ResponseEntity<ProductResponse> patch(
        @PathVariable Long id,
        @org.springframework.web.bind.annotation.RequestBody JsonNode patchDocument
    ) {
        if (!patchDocument.isObject()) {
            return ResponseEntity.badRequest().build();
        }

        ProductResponse updated = productService.applyMergePatch(id, patchDocument);
        return ResponseEntity.ok(updated);
    }
}
```

`ProductMergePatchDocument` mô tả schema công khai; controller nhận `JsonNode` để xử lý đúng trạng thái của từng member. `productService.applyMergePatch` đại diện cho phần xử lý nghiệp vụ: lấy tài nguyên hiện tại, áp dụng thuật toán RFC 7396, kiểm tra các field được phép sửa và lưu kết quả. Hãy dùng implementation Merge Patch đã được kiểm thử hoặc viết bộ xử lý tuân thủ RFC; không chỉ deserialize vào DTO thông thường rồi tự suy đoán field nào đã được gửi.

`consumes` giúp Spring mapping và tài liệu thể hiện đúng media type. Annotation Swagger `RequestBody` ở đây được viết bằng tên đầy đủ để tránh nhầm với `@RequestBody` của Spring MVC. `required = true` nói rằng HTTP request phải có body; điều đó không có nghĩa tất cả field trong schema đều bắt buộc.

## 6. JSON Patch theo RFC 6902

JSON Patch dùng media type `application/json-patch+json`. Body là một mảng operation được áp dụng tuần tự lên tài nguyên. Các operation chuẩn gồm:

| Operation | Ý nghĩa | Field bổ sung |
|---|---|---|
| `add` | Thêm giá trị tại path; với object, có thể thay giá trị member đã tồn tại | `value` |
| `remove` | Xóa giá trị tại path | Không có |
| `replace` | Thay giá trị tại path đã tồn tại | `value` |
| `move` | Di chuyển giá trị từ path nguồn sang path đích | `from` |
| `copy` | Sao chép giá trị từ path nguồn sang path đích | `from` |
| `test` | Kiểm tra giá trị tại path có bằng giá trị mong đợi không | `value` |

Ví dụ:

```http
PATCH /api/products/42 HTTP/1.1
Content-Type: application/json-patch+json
```

```json
[
  { "op": "replace", "path": "/name", "value": "Keyboard Pro" },
  { "op": "remove", "path": "/description" },
  { "op": "add", "path": "/tags/-", "value": "featured" }
]
```

Các operation được áp dụng theo thứ tự trong mảng. `path` và `from` sử dụng JSON Pointer. Ký tự `/` trong tên member được escape thành `~1`, còn `~` được escape thành `~0`. Ký hiệu `-` ở cuối path array dùng để thêm phần tử vào cuối mảng.

JSON Patch phù hợp khi client cần thay đổi chính xác một phần tử trong array, di chuyển giá trị hoặc kiểm tra điều kiện trước khi sửa. Đổi lại, body phức tạp hơn và server cần xác thực path, operation, quyền cập nhật từng field cùng giới hạn thao tác. Không nên cho phép client sửa tùy ý các property nội bộ hoặc field nhạy cảm chỉ vì JSON Pointer có thể truy cập đến chúng.

### Mô tả JSON Patch trong OpenAPI

Một schema operation đơn giản để trình bày có thể như sau:

```java
import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "JsonPatchOperation")
public class JsonPatchOperationDocument {

    @Schema(
        description = "Loại thao tác",
        allowableValues = {"add", "remove", "replace", "move", "copy", "test"},
        example = "replace"
    )
    public String op;

    @Schema(description = "JSON Pointer đến vị trí đích", example = "/name")
    public String path;

    @Schema(description = "Giá trị dùng cho add, replace hoặc test")
    public JsonNode value;

    @Schema(description = "JSON Pointer nguồn dùng cho move hoặc copy", example = "/oldName")
    public String from;
}
```

Một operation object thực tế có yêu cầu field khác nhau tùy `op`: `remove` không cần `value`, còn `move` và `copy` cần `from`. Một DTO phẳng chỉ liệt kê tất cả field không thể hiện đầy đủ các điều kiện này. Với hợp đồng nghiêm ngặt, nên mô tả schema bằng `oneOf` cho từng operation variant hoặc dùng schema JSON Patch chuẩn đã được kiểm tra.

Controller có thể mô tả body là mảng operation:

```java
@PatchMapping(value = "/{id}", consumes = "application/json-patch+json")
@io.swagger.v3.oas.annotations.parameters.RequestBody(
    required = true,
    description = "Danh sách JSON Patch operation theo RFC 6902",
    content = @Content(
        mediaType = "application/json-patch+json",
        array = @io.swagger.v3.oas.annotations.media.ArraySchema(
            schema = @Schema(implementation = JsonPatchOperationDocument.class)
        )
    )
)
ResponseEntity<ProductResponse> patchJson(
    @PathVariable Long id,
    @org.springframework.web.bind.annotation.RequestBody JsonNode operations
) {
    ProductResponse updated = productService.applyJsonPatch(id, operations);
    return ResponseEntity.ok(updated);
}
```

Phần `applyJsonPatch` cần dùng thư viện hoặc bộ xử lý tuân thủ RFC 6902, áp dụng operation theo thứ tự và từ chối patch sai định dạng hoặc path không hợp lệ. Không nên tự viết một bộ xử lý JSON Pointer/JSON Patch rút gọn cho production nếu chưa bao phủ các quy tắc của RFC.

## 7. DTO PATCH tùy chỉnh cho nghiệp vụ đơn giản

Không phải API nào cũng cần áp dụng đầy đủ RFC 7396 hoặc RFC 6902. Nếu chỉ cho phép thay đổi một số field và muốn giữ hợp đồng đơn giản, có thể tạo DTO PATCH riêng.

Ví dụ body:

```http
PATCH /api/products/42
Content-Type: application/json
```

```json
{
  "name": "Keyboard Pro",
  "active": false
}
```

Hợp đồng có thể quy định:

- Field bị bỏ qua giữ nguyên giá trị hiện tại.
- Field có giá trị hợp lệ được cập nhật.
- Field null bị từ chối hoặc được dùng để xóa giá trị theo từng field.
- Những field không được phép sửa sẽ bị từ chối hoặc bị bỏ qua theo chính sách được công bố.

Nếu null luôn có nghĩa “không cập nhật”, DTO thông thường có thể đủ dùng. Nếu cần phân biệt field bị bỏ qua với field được gửi null, có thể dùng wrapper `JsonNullable<T>` của thư viện `jackson-databind-nullable`.

### Phân biệt undefined và null bằng `JsonNullable`

Dependency Maven:

```xml
<dependency>
    <groupId>org.openapitools</groupId>
    <artifactId>jackson-databind-nullable</artifactId>
    <version>${jackson-databind-nullable.version}</version>
</dependency>
```

Đăng ký module Jackson:

```java
import com.fasterxml.jackson.databind.Module;
import org.openapitools.jackson.nullable.JsonNullableModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonConfiguration {

    @Bean
    Module jsonNullableModule() {
        return new JsonNullableModule();
    }
}
```

DTO cần khởi tạo property ở trạng thái undefined để field bị thiếu vẫn được nhận diện là chưa cung cấp:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import org.openapitools.jackson.nullable.JsonNullable;

public class ProductPatchRequest {

    @Schema(
        description = "Tên mới; undefined giữ nguyên, null được xử lý theo quy tắc xóa",
        nullable = true
    )
    private JsonNullable<String> name = JsonNullable.undefined();

    @Schema(
        description = "Mô tả mới; undefined giữ nguyên, null xóa mô tả",
        nullable = true
    )
    private JsonNullable<String> description = JsonNullable.undefined();

    public JsonNullable<String> getName() {
        return name;
    }

    public void setName(JsonNullable<String> name) {
        this.name = name;
    }

    public JsonNullable<String> getDescription() {
        return description;
    }

    public void setDescription(JsonNullable<String> description) {
        this.description = description;
    }
}
```

Khi module được đăng ký và Jackson deserialize đúng:

- JSON không có `name`: property giữ trạng thái `JsonNullable.undefined()`.
- JSON có `"name": null`: property biểu diễn giá trị null đã được cung cấp.
- JSON có `"name": "Keyboard Pro"`: property biểu diễn giá trị mới.

Phần áp dụng patch cần kiểm tra trạng thái trước khi đọc giá trị:

```java
if (patch.getName().isPresent()) {
    String newName = patch.getName().get();
    if (newName == null) {
        product.clearName();
    } else {
        product.rename(newName);
    }
}
```

Đoạn code minh họa quy tắc nghiệp vụ: field undefined không thay đổi; field có giá trị null xóa tên; field có chuỗi thì đổi tên. Nếu domain không cho phép tên null, hãy trả lỗi validation thay vì gọi `clearName()`.

Khi dùng `JsonNullable`, cần kiểm tra schema Springdoc sinh ra. Kiểu wrapper, nullable và required có thể được biểu diễn khác nhau tùy phiên bản thư viện và OpenAPI dialect. Hãy tùy chỉnh schema nếu tài liệu không thể hiện rõ ba trạng thái mà API hỗ trợ. Không được chỉ dựa vào kiểu Java để kết luận schema đã đúng.

## 8. Mô tả Request Body và media type bằng Springdoc

Springdoc thường suy luận request body từ `@RequestBody`, kiểu tham số và `consumes` của Spring mapping. Khi API dùng media type đặc biệt hoặc body có semantics riêng, nên mô tả tường minh bằng Swagger `@RequestBody` và `@Content`.

| Nội dung | Nơi mô tả |
|---|---|
| HTTP method và path | `@PatchMapping` hoặc `@RequestMapping` của Spring |
| Media type được chấp nhận | Thuộc tính `consumes` và `requestBody.content` |
| Schema body | DTO, `@Schema`, `@ArraySchema` hoặc schema tùy chỉnh |
| Body có bắt buộc không | `@RequestBody(required = true)` của Swagger và binding của Spring |
| Ý nghĩa field bị thiếu/null | Description của request body/property và quy tắc nghiệp vụ |
| Response thành công/lỗi | `@ApiResponse`, `@ApiResponses`, response type |

Có hai annotation cùng tên `RequestBody`:

```java
org.springframework.web.bind.annotation.RequestBody
```

Annotation Spring gắn HTTP body vào tham số controller.

```java
io.swagger.v3.oas.annotations.parameters.RequestBody
```

Annotation Swagger mô tả body trong OpenAPI. Nếu dùng cả hai trong cùng method, có thể import một loại và viết tên đầy đủ cho loại còn lại để tránh nhầm lẫn.

`required = true` ở Request Body Object nói rằng request cần có body. Nó không tự làm cho mọi property của DTO trở thành required. Với PATCH, thông thường body bắt buộc nhưng từng field đều có thể tùy chọn; schema cần phản ánh điều đó.

## 9. Validation khi áp dụng patch

Validation của PATCH cần xem xét cả request document và trạng thái tài nguyên sau khi cập nhật.

**Kiểm tra request document:**

- Body có đúng media type không?
- Body có đúng kiểu JSON object hoặc array theo mô hình đã chọn không?
- Có field không được phép cập nhật không?
- JSON Patch có operation, path, from và value hợp lệ không?
- Có giới hạn kích thước body, số operation hoặc độ sâu lồng nhau không?

**Kiểm tra trạng thái sau cập nhật:**

- Các field bắt buộc của domain có còn hợp lệ không?
- Các quy tắc liên trường có được thỏa mãn không?
- Giá trị mới có nằm trong miền cho phép không?
- Trạng thái chuyển đổi có hợp lệ không, ví dụ không cho sửa đơn hàng đã hoàn tất?

Không nên áp dụng `@NotNull` hoặc `@NotBlank` một cách máy móc lên DTO PATCH nếu field bị bỏ qua là hợp lệ. Với JSON Merge Patch, null có nghĩa xóa member; sau khi merge, domain validator cần xác định resource có còn hợp lệ không. Với DTO tùy chỉnh, chỉ validate field được cung cấp và sau đó validate aggregate/resource hoàn chỉnh.

Các response thường cần mô tả gồm:

| HTTP status | Tình huống |
|---|---|
| `200 OK` | PATCH thành công và trả representation mới |
| `204 No Content` | PATCH thành công nhưng không trả body |
| `400 Bad Request` | JSON sai cú pháp hoặc patch document không hợp lệ |
| `404 Not Found` | Không tìm thấy tài nguyên |
| `409 Conflict` | Xung đột với trạng thái hoặc quy tắc nghiệp vụ hiện tại |
| `412 Precondition Failed` | Điều kiện `If-Match` không thỏa mãn |
| `415 Unsupported Media Type` | Client gửi media type không được endpoint hỗ trợ |
| `422 Unprocessable Content` | Nội dung hợp lệ về cú pháp nhưng không thể áp dụng theo quy tắc nghiệp vụ |

Chọn status code theo chính sách API và cách hệ thống xử lý lỗi; không cần trả tất cả mã cho mọi endpoint.

## 10. Kiểm soát cập nhật đồng thời bằng ETag và If-Match

Hai client có thể cùng đọc một tài nguyên rồi gửi patch dựa trên cùng trạng thái cũ. Nếu server áp dụng tuần tự mà không kiểm tra phiên bản, bản cập nhật sau có thể ghi đè thay đổi của client trước.

ETag và `If-Match` hỗ trợ optimistic concurrency. Server trả ETag khi đọc tài nguyên; client gửi lại ETag trong request PATCH. Nếu tài nguyên đã thay đổi và ETag không còn khớp, server trả `412 Precondition Failed`.

Ví dụ:

```http
PATCH /api/products/42 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "product-42-v7"
```

`If-Match` là header điều kiện HTTP thông thường, không phải credentials. Có thể mô tả bằng header parameter:

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;

@Parameter(
    name = "If-Match",
    in = ParameterIn.HEADER,
    description = "ETag hiện tại của tài nguyên để tránh ghi đè cập nhật đồng thời",
    required = true,
    example = "\"product-42-v7\""
)
```

Đặt `@Parameter` trên tham số controller tương ứng với `@RequestHeader("If-Match")`. Server phải thực sự so sánh validator với phiên bản hiện tại và trả `412` khi không khớp; chỉ thêm parameter vào OpenAPI không tạo ra kiểm soát đồng thời.

## 11. PATCH có idempotent không?

Không nên mặc định rằng mọi PATCH đều idempotent. Tính idempotent phụ thuộc semantics của patch document và cách server áp dụng nó.

- Một JSON Merge Patch đặt `price` thành cùng một giá trị thường đưa tài nguyên về cùng trạng thái nếu gửi lặp lại.
- Một JSON Patch `replace /name` với cùng giá trị thường cho cùng trạng thái cuối.
- Một JSON Patch `add /tags/-` có thể thêm một phần tử mới mỗi lần gửi, nên gửi lặp lại tạo trạng thái khác.
- Side effect như ghi lịch sử, gửi thông báo hoặc tính phí có thể làm request lặp lại tạo tác động bổ sung dù resource cuối giống nhau.

Nếu client cần retry an toàn, hãy thiết kế semantics rõ, cân nhắc `If-Match`, idempotency key cho nghiệp vụ phù hợp và xử lý side effect trong transaction/outbox. Mô tả API nên nói rõ những giới hạn retry mà client cần biết.

## 12. Kiểm tra OpenAPI và thử request PATCH

Sau khi cấu hình, mở `/v3/api-docs` và kiểm tra:

- Operation có đúng method `patch` và path không?
- `requestBody.required` có đúng không?
- `requestBody.content` có đúng media type không?
- Schema có thể hiện object Merge Patch, array JSON Patch hoặc DTO riêng không?
- Field tùy chọn có được đánh dấu required sai không?
- Description có nói rõ ý nghĩa của field thiếu và null không?
- Response có mô tả các status code mà server thực sự trả về không?
- Header `If-Match` có được mô tả nếu endpoint dùng optimistic concurrency không?

Ví dụ thử JSON Merge Patch:

```bash
curl -i -X PATCH http://localhost:8080/api/products/42 \
  -H "Content-Type: application/merge-patch+json" \
  -d '{"price":1590000,"description":null}'
```

Ví dụ thử JSON Patch:

```bash
curl -i -X PATCH http://localhost:8080/api/products/42 \
  -H "Content-Type: application/json-patch+json" \
  -d '[{"op":"replace","path":"/name","value":"Keyboard Pro"}]'
```

Ví dụ thử DTO PATCH tùy chỉnh:

```bash
curl -i -X PATCH http://localhost:8080/api/products/42 \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard Pro","active":false}'
```

Không dùng lẫn media type giữa ba ví dụ. Nếu gửi JSON Merge Patch vào endpoint chỉ nhận `application/json`, Spring có thể trả `415 Unsupported Media Type` theo cấu hình mapping.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gửi một field nhưng field khác bị xóa | DTO được deserialize thành null và service xem null là xóa | Phân biệt undefined/null hoặc dùng JSON Merge Patch đúng chuẩn |
| Không thể đặt field thành null | JSON Merge Patch xem null là xóa member | Dùng JSON Patch hoặc DTO tùy chỉnh nếu cần semantics set-null |
| Thay một phần tử array nhưng các phần tử khác biến mất | JSON Merge Patch thay cả array | Dùng JSON Patch hoặc endpoint thao tác collection chuyên biệt |
| Swagger UI hiển thị body là `application/json` | `consumes` hoặc `@Content.mediaType` chưa khai báo rõ | Đồng bộ media type trong Spring mapping và OpenAPI |
| Tất cả field PATCH bị đánh dấu required | Schema kế thừa DTO dùng cho create/replace hoặc annotation required sai | Dùng schema PATCH riêng và đánh dấu field tùy chọn |
| JSON Patch thất bại vì path | JSON Pointer sai, escape sai hoặc path không tồn tại | Kiểm tra `path`, `from`, thứ tự operation và schema tài nguyên |
| Body hợp lệ nhưng không lưu được | Trạng thái sau merge vi phạm validation/domain rule | Validate resource sau khi áp dụng patch |
| Hai client ghi đè thay đổi của nhau | Không có kiểm soát optimistic concurrency | Dùng ETag/If-Match hoặc cơ chế version phù hợp |

## 14. Checklist chọn và mô tả mô hình PATCH

- [ ] Đã xác định API dùng JSON Merge Patch, JSON Patch hay DTO PATCH riêng.
- [ ] Đã chọn media type đúng với semantics của body.
- [ ] Đã quy định rõ field bị bỏ qua có nghĩa gì.
- [ ] Đã quy định rõ field null có nghĩa xóa, đặt null hay bị từ chối.
- [ ] Đã xác định cách xử lý object lồng nhau và array.
- [ ] Schema OpenAPI thể hiện đúng field tùy chọn, nullable và operation body.
- [ ] `@PatchMapping(consumes = ...)` khớp với `requestBody.content`.
- [ ] Response mô tả các lỗi cú pháp, validation, trạng thái và media type phù hợp.
- [ ] Đã kiểm tra quyền sửa từng field và giới hạn patch document.
- [ ] Đã kiểm tra trạng thái tài nguyên sau khi áp dụng patch.
- [ ] Có chiến lược chống ghi đè cập nhật đồng thời nếu nghiệp vụ yêu cầu.
- [ ] Đã thử request thật và đối chiếu JSON/YAML OpenAPI được sinh.

Một hợp đồng PATCH tốt phải cho client biết chính xác body được diễn giải ra sao. JSON Merge Patch phù hợp với cập nhật object theo quy tắc merge; JSON Patch phù hợp với chuỗi thao tác chính xác; DTO PATCH riêng phù hợp với quy tắc nghiệp vụ giới hạn. Springdoc giúp công bố media type, schema và response, còn controller/service chịu trách nhiệm thực hiện đúng semantics đã mô tả.
