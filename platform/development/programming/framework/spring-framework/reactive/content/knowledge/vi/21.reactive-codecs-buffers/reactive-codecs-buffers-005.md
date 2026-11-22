# `maxInMemorySize` và `DataBufferLimitException` trong Spring WebFlux

## 1. Vấn đề: codec không thể giữ dữ liệu trong bộ nhớ vô hạn

Spring WebFlux nhận và gửi HTTP body dưới dạng luồng `DataBuffer`. Các codec và `HttpMessageReader` chuyển luồng byte này thành kiểu Java như `String`, `byte[]`, DTO JSON, form data hoặc multipart. Để tạo một object hoàn chỉnh, một số reader phải gom (aggregate) nhiều buffer lại trong bộ nhớ. Nếu không có giới hạn, một request lớn hoặc nhiều request đồng thời có thể làm heap tăng nhanh.

Hai khái niệm cần nắm:

- **`maxInMemorySize`** là giới hạn số byte mà codec/reader được phép giữ khi cần gom dữ liệu trong bộ nhớ.
- **`DataBufferLimitException`** là exception báo rằng số byte tích lũy trong một thao tác buffer/aggregate đã vượt giới hạn được cấu hình.

Đây là cơ chế bảo vệ bộ nhớ của codec. Nó không phải giới hạn tổng dung lượng upload của toàn bộ HTTP request và cũng không phải một HTTP status. Status cuối cùng phụ thuộc nơi exception phát sinh và cách ứng dụng ánh xạ lỗi.

Trong Spring Framework 6.2, phần lớn codec mặc định có giới hạn 256 KB. Giới hạn có thể được thay đổi ở phía server qua `ServerCodecConfigurer`, phía client qua `WebClient.Builder`, hoặc bằng cấu hình Spring Boot. Với streaming, giới hạn thường áp dụng cho **từng phần tử/đơn vị được gom**, không phải tổng dung lượng của cả stream. Với multipart, cùng thuộc tính có ý nghĩa riêng cho từng part: giới hạn phần không phải file và ngưỡng để file part được ghi ra đĩa.

## 2. `DataBuffer`, codec và quá trình aggregate

### 2.1. `DataBuffer` là gì?

`DataBuffer` là abstraction của Spring cho vùng byte. Nó che giấu khác biệt giữa các implementation bên dưới, chẳng hạn:

- Netty `ByteBuf`.
- Java NIO `ByteBuffer`.
- Buffer do server connector hoặc thư viện I/O khác cung cấp.

HTTP body thường đến theo nhiều chunk. Một JSON document 1 MB có thể được transport thành hàng chục hoặc hàng trăm `DataBuffer` nhỏ; ranh giới buffer không nhất thiết trùng với ranh giới JSON object, dòng NDJSON hoặc SSE event.

Codec đọc các buffer và chuyển chúng thành dữ liệu cấp cao:

```text
Network / HTTP body
        |
        v
Flux<DataBuffer>
        |
        v
Decoder / HttpMessageReader
        |
        +---- parse / aggregate / split
        |
        v
Mono<DTO> hoặc Flux<DTO>
        |
        v
Controller / WebClient caller
```

`Encoder` thực hiện chiều ngược lại: nhận object và tạo ra các `DataBuffer` để ghi vào response/request body.

### 2.2. Khi nào phải gom dữ liệu?

Một số kiểu đích đòi hỏi reader phải có đủ dữ liệu trước khi phát kết quả:

| Cách đọc body | Hành vi thường gặp |
|---|---|
| `@RequestBody byte[]` | Gom body thành một mảng byte |
| `bodyToMono(String.class)` | Gom nội dung thành một String |
| `bodyToMono(MyDto.class)` | Parse một JSON object thành một DTO; parser có thể giữ token/buffer cho object đó |
| `application/x-www-form-urlencoded` | Phân tích body thành map các form field |
| Multipart qua `getMultipartData()` hoặc `@RequestPart` | Phân tích và tạo cấu trúc parts để truy cập theo tên |
| `DataBufferUtils.join(...)` | Chủ động ghép nhiều buffer thành một buffer |
| Reader tách theo delimiter | Giữ dữ liệu cho tới khi tìm được delimiter hoặc một phần tử hoàn chỉnh |

Các cách đọc trên có thể tiêu thụ nhiều bộ nhớ hơn một pipeline chỉ chuyển từng phần tử. Vì vậy, một response JSON lớn đọc bằng `bodyToMono(String.class)` có thể vượt giới hạn, trong khi một stream gồm nhiều record nhỏ được đọc bằng `Flux<Record>` có thể xử lý tuần tự.

### 2.3. Ví dụ aggregate và streaming

Aggregate toàn bộ body:

```java
Mono<String> body = webClient.get()
        .uri("/export")
        .retrieve()
        .bodyToMono(String.class);
```

Reader phải tạo một String hoàn chỉnh trước khi phát `Mono<String>`. Nếu body lớn hơn ngưỡng của decoder, quá trình đọc có thể thất bại.

Đọc từng record:

```java
Flux<LogEntry> entries = webClient.get()
        .uri("/logs")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .bodyToFlux(LogEntry.class);
```

Với định dạng streaming được hỗ trợ, Jackson decoder có thể phát từng object sau khi object đó đã hoàn chỉnh. Ứng dụng có thể xử lý record rồi tiếp tục nhận record kế tiếp mà không cần tạo một `List` chứa toàn bộ kết quả.

**Lưu ý:** `Flux<T>` tự nó không bảo đảm mọi phần xử lý đều streaming. Nếu gọi `.collectList()`, `.collectMap()`, `.reduce(...)` để giữ toàn bộ kết quả hoặc đổi sang `bodyToMono(List.class)`, ứng dụng lại có thể aggregate dữ liệu. Hãy kiểm tra toàn bộ pipeline, không chỉ kiểu trả về của controller.

## 3. `maxInMemorySize` giới hạn chính xác điều gì?

`maxInMemorySize` giới hạn số byte được buffer khi input stream cần được aggregate. Những tình huống đó có thể gồm:

- Gom nhiều `DataBuffer` thành một buffer hoặc một object.
- Decode một `byte[]`, `ByteBuffer`, `Resource` hoặc `String`.
- Parse một JSON object thành DTO.
- Tách dữ liệu theo delimiter, ví dụ dòng text hoặc một phần tử trong stream.
- Aggregate phần dữ liệu của một SSE event.

Trong trường hợp streaming, giới hạn áp dụng cho số byte gắn với **một object/đơn vị đang được tạo**, không phải tổng byte của tất cả phần tử đã đi qua stream.

Ví dụ giới hạn là 256 KB:

```text
Flux<LogEntry>
  record 1: 12 KB  -> OK
  record 2: 20 KB  -> OK
  record 3: 18 KB  -> OK
  ...
  tổng cả stream: 2 GB -> không tự động vi phạm chỉ vì tổng là 2 GB
```

Nhưng nếu một record đơn lẻ cần buffer 400 KB thì record đó có thể vượt giới hạn:

```text
Flux<LogEntry>
  record 1: 12 KB  -> OK
  record 2: 400 KB -> DataBufferLimitException
  record 3: không được xử lý như bình thường sau lỗi terminal
```

Điều này không có nghĩa stream vô hạn an toàn tuyệt đối. Một pipeline vẫn có thể giữ dữ liệu qua `cache`, `collectList`, hàng đợi không giới hạn hoặc operator tự viết. `maxInMemorySize` bảo vệ các điểm aggregate mà codec/reader quản lý; nó không phải bộ giới hạn heap toàn ứng dụng.

### Giới hạn mặc định

Trong Spring Framework 6.2, phần lớn codec mặc định sử dụng giới hạn **256 KB**. Một số decoder/reader có cấu hình riêng; hãy xem Javadoc của codec cụ thể khi cần biết chính xác. `CodecConfigurer.defaultCodecs().maxInMemorySize(...)` cung cấp một điểm cấu hình chung cho các default codec.

Giá trị được truyền theo byte:

```java
configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
```

Đây là 2 MiB (2.097.152 byte). Không nhầm 2 MB theo hệ thập phân với 2 MiB theo lũy thừa của 1024 khi tính dung lượng.

## 4. `DataBufferLimitException` là gì?

`org.springframework.core.io.buffer.DataBufferLimitException` là một subclass của `IllegalStateException`. Exception biểu thị rằng tổng byte được tiêu thụ từ một stream `DataBuffer` đã vượt ngưỡng cấu hình trước đó.

Nó có thể xuất hiện khi:

- `DataBufferUtils.join(...)` ghép buffer.
- Codec giữ và aggregate dữ liệu trong quá trình decode.
- Jackson asynchronous parsing đang gom token cho một JSON object.
- SSE reader gom các dòng thành một event.
- Reader tách stream theo delimiter nhưng phần dữ liệu trước delimiter quá lớn.

Một message thường gặp:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

Đây là lỗi về giới hạn buffering, không nhất thiết có nghĩa toàn bộ HTTP body quá lớn. Ví dụ một stream 100 MB gồm nhiều JSON record nhỏ có thể được xử lý; một JSON record duy nhất 400 KB có thể vượt ngưỡng 256 KB.

### 4.1. Ví dụ tự tạo lỗi bằng `DataBufferUtils.join`

`DataBufferUtils.join(publisher, maxByteCount)` là API hữu ích khi ứng dụng thực sự cần ghép các buffer và muốn đặt giới hạn riêng cho thao tác đó:

```java
DataBufferFactory factory = new DefaultDataBufferFactory();

Flux<DataBuffer> input = Flux.just(
        factory.wrap(new byte[8]),
        factory.wrap(new byte[8])
);

Mono<DataBuffer> joined =
        DataBufferUtils.join(input, 12);
```

Hai buffer chứa tổng cộng 16 byte, nhưng thao tác join chỉ được phép giữ tối đa 12 byte. Khi subscribe, publisher phát `DataBufferLimitException`.

Không dùng `DataBufferUtils.join(input)` không giới hạn cho body có thể lớn tùy ý. Nếu nghiệp vụ chỉ cần lưu file hoặc chuyển tiếp nội dung, hãy dùng API streaming thay vì ghép toàn bộ body.

### 4.2. `DataBufferLimitException` khác `OutOfMemoryError`

| Đặc điểm | `DataBufferLimitException` | `OutOfMemoryError` |
|---|---|---|
| Nguyên nhân | Một thao tác buffer vượt giới hạn đã cấu hình | JVM không thể cấp phát bộ nhớ cần thiết |
| Tính chất | Exception có thể được xử lý trong reactive pipeline | Error nghiêm trọng của JVM |
| Có thể dự đoán? | Có, nếu giới hạn và kích thước dữ liệu được kiểm soát | Không nhất thiết |
| Cách xử lý | Điều chỉnh thiết kế/giới hạn hoặc trả lỗi phù hợp | Điều tra memory pressure, leak, heap sizing và concurrency |

Giới hạn codec giúp từ chối một thao tác aggregate trước khi nó có thể chiếm lượng bộ nhớ không kiểm soát. Nó không thay thế việc theo dõi heap, GC, số request đồng thời hoặc các nguồn giữ object khác.

## 5. Cấu hình phía server bằng `ServerCodecConfigurer`

Trong Spring WebFlux, có thể tùy chỉnh các codec mặc định thông qua `WebFluxConfigurer`.

```java
@Configuration
public class WebFluxCodecConfiguration
        implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024);
    }
}
```

Ví dụ đặt giới hạn 2 MiB cho các default codec phía server.

### 5.1. Với Spring Boot

Trong ứng dụng Spring Boot, có thể dùng cấu hình:

`application.properties`:

```properties
spring.codec.max-in-memory-size=2MB
```

Hoặc YAML:

```yaml
spring:
  codec:
    max-in-memory-size: 2MB
```

Thuộc tính này áp dụng cho các WebFlux server và WebClient instance được Spring Boot auto-configure. Nếu tự tạo một `WebClient` bằng builder riêng hoặc tự tạo codec configurer ngoài auto-configuration, hãy cấu hình trực tiếp ở builder/configurer tương ứng.

Khi dùng Spring Boot, thường chỉ cần khai báo `WebFluxConfigurer` mà không thêm `@EnableWebFlux`. `@EnableWebFlux` bật cấu hình WebFlux ở chế độ chủ động và có thể làm mất một số tùy chỉnh auto-configuration của Boot nếu không cấu hình lại đầy đủ.

### 5.2. Chọn giới hạn theo nhu cầu endpoint

Không nhất thiết tăng toàn bộ codec lên nhiều chục MB chỉ vì một endpoint nhận file lớn. Hãy xác định:

- Endpoint nào cần aggregate một object lớn?
- Có thể chuyển sang `Flux<T>` hoặc streaming file không?
- Một record lớn nhất dự kiến bao nhiêu byte?
- Có bao nhiêu request có thể cùng aggregate ở mức tối đa?
- Có giới hạn body ở reverse proxy, API gateway hoặc HTTP server không?
- Endpoint có nhận dữ liệu không tin cậy từ client không?

Nếu chỉ một endpoint cần một object JSON lớn, hãy cân nhắc một thiết kế riêng cho endpoint đó thay vì mở rộng giới hạn chung cho toàn bộ API.

## 6. Cấu hình phía client bằng `WebClient`

`WebClient` cũng dùng codec để decode response body. Vì vậy `DataBufferLimitException` có thể xuất hiện khi ứng dụng gọi một API khác và cố đọc response lớn thành một object/string duy nhất.

Cấu hình giới hạn 2 MiB cho default codecs của một `WebClient`:

```java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(2 * 1024 * 1024))
        .build();
```

Nếu ứng dụng dùng `WebClient.Builder` do Spring Boot inject, có thể tận dụng cấu hình `spring.codec.max-in-memory-size`. Với client builder tự tạo, khai báo `.codecs(...)` rõ ràng giúp biết giới hạn nào đang được áp dụng.

### 6.1. Chọn body API phù hợp

Aggregate response thành String:

```java
Mono<String> report = client.get()
        .uri("/reports/large")
        .retrieve()
        .bodyToMono(String.class);
```

Cách này cần giữ toàn bộ nội dung report trong bộ nhớ dưới dạng một String. Nó phù hợp khi response nhỏ và nghiệp vụ thật sự cần nội dung hoàn chỉnh.

Đọc từng record:

```java
Flux<ReportRow> rows = client.get()
        .uri("/reports/stream")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .bodyToFlux(ReportRow.class);
```

Sau đó xử lý tuần tự:

```java
Mono<Void> processing = rows
        .concatMap(reportService::process)
        .then();
```

`concatMap` giữ thứ tự và chỉ chuyển sang xử lý phần tử tiếp theo sau khi publisher của phần tử hiện tại hoàn tất. Nếu nghiệp vụ cho phép xử lý đồng thời, có thể dùng `flatMap` với concurrency được giới hạn. Không dùng concurrency vô hạn cho stream lớn.

### 6.2. Đừng cache response lớn mà không có giới hạn

Những cách sau có thể biến một luồng thành dữ liệu được giữ trong bộ nhớ:

```java
Mono<List<ReportRow>> allRows = rows.collectList();

Mono<String> allText = rows
        .map(ReportRow::toString)
        .collect(Collectors.joining("\n"));
```

Chúng có thể phù hợp với tập dữ liệu nhỏ, có giới hạn rõ. Với dữ liệu lớn, hãy xử lý từng phần tử, ghi ra file/database theo batch hoặc chuyển tiếp stream tới downstream.

## 7. Multipart: file part và non-file part có quy tắc khác nhau

Multipart không nên được hiểu đơn giản là một body duy nhất có giới hạn 256 KB.

Trong WebFlux multipart parsing:

- `maxInMemorySize` giới hạn kích thước của **non-file part** được giữ trong bộ nhớ.
- Với **file part**, thuộc tính này là ngưỡng mà sau đó nội dung file được ghi ra đĩa.
- File part ghi ra đĩa còn có `maxDiskUsagePerPart` để giới hạn dung lượng đĩa cho từng part.
- `maxParts` giới hạn tổng số part trong một request.
- `file-storage-directory` chỉ định thư mục lưu các file part vượt ngưỡng; mặc định là thư mục `spring-multipart` bên dưới thư mục tạm của hệ thống.

Ví dụ Spring Boot 3.3:

```properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=1GB
spring.webflux.multipart.max-parts=20
spring.webflux.multipart.file-storage-directory=/var/app/upload-tmp
```

Các thuộc tính multipart này có phạm vi khác với `spring.codec.max-in-memory-size`. Hãy đặt cả hai theo đặc điểm của API nếu ứng dụng vừa nhận JSON/form body vừa nhận file.

### 7.1. `FilePart.transferTo` thay vì đọc toàn file thành byte array

```java
@PostMapping(
        path = "/files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<ResponseEntity<Void>> upload(
        @RequestPart("file") FilePart file) {

    Path destination = uploadDirectory.resolve(
            UUID.randomUUID() + ".bin");

    return file.transferTo(destination)
            .thenReturn(ResponseEntity.accepted().build());
}
```

Ví dụ minh họa việc lưu file part vào đĩa. Tên file đích được tạo từ UUID; không ghép trực tiếp `file.filename()` vào filesystem path nếu chưa kiểm tra để tránh path traversal. Trong ứng dụng thực, cần xác thực quyền, giới hạn dung lượng, kiểm tra loại file và dọn file tạm theo lifecycle.

Tránh:

```java
file.content()
        .reduce(new byte[0], this::append);
```

hoặc đọc thành `byte[]` lớn nếu mục tiêu cuối cùng chỉ là ghi file. Việc aggregate file vào một mảng có thể gây memory pressure và vượt giới hạn codec.

### 7.2. Multipart streaming bằng `PartEvent`

Khi cần xử lý multipart theo luồng, WebFlux hỗ trợ `Flux<PartEvent>`. Cách này tránh yêu cầu parse toàn bộ nội dung thành `MultiValueMap` chỉ để truy cập parts theo tên.

Ví dụ signature:

```java
@PostMapping(
        path = "/stream-upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<Void> upload(
        @RequestBody Flux<PartEvent> events) {

    return events
            .concatMap(this::processPartEvent)
            .then();
}
```

`processPartEvent` là hàm ứng dụng cần viết để xử lý header, loại part, buffer và ranh giới cuối part. Nếu tự đọc `PartEvent.content()` hoặc `DataBuffer`, phải quản lý việc tiêu thụ/giải phóng buffer đúng contract. Với API upload đơn giản, `FilePart.transferTo` thường dễ bảo trì hơn.

## 8. Streaming để tránh aggregate dữ liệu lớn

### 8.1. NDJSON cho nhiều JSON record

NDJSON (Newline Delimited JSON) đặt mỗi object trên một dòng:

```text
{"id":1,"value":"alpha"}
{"id":2,"value":"beta"}
{"id":3,"value":"gamma"}
```

Controller có thể nhận:

```java
@PostMapping(
        path = "/events",
        consumes = "application/x-ndjson"
)
public Mono<Void> ingest(
        @RequestBody Flux<Event> events) {

    return events
            .concatMap(eventService::process)
            .then();
}
```

Jackson decoder hỗ trợ stream JSON object theo định dạng như NDJSON. Mỗi object được phát khi parser đã nhận đủ dữ liệu cho object đó; giới hạn bộ nhớ áp dụng theo object đang được parse. Vì vậy tổng stream có thể lớn hơn `maxInMemorySize` nếu từng object vẫn nằm trong giới hạn và downstream tiêu thụ đều.

Không chuyển `Flux<Event>` thành `List<Event>` nếu không cần toàn bộ danh sách cùng lúc.

### 8.2. JSON array và `Flux<T>`

Jackson decoder cũng hỗ trợ đọc JSON array thành nhiều giá trị trong `Flux<T>`. Ví dụ:

```json
[
  {"id":1,"value":"alpha"},
  {"id":2,"value":"beta"},
  {"id":3,"value":"gamma"}
]
```

Có thể nhận:

```java
@PostMapping("/events-json")
public Mono<Void> ingestJsonArray(
        @RequestBody Flux<Event> events) {

    return events.concatMap(eventService::process).then();
}
```

Đừng nhầm decoder với encoder. Với multi-value publisher dùng `application/json`, `Jackson2Encoder` mặc định có thể thu thập các giá trị thành list trước khi serialize thành JSON array. Nếu cần ghi từng phần tử và flush tuần tự, dùng media type streaming như `application/x-ndjson` hoặc một streaming format phù hợp.

### 8.3. Server-Sent Events

SSE là stream các event được phân tách bằng dòng. WebFlux có thể decode/encode từng event, nhưng reader cần gom các dòng thuộc một event để parse hoàn chỉnh. Một event đơn lẻ quá lớn hoặc một dòng không có delimiter quá dài vẫn có thể vượt giới hạn buffer.

Vì vậy, khi dùng SSE:

- Giữ từng event nhỏ và có cấu trúc rõ.
- Không đưa toàn bộ log hoặc tài liệu lớn vào một event.
- Gửi heartbeat định kỳ khi stream dài để phát hiện client disconnect.
- Không aggregate toàn bộ stream bằng `collectList()`.
- Đặt giới hạn event phù hợp với contract.

### 8.4. Backpressure không thay thế giới hạn buffer

Backpressure điều tiết tốc độ producer/consumer bằng demand. Nó không tự động bảo đảm mọi operator đều dùng bộ nhớ hằng định. Một operator có thể prefetch, cache hoặc gom dữ liệu. Một ứng dụng cũng có thể dùng queue riêng không giới hạn.

Thiết kế streaming an toàn cần đồng thời:

1. Publisher phát dữ liệu theo từng phần tử.
2. Downstream tiêu thụ theo demand.
3. Operator có concurrency/prefetch được kiểm soát.
4. Không gom toàn bộ stream vào collection.
5. Các buffer được release khi đã dùng hoặc bị discard.
6. Có giới hạn riêng cho phần tử đơn lẻ và các tài nguyên ngoài heap.

## 9. Quản lý `DataBuffer` và tránh leak

Với các ứng dụng chỉ dùng `@RequestBody DTO`, `bodyToMono`, `bodyToFlux`, `FilePart` và codec mặc định, Spring thường quản lý vòng đời buffer. Ứng dụng phải chú ý hơn khi đọc/ghi trực tiếp `DataBuffer`, tạo custom codec hoặc dùng operator có thể loại bỏ buffer.

### 9.1. Buffer có thể được pool và reference-counted

Một số connector như Reactor Netty sử dụng pooled buffer. Khi dữ liệu được tiêu thụ, buffer cần được release để trả tài nguyên về pool. Nếu giữ buffer sau khi pipeline kết thúc hoặc bỏ buffer mà không release, ứng dụng có thể bị memory leak.

Các API hỗ trợ:

- `DataBufferUtils.release(dataBuffer)`: release nếu buffer thuộc loại pooled/closeable cần giải phóng.
- `DataBufferUtils.retain(dataBuffer)`: tăng reference count khi cần giữ buffer lâu hơn contract hiện tại.
- `DataBufferUtils.join(...)`: ghép buffer an toàn và quản lý buffer đầu vào trong quá trình aggregate.
- `doOnDiscard(DataBuffer.class, DataBufferUtils::release)`: release buffer bị operator discard khi composition được thiết kế theo pattern phù hợp.

Không gọi `release` tùy tiện trên buffer mà framework hoặc downstream vẫn đang sở hữu. Mỗi buffer cần một ownership rõ ràng: ai đọc, ai giữ và ai release.

### 9.2. Operator có thể discard buffer

Các operator như `filter`, `skip`, `take`, `flatMap` hoặc các operator có prefetch/cache có thể loại bỏ phần tử trong một số đường lỗi/cancel. Khi phần tử bị loại bỏ là pooled `DataBuffer`, cần đảm bảo nó được release.

Ví dụ pattern trong một decoder/custom pipeline:

```java
Flux<DataBuffer> safe = source
        .filter(this::isUseful)
        .doOnDiscard(
                DataBuffer.class,
                DataBufferUtils::release);
```

Đây là ví dụ về discard hook, không phải công thức phải thêm vào mọi `Flux<DataBuffer>`. Chỉ thêm khi operator thực sự có thể discard buffer và ownership thuộc pipeline này.

### 9.3. Khi dùng `DataBufferUtils.join`

```java
Mono<DataBuffer> joined = DataBufferUtils.join(
        request.getBody(),
        1024 * 1024);
```

Thao tác này giới hạn phần body được ghép ở 1 MiB. Khi nhận buffer kết quả, code tiêu thụ phải bảo đảm release sau khi đọc xong. Nếu chỉ muốn lưu/forward stream, không cần join.

Đừng tự chuyển `DataBuffer` sang `byte[]` rồi giữ nhiều bản sao không cần thiết. Trong quá trình xử lý có thể đồng thời tồn tại buffer gốc, mảng byte, String UTF-16 và object JSON, khiến mức tiêu thụ thực tế cao hơn kích thước wire body.

## 10. `DataBufferLimitException` và HTTP status

`DataBufferLimitException` là exception của Spring Core, không mang sẵn HTTP status. Nó không tự động có nghĩa response phải là `413 Payload Too Large`.

Cần phân biệt nơi exception xảy ra:

| Nơi phát sinh | Ý nghĩa |
|---|---|
| Server đang decode request body | Server không thể tiếp tục aggregate body/record trong giới hạn codec |
| WebClient đang decode response body | Ứng dụng client không thể decode response trong giới hạn local |
| Custom `DataBufferUtils.join` | Chính thao tác join đã vượt `maxByteCount` |
| Multipart parser | Một part vượt giới hạn memory/disk/parts theo cấu hình reader |

Ở server, lỗi decode request có thể được bọc trong exception input/codec trước khi tới exception handler. Status mặc định phụ thuộc đường xử lý và cấu hình lỗi. Nếu API muốn biểu diễn riêng việc vượt ngưỡng body bằng 413, hãy chủ động nhận diện `DataBufferLimitException` trong cause chain và ánh xạ ở `@ControllerAdvice` hoặc `WebExceptionHandler`.

Ở client, nếu WebClient nhận status 200 nhưng body vượt giới hạn decode local, ứng dụng có thể nhận `DataBufferLimitException` trong reactive pipeline. Đây không phải HTTP 413 từ server từ xa; server có thể đã trả response thành công.

### Ví dụ ánh xạ có chủ đích thành 413

```java
@RestControllerAdvice
public class PayloadLimitAdvice {

    @ExceptionHandler({
            DataBufferLimitException.class,
            ServerWebInputException.class
    })
    public ResponseEntity<ProblemDetail> handleInput(Exception error) {
        boolean limitExceeded = hasCause(
                error, DataBufferLimitException.class);

        HttpStatus status = limitExceeded
                ? HttpStatus.PAYLOAD_TOO_LARGE
                : HttpStatus.BAD_REQUEST;

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                limitExceeded
                        ? "The request contains a buffered item that is too large."
                        : "The request body could not be read.");

        problem.setTitle(limitExceeded
                ? "Payload limit exceeded"
                : "Invalid request body");

        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expected) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (expected.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

Đây là chính sách minh họa. Tùy codec/argument resolver, exception có thể được bọc qua nhiều lớp; kiểm thử với phiên bản Spring và endpoint thực tế để xác nhận cause chain. Không trả stack trace, tên file nội bộ hoặc raw body cho client.

## 11. Chọn ngưỡng theo ngân sách bộ nhớ

Không tăng `maxInMemorySize` một cách tùy tiện chỉ để hết lỗi. Hãy ước lượng mức tiêu thụ khi có nhiều request cùng chạy.

Ví dụ giả định:

- Giới hạn aggregate cho một request: 2 MiB.
- Có 200 request đồng thời cùng đi qua điểm aggregate.
- Mức dữ liệu aggregate lý thuyết: khoảng 400 MiB.

Đây chỉ là phần dữ liệu buffer theo giới hạn, chưa tính object đã decode, token buffer, bản sao String/byte array, response buffer, queue, connection, heap của framework và phần còn lại của ứng dụng. Một giới hạn 10 MiB có vẻ nhỏ khi xét một request nhưng rất lớn khi nhân với hàng trăm request đồng thời.

Khi chọn ngưỡng:

1. Đo kích thước payload hợp lệ lớn nhất trong nghiệp vụ.
2. Ước lượng concurrency tại endpoint.
3. Đo heap/GC dưới tải thực tế.
4. Đặt ngưỡng đủ dùng với khoảng dự phòng có kiểm soát.
5. Giới hạn số request đồng thời hoặc tốc độ upload khi cần.
6. Dùng streaming cho file/record lớn.
7. Đặt giới hạn body tổng ở gateway/server nếu API cần bảo vệ toàn bộ request.
8. Đặt giới hạn riêng cho multipart part, số part và dung lượng đĩa.
9. Theo dõi số lỗi `DataBufferLimitException` theo endpoint và codec.
10. Kiểm thử với payload ngay dưới, đúng bằng và vượt giới hạn.

### `-1` có nghĩa gì?

Một số API `maxInMemorySize` chấp nhận `-1` để bỏ giới hạn. Đây là cấu hình nguy hiểm với input không tin cậy hoặc payload có thể lớn tùy ý. Chỉ dùng khi có một cơ chế giới hạn khác đã được chứng minh và hiểu rõ tác động tới bộ nhớ.

Bỏ giới hạn codec không làm dữ liệu trở thành streaming. Nếu code vẫn gọi `bodyToMono(String.class)` hoặc `collectList()`, ứng dụng vẫn có thể giữ toàn bộ dữ liệu trong heap và gặp `OutOfMemoryError`.

## 12. Dự án Java 17+ chạy được: kiểm thử giới hạn codec

Ví dụ dùng Spring Boot 3.3.5, Java 17, Spring WebFlux và `WebTestClient`. Codec server được cấu hình giới hạn 128 byte để kiểm thử nhanh:

- Body text nhỏ được đọc thành công.
- Body text lớn vượt giới hạn được ánh xạ thành 413 theo advice của ứng dụng.
- NDJSON có tổng dung lượng lớn hơn 128 byte vẫn đọc được khi từng record nằm dưới ngưỡng.
- `DataBufferUtils.join` phát `DataBufferLimitException` khi vượt giới hạn riêng.

### 12.1. Cấu trúc

```text
webflux-buffer-limit/
├── pom.xml
└── src/
    ├── main/java/edu/demo/buffer/
    │   ├── BufferApplication.java
    │   ├── CodecConfiguration.java
    │   ├── BufferController.java
    │   └── PayloadLimitAdvice.java
    └── test/java/edu/demo/buffer/
        └── BufferLimitTests.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-buffer-limit</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

### 12.3. `BufferApplication.java`

```java
package edu.demo.buffer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BufferApplication {

    public static void main(String[] args) {
        SpringApplication.run(BufferApplication.class, args);
    }
}
```

### 12.4. `CodecConfiguration.java`

```java
package edu.demo.buffer;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs().maxInMemorySize(128);
    }
}
```

Giới hạn 128 byte chỉ dành cho test để dễ tái hiện. Không dùng con số nhỏ như vậy làm cấu hình production cho JSON API thông thường.

### 12.5. `BufferController.java`

```java
package edu.demo.buffer;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class BufferController {

    public record Event(String value) {
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> echo(@RequestBody Mono<String> body) {
        return body;
    }

    @PostMapping(
            path = "/events",
            consumes = "application/x-ndjson"
    )
    public Mono<Void> events(@RequestBody Flux<Event> events) {
        return events
                .doOnNext(event -> {
                    // Replace with bounded, non-blocking processing.
                })
                .then();
    }
}
```

`/echo` cần tạo một String hoàn chỉnh. `/events` nhận từng NDJSON object và không thu thập tất cả vào list. Trong ứng dụng thật, thay `doOnNext` bằng service reactive có giới hạn concurrency và side effect phù hợp.

### 12.6. `PayloadLimitAdvice.java`

```java
package edu.demo.buffer;

import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
public class PayloadLimitAdvice {

    @ExceptionHandler({
            DataBufferLimitException.class,
            ServerWebInputException.class
    })
    public ResponseEntity<ProblemDetail> handle(Exception error) {
        boolean exceeded = hasCause(
                error, DataBufferLimitException.class);

        HttpStatus status = exceeded
                ? HttpStatus.PAYLOAD_TOO_LARGE
                : HttpStatus.BAD_REQUEST;

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status,
                exceeded
                        ? "A buffered request item exceeded the configured limit."
                        : "The request body could not be read.");

        problem.setTitle(exceeded
                ? "Payload limit exceeded"
                : "Invalid request body");

        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expected) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (expected.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

Advice này là chính sách của sample app: chỉ khi cause chain có `DataBufferLimitException` mới trả 413. Các lỗi đọc body khác trả 400. Một ứng dụng thực cần kiểm thử exception wrapping và có thể cần xử lý thêm loại exception tùy codec/endpoint.

### 12.7. `BufferLimitTests.java`

```java
package edu.demo.buffer;

import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferFactory;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BufferLimitTests {

    @Autowired
    WebTestClient client;

    @Test
    void smallTextBodyIsAccepted() {
        client.post()
                .uri("/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("hello");
    }

    @Test
    void oversizedAggregatedBodyMapsTo413() {
        String large = "x".repeat(1024);

        client.post()
                .uri("/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue(large)
                .exchange()
                .expectStatus().isEqualTo(413)
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.title")
                .isEqualTo("Payload limit exceeded");
    }

    @Test
    void streamCanExceedTotalLimitWhenEachRecordIsSmall() {
        String ndjson = IntStream.range(0, 20)
                .mapToObj(index ->
                        "{\"value\":\"record-" + index + "\"}")
                .collect(Collectors.joining("\n"));

        client.post()
                .uri("/events")
                .contentType(MediaType.parseMediaType(
                        "application/x-ndjson"))
                .bodyValue(ndjson)
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void joinFailsWhenCumulativeBytesExceedItsLimit() {
        DataBufferFactory factory = new DefaultDataBufferFactory();

        Flux<DataBuffer> buffers = Flux.just(
                factory.wrap(new byte[8]),
                factory.wrap(new byte[8]));

        StepVerifier.create(DataBufferUtils.join(buffers, 12))
                .expectError(DataBufferLimitException.class)
                .verify();
    }
}
```

### 12.8. Chạy test

Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Khi dependencies tải thành công và môi trường test hoạt động, bộ test có bốn trường hợp:

1. Body nhỏ được đọc thành công.
2. Body aggregate 1.024 byte vượt giới hạn 128 byte và advice trả 413.
3. NDJSON có tổng dung lượng lớn hơn 128 byte vẫn được đọc khi từng record nhỏ hơn giới hạn.
4. `DataBufferUtils.join` phát `DataBufferLimitException` khi tổng buffer vượt 12 byte.

Kết quả mong đợi của Maven Surefire:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

Đây là kết quả cần đối chiếu sau khi chạy `mvn test`; tài liệu không tuyên bố đã thực thi Maven trong môi trường biên soạn.

## 13. Chẩn đoán khi gặp `DataBufferLimitException`

Khi log xuất hiện `Exceeded limit on max bytes to buffer`, kiểm tra theo trình tự:

1. Exception phát sinh ở server hay ở WebClient?
2. Endpoint đang dùng `Mono<T>`, `byte[]`, `String`, `collectList()` hay `Flux<T>`?
3. Codec nào đang decode? Jackson, String, form, SSE hay multipart?
4. Giới hạn thực tế đến từ codec mặc định, `WebFluxConfigurer`, `spring.codec.max-in-memory-size` hay cấu hình riêng của WebClient?
5. Nếu là stream, phần tử đơn lẻ nào vượt giới hạn?
6. Nếu là multipart, đó là non-file part hay file part? Ngưỡng spill-to-disk, max disk usage và max parts đã được đặt chưa?
7. Có filter, logger hoặc custom decoder nào đang đọc/aggregate body thêm lần nữa không?
8. Có `collectList`, `cache`, `join`, `reduce` hoặc queue không giới hạn sau khi decode không?
9. Số request đồng thời và mức heap/GC tại thời điểm lỗi ra sao?
10. Có thể xử lý theo stream, chia batch hoặc ghi trực tiếp ra storage không?

### Phân biệt các lỗi dễ nhầm

| Lỗi | Ý nghĩa | Hướng điều tra |
|---|---|---|
| `DataBufferLimitException` | Thao tác buffer/aggregate vượt ngưỡng | Codec limit, kích thước record, `join`, delimiter |
| `OutOfMemoryError` | JVM cạn bộ nhớ cấp phát | Heap dump, leak, object retention, concurrency |
| 413 Payload Too Large | HTTP server/gateway/API contract từ chối payload quá lớn | Request-size policy và body limit ở từng tầng |
| 415 Unsupported Media Type | Server không hỗ trợ Content-Type | Codec/reader và `consumes` |
| JSON decode error | Body không parse được thành kiểu đích | Syntax, JSON shape, DTO, Jackson |
| Timeout | Quá thời gian chờ I/O hoặc xử lý | Network, scheduler, upstream, timeout config |

`413` không tự động xuất hiện chỉ vì codec ném `DataBufferLimitException`; cần ánh xạ theo API contract. Ngược lại, một gateway có thể trả 413 trước khi request tới WebFlux nên ứng dụng không thấy exception này.

### Log và metrics

Nên ghi nhận:

- Request ID/correlation ID.
- Route template và HTTP method.
- Phía server hay client.
- Codec/operation nếu có thể xác định.
- Kích thước ước lượng hoặc content length khi đáng tin cậy.
- Số lần lỗi theo endpoint và thời gian.
- Heap, GC và concurrency ở thời điểm lỗi.

Không log toàn bộ body chỉ để tìm nguyên nhân; chính hành động log body có thể aggregate dữ liệu và làm tái hiện lỗi. Không ghi token, password, PII hoặc file content vào log.

## 14. Lỗi thiết kế thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Tăng `maxInMemorySize` rất lớn để che mọi lỗi | Nhiều request đồng thời có thể gây memory pressure/OOM | Chọn giới hạn theo kích thước record và concurrency |
| Đặt `-1` cho input không tin cậy | Aggregate không có ngưỡng bảo vệ | Giữ giới hạn hữu hạn và dùng streaming |
| Đọc file lớn bằng `byte[]` hoặc `String` | Toàn bộ file nằm trong heap | `FilePart.transferTo` hoặc streaming tới storage |
| Gọi `collectList()` cho stream dài | Tích lũy toàn bộ record trong bộ nhớ | Xử lý từng record hoặc batch có giới hạn |
| Nghĩ `Flux<T>` luôn streaming | Operator downstream có thể vẫn aggregate | Kiểm tra toàn pipeline và media type |
| Gửi một JSON object rất lớn trong NDJSON | Một record vẫn vượt ngưỡng | Chia object thành phần nhỏ hoặc tăng ngưỡng có kiểm soát |
| Nhầm limit codec với giới hạn tổng upload | Bỏ sót body-size policy ở gateway/server | Đặt giới hạn tổng riêng cho request |
| Nhầm multipart threshold với file-size cap | File lớn vẫn có thể ghi xuống đĩa | Cấu hình `maxDiskUsagePerPart`, `maxParts` và giới hạn tổng |
| Gọi `DataBufferUtils.join` không giới hạn | Ghép body lớn vào bộ nhớ | Dùng overload có `maxByteCount` |
| Tự đọc `DataBuffer` nhưng không release | Pooled buffer leak | Quản lý ownership và release đúng contract |
| Dùng `filter`/`skip` trên DataBuffer mà bỏ qua discard | Buffer bị bỏ không được release | Dùng `doOnDiscard` phù hợp |
| Chỉ kiểm tra status 413 | Bỏ sót lỗi client-side decode hoặc lỗi 400 | Kiểm tra exception/cause chain và nơi phát sinh |
| Log body để debug | Tạo thêm aggregate, lộ dữ liệu | Log metadata an toàn và trace ID |
| Dùng concurrency không giới hạn để xử lý stream | Nhiều object/buffer cùng nằm trong bộ nhớ | Dùng `flatMap` có concurrency hoặc `concatMap` |

## 15. Checklist cấu hình production

Trước khi đưa endpoint nhận dữ liệu lớn vào production:

- Đã xác định codec/reader thực sự aggregate dữ liệu chưa?
- `maxInMemorySize` có phù hợp với kích thước tối đa của một object/record không?
- Giới hạn có được áp dụng đúng cho cả WebFlux server và WebClient cần dùng không?
- WebClient tự tạo có cấu hình codec riêng không?
- Multipart non-file part, file threshold, disk usage và số part có giới hạn không?
- File part có được stream/transfer ra storage thay vì gom vào byte array không?
- NDJSON/SSE có kích thước từng record/event hữu hạn không?
- Có tránh `collectList`, `cache`, `join` và queue không giới hạn không?
- Các operator xử lý `DataBuffer` có release buffer bị tiêu thụ hoặc discard đúng cách không?
- Có giới hạn concurrency, upload rate và request-size ở gateway/server không?
- Có phân biệt lỗi codec ở server với lỗi decode response ở WebClient không?
- Status/error body có được ánh xạ theo contract thay vì giả định 413 mặc định không?
- Có test dưới ngưỡng, vượt ngưỡng, stream nhiều record nhỏ và multipart file lớn không?
- Có metrics cho số lỗi limit, heap, GC, request concurrency và thời gian xử lý không?

## 16. Bài tập tự kiểm tra

**Bài 1.** `bodyToMono(String.class)` nhận response 1 MB trong khi codec limit là 256 KB. Điều gì có thể xảy ra?

**Đáp án:** Reader phải aggregate toàn bộ body thành String; nó có thể phát `DataBufferLimitException` khi vượt 256 KB.

**Bài 2.** Một `Flux<Event>` có 10.000 record, mỗi record 2 KB. Tổng stream khoảng 20 MB, codec limit 256 KB. Stream có chắc chắn thất bại không?

**Đáp án:** Không. Với streaming decoder, giới hạn áp dụng cho từng object đang được gom; tổng stream có thể lớn hơn giới hạn nếu mỗi record nằm trong ngưỡng và downstream tiêu thụ tuần tự.

**Bài 3.** Một NDJSON record đơn lẻ có kích thước 500 KB, limit 256 KB. Điều gì xảy ra?

**Đáp án:** Record đó có thể vượt giới hạn vì parser phải giữ đủ dữ liệu cho một object hoàn chỉnh.

**Bài 4.** Multipart file 100 MB có bắt buộc giữ 100 MB trong heap không?

**Đáp án:** Không. `maxInMemorySize` là ngưỡng ghi file part xuống đĩa; file part lớn hơn ngưỡng có thể được lưu vào thư mục tạm. Cần cấu hình giới hạn dung lượng đĩa và số part.

**Bài 5.** `DataBufferLimitException` có luôn trả HTTP 413 không?

**Đáp án:** Không. Đây là exception của Spring Core, không mang HTTP status. Ứng dụng có thể chủ động ánh xạ thành 413; status thực tế phụ thuộc nơi phát sinh và exception handling.

**Bài 6.** Vì sao tăng limit lên `-1` không phải cách sửa bền vững?

**Đáp án:** `-1` bỏ giới hạn aggregate. Nếu request lớn hoặc nhiều request đồng thời, ứng dụng có thể giữ lượng dữ liệu rất lớn và gặp `OutOfMemoryError`.

**Bài 7.** Vì sao cần `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` trong một số custom pipeline?

**Đáp án:** Một số operator có thể discard buffer khi filter/skip/error/cancel. Với pooled DataBuffer, cần release những buffer bị loại bỏ mà pipeline sở hữu.

**Bài 8.** WebClient nhận HTTP 200 nhưng decode response thất bại vì vượt memory limit. Có thể nói server đã trả 413 không?

**Đáp án:** Không. Server có thể đã trả 200; lỗi xảy ra ở client khi decode response theo giới hạn local.

## 17. Ghi nhớ

- `maxInMemorySize` giới hạn byte được aggregate trong bộ nhớ bởi codec/reader.
- Phần lớn codec mặc định của Spring Framework 6.2 có ngưỡng 256 KB; cấu hình cụ thể có thể thay đổi theo codec.
- `DataBufferLimitException` báo tổng byte trong một thao tác buffer/aggregate vượt ngưỡng.
- Với streaming, giới hạn áp dụng theo object/record/event đang được gom, không phải tổng byte của toàn stream.
- Server dùng `ServerCodecConfigurer`; WebClient dùng `WebClient.Builder.codecs(...)`; Spring Boot có `spring.codec.max-in-memory-size`.
- Multipart dùng `maxInMemorySize` làm giới hạn non-file part và ngưỡng spill-to-disk cho file part; cần thêm giới hạn disk và số part.
- `Flux<T>` chỉ giúp streaming khi downstream không gom toàn bộ dữ liệu.
- Nếu xử lý trực tiếp `DataBuffer`, phải quản lý release/retain và discard đúng contract.
- `DataBufferLimitException` không tự động có nghĩa HTTP 413; hãy ánh xạ có chủ đích.
- Đừng chỉ tăng ngưỡng: chọn cách đọc/ghi streaming, giới hạn concurrency và đo memory dưới tải.

Khi gặp lỗi, hãy trả lời ba câu hỏi: **đang aggregate cái gì, giới hạn áp dụng cho đơn vị nào, và có thể xử lý từng phần tử thay vì giữ toàn bộ nội dung hay không?**

## Tài liệu chính thức

- Spring Framework 6.2, **WebFlux Reactive Core – Limits, Codecs, Multipart và DataBuffer**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2, **Data Buffers and Codecs**: https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html
- Spring Framework 6.2, **WebFlux HTTP Message Codec Configuration**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html
- Spring Framework 6.2, **WebClient Configuration and MaxInMemorySize**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html
- Spring Framework 6.2, **`DataBufferLimitException` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/io/buffer/DataBufferLimitException.html
- Spring Framework 6.2, **`DataBufferUtils` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
- Spring Framework 6.2, **`CodecConfigurer.DefaultCodecs` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/codec/CodecConfigurer.DefaultCodecs.html
- Spring Boot 3.3, **Common Application Properties – codec and multipart limits**: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.2, **WebTestClient**: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html