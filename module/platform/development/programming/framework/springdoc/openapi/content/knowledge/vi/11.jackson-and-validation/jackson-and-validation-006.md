# `@NotNull`, `@NotBlank`, `@Size` và thông tin có thể suy ra

Bean Validation giúp ứng dụng kiểm tra dữ liệu đầu vào theo các ràng buộc được khai báo trên DTO. Springdoc có thể đọc nhiều constraint phổ biến để bổ sung thông tin vào schema OpenAPI, chẳng hạn thuộc tính bắt buộc, độ dài chuỗi hoặc số phần tử của collection. Vì vậy, cùng một nhóm annotation có thể vừa được dùng để kiểm tra request lúc chạy, vừa cung cấp metadata cho client qua tài liệu API.

Ba annotation `@NotNull`, `@NotBlank` và `@Size` có phạm vi và ý nghĩa khác nhau. Chọn đúng annotation giúp tránh trường hợp tài liệu mô tả một field bắt buộc nhưng ứng dụng vẫn chấp nhận dữ liệu rỗng, hoặc tài liệu thể hiện giới hạn mà server không thực thi.

## 1. Bean Validation trong ứng dụng Spring Boot

Bean Validation là cơ chế khai báo constraint trên field, property, tham số hoặc kiểu dữ liệu. Khi validation được kích hoạt, provider kiểm tra object và trả về các lỗi vi phạm constraint.

Với Spring Boot 3, các annotation chuẩn thuộc package `jakarta.validation`. Ứng dụng Spring Boot 2 thường sử dụng namespace cũ `javax.validation`. Không trộn hai namespace trong cùng một cấu hình nếu các dependency của dự án không hỗ trợ chúng.

Với Spring Boot 3, dependency thường dùng là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Spring Boot dependency management quản lý phiên bản phù hợp. Starter này đưa Bean Validation API và provider cần thiết vào ứng dụng. Nếu chỉ khai báo annotation nhưng không có provider validation hoặc không kích hoạt validation trên luồng xử lý, các constraint có thể không được thực thi lúc chạy.

Khi dùng Spring MVC, đánh dấu request DTO bằng `@Valid` để yêu cầu Spring kiểm tra object sau khi deserialize:

```java
@PostMapping("/api/users")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateUserRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

`@Valid` yêu cầu validation cho object và cho phép kiểm tra tiếp các object lồng nhau khi thuộc tính tương ứng được đánh dấu `@Valid`. Với validation group hoặc method validation, có thể cần `@Validated` và cấu hình phù hợp với phiên bản Spring đang dùng. `@Valid` không tự tạo constraint; các constraint phải được khai báo trên DTO hoặc tham số.

## 2. `@NotNull`: giá trị không được là null

`@NotNull` yêu cầu giá trị phải khác `null`. Annotation này có thể áp dụng cho nhiều kiểu tham chiếu như `String`, `Integer`, DTO, collection và các object khác.

```java
import jakarta.validation.constraints.NotNull;

public record UpdateProductRequest(
    @NotNull
    Integer quantity
) {}
```

Các giá trị được đánh giá như sau:

| Giá trị | Kết quả với `@NotNull` |
| --- | --- |
| `null` | Không hợp lệ |
| `0` | Hợp lệ |
| `10` | Hợp lệ |
| `""` với kiểu `String` | Hợp lệ |
| `"   "` với kiểu `String` | Hợp lệ |

`@NotNull` chỉ kiểm tra sự tồn tại của giá trị khác null. Với chuỗi, nó không đảm bảo chuỗi có nội dung. Với số, nó không đảm bảo số dương. Nếu nghiệp vụ yêu cầu số lượng lớn hơn 0, cần thêm constraint phù hợp như `@Positive` hoặc `@Min(1)`.

Trong schema OpenAPI, `@NotNull` thường giúp Springdoc thể hiện thuộc tính là bắt buộc hoặc không nullable theo phiên bản OpenAPI và cấu hình đang sử dụng. Cần phân biệt hai ý: property phải xuất hiện trong object và giá trị property không được là null. Hãy kiểm tra `required` và cách biểu diễn nullability trong tài liệu đầu ra.

## 3. `@NotBlank`: chuỗi phải có ký tự không phải khoảng trắng

`@NotBlank` dành cho `CharSequence`, chẳng hạn `String`. Giá trị phải khác null và sau khi xét các ký tự khoảng trắng phải còn ít nhất một ký tự nội dung.

```java
import jakarta.validation.constraints.NotBlank;

public record CreateUserRequest(
    @NotBlank
    String displayName
) {}
```

Ví dụ kết quả:

| Giá trị | Kết quả với `@NotBlank` |
| --- | --- |
| `null` | Không hợp lệ |
| `""` | Không hợp lệ |
| `"   "` | Không hợp lệ |
| `"Lan"` | Hợp lệ |
| `" Lan Nguyen "` | Hợp lệ |

`@NotBlank` khác `@NotNull` và `@NotEmpty`:

| Annotation | Không cho phép null | Không cho phép chuỗi rỗng | Không cho phép toàn khoảng trắng |
| --- | --- | --- | --- |
| `@NotNull` | Có | Không | Không |
| `@NotEmpty` | Có | Có | Không |
| `@NotBlank` | Có | Có | Có |

Với `@NotBlank`, Springdoc thường có thể suy ra field là bắt buộc và chuỗi có độ dài tối thiểu lớn hơn 0. Tuy nhiên, OpenAPI `minLength: 1` không diễn đạt đầy đủ quy tắc loại bỏ chuỗi chỉ chứa khoảng trắng. Nếu muốn tài liệu thể hiện rõ hơn, thêm mô tả cho field hoặc pattern phù hợp và xác minh schema được sinh ra.

Không dùng `@NotBlank` cho `Integer`, `Long`, `Boolean` hoặc collection; những kiểu này không phải `CharSequence` và không phù hợp với constraint.

## 4. `@Size`: giới hạn kích thước hoặc độ dài

`@Size` đặt giới hạn nhỏ nhất và lớn nhất cho giá trị. Annotation hỗ trợ `CharSequence`, collection, map và array. Cả `min` và `max` đều tính là giá trị hợp lệ ở biên.

```java
import jakarta.validation.constraints.Size;

public record ProfileRequest(
    @Size(min = 2, max = 80)
    String fullName
) {}
```

Với chuỗi, `@Size` kiểm tra độ dài. Với collection hoặc array, nó kiểm tra số phần tử; với map, nó kiểm tra số entry.

| Kiểu dữ liệu | `@Size` kiểm tra | Thông tin OpenAPI có thể suy ra |
| --- | --- | --- |
| `String` hoặc `CharSequence` | Độ dài chuỗi | `minLength`, `maxLength` |
| `List`, `Set`, collection | Số phần tử | `minItems`, `maxItems` |
| Array | Số phần tử | `minItems`, `maxItems` |
| `Map` | Số cặp key/value | `minProperties`, `maxProperties` |

Một điểm quan trọng: `@Size` cho phép `null`. Nếu field phải vừa có giá trị vừa nằm trong giới hạn kích thước, kết hợp `@NotNull` hoặc `@NotBlank` tùy kiểu dữ liệu.

Ví dụ:

```java
public record CreateProductRequest(
    @NotBlank
    @Size(min = 3, max = 80)
    String name,

    @NotNull
    @Size(min = 1, max = 10)
    List<String> labels
) {}
```

Ở đây `name` không được null, rỗng hoặc toàn khoảng trắng và phải nằm trong giới hạn kích thước. `labels` phải có mặt và chứa từ 1 đến 10 phần tử. Nếu chỉ dùng `@Size(min = 1, max = 10)` cho `labels`, giá trị null vẫn hợp lệ đối với constraint `@Size`.

`@Size` không giới hạn giá trị số. Ví dụ, không dùng `@Size(min = 1, max = 100)` cho `Integer quantity`; hãy dùng constraint số như `@Min`, `@Max` hoặc `@Positive`.

## 5. Kết hợp các constraint cho một field

Một field thường cần nhiều điều kiện cùng lúc. Các constraint trên cùng một field được áp dụng đồng thời; dữ liệu phải thỏa tất cả điều kiện.

Ví dụ DTO đăng ký tài khoản:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record RegisterUserRequest(
    @NotBlank
    @Size(min = 3, max = 40)
    String username,

    @NotBlank
    @Size(max = 120)
    String fullName,

    @NotNull
    Integer age
) {}
```

Ý nghĩa:

- `username` phải có nội dung và độ dài từ 3 đến 40.
- `fullName` phải có nội dung và không vượt quá 120 ký tự.
- `age` không được null; các giới hạn số tuổi cần constraint số riêng nếu nghiệp vụ yêu cầu.

Springdoc có thể kết hợp metadata để mô tả required và giới hạn. Schema rút gọn có thể trông như sau:

```yaml
RegisterUserRequest:
  type: object
  required:
    - username
    - fullName
    - age
  properties:
    username:
      type: string
      minLength: 3
      maxLength: 40
    fullName:
      type: string
      minLength: 1
      maxLength: 120
    age:
      type: integer
```

Đây là cấu trúc minh họa. Schema thực tế có thể khác về danh sách `required`, nullability, mô tả và cách suy luận tùy phiên bản Springdoc, swagger-core và Bean Validation. Đặc biệt, `minLength: 1` không thể biểu diễn đầy đủ điều kiện “không phải toàn khoảng trắng” của `@NotBlank`.

## 6. Constraint trên collection và phần tử bên trong

`@Size` trên collection kiểm tra số phần tử, không tự kiểm tra nội dung từng phần tử. Nếu mỗi phần tử cũng phải hợp lệ, dùng constraint trên phần tử và kích hoạt validation lồng nhau.

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;

public record CreateArticleRequest(
    @NotEmpty
    @Size(max = 5)
    List<@NotBlank String> tags,

    @Valid
    @NotNull
    AuthorRequest author
) {}

public record AuthorRequest(
    @NotBlank
    @Size(max = 80)
    String name
) {}
```

Trong ví dụ:

- `@NotEmpty` yêu cầu danh sách không null và có ít nhất một phần tử.
- `@Size(max = 5)` giới hạn danh sách tối đa năm phần tử.
- `@NotBlank` trên phần tử `String` yêu cầu từng tag có nội dung.
- `@Valid` trên `author` yêu cầu validation tiếp object lồng nhau.

Với Springdoc, các ràng buộc collection có thể được thể hiện bằng `minItems` và `maxItems`; constraint trên phần tử có thể được đưa vào schema `items`. Kiểm tra kết quả trong `/v3/api-docs` để xác nhận đúng cấu trúc.

## 7. Kích hoạt validation trên controller

Ví dụ controller hoàn chỉnh:

```java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    @PostMapping
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateProductRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Nếu request không thỏa constraint, Spring MVC thường trả về `400 Bad Request` do lỗi validation của request body. Cấu trúc JSON lỗi cụ thể phụ thuộc exception handler và cách ứng dụng chuẩn hóa lỗi. Springdoc không thể tự biết chính xác response body lỗi tùy chỉnh nếu nhóm chưa mô tả nó.

Có thể khai báo response lỗi bằng `@ApiResponse` và `@Content` với schema lỗi của ứng dụng. Hãy dùng cùng kiểu lỗi mà exception handler thực sự trả về; không ghi một payload ví dụ chung nếu runtime có cấu trúc khác.

## 8. Springdoc suy luận những thông tin nào?

Springdoc tích hợp với swagger-core và có thể đọc metadata từ Bean Validation. Các constraint phổ biến giúp bổ sung ràng buộc vào schema mà không cần lặp lại mọi giới hạn trong `@Schema`.

| Bean Validation | Thông tin schema OpenAPI có thể suy ra |
| --- | --- |
| `@NotNull` | Field/parameter bắt buộc hoặc không nullable theo ngữ cảnh |
| `@NotBlank` | Field bắt buộc; thường có độ dài tối thiểu 1 cho chuỗi |
| `@Size(min, max)` trên chuỗi | `minLength`, `maxLength` |
| `@Size(min, max)` trên collection/array | `minItems`, `maxItems` |
| `@Size(min, max)` trên map | `minProperties`, `maxProperties` |

Khả năng suy luận cụ thể phụ thuộc phiên bản Springdoc, swagger-core, OpenAPI version và namespace validation (`jakarta` hoặc `javax`). Annotation có thể được dùng ở field, getter, record component hoặc type-use; cách thư viện phát hiện metadata cũng có thể phụ thuộc vị trí annotation và cấu trúc DTO.

Springdoc mô tả constraint trong hợp đồng, nhưng không thay thế provider validation. Ngược lại, validation runtime có thể hoạt động dù schema chưa thể hiện hết mọi quy tắc. Vì vậy, cần kiểm tra cả response validation thực tế và đặc tả OpenAPI.

## 9. Khi nào cần bổ sung `@Schema` tường minh?

Nếu metadata suy ra chưa đủ rõ, có thể dùng `@Schema` để bổ sung mô tả, ví dụ, định dạng hoặc constraint mong muốn:

```java
public record CreateProductRequest(
    @NotBlank
    @Size(min = 3, max = 80)
    @Schema(
        description = "Tên sản phẩm, không được để trống và có từ 3 đến 80 ký tự",
        example = "Mechanical Keyboard"
    )
    String name
) {}
```

Ưu tiên Bean Validation làm nguồn constraint thực thi; `@Schema` bổ sung phần diễn giải cho người tiêu thụ API. Nếu lặp lại giới hạn trong cả hai nơi, chúng phải khớp nhau. Ví dụ, không khai báo `@Size(max = 80)` nhưng `@Schema(maxLength = 100)` vì tài liệu sẽ cho phép dữ liệu mà server từ chối.

Nếu muốn kiểm soát tính bắt buộc khi Springdoc không suy luận như mong muốn, có thể dùng `@Schema(requiredMode = Schema.RequiredMode.REQUIRED)` hoặc `NOT_REQUIRED` tùy trường hợp. Chỉ override khi đã xác minh hành vi thực tế; annotation OpenAPI không làm thay đổi Bean Validation.

Không dùng `@Schema` để thay thế `@NotBlank`, `@NotNull` hoặc `@Size` nếu ứng dụng cần thực thi các constraint đó lúc chạy.

## 10. Phân biệt required, nullable và giới hạn kích thước

Ba khái niệm thường bị nhầm lẫn:

- **Required:** property hoặc parameter có bắt buộc phải được cung cấp hay không.
- **Nullable:** giá trị có được phép là `null` hay không.
- **Size/length constraint:** giá trị có nằm trong giới hạn độ dài hoặc số phần tử hay không.

Ví dụ một chuỗi có thể không bắt buộc nhưng nếu được gửi thì phải có từ 3 đến 40 ký tự. Khi đó, property không nằm trong danh sách `required`, nhưng schema vẫn có `minLength` và `maxLength`. Với `@Size`, giá trị null được chấp nhận; để cấm null cần kết hợp constraint phù hợp.

`@NotBlank` vừa cấm null vừa cấm chuỗi rỗng/toàn khoảng trắng. `@NotNull` cấm null nhưng không cấm chuỗi rỗng. `@Size` giới hạn kích thước nhưng không cấm null. Hiểu rõ sự khác biệt này giúp schema phản ánh đúng các trường hợp client được phép bỏ qua, gửi null hoặc gửi chuỗi rỗng.

## 11. Kiểm tra schema được Springdoc sinh ra

Sau khi chạy ứng dụng, mở `/v3/api-docs` hoặc `/v3/api-docs.yaml` và tìm schema DTO. Kiểm tra:

1. Các field có `@NotNull` hoặc `@NotBlank` được đánh dấu bắt buộc theo mong đợi.
2. `@Size` trên chuỗi tạo giới hạn độ dài phù hợp.
3. `@Size` trên collection/array tạo giới hạn số phần tử.
4. Constraint trên phần tử collection xuất hiện trong schema `items` nếu được hỗ trợ.
5. Mô tả và example từ `@Schema` không mâu thuẫn với constraint.
6. Request body tham chiếu đúng schema DTO.

Schema minh họa:

```yaml
CreateProductRequest:
  type: object
  required:
    - name
    - labels
  properties:
    name:
      type: string
      minLength: 3
      maxLength: 80
      description: Tên sản phẩm
    labels:
      type: array
      minItems: 1
      maxItems: 10
      items:
        type: string
```

Kết quả thực tế có thể chứa thêm `items` constraint, format, example, `$ref` hoặc cách thể hiện nullability khác. Swagger UI có thể hiển thị các giới hạn trong phần schema; tài liệu JSON/YAML là căn cứ chính để xác minh metadata.

## 12. Kiểm tra validation lúc chạy

Không chỉ kiểm tra schema, hãy gửi các payload hợp lệ và không hợp lệ để xác nhận Bean Validation đang được kích hoạt.

Ví dụ payload hợp lệ:

```json
{
  "name": "Mechanical Keyboard",
  "labels": ["keyboard", "accessory"]
}
```

Ví dụ tên rỗng:

```json
{
  "name": "   ",
  "labels": ["keyboard"]
}
```

Ví dụ tên quá dài hoặc danh sách có quá nhiều phần tử cũng cần bị từ chối nếu vượt constraint đã khai báo. Khi request không hợp lệ, xác minh status code và body lỗi theo exception handler của ứng dụng.

Nếu schema có giới hạn nhưng request không hợp lệ vẫn được chấp nhận, kiểm tra dependency `spring-boot-starter-validation`, `@Valid` trên tham số controller và vị trí các annotation. Nếu runtime từ chối đúng nhưng schema thiếu constraint, kiểm tra namespace annotation, vị trí đặt constraint và phiên bản Springdoc/swagger-core.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@NotBlank` không biên dịch với field số | Constraint chỉ áp dụng cho `CharSequence` | Dùng constraint phù hợp với kiểu số |
| Field null vẫn được chấp nhận dù có `@Size` | `@Size` cho phép null | Kết hợp `@NotNull` hoặc `@NotBlank` |
| Chuỗi toàn khoảng trắng vẫn qua validation | Chỉ dùng `@NotNull` hoặc `@Size` | Dùng `@NotBlank` |
| Constraint không chạy lúc gọi API | Thiếu validation provider hoặc `@Valid` | Thêm starter validation và kích hoạt validation |
| Schema không có `minLength`/`maxLength` | Constraint đặt sai vị trí, namespace không tương thích hoặc phiên bản thư viện | Kiểm tra import, DTO và OpenAPI đầu ra |
| Tài liệu ghi field bắt buộc nhưng server chấp nhận null | Metadata required/nullability và runtime không đồng bộ | Kiểm tra constraint và `@Schema` override |
| Schema giới hạn khác runtime | `@Schema` và Bean Validation khai báo hai giá trị khác nhau | Dùng Bean Validation làm nguồn constraint thực thi và đồng bộ metadata |
| Validation lồng nhau không hoạt động | Thiếu `@Valid` trên thuộc tính object lồng nhau | Đánh dấu thuộc tính bằng `@Valid` |
| Collection đúng số phần tử nhưng có phần tử rỗng | Chỉ có `@Size` trên collection | Thêm constraint cho phần tử như `List<@NotBlank String>` |

## 14. Checklist cho constraint và schema suy luận

- [ ] Dùng đúng namespace `jakarta.validation` cho Spring Boot 3 hoặc `javax.validation` cho thế hệ cũ tương ứng.
- [ ] Có validation provider trong runtime khi cần thực thi constraint.
- [ ] Dùng `@NotNull` khi chỉ cần cấm null.
- [ ] Dùng `@NotBlank` cho chuỗi bắt buộc có nội dung.
- [ ] Dùng `@Size` cho giới hạn độ dài chuỗi, số phần tử collection/array hoặc số entry map.
- [ ] Kết hợp constraint khi vừa cần bắt buộc vừa cần giới hạn kích thước.
- [ ] Dùng `@Valid` để kích hoạt validation cho request DTO và object lồng nhau.
- [ ] Bổ sung `@Schema` cho mô tả/example; không để metadata mâu thuẫn với constraint runtime.
- [ ] Kiểm tra required, nullability, minLength/maxLength và minItems/maxItems trong `/v3/api-docs`.
- [ ] Thử payload hợp lệ và không hợp lệ để xác nhận runtime thực thi cùng hợp đồng.

`@NotNull`, `@NotBlank` và `@Size` mô tả những khía cạnh khác nhau của dữ liệu. Spring Boot dùng Bean Validation để thực thi các quy tắc khi request được kiểm tra; Springdoc có thể suy luận nhiều ràng buộc thành metadata OpenAPI. Khi constraint, DTO, `@Valid` và schema được giữ nhất quán, tài liệu giúp client biết field nào cần gửi và giới hạn dữ liệu trước khi gọi API.
