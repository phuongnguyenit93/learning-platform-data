# Giới hạn kích thước dữ liệu, tốc độ tiêu thụ và tránh gom toàn bộ stream trong Spring WebFlux

## 1. Bài toán và mục tiêu

Spring WebFlux và Project Reactor giúp xây dựng HTTP pipelines xử lý dữ liệu **theo luồng (streaming)**, trong đó nguồn phát, toán tử xử lý và phía tiêu thụ có thể tiến hành dần thay vì đợi toàn bộ body đến đủ. Tuy nhiên, “ứng dụng trả `Flux`” **không đồng nghĩa bộ nhớ luôn bị giới hạn**, “non-blocking” **không đồng nghĩa vô hạn throughput**, và “có backpressure” **không đồng nghĩa tất cả các downstream, proxy hay cơ sở dữ liệu tự biết giảm tốc**.

Một request có thể vượt giới hạn vì:
- Client gửi một body lớn hoặc upload chậm, và server chờ/đệm quá nhiều bytes.
- JSON decoder buộc phải gom một object lớn, dù endpoint được viết theo reactive API.
- Code gọi `collectList()`, `collectMap()`, `reduce` với accumulator lớn hoặc `DataBufferUtils.join(...)` không giới hạn.
- Một nguồn phát nhanh hơn người đọc, dẫn tới buffers/queues trong `flatMap`, hot source, WebClient hoặc gateway phình ra.
- Một file download rất lớn được đọc toàn bộ thành `byte[]` trước khi response được gửi.
- Retry, timeout, connection pool và số request đồng thời khiến tổng memory tăng dù từng request có giới hạn riêng.

Sau bài này, bạn sẽ biết cách:

1. Phân biệt **limit kích thước** (bytes/items), **rate limiting** (bytes/giây, requests/giây), **concurrency limiting**, **backpressure/demand**, **timeout** và **quota**.
2. Nêu chính xác phạm vi của `maxInMemorySize` trong Spring WebFlux codecs, `DataBufferLimitException`, `DataBufferUtils.join(source, maxByteCount)`.
3. Xử lý `Flux<DataBuffer>` mà không giữ toàn body; đếm bytes bằng một state nhỏ và release buffers sau khi đã tiêu thụ.
4. Tạo response NDJSON/SSE theo luồng, tránh materialize vô hạn bằng `collectList()` hay `block()` trong event loop.
5. Hiểu `limitRate`, `limitRequest`, `take`, `flatMap(..., concurrency)`, `concatMap`, `onBackpressureBuffer`, `onBackpressureLatest` và `sample`, cùng hậu quả khi drop events.
6. Đặt limits tại nhiều lớp: ingress, WebFlux codec, application-level cumulative bytes, WebClient, connection pools, slow-client controls và storage.
7. Chạy ví dụ **Java 17+, Spring Boot 3.x, Spring Framework 6.x** với REST endpoint đếm bytes upload có hard limit và endpoint NDJSON streaming; dùng `WebTestClient` kiểm tra HTTP 200/413 và các chunks.
8. Thiết kế cleanup/cancellation/error, quan sát metrics và tránh hiểu sai kết quả benchmark.

**Phạm vi:** WebFlux với Reactor/Reactive Streams và Reactor Netty phổ biến trong Spring Boot 3.x. Dù dùng các phần tử của Spring Framework 6.2 để giải thích, hãy đối chiếu API theo phiên bản project thực tế. Bài không tuyên bố WebFlux tự làm toàn bộ I/O trong ứng dụng thành non-blocking nếu bên dưới còn JDBC/SDK/file API blocking.

## 2. Sơ đồ luồng dữ liệu và nơi có thể tích tụ bộ nhớ

Một endpoint có thể đi qua nhiều vùng đệm:

~~~text
HTTP client / upstream
         |
         | TCP incoming bytes / headers / chunks
         v
Ingress / CDN / reverse proxy
         |  - max request body
         |  - read timeout, slow client protection
         |  - buffering có thể bật/tắt theo route
         v
Netty HTTP receive / request body Flux<DataBuffer>
         |
         |  decoder & message reader (JSON/NDJSON/multipart)
         |  maxInMemorySize áp dụng theo ngữ cảnh
         v
Controller -> Reactor operators
         |  - map/filter, flatMap queues, buffers
         |  - collectList / join (aggregate!)
         |  - concurrency/prefetch/rate policy
         v
Service / WebClient / R2DBC / file storage
         |  - pool / DB connection / upstream timeout
         v
WebFlux response encoder / HTTP send
         |  - codec, TCP send buffers, slow reader
         v
Proxy / Browser
~~~

Với từng ranh giới phải trả lời:
- **Ai cấp phát dữ liệu?** Java heap, direct/native buffers, temp disk hay remote queue?
- **Ai có quyền giải phóng?** Framework decoder, owner của DataBuffer, writer, store, cancellation handler?
- **Có hard limit rõ ràng không?** Per element, per HTTP request, per user/tenant, per instance và hệ thống?
- **Có backpressure thật sự không?** Có từ `Publisher` tới nguồn đọc được không, hay upstream service/message broker vẫn push?
- **Có điểm nào giữ toàn bộ body trước khi xử lý không?** `bodyToMono(byte[].class)`, `collectList`, `join`, proxy buffering?
- **Nếu client disconnect thì sao?** Downstream có cancel không, buffers đã cấp phát có được dọn không, filesystem/object storage có file dở không?

Cần nhìn **cả chuỗi**, không chỉ đặt một operator Reactor rồi mặc định mọi tầng đều an toàn.

## 3. Phân biệt năm loại giới hạn dễ nhầm

| Cơ chế | Kiểm soát gì? | Ví dụ | Không thay thế được |
| --- | --- | --- | --- |
| **Kích thước** | Tổng byte/part/item sau khi đọc | Upload tối đa 10 MiB | Tốc độ gửi bytes và request flood |
| **Tốc độ** | Số bytes/items được xử lý trong một đơn vị thời gian | 1 MiB/s mỗi tenant | Tổng bytes/1 request |
| **Demand/backpressure** | Số phần tử downstream đang yêu cầu upstream | Reactive Streams `request(n)` | Global rate limit |
| **Concurrency** | Số operation/connection đang active | Chỉ 8 remote calls đồng thời | Bytes/connection và timeout |
| **Thời gian/quota** | Deadline, idle timeout, dung lượng theo user/ngày | 30 s/request, 1 GiB/ngày | Buffer leaks và malformed payload |

Ví dụ: giới hạn `flatMap(..., 8)` cho tối đa khoảng 8 inner subscriptions hoạt động trong toán tử đó, **nhưng** nếu mỗi subscription tải 1 GiB bằng `collectList`, ứng dụng vẫn có thể OOM. Giới hạn **tổng bytes** 10 MiB nhưng không có minimum upload rate, client có thể giữ kết nối hàng giờ bằng cách gửi 1 byte mỗi phút. Còn `limitRate(16)` yêu cầu upstream theo từng đợt tối đa 16 phần tử, **không** thể hứa tốc độ 16 event/giây.

### 3.1. Tính tổng tài nguyên theo concurrency

Giả sử ứng dụng cho phép 200 uploads đồng thời, và mỗi upload có thể giữ tạm 1 MiB trong memory. Chỉ riêng phần đó có thể cần khoảng **200 MiB**, chưa tính JVM, Netty direct buffers, TLS buffers, encoder, databases và các request khác.

~~~text
Tổng ngân sách bộ nhớ cho buffers
  ≈ số requests đồng thời × buffered bytes/request
  + các queue/cache/shared pools
  + overhead của framework và runtime.
~~~

Đây là **ước lượng**, không phải một đẳng thức heap chính xác: dữ liệu có thể ở native/direct memory, temp disk hoặc object storage. Chỉ giới hạn per request mà không đặt concurrency budget vẫn chưa đủ.

## 4. Backpressure: nhu cầu tiêu thụ phần tử chứ không phải tốc độ thời gian

Trong Reactive Streams, subscriber gọi `request(n)` thông báo muốn nhận tối đa n phần tử tiếp theo. Publisher có thể emit tới số lượng đã yêu cầu theo hợp đồng. Reactor operators phối hợp demand qua chuỗi khi nguồn hỗ trợ.

Ví dụ:

~~~java
Flux<Integer> source = Flux.range(1, 100);

Flux<Integer> boundedDemand = source.limitRate(8);
~~~

`limitRate(8)` chia demand lớn downstream thành các yêu cầu nhỏ hơn upstream, có cơ chế replenishment. Nó **không** đặt `sleep(1/8s)`; một nguồn dữ liệu có sẵn có thể phát cả 100 phần tử rất nhanh.

### 4.1. `limitRate` không phải bandwidth throttle

~~~java
flux.limitRate(32);
~~~

Điều trên là `request(n)` batching cho Reactor; nó không giới hạn mỗi phần tử là bao nhiêu bytes. Nếu mỗi DataBuffer 64 KiB thì 32 phần tử tương đương tới khoảng 2 MiB dữ liệu; nếu mỗi phần tử là vài bytes thì chỉ rất nhỏ. Hơn nữa, upstream/bridges không hợp tác có thể đã buffer sẵn.

`limitRate(highTide, lowTide)` cho phép cấu hình nhu cầu/replenishment. `lowTide=0` giúp request theo lô nghiêm ngặt hơn, nhưng vẫn không phải token bucket theo clock.

### 4.2. `take(n)`/limitRequest không thay byte limit

~~~java
Flux<String> firstTen = source.take(10);
~~~

Câu lệnh này chỉ lấy **10 phần tử**, bất kể mỗi phần tử dài 10 bytes hay 10 MiB. Nếu một NDJSON document hoặc DataBuffer khổng lồ được phát thành một phần tử, `take(10)` không bảo vệ memory/bytes.

Reactor còn có `limitRequest(n)` để giới hạn tổng demand qua operator theo tài liệu phiên bản; ý nghĩa là giới hạn **số phần tử**, không phải số bytes hoặc thời gian.

### 4.3. `delayElements` không tương đương rate limit production

~~~java
Flux.range(1, 5)
    .delayElements(Duration.ofMillis(200));
~~~

Đây là minh họa phát các phần tử với độ trễ. Dùng timer làm demo đơn giản, nhưng `delayElements` **không** tự quản lý global quota theo tenant hoặc bandwidth thật khi có hàng nghìn clients. Nếu source là hot, dữ liệu có thể buffer/drop/overflow trước khi operator nhận; nếu downstream slow, memory/queue vẫn cần chính sách.

Muốn điều tiết bytes/giây thực tế, thiết kế token bucket/rate limiter trên **bytes đã đọc hoặc gửi**, và đảm bảo mechanism giới hạn được đường dữ liệu thật, không chỉ thêm `Thread.sleep` trên event loop.

## 5. Codec `maxInMemorySize`: phạm vi thực sự là gì?

Spring WebFlux dùng HTTP message readers và decoders để chuyển bytes thành DTO, JSON, form fields, multipart và text.

**`maxInMemorySize` không phải giới hạn tổng byte của mọi HTTP request hoặc của toàn bộ stream.** Theo Spring Framework reference:
- Với `@RequestBody byte[]` hoặc object cần aggregate, decoder có thể gom dữ liệu và limit áp vào phần được gom.
- Với NDJSON/JSON stream, reader có thể gom **từng JSON object** trước khi emit; limit thường áp vào kích thước của **một object**, không phải tổng vô hạn objects.
- Với form fields, các phần có thể được gom theo contract của reader.
- Với multipart parsed reader, limit thường áp non-file parts; đối với file parts, limit là **ngưỡng spool ra disk**, còn max disk usage và số parts có giới hạn khác.
- Với `Flux<DataBuffer>` raw body, bạn vẫn cần **hard byte count** ở ứng dụng/ingress nếu muốn giới hạn toàn request.

### 5.1. Cấu hình codecs server-side

~~~java
@Configuration
public class CodecBudgetConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(256 * 1024);
    }
}
~~~

Đây là class minh họa; phải import `Configuration`, `WebFluxConfigurer`, `ServerCodecConfigurer`. Trong Spring Boot 3.x, cũng có thể cấu hình property:

~~~properties
spring.codec.max-in-memory-size=256KB
~~~

Chọn **một chính sách được kiểm thử**; đừng thêm nhiều custom codec configurer mâu thuẫn nhau. Giá trị 256 KiB là ví dụ và đồng thời là default thường được Spring docs nêu ở WebClient codecs; kiểm tra theo Boot version/codec. Kích thước phù hợp phụ thuộc kích thước **một DTO/object** dự kiến chứ không phải tổng file upload.

### 5.2. DataBufferLimitException

Khi decoder/join cố buffer vượt ngưỡng, bạn có thể gặp:

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

Đừng “sửa” bằng cách tăng lên vô hạn hoặc `-1` mà chưa biết **vì sao cần aggregate**. Các bước hợp lý:
1. Xác định điểm gom: `byte[]`, `String`, JSON object rất lớn, `collectList`, `join`, multipart fields.
2. Nếu business chỉ cần parse theo dòng/record, dùng `Flux<Record>` với format streaming phù hợp (NDJSON, SSE).
3. Nếu cần file lớn, dùng `Flux<DataBuffer>`/FilePart streaming thay vì `byte[]`.
4. Nếu object cố hữu lớn và đã có hard business limit, tăng riêng budget vừa đủ và test.
5. Đặt ingress/body size limit và application cumulative count độc lập.

### 5.3. WebClient có codec budget riêng

~~~java
WebClient client = WebClient.builder()
        .codecs(c -> c.defaultCodecs()
                .maxInMemorySize(256 * 1024))
        .build();
~~~

Đây là snippet trong code có imports. Nếu dùng `bodyToMono(String.class)` với response nhiều MiB, nó có thể phải aggregate thành một String và bị giới hạn. Nếu remote API hỗ trợ NDJSON, bạn có thể dùng `bodyToFlux(Record.class)`, với object bound và HTTP connection limits; không tự động bảo vệ tổng số records vô hạn nếu code sau đó gọi `collectList`.

## 6. Tránh các operator vô tình gom toàn bộ stream

### 6.1. Các anti-pattern thường gặp

~~~java
Mono<List<Item>> all = itemFlux.collectList();
Mono<Map<String, Item>> map = itemFlux.collectMap(Item::id);
Mono<byte[]> bytes = webClient.get()
        .uri("/large-download")
        .retrieve()
        .bodyToMono(byte[].class);
Mono<DataBuffer> combined =
        DataBufferUtils.join(buffers);
~~~

Đây là **đoạn minh họa** với `Item`, `itemFlux`, `webClient`, `buffers` và URI giả định. Các API có use case hợp lý khi dữ liệu **nhỏ, đã giới hạn, hữu hạn**; nhưng chúng tạo vùng tích lũy:
- `collectList()` giữ các object cho đến khi source complete; source vô hạn không bao giờ complete.
- `collectMap()` giữ entries theo keys, có thể tăng theo data cardinality.
- `bodyToMono(byte[].class)` cần biểu diễn response bằng một byte array.
- `DataBufferUtils.join(buffers)` gom/compose mọi DataBuffer từ source, có thể giữ references/nội dung tăng không giới hạn.
- `sort()`, `reduce` với accumulator growing list/string cũng có thể aggregate nhiều dữ liệu.
- `cache()`, `replay()` không có giới hạn hoặc sink replay-all lưu history lâu dài.

**Ưu tiên:** xử lý từng phần tử, ghi vào sink có giới hạn, sử dụng transactional batches có kích thước kiểm soát hoặc phân trang với cursor. Với request vô hạn, không dùng `collectList` trừ khi đã `take(n)` hữu hạn và giới hạn kích thước từng phần tử.

### 6.2. Khi nào `collectList` vẫn được phép?

~~~java
return itemFlux
        .take(20)
        .collectList();
~~~

Được khi:
- Từng Item cũng có kích thước tối đa hợp lệ.
- 20 Items là một giới hạn nghiệp vụ phù hợp.
- Không có operator upstream nào đã aggregate dữ liệu lớn.
- Đã kiểm soát remote call / timeout / overall response size.
- Có thể chấp nhận materialize 20 Items trước khi trả response.

`take(20)` không thay validation max size of one item. Với pagination, hãy trả `Page/Slice` hữu hạn có `limit` ở database thay vì tải hàng triệu rows về rồi `take(20)` ở application.

### 6.3. `DataBufferUtils.join(..., maxByteCount)`

Khi bắt buộc hợp nhất **một payload nhỏ đã có hard maximum**, sử dụng overload giới hạn:

~~~java
Mono<DataBuffer> joined =
        DataBufferUtils.join(buffers, 64 * 1024);
~~~

Javadoc xác nhận khi vượt `maxByteCount`, `DataBufferLimitException` được phát và buffers đã tích lũy được giải phóng theo contract. Đây **không** phải cách stream vô hạn: nó vẫn cần gom đến khi source hoàn tất trong limit.

Nếu bạn nhận buffer kết quả, chính consumer phải release **buffer đã join** sau khi xử lý:

~~~java
return DataBufferUtils.join(buffers, 64 * 1024)
        .map(joinedBuffer -> {
            try {
                return decodeBoundedPayload(joinedBuffer);
            } finally {
                DataBufferUtils.release(joinedBuffer);
            }
        });
~~~

Đây là snippet minh họa có `decodeBoundedPayload` bên ngoài. Không tự release từng source buffers một lần nữa sau khi join đã nhận ownership theo Javadoc; làm vậy dễ double-release. Đừng suy rằng tăng `maxByteCount` giúp một stream hàng GiB “non-blocking”.

## 7. DataBuffer: giữ đúng ownership khi đếm kích thước

Bài về **DataBuffer, bộ nhớ pool và trách nhiệm giải phóng** đã phân tích đầy đủ `PooledDataBuffer`, `retain/release`, `join`, `write` và leak detection. Ở bài này, điều cần áp dụng là: **nếu chính mã của bạn tiêu thụ một `DataBuffer` chỉ để đếm bytes rồi bỏ, hãy release sau khi đọc; nếu chuyển buffer cho HTTP writer thì không release sớm**.

| Trường hợp trong pipeline giới hạn bytes | Ai chịu trách nhiệm |
| --- | --- |
| Đọc `readableByteCount()` rồi không chuyển buffer đi | Mã consumer gọi `DataBufferUtils.release(buffer)` trong `finally` |
| Chuyển `Flux<DataBuffer>` vào response writer | Writer nhận ownership; không release trước `writeWith` |
| `DataBufferUtils.join(source, maxByteCount)` | Utility quản lý các buffer nguồn; consumer release **joined result** khi đã dùng |
| Operator bỏ buffer khi filter/cancel | Dùng `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` ở vị trí được operator hỗ trợ |
| Ghi stream sang file | Theo đúng contract của overload `DataBufferUtils.write(...)` hoặc `FilePart.transferTo(...)`; cleanup file dở khi hủy |

Ví dụ khi bộ đếm **tiêu thụ** một buffer, không truyền nó đi tiếp:

~~~java
int size;
try {
    size = dataBuffer.readableByteCount();
} finally {
    DataBufferUtils.release(dataBuffer);
}
~~~

Đây là snippet trong method có biến `DataBuffer dataBuffer` và import `DataBufferUtils`. Với nhánh xuất response, đảo chiều ownership: bàn giao cho writer thay vì release ở đây. Không gọi release **hai lần**, và nhớ giới hạn số buffers đang chờ xử lý, không chỉ kích thước một buffer.

**Tránh stream giả:** `Files.readAllBytes(path)` rồi `Mono.just(byteArray)` vừa dùng filesystem API blocking vừa materialize toàn bộ file. Khi dữ liệu lớn, dùng `Resource`/`Flux<DataBuffer>` streaming với byte cap, timeout và cancellation cleanup. `doOnDiscard` chỉ bổ sung cho những operators hỗ trợ discard, không tự xử lý mọi reference bị ứng dụng giữ trong collection riêng.

## 8. Đếm bytes trên stream thay vì đọc toàn bộ: một pattern an toàn

Cần bảo vệ endpoint upload binary với hard limit **64 KiB** trong demo. Body vẫn được nhận qua `Flux<DataBuffer>`, nhưng chỉ lưu một **biến đếm `long`** và release từng buffer:

~~~java
return Mono.defer(() -> {
    AtomicLong bytes = new AtomicLong();
    return body.concatMap(buffer -> {
        try {
            int n = buffer.readableByteCount();
            if (n > MAX_BYTES - bytes.get()) {
                return Mono.<Void>error(
                    new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE,
                        "body exceeds limit"));
            }
            bytes.addAndGet(n);
            return Mono.<Void>empty();
        } finally {
            DataBufferUtils.release(buffer);
        }
    }, 1)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .then(Mono.fromSupplier(() -> new Receipt(bytes.get())));
});
~~~

Đây là **method body minh họa**; full controller ở mục 13 có imports và route hoàn chỉnh. Lý do quan trọng:

1. `Mono.defer` tạo state đếm **cho từng subscription**, không để counter mutable trong controller singleton.
2. `concatMap(..., 1)` xử lý lần lượt và cấu hình prefetch nhỏ, tránh mất thứ tự/đua updates trong code demo.
3. Kiểm tra `n > MAX_BYTES - bytes.get()` thay vì `bytes.addAndGet(n) > MAX_BYTES` cho phép tránh overflow nếu counters lớn hơn trong ứng dụng thực.
4. `finally` luôn gọi `DataBufferUtils.release(buffer)` sau khi đọc số byte, kể cả khi trả error.
5. Khi đã vượt ngưỡng, `Mono.error` dẫn tới HTTP 413 khi response chưa commit và upstream subscription bị hủy. **Không cần** đọc phần body còn lại vào RAM chỉ để chứng minh vượt hạn mức.
6. `.doOnDiscard(...)` là bảo vệ **bổ sung** cho discard-aware operators, không thay release chính.
7. Bởi vì response là Receipt nhỏ trả **sau khi body được tiêu thụ hoặc error**, không cần giữ toàn body để tạo JSON.
8. Demo không đo tốc độ gửi bytes/giây hoặc ngăn slowloris; cần giới hạn ở ingress/transport.

### 8.1. `Content-Length` có đáng tin không?

Có thể kiểm tra sớm `Content-Length` trước khi đọc, ví dụ để từ chối request có header công bố 1 GiB trong khi quota là 10 MiB. Nhưng:
- Request có thể không có Content-Length (chunked/streaming).
- Header có thể bị proxy chuyển đổi.
- Client không nên được tin để quyết định quota; phải kiểm tra **số bytes thực nhận**.
- Body đã được decode có thể khác kích thước **compressed/encoded bytes**: cần xác định limit đang áp trên wire bytes, decompressed bytes hay business payload.
- Compression/decompression bombs cần hard cap sau giải nén nếu app hỗ trợ compressed uploads.

Do đó, kiểm tra Content-Length là fast-fail optimization, **không thay** streaming cumulative bytes guard.

## 9. Kiểm soát tốc độ tiêu thụ và sự chênh lệch upstream/downstream

### 9.1. Backpressure khi upstream hợp tác

Trong Reactor pipeline:

~~~java
Flux<Item> stream = repository.findMany()
        .limitRate(16)
        .flatMap(this::sendToUpstream, 4);
~~~

Đây là snippet với `repository`, `Item`, `sendToUpstream` giả định. `limitRate(16)` điều chỉnh request batching; `flatMap(..., 4)` giới hạn concurrent inner subscriptions. Nếu downstream HTTP API chỉ cho 10 QPS, **4 concurrent** chưa bảo đảm <=10 QPS; cần rate limiter/capability ở downstream.

Một phiên bản tuần tự:

~~~java
Flux<Result> stream = items
        .concatMap(item -> process(item));
~~~

`concatMap` xử lý lần lượt inner streams, bảo toàn thứ tự; throughput có thể thấp hơn `flatMap`. Nếu processing từng item là blocking, `concatMap` không tự đưa nó khỏi event loop; cần client non-blocking hoặc bounded offload.

### 9.2. Tốc độ items khác tốc độ bytes

Nếu phải giới hạn **1 MiB/giây**, chỉ gọi `limitRate(100)` trên `Flux<DataBuffer>` là sai nếu buffer size không cố định. Bạn cần một **rate limiter xét từng số byte thực**, ví dụ token bucket đo elapsed time có concurrency-safe state và admission budget, hoặc giới hạn egress ở reverse proxy/gateway/object storage.

Một cơ chế làm chậm reactive source có thể là `delayElements`, nhưng:
- Chỉ phù hợp dữ liệu nhỏ, cold source với số item kiểm soát, không phải một hệ thống bandwidth throttling chuẩn.
- Không tự giới hạn nhiều requests cùng tenant.
- Nếu source liên tục phát nhanh hơn, phải biết dữ liệu đang nằm ở queue nào.
- **Không gọi `Thread.sleep` trên Reactor Netty event loop**; nó block cả những kết nối khác cùng event-loop thread.

### 9.3. FlatMap prefetch và buffers

`flatMap`, `publishOn`, `buffer`, `window`, `groupBy` có prefetch/queue semantics riêng. Khi một pipeline gom/chạy quá nhiều inner operations, có thể giữ nhiều objects trước khi downstream xử lý. Hãy:
1. Chọn explicit concurrency budget ở `flatMap(fn, concurrency)`.
2. Cân nhắc overload prefetch phù hợp version nếu xử lý nhiều items lớn.
3. Cân nhắc `concatMap` cho những sources cần thứ tự và bounded memory.
4. Tránh `groupBy` với cardinality không có giới hạn mà không có tiêu thụ group đầy đủ.
5. Không buffer toàn bộ streaming source vào `collectList` trong terminal.
6. Đo active memory và queue length dưới tải thật.

### 9.4. Hot sources và policies khi vượt tốc

Với `Sinks.Many` hoặc message broker, producer có thể phát khi downstream chưa sẵn sàng. Reactor có các toán tử:

~~~java
source.onBackpressureLatest();
source.onBackpressureDrop();
source.onBackpressureBuffer(128);
~~~

Đây là những snippet minh họa, mỗi biểu thức trả `Flux` mới; trong ứng dụng phải compose vào return chain. Semantics:
- **Latest**: có thể bỏ dữ liệu cũ, giữ cập nhật gần nhất khi không đủ demand.
- **Drop**: có thể bỏ events khi thiếu demand.
- **Buffer(128)**: giữ bounded số elements, rồi phát overflow error theo overload/policy.
- Buffer size là **số elements**, không phải bytes. Một object 10 MiB vẫn gây áp lực lớn.
- Chính source đó có thể có buffer riêng trước operator; giới hạn ở một operator không bảo vệ mọi boundary.

Dùng drop/latest với telemetry/dashboard nơi chỉ cần trạng thái mới nhất; **không được drop** giao dịch/đơn hàng/audit events phải giao đủ. Khi cần replay đáng tin, phải có durable event log + cursor/idempotency, không chỉ một sink giữ in-memory.

## 10. Streaming response: NDJSON, SSE và binary bytes

### 10.1. JSON array thường được xem như một document

Response `application/json` với body `[{"id":1}, ...]` có thể buộc consumer cần chờ đủ array hoặc có cơ chế streaming parser đặc biệt. Nếu muốn processing record-by-record, sử dụng media type hỗ trợ framing, ví dụ:
- `application/x-ndjson` cho **một JSON object mỗi dòng**.
- `text/event-stream` cho SSE events (`data:`, optional IDs).
- `application/octet-stream` khi streaming bytes/file nhị phân.
- Protocol/framing riêng nếu hai bên thống nhất.

Chọn format dựa client decoding và business contract, không chỉ đổi `produces` mà vẫn `collectList()` trước return.

### 10.2. NDJSON example

~~~java
@GetMapping(path = "/numbers",
        produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<StreamItem> numbers() {
    return Flux.range(1, 5)
            .delayElements(Duration.ofMillis(70))
            .map(i -> new StreamItem(i, "item-" + i));
}
~~~

Đây là method sẽ có class/imports hoàn chỉnh ở mục 13. Trả Flux để codec encode từng item, tránh gom năm items trước khi ghi HTTP. `delayElements` dùng cho quan sát demo; **không** phải business throughput guarantee.

### 10.3. SSE khi số updates không xác định

~~~java
@GetMapping(path="/events",
        produces=MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(i -> ServerSentEvent.<String>builder()
                    .event("tick")
                    .data("tick-" + i)
                    .build());
}
~~~

Đây là snippet trong WebFlux controller có imports. Browser dùng `EventSource`/named event listener. Đây là **Flux vô hạn**, do đó **đừng gọi `collectList()`** trên stream, và trong integration test phải `take(n)` rồi cancel. SSE connection còn cần heartbeat, proxy flushing, active connection cap và replay policy khi disconnect.

### 10.4. Binary download theo chunks

Một HTTP file/download response có thể trả `Flux<DataBuffer>` tạo từ `DataBufferUtils.read(Path, DataBufferFactory, bufferSize)` hoặc `Resource` phù hợp:

~~~java
Flux<DataBuffer> chunks = DataBufferUtils.read(
        filePath, new DefaultDataBufferFactory(), 8192);
~~~

Snippet có `Path filePath`. Nó không đòi bạn tự đọc `Files.readAllBytes(filePath)` trước, nhưng cần:
- Kiểm tra authorization trước khi mở file.
- Đường dẫn/size được kiểm soát và chống path traversal.
- Để HTTP writer tiêu thụ/release buffers theo contract. Không release từng buffer **trước** khi HTTP writer nhận nó.
- Xử lý source error/cancellation và cleanup nguồn.
- Không mở hàng nghìn file handles vô hạn qua một endpoint public.
- Theo dõi HTTP range/ETag/cache policy khi hỗ trợ resume download.

Nếu sử dụng Filesystem blocking APIs, hãy chọn `DataBufferUtils.read` hoặc `Resource`/HTTP resource writer theo đúng context thay vì tự đọc synchronous file trong event loop.

## 11. WebClient: không tự aggregate response lớn

Một microservice làm gateway gọi upstream `WebClient` có thể vô tình chuyển từ streaming thành aggregate.

### Anti-pattern

~~~java
Mono<byte[]> all = webClient.get()
        .uri("/api/huge-file")
        .retrieve()
        .bodyToMono(byte[].class);
~~~

Dữ liệu phải biểu diễn thành một byte[] trước khi consumer nhận. Nếu muốn relay stream:

~~~java
Flux<DataBuffer> body = webClient.get()
        .uri("/api/huge-file")
        .retrieve()
        .bodyToFlux(DataBuffer.class);
~~~

Đây là snippet: `body` trả raw `DataBuffer` từ WebClient; nếu trực tiếp nối vào HTTP server response, **phải hiểu ownership** và đảm bảo downstream writer nhận/release đúng. Nếu subscribe để tự đọc hoặc bỏ stream, cần cleanup buffers. Không tự `.subscribe()` rồi return 200 trước khi upstream complete.

Với JSON nhỏ đã giới hạn, `bodyToMono(Dto.class)` hoàn toàn hợp lý; mục tiêu là **biết phần nào cần aggregate**.

### Các hạn mức outbound cần đặt

- WebClient codec `maxInMemorySize` cho buffered decoding.
- Remote response body total bytes limit nếu consumer không cho phép file lớn.
- HTTP client connection pool max connections, pending acquire timeout.
- Connect/response/read timeouts và tổng business deadline.
- Rate limit và concurrency budget per upstream/tenant.
- Retry bounded + backoff khi idempotent, không retry vô hạn.
- Max redirects/trusted hosts để tránh SSRF trong proxy download feature.
- Metrics về buffered bytes và downstream slow consumers.

Không coi `timeout(Duration.ofSeconds(5))` là giới hạn bytes: một upstream có thể gửi hàng GiB rất nhanh trước 5 s. Ngược lại, chỉ có size limit mà không có timeouts cho phép client cực chậm giữ connection lâu.

## 12. Một ví dụ số học minh họa budget

Giả sử hệ thống có:
- 4 instances.
- Mỗi instance nhận tối đa 100 streaming requests đồng thời.
- Mỗi request cho phép 64 KiB application buffer theo pipeline.
- HTTP writer còn có network buffers và event-loop queues.
- Downstream storage pool tối đa 10 concurrent writes/instance.

Một budget phần application buffer lý tưởng:

~~~text
100 requests × 64 KiB = 6,400 KiB ≈ 6.25 MiB / instance.
4 instances × 6.25 MiB = 25 MiB (chỉ một loại buffer).
~~~

**Đây là phép tính ví dụ**, không phải số liệu đo; tổng RSS/heap/direct memory thực có thể lớn hơn đáng kể vì decoder, TCP, TLS, gói request đang bay, object headers, temporary files và GC. Số threads ít không chứng minh low memory nếu buffer per request và total connections vẫn tăng.

Nếu queue dùng `onBackpressureBuffer(128)` với mỗi item là 1 MiB, bản thân queue đó có thể giữ tới khoảng **128 MiB cho một subscriber**, chưa kể overhead. Cần cap **byte size** ngoài element count khi item size biến thiên.

### Đo ở đâu?

| Metric | Nên theo dõi |
| --- | --- |
| JVM heap/live objects | Bộ nhớ được giữ và tần suất GC |
| Direct/native buffer allocation | Leak Netty pooled buffers, off-heap pressure |
| Active connections/in-flight streams | Số streams ở server/client |
| Request/response bytes | P50/p95/p99 size và user/tenant quota |
| Processing latency & p99 | Kể cả timeout/error |
| Rate-limited/rejected requests | 413/429/503 và nguyên nhân |
| Reactor scheduler queue | BoundedElastic blocking work saturation |
| WebClient connection pending | Pool saturation, upstream slow |
| DB/Redis pool/queries | Thực sự xử lý dữ liệu tới đâu |
| Downstream consumer lag | Có backpressure, buffers hay dropped events |
| Temp disk/object storage staging | Upload có spool hoặc chưa cleanup |

Một biểu đồ “RPS tăng” không đủ nếu p99 latency, 413, 503, direct memory hoặc GC pauses cũng tăng.

## 13. Ví dụ thực hành Spring Boot 3.x / Java 17

Dự án minh họa gồm:
- `POST /api/stream/measure`: nhận **`application/octet-stream`**, đếm bytes qua `Flux<DataBuffer>` rồi release từng buffer, giới hạn **64 KiB/request**, trả JSON `{"bytes":N}`.
- `GET /api/stream/numbers`: trả **NDJSON streaming** gồm 5 record, không gom thành một List trong controller.
- `GET /api/stream/ticks`: trả **SSE** từ `Flux<ServerSentEvent<String>>`, không hoàn tất cho tới khi cancel.
- `WebTestClient`: kiểm tra 4 bytes được chấp nhận, 65,537 bytes trả 413, NDJSON nhận từng record và SSE được cancel sau `take(2)`.
- `WebFluxConfigurer` áp decoder budget 256 KiB. **Giới hạn upload 64 KiB là logic khác**, không lệ thuộc codec `maxInMemorySize`.

Demo **không** bao gồm auth, admission control, gateway max-body config, slowloris defense, virus scanning hay multi-tenant quotas; bổ sung các lớp đó trước khi triển khai public.

### 13.1. Project dependencies

Tạo Spring Initializr Maven project với Java 17+, Spring Boot 3.x, `Spring Reactive Web` và `Spring Boot Starter Test`. Đảm bảo có:

~~~xml
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
~~~

Đây là **fragment** đặt trong `pom.xml` do Initializr sinh sẵn, không phải toàn bộ file Maven độc lập. Nếu vừa thêm `spring-boot-starter-web` vừa thêm WebFlux, Boot 3.x thường ưu tiên MVC application type; chỉ dùng WebFlux starter cho bài demo.

Cấu trúc:

~~~text
src/main/java/com/example/demo/
    DemoApplication.java
    StreamCodecConfig.java
    StreamController.java
src/test/java/com/example/demo/
    StreamControllerTest.java
~~~

### 13.2. DemoApplication.java

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 13.3. StreamCodecConfig.java

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class StreamCodecConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(256 * 1024);
    }
}
~~~

Nhắc lại: đoạn codec này giới hạn phần **decoder buffering**, không bảo vệ tổng upload size. Nếu muốn giới hạn 64 KiB total body, route sẽ **đếm bytes thật**.

### 13.4. StreamController.java

~~~java
package com.example.demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/stream")
public class StreamController {

    private static final long MAX_BYTES = 64L * 1024;

    @PostMapping(path = "/measure",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public Mono<ByteReceipt> measure(
            @RequestBody Flux<DataBuffer> body) {

        return Mono.defer(() -> {
            AtomicLong bytes = new AtomicLong();

            return body.concatMap(buffer -> {
                        try {
                            int n = buffer.readableByteCount();

                            // Check remaining budget before addition:
                            if (n > MAX_BYTES - bytes.get()) {
                                return Mono.<Void>error(
                                    new ResponseStatusException(
                                        HttpStatus.PAYLOAD_TOO_LARGE,
                                        "raw body exceeds 64 KiB"));
                            }

                            bytes.addAndGet(n);
                            return Mono.<Void>empty();
                        } finally {
                            DataBufferUtils.release(buffer);
                        }
                    }, 1)
                    .doOnDiscard(
                        DataBuffer.class, DataBufferUtils::release)
                    .then(Mono.fromSupplier(() ->
                            new ByteReceipt(bytes.get())));
        });
    }

    @GetMapping(path = "/numbers",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<StreamItem> numbers() {
        return Flux.range(1, 5)
                .delayElements(Duration.ofMillis(70))
                .map(i -> new StreamItem(i, "item-" + i));
    }

    @GetMapping(path = "/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> ticks() {
        return Flux.interval(Duration.ofMillis(100))
                .map(n -> ServerSentEvent.<String>builder()
                        .event("tick")
                        .data("tick-" + n)
                        .build());
    }

    public record ByteReceipt(long bytes) {}

    public record StreamItem(int sequence, String label) {}
}
~~~

**Phân tích tính an toàn và giới hạn:**
1. Controller là singleton bean nhưng state `AtomicLong` được tạo trong `Mono.defer` **theo từng subscription**, không dùng field shared.
2. `concatMap(..., 1)` xử lý buffers theo thứ tự với prefetch nhỏ; mỗi buffer được release trong finally.
3. Nếu vượt MAX_BYTES, Mono phát `ResponseStatusException(413)` **trước khi trả body Receipt**, không cần giữ toàn body trong RAM. Upstream có thể được cancel thay vì đọc hết request.
4. `MAX_BYTES - bytes.get()` tránh cộng vượt ngưỡng; `long` giúp đếm tổng bytes với headroom lớn hơn `int`.
5. `doOnDiscard` bổ sung cho các operators có cơ chế discard; không chứng minh mọi buffer đã được framework cấp phát nhưng chưa deliver đều sẽ được dọn trong mọi network error case. Cần integration/stress tests dưới Netty pooled buffer leak detector khi dùng direct buffers.
6. `numbers` trả `Flux<StreamItem>` NDJSON 5 items hữu hạn; codec có thể encode/flush từng item. Không gọi `collectList` trong controller.
7. `ticks` phát SSE vô hạn; phải hủy subscription khi client rời. Một ứng dụng thật cần connection cap, heartbeat/proxy config và source lifecycle cleanup.
8. `delayElements`/timer ở đây **chỉ phục vụ quan sát streaming**; không phải hệ thống limit toàn bộ bandwidth hay QPS.
9. Demo không tự tạo file hay publish upload, nên bài toán dọn staging file không xuất hiện. Khi chuyển sang upload file thật, cần staging/atomic publish/cancel cleanup.
10. Cấu hình codec 256 KiB không làm mất hiệu lực giới hạn total bytes 64 KiB: hai chính sách ở hai tầng khác nhau.

### 13.5. StreamControllerTest.java — HTTP integration tests

~~~java
package com.example.demo;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamControllerTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void acceptsSmallBodyAndCountsExactBytes() {
        client.post()
                .uri("/api/stream/measure")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .bodyValue(new byte[] {1, 2, 3, 4})
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.bytes").isEqualTo(4);
    }

    @Test
    void rejectsActualBodyLargerThan64KiB() {
        client.post()
                .uri("/api/stream/measure")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .bodyValue(new byte[65_537])
                .exchange()
                .expectStatus().isEqualTo(413);
    }

    @Test
    void ndjsonCanBeReadIncrementally() {
        List<StreamController.StreamItem> data =
                client.get()
                        .uri("/api/stream/numbers")
                        .accept(MediaType.APPLICATION_NDJSON)
                        .exchange()
                        .expectStatus().isOk()
                        .expectHeader().contentTypeCompatibleWith(
                            MediaType.APPLICATION_NDJSON)
                        .returnResult(StreamController.StreamItem.class)
                        .getResponseBody()
                        .take(3)
                        .collectList()
                        .block(Duration.ofSeconds(5));

        assertNotNull(data);
        assertEquals(3, data.size());
        assertEquals(1, data.get(0).sequence());
        assertEquals("item-3", data.get(2).label());
    }

    @Test
    void infiniteSseIsBoundedInTestWithTakeTwo() {
        List<ServerSentEvent<String>> data =
                client.get()
                        .uri("/api/stream/ticks")
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .exchange()
                        .expectStatus().isOk()
                        .returnResult(
                            new ParameterizedTypeReference<
                                    ServerSentEvent<String>>() {})
                        .getResponseBody()
                        .take(2)
                        .collectList()
                        .block(Duration.ofSeconds(5));

        assertNotNull(data);
        assertEquals(2, data.size());
        assertEquals("tick", data.get(0).event());
        assertEquals("tick-0", data.get(0).data());
        assertEquals("tick-1", data.get(1).data());
    }
}
~~~

**Điểm cần hiểu trong test:**
- `@SpringBootTest(RANDOM_PORT)` và `WebTestClient.bindToServer` dùng embedded HTTP server thực; không chỉ gọi method Java.
- Test size 65,537 bytes vượt 65,536 bytes. Nếu gateway hay client connector xử lý error sớm làm socket close, đôi khi network layer kết thúc trước khi có body lỗi; cần cấu hình và integration testing tương ứng khi production route rất lớn. Với demo và request nhỏ vừa quá hạn, dự kiến HTTP 413.
- `take(3)` đặt **trong test subscriber** để không gom dữ liệu vô hạn; server `numbers` vốn chỉ có 5 items. Test này không chứng minh production throughput hoặc streaming flush qua nginx.
- `take(2)` khiến subscriber hủy SSE sau 2 events, tránh `collectList()` chờ một Flux vô hạn.
- `.block(Duration.ofSeconds(5))` nằm **chỉ ở JUnit test thread**; không dùng `.block()` bên trong Spring WebFlux handler/event loop.
- Nếu muốn chứng minh thực sự stream chứ không buffer toàn response, nên thêm test quan sát **thời điểm nhận từng element** (ví dụ StepVerifier trong client-side test), vì `collectList()` hữu hạn ở test cuối cùng vẫn giữ danh sách nhỏ để assert.

Chạy:
~~~bash
./mvnw test
~~~

Windows:
~~~powershell
.\mvnw.cmd test
~~~

Nếu không có wrapper, chạy `mvn test` khi Maven đã cài. Không suy diễn test demo này đã đo memory dưới 100.000 concurrent uploads; cần stress test riêng.

## 14. Dùng curl để nhìn streaming và size limit

Chạy server:

~~~bash
./mvnw spring-boot:run
~~~

### 14.1. Request binary nhỏ

~~~bash
printf 'abcd' > input.bin
curl -i --data-binary @input.bin   -H "Content-Type: application/octet-stream"   http://localhost:8080/api/stream/measure
~~~

Kết quả dự kiến:

~~~json
{"bytes":4}
~~~

Đếm **bytes**, không phải số ký tự Unicode. File UTF-8 có dấu tiếng Việt thường nhiều bytes hơn số ký tự được nhìn thấy.

### 14.2. NDJSON streaming

~~~bash
curl -i -N   -H "Accept: application/x-ndjson"   http://localhost:8080/api/stream/numbers
~~~

Response body về mặt logic là các dòng:

~~~json
{"sequence":1,"label":"item-1"}
{"sequence":2,"label":"item-2"}
{"sequence":3,"label":"item-3"}
{"sequence":4,"label":"item-4"}
{"sequence":5,"label":"item-5"}
~~~

Trong code fence `json`, nội dung trên là **NDJSON gồm nhiều JSON objects độc lập**, không phải một JSON document hợp lệ duy nhất. `curl -N` giúp tắt buffering stdout, nhưng reverse proxy vẫn có thể buffer response nếu cấu hình sai.

### 14.3. SSE vô hạn

~~~bash
curl -N -H "Accept: text/event-stream"   http://localhost:8080/api/stream/ticks
~~~

Quan sát `event:tick`, `data:tick-0`, `data:tick-1`, ... theo wire format của codec. Nhấn `Ctrl+C` để ngắt kết nối. Không để terminal/automated test giữ stream vô hạn khi không cần.

### 14.4. Giới hạn upload

Tạo file >64 KiB rồi POST để quan sát 413:

~~~bash
python -c "open('big.bin','wb').write(b'x' * 65537)"
curl -i --data-binary @big.bin   -H "Content-Type: application/octet-stream"   http://localhost:8080/api/stream/measure
~~~

Đoạn lệnh Python chỉ tạo **file test** có 65,537 bytes; không liên quan runtime Java. Response mong đợi là HTTP 413. Một số connectors đóng request body sớm khi server trả 413; thông điệp curl về broken pipe hoặc connection reset trong tình huống này cần phân biệt với bug business logic.

Các lệnh nhiều dòng dùng `\` cho Linux/macOS/Git Bash. Windows PowerShell dùng `curl.exe` một dòng hoặc line continuation `backtick` theo PowerShell.

## 15. Streaming file upload lớn: khác demo đếm bytes

Nếu lưu file thật, thông thường:
1. Xác thực và áp quota trước khi mở storage.
2. Nhận FilePart hoặc `Flux<DataBuffer>` và đọc/ghi theo streaming.
3. Kiểm soát per-file bytes tổng, tốc độ upload tối thiểu/timeout và số uploads đồng thời.
4. Giữ staging file/object có storage key do server tạo, không dùng raw client filename.
5. Ghi theo một pass; không `collectList` rồi `Files.write`.
6. Hash/scan MIME/virus theo policy, **không dựa vào Content-Type/extension do client gửi**.
7. Nếu quota/virus/IO/error/cancellation xảy ra, dọn staging và chỉ publish khi complete.
8. Xử lý backpressure giữa inbound HTTP và disk/object-storage writer; disk write có thể blocking nếu dùng API/SDK synchronous.
9. Đảm bảo max total bytes ở ingress, app và storage; codec maxInMemorySize **không đủ**.
10. Có idempotency/retry/resumable strategy nếu file lớn và mạng không ổn định.

### `DataBufferUtils.write` cần đọc đúng overload

`DataBufferUtils.write(source, Path, OpenOption...)` trả `Mono<Void>` trong API Spring Framework 6.x; các overload nhận `OutputStream`/`WritableByteChannel` có thể trả `Flux<DataBuffer>` và **không tự release** buffers. Không copy-paste `doOnNext(DataBufferUtils.releaseConsumer())` tùy tiện vào overload có ownership khác.

Nếu dùng `FilePart.transferTo(Path)`, không đọc `file.content()` một lượt rồi transfer lại với giả định nó luôn repeatable. Chọn contract và tests cho một-pass streaming. Việc ghi thành công không đồng nghĩa scan thành công hoặc dữ liệu đã được durable replicated.

## 16. Proxy, networking và “server đang stream nhưng client không thấy”

Một pipeline WebFlux có thể emit từng item ngay, nhưng nginx/gateway/compression layer **buffer toàn bộ response**. Với NDJSON/SSE route:
- Khai báo `Content-Type` phù hợp (`application/x-ndjson`, `text/event-stream`, `application/octet-stream`).
- Kiểm tra proxy response buffering, HTTP/2 stream settings, compression buffering và flush.
- Đặt idle timeout phù hợp; với SSE có thể phát heartbeat comment-only.
- Dùng `curl -N`/browser Network Timing/packet captures để quan sát item arrival, không chỉ bytes cuối.
- Không cho response cache sai user/tenant.
- Đặt max header/body/request limits ở ingress.
- Đo slow-reader conditions; tốc độ client tải xuống cũng là bottleneck.

SSE có thể dùng comment lines `: keep-alive` để tránh im lặng quá lâu. Đây không phải giới hạn kích thước dữ liệu, và heartbeat tạo overhead khi có nhiều clients.

## 17. Timeout, cancellation và cleanup

### 17.1. Hai loại timeout cần phân biệt

- **Total deadline**: request/operation không vượt thời gian kinh doanh, ví dụ 30 giây.
- **Idle/read timeout**: client/upstream không được im lặng quá lâu, kể cả tổng chưa hết 30 giây.

Một live SSE stream có chủ đích kéo dài hàng giờ có thể **không phù hợp với total response timeout 30 giây**, nhưng vẫn cần heartbeat/idle detection và connection cap. Ngược lại, một upload phải hoàn tất trong 60 giây có thể cần absolute deadline bên cạnh minimum data rate.

### 17.2. Cancellation không phải phép màu

Khi client disconnect, Reactor có thể phát cancellation ngược upstream; các operators và I/O implementations hợp tác sẽ dừng. Tuy nhiên:
- Công việc blocking đang chạy trong worker có thể không dừng ngay.
- Một DB query/client SDK không hỗ trợ cancel có thể tiếp tục giữ connection.
- Một file đã ghi nửa chừng vẫn cần cleanup staging.
- `doFinally` gọi khi complete/error/cancel theo Reactor lifecycle, nhưng cleanup bất đồng bộ cần thiết kế riêng; không gọi `subscribe()` vô chủ trong hook.
- Pooled buffers bị discard/cancel cần được release ở đúng ownership boundaries.

### 17.3. Quá tải nên được xử lý rõ ràng

Khi queue/connections/quota đầy, có thể trả:
- **413 Payload Too Large** nếu kích thước vượt policy.
- **429 Too Many Requests** nếu user/tenant quá tốc hoặc quota.
- **503 Service Unavailable** nếu service/storage quá tải tạm thời.
- **408/504** theo failure mode HTTP client/proxy timeout, sau khi kiểm tra tầng phát lỗi.

Không giữ request trong queue vô hạn chỉ để “không làm mất việc”. Giới hạn vào (admission control) và retry có backoff thường an toàn hơn khi nguồn lực đã bão hòa.

## 18. Kiểm thử và hiệu năng đúng cách

### 18.1. Các case chức năng

| Case | Điều cần xác nhận |
| --- | --- |
| Raw body 0 bytes | Receipt 0 hoặc contract lỗi rõ |
| Raw body đúng 64 KiB | Được chấp nhận theo ngưỡng |
| Raw body 64 KiB + 1 | 413 và không ghi toàn bộ vào RAM |
| Nhiều chunks kích thước khác nhau | Tổng bytes đúng, không overflow |
| Client ngắt giữa upload | Server cancel và cleanup đúng |
| NDJSON nhiều items | Nhận từng object, không cần toàn array |
| JSON object vượt codec budget | DataBufferLimitException hoặc lỗi theo contract |
| SSE vô hạn | `take(n)`/cancel khi test, không collectList toàn stream |
| Hot producer nhanh, client chậm | Buffer/drop/overflow đúng policy |
| Proxy buffering enabled | Xác nhận hiện tượng chậm flush |
| Concurrency 1/100/1000 | Heap/direct memory/DB pools trong budgets |
| Downstream lỗi giữa stream | Cleanup và response error semantics |
| Retry nhiều lần | Không nhân tải hoặc tạo event/record trùng |
| Quota theo tenant | Không vượt limit ngay cả với nhiều concurrent requests |

### 18.2. Benchmark phải đo đúng memory

Không lấy một response 1 KiB rồi kết luận service có thể truyền 100 GiB. Nên:
1. So sánh `bodyToMono(byte[].class)` với raw chunk streaming ở **cùng throughput và payload profile**.
2. Chạy tải vừa đủ để đo RSS/direct memory/heap allocation, GC và Netty pooled buffer usage.
3. Ghi số requests thành công/timeout/413/429/503, p95/p99 latency.
4. Thử upstream fast, downstream slow, client disconnect và proxy buffering.
5. Đo queue của boundedElastic, `flatMap` concurrency, WebClient pool acquires và DB lock contention.
6. Kiểm thử overload theo thiết kế, không tổ chức tấn công tải lên hệ thống đang phục vụ production.
7. Kiểm tra data correctness (đủ bytes, checksum, không duplicate/missing chunks), vì throughput cao nhưng mất dữ liệu không phải thành công.

### 18.3. BlockHound, Java Flight Recorder và observability

Trong test phù hợp, BlockHound có thể giúp phát hiện một số blocking calls trên Reactor non-blocking threads, nhưng không chứng minh toàn pipeline không có nguồn lực bị đệm vô hạn. Java Flight Recorder/threaddumps/Netty leak detector/direct-memory metrics giúp tìm queue, allocations và chặn event loop. Kiểm tra tương thích của công cụ với Java/Reactor versions trước khi kích hoạt.

## 19. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `Flux` tự tiết kiệm memory | Một operator sau nó vẫn có thể aggregate | Audit `collect*`, `join`, caches, buffers |
| Dùng `collectList` trên stream vô hạn | Không bao giờ complete, memory tăng | `take(n)`, streaming format, bounded storage |
| Đặt `maxInMemorySize` để cap tổng file upload | File/stream vẫn có thể lớn hơn limit | Total byte counter + ingress cap |
| Tăng `maxInMemorySize=-1` khi lỗi | OOM/heap spikes | Thiết kế streaming hoặc bounded DTO |
| Chỉ dùng `limitRate(20)` làm 20 items/sec | Demand batching không kiểm soát clock | Rate limiter theo thời gian |
| Chỉ dùng `take(100)` để cap bytes | Một item có thể khổng lồ | Đếm byte kích thước thực |
| `onBackpressureBuffer` không giới hạn | Slow consumers giữ queue vô hạn | Bounded buffer, overflow policy |
| Drop events giao dịch bằng latest/drop | Mất dữ liệu không phát hiện | Durable log + retry/checkpoint |
| Dùng `flatMap` concurrency cao vô tội vạ | Pool/DB/upstream saturation | Explicit concurrency budgets |
| Quên release `DataBuffer` trực tiếp consume | Netty direct memory leak | try/finally, ownership, discard tests |
| Release trước khi HTTP writer dùng buffer | Use-after-release/corrupt bytes | Writer sở hữu buffer tới khi hoàn thành |
| `DataBufferUtils.join` toàn file lớn | Gom toàn body | Stream/write hoặc join với cap nhỏ |
| `bodyToMono(byte[].class)` ở gateway | Buffer response lớn | `bodyToFlux(DataBuffer.class)` + streaming relay |
| `Thread.sleep` để giảm tốc upload | Block event loop | Non-blocking limiter/transport shaping |
| Chỉ kiểm tra Content-Length | Chunked/body thực khác header | Đếm bytes thực + ingress cap |
| Không có timeout | Slowloris/hanging streams | Deadline + read/idle timeout |
| Codec budget có nhưng số requests vô hạn | Tổng memory tăng theo concurrency | Admission/connection limits |
| Server stream nhưng client chờ đến cuối | Proxy/HTTP client buffers | Flush, correct content type, curl -N |
| Test `collectList` lên SSE vô hạn | Test treo | `take(n)` và timeout |
| Dùng MVC blocking SDK trong WebFlux event loop | Ngừng xử lý nhiều connections | Reactive driver hoặc bounded offload |
| Không cleanup file dở khi cancel | Rác disk và quota sai | Staging + cleanup, integration test |
| Retry vô hạn khi 503 | Thêm tải và queue | Bounded backoff/jitter |
| Chỉ đo RPS, bỏ p99/errors | Đánh giá sai tải khỏe | Successful RPS + SLO + resource metrics |

## 20. Câu hỏi ôn tập

**1. `limitRate(10)` có nghĩa giới hạn 10 items mỗi giây?**  
Không. Nó chia demand lên upstream theo batches, không tự áp đồng hồ hay bandwidth policy.

**2. `maxInMemorySize=256 KiB` có tự chặn mọi request trên 256 KiB?**  
Không. Nó liên quan việc reader/decoder buffer dữ liệu. NDJSON có thể chứa nhiều objects nhỏ trong một stream dài, còn raw `Flux<DataBuffer>` cần cumulative byte limit riêng.

**3. Vì sao `collectList()` trên SSE `Flux.interval` là lỗi?**  
Flux không có terminal complete trong hoạt động bình thường, nên List không thể được emit và có thể tích lũy vô hạn.

**4. Nếu chỉ cho 10 DataBuffers mà mỗi buffer 8 MiB, bộ nhớ có an toàn không?**  
Không thể suy ra: có thể giữ đến khoảng 80 MiB buffers chưa tính overhead. Cần tính byte sizes.

**5. `DataBufferUtils.join(buffers, 65536)` làm gì?**  
Nó gom/compose buffers trong budget 65,536 bytes, phát lỗi khi vượt budget. Đây vẫn là aggregation hữu hạn, không phải raw streaming.

**6. Vì sao release buffer trong `finally`?**  
Nếu code throw khi đang kiểm tra size, buffer cần được release. `finally` chạy cả success lẫn exception.

**7. Trong demo, tại sao dùng `Mono.defer`?**  
Mỗi subscription nhận một counter riêng; không để state mutable shared trong controller singleton.

**8. `Content-Length` có đủ để enforce quota không?**  
Không. Chunked requests có thể không có header, và header không phải nguồn tin cậy duy nhất. Đếm bytes đã nhận thật.

**9. Nếu WebFlux dùng WebClient mà response gọi `bodyToMono(byte[].class)`, có còn streaming không?**  
Không theo nghĩa consumer nhận từng chunks; nó phải materialize một byte array trước khi emit. Có thể dùng raw DataBuffer Flux hoặc NDJSON Flux khi phù hợp.

**10. Vì sao 413 và 429 khác nhau?**  
413 là payload vượt limit; 429 là rate/quota exceeded. Cần policy định nghĩa rõ và kiểm thử.

**11. Làm thế nào kiểm tra SSE vô hạn bằng WebTestClient?**  
Dùng `take(n)`/timeout ở test subscription, không chờ `collectList` của toàn infinite stream.

**12. Giới hạn concurrency và limit bytes có thay thế nhau không?**  
Không. Một request có thể rất lớn; ngược lại hàng nghìn requests nhỏ có thể cộng dồn thành quá tải.

## 21. Checklist triển khai

1. Vẽ toàn bộ chuỗi ingest/process/egress và xác định mọi nơi aggregate/buffer.
2. Đặt ingress max-body/timeout/rate controls và concurrent connections budget.
3. Cấu hình WebFlux `maxInMemorySize` cho decoder, hiểu giới hạn per object/part, không nhầm với total request size.
4. Dùng raw `Flux<DataBuffer>` hoặc `FilePart` phù hợp để stream body lớn; đếm cumulative bytes và stop khi vượt.
5. Release mọi DataBuffer mà ứng dụng trực tiếp consume; bảo vệ error/cancel/discard, không double-release buffer HTTP writer đang sở hữu.
6. Tránh `collectList`, `collectMap`, unbounded `join`, `cache`, `replay` trên stream không giới hạn; dùng bounded batches/records.
7. Với NDJSON/SSE, trả Flux trực tiếp, test streaming/cancellation/slow readers thay vì chờ toàn bộ data.
8. Dùng `limitRate` cho demand batching, explicit concurrency cho `flatMap`, rate limiter cho requests/bytes per second; không coi chúng là một.
9. Chọn overflow/drop/backpressure policy theo nghiệp vụ: có được mất events hay không?
10. Đặt WebClient codec/connection pool/timeout/response-byte policies và downstream storage quotas.
11. Nếu upload file, staging/scan/atomic publish/cleanup; không dùng raw filename/path hoặc Content-Length làm tin cậy tuyệt đối.
12. Kiểm tra reverse proxy buffering/flush, ingress limits, load balancer idle timeout, HTTP/2 behavior.
13. Test 0 bytes, exactly limit, limit+1, chunked uploads, client disconnect, concurrency, large objects, streaming correctness.
14. Quan sát heap + direct memory + temp disk + GC + queues + connection pools + p99/errors; thay đổi giới hạn dựa trên SLO thực tế.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — WebFlux Reactive Core, Limits và Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — Configuring HTTP Codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Framework 6.2 — WebClient Configuration: maxInMemorySize](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html)
- [Spring Framework 6.2 — DataBufferUtils API, join và release](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework 6.2 — WebFlux Return Types](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Project Reactor — Backpressure, limitRate and Prefetch](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html)
- [Project Reactor — Reactor Sinks and Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)
- [Project Reactor — Schedulers and blocking offloading](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Reactive Streams specification](https://www.reactive-streams.org/)
