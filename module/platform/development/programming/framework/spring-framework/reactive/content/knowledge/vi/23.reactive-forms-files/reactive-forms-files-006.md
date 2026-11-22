# Tiêu thụ hoặc giải phóng đầy đủ phần nội dung request bị bỏ qua trong Spring WebFlux

> **Module:** Spring Framework – reactive · **Chủ đề cha:** Form và tập tin. Bài học giải thích vòng đời request body khi filter, controller hoặc multipart handler quyết định bỏ qua một phần hay toàn bộ dữ liệu. Trọng tâm là phân biệt consume, relay và release; xử lý đúng `DataBuffer`, `Part`, `PartEvent`; và kiểm thử để phát hiện nội dung bị bỏ quên.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao request body trong WebFlux là reactive stream thường chỉ đọc được một lần.
2. Phân biệt consume, relay và release khi ứng dụng không cần nội dung.
3. Tiêu thụ toàn bộ `Flux<DataBuffer>` mà không gom toàn bộ body vào memory.
4. Giải phóng pooled `DataBuffer` đúng lúc và xử lý buffer bị loại bởi `filter`, `skip`, lỗi hoặc cancellation.
5. Biết khi nào dùng `DataBufferUtils.release`, `retain`, `join` và `doOnDiscard`.
6. Xử lý form URL-encoded, multipart map và multipart streaming bằng `PartEvent`.
7. Drain body trong `WebFilter` khi short-circuit trước controller.
8. Viết HTTP integration tests cho raw body, multipart và request tiếp theo sau khi body bị từ chối.

**Quy tắc:** khi ứng dụng nhận quyền sở hữu một `DataBuffer` hoặc `PartEvent` chứa buffer, ứng dụng phải tiêu thụ, chuyển giao cho consumer khác hoặc giải phóng nội dung. Chỉ gọi `.then()` để bỏ qua các phần tử không tự release buffer.

## 2. Vì sao request body phải được xử lý đến cùng?

Trong WebFlux, request body được biểu diễn bằng `Publisher`/Reactor `Flux` hoặc `Mono`. Ở tầng thấp, body thường là chuỗi `DataBuffer` được server connector phát theo nhu cầu (backpressure). Một `DataBuffer` có thể bọc bộ nhớ pooled, đặc biệt khi chạy trên Reactor Netty.

~~~text
Client gửi bytes
      |
      v
HTTP server / connector
      |
      v
Flux<DataBuffer>
      |
      +---- HttpMessageReader / codec
      |          |
      |          v
      |       DTO / String / PartEvent
      |
      +---- Controller / functional handler
      |
      +---- Filter có thể short-circuit
                 |
                 v
       Consume / Relay / Release
~~~

Một endpoint có thể trả 401, 413 hoặc 415 trước khi đọc hết body. Multipart handler có thể chỉ cần field `name` nhưng bỏ qua file part. Một stream có thể dừng ở phần tử đầu tiên. Những nhánh này đều phải có quy tắc rõ ràng cho nội dung còn lại.

Nếu buffer bị bỏ quên, bộ nhớ pooled có thể không được trả lại pool, dẫn đến memory leak hoặc `OutOfDirectMemoryError` khi tải tăng. Nếu request stream không được hoàn tất, server connector có thể phải tiếp tục drain hoặc đóng kết nối; hành vi keep-alive và tài nguyên socket phụ thuộc connector/protocol. Đừng giả định mọi connector đều tự xử lý phần body mà ứng dụng bỏ qua.

### 2.1. Ba cách xử lý hợp lệ

| Cách | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Consume** | Đọc hết nội dung và dùng hoặc bỏ giá trị sau khi đọc | Decode JSON thành DTO; đọc hết byte để tính kích thước |
| **Relay** | Chuyển stream cho writer/consumer khác và chờ consumer hoàn tất | Chuyển `PartEvent` sang WebClient hoặc ghi file |
| **Release** | Không cần bytes; giải phóng từng buffer khi nhận | Drain body rồi trả 413; bỏ qua file part không được chọn |

Ba cách có thể xuất hiện trong cùng pipeline. Ví dụ, ứng dụng đọc metadata multipart, relay file được chấp nhận, rồi release mọi part còn lại. Với mọi part, nội dung phải có đúng một chủ sở hữu tại từng thời điểm.

### 2.2. `.then()` không đồng nghĩa release

Ví dụ sau chỉ đợi Publisher hoàn tất và bỏ các giá trị:

~~~java
Mono<Void> wrong = request.getBody().then();
~~~

`then()` không biết phải giải phóng `DataBuffer` mà ứng dụng đang sở hữu. Với raw `Flux<DataBuffer>`, hãy release trước khi bỏ giá trị:

~~~java
Mono<Void> drain = request.getBody()
    .doOnNext(DataBufferUtils::release)
    .then();
~~~

`then()` biểu diễn “đợi body hoàn tất”; `doOnNext` mới là thao tác giải phóng từng buffer.

## 3. DataBuffer và quyền sở hữu bộ nhớ

`DataBuffer` là abstraction của Spring trên các kiểu byte buffer khác nhau. Một số implementation là pooled và có reference count. Khi reference count về 0, bộ nhớ có thể được trả lại pool; nếu giữ reference quá lâu, pool không thể tái sử dụng vùng nhớ đó.

| Trường hợp | Ứng dụng làm gì? |
| --- | --- |
| Nhận raw `DataBuffer`, đọc xong và không chuyển tiếp | Gọi `DataBufferUtils.release(buffer)` |
| Bỏ buffer trong `filter` hoặc operator hỗ trợ discard | Đăng ký `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` |
| Gom nhiều buffer bằng `DataBufferUtils.join` | Release buffer kết quả sau khi dùng; join tự dọn buffer đã gom khi error/cancel |
| Chuyển buffer sang HTTP writer khác | Không release trước khi writer đọc xong; ownership đã được chuyển |
| Cần hai consumer cùng đọc một pooled buffer | Dùng `retain` có chủ đích và release mỗi reference đúng một lần |
| Đã decode thành `String`, DTO hoặc `byte[]` qua codec chuẩn | Không tự release object đã decode |

Ưu tiên `DataBufferUtils.release` thay vì cast sang `PooledDataBuffer` hoặc gọi API Netty trực tiếp. Utility này xử lý pooled buffer phù hợp và không buộc ứng dụng phụ thuộc connector cụ thể.

### 3.1. Release buffer sau khi đọc

~~~java
int byteCount = buffer.readableByteCount();
try {
    byte[] copy = new byte[byteCount];
    buffer.read(copy);
    // Xử lý bản copy ở đây.
}
finally {
    DataBufferUtils.release(buffer);
}
~~~

Không dùng buffer sau khi đã release. Nếu cần giữ nội dung cho xử lý bất đồng bộ, hãy copy sang `byte[]` hoặc representation có ownership rõ ràng trước khi release.

### 3.2. Không release hai lần

Nếu code đã release buffer trong `doOnNext`, đừng tiếp tục đưa chính buffer đó vào writer. Nếu writer nhận buffer để ghi response hoặc request outbound, writer là consumer và chịu trách nhiệm release sau khi đọc. Release lần thứ hai có thể gây lỗi reference count hoặc truy cập bộ nhớ đã giải phóng.

### 3.3. Retain chỉ khi thật sự có hai chủ sở hữu

`DataBufferUtils.retain(buffer)` tăng reference count khi implementation hỗ trợ. Mỗi reference được giữ phải có một lần release tương ứng. Nếu mục đích chỉ là ghi log hoặc kiểm tra chữ ký, thường an toàn hơn khi copy một lượng bytes có giới hạn rồi release buffer gốc.

Không dùng `retain` như cách sửa chữa chung cho pipeline khó hiểu. Hãy viết rõ consumer nào giữ buffer và consumer nào giải phóng nó.

## 4. Drain toàn bộ raw request body

Nếu endpoint không cần body nhưng cần đọc hết request trước khi trả response, drain `Flux<DataBuffer>` theo từng buffer. Cách này không gom toàn bộ payload vào memory.

~~~java
@PostMapping("/discard")
Mono<String> discard(@RequestBody Flux<DataBuffer> body) {
    AtomicLong totalBytes = new AtomicLong();

    return body
        .doOnNext(buffer -> {
            totalBytes.addAndGet(buffer.readableByteCount());
            DataBufferUtils.release(buffer);
        })
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
        .then(Mono.fromSupplier(
            () -> "discardedBytes=" + totalBytes.get()));
}
~~~

Giải thích:

1. `@RequestBody Flux<DataBuffer>` nhận luồng buffer thô thay vì yêu cầu Jackson decode JSON.
2. `readableByteCount()` lấy số byte còn đọc được trong buffer.
3. `doOnNext` cập nhật bộ đếm và release buffer ngay sau khi dùng.
4. `doOnDiscard` là lớp bảo vệ cho buffer bị operator hỗ trợ discard loại bỏ do filter, prefetch, lỗi hoặc cancellation.
5. `then(...)` chỉ phát kết quả sau khi body hoàn tất.

**Không dùng `collectList()` để drain body lớn.** Nó giữ tất cả phần tử trong memory cho tới khi nguồn complete; điều đó làm mất lợi ích streaming và có thể tạo memory pressure.

### 4.1. Drain trong functional endpoint

~~~java
Mono<ServerResponse> discard(ServerRequest request) {
    return request.bodyToFlux(DataBuffer.class)
        .doOnNext(DataBufferUtils::release)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
        .then(ServerResponse.noContent().build());
}
~~~

Cùng nguyên tắc với annotated controller: tiêu thụ hết stream, release từng buffer, rồi mới tạo response.

### 4.2. Khi cần gom body nhỏ có giới hạn

Đôi khi cần đọc bytes một lần để tính digest, kiểm tra định dạng hoặc parse thủ công. Dùng `DataBufferUtils.join` với giới hạn byte:

~~~java
Mono<byte[]> readBounded(Flux<DataBuffer> body) {
    int maxBytes = 64 * 1024;

    return DataBufferUtils.join(body, maxBytes)
        .map(buffer -> {
            try {
                byte[] copy = new byte[buffer.readableByteCount()];
                buffer.read(copy);
                return copy;
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        })
        .defaultIfEmpty(new byte[0]);
}
~~~

`join` tạo một buffer tổng hợp; tùy implementation, kết quả có thể là composite/zero-copy. Ứng dụng phải release buffer kết quả sau khi copy hoặc đọc xong. Khi nguồn lỗi hoặc bị cancel trong lúc gom, `DataBufferUtils.join` giải phóng những buffer đã tích lũy. Nếu vượt `maxBytes`, thao tác phát `DataBufferLimitException` thay vì âm thầm cấp phát không giới hạn.

Dùng giới hạn phù hợp với nghiệp vụ. Với file lớn hoặc body không giới hạn, hãy stream tới file/object storage hoặc downstream writer thay vì gom vào `byte[]`.

## 5. doOnDiscard: giải phóng phần tử bị operator loại bỏ

Một pipeline có thể bỏ buffer trước khi tới `doOnNext` cuối cùng:

~~~java
Flux<DataBuffer> selected = request.getBody()
    .filter(this::isWanted)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

Buffer không thỏa `isWanted` bị filter loại bỏ. `doOnDiscard` đăng ký cleanup cho những operator hỗ trợ discard trong phần upstream của chain. Nó không tự release mọi object bị mất khỏi mọi loại code; hãy kiểm tra operator nào thực sự hỗ trợ discard và đặt hook trong đúng composition chain.

Nếu giữ buffer được chọn để xử lý, vẫn cần release sau khi đọc:

~~~java
Mono<Void> processSelected(Flux<DataBuffer> selected) {
    return selected
        .doOnNext(buffer -> {
            try {
                inspect(buffer);
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        })
        .then();
}
~~~

Buffer bị filter loại được xử lý bởi discard hook; buffer đi qua filter được xử lý trong `doOnNext`. Hai đường cleanup có vai trò khác nhau.

`doOnDiscard` không thay thế cleanup cho buffer mà code đã lấy ra rồi giữ trong field, collection hoặc closure. Nếu ứng dụng tự lưu buffer, phải giải phóng nó khi hoàn tất, lỗi hoặc cancellation. `doFinally` chỉ báo hiệu kết thúc; nó không tự biết buffer nào cần release.

## 6. Lỗi và cancellation trong lúc đọc body

Một request có thể kết thúc trước khi body được đọc hết:
- Client đóng kết nối hoặc ngắt upload.
- Server timeout hoặc hủy subscription.
- Codec phát lỗi khi decode.
- Filter/handler dùng `take`, `next`, `timeout` hoặc short-circuit.
- Downstream writer từ chối hoặc lỗi khi relay.

Trong các tình huống này:
1. Để cancellation/error lan truyền theo reactive chain.
2. Release buffer đang được ứng dụng sở hữu.
3. Dùng `doOnDiscard` cho buffer được operator hỗ trợ discard.
4. Với buffer được giữ thủ công, dùng cleanup có ownership rõ ràng.
5. Không tạo subscription phụ bằng `subscribe()` chỉ để drain body.

Cách viết dễ sai:

~~~java
request.getBody().subscribe(DataBufferUtils::release);
return response.setComplete();
~~~

Subscription phụ chạy tách khỏi lifecycle của request. Response có thể complete trước khi drain xong; lỗi và cancellation của stream khó được phối hợp. Hãy compose Publisher:

~~~java
return request.getBody()
    .doOnNext(DataBufferUtils::release)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .then(response.setComplete());
~~~

Response chỉ được complete sau khi body Publisher hoàn tất. Nếu client disconnect, cancellation vẫn có thể làm chain kết thúc trước; không thể đảm bảo drain một request mà peer đã ngắt kết nối.

## 7. Form URL-encoded: dùng API đã decode và cache

Với `application/x-www-form-urlencoded`, Spring WebFlux cung cấp `ServerWebExchange.getFormData()` và `ServerRequest.formData()`. Framework dùng `FormHttpMessageReader` để decode thành `MultiValueMap<String, String>`.

~~~java
Mono<MultiValueMap<String, String>> form =
    exchange.getFormData();
~~~

Khi `getFormData()` được gọi, Spring parse body và cache kết quả để các thành phần khác có thể truy cập lại form data. Sau đó, raw request body ban đầu không còn là nguồn có thể đọc lại.

- Nếu cần giá trị form, dùng `getFormData()` nhất quán ở các thành phần.
- Không gọi `getFormData()` rồi tiếp tục mong `getRequest().getBody()` trả lại nguyên bytes.
- Nếu chỉ muốn bỏ form, có thể chờ `getFormData().then(...)`; parser có thể phải buffer form data trong giới hạn cấu hình.
- Nếu cần drain bytes thô mà không decode, đọc raw body và release từng `DataBuffer`; không đồng thời dùng form parser.

Đọc form trong functional endpoint:

~~~java
Mono<ServerResponse> handleForm(ServerRequest request) {
    return request.formData()
        .flatMap(data -> {
            String name = data.getFirst("name");
            return ServerResponse.ok()
                .bodyValue("namePresent=" + (name != null));
        });
}
~~~

Nếu chỉ cần kiểm tra một vài field, `getFormData()` phù hợp hơn tự parse URL encoding. Nếu body lớn hoặc có nguy cơ bị lạm dụng, cấu hình giới hạn bytes và kích thước form phù hợp.

## 8. Multipart: map-style và streaming

Multipart có thể chứa nhiều part, bao gồm field text và file. Spring WebFlux hỗ trợ parse thành `MultiValueMap<String, Part>` hoặc đọc lần lượt `Flux<PartEvent>`.

### 8.1. Map-style với getMultipartData()

~~~java
Mono<MultiValueMap<String, Part>> parts =
    exchange.getMultipartData();
~~~

`getMultipartData()` parse và cache map; raw body ban đầu không thể được đọc lại sau khi parser đã tiêu thụ. Nếu ứng dụng bỏ qua part đã parse và part có backing storage tạm, hãy xóa storage qua `Part.delete()`:

~~~java
Mono<Void> deleteAllParts(ServerWebExchange exchange) {
    return exchange.getMultipartData()
        .flatMapMany(map ->
            Flux.fromIterable(map.values())
                .flatMapIterable(parts -> parts))
        .concatMap(Part::delete)
        .then();
}
~~~

`Part.delete()` trả `Mono<Void>`; thao tác chỉ thực hiện khi Publisher được subscribe. Hãy compose nó vào chain và chờ hoàn tất. Không gọi `delete().subscribe()` rồi trả response ngay.

Với `FilePart`, nếu muốn giữ file, dùng `transferTo(Path)` hoặc streaming API phù hợp. `transferTo` tiêu thụ nội dung part và ghi vào destination; sau đó ứng dụng chịu trách nhiệm quản lý file đích. Nếu từ chối file, hãy cleanup part storage thay vì giữ file tạm không cần thiết.

### 8.2. Streaming bằng PartEvent

Khi dùng `Flux<PartEvent>`, mỗi multipart part phát ít nhất một event có header và buffer nội dung:
- `FormPartEvent` biểu diễn field text và cung cấp `value()`.
- `FilePartEvent` biểu diễn file; file lớn có thể phát nhiều event/buffer.
- Event cuối của mỗi part có `isLast() == true`.

Có thể chia stream thành các cửa sổ theo từng part:

~~~java
Flux<Flux<PartEvent>> parts =
    allPartEvents.windowUntil(PartEvent::isLast);
~~~

Nếu endpoint không cần bất kỳ part nào, release nội dung của từng event:

~~~java
Mono<Void> discardAllParts(Flux<PartEvent> events) {
    return events
        .doOnNext(event ->
            DataBufferUtils.release(event.content()))
        .doOnDiscard(PartEvent.class, event ->
            DataBufferUtils.release(event.content()))
        .then();
}
~~~

Mỗi `PartEvent.content()` trả `DataBuffer` do handler tiếp nhận. Khi bỏ qua part, phải release content của tất cả event, kể cả các event tiếp theo của file lớn. Không chỉ đọc `filename()` hoặc `FormPartEvent.value()` rồi bỏ Publisher mà không xử lý phần content còn lại.

### 8.3. Bỏ qua một part nhưng tiếp tục part tiếp theo

`windowUntil(PartEvent::isLast)` tạo một window cho mỗi part. Có thể xử lý tuần tự từng window; nếu không cần part, drain và release toàn bộ event trong window:

~~~java
Mono<Void> discardPart(Flux<PartEvent> part) {
    return part
        .doOnNext(event ->
            DataBufferUtils.release(event.content()))
        .doOnDiscard(PartEvent.class, event ->
            DataBufferUtils.release(event.content()))
        .then();
}

Mono<Void> discardMultipart(Flux<PartEvent> allEvents) {
    return allEvents
        .windowUntil(PartEvent::isLast)
        .concatMap(this::discardPart)
        .then();
}
~~~

`concatMap` giữ thứ tự và chỉ xử lý window tiếp theo sau khi window hiện tại hoàn tất. Nếu xử lý file được chọn, hãy relay toàn bộ stream content tới writer/storage và chờ relay complete trước khi chuyển sang phần tiếp theo.

### 8.4. Relay file part sang WebClient

Nếu mục tiêu là chuyển file tới service khác, không release buffer trước khi WebClient đọc. Khi Publisher được truyền cho writer, quyền tiêu thụ buffer được chuyển sang writer:

~~~java
Mono<Void> relay(
        WebClient client,
        Flux<PartEvent> partEvents) {

    return client.post()
        .uri("/internal/uploads")
        .body(partEvents, PartEvent.class)
        .retrieve()
        .bodyToMono(Void.class);
}
~~~

Đây là fragment minh họa; trong ứng dụng thực, route đích, metadata, timeout, xác thực và response mapping phải được cấu hình. Chỉ chuyển tiếp tới service được phép nhận dữ liệu. Không vừa release buffer trong `doOnNext` vừa truyền cùng buffer vào WebClient.

### 8.5. Chọn map-style hay streaming?

| Tình huống | Cách phù hợp |
| --- | --- |
| Form nhỏ, số part ít, cần đọc nhiều field | `getMultipartData()` hoặc binding `@RequestPart` |
| Upload file có kích thước giới hạn | `FilePart.transferTo(Path)` |
| File lớn, muốn backpressure và xử lý từng chunk | `Flux<PartEvent>` |
| Bỏ qua file part đã parse | `Part.delete()` |
| Bỏ qua toàn bộ multipart theo streaming | `PartEvent.content()` + `DataBufferUtils.release` |
| Relay upload tới service khác | Truyền `PartEvent`/`DataBuffer` tới WebClient writer và chờ hoàn tất |

Không parse multipart thành map chỉ để bỏ file lớn. Map-style có thể buffer metadata và quản lý temporary storage; streaming `PartEvent` phù hợp khi cần kiểm soát từng chunk và backpressure.

## 9. Short-circuit trong WebFilter

Một filter có thể chặn request trước controller, ví dụ auth middleware hoặc kiểm tra policy. Nếu quyết định trả response ngay, body có thể chưa được controller đọc.

Với request body có kích thước đã được giới hạn, filter có thể drain toàn bộ stream và release từng buffer trước khi hoàn tất response:

~~~java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class DrainAndRejectFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest()
            .getPath().pathWithinApplication().value();

        if (!"/api/body/reject".equals(path)) {
            return chain.filter(exchange);
        }

        exchange.getResponse()
            .setStatusCode(HttpStatus.PAYLOAD_TOO_LARGE);

        return exchange.getRequest().getBody()
            .doOnNext(DataBufferUtils::release)
            .doOnDiscard(
                DataBuffer.class, DataBufferUtils::release)
            .then(exchange.getResponse().setComplete());
    }
}
~~~

Thứ tự quan trọng:
1. Filter xác định request cần short-circuit.
2. Đặt status nhưng chưa commit response.
3. Subscribe vào request body và release mỗi buffer.
4. Chờ body complete.
5. Gọi `setComplete()` để commit response.

### 9.1. Không drain vô hạn một request bị từ chối

Drain toàn bộ body không phải lúc nào cũng là lựa chọn tốt. Nếu client gửi payload quá lớn, malicious upload hoặc stream không kết thúc, việc drain đến cuối có thể tiêu tốn băng thông, CPU và thời gian server.

- Với request hợp lệ về kích thước nhưng bị policy từ chối, drain/release rồi trả response có thể phù hợp.
- Với request vượt giới hạn kích thước, dừng đọc theo chính sách và cấu hình server/proxy để đóng hoặc reset kết nối khi cần.
- Đặt giới hạn ở gateway, HTTP server, codec và tầng upload; không chỉ kiểm tra sau khi toàn bộ body đã được nhận.
- Dùng timeout và rate limit cho upload.

Mục tiêu là xử lý ownership đúng. Điều đó không buộc ứng dụng phải đọc một body không giới hạn trong mọi tình huống.

## 10. Giới hạn buffering và chống cạn kiệt bộ nhớ

Một số API tiện dụng parse toàn bộ body thành object hoặc map. Điều này dễ dùng nhưng có chi phí:
- `Mono<byte[]>` giữ toàn bộ payload.
- `Mono<String>` giữ toàn bộ chuỗi sau decode.
- `getFormData()` parse form thành map.
- `getMultipartData()` tạo map part và có thể dùng temporary storage.
- `DataBufferUtils.join()` gom buffer thành một buffer tổng hợp.

Các biện pháp cần thiết:

1. Đặt giới hạn kích thước request ở gateway và server.
2. Cấu hình giới hạn buffer/codec phù hợp.
3. Dùng `PartEvent` cho file lớn hoặc streaming.
4. Không log hoặc cache toàn bộ request body mặc định.
5. Không dùng `collectList()` hoặc `join()` không giới hạn trên stream lớn.
6. Drain bằng `doOnNext(release).then()` khi chỉ cần bỏ body.
7. Giữ backpressure; không dùng `onBackpressureBuffer()` không giới hạn cho upload.
8. Theo dõi memory pool, request duration, upload failures và cancellation.

### 10.1. Request body chỉ đọc một lần

Không viết hai subscriber độc lập trên cùng raw body:

~~~java
Flux<DataBuffer> body = exchange.getRequest().getBody();

Mono<Long> count = body
    .map(DataBuffer::readableByteCount)
    .reduce(0L, Long::sum);

Mono<DataBuffer> joined = DataBufferUtils.join(body);
~~~

Không thể giả định body sẽ phát lại cho subscriber thứ hai. Nếu cần nhiều phép xử lý, hãy thực hiện trong một pipeline, copy bytes có giới hạn hoặc dùng API cache của exchange dành cho form/multipart. Cache body tùy chỉnh cần giới hạn memory và quản lý retain/release cẩn thận.

## 11. Ví dụ hoàn chỉnh: Spring Boot 4.0.9 và Java 17+

Project minh họa:
- Controller nhận raw `Flux<DataBuffer>` và release toàn bộ body.
- Controller nhận multipart `Flux<PartEvent>` và release nội dung từng event.
- `WebFilter` từ chối request trước controller nhưng drain body trước khi commit response.

### 11.1. Cấu trúc

~~~text
webflux-body-discard/
├── pom.xml
├── src/main/java/com/example/body/BodyDiscardApplication.java
├── src/main/java/com/example/body/BodyController.java
├── src/main/java/com/example/body/DrainAndRejectFilter.java
└── src/test/java/com/example/body/BodyDiscardIntegrationTest.java
~~~

### 11.2. pom.xml

Spring Boot 4.0.9 yêu cầu Java 17+ và Maven 3.6.3+.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-body-discard</artifactId>
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

### 11.3. BodyDiscardApplication.java

~~~java
package com.example.body;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BodyDiscardApplication {
    public static void main(String[] args) {
        SpringApplication.run(BodyDiscardApplication.class, args);
    }
}
~~~

### 11.4. BodyController.java

~~~java
package com.example.body;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.PartEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/body")
public class BodyController {

    @PostMapping(
        value = "/discard",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> discard(@RequestBody Flux<DataBuffer> body) {
        AtomicLong totalBytes = new AtomicLong();

        return body
            .doOnNext(buffer -> {
                totalBytes.addAndGet(buffer.readableByteCount());
                DataBufferUtils.release(buffer);
            })
            .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
            .then(Mono.fromSupplier(
                () -> "discardedBytes=" + totalBytes.get()));
    }

    @PostMapping(
        value = "/multipart/discard",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<ResponseEntity<Void>> discardMultipart(
            @RequestBody Flux<PartEvent> allPartEvents) {

        return allPartEvents
            .doOnNext(event ->
                DataBufferUtils.release(event.content()))
            .doOnDiscard(PartEvent.class, event ->
                DataBufferUtils.release(event.content()))
            .thenReturn(ResponseEntity.noContent().build());
    }

    @GetMapping(value = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("ok");
    }
}
~~~

Trong `/discard`, mỗi `DataBuffer` được đếm và release ngay; response chỉ được tạo khi Publisher complete. Trong `/multipart/discard`, mỗi `PartEvent.content()` được release, kể cả chunk file tiếp theo.

### 11.5. DrainAndRejectFilter.java

~~~java
package com.example.body;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class DrainAndRejectFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String path = exchange.getRequest()
            .getPath().pathWithinApplication().value();

        if (!"/api/body/reject".equals(path)) {
            return chain.filter(exchange);
        }

        exchange.getResponse()
            .setStatusCode(HttpStatus.PAYLOAD_TOO_LARGE);

        return exchange.getRequest().getBody()
            .doOnNext(DataBufferUtils::release)
            .doOnDiscard(
                org.springframework.core.io.buffer.DataBuffer.class,
                DataBufferUtils::release)
            .then(exchange.getResponse().setComplete());
    }
}
~~~

Filter chỉ short-circuit path thử nghiệm `/api/body/reject`. Nó đặt status 413, drain và release request body, sau đó mới complete response. Trong production, kết hợp với giới hạn body và chính sách close/reset connection khi request vượt giới hạn hoặc không thể drain an toàn.

## 12. HTTP integration tests

Test đi qua server thật bằng `RANDOM_PORT`. Dùng cùng một `HttpClient` để gửi body lớn, request bị từ chối, rồi request tiếp theo.

### 12.1. BodyDiscardIntegrationTest.java

~~~java
package com.example.body;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BodyDiscardIntegrationTest {

    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    @Value("${local.server.port}")
    int port;

    private HttpResponse<String> send(
            String method, String path,
            String contentType, String body) throws Exception {

        HttpRequest.Builder builder = HttpRequest.newBuilder(
            URI.create("http://localhost:" + port + path));

        HttpRequest.BodyPublisher publisher = body == null
            ? HttpRequest.BodyPublishers.noBody()
            : HttpRequest.BodyPublishers.ofString(body);

        if (contentType != null) {
            builder.header("Content-Type", contentType);
        }

        return CLIENT.send(
            builder.method(method, publisher).build(),
            HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void rawBodyIsFullyDrainedAndCounted() throws Exception {
        String payload = "x".repeat(256 * 1024);

        HttpResponse<String> response = send(
            "POST", "/api/body/discard",
            "application/octet-stream", payload);

        assertEquals(200, response.statusCode());

        int expectedBytes =
            payload.getBytes(StandardCharsets.UTF_8).length;

        assertEquals(
            "discardedBytes=" + expectedBytes,
            response.body());
    }

    @Test
    void rejectedRequestIsDrainedBeforeNextRequest()
            throws Exception {

        String payload = "ignored=".repeat(32 * 1024);

        HttpResponse<String> rejected = send(
            "POST", "/api/body/reject",
            "application/octet-stream", payload);

        assertEquals(413, rejected.statusCode());

        HttpResponse<String> next =
            send("GET", "/api/body/ping", null, null);

        assertEquals(200, next.statusCode());
        assertEquals("ok", next.body());
    }

    @Test
    void multipartPartsAreConsumedAndReleased() throws Exception {
        String boundary = "----webflux-boundary-123";
        String multipart =
            "--" + boundary + "\r\n" +
            "Content-Disposition: form-data; name=\"description\"\r\n" +
            "\r\n" +
            "sample upload\r\n" +
            "--" + boundary + "\r\n" +
            "Content-Disposition: form-data; name=\"file\"; filename=\"note.txt\"\r\n" +
            "Content-Type: text/plain\r\n" +
            "\r\n" +
            "file content that will be discarded\r\n" +
            "--" + boundary + "--\r\n";

        HttpResponse<String> response = send(
            "POST", "/api/body/multipart/discard",
            "multipart/form-data; boundary=" + boundary,
            multipart);

        assertEquals(204, response.statusCode());
        assertTrue(response.body().isEmpty());
    }
}
~~~

### 12.2. Chạy project

Yêu cầu JDK 17+ và Maven 3.6.3+:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Thử drain raw body:

~~~bash
curl -i -X POST http://localhost:8080/api/body/discard ^
  -H "Content-Type: application/octet-stream" ^
  --data-binary "payload to discard"
~~~

Thử filter từ chối và drain:

~~~bash
curl -i -X POST http://localhost:8080/api/body/reject ^
  -H "Content-Type: application/octet-stream" ^
  --data-binary "request body is drained before 413"
~~~

`^` là ký tự nối dòng của Windows CMD. Nếu chạy PowerShell, dùng một dòng hoặc ký tự nối dòng của PowerShell.

**Kết quả mong đợi:**

| Request | Kết quả |
| --- | --- |
| POST `/api/body/discard` | 200, body `discardedBytes=<số byte UTF-8>` |
| POST `/api/body/reject` | 413, filter drain body trước khi complete |
| GET `/api/body/ping` sau request bị từ chối | 200, body `ok` |
| POST `/api/body/multipart/discard` | 204, mọi event content đã được release |

Test dùng cùng một `HttpClient` cho request bị từ chối và request tiếp theo. Điều đó kiểm tra luồng HTTP tiếp tục hoạt động; nó không khẳng định connector luôn tái sử dụng chính xác cùng một TCP socket.

## 13. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `.then()` trên raw body mà không release | Buffer bị bỏ qua nhưng vẫn giữ reference | `doOnNext(DataBufferUtils::release).then()` |
| Chỉ release buffer đầu tiên | Phần còn lại của body/file vẫn bị giữ | Tiêu thụ hoặc release mọi buffer/event tới khi complete |
| Đọc `PartEvent.filename()` rồi bỏ window | Các chunk file sau không được xử lý | Consume, relay hoặc release toàn bộ window |
| Đọc `FormPartEvent.value()` rồi giả định mọi part đã giải phóng | Event content và các part tiếp theo có thể còn buffer | Đảm bảo toàn stream `PartEvent` được consume/release |
| Dùng `collectList()` để drain upload | Toàn bộ body bị giữ trong memory | Stream từng buffer rồi release |
| Dùng `DataBufferUtils.join()` không giới hạn | Payload lớn có thể làm cạn memory | Dùng `join(body, maxBytes)` hoặc streaming |
| Release buffer rồi truyền nó vào WebClient | Writer đọc buffer đã release | Chuyển ownership cho writer; không release thủ công trước |
| Truyền buffer cho hai consumer mà không retain/copy | Một consumer có thể đọc buffer đã giải phóng | Copy hoặc retain/release theo ownership rõ ràng |
| Dùng `doOnDiscard` như cleanup cho mọi biến | Buffer tự lưu trong field vẫn bị leak | Cleanup explicit khi hoàn tất/error/cancel |
| Gọi `subscribe()` riêng trong filter để drain | Response có thể complete trước drain | Compose drain bằng `.then(response.setComplete())` |
| Đọc raw body sau `getFormData()` | Body đã được parser tiêu thụ | Dùng cache `getFormData()` nhất quán |
| Đọc raw body sau `getMultipartData()` | Multipart parser đã tiêu thụ raw body | Dùng map cache hoặc streaming `PartEvent` từ đầu |
| Xóa file tạm mà không subscribe `Part.delete()` | Cleanup không được thực thi | Compose `Part.delete()` vào Publisher được trả về |
| Drain vô hạn request bị từ chối | Tốn băng thông/CPU, có thể giữ tài nguyên | Giới hạn body, timeout và đóng/reset kết nối theo chính sách |
| Chỉ kiểm tra happy path | Không phát hiện lỗi khi cancel, malformed body hoặc upload lớn | Test error/cancel, size limit, multipart và request tiếp theo |

## 14. Debug DataBuffer leak

### 14.1. Dấu hiệu thường gặp

- Direct memory tăng dần dù heap không tăng tương ứng.
- Netty báo `LEAK: ByteBuf.release() was not called before it's garbage-collected`.
- `OutOfDirectMemoryError` hoặc pool allocation thất bại.
- Lỗi xuất hiện sau request upload, parse multipart hoặc filter short-circuit.
- Test nhỏ chạy tốt nhưng lỗi khi tải đồng thời hoặc file lớn.

### 14.2. Checklist điều tra

1. Tìm tất cả nơi gọi `getBody()`, `bodyToFlux(DataBuffer.class)` và `PartEvent.content()`.
2. Xác định mỗi buffer thuộc consumer nào.
3. Kiểm tra nhánh filter, `skip`, `filter`, `take`, `next`, timeout và cancellation.
4. Kiểm tra mọi `DataBuffer` đã được release sau khi đọc hay đã chuyển ownership cho writer.
5. Kiểm tra `doOnDiscard` đặt sau các operator có thể discard.
6. Kiểm tra code có gọi `subscribe()` tách rời hoặc đọc body nhiều lần không.
7. Kiểm tra multipart temporary storage và `Part.delete()`.
8. Bật leak detection/debug option phù hợp của Reactor Netty trong môi trường test.
9. Chạy integration test với body lớn và nhiều request đồng thời.
10. Theo dõi direct memory, pool metrics và số request đang xử lý.

Không bật leak detection mức chi tiết cao liên tục trong production nếu chi phí hiệu năng quá lớn. Dùng profile chẩn đoán hoặc test môi trường để tìm vị trí cấp phát và release.

## 15. Quy tắc thiết kế production

- Đọc ở abstraction cao nhất có thể: DTO/String/Part API giúp codec quản lý buffer; chỉ thao tác raw `DataBuffer` khi cần.
- Nếu bỏ body, drain và release theo stream; không aggregate payload chỉ để vứt đi.
- Nếu relay, để writer nhận ownership và chờ Publisher downstream complete.
- Nếu parse form/multipart qua exchange API, không đọc lại raw body.
- Nếu stream multipart, xử lý từng part đến `isLast`; không bỏ các chunk còn lại.
- Nếu dùng operator discard, thêm cleanup hook; vẫn giải phóng explicit buffer đi qua nhánh xử lý.
- Giới hạn kích thước và thời gian; tránh drain upload không giới hạn.
- Kiểm thử cancellation và lỗi; happy path không chứng minh cleanup đúng.
- Không log body/file mặc định; tránh lộ dữ liệu và tạo bản sao lớn trong memory.
- Không subscribe thủ công; để request lifecycle quản lý consumption, error và cancellation.

## 16. Bài tập thực hành

**Bài 1 – Drain raw body.** Viết endpoint nhận `Flux<DataBuffer>`, đếm số byte và release từng buffer. Gửi body vài trăm KB và kiểm tra số byte.

**Bài 2 – Filter short-circuit.** Viết `WebFilter` từ chối một path trước controller. Drain/release body rồi trả 413. Dùng cùng `HttpClient` gửi request tiếp theo.

**Bài 3 – DataBufferUtils.join.** Viết helper đọc body có giới hạn 64 KB. Thử body nhỏ, body rỗng và body vượt giới hạn; kiểm tra buffer kết quả luôn được release.

**Bài 4 – doOnDiscard.** Thêm `filter` loại một số `DataBuffer`. Release buffer được chọn sau khi đọc và dùng `doOnDiscard` cho buffer bị filter bỏ.

**Bài 5 – Form cache.** Gọi `getFormData()` từ filter và controller. Chứng minh cả hai đọc cùng cache, đồng thời raw request body không còn đọc lại được.

**Bài 6 – Multipart map.** Gọi `getMultipartData()`, bỏ một `FilePart` và gọi `Part.delete()`. Kiểm tra Publisher cleanup đã complete.

**Bài 7 – PartEvent.** Dùng `windowUntil(PartEvent::isLast)` để chia file thành part. Release toàn bộ content của part không được chọn.

**Bài 8 – Relay upload.** Relay `Flux<PartEvent>` tới WebClient. Không release buffer trước writer; chờ response outbound hoàn tất.

**Bài 9 – Cancellation.** Ngắt client giữa upload. Kiểm tra cancellation lan tới nguồn, buffer đang giữ được cleanup và không có subscription phụ.

**Bài 10 – Load test.** Gửi nhiều upload đồng thời, theo dõi direct memory/pool metrics trước và sau khi sửa. So sánh với phiên bản gom toàn bộ body vào `List<DataBuffer>`.

## 17. Tài liệu tham khảo chính thức

1. Spring Framework 7.0.8 – Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
2. Spring Framework 7.0.8 – Functional Endpoints / `ServerRequest.bodyToFlux` và multipart `PartEvent`: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
3. Spring Framework 7.0.8 – Multipart Content trong annotated controller: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
4. Spring Framework 7.0.8 – Reactive Core, Form Data và Multipart Data: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
5. Spring Framework Javadoc – `DataBufferUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
6. Spring Framework Javadoc – `DataBuffer` / `PooledDataBuffer`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/PooledDataBuffer.html
7. Spring Framework Javadoc – `Part` / `PartEvent`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/Part.html
8. Spring Framework Javadoc – `FilePart`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/FilePart.html
9. Spring Boot 4.0.9 – System Requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html
10. Reactor Core – Reference Guide, discard hooks and cancellation: https://projectreactor.io/docs/core/release/reference/

**Tự đánh giá cuối:** Vì sao `.then()` không tự release `DataBuffer`? Khi nào cần `doOnDiscard` ngoài `doOnNext(release)`? Vì sao không thể đọc raw body sau `getFormData()` hoặc `getMultipartData()`? Khi bỏ một file `PartEvent`, phải làm gì với mọi chunk đến sau event đầu tiên? Nếu trả lời được các câu hỏi này và kiểm thử được filter short-circuit, multipart, cancellation và request kế tiếp, bạn đã nắm được cách xử lý đầy đủ body bị bỏ qua trong WebFlux.
