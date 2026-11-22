# Quy ước về phân trang, sắp xếp và lọc dữ liệu

## 1. Vì sao API cần quy ước truy vấn nhất quán?

Một endpoint danh sách thường phục vụ nhiều màn hình và quy trình khác nhau: trang quản trị cần xem toàn bộ sản phẩm, ứng dụng khách hàng cần tìm theo từ khóa, còn báo cáo cần lọc theo trạng thái và khoảng thời gian. Nếu endpoint trả về toàn bộ dữ liệu trong một lần gọi, response có thể rất lớn, truy vấn tốn tài nguyên và thời gian tải tăng theo quy mô dữ liệu.

Phân trang, sắp xếp và lọc dữ liệu giúp client yêu cầu đúng tập kết quả cần dùng:

- **Phân trang (pagination)** giới hạn số bản ghi trả về trong một lần gọi và cho phép client chuyển qua các phần kết quả.
- **Sắp xếp (sorting)** xác định thứ tự bản ghi, giúp kết quả ổn định và dễ đọc.
- **Lọc dữ liệu (filtering)** giới hạn kết quả theo từ khóa, trạng thái, khoảng giá, thời gian hoặc các điều kiện nghiệp vụ.

Ba khả năng này là một phần của hợp đồng HTTP API. Client cần biết tên query parameter, kiểu dữ liệu, giá trị mặc định, giới hạn, cách kết hợp điều kiện và cấu trúc metadata trong response. Nếu mỗi endpoint dùng một quy ước khác nhau, client phải viết logic riêng và dễ gửi request sai.

Trong Spring Boot, Springdoc OpenAPI có thể mô tả các query parameter và response schema này trong tài liệu OpenAPI. Mục tiêu là để người dùng API hiểu chính xác cách truy vấn mà không phải đọc implementation của controller hoặc repository.

## 2. Thiết kế hợp đồng phân trang

### 2.1. Chọn offset pagination

Offset pagination chia kết quả thành các trang dựa trên vị trí bắt đầu và số bản ghi cần lấy. Một quy ước phổ biến là dùng hai query parameter:

- **page**: số thứ tự trang, bắt đầu từ 0.
- **size**: số bản ghi tối đa trong một trang.

Ví dụ:

~~~http
GET /api/products?page=0&size=20
GET /api/products?page=1&size=20
GET /api/products?page=2&size=20
~~~

Với quy ước này, trang đầu tiên có page bằng 0, trang tiếp theo có page bằng 1. Nếu API chọn đánh số từ 1, tài liệu phải ghi rõ và backend phải chuyển đổi nhất quán. Không nên để client tự đoán cách đánh số.

Cần công bố giá trị mặc định và giới hạn của size. Ví dụ:

| Tham số | Mặc định | Giới hạn | Ý nghĩa |
|---|---:|---:|---|
| page | 0 | Từ 0 trở lên | Trang cần lấy |
| size | 20 | Từ 1 đến 100 | Số bản ghi tối đa trong một trang |

Giới hạn kích thước giúp tránh request yêu cầu hàng chục nghìn bản ghi. Backend nên kiểm tra giá trị đầu vào và trả lỗi validation phù hợp khi page hoặc size không hợp lệ. Không nên âm thầm chấp nhận mọi giá trị lớn do client gửi lên.

### 2.2. Cấu trúc response có metadata

Với offset pagination, response nên cung cấp cả dữ liệu của trang hiện tại và metadata để client điều khiển giao diện:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Bàn phím cơ",
      "price": 1290000
    },
    {
      "id": 102,
      "name": "Chuột không dây",
      "price": 450000
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 137,
  "totalPages": 7,
  "first": true,
  "last": false
}
~~~

Ý nghĩa các trường:

| Trường | Ý nghĩa |
|---|---|
| content | Danh sách bản ghi trong trang hiện tại |
| page | Số trang hiện tại, theo quy ước của API |
| size | Kích thước trang được áp dụng |
| totalElements | Tổng số bản ghi thỏa điều kiện lọc |
| totalPages | Tổng số trang theo size hiện tại |
| first | Có phải trang đầu tiên hay không |
| last | Có phải trang cuối cùng hay không |

Tổng số bản ghi phải được tính sau khi áp dụng các điều kiện lọc. Ví dụ, nếu kho có 10.000 sản phẩm nhưng chỉ 137 sản phẩm ở trạng thái ACTIVE, thì totalElements của truy vấn ACTIVE phải là 137.

Nếu hệ thống không tính tổng số bản ghi vì chi phí truy vấn, có thể thiết kế response chỉ trả về content, hasNext và cursor tiếp theo. Khi đó, không nên tạo ra totalPages giả định; hợp đồng phải thể hiện đúng loại phân trang đang dùng.

### 2.3. Khi nào dùng cursor pagination?

Offset pagination dễ hiểu và phù hợp với các danh sách có quy mô vừa phải, giao diện cần nhảy đến trang cụ thể hoặc cần hiển thị tổng số trang. Tuy nhiên, offset lớn có thể làm truy vấn cơ sở dữ liệu tốn kém. Dữ liệu thay đổi liên tục cũng có thể khiến bản ghi bị lặp hoặc bị bỏ qua giữa hai lần tải trang.

Cursor pagination dùng một giá trị con trỏ để tiếp tục từ vị trí cuối cùng đã đọc. Ví dụ:

~~~http
GET /api/events?limit=50
GET /api/events?limit=50&cursor=eyJpZCI6MTAwNX0
~~~

Response có thể là:

~~~json
{
  "content": [
    {
      "id": 1006,
      "type": "ORDER_CREATED"
    }
  ],
  "nextCursor": "eyJpZCI6MTA1NX0",
  "hasNext": true
}
~~~

Cursor thường được tạo từ các trường sắp xếp ổn định, chẳng hạn thời gian tạo và ID. Giá trị cursor nên được xem như dữ liệu opaque: client lưu và gửi lại nhưng không tự phân tích hoặc chỉnh sửa. Base64 chỉ là cách mã hóa biểu diễn, không phải cơ chế bảo mật; nếu cursor chứa thông tin nhạy cảm hoặc cho phép thay đổi vị trí truy vấn, cần ký hoặc bảo vệ bằng cơ chế phù hợp.

Cursor pagination phù hợp với luồng sự kiện, timeline hoặc danh sách lớn có dữ liệu thay đổi thường xuyên. Offset pagination phù hợp với giao diện cần số trang và khả năng nhảy đến một trang đã biết. Lựa chọn này phải được phản ánh rõ trong tên tham số và response schema.

## 3. Quy ước sắp xếp dữ liệu

### 3.1. Tên và cú pháp tham số sort

Một quy ước phổ biến là dùng query parameter **sort** với tên trường và hướng sắp xếp:

~~~http
GET /api/products?sort=name,asc
GET /api/products?sort=price,desc
~~~

Trong đó:

- **asc** là tăng dần.
- **desc** là giảm dần.
- Tên trường phải thuộc tập trường được API cho phép sắp xếp.

API hỗ trợ nhiều tiêu chí có thể cho phép lặp query parameter:

~~~http
GET /api/products?sort=status,asc&sort=createdAt,desc
~~~

Request trên sắp xếp theo status trước, sau đó theo createdAt trong các bản ghi có cùng status. Với OpenAPI, tham số dạng mảng trong query có thể được mô tả bằng style=form và explode=true để biểu diễn các giá trị lặp. Nếu API dùng cú pháp khác, chẳng hạn một chuỗi phân tách bằng dấu phẩy, phải mô tả chính xác cách phân tích.

Một hợp đồng cần công bố:

- Trường sắp xếp mặc định nếu client không truyền sort.
- Hướng mặc định nếu client chỉ truyền tên trường.
- Có hỗ trợ nhiều tiêu chí hay chỉ một tiêu chí.
- Cách xử lý trường không được phép hoặc hướng sắp xếp không hợp lệ.
- Cách xử lý giá trị null và các trường có kiểu dữ liệu đặc biệt nếu điều đó ảnh hưởng kết quả.

### 3.2. Bảo đảm thứ tự ổn định

Nếu nhiều bản ghi có cùng giá trị ở trường sắp xếp, thứ tự giữa chúng có thể thay đổi giữa các request. Điều này gây ra lỗi khi phân trang: một bản ghi có thể xuất hiện ở hai trang hoặc không xuất hiện ở trang nào.

Để tránh vấn đề, hãy bổ sung một trường phân xử duy nhất, thường là ID. Ví dụ, khi sort theo createdAt giảm dần, backend có thể thêm id giảm dần làm tiêu chí phụ:

~~~text
createdAt DESC, id DESC
~~~

Thứ tự ổn định đặc biệt quan trọng với cursor pagination, vì cursor cần xác định duy nhất vị trí tiếp tục.

### 3.3. Chỉ cho phép sắp xếp theo trường đã công bố

Không nên lấy trực tiếp tên thuộc tính do client gửi rồi ghép vào câu SQL hoặc biểu thức truy vấn. Cách làm này có thể tạo lỗi truy vấn và mở ra rủi ro injection nếu tên trường được xử lý không an toàn.

Backend nên dùng allowlist, ví dụ chỉ cho phép **name**, **price**, **createdAt** và **status**. Nếu client gửi **sort=passwordHash,desc**, API nên trả lỗi 400 với thông báo cho biết trường sắp xếp không hợp lệ.

Cũng cần phân biệt tên trường trong hợp đồng API với tên cột cơ sở dữ liệu. Client có thể gửi createdAt trong khi backend ánh xạ nó tới một thuộc tính hoặc biểu thức khác. Không nên để cấu trúc database trở thành một phần bắt buộc của hợp đồng công khai.

## 4. Quy ước lọc dữ liệu

Lọc dữ liệu thường dùng các query parameter riêng cho từng điều kiện. Ví dụ:

~~~http
GET /api/products?status=ACTIVE
GET /api/products?keyword=keyboard
GET /api/products?minPrice=100000&maxPrice=2000000
GET /api/products?createdFrom=2026-01-01T00:00:00Z&createdTo=2026-02-01T00:00:00Z
~~~

Tên parameter cần phản ánh ý nghĩa nghiệp vụ. Hãy dùng tên nhất quán giữa các endpoint tương tự, ví dụ status, createdFrom, createdTo, minPrice và maxPrice.

### 4.1. Lọc chính xác và lọc theo từ khóa

Lọc chính xác phù hợp với enum, mã định danh hoặc trạng thái:

~~~http
GET /api/orders?status=PAID
GET /api/products?categoryId=12
~~~

Lọc theo từ khóa thường dùng keyword hoặc q:

~~~http
GET /api/products?keyword=mechanical%20keyboard
~~~

Tài liệu cần nói rõ keyword tìm trên trường nào, có phân biệt chữ hoa/chữ thường hay không, có bỏ khoảng trắng đầu cuối không, và tìm theo kiểu chứa chuỗi, bắt đầu bằng hay khớp chính xác.

Không nên để client suy luận rằng keyword luôn tìm trên mọi trường văn bản. Ví dụ, API có thể chỉ tìm trên tên và mã sản phẩm, không tìm trong mô tả dài.

### 4.2. Lọc theo khoảng giá hoặc số

Với dữ liệu dạng số, có thể dùng cặp tham số min và max:

~~~http
GET /api/products?minPrice=100000&maxPrice=2000000
~~~

Hợp đồng cần xác định biên có bao gồm hay không. Một quy ước dễ hiểu là minPrice và maxPrice đều bao gồm giá trị biên. Nếu minPrice lớn hơn maxPrice, API nên trả lỗi 400 với mã lỗi nhất quán.

Với trường ngày giờ, nên thống nhất định dạng ISO 8601 và múi giờ. Ví dụ dùng OffsetDateTime để thể hiện offset hoặc dùng Instant cho thời điểm UTC. Cần công bố khoảng thời gian có bao gồm biên hay không.

Một quy ước phổ biến cho khoảng thời gian là khoảng nửa mở: createdFrom được tính bao gồm, createdTo không bao gồm. Request:

~~~http
GET /api/orders?createdFrom=2026-01-01T00:00:00Z&createdTo=2026-02-01T00:00:00Z
~~~

sẽ lấy bản ghi có thời điểm tạo từ đầu ngày 1/1 đến trước đầu ngày 1/2 theo UTC. Cách này giúp nối các khoảng thời gian liên tiếp mà không bị đếm trùng ở điểm giao.

### 4.3. Lọc theo nhiều giá trị

Một số API cần nhận nhiều trạng thái hoặc nhiều danh mục. Có thể biểu diễn bằng query parameter lặp:

~~~http
GET /api/orders?status=PAID&status=SHIPPED
~~~

Hoặc dùng danh sách phân tách bằng dấu phẩy:

~~~http
GET /api/orders?status=PAID,SHIPPED
~~~

Hai cách này là hai hợp đồng khác nhau. Nếu dùng tham số lặp, tài liệu OpenAPI nên thể hiện parameter là array và cách serialize phù hợp. Nếu dùng dấu phẩy, cần công bố delimiter và cách xử lý giá trị có chứa delimiter.

Đối với danh sách dài, cần giới hạn số phần tử để tránh request quá lớn. Cũng cần định nghĩa phép kết hợp điều kiện: nhiều giá trị của cùng một trường thường mang nghĩa OR, còn các trường lọc khác nhau thường kết hợp bằng AND. Ví dụ status thuộc PAID hoặc SHIPPED đồng thời createdFrom thỏa khoảng thời gian.

### 4.4. Quy định giá trị thiếu, rỗng và null

Các trường hợp sau không nhất thiết có cùng ý nghĩa:

- Không truyền parameter: không áp dụng điều kiện lọc đó.
- Truyền chuỗi rỗng: có thể bị từ chối hoặc được chuẩn hóa thành không có điều kiện.
- Truyền literal null: đây là chuỗi ký tự trong query string, không tự động trở thành giá trị null của Java.
- Truyền giá trị không hợp lệ: trả lỗi validation.

Hợp đồng API cần xác định hành vi cho các trường hợp này, đặc biệt khi client tạo URL từ biểu mẫu tìm kiếm. Không nên để cách xử lý rỗng thay đổi tùy endpoint.

## 5. Kết hợp phân trang, sắp xếp và lọc

Một endpoint danh sách có thể hỗ trợ cả ba nhóm tham số cùng lúc:

~~~http
GET /api/products?page=0&size=20&sort=createdAt,desc&status=ACTIVE&keyword=keyboard&minPrice=100000&maxPrice=2000000
~~~

Backend nên áp dụng điều kiện lọc trước, sau đó sắp xếp và cuối cùng lấy phần dữ liệu theo trang. Tổng số bản ghi trong metadata là số bản ghi sau lọc nhưng trước khi cắt trang.

Thứ tự xử lý logic:

1. Kiểm tra cú pháp và giới hạn của các query parameter.
2. Xây dựng điều kiện lọc theo quy tắc nghiệp vụ.
3. Áp dụng thứ tự sắp xếp mặc định hoặc do client yêu cầu.
4. Lấy trang hoặc batch theo page/size hay cursor/limit.
5. Tạo response chứa dữ liệu và metadata nhất quán.

Nếu client thay đổi bộ lọc, nên đưa page về 0 khi dùng offset pagination vì trang hiện tại có thể vượt quá tổng số trang mới. Client cũng cần gửi lại toàn bộ điều kiện lọc và sort khi chuyển trang; mỗi request GET nên đủ thông tin để tái tạo kết quả.

## 6. Triển khai với Spring Data và Spring Boot

Spring Data cung cấp các kiểu dữ liệu hỗ trợ phân trang và sắp xếp:

- **Pageable** mô tả trang, kích thước và thứ tự sắp xếp.
- **PageRequest** tạo yêu cầu phân trang cụ thể.
- **Sort** biểu diễn một hoặc nhiều tiêu chí sắp xếp.
- **Page<T>** chứa dữ liệu trang cùng metadata như tổng số phần tử và tổng số trang.
- **Slice<T>** cung cấp dữ liệu trang và thông tin có trang tiếp theo mà không yêu cầu tổng số bản ghi.

Ví dụ tạo yêu cầu phân trang:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Chỉ số trang trong PageRequest bắt đầu từ 0. Nếu API công bố page bắt đầu từ 1, cần chuyển đổi rõ ràng trước khi tạo PageRequest và kiểm tra trường hợp page nhỏ hơn 1.

Với repository, một phương thức có thể trả về Page:

~~~java
Page<Product> findByStatus(
    ProductStatus status,
    Pageable pageable
);
~~~

Spring Data sẽ dùng Pageable để áp dụng giới hạn và thứ tự sắp xếp phù hợp với cơ chế lưu trữ. Với bộ lọc phức tạp, có thể dùng Specification, Querydsl hoặc truy vấn tùy chỉnh, miễn là điều kiện đếm tổng số bản ghi khớp với điều kiện lấy content.

Không phải endpoint nào cũng cần tổng số bản ghi. Nếu truy vấn count tốn kém, Slice có thể phù hợp hơn. Hãy chọn kiểu kết quả theo yêu cầu sản phẩm và thể hiện rõ trong response API.

## 7. Mô tả query parameter bằng Springdoc OpenAPI

Springdoc có thể suy luận một phần thông tin từ chữ ký controller, nhưng mô tả rõ ràng giúp tài liệu dễ dùng hơn. Các annotation thường dùng gồm:

| Annotation | Vai trò |
|---|---|
| **@Operation** | Mô tả mục đích của endpoint |
| **@Parameter** | Mô tả từng query parameter, ví dụ và ràng buộc |
| **@Parameters** | Gom nhiều mô tả parameter |
| **@Schema** | Mô tả kiểu dữ liệu và schema response |
| **@ApiResponse** | Mô tả response code và nội dung lỗi hoặc thành công |
| **@ParameterObject** | Mở rộng object thành các query parameter riêng trong tài liệu, thường dùng với Pageable |

Ví dụ controller có mô tả phân trang, sắp xếp và lọc:

~~~java
@RestController
@RequestMapping("/api/products")
@Validated
@Tag(name = "Products", description = "API tra cứu sản phẩm")
public class ProductController {

    @GetMapping
    @Operation(
        summary = "Tìm kiếm sản phẩm",
        description = "Lọc sản phẩm, sắp xếp và trả về một trang kết quả."
    )
    @ApiResponse(
        responseCode = "200",
        description = "Trả về trang sản phẩm phù hợp"
    )
    @ApiResponse(
        responseCode = "400",
        description = "Tham số phân trang hoặc bộ lọc không hợp lệ"
    )
    public ProductPageResponse search(
        @Parameter(
            description = "Số trang, bắt đầu từ 0",
            example = "0"
        )
        @RequestParam(defaultValue = "0")
        @Min(0) int page,

        @Parameter(
            description = "Số phần tử mỗi trang, từ 1 đến 100",
            example = "20"
        )
        @RequestParam(defaultValue = "20")
        @Min(1) @Max(100) int size,

        @Parameter(
            description = "Có thể lặp tham số; mỗi giá trị có dạng field,asc hoặc field,desc",
            example = "createdAt,desc"
        )
        @RequestParam(required = false)
        List<String> sort,

        @Parameter(
            description = "Từ khóa tìm trong tên và mã sản phẩm",
            example = "keyboard"
        )
        @RequestParam(required = false)
        String keyword,

        @Parameter(
            description = "Trạng thái sản phẩm",
            example = "ACTIVE"
        )
        @RequestParam(required = false)
        ProductStatus status,

        @Parameter(
            description = "Giá tối thiểu, bao gồm giá trị biên",
            example = "100000"
        )
        @RequestParam(required = false)
        @DecimalMin("0") BigDecimal minPrice,

        @Parameter(
            description = "Giá tối đa, bao gồm giá trị biên",
            example = "2000000"
        )
        @RequestParam(required = false)
        @DecimalMin("0") BigDecimal maxPrice
    ) {
        Sort requestedSort = ProductSorts.parse(sort);
        Pageable pageable = PageRequest.of(page, size, requestedSort);

        Page<Product> result = productService.search(
            keyword, status, minPrice, maxPrice, pageable
        );

        return ProductPageResponse.from(result);
    }
}
~~~

Ví dụ minh họa cách khai báo parameter và gọi service. Trong ứng dụng thực tế, cần bổ sung xử lý khi minPrice lớn hơn maxPrice, kiểm tra trường sort bằng allowlist và ánh xạ exception validation thành response lỗi thống nhất. Các import và lớp ProductSorts, ProductService, ProductPageResponse được lược bỏ để tập trung vào hợp đồng endpoint.

Với Spring Data Pageable, có thể dùng **@ParameterObject** cùng **@PageableDefault** để Springdoc mở rộng page, size và sort thành các query parameter:

~~~java
@GetMapping
public Page<ProductResponse> search(
    @ParameterObject
    @PageableDefault(
        size = 20,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return productService.search(pageable);
}
~~~

Cách này gọn khi dùng quy ước Pageable mặc định của Spring Data. Nếu API có giới hạn size, quy ước page khác mặc định hoặc cú pháp sort tùy biến, hãy xác minh OpenAPI document sinh ra và bổ sung mô tả rõ ràng cho các giới hạn đó. Khả năng suy luận Pageable có thể phụ thuộc phiên bản Springdoc và cấu hình ứng dụng.

## 8. Mô tả schema response phân trang

Không nhất thiết phải trả trực tiếp đối tượng Page của Spring Data ra ngoài. Một DTO response riêng giúp hợp đồng API ổn định hơn khi thay đổi framework hoặc cấu trúc nội bộ.

Ví dụ:

~~~java
@Schema(description = "Trang kết quả tìm kiếm sản phẩm")
public record ProductPageResponse(
    @Schema(description = "Các sản phẩm trong trang hiện tại")
    List<ProductResponse> content,

    @Schema(description = "Số trang bắt đầu từ 0", example = "0")
    int page,

    @Schema(description = "Kích thước trang", example = "20")
    int size,

    @Schema(description = "Tổng số sản phẩm sau khi lọc", example = "137")
    long totalElements,

    @Schema(description = "Tổng số trang", example = "7")
    int totalPages,

    @Schema(description = "Có phải trang đầu tiên", example = "true")
    boolean first,

    @Schema(description = "Có phải trang cuối cùng", example = "false")
    boolean last
) {
    public static ProductPageResponse from(Page<Product> result) {
        return new ProductPageResponse(
            result.getContent().stream()
                .map(ProductResponse::from)
                .toList(),
            result.getNumber(),
            result.getSize(),
            result.getTotalElements(),
            result.getTotalPages(),
            result.isFirst(),
            result.isLast()
        );
    }
}
~~~

Các trường trong schema phải thống nhất với hành vi backend. Nếu API không trả totalElements hoặc totalPages, không nên mô tả hai trường đó trong OpenAPI. Nếu dùng cursor, hãy tạo schema riêng với nextCursor và hasNext thay vì cố ép cursor vào cấu trúc page/totalPages.

## 9. Mô tả lỗi validation và trường hợp biên

Query parameter là dữ liệu đầu vào từ client, vì vậy API cần xác định response khi giá trị không hợp lệ.

Một số trường hợp thường gặp:

| Tình huống | Hành vi nên xác định |
|---|---|
| page nhỏ hơn 0 | Trả 400 hoặc chuẩn hóa theo quy tắc đã công bố |
| size bằng 0 hoặc vượt giới hạn | Trả 400 hoặc áp dụng giới hạn tối đa đã công bố |
| sort dùng trường không cho phép | Trả 400 với mã lỗi rõ ràng |
| Hướng sort không hợp lệ | Trả 400 |
| minPrice lớn hơn maxPrice | Trả 400 |
| createdFrom sau createdTo | Trả 400 |
| Enum filter không tồn tại | Trả 400 |
| Không có bản ghi phù hợp | Trả 200 với content rỗng và metadata phù hợp |

Không tìm thấy bản ghi phù hợp thường không phải lỗi HTTP 404 đối với endpoint danh sách. Endpoint vẫn tồn tại và truy vấn hợp lệ; kết quả chỉ là một danh sách rỗng. Quy ước này giúp client xử lý danh sách nhất quán.

Có thể mô tả response lỗi bằng schema dùng chung, ví dụ gồm code, message, details và timestamp. Dùng **@ApiResponse** hoặc cấu hình OpenAPI dùng chung để các endpoint công bố cùng một cấu trúc lỗi. Đồng thời, bảo đảm exception handler thực tế trả đúng status code và schema đã mô tả.

## 10. Kiểm thử hợp đồng phân trang, sắp xếp và lọc

Tài liệu OpenAPI chỉ có giá trị khi phản ánh đúng hành vi của endpoint. Nên kiểm tra các nhóm trường hợp sau:

**Phân trang:**
- Trang đầu, trang giữa và trang cuối.
- Trang rỗng khi page vượt quá phạm vi.
- Size mặc định, size nhỏ nhất và size tối đa.
- Giá trị page âm hoặc size ngoài giới hạn.
- Metadata totalElements và totalPages khi có bộ lọc.

**Sắp xếp:**
- Tăng dần và giảm dần.
- Nhiều tiêu chí sort.
- Nhiều bản ghi có cùng giá trị sort để kiểm tra tie-breaker.
- Trường không nằm trong allowlist và direction không hợp lệ.
- Thứ tự kết quả có ổn định khi tải trang liên tiếp.

**Lọc:**
- Mỗi điều kiện riêng lẻ và nhiều điều kiện kết hợp.
- Giá trị enum hợp lệ và không hợp lệ.
- Khoảng số và khoảng thời gian tại đúng biên.
- Nhiều giá trị của cùng parameter.
- Parameter bị thiếu, rỗng hoặc chứa khoảng trắng.
- Kết quả rỗng nhưng request hợp lệ.

Có thể dùng integration test để gọi endpoint bằng query string thật và xác minh cả JSON response lẫn status code. Contract test có thể kiểm tra OpenAPI document chứa đúng tên parameter, kiểu dữ liệu, giá trị mặc định, giới hạn và schema response. Khi hợp đồng thay đổi, so sánh tài liệu giữa hai phiên bản để nhận diện thay đổi ảnh hưởng client.

## 11. Ví dụ hợp đồng API hoàn chỉnh

Một request tìm sản phẩm có thể được chuẩn hóa như sau:

~~~http
GET /api/products?page=0&size=20&sort=createdAt,desc&sort=id,desc&status=ACTIVE&keyword=keyboard&minPrice=100000&maxPrice=2000000
~~~

Hợp đồng của endpoint cần mô tả:

- page bắt đầu từ 0, mặc định là 0.
- size mặc định là 20, giới hạn tối đa là 100.
- sort có thể lặp; mỗi giá trị gồm tên trường được phép và hướng asc hoặc desc.
- status chỉ nhận giá trị thuộc enum ProductStatus.
- keyword tìm trong tên và mã sản phẩm theo quy tắc đã công bố.
- minPrice và maxPrice là biên bao gồm.
- Các điều kiện lọc khác nhau được kết hợp bằng AND.
- Kết quả được sắp xếp ổn định, có thể dùng id làm tiêu chí phụ.
- Response trả content cùng metadata phân trang; nếu không có bản ghi, content là mảng rỗng.

Ví dụ response:

~~~json
{
  "content": [],
  "page": 0,
  "size": 20,
  "totalElements": 0,
  "totalPages": 0,
  "first": true,
  "last": true
}
~~~

Đây là một response hợp lệ khi không có sản phẩm nào thỏa điều kiện. Client vẫn có thể hiển thị trạng thái không có kết quả và giữ nguyên các bộ lọc người dùng đã chọn.

## 12. Nguyên tắc duy trì hợp đồng lâu dài

Quy ước phân trang, sắp xếp và lọc nên được dùng nhất quán giữa các endpoint có cùng mục đích. Khi một endpoint thay đổi tên parameter, cách đánh số trang, giá trị mặc định hoặc cấu trúc response, đó có thể là thay đổi phá vỡ tương thích với client hiện tại.

Một số nguyên tắc giúp duy trì hợp đồng:

- Dùng tên parameter rõ nghĩa và nhất quán.
- Công bố mặc định, giới hạn và cách serialize danh sách.
- Dùng thứ tự ổn định để tránh trùng hoặc bỏ sót bản ghi giữa các trang.
- Chỉ cho phép sort trên các trường đã công bố.
- Xác định rõ biên của filter số và thời gian.
- Chọn offset hoặc cursor theo đặc tính dữ liệu và nhu cầu giao diện.
- Mô tả query parameter, response schema và lỗi bằng Springdoc OpenAPI.
- Kiểm tra tài liệu sinh ra cùng integration test và contract test.

Khi các quy ước này được đưa vào OpenAPI document, client có thể tạo request nhất quán, backend có thể kiểm soát truy vấn và nhóm phát triển có cơ sở rõ ràng để kiểm thử, quản lý phiên bản và phân phối hợp đồng API.

