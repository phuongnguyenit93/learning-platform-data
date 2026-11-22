# Phản hồi mảng, lớp bao dữ liệu và cấu trúc phân trang

Một endpoint đọc dữ liệu có thể trả về một đối tượng, một mảng đối tượng hoặc một trang kết quả gồm dữ liệu và thông tin phân trang. Ba dạng response này có ý nghĩa khác nhau đối với client. Một mảng chỉ biểu diễn tập phần tử; một lớp bao dữ liệu có thể bổ sung trạng thái hoặc thông điệp chung; còn response phân trang cần cho biết vị trí hiện tại, kích thước trang và tổng số kết quả.

Trong Spring Boot, controller thường trả về `List<T>`, DTO wrapper hoặc kết quả từ Spring Data. springdoc-openapi phân tích kiểu trả về để tạo schema OpenAPI, giúp Swagger UI và client generator hiểu cấu trúc response. Bài học này hướng dẫn thiết kế các dạng response đó sao cho rõ ràng, ổn định và dễ kiểm thử.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt response object, array, wrapper và page.
- Mô tả mảng trong OpenAPI bằng `type: array` và `items`.
- Dùng `List<T>` hoặc DTO chuyên biệt trong controller Spring MVC.
- Thiết kế lớp bao dữ liệu generic và biết khi nào nên dùng envelope.
- Thiết kế DTO phân trang ổn định thay vì phụ thuộc trực tiếp vào cấu trúc nội bộ của thư viện.
- Mô tả query parameter `page`, `size`, `sort` và schema metadata phân trang.
- Dùng springdoc-openapi để kiểm tra response array, wrapper và page được sinh đúng.
- Kiểm thử trường hợp rỗng, nhiều trang, trang cuối và dữ liệu lớn.

## 1. Phân biệt object, array, wrapper và page

Giả sử API quản lý sản phẩm có thể trả về các dạng sau:

**Một sản phẩm:**

~~~json
{
  "id": 42,
  "name": "Bàn phím cơ",
  "price": 1250000
}
~~~

**Danh sách sản phẩm:**

~~~json
[
  {
    "id": 42,
    "name": "Bàn phím cơ",
    "price": 1250000
  },
  {
    "id": 43,
    "name": "Chuột không dây",
    "price": 650000
  }
]
~~~

**Lớp bao dữ liệu:**

~~~json
{
  "data": [
    {
      "id": 42,
      "name": "Bàn phím cơ",
      "price": 1250000
    }
  ],
  "message": "Lấy dữ liệu thành công"
}
~~~

**Trang kết quả:**

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Bàn phím cơ",
      "price": 1250000
    }
  ],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 57,
    "totalPages": 3,
    "numberOfElements": 1,
    "first": true,
    "last": false
  }
}
~~~

| Dạng response | Cấu trúc gốc | Phù hợp với |
|---|---|---|
| Object | Một object JSON | Lấy chi tiết một tài nguyên |
| Array | Một mảng JSON | Danh sách nhỏ, không cần metadata trang |
| Wrapper | Object chứa data và metadata chung | API có envelope thống nhất |
| Page | Object chứa một phần dữ liệu và metadata phân trang | Tập dữ liệu lớn, cần tải theo từng trang |

Đừng bọc mọi response vào một lớp envelope chỉ vì muốn có cùng hình dạng. Hãy chọn cấu trúc giúp client hiểu dữ liệu và cách điều hướng kết quả. Nếu một endpoint trả mảng rỗng, thông thường nên trả `200 OK` cùng `[]`; `204 No Content` có nghĩa response không có body và là một hợp đồng khác.

## 2. Mảng trong JSON và OpenAPI

Trong JSON, mảng được đặt trong dấu ngoặc vuông. Các phần tử trong một mảng thường cùng tuân theo một schema:

~~~json
[
  "spring",
  "java",
  "openapi"
]
~~~

OpenAPI mô tả mảng bằng `type: array`; `items` định nghĩa kiểu của từng phần tử:

~~~yaml
type: array
items:
  type: string
~~~

Mảng các object tham chiếu schema dùng chung:

~~~yaml
type: array
items:
  $ref: '#/components/schemas/ProductResponse'
~~~

Ví dụ khai báo schema:

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
    ProductList:
      type: array
      items:
        $ref: '#/components/schemas/ProductResponse'
~~~

Khi schema phần tử thay đổi, mọi nơi tham chiếu đến ProductResponse đều dùng cùng định nghĩa. Không nên mô tả mảng chỉ bằng `type: array` mà bỏ `items`; client khi đó không biết phần tử là string, number hay object nào.

### Các ràng buộc của mảng

OpenAPI có thể mô tả giới hạn số phần tử và tính duy nhất:

~~~yaml
type: array
minItems: 1
maxItems: 100
uniqueItems: true
items:
  type: integer
  format: int64
~~~

- `minItems`: số phần tử tối thiểu.
- `maxItems`: số phần tử tối đa.
- `uniqueItems: true`: các phần tử không được trùng nhau theo cách so sánh của schema.
- `items`: schema của mỗi phần tử.

Chỉ khai báo giới hạn nếu server thực sự kiểm tra hoặc bảo đảm giới hạn đó. Nếu OpenAPI nói tối đa 100 phần tử nhưng endpoint vẫn nhận 500 phần tử, hợp đồng đang không phản ánh hành vi runtime.

## 3. Trả List<T> từ Spring Boot

Spring MVC có thể serialize một `List<ProductResponse>` thành JSON array:

~~~java
public record ProductResponse(
    Long id,
    String name,
    BigDecimal price
) {}

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    public List<ProductResponse> list() {
        return productService.findAll();
    }
}
~~~

Nếu service trả danh sách rỗng, response thông thường là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[]
~~~

springdoc thường suy luận kiểu phần tử từ generic return type và tạo schema dạng array với `items` tham chiếu đến ProductResponse. Bạn không cần tự khai báo `type: array` trong mọi controller nếu kiểu Java đã rõ và output được sinh chính xác.

### Khi cần mô tả array tường minh

Nếu kiểu trả về phức tạp hoặc công cụ suy luận chưa đúng, có thể dùng `@ApiResponse`, `@Content` và `@ArraySchema`:

~~~java
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@GetMapping
@ApiResponse(
    responseCode = "200",
    description = "Danh sách sản phẩm",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = ProductResponse.class)
        )
    )
)
public List<ProductResponse> list() {
    return productService.findAll();
}
~~~

`@ArraySchema` mô tả schema của mảng; `@Schema(implementation = ProductResponse.class)` mô tả mỗi phần tử. Không dùng `@Schema(implementation = ProductResponse.class)` đơn lẻ nếu response thực tế là một mảng, vì như vậy có thể khiến tài liệu mô tả một object thay vì array.

### ResponseEntity<List<T>>

Khi cần điều khiển status hoặc header, có thể bọc danh sách bằng ResponseEntity:

~~~java
@GetMapping
public ResponseEntity<List<ProductResponse>> list() {
    List<ProductResponse> products = productService.findAll();
    return ResponseEntity.ok(products);
}
~~~

`ResponseEntity` không làm thay đổi cấu trúc body: JSON vẫn là array. springdoc phân tích kiểu body bên trong ResponseEntity để tạo response schema.

## 4. Mảng lồng nhau và mảng kiểu dữ liệu khác

Mảng có thể chứa object lồng nhau:

~~~java
public record ProductGroupResponse(
    String category,
    List<ProductResponse> products
) {}
~~~

OpenAPI tương ứng:

~~~yaml
ProductGroupResponse:
  type: object
  properties:
    category:
      type: string
    products:
      type: array
      items:
        $ref: '#/components/schemas/ProductResponse'
~~~

Mảng cũng có thể chứa enum:

~~~java
public enum ProductStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}

public record ProductStatusResponse(
    List<ProductStatus> statuses
) {}
~~~

Schema phần tử enum có thể được biểu diễn dưới dạng string với tập giá trị cho phép. Với mảng số, ngày giờ hoặc kiểu value object, hãy kiểm tra `type`, `format` và schema tham chiếu trong tài liệu.

### Mảng rỗng, null và trường bị thiếu

Ba trạng thái này không giống nhau:

- `[]`: mảng tồn tại nhưng không có phần tử.
- `null`: giá trị mảng là null.
- Không có property: trường không xuất hiện trong object cha.

Client có thể xử lý ba trường hợp theo cách khác nhau. Với danh sách kết quả, nên ưu tiên trả `[]` khi không có phần tử. Nếu property có thể null hoặc vắng mặt, hãy mô tả rõ trong schema và bảo đảm serializer cùng validation phản ánh quy ước đó.

## 5. Lớp bao dữ liệu (response envelope)

Một envelope là object bao quanh dữ liệu chính và metadata chung. Ví dụ:

~~~java
public record ApiResponse<T>(
    T data,
    String message
) {}
~~~

Controller có thể trả:

~~~java
@GetMapping("/{id}")
public ApiResponse<ProductResponse> getById(@PathVariable Long id) {
    ProductResponse product = productService.getById(id);
    return new ApiResponse<>(product, "Lấy sản phẩm thành công");
}
~~~

Với danh sách:

~~~java
@GetMapping
public ApiResponse<List<ProductResponse>> list() {
    return new ApiResponse<>(
        productService.findAll(),
        "Lấy danh sách sản phẩm thành công"
    );
}
~~~

Trong trường hợp thứ hai, body là object có property `data`, và `data` là array. Đây không phải response array trực tiếp. Client cần truy cập `response.data` rồi mới lặp qua các phần tử.

### Khi nào nên dùng envelope?

Envelope có ích khi API cần một quy ước thống nhất cho metadata như request ID, thông điệp hiển thị hoặc dữ liệu chính. Nhưng hãy cân nhắc:

- Nếu metadata không mang thêm giá trị, envelope làm response dài hơn và tăng một lớp truy cập cho client.
- Nếu lỗi dùng một cấu trúc khác, hãy mô tả riêng response lỗi thay vì ép mọi trường hợp vào cùng envelope.
- Nếu dùng HTTP status code để biểu đạt thành công/thất bại, không nên chỉ trả `200` rồi dùng một trường `success` để thay thế semantics HTTP.
- Nếu API đã phát hành dạng array trực tiếp, đổi sang envelope là thay đổi hợp đồng có thể phá vỡ client.

Không có quy tắc bắt buộc mọi endpoint phải dùng envelope. Hãy chọn một quy ước ở cấp API và áp dụng nhất quán.

## 6. Schema generic cho envelope

OpenAPI có thể biểu diễn một schema wrapper chứa property `data`. Nếu `data` là ProductResponse:

~~~yaml
ApiResponseProduct:
  type: object
  properties:
    data:
      $ref: '#/components/schemas/ProductResponse'
    message:
      type: string
~~~

Nếu `data` là mảng:

~~~yaml
ApiResponseProductList:
  type: object
  properties:
    data:
      type: array
      items:
        $ref: '#/components/schemas/ProductResponse'
    message:
      type: string
~~~

Một lớp Java generic `ApiResponse<T>` giúp tái sử dụng code, nhưng tên component cụ thể do springdoc/swagger-core sinh có thể khác theo phiên bản và cách cấu hình. Hãy kiểm tra `/v3/api-docs` để biết schema được đặt tên thế nào và generic `T` đã được thay bằng kiểu thực tế hay chưa.

### Generic type trong controller

Khai báo return type đầy đủ giúp công cụ suy luận:

~~~java
@GetMapping("/{id}")
public ApiResponse<ProductResponse> getById(@PathVariable Long id) {
    return new ApiResponse<>(productService.getById(id), "OK");
}
~~~

Tránh khai báo return type thô như `ApiResponse` hoặc `ResponseEntity` không có generic. Khi mất thông tin kiểu, springdoc khó xác định schema của `data`, và client generator có thể chỉ tạo một object không có kiểu cụ thể.

Nếu công cụ không tạo schema generic đúng như mong muốn, có thể định nghĩa DTO cụ thể cho các response quan trọng:

~~~java
public record ProductResponseEnvelope(
    ProductResponse data,
    String message
) {}

public record ProductListEnvelope(
    List<ProductResponse> data,
    String message
) {}
~~~

DTO cụ thể tạo tên component rõ ràng và dễ kiểm soát hơn, đổi lại có thêm một số lớp Java.

## 7. Vì sao không nên trả trực tiếp PageImpl?

Spring Data cung cấp `Page<T>` để biểu diễn một lát dữ liệu cùng metadata phân trang. Một controller có thể trả trực tiếp:

~~~java
@GetMapping
public Page<ProductResponse> search(Pageable pageable) {
    return productService.search(pageable);
}
~~~

Cách này thuận tiện cho ứng dụng nội bộ, nhưng JSON serialize của các kiểu triển khai như PageImpl có thể phản ánh chi tiết cấu trúc thư viện. Khi phiên bản Spring Data thay đổi, hình dạng JSON có thể thay đổi theo. Điều đó khiến client phụ thuộc vào implementation detail thay vì hợp đồng do API chủ động thiết kế.

Spring Data cũng cảnh báo việc serialize trực tiếp implementation của Page không phải định dạng ổn định cho API công khai. Ở các phiên bản Spring Data hiện đại, có thể dùng chế độ DTO hóa của cơ chế web support để tạo dạng ổn định hơn; tuy nhiên, một DTO response riêng vẫn cho phép kiểm soát chính xác tên field, nội dung metadata và tương thích hợp đồng.

Hãy xem `Page<T>` là kiểu kết quả tiện ích ở tầng service/repository. Ở ranh giới API, chuyển kết quả đó sang DTO công khai có cấu trúc do dự án quản lý.

## 8. Thiết kế DTO phân trang

Một cấu trúc page response có thể gồm danh sách phần tử và metadata:

~~~java
public record PageMetadata(
    int number,
    int size,
    long totalElements,
    int totalPages,
    int numberOfElements,
    boolean first,
    boolean last,
    boolean empty
) {}

public record PageResponse<T>(
    List<T> items,
    PageMetadata page
) {}
~~~

Ý nghĩa:

| Trường | Ý nghĩa |
|---|---|
| `items` | Các phần tử trong trang hiện tại |
| `number` | Chỉ số trang hiện tại, ví dụ trang đầu là 0 nếu theo quy ước Spring Data |
| `size` | Kích thước trang được yêu cầu hoặc kích thước trang hiệu lực theo hợp đồng |
| `totalElements` | Tổng số phần tử phù hợp với truy vấn |
| `totalPages` | Tổng số trang |
| `numberOfElements` | Số phần tử thực tế trong trang hiện tại |
| `first` | Có phải trang đầu tiên hay không |
| `last` | Có phải trang cuối cùng hay không |
| `empty` | Trang hiện tại không có phần tử |

Ví dụ response:

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Bàn phím cơ",
      "price": 1250000
    },
    {
      "id": 43,
      "name": "Chuột không dây",
      "price": 650000
    }
  ],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 57,
    "totalPages": 3,
    "numberOfElements": 2,
    "first": true,
    "last": false,
    "empty": false
  }
}
~~~

Metadata cần có định nghĩa nhất quán. Ví dụ, nếu client yêu cầu `size=1000` nhưng server giới hạn tối đa 100, response nên trả `size=100` để biểu diễn kích thước hiệu lực. `totalElements` phải là tổng kết quả sau khi áp dụng bộ lọc, không phải số phần tử trong trang hiện tại.

### Chuyển Page<T> thành PageResponse<T>

Service có thể trả `Page<ProductResponse>`, controller chuyển thành DTO:

~~~java
private PageResponse<ProductResponse> toPageResponse(
        Page<ProductResponse> result) {

    PageMetadata metadata = new PageMetadata(
        result.getNumber(),
        result.getSize(),
        result.getTotalElements(),
        result.getTotalPages(),
        result.getNumberOfElements(),
        result.isFirst(),
        result.isLast(),
        result.isEmpty()
    );

    return new PageResponse<>(result.getContent(), metadata);
}
~~~

Controller:

~~~java
@GetMapping
public PageResponse<ProductResponse> search(
        @ParameterObject Pageable pageable) {
    Page<ProductResponse> result = productService.search(pageable);
    return toPageResponse(result);
}
~~~

`@ParameterObject` của springdoc giúp biểu diễn các thuộc tính Pageable thành query parameters trong tài liệu. Cần import `org.springdoc.core.annotations.ParameterObject` ở các phiên bản springdoc hiện đại. Nếu phiên bản dự án không có annotation này hoặc cách suy luận khác, khai báo `page`, `size` và `sort` tường minh bằng `@Parameter`.

Trong controller thật, có thể đặt giới hạn `size` tối đa và danh sách trường `sort` được phép. Không cho phép client sắp xếp tùy ý theo tên cột nội bộ hoặc biểu thức chưa được kiểm soát.

## 9. Mô tả schema phân trang trong OpenAPI

Schema của một trang có hai lớp: mảng phần tử và metadata. Ví dụ:

~~~yaml
components:
  schemas:
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
          description: Chỉ số trang bắt đầu từ 0
          example: 0
        size:
          type: integer
          minimum: 1
          example: 20
        totalElements:
          type: integer
          format: int64
          example: 57
        totalPages:
          type: integer
          example: 3
        numberOfElements:
          type: integer
          example: 20
        first:
          type: boolean
          example: true
        last:
          type: boolean
          example: false
        empty:
          type: boolean
          example: false
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

Một operation dùng schema này:

~~~yaml
paths:
  /api/products:
    get:
      summary: Tìm kiếm sản phẩm theo trang
      responses:
        '200':
          description: Trang sản phẩm
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductPageResponse'
~~~

Nếu endpoint trả envelope ngoài page, schema sẽ có thêm một lớp:

~~~yaml
ProductSearchEnvelope:
  type: object
  properties:
    data:
      $ref: '#/components/schemas/ProductPageResponse'
    message:
      type: string
~~~

Hãy giữ đúng cấu trúc thực tế. Nếu controller trả trực tiếp ProductPageResponse, không khai báo thêm property `data`. Nếu controller trả ApiResponse<ProductPageResponse>, schema cần thể hiện `data` chứa page.

## 10. Query parameter cho phân trang và sắp xếp

Một API phân trang thường nhận:

| Parameter | Ý nghĩa | Ví dụ |
|---|---|---|
| `page` | Chỉ số trang | `page=0` |
| `size` | Số phần tử tối đa trong trang | `size=20` |
| `sort` | Trường và hướng sắp xếp | `sort=createdAt,desc` |

Spring Data Pageable dùng chỉ số trang bắt đầu từ 0 theo mặc định. Ví dụ `page=0&size=20` yêu cầu trang đầu tiên gồm tối đa 20 phần tử. Nếu API muốn dùng số trang bắt đầu từ 1 cho người dùng, cần chuyển đổi nhất quán giữa hợp đồng công khai và `PageRequest`; không để client phải đoán.

Một tham số sort có thể lặp lại để sắp xếp theo nhiều trường:

~~~text
GET /api/products?page=0&size=20&sort=createdAt,desc&sort=name,asc
~~~

Trong OpenAPI, có thể mô tả các tham số như sau:

~~~yaml
parameters:
  - name: page
    in: query
    required: false
    description: Chỉ số trang bắt đầu từ 0
    schema:
      type: integer
      minimum: 0
      default: 0
  - name: size
    in: query
    required: false
    description: Số phần tử tối đa trong một trang
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
  - name: sort
    in: query
    required: false
    description: Trường và hướng sắp xếp; có thể lặp tham số để tạo nhiều tiêu chí
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

Với `style: form` và `explode: true`, nhiều giá trị được biểu diễn bằng cách lặp key trong query string. Cách này phù hợp với cách Spring Data nhận nhiều tham số sort. Nếu API dùng cú pháp khác, hãy mô tả đúng cú pháp thực tế.

### Dùng @ParameterObject với Pageable

Springdoc có thể phân tích Pageable thành các query parameter:

~~~java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.domain.Sort;

@GetMapping
public ProductPageResponse search(
        @ParameterObject
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        )
        Pageable pageable) {

    Page<ProductResponse> result = productService.search(pageable);
    return toPageResponse(result);
}
~~~

`@PageableDefault` đặt giá trị mặc định cho Pageable; `@ParameterObject` yêu cầu springdoc mở rộng các thuộc tính của object thành parameter tài liệu. Kiểm tra `/v3/api-docs` để xác nhận page, size và sort có mô tả, default và giới hạn đúng. Nếu annotation không được nhận diện trong phiên bản đang dùng, khai báo các `@Parameter` riêng thay vì để tài liệu thiếu query parameter.

### Khai báo tham số tường minh

Khi muốn hợp đồng độc lập với kiểu Pageable, có thể khai báo tham số trực tiếp:

~~~java
@Operation(summary = "Tìm kiếm sản phẩm theo trang")
@Parameters({
    @Parameter(
        name = "page",
        in = ParameterIn.QUERY,
        description = "Chỉ số trang bắt đầu từ 0",
        schema = @Schema(type = "integer", defaultValue = "0", minimum = "0")
    ),
    @Parameter(
        name = "size",
        in = ParameterIn.QUERY,
        description = "Số phần tử tối đa trong trang",
        schema = @Schema(type = "integer", defaultValue = "20", minimum = "1", maximum = "100")
    )
})
~~~

Đây là phần metadata có thể đặt trên operation. Với tham số sort lặp lại, nên mô tả array và cách serialize rõ ràng trong OpenAPI YAML hoặc dùng annotation có đủ thuộc tính tương ứng.

Các import thường dùng cho đoạn annotation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Schema;
~~~

## 11. Giới hạn page size và kiểm soát sort

Không nên cho client yêu cầu kích thước trang tùy ý. Một request với `size=1000000` có thể tạo truy vấn nặng, chiếm bộ nhớ và làm response quá lớn. Hãy quy định:

- Giá trị mặc định của size.
- Kích thước trang tối thiểu và tối đa.
- Cách xử lý page âm hoặc size bằng 0.
- Danh sách field sort được phép.
- Hướng sort mặc định.
- Có cho phép nhiều tiêu chí sort hay không.

Ví dụ xử lý giới hạn:

~~~java
int effectivePage = Math.max(page, 0);
int effectiveSize = Math.min(Math.max(size, 1), 100);
Pageable pageable = PageRequest.of(
    effectivePage,
    effectiveSize,
    Sort.by(Sort.Direction.DESC, "createdAt")
);
~~~

Đoạn mã trên minh họa giới hạn page và size cùng sort mặc định. Nếu client được phép truyền sort, hãy ánh xạ tên trường public sang danh sách field hợp lệ:

~~~java
private static final Set<String> ALLOWED_SORTS =
    Set.of("name", "createdAt", "price");

private Sort toSort(String field, String direction) {
    if (!ALLOWED_SORTS.contains(field)) {
        throw new IllegalArgumentException("Trường sắp xếp không được hỗ trợ");
    }

    Sort.Direction sortDirection = Sort.Direction.fromString(direction);
    return Sort.by(sortDirection, field);
}
~~~

Không nối trực tiếp chuỗi sort từ client vào SQL hoặc JPQL. Dùng Sort/Pageable của Spring Data cùng danh sách field được phép; nếu cần ánh xạ tên public sang tên thuộc tính nội bộ, thực hiện ở server.

Nếu controller dùng Bean Validation cho tham số method như `@Min` và `@Max`, hãy cấu hình method validation phù hợp với phiên bản Spring Boot, ví dụ đặt `@Validated` trên controller và khai báo constraint trên tham số. Dù dùng validation hay chuẩn hóa giá trị, tài liệu cần phản ánh đúng hành vi khi page/size không hợp lệ hoặc vượt giới hạn.

## 12. Phân trang offset và cursor

Phân trang theo page/size thường là offset pagination. Client yêu cầu trang và kích thước; server bỏ qua số bản ghi tương ứng rồi lấy phần tiếp theo. Cách này dễ hiểu và phù hợp với nhiều màn hình quản trị, nhưng trang sâu có thể tốn chi phí truy vấn lớn. Khi dữ liệu thay đổi giữa hai lần gọi, phần tử có thể dịch chuyển khiến client thấy trùng hoặc bỏ sót nếu thứ tự không ổn định.

Cursor pagination dùng một con trỏ đại diện vị trí tiếp theo:

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Bàn phím cơ"
    }
  ],
  "page": {
    "nextCursor": "eyJpZCI6NDJ9",
    "hasNext": true
  }
}
~~~

Request tiếp theo có thể là:

~~~text
GET /api/products?cursor=eyJpZCI6NDJ9&limit=20
~~~

OpenAPI có thể mô tả cursor và limit như query parameters, còn response metadata chứa nextCursor và hasNext. Cursor nên được tạo và xác thực ở server, không nên để client tự chỉnh sửa offset hoặc khóa nội bộ. Với cursor pagination, thường không cần `totalElements` hay `totalPages`; việc tính tổng có thể tốn kém và không cần thiết cho luồng cuộn vô hạn.

| Tiêu chí | Offset/page | Cursor |
|---|---|---|
| Điều hướng | Theo số trang | Theo con trỏ tiếp theo/trước đó |
| Nhảy đến trang bất kỳ | Dễ hỗ trợ | Thường không thuận tiện |
| Dữ liệu thay đổi liên tục | Có thể dịch chuyển phần tử giữa trang | Ổn định hơn nếu cursor dựa trên khóa sắp xếp phù hợp |
| Tổng số phần tử | Thường có thể trả total | Có thể bỏ tổng để giảm chi phí |
| Trường hợp phù hợp | Trang quản trị, bảng dữ liệu | Feed lớn, cuộn vô hạn, dữ liệu thay đổi thường xuyên |

Hãy chọn mô hình phân trang dựa trên cách client điều hướng và chi phí truy vấn. Đừng dùng chung tên `page` cho cursor nếu semantics thực tế là một token tiếp tục.

## 13. Dùng springdoc mô tả array và wrapper

Với kiểu trả về rõ ràng, springdoc thường tự suy luận array và schema phần tử:

~~~java
@GetMapping
public List<ProductResponse> list() {
    return productService.findAll();
}
~~~

Nếu muốn công bố response array tường minh, dùng `@ArraySchema` trong `@Content`:

~~~java
@GetMapping
@ApiResponse(
    responseCode = "200",
    description = "Danh sách sản phẩm",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = ProductResponse.class)
        )
    )
)
public List<ProductResponse> list() {
    return productService.findAll();
}
~~~

Với wrapper cụ thể:

~~~java
@Schema(name = "ProductListEnvelope")
public record ProductListEnvelope(
    @ArraySchema(
        schema = @Schema(implementation = ProductResponse.class)
    )
    List<ProductResponse> data,
    String message
) {}
~~~

Với response phân trang:

~~~java
@Schema(name = "ProductPageResponse")
public record ProductPageResponse(
    @ArraySchema(
        schema = @Schema(implementation = ProductResponse.class)
    )
    List<ProductResponse> items,
    PageMetadata page
) {}
~~~

Controller có thể khai báo response cụ thể:

~~~java
@GetMapping
@ApiResponse(
    responseCode = "200",
    description = "Trang sản phẩm",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ProductPageResponse.class)
    )
)
public ProductPageResponse search(@ParameterObject Pageable pageable) {
    return productService.searchPage(pageable);
}
~~~

Các ví dụ trên minh họa metadata cho schema và response. Cần có định nghĩa ProductResponse, PageMetadata và service tương ứng. Với kiểu trả về generic, tên component và cách thay thế tham số kiểu có thể khác giữa các phiên bản swagger-core/springdoc; hãy kiểm tra tài liệu JSON được sinh để bảo đảm `items` thực sự chứa ProductResponse.

### Khi nào dùng @ArraySchema?

- Dùng kiểu Java `List<ProductResponse>` khi springdoc đã suy luận đúng.
- Dùng `@ArraySchema` khi cần mô tả phần tử, giới hạn mảng hoặc ví dụ cụ thể.
- Dùng schema object thông thường khi body là wrapper chứa mảng trong một property.
- Không khai báo response array thành object chỉ vì phần tử của mảng là object.

Nếu cần giới hạn số phần tử, có thể bổ sung `minItems` hoặc `maxItems` trong `@ArraySchema` theo API annotation của phiên bản đang dùng. Hãy bảo đảm giới hạn đó được thực thi ở server.

## 14. Tùy biến schema generic và tên component

Generic giúp giảm mã Java lặp lại:

~~~java
public record ApiResponse<T>(
    T data,
    String message
) {}

public record PageResponse<T>(
    List<T> items,
    PageMetadata page
) {}
~~~

Một operation có thể trả:

~~~java
public ApiResponse<PageResponse<ProductResponse>> search(...) {
    // ...
}
~~~

Về mặt hợp đồng, schema cuối cùng cần thể hiện các lớp:

1. ApiResponse object có `data` và `message`.
2. `data` là PageResponse object.
3. PageResponse có `items` là array của ProductResponse và `page` là PageMetadata.

Tên component mà springdoc sinh cho generic wrapper phụ thuộc cách resolve generic và phiên bản thư viện. Đừng hardcode một tên suy đoán trong test hoặc tài liệu hướng dẫn. Mở `/v3/api-docs`, lần theo `$ref` từ response đến `components.schemas`, rồi xác nhận các kiểu generic đã được thay đúng.

Nếu cần tên schema công khai ổn định, có thể tạo DTO cụ thể:

~~~java
@Schema(name = "ProductSearchResponse")
public record ProductSearchResponse(
    ProductPageResponse data,
    String message
) {}
~~~

Hoặc dùng schema tùy biến bằng `OpenApiCustomizer` khi dự án cần quy tắc đặt tên hoặc thay thế schema generic trên diện rộng. Customizer cần cập nhật cả schema và các `$ref` tương ứng; không đổi tên component mà để reference cũ còn sót lại.

### Không dùng chung một tên cho nhiều generic specialization

Ví dụ `ApiResponse<ProductResponse>` và `ApiResponse<OrderResponse>` có cùng raw Java type nhưng `data` khác schema. Nếu công cụ tạo component không phân biệt specialization theo cấu hình hiện tại, hai kiểu có thể va chạm hoặc sinh schema không rõ ràng. Với response quan trọng, DTO cụ thể thường dễ kiểm soát hơn và giúp tên schema phản ánh ngữ cảnh nghiệp vụ.

## 15. Xử lý trang rỗng, trang cuối và dữ liệu thay đổi

Các trường hợp phân trang cần được quy định:

| Trường hợp | Response thường dùng | Metadata |
|---|---|---|
| Có kết quả ở trang đầu | `200` cùng items | `first=true` |
| Trang giữa | `200` cùng items | `first=false`, `last=false` |
| Trang cuối | `200` cùng items | `last=true` |
| Không có bản ghi phù hợp | `200` cùng `items: []` | `empty=true`, `totalElements=0`, `totalPages=0` |
| Trang yêu cầu vượt quá trang cuối | Thường `200` cùng `items: []` | Tổng số trang vẫn phản ánh truy vấn |

API có thể chọn chính sách khác cho trang vượt phạm vi, nhưng cần nhất quán và mô tả rõ. Với collection search, trả trang rỗng thường dễ xử lý hơn trả `404`, vì collection endpoint vẫn tồn tại dù không có phần tử ở vị trí được yêu cầu.

### Sắp xếp ổn định

Khi phân trang offset, hãy dùng thứ tự sắp xếp xác định. Nếu nhiều bản ghi có cùng `createdAt`, hãy thêm khóa duy nhất như `id` làm tiêu chí phụ. Nếu không, bản ghi có thể đổi vị trí giữa các trang khi cơ sở dữ liệu trả về các hàng đồng hạng theo thứ tự không xác định.

### Tổng số phần tử có chi phí

`totalElements` thường cần một truy vấn đếm. Với dữ liệu lớn hoặc bộ lọc phức tạp, truy vấn count có thể tốn kém. Nếu client chỉ cần biết còn dữ liệu tiếp theo hay không, cân nhắc response có `hasNext` và cursor thay vì luôn tính tổng số trang.

### Kích thước trang hiệu lực

Nếu server giới hạn `size`, response nên trả kích thước thực tế đã áp dụng. Không trả `size=1000` nếu server chỉ lấy tối đa 100 phần tử. Metadata phải mô tả cách server xử lý request, không chỉ lặp lại giá trị client gửi lên.

## 16. Kiểm thử response array và phân trang

MockMvc có thể xác minh JSON array:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    ProductService productService;

    @Test
    void returnsProductArray() throws Exception {
        given(productService.findAll()).willReturn(List.of(
            new ProductResponse(42L, "Bàn phím cơ", new BigDecimal("1250000")),
            new ProductResponse(43L, "Chuột không dây", new BigDecimal("650000"))
        ));

        mockMvc.perform(get("/api/products"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$").isArray())
            .andExpect(jsonPath("$.length()").value(2))
            .andExpect(jsonPath("$[0].id").value(42));
    }

    @Test
    void returnsEmptyArrayWhenNoProductsMatch() throws Exception {
        given(productService.findAll()).willReturn(List.of());

        mockMvc.perform(get("/api/products"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$").isArray())
            .andExpect(jsonPath("$.length()").value(0));
    }
}
~~~

Test phân trang có thể kiểm tra cả items và metadata:

~~~java
@Test
void returnsPageItemsAndMetadata() throws Exception {
    Page<ProductResponse> result = new PageImpl<>(
        List.of(new ProductResponse(
            42L, "Bàn phím cơ", new BigDecimal("1250000")
        )),
        PageRequest.of(0, 20),
        57
    );
    given(productService.search(any(Pageable.class))).willReturn(result);

    mockMvc.perform(get("/api/products")
            .param("page", "0")
            .param("size", "20"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items[0].id").value(42))
        .andExpect(jsonPath("$.page.number").value(0))
        .andExpect(jsonPath("$.page.size").value(20))
        .andExpect(jsonPath("$.page.totalElements").value(57))
        .andExpect(jsonPath("$.page.totalPages").value(3));
}
~~~

Ví dụ giả định controller chuyển Page thành ProductPageResponse và service được mock theo chữ ký tương ứng. Bổ sung import Spring Test, Mockito, PageImpl, PageRequest và kiểu DTO trong dự án. Nếu controller nhận `Pageable`, kiểm tra cả việc query parameters được bind đúng.

### Kiểm tra schema OpenAPI

Gọi endpoint tài liệu và xác nhận response array:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/products'].get.responses['200'].content['application/json'].schema.type"
    ).value("array"));
~~~

Với page response, kiểm tra schema có object, property `items` là array và `page` tham chiếu PageMetadata. Tên schema có thể thay đổi nếu dùng generic wrapper; hãy đọc `$ref` thực tế thay vì giả định tên component.

Một bộ kiểm thử đầy đủ nên bao gồm:

- Mảng có nhiều phần tử và mảng rỗng.
- Wrapper có `data` là object và `data` là array.
- Trang đầu, trang giữa, trang cuối và trang rỗng.
- `page` âm, `size` bằng 0 và `size` vượt giới hạn.
- Sort hợp lệ, sort không được hỗ trợ và nhiều tiêu chí sort.
- Schema OpenAPI phản ánh đúng array item, wrapper và page metadata.

## 17. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Trả `List<T>` nhưng tài liệu mô tả một object | Client parse sai cấu trúc body | Dùng array schema với `items` đúng kiểu |
| Khai báo `type: array` nhưng thiếu `items` | Client không biết kiểu phần tử | Tham chiếu schema phần tử hoặc khai báo kiểu scalar |
| Trả mảng rỗng bằng `null` | Client phải xử lý thêm trạng thái không cần thiết | Trả `[]` nếu collection không có phần tử |
| Trả `204` rồi vẫn mong client đọc JSON | Response không có body theo semantics HTTP | Dùng `200` nếu cần trả mảng rỗng hoặc metadata |
| Bọc response nhưng OpenAPI không có property `data` | Hợp đồng không khớp JSON thực tế | Mô tả schema wrapper thay vì schema phần tử trực tiếp |
| Dùng raw generic `ApiResponse` | Schema `data` thiếu kiểu cụ thể | Khai báo generic đầy đủ hoặc DTO chuyên biệt |
| Trả trực tiếp cấu trúc PageImpl như hợp đồng lâu dài | Client phụ thuộc chi tiết triển khai Spring Data | Chuyển sang PageResponse DTO hoặc cấu hình serialization ổn định có chủ ý |
| Không giới hạn page size | Request có thể tạo response và truy vấn quá lớn | Đặt default, maximum và kiểm tra ở server |
| Cho sort theo mọi thuộc tính | Lộ chi tiết persistence hoặc tạo truy vấn không an toàn | Ánh xạ qua allowlist field public |
| Không có tiêu chí sort duy nhất | Bản ghi có thể đổi vị trí giữa các trang | Thêm khóa duy nhất làm tiêu chí phụ |
| Luôn tính total count dù client không cần | Truy vấn đếm có thể tốn kém | Cân nhắc cursor và metadata `hasNext` |
| Tên schema generic va chạm | Client generator nhận cấu trúc sai hoặc mơ hồ | Dùng DTO cụ thể hoặc kiểm soát component name |

### Khi nào có thể dùng PageSerializationMode.VIA_DTO?

Spring Data Commons từ dòng 3.3 cung cấp chế độ serialize Page qua DTO để tránh phơi bày trực tiếp cấu trúc PageImpl:

~~~java
import org.springframework.data.web.config.EnableSpringDataWebSupport;
import org.springframework.data.web.config.EnableSpringDataWebSupport.PageSerializationMode;
import org.springframework.context.annotation.Configuration;

@EnableSpringDataWebSupport(pageSerializationMode = PageSerializationMode.VIA_DTO)
@Configuration
public class SpringDataWebConfiguration {
}
~~~

Đây là lựa chọn hữu ích nếu dự án muốn dùng representation DTO do Spring Data cung cấp. Tuy nhiên, response vẫn theo cấu trúc PagedModel mà Spring Data định nghĩa. Nếu API cần tên property, metadata hoặc quy tắc tương thích riêng, hãy chuyển Page sang DTO của ứng dụng như PageResponse. Kiểm tra phiên bản Spring Data trước khi dùng cấu hình này.

## 18. Bài thực hành tổng hợp

Xây dựng endpoint tìm kiếm sản phẩm hỗ trợ cả danh sách và phân trang:

1. Tạo ProductResponse và endpoint trả `List<ProductResponse>` cho một tập kết quả nhỏ.
2. Kiểm tra springdoc sinh schema array có `items` tham chiếu ProductResponse.
3. Tạo ApiResponse<T> và ProductListEnvelope để so sánh response array trực tiếp với envelope.
4. Tạo PageMetadata và ProductPageResponse với items cùng metadata.
5. Nhận Pageable bằng `@ParameterObject` hoặc khai báo `page`, `size`, `sort` tường minh.
6. Đặt page mặc định là 0, size mặc định là 20 và giới hạn size tối đa là 100.
7. Chỉ cho phép sort theo các field public đã định nghĩa và thêm id làm tiêu chí phụ để ổn định thứ tự.
8. Chuyển `Page<ProductResponse>` ở service thành ProductPageResponse trước khi trả cho client.
9. Tạo đặc tả OpenAPI cho response phân trang và kiểm tra schema trong Swagger UI.
10. Viết test cho mảng rỗng, trang đầu, trang cuối, page vượt phạm vi và size vượt giới hạn.
11. So sánh JSON runtime với schema OpenAPI, điều chỉnh nếu property hoặc kiểu dữ liệu không khớp.
12. Đánh giá khi nào API cần offset pagination và khi nào cursor pagination phù hợp hơn.

### Tiêu chí hoàn thành

- [ ] Response array có schema `type: array` và `items` đúng kiểu.
- [ ] Mảng rỗng được biểu diễn nhất quán và không nhầm với response 204.
- [ ] Wrapper có schema thể hiện đúng property data và kiểu generic bên trong.
- [ ] Page response có items là array và metadata được mô tả rõ.
- [ ] Query parameter page, size và sort có kiểu, default, giới hạn và ví dụ.
- [ ] Server thực thi giới hạn size và allowlist sort như hợp đồng.
- [ ] Metadata phản ánh kích thước trang hiệu lực và tổng kết quả chính xác.
- [ ] OpenAPI JSON và Swagger UI hiển thị đúng response array, wrapper và page.
- [ ] Test bao phủ trường hợp rỗng, nhiều trang và tham số không hợp lệ.
- [ ] Không phụ thuộc trực tiếp vào cấu trúc serialize nội bộ không ổn định của thư viện.

## Tiếp tục học

Sau bài này, hãy kết hợp response array và page với chuẩn hóa lỗi, response component dùng chung và versioning hợp đồng. Khi thay đổi từ mảng sang wrapper hoặc đổi cấu trúc metadata phân trang, hãy xem đó là thay đổi API cần đánh giá tương thích, cập nhật OpenAPI và kiểm thử client trước khi phát hành.
