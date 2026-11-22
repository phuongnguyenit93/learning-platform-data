# `style`, `explode` và tính tương thích với cơ chế binding thực tế

OpenAPI mô tả không chỉ tên và kiểu của một tham số mà còn cách tham số được tuần tự hóa trong URL, header hoặc cookie. Hai thuộc tính `style` và `explode` quy định cách biểu diễn mảng và object khi client gửi request. Tuy nhiên, Spring MVC hoặc WebFlux có cơ chế binding riêng để chuyển dữ liệu HTTP thành tham số Java.

Vì vậy, khai báo `style` và `explode` trong OpenAPI không tự thay đổi cách Spring đọc request. Đặc tả phải mô tả đúng định dạng mà handler thực sự chấp nhận. Nếu tài liệu ghi client gửi `tag=java&tag=spring` nhưng code chỉ đọc một giá trị, hoặc tài liệu ghi `filter[status]=ACTIVE` trong khi binder đang chờ `status=ACTIVE`, hợp đồng và runtime sẽ không khớp.

## 1. `style` và `explode` giải quyết vấn đề gì?

Một tham số kiểu chuỗi đơn thường dễ biểu diễn:

```text
GET /products?status=ACTIVE
```

Nhưng với mảng hoặc object, cùng một giá trị Java có thể được biểu diễn theo nhiều cách. Ví dụ, danh sách `java`, `spring` có thể được gửi như:

```text
?tag=java&tag=spring
```

hoặc:

```text
?tag=java,spring
```

Hai cách trên có ý nghĩa dữ liệu giống nhau nhưng cách tuần tự hóa khác nhau.

- **`style`** xác định quy tắc tuần tự hóa: dùng dấu phẩy, dấu chấm, dấu chấm phẩy, cặp tên/giá trị, dấu ngoặc vuông hoặc dấu phân cách khác.
- **`explode`** xác định mảng/object được mở rộng thành nhiều tham số hay gộp vào một giá trị theo style đã chọn.

Ví dụ với query parameter `tag`:

| `style` | `explode` | Biểu diễn mảng `java`, `spring` |
|---|---:|---|
| `form` | `true` | `?tag=java&tag=spring` |
| `form` | `false` | `?tag=java,spring` |

`style` và `explode` là metadata của OpenAPI Parameter Object. Chúng giúp Swagger UI, SDK generator và các client hiểu cách tạo request. Server vẫn phải thực hiện binding đúng với định dạng được mô tả.

## 2. Giá trị mặc định theo vị trí tham số

OpenAPI quy định style mặc định dựa trên vị trí (`in`) của parameter:

| Vị trí `in` | `style` mặc định | `explode` mặc định |
|---|---|---:|
| `query` | `form` | `true` |
| `path` | `simple` | `false` |
| `header` | `simple` | `false` |
| `cookie` | `form` | `true` |

Nếu không khai báo `style` hoặc `explode`, consumer sẽ áp dụng mặc định theo đặc tả OpenAPI. Dù vậy, với tham số mảng/object quan trọng, nên khai báo tường minh khi muốn tránh khác biệt giữa các công cụ hoặc cần bảo đảm client sinh ra dùng đúng định dạng.

Không phải mọi style đều dùng được ở mọi vị trí. Các lựa chọn thường gặp:

| Style | Vị trí phù hợp | Mô tả ngắn |
|---|---|---|
| `form` | Query, cookie | Dạng tên/giá trị; có thể lặp tên tham số. |
| `simple` | Path, header | Dạng đơn giản, thường dùng dấu phẩy để phân tách. |
| `matrix` | Path | Dạng `;name=value` gắn với path segment. |
| `label` | Path | Giá trị bắt đầu bằng dấu chấm `.`. |
| `spaceDelimited` | Query | Mảng dùng dấu cách làm dấu phân cách. |
| `pipeDelimited` | Query | Mảng dùng ký tự `|` làm dấu phân cách. |
| `deepObject` | Query | Object dùng key dạng `filter[property]=value`. |

`allowReserved` là thuộc tính liên quan của query parameter. Mặc định là `false`, nghĩa là các ký tự reserved được percent-encode theo quy tắc URI. Chỉ bật `allowReserved` khi hợp đồng thực sự yêu cầu giữ các ký tự reserved trong giá trị query và client/server đã được kiểm thử với cách mã hóa đó.

## 3. Cách tuần tự hóa mảng và object

### 3.1. Query `form`: dạng phổ biến nhất

Với `style: form`, `explode: true`, một mảng được biểu diễn bằng cách lặp lại tên query parameter:

```text
GET /products?tag=java&tag=spring&tag=api
```

Khi `explode: false`, các phần tử được ghép thành một giá trị, phân tách bằng dấu phẩy:

```text
GET /products?tag=java,spring,api
```

Với object gồm `role=admin` và `active=true`:

```text
# style=form, explode=true
GET /users?role=admin&active=true

# style=form, explode=false
GET /users?filter=role,admin,active,true
```

Ở dạng `explode=true`, tên các thuộc tính object trở thành tên query parameter. Nếu endpoint có nhiều object với thuộc tính trùng tên, cần thiết kế tên parameter hoặc cấu trúc request để tránh nhập nhằng.

### 3.2. Query `spaceDelimited` và `pipeDelimited`

Hai style này chủ yếu dùng cho mảng query:

```text
# style=spaceDelimited, explode=false
GET /products?tag=java%20spring%20api

# style=pipeDelimited, explode=false
GET /products?tag=java|spring|api
```

Ký tự dấu cách trong URL thường được mã hóa thành `%20`. Ký tự `|` cũng có thể được percent-encode tùy client. Không giả định chuỗi raw nhìn thấy trong log luôn giống hệt chuỗi client gửi trên mạng; hãy xem cả URL đã giải mã và giá trị Spring nhận được.

### 3.3. Query `deepObject` cho object

Với `style: deepObject`, `explode: true`, các thuộc tính object được biểu diễn bằng cú pháp ngoặc vuông:

```text
GET /products?filter[status]=ACTIVE&filter[minPrice]=100&filter[maxPrice]=500
```

Đây là cách dễ đọc khi một query parameter đại diện cho một object có nhiều thuộc tính. Tuy nhiên, Spring không tự biến mọi query parameter dạng `filter[status]` thành một DTO lồng nhau chỉ vì OpenAPI khai báo `deepObject`. Cần chọn cơ chế binding tương ứng hoặc tự đọc các key trong request parameter map.

### 3.4. Path `simple`, `label` và `matrix`

Với path parameter, `simple` là mặc định:

```text
# simple
/products/java,spring
```

`label` thêm dấu chấm ở đầu giá trị:

```text
# label
/products/.java,spring
```

`matrix` dùng dấu chấm phẩy và tên parameter:

```text
# matrix
/products/42;color=blue;size=large
```

Với `simple` hoặc `label`, array/object có quy tắc dấu phân cách riêng tùy `explode`. `matrix` có thể lặp tên thuộc tính khi `explode=true`. Đây là quy tắc serialization của OpenAPI; Spring cần nhận đúng chuỗi path và chuyển đổi theo kiểu tham số hoặc annotation phù hợp.

Spring MVC có `@MatrixVariable` để bind matrix variable. Ví dụ:

```java
@GetMapping("/products/{segment}")
ProductResponse findProduct(
        @PathVariable String segment,
        @MatrixVariable(pathVar = "segment", required = false)
        Map<String, String> filters) {
    return productService.find(segment, filters);
}
```

Với matrix variable, cần xác nhận cấu hình path matching của ứng dụng cho phép xử lý semicolon content. Nếu chỉ dùng `@PathVariable String`, Spring sẽ nhận giá trị path variable theo quy tắc path matching; nó không tự diễn giải mọi cấu trúc `matrix` thành map.

### 3.5. Header `simple` và cookie `form`

Header parameter dùng `simple` mặc định. Một array thường được biểu diễn bằng dấu phẩy:

```http
X-Scopes: read,write,admin
```

Cookie parameter dùng `form` mặc định. Tuy nhiên, cấu trúc cookie trên HTTP request có quy tắc riêng; không nên suy ra rằng cookie object có thể được Spring bind thành DTO chỉ từ `style=form`. Với cookie đơn, `@CookieValue` là cách binding trực tiếp thường dùng. Với cấu trúc phức tạp, cần quy ước encoding rõ ràng và tự chuyển đổi giá trị.

## 4. Khai báo `style` và `explode` trong springdoc

Springdoc dùng các annotation của Swagger để bổ sung metadata OpenAPI. Với một danh sách query parameter, có thể khai báo như sau:

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.Explode;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.enums.ParameterStyle;

@GetMapping("/products")
List<ProductResponse> findProducts(
        @Parameter(
                name = "tag",
                in = ParameterIn.QUERY,
                description = "Danh sách nhãn sản phẩm",
                style = ParameterStyle.FORM,
                explode = Explode.TRUE
        )
        @RequestParam(name = "tag", required = false)
        List<String> tags) {
    return productService.findByTags(tags);
}
```

Metadata trên mô tả query array theo dạng lặp tên parameter:

```text
GET /products?tag=java&tag=spring
```

Spring MVC có thể bind nhiều giá trị cùng tên vào `List<String>`. Với một số kiểu dữ liệu và converter mặc định, chuỗi phân tách bằng dấu phẩy cũng có thể được chuyển thành collection. Nếu muốn công bố duy nhất một định dạng, hãy kiểm thử request thật và khai báo style/explode khớp với định dạng đó.

Với dạng comma-separated, có thể khai báo:

```java
@Parameter(
        name = "tag",
        in = ParameterIn.QUERY,
        style = ParameterStyle.FORM,
        explode = Explode.FALSE
)
@RequestParam(name = "tag", required = false)
List<String> tags
```

Kết quả mô tả là:

```text
GET /products?tag=java,spring
```

Annotation OpenAPI chỉ mô tả cách client nên tuần tự hóa parameter. Nếu Spring binding không chấp nhận đúng dạng này, cần thay đổi kiểu tham số, converter hoặc logic parse để hợp đồng được thực thi đúng.

## 5. Binding query array trong Spring MVC

### 5.1. `@RequestParam List<T>` với tên lặp

Đây là dạng tự nhiên cho query parameter `form` với `explode=true`:

```java
@GetMapping("/products")
List<ProductResponse> findProducts(
        @RequestParam(name = "tag", required = false)
        List<String> tags) {
    return productService.findByTags(tags);
}
```

Request:

```text
GET /products?tag=java&tag=spring
```

Spring MVC lấy các giá trị của cùng tên parameter và chuyển đổi thành `List<String>`. Với `Long`, `UUID`, enum hoặc kiểu tự định nghĩa, việc chuyển đổi còn phụ thuộc converter có sẵn hoặc converter mà ứng dụng đăng ký.

### 5.2. Dùng `MultiValueMap` khi cần giữ mọi giá trị

Nếu endpoint cần đọc nhiều giá trị của nhiều parameter và muốn giữ nguyên danh sách, dùng `MultiValueMap`:

```java
@GetMapping("/products")
List<ProductResponse> findProducts(
        @RequestParam MultiValueMap<String, String> params) {
    List<String> tags = params.get("tag");
    return productService.findByTags(tags);
}
```

`MultiValueMap` giữ nhiều giá trị cho cùng một key, phù hợp với `?tag=java&tag=spring`. `Map<String, String>` thông thường chỉ phù hợp khi mỗi key cần một giá trị; nếu hợp đồng cho phép lặp key, hãy chọn kiểu có thể giữ nhiều giá trị.

### 5.3. Comma-separated và converter

Spring có cơ chế chuyển đổi chuỗi sang collection. Trong các trường hợp thông dụng, một giá trị như `tag=java,spring` có thể được tách thành hai phần tử khi bind vào `List<String>`. Tuy nhiên, hành vi này phụ thuộc kiểu đích, converter và cấu hình chuyển đổi.

Nếu cần kiểm soát chính xác, có thể nhận `String` rồi parse theo quy tắc của API:

```java
@GetMapping("/products")
List<ProductResponse> findProducts(
        @RequestParam(name = "tag", required = false) String tagValue) {
    List<String> tags = tagValue == null || tagValue.isBlank()
            ? List.of()
            : Arrays.stream(tagValue.split(",", -1))
                    .map(String::trim)
                    .toList();
    return productService.findByTags(tags);
}
```

Nếu phần tử có thể chứa dấu phẩy, quy ước comma-separated đơn giản không đủ để phân biệt dấu phẩy trong dữ liệu với dấu phẩy phân tách. Khi đó, hãy dùng repeated parameters, một encoding rõ ràng hoặc một request body thích hợp.

## 6. Binding object query trong Spring

### 6.1. `@ModelAttribute` và `@ParameterObject`

Với bộ lọc tìm kiếm có các field đơn giản, một DTO query thường dễ dùng và dễ kiểm tra:

```java
public class ProductFilter {
    private String status;
    private BigDecimal minPrice;
    private BigDecimal maxPrice;

    // getters và setters
}
```

Controller:

```java
@GetMapping("/products")
List<ProductResponse> search(
        @ParameterObject @ModelAttribute ProductFilter filter) {
    return productService.search(filter);
}
```

Spring MVC bind các query parameter vào thuộc tính DTO theo tên property:

```text
GET /products?status=ACTIVE&minPrice=100&maxPrice=500
```

`@ParameterObject` giúp springdoc phân rã các thuộc tính của object thành các query parameter trong OpenAPI. Annotation này phục vụ việc mô tả tài liệu; `@ModelAttribute` mới là cơ chế Spring dùng để bind request parameter vào object. Hai annotation có vai trò khác nhau và không thay thế lẫn nhau.

### 6.2. `deepObject` và key dạng ngoặc vuông

Nếu hợp đồng cần đúng định dạng:

```text
GET /products?filter[status]=ACTIVE&filter[minPrice]=100
```

Spring MVC có thể đọc toàn bộ query parameter qua `MultiValueMap` và ứng dụng tự phân tích các key `filter[...]`:

```java
@GetMapping("/products")
List<ProductResponse> search(
        @RequestParam MultiValueMap<String, String> params) {
    String status = params.getFirst("filter[status]");
    String minPriceValue = params.getFirst("filter[minPrice]");

    ProductFilter filter = new ProductFilter();
    filter.setStatus(status);
    if (minPriceValue != null) {
        filter.setMinPrice(new BigDecimal(minPriceValue));
    }
    return productService.search(filter);
}
```

Metadata OpenAPI có thể mô tả parameter `filter` bằng `deepObject`:

```java
@Parameter(
        name = "filter",
        in = ParameterIn.QUERY,
        style = ParameterStyle.DEEPOBJECT,
        explode = Explode.TRUE,
        schema = @Schema(implementation = ProductFilter.class)
)
```

Đặt metadata này trên tham số/operation tương ứng theo cấu trúc code của dự án. Cần xác nhận bản springdoc và Swagger Annotations đang dùng hỗ trợ cách biểu diễn schema mong muốn.

Không nhầm `deepObject` với DTO `@ModelAttribute` phẳng. `@ModelAttribute ProductFilter` thường bind các key `status`, `minPrice`; còn `deepObject` dùng key có tiền tố và ngoặc vuông `filter[status]`. Nếu muốn dùng deepObject, code phải đọc đúng tên key hoặc có binder/converter tùy chỉnh.

## 7. Binding path, header và cookie

| Vị trí | Cơ chế Spring thường dùng | Điểm cần xác minh |
|---|---|---|
| Path | `@PathVariable` | Kiểu Java có converter tương ứng; chuỗi phân tách của array có khớp style không? |
| Matrix path | `@MatrixVariable` | Path matching có giữ semicolon content và map đúng path segment không? |
| Header | `@RequestHeader` | Header đơn, header lặp hoặc giá trị comma-separated có được chuyển đổi như mong đợi không? |
| Cookie | `@CookieValue` | Giá trị cookie được bind theo tên; object phức tạp cần quy ước encoding và parse riêng. |

Ví dụ header:

```java
@GetMapping("/reports")
List<ReportResponse> reports(
        @RequestHeader(name = "X-Scopes", required = false)
        List<String> scopes) {
    return reportService.findByScopes(scopes);
}
```

Nếu OpenAPI mô tả `style=simple` và mảng header dùng dấu phẩy, kiểm thử request với header `X-Scopes: read,write`. Nếu hệ thống proxy hoặc client gửi nhiều header cùng tên, hãy xác minh cách servlet container và Spring gộp/đọc giá trị.

Ví dụ cookie đơn:

```java
@GetMapping("/preferences")
PreferencesResponse preferences(
        @CookieValue(name = "locale", required = false) String locale) {
    return preferenceService.get(locale);
}
```

Cookie `locale` ở đây là một chuỗi đơn. Không nên mô tả nó như object exploded chỉ vì OpenAPI hỗ trợ `form` cho cookie; `@CookieValue` không tự bind một nhóm cookie thành DTO.

## 8. Kiểm tra metadata OpenAPI được sinh ra

Sau khi khai báo `@Parameter`, mở `/v3/api-docs` hoặc endpoint tài liệu đã cấu hình và kiểm tra parameter trong operation. Với array query lặp tên, tài liệu nên thể hiện dạng tương tự:

```yaml
parameters:
  - name: tag
    in: query
    style: form
    explode: true
    schema:
      type: array
      items:
        type: string
```

Nếu `style` và `explode` không xuất hiện, consumer áp dụng mặc định của OpenAPI theo vị trí và style. Nếu tài liệu có giá trị không như mong muốn, kiểm tra annotation, kiểu tham số Java và phiên bản Swagger Annotations được springdoc sử dụng.

Không nên chỉ kiểm tra annotation trong source code. Cần đọc tài liệu JSON thực tế vì springdoc có thể suy ra metadata từ mapping, kiểu Java, annotation và cấu hình khác nhau.

## 9. Kiểm thử tương thích giữa OpenAPI và Spring binding

Một bài kiểm thử tốt nên gửi request theo đúng cách serialization mà OpenAPI công bố, sau đó xác nhận handler nhận được các giá trị dự kiến.

Ví dụ với MockMvc và query parameter lặp:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProductParameterBindingTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void bindsRepeatedTagParameters() throws Exception {
        mockMvc.perform(get("/products")
                        .param("tag", "java", "spring"))
                .andExpect(status().isOk());
    }
}
```

Nếu endpoint dùng comma-separated, thêm kiểm thử riêng với `.param("tag", "java,spring")`. Nếu dùng `deepObject`, gửi đúng các key `filter[status]`, `filter[minPrice]` và xác nhận object/service nhận đúng dữ liệu. Kiểm thử status `200` một mình chưa đủ nếu cần xác minh từng phần tử; nên kiểm tra response hoặc dùng mock service để xác nhận đối số đã bind.

Một ma trận kiểm thử có thể áp dụng:

| Dạng OpenAPI | Request mẫu | Kiểu/annotation Spring | Điều cần xác nhận |
|---|---|---|---|
| `form`, `explode=true` | `?tag=a&tag=b` | `@RequestParam List<String>` | Danh sách có đủ hai phần tử. |
| `form`, `explode=false` | `?tag=a,b` | `String`, `List<String>` hoặc converter | Quy tắc tách dấu phẩy nhất quán. |
| `deepObject`, `explode=true` | `?filter[status]=ACTIVE` | `MultiValueMap` hoặc binder tùy chỉnh | Key có tiền tố và ngoặc vuông được parse đúng. |
| `simple` path | `/items/a,b` | `@PathVariable` | Converter nhận đúng giá trị/collection. |
| `simple` header | `X-Scopes: a,b` | `@RequestHeader` | Header được tách và chuyển đổi đúng. |

## 10. Những lỗi thường gặp

- **Chỉ khai báo `explode=true` rồi mong Spring tự thay đổi binding**: annotation chỉ mô tả OpenAPI; handler phải nhận đúng định dạng.
- **Mô tả repeated query nhưng dùng một `String` đơn**: chuyển sang `List`, `MultiValueMap` hoặc xử lý danh sách rõ ràng.
- **Mô tả comma-separated nhưng parser hiểu dấu phẩy là dữ liệu**: xác định delimiter và kiểm thử trường hợp phần tử có ký tự đặc biệt.
- **Dùng `@ParameterObject` rồi kỳ vọng deepObject**: `@ParameterObject` chủ yếu flatten thuộc tính query; `filter[field]` cần binding tương ứng.
- **Dùng matrix style nhưng chỉ đọc `@PathVariable`**: xem xét `@MatrixVariable` và cấu hình path matching.
- **Bật `allowReserved` mà không kiểm tra URL encoding**: ký tự reserved như `&` hoặc `=` có thể ảnh hưởng cấu trúc query.
- **Dựa vào Swagger UI Try it out làm bằng chứng duy nhất**: kiểm thử trực tiếp request ở runtime và kiểm tra JSON OpenAPI được sinh ra.
- **Giả định mọi generator serialize giống nhau**: kiểm tra request do SDK/client thực tế tạo ra, đặc biệt khi có object, mảng hoặc ký tự cần percent-encode.

## 11. Quy trình chọn style/explode cho một tham số

1. **Xác định vị trí parameter**: query, path, header hay cookie.
2. **Xác định kiểu dữ liệu**: scalar, array hay object; ghi rõ tên, kiểu phần tử và quy tắc giá trị.
3. **Chọn định dạng client sẽ gửi**: repeated key, comma-separated, matrix, label, deepObject hoặc cách khác được OpenAPI hỗ trợ.
4. **Khai báo `style` và `explode`**: dùng mặc định nếu phù hợp; khai báo tường minh khi cần một serialization cụ thể.
5. **Chọn cơ chế Spring binding**: `@RequestParam`, `MultiValueMap`, `@ModelAttribute`, `@PathVariable`, `@MatrixVariable`, `@RequestHeader` hoặc `@CookieValue`.
6. **Kiểm thử request thực tế**: xác nhận giá trị được bind đúng với request mẫu đã công bố.
7. **Đọc lại `/v3/api-docs`**: bảo đảm tài liệu có style/explode và schema mong muốn.
8. **Kiểm tra consumer**: thử Swagger UI hoặc SDK generator để xác nhận client tạo đúng request.

## 12. Checklist review

- [ ] Vị trí `in` và `style` phù hợp với OpenAPI Specification.
- [ ] Giá trị mặc định của `style` và `explode` đã được hiểu đúng.
- [ ] Array/object có ví dụ request minh họa rõ ràng.
- [ ] `explode` phản ánh đúng repeated key hay một giá trị ghép.
- [ ] `allowReserved` chỉ bật khi có nhu cầu và đã kiểm thử URL encoding.
- [ ] Spring binding có thể nhận định dạng request đã công bố.
- [ ] `@ParameterObject` không bị nhầm với cơ chế `deepObject`.
- [ ] Matrix variable có cấu hình path matching tương ứng.
- [ ] Tài liệu `/v3/api-docs` đã được kiểm tra sau khi cấu hình annotation.
- [ ] Integration test bao phủ các định dạng request quan trọng.

## 13. Tài liệu tham khảo

- [OpenAPI Specification 3.1.2 – Parameter Object](https://spec.openapis.org/oas/v3.1.2.html#parameter-object)
- [OpenAPI Specification 3.0.4 – Parameter Object](https://spec.openapis.org/oas/v3.0.4.html#parameter-object)
- [OpenAPI Initiative – Parameter serialization](https://learn.openapis.org/specification/parameters.html)
- [Spring Framework – `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring Framework – `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework – Matrix Variables](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/matrix-variables.html)
- [springdoc-openapi FAQ – Parameter objects](https://springdoc.org/faq.html)

`style` và `explode` mô tả cách client tuần tự hóa tham số theo hợp đồng OpenAPI. Để API hoạt động đúng, hãy đối chiếu metadata đó với cơ chế binding và converter thật của Spring, sau đó kiểm tra bằng request integration test. Tài liệu tốt phải mô tả đúng dữ liệu server nhận được, không chỉ trình bày một cú pháp hợp lệ trên Swagger UI.
