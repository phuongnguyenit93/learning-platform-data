# Sắp xếp tag, operation và mức mở rộng mặc định

Swagger UI trình bày các operation theo nhóm tag và cho phép người dùng mở rộng từng nhóm để xem chi tiết request, response và schema. Với API có nhiều endpoint, thứ tự tag, thứ tự operation và trạng thái mở rộng ban đầu ảnh hưởng trực tiếp tới khả năng tìm kiếm thông tin. Springdoc-openapi cung cấp các thuộc tính cấu hình để sắp xếp tag/operation và điều khiển mức mở rộng của tài liệu. Có thể kết hợp chúng với thứ tự tag được khai báo trong OpenAPI để tạo giao diện nhất quán.

## 1. Ba quyết định giao diện cần phân biệt

Khi cấu hình Swagger UI, cần phân biệt ba vấn đề:

1. **Thứ tự tag:** các nhóm như Products, Orders, Accounts xuất hiện theo thứ tự nào.
2. **Thứ tự operation:** trong một tag, endpoint GET, POST, PUT, DELETE được sắp xếp ra sao.
3. **Mức mở rộng ban đầu:** Swagger UI mở sẵn toàn bộ operation, chỉ mở tên nhóm hay thu gọn tất cả.

Đây là các tùy chọn hiển thị. Chúng không thay đổi routing của Spring MVC, quyền truy cập, thứ tự thực thi request hoặc nội dung OpenAPI schema.

| Mục tiêu | Thuộc tính Swagger UI | Giá trị thường dùng |
|---|---|---|
| Sắp xếp tag theo tên | `tagsSorter` | `alpha` |
| Sắp xếp operation theo đường dẫn | `operationsSorter` | `alpha` |
| Sắp xếp operation theo HTTP method | `operationsSorter` | `method` |
| Thu gọn toàn bộ operation lúc mở trang | `docExpansion` | `none` |
| Mở tag nhưng thu gọn operation | `docExpansion` | `list` |
| Mở tất cả tag và operation | `docExpansion` | `full` |
| Ẩn khu vực Models | `defaultModelsExpandDepth` | `-1` |
| Điều khiển độ sâu schema trong Models | `defaultModelExpandDepth` | `1` hoặc giá trị phù hợp |

Không nên nhầm `docExpansion` với `defaultModelsExpandDepth`: thuộc tính đầu điều khiển phần danh sách operation, thuộc tính sau điều khiển khu vực Models ở cuối Swagger UI.

## 2. Tag là nhóm hiển thị của operation

Trong OpenAPI, operation có thể gắn một hoặc nhiều tag. Swagger UI dùng tag để nhóm các operation thành từng phần có thể thu gọn.

Ví dụ:

```yaml
paths:
  /api/products:
    get:
      tags:
        - Products
      summary: Tìm kiếm sản phẩm
      responses:
        '200':
          description: Danh sách sản phẩm
    post:
      tags:
        - Products
      summary: Tạo sản phẩm
      responses:
        '201':
          description: Đã tạo sản phẩm
  /api/orders:
    get:
      tags:
        - Orders
      summary: Tìm kiếm đơn hàng
      responses:
        '200':
          description: Danh sách đơn hàng
```

Swagger UI sẽ có nhóm `Products` chứa hai operation và nhóm `Orders` chứa một operation. Tên tag trong operation phải khớp với tên tag được định nghĩa ở cấp tài liệu nếu muốn cung cấp description và metadata chung.

### Gắn tag bằng annotation

Có thể gắn `@Tag` ở cấp controller để các operation trong controller dùng cùng nhóm:

```java
import io.swagger.v3.oas.annotations.tags.Tag;

@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Quản lý và tra cứu sản phẩm")
class ProductController {

    @GetMapping
    List<ProductResponse> search() {
        return productService.search();
    }

    @PostMapping
    ProductResponse create(@RequestBody CreateProductRequest request) {
        return productService.create(request);
    }
}
```

Nếu một controller có operation thuộc nhiều nhóm khác nhau, có thể gắn tag ở từng operation:

```java
@Operation(tags = {"Products", "Catalog"})
@GetMapping("/{id}")
ProductResponse getById(@PathVariable UUID id) {
    return productService.getById(id);
}
```

Một operation có nhiều tag có thể xuất hiện trong nhiều nhóm trong Swagger UI. Chỉ nên làm vậy khi người dùng thực sự cần tìm operation từ nhiều góc nhìn; nếu gắn tag tràn lan, tài liệu sẽ có nhiều bản hiển thị gây khó định hướng.

## 3. Khai báo thứ tự tag trong OpenAPI

OpenAPI cho phép khai báo danh sách tag ở cấp root document. Thứ tự các phần tử trong danh sách này có thể được dùng để thể hiện thứ tự nhóm operation. Nếu muốn thứ tự thủ công, hãy khai báo tag theo thứ tự mong muốn và không bật `tagsSorter` tự động.

Ví dụ YAML:

```yaml
openapi: 3.1.0
info:
  title: Store API
  version: 1.0.0
tags:
  - name: Products
    description: Tạo, cập nhật và tìm kiếm sản phẩm
  - name: Orders
    description: Quản lý đơn hàng và trạng thái xử lý
  - name: Accounts
    description: Tài khoản và thông tin người dùng
paths:
  /api/products:
    get:
      tags: [Products]
      summary: Tìm sản phẩm
      responses:
        '200':
          description: OK
  /api/orders:
    get:
      tags: [Orders]
      summary: Tìm đơn hàng
      responses:
        '200':
          description: OK
```

Khi Swagger UI không áp dụng `tagsSorter`, thứ tự khai báo tag trong OpenAPI document là cơ sở để hiển thị nhóm. Nếu đặt `tagsSorter: alpha`, thứ tự thủ công có thể bị thay thế bằng thứ tự chữ cái.

### Khai báo thứ tự tag bằng @OpenAPIDefinition

Trong Spring Boot, có thể khai báo metadata tag ở cấu hình OpenAPI:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Store API", version = "1.0.0"),
    tags = {
        @Tag(name = "Products", description = "Quản lý sản phẩm"),
        @Tag(name = "Orders", description = "Quản lý đơn hàng"),
        @Tag(name = "Accounts", description = "Quản lý tài khoản")
    }
)
class OpenApiConfiguration {}
```

Danh sách `tags` được khai báo theo thứ tự Products, Orders, Accounts. Các controller/operation phải dùng đúng tên tag tương ứng. Sau khi ứng dụng chạy, hãy kiểm tra mảng `tags` trong `/v3/api-docs` để xác nhận thứ tự tài liệu được sinh ra.

Nếu cần sắp xếp tag theo nghiệp vụ thay vì chữ cái, tránh bật `tagsSorter: alpha`. Nếu bật sorter, Swagger UI sẽ sắp xếp theo sorter dù danh sách tag trong OpenAPI được khai báo theo thứ tự khác.

## 4. Sắp xếp tag bằng tagsSorter

`tagsSorter` là tùy chọn của Swagger UI để sắp xếp nhóm tag. Giá trị phổ biến:

| Giá trị | Hành vi |
|---|---|
| Không khai báo | Dùng thứ tự tag trong OpenAPI document/logic mặc định của Swagger UI |
| `alpha` | Sắp xếp tag theo tên chữ cái |

Cấu hình springdoc trong `application.yml`:

```yaml
springdoc:
  swagger-ui:
    tags-sorter: alpha
```

Với cấu hình này, nhóm Accounts có thể xuất hiện trước Orders và Products theo thứ tự chữ cái. Nếu muốn thứ tự theo luồng nghiệp vụ như Authentication → Products → Orders → Reports, hãy khai báo thứ tự tag ở cấp OpenAPI và để `tags-sorter` không được cấu hình.

Không nên dựa vào thứ tự ngẫu nhiên của quá trình quét controller hoặc thứ tự file Java. Hãy khai báo tag root rõ ràng khi cần thứ tự có chủ đích.

## 5. Sắp xếp operation bằng operationsSorter

`operationsSorter` điều khiển thứ tự operation bên trong một tag. Swagger UI cung cấp hai lựa chọn chuỗi thường dùng:

| Giá trị | Hành vi |
|---|---|
| Không khai báo | Dùng thứ tự mặc định theo OpenAPI document/Swagger UI |
| `alpha` | Sắp xếp operation theo path |
| `method` | Sắp xếp theo HTTP method |

Cấu hình theo path:

```yaml
springdoc:
  swagger-ui:
    operations-sorter: alpha
```

Khi đó, các operation thường được sắp xếp theo đường dẫn, giúp người đọc tìm endpoint theo URL. Nếu API có nhiều thao tác CRUD và muốn gom theo HTTP method, có thể dùng:

```yaml
springdoc:
  swagger-ui:
    operations-sorter: method
```

`method` sắp xếp theo HTTP verb theo quy tắc của Swagger UI. Không nên giả định nó tạo thứ tự nghiệp vụ tùy chỉnh như GET → POST → PATCH → DELETE theo mọi phiên bản; nếu cần một thứ tự riêng, cần dùng khả năng custom sorter của Swagger UI và kiểm tra cấu hình tích hợp cụ thể.

### Ví dụ nhiều operation trong một tag

```yaml
paths:
  /api/products:
    get:
      tags: [Products]
      summary: Tìm sản phẩm
    post:
      tags: [Products]
      summary: Tạo sản phẩm
  /api/products/{id}:
    get:
      tags: [Products]
      summary: Xem chi tiết sản phẩm
    patch:
      tags: [Products]
      summary: Cập nhật sản phẩm
    delete:
      tags: [Products]
      summary: Xóa sản phẩm
```

Với `operationsSorter: alpha`, các operation được sắp xếp theo path; với `method`, thứ tự được quyết định theo HTTP method. Cấu hình sorter chỉ thay đổi cách trình bày trong Swagger UI, không thay đổi thứ tự route hoặc cách Spring xử lý request.

## 6. Điều khiển mức mở rộng bằng docExpansion

`docExpansion` quyết định Swagger UI mở rộng tag và operation tới mức nào khi người dùng tải trang.

| Giá trị | Trạng thái ban đầu | Phù hợp khi |
|---|---|---|
| `none` | Thu gọn các nhóm operation | Tài liệu lớn, người dùng chủ động mở nhóm cần xem |
| `list` | Mở nhóm tag, thu gọn operation bên trong | Muốn người dùng thấy danh sách nhóm ngay |
| `full` | Mở nhóm tag và chi tiết operation | API nhỏ hoặc tài liệu cần xem toàn bộ ngay |

Ví dụ:

```yaml
springdoc:
  swagger-ui:
    doc-expansion: none
```

Với `none`, trang Swagger UI tải nhanh và gọn hơn về mặt hiển thị đối với tài liệu có nhiều operation; người dùng mở từng tag để tìm endpoint. Với `list`, tên các tag hiển thị cùng danh sách operation có thể mở. Với `full`, các operation được mở rộng, khiến trang dài hơn đáng kể.

Giá trị mặc định thường gặp của Swagger UI là `list`. Nên khai báo tường minh nếu muốn giao diện giữ cùng hành vi giữa môi trường hoặc khi nâng phiên bản Swagger UI. `docExpansion` không thay đổi nội dung schema và không kiểm soát phần Models.

## 7. Phân biệt mức mở rộng operation và mức mở rộng Models

Swagger UI có một khu vực riêng để hiển thị các schema trong `components.schemas`, thường nằm cuối trang với tên Models. Các tùy chọn liên quan gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| `defaultModelsExpandDepth` | Độ sâu mở rộng khu vực Models; `-1` ẩn khu vực này |
| `defaultModelExpandDepth` | Độ sâu mở rộng từng model/schema |
| `defaultModelRendering` | Chọn hiển thị `example` hoặc `model` ban đầu |

Ví dụ ẩn hoàn toàn khu vực Models:

```yaml
springdoc:
  swagger-ui:
    default-models-expand-depth: -1
```

Ví dụ vẫn hiển thị Models nhưng chỉ mở một mức:

```yaml
springdoc:
  swagger-ui:
    default-models-expand-depth: 1
    default-model-expand-depth: 1
    default-model-rendering: example
```

Các tùy chọn này hữu ích khi tài liệu có nhiều schema lồng nhau. Nếu ẩn Models, người dùng vẫn có thể xem schema thông qua phần request/response của từng operation; việc ẩn khu vực cuối trang không xóa `components.schemas` khỏi OpenAPI document.

## 8. Cấu hình kết hợp cho một API có nhiều endpoint

Một cấu hình thực tế có thể kết hợp tag alphabetic, operation theo HTTP method và thu gọn operation ban đầu:

```yaml
springdoc:
  swagger-ui:
    path: /swagger-ui.html
    tags-sorter: alpha
    operations-sorter: method
    doc-expansion: none
    default-models-expand-depth: -1
```

Ý nghĩa:

- Swagger UI truy cập qua `/swagger-ui.html` theo cấu hình path của ứng dụng.
- Tag được sắp xếp theo tên.
- Operation trong từng tag được sắp xếp theo HTTP method.
- Tất cả nhóm operation thu gọn khi mở trang.
- Khu vực Models ở cuối trang được ẩn.

Nếu ưu tiên thứ tự nghiệp vụ đã khai báo trong `@OpenAPIDefinition`, bỏ `tags-sorter: alpha`:

```yaml
springdoc:
  swagger-ui:
    operations-sorter: alpha
    doc-expansion: list
    default-models-expand-depth: 1
```

Trong cấu hình thứ hai, tag giữ thứ tự từ OpenAPI document, operation được sắp theo path, tag mở nhưng operation thu gọn và khu vực Models vẫn hiển thị.

Các key YAML dùng dạng kebab-case theo quy ước cấu hình Spring Boot. Tên thuộc tính trong Swagger UI/Java configuration thường viết camelCase như `tagsSorter`, `operationsSorter`, `docExpansion`, `defaultModelsExpandDepth` và `defaultModelExpandDepth`.

## 9. Phân biệt cấu hình global với từng nhóm tài liệu

Springdoc có thể tạo nhiều OpenAPI document bằng `GroupedOpenApi`, chẳng hạn public, admin và internal. Mỗi document có thể chứa tập tag/operation khác nhau. Swagger UI hiển thị tài liệu được chọn qua cấu hình hoặc dropdown group.

Khi tổ chức nhiều group:

- Tag chỉ xuất hiện trong document có operation gắn tag đó.
- Danh sách tag root và thứ tự tag có thể khác giữa các group.
- Component schema và `$ref` thuộc document tương ứng.
- Các tùy chọn Swagger UI như sorter và doc expansion thường áp dụng cho giao diện chung, không tự tạo một chính sách nghiệp vụ riêng cho từng group.
- Nếu cần thứ tự tag khác nhau theo group, hãy tạo OpenAPI document tương ứng với tag list phù hợp và kiểm tra Swagger UI khi chuyển group.

Ví dụ khai báo group:

```java
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
```

Mỗi group có endpoint tài liệu riêng, ví dụ `/v3/api-docs/public` và `/v3/api-docs/admin`. Cần xác nhận đường dẫn thực tế theo cấu hình `springdoc.api-docs.path` và tên group. Việc tạo group không đồng nghĩa tự tạo hai trang Swagger UI độc lập; một giao diện có thể cho phép chọn group document.

## 10. Những điểm cần lưu ý về cấu hình sorter

`tagsSorter` và `operationsSorter` là tùy chọn trình bày phía Swagger UI. Một số điểm cần nhớ:

- `alpha` cho tag sắp xếp theo tên tag.
- `alpha` cho operation sắp xếp theo path.
- `method` cho operation sắp xếp theo HTTP method.
- Không khai báo sorter nếu muốn giữ thứ tự từ OpenAPI document hoặc thứ tự mặc định.
- Custom sorter dạng JavaScript function là khả năng của Swagger UI; không thể viết một function tùy ý như chuỗi YAML `alpha` hoặc `method`. Cách truyền function phụ thuộc cách tích hợp Swagger UI và cấu hình custom UI của ứng dụng.
- Sorter không đổi `tags` hoặc `paths` trong tài liệu OpenAPI được tải xuống; nó chỉ sắp xếp cách hiển thị.

Nếu cần thứ tự operation thủ công theo ưu tiên nghiệp vụ, không nên đổi path để ép thứ tự alphabetic. Hãy cân nhắc custom sorter phía Swagger UI hoặc chia tài liệu theo group nếu các nhóm operation có ranh giới rõ.

## 11. Kiểm tra cấu hình trong Swagger UI

Sau khi thay đổi `application.yml`, khởi động lại ứng dụng và mở Swagger UI. Kiểm tra lần lượt:

1. Các tag xuất hiện đúng thứ tự mong muốn.
2. Operation trong từng tag được sắp theo path hoặc method như cấu hình.
3. Trạng thái ban đầu của tag/operation đúng với `docExpansion`.
4. Khu vực Models hiển thị hoặc bị ẩn đúng với `defaultModelsExpandDepth`.
5. Nếu có nhiều group, đổi group và xác nhận tag/operation thuộc đúng tài liệu.
6. Mở một operation và kiểm tra request, response, schema vẫn hiển thị đầy đủ.

Có thể mở `/v3/api-docs` để kiểm tra thứ tự khai báo tag:

```json
{
  "tags": [
    {"name": "Products", "description": "Quản lý sản phẩm"},
    {"name": "Orders", "description": "Quản lý đơn hàng"},
    {"name": "Accounts", "description": "Quản lý tài khoản"}
  ]
}
```

Nếu `tagsSorter` là `alpha`, Swagger UI có thể hiển thị theo alphabetic dù mảng `tags` vẫn theo thứ tự Products, Orders, Accounts. Đây là khác biệt giữa tài liệu OpenAPI và cách giao diện trình bày.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tag không theo thứ tự khai báo | `tagsSorter: alpha` đang ghi đè thứ tự tài liệu | Bỏ sorter nếu muốn thứ tự thủ công |
| Tag không xuất hiện dù đã khai báo metadata | Operation chưa gắn đúng tên tag hoặc group không chứa operation | Kiểm tra `tags` ở operation và tài liệu của group |
| Một operation xuất hiện ở nhiều nhóm | Operation được gắn nhiều tag | Chỉ giữ các tag cần thiết |
| Operation không sắp theo path | `operationsSorter` đang là `method` hoặc chưa được áp dụng | Đặt `operations-sorter: alpha` và tải lại UI |
| Operation không sắp theo HTTP method | `operationsSorter` đang là `alpha` | Đặt `operations-sorter: method` |
| Tất cả operation mở ra dù muốn thu gọn | `docExpansion` là `full` hoặc cấu hình không được bind | Đặt `doc-expansion: none` và kiểm tra config runtime |
| Tag mở nhưng operation thu gọn | `docExpansion: list` | Đây là hành vi dự kiến; dùng `none` hoặc `full` nếu cần |
| Khu vực Models vẫn hiện | `defaultModelsExpandDepth` chưa đặt `-1` | Đặt `default-models-expand-depth: -1` |
| Schema quá dài trong Models | Độ sâu mở rộng model quá lớn | Giảm `default-model-expand-depth` hoặc ẩn Models |
| Đổi application.yml nhưng UI không đổi | Sai key, cấu hình profile khác hoặc cache trình duyệt | Kiểm tra profile active, key relaxed binding và hard refresh |
| Một group thiếu tag/operation | PathsToMatch hoặc packagesToScan loại endpoint khỏi group | Kiểm tra OpenAPI document riêng của group |

## 13. Quy trình chọn cấu hình phù hợp

Khi tổ chức Swagger UI, có thể làm theo thứ tự:

1. Xác định các nhóm nghiệp vụ mà client cần nhìn thấy.
2. Đặt tên tag ngắn, ổn định và gắn tag nhất quán ở controller/operation.
3. Khai báo metadata tag cấp root bằng `@OpenAPIDefinition` nếu cần description và thứ tự thủ công.
4. Chọn `tagsSorter: alpha` nếu số lượng tag lớn và người dùng thường tìm theo tên; bỏ sorter nếu cần thứ tự nghiệp vụ.
5. Chọn `operationsSorter: alpha` để tìm theo path hoặc `method` để nhóm theo HTTP verb.
6. Chọn `docExpansion: none`, `list` hoặc `full` theo kích thước tài liệu và cách người dùng khám phá endpoint.
7. Quyết định khu vực Models có cần hiển thị; dùng `defaultModelsExpandDepth: -1` nếu muốn ẩn.
8. Kiểm tra từng group và tải lại Swagger UI sau khi đổi cấu hình.
9. Xác nhận `/v3/api-docs` vẫn chứa đầy đủ tag, operation và schema; sorter không làm thay đổi tài liệu gốc.

Một cấu hình tốt giúp người dùng tìm đúng operation nhanh mà không làm thay đổi hợp đồng API. Hãy dùng tag để nhóm theo nghiệp vụ, sorter để sắp xếp theo tiêu chí rõ ràng và doc expansion để kiểm soát lượng nội dung xuất hiện khi trang được mở.

## 14. Tài liệu tham khảo

- [Swagger UI Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): `tagsSorter`, `operationsSorter`, `docExpansion` và model expansion options.
- [OpenAPI Specification – Tag Object](https://spec.openapis.org/oas/latest.html#tag-object): khai báo tag và metadata ở cấp tài liệu.
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): gắn tag vào operation.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): `@OpenAPIDefinition`, `@Tag` và `@Operation`.
- [Springdoc OpenAPI](https://springdoc.org/): cấu hình Swagger UI và tạo OpenAPI document từ Spring Boot.
