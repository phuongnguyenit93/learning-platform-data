# Tránh gom toàn bộ body lớn khi có thể xử lý từng phần trong Spring WebFlux

## 1. Vấn đề: đọc cả request vào RAM làm mất lợi ích streaming

Một endpoint nhận file 2 GB hoặc hàng triệu bản ghi không nên mặc định đọc toàn bộ request vào một object Java rồi mới xử lý. Các cách sau thường gom dữ liệu vào bộ nhớ:

```java
Mono<byte[]> body = request.bodyToMono(byte[].class);
Mono<String> text = request.bodyToMono(String.class);
Mono<List<Event>> events = request.bodyToFlux(Event.class).collectList();
```

Chúng có thể phù hợp với payload nhỏ, có giới hạn rõ ràng. Với body lớn, chúng tạo áp lực bộ nhớ theo kích thước payload và số request đồng thời.

Ví dụ, nếu 20 request cùng gom một body 100 MB, chỉ riêng phần body đã có thể cần khoảng 2 GB bộ nhớ, chưa tính object, buffer trung gian, bản sao khi giải mã, cache và overhead của JVM. Khi nhiều request tăng đồng thời, ứng dụng có thể gặp GC kéo dài, `OutOfMemoryError`, tăng độ trễ hoặc bị hệ điều hành kết thúc.

Spring WebFlux cho phép đọc và ghi body dưới dạng `Mono`/`Flux`. Thay vì đợi toàn bộ body hoàn tất, ứng dụng có thể xử lý từng phần tử hoặc từng `DataBuffer`, rồi chuyển kết quả tiếp theo trong reactive pipeline.

**Mục tiêu không phải là không dùng bộ nhớ.** Mục tiêu là giữ lượng dữ liệu đang được giữ trong RAM ở mức có giới hạn, không tăng theo tổng kích thước body.

## 2. Tư duy streaming: xử lý một phần rồi yêu cầu phần tiếp theo

Luồng dữ liệu có thể hình dung như sau:

```text
HTTP request body
      |
      v
HttpMessageReader / Decoder
      |
      | decode từng phần tử
      v
Flux<Event>
      |
      | validate một phần tử
      v
xử lý / lưu dữ liệu
      |
      | hoàn tất phần tử hiện tại
      v
yêu cầu phần tiếp theo theo demand
      |
      v
Mono<Summary>
```

Reactive Streams có cơ chế **backpressure**. Subscriber báo số phần tử nó sẵn sàng nhận; Publisher không nên phát vô hạn bất chấp demand. Các operator Reactor như `concatMap`, `flatMap` có giới hạn concurrency và `limitRate` giúp kiểm soát tốc độ xử lý.

Ví dụ:

```java
Flux<Event> events = request.bodyToFlux(Event.class);

return events
        .concatMap(event -> eventService.save(event))
        .then();
```

Mỗi event được chuyển tới service theo thứ tự. Pipeline không cần giữ toàn bộ danh sách event trong một `List`.

Nếu cần trả số lượng bản ghi đã xử lý, có thể giữ một bộ đếm nhỏ:

```java
return events
        .concatMap(event -> eventService.save(event).thenReturn(1L))
        .reduce(0L, Long::sum);
```

`reduce` ở đây chỉ giữ một số `long` làm accumulator. Nó khác với `collectList()`, vốn giữ mọi phần tử cho tới khi nguồn hoàn tất.

## 3. Vai trò của codec và HTTP message reader/writer

Trong WebFlux, body không tự biến thành object. Framework chọn `HttpMessageReader` và `Decoder` dựa trên:

- `Content-Type` của request.
- Kiểu đích mà handler khai báo.
- Các codec có trên classpath và cấu hình hiện tại.

Chiều response dùng `HttpMessageWriter` và `Encoder` để chuyển object hoặc Publisher thành byte.

```text
Request bytes
    |
    v
HttpMessageReader
    |
    v
Decoder
    |
    v
Mono<T> / Flux<T>
    |
    | business pipeline
    v
Mono<R> / Flux<R>
    |
    v
Encoder
    |
    v
HttpMessageWriter
    |
    v
Response bytes
```

Ví dụ:

```java
@PostMapping("/events")
Mono<Void> ingest(@RequestBody Flux<Event> events) {
    return events.concatMap(event -> eventService.save(event)).then();
}
```

Spring chọn decoder phù hợp để biến body thành `Flux<Event>`. Khi trả `Flux<Event>` từ controller, encoder tương ứng sẽ ghi các phần tử ra response.

`bodyToFlux` không bảo đảm mọi định dạng đều có cùng đặc tính streaming. Hãy chọn media type và codec hỗ trợ việc tách dữ liệu thành phần tử độc lập. Với dữ liệu dạng bản ghi, NDJSON (`application/x-ndjson`) thường dễ stream hơn một JSON document duy nhất chứa mảng rất lớn.

## 4. Chọn kiểu body theo kích thước và cấu trúc dữ liệu

| Kiểu nhận | Hành vi | Khi phù hợp |
|---|---|---|
| `@RequestBody Dto` hoặc `Mono<Dto>` | Decode một object | JSON nhỏ, có giới hạn |
| `@RequestBody byte[]` | Gom body thành mảng byte | Payload nhỏ, cần toàn bộ bytes |
| `@RequestBody String` | Gom và giải mã toàn bộ body thành text | Văn bản nhỏ, có giới hạn |
| `@RequestBody List<Dto>` | Tạo collection chứa toàn bộ phần tử | Danh sách nhỏ, kích thước xác định |
| `@RequestBody Flux<Dto>` | Phát và xử lý từng phần tử | Stream bản ghi hoặc JSON sequence |
| `@RequestBody Flux<DataBuffer>` | Nhận trực tiếp các buffer byte | Proxy, upload/download hoặc xử lý byte tùy chỉnh |
| `FilePart` | Đại diện cho file multipart | Upload file qua multipart với API mức cao |
| `Flux<PartEvent>` | Nhận từng event/part trong multipart | Multipart lớn cần xử lý theo luồng |

Không chọn `Flux` chỉ vì muốn mọi thứ đều reactive. Nếu request chỉ chứa một object nhỏ, `Mono<Dto>` thường dễ hiểu và đủ tốt. Nếu body có thể rất lớn hoặc không biết trước số phần tử, hãy tránh biến nó thành `byte[]`, `String` hay `List` toàn bộ.

## 5. Vì sao NDJSON hữu ích cho luồng bản ghi?

Một JSON document thông thường có thể chứa một mảng:

```json
[
  {"id": 1, "value": "alpha"},
  {"id": 2, "value": "beta"},
  {"id": 3, "value": "gamma"}
]
```

NDJSON (Newline Delimited JSON) biểu diễn mỗi object trên một dòng:

```text
{"id":1,"value":"alpha"}
{"id":2,"value":"beta"}
{"id":3,"value":"gamma"}
```

Mỗi dòng là một JSON object độc lập. Server có thể decode từng object và xử lý khi dữ liệu đến mà không cần đợi toàn bộ tài liệu kết thúc.

Request:

```http
Content-Type: application/x-ndjson
```

Response streaming có thể dùng cùng media type. Với Server-Sent Events, dùng `text/event-stream`.

Không tự tách từng `DataBuffer` theo newline bằng `new String(bufferBytes)`: một dòng có thể bị chia giữa hai buffer, hoặc một buffer có nhiều dòng. Codec và decoder chuyên dụng chịu trách nhiệm xử lý framing và ký tự đa byte đúng cách.

## 6. `maxInMemorySize` là giới hạn buffer, không phải giới hạn toàn body

Các decoder và `HttpMessageReader` có thể cần buffer một phần hoặc toàn bộ dữ liệu để tạo object. Spring cho phép giới hạn số byte được buffer qua `maxInMemorySize`.

Với các codec mặc định của WebFlux, giá trị mặc định phổ biến là **256 KiB**. Nếu codec phải buffer vượt giới hạn, request có thể phát `DataBufferLimitException`.

Điểm quan trọng: giới hạn này không có nghĩa toàn bộ HTTP request chỉ được phép có 256 KiB.

- Khi một request được gom thành một `byte[]`, `String` hoặc object đơn, giới hạn áp dụng cho phần dữ liệu cần aggregate.
- Khi decoder stream nhiều object, giới hạn áp dụng cho số byte cần buffer để tách/giải mã **một object** trong stream.
- Với multipart, giới hạn có ý nghĩa riêng cho form field và file part; file có thể được ghi ra disk theo ngưỡng cấu hình.
- Giới hạn codec không thay thế giới hạn tổng request body ở reverse proxy, gateway hoặc server connector.

Nếu một NDJSON request chứa 10 triệu dòng, mỗi dòng nhỏ, tổng request có thể lớn hơn nhiều so với `maxInMemorySize` mà vẫn được xử lý theo luồng. Một dòng đơn lẻ quá lớn vẫn có thể vượt giới hạn.

### 6.1. Cấu hình codec ở phía server

Có thể tùy chỉnh codec mặc định bằng `WebFluxConfigurer`:

```java
@Configuration
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(512 * 1024);
    }
}
```

Đoạn này nâng ngưỡng buffer của default codecs lên 512 KiB. Chỉ tăng khi có lý do rõ ràng, chẳng hạn một object đơn hợp lệ lớn hơn mức mặc định.

Trong Spring Boot, dùng `WebFluxConfigurer` mà không thêm `@EnableWebFlux` nếu muốn giữ auto-configuration WebFlux của Boot. Nếu tự thay thế codec, kiểm tra các codec khác và cấu hình giới hạn tương ứng; custom decoder có thể cần tự quản lý giới hạn riêng.

### 6.2. Cấu hình codec ở phía WebClient

Client cũng có giới hạn buffer khi encode/decode:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(512 * 1024)
        )
        .build();
```

Cấu hình client và server là hai nơi độc lập. Tăng giới hạn ở WebClient không tự thay đổi giới hạn của server nhận request.

### 6.3. Không dùng tăng giới hạn để che lỗi thiết kế

Nếu endpoint đang gọi:

```java
Mono<byte[]> body = request.bodyToMono(byte[].class);
```

tăng `maxInMemorySize` lên vài trăm MB chỉ khiến ứng dụng có thể gom payload lớn hơn. Nó không biến code thành streaming và cũng không bảo vệ ứng dụng trước nhiều request đồng thời.

Hãy đổi thiết kế sang `Flux<T>`, `Flux<DataBuffer>`, `FilePart` hoặc `PartEvent` khi nghiệp vụ cho phép xử lý từng phần.

## 7. Xử lý `Flux<T>` theo từng phần tử

### 7.1. `concatMap`: tuần tự và giữ thứ tự

```java
return request.bodyToFlux(Event.class)
        .concatMap(event -> eventService.save(event))
        .then(ServerResponse.accepted().build());
```

`concatMap` chỉ xử lý Publisher con theo thứ tự. Phù hợp khi:

- Thứ tự bản ghi quan trọng.
- Service ghi dữ liệu tuần tự.
- Muốn giới hạn số thao tác đang chạy.
- Cần đơn giản hóa việc quản lý tài nguyên theo từng phần tử.

Nếu một event mất nhiều thời gian, event sau phải chờ. Đây là trade-off có chủ đích để kiểm soát concurrency.

### 7.2. `flatMap` với concurrency giới hạn

```java
return request.bodyToFlux(Event.class)
        .flatMap(event -> eventService.save(event), 8)
        .then();
```

Đoạn này cho phép tối đa 8 Publisher con hoạt động đồng thời. Nó có thể tăng throughput khi các thao tác độc lập, nhưng thứ tự hoàn thành có thể khác thứ tự đầu vào.

Không dùng `flatMap` không giới hạn cho hàng triệu phần tử nếu service downstream không chịu được tải. Chọn concurrency theo giới hạn database pool, dịch vụ ngoài và năng lực xử lý.

### 7.3. `limitRate` và prefetch

```java
Flux<Event> controlled = events.limitRate(64);
```

`limitRate` điều chỉnh cách Reactor yêu cầu dữ liệu từ upstream theo các nhóm demand. Nó hữu ích để tránh yêu cầu một lượng quá lớn cùng lúc, nhưng không phải giới hạn tổng số phần tử hoặc tổng dung lượng body.

Một operator có prefetch lớn, `flatMap` concurrency cao hoặc queue lớn vẫn có thể giữ nhiều phần tử cùng lúc. Cần xem toàn bộ pipeline chứ không chỉ một operator.

### 7.4. `onBackpressureBuffer` cần có giới hạn

```java
events.onBackpressureBuffer(
        256,
        dropped -> log.warn("Dropped event: {}", dropped)
);
```

Đây là buffer có giới hạn 256 phần tử và callback khi overflow theo overload được dùng. Buffer không tự giải quyết tải; nó đổi áp lực upstream thành việc giữ dữ liệu trong RAM. Chọn chính sách overflow có chủ đích: lỗi, drop hoặc lưu bền vững. Tránh queue không giới hạn cho body lớn.

## 8. Giữ accumulator nhỏ, tránh `collectList()`

Hai cách sau có chi phí bộ nhớ rất khác nhau.

Gom tất cả phần tử:

```java
Mono<List<Event>> allEvents =
        request.bodyToFlux(Event.class).collectList();
```

Chỉ đếm phần tử:

```java
Mono<Long> count =
        request.bodyToFlux(Event.class)
                .count();
```

Hoặc vừa xử lý vừa đếm:

```java
Mono<Long> count = request.bodyToFlux(Event.class)
        .concatMap(event ->
                eventService.save(event).thenReturn(1L)
        )
        .reduce(0L, Long::sum);
```

`collectList()` cần giữ toàn bộ object cho đến khi stream hoàn tất. `count()` và `reduce` với accumulator nhỏ chỉ cần giữ trạng thái tổng hợp. Nhưng `reduce` cũng có thể gây vấn đề nếu accumulator là một `List`, `Map` hoặc `StringBuilder` liên tục lớn lên.

Hãy hỏi: accumulator có tăng theo tổng số bản ghi không? Nếu có, đó vẫn là một dạng gom dữ liệu.

## 9. Đọc và ghi byte bằng `DataBuffer`

`DataBuffer` là abstraction byte buffer của Spring. Khi làm việc trực tiếp với request/response bytes, API thường trả `Flux<DataBuffer>`.

Một số server như Reactor Netty sử dụng pooled, reference-counted buffers. Khi ứng dụng tự tiêu thụ `DataBuffer`, phải bảo đảm buffer được release đúng lúc. Nếu giữ buffer quá lâu hoặc quên release, native memory có thể tăng dù heap của JVM không tăng tương ứng.

### 9.1. Đọc một buffer rồi release

Ví dụ chuyển từng buffer thành mảng byte nhỏ để xử lý:

```java
Flux<byte[]> chunks = request.bodyToFlux(DataBuffer.class)
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return bytes;
            } finally {
                DataBufferUtils.release(buffer);
            }
        });
```

Đoạn trên chỉ tạo một mảng cho mỗi chunk. Consumer tiếp theo vẫn phải xử lý và bỏ chunk sau khi hoàn tất; nếu gom tất cả mảng vào một list thì lại quay về vấn đề ban đầu.

Không release buffer trước khi thành phần downstream đã đọc xong. Khi chuyển buffer cho response writer hoặc một API khác sở hữu nó, hãy tuân thủ hợp đồng ownership của API đó.

### 9.2. Khi nào cần `retain`?

`DataBufferUtils.retain(buffer)` tăng reference count nếu buffer là pooled. Chỉ retain khi cần giữ buffer sau ranh giới mà bên sở hữu hiện tại có thể release, ví dụ chuyển quyền sở hữu sang một tác vụ bất đồng bộ khác. Sau khi sử dụng xong, phải release đúng số lần.

Không gọi `retain` như một cách chữa memory leak. Retain mà không release sẽ làm buffer tồn tại lâu hơn.

### 9.3. `doOnDiscard` cho buffer bị loại bỏ

Một số operator có thể discard phần tử khi cancel, filter hoặc kết thúc sớm. Với pipeline trực tiếp quản lý `DataBuffer`, có thể cần cleanup cho phần tử bị discard:

```java
Flux<DataBuffer> safe = source
        .filter(this::shouldKeep)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

Đây là ví dụ minh họa. `doOnDiscard` chỉ xử lý các phần tử mà operator hỗ trợ discard hook; nó không thay thế việc release buffer đã được consumer lấy ra và sử dụng trực tiếp.

### 9.4. Không tự giải mã từng buffer như một chuỗi độc lập

Một ký tự UTF-8 có thể trải qua ranh giới hai buffer. Một dòng JSON có thể bị chia thành nhiều chunk. Vì vậy:

```java
new String(bytes, StandardCharsets.UTF_8)
```

trên từng buffer riêng lẻ không phải cách parser an toàn cho stream text tùy ý.

Dùng `Decoder`/`HttpMessageReader` và `bodyToFlux(Dto.class)` khi có thể. Nếu định nghĩa protocol byte riêng, dùng parser có state để giữ phần dữ liệu dở dang giữa các chunk.

## 10. `DataBufferUtils.join`: chỉ aggregate khi có giới hạn

`DataBufferUtils.join(...)` ghép một stream buffer thành một `DataBuffer`. Đây là cách hữu ích cho payload nhỏ cần xử lý như một khối, nhưng không phù hợp với body lớn không có giới hạn.

Dùng overload có giới hạn:

```java
Mono<String> smallText = DataBufferUtils.join(body, 64 * 1024)
        .map(joined -> {
            try {
                byte[] bytes = new byte[joined.readableByteCount()];
                joined.read(bytes);
                return new String(bytes, StandardCharsets.UTF_8);
            } finally {
                DataBufferUtils.release(joined);
            }
        });
```

Ví dụ này chỉ chấp nhận tối đa 64 KiB để aggregate. Khi vượt giới hạn, pipeline phát `DataBufferLimitException`. `join` quản lý các buffer đầu vào đã tích lũy; buffer ghép trả về cần được release sau khi ứng dụng đọc xong.

Không dùng `join` không giới hạn cho upload hoặc download lớn. Nếu chỉ cần chuyển dữ liệu sang file, hãy stream buffer vào file thay vì nối tất cả thành một buffer lớn.

## 11. Stream file upload và download

### 11.1. Download file theo chunk

`DataBufferUtils.read(Path, DataBufferFactory, bufferSize, ...)` đọc file thành `Flux<DataBuffer>` với kích thước buffer do ứng dụng chọn:

```java
Path file = Path.of("exports", "large-report.bin");

Flux<DataBuffer> body = DataBufferUtils.read(
        file,
        new DefaultDataBufferFactory(),
        64 * 1024
);

return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(body);
```

Mỗi buffer tối đa khoảng 64 KiB theo cấu hình đọc. `DataBufferUtils.read` đóng channel khi Flux kết thúc hoặc bị cancel. Response writer tiêu thụ các buffer để gửi về client; không release buffer trước khi writer đọc xong.

Đây là mã minh họa trong một controller method trả `ResponseEntity<Flux<DataBuffer>>`. Đường dẫn file phải được server kiểm soát, không lấy nguyên đường dẫn do client gửi.

### 11.2. Ghi luồng buffer xuống file

`DataBufferUtils.write(Publisher<DataBuffer>, Path, OpenOption...)` nhận stream buffer và trả `Mono<Void>` báo hoàn tất hoặc lỗi:

```java
Mono<Void> saveUpload(Flux<DataBuffer> body, Path destination) {
    return DataBufferUtils.write(body, destination);
}
```

Việc ghi chỉ bắt đầu khi Publisher được subscribe. Ghép Mono này vào handler/controller và để WebFlux điều phối subscription. Không gọi `.subscribe()` riêng trong service.

Chọn thư mục đích do server quản lý, tạo tên file an toàn, đặt quota và xử lý cleanup khi request bị hủy. Kiểm tra Javadoc đúng phiên bản Spring khi tự kết hợp các API buffer cấp thấp; không release hoặc retain buffer theo phỏng đoán.

### 11.3. Dùng `FilePart` cho multipart upload mức cao

Nếu không cần điều khiển từng chunk, `FilePart` là abstraction tiện dụng:

```java
@PostMapping(
        path = "/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
Mono<ResponseEntity<String>> upload(@RequestPart("file") FilePart file) {
    Path destination = uploadDirectory.resolve(
            UUID.randomUUID().toString() + ".bin"
    );

    return file.transferTo(destination)
            .thenReturn(ResponseEntity.accepted().body("stored"));
}
```

Tạo thư mục `uploadDirectory` trước khi chạy. Tên file đích được server tạo bằng UUID, không dùng trực tiếp tên file client làm đường dẫn. `transferTo` trả Publisher để quá trình ghi được ghép vào request lifecycle.

Trong multipart reader mặc định, file part lớn hơn ngưỡng bộ nhớ có thể được ghi vào file tạm. Cần cấu hình giới hạn bộ nhớ, dung lượng disk, số part và chính sách dọn file tạm phù hợp.

## 12. Multipart lớn: `multipartData()` và `PartEvent`

`ServerRequest.multipartData()` hoặc API tương đương có thể trả `MultiValueMap<String, Part>`. Cách này tiện khi cần truy cập nhiều part theo tên, nhưng reader tổng hợp các part vào map. Với request có nhiều part hoặc cần xử lý file ngay khi đến, dùng `PartEvent` để stream từng phần.

Spring WebFlux hỗ trợ:

```java
Flux<PartEvent> events = request.bodyToFlux(PartEvent.class);
```

Một part có thể tạo nhiều `PartEvent`. `isLast()` đánh dấu event cuối của part hiện tại. Ví dụ pattern xử lý theo từng part:

```java
return request.bodyToFlux(PartEvent.class)
        .windowUntil(PartEvent::isLast)
        .concatMap(partEvents ->
                partEvents.switchOnFirst((signal, samePart) -> {
                    if (!signal.hasValue()) {
                        return samePart.then();
                    }

                    PartEvent first = signal.get();

                    if (first instanceof FormPartEvent form) {
                        return handleFormField(form.value());
                    }

                    if (first instanceof FilePartEvent file) {
                        Path destination = uploadDirectory.resolve(
                                UUID.randomUUID().toString()
                        );

                        Flux<DataBuffer> content =
                                samePart.map(PartEvent::content);

                        return DataBufferUtils.write(
                                content, destination
                        );
                    }

                    return Mono.error(
                            new IllegalStateException("Unsupported part")
                    );
                })
        )
        .then();
```

Đây là mẫu functional handler cần `ServerRequest`, `PartEvent`, `FormPartEvent`, `FilePartEvent`, `DataBuffer`, `DataBufferUtils` và các hàm `handleFormField`/`uploadDirectory` của ứng dụng. `concatMap` giữ thứ tự các part; nội dung file được chuyển thẳng thành stream buffer để ghi.

**Mọi nội dung `PartEvent` phải được tiêu thụ, chuyển tiếp hoặc release.** Không bỏ qua file part rồi tiếp tục sang part kế tiếp khi nội dung trước vẫn chưa được xử lý xong. Nếu client cancel hoặc xử lý lỗi, cần cleanup file tạm và resource đã tạo.

## 13. Multipart limits và disk usage

Multipart có nhiều loại giới hạn khác nhau:

- `maxInMemorySize`: giới hạn bộ nhớ cho form field hoặc ngưỡng giữ file part trong RAM.
- `maxDiskUsagePerPart`: giới hạn dung lượng file part được ghi ra disk trong reader hỗ trợ thuộc tính này.
- `maxParts`: giới hạn số lượng part trong một request.
- `maxHeadersSize`: giới hạn bộ nhớ dành cho header của mỗi part.
- Giới hạn tổng request body: cần phối hợp ở server connector, gateway hoặc reverse proxy.

`DefaultPartHttpMessageReader` và `PartEventHttpMessageReader` có cấu hình khác nhau theo phiên bản Spring. Với `PartEventHttpMessageReader`, các phiên bản Spring 6.1 hỗ trợ giới hạn bộ nhớ form field, kích thước part, số part và header. Kiểm tra Javadoc đúng phiên bản đang chạy trước khi cấu hình.

Không đặt giới hạn disk vô hạn ở môi trường có thể nhận upload lớn từ người dùng không tin cậy. Cần quota tổng thư mục, cleanup file tạm, timeout và giới hạn request đồng thời.

## 14. Stream response cũng cần tránh aggregate

Tránh tạo danh sách lớn rồi trả về:

```java
Mono<List<Order>> allOrders = orderRepository.findAll()
        .collectList();
```

Nếu client có thể nhận dữ liệu từng phần tử:

```java
@GetMapping(
        value = "/orders/export",
        produces = "application/x-ndjson"
)
Flux<OrderExportRow> export() {
    return orderRepository.findAll()
            .map(OrderExportRow::from);
}
```

Với SSE:

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<ServerSentEvent<EventMessage>> stream() {
    return eventPublisher.map(event ->
            ServerSentEvent.builder(event).build()
    );
}
```

Khi streaming response kéo dài, hãy gửi dữ liệu định kỳ hoặc heartbeat phù hợp để phát hiện client disconnect sớm hơn. Nếu client ngắt kết nối, cancellation cần được truyền tới nguồn và tác vụ phía sau.

Không phải mọi client đều tiêu thụ stream như nhau. Một client có thể vẫn buffer toàn bộ body trước khi hiển thị. Chọn media type và client API cùng nhau; `application/x-ndjson` hoặc SSE thường phù hợp hơn cho incremental consumption.

## 15. WebClient: không buffer response lớn ở phía client

Tránh:

```java
Mono<byte[]> file = webClient.get()
        .uri("/large-file")
        .retrieve()
        .bodyToMono(byte[].class);
```

Dùng stream object:

```java
Flux<Event> events = webClient.get()
        .uri("/events")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .bodyToFlux(Event.class);
```

Hoặc stream raw byte buffer khi cần chuyển file:

```java
Mono<Void> download = webClient.get()
        .uri("/large-file")
        .retrieve()
        .bodyToFlux(DataBuffer.class)
        .as(buffers -> DataBufferUtils.write(
                buffers,
                Path.of("downloads", "large-file.bin")
        ));
```

Để gửi một stream object:

```java
Mono<Void> upload = webClient.post()
        .uri("/events")
        .contentType(MediaType.parseMediaType("application/x-ndjson"))
        .body(eventFlux, Event.class)
        .retrieve()
        .bodyToMono(Void.class);
```

`eventFlux` nên là nguồn reactive thực sự, chẳng hạn database stream hoặc file parser; không tạo sẵn một `List` khổng lồ rồi mới `Flux.fromIterable(list)`.

## 16. Blocking I/O và các thao tác CPU nặng

Streaming không tự làm một thao tác blocking trở thành non-blocking. Nếu xử lý mỗi chunk bằng một API file/database blocking trên event-loop thread, các request khác có thể bị chậm.

Ưu tiên:

- Reactive driver và API I/O non-blocking.
- `DataBufferUtils.read` hoặc `write` cho các trường hợp phù hợp.
- Giải mã bằng codec sẵn có.
- Xử lý từng record với concurrency có giới hạn.

Nếu bắt buộc gọi thư viện blocking, cô lập đúng lời gọi:

```java
Mono<Result> result = Mono.fromCallable(
        () -> legacyBlockingService.process(event)
).subscribeOn(Schedulers.boundedElastic());
```

Không đưa toàn bộ pipeline sang `boundedElastic` theo thói quen. Chỉ cô lập phần blocking; vẫn giữ số tác vụ đồng thời ở mức có thể kiểm soát.

Với CPU-intensive work, đo tải và chọn scheduler phù hợp. Tăng concurrency không luôn làm throughput tăng; nó có thể khiến CPU, heap, queue và downstream quá tải.

## 17. Hủy request, lỗi giữa stream và cleanup

Body stream có thể kết thúc theo ba cách: complete, error hoặc cancel. Cancel xảy ra khi client đóng kết nối, timeout, server dừng hoặc subscriber không còn cần dữ liệu.

Khi cancel:

- Ngừng đọc dữ liệu mới nếu upstream hỗ trợ cancellation.
- Đóng file/channel và giải phóng buffer còn sở hữu.
- Xóa file tạm chưa hoàn tất theo chính sách.
- Hủy tác vụ downstream không còn cần thiết.
- Không để `subscribe()` lồng tạo pipeline sống độc lập với request.

Khi lỗi giữa stream, response có thể đã gửi một phần body. Server không thể thu hồi các byte đã gửi. Với export/download, client cần nhận biết stream bị gián đoạn và có thể retry theo cơ chế idempotent hoặc cursor.

Với upload có side effect, hãy xác định điểm commit nghiệp vụ. Nếu chỉ ghi một phần file rồi lỗi, xóa file chưa hoàn tất hoặc ghi vào staging path trước khi đổi tên thành file chính thức. Không công bố file cho hệ thống khác trước khi quá trình upload hoàn tất.

## 18. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ có hai endpoint:

- `POST /stream/events`: nhận NDJSON, validate và xử lý từng record tuần tự, chỉ giữ bộ đếm.
- `GET /stream/demo`: phát 5 record NDJSON để client đọc từng dòng.

### Cấu trúc thư mục

```text
webflux-streaming-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

### File `pom.xml`

```xml
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

    <groupId>demo</groupId>
    <artifactId>webflux-streaming-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
```

### File `src/main/java/demo/Main.java`

```java
package demo;

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
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }
}

@RestController
@RequestMapping("/stream")
class StreamController {

    @PostMapping(
            path = "/events",
            consumes = "application/x-ndjson",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<IngestSummary> ingest(@RequestBody Flux<EventRecord> events) {
        return events
                .concatMap(this::accept, 1)
                .reduce(0L, Long::sum)
                .map(IngestSummary::new);
    }

    private Mono<Long> accept(EventRecord event) {
        if (event.id() <= 0
                || event.value() == null
                || event.value().isBlank()) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Each event needs a positive id and a non-empty value"
            ));
        }

        // Thay bằng repository.save(event) nếu dùng reactive database.
        return Mono.just(1L);
    }

    @GetMapping(
            path = "/demo",
            produces = "application/x-ndjson"
    )
    Flux<EventRecord> demo() {
        return Flux.range(1, 5)
                .map(id -> new EventRecord(id, "event-" + id));
    }

    record EventRecord(long id, String value) {}

    record IngestSummary(long accepted) {}
}
```

Chạy từ thư mục dự án bằng JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

### Thử response streaming

```bash
curl -N http://localhost:8080/stream/demo
```

Body được phát thành từng dòng NDJSON:

```text
{"id":1,"value":"event-1"}
{"id":2,"value":"event-2"}
{"id":3,"value":"event-3"}
{"id":4,"value":"event-4"}
{"id":5,"value":"event-5"}
```

### Gửi một stream NDJSON

Tạo file `events.ndjson`:

```text
{"id":1,"value":"alpha"}
{"id":2,"value":"beta"}
{"id":3,"value":"gamma"}
```

Gửi request:

```bash
curl -i -X POST http://localhost:8080/stream/events \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @events.ndjson
```

Body response:

```json
{"accepted":3}
```

**Giải thích:**

1. `@RequestBody Flux<EventRecord>` cho phép decoder phát từng record.
2. `concatMap(..., 1)` xử lý tuần tự và giữ prefetch nhỏ.
3. `accept` chỉ trả một giá trị `Long` sau khi kiểm tra record; ứng dụng thực tế có thể thay bằng `repository.save(event)`.
4. `reduce(0L, Long::sum)` giữ một bộ đếm, không giữ danh sách event.
5. Endpoint demo trả `Flux<EventRecord>` với media type NDJSON để client đọc từng dòng.
6. Không có `.collectList()`, `byte[]` hoặc `.block()` trong request pipeline.

Đây là chương trình demo có xử lý record trong bộ nhớ để minh họa streaming. Khi dùng thật, thay phần `Mono.just(1L)` bằng reactive persistence hoặc một tác vụ có giới hạn concurrency. Ví dụ không mô phỏng lưu trữ bền vững.

## 19. Kiểm thử bằng `WebTestClient`

Có thể kiểm thử endpoint mà không mở cổng TCP:

```java
WebTestClient client = WebTestClient
        .bindToController(new StreamController())
        .build();

client.post()
        .uri("/stream/events")
        .contentType(MediaType.parseMediaType("application/x-ndjson"))
        .body(
                Flux.just(
                        new StreamController.EventRecord(1, "alpha"),
                        new StreamController.EventRecord(2, "beta")
                ),
                StreamController.EventRecord.class
        )
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.accepted").isEqualTo(2);
```

Đây là đoạn test minh họa, cần `spring-test` (thường được đưa vào qua `spring-boot-starter-test`) và import `WebTestClient`. Nếu record lồng trong controller không được truy cập từ test package, hãy đổi visibility phù hợp hoặc đặt DTO ở file riêng.

Test nên bổ sung:

- Nhiều record và record rỗng.
- Một record không hợp lệ giữa stream.
- Payload có một record vượt `maxInMemorySize`.
- Client cancel khi server đang phát dữ liệu.
- Đo bộ nhớ với số record tăng nhưng kích thước từng record ổn định.
- Multipart file lớn, giới hạn disk và cleanup khi cancel.
- Kiểm tra thứ tự với `concatMap` và concurrency với `flatMap`.

## 20. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `bodyToMono(byte[].class)` cho file lớn | Toàn bộ body có thể được giữ trong RAM | Stream `Flux<DataBuffer>` hoặc dùng `FilePart` |
| Dùng `collectList()` cho hàng triệu record | Heap tăng theo số phần tử | Xử lý từng record và giữ accumulator nhỏ |
| Tăng `maxInMemorySize` lên hàng trăm MB để tránh lỗi | Một request có thể chiếm lượng RAM rất lớn | Chuyển sang streaming; chỉ tăng giới hạn cho object đơn thực sự cần |
| Nhầm `maxInMemorySize` là giới hạn tổng request | Bỏ sót giới hạn upload và request body | Cấu hình thêm limit ở server, gateway và proxy |
| Dùng `multipartData()` cho upload cực lớn mà không xét aggregation | Tạo map chứa toàn bộ part metadata/content abstraction | Dùng `PartEvent` khi cần streaming từng part |
| Dùng `flatMap` không giới hạn | Tăng concurrency và queue ngoài khả năng downstream | Dùng `concatMap` hoặc `flatMap` có concurrency |
| Dùng `onBackpressureBuffer()` không giới hạn | Buffer tăng theo tốc độ producer | Dùng buffer bounded và overflow policy |
| Tự `subscribe()` trong controller/service | Pipeline tách khỏi request lifecycle | Trả Publisher để WebFlux điều phối |
| Quên release `DataBuffer` tự tiêu thụ | Pooled native memory có thể bị leak | Release sau khi đọc xong, xử lý retain/discard đúng ownership |
| Release buffer trước khi writer dùng | Response lỗi hoặc dữ liệu bị hỏng | Chỉ release sau khi consumer sở hữu đã hoàn tất |
| Tự chuyển từng buffer thành String | Có thể cắt giữa UTF-8 character hoặc record | Dùng codec/framing parser có state |
| Đọc body hai lần | Body thường không replay tự động | Decode một lần rồi truyền object trong pipeline |
| Dùng blocking file/database trên event loop | Chặn nhiều request cùng lúc | Dùng reactive I/O hoặc cô lập blocking call |
| Không xử lý cancellation | File tạm, channel hoặc tác vụ còn chạy | Gắn cleanup vào lifecycle/cancel |
| Dùng tên file client làm path | Nguy cơ path traversal hoặc ghi đè file | Tạo tên file server-side và giới hạn thư mục |
| Không giới hạn multipart disk usage/parts | Có thể cạn dung lượng disk hoặc tạo quá nhiều part | Đặt quota, max part size, maxParts và cleanup |
| Nghĩ NDJSON tự động giới hạn kích thước từng dòng | Một dòng rất lớn vẫn cần buffer để decode | Đặt giới hạn object và validate record size |
| Trả stream nhưng client luôn gom toàn bộ | Client vẫn có thể tốn RAM | Chọn client API và media type hỗ trợ incremental read |

## 21. Checklist thiết kế endpoint body lớn

1. Xác định request là một object nhỏ, danh sách hữu hạn hay stream không biết trước kích thước.
2. Chọn `Mono<T>`, `Flux<T>`, `Flux<DataBuffer>`, `FilePart` hoặc `PartEvent` phù hợp.
3. Dùng NDJSON/SSE hoặc framing rõ ràng khi client cần nhận dữ liệu từng phần.
4. Tránh `byte[]`, `String`, `collectList()` và `DataBufferUtils.join()` không giới hạn.
5. Đặt `maxInMemorySize` theo kích thước object hợp lệ, không theo tổng kích thước file.
6. Đặt giới hạn tổng request, multipart size, disk usage, số part và thời gian xử lý.
7. Chọn `concatMap` hoặc concurrency có giới hạn theo năng lực downstream.
8. Giữ accumulator nhỏ; tránh queue không giới hạn.
9. Với `DataBuffer` trực tiếp, xác định rõ owner, retain/release và discard cleanup.
10. Không gọi blocking I/O trên event-loop.
11. Xử lý cancellation, lỗi giữa stream và file tạm.
12. Kiểm thử với payload lớn hơn dữ liệu thông thường và theo dõi heap lẫn direct/native memory.
13. Kiểm tra cả client: client cũng phải stream thay vì gom response vào RAM.
14. Không log toàn bộ body lớn hoặc dữ liệu nhạy cảm.

## 22. Bài tập tự kiểm tra

**Câu 1.** Vì sao `bodyToMono(byte[].class)` không phù hợp cho upload nhiều GB?

**Đáp án:** Vì ứng dụng cần tạo một mảng byte chứa toàn bộ body; bộ nhớ tăng theo kích thước file và số request đồng thời.

**Câu 2.** `bodyToFlux(Event.class)` có lợi ích gì?

**Đáp án:** Decoder có thể phát các event theo luồng để pipeline xử lý từng phần tử thay vì tạo một List chứa toàn bộ dữ liệu.

**Câu 3.** `maxInMemorySize` có phải giới hạn tổng request body không?

**Đáp án:** Không. Nó giới hạn dữ liệu codec cần buffer; với stream, giới hạn có thể áp dụng theo từng object. Tổng body cần limit riêng ở server/gateway.

**Câu 4.** Vì sao NDJSON phù hợp với dữ liệu bản ghi lớn?

**Đáp án:** Mỗi dòng là một JSON object độc lập, giúp decoder tách và phát record khi dữ liệu đến.

**Câu 5.** `concatMap` và `flatMap` khác nhau thế nào khi xử lý stream?

**Đáp án:** `concatMap` xử lý tuần tự và giữ thứ tự; `flatMap` cho phép xử lý đồng thời, cần giới hạn concurrency và không đảm bảo thứ tự hoàn thành.

**Câu 6.** `reduce(0L, Long::sum)` có phải gom toàn bộ stream không?

**Đáp án:** Không. Nó chỉ giữ một bộ đếm `long`; nhưng nếu accumulator là List/Map/String tăng không giới hạn thì vẫn là aggregation.

**Câu 7.** Khi nào cần gọi `DataBufferUtils.release`?

**Đáp án:** Khi ứng dụng trực tiếp tiêu thụ và sở hữu một pooled `DataBuffer`; release sau khi sử dụng xong, không release trước khi downstream consumer hoàn tất.

**Câu 8.** `DataBufferUtils.join` có phù hợp với file 10 GB không?

**Đáp án:** Không. `join` aggregate buffers thành một buffer; chỉ dùng khi có giới hạn nhỏ và rõ ràng.

**Câu 9.** Vì sao `multipartData()` có thể không phù hợp với multipart rất lớn?

**Đáp án:** API này tạo `MultiValueMap` chứa các part. Nếu cần xử lý từng part theo luồng, dùng `PartEvent`.

**Câu 10.** `PartEvent` content có thể bỏ qua sau khi đọc filename không?

**Đáp án:** Không. Nội dung buffer của mỗi part phải được tiêu thụ, chuyển tiếp hoặc release để tránh rò bộ nhớ.

**Câu 11.** Vì sao `onBackpressureBuffer()` không giới hạn có thể nguy hiểm?

**Đáp án:** Khi producer nhanh hơn consumer, queue tiếp tục tăng và giữ dữ liệu trong RAM.

**Câu 12.** Client hủy download giữa chừng thì server nên làm gì?

**Đáp án:** Propagate cancellation, đóng channel/file và cleanup resource không còn cần thiết.

## 23. Quy tắc áp dụng

- Dùng `Mono<T>` cho object nhỏ và `Flux<T>` cho stream nhiều phần tử.
- Chọn NDJSON/SSE khi cần incremental transfer; không gom thành JSON array khổng lồ nếu không cần.
- Xem `maxInMemorySize` là giới hạn buffer của codec, không phải giới hạn tổng request.
- Dùng `concatMap` hoặc `flatMap` có concurrency giới hạn; giữ accumulator nhỏ.
- Với file, ưu tiên stream `DataBuffer`, `FilePart` hoặc `PartEvent` thay vì `byte[]`.
- Chỉ dùng `DataBufferUtils.join` khi payload nhỏ và có giới hạn.
- Khi tự xử lý `DataBuffer`, tuân thủ ownership và release đúng lúc.
- Thiết kế cleanup cho error/cancel và giới hạn memory, disk, request size.
- Kiểm thử cả server lẫn client với payload lớn và tốc độ producer/consumer khác nhau.

**Ghi nhớ:** WebFlux có thể xử lý body lớn theo từng phần nhờ `Flux`, codec và backpressure. Đừng gom toàn bộ body vào `byte[]`, `String` hoặc `List` nếu có thể xử lý từng record hoặc buffer. Giới hạn codec, concurrency, disk usage và lifecycle của `DataBuffer` phải được thiết kế cùng nhau.

## 24. Tài liệu tham khảo chính thức

- [Spring Framework — Functional Endpoints: request body và PartEvent streaming](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — Reactive Core: codec limits, multipart và DataBuffer](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework — WebFlux Config: HTTP message codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework 6.1.11 — DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework 6.1.11 — PartEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/codec/multipart/PartEvent.html)
- [Spring Framework 6.1.11 — DefaultPartHttpMessageReader Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html)
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — WebClient request body streaming](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html)
