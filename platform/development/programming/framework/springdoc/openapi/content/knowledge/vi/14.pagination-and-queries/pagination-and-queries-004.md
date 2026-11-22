# Chỉ số trang bắt đầu từ 0 hoặc 1 và hợp đồng thực tế

Phân trang bằng query parameter `page` tưởng như đơn giản, nhưng các hệ thống có thể hiểu chỉ số trang theo hai quy ước khác nhau. Với chỉ số bắt đầu từ 0 (zero-based), `page=0` là trang đầu tiên. Với chỉ số bắt đầu từ 1 (one-based), `page=1` là trang đầu tiên.

Spring Data dùng chỉ số trang bắt đầu từ 0 trong `Pageable`, `PageRequest` và `Page.getNumber()`. API công khai vẫn có thể chọn nhận `page=1` cho trang đầu tiên, nhưng phải chuyển đổi rõ ràng giữa quy ước của client và chỉ số nội bộ. Spring Boot có tùy chọn hỗ trợ one-based query parameter khi bind vào `Pageable`; tùy chọn đó không thay đổi bản chất zero-based của `PageRequest` và metadata `Page`.

Với Springdoc, tài liệu OpenAPI cần mô tả đúng quy ước mà client gửi và nhận. Không nên chỉ dựa vào tên parameter `page` hoặc kiểu `Pageable` để người dùng tự đoán trang đầu tiên là 0 hay 1.

## 1. Phân biệt zero-based và one-based

Hai quy ước khác nhau ở giá trị của trang đầu tiên:

| Quy ước | Trang đầu tiên | Trang thứ hai | Trang thứ ba | Công thức offset |
|---|---:|---:|---:|---|
| Zero-based | `page=0` | `page=1` | `page=2` | `offset = page × size` |
| One-based | `page=1` | `page=2` | `page=3` | `offset = (page - 1) × size` |

Ví dụ `size=20`:

- Zero-based `page=0` lấy các phần tử từ vị trí offset 0 đến 19.
- One-based `page=1` cũng lấy các phần tử từ vị trí offset 0 đến 19.
- Zero-based `page=2` và one-based `page=3` đều bắt đầu ở offset 40.

Hai quy ước có thể truy cập cùng một dữ liệu nếu server chuyển đổi đúng. Khác biệt nằm ở hợp đồng request mà client phải gửi.

## 2. Vì sao Spring Data dùng chỉ số bắt đầu từ 0?

Các API nền tảng của Spring Data được thiết kế theo chỉ số nội bộ zero-based:

```java
PageRequest firstPage = PageRequest.of(0, 20);
PageRequest secondPage = PageRequest.of(1, 20);
PageRequest thirdPage = PageRequest.of(2, 20);
```

Tham số đầu tiên của `PageRequest.of(page, size)` là page index bắt đầu từ 0. `Page.getNumber()` cũng trả về chỉ số trang zero-based. `Page.getTotalPages()` trả tổng số trang; `Page.getNumberOfElements()` trả số phần tử thực có trong trang hiện tại.

Ví dụ truy vấn repository:

```java
Page<Product> products = productRepository.findAll(
    PageRequest.of(0, 20, Sort.by("name").ascending())
);

int internalPageIndex = products.getNumber(); // 0
```

Ngay cả khi API nhận query one-based, khi đã tạo `PageRequest` thì chỉ số bên trong vẫn là 0 cho trang đầu tiên. Không truyền trực tiếp `page=1` từ client one-based vào `PageRequest.of(1, size)`, vì như vậy server sẽ trả trang thứ hai.

## 3. Hợp đồng zero-based cho API công khai

Nếu chọn zero-based, query parameter có thể được mô tả như sau:

```http
GET /api/products?page=0&size=20
```

Ý nghĩa:

- `page`: chỉ số trang bắt đầu từ 0; mặc định `0`.
- `size`: số phần tử tối đa trong một trang; ví dụ mặc định `20`.
- `sort`: tiêu chí sắp xếp, nếu API hỗ trợ.

Ví dụ controller nhận `Pageable`:

```java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping
    Page<ProductResponse> list(
        @ParameterObject
        @PageableDefault(page = 0, size = 20, sort = "name")
        Pageable pageable
    ) {
        return productService.findAll(pageable).map(ProductResponse::from);
    }
}
```

`@ParameterObject` yêu cầu Springdoc phân rã `Pageable` thành các query parameter, thường gồm `page`, `size` và `sort`. `@PageableDefault` đặt mặc định cho đối tượng Pageable khi request không truyền các giá trị tương ứng. Để hợp đồng rõ ràng, phần mô tả của `page` nên nói rõ `0` là trang đầu tiên, `size` là số phần tử và giới hạn tối đa nếu có.

## 4. Hợp đồng one-based cho API công khai

Nhiều API hướng đến người dùng chọn one-based vì cách gọi “trang 1, trang 2” quen thuộc hơn. Khi đó request đầu tiên là:

```http
GET /api/products?page=1&size=20
```

Server cần chuyển đổi từ số trang công khai sang chỉ số Spring Data:

```java
int pageIndex = pageNumber - 1;
Pageable pageable = PageRequest.of(pageIndex, size);
```

Với cách xử lý thủ công, nên xác thực `pageNumber >= 1` trước khi trừ 1. Không tự động đổi `page=0` thành trang đầu tiên nếu hợp đồng quy định 1-based; trả lỗi 400 giúp client phát hiện sai quy ước.

### Ví dụ controller nhận one-based rõ ràng

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.validation.annotation.Validated;

@RestController
@Validated
@RequestMapping("/api/products")
class ProductController {

    @GetMapping
    ResponseEntity<ProductPageResponse> list(
        @Parameter(
            description = "Số thứ tự trang, bắt đầu từ 1. Trang đầu tiên là page=1.",
            example = "1",
            schema = @Schema(defaultValue = "1", minimum = "1")
        )
        @RequestParam(defaultValue = "1")
        @Min(1) int page,

        @Parameter(
            description = "Số sản phẩm tối đa trong một trang.",
            example = "20",
            schema = @Schema(defaultValue = "20", minimum = "1", maximum = "100")
        )
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(100) int size
    ) {
        Page<Product> result = productService.findAll(
            PageRequest.of(page - 1, size, Sort.by("name").ascending())
        );
        return ResponseEntity.ok(ProductPageResponse.fromOneBased(result));
    }
}
```

Trong ví dụ, client gửi page bắt đầu từ 1; controller chuyển thành `page - 1` trước khi gọi Spring Data. `@Parameter` cung cấp mô tả và ví dụ để tài liệu OpenAPI thể hiện đúng quy ước. `@Min` và `@Max` kiểm tra giá trị runtime khi Bean Validation được kích hoạt cho method parameter theo cấu hình ứng dụng; dự án cần dependency validation tương ứng, thường là `spring-boot-starter-validation`.

Ví dụ dùng `jakarta.validation` phù hợp với các dòng Spring Boot hiện đại dùng Jakarta. Với dự án cũ sử dụng `javax.validation`, import sẽ khác.

## 5. Bật one-based query parameter cho `Pageable` trong Spring Boot

Nếu controller nhận trực tiếp `Pageable`, Spring Boot cho phép cấu hình resolver để query parameter `page` được hiểu theo chỉ số bắt đầu từ 1:

```yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
```

Hoặc trong `application.properties`:

```properties
spring.data.web.pageable.one-indexed-parameters=true
```

Khi bật tùy chọn này, request `?page=1&size=20` được Pageable argument resolver chuyển thành `Pageable` có `getPageNumber() == 0`. Request `?page=2&size=20` được chuyển thành page index nội bộ `1`.

Điều quan trọng:

- Tùy chọn này ảnh hưởng đến cách Spring Data web resolver bind query parameter vào `Pageable`.
- Nó không đổi `PageRequest.of(...)`; API đó vẫn nhận chỉ số zero-based.
- Nó không đổi `Page.getNumber()`; giá trị vẫn là chỉ số nội bộ zero-based.
- Nó không tự biến response metadata thành one-based.
- Nó không tự bảo đảm tài liệu OpenAPI mô tả rõ page bắt đầu từ 1.
- Nếu controller nhận `@RequestParam int page` rồi tự tạo `PageRequest`, thuộc tính resolver này không tự thực hiện phép chuyển đổi cho biến int đó.

Resolver one-indexed chuẩn thường trừ 1 khi giá trị page lớn hơn 0; `page=0` có thể vẫn được chuyển thành index 0 thay vì tự động bị từ chối. Vì vậy, nếu hợp đồng yêu cầu nghiêm ngặt `page >= 1`, chỉ bật thuộc tính này chưa đủ để bảo đảm validation. Hãy bổ sung kiểm tra ở tầng nhận request hoặc custom resolver phù hợp. Còn nếu dùng `@RequestParam int page` như ví dụ trước, `@Min(1)` cùng method validation sẽ từ chối page 0.

Vì vậy, chỉ bật thuộc tính khi controller thực sự dùng `Pageable` được Spring bind. Nếu có endpoint dùng cả `Pageable` và `@RequestParam page` thủ công, hãy áp dụng quy tắc rõ ràng cho từng endpoint.

## 6. Không nhầm query one-based với metadata `Page` zero-based

Đây là nguồn lỗi phổ biến. Khi dùng `one-indexed-parameters=true`, client gửi `page=1` cho trang đầu tiên, nhưng `Pageable` nội bộ có page number là 0. Kết quả repository trả về `Page` vẫn có:

```java
page.getNumber() == 0
```

Nếu API trả thẳng `Page<T>` hoặc một cấu trúc metadata dựa trực tiếp trên `Page.getNumber()`, response có thể chứa `number: 0` trong khi request dùng `page=1`.

Điều này không nhất thiết sai: metadata đang biểu diễn chỉ số nội bộ zero-based. Nhưng nếu hợp đồng công khai muốn cả request lẫn response đều one-based, phải chuyển đổi metadata khi tạo response.

### DTO metadata one-based

```java
public record PageMetadata(
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last
) {
    static PageMetadata fromOneBased(Page<?> result) {
        return new PageMetadata(
            result.getNumber() + 1,
            result.getSize(),
            result.getTotalElements(),
            result.getTotalPages(),
            result.isFirst(),
            result.isLast()
        );
    }
}

public record ProductPageResponse(
    List<ProductResponse> content,
    PageMetadata page
) {
    static ProductPageResponse fromOneBased(Page<Product> result) {
        return new ProductPageResponse(
            result.getContent().stream().map(ProductResponse::from).toList(),
            PageMetadata.fromOneBased(result)
        );
    }
}
```

Với response này, trang đầu tiên có `page: 1`. `totalPages` vẫn là số lượng trang, không cộng thêm 1. `first` và `last` lấy từ kết quả Page; không tự tính lại theo chỉ số công khai.

Ví dụ JSON:

```json
{
  "content": [
    { "id": 42, "name": "Keyboard" }
  ],
  "page": {
    "page": 1,
    "size": 20,
    "totalElements": 45,
    "totalPages": 3,
    "first": true,
    "last": false
  }
}
```

Nếu API chọn zero-based cho request, response metadata nên giữ `page: 0` ở trang đầu tiên. Điều quan trọng là ghi rõ semantics trong schema và mô tả response.

## 7. Dùng `Pageable` với Springdoc

Springdoc hỗ trợ mô tả `Pageable` thành các query parameter bằng `@ParameterObject`:

```java
@GetMapping
Page<ProductResponse> list(@ParameterObject Pageable pageable) {
    return productService.findAll(pageable).map(ProductResponse::from);
}
```

Tài liệu thường thể hiện:

| Parameter | Ý nghĩa |
|---|---|
| `page` | Chỉ số trang |
| `size` | Số phần tử trong trang |
| `sort` | Một hoặc nhiều tiêu chí sắp xếp |

Tuy nhiên, việc Springdoc nhận diện `Pageable` không có nghĩa nó tự biết hợp đồng của ứng dụng là zero-based hay one-based trong mọi cấu hình. Hãy bổ sung mô tả rõ ràng, ví dụ và default cho `page`. Có thể dùng `@Parameter` hoặc cơ chế tùy chỉnh parameter phù hợp với phiên bản Springdoc.

Nếu cần kiểm soát chính xác nội dung OpenAPI, có thể khai báo query parameter tường minh bằng `@RequestParam` như ví dụ one-based ở trên. Cách này dài hơn nhưng dễ đảm bảo description, minimum, default và example khớp với logic chuyển đổi.

### `@PageableDefault` không đổi quy ước index

Ví dụ:

```java
@PageableDefault(page = 0, size = 20)
Pageable pageable
```

`page = 0` là giá trị mặc định nội bộ của Pageable. Khi resolver được cấu hình one-based, query bên ngoài vẫn có thể bắt đầu từ 1 trong khi default Pageable được tạo với page index 0. Đừng đổi `@PageableDefault(page = 1)` chỉ vì API công khai nhận `page=1`; điều đó có thể khiến default nội bộ chuyển sang trang thứ hai.

## 8. Mô tả hợp đồng zero-based trong OpenAPI

Nếu API công khai dùng zero-based, parameter nên thể hiện điều đó:

```yaml
parameters:
  - name: page
    in: query
    required: false
    description: Chỉ số trang bắt đầu từ 0; trang đầu tiên là page=0.
    schema:
      type: integer
      minimum: 0
      default: 0
      example: 0
  - name: size
    in: query
    required: false
    description: Số phần tử tối đa trong một trang.
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
```

## 9. Mô tả hợp đồng one-based trong OpenAPI

Nếu API công khai dùng one-based, schema nên phản ánh minimum 1 và ví dụ 1:

```yaml
parameters:
  - name: page
    in: query
    required: false
    description: Số thứ tự trang bắt đầu từ 1; trang đầu tiên là page=1.
    schema:
      type: integer
      minimum: 1
      default: 1
      example: 1
  - name: size
    in: query
    required: false
    description: Số phần tử tối đa trong một trang.
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
```

Trong OpenAPI 3.0, `example` thường được đặt trên Parameter Object hoặc Schema Object theo cấu trúc được hỗ trợ; nếu validator của dự án yêu cầu, chọn một vị trí hợp lệ cho phiên bản đặc tả đang dùng. Nội dung quan trọng là mô tả và giới hạn phải thể hiện đúng hợp đồng.

## 10. Kiểm soát `size`, giá trị âm và trang vượt phạm vi

Quy ước index không phải quy tắc duy nhất của phân trang. API cũng cần công bố:

- `size` mặc định là bao nhiêu.
- Kích thước tối đa cho phép.
- `page` âm hoặc bằng 0 được xử lý ra sao.
- Trang vượt quá `totalPages` trả danh sách rỗng, 404 hay lỗi validation.
- Thứ tự sắp xếp mặc định và các field được phép sort.

Không nên cho client gửi `size` không giới hạn vì có thể tạo truy vấn lớn và response nặng. Với one-based, `page=0` thường nên bị từ chối bằng 400; với zero-based, `page=-1` nên bị từ chối. `size` phải lớn hơn 0 và có giới hạn tối đa.

Trang vượt quá phạm vi thường trả content rỗng cùng metadata tổng số phần tử, nhưng đây là quyết định của hợp đồng API. Hãy chọn một hành vi và mô tả nhất quán.

Khi tính offset thủ công, chú ý overflow với page hoặc size rất lớn. Nên dùng `Pageable`/`PageRequest` và giới hạn đầu vào thay vì tự nhân hai số nguyên không được xác thực.

## 11. `sort` là một phần của hợp đồng phân trang

Spring Data thường nhận sort qua query parameter `sort`. Ví dụ:

```http
GET /api/products?page=1&size=20&sort=name,asc&sort=createdAt,desc
```

Mỗi giá trị có thể gồm tên property và hướng sắp xếp. Cần công bố các property được phép sort; không nên để client truyền tên cột database tùy ý. API có thể ánh xạ tên sort công khai sang property domain/repository tương ứng.

Ví dụ mô tả:

```yaml
- name: sort
  in: query
  required: false
  description: Tiêu chí sắp xếp; có thể lặp lại, ví dụ sort=name,asc.
  schema:
    type: array
    items:
      type: string
  style: form
  explode: true
```

Nếu controller dùng `Pageable`, hãy xác minh cách Springdoc biểu diễn tham số sort trong phiên bản hiện tại. Nếu API có quy tắc sort riêng, mô tả rõ bằng annotation hoặc khai báo parameter tường minh.

## 12. Ảnh hưởng đến response links và điều hướng trang

Nếu API trả `next`, `previous`, `first` hoặc `last` link, số trang trong URL phải theo quy ước công khai.

Ví dụ one-based:

```json
{
  "page": 1,
  "size": 20,
  "totalPages": 3,
  "links": {
    "self": "/api/products?page=1&size=20",
    "next": "/api/products?page=2&size=20",
    "last": "/api/products?page=3&size=20"
  }
}
```

Ví dụ zero-based sẽ dùng `page=0`, `page=1` và `page=2` cho cùng ba trang. Không lấy trực tiếp số trang nội bộ rồi tạo URL one-based mà quên cộng 1; cũng không cộng 1 hai lần nếu đã dùng resolver chuyển đổi và một helper URL đã trả số công khai.

Nếu dùng OpenAPI Link Object cho quan hệ giữa trang hiện tại và trang tiếp theo, runtime expression phải tham chiếu đúng cursor/page value trong response. Link Object không tự tạo URL pagination hoặc header `Link`; server cần trả link thật nếu client cần điều hướng theo response.

## 13. Kiểm thử để phát hiện lỗi off-by-one

Lỗi thường gặp nhất là trang đầu tiên bị bỏ qua hoặc hai trang đầu bị lặp do chuyển đổi sai một đơn vị. Hãy kiểm tra tối thiểu các trường hợp:

| Request | Hợp đồng zero-based | Hợp đồng one-based |
|---|---|---|
| Giá trị đầu tiên | `page=0` | `page=1` |
| Giá trị thứ hai | `page=1` | `page=2` |
| Giá trị không hợp lệ theo hợp đồng nghiêm ngặt | `page=-1` | `page=0` |
| Không truyền page | Mặc định trang đầu | Mặc định trang đầu |

Ví dụ kiểm thử mapping one-based sang Pageable:

```java
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.PageRequest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PageIndexMapperTest {

    @Test
    void convertsOneBasedPageToZeroBasedIndex() {
        int publicPage = 1;
        int internalPage = publicPage - 1;

        assertThat(PageRequest.of(internalPage, 20).getPageNumber()).isZero();
    }

    @Test
    void rejectsZeroForOneBasedContract() {
        int publicPage = 0;

        assertThatThrownBy(() -> toZeroBasedPage(publicPage))
            .isInstanceOf(IllegalArgumentException.class);
    }

    private int toZeroBasedPage(int publicPage) {
        if (publicPage < 1) {
            throw new IllegalArgumentException("page phải bắt đầu từ 1");
        }
        return publicPage - 1;
    }
}
```

Với endpoint dùng Spring `Pageable`, nên có integration test để xác nhận cấu hình resolver thật sự chuyển `page=1` thành page index 0. Nếu hợp đồng yêu cầu từ chối `page=0`, hãy thêm test cho điều kiện đó vì resolver one-indexed mặc định có thể vẫn ánh xạ giá trị này về trang đầu. Đồng thời kiểm tra JSON response metadata để chắc chắn `page` trả về dùng cùng quy ước mà hợp đồng đã công bố.

## 14. Kiểm tra tài liệu Springdoc được sinh ra

Sau khi chạy ứng dụng, mở `/v3/api-docs` và kiểm tra operation phân trang. Với zero-based, description/example/default nên nói rõ `page=0` là trang đầu. Với one-based, minimum/default/example nên tương ứng `1`.

Có thể dùng `curl` và `jq` để xem parameter:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/products"].get.parameters'
```

Kiểm tra schema response:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.components.schemas.ProductPageResponse'
```

Nếu dùng `Page<T>` trực tiếp, kiểm tra cấu trúc schema được Springdoc sinh ra và đừng giả định metadata response đã được chuyển sang one-based. Nếu hợp đồng cần metadata tùy chỉnh, tạo DTO response riêng và mô tả rõ `page`.

## 15. Chuyển đổi một API đã phát hành từ zero-based sang one-based

Đổi `page=0` thành `page=1` là thay đổi hợp đồng request. Client hiện tại có thể đang gửi `page=0` cho trang đầu tiên; nếu server đột ngột chuyển sang one-based, request đó có thể bị từ chối hoặc trả dữ liệu sai.

Một kế hoạch chuyển đổi nên gồm:

1. Xác định client nào đang dùng API và quy ước hiện tại.
2. Không thay đổi semantics âm thầm trên cùng route nếu client cũ vẫn được hỗ trợ.
3. Cân nhắc phiên bản API mới hoặc thời gian chuyển tiếp có cơ chế tương thích rõ.
4. Cập nhật OpenAPI description, default, minimum, examples và response metadata.
5. Cập nhật SDK, tài liệu hướng dẫn, link phân trang và test.
6. Theo dõi request cũ trong thời gian chuyển đổi rồi mới ngừng hỗ trợ.

Nếu cần hỗ trợ đồng thời hai quy ước, tránh dùng cùng một parameter `page` với cách hiểu mơ hồ. Có thể tạo version endpoint riêng hoặc parameter khác có tên rõ ràng trong giai đoạn chuyển đổi. Cách làm phải dễ hiểu và không khiến một request hợp lệ có hai cách diễn giải.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `page=1` trả trang thứ hai | Truyền one-based trực tiếp vào `PageRequest.of` | Trừ 1 trước khi tạo PageRequest hoặc dùng resolver one-indexed |
| `page=0` trả 400 dù trước đây hợp lệ | API đã chuyển sang one-based | Cập nhật client hoặc duy trì tương thích theo kế hoạch |
| Request dùng `page=1` nhưng response báo `number=0` | `Page.getNumber()` vẫn zero-based | Chuyển metadata sang one-based nếu hợp đồng yêu cầu |
| `@PageableDefault(page = 1)` làm default thành trang thứ hai | Nhầm page index nội bộ với số thứ tự công khai | Để default Pageable là 0; resolver xử lý query one-based |
| Bật `one-indexed-parameters` nhưng controller vẫn nhận sai | Controller dùng `@RequestParam int` hoặc tự tạo PageRequest | Tùy chỉnh conversion cho kiểu nhận thực tế |
| OpenAPI không nói rõ trang đầu tiên là 0 hay 1 | Chỉ dùng `@ParameterObject Pageable` mà không bổ sung mô tả | Thêm description, default, minimum và example |
| Link next/previous lặp hoặc bỏ qua trang | URL dùng sai quy ước hoặc cộng/trừ 1 hai lần | Kiểm tra công thức chuyển đổi và response metadata |
| Kết quả truy vấn quá lớn | Không giới hạn `size` | Đặt default, maximum và validation |

## 17. Checklist thiết kế hợp đồng phân trang

- [ ] Đã chọn rõ zero-based hoặc one-based cho query parameter `page`.
- [ ] Giá trị mặc định tương ứng với trang đầu tiên của quy ước đã chọn.
- [ ] Nếu dùng Spring Data, hiểu `PageRequest` và `Page.getNumber()` luôn zero-based.
- [ ] Nếu bật `spring.data.web.pageable.one-indexed-parameters`, controller thực sự nhận `Pageable` qua resolver.
- [ ] Nếu tự nhận `@RequestParam`, có logic chuyển đổi và validation riêng.
- [ ] `@PageableDefault` dùng page index nội bộ phù hợp, không nhầm với số trang công khai.
- [ ] OpenAPI description, minimum, default và example thể hiện đúng hợp đồng.
- [ ] Response metadata dùng cùng quy ước với request hoặc ghi rõ là zero-based nội bộ.
- [ ] `size` có giá trị mặc định và giới hạn tối đa.
- [ ] Sort parameter và các field được phép sort được mô tả rõ.
- [ ] Link phân trang dùng số trang theo quy ước công khai.
- [ ] Test bao phủ trang đầu, trang kế tiếp, giá trị biên và trang vượt phạm vi.
- [ ] Đã kiểm tra `/v3/api-docs` sau khi thay đổi cấu hình hoặc annotation.
- [ ] Có kế hoạch tương thích nếu đổi quy ước của API đã phát hành.

Spring Data dùng page index zero-based ở bên trong, nhưng API có thể công bố zero-based hoặc one-based cho client. Nếu dùng `Pageable`, `spring.data.web.pageable.one-indexed-parameters` giúp chuyển query one-based sang index nội bộ; nếu tự nhận `page`, controller phải tự chuyển đổi. Springdoc cần mô tả đúng quy ước request và response, còn kiểm thử phải xác nhận trang đầu tiên thực sự trả đúng dữ liệu để tránh lỗi off-by-one.
