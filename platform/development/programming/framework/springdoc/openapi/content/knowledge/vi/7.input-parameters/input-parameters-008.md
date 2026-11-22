# Danh sách giá trị, tham số lặp lại và cách truyền mảng

Một API thường cần nhận nhiều giá trị cho cùng một tham số: danh sách mã sản phẩm, nhiều trạng thái đơn hàng, các nhãn tìm kiếm hoặc nhiều ID cần truy vấn. Trong Spring MVC, các giá trị này thường được bind vào `List<T>`, mảng Java hoặc `MultiValueMap`. Trong OpenAPI, chúng được mô tả bằng schema có `type: array` và quy tắc tuần tự hóa xác định cách client gửi danh sách qua URL, header hoặc cookie.

Điểm quan trọng là kiểu dữ liệu Java và cách truyền dữ liệu trên HTTP là hai việc khác nhau. `List<String>` cho biết server muốn nhận một tập hợp chuỗi; `style` và `explode` trong OpenAPI cho biết client phải mã hóa tập hợp đó thành request như thế nào. Nếu tài liệu và cách bind của ứng dụng không thống nhất, Swagger UI, SDK sinh tự động và client viết thủ công có thể gửi những request khác nhau.

## 1. Phân biệt tham số đơn, nhiều tham số và mảng

Giả sử endpoint tìm kiếm sản phẩm cần nhận nhiều nhãn (`tag`). Có một số cách truyền thường gặp:

| Request | Ý nghĩa |
| --- | --- |
| `?tag=java` | Một giá trị `tag` |
| `?tag=java&tag=spring` | Hai giá trị của cùng tên tham số `tag` |
| `?tag=java,spring` | Một giá trị chứa danh sách phân tách bằng dấu phẩy |
| `?tag=java%20spring` | Một giá trị chứa danh sách phân tách bằng khoảng trắng |
| `?tag=java%7Cspring` | Một giá trị chứa danh sách phân tách bằng dấu gạch đứng `\|` |

Các request trên không tự động có cùng ý nghĩa. Server phải biết delimiter nào được chấp nhận và OpenAPI phải mô tả cùng quy tắc đó. Nếu không có yêu cầu đặc biệt, dạng lặp lại `?tag=java&tag=spring` thường dễ đọc, dễ mở rộng và tương ứng với mặc định của OpenAPI cho query array.

Một mảng trong schema OpenAPI được mô tả bằng `type: array` và `items`:

```yaml
schema:
  type: array
  items:
    type: string
```

`items` mô tả kiểu của từng phần tử. Ví dụ, `type: array` với `items.type: integer` là danh sách số nguyên; `items.$ref` có thể tham chiếu schema dùng chung cho từng phần tử.

## 2. Bind query array bằng Spring MVC

Spring MVC có thể bind nhiều giá trị cùng tên query parameter vào `List<T>` hoặc mảng Java bằng `@RequestParam`.

```java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping
    public List<ProductResponse> search(
            @RequestParam(name = "tag", required = false) List<String> tags) {
        return productService.searchByTags(tags);
    }
}
```

Client có thể gọi:

```text
GET /api/products?tag=java&tag=spring
```

Spring bind thành một danh sách tương đương `List.of("java", "spring")`. Nếu dùng mảng, có thể khai báo `String[] tags` thay cho `List<String> tags`:

```java
@GetMapping("/by-ids")
public List<ProductResponse> findByIds(
        @RequestParam(name = "id") Long[] ids) {
    return productService.findByIds(Arrays.asList(ids));
}
```

Request tương ứng:

```text
GET /api/products/by-ids?id=10&id=20&id=30
```

Nên đặt rõ `name` trong `@RequestParam` để tên tham số HTTP không phụ thuộc vào cách compiler lưu tên tham số Java. `required = false` cho phép bỏ qua tham số; khi đó ứng dụng cần xác định rõ xử lý giá trị `null` hoặc danh sách rỗng như thế nào. Cần phân biệt trường hợp không truyền `tag`, truyền `tag` với giá trị rỗng (`?tag=`), và truyền nhiều giá trị (`?tag=java&tag=spring`).

Nếu cần nhận toàn bộ query parameter mà chưa biết trước tên, Spring hỗ trợ `MultiValueMap<String, String>`:

```java
@GetMapping("/search/raw")
public SearchResponse searchRaw(
        @RequestParam MultiValueMap<String, String> parameters) {
    List<String> tags = parameters.get("tag");
    return productService.search(tags);
}
```

`MultiValueMap` giữ được nhiều giá trị cho cùng một key, phù hợp với endpoint tìm kiếm tổng quát hoặc bộ lọc động. Với API công khai có hợp đồng ổn định, các tham số khai báo rõ bằng `@RequestParam` thường dễ hiểu và dễ sinh tài liệu hơn.

## 3. Mặc định của OpenAPI: form và explode

OpenAPI dùng hai thuộc tính để mô tả cách tuần tự hóa parameter:

- `style`: kiểu biểu diễn và delimiter của giá trị.
- `explode`: khi bật, mỗi phần tử của array hoặc mỗi cặp key/value của object được tách thành tham số riêng theo quy tắc của `style`.

Đối với query parameter, mặc định là `style: form` và `explode: true`. Vì vậy, một mảng `tag = ["java", "spring"]` được biểu diễn thành các tham số lặp lại:

```yaml
parameters:
  - name: tag
    in: query
    required: false
    description: Danh sách nhãn cần lọc
    style: form
    explode: true
    schema:
      type: array
      items:
        type: string
```

Request mẫu:

```text
GET /api/products?tag=java&tag=spring
```

Vì đây là mặc định của OpenAPI cho query parameter, có thể lược bỏ `style` và `explode` trong tài liệu. Tuy nhiên, khai báo tường minh giúp người đọc dễ nhận ra cách truyền khi API có nhiều kiểu tham số.

## 4. Truyền mảng bằng một tham số phân tách dấu phẩy

Nếu muốn gửi toàn bộ danh sách trong một query parameter, đặt `style: form` và `explode: false`:

```yaml
parameters:
  - name: tag
    in: query
    required: false
    description: Danh sách nhãn, phân tách bằng dấu phẩy
    style: form
    explode: false
    schema:
      type: array
      items:
        type: string
```

Với `tag = ["java", "spring"]`, request được tuần tự hóa thành:

```text
GET /api/products?tag=java,spring
```

Spring MVC có thể chuyển chuỗi query thành collection thông qua `ConversionService`; converter mặc định thường hỗ trợ chuỗi phân tách bằng dấu phẩy. Tuy nhiên, cần kiểm thử đúng phiên bản Spring và kiểu dữ liệu đang dùng để bảo đảm hành vi bind khớp hợp đồng. Nếu có phần tử chứa dấu phẩy, delimiter có thể gây nhập nhằng; hãy quy định cách percent-encode hoặc chọn kiểu truyền lặp lại.

Có thể khai báo quy tắc `style` và `explode` trên tham số Java bằng `@Parameter`. Khi kiểu Java là `List<T>` hoặc mảng, springdoc có thể suy ra schema array từ kiểu tham số:

```java
@GetMapping
public List<ProductResponse> search(
        @Parameter(
            name = "tag",
            description = "Danh sách nhãn, phân tách bằng dấu phẩy",
            style = ParameterStyle.FORM,
            explode = Explode.FALSE
        )
        @RequestParam(name = "tag", required = false) List<String> tags) {
    return productService.searchByTags(tags);
}
```

Nếu muốn giữ dạng lặp lại mặc định, dùng `ParameterStyle.FORM` và `Explode.TRUE`, hoặc để springdoc suy ra mặc định. Không khai báo schema kiểu chuỗi cho một `List<T>` nếu mục tiêu là công bố array.

Các import OpenAPI dùng trong ví dụ:

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.Explode;
import io.swagger.v3.oas.annotations.enums.ParameterStyle;
```

## 5. Các kiểu tuần tự hóa mảng thường gặp

OpenAPI hỗ trợ nhiều `style` tùy vị trí tham số. Với query array, các lựa chọn chính gồm:

| `style` | `explode` | Ví dụ với `tag = ["java", "spring"]` | Vị trí |
| --- | --- | --- | --- |
| `form` | `true` | `?tag=java&tag=spring` | Query; mặc định |
| `form` | `false` | `?tag=java,spring` | Query |
| `spaceDelimited` | `false` | `?tag=java%20spring` | Query |
| `pipeDelimited` | `false` | `?tag=java%7Cspring` | Query |
| `simple` | `false` | `X-Tags: java,spring` hoặc `/items/java,spring` | Header hoặc path |

`spaceDelimited` và `pipeDelimited` chỉ có ý nghĩa cho array hoặc object trong query. Với các kiểu này, `explode` phải là `false`. Ký tự phân tách có thể xuất hiện dưới dạng percent-encoded trong URL: khoảng trắng thành `%20`, dấu `|` thành `%7C`. Trình duyệt, proxy hoặc công cụ client có thể hiển thị URL đã encode hoặc decode, nhưng nội dung truyền trên dây cần tuân theo quy tắc URI.

`simple` là kiểu mặc định cho path và header parameter. Với array, `explode: false` nối các phần tử bằng dấu phẩy. Ví dụ path parameter:

```yaml
parameters:
  - name: ids
    in: path
    required: true
    style: simple
    explode: false
    schema:
      type: array
      items:
        type: integer
        format: int64
```

URL tương ứng:

```text
GET /api/orders/10,20,30
```

Không phải mọi delimiter đều được Spring MVC tự chuyển thành `List<T>`. Kiểu comma-delimited có thể dùng conversion mặc định; pipe-delimited hoặc space-delimited thường cần parser/converter phù hợp. Nếu chọn một kiểu khác mặc định, hãy triển khai cách parse ở server và kiểm thử request thực tế, không chỉ sửa `style` trong annotation.

## 6. Mô tả enum array và giới hạn danh sách

Một query array có thể chứa các giá trị enum. Ví dụ API lọc đơn hàng theo nhiều trạng thái:

```java
public enum OrderStatus {
    NEW,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}

@GetMapping("/api/orders")
public List<OrderResponse> findOrders(
        @RequestParam(name = "status", required = false)
        List<OrderStatus> statuses) {
    return orderService.findByStatuses(statuses);
}
```

Request mẫu:

```text
GET /api/orders?status=NEW&status=SHIPPED
```

Spring chuyển mỗi giá trị thành enum tương ứng nếu tên hoặc converter phù hợp. springdoc có thể suy ra danh sách giá trị hợp lệ từ kiểu enum. Nếu cần kiểm soát cách enum xuất hiện trong tài liệu, có thể dùng `@Schema` trên enum hoặc cấu hình serialization phù hợp với cách Jackson chuyển enum thành JSON.

Schema array cũng có thể công bố giới hạn số lượng phần tử, phần tử duy nhất hoặc kiểu dữ liệu của từng phần tử:

```yaml
schema:
  type: array
  minItems: 1
  maxItems: 10
  uniqueItems: true
  items:
    type: string
    enum: [NEW, CONFIRMED, SHIPPED, CANCELLED]
```

Với thuộc tính collection trong DTO, có thể dùng `@ArraySchema` để mô tả schema của phần tử và giới hạn của mảng:

```java
public class ProductFilter {

    @ArraySchema(
        schema = @Schema(type = "string"),
        minItems = 1,
        maxItems = 10,
        uniqueItems = true
    )
    private List<String> tags;
}
```

Các import tương ứng là `io.swagger.v3.oas.annotations.media.ArraySchema` và `io.swagger.v3.oas.annotations.media.Schema`.

Trong DTO, có thể dùng Bean Validation như `@Size` để giới hạn số phần tử, `@NotEmpty` để yêu cầu danh sách có ít nhất một phần tử, và constraint trên kiểu phần tử để kiểm tra từng giá trị. Ví dụ:

```java
public List<ProductResponse> search(
        @RequestParam(name = "tag", required = false)
        @Size(max = 10) List<@NotBlank String> tags) {
    return productService.searchByTags(tags);
}
```

Các annotation validation chỉ có tác dụng khi validation được kích hoạt và cấu hình đúng. OpenAPI mô tả giới hạn để client biết trước; server vẫn phải thực thi kiểm tra đầu vào.

## 7. Dùng `@ParameterObject` cho bộ lọc có nhiều trường

Khi một endpoint có nhiều query parameter liên quan, có thể gom chúng vào một POJO thay vì khai báo danh sách tham số dài:

```java
public class ProductSearchCriteria {

    private List<String> tag;
    private List<ProductStatus> status;
    private Integer page;
    private Integer size;

    public List<String> getTag() { return tag; }
    public void setTag(List<String> tag) { this.tag = tag; }

    public List<ProductStatus> getStatus() { return status; }
    public void setStatus(List<ProductStatus> status) { this.status = status; }

    public Integer getPage() { return page; }
    public void setPage(Integer page) { this.page = page; }

    public Integer getSize() { return size; }
    public void setSize(Integer size) { this.size = size; }
}
```

Controller:

```java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.web.bind.annotation.ModelAttribute;

@GetMapping("/api/products/search")
public Page<ProductResponse> search(
        @ParameterObject @ModelAttribute ProductSearchCriteria criteria) {
    return productService.search(criteria);
}
```

springdoc có thể bung các field của parameter object thành query parameter riêng. Ví dụ, client gửi `?tag=java&tag=spring&status=ACTIVE&page=0&size=20`. Các field cần getter theo quy ước JavaBean để springdoc nhận diện. Theo FAQ của springdoc, `@ParameterObject` hỗ trợ POJO request parameter của Spring MVC nhưng không hỗ trợ parameter object lồng nhau; với cấu trúc phức tạp, hãy mô tả parameter rõ ràng hoặc thiết kế query đơn giản hơn.

## 8. Phân biệt mảng với object query và deepObject

`deepObject` dành cho object query có các thuộc tính scalar, không phải kiểu truyền mảng tổng quát. Ví dụ một bộ lọc object:

```yaml
parameters:
  - name: filter
    in: query
    style: deepObject
    explode: true
    schema:
      type: object
      properties:
        active:
          type: boolean
        region:
          type: string
```

Request minh họa:

```text
GET /api/products?filter[active]=true&filter[region]=north
```

OpenAPI định nghĩa biểu diễn `deepObject` cho object có thuộc tính scalar. Cách biểu diễn thuộc tính array hoặc object lồng nhau không được chuẩn hóa rõ trong đặc tả. Nếu cần gửi danh sách, hãy dùng array parameter riêng như `tag=java&tag=spring`, hoặc dùng request body JSON cho bộ lọc phức tạp.

## 9. Quy tắc đặt tên và tương thích client

Khi thiết kế tham số array, hãy giữ cách đặt tên nhất quán. Dùng `tag` nếu mỗi giá trị là một tag của cùng bộ lọc; dùng `tagIds` nếu API nhận danh sách ID. Tránh đổi tên giữa số ít và số nhiều tùy endpoint vì client sinh tự động có thể tạo model hoặc hàm không đồng nhất.

Một số nguyên tắc thực tế:

- Chọn dạng lặp lại cho query array khi không có yêu cầu tương thích khác: `?id=1&id=2`.
- Chỉ dùng dấu phẩy, khoảng trắng hoặc `|` khi hợp đồng cần kiểu tuần tự hóa đó và server đã hỗ trợ.
- Công bố `minItems`, `maxItems`, `uniqueItems`, kiểu phần tử và enum khi có giới hạn.
- Xác định hành vi khi không truyền, truyền rỗng, truyền phần tử trùng hoặc danh sách vượt giới hạn.
- Kiểm tra percent-encoding với dấu phẩy, dấu `|`, dấu `+`, `&`, `#`, dấu ngoặc vuông và ký tự Unicode.
- Giữ nguyên thứ tự phần tử nếu thứ tự có ý nghĩa; nếu không, ghi rõ danh sách được xem như tập hợp.

Trong OpenAPI 2.0/Swagger 2.0, cách truyền collection thường được mô tả bằng `collectionFormat` với các giá trị như `csv`, `ssv`, `tsv`, `pipes` và `multi`. OpenAPI 3 thay cơ chế đó bằng cặp `style` và `explode`. Khi chuyển tài liệu từ Swagger 2 sang OpenAPI 3, cần chuyển đổi đúng ý nghĩa: `multi` thường tương ứng `style: form, explode: true`; `csv` thường tương ứng `style: form, explode: false`; `ssv` tương ứng `spaceDelimited`; `pipes` tương ứng `pipeDelimited`. `tsv` không có kiểu `style` tương đương trực tiếp trong OpenAPI 3, nên cần chọn quy ước khác hoặc mô tả bằng cơ chế nội dung phù hợp.

## 10. Kiểm tra tài liệu và hành vi thực tế

Sau khi ứng dụng khởi động, mở `/v3/api-docs` hoặc endpoint đã cấu hình và tìm operation cần kiểm tra. Với mỗi array parameter, xác nhận:

1. `schema.type` là `array` và `items` mô tả đúng kiểu phần tử.
2. `name` và `in` đúng với tên query, path, header hoặc cookie mà controller nhận.
3. `style` và `explode` tạo đúng định dạng request mà server hỗ trợ.
4. `required`, `minItems`, `maxItems`, `uniqueItems`, enum và ví dụ phản ánh đúng validation.
5. Swagger UI gửi đúng dạng request khi nhập nhiều giá trị.
6. Server bind được request đã gửi và xử lý đúng trường hợp thiếu, rỗng, trùng hoặc sai định dạng.

Ví dụ kiểm tra query array mặc định bằng `curl`:

```bash
curl -i "http://localhost:8080/api/products?tag=java&tag=spring"
```

Ví dụ kiểm tra comma-delimited:

```bash
curl -i "http://localhost:8080/api/products?tag=java,spring"
```

Đối với ký tự đặc biệt, hãy encode theo URI trước khi gửi. Ví dụ `|` có thể truyền dưới dạng `%7C`; không dựa vào việc một client cụ thể chấp nhận URL chưa encode để kết luận request tương thích với mọi proxy hoặc server.

Một kiểm thử tích hợp nên bao gồm ít nhất: một giá trị, nhiều giá trị lặp, một danh sách phân tách theo delimiter đã chọn, không truyền tham số, giá trị rỗng, phần tử không hợp lệ và số phần tử vượt giới hạn. Nếu có nhiều cách tuần tự hóa được hỗ trợ, kiểm thử từng cách như một trường hợp riêng.

## 11. Lỗi thường gặp và cách khắc phục

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Server chỉ nhận phần tử đầu tiên | Handler khai báo kiểu scalar như `String` thay vì `List<String>` hoặc mảng | Dùng `List<T>`, `T[]` hoặc `MultiValueMap` |
| Swagger UI gửi `tag=java&tag=spring` nhưng API mong `tag=java,spring` | OpenAPI dùng `form` với `explode=true` trong khi server yêu cầu `explode=false` | Đồng bộ `style`, `explode` và cách bind của Spring |
| Tài liệu hiển thị kiểu string thay vì array | Kiểu Java hoặc annotation schema không thể hiện collection | Khai báo `List<T>`/mảng và kiểm tra `schema.type` cùng `items` |
| Dấu `|` hoặc khoảng trắng không được tách | Spring conversion mặc định không dùng delimiter này | Viết converter/parser riêng và kiểm thử percent-encoding |
| `@ParameterObject` không bung field | POJO thiếu getter theo quy ước, hoặc object lồng nhau | Bổ sung getter/setter và dùng object phẳng hoặc mô tả parameter thủ công |
| Giá trị rỗng và không truyền bị xử lý giống nhau | Chưa xác định quy ước cho `null`, empty string và empty list | Định nghĩa rõ hợp đồng và viết kiểm thử cho từng trường hợp |
| SDK sinh ra gửi sai query string | `style`/`explode` không khớp server hoặc công cụ client hỗ trợ không đầy đủ | Kiểm tra OpenAPI JSON và request thực tế của SDK |

## 12. Tài liệu tham khảo chính thức

- [OpenAPI Specification 3.1.2 — Parameter Object](https://spec.openapis.org/oas/v3.1.2.html#parameter-object) — schema, `style`, `explode`, `allowReserved` và quy tắc serialization.
- [OpenAPI Specification 3.1.2 — Style Examples](https://spec.openapis.org/oas/v3.1.2.html#style-examples) — ví dụ tuần tự hóa primitive, array và object.
- [springdoc-openapi — FAQ](https://springdoc.org/faq.html) — `@ParameterObject`, các field query POJO và giới hạn object lồng nhau.
- [Swagger Annotations — Parameter](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/Parameter.html) — thuộc tính `style`, `explode`, `schema` và `array` của annotation `@Parameter`.

Khi danh sách giá trị được mô tả đúng, client có thể tạo query string nhất quán và Spring Boot có thể bind chúng vào collection theo cách dự kiến. Hãy xem `type: array`, `style` và `explode` là một phần của hợp đồng API; thay đổi delimiter hoặc cách lặp tham số có thể ảnh hưởng đến client hiện hữu và cần được kiểm thử như một thay đổi hợp đồng.
