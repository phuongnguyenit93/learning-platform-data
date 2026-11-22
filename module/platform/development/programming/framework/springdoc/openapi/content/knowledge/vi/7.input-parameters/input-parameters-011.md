# Giới hạn làm phẳng thuộc tính lồng nhau

Springdoc-openapi có thể chuyển một đối tượng tham số của Spring MVC thành nhiều query parameter riêng lẻ. Cách làm này thường được gọi là làm phẳng (flattening) đối tượng. Nó phù hợp với DTO tìm kiếm có các thuộc tính đơn giản như `status`, `customerId`, `fromDate` hoặc `page`. Tuy nhiên, khi DTO chứa một đối tượng khác, collection phức tạp hoặc cấu trúc nhiều tầng, không nên mặc định rằng springdoc sẽ đệ quy chuyển toàn bộ cây thuộc tính thành query parameter.

Annotation `@ParameterObject` của springdoc hỗ trợ việc phân rã một parameter object thành các parameter trong tài liệu OpenAPI. Hỗ trợ đối tượng lồng nhau có giới hạn; tài liệu springdoc nêu rõ nested parameter objects không được hỗ trợ như các parameter object độc lập lồng trong nhau. Đồng thời, Spring MVC có cơ chế binding model attribute riêng. Vì vậy, một cấu trúc có thể được Spring bind ở runtime nhưng chưa chắc được springdoc biểu diễn đầy đủ và chính xác trong hợp đồng OpenAPI.

## 1. Làm phẳng parameter object là gì?

Trong Spring MVC, một tham số kiểu đối tượng thường được bind từ query parameter hoặc form data thông qua cơ chế model attribute. Springdoc có thể đọc các thuộc tính của đối tượng để tạo các parameter riêng trong OpenAPI thay vì mô tả cả đối tượng như một request body.

Ví dụ DTO tìm kiếm đơn giản:

```java
public class OrderSearchCriteria {
    private String status;
    private UUID customerId;
    private LocalDate fromDate;
    private LocalDate toDate;

    // getters và setters
}
```

Controller sử dụng `@ParameterObject`:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    List<OrderResponse> search(
            @ParameterObject @ModelAttribute OrderSearchCriteria criteria) {
        return orderService.search(criteria);
    }
}
```

Thay vì một query parameter duy nhất đại diện cho toàn bộ `OrderSearchCriteria`, tài liệu OpenAPI có thể biểu diễn các thuộc tính thành những parameter riêng:

```yaml
paths:
  /api/orders:
    get:
      parameters:
        - name: status
          in: query
          required: false
          schema:
            type: string
        - name: customerId
          in: query
          required: false
          schema:
            type: string
            format: uuid
        - name: fromDate
          in: query
          required: false
          schema:
            type: string
            format: date
        - name: toDate
          in: query
          required: false
          schema:
            type: string
            format: date
      responses:
        '200':
          description: Danh sách đơn hàng phù hợp
```

Client có thể gọi:

```text
GET /api/orders?status=PAID&customerId=550e8400-e29b-41d4-a716-446655440000&fromDate=2026-01-01
```

Mỗi thuộc tính là một query parameter độc lập. Kiểu dữ liệu, mô tả, ví dụ và ràng buộc của từng trường có thể được thể hiện riêng trong hợp đồng.

## 2. Ranh giới giữa thuộc tính phẳng và thuộc tính lồng nhau

Đối tượng phẳng có các thuộc tính trực tiếp là kiểu đơn giản hoặc kiểu mà công cụ có thể mô tả như một parameter. Ví dụ:

```java
public class ProductFilter {
    private String keyword;
    private String category;
    private BigDecimal minPrice;
    private BigDecimal maxPrice;
    private Boolean available;

    // getters và setters
}
```

Các thuộc tính này có thể được biểu diễn thành query parameter như `keyword`, `category`, `minPrice`, `maxPrice` và `available`.

Đối tượng lồng nhau có một thuộc tính lại là một object khác:

```java
public class OrderSearchCriteria {
    private String status;
    private CustomerFilter customer;
    private DateRange dateRange;

    // getters và setters
}

public class CustomerFilter {
    private String email;
    private String tier;

    // getters và setters
}

public class DateRange {
    private LocalDate from;
    private LocalDate to;

    // getters và setters
}
```

Ở đây, `customer` và `dateRange` không phải các scalar field thông thường. Chúng chứa các thuộc tính con cần một quy ước biểu diễn bổ sung. `@ParameterObject` không nên được xem là một bộ chuyển đổi đệ quy tùy ý cho mọi cấp của object graph. Đặc biệt, không thể giả định rằng việc đặt một `@ParameterObject` lên `OrderSearchCriteria` sẽ tự tạo các parameter `customer.email`, `customer.tier`, `dateRange.from` và `dateRange.to` trong mọi phiên bản springdoc.

Giới hạn này ảnh hưởng đến hợp đồng được sinh: một số thuộc tính lồng nhau có thể không xuất hiện như các query parameter riêng, hoặc không được mô tả theo hình thức mà client mong đợi. Kết quả cụ thể còn phụ thuộc kiểu thuộc tính, cách binding, annotation và phiên bản thư viện. Cần kiểm tra tài liệu thực tế sau khi sinh.

## 3. Spring MVC binding và OpenAPI generation là hai việc khác nhau

Spring MVC có thể bind model attribute bằng property path. Với DTO lồng nhau có getter/setter phù hợp, một request có thể truyền các thuộc tính con theo dạng tên có dấu chấm:

```text
GET /api/orders?status=PAID&customer.email=buyer@example.com&dateRange.from=2026-01-01
```

Spring `WebDataBinder` xử lý việc bind request parameter vào các thuộc tính của object theo quy tắc property binding. Khả năng bind còn phụ thuộc cấu trúc bean, setter, converter, cấu hình binder và các giới hạn bảo mật của ứng dụng.

Điều đó không đồng nghĩa springdoc tự động công bố các tên có dấu chấm thành những parameter OpenAPI chính xác. `@ParameterObject` tập trung vào việc phân rã parameter object theo khả năng hỗ trợ của springdoc; nó không thay đổi cơ chế binding của Spring và không tự tạo một quy ước query string đệ quy cho mọi cấu trúc.

Hãy phân biệt hai câu hỏi khi thiết kế endpoint:

1. Spring có thể nhận và bind query string vào DTO này khi request chạy hay không?
2. Tài liệu OpenAPI được sinh có mô tả đầy đủ tên parameter, kiểu dữ liệu, định dạng và giới hạn mà client cần gửi hay không?

Phải xác minh cả hai. Chỉ kiểm tra Swagger UI thấy endpoint xuất hiện là chưa đủ; hãy xem `parameters` trong JSON/YAML và gửi request thật để kiểm tra binding.

## 4. Những cấu trúc cần thận trọng khi flatten

Không phải mọi thuộc tính đều phù hợp để biến thành một query parameter đơn giản.

| Cấu trúc trong DTO | Vấn đề khi làm phẳng | Cách thiết kế nên cân nhắc |
|---|---|---|
| Scalar field như `String`, `UUID`, `LocalDate` | Thường ánh xạ rõ thành parameter | Dùng `@ParameterObject` cho DTO phẳng |
| Nested POJO như `CustomerFilter` | Cần quy ước tên và cách mô tả thuộc tính con; nested parameter object không được hỗ trợ đầy đủ | Làm phẳng DTO hoặc mô tả parameter tường minh |
| Object lồng nhiều cấp | Tên, schema và cách serialize khó thống nhất; không có flatten đệ quy tổng quát | Chuyển sang request body cho thao tác tìm kiếm phức tạp |
| Collection hoặc mảng | Cần xác định cách lặp key, dấu phân cách hoặc serialization style | Khai báo rõ `array`, `style`, `explode` và kiểm tra client |
| Map có key động | Không có danh sách parameter cố định để sinh từ property | Dùng request body hoặc một query format được định nghĩa rõ |
| Object có kiểu generic/phức tạp | Kiểu thực tế có thể không suy ra đầy đủ từ chữ ký Java | Bổ sung schema/parameter metadata hoặc customizer |
| Entity persistence | Có thể làm lộ nhiều thuộc tính nội bộ và tạo API khó kiểm soát | Dùng DTO tìm kiếm chuyên biệt với field cho phép rõ ràng |

Đặc biệt, một DTO tìm kiếm không nên tái sử dụng trực tiếp entity JPA chỉ vì các field của entity đã có sẵn. Entity thường chứa quan hệ, thông tin nội bộ và thuộc tính không nên trở thành API công khai.

## 5. Cách 1: thiết kế DTO phẳng cho query parameter

Nếu bộ lọc chỉ cần một số thuộc tính đơn giản, cách dễ hiểu nhất là đưa các trường đó lên cùng một DTO.

```java
public class OrderSearchCriteria {
    private String status;
    private UUID customerId;
    private LocalDate createdFrom;
    private LocalDate createdTo;
    private BigDecimal minTotal;
    private BigDecimal maxTotal;

    // getters và setters
}
```

```java
@GetMapping
List<OrderResponse> search(
        @ParameterObject @ModelAttribute OrderSearchCriteria criteria) {
    return orderService.search(criteria);
}
```

Query string có cấu trúc rõ ràng:

```text
GET /api/orders?status=PAID&customerId=...&createdFrom=2026-01-01&minTotal=100000
```

Ưu điểm của DTO phẳng:

- Mỗi thuộc tính có một tên query parameter ổn định.
- Springdoc dễ tạo parameter và schema hơn.
- Swagger UI hiển thị từng trường riêng để người dùng nhập.
- Client generator tạo chữ ký hàm dễ sử dụng.
- Dễ kiểm soát field nào được công khai và field nào chỉ dùng nội bộ.

Không nên làm DTO phẳng quá lớn. Nếu bộ lọc có hàng chục trường thuộc nhiều nhóm nghiệp vụ, hãy cân nhắc chia endpoint hoặc dùng request body tìm kiếm để giữ hợp đồng dễ hiểu.

## 6. Cách 2: khai báo query parameter tường minh

Với endpoint có số lượng tham số nhỏ, khai báo từng `@RequestParam` thường rõ ràng hơn việc đưa một object lồng nhau vào `@ParameterObject`.

```java
@GetMapping
List<OrderResponse> search(
        @RequestParam(required = false) String status,
        @RequestParam(required = false) UUID customerId,
        @RequestParam(required = false) LocalDate createdFrom,
        @RequestParam(required = false) LocalDate createdTo) {
    return orderService.search(status, customerId, createdFrom, createdTo);
}
```

Có thể bổ sung metadata cho từng tham số bằng annotation OpenAPI:

```java
@GetMapping
List<OrderResponse> search(
        @Parameter(description = "Trạng thái đơn hàng", example = "PAID")
        @RequestParam(required = false) String status,
        @Parameter(description = "Mã khách hàng")
        @RequestParam(required = false) UUID customerId) {
    return orderService.search(status, customerId, null, null);
}
```

Cách này tạo hợp đồng trực tiếp, không phụ thuộc vào việc springdoc phải khám phá thuộc tính của một nested object. Đổi lại, chữ ký controller sẽ dài hơn nếu có quá nhiều tham số.

Nếu cần gom các tham số vào một đối tượng nội bộ, có thể dùng model attribute và bổ sung mô tả OpenAPI bằng `@Parameters` hoặc customizer. Phải tránh để springdoc tự sinh thêm một bộ parameter trùng với các parameter khai báo tường minh.

## 7. Cách 3: dùng tên query có dấu chấm và mô tả rõ hợp đồng

Trong một số ứng dụng, nhóm phát triển muốn giữ DTO lồng nhau ở runtime nhưng công bố query parameter theo property path, ví dụ `customer.email` hoặc `dateRange.from`. Spring MVC có thể bind dạng tên này nếu model attribute và bean property được cấu hình phù hợp.

```text
GET /api/orders?customer.email=buyer@example.com&dateRange.from=2026-01-01
```

Nếu chọn quy ước này, hợp đồng OpenAPI cần mô tả các tên parameter đúng như client phải gửi. Có thể khai báo metadata tường minh trên operation, ví dụ:

```java
@Operation(summary = "Tìm kiếm đơn hàng")
@Parameters({
    @Parameter(
        name = "customer.email",
        in = ParameterIn.QUERY,
        description = "Email của khách hàng",
        schema = @Schema(type = "string", format = "email")
    ),
    @Parameter(
        name = "dateRange.from",
        in = ParameterIn.QUERY,
        description = "Ngày bắt đầu lọc",
        schema = @Schema(type = "string", format = "date")
    )
})
@GetMapping
List<OrderResponse> search(@ModelAttribute OrderSearchCriteria criteria) {
    return orderService.search(criteria);
}
```

Đây là cách mô tả hợp đồng tường minh; cần kiểm tra với phiên bản springdoc đang dùng để tránh các parameter tự sinh từ model attribute bị trùng. Nếu việc tự động sinh gây trùng hoặc sai kiểu, hãy dùng `OperationCustomizer` để điều chỉnh operation hoặc chuyển sang khai báo từng `@RequestParam`.

Không nên dùng dấu chấm chỉ vì nó trông giống cấu trúc object. Tên query parameter là một phần hợp đồng công khai; hãy xác định rõ cách client mã hóa, URL encode khi cần và cách Spring binder nhận giá trị.

## 8. Cách 4: mô tả object query bằng `deepObject` trong trường hợp phù hợp

OpenAPI hỗ trợ `style: deepObject` cho một số query parameter dạng object. Cách biểu diễn này cho phép nhóm các thuộc tính dưới một tên parameter:

```yaml
parameters:
  - name: filter
    in: query
    style: deepObject
    explode: true
    schema:
      type: object
      properties:
        status:
          type: string
        customerId:
          type: string
          format: uuid
```

Query string tương ứng thường có dạng:

```text
GET /api/orders?filter[status]=PAID&filter[customerId]=550e8400-e29b-41d4-a716-446655440000
```

`deepObject` có thể phù hợp với object phẳng có các thuộc tính scalar. Quy tắc serialize object lồng nhiều cấp hoặc array bên trong object không được hỗ trợ đồng nhất giữa các công cụ và không nên mặc định rằng mọi client generator đều hiểu cùng một cách. Ngoài ra, Spring MVC không tự động bảo đảm binding cú pháp `filter[status]` vào DTO theo đúng quy ước này nếu không có cấu hình hoặc xử lý bổ sung.

Chỉ chọn `deepObject` khi client, server và validator đều thống nhất cách serialize. Hãy kiểm tra URL thực tế, cấu hình binding và tài liệu được sinh. Không dùng `deepObject` như một cách né giới hạn nested `@ParameterObject` mà chưa xác minh tương thích.

## 9. Cách 5: chuyển bộ lọc phức tạp sang request body

Nếu bộ lọc có nhiều cấp, danh sách điều kiện, nhóm `AND`/`OR`, khoảng giá trị hoặc cấu trúc lồng nhau sâu, request body thường phù hợp hơn query parameter.

Ví dụ DTO tìm kiếm:

```java
public class OrderSearchRequest {
    private String status;
    private CustomerFilter customer;
    private DateRange dateRange;
    private List<String> channels;

    // getters và setters
}
```

Controller:

```java
@PostMapping("/search")
List<OrderResponse> search(@Valid @RequestBody OrderSearchRequest request) {
    return orderService.search(request);
}
```

Hợp đồng OpenAPI:

```yaml
paths:
  /api/orders/search:
    post:
      summary: Tìm kiếm đơn hàng theo điều kiện
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/OrderSearchRequest'
      responses:
        '200':
          description: Danh sách đơn hàng phù hợp
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/OrderResponse'
```

Request body giữ nguyên cấu trúc object, nested object và collection. Schema có thể mô tả các trường lồng nhau một cách tự nhiên, đồng thời hỗ trợ validation và ví dụ ở từng cấp.

POST search endpoint cần được thiết kế có chủ đích. Không nên chuyển mọi bộ lọc sang POST nếu một query GET đơn giản đã đủ; hãy cân nhắc cache, tính an toàn, giới hạn kích thước request và quy ước API của hệ thống.

## 10. Tùy biến mô hình OpenAPI bằng customizer

Khi cấu trúc runtime bắt buộc phải giữ nested object nhưng hợp đồng cần biểu diễn khác với khả năng tự suy ra của springdoc, có thể tùy biến mô hình OpenAPI.

Springdoc cung cấp các điểm mở rộng như `OperationCustomizer` cho operation của Spring MVC và `OpenApiCustomizer` cho tài liệu. Chúng cho phép bổ sung, loại bỏ hoặc điều chỉnh parameter, schema và metadata theo quy tắc của ứng dụng.

Ví dụ khung `OperationCustomizer`:

```java
@Bean
OperationCustomizer searchParameterCustomizer() {
    return (operation, handlerMethod) -> {
        if (handlerMethod.getMethod().getName().equals("search")) {
            // Bổ sung hoặc điều chỉnh parameter của operation tại đây.
        }
        return operation;
    };
}
```

Customizer cần được viết có điều kiện rõ ràng, tránh áp dụng cho mọi operation hoặc tạo parameter trùng tên. Nên dựa trên annotation riêng, tên method kèm controller hoặc metadata ổn định khác thay vì chỉ dựa vào tên phương thức có thể trùng ở nhiều controller.

Sau khi tùy biến, kiểm tra JSON/YAML được sinh và chạy validator OpenAPI. Customizer chỉ thay đổi tài liệu; nó không tự thay đổi cách Spring MVC bind query string. Nếu hợp đồng công bố `customer.email`, controller vẫn phải thực sự nhận được tên đó.

## 11. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Nested field không xuất hiện trong Swagger UI | `@ParameterObject` không flatten đệ quy nested parameter object | Dùng DTO phẳng hoặc khai báo parameter tường minh |
| Spring nhận query nhưng tài liệu không có parameter tương ứng | Spring model binding và springdoc generation có phạm vi riêng | Đối chiếu YAML với query string thực tế, bổ sung metadata |
| Tài liệu chỉ hiển thị một parameter object không rõ cách gửi | Thuộc tính là POJO lồng nhau hoặc kiểu phức tạp | Chọn quy ước query rõ ràng hoặc chuyển sang request body |
| Parameter bị lặp | Vừa để springdoc tự sinh vừa khai báo `@Parameter`/customizer | Chỉ duy trì một nguồn mô tả cho mỗi cặp tên và vị trí |
| Client generator không tạo đúng request | Cấu trúc object query hoặc `deepObject` không được công cụ hỗ trợ như mong đợi | Dùng scalar query rõ ràng hoặc request body |
| Spring không bind `customer.email` | DTO thiếu getter/setter, property path sai hoặc binder bị giới hạn | Kiểm tra bean và cấu hình `WebDataBinder` |
| Query collection không thống nhất | Chưa xác định cách serialize array và quy tắc `style`/`explode` | Mô tả rõ định dạng và thử với client thực tế |
| Thay đổi DTO làm lộ thêm field | Tự động flatten object dùng chung hoặc entity | Dùng DTO công khai chuyên biệt và kiểm soát field |

Khi điều tra, hãy kiểm tra riêng ba lớp:

1. **Binding:** gửi request thật và xác nhận Spring nhận đúng giá trị trong DTO.
2. **Generation:** tải `/v3/api-docs` hoặc `/v3/api-docs.yaml`, xem `paths`, `parameters`, schema và các tên query được công bố.
3. **Client:** dùng Swagger UI hoặc client generator để xác nhận cách công cụ tạo URL phù hợp với quy ước server.

## 12. Nguyên tắc thiết kế

- Dùng `@ParameterObject` cho DTO query phẳng, có tập thuộc tính công khai và kiểu dữ liệu đơn giản.
- Không giả định `@ParameterObject` tự flatten mọi nested POJO hoặc object graph nhiều tầng.
- Phân biệt rõ khả năng bind của Spring MVC với khả năng mô tả tự động của springdoc.
- Nếu dùng property path như `customer.email`, hãy công bố chính xác tên query và kiểm tra binding thực tế.
- Chỉ dùng `deepObject` cho cấu trúc mà client và server cùng hỗ trợ; tránh lồng object sâu hoặc array phức tạp nếu chưa có quy ước rõ.
- Dùng `@RequestParam` và metadata `@Parameter` khi số trường nhỏ và cần hợp đồng rõ ràng.
- Dùng request body cho bộ lọc phức tạp có nested object, collection hoặc logic điều kiện nhiều cấp.
- Dùng customizer khi cần kiểm soát tài liệu ở cấp chương trình, đồng thời kiểm tra không sinh parameter trùng.
- Không dùng entity persistence làm parameter object công khai; tạo DTO riêng với danh sách field được cho phép.
- Sau khi thay đổi cấu trúc DTO hoặc annotation, kiểm tra tài liệu OpenAPI và gửi request thật để đối chiếu.

## Kết luận

Làm phẳng thuộc tính giúp biến DTO tìm kiếm đơn giản thành các query parameter dễ đọc và dễ dùng. Giới hạn xuất hiện khi DTO có nested object, collection hoặc cấu trúc nhiều tầng: Spring MVC có thể bind một số property path ở runtime, nhưng `@ParameterObject` không phải cơ chế flatten đệ quy tổng quát của OpenAPI. Hãy chọn DTO phẳng cho query đơn giản, khai báo parameter tường minh khi cần kiểm soát tên, hoặc dùng request body cho bộ lọc có cấu trúc sâu. Dù chọn cách nào, cần xác minh cả binding thực tế, tài liệu được springdoc sinh và cách client gửi request.
