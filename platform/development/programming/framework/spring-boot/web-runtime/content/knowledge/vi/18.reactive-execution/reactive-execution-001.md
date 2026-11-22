# Chuỗi Publisher từ đọc yêu cầu đến ghi phản hồi trong Spring WebFlux

> **Phạm vi:** Spring Boot web runtime ở mô hình **reactive**, dùng Spring WebFlux và Project Reactor. Bài này theo dõi trọn đường đi của **một HTTP request**: từ byte trên kết nối mạng, giải mã request body thành `Publisher`, xử lý bởi handler/service, đến mã hóa và ghi HTTP response. Ví dụ chạy với **Spring Boot 4.1.2**, **Java 17+** và **Maven 3.6.3+**. Những khái niệm cốt lõi cũng áp dụng cho WebFlux trong Spring Boot 3.x, nhưng cần dùng dependency và phiên bản tương ứng.

## Mục tiêu

Sau bài này, bạn có thể:

1. Mô tả đúng vai trò của `Publisher`, `Subscriber`, `Subscription`, `Mono`, `Flux`, `DataBuffer` và `Mono<Void>` trong chuỗi xử lý HTTP.
2. Giải thích cách WebFlux **đọc body theo luồng**, giải mã thành đối tượng, biến đổi bằng operator và ghi response theo nhu cầu downstream.
3. Phân biệt **lắp ghép pipeline (assembly)** với **thực thi khi subscribe**, biết ai subscribe và vì sao handler thông thường không tự gọi `subscribe()` hoặc `block()`.
4. Hiểu sự lan truyền `onNext`, `onError`, `onComplete`, tín hiệu `request(n)` và `cancel` qua các lớp.
5. Tự xây dựng và gọi hai endpoint: POST JSON một kết quả, GET Server-Sent Events nhiều kết quả; nhận diện những sai lầm thường gặp về blocking, buffering, lỗi và ngắt kết nối.

## 1. Khung tư duy: HTTP request và Publisher không phải cùng một thứ

**Reactive Streams** định nghĩa một giao thức giữa nguồn phát `Publisher<T>` và bên tiêu thụ `Subscriber<T>`. Publisher có thể phát **0 đến nhiều phần tử**, kết thúc thành công hoặc kết thúc bằng lỗi; subscriber dùng `Subscription` để yêu cầu dữ liệu và hủy luồng.

Trong Reactor, hai kiểu thường gặp là:

| Kiểu | Số phần tử dữ liệu | Sử dụng phổ biến trong WebFlux |
| --- | --- | --- |
| `Mono<T>` | 0 hoặc 1 | Giải mã một JSON object, tìm một bản ghi, tạo một response, chờ một công việc bất đồng bộ |
| `Flux<T>` | 0 đến N | Các chunk body, dãy phần tử JSON/NDJSON, sự kiện SSE, dữ liệu stream liên tục |
| `Mono<Void>` | Không có giá trị `T` hữu ích; chỉ phát tín hiệu kết thúc hoặc lỗi | Biểu diễn **hoàn tất một thao tác**, ví dụ xử lý exchange hoặc hoàn tất việc ghi response |
| `Flux<DataBuffer>` | Nhiều bộ đệm byte | Biểu diễn request body hoặc response body ở tầng dữ liệu thô, trước/sau codec |

Một HTTP request có **method, path, headers** và có thể có **body**. Headers thường đã được đọc đủ để định tuyến khi handler được chọn; phần body có thể còn đang đến qua mạng. WebFlux diễn tả dữ liệu body thành Publisher để xử lý bất đồng bộ, không cần giữ toàn bộ request trong bộ nhớ trước khi bắt đầu làm việc nếu codec/trường hợp sử dụng hỗ trợ streaming.

Ví dụ: `POST /api/echo` mang `{"name":"Lan"}`. Ở tầng transport có các byte; ở tầng ứng dụng, `request.bodyToMono(EchoRequest.class)` cung cấp `Mono<EchoRequest>`. Service biến đối tượng thành kết quả `Mono<String>`; WebFlux dùng `HttpMessageWriter` biến kết quả thành bytes cho response. Đây là **chuỗi liên kết nhiều Publisher/Subscriber và adapter**, không phải một đối tượng `Publisher` duy nhất chứa mọi tầng.

**Phân biệt quan trọng:** WebFlux hỗ trợ HTTP server reactive trên Reactor Netty và cũng có adapter cho những container Servlet tương thích. Dùng Netty là lựa chọn phổ biến của starter WebFlux, nhưng `reactive` không đồng nghĩa riêng với Netty; tiêu chí chính là API non-blocking và giao thức Publisher/Subscriber. Không đưa kiến trúc `DispatcherServlet` của Spring MVC vào pipeline WebFlux; front controller của WebFlux là **`DispatcherHandler`**.

## 2. Bản đồ toàn bộ request-to-response

Với Spring Boot + WebFlux + Reactor Netty, có thể hình dung:

~~~text
Client gửi POST /api/echo và JSON qua TCP/HTTP
             |
             v
Reactor Netty: nhận request, quản lý I/O non-blocking
             |
             v
ReactorHttpHandlerAdapter -> HttpHandler
             |
             v
WebHttpHandlerBuilder: tạo chuỗi WebHandler
    +--> WebExceptionHandler (bọc xử lý lỗi)
    +--> WebFilter chain (lọc request/response)
    +--> DispatcherHandler (front controller WebFlux)
            |
            +--> HandlerMapping (tìm route/handler)
            +--> HandlerAdapter (gọi handler)
            |       |
            |       +--> Handler đọc body:
            |       |    Flux<DataBuffer>
            |       |       -> HttpMessageReader / Decoder
            |       |       -> Mono<EchoRequest>
            |       |       -> map / flatMap / service
            |       |       -> Mono<ServerResponse>
            |       |
            |       +--> HandlerResult
            |
            +--> HandlerResultHandler / ServerResponse.writeTo
                    |
                    +--> HttpMessageWriter / Encoder
                    +--> Publisher<DataBuffer> để ghi body
             |
             v
Response status + headers + bytes -> Reactor Netty -> client

Toàn exchange hoàn tất qua một tác vụ kiểu Mono<Void>
khi ghi xong, lỗi xảy ra hoặc request bị hủy.
~~~

**Không hiểu sơ đồ như từng bước đồng bộ chiếm một thread đến cuối.** Đây là sơ đồ trách nhiệm và liên kết của pipeline. Việc đọc, xử lý, ghi có thể diễn ra qua nhiều callback bất đồng bộ; `onNext` từ nguồn đến downstream theo nhu cầu, các bước có thể được thực hiện đan xen với I/O.

### Các tầng đảm nhận điều gì?

| Tầng | Giao diện/cấu phần | Công việc |
| --- | --- | --- |
| Server transport | Reactor Netty | Nhận/gửi byte, thông báo khả năng đọc/ghi của socket |
| Adapter HTTP | `HttpHandler`, `ServerHttpRequest`, `ServerHttpResponse` | Cầu nối giữa server cụ thể với xử lý HTTP không phụ thuộc server |
| Web chain | `WebFilter`, `WebExceptionHandler`, `WebHandler` | Xử lý cross-cutting concern, định nghĩa chuỗi xử lý và điểm chặn lỗi |
| Front controller | `DispatcherHandler` | Tìm handler, gọi handler, chuyển kết quả đến phần ghi response |
| Routing | `HandlerMapping` | Tìm route trong controller annotation hoặc functional `RouterFunction` |
| Invocation | `HandlerAdapter` | Giải quyết tham số và gọi handler; đóng gói `HandlerResult` |
| Request codec | `HttpMessageReader` + `Decoder` | Chuyển `DataBuffer` thành Java object, chuỗi, multipart hoặc element stream |
| Business pipeline | `Mono`/`Flux` + Reactor operators | Áp dụng validation, service, biến đổi dữ liệu và xử lý lỗi do ứng dụng sở hữu |
| Response codec | `HandlerResultHandler` hoặc functional `ServerResponse`, `HttpMessageWriter`/`Encoder` | Chọn status/header, mã hóa giá trị thành bytes và ghi response |
| Kết thúc exchange | `Mono<Void>` và terminal signal | Báo hoàn tất/error của công việc HTTP; cancel có thể cắt ngắn quá trình |

Ở kiểu **annotated controller**, `RequestMappingHandlerMapping` chọn method `@GetMapping`/`@PostMapping`; `RequestMappingHandlerAdapter` thực hiện invocation; `ResponseBodyResultHandler` ghi kết quả từ `@RestController`. Ở kiểu **functional endpoint**, `RouterFunctionMapping` chọn `HandlerFunction` nhận `ServerRequest` và trả `Mono<ServerResponse>`. Cả hai đi trên cùng cơ sở web reactive bên dưới; cách mô tả route và ghi response có khác nhau.

## 3. Từng bước: từ đọc yêu cầu đến ghi phản hồi

### Bước 1 — Request đến và body được biểu diễn thành luồng byte

Khi request được chấp nhận, server adapter tạo/giới thiệu request-response abstraction. Ở tầng thấp, có thể xem:

~~~java
// Minh họa API của WebFlux trong một WebHandler; không phải chương trình độc lập.
Flux<DataBuffer> rawBody = exchange.getRequest().getBody();
~~~

`DataBuffer` là abstraction cho buffer byte. Với Netty, buffer có thể dùng pooled memory và reference counting. Chia gói TCP, các đoạn HTTP và những `DataBuffer` bạn thấy không có nghĩa mỗi phần tương ứng một JSON object. Không tự đọc “một buffer = một message”.

`getBody()` cho phép xử lý không chặn theo cách phù hợp với runtime; không có nghĩa toàn body tự động được load sẵn. Muốn đọc chuỗi raw bytes, phải xử lý framing, encoding, giới hạn kích thước và giải phóng buffer đúng cách. Trong ứng dụng thông thường, **ưu tiên codec cấp cao** như `bodyToMono(...)` hoặc `@RequestBody Mono<T>`.

### Bước 2 — Định tuyến trước khi handler tiêu thụ body

`DispatcherHandler` hỏi các `HandlerMapping` để tìm handler phù hợp với path, method, headers và các điều kiện route. Sau đó `HandlerAdapter` hoặc functional handler được sử dụng để tạo kết quả.

Điểm cần nắm: **định tuyến thường dựa trên method/path/header, không phải đợi giải mã hết body**. Handler có thể được chọn trước khi body đến đầy đủ. Các đoạn body sau được đẩy vào luồng khi I/O và demand cho phép.

Nếu không có route phù hợp, framework tạo lỗi HTTP tương ứng mà không cần chạy business pipeline của route đó. Nếu có `WebFilter`, filter có thể thực hiện công việc trước/sau handler thông qua chuỗi `Mono<Void>`.

### Bước 3 — `HttpMessageReader` giải mã Publisher của body

Functional WebFlux có thể viết:

~~~java
Mono<EchoRequest> input = request.bodyToMono(EchoRequest.class);
~~~

Annotated WebFlux tương đương ở mức ý tưởng:

~~~java
@PostMapping("/api/echo")
public Mono<EchoResponse> echo(@RequestBody Mono<EchoRequest> input) {
    return input.flatMap(req -> service.reply(req.name()))
                .map(EchoResponse::new);
}
~~~

Đoạn annotated là minh họa, giả sử `service.reply(...)` trả `Mono<String>`, có sẵn các import và `EchoRequest`/`EchoResponse`. Không thêm route này cùng path vào project functional bên dưới.

`bodyToMono(EchoRequest.class)`/`@RequestBody Mono<EchoRequest>` sử dụng các `HttpMessageReader` phù hợp với `Content-Type` và kiểu dữ liệu, chẳng hạn JSON decoder. Dữ liệu byte được giải mã thành một object và phát **một** `onNext(EchoRequest)`, rồi `onComplete`; body trống có thể trở thành `Mono.empty()`; JSON sai hoặc media type không được hỗ trợ dẫn đến lỗi HTTP/phát `onError` theo giai đoạn liên quan.

Khi cần nhiều phần tử, `bodyToFlux(T.class)` có thể giải mã thành nhiều object **nếu codec và media type cho phép biểu diễn luồng**, ví dụ NDJSON. Nhưng `Flux<T>` ở API **không tự đảm bảo** server stream từng object ngay tức thì với mọi `application/json` thông thường. Khả năng streaming phụ thuộc format, codec, nguồn dữ liệu và cách flush.

**Body không phải tài nguyên lặp lại vô hạn.** Đừng tự `subscribe()` hai lần vào Publisher body để đọc cùng payload nhiều lần; body HTTP theo mặc định là một dòng byte từ kết nối, không tự có cơ chế replay. Muốn xử lý body cho nhiều mục đích, hãy giải mã một lần rồi chia sẻ kết quả một cách có kiểm soát, hoặc dùng cơ chế cache/decorate request có giới hạn kích thước và quy tắc DataBuffer rõ ràng.

### Bước 4 — Lắp ghép nghiệp vụ bằng operator

Ví dụ chuỗi xử lý:

~~~java
return request.bodyToMono(EchoRequest.class)            // Mono<EchoRequest>
    .flatMap(value -> service.reply(value.name()))     // Mono<String>
    .map(message -> new EchoResponse(message))         // Mono<EchoResponse>
    .flatMap(result -> ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(result));                           // Mono<ServerResponse>
~~~

Sự khác biệt giữa các operator:

- `map(T -> R)`: biến đổi **đồng bộ, nhanh**, tạo một giá trị `R` cho mỗi giá trị `T`; không dùng để gọi một hàm trả `Mono<R>` rồi mong kết quả được tự chờ/flatten.
- `flatMap(T -> Mono<R>)`: biến mỗi `T` thành một publisher bất đồng bộ và **nối/phẳng hóa** kết quả. Với `Flux.flatMap`, nhiều publisher nội bộ có thể được xử lý đồng thời, khiến thứ tự phần tử khác thứ tự input; dùng `concatMap` nếu cần lần lượt theo thứ tự.
- `filter`: có thể khiến chuỗi trở thành empty khi giá trị không thỏa; cần quyết định explicit empty có nghĩa “không có dữ liệu”, 404, 400 hay 204.
- `switchIfEmpty`: chọn publisher khác khi upstream hoàn tất mà không có dữ liệu, thường dùng để biến empty thành một lỗi HTTP hoặc kết quả dự phòng.
- `onErrorResume`: chuyển một loại lỗi thành publisher dự phòng/phản hồi; không dùng để nuốt mọi lỗi một cách vô điều kiện.
- `then()`: bỏ qua giá trị dữ liệu upstream, chờ hoàn tất rồi trả `Mono<Void>`; thích hợp khi mục tiêu là một thao tác hoàn thành thay vì cần body.

**Pipeline không phải chuỗi lệnh gọi đồng bộ:** dòng `flatMap(...)` mô tả cách xử lý khi upstream cung cấp giá trị. Khi method handler trả `Mono<ServerResponse>`, những việc chưa được subscribe có thể chưa chạy. Service có thể thực hiện I/O reactive khi subscription diễn ra.

### Bước 5 — Handler trả Publisher, framework điều phối subscription

Trong WebFlux, handler thường **trả về** `Mono<T>`, `Flux<T>` hoặc `Mono<ServerResponse>`; phần framework/server sẽ đảm nhiệm tích hợp vào exchange và **subscribe** tại ranh giới runtime.

Vì vậy không viết:

~~~java
// Sai trong WebFlux handler:
service.save(input).subscribe();  // bỏ mặc lỗi, cancel và thứ tự hoàn tất
return Mono.empty();              // HTTP có thể hoàn tất trước khi save xong
~~~

Hãy **kết hợp và trả lại Publisher**:

~~~java
// Đúng về mặt composition, giả sử save(input) trả Mono<?>:
return service.save(input).then();
~~~

`subscribe()` tường minh có thể phù hợp tại một boundary imperative do ứng dụng thực sự sở hữu, ví dụ event listener đã được thiết kế để tự quản lý lifecycle và error. Tuy nhiên, trong HTTP handler, subscribe sớm làm **đứt đường lan truyền lỗi, context, cancellation và completion** giữa công việc và response.

`block()`/`blockFirst()`/`blockLast()` đợi kết quả đồng bộ, có nguy cơ chặn event loop và Reactor còn có thể từ chối blocking trên scheduler được đánh dấu non-blocking. Nếu phải gọi thư viện legacy blocking, hãy cô lập nó (ví dụ `Mono.fromCallable(...)` + `subscribeOn(Schedulers.boundedElastic())`) và giới hạn tải; giải pháp dài hạn là dùng driver hoặc client non-blocking.

### Bước 6 — Viết response là một pipeline Publisher khác

Ở annotated WebFlux, `HandlerResultHandler` chọn cách xử lý kết quả `Mono<EchoResponse>`/`Flux<T>`. Với functional WebFlux, `ServerResponse` có status, headers và body sẽ được ghi qua `ServerResponse.writeTo(...)`. `HttpMessageWriter` chọn encoder phù hợp với kiểu/`Content-Type`, chuyển object thành `DataBuffer` rồi chuyển đến tầng response.

Nếu handler trả `Mono<ServerResponse>`, đừng nhầm:

1. **Outer `Mono<ServerResponse>`:** bất đồng bộ xác định response (status/headers/body strategy).
2. **Publisher của response body:** có thể là `Mono<T>`, `Flux<T>` hoặc giá trị được adapter biến thành publisher để codec ghi.
3. **Mono hoàn tất ghi exchange:** tượng trưng cho việc runtime đã đi qua quá trình commit và ghi response hoặc lỗi của quá trình ấy.

Với `Mono<EchoResponse>` và JSON thông thường, response thường là một JSON object. Với `Flux<EchoResponse>` và `application/json`, codec có thể dựng **một JSON array**; tùy codec/format sẽ có buffering. Với `text/event-stream`, các sự kiện được encode/flush thành một dòng SSE để client nhận dần. Với `application/x-ndjson`, mỗi đối tượng JSON nằm trên một dòng, hữu ích để stream record liên tục. Không xem mọi `Flux<T>` trả về là HTTP streaming đến client ngay.

**Thời điểm commit quan trọng:** sau khi status/headers đã được gửi, lỗi mới xảy ra trong quá trình stream body thường không thể chuyển response 200 đang truyền thành response 500 mới. Ứng dụng cần xử lý lỗi trước commit nếu có thể; với SSE/NDJSON dài, nên thiết kế cách báo lỗi trong giao thức stream và cách client reconnect.

### Bước 7 — Kết thúc, lỗi và hủy

Reactive Streams có các signal cơ bản:

~~~text
Subscriber <- onSubscribe(Subscription)
Subscriber  -> request(n)    // downstream yêu cầu tối đa n phần tử
Publisher   -> onNext(value) // có dữ liệu khi nguồn phát và có demand
Publisher   -> onNext(value) // ... có thể nhiều lần với Flux
Publisher   -> onComplete()  // một terminal signal thành công
         HOẶC
Publisher   -> onError(err)  // một terminal signal lỗi
         HOẶC
Subscriber  -> cancel()      // ngừng nhận dữ liệu từ upstream
~~~

`onComplete` và `onError` loại trừ nhau trong cùng một subscription hợp lệ. `cancel()` không phải là `onError`/`onComplete`, và việc hủy có thể cần thời gian truyền tới nguồn. Với `Mono<Void>` hoàn tất thành công, không có `onNext(value)` nhưng vẫn có `onComplete()`.

Client ngắt kết nối có thể làm transport hủy/đóng chuỗi ghi. Publisher được kết hợp đúng cách có thể nhận cancel để ngừng truy vấn, timer hoặc nguồn dữ liệu. Tuy nhiên việc cancel **không tự rollback** một thao tác đã commit bên ngoài (ví dụ ghi database). Cancellation propagation phụ thuộc adapter, nguồn Publisher và trạng thái I/O; không nên hứa mọi kết nối đóng đều dừng toàn bộ side effect ngay lập tức.

## 4. Assembly, subscription và backpressure: ba điểm phải tách biệt

### Assembly: khi tạo đối tượng Publisher

Ví dụ:

~~~java
Mono<String> pipeline = Mono.just("lan")
    .map(String::toUpperCase)
    .doOnNext(System.out::println);
~~~

Ở đây pipeline mới được **mô tả**; `System.out.println` trong `doOnNext` chưa chạy chỉ vì code tạo `Mono`. Khi subscriber thực sự yêu cầu và nguồn phát `onNext`, tác dụng mới xảy ra. Một số factory có tính eager ở lúc tạo đối tượng, ví dụ biểu thức đối số truyền cho `Mono.just(expensiveCall())` chạy ngay. Dùng `Mono.defer(...)` hoặc `Mono.fromCallable(...)` khi cần trì hoãn việc tạo dữ liệu đến subscription.

### Subscription: tạo quan hệ upstream/downstream

Khi runtime subscribe, Reactor xây chuỗi subscriber theo operator. `Subscription` liên kết hai phía, sau đó downstream đưa ra demand. Đối với handler, WebFlux làm việc này trong quy trình HTTP; người viết controller không tự subscribe.

Nếu gọi hai lần `subscribe()` với một **cold publisher**, công việc có thể chạy hai lần (ví dụ hai HTTP calls hoặc hai truy vấn). Một **hot publisher** có thể đang phát dữ liệu độc lập với mỗi subscriber, nên người đến sau có thể không thấy phần tử trước đó. `share()`, `cache()`, `publish()` thay đổi semantics và có hệ quả về bộ nhớ, thời gian sống, số subscription; không dùng chỉ để “chữa” một lỗi không hiểu rõ.

### Demand/backpressure: subscriber yêu cầu bao nhiêu dữ liệu

`request(n)` thể hiện nhu cầu downstream; nguồn tuân thủ Reactive Streams không nên phát `onNext` vượt demand chưa được đáp ứng. Khi client đọc chậm, server có thể hạn chế việc nhận/đẩy dữ liệu ngược lên upstream, qua I/O adapter và các operator có hỗ trợ backpressure.

Nhưng **backpressure không xóa hết buffering**. Nguồn ngoài có thể không hỗ trợ điều tiết, hoặc codec/operator có thể cần buffer để giải mã một JSON object lớn. `flatMap` có prefetch, `buffer` gom phần tử, `collectList` thu toàn bộ sequence vào RAM, `cache` giữ dữ liệu; cần đo bộ nhớ và giới hạn payload thực tế.

Ví dụ về tốc độ: một `Flux` có 100.000 sự kiện không nhất thiết tạo 100.000 response objects ngay lập tức. Với SSE và một nguồn hỗ trợ demand, dữ liệu có thể được tạo/ghi dần; nhưng nếu dùng `collectList()` trước khi trả response, bạn đã chuyển từ streaming sang tích lũy đủ dữ liệu rồi mới trả.

**Luật thực hành:** đừng gọi `subscribe()` hoặc `request(Long.MAX_VALUE)` thủ công để “ép chạy” handler; hãy trả Publisher cho framework và theo dõi buffering/backpressure tại những vị trí thực tế có tải.

## 5. Dự án Java 17 chạy được: POST JSON và GET SSE

Ví dụ này cố ý dùng **functional endpoints** để nhìn thấy rõ `ServerRequest.bodyToMono(...)` và `ServerResponse.body(...)`. Không truy cập database, không tạo thread riêng; source `Flux.interval` chỉ dùng để minh họa việc phát từng sự kiện theo thời gian.

Cấu trúc thư mục:

~~~text
webflux-publisher-flow/
  pom.xml
  src/main/java/com/example/publisherflow/
    PublisherFlowApplication.java
    RouteConfig.java
    EchoHandler.java
    EchoService.java
~~~

**`pom.xml`** — starter WebFlux đi kèm Reactor Netty; parent quản lý phiên bản dependency tương thích.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-publisher-flow</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

**`src/main/java/com/example/publisherflow/PublisherFlowApplication.java`**

~~~java
package com.example.publisherflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PublisherFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(PublisherFlowApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/publisherflow/RouteConfig.java`**

~~~java
package com.example.publisherflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class RouteConfig {
    @Bean
    RouterFunction<ServerResponse> routes(EchoHandler handler) {
        return RouterFunctions.route()
                .POST("/api/echo", handler::echo)
                .GET("/api/ticks", handler::ticks)
                .build();
    }
}
~~~

**`src/main/java/com/example/publisherflow/EchoService.java`**

~~~java
package com.example.publisherflow;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class EchoService {
    public Mono<String> reply(String name) {
        return Mono.justOrEmpty(name)
                .map(String::trim)
                .filter(value -> !value.isEmpty())
                .switchIfEmpty(Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "name must not be blank")))
                .map(value -> "Hello, " + value + "!");
    }
}
~~~

Ở đây `Mono.justOrEmpty(null)` tạo publisher rỗng và `switchIfEmpty(...)` chuyển `null`/chuỗi trắng thành HTTP 400. Không có side effect phải chờ; việc dùng `Mono` vẫn giúp nối liền pipeline và thể hiện cách một service có thể thay bằng I/O reactive sau này.

**`src/main/java/com/example/publisherflow/EchoHandler.java`**

~~~java
package com.example.publisherflow;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoHandler {
    private final EchoService service;

    public EchoHandler(EchoService service) {
        this.service = service;
    }

    // Chỉ một JSON object -> một response JSON object.
    public Mono<ServerResponse> echo(ServerRequest request) {
        return request.bodyToMono(EchoRequest.class)
                .switchIfEmpty(Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "request body is required")))
                .flatMap(body -> service.reply(body.name()))
                .map(EchoResponse::new)
                .flatMap(result -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(result));
    }

    // Flux phát ba phần tử, mỗi 500 ms, dưới dạng SSE.
    public Mono<ServerResponse> ticks(ServerRequest request) {
        Flux<String> events = Flux.interval(Duration.ofMillis(500))
                .take(3)
                .map(index -> "tick-" + index);

        return ServerResponse.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .body(events, String.class);
    }

    public record EchoRequest(String name) {}
    public record EchoResponse(String message) {}
}
~~~

Lưu ý mã trên **không** tự `subscribe()`. `echo()` tạo Publisher cho kết quả. Với `ticks()`, `Mono<ServerResponse>` dựng metadata response và `Flux<String>` làm nguồn body; WebFlux subscribe/ghi dữ liệu theo lifecycle của HTTP exchange. `Flux.interval(...)` dùng scheduler của Reactor cho timer; đây là mô phỏng source không chặn, chưa phải ví dụ truy vấn dữ liệu thực tế.

### Chạy thử

Ở thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Mặc định server chạy trên cổng 8080 nếu không có cấu hình khác chi phối. Trên Bash hoặc shell hiểu single quotes, gửi request:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -d '{"name":" Lan "}'
~~~

Kỳ vọng status **HTTP 200**, `Content-Type` JSON và body:

~~~json
{"message":"Hello, Lan!"}
~~~

Khoảng trắng trong `name` bị loại bởi `String::trim`. Số thứ tự và thứ tự HTTP headers, thời gian phản hồi, phần thông tin kết nối có thể khác theo môi trường.

Kiểm tra lỗi tên trống:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -d '{"name":"   "}'
~~~

Kỳ vọng **HTTP 400**; body lỗi do Spring Boot/WebFlux error handler quyết định và có thể khác theo cấu hình/version, nên không khóa cứng nội dung JSON lỗi.

Đọc dòng sự kiện:

~~~bash
curl -N -i http://localhost:8080/api/ticks
~~~

Kỳ vọng HTTP 200, `Content-Type: text/event-stream`, lần lượt có ba payload mang giá trị `tick-0`, `tick-1`, `tick-2`; mỗi sự kiện đến theo nhịp timer, thay vì đợi gom thành một JSON array. Với một SSE writer điển hình, dữ liệu nhìn gần như:

~~~text
data:tick-0

data:tick-1

data:tick-2

~~~

Đây là **minh họa body SSE**; cặp xuống dòng, header và thời điểm thực tế do writer/server/client quyết định. `curl -N` tắt buffering đầu ra của curl để bạn quan sát từng sự kiện.

Trên Windows PowerShell, có thể gửi JSON bằng lệnh thay cho cú pháp multiline Bash:

~~~powershell
Invoke-RestMethod -Uri "http://localhost:8080/api/echo" -Method Post -ContentType "application/json" -Body '{"name":" Lan "}'
~~~

Và dùng `curl.exe -N http://localhost:8080/api/ticks` để xem SSE dưới dạng stream.

### Truy vết cụ thể chuỗi Publisher ở POST

| Giai đoạn | Đối tượng/publisher | Khi nào có dữ liệu? |
| --- | --- | --- |
| Server nhận HTTP request | `ServerHttpRequest` / raw `Flux<DataBuffer>` | Khi transport có byte và phần body được tiêu thụ |
| Functional handler gọi `bodyToMono` | `Mono<EchoRequest>` | Khi codec đọc đủ payload để tạo object |
| `flatMap(body -> service.reply(...))` | `Mono<String>` | Khi input đã được giải mã và service publisher có dữ liệu |
| `map(EchoResponse::new)` | `Mono<EchoResponse>` | Khi có `String` kết quả |
| `flatMap(result -> ServerResponse...)` | `Mono<ServerResponse>` | Khi đã dựng metadata và body strategy của HTTP response |
| WebFlux ghi body | `HttpMessageWriter` + data-buffer Publisher | Khi outer response đã có và runtime subscribe publisher dữ liệu phản hồi |
| Hoàn tất | `Mono<Void>` từ exchange/write | Khi quá trình ghi hoàn tất hoặc thất bại/cancel theo lifecycle |

Với GET SSE, bước giải mã request body **không có**; `Flux.interval().take(3)` trực tiếp tạo dữ liệu để ghi. Đây là minh họa rằng mọi HTTP exchange có một pipeline riêng, không nhất thiết exchange nào cũng đi qua `bodyToMono`.

## 6. Khi ứng dụng thực tế kết nối với nguồn dữ liệu

Giả sử service dùng một client database reactive:

~~~java
// Minh họa, phụ thuộc vào repository reactive thực tế của dự án:
public Mono<OrderDto> findOrder(String id) {
    return reactiveRepository.findById(id)
            .map(order -> new OrderDto(order.getId(), order.getTotal()));
}
~~~

`reactiveRepository.findById` phải thực sự cung cấp publisher bất đồng bộ (ví dụ R2DBC hoặc driver reactive tương thích). Không được suy ra rằng bao một lời gọi JDBC đồng bộ trong `Mono.just(...)` sẽ biến nó thành non-blocking; JDBC đã chạy trước khi tạo Mono.

Nếu bắt buộc tạm tích hợp một API blocking:

~~~java
// Minh họa trong một service đã có legacyClient; không phải code độc lập.
Mono<Result> result = Mono.fromCallable(() -> legacyClient.load())
        .subscribeOn(Schedulers.boundedElastic());
~~~

Cách này **cô lập thao tác blocking khỏi event loop**, nhưng thao tác bên trong vẫn blocking và tiêu tốn thread; cần timeout, giám sát pool, giới hạn concurrency và kế hoạch chuyển sang API non-blocking. `publishOn` và `subscribeOn` đổi execution context, không tự biến thư viện đồng bộ thành asynchronous I/O.

Khi gọi WebClient:

~~~java
// Minh họa với WebClient đã được cấu hình sẵn:
Mono<CustomerDto> customer = webClient.get()
        .uri("/customers/{id}", customerId)
        .retrieve()
        .bodyToMono(CustomerDto.class);
~~~

Đây cũng chỉ là pipeline. Đừng gọi `block()` để lấy `CustomerDto` ngay trong WebFlux handler; hãy `flatMap` publisher trả về từ WebClient vào luồng response. `WebClient` xử lý HTTP client-side và trả Publisher để ghép nối với chuỗi server-side.

## 7. Xử lý lỗi, empty và cancel theo từng giai đoạn

| Giai đoạn lỗi | Ví dụ | Xử lý phù hợp |
| --- | --- | --- |
| Định tuyến | Không tìm thấy handler cho `/api/missing` | Framework xử lý response kiểu 404; kiểm tra router/mapping |
| Decode | JSON không hợp lệ, media type sai, payload vượt giới hạn | Để WebFlux trả lỗi 4xx phù hợp; cấu hình codec/giới hạn và kiểm thử |
| Validation/nghiệp vụ | `name` rỗng hoặc record không tồn tại | Trả `ResponseStatusException` hoặc mapping 400/404 rõ ràng |
| I/O downstream | Service/database/WebClient timeout hoặc lỗi | Dùng `timeout`, `onErrorMap`/`onErrorResume` có chọn lọc, log context |
| Encode/write response | Không serialize được kiểu dữ liệu; socket lỗi | Chẩn đoán writer/codec và trạng thái response đã commit |
| Client cancel | Người dùng đóng tab/đóng kết nối SSE | Ngừng nguồn upstream khi có thể; không giả định side effect được rollback |

Trong một chuỗi `Mono<T>`, empty khác error:

~~~java
// Giả sử repository.findById trả Mono<Order>:
return repository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND, "Order not found")))
        .map(OrderDto::from);
~~~

Nếu `Mono.empty()` đi thẳng đến response mà không có chính sách rõ ràng, kết quả có thể không như hợp đồng API mong muốn. Với `onErrorResume`, chỉ bắt những lỗi bạn hiểu; tránh `onErrorResume(error -> Mono.empty())` chung cho mọi exception vì nó làm mất lỗi và tạo response thiếu dữ liệu.

Muốn quan sát lifecycle (đoạn sau là minh họa trong một method trả Publisher):

~~~java
return somePublisher
        .doOnSubscribe(subscription -> log.debug("subscribed"))
        .doOnNext(value -> log.debug("emitted"))
        .doOnError(error -> log.warn("failed", error))
        .doFinally(signal -> log.debug("terminated: {}", signal));
~~~

`doFinally` có thể nhận kết quả như `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. Đừng mặc định mọi thành phần trong pipeline sẽ luôn đi qua `doOnNext`: `Mono.empty()` và `Mono<Void>` có thể hoàn tất mà không phát giá trị.

**Khi response stream đã gửi một phần:** server không thể thu hồi byte đã gửi. Một exception tại sự kiện thứ 10 của SSE có thể đóng stream giữa chừng; thiết kế consumer để nhận biết mất kết nối, retry có giới hạn, idempotency hoặc event ID khi cần. Không tự động `retry()` Publisher đọc raw HTTP request body, vì nguồn body network không được đảm bảo replay và retry có thể thực hiện side effect trùng lặp.

## 8. Phân biệt các định dạng response thường gặp

| Kiểu trả về của ứng dụng | Content-Type thường dùng | Hành vi trên dây cần hiểu |
| --- | --- | --- |
| `Mono<T>` | `application/json` | Một object/value JSON hoặc empty/error |
| `Flux<T>` | `application/json` | Thường là một JSON array; việc gửi từng phần phụ thuộc codec, có thể buffer |
| `Flux<T>` | `application/x-ndjson` | Nhiều JSON object, mỗi object một dòng; thích hợp record stream |
| `Flux<ServerSentEvent<T>>` hoặc dữ liệu SSE hỗ trợ | `text/event-stream` | Các event theo thời gian; thích hợp server → browser/client |
| `Flux<DataBuffer>` | Tùy loại bytes | Truyền buffer thô; ứng dụng phải hiểu release/cancellation |
| `Mono<Void>` | Không cần body | Thành công khi công việc hoàn thành; có thể phù hợp 204 hoặc response không body theo contract đã chọn |

**SSE không phải WebSocket.** SSE là response HTTP server → client dạng event stream; WebSocket hỗ trợ giao tiếp hai chiều theo cơ chế khác. **Mono không mặc định nhanh hơn blocking cho mọi tác vụ**: giá trị lớn nhất của thiết kế reactive thường thể hiện khi nhiều I/O chờ đợi và các nguồn/đích thực sự non-blocking.

## 9. Giới hạn tài nguyên và lỗi phổ biến khi tự xây publisher chain

1. **Blocking trên event loop:** gọi `Thread.sleep`, JDBC, `InputStream.read`, `Future.get`, `block()` trong pipeline xử lý I/O. Kết quả là các request khác bị chậm vì event loop không thể tiếp tục phục vụ.
2. **Subscribe thủ công ở controller:** tạo “fire and forget” làm HTTP response có thể hoàn tất trước nghiệp vụ; mất propagation error/cancel/context.
3. **Đọc request body nhiều lần:** gọi `bodyToMono`/subscribe lặp cho cùng request mà không có chiến lược replay; gặp body rỗng hoặc lỗi tiêu thụ.
4. **Giữ nguyên `DataBuffer` mà không release:** ở backend dùng pooled buffers có thể gây memory leak; với controller thông thường, dùng codec để framework quản lý buffer.
5. **Dùng `collectList` vô hạn:** tích lũy một stream lớn trong bộ nhớ và phá mục tiêu xử lý tăng dần; cần giới hạn số phần tử/kích thước.
6. **Dùng `Flux.flatMap` khi yêu cầu giữ thứ tự:** các kết quả async có thể về lộn thứ tự; cân nhắc `concatMap` hoặc xử lý có điều kiện rõ ràng.
7. **Nhầm empty với error:** không có dữ liệu không tự đồng nghĩa 404/400; quyết định API contract và sử dụng `switchIfEmpty` nếu cần.
8. **Trả SSE nhưng không có nhịp heartbeat:** một số proxy/client có thể ngắt kết nối ít dữ liệu; với stream lâu dài, gửi event/comment giữ kết nối theo chiến lược phù hợp.
9. **Assume all Flux = streaming:** `application/json`, codec, proxy và client có thể buffer; dùng media type tương ứng và kiểm tra bằng `curl -N`/network tracing.
10. **Tự gắn dữ liệu request vào `ThreadLocal`:** operator có thể chạy ở những thread khác nhau. Khi cần truyền metadata/correlation id qua chain, cân nhắc Reactor `Context` và các cơ chế context propagation có hỗ trợ.
11. **Cấu hình nhầm MVC/WebFlux:** trong một Spring Boot app có cả MVC và WebFlux starter, Boot thường chọn MVC theo mặc định. Muốn server WebFlux, phải bảo đảm đúng web application type/dependency, tránh áp servlet filter/interceptor thay cho `WebFilter`.
12. **Thay đổi response quá muộn:** status và headers chỉ sửa được trước commit. Với stream dài, thiết kế error protocol và timeout phù hợp.

### Bộ câu hỏi kiểm tra thực tế

**Câu 1.** Tại sao `return service.save(body).then()` phù hợp hơn `service.save(body).subscribe(); return Mono.empty();`?

**Đáp án:** Chuỗi HTTP vẫn chờ công việc hoàn thành, nhận error/cancel theo pipeline và lifecycle được gắn với HTTP exchange. Với subscribe thủ công, save chạy độc lập và response có thể hoàn tất trước khi save xong.

**Câu 2.** `bodyToMono(Order.class)` đọc `Flux<DataBuffer>` lúc nào?

**Đáp án:** Nó tạo Publisher để decoder đọc request body; việc tiêu thụ dữ liệu thực sự được điều phối khi pipeline được subscribe và demand/I/O cho phép. Headers/routing có thể đã được xử lý trước đó.

**Câu 3.** Handler trả `Flux<Event>` thì client luôn nhìn thấy từng event ngay?

**Đáp án:** Không. Điều này phụ thuộc `Content-Type`, writer, buffering, flushing và client. SSE/NDJSON phù hợp hơn khi mục tiêu là từng event/record; phải đo thực tế.

**Câu 4.** Client disconnect có tự rollback một lệnh insert đã commit không?

**Đáp án:** Không. Cancel có thể dừng công việc còn đang chờ nếu nguồn hỗ trợ, nhưng không đảo ngược side effect đã hoàn tất. Cần transaction/idempotency phù hợp.

**Câu 5.** Điều gì đóng vai trò front controller của WebFlux, và ai ghi response?

**Đáp án:** `DispatcherHandler` điều phối `HandlerMapping`/`HandlerAdapter`/`HandlerResultHandler`. Response được mã hóa bởi các writer/codec rồi ghi qua HTTP adapter/server; ứng dụng mô tả response bằng `Mono`/`Flux` hoặc `ServerResponse`.

## 10. Tài liệu chính thức

- [Spring Framework — WebFlux Reactive Core: HttpHandler, WebHandler, DataBuffer, codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — WebFlux DispatcherHandler: routing, adapter, result handler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
- [Spring Framework — WebFlux Functional Endpoints: ServerRequest/ServerResponse](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework — WebFlux @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html)
- [Spring Boot — Reactive Web Applications và cấu hình WebFlux](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Project Reactor — Subscription and backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/reference/getting-started/system-requirements.html)

**Điều cần nhớ:** Request body có thể là một `Flux<DataBuffer>` được codec chuyển thành `Mono<T>`/`Flux<T>`; ứng dụng **ghép** operator và trả Publisher; framework **subscribe và ghi** response; demand, lỗi, completion và cancel có thể đi ngược/xuôi qua chuỗi. Hiểu đường đi đó giúp giữ I/O non-blocking, kiểm soát bộ nhớ và xác định chính xác khi nào request thực sự hoàn tất.