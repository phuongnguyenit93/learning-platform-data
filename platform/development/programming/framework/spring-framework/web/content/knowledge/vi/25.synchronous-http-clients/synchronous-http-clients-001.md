# Chọn RestClient, RestTemplate, WebClient hoặc HTTP Service Client trong Spring Framework

> **Ngữ cảnh:** HTTP client đồng bộ, nhưng cần hiểu cả phương án reactive và khai báo interface để chọn đúng kiến trúc. Bản hướng dẫn dùng **Spring Framework 6.2.x, Spring Boot 3.5.x và Java 17+** cho code chạy được. Spring Framework 7.x đã đánh dấu `RestTemplate` deprecated để hướng người dùng sang `RestClient`; điều này không có nghĩa `RestTemplate` ngừng chạy ngay, và **không** nên áp nguyên API Spring 7 lên project Spring 6.2. Mọi cấu hình HTTP timeout, pool, auth, error handling và tracing vẫn phải được kiểm tra theo phiên bản framework và thư viện transport thực tế.

## 1. Kết luận lựa chọn trong 30 giây

| Nhu cầu thực tế | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Mã Java/Spring MVC đồng bộ mới, gọi API JSON thông thường | **`RestClient`** | Fluent synchronous API, gọn, dễ đọc, dùng `HttpMessageConverter` |
| Codebase đã dùng nhiều `RestTemplate` ổn định | Giữ `RestTemplate` tạm thời, lên kế hoạch chuyển sang `RestClient` | Không phải thay toàn hệ thống chỉ vì có API mới |
| Gọi HTTP non-blocking, phối hợp nhiều remote calls, stream, WebFlux/Reactor | **`WebClient`** | Trả `Mono`/`Flux`, hỗ trợ reactive composition, backpressure/streaming |
| Nhiều endpoint của một remote service, muốn interface dễ đọc/dễ mock | **HTTP Service Client** trên `RestClient` hoặc `WebClient` | Proxy tạo từ interface `@HttpExchange`/`@GetExchange`, **không phải transport thứ tư** |
| Muốn interface khai báo nhưng vẫn giữ synchronous call site | HTTP Service Client + `RestClientAdapter` | Method trả DTO/`ResponseEntity<T>` đồng bộ |
| Muốn interface khai báo và method trả `Mono<T>`/`Flux<T>` | HTTP Service Client + `WebClientAdapter` | Reactive signature do transport adapter hỗ trợ |
| Một tác vụ định kỳ hoặc MVC controller xử lý I/O blocking theo request | `RestClient` hoặc interface proxy trên nó | Không cần thêm Reactor chỉ để GET một DTO |
| SSE, NDJSON hoặc response lớn/infinite stream | `WebClient` hoặc interface proxy trên nó | Streaming reactive, không gom hết vào bộ nhớ |

**Thứ tự ra quyết định:** (1) phương thức gọi **blocking hay non-blocking**, (2) API trực tiếp hay HTTP interface, (3) lựa chọn transport/pooling/timeouts/observability, (4) contract lỗi và retry. Đừng chọn client chỉ vì tên mới hơn hoặc vì “WebClient luôn nhanh hơn”.

## 2. Bốn khái niệm không cùng một cấp

`RestClient`, `RestTemplate` và `WebClient` trực tiếp xây/gửi HTTP requests; **HTTP Service Client** định nghĩa interface Java mà Spring tạo một proxy để **ủy quyền** các requests cho một trong những clients bên dưới.

```text
                    Spring HTTP client usage
                              |
                  +-----------+------------+
                  |                        |
             Fluent/direct             Interface-first
                  |                        |
      +-----------+-----------+       @HttpExchange
      |           |           |       @GetExchange
   RestClient  RestTemplate  WebClient        |
      |           |           |       HttpServiceProxyFactory
      +-----------+-----------+             |
                  |                  HTTP adapter lựa chọn
        Actual client request factory/connector
                  |
      TCP/TLS connection, HTTP exchange, codecs
                  |
             Remote HTTP API
```

- `RestClient`: synchronous fluent API, xuất hiện từ Spring Framework 6.1. Khi gọi terminal `retrieve().body(...)` hoặc `toEntity(...)`, caller đợi kết quả.
- `RestTemplate`: synchronous template-method API lâu đời, các phương thức như `getForObject`, `postForEntity`, `exchange`. Trên Spring 6.2 vẫn hoạt động; Spring 7 deprecates nó theo hướng khuyến nghị `RestClient`.
- `WebClient`: reactive HTTP API, sử dụng `Mono`/`Flux` của Reactor và HTTP connector non-blocking (thường Reactor Netty). Caller có thể compose async sources thay vì giữ thread chờ network.
- HTTP Service Client: một interface với `@HttpExchange`, `@GetExchange`, `@PostExchange`… do `HttpServiceProxyFactory` implement thông qua adapter. Với `RestClientAdapter`, method có thể trả DTO đồng bộ; với `WebClientAdapter`, có thể trả `Mono<T>`/`Flux<T>`.

**Điểm quan trọng:** interface proxy không thay business logic, không tự thêm circuit breaker, retry, transactions hay async execution. Những thuộc tính đó đến từ underlying client/config hoặc một layer ứng dụng được triển khai rõ.

## 3. So sánh chi tiết

| Thuộc tính | RestClient | RestTemplate | WebClient | HTTP Service Client |
| --- | --- | --- | --- | --- |
| Hình thức API | Fluent | Template operations | Fluent reactive | Annotated interface + proxy |
| Bản chất | Synchronous/blocking caller | Synchronous/blocking caller | Non-blocking HTTP I/O khi cấu hình thích hợp | **Phụ thuộc adapter** |
| Kiểu return phổ biến | DTO, `ResponseEntity<T>` | DTO, `ResponseEntity<T>` | `Mono<T>`, `Flux<T>` | DTO hoặc Mono/Flux tùy adapter/signature |
| JSON conversion | `HttpMessageConverter` | `HttpMessageConverter` | Reactive `HttpMessageReader/Writer` | Theo client nền |
| HTTP status errors mặc định | 4xx/5xx ném `RestClientException`/subtype với `retrieve()` | Default `ResponseErrorHandler` ném exception 4xx/5xx | `retrieve()` tạo error signal `WebClientResponseException` khi subscribe | Theo client nền và status policy |
| Custom lỗi | `onStatus`, builder status handler, `exchange` | `ResponseErrorHandler`, `exchange` | `onStatus`, `exchangeToMono/Flux` | Cấu hình underlying client |
| Streaming/backpressure | Không native reactive | Không native reactive | Native publisher/streaming | Native khi dùng reactive adapter |
| Dễ tích hợp Spring MVC blocking code | Rất phù hợp | Phù hợp khi có legacy | Có thể dùng, nhưng cần xác định sync/async contract | Tốt với sync adapter |
| Dễ tích hợp WebFlux event loop | **Không nên gọi trực tiếp** vì blocking | **Không nên gọi trực tiếp** | Phù hợp | Chọn WebClientAdapter |
| Connection pooling | Tùy `ClientHttpRequestFactory` | Tùy `ClientHttpRequestFactory` | Tùy `ClientHttpConnector`/Netty pool | Theo client nền |
| Phù hợp code mới Spring 6.2 | Ưu tiên synchronous | Chủ yếu bảo trì | Reactive/concurrent streaming | Interface-first khi giảm boilerplate có ích |

### 3.1. REST API và transport là hai lớp

Cùng một `RestClient` có thể chạy qua những HTTP libraries/request factories khác nhau. Cũng như vậy, `WebClient` có thể dùng Reactor Netty connector hoặc connector phù hợp khác. Lựa chọn “RestClient vs WebClient” nói lên **programming model** trước; throughput/latency còn phụ thuộc transport implementation, DNS, TLS, pool size, server khả dụng, payload và lưu lượng.

### 3.2. Không đồng nhất Reactive client với Reactive server

Ứng dụng Spring MVC/Servlet **có thể dùng `WebClient`** để gọi downstream, thậm chí return `Mono<T>` từ MVC controller qua Servlet async support. Điều này **không làm `DispatcherServlet` biến thành `DispatcherHandler`**. Ngược lại, WebFlux server vẫn có thể gọi một thư viện blocking, nhưng không nên gọi trực tiếp ở non-blocking event-loop.

### 3.3. Phiên bản cần nhớ

- `RestTemplate`: đã có từ Spring 3.0, dùng lâu năm.
- `WebClient`: có từ Spring 5.0 (WebFlux).
- `@HttpExchange`/HTTP Interface: từ Spring 6.0.
- `RestClient`: từ Spring 6.1.
- Với Spring 6.2, `HttpServiceProxyFactory.builderFor(adapter)` là API đúng; tránh các snippets rất cũ dùng `builder(HttpClientAdapter)` đã deprecated/loại bỏ.
- Từ Spring 7, `RestTemplate` bị đánh dấu deprecated để hướng đến `RestClient`; không suy diễn “mọi project Spring 6.2 ngay lập tức compile warning deprecated”.

## 4. RestClient: mặc định tốt cho HTTP đồng bộ mới

### 4.1. Một GET đơn giản

```java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

Item item = client.get()
        .uri("/items/{id}", 7)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(Item.class);
```

**Đây là snippet**: cần `Item` record/class, imports, endpoint thật. `.retrieve()` trả một `ResponseSpec`; **chưa phải terminal operation**. Lời gọi `.body(Item.class)` sẽ thực hiện exchange và decode result. Vì là synchronous API, thread gọi hàm phải chờ network/exchange/response decoding hoàn tất.

### 4.2. Muốn status và headers

```java
ResponseEntity<Item> response = client.get()
        .uri("/items/{id}", 7)
        .retrieve()
        .toEntity(Item.class);

HttpStatusCode status = response.getStatusCode();
HttpHeaders headers = response.getHeaders();
Item body = response.getBody();
```

Nếu server trả 204 thành công không body, `body` có thể null; kiểu DTO không có nghĩa runtime luôn trả value. Nếu status là 4xx/5xx, `retrieve()` thường ném exception trước khi bạn nhận `ResponseEntity`, trừ khi đã có handler tùy biến.

### 4.3. POST JSON

```java
record CreateItem(String name) {}

Item created = client.post()
        .uri("/items")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(new CreateItem("Java"))
        .retrieve()
        .body(Item.class);
```

Đoạn này minh họa request body converter; API thực có thể trả 201 + Location, nên `toEntity(Item.class)` phù hợp nếu cần đọc header Location hoặc ETag.

### 4.4. Danh sách generic

```java
List<Item> items = client.get()
        .uri("/items")
        .retrieve()
        .body(new ParameterizedTypeReference<List<Item>>() {});
```

Dùng `ParameterizedTypeReference` khi response là list/map generic; `List.class` không lưu element type tại runtime và dễ khiến JSON items trở thành `Map` thay vì `Item`.

### 4.5. Kiểm tra status rõ ràng

```java
Item item = client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(HttpStatusCode::is4xxClientError,
                (request, response) -> {
                    throw new IllegalStateException(
                            "Catalog returned " + response.getStatusCode());
                })
        .body(Item.class);
```

Snippet này minh họa syntax, **không khuyến khích biến mọi 4xx thành IllegalStateException** trong production. Hãy phân loại 404/resource missing, 401/403/auth, 429/rate-limit; log an toàn. `RestClient` mặc định đã throw cho 4xx/5xx; custom `onStatus` chỉ cần khi contract khác.

### 4.6. retrieve vs exchange

`RestClient.retrieve()` thực hiện high-level status handling/conversion. `RestClient.exchange((request,response) -> ...)` cho quyền xử lý lower-level với response trực tiếp.

**Bẫy:** trong RestClient, `exchange` bỏ qua status handlers gắn cho `retrieve`. Vì vậy nếu dùng `exchange` để lấy response raw, **phải** quyết định status, kiểm tra 4xx/5xx, body/resource closure đúng. Không chọn exchange chỉ vì trông “linh hoạt hơn” khi bài toán chỉ cần DTO.

## 5. RestTemplate: khi nào giữ và khi nào chuyển?

### 5.1. Dùng trong codebase hiện hữu

```java
RestTemplate template = new RestTemplate();

Item item = template.getForObject(
        "https://catalog.example.test/items/{id}",
        Item.class,
        7);
```

API này vẫn được hỗ trợ trong Spring 6.2 và tiện cho hệ thống cũ. `RestTemplate` sử dụng `HttpMessageConverter`, `ClientHttpRequestFactory` và request interceptors, tương tự hạ tầng dùng chung với `RestClient`. Một bean RestTemplate có thể được dùng từ nhiều threads sau khi cấu hình xong, nhưng **không** nên sửa config concurrent khi đang phục vụ requests.

### 5.2. exchange và generic result

```java
ResponseEntity<List<Item>> result = template.exchange(
        "https://catalog.example.test/items",
        HttpMethod.GET,
        HttpEntity.EMPTY,
        new ParameterizedTypeReference<List<Item>>() {});
```

Snippet minh họa signature (không phải full program). Với cần header authorization, tạo `HttpEntity<?>` có HttpHeaders thích hợp, hoặc cấu hình interceptor cấp token tin cậy. Không gắn raw token vào query string hoặc stdout.

### 5.3. Phân biệt “legacy” với “cần rewrite ngay”

- Không có lý do phải dừng một dịch vụ đang chạy tốt chỉ vì `RestTemplate` có API cũ; thay client phải được test về exceptions, URI encoding, status, timeout, pooling và request interceptors.
- Với code đồng bộ **mới**, `RestClient` thường rõ ràng hơn và được Spring khuyến nghị.
- Spring Framework 7 deprecates `RestTemplate`; vì thế nên tránh tạo thêm khối lượng code RestTemplate mới nếu có thể.
- Đừng chuyển sang WebClient chỉ để “thoát RestTemplate” khi call sites đồng bộ và bạn dự định gọi `.block()` ở khắp nơi; lựa chọn tự nhiên là RestClient.

### 5.4. Chuyển RestTemplate sang RestClient

| RestTemplate | RestClient tương ứng |
| --- | --- |
| `getForObject(url,Item.class,id)` | `get().uri(url,id).retrieve().body(Item.class)` |
| `getForEntity(url,Item.class,id)` | `get().uri(url,id).retrieve().toEntity(Item.class)` |
| `postForObject(url,request,Item.class)` | `post().uri(url).body(request).retrieve().body(Item.class)` |
| `delete(url,id)` | `delete().uri(url,id).retrieve().toBodilessEntity()` |
| `exchange(...,ParameterizedTypeReference)` | `method(...).uri(...).body(...).retrieve().toEntity(new ParameterizedTypeReference<...>() {})` |
| `setErrorHandler(...)` | `onStatus(...)` hoặc builder defaultStatusHandler |
| `ClientHttpRequestFactory` | Chọn requestFactory phù hợp ở RestClient.Builder |

Bảng là **định hướng migration**, không phải phép thay thế máy móc từng overload. Kiểm tra status handling, encoding và đặc biệt các phương thức REST được gọi sau khi convert. Nếu application dùng interceptors, SSL client certificates, OAuth2, proxy hoặc compression thì phải di chuyển cấu hình tương ứng.

## 6. WebClient: khi cần reactive, async fan-out hoặc streaming

### 6.1. GET non-blocking

```java
WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

Mono<Item> pending = client.get()
        .uri("/items/{id}", 7)
        .retrieve()
        .bodyToMono(Item.class);
```

Khác với RestClient:
- `pending` mô tả một **reactive HTTP operation**, thường cold/lazy.
- Không có request thật chỉ vì tạo biến Mono; khi **subscribe** mới bắt đầu.
- Trong WebFlux controller, return Mono/Flux cho framework subscribe.
- Trong Spring MVC controller, có thể return Mono để MVC async adapter xử lý, nhưng server vẫn chạy MVC.
- Không gọi `pending.subscribe()` rồi return `null`, vì detached work không còn gắn response/error/cancellation.

### 6.2. Nhiều request độc lập

```java
Mono<Item> item = client.get()
        .uri("/items/{id}", 7)
        .retrieve()
        .bodyToMono(Item.class);

Mono<Stock> stock = client.get()
        .uri("/stock/{id}", 7)
        .retrieve()
        .bodyToMono(Stock.class);

Mono<ItemPage> page = Mono.zip(
        item, stock,
        (i, s) -> new ItemPage(i, s));
```

Snippets cần `Stock`/`ItemPage` DTOs. Với hai upstream calls độc lập, `Mono.zip` có thể overlap I/O và tổng latency thường gần max latency cộng overhead thay vì cộng hai latency tuần tự. Nhưng nếu một Mono rỗng, zip có thể hoàn tất rỗng. Với 404 cần mô hình rõ `switchIfEmpty` hoặc error mapping.

### 6.3. Fan-out danh sách có giới hạn

```java
Flux<Item> items = Flux.fromIterable(ids)
        .flatMap(id -> client.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(Item.class),
                5);
```

`flatMap(...,5)` giới hạn inner publishers ở **một pipeline/subscription**, không phải tối đa năm connections của toàn ứng dụng. 100 inbound requests mỗi request concurrency=5 có thể tạo tới khoảng 500 operations đang active. Cần connection pool limits, rate-limit/bulkhead global, timeout và backpressure.

Nếu phải giữ output theo thứ tự IDs, cân nhắc `flatMapSequential`; nếu side effects phải thực thi tuần tự, `concatMap`. Tăng concurrency không luôn tăng throughput khi downstream đã bão hòa.

### 6.4. Lỗi HTTP reactive

```java
Mono<Item> item = client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                response -> Mono.error(
                        new ItemNotFoundException(id)))
        .bodyToMono(Item.class);
```

Snippet cần `ItemNotFoundException`. Với `retrieve()`, 4xx/5xx mặc định thành `WebClientResponseException` error signal. `exchangeToMono`/`exchangeToFlux` cho phép kiểm soát response status/body tùy outcome, nhưng phải consume/release body theo contract trước khi thoát callback. Không lưu cả error body lớn hoặc log PII/raw upstream error như một detail gửi client.

### 6.5. Có được dùng WebClient rồi block trong MVC?

Spring reference có hướng dẫn sử dụng `WebClient...bodyToMono(...).block()` trong môi trường đồng bộ, nhưng:
- Điều đó **vẫn chặn thread gọi**; nó không tự mang lại non-blocking end-to-end.
- Tránh làm vậy trên WebFlux event loop, nơi blocking terminal operation có thể bị cấm hoặc làm nghẽn.
- Nếu phần còn lại của ứng dụng synchronous, `RestClient` thường đơn giản hơn.
- Nếu cần chờ **nhiều** requests nhưng không thể đổi call site, có thể compose chúng trước bằng `Mono.zip` rồi block **một lần tại ranh giới thực sự được phép blocking**; không block từng request tuần tự.

### 6.6. Streaming response

```java
Flux<EventDto> events = client.get()
        .uri("/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(EventDto.class);
```

Đây là snippet, yêu cầu server và codec hỗ trợ event stream, class EventDto. Với SSE/NDJSON nên tránh `collectList()` khi stream vô hạn: nó không hoàn tất và có thể giữ dữ liệu không giới hạn. Cần cancellation, reconnect policy, backpressure, authentication expiry, memory limits và xử lý event ID/duplicate semantics theo protocol.

## 7. HTTP Service Client: interface + proxy, không phải thư viện HTTP thứ tư

### 7.1. Interface với @HttpExchange

```java
@HttpExchange("/items")
interface ItemApi {

    @GetExchange("/{id}")
    Item find(@PathVariable("id") long id);

    @GetExchange
    List<Item> list();
}
```

Đây là interface sync dùng với `RestClientAdapter` hoặc `RestTemplateAdapter`. `@HttpExchange` mô tả common base path, `@GetExchange` mô tả GET endpoint; tương tự có `@PostExchange`, `@PutExchange`, `@PatchExchange`, `@DeleteExchange`. Proxy tạo động implement interface, nên **không** cần tự viết implementation gửi HTTP.

**Lưu ý:** Spring HTTP Service Client interface là **client contract** được thực thi bởi proxy, khác hẳn cách server dispatch annotated controller. Interface không chứa transport, connection pool hay authentication policy; chúng được cấu hình trên client nền.

### 7.2. Proxy đồng bộ trên RestClient

```java
RestClient restClient = RestClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

RestClientAdapter adapter = RestClientAdapter.create(restClient);

HttpServiceProxyFactory proxyFactory =
        HttpServiceProxyFactory.builderFor(adapter).build();

ItemApi itemApi = proxyFactory.createClient(ItemApi.class);

Item item = itemApi.find(7);  // Call đồng bộ.
```

Đây là snippet; cần đúng imports:
- `org.springframework.web.client.RestClient`;
- `org.springframework.web.client.support.RestClientAdapter`;
- `org.springframework.web.service.invoker.HttpServiceProxyFactory`;
- `org.springframework.web.service.annotation.HttpExchange` và `GetExchange`;
- `org.springframework.web.bind.annotation.PathVariable`.

Method `find` trả Item vì adapter synchronous. Nếu remote bị chậm, thread gọi proxy vẫn chờ như khi gọi RestClient trực tiếp.

### 7.3. Proxy reactive trên WebClient

```java
@HttpExchange("/items")
interface ReactiveItemApi {
    @GetExchange("/{id}")
    Mono<Item> find(@PathVariable("id") long id);

    @GetExchange
    Flux<Item> stream();
}

WebClient webClient = WebClient.builder()
        .baseUrl("https://catalog.example.test")
        .build();

ReactiveItemApi reactiveApi = HttpServiceProxyFactory
        .builderFor(WebClientAdapter.create(webClient))
        .build()
        .createClient(ReactiveItemApi.class);

Mono<Item> future = reactiveApi.find(7);
```

Đoạn trên là snippet cần imports; `Flux<Item>` chỉ phù hợp khi remote response/codec hợp lý cho nhiều values, không phải tự động biến JSON object thành stream. Dùng `org.springframework.web.reactive.function.client.support.WebClientAdapter`. Với reactive signature, không dùng sync `RestClientAdapter` rồi mong proxy tự trả Mono/Flux non-blocking.

### 7.4. Proxy trên RestTemplate

Trong Spring 6.2 cũng có `RestTemplateAdapter`:

```java
RestTemplate template = new RestTemplate();

RestTemplateAdapter adapter =
        RestTemplateAdapter.create(template);

ItemApi api = HttpServiceProxyFactory
        .builderFor(adapter)
        .build()
        .createClient(ItemApi.class);
```

Đây là snippet; muốn dùng relative paths ở interface thì cấu hình `DefaultUriBuilderFactory(baseUrl)` cho RestTemplate trước. Nếu không có base URL, relative `/items/{id}` không đủ để mở connection. Đây là bridge tiện cho dự án cũ nhưng không phải lý do bắt đầu code mới trên RestTemplate.

### 7.5. Annotated method parameters

HTTP interface có thể nhận:
- `@PathVariable`: chèn URI template variables và encode đúng;
- `@RequestParam`: query/form params tùy method/content type;
- `@RequestHeader`: request headers;
- `@RequestBody`: request object;
- `URI` hoặc `UriBuilderFactory` cho dynamic target theo API được framework hỗ trợ.

Ví dụ:

```java
@HttpExchange("/orders")
interface OrderApi {

    @GetExchange("/{id}")
    OrderView find(@PathVariable("id") long id,
                   @RequestHeader("X-Correlation-Id") String traceId);

    @PostExchange(contentType = "application/json")
    OrderView create(@RequestBody CreateOrder command);
}
```

Đây là interface snippet; `OrderView` và `CreateOrder` cần khai báo. Header trace ID không thay Authorization. Sự kiện POST tạo resource có thể cần `ResponseEntity<OrderView>` để đọc Location/ETag nếu API contract yêu cầu.

### 7.6. Kiểu return theo adapter

| Return của HTTP interface | RestClientAdapter / RestTemplateAdapter | WebClientAdapter |
| --- | --- | --- |
| `T` | Có, synchronous | Có thể block qua adapter; cân nhắc tránh trong reactive code |
| `ResponseEntity<T>` | Có, synchronous | Có thể có synchronous form, nhưng vẫn block |
| `void` | Có | Có |
| `Mono<T>` | **Không dùng với sync adapter** | Có |
| `Flux<T>` | **Không dùng với sync adapter** | Có |
| `Mono<ResponseEntity<T>>` | Không | Có |
| `Flux<ServerSentEvent<T>>` | Không native reactive | Có nếu media type/codec hỗ trợ |

Khi API interface trả DTO đồng bộ nhưng dùng WebClientAdapter, proxy phải chờ để cung cấp một giá trị synchronous; điều đó không làm method trở thành non-blocking. Muốn reactive thật, khai báo reactive return type và compose publisher.

### 7.7. Ưu điểm và giới hạn của interface-first

**Ưu điểm:** code service gọn, một chỗ mô tả contract của nhiều endpoints, dễ thay implementation qua mock/stub interface, tái sử dụng API shape, giảm lặp boilerplate. **Giới hạn:** những requests rất động, streaming logic phức tạp, branching theo status, request signing/customization từng lần có thể dễ đọc hơn với direct RestClient/WebClient. Tính ổn định API interface đòi hỏi versioning và test khi upstream đổi.

**Không nhầm với OpenFeign:** Spring HTTP Service Client là tính năng framework riêng, không tự cung cấp các features của những hệ client declarative khác (service discovery, load balancing, circuit breaker, retry) nếu bạn chưa cấu hình.

## 8. Java 17 + Spring Boot 3.5: ví dụ chạy cả bốn lựa chọn

Mục tiêu một project có một **supplier HTTP endpoint giả lập** chạy ngay trong process, và bốn call paths:
- `/compare/rest-client/7` — gọi bằng RestClient đồng bộ;
- `/compare/rest-template/7` — gọi bằng RestTemplate đồng bộ;
- `/compare/http-interface/7` — gọi bằng HTTP Service Client trên RestClient;
- `/compare/web-client/7` — trả `Mono<Item>` từ WebClient.

Ứng dụng này dùng **Spring MVC server** để cho thấy WebClient vẫn có thể được dùng trong dự án MVC. Vì test demo supplier và caller cùng process dùng localhost:8080, không cần remote service thật; **đây không phải kiến trúc microservice production**. Cẩn thận: request sync gọi lại cùng server có thể góp phần cạn servlet thread pool dưới tải lớn; chỉ sử dụng pattern self-call này để học.

### 8.1. Dependency và cấu trúc

Tạo Maven Spring Boot **3.5.x**, Java 17+, các dependencies:
- **Spring Web**: MVC server, RestClient, RestTemplate;
- **Spring Reactive Web**: WebClient, Reactor.

Trong POM từ Spring Initializr có fragment:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
```

Đây **chỉ là dependency fragment**, không phải POM hoàn chỉnh; parent/BOM/plugins của Initializr quản lý các versions. Khi có **cả hai starters** trên Boot 3.5, mặc định web application type là **Servlet MVC**, không phải WebFlux server. `WebClient.Builder` vẫn có thể được auto-configure để gọi downstream reactive HTTP.

Cấu trúc:

```text
src/main/java/com/example/demo/DemoApplication.java
src/test/java/com/example/demo/RestClientExampleTest.java
```

### 8.2. Source đầy đủ (một file)

Lưu toàn bộ vào `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    // Mọi client gọi local supplier chỉ để minh họa.
    @Bean
    RestClient restClient(RestClient.Builder builder) {
        return builder.baseUrl("http://localhost:8080").build();
    }

    @Bean
    RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder.rootUri("http://localhost:8080").build();
    }

    @Bean
    WebClient webClient(WebClient.Builder builder) {
        return builder.baseUrl("http://localhost:8080").build();
    }

    @Bean
    SupplierApi supplierApi(RestClient restClient) {
        return HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(restClient))
                .build()
                .createClient(SupplierApi.class);
    }
}

record Item(long id, String name, int stock) {}

record ErrorView(String code, int upstreamStatus) {}

// Client-side declarative HTTP service interface.
@HttpExchange("/supplier/items")
interface SupplierApi {
    @GetExchange("/{id}")
    Item find(@PathVariable("id") long id);
}

// Server-side stub (chỉ phục vụ demo; không phải upstream thật).
@RestController
@RequestMapping("/supplier/items")
class SupplierController {

    @GetMapping("/{id}")
    ResponseEntity<Item> find(@PathVariable("id") long id) {
        if (id != 7L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(
                new Item(7L, "Spring Web", 12));
    }

    @GetMapping
    List<Item> list() {
        return List.of(new Item(7L, "Spring Web", 12));
    }
}

// Bốn client styles cùng gọi chung một supplier endpoint.
@RestController
@RequestMapping("/compare")
class ComparisonController {

    private final RestClient restClient;
    private final RestTemplate restTemplate;
    private final WebClient webClient;
    private final SupplierApi supplierApi;

    ComparisonController(
            RestClient restClient,
            RestTemplate restTemplate,
            WebClient webClient,
            SupplierApi supplierApi) {
        this.restClient = restClient;
        this.restTemplate = restTemplate;
        this.webClient = webClient;
        this.supplierApi = supplierApi;
    }

    @GetMapping("/rest-client/{id}")
    Item viaRestClient(@PathVariable("id") long id) {
        return restClient.get()
                .uri("/supplier/items/{id}", id)
                .retrieve()
                .body(Item.class);
    }

    @GetMapping("/rest-template/{id}")
    Item viaRestTemplate(@PathVariable("id") long id) {
        return restTemplate.getForObject(
                "/supplier/items/{id}", Item.class, id);
    }

    @GetMapping("/http-interface/{id}")
    Item viaHttpInterface(@PathVariable("id") long id) {
        return supplierApi.find(id);
    }

    @GetMapping("/web-client/{id}")
    Mono<Item> viaWebClient(@PathVariable("id") long id) {
        return webClient.get()
                .uri("/supplier/items/{id}", id)
                .retrieve()
                .bodyToMono(Item.class);
    }
}

// Giữ thông điệp lỗi an toàn thay vì lộ raw upstream body.
@RestControllerAdvice
class DemoClientErrors {

    @ExceptionHandler(RestClientResponseException.class)
    ResponseEntity<ErrorView> syncError(
            RestClientResponseException exception) {
        return ResponseEntity.status(exception.getStatusCode())
                .body(new ErrorView(
                        "UPSTREAM_HTTP_ERROR",
                        exception.getStatusCode().value()));
    }

    @ExceptionHandler(WebClientResponseException.class)
    ResponseEntity<ErrorView> reactiveError(
            WebClientResponseException exception) {
        return ResponseEntity.status(exception.getStatusCode())
                .body(new ErrorView(
                        "UPSTREAM_HTTP_ERROR",
                        exception.getStatusCode().value()));
    }
}
```

### 8.3. Vì sao code hợp lệ trên Boot 3.5?

- Java 17 cho phép `record`; một file có một public top-level class `DemoApplication`, các classes/interfaces/records còn lại package-private.
- `@SpringBootApplication` component-scan thấy `SupplierController`, `ComparisonController`, `DemoClientErrors` cùng package; các beans trong main class được phát hiện.
- `RestClient.Builder`, `RestTemplateBuilder`, `WebClient.Builder` được Boot cung cấp khi starters liên quan có mặt; beans built một lần và được dùng lại, không tạo HTTP client cho từng request.
- `SupplierApi` là HTTP Service Client proxy do `RestClientAdapter` xử lý; nó synchronous đúng chữ ký `Item find(long)`.
- `viaWebClient` return Mono, nên controller MVC dùng async support; **server vẫn Servlet MVC**. Không cần `.block()` để lấy Item trong controller.
- `DemoClientErrors` minh họa mapping errors từ hai client families sang status và sanitized error body. Trên API production, cần policy riêng cho rate limits, 502/503 upstream failures, permissions và return-timeout; không đơn giản forward mọi upstream status.
- Local supplier và caller cùng dùng port 8080; khi đổi `server.port`, cần đổi cả `baseUrl`/`rootUri` ở ba beans tương ứng. Đây là demo hardcoded local URLs, không phải config deployment.
- Không có network timeout, circuit breaker, retries, auth, observability hoặc connection limits do ví dụ nhắm vào **lựa chọn API**. Cần thêm trước production.

### 8.4. Chạy

Ở thư mục có Maven wrapper do Spring Initializr tạo:

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell / CMD
mvnw.cmd spring-boot:run
```

Giữ port 8080 như code và không có dịch vụ khác dùng port đó.

### 8.5. So sánh kết quả HTTP

Gọi bốn phương án:

```bash
curl -i 'http://localhost:8080/compare/rest-client/7'
curl -i 'http://localhost:8080/compare/rest-template/7'
curl -i 'http://localhost:8080/compare/http-interface/7'
curl -i 'http://localhost:8080/compare/web-client/7'
```

Mỗi request thành công trả status 200 và một JSON object có giá trị:

```json
{"id":7,"name":"Spring Web","stock":12}
```

Sự khác biệt là **call mechanics**, không phải khác dữ liệu hay HTTP business contract:
- RestClient: blocking thread thực thi MVC handler trong lúc chờ local supplier.
- RestTemplate: cũng blocking, nhưng API template method.
- HTTP interface: method invocation trông như Java interface, bên dưới vẫn RestClient synchronous.
- WebClient: method trả Mono, không block trong controller code; Spring MVC dùng Servlet async support khi đợi Mono hoàn tất. HTTP I/O phía client là reactive.

### 8.6. Trường hợp không tìm thấy

```bash
curl -i 'http://localhost:8080/compare/rest-client/99'
curl -i 'http://localhost:8080/compare/rest-template/99'
curl -i 'http://localhost:8080/compare/http-interface/99'
curl -i 'http://localhost:8080/compare/web-client/99'
```

Supplier trả 404. Các clients mặc định biến 4xx thành exception/reactive error; advice minh họa mapping thành response 404 JSON:

```json
{"code":"UPSTREAM_HTTP_ERROR","upstreamStatus":404}
```

Đây là **deliberate demo policy**, không mặc nhiên sao chép cách “forward nguyên upstream 404/500 cho browser” trong production. Có lúc frontend resource không tìm thấy thì 404 là hợp lý; có lúc một third-party upstream 404 nghĩa là integration misconfiguration và nên được nội bộ xử lý thành 502. API gateway cần policy được thiết kế theo domain.

### 8.7. Powershell

```powershell
curl.exe -i "http://localhost:8080/compare/rest-client/7"
curl.exe -i "http://localhost:8080/compare/rest-template/7"
curl.exe -i "http://localhost:8080/compare/http-interface/7"
curl.exe -i "http://localhost:8080/compare/web-client/7"
```

Chạy `curl.exe` để tránh alias `curl` của một số phiên bản PowerShell. Nếu JSON pretty-printed, không so whitespace hay thứ tự object fields như dữ liệu nghiệp vụ.

## 9. Test RestClient và HTTP interface không cần remote server

Spring Test có `MockRestServiceServer` hỗ trợ bind vào `RestClient.Builder` và intercept mock HTTP requests. Thích hợp để verify URL, HTTP method, JSON conversion, default exception mapping mà không phụ thuộc service ngoài.

Thêm test dependency với Spring Boot 3.5:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

### 9.1. Test file đầy đủ

Tạo `src/test/java/com/example/demo/RestClientExampleTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class RestClientExampleTest {

    @Test
    void restClientDecodesJson() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();

        server.expect(requestTo(
                        "https://catalog.example.test/supplier/items/7"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Spring Web\",\"stock\":12}",
                        MediaType.APPLICATION_JSON));

        Item item = client.get()
                .uri("/supplier/items/{id}", 7)
                .retrieve()
                .body(Item.class);

        assertNotNull(item);
        assertEquals(7L, item.id());
        assertEquals("Spring Web", item.name());
        assertEquals(12, item.stock());
        server.verify();
    }

    @Test
    void annotatedProxyUsesUnderlyingRestClient() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();
        SupplierApi api = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(client))
                .build()
                .createClient(SupplierApi.class);

        server.expect(requestTo(
                        "https://catalog.example.test/supplier/items/7"))
                .andRespond(withSuccess(
                        "{\"id\":7,\"name\":\"Spring Web\",\"stock\":12}",
                        MediaType.APPLICATION_JSON));

        Item item = api.find(7L);
        assertEquals(7L, item.id());
        server.verify();
    }

    @Test
    void status404IsRaisedByRetrieve() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder.build();

        server.expect(requestTo(
                        "https://catalog.example.test/supplier/items/99"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        RestClientResponseException exception = assertThrows(
                RestClientResponseException.class,
                () -> client.get()
                        .uri("/supplier/items/{id}", 99)
                        .retrieve()
                        .body(Item.class));

        assertEquals(404, exception.getStatusCode().value());
        server.verify();
    }
}
```

Các tests này dùng `Item` và `SupplierApi` package-private từ file main cùng package. Để chạy, Spring Initializr cần Maven/Java17 và `spring-boot-starter-test`. Test `RestClient.Builder` được bind tới mock server trước khi gọi `build()`; không cần mở socket thật.

### 9.2. Mocking RestTemplate

Với RestTemplate, Spring Test hỗ trợ:

```java
RestTemplate template = new RestTemplate();
MockRestServiceServer server = MockRestServiceServer.createServer(template);

server.expect(requestTo("https://catalog.example.test/items/7"))
        .andRespond(withSuccess(
                "{\"id\":7,\"name\":\"Spring Web\",\"stock\":12}",
                MediaType.APPLICATION_JSON));

Item item = template.getForObject(
        "https://catalog.example.test/items/{id}",
        Item.class,
        7);

server.verify();
```

Đây là fragment trong test method, cần imports. Không cần dùng WebClient chỉ để mock một RestTemplate call.

### 9.3. Testing WebClient

Có thể dùng local HTTP mock server (ví dụ OkHttp MockWebServer hoặc WireMock), hoặc `WebTestClient` để test WebFlux handler/server, hoặc cấp `ExchangeFunction` test double khi muốn test client only. **`MockRestServiceServer` không phải công cụ dùng nguyên xi cho WebClient**, vì WebClient dựa trên reactive connector/ExchangeFunction. Khi test WebClient, cần kiểm tra:
- request URI/method/headers và JSON body;
- 2xx decoding thành Mono/Flux;
- 404/429/500 thành error signal theo policy;
- timeout/retry/cancellation;
- streaming/backpressure và response body release khi dùng `exchangeToMono`;
- trace/auth/tenant header propagation (không log token).

### 9.4. HTTP service interface unit test

Với interface-first, tầng business gọi `SupplierApi` có thể mock interface trực tiếp (Mockito) mà không cần mở HTTP. Tuy nhiên riêng tests proxy/adapter vẫn cần mock HTTP để đảm bảo annotations `@HttpExchange`/`@GetExchange`/`@PathVariable` tạo đúng path, headers và body.

## 10. Timeout và connection pool: điều quan trọng hơn cú pháp

### 10.1. Một request phải có deadlines

Cần phân biệt:
- DNS lookup timeout;
- connect timeout (mở TCP connection);
- TLS handshake timeout;
- pending connection acquisition/pool wait timeout;
- response/read timeout;
- write timeout;
- toàn request deadline;
- thời gian retry/backoff nằm trong overall SLA.

Không có một option chung như `timeout=2s` bao tất cả các giới hạn ở mọi HTTP transport. `RestClient`/`RestTemplate` dùng `ClientHttpRequestFactory`; `WebClient` dùng `ClientHttpConnector`. Timeout/connection pool có thể nằm trên Apache HttpComponents, JDK HttpClient, Reactor Netty hoặc transport khác được chọn.

### 10.2. Timeout trên RestClient dùng request factory

Ví dụ nguyên tắc:

```java
// Snippet: cấu hình ở HTTP request factory bạn thực sự sử dụng.
ClientHttpRequestFactory factory = configuredFactory;

RestClient client = RestClient.builder()
        .requestFactory(factory)
        .baseUrl("https://catalog.example.test")
        .build();
```

`configuredFactory` phải được tạo/cấu hình connect/read/pool timeout theo concrete class. Đây không phải mã chạy độc lập; **không** mặc định chỉ xây RestClient.Builder là đã có production-safe timeouts. Trong Spring Boot, hãy xem request factory selection và RestClient customization/builder beans trước khi tự tạo một HttpClient mới bỏ qua cấu hình của Boot.

### 10.3. WebClient/Reactor Netty example

```java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("https://catalog.example.test")
        .build();
```

Đây là snippet cho connector Reactor Netty, cần imports:
- `reactor.netty.http.client.HttpClient`;
- `io.netty.channel.ChannelOption`;
- `org.springframework.http.client.reactive.ReactorClientHttpConnector`;
- `java.time.Duration`.

`responseTimeout` không tự là overall end-to-end deadline và chưa cấu hình pending acquire timeout/pool max size. Nếu tổ chức dùng proxy/TLS connection reuse, cần thêm TLS/HTTP2/proxy/pool settings và test slow responses.

### 10.4. Giới hạn kết nối và tổng concurrency

Giả sử 60 inbound requests, mỗi request fan-out 10 HTTP calls:
- Có thể tạo **600 in-flight operations** dù một `flatMap(mapper, 10)` trông nhỏ.
- Downstream pool max connections, max pending acquire và rate limit phải đủ hoặc có bulkhead.
- Với RestClient/RestTemplate, mỗi caller thường chiếm một thread chờ response; thread pool saturation có thể làm tail latency tăng.
- Với WebClient, bớt giữ thread chờ I/O nhưng **không xóa** bottleneck ở remote services hoặc sự cần thiết của backpressure/limits.

### 10.5. Singleton/shared client beans

Nên cấu hình clients một lần thành beans hoặc reuse builders đã cấu hình. Đừng tạo RestClient/WebClient mới cho mỗi HTTP request; chi phí pool/TLS/config và resource lifecycle sẽ bị lãng phí. Builders có tính mutable ở giai đoạn configuration; clients được built được chia sẻ trong ứng dụng theo thiết kế. Với RestTemplate, cấu hình trước khi share và không sửa đồng thời runtime.

## 11. Error handling: HTTP status, transport và parsing phải tách riêng

| Tình huống | RestClient/RestTemplate | WebClient |
| --- | --- | --- |
| 404/4xx từ server | Default status handling ném RestClientResponseException subtype | `retrieve()` chuyển thành WebClientResponseException error signal |
| 500/5xx từ server | Exception chứa status/body/header khi có | Error signal với status/header/body khi có |
| DNS/connect timeout | I/O exception bọc trong RestClientException family | `WebClientRequestException` hoặc cause/timeout signal |
| JSON sai schema/decoder | Message conversion/RestClientException family | Reactive codec/decoding error |
| Response 204 | DTO body có thể null | `Mono<T>` thường complete empty |
| Consumer cancel | Blocking caller có cơ chế interruption/transport-specific | Publisher cancellation có thể truyền tới connector |
| Retry | Phải thực thi explicit policy ở service/client resilience layer | `retryWhen` + filter/backoff với reactive pipeline |

Các kiểu exception thực tế có thể khác theo phương thức `retrieve/exchange`, status handler custom, codec, transport và Spring version. Đừng `catch(Exception.class) -> HTTP 200`.

### 11.1. Không map mọi upstream 404/500 theo một cách

Nếu client GET đúng resource mà upstream 404, API của bạn có thể trả 404. Nhưng nếu downstream là **identity provider** hoặc payment gateway, upstream 404 có thể nghĩa là route misconfiguration, không phải khách hàng không tồn tại. Bản đồ status phải có ý nghĩa nghiệp vụ.

### 11.2. Retry không tự động miễn phí

Chỉ retry lỗi tạm thời có thể phục hồi: connection reset/timeout trong điều kiện idempotent, 502/503/504/429 nếu API contract và Retry-After cho phép. **Không** retry bừa POST tạo thanh toán, 400 validation, 401/403 hay operations đã commit side effects mà không có idempotency key.

Với WebClient:

```java
Mono<Item> item = client.get()
        .uri("/items/{id}", id)
        .retrieve()
        .bodyToMono(Item.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(150))
                .filter(ex -> isTransient(ex)));
```

Đây là snippet; `isTransient` phải được định nghĩa và cần import `reactor.util.retry.Retry`. Có 2 retry bổ sung sau lần đầu khi phù hợp filter. Đặt overall deadline và backoff/jitter để tránh retry storm.

Với synchronous callers, dùng resilience wrapper như Spring Retry/Resilience4j theo nhu cầu (phải bổ sung dependencies/config), không viết while(true) retry thiếu giới hạn.

### 11.3. Tránh log lộ secrets

Không log:
- `Authorization: Bearer ...`, cookies/session tokens;
- query strings chứa PII hoặc signed URLs;
- toàn raw HTTP response lỗi có dữ liệu khách hàng;
- credentials trong URI hoặc proxy settings.

Nên log upstream service logical name, safe status class, latency, requestId/traceId và mã lỗi nội bộ, với retention/sampling hợp lý.

## 12. Header, URI, auth và request signing

### 12.1. URI variables và encoding

Thay vì tự ghép URL với input của người dùng:

```java
String unsafe = baseUrl + "/items/" + userInput;
```

Dùng URI templates:

```java
client.get()
        .uri("/items/{id}", itemId)
        .retrieve()
        .body(Item.class);
```

URI template expansion giảm lỗi encoding và path injection; vẫn cần kiểm tra `itemId` thuộc business contract. Nếu client cho phép dynamic absolute URL từ user, có nguy cơ **SSRF** dù URI được encode: phải allowlist hosts/protocol/ports, deny private/internal targets theo policy và kiểm soát redirect/DNS rebinding.

### 12.2. Auth propagation

RestClient:
```java
client.get()
        .uri("/items/{id}", id)
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .body(Item.class);
```

WebClient:
```java
client.get()
        .uri("/items/{id}", id)
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(Item.class);
```

Đây là snippets: `accessToken` phải được cấp hợp lệ theo OAuth2/service credentials flow, không copy token người dùng sang mọi downstream. Nếu dùng Spring Security OAuth2 client, cân nhắc dedicated interceptors/filters/AuthorizedClientManager. Tránh gửi token qua hosts không thuộc trust boundary; redirect phải được xử lý theo chính sách.

### 12.3. Content-Type và Accept

- `Content-Type` của request nói body đang gửi là JSON, form, binary…
- `Accept` nói client muốn response media type gì.
- RestClient/RestTemplate sử dụng `HttpMessageConverter`; WebClient dùng reactive codec writers/readers.
- Nếu server trả Content-Type không hỗ trợ, client có thể phát decoding error; không phải do HTTP status 500 trên server.

## 13. Observability, tracing, cancellation và testing

### 13.1. Metrics

Với Spring Boot Actuator/Micrometer nếu đã cấu hình, có thể instrument HTTP client calls để thấy:
- outgoing request count/status;
- latency average/p95/p99;
- timeout, connection pool wait, DNS/TLS errors;
- retry rate và downstream 429/503;
- active requests/connection counts;
- slow consumer/stream cancellation (WebClient).

Không đặt raw URL path có IDs riêng lẻ, requestId hay email address làm metrics tags high-cardinality; ưu tiên URI templates và logical service names.

### 13.2. Cân nhắc testing theo client

| Client | Kiểm thử có giá trị |
| --- | --- |
| RestClient | `MockRestServiceServer.bindTo(RestClient.Builder)`, kiểm tra URI/method/body/status |
| RestTemplate | `MockRestServiceServer.createServer(template)`, verify request/response |
| WebClient | HTTP mock server/ExchangeFunction stub, Reactor `StepVerifier` cho Mono/Flux |
| HTTP Service Client | Mockito mock interface cho business test + HTTP mock cho proxy/annotations |
| Tất cả | Integration test thật với TLS/proxy/pool/timeouts, 4xx/5xx, payload lớn |

Test không chỉ assert DTO 200: cần malformed JSON, bad status, 204 empty, timeouts, cancellation, header/auth security, retry/no retry và wrong Content-Type.

### 13.3. HTTP client không quyết định transaction

Một call POST sang remote service có thể commit thành công dù local client timeout trước khi nhận response. Retry không thể biết chắc status cuối nếu API thiếu idempotency key/reconciliation. `RestClient`, `WebClient`, hay interface proxy đều **không tự tạo distributed transaction**. Khi có nhiều downstream writes, phải cân nhắc saga/outbox/compensation và business-level idempotency.

### 13.4. Test thực và mock không giống nhau

`MockRestServiceServer` mock HTTP boundary nên nhanh, deterministic, không chứng minh DNS/TLS/client connection pool hoạt động thật. Với các lỗi proxy certificates, keepalive và slow downstream, cần test qua embedded/local upstream server hoặc staging. Việc một MockRestServiceServer test pass không tự chứng minh client production có proper timeouts.

## 14. Anti-pattern phổ biến

| Anti-pattern / triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Dùng WebClient + `block()` cho mọi call đồng bộ mới | Reactive overhead không mang lợi ích | RestClient |
| Dùng RestTemplate trong WebFlux handler event-loop | Blocking I/O | WebClient hoặc bridge boundedElastic có quota |
| Dùng RestClient rồi kỳ vọng Mono/Flux reactive | Client sync | WebClient |
| Dùng `Mono.just(restClient.get()...)` | Call đồng bộ đã chạy trước Mono | Chọn WebClient hoặc controlled bridge |
| HTTP interface trả Mono với RestClientAdapter | Adapter sync không hỗ trợ signature reactive | WebClientAdapter |
| Tưởng HTTP interface là protocol mới | Interface chỉ là proxy | Cấu hình underlying client |
| `retrieve()` mà không terminal operation ở RestClient | Chưa gửi request | Thêm `body/toEntity/toBodilessEntity` |
| `WebClient.retrieve()` mà không subscribe | Publisher lazy | Return Mono/Flux cho framework subscribe |
| Tạo WebClient mới mỗi request | Pool/resources/config thừa | Reuse configured bean |
| RestTemplate.config mutate trong concurrent requests | Không thread-safe khi sửa runtime | Cấu hình startup một lần |
| `exchange` rồi quên kiểm tra status | Bỏ default status mapping | Handle 4xx/5xx chủ động |
| `body(List.class)` khiến item thành Map | Generic type erasure | ParameterizedTypeReference |
| 204 body được dùng như non-null | Response rỗng | Optional/empty semantics rõ |
| Trả raw upstream exception body cho client | Lộ implementation/PII | Domain-safe error DTO |
| WebClient flatMap concurrency quá lớn | Downstream/pool saturation | Per request và global limits |
| Dùng `collectList()` trên stream vô hạn | Memory/never complete | SSE/NDJSON streaming, termination |
| Retry POST không idempotent | Duplicated side effects | Idempotency key/reconciliation |
| Chưa cấu hình timeout | Thread/connection treo lâu | Factory/connector timeouts + deadline |
| Kết quả 200 nhưng response invalid JSON | Codec/Content-Type mismatched | Test media types và conversion |
| Cho client nhập absolute URL bất kỳ | SSRF | URL allowlist/network egress controls |
| Gửi bearer token cho host redirect lạ | Credential leak | Redirect/auth policies |
| Chỉ mock test mà không load test | Không đo pool/DNS/TLS/resource pressure | Integration/load tests |
| Dùng Spring7 API trong Boot3.5 | Version/API mismatch | Khóa đúng framework version khi copy code |

## 15. Checklist chọn client và triển khai

1. [ ] Module của mình dùng synchronous thread-per-request, MVC hay WebFlux reactive event-loop?
2. [ ] Với sync mới: ưu tiên RestClient; legacy RestTemplate vẫn dùng được trong Spring 6.2 nhưng có migration plan.
3. [ ] Nếu chọn WebClient, caller có thể **compose Publisher** mà không chèn `block()` vào event-loop?
4. [ ] Nếu chọn HTTP interface, adapter backend và method return types có khớp (sync vs reactive)?
5. [ ] Base URL thuộc trusted configuration; dynamic targets được validate chống SSRF?
6. [ ] URI templates/encoding, Content-Type/Accept và DTO generic đúng?
7. [ ] Connection/read/response/pool wait timeouts và overall deadline có giới hạn?
8. [ ] Retry filter/backoff/jitter/idempotency/Retry-After đúng nghiệp vụ?
9. [ ] Pool size, max pending acquire, per-request concurrency và global rate limits được đo?
10. [ ] Status 404/401/403/429/5xx được map theo domain contract, không leak upstream body?
11. [ ] Có auth propagation/OAuth2 policy và redaction tokens/cookies?
12. [ ] Client beans được tái sử dụng; không mutate shared config lúc runtime?
13. [ ] HTTP Service Client interface không biến thành danh sách overload phức tạp hơn direct client?
14. [ ] 204/empty response và codecs xử lý được?
15. [ ] Với streaming, có cancellation, backpressure và resource release?
16. [ ] Tests cover URI, method, JSON, errors, timeout, auth, retry và proxy integration?
17. [ ] Giải pháp đã được benchmark theo workload thực, không suy từ tên thư viện?

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Trong code Spring MVC đồng bộ mới, nên chọn RestClient hay WebClient cho một GET JSON đơn giản?

**Đáp án:** Thường RestClient vì synchronous contract rõ và API fluent. WebClient có ý nghĩa khi cần non-blocking composition/streaming.

**Câu 2.** HTTP Service Client là HTTP transport thứ tư?

**Đáp án:** Không. Nó là Java interface + proxy trên RestClient, RestTemplate hoặc WebClient qua adapter.

**Câu 3.** `RestClient.get().retrieve()` đã gửi request chưa?

**Đáp án:** Theo Spring RestClient API, `retrieve()` chỉ trả ResponseSpec; terminal `body/toEntity/toBodilessEntity` mới thực thi exchange.

**Câu 4.** WebClient trả Mono có nghĩa request được gửi ngay khi tạo Mono?

**Đáp án:** Không, Publisher thường lazy; phải có subscription, framework có thể subscribe khi controller return Mono.

**Câu 5.** Khi HTTP interface method trả `Mono<Item>` nên chọn adapter nào?

**Đáp án:** `WebClientAdapter`; sync adapters không cung cấp reactive return contract.

**Câu 6.** `RestTemplate` ngừng hoạt động trên Spring Framework 6.2?

**Đáp án:** Không. Nó còn hoạt động; từ Spring 7 API được đánh dấu deprecated theo hướng chuyển sang RestClient.

**Câu 7.** `WebClient.bodyToMono(...).block()` trong WebFlux event-loop có an toàn?

**Đáp án:** Không; tránh blocking terminal methods trong WebFlux event-loop. Compose non-blocking Mono/Flux.

**Câu 8.** Vì sao cần timeout ngay cả khi dùng WebClient?

**Đáp án:** Non-blocking vẫn có connection/pool/server resources, có thể in-flight lâu vô hạn nếu không có deadlines; high concurrency không sửa được slow downstream.

**Câu 9.** Khi POST timeout nhưng upstream đã commit, retry mù có rủi ro gì?

**Đáp án:** Có thể tạo giao dịch/tài nguyên trùng; cần idempotency key và reconciliation.

**Câu 10.** MockRestServiceServer test pass có nghĩa TLS/proxy/pooling production đã được xác minh?

**Đáp án:** Không. Nó mock HTTP boundary; cần integration/load tests riêng.

## 17. Tài liệu chính thức

- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): lựa chọn RestClient, RestTemplate, WebClient và HTTP interfaces, method signatures, status/headers.
- [Spring Framework — REST Clients (current)](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): cập nhật migration và tình trạng RestTemplate ở Spring 7.
- [Spring Framework 6.2 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestClient.html): retrieve, exchange, requestFactory, default status handlers.
- [Spring Framework 6.2 — RestTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/client/RestTemplate.html): synchronous template methods và request factory.
- [Spring Framework 6.2 — WebClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/WebClient.html): reactive HTTP API.
- [Spring Framework 6.2 — WebClient Synchronous Use](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-synchronous.html): hợp đồng block ở ranh giới sync và compose nhiều calls.
- [Spring Framework 6.2 — HttpServiceProxyFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html): `builderFor(adapter)` và `createClient`.
- [Spring Framework 6.2 — HTTP Interface Client](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-http-interface-client.html): @HttpExchange/@GetExchange, adapters và return values.
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): RestClient.Builder, RestTemplateBuilder, WebClient.Builder auto-configuration.
- [Spring Framework — WebClient retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): status/error handling.
- [Spring Framework — WebClient Exchange](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): exchangeToMono/Flux và response release rules.
- [Spring Boot 3.5 — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): Spring Test/client testing practices.

**Kết luận:** Với module “HTTP client đồng bộ”, **RestClient** là lựa chọn mặc định hợp lý cho code Spring mới. **RestTemplate** tiếp tục hỗ trợ code hiện hữu và có thể chuyển dần, đặc biệt khi nâng Spring 7. **WebClient** phù hợp khi có non-blocking composition, fan-out hay stream và tránh blocking event loop. **HTTP Service Client** không phải một transport khác: nó đặt một interface annotation lên RestClient/WebClient (hoặc RestTemplate), nên lựa chọn **đồng bộ hay reactive vẫn nằm ở adapter và kiểu return**. Bất kể chọn API nào, chất lượng production phụ thuộc timeouts, pooling, errors, auth, retries, backpressure, observability và integration tests.
