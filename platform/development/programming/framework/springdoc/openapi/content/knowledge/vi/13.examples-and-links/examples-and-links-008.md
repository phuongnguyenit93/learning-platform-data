# Callback và webhook theo khả năng của phiên bản đặc tả

Nhiều API cần thông báo cho một hệ thống khác khi một sự kiện xảy ra. Ví dụ, khi đơn hàng được tạo, dịch vụ thương mại điện tử có thể gửi một sự kiện đến URL do đối tác đăng ký. Một quy trình khác có thể cho phép client đăng ký URL nhận cập nhật trạng thái rồi server gọi URL đó sau khi xử lý xong. Đây là giao tiếp bất đồng bộ: bên gửi không chờ một request API đang mở để trả kết quả cuối cùng.

**springdoc-openapi** có thể mô tả các luồng này trong tài liệu OpenAPI. Cần chọn đúng cấu trúc theo ngữ nghĩa và phiên bản đặc tả:

- **Callback Object** mô tả request ngoài luồng được khởi tạo bởi API provider và gắn với một operation cụ thể. Callback có từ OpenAPI 3.0.
- **Top-level webhooks** mô tả request do API provider chủ động gửi đến người tiêu thụ, độc lập với một operation đang chạy. Trường webhooks được bổ sung trong OpenAPI 3.1.

Hai cấu trúc này mô tả hợp đồng. Chúng không tự tạo endpoint, gửi callback, quản lý hàng đợi, retry hoặc xác thực chữ ký. Phần runtime vẫn phải được triển khai trong ứng dụng.

## 1. Phân biệt callback và webhook

Trong giao tiếp hằng ngày, callback và webhook đôi khi được dùng thay thế cho nhau. Khi viết OpenAPI, nên phân biệt theo mối liên hệ giữa sự kiện và operation:

| Tiêu chí | Callback | Webhook |
| --- | --- | --- |
| Quan hệ với operation | Gắn với một operation cụ thể | Độc lập với operation đang chạy |
| Thời điểm gửi | Sau khi client gọi operation cha và sự kiện liên quan xảy ra | Khi một sự kiện được phát sinh, có thể bất kỳ lúc nào |
| Địa chỉ nhận | Thường lấy từ dữ liệu request/response qua runtime expression | Địa chỉ do consumer cấu hình trong quy trình đăng ký hoặc cấu hình ngoài tài liệu |
| Vị trí trong OpenAPI | Thuộc tính callbacks của Operation Object | Trường webhooks cấp cao nhất của OpenAPI Object |
| Phiên bản | OpenAPI 3.0 trở lên | OpenAPI 3.1 trở lên |
| Ví dụ | Client gửi callbackUrl khi tạo đăng ký; server gọi URL đó khi trạng thái thay đổi | Dịch vụ gửi sự kiện orderCreated đến các subscriber đã đăng ký |

Ví dụ callback thường có quy trình:

1. Client gọi POST /api/subscriptions và gửi callbackUrl.
2. Server lưu đăng ký và trả về subscriptionId.
3. Khi đơn hàng thay đổi, server gửi POST đến callbackUrl đã đăng ký.
4. Hệ thống nhận callback trả về mã 2xx để xác nhận đã nhận dữ liệu.

Webhook thường có quy trình:

1. Consumer đăng ký nhận một hoặc nhiều loại sự kiện.
2. Provider lưu cấu hình endpoint nhận sự kiện.
3. Khi sự kiện phát sinh, provider gửi HTTP request đến endpoint đó.
4. Consumer xác minh request, xử lý sự kiện và trả phản hồi xác nhận.

Trong OpenAPI, webhook ở trường webhooks là request do API provider gửi ra phía consumer. Nếu ứng dụng Spring Boot của bạn là bên nhận webhook từ một dịch vụ bên ngoài, endpoint nhận đó vẫn là một operation HTTP thông thường trong paths. Hướng gửi request quyết định cách mô hình hóa; tên gọi trong code không quyết định cấu trúc đặc tả.

## 2. Callback trong OpenAPI 3.0 và 3.1

OpenAPI 3.0 đã có Callback Object. Một callback được khai báo bên trong operation mà nó liên quan. Callback gồm một hoặc nhiều biểu thức runtime; mỗi biểu thức ánh xạ đến Path Item Object mô tả HTTP request mà API provider sẽ gửi.

OpenAPI 3.1 tiếp tục hỗ trợ callback và bổ sung trường webhooks ở cấp tài liệu. Vì vậy, khi dự án đang dùng OpenAPI 3.0, vẫn có thể mô tả callback gắn với operation. Nếu cần mô tả webhook độc lập theo cấu trúc chuẩn, cần xuất OpenAPI 3.1 trở lên.

| Phiên bản đặc tả | Callback Object | Top-level webhooks |
| --- | --- | --- |
| OpenAPI 3.0.x | Có | Không có trong chuẩn |
| OpenAPI 3.1.x | Có | Có |

Không nên đổi nhãn phiên bản trong JSON bằng cách sửa thủ công trường openapi. Cấu trúc và schema của tài liệu phải phù hợp với phiên bản đã khai báo. Nếu dùng tính năng OAS 3.1, hãy cấu hình springdoc và phiên bản swagger-core có hỗ trợ OAS 3.1.

## 3. Runtime expression xác định URL callback

Callback Object dùng runtime expression làm khóa. Expression được đánh giá từ HTTP request hoặc response của operation cha tại thời điểm thực thi.

Một số nguồn dữ liệu thường dùng:

| Expression | Giá trị được đọc |
| --- | --- |
| $request.body#/callbackUrl | Thuộc tính callbackUrl trong request body |
| $request.query.callbackUrl | Query parameter callbackUrl |
| $request.header.X-Callback-Url | Request header X-Callback-Url |
| $request.path.subscriptionId | Path parameter subscriptionId |
| $response.header.Location | Response header Location |
| $url | URL của request hiện tại |
| $method | HTTP method của request hiện tại |
| $statusCode | Mã trạng thái response |

Trong YAML, khóa callback thường được viết trong dấu nháy đơn và đặt expression trong ngoặc nhọn:

~~~yaml
callbacks:
  orderStatusChanged:
    '{$request.body#/callbackUrl}':
      post:
        summary: Gửi cập nhật trạng thái đơn hàng
        responses:
          '200':
            description: Consumer đã nhận callback
~~~

Expression phải khớp với cấu trúc payload thực tế. Nếu request body có dạng:

~~~json
{
  "notification": {
    "callbackUrl": "https://consumer.example.com/events"
  }
}
~~~

thì expression cần tham chiếu đến /notification/callbackUrl. JSON Pointer phân biệt tên thuộc tính và hỗ trợ escape ký tự theo quy tắc của JSON Pointer.

Runtime expression chỉ cho công cụ đọc OpenAPI biết cách xác định đích callback từ message. Nó không kiểm tra URL, không xác minh quyền sở hữu domain và không tự gửi HTTP request.

## 4. Mô tả callback bằng YAML

Ví dụ API cho phép client đăng ký URL nhận sự kiện đơn hàng:

~~~yaml
openapi: 3.0.3
paths:
  /api/subscriptions:
    post:
      operationId: createOrderSubscription
      summary: Đăng ký nhận sự kiện đơn hàng
      description: Lưu URL mà server sẽ gọi khi đơn hàng thay đổi.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateSubscriptionRequest'
      responses:
        '201':
          description: Đăng ký đã được tạo
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SubscriptionView'
      callbacks:
        orderStatusChanged:
          '{$request.body#/callbackUrl}':
            post:
              operationId: receiveOrderStatusChanged
              summary: Nhận thông báo thay đổi trạng thái
              parameters:
                - name: X-Webhook-Signature
                  in: header
                  required: true
                  schema:
                    type: string
              requestBody:
                required: true
                content:
                  application/json:
                    schema:
                      $ref: '#/components/schemas/OrderStatusEvent'
              responses:
                '200':
                  description: Callback đã được tiếp nhận
components:
  schemas:
    CreateSubscriptionRequest:
      type: object
      required:
        - callbackUrl
      properties:
        callbackUrl:
          type: string
          format: uri
          description: URL HTTPS do consumer quản lý để nhận sự kiện
          example: https://consumer.example.com/order-events
    SubscriptionView:
      type: object
      properties:
        subscriptionId:
          type: string
          example: sub-1001
        status:
          type: string
          example: ACTIVE
    OrderStatusEvent:
      type: object
      required:
        - eventId
        - orderId
        - status
      properties:
        eventId:
          type: string
          example: evt-9001
        orderId:
          type: string
          example: ord-1001
        status:
          type: string
          example: SHIPPED
~~~

Trong tài liệu này:

- Operation createOrderSubscription là thao tác cha mà client gọi.
- callbacks.orderStatusChanged mô tả request POST do provider gửi sau đó.
- Khóa {$request.body#/callbackUrl} cho biết URL callback lấy từ request body của operation cha.
- Request body callback là OrderStatusEvent, khác với CreateSubscriptionRequest.
- Header chữ ký được mô tả như một phần của request callback để consumer biết cách xác minh.

Callback operation không phải endpoint controller mà server nhận tại chính ứng dụng provider. Nó mô tả request được gửi đến hệ thống consumer. Nếu muốn mô tả API của consumer trong một tài liệu riêng, consumer có thể công bố endpoint POST /order-events của mình.

## 5. Khai báo callback bằng annotation Swagger

Swagger Core cung cấp annotation **@Callback** để thêm callback ở cấp phương thức. Springdoc đọc annotation OpenAPI từ controller và chuyển thành Callback Object khi phiên bản dependency hỗ trợ.

Ví dụ DTO đăng ký:

~~~java
import jakarta.validation.constraints.NotBlank;

public record CreateSubscriptionRequest(
    @NotBlank
    String callbackUrl
) {}
~~~

DTO sự kiện:

~~~java
public record OrderStatusEvent(
    String eventId,
    String orderId,
    String status
) {}
~~~

Controller khai báo callback:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.callbacks.Callback;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SubscriptionController {

    @Operation(
        operationId = "createOrderSubscription",
        summary = "Đăng ký nhận sự kiện đơn hàng"
    )
    @Callback(
        name = "orderStatusChanged",
        callbackUrlExpression = "{$request.body#/callbackUrl}",
        operation = @Operation(
            method = "post",
            summary = "Gửi sự kiện thay đổi trạng thái đơn hàng",
            parameters = @Parameter(
                name = "X-Webhook-Signature",
                in = ParameterIn.HEADER,
                required = true,
                description = "Chữ ký để consumer xác minh payload",
                schema = @Schema(type = "string")
            ),
            requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
                required = true,
                content = @Content(
                    mediaType = "application/json",
                    schema = @Schema(implementation = OrderStatusEvent.class)
                )
            ),
            responses = @ApiResponse(
                responseCode = "200",
                description = "Consumer đã nhận callback"
            )
        )
    )
    @PostMapping("/api/subscriptions")
    SubscriptionView create(
        @Valid @RequestBody CreateSubscriptionRequest request
    ) {
        return subscriptionService.create(request);
    }
}
~~~

Ở ví dụ này, **@Callback** đặt trên phương thức controller và operation lồng bên trong mô tả HTTP method, request body, header và response của callback. Annotation mô tả hợp đồng; service vẫn phải lưu đăng ký, phát sự kiện và gửi request đến URL tương ứng.

Tên thuộc tính annotation có thể khác giữa các thế hệ swagger-annotations. Ví dụ trên dùng API của Swagger Core 2.x; kiểm tra Javadoc đúng phiên bản đang được springdoc quản lý trước khi sao chép vào dự án. Nếu annotation không tạo ra callback trong tài liệu, có thể dùng OpenApiCustomizer để bổ sung Callback Object vào operation.

## 6. Webhook độc lập trong OpenAPI 3.1

Với webhook không gắn với một operation cụ thể, OpenAPI 3.1 cung cấp trường **webhooks** ở cấp cao nhất. Mỗi khóa là tên logic của loại sự kiện; giá trị là Path Item Object mô tả request mà API provider sẽ gửi đến consumer.

Ví dụ:

~~~yaml
openapi: 3.1.0
info:
  title: Order Event API
  version: 1.0.0
webhooks:
  orderCreated:
    post:
      operationId: receiveOrderCreated
      summary: Nhận sự kiện đơn hàng được tạo
      description: Provider gửi request này khi một đơn hàng mới được tạo.
      parameters:
        - name: X-Webhook-Signature
          in: header
          required: true
          description: Chữ ký HMAC của payload và timestamp
          schema:
            type: string
        - name: X-Webhook-Event-Id
          in: header
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/OrderCreatedEvent'
      responses:
        '200':
          description: Consumer đã nhận sự kiện
        '202':
          description: Consumer đã nhận và đưa sự kiện vào hàng đợi xử lý
components:
  schemas:
    OrderCreatedEvent:
      type: object
      required:
        - eventId
        - eventType
        - occurredAt
        - data
      properties:
        eventId:
          type: string
          example: evt-2026-0001
        eventType:
          type: string
          const: order.created
        occurredAt:
          type: string
          format: date-time
        data:
          type: object
          required:
            - orderId
          properties:
            orderId:
              type: string
              example: ord-1001
            total:
              type: number
              example: 1250000
~~~

Trường webhooks không cần biểu thức URL như callback. Nó mô tả loại request provider sẽ gửi; địa chỉ đích của consumer thường được cấu hình trong quy trình đăng ký hoặc hệ thống quản lý subscription. Tài liệu cần nói rõ consumer đăng ký URL và loại sự kiện bằng cách nào.

Trong OAS 3.1, schema dùng JSON Schema hiện đại, ví dụ **const** để giới hạn eventType vào một giá trị. Nếu tài liệu phải tương thích OAS 3.0, không dùng trường webhooks chuẩn và không giả định const có cùng cách hỗ trợ; hãy dùng enum một phần tử hoặc cơ chế tương thích phù hợp.

## 7. Chọn OpenAPI 3.1 trong springdoc

Muốn springdoc xuất trường top-level webhooks, ứng dụng phải tạo đặc tả OpenAPI 3.1 và dùng phiên bản swagger-core/swagger-models có hỗ trợ trường này. Với phiên bản springdoc hỗ trợ thuộc tính cấu hình tương ứng, có thể đặt trong application.properties:

~~~properties
springdoc.api-docs.version=OPENAPI_3_1
~~~

Hoặc application.yml:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Tên property và giá trị enum cần được đối chiếu với tài liệu của phiên bản springdoc đang dùng. Sau khi khởi động, kiểm tra trường **openapi** trong JSON tại /v3/api-docs. Kết quả phải là phiên bản 3.1.x trước khi thêm trường webhooks.

Nếu dự án đang xuất 3.0.x, cấu trúc webhooks có thể bị bỏ qua, không serialize hoặc bị validator từ chối tùy phiên bản model và cấu hình. Không khắc phục bằng cách tự sửa chuỗi JSON cuối cùng; hãy nâng cấp bộ dependency tương thích và cấu hình spec version ngay trong springdoc.

## 8. Bổ sung webhook bằng OpenApiCustomizer

Springdoc hỗ trợ tùy biến OpenAPI model bằng **OpenApiCustomizer**. Đây là cách hữu ích khi webhook không tương ứng với một phương thức controller trong ứng dụng hoặc annotation chưa đủ để mô tả.

Ví dụ sau thêm một webhook orderCreated vào tài liệu OpenAPI 3.1:

~~~java
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.parameters.RequestBody;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.responses.ApiResponses;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.utils.SpringDocAnnotationsUtils;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WebhookOpenApiConfiguration {

    @Bean
    OpenApiCustomizer orderWebhookCustomizer() {
        return openApi -> {
            if (openApi.getComponents() == null) {
                openApi.setComponents(new Components());
            }

            Schema<?> eventSchema =
                SpringDocAnnotationsUtils.extractSchema(
                    openApi.getComponents(),
                    OrderCreatedEvent.class,
                    null,
                    null,
                    openApi.getSpecVersion()
                );

            PathItem webhook = new PathItem().post(
                new Operation()
                    .operationId("receiveOrderCreated")
                    .summary("Nhận sự kiện đơn hàng được tạo")
                    .requestBody(
                        new RequestBody()
                            .required(true)
                            .content(
                                new Content().addMediaType(
                                    "application/json",
                                    new MediaType().schema(eventSchema)
                                )
                            )
                    )
                    .responses(
                        new ApiResponses().addApiResponse(
                            "200",
                            new ApiResponse()
                                .description("Consumer đã nhận sự kiện")
                        )
                    )
            );

            openApi.addWebhooks("orderCreated", webhook);
        };
    }
}
~~~

**SpringDocAnnotationsUtils.extractSchema** giúp springdoc phân tích kiểu DTO và đăng ký schema được tham chiếu vào components. Sau đó **addWebhooks** gắn Path Item vào trường webhooks của OpenAPI model. Các API model này phụ thuộc phiên bản swagger-core; phương thức addWebhooks thuộc hỗ trợ OpenAPI 3.1 trong swagger-models 2.2.0 trở lên. Kiểm tra dependency thực tế và cấu hình OAS 3.1 của ứng dụng.

Một bean **OpenApiCustomizer** mặc định áp dụng cho tài liệu mặc định. Nếu dự án dùng **GroupedOpenApi**, hãy gắn customizer vào group tương ứng hoặc dùng **GlobalOpenApiCustomizer** khi webhook cần xuất hiện trong tất cả nhóm. Tránh thêm cùng webhook nhiều lần nếu customizer được đăng ký ở cả phạm vi group và global.

Ví dụ code giả định **OrderCreatedEvent** là DTO hợp lệ trong project. Nếu model có các annotation như **@Schema**, springdoc có thể dùng chúng khi trích schema. Với customizer gắn security, header hoặc response phức tạp, bổ sung các thành phần tương ứng vào Path Item và kiểm tra JSON đầu ra.

## 9. Bảo mật callback và webhook

Callback URL và webhook là ranh giới giữa hai hệ thống. Tài liệu nên mô tả cách xác minh request, còn runtime phải thực hiện kiểm tra trước khi xử lý payload.

### Chữ ký payload

Một mô hình phổ biến là provider gửi:

- Header chữ ký, ví dụ X-Webhook-Signature.
- Timestamp để giới hạn tuổi của request.
- Event ID để nhận diện lần phát sự kiện.
- Payload JSON chứa dữ liệu sự kiện.

Consumer dùng secret đã trao đổi trước để tính lại chữ ký HMAC trên nội dung đã quy ước, so sánh theo cách constant-time và kiểm tra timestamp. Không nên đặt secret trực tiếp trong callback URL hoặc query string vì URL thường xuất hiện trong log, lịch sử và hệ thống giám sát.

Nếu dùng HTTP Bearer authentication thay cho chữ ký riêng, khai báo security scheme ở components.securitySchemes và gắn security requirement vào callback/webhook operation. Với chữ ký tùy chỉnh như X-Webhook-Signature, mô tả header bằng Parameter Object vì đó là header nghiệp vụ của giao thức webhook.

### Kiểm tra callback URL

Khi server nhận URL do client cung cấp rồi chủ động gửi request đến URL đó, cần phòng chống SSRF:

- Chỉ cho phép HTTPS nếu không có lý do nghiệp vụ khác.
- Dùng allow-list domain hoặc xác minh quyền sở hữu endpoint.
- Chặn địa chỉ loopback, private network, link-local và metadata endpoint.
- Kiểm tra DNS resolution và xử lý redirect cẩn thận để không vượt qua allow-list.
- Giới hạn port, timeout, kích thước response và số lần redirect.
- Không gửi credential nội bộ hoặc header nhạy cảm đến URL do client kiểm soát.
- Cho phép consumer xác minh URL bằng challenge trước khi kích hoạt subscription nếu phù hợp.

Định dạng URI trong OpenAPI chỉ mô tả giá trị là URI; nó không thực hiện các kiểm tra an toàn trên.

## 10. Retry, idempotency và thứ tự sự kiện

OpenAPI mô tả hình dạng request/response nhưng không chuẩn hóa chính sách gửi lại, thời gian chờ hoặc bảo đảm thứ tự sự kiện. Provider và consumer cần thống nhất các quy tắc vận hành.

| Chủ đề | Điều cần công bố |
| --- | --- |
| Xác nhận nhận sự kiện | Mã 2xx nào được xem là đã nhận |
| Retry | Thời gian chờ, backoff, số lần thử và thời hạn gửi |
| Idempotency | Dùng eventId hoặc deliveryId để nhận diện sự kiện trùng |
| Ordering | Có bảo đảm thứ tự theo aggregate/orderId hay không |
| Timeout | Thời gian chờ response trước khi retry |
| Payload size | Giới hạn kích thước body và cách xử lý payload lớn |
| Phiên bản sự kiện | Quy tắc thay đổi schema và thời gian hỗ trợ phiên bản cũ |
| Ngừng đăng ký | Cách hủy subscription hoặc vô hiệu hóa endpoint |

Một webhook thường được giao theo mô hình at-least-once: consumer có thể nhận cùng một event nhiều lần nếu provider không nhận được acknowledgement. Consumer nên xử lý idempotent, lưu eventId đã xử lý và trả response xác nhận sau khi đã ghi nhận sự kiện một cách bền vững. Nếu trả 2xx trước khi lưu thành công, consumer có thể mất sự kiện khi tiến trình dừng đột ngột.

Không giả định một response 500 sẽ luôn dẫn đến retry hoặc một response 200 đồng nghĩa xử lý nghiệp vụ đã hoàn tất. Hãy ghi rõ semantics của mã trạng thái trong description và tài liệu tích hợp.

## 11. Kiểm thử và xác minh tài liệu sinh ra

Sau khi khởi động ứng dụng, lấy OpenAPI JSON:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Kiểm tra phiên bản đặc tả:

~~~bash
jq -r '.openapi' openapi.json
~~~

Kiểm tra callback gắn với operation:

~~~bash
jq '.paths["/api/subscriptions"].post.callbacks' openapi.json
~~~

Kiểm tra webhook cấp cao nhất:

~~~bash
jq '.webhooks' openapi.json
~~~

Đối chiếu các điểm:

1. Callback nằm dưới đúng operation cha.
2. Runtime expression trỏ đến đúng field trong request hoặc response.
3. Callback operation có đúng HTTP method, request body, header và response.
4. Webhook chỉ xuất hiện ở top-level webhooks khi tài liệu dùng OAS 3.1.
5. Mỗi webhook có operationId duy nhất trong tài liệu.
6. Các $ref đến components.schemas đều tồn tại.
7. Security scheme và header chữ ký khớp với cách provider gửi request thực tế.
8. Swagger UI hoặc công cụ đọc OpenAPI hiển thị được callback/webhook.

Swagger UI có thể hiển thị cấu trúc callback hoặc webhook nhưng không tự đăng ký URL, gửi sự kiện hoặc mô phỏng toàn bộ luồng bất đồng bộ. Hãy kiểm thử runtime bằng một consumer thử nghiệm hoặc HTTP server giả lập để xác minh URL đích, chữ ký, payload, retry và acknowledgement.

## 12. Lỗi thường gặp

**Callback không xuất hiện trong tài liệu.** Kiểm tra **@Callback** có đặt trên đúng phương thức, callbackUrlExpression có giá trị và phiên bản swagger-annotations/springdoc có hỗ trợ annotation đó. Nếu cần, bổ sung callback bằng OpenApiCustomizer và kiểm tra thuộc tính callbacks của operation trong JSON.

**Webhook không xuất hiện ở top-level.** Kiểm tra tài liệu có thực sự xuất OAS 3.1 không, swagger-models có hỗ trợ trường webhooks không và customizer có chạy trên đúng document/group không.

**Đã đổi openapi thành 3.1 nhưng webhook vẫn mất.** Không sửa chuỗi phiên bản sau khi sinh tài liệu. Cấu hình springdoc dùng OAS 3.1 và nâng cấp dependency tương thích để model có trường webhooks.

**Dùng paths để mô tả webhook gửi ra ngoài.** Xác định lại hướng request. Nếu provider chủ động gọi endpoint của consumer, đó là callback hoặc top-level webhook; paths mô tả endpoint thuộc API provider. Nếu ứng dụng đang nhận webhook từ dịch vụ ngoài, endpoint nhận nằm trong paths của ứng dụng.

**Callback URL expression không được thay thế.** Kiểm tra tên field, cấu trúc JSON, JSON Pointer và dấu ngoặc nhọn. Expression trong tài liệu không phải placeholder của Spring MVC.

**Schema webhook bị thiếu.** Khi tạo Path Item thủ công, bảo đảm schema được đăng ký vào components. Có thể dùng SpringDocAnnotationsUtils.extractSchema hoặc thêm schema tường minh.

**Webhook bị gửi lặp và consumer xử lý trùng.** Dùng eventId/deliveryId để idempotency; không dựa vào việc provider chỉ gửi một lần.

**Callback URL trỏ vào tài nguyên nội bộ.** Kiểm tra URL và địa chỉ IP sau DNS resolution, giới hạn redirect và áp dụng allow-list trước khi server gửi request.

## 13. Checklist lựa chọn và triển khai

- [ ] Xác định API provider gửi request gắn với operation hay gửi sự kiện độc lập.
- [ ] Dùng Callback Object cho callback gắn với operation.
- [ ] Dùng top-level webhooks cho webhook độc lập trong OpenAPI 3.1 trở lên.
- [ ] Với OAS 3.0, không khai báo trường webhooks như một trường chuẩn.
- [ ] Cấu hình đúng phiên bản OpenAPI và bộ swagger-core/swagger-models tương thích.
- [ ] Dùng runtime expression khớp cấu trúc message thực tế.
- [ ] Mô tả method, header, request body, response và security của callback/webhook.
- [ ] Đăng ký đầy đủ component schema khi dùng customizer.
- [ ] Kiểm tra callback URL, chữ ký, timestamp và replay protection.
- [ ] Định nghĩa retry, timeout, idempotency, ordering và versioning.
- [ ] Kiểm tra /v3/api-docs, Swagger UI và luồng HTTP runtime.

## 14. Kết luận

Callback và webhook giúp API thông báo sự kiện mà không buộc client phải liên tục polling. OpenAPI 3.0 hỗ trợ callback gắn với operation; OpenAPI 3.1 bổ sung top-level webhooks cho sự kiện độc lập. Springdoc có thể tạo callback từ annotation và cho phép bổ sung webhook bằng OpenApiCustomizer khi model/version hỗ trợ. Hãy xác định đúng hướng request, chọn cấu trúc theo phiên bản đặc tả, mô tả payload và cơ chế bảo mật, rồi kiểm thử cả tài liệu lẫn hành vi gửi nhận thực tế.

## 15. Nguồn tham khảo

- [OpenAPI Specification 3.0.3 — Callback Object](https://spec.openapis.org/oas/v3.0.3.html#callback-object): callback gắn với operation và runtime expression.
- [OpenAPI Specification 3.1.1 — Callback Object và Webhooks Object](https://spec.openapis.org/oas/v3.1.1.html#callback-object): callback và trường webhooks cấp cao nhất.
- [Swagger Core 2.2 — @Callback annotation](https://docs.swagger.io/swagger-core/v2.2.30/apidocs/io/swagger/v3/oas/annotations/callbacks/Callback.html): vị trí và thuộc tính của annotation callback.
- [Springdoc — Configuration Properties](https://springdoc.org/properties.html): cấu hình phiên bản OpenAPI được sinh ra.
- [Springdoc — FAQ: Programmatic OpenAPI customization](https://springdoc.org/faq.html): dùng OpenAPI Bean, OpenApiCustomizer và GlobalOpenApiCustomizer.
