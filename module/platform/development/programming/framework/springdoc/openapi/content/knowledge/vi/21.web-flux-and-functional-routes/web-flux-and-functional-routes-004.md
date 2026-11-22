# Mô tả `text/event-stream` hoặc kiểu nội dung luồng phù hợp

Trong Spring WebFlux, một controller có thể trả `Flux<T>` để phát nhiều phần tử theo thời gian. Tuy nhiên, kiểu trả về `Flux` tự nó chưa quyết định định dạng HTTP trên dây. Media type được khai báo bằng `produces` hoặc được chọn qua content negotiation mới cho biết server gửi một JSON array hoàn chỉnh, một luồng Server-Sent Events (SSE), hay các bản ghi JSON phân tách theo dòng.

Với Springdoc, cần mô tả chính xác media type của response và giải thích cấu trúc của từng phần tử trong luồng. Nếu tài liệu chỉ thể hiện `application/json` hoặc một schema array trong khi runtime thực tế trả `text/event-stream`, client có thể chọn sai parser, SDK có thể sinh kiểu trả về không phù hợp và người tích hợp không biết phải giữ kết nối HTTP mở để nhận dữ liệu.

## 1. Phân biệt JSON response thông thường và HTTP streaming

Một `Flux<T>` có thể được ghi theo nhiều cách tùy media type:

| Media type | Cách biểu diễn | Hành vi thường gặp trong WebFlux |
|---|---|---|
| `application/json` | Một JSON document, thường là array khi có nhiều phần tử | WebFlux gom các phần tử của publisher thành collection rồi serialize thành JSON array |
| `text/event-stream` | Các event SSE liên tiếp, mỗi event kết thúc bằng dòng trống | Ghi từng event và flush để client nhận dữ liệu sớm |
| `application/x-ndjson` | Mỗi dòng là một JSON value độc lập | Ghi và flush từng phần tử theo định dạng JSON Lines/NDJSON |
| `application/jsonl` | JSON Lines | Ghi từng JSON value theo dòng; cần codec hỗ trợ media type này |
| `application/stream+json` hoặc `application/json+stream` | Một số stack/phiên bản dùng để biểu diễn JSON streaming | Chỉ dùng khi codec và client của hệ thống hỗ trợ đúng media type này |
| `application/octet-stream` | Luồng byte, thường dùng cho file hoặc dữ liệu nhị phân | Không phải JSON event stream; mô tả theo hợp đồng download/binary riêng |

Spring Framework hiện hỗ trợ các streaming media type như `application/jsonl` và `application/x-ndjson` cho Jackson JSON encoder; với `text/event-stream`, encoder ghi từng event và flush. Các phiên bản Spring cũ hơn hoặc cấu hình codec tùy chỉnh có thể dùng những media type khác. Vì vậy, hãy đối chiếu phiên bản Spring Framework, codec thực tế và client consumer của dự án.

Điểm cần nhớ: `Flux<T>` kết hợp `application/json` thường tạo một JSON array, còn `Flux<T>` kết hợp media type streaming mới phát từng phần tử theo thời gian. Không nên kết luận API là streaming chỉ vì chữ ký method trả về `Flux`.

## 2. Chọn media type theo cách client cần nhận dữ liệu

### Server-Sent Events: `text/event-stream`

SSE phù hợp khi server đẩy sự kiện một chiều đến client qua một kết nối HTTP kéo dài. Trình duyệt có API `EventSource` hỗ trợ nhận sự kiện, tự kết nối lại và xử lý event ID/retry theo giao thức.

Một SSE message có thể chứa các field:

- `event`: tên loại sự kiện.
- `data`: payload của sự kiện; thường là text hoặc JSON được serialize thành chuỗi.
- `id`: mã sự kiện để client có thể tiếp tục từ vị trí trước khi reconnect.
- `retry`: thời gian chờ reconnect tính bằng mili giây.
- Dòng bắt đầu bằng `:` là comment, thường dùng làm heartbeat.

Mỗi event kết thúc bằng một dòng trống. Ví dụ trên HTTP response:

```text
id: 42
event: order-updated
data: {"orderId":42,"status":"PAID"}

id: 43
event: order-shipped
data: {"orderId":42,"status":"SHIPPED"}

```

Header response phải là `Content-Type: text/event-stream`. Dữ liệu có thể được gửi thành nhiều event trong cùng một response body; client giữ kết nối mở để tiếp tục nhận event mới.

### NDJSON hoặc JSON Lines: `application/x-ndjson`

NDJSON phù hợp khi mỗi phần tử là một JSON object độc lập trên một dòng. Đây là lựa chọn hữu ích cho export lớn, log stream hoặc pipeline đọc tuần tự mà không cần đợi toàn bộ JSON array hoàn tất.

Ví dụ response:

```text
{"id":101,"status":"PAID"}
{"id":102,"status":"SHIPPED"}
{"id":103,"status":"CANCELLED"}
```

Mỗi dòng có thể được parse như một JSON document riêng. Không có `data:`, `event:` hay dòng trống theo framing SSE. Client phải đọc theo dòng và parse từng JSON value.

### JSON array thông thường: `application/json`

Nếu client cần một response JSON chuẩn có thể parse một lần thành danh sách, dùng `application/json`:

```json
[
  {"id":101,"status":"PAID"},
  {"id":102,"status":"SHIPPED"}
]
```

Trong trường hợp này, server có thể nhận các phần tử từ `Flux` theo thời gian nhưng response được biểu diễn như một JSON array hoàn chỉnh. Client thường phải đợi JSON document hoàn tất trước khi parse toàn bộ array.

## 3. Khai báo endpoint SSE trong annotated controller

Spring WebFlux hỗ trợ trả `Flux<ServerSentEvent<T>>`. Wrapper `ServerSentEvent` cho phép đặt `id`, `event`, `retry`, comment và data. Nếu chỉ cần gửi data, có thể trả `Flux<T>` nhưng mapping vẫn phải khai báo `produces = text/event-stream`.

Ví dụ DTO sự kiện:

```java
import java.time.Instant;

public record OrderEvent(
    Long orderId,
    String status,
    Instant occurredAt
) {
}
```

Controller:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/orders")
class OrderEventController {

    private final OrderEventService eventService;

    OrderEventController(OrderEventService eventService) {
        this.eventService = eventService;
    }

    @GetMapping(
        value = "/{orderId}/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    @Operation(
        operationId = "streamOrderEvents",
        summary = "Theo dõi sự kiện của đơn hàng",
        description = "Giữ kết nối HTTP mở và nhận các event SSE khi trạng thái đơn hàng thay đổi.",
        responses = @ApiResponse(
            responseCode = "200",
            description = "Luồng SSE liên tục. Mỗi event có thể chứa id, event và data; data là JSON của OrderEvent.",
            content = @Content(
                mediaType = MediaType.TEXT_EVENT_STREAM_VALUE,
                schema = @Schema(type = "string"),
                examples = @ExampleObject(value = """
                    id: 42
                    event: order-updated
                    data: {"orderId":42,"status":"PAID","occurredAt":"2026-11-20T10:15:30Z"}

                    """)
            )
        )
    )
    Flux<ServerSentEvent<OrderEvent>> stream(@PathVariable Long orderId) {
        return eventService.eventsFor(orderId)
            .map(event -> ServerSentEvent.<OrderEvent>builder(event)
                .id(event.orderId() + "-" + event.occurredAt())
                .event("order-updated")
                .build());
    }
}
```

`produces` xác định response media type. `Flux<ServerSentEvent<OrderEvent>>` cho Spring biết mỗi phần tử cần được ghi thành một SSE event. Annotation `@ApiResponse` mô tả response là `text/event-stream`; ví dụ minh họa framing trên dây.

Trong ví dụ OpenAPI 3.0/3.1, schema `type: string` biểu diễn nội dung văn bản của stream và example cho thấy một event frame. DTO `OrderEvent` là mô hình payload nghiệp vụ mà `data` chứa, nhưng schema string chưa liên kết trực tiếp cấu trúc DTO vào từng event. Nếu client generator cần biết kiểu từng event, dùng OpenAPI 3.2 `itemSchema` khi toolchain hỗ trợ, hoặc công bố component/extension theo quy ước mà các consumer của dự án thống nhất.

Nếu chỉ trả data mà không cần metadata SSE:

```java
@GetMapping(value = "/{orderId}/updates", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<OrderEvent> updates(@PathVariable Long orderId) {
    return eventService.eventsFor(orderId);
}
```

Spring WebFlux có thể ghi mỗi phần tử thành một event data khi media type là `text/event-stream`. Dùng `ServerSentEvent<T>` khi cần kiểm soát event name, ID, retry hoặc comment.

## 4. Mô tả NDJSON trong OpenAPI và Springdoc

Controller trả mỗi `OrderEvent` thành một JSON record trên một dòng:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/exports")
class OrderExportController {

    private final OrderExportService exportService;

    OrderExportController(OrderExportService exportService) {
        this.exportService = exportService;
    }

    @GetMapping(value = "/orders", produces = "application/x-ndjson")
    @Operation(
        operationId = "streamOrdersAsNdjson",
        summary = "Xuất đơn hàng theo định dạng NDJSON",
        description = "Mỗi dòng trong response là một JSON object OrderEvent độc lập.",
        responses = @ApiResponse(
            responseCode = "200",
            description = "Luồng NDJSON; mỗi dòng là một OrderEvent.",
            content = @Content(
                mediaType = "application/x-ndjson",
                schema = @Schema(type = "string"),
                examples = @ExampleObject(value = """
                    {"orderId":101,"status":"PAID","occurredAt":"2026-11-20T10:15:30Z"}
                    {"orderId":102,"status":"SHIPPED","occurredAt":"2026-11-20T10:16:00Z"}
                    """)
            )
        )
    )
    Flux<OrderEvent> streamOrders() {
        return exportService.streamOrders();
    }
}
```

Ở đây schema `string` cùng ví dụ nhiều dòng mô tả body text trên dây trong OpenAPI 3.0/3.1. Mô hình Java `OrderEvent` mô tả cấu trúc của từng JSON record; phần description phải nói rõ mỗi dòng được parse độc lập. Nếu cần schema record được liên kết chuẩn với stream, dùng `itemSchema` trong OpenAPI 3.2 khi toolchain hỗ trợ. Không mô tả response này như một JSON array nếu runtime thực sự phát NDJSON.

Nếu Spring Framework và codec đang dùng hỗ trợ `application/jsonl`, có thể chọn media type đó thay cho `application/x-ndjson`. Hai định dạng đều biểu diễn JSON value theo dòng, nhưng phải bảo đảm client và gateway hỗ trợ đúng media type mà server công bố.

## 5. Dùng `itemSchema` khi tài liệu có thể dùng OpenAPI 3.2

OpenAPI 3.2 bổ sung `itemSchema` cho các sequential media type như `text/event-stream`, `application/jsonl` và `application/x-ndjson`. Trường này mô tả schema của từng phần tử được lặp lại trong luồng, thay vì coi toàn bộ body là một JSON object duy nhất.

Ví dụ NDJSON ở OpenAPI 3.2:

```yaml
openapi: 3.2.0
paths:
  /api/exports/orders:
    get:
      operationId: streamOrdersAsNdjson
      responses:
        '200':
          description: Luồng NDJSON; mỗi dòng là một đơn hàng.
          content:
            application/x-ndjson:
              itemSchema:
                $ref: '#/components/schemas/OrderEvent'
components:
  schemas:
    OrderEvent:
      type: object
      properties:
        orderId:
          type: integer
          format: int64
        status:
          type: string
        occurredAt:
          type: string
          format: date-time
```

Ví dụ SSE ở OpenAPI 3.2 có thể mô tả cả envelope của SSE và JSON nằm trong field `data`:

```yaml
openapi: 3.2.0
paths:
  /api/orders/{orderId}/events:
    get:
      operationId: streamOrderEvents
      responses:
        '200':
          description: Luồng Server-Sent Events.
          content:
            text/event-stream:
              itemSchema:
                $ref: '#/components/schemas/OrderSseEvent'
components:
  schemas:
    OrderSseEvent:
      type: object
      required: [data]
      properties:
        id:
          type: string
        event:
          type: string
        retry:
          type: integer
          minimum: 0
        data:
          type: string
          contentMediaType: application/json
          contentSchema:
            $ref: '#/components/schemas/OrderEvent'
    OrderEvent:
      type: object
      properties:
        orderId:
          type: integer
          format: int64
        status:
          type: string
        occurredAt:
          type: string
          format: date-time
```

`itemSchema` là tính năng của OpenAPI 3.2. Không thêm trường này vào document khai báo `openapi: 3.0.x` hoặc `3.1.x`. Khả năng phát sinh OpenAPI 3.2 phụ thuộc phiên bản Springdoc, Swagger Core và các công cụ downstream. Nếu stack hiện tại chưa hỗ trợ, dùng mô tả tương thích 3.0/3.1 như các ví dụ trước và ghi rõ cấu trúc từng event/record trong description cùng example.

Không giả định Swagger UI hoặc client generator đang dùng đã hiển thị và sinh code từ `itemSchema` đầy đủ. Hãy kiểm tra cả validator, tài liệu hiển thị và SDK đầu ra trước khi chuẩn hóa OpenAPI 3.2 trong pipeline.

## 6. Functional routes cũng cần mô tả media type

Springdoc hỗ trợ Spring WebFlux functional endpoints. Với `RouterFunction`, route không nằm trên method `@GetMapping`; vì vậy cần cung cấp metadata bằng `@RouterOperation`/`@RouterOperations` hoặc functional DSL của Springdoc.

Ví dụ handler trả SSE:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
class OrderEventHandler {

    private final OrderEventService eventService;

    OrderEventHandler(OrderEventService eventService) {
        this.eventService = eventService;
    }

    @Operation(
        operationId = "streamOrderEventsFunctional",
        summary = "Theo dõi sự kiện đơn hàng",
        responses = @ApiResponse(
            responseCode = "200",
            description = "Luồng SSE; data chứa JSON OrderEvent.",
            content = @Content(
                mediaType = MediaType.TEXT_EVENT_STREAM_VALUE,
                schema = @Schema(type = "string"),
                examples = @ExampleObject(value = """
                    event: order-updated
                    data: {"orderId":42,"status":"PAID"}

                    """)
            )
        )
    )
    Mono<ServerResponse> stream(ServerRequest request) {
        Long orderId = Long.valueOf(request.pathVariable("orderId"));
        Flux<ServerSentEvent<OrderEvent>> events = eventService.eventsFor(orderId)
            .map(event -> ServerSentEvent.<OrderEvent>builder(event)
                .event("order-updated")
                .id(event.orderId() + "")
                .build());

        return ServerResponse.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(BodyInserters.fromServerSentEvents(events));
    }
}
```

Khai báo metadata trên Router bean:

```java
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.http.MediaType;

@Bean
@RouterOperation(
    path = "/api/orders/{orderId}/events",
    method = RequestMethod.GET,
    produces = MediaType.TEXT_EVENT_STREAM_VALUE,
    beanClass = OrderEventHandler.class,
    beanMethod = "stream"
)
RouterFunction<ServerResponse> orderEventRoutes(OrderEventHandler handler) {
    return RouterFunctions.route(
        RequestPredicates.GET("/api/orders/{orderId}/events")
            .and(RequestPredicates.accept(MediaType.TEXT_EVENT_STREAM)),
        handler::stream
    );
}
```

`@RouterOperation` dùng `path`, `method` và `produces` để nhận diện route; `beanClass`/`beanMethod` cho phép Springdoc đọc metadata Swagger annotations trên handler method. Với một Router bean có nhiều route, dùng `@RouterOperations` và khai báo từng `@RouterOperation` với path phù hợp. Có thể dùng functional DSL Springdoc nếu muốn mô tả operation ngay tại route builder.

`produces` trong metadata phải khớp `accept(...)` của route và `contentType(...)` của response. Nếu một route chỉ nhận `text/event-stream` mà tài liệu lại công bố `application/json`, Springdoc mô tả sai cách client cần gọi.

## 7. Một operation hỗ trợ nhiều response media type

Nếu cùng một resource có thể trả representation JSON hoặc SSE tùy `Accept`, có thể khai báo nhiều media type trong mapping:

```java
@GetMapping(
    value = "/api/orders/events",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.TEXT_EVENT_STREAM_VALUE
    }
)
Flux<OrderEvent> events() {
    return eventService.allEvents();
}
```

Khi client gửi `Accept: application/json`, WebFlux có thể serialize nhiều phần tử thành JSON array. Khi client gửi `Accept: text/event-stream`, WebFlux stream các phần tử dưới dạng SSE. Tài liệu OpenAPI cần mô tả cả hai media type và giải thích sự khác biệt về cách đọc.

Ví dụ OpenAPI 3.0/3.1:

```yaml
responses:
  '200':
    description: >
      Với application/json, response là một JSON array hoàn chỉnh.
      Với text/event-stream, server giữ kết nối mở và gửi từng event SSE.
    content:
      application/json:
        schema:
          type: array
          items:
            $ref: '#/components/schemas/OrderEvent'
      text/event-stream:
        schema:
          type: string
        examples:
          oneEvent:
            value: |
              event: order-updated
              data: {"orderId":42,"status":"PAID"}
```

Nếu controller trả `Flux<ServerSentEvent<OrderEvent>>`, không nên khai báo `application/json` cho cùng method trừ khi runtime thực sự hỗ trợ và serialize đúng media type đó. Hãy kiểm tra content negotiation bằng request có header `Accept` cụ thể.

## 8. Springdoc có thể suy luận schema từ `Flux` như thế nào?

Springdoc phân tích kiểu trả về, mapping và annotation để xây dựng response content. Tuy nhiên, biểu diễn stream có những khác biệt mà một kiểu Java đơn lẻ không mô tả hết:

- `Flux<OrderEvent>` cho biết nhiều giá trị phát ra, nhưng không nói client nhận JSON array, NDJSON hay SSE.
- `produces` xác định media type và là tín hiệu quan trọng để xác định cách ghi response.
- `ServerSentEvent<OrderEvent>` có metadata của event, còn `OrderEvent` là payload data.
- `application/x-ndjson` truyền từng JSON record theo dòng, không phải một JSON array.
- OpenAPI 3.0/3.1 không có `itemSchema` chuẩn cho sequential media type; OpenAPI 3.2 bổ sung trường này.

Vì vậy, với endpoint streaming, hãy khai báo response content tường minh bằng `@ApiResponse`/`@Content` khi schema suy luận chưa phản ánh đúng hợp đồng. Sau đó kiểm tra document sinh ra thay vì giả định Springdoc sẽ luôn suy ra chính xác framing của stream từ `Flux`.

Không dùng `@ArraySchema` cho SSE hoặc NDJSON chỉ vì method trả `Flux`. `@ArraySchema` mô tả một JSON array; nó không mô tả event framing hoặc JSON Lines trên dây.

## 9. Kiểm tra OpenAPI document được sinh ra

Sau khi chạy ứng dụng, mở `/v3/api-docs` hoặc document group tương ứng. Kiểm tra `content` của response:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/orders/{orderId}/events"].get.responses["200"].content'
```

Với SSE trong OpenAPI 3.0/3.1, cần thấy media type `text/event-stream` và mô tả/schema tương ứng. Với NDJSON, cần thấy `application/x-ndjson` hoặc media type JSON Lines đã chọn.

Kiểm tra operation không bị mô tả nhầm thành JSON array:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/exports/orders"].get.responses["200"].content | keys'
```

Nếu dùng OpenAPI 3.2, xác minh `itemSchema` tồn tại dưới media type phù hợp và document khai báo phiên bản `openapi: 3.2.x`. Không đưa `itemSchema` vào document 3.0/3.1.

Đối với functional routes, kiểm tra path, HTTP method, `produces` và operationId đã xuất hiện trong document. Nếu thiếu route, xem lại `@RouterOperation`/`@RouterOperations` hoặc functional DSL và tiêu chí nhận diện route.

## 10. Kiểm thử stream bằng HTTP client

### Dùng cURL với SSE

```bash
curl -N \
  -H 'Accept: text/event-stream' \
  http://localhost:8080/api/orders/42/events
```

`-N` tắt buffering phía cURL để các event hiển thị ngay khi nhận được. Nếu không có `-N`, cURL hoặc terminal có thể làm người dùng tưởng server chưa gửi event dù dữ liệu đang được buffer ở client.

### Dùng cURL với NDJSON

```bash
curl -N \
  -H 'Accept: application/x-ndjson' \
  http://localhost:8080/api/exports/orders
```

Client đọc từng dòng và parse JSON riêng. Không dùng JSON array parser cho NDJSON.

### Kiểm thử bằng WebTestClient

Với SSE, có thể xác nhận response media type và đọc một vài event rồi hủy subscription:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest
@AutoConfigureWebTestClient
class OrderEventStreamTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void streamsOrderEventsAsSse() {
        FluxExchangeResult<ServerSentEvent<OrderEvent>> result = webTestClient
            .get()
            .uri("/api/orders/42/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
            .returnResult(new ParameterizedTypeReference<ServerSentEvent<OrderEvent>>() {});

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                "order-updated".equals(event.event()) && event.data() != null
            )
            .thenCancel()
            .verify();
    }
}
```

Test stream nên dùng dữ liệu sự kiện có thể điều khiển trong test, timeout phù hợp và hủy subscription sau khi xác minh. Nếu publisher là luồng vô hạn, không dùng `expectComplete()` như với một response hữu hạn.

## 11. Trình duyệt và giới hạn của SSE client

Trình duyệt có thể dùng `EventSource` để nhận SSE:

```javascript
const source = new EventSource("https://api.example.com/api/orders/42/events");

source.addEventListener("order-updated", (event) => {
  const order = JSON.parse(event.data);
  console.log(order.status);
});

source.onerror = () => {
  console.log("SSE connection interrupted; browser may reconnect automatically.");
};
```

Native `EventSource` không cho phép tùy ý đặt `Authorization` header. Nếu API yêu cầu Bearer token trong header, ứng dụng trình duyệt có thể dùng `fetch` streaming với `ReadableStream`, một thư viện SSE hỗ trợ custom headers, hoặc cơ chế cookie phù hợp. Không đưa token dài hạn vào query string chỉ để vượt giới hạn này.

Nếu Swagger UI có nút Try it out, nó có thể gửi request HTTP nhưng không nhất thiết hiển thị stream vô hạn như một SSE client chuyên dụng. Dùng cURL, WebTestClient hoặc ứng dụng client thật để kiểm tra event liên tục và reconnect behavior.

## 12. Heartbeat, reconnect và proxy buffering

Một kết nối SSE có thể tồn tại lâu. Proxy, load balancer hoặc firewall có thể đóng kết nối nhàn rỗi nếu không có dữ liệu trong một khoảng thời gian. Có thể phát comment heartbeat:

```text
: keep-alive

```

Comment không tạo event cho ứng dụng client nhưng giúp luồng có hoạt động định kỳ. Khi dùng `ServerSentEvent`, có thể phát comment event theo API builder của phiên bản Spring Framework đang dùng.

Các yếu tố cần kiểm tra:

- Reverse proxy có buffer response hay không; buffering có thể khiến event chỉ xuất hiện theo đợt.
- Idle timeout của gateway/load balancer có lớn hơn khoảng heartbeat không.
- Client có xử lý `Last-Event-ID` và server có khả năng tiếp tục từ event ID tương ứng không.
- Publisher có tôn trọng cancellation khi client ngắt kết nối không.
- Một kết nối stream có được giới hạn thời gian hoặc số lượng theo chính sách hệ thống không.
- Server có phát dữ liệu định kỳ để phát hiện kết nối đã bị đóng không.

SSE có cơ chế reconnect ở client, nhưng server phải thiết kế event ID và cách phát lại phù hợp nếu không muốn client bỏ lỡ sự kiện trong khoảng mất kết nối.

## 13. Xử lý lỗi sau khi stream đã bắt đầu

Với response streaming, status và header HTTP thường đã được gửi khi phần tử đầu tiên được ghi. Nếu publisher phát lỗi sau đó, server không thể quay lại thay status thành `500` hoặc thay body đã gửi bằng một JSON error response thông thường.

Vì vậy:

- Xác thực, kiểm tra quyền và validate tham số trước khi bắt đầu stream nếu có thể.
- Với lỗi nghiệp vụ có thể xảy ra trong stream, định nghĩa event lỗi như `event: error` với payload có schema rõ.
- Với lỗi hạ tầng nghiêm trọng, có thể kết thúc kết nối; client phải xử lý việc stream bị ngắt.
- Mô tả lỗi khởi tạo stream bằng các HTTP status như 400, 401, 403 hoặc 404 trước khi body bắt đầu.
- Không hứa rằng mọi lỗi phát sinh giữa luồng đều được trả bằng Problem Details JSON như response đồng bộ.

Ví dụ event lỗi:

```text
event: error
data: {"code":"UPSTREAM_UNAVAILABLE","message":"Không thể nhận cập nhật lúc này"}

```

Nếu có event lỗi, đưa schema payload lỗi vào OpenAPI document và mô tả rằng đây là event nằm trong luồng `200 text/event-stream`, không phải một HTTP response status mới.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Flux<T>` trả về JSON array thay vì stream | Mapping dùng `application/json` | Chọn media type streaming như `text/event-stream` hoặc `application/x-ndjson` |
| Client nhận một khối dữ liệu sau thời gian dài | Client, proxy hoặc gateway đang buffer | Dùng cURL `-N`, kiểm tra proxy buffering và flush behavior |
| SSE không có `event` hoặc `id` | Trả `Flux<T>` thay vì `Flux<ServerSentEvent<T>>` | Dùng `ServerSentEvent<T>` khi cần metadata event |
| OpenAPI hiển thị JSON array cho SSE | Schema suy luận từ `Flux` hoặc annotation array | Khai báo response content/media type tường minh và kiểm tra document |
| NDJSON không parse được | Client dùng JSON array parser hoặc media type không khớp | Đọc từng dòng và parse từng JSON value |
| Server trả 406 | Header `Accept` không khớp `produces` | Gửi đúng Accept hoặc khai báo media type mà API thực sự hỗ trợ |
| Route hàm không xuất hiện trong Swagger UI | Thiếu `@RouterOperation`/`@RouterOperations` hoặc metadata không nhận diện đúng route | Khai báo path, method, produces và operationId chính xác |
| Event stream bị đóng khi idle | Proxy timeout hoặc không có heartbeat | Phát heartbeat và điều chỉnh timeout phù hợp |
| Client không gửi được Bearer token bằng EventSource | Native EventSource không hỗ trợ custom Authorization header | Dùng fetch streaming, client SSE hỗ trợ header hoặc cookie phù hợp |
| Lỗi xảy ra sau event đầu tiên nhưng không có HTTP 500 | Response đã commit | Định nghĩa event lỗi trong stream hoặc kết thúc kết nối theo hợp đồng |
| `itemSchema` bị validator từ chối | Document khai báo OpenAPI 3.0/3.1 | Chỉ dùng `itemSchema` với OpenAPI 3.2 và toolchain tương thích |

## 15. Checklist mô tả streaming response

- [ ] Đã chọn media type theo cách client nhận dữ liệu: SSE, NDJSON/JSON Lines hay JSON array.
- [ ] `produces` của controller hoặc functional route khớp `Content-Type` runtime.
- [ ] Client gửi `Accept` phù hợp với media type đã công bố.
- [ ] SSE dùng `text/event-stream`; NDJSON dùng media type được codec/client hỗ trợ.
- [ ] Đã phân biệt `Flux<T>` với JSON array và stream trên dây.
- [ ] OpenAPI response có đúng media type trong `content`.
- [ ] Description giải thích stream kéo dài, framing và cách parse từng phần tử.
- [ ] Example thể hiện đúng SSE frame hoặc NDJSON lines.
- [ ] Không dùng `@ArraySchema` để thay thế mô tả sequential media type.
- [ ] Nếu dùng OpenAPI 3.2, `itemSchema` mô tả một event/record và toàn bộ toolchain hỗ trợ.
- [ ] Functional routes được khai báo bằng `@RouterOperation`, `@RouterOperations` hoặc functional DSL.
- [ ] Đã kiểm tra `/v3/api-docs` hoặc group document sau khi chạy ứng dụng.
- [ ] Đã kiểm thử bằng cURL `-N`, WebTestClient hoặc client stream thực tế.
- [ ] Đã xem xét heartbeat, reconnect, cancellation và proxy buffering.
- [ ] Đã mô tả cách xử lý lỗi sau khi response đã bắt đầu gửi dữ liệu.

`text/event-stream` mô tả SSE với framing event, còn `application/x-ndjson` hoặc `application/jsonl` mô tả các JSON record phân tách theo dòng. `application/json` thường biểu diễn một JSON array hoàn chỉnh ngay cả khi method trả `Flux`. Trong Springdoc, hãy công bố đúng media type, giải thích cấu trúc từng event/record và xác minh document sinh ra. Nếu toàn bộ hệ sinh thái hỗ trợ OpenAPI 3.2, dùng `itemSchema` để mô tả từng phần tử của sequential stream; với OpenAPI 3.0/3.1, dùng schema/example tương thích và ghi rõ giới hạn biểu diễn.

## Tài liệu tham khảo

- [Spring Framework – WebFlux Controller Return Types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework – Reactive Core and JSON Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Springdoc OpenAPI v2 – WebFlux and Functional Endpoints](https://springdoc.org/v2/features.html#spring-webflux-webmvc-fn-with-functional-endpoints)
- [OpenAPI Specification 3.2.1 – Sequential Media Types](https://spec.openapis.org/oas/v3.2.1.html#sequential-media-types)
- [OpenAPI Specification 3.2.1 – Special Considerations for Server-Sent Events](https://spec.openapis.org/oas/v3.2.1.html#special-considerations-for-server-sent-events)
