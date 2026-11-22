# Tham số đường dẫn, truy vấn, header và cookie

Một API thường nhận dữ liệu đầu vào từ nhiều vị trí trong HTTP request. Có giá trị định danh tài nguyên nằm ngay trong URL, có bộ lọc nằm sau dấu hỏi, có metadata đi kèm trong header và có thông tin phiên được trình duyệt gửi qua cookie. Trong OpenAPI, bốn nhóm này được mô tả bằng **parameter** với các vị trí (location) lần lượt là **path**, **query**, **header** và **cookie**.

Với **springdoc-openapi**, các annotation của Spring MVC giúp thư viện suy ra phần lớn parameter từ chữ ký controller. Annotation OpenAPI bổ sung mô tả, ví dụ, schema và cách tuần tự hóa khi hợp đồng cần rõ ràng hơn. Bài này tập trung vào cách chọn đúng vị trí, khai báo bằng Spring Boot và kiểm tra đặc tả được sinh ra.

## 1. Bốn vị trí parameter trong một HTTP request

Xét request lấy một đơn hàng:

~~~http
GET /api/orders/8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001?includeItems=true&page=0 HTTP/1.1
Host: api.example.com
X-Request-Id: req-2026-0042
Cookie: locale=vi
~~~

Các giá trị đầu vào nằm ở những vị trí khác nhau:

| Vị trí OpenAPI | Dữ liệu ví dụ | Mục đích thường gặp | Spring MVC |
|---|---|---|---|
| **path** | **/api/orders/{orderId}** | Xác định tài nguyên hoặc tài nguyên con | **@PathVariable** |
| **query** | **includeItems=true**, **page=0** | Lọc, tìm kiếm, phân trang, sắp xếp hoặc chọn cách biểu diễn | **@RequestParam** |
| **header** | **X-Request-Id: req-2026-0042** | Metadata của request, tracing, điều kiện hoặc phiên bản | **@RequestHeader** |
| **cookie** | **locale=vi** | Tùy chọn hoặc trạng thái mà client lưu trong cookie | **@CookieValue** |

Trong OpenAPI, mỗi parameter có tên (**name**), vị trí (**in**) và thường có schema để mô tả kiểu dữ liệu. Tổ hợp tên và vị trí xác định một parameter; cùng một tên có thể xuất hiện ở hai vị trí khác nhau, ví dụ **version** trong query và **X-Api-Version** trong header.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Path"]
    A --> C["Query string"]
    A --> D["Headers"]
    A --> E["Cookies"]
    B --> F["path parameter"]
    C --> G["query parameter"]
    D --> H["header parameter"]
    E --> I["cookie parameter"]
    F --> J["OpenAPI Parameter"]
    G --> J
    H --> J
    I --> J
    J --> K["name + in + schema + mô tả"]
~~~

Điểm cần nhớ là parameter mô tả giá trị truyền ngoài thân request. Nếu client gửi một object JSON trong HTTP body, hãy mô tả bằng **requestBody**; schema của body là một schema riêng, không phải query parameter.

## 2. Path parameter: xác định tài nguyên trong đường dẫn

Path parameter là một phần của path template. Ví dụ **/api/orders/{orderId}** dùng **orderId** để xác định đơn hàng. Trong Spring MVC, dùng **@PathVariable**:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{orderId}")
    public OrderResponse getOrder(
        @PathVariable("orderId") UUID orderId
    ) {
        // Tìm đơn hàng theo orderId
        return null;
    }
}
~~~

springdoc nhận biết **@PathVariable** và tạo parameter có vị trí **path**. Có thể thêm mô tả và ví dụ bằng annotation **@Parameter**:

~~~java
@GetMapping("/{orderId}")
public OrderResponse getOrder(
    @Parameter(
        description = "UUID của đơn hàng cần xem",
        example = "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001"
    )
    @PathVariable("orderId") UUID orderId
) {
    // ...
}
~~~

Các quy tắc quan trọng:

- Tên placeholder trong path phải khớp với tên biến được bind. Dùng **@PathVariable("orderId")** tường minh giúp tránh phụ thuộc vào việc giữ tên tham số khi biên dịch.
- Path parameter luôn bắt buộc. Theo đặc tả OpenAPI, parameter có **in: path** phải có **required: true**.
- Một path template có nhiều placeholder thì phải khai báo đủ parameter tương ứng.
- Path parameter nên đại diện cho định danh hoặc phân cấp tài nguyên. Bộ lọc tùy chọn thường phù hợp với query parameter hơn.

Ví dụ **/api/orders/{orderId}/items/{itemId}** có hai path parameter là **orderId** và **itemId**. Cả hai đều bắt buộc vì thiếu một giá trị thì URL không còn khớp với path template.

## 3. Query parameter: lọc, phân trang và tùy chọn truy vấn

Query parameter nằm sau dấu **?** trong URL. Nhiều giá trị được nối với nhau bằng **&**. Chúng thường dùng cho các điều kiện tìm kiếm, phân trang, sắp xếp hoặc lựa chọn dữ liệu trả về.

~~~java
@GetMapping
public List<OrderResponse> searchOrders(
    @Parameter(description = "Trạng thái đơn hàng", example = "PAID")
    @RequestParam(required = false) OrderStatus status,

    @Parameter(description = "Số trang, bắt đầu từ 0", example = "0")
    @RequestParam(defaultValue = "0") int page,

    @Parameter(description = "Số bản ghi trên một trang", example = "20")
    @RequestParam(defaultValue = "20") int size,

    @Parameter(description = "Có đưa các dòng hàng vào kết quả hay không", example = "true")
    @RequestParam(defaultValue = "false") boolean includeItems
) {
    // ...
    return List.of();
}
~~~

Trong Spring MVC:

- **@RequestParam** mặc định là bắt buộc (**required = true**) nếu không có **defaultValue**.
- **required = false** cho phép request bỏ qua tham số.
- Có **defaultValue** thì Spring dùng giá trị mặc định khi tham số vắng mặt hoặc rỗng; tham số đó không còn bắt buộc đối với việc bind.
- Kiểu Java như **int**, **boolean**, **UUID** hoặc enum được Spring chuyển đổi từ giá trị văn bản nhận qua URL. Giá trị không hợp lệ có thể dẫn đến lỗi chuyển đổi hoặc lỗi request.

Đối với API công khai, hãy mô tả rõ ý nghĩa, miền giá trị, đơn vị, giá trị mặc định và ví dụ. Chẳng hạn, **page** bắt đầu từ 0 hay 1 là một phần của hợp đồng; chỉ ghi tên **page** là chưa đủ.

### Gom nhiều query parameter bằng ParameterObject

Khi endpoint có nhiều bộ lọc, chữ ký method có thể trở nên dài. **@ParameterObject** của springdoc-openapi cho phép bung các thuộc tính của một object thành các query parameter riêng trong tài liệu:

~~~java
public class OrderSearchCriteria {
    private OrderStatus status;
    private String customer;
    private Integer page;
    private Integer size;

    public OrderStatus getStatus() { return status; }
    public void setStatus(OrderStatus status) { this.status = status; }
    public String getCustomer() { return customer; }
    public void setCustomer(String customer) { this.customer = customer; }
    public Integer getPage() { return page; }
    public void setPage(Integer page) { this.page = page; }
    public Integer getSize() { return size; }
    public void setSize(Integer size) { this.size = size; }
}

@GetMapping("/search")
public List<OrderResponse> search(
    @ParameterObject OrderSearchCriteria criteria
) {
    // ...
    return List.of();
}
~~~

Trong ví dụ, các thuộc tính **status**, **customer**, **page** và **size** được trình bày thành các query parameter. **@ParameterObject** là annotation của springdoc, thường được import từ **org.springdoc.core.annotations.ParameterObject** ở dòng springdoc 2.x. Hãy kiểm tra package tương ứng nếu dự án đang dùng dòng phiên bản khác.

Chỉ dùng **@ParameterObject** cho object được bind từ query string, thường là model attribute. Nếu client gửi một JSON object trong body thì dùng **@RequestBody**; hai cơ chế này có cách truyền và cấu trúc OpenAPI khác nhau.

## 4. Header parameter: metadata đi kèm request

Header truyền metadata ở cấp HTTP request. Ví dụ thường gặp là request ID, ngôn ngữ, điều kiện cache hoặc một thông tin định tuyến. Trong Spring MVC, dùng **@RequestHeader**:

~~~java
@GetMapping("/{orderId}")
public OrderResponse getOrder(
    @PathVariable UUID orderId,
    @Parameter(
        description = "Mã tương quan để theo dõi request qua các dịch vụ",
        example = "req-2026-0042"
    )
    @RequestHeader(name = "X-Request-Id", required = false)
    String requestId
) {
    // ...
    return null;
}
~~~

Một header parameter có thể bắt buộc hoặc tùy chọn. Nếu header vắng mặt trong khi **required = true**, Spring MVC có thể trả lỗi thiếu header trước khi gọi logic controller. Với header tùy chọn, hãy định nghĩa cách ứng dụng xử lý khi không có giá trị.

Tên HTTP header không phân biệt chữ hoa và chữ thường theo quy tắc HTTP. Tuy nhiên, hãy dùng một cách viết thống nhất trong tài liệu, ví dụ **X-Request-Id**, để người tích hợp dễ nhận biết.

### Không mô tả header xác thực như parameter thông thường

Các header **Authorization**, **Accept** và **Content-Type** có cách biểu diễn riêng trong OpenAPI:

- Mô tả xác thực bằng **securitySchemes** và **security**, ví dụ HTTP Bearer hoặc API key.
- Media type của request body được mô tả trong **requestBody.content**.
- Media type của response được mô tả trong **responses.content**.

Đặc tả OpenAPI bỏ qua header parameter có tên **Accept**, **Content-Type** hoặc **Authorization**. Vì vậy, không nên khai báo chúng như parameter thông thường để thay thế cơ chế content negotiation hoặc security scheme.

Ví dụ mô tả header Bearer token bằng OpenAPI:

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI orderApi() {
        return new OpenAPI()
            .components(new Components().addSecuritySchemes(
                "bearerAuth",
                new SecurityScheme()
                    .type(SecurityScheme.Type.HTTP)
                    .scheme("bearer")
                    .bearerFormat("JWT")
            ))
            .addSecurityItem(new SecurityRequirement().addList("bearerAuth"));
    }
}
~~~

Ví dụ này mô tả cơ chế xác thực áp dụng ở cấp tài liệu. Nếu chỉ một số operation cần xác thực, có thể gắn **@SecurityRequirement** vào operation hoặc cấu hình tương ứng. Không đưa token thật vào ví dụ hay mô tả parameter.

## 5. Cookie parameter: giá trị được gửi trong Cookie header

Trình duyệt và HTTP client gửi cookie trong header **Cookie**. Spring MVC cung cấp **@CookieValue** để bind một cookie cụ thể:

~~~java
@GetMapping("/preferences")
public PreferenceResponse getPreferences(
    @Parameter(
        description = "Mã ngôn ngữ đã chọn",
        example = "vi"
    )
    @CookieValue(name = "locale", required = false)
    String locale
) {
    String selectedLocale = locale == null ? "vi" : locale;
    // ...
    return null;
}
~~~

Cookie parameter có thể tùy chọn. Nếu cookie bắt buộc nhưng không được gửi, Spring MVC báo lỗi thiếu cookie. Cookie cũng được truyền dưới dạng văn bản; nếu cần bind sang kiểu khác, Spring thực hiện chuyển đổi tương tự các giá trị request khác.

Trong OpenAPI, cookie parameter được biểu diễn với **in: cookie**. Ví dụ:

~~~yaml
parameters:
  - name: locale
    in: cookie
    required: false
    description: Mã ngôn ngữ đã chọn
    schema:
      type: string
      example: vi
~~~

Một số lưu ý khi thiết kế:

- Cookie thường do trình duyệt tự gửi theo domain, path, SameSite và các thuộc tính cookie đã thiết lập. Người dùng Swagger UI có thể không kiểm soát được cookie giống một HTTP client chuyên dụng.
- Cookie **HttpOnly** không thể được JavaScript phía trình duyệt đọc trực tiếp. Việc thử API trong Swagger UI còn phụ thuộc cấu hình CORS, credentials và chính sách cookie của trình duyệt.
- Nếu cookie chứa session hoặc thông tin xác thực, cần mô tả cơ chế xác thực bằng security scheme phù hợp, chẳng hạn API key với **in: cookie**, thay vì chỉ xem nó như tùy chọn giao diện.
- Cookie xác thực làm phát sinh yêu cầu bảo vệ CSRF tùy kiến trúc ứng dụng. Đặc tả API nên ghi rõ cách client gửi cookie và token chống CSRF nếu hệ thống yêu cầu.

Ví dụ khai báo cookie như API key trong cấu hình OpenAPI:

~~~java
@Bean
public OpenAPI cookieAuthenticatedApi() {
    return new OpenAPI()
        .components(new Components().addSecuritySchemes(
            "sessionCookie",
            new SecurityScheme()
                .type(SecurityScheme.Type.APIKEY)
                .in(SecurityScheme.In.COOKIE)
                .name("SESSION")
        ))
        .addSecurityItem(new SecurityRequirement().addList("sessionCookie"));
}
~~~

Đây là cách mô tả cookie dùng cho xác thực. Nếu cookie chỉ chứa tùy chọn không nhạy cảm như ngôn ngữ hiển thị, có thể mô tả nó như cookie parameter thông thường.

## 6. Schema, required và giá trị ví dụ của parameter

Mỗi parameter có một schema mô tả kiểu dữ liệu và các ràng buộc. Một vài ví dụ:

| Dữ liệu | Schema OpenAPI thường dùng |
|---|---|
| Mã đơn hàng UUID | **type: string**, **format: uuid** |
| Số trang | **type: integer**, **format: int32**, **minimum: 0** |
| Cờ bật/tắt | **type: boolean** |
| Trạng thái đơn hàng | **type: string**, **enum: [PENDING, PAID, CANCELLED]** |
| Thời điểm | **type: string**, **format: date-time** |

Có thể dùng **@Parameter** để bổ sung mô tả, ví dụ và schema:

~~~java
@GetMapping
public List<OrderResponse> find(
    @Parameter(
        name = "status",
        description = "Trạng thái cần lọc",
        example = "PAID",
        schema = @Schema(
            type = "string",
            allowableValues = {"PENDING", "PAID", "CANCELLED"}
        )
    )
    @RequestParam(required = false) String status
) {
    // ...
    return List.of();
}
~~~

Nếu tham số Java đã có kiểu enum, springdoc thường có thể suy ra tập giá trị từ enum. Chỉ khai báo lại **allowableValues** khi cần kiểm soát mô tả hoặc kiểu Java không thể hiện đầy đủ hợp đồng.

**required** nói rằng client có phải gửi parameter hay không. Nó không có nghĩa là giá trị được phép hoặc không được phép là **null**. Với parameter, hãy xác định rõ:

- Path parameter luôn required.
- Query, header và cookie có thể required hoặc optional theo hợp đồng.
- Giá trị mặc định cần được thể hiện nhất quán giữa Spring MVC, mô tả OpenAPI và logic thực tế.
- Schema nên mô tả kiểu, format, enum, giới hạn số hoặc độ dài nếu chúng là một phần của hợp đồng.

Không đưa giá trị thật nhạy cảm vào **example**. Dùng giá trị minh họa giả lập cho token, mã khách hàng, cookie phiên hoặc thông tin cá nhân.

## 7. Truyền danh sách và quy tắc serialization

Parameter có thể là một mảng hoặc danh sách. Ví dụ client muốn lọc theo nhiều trạng thái. OpenAPI mô tả không chỉ kiểu mảng mà còn cách ghép các giá trị trên dây truyền HTTP.

Với query parameter, hai dạng thường gặp:

~~~http
GET /api/orders?status=PAID&status=PENDING
GET /api/orders?status=PAID,PENDING
~~~

Dạng đầu truyền nhiều giá trị cùng tên; dạng sau phân tách các giá trị bằng dấu phẩy. Trong OpenAPI, cách biểu diễn được điều khiển bởi **style** và **explode**. Với query parameter, **style: form** là mặc định; **explode: true** thường tạo dạng lặp tên, còn **explode: false** tạo dạng phân tách bằng dấu phẩy.

~~~yaml
parameters:
  - name: status
    in: query
    required: false
    style: form
    explode: true
    description: Danh sách trạng thái cần lọc
    schema:
      type: array
      items:
        type: string
        enum: [PENDING, PAID, CANCELLED]
~~~

Đối với parameter ở các vị trí khác, OpenAPI có quy tắc mặc định serialization riêng. Path và header thường dùng **style: simple**; query và cookie thường dùng **style: form**. Khi cần định dạng đặc biệt, hãy khai báo tường minh và kiểm tra request Swagger UI thực sự gửi.

Trong Spring MVC, cách chuyển đổi danh sách còn phụ thuộc kiểu tham số, converter và cấu hình binding. Ví dụ **List<String>** có thể được bind từ một chuỗi phân tách bằng dấu phẩy, trong khi **MultiValueMap** hoặc cách gửi lặp tên cho phép giữ nhiều giá trị. Vì vậy, tài liệu phải khớp với hành vi controller thật, không chỉ với schema mong muốn.

Với OpenAPI annotation, có thể mô tả mảng bằng **@ArraySchema**:

~~~java
@GetMapping
public List<OrderResponse> findByStatuses(
    @Parameter(
        description = "Các trạng thái cần lọc",
        array = @ArraySchema(
            schema = @Schema(
                type = "string",
                allowableValues = {"PENDING", "PAID", "CANCELLED"}
            )
        ),
        style = ParameterStyle.FORM,
        explode = Explode.TRUE
    )
    @RequestParam(required = false) List<String> status
) {
    // ...
    return List.of();
}
~~~

Các kiểu **ParameterStyle** và **Explode** thuộc swagger-annotations. Tùy phiên bản thư viện, chữ ký annotation có thể khác; nếu dự án không cần tùy chỉnh serialization, hãy để springdoc suy ra schema từ kiểu Java rồi kiểm tra đặc tả đầu ra.

## 8. Khai báo parameter ở cấp method và operation

Trong trường hợp thông thường, đặt **@Parameter** ngay cạnh tham số controller giúp mô tả sát với nơi giá trị được bind:

~~~java
@GetMapping("/{orderId}")
public OrderResponse get(
    @Parameter(description = "Mã đơn hàng", example = "42")
    @PathVariable long orderId,

    @Parameter(description = "Mã tương quan của request")
    @RequestHeader(name = "X-Request-Id", required = false)
    String requestId
) {
    // ...
    return null;
}
~~~

Khi muốn khai báo parameter ở cấp operation, có thể dùng thuộc tính **parameters** của **@Operation**:

~~~java
@Operation(
    summary = "Tìm đơn hàng",
    parameters = {
        @Parameter(
            name = "X-Client-Version",
            in = ParameterIn.HEADER,
            description = "Phiên bản client",
            required = false,
            example = "2.4.0"
        )
    }
)
@GetMapping
public List<OrderResponse> find() {
    // ...
    return List.of();
}
~~~

Parameter ở cấp operation hữu ích khi tài liệu cần mô tả một giá trị mà không được bind trực tiếp vào tham số method, hoặc khi muốn bổ sung thông tin hợp đồng. Tuy nhiên, nếu ứng dụng thực sự cần đọc giá trị đó, controller hoặc tầng xử lý phải có cơ chế nhận nó. Khai báo tài liệu không tự làm cho Spring MVC bind thêm dữ liệu.

Có thể ẩn một parameter khỏi tài liệu bằng **@Parameter(hidden = true)** trong trường hợp phù hợp. Việc ẩn chỉ tác động đến tài liệu; nó không bảo vệ endpoint, không bỏ qua kiểm tra quyền và không biến một giá trị thành bí mật. Không dùng hidden như một cơ chế bảo mật.

## 9. Bản đồ annotation Spring MVC và OpenAPI

| Mục tiêu | Annotation Spring MVC | Annotation OpenAPI / springdoc |
|---|---|---|
| Nhận path parameter | **@PathVariable** | **@Parameter** |
| Nhận query parameter | **@RequestParam** | **@Parameter**, **@ParameterObject** |
| Nhận header parameter | **@RequestHeader** | **@Parameter** |
| Nhận cookie parameter | **@CookieValue** | **@Parameter** |
| Mô tả kiểu và ràng buộc | Kiểu Java, Bean Validation | **@Schema**, **@ArraySchema** |
| Mô tả xác thực | Spring Security và cấu hình bảo mật | **@SecurityScheme**, **@SecurityRequirement**, **OpenAPI** bean |

Spring MVC quyết định cách request được bind và xử lý. OpenAPI mô tả hợp đồng mà client nhìn thấy. springdoc kết hợp mapping và kiểu Java với annotation OpenAPI để sinh đặc tả. Nếu annotation tài liệu khai báo khác hành vi thực tế, Swagger UI có thể hướng dẫn client gửi request sai dù ứng dụng vẫn chạy.

## 10. Đọc đặc tả OpenAPI của một operation

Ví dụ rút gọn dưới đây mô tả một endpoint có đủ bốn vị trí parameter:

~~~yaml
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrder
      summary: Lấy đơn hàng
      parameters:
        - name: orderId
          in: path
          required: true
          description: UUID của đơn hàng
          schema:
            type: string
            format: uuid
        - name: includeItems
          in: query
          required: false
          schema:
            type: boolean
            default: false
        - name: X-Request-Id
          in: header
          required: false
          schema:
            type: string
        - name: locale
          in: cookie
          required: false
          schema:
            type: string
            example: vi
      responses:
        "200":
          description: Lấy đơn hàng thành công
~~~

Khi đọc phần **parameters**, hãy lần lượt kiểm tra:

1. **name** có khớp với tên placeholder, query key, header hoặc cookie thực tế không?
2. **in** có đúng vị trí dữ liệu được gửi không?
3. **required** có phản ánh đúng hành vi controller không?
4. **schema** có đúng kiểu, format, enum và giới hạn không?
5. **description**, **example**, **style** và **explode** có giúp client gửi đúng request không?

Parameter có thể được đặt trực tiếp trong operation hoặc tham chiếu từ **components.parameters** khi nhiều operation dùng chung một định nghĩa. Dù dùng cách nào, đặc tả cuối cùng vẫn phải chỉ rõ tên, vị trí và schema.

## 11. Kiểm tra tài liệu được springdoc sinh ra

Sau khi viết controller và annotation, mở endpoint OpenAPI JSON thường là **/v3/api-docs**; nếu ứng dụng bật YAML, kiểm tra **/v3/api-docs.yaml**. Swagger UI thường nằm tại **/swagger-ui/index.html**, trừ khi dự án đã tùy chỉnh đường dẫn.

Với từng endpoint, hãy đối chiếu ba lớp:

- **Mã nguồn:** annotation Spring MVC có đúng vị trí bind và chính sách required không?
- **Đặc tả:** **parameters** có đúng name, in, schema, example, style và explode không?
- **Request thực tế:** Swagger UI hoặc HTTP client có gửi đúng URL, header và cookie mà server mong đợi không?

Các tình huống nên thử:

- Bỏ một path parameter: URL phải không còn khớp path template.
- Bỏ query parameter tùy chọn: server phải dùng cách xử lý mặc định đã công bố.
- Gửi query value sai kiểu hoặc ngoài enum: server phải trả lỗi phù hợp với hợp đồng.
- Bỏ header bắt buộc: kiểm tra lỗi thiếu header.
- Gửi cookie tùy chọn và không gửi cookie: cả hai trường hợp phải được xử lý đúng.
- Gửi danh sách theo đúng serialization đã công bố: xác minh Spring bind đủ các giá trị.

Nếu endpoint hoạt động nhưng tài liệu hiển thị sai, hãy xem lại mapping, kiểu tham số, annotation OpenAPI và cấu hình springdoc. Nếu tài liệu đúng nhưng request thử trong Swagger UI không thành công, kiểm tra thêm CORS, credentials, cookie policy, security scheme và cấu hình máy chủ.

## 12. Lỗi thiết kế thường gặp và cách tránh

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng path parameter cho một bộ lọc tùy chọn | URL biểu diễn tài nguyên khó hiểu và không thể bỏ giá trị | Chuyển bộ lọc sang query parameter |
| Tên **@PathVariable** không khớp placeholder | Spring không bind được giá trị hoặc tài liệu không rõ ràng | Đặt tên rõ ràng trong cả mapping và annotation |
| Để query parameter bắt buộc trong tài liệu nhưng controller cho phép bỏ qua | Client gửi dữ liệu thừa hoặc hiểu sai hợp đồng | Đồng bộ **required**, **defaultValue** và mô tả |
| Khai báo Authorization như header parameter | Tài liệu bảo mật không được mô hình hóa đúng | Dùng security scheme |
| Mô tả Content-Type như parameter | Nhầm lẫn giữa metadata của body và parameter | Dùng **requestBody.content** |
| Mô tả danh sách nhưng không nói cách phân tách | Client gửi **a,b** trong khi server chờ nhiều giá trị riêng hoặc ngược lại | Khai báo và kiểm tra **style** / **explode** |
| Dùng cookie để xác thực nhưng bỏ qua CSRF và chính sách trình duyệt | Thử API hoặc tích hợp trình duyệt thất bại, tăng rủi ro bảo mật | Mô tả security scheme và yêu cầu cookie/CSRF rõ ràng |
| Dùng **hidden** để che một tham số nhạy cảm | Tạo cảm giác an toàn giả; server vẫn nhận giá trị | Bảo vệ bằng xác thực, phân quyền và xử lý dữ liệu đúng cách |

Không nên truyền bí mật qua query string vì URL có thể xuất hiện trong lịch sử trình duyệt, log, hệ thống phân tích và header referrer. Dữ liệu nhạy cảm cần được truyền bằng cơ chế xác thực phù hợp qua HTTPS và không được ghi log tùy tiện.

## Kết luận

Path, query, header và cookie đều là vị trí truyền parameter trong HTTP request, nhưng mỗi vị trí phục vụ một mục đích khác nhau. **@PathVariable** xác định tài nguyên; **@RequestParam** truyền bộ lọc và tùy chọn; **@RequestHeader** mang metadata; **@CookieValue** đọc cookie từ request. springdoc-openapi dùng các annotation này để tạo parameter trong OpenAPI, còn **@Parameter**, **@ParameterObject**, **@Schema** và security scheme giúp diễn đạt hợp đồng chi tiết hơn. Hãy kiểm tra đặc tả JSON/YAML và request thực tế để bảo đảm tài liệu, controller và cách client gửi dữ liệu luôn thống nhất.
