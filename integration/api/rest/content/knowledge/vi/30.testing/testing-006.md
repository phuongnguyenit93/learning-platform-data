# Kiểm tra schema, validation và Problem Details

Một REST API có thể trả `200 OK` cho JSON đúng cú pháp nhưng sai ý nghĩa, hoặc trả `500 Internal Server Error` cho một trường `quantity: -1` mà lẽ ra phải bị từ chối ngay từ đầu. Khi frontend, ứng dụng mobile và đối tác dùng chung một API, lỗi kiểu này khiến client khó xử lý, test dễ bỏ sót và hợp đồng thay đổi mà không ai nhận ra.

Trong phần **Kiểm thử** của module thiết kế REST API, ta kết hợp ba lớp:

1. **Schema/contract**: mô tả và kiểm tra hình dạng dữ liệu, kiểu, trường bắt buộc, giới hạn cấu trúc và các response được công bố trong OpenAPI.
2. **Validation**: kiểm tra ràng buộc đầu vào ở nhiều tầng, từ JSON parser đến DTO, nghiệp vụ và cơ sở dữ liệu.
3. **Problem Details**: trả lỗi HTTP có cấu trúc, ổn định và có thể kiểm thử theo **RFC 9457**, thay cho chuỗi lỗi tùy tiện hoặc stack trace.

Đích học tập là viết được test tự động cho cả đường thành công, trường hợp ranh giới và lỗi bảo mật, đồng thời biết **test nào chứng minh được điều gì**. Ví dụ xuyên suốt dùng Java 17+, Spring Boot 3.x/Spring MVC, Jakarta Bean Validation và OpenAPI 3.1; nguyên tắc vẫn áp dụng với Jakarta REST hoặc framework tương đương.

## 1. Tách các lớp kiểm tra để không bỏ sót hành vi

Xét `POST /v1/orders` với JSON:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Authorization: Bearer <access-token>

{
  "customerEmail": "linh@example.com",
  "items": [
    {"sku": "BOOK-42", "quantity": 2}
  ],
  "deliveryAddressId": "ADDR-100"
}
~~~

Server phải trả lời những câu hỏi khác nhau:

| Tầng | Câu hỏi | Ví dụ lỗi | Kết quả thường dùng |
| --- | --- | --- | --- |
| **HTTP/media type** | Header và body có thể xử lý không? | `Content-Type: text/plain` cho endpoint chỉ nhận JSON | `415 Unsupported Media Type` |
| **JSON parser** | Body có đúng cú pháp, kiểu có thể giải mã không? | Thiếu dấu `}`, `quantity` là object thay vì số | `400 Bad Request` |
| **Schema** | Cấu trúc có phù hợp hợp đồng không? | Thiếu `items`, mảng quá 100 phần tử, field lạ | `400` hoặc `422` theo chính sách đã công bố |
| **Bean Validation** | Giá trị DTO có đúng ràng buộc không? | `quantity: 0`, `customerEmail` rỗng | `422 Unprocessable Content` trong ví dụ này |
| **Nghiệp vụ/authorization** | Lệnh có hợp lệ trong bối cảnh hiện tại không? | SKU trùng, địa chỉ không thuộc người gọi, hàng hết | `422`, `403`, `404` hoặc `409` tùy tình huống |
| **Database/concurrency** | Bất biến còn đúng khi có race không? | Hai request cùng tạo một mã đơn duy nhất | Unique constraint, conditional update; chuyển lỗi có kiểm soát |
| **Response contract** | Response và lỗi có khớp tài liệu không? | Server công bố 201 nhưng trả field `id` sai kiểu | Contract test phải thất bại |

**Schema không đồng nghĩa với validation đầy đủ**. Schema có thể nói `quantity` là số nguyên từ 1 đến 1.000, nhưng không biết tenant có đủ hàng hay người dùng có quyền dùng `deliveryAddressId`. Ngược lại, chỉ kiểm tra trong service là quá muộn nếu parser đã cấp phát một body quá lớn; phải giới hạn kích thước/depth trước khi deserialize.

### 1.1. Mã HTTP phải theo hành vi thực tế

Ở ví dụ này ta chọn quy ước:

- `400`: JSON hỏng, không giải mã được, thiếu header bắt buộc hoặc không đúng cấu trúc để đọc.
- `422`: JSON đã đọc được thành DTO nhưng ràng buộc giá trị không hợp lệ, ví dụ `quantity` nhỏ hơn 1 hoặc `items` rỗng.
- `409`: xung đột với trạng thái hiện tại của resource, ví dụ kho đã hết tại thời điểm tạo đơn hoặc idempotency key được dùng lại cho payload khác.
- `415`: media type không hỗ trợ; `413`: body quá lớn; `401`/`403`: xác thực hoặc phân quyền không đạt.

Đây là **một lựa chọn hợp đồng**, không phải HTTP tự động quy định mọi lỗi Bean Validation phải trả 422. Spring MVC mặc định thường trả **400** cho `MethodArgumentNotValidException`. Một hệ thống chọn 400 cho toàn bộ lỗi đầu vào cũng có thể hợp lệ nếu nhất quán và ghi rõ trong OpenAPI. Test phải dựa vào **quy ước đã chọn**, tránh trộn 400/422 không chủ đích giữa các endpoint.

## 2. Viết schema làm nguồn tham chiếu cho request và response

OpenAPI 3.1 tương thích tốt hơn với JSON Schema 2020-12. Ví dụ hợp đồng tối thiểu:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /v1/orders:
    post:
      operationId: createOrder
      summary: Tạo đơn hàng
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Đơn hàng được tạo
          headers:
            Location:
              description: URI của đơn hàng
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderCreated'
        '400':
          description: JSON sai cú pháp hoặc không đọc được
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '409':
          description: Trạng thái nghiệp vụ xung đột
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '422':
          description: Dữ liệu không đạt ràng buộc giá trị
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '415':
          description: Media type không hỗ trợ
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
components:
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerEmail, items, deliveryAddressId]
      additionalProperties: false
      properties:
        customerEmail:
          type: string
          minLength: 1
          maxLength: 254
          format: email
        items:
          type: array
          minItems: 1
          maxItems: 100
          items:
            type: object
            required: [sku, quantity]
            additionalProperties: false
            properties:
              sku:
                type: string
                minLength: 1
                maxLength: 64
              quantity:
                type: integer
                minimum: 1
                maximum: 1000
        deliveryAddressId:
          type: string
          minLength: 1
          maxLength: 64
    OrderCreated:
      type: object
      required: [id, status]
      properties:
        id:
          type: string
        status:
          type: string
          enum: [CREATED]
    ApiProblem:
      type: object
      required: [type, title, status]
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        instance:
          type: string
          format: uri-reference
        code:
          type: string
        violations:
          type: array
          items:
            type: object
            required: [field, code, message]
            properties:
              field: {type: string}
              code: {type: string}
              message: {type: string}
~~~

Một bản đặc tả production còn cần mô tả `security`, response 401/403/413/429/5xx, ví dụ, giới hạn header, liên kết và các endpoint GET liên quan. Đoạn trên chỉ tập trung phần **kiểm thử schema và lỗi**.

### 2.1. Đừng coi mọi keyword được mọi công cụ thực thi giống nhau

Những điểm phải test cụ thể:

1. `required` bắt buộc **có mặt property**, nhưng không tự cấm mọi kiểu giá trị nếu schema của property cho phép. Với `type: string`, `null` không hợp lệ; với kiểu nullable trong OpenAPI 3.1 phải biểu diễn tường minh, ví dụ `type: [string, 'null']`.
2. `minLength: 1` không tự cấm `"   "`. `@NotBlank` trong Java sẽ từ chối whitespace; muốn schema và implementation sát nhau, bổ sung quy tắc tương ứng trong hợp đồng.
3. `format: email` hoặc `format: uri-reference` có thể được công cụ coi là **annotation** thay vì assertion tùy cấu hình validator và dialect. Không dùng duy nhất `format` để chứng minh dữ liệu đã đạt kiểm tra nghiệp vụ.
4. `additionalProperties: false` nói request không chấp nhận field ngoài schema. Nhưng Jackson mặc định của một dự án có thể **bỏ qua field lạ**. Muốn test khớp hợp đồng, phải cấu hình deserializer hoặc kiểm tra schema ở runtime; nếu có chủ trương forward-compatible, hãy chủ động cho phép field lạ trong cả docs lẫn code.
5. Từ JSON tới Java có thể xảy ra **coercion** như chuỗi `"2"` thành số 2 tùy cấu hình Jackson. Schema test riêng trên tài liệu không tự chứng minh API thật từ chối các kiểu đã được ép; cần kiểm thử HTTP.
6. `uniqueItems` (nếu dùng) so sánh tính duy nhất toàn phần tử JSON, không có nghĩa là “không trùng `sku`” khi `quantity` khác. Ràng buộc SKU duy nhất là kiểm tra ở tầng DTO/domain hoặc custom validator.

Hợp đồng nên định nghĩa rõ **field thiếu, field `null`, chuỗi trống, whitespace, số ngoài khoảng, field lạ, phần tử `null` trong array**. Đây là các ca dễ bị bỏ quên khi chỉ kiểm thử một JSON hợp lệ.

## 3. Bean Validation trong Spring: kiểm tra đúng chỗ

Với Spring Boot 3, thêm starter Bean Validation của Jakarta Validation nếu ứng dụng chưa có. Tạo DTO chỉ chứa các field client có quyền cung cấp:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

public record CreateOrderRequest(
    @NotBlank
    @Email
    @Size(max = 254)
    String customerEmail,

    @NotEmpty
    @Size(max = 100)
    List<@Valid LineItem> items,

    @NotBlank
    @Size(max = 64)
    String deliveryAddressId
) {
    public record LineItem(
        @NotBlank @Size(max = 64) String sku,
        @NotNull @Min(1) @Max(1000) Integer quantity
    ) {}
}
~~~

Khi controller dùng `@Valid @RequestBody`, Spring sẽ deserialize JSON bằng Jackson rồi gọi Bean Validation. Các ràng buộc có vai trò riêng:

| Annotation | Kiểm tra | Lưu ý |
| --- | --- | --- |
| `@NotNull` | Không cho `null` | Dùng `Integer` nếu cần phân biệt thiếu/`null` với giá trị 0; primitive `int` có mặc định 0 |
| `@NotEmpty` | Collection/string không rỗng | Không đảm bảo phần tử bên trong hợp lệ |
| `@NotBlank` | Chuỗi khác null và có ký tự không phải whitespace | Phù hợp ID/chuỗi bắt buộc, khác `minLength` thuần túy |
| `@Size` | Giới hạn độ dài chuỗi hoặc số phần tử collection | Không phải giới hạn kích thước byte toàn HTTP request |
| `@Min`/`@Max` | Giới hạn giá trị số | Không xử lý mọi nghiệp vụ như giới hạn tồn kho |
| `@Email` | Kiểm tra định dạng email theo provider | Không chứng minh mailbox tồn tại hoặc thuộc người dùng |
| `@Valid` | Kiểm tra object lồng trong DTO | Cần bật đúng vị trí để không bỏ qua `items[0]` |

Ví dụ `items: []` bị `@NotEmpty` từ chối; `items: [{"sku":"BOOK-42","quantity":0}]` bị `@Min(1)` từ chối; `quantity` thiếu sẽ thành `null` ở `Integer` và bị `@NotNull`. Nếu `items` chứa `null`, `@Valid` không tự cấm null phần tử. Với hợp đồng không cho null item, có thể dùng `List<@NotNull @Valid LineItem>` và thêm test tương ứng.

Khi dùng `additionalProperties: false` ở schema, cấu hình Jackson cùng chính sách trong ứng dụng, ví dụ Spring Boot:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Đây là cấu hình **toàn ứng dụng**; cần cân nhắc backward compatibility trước khi bật cho dự án đang có client thực tế. Không mặc định rằng một annotation trên DTO đã kích hoạt chặn field lạ toàn bộ. Với định dạng số, boolean, enum hoặc ngày tháng, cần quyết định có chấp nhận coercion không và kiểm thử request thực chứ không chỉ kiểm tra đối tượng Java sau deserialize.

### 3.1. Chưa đủ nếu nghiệp vụ sai

DTO hợp lệ vẫn có thể chứa hai dòng hàng trùng SKU, địa chỉ giao hàng thuộc tenant khác hoặc sản phẩm đã hết. Service phải kiểm tra những ràng buộc này ở ngữ cảnh đã xác thực, ví dụ:

~~~java
Set<String> seen = new HashSet<>();
for (CreateOrderRequest.LineItem item : request.items()) {
    if (!seen.add(item.sku())) {
        throw new InvalidOrderException("DUPLICATE_SKU");
    }
}
// Kiểm tra address thuộc principal/tenant đã xác thực.
// Kiểm tra hàng tồn trong transaction có khóa/conditional update cần thiết.
~~~

Ví dụ trên là trích đoạn service; `Set`/`HashSet` thuộc `java.util`. Các error code như `DUPLICATE_SKU` cần ánh xạ sang Problem Details. Không gửi nội dung exception nội bộ tới client.

**Validation cũng có race condition.** Kiểm tra “mã đơn chưa tồn tại” rồi mới ghi bằng hai request đồng thời có thể cùng vượt qua. Ràng buộc unique/foreign key hoặc conditional update ở DB là lớp bảo vệ cuối. Thất bại do tranh chấp cần được chuyển sang 409/422 phù hợp, chứ không lộ SQL exception hoặc trả 500 cho tình huống đã được dự liệu.

### 3.2. Validation không phải authorization

DTO không nên nhận `role`, `isAdmin`, `tenantId`, `unitPrice` như dữ liệu tin cậy của client. Giá, chủ sở hữu, tenant và quyền truy cập resource phải được xác định **server-side** từ principal và dữ liệu nghiệp vụ. JSON đúng schema không chứng minh người gọi có quyền. Test việc user A không thể xem/sửa đơn của user B là **security integration test**, không thể thay bằng schema test.

## 4. Problem Details: hợp đồng lỗi chuẩn hóa

**RFC 9457 Problem Details** định nghĩa cách mô tả lỗi dùng với HTTP. Media type JSON là `application/problem+json`. Một response minh họa cho lỗi validation:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/validation",
  "title": "Dữ liệu không hợp lệ",
  "status": 422,
  "detail": "Một hoặc nhiều trường không đạt ràng buộc.",
  "code": "VALIDATION_FAILED",
  "violations": [
    {
      "field": "items[0].quantity",
      "code": "OUT_OF_RANGE",
      "message": "Giá trị nằm ngoài khoảng cho phép."
    }
  ]
}
~~~

Các member **chuẩn** của Problem Details:

| Member | Ý nghĩa | Quy tắc nên áp dụng |
| --- | --- | --- |
| `type` | URI reference định danh **loại vấn đề** | Dùng URI ổn định, tốt nhất có tài liệu cho developer; mặc định có thể là `about:blank` |
| `title` | Tóm tắt ngắn của loại vấn đề | Nên ổn định theo type, có thể được bản địa hóa |
| `status` | Mã HTTP được mô tả | Cần khớp status thực trên response; không dùng thay HTTP status |
| `detail` | Mô tả cho lần xảy ra cụ thể | Viết an toàn, hữu ích, không phơi stack trace/thông tin nhạy cảm |
| `instance` | URI reference nhận diện lần xảy ra cụ thể | Tùy chọn; không bắt buộc phải bằng URI resource đang gọi |

`code` và `violations` trong ví dụ là **extension members do ứng dụng tự định nghĩa**, không phải trường bắt buộc của RFC 9457. Vì vậy client phải dựa vào tài liệu API để hiểu chúng. Nên giữ `code` ổn định qua thay đổi ngôn ngữ hiển thị; không parse nội dung tiếng Việt trong `detail` để quyết định hành vi.

**Thống nhất schema của vi phạm từng trường:** Ở ví dụ này `field` dùng đường dẫn gần với cách Bean Validation biểu diễn, ví dụ `items[0].quantity`. Nếu API chọn chuẩn **JSON Pointer (RFC 6901)** như `/items/0/quantity` thì phải dùng nhất quán, xử lý escape `~`/`/` đúng quy tắc và công bố trong docs. Không trả xen kẽ hai kiểu đường dẫn giữa các endpoint.

### 4.1. Khi nào không cần `violations`?

Một response 409 do hết tồn kho không nhất thiết có field sai; lỗi do **trạng thái hiện tại** thay đổi:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/inventory-conflict",
  "title": "Không thể tạo đơn ở trạng thái hiện tại",
  "status": 409,
  "detail": "Một mặt hàng không còn đủ tồn kho.",
  "code": "INVENTORY_CONFLICT"
}
~~~

Với `401 Unauthorized`, `403 Forbidden`, `404 Not Found` và `500`, thông điệp có thể cần **ít chi tiết hơn** để không lộ tài nguyên, danh tính hoặc cấu trúc hệ thống. Vị trí tạo response cũng khác nhau: một số lỗi bị Spring Security filter hoặc reverse proxy xử lý **trước** khi vào controller/advice; cần kiểm thử toàn bộ đường thực tế.

### 4.2. Những điều cần tránh

- Trả `HTTP 200` với body `{"success": false}` cho lỗi đầu vào; client, gateway và metric sẽ hiểu nhầm thành công.
- Trả `status: 422` trong JSON nhưng HTTP thực lại `500` hoặc `400`; hai lớp không nhất quán.
- Dùng exception message, SQL, access token, email, địa chỉ, giá trị nguyên của field bí mật trong `detail` hoặc `violations`.
- Dùng một URL `type` biến đổi cho từng request; `type` nên xác định **loại lỗi**, còn `instance` có thể gắn với occurrence.
- Cho client phụ thuộc vào thứ tự của mảng `violations`; nên chọn mã trường ổn định, trong test có thể sắp xếp để kết quả lặp lại.
- Ghi body raw của request vào log mỗi khi validation lỗi; log ngắn gọn theo code, endpoint và traceId, có lọc dữ liệu nhạy cảm.

## 5. Spring MVC: trả lỗi có cấu trúc và dễ kiểm thử

Giả sử `OrderService` đã xử lý authorization và nghiệp vụ; controller tập trung hợp đồng HTTP:

~~~java
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @PostMapping(value = "/v1/orders",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderCreated> create(
            @Valid @RequestBody CreateOrderRequest request,
            Authentication authentication) {
        // SecurityFilterChain yêu cầu login và service kiểm tra quyền thực tế.
        String principal = authentication.getName();
        OrderCreated created = orders.create(principal, request);
        return ResponseEntity
            .created(URI.create("/v1/orders/" + created.id()))
            .body(created);
    }
}

record OrderCreated(String id, String status) {}

interface OrderService {
    OrderCreated create(String trustedPrincipal,
                        CreateOrderRequest request);
}
~~~

Trong ứng dụng production, principal phải do Spring Security xác thực; service phải kiểm tra tenant/resource và dùng dữ liệu server làm nguồn sự thật. Trường hợp request bị chặn ở filter bảo mật có thể trả 401/403 trước khi controller chạy. Ví dụ dự kiến xử lý hợp lệ trả `201 Created` và header `Location`, theo hợp đồng OpenAPI ở trên.

### 5.1. Map lỗi DTO, JSON parser và xung đột nghiệp vụ

Tạo một `@RestControllerAdvice` với mã HTTP và error code rõ:

~~~java
import java.net.URI;
import java.util.Comparator;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

@RestControllerAdvice
public class ApiProblemAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> validation(
            MethodArgumentNotValidException exception) {

        List<Violation> fields = exception.getBindingResult()
            .getAllErrors()
            .stream()
            .map(error -> new Violation(
                error instanceof FieldError fe ? fe.getField() : "$",
                safeCode(error),
                safeMessage(error)
            ))
            .sorted(Comparator
                .comparing(Violation::field)
                .thenComparing(Violation::code))
            .toList();

        ProblemDetail p = newProblem(
            422, "validation", "Dữ liệu không hợp lệ",
            "VALIDATION_FAILED",
            "Một hoặc nhiều trường không đạt ràng buộc."
        );
        p.setProperty("violations", fields);
        return asResponse(422, p);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ProblemDetail> invalidJson(
            HttpMessageNotReadableException exception) {
        ProblemDetail p = newProblem(
            400, "invalid-json", "Không đọc được JSON",
            "INVALID_JSON", "Body sai cú pháp hoặc kiểu dữ liệu."
        );
        return asResponse(400, p);
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ProblemDetail> unsupportedMedia(
            HttpMediaTypeNotSupportedException exception) {
        ProblemDetail p = newProblem(
            415, "unsupported-media-type", "Media type không hỗ trợ",
            "UNSUPPORTED_MEDIA_TYPE",
            "Endpoint yêu cầu Content-Type: application/json."
        );
        return asResponse(415, p);
    }

    @ExceptionHandler(OrderConflictException.class)
    public ResponseEntity<ProblemDetail> conflict(
            OrderConflictException exception) {
        ProblemDetail p = newProblem(
            409, "inventory-conflict",
            "Không thể tạo đơn ở trạng thái hiện tại",
            "INVENTORY_CONFLICT",
            "Một mặt hàng không còn đủ tồn kho."
        );
        return asResponse(409, p);
    }

    private static ProblemDetail newProblem(
            int status, String type, String title,
            String code, String detail) {
        ProblemDetail p = ProblemDetail.forStatus(status);
        p.setType(URI.create("https://api.example.com/problems/" + type));
        p.setTitle(title);
        p.setDetail(detail);
        p.setProperty("code", code);
        return p;
    }

    private static ResponseEntity<ProblemDetail> asResponse(
            int status, ProblemDetail p) {
        return ResponseEntity.status(status)
            .contentType(MediaType.valueOf("application/problem+json"))
            .header("Cache-Control", "no-store")
            .body(p);
    }

    private static String safeCode(ObjectError error) {
        String raw = error.getCode();
        return switch (raw == null ? "" : raw) {
            case "NotBlank", "NotEmpty", "NotNull" -> "REQUIRED";
            case "Min", "Max", "Size" -> "OUT_OF_RANGE";
            case "Email" -> "INVALID_EMAIL";
            default -> "INVALID_VALUE";
        };
    }

    private static String safeMessage(ObjectError error) {
        return switch (safeCode(error)) {
            case "REQUIRED" -> "Trường bắt buộc.";
            case "OUT_OF_RANGE" -> "Giá trị nằm ngoài khoảng cho phép.";
            case "INVALID_EMAIL" -> "Định dạng email không hợp lệ.";
            default -> "Giá trị không hợp lệ.";
        };
    }

    public record Violation(
        String field, String code, String message
    ) {}
}

class OrderConflictException extends RuntimeException {}
~~~

Đoạn code dùng Spring MVC `ProblemDetail` (Spring Framework 6+) và trả body ở media type chuẩn. `ProblemDetail` hỗ trợ extension properties; khi được serialize bởi Spring MVC/Jackson tích hợp, `code` và `violations` xuất hiện như các trường JSON mở rộng. Chỉ lấy **mã lỗi đã ánh xạ** và thông điệp cố định, không serialize `exception.getMessage()` hoặc `FieldError.getRejectedValue()` ra client. Với class-level validation, `"$"` trong ví dụ biểu thị lỗi không quy cho một field cụ thể.

Ở ví dụ trên, `MethodArgumentNotValidException` được ánh xạ thành 422 theo hợp đồng. Nếu API chọn 400, hãy đồng bộ cả handler, OpenAPI và test. Với `ConstraintViolationException` từ tham số `@RequestParam`/`@PathVariable` hoặc method validation ở service, cần bộ xử lý riêng phù hợp với ý nghĩa lỗi; Spring Framework 6.1+ còn có `HandlerMethodValidationException`. Không kết luận rằng chỉ một advice đã bao phủ mọi nguồn validation.

Đối với HTTP 401/403 do Spring Security filter tạo, cấu hình `AuthenticationEntryPoint`/`AccessDeniedHandler` để dùng định dạng lỗi thích hợp. Với 413 tại gateway, ingress có thể tự trả HTML; muốn mọi lỗi cùng `application/problem+json` phải kiểm thử cả gateway. Nếu API phục vụ browser xuyên origin, phản hồi lỗi cho origin **được cho phép** cũng cần CORS header đúng, nếu không frontend chỉ thấy lỗi CORS.

## 6. Viết test cho điều kiện đúng, sai và ranh giới

Một **schema test** xác nhận ví dụ dữ liệu đáp ứng một schema; một **HTTP integration test** xác nhận server thật trả đúng phản hồi. Cần cả hai: một bộ tài liệu OpenAPI đúng vẫn vô ích nếu controller chấp nhận/loại dữ liệu trái hợp đồng.

| Request | Tầng được kiểm tra | Kỳ vọng của ví dụ |
| --- | --- | --- |
| Request hợp lệ, có quyền | HTTP + DTO + service | 201, `Location`, JSON `OrderCreated` |
| Body JSON thiếu dấu đóng | Parser | 400, `INVALID_JSON` |
| `quantity` là object | Jackson binding | 400, `INVALID_JSON` |
| `items: []` | Bean Validation | 422, `VALIDATION_FAILED` |
| `quantity: 0` | Nested Bean Validation | 422, `violations` chỉ ra `items[0].quantity` |
| Thiếu `quantity` | `@NotNull` | 422 |
| `customerEmail` chỉ chứa khoảng trắng | `@NotBlank` | 422 |
| `items` có 101 phần tử | `@Size(max = 100)` | 422 |
| Thêm field `isAdmin` ở root | Parser với strict unknown fields | 400 |
| `Content-Type: text/plain` | HTTP media negotiation | 415 |
| Địa chỉ thuộc tenant khác | Authorization nghiệp vụ | 403/404 theo hợp đồng, không tạo đơn |
| Đơn xung đột vì hàng đã hết | Domain/DB | 409, `INVENTORY_CONFLICT` |
| Payload vượt trần byte hoặc depth | Ingress/parser | 413/400 theo giới hạn đã cấu hình |

### 6.1. MockMvc: kiểm tra Problem Details ở mức HTTP

Ví dụ trích đoạn test sử dụng `MockMvc` với controller, validation starter và advice ở trên:

~~~java
// Giả sử mockMvc đã được inject và có ApiProblemAdvice,
// OrderController, ObjectMapper/Bean Validation trong test context.
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

@Test
void quantityZeroReturns422ProblemDetail() throws Exception {
    mockMvc.perform(post("/v1/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerEmail": "linh@example.com",
                  "items": [{"sku": "BOOK-42", "quantity": 0}],
                  "deliveryAddressId": "ADDR-100"
                }
                """))
        .andExpect(status().is(422))
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.valueOf("application/problem+json")))
        .andExpect(jsonPath("$.status").value(422))
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.violations[0].field")
            .value("items[0].quantity"))
        .andExpect(jsonPath("$.violations[0].code")
            .value("OUT_OF_RANGE"));
}

@Test
void malformedJsonReturns400WithoutStackTrace() throws Exception {
    mockMvc.perform(post("/v1/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"items\": ["))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("INVALID_JSON"))
        .andExpect(jsonPath("$.detail")
            .value("Body sai cú pháp hoặc kiểu dữ liệu."))
        .andExpect(jsonPath("$.stackTrace").doesNotExist());
}

@Test
void unsupportedMediaTypeReturns415() throws Exception {
    mockMvc.perform(post("/v1/orders")
            .contentType(MediaType.TEXT_PLAIN)
            .content("hello"))
        .andExpect(status().isUnsupportedMediaType())
        .andExpect(jsonPath("$.code")
            .value("UNSUPPORTED_MEDIA_TYPE"));
}
~~~

Ở test context đã bật Spring Security, ba request trên có thể bị chặn **401/403 trước validation** nếu không có xác thực phù hợp. Cần dùng principal test (`@WithMockUser` hoặc mock JWT có claim phù hợp), cấp CSRF token khi chính sách yêu cầu, hoặc tạo MVC slice riêng để chỉ test validation và viết security integration test độc lập. **Không tắt bảo mật trong ứng dụng production để khiến test 422 đi qua**.

### 6.2. Kiểm tra request hợp lệ và service không bị gọi khi input sai

Với request hợp lệ, mock `OrderService` trả một resource; assert 201, `Location` và body có trường theo schema. Với request bị từ chối ở parser/Bean Validation, thêm Mockito `verifyNoInteractions(orders)` để chứng minh nghiệp vụ **không chạy** khi đầu vào không hợp lệ.

~~~java
// Giả sử orders là Mockito mock đã inject vào controller.
@Test
void missingQuantityNeverCallsService() throws Exception {
    mockMvc.perform(post("/v1/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerEmail": "linh@example.com",
                  "items": [{"sku": "BOOK-42"}],
                  "deliveryAddressId": "ADDR-100"
                }
                """))
        .andExpect(status().is(422))
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));

    verifyNoInteractions(orders);
}
~~~

Không chỉ test response code. Assert thêm `Content-Type`, `type`, `status` khớp HTTP, `code` ổn định, `violations` có field cần thiết và **không chứa dữ liệu nhạy cảm**. Khi có nhiều lỗi, đừng phụ thuộc vào thứ tự validator trả về; dùng tập hợp/JSONPath phù hợp hoặc tự sắp xếp ở handler như ví dụ.

### 6.3. Tạo dữ liệu test ở ranh giới

Đối với `items` có tối đa 100 phần tử, tối thiểu phải có ca 0, 1, 100 và 101. Đối với `quantity` từ 1 đến 1.000, kiểm tra 0, 1, 1.000 và 1.001. Thêm null, thiếu property và sai kiểu. Với `sku` dài tối đa 64, kiểm tra chuỗi ASCII và Unicode; `@Size` đếm độ dài theo quy tắc Java/Bean Validation, **không phải byte UTF-8**.

Đừng tạo JSON vượt 1 MiB rồi suy ra DTO validation có trách nhiệm trả 413: đây là trần byte của HTTP server/gateway, nên test ở integration environment thật. Tương tự, JSON lồng quá sâu bị Jackson từ chối trước Bean Validation; lỗi phải ở parser stage, thường là 400. Khi request sử dụng `Transfer-Encoding: chunked` và thiếu `Content-Length`, trần byte vẫn phải được áp bằng số byte thực nhận.

## 7. Schema test và contract test: kiểm tra cả hai chiều

### 7.1. Validate mẫu JSON theo schema

Tạo bộ mẫu hợp lệ/bất hợp lệ và cho **JSON Schema validator** chạy trên `CreateOrderRequest`. Với OpenAPI 3.1, xác nhận công cụ chọn đúng dialect và cấu hình `format` assertions theo chủ đích. Ví dụ:

~~~json
{
  "customerEmail": "linh@example.com",
  "items": [{"sku": "BOOK-42", "quantity": 2}],
  "deliveryAddressId": "ADDR-100"
}
~~~

Các mẫu phản ví dụ:

~~~json
{"customerEmail":"linh@example.com","items":[],"deliveryAddressId":"ADDR-100"}
~~~

~~~json
{
  "customerEmail": "linh@example.com",
  "items": [{"sku": "BOOK-42", "quantity": 1001}],
  "deliveryAddressId": "ADDR-100"
}
~~~

~~~json
{
  "customerEmail": "linh@example.com",
  "items": [{"sku": "BOOK-42", "quantity": 2}],
  "deliveryAddressId": "ADDR-100",
  "role": "ADMIN"
}
~~~

Trong bộ mẫu này, cả ba phải bị schema từ chối vì `minItems`, `maximum` hoặc `additionalProperties: false`. Kết quả schema test **không đủ** để nói ứng dụng HTTP sẽ trả 422: server có thể deserialize/bind khác. Vì vậy cần chạy cùng các mẫu qua API thật để xác minh sự đồng nhất.

### 7.2. Validate response của API theo OpenAPI

Một contract test tốt không chỉ kiểm request; nó phải bắt được các lỗi như:

- `201` không có `Location` trong khi hợp đồng yêu cầu.
- `OrderCreated.id` biến thành số hoặc `status` trả giá trị ngoài enum đã công bố.
- `422` trả `text/html` do gateway, hoặc `application/json` với cấu trúc `{"error":"bad"}` thay vì `application/problem+json`.
- `ProblemDetail.status` không trùng mã HTTP thực; `type`/`code` sai so với loại lỗi.
- Một bản release vô tình xóa field bắt buộc hoặc đổi kiểu mà chưa cập nhật version/hợp đồng.

Có thể dùng công cụ validate OpenAPI request/response trong test hoặc dựng test harness đọc OpenAPI rồi thực hiện HTTP, không cần phụ thuộc vào một thư viện cụ thể. Với API công khai cho đối tác, chạy **provider contract test** và một bộ **consumer-driven contract** cho các client quan trọng. Schema chỉ mô tả dữ liệu, còn điều kiện nghiệp vụ như “`GET` sau `POST` trả bản ghi của đúng chủ sở hữu” cần scenario/integration test bổ sung.

### 7.3. Định nghĩa tương thích khi API phát triển

Thêm field **bắt buộc** vào request có thể làm client cũ lỗi. Đổi `quantity` từ integer sang string, hạ `maxItems`, đổi `type`/`code`, hoặc chuyển status 400 thành 422 cũng có thể là thay đổi phá vỡ hợp đồng. Thêm field tùy chọn vào response thường dễ tương thích hơn **nếu** client cho phép unknown fields; khi dùng strict decoder ở client, điều này vẫn có thể làm vỡ tích hợp.

Khi thay đổi schema, lưu bộ payload và response đại diện từ các phiên bản client, chạy regression với OpenAPI diff và contract test, đồng thời thông báo chính sách deprecation/versioning. Không tự động lấy “schema mới được validate” làm bằng chứng client cũ vẫn chạy.

## 8. Negative test, bảo mật và tải

Validation là một phần của bề mặt tấn công. Những ca sau đáng có bên cạnh test functional:

| Nhóm | Input cần thử | Điều cần kiểm chứng |
| --- | --- | --- |
| **JSON parser** | JSON sâu hàng trăm mức, chuỗi/số cực dài | Giới hạn depth/token; phản hồi có kiểm soát, không 500 |
| **Kích thước** | Body vượt trần, kể cả chunked hoặc đã giải nén | 413; không cấp phát body không giới hạn |
| **Coercion** | `"quantity": "2"`, `1.5`, `true`, `null` | Server chấp nhận hay từ chối đúng chính sách kiểu đã công bố |
| **Duplicate JSON keys** | Hai `quantity` khác nhau trong cùng object | Các tầng không diễn giải mâu thuẫn, cân nhắc từ chối |
| **Mass assignment** | Client thêm `tenantId`, `isAdmin`, `price` | Không ghi field nhạy cảm, strict schema nếu được khai báo |
| **Authorization** | Dùng ID resource thuộc tenant khác | 403/404 không rò thông tin; validation không làm lộ dữ liệu |
| **Nhiều vi phạm** | 10 trường không hợp lệ một lúc | Message an toàn, kích thước lỗi được giới hạn |
| **Content negotiation** | Accept không phù hợp, media type không hỗ trợ | Status 406/415 khi thích hợp; error representation nhất quán |
| **Rate/concurrency** | Flood payload hợp lệ và nhiều request song song | Có 429/503/admission limit; service không suy sụp |
| **Error path** | Database timeout, exception bất ngờ, gateway 502 | Không lộ nội bộ; traceId và metric hỗ trợ điều tra |

Đặc biệt, **không trả lại toàn bộ giá trị bị từ chối** trong `violations`. Với field `password`, token, email hay địa chỉ giao hàng, một lỗi về format không được trở thành nơi phát tán dữ liệu. Không đưa raw request vào log mà không lọc. Nên giới hạn số `violations` và kích thước message để kẻ tấn công không dùng lỗi validation làm công cụ khuếch đại response.

### 8.1. Thực hành fuzz/property-based testing

Thay vì viết tay hàng trăm ví dụ, có thể dùng generator tạo:

- JSON object với field thiếu/thừa/null, độ dài chuỗi 0–300, mảng 0–150 phần tử.
- Số ở ranh giới và ngoài khoảng, ký tự Unicode, escape sequence, duplicate key.
- Combination giữa header `Content-Type`, authentication và payload.

Tạo **invariant**: mọi input không hợp lệ bị từ chối trước khi gọi service; mọi response lỗi đều có HTTP status khớp JSON `status`; không có stack trace; request vượt giới hạn không gây out-of-memory; sai authorization không để lộ dữ liệu. Seed của generator phải được ghi lại để tái hiện lỗi; áp giới hạn thời gian và dung lượng cho các test tải/fuzz.

### 8.2. Kiểm thử nhiều lớp

~~~mermaid
flowchart TD
    S[OpenAPI 3.1 + JSON Schema] --> C[Contract tests]
    V[DTO + Bean Validation] --> U[Unit tests]
    A[Spring MVC Advice] --> M[MockMvc HTTP tests]
    B[Business + Database] --> I[Integration tests]
    G[Gateway / Spring Security] --> E[End-to-end tests]
    C --> R[Regression / CI]
    U --> R
    M --> R
    I --> R
    E --> R
~~~

**Unit test** phù hợp custom validator, đối tượng ranh giới. **MockMvc** phù hợp HTTP controller/advice, body JSON, media type, mã lỗi. **Integration test** cần DB thật hoặc tương đương đáng tin cho unique constraint, transaction và xung đột đồng thời. **End-to-end** kiểm tra gateway, giới hạn byte, TLS, CORS, Spring Security và phản hồi lỗi từ proxy. Không cần nhân đôi toàn bộ ca ở mọi tầng; đặt test ở nơi nó chứng minh đúng hành vi và chọn vài hành trình liên tầng quan trọng.

## 9. Quy trình chẩn đoán khi test thất bại

Một ca `quantity=0` lẽ ra trả 422 nhưng thực tế trả 400, 401 hoặc 500. Hãy lần theo thứ tự:

1. **401/403**: Spring Security chặn trước khi controller? Thiếu token/CSRF? Test có principal đúng quyền không?
2. **415**: `Content-Type` sai hoặc endpoint `consumes` không khớp?
3. **400**: Jackson không deserialize được, hay Bean Validation đang dùng quy ước 400 mặc định? Kiểm tra exception được xử lý **bên trong server** nhưng không lộ raw exception cho client.
4. **422 không có `violations`**: Advice có được load không, có dùng `@Valid` đúng vị trí và có Bean Validation provider không?
5. **200/201 dù input sai**: Có dùng `@Valid` trên `@RequestBody`? DTO có ràng buộc nested? Mapper đang bỏ qua field lạ hoặc ép kiểu?
6. **500**: Exception nghiệp vụ hoặc lỗi DB chưa được ánh xạ? Có race hoặc uniqueness violation chưa được xử lý?
7. **Frontend báo CORS**: API có thể đã trả 422/401 nhưng browser không cho đọc vì lỗi CORS header trên error path. Xem request và response trong Network.

Đọc log/tracing đã được che dữ liệu nhạy cảm để xác định **lớp xử lý thực sự**, rồi sửa nguồn gốc. Không đổi toàn bộ exception thành 200 chỉ để test “xanh”, cũng không tắt validation/CSRF mà không có thiết kế bảo mật thay thế.

## 10. Bài tập thực hành

**Bài 1 — Khớp schema và DTO.** Dựa trên `CreateOrderRequest`, chỉ ra mọi khác biệt giữa JSON Schema và Bean Validation liên quan đến chuỗi chỉ chứa whitespace, email format, field lạ, coercion và phần tử null trong array. Đề xuất sửa schema, DTO hoặc cấu hình Jackson để cả ba cùng tuân thủ hợp đồng.

**Bài 2 — Hoàn thiện exception handler.** Mở rộng `ApiProblemAdvice` xử lý lỗi class-level và validation tham số query/path theo phiên bản Spring đang dùng. Đặt thống nhất status 400/422, `type`, `code`; viết test bảo đảm không đưa rejected value hoặc stack trace ra client.

**Bài 3 — Bộ test ranh giới.** Viết test với `MockMvc` cho `items` có 0, 1, 100, 101 phần tử; `quantity` bằng 0, 1, 1000, 1001; `sku` dài 0, 1, 64, 65; JSON thiếu field, null, sai kiểu, field ngoài schema. Với mọi lỗi parser/DTO, xác minh `OrderService` không được gọi.

**Bài 4 — Contract drift.** API hiện trả `201` với `{"id":"ord-1","status":"CREATED"}`. Một bản refactor đổi `id` thành số `1`, và một gateway đổi response lỗi 422 sang HTML. Thiết kế bộ kiểm thử dùng OpenAPI/schema và HTTP integration để bắt cả hai regression; giải thích tại sao chỉ test DTO input là chưa đủ.

**Bài 5 — Kiểm thử bảo mật.** Người dùng A gửi `deliveryAddressId` thuộc người dùng B, đồng thời thêm field `unitPrice` và `tenantId` trong JSON. Hãy xác định kiểm soát ở schema/parser, authorization và service/DB; thiết kế assertion chứng minh không tạo đơn, không lộ sự tồn tại của resource nhạy cảm và không tin giá do client cung cấp.

**Đáp án định hướng:** (1) `minLength` không tương đương `@NotBlank`, `format` có thể không được thực thi, unknown fields/coercion/null item cần chính sách rõ. (2) Không dùng exception message hoặc rejected value; quy ước 400/422 nhất quán và test đúng lớp. (3) Kết hợp boundary + negative, xác minh HTTP và việc không gọi service. (4) Kiểm cả response schema, media type và status; drift có thể xuất hiện ở gateway. (5) Schema chỉ kiểm hình dạng; principal/tenant server-side và kiểm tra quyền ở service là bắt buộc.
