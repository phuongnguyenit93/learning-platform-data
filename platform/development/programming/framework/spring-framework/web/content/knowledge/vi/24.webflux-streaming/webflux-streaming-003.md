# DataBuffer, bộ nhớ đệm dùng pool và trách nhiệm giải phóng trong Spring WebFlux

## 1. Mục tiêu và vấn đề thực tế

Trong Spring WebFlux, HTTP body không nhất thiết xuất hiện một lần dưới dạng `String` hay `byte[]`. Khi tải tệp, phát video, proxy một luồng dữ liệu hoặc đọc payload lớn, hạ tầng thường xử lý **`Flux<DataBuffer>`**, tức một chuỗi những mảnh byte. Một số mảnh dùng **pooled/direct memory** được quản lý bằng reference count; nếu nhận buffer mà không trả lại đúng lúc sẽ gây rò bộ nhớ, còn trả lại quá sớm sẽ gây lỗi truy cập vùng nhớ đã được tái sử dụng.

Bài thuộc nhóm **Streaming WebFlux**, dành cho **Java 17+, Spring Framework 6.x, Spring Boot 3.x, Project Reactor**. Trọng tâm không chỉ là biết gọi `DataBufferUtils.release`, mà là trả lời đúng câu hỏi **ai sở hữu buffer tại từng bước**.

Sau bài học, bạn có thể:

- Giải thích `DataBuffer`, `DataBufferFactory`, `DefaultDataBuffer`, `NettyDataBuffer`, `PooledDataBuffer` và `DataBufferUtils`.
- Hiểu direct vs heap memory, pooling và reference counting (`retain`/`release`).
- Phân biệt **đọc xong rồi bỏ** với **chuyển ownership sang người tiêu thụ tiếp theo**.
- Biết khi nào **cần tự release** và khi nào **tuyệt đối không release thủ công** vì WebFlux/codec/HTTP writer đã chịu trách nhiệm.
- Viết pipeline `Flux<DataBuffer>` xử lý đúng `onNext`, `onError`, `cancel` và discarded buffers.
- Dùng `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` đúng chỗ; không lạm dụng `doFinally` để release các buffer đã bị chuyển quyền.
- Hiểu `DataBufferUtils.join(...)`, `maxByteCount`, `DataBufferLimitException`, zero-copy composite và giới hạn memory.
- Phân biệt các biến thể `DataBufferUtils.write(...)`, file channel và response writing.
- Xây ví dụ Spring Boot WebFlux có endpoint nhận bytes giới hạn và endpoint trả streaming bytes; kiểm thử bằng `WebTestClient` và Reactor.
- Chẩn đoán leak, double-release, use-after-release, native memory growth và giới hạn tài nguyên.

**Phạm vi:** WebFlux reactive streaming, không phải Java `ByteBuffer` đơn lẻ. Code dùng Spring Boot 3.x/WebFlux, nơi ứng dụng thường dùng Reactor Netty. Các hành vi cụ thể của native buffer allocator có thể khác theo HTTP server/framework version; hãy dựa trên API contract và kiểm thử, không tự hardcode reference count của mọi triển khai.

## 2. DataBuffer nằm ở đâu trong HTTP pipeline?

```text
HTTP network -> Reactor Netty ByteBuf
                         |
                         v
                  NettyDataBuffer
                         |
                   Flux<DataBuffer>
                         |
           +-------------+--------------+
           |             |              |
           v             v              v
       JSON decoder  custom transform  raw streaming/file
           |             |              |
           v             v              v
       Java DTO        bytes/frames   DataBuffer stream
           |             |              |
           +-------------+--------------+
                         |
                         v
               HTTP response writer
                         |
                         v
                 release/cleanup
```

`DataBuffer` trừu tượng hóa một mảnh byte bất kể nền tảng là Netty, Jetty, array hay `ByteBuffer`. Framework có `Encoder`, `Decoder`, message readers/writers và transport handlers xử lý chúng.

Một endpoint thông thường:

```java
@PostMapping("/users")
public Mono<UserDto> create(@RequestBody Mono<UserInput> body) {
    return body.flatMap(service::create);
}
```

Đây là **snippet**, không phải file độc lập. Ứng dụng không trực tiếp thấy `DataBuffer` vì message reader/Jackson decoder đang sở hữu các raw buffers và giải phóng theo contract của codec. Việc tự thêm `DataBufferUtils.release(...)` vào controller DTO là vô nghĩa.

Chỉ cần xử lý raw `DataBuffer` khi bạn chủ động tham gia đường đi byte-level như upload/proxy/filter/custom decoder/binary transforms. Khi đó bạn phải xác định ownership rõ ràng.

## 3. Các interface/lớp quan trọng

| Thành phần | Trách nhiệm |
| --- | --- |
| `DataBuffer` | Byte buffer abstraction: đọc/ghi, positions, số byte có thể đọc/ghi |
| `DataBufferFactory` | Allocate hoặc wrap byte array/ByteBuffer thành DataBuffer |
| `DefaultDataBufferFactory` | Factory thường dùng heap/NIO buffers không reference-counted kiểu Netty |
| `NettyDataBufferFactory` | Factory dựa trên Netty `ByteBufAllocator` |
| `PooledDataBuffer` | DataBuffer mở rộng với `retain()`, `release()`, `isAllocated()` |
| `CloseableDataBuffer` | API close khi buffer hỗ trợ lifecycle kiểu AutoCloseable |
| `DataBufferUtils` | Helper read/write/join/release/retain/touch và byte-count operations |
| `DataBufferLimitException` | Lỗi khi tổng số bytes cần buffer vượt giới hạn đặt trước |
| `DataBufferUtils.releaseConsumer()` | Consumer gọi release cho mỗi DataBuffer |
| `DataBufferUtils.join(...)` | Gộp Flux buffers thành một DataBuffer (có thể composite) |
| `DataBufferUtils.read(...)` | Chuyển file/resource/channel thành Flux buffers |
| `ServerHttpResponse.writeWith(...)` | Viết Publisher<DataBuffer> ra response body |

Các lớp ở package `org.springframework.core.io.buffer`, trừ các HTTP request/response types thuộc Spring Web reactive HTTP APIs.

Không nhầm `org.springframework.core.io.buffer.DataBuffer` với `java.nio.ByteBuffer`: DataBuffer có các semantics quản lý memory/pooled ownership riêng, nhất là khi được bọc Netty `ByteBuf`.

## 4. Heap memory, direct memory và pooled memory

### Heap buffer

Một buffer dựa trên Java `byte[]` thường nằm trong JVM heap; garbage collector quản lý tuổi thọ array. `DefaultDataBufferFactory` có thể sử dụng kiểu này. `DataBufferUtils.release` với buffer không được pooled/closeable có thể trả `false` vì không có native reference cần decrement.

**Điều này không khiến code leak-safe trên mọi transport.** Nếu test chỉ chạy với DefaultDataBufferFactory, một bug thiếu release có thể không lộ rõ; triển khai Netty sử dụng pooled direct memory vẫn rò.

### Direct buffer

`ByteBuffer.allocateDirect`/Netty direct buffers có thể dùng memory ngoài heap để giảm copy khi I/O. Phần memory đó **không được nhìn thấy đầy đủ** qua chỉ số `Runtime.totalMemory()-freeMemory()`; leak có thể gây OOM/direct-memory pressure dù Java heap còn đủ.

### Pool

Tạo/hủy hàng nghìn buffers thường xuyên có chi phí. Pool cho phép trả vùng memory về allocator để tái sử dụng. Tuy nhiên **buffer được trả về pool có thể được một request khác dùng ngay**; nếu code tiếp tục đọc sau release, dữ liệu có thể sai, phát exception hoặc xảy ra lỗi nguy hiểm ở tầng native.

Không kết luận “GC sẽ tự release buffer đúng lúc” trong trường hợp `PooledDataBuffer` reference-counted. Pool ownership cần được giải quyết bằng release có chủ đích ở boundary.

## 5. Reference counting: retain và release

`PooledDataBuffer` theo semantics của Spring:

```text
allocate()      refCount ≈ 1 (chủ sở hữu ban đầu)
retain()        refCount ≈ 2 (thêm một reference có trách nhiệm release)
release()       refCount ≈ 1
release()       refCount ≈ 0 -> allocator có thể tái dùng memory
```

Dấu `≈` nhấn mạnh đây là **mô hình đơn giản hóa**; allocator/shared slices/composite buffers có chi tiết riêng.

- `retain()` giữ buffer sống lâu hơn bằng cách tăng reference count nếu là pooled.
- `release()` giảm count của reference đã sở hữu; khi về 0, vùng nhớ được coi đã trả lại.
- `isAllocated()` phản ánh trạng thái theo PooledDataBuffer contract.
- `DataBufferUtils.retain(dataBuffer)` chỉ retain khi thích hợp; code portable hơn tự cast.
- `DataBufferUtils.release(dataBuffer)` release khi buffer pooled hoặc closeable theo API; có thể trả true/false tùy việc giải phóng.
- **Mỗi ownership reference thêm bởi retain phải có một release tương ứng**.
- Không gọi release hai lần trên **cùng một ownership**.
- Không retain “cho chắc” mà không thiết kế đường release trong cả success/error/cancel.

Một bộ nhớ được phát lại từ pool không phải một object business bất biến mà bạn có thể lưu vào cache hoặc chia sẻ cho nhiều threads tùy tiện. Nếu cần giữ payload sau HTTP request, hãy **copy dữ liệu vào `byte[]`/storage có giới hạn**, hoặc quản lý retain/release với ownership rõ ràng.

## 6. Quy tắc vàng: ai là consumer cuối?

| Tình huống | Ai chịu trách nhiệm cuối? | Hành động |
| --- | --- | --- |
| Controller nhận `Mono<DTO>` từ `@RequestBody` | Decoder/WebFlux | Không release thủ công DTO |
| Code đọc trực tiếp một `DataBuffer`, biến thành String/DTO rồi bỏ buffer | Code đó | Release trong `finally` |
| Code gộp buffers bằng `DataBufferUtils.join` | Join quản lý các buffers thành phần; consumer của kết quả quản lý joined buffer | Release **joined result** một lần |
| Code tạo buffer rồi truyền tới `ServerHttpResponse.writeWith` | HTTP writer sau khi nhận ownership | Không release sớm trong controller |
| Code tạo buffer, nhưng encode thất bại **trước khi bàn giao** | Code tạo buffer | Release trong catch/finally |
| Code filter bỏ bớt DataBuffer trên đường đi | Pipeline/filter đã bỏ | Release discarded buffers, ví dụ `doOnDiscard` |
| Code cần giữ một pooled buffer ngoài vòng đời hiện tại | Người giữ thêm reference | `retain` khi giữ; `release` khi xong |
| Code dùng `DataBufferUtils.write(..., OutputStream)` | Caller quản lý channel, xử lý returned buffers | Theo contract, output stream không đóng và buffers không tự release |
| Code chỉ gọi `Flux<DataBuffer>.map(...)` để quan sát rồi forward cùng buffer | Downstream cuối nếu ownership được chuyển rõ | Không release khi còn forward |

**Không có quy tắc chung “cứ thấy DataBuffer là gọi release ngay”.** Đúng hơn: **mỗi lần một bên tiêu thụ xong ownership thì phải release; nếu chuyển ownership cho bên khác thì không tự release phần đó**.

## 7. Dùng DataBufferFactory đúng cách

Trong WebFlux HTTP handler, factory có sẵn trên response:

```java
DataBufferFactory factory = response.bufferFactory();
byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
DataBuffer buffer = factory.wrap(bytes);
```

Đây là snippet trong method có `ServerHttpResponse response` và imports Spring/Java. `wrap(byte[])` bọc dữ liệu sẵn có; `allocateBuffer(initialCapacity)` tạo buffer mới.

```java
DataBuffer buffer = factory.allocateBuffer(64);
buffer.write("hello".getBytes(StandardCharsets.UTF_8));
```

Không dùng `allocateBuffer()` no-arg khi đã biết capacity hợp lý (method no-arg đã deprecated trong Spring Framework 6.0+). Đặt `64` là initial capacity, **không phải** giới hạn payload: DataBuffer implementation có thể mở rộng nếu cứ write nhiều bytes.

**Nếu wrapper dùng underlying byte[] có thể thay đổi, không mutate mảng đó sau khi đã bàn giao buffer**; đây là nguy cơ data race/corruption. Cách đơn giản cho response nhỏ là trả `Mono<String>`/DTO để encoder tự quản lý thay vì raw DataBuffer.

### Wrap và allocate khác pool thế nào?

Factory cụ thể quyết định wrap có copy/pooled hay không. `DefaultDataBufferFactory` và `NettyDataBufferFactory` có implementation khác nhau. Không dựa vào câu “wrap không copy” để kết luận reference counting luôn tăng hoặc không cần release. Nếu bạn chỉ cần text JSON API thông thường, hãy để framework encoder quyết định.

## 8. Đọc một buffer và release trong finally

Ví dụ chuyển raw `DataBuffer` thành `byte[]`:

```java
static byte[] consumeBytes(DataBuffer buffer) {
    try {
        byte[] out = new byte[buffer.readableByteCount()];
        buffer.read(out);
        return out;
    } finally {
        DataBufferUtils.release(buffer);
    }
}
```

**Đây là method hoàn chỉnh để đặt trong class có imports** `org.springframework.core.io.buffer.DataBuffer` và `DataBufferUtils`, nhưng **không** tự biên dịch khi thiếu Spring libraries/class wrapper.

Ownership: method **nhận và tiêu thụ toàn bộ ownership của buffer đầu vào**. Nó trả `byte[]` độc lập và release buffer ngay cả khi `read(...)` ném exception. Đừng truyền vào method này một buffer mà HTTP writer hoặc downstream khác đang cần dùng nếu bạn chưa có reference/ownership riêng.

**Cảnh báo memory:** Tạo `byte[]` bằng `readableByteCount()` có thể allocate rất lớn nếu input không bị giới hạn. Chỉ dùng sau khi đã có giới hạn kích thước request và tổng số bytes. Nếu cần streaming file nhiều GB, xử lý từng buffer và giới hạn memory; không gom toàn bộ vào heap.

## 9. Anti-pattern: release trước response.writeWith

**Sai:**

```java
DataBuffer db = response.bufferFactory()
    .wrap("hello".getBytes(StandardCharsets.UTF_8));

DataBufferUtils.release(db);       // Ownership đã bị trả quá sớm!
return response.writeWith(Mono.just(db));
```

Đây là **phản ví dụ**, không được đưa vào project. Nếu db là pooled và refCount đã về 0, HTTP writer có thể đọc vùng nhớ đã được allocator thu hồi.

**Đúng khi chuyển ownership cho HTTP writer:**

```java
DataBuffer db = response.bufferFactory()
    .wrap("hello".getBytes(StandardCharsets.UTF_8));
return response.writeWith(Mono.just(db));
```

Đây cũng là snippet trong method trả `Mono<Void>`, có `response`. Khi giao buffer cho `writeWith`, code không tự release buffer đó sau khi phát. Writer/transport layer có trách nhiệm theo contract. Nếu method tự allocate nhưng thất bại **trước khi Publisher được trả/bàn giao**, code tạo buffer phải dọn reference đó.

**Không tự viết `doOnNext(DataBufferUtils::release)` trên source đang gửi vào HTTP response.** Nó có thể làm buffer hết hạn trước khi response writer sử dụng.

## 10. Reactive operators có thể bỏ hoặc giữ buffer

Reactor operators như `filter`, `skip`, `take`, `flatMap`, `buffer`, `window` có thể bỏ phần tử hoặc giữ chúng trong internal queues. Nếu phần tử là `DataBuffer` pooled, cần xác định cả **path được forward** lẫn **path bị discard**.

Ví dụ loại bỏ buffer rỗng:

```java
Flux<DataBuffer> nonEmpty = incoming
    .filter(db -> db.readableByteCount() > 0)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

Đây là snippet với `Flux<DataBuffer> incoming` có sẵn. Với dropped buffers, `doOnDiscard` giúp release khi operator hỗ trợ discard. **Những buffers được giữ lại trong `nonEmpty` vẫn cần được consumer cuối release hoặc nhận ownership** — `doOnDiscard` không tự release phần tử được gửi tới downstream.

Nếu pipeline chuyển đổi thành DTO:

```java
Flux<byte[]> payloads = incoming
    .filter(db -> db.readableByteCount() > 0)
    .map(db -> {
        try {
            byte[] out = new byte[db.readableByteCount()];
            db.read(out);
            return out;
        } finally {
            DataBufferUtils.release(db);
        }
    })
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

Đây là snippet minh họa trong một pipeline đã có `incoming`. `map` xử lý buffers đi qua; `filter` có thể discard. Với operators nội bộ phức tạp, đặt `doOnDiscard` ở một vị trí mà hook thấy các discard upstream/downstream phù hợp, theo Reactor semantics. Không kỳ vọng `doOnDiscard` tự xử lý mọi ownership giữ trong biến local bên ngoài Reactor, hoặc mọi operator tùy chỉnh.

### Cancellation và discarded buffers

Khi client disconnect/cancel, operator với prefetch/queue có thể bỏ các phần tử đang giữ; một số operators hỗ trợ discard hooks để cleanup. Nhưng nếu ứng dụng tự cất buffer vào `Map`, `List` hoặc shared queue thì `doOnDiscard` không quản lý references bên ngoài: bạn vẫn phải release explicit cho những references đó trên complete/error/cancel.

## 11. Vì sao doFinally không thể thay release cho từng DataBuffer?

Một anti-pattern:

```java
Flux<DataBuffer> source = incoming
    .doFinally(signal -> System.out.println("done"));
```

`doFinally` chạy **một lần cho một subscription terminal/cancel ở vị trí operator**, không phải một lần cho từng buffer. Chỉ in log ở đây không giải phóng các phần tử đã được phát và bỏ. Nếu bạn giữ `List<DataBuffer>` trong một scope, dùng `doFinally` để dọn list có thể hợp lý **khi bảo đảm ownership, exactly-once cleanup và không có buffer nào đã chuyển downstream**, nhưng cách đó dễ sai với cạnh tranh giữa cancellation và async writes.

Tốt hơn:

- Release trực tiếp mỗi buffer khi tiêu thụ xong (`try/finally`, `doOnNext` khi đúng boundary).
- Dùng `doOnDiscard` cho elements operator bỏ.
- Dùng `DataBufferUtils.join` cho bounded aggregation.
- Dùng `using/usingWhen` để quản lý resources như file/channel/connection (không thay ownership của từng DataBuffer).
- Để response writer quản lý buffers đã chuyển cho `writeWith`.

**Không release cùng buffer ở cả `map finally` và `doOnNext` downstream**, vì có thể double-release.

## 12. DataBufferUtils.release, retain, touch

Các helpers chuẩn:

```java
DataBufferUtils.retain(buffer);   // Tăng ref nếu buffer pooled.
DataBufferUtils.release(buffer);  // Giảm ref/close nếu implementation hỗ trợ.
DataBufferUtils.touch(buffer, "request-123");
```

Đây là snippets. `touch` gắn hint nếu buffer hỗ trợ leak tracking; hint **không** thay release và không dùng string chứa token/PII.

### Khi nào retain?

Giả sử bạn đã có một buffer thuộc **một chủ sở hữu** mà phải bàn giao thêm cho một consumer độc lập. Khi và chỉ khi cần hai ownership references:

```text
Owner A             Owner B
  |                   |
  | -- retain(buf) -->|  (thêm 1 reference)
  |                   |
  | release(buf)      |  Owner A xong
  |                   |
  |                release(buf)  Owner B xong
```

Nếu A chỉ **chuyển** ownership duy nhất cho B, **không cần retain**; A không release nữa. Retain vô cớ rồi chỉ release một lần sẽ leak một reference; release của A trước khi retain cho B sẽ gây use-after-release.

### Kiểm tra trạng thái

`PooledDataBuffer.isAllocated()` là API kiểm buffer vẫn được phân bổ. Nó không phải tín hiệu “đã đủ an toàn để bất kỳ thread nào đọc” hay bằng chứng uniqueness; multiple owners có thể cùng giữ reference. Không sử dụng một lần check-then-use làm synchronization giữa concurrent threads. Ownership và thread safety phải được thiết kế chặt.

## 13. DataBufferUtils.join: gộp, giới hạn và composite

`DataBufferUtils.join(Publisher<? extends DataBuffer>)` gộp một luồng thành một `Mono<DataBuffer>`. Kết quả có thể:

- Copy bytes vào một buffer mới; hoặc
- **Composite/zero-copy** nắm references tới các buffers thành phần.

Hành vi tùy implementation; không giả định `join` luôn copy hoặc luôn zero-copy.

**Ownership đặc biệt:**

1. Buffers **đã đưa vào join thành công** được quản lý bởi aggregate/composite — **không release lại từng buffer thành phần**.
2. Khi join gặp error hoặc cancel trước khi hoàn tất, Spring giải phóng những buffers đã tích lũy theo API contract.
3. **Người tiêu thụ kết quả joined DataBuffer** phải release **joined result** sau khi đọc xong.
4. Không vừa release joined result vừa release các thành phần vì đó có thể là double release.

### Giới hạn maxByteCount

```java
Mono<DataBuffer> bounded =
    DataBufferUtils.join(request.getBody(), 64 * 1024);
```

Đây là snippet trong method có `ServerHttpRequest request`. `64 * 1024` = 65.536 bytes, **tổng dung lượng buffer** ở nhánh join. Nếu vượt, API phát `DataBufferLimitException`; không tạo một byte array vài GB rồi mới kiểm độ dài.

Lưu ý: Việc giới hạn `join` bảo vệ **aggregation cụ thể**, không thay các hạn mức HTTP server, decoder, gateway, upload quota, CPU hoặc tổng in-flight requests. Nếu 2.000 clients cùng tạo 65 KiB buffers, tổng memory vẫn đáng kể.

### Release joined result đúng chỗ

```java
return DataBufferUtils.join(request.getBody(), 65536)
    .map(joined -> {
        try {
            byte[] bytes = new byte[joined.readableByteCount()];
            joined.read(bytes);
            return calculate(bytes);
        } finally {
            DataBufferUtils.release(joined);
        }
    });
```

Snippet giả định `calculate(byte[])` trả DTO; có thể thêm `onErrorMap(DataBufferLimitException.class,...)` để map thành HTTP 413. `map` nhận duy nhất joined buffer đã hoàn tất; nếu join bị cancel/error trước khi phát result, Spring quản lý các accumulated buffers. Mỗi joined result được giải phóng một lần trong `finally`.

## 14. DataBufferUtils.write: các overload không giống nhau

`DataBufferUtils.write` có nhiều chữ ký; không được gộp tất cả thành câu “write sẽ tự release”.

| Dạng | Kết quả | Điểm cần nhớ |
| --- | --- | --- |
| `write(source, OutputStream)` | `Flux<DataBuffer>` | Không đóng OutputStream và **không tự release buffers** |
| `write(source, WritableByteChannel)` | `Flux<DataBuffer>` | Không đóng channel, không tự release buffers |
| `write(source, AsynchronousFileChannel)` | `Flux<DataBuffer>` | Không đóng channel, không tự release buffers |
| `write(source, AsynchronousFileChannel, position)` | `Flux<DataBuffer>` | Cũng cần ownership/close policy |
| `write(source, Path, OpenOption...)` | `Mono<Void>` | File write API tự quản lý file channel theo implementation; xem Javadoc khi dùng, không đồng nhất với overload Flux |
| `read(Path, factory, size)` | `Flux<DataBuffer>` | Stream file, API bảo đảm đóng file khi Flux kết thúc |
| `join(source, max)` | `Mono<DataBuffer>` | Aggregation bounded; release joined result sau khi dùng |

Ví dụ với `OutputStream` (minh họa **blocking API**, không đặt trực tiếp trên Netty event loop):

```java
Flux<DataBuffer> written =
    DataBufferUtils.write(source, outputStream)
        .doOnNext(DataBufferUtils.releaseConsumer())
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

Snippet này cần `source` và `outputStream` được tạo/đóng bởi owner đúng. `write(source, outputStream)` thực thi khi có subscription, không tự close stream; `doOnNext` release những buffers đã được writer phát ra **sau khi ghi**. Với prefetch/cancel, discarded hook giúp release ở operators hỗ trợ discard. Trong triển khai hoàn chỉnh, còn phải đóng stream trên complete/error/cancel, hạn chế blocking bằng scheduler phù hợp và xử lý đường lỗi trước khi buffer được phát tới `doOnNext`.

Để lưu file upload thực tế, ưu tiên `FilePart.transferTo(Path)` khi phù hợp và áp dụng size limit, kiểm filename/path, storage authorization và cleanup. Chỉ dùng low-level write khi thật sự cần kiểm soát bytes.

## 15. Custom decoder và encoder: điểm bàn giao ownership

Spring mô tả quy tắc đối với codecs:

### Decoder

Decoder là bên cuối trực tiếp đọc một buffer trước khi tạo object cấp cao (`String`/DTO/JSON). Nếu đã hoàn tất đọc và không chuyển `DataBuffer` cho ai khác, **decoder release buffer**.

```java
.map(buffer -> {
    try {
        return deserialize(buffer);
    } finally {
        DataBufferUtils.release(buffer);
    }
})
.doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

Đây là snippet cần implementation `deserialize` và upstream. Mỗi input buffer được đọc xong phải được release; discarded hook cho các đường rẽ không đưa buffer vào map. Nếu decoder gộp nhiều buffers, dùng `join`/bounded aggregation và release **aggregate** đúng; đừng giữ object pooled trong field sống lâu.

### Encoder

Encoder tạo một `DataBuffer` và chuyển downstream cho HTTP response writer. Nếu encode hoàn tất, encoder **bàn giao** ownership, không release sớm. Nếu encode/serialization throw **trước khi bàn giao**, encoder phải cleanup.

```java
DataBuffer buffer = factory.allocateBuffer(256);
boolean transferred = false;
try {
    writeSerializedValue(buffer, value);
    transferred = true;
    return buffer;
} finally {
    if (!transferred) {
        DataBufferUtils.release(buffer);
    }
}
```

Đây là snippet minh họa trong method có `factory`, `value` và `writeSerializedValue`. Nó bao phủ exception **trước return/bàn giao**; khi downstream filter hoặc HTTP writer từ chối/hủy, còn cần thiết kế release/discard theo đúng pipeline. Không lấy đoạn này làm custom encoder production mà thiếu test error/cancel.

**Quan trọng:** “Bên tạo tự release” đúng chỉ khi tạo thất bại trước khi giao; khi encoder đã giao cho writer thì **writer** là consumer chịu trách nhiệm theo contract.

## 16. WebClient: consume hoặc release response body

`WebClient` thường dùng các high-level methods:

```java
Mono<UserDto> user = webClient.get()
    .uri("/users/{id}", id)
    .retrieve()
    .bodyToMono(UserDto.class);
```

Đây là snippet trong service có `webClient`/`UserDto`. Framework codecs giải mã và quản lý DataBuffers; code của bạn chỉ nhận DTO, không tự release raw buffers.

Khi cần kiểm status/body tùy condition:

```java
Mono<String> result = webClient.get()
    .uri("/status")
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(String.class);
        }
        return response.createError();
    });
```

`exchangeToMono`/`exchangeToFlux` kiểm response body chưa được consume khi returned publisher hoàn tất và giải phóng để tránh leak. **Không dùng API raw response exchange rồi quên xử lý/release body**. Không trả `ClientResponse` ra ngoài callback để đọc body sau này khi callback contract không cho phép.

### Khi chủ động nhận DataBuffer từ WebClient

Nếu bạn dùng `response.bodyToFlux(DataBuffer.class)`, consumer raw có responsibility tương ứng:

- Nếu chỉ đọc/sao chép buffer vào DTO, release sau khi đọc.
- Nếu relay sang `ServerHttpResponse.writeWith`, transfer ownership theo contract, **không release trên nhánh forward**.
- Nếu filter bỏ một buffer hoặc cancel, giải phóng những buffers còn thuộc ownership của mình.
- Đừng đưa cùng một `Flux<DataBuffer>` cold tới hai subscriptions không chủ ý; một response network body không phải collection repeatable.

Trong một HTTP proxy, ngoài reference count còn cần propagate backpressure, status/headers, cancel, timeout, kiểm hop-by-hop headers và request size limits. Không biến nó thành `collectList` unbounded.

## 17. HTTP response streaming: transfer ownership đúng cách

Một controller có thể trả `Mono<Void>` và viết raw buffers:

```java
@GetMapping("/download")
public Mono<Void> download(ServerHttpResponse response) {
    response.getHeaders()
        .setContentType(MediaType.APPLICATION_OCTET_STREAM);

    Flux<DataBuffer> buffers = Flux.defer(() ->
        Flux.just("alpha\n", "beta\n")
            .map(text -> response.bufferFactory().wrap(
                text.getBytes(StandardCharsets.UTF_8))));

    return response.writeWith(buffers);
}
```

Đây là snippet, file runnable hoàn chỉnh có ở phần thực hành. Ở đây `response.writeWith` là owner cuối theo HTTP server; **không gắn `.doOnNext(DataBufferUtils::release)`** lên buffers. `Flux.defer` bảo đảm mỗi subscription tạo pipeline/source mới, nhưng controller handler thường đã được gọi riêng cho mỗi HTTP request; không coi defer là cách sửa mọi vấn đề ownership.

### Khi nào có thể return Flux<DataBuffer> trực tiếp?

Trong annotated WebFlux controller có thể trả kiểu reactive body khi handler/codec hỗ trợ; song `ServerHttpResponse.writeWith` minh họa rõ ownership. Functional handler cũng có thể dùng `ServerResponse.ok().body(bufferFlux, DataBuffer.class)`. Dù chọn cách nào, cần phân biệt producer tạo buffers, HTTP writer consume và operator nào có thể discard.

Không dùng `Flux<DataBuffer>.cache()` theo thói quen: cache giữ references tới pooled buffers mà HTTP writer có thể đã release, dẫn đến dữ liệu không hợp lệ ở subscriptions sau. Nếu cần cache nội dung, cache `byte[]`/immutable domain data với size+TTL policy và tạo DataBuffers **mới** cho mỗi response.

## 18. Ứng dụng Spring Boot 3 Java 17+ runnable

Tạo Maven project từ Spring Initializr với:

- **Java 17+**.
- **Spring Boot 3.x**.
- `spring-boot-starter-webflux` (Reactor, Netty, Jackson).
- `spring-boot-starter-test` (test scope).
- `reactor-test` (test scope nếu starter-test của phiên bản đang dùng không có).

Không thêm `spring-boot-starter-web` nếu muốn Boot tự chọn reactive application type khi chỉ có WebFlux starter. Ứng dụng này không cần database hoặc file upload thực tế. Nó có:

- `POST /api/buffers/crc32` nhận binary body `application/octet-stream`, gộp **tối đa 65.536 bytes**, tính CRC32 và trả JSON; **giải phóng joined result trong finally**.
- `GET /api/buffers/download` tạo hai buffers text và chuyển trực tiếp cho HTTP writer.
- `DataBufferLimitException` được ánh xạ thành **413 Payload Too Large** ở endpoint nhận dữ liệu.

Cấu trúc:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  BufferController.java
src/test/java/com/example/demo/
  BufferControllerTest.java
  BufferOwnershipTest.java
```

### 18.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 18.2. BufferController.java

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;
import java.util.zip.CRC32;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/buffers")
public class BufferController {

    private static final int MAX_BYTES = 64 * 1024;

    @PostMapping(path = "/crc32",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Digest> crc32(ServerHttpRequest request) {

        return DataBufferUtils.join(request.getBody(), MAX_BYTES)
            .map(joined -> {
                try {
                    // MAX_BYTES được áp dụng trước allocation byte[].
                    byte[] bytes = new byte[joined.readableByteCount()];
                    joined.read(bytes);

                    CRC32 crc = new CRC32();
                    crc.update(bytes);
                    return new Digest(bytes.length,
                        String.format("%08x", crc.getValue()));
                } finally {
                    // Chúng ta tiêu thụ joined result, nên tự release.
                    DataBufferUtils.release(joined);
                }
            })
            .switchIfEmpty(Mono.just(new Digest(0, "00000000")))
            .onErrorMap(DataBufferLimitException.class, ex ->
                new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "body too large", ex));
    }

    @GetMapping(path = "/download",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public Mono<Void> download(ServerHttpResponse response) {
        response.getHeaders()
            .setContentType(MediaType.APPLICATION_OCTET_STREAM);

        // Tạo buffers mới mỗi subscription.
        Flux<DataBuffer> payload = Flux.defer(() ->
            Flux.just("alpha\n", "beta\n")
                .map(text -> response.bufferFactory().wrap(
                    text.getBytes(StandardCharsets.UTF_8))));

        // Transfer ownership cho HTTP response writer.
        return response.writeWith(payload);
    }

    public record Digest(int length, String crc32) {}
}
```

**Phân tích ownership endpoint crc32:**

1. `ServerHttpRequest.getBody()` cung cấp `Flux<DataBuffer>`.
2. `DataBufferUtils.join(source, 65536)` tiếp nhận các components và quản lý accumulated buffers khi thành công hoặc cancel/error.
3. `map(joined -> ...)` là consumer của **joined result**, copy bytes sang heap có giới hạn để tính checksum.
4. `finally` release joined result đúng một lần, cả khi `CRC32`/read có lỗi.
5. Nếu tổng bytes vượt 65536, join báo `DataBufferLimitException`; accumulated buffers do join quản lý, **không có joined result để tự release thêm**.
6. Nếu request body rỗng và join complete empty, trả `Digest(0,"00000000")`.
7. `onErrorMap` chỉ đổi error thành response exception; không thay reference-count semantics.
8. Không gọi `block()` hoặc tự `subscribe()` trong controller.

**Phân tích download:** `response.writeWith(payload)` là consumer/owner cuối. Code không giữ buffer sau khi đã đưa vào publisher, không làm double release và không cache pooled memory. Payload rất nhỏ, nhưng pattern có thể mở rộng sang bounded streaming từ file/channel bằng `DataBufferUtils.read` với lifecycle rõ.

**Production caveat:** CRC32 chỉ là checksum phát hiện lỗi ngẫu nhiên, **không phải chữ ký mật mã, không chống giả mạo**. Nếu API cần integrity chống tấn công, dùng HMAC/sha-256 phù hợp và đừng tính checksum nhầm là authentication. Endpoint demo không bảo vệ/authenticate người gọi; production cần limits ở gateway/security nữa.

### 18.3. Khởi động

macOS/Linux:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Nếu không đặt `server.port`, app thường nghe port 8080. Không biên dịch các file Spring này bằng `javac BufferController.java` trần khi thiếu Maven/Gradle dependencies.

## 19. curl: kiểm tra CRC32, giới hạn và streaming

### Gửi 5 bytes "hello"

```bash
curl -i -X POST \
  'http://localhost:8080/api/buffers/crc32' \
  -H 'Content-Type: application/octet-stream' \
  -H 'Accept: application/json' \
  --data-binary 'hello'
```

Kỳ vọng HTTP **200**:

```json
{"length":5,"crc32":"3610a686"}
```

Đây là CRC32 của 5 byte UTF-8 ASCII `hello` (không có newline). Nếu dùng `echo hello | curl --data-binary @-`, stdin có thể thêm newline và CRC32/length khác. Dùng `printf 'hello'` hoặc literal `--data-binary 'hello'` để có output trên.

### Gửi body rỗng

```bash
curl -i -X POST \
  'http://localhost:8080/api/buffers/crc32' \
  -H 'Content-Type: application/octet-stream' \
  --data-binary ''
```

Kỳ vọng JSON `{"length":0,"crc32":"00000000"}` nếu HTTP body được nhận rỗng đúng như demo. Không gửi Content-Type có thể không match endpoint trước khi code kiểm body.

### Body vượt 64 KiB

Không cần gửi hàng MB/GB. Trên máy local, dùng script tạo đúng 65.537 bytes:

```bash
python -c "import sys; sys.stdout.buffer.write(b'x' * 65537)" \
  | curl -sS -i -X POST \
      'http://localhost:8080/api/buffers/crc32' \
      -H 'Content-Type: application/octet-stream' \
      --data-binary @-
```

Kỳ vọng HTTP **413 Payload Too Large** từ `DataBufferLimitException` được map tại controller nếu request được xử lý đến join. Gateway/server có thể giới hạn request sớm hơn. Không gửi payload lớn vào server ngoài môi trường test có quyền.

### Download raw binary stream

```bash
curl -i 'http://localhost:8080/api/buffers/download'
```

HTTP body chính xác (UTF-8, hai newline):

```text
alpha
beta
```

Server có thể chunk hoặc thêm transfer headers; **không** kết luận hai `DataBuffer` luôn là hai TCP packets. Headers tự động có thể thay đổi theo web server. Không dùng `Content-Length` hardcode nếu response streaming chưa tính độ dài.

## 20. WebTestClient kiểm HTTP endpoint

Tệp `src/test/java/com/example/demo/BufferControllerTest.java`:

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BufferControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void crc32OfHelloHasExpectedLengthAndHex() {
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);

        client.post().uri("/api/buffers/crc32")
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(bytes)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.length").isEqualTo(5)
            .jsonPath("$.crc32").isEqualTo("3610a686");
    }

    @Test
    void tooLargeBodyBecomes413() {
        byte[] bytes = new byte[65537];

        client.post().uri("/api/buffers/crc32")
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue(bytes)
            .exchange()
            .expectStatus().isEqualTo(413);
    }

    @Test
    void downloadContainsExpectedBytes() {
        byte[] expected =
            "alpha\nbeta\n".getBytes(StandardCharsets.UTF_8);

        client.get().uri("/api/buffers/download")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_OCTET_STREAM)
            .expectBody()
            .consumeWith(result ->
                assertArrayEquals(expected, result.getResponseBody()));
    }
}
```

Chạy:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

Các bài test là **source mẫu** với Boot 3/WebFlux test dependencies, không phải tuyên bố đã chạy trên repository người dùng. `WebTestClient` đi qua WebFlux HTTP server khi dùng RANDOM_PORT; tuy nhiên không tự động mô phỏng reverse proxy, client disconnect hay mọi chế độ leak detection Netty.

**Điểm đáng chú ý:** Việc assert HTTP 200/413 và bytes đúng **không chứng minh** native reference count trong mọi path đã về 0. Cần thêm unit test pooled buffers, tests cancellation và soak/load test có leak detection.

## 21. Test pooled ownership bằng NettyDataBufferFactory

Spring Boot WebFlux mặc định thường dùng Reactor Netty và có Netty `ByteBufAllocator`. Tệp `src/test/java/com/example/demo/BufferOwnershipTest.java`:

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import io.netty.buffer.PooledByteBufAllocator;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.NettyDataBuffer;
import org.springframework.core.io.buffer.NettyDataBufferFactory;

import static org.junit.jupiter.api.Assertions.*;

class BufferOwnershipTest {

    @Test
    void retainedBufferNeedsMatchingReleases() {
        NettyDataBufferFactory factory =
            new NettyDataBufferFactory(
                PooledByteBufAllocator.DEFAULT);

        NettyDataBuffer buffer = factory.allocateBuffer(32);
        buffer.write("ok".getBytes(StandardCharsets.UTF_8));

        assertTrue(buffer.isAllocated());

        DataBufferUtils.retain(buffer);   // +1 reference
        DataBufferUtils.release(buffer);  // Release đầu.
        assertTrue(buffer.isAllocated()); // Vẫn còn ref thứ hai.

        DataBufferUtils.release(buffer);  // Release cuối.
        assertFalse(buffer.isAllocated());
    }

    @Test
    void joinedBufferCanBeReleasedAsOneUnit() {
        NettyDataBufferFactory factory =
            new NettyDataBufferFactory(
                PooledByteBufAllocator.DEFAULT);

        NettyDataBuffer a = factory.allocateBuffer(8);
        NettyDataBuffer b = factory.allocateBuffer(8);
        a.write(new byte[]{1, 2});
        b.write(new byte[]{3, 4});

        // join thuộc quyền quản lý các buffers thành phần.
        var joined = DataBufferUtils.join(
            reactor.core.publisher.Flux.just(a, b),
            32).block();

        assertNotNull(joined);
        try {
            byte[] bytes = new byte[joined.readableByteCount()];
            joined.read(bytes);
            assertArrayEquals(
                new byte[]{1, 2, 3, 4}, bytes);
        } finally {
            DataBufferUtils.release(joined);
        }
        // Không gọi release(a) và release(b) thêm.
    }
}
```

**Lưu ý bản chất của test:**

- Netty `PooledByteBufAllocator.DEFAULT` cần Netty trên classpath. `spring-boot-starter-webflux` với Reactor Netty cung cấp Netty 4 dependency trong Boot 3 thông thường, nhưng nếu ứng dụng đổi server stack thì hãy khai báo đúng test dependency.
- Test thứ nhất minh họa retain/release hai ownership references và `isAllocated`. Tuy nhiên code production không nên gọi release hai lần vô điều kiện trên buffer không biết đã retain hay chưa.
- Test thứ hai dùng join, release **joined result duy nhất**, không release a/b nữa. Nếu join fail trước khi tạo result, contract join quản lý accumulated buffers; trong test nâng cao cần kiểm các nhánh error/cancel.
- `block()` chỉ ở JUnit test thread nhằm lấy joined result, **không** trong HTTP event loop.
- Không dùng `isAllocated` như một phép đồng bộ trong shared mutable/concurrent code. Nó chỉ kiểm trạng thái tại thời điểm đọc.

Nếu cần chứng minh leak-free thật, bật Netty leak detector trong test/staging và chạy tải/cancel; pass hai unit tests không đủ bao quát mọi race.

## 22. JDK 17 độc lập: mô phỏng ref-counting ownership

Không cần Spring dependencies cho mô hình khái niệm nhỏ này. Tệp `ReferenceOwnershipDemo.java`:

```java
public class ReferenceOwnershipDemo {

    static final class Lease {
        private int references = 1;

        synchronized void retain() {
            if (references == 0) {
                throw new IllegalStateException("already released");
            }
            references++;
        }

        synchronized void release() {
            if (references == 0) {
                throw new IllegalStateException("double release");
            }
            references--;
        }

        synchronized int count() {
            return references;
        }
    }

    public static void main(String[] args) {
        Lease lease = new Lease();

        lease.retain(); // Chủ B giữ thêm.
        System.out.println("after retain=" + lease.count());

        lease.release(); // Chủ A đã xong.
        System.out.println("after A=" + lease.count());

        lease.release(); // Chủ B đã xong.
        System.out.println("after B=" + lease.count());
    }
}
```

Biên dịch và chạy:

```bash
javac ReferenceOwnershipDemo.java
java ReferenceOwnershipDemo
```

Stdout **chính xác**:

```text
after retain=2
after A=1
after B=0
```

Đây **không phải** implementation Netty, PooledDataBuffer hay thread-safe memory allocator thực tế. Nó chỉ diễn tả luật ownership balance dễ nhớ; code Spring thực phải dùng `DataBufferUtils.retain/release` và tuân theo bên đã bàn giao/consume buffers.

## 23. DataBufferLimitException và giới hạn tài nguyên

Vì sao giới hạn cực quan trọng:

```text
1 request upload      10 MB
100 requests in-flight
------------------------
~1 GB payload nếu gom toàn bộ cùng lúc
(chưa tính objects, codec state, network queues, buffers copy)
```

`DataBufferUtils.join(source, maxByteCount)` đặt giới hạn tại **aggregation cụ thể**. Với default codecs, property `spring.codec.max-in-memory-size` của Spring Boot có thể kiểm giới hạn in-memory decoding/aggregation tùy codec/framework version. Không suy rằng một property duy nhất bao phủ mọi low-level custom buffer handling, multipart streaming, HTTP server connection quota và gateway request size.

Thực hành:

- Đặt giới hạn request body **trước khi allocation toàn bộ payload**.
- Dùng `maxByteCount` ở mọi aggregation raw.
- Khi parse JSON, dùng decoder/validation với limit phù hợp; không tự collect unbounded.
- Khi xử lý multipart, có hạn mức total size, mỗi file, mỗi field, số parts, disk spill/quarantine.
- Giới hạn số đồng thời uploads/downloads/connections và tổng native memory budget.
- Chọn chunk size hợp lý, không dùng một buffer 1 GB rồi gọi đó là streaming.
- Streaming nhiều chunk không có nghĩa ứng dụng không buffer; `collectList`/`join`/`cache` có thể biến nó thành aggregation lớn.
- Nếu cần lưu file rất lớn, stream vào storage thay vì giữ cả file trong heap.
- Tách long streams khỏi request/worker capacity khác khi cần.

**413 Payload Too Large** là hợp đồng HTTP thường phù hợp với body vượt quota; nếu error đã xảy ra sau khi response commit, không thể luôn gửi 413 mới.

## 24. Cancellation, error và race trong stream

Reactive Streams có ba kiểu kết thúc thường gặp:

```text
onComplete()   -> nguồn kết thúc thành công
onError(e)     -> nguồn kết thúc do lỗi
cancel()       -> subscriber không còn muốn nhận thêm
```

Các trách nhiệm:

| Trường hợp | Điều cần giải phóng |
| --- | --- |
| Error khi đang đọc một DataBuffer | Buffer local đã nhận quyền sở hữu |
| Cancel khi join đang tích lũy | Join tự release accumulated buffers theo contract |
| Cancel khi operator có internal queue | Discard hook và operator semantics |
| HTTP client disconnect sau một số chunks | Những buffers pending có ownership ở writer/pipeline; cleanup producer |
| File write hỏng sau khi mở channel | Channel/file resources và buffers không chuyển quyền |
| Encoder serialization lỗi trước khi publish | Buffer mới tạo, chưa bàn giao |
| Retry tạo subscription mới | Không tái dùng pooled buffers đã được release từ lần trước |

Không release một buffer trong cả `doOnError` lẫn `doFinally` nếu hai nhánh cùng nhắm một reference. `doFinally` có thể chạy sau downstream terminal; nếu dùng nó cho cleanup cần tránh race/double-free và bảo đảm không ai đang đọc buffer nữa.

Nếu client disconnect, application không được giả định phát tiếp `onNext` vô hạn vào queue. Dùng bounded queues/backpressure, hủy file read/remote subscriptions theo cancellation và không lưu pooled buffers trong static caches.

## 25. Leak detection với Netty và troubleshooting

Các dấu hiệu có thể gặp:

- Native/direct memory tăng liên tục dù số active requests ổn định.
- `OutOfDirectMemoryError` hoặc lỗi liên quan Netty pooled allocator.
- Netty leak detector ghi cảnh báo kiểu `LEAK: ByteBuf.release() was not called...`.
- HTTP streaming trả bytes sai hoặc `IllegalReferenceCountException` khi buffer đã release quá sớm.
- Heap dump không giải thích hết native memory consumption.
- Tăng `-Xmx` không giải quyết được leak native/direct buffers và còn có thể làm memory limit của container chật hơn.

Trong môi trường **test/staging có kiểm soát**, Netty có property `-Dio.netty.leakDetection.level=advanced` hoặc `paranoid` để thu thập bằng chứng, nhưng mức cao có overhead lớn; không bật `paranoid` trên production bận rộn mà thiếu đánh giá tác động. Cú pháp/env var cụ thể phụ thuộc cách JVM/server được khởi động.

Checklist điều tra:

1. Xác nhận backend dùng pooled buffer (Reactor Netty, Jetty hay custom implementation).
2. Tìm những nơi nhận trực tiếp `Flux<DataBuffer>`.
3. Vẽ ownership mỗi buffer: ai allocate, ai consume, ai release, ai transfer.
4. Kiểm branches `filter`/`skip`/`take`/`timeout`/`onErrorResume`/`retry`.
5. Tìm `collectList`/`cache`/shared state giữ buffer.
6. Kiểm encoder lỗi trước bàn giao.
7. Kiểm raw `DataBufferUtils.write` overload có tự release không, channel có đóng không.
8. Kiểm `WebClient` raw response body có được consume/relay/release không.
9. Tạo test cancellation/disconnect, malformed body, quota breach và streaming failure.
10. Quan sát native memory, Netty allocator metrics, request concurrency và P99 latency.
11. So sánh performance trước/sau thay đổi, không gọi `release` bừa bãi để làm im leak detector.
12. Nếu dùng `touch` hints, không ghi dữ liệu bí mật vào hint.

**Không dùng `System.gc()` hoặc tăng heap làm giải pháp cho leak reference-counted.** Phải sửa đường ownership.

## 26. Tình huống thực tế và cách chọn pattern

### 26.1. JSON REST CRUD bình thường

Controller nhận `@RequestBody Mono<Dto>`, trả `Mono<ResponseEntity<Dto>>`. **Không cần** trực tiếp quản lý `DataBuffer`. Spring codecs/HTTP writers nắm responsibility.

### 26.2. Tính hash/checksum request binary nhỏ

Dùng bounded `DataBufferUtils.join`, copy bytes có giới hạn, release joined result trong `finally`; trả DTO. Đây là pattern của sample app.

### 26.3. Stream file lớn về client

Ưu tiên `Resource` hoặc `DataBufferUtils.read`/`ServerResponse.body` phù hợp, không join cả file. Khi chuyển `Flux<DataBuffer>` thẳng cho response writer, owner downstream cuối release; code không vừa forward vừa release.

### 26.4. Proxy/relay upstream WebClient body

Đọc raw `Flux<DataBuffer>` chỉ nếu thực sự cần; forward ownership tới response writer và xử lý header/status/backpressure/cancel đúng. Không cache raw buffers, không dual-subscribe và không leak khi target/client đóng.

### 26.5. Lọc một vài mảnh

Nếu filter bỏ mảnh, dùng discard hook. Nếu mảnh giữ lại được chuyển xuống downstream, **không release mảnh giữ lại trước khi downstream dùng**.

### 26.6. Chuyển thành DTO/String

Nếu code là consumer cuối của raw DataBuffer, release sau khi tạo DTO trong `try/finally`. Nếu dùng standard codecs, không chèn release thêm.

### 26.7. Gộp nhiều mảnh rồi chia nhỏ lại

`join` có thể tạo composite giữ references. Nếu split thành retained views cần hiểu `retainedSlice`/Netty reference semantics: ai giữ view, ai release composite, có share underlying memory không. Tránh thiết kế này trừ khi cần thiết; dùng copy vào bounded immutable bytes cho dữ liệu sống lâu.

### 26.8. Logging/filter request body

Đây là nơi leak rất phổ biến. Một `WebFilter` đọc raw body để log rồi không tái tạo/decorate body đúng sẽ khiến controller downstream không đọc được hoặc bị đọc hai lần. Nếu bắt buộc inspect payload, phải có size cap, redact secrets, replay/decorator semantics và ownership/cancel tests; không copy ví dụ debug body logging lên production vô điều kiện.

## 27. Những lỗi phổ biến

1. **Nhìn DataBuffer như byte[] GC-managed:** pooled reference cần release.
2. **Không phân biệt heap/direct memory:** leak native có thể không xuất hiện trong heap metric.
3. **Đọc buffer rồi không release:** local consumer cuối tạo leak.
4. **Release rồi chuyển buffer cho `writeWith`:** use-after-release.
5. **Vừa release buffer trong controller vừa để writer release:** double-release.
6. **Retain nhưng không có release tương ứng:** leak reference.
7. **Release mọi buffer ở doFinally bất kể đã chuyển downstream:** ownership sai/race.
8. **Tin doOnDiscard release mọi onNext:** nó chỉ xử lý discarded buffers theo operator support.
9. **Dùng filter/drop trên pooled source mà quên doOnDiscard:** leak dropped pieces.
10. **Dùng `join` rồi release từng component và joined result:** double-release.
11. **Dùng `join` mà không release joined result:** leak aggregate.
12. **Gộp body không maxByteCount:** nguy cơ memory exhaustion.
13. **Tin `maxByteCount` ở một join là tổng quota hệ thống:** vẫn cần concurrency/server/gateway limits.
14. **Tin `DataBufferUtils.write(OutputStream)` tự đóng stream/release buffers:** sai overload contract.
15. **Dùng blocking OutputStream trên Netty event loop:** thread starvation.
16. **Cache `Flux<DataBuffer>` pooled:** resubscription có thể thấy memory đã release.
17. **Subscribe raw WebClient body rồi quên consume/release:** leak response resources.
18. **Đọc request body hai lần trong filter/controller:** body thường không repeatable.
19. **Mutate `byte[]` sau khi wrap/bàn giao:** data corruption.
20. **Assume mọi DataBuffer đều pooled:** implementation quyết định; dùng helper portable.
21. **Assume mọi pooled buffer đều dùng same refCount numbers:** slices/composite có nuances.
22. **Lấy `isAllocated` rồi đọc trên thread khác không đồng bộ:** TOCTOU/race.
23. **Quên error path khi custom encoder allocate:** leak trên serialization failure.
24. **Quên cancel path trong long-lived streaming:** leak buffers/listeners.
25. **Dùng unbounded `collectList` cho file lớn:** đẩy byte buffers vào RAM.
26. **Dựa vào một happy-path HTTP test để tuyên bố leak-free:** cần pooled/cancel/error stress.
27. **Bật Netty leakDetection paranoid trên production bận:** overhead đáng kể.
28. **Tăng -Xmx để “sửa” off-heap leak:** chưa xử lý root cause.
29. **Dùng buffer shared giữa hai consumers mà không retain/copy:** double ownership sai.
30. **Gọi release hai lần vì tưởng release đầu trả false nghĩa chưa release:** return value không phải license release tùy tiện.
31. **Gọi retainedSlice mà quên lifetime của parent/shared memory:** unsafe refs.
32. **Không giới hạn file upload/multipart:** memory/disk exhaustion.
33. **Cho raw binary endpoint public không kiểm quota/auth:** dễ thành DoS.
34. **Coi CRC32 là chữ ký bảo mật:** không chống giả mạo.
35. **Coi một DataBuffer = một packet TCP:** transport có thể chia/gộp tùy flow control.
36. **Không phân biệt lỗi trước/sau response commit:** status không luôn sửa được.
37. **Bỏ Spring codecs để tự parse JSON từ raw ByteBuf không cần thiết:** phức tạp và dễ leak.

## 28. Checklist code review và production

### Ownership

- [ ] Có sơ đồ allocate → read/write → transfer/release cho mỗi raw DataBuffer?
- [ ] Consumer cuối của buffer có release trong success/error/cancel?
- [ ] Nếu chuyển buffer sang HTTP writer, code không release sớm?
- [ ] Mỗi `retain` có đúng một release ownership tương ứng?
- [ ] `join` chỉ release joined result, không double release components?
- [ ] Custom decoder/encoder có cleanup khi exception trước bàn giao?
- [ ] `doOnDiscard` đặt đúng operator/path khi có dropped buffers?
- [ ] Không dùng `cache`/share raw pooled buffers sống ngoài request?
- [ ] Không mutate underlying byte[] sau khi chuyển ownership?

### Giới hạn tài nguyên

- [ ] Mọi aggregation có maxByteCount/codec memory limit phù hợp?
- [ ] Có giới hạn số concurrent requests, uploads, stream connections?
- [ ] Có file size/part count/storage quota cho multipart?
- [ ] Blocking file/OutputStream work không chạy trên Netty event-loop?
- [ ] Body raw không bị consume lặp giữa WebFilter và controller?
- [ ] Xử lý disconnect/cancel và cleanup resource subscriptions?
- [ ] Response status và header được đặt trước commit?

### Kiểm thử và vận hành

- [ ] Unit test pooled retain/release và join composite?
- [ ] HTTP test kiểm bytes đúng, body rỗng, vượt limit/413?
- [ ] Error path: malformed body, decoder lỗi, stream writer lỗi?
- [ ] Cancel/disconnect path: không còn pooled buffers/queued references?
- [ ] Quan sát native memory, allocator metrics, leak detector trong staging?
- [ ] Không log raw body/token/file data vì mục đích debug không kiểm soát?
- [ ] Tắt leak-debug mức overhead cao khi vận hành bình thường trừ khi có kế hoạch?

## 29. Câu hỏi tự kiểm tra

**1.** `DataBuffer` có phải luôn ở Java heap không?

**Đáp án:** Không. Nó có thể bọc direct/native pooled buffers, nhất là với Netty.

**2.** Vì sao `DataBufferUtils.release(buffer)` cần được gọi trong custom decoder?

**Đáp án:** Decoder là consumer cuối của raw buffer khi đã tạo DTO/String và không forward nó nữa; pooled memory cần được trả.

**3.** Khi nào không nên release trong controller?

**Đáp án:** Khi đã chuyển ownership của buffer cho `response.writeWith`/HTTP writer hoặc một consumer được giao trách nhiệm cuối.

**4.** Retain làm gì?

**Đáp án:** Thêm một reference nếu buffer pooled, cho phép chủ sở hữu mới giữ buffer sống đến khi release riêng.

**5.** Gọi retain một lần rồi chỉ release một lần có sao không?

**Đáp án:** Nếu đã có một initial ownership và không ai release reference còn lại, refCount > 0 và leak.

**6.** `doOnDiscard` giải phóng những buffer nào?

**Đáp án:** Những phần tử DataBuffer bị các operators có hỗ trợ discard bỏ đi tại pipeline boundary, không tự release mọi buffer đã forward.

**7.** `DataBufferUtils.join` có luôn copy dữ liệu không?

**Đáp án:** Không. Nó có thể tạo zero-copy composite; ownership của thành phần nằm trong aggregate theo contract.

**8.** Sau khi join hoàn tất, release gì?

**Đáp án:** Release joined result khi tiêu thụ xong; không release lại từng component đã đưa vào join.

**9.** Vì sao cần `join(source, maxByteCount)`?

**Đáp án:** Giới hạn tổng bytes khi aggregation, tránh gom body vô hạn; vượt limit phát DataBufferLimitException.

**10.** `DataBufferUtils.write(source, OutputStream)` có tự release input DataBuffers không?

**Đáp án:** Không. Returned Flux phát các buffers sau write; caller cần giải phóng theo contract và quản lý đóng OutputStream.

**11.** `response.writeWith(flux)` có cần `doOnNext(DataBufferUtils::release)` không?

**Đáp án:** Không nên. Writer là consumer cuối; release trước writer có thể làm dữ liệu bị thu hồi quá sớm.

**12.** Heap ít dùng nhưng native memory tăng đều có thể do đâu?

**Đáp án:** Pooled/direct buffer leak, shared allocator pressure, outstanding connections hoặc các native resources khác; cần metrics/leak detector và phân tích ownership.

**13.** Vì sao `doFinally` không thay release mỗi buffer?

**Đáp án:** doFinally quan sát một subscription kết thúc/cancel, không tự được gọi trên từng buffer; các buffers có thể đã chuyển ownership cho downstream.

**14.** CRC32 có chứng minh dữ liệu do một bên đáng tin gửi không?

**Đáp án:** Không. Nó chỉ checksum không kháng giả mạo; nếu cần authentication/integrity dùng HMAC/signature.

**15.** Test HTTP CRC32 PASS có đủ kết luận không có leak không?

**Đáp án:** Không. Cần test pooled reference counts, error, cancellation và stress/leak detector.

## 30. Nguồn tham khảo

- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework 6.2.4 — `DataBufferUtils` Javadoc, `join`/`release`/`write`: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
- Spring Framework 6.2.4 — `PooledDataBuffer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/PooledDataBuffer.html
- Spring Framework 6.2.4 — `DataBufferFactory` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/DataBufferFactory.html
- Spring Framework 6.2.4 — `DataBuffer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/DataBuffer.html
- Spring Framework 6.2.4 — `DataBufferLimitException`: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/core/io/buffer/DataBufferLimitException.html
- Spring Framework — WebFlux annotated controllers and request body: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework — WebClient response exchange/cleanup: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework — WebFlux WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Project Reactor — Handling discarded elements: https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html
- Project Reactor — Error handling and cancellation: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Netty — ByteBuf reference counting: https://netty.io/wiki/reference-counted-objects.html
- Netty — Resource leak detector: https://netty.io/wiki/reference-counted-objects.html#troubleshooting-buffer-leaks
