# Mô tả @RequestParam với giá trị mặc định và tùy chọn

Trong Spring Boot, `@RequestParam` liên kết một request parameter với tham số của method controller. Với REST API, annotation này thường dùng để nhận giá trị trên query string, chẳng hạn từ khóa tìm kiếm, bộ lọc, số trang hoặc kích thước trang. Khi tích hợp `springdoc-openapi`, các khai báo này được chuyển thành parameter trong OpenAPI để client biết tên, vị trí, kiểu dữ liệu, tính bắt buộc và giá trị mặc định.

Điểm cần phân biệt là ba trạng thái: tham số bắt buộc, tham số có thể vắng mặt và tham số có giá trị thay thế khi không được gửi. `required`, `defaultValue` và `Optional` giúp thể hiện ba ý định này trong code.

## 1. Cú pháp và hành vi mặc định

Khai báo cơ bản:

```java
@GetMapping("/search")
List<ProductDto> search(
        @RequestParam(name = "keyword") String keyword) {
    return productService.search(keyword);
}
```

Request mẫu:

```http
GET /api/products/search?keyword=keyboard
```

`@RequestParam` có các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `name` hoặc `value` | Tên parameter trên request. Hai thuộc tính là alias của nhau. |
| `required` | Có bắt buộc phải có parameter hay không; mặc định là `true`. |
| `defaultValue` | Giá trị dùng khi parameter bị thiếu hoặc có giá trị rỗng; khi đặt thuộc tính này, `required` được ngầm chuyển thành `false`. |

Nếu không truyền `required` hoặc `defaultValue`, parameter là bắt buộc. Khi client bỏ qua parameter, Spring không thể bind method argument và thường trả về HTTP 400 Bad Request.

Nên khai báo `name` rõ ràng, ví dụ `@RequestParam(name = "keyword")`, để tên trong hợp đồng HTTP không phụ thuộc cách compiler lưu metadata tên biến Java. Nếu dùng `value`, kết quả tương đương:

```java
@RequestParam(value = "keyword") String keyword
```

## 2. Tham số bắt buộc với required=true

`required` mặc định là `true`, vì vậy có thể bỏ thuộc tính này nếu muốn parameter bắt buộc:

```java
@GetMapping("/search")
List<ProductDto> search(
        @RequestParam(name = "keyword", required = true) String keyword) {
    return productService.search(keyword);
}
```

Client phải gửi `keyword`:

```text
GET /api/products/search?keyword=keyboard
```

Request thiếu `keyword`:

```text
GET /api/products/search
```

Spring không thể cung cấp giá trị cho argument bắt buộc nên trả lỗi 400. `required=true` chỉ kiểm tra parameter có được cung cấp hay không; nó không tự kiểm tra chuỗi có nội dung hợp lệ về mặt nghiệp vụ. Ví dụ, nếu không chấp nhận chuỗi trắng, cần thêm validation như `@NotBlank` và kích hoạt cơ chế validation phù hợp.

Trong OpenAPI, parameter bắt buộc được biểu diễn bằng `in: query` và `required: true`:

```yaml
parameters:
  - name: keyword
    in: query
    required: true
    schema:
      type: string
```

## 3. Tham số tùy chọn với required=false

Khi parameter có thể vắng mặt và ứng dụng cần tự quyết định cách xử lý, dùng `required = false`:

```java
@GetMapping("/search")
List<ProductDto> search(
        @RequestParam(name = "keyword", required = false) String keyword) {
    if (keyword == null || keyword.isBlank()) {
        return productService.findFeatured();
    }
    return productService.search(keyword);
}
```

Hai request sau đều có thể được xử lý:

```text
GET /api/products/search?keyword=keyboard
GET /api/products/search
```

Khi parameter không xuất hiện, Spring bind `null` cho kiểu tham chiếu như `String`. Vì vậy, code phải xử lý trường hợp `null` trước khi gọi các method trên giá trị đó.

Không nên dùng kiểu nguyên thủy như `int` hoặc `boolean` cho parameter có thể vắng mặt nếu không có default. Kiểu nguyên thủy không biểu diễn được `null`; hãy dùng `Integer`, `Boolean`, kiểu tham chiếu khác hoặc `Optional<T>` tùy ý nghĩa của API.

OpenAPI biểu diễn parameter tùy chọn bằng `required: false` hoặc bỏ trường `required` (mặc định của OpenAPI là `false`):

```yaml
parameters:
  - name: keyword
    in: query
    required: false
    schema:
      type: string
```

## 4. Dùng defaultValue để cung cấp giá trị mặc định

`defaultValue` phù hợp khi API có hành vi mặc định rõ ràng nếu client không gửi parameter. Ví dụ, trang đầu tiên có chỉ số `0` và mỗi trang mặc định chứa `20` sản phẩm:

```java
@GetMapping
Page<ProductDto> listProducts(
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return productService.findPage(page, size);
}
```

Client có thể bỏ cả hai parameter:

```text
GET /api/products
```

Spring bind `page = 0` và `size = 20`. Nếu client gửi giá trị khác, giá trị client được sử dụng:

```text
GET /api/products?page=2&size=50
```

Khi đặt `defaultValue`, `required` tự động trở thành `false`. Không cần viết đồng thời `required = false`, trừ khi muốn nhấn mạnh ý định cho người đọc code.

Giá trị `defaultValue` được khai báo dưới dạng chuỗi, sau đó Spring chuyển đổi sang kiểu argument thông qua cơ chế conversion. Ví dụ `"0"` được chuyển thành `int` có giá trị `0`, `"true"` có thể được chuyển thành `boolean`, và chuỗi enum được chuyển thành hằng tương ứng nếu tên hợp lệ.

`defaultValue` cũng được dùng khi parameter có mặt nhưng giá trị rỗng. Điều này khác với `required = false`: parameter tùy chọn không có default có thể nhận `null` khi bị bỏ qua, còn parameter có default sẽ nhận giá trị thay thế khi bị thiếu hoặc rỗng.

OpenAPI có thể thể hiện default trong schema:

```yaml
parameters:
  - name: page
    in: query
    required: false
    schema:
      type: integer
      default: 0
  - name: size
    in: query
    required: false
    schema:
      type: integer
      default: 20
```

Giá trị mặc định trong tài liệu cần khớp với hành vi thực tế của controller. Không khai báo default trong `@Parameter` hoặc schema là `20` nếu code thực tế dùng `10`.

## 5. Dùng Optional<T> khi muốn thể hiện sự vắng mặt

`Optional<T>` diễn tả rõ rằng argument có thể không tồn tại:

```java
@GetMapping("/search")
List<ProductDto> search(
        @RequestParam(name = "keyword") Optional<String> keyword) {
    return keyword
        .filter(value -> !value.isBlank())
        .map(productService::search)
        .orElseGet(productService::findFeatured);
}
```

Khi request không có `keyword`, Spring cung cấp `Optional.empty()`. Khi có parameter, giá trị được bọc trong `Optional`. Với kiểu argument là `Optional`, parameter được xem là không bắt buộc; không cần đặt `required = false` trong trường hợp thông thường.

Có thể dùng `Optional<T>` cùng default value khi API muốn biểu diễn cả giá trị thay thế:

```java
@RequestParam(name = "sort", defaultValue = "newest") Optional<String> sort
```

Tuy nhiên, nếu đã có `defaultValue`, argument luôn nhận giá trị mặc định khi parameter vắng mặt hoặc rỗng, nên `Optional` thường không đem lại nhiều ý nghĩa. Chọn một cách biểu diễn đơn giản, nhất quán với convention của dự án.

## 6. Kết hợp @RequestParam với nhiều kiểu dữ liệu

Spring chuyển chuỗi trong request thành kiểu Java dựa trên conversion service và converter được đăng ký trong ứng dụng.

### Kiểu số và boolean

```java
@GetMapping("/filter")
List<ProductDto> filter(
        @RequestParam(name = "minPrice", required = false) BigDecimal minPrice,
        @RequestParam(name = "available", defaultValue = "true") boolean available) {
    return productService.filter(minPrice, available);
}
```

Request ví dụ:

```text
GET /api/products/filter?minPrice=100000&available=false
```

Nếu client gửi `minPrice=abc`, Spring không thể chuyển chuỗi đó thành `BigDecimal` và thường trả HTTP 400. `required=false` chỉ cho phép bỏ qua parameter; nó không cho phép gửi một giá trị sai kiểu.

### Enum

```java
public enum ProductStatus {
    ACTIVE,
    INACTIVE,
    OUT_OF_STOCK
}

@GetMapping
List<ProductDto> listByStatus(
        @RequestParam(name = "status", required = false) ProductStatus status) {
    return productService.findByStatus(status);
}
```

Request:

```text
GET /api/products?status=ACTIVE
```

Giá trị không khớp enum có thể gây lỗi chuyển đổi và trả 400. Nếu muốn nhận các mã thân thiện hoặc khác tên enum, hãy đăng ký `Converter<String, ProductStatus>` và mô tả chính xác các giá trị công khai trong OpenAPI.

### Ngày tháng

Với kiểu ngày, nên công bố rõ định dạng mà client phải gửi:

```java
@GetMapping("/by-date")
List<ProductDto> findByDate(
        @RequestParam(name = "date")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date) {
    return productService.findByDate(date);
}
```

Request mẫu:

```text
GET /api/products/by-date?date=2026-11-20
```

`@DateTimeFormat` hướng dẫn Spring chuyển đổi request parameter. Để mô tả rõ hơn trên giao diện tài liệu, có thể bổ sung `@Parameter` với mô tả và ví dụ.

## 7. Mô tả query parameter trong OpenAPI bằng springdoc

Springdoc đọc `@RequestParam` trên controller để tạo parameter trong OpenAPI. Với các trường hợp đơn giản, annotation Spring đã đủ để springdoc suy ra tên, vị trí, kiểu và tính bắt buộc. Có thể thêm `@Parameter` để mô tả mục đích và ví dụ cho người tích hợp:

```java
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping
Page<ProductDto> listProducts(
        @Parameter(
            description = "Số trang, bắt đầu từ 0",
            example = "0"
        )
        @RequestParam(name = "page", defaultValue = "0") int page,

        @Parameter(
            description = "Số phần tử trên một trang",
            example = "20"
        )
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return productService.findPage(page, size);
}
```

`@Parameter` bổ sung metadata cho tài liệu; nó không thay thế `@RequestParam` và không tự thực thi việc bind giá trị. Tương tự, `@Schema` mô tả kiểu và ràng buộc cho tài liệu, còn Spring và Bean Validation mới chịu trách nhiệm xử lý request tại runtime.

Đặc tả OpenAPI sinh ra có thể có dạng:

```yaml
paths:
  /api/products:
    get:
      parameters:
        - name: page
          in: query
          description: Số trang, bắt đầu từ 0
          required: false
          schema:
            type: integer
            default: 0
          example: 0
        - name: size
          in: query
          description: Số phần tử trên một trang
          required: false
          schema:
            type: integer
            default: 20
          example: 20
```

Đây là dạng minh họa. Cấu trúc chính xác phụ thuộc phiên bản OpenAPI được springdoc cấu hình và phiên bản thư viện đi kèm. Hãy kiểm tra tài liệu thực tế ở `/v3/api-docs` thay vì giả định mọi thuộc tính annotation đều được xuất giống nhau ở mọi phiên bản.

## 8. Phân biệt default value với example

`defaultValue` và `example` có ý nghĩa khác nhau:

| Thuộc tính | Ý nghĩa | Ảnh hưởng runtime |
| --- | --- | --- |
| `@RequestParam(defaultValue = "20")` | Giá trị server sử dụng khi parameter bị thiếu hoặc rỗng | Có |
| `@Parameter(example = "20")` | Ví dụ hiển thị cho người đọc tài liệu | Không |
| `@Schema(defaultValue = "20")` | Giá trị mặc định được công bố trong schema OpenAPI | Không tự thay đổi controller |

Ví dụ, nếu controller đặt `defaultValue = "20"` nhưng tài liệu mô tả example là `50`, điều đó không nhất thiết sai: `20` là giá trị server dùng khi client bỏ qua parameter, còn `50` là một request mẫu. Tuy nhiên, nếu schema công bố default khác hành vi server, client có thể hiểu sai hợp đồng.

## 9. Ví dụ hoàn chỉnh: API tìm kiếm và phân trang

Ví dụ dưới đây kết hợp parameter bắt buộc, tùy chọn và default value:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    Page<ProductDto> search(
            @Parameter(description = "Từ khóa tìm kiếm", example = "keyboard")
            @RequestParam(name = "keyword", required = false)
            Optional<String> keyword,

            @Parameter(description = "Trạng thái sản phẩm")
            @RequestParam(name = "status", required = false)
            Optional<ProductStatus> status,

            @Parameter(description = "Số trang, bắt đầu từ 0", example = "0")
            @RequestParam(name = "page", defaultValue = "0")
            int page,

            @Parameter(description = "Số phần tử trên một trang", example = "20")
            @RequestParam(name = "size", defaultValue = "20")
            int size) {

        return productService.search(keyword, status, page, size);
    }
}
```

Request đầy đủ:

```http
GET /api/products?keyword=keyboard&status=ACTIVE&page=0&size=20
```

Request chỉ dùng giá trị mặc định:

```http
GET /api/products
```

Trong request thứ hai, `keyword` và `status` là `Optional.empty()`, còn `page` là `0` và `size` là `20`. Cách triển khai service cần hiểu rõ ý nghĩa của `Optional.empty()` — ví dụ không lọc theo keyword hoặc status.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Thiếu parameter trả 400 | `required` mặc định là `true` | Đặt `required=false`, dùng `Optional` hoặc khai báo `defaultValue` nếu đúng ý nghĩa API |
| Parameter tùy chọn gây lỗi null | Code gọi method trên giá trị có thể là `null` | Kiểm tra null hoặc dùng `Optional<T>` |
| Giá trị mặc định không xuất hiện | Không khai báo `defaultValue` hoặc cấu hình runtime khác với tài liệu | Kiểm tra annotation và schema được sinh |
| Chuỗi số không chuyển đổi được | Client gửi giá trị không phù hợp kiểu Java | Gửi đúng định dạng hoặc cung cấp converter phù hợp |
| Swagger UI hiển thị parameter bắt buộc sai | Metadata annotation mâu thuẫn hoặc tài liệu chưa được cập nhật | Kiểm tra `required`, `defaultValue` và JSON `/v3/api-docs` |
| Tên parameter trong tài liệu không đúng | Không khai báo rõ `name` hoặc có metadata trùng | Dùng `@RequestParam(name = "...")` và kiểm tra annotation OpenAPI bổ sung |

Đừng dùng `required=false` để che lỗi dữ liệu. Một parameter tùy chọn vẫn cần quy tắc xử lý khi vắng mặt, còn giá trị được gửi lên vẫn phải được chuyển đổi và kiểm tra đúng kiểu.

## 11. Quy trình thiết kế @RequestParam

Khi thêm một query parameter, hãy quyết định theo thứ tự:

1. Xác định tên parameter công khai và dùng `@RequestParam(name = "...")`.
2. Chọn parameter bắt buộc (`required=true`), tùy chọn (`required=false`/`Optional<T>`) hay có giá trị mặc định (`defaultValue`).
3. Chọn kiểu Java phù hợp; dùng wrapper hoặc `Optional` nếu giá trị có thể vắng mặt.
4. Xác định quy tắc chuyển đổi và validation cho giá trị được gửi.
5. Dùng `@Parameter` hoặc `@Schema` để bổ sung mô tả, ví dụ và ràng buộc cần công bố.
6. Mở `/v3/api-docs` hoặc Swagger UI để xác nhận `in: query`, `required`, `schema`, `default` và ví dụ khớp với controller.
7. Kiểm thử request có parameter, thiếu parameter, có giá trị rỗng và có giá trị sai kiểu.

Khi thiết kế rõ ba trạng thái bắt buộc, tùy chọn và mặc định, client có thể tạo request đúng ngay từ đầu; Swagger UI cũng hiển thị chính xác cách sử dụng API mà controller thực thi.

## Tài liệu tham khảo

- [Spring Framework – `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Framework – Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object)
- [springdoc-openapi – Documentation](https://springdoc.org/)
