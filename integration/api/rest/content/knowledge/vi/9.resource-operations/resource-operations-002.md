# Phản hồi dữ liệu tạo mới và URI tài nguyên

## 1. Mục tiêu của bài học

Trong một REST API, thao tác tạo tài nguyên chưa hoàn chỉnh chỉ vì máy chủ đã ghi dữ liệu thành công. Client còn cần biết **điều gì vừa được tạo**, **định danh của tài nguyên là gì** và **có thể truy cập tài nguyên qua URI nào**. Cách trả về mã trạng thái, header và body quyết định mức rõ ràng của hợp đồng API.

Bài này thuộc chương **Thao tác tài nguyên** của module **INTEGRATION_API_REST**. Người học kết hợp resource, URI, HTTP method, status code, hợp đồng dữ liệu, OpenAPI và kiểm thử bằng Java/Spring hoặc công nghệ tương đương. Trọng tâm là thiết kế phản hồi khi tạo mới để client có thể tiếp tục làm việc an toàn, không phải suy luận từ chi tiết cài đặt database.

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa của **201 Created** và header **Location**.
2. Thiết kế response body mô tả tài nguyên mới ở mức cần thiết.
3. Phân biệt URI của collection, URI của tài nguyên, URI của tác vụ bất đồng bộ và URI hiển thị trong các liên kết.
4. Chọn đúng 201, 200, 202, 204 hoặc mã lỗi theo kết quả thực tế.
5. Cài đặt response bằng **Spring Boot / Spring MVC** và mô tả hợp đồng bằng **OpenAPI**.
6. Kiểm thử rằng response tạo mới nhất quán với dữ liệu đã lưu, quyền truy cập và hành vi khi retry.

## 2. Bắt đầu từ hợp đồng tạo tài nguyên

Giả sử một dịch vụ quản lý đơn hàng có collection:

- **POST /api/v1/orders**: yêu cầu tạo đơn hàng.
- **GET /api/v1/orders/{id}**: lấy thông tin đơn hàng theo định danh.
- **GET /api/v1/orders**: truy vấn danh sách đơn hàng có phân trang.

Client gửi:

~~~http
POST /api/v1/orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json
Authorization: Bearer <access-token>

{
  "sku": "BOOK-42",
  "quantity": 2
}
~~~

Giả sử máy chủ đã kiểm tra quyền, kiểm tra dữ liệu và **tạo bền vững** đơn hàng có ID **8e56e37d-0c12-4fc9-9804-1ffed57bd7da**. Một phản hồi tiêu biểu:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/8e56e37d-0c12-4fc9-9804-1ffed57bd7da
Content-Type: application/json
Cache-Control: no-store

{
  "id": "8e56e37d-0c12-4fc9-9804-1ffed57bd7da",
  "sku": "BOOK-42",
  "quantity": 2,
  "status": "PENDING",
  "createdAt": "2026-11-18T09:00:00Z"
}
~~~

Phản hồi này trả lời ba câu hỏi:

- **201 Created:** yêu cầu đã được thực hiện và dẫn đến tạo một hoặc nhiều tài nguyên mới.
- **Location:** tham chiếu URI xác định tài nguyên mới **chính** được tạo, ở đây là đơn hàng cụ thể.
- **Body:** representation JSON mô tả trạng thái đơn hàng sau khi được tạo. Body có thể khác dữ liệu gửi lên vì server bổ sung ID, thời điểm tạo, trạng thái hoặc giá trị được chuẩn hóa.

Client có thể dùng tham chiếu trong Location để thực hiện GET, cập nhật đơn hàng, hoặc lưu lại liên kết. **Location không phải địa chỉ file trong cơ sở dữ liệu**; nó thuộc hợp đồng HTTP công khai của API.

## 3. 201 Created thực sự bảo đảm điều gì?

Theo HTTP Semantics (RFC 9110), phản hồi **201 Created** biểu thị request đã được hoàn tất và tạo ra một hoặc nhiều tài nguyên. Tài nguyên chính được xác định bởi header **Location** nếu header này có mặt; nếu không có Location, theo ngữ nghĩa HTTP, tài nguyên chính được xác định bởi URI đích của request.

Điều này tạo ra quy tắc thực tế rất quan trọng:

- Khi client **POST vào collection** và server sinh ID mới, URI đích của request là collection, ví dụ **/orders**, còn tài nguyên mới là **/orders/{id}**. **Nên trả Location** để chỉ rõ tài nguyên vừa tạo.
- Khi client **PUT vào URI tài nguyên do client chọn**, ví dụ **PUT /orders/external-123**, URI đích đã là URI tài nguyên. Nếu PUT tạo mới thành công, trả **201 Created**; Location có thể được trả để tăng rõ ràng nhưng không phải lúc nào cũng cần vì URI đích đã biết.
- Một response 201 **không bắt buộc** có JSON body. Tuy nhiên, khi client thường cần ID, trạng thái hoặc metadata, body là lựa chọn thiết kế hữu ích.
- Không nên dùng 201 chỉ vì một tiến trình được **đưa vào hàng đợi** để có thể tạo tài nguyên trong tương lai. Nếu việc xử lý request chưa hoàn tất, **202 Accepted** thường phản ánh đúng trạng thái hơn.

**Độ bền và tính đúng đắn:** HTTP 201 không tự chứng minh hệ thống có database transaction, backup hay replication đồng bộ. Đội triển khai phải định nghĩa thời điểm nào thao tác tạo được coi là thành công theo cam kết nghiệp vụ. Với đơn hàng, 201 phải được phát sau khi phần tạo đơn thuộc giao dịch cốt lõi đã thành công; những hoạt động phụ như gửi email có thể tiếp tục bất đồng bộ nếu hợp đồng nói rõ.

### Khi tạo nhiều tài nguyên cùng lúc

201 có thể được dùng khi request tạo nhiều tài nguyên và có một **tài nguyên chính** được định danh rõ. Nhưng với API tạo hàng loạt có thể thành công một phần, một Location đơn lẻ không mô tả được tất cả kết quả. Cần thiết kế hợp đồng riêng gồm ID, trạng thái cho từng phần tử, quy tắc transaction và cách retry. Không nên tự suy ra một mã trạng thái cho từng phần từ status code của toàn bộ HTTP response.

## 4. Thiết kế URI của tài nguyên mới

URI là một phần của API contract, nên thiết kế để người dùng API hiểu được, ổn định và không lộ chi tiết cài đặt.

| Tình huống | URI ví dụ | Vai trò |
| --- | --- | --- |
| Collection | **/api/v1/orders** | Đích POST tạo đơn; có thể dùng GET phân trang |
| Tài nguyên cụ thể | **/api/v1/orders/8e56e37d-...** | Định danh đơn hàng mới; phù hợp Location |
| Tài nguyên lồng trong chủ sở hữu | **/api/v1/customers/42/orders/8e56e37d-...** | Phù hợp khi đường dẫn thể hiện quan hệ theo contract |
| Tác vụ đang chạy | **/api/v1/operations/op-739** | Theo dõi tác vụ bất đồng bộ; chưa chắc là URI đơn hàng |
| Tài nguyên phụ thuộc | **/api/v1/orders/{id}/items** | Collection mặt hàng thuộc một đơn |

### Nguyên tắc khi sinh URI

1. **Trỏ đến tài nguyên**, không trỏ đến tên class, bảng hay tên thao tác nội bộ. URI như **/orders/{id}** thường rõ hơn **/createOrderResult/{id}**.
2. **Dùng định danh bền vững**, phù hợp với chính sách công khai. ID được server tạo có thể là UUID, ULID hoặc một loại khóa khác; thứ tự ID có thể đoán được không được thay cho kiểm tra phân quyền.
3. **Không đưa bí mật vào URI**: access token, mật khẩu, thông tin thanh toán và dữ liệu cá nhân không nên nằm ở path/query, vì URI thường được ghi vào log và lịch sử.
4. **Mã hóa segment động đúng cách**. Nếu ID hoặc khóa bên ngoài chứa dấu cách, dấu gạch chéo hay ký tự đặc biệt, không nối chuỗi trực tiếp rồi giả định URI hợp lệ.
5. **Giữ URI nhất quán với các route thật**. Không trả Location trỏ đến endpoint mà router không có, host nội bộ, tên container hoặc đường dẫn chỉ dùng cho quản trị.
6. **Ổn định sau khi tạo**. Nếu dữ liệu có thể đổi tên, không lấy tên dễ thay đổi làm định danh duy nhất trừ khi đã thiết kế cơ chế chuyển tiếp rõ ràng.

### Location tuyệt đối hay tương đối?

HTTP cho phép giá trị **Location là URI-reference**, nên cả hai cách đều hợp lệ:

~~~http
Location: https://api.example.com/api/v1/orders/8e56e37d-0c12-4fc9-9804-1ffed57bd7da
~~~

~~~http
Location: /api/v1/orders/8e56e37d-0c12-4fc9-9804-1ffed57bd7da
~~~

Giá trị tương đối được client giải quyết dựa trên URI của request theo quy tắc tham chiếu URI. Đường dẫn bắt đầu bằng dấu **/** là tham chiếu bắt đầu từ gốc host, có thể tránh một số lỗi lấy nhầm host nội bộ sau reverse proxy.

Nếu ứng dụng tạo **absolute URI**, cần dùng public base URL đáng tin cậy hoặc cấu hình proxy/forwarded headers đã được kiểm soát. Không lấy bừa header **Host** hay **X-Forwarded-Host** do client gửi để dựng Location, vì có thể dẫn đến URL giả mạo hoặc lộ host nội bộ. Đối với hệ thống đa tenant hoặc nhiều domain, định nghĩa rõ chính sách host nào được phép xuất hiện trong Location.

## 5. Có nên trả body của tài nguyên mới?

Không có một mẫu body phù hợp cho mọi resource. Chọn theo nhu cầu client và yêu cầu bảo mật.

| Phương án | Ví dụ | Khi phù hợp | Đánh đổi |
| --- | --- | --- | --- |
| **201 + Location + representation** | Body chứa ID, trạng thái, thuộc tính chính | Client cần cập nhật giao diện ngay, tránh một lần GET | Response lớn hơn, cần thiết kế field ổn định |
| **201 + Location, không body** | Body rỗng | Client chỉ cần biết URI và sẽ GET khi cần | Client có thể cần thêm request |
| **201 + Location + representation tối thiểu** | ID, status, createdAt, links | Resource phức tạp, tránh gửi toàn bộ dữ liệu | Cần ghi rõ trường nào hiện diện |
| **202 + tác vụ xử lý** | Operation ID, trạng thái PENDING | Việc tạo chưa hoàn tất | Client phải polling/callback và xử lý lỗi bất đồng bộ |

Phản hồi thường nên chứa:

- **id:** định danh ổn định.
- **Các trường cần thiết để hiển thị:** trạng thái hoặc dữ liệu mà server đã chấp nhận.
- **Metadata do server quyết định:** thời điểm tạo, mã phiên bản, tổng tiền do server tính, nếu phù hợp.
- **Liên kết tùy chọn:** **self** hoặc các action hợp lệ theo trạng thái tài nguyên.

Không phản chiếu toàn bộ payload đầu vào một cách máy móc. Chẳng hạn API tạo tài khoản không được trả password/password hash; API tạo thanh toán không được trả khóa bí mật từ gateway; API đa tenant không được hiển thị thuộc tính nội bộ của tenant khác.

### Request DTO và response DTO nên tách nhau

Ví dụ:

~~~json
{
  "sku": "BOOK-42",
  "quantity": 2
}
~~~

Request trên **không** yêu cầu client tự cấp ID, tự quyết định trạng thái cuối hoặc tự gán quyền sở hữu. Server sau khi kiểm tra quyền sẽ trả:

~~~json
{
  "id": "8e56e37d-0c12-4fc9-9804-1ffed57bd7da",
  "sku": "BOOK-42",
  "quantity": 2,
  "status": "PENDING",
  "createdAt": "2026-11-18T09:00:00Z"
}
~~~

Việc tách DTO giảm nguy cơ **mass assignment**: client cố đưa thêm trường nhạy cảm như **ownerId**, **isAdmin** hoặc **approved=true** vào body để thay đổi dữ liệu không có quyền. Hợp đồng tạo mới cần quy định trường nào client được phép gửi, trường nào do server kiểm soát.

## 6. Phân biệt Location và Content-Location

Hai header cùng nói về URI nhưng ý nghĩa khác nhau.

| Header | Vai trò | Ví dụ |
| --- | --- | --- |
| **Location** | Xác định tài nguyên chính vừa được tạo trong 201; cũng được sử dụng cho URI đích chuyển hướng trong các phản hồi 3xx | **Location: /api/v1/orders/{id}** |
| **Content-Location** | Cung cấp URI xác định tài nguyên tương ứng với **representation trong body**; không phải chỉ dẫn chuyển hướng | **Content-Location: /api/v1/orders/{id}** |

Với 201, nếu **Content-Location** trùng **Location**, đây là tín hiệu rằng nội dung phản hồi là representation hiện tại của tài nguyên mới được tạo. Điều đó hữu ích với client có cơ chế cache/metadata, nhưng phần lớn API CRUD đơn giản không cần tự thêm Content-Location khi chưa có use case rõ.

**Đừng nhầm:** Content-Location không thay thế Location để thông báo nơi tạo tài nguyên. Và Location cũng không tự chứng minh body có cùng nội dung với GET ở thời điểm sau, vì tài nguyên có thể tiếp tục thay đổi.

### ETag và cơ chế cập nhật có điều kiện

Nếu API trả representation có version rõ ràng, có thể cân nhắc **ETag**:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/8e56e37d-0c12-4fc9-9804-1ffed57bd7da
ETag: "v1"
Content-Type: application/json
~~~

Client có thể dùng validator phù hợp cho lần sửa tiếp theo:

~~~http
PATCH /api/v1/orders/8e56e37d-0c12-4fc9-9804-1ffed57bd7da HTTP/1.1
If-Match: "v1"
Content-Type: application/merge-patch+json

{"status":"CONFIRMED"}
~~~

Server chỉ thực hiện cập nhật nếu điều kiện phiên bản vẫn đúng; nếu không, trả **412 Precondition Failed** theo ngữ nghĩa điều kiện tương ứng. Cách tạo và kiểm tra ETag phải phản ánh đúng representation/version mà server quản lý. Không đưa ETag giả hoặc tính từ một tập field không đại diện cho điều kiện đồng thời cần bảo vệ.

## 7. Mã trạng thái theo kết quả thao tác

| Tình huống | Mã thường phù hợp | Lý do |
| --- | --- | --- |
| POST đã tạo tài nguyên mới thành công | **201 Created** | Đã có tài nguyên mới; thông báo URI qua Location |
| PUT tạo mới tại URI đã chỉ định trước đó chưa tồn tại | **201 Created** | PUT dẫn đến tạo representation tại URI đích |
| PUT thay thế representation đã tồn tại | **200 OK** nếu trả body, hoặc **204 No Content** nếu không body | Không phải tạo tài nguyên mới |
| POST thực hiện hành động nhưng không tạo tài nguyên mới và trả kết quả | **200 OK** | Thành công đồng bộ, kết quả là response body |
| Request hợp lệ đã được chấp nhận nhưng chưa xử lý hoàn tất | **202 Accepted** | Không khẳng định đã tạo resource cuối cùng |
| Request thành công và không có body, không cần báo tạo tài nguyên mới | **204 No Content** | Không có representation trong response |
| Payload JSON sai cú pháp hoặc request không thể phân tích | **400 Bad Request** | Request không hợp lệ về cú pháp/định dạng |
| Không có xác thực hợp lệ khi endpoint yêu cầu | **401 Unauthorized** | Cần xác thực phù hợp |
| Có xác thực nhưng không có quyền thực hiện | **403 Forbidden** | Không được tạo tài nguyên trong phạm vi đó |
| URI cha/tài nguyên liên quan không tồn tại | **404 Not Found** | Tùy chính sách API và che giấu thông tin |
| Tạo trùng khóa duy nhất hoặc xung đột trạng thái | **409 Conflict** | Trạng thái hiện tại không cho phép hoàn tất tạo mới như yêu cầu |
| Định dạng body không được hỗ trợ | **415 Unsupported Media Type** | Content-Type không hợp lệ |
| Nội dung hợp lệ về cú pháp nhưng vi phạm ràng buộc nghiệp vụ | **422 Unprocessable Content** nếu API áp dụng quy ước đó | Client cần sửa dữ liệu theo quy tắc nghiệp vụ |

**400 hay 422** cho lỗi validation là quyết định hợp đồng cần thống nhất. Nhiều hệ thống dùng 400 cho lỗi Bean Validation, trong khi một số API phân biệt 422 cho dữ liệu hợp lệ về cú pháp nhưng không thể xử lý. Đừng thay đổi ngẫu nhiên giữa các endpoint.

### Sơ đồ chọn response

~~~mermaid
flowchart TD
    R[Nhận request tạo mới] --> V{Dữ liệu, quyền, điều kiện hợp lệ?}
    V -->|Không| E[Trả lỗi 4xx phù hợp]
    V -->|Có| P{Tạo tài nguyên đã hoàn tất?}
    P -->|Chưa, xử lý bất đồng bộ| A[202 Accepted + URI theo dõi nếu có]
    P -->|Đã hoàn tất| N{Có tài nguyên mới?}
    N -->|Có| C[201 Created + Location tài nguyên]
    N -->|Không| O[200 OK hoặc 204 No Content tùy hợp đồng]
~~~

Sơ đồ rút gọn phần lớn trường hợp POST. Với PUT cập nhật tài nguyên đã tồn tại, cần áp dụng riêng quy tắc phân biệt tạo mới và thay thế.

## 8. Trường hợp tạo mới bất đồng bộ: đừng trả 201 quá sớm

Giả sử client yêu cầu nhập 10.000 sản phẩm. Server chỉ nhận request, kiểm tra sơ bộ và đưa job vào hàng đợi; bản ghi sản phẩm cuối cùng **chưa tồn tại**.

Phản hồi phù hợp:

~~~http
HTTP/1.1 202 Accepted
Location: /api/v1/operations/op-739
Content-Type: application/json
Retry-After: 3

{
  "operationId": "op-739",
  "status": "PENDING",
  "statusUrl": "/api/v1/operations/op-739"
}
~~~

Ở đây **Location** theo contract của API là URI tác vụ theo dõi, **không đồng nghĩa** URI sản phẩm đã được tạo. Client có thể GET operation, thấy trạng thái đang chạy, thất bại hoặc hoàn thành kèm URI tài nguyên kết quả:

~~~http
GET /api/v1/operations/op-739 HTTP/1.1
Host: api.example.com
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "operationId": "op-739",
  "status": "SUCCEEDED",
  "result": {
    "productId": "prd-101",
    "resourceUri": "/api/v1/products/prd-101"
  }
}
~~~

**202 không tự định nghĩa một giao thức polling.** Cần tài liệu hóa URI, chu kỳ retry, ý nghĩa status, thời hạn lưu operation, mã lỗi khi job thất bại, quyền xem operation và hành vi khi request lặp.

Một tình huống khác: **đơn hàng đã được tạo bền vững**, nhưng gửi email xác nhận được đưa vào queue xử lý sau. Khi đó **201 Created** vẫn đúng cho việc tạo đơn nếu hợp đồng chỉ hứa đơn hàng tồn tại, còn email là tác vụ phụ. Ranh giới “đã tạo” phải được định nghĩa theo nghiệp vụ.

## 9. POST, PUT và định danh do ai chọn?

**POST vào collection:** client yêu cầu tạo đơn, server quyết định ID.

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json

{"sku":"BOOK-42","quantity":2}
~~~

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/8e56e37d-0c12-4fc9-9804-1ffed57bd7da
~~~

**PUT vào URI cụ thể:** client đã biết URI đích (ví dụ do khóa tích hợp hoặc chính sách định danh cho phép).

~~~http
PUT /api/v1/preferences/user-42 HTTP/1.1
Content-Type: application/json

{"theme":"dark"}
~~~

Nếu tài nguyên đó **chưa tồn tại** và được tạo, response là **201 Created**. Nếu **đã tồn tại** và được thay thế, response thường là 200 hoặc 204. PUT có tính **idempotent** về hiệu ứng dự kiến của nhiều yêu cầu giống nhau, nhưng điều đó không có nghĩa mọi lần lặp đều phải trả cùng status: lần đầu có thể 201, lần sau 200/204.

**Không mặc định cho phép client quyết định URI** nếu điều đó mở đường giả mạo ID hoặc tạo tài nguyên dưới chủ sở hữu khác. Kiểm tra quyền và uniqueness ở lớp dữ liệu.

## 10. Cài đặt trong Java/Spring MVC

Ví dụ dùng **Java 17+** và Spring MVC. Lớp service đảm nhiệm xác thực nghiệp vụ và lưu dữ liệu; controller tạo HTTP response. Mã minh họa giả định repository, kiểm tra quyền và exception handler đã được triển khai phù hợp.

### 10.1. Định nghĩa DTO

~~~java
import java.time.Instant;
import java.util.UUID;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
    @NotBlank String sku,
    @Min(1) int quantity
) {}

public record OrderResponse(
    UUID id,
    String sku,
    int quantity,
    String status,
    Instant createdAt
) {}
~~~

Các trường **id**, **status** và **createdAt** không được client tự gán qua CreateOrderRequest. Trong hệ thống thật, quyền sở hữu nên lấy từ principal đã xác thực sau khi kiểm tra quyền, không lấy giá trị owner tùy ý do client gửi.

### 10.2. Controller trả 201 và Location

~~~java
import java.net.URI;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;

@RestController
@RequestMapping("/api/v1/orders")
@Validated
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderResponse created = orderService.create(request);

        URI location = URI.create("/api/v1/orders/" + created.id());

        return ResponseEntity
                .created(location)
                .body(created);
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderResponse> findById(@PathVariable UUID id) {
        return orderService.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

**Điểm cần lưu ý:**

- **ResponseEntity.created(location)** đặt **201 Created** và header **Location**.
- **body(created)** trả representation mới, để client có thể hiển thị ngay.
- URI dạng **absolute path** bắt đầu từ gốc host hợp lệ theo HTTP; nếu hợp đồng yêu cầu absolute URI thì xây bằng base URL công khai đáng tin cậy.
- Service phải hoàn tất phần lưu có thẩm quyền **trước khi** trả response. Nếu chưa tạo được bản ghi, không trả 201.
- Ví dụ GET trả 404 khi ID không có. Với ứng dụng có phân quyền phức tạp, cần xử lý quyền của người gọi trước khi trả dữ liệu.
- Với API thực tế, controller cũng nên trả Problem Details khi lỗi, cấu hình validation và content negotiation, thay vì làm rò rỉ exception hoặc stack trace.

### 10.3. Giao dịch và tính nguyên tử

Một lớp service minh họa có thể:

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public OrderResponse create(CreateOrderRequest request) {
        OrderEntity entity = new OrderEntity();
        entity.setSku(request.sku());
        entity.setQuantity(request.quantity());
        entity.setStatus("PENDING");
        entity.setCreatedAt(Instant.now());

        OrderEntity saved = repository.save(entity);

        return new OrderResponse(
                saved.getId(),
                saved.getSku(),
                saved.getQuantity(),
                saved.getStatus(),
                saved.getCreatedAt());
    }

    public Optional<OrderResponse> findById(UUID id) {
        return repository.findById(id).map(saved ->
                new OrderResponse(
                        saved.getId(), saved.getSku(),
                        saved.getQuantity(), saved.getStatus(),
                        saved.getCreatedAt()));
    }
}
~~~

Các import/định nghĩa **OrderEntity**, **OrderRepository** và cấu hình transaction được lược bớt để tập trung vào hợp đồng HTTP. Với Spring và transaction proxy, controller chỉ trả 201 sau khi lời gọi service có transaction hoàn tất thành công; cần kiểm tra cấu hình thực tế, nhất là khi có async transaction hoặc ghi qua hệ thống phân tán.

**Không gọi dịch vụ thanh toán bên ngoài rồi mặc định một transaction DB có thể rollback tác dụng phụ đó.** Nếu tạo đơn bao gồm tác vụ ngoài database, dùng idempotency, outbox, saga hoặc workflow phù hợp để giữ tính đúng đắn đầu-cuối.

## 11. Retry, idempotency và tránh tạo hai lần

POST **không mặc định idempotent**. Một client có thể gửi tạo đơn, server tạo thành công và trả 201, nhưng kết nối bị ngắt trước khi client nhận response. Client retry cùng payload có thể tạo **đơn thứ hai** nếu server không có cơ chế kiểm soát.

Tùy nghiệp vụ, có thể dùng **Idempotency-Key**:

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 5be4d80d-f0db-4f91-86e5-4a9776ce930f

{"sku":"BOOK-42","quantity":2}
~~~

Thiết kế phù hợp gồm:

1. Ràng buộc key theo **người gọi/tenant và loại thao tác**; không cho key từ tài khoản khác bị dùng để lấy dữ liệu.
2. Lưu idempotency key, fingerprint của request và kết quả/URI tài nguyên trong một cơ chế chống race; dùng unique constraint hoặc khóa phù hợp.
3. Khi key mới, xử lý tạo một lần và lưu mapping đến tài nguyên mới.
4. Khi retry **cùng key + cùng request hợp lệ**, trả về kết quả phù hợp hợp đồng đã công bố, thường là cùng 201 và Location, hoặc trỏ đến cùng tài nguyên.
5. Khi **cùng key nhưng payload khác**, trả lỗi xung đột phù hợp (ví dụ 409), không tạo tài nguyên mới.
6. Quy định thời hạn giữ key, trạng thái đang xử lý, hành vi concurrency và khả năng retry sau timeout; không để trạng thái trung gian vĩnh viễn.

**201 không bảo đảm idempotency.** Client và server phải thống nhất cơ chế retry. Nếu dùng unique business key, vẫn cần xác định khác biệt giữa “đã tạo trước đó” và “yêu cầu trùng nhưng sai dữ liệu”.

## 12. OpenAPI mô tả phản hồi tạo mới

Ví dụ **OpenAPI 3.1** tối giản, tập trung vào response 201 và header Location:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/v1/orders:
    post:
      summary: Tạo một đơn hàng
      operationId: createOrder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [sku, quantity]
              properties:
                sku:
                  type: string
                  minLength: 1
                quantity:
                  type: integer
                  minimum: 1
      responses:
        '201':
          description: Đơn hàng đã được tạo
          headers:
            Location:
              description: URI-reference của đơn hàng mới
              schema:
                type: string
                format: uri-reference
              example: /api/v1/orders/8e56e37d-0c12-4fc9-9804-1ffed57bd7da
          content:
            application/json:
              schema:
                type: object
                required: [id, sku, quantity, status, createdAt]
                properties:
                  id:
                    type: string
                    format: uuid
                  sku:
                    type: string
                  quantity:
                    type: integer
                  status:
                    type: string
                    example: PENDING
                  createdAt:
                    type: string
                    format: date-time
        '400':
          description: Request không hợp lệ
        '409':
          description: Xung đột trạng thái hoặc khóa nghiệp vụ
~~~

Khi triển khai thật, nên khai báo thêm authentication, error schema chuẩn (ví dụ Problem Details), GET tài nguyên, mã 401/403 và các response cần thiết khác. Trong bài học này, phần quan trọng là OpenAPI phải mô tả **Location là response header** và **schema của representation tạo mới** để client và test có thể kiểm chứng.

Nếu quyết định trả 201 không body, hãy bỏ phần **content** của response 201 thay vì khai báo schema JSON rồi luôn trả rỗng. Nếu API chỉ nhận job bất đồng bộ, mô tả 202 và status endpoint đúng quy trình thực.

## 13. Kiểm thử hợp đồng bằng Spring MockMvc

Trường hợp tạo mới nên được kiểm tra cả **status**, **header**, **body** và **URI có thể truy cập**, không chỉ kiểm tra rằng response trả thành công.

Một kiểm thử tích hợp Spring Boot mang tính minh họa:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderCreationHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void create_returnsResourceUriAndReadableRepresentation() throws Exception {
        MvcResult result = mockMvc.perform(
                post("/api/v1/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"BOOK-42","quantity":2}
                        """))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andExpect(jsonPath("$.id").isNotEmpty())
            .andExpect(jsonPath("$.status").value("PENDING"))
            .andReturn();

        String uri = result.getResponse().getHeader("Location");
        assertNotNull(uri);
        assertTrue(uri.startsWith("/api/v1/orders/"));

        mockMvc.perform(get(uri).accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sku").value("BOOK-42"))
            .andExpect(jsonPath("$.quantity").value(2));
    }
}
~~~

Để chạy ví dụ, dự án cần dependency Spring Boot Test/MockMvc, các import tĩnh, cấu hình database thử và cơ chế authentication phù hợp. Nếu endpoint yêu cầu xác thực, test cần tạo principal hợp lệ thay vì tắt bảo mật để test “xanh”.

### Ma trận kiểm thử nên có

| Tình huống | Kỳ vọng |
| --- | --- |
| POST hợp lệ | 201, Location hợp lệ, response body có ID và trạng thái |
| GET URI từ Location | 200 và trả đúng tài nguyên, trong cùng phạm vi quyền |
| Request sai cú pháp/thiếu trường bắt buộc | 400 hoặc mã validation được hợp đồng định nghĩa; không có tài nguyên mới |
| Caller không có quyền | 401/403 phù hợp; không tạo dữ liệu |
| Tạo trùng khóa nghiệp vụ | 409 hoặc kết quả idempotent đã quy định; không nhân đôi |
| POST timeout rồi retry cùng Idempotency-Key | Trỏ cùng tài nguyên/kết quả; không phát sinh đơn mới |
| Client dùng key cũ với payload khác | Lỗi xung đột; không ghi dữ liệu khác |
| Lưu DB thất bại | Không được trả 201; không thông báo tạo thành công giả |
| Tạo job async | 202 và URI/trạng thái theo dõi, không giả vờ tài nguyên đã hoàn thành |
| Sau reverse proxy | Location dùng URI công khai, không lộ hostname nội bộ |
| ID lạ hoặc không có quyền xem | GET xử lý 404/403 theo chính sách, không lộ dữ liệu tenant khác |

Với hệ thống có gateway, nên có test chạy **qua đường public ingress**, vì MockMvc không thể tự bắt được mọi lỗi host, context path, TLS hoặc forwarded headers.

## 14. Các lỗi thiết kế phổ biến

### Lỗi 1: Trả 200 mặc định sau mọi POST

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"success":true}
~~~

Response này khiến client thiếu ID và vị trí tài nguyên, nếu thao tác thực tế là tạo mới. Khi việc tạo đã hoàn thành, **201 + Location** diễn đạt kết quả chính xác hơn. 200 không bị cấm cho mọi POST, nhưng cần phản ánh đúng hợp đồng của thao tác.

### Lỗi 2: Trả Location trỏ đến collection

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders
~~~

Nếu POST tạo **một đơn hàng cụ thể**, Location ở ví dụ này không cho biết tài nguyên mới ở đâu. Cần trả **/api/v1/orders/{id}**. Nếu tài nguyên chính thực sự là một collection mới hoặc kết quả batch, hợp đồng phải nêu rõ khác biệt đó.

### Lỗi 3: Trả 201 trước khi ghi đã thành công

Ví dụ một controller tự tạo ID, đưa lệnh vào queue, trả 201, trong khi consumer có thể thất bại và resource chưa tồn tại. Trường hợp xử lý chưa hoàn tất nên dùng **202** và nêu rõ cách theo dõi hoặc giải quyết lỗi.

### Lỗi 4: Trả ID trong body nhưng URI không nhất quán

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/123

{"id":"456","status":"PENDING"}
~~~

Trừ khi hợp đồng cố ý mô tả các ID khác nhau, đây là lỗi nghiêm trọng. Location và ID của tài nguyên chính phải được tạo từ **cùng kết quả lưu dữ liệu**.

### Lỗi 5: Dùng URI tài nguyên làm cơ chế phân quyền

Một URL có UUID khó đoán **không đủ** để bảo vệ đơn hàng. Endpoint GET/PATCH/DELETE phải xác thực và kiểm tra quyền theo người dùng, tenant và từng hành động.

### Lỗi 6: Trả representation chứa dữ liệu nhạy cảm

Không đưa password, token, thông tin thẻ đầy đủ, secret hoặc field chỉ dành cho nhân viên nội bộ vào body chỉ vì entity database có các trường đó. Cần mapping sang response DTO theo hợp đồng công khai.

### Lỗi 7: Nhầm header Location với JSON self-link

Body có thể chứa **links.self**, nhưng liên kết đó không tự thay thế ý nghĩa của **Location** trong response 201. Nếu body và header cùng tồn tại, nên đảm bảo chúng trỏ đến cùng tài nguyên chính.

## 15. Bài thực hành: thiết kế API tạo phiếu hỗ trợ

Một hệ thống chăm sóc khách hàng cần endpoint tạo phiếu:

- **POST /api/v1/tickets**
- **GET /api/v1/tickets/{ticketId}**

Người dùng gửi **subject**, **description** và **priority**. Server gán **ticketId**, **createdAt**, **status=OPEN** và chủ sở hữu dựa trên phiên đăng nhập. Sau khi tạo, hệ thống có thể đẩy event gửi email bất đồng bộ.

### Nhiệm vụ

1. Viết request body mẫu và response **201 Created** có **Location** trỏ đến ticket mới.
2. Thiết kế response DTO, giải thích trường nào client được phép gửi và trường nào chỉ server quyết định.
3. Triển khai controller và service bằng Java/Spring (hoặc công nghệ tương đương) có validation và quyền của người tạo.
4. Mô tả response **400**, **401**, **403** và **409** cho các tình huống phù hợp.
5. Thêm **Idempotency-Key** để retry sau timeout không tạo hai ticket. Định nghĩa thời hạn key và xử lý khi payload khác.
6. Viết đoạn OpenAPI mô tả response 201, header Location, schema JSON và lỗi validation.
7. Viết test xác minh một ticket đã được tạo, GET từ Location trả đúng dữ liệu, client không tự gán owner/status và không lộ thông tin của tenant khác.
8. Nếu việc tạo ticket phải được duyệt trong workflow bất đồng bộ trước khi resource tồn tại, đổi thiết kế sang **202 Accepted + operation resource** và mô tả cách client theo dõi trạng thái.

### Tiêu chí đánh giá

Một bài làm tốt thể hiện đúng ba bất biến:

- **Đúng mã:** 201 chỉ khi việc tạo tài nguyên theo hợp đồng đã hoàn tất.
- **Đúng vị trí:** Location là URI-reference ổn định, truy cập được theo quyền, trỏ đến đúng ticket.
- **Đúng dữ liệu:** body phản ánh trạng thái do server xác nhận, không lộ field nhạy cảm; retry không tạo tác dụng phụ trùng.

## 16. Checklist trước khi công bố API

| Câu hỏi kiểm tra | Đạt khi |
| --- | --- |
| Phạm vi tài nguyên được xác định rõ chưa? | Có collection, resource URI và quy tắc ID nhất quán |
| Status code có phản ánh kết quả thật không? | 201 khi tạo xong, 202 khi chưa hoàn tất, lỗi khi thất bại |
| Location đúng chưa? | URI-reference hợp lệ, không lộ host nội bộ, trỏ đúng tài nguyên chính |
| Body có hữu ích và an toàn không? | DTO đúng hợp đồng, có dữ liệu cần dùng, không trả bí mật |
| GET từ Location có ý nghĩa không? | Có endpoint hoặc tài liệu giải thích truy cập theo quyền/trạng thái |
| Có xử lý tạo trùng và retry không? | Ràng buộc dữ liệu, idempotency và concurrency được định nghĩa |
| Có cơ chế validation và phân quyền không? | Request không hợp lệ/không có quyền không tạo dữ liệu |
| OpenAPI có khớp implementation không? | Document 201/Location/body, 202, các lỗi và schema |
| Có kiểm thử end-to-end không? | Test status + header + body + GET + các tình huống lỗi |
| Có xem xét proxy/gateway không? | URI public đúng trong môi trường triển khai thật |

## 17. Điều cần ghi nhớ

**Tạo tài nguyên là một hợp đồng HTTP hoàn chỉnh:** client gửi yêu cầu đến collection hoặc URI đích, server kiểm tra và tạo dữ liệu, sau đó phản hồi bằng status đúng, URI tài nguyên và representation phù hợp. Bộ ba **201 Created + Location + body có ý nghĩa** là mẫu rất hữu ích cho POST tạo mới đồng bộ, nhưng phải được điều chỉnh khi tài nguyên có sẵn, thao tác xử lý bất đồng bộ, nhiều tài nguyên được tạo hoặc có yêu cầu idempotency.

Khi tự kiểm tra thiết kế, hãy thử đặt câu hỏi từ phía client: **“Tôi vừa tạo được tài nguyên gì, URI nào là nguồn tham chiếu chính, dữ liệu nào đã thực sự được lưu, và nếu tôi gửi lại request thì điều gì xảy ra?”**
