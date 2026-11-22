# Thêm trường, thêm enum và client không chấp nhận dữ liệu lạ

> **Module:** `INTEGRATION_API_REST` — chương **Tiến hóa API**. Bài học phân tích khả năng tương thích của REST API khi mở rộng JSON response: thêm property mới, thêm giá trị enum mới và cách client xử lý dữ liệu chưa biết. Người học thực hành thiết kế hợp đồng resource, URI, HTTP status, OpenAPI và Java/Spring; kết hợp bảo mật, chiến lược rollout và kiểm thử consumer. Mục tiêu là **phát triển API mà không âm thầm làm hỏng client đã triển khai**.

## 1. Tình huống: backend thêm một field, ứng dụng cũ ngừng hoạt động

Một ứng dụng mobile đã phát hành gọi `GET /v1/orders/ord_916`. Representation ban đầu:

~~~json
{
  "id": "ord_916",
  "status": "PAID",
  "currency": "VND",
  "totalAmount": "250000"
}
~~~

Backend triển khai tính năng dự kiến giao hàng và bổ sung `estimatedDeliveryAt`:

~~~json
{
  "id": "ord_916",
  "status": "PAID",
  "currency": "VND",
  "totalAmount": "250000",
  "estimatedDeliveryAt": "2026-11-21T10:00:00Z"
}
~~~

Client chỉ đọc field đã biết vẫn chạy được; SDK bật `FAIL_ON_UNKNOWN_PROPERTIES` hoặc validator đóng schema lại có thể ném lỗi và làm hỏng màn hình.

Vấn đề tương tự xuất hiện khi backend mở thêm trạng thái:

~~~json
{
  "id": "ord_916",
  "status": "AWAITING_VERIFICATION",
  "currency": "VND",
  "totalAmount": "250000"
}
~~~

Đây là **giá trị mới của field cũ**. Client có thể parse lỗi vì enum đóng, hoặc rơi vào nhánh mặc định xử lý như `PAID` và đề nghị thao tác sai.

**Thông điệp:** “chỉ thêm” trên wire format **không tự động đồng nghĩa** “tương thích với mọi client”. Phải xét parser, code sinh từ OpenAPI, nghiệp vụ, tính bắt buộc của field, cách hiển thị và quyền.

### Mục tiêu học tập

Sau bài, người học có thể đánh giá **backward/forward compatibility**, viết Java tolerant reader với enum fallback an toàn; thiết kế request DTO chặt chẽ trong Spring, OpenAPI phản ánh enum mở/đóng và kiểm thử rollout nhiều phiên bản.

## 2. Tương thích không có một chiều duy nhất

Giả sử server `S1` đang chạy, client `C1` đã phát hành. Sau đó lần lượt có `S2` và `C2`:

| Câu hỏi | Ví dụ kiểm chứng |
|---|---|
| **Client cũ dùng server mới?** | `C1` đọc response của `S2` đã thêm `estimatedDeliveryAt` và trạng thái mới |
| **Client mới dùng server cũ?** | `C2` hoạt động khi `S1` chưa có field mới |
| **Hai phiên bản chạy cùng lúc?** | Mobile cũ, web mới và nhiều replica server triển khai không đồng bộ |
| **Dữ liệu cũ vẫn hợp lệ?** | JSON, event, cache hoặc snapshot lưu từ trước |

Triển khai cần hỗ trợ **giai đoạn trộn phiên bản**; mobile không cập nhật đồng thời với backend.

### 2.1. Tolerant reader là gì?

*Tolerant reader* chỉ giải mã **dữ liệu thực sự cần**, không yêu cầu representation có đúng một tập property cố định khi schema công bố cho phép mở rộng. Ví dụ client hiển thị `id` và `status` có thể bỏ qua `estimatedDeliveryAt` mà nó chưa hỗ trợ.

**Response:** chấp nhận field mới theo hợp đồng nhưng kiểm tra field thiết yếu. **Enum mới:** có fallback an toàn, không suy thành trạng thái cũ. **Request:** server có thể từ chối field lạ để tránh mass assignment hoặc lỗi gõ tên.

Đó không phải quy tắc “bỏ qua mọi dữ liệu lạ ở mọi nơi”. Mức độ linh hoạt phải **theo hướng trao đổi dữ liệu và rủi ro nghiệp vụ**.

### 2.2. Phân biệt thay đổi ở response và request

| Thay đổi | Tương thích thường gặp | Điều kiện |
|---|---|---|
| Thêm property **tùy chọn** trong response | Thường có thể tương thích | Client đọc linh hoạt; không làm đổi nghĩa field cũ |
| Thêm property **bắt buộc** trong request | **Breaking** đối với client cũ | Client cũ không biết gửi field |
| Thêm property **tùy chọn** trong request | Thường tương thích với client cũ | Có default an toàn, không đổi nghĩa request cũ |
| Thêm giá trị enum trong response | **Có rủi ro breaking** | Client không dùng enum đóng hoặc có xử lý giá trị lạ |
| Thêm giá trị enum được chấp nhận trong request | Có thể tương thích với request cũ | Server vẫn hiểu giá trị cũ; contract và auth rõ |
| Đổi tên hoặc xóa property cũ | Thường breaking | Client cũ còn phụ thuộc field |
| Đổi kiểu `"250000"` sang số `250000` | Breaking với parser nghiêm | Thay đổi wire type |
| Đổi field từ luôn có giá trị sang có thể `null` | Có rủi ro breaking | Client không null-safe có thể lỗi |
| Đổi semantics của một trạng thái cũ | **Breaking về nghiệp vụ** | Dù JSON không đổi |

Vẫn phải kiểm thử **consumer thực tế**: `additionalProperties: false`, SDK enum đóng hoặc constraint mới có thể biến thay đổi tưởng là additive thành breaking.

## 3. Thêm field: “optional” là điều kiện cần, chưa đủ

Giả sử backend muốn trả thêm:

~~~json
{
  "id": "ord_916",
  "status": "PAID",
  "currency": "VND",
  "totalAmount": "250000",
  "estimatedDeliveryAt": "2026-11-21T10:00:00Z",
  "delivery": {
    "method": "HOME",
    "window": "MORNING"
  }
}
~~~

### 3.1. Giữ bất biến của trường cũ

Khi mở rộng response:

- Không đổi `id` từ string sang number, không đổi `totalAmount` từ chuỗi decimal sang kiểu float chỉ vì client mới hỗ trợ.
- Không đổi đơn vị hoặc múi giờ ngầm; `estimatedDeliveryAt` cần mô tả timestamp theo RFC 3339, và có thể chưa xác định được.
- Không làm `status` mang nghĩa khác với trước. Nếu bắt đầu hoàn tiền mà vẫn trả `PAID` nhưng đổi ý nghĩa của `totalAmount`, có thể phá logic dù schema vẫn hợp lệ.
- Không tự thêm field nhạy cảm (`internalRiskScore`, địa chỉ người khác, token) với lý do “client cũ sẽ bỏ qua”.

### 3.2. Phân biệt **vắng mặt**, **null** và **giá trị**

Các JSON sau không nhất thiết tương đương:

~~~json
{"id":"ord_916","status":"PAID"}
~~~

~~~json
{"id":"ord_916","status":"PAID","estimatedDeliveryAt":null}
~~~

~~~json
{"id":"ord_916","status":"PAID","estimatedDeliveryAt":"2026-11-21T10:00:00Z"}
~~~

Định nghĩa rõ:

| Trạng thái property | Ý nghĩa đề xuất |
|---|---|
| Không có property | Server cũ chưa hỗ trợ hoặc tính năng không được trả trong representation đó |
| `null` | Server hỗ trợ field nhưng **chưa có giá trị xác định** |
| Có timestamp | Dự kiến giao tại thời điểm cụ thể |

Nếu chọn coi vắng mặt và null tương đương, phải ghi rõ trong contract.

### 3.3. Field mới và cache / ETag

Nếu representation trả thêm field, body của cùng resource đã thay đổi. Với strong `ETag`, phải đánh giá lại validator để nó phản ánh **representation được chọn**; không giữ validator cũ trong khi byte representation đã đổi. Client gọi GET với `If-None-Match` có thể cần nhận `200` và ETag mới; client gửi `If-Match` để chỉnh sửa cũng phải tuân thủ precondition đúng.

Không dùng trường mới trong ETag để lén phá mọi lần chỉnh sửa nếu API không thiết kế validator nhất quán giữa các biến thể representation; cần phân biệt **thay đổi representation** với **version business state**, và công bố chính sách conditional requests.

## 4. Thêm enum: rủi ro lớn hơn thêm property

Ban đầu `status` chỉ có:

~~~text
PENDING_PAYMENT | PAID | SHIPPED | DELIVERED | CANCELLED
~~~

Backend thêm `AWAITING_VERIFICATION` để chờ xác minh gian lận. Những client cũ có thể không biết đây là trạng thái tạm thời, và **không nên cho phép hủy/đổi địa chỉ/thanh toán** chỉ vì trạng thái không nằm trong danh sách cũ.

### 4.1. Enum đóng và enum mở có kỳ vọng khác nhau

- **Closed enum:** tài liệu nói chỉ có các giá trị đã liệt kê, client được phép xử lý đầy đủ chúng bằng `switch` không có nhánh unknown. Thêm giá trị là breaking change trong mô hình này.
- **Open/extensible enum:** tài liệu công bố các giá trị **đang biết**, đồng thời nói giá trị mới có thể xuất hiện. Client phải có nhánh unknown an toàn. Dù vậy, API vẫn kiểm soát tập giá trị hợp lệ phía producer.

Không thể vừa hứa “enum đóng” vừa bổ sung giá trị tùy ý vào response rồi nói đó là thay đổi hoàn toàn tương thích.

### 4.2. Chính sách xử lý trạng thái lạ

~~~mermaid
flowchart TD
    A["Nhận GET /orders/{id}"] --> B{"Parse JSON cấu trúc chính?"}
    B -- "Sai kiểu / thiếu dữ liệu thiết yếu" --> X["Báo lỗi hợp đồng; không thực thi action"]
    B -- "Đúng" --> C{"Status đã biết?"}
    C -- "Có" --> D["Áp dụng logic của status đã biết"]
    C -- "Không" --> E["UNKNOWN: hiển thị thông báo trung tính"]
    E --> F["Tắt thao tác nguy hiểm; có thể refresh/cập nhật client"]
    D --> G["Kiểm tra quyền và affordance hiện hành"]
    F --> G
~~~

**Không** viết:

~~~java
// Phản mẫu: giả định mọi giá trị khác CANCELLED đều có thể thanh toán.
boolean canPay = status != OrderStatus.CANCELLED;
~~~

Thay vào đó:

~~~java
// Chỉ chủ động cho phép trường hợp đã biết và đủ điều kiện.
boolean canPay = status == OrderStatus.PENDING_PAYMENT
    && hasPayPermission
    && serverOffersPaymentAction;
~~~

Client vẫn là tầng UX; **server phải kiểm lại quyền và trạng thái** tại thời điểm POST thanh toán. Khi gặp `UNKNOWN`, mặc định **không phát lệnh có tác động** và đưa thông báo trung tính như “Trạng thái đang được xử lý; vui lòng cập nhật ứng dụng hoặc thử lại sau”.

### 4.3. Vì sao fallback “UNKNOWN” không giải quyết mọi việc?

Với enum quyết định quyền, hoàn tiền hoặc hành động nhạy cảm, client có thể **hiển thị thông tin an toàn nhưng chặn action**. Nếu không thể xử lý hợp lệ thì phải dùng capability/version contract riêng. Giá trị mới là **chuỗi enum chưa biết**; field thiếu, null hoặc sai kiểu là **lỗi cấu trúc**, không được âm thầm coi là enum tương lai.

## 5. Java 17 + Jackson: tolerant reader có giới hạn

### 5.1. Phản mẫu: DTO đóng cứng toàn bộ response

~~~java
public record OrderResponse(
    String id,
    OrderStatus status,
    String currency,
    String totalAmount
) {}

public enum OrderStatus {
    PENDING_PAYMENT, PAID, SHIPPED, DELIVERED, CANCELLED
}
~~~

Với một `ObjectMapper` cấu hình `FAIL_ON_UNKNOWN_PROPERTIES=true`, JSON có `estimatedDeliveryAt` sẽ bị từ chối. Ngay cả khi bỏ qua property mới, mapper vẫn có thể ném lỗi khi enum nhận `AWAITING_VERIFICATION`.

### 5.2. Client DTO chỉ nhận các field đã biết

~~~java
import com.fasterxml.jackson.annotation.JsonEnumDefaultValue;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderView(
    String id,
    OrderStatus status,
    String currency,
    String totalAmount
) {
    public OrderView {
        if (id == null || id.isBlank()
                || status == null
                || currency == null || currency.isBlank()
                || totalAmount == null) {
            throw new IllegalArgumentException(
                "Missing essential response fields");
        }
    }
}

enum OrderStatus {
    PENDING_PAYMENT,
    PAID,
    SHIPPED,
    DELIVERED,
    CANCELLED,
    @JsonEnumDefaultValue UNKNOWN
}

final class OrderJson {
    private static final JsonMapper MAPPER = JsonMapper.builder()
        .enable(
            DeserializationFeature
                .READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE)
        .build();

    static OrderView parse(String json) throws Exception {
        return MAPPER.readValue(json, OrderView.class);
    }
}
~~~

Hai quyết định độc lập:

1. `@JsonIgnoreProperties(ignoreUnknown = true)` cho phép **property response mới** bị bỏ qua tại lớp `OrderView`.
2. `@JsonEnumDefaultValue UNKNOWN` cùng `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` ánh xạ **enum string mới** sang một giá trị fallback có thể xử lý.

Một trong hai **không thay** cái còn lại. Không bật `READ_UNKNOWN_ENUM_VALUES_AS_NULL` như cách né lỗi dễ dãi: việc âm thầm biến trạng thái không biết thành null có thể tạo NullPointerException hoặc nhánh nghiệp vụ sai. Nếu response có **nested DTO**, chúng cũng cần chính sách unknown-field phù hợp; annotation trên lớp ngoài không tự làm mọi đối tượng lồng nhau tolerant.

**Giới hạn:** snippet minh họa deserialization, chưa validate chi tiết cú pháp decimal, currency hay schema. Ứng dụng thật phải giới hạn size/depth JSON, kiểu của field đã biết, kiểu thời gian và quyền truy cập. Parser chỉ nên bỏ qua property chưa biết **theo hợp đồng được phép mở rộng**, không bỏ qua lỗi cấu trúc của field thiết yếu.

### 5.3. Hành động theo enum chỉ cho phép khi đã biết

~~~java
public final class OrderActions {
    public static boolean showPayButton(
            OrderView order, boolean authorized,
            boolean hasPaymentAffordance) {
        return authorized
            && hasPaymentAffordance
            && order.status() == OrderStatus.PENDING_PAYMENT;
    }

    public static String statusText(OrderStatus status) {
        return switch (status) {
            case PENDING_PAYMENT -> "Chờ thanh toán";
            case PAID -> "Đã thanh toán";
            case SHIPPED -> "Đang giao hàng";
            case DELIVERED -> "Đã giao";
            case CANCELLED -> "Đã hủy";
            case UNKNOWN -> "Trạng thái mới, chưa được hỗ trợ đầy đủ";
        };
    }
}
~~~

Không bao giờ dùng `case UNKNOWN -> executeDefaultAction()`. Đặc biệt, client phải tránh suy diễn “không phải CANCELLED nghĩa là trả tiền được”. Server là nơi cuối cùng quyết định quyền và trạng thái; kể cả client mới gửi action sai vẫn phải bị từ chối với mã HTTP phù hợp, chẳng hạn `409 Conflict` hoặc `403 Forbidden`.

## 6. Spring API: response mở rộng, request phải được kiểm soát

Client linh hoạt khi **đọc output** không có nghĩa backend nên bỏ qua mọi field trong **input**. Giả sử endpoint tạo đơn nhận:

~~~json
{
  "shippingAddressId": "addr_11",
  "note": "Giao sau 18 giờ"
}
~~~

Một client gõ nhầm `shippingAdressId` hoặc gửi thêm `isPaid: true`. Nếu server lặng lẽ bỏ qua cả hai, client có thể tưởng đã lưu đúng; nếu bind thẳng JPA entity thì `isPaid` còn có nguy cơ thành **mass assignment**.

### 6.1. DTO request tách biệt với entity và response

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
    @NotBlank String shippingAddressId,
    @Size(max = 500) String note
) {}

// DTO response: có thể thêm field tùy chọn độc lập.
public record OrderResponse(
    String id,
    String status,
    String currency,
    String totalAmount,
    java.time.Instant estimatedDeliveryAt
) {}
~~~

Phía server **không** nhận `status`, `totalAmount`, `tenantId` hoặc `isPaid` từ request DTO. Giá/tenant/trạng thái phải do service tính từ dữ liệu và danh tính đáng tin cậy. DTO response có thể chứa thêm property, nhưng cần bảo đảm policy không vô tình tiết lộ thông tin nội bộ.

### 6.2. Kiểm tra unknown input field

Với Spring Boot dùng Jackson, có thể cấu hình:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Khi đó JSON request có key ngoài `CreateOrderRequest` sẽ không được chấp nhận nếu không có annotation hoặc cấu hình riêng ghi đè. Cần `@Valid` để kiểm tra ràng buộc của **field đã biết**; Jackson không tự thay thế Bean Validation.

~~~java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/orders")
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping(consumes = "application/json")
    ResponseEntity<OrderResponse> create(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody CreateOrderRequest request) {
        // Service phải xác thực/kiểm quyền, kiểm tra địa chỉ thuộc
        // principal/tenant và tính giá ở server.
        OrderResponse created =
            service.createAuthorized(jwt.getSubject(), request);
        return ResponseEntity
            .created(java.net.URI.create(
                "/v1/orders/" + created.id()))
            .body(created);
    }
}

interface OrderService {
    OrderResponse createAuthorized(
        String authenticatedSubject, CreateOrderRequest request);
}
~~~

**Chú ý:** đây là skeleton, cần Spring Security/JWT validation, repository và xử lý lỗi thực tế. Tenant không được tin từ request body. Thay đổi field ở response không cho phép client tự ghi field đó trở lại. Nếu một ứng dụng Spring vừa đóng vai server vừa là HTTP consumer, **đừng áp dụng cùng một `ObjectMapper` strict cho mọi hướng dữ liệu một cách vô thức**: nên có mapper/decoder cho client response với chính sách tolerant riêng, còn endpoint nhận request tuân thủ allowlist.

Có thể trả `400 Bad Request` với `application/problem+json` cho key không nhận diện hoặc sai cú pháp; `422 Unprocessable Content` có thể dùng cho ràng buộc nghiệp vụ theo contract. Không phản chiếu nội dung nhạy cảm của request trong Problem Details.

## 7. HTTP contract: dữ liệu mới không nên thay đổi ý nghĩa kết quả

Ví dụ server mở rộng response nhưng giữ ngữ nghĩa GET:

~~~http
GET /v1/orders/ord_916 HTTP/1.1
Host: api.example.test
Accept: application/json
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "ord_916-representation-v12"
Cache-Control: private, no-store

{
  "id": "ord_916",
  "status": "AWAITING_VERIFICATION",
  "currency": "VND",
  "totalAmount": "250000",
  "estimatedDeliveryAt": null
}
~~~

`200 OK` nghĩa là GET thành công, **không** phải trạng thái nghiệp vụ được client cũ hỗ trợ. Đừng biến unknown enum thành `500` phía server hoặc đổi thành `404` để che lỗi phiên bản khi quyền đọc vẫn hợp lệ. Nếu client không hiểu workflow, nó có thể hiển thị an toàn hoặc thông báo cập nhật ứng dụng.

Khi người dùng dựa trên dữ liệu cũ để chỉnh đơn, việc thêm field và thay representation có thể ảnh hưởng ETag. Với `If-Match`, điều kiện thất bại trả `412 Precondition Failed` thay vì âm thầm bỏ kiểm tra version. Tuy nhiên **một bộ điều kiện mới không được tự ý đổi ngữ nghĩa một command cũ**; nếu yêu cầu xử lý đã khác về nghiệp vụ thì phải tiến hóa hợp đồng đúng cách.

### 7.1. Khi không thể phục vụ an toàn cho client cũ

Không được “dịch” `AWAITING_VERIFICATION` thành `PAID` để lừa parser cũ. Có thể khóa action nguy hiểm, yêu cầu cập nhật hoặc thương lượng capability/media type khác. **Không cần version mới cho mọi field tùy chọn**; chỉ tách hợp đồng khi không thể duy trì semantics an toàn.

## 8. OpenAPI 3.1: mô tả response mở rộng và request chặt chẽ

Một nguồn gây lỗi phổ biến là dùng **cùng một schema đóng** cho cả JSON server trả về và JSON client gửi lên. Để tiến hóa an toàn, cần tách hợp đồng theo **hướng dữ liệu** và **mức độ mở của enum**.

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.1.0
paths:
  /v1/orders/{id}:
    get:
      summary: Đọc thông tin đơn hàng
      security: [{bearerAuth: []}]
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '200':
          description: Response có thể bổ sung property trong tương lai
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '401': {description: Chưa xác thực}
        '404': {description: Không tìm thấy hoặc không công bố đơn}
  /v1/orders:
    post:
      summary: Tạo đơn; chỉ chấp nhận trường đầu vào đã hỗ trợ
      security: [{bearerAuth: []}]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Đơn được tạo
          headers:
            Location:
              schema: {type: string, format: uri-reference}
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '400': {description: JSON hoặc input field không hợp lệ}
        '403': {description: Không có quyền tạo}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
  schemas:
    OrderResponse:
      type: object
      required: [id, status, currency, totalAmount]
      # Nêu rõ ý định mở rộng của response:
      additionalProperties: true
      properties:
        id: {type: string}
        status:
          type: string
          description: |
            Các giá trị hiện biết được liệt kê bên dưới.
            Server có thể bổ sung giá trị; client phải xử lý
            unknown bằng cách không thực thi action nguy hiểm.
          examples: [PENDING_PAYMENT, PAID, SHIPPED, DELIVERED, CANCELLED]
          x-extensible-enum:
            - PENDING_PAYMENT
            - PAID
            - SHIPPED
            - DELIVERED
            - CANCELLED
        currency: {type: string, example: VND}
        totalAmount: {type: string, example: '250000'}
        estimatedDeliveryAt:
          type: [string, 'null']
          format: date-time
          description: Thời gian dự kiến, có thể vắng hoặc null
    CreateOrderRequest:
      type: object
      required: [shippingAddressId]
      additionalProperties: false
      properties:
        shippingAddressId: {type: string}
        note: {type: string, maxLength: 500}
~~~

**Các điểm cần hiểu rõ:**

- `additionalProperties: true` trên response công bố chủ đích **cho phép field bổ sung**. Bỏ hẳn từ khóa này cũng không mặc nhiên cấm extras trong JSON Schema; dùng `false` mới đóng schema.
- `additionalProperties: false` trên request nhằm chặn field ngoài contract; **server phải thực thi validation/deserialization tương ứng**. OpenAPI không tự ngăn mass assignment.
- `x-extensible-enum` là **vendor extension**, không phải thuộc tính chuẩn yêu cầu mọi OpenAPI generator phải hiểu. Công cụ không hỗ trợ có thể bỏ qua extension. Dùng `type: string` + documentation rõ để tránh phát sinh client enum đóng ngoài ý muốn.
- Nếu thay `status` bằng `enum: [...]` trong chuẩn JSON Schema, schema sẽ coi **chỉ các giá trị liệt kê là hợp lệ**. Không thể đồng thời hứa enum mở mà bắt mọi client validate theo danh sách đóng.
- `examples` giúp mô tả giá trị hiện biết, không giới hạn giá trị hợp lệ. Provider vẫn cần kiểm tra domain để không phát ra chuỗi rác.

Trường hợp use case thật sự chỉ cho tập giá trị cố định — ví dụ `deliveryMethod` trong **request** được giới hạn `HOME` hoặc `PICKUP` — hãy dùng `enum` đóng và từ chối input không nằm trong tập đó. **Mở enum response** không phải quyết định mở mọi enum của API.

## 9. Triển khai an toàn qua nhiều phiên bản client

### Kế hoạch thực dụng

1. **Kiểm kê consumer:** mobile, web, SDK/đối tác và phản ứng thực tế khi có unknown fields/enums.
2. **Công bố contract:** optional/absent/null, enum đóng hay mở và action phải fail-closed.
3. **Chuẩn bị client:** parser tolerant, fallback an toàn, mock response tương lai, telemetry theo version.
4. **Triển khai field mới:** đánh giá PII, cache/ETag, generated SDK và chạy consumer tests.
5. **Bật enum mới theo canary/feature flag:** đo lỗi deserialize và tỷ lệ UNKNOWN; không phát cho client chưa thể xử lý an toàn.
6. **Nếu breaking:** dùng capability/version hợp lý, thời hạn hỗ trợ client cũ và kế hoạch rollback.

Mobile có thể không cập nhật nhiều tháng; **không được ngụy trang enum mới thành trạng thái cũ sai nghĩa** để vượt qua parser.

## 10. Bảo mật: linh hoạt khi đọc không được nới quyền

Ba rủi ro thực tế:

- **Mass assignment:** client GET rồi POST/PUT lại toàn bộ response. Field mới như `approvalLevel` có thể bị ghi trở lại nếu backend bind thẳng entity. Giải pháp: request DTO allowlist, business validation và policy ở server.
- **Unknown trạng thái quyết định quyền:** code kiểm `status != CANCELLED` rồi cho thanh toán/xóa. Khi thêm `AWAITING_VERIFICATION`, logic sai. Giải pháp: chỉ allow hành động ở **trạng thái đã xác định**, luôn xác thực và phân quyền ở backend.
- **Rò dữ liệu qua field mới:** dù client cũ bỏ qua `internalFraudScore`, JSON vẫn đã truyền đến người dùng và có thể xuất hiện trong proxy/log/cache. Giải pháp: response projection theo principal/tenant, phân loại dữ liệu, kiểm thử field-level authorization.

**Không** coi tolerant reader là “bỏ qua validation hoàn toàn”: nếu `id` bị thiếu, `totalAmount` đổi kiểu, `status` không phải chuỗi hay HTTP body vượt ngưỡng, client phải báo lỗi cấu trúc phù hợp. Server không dựa vào UI để bảo vệ các thao tác thay đổi trạng thái.

## 11. Kiểm thử tương thích ở hai phía hợp đồng

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Client cũ đọc JSON có `estimatedDeliveryAt` | Parse thành công, field cũ không đổi |
| `status=AWAITING_VERIFICATION` | Parse `UNKNOWN` hoặc báo không hỗ trợ có kiểm soát, không crash |
| `status=UNKNOWN` | Không hiển thị nút thanh toán/hủy nguy hiểm |
| `status` vắng hoặc null | Báo response không hợp lệ; không coi như trạng thái mới hợp lệ |
| Request có `shippingAdressId` viết sai | `400`; không tạo đơn im lặng |
| Request có `isPaid`/`tenantId` tự gán | Từ chối hoặc bảo đảm không có mass assignment |
| Consumer đọc response server cũ chưa có field mới | Tính năng hiển thị fallback, không NPE |
| Cùng URI nhưng representation đổi | ETag/conditional GET xử lý đúng; không trả body cũ sai |
| Deploy hỗn hợp S1/S2 và C1/C2 | Hành trình quan trọng chạy đúng theo ma trận tương thích |

### 11.1. JUnit kiểm tra client tolerant

~~~java
import com.fasterxml.jackson.databind.JsonMappingException;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderJsonTest {
    @Test
    void ignoresExtraResponseFieldButRetainsKnownData()
            throws Exception {
        String json = """
            {"id":"ord_916","status":"PAID","currency":"VND",
             "totalAmount":"250000",
             "estimatedDeliveryAt":"2026-11-21T10:00:00Z"}
            """;
        OrderView order = OrderJson.parse(json);
        assertEquals("ord_916", order.id());
        assertEquals(OrderStatus.PAID, order.status());
    }

    @Test
    void unknownStatusDisablesDangerousAction() throws Exception {
        String json = """
            {"id":"ord_916","status":"AWAITING_VERIFICATION",
             "currency":"VND","totalAmount":"250000"}
            """;
        OrderView order = OrderJson.parse(json);
        assertEquals(OrderStatus.UNKNOWN, order.status());
        assertFalse(OrderActions.showPayButton(order, true, true));
    }

    @Test
    void missingEssentialStatusMustNotLookLikeUnknown()
            throws Exception {
        String json = """
            {"id":"ord_916","currency":"VND","totalAmount":"250000"}
            """;
        assertThrows(JsonMappingException.class,
            () -> OrderJson.parse(json));
    }
}
~~~

Đây là unit test minh họa dựa trên các lớp ở mục 5; cần đúng phiên bản Jackson/JUnit và build configuration của dự án. Với server, dùng MockMvc gửi `POST` có field lạ và xác nhận `400`, đồng thời kiểm tra database **không tạo đơn**. Consumer-driven contract tests nên chạy trên phiên bản SDK/ứng dụng còn được hỗ trợ; chỉ test OpenAPI schema phía producer không chứng minh client thực tế dùng được.

### 11.2. Quan sát khi triển khai

Theo dõi `response_deserialization_errors`, tỷ lệ client báo unknown status, tỷ lệ bỏ hành động vì unsupported state, kết quả tạo đơn thất bại do unknown input và phân bố client version. Ghi metric theo **nhóm status/version**, không log nguyên payload chứa PII hoặc đưa ID đơn/user vào metric có cardinality cao.

## 12. Bài thực hành: thêm trạng thái rà soát vào API đơn hàng

**Đề bài:** API đang trả `status=PAID` và bốn field cố định. Nhóm backend muốn thêm `riskReviewAt` tùy chọn và trạng thái mới `AWAITING_VERIFICATION`. Đã có web client mới, mobile client cũ dùng Java/Jackson strict, một đối tác dùng OpenAPI generator sinh enum đóng. Một số trạng thái cho phép thanh toán/hủy, còn trạng thái rà soát **không được thực hiện hai hành động đó**.

Hãy thực hiện:

1. Phân loại từng thay đổi theo chiều tương thích: field response mới, enum response mới, field request mới bắt buộc (giả định).
2. Viết JSON cũ/mới, phân biệt `riskReviewAt` vắng, null và có timestamp.
3. Sửa DTO/parser của mobile để bỏ qua field mới nhưng giữ ràng buộc field cũ, xử lý unknown status fail-closed.
4. Viết OpenAPI mô tả response mở rộng; giải thích `enum` chuẩn khác `x-extensible-enum`.
5. Tạo request DTO Spring không nhận `riskReviewAt` và `isPaid` từ client; test unknown input.
6. Lập kế hoạch triển khai C1/C2 và S1/S2, giải pháp nếu đối tác không thể cập nhật enum đóng.
7. Thiết kế ít nhất tám test (parser, schema, action, authorization, rollback và ETag).

**Gợi ý đáp án:** thêm `riskReviewAt` thường có thể tương thích nếu chỉ là output tùy chọn và không lộ thông tin nhạy cảm. `AWAITING_VERIFICATION` có thể phá client enum đóng; không thể tuyên bố hoàn toàn tương thích nếu chưa kiểm chứng. Client fallback `UNKNOWN` nên hiển thị thông tin an toàn và chặn action; server vẫn kiểm tra trạng thái thực. Nếu đối tác không hiểu giá trị mới và cần quyết định nghiệp vụ, hãy phân tách capability/contract hoặc kế hoạch nâng cấp, **không ngụy trang** trạng thái thành `PAID`.

## 13. Ghi nhớ

Thêm một property JSON thường dễ hơn thay đổi hoặc mở rộng **enum điều khiển hành vi**, nhưng cả hai đều có thể gây breaking change đối với client giải mã nghiêm ngặt. Thiết kế bền vững cần **response reader linh hoạt trong phạm vi đã công bố**, **request allowlist chặt chẽ**, fallback enum an toàn, hợp đồng OpenAPI đúng kỳ vọng và kiểm thử trên các client thực tế.

Khả năng tương thích không chỉ là JSON parse thành công: một client phải tiếp tục **hiểu đúng ý nghĩa và không thực hiện hành động nguy hiểm** khi dữ liệu mới xuất hiện. Nếu điều đó không thể bảo đảm, hãy thay đổi contract/version hoặc cơ chế thương lượng năng lực thay vì âm thầm phát dữ liệu mà client cũ không thể xử lý.
