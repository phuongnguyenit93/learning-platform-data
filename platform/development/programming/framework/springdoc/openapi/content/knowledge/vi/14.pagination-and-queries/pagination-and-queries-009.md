# Giới hạn kích thước trang và các ràng buộc lọc cần ghi rõ

API danh sách thường cho phép client phân trang, sắp xếp và lọc dữ liệu. Nếu không giới hạn kích thước trang hoặc phạm vi lọc, một request có thể buộc ứng dụng đọc, sắp xếp hoặc đếm quá nhiều bản ghi. Nếu tài liệu OpenAPI không mô tả rõ giới hạn, client có thể gửi request mà server từ chối, tự điều chỉnh hoặc xử lý rất tốn tài nguyên.

Với Spring Boot dùng Spring Data, `Pageable` giúp nhận các tham số `page`, `size` và `sort`. Springdoc-openapi có thể biểu diễn chúng cùng các bộ lọc từ DTO bằng `@ParameterObject`. Bean Validation và cấu hình Spring Data Web giúp thực thi giới hạn; OpenAPI cần công bố cùng quy tắc để client biết giá trị hợp lệ.

## 1. Vì sao cần giới hạn phân trang và bộ lọc?

Một endpoint danh sách có thể được gọi bởi trình duyệt, ứng dụng di động, báo cáo định kỳ hoặc một client tích hợp tự động. Nếu endpoint cho phép `size=1000000`, truy vấn có thể:

- Đọc và chuyển đổi quá nhiều bản ghi.
- Giữ nhiều object trong bộ nhớ và làm tăng thời gian phản hồi.
- Tạo response lớn, tốn băng thông và làm client xử lý chậm.
- Thực hiện sort trên tập dữ liệu lớn hoặc dùng cột không có index.
- Tính tổng số bản ghi phù hợp với filter bằng một truy vấn `COUNT` tốn kém.

Bộ lọc quá rộng hoặc không được kiểm soát cũng có thể tạo truy vấn nặng. Ví dụ, tìm kiếm theo chuỗi rỗng, khoảng ngày nhiều năm, nhiều giá trị `IN` hoặc sắp xếp theo thuộc tính không được hỗ trợ có thể gây tải lớn hoặc lỗi runtime.

Một hợp đồng truy vấn tốt cần trả lời rõ:

1. Trang bắt đầu từ chỉ số nào: `0` hay `1`?
2. Kích thước trang mặc định là bao nhiêu?
3. Kích thước tối thiểu và tối đa là bao nhiêu?
4. Client được phép sắp xếp theo field nào và theo hướng nào?
5. Filter nào là tùy chọn, filter nào bắt buộc?
6. Giới hạn độ dài, khoảng giá trị, số lượng phần tử và khoảng thời gian là gì?
7. Khi tham số không hợp lệ, server trả `400`, dùng giá trị mặc định hay giới hạn về mức tối đa?

## 2. Các tham số phân trang của Spring Data

Khi controller nhận `Pageable`, Spring Data Web thường ánh xạ query parameter theo quy ước:

| Parameter | Ý nghĩa | Ví dụ |
|---|---|---|
| `page` | Chỉ số trang | `page=0` là trang đầu nếu dùng zero-based indexing. |
| `size` | Số phần tử yêu cầu trong một trang | `size=20`. |
| `sort` | Thuộc tính và hướng sắp xếp | `sort=createdAt,desc`. |

Ví dụ:

```http
GET /api/products?page=0&size=20&sort=createdAt,desc
```

Có thể truyền nhiều tiêu chí sort bằng cách lặp lại parameter:

```http
GET /api/products?page=0&size=20&sort=status,asc&sort=createdAt,desc
```

Thứ tự các tiêu chí sort có ý nghĩa. Trong ví dụ trên, kết quả được sắp xếp theo `status` tăng dần, sau đó theo `createdAt` giảm dần.

### 2.1. Zero-based và one-based page index

Spring Data mặc định dùng chỉ số trang bắt đầu từ `0`:

- `page=0`: trang đầu tiên.
- `page=1`: trang thứ hai.
- `page=2`: trang thứ ba.

Nếu API muốn dùng cách đánh số bắt đầu từ `1`, có thể bật `one-indexed-parameters`. Khi đó resolver chuyển page index từ request sang chỉ số nội bộ phù hợp. Hãy công bố rõ quy ước này vì client thường tự tính `page + 1` hoặc `page - 1`.

Không trộn hai quy ước trong cùng API. Nếu thay đổi từ zero-based sang one-based sau khi client đã tích hợp, đó là thay đổi hợp đồng có thể làm client lấy sai trang.

## 3. Đặt kích thước trang mặc định và tối đa

Spring Data Web có giá trị mặc định cho kích thước trang và một giới hạn tối đa của resolver. Giá trị mặc định thường gặp là 20 phần tử mỗi trang và giới hạn trên mặc định có thể khá lớn (thường là 2.000). Không nên phụ thuộc vào mặc định ngầm; hãy cấu hình giá trị phù hợp với tải và SLA của ứng dụng.

Với Spring Boot, có thể cấu hình trong `application.yml`:

```yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
        page-parameter: page
        size-parameter: size
        one-indexed-parameters: false
```

Trong cấu hình này:

- Nếu client không truyền `size`, resolver dùng 20.
- Kích thước hiệu lực không vượt quá 100.
- Tên query parameter là `page` và `size`.
- Chỉ số trang bắt đầu từ 0.

`max-page-size` là giới hạn của cơ chế phân giải `Pageable`; khi client gửi giá trị vượt mức, resolver có thể giới hạn kích thước hiệu lực về mức tối đa. Hành vi này không đồng nghĩa server luôn trả `400 Bad Request`. Nếu hợp đồng yêu cầu từ chối giá trị vượt giới hạn, hãy kiểm tra và validate input rõ ràng thay vì chỉ dựa vào việc resolver giới hạn giá trị.

### 3.1. Cấu hình bằng Java

Có thể đặt giới hạn cho `PageableHandlerMethodArgumentResolver` bằng customizer:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer;

@Configuration
class PageableConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableCustomizer() {
        return resolver -> resolver.setMaxPageSize(100);
    }
}
```

Customizer hữu ích khi cần cấu hình bằng code hoặc có quy tắc riêng. Nếu đã cấu hình `spring.data.web.pageable.max-page-size`, tránh đặt thêm một giá trị khác trong customizer khiến nhóm phát triển khó biết giới hạn thực tế đến từ đâu.

### 3.2. Mặc định theo từng endpoint

`@PageableDefault` đặt giá trị mặc định cho một method:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.domain.Sort;
import org.springdoc.core.annotations.ParameterObject;

@GetMapping("/api/products")
Page<ProductResponse> findProducts(
        @ParameterObject
        @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC)
        Pageable pageable) {
    return productService.findAll(pageable);
}
```

`@PageableDefault` điều khiển giá trị mặc định khi client không truyền tham số. Giới hạn tối đa vẫn nên được cấu hình tập trung bằng resolver. Không xem `@PageableDefault(size = 20)` là giới hạn tối đa; client vẫn có thể yêu cầu size lớn hơn nếu resolver cho phép.

Có thể dùng `@SortDefault` hoặc `@SortDefault.SortDefaults` khi cần nhiều tiêu chí sắp xếp mặc định. Hãy kiểm tra tài liệu API để bảo đảm sort mặc định mà server áp dụng cũng được mô tả cho client.

## 4. Giới hạn `page`, `size` và hành vi với giá trị không hợp lệ

Giới hạn page size không thay thế kiểm tra mọi tham số phân trang. API cần xác định hành vi với các đầu vào:

| Đầu vào | Quy tắc nên công bố |
|---|---|
| Không truyền `page` | Dùng trang mặc định, thường là `0`. |
| `page` âm | Từ chối bằng `400` hoặc chuẩn hóa theo một quy tắc được công bố. |
| Không truyền `size` | Dùng kích thước mặc định. |
| `size=0` hoặc âm | Từ chối hoặc dùng mặc định; tránh hành vi không rõ ràng. |
| `size` lớn hơn tối đa | Từ chối hoặc giới hạn về max; phải ghi rõ hành vi. |
| `page` quá lớn | Trả trang rỗng hoặc phản hồi theo quy ước; không tự coi đó là lỗi nếu API không quy định. |
| `sort` sai cú pháp | Trả lỗi validation rõ ràng. |
| Sort field không được hỗ trợ | Từ chối bằng `400` thay vì để lỗi repository lộ ra thành `500`. |

Nếu muốn trả `400` cho `size` vượt ngưỡng, có thể nhận các tham số riêng và tạo `PageRequest` sau khi validate:

```java
@GetMapping("/api/products")
Page<ProductResponse> findProducts(
        @RequestParam(defaultValue = "0") @Min(0) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {

    Pageable pageable = PageRequest.of(page, size);
    return productService.findAll(pageable);
}
```

Để method validation thực thi trên các tham số scalar, cấu hình Bean Validation phù hợp cho phiên bản Spring Boot/Spring Framework đang dùng. Tùy phiên bản, cần `@Validated` ở controller hoặc cơ chế method validation của Spring MVC. Bổ sung `spring-boot-starter-validation` nếu ứng dụng chưa có provider.

Khi dùng tham số riêng, tài liệu OpenAPI có thể mô tả giới hạn trực tiếp:

```java
@Operation(parameters = {
    @Parameter(
        name = "page",
        in = ParameterIn.QUERY,
        description = "Chỉ số trang, bắt đầu từ 0",
        schema = @Schema(type = "integer", minimum = "0", defaultValue = "0")
    ),
    @Parameter(
        name = "size",
        in = ParameterIn.QUERY,
        description = "Số phần tử mỗi trang, từ 1 đến 100",
        schema = @Schema(type = "integer", minimum = "1", maximum = "100", defaultValue = "20")
    )
})
```

Ví dụ này dùng `@Operation` và `@Parameter` của Swagger Annotations. Nếu dùng `Pageable` cùng `@ParameterObject`, springdoc tự sinh `page`, `size`, `sort`; không thêm lại các parameter cùng tên theo cách tạo ra bản ghi trùng. Chọn một cách công bố rõ ràng: để springdoc suy luận từ `Pageable` và kiểm tra output, hoặc tự khai báo query parameter khi controller nhận tham số riêng.

## 5. Mô tả `Pageable` trong OpenAPI bằng springdoc

Với controller nhận `Pageable`, dùng `@ParameterObject` để springdoc phân rã object thành query parameter:

```java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;

@GetMapping("/api/products")
Page<ProductResponse> findProducts(
        @ParameterObject
        @PageableDefault(size = 20)
        Pageable pageable,
        @Valid @ParameterObject @ModelAttribute ProductFilter filter) {
    return productService.search(filter, pageable);
}
```

OpenAPI thường biểu diễn các tham số `page`, `size` và `sort` riêng lẻ. `@ParameterObject` là annotation của springdoc giúp tài liệu hóa các thuộc tính query; `Pageable` mới là kiểu Spring Data dùng để nhận và phân giải tham số.

Hãy kiểm tra `/v3/api-docs` để xác nhận:

- `page` là integer và có mô tả chỉ số bắt đầu.
- `size` là integer, có default và maximum đúng với resolver.
- `sort` thể hiện cú pháp property/direction được API chấp nhận.
- Filter DTO được flatten thành query parameter, không bị mô tả nhầm thành JSON request body.

Không giả định springdoc luôn suy ra `max-page-size` từ cấu hình resolver. Nếu giới hạn runtime không xuất hiện trong schema, bổ sung metadata OpenAPI bằng annotation/customizer hoặc khai báo tham số tường minh, rồi kiểm tra lại tài liệu.

### 5.1. Không công bố trực tiếp toàn bộ cấu trúc `Page` nếu không cần

Spring Data `Page<T>` chứa dữ liệu trang và metadata phân trang. Cấu trúc JSON được serialize có thể phụ thuộc phiên bản Spring Data và cấu hình serializer. Nếu cần hợp đồng response ổn định, tạo DTO riêng:

```java
public record PageResponse<T>(
        List<T> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean last
) {}
```

Map `Page<T>` sang `PageResponse<T>` trong service hoặc controller. Cách này giúp kiểm soát tên field, schema và các metadata mà client cần.

## 6. Giới hạn sort và danh sách field được phép

Spring Data cho phép client gửi sort property, ví dụ:

```text
?sort=createdAt,desc&sort=name,asc
```

Không nên cho phép client sắp xếp tùy ý trên mọi thuộc tính entity. Một sort field không tồn tại có thể làm repository ném lỗi; sort trên cột không có index hoặc quan hệ phức tạp có thể tạo truy vấn rất nặng.

Hãy công bố danh sách field được hỗ trợ, ví dụ:

| Public sort key | Hướng hỗ trợ | Ý nghĩa |
|---|---|---|
| `name` | `asc`, `desc` | Tên sản phẩm. |
| `price` | `asc`, `desc` | Giá sản phẩm. |
| `createdAt` | `asc`, `desc` | Thời điểm tạo. |

Có thể kiểm tra sort trước khi truyền vào repository:

```java
private static final Set<String> ALLOWED_SORTS = Set.of(
        "name",
        "price",
        "createdAt"
);

private void validateSort(Sort sort) {
    for (Sort.Order order : sort) {
        if (!ALLOWED_SORTS.contains(order.getProperty())) {
            throw new InvalidQueryParameterException(
                    "Không hỗ trợ sắp xếp theo: " + order.getProperty()
            );
        }
    }
}
```

Trong ứng dụng thực tế, có thể ánh xạ public sort key sang property/query expression nội bộ thay vì dùng trực tiếp tên field entity. Cách này cho phép giữ hợp đồng ổn định khi cấu trúc persistence thay đổi.

Không nên nhận raw SQL expression từ query parameter. Dùng danh sách cho phép và mapping cố định ở server. Hãy kiểm tra cả cú pháp hướng sort; Spring Data chỉ hỗ trợ `ASC` và `DESC` cho `Sort.Direction`.

## 7. Ràng buộc cho các filter query

Filter DTO nên thể hiện rõ kiểu dữ liệu, giá trị hợp lệ và giới hạn kích thước. Ví dụ bộ lọc sản phẩm:

```java
public class ProductFilter {

    @Size(max = 80)
    private String keyword;

    private ProductStatus status;

    @DecimalMin("0.00")
    @DecimalMax("1000000.00")
    private BigDecimal minPrice;

    @DecimalMin("0.00")
    @DecimalMax("1000000.00")
    private BigDecimal maxPrice;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdFrom;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdTo;

    // getters và setters
}
```

Controller:

```java
@GetMapping("/api/products")
PageResponse<ProductResponse> search(
        @Valid @ParameterObject @ModelAttribute ProductFilter filter,
        @ParameterObject @PageableDefault(size = 20) Pageable pageable) {
    validateSort(pageable.getSort());
    return productService.search(filter, pageable);
}
```

Các annotation giúp mô tả và kiểm tra từng field:

- `@Size(max = 80)`: keyword không vượt quá 80 ký tự.
- `ProductStatus`: chỉ nhận các giá trị enum đã định nghĩa.
- `@DecimalMin`/`@DecimalMax`: giá trị giá nằm trong khoảng công bố.
- `@DateTimeFormat`: chuyển query string theo định dạng ngày ISO `yyyy-MM-dd`.
- `@Valid`: kích hoạt validation trên filter DTO.

`@ParameterObject` giúp springdoc đưa các property thành query parameter. Bean Validation thực thi ràng buộc ở runtime; schema OpenAPI cần được kiểm tra để xác nhận các giới hạn được phản ánh đúng.

### 7.1. Giới hạn chuỗi tìm kiếm

Một filter `keyword` nên có độ dài tối đa hợp lý. Tìm kiếm chuỗi rỗng hoặc chuỗi chỉ có khoảng trắng thường không mang lại kết quả hữu ích và có thể khiến truy vấn thành full scan.

Có thể chuẩn hóa đầu vào bằng cách trim khoảng trắng và coi chuỗi rỗng như filter không được truyền. Hãy ghi rõ hành vi này trong description và kiểm thử các trường hợp:

- Không truyền `keyword`.
- Truyền `keyword` rỗng.
- Truyền chuỗi chỉ có khoảng trắng.
- Truyền chuỗi dài hơn giới hạn.
- Truyền ký tự Unicode hoặc dấu tiếng Việt.

Nếu dùng `@Size(max = 80)`, lưu ý `null` vẫn hợp lệ. Với filter tùy chọn, đây thường là hành vi mong muốn; không thêm `@NotBlank` nếu client được phép bỏ qua filter.

### 7.2. Giới hạn khoảng số

Nếu có `minPrice` và `maxPrice`, mỗi giá trị cần giới hạn trong miền hợp lệ. Ngoài ra cần kiểm tra quan hệ giữa chúng:

```text
minPrice <= maxPrice
```

Hai annotation `@DecimalMin` và `@DecimalMax` trên từng field không tự bảo đảm quan hệ giữa hai field. Dùng class-level Bean Validation constraint hoặc validator nghiệp vụ để kiểm tra điều kiện liên trường.

Khi một đầu mút không được gửi, xác định rõ ý nghĩa:

- Chỉ có `minPrice`: lấy các sản phẩm từ giá tối thiểu trở lên.
- Chỉ có `maxPrice`: lấy các sản phẩm tới giá tối đa.
- Có cả hai: lọc trong khoảng đóng hoặc khoảng mở theo hợp đồng.
- Không có cả hai: không áp dụng filter giá.

### 7.3. Giới hạn khoảng thời gian

Với filter thời gian, công bố định dạng, múi giờ và quy tắc biên. Nếu dùng `LocalDate`, ví dụ query có thể là:

```text
GET /api/products?createdFrom=2026-01-01&createdTo=2026-03-31
```

Hãy xác định `createdTo` có bao gồm hết ngày đó hay không. Với trường timestamp, cách dễ tránh sai lệch là dùng khoảng nửa mở `[from, to)`: `createdAt >= from` và `createdAt < to`. Nếu nhận `OffsetDateTime` hoặc `Instant`, công bố múi giờ/offset được chấp nhận và chuẩn hóa thời điểm về UTC khi truy vấn.

Ngoài kiểm tra `createdFrom <= createdTo`, có thể giới hạn khoảng thời gian tối đa, ví dụ 90 ngày, để tránh truy vấn quá rộng. Giới hạn 90 ngày chỉ là ví dụ nghiệp vụ; chọn con số dựa trên dữ liệu, index và yêu cầu sản phẩm.

### 7.4. Giới hạn danh sách filter

Nếu API nhận nhiều ID hoặc trạng thái trong query, giới hạn số phần tử:

```java
@Size(max = 50)
private List<UUID> ids;
```

Trong OpenAPI, schema tương ứng có thể có `maxItems: 50`. Cũng cần công bố cách client truyền nhiều giá trị, ví dụ repeated parameter hay comma-separated, và xác minh binder nhận đúng định dạng. Đừng để một request tạo `IN` clause với hàng nghìn giá trị không giới hạn.

## 8. Ràng buộc liên trường và validation nghiệp vụ

Một số quy tắc không thể biểu diễn chỉ bằng giới hạn độc lập của từng parameter:

- `minPrice` không lớn hơn `maxPrice`.
- `createdFrom` không sau `createdTo`.
- Khoảng ngày không vượt quá 90 ngày.
- Nếu `status=ARCHIVED`, filter `archivedAtFrom` có thể bắt buộc.
- Không cho phép đồng thời hai chế độ lọc loại trừ nhau.

Có thể tạo class-level constraint bằng Jakarta Bean Validation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidProductFilterValidator.class)
public @interface ValidProductFilter {
    String message() default "Khoảng lọc không hợp lệ";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Validator đọc toàn bộ DTO và kiểm tra quan hệ giữa các field:

```java
public class ValidProductFilterValidator
        implements ConstraintValidator<ValidProductFilter, ProductFilter> {

    @Override
    public boolean isValid(ProductFilter value, ConstraintValidatorContext context) {
        if (value == null) {
            return true;
        }

        boolean valid = true;
        if (value.getMinPrice() != null && value.getMaxPrice() != null
                && value.getMinPrice().compareTo(value.getMaxPrice()) > 0) {
            valid = false;
        }

        if (value.getCreatedFrom() != null && value.getCreatedTo() != null
                && value.getCreatedFrom().isAfter(value.getCreatedTo())) {
            valid = false;
        }
        return valid;
    }
}
```

Gắn constraint ở cấp lớp:

```java
@ValidProductFilter
public class ProductFilter {
    // Các thuộc tính filter và getter/setter
}
```

Trong ứng dụng thực tế, nên thêm message cụ thể cho từng lỗi bằng `ConstraintValidatorContext` để client biết field hoặc quan hệ nào không hợp lệ. Nếu có giới hạn khoảng ngày tối đa, kiểm tra thêm `ChronoUnit.DAYS.between(from, to)`.

OpenAPI có thể mô tả giới hạn của từng parameter bằng schema và description. Các quy tắc liên trường thường cần description rõ ràng, ví dụ “`createdFrom` phải nhỏ hơn hoặc bằng `createdTo`”; không giả định một schema parameter riêng lẻ diễn đạt được toàn bộ logic đó.

## 9. Mô tả filter constraints trong OpenAPI

Với filter DTO, dùng `@Schema` để bổ sung mô tả, ví dụ, format và giới hạn khi cần:

```java
public class ProductFilter {

    @Schema(
            description = "Từ khóa tìm trong tên sản phẩm, tối đa 80 ký tự",
            example = "laptop"
    )
    @Size(max = 80)
    private String keyword;

    @Schema(description = "Trạng thái sản phẩm")
    private ProductStatus status;

    @Schema(description = "Giá tối thiểu, phải nhỏ hơn hoặc bằng maxPrice",
            minimum = "0.00", maximum = "1000000.00")
    @DecimalMin("0.00")
    @DecimalMax("1000000.00")
    private BigDecimal minPrice;

    @Schema(description = "Ngày tạo bắt đầu, định dạng yyyy-MM-dd",
            type = "string", format = "date")
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate createdFrom;
}
```

Bean Validation biểu diễn ràng buộc thực thi; `@Schema` làm rõ thông tin cho tài liệu. Tránh khai báo hai giá trị mâu thuẫn, ví dụ `@Size(max=80)` nhưng `@Schema(maxLength=120)`. Sau khi sinh tài liệu, kiểm tra schema thực tế và điều chỉnh annotation/customizer nếu springdoc không ánh xạ đúng.

Ví dụ OpenAPI rút gọn cho một số query parameter:

```yaml
parameters:
  - name: keyword
    in: query
    required: false
    description: Từ khóa tìm trong tên sản phẩm, tối đa 80 ký tự
    schema:
      type: string
      maxLength: 80
  - name: minPrice
    in: query
    required: false
    description: Giá tối thiểu; không được lớn hơn maxPrice
    schema:
      type: number
      minimum: 0
      maximum: 1000000
  - name: createdFrom
    in: query
    required: false
    schema:
      type: string
      format: date
```

Với `Pageable`, tài liệu cũng cần mô tả `page`, `size` và `sort`, trong đó `size` thể hiện giới hạn tối đa đã cấu hình. `description` là nơi phù hợp để nêu hành vi nếu server giới hạn giá trị vượt max thay vì trả `400`.

## 10. Cẩn trọng với chi phí truy vấn

Giới hạn giá trị không chỉ là validation đầu vào. Một số lựa chọn thiết kế ảnh hưởng trực tiếp tới chi phí truy vấn:

- **`Page` và `Slice`**: `Page` thường cần tổng số phần tử/trang, có thể phát sinh truy vấn count; `Slice` chỉ cần biết còn dữ liệu tiếp theo hay không và có thể tránh count tùy cách truy vấn.
- **Sort field**: chỉ cho phép các field có ý nghĩa và có kế hoạch index phù hợp.
- **Khoảng ngày**: giới hạn khoảng thời gian và dùng điều kiện trên cột index-friendly.
- **Keyword search**: xác định rõ prefix, exact match hay contains; `LIKE '%term%'` có thể tốn kém nếu không có cơ chế tìm kiếm phù hợp.
- **Danh sách ID**: giới hạn số phần tử để tránh `IN` clause quá lớn.
- **Filter tùy chọn**: tránh tạo điều kiện truy vấn làm vô hiệu index mà không cần thiết.

Nếu dữ liệu rất lớn hoặc client duyệt tuần tự nhiều trang, cân nhắc cursor/keyset pagination. Cursor thường dựa trên một thứ tự ổn định, ví dụ `(createdAt, id)`, để tránh việc bản ghi mới được chèn làm dịch chuyển offset giữa các lần gọi. Nếu dùng cursor, tài liệu cần mô tả định dạng cursor, tính opaque, thời hạn và cách client gửi cursor tiếp theo.

## 11. Kiểm thử các giới hạn phân trang và filter

Kiểm thử cần bao phủ cả cấu hình resolver, validation DTO và schema OpenAPI.

### 11.1. Kiểm tra size tối đa

Với resolver giới hạn `max-page-size=100`, gửi request có `size=500` và xác nhận hành vi đúng với hợp đồng:

- Nếu chính sách là clamp: service nhận `Pageable.getPageSize() == 100`.
- Nếu chính sách là reject: response là `400` và body lỗi chỉ rõ giới hạn.

Không chỉ kiểm tra status `200`; hãy xác nhận page size thực tế được truyền xuống service/repository.

### 11.2. Kiểm tra filter DTO

Các trường hợp nên có:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Không truyền filter tùy chọn | Truy vấn không áp dụng điều kiện đó. |
| `keyword` dài hơn 80 ký tự | Validation lỗi. |
| `minPrice` âm | Validation lỗi. |
| `minPrice` lớn hơn `maxPrice` | Class-level validation lỗi. |
| `createdFrom` sau `createdTo` | Class-level validation lỗi. |
| Khoảng ngày vượt giới hạn | Validation lỗi theo chính sách. |
| `ids` vượt 50 phần tử | Validation lỗi. |
| Sort field ngoài allow-list | Trả `400`, không để repository ném lỗi thành `500`. |

### 11.3. Kiểm tra OpenAPI

Đọc `/v3/api-docs` hoặc URL group tương ứng và xác nhận:

- `page` có mô tả zero-based/one-based đúng cấu hình.
- `size` có default và maximum đúng runtime.
- `sort` mô tả cú pháp và field được phép.
- Filter parameters có đúng type, format, enum, min/max, maxLength hoặc maxItems.
- Filter DTO được mô tả là query parameters, không phải request body.
- Mô tả nêu các quy tắc liên trường không thể thể hiện bằng schema đơn.

Ví dụ MockMvc kiểm tra validation của filter:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProductSearchValidationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsKeywordLongerThanLimit() throws Exception {
        String keyword = "x".repeat(81);

        mockMvc.perform(get("/api/products")
                        .param("keyword", keyword))
                .andExpect(status().isBadRequest());
    }
}
```

Test này giả định controller kích hoạt Bean Validation cho `@ModelAttribute` và exception handler chuyển lỗi thành `400`. Nếu phiên bản Spring MVC hoặc cách cấu hình validation khác, hãy điều chỉnh cơ chế method validation và assertion theo ứng dụng thực tế.

## 12. Những lỗi thường gặp

- **Chỉ dùng `@PageableDefault` để giới hạn size**: annotation đặt default, không đặt max. Cấu hình resolver để giới hạn kích thước tối đa.
- **Không mô tả clamp hay reject**: client không biết `size` vượt ngưỡng được xử lý thế nào.
- **Giới hạn runtime nhưng không cập nhật OpenAPI**: Swagger UI có thể gợi ý giá trị mà server không chấp nhận.
- **Cho phép sort mọi property**: có thể tạo truy vấn nặng hoặc lỗi property path; dùng allow-list.
- **Không kiểm tra quan hệ giữa filter**: min/max riêng lẻ hợp lệ nhưng kết hợp lại không hợp lệ.
- **Không giới hạn khoảng ngày hoặc số lượng ID**: request có thể truy vấn quá rộng.
- **Nhầm `Page` và `Slice`**: response và chi phí truy vấn có thể khác nhau.
- **Không kiểm thử page index**: client và server có thể lệch zero-based/one-based.
- **Để filter DTO thành request body**: với query filter, dùng `@ModelAttribute` và `@ParameterObject` phù hợp.
- **Cho rằng OpenAPI constraint tự validate runtime**: schema mô tả hợp đồng; Spring cần Bean Validation hoặc logic tương ứng để thực thi.

## 13. Quy trình thiết kế API danh sách

1. **Chọn mô hình phân trang**: `Page`, `Slice` hoặc cursor/keyset theo nhu cầu dữ liệu.
2. **Đặt default và max page size**: cấu hình Spring Data Web, thống nhất chính sách clamp/reject.
3. **Chốt page index**: zero-based hoặc one-based và giữ nhất quán.
4. **Allow-list sort fields**: công bố field và direction được hỗ trợ.
5. **Thiết kế filter DTO**: chọn kiểu dữ liệu, required/optional, default và format.
6. **Đặt ràng buộc từng field và liên trường**: độ dài, khoảng số, enum, khoảng thời gian, số lượng phần tử.
7. **Tạo tài liệu OpenAPI**: dùng `@ParameterObject`, `@Schema` và description để công bố giới hạn.
8. **Kiểm tra query cost**: xem index, count query, sort và phạm vi dữ liệu.
9. **Kiểm thử biên**: xác nhận runtime và `/v3/api-docs` cùng phản ánh một hợp đồng.

## 14. Checklist review

- [ ] `page` dùng quy ước zero-based hoặc one-based được công bố rõ.
- [ ] `default-page-size` và `max-page-size` được cấu hình tường minh.
- [ ] Chính sách với size vượt giới hạn là clamp hay reject được mô tả.
- [ ] `@PageableDefault` chỉ được dùng cho default, không nhầm là max.
- [ ] `Pageable` và filter DTO được springdoc mô tả bằng `@ParameterObject`.
- [ ] OpenAPI thể hiện đúng default/max của `page` và `size`.
- [ ] Sort field và direction nằm trong allow-list.
- [ ] Filter có type, format, enum, min/max, maxLength hoặc maxItems phù hợp.
- [ ] Các quy tắc liên trường được validate ở server và mô tả trong tài liệu.
- [ ] Khoảng ngày, danh sách ID và keyword có giới hạn hợp lý.
- [ ] Lựa chọn `Page`, `Slice` hoặc cursor phù hợp với chi phí truy vấn.
- [ ] Integration test bao phủ giá trị hợp lệ, biên và không hợp lệ.
- [ ] `/v3/api-docs` khớp với hành vi runtime.

## 15. Tài liệu tham khảo

- [Spring Data – Web support và Pageable](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring Data Commons – `PageableHandlerMethodArgumentResolver`](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableHandlerMethodArgumentResolver.html)
- [Spring Boot – Application Properties: Spring Data Web](https://docs.spring.io/spring-boot/appendix/application-properties/index.html#appendix.application-properties.data)
- [Spring Framework – Data Binding và Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [OpenAPI Specification 3.1.2 – Parameter Object](https://spec.openapis.org/oas/v3.1.2.html#parameter-object)
- [springdoc-openapi FAQ – Pageable support](https://springdoc.org/faq.html)

Giới hạn phân trang và filter cần được thực thi ở server, mô tả trong OpenAPI và kiểm tra bằng request thực tế. Khi default, maximum, sort allow-list và các ràng buộc lọc được công bố rõ, client có thể tạo truy vấn hợp lệ còn ứng dụng kiểm soát tốt hơn chi phí đọc, sắp xếp và trả dữ liệu.
