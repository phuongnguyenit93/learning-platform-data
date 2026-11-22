# Phân biệt danh sách JSON với luồng dữ liệu liên tục

Trong Spring WebFlux, `Flux<T>` biểu diễn một chuỗi bất đồng bộ gồm từ không đến nhiều phần tử. Tuy nhiên, một controller trả về `Flux<T>` không có nghĩa HTTP response chắc chắn được gửi thành nhiều message độc lập ngay khi từng phần tử phát ra. Cách dữ liệu được mã hóa và truyền phụ thuộc `Content-Type`, HTTP message codec và hành vi của client.

Với JSON thông thường (`application/json`), nhiều phần tử thường được biểu diễn thành một JSON array. Với NDJSON, mỗi phần tử là một JSON object trên một dòng riêng. Với Server-Sent Events (SSE), mỗi sự kiện có framing `event`, `id`, `data` riêng. Chọn đúng định dạng giúp client đọc được dữ liệu tăng dần, giảm buffering và xử lý kết nối lâu dài đúng cách.

## 1. Flux không đồng nghĩa với HTTP streaming

`Flux<T>` là kiểu reactive ở phía ứng dụng. Nó mô tả một publisher có thể phát nhiều phần tử theo thời gian, hoàn tất hoặc kết thúc bằng lỗi. HTTP response là một representation trên mạng; `Content-Type` và codec quyết định cách các phần tử được biến thành byte.

Có ba khái niệm cần tách biệt:

1. **Reactive sequence:** `Flux<T>` phát các phần tử trong ứng dụng theo tín hiệu Reactive Streams.
2. **Representation của HTTP:** JSON array, NDJSON, SSE hoặc một định dạng khác được xác định bởi media type.
3. **Truyền dữ liệu qua mạng:** server ghi byte theo từng lần flush, theo chunk hoặc qua cơ chế transport tương ứng.

Một `Flux<Product>` có thể được mã hóa thành một JSON array hoàn chỉnh. Ngược lại, một `Flux<ProductEvent>` có thể được ghi thành nhiều record NDJSON hoặc nhiều SSE event. Chỉ nhìn kiểu trả về Java không thể xác định client sẽ nhận representation nào.

HTTP chunked transfer encoding cũng không đồng nghĩa NDJSON hoặc SSE. Chunking là cách truyền byte ở tầng HTTP/1.1; nó không quy định ranh giới JSON record hay event. Client phải dựa vào `Content-Type` và framing của representation, không được giả định một network chunk tương ứng với một object. HTTP/2 cũng có cơ chế frame riêng, không dùng `Transfer-Encoding: chunked` theo cách HTTP/1.1.

| Kiểu trả về và media type | Representation HTTP | Cách client tiêu thụ |
|---|---|---|
| `Mono<Product>` + `application/json` | Một JSON object | Đọc một document JSON |
| `Flux<Product>` + `application/json` | Một JSON array gồm nhiều object | Đọc một document JSON array |
| `Flux<ProductEvent>` + `application/x-ndjson` | Nhiều JSON object, mỗi object trên một dòng | Đọc và parse từng dòng |
| `Flux<ServerSentEvent<T>>` + `text/event-stream` | Nhiều SSE event có framing riêng | Đọc event theo giao thức EventSource |

## 2. Danh sách JSON: một document có cấu trúc array

Khi API trả một tập kết quả hữu hạn, JSON array là representation phổ biến và dễ tích hợp nhất.

Ví dụ response:

```json
[
  {"id": "p-101", "name": "Bút bi"},
  {"id": "p-102", "name": "Sổ tay"},
  {"id": "p-103", "name": "Thước kẻ"}
]
```

Controller:

```java
@GetMapping(
    value = "/api/products",
    produces = MediaType.APPLICATION_JSON_VALUE
)
Flux<ProductResponse> findAll() {
    return productService.findAll();
}
```

Với Jackson JSON encoder mặc định trong Spring Framework hiện hành, một multi-value publisher được ghi dưới `application/json` sẽ được gom thành list rồi serialize thành JSON collection. Vì vậy client nhận một document JSON array, không phải từng object độc lập có thể parse ngay khi nó xuất hiện.

Nếu API cần giới hạn số phần tử, có thể biểu diễn rõ ràng bằng `Mono<List<ProductResponse>>`:

```java
@GetMapping(value = "/api/products", produces = MediaType.APPLICATION_JSON_VALUE)
Mono<List<ProductResponse>> findAll() {
    return productService.findAll().collectList();
}
```

`collectList()` làm rõ rằng ứng dụng gom các phần tử trước khi trả list. Cách này phù hợp với tập kết quả có giới hạn và kích thước được kiểm soát. Không nên gom một luồng vô hạn hoặc một tập dữ liệu rất lớn vào bộ nhớ chỉ để tạo JSON array.

### Khi nào nên dùng JSON array?

- Kết quả tìm kiếm hoặc danh sách có giới hạn.
- Client cần parse một document hoàn chỉnh.
- Client cần xử lý toàn bộ collection trước khi hiển thị hoặc cập nhật state.
- API có phân trang, page size và giới hạn kích thước rõ ràng.

JSON array thường dễ mô tả trong OpenAPI: response schema là `type: array`, `items` trỏ tới schema của phần tử.

## 3. NDJSON: mỗi dòng là một JSON object độc lập

NDJSON (Newline Delimited JSON), còn gọi là JSON Lines, đóng khung dữ liệu bằng ký tự xuống dòng. Mỗi dòng chứa một JSON value độc lập; với API thường dùng object cho mỗi record.

Ví dụ body:

```text
{"id":"p-101","name":"Bút bi"}
{"id":"p-102","name":"Sổ tay"}
{"id":"p-103","name":"Thước kẻ"}
```

Body không có dấu ngoặc vuông bao quanh toàn bộ các record. Client có thể đọc từng dòng, parse JSON của dòng đó và bắt đầu xử lý trước khi server gửi xong toàn bộ response.

Spring WebFlux hỗ trợ các media type streaming JSON như `application/x-ndjson` và `application/jsonl`. Với streaming media type được codec hỗ trợ, Jackson encoder ghi và flush từng giá trị riêng lẻ.

Controller:

```java
@GetMapping(
    value = "/api/products/export",
    produces = "application/x-ndjson"
)
Flux<ProductExportRow> exportProducts() {
    return productService.exportRows();
}
```

Một client WebClient có thể đọc NDJSON thành từng object:

```java
Flux<ProductExportRow> rows = WebClient.create("http://localhost:8080")
    .get()
    .uri("/api/products/export")
    .accept(MediaType.parseMediaType("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(ProductExportRow.class);
```

### Khi nào nên dùng NDJSON?

- Export tập dữ liệu lớn theo từng record.
- Pipeline xử lý log, event hoặc batch data.
- Client cần xử lý tăng dần mà không chờ JSON array hoàn chỉnh.
- Producer có thể phát record trong thời gian dài nhưng mỗi record vẫn là JSON độc lập.

NDJSON không có metadata chuẩn cho toàn bộ stream như tổng số phần tử, page count hoặc trạng thái hoàn tất nghiệp vụ. Nếu cần metadata, có thể dùng header, endpoint riêng, record envelope có loại message hoặc giao thức khác được định nghĩa rõ.

## 4. Server-Sent Events: luồng event một chiều từ server tới client

SSE là giao thức gửi event từ server tới trình duyệt qua một kết nối HTTP lâu dài. Media type là `text/event-stream`. Mỗi event có thể chứa các trường `id`, `event`, `data` và `retry`; các trường được phân tách bằng dòng mới và event kết thúc bằng một dòng trống.

Ví dụ response:

```text
id: 101
event: product-updated
data: {"id":"p-101","name":"Bút bi mới"}

id: 102
event: product-created
data: {"id":"p-102","name":"Sổ tay"}

```

Controller WebFlux:

```java
@GetMapping(
    value = "/api/products/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<ServerSentEvent<ProductEvent>> watchProductEvents() {
    return productEventService.events()
        .map(event -> ServerSentEvent.builder(event)
            .id(event.id().toString())
            .event(event.type())
            .build());
}
```

Nếu chỉ cần trường `data`, controller có thể trả `Flux<ProductEvent>` với `produces = MediaType.TEXT_EVENT_STREAM_VALUE`; wrapper `ServerSentEvent` cần thiết khi muốn đặt id, event name, retry hoặc comment.

Client trình duyệt có thể dùng `EventSource`:

```javascript
const source = new EventSource("/api/products/events");

source.addEventListener("product-updated", event => {
  const product = JSON.parse(event.data);
  console.log("Updated product", product);
});

source.onerror = () => {
  console.log("SSE connection interrupted; browser may reconnect");
};
```

SSE phù hợp cho thông báo, tiến độ tác vụ, trạng thái đơn hàng hoặc dữ liệu dashboard cần cập nhật một chiều. Nếu client cũng cần gửi message liên tục lên server qua cùng giao thức hai chiều, hãy cân nhắc WebSocket hoặc một giao thức phù hợp khác.

## 5. So sánh JSON array, NDJSON và SSE

| Tiêu chí | JSON array | NDJSON | SSE |
|---|---|---|---|
| Media type | `application/json` | `application/x-ndjson` hoặc `application/jsonl` | `text/event-stream` |
| Framing | Một JSON document, thường là array | Một JSON value mỗi dòng | Event frame kết thúc bằng dòng trống |
| Metadata event | Không có cấu trúc chuẩn riêng | Không có cấu trúc chuẩn riêng | Có `id`, `event`, `retry`, `data` |
| Gửi tăng dần | Không nên giả định; encoder mặc định có thể gom thành list | Có, mỗi record được ghi riêng | Có, mỗi event được flush |
| Kết thúc | Kết thúc document JSON | EOF kết thúc stream record | Kết nối có thể duy trì lâu dài; event không đồng nghĩa hoàn tất nghiệp vụ |
| Client phổ biến | `fetch`, `WebClient`, JSON parser | Line reader, `WebClient.bodyToFlux` | Browser `EventSource`, SSE client |
| Trường hợp phù hợp | Danh sách hữu hạn | Export hoặc feed record | Event realtime một chiều |

Chọn định dạng theo cách consumer cần nhận dữ liệu, không theo việc service đang trả `Flux` hay `Mono`.

## 6. Content negotiation và khai báo produces

Spring WebFlux dùng `produces` để giới hạn representation mà endpoint có thể tạo. Client có thể gửi header `Accept` để yêu cầu định dạng phù hợp.

Ví dụ endpoint chỉ hỗ trợ NDJSON:

```java
@GetMapping(value = "/api/events", produces = "application/x-ndjson")
Flux<ProductEvent> events() {
    return eventService.stream();
}
```

Client:

```http
GET /api/events HTTP/1.1
Accept: application/x-ndjson
```

Nếu client gửi `Accept: application/json` trong khi endpoint chỉ công bố `application/x-ndjson`, Spring có thể trả `406 Not Acceptable`. Đây là hành vi đúng theo content negotiation; không nên âm thầm trả một framing khác với điều client yêu cầu.

Nếu API cần hỗ trợ nhiều representation, có thể khai báo nhiều media type trong `produces` và kiểm tra codec/handler có thể tạo từng representation:

```java
@GetMapping(
    value = "/api/products/feed",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        "application/x-ndjson"
    }
)
Flux<ProductResponse> feed() {
    return productService.feed();
}
```

Tuy nhiên, một endpoint có nhiều representation cần test rõ với từng header `Accept`; đừng giả định cùng một client parser có thể đọc cả JSON array và NDJSON.

## 7. Cấu hình codec quyết định cách ghi dữ liệu

WebFlux dùng `HttpMessageWriter` và codec để serialize response. Với Jackson, encoder nhận biết media type để quyết định gom nhiều phần tử hay ghi từng phần tử.

Theo tài liệu Spring Framework hiện hành:

- `Mono<T>` với JSON được serialize như một giá trị đơn.
- Multi-value publisher với `application/json` mặc định được gom thành list rồi serialize collection.
- Streaming media type như `application/jsonl` và `application/x-ndjson` ghi từng phần tử riêng và flush.
- Với SSE, Jackson encoder được gọi cho từng event và flush để dữ liệu được chuyển đi mà không phải chờ event tiếp theo.

Hành vi cụ thể phụ thuộc Spring Framework version và codec được cấu hình. Nếu ứng dụng đăng ký custom `Encoder`, `HttpMessageWriter` hoặc Gson thay cho Jackson, cần kiểm tra tài liệu và test của codec đó. Không suy luận hành vi chỉ từ tên `Flux`.

Ví dụ cấu hình codec giới hạn bộ nhớ:

```java
@Configuration
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
    }
}
```

Giới hạn bộ nhớ của codec có tác động tới các thao tác cần aggregate hoặc buffer. Không tăng giới hạn một cách tùy tiện để che việc endpoint đang gom một stream quá lớn vào RAM. Hãy chọn media type và cách xử lý dữ liệu phù hợp trước.

## 8. Mô tả JSON array trong OpenAPI

Với danh sách JSON hữu hạn, schema response nên là array và `items` trỏ tới schema của từng phần tử.

Ví dụ annotation:

```java
@Operation(summary = "Liệt kê sản phẩm")
@ApiResponse(
    responseCode = "200",
    description = "Danh sách sản phẩm dưới dạng JSON array",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        array = @ArraySchema(
            schema = @Schema(implementation = ProductResponse.class)
        )
    )
)
@GetMapping(value = "/api/products", produces = MediaType.APPLICATION_JSON_VALUE)
Flux<ProductResponse> findAll() {
    return productService.findAll();
}
```

Schema OpenAPI tương ứng:

```yaml
responses:
  '200':
    description: Danh sách sản phẩm dưới dạng JSON array
    content:
      application/json:
        schema:
          type: array
          items:
            $ref: '#/components/schemas/ProductResponse'
```

Springdoc có thể suy luận schema từ `Flux<ProductResponse>` trong controller. `@ApiResponse`/`@ArraySchema` giúp công bố representation rõ ràng khi suy luận không khớp hoặc khi muốn kiểm soát description.

## 9. Mô tả NDJSON trong OpenAPI

NDJSON không phải một JSON array. Mỗi dòng là một JSON value độc lập. OpenAPI có thể mô tả media type và schema của một record, đồng thời description giải thích quy tắc phân tách dòng.

Ví dụ:

```java
@Operation(
    summary = "Xuất sự kiện sản phẩm",
    description = "Response là NDJSON: mỗi dòng chứa một ProductEvent JSON độc lập."
)
@ApiResponse(
    responseCode = "200",
    description = "Luồng record NDJSON",
    content = @Content(
        mediaType = "application/x-ndjson",
        schema = @Schema(implementation = ProductEvent.class)
    )
)
@GetMapping(value = "/api/products/export", produces = "application/x-ndjson")
Flux<ProductEvent> export() {
    return productEventService.export();
}
```

Trong ví dụ này, schema mô tả một record trên mỗi dòng. Description phải nói rõ framing NDJSON và cách client đọc nhiều record cho tới EOF. Không mô tả response NDJSON như một JSON array nếu wire format thực tế không có dấu `[` và `]`.

OpenAPI mô tả media type và schema của dữ liệu nhưng không có một trường tiêu chuẩn riêng để mô tả toàn bộ semantics của một luồng NDJSON vô hạn. Dùng `description`, `example` và tài liệu operation để giải thích newline framing, thứ tự record, điều kiện kết thúc và cách xử lý lỗi.

## 10. Mô tả SSE trong OpenAPI

SSE là một text protocol có các field framing. Nếu controller trả `Flux<ServerSentEvent<ProductEvent>>`, phần `data` có thể chứa JSON nhưng toàn bộ response vẫn là `text/event-stream`.

Ví dụ annotation:

```java
@Operation(
    summary = "Theo dõi thay đổi sản phẩm",
    description = "Mở kết nối SSE; mỗi event có event name và data là ProductEvent JSON."
)
@ApiResponse(
    responseCode = "200",
    description = "SSE event stream",
    content = @Content(
        mediaType = MediaType.TEXT_EVENT_STREAM_VALUE,
        schema = @Schema(
            type = "string",
            description = "SSE frames gồm id, event và data; data chứa ProductEvent JSON."
        )
    )
)
@GetMapping(value = "/api/products/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<ProductEvent>> events() {
    return productEventService.events()
        .map(event -> ServerSentEvent.builder(event)
            .id(event.id().toString())
            .event(event.type())
            .build());
}
```

Schema `string` ở đây mô tả body dạng text/event-stream. `ProductEvent` là payload của field `data`, không phải toàn bộ frame SSE. Cần giải thích rõ cấu trúc `id`, `event`, `data`, `retry` nếu client cần sử dụng chúng.

Ví dụ một event trong description:

```text
id: 101
event: product-updated
data: {"id":"p-101","name":"Bút bi mới"}

```

Không khai báo SSE response thành `application/json` chỉ vì phần `data` là JSON. Media type của toàn bộ stream vẫn là `text/event-stream`.

## 11. Error handling khi response đã bắt đầu stream

Với JSON array được gom trước khi serialize, server có thể phát hiện một số lỗi trước khi body được ghi hoàn chỉnh. Với NDJSON hoặc SSE, sau khi record/event đầu tiên được gửi, HTTP response có thể đã được commit.

Khi response đã commit:

- Server không thể đổi status thành 500 và thay body bằng một Problem Details document như khi response chưa bắt đầu.
- Một lỗi giữa stream có thể làm kết nối kết thúc bất thường hoặc thiếu record cuối.
- Client cần phân biệt stream kết thúc bình thường với kết nối bị ngắt.
- Nếu nghiệp vụ cần thông báo lỗi ở cấp giao thức, phải định nghĩa cách biểu diễn lỗi trong stream.

Với SSE, có thể định nghĩa event `error` có payload theo schema riêng, sau đó kết thúc stream hoặc giữ kết nối theo chính sách. Với NDJSON, có thể định nghĩa một envelope có field `type` như `data`, `error`, `complete`; client phải biết phân biệt các record đó. Đừng tự thêm record lỗi vào stream nếu consumer không được thông báo về quy ước này.

Ví dụ envelope NDJSON:

```json
{"type":"data","payload":{"id":"p-101","name":"Bút bi"}}
{"type":"data","payload":{"id":"p-102","name":"Sổ tay"}}
{"type":"error","code":"SOURCE_UNAVAILABLE","message":"Nguồn dữ liệu tạm thời không khả dụng"}
```

Envelope này là hợp đồng do ứng dụng định nghĩa; không phải quy tắc mặc định của NDJSON hoặc Spring WebFlux. Nếu sử dụng, hãy mô tả schema discriminated union tương ứng trong OpenAPI.

## 12. Backpressure, buffering và giới hạn tài nguyên

Reactive Streams có cơ chế backpressure để subscriber báo lượng phần tử mà nó sẵn sàng nhận. Điều này giúp phối hợp tốc độ giữa publisher và subscriber bên trong pipeline reactive. Tuy nhiên, backpressure không đồng nghĩa mọi HTTP client hoặc reverse proxy tự động kiểm soát tốc độ producer theo cùng một cách.

Một số nguyên tắc:

- Không dùng `collectList()` cho nguồn dữ liệu lớn hoặc vô hạn.
- Không dùng `onBackpressureBuffer()` không giới hạn cho luồng có producer nhanh hơn consumer.
- Đặt giới hạn số record, buffer, thời gian và concurrency khi phù hợp.
- Xử lý cancellation khi client đóng kết nối để dừng công việc upstream không còn cần thiết.
- Theo dõi metric về số kết nối mở, tốc độ phát record, thời gian sống kết nối và số lỗi.
- Với SSE lâu dài, gửi heartbeat định kỳ nếu môi trường proxy/load balancer cần traffic để nhận biết client còn kết nối.

Ví dụ giới hạn số record:

```java
Flux<ProductEvent> export() {
    return productEventService.events()
        .take(10_000);
}
```

Ví dụ giới hạn thời gian stream:

```java
Flux<ProductEvent> watch() {
    return productEventService.events()
        .take(Duration.ofMinutes(5));
}
```

Giới hạn cụ thể phải phù hợp với nghiệp vụ. Không đặt `take` tùy tiện nếu API hứa hẹn stream vô hạn; hãy công bố điều kiện kết thúc và cách client mở kết nối lại.

## 13. Client đọc từng định dạng như thế nào?

### JSON array

Client thường chờ một JSON document hợp lệ rồi parse thành list:

```javascript
const response = await fetch("/api/products", {
  headers: { Accept: "application/json" }
});
const products = await response.json();
```

### NDJSON

Client cần đọc response body theo chunk, ghép dữ liệu chưa đủ dòng và parse từng dòng hoàn chỉnh. Không giả định mỗi network chunk luôn tương ứng đúng một dòng hoặc một record.

Ví dụ Java WebClient:

```java
Flux<ProductEvent> events = webClient.get()
    .uri("/api/products/export")
    .accept(MediaType.parseMediaType("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(ProductEvent.class);
```

### SSE

Trình duyệt có thể dùng `EventSource` cho kết nối GET một chiều. Java WebClient có thể đọc `ServerSentEvent`:

```java
ParameterizedTypeReference<ServerSentEvent<ProductEvent>> eventType =
    new ParameterizedTypeReference<>() {};

Flux<ServerSentEvent<ProductEvent>> events = webClient.get()
    .uri("/api/products/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .retrieve()
    .bodyToFlux(eventType);
```

Với SSE, client cần xử lý reconnect, `Last-Event-ID` nếu dùng event id và khả năng nhận event trùng lặp sau reconnect. Thiết kế consumer theo hướng idempotent nếu event có thể được phát lại.

## 14. Kiểm thử representation bằng WebTestClient

Test cần kiểm tra `Content-Type` và hình dạng body, không chỉ status 200.

### Kiểm tra JSON array

```java
webTestClient.get()
    .uri("/api/products")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBodyList(ProductResponse.class)
    .hasSize(2);
```

### Kiểm tra NDJSON

```java
FluxExchangeResult<ProductEvent> result = webTestClient.get()
    .uri("/api/products/export")
    .accept(MediaType.parseMediaType("application/x-ndjson"))
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(
        MediaType.parseMediaType("application/x-ndjson")
    )
    .returnResult(ProductEvent.class);

StepVerifier.create(result.getResponseBody())
    .expectNextCount(2)
    .verifyComplete();
```

### Kiểm tra SSE

```java
ParameterizedTypeReference<ServerSentEvent<ProductEvent>> eventType =
    new ParameterizedTypeReference<>() {};

FluxExchangeResult<ServerSentEvent<ProductEvent>> result = webTestClient.get()
    .uri("/api/products/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
    .returnResult(eventType);

StepVerifier.create(result.getResponseBody())
    .assertNext(event -> {
        assertThat(event.event()).isEqualTo("product-updated");
        assertThat(event.data()).isNotNull();
    })
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

Với stream vô hạn, dùng `thenCancel()` sau khi kiểm tra các event mong muốn để test không chờ stream hoàn tất. Đảm bảo test có timeout hợp lý và publisher được dọn dẹp khi subscription bị cancel. Ví dụ cần import `java.time.Duration` và Reactor Test `StepVerifier`.

## 15. Kiểm tra OpenAPI document được springdoc tạo

Sau khi khai báo annotation, tải `/v3/api-docs` và kiểm tra response content theo media type:

- Endpoint danh sách JSON có `application/json` và schema array.
- Endpoint NDJSON có `application/x-ndjson`, schema của một record và description nói rõ newline framing.
- Endpoint SSE có `text/event-stream`, description về event frame và payload `data`.
- Response status và ví dụ phải khớp hành vi runtime.

Ví dụ OpenAPI YAML rút gọn:

```yaml
paths:
  /api/products:
    get:
      responses:
        '200':
          description: Danh sách sản phẩm dưới dạng JSON array
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ProductResponse'
  /api/products/export:
    get:
      responses:
        '200':
          description: Mỗi dòng là một ProductEvent JSON độc lập (NDJSON)
          content:
            application/x-ndjson:
              schema:
                $ref: '#/components/schemas/ProductEvent'
  /api/products/events:
    get:
      responses:
        '200':
          description: SSE stream; data của mỗi event chứa ProductEvent JSON
          content:
            text/event-stream:
              schema:
                type: string
```

OpenAPI mô tả media type và schema, nhưng semantics về thời gian sống của stream, heartbeat, reconnect, cancellation và terminal error cần được ghi trong description hoặc tài liệu giao thức đi kèm.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Client nhận một JSON array dù controller trả `Flux` | Endpoint dùng `application/json`; encoder gom nhiều phần tử thành collection | Dùng NDJSON hoặc SSE nếu cần record/event độc lập |
| Client parse lỗi vì mong array nhưng nhận nhiều dòng | Server công bố NDJSON, client dùng JSON document parser | Dùng line reader hoặc WebClient `bodyToFlux` |
| Dữ liệu không tới client ngay khi phần tử được tạo | Codec đang aggregate hoặc proxy đang buffer | Chọn streaming media type và kiểm tra proxy buffering/flush |
| SSE client không nhận event name | Controller trả object trực tiếp thay vì `ServerSentEvent` | Dùng wrapper để khai báo `event`, `id`, `retry` |
| Response trả 406 | `Accept` không tương thích với `produces` | Đồng bộ media type giữa client và endpoint |
| OpenAPI mô tả NDJSON thành array | Springdoc suy luận theo generic publisher hoặc annotation chưa tường minh | Override `@ApiResponse` và ghi rõ một record mỗi dòng |
| OpenAPI mô tả SSE như JSON object | Nhầm payload `data` với toàn bộ SSE frame | Dùng `text/event-stream`, mô tả frame và payload riêng |
| Lỗi xảy ra sau vài record nhưng client không nhận Problem Details | Response đã commit và một phần stream đã được gửi | Định nghĩa error record/event hoặc đóng stream theo hợp đồng |
| Bộ nhớ tăng theo thời gian | Gom list hoặc buffer không giới hạn | Dùng streaming media type, giới hạn dữ liệu và buffer |
| Stream vẫn chạy sau khi client rời đi | Nguồn không xử lý cancellation hoặc tác vụ upstream không được dispose | Kiểm tra lifecycle, `doFinally` và cancellation của publisher |
| SSE ngắt sau một khoảng thời gian cố định | Proxy/load balancer timeout hoặc thiếu heartbeat | Cấu hình idle timeout và gửi heartbeat định kỳ |

## 17. Quy trình chọn representation cho endpoint

Khi thiết kế endpoint trả nhiều phần tử, hãy xác định:

1. Kết quả là một tập hữu hạn hay một luồng kéo dài?
2. Client cần một JSON document hoàn chỉnh hay cần xử lý từng record ngay khi nhận?
3. Có cần metadata event như `id`, `event`, `retry` và reconnect không?
4. Media type nào phản ánh đúng framing: `application/json`, `application/x-ndjson` hay `text/event-stream`?
5. Có giới hạn kích thước, thời gian, số record và buffer không?
6. Client xử lý cancellation, reconnect và record lỗi như thế nào?
7. OpenAPI đã mô tả đúng media type, schema và semantics chưa?
8. Test đã xác minh body thực tế, header và hành vi streaming chưa?

Với danh sách hữu hạn và kích thước có giới hạn, JSON array là lựa chọn đơn giản. Với tập record lớn cần đọc tăng dần, NDJSON phù hợp hơn. Với thông báo realtime một chiều tới trình duyệt, SSE cung cấp framing event rõ ràng. Spring WebFlux hỗ trợ cả ba; hợp đồng HTTP phải thể hiện đúng định dạng mà client sẽ nhận.

## 18. Tài liệu tham khảo

- [Spring Framework – WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): cách Spring xử lý `Flux`, `Mono` và SSE return type.
- [Spring Framework – Reactive Core and JSON Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Jackson encoder, JSON array, NDJSON, SSE và streaming codec.
- [Spring Framework – @ResponseBody in WebFlux](https://docs.spring.io/spring/reference/web/webflux/controller/ann-methods/responsebody.html): reactive return types và HTTP message writers.
- [Project Reactor – Flux](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html): ý nghĩa chuỗi 0..N phần tử của `Flux`.
- [Project Reactor – Backpressure](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactiveProgramming.html): demand và backpressure trong Reactive Streams.
- [Project Reactor – Hot vs Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html): khác biệt publisher hot và cold.
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object): mô tả media type, schema và examples trong response content.
- [Springdoc OpenAPI](https://springdoc.org/): sinh OpenAPI document từ controller và cấu hình response schema.
