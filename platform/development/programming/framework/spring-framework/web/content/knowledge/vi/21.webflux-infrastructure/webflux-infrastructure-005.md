# Codec, HttpMessageReader, HttpMessageWriter và cấu hình giới hạn bộ nhớ trong Spring WebFlux

## 1. Vì sao một ứng dụng reactive vẫn có thể hết bộ nhớ?

Spring WebFlux dùng API reactive và I/O bất đồng bộ để xử lý HTTP, nhưng **không đồng nghĩa mọi request/response luôn được streaming không giới hạn bộ nhớ**. Khi nhận JSON, form, multipart, SSE hoặc text, Spring vẫn cần biến các **bytes của HTTP body** thành đối tượng Java. Khi trả response, nó lại phải chuyển đối tượng Java thành bytes. Công việc này do hệ thống **HTTP codecs** đảm nhiệm.

Một API:

```java
@PostMapping("/documents")
Mono<Result> upload(@RequestBody Mono<Document> input) {
    return input.map(this::process);
}
```

có thể phải **tích lũy nhiều bytes của một JSON object** trước khi decoder tạo được `Document`. Nếu client gửi object có giá trị chuỗi rất dài hoặc nhiều mảng lồng nhau, quá trình này có thể gây áp lực heap/direct memory dù controller không hề gọi `collectList()`. Đây là lý do hệ thống HTTP codecs có giới hạn **`maxInMemorySize`** và có thể phát sinh `DataBufferLimitException`.

Các câu hỏi của bài:

1. Sự khác biệt giữa **`Encoder`/`Decoder`** và **`HttpMessageWriter`/`HttpMessageReader`** là gì?
2. Một `@RequestBody Mono<T>`, `@RequestBody Flux<T>` và `@ResponseBody Flux<T>` được chuyển qua codec như thế nào?
3. Khi nào limit áp vào **cả body**, khi nào áp vào **một record/delimiter/event**?
4. Cấu hình đúng `spring.http.codecs.max-in-memory-size` cho **Spring Boot 3.5** và `ServerCodecConfigurer.defaultCodecs().maxInMemorySize(...)` cho WebFlux ra sao?
5. Làm thế nào thiết lập riêng cho **WebClient** và phân biệt inbound server với outbound client?
6. Vì sao codec limit không phải **max HTTP upload**, rate limit, tổng heap limit hay backpressure policy?
7. Tại sao multipart có giới hạn riêng cho RAM, disk và part count? Khi nào dùng `FilePart`, `PartEvent`?
8. Làm sao kiểm thử decode, NDJSON streaming, `DataBufferLimitException` và byte-buffer lifecycle một cách có căn cứ?

**Phạm vi:** Spring Framework **6.2.x**, Spring Boot **3.5.x**, Java **17+**, **WebFlux reactive stack** và mặc định Reactor Netty. Tên property ở Spring Boot 3.5 được lấy theo chính metadata của release, không dùng máy móc các ví dụ Boot cũ. Bài thuộc nhóm **Hạ tầng WebFlux**.

## 2. Tổng quan đường đi request và response

```text
                  INBOUND HTTP REQUEST
HTTP/TCP bytes
    |
Reactor Netty / ServerHttpRequest
    |
Flux<DataBuffer>
    |
HttpMessageReader<T>
   + Decoder<T> nếu dùng codec chuyển bytes -> object
    |
@RequestBody Mono<T> / Flux<T> hoặc ServerRequest.bodyToMono(...)
    |
Handler / Service (validation + business)
    |
Flux<R> / Mono<R> / ResponseEntity<...>
    |
HttpMessageWriter<R>
   + Encoder<R> nếu dùng codec chuyển object -> bytes
    |
Flux<DataBuffer>
    |
ServerHttpResponse -> Reactor Netty -> HTTP client
                  OUTBOUND HTTP RESPONSE
```

Điều quan trọng: **`DataBuffer`** là abstraction cho vùng bytes, không nhất thiết là `byte[]` trên heap. Với Reactor Netty, dữ liệu có thể dựa trên Netty `ByteBuf` với pooled/direct memory. Hệ thống codecs và writers/readers quản lý nhiều tác vụ decode/encode, media type, character set, hints và buffer lifecycle.

- **Reader** quan tâm HTTP request/response body **đầu vào** của một thành phần.
- **Writer** quan tâm HTTP request/response body **đầu ra** của một thành phần.
- Trên **server**, đọc request bằng reader, ghi response bằng writer.
- Trên **WebClient**, ghi outbound request bằng writer, đọc inbound response bằng reader.
- Các vai trò đổi theo chiều đọc/ghi; **không có một bộ codec “chỉ dành cho server” về mặt nguyên lý**.
- HTTP codec không thay thế business validation, authorization, chống malware, giới hạn tổng payload hay quản lý các kết nối chậm.

## 3. So sánh các tầng API

| Lớp/API | Package Spring tiêu biểu | Vai trò | Phụ thuộc HTTP? |
| --- | --- | --- | --- |
| `DataBuffer` | `org.springframework.core.io.buffer` | Đại diện bytes/chunks | Không |
| `DataBufferFactory` | `org.springframework.core.io.buffer` | Tạo/cấp phát DataBuffer | Không |
| `DataBufferUtils` | `org.springframework.core.io.buffer` | Join, read, write, retain/release, stream hỗ trợ | Không |
| `Decoder<T>` | `org.springframework.core.codec` | `Flux<DataBuffer>` → objects | Không nhất thiết |
| `Encoder<T>` | `org.springframework.core.codec` | Objects → `DataBuffer` | Không nhất thiết |
| `HttpMessageReader<T>` | `org.springframework.http.codec` | Đọc HTTP body, có headers, media type, hints | **Có** |
| `HttpMessageWriter<T>` | `org.springframework.http.codec` | Ghi HTTP body, xử lý HTTP output/message metadata | **Có** |
| `DecoderHttpMessageReader<T>` | `org.springframework.http.codec` | Adapter bọc một Decoder để đọc HTTP | Có |
| `EncoderHttpMessageWriter<T>` | `org.springframework.http.codec` | Adapter bọc một Encoder để ghi HTTP | Có |
| `ServerCodecConfigurer` | `org.springframework.http.codec` | Cấu hình readers/writers cho WebFlux server | Có |
| `ClientCodecConfigurer` | `org.springframework.http.codec` | Cấu hình codecs cho WebClient | Có |
| `DataBufferLimitException` | `org.springframework.core.io.buffer` | Cảnh báo decoder/join vượt giới hạn tích lũy | Không |

Spring Framework mô tả `Encoder` và `Decoder` là hợp đồng mức thấp, độc lập với HTTP; `HttpMessageReader` và `HttpMessageWriter` đưa hợp đồng này vào ngữ cảnh HTTP. Những codec đặc thù như **multipart, form data, SSE** có thể là reader/writer chuyên dụng, không nhất thiết chỉ là Jackson encoder bọc ngoài.

### 3.1. Hai chuyển đổi cơ bản

**Đọc JSON:**

```text
Content-Type: application/json
Body: {"id":7,"name":"An"}
                |
     Jackson2JsonDecoder
                |
             Item
```

**Ghi JSON:**

```text
Item(id=7,name="An")
                |
     Jackson2JsonEncoder
                |
application/json response bytes
{"id":7,"name":"An"}
```

`Jackson2JsonDecoder` và `Jackson2JsonEncoder` có các quy tắc xử lý stream khác nhau theo media type và Reactor publisher type. Đừng mô tả WebFlux là “convert text sang object” mà bỏ qua MediaType, DataBuffer lifecycle, validation và limit.

## 4. HttpMessageReader: inbound body được đọc như thế nào?

Trong Spring WebFlux annotated controllers:

```java
@PostMapping("/items")
Mono<Item> create(@RequestBody Mono<Item> input) {
    return input;
}
```

`@RequestBody` được infrastructure dùng một **`HttpMessageReader` phù hợp** với body type và `Content-Type` để decode request. Với JSON, reader thường bọc Jackson decoder khi Jackson có trong classpath.

### 4.1. Chọn reader

Việc chọn phụ thuộc vào:

- Target type: `Item`, `String`, `byte[]`, `DataBuffer`, `MultiValueMap`, `Part`, v.v.
- `Content-Type` do client khai báo và media type mà reader hỗ trợ.
- Reactive wrapper/cardinality: `Mono<T>` hoặc `Flux<T>`.
- Generic type information như `List<Item>`, `Map<String,Object>`, `Flux<Item>`.
- Codecs đã đăng ký và thứ tự ưu tiên.
- ObjectMapper/Kotlin/Jackson XML/Protobuf dependencies nếu cần.
- Decoding hints/charset/validation sau khi deserialize.

**Không tin Content-Type là xác minh nội dung an toàn.** Header do client kiểm soát; một JSON parser có thể từ chối cú pháp sai, nhưng điều đó không đồng nghĩa dữ liệu đã đúng quy tắc nghiệp vụ.

### 4.2. `Mono<T>` có thể phải gom nội dung

```java
@PostMapping(path = "/echo", consumes = "application/json")
Mono<Echo> echo(@RequestBody Mono<Echo> request) {
    return request;
}
```

Đây là **fragment** giả định có record `Echo`. Khi một JSON object nằm trên nhiều network chunks, decoder cần ghép đủ tokens để tạo object. **Limit áp vào bytes tích lũy để decode một đơn vị**, không chỉ một TCP chunk.

Nếu JSON object lớn hơn limit (ví dụ một field chứa vài MB text), có thể ném `DataBufferLimitException`. Tùy lớp xử lý lỗi/exception resolver, status mặc định **không nên được đoán là luôn 413**. Hãy cấu hình HTTP error contract có kiểm thử thực tế.

### 4.3. `Flux<T>` hỗ trợ stream nhưng không miễn limit

```java
@PostMapping(
    path = "/items/stream",
    consumes = "application/x-ndjson")
Mono<Summary> summary(@RequestBody Flux<Item> items) {
    // Xử lý theo từng record...
    return items.reduce(...);
}
```

Fragment minh họa. Với NDJSON, mỗi dòng là một JSON value. Reader có thể decode từng record mà **không tích lũy cả HTTP body**. Tuy nhiên **một dòng/record quá dài** vẫn có thể vượt `maxInMemorySize` khi codec phải giữ đến delimiter hoặc object hoàn chỉnh.

Một stream có **1 triệu dòng × mỗi dòng 1 KiB** về nguyên tắc có thể được đọc dần dù tổng request lớn hơn 256 KiB. Nhưng nếu bạn `collectList()` toàn stream hoặc `reduce` tạo structure tăng dần không giới hạn thì heap vẫn có thể OOM; limit codec không giới hạn tổng kết quả mà application tự giữ.

### 4.4. Form body và multipart

Với `application/x-www-form-urlencoded`, framework thường phải phân tích toàn bộ form fields thành cấu trúc, nên có buffering và các giới hạn tương ứng. Với multipart, parser có cơ chế chuyển file parts sang disk và các giới hạn riêng. Không xem multipart là “chỉ một JSON request lớn”.

## 5. HttpMessageWriter: outgoing response bytes

`@ResponseBody` / `@RestController` được WebFlux xử lý bằng `HttpMessageWriter`:

```java
@GetMapping(path = "/item", produces = "application/json")
Mono<Item> one() {
    return Mono.just(new Item(1, "demo"));
}
```

Jackson encoder biến `Item` thành JSON bytes, HttpMessageWriter ghi vào `ServerHttpResponse` qua reactive buffers.

### 5.1. Flux và media type quyết định behavior

```java
@GetMapping(path = "/items", produces = "application/json")
Flux<Item> items() {
    return Flux.range(1, 3)
            .map(i -> new Item(i, "item-" + i));
}
```

Với `application/json`, nhiều giá trị thường được biểu diễn thành **JSON array**:

```json
[
  {"id":1,"name":"item-1"},
  {"id":2,"name":"item-2"},
  {"id":3,"name":"item-3"}
]
```

Trong khi `application/x-ndjson` biểu diễn từng JSON object theo dòng:

```text
{"id":1,"name":"item-1"}
{"id":2,"name":"item-2"}
{"id":3,"name":"item-3"}
```

Và `text/event-stream` dùng SSE framing:

```text
event: update
data: {"id":1,"name":"item-1"}

event: update
data: {"id":2,"name":"item-2"}

```

**Không mặc định** mỗi `onNext` sẽ lập tức tạo một HTTP packet. Encoder/writer, buffering/flush policy, proxy, HTTP/2 DATA frames và client đều ảnh hưởng thời điểm nhận dữ liệu. `Flux<T>` chỉ là một nguồn reactive; semantics của HTTP output còn phụ thuộc `Content-Type`.

### 5.2. Writer và custom serialization

Khi muốn đổi tên JSON fields hoặc format timestamps, ưu tiên cấu hình **Jackson ObjectMapper** / DTO annotations theo chuẩn Boot. Không tự viết một `HttpMessageWriter` chỉ để đổi tên field hoặc cắt chuỗi.

Khi có **media type riêng** như `application/vnd.mycompany.binary`, cân nhắc viết `Encoder`/`Decoder` hoặc reader/writer chuyên dụng nếu thật sự có wire protocol mới; cần tuân thủ backpressure, byte lifecycle và validation. Xem phần 17.

## 6. DataBuffer: byte storage và lifecycle

`DataBuffer` trừu tượng hóa byte regions. Trên Reactor Netty, một `DataBuffer` có thể bọc pooled Netty `ByteBuf` (direct memory). Bộ nhớ trực tiếp **không hiển thị đầy đủ trong heap usage**; ứng dụng có thể chịu OOM/direct memory pressure dù heap metrics còn ổn.

Các thao tác thường gặp:

```java
DataBufferFactory factory = new DefaultDataBufferFactory();
DataBuffer buffer = factory.wrap(
        "hello".getBytes(StandardCharsets.UTF_8));
```

Đây là fragment với imports Spring buffer + `StandardCharsets`, không phải file độc lập. `DefaultDataBufferFactory` trong test thường tạo buffer unpooled; trong Netty có thể dùng pooled buffer factory.

### 6.1. Không được giữ DataBuffer tùy tiện

Sai kiểu:

```java
List<DataBuffer> all = new ArrayList<>();
return request.getBody()
        .doOnNext(all::add)
        .then();
```

Đây là **anti-pattern**: giữ mọi buffer có thể gây tăng RAM/direct memory, và pooled buffers có vòng đời release. Phải consume, relay hoặc release theo đúng contract.

Nếu code **tự sở hữu** một buffer và quyết định bỏ nó, sử dụng `DataBufferUtils.release(buffer)`. Nếu sử dụng buffer sau asynchronous handoff, có thể phải `retain` theo cách phù hợp; không double-release hoặc dùng sau release.

### 6.2. `DataBufferUtils.join` là aggregation — có limit khi cần

```java
Mono<DataBuffer> combined =
        DataBufferUtils.join(sourceBuffers, 8 * 1024);
```

Khi tổng bytes vượt 8192, Spring có thể phát `DataBufferLimitException`. Nếu thành công, một combined buffer được trả về; bên **nhận/tiêu thụ** phải release đúng nếu tự quản lý nó. Khi `join` gặp error/cancel, API đã có contract giải phóng các buffers tích lũy.

Không dùng overload `DataBufferUtils.join(sourceBuffers)` không có bound cho data untrusted hoặc stream vô hạn nếu không có control/limit ở nơi khác.

### 6.3. File streaming

Đối với file lớn, hãy **stream** từ disk/object store thay vì `DataBufferUtils.join` toàn bộ file. Ví dụ dùng `DataBufferUtils.read(Path, DataBufferFactory, bufferSize)` và `ServerHttpResponse.writeWith(...)` trong code phù hợp, hoặc `Resource`/`FilePart.transferTo(...)` theo use case.

Lưu ý: không biến việc dùng `Flux<DataBuffer>` thành bảo đảm an toàn tuyệt đối. Cần giới hạn **tổng bytes, thời gian, số concurrent streams, disk quota, permissions và file validation**.

## 7. Vì sao có DataBufferLimitException?

Class:

```java
import org.springframework.core.io.buffer.DataBufferLimitException;
```

Exception biểu thị số bytes tích lũy vượt giới hạn đặt trước trong một decoder/reader/join operation. Điều này có thể xảy ra khi:

- Decode một JSON request object quá lớn.
- `bodyToMono(String.class)`/`bodyToMono(byte[].class)` cho body lớn.
- Decode form-data thành toàn bộ map.
- JSON streaming: **một** record/tokens quá lớn.
- SSE: một event payload/line vượt khả năng tích lũy.
- `DataBufferUtils.join(source, maxBytes)`.
- WebClient nhận response lớn và muốn aggregate thành một object.
- Decoder XML/protobuf/custom codec cần buffer một đơn vị lớn, tùy implementation.

Lỗi điển hình:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

Thông báo chính xác có thể khác theo Spring version/decoder. Không tự kết luận đây là “heap đã đầy”; thường là **guardrail cố ý từ chối một unit quá lớn trước khi dùng thêm bộ nhớ**.

### 7.1. Không phải mọi trường hợp đều giống nhau

| Đường xử lý | Giới hạn thường áp vào | Có giới hạn tổng HTTP body? |
| --- | --- | --- |
| JSON object → `Mono<Pojo>` | Bytes cần để decode một object | Không nhất thiết tách biệt |
| Text → `Mono<String>` | Chuỗi body được aggregate | Thực tế là body mà decoder đọc |
| NDJSON → `Flux<Pojo>` | Một record/JSON value | **Không** giới hạn toàn stream |
| SSE → `Flux<ServerSentEvent<T>>` | Nội dung một event/đơn vị parser | **Không** giới hạn toàn kết nối |
| Multipart form field | Bytes của từng non-file part | **Không** thay max-parts |
| Multipart file part | Ngưỡng giữ in-memory trước khi spool disk | **Không** thay disk usage quota |
| `Flux<DataBuffer>` | Chunks thô | Không tự aggregate; app phải kiểm soát |
| `collectList()` trong service | Heap dùng cho tất cả items trong list | Codec limit không kiểm soát |
| `WebClient.bodyToMono(...)` | Client decode/aggregation | Không phải server inbound limit |

**Cần phân biệt unit-of-aggregation và tổng bytes** khi quyết định nâng từ 256 KiB lên 2 MiB. Nếu mỗi user gửi 2 MiB và có 200 requests đồng thời, chỉ riêng buffered payloads có thể tương đương hàng trăm MB, chưa kể parser structures và network buffers.

## 8. Mặc định và cấu hình Spring Boot 3.5

### 8.1. Property ĐÚNG cho Boot 3.5

Trong **Spring Boot 3.5**, cấu hình codec liên quan chính thức là:

```properties
# src/main/resources/application.properties
spring.http.codecs.max-in-memory-size=8KB
```

Tên namespace này là **`spring.http.codecs.*`** trong Boot **3.5**. Spring Boot 3.5 metadata xác nhận `HttpCodecsProperties` với prefix `spring.http.codecs` (có từ 3.5.0). Một số bài hướng dẫn **Boot cũ** dùng `spring.codec.max-in-memory-size`; không copy property cũ mà không xem phiên bản và configuration metadata.

**Mặc định Boot 3.5:** property `spring.http.codecs.max-in-memory-size` **không đặt** nếu người dùng không cấu hình. Khi đó các codec dùng default riêng; đa số codec tích lũy có giới hạn khoảng **256 KiB**. Không khẳng định mọi codec/multipart mode có cùng default/behavior.

Property này áp dụng cho **auto-configured WebFlux server** và các **WebClient instances được Boot auto-configure**; nó không tự thay đổi mọi `WebClient.create()` tự tạo ngoài Boot builder, không tự áp dụng cho app Spring Framework tự quản lý hoàn toàn và không phải “giới hạn memory của cả JVM”.

### 8.2. YAML tương đương

```yaml
spring:
  http:
    codecs:
      max-in-memory-size: 8KB
```

Chỉ chọn một nơi khai báo thống nhất. Với config theo environment, cần xác định precedence và kiểm tra config hiệu dụng trong staging/production thay vì chỉ đọc file source.

### 8.3. Vì sao chọn 8 KiB cho demo?

Để dễ thử guardrail trên các JSON nhỏ:

- Body JSON echo vài chục bytes → qua.
- Một JSON field lớn hàng chục KiB → có thể gây decoder limit.
- NDJSON nhiều dòng nhỏ → có thể stream qua dù **tổng** body lớn hơn 8 KiB.
- Một NDJSON **dòng duy nhất** trên 8 KiB → có thể vượt limit từng record.

**8 KiB chỉ là ngưỡng học tập**, không phải recommendation production. Với API upload hồ sơ hoặc thông tin người dùng thực tế, một record hợp lệ có thể cần lớn hơn; chọn dựa trên payload distributions, business validation, concurrent load và overhead.

### 8.4. Chỉ có property không đủ để giới hạn upload

Nếu cần giới hạn **tổng request HTTP** ở 1 MiB, một codec max-in-memory-size 1 MiB chưa chắc bảo đảm điều đó. Một `Flux<DataBuffer>` hoặc multipart file đã spool disk có thể vượt tổng dung lượng, mà codec vẫn xử lý streaming bình thường. Hãy kết hợp proxy/gateway max request size, server/container controls và byte-counting ở application layer.

## 9. Cấu hình trực tiếp ServerCodecConfigurer

Không dùng Boot autoconfiguration hoặc cần custom codec behavior? Spring WebFlux cung cấp `WebFluxConfigurer`:

```java
package demo.codec;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
class CodecConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(512 * 1024);
    }
}
```

**Code class này độc lập hợp lệ khi đặt trong app WebFlux cùng package.** `ServerCodecConfigurer` cung cấp bộ default readers/writers và cách thêm, thay hoặc tùy chỉnh codecs. `WebFluxConfigurer#configureHttpMessageCodecs` được WebFlux gọi cho cả annotated controllers lẫn functional endpoints.

**Đừng tự thêm `@EnableWebFlux` vào Spring Boot app chỉ để đổi limit.** Trong Boot, `@EnableWebFlux` có thể làm Boot WebFlux auto-configuration bị thay thế/disable theo cách không mong muốn; implement `WebFluxConfigurer` mà không thêm annotation này khi muốn giữ Boot defaults.

### 9.1. Property vs Java config

- **Property** phù hợp khi muốn đặt chung global default trong Boot.
- **`WebFluxConfigurer`** phù hợp khi cần kiểm soát codec setup theo application architecture.
- Nếu cùng lúc đặt property và Java override khác nhau, thứ tự áp dụng có thể phụ thuộc auto-config/customization; **không suy đoán giá trị hiệu lực**. Chọn một nguồn cấu hình, test payload tại ranh giới.
- Có thể có codec custom với limit riêng, không tự nghe mọi default settings.
- Với **WebClient**, cần cấu hình codec ở client builder riêng nếu không dùng Boot-configured `WebClient.Builder` hoặc muốn giới hạn khác.

### 9.2. Server side không dùng Servlet `HttpMessageConverter`

Spring MVC Servlet dùng `HttpMessageConverter`. **Spring WebFlux dùng `HttpMessageReader`/`HttpMessageWriter` với reactive codecs.** Tên lớp tương tự nhưng khác contract và stack. Đừng copy MVC `configureMessageConverters`/`extendMessageConverters` để điều khiển WebFlux reactive codec.

## 10. WebClient: HTTP client cũng có codec memory limit

`WebClient` viết request và đọc response qua `ClientCodecConfigurer`. Khi cần đọc response JSON lớn:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.org")
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024))
        .build();
```

Đây là **fragment**, cần import `org.springframework.web.reactive.function.client.WebClient`. Limit trên áp cho codec của **client instance này**, không thay `ServerCodecConfigurer` inbound server.

Nếu cần giữ tùy chỉnh Boot:

```java
@Service
class PartnerClient {
    private final WebClient http;

    PartnerClient(WebClient.Builder builder) {
        this.http = builder
                .baseUrl("https://partner.example")
                .codecs(c -> c.defaultCodecs()
                        .maxInMemorySize(512 * 1024))
                .build();
    }
}
```

Đây là fragment cần `@Service` và import WebClient; partner hostname minh họa. Trong Boot, injection `WebClient.Builder` giúp hưởng các customizations được auto-configured; `WebClient.create()` **không nhất thiết** có chúng. Khi mutate builder, kiểm tra limit nào được dùng cuối cùng.

### 10.1. bodyToMono và bodyToFlux

```java
Mono<List<Item>> all = client.get()
        .uri("/items")
        .retrieve()
        .bodyToMono(new ParameterizedTypeReference<List<Item>>() {});
```

Dạng này thường cần decode **một JSON array** vào `List<Item>`; nếu body/array rất lớn, có thể bị codec limit hoặc heap cao.

```java
Flux<Item> stream = client.get()
        .uri("/items.ndjson")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(Item.class);
```

Với NDJSON, mỗi record có thể decode riêng, làm giảm nhu cầu aggregate toàn response. Nhưng `stream.collectList()` sẽ lại tập hợp toàn bộ items trong application heap. **Streaming codec không sửa được một consumer gom tất cả dữ liệu.**

### 10.2. Client không mặc nhiên đồng bộ limit với server

Ví dụ origin server cho JSON object tối đa 1 MiB nhưng WebClient consumer còn default khoảng 256 KiB → client có thể ném `DataBufferLimitException` khi server đã trả HTTP 200. Đọc stack trace/metrics để xác định **lỗi xuất hiện trong client decoder hay server decoder**.

Không nâng client limit lên 100 MiB chỉ để “sửa lỗi” mà không hỏi vì sao response cần lớn vậy. Cân nhắc pagination/NDJSON/streaming endpoints, giới hạn array size và kiểm soát aggregate trong service.

## 11. Multipart: giới hạn RAM khác giới hạn disk và số parts

Multipart thường xuất hiện trong API upload ảnh, file CSV, video hoặc form có nhiều fields. Spring WebFlux có parser và `FilePart`/`Part`/`PartEvent`; các giới hạn chuyên biệt khác với global HTTP codec memory setting.

**Spring Boot 3.5** có các properties được document:

```properties
# Chỉ là ví dụ policy, phải điều chỉnh theo sản phẩm:
spring.webflux.multipart.max-in-memory-size=64KB
spring.webflux.multipart.max-disk-usage-per-part=10MB
spring.webflux.multipart.max-parts=8
spring.webflux.multipart.max-headers-size=10KB
```

Ý nghĩa:

| Property | Phạm vi |
| --- | --- |
| `spring.webflux.multipart.max-in-memory-size` | Ngưỡng giữ non-file part trong RAM; với file part có thể xác định khi nào spool ra disk |
| `spring.webflux.multipart.max-disk-usage-per-part` | Mức disk sử dụng tối đa cho mỗi file part được ghi ra disk |
| `spring.webflux.multipart.max-parts` | Tổng số parts cho request |
| `spring.webflux.multipart.max-headers-size` | Bộ nhớ cho phần headers của một part |
| `spring.webflux.multipart.file-storage-directory` | Nơi lưu file parts khi parser spool ra disk |
| `spring.webflux.multipart.headers-charset` | Charset để decode part headers |

Các defaults Boot 3.5 đáng chú ý: `max-in-memory-size` thường **256KB**; `max-disk-usage-per-part` và `max-parts` mặc định **-1** (không áp limit tương ứng), nên phải quyết định chính sách production phù hợp. Một số trường hợp stream multipart qua `PartEvent` có behavior khác parser dùng aggregated `Part`; đừng áp tất cả properties mà mặc định chúng giới hạn như nhau.

**Đây không phải chống malware hay phân quyền.** Multipart parser chỉ đọc cấu trúc tệp; ứng dụng vẫn cần allowlist định dạng, kiểm tra nội dung, quota/tần suất, storage quyền riêng, scanning/CDR nếu cần, auth và cleanup.

### 11.1. `FilePart.transferTo(...)`

Một controller reactive có thể nhận file part và chuyển nó sang path do server tạo:

```java
@PostMapping(path = "/files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> save(@RequestPart("file") FilePart file) {
    Path safeDestination = ...; // Server-generated & private.
    return file.transferTo(safeDestination);
}
```

**Đây là fragment**, không phải runnable method độc lập: `safeDestination` phải được tạo trong service với quyền, quota, collision/cleanup policy. Không dùng `file.filename()` làm path; đây là tên do client điều khiển. `FilePart.transferTo` trả `Mono<Void>`; để WebFlux subscribe, **trả Mono** thay vì gọi `subscribe()` bên trong controller.

### 11.2. `PartEvent` để stream multipart theo part

Spring WebFlux 6.2 hỗ trợ `@RequestBody Flux<PartEvent>`. Mỗi part có thể tạo nhiều events; `PartEvent.isLast()` đánh dấu event cuối part. Một mẫu tổ chức:

```java
Flux<PartEvent> events = ...;

Flux<Flux<PartEvent>> byPart =
        events.windowUntil(PartEvent::isLast);
```

Đây là fragment; mỗi inner flux cần được **consume, relay hoặc release** hoàn toàn, đặc biệt nếu các `DataBuffer` chứa pooled memory. Nếu xử lý file content tự viết với `PartEvent.content()`, phải có ownership contract: khi bỏ content, release buffer; khi chuyển downstream, tránh double-release.

**Không đồng nhất `PartEvent` với `Flux<FilePart>`**. PartEvent giúp streaming data theo events, còn `FilePart` thường là abstraction cho part đã được parser quản lý, có thể dùng disk spool.

## 12. Cấu hình không thay thế giới hạn tổng HTTP request

Giả sử API chấp nhận:

```http
POST /api/items.ndjson HTTP/1.1
Content-Type: application/x-ndjson

{"id":1,"name":"A"}
{"id":2,"name":"B"}
...
```

Nếu mỗi line nhỏ và decoder phát object từng dòng, **tổng request 2 GB** vẫn có thể đi qua codec limit 8KB theo từng item, miễn các layers khác cho phép. Điều này có thể không an toàn với tài nguyên hệ thống.

Để đặt tổng tối đa 1 MiB cần:

1. Gateway/load balancer policy về request body size và connection limits.
2. HTTP server settings tương thích Reactor Netty / underlying server.
3. **Per-request byte counting** ở stream khi cần, với cancel/cleanup khi vượt ngưỡng.
4. Application quota theo user/tenant, multipart total-size/file count limits.
5. Timeout/slow upload defenses, concurrency limits, disk quotas.
6. Không giữ infinite streams hoặc vô hạn buffered items.

### 12.1. Tự giới hạn số bytes trong Flux<DataBuffer>

Phác thảo fragment giới hạn tổng inbound bytes:

```java
AtomicLong total = new AtomicLong();

Flux<DataBuffer> limited = request.getBody()
        .handle((buffer, sink) -> {
            long length = buffer.readableByteCount();
            long now = total.addAndGet(length);
            if (now > MAX_TOTAL_BYTES) {
                DataBufferUtils.release(buffer);
                sink.error(new PayloadTooLargeException());
            } else {
                sink.next(buffer);
            }
        });
```

Đây **chỉ là fragment minh họa**: `request`, `MAX_TOTAL_BYTES`, `PayloadTooLargeException`, imports, ownership của buffers và xử lý cancel/error phải được xác định trong app thật. Dùng `AtomicLong` để xử lý số cộng và overflow theo policy (giới hạn max thực tế, tránh long overflow), không reuse state across requests. Một khi `sink.next(buffer)`, downstream nhận ownership theo contract; không tự release buffer sau khi chuyển. Trong functional WebFlux, có thể decorate `ServerHttpRequest`/WebFilter để đếm bytes, nhưng phải giữ backpressure, giải phóng buffer đúng và tránh hai consumers đọc body.

Đối với phần lớn ứng dụng, **proxy/gateway request body cap** đơn giản và đáng tin hơn tự viết một global filter đọc lại body. Nếu cần limit sau khi parse, kiểm tra cả metadata và source stream.

## 13. Chạy demo Spring Boot 3.5 WebFlux / Java 17

Ví dụ tối giản nhưng tách rõ từng codec behavior:

- `POST /api/echo` đọc một JSON object và trả một JSON object.
- `GET /api/items.ndjson` xuất ba JSON records theo dạng NDJSON.
- `POST /api/summary` nhận NDJSON `Flux<Item>` và chỉ giữ **count + sum IDs**, không collect toàn bộ records.
- Codec memory limit cho demo đặt **8KB** để kiểm thử ranh giới.
- Unit test trực tiếp `DataBufferUtils.join(maxByteCount)` và HTTP test qua WebTestClient.

Không có DB, upload, auth hay production rate limiting; code **để học codec behavior**, không dùng trực tiếp cho public service.

### 13.1. Build dependencies

Dự án được tạo từ Spring Initializr với **Spring Boot 3.5.x**, Java **17**, dependency **Spring Reactive Web**. Với Gradle project đã có Boot plugin, repositories, BOM và toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **fragment `build.gradle`**, không phải file Gradle build độc lập. Không thêm `spring-boot-starter-web` vào demo này: khi MVC và WebFlux cùng hiện diện, Boot 3.x thường chọn MVC web application type mặc định, làm kết quả lệch mục tiêu.

### 13.2. Properties

Tạo `src/main/resources/application.properties`:

```properties
# Spring Boot 3.5 namespace; 8KB để dễ quan sát decoder limit.
spring.http.codecs.max-in-memory-size=8KB

# Không chủ động log raw HTTP request details:
spring.http.codecs.log-request-details=false
```

Property log request details được Boot 3.5 metadata công bố; `false` là default thông dụng. Không có nghĩa gateway, APM hoặc code khác sẽ tự masking nếu chúng log payload.

### 13.3. Java application

Tạo **`src/main/java/demo/codec/CodecDemoApplication.java`**:

```java
package demo.codec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class CodecDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CodecDemoApplication.class, args);
    }
}

record EchoInput(String message) {}

record EchoOutput(String message, int length) {}

record Item(int id, String name) {}

record Summary(long count, long sumIds) {}

@RestController
@RequestMapping("/api")
class CodecDemoController {

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<EchoOutput> echo(@RequestBody Mono<EchoInput> incoming) {
        return incoming.map(body -> {
            if (body.message() == null
                    || body.message().isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "message must not be blank");
            }

            String text = body.message().strip();
            return new EchoOutput(text, text.length());
        });
    }

    @GetMapping(
            path = "/items.ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<Item> itemsNdjson() {
        return Flux.range(1, 3)
                .map(id -> new Item(id, "item-" + id));
    }

    @PostMapping(
            path = "/summary",
            consumes = MediaType.APPLICATION_NDJSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<Summary> summary(@RequestBody Flux<Item> items) {
        return items.reduce(
                new Summary(0L, 0L),
                (acc, item) -> new Summary(
                        acc.count() + 1,
                        acc.sumIds() + item.id()));
    }
}
```

Mã dùng Java 17 **records**, `Flux`/`Mono` và WebFlux annotation controllers. Chỉ class `CodecDemoApplication` là public; các records và controller cùng package được component scan. Jackson từ `starter-webflux` có thể encode/decode Java records.

#### Điều cần đọc kỹ trong code

- `echo(...)` dùng **`Mono<EchoInput>`**: reader tạo **một object**. Limit 8KB có thể chặn request JSON quá lớn trong decode trước khi vào `map`.
- `itemsNdjson()` trả **`Flux<Item>`** cùng `produces=application/x-ndjson`: writer có thể encode ba object theo line framing.
- `summary(...)` dùng `@RequestBody Flux<Item>`: reader decode mỗi NDJSON record; `reduce` giữ đúng **hai số**, không tạo list tăng dần. Nhưng nếu client gửi vô hạn record, CPU/network vẫn hoạt động vô hạn; **codec limit không thay request size/time/count quota**.
- `Summary.count` và `sumIds` có thể overflow `long` nếu source cực kỳ lớn hoặc ID không tin cậy. Production cần range check/limit count/checked arithmetic nếu business đòi chính xác.
- Body JSON không hợp lệ thường dẫn đến error từ reader; body hợp lệ nhưng business invalid trả `400` như trong code. Đừng kết luận mọi `DataBufferLimitException` sẽ tự biến thành 413 nếu chưa có error policy.
- Không gọi `subscribe()` hoặc `block()` trong controller; WebFlux HTTP adapter tự subscribe và quản lý lifecycle.

### 13.4. Chạy HTTP

```bash
./gradlew bootRun
```

Request nhỏ:

```bash
curl -i -X POST 'http://localhost:8080/api/echo' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"message":"Hello WebFlux"}'
```

Response dự kiến:

```json
{"message":"Hello WebFlux","length":13}
```

`Hello` = 5, một space = 1, `WebFlux` = 7 nên length = **13** theo Java String length với toàn ký tự ASCII của ví dụ. Nếu thêm Unicode supplementary characters, `String#length()` đếm **UTF-16 code units**, không phải số grapheme/user-perceived characters; ví dụ cố ý ASCII để output có thể xác minh.

GET NDJSON:

```bash
curl -N -i \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/items.ndjson'
```

Body dự kiến:

```text
{"id":1,"name":"item-1"}
{"id":2,"name":"item-2"}
{"id":3,"name":"item-3"}
```

POST NDJSON:

```bash
printf '%s\n' \
  '{"id":1,"name":"A"}' \
  '{"id":2,"name":"B"}' \
  '{"id":3,"name":"C"}' \
  | curl -i -X POST 'http://localhost:8080/api/summary' \
      -H 'Content-Type: application/x-ndjson' \
      -H 'Accept: application/json' \
      --data-binary @-
```

Body dự kiến:

```json
{"count":3,"sumIds":6}
```

Các response trên là **kết quả dự kiến nếu đúng project/baseline và input**; chưa phải output của một lần chạy thực tế.

### 13.5. Kiểm tra payload vượt limit

Với `spring.http.codecs.max-in-memory-size=8KB`, thử gửi một `message` dài hơn 10.000 ký tự ASCII trong **một JSON object**:

```bash
# Ví dụ tạo payload bằng Python tại terminal ngoài ứng dụng:
python -c "import json; print(json.dumps({'message':'A'*10000}))" \
  | curl -i -X POST 'http://localhost:8080/api/echo' \
      -H 'Content-Type: application/json' \
      --data-binary @-
```

Kỳ vọng **decode vượt limit**; HTTP status và body lỗi chính xác còn phụ thuộc exception translation của phiên bản/config. **Không cố gắng khẳng định mặc định luôn 413**, và không log payload 10.000 bytes trong môi trường có dữ liệu nhạy cảm.

Với NDJSON, có thể stream hàng trăm dòng 100 bytes; tổng request lớn hơn 8KB nhưng từng record nằm trong giới hạn, tùy những giới hạn khác. Nếu một dòng chứa 20KB text thì decoder có thể báo `DataBufferLimitException` cho **dòng đó**.

## 14. Tests có kiểm chứng: HTTP codecs và giới hạn bộ đệm

Tạo **`src/test/java/demo/codec/CodecDemoApplicationTests.java`**:

```java
package demo.codec;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CodecDemoApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void echoesSmallJsonWithJacksonCodec() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue("""
                    {"message":"Hello WebFlux"}
                    """)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello WebFlux")
                .jsonPath("$.length").isEqualTo(13);
    }

    @Test
    void emitsThreeNdjsonRecords() {
        Flux<Item> items = client.get()
                .uri("/api/items.ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_NDJSON)
                .returnResult(Item.class)
                .getResponseBody();

        StepVerifier.create(items)
                .expectNext(new Item(1, "item-1"))
                .expectNext(new Item(2, "item-2"))
                .expectNext(new Item(3, "item-3"))
                .verifyComplete();
    }

    @Test
    void limitedJoinRejectsExcessBytes() {
        DefaultDataBufferFactory factory =
                new DefaultDataBufferFactory();

        Flux<DataBuffer> tooLarge = Flux.just(
                factory.wrap(new byte[8193]));

        StepVerifier.create(
                DataBufferUtils.join(tooLarge, 8192))
                .expectError(DataBufferLimitException.class)
                .verify();
    }

    @Test
    void limitedJoinCanCombineAllowedBytes() {
        DefaultDataBufferFactory factory =
                new DefaultDataBufferFactory();

        Flux<DataBuffer> parts = Flux.just(
                factory.wrap("ab".getBytes(
                        StandardCharsets.UTF_8)),
                factory.wrap("cd".getBytes(
                        StandardCharsets.UTF_8)));

        StepVerifier.create(DataBufferUtils.join(parts, 8))
                .assertNext(buffer -> {
                    try {
                        byte[] bytes = new byte[
                                buffer.readableByteCount()];
                        buffer.read(bytes);
                        assertEquals(
                                "abcd",
                                new String(bytes,
                                        StandardCharsets.UTF_8));
                    } finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .verifyComplete();
    }
}
```

Chạy:

```bash
./gradlew test
```

Bốn tests được **thiết kế để pass** trên baseline Java17/Boot3.5/WebFlux; **chưa chạy Gradle trong tài liệu này**. Test HTTP dùng `RANDOM_PORT` để chạy qua WebFlux HTTP stack thay vì chỉ unit-call controller. Test `limitedJoinRejectsExcessBytes` kiểm tra **hợp đồng chính xác** của `DataBufferUtils.join(source,maxBytes)`: buffer 8193 > limit 8192, phát `DataBufferLimitException`; test thành công đọc đủ 4 bytes và release buffer sở hữu.

**Giới hạn của tests:** hai test `join` minh họa **DataBufferUtils guard**, không khẳng định toàn bộ Boot decoder limit được cấu hình đúng. Để kiểm chứng hiệu lực property 8KB qua HTTP, bổ sung một HTTP test gửi một JSON object >8KB và xác nhận lỗi decode; khi muốn assert **413**, phải xây error-handling contract của application và test nó, không phụ thuộc mặc định không được kiểm chứng.

## 15. Thiết kế HTTP status khi vượt bộ đệm

Một API public nên xác định semantics cho payload quá lớn:

| Tình huống | Status thường phù hợp | Cần lưu ý |
| --- | --- | --- |
| JSON body vượt kích thước cho phép theo API | `413 Content Too Large` | Có thể chặn tại proxy trước khi tới codec |
| Form/file part vượt quota | `413 Content Too Large` | Trường hợp disk/part count có exception riêng |
| JSON syntax sai | `400 Bad Request` | Không phải vấn đề quota |
| Media type không hỗ trợ | `415 Unsupported Media Type` | Reader selection khác với byte limit |
| Response `Accept` không đáp ứng | `406 Not Acceptable` | Writer content negotiation |
| Business validation fail | `400`/`422` theo contract | Không phải DataBufferLimitException |
| Authentication thiếu | `401 Unauthorized` | Không phải codec |
| Không đủ quyền upload/download | `403 Forbidden` | Không phải codec |
| Server heap thực sự cạn | Sự cố hệ thống, không đơn thuần 413 | Không dựa vào exception mapper để cứu OOM |

Có thể ánh xạ `DataBufferLimitException` thành 413 trong một `@RestControllerAdvice` / `WebExceptionHandler` có scope phù hợp. Nhưng lỗi có thể bị **wrap** bởi reader/decoder hoặc xảy ra **sau khi response committed**, và có thể đến từ **WebClient outbound** hoặc một internal aggregate, không luôn là request quá lớn của client. Khi xử lý, cần phân loại nguyên nhân trước, tránh biến mọi internal buffering error thành HTTP 413 “client sai”.

**Không in raw exception/toString body ra client**, nhất là nếu thông báo chứa request content, parser details hoặc paths. Có error code ổn định như `PAYLOAD_TOO_LARGE` và message public ngắn gọn, log kỹ thuật theo privacy policy.

## 16. Reader, writer và content negotiation

HTTP codecs được chọn theo cả **kiểu Java** và **MediaType**:

- Inbound: `Content-Type` khai loại body để reader decode.
- Outbound: `Accept` khai format client muốn nhận, còn `produces` và available writers quyết định kiểu đáp ứng.
- `Content-Encoding` như gzip/br là một tầng khác; không nhầm nó với media type `application/json`.
- Charset quan trọng với text codecs, nhưng JSON phổ biến dùng UTF-8 theo các quy tắc HTTP/JSON tương ứng.
- Generic type parameters quan trọng: `List<Item>` và raw `List.class` có thông tin khác, ảnh hưởng decode element types.
- Classpath quyết định có Jackson JSON, JAXB/XML, Protobuf hoặc codecs optional; thiếu dependency có thể gây unsupported media type/codec selection failures.
- HTTP codecs không tự bảo vệ khỏi unsafe deserialization business types nếu ObjectMapper được cấu hình mở polymorphic typing tùy tiện. Chỉ bật loại typing đã đánh giá kỹ và cập nhật dependencies.

### 16.1. `Mono<List<T>>` khác `Flux<T>`

```java
Mono<List<Item>> a = ...;
Flux<Item> b = ...;
```

Nếu source thực sự là list lớn, `Mono<List<Item>>` đã aggregate vào heap trước khi writer nhìn thấy. Trong khi `Flux<Item>` có thể giữ stream, nhưng nếu media type là `application/json` writer có thể có behavior khác NDJSON/SSE. Để kiểm soát memory, cần xét **producer, operator và codec**, không chỉ kiểu return.

### 16.2. String, byte[] và Resource

`Mono<String>` hoặc `Mono<byte[]>` thường đại diện một body hoàn chỉnh; khi decode những dạng này từ network response, codec có thể gom bytes trước. Với `Flux<DataBuffer>` raw response streaming, memory use có thể thấp hơn nhưng ownership/release rủi ro cao hơn.

Khi file có trên disk, **`Resource`** và HTTP range/conditional support có thể phù hợp hơn tự viết `Mono<byte[]>` cho file lớn. Không copy toàn bộ file vào heap vì muốn trả download 200.

## 17. Khi thực sự cần custom codec

Chỉ viết codec riêng khi có **wire representation không được built-in codecs xử lý hợp lý**, ví dụ binary event format nội bộ có framing cụ thể. Nếu chỉ muốn đổi tên JSON field, annotation/Jackson module là đủ.

Một custom `Decoder<CustomPacket>` phải quan tâm:

1. **`canDecode(ResolvableType, MimeType)`** thật sự match type/media type.
2. Decode `Flux<DataBuffer>` một cách **backpressure-aware**.
3. Có framing rõ: length-prefix, delimiter hoặc self-delimiting format.
4. Enforce max frame/object bytes trước khi cấp phát dữ liệu lớn.
5. Cẩn thận partial frame ở ranh giới giữa hai DataBuffers.
6. Xử lý UTF-8 split chars nếu frame là text; không decode từng chunk như chuỗi độc lập rồi ghép tùy tiện.
7. Release buffers đã consume, discard và lỗi/cancel; không double release.
8. Reject invalid/truncated/oversized messages một cách có kiểm soát.
9. Không tạo blocking read hoặc `block()` trên Netty event loop.
10. Có tests phân mảnh bytes ở mọi vị trí và fuzz malformed frames.
11. Đăng ký reader/writer theo thứ tự sao cho không che built-in codec cho các media types chung.
12. Cấu hình limit/metrics theo chính codec đó, không giả định defaultCodecs.maxInMemorySize tự điều khiển một custom codec không hỗ trợ limit.

### 17.1. Adapter lớp thấp và lớp HTTP

Framework có:

```java
DecoderHttpMessageReader<MyType> reader =
        new DecoderHttpMessageReader<>(myDecoder);

EncoderHttpMessageWriter<MyType> writer =
        new EncoderHttpMessageWriter<>(myEncoder);
```

Đây là **fragment** giả định `myDecoder`/`myEncoder` là implementations có interface/generics hợp lệ. Reader/writer sẽ hiểu HTTP headers/media type ngoài semantics bytes của encoder/decoder. Đăng ký với `ServerCodecConfigurer.customCodecs()` bằng API tương ứng; xem Javadoc version cụ thể vì custom codec registration có overload khác nhau giữa release series.

Không ghi source custom codec 20 dòng và khẳng định production-safe. Binary framing, buffer release, streams vô hạn, byte limits và malformed data cần test sâu hơn code mẫu.

## 18. Byte memory vs heap vs direct memory vs disk

| Tầng tài nguyên | Ví dụ | Ai phải giới hạn |
| --- | --- | --- |
| Java heap | Decoded DTOs, Strings, Lists, cached objects | JVM sizing, business quotas, bounded operators |
| Direct/native memory | Netty ByteBuf/pooled DataBuffer | Netty allocator, buffer lifecycle, runtime metrics |
| Codec aggregate memory | JSON object/string/form parsing | `maxInMemorySize` của codec tương ứng |
| Operator queues | `flatMap` prefetch, `buffer`, `collectList` | Reactor policies, concurrency/backpressure |
| Multipart temporary disk | FilePart spool directory | WebFlux multipart limits, disk quotas, cleanup |
| Persistent storage | Object store, DB/file uploads | Business quotas/retention/permissions |
| Gateway buffers | NGINX/CDN buffering | Proxy request/response size and buffering policy |
| Client heap | `WebClient.bodyToMono`, browser JSON parse | Client codecs, application and browser limits |

Một application có codec limit 256KB vẫn có thể dùng 10GB heap qua `collectList()` hoặc nhiều concurrent requests. Ngược lại, nâng codec limit lên 10MB không tự làm heap tăng 10MB cho mọi request; mức sử dụng còn phụ thuộc concurrency, payload size, decoder và connection behavior.

**Chiến lược chọn ngưỡng:**

- Đo P50/P95/P99 size cho từng endpoint, cộng biên hợp lý.
- Dùng DTO/schema validation và size quotas theo nghiệp vụ.
- Tách endpoint stream/bulk import khỏi endpoint JSON nhỏ.
- Định mức concurrent requests × peak buffered bytes cùng các buffers/decoded object overhead.
- Kiểm tra upload cả RAM và disk, không xem multipart limit như một số.
- Test slow clients và nhiều requests đồng thời trước khi tăng global default.
- Thử chaos/overflow/large nested JSON để xác định failure modes.
- Theo dõi memory và status errors sau rollout; đừng thay property trên production mà chưa biết side effects.

## 19. Multipart, SSE, NDJSON và backpressure: mối liên hệ

Backpressure trong Reactive Streams đo **nhu cầu theo phần tử**, còn codec limit đo **bytes tích lũy khi decode một đơn vị**. Hai cơ chế bổ sung nhưng **không thay thế nhau**.

Ví dụ:

```text
Client gửi NDJSON 100MB
  gồm 100.000 dòng, mỗi dòng 1KB

Codec maxInMemorySize=8KB
  => mỗi record có thể được decode riêng

Reactive downstream request(n)
  => hướng dẫn tốc độ xử lý item

Application collectList()
  => vẫn có thể tích toàn bộ records 100MB+ vào heap

Gateway maxBodySize=10MB
  => có thể chặn request trước khi đủ 100MB

Kết luận:
  Bốn giới hạn/cơ chế khác nhau
```

Với SSE, một event có nhiều dòng `data:` và event delimiter; decoder có thể tích lũy cho đến khi event hoàn chỉnh. Nếu event quá lớn, codec limit có thể gây error, dù mỗi network chunk nhỏ.

Với multipart, `FilePart` có thể spool data sang disk ngay khi vượt ngưỡng, nên tổng file lớn hơn `max-in-memory-size` mà không nhất thiết là `DataBufferLimitException`. Tuy nhiên nếu không giới hạn disk usage per part, part count và concurrency thì kẻ tấn công vẫn có thể làm đầy ổ đĩa.

## 20. Lỗi điển hình và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `DataBufferLimitException: Exceeded limit...` khi POST JSON | Một object/body aggregate vượt limit | Kiểm tra kích thước bytes thật, Boot property và decoder |
| Request JSON nhỏ pass, JSON có field rất dài fail | Per-object buffer limit | Validation max field length; cân nhắc 413 có contract |
| WebClient fail khi origin trả 200 | Client decoder limit nhỏ hơn response | Kiểm tra `WebClient.Builder.codecs` |
| Property không có hiệu lực | Dùng tên của Boot version cũ | Với Boot 3.5 dùng `spring.http.codecs.max-in-memory-size` |
| WebFlux custom codec vẫn nhận payload quá lớn | Custom codec không obey default limit | Thêm explicit max frame/object size |
| App memory tăng dù limit 8KB | `collectList`, operator buffer/queue, nhiều concurrent requests | Heap profiler + Reactor/Netty metrics |
| Direct memory OOM | Pooled DataBuffer không được release hoặc Netty buffer pressure | Kiểm tra retain/release và allocator metrics |
| Multipart upload vượt 256KB vẫn thành công | 256KB là ngưỡng RAM→disk, không phải upload max | `spring.webflux.multipart.max-disk-usage-per-part` và total body policy |
| Disk đầy vì multipart | Max-disk-usage default unbounded hoặc cleanup sai | Cấu hình quota, spool directory, retention |
| NDJSON stream 100MB không bị 8KB chặn | Mỗi record nhỏ hơn limit | Bổ sung total byte limit/timeout/count limit |
| Một NDJSON record lớn bị lỗi giữa stream | Buffering giữa delimiters quá lớn | Giới hạn record, client split data đúng |
| SSE event lớn khiến client decoder fail | Tích lũy event vượt limit | Event size limit, chunk domain data hợp lý |
| `HTTP 415` dù JSON hợp lệ | Content-Type không được reader hỗ trợ | Kiểm tra media type và dependencies |
| `HTTP 406` khi client yêu cầu YAML | Không có writer cho Accept type | Cấu hình produces hoặc bổ sung codec thích hợp |
| Unicode text bị lỗi | Charset/decoder hoặc split bytes sai | Sử dụng codec xử lý UTF-8 chuẩn |
| Request body rỗng làm Mono.empty | Client không gửi body, handler chưa có default | Quy định contract required body/validation |
| Test chỉ assert 500 khi oversized | Exception mapping không ổn định/không rõ | Test DataBufferLimitException trực tiếp và HTTP policy riêng |
| Netty event loop block | Custom codec/handler gọi `block()` hoặc blocking I/O | Dùng non-blocking APIs hoặc isolate boundedElastic |
| Form details bị lộ trong DEBUG | Bật raw request detail logging | Giữ `spring.http.codecs.log-request-details=false`, redaction toàn tầng |

### Quy trình debug ngắn

1. Xác nhận runtime là WebFlux (không bị `starter-web` đưa thành MVC).
2. Xem request `Content-Type`, expected Java type và serialization format.
3. Xem exception **server hay WebClient**, trước hay sau controller.
4. Kiểm tra property **Boot 3.5 namespace** và WebFluxConfigurer/ClientCodecConfigurer customization.
5. Kiểm tra aggregation xảy ra ở codec hay ở `collectList/join/reduce` trong service.
6. Kiểm tra media type streaming như NDJSON/SSE và kích thước một record.
7. Nếu multipart, kiểm tra settings **riêng** và disk metrics.
8. Với custom DataBuffer access, audit release/retain.
9. Tái hiện bằng payload gần threshold và load test concurrent requests.
10. Đưa response lỗi có status, error code và retry policy phù hợp.

## 21. Test boundary và những điều cần đo thật

Một bộ test có giá trị nên gồm ba tầng:

### A. Unit-level codec/buffer

- `DataBufferUtils.join` với bytes ngay dưới/đúng/bên trên limit.
- `StepVerifier` kiểm tra `DataBufferLimitException`.
- Test release buffers khi normal/error/cancel.
- Nếu custom Decoder, test dữ liệu được split giữa mọi byte positions, malformed UTF-8/JSON, trailing bytes và memory leaks.

### B. WebFlux HTTP integration

- `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` để đi qua Reactor Netty/codec thật.
- Gửi JSON nhỏ đúng type và kiểm tra deserialize/serialize.
- Gửi một JSON object vượt limit, quan sát HTTP error path thực.
- Gửi NDJSON nhiều records nhỏ tổng lớn hơn limit, xác minh từng record đến.
- Gửi một NDJSON record vượt limit, xác minh error/cancel.
- Gửi Accept/Content-Type mismatch để xem 406/415 contract.
- Kiểm tra client codec limit khi downstream WebClient đọc response lớn.

### C. Staging qua gateway/production topology

- Payload vượt tổng ingress body limit; xác nhận bị chặn trước app.
- Multipart nhiều parts, lớn hơn disk usage quota, ngắt giữa upload.
- Pooled buffers/Netty direct memory/GC/concurrency dưới load.
- Test slow client/sender, cancellation và streaming flush latency.
- Reverse proxy buffering, compression và HTTP/2→HTTP/1.1 translation.
- Kiểm tra không lưu raw body, passwords hoặc file bytes trong logs/APM.
- Quan sát HTTP 413/4xx/5xx và error recovery.

**Đừng lấy một test StepVerifier thuần làm bằng chứng** rằng Boot property đã được bind, hay một HTTP test success làm bằng chứng rằng pooled buffers không leak. Mỗi tầng kiểm tra một giả thuyết khác nhau.

## 22. Lưu ý bảo mật cho dữ liệu đi qua codec

- Parser JSON/XML có thể đối diện input bất thường, deeply nested data hoặc resource-exhaustion payloads; giữ dependencies cập nhật và validation schema/depth/size.
- Không bật polymorphic deserialization/default typing không kiểm soát cho dữ liệu client.
- Không log raw HTTP body, Authorization, cookies, access tokens, multipart parts hoặc signed URLs.
- Cấu hình `spring.http.codecs.log-request-details=false` chỉ liên quan những log qua codec config; gateway/Netty access logs/APM cần redaction riêng.
- Khi custom codec trả lỗi, không đưa stack traces/parser internals vào response.
- Upload format allowlist, anti-malware/quarantine/storage isolation là việc của nghiệp vụ, không của codec.
- Với XML, lưu ý XXE/entity expansion policy của XML parser nếu bật XML codec; đừng tự thêm parser không an toàn.
- Multipart filename, Content-Type của part, JSON field data đều do client đưa; không dùng làm filesystem path hoặc trusted host.
- DataBuffer không tự mã hóa, ký chữ ký hoặc kiểm tra integrity; cần HTTPS, auth và application-level integrity khi hợp đồng yêu cầu.
- `DataBufferLimitException` giúp chống một kiểu tăng memory nhưng không bảo vệ khỏi flood nhiều requests nhỏ; dùng ingress rate/concurrency limits.

## 23. So sánh giữa Spring Framework/Boot versions

| Thế hệ | Điểm khác biệt đáng chú ý |
| --- | --- |
| Spring Framework 5.x / Boot 2.x | WebFlux codecs đã có; namespace Boot codec settings có thể khác bản mới; phải xem đúng reference |
| Spring Framework 6.2 / Boot 3.5 | Java 17+, Jakarta APIs; WebFlux `ServerCodecConfigurer`; Boot property **`spring.http.codecs.max-in-memory-size`** |
| Spring Framework 7.x / Boot 4.x | Core concepts reader/writer/encoder/decoder còn, nhưng codec classes (đặc biệt JSON), Boot starters/modules và config properties có thể đổi; kiểm tra migration docs của exact version |

**Không chép nguyên** `spring.codec.max-in-memory-size` từ tutorial Boot 2/đầu Boot 3 rồi coi chắc chắn hiệu lực trên Boot 3.5. Cũng không nhầm `spring.servlet.multipart.*` của Servlet MVC với **`spring.webflux.multipart.*`** trong reactive stack.

Khi chuyển WebFlux sang MVC hoặc ngược lại, ngoài annotations/controller code còn phải đổi **HTTP serialization infrastructure, validation/error handling, multipart parsing, response streaming và test setup**. Reactor `Flux` có thể xuất hiện trong Spring MVC trong vài return types, nhưng MVC servlet response writing không cùng contract với WebFlux reactive readers/writers.

## 24. Checklist vận hành production

- [ ] Xác nhận app thật chạy WebFlux, không vô tình chạy MVC vì dependency trùng.
- [ ] Có media types/DTO contracts cho inbound và outbound.
- [ ] Dùng property đúng Spring Boot 3.5: `spring.http.codecs.max-in-memory-size`.
- [ ] Đã xác định default (~256KiB với nhiều codecs) và config hiệu dụng bằng test.
- [ ] Không tăng global limit chỉ để chữa một endpoint thiết kế body quá lớn.
- [ ] Endpoint cần stream dùng NDJSON/SSE/Flux phù hợp, không aggregate toàn bộ.
- [ ] Có record/event size cap, total HTTP payload cap, timeout và quota.
- [ ] WebClient được config riêng nếu cần limit khác server; tránh `WebClient.create()` bypass customizations.
- [ ] Multipart có RAM/disk/part/header limits và storage cleanup.
- [ ] Không dùng originalFilename làm đường dẫn; kiểm soát validation và scan.
- [ ] Không giữ buffers thô vô hạn, pooled buffers được release/relay đúng.
- [ ] Không có `collectList/join` unbounded trên dữ liệu không tin cậy.
- [ ] Custom codec tuân thủ frame limit, media type và backpressure.
- [ ] Xử lý lỗi decoder/limit thành HTTP contract ổn định, không lộ stack traces.
- [ ] Có test với payload sát/ngay trên limit và nhiều request đồng thời.
- [ ] Có WebTestClient HTTP test và buffer unit tests riêng.
- [ ] Theo dõi heap, direct memory, Netty pending buffers, disk usage và 413/5xx rates.
- [ ] Gateway/proxy size limits, rate limits và timeouts đồng bộ với policy.
- [ ] Không log raw HTTP headers/form data/PII nếu không được phép.
- [ ] Migration Spring/Boot được rà soát theo dependency BOM và property metadata.

## 25. Bài tập tự đánh giá

1. Phân biệt `Decoder<T>` và `HttpMessageReader<T>`. Vì sao reader cần biết HTTP metadata?
2. `HttpMessageWriter` trên server làm gì và khi WebClient gửi request thì class tương tự đóng vai trò nào?
3. Tại sao `@RequestBody Mono<byte[]>` có thể vượt limit khi một HTTP request body lớn, dù các network chunks nhỏ?
4. Với NDJSON gồm 10.000 records × 100 bytes, codec limit 8KiB có giới hạn tổng 1MB không?
5. Một NDJSON record dài 16KiB nhưng mỗi TCP segment chỉ 1KiB. Vì sao vẫn có thể `DataBufferLimitException`?
6. Phân biệt `spring.http.codecs.max-in-memory-size` (Boot 3.5) với property trong tutorial Boot cũ.
7. Khi có một `WebFluxConfigurer` custom và Boot property khác nhau, làm sao xác minh limit hiệu dụng?
8. Vì sao `WebClient.create()` có thể không nhận auto-configured Boot customizations?
9. Tại sao server trả 200 với body 1MiB nhưng WebClient vẫn lỗi ở client-side decoder 256KiB?
10. Vì sao `WebClient.bodyToFlux(Item.class)` thường giúp stream, nhưng `collectList()` lại có thể gây OOM?
11. Với multipart, vì sao file có thể lớn hơn `max-in-memory-size` mà parser vẫn lưu được?
12. Tại sao maxDiskUsagePerPart, maxParts và gateway max request size là ba giới hạn khác nhau?
13. Khi tự đọc `Flux<DataBuffer>`, khi nào cần `DataBufferUtils.release`? Tại sao double-release nguy hiểm?
14. `DataBufferUtils.join(source, 8192)` phải làm gì nếu source có 8193 bytes? Test bằng StepVerifier.
15. Kiểm thử `DataBufferUtils.join` thành công: khi nhận combined buffer, ai chịu trách nhiệm release nếu tự tiêu thụ nó?
16. Một `Flux<Item>` response với `application/json` và `application/x-ndjson` khác nhau ra sao về framing?
17. Khi dữ liệu đã trả 200 + một vài NDJSON lines rồi decoder/producer gặp error, có thay HTTP status thành 413 không?
18. Nếu viết codec custom cho length-prefixed binary, làm sao xử lý một frame bị split qua nhiều DataBuffers?
19. Vì sao `spring.http.codecs.log-request-details=false` không bảo đảm proxy logs không chứa token?
20. Hãy thiết kế policy cho API nhập CSV 1GB nhưng mỗi record nhỏ: total-size quota, disk storage, streaming decoder, auth, retry, cancellation và validation.
21. Bạn sẽ đo metric nào để phân biệt codec aggregation pressure với memory leak do pooled Netty ByteBuf?
22. Khi server code gọi `collectList()` sau khi decoder đã tạo từng object, codec max-in-memory-size có bảo vệ bộ nhớ list đó không?
23. Với JSON nested array lớn, việc tăng limit toàn hệ thống có tác động ra sao tới peak memory khi 200 users upload đồng thời?
24. Khi chuyển Boot 3.5 sang Boot 4, tại sao cần kiểm tra chính xác codec classes, property metadata và tests thay vì chỉ copy snippets?

## 26. Tài liệu chính thức

- [Spring Framework 6.2 — Reactive Core, codecs và Limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): DataBuffer, HTTP codecs, memory limits, multipart và sensitive logging.
- [Spring Framework 6.2 — WebFlux Config / HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): `WebFluxConfigurer#configureHttpMessageCodecs`, `ServerCodecConfigurer`.
- [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): `HttpMessageReader`, Mono/Flux request bodies.
- [Spring Framework 6.2 — @ResponseBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html): `HttpMessageWriter` và reactive response.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.http.codecs.*` và `spring.webflux.multipart.*`.
- [Spring Boot 3.5 — HttpCodecsProperties Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/http/codec/HttpCodecsProperties.html): `@ConfigurationProperties("spring.http.codecs")`.
- [Spring Framework 6.2 — DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): `join`, `read`, `write` và buffer lifecycle.
- [Spring Framework 6.2 — DataBufferLimitException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferLimitException.html): lỗi vượt aggregation limit.
- [Spring Framework 6.2 — Multipart Content](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html): `FilePart`, `PartEvent` và resource ownership.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html): `WebClient.Builder.codecs`.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): HTTP reactive integration testing.
- [Spring Framework — HTTP Codecs API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/ServerCodecConfigurer.html): default codecs/custom codecs.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): signal/exception tests.
