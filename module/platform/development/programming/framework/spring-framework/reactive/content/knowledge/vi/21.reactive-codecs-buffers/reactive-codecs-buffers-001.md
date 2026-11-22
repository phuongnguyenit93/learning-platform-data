# Encoder, Decoder, HttpMessageReader và HttpMessageWriter

Trong **Spring WebFlux**, HTTP request và response đi qua một chuỗi chuyển đổi giữa byte và object Java. Client gửi byte theo một media type như JSON, form hoặc binary; controller thường muốn nhận DTO, String, Resource hay Flux. Khi trả response, controller phát object hoặc publisher và framework phải mã hóa chúng thành byte để ghi ra HTTP connection.

Spring chia công việc này thành hai tầng:

- **Encoder và Decoder** là các hợp đồng codec cấp thấp. Encoder biến publisher của object thành luồng DataBuffer; Decoder biến luồng DataBuffer thành object.
- **HttpMessageReader và HttpMessageWriter** là các hợp đồng ở tầng HTTP. Reader đọc body từ ReactiveHttpInputMessage; Writer ghi body vào ReactiveHttpOutputMessage. Chúng còn biết media type, kiểu dữ liệu và metadata HTTP.

DataBuffer là đơn vị byte buffer mà codec sử dụng. Với server dựa trên Netty, buffer có thể được pool và reference-count; nếu code tự xử lý DataBuffer, phải quản lý việc release đúng vòng đời. Khi dùng codec mặc định, Spring chịu trách nhiệm phần lớn việc này.

Bài này đi từ luồng request/response, các interface và codec mặc định đến cấu hình codec, WebClient, giới hạn bộ nhớ, DataBuffer ownership và một ứng dụng Java 17 có ví dụ JSON, NDJSON và raw bytes.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả đường đi từ HTTP body đến object Java qua HttpMessageReader và Decoder.
2. Mô tả đường đi từ object/publisher đến HTTP response qua Encoder và HttpMessageWriter.
3. Phân biệt Encoder/Decoder cấp thấp với Reader/Writer ở tầng HTTP.
4. Hiểu vai trò của DataBuffer, DataBufferFactory, DataBufferUtils và pooled buffer.
5. Chọn media type phù hợp cho JSON, text, binary, form, multipart, NDJSON và SSE.
6. Cấu hình default codecs, maxInMemorySize và custom codecs bằng ServerCodecConfigurer.
7. Cấu hình ClientCodecConfigurer/WebClient để đọc và ghi cùng định dạng.
8. Tránh DataBuffer leak, double release, giữ buffer quá lâu và gom body lớn vào RAM.
9. Hiểu DataBufferLimitException, giới hạn theo từng object khi streaming và giới hạn riêng của multipart.
10. Viết và kiểm thử controller WebFlux sử dụng JSON, NDJSON và DataBuffer trực tiếp.

## 2. Bức tranh tổng thể: từ byte đến object và ngược lại

Một request JSON đến controller có thể đi theo đường sau:

~~~text
HTTP request
Content-Type: application/json
Body bytes
    |
    v
ReactiveHttpInputMessage
    |
    v
HttpMessageReader
    |
    v
Decoder (ví dụ Jackson JSON)
    |
    v
DataBuffer stream -> Java object / Flux<Object>
    |
    v
Controller method
~~~

Khi trả response, luồng xử lý đi theo chiều ngược lại:

~~~text
Controller return value
Mono<Book> / Flux<Book> / Book
    |
    v
HttpMessageWriter
    |
    v
Encoder (ví dụ Jackson JSON)
    |
    v
Java object -> DataBuffer stream
    |
    v
ReactiveHttpOutputMessage
    |
    v
HTTP response bytes
~~~

Đây là mô hình khái quát. Một số reader/writer chuyên biệt tự xử lý format HTTP mà không dùng một Decoder/Encoder đơn giản bên dưới, ví dụ reader cho form hoặc multipart. Tuy nhiên, ranh giới vẫn giống nhau: Reader/Writer giải quyết HTTP message; codec biến dữ liệu giữa byte buffer và kiểu ứng dụng.

WebFlux dùng Reactive Streams để đọc/ghi không chặn và điều phối demand. Khi body là một publisher, framework có thể xử lý theo từng phần tử thay vì phải đợi toàn bộ nội dung được gom thành một mảng byte lớn.

## 3. Encoder và Decoder

Các interface cấp thấp nằm trong package org.springframework.core.codec.

### 3.1. Encoder

Encoder<T> biến publisher của T thành publisher của DataBuffer:

~~~text
Publisher<T>
    |
    v
Encoder<T>
    |
    v
Publisher<DataBuffer>
~~~

Các trách nhiệm chính:

- Kiểm tra một kiểu dữ liệu và media type có được hỗ trợ hay không, qua canEncode.
- Mã hóa một giá trị đơn nếu implementation hỗ trợ encodeValue.
- Mã hóa một publisher thành luồng DataBuffer qua encode.
- Cung cấp MIME types mà encoder hỗ trợ.

Ví dụ khái niệm: Jackson JSON encoder nhận Book hoặc Flux<Book> và tạo byte JSON tương ứng. String encoder nhận chuỗi và mã hóa thành byte theo charset/media type.

Encoder không tự quyết định toàn bộ HTTP status hoặc response headers. Việc chọn writer và media type thuộc tầng HTTP message.

### 3.2. Decoder

Decoder<T> làm chiều ngược lại: nhận publisher DataBuffer và tạo publisher object:

~~~text
Publisher<DataBuffer>
    |
    v
Decoder<T>
    |
    v
Publisher<T>
~~~

Các trách nhiệm chính:

- Kiểm tra kiểu đích và media type có thể decode qua canDecode.
- Đọc luồng byte và tạo object.
- Hỗ trợ decodeToMono cho trường hợp cần một kết quả đã tổng hợp, khi implementation cung cấp.
- Quản lý buffer đã tiêu thụ, buffer bị bỏ qua, lỗi và cancellation.

Ví dụ: Jackson JSON decoder nhận byte JSON và tạo CreateBookRequest. String decoder chuyển byte thành String. Decoder cho binary có thể giữ dữ liệu ở dạng DataBuffer, ByteBuffer hoặc byte[] tùy kiểu đích.

### 3.3. Encoder/Decoder không phải là HTTP message converter

Encoder/Decoder được thiết kế để chuyển đổi nội dung byte và object, độc lập với toàn bộ HTTP message. Chúng không phải nơi duy nhất xử lý Content-Type, Accept, status hoặc header.

Spring cung cấp adapter để sử dụng chúng ở tầng HTTP:

- EncoderHttpMessageWriter bọc một Encoder và cung cấp hợp đồng HttpMessageWriter.
- DecoderHttpMessageReader bọc một Decoder và cung cấp hợp đồng HttpMessageReader.

Các reader/writer chuyên biệt như FormHttpMessageReader, MultipartHttpMessageReader hoặc ServerSentEventHttpMessageWriter có thể triển khai trực tiếp logic HTTP phù hợp với định dạng của chúng.

## 4. HttpMessageReader và HttpMessageWriter

### 4.1. HttpMessageReader<T>

HttpMessageReader<T> đọc từ ReactiveHttpInputMessage và giải mã body thành object:

~~~text
ReactiveHttpInputMessage
  headers + body DataBuffer
          |
          v
   HttpMessageReader<T>
          |
          v
     Publisher<T>
~~~

Các phương thức quan trọng về mặt ý nghĩa:

| API | Vai trò |
| --- | --- |
| canRead(elementType, mediaType) | Kiểm tra reader có đọc được kiểu và media type này không. |
| getReadableMediaTypes() | Trả về media type reader hỗ trợ. |
| read(...) | Đọc body thành publisher nhiều phần tử. |
| readMono(...) | Đọc body thành Mono cho trường hợp một giá trị hoặc body được tổng hợp. |

Một reader thường được chọn dựa trên kiểu tham số controller và Content-Type của request. Ví dụ, tham số @RequestBody CreateBookRequest với application/json sẽ phù hợp JSON reader nếu Jackson codec có mặt.

### 4.2. HttpMessageWriter<T>

HttpMessageWriter<T> ghi publisher object thành byte vào ReactiveHttpOutputMessage:

~~~text
Publisher<T>
      |
      v
HttpMessageWriter<T>
      |
      v
ReactiveHttpOutputMessage
  headers + body DataBuffer
~~~

Các phương thức quan trọng:

| API | Vai trò |
| --- | --- |
| canWrite(elementType, mediaType) | Kiểm tra writer có ghi được kiểu và media type không. |
| getWritableMediaTypes() | Trả về media type writer hỗ trợ. |
| write(...) | Ghi publisher object vào HTTP output message. |

Writer phù hợp được chọn dựa trên kiểu return value, media type mà controller khai báo qua produces và Accept của client.

### 4.3. Quan hệ giữa bốn interface

| Interface | Tầng | Hướng chuyển đổi | Đầu vào | Đầu ra |
| --- | --- | --- | --- | --- |
| Encoder<T> | Codec cấp thấp | Encode | Publisher<T> | Publisher<DataBuffer> |
| Decoder<T> | Codec cấp thấp | Decode | Publisher<DataBuffer> | Publisher<T> |
| HttpMessageReader<T> | HTTP | Read/decode request | ReactiveHttpInputMessage | Publisher<T> |
| HttpMessageWriter<T> | HTTP | Encode/write response | Publisher<T> | ReactiveHttpOutputMessage |

Đối với codec dựa trên Encoder/Decoder, adapter làm cầu nối:

~~~text
Decoder<T> -- DecoderHttpMessageReader --> HttpMessageReader<T>

Encoder<T> -- EncoderHttpMessageWriter --> HttpMessageWriter<T>
~~~

Không phải mọi Reader/Writer đều chỉ là adapter. Reader cho form hoặc multipart cần xử lý cấu trúc HTTP riêng; writer cho SSE phải tạo framing sự kiện đúng chuẩn.

## 5. Media type và content negotiation

Codec không được chọn chỉ dựa trên tên class Java. Spring còn xét media type.

Hai header quan trọng:

- **Content-Type** mô tả định dạng body mà client gửi.
- **Accept** mô tả định dạng response mà client muốn nhận.

Ví dụ:

~~~http
POST /api/books
Content-Type: application/json
Accept: application/json
~~~

Request JSON cần reader có thể đọc kiểu DTO với application/json. Response DTO cần writer có thể ghi application/json.

Nếu request dùng Content-Type mà không reader nào hỗ trợ, thường nhận 415 Unsupported Media Type. Nếu client yêu cầu Accept không tương thích với writer có thể ghi, thường nhận 406 Not Acceptable. JSON sai cú pháp hoặc không thể decode có thể trở thành lỗi đọc request body, thường được xử lý như bad request.

### 5.1. Các định dạng thường gặp

| Media type | Kiểu dữ liệu thường dùng | Codec/reader/writer thường gặp |
| --- | --- | --- |
| application/json | DTO, Map, record, collection | Jackson JSON |
| application/x-ndjson | Dòng JSON độc lập | Jackson streaming/NDJSON |
| text/plain | String | String codec |
| application/octet-stream | byte[], ByteBuffer, DataBuffer, Resource | Byte array/Resource/DataBuffer codec |
| application/x-www-form-urlencoded | MultiValueMap<String,String> | Form reader/writer |
| multipart/form-data | Part, FilePart, PartEvent | Multipart reader/writer |
| text/event-stream | ServerSentEvent<T> hoặc event data | SSE reader/writer |

Tên media type và hỗ trợ cụ thể phụ thuộc codec/version. Hãy khai báo consumes/produces phù hợp và kiểm tra danh sách readable/writable media types của cấu hình đang chạy.

### 5.2. JSON array và NDJSON streaming

Một Flux<Book> với application/json thường được encode thành một JSON array:

~~~json
[
  {"id":"b-1","title":"Reactive Basics"},
  {"id":"b-2","title":"WebFlux in Practice"}
]
~~~

Với application/x-ndjson, mỗi object được mã hóa thành một dòng JSON riêng:

~~~text
{"id":"b-1","title":"Reactive Basics"}
{"id":"b-2","title":"WebFlux in Practice"}
~~~

NDJSON phù hợp với luồng phần tử độc lập, cho phép client xử lý từng record khi nhận được. JSON array thông thường cần cấu trúc mở/đóng mảng và cách tiêu thụ khác. Chọn định dạng dựa trên hợp đồng client, không chỉ dựa trên việc controller trả Flux.

### 5.3. SSE khác NDJSON

Server-Sent Events dùng text/event-stream và framing sự kiện gồm các trường như data, id, event, retry. NDJSON chỉ là các dòng JSON. Nếu cần event ID, tên sự kiện hoặc retry hint, dùng ServerSentEvent<T> và SSE writer.

Với stream kéo dài, nên gửi dữ liệu hoặc heartbeat định kỳ để phát hiện client ngắt kết nối sớm hơn. Một Flux không phát gì trong thời gian dài có thể khiến việc nhận biết disconnect bị trì hoãn tùy server/client.

## 6. Codec mặc định trong Spring WebFlux

WebFlux cung cấp các reader/writer mặc định dựa trên classpath và cấu hình. Các nhóm phổ biến gồm:

- Byte array, ByteBuffer, DataBuffer, Resource và String.
- Jackson JSON và một số định dạng Jackson khác khi dependency tương ứng có mặt.
- Form URL encoded.
- Multipart.
- Server-Sent Events.
- Một số định dạng như XML hoặc Protocol Buffers khi dependency/codec phù hợp được thêm.

Spring Boot tự cấu hình HttpMessageReader và HttpMessageWriter mặc định dựa trên thư viện có trên classpath. WebFlux và WebClient dùng các codec có cấu trúc tương tự, nhưng phía server dùng ServerCodecConfigurer và phía client dùng ClientCodecConfigurer.

Không cần tự tạo Jackson reader/writer cho mọi controller. Khi starter WebFlux và Jackson phù hợp đã có, @RequestBody DTO và return DTO thường hoạt động trực tiếp.

### 6.1. Kiểm tra định dạng theo classpath

Nếu thêm dependency Jackson, codec JSON có thể được cấu hình tự động. Nếu thêm một thư viện định dạng mới, hãy kiểm tra:

1. Codec có được đăng ký không?
2. Codec hỗ trợ kiểu Java cần dùng không?
3. Codec hỗ trợ đúng Content-Type/Accept không?
4. Codec có giới hạn buffering phù hợp không?
5. Có xung đột với codec khác có media type rộng hơn không?

Thêm dependency không tự bảo đảm endpoint dùng định dạng mới nếu không có reader/writer tương ứng.

## 7. Cấu hình ServerCodecConfigurer

ServerCodecConfigurer quản lý danh sách reader và writer phía server. Có thể tùy chỉnh qua WebFluxConfigurer:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
            .maxInMemorySize(512 * 1024);
    }
}
~~~

Đoạn này đặt giới hạn buffering của các default codec có hỗ trợ cấu hình đó ở mức 512 KiB. Nó không có nghĩa mọi request body đều bị giới hạn tổng cộng 512 KiB; phần giới hạn và cách áp dụng phụ thuộc codec, đặc biệt với streaming và multipart.

### 7.1. Đăng ký custom codec

Khi cần một định dạng riêng, có thể đăng ký Encoder hoặc Decoder; Spring tự bọc chúng thành writer/reader tương ứng:

~~~java
@Configuration
class CustomCodecConfig implements WebFluxConfigurer {

    private final Decoder<CustomRecord> customDecoder;
    private final Encoder<CustomRecord> customEncoder;

    CustomCodecConfig(
            Decoder<CustomRecord> customDecoder,
            Encoder<CustomRecord> customEncoder) {
        this.customDecoder = customDecoder;
        this.customEncoder = customEncoder;
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.customCodecs()
            .registerWithDefaultConfig(customDecoder);

        configurer.customCodecs()
            .registerWithDefaultConfig(customEncoder);
    }
}
~~~

Đây là cấu hình tích hợp: CustomRecord, customDecoder và customEncoder phải là các implementation thực tế do ứng dụng cung cấp. registerWithDefaultConfig đăng ký codec và áp dụng cấu hình mặc định liên quan như maxInMemorySize/logging khi phù hợp.

Nếu đã có sẵn một HttpMessageReader hoặc HttpMessageWriter hoàn chỉnh, đăng ký trực tiếp đối tượng đó. Khi hai codec cùng hỗ trợ một kiểu và media type, thứ tự và độ cụ thể của cấu hình có thể ảnh hưởng codec được chọn; hãy kiểm thử bằng request thực tế.

### 7.2. Khi nào thay thế default codecs?

Chỉ gọi registerDefaults(false) khi chủ động muốn kiểm soát toàn bộ danh sách reader/writer. Nếu tắt default codecs mà quên đăng ký lại JSON, String, byte array hoặc multipart cần thiết, controller có thể không đọc/ghi được body phổ biến.

Thông thường nên giữ default codecs và bổ sung custom codec. Nếu cần cấu hình thêm trong Spring Boot, dùng WebFluxConfigurer hoặc CodecCustomizer phù hợp với phiên bản Boot; không thêm @EnableWebFlux chỉ để thay đổi một giới hạn nhỏ vì annotation đó đưa ứng dụng sang chế độ tự kiểm soát WebFlux configuration.

## 8. Cấu hình codec phía WebClient

WebClient dùng cùng họ codec để encode request body và decode response body:

~~~java
WebClient client = WebClient.builder()
    .baseUrl("https://api.example.test")
    .codecs(configurer ->
        configurer.defaultCodecs()
            .maxInMemorySize(1024 * 1024)
    )
    .build();

Mono<Book> book = client.get()
    .uri("/books/b-1")
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToMono(Book.class);
~~~

Đây là snippet tích hợp; Book là DTO của ứng dụng. Cấu hình này đặt maxInMemorySize 1 MiB cho default codecs của client có hỗ trợ giới hạn.

Các cách tiêu thụ body:

- bodyToMono(Book.class): decode một object.
- bodyToFlux(Book.class): decode một luồng object nếu media type/codec hỗ trợ.
- toEntity(Book.class): lấy ResponseEntity cùng status/headers/body.
- toBodilessEntity(): chỉ lấy metadata response khi không cần body.

Với response body lớn, cân nhắc bodyToFlux hoặc xử lý DataBuffer streaming thay vì bodyToMono một object chứa toàn bộ nội dung. Đừng dùng block() trong event-loop; nếu cần tích hợp với code imperative, đặt ranh giới blocking ở scheduler/adapter phù hợp.

## 9. DataBuffer và DataBufferFactory

DataBuffer là abstraction của Spring cho byte buffer. Nó che giấu khác biệt giữa các implementation như Netty ByteBuf, Java NIO ByteBuffer hoặc buffer mặc định.

DataBuffer cung cấp:

- Đọc và ghi byte với read position/write position.
- Capacity có thể tăng theo implementation.
- Truy cập nội dung qua ByteBuffer, InputStream hoặc OutputStream khi cần.
- PooledDataBuffer/reference counting ở các implementation hỗ trợ pooling.

DataBufferFactory tạo buffer mới hoặc wrap byte[]/ByteBuffer sẵn có. Trong ứng dụng WebFlux, thường lấy factory từ response hoặc client request thay vì tự tạo factory gắn với một server cụ thể:

~~~java
DataBufferFactory factory = exchange.getResponse().bufferFactory();

DataBuffer buffer = factory.allocateBuffer();
buffer.write("hello".getBytes(StandardCharsets.UTF_8));
~~~

Nếu code tự ghi buffer vào response, response writer tiếp nhận ownership của buffer đã phát và chịu trách nhiệm tiêu thụ/release theo contract. Không release buffer lần thứ hai sau khi đã chuyển quyền sở hữu cho writer.

## 10. PooledDataBuffer, reference count và memory leak

Một số server như Reactor Netty dùng direct buffer được pool để giảm allocation và copy khi I/O. PooledDataBuffer có reference count:

- Khi buffer được cấp phát, reference count thường bắt đầu ở 1.
- retain() tăng reference count khi cần giữ thêm một quyền sở hữu.
- release() giảm reference count.
- Khi count về 0, buffer có thể được trả lại pool.

Nếu code đọc buffer nhưng không release đúng lúc, direct memory có thể bị giữ lâu và gây leak. Nếu release nhiều lần hơn số lần retain/ownership cho phép, có thể gặp IllegalReferenceCountException hoặc lỗi truy cập buffer đã giải phóng.

**Nguyên tắc ownership:** thành phần nhận DataBuffer có trách nhiệm biết khi nào mình tiêu thụ xong hoặc chuyển quyền sở hữu cho thành phần khác. Đừng release một buffer sau khi đã phát nó cho một writer khác; đừng giữ buffer qua request hoặc callback không rõ vòng đời.

### 10.1. DataBufferUtils.release và retain

Dùng utility của Spring thay vì ép kiểu sang PooledDataBuffer:

~~~java
DataBufferUtils.release(buffer);
~~~

~~~java
DataBufferUtils.retain(buffer);
~~~

Các utility này áp dụng thao tác khi implementation hỗ trợ pooled buffer. Với code nghiệp vụ thông thường, nên tránh giữ DataBuffer lâu; decode thành DTO/byte array nhỏ hoặc dùng Resource/streaming abstraction khi phù hợp.

### 10.2. DataBufferUtils.join

Khi cần tổng hợp nhiều DataBuffer thành một buffer, dùng DataBufferUtils.join thay vì tự nối byte array từng phần:

~~~java
Mono<DataBuffer> joined = DataBufferUtils.join(buffers);
~~~

join có thể sử dụng composite buffer để tránh copy toàn bộ dữ liệu nếu implementation hỗ trợ. Buffer kết quả phải được release sau khi đọc xong. Với overload có maxByteCount, ứng dụng có thể giới hạn tổng số byte được phép tổng hợp:

~~~java
Mono<DataBuffer> joined =
    DataBufferUtils.join(buffers, 1024 * 1024);
~~~

Nếu dữ liệu vượt ngưỡng, quá trình join phát lỗi DataBufferLimitException. Với stream lớn, cân nhắc xử lý từng buffer thay vì join toàn bộ.

### 10.3. Ví dụ đọc body raw và release đúng cách

Trong controller có thể nhận Flux<DataBuffer>, join một body nhỏ, đọc số byte rồi release buffer kết quả:

~~~java
@PostMapping(
    path = "/raw-size",
    consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<Integer> rawSize(@RequestBody Flux<DataBuffer> body) {
    return DataBufferUtils.join(body, 1024 * 1024)
        .map(buffer -> {
            try {
                return buffer.readableByteCount();
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        })
        .defaultIfEmpty(0);
}
~~~

Ở đây body tối đa 1 MiB được tổng hợp để đếm byte. finally bảo đảm buffer đã join được release kể cả khi thao tác đọc có lỗi. Nếu chỉ cần chuyển tiếp body tới response, hãy dùng writeWith(body) và để writer nhận quyền sở hữu; không join hoặc release thủ công nếu không cần.

## 11. Decoder tự viết phải quản lý buffer bị tiêu thụ và bị discard

Một Decoder thường là nơi cuối cùng đọc DataBuffer trước khi tạo object cấp cao hơn. Khi viết decoder riêng, phải xử lý:

1. Buffer được đọc xong và có thể release ngay.
2. Buffer bị filter, skip hoặc bị operator loại bỏ.
3. Buffer được giữ lại để ghép nhiều phần trước khi decode.
4. Lỗi, cancellation hoặc downstream không còn demand trước khi buffer được đọc.
5. Buffer được retain thêm lần nữa và cần release đúng số ownership.

Nếu dùng các Reactor operator có thể prefetch/cache hoặc bỏ phần tử, decoder cần xử lý discard. Mẫu quan trọng:

~~~java
return input
    .map(this::decodeOne)
    .doOnDiscard(
        DataBuffer.class,
        DataBufferUtils::release
    );
~~~

Đây là khung ý tưởng; decodeOne phải quản lý buffer mà nó nhận theo ownership của decoder. doOnDiscard chỉ xử lý phần tử bị Reactor discard trong những operator hỗ trợ discard hook; nó không thay thế việc release buffer đã được decoder giữ lại trong state riêng.

Khi phải giữ nhiều buffer để tạo một object, giải phóng tất cả buffer còn giữ trong cả ba tình huống: decode thành công, error và cancellation. DataBufferUtils.join, skipUntilByteCount và takeUntilByteCount là các utility nên xem xét trước khi tự xây thuật toán tổng hợp.

## 12. Encoder tự viết phải xử lý lỗi khi cấp phát buffer

Encoder tạo DataBuffer để downstream ghi ra HTTP. Nếu serialization lỗi sau khi đã allocate buffer nhưng trước khi phát buffer ra ngoài, encoder phải tự release buffer chưa chuyển quyền sở hữu.

Ví dụ quản lý buffer trong một đoạn encode:

~~~java
DataBuffer buffer = factory.allocateBuffer();
boolean handedOff = false;

try {
    // Serialize value and write bytes into buffer.
    serialize(value, buffer);
    handedOff = true;
    return buffer;
}
finally {
    if (!handedOff) {
        DataBufferUtils.release(buffer);
    }
}
~~~

Đây là mẫu ownership, cần được đặt trong implementation Encoder phù hợp. Sau khi buffer được phát thành công, consumer downstream chịu trách nhiệm release khi ghi xong. Không release ngay sau khi return buffer nếu consumer còn phải đọc nó.

## 13. Giới hạn bộ nhớ và DataBufferLimitException

Một số decoder/reader phải buffer một phần hoặc toàn bộ body trong RAM. Ví dụ:

- @RequestBody byte[] cần tạo một mảng byte hoàn chỉnh.
- Form URL encoded cần tổng hợp dữ liệu để tạo MultiValueMap.
- JSON object đơn có thể cần đọc body để tạo một DTO.
- Decoder streaming phải tách byte thành từng record/object.
- Multipart cần phân tích từng part và có thể giữ non-file part trong memory.

Các default codec có giới hạn buffering; tài liệu Spring hiện hành nêu mặc định thường là **256 KiB** cho các codec áp dụng giới hạn này. Khi vượt quá giới hạn, ứng dụng có thể nhận DataBufferLimitException với thông báo vượt quá max bytes to buffer.

### 13.1. Cấu hình maxInMemorySize

Phía server:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
            .maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

Phía WebClient:

~~~java
WebClient client = WebClient.builder()
    .codecs(configurer -> configurer.defaultCodecs()
        .maxInMemorySize(2 * 1024 * 1024))
    .build();
~~~

Hai ví dụ đặt giới hạn 2 MiB cho default codecs có hỗ trợ cấu hình đó. Cấu hình client không thay đổi giới hạn server và ngược lại.

### 13.2. Streaming: giới hạn có thể tính theo từng object

Với decoder cần tách một luồng thành nhiều object, maxInMemorySize thường áp dụng cho số byte cần buffer để tạo **một object** trong stream, không phải tổng byte của toàn bộ stream.

Ví dụ NDJSON có thể phát hàng triệu dòng nhỏ; nếu decoder xử lý từng dòng, tổng stream có thể lớn hơn giới hạn nhưng từng record vẫn nằm dưới ngưỡng. Một dòng JSON duy nhất quá lớn vẫn có thể vượt giới hạn.

Đây là lý do cần phân biệt:
- Một body được gom thành một object.
- Một stream dài gồm nhiều object độc lập.
- Một stream byte được chuyển tiếp mà không cần tổng hợp.

Không tăng giới hạn toàn cục chỉ để làm một endpoint upload lớn hoạt động. Hãy cân nhắc streaming, giới hạn kích thước nghiệp vụ, lưu file theo luồng và cấu hình codec phù hợp.

### 13.3. Multipart có các giới hạn riêng

Với multipart:
- maxInMemorySize giới hạn kích thước non-file part được giữ trong memory.
- Với file part, giá trị này là ngưỡng trước khi nội dung được ghi xuống disk theo reader implementation.
- maxDiskUsagePerPart giới hạn dung lượng disk cho từng file part.
- maxParts giới hạn tổng số part trong request.

Nếu cần kiểm soát cả ba, cấu hình MultipartHttpMessageReader/DefaultPartHttpMessageReader tương ứng rồi đăng ký reader đã cấu hình qua ServerCodecConfigurer. Không coi maxInMemorySize là giới hạn tổng upload size hoặc giới hạn disk đầy đủ.

### 13.4. Tăng giới hạn không đồng nghĩa tăng khả năng chịu tải

Nếu nâng maxInMemorySize lên rất lớn, nhiều request đồng thời có thể giữ lượng RAM đáng kể. Ví dụ 100 request cùng buffer 20 MiB có thể tạo áp lực xấp xỉ 2 GiB chỉ riêng phần body đang giữ, chưa tính object graph và overhead.

Hãy kết hợp:
- Giới hạn kích thước request ở gateway/server và tầng nghiệp vụ.
- Streaming cho file hoặc dữ liệu lớn.
- Giới hạn concurrency và queue.
- Đo heap/direct memory, GC và số request đồng thời.
- Chọn maxInMemorySize theo kích thước record thực tế.

DataBufferLimitException không tự cho biết chính sách nghiệp vụ nào phù hợp. Ứng dụng có thể ánh xạ lỗi sang status và error body theo hợp đồng API; đừng giả định status cố định nếu chưa cấu hình exception handling.

## 14. Cấu hình multipart và streaming

### 14.1. FilePart

Đối với upload file, FilePart cho phép chuyển nội dung file tới đích mà không cần biến toàn bộ file thành byte[]:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<String> upload(@RequestPart("file") FilePart file) {
    Path destination = Paths.get("/tmp/uploads")
        .resolve(UUID.randomUUID().toString());

    return file.transferTo(destination)
        .thenReturn(destination.getFileName().toString());
}
~~~

Đây là snippet tích hợp. Dùng tên file do server tạo; nếu dùng filename của client để hiển thị hoặc lưu metadata, phải validate và không nối trực tiếp vào đường dẫn filesystem. Cần giới hạn kích thước, quyền truy cập, loại nội dung, disk quota và cleanup file tạm.

### 14.2. PartEvent khi cần stream multipart

Với upload lớn hoặc nhiều part, WebFlux có API PartEvent để xử lý multipart theo luồng. Cách này cho phép nhận từng part/event và xử lý dữ liệu theo từng buffer thay vì tạo một MultiValueMap chứa toàn bộ multipart. Khi dùng PartEvent, phải tuân thủ ownership/release của DataBuffer và tiêu thụ từng part theo API contract.

### 14.3. NDJSON và SSE

NDJSON phù hợp cho nhiều object JSON phân tách bằng newline. SSE phù hợp cho event stream có framing riêng và có thể có id/retry/event name. Với cả hai, gửi dữ liệu định kỳ/heartbeat để client disconnect được phát hiện sớm hơn và cân nhắc giới hạn thời gian, số subscriber, cancellation.

## 15. Ví dụ Java 17 chạy được: JSON, NDJSON và DataBuffer

Ví dụ dùng Spring Boot 3.3.5, Java 17 và WebFlux. Boot quản lý bộ Spring Framework/Reactor tương thích. Ứng dụng minh họa:
- JSON request/response được xử lý bằng reader/writer mặc định.
- Flux<Book> được ghi thành NDJSON.
- Một endpoint nhận Flux<DataBuffer>, join có giới hạn và release buffer.
- ServerCodecConfigurer cấu hình giới hạn buffering.

### 15.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 15.2. src/main/java/demo/CodecDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CodecDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CodecDemoApplication.class, args);
    }
}
~~~

### 15.3. src/main/java/demo/CodecConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
            .maxInMemorySize(512 * 1024);
    }
}
~~~

### 15.4. src/main/java/demo/BookController.java

~~~java
package demo;

import java.net.URI;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record CreateBookRequest(String title, String author) {}
record Book(String id, String title, String author) {}

@RestController
@RequestMapping("/api/books")
class BookController {

    private final ConcurrentMap<String, Book> books =
        new ConcurrentHashMap<>();

    private final AtomicInteger sequence = new AtomicInteger(2);

    BookController() {
        books.put("b-1",
            new Book("b-1", "Reactive Basics", "An"));
        books.put("b-2",
            new Book("b-2", "WebFlux in Practice", "Binh"));
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    Flux<Book> list() {
        return Flux.fromIterable(books.values());
    }

    @GetMapping(
        path = "/stream",
        produces = "application/x-ndjson"
    )
    Flux<Book> stream() {
        return Flux.fromIterable(books.values());
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<Book>> get(@PathVariable String id) {
        return Mono.justOrEmpty(books.get(id))
            .map(book -> ResponseEntity.ok(book))
            .defaultIfEmpty(ResponseEntity.<Book>notFound().build());
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<Book>> create(
            @RequestBody Mono<CreateBookRequest> body) {
        return body.map(request -> {
            String id = "b-" + sequence.incrementAndGet();
            Book book = new Book(
                id, request.title(), request.author()
            );
            books.put(id, book);

            return ResponseEntity
                .created(URI.create("/api/books/" + id))
                .body(book);
        });
    }

    @PostMapping(
        path = "/raw-size",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<Integer> rawSize(@RequestBody Flux<DataBuffer> body) {
        return DataBufferUtils.join(body, 1024 * 1024)
            .map(buffer -> {
                try {
                    return buffer.readableByteCount();
                }
                finally {
                    DataBufferUtils.release(buffer);
                }
            })
            .defaultIfEmpty(0);
    }
}
~~~

Endpoint raw-size chỉ tổng hợp tối đa 1 MiB để minh họa. Ứng dụng thực tế nên tránh join file lớn và xử lý theo luồng hoặc ghi xuống storage.

### 15.5. src/test/java/demo/BookControllerTest.java

~~~java
package demo;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class BookControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void jsonReaderAndWriterHandleBookList() {
        client.get()
            .uri("/api/books")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody(byte[].class)
            .value(bytes -> {
                String body = new String(bytes, StandardCharsets.UTF_8);
                assertTrue(body.contains("Reactive Basics"));
                assertTrue(body.contains("WebFlux in Practice"));
            });
    }

    @Test
    void ndjsonWriterStreamsIndividualBooks() {
        client.get()
            .uri("/api/books/stream")
            .accept(MediaType.valueOf("application/x-ndjson"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.valueOf("application/x-ndjson")
                )
            .expectBody(byte[].class)
            .value(bytes -> {
                String body = new String(bytes, StandardCharsets.UTF_8);
                assertTrue(body.contains("\"id\":\"b-1\""));
                assertTrue(body.contains("\"id\":\"b-2\""));
            });
    }

    @Test
    void jsonReaderDecodesCreateRequest() {
        client.post()
            .uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateBookRequest(
                "Codec Handbook", "Chi"
            ))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody()
            .jsonPath("$.title").isEqualTo("Codec Handbook");
    }

    @Test
    void dataBufferBodyIsJoinedAndReleased() {
        byte[] bytes = "abcdef".getBytes(StandardCharsets.UTF_8);

        client.post()
            .uri("/api/books/raw-size")
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(bytes)
            .exchange()
            .expectStatus().isOk()
            .expectBody(Integer.class)
            .isEqualTo(6);
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Bốn test kiểm tra:
- JSON reader giải mã request DTO và JSON writer ghi list response.
- NDJSON writer ghi từng book thành dòng JSON.
- POST trả status 201 và Location.
- Endpoint raw-size đọc body DataBuffer, join trong giới hạn và release buffer sau khi đếm.

Dữ liệu ban đầu có hai book cố định nên hai test đọc list có thể kiểm tra tên cụ thể. Test POST thêm book vào map trong context test; nếu mở rộng test chạy song song hoặc phụ thuộc thứ tự, nên tạo fixture/reset store riêng cho mỗi test.

### 15.6. Gọi API bằng curl

Liệt kê JSON:

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/books
~~~

Nhận NDJSON:

~~~bash
curl -i -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/books/stream
~~~

Tạo book:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Codec Handbook","author":"Chi"}'
~~~

Gửi raw bytes:

~~~bash
curl -i -X POST http://localhost:8080/api/books/raw-size \
  -H "Content-Type: application/octet-stream" \
  --data-binary "abcdef"
~~~

Response cuối cùng là số JSON 6. ID book mới tăng theo sequence bắt đầu từ b-3. Các lệnh tạo dữ liệu thay đổi map trong process hiện tại.

## 16. WebClient đọc stream và xử lý DataBuffer

Khi client nhận body lớn, có thể dùng bodyToFlux để xử lý object theo từng phần tử:

~~~java
Flux<Book> books = webClient.get()
    .uri("/api/books/stream")
    .accept(MediaType.valueOf("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(Book.class);
~~~

Nếu cần thao tác trực tiếp byte, có thể nhận DataBuffer:

~~~java
Flux<DataBuffer> buffers = webClient.get()
    .uri("/exports/archive")
    .retrieve()
    .bodyToFlux(DataBuffer.class);
~~~

Khi làm việc với DataBuffer từ WebClient, phải tiêu thụ hoặc chuyển quyền sở hữu rõ ràng. Nếu ghi xuống file/channel, ưu tiên DataBufferUtils.write hoặc Resource/streaming API phù hợp và tuân thủ contract của API đang dùng. Nếu tự đọc rồi bỏ buffer, release đúng cách. Không thu tất cả buffer vào List<DataBuffer> để giữ mãi trong heap/direct memory.

## 17. Logging và quan sát codec

Khi debug lỗi decode/encode, kiểm tra:

1. Request Content-Type và response Accept.
2. Kiểu Java thực tế của tham số/return value.
3. Reader/writer có hỗ trợ media type đó không.
4. Jackson/codec dependency và cấu hình ObjectMapper.
5. maxInMemorySize và kích thước record/body.
6. Exception gốc: decode error, DataBufferLimitException, codec-not-found hay lỗi serialization.
7. Direct memory và leak detector nếu đang dùng pooled Netty buffers.

Không bật log request/response body một cách vô điều kiện trong production: payload có thể chứa mật khẩu, token hoặc dữ liệu cá nhân; logging cũng có thể làm tăng allocation và chi phí I/O. Chỉ log metadata cần thiết và che dữ liệu nhạy cảm.

Khi chạy Reactor Netty, có thể bật Netty leak detection ở môi trường phát triển/test để phát hiện buffer không được release. Mức kiểm tra chi tiết có chi phí hiệu năng; không mặc định bật chế độ nặng nhất trên production traffic.

## 18. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ Encoder và HttpMessageWriter là một interface | Không phân biệt được encode bytes với ghi HTTP message | Hiểu writer là tầng HTTP; encoder là codec cấp thấp |
| Nghĩ mọi reader/writer đều bọc Decoder/Encoder | Bỏ qua reader/writer chuyên biệt cho form, multipart, SSE | Dùng interface phù hợp với định dạng |
| Content-Type không khớp consumes/reader | Request có thể bị từ chối 415 | Gửi đúng media type và đăng ký reader hỗ trợ |
| Accept không khớp produces/writer | Response có thể bị từ chối 406 | Điều chỉnh Accept/produces hoặc thêm writer |
| Dùng application/json cho stream vô hạn | Client phải xử lý JSON array có cấu trúc dài; lỗi giữa stream khó phục hồi | Cân nhắc NDJSON hoặc SSE theo hợp đồng |
| Join file lớn thành một DataBuffer | Tăng bộ nhớ và có thể vượt maxInMemorySize | Xử lý từng buffer hoặc stream xuống file |
| Tăng maxInMemorySize rất lớn cho mọi codec | Nhiều request đồng thời có thể giữ RAM/direct memory lớn | Giới hạn theo endpoint và dùng streaming |
| Quên release pooled DataBuffer | Direct memory leak | Dùng DataBufferUtils.release và xác định ownership |
| Release buffer sau khi chuyển cho response writer | Writer có thể đọc buffer đã bị giải phóng | Chuyển quyền sở hữu; để writer release |
| Release hai lần | IllegalReferenceCountException | Theo dõi retain/release và ownership |
| Decoder bỏ qua buffer bị discard | Buffer leak khi filter/skip/cancel | Dùng doOnDiscard và cleanup state riêng |
| Encoder không release buffer khi serialization lỗi | Buffer chưa phát bị leak | Dùng try/finally trước khi handoff |
| Nghĩ maxInMemorySize là giới hạn tổng stream | Hiểu sai giới hạn cho NDJSON/stream | Kiểm tra limit theo từng object của decoder |
| Nghĩ maxInMemorySize kiểm soát mọi multipart quota | Có thể thiếu giới hạn disk và số part | Cấu hình maxDiskUsagePerPart và maxParts |
| Tắt registerDefaults(false) rồi quên JSON codec | Controller không còn đọc/ghi định dạng phổ biến | Chỉ tắt khi tự cấu hình đầy đủ danh sách codec |
| Thêm custom codec nhưng không kiểm tra canRead/canWrite | Codec không được chọn hoặc xung đột codec khác | Kiểm tra kiểu, media type và thứ tự đăng ký |
| Tự tạo DataBufferFactory gắn với Netty trong code chung | Code phụ thuộc server implementation | Lấy factory từ request/response hoặc client request |
| Buffer body thành byte[] khi không cần | Mất lợi ích streaming, tăng heap | Dùng Flux/DataBuffer/Resource phù hợp |

## 19. Checklist thiết kế codec và buffer

Trước khi triển khai endpoint hoặc custom codec, hãy kiểm tra:

1. **Kiểu dữ liệu:** body là DTO, String, Resource, byte[] hay stream?
2. **Media type:** request Content-Type và response Accept/produces có tương thích không?
3. **Tầng abstraction:** cần custom Encoder/Decoder hay custom HttpMessageReader/Writer?
4. **Streaming:** có cần đọc/ghi từng record hay có thể tổng hợp một body hữu hạn?
5. **Memory bound:** maxInMemorySize có phù hợp kích thước một object/part không?
6. **Multipart:** đã đặt giới hạn non-file memory, disk per part và maxParts chưa?
7. **Buffer ownership:** ai release buffer khi thành công, lỗi và cancellation?
8. **Discard:** custom decoder có doOnDiscard hoặc cleanup cho buffer bị bỏ không?
9. **Client/server parity:** WebClient có cấu hình codec/media type tương thích server không?
10. **Test:** WebTestClient/WebClient đã kiểm tra JSON, stream, sai media type, body lớn và cancellation chưa?
11. **Observability:** có log metadata và theo dõi direct memory/leak mà không lộ payload nhạy cảm không?
12. **Version:** custom codec API và dependency Jackson/Protobuf/XML có tương thích Spring Framework/Boot đang chạy không?

**Ghi nhớ:** Encoder/Decoder chuyển đổi giữa object và DataBuffer; HttpMessageReader/HttpMessageWriter áp dụng việc đó cho HTTP message và media type. Codec mặc định xử lý phần lớn JSON, text, binary, form, multipart và SSE. Khi tự làm việc với DataBuffer, hãy xác định ownership và release trong mọi đường thành công, lỗi và cancellation. Đặt giới hạn buffering theo kích thước dữ liệu cần xử lý, và dùng streaming khi body lớn hoặc không có kích thước hữu hạn.

## Tài liệu tham khảo

- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework — Reactive Core and HTTP Message Codecs: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — WebFlux Configuration, HTTP Message Codecs: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework — WebClient Configuration and Codec Limits: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework — HttpMessageReader API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/HttpMessageReader.html
- Spring Framework — HttpMessageWriter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/HttpMessageWriter.html
- Spring Framework — CodecConfigurer API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/CodecConfigurer.html
- Spring Boot — Reactive Web Applications and Codecs: https://docs.spring.io/spring-boot/reference/web/reactive.html
