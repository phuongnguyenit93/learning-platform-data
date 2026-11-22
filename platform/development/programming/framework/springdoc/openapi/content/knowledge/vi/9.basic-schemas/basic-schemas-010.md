# Giá trị mặc định khác với ví dụ minh họa

Trong tài liệu OpenAPI, **giá trị mặc định** (`default`) và **ví dụ minh họa** (`example`) đều giúp người đọc hiểu dữ liệu, nhưng chúng có ý nghĩa khác nhau. Giá trị mặc định mô tả giá trị được giả định hoặc sử dụng khi client không cung cấp dữ liệu. Ví dụ minh họa chỉ đưa ra một giá trị mẫu hợp lệ để người đọc hình dung cách gửi hoặc nhận dữ liệu.

Springdoc có thể đưa cả hai loại metadata vào đặc tả từ annotation OpenAPI. Tuy nhiên, annotation mô tả tài liệu không tự thay đổi hành vi của controller. Nếu API cần áp dụng một giá trị khi tham số hoặc field bị bỏ qua, code Spring phải thực hiện hành vi đó, chẳng hạn bằng `@RequestParam(defaultValue = ...)`, `@RequestHeader(defaultValue = ...)` hoặc logic khởi tạo DTO.

## 1. Phân biệt `default` và `example` trong OpenAPI

Giả sử API phân trang có tham số `size` với giá trị mặc định là `20`. Client thường gửi `size=10` trong một request cụ thể. Hai giá trị này có mục đích khác nhau:

- `default: 20` cho biết giá trị mặc định của tham số khi client không cung cấp giá trị.
- `example: 10` minh họa một giá trị cụ thể mà client có thể gửi.

Trong OpenAPI, schema có thể biểu diễn cả hai:

```yaml
name: size
in: query
required: false
schema:
  type: integer
  default: 20
  example: 10
```

`default` và `example` không thay thế cho nhau. Nếu chỉ khai báo `example: 10`, client không thể suy ra rằng server sẽ dùng `10` khi tham số vắng mặt. Nếu khai báo `default: 20`, tài liệu nói rõ giá trị mặc định là `20`, còn ví dụ `10` cho thấy client có thể chọn một giá trị khác.

| Tiêu chí | `default` | `example` |
| --- | --- | --- |
| Mục đích | Mô tả giá trị mặc định khi dữ liệu bị bỏ qua | Minh họa một giá trị mẫu |
| Ý nghĩa với hợp đồng | Có thể ảnh hưởng cách client hiểu hành vi khi không truyền dữ liệu | Giúp hiểu định dạng và cách sử dụng |
| Tự thay đổi hành vi server? | Không | Không |
| Có thể khác giá trị gửi thực tế? | Có, nếu client ghi đè | Có, vì chỉ là ví dụ |
| Vị trí trong OpenAPI | `default` trong Schema Object | `example` hoặc `examples` ở schema/parameter/media type tùy ngữ cảnh |

OpenAPI mô tả ý nghĩa của giá trị mặc định trong hợp đồng. Ứng dụng vẫn phải triển khai cùng hành vi để tài liệu không gây hiểu nhầm.

## 2. Khai báo default và example bằng `@Schema`

`@Schema` thuộc `io.swagger.v3.oas.annotations.media`. Có thể đặt annotation trên field, thuộc tính hoặc record component để mô tả schema. Thuộc tính `defaultValue` biểu diễn giá trị mặc định; `example` cung cấp giá trị mẫu.

```java
import io.swagger.v3.oas.annotations.media.Schema;

public record SearchRequest(
    @Schema(
        description = "Số trang bắt đầu từ 0",
        defaultValue = "0",
        example = "2"
    )
    Integer page,

    @Schema(
        description = "Số bản ghi trong một trang",
        defaultValue = "20",
        example = "10"
    )
    Integer size
) {}
```

Trong ví dụ, schema nói rằng `page` mặc định là `0`, `size` mặc định là `20`; ví dụ request minh họa việc client yêu cầu trang `2` với `10` bản ghi. Các chuỗi `"0"` và `"20"` là cách truyền giá trị vào thuộc tính annotation; Springdoc tạo schema theo kiểu dữ liệu Java và cần được kiểm tra ở tài liệu đầu ra.

`@Schema(defaultValue = ...)` chỉ mô tả metadata OpenAPI. Nó không tự khởi tạo field Java, không sửa giá trị `null` và không thay thế logic nghiệp vụ. Nếu controller nhận JSON và cần áp dụng mặc định, hãy cài đặt điều đó trong DTO hoặc service.

## 3. Áp dụng giá trị mặc định thực tế cho JSON DTO

Với request body JSON, client có thể bỏ qua một field tùy chọn. Nếu ứng dụng muốn dùng giá trị mặc định, DTO cần có logic tương ứng.

Ví dụ dùng class có field initializer:

```java
import io.swagger.v3.oas.annotations.media.Schema;

public class SearchRequest {

    @Schema(
        description = "Số trang bắt đầu từ 0",
        defaultValue = "0",
        example = "2"
    )
    private Integer page = 0;

    @Schema(
        description = "Số bản ghi trong một trang",
        defaultValue = "20",
        example = "10"
    )
    private Integer size = 20;

    public Integer getPage() {
        return page;
    }

    public void setPage(Integer page) {
        this.page = page;
    }

    public Integer getSize() {
        return size;
    }

    public void setSize(Integer size) {
        this.size = size;
    }
}
```

Khi Jackson tạo object bằng constructor mặc định, các field initializer được chạy. Nếu JSON không có `page` hoặc `size`, giá trị khởi tạo có thể được giữ lại. Nếu JSON gửi rõ `"size": null`, setter có thể ghi đè giá trị `20` thành `null`. Do đó, cần quyết định riêng cách xử lý field bị bỏ qua và field được gửi tường minh với `null`.

Một cách khác là chuẩn hóa giá trị ở constructor compact của record hoặc trong service:

```java
public record SearchRequest(Integer page, Integer size) {
    public SearchRequest {
        page = page == null ? 0 : page;
        size = size == null ? 20 : size;
    }
}
```

Với cách này, cả field bị bỏ qua và field gửi `null` đều nhận giá trị mặc định. Chỉ chọn cách này nếu hợp đồng nghiệp vụ xem hai tình huống đó là tương đương. Nếu `null` tường minh phải bị từ chối, hãy dùng validation hoặc xử lý sự hiện diện của field theo cách phù hợp.

Không nên dựa vào giá trị mặc định ngầm của kiểu primitive như `int` là `0` hoặc `boolean` là `false` nếu đó không phải quy tắc nghiệp vụ. Dùng kiểu wrapper như `Integer` hoặc `Boolean` khi cần phân biệt dữ liệu chưa được cung cấp với một giá trị hợp lệ bằng `0` hoặc `false`.

## 4. Default cho query parameter bằng `@RequestParam`

Với query parameter, Spring MVC cung cấp thuộc tính `defaultValue` trực tiếp trong `@RequestParam`. Thuộc tính này vừa tạo fallback lúc chạy vừa khiến tham số không còn bắt buộc.

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/products")
public String listProducts(
        @Parameter(
            description = "Trang bắt đầu từ 0",
            example = "2",
            schema = @Schema(defaultValue = "0")
        )
        @RequestParam(name = "page", defaultValue = "0") int page,

        @Parameter(
            description = "Số sản phẩm trên một trang",
            example = "10",
            schema = @Schema(defaultValue = "20")
        )
        @RequestParam(name = "size", defaultValue = "20") int size) {

    return "page=" + page + ", size=" + size;
}
```

Khi client gọi `/api/products` mà không gửi query parameter, Spring truyền `page = 0` và `size = 20` vào method. Nếu client gửi `?page=2&size=10`, các giá trị được truyền vào là `2` và `10`.

`@Parameter(example = ...)` cung cấp giá trị mẫu ở cấp parameter; `@Schema(defaultValue = ...)` mô tả default của schema. `@RequestParam(defaultValue = ...)` điều khiển hành vi runtime. Springdoc có thể tự suy ra một phần metadata từ Spring annotation, nhưng nên kiểm tra `/v3/api-docs` để chắc chắn giá trị default và example được biểu diễn như mong muốn.

### Chỉ khai báo default trong tài liệu

Nếu dùng `@RequestParam(required = false)` mà không đặt `defaultValue`, việc thêm `@Schema(defaultValue = "20")` không khiến Spring tự truyền `20` vào method:

```java
@GetMapping("/api/products")
public String listProducts(
        @Parameter(
            description = "Số sản phẩm mỗi trang",
            example = "10",
            schema = @Schema(defaultValue = "20")
        )
        @RequestParam(name = "size", required = false) Integer size) {

    int effectiveSize = size == null ? 20 : size;
    return "size=" + effectiveSize;
}
```

Ở đây, code tự áp dụng `20` khi `size` là `null`. Nếu bỏ phần `effectiveSize` và sử dụng `size` trực tiếp, tham số vẫn có thể là `null` dù tài liệu có `default: 20`. Đây là lý do phải phân biệt metadata với hành vi thực tế.

## 5. Default cho header và cookie

Spring MVC cũng hỗ trợ `defaultValue` với `@RequestHeader` và `@CookieValue`. Quy tắc tương tự query parameter: giá trị được dùng khi header/cookie vắng mặt hoặc rỗng, và tham số trở thành không bắt buộc.

```java
@GetMapping("/api/preferences")
public String getPreferences(
        @RequestHeader(name = "Accept-Language", defaultValue = "vi")
        String language,

        @CookieValue(name = "theme", defaultValue = "light")
        String theme) {

    return "language=" + language + ", theme=" + theme;
}
```

Nếu muốn thể hiện rõ metadata trong OpenAPI, có thể bổ sung `@Parameter`:

```java
@Parameter(
    description = "Ngôn ngữ ưu tiên của client",
    example = "en",
    schema = @Schema(defaultValue = "vi")
)
@RequestHeader(name = "Accept-Language", defaultValue = "vi")
String language
```

Tương tự, có thể mô tả cookie `theme` với `defaultValue = "light"` và example `"dark"`. Cần kiểm tra OpenAPI để xác nhận parameter có `in: header` hoặc `in: cookie`, `required: false` và default phù hợp.

Không dùng default của header/cookie để thay thế cơ chế xác thực. Ví dụ, không đặt một token mặc định vào `Authorization`; thông tin xác thực cần được xử lý qua security scheme và bảo mật runtime.

## 6. `@ExampleObject` cho request body

`@ExampleObject` phù hợp khi cần cung cấp một hoặc nhiều payload mẫu đầy đủ cho request body. Ví dụ:

```java
@Operation(
    summary = "Tìm kiếm sản phẩm",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = SearchRequest.class),
            examples = {
                @ExampleObject(
                    name = "DefaultPage",
                    summary = "Client chỉ định trang đầu và kích thước mặc định",
                    value = "{\"page\":0,\"size\":20}"
                ),
                @ExampleObject(
                    name = "CustomPage",
                    summary = "Client yêu cầu trang 2 với 10 bản ghi",
                    value = "{\"page\":2,\"size\":10}"
                )
            }
        )
    )
)
```

Các ví dụ trên thể hiện payload cụ thể. Chúng không quyết định giá trị fallback của DTO. Nếu muốn người đọc biết rằng `size` mặc định là `20` khi field bị bỏ qua, hãy mô tả `defaultValue` trên schema và bảo đảm code thực thi cùng quy tắc.

Một ví dụ có thể trùng với default, nhưng không bắt buộc. Ví dụ thường nên minh họa một trường hợp sử dụng hữu ích; default nên phản ánh giá trị thực sự được áp dụng khi bỏ qua dữ liệu.

## 7. Default trong schema response

`default` cũng có thể xuất hiện trong schema response, nhưng cần diễn giải đúng. Nó mô tả giá trị mặc định của schema nếu giá trị không được cung cấp; nó không có nghĩa server sẽ tự chèn giá trị đó vào response JSON.

Ví dụ schema:

```java
public record ProductSettings(
    @Schema(
        description = "Chế độ hiển thị",
        defaultValue = "light",
        example = "dark"
    )
    String theme
) {}
```

Nếu API thực sự luôn trả về `theme`, service phải tạo response với giá trị đã được chọn. Nếu server bỏ qua field, tài liệu không thể thay thế việc serialize giá trị đó. Khi field có thể vắng mặt hoặc `null`, hãy mô tả rõ tính tùy chọn/nullability theo phiên bản OpenAPI và chính sách response của ứng dụng.

Với response, example nên phản ánh một response có thể quan sát được. Không đặt một default giả định khiến client nghĩ server luôn trả về giá trị đó khi thực tế field có thể thiếu.

## 8. Chọn giá trị mặc định hợp lý

Default là một phần của hợp đồng API và có thể ảnh hưởng kết quả nghiệp vụ. Trước khi chọn default, hãy xem xét:

1. **Giá trị có an toàn không?** Ví dụ `page = 0` hoặc `size = 20` thường dễ hiểu; mặc định một bộ lọc quyền truy cập rộng có thể gây rủi ro.
2. **Có nằm trong giới hạn schema không?** `default` phải phù hợp kiểu dữ liệu, `minimum`, `maximum`, `enum`, `pattern` và các ràng buộc khác.
3. **Có nhất quán giữa runtime và tài liệu không?** `@RequestParam(defaultValue = "20")`, logic service và `@Schema(defaultValue = "20")` không nên mâu thuẫn.
4. **Có cần phân biệt thiếu với null?** JSON có thể bỏ qua property hoặc gửi `null` tường minh; ứng dụng cần quyết định hai trường hợp có cùng ý nghĩa không.
5. **Thay đổi default có ảnh hưởng client không?** Client bỏ qua tham số có thể nhận kết quả khác khi default đổi, vì vậy cần xem đây là thay đổi hành vi API.

Ví dụ default phải nằm trong miền giá trị hợp lệ:

```java
@Schema(
    description = "Số bản ghi mỗi trang, từ 1 đến 100",
    defaultValue = "20",
    example = "50",
    minimum = "1",
    maximum = "100"
)
Integer size
```

Giá trị mặc định `20` hợp lệ; ví dụ `50` cũng nằm trong giới hạn. Một default `200` sẽ mâu thuẫn với `maximum = 100` và gây hiểu nhầm cho client.

## 9. Kiểm tra default và example trong tài liệu được sinh ra

Sau khi khởi chạy ứng dụng, mở `/v3/api-docs` hoặc `/v3/api-docs.yaml`. Tìm parameter hoặc schema cần kiểm tra. Kết quả rút gọn có thể giống:

```yaml
parameters:
  - name: size
    in: query
    required: false
    description: Số sản phẩm trên một trang
    schema:
      type: integer
      default: 20
      example: 10
```

Với request body, tìm schema trong `components.schemas`:

```yaml
SearchRequest:
  type: object
  properties:
    page:
      type: integer
      default: 0
      example: 2
    size:
      type: integer
      default: 20
      example: 10
```

Đây là cấu trúc minh họa. Vị trí `example` có thể nằm ở parameter, schema hoặc media type tùy annotation và phiên bản thư viện. Điều cần xác nhận là default và example xuất hiện đúng ngữ cảnh, kiểu dữ liệu và giá trị mong muốn.

Trong Swagger UI, quan sát giá trị được hiển thị ban đầu cho parameter hoặc request body. Giao diện có thể dùng example/default để gợi ý payload tùy phiên bản; không nên dựa vào việc UI tự điền để kết luận server có thực thi default. Hãy gửi request thực tế không có tham số/field và kiểm tra kết quả runtime.

## 10. Kiểm thử trường hợp có, thiếu và null

Để xác minh default, cần kiểm tra các trường hợp khác nhau. Với query parameter:

```bash
# Không gửi size: server áp dụng default 20
curl "http://localhost:8080/api/products"

# Gửi size khác default: server dùng 10
curl "http://localhost:8080/api/products?size=10"
```

Với JSON body:

```json
{
  "page": 2,
  "size": 10
}
```

So sánh với payload bỏ qua `size`:

```json
{
  "page": 2
}
```

Và payload gửi `null` tường minh:

```json
{
  "page": 2,
  "size": null
}
```

Kết quả của hai payload cuối phụ thuộc cách DTO/Jackson và logic service được triển khai. Hãy xác định rõ hợp đồng: bỏ qua field có dùng default không, `null` có được chấp nhận không, hay `null` phải trả về lỗi validation. Không suy ra hành vi đó chỉ từ `@Schema(defaultValue = ...)`.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Swagger UI hiển thị example nhưng server không dùng giá trị đó | Nhầm `example` với default runtime | Thêm logic mặc định trong Spring hoặc dùng `defaultValue` của Spring annotation |
| Tài liệu có default nhưng method nhận `null` | Chỉ khai báo `@Schema(defaultValue = ...)` | Áp dụng fallback trong controller/service hoặc Spring annotation |
| Query parameter không được đánh dấu optional | Không dùng `defaultValue` hoặc metadata `required` không khớp | Kiểm tra `@RequestParam` và OpenAPI `required` |
| Default không xuất hiện trong OpenAPI | Annotation đặt sai vị trí hoặc Springdoc không suy ra giá trị runtime | Khai báo `@Schema(defaultValue = ...)` rõ ràng và kiểm tra JSON |
| Default không hợp lệ với schema | Default nằm ngoài minimum/maximum hoặc không thuộc enum | Đồng bộ default với các constraint |
| Field JSON bị `null` dù có initializer | JSON gửi `null` và Jackson ghi đè field | Quy định riêng hành vi null hoặc chuẩn hóa dữ liệu |
| Giá trị `0`/`false` bị hiểu nhầm là thiếu | Dùng primitive và không phân biệt giá trị mặc định ngầm | Dùng wrapper khi cần phân biệt trạng thái chưa cung cấp |
| Client phụ thuộc vào default cũ | Nhóm thay đổi default mà không đánh giá tác động | Quản lý thay đổi default như thay đổi hợp đồng API |

## 12. Checklist mô tả default và example

- [ ] `defaultValue` chỉ được dùng cho giá trị thực sự được áp dụng khi dữ liệu bị bỏ qua.
- [ ] `example` là giá trị mẫu hữu ích và hợp lệ với schema.
- [ ] `@Schema(defaultValue = ...)` và logic runtime không mâu thuẫn.
- [ ] `@RequestParam`, `@RequestHeader` hoặc `@CookieValue` dùng `defaultValue` khi Spring cần áp dụng fallback trực tiếp.
- [ ] DTO có logic khởi tạo hoặc chuẩn hóa khi request body cần default cho field bị bỏ qua.
- [ ] Đã xác định cách xử lý field thiếu và field `null` tường minh.
- [ ] Default nằm trong giới hạn kiểu dữ liệu và constraint của schema.
- [ ] Example không chứa dữ liệu nhạy cảm và không bị hiểu là giá trị fallback.
- [ ] Đã kiểm tra `default` và `example` trong `/v3/api-docs`.
- [ ] Đã thử request không gửi tham số/field, gửi giá trị khác default và gửi `null` nếu phù hợp.

`default` mô tả hành vi được kỳ vọng khi client bỏ qua dữ liệu; `example` minh họa một giá trị cụ thể. Springdoc giúp công bố cả hai trong OpenAPI, còn Spring MVC và code DTO/service chịu trách nhiệm áp dụng giá trị thực tế. Giữ ba phần này nhất quán giúp client hiểu đúng hợp đồng và tránh phụ thuộc vào một giá trị mẫu như thể đó là quy tắc runtime.
