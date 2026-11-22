# Thời điểm framework đăng ký đọc body và ghi phản hồi trong Spring WebFlux

## 1. Câu hỏi cốt lõi: khi nào dữ liệu thực sự được đọc và ghi?

Trong Spring WebFlux, controller thường trả về `Mono<T>` hoặc `Flux<T>`. Những kiểu này mô tả một quá trình sẽ phát dữ liệu sau khi có người đăng ký. Việc gọi một method controller và việc framework thực sự đọc request body hoặc ghi response body vì thế có thể xảy ra ở **những thời điểm khác nhau**.

Cần tách hai câu hỏi:

- **Đọc request body:** khi nào Spring bắt đầu subscribe vào Publisher đại diện cho body và dùng codec giải mã byte thành object?
- **Ghi response body:** khi nào Spring subscribe vào Publisher do controller trả về, chọn writer, encode object thành byte và gửi byte xuống HTTP server?

Điểm quan trọng nhất: trong một request WebFlux thông thường, **framework quản lý subscription của pipeline HTTP**. Ứng dụng tạo và kết hợp Publisher rồi trả nó về; không tự gọi `subscribe()` hoặc `block()` trong controller để kích hoạt việc đọc/ghi.

~~~text
HTTP server nhận request
        |
        v
WebFlux route tới handler/controller
        |
        +--> resolve tham số method
        |       |
        |       +--> @RequestBody Object
        |       |       -> đọc/giải mã body trước khi gọi method
        |       |
        |       +--> @RequestBody Mono<T>/Flux<T>
        |               -> cung cấp Publisher cho method
        |                  body được tiêu thụ khi Publisher được subscribe
        |
        v
Gọi controller/HandlerFunction
        |
        v
Nhận return value (Object, Mono, Flux, ResponseEntity, ...)
        |
        v
HandlerResultHandler / response writer
        |
        +--> chọn HttpMessageWriter theo kiểu dữ liệu + media type
        |
        v
Framework subscribe vào response-writing Publisher
        |
        v
Encode -> ghi byte -> commit response -> complete/error/cancel
~~~

Sơ đồ là cách nhìn theo lifecycle. Việc server nhận byte từ socket có thể diễn ra trước lúc codec tiêu thụ chúng; “đọc body” trong bài này nói về **quá trình framework subscribe và giải mã request body**, không khẳng định NIC/server chỉ nhận byte đúng tại thời điểm đó.

## 2. Assembly và subscription: tạo Publisher chưa có nghĩa là chạy

### 2.1. Assembly time

Assembly là lúc Java chạy các câu lệnh tạo Publisher và ghép toán tử:

~~~java
Mono<String> result = Mono.fromSupplier(() -> {
    System.out.println("supplier executed");
    return "hello";
}).map(String::toUpperCase);

System.out.println("publisher assembled");
~~~

Stdout:

~~~text
publisher assembled
~~~

Supplier chưa chạy vì chưa có subscriber. Tương tự, gọi `request.bodyToMono(Order.class)` tạo một Publisher đại diện cho việc đọc/giải mã body; việc tạo object Publisher không đồng nghĩa body đã được tiêu thụ hoàn toàn.

### 2.2. Subscription time

Khi có subscriber, pipeline mới bắt đầu thực thi theo demand:

~~~java
result.subscribe(System.out::println);
~~~

Stdout tiếp theo:

~~~text
supplier executed
HELLO
~~~

Trong HTTP server, Spring thực hiện việc subscribe vào pipeline xử lý request/response. Khi subscriber yêu cầu dữ liệu, nguồn và các toán tử upstream bắt đầu hoạt động theo hợp đồng Reactive Streams.

### 2.3. Vì sao controller không cần tự subscribe?

Với controller:

~~~java
@GetMapping("/message")
public Mono<String> message() {
    return Mono.fromSupplier(() -> "hello");
}
~~~

Spring nhận `Mono<String>`, chọn cách ghi response phù hợp và quản lý subscription để gửi nội dung. Nếu controller tự viết:

~~~java
@GetMapping("/wrong")
public Mono<String> wrong() {
    Mono<String> source = service.load();
    source.subscribe(); // Không nên làm trong handler
    return Mono.just("accepted");
}
~~~

thì subscription do ứng dụng tự tạo chạy độc lập với response. HTTP có thể trả về trước khi `service.load()` hoàn tất; lỗi và cancellation không còn gắn đúng với vòng đời request. Hãy trả hoặc ghép Publisher:

~~~java
@GetMapping("/correct")
public Mono<String> correct() {
    return service.load().map(value -> "loaded=" + value);
}
~~~

Không gọi `block()` để lấy dữ liệu đồng bộ trong event-loop. Nó chặn thread xử lý I/O và phá lợi ích non-blocking của WebFlux.

## 3. Khi nào Spring đọc request body?

Spring WebFlux dùng `HttpMessageReader<T>` để giải mã HTTP body thành Java object hoặc reactive publisher. `ServerCodecConfigurer` cung cấp các reader mặc định và cho phép cấu hình codec. Reader được lựa chọn dựa trên kiểu dữ liệu cần đọc, `Content-Type` và khả năng hỗ trợ của codec.

### 3.1. `@RequestBody Object`: resolve body trước khi gọi controller

Ví dụ:

~~~java
@PostMapping("/orders")
public Mono<String> create(@RequestBody CreateOrder request) {
    System.out.println("controller invoked");
    return orderService.create(request).thenReturn("created");
}
~~~

Với tham số `CreateOrder` thông thường, Spring phải đọc và giải mã body thành một object trước khi có thể gọi method controller. Trình tự khái niệm:

1. Route tìm đúng handler method.
2. Argument resolver yêu cầu `HttpMessageReader` đọc body và tạo `CreateOrder`.
3. Khi object đã được resolve thành công, Spring mới gọi `create(request)`.
4. Method trả về `Mono<String>`.
5. Framework subscribe vào Publisher kết quả để ghi response.

Nếu JSON không hợp lệ, body thiếu trong trường hợp bắt buộc, hoặc chuyển đổi thất bại, lỗi có thể xuất hiện **trước khi dòng log trong controller chạy**. Đây là khác biệt quan trọng so với việc nhận `Mono<CreateOrder>`.

“Đọc trước khi gọi method” không có nghĩa Spring phải block một thread cho đến khi toàn bộ mạng truyền xong. Việc resolve tham số vẫn được điều phối theo reactive pipeline; method chỉ được gọi khi giá trị tham số non-reactive đã sẵn sàng.

### 3.2. `@RequestBody Mono<T>`: method nhận Publisher trước, body được đọc khi có subscribe

Ví dụ:

~~~java
@PostMapping("/orders")
public Mono<String> create(@RequestBody Mono<CreateOrder> requestMono) {
    System.out.println("controller invoked");
    return requestMono
        .doOnNext(order -> System.out.println("decoded=" + order.name()))
        .flatMap(orderService::create)
        .thenReturn("created");
}
~~~

Ở đây method nhận một `Mono<CreateOrder>`. Spring có thể gọi method với Publisher đó mà chưa cần chờ object `CreateOrder` được giải mã. Body thực sự được tiêu thụ khi chuỗi trả về được subscribe và subscription đi tới `requestMono`.

~~~text
Spring resolve argument -> tạo requestMono
             |
             v
Gọi controller method
             |
             v
Controller trả requestMono.flatMap(...).thenReturn(...)
             |
             v
Framework subscribe vào response Publisher
             |
             v
Subscription đi vào requestMono
             |
             v
HttpMessageReader đọc byte và decode CreateOrder
             |
             v
flatMap -> service -> response
~~~

Điều này cho phép controller kết hợp việc đọc body với thao tác reactive tiếp theo mà không tự quản lý subscription.

Nếu controller nhận `Mono<T>` nhưng không đưa nó vào chuỗi trả về, không tự subscribe và không chuyển nó cho một thành phần reactive khác, body Publisher có thể không được tiêu thụ bởi logic đó. Vì thế hãy kiểm tra rằng request body thực sự được compose vào pipeline mà framework quản lý.

### 3.3. `@RequestBody Flux<T>`: đọc nhiều phần tử theo demand

Với body có thể biểu diễn thành nhiều phần tử:

~~~java
@PostMapping("/events")
public Mono<Long> receive(@RequestBody Flux<Event> events) {
    return events
        .doOnNext(event -> System.out.println("event=" + event.id()))
        .count();
}
~~~

`Flux<Event>` cho phép xử lý từng phần tử khi decoder tạo ra chúng. Khi subscriber downstream yêu cầu dữ liệu, demand có thể lan ngược qua các toán tử tới reader và nguồn request. Ứng dụng không nhất thiết phải gom toàn bộ body thành một `List<Event>` trước khi xử lý.

Tuy nhiên, `Flux<T>` không tự bảo đảm mọi định dạng đều streaming theo cùng một cách. Khả năng decode phụ thuộc codec và media type. Ví dụ Jackson decoder có thể tách nội dung JSON thành các object khi nhận đủ byte cho từng object; NDJSON/JSON Lines cũng phù hợp cho luồng object phân tách theo dòng.

### 3.4. So sánh ba kiểu tham số

| Tham số controller | Khi method được gọi | Khi body được tiêu thụ | Phù hợp |
| --- | --- | --- | --- |
| `@RequestBody Order` | Sau khi argument được đọc/giải mã thành Order | Trước khi method được gọi | Một object nhỏ, logic đơn giản |
| `@RequestBody Mono<Order>` | Method nhận Publisher | Khi Publisher được subscribe trong pipeline | Một object bất đồng bộ, compose với service |
| `@RequestBody Flux<Event>` | Method nhận Publisher | Khi downstream subscribe và yêu cầu phần tử | Stream nhiều event, xử lý theo từng phần |

Chọn kiểu tham số theo hợp đồng dữ liệu và cách xử lý. Không dùng `Flux` chỉ để trông “reactive” nếu nghiệp vụ thực tế cần một object nhỏ duy nhất.

## 4. `HttpMessageReader` và codec quyết định cách giải mã

### 4.1. Chuỗi chuyển đổi

~~~text
Byte từ HTTP request
        |
        v
DataBuffer
        |
        v
Decoder (ví dụ JacksonJsonDecoder)
        |
        v
HttpMessageReader<T>
        |
        v
T hoặc Publisher<T> (Mono/Flux)
        |
        v
Controller / handler
~~~

`Decoder` là hợp đồng thấp hơn để giải mã byte thành object. `HttpMessageReader` kết nối decoder với ngữ nghĩa HTTP, bao gồm media type và request body. `DataBuffer` là abstraction cho dữ liệu byte; trên một số server như Netty, buffer có thể được pool và reference-counted.

Trong ứng dụng thông thường, hãy dùng `@RequestBody`, `ServerRequest.bodyToMono`, `ServerRequest.bodyToFlux` hoặc `ServerWebExchange` API thay vì tự thao tác `DataBuffer`. Nếu tự đọc/giữ buffer, phải giải phóng đúng vòng đời để tránh memory leak.

### 4.2. `Content-Type` và kiểu Java phải tương thích

Ví dụ:

- `Content-Type: application/json` với `@RequestBody CreateOrder`: reader JSON giải mã một object.
- `Content-Type: application/json` với `@RequestBody Flux<CreateOrder>`: decoder có thể tách các object trong cấu trúc JSON được hỗ trợ.
- `Content-Type: application/x-ndjson` với `Flux<CreateOrder>`: mỗi dòng JSON là một phần tử trong stream.
- `Content-Type: application/x-www-form-urlencoded`: dùng reader form data.
- `Content-Type: multipart/form-data`: dùng reader multipart phù hợp.

Nếu không có reader nào hỗ trợ cặp kiểu dữ liệu/media type, Spring có thể báo lỗi không hỗ trợ media type hoặc không đọc được body. Không chữa bằng cách tự parse chuỗi tùy tiện; kiểm tra đúng `Content-Type`, dependency codec và kiểu tham số.

### 4.3. Cấu hình reader và giới hạn bộ nhớ

`ServerCodecConfigurer` cho phép thêm reader, writer và tùy chỉnh codec mặc định. Một số decoder/reader buffer một phần hoặc toàn bộ body để tạo object đơn. Những trường hợp thường cần chú ý:

- `@RequestBody byte[]` hoặc một object JSON đơn.
- Form URL-encoded được chuyển thành map.
- Multipart dạng map-like cần thu thập các part.
- Các stream cần buffer từng object trước khi decode.

Spring có giới hạn bộ nhớ cho một số codec thông qua `maxInMemorySize`. Giới hạn áp dụng theo cách codec buffer: với body được gom thành một object, nó có thể giới hạn toàn bộ phần cần aggregate; với stream, nó có thể áp dụng theo từng object được tách ra. Không tăng giới hạn chỉ để che việc client gửi payload quá lớn; hãy chọn kiểu streaming và giới hạn phù hợp.

## 5. Body thường là stream một lần: tránh đọc hoặc subscribe hai lần

HTTP request body là một luồng byte có vòng đời gắn với request. Không nên giả định có thể đọc raw body nhiều lần:

~~~java
@PostMapping("/bad")
public Mono<String> bad(@RequestBody Mono<CreateOrder> body) {
    Mono<CreateOrder> first = body;
    Mono<CreateOrder> second = body;

    // Hai nhánh có thể cố tiêu thụ cùng một request body.
    return first.flatMap(a ->
        second.map(b -> a.name() + b.name()));
}
~~~

Đoạn trên không phải cách chia sẻ body an toàn. Hai subscription vào cùng một body publisher có thể vi phạm giả định một lần đọc, tạo lỗi hoặc hành vi không mong muốn tùy resolver/reader. Hãy subscribe một lần và chia sẻ **giá trị đã decode** trong cùng pipeline:

~~~java
@PostMapping("/good")
public Mono<String> good(@RequestBody Mono<CreateOrder> body) {
    return body.map(order ->
        order.name() + ":" + order.quantity());
}
~~~

Nếu thật sự cần dùng dữ liệu ở nhiều nhánh, hãy decode một lần rồi dùng giá trị đó trong cùng `flatMap`/`zipWhen` hoặc cache có chủ đích với giới hạn bộ nhớ và vòng đời ngắn. Không cache toàn bộ body stream lớn mà không có chính sách.

### 5.1. Form data và multipart có API cache riêng

`ServerWebExchange.getFormData()` đọc và cache dữ liệu form đã parse để nhiều thành phần có thể truy cập cùng kết quả. `getMultipartData()` cũng cung cấp cách truy cập multipart dạng map-like và cache kết quả parse. Tuy nhiên, sau khi dùng các API này, **raw request body ban đầu không còn có thể đọc lại** theo cách tùy ý. Hãy nhất quán: nếu đã dùng API form/multipart được cache, tiếp tục dùng API đó thay vì đọc raw body lần nữa.

Khi xử lý multipart streaming bằng `Flux<PartEvent>`, nội dung của mỗi part phải được tiêu thụ, chuyển tiếp hoặc giải phóng đúng cách. Bỏ qua DataBuffer mà không release có thể gây rò rỉ bộ nhớ trên server dùng buffer pool.

## 6. Khi nào framework ghi response body?

Sau khi handler/controller trả về một giá trị, Spring xác định cách xử lý return value. Với `@ResponseBody` hoặc `@RestController`, dữ liệu được encode qua `HttpMessageWriter`. `ResponseEntity` bổ sung status và headers; WebFlux.fn dùng `ServerResponse` và `BodyInserter`.

### 6.1. Chuỗi ghi response

~~~text
Controller trả Object / Mono<T> / Flux<T>
                 |
                 v
HandlerResultHandler chọn cách xử lý return value
                 |
                 v
Xác định body type + Content-Type/Accept
                 |
                 v
Chọn HttpMessageWriter phù hợp
                 |
                 v
Framework subscribe vào Publisher của response
                 |
                 v
Encoder chuyển object thành DataBuffer/byte
                 |
                 v
HTTP server ghi byte và commit response
                 |
                 v
Hoàn tất, lỗi hoặc client cancel
~~~

Với `Mono<T>` hoặc `Flux<T>`, framework không cần gọi `subscribe()` trong controller. Nó tạo chuỗi ghi response và quản lý subscription ở tầng server. Publisher trả về từ controller là một phần của pipeline đó.

### 6.2. `@RestController` và `@ResponseBody`

`@RestController` là annotation kết hợp `@Controller` và `@ResponseBody`. Giá trị trả về được ghi vào HTTP body qua `HttpMessageWriter`:

~~~java
@GetMapping("/account")
public Mono<Account> account() {
    return accountService.findCurrent();
}
~~~

Controller trả Publisher. Khi framework xử lý kết quả và subscribe vào pipeline ghi response, `accountService.findCurrent()` được tiêu thụ theo cách Publisher của nó được thiết kế. Writer chọn codec tương ứng, ví dụ Jackson JSON khi media type phù hợp.

### 6.3. Functional endpoint cũng có cùng lifecycle reactive

Với WebFlux.fn:

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    Mono<CreateOrder> order = request.bodyToMono(CreateOrder.class);

    return order.flatMap(service::save)
        .flatMap(saved ->
            ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(saved));
}
~~~

`request.bodyToMono` tạo Publisher đọc body. Việc đọc được thực hiện khi Publisher được subscribe trong chuỗi xử lý. `Mono<ServerResponse>` là response được tạo bất đồng bộ; framework thực thi handler và ghi response qua cùng hạ tầng reactive.

Nếu thao tác lưu trả `Mono<Void>`, có thể dùng `ServerResponse.ok().build(savePublisher)` để response chỉ hoàn tất sau khi Publisher lưu xong. Đây là cách ghép công việc vào lifecycle response thay vì gọi `savePublisher.subscribe()` riêng.

## 7. `HttpMessageWriter`, media type và thời điểm flush

`HttpMessageWriter` lựa chọn cách encode body dựa trên kiểu phần tử và media type. **Một `Flux<T>` không tự động có nghĩa là HTTP client nhận từng item ngay lập tức.** Cách ghi còn phụ thuộc codec và định dạng response.

### 7.1. `application/json`: JSON array có thể được aggregate

Với Jackson JSON encoder mặc định, một Publisher nhiều phần tử có media type `application/json` thường được thu thập thành collection rồi serialize thành một JSON array:

~~~java
@GetMapping(value = "/items", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<Item> items() {
    return Flux.just(
        new Item(1, "A"),
        new Item(2, "B"),
        new Item(3, "C")
    );
}
~~~

Body HTTP có dạng:

~~~json
[
  {"id":1,"name":"A"},
  {"id":2,"name":"B"},
  {"id":3,"name":"C"}
]
~~~

Dù source là `Flux<Item>`, writer mặc định có thể cần thu thập các giá trị trước khi serialize mảng JSON. Vì vậy không nên mặc định `application/json` sẽ flush từng phần tử ngay khi source phát ra.

Đổi lại, nếu writer phải đợi toàn bộ dữ liệu và serialize thành một mảng, một lỗi xảy ra khi source phát/encode trước khi ghi có thể được xử lý trước khi response commit. Tuy nhiên, aggregate tăng bộ nhớ theo số lượng phần tử. Hãy giới hạn kích thước dữ liệu.

### 7.2. NDJSON: encode và ghi từng dòng

Với `application/x-ndjson`, mỗi phần tử được encode thành một JSON object trên một dòng:

~~~java
@GetMapping(value = "/events", produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<Event> events() {
    return Flux.just(
        new Event(1, "created"),
        new Event(2, "updated"),
        new Event(3, "closed")
    );
}
~~~

Body dạng:

~~~text
{"id":1,"type":"created"}
{"id":2,"type":"updated"}
{"id":3,"type":"closed"}
~~~

Streaming media type cho phép encoder ghi và flush từng giá trị. Client có thể bắt đầu xử lý dòng đầu trong khi server vẫn tạo dòng tiếp theo. Đây là lựa chọn phù hợp cho stream event hoặc batch lớn cần xử lý từng phần.

### 7.3. Server-Sent Events (SSE)

Với `text/event-stream`, Spring có thể ghi từng `ServerSentEvent<T>` và flush event để client nhận mà không phải đợi toàn bộ stream:

~~~java
@GetMapping(value = "/notifications", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> notifications() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(index -> ServerSentEvent.<String>builder()
            .id(Long.toString(index))
            .event("tick")
            .data("message-" + index)
            .build());
}
~~~

SSE phù hợp với server-to-client event stream. Một stream vô hạn không tự hoàn tất; cần cancellation, timeout hoặc lifecycle rõ ràng. Đối với kết nối lâu dài, heartbeat có thể giúp phát hiện client đã ngắt kết nối sớm hơn.

### 7.4. So sánh cách ghi

| Media type | Cách ghi thường gặp | Hệ quả |
| --- | --- | --- |
| `application/json` với một object/Mono | Encode một object | Body đơn |
| `application/json` với Flux nhiều phần tử | Jackson mặc định aggregate rồi serialize array | Có thể cần bộ nhớ cho toàn bộ collection |
| `application/x-ndjson` | Encode, ghi và flush từng item | Hợp với stream dữ liệu theo dòng |
| `text/event-stream` | Ghi và flush từng event SSE | Hợp với kết nối event lâu dài |

Nếu cần client thấy từng item sớm, hãy chọn streaming media type phù hợp và kiểm thử cả proxy/gateway vì một số tầng trung gian có thể buffer response.

## 8. Khi nào status/header được quyết định và response được commit?

HTTP response có các phần: status, headers và body. Spring cần biết status/header trước hoặc khi bắt đầu ghi body. Khi response đã **committed**, status và headers không còn có thể thay đổi; body đã gửi cũng không thể thu hồi.

Có ba trường hợp hay gặp với `ResponseEntity`:

| Kiểu return | Khi status/header được xác định | Khi body có dữ liệu |
| --- | --- | --- |
| `ResponseEntity<T>` | Khi method trả về entity đồng bộ | Body đã có sẵn |
| `ResponseEntity<Mono<T>>` / `ResponseEntity<Flux<T>>` | Có ngay từ entity | Body được cung cấp bất đồng bộ sau |
| `Mono<ResponseEntity<T>>` | Khi Mono tạo ra ResponseEntity | Body/metadata được xác định cùng lúc |
| `Mono<ResponseEntity<Flux<T>>>` | Khi Mono tạo entity ngoài | Body Flux tiếp tục chạy sau |

Ví dụ:

~~~java
@GetMapping("/accepted")
public ResponseEntity<Mono<String>> accepted() {
    Mono<String> body = service.loadMessage();
    return ResponseEntity.accepted().body(body);
}
~~~

Status 202 và headers được biết ngay khi entity được trả về; body vẫn được subscribe và ghi sau đó.

Nếu cần status phụ thuộc kết quả bất đồng bộ:

~~~java
@GetMapping("/conditional")
public Mono<ResponseEntity<String>> conditional() {
    return service.findMessage()
        .map(value -> ResponseEntity.ok(value))
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Ở đây phải đợi Publisher của service phát giá trị hoặc complete rỗng mới biết nên tạo response 200 hay 404.

### 8.1. Sau khi commit, không thể thay response bằng JSON lỗi khác

Giả sử stream NDJSON đã gửi hai dòng và phần tử thứ ba gây lỗi encode. Hai dòng đầu có thể đã đến client và response đã committed. Exception handler không thể đổi status từ 200 sang 500 rồi gửi một JSON error body thay thế cho toàn response.

Với streaming protocol, hãy thiết kế cách biểu diễn lỗi phù hợp nếu cần (ví dụ một event lỗi trong hợp đồng stream trước khi kết thúc). Nếu response đã committed, ứng dụng không được giả vờ có thể gửi một response HTTP mới.

## 9. Backpressure và cancellation ảnh hưởng thời điểm đọc/ghi

### 9.1. Request body: đọc theo nhu cầu

Một `Flux<T>` từ request body có thể được tiêu thụ theo demand của downstream. Ví dụ:

~~~java
@PostMapping("/count")
public Mono<Long> count(@RequestBody Flux<Row> rows) {
    return rows
        .limitRate(32)
        .count();
}
~~~

`limitRate` điều chỉnh nhịp request qua pipeline; reader không cần tạo toàn bộ danh sách trong RAM trước khi downstream xử lý. Tuy nhiên, từng codec có thể buffer byte để hoàn thiện một object trước khi phát. Backpressure không có nghĩa mỗi byte được xử lý ngay lập tức, cũng không loại bỏ giới hạn bộ nhớ của decoder.

### 9.2. Response body: subscriber của server điều tiết source

Khi writer ghi một `Flux<T>`, demand từ phần ghi response có thể truyền ngược về Publisher nguồn. Điều này giúp source không nhất thiết phát toàn bộ dữ liệu nhanh hơn tốc độ ghi. Các toán tử có prefetch hoặc buffer vẫn có thể giữ một lượng dữ liệu nhất định; cần đánh giá toàn pipeline.

### 9.3. Client disconnect và cancellation

Nếu client đóng kết nối khi server đang stream, server có thể hủy subscription downstream. Cancellation thường lan ngược về source và các toán tử reactive để dừng phát thêm dữ liệu khi có thể.

Hãy gắn cleanup với lifecycle:

~~~java
@GetMapping("/stream")
public Flux<String> stream() {
    return Flux.interval(Duration.ofMillis(250))
        .map(index -> "item-" + index)
        .doFinally(signal ->
            System.out.println("stream ended: " + signal));
}
~~~

`doFinally` quan sát các đường complete, error và cancel. Nếu source quản lý resource như file, socket hoặc database cursor, dùng cơ chế quản lý resource reactive như `using`/`usingWhen` hoặc API của driver để release đúng lúc.

Cancellation không đảm bảo một thao tác bên ngoài đã bắt đầu sẽ bị rollback hoặc dừng tức thì. Ví dụ server downstream đã nhận request ghi dữ liệu, việc client ngắt kết nối không tự đảo ngược transaction.

## 10. Chương trình Spring Boot 3.5.7 + Java 17 hoàn chỉnh

Chương trình này minh họa bốn trường hợp:

1. `@RequestBody Mono<CreateRequest>`: controller được gọi trước khi body được decode; body được subscribe trong chuỗi response.
2. `@RequestBody CreateRequest`: framework resolve body trước khi gọi controller.
3. `@RequestBody Flux<CreateRequest>`: nhận body NDJSON theo từng item và tổng hợp số lượng.
4. `Flux<StreamItem>` trả về NDJSON: framework subscribe để ghi response theo từng dòng.

Cấu trúc project:

~~~text
webflux-body-lifecycle/
├── pom.xml
└── src/main/java/example/webflux/
    ├── BodyLifecycleApplication.java
    ├── RequestLifecycleFilter.java
    └── BodyLifecycleController.java
~~~

### 10.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-body-lifecycle</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.2. `BodyLifecycleApplication.java`

~~~java
package example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BodyLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(BodyLifecycleApplication.class, args);
    }
}
~~~

### 10.3. `RequestLifecycleFilter.java`

~~~java
package example.webflux;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class RequestLifecycleFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        String path = exchange.getRequest().getPath().value();

        System.out.println("[" + path + "] exchange started");

        return chain.filter(exchange)
            .doFinally(signal ->
                System.out.println(
                    "[" + path + "] exchange finished: " + signal));
    }
}
~~~

Filter không tự subscribe. Nó trả Publisher của `chain.filter(exchange)` và chỉ quan sát lúc chuỗi HTTP hoàn tất hoặc bị hủy. Vì vậy log cuối của filter giúp quan sát toàn bộ lifecycle request/response ở tầng WebFlux.

### 10.4. `BodyLifecycleController.java`

~~~java
package example.webflux;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class BodyLifecycleController {

    public record CreateRequest(String name, int quantity) {}

    public record Receipt(String id, String name, int quantity) {}

    public record ImportSummary(long received) {}

    public record StreamItem(long sequence, String value) {}

    @PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Receipt> echo(
        @RequestBody Mono<CreateRequest> body
    ) {
        log("/echo controller invoked; body Publisher prepared");

        return body
            .doOnSubscribe(subscription ->
                log("/echo request body subscribed"))
            .doOnNext(request ->
                log("/echo decoded request: " + request.name()))
            .map(this::toReceipt)
            .doOnSubscribe(subscription ->
                log("/echo response Publisher subscribed"));
    }

    @PostMapping(
        path = "/eager",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Receipt> eager(
        @RequestBody CreateRequest request
    ) {
        log("/eager controller invoked after body argument resolved");

        return Mono.fromSupplier(() -> toReceipt(request))
            .doOnSubscribe(subscription ->
                log("/eager response Publisher subscribed"));
    }

    @PostMapping(
        path = "/bulk",
        consumes = MediaType.APPLICATION_NDJSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ImportSummary> bulk(
        @RequestBody Flux<CreateRequest> body
    ) {
        log("/bulk controller invoked; body Flux prepared");

        return body
            .doOnSubscribe(subscription ->
                log("/bulk request Flux subscribed"))
            .doOnNext(request ->
                log("/bulk decoded: " + request.name()))
            .count()
            .map(ImportSummary::new)
            .doOnSubscribe(subscription ->
                log("/bulk response Publisher subscribed"));
    }

    @GetMapping(
        path = "/stream",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<StreamItem> stream() {
        log("/stream controller invoked; response Flux prepared");

        return Flux.interval(Duration.ofMillis(250))
            .take(3)
            .map(index -> new StreamItem(
                index + 1,
                "item-" + (index + 1)))
            .doOnSubscribe(subscription ->
                log("/stream response Flux subscribed"))
            .doOnNext(item ->
                log("/stream response item ready: " + item.sequence()));
    }

    private Receipt toReceipt(CreateRequest request) {
        return new Receipt(
            "R-" + request.name(),
            request.name(),
            request.quantity()
        );
    }

    private static void log(String message) {
        System.out.println(message);
    }
}
~~~

### 10.5. Chạy ứng dụng

Yêu cầu JDK 17+ và Maven. Từ thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Thử request dùng reactive body:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -d '{"name":"pen","quantity":2}'
~~~

Body response dự kiến:

~~~json
{"id":"R-pen","name":"pen","quantity":2}
~~~

Log theo thứ tự logic dự kiến:

~~~text
[/api/echo] exchange started
/api/echo controller invoked; body Publisher prepared
/api/echo response Publisher subscribed
/api/echo request body subscribed
/api/echo decoded request: pen
[/api/echo] exchange finished: onComplete
~~~

Điểm cần quan sát: controller được gọi và trả về Publisher trước khi `request body subscribed`. Khi framework subscribe vào response chain để ghi response, subscription đi vào `body` và reader bắt đầu decode request. Thời gian log có thể xen với log server khác; không dựa vào thứ tự giữa các request độc lập.

Thử tham số non-reactive:

~~~bash
curl -i -X POST http://localhost:8080/api/eager \
  -H "Content-Type: application/json" \
  -d '{"name":"book","quantity":1}'
~~~

Body response dự kiến:

~~~json
{"id":"R-book","name":"book","quantity":1}
~~~

Log liên quan:

~~~text
[/api/eager] exchange started
/eager controller invoked after body argument resolved
/eager response Publisher subscribed
[/api/eager] exchange finished: onComplete
~~~

Trong endpoint này, Spring đã resolve `CreateRequest` trước khi gọi controller. `Mono.fromSupplier` vẫn được thực thi khi response Publisher được subscribe.

Thử request stream NDJSON:

~~~bash
curl -i -X POST http://localhost:8080/api/bulk \
  -H "Content-Type: application/x-ndjson" \
  --data-binary $'{"name":"pen","quantity":1}\n{"name":"book","quantity":2}\n'
~~~

Body response dự kiến:

~~~json
{"received":2}
~~~

Request body được decode thành các phần tử `CreateRequest`. Toán tử `count` yêu cầu tiêu thụ toàn bộ stream trước khi tạo `ImportSummary`.

Thử response stream:

~~~bash
curl -N http://localhost:8080/api/stream
~~~

Body dự kiến (mỗi object một dòng, cách nhau khoảng 250 ms):

~~~text
{"sequence":1,"value":"item-1"}
{"sequence":2,"value":"item-2"}
{"sequence":3,"value":"item-3"}
~~~

Trong endpoint này, response Publisher được subscribe khi framework bắt đầu ghi body. NDJSON cho phép writer encode/flush từng phần tử; filter chỉ ghi “exchange finished” sau khi pipeline ghi response hoàn tất.

**Lưu ý về log:** các dòng log của ứng dụng minh họa các điểm subscribe và decode. Thời điểm byte đầu tiên được đẩy xuống socket phụ thuộc server, codec, buffering, network và client; không thể suy ra chính xác chỉ từ thời điểm `doOnNext` của controller.

## 11. Kiểm thử lifecycle bằng WebTestClient

Trong project thực tế, thêm dependency `spring-boot-starter-test` ở scope test và viết kiểm thử tích hợp:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BodyLifecycleIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void reactiveBodyIsDecodedAndWritten() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new BodyLifecycleController.CreateRequest("pen", 2))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("R-pen")
            .jsonPath("$.quantity").isEqualTo(2);
    }

    @Test
    void streamingResponseContainsThreeItems() {
        client.get()
            .uri("/api/stream")
            .accept(MediaType.APPLICATION_NDJSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
            .expectBody(String.class)
            .value(body -> {
                org.junit.jupiter.api.Assertions.assertTrue(
                    body.contains("\"sequence\":1"));
                org.junit.jupiter.api.Assertions.assertTrue(
                    body.contains("\"sequence\":3"));
            });
    }
}
~~~

Đây là đoạn test minh họa; cần các import JUnit, Spring Boot Test và WebTestClient tương ứng. Test response stream ở đây kiểm tra nội dung cuối cùng, không đo thời điểm flush từng dòng. Muốn kiểm tra streaming thực tế, cần client đọc từng chunk/event và đo thời gian nhận với dung sai hợp lý, tránh assertion phụ thuộc timing quá chặt.

Các kiểm thử lifecycle nên bao gồm:

- Body JSON hợp lệ và không hợp lệ.
- Body rỗng khi endpoint yêu cầu dữ liệu.
- Body nhiều phần tử, xác minh không bỏ sót item.
- Client cancel giữa chừng khi gửi/nhận stream.
- Source lỗi trước khi response commit và source lỗi sau khi đã gửi một phần response.
- Payload lớn vượt giới hạn codec.
- Hai request đồng thời, bảo đảm dữ liệu và log correlation không trộn lẫn.

## 12. Lỗi phổ biến và cách sửa

**Lỗi 1 — Nghĩ tạo `Mono` là body đã được đọc.** Assembly chỉ tạo Publisher. Body được tiêu thụ khi reader được subscribe.

**Lỗi 2 — Nghĩ controller nhận `Mono<T>` nghĩa là method sẽ đợi body trước khi chạy.** Method có thể nhận Publisher trước; body được đọc khi subscription đi tới Publisher đó. Nếu cần object trước khi method chạy, khai báo tham số object non-reactive và hiểu rằng Spring phải resolve body trước khi gọi method.

**Lỗi 3 — Controller nhận body Publisher nhưng bỏ qua nó.** Không có toán tử nào trong chuỗi trả về tiêu thụ body. Hãy ghép Publisher vào response pipeline hoặc thiết kế luồng xử lý rõ ràng.

**Lỗi 4 — Gọi `body.subscribe()` thủ công trong controller.** Tạo subscription ngoài lifecycle HTTP, dễ làm response trả trước khi xử lý xong và tách lỗi/cancel.

**Lỗi 5 — Gọi `block()` để chờ body.** Chặn thread non-blocking. Dùng `flatMap`/`map`/`then` để kết hợp Publisher.

**Lỗi 6 — Subscribe hai lần vào raw request body.** Body thường là stream một lần. Decode một lần rồi chia sẻ giá trị đã decode trong cùng pipeline nếu cần.

**Lỗi 7 — Nghĩ mọi `Flux<T>` response đều flush từng item.** `application/json` với Jackson mặc định có thể aggregate thành JSON array. Dùng NDJSON/SSE hoặc streaming media type phù hợp nếu cần ghi từng phần tử.

**Lỗi 8 — Dùng NDJSON nhưng client gửi `application/json`.** Reader lựa chọn theo Content-Type và codec. Khai báo đúng media type ở client và controller.

**Lỗi 9 — Nghĩ `onNext` ở controller đồng nghĩa client đã nhận byte.** Item còn phải qua encoder, writer, server, network và client buffer.

**Lỗi 10 — Cố đổi status/body sau khi response đã committed.** Status và headers không thể thay sau khi byte đã gửi. Với stream, hãy thiết kế error event hoặc kết thúc kết nối theo chính sách.

**Lỗi 11 — Gom stream lớn vào `collectList()` hoặc `byte[]` mà không giới hạn.** Có thể làm tăng bộ nhớ theo kích thước toàn bộ body. Chọn streaming, giới hạn payload và cấu hình codec.

**Lỗi 12 — Đọc raw body trong filter rồi đọc lại ở controller.** Body đã bị tiêu thụ. Dùng API cache form/multipart thích hợp hoặc thiết kế một lần đọc.

**Lỗi 13 — Bỏ qua DataBuffer/PartEvent content.** Buffer pooled cần release hoặc relay/consume đúng cách. Ưu tiên codec cao cấp trừ khi thực sự cần xử lý byte thủ công.

**Lỗi 14 — Cho rằng client cancel luôn rollback thao tác.** Cancel dừng luồng reactive khi có thể, không đảo ngược side effect đã xảy ra ở server hoặc dịch vụ ngoài.

**Lỗi 15 — Dùng `doOnNext` để đo lúc response đã gửi xong.** Callback đó nằm ở upstream của writer. Quan sát toàn bộ chuỗi bằng filter `doFinally`, nhưng ngay cả khi server hoàn tất write cũng không phải acknowledgement nghiệp vụ từ client.

**Lỗi 16 — Dùng streaming mà không xem xét buffering ở proxy.** Server có thể flush từng item nhưng reverse proxy hoặc client library vẫn buffer. Kiểm tra toàn đường truyền bằng client đọc streaming thật.

**Lỗi 17 — Nhầm request publisher và response publisher.** Request body Publisher được tạo từ `HttpMessageReader`; response body Publisher được tiêu thụ bởi `HttpMessageWriter`. Chúng là hai hướng khác nhau của cùng request lifecycle.

## 13. Bài tập tự kiểm tra

1. Với `@RequestBody Order order`, Spring có cần đọc body trước khi gọi controller không? **Có**, vì method cần object đã resolve.
2. Với `@RequestBody Mono<Order> order`, method có thể được gọi trước khi body decode hoàn tất không? **Có**; method nhận Publisher và body được tiêu thụ khi Publisher được subscribe.
3. Ai subscribe vào response Publisher trong controller WebFlux thông thường? **Framework trong pipeline ghi response**, không phải controller tự gọi `subscribe()`.
4. `HttpMessageReader` và `HttpMessageWriter` làm gì? **Reader giải mã HTTP body thành object; writer encode object thành HTTP body.**
5. `Flux<Event>` có bảo đảm toàn bộ body được buffer trước khi xử lý không? **Không**; có thể xử lý streaming theo demand và khả năng codec.
6. `Flux<Item>` trả về với `application/json` có luôn flush từng item không? **Không**; Jackson JSON mặc định có thể aggregate thành array trước khi serialize.
7. Media type nào thường phù hợp để stream từng JSON object theo dòng? **`application/x-ndjson`.**
8. Khi response đã committed, exception handler có thể đổi status từ 200 sang 500 không? **Không.**
9. Client disconnect trong lúc stream có thể gây tín hiệu nào tới upstream? **Cancellation.**
10. Có nên đọc raw body trong filter rồi tiếp tục dùng `@RequestBody` trong controller không? **Không**, trừ khi đã thiết kế cơ chế cache/replay hợp lệ.
11. Vì sao `doOnNext` không chứng minh client đã nhận dữ liệu? **Item còn phải qua encoder, writer, server, network và client buffer.**
12. Khi nào dùng `getFormData()` thay vì đọc raw body? **Khi cần form map-like và muốn dùng kết quả đã parse/cache qua ServerWebExchange.**
13. Vì sao không nên gom file upload lớn thành `byte[]`? **Tốn bộ nhớ và bỏ lợi ích streaming/backpressure.**
14. Nếu cần status HTTP phụ thuộc vào kết quả service bất đồng bộ, chọn `ResponseEntity<Flux<T>>` hay `Mono<ResponseEntity<T>>`? **`Mono<ResponseEntity<T>>` khi status/headers phụ thuộc kết quả Mono trước khi response được tạo.**

## 14. Ghi nhớ và tài liệu chính thức

- **Tạo Publisher ≠ đọc body.** Assembly tạo mô tả xử lý; subscription kích hoạt việc tiêu thụ.
- **`@RequestBody T`**: Spring resolve object trước khi gọi method.
- **`@RequestBody Mono<T>/Flux<T>`**: controller nhận Publisher; body được đọc khi subscription đi tới Publisher đó.
- **Đọc body:** `HttpMessageReader` + decoder + `DataBuffer`.
- **Ghi body:** `HttpMessageWriter` + encoder + response Publisher.
- **Framework quản lý subscription** của request/response; controller trả Publisher, không tự subscribe/block.
- **Flux không tự bảo đảm flush từng item.** Media type và writer quyết định aggregate hay streaming.
- **Response commit là ranh giới quan trọng.** Sau commit không thể thay status/headers/body đã gửi.
- **Backpressure và cancellation** ảnh hưởng việc đọc/ghi; cleanup tài nguyên phải gắn với lifecycle.

Tài liệu chính thức để đối chiếu:

1. [Spring Framework — @RequestBody trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html): cách resolve request body, reactive arguments, validation và HttpMessageReader.
2. [Spring Framework — @ResponseBody trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): reactive return values và HttpMessageWriter.
3. [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): HttpHandler, WebHandler, codecs, DataBuffer, JSON streaming, form/multipart caching và giới hạn buffer.
4. [Spring Framework — Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): ServerRequest.bodyToMono/bodyToFlux, ServerResponse và ghép body Publisher vào response.
5. [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html): thời điểm xác định status/headers so với body reactive.
6. [Spring Framework — HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): cấu hình ServerCodecConfigurer và giới hạn bộ nhớ của codec.
