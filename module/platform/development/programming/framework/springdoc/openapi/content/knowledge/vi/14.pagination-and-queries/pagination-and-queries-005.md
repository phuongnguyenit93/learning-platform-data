# Nhiều tiêu chí sắp xếp và tham số `sort` lặp lại

Một API danh sách thường cần sắp xếp theo nhiều tiêu chí cùng lúc. Ví dụ, danh sách sách có thể được sắp xếp theo ngày tạo giảm dần, sau đó theo tiêu đề tăng dần để các bản ghi cùng ngày có thứ tự ổn định. Spring Data hỗ trợ cách truyền nhiều giá trị `sort` trong query string; Springdoc có thể mô tả `sort` như một mảng query parameter trong OpenAPI để người tích hợp biết cần lặp lại tên tham số.

Request điển hình:

```http
GET /api/books?page=0&size=20&sort=createdAt,desc&sort=title,asc HTTP/1.1
Accept: application/json
```

Mỗi lần xuất hiện của `sort` biểu diễn một tiêu chí. Thứ tự các tiêu chí có ý nghĩa: server ưu tiên `createdAt DESC`, sau đó dùng `title ASC` để sắp xếp các bản ghi có cùng thời điểm tạo.

## 1. Cú pháp nhiều tiêu chí của Spring Data

Spring Data Web hỗ trợ query parameter `sort` khi bind request thành `Sort` hoặc `Pageable`. Mỗi giá trị thường có dạng:

```text
property,direction
```

Trong đó:

- `property` là thuộc tính có thể sắp xếp của entity hoặc thuộc tính mà repository hỗ trợ.
- `direction` là `asc` hoặc `desc`.
- Nếu không truyền direction, Spring Data mặc định dùng `ASC`.

Ví dụ:

| Query string | Ý nghĩa |
| --- | --- |
| `?sort=title` | Sắp xếp theo `title ASC` |
| `?sort=createdAt,desc` | Sắp xếp theo `createdAt DESC` |
| `?sort=createdAt,desc&sort=title,asc` | Ưu tiên `createdAt DESC`, sau đó `title ASC` |
| `?sort=category,asc&sort=price,desc&sort=id,asc` | Sắp xếp theo ba tiêu chí theo đúng thứ tự truyền |

Với nhiều tiêu chí có hướng khác nhau, cách rõ ràng nhất là lặp lại tham số `sort`, mỗi giá trị dành cho một thuộc tính. Tránh gộp nhiều cặp thuộc tính/hướng vào một chuỗi tùy ý vì cách phân tích dấu phẩy có thể gây nhầm lẫn.

## 2. Vì sao cần lặp lại cùng tên query parameter?

Một URL có thể chứa nhiều cặp key/value trùng tên:

```text
/api/books?sort=createdAt,desc&sort=title,asc
```

Đây là cách mã hóa phổ biến của một query parameter dạng mảng. Trong OpenAPI 3, query parameter có thể được khai báo là array với `style: form` và `explode: true`:

```yaml
name: sort
in: query
required: false
style: form
explode: true
schema:
  type: array
  items:
    type: string
  example:
    - createdAt,desc
    - title,asc
```

`style: form` xác định cách tuần tự hóa parameter query; `explode: true` yêu cầu mỗi phần tử được biểu diễn bằng một cặp query parameter riêng. Vì vậy, hai phần tử tạo thành `sort=createdAt,desc&sort=title,asc`.

Nếu dùng `explode: false`, các phần tử mảng thường được nối trong một parameter bằng dấu phẩy. Cách đó tạo ra biểu diễn khác và có thể không tương ứng với cú pháp `sort` lặp lại mà Spring Data resolver đang nhận. Với Spring Data `Pageable`, hãy dùng dạng lặp `sort` và xác minh đặc tả OpenAPI thể hiện `style: form`, `explode: true`.

## 3. Nhận nhiều tiêu chí bằng `Pageable`

Trong ứng dụng Spring MVC dùng Spring Data, cách thuận tiện là nhận `Pageable`. Spring Data Web tự đọc các tham số phân trang và sắp xếp:

- `page`: chỉ số trang, mặc định bắt đầu từ `0`.
- `size`: số bản ghi trên một trang.
- `sort`: một hoặc nhiều tiêu chí sắp xếp.

Ví dụ controller:

```java
package com.example.books;

import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.SortDefault;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping
    public Page<BookResponse> list(
            @ParameterObject
            @PageableDefault(size = 20)
            @SortDefault.SortDefaults({
                @SortDefault(sort = "createdAt", direction = Sort.Direction.DESC),
                @SortDefault(sort = "id", direction = Sort.Direction.ASC)
            })
            Pageable pageable) {

        return bookService.findAll(pageable);
    }
}
```

`@ParameterObject` của Springdoc làm phẳng `Pageable` thành các query parameter để đưa vào tài liệu OpenAPI. Trong ví dụ, `@PageableDefault(size = 20)` đặt kích thước trang mặc định; `@SortDefault.SortDefaults` cung cấp hai tiêu chí mặc định theo thứ tự khai báo khi client không gửi sort riêng.

Ví dụ dùng Spring Boot 3 và Springdoc 2.x. Với Springdoc 1.x, package của một số annotation Springdoc có thể khác. Hãy dùng import phù hợp với dòng thư viện của dự án.

## 4. Gửi sort lặp lại khi gọi API

Gọi endpoint bằng curl:

```bash
curl -G "http://localhost:8080/api/books" \
  --data-urlencode "page=0" \
  --data-urlencode "size=20" \
  --data-urlencode "sort=createdAt,desc" \
  --data-urlencode "sort=title,asc"
```

`curl -G` đưa các giá trị `--data-urlencode` vào query string. Hai tùy chọn `sort` tạo ra hai cặp key/value cùng tên. Có thể kiểm tra URL tương đương:

```text
http://localhost:8080/api/books?page=0&size=20&sort=createdAt%2Cdesc&sort=title%2Casc
```

Dấu phẩy được URL encode thành `%2C` trong ví dụ trên. Server giải mã query parameter trước khi Spring Data phân tích giá trị.

## 5. Mô tả `sort` trong OpenAPI bằng array và explode

Springdoc hỗ trợ `Pageable` thông qua `@ParameterObject` và tạo các tham số `page`, `size`, `sort`. Sau khi sinh tài liệu, hãy kiểm tra `/v3/api-docs` để chắc chắn `sort` được thể hiện đúng là một mảng chuỗi và có serialization phù hợp.

Nếu cần khai báo tường minh cách lặp parameter trong hợp đồng, có thể mô tả `sort` bằng `@Parameter`:

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.Explode;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.enums.ParameterStyle;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.Operation;

@Operation(
    summary = "Liệt kê sách",
    parameters = @Parameter(
        name = "sort",
        in = ParameterIn.QUERY,
        description = "Có thể lặp lại để chỉ định nhiều tiêu chí theo thứ tự ưu tiên",
        style = ParameterStyle.FORM,
        explode = Explode.TRUE,
        array = @ArraySchema(
            schema = @Schema(
                type = "string",
                example = "createdAt,desc"
            )
        )
    )
)
```

Đặt metadata này trên operation có nhận `Pageable`. Nếu Springdoc đã tự sinh `sort`, hãy kiểm tra kết quả để tránh tạo hai parameter cùng tên và cùng vị trí. Trong trường hợp cần chỉnh sửa parameter đã được sinh, có thể dùng `OpenApiCustomizer` để cập nhật parameter hiện có thay vì thêm một bản sao.

Đoạn annotation trên chỉ mô tả cách tuần tự hóa trong OpenAPI. Nó không tự thay đổi cách Spring Data parse request; controller vẫn phải nhận `Pageable` hoặc một cấu trúc dữ liệu phù hợp.

## 6. Cấu trúc OpenAPI mong đợi

Parameter `sort` trong đặc tả có thể có dạng:

```yaml
parameters:
  - name: sort
    in: query
    description: Có thể lặp lại để chỉ định nhiều tiêu chí theo thứ tự ưu tiên
    required: false
    style: form
    explode: true
    schema:
      type: array
      items:
        type: string
      example:
        - createdAt,desc
        - title,asc
```

Swagger UI có thể trình bày parameter dạng array dưới dạng nhiều ô nhập hoặc một trường cho phép thêm phần tử, tùy phiên bản giao diện. Quan trọng là client generator và công cụ HTTP phải tuần tự hóa array thành các key `sort` lặp lại.

Khi kiểm tra `/v3/api-docs`, xác nhận:

1. `name` là `sort` và `in` là `query`.
2. `schema.type` là `array` và `items.type` là `string`.
3. `style` là `form`.
4. `explode` là `true`.
5. Ví dụ có nhiều phần tử, mỗi phần tử dùng cú pháp `property,direction`.

Nếu tài liệu thể hiện `sort` thành một chuỗi đơn, người tích hợp có thể hiểu nhầm cách truyền nhiều tiêu chí. Khi đó cần điều chỉnh metadata Springdoc và kiểm tra lại URL được tạo bởi Swagger UI hoặc client generator.

## 7. Sắp xếp mặc định nhiều tiêu chí

Có thể đặt thứ tự mặc định bằng `@SortDefault.SortDefaults`:

```java
@GetMapping
public Page<BookResponse> list(
        @ParameterObject
        @PageableDefault(size = 20)
        @SortDefault.SortDefaults({
            @SortDefault(sort = "createdAt", direction = Sort.Direction.DESC),
            @SortDefault(sort = "title", direction = Sort.Direction.ASC),
            @SortDefault(sort = "id", direction = Sort.Direction.ASC)
        })
        Pageable pageable) {
    return bookService.findAll(pageable);
}
```

Khi client không gửi `sort`, resolver dùng các tiêu chí mặc định theo cấu hình. Khi client gửi tiêu chí riêng, Spring Data sử dụng sort được truyền trong request theo hành vi của resolver. Hãy kiểm tra trường hợp không gửi sort và trường hợp có sort để xác nhận đúng quy tắc mà ứng dụng mong muốn.

`@PageableDefault(sort = ..., direction = ...)` cũng có thể dùng cho một hoặc nhiều thuộc tính có cùng hướng sắp xếp. Khi mỗi tiêu chí cần hướng khác nhau, `@SortDefault.SortDefaults` diễn đạt rõ hơn.

Không nhầm default sort với ví dụ OpenAPI. `@SortDefault` tác động đến cách Spring Data tạo `Pageable` khi request không có sort; ví dụ trong `@Parameter` chỉ minh họa request mà client có thể gửi.

## 8. Thứ tự ưu tiên và tính ổn định của phân trang

Sort nhiều tiêu chí được áp dụng theo thứ tự:

```sql
ORDER BY created_at DESC, title ASC, id ASC
```

Tiêu chí đầu tiên quyết định thứ tự chính. Nếu nhiều bản ghi có cùng giá trị ở tiêu chí đó, tiêu chí kế tiếp được dùng để phân định. Vì vậy, nên có một tiêu chí phụ đủ ổn định, thường là khóa duy nhất như `id`, để kết quả phân trang dễ dự đoán.

Nếu chỉ sắp xếp theo `createdAt` và nhiều bản ghi có cùng timestamp, thứ tự giữa chúng có thể không ổn định. Khi client chuyển từ trang này sang trang khác, các bản ghi có thể xuất hiện lặp hoặc bị bỏ qua nếu dữ liệu thay đổi giữa các request. Thêm khóa duy nhất làm tiêu chí cuối giúp tạo thứ tự toàn phần ổn định hơn.

Sắp xếp ổn định không ngăn mọi thay đổi do dữ liệu mới được thêm hoặc cập nhật giữa hai request. Với hệ thống cần duyệt tập dữ liệu thay đổi liên tục, cân nhắc cursor/keyset pagination thay vì chỉ dựa trên offset pagination.

## 9. Giới hạn các thuộc tính được phép sắp xếp

Không nên cho client truyền tùy ý tên thuộc tính nội bộ của entity. Một số thuộc tính không có ý nghĩa với người tiêu thụ API, không được lập chỉ mục hoặc không phù hợp để sort. Với repository JPA, thuộc tính không tồn tại có thể gây lỗi khi tạo truy vấn.

Hãy công bố danh sách trường được phép sắp xếp, ví dụ:

| Tên sort công khai | Thuộc tính dữ liệu được dùng | Hướng cho phép |
| --- | --- | --- |
| `title` | `Book.title` | `asc`, `desc` |
| `createdAt` | `Book.createdAt` | `asc`, `desc` |
| `price` | `Book.price` | `asc`, `desc` |

Nếu tên công khai khác tên property entity, ánh xạ từ danh sách cho phép sang thuộc tính nội bộ trước khi gọi repository. Không nối trực tiếp chuỗi sort từ client vào câu SQL hoặc JPQL. Tránh dùng `JpaSort.unsafe` với dữ liệu đầu vào chưa được kiểm soát.

Với `Pageable`, có thể kiểm tra `pageable.getSort()` trước khi chuyển xuống service/repository:

```java
private static final Set<String> ALLOWED_SORTS = Set.of(
    "title", "createdAt", "price", "id"
);

private void validateSort(Pageable pageable) {
    pageable.getSort().forEach(order -> {
        if (!ALLOWED_SORTS.contains(order.getProperty())) {
            throw new IllegalArgumentException(
                "Không hỗ trợ sắp xếp theo: " + order.getProperty()
            );
        }
    });
}
```

Trong ứng dụng thực tế, chuyển lỗi này thành response `400 Bad Request` với mã lỗi và thông báo nhất quán. Tài liệu OpenAPI nên mô tả các thuộc tính được hỗ trợ trong description hoặc dùng enum nếu danh sách đủ ổn định và phù hợp với cách biểu diễn parameter.

## 10. Giới hạn page size và kiểm soát truy vấn

Sort nhiều tiêu chí thường đi cùng phân trang. Ngoài việc kiểm soát các trường sort, API cần giới hạn kích thước trang để tránh client yêu cầu quá nhiều bản ghi trong một lần gọi.

Ví dụ cấu hình mặc định:

```java
@PageableDefault(size = 20)
Pageable pageable
```

Đây là kích thước mặc định, không nhất thiết là giới hạn tối đa. Hãy cấu hình giới hạn page size ở resolver hoặc kiểm tra `pageable.getPageSize()` trong tầng phù hợp. Khi giới hạn bị vượt, API có thể từ chối request hoặc chuẩn hóa về mức tối đa theo chính sách đã công bố.

Mô tả rõ trong OpenAPI:

- `page` bắt đầu từ `0` hay `1`.
- `size` mặc định và giới hạn tối đa.
- `sort` có thể lặp lại hay không.
- Các trường sort được hỗ trợ.
- Hướng mặc định khi client chỉ truyền tên thuộc tính.
- Tiêu chí mặc định khi client không truyền sort.

Đảm bảo tài liệu phản ánh cách resolver được cấu hình trong ứng dụng, vì các tên parameter, giá trị mặc định và giới hạn có thể được tùy chỉnh.

## 11. Kiểm thử nhiều tiêu chí sắp xếp

Nên kiểm tra cả cách Spring bind query string và thứ tự dữ liệu trả về.

Ví dụ request:

```bash
curl -G "http://localhost:8080/api/books" \
  --data-urlencode "sort=createdAt,desc" \
  --data-urlencode "sort=title,asc"
```

Kiểm tra các trường hợp:

1. Không có `sort`: server áp dụng thứ tự mặc định.
2. Một `sort`: server áp dụng một tiêu chí.
3. Nhiều `sort`: server giữ đúng thứ tự ưu tiên và hướng của từng tiêu chí.
4. Chỉ có tên property: server dùng hướng mặc định `ASC` theo resolver.
5. Direction không hợp lệ: API trả lỗi có thể hiểu được.
6. Property không được hỗ trợ: API từ chối hoặc xử lý theo chính sách đã công bố.
7. Nhiều bản ghi có cùng giá trị tiêu chí đầu: tiêu chí phụ tạo thứ tự ổn định.

Trong test Spring MVC, có thể dùng MockMvc để gửi cùng tên parameter nhiều lần:

```java
mockMvc.perform(get("/api/books")
        .param("sort", "createdAt,desc")
        .param("sort", "title,asc"))
    .andExpect(status().isOk());
```

Test trên xác nhận request có hai giá trị `sort` được gửi đến endpoint. Nên bổ sung kiểm tra kết quả hoặc verify `Pageable` được truyền đến service với thứ tự `createdAt DESC`, `title ASC`.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Chỉ có tiêu chí sort cuối cùng được áp dụng | Client hoặc proxy ghi đè query parameter trùng tên | Gửi nhiều key `sort` và kiểm tra `getSort()` |
| Tất cả tiêu chí có cùng direction ngoài ý muốn | Gộp nhiều property vào một chuỗi hoặc dùng default direction chung | Lặp một giá trị `property,direction` cho từng tiêu chí |
| Swagger UI chỉ gửi một giá trị sort | OpenAPI mô tả `sort` là string hoặc `explode` không đúng | Mô tả array với `style: form`, `explode: true` |
| OpenAPI có hai parameter `sort` | Thêm parameter tường minh trong khi Springdoc đã sinh từ Pageable | Cập nhật parameter hiện có bằng customizer, tránh duplicate |
| Sort không chạy với property mong muốn | Tên public không phải property hợp lệ của entity/repository | Ánh xạ allowlist sang thuộc tính dữ liệu |
| Request sort sai direction trả lỗi khó hiểu | Giá trị direction không được kiểm tra hoặc exception chưa được xử lý | Validate `asc`/`desc` và trả lỗi 400 nhất quán |
| Kết quả trang bị lặp hoặc thiếu bản ghi | Sort không có tiêu chí phụ duy nhất hoặc dữ liệu thay đổi giữa các lần gọi | Thêm khóa duy nhất làm tie-breaker; cân nhắc keyset pagination |
| Default sort không xuất hiện | `@SortDefault` đặt sai vị trí hoặc request đã gửi sort riêng | Kiểm tra `Pageable` được bind và cấu hình resolver |

## 13. Checklist mô tả sort lặp lại

- [ ] API nhận `Pageable` hoặc cấu trúc sort có thể xử lý nhiều giá trị.
- [ ] Mỗi tiêu chí dùng cú pháp `property,direction`.
- [ ] Query string lặp lại cùng tên `sort` cho từng tiêu chí.
- [ ] OpenAPI mô tả `sort` là array string khi hỗ trợ lặp.
- [ ] `style: form` và `explode: true` phản ánh đúng cách tuần tự hóa.
- [ ] `@ParameterObject` được dùng để Springdoc nhận diện `Pageable`.
- [ ] Default page size và sort được mô tả rõ.
- [ ] Các thuộc tính sort được allowlist và ánh xạ an toàn.
- [ ] Có tiêu chí phụ duy nhất để ổn định thứ tự khi phân trang.
- [ ] Đã kiểm tra `/v3/api-docs`, Swagger UI và request lặp bằng curl/test.
- [ ] Direction và property không hợp lệ được xử lý thành lỗi API nhất quán.

Spring Data cho phép truyền nhiều tiêu chí bằng cách lặp query parameter `sort`. Springdoc cần mô tả đúng đây là một mảng query parameter được serialize theo `form` với `explode: true`. Khi hợp đồng, resolver và repository cùng thống nhất về tên property, hướng sắp xếp và thứ tự ưu tiên, client có thể kết hợp nhiều tiêu chí mà vẫn nhận kết quả phân trang dễ dự đoán.
