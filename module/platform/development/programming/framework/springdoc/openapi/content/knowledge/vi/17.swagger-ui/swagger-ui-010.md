# Thiết lập giá trị mặc định khác với ép hành vi của API

Khi xem tài liệu trong Swagger UI, client có thể thấy một tham số đã có sẵn giá trị, chẳng hạn `pageSize = 20` hoặc `includeArchived = false`. Giá trị đó giúp người dùng hiểu cách gọi endpoint và có thể được công cụ dùng làm gợi ý khi thử request. Tuy nhiên, việc khai báo `default` trong OpenAPI không tự khiến Spring Boot áp dụng giá trị đó khi client bỏ qua trường.

Muốn API thật sự dùng giá trị mặc định, ứng dụng phải triển khai hành vi ở runtime bằng Spring MVC binding, khởi tạo DTO, Jackson hoặc logic nghiệp vụ. Muốn giới hạn giá trị hợp lệ, cần validation hoặc quy tắc xử lý tương ứng. Với springdoc-openapi, cần giữ metadata `default`/`example` trong tài liệu đồng bộ với hành vi runtime để client không hiểu sai.

## 1. Ba lớp cần phân biệt

Giá trị mặc định có thể xuất hiện ở ba lớp khác nhau:

| Lớp | Ví dụ | Tác dụng |
|---|---|---|
| OpenAPI contract | `schema.default: 20` | Mô tả giá trị mặc định của dữ liệu theo hợp đồng |
| Swagger UI | Hiển thị `20` trong form thử request | Gợi ý hoặc điền giá trị để người dùng thao tác thuận tiện |
| API runtime | `@RequestParam(defaultValue = "20")` | Spring thực sự dùng `20` khi request không cung cấp tham số theo quy tắc binding |

Ba lớp có liên quan nhưng không tự đồng bộ trong mọi tình huống. Ví dụ, nếu OpenAPI khai báo `default: 20` nhưng controller nhận `Integer pageSize` mà không có default runtime, request thiếu `pageSize` có thể làm giá trị Java thành `null`. Swagger UI hiển thị `20` không thay đổi cách Spring xử lý request được gửi từ curl, Postman hay một ứng dụng khác.

## 2. Phân biệt `default`, `example`, `required` và `enum`

Các thuộc tính trong OpenAPI giải quyết những câu hỏi khác nhau:

| Thuộc tính | Câu hỏi | Ví dụ |
|---|---|---|
| `default` | Giá trị mặc định được mô tả khi không cung cấp giá trị là gì? | `default: 20` |
| `example` | Một giá trị minh họa có thể dùng là gì? | `example: 20` |
| `examples` | Những ví dụ đặt tên nào được cung cấp? | `basic`, `largePage` |
| `required` | Tham số hoặc thuộc tính có bắt buộc xuất hiện không? | `required: true` |
| `enum` | Những giá trị nào được phép theo schema? | `enum: [small, medium, large]` |
| `minimum`, `maximum` | Giá trị số được giới hạn trong khoảng nào? | `minimum: 1`, `maximum: 100` |

`default` không làm cho tham số trở thành optional, không ép client gửi giá trị đó và không giới hạn client chọn giá trị khác. Nếu một parameter vừa bắt buộc vừa có default, cần kiểm tra lại ý nghĩa hợp đồng: client phải gửi giá trị, nên default có thể không giúp ích cho trường hợp thiếu parameter.

Ví dụ schema:

```yaml
type: object
properties:
  pageSize:
    type: integer
    default: 20
    example: 20
    minimum: 1
    maximum: 100
```

Schema cho biết `pageSize` có default được mô tả là 20, ví dụ là 20 và giá trị hợp lệ theo giới hạn từ 1 đến 100. Nó không tự chạy logic gán 20 trong ứng dụng.

## 3. `default` trong OpenAPI là metadata của hợp đồng

Trong Schema Object, `default` mô tả giá trị được giả định khi dữ liệu không được cung cấp. Đây là metadata dành cho người đọc và công cụ tiêu thụ schema. OpenAPI không yêu cầu server tự điền giá trị vào request body hoặc query parameter.

Ví dụ parameter:

```yaml
paths:
  /api/orders:
    get:
      parameters:
        - name: pageSize
          in: query
          required: false
          description: Số đơn hàng tối đa trả về trong một trang
          schema:
            type: integer
            default: 20
            minimum: 1
            maximum: 100
```

Client có thể hiểu rằng nếu không truyền `pageSize`, giá trị được giả định theo hợp đồng là 20. Nhưng để server thực sự áp dụng 20, controller hoặc tầng xử lý phải có logic tương ứng.

Trong OpenAPI 3.0 và 3.1, `default` vẫn là thông tin mô tả trong schema. Việc nâng phiên bản OpenAPI không biến `default` thành cơ chế thực thi ở server.

## 4. Swagger UI dùng default và example như thế nào?

Swagger UI đọc OpenAPI document để hiển thị parameter, schema và ví dụ. Tùy loại dữ liệu, phiên bản Swagger UI và cách schema được khai báo, giá trị `default` hoặc `example` có thể được trình bày như gợi ý trong giao diện hoặc dùng khi tạo nội dung thử request.

Người dùng vẫn có thể sửa giá trị trước khi bấm **Try it out** và gửi request. Khi request được gửi, server chỉ nhận dữ liệu thực sự có trong HTTP request. Giao diện không thể áp đặt giá trị mặc định lên mọi client khác.

Ví dụ parameter có cả default và example:

```yaml
- name: pageSize
  in: query
  required: false
  schema:
    type: integer
    default: 20
    minimum: 1
    maximum: 100
  example: 20
```

`default` mô tả giá trị mặc định của schema; `example` cung cấp giá trị minh họa cho parameter. Nếu ví dụ là một request đặc biệt, có thể dùng `examples` để đặt tên và mô tả từng trường hợp. Không nên dùng một ví dụ như thể đó là giá trị runtime bắt buộc.

## 5. Khai báo default/example bằng `@Schema` và `@Parameter`

Springdoc có thể đọc metadata từ Swagger Annotations. Với tham số query, có thể khai báo rõ mô tả, ví dụ và schema default:

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/orders")
OrderPage listOrders(
        @Parameter(
            description = "Số đơn hàng tối đa trong một trang",
            example = "20",
            schema = @Schema(
                defaultValue = "20",
                minimum = "1",
                maximum = "100"
            )
        )
        @RequestParam(required = false) @Min(1) @Max(100) Integer pageSize) {
    // Xử lý ở runtime được trình bày ở phần tiếp theo.
    return orderService.list(pageSize);
}
```

`@Schema(defaultValue = "20")` bổ sung metadata default vào schema được sinh. `@Parameter(example = "20")` mô tả giá trị minh họa của parameter. Các annotation này không tự gán giá trị vào `pageSize`.

Nếu phiên bản springdoc đang dùng đã suy ra default từ annotation Spring MVC, hãy kiểm tra `/v3/api-docs` trước khi khai báo metadata lặp. Khi cần khai báo tường minh bằng Swagger Annotations, giữ giá trị trong `@Schema` đồng bộ với giá trị runtime.

## 6. Ép default runtime cho query parameter bằng Spring MVC

Muốn Spring thực sự dùng một giá trị khi query parameter bị thiếu, có thể dùng `@RequestParam(defaultValue = "...")`:

```java
@GetMapping("/api/orders")
OrderPage listOrders(
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(100) int pageSize) {
    return orderService.list(pageSize);
}
```

Khi client gọi:

```http
GET /api/orders
```

Spring MVC bind `pageSize` bằng 20. Khi client gọi:

```http
GET /api/orders?pageSize=50
```

giá trị được bind là 50. Với `@RequestParam`, khai báo `defaultValue` cũng làm parameter không còn bắt buộc theo cơ chế binding của Spring.

Spring MVC áp dụng `defaultValue` khi parameter bị thiếu hoặc có giá trị rỗng theo quy tắc binding. Nếu muốn phân biệt rõ không truyền, truyền chuỗi rỗng và truyền một giá trị cụ thể, hãy kiểm thử các trường hợp đó với phiên bản Spring đang dùng.

`@RequestParam(required = false) Integer pageSize` không tương đương `@RequestParam(defaultValue = "20") int pageSize`. Trường hợp đầu có thể nhận null khi thiếu; trường hợp sau có giá trị runtime 20.

## 7. Khai báo default cho request header

Spring MVC cũng hỗ trợ default cho request header:

```java
@GetMapping("/api/profile")
ProfileResponse getProfile(
        @RequestHeader(name = "X-Client-Locale", defaultValue = "vi-VN")
        String locale) {
    return profileService.getProfile(locale);
}
```

Nếu header không được gửi, Spring bind `locale` bằng `vi-VN`. Có thể mô tả header trong OpenAPI bằng `@Parameter` hoặc để springdoc suy luận từ mapping, sau đó kiểm tra tài liệu được sinh.

Không nên dùng default giả cho header bảo mật như `Authorization`. Nếu header xác thực bị thiếu, security layer phải từ chối request theo chính sách thay vì thay bằng một giá trị mặc định.

## 8. Giá trị mặc định trong request body DTO

Với JSON request body, giá trị mặc định có thể được áp dụng bằng field initializer hoặc constructor của DTO. Ví dụ:

```java
public class SearchRequest {

    @Schema(
        description = "Có bao gồm đơn hàng đã lưu trữ hay không",
        defaultValue = "false",
        example = "false"
    )
    private boolean includeArchived = false;

    @Schema(
        description = "Số phần tử tối đa",
        defaultValue = "20",
        example = "20"
    )
    @Min(1)
    @Max(100)
    private Integer pageSize = 20;

    // getters và setters
}
```

Với bean mutable được Jackson tạo bằng constructor không tham số, nếu JSON không có thuộc tính, field initializer thường được giữ nguyên. Nếu JSON gửi `"pageSize": 50`, setter gán 50. Nếu JSON gửi `"pageSize": null`, wrapper `Integer` có thể bị gán null theo cấu hình mặc định, dù field có initializer 20.

Điều này cho thấy ba trạng thái có thể khác nhau:

| JSON body | Kết quả thường gặp với DTO minh họa |
|---|---|
| Không có `pageSize` | Giữ initializer 20 |
| `"pageSize": null` | Wrapper có thể thành null |
| `"pageSize": 50` | Giá trị 50 |

Hành vi thực tế còn phụ thuộc constructor/record, Jackson annotations, custom deserializer và cấu hình `ObjectMapper`. Hãy kiểm tra DTO đang dùng thay vì mặc định rằng mọi loại object đều áp dụng initializer giống nhau.

## 9. Default trong schema không tự điền request body

Giả sử OpenAPI khai báo:

```yaml
SearchRequest:
  type: object
  properties:
    pageSize:
      type: integer
      default: 20
```

Nếu client gửi body:

```json
{}
```

OpenAPI không tự sửa JSON thành:

```json
{
  "pageSize": 20
}
```

Việc gán 20 phải được thực hiện bởi DTO initializer, constructor, Jackson deserializer, controller hoặc service. Nếu không có logic đó, `pageSize` có thể là null hoặc giá trị mặc định của kiểu Java.

Swagger UI cũng không thể bảo đảm mọi request body được điền default. Một số dạng schema và giao diện có thể hiển thị default/example để người dùng tham khảo, nhưng client có thể xóa trường hoặc gửi payload khác. Server vẫn phải xử lý trường hợp thiếu theo hợp đồng runtime.

## 10. Phân biệt default với validation và giới hạn hợp lệ

Default chỉ mô tả hoặc cung cấp giá trị khi thiếu. Validation quyết định giá trị nào được chấp nhận.

Ví dụ:

```java
@RequestParam(defaultValue = "20")
@Min(1)
@Max(100)
int pageSize
```

Ý nghĩa:

- Không truyền `pageSize`: Spring bind 20.
- Truyền `pageSize=50`: Spring bind 50.
- Truyền `pageSize=0`: validation từ chối nếu method validation được bật và xử lý lỗi được cấu hình.
- Truyền `pageSize=500`: validation từ chối vì vượt mức tối đa.

`default: 20` không giới hạn người dùng chỉ được gửi 20. `maximum: 100` và `minimum: 1` mới mô tả giới hạn schema; `@Min` và `@Max` cùng cơ chế validation mới thực thi giới hạn trong ứng dụng.

Với constraint đặt trực tiếp trên method parameter trong controller, hãy bảo đảm method validation được kích hoạt theo phiên bản Spring Boot/Spring Framework của dự án (thường thông qua `@Validated` và cấu hình validation tương ứng). Không giả định annotation constraint tự chạy nếu chưa có cơ chế validation.

## 11. Default trong tầng service và cấu hình ứng dụng

Không phải default nào cũng nên đặt ở controller. Khi nhiều endpoint dùng chung một quy tắc, service hoặc cấu hình ứng dụng có thể là nơi phù hợp hơn.

Ví dụ service áp dụng fallback:

```java
public OrderPage list(Integer requestedPageSize) {
    int pageSize = requestedPageSize == null ? 20 : requestedPageSize;

    if (pageSize < 1 || pageSize > 100) {
        throw new InvalidPageSizeException(pageSize);
    }

    return orderRepository.findPage(pageSize);
}
```

Trong trường hợp này, controller có thể nhận `Integer` nullable và service quyết định fallback. Cách này hữu ích khi nhiều luồng gọi service không đi qua cùng một controller. Tuy nhiên, cần thống nhất default được công bố trong OpenAPI với giá trị service áp dụng.

Nếu default thay đổi theo môi trường hoặc vận hành, có thể lấy từ `application.yml`:

```yaml
app:
  orders:
    default-page-size: 20
    max-page-size: 100
```

```java
@ConfigurationProperties(prefix = "app.orders")
public record OrderQueryProperties(
        int defaultPageSize,
        int maxPageSize
) {}
```

Khi cấu hình default từ property, hãy dùng cùng nguồn giá trị để khởi tạo runtime và tạo OpenAPI metadata nếu cần. Tránh để tài liệu ghi 20 trong khi môi trường production cấu hình 50.

## 12. Giá trị mặc định của response khác giá trị mặc định của request

Default trong request schema thường giúp client biết server sẽ dùng giá trị nào nếu trường không được cung cấp. Với response schema, `default` không có nghĩa server tự động thêm thuộc tính bị thiếu vào response JSON.

Ví dụ response DTO:

```java
public class OrderResponse {
    private String status;
    private boolean archived;

    // getters và setters
}
```

Nếu serializer bỏ qua thuộc tính `archived` hoặc DTO không được gán giá trị mong muốn, `default: false` trong OpenAPI không tự thêm `"archived": false` vào response. Muốn response luôn có giá trị, hãy gán trong mapper, constructor hoặc service và cấu hình serialization phù hợp.

Chỉ khai báo default trong response schema khi đó thực sự là giá trị mặc định có ý nghĩa trong hợp đồng. Nếu server luôn trả trường với giá trị cụ thể, ví dụ `false`, dùng `example` có thể phù hợp hơn để minh họa payload.

## 13. Dùng `examples` cho nhiều kịch bản thử request

Khi endpoint có các tình huống sử dụng khác nhau, một ví dụ duy nhất có thể không đủ. OpenAPI hỗ trợ `examples` để mô tả nhiều trường hợp có tên.

Ví dụ request body:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/SearchRequest'
      examples:
        defaultSearch:
          summary: Tìm kiếm với kích thước trang mặc định
          value:
            keyword: laptop
            pageSize: 20
        largePage:
          summary: Tìm kiếm với trang lớn hơn
          value:
            keyword: laptop
            pageSize: 50
```

Ví dụ có tên giúp người dùng Swagger UI chọn kịch bản thử. `examples` không thay thế default runtime và không giới hạn request chỉ được dùng các payload đó.

Trong Java có thể dùng `@ExampleObject` bên trong `@Content` của `@RequestBody` hoặc `@ApiResponse`, tùy vị trí cần mô tả. Cần kiểm tra annotation sinh ra đúng media type và schema.

## 14. Kiểm tra default trong tài liệu và hành vi runtime

Sau khi khai báo default, cần xác minh cả OpenAPI document lẫn request thực tế:

1. Mở `/v3/api-docs` hoặc `/v3/api-docs.yaml`.
2. Tìm parameter hoặc schema và kiểm tra `default`, `example`, `required`, `minimum`, `maximum`.
3. Mở Swagger UI, xem giá trị được hiển thị trong form thử request.
4. Bỏ giá trị khỏi form và gửi request để kiểm tra server có áp dụng default runtime hay không.
5. Gửi một giá trị khác default để xác nhận client vẫn có thể chọn giá trị hợp lệ khác.
6. Gửi giá trị ngoài giới hạn để kiểm tra validation thực sự hoạt động.
7. Với JSON body, thử lần lượt thuộc tính bị thiếu, explicit null và có giá trị.
8. Kiểm tra response lỗi và status code khi validation thất bại.
9. So sánh default trong OpenAPI với property/profile thực tế của môi trường.
10. Kiểm tra client generator hoặc SDK nếu công cụ đó sinh giá trị mặc định từ schema.

Ví dụ ma trận kiểm tra `pageSize`:

| Request | Kết quả runtime mong đợi |
|---|---|
| Không có query `pageSize` | Dùng 20 nếu controller có `defaultValue = "20"` |
| `?pageSize=50` | Dùng 50 |
| `?pageSize=0` | Bị validation từ chối nếu `@Min(1)` được kích hoạt |
| `?pageSize=101` | Bị validation từ chối nếu `@Max(100)` được kích hoạt |
| `?pageSize=abc` | Lỗi chuyển kiểu binding, thường là `400 Bad Request` |

Đối với body DTO có initializer, kiểm tra riêng trường hợp thiếu và null vì hai request có thể tạo ra trạng thái Java khác nhau.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Swagger UI hiển thị default nhưng API nhận null | Chỉ khai báo `@Schema(defaultValue)` hoặc `schema.default` | Thêm default runtime ở Spring MVC, DTO hoặc service |
| API dùng default nhưng tài liệu không hiển thị | Springdoc không suy ra metadata từ cấu hình đang dùng | Bổ sung `@Schema(defaultValue)` hoặc `@Parameter` và kiểm tra output |
| Người dùng đổi được giá trị trong Swagger UI | Default chỉ là giá trị gợi ý, không phải giới hạn | Dùng validation nếu cần giới hạn giá trị |
| Parameter thiếu vẫn gây lỗi | Không có runtime default hoặc parameter được đánh dấu required | Cấu hình `@RequestParam(defaultValue = ...)` hoặc quy tắc phù hợp |
| `default` làm người đọc nghĩ field bắt buộc | Nhầm lẫn giữa default và required | Mô tả riêng sự hiện diện bằng `required` |
| Body thiếu field không nhận default | Chỉ khai báo default trong OpenAPI schema | Khởi tạo DTO hoặc xử lý fallback trong ứng dụng |
| Body explicit null ghi đè initializer | Jackson gán null cho wrapper field | Quy định null bằng `@JsonSetter`, validation hoặc kiểu dữ liệu phù hợp |
| Giá trị mặc định vượt giới hạn | Default không được kiểm tra cùng validation hoặc cấu hình lệch | Bảo đảm default nằm trong miền hợp lệ và kiểm thử |
| Default trong docs khác production | Hard-code metadata nhưng runtime dùng property khác | Dùng chung nguồn cấu hình hoặc sinh metadata từ cấu hình |
| Dùng example như giá trị mặc định | Nhầm ý nghĩa `example` và `default` | Khai báo đúng metadata cho từng mục đích |

## 16. Nguyên tắc thiết kế

- Dùng `default` để mô tả giá trị mặc định của hợp đồng; không xem nó là lệnh thực thi trên server.
- Dùng `example` hoặc `examples` để hướng dẫn cách gọi và minh họa kịch bản.
- Dùng `required` để mô tả việc tham số/thuộc tính có phải xuất hiện hay không.
- Dùng `enum`, `minimum`, `maximum`, Bean Validation hoặc logic nghiệp vụ để giới hạn giá trị.
- Dùng `@RequestParam(defaultValue = ...)` hoặc `@RequestHeader(defaultValue = ...)` khi muốn Spring MVC áp dụng default lúc binding.
- Dùng field initializer, constructor hoặc service fallback cho default của request body theo semantics đã chọn.
- Phân biệt thuộc tính thiếu với explicit null, đặc biệt trong DTO cập nhật một phần.
- Đồng bộ giá trị default trong OpenAPI với runtime và cấu hình môi trường.
- Không dùng default giả cho header bảo mật hoặc dữ liệu nhạy cảm.
- Kiểm tra cả tài liệu JSON/YAML, Swagger UI và request gửi trực tiếp ngoài Swagger UI.

## Kết luận

Giá trị `default` trong OpenAPI và giá trị hiển thị trên Swagger UI chủ yếu mô tả hoặc gợi ý cho người tiêu dùng API. Chúng không tự thay đổi request, không giới hạn lựa chọn của client và không khiến Spring Boot tự gán giá trị khi dữ liệu bị thiếu. Muốn có hành vi mặc định thật sự, hãy triển khai ở Spring MVC binding, DTO/Jackson hoặc tầng service; muốn giới hạn giá trị, hãy dùng validation và quy tắc runtime. Springdoc-openapi giúp công bố `default`, `example`, `required` và các giới hạn trong hợp đồng. Hãy giữ các metadata đó đồng bộ với hành vi thực tế và kiểm tra riêng trường hợp thiếu, null, giá trị hợp lệ và giá trị không hợp lệ.
