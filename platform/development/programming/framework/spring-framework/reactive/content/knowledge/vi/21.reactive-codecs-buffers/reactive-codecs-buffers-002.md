# ServerCodecConfigurer, ClientCodecConfigurer và ExchangeStrategies trong Spring WebFlux

## 1. Mục tiêu

Spring WebFlux cần chuyển đổi dữ liệu giữa HTTP và các kiểu Java mà ứng dụng sử dụng. Khi client gửi JSON, form hoặc multipart, server phải đọc byte từ request và tạo object. Khi controller trả object, server phải serialize object thành response body. Ở chiều client, WebClient cũng cần encode request body và decode response body.

**Codec** là thành phần thực hiện chuyển đổi dữ liệu. Spring cung cấp các codec mặc định và các API cấu hình để ứng dụng bổ sung hoặc thay thế chúng:

- **ServerCodecConfigurer:** cấu hình HTTP message readers/writers ở phía WebFlux server.
- **ClientCodecConfigurer:** cấu hình HTTP message readers/writers ở phía HTTP client.
- **ExchangeStrategies:** tập chiến lược đọc/ghi HTTP mà WebClient sử dụng thông qua ExchangeFunction; nó chứa danh sách reader/writer đã cấu hình.

Ba thành phần có liên hệ với nhau nhưng không thay thế nhau. ServerCodecConfigurer dành cho server; ClientCodecConfigurer dành cho client; ExchangeStrategies là đối tượng đóng gói cấu hình codec ở phía WebClient.

Bài học đi từ luồng đọc/ghi, vai trò từng API, cách tùy chỉnh codec mặc định, đăng ký codec riêng, giới hạn bộ nhớ và quản lý DataBuffer. Ví dụ dùng Java 17+ và các API phổ biến của Spring Framework 6.2/7.0.

## 2. Codec, Encoder, Decoder, HttpMessageReader và HttpMessageWriter

Các abstraction nằm ở nhiều tầng:

| Thành phần | Trách nhiệm | Đầu vào | Đầu ra |
| --- | --- | --- | --- |
| Encoder | Mã hóa object thành byte buffers | Publisher của object | Publisher của DataBuffer |
| Decoder | Giải mã byte buffers thành object | Publisher của DataBuffer | Publisher của object |
| HttpMessageReader | Đọc nội dung HTTP thành kiểu Java | HTTP body, headers, target type | Publisher của object |
| HttpMessageWriter | Ghi kiểu Java thành nội dung HTTP | Publisher của object, headers | HTTP body |
| CodecConfigurer | Đăng ký reader/writer mặc định và tùy chỉnh | Cấu hình codec | Danh sách reader/writer |
| ExchangeStrategies | Đóng gói reader/writer cho WebClient | Client codec configuration | Strategy dùng bởi ExchangeFunction |

Encoder/Decoder là abstraction chuyển đổi dữ liệu độc lập với HTTP. HttpMessageReader/HttpMessageWriter bổ sung ngữ cảnh HTTP như Content-Type, MediaType, ResolvableType, headers và cách ghi body. Trong nhiều trường hợp, Spring bọc Encoder bằng EncoderHttpMessageWriter và Decoder bằng DecoderHttpMessageReader để dùng trong WebFlux.

Ví dụ request:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"id":"o-42","quantity":3}
```

Luồng xử lý phía server:

1. WebFlux chọn một HttpMessageReader tương thích với Content-Type và kiểu tham số của controller.
2. Reader lấy DataBuffer từ HTTP body.
3. Decoder, ví dụ Jackson JSON decoder, chuyển byte thành object Java.
4. Controller xử lý object và trả Mono hoặc Flux.
5. WebFlux chọn HttpMessageWriter tương thích với kiểu trả về và media type response.
6. Encoder chuyển object thành DataBuffer.
7. Server ghi các buffer xuống HTTP response theo cơ chế non-blocking.

Ở phía client, WebClient thực hiện chiều ngược lại: encoder ghi request body; decoder đọc response body.

## 3. Codec mặc định của Spring WebFlux

Spring cung cấp các codec cơ bản trong spring-core và các codec HTTP trong spring-web. Codec cụ thể được đăng ký phụ thuộc thư viện có trên classpath.

Nhóm hỗ trợ thường gặp:

| Dữ liệu | Codec/reader/writer thường dùng | Ghi chú |
| --- | --- | --- |
| String / CharSequence | StringEncoder, StringDecoder, CharSequenceEncoder | Text và chuỗi ký tự |
| byte[] | ByteArrayEncoder, ByteArrayDecoder | Dữ liệu nhị phân đã được gom vào mảng |
| ByteBuffer | ByteBufferEncoder, ByteBufferDecoder | Tương tác với Java NIO |
| DataBuffer | DataBufferEncoder, DataBufferDecoder | Làm việc trực tiếp với buffer |
| Resource | ResourceHttpMessageReader/Writer | Đọc/ghi file hoặc resource |
| JSON | Jackson JSON encoder/decoder | Có khi Jackson tương thích hiện diện |
| Smile | Jackson Smile encoder/decoder | Binary JSON của Jackson |
| XML | JAXB2 hoặc codec tương thích | Phụ thuộc thư viện JAXB |
| Protocol Buffers | Protobuf encoder/decoder | Phụ thuộc protobuf-java |
| Form URL encoded | FormHttpMessageReader/Writer | application/x-www-form-urlencoded |
| Multipart | MultipartHttpMessageReader/Writer | multipart/form-data và các dạng liên quan |
| Server-Sent Events | SSE reader/writer | text/event-stream |

Không phải mọi codec đều luôn có mặt. Ví dụ, Protobuf codec cần thư viện Protobuf; codec JSON cần Jackson hoặc một thư viện JSON tương thích. Spring Boot cũng điều chỉnh codec theo classpath và cấu hình Jackson của ứng dụng.

### 3.1. Jackson và JSON

Jackson decoder dùng parser không blocking để đọc luồng byte và tạo object. Với một JSON object đơn lẻ, decoder tạo một object. Với publisher nhiều giá trị, decoder có thể phát từng object khi đã nhận đủ byte để hoàn thành object đó, tùy định dạng streaming.

Ở phía encode:

- Với một Mono<T>, encoder serialize một object.
- Với Flux<T> và media type application/json, mặc định các phần tử được thu thập thành một danh sách rồi serialize thành JSON array.
- Với media type streaming như application/x-ndjson, encoder có thể encode, ghi và flush từng phần tử theo từng dòng.
- Với Server-Sent Events, JSON encoder được gọi cho từng event và output được flush để event được gửi kịp thời.

Một chi tiết dễ gây nhầm: Jackson JSON encoder/decoder mặc định không dùng String như một object JSON thông thường. Spring thường xem String hoặc chuỗi String là nội dung JSON đã serialize và dùng CharSequence codec. Nếu cần trả một JSON array từ Flux<String>, hãy collectList rồi encode Mono<List<String>>.

Ví dụ:

```java
@GetMapping(value = "/names", produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<List<String>> names() {
    return Flux.just("An", "Binh", "Chi")
            .collectList();
}
```

Response JSON:

```json
["An","Binh","Chi"]
```

Nếu trả Flux<String> trực tiếp với application/json, đừng mặc định rằng Spring sẽ tạo JSON array gồm các string. Chọn kiểu body và media type thể hiện đúng contract.

### 3.2. JSON streaming và NDJSON

Nếu muốn phát nhiều object theo từng dòng, dùng media type application/x-ndjson:

```java
@GetMapping(
        value = "/events",
        produces = "application/x-ndjson")
public Flux<OrderEvent> events() {
    return Flux.just(
            new OrderEvent("o-1", "CREATED"),
            new OrderEvent("o-2", "PAID"),
            new OrderEvent("o-3", "SHIPPED"));
}
```

Dữ liệu được encode thành từng JSON object, mỗi object trên một dòng:

```text
{"orderId":"o-1","status":"CREATED"}
{"orderId":"o-2","status":"PAID"}
{"orderId":"o-3","status":"SHIPPED"}
```

NDJSON phù hợp với xử lý từng record và backpressure. Nếu dùng application/json cho Flux, mặc định encoder thu thập thành collection; nếu dùng media type streaming, các phần tử có thể được ghi dần.

## 4. ServerCodecConfigurer: cấu hình codec phía server

ServerCodecConfigurer cung cấp các reader/writer mặc định cho WebFlux server. Nó được dùng trong annotated controllers, functional endpoints và các chức năng đọc form/multipart qua ServerWebExchange.

Cách mở rộng phổ biến là triển khai WebFluxConfigurer và override configureHttpMessageCodecs:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ServerCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(1024 * 1024);
    }
}
```

Đoạn cấu hình đặt giới hạn buffering cho các codec mặc định ở mức 1 MiB. Đây là ví dụ cấu hình server; không cần tạo ServerCodecConfigurer bằng tay trong một ứng dụng WebFlux bình thường vì framework quản lý nó.

### 4.1. defaultCodecs và customCodecs

CodecConfigurer có hai nhóm API chính:

- `defaultCodecs()`: tùy chỉnh hoặc thay thế codec mà Spring đã đăng ký mặc định.
- `customCodecs()`: thêm HttpMessageReader hoặc HttpMessageWriter mới.

Ví dụ thay đổi giới hạn bộ nhớ:

```java
configurer.defaultCodecs().maxInMemorySize(1024 * 1024);
```

Ví dụ đăng ký reader/writer tùy chỉnh:

```java
configurer.customCodecs().register(myDecoder);
configurer.customCodecs().register(myEncoder);
```

Ở đây myDecoder phải triển khai Decoder hoặc HttpMessageReader phù hợp; myEncoder phải triển khai Encoder hoặc HttpMessageWriter phù hợp. Đây là điểm mở rộng, không phải class có sẵn của Spring.

Nếu custom codec cần nhận các cấu hình mặc định như giới hạn buffering hoặc logging policy, có thể dùng:

```java
configurer.customCodecs()
        .registerWithDefaultConfig(myDecoder);
```

registerWithDefaultConfig cho phép codec tùy chỉnh nhận các giá trị cấu hình mặc định tương ứng. Nếu dùng register thông thường, codec riêng có thể cần tự quản lý các giới hạn hoặc tùy chọn mà codec mặc định đã hỗ trợ.

### 4.2. Không tắt default codecs một cách tùy tiện

Có thể gọi:

```java
configurer.registerDefaults(false);
```

Lệnh này tắt việc đăng ký reader/writer mặc định. Khi đó ứng dụng phải tự cung cấp đầy đủ codec cần thiết qua customCodecs. Nếu quên đăng ký JSON, String, byte[], form hoặc multipart reader/writer, các endpoint vốn hoạt động trước đó có thể không đọc/ghi được body.

Chỉ tắt defaults khi bạn thực sự muốn kiểm soát toàn bộ danh sách codec, hiểu các endpoint đang phụ thuộc codec nào và có test bao phủ. Trong ứng dụng thông thường, giữ defaults và bổ sung/customize là lựa chọn an toàn hơn.

### 4.3. Cấu hình Jackson

Spring Boot áp dụng các thuộc tính Jackson của ứng dụng vào codec tương ứng. Nếu cần cấu hình sâu hơn, có thể dùng Jackson-specific builder hoặc thay codec mặc định bằng encoder/decoder dùng ObjectMapper riêng.

Ví dụ dưới đây dành cho ứng dụng dùng Jackson 2.x:

```java
ObjectMapper mapper = Jackson2ObjectMapperBuilder.json()
        .modulesToInstall(new JavaTimeModule())
        .featuresToDisable(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

configurer.defaultCodecs().jackson2JsonDecoder(
        new Jackson2JsonDecoder(mapper));

configurer.defaultCodecs().jackson2JsonEncoder(
        new Jackson2JsonEncoder(mapper));
```

Cần các import Jackson và Spring tương ứng, gồm Jackson2ObjectMapperBuilder, Jackson2JsonDecoder, Jackson2JsonEncoder, ObjectMapper, JavaTimeModule và DeserializationFeature. Đoạn này minh họa việc thay Jackson 2 codec mặc định.

**Lưu ý phiên bản:** Spring Framework 6.x thường dùng các lớp Jackson2JsonEncoder/Decoder khi ứng dụng dùng Jackson 2. Spring Framework 7 hỗ trợ cả thế hệ Jackson 3 với các lớp JacksonJsonEncoder/Decoder. Chọn codec phù hợp với Jackson dependency thực tế và BOM của Spring Boot; không trộn Jackson 2 và Jackson 3 tùy tiện.

### 4.4. Spring Boot và @EnableWebFlux

Khi dùng Spring Boot, thông thường chỉ cần khai báo @Configuration implements WebFluxConfigurer. Không thêm @EnableWebFlux nếu bạn vẫn muốn Spring Boot giữ các tùy chỉnh auto-configuration của WebFlux.

@EnableWebFlux phù hợp khi muốn tự kiểm soát cấu hình WebFlux ở mức framework và chấp nhận thay thế một phần auto-configuration của Boot. Việc thêm annotation này chỉ để đổi maxInMemorySize thường không cần thiết.

Spring Boot còn có cơ chế CodecCustomizer và các property cấu hình codec. Tên property và package của CodecCustomizer có thể thay đổi theo thế hệ Boot; hãy dùng tài liệu đúng version đang chạy. Nếu đã có một WebFluxConfigurer, tránh tạo nhiều cấu hình mâu thuẫn cùng thay đổi một codec mà không hiểu thứ tự áp dụng.

## 5. ClientCodecConfigurer: cấu hình codec phía WebClient

ClientCodecConfigurer là CodecConfigurer dành cho HTTP client. Nó cung cấp reader/writer mặc định và các tùy chọn riêng cho client, bao gồm hỗ trợ multipart và SSE decoder.

Bạn thường không cần tự tạo ClientCodecConfigurer. WebClient.Builder cung cấp callback codecs để thay đổi cấu hình:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.test")
        .codecs(configurer -> {
            configurer.defaultCodecs()
                    .maxInMemorySize(2 * 1024 * 1024);
        })
        .build();
```

Đây là cách ngắn gọn để tăng giới hạn buffering cho codec mặc định của WebClient lên 2 MiB.

Các tùy chỉnh phía client ảnh hưởng đến:

- Body request mà WebClient encode trước khi gửi.
- Body response mà WebClient decode sau khi nhận.
- Multipart reader/writer của client.
- SSE decoder của client.
- Giới hạn buffering và tùy chọn logging của codec mặc định.

ServerCodecConfigurer không tự cấu hình WebClient. Nếu một ứng dụng vừa chạy WebFlux server vừa gọi dịch vụ ngoài bằng WebClient, hãy xác định rõ cấu hình codec cho từng phía.

## 6. ExchangeStrategies: tập chiến lược codec của WebClient

ExchangeStrategies là đối tượng đóng gói các HttpMessageReader và HttpMessageWriter mà một ExchangeFunction sử dụng. WebClient dựa vào ExchangeStrategies để encode request và decode response.

Các factory/builder quan trọng:

| API | Mục đích |
| --- | --- |
| `ExchangeStrategies.withDefaults()` | Lấy strategy mặc định |
| `ExchangeStrategies.builder()` | Tạo builder đã có cấu hình mặc định để bắt đầu tùy chỉnh |
| `ExchangeStrategies.empty()` | Tạo builder rỗng, không đăng ký defaults |
| `builder.codecs(...)` | Cấu hình ClientCodecConfigurer bên trong strategy |
| `builder.build()` | Tạo ExchangeStrategies |
| `strategies.mutate()` | Tạo builder mới dựa trên strategy hiện tại |

Ví dụ tạo strategy riêng:

```java
ExchangeStrategies strategies = ExchangeStrategies.builder()
        .codecs(configurer -> {
            configurer.defaultCodecs()
                    .maxInMemorySize(2 * 1024 * 1024);
        })
        .build();

WebClient client = WebClient.builder()
        .baseUrl("https://api.example.test")
        .exchangeStrategies(strategies)
        .build();
```

Ở đây ExchangeStrategies chứa codec defaults cùng giới hạn bộ nhớ mới. WebClient sử dụng strategy đó cho các request/response của client.

### 6.1. Khi nào dùng WebClient.Builder.codecs và khi nào dùng ExchangeStrategies?

Với phần lớn trường hợp, ưu tiên:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
        .build();
```

Cách này cho phép các thành phần khác cùng đóng góp cấu hình vào WebClient.Builder. Nó thường rõ ràng hơn việc tự tạo strategy rồi thay toàn bộ.

Dùng ExchangeStrategies khi:

- Muốn tạo một strategy độc lập và tái sử dụng.
- Muốn kiểm soát strategy ở cấp ExchangeFunction.
- Muốn chia sẻ cùng cấu hình reader/writer giữa nhiều WebClient.
- Muốn clone hoặc mutate một strategy có sẵn.
- Có nhu cầu kiểm soát rõ tập codec mà client sử dụng.

WebClient sau khi build là immutable. Nếu cần một client biến thể, có thể dùng client.mutate() để tạo builder mới, giữ cấu hình hiện có rồi bổ sung filter hoặc codec. Không sửa trực tiếp một WebClient đã build.

### 6.2. ClientCodecConfigurer bên trong ExchangeStrategies

Có thể khai báo rõ kiểu ClientCodecConfigurer để người đọc thấy ranh giới cấu hình:

```java
ExchangeStrategies strategies = ExchangeStrategies.builder()
        .codecs((ClientCodecConfigurer configurer) -> {
            configurer.defaultCodecs()
                    .maxInMemorySize(1024 * 1024);
        })
        .build();
```

ClientCodecConfigurer cung cấp defaultCodecs/customCodecs giống CodecConfigurer chung. Điểm khác là nó bổ sung các codec và tùy chọn riêng cho HTTP client.

### 6.3. Không dùng ExchangeStrategies.empty() nếu chưa cần thay toàn bộ

ExchangeStrategies.empty() tạo cấu hình rỗng. Nếu dùng nó mà chỉ đăng ký một JSON decoder, các reader/writer mặc định khác có thể không còn: String, byte[], Resource, form, multipart hoặc SSE.

Đây là lựa chọn cho hệ thống kiểm soát đầy đủ codec, không phải shortcut để “tạo WebClient nhẹ hơn”. Hãy ưu tiên builder() nếu muốn giữ defaults rồi thay đổi một vài lựa chọn.

## 7. Tùy chỉnh codec: ba cấp độ thường gặp

### 7.1. Điều chỉnh default codec

Dùng khi chỉ cần thay đổi hành vi codec mặc định:

```java
configurer.defaultCodecs().maxInMemorySize(1024 * 1024);
configurer.defaultCodecs().enableLoggingRequestDetails(false);
```

maxInMemorySize đặt giới hạn buffering. enableLoggingRequestDetails điều khiển việc log chi tiết form data và headers; mặc định cần thận trọng vì những dữ liệu này có thể chứa secret hoặc thông tin cá nhân.

### 7.2. Thay codec mặc định

Dùng khi cần một JSON encoder/decoder với ObjectMapper hoặc JsonMapper riêng. Ví dụ Jackson 2 ở mục 4.3. Khi thay encoder, decoder, hãy thay đồng bộ nếu cùng một quy tắc serialization cần áp dụng cả hai chiều.

Không nên tạo ObjectMapper mới với cấu hình thiếu module rồi thay codec mặc định một cách vô tình. Ví dụ, thiếu Java Time module có thể làm kiểu LocalDate/Instant serialize khác mong đợi. Hãy tái sử dụng cấu hình Jackson của ứng dụng hoặc đăng ký các module cần thiết.

### 7.3. Đăng ký custom Encoder/Decoder

Dùng khi media type hoặc wire format không được codec mặc định hỗ trợ, ví dụ binary format riêng của hệ thống.

Một custom decoder cần:

1. Khai báo kiểu Java có thể decode.
2. Khai báo media type mà decoder hỗ trợ.
3. Đọc DataBuffer theo cơ chế non-blocking.
4. Xử lý dữ liệu chia thành nhiều buffer.
5. Giải phóng buffer đã tiêu thụ hoặc bị discard.
6. Xử lý error và cancellation để không giữ buffer.
7. Có test cho payload hợp lệ, thiếu, sai định dạng và payload chia qua nhiều buffer.

Một custom encoder cần:

1. Xác định kiểu object và media type có thể encode.
2. Chuyển object thành DataBuffer hoặc chuỗi buffer.
3. Giải phóng buffer nếu serialization thất bại trước khi giao buffer cho consumer.
4. Hỗ trợ backpressure, không tự gom stream không giới hạn vào bộ nhớ.
5. Đảm bảo consumer nhận buffer có ownership rõ ràng.

Đăng ký vào server:

```java
configurer.customCodecs()
        .registerWithDefaultConfig(new MyBinaryDecoder());
```

Đăng ký vào WebClient:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.customCodecs()
                        .registerWithDefaultConfig(new MyBinaryDecoder()))
        .build();
```

`MyBinaryDecoder` là class do ứng dụng triển khai. Hai đoạn code là mẫu đăng ký, không phải chương trình độc lập. Nếu custom codec tự quản lý giới hạn hoặc logging riêng, hãy cấu hình rõ thay vì mặc định rằng mọi setting của default codec đều tự động áp dụng.

## 8. maxInMemorySize và DataBufferLimitException

Spring giới hạn số byte mà các decoder/reader được phép buffer trong bộ nhớ để tránh ứng dụng gom payload quá lớn. Mặc định phổ biến của codec là **256 KiB**.

Nếu dữ liệu cần buffer vượt giới hạn, Spring có thể phát:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

Lỗi thường xuất hiện khi:

- Đọc toàn bộ request body thành một object duy nhất.
- Dùng `@RequestBody byte[]` hoặc `String` cho payload lớn.
- Parse form URL encoded.
- Đọc một multipart non-file part lớn.
- Decode một phần tử JSON/NDJSON quá lớn.
- Dùng bodyToMono hoặc một API client cần aggregate toàn bộ response.
- Một decoder custom gom nhiều DataBuffer thành một object.

Đối với một số định dạng streaming, giới hạn áp dụng cho số byte của từng object đang được tách/aggregate, không nhất thiết là tổng dung lượng của toàn bộ stream. Vì vậy, một Flux dài gồm nhiều phần tử nhỏ có thể chạy lâu hơn tổng 256 KiB mà không cần gom cả stream thành một buffer duy nhất.

### 8.1. Tăng giới hạn phía server

```java
@Configuration(proxyBeanMethods = false)
public class ServerCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(5 * 1024 * 1024);
    }
}
```

Ví dụ tăng lên 5 MiB. Chỉ chọn giá trị dựa trên kích thước request hợp lệ của API, số request đồng thời và ngân sách bộ nhớ. Nếu có nhiều request lớn đồng thời, tổng memory pressure có thể lớn hơn nhiều so với giới hạn của một request.

### 8.2. Tăng giới hạn phía WebClient

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(5 * 1024 * 1024))
        .build();
```

Giới hạn phía client độc lập với server. Nếu server chấp nhận body 5 MiB nhưng WebClient chỉ cho buffer 256 KiB, client vẫn có thể lỗi khi decode response lớn. Cần cấu hình đúng phía đang đọc dữ liệu.

### 8.3. Đừng tăng giới hạn để che lỗi streaming

Nếu dữ liệu có thể rất lớn hoặc không có giới hạn, hãy thiết kế streaming thay vì tăng maxInMemorySize lên một giá trị rất lớn.

Ví dụ:

```java
@GetMapping(
        value = "/export",
        produces = "application/x-ndjson")
public Flux<ExportRow> export() {
    return exportService.streamRows();
}
```

Flux được ghi dần theo định dạng NDJSON. Client có thể dùng bodyToFlux(ExportRow.class) để xử lý từng dòng:

```java
return webClient.get()
        .uri("/export")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .bodyToFlux(ExportRow.class);
```

Cách này giảm nhu cầu gom toàn bộ dữ liệu vào heap. Tuy nhiên, mỗi phần tử vẫn phải có kích thước hợp lý và các giới hạn của decoder vẫn có ý nghĩa.

## 9. DataBuffer và quản lý bộ nhớ

### 9.1. DataBuffer là gì?

DataBuffer là abstraction của Spring đại diện cho vùng byte. Nó có thể bọc byte array, ByteBuffer hoặc buffer của server như Netty ByteBuf.

Các API liên quan:

- **DataBufferFactory:** tạo hoặc wrap DataBuffer.
- **DataBuffer:** đọc/ghi byte và quản lý vị trí đọc/ghi.
- **PooledDataBuffer:** buffer có thể được pool và quản lý bằng reference count.
- **DataBufferUtils:** các tiện ích join, retain, release, skip/take theo byte count.

WebFlux thường lấy DataBufferFactory từ ServerHttpResponse hoặc ClientHttpRequest. Ứng dụng không cần tự tạo factory trong các trường hợp controller thông thường.

### 9.2. Vì sao pooled buffer cần release?

Một số server như Reactor Netty sử dụng pooled/direct buffers để giảm allocation và copy. PooledDataBuffer có reference count:

- Khi tạo, reference count thường bắt đầu ở 1.
- retain tăng reference count.
- release giảm reference count.
- Khi reference count về 0, vùng nhớ có thể được trả về pool.

Nếu ứng dụng giữ buffer nhưng không release đúng lúc, bộ nhớ native/direct có thể bị giữ lại và gây memory leak. Nếu release quá sớm hoặc nhiều lần, phần code khác có thể đọc buffer đã được trả về pool và phát sinh lỗi khó chẩn đoán.

Trong phần lớn controller, hãy dùng object Java và codec mặc định để Spring quản lý buffer. Chỉ cần tự quản lý khi bạn trực tiếp tiêu thụ/tạo DataBuffer hoặc viết custom codec.

### 9.3. Giải phóng buffer đã tiêu thụ

Nếu custom decoder đọc xong một DataBuffer và không giữ lại, có thể dùng:

```java
DataBufferUtils.release(dataBuffer);
```

Đừng release buffer mà bạn chưa sở hữu hoặc buffer đã được chuyển cho thành phần khác chịu trách nhiệm. Quyền sở hữu phải rõ ràng ở từng bước.

### 9.4. Buffer bị discard do operator

Một decoder có thể dùng các operator như filter, skip, flatMap, reduce hoặc prefetch. Một số buffer có thể bị loại bỏ khi có filter, error hoặc cancellation. Khi đó cần đăng ký cleanup cho buffer bị discard:

```java
return buffers
        .filter(this::isRelevant)
        .map(this::decode)
        .doOnDiscard(
                DataBuffer.class,
                DataBufferUtils::release);
```

Đây là ví dụ khái niệm cho custom decoder; cần đảm bảo operator chain và ownership của buffer phù hợp. doOnDiscard không thay thế việc release buffer đã được decoder đọc thành công hoặc buffer đang được giữ lại.

### 9.5. Giữ buffer qua nhiều bước

Nếu decoder lưu tạm một hoặc nhiều DataBuffer, nó phải giải phóng chúng khi:

- Đã đọc xong.
- Gặp lỗi trước khi đọc xong.
- Publisher bị cancel.
- Buffer bị loại bỏ do filter/skip hoặc operator khác.

Không chỉ viết happy path. Leak thường xuất hiện trong error/cancel path, nhất là khi client ngắt kết nối giữa lúc upload/download.

### 9.6. DataBufferUtils.join

DataBufferUtils.join có thể ghép một publisher nhiều DataBuffer thành một DataBuffer, có thể dùng composite buffer nếu implementation hỗ trợ. Đây là API tiện ích an toàn hơn việc tự copy byte từng buffer vào một mảng.

```java
Mono<DataBuffer> joined = DataBufferUtils.join(buffers);
```

Join vẫn có thể aggregate một lượng dữ liệu lớn. Dùng nó khi payload có giới hạn rõ ràng và có chính sách max bytes phù hợp; không dùng để gom một stream vô hạn.

### 9.7. Encoder và ownership của buffer

Encoder tạo DataBuffer để consumer đọc. Trong WebFlux, consumer thường là writer ghi ra HTTP response hoặc client request; writer chịu trách nhiệm giải phóng buffer đã nhận. Encoder cần giải phóng buffer nếu serialization thất bại trong lúc đang ghi dữ liệu vào buffer trước khi trả buffer cho consumer.

Không release buffer ngay sau khi emit nó cho response writer, vì writer vẫn cần đọc nội dung. Ngược lại, nếu encoder tạo buffer rồi ném exception trước khi emit, encoder phải dọn buffer của chính nó.

## 10. Multipart và các giới hạn liên quan

Multipart có thêm các giới hạn ngoài maxInMemorySize:

| Giới hạn | Tác dụng |
| --- | --- |
| maxInMemorySize | Với non-file parts, giới hạn số byte giữ trong bộ nhớ; với file part, xác định ngưỡng chuyển sang ghi file xuống disk |
| maxDiskUsagePerPart | Giới hạn dung lượng file part ghi ra disk |
| maxParts | Giới hạn tổng số multipart parts |

Để cấu hình các giới hạn multipart này, thường cần cung cấp một MultipartHttpMessageReader được cấu hình sẵn cho ServerCodecConfigurer. Không chỉ tăng maxInMemorySize nếu mục tiêu là giới hạn dung lượng file hoặc số lượng part.

WebFlux có thể đọc multipart theo dạng map-like qua MultiValueMap<String, Part>. Cách này thuận tiện khi cần truy cập nhiều part theo tên, nhưng yêu cầu parse và thu thập cấu trúc multipart.

Nếu cần xử lý upload lớn theo streaming, có thể dùng Flux<PartEvent> qua @RequestBody thay vì yêu cầu toàn bộ multipart được thu thập thành map. Khi xử lý từng event/part, phải quản lý DataBuffer và cleanup đúng ownership.

## 11. Logging request details và dữ liệu nhạy cảm

Codec mặc định hỗ trợ bật logging chi tiết request data:

```java
configurer.defaultCodecs()
        .enableLoggingRequestDetails(true);
```

Ở phía WebClient:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .enableLoggingRequestDetails(true))
        .build();
```

Tùy chọn này có thể làm form data hoặc headers được log chi tiết hơn. Mặc định Spring che/mask một số dữ liệu nhạy cảm. Bật logging details có thể làm lộ Authorization, cookie, form fields, thông tin cá nhân hoặc payload bí mật.

Chỉ bật tạm thời khi debug ở môi trường kiểm soát; tắt sau khi điều tra. Production nên dùng logging có chọn lọc, redact dữ liệu và tránh log toàn bộ request/response body.

## 12. Ví dụ Spring Boot WebFlux: cấu hình server và client

Ví dụ dưới đây dùng Java 17+, Spring Boot 3.x và Spring Framework 6.2 với Jackson 2 mặc định. Nó minh họa cấu hình server, controller nhận JSON, WebClient dùng ExchangeStrategies và test HTTP bằng WebTestClient.

### 12.1. Dependencies

Trong build.gradle, dự án cần các dependency chính:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Dự án cần Spring Boot Gradle plugin và dependency management tương thích. Dùng BOM của Boot để quản lý version Spring Framework, Reactor, Jackson và test libraries; không override riêng spring-webflux.

### 12.2. Application class

Tệp src/main/java/demo/CodecDemoApplication.java:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CodecDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CodecDemoApplication.class, args);
    }
}
```

### 12.3. ServerCodecConfigurer

Tệp src/main/java/demo/ServerCodecConfiguration.java:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ServerCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(1024 * 1024);
    }
}
```

Server giữ default codecs và nâng giới hạn buffering lên 1 MiB. Trong Spring Boot không thêm @EnableWebFlux cho ví dụ này.

### 12.4. Request/response DTO

Tệp src/main/java/demo/EchoRequest.java:

```java
package demo;

public record EchoRequest(String message) {
}
```

Tệp src/main/java/demo/EchoResponse.java:

```java
package demo;

public record EchoResponse(String message, int length) {
}
```

### 12.5. Controller

Tệp src/main/java/demo/EchoController.java:

```java
package demo;

import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    @PostMapping(
            value = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<EchoResponse> echo(
            @RequestBody Mono<EchoRequest> request) {

        return request.map(body ->
                new EchoResponse(
                        body.message(),
                        body.message().length()));
    }

    @GetMapping(
            value = "/api/events",
            produces = "application/x-ndjson")
    public Flux<EchoResponse> events() {
        return Flux.fromIterable(List.of(
                new EchoResponse("created", 7),
                new EchoResponse("updated", 7),
                new EchoResponse("closed", 6)));
    }
}
```

Endpoint POST nhận JSON qua decoder và trả JSON qua encoder. Endpoint GET trả Flux theo NDJSON để mỗi object có thể được ghi thành một dòng thay vì gom thành JSON array.

### 12.6. ClientCodecConfigurer và ExchangeStrategies

Tệp src/main/java/demo/ClientCodecConfiguration.java:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ExchangeStrategies;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class ClientCodecConfiguration {

    @Bean
    WebClient echoWebClient() {
        ExchangeStrategies strategies = ExchangeStrategies.builder()
                .codecs(configurer ->
                        configurer.defaultCodecs()
                                .maxInMemorySize(1024 * 1024))
                .build();

        return WebClient.builder()
                .baseUrl("http://localhost:8080")
                .exchangeStrategies(strategies)
                .build();
    }
}
```

ExchangeStrategies được tạo từ builder mặc định, nên các codec mặc định vẫn tồn tại. Client chỉ thay đổi giới hạn buffering. WebClient sau khi build là immutable.

Nếu chỉ cần cấu hình nhanh, có thể bỏ ExchangeStrategies và dùng WebClient.Builder.codecs:

```java
WebClient client = WebClient.builder()
        .baseUrl("http://localhost:8080")
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(1024 * 1024))
        .build();
```

Hai cách đều tùy chỉnh ClientCodecConfigurer bên trong WebClient. Cách dùng ExchangeStrategies hữu ích khi cần giữ strategy thành một object có thể tái sử dụng.

### 12.7. Service gọi WebClient

Tệp src/main/java/demo/EchoClient.java:

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoClient {

    private final WebClient client;

    public EchoClient(WebClient echoWebClient) {
        this.client = echoWebClient;
    }

    public Mono<EchoResponse> send(EchoRequest request) {
        return client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .retrieve()
                .bodyToMono(EchoResponse.class);
    }

    public Flux<EchoResponse> events() {
        return client.get()
                .uri("/api/events")
                .accept(MediaType.parseMediaType("application/x-ndjson"))
                .retrieve()
                .bodyToFlux(EchoResponse.class);
    }
}
```

Client dùng encoder để serialize EchoRequest thành JSON, rồi decoder tạo EchoResponse từ JSON. Với NDJSON, bodyToFlux decode từng object theo stream.

Service không gọi block() hoặc subscribe(); publisher được trả về để tầng gọi quyết định cách compose và quản lý lifecycle.

### 12.8. Test bằng WebTestClient

Tệp src/test/java/demo/EchoControllerTest.java:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class EchoControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void decodesAndEncodesJson() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoRequest("hello"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message").isEqualTo("hello")
                .jsonPath("$.length").isEqualTo(5);
    }

    @Test
    void writesNdjsonStream() {
        client.get()
                .uri("/api/events")
                .accept(MediaType.parseMediaType("application/x-ndjson"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.parseMediaType("application/x-ndjson"))
                .expectBody()
                .jsonPath("$[0].message").isEqualTo("created")
                .jsonPath("$[1].message").isEqualTo("updated")
                .jsonPath("$[2].message").isEqualTo("closed");
    }
}
```

Test đầu xác nhận JSON reader và writer của server hoạt động. Test thứ hai xác nhận NDJSON media type và nội dung các phần tử. Test có thể được điều chỉnh theo phiên bản Spring Boot/test support trong dự án.

Chạy test:

```bash
./gradlew test
```

### 12.9. Chạy và gọi bằng curl

Khởi động:

```bash
./gradlew bootRun
```

Gửi JSON:

```bash
curl -i -X POST http://localhost:8080/api/echo -H "Content-Type: application/json" -H "Accept: application/json" -d "{"message":"hello"}"
```

Body JSON dự kiến:

```json
{
  "message": "hello",
  "length": 5
}
```

Gọi stream:

```bash
curl -N -H "Accept: application/x-ndjson" http://localhost:8080/api/events
```

Output NDJSON:

```text
{"message":"created","length":7}
{"message":"updated","length":7}
{"message":"closed","length":6}
```

Thứ tự field JSON phụ thuộc cấu hình serializer, nhưng giá trị và số phần tử phải khớp dữ liệu trong controller.

## 13. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| JSON body không decode được | Thiếu Jackson hoặc Content-Type không khớp | Kiểm tra dependency và Content-Type |
| WebClient nhận DataBufferLimitException | Response cần aggregate vượt maxInMemorySize | Giảm payload, stream dữ liệu hoặc tăng limit có kiểm soát |
| Server nhận được payload nhưng WebClient lỗi | Giới hạn client khác giới hạn server | Cấu hình codec đúng phía đang đọc |
| Custom decoder không được chọn | Không hỗ trợ target type hoặc media type; đăng ký sai | Kiểm tra canDecode/canRead và MediaType |
| Custom codec che codec mặc định ngoài ý muốn | Thứ tự/độ ưu tiên reader-writer không như mong đợi | Kiểm tra danh sách reader/writer và đăng ký đúng loại |
| Mất JSON codec sau cấu hình | Gọi registerDefaults(false) | Giữ defaults hoặc đăng ký đầy đủ codec cần thiết |
| Multipart upload giữ quá nhiều memory | Non-file part hoặc file threshold quá lớn | Cấu hình maxInMemorySize, disk usage và maxParts |
| Memory leak với Netty | Pooled DataBuffer không được release | Quản lý ownership và release trong custom codec |
| Buffer đã release nhưng vẫn bị đọc | Release quá sớm hoặc sai ownership | Chỉ release khi consumer không còn cần buffer |
| Leak chỉ xảy ra khi cancel/error | Cleanup chỉ xử lý happy path | Xử lý error, cancellation và doOnDiscard |
| Flux JSON bị gom thành một array | application/json là representation không streaming mặc định | Dùng NDJSON/SSE hoặc kiểu streaming phù hợp |
| Flux<String> không tạo JSON string array | String được xử lý như CharSequence/serialized content | Dùng Mono<List<String>> nếu cần JSON array |
| Log lộ token/cookie | Bật request detail logging hoặc log raw body | Redact dữ liệu, tắt logging chi tiết |
| Boot mất auto-config sau khi thêm @EnableWebFlux | Đã chuyển sang chế độ cấu hình WebFlux tường minh | Bỏ @EnableWebFlux nếu chỉ cần WebFluxConfigurer |
| Tăng limit lên rất lớn nhưng vẫn thiếu memory | Nhiều request lớn đồng thời hoặc aggregate không giới hạn | Thiết kế streaming, giới hạn concurrency và payload |

## 14. Checklist chọn và cấu hình codec

Trước khi thay đổi codec, hãy kiểm tra:

1. Dữ liệu cần đọc/ghi là JSON, text, binary, form, multipart, SSE hay NDJSON?
2. Đây là cấu hình server hay client? Chọn ServerCodecConfigurer hoặc ClientCodecConfigurer đúng phía.
3. Codec mặc định có đủ không? Nếu chỉ cần thay memory limit, dùng defaultCodecs.
4. Nếu thêm format riêng, custom codec có khai báo target type và media type chính xác không?
5. Custom codec có hỗ trợ backpressure và xử lý buffer theo kiểu non-blocking không?
6. Có giới hạn buffering hợp lý cho payload, multipart part và stream element không?
7. Có thực sự cần aggregate toàn bộ body hay có thể dùng Flux/streaming?
8. DataBuffer có được release đúng khi success, error và cancel không?
9. Codec custom có cần registerWithDefaultConfig để nhận các setting chung không?
10. Có lý do rõ ràng để gọi registerDefaults(false) không?
11. Logging có thể làm lộ Authorization, cookie hoặc body nhạy cảm không?
12. Test có kiểm tra Content-Type, payload lớn, NDJSON, multipart và lỗi codec không?

## 15. Tóm tắt lựa chọn API

| Nhu cầu | API nên dùng |
| --- | --- |
| Tùy chỉnh codec mặc định của WebFlux server | `WebFluxConfigurer.configureHttpMessageCodecs(ServerCodecConfigurer)` |
| Tăng giới hạn buffer server | `ServerCodecConfigurer.defaultCodecs().maxInMemorySize(...)` |
| Đăng ký reader/writer riêng cho server | `ServerCodecConfigurer.customCodecs()` |
| Tùy chỉnh codec của WebClient | `WebClient.Builder.codecs(Consumer<ClientCodecConfigurer>)` |
| Tạo strategy riêng cho WebClient | `ExchangeStrategies.builder().codecs(...).build()` |
| Gắn strategy vào WebClient | `WebClient.Builder.exchangeStrategies(...)` |
| Lấy strategy mặc định | `ExchangeStrategies.withDefaults()` |
| Tạo strategy rỗng | `ExchangeStrategies.empty()` |
| Clone strategy để chỉnh sửa | `ExchangeStrategies.mutate()` |
| Release pooled buffer | `DataBufferUtils.release(...)` |
| Join stream buffer có giới hạn | `DataBufferUtils.join(...)` |
| Cleanup buffer bị discard | `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` |

## 16. Tài liệu tham khảo chính thức

- [Spring Framework – WebFlux Config: HTTP message codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): cấu hình ServerCodecConfigurer, default codecs và custom readers/writers.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): cấu hình WebClient.Builder, codecs, ExchangeStrategies và maxInMemorySize.
- [Spring Framework – Reactive Core / Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Encoder, Decoder, HttpMessageReader, HttpMessageWriter, JSON streaming, multipart và logging.
- [Spring Framework – Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): DataBufferFactory, PooledDataBuffer, DataBufferUtils, retain/release và doOnDiscard.
- [CodecConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/CodecConfigurer.html): defaultCodecs, customCodecs, registerDefaults, getReaders/getWriters.
- [ServerCodecConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ServerCodecConfigurer.html): codec configuration phía server.
- [ClientCodecConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ClientCodecConfigurer.html): codec configuration phía client.
- [ExchangeStrategies Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ExchangeStrategies.html): builder, withDefaults, empty và mutate.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): auto-configuration và CodecCustomizer của Spring Boot.

## 17. Ghi nhớ

**ServerCodecConfigurer quản lý codec phía WebFlux server; ClientCodecConfigurer quản lý codec phía client; ExchangeStrategies đóng gói reader/writer mà WebClient sử dụng.** Cả hai phía đều có codec mặc định, có thể điều chỉnh qua defaultCodecs và mở rộng qua customCodecs.

Hãy giữ codec defaults nếu chỉ cần thay đổi một giới hạn hoặc một encoder/decoder. Dùng ExchangeStrategies khi muốn đóng gói và tái sử dụng một cấu hình client; với phần lớn trường hợp, WebClient.Builder.codecs là cách ngắn gọn hơn. Giới hạn buffering mặc định khoảng 256 KiB giúp ngăn aggregate payload quá lớn; tăng limit phải dựa trên kích thước dữ liệu và mức đồng thời. Nếu cần xử lý dữ liệu lớn, hãy ưu tiên streaming và backpressure. Khi tự làm việc với DataBuffer, luôn xác định ownership và release đúng trong cả success, error và cancellation để tránh memory leak hoặc use-after-release.
