# Phân biệt giải mã một đối tượng với giải mã một chuỗi đối tượng trong Spring WebFlux

Trong Spring WebFlux, dữ liệu HTTP đi vào dưới dạng các byte được chia thành nhiều phần. Trước khi controller hoặc WebClient nhận được một đối tượng Java, một **codec** phải đọc các byte, nhận biết định dạng, giải mã và chuyển chúng thành kiểu dữ liệu mà ứng dụng yêu cầu.

Điểm quan trọng của bài này là phân biệt hai mục tiêu:

- **Giải mã một giá trị:** một body được chuyển thành một đối tượng Java, thường được biểu diễn bằng **Mono<T>**.
- **Giải mã một chuỗi giá trị:** body được đọc thành nhiều đối tượng Java, thường được biểu diễn bằng **Flux<T>**.

Sự khác nhau không chỉ nằm ở Mono và Flux. Nó còn phụ thuộc vào kiểu Java đích, cấu trúc dữ liệu trên wire, media type, khả năng streaming của codec và giới hạn bộ nhớ. Ví dụ, cùng một JSON array có thể được đọc thành **Mono<List<Event>>** (một giá trị là cả danh sách) hoặc **Flux<Event>** (nhiều giá trị Event riêng biệt).

Bài học thuộc nhóm **Codec và bộ đệm**, tập trung vào cách WebFlux giải mã một object và một sequence, cách JSON array khác NDJSON, vai trò của DataBuffer và cách kiểm soát bộ nhớ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của Encoder, Decoder, HttpMessageReader và HttpMessageWriter.
- Phân biệt decode một object với decode một stream các object.
- Chọn Mono<T>, Mono<List<T>> hoặc Flux<T> theo cardinality mong muốn.
- Hiểu JSON object, JSON array và NDJSON là ba dạng payload khác nhau.
- Mô tả cách Jackson2JsonDecoder phát các phần tử khi giải mã Flux.
- Hiểu vì sao một DataBuffer không tương đương một JSON object hoặc một record.
- Dùng WebClient bodyToMono và bodyToFlux đúng kiểu.
- Trả Flux dưới application/json hoặc application/x-ndjson theo semantics cần thiết.
- Quản lý maxInMemorySize, DataBufferLimitException và pooled DataBuffer.
- Viết ứng dụng Java 17+ và kiểm thử bằng WebTestClient.

## 2. Bức tranh tổng thể: từ byte đến object

HTTP request body không đến ứng dụng dưới dạng một object Java. Server nhận các byte từ network; WebFlux chuyển chúng qua message reader và codec trước khi method handler xử lý dữ liệu.

~~~text
HTTP request body
       |
       v
Network byte chunks
       |
       v
DataBuffer stream
       |
       v
HttpMessageReader
       |
       v
Decoder / Codec
       |
       +------------------------------+
       |                              |
       v                              v
Một giá trị Java                 Nhiều giá trị Java
Mono<T>                         Flux<T>
       |                              |
       v                              v
Controller / WebClient consumer
~~~

Các lớp có trách nhiệm khác nhau:

- **DataBuffer:** biểu diễn một vùng byte. Nó có thể bao bọc byte buffer thông thường hoặc buffer được pool bởi server như Reactor Netty.
- **Decoder<T>:** hợp đồng mức thấp chuyển Publisher<DataBuffer> thành publisher của kiểu T.
- **HttpMessageReader<T>:** tích hợp việc decode với HTTP message, media type, headers và hints.
- **HttpMessageWriter<T>:** ghi giá trị Java ra HTTP body thông qua encoder.
- **Encoder<T>:** chuyển publisher của T thành stream DataBuffer.
- **Codec:** cách gọi chung cho thành phần encode/decode; trong WebFlux thường là một cặp reader/writer hoặc encoder/decoder.

Ở phía server, @RequestBody được xử lý bằng các HttpMessageReader đã cấu hình. Ở phía client, WebClient dùng các codec tương tự để giải mã response và encode request. Vì vậy, cùng một định dạng có thể được xử lý nhất quán ở hai phía.

## 3. Một object: Mono<T>

Khi ứng dụng mong đợi đúng một object, kiểu reactive phù hợp thường là **Mono<T>**.

Ví dụ payload JSON:

~~~json
{
  "id": "evt-1",
  "sequence": 1
}
~~~

Kiểu Java:

~~~java
public record Event(String id, int sequence) {
}
~~~

Controller có thể nhận:

~~~java
@PostMapping("/events/one")
public Mono<Event> receiveOne(@RequestBody Mono<Event> body) {
    return body;
}
~~~

WebFlux đọc body, chọn reader phù hợp với application/json, rồi decoder chuyển document thành một Event. Publisher phát tối đa một Event và hoàn tất.

Ở phía WebClient:

~~~java
Mono<Event> event = webClient.get()
    .uri("/events/evt-1")
    .retrieve()
    .bodyToMono(Event.class);
~~~

bodyToMono(Event.class) nói với WebClient rằng response được mong đợi là một giá trị Event. Kiểu đích giúp codec chọn cách giải mã phù hợp.

### Một object không đồng nghĩa một DataBuffer

Một JSON object có thể đến qua nhiều DataBuffer:

~~~text
DataBuffer #1: {"id":"ev
DataBuffer #2: t-1","seq
DataBuffer #3: uence":1}
                  |
                  v
       Decoder giữ trạng thái parse
                  |
                  v
             Event(...)
~~~

Các ranh giới buffer do network và server quyết định. Một JSON object có thể bị chia giữa hai buffer; ngược lại, một buffer có thể chứa nhiều phần của document hoặc nhiều record. Không được giả định mỗi lần onNext(DataBuffer) tương ứng với một object hoàn chỉnh.

Decoder phải giữ trạng thái parse qua các buffer cho tới khi có đủ byte để tạo giá trị. Với Jackson non-blocking parser, quá trình này có thể diễn ra mà không cần gom toàn bộ response thành một String trước.

## 4. Một danh sách trong một giá trị: Mono<List<T>>

Có một trường hợp dễ nhầm: ứng dụng nhận một JSON array nhưng muốn coi **cả danh sách là một giá trị duy nhất**.

Payload:

~~~json
[
  {"id":"evt-1","sequence":1},
  {"id":"evt-2","sequence":2}
]
~~~

Kiểu đích:

~~~java
Mono<List<Event>>
~~~

Controller:

~~~java
@PostMapping("/events/array-as-list")
public Mono<List<Event>> receiveArrayAsList(
        @RequestBody Mono<List<Event>> body) {
    return body;
}
~~~

Mono phát một đối tượng List chứa hai Event. Handler nhận danh sách sau khi codec đã decode cấu trúc array thành collection. Cách này phù hợp khi nghiệp vụ cần xử lý toàn bộ batch như một đơn vị, ví dụ kiểm tra tổng số phần tử, xác nhận tính nhất quán toàn danh sách hoặc thực hiện một thao tác batch.

WebClient có thể đọc cùng payload bằng kiểu generic:

~~~java
Mono<List<Event>> events = webClient.get()
    .uri("/events/array")
    .retrieve()
    .bodyToMono(new ParameterizedTypeReference<List<Event>>() {});
~~~

Do Java type erasure, khi cần truyền kiểu generic như List<Event>, hãy dùng ParameterizedTypeReference để giữ thông tin kiểu cho codec. List.class đơn thuần không cho biết phần tử bên trong là Event.

### Mono<List<T>> và Flux<T> khác nhau ở cardinality

| Kiểu | Số tín hiệu được phát | Giá trị mỗi tín hiệu |
| --- | --- | --- |
| Mono<Event> | 0 hoặc 1 | Một Event |
| Mono<List<Event>> | 0 hoặc 1 | Một List chứa nhiều Event |
| Flux<Event> | 0 đến nhiều | Mỗi tín hiệu là một Event |

Mono<List<Event>> vẫn là publisher một giá trị. Flux<Event> là publisher nhiều giá trị. Dù hai kiểu có thể đọc cùng một JSON array, cách controller/service nhận và xử lý dữ liệu khác nhau.

## 5. Một chuỗi object: Flux<T>

Khi muốn xử lý từng object riêng biệt, dùng **Flux<T>**.

~~~java
@PostMapping("/events/array-as-flux")
public Flux<Event> receiveArrayAsFlux(
        @RequestBody Flux<Event> body) {
    return body;
}
~~~

Với Jackson JSON decoder của Spring, khi kiểu đích là Flux, parser có thể phát từng object khi đã nhận đủ byte để hoàn thành object đó. Nội dung đầu vào có thể là JSON array hoặc định dạng JSON phân tách theo dòng như NDJSON.

WebClient đọc chuỗi object:

~~~java
Flux<Event> events = webClient.get()
    .uri("/events/stream")
    .accept(MediaType.valueOf("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(Event.class);
~~~

Mỗi phần tử của Flux là một Event. Consumer có thể xử lý từng phần tử bằng map, flatMap, concatMap, buffer hoặc ghi vào một sink phù hợp.

~~~java
Flux<Event> saved = events.concatMap(repository::save);
~~~

concatMap giữ thứ tự và chờ thao tác lưu phần tử hiện tại hoàn tất trước khi chuyển sang phần tử kế tiếp. Nếu nghiệp vụ cho phép xử lý song song, có thể dùng flatMap với concurrency được giới hạn có chủ đích.

**Không nên mặc định Flux nghĩa là dữ liệu vô hạn.** Flux có thể phát 0 phần tử, một phần tử hoặc hàng triệu phần tử rồi hoàn tất. Khác biệt nằm ở cardinality và cách tiêu thụ, không nằm ở việc stream có bắt buộc kéo dài mãi hay không.

## 6. JSON object, JSON array và NDJSON

Để giải mã một hay nhiều object, trước hết phải hiểu cấu trúc payload trên wire.

### JSON object: một document có root object

~~~json
{"id":"evt-1","sequence":1}
~~~

Đây là một JSON document chứa một object. Nó thường được giải mã thành Mono<Event>.

### JSON array: một document chứa nhiều object

~~~json
[
  {"id":"evt-1","sequence":1},
  {"id":"evt-2","sequence":2}
]
~~~

Đây vẫn là **một JSON document**, có root là array. Codec có thể:

- Decode thành một List trong Mono<List<Event>>.
- Decode thành các phần tử riêng trong Flux<Event> nếu decoder hỗ trợ streaming array.

Điểm thứ hai rất hữu ích: một JSON array không bắt buộc phải được chuyển thành một List lớn trước khi controller có thể nhận phần tử đầu tiên. Jackson non-blocking decoder có thể phát từng object khi object đó đã hoàn chỉnh.

### NDJSON: nhiều JSON document được phân tách theo dòng

NDJSON (Newline Delimited JSON, thường dùng media type application/x-ndjson) có dạng:

~~~text
{"id":"evt-1","sequence":1}
{"id":"evt-2","sequence":2}
{"id":"evt-3","sequence":3}
~~~

Mỗi dòng là một JSON value độc lập. Đây là định dạng phù hợp cho stream vì receiver có thể parse một record khi dòng đó hoàn tất, trong khi các record tiếp theo vẫn đang được truyền.

NDJSON không phải một JSON array. Toàn bộ ba dòng trên không phải một JSON document chuẩn duy nhất nếu chỉ nối bằng newline. Client và server phải thống nhất media type và quy tắc framing.

### So sánh payload

| Định dạng | Ví dụ hình dạng | Ý nghĩa | Dùng phổ biến |
| --- | --- | --- | --- |
| JSON object | {...} | Một document, một object | Mono<T> |
| JSON array | [{...},{...}] | Một document, nhiều object | Mono<List<T>> hoặc Flux<T> |
| NDJSON | Một JSON value mỗi dòng | Nhiều JSON value phân tách theo dòng | Flux<T> streaming |

Không gửi các object JSON nối liền tùy ý như {"id":"a"}{"id":"b"} mà không có framing rõ ràng. Hãy dùng JSON array, NDJSON hoặc một giao thức sequence đã định nghĩa.

## 7. Decoder.decodeToMono và Decoder.decode

Ở tầng Spring Core, interface **Decoder<T>** mô tả cách chuyển byte stream thành object stream. Hai phương thức quan trọng là:

~~~java
Mono<T> decodeToMono(
    Publisher<DataBuffer> input,
    ResolvableType elementType,
    MimeType mimeType,
    Map<String, Object> hints);

Flux<T> decode(
    Publisher<DataBuffer> input,
    ResolvableType elementType,
    MimeType mimeType,
    Map<String, Object> hints);
~~~

Ý nghĩa:

- **decodeToMono:** giải mã input thành tối đa một giá trị T. Decoder có thể phải gom đủ byte để tạo một giá trị hoàn chỉnh.
- **decode:** giải mã input thành một Flux<T>, có thể phát từng giá trị khi đủ dữ liệu cho một phần tử.

Hai API nhận ResolvableType thay vì chỉ Class vì kiểu đích có thể là generic như List<Event>. MimeType giúp decoder chọn định dạng phù hợp; hints truyền thêm thông tin cho quá trình decode.

Đây là hợp đồng codec mức thấp, độc lập với HTTP. Một decoder cũng có thể có phương thức decode một DataBuffer đã chứa trọn message, phù hợp với những định dạng mà mỗi message đã được đóng khung trước.

### HttpMessageReader ở tầng HTTP

WebFlux dùng **HttpMessageReader<T>** để đọc nội dung HTTP. Các phương thức chính tương ứng với hai cardinality:

~~~java
Mono<T> readMono(
    ResolvableType elementType,
    ReactiveHttpInputMessage message,
    Map<String, Object> hints);

Flux<T> read(
    ResolvableType elementType,
    ReactiveHttpInputMessage message,
    Map<String, Object> hints);
~~~

HttpMessageReader còn có thể kiểm tra canRead(elementType, mediaType) và công bố các media type mà nó hỗ trợ. Vì thế, WebFlux có thể chọn reader dựa trên kiểu tham số handler và Content-Type của request.

Thông thường ứng dụng không gọi trực tiếp decodeToMono hoặc readMono. Khi khai báo @RequestBody Mono<T>, @RequestBody Flux<T>, hoặc gọi WebClient bodyToMono/bodyToFlux, framework tự chọn reader/decoder thích hợp.

### Sơ đồ quan hệ

~~~text
@RequestBody Mono<T> / WebClient.bodyToMono(T)
                  |
                  v
          HttpMessageReader.readMono
                  |
                  v
          Decoder.decodeToMono
                  |
                  v
                Mono<T>


@RequestBody Flux<T> / WebClient.bodyToFlux(T)
                  |
                  v
           HttpMessageReader.read
                  |
                  v
             Decoder.decode
                  |
                  v
                Flux<T>
~~~

Tương tự theo chiều ghi, HttpMessageWriter sử dụng Encoder để biến publisher của object thành DataBuffer và ghi vào response/request body.

## 8. Jackson JSON giải mã một object và một sequence như thế nào?

Khi Jackson được cài đặt, WebFlux có JSON decoder dựa trên parser non-blocking. Trong Spring Framework 6.x, lớp thường gặp là **Jackson2JsonDecoder**.

Cách hoạt động khái quát:

1. Parser nhận DataBuffer theo từng phần.
2. Parser duy trì trạng thái qua các byte chunks và tạo token buffer cho JSON value hoàn chỉnh.
3. ObjectMapper chuyển token buffer thành kiểu Java đích.
4. Với kiểu đích một giá trị như Mono, decoder tạo một giá trị.
5. Với kiểu đích nhiều giá trị như Flux, decoder có thể phát từng object ngay khi đã nhận đủ byte để giải mã object đó.

Đầu vào của Flux có thể là JSON array hoặc định dạng line-delimited như NDJSON/JSON Lines. Do đó, một JSON array có thể được decode thành từng phần tử Flux mà không nhất thiết tạo List trước.

### Đọc một object

Với payload:

~~~json
{"id":"evt-1","sequence":1}
~~~

Kiểu đích Event hoặc Mono<Event> tạo một Event. Nếu body chứa một object lớn, decoder cần đủ dữ liệu để giải mã object đó; giới hạn bộ nhớ áp dụng cho phần dữ liệu cần buffer.

### Đọc một array thành Flux

Với payload:

~~~json
[
  {"id":"evt-1","sequence":1},
  {"id":"evt-2","sequence":2},
  {"id":"evt-3","sequence":3}
]
~~~

Kiểu đích Flux<Event> có thể phát lần lượt:

~~~text
onNext(Event("evt-1", 1))
onNext(Event("evt-2", 2))
onNext(Event("evt-3", 3))
onComplete()
~~~

Decoder chỉ phát một Event sau khi token của Event đó đã đầy đủ. Nếu object thứ ba chưa đến, hai object đầu vẫn có thể đã được chuyển cho downstream. Đây là streaming ở tầng decode; tốc độ truyền thực tế còn phụ thuộc server, client, network, publisher và demand.

### Đọc NDJSON thành Flux

Với:

~~~text
{"id":"evt-1","sequence":1}
{"id":"evt-2","sequence":2}
{"id":"evt-3","sequence":3}
~~~

Mỗi dòng là một JSON value. Decoder dùng dấu phân tách theo định dạng để xác định từng record. NDJSON thường phù hợp hơn khi producer muốn phát record độc lập theo thời gian, thay vì phải duy trì một JSON array chưa đóng.

### Lưu ý về encoder: Flux + application/json không mặc nhiên streaming

Chiều encode có một quy tắc dễ bị bỏ qua:

- Với Mono<T>, Jackson encoder serialize một giá trị.
- Với Flux<T> và media type application/json, mặc định encoder thu các phần tử bằng collectToList rồi serialize thành một JSON array.
- Với streaming media type như application/x-ndjson, encoder ghi và flush từng giá trị theo định dạng line-delimited.

Vì vậy, **Flux<T> không tự động có nghĩa response được gửi từng item ra network**. Nếu muốn stream từng record, hãy chọn media type streaming phù hợp và kiểm tra cách client tiêu thụ.

## 9. Chọn Content-Type và Accept đúng với cấu trúc dữ liệu

Hai HTTP header thường quyết định cách codec được chọn:

- **Content-Type:** định dạng của body đang gửi.
- **Accept:** định dạng response mà client muốn nhận.

Ví dụ:

| Body | Content-Type / Accept | Kiểu đích hoặc nguồn |
| --- | --- | --- |
| Một JSON object | application/json | Mono<Event> |
| JSON array, nhận thành list | application/json | Mono<List<Event>> |
| JSON array, phát từng object | application/json | Flux<Event> |
| Nhiều JSON record theo dòng | application/x-ndjson | Flux<Event> |
| Một chuỗi văn bản | text/plain | Mono<String> |
| Nhiều dòng văn bản | text/plain hoặc định dạng text phù hợp | Flux<String> |

JSON array và NDJSON đều có thể biểu diễn nhiều object, nhưng framing khác nhau. JSON array là một document có dấu ngoặc vuông và dấu phẩy; NDJSON là nhiều JSON value tách bằng newline.

Nếu client gửi Accept application/json nhưng endpoint chỉ xuất application/x-ndjson, content negotiation có thể không tìm được representation phù hợp. Nếu Content-Type không được reader nào hỗ trợ, server có thể trả lỗi unsupported media type.

### JSON array response và NDJSON response

Ví dụ một handler trả Flux<Event>:

~~~java
@GetMapping(value = "/events/array", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<Event> array() {
    return Flux.just(
        new Event("evt-1", 1),
        new Event("evt-2", 2));
}
~~~

Response là một JSON array. Encoder mặc định thu các phần tử rồi serialize:

~~~json
[
  {"id":"evt-1","sequence":1},
  {"id":"evt-2","sequence":2}
]
~~~

Nếu muốn gửi từng record:

~~~java
@GetMapping(
    value = "/events/stream",
    produces = "application/x-ndjson")
public Flux<Event> stream() {
    return Flux.just(
        new Event("evt-1", 1),
        new Event("evt-2", 2));
}
~~~

Response là các JSON object được phân tách theo dòng. Encoder có thể ghi và flush từng phần tử. Với stream dài hoặc vô hạn, cần thiết kế heartbeat/keep-alive nếu giao thức và client yêu cầu phát hiện kết nối bị ngắt sớm.

### WebClient đọc một object, một list và một stream

~~~java
Mono<Event> one = webClient.get()
    .uri("/events/evt-1")
    .retrieve()
    .bodyToMono(Event.class);

Mono<List<Event>> batch = webClient.get()
    .uri("/events/array")
    .retrieve()
    .bodyToMono(new ParameterizedTypeReference<List<Event>>() {});

Flux<Event> stream = webClient.get()
    .uri("/events/stream")
    .accept(MediaType.valueOf("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(Event.class);
~~~

Mỗi lời gọi thể hiện rõ cardinality mong muốn. Đừng dùng bodyToMono(Event.class) cho một sequence nhiều Event; nếu cần một collection, dùng ParameterizedTypeReference<List<Event>>; nếu muốn xử lý từng Event, dùng bodyToFlux(Event.class).

### WebClient gửi một object hoặc một sequence

~~~java
Mono<Void> sendOne = webClient.post()
    .uri("/events/one")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new Event("evt-1", 1))
    .retrieve()
    .bodyToMono(Void.class);

Mono<Void> sendStream = webClient.post()
    .uri("/events/stream")
    .contentType(MediaType.valueOf("application/x-ndjson"))
    .body(Flux.just(
        new Event("evt-1", 1),
        new Event("evt-2", 2)), Event.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

bodyValue phù hợp với một object đã có sẵn. body(Publisher, Class) phù hợp với publisher nhiều object. Media type phải khớp hợp đồng endpoint và encoder được cấu hình.

## 10. DataBuffer, giới hạn bộ nhớ và giải phóng buffer

DataBuffer là abstraction byte buffer của Spring Core. Nó có thể dựa trên ByteBuffer của Java NIO hoặc buffer của server như Netty ByteBuf. Một số implementation dùng pool và reference counting để tái sử dụng bộ nhớ.

Khi ứng dụng dùng @RequestBody, WebClient bodyToMono hoặc bodyToFlux với object Java, codec mặc định chịu trách nhiệm đọc và quản lý DataBuffer. Thông thường bạn không cần tự release buffer.

Khi tự đọc raw body hoặc viết custom Decoder, bạn phải quản lý vòng đời buffer cẩn thận.

### Các quy tắc quan trọng

1. **Buffer có thể được pool:** đọc xong phải release nếu code của bạn sở hữu buffer.
2. **Không release buffer do codec vẫn đang quản lý:** ownership phải rõ ràng; release hai lần có thể gây lỗi.
3. **Nếu giữ buffer để xử lý sau:** phải retain theo đúng API và release cân bằng khi xong.
4. **Nếu operator bỏ item:** cần bảo đảm buffer bị discard cũng được release, thường bằng doOnDiscard(DataBuffer.class, DataBufferUtils::release).
5. **Khi lỗi hoặc cancel:** buffer đang được giữ phải được giải phóng.
6. **Khi cần gom nhiều buffer:** ưu tiên DataBufferUtils.join thay vì tự ghép byte array tùy tiện.

Ví dụ về ownership trong custom decoder, chỉ mang tính minh họa:

~~~java
Flux<DecodedValue> decoded = input
    .map(buffer -> {
        try {
            return decodeOneBuffer(buffer);
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    })
    .doOnDiscard(
        DataBuffer.class,
        DataBufferUtils::release);
~~~

Ví dụ trên chỉ đúng khi decodeOneBuffer đọc xong buffer ngay trong callback và không giữ tham chiếu tới nó. Nếu parser cần giữ byte qua nhiều buffer, custom decoder phải thiết kế state, retain/release và xử lý error/cancellation đầy đủ. Không copy đoạn minh họa này vào ứng dụng như một decoder tổng quát.

### DataBufferUtils.join

DataBufferUtils.join có thể gom một Publisher<DataBuffer> thành một DataBuffer tổng hợp, có thể dùng composite buffer để tránh copy khi implementation hỗ trợ. Đây là cách tiện ích và an toàn hơn khi thực sự cần một buffer đầy đủ.

Việc gom toàn bộ body vẫn tiêu thụ bộ nhớ theo kích thước nội dung. Nếu body lớn hoặc là stream dài, cân nhắc giải mã theo từng phần tử thay vì join toàn bộ stream.

### maxInMemorySize

Các decoder và HttpMessageReader có thể buffer một phần hoặc toàn bộ input. WebFlux cung cấp cấu hình giới hạn số byte được buffer trong bộ nhớ. Khi vượt giới hạn, quá trình đọc có thể phát **DataBufferLimitException**.

Giới hạn này hữu ích cho cả hai trường hợp:

- Một object lớn cần được gom đủ trước khi decode.
- Một stream cần buffer một record cho tới khi có đủ byte để tách và decode record đó.

Với decoder streaming, giới hạn thường áp dụng cho lượng byte của từng object/record đang được tách, không phải tổng kích thước của mọi phần tử trong cả stream.

Cấu hình phía server:

~~~java
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

Cấu hình phía WebClient:

~~~java
WebClient client = WebClient.builder()
    .codecs(configurer ->
        configurer.defaultCodecs()
            .maxInMemorySize(512 * 1024))
    .build();
~~~

512 KiB trong ví dụ là giá trị lựa chọn cho demo, không phải khuyến nghị mặc định cho mọi hệ thống. Hãy chọn giới hạn theo kích thước payload hợp lệ, concurrency, bộ nhớ khả dụng và yêu cầu bảo vệ hệ thống.

## 11. Backpressure và streaming thực sự

Flux cho phép downstream yêu cầu dữ liệu theo demand thông qua Reactive Streams. Decoder có thể phát từng object khi object hoàn chỉnh và downstream yêu cầu thêm dữ liệu. Điều này giúp tránh phải tạo một List chứa toàn bộ sequence trước khi xử lý.

Tuy nhiên, có ba tầng cần phân biệt:

1. **Streaming decode:** decoder phát các object riêng lẻ thay vì chờ gom cả danh sách.
2. **Streaming encode:** encoder ghi từng object ra response thay vì thu toàn bộ Flux thành một JSON array.
3. **Streaming transport:** server/client/network thực sự chuyển và flush các phần dữ liệu theo thời gian.

Một endpoint có Flux<Event> nhưng produces application/json có thể vẫn gom toàn bộ giá trị thành một List trước khi ghi response. Ngược lại, NDJSON cho phép encoder ghi từng record và flush theo từng phần tử.

Nếu stream có thể kéo dài lâu, cần cân nhắc heartbeat hoặc keep-alive để phát hiện client đã ngắt kết nối. Nếu client không tiêu thụ đủ nhanh, backpressure và chính sách buffering của pipeline cần được thiết kế để không tạo hàng đợi vô hạn.

### Khi nào dùng từng kiểu?

| Nhu cầu | Kiểu phù hợp | Định dạng thường dùng |
| --- | --- | --- |
| Lấy một tài nguyên | Mono<T> | application/json |
| Nhận batch và validate toàn batch | Mono<List<T>> | application/json array |
| Đọc array rồi xử lý từng phần tử | Flux<T> | application/json array |
| Nhận record liên tục theo thời gian | Flux<T> | application/x-ndjson |
| Phát event cho trình duyệt | Flux<ServerSentEvent<T>> | text/event-stream |

## 12. Cấu hình và khả năng của codec

WebFlux có các codec mặc định cho byte[], ByteBuffer, DataBuffer, Resource, String, JSON và các định dạng khác tùy dependency. Jackson JSON được sử dụng khi Jackson có mặt trên classpath.

Có thể tùy biến codec thông qua:

- **ServerCodecConfigurer:** codec dùng cho server request/response.
- **ClientCodecConfigurer:** codec dùng cho WebClient.
- **WebFluxConfigurer.configureHttpMessageCodecs:** tùy biến reader/writer mặc định hoặc đăng ký codec.
- **WebClient.Builder.codecs:** tùy biến codec phía client.

Không phải mọi decoder đều hỗ trợ streaming decode. Khả năng này phụ thuộc parser và codec:

- Jackson có non-blocking parser và hỗ trợ decode Flux cho JSON array hoặc định dạng line-delimited.
- Gson không có parser non-blocking tương đương; GsonDecoder không hỗ trợ deserialize một số stream Flux và có thể ném UnsupportedOperationException.
- Protobuf JSON decoder không hỗ trợ đọc stream message theo cùng cách với Protobuf binary delimited format.

Hãy kiểm tra tài liệu của codec thực tế đang được cấu hình. Việc một controller khai báo Flux<T> không thể tự bổ sung khả năng streaming mà decoder không hỗ trợ.

### Lưu ý riêng với Flux<String>

Jackson2JsonEncoder và Jackson2JsonDecoder mặc định không xem String là một object JSON cần serialize/deserialize theo cách thông thường. Spring thường xử lý String hoặc sequence String như nội dung văn bản/serialized JSON thông qua CharSequenceEncoder.

Nếu muốn trả một JSON array gồm các chuỗi, hãy cân nhắc collect thành List và encode Mono<List<String>>. Nếu muốn stream các dòng văn bản, dùng media type text phù hợp. Đừng mặc định Flux<String> với application/json luôn tạo JSON array các string.

## 13. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ dưới đây minh họa cùng một JSON array có thể được giải mã thành một List hoặc thành nhiều Event. Nó cũng có endpoint NDJSON để minh họa sequence streaming.

### Cấu trúc project

~~~text
webflux-codec-demo/
├── pom.xml
└── src
    ├── main/java/com/example/codec
    │   ├── CodecDemoApplication.java
    │   ├── Event.java
    │   └── CodecController.java
    └── test/java/com/example/codec
        └── CodecControllerTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webflux-codec-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
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

Spring Boot 3.3.5 quản lý các phiên bản Spring Framework, Reactor và Jackson tương thích. Ví dụ dùng Java 17, Spring WebFlux và JUnit 5.

### CodecDemoApplication.java

~~~java
package com.example.codec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CodecDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CodecDemoApplication.class, args);
    }
}
~~~

### Event.java

~~~java
package com.example.codec;

public record Event(String id, int sequence) {
}
~~~

### CodecController.java

~~~java
package com.example.codec;

import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/codec")
public class CodecController {

    private static final MediaType NDJSON =
        MediaType.valueOf("application/x-ndjson");

    private static final List<Event> EVENTS = List.of(
        new Event("evt-1", 1),
        new Event("evt-2", 2)
    );

    @PostMapping(
        path = "/one",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Event> one(@RequestBody Mono<Event> body) {
        return body;
    }

    @PostMapping(
        path = "/array-as-list",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<List<Event>> arrayAsList(
            @RequestBody Mono<List<Event>> body) {
        return body;
    }

    @PostMapping(
        path = "/array-as-flux",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Event> arrayAsFlux(
            @RequestBody Flux<Event> body) {
        return body;
    }

    @PostMapping(
        path = "/ndjson",
        consumes = "application/x-ndjson",
        produces = "application/x-ndjson")
    public Flux<Event> ndjson(@RequestBody Flux<Event> body) {
        return body;
    }

    @GetMapping(
        path = "/array",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Event> array() {
        return Flux.fromIterable(EVENTS);
    }

    @GetMapping(
        path = "/stream",
        produces = "application/x-ndjson")
    public Flux<Event> stream() {
        return Flux.fromIterable(EVENTS);
    }
}
~~~

Các endpoint thể hiện bốn kiểu xử lý:

- POST /codec/one: một JSON object vào Mono<Event>.
- POST /codec/array-as-list: một JSON array vào Mono<List<Event>>.
- POST /codec/array-as-flux: cùng JSON array nhưng giải mã thành Flux<Event>.
- POST /codec/ndjson: nhiều JSON record phân tách theo dòng vào Flux<Event>.
- GET /codec/array: Flux<Event> được encode thành JSON array.
- GET /codec/stream: Flux<Event> được encode thành NDJSON record stream.

### CodecControllerTests.java

~~~java
package com.example.codec;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@WebFluxTest(CodecController.class)
class CodecControllerTests {

    private static final MediaType NDJSON =
        MediaType.valueOf("application/x-ndjson");

    @Autowired
    private WebTestClient client;

    @Test
    void decodesOneJsonObjectAsMono() {
        client.post()
            .uri("/codec/one")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("id", "evt-1", "sequence", 1))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("{\"id\":\"evt-1\",\"sequence\":1}");
    }

    @Test
    void decodesJsonArrayAsFluxElements() {
        client.post()
            .uri("/codec/array-as-flux")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(List.of(
                Map.of("id", "evt-1", "sequence", 1),
                Map.of("id", "evt-2", "sequence", 2)))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("[{\"id\":\"evt-1\",\"sequence\":1}," +
                  "{\"id\":\"evt-2\",\"sequence\":2}]");
    }

    @Test
    void decodesJsonArrayAsOneListValue() {
        client.post()
            .uri("/codec/array-as-list")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(List.of(
                Map.of("id", "evt-1", "sequence", 1),
                Map.of("id", "evt-2", "sequence", 2)))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("[{\"id\":\"evt-1\",\"sequence\":1}," +
                  "{\"id\":\"evt-2\",\"sequence\":2}]");
    }

    @Test
    void decodesNdjsonAsASequence() {
        Event first = new Event("evt-1", 1);
        Event second = new Event("evt-2", 2);

        FluxExchangeResult<Event> result = client.post()
            .uri("/codec/ndjson")
            .contentType(NDJSON)
            .body(Flux.just(first, second), Event.class)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(NDJSON)
            .returnResult(Event.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(first, second)
            .verifyComplete();
    }

    @Test
    void encodesFluxAsJsonArray() {
        client.get()
            .uri("/codec/array")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("[{\"id\":\"evt-1\",\"sequence\":1}," +
                  "{\"id\":\"evt-2\",\"sequence\":2}]");
    }

    @Test
    void encodesFluxAsNdjsonStream() {
        FluxExchangeResult<Event> result = client.get()
            .uri("/codec/stream")
            .accept(NDJSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(NDJSON)
            .returnResult(Event.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(
                new Event("evt-1", 1),
                new Event("evt-2", 2))
            .verifyComplete();
    }
}
~~~

Chạy test:

~~~bash
mvn -q test
~~~

Nếu sáu test pass, Maven kết thúc với exit code 0. Hai test JSON array dùng cùng payload nhưng chữ ký controller khác nhau: một method nhận một List, method kia nhận từng Event. Hai test NDJSON kiểm tra body publisher được encode/decode theo media type streaming.

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Gửi một object:

~~~bash
curl -i -X POST http://localhost:8080/codec/one -H "Content-Type: application/json" -d "{\"id\":\"evt-1\",\"sequence\":1}"
~~~

Gửi một JSON array:

~~~bash
curl -i -X POST http://localhost:8080/codec/array-as-flux -H "Content-Type: application/json" -d "[{\"id\":\"evt-1\",\"sequence\":1},{\"id\":\"evt-2\",\"sequence\":2}]"
~~~

Gửi NDJSON bằng Bash:

~~~bash
printf '%s\n' '{"id":"evt-1","sequence":1}' '{"id":"evt-2","sequence":2}' |
curl -i -X POST http://localhost:8080/codec/ndjson -H "Content-Type: application/x-ndjson" --data-binary @-
~~~

printf tạo newline thật giữa hai record; --data-binary @- chuyển nguyên nội dung từ standard input cho curl. Cách escape lệnh có thể khác trong PowerShell, nhưng body phải chứa hai JSON record trên hai dòng.

## 14. Lỗi thường gặp và cách khắc phục

1. **Dùng Mono<T> cho nhiều object:** Mono chỉ phát tối đa một giá trị. Dùng Flux<T> hoặc Mono<List<T>> tùy cách xử lý mong muốn.
2. **Nhầm Mono<List<T>> với Flux<T>:** cả hai có thể nhận cùng JSON array, nhưng một bên phát một List, bên kia phát từng T.
3. **Cho rằng JSON array và NDJSON giống nhau:** JSON array là một document; NDJSON là nhiều JSON value phân tách theo dòng.
4. **Giả định mỗi DataBuffer là một object:** network chunk có thể cắt giữa object hoặc chứa nhiều record. Dựa vào codec/framing, không dựa vào ranh giới buffer.
5. **Dùng bodyToMono cho response stream:** client chỉ yêu cầu một giá trị. Dùng bodyToFlux cho sequence.
6. **Dùng bodyToFlux nhưng endpoint chỉ serialize một object:** kiểm tra kiểu dữ liệu và media type thực tế; Flux không tự tạo nhiều phần tử.
7. **Nghĩ Flux + application/json luôn flush từng phần tử:** Jackson encoder mặc định thu Flux thành List để ghi JSON array. Dùng NDJSON hoặc SSE khi cần stream response.
8. **Gửi nhiều JSON object nối liền không delimiter:** không có framing rõ ràng. Dùng JSON array hoặc NDJSON.
9. **Content-Type không khớp consumes:** reader có thể không chọn được codec hoặc request bị từ chối.
10. **Accept không khớp produces:** server không có representation tương thích và có thể trả 406.
11. **Không truyền ParameterizedTypeReference cho List<T>:** Java type erasure làm mất kiểu phần tử; codec không có đủ thông tin generic.
12. **Giả định mọi codec đều hỗ trợ Flux:** khả năng streaming phụ thuộc decoder; kiểm tra codec cụ thể.
13. **Đọc body nhiều lần:** request body là stream; sau khi tiêu thụ, không thể tùy ý đọc lại từ raw body.
14. **Không giới hạn object quá lớn:** một record lớn có thể vượt maxInMemorySize và phát DataBufferLimitException.
15. **Tăng maxInMemorySize vô hạn để tránh lỗi:** điều này có thể khiến một request chiếm nhiều bộ nhớ; chọn giới hạn hợp lý và xử lý payload lớn theo streaming.
16. **Tự ghép DataBuffer rồi quên release:** có thể gây memory leak khi server dùng pooled buffer.
17. **Release buffer do framework đang sở hữu:** có thể gây double-release hoặc lỗi truy cập buffer đã giải phóng.
18. **Không xử lý cancellation trong custom decoder:** client đóng kết nối nhưng buffer đang giữ không được release.
19. **Cho rằng NDJSON luôn có newline cuối:** producer nên kết thúc record bằng newline theo quy ước để parser và công cụ dòng hoạt động nhất quán.
20. **Dùng Flux<String> với Jackson như sequence object JSON:** String có cách xử lý codec riêng; dùng DTO hoặc media type text thích hợp.

## 15. Checklist chọn cách decode

Trước khi khai báo kiểu request/response, hãy xác định:

- **Cardinality:** một object, một List hay nhiều object độc lập?
- **Wire shape:** JSON object, JSON array hay NDJSON?
- **Target type:** Mono<T>, Mono<List<T>> hay Flux<T>?
- **Media type:** Content-Type và Accept có khớp codec không?
- **Codec:** decoder hiện tại có hỗ trợ streaming cho kiểu và media type này không?
- **Generic type:** có cần ParameterizedTypeReference cho collection không?
- **Memory:** một object/record lớn nhất có nằm trong maxInMemorySize không?
- **Backpressure:** downstream có tiêu thụ theo demand hay tạo hàng đợi lớn?
- **Response encoding:** Flux + application/json có thể bị collect; có cần NDJSON/SSE không?
- **Buffer ownership:** code có tự đọc DataBuffer hoặc viết custom codec không?
- **Cancellation:** buffer có được release khi lỗi hoặc client ngắt kết nối không?
- **Testing:** test có phân biệt object, List, Flux array và NDJSON không?

## 16. Bài tập tự kiểm tra

**Bài 1.** JSON body là một object và controller muốn nhận một giá trị Event. Kiểu phù hợp là gì?  
**Đáp án:** Mono<Event> hoặc Event tùy thiết kế đồng bộ/reactive; trong pipeline reactive thường dùng Mono<Event>.

**Bài 2.** JSON body là một array nhưng service muốn nhận toàn bộ danh sách như một đơn vị. Dùng kiểu nào?  
**Đáp án:** Mono<List<Event>>.

**Bài 3.** Cùng JSON array đó nhưng service muốn xử lý từng Event riêng biệt. Dùng kiểu nào?  
**Đáp án:** Flux<Event>; Jackson decoder có thể phát từng phần tử của array khi object đã hoàn chỉnh.

**Bài 4.** NDJSON khác JSON array ở điểm nào?  
**Đáp án:** JSON array là một JSON document có root array; NDJSON là nhiều JSON value độc lập được phân tách bằng newline.

**Bài 5.** Vì sao một JSON object có thể trải qua nhiều DataBuffer?  
**Đáp án:** DataBuffer là network byte chunk, không phải message boundary. Network có thể chia body ở bất kỳ vị trí byte nào.

**Bài 6.** Decoder.decode và decodeToMono khác nhau thế nào?  
**Đáp án:** decode tạo Flux<T> cho nhiều giá trị; decodeToMono tạo Mono<T> cho một giá trị.

**Bài 7.** Flux<Event> trả về với application/json có mặc nhiên flush từng Event không?  
**Đáp án:** Không. Jackson encoder mặc định thu các phần tử thành List rồi serialize thành JSON array. Dùng media type streaming như application/x-ndjson khi cần flush từng record.

**Bài 8.** DataBufferLimitException cho biết điều gì?  
**Đáp án:** Decoder/reader cần buffer nhiều byte hơn giới hạn bộ nhớ đã cấu hình cho nội dung đang xử lý.

**Bài 9.** Vì sao không tự release mọi DataBuffer trong controller?  
**Đáp án:** Codec và framework đang quản lý buffer. Chỉ code trực tiếp sở hữu buffer mới phải release theo đúng vòng đời.

**Bài 10.** WebClient dùng API nào để đọc một Event và nhiều Event?  
**Đáp án:** bodyToMono(Event.class) cho một giá trị; bodyToFlux(Event.class) cho sequence.

**Bài 11.** Một decoder có hỗ trợ decodeToMono thì có chắc hỗ trợ streaming Flux không?  
**Đáp án:** Không. Khả năng multi-value phụ thuộc parser và implementation của decoder.

**Bài 12.** Khi nào nên chọn Mono<List<T>> thay cho Flux<T>?  
**Đáp án:** Khi nghiệp vụ cần toàn bộ batch như một giá trị, cần kiểm tra hoặc xử lý nguyên danh sách, và kích thước batch có giới hạn phù hợp bộ nhớ.

## 17. Ghi nhớ

**Mono<T>** biểu diễn tối đa một object; **Mono<List<T>>** biểu diễn một giá trị là cả danh sách; **Flux<T>** biểu diễn nhiều object riêng biệt. Cùng một JSON array có thể được decode thành List hoặc thành Flux các phần tử, tùy kiểu đích và khả năng của decoder.

JSON array là một JSON document chứa nhiều phần tử. NDJSON là nhiều JSON value được phân tách theo dòng, thường phù hợp hơn cho stream record độc lập. Jackson decoder có thể phát từng object của JSON array hoặc NDJSON vào Flux khi object đã hoàn chỉnh. Ở chiều encode, Flux với application/json mặc định có thể được collect thành List; media type application/x-ndjson cho phép ghi và flush từng record.

DataBuffer là byte chunk, không phải message boundary. Codec quản lý buffer khi ứng dụng làm việc ở tầng object; custom decoder hoặc code đọc raw body phải xử lý ownership, release, discard, cancellation và giới hạn bộ nhớ. Chọn cardinality, media type, codec và maxInMemorySize theo kích thước dữ liệu và semantics thực tế.

### Tài liệu tham khảo

- Spring Framework, [Reactive Core – Codecs and Reactive HTTP Messages](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework, [Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).
- Spring Framework, [WebFlux HTTP Message Codec Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework, [WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Spring Framework, [WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html).
- Spring Framework Javadoc, [Decoder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/codec/Decoder.html).
- Spring Framework Javadoc, [DataBufferUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html).
