# Callback, webhook và các thay đổi trong cấu trúc đặc tả

## 1. Vì sao API cần mô tả callback và webhook?

REST API thông thường mô tả client gửi request tới server và nhận response. Tuy nhiên, nhiều tích hợp cần server chủ động thông báo cho client khi một sự kiện xảy ra, ví dụ đơn hàng đã giao, thanh toán hoàn tất hoặc trạng thái xử lý thay đổi.

Có hai cách phổ biến để mô tả những lời gọi do server khởi tạo:

- **Callback**: một lời gọi HTTP được gắn với một operation cụ thể. URL callback thường được client cung cấp trong request hoặc được suy ra từ dữ liệu của request/response.
- **Webhook**: một loại request do API provider gửi tới endpoint của API consumer khi sự kiện xảy ra. Trong OpenAPI 3.1, webhook được mô tả ở cấp cao nhất của document, độc lập với operation khởi tạo ban đầu.

Springdoc OpenAPI chủ yếu suy luận API từ các handler mà ứng dụng cung cấp. Các endpoint callback hoặc webhook do hệ thống gửi ra ngoài có thể không tương ứng với controller inbound nào trong ứng dụng. Vì vậy, cần bổ sung metadata bằng Swagger annotations hoặc OpenAPI model để document phản ánh đúng giao tiếp bất đồng bộ.

Bài này giải thích cấu trúc Callback Object, Webhooks Object, runtime expressions, sự khác biệt giữa OpenAPI 3.0 và 3.1, cách mô tả bằng Springdoc và những điểm cần kiểm tra khi công cụ chưa hỗ trợ đầy đủ.

## 2. Phân biệt callback, webhook và endpoint thông thường

Cả callback và webhook đều có thể dẫn tới một HTTP request được gửi từ một hệ thống sang hệ thống khác, nhưng chúng có vị trí và ngữ cảnh khác nhau trong hợp đồng API.

| Khái niệm | Được mô tả ở đâu | Khi nào được gọi |
|---|---|---|
| Operation thông thường | paths | Client gọi operation trên API provider |
| Callback | Trong callbacks của một operation | Khi một điều kiện liên quan đến operation xảy ra |
| Webhook | Trong webhooks ở cấp document của OpenAPI 3.1 | Khi provider phát sinh sự kiện, không cần gắn với một operation cụ thể |

Ví dụ:

- Client gọi POST /subscriptions và gửi URL nhận sự kiện. Khi có thay đổi, provider gửi POST tới URL đó. Đây là trường hợp phù hợp để mô tả callback gắn với operation tạo subscription.
- Một nền tảng thanh toán gửi sự kiện payment.completed tới endpoint mà merchant đã đăng ký. Sự kiện có thể phát sinh độc lập với một request đang được thực hiện. Đây là trường hợp phù hợp để mô tả webhook ở cấp document.
- Nếu ứng dụng của bạn cung cấp POST /webhook-events để nhận sự kiện từ nhà cung cấp bên ngoài, endpoint đó vẫn là một API operation inbound thông thường trong paths của API bạn. Tài liệu OpenAPI của nhà cung cấp mới mô tả webhook mà họ gửi tới endpoint đó.

Điểm quan trọng là xác định ai khởi tạo request và request đó gắn với ngữ cảnh operation nào.

## 3. Callback trong OpenAPI là gì?

Callback Object mô tả một hoặc nhiều request mà API provider có thể gửi tới một URL do client cung cấp hoặc được tính từ ngữ cảnh của operation.

Callback được khai báo trong thuộc tính callbacks của Operation Object. Mỗi callback có:

- Tên callback để tham chiếu trong document.
- Một hoặc nhiều runtime expression dùng để xác định URL đích.
- Path Item mô tả HTTP method, request body, parameter và response của lời gọi callback.

Ví dụ, client đăng ký nhận thông báo bằng cách gửi:

~~~http
POST /api/subscriptions
Content-Type: application/json

{
  "eventType": "order.status.changed",
  "callbackUrl": "https://merchant.example.com/hooks/orders"
}
~~~

Khi trạng thái đơn hàng thay đổi, API provider có thể gửi:

~~~http
POST https://merchant.example.com/hooks/orders
Content-Type: application/json

{
  "eventId": "evt-901",
  "orderId": "ORD-1001",
  "status": "SHIPPED"
}
~~~

Callback mô tả request thứ hai như một phần của operation POST /api/subscriptions. URL đích được lấy từ callbackUrl trong request body.

Callback không tạo thêm một endpoint inbound trong ứng dụng provider. Nó mô tả lời gọi mà provider sẽ gửi tới client.

## 4. Cấu trúc Callback Object

Trong OpenAPI, callback là một map từ runtime expression tới Path Item Object. Ví dụ rút gọn:

~~~yaml
paths:
  /api/subscriptions:
    post:
      summary: Đăng ký nhận sự kiện
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SubscriptionRequest'
      callbacks:
        orderStatusChanged:
          '{$request.body#/callbackUrl}':
            post:
              summary: Thông báo thay đổi trạng thái đơn hàng
              requestBody:
                required: true
                content:
                  application/json:
                    schema:
                      $ref: '#/components/schemas/OrderStatusEvent'
              responses:
                '202':
                  description: Client đã tiếp nhận sự kiện
      responses:
        '201':
          description: Đăng ký thành công
~~~

Trong cấu trúc trên:

- callbacks thuộc operation POST /api/subscriptions.
- orderStatusChanged là tên callback.
- {$request.body#/callbackUrl} là runtime expression xác định URL đích.
- post mô tả HTTP request mà provider gửi tới client.
- requestBody mô tả payload sự kiện.
- responses mô tả response mà endpoint callback của client trả lại.

Callback có thể chứa nhiều expression và Path Item, tùy thiết kế. Mỗi callback operation nên mô tả rõ method, media type, schema, response và các header cần thiết.

## 5. Runtime expressions dùng để xác định URL callback

Runtime expression là biểu thức tham chiếu dữ liệu của request hoặc response tại thời điểm operation chạy. Callback dùng biểu thức này để xác định URL đích.

Một số biểu thức thường gặp:

| Expression | Giá trị được tham chiếu |
|---|---|
| {$request.body#/callbackUrl} | Thuộc tính callbackUrl trong JSON request body |
| {$request.query.queryUrl} | Query parameter queryUrl |
| {$request.header.X-Callback-Url} | Request header X-Callback-Url |
| {$response.header.Location} | Header Location trong response |
| {$request.body#/notification/target} | Thuộc tính lồng nhau trong request body |

Ví dụ nếu request có:

~~~json
{
  "notification": {
    "target": "https://client.example.com/events"
  }
}
~~~

thì expression {$request.body#/notification/target} tham chiếu URL trong thuộc tính target.

Expression không phải template string tùy ý của Spring hoặc Java. Đây là cú pháp được OpenAPI định nghĩa để liên kết callback với dữ liệu của message hiện tại. Tên property và JSON Pointer phải khớp payload thực tế.

Nếu expression trỏ tới một giá trị không có trong request/response, tài liệu vẫn có thể hợp lệ về cú pháp nhưng client không thể xác định callback URL khi thực thi. Hãy bảo đảm request schema yêu cầu field đó và mô tả rõ định dạng URL.

## 6. Khai báo callback bằng Swagger annotations

Swagger Core cung cấp các annotation để mô tả callback trong operation. Ví dụ:

~~~java
@RestController
@RequestMapping("/api/subscriptions")
public class SubscriptionController {

    @Operation(
        summary = "Đăng ký nhận sự kiện đơn hàng",
        callbacks = {
            @Callback(
                name = "orderStatusChanged",
                callbackUrlExpression = "{$request.body#/callbackUrl}",
                operations = {
                    @CallbackOperation(
                        method = "post",
                        operation = @Operation(
                            summary = "Thông báo trạng thái đơn hàng",
                            requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
                                required = true,
                                content = @Content(
                                    schema = @Schema(
                                        implementation = OrderStatusEvent.class
                                    )
                                )
                            ),
                            responses = {
                                @ApiResponse(
                                    responseCode = "202",
                                    description = "Sự kiện đã được tiếp nhận"
                                )
                            }
                        )
                    )
                }
            )
        }
    )
    @PostMapping
    public SubscriptionResponse subscribe(
            @Valid @RequestBody SubscriptionRequest request) {
        return subscriptionService.subscribe(request);
    }
}
~~~

Các annotation callback nằm trong package io.swagger.v3.oas.annotations.callbacks:

- @Callback
- @CallbackOperation

Operation metadata dùng @Operation, @ApiResponse, @Content và @Schema.

Trong ví dụ, callbackUrlExpression phải trỏ tới field callbackUrl của SubscriptionRequest. DTO nên có field này và validation phù hợp:

~~~java
public record SubscriptionRequest(
    @NotBlank
    @URL
    String callbackUrl,

    @NotBlank
    String eventType
) {
}
~~~

Tên annotation và thuộc tính cụ thể phụ thuộc phiên bản Swagger Core đi kèm Springdoc. Hãy xác nhận dependency đang dùng hỗ trợ các callback annotations trước khi áp dụng.

Callback URL thường đến từ dữ liệu client gửi lên, vì vậy provider phải xem đây là input không tin cậy. Nếu server gửi HTTP request tới URL tùy ý, endpoint đăng ký callback có thể trở thành điểm khai thác Server-Side Request Forgery (SSRF). Nên chỉ cho phép HTTPS và host nằm trong allowlist phù hợp với mô hình tích hợp; từ chối loopback, private, link-local và địa chỉ metadata nội bộ sau khi resolve DNS; kiểm tra lại đích sau redirect hoặc tắt redirect; đồng thời giới hạn outbound network ở tầng hạ tầng. Kiểm tra URL bằng regex đơn thuần không đủ để chống DNS rebinding hoặc redirect tới địa chỉ nội bộ.

## 7. Tách DTO của callback khỏi request đăng ký

Request tạo subscription và payload callback là hai message khác nhau. Không nên dùng chung một DTO chỉ vì cả hai đều liên quan đến đơn hàng.

Ví dụ request đăng ký:

~~~java
public record SubscriptionRequest(
    @NotBlank
    @URL
    String callbackUrl,

    @NotBlank
    String eventType
) {
}
~~~

Ví dụ event provider gửi về:

~~~java
public record OrderStatusEvent(
    String eventId,
    String orderId,
    String status,
    Instant occurredAt
) {
}
~~~

Request đăng ký chứa thông tin endpoint nhận callback và loại sự kiện. Payload callback chứa dữ liệu về sự kiện đã xảy ra.

Trong OpenAPI, hai schema nên được tham chiếu riêng:

- SubscriptionRequest ở request body của operation tạo subscription.
- OrderStatusEvent ở request body của callback operation.

Cách tách này giúp client hiểu rõ dữ liệu nào họ gửi cho provider và dữ liệu nào provider sẽ gửi ngược lại.

## 8. Callback không đồng nghĩa với bảo đảm giao nhận

OpenAPI mô tả hình dạng và ngữ cảnh của callback; nó không định nghĩa toàn bộ cơ chế vận hành giao nhận.

Một hệ thống callback thực tế cần quyết định:

- Retry khi endpoint client timeout hoặc trả lỗi.
- Khoảng thời gian retry và backoff.
- Điều kiện đánh dấu delivery thất bại.
- Thời hạn lưu event và khả năng replay.
- Cách phát hiện callback trùng lặp.
- Thứ tự sự kiện và khả năng đến sai thứ tự.
- Cách client xác nhận đã tiếp nhận message.

Các quy tắc này nên được ghi trong operation description, callback description hoặc tài liệu vận hành liên kết. Không nên để client suy đoán rằng một callback chỉ được gửi đúng một lần hoặc luôn theo thứ tự.

Một event nên có định danh ổn định như eventId, thời điểm phát sinh và loại sự kiện để client có thể xử lý idempotency.

## 9. Webhook trong OpenAPI 3.1

OpenAPI 3.1 bổ sung thuộc tính cấp cao nhất webhooks. Thuộc tính này mô tả các request mà API provider có thể gửi tới API consumer, độc lập với một operation cụ thể trong paths.

Ví dụ:

~~~yaml
openapi: 3.1.0
info:
  title: Payment API
  version: '2.0.0'

webhooks:
  paymentCompleted:
    post:
      summary: Thông báo thanh toán hoàn tất
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PaymentCompletedEvent'
      responses:
        '202':
          description: Consumer đã tiếp nhận webhook

paths:
  /api/payments:
    post:
      summary: Tạo yêu cầu thanh toán
      responses:
        '201':
          description: Đã tạo yêu cầu thanh toán
~~~

Ở đây:

- webhooks là sibling của paths, components và các thành phần cấp cao nhất khác.
- paymentCompleted là tên webhook.
- post mô tả request mà provider gửi tới consumer.
- PaymentCompletedEvent mô tả payload.
- 202 là response mà endpoint nhận webhook trả về.

Webhook không cần nằm dưới paths của API provider vì request được gửi tới endpoint do consumer vận hành. OpenAPI document mô tả hình dạng request mà consumer cần sẵn sàng nhận.

## 10. Khác biệt giữa Callback Object và Webhooks Object

| Tiêu chí | Callback | Webhook |
|---|---|---|
| Phiên bản OpenAPI | Có từ OpenAPI 3.0 | Được bổ sung trong OpenAPI 3.1 |
| Vị trí | callbacks bên trong Operation Object | webhooks ở cấp document |
| Ngữ cảnh | Gắn với một operation cụ thể | Độc lập với operation khởi tạo |
| URL đích | Thường được xác định bằng runtime expression | Thường do hai bên đăng ký/cấu hình ngoài document |
| Trường hợp điển hình | Gửi kết quả xử lý về URL trong request tạo tác vụ | Gửi sự kiện thanh toán, đơn hàng, tài khoản |
| Quan hệ với operation | Có quan hệ trực tiếp | Không cần operation cha |

Không nên chuyển mọi callback thành webhook chỉ vì cả hai đều là request bất đồng bộ. Nếu URL đích được gửi trong request của một operation và callback chỉ có ý nghĩa trong giao dịch đó, Callback Object thường mô tả chính xác hơn.

Nếu sự kiện được phát độc lập theo đăng ký dài hạn và không gắn với một operation cụ thể, Webhooks Object thường phù hợp hơn.

## 11. Chọn OpenAPI 3.1 trong Springdoc

Webhook cấp document yêu cầu OpenAPI 3.1 trở lên. Nếu ứng dụng xuất OpenAPI 3.0, trường webhooks không thuộc cấu trúc chuẩn của phiên bản đó.

Springdoc có thuộc tính cấu hình phiên bản OpenAPI document ở các phiên bản hỗ trợ:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Giá trị cấu hình và khả năng hỗ trợ phụ thuộc phiên bản Springdoc. Hãy kiểm tra tài liệu của đúng dòng Springdoc đang dùng và xác minh trường openapi trong /v3/api-docs thực sự là 3.1.x.

Không chỉ thêm webhooks vào model rồi giả định document sẽ hợp lệ nếu trường openapi vẫn là 3.0.x. Công cụ validator và client generator có thể từ chối hoặc bỏ qua trường không thuộc phiên bản đã khai báo.

Nếu project cần giữ OpenAPI 3.0 vì tooling cũ, có thể mô tả webhook receiver như operation thông thường trong một document dành cho API consumer, hoặc phát hành một document 3.1 riêng khi hệ sinh thái công cụ đã sẵn sàng.

## 12. Thêm webhook bằng OpenApiCustomizer

Springdoc không thể tự suy ra mọi webhook outbound chỉ từ controller, vì endpoint nhận webhook thường nằm ở hệ thống của đối tác. Có thể bổ sung Webhooks Object bằng OpenApiCustomizer và Swagger Core model.

Ví dụ:

~~~java
@Bean
OpenApiCustomizer paymentWebhookCustomizer() {
    return openApi -> {
        Operation operation = new Operation()
            .summary("Thông báo thanh toán hoàn tất")
            .description(
                "Payment provider gửi event tới endpoint đã đăng ký của consumer."
            )
            .requestBody(new RequestBody()
                .required(true)
                .content(new Content()
                    .addMediaType(
                        "application/json",
                        new MediaType()
                            .schema(new Schema<>()
                                .$ref("#/components/schemas/PaymentCompletedEvent"))
                    )
                )
            )
            .responses(new ApiResponses()
                .addApiResponse(
                    "202",
                    new ApiResponse()
                        .description("Consumer đã tiếp nhận webhook")
                )
            );

        PathItem pathItem = new PathItem().post(operation);

        Map<String, PathItem> webhooks = new LinkedHashMap<>();
        if (openApi.getWebhooks() != null) {
            webhooks.putAll(openApi.getWebhooks());
        }
        webhooks.put("paymentCompleted", pathItem);
        openApi.setWebhooks(webhooks);
    };
}
~~~

Các model được dùng thuộc io.swagger.v3.oas.models:

- Operation
- RequestBody
- Content
- MediaType
- Schema
- ApiResponses
- ApiResponse
- PathItem

Đoạn code minh họa cách bổ sung một webhook. Schema PaymentCompletedEvent cần tồn tại trong components.schemas của document; nếu Springdoc chưa tạo schema đó từ DTO/controller nào, hãy đăng ký schema một cách tường minh.

Nếu document đã có webhook từ customizer khác, không nên dùng Map.of để thay toàn bộ map hiện hữu. Hãy lấy map hiện tại, thêm entry và đặt lại map để tránh ghi đè các webhook khác.

## 13. Đảm bảo webhook schema có trong components

Có thể đăng ký schema từ DTO được dùng trong API hoặc thêm schema bằng model. Ví dụ DTO:

~~~java
public record PaymentCompletedEvent(
    String eventId,
    String paymentId,
    BigDecimal amount,
    String currency,
    Instant occurredAt
) {
}
~~~

Nếu DTO chưa được tham chiếu bởi operation nào, Springdoc có thể không tự thêm schema vào components.schemas. Khi đó, customizer cần bổ sung schema hoặc tạo một operation/schema reference theo cơ chế phù hợp của phiên bản.

Một cách tạo schema tường minh bằng Swagger Core model có thể dùng ModelConverters:

~~~java
if (openApi.getComponents() == null) {
    openApi.setComponents(new Components());
}

ResolvedSchema resolved = ModelConverters.getInstance()
    .resolveAsResolvedSchema(
        new AnnotatedType(PaymentCompletedEvent.class)
    );

openApi.getComponents().addSchemas(
    "PaymentCompletedEvent",
    resolved.schema
);

if (resolved.referencedSchemas != null) {
    resolved.referencedSchemas.forEach(
        (name, schema) -> openApi.getComponents()
            .addSchemas(name, schema)
    );
}
~~~

Cần kiểm tra schema converter và package tương ứng với phiên bản Swagger Core. Nếu schema đã được Springdoc tạo, không thêm trùng tên hoặc ghi đè schema hiện có một cách vô ý.

Khi document có nhiều webhook dùng chung event schema, nên tái sử dụng một component schema thay vì nhúng một bản sao khác nhau vào từng operation.

## 14. Mô tả header xác thực của webhook

Webhook thường cần cơ chế xác thực request để consumer xác nhận request thực sự đến từ provider và payload chưa bị thay đổi. Một số cách thường gặp:

- HMAC signature trên raw request body.
- Bearer token được quản lý và luân chuyển.
- Mutual TLS giữa provider và consumer.
- Chữ ký bất đối xứng hoặc cơ chế ký message theo chuẩn riêng.

Ví dụ header chữ ký:

~~~http
X-Webhook-Signature: sha256=SIGNATURE_VALUE
X-Webhook-Timestamp: 1732100000
X-Webhook-Event-Id: evt-901
~~~

Có thể mô tả các header này trong operation webhook bằng Parameter Object:

~~~yaml
parameters:
  - name: X-Webhook-Signature
    in: header
    required: true
    description: Chữ ký HMAC của payload theo quy ước tích hợp
    schema:
      type: string
  - name: X-Webhook-Timestamp
    in: header
    required: true
    description: Thời điểm ký request
    schema:
      type: integer
      format: int64
~~~

Nếu header đại diện cho một credential theo security scheme, có thể mô tả bằng components.securitySchemes và security phù hợp. Với HMAC signature thay đổi theo từng payload, cần giải thích thuật toán canonicalization, encoding, timestamp tolerance và cách tính chữ ký trong description hoặc tài liệu bảo mật liên kết.

Không đưa secret HMAC thật vào OpenAPI document. Secret được chia sẻ qua kênh provisioning an toàn và cần có quy trình rotate/revoke.

## 15. Mô tả response và retry contract

Webhook sender thường cần biết consumer phải phản hồi thế nào để xác nhận đã tiếp nhận event.

Một quy ước phổ biến:

| Response | Ý nghĩa có thể quy định |
|---|---|
| 2xx | Consumer đã nhận request |
| 400 | Payload không hợp lệ; có thể không retry |
| 401/403 | Credential không hợp lệ hoặc không được phép |
| 429 | Consumer đang giới hạn tốc độ; retry theo chính sách |
| 5xx | Consumer gặp lỗi tạm thời; provider có thể retry |

Đây là quy ước tích hợp, không phải OpenAPI tự áp đặt. Provider cần công bố rõ status nào được retry, thời gian chờ, số lần thử và cách xử lý dead-letter.

Trong OpenAPI, mô tả response cụ thể:

~~~yaml
responses:
  '202':
    description: Event đã được tiếp nhận để xử lý bất đồng bộ
  '400':
    description: Payload không hợp lệ
  '401':
    description: Chữ ký webhook không hợp lệ
  '429':
    description: Consumer đang giới hạn tốc độ
  '500':
    description: Lỗi tạm thời khi tiếp nhận event
~~~

Không nên ghi “2xx nghĩa là xử lý nghiệp vụ hoàn tất” nếu consumer chỉ enqueue event để xử lý sau. Response description cần phân biệt accepted và processed.

## 16. Idempotency, replay và thứ tự sự kiện

Webhook có thể được gửi lại do timeout, mất response hoặc retry. Consumer nên xử lý theo hướng idempotent.

Một event nên có định danh duy nhất:

~~~json
{
  "eventId": "evt-901",
  "eventType": "payment.completed",
  "occurredAt": "2026-11-20T10:30:00Z",
  "data": {
    "paymentId": "pay-1001",
    "status": "COMPLETED"
  }
}
~~~

Tài liệu nên nêu:

- eventId có duy nhất trong phạm vi nào.
- Consumer cần lưu ID đã xử lý trong bao lâu.
- Provider có thể gửi trùng event hay không.
- Có header delivery attempt hoặc timestamp không.
- Có thể nhận event sai thứ tự hay không.
- Có API truy vấn trạng thái để reconcile khi bỏ lỡ event không.

OpenAPI mô tả schema và header, nhưng không thể tự bảo đảm exactly-once delivery. Hệ thống phân phối thường hướng tới at-least-once và yêu cầu consumer chống xử lý trùng.

Nếu provider hỗ trợ replay, cần mô tả cách yêu cầu gửi lại và các giới hạn liên quan.

## 17. Callback và webhook trong OpenAPI 3.0

OpenAPI 3.0 hỗ trợ Callback Object nhưng chưa có thuộc tính cấp cao nhất webhooks.

Nếu phải giữ OpenAPI 3.0, callback gắn với operation vẫn có thể được mô tả:

~~~yaml
openapi: 3.0.3
paths:
  /api/subscriptions:
    post:
      callbacks:
        orderStatusChanged:
          '{$request.body#/callbackUrl}':
            post:
              requestBody:
                required: true
                content:
                  application/json:
                    schema:
                      $ref: '#/components/schemas/OrderStatusEvent'
              responses:
                '202':
                  description: Accepted
      responses:
        '201':
          description: Subscription created
~~~

Nếu webhook không gắn với operation, có thể tạo một document riêng cho phía consumer và mô tả endpoint nhận webhook trong paths, nếu mục tiêu là tài liệu cho API do consumer vận hành. Cách này không thay thế ngữ nghĩa webhook outbound ở cấp provider, nhưng vẫn có thể giúp consumer xây dựng receiver.

Khi nâng document lên OpenAPI 3.1, hãy kiểm tra thêm các khác biệt JSON Schema và khả năng tương thích của validator, code generator, API gateway và developer portal.

## 18. Các thay đổi cấu trúc đáng chú ý khi chuyển sang OpenAPI 3.1

OpenAPI 3.1 không chỉ thêm webhooks. Phiên bản này đồng bộ Schema Object gần hơn với JSON Schema 2020-12 và có một số thay đổi cấu trúc/diễn giải quan trọng.

| Thành phần | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Webhook độc lập | Không có top-level webhooks | Có webhooks ở cấp document |
| Schema Object | Dựa trên subset và mở rộng của JSON Schema | Gần với JSON Schema 2020-12 |
| Giá trị null | Có nullable: true | Dùng JSON Schema type union có null |
| JSON Schema dialect | Không có jsonSchemaDialect ở root theo cấu trúc 3.1 | Có thể khai báo dialect mặc định |
| $ref siblings | Có giới hạn theo quy tắc Reference Object 3.0 | Quy tắc Reference Object được mở rộng; cần kiểm tra đúng ngữ cảnh |

Ví dụ biểu diễn giá trị nullable:

OpenAPI 3.0:

~~~yaml
type: string
nullable: true
~~~

OpenAPI 3.1:

~~~yaml
type:
  - string
  - 'null'
~~~

Không nên đổi nullable: true thành union null một cách máy móc nếu schema còn composition, reference hoặc constraint khác. Hãy kiểm tra schema theo JSON Schema dialect và validator mục tiêu.

OpenAPI 3.1 cũng hỗ trợ jsonSchemaDialect ở cấp root để chỉ định dialect mặc định cho Schema Object. Công cụ xử lý document cần hiểu dialect đó để diễn giải schema nhất quán.

## 19. $ref và thay đổi quy tắc Reference Object

Trong OpenAPI 3.0, $ref trong Reference Object có quy tắc hạn chế; các sibling fields không được xử lý như một schema object tùy ý. Trong OpenAPI 3.1, Reference Object cho phép một số thành phần bổ sung như summary và description theo cấu trúc chuẩn, trong khi Schema Object sử dụng quy tắc JSON Schema cho $ref.

Ví dụ tham chiếu schema:

~~~yaml
schema:
  $ref: '#/components/schemas/PaymentCompletedEvent'
~~~

Khi cần mô tả thêm metadata cho một tham chiếu, hãy dùng đúng cấu trúc của phiên bản document và phân biệt Reference Object với Schema Object. Không giả định mọi sibling của $ref đều có cùng ý nghĩa ở mọi vị trí.

Nếu API có nhiều document được tiêu thụ bởi code generator cũ, hãy kiểm tra cách công cụ xử lý $ref siblings trước khi chuyển sang OpenAPI 3.1. Một document hợp lệ theo chuẩn mới vẫn có thể không tương thích với parser cũ.

## 20. Kiểm tra Springdoc có xuất đúng callback và webhook

Sau khi cấu hình annotation hoặc customizer, tải OpenAPI JSON:

~~~http
GET /v3/api-docs
~~~

Kiểm tra callback:

- Operation cha có trường callbacks.
- Callback name đúng.
- Runtime expression đúng với request/response field.
- Callback operation có method và request body đúng.
- Response mô tả status mà receiver trả về.
- Schema được tham chiếu có trong components.schemas.

Kiểm tra webhook:

- Trường openapi là 3.1.x.
- webhooks nằm ở cấp root, cùng cấp với paths.
- Tên webhook và Path Item đúng.
- Request body, media type, schema và response đầy đủ.
- Header xác thực và event metadata được mô tả.
- Không có secret hoặc URL nội bộ bị công bố.

Nếu dùng document group, kiểm tra webhook có xuất hiện trong document của group phù hợp hay không. Global và group-specific customizer có phạm vi khác nhau; không giả định một customizer áp dụng cho mọi document.

## 21. Kiểm thử callback và webhook bằng contract test

Có thể kiểm tra cấu trúc OpenAPI bằng MockMvc hoặc WebTestClient tùy web stack.

Ví dụ kiểm tra callback:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/subscriptions'].post.callbacks.orderStatusChanged"
    ).exists());
~~~

Ví dụ kiểm tra webhook cấp root:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.openapi").value(startsWith("3.1")))
    .andExpect(jsonPath("$.webhooks.paymentCompleted.post").exists());
~~~

Matcher startsWith cần được import từ thư viện test phù hợp; nếu dùng JSONPath matcher khác, có thể parse response rồi xác minh chuỗi openapi bắt đầu bằng 3.1.

Ngoài kiểm tra document, cần test HTTP sender/receiver:

- Sender tạo request đúng URL và payload.
- Chữ ký được tính đúng trên payload đã gửi.
- Receiver từ chối signature sai hoặc timestamp quá cũ.
- Receiver xử lý event trùng mà không lặp side effect.
- Sender retry theo chính sách khi nhận timeout hoặc status retryable.
- Log không ghi secret hoặc dữ liệu nhạy cảm.

Contract test xác minh mô tả; integration test xác minh cơ chế giao nhận thực tế.

## 22. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| webhooks không xuất hiện trong OpenAPI JSON | Document vẫn là 3.0.x hoặc customizer chưa chạy |
| Validator báo webhooks không hợp lệ | Trường webhook đặt sai cấp hoặc version document không phải 3.1 |
| Callback không xuất hiện | Annotation chưa được Springdoc/Swagger Core resolve |
| Callback URL không xác định được | Runtime expression trỏ sai field hoặc request thiếu field |
| Callback schema bị thiếu | DTO chưa được đăng ký vào components |
| Webhook bị đưa vào paths sai ngữ nghĩa | Nhầm endpoint receiver của consumer với webhook outbound của provider |
| Swagger UI không hiển thị webhook | Phiên bản UI hoặc renderer chưa hỗ trợ phần này đầy đủ |
| Code generator bỏ qua webhook | Generator chưa hỗ trợ OpenAPI 3.1 webhooks |
| Webhook signature không rõ cách xác minh | Thiếu mô tả thuật toán, timestamp, encoding hoặc raw body |
| Consumer xử lý event hai lần | Không có idempotency theo event ID |
| Event đến sai thứ tự | Thiếu sequence/version hoặc quy tắc reconcile |
| Chuyển 3.0 sang 3.1 làm schema lỗi | JSON Schema dialect hoặc nullable/ref semantics thay đổi |
| Group document thiếu callback/webhook | Customizer áp dụng sai phạm vi group |

Khi công cụ không hỗ trợ webhook, không nên xóa phần contract chỉ để Swagger UI hiển thị đẹp. Có thể phát hành OpenAPI JSON/YAML chuẩn 3.1 qua developer portal hoặc tài liệu khác hỗ trợ đầy đủ hơn, đồng thời ghi rõ giới hạn của UI hiện tại.

## 23. Lộ trình chuyển đổi và lựa chọn mô hình

Khi thiết kế tích hợp bất đồng bộ:

1. Dùng Callback nếu lời gọi ngược gắn với một operation và URL được xác định từ request/response.
2. Dùng Webhooks Object nếu provider phát sự kiện độc lập và document cần mô tả request outbound ở cấp cao nhất.
3. Dùng operation trong paths khi đang mô tả endpoint inbound do chính API của bạn cung cấp.
4. Dùng OpenAPI 3.1 khi cần top-level webhooks.
5. Kiểm tra Swagger UI, validator, code generator và API gateway có hỗ trợ version/feature đó không.
6. Mô tả payload, headers, response, retry, idempotency và security.
7. Không đưa secret hoặc credential thật vào document.
8. Dùng customizer để bổ sung webhook outbound mà Springdoc không thể suy ra từ controller.
9. Kiểm tra callback expression và webhook root structure trong OpenAPI JSON.
10. Quản lý thay đổi schema và event contract như một phần của versioning API.

Callback và webhook giúp OpenAPI mô tả giao tiếp do server khởi tạo thay vì chỉ mô tả request/response đồng bộ. Callback gắn với operation và runtime context; webhook là thành phần cấp document trong OpenAPI 3.1. Khi chọn đúng cấu trúc, bổ sung metadata outbound bằng Springdoc và kiểm tra khả năng tương thích của tooling, client có thể triển khai receiver với hiểu biết rõ ràng về payload, bảo mật và hành vi giao nhận.

