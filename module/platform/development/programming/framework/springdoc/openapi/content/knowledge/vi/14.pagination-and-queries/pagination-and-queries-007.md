# Page, Slice và DTO phân trang do ứng dụng sở hữu

Spring Data cung cấp `Page<T>` và `Slice<T>` để biểu diễn kết quả truy vấn theo từng phần. Cả hai đều chứa các phần tử của lát dữ liệu hiện tại và thông tin điều hướng, nhưng khác nhau ở metadata tổng số kết quả. `Page<T>` cung cấp tổng số phần tử và tổng số trang; `Slice<T>` tập trung vào việc có phần tiếp theo hay không và thường tránh truy vấn đếm tổng.

Khi đưa kết quả ra API, controller có thể trả trực tiếp `Page<T>` hoặc `Slice<T>`. Cách đó nhanh để bắt đầu, nhưng JSON của kiểu thư viện không nhất thiết là hợp đồng công khai ổn định. Một DTO phân trang do ứng dụng sở hữu giúp kiểm soát tên trường, metadata, schema OpenAPI và khả năng tương thích khi nâng cấp Spring Data.

Bài học này tập trung vào việc chọn Page hay Slice theo nhu cầu, chuyển kết quả truy vấn thành DTO công khai, mô tả response bằng springdoc-openapi và kiểm thử cả dữ liệu lẫn metadata.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt `Page<T>` và `Slice<T>` về nội dung, metadata và chi phí truy vấn.
- Hiểu khi nào truy vấn phân trang cần count query và khi nào có thể tránh.
- Chọn Page hoặc Slice theo nhu cầu thực tế của client.
- Thiết kế DTO phân trang do ứng dụng sở hữu với tên trường và semantics ổn định.
- Chuyển Page/Slice của Spring Data sang DTO bằng `map()` và metadata tương ứng.
- Mô tả Page response và Slice response trong OpenAPI bằng springdoc-openapi.
- Công bố query parameters `page`, `size`, `sort` và giới hạn hợp lệ.
- Kiểm thử trang đầu, trang giữa, trang cuối, trang rỗng và metadata được ánh xạ đúng.

## 1. Page và Slice giải quyết vấn đề gì?

Giả sử API tìm kiếm sản phẩm có hàng trăm nghìn bản ghi. Nếu trả toàn bộ danh sách trong một response, server phải tải nhiều dữ liệu, response lớn và client phải xử lý nhiều hơn mức cần thiết. Phân trang cho phép client yêu cầu một phần kết quả:

~~~http
GET /api/products?page=0&size=20
~~~

Spring Data dùng `Pageable` để biểu diễn yêu cầu trang và trả về một trong các abstraction:

- `Page<T>`: nội dung hiện tại cùng metadata về tổng số kết quả và tổng số trang.
- `Slice<T>`: nội dung hiện tại cùng thông tin có phần tiếp theo hay không, không yêu cầu phải biết tổng số kết quả.

Hai abstraction này đều có nội dung hiện tại thông qua `getContent()`, kích thước trang, số trang hiện tại và thông tin điều hướng cơ bản. Điểm khác biệt chính là Page biết tổng số; Slice không cung cấp tổng số phần tử hoặc tổng số trang.

## 2. Page<T>: khi client cần tổng số kết quả

`Page<T>` phù hợp khi giao diện cần hiển thị tổng số bản ghi, tổng số trang, thanh chọn trang hoặc cho phép người dùng nhảy đến một trang cụ thể.

Ví dụ một Page có:

~~~text
page number        = 0
page size          = 20
total elements     = 57
total pages        = 3
number of elements = 20
first              = true
last               = false
~~~

Một số phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `getContent()` | Danh sách phần tử trong trang hiện tại |
| `getNumber()` | Chỉ số trang hiện tại, bắt đầu từ 0 theo mặc định |
| `getSize()` | Kích thước trang |
| `getNumberOfElements()` | Số phần tử thực tế trong trang hiện tại |
| `getTotalElements()` | Tổng số phần tử phù hợp truy vấn |
| `getTotalPages()` | Tổng số trang |
| `isFirst()` / `isLast()` | Có phải trang đầu/cuối |
| `hasNext()` / `hasPrevious()` | Có trang tiếp theo/trước đó |
| `isEmpty()` | Trang hiện tại không có phần tử |

### Chi phí count query

Với Spring Data JPA, việc tạo `Page<T>` thường cần biết tổng số bản ghi phù hợp truy vấn. Ngoài truy vấn lấy dữ liệu, repository có thể thực hiện thêm count query để tính `totalElements`, từ đó suy ra `totalPages`.

Ví dụ truy vấn:

~~~java
Page<Product> findPageByStatus(
    ProductStatus status,
    Pageable pageable
);
~~~

SQL khái niệm có thể tương đương:

~~~sql
SELECT id, name, price
FROM products
WHERE status = ?
ORDER BY created_at DESC
LIMIT ? OFFSET ?;

SELECT COUNT(*)
FROM products
WHERE status = ?;
~~~

Đây là hình dung về hai loại công việc, không phải cam kết Spring Data luôn phát đúng hai câu SQL trong mọi trường hợp. Framework có thể tối ưu hoặc bỏ count query nếu có thể suy ra tổng số từ kết quả và metadata truy vấn. Nhưng khi cần tổng số chính xác, count query thường là một phần chi phí đáng kể, đặc biệt với bộ lọc phức tạp, join nhiều bảng hoặc tập dữ liệu lớn.

### Khi nào chi phí tổng số là hợp lý?

Chọn Page khi client thực sự cần:

- Hiển thị tổng số kết quả, ví dụ “Có 12.450 sản phẩm”.
- Hiển thị số trang và cho phép nhảy trực tiếp đến trang bất kỳ.
- Tạo báo cáo cần tổng số chính xác tại thời điểm truy vấn.
- Thể hiện tiến trình duyệt toàn bộ tập kết quả theo số trang.

Nếu client chỉ cần nút “Tải thêm” hoặc “Xem tiếp”, việc tính tổng có thể là chi phí không cần thiết. Khi đó, cân nhắc Slice.

## 3. Slice<T>: khi chỉ cần biết còn dữ liệu tiếp theo

`Slice<T>` cung cấp nội dung hiện tại và thông tin điều hướng mà không yêu cầu tổng số phần tử. Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `getContent()` | Danh sách phần tử trong lát hiện tại |
| `getNumber()` | Chỉ số lát hiện tại |
| `getSize()` | Kích thước yêu cầu |
| `getNumberOfElements()` | Số phần tử thực tế |
| `isFirst()` / `isLast()` | Có phải lát đầu/cuối |
| `hasNext()` / `hasPrevious()` | Có lát tiếp theo/trước đó |
| `nextPageable()` / `previousPageable()` | Pageable cho lát tiếp theo/trước đó |
| `isEmpty()` | Lát hiện tại không có phần tử |

Slice không có `getTotalElements()` hoặc `getTotalPages()`. Đó là chủ ý trong thiết kế: client điều hướng tiếp theo dựa trên `hasNext()` thay vì cần biết trước toàn bộ kích thước tập dữ liệu.

### Vì sao Slice thường tránh count query?

Với truy vấn phân trang thông thường, Spring Data JPA có thể lấy nhiều hơn kích thước yêu cầu một phần tử để xác định còn dữ liệu tiếp theo hay không. Ví dụ client yêu cầu 20 phần tử, truy vấn có thể lấy tối đa 21 hàng:

- Nếu nhận 21 hàng, framework giữ lại 20 phần tử và đặt `hasNext=true`.
- Nếu nhận không quá 20 hàng, không còn phần tử kế tiếp và `hasNext=false`.

Cách thực hiện cụ thể phụ thuộc module Spring Data và kiểu truy vấn. Ý nghĩa của Slice là không cần tính tổng số bản ghi chỉ để xác định có trang kế tiếp.

Ví dụ repository:

~~~java
Slice<Product> findSliceByStatus(
    ProductStatus status,
    Pageable pageable
);
~~~

Slice phù hợp với:

- Feed hoạt động hoặc danh sách sự kiện mới nhất.
- Danh sách cuộn vô hạn.
- Màn hình “Tải thêm” không hiển thị tổng số.
- Tập dữ liệu lớn, trong đó count query tốn kém và không mang giá trị cho người dùng.

Nếu giao diện cần “Trang 4 trên 12” hoặc nhảy tới trang cuối, Slice không cung cấp đủ dữ liệu. Đừng tự suy ra tổng số từ `hasNext()`; hãy dùng Page hoặc một hợp đồng phân trang khác có total count.

## 4. So sánh Page và Slice

| Tiêu chí | Page<T> | Slice<T> |
|---|---|---|
| Nội dung trang hiện tại | Có | Có |
| Chỉ số trang và kích thước | Có | Có |
| Tổng số phần tử | Có | Không |
| Tổng số trang | Có | Không |
| Có phần tiếp theo | Có | Có |
| Count query | Thường cần nếu phải xác định total | Thường không cần |
| Nhảy đến trang bất kỳ | Phù hợp hơn | Không có thông tin tổng để hỗ trợ đầy đủ |
| “Tải thêm” | Có thể dùng nhưng dư metadata | Phù hợp |
| Chi phí truy vấn | Có thể cao hơn do count | Thường thấp hơn khi count đắt |

Một quy tắc thực tế:

- Dùng Page khi tổng số kết quả là một phần yêu cầu nghiệp vụ hoặc UX.
- Dùng Slice khi client chỉ cần biết có thể tải tiếp hay không.
- Dùng cursor pagination khi dữ liệu thay đổi liên tục, cần điều hướng theo con trỏ hoặc offset sâu trở nên tốn kém.

Không chọn Slice chỉ vì nghĩ nó luôn nhanh hơn. Truy vấn dữ liệu chính vẫn có thể nặng do join, sort, filter hoặc offset lớn. Slice chỉ giúp tránh yêu cầu tính tổng; nó không tự tối ưu mọi phần của truy vấn.

## 5. Vì sao API nên sở hữu DTO phân trang?

Trả trực tiếp `Page<T>` hoặc `Slice<T>` có thể tiện trong giai đoạn đầu:

~~~java
@GetMapping
public Page<ProductResponse> list(Pageable pageable) {
    return productService.findAll(pageable);
}
~~~

Nhưng kiểu trả về của Spring Data là abstraction thư viện. Nếu serialize trực tiếp implementation như PageImpl, JSON có thể phản ánh chi tiết nội bộ và thay đổi theo phiên bản. Client khi đó phụ thuộc vào cấu trúc do thư viện tạo ra thay vì một hợp đồng do ứng dụng định nghĩa.

Một DTO phân trang do ứng dụng sở hữu giúp:

- Đặt tên property rõ ràng và ổn định.
- Chỉ công bố metadata client thực sự cần.
- Ẩn chi tiết triển khai của Spring Data.
- Chuẩn hóa cấu trúc giữa nhiều endpoint.
- Giữ schema OpenAPI độc lập với implementation của repository.
- Dễ thay Page bằng Slice hoặc nguồn dữ liệu khác mà không buộc client đổi hợp đồng ngoài ý muốn.

Ví dụ response do ứng dụng kiểm soát:

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Bàn phím cơ"
    }
  ],
  "page": {
    "number": 0,
    "size": 20,
    "numberOfElements": 1,
    "totalElements": 57,
    "totalPages": 3,
    "first": true,
    "last": false
  }
}
~~~

Tên `items` và `page` là lựa chọn của hợp đồng ứng dụng. Có thể dùng `content`, `metadata` hoặc tên khác, miễn là nhất quán và được mô tả chính xác trong OpenAPI.

## 6. Thiết kế DTO cho Page response

Với endpoint cần tổng số, định nghĩa metadata riêng:

~~~java
public record PageMetadata(
    int number,
    int size,
    int numberOfElements,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last,
    boolean empty
) {}

public record ProductPageResponse(
    List<ProductResponse> items,
    PageMetadata page
) {}
~~~

Ý nghĩa của từng trường:

| Trường | Ý nghĩa |
|---|---|
| `items` | Các phần tử trong trang hiện tại |
| `number` | Chỉ số trang hiện tại, thường bắt đầu từ 0 |
| `size` | Kích thước trang hiệu lực |
| `numberOfElements` | Số phần tử thực tế trong `items` |
| `totalElements` | Tổng số phần tử phù hợp truy vấn |
| `totalPages` | Tổng số trang |
| `first` | Trang hiện tại có phải trang đầu |
| `last` | Trang hiện tại có phải trang cuối |
| `empty` | Trang hiện tại không có phần tử |

Không nên đưa mọi thuộc tính của Page vào DTO một cách máy móc. Ví dụ, nếu client không cần `sort` nội bộ, `pageable` hay offset, đừng công bố chúng. Metadata là một phần hợp đồng và cần có ý nghĩa ổn định với client.

### Chuyển Page sang DTO

Một mapper có thể chuyển Page<ProductResponse> thành ProductPageResponse:

~~~java
private ProductPageResponse toPageResponse(Page<ProductResponse> result) {
    PageMetadata metadata = new PageMetadata(
        result.getNumber(),
        result.getSize(),
        result.getNumberOfElements(),
        result.getTotalElements(),
        result.getTotalPages(),
        result.isFirst(),
        result.isLast(),
        result.isEmpty()
    );

    return new ProductPageResponse(result.getContent(), metadata);
}
~~~

`size` ở đây lấy từ Page đã được tạo sau khi áp dụng Pageable. Nếu ứng dụng có quy tắc giới hạn kích thước trang, metadata nên thể hiện kích thước thực tế mà server áp dụng.

## 7. Thiết kế DTO cho Slice response

Slice không có tổng số, vì vậy không nên tái sử dụng PageMetadata rồi điền `0` hoặc `null` cho `totalElements` và `totalPages`. Những giá trị đó có thể khiến client hiểu nhầm rằng hệ thống đã tính tổng và kết quả bằng 0.

Định nghĩa metadata phản ánh đúng semantics của Slice:

~~~java
public record SliceMetadata(
    int number,
    int size,
    int numberOfElements,
    boolean first,
    boolean last,
    boolean hasNext,
    boolean hasPrevious,
    boolean empty
) {}

public record ProductSliceResponse(
    List<ProductResponse> items,
    SliceMetadata slice
) {}
~~~

Ví dụ response:

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Bàn phím cơ"
    }
  ],
  "slice": {
    "number": 0,
    "size": 20,
    "numberOfElements": 1,
    "first": true,
    "last": false,
    "hasNext": true,
    "hasPrevious": false,
    "empty": false
  }
}
~~~

Client có thể dùng `hasNext` để quyết định hiển thị nút “Tải thêm”. Không có `totalPages` nên client không thể hiển thị “Trang 1 trên N” nếu không gọi một API khác để lấy tổng số.

### Chuyển Slice sang DTO

~~~java
private ProductSliceResponse toSliceResponse(Slice<ProductResponse> result) {
    SliceMetadata metadata = new SliceMetadata(
        result.getNumber(),
        result.getSize(),
        result.getNumberOfElements(),
        result.isFirst(),
        result.isLast(),
        result.hasNext(),
        result.hasPrevious(),
        result.isEmpty()
    );

    return new ProductSliceResponse(result.getContent(), metadata);
}
~~~

`isLast()` và `hasNext()` diễn đạt hai phía của cùng thông tin điều hướng trong Slice. Giữ cả hai trong DTO nếu client thấy hữu ích; nếu muốn schema nhỏ hơn, có thể chỉ công bố `hasNext` và `hasPrevious`.

## 8. Tái sử dụng mapper với Page.map() và Slice.map()

Thông thường, repository trả về entity, trong khi API cần response DTO. Không cần tự lặp qua nội dung rồi tự tính lại metadata. Page và Slice đều có phương thức `map()` để chuyển từng phần tử mà giữ thông tin phân trang:

~~~java
Page<Product> entities = productRepository.findPageByStatus(status, pageable);
Page<ProductResponse> responsePage = entities.map(ProductResponse::from);
~~~

Với Slice:

~~~java
Slice<Product> entities = productRepository.findSliceByStatus(status, pageable);
Slice<ProductResponse> responseSlice = entities.map(ProductResponse::from);
~~~

Ví dụ DTO:

~~~java
public record ProductResponse(
    Long id,
    String name,
    BigDecimal price
) {
    public static ProductResponse from(Product product) {
        return new ProductResponse(
            product.getId(),
            product.getName(),
            product.getPrice()
        );
    }
}
~~~

Sau khi map, `Page` vẫn giữ total count, số trang và trạng thái first/last; `Slice` vẫn giữ hasNext/hasPrevious. Điều này tránh lỗi thường gặp khi chỉ lấy `getContent()` rồi tạo metadata bằng cách đếm danh sách hiện tại.

Không tính `totalElements` bằng `items.size()`: đó chỉ là số phần tử trong trang hiện tại. Tương tự, không suy ra `hasNext` bằng cách so sánh `items.size()` với kích thước trang sau khi đã map nếu đã có metadata từ Slice.

## 9. Tổ chức service và controller cho Page

Repository có thể trả Page entity:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {
    Page<Product> findPageByStatus(ProductStatus status, Pageable pageable);
}
~~~

Service chịu trách nhiệm truy vấn và có thể chuyển entity sang DTO:

~~~java
public Page<ProductResponse> findPage(
        ProductStatus status,
        Pageable pageable) {

    return productRepository
        .findPageByStatus(status, pageable)
        .map(ProductResponse::from);
}
~~~

Controller chuyển Page DTO thành response DTO do ứng dụng sở hữu:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/page")
    public ProductPageResponse findPage(
            @ParameterObject
            @PageableDefault(
                size = 20,
                sort = "createdAt",
                direction = Sort.Direction.DESC
            )
            Pageable pageable) {

        Page<ProductResponse> result =
            productService.findPage(ProductStatus.ACTIVE, pageable);

        return toPageResponse(result);
    }
}
~~~

Trong ví dụ này, repository/service sở hữu truy vấn; controller công bố DTO công khai. DTO response không để lộ `PageImpl`, `Pageable` hoặc cấu trúc nội bộ của Spring Data.

## 10. Tổ chức service và controller cho Slice

Nếu màn hình chỉ cần tải tiếp, khai báo repository trả Slice:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {
    Slice<Product> findSliceByStatus(ProductStatus status, Pageable pageable);
}
~~~

Service:

~~~java
public Slice<ProductResponse> findSlice(
        ProductStatus status,
        Pageable pageable) {

    return productRepository
        .findSliceByStatus(status, pageable)
        .map(ProductResponse::from);
}
~~~

Controller:

~~~java
@GetMapping("/feed")
public ProductSliceResponse feed(
        @ParameterObject
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        )
        Pageable pageable) {

    Slice<ProductResponse> result =
        productService.findSlice(ProductStatus.ACTIVE, pageable);

    return toSliceResponse(result);
}
~~~

API này trả metadata `hasNext` và `hasPrevious` trong `slice`, không trả `totalElements` hoặc `totalPages`. Client có thể gửi page tiếp theo sau khi nhận response hiện tại. Nếu server giới hạn size, DTO cần phản ánh kích thước đã áp dụng.

### Không đổi Page thành Slice sau khi truy vấn

Nếu repository đã truy vấn Page và thực hiện count query, sau đó controller bỏ total metadata để trả Slice DTO thì chi phí count đã phát sinh. Muốn tránh count, hãy khai báo phương thức repository trả `Slice<T>` ngay từ đầu. Chỉ thay đổi DTO response không thay đổi chiến lược truy vấn của repository.

## 11. Công bố Pageable thành query parameters

Spring Data thường nhận phân trang qua query parameters:

~~~http
GET /api/products/page?page=0&size=20&sort=createdAt,desc
~~~

| Parameter | Ý nghĩa | Giá trị ví dụ |
|---|---|---|
| `page` | Chỉ số trang bắt đầu từ 0 | `0` |
| `size` | Số phần tử tối đa trong trang | `20` |
| `sort` | Tên thuộc tính và hướng sắp xếp | `createdAt,desc` |

Có thể lặp `sort` để sắp xếp theo nhiều tiêu chí:

~~~http
GET /api/products/page?page=0&size=20&sort=createdAt,desc&sort=name,asc
~~~

Springdoc cung cấp `@ParameterObject` để mở rộng object Pageable thành các query parameter trong OpenAPI:

~~~java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;

@GetMapping("/page")
public ProductPageResponse findPage(
        @ParameterObject
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        )
        Pageable pageable) {
    // ...
}
~~~

`@PageableDefault` đặt giá trị mặc định khi client không gửi parameter. `@ParameterObject` giúp tài liệu thể hiện các trường của Pageable thay vì một parameter object không rõ cấu trúc. Import trên áp dụng cho các phiên bản springdoc hiện đại; hãy dùng đúng package theo dependency của dự án.

### Mô tả tham số tường minh

Nếu không muốn tài liệu phụ thuộc vào cách springdoc suy luận Pageable, có thể công bố các parameter rõ ràng:

~~~yaml
parameters:
  - name: page
    in: query
    description: Chỉ số trang, bắt đầu từ 0
    schema:
      type: integer
      minimum: 0
      default: 0
  - name: size
    in: query
    description: Số phần tử tối đa trong một trang
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
  - name: sort
    in: query
    description: Có thể lặp tham số để khai báo nhiều tiêu chí sắp xếp
    style: form
    explode: true
    schema:
      type: array
      items:
        type: string
    example:
      - createdAt,desc
      - name,asc
~~~

Với `style: form` và `explode: true`, mỗi tiêu chí sort được gửi bằng một query parameter lặp lại. Cách mô tả phải khớp với cách Spring Data nhận request thực tế.

## 12. Thiết kế schema OpenAPI cho Page DTO

Schema của Page response có thể được mô tả bằng components:

~~~yaml
components:
  schemas:
    ProductResponse:
      type: object
      required:
        - id
        - name
      properties:
        id:
          type: integer
          format: int64
          example: 42
        name:
          type: string
          example: Bàn phím cơ
        price:
          type: number
          example: 1250000
    PageMetadata:
      type: object
      required:
        - number
        - size
        - totalElements
        - totalPages
      properties:
        number:
          type: integer
          minimum: 0
          example: 0
        size:
          type: integer
          minimum: 1
          example: 20
        numberOfElements:
          type: integer
          example: 20
        totalElements:
          type: integer
          format: int64
          example: 57
        totalPages:
          type: integer
          example: 3
        first:
          type: boolean
        last:
          type: boolean
        empty:
          type: boolean
    ProductPageResponse:
      type: object
      required:
        - items
        - page
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/ProductResponse'
        page:
          $ref: '#/components/schemas/PageMetadata'
~~~

Operation tham chiếu response:

~~~yaml
paths:
  /api/products/page:
    get:
      summary: Lấy sản phẩm theo trang
      parameters:
        - name: page
          in: query
          schema:
            type: integer
            minimum: 0
            default: 0
        - name: size
          in: query
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
      responses:
        '200':
          description: Trang sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductPageResponse'
~~~

Không cần công bố toàn bộ thuộc tính của Page nếu DTO chỉ chứa một phần metadata. OpenAPI cần mô tả chính xác những gì JSON thực sự trả về.

## 13. Thiết kế schema OpenAPI cho Slice DTO

Slice response không có total count. Schema nên thể hiện rõ các thuộc tính điều hướng:

~~~yaml
components:
  schemas:
    SliceMetadata:
      type: object
      required:
        - number
        - size
        - hasNext
        - hasPrevious
      properties:
        number:
          type: integer
          minimum: 0
        size:
          type: integer
          minimum: 1
        numberOfElements:
          type: integer
        first:
          type: boolean
        last:
          type: boolean
        hasNext:
          type: boolean
        hasPrevious:
          type: boolean
        empty:
          type: boolean
    ProductSliceResponse:
      type: object
      required:
        - items
        - slice
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/ProductResponse'
        slice:
          $ref: '#/components/schemas/SliceMetadata'
~~~

Operation:

~~~yaml
paths:
  /api/products/feed:
    get:
      summary: Lấy lát sản phẩm tiếp theo
      responses:
        '200':
          description: Lát sản phẩm cùng trạng thái điều hướng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductSliceResponse'
~~~

Đừng thêm `totalElements: 0` hoặc `totalPages: 0` vào SliceMetadata chỉ để hai DTO giống nhau. `0` là một giá trị tổng đã biết, trong khi Slice không tính tổng. Nếu muốn tái sử dụng schema, chỉ chia sẻ phần metadata thực sự có cùng semantics; không ép các trường không tồn tại vào hợp đồng.

## 14. Annotation springdoc cho DTO phân trang

Với DTO Java, springdoc thường suy luận object, array và property từ kiểu record/class:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "PageMetadata", description = "Thông tin tổng hợp của trang")
public record PageMetadata(
    @Schema(description = "Chỉ số trang bắt đầu từ 0", example = "0")
    int number,
    @Schema(description = "Kích thước trang hiệu lực", example = "20")
    int size,
    int numberOfElements,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last,
    boolean empty
) {}

@Schema(name = "ProductPageResponse")
public record ProductPageResponse(
    List<ProductResponse> items,
    PageMetadata page
) {}
~~~

Controller có thể mô tả response tường minh:

~~~java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/page")
@ApiResponse(
    responseCode = "200",
    description = "Trang sản phẩm",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductPageResponse.class)
    )
)
public ProductPageResponse findPage(
        @ParameterObject Pageable pageable) {
    // ...
}
~~~

Các annotation này tạo metadata tài liệu. Chúng không chuyển Page thành DTO và không thực hiện phân trang. Việc ánh xạ phải diễn ra trong service hoặc controller trước khi trả response.

Nếu DTO generic như `PageResponse<T>` được dùng cho nhiều kiểu phần tử, kiểm tra tên component và `$ref` do phiên bản springdoc/swagger-core sinh ra. Với hợp đồng công khai quan trọng, DTO cụ thể như ProductPageResponse và ProductSliceResponse thường tạo schema dễ hiểu và ổn định hơn.

## 15. Giới hạn page size và kiểm soát sort

Không nên cho client yêu cầu kích thước trang tùy ý. Request `size=1000000` có thể tạo truy vấn nặng, chiếm bộ nhớ và làm response quá lớn. Hãy quy định:

- Giá trị mặc định của size.
- Kích thước trang tối thiểu và tối đa.
- Cách xử lý page âm hoặc size bằng 0.
- Danh sách field sort được phép.
- Hướng sort mặc định.
- Có cho phép nhiều tiêu chí sort hay không.

Ví dụ chuẩn hóa giá trị:

~~~java
int effectivePage = Math.max(page, 0);
int effectiveSize = Math.min(Math.max(size, 1), 100);

Pageable pageable = PageRequest.of(
    effectivePage,
    effectiveSize,
    Sort.by(Sort.Direction.DESC, "createdAt")
);
~~~

Đoạn mã minh họa việc ép page không âm và size trong khoảng từ 1 đến 100. Một API khác có thể chọn trả lỗi 400 thay vì tự chuẩn hóa giá trị; điều quan trọng là hành vi phải nhất quán và được mô tả trong OpenAPI.

Nếu client được phép truyền sort, hãy ánh xạ tên trường public sang allowlist:

~~~java
private static final Set<String> ALLOWED_SORTS =
    Set.of("name", "createdAt", "price");

private Sort toSort(String field, String direction) {
    if (!ALLOWED_SORTS.contains(field)) {
        throw new IllegalArgumentException(
            "Trường sắp xếp không được hỗ trợ"
        );
    }

    Sort.Direction sortDirection = Sort.Direction.fromString(direction);
    return Sort.by(sortDirection, field);
}
~~~

Không nối trực tiếp chuỗi sort từ client vào SQL hoặc JPQL. Dùng Sort/Pageable của Spring Data cùng danh sách field được phép; nếu cần ánh xạ tên public sang tên thuộc tính nội bộ, thực hiện ở server.

Nếu controller dùng Bean Validation cho tham số method như `@Min` và `@Max`, hãy cấu hình method validation phù hợp với phiên bản Spring Boot, ví dụ đặt `@Validated` trên controller và khai báo constraint trên tham số. Dù dùng validation hay chuẩn hóa giá trị, tài liệu cần phản ánh đúng hành vi khi page/size không hợp lệ hoặc vượt giới hạn.

## 16. Trang rỗng, trang cuối và dữ liệu thay đổi

Các trường hợp biên cần được định nghĩa rõ:

| Trường hợp | Page response | Slice response |
|---|---|---|
| Có kết quả ở trang đầu | `200`, `first=true` | `200`, `first=true` |
| Trang giữa | `200`, `first=false`, `last=false` | `200`, `hasNext=true` nếu còn dữ liệu |
| Trang cuối | `200`, `last=true` | `200`, `hasNext=false`, `last=true` |
| Không có bản ghi phù hợp | `items=[]`, `totalElements=0`, `totalPages=0` | `items=[]`, `empty=true`, `hasNext=false` |
| Trang yêu cầu vượt quá trang cuối | Thường trả `200` với `items=[]` và total của truy vấn | Thường trả `200` với `items=[]`, `hasNext=false` |

Với collection endpoint, trả trang rỗng thường dễ xử lý hơn trả 404, vì collection endpoint vẫn tồn tại dù không có phần tử ở vị trí được yêu cầu. API có thể chọn chính sách khác cho page vượt phạm vi, nhưng cần nhất quán và mô tả rõ.

### Page size và số phần tử thực tế

`size` là kích thước trang hiệu lực; `numberOfElements` là số phần tử thực tế trong trang. Trang cuối có thể chỉ có vài phần tử dù size là 20. Không gán `size = numberOfElements`, vì hai trường có ý nghĩa khác nhau.

### Sắp xếp ổn định

Khi phân trang offset, hãy dùng thứ tự sắp xếp xác định. Nếu nhiều bản ghi có cùng `createdAt`, hãy thêm khóa duy nhất như `id` làm tiêu chí phụ. Nếu không, bản ghi có thể đổi vị trí giữa các trang khi cơ sở dữ liệu trả về các hàng đồng hạng theo thứ tự không xác định.

Ví dụ:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
Pageable pageable = PageRequest.of(page, size, sort);
~~~

### Dữ liệu thay đổi giữa các request

Với offset pagination, nếu bản ghi mới được thêm hoặc xóa trước vị trí offset hiện tại, client có thể thấy phần tử trùng hoặc bỏ sót khi chuyển trang. Đây là đặc tính của phân trang theo vị trí trong một tập dữ liệu đang thay đổi. Nếu cần duyệt ổn định một luồng dữ liệu lớn, hãy cân nhắc cursor pagination hoặc snapshot semantics.

## 17. Page, Slice và cursor pagination

Page và Slice của Spring Data thường dùng page number cùng offset. Cursor pagination là một mô hình khác: client gửi con trỏ do server cấp để tiếp tục từ vị trí trước đó.

Ví dụ response cursor:

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Bàn phím cơ"
    }
  ],
  "continuation": {
    "nextCursor": "eyJjcmVhdGVkQXQiOiIyMDI2LTExLTIwIn0",
    "hasNext": true
  }
}
~~~

Request tiếp theo:

~~~http
GET /api/products/feed?cursor=eyJjcmVhdGVkQXQiOiIyMDI2LTExLTIwIn0&limit=20
~~~

Cursor nên được tạo và xác thực ở server, không nên để client tự chỉnh sửa offset hoặc khóa nội bộ. Với cursor pagination, thường không cần `totalElements` hay `totalPages`; việc tính tổng có thể tốn kém và không cần thiết cho luồng cuộn vô hạn.

| Tiêu chí | Page | Slice | Cursor |
|---|---|---|---|
| Vị trí | Page number/offset | Page number/offset | Token tiếp tục |
| Tổng số | Có | Không | Thường không |
| Biết còn dữ liệu | Có | Có | Có qua continuation metadata |
| Nhảy đến trang bất kỳ | Có thể | Không có tổng để hỗ trợ đầy đủ | Thường không |
| Dữ liệu thay đổi liên tục | Có thể dịch chuyển phần tử | Có thể dịch chuyển phần tử | Ổn định hơn nếu cursor dựa trên khóa sắp xếp phù hợp |
| Trường hợp phù hợp | Bảng dữ liệu cần tổng số | Tải thêm theo trang | Feed lớn, cuộn vô hạn |

Đừng dùng tên `page` cho cursor nếu semantics thực tế là token tiếp tục. Đặt tên `cursor` và `limit` giúp client hiểu cách điều hướng.

## 18. Kiểm thử mapper và response DTO

Nên kiểm thử mapper riêng để bảo đảm metadata được chuyển chính xác. Ví dụ với Page:

~~~java
@Test
void mapsPageMetadataWithoutLosingTotalCount() {
    Pageable pageable = PageRequest.of(0, 20);
    Page<ProductResponse> source = new PageImpl<>(
        List.of(new ProductResponse(42L, "Bàn phím cơ", new BigDecimal("1250000"))),
        pageable,
        57
    );

    ProductPageResponse response = mapper.toPageResponse(source);

    assertEquals(0, response.page().number());
    assertEquals(20, response.page().size());
    assertEquals(1, response.page().numberOfElements());
    assertEquals(57, response.page().totalElements());
    assertEquals(3, response.page().totalPages());
    assertTrue(response.page().first());
    assertFalse(response.page().last());
}
~~~

Với Slice:

~~~java
@Test
void mapsSliceNavigationWithoutInventingTotals() {
    Pageable pageable = PageRequest.of(0, 20);
    Slice<ProductResponse> source = new SliceImpl<>(
        List.of(new ProductResponse(42L, "Bàn phím cơ", new BigDecimal("1250000"))),
        pageable,
        true
    );

    ProductSliceResponse response = mapper.toSliceResponse(source);

    assertEquals(0, response.slice().number());
    assertEquals(20, response.slice().size());
    assertTrue(response.slice().hasNext());
    assertFalse(response.slice().hasPrevious());
    assertFalse(response.slice().last());
}
~~~

Các test trên giả định có mapper cùng DTO như phần trước. `PageImpl` và `SliceImpl` hữu ích trong unit test để tạo dữ liệu mẫu; chúng không phải kiểu response công khai của API.

## 19. Kiểm thử endpoint và schema OpenAPI

MockMvc có thể xác minh response DTO của endpoint Page:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    ProductService productService;

    @Test
    void returnsApplicationOwnedPageResponse() throws Exception {
        Page<ProductResponse> page = new PageImpl<>(
            List.of(new ProductResponse(
                42L, "Bàn phím cơ", new BigDecimal("1250000")
            )),
            PageRequest.of(0, 20),
            57
        );
        given(productService.findPage(any(), any(Pageable.class)))
            .willReturn(page);

        mockMvc.perform(get("/api/products/page")
                .param("page", "0")
                .param("size", "20"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(42))
            .andExpect(jsonPath("$.page.totalElements").value(57))
            .andExpect(jsonPath("$.page.totalPages").value(3));
    }
}
~~~

Trong ví dụ, service trả Page<ProductResponse> như phần controller ở trên; controller gọi mapper để tạo ProductPageResponse trước khi serialize. Nếu dự án đặt mapper ở service, hãy điều chỉnh kiểu trả về và mock theo đúng ranh giới đã chọn.

Có thể kiểm tra schema OpenAPI:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.ProductPageResponse.properties.items.type"
    ).value("array"))
    .andExpect(jsonPath(
        "$.components.schemas.ProductPageResponse.properties.page['$ref']"
    ).exists())
    .andExpect(jsonPath(
        "$.components.schemas.PageMetadata.properties.totalElements.type"
    ).value("integer"));
~~~

Với Slice, kiểm tra `ProductSliceResponse` có `items` là array và `slice.hasNext` là boolean; schema không nên có `totalElements` hoặc `totalPages`. Nếu springdoc đặt tên component khác do cấu hình, hãy lần theo `$ref` thực tế trong `/v3/api-docs` và cập nhật JSONPath.

## 20. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Slice DTO vẫn có total count | Tái sử dụng PageMetadata hoặc lấy Page rồi bỏ trường | Dùng Slice repository method và SliceMetadata riêng |
| Dùng Page nhưng tổng số không đúng | Count query không áp dụng cùng filter hoặc mapping metadata sai | Kiểm tra điều kiện truy vấn và nguồn total |
| Client không biết còn trang tiếp theo | Response Slice thiếu hasNext | Công bố hasNext/hasPrevious trong SliceMetadata |
| Response công khai thay đổi sau khi nâng Spring Data | Serialize trực tiếp PageImpl/SliceImpl | Chuyển sang DTO do ứng dụng sở hữu |
| Tổng số phần tử bằng số phần tử trong trang | Gán totalElements từ items.size() | Dùng Page.getTotalElements() |
| Count query làm endpoint chậm | Client không cần tổng số nhưng repository trả Page | Đổi repository method sang Slice nếu phù hợp UX |
| Slice không tránh được truy vấn nặng | Join, sort hoặc offset lớn vẫn tốn chi phí | Tối ưu query, index, sort và cân nhắc cursor |
| Page size quá lớn | Không có giới hạn ở server | Đặt default, maximum và validation |
| Sort làm lộ field nội bộ | Cho client truyền tên thuộc tính tùy ý | Dùng allowlist và ánh xạ tên public |
| Các trang có phần tử trùng hoặc thiếu | Thứ tự sort không ổn định hoặc dữ liệu thay đổi | Thêm khóa duy nhất làm tiêu chí sort phụ; cân nhắc cursor |
| Schema thiếu Page metadata | springdoc không nhận diện DTO hoặc response annotation sai | Kiểm tra kiểu return, component và `$ref` trong `/v3/api-docs` |

## 21. Nguyên tắc thiết kế hợp đồng phân trang

Khi công bố Page hoặc Slice qua API, hãy áp dụng các nguyên tắc:

1. Chọn Page khi client cần total count; chọn Slice khi chỉ cần biết còn dữ liệu tiếp theo.
2. Chuyển kết quả Spring Data sang DTO công khai trước khi serialize.
3. Dùng PageMetadata và SliceMetadata riêng để không gán ý nghĩa sai cho total fields.
4. Dùng `Page.map()` hoặc `Slice.map()` để chuyển entity sang DTO mà giữ metadata.
5. Công bố page, size và sort với default, giới hạn và semantics rõ ràng.
6. Giới hạn size và chỉ cho phép sort theo các field public được hỗ trợ.
7. Dùng thứ tự sắp xếp xác định, thường thêm khóa duy nhất làm tiêu chí phụ.
8. Mô tả response DTO bằng schema OpenAPI cụ thể và kiểm tra `$ref`.
9. Kiểm thử cả JSON runtime lẫn OpenAPI JSON.
10. Đánh giá thay đổi cấu trúc response như thay đổi hợp đồng cần kiểm tra tương thích.

## 22. Bài thực hành tổng hợp

Xây dựng API tìm kiếm sản phẩm có hai cách điều hướng:

1. Tạo repository method trả `Page<Product>` cho màn hình quản trị cần tổng số.
2. Tạo repository method trả `Slice<Product>` cho feed chỉ cần tải tiếp.
3. Chuyển entity sang ProductResponse bằng `Page.map()` và `Slice.map()`.
4. Tạo ProductPageResponse cùng PageMetadata cho endpoint Page.
5. Tạo ProductSliceResponse cùng SliceMetadata cho endpoint Slice.
6. Viết mapper bảo toàn total count của Page và hasNext/hasPrevious của Slice.
7. Dùng `@ParameterObject` và `@PageableDefault` để mô tả Pageable, hoặc khai báo page/size/sort tường minh.
8. Giới hạn size tối đa và allowlist các field sort.
9. Dùng springdoc để sinh schema cho cả hai response DTO.
10. Viết unit test cho mapper với PageImpl và SliceImpl.
11. Viết MockMvc test cho trang đầu, trang cuối, trang rỗng và schema OpenAPI.
12. Quan sát SQL/log truy vấn để xác nhận Page có thể cần count query trong khi Slice không yêu cầu tổng số.
13. So sánh UX cần tổng số với UX chỉ cần tải tiếp và giải thích lựa chọn Page/Slice.

### Tiêu chí hoàn thành

- [ ] Page response có items cùng totalElements và totalPages chính xác.
- [ ] Slice response có items cùng hasNext/hasPrevious và không giả lập total count.
- [ ] DTO công khai không phụ thuộc cấu trúc serialize của PageImpl/SliceImpl.
- [ ] Mapping entity sang DTO giữ nguyên metadata phân trang.
- [ ] Query parameters page, size và sort được mô tả đúng trong OpenAPI.
- [ ] Server giới hạn page size và sort theo allowlist.
- [ ] Schema OpenAPI mô tả đúng ProductPageResponse và ProductSliceResponse.
- [ ] Test xác minh mapper, JSON response và schema được sinh.
- [ ] Lựa chọn Page/Slice có lý do dựa trên nhu cầu client và chi phí truy vấn.

## Tiếp tục học

Sau bài này, hãy kết hợp Page/Slice DTO với lọc dữ liệu, sắp xếp, cursor pagination và chuẩn hóa response lỗi. Khi thay đổi từ Page sang Slice hoặc đổi tên metadata, hãy đánh giá tác động đến client, cập nhật OpenAPI và kiểm thử hợp đồng trước khi phát hành.
