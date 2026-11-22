# @Operation: summary, description, tags và deprecated

Trong OpenAPI, mỗi endpoint được biểu diễn bằng một **Operation Object** gắn với một HTTP method dưới một path. Ví dụ, GET /api/orders/{id} là một operation. Với springdoc-openapi, annotation **@Operation** cho phép bổ sung metadata để tài liệu giải thích endpoint làm gì, được xếp vào nhóm nào và còn được khuyến nghị sử dụng hay không.

Bốn thuộc tính thường được dùng nhất là:

- **summary**: tiêu đề ngắn giúp người đọc nhận diện thao tác.
- **description**: giải thích chi tiết hành vi, điều kiện và lưu ý khi gọi API.
- **tags**: nhóm operation theo chủ đề hoặc miền nghiệp vụ.
- **deprecated**: đánh dấu operation đã lỗi thời hoặc không còn được khuyến nghị cho tích hợp mới.

Các thuộc tính này làm giàu hợp đồng API và giao diện Swagger UI. Chúng không thay đổi HTTP method, URL, quyền truy cập hay logic nghiệp vụ của controller.

## 1. @Operation liên kết metadata với một endpoint

**@Operation** thuộc thư viện swagger-annotations và được springdoc đọc khi tạo đặc tả OpenAPI. Đặt annotation trên method controller tương ứng với endpoint cần mô tả:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    @Operation(
        summary = "Liệt kê đơn hàng",
        description = "Trả về danh sách đơn hàng mà người dùng hiện tại được phép xem."
    )
    public List<OrderResponse> listOrders() {
        // Gọi service để lấy dữ liệu.
        return List.of();
    }
}
~~~

Trong ví dụ, **@GetMapping** quyết định mapping HTTP của Spring; **@Operation** bổ sung nội dung mô tả vào hợp đồng OpenAPI. Nếu xóa @Operation, endpoint vẫn hoạt động theo mapping của Spring, nhưng phần mô tả có thể chỉ được suy ra từ thông tin mặc định.

Một Operation Object có thể chứa nhiều thuộc tính khác ngoài bốn thuộc tính đang học, chẳng hạn **operationId**, **parameters**, **requestBody**, **responses**, **security** và **externalDocs**. Mỗi thuộc tính phục vụ một khía cạnh riêng. Bài này tập trung vào metadata giúp người dùng hiểu và điều hướng tài liệu.

## 2. Viết summary ngắn và dễ nhận diện

**summary** là tiêu đề ngắn của operation. Nó thường xuất hiện ngay cạnh method và path trong Swagger UI, nên người đọc có thể quét qua danh sách endpoint mà chưa cần mở phần mô tả dài.

Ví dụ:

~~~java
@Operation(summary = "Tìm đơn hàng theo mã")
@GetMapping("/{orderId}")
public OrderResponse getOrder(@PathVariable String orderId) {
    return orderService.getById(orderId);
}
~~~

Một summary tốt nên nói rõ hành động và đối tượng:

| Summary | Nhận xét |
|---|---|
| **Lấy đơn hàng theo mã** | Nêu hành động và đối tượng cụ thể |
| **Tạo yêu cầu hoàn tiền** | Cho biết thao tác tạo một yêu cầu |
| **Cập nhật địa chỉ giao hàng** | Nêu rõ dữ liệu được thay đổi |
| **API đơn hàng** | Quá chung, không nói operation làm gì |
| **Xử lý dữ liệu** | Không xác định dữ liệu hay kết quả nào |

Nên dùng một câu ngắn, tránh đưa toàn bộ quy tắc nghiệp vụ, ví dụ JSON hoặc danh sách mã lỗi vào summary. Những thông tin đó phù hợp với description, requestBody và responses.

Không cần lặp lại HTTP method hoặc path trong summary nếu chúng đã hiển thị ngay bên cạnh. Ví dụ, summary “GET /orders: lấy đơn hàng” lặp lại thông tin có sẵn; “Lấy đơn hàng theo mã” hữu ích hơn.

## 3. Dùng description để giải thích hành vi

**description** là phần diễn giải chi tiết của operation. OpenAPI cho phép nội dung description sử dụng CommonMark, vì vậy có thể trình bày đoạn văn, danh sách, liên kết hoặc định dạng nhấn mạnh.

Ví dụ:

~~~java
@Operation(
    summary = "Tìm đơn hàng theo mã",
    description = """
        Tra cứu đơn hàng theo mã định danh.

        - Người dùng chỉ xem được đơn hàng thuộc phạm vi được cấp quyền.
        - Nếu không tìm thấy đơn hàng, API trả về HTTP 404.
        - Trường items chỉ được trả về khi người gọi có quyền xem chi tiết.
        """
)
@GetMapping("/{orderId}")
public OrderResponse getOrder(@PathVariable String orderId) {
    return orderService.getById(orderId);
}
~~~

Đây là Java text block, cần Java 15 trở lên. Nếu dự án dùng Java thấp hơn, có thể nối chuỗi hoặc dùng một chuỗi đơn giản.

Description nên trả lời những câu hỏi mà tên endpoint không thể hiện:

- Operation phục vụ mục đích gì?
- Dữ liệu được đọc hoặc thay đổi theo quy tắc nào?
- Có điều kiện nghiệp vụ, giới hạn hoặc quyền truy cập đặc biệt nào?
- Trường hợp nào trả về kết quả rỗng, lỗi hoặc trạng thái khác?
- Có tác dụng phụ nào như tạo giao dịch, gửi thông báo hoặc phát sự kiện không?
- Người tích hợp cần lưu ý gì về tính lặp lại, phân trang hoặc thứ tự xử lý?

Chỉ mô tả hành vi thực tế của endpoint. Annotation không tự bảo đảm controller thực hiện đúng nội dung đã viết. Nếu description nói rằng API trả về 404 nhưng implementation lại trả về 200 với body rỗng, tài liệu và hành vi đã lệch nhau.

## 4. Phân biệt summary và description

Hai thuộc tính cùng mô tả operation nhưng phục vụ hai mức đọc khác nhau.

| Tiêu chí | summary | description |
|---|---|---|
| Mục tiêu | Nhận diện nhanh operation | Hiểu cách operation hoạt động |
| Độ dài | Ngắn, thường một câu | Có thể gồm nhiều đoạn |
| Nội dung | Hành động và đối tượng | Quy tắc, điều kiện, lưu ý, ví dụ |
| Hiển thị | Tiêu đề của operation | Phần chi tiết khi mở operation |
| Định dạng | Nên là văn bản ngắn, trực tiếp | Có thể dùng CommonMark |

Ví dụ hoàn chỉnh:

~~~java
@Operation(
    summary = "Tạo đơn hàng",
    description = """
        Tạo đơn hàng mới từ giỏ hàng hiện tại.

        API kiểm tra tồn kho và giá tại thời điểm tạo.
        Nếu một sản phẩm không còn đủ số lượng, request bị từ chối
        và phản hồi chứa thông tin lỗi xác thực nghiệp vụ.
        """
)
@PostMapping
public ResponseEntity<OrderResponse> createOrder(
    @RequestBody CreateOrderRequest request
) {
    // Xử lý tạo đơn hàng.
    return ResponseEntity.accepted().build();
}
~~~

Summary cho biết người dùng đang tạo đơn hàng. Description giải thích nguồn dữ liệu, kiểm tra được thực hiện và trường hợp có thể bị từ chối. Response code và schema lỗi vẫn nên được mô tả bằng **@ApiResponse** hoặc metadata tương ứng; không nên dùng description thay thế toàn bộ hợp đồng response.

## 5. Dùng tags để nhóm operation

**tags** là danh sách tên nhóm gắn với operation. Swagger UI thường gom các operation có cùng tag thành một nhóm để người đọc dễ tìm theo miền chức năng.

Có thể gắn tag ngay trên operation:

~~~java
@Operation(
    summary = "Tìm đơn hàng theo mã",
    tags = {"Orders"}
)
@GetMapping("/{orderId}")
public OrderResponse getOrder(@PathVariable String orderId) {
    return orderService.getById(orderId);
}
~~~

Nhiều operation có thể dùng chung tag **Orders**. Khi tài liệu có nhiều miền nghiệp vụ, nên đặt tên tag nhất quán như **Orders**, **Customers**, **Payments** và **Inventory**.

Một operation có thể có nhiều tag:

~~~java
@Operation(
    summary = "Tạo đơn hàng từ giỏ hàng",
    tags = {"Orders", "Checkout"}
)
@PostMapping
public OrderResponse createOrder(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Khi có nhiều tag, operation có thể xuất hiện trong nhiều nhóm giao diện. Chỉ dùng nhiều tag khi operation thực sự liên quan đến các nhóm đó; nếu gắn quá nhiều tag, người dùng khó hiểu đâu là nhóm chính.

Tên tag cần thống nhất về chữ hoa, chữ thường, số ít/số nhiều và cách đặt tên. Ví dụ **Orders**, **Order** và **orders** có thể bị xem là các tên khác nhau trong công cụ đọc OpenAPI. Chọn một cách viết và sử dụng xuyên suốt tài liệu.

## 6. Khai báo mô tả tag bằng @Tag

**@Tag** định nghĩa tên và mô tả của một nhóm operation. Có thể đặt trên controller để mô tả nhóm API thuộc controller đó:

~~~java
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
@Tag(
    name = "Orders",
    description = "Các thao tác tra cứu và quản lý đơn hàng"
)
class OrderController {
    // Các endpoint của đơn hàng.
}
~~~

Các operation trong controller có thể dùng tag **Orders**. Nếu một method cần được xếp vào nhóm khác hoặc nhiều nhóm, hãy khai báo **tags** trên @Operation và kiểm tra JSON đầu ra để xác nhận kết quả theo phiên bản springdoc đang dùng.

Có thể khai báo metadata tag ở cấp tài liệu bằng **@OpenAPIDefinition**:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Shop API",
        version = "v1",
        description = "API của hệ thống bán hàng"
    ),
    tags = {
        @Tag(
            name = "Orders",
            description = "Tra cứu, tạo và quản lý đơn hàng"
        ),
        @Tag(
            name = "Customers",
            description = "Thông tin và hồ sơ khách hàng"
        ),
        @Tag(
            name = "Payments",
            description = "Thanh toán và hoàn tiền"
        )
    }
)
class OpenApiDocumentationConfiguration {
}
~~~

Ở đây, **@OpenAPIDefinition.tags** định nghĩa metadata tag ở cấp tài liệu. **@Operation.tags** gắn tên tag vào từng operation. Hai phần cần khớp nhau để tài liệu có mô tả nhóm rõ ràng.

Nếu operation dùng một tag chưa được khai báo metadata toàn cục, tên tag vẫn có thể xuất hiện từ operation; tuy nhiên, nhóm sẽ thiếu phần mô tả chung. Khai báo tag ở cấp tài liệu giúp giữ tên và mô tả nhất quán.

## 7. Đánh dấu operation deprecated

Thuộc tính **deprecated** trong @Operation cho biết operation đã lỗi thời hoặc không còn được khuyến nghị cho tích hợp mới. Trong OpenAPI, đây là một cờ boolean của Operation Object.

Ví dụ:

~~~java
@Operation(
    summary = "Tìm đơn hàng bằng mã cũ",
    description = """
        Endpoint này được giữ lại để tương thích với client cũ.

        Hãy chuyển sang GET /api/v2/orders/{orderId}.
        Endpoint cũ dự kiến ngừng hỗ trợ trong phiên bản API tiếp theo.
        """,
    tags = {"Orders"},
    deprecated = true
)
@Deprecated(since = "2.0", forRemoval = false)
@GetMapping("/legacy/orders/{id}")
public OrderResponse getLegacyOrder(@PathVariable String id) {
    return orderService.getByLegacyId(id);
}
~~~

Hai annotation có mục đích khác nhau:

- **@Operation(deprecated = true)** ghi trạng thái deprecated vào metadata OpenAPI.
- **@Deprecated** của Java giúp người đọc mã nguồn và IDE nhận biết method Java không còn được khuyến nghị. Các thuộc tính **since** và **forRemoval** phục vụ thông tin trong mã nguồn Java.

Đặt cả hai annotation giúp thông tin trong mã nguồn và tài liệu API nhất quán. Hãy kiểm tra **deprecated: true** trong JSON sinh ra để xác nhận metadata đã được công bố.

Đánh dấu deprecated không tự động:

- Xóa endpoint khỏi ứng dụng.
- Trả về HTTP 410 hoặc chuyển hướng sang endpoint mới.
- Ngăn client tiếp tục gọi API.
- Thay đổi response hoặc quyền truy cập.
- Lên lịch gỡ bỏ endpoint.

Đó là quyết định trong implementation và quy trình quản lý vòng đời API. Nếu muốn ngừng phục vụ, nhóm cần triển khai thay đổi tương ứng và thông báo thời điểm cho client.

## 8. Mô tả lộ trình thay thế cho endpoint cũ

Một operation deprecated cần giải thích người dùng nên làm gì tiếp theo. Description nên nêu endpoint thay thế, khác biệt request/response và thời điểm dự kiến ngừng hỗ trợ nếu đã có quyết định.

Ví dụ controller có endpoint mới và cũ:

~~~java
@RestController
@RequestMapping("/api")
@Tag(name = "Orders", description = "Tra cứu và quản lý đơn hàng")
class OrderController {

    @Operation(
        summary = "Tìm đơn hàng theo mã",
        description = "API hiện hành để tra cứu một đơn hàng.",
        tags = {"Orders"}
    )
    @GetMapping("/v2/orders/{orderId}")
    public OrderResponse getOrder(
        @PathVariable String orderId
    ) {
        return orderService.getById(orderId);
    }

    @Operation(
        summary = "Tìm đơn hàng bằng mã cũ",
        description = """
            Đã deprecated. Client nên chuyển sang
            GET /api/v2/orders/{orderId}.

            Endpoint này tiếp tục phục vụ tích hợp cũ trong giai đoạn chuyển đổi.
            """,
        tags = {"Orders"},
        deprecated = true
    )
    @Deprecated(since = "2.0")
    @GetMapping("/legacy/orders/{id}")
    public OrderResponse getLegacyOrder(@PathVariable String id) {
        return orderService.getByLegacyId(id);
    }
}
~~~

Trong kế hoạch deprecation, nhóm API nên xác định:

1. Endpoint mới thay thế endpoint cũ.
2. Cách chuyển đổi path, query, header và request body.
3. Khác biệt về response schema hoặc mã HTTP.
4. Phiên bản bắt đầu đánh dấu deprecated.
5. Thời gian hỗ trợ song song và thời điểm dự kiến loại bỏ.
6. Kênh thông báo cho các nhóm client đang tích hợp.

Không ghi ngày ngừng hỗ trợ nếu chưa có quyết định được thống nhất. Một mốc thời gian sai có thể khiến đội client lên kế hoạch chuyển đổi không chính xác.

## 9. Đọc summary, description, tags và deprecated trong JSON

Sau khi ứng dụng chạy, gọi endpoint tài liệu:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Một operation được mô tả trong JSON có thể trông như sau:

~~~json
{
  "paths": {
    "/api/orders/{orderId}": {
      "get": {
        "summary": "Tìm đơn hàng theo mã",
        "description": "Tra cứu đơn hàng theo mã định danh.",
        "tags": [
          "Orders"
        ],
        "deprecated": false,
        "responses": {
          "200": {
            "description": "Tìm thấy đơn hàng"
          }
        }
      }
    },
    "/api/legacy/orders/{id}": {
      "get": {
        "summary": "Tìm đơn hàng bằng mã cũ",
        "description": "Đã deprecated. Hãy chuyển sang API v2.",
        "tags": [
          "Orders"
        ],
        "deprecated": true,
        "responses": {
          "200": {
            "description": "Tìm thấy đơn hàng"
          }
        }
      }
    }
  },
  "tags": [
    {
      "name": "Orders",
      "description": "Tra cứu và quản lý đơn hàng"
    }
  ]
}
~~~

Có thể dùng jq để đọc riêng các thuộc tính:

~~~bash
# Xem toàn bộ operation của một path
jq '.paths["/api/orders/{orderId}"].get' openapi.json

# Liệt kê summary và tags của các operation
jq -r '
  .paths
  | to_entries[]
  | .key as $path
  | .value
  | to_entries[]
  | select(.key | IN("get","post","put","patch","delete","options","head","trace"))
  | "\(.key | ascii_upcase) \($path) | \(.value.summary // "(chưa có summary)") | \((.value.tags // []) | join(", "))"
' openapi.json

# Tìm các operation đã deprecated
jq -r '
  .paths
  | to_entries[]
  | .key as $path
  | .value
  | to_entries[]
  | select(.key | IN("get","post","put","patch","delete","options","head","trace"))
  | select(.value.deprecated == true)
  | "\(.key | ascii_upcase) \($path) | \(.value.summary // "")"
' openapi.json
~~~

Nếu **deprecated** không xuất hiện trong JSON, theo OpenAPI operation đó mặc định không được đánh dấu deprecated. Để xác minh endpoint cũ, hãy kiểm tra đúng path và method, không chỉ tìm chuỗi deprecated ở nơi khác trong tài liệu.

## 10. Hiển thị trên Swagger UI

Swagger UI đọc Operation Object và trình bày các metadata cho người dùng:

- **summary** làm tiêu đề ngắn của operation.
- **description** hiển thị phần giải thích khi mở chi tiết operation.
- **tags** nhóm operation thành các khu vực điều hướng.
- **deprecated** thường được thể hiện bằng kiểu hiển thị hoặc nhãn cảnh báo để người dùng nhận biết operation cũ.

Giao diện cụ thể phụ thuộc phiên bản Swagger UI và cấu hình giao diện. Vì vậy, khi kiểm tra kết quả, nên đối chiếu cả JSON tại **/v3/api-docs** và cách hiển thị trong Swagger UI.

Một tài liệu có summary tốt nhưng tag lộn xộn vẫn khó sử dụng. Ngược lại, nhóm tag rõ ràng nhưng description thiếu điều kiện nghiệp vụ cũng chưa đủ để client tích hợp an toàn. Hãy kiểm tra cả bốn thuộc tính trong ngữ cảnh operation hoàn chỉnh.

## 11. Các lỗi mô tả thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Summary không xuất hiện như mong muốn | @Operation chưa đặt trên đúng method, có annotation khác ghi đè hoặc ứng dụng đang phục vụ tài liệu từ cấu hình khác. |
| Description hiển thị nhưng xuống dòng không đúng | Kiểm tra chuỗi Java, text block và Markdown/CommonMark được sử dụng. |
| Một operation xuất hiện ở nhiều nhóm | Operation được gắn nhiều tag; kiểm tra danh sách tags và chỉ giữ các nhóm thực sự cần thiết. |
| Có nhiều nhóm gần giống nhau | Tên tag khác chữ hoa/chữ thường hoặc cách đặt tên không thống nhất. |
| Tag không có phần mô tả | Chưa khai báo metadata bằng @Tag hoặc @OpenAPIDefinition.tags. |
| Endpoint cũ không được đánh dấu deprecated | Kiểm tra @Operation(deprecated = true) và trường deprecated của operation trong JSON. |
| Swagger UI vẫn gọi endpoint deprecated | Cờ deprecated chỉ mô tả trạng thái; nó không chặn request. |
| Description nói endpoint đã thay thế nhưng không có đường dẫn mới | Bổ sung method, path và hướng dẫn chuyển đổi cụ thể. |

Khi nhiều annotation cùng mô tả một operation, hãy xác minh kết quả cuối cùng trong OpenAPI JSON. Đừng chỉ đọc mã nguồn và giả định thư viện đã tạo đúng metadata.

## 12. Quy ước viết metadata cho nhóm API

Một nhóm có nhiều người phát triển nên thống nhất quy ước trước khi thêm annotation:

| Thuộc tính | Quy ước đề xuất |
|---|---|
| **summary** | Dùng động từ chỉ hành động và đối tượng cụ thể; ngắn, nhất quán về cách viết |
| **description** | Mô tả mục đích, điều kiện, quyền truy cập, tác dụng phụ và các trường hợp đáng chú ý |
| **tags** | Dùng danh mục miền nghiệp vụ đã thống nhất; hạn chế tên gần giống |
| **deprecated** | Bật khi endpoint không còn được khuyến nghị; nêu endpoint thay thế và lộ trình trong description |

Ví dụ danh mục tag cho một hệ thống thương mại điện tử:

- **Catalog**: danh mục và sản phẩm.
- **Customers**: hồ sơ và thông tin khách hàng.
- **Orders**: tạo và quản lý đơn hàng.
- **Payments**: thanh toán, hoàn tiền và giao dịch.
- **Inventory**: tồn kho và giữ chỗ sản phẩm.

Tên tag nên phản ánh miền nghiệp vụ, không nên chỉ phản ánh tên class Java hoặc tên nhóm phát triển. Nếu đổi tag đã được client hoặc tài liệu nội bộ sử dụng, hãy xem đó là thay đổi cấu trúc tài liệu cần thông báo.

## 13. Checklist kiểm tra @Operation

- [ ] Mỗi operation quan trọng có summary ngắn và mô tả đúng hành động.
- [ ] Description giải thích điều kiện, quy tắc nghiệp vụ và lưu ý cần thiết.
- [ ] Nội dung description không mâu thuẫn với hành vi controller.
- [ ] Tên tag thống nhất giữa các controller và operation.
- [ ] Metadata tag được khai báo khi cần mô tả chung cho nhóm.
- [ ] Operation chỉ gắn những tag thực sự liên quan.
- [ ] Endpoint đã lỗi thời có deprecated: true trong JSON.
- [ ] Description của endpoint deprecated chỉ rõ endpoint thay thế và cách chuyển đổi.
- [ ] Cờ deprecated không bị nhầm với việc endpoint đã bị tắt.
- [ ] Swagger UI hiển thị nhóm và metadata như mong đợi.
- [ ] Đã kiểm tra nội dung cuối cùng tại /v3/api-docs.

## 14. Nguồn tra cứu

- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object)
- [OpenAPI Specification – Tag Object](https://spec.openapis.org/oas/latest.html#tag-object)
- [OpenAPI Specification – Root Object](https://spec.openapis.org/oas/latest.html#oas-object)
- [Swagger Annotations – API documentation](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/index.html)
- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)

OpenAPI định nghĩa ý nghĩa của các trường summary, description, tags và deprecated. springdoc-openapi đọc annotation và tạo Operation Object tương ứng. Khi thay đổi phiên bản thư viện hoặc cách tổ chức controller, hãy kiểm tra JSON sinh ra và Swagger UI để bảo đảm tài liệu phản ánh đúng API đang chạy.
