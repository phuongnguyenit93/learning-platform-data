# Bộ nhớ heap, direct memory và bộ đệm đọc hoặc ghi HTTP

## 1. Bối cảnh: hết bộ nhớ dù heap chưa đầy

Giả sử một Spring Boot service tiếp nhận tệp, giải mã JSON, gọi downstream bằng `WebClient` và trả file HTTP. Dashboard báo **Java heap chỉ dùng khoảng 50%**, nhưng container bị OOMKilled hoặc server ghi lỗi:

~~~text
java.lang.OutOfMemoryError: Cannot reserve ... bytes of direct buffer memory
~~~

Một service khác không gặp lỗi direct memory nhưng sau khi tăng giới hạn JSON từ 256 KiB lên 50 MiB thì GC pause, latency và `java.lang.OutOfMemoryError: Java heap space` tăng rõ rệt. Một ứng dụng thứ ba có `Flux<DataBuffer>` “streaming” nhưng lại dùng `collectList()`, `DataBufferUtils.join()` không giới hạn hoặc giữ `ByteBuf` trong cache mà không release, khiến memory tăng theo số clients.

Để giải thích, ta phải tách **heap objects**, **native/off-heap/direct memory**, **bộ đệm do transport sở hữu**, **bộ đệm do HTTP codec giữ để gom message**, và **bộ đệm tại kernel/proxy**. Các loại đó có quan hệ nhưng không cùng một chỉ số và không được quản lý bởi một cấu hình duy nhất.

Bài học thuộc mục **Hiệu năng và giới hạn** trong Spring Boot web runtime. Sau khi học, bạn có thể:

1. Phân biệt `-Xmx`, `-XX:MaxDirectMemorySize`, process RSS/cgroup memory, Java NIO direct buffers, Netty pooled ByteBuf, socket buffers.
2. Phân tích đường đi của HTTP request/response từ socket → decoder → `DataBuffer` → JSON/multipart → controller và chiều ngược lại.
3. Hiểu vì sao `spring.http.codecs.max-in-memory-size` không phải giới hạn kích thước HTTP body toàn cục.
4. Giữ ownership của pooled `DataBuffer` và giải phóng qua `DataBufferUtils.release` khi **tự tiêu thụ** buffer.
5. So sánh aggregate vs streaming, backpressure, slow consumer, codec limits, multipart disk spill và bảo vệ hệ thống khỏi uploads/downloads lớn.
6. Chạy demo **Spring Boot 3.5.x + Java 17+ + WebFlux** với upload SHA-256 theo luồng, response download nhiều chunks, JSON codec limit và quan sát JVM memory.
7. Dùng Micrometer, Reactor Netty allocator metrics, `jcmd`/Native Memory Tracking và tải thử để tìm heap/direct memory pressure mà không mở rộng memory vô kiểm soát.

> **Phạm vi phiên bản:** Các ví dụ thực hành dùng Spring Boot **3.5.x**, Spring Framework **6.2.x** và Java **17+**. Boot 3.5 dùng property **`spring.http.codecs.max-in-memory-size`**. Ở các phiên bản Boot trước, cấu hình thường mang tên `spring.codec.max-in-memory-size`; không copy lẫn giữa versions. Với Boot 4.x cần đọc tài liệu property/starter tương ứng. Không giả định default, allocator và metric names giống nhau ở mọi container/server.

## 2. Bản đồ bộ nhớ của một process Spring Boot

~~~text
Container / host physical memory, cgroup quota
|
+-- Java process address space / RSS
|   |
|   +-- Java HEAP (giới hạn tối đa bởi -Xmx)
|   |   +-- Java objects: DTO, String, byte[], List, Map
|   |   +-- Jackson-decoded JSON object graph
|   |   +-- queues/cache, metadata, Java wrappers của native buffers
|   |
|   +-- JVM non-heap/native memory
|   |   +-- Metaspace, class metadata
|   |   +-- JIT code cache, GC structures
|   |   +-- Thread stacks
|   |   +-- Java NIO direct ByteBuffer allocations
|   |   +-- Native allocations / Netty pooled direct memory
|   |   +-- TLS/native libraries, mmap và các thành phần khác
|   |
|   +-- Memory-mapped files / shared libraries / page residency
|
+-- OS kernel memory (socket send/receive buffers, TCP queues)
+-- Sidecars / reverse proxies nếu chung Pod/cgroup liên quan
~~~

Sơ đồ là mô hình vận hành, không phải phân chia **tách biệt tuyệt đối** của từng accounting system. Heap có thể chưa commit tới `-Xmx`. Bộ nhớ reserved và committed khác nhau; RSS không bằng tổng mọi “max”. Một số loại native memory không được JVM NMT theo dõi đầy đủ. Kernel socket buffers có cách hạch toán khác theo Linux/cgroup version.

### Các giới hạn quan trọng

| Giới hạn hoặc thống kê | Ý nghĩa | Không có nghĩa |
|---|---|---|
| `-Xmx512m` | Heap capacity tối đa khoảng 512 MiB | **Không** có nghĩa toàn process chỉ dùng ≤512 MiB |
| `-Xms256m` | Thiết lập initial/min heap sizing của JVM | Không tự giới hạn direct/native memory |
| `-XX:MaxDirectMemorySize=256m` | Giới hạn cho một lớp **Java NIO direct-buffer allocations** theo JVM | Không phải hard cap cho **mọi** off-heap/native allocations |
| Container `memory.max`/memory limit | Ngân sách memory được cgroup áp dụng | Không tự phân phối heap/direct/native an toàn |
| Micrometer `jvm.memory.used{area=heap}` | Heap sử dụng tại lúc lấy mẫu | Không thể hiện mọi direct Netty allocations |
| Java `BufferPoolMXBean` direct | Bộ nhớ/counters được Java NIO direct buffer pool thống kê | Không nhất thiết bao quát native buffers do Netty cấp phát riêng |
| Reactor Netty `used.direct.memory` | Bộ nhớ direct allocator reserved theo Netty meter | Không đồng nghĩa toàn process RSS hoặc JVM heap |

**Sai lầm thường gặp:** cấp memory limit container là 768 MiB, đặt `-Xmx768m`, rồi ngạc nhiên khi pod OOMKilled. Process còn cần direct/native memory, metaspace, code cache, thread stacks và phần overhead khác. Cần dành **headroom**, kiểm chứng bằng tải thật thay vì cộng các giá trị max như một phép tính chính xác.

## 3. Java heap là gì? Dữ liệu HTTP nào hay nằm trên heap?

Heap quản lý các Java objects; garbage collector có thể thu hồi những objects không còn reachable. Trong ứng dụng web:

- `String`, `byte[]`, `Map`, records/DTOs từ JSON decoding thường nằm trên heap.
- Một request JSON được parse có thể tạo **nhiều objects hơn kích thước JSON gốc**: strings, collections, indexes, boxing, references, object headers.
- `@RequestBody byte[]` thường đòi một mảng byte chứa body đã gom; khi chuyển tiếp thành `String`, Base64 hoặc tree JSON, hệ thống có thể giữ **nhiều bản sao đồng thời**.
- Một response được serialize thành `byte[]`/`String` lớn trước khi gửi cũng giữ bộ nhớ trên heap.
- A cache/list tích tụ unbounded có thể khiến `-Xmx` đầy dù sockets/buffers direct đang ổn.

Ví dụ bộ nhớ minh họa:

~~~text
Request HTTP body trên wire: 2 MiB JSON
   |
   +-- inbound network DataBuffers (direct/heap tùy runtime)
   +-- codec aggregation buffer(s)
   +-- Java DTO graph và Strings
   +-- object validation / business copies
   +-- response serialization buffer(s)
~~~

Không thể mặc định `2 MiB body = 2 MiB heap`. Số copy và object expansion phụ thuộc converter, shape JSON, JVM, codec, compress/decompress và độ đồng thời. JSON chứa hàng trăm nghìn phần tử nhỏ thường có overhead cao hơn một blob nhị phân cùng số bytes.

### Heap OOM và GC pressure

Dấu hiệu:
- `java.lang.OutOfMemoryError: Java heap space`.
- Heap used gần `-Xmx`, GC chạy thường xuyên nhưng reclaim ít.
- Allocation rate tăng khi tạo/parse bodies lớn.
- Endpoint `collectList()` giữ toàn bộ dữ liệu.
- Jackson deserialization tạo object graph khổng lồ.
- Retained heap tăng sau request hoàn thành do cache, static collections hoặc subscriber references.

Phải phân biệt **GC pressure do allocation throughput** (có thể phục hồi sau GC) và **memory leak do giữ references** (old-gen usage tăng sau GC và heap dump có retainer rõ).

## 4. Direct memory là gì? Java NIO ByteBuffer.allocateDirect

Java NIO có hai kiểu buffer nền tảng:

~~~java
import java.nio.ByteBuffer;

ByteBuffer heap = ByteBuffer.allocate(4096);
ByteBuffer direct = ByteBuffer.allocateDirect(4096);

System.out.println(heap.isDirect());   // false
System.out.println(direct.isDirect()); // true
~~~

Đây là một **fragment Java**; có thể đặt trong `main` của bất kỳ class Java 17. `ByteBuffer.allocate` dùng Java heap backing storage; `allocateDirect` yêu cầu buffer mà JVM có thể sử dụng hiệu quả hơn cho một số tác vụ native I/O.

Direct buffer vẫn có **Java object wrapper trên heap**, nhưng vùng lưu bytes có thể ở **native/off-heap memory**. Direct không nghĩa “tự động zero-copy mọi lúc”; thực tế còn phụ thuộc API, kernel, TLS, allocator, OS, scatter/gather I/O và application transformations. Việc allocation và giải phóng direct buffers có chi phí, vì vậy network frameworks thường dùng **pooling**.

### Phân biệt cấp phát và thu hồi

- Heap `byte[]` có lifecycle theo reachability và GC.
- Java NIO direct buffer có native storage; quá trình thu hồi thường gắn với cleaner/GC lifecycle, không nên dựa vào “GC sẽ chạy ngay” để đáp ứng peak traffic.
- Netty pooled `ByteBuf` có **reference counting**: cần release khi không dùng. Pool có thể giữ reserved memory để tái sử dụng sau khi buffer đã được trả về pool.
- Java NIO `-XX:MaxDirectMemorySize` không thể được xem là quota duy nhất cho mọi native allocation từ một library như Netty; dùng cùng với cgroup/RSS và allocator metrics để quan sát.

Direct memory đặc biệt hữu ích cho network I/O, nhưng **dùng direct mọi nơi không phải tối ưu tuyệt đối**. Các arrays nhỏ, JSON business objects hoặc dữ liệu chỉ xử lý trong Java heap thường không hưởng lợi đủ lớn từ direct allocations.

## 5. Netty ByteBuf, heap và pooled direct buffers

Spring WebFlux chạy trên Reactor Netty thường đi qua Netty `ByteBuf`:

~~~text
NIC/TCP socket -> Netty ChannelPipeline -> ByteBuf
        |
        +--> Netty pooled allocator
        |       +--> heap ByteBuf
        |       +--> direct ByteBuf
        |
        +--> Spring NettyDataBuffer (DataBuffer abstraction)
        |
        +--> HTTP reader/codec / WebFlux handler
~~~

`ByteBuf` không giống `java.nio.ByteBuffer` về ownership. Netty có pooled/unpooled, direct/heap, composite buffers, reader/writer indexes và refcount.

### Reserved vs active allocator memory

Reactor Netty có metrics:
- `reactor.netty.bytebuf.allocator.used.direct.memory`: số bytes **reserved** bởi direct allocator.
- `reactor.netty.bytebuf.allocator.active.direct.memory`: số bytes **in-use** theo pooled allocator.
- Tương tự `used.heap.memory` và `active.heap.memory`.
- `direct.arenas`, `heap.arenas`, `threadlocal.caches` và các metrics pool khác khi có.

Ví dụ sau một đợt tải:
- Active direct memory đã giảm về thấp nhưng **used/reserved** vẫn cao: pool có thể giữ các chunks/arenas để tái sử dụng, **chưa đủ chứng minh leak**.
- Active direct memory **cứ tăng sau khi requests đã hoàn thành**, không giảm sau warm-up và trong một tải lặp được: nghi có buffers chưa release hoặc long-lived streams, nhưng cần kiểm tra requests thực tế còn active và metrics.
- Cả active/used tăng vì connection concurrency tăng: có thể là nhu cầu bình thường của workload, không phải leak.

**Không so sánh trực tiếp** `used.direct.memory` với `-XX:MaxDirectMemorySize` rồi kết luận chính xác toàn bộ native footprint; cơ chế Netty native allocation và Java NIO limits cần được kiểm tra theo Netty/JDK version.

## 6. Bộ đệm HTTP nằm ở những đâu?

Một HTTP request body đi qua nhiều lớp:

~~~text
Client sends bytes
    |
    v
[OS socket receive buffer]                  (kernel/network)
    |
    v
[Netty ByteBuf / servlet input buffer]      (transport)
    |
    v
[HTTP framing decoder]                      (headers/chunks/frames)
    |
    v
[Spring DataBuffer / InputStream]           (framework)
    |
    +--> [JSON decoder may aggregate input] (codec)
    +--> [Multipart parser: memory/disk]    (codec)
    +--> [Stream directly to sink/storage]  (application)
    |
    v
Controller / service
~~~

Response chiều ngược lại:

~~~text
Business data / file / Publisher<T>
    |
    v
[Serializer / DataBufferFactory]        (HTTP encoder)
    |
    v
[Netty channel outbound buffer]        (I/O queue)
    |
    v
[OS socket send buffer]                (kernel)
    |
    v
Proxy / CDN / client receive buffer
~~~

Một request không nhất thiết nằm trong **một** buffer duy nhất. HTTP/1.1 chunked transfer và HTTP/2 DATA frames là các cơ chế truyền/framing; chúng **không** bảo đảm ứng dụng sẽ không aggregate thành một JSON object lớn. Một client phát thành 100 HTTP chunks nhưng handler dùng `@RequestBody byte[]` vẫn có thể giữ toàn bộ decoded body.

### TCP socket buffers khác application buffers

- Kernel `SO_RCVBUF`/`SO_SNDBUF` kiểm soát vùng buffering ở TCP socket; OS có autotuning và accounting riêng.
- JVM/Netty inbound/outbound buffers tồn tại ở user space.
- Codec buffers dùng để parse/aggregate payload thành logical object.
- Reverse proxy cũng có các buffers riêng trong **process khác**.

Bởi vậy tăng hoặc giảm `server.netty.initial-buffer-size` không tương đương “đặt max size cho HTTP body”. Trong Boot 3.5, property đó là **kích thước buffer khởi đầu để decode HTTP request**, không phải quota cho multipart uploads hoặc JSON object size.

## 7. Spring MVC/Servlet và WebFlux/Reactive quản lý bộ đệm thế nào?

| Vấn đề | Spring MVC + Servlet | Spring WebFlux + Reactor Netty |
|---|---|---|
| I/O model thường gặp | Servlet blocking/async tùy endpoint | Reactive/non-blocking event loop |
| API body phổ biến | `HttpServletRequest.getInputStream()`, `@RequestBody` | `Flux<DataBuffer>`, `Mono<DTO>` |
| Bộ đệm transport | Tomcat/Jetty/Undertow implementation | Netty ByteBuf/direct allocator |
| JSON decode | `HttpMessageConverter` như Jackson | `HttpMessageReader`/Decoder |
| Limit codec | Converter/Servlet/container/application limits | `maxInMemorySize` và codec-specific limits |
| Multipart | `MultipartFile`, servlet multipart/temp files | `FilePart`, `PartEvent`, disk spill theo config |
| Download lớn | `StreamingResponseBody`, `Resource`/sendfile khi phù hợp | `Flux<DataBuffer>`, `DataBufferUtils.read`, `Resource` |
| Backpressure | Servlet async/output/client flow control riêng | Reactor demand + Netty channel backpressure |
| Ownership buffer | Thường abstracted dưới InputStream/response | Cần chú ý `DataBufferUtils.release` khi tự xử lý `DataBuffer` |
| Vấn đề thường gặp | Bị giữ servlet thread, copy byte[] lớn, async queues | Unbounded reactive queues, DataBuffer leak, block event loop |

**Không mặc định “MVC không dùng direct memory”**: Tomcat NIO/NIO2, Undertow hoặc TLS/native libraries vẫn có thể dùng native/direct buffers. Ngược lại, WebFlux vẫn tạo nhiều Java heap objects cho JSON và business data. Lựa chọn framework không xóa nhu cầu kiểm soát memory.

## 8. DataBuffer của Spring: abstraction và ownership

Spring Framework định nghĩa:
- `DataBufferFactory`: tạo hoặc wrap byte buffers.
- `DataBuffer`: đại diện một vùng bytes có read/write positions, có thể pooled.
- `PooledDataBuffer`: hỗ trợ refcount ownership.
- `DataBufferUtils`: các thao tác join, read, write, retain, release và utilities.

Khi dùng `@RequestBody Mono<MyDto>` hoặc trả `Mono<MyDto>`, codec chuẩn thường tự quản lý buffers theo lifecycle. Khi trực tiếp nhận `Flux<DataBuffer>` hoặc viết codec riêng, **ứng dụng bước vào vùng phải quản lý ownership**.

### Quy tắc “ai tiêu thụ thì ai giải phóng?”

- Nếu bạn **chỉ đọc** một DataBuffer inbound rồi biến nó thành checksum/counter, bạn phải release buffer sau khi đọc (nếu pooled).
- Nếu bạn **chuyển tiếp DataBuffer downstream để HTTP writer tiêu thụ**, **không release trước khi writer đọc xong**; writer chịu trách nhiệm release buffers được chuyển giao.
- Nếu bạn allocate DataBuffer mới mà chưa chuyển giao ownership vì serialization bị lỗi, phải release buffer đang sở hữu.
- Nếu bạn giữ buffer qua asynchronous boundary, cần `retain` khi có chia sẻ/giữ ownership và release tương ứng; ưu tiên **copy bytes có giới hạn** nếu logic phức tạp, tránh giữ pooled buffers lâu.
- Nếu operator bỏ/discard buffers khi filter, cancel, error hoặc prefetch, dùng `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` ở vị trí thích hợp.

### Reference counting trong pooled buffer

~~~text
Allocated pooled buffer: refCnt = 1
retain()                -> refCnt = 2
release()               -> refCnt = 1
release()               -> refCnt = 0 => có thể trở lại pool
release() thêm lần nữa  -> BUG, có thể IllegalReferenceCountException
~~~

Refcount là **logic ownership**, không đo bytes trực tiếp. `DataBufferUtils.release(DataBuffer)` là helper an toàn cho pooled vs non-pooled types: với non-pooled buffer nó có thể không cần thao tác. Nhưng **không có nghĩa gọi release nhiều lần là vô hại** trên pooled buffer.

### Vì sao direct buffers có thể rò rỉ?

Một `NettyDataBuffer` có thể giữ `ByteBuf` pooled. Nếu ứng dụng lấy data rồi quên release, reference count vẫn >0, allocator không thể tái sử dụng vùng đó. JVM GC có thể xóa Java wrapper nhưng không bù được một lỗi reference counting ở thời điểm cần giải phóng; Netty có leak detector để giúp phát hiện.

**Đừng giải quyết bằng cách gọi `System.gc()` trong request handler.** Sửa ownership, giới hạn concurrency và kiểm tra metrics trước.

## 9. DataBuffer API nên sử dụng trong Spring 6.2

Spring `DataBuffer.readableByteBuffers()` (từ Spring 6.0.5) trả một iterator phải **đóng** bằng try-with-resources. Có thể cập nhật SHA-256 không cần copy toàn bộ body:

~~~java
// Fragment trong code có MessageDigest sha và DataBuffer buffer.
try (DataBuffer.ByteBufferIterator views =
         buffer.readableByteBuffers()) {
    while (views.hasNext()) {
        sha.update(views.next());
    }
} finally {
    DataBufferUtils.release(buffer);
}
~~~

Nếu thư viện dùng codec trực tiếp, khác biệt giữa `read(byte[])` và `readableByteBuffers()`:
- `read(byte[])` có thể copy dữ liệu sang Java heap array, thuận tiện nhưng tạo additional allocations.
- Iterator trên readable ByteBuffers có thể tránh copy tùy backing buffer.
- Không giữ `ByteBuffer` views ngoài vòng đời iteration và **không** sử dụng sau khi DataBuffer được release.
- Trong Spring 6.2, một số `DataBuffer.asByteBuffer()`/`toByteBuffer()` overload cũ đã deprecated; dùng API mới theo Javadoc để tránh lệ thuộc các view thiếu lifecycle rõ.

### Không dùng DataBufferUtils.join vô giới hạn

~~~java
// RỦI RO: gom toàn bộ body; nếu không có giới hạn,
// client có thể khiến app giữ hàng trăm MiB.
Mono<DataBuffer> all = DataBufferUtils.join(incoming);
~~~

Nếu nghiệp vụ bắt buộc gom, đặt bound:

~~~java
// Fragment: gom tối đa 1 MiB.
Mono<DataBuffer> bounded = DataBufferUtils.join(
    incoming, 1024 * 1024);
~~~

Sau khi nhận `DataBuffer` kết quả, code **tự tiêu thụ** phải release kết quả:

~~~java
return bounded.map(buffer -> {
    try {
        return buffer.readableByteCount();
    } finally {
        DataBufferUtils.release(buffer);
    }
});
~~~

`DataBufferUtils.join(..., maxByteCount)` có thể ném `DataBufferLimitException` khi vượt bound. Join có thể sử dụng composite buffer/zero-copy theo backing allocator, nhưng vẫn giữ dữ liệu của các chunks đến khi hoàn thành. “Zero-copy” ở một thao tác không có nghĩa memory footprint gần 0.

## 10. Codec aggregation limit của WebFlux: 256 KiB mặc định ở nhiều codecs

Theo tài liệu Spring WebFlux, nhiều codec mặc định giới hạn khoảng **256 KiB** dữ liệu được buffer khi phải **aggregate** thành một object. Khi vượt mức, exception có thể là:

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

Trong **Spring Boot 3.5**, property được tài liệu hóa:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 256KB
~~~

Property này:
- Áp dụng cho **auto-configured WebFlux server** và các **auto-configured WebClient instances** trong phạm vi Boot mô tả.
- Điều chỉnh **giới hạn bộ nhớ khi stream phải được gom**; không phải quota memory toàn process.
- Không tự giới hạn tổng bytes qua một endpoint streaming sử dụng `Flux<DataBuffer>`.
- Không đồng nghĩa max upload size từ reverse proxy, container hoặc security gateway.
- Không nhất thiết áp dụng cho `WebClient.builder()`/client được tạo thủ công ngoài Boot customization.

Nếu ứng dụng cần nhận JSON 1 MiB, có thể tăng lên **2 MiB** sau khi tính worst-case concurrency, nhưng **đừng chọn 100 MiB chỉ vì nhận được một lỗi**. Hãy hỏi tại sao endpoint phải aggregate thay vì streaming/file-based processing.

### Cấu hình riêng với WebFluxConfigurer

Nếu không muốn dùng Boot global codec property hoặc cần control theo framework:

~~~java
// Fragment trong @Configuration class implement WebFluxConfigurer.
@Override
public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer) {
    configurer.defaultCodecs()
              .maxInMemorySize(512 * 1024);
}
~~~

Các imports:
- `org.springframework.web.reactive.config.WebFluxConfigurer`
- `org.springframework.http.codec.ServerCodecConfigurer`

Không bật `@EnableWebFlux` chỉ để đổi codec limits trong một Boot WebFlux app; nó có thể vô hiệu hóa nhiều cấu hình tự động của Boot.

### WebClient có limit phía client độc lập

~~~java
// Fragment khi chủ động tạo WebClient.
WebClient client = WebClient.builder()
    .codecs(c -> c.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
    .build();
~~~

Nếu client dùng `retrieve().bodyToMono(String.class)` hoặc `bodyToMono(byte[].class)` với response lớn, codec có thể phải gom và gặp `DataBufferLimitException`. Tăng client limit không tăng server limit và ngược lại. Nên ưu tiên `bodyToFlux(DataBuffer.class)` + consume/release đúng cách cho response lớn hoặc streaming.

### Limit là per aggregation, không phải global concurrency cap

Ví dụ 500 requests đồng thời, mỗi request decode JSON gần 2 MiB:

~~~text
500 x 2 MiB = 1,000 MiB (~0.98 GiB) body bytes lý thuyết
~~~

Chưa tính decoded Java objects, Netty buffers, TLS, serialization, threads, caches, queue và GC. `maxInMemorySize=2MB` **không** giới hạn tổng cùng lúc là 2 MiB; nó là một limit cho mỗi decoder/object theo cơ chế cụ thể.

## 11. HTTP request body size, header size và multipart là các limit riêng

Đừng nhầm các limit:

| Cơ chế | Điều bảo vệ | Ví dụ |
|---|---|---|
| `spring.http.codecs.max-in-memory-size` | Dữ liệu codec cần buffer khi aggregate | JSON/String/byte[] decoding |
| `spring.webflux.multipart.max-in-memory-size` | In-memory threshold per multipart part (file part có thể spill disk) | Form upload |
| `spring.webflux.multipart.max-disk-usage-per-part` | Dung lượng đĩa giới hạn cho một part | File part quá lớn |
| `spring.webflux.multipart.max-parts` | Số parts mỗi multipart request | Multipart DoS |
| `server.max-http-request-header-size` | Kích thước HTTP headers theo embedded server semantics | Quá nhiều cookies/headers |
| `server.netty.initial-buffer-size` | Initial HTTP request decoding buffer | Không phải body maximum |
| Reverse proxy `client_max_body_size` (NGINX) | HTTP request body accepted at edge | Edge trả 413 trước JVM |
| Ứng dụng tự đếm bytes stream | Tổng kích thước một request stream | Multipart/raw binary lớn |

Trong Boot 3.5, các property WebFlux multipart thuộc `spring.webflux.multipart.*` theo Common Application Properties. File parts có thể được ghi ra **temporary disk** khi vượt in-memory threshold, khác với non-file parts. Cần giới hạn disk/quota, số parts, temporary directory permissions và cleanup.

**Spring MVC/Servlet** có namespace riêng `spring.servlet.multipart.max-file-size`, `spring.servlet.multipart.max-request-size`, `spring.servlet.multipart.file-size-threshold`. Không dùng properties MVC để “sửa” một app WebFlux/Netty.

### HTTP 413 và DataBufferLimitException

HTTP `413 Content Too Large`/`Payload Too Large` nói server từ chối body do kích thước. Nhưng `DataBufferLimitException` do codec phát sinh không bảo đảm mọi ứng dụng sẽ tự chuyển đúng 413 trong mọi version/handler chain. Với API cần hợp đồng ổn định, cấu hình exception mapping/test rõ, **và** đặt limit tại proxy/server/codec theo các lớp phù hợp.

Khi request vượt limit, server có thể trả response trước khi client gửi hết body, đóng connection hoặc drain theo policy. Đừng dựa vào một status từ `curl` là bằng chứng toàn bộ body đã được đọc vào heap.

## 12. HTTP response buffers và backpressure

Đọc inbound chưa phải toàn bộ bài toán: **ghi outbound** cũng giữ buffers. Khi ứng dụng trả 100 MiB binary response, có hai cách:

**Aggregate toàn bộ trước:**

~~~java
// Phản ví dụ cho file lớn: lấy cả nội dung vào heap.
byte[] bytes = Files.readAllBytes(path);
return ResponseEntity.ok(bytes);
~~~

Đây là Java fragment, `path`/imports/handler chưa được định nghĩa. Nó có thể tạo một `byte[]` 100 MiB trên heap, rồi serializer/transport cần thêm buffers/copies.

**Stream thành từng phần:**

~~~java
// Fragment WebFlux khi đã có Flux<DataBuffer> body.
return response.writeWith(body);
~~~

Dùng một publisher phát chunks theo demand, giới hạn prefetch/queues và chuyển buffer ownership cho HTTP response writer. Không nhất thiết giữ toàn file trên heap cùng lúc.

### Backpressure không đồng nghĩa “tự động không bao giờ OOM”

Reactive Streams có `request(n)` và `cancel`; khi subscriber/HTTP transport chậm, upstream **có thể** giảm phát dữ liệu nếu nguồn tôn trọng demand. Tuy nhiên các điểm sau vẫn làm memory nở:
- `onBackpressureBuffer()` không giới hạn.
- `collectList()` trên toàn bộ stream.
- `flatMap` concurrency/prefetch cao.
- Dữ liệu từ hot publisher phát nhanh hơn clients tiêu thụ.
- Queue trong message broker/application không được backpressure.
- HTTP/2 multiplexing: nhiều streams cùng mở trên một connection.
- Compression/TLS/serialization có buffering riêng.
- Netty channel outbound queue có thể phình nếu producers không tôn trọng write demand.

Với file download/streaming, kiểm soát **bytes retained per connection**, concurrent clients, output queues và slow-client timeout. Một server có 50.000 kết nối chậm có thể cần nhiều memory ngay cả khi mỗi connection giữ rất ít buffers.

### HTTP/1.1 chunked và HTTP/2 frames

- HTTP/1.1 có thể dùng `Transfer-Encoding: chunked` khi chưa biết Content-Length.
- HTTP/2 truyền DATA frames và không dùng HTTP/1.1 chunked transfer coding.
- Kích thước một TCP packet hay HTTP chunk/frame **không bảo đảm** kích thước `DataBuffer` vào controller bằng đúng con số đó.
- Proxy có thể buffer hoặc re-chunk dữ liệu; đừng viết business parser dựa vào ranh giới TCP read/chunk. Luồng là bytes liên tục; tự thiết kế framing như NDJSON, length-prefix hoặc multipart protocol khi cần.

## 13. Demo runnable: WebFlux upload theo luồng, download từng chunk và memory snapshot

Demo có bốn endpoints:
- `GET /api/stream?chunks=4`: tạo **4 chunks × 4096 bytes**, gửi body nhị phân qua `Flux<DataBuffer>`, không tạo mảng 16 KiB tổng.
- `POST /api/digest`: nhận raw `application/octet-stream` dưới dạng `Flux<DataBuffer>`, cập nhật **SHA-256 từng buffer**, release buffer sau khi xử lý và tự giới hạn tổng 8 MiB.
- `POST /api/json`: nhận một JSON DTO bình thường qua codec aggregation, để nhìn sự khác nhau với streaming.
- `GET /api/memory`: đọc `MemoryMXBean` và Java NIO `BufferPoolMXBean`, **không** giả định giá trị direct NIO bằng toàn Netty direct memory.

Chỉ dùng **Spring Reactive Web + Actuator**; thêm Prometheus registry nếu muốn scrape.

### 13.1. Khởi tạo project

Tạo project Spring Initializr:
- Java **17+**, Spring Boot **3.5.x**, Gradle, dependency **Spring Reactive Web (WebFlux)**, **Spring Boot Actuator**.
- Không thêm `spring-boot-starter-web` vào demo reactive (nếu có cả web + webflux starters Boot thường chọn Servlet stack).

Trong Gradle project do Initializr tạo, phần dependencies cần tương đương:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là **fragment dependency**, không phải một `build.gradle` hoàn chỉnh. Boot dependency management chọn các phiên bản compatible. Các source file tiếp theo dùng package `demo.buffers`.

### 13.2. application.yml

Tạo `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  http:
    codecs:
      max-in-memory-size: 256KB

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
~~~

Giải thích:
- `max-in-memory-size: 256KB`: mức thử nghiệm codec aggregation, không phải HTTP upload hard cap.
- Bài tự giới hạn `/api/digest` ở 8 MiB trong controller vì endpoint đọc dạng stream; không dựa vào codec 256KB để bảo vệ nó.
- Actuator `metrics`/`prometheus` **chỉ chạy local**. Trên production phải bảo vệ qua private network/auth/mTLS tùy kiến trúc; không mở toàn bộ diagnostics cho Internet.

### 13.3. File Java hoàn chỉnh

Tạo `src/main/java/demo/buffers/BufferRuntimeApplication.java`:

~~~java
package demo.buffers;

import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class BufferRuntimeApplication {

    private static final int CHUNK_SIZE = 4096;
    private static final int MAX_CHUNKS = 1024;
    private static final long MAX_UPLOAD_BYTES = 8L * 1024 * 1024;

    public static void main(String[] args) {
        SpringApplication.run(BufferRuntimeApplication.class, args);
    }

    public record DigestResult(long bytes, String sha256) { }
    public record JsonRequest(String text) { }
    public record JsonResult(int textLength) { }

    @GetMapping(
        path = "/api/stream",
        produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
    )
    public Flux<DataBuffer> stream(
            @RequestParam(defaultValue = "4") int chunks,
            ServerHttpResponse response) {

        if (chunks < 1 || chunks > MAX_CHUNKS) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "chunks must be between 1 and 1024"
            );
        }

        // Flux.range phát theo demand; map tạo MỘT block
        // khi downstream yêu cầu, thay vì gom toàn bộ file.
        return Flux.range(0, chunks)
            .map(i -> {
                byte[] block = new byte[CHUNK_SIZE];
                Arrays.fill(block, (byte) 'A');
                return response.bufferFactory().wrap(block);
            })
            .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
    }

    @PostMapping(
        path = "/api/digest",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<DigestResult> digest(
            @RequestBody Flux<DataBuffer> body) {

        return Mono.defer(() -> {
            MessageDigest sha;
            try {
                sha = MessageDigest.getInstance("SHA-256");
            } catch (NoSuchAlgorithmException ex) {
                return Mono.error(new IllegalStateException(ex));
            }

            AtomicLong total = new AtomicLong();

            return body
                .doOnDiscard(
                    DataBuffer.class, DataBufferUtils::release)
                .handle((buffer, sink) -> {
                    try {
                        long count = total.addAndGet(
                            buffer.readableByteCount());

                        if (count > MAX_UPLOAD_BYTES) {
                            sink.error(new ResponseStatusException(
                                HttpStatus.PAYLOAD_TOO_LARGE,
                                "Upload exceeds 8 MiB"
                            ));
                            return;
                        }

                        // Close iterator, then release the consumed buffer.
                        try (DataBuffer.ByteBufferIterator views =
                                 buffer.readableByteBuffers()) {
                            while (views.hasNext()) {
                                ByteBuffer view = views.next();
                                sha.update(view);
                            }
                        }
                    } finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .then(Mono.fromSupplier(() ->
                    new DigestResult(
                        total.get(),
                        HexFormat.of().formatHex(sha.digest())
                    )
                ));
        });
    }

    @PostMapping(
        path = "/api/json",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<JsonResult> json(
            @RequestBody Mono<JsonRequest> incoming) {
        return incoming.map(request ->
            new JsonResult(request.text().length())
        );
    }

    @GetMapping("/api/memory")
    public Map<String, Long> memory() {
        long heapUsed = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getUsed();
        long heapMax = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getMax();

        long nioDirectBytes = ManagementFactory.getPlatformMXBeans(
                    BufferPoolMXBean.class)
                .stream()
                .filter(pool -> "direct".equals(pool.getName()))
                .mapToLong(BufferPoolMXBean::getMemoryUsed)
                .filter(bytes -> bytes >= 0)
                .sum();

        return Map.of(
            "heapUsedBytes", heapUsed,
            "heapMaxBytes", heapMax,
            "nioDirectUsedBytes", nioDirectBytes
        );
    }
}
~~~

**QA code structure:**
- Một file có đúng một `public class BufferRuntimeApplication` và records nested static implicitly trong class.
- `MessageDigest` được tạo **riêng trên mỗi subscription** nhờ `Mono.defer(...)`. Không dùng singleton mutable hash shared giữa các requests.
- `Flux<DataBuffer>` của upload được tiêu thụ từng buffer, iterator view được đóng, và `DataBufferUtils.release(buffer)` luôn chạy trong `finally`.
- Khi vượt 8 MiB, handler tạo `ResponseStatusException(413)`, release buffer hiện tại và kết thúc subscription; các buffered/discarded buffers được xử lý qua hook phù hợp.
- `Flux.range` + `map` cho download không tạo tất cả buffers ngay lập tức trước subscription. Buffers **được chuyển cho Spring HTTP writer**; controller không gọi `release` sớm cho buffers đã chuyển giao.
- Endpoint `/api/memory` chỉ đọc metrics; không giữ bytes của body hoặc tạo một direct buffer cực lớn làm thí nghiệm.
- Thí nghiệm JSON sử dụng `Mono<JsonRequest>` để cho framework decoder quản lý buffer, khác với raw streaming handler.

**Giới hạn demo:** Mỗi chunk tạo một `byte[4096]`; vẫn có allocation Java heap theo chunks và có thể có Netty transport copies. “Streaming” ở đây nghĩa **không giữ toàn response 4 MiB trong ứng dụng cùng một lúc**, không có nghĩa zero heap allocations hoặc zero native allocations. Nếu môi trường/client chậm, transport có thể còn giữ buffers cho đến khi gửi xong.

### 13.4. Chạy ứng dụng

Ở root dự án có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Ứng dụng chạy `http://localhost:8080` khi cổng chưa bị dùng. Demo không có auth nên chỉ chạy trong môi trường học cục bộ. Không chạy payload tests với dữ liệu nhạy cảm.

## 14. Test upload streaming bằng SHA-256

Gửi 5 bytes ASCII `hello`:

~~~bash
curl -sS -i \
  -X POST \
  -H 'Content-Type: application/octet-stream' \
  --data-binary 'hello' \
  http://localhost:8080/api/digest
~~~

HTTP status kỳ vọng **200 OK**, response body **chính xác về các field**:

~~~json
{
  "bytes": 5,
  "sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
}
~~~

Thứ tự JSON fields không được bảo đảm, nhưng SHA-256 của UTF-8 `hello` là giá trị cố định trên. `bytes=5` vì chỉ có 5 ASCII bytes. Nếu đổi sang chuỗi tiếng Việt, số bytes UTF-8 có thể khác số ký tự.

### Upload >256 KiB vẫn có thể qua streaming endpoint

Do `/api/digest` đọc `Flux<DataBuffer>` theo chunks, codec aggregation limit 256KB **không tự cắt** payload 512 KiB nếu không có một reader nào đang aggregate; application 8 MiB limit vẫn áp dụng.

Tạo dữ liệu thử nghiệm bằng Python chuẩn, chỉ ở máy local:

~~~bash
python -c "open('payload.bin','wb').write(b'x' * (512 * 1024))"
~~~

Sau đó:

~~~bash
curl -sS -i \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @payload.bin \
  http://localhost:8080/api/digest
~~~

Body JSON sẽ có `"bytes":524288` và `sha256` tương ứng dữ liệu `x` lặp 524288 lần; không ghi một SHA giả vì chưa chạy hash trên máy thực. Nếu tệp lớn hơn **8 MiB**, controller tự báo **413**; request có thể chưa được client gửi hết khi server từ chối, tùy transport.

**Đừng dùng** lệnh tạo payload hàng chục GiB trên thiết bị production; mọi thí nghiệm memory stress phải ở môi trường cô lập, có quotas và timeout.

## 15. Test download streaming, số bytes chính xác

Tạo 4 chunks:

~~~bash
curl -sS \
  "http://localhost:8080/api/stream?chunks=4" \
  -o stream.bin
~~~

File chứa đúng:

~~~text
4 chunks × 4096 bytes/chunk = 16384 bytes
~~~

Bash/Linux/macOS:

~~~bash
wc -c < stream.bin
~~~

Stdout kỳ vọng:

~~~text
16384
~~~

PowerShell:

~~~powershell
(Get-Item .\stream.bin).Length
~~~

Stdout kỳ vọng:

~~~text
16384
~~~

Đổi `chunks=1024` cho tối đa **4 MiB** response (1024 × 4096 = 4194304 bytes), nhưng endpoint **không dựng một mảng 4 MiB duy nhất**. Với `chunks=0` hoặc `chunks=1025`, server báo **400 Bad Request** theo validation của demo.

**Vì sao kích thước có thể tính chính xác?** Controller sinh mỗi chunk thành mảng 4096 byte và phát đúng `chunks` chunks. Bytes trên wire có thể còn framing overhead (HTTP/1.1 chunked hoặc HTTP/2 frames), nhưng `curl -o stream.bin` chỉ lưu **entity body**, nên file size đúng nếu request thành công/truyền đủ.

## 16. Test JSON aggregation vs raw stream

Request nhỏ:

~~~bash
curl -sS -i \
  -H 'Content-Type: application/json' \
  --data-binary '{"text":"hi"}' \
  http://localhost:8080/api/json
~~~

Status **200**, body:

~~~json
{"textLength":2}
~~~

Tạo JSON dài vượt 256 KiB:

~~~bash
python -c "import json; open('large.json','w',encoding='utf-8').write(json.dumps({'text':'x' * 400000}))"
~~~

Gửi:

~~~bash
curl -sS -i \
  -H 'Content-Type: application/json' \
  --data-binary @large.json \
  http://localhost:8080/api/json
~~~

Spring WebFlux decoder có thể phát `DataBufferLimitException` khi vượt configured memory aggregation bound. **HTTP status/body lỗi cuối cùng phụ thuộc exception handling và phiên bản**. Nếu API production cần trả 413 theo hợp đồng, thêm exception mapping rõ ràng và kiểm thử thay vì giả định mọi `DataBufferLimitException` đều mặc định là HTTP 413.

### Map codec limit thành 413 một cách có chủ đích

Fragment Spring WebFlux:

~~~java
@RestControllerAdvice
class CodecLimitAdvice {

    @ExceptionHandler(DataBufferLimitException.class)
    public ResponseEntity<Map<String, String>> tooLarge(
            DataBufferLimitException ignored) {
        return ResponseEntity
            .status(HttpStatus.PAYLOAD_TOO_LARGE)
            .body(Map.of("error", "CODEC_LIMIT"));
    }
}
~~~

Imports:
- `org.springframework.web.bind.annotation.RestControllerAdvice`
- `org.springframework.web.bind.annotation.ExceptionHandler`
- `org.springframework.core.io.buffer.DataBufferLimitException`
- `org.springframework.http.ResponseEntity`
- `org.springframework.http.HttpStatus`
- `java.util.Map`

Đây là **fragment minh họa**, không nằm trong file runnable chính. Một lỗi decoder có thể được framework bọc bởi loại exception khác hoặc xử lý tại tầng khác, nên khi cần chính sách production cần test với WebFlux version, CORS/Security/error handler chain thật. Mục tiêu là trả một lỗi kích thước rõ nghĩa **mà không bật maxInMemorySize vô hạn**.

### Đừng nhầm memory limit với business upload limit

- `/api/json` dùng JSON decoder: memory aggregation limit có hiệu lực khi codec buffer.
- `/api/digest` là streaming raw bytes: tự đếm `MAX_UPLOAD_BYTES`, không gom toàn body.
- Reverse proxy hoặc firewall có thể chặn request sớm hơn, ví dụ `client_max_body_size`.
- Một multipart upload cũng có parser thresholds/limits và temp disk logic riêng.

Mỗi loại nên có **test vượt ngưỡng** từ môi trường ngoài, không chỉ unit test trên controller.

## 17. WebClient: bodyToMono(byte[]) và bodyToFlux(DataBuffer.class)

WebClient là HTTP client reactive dùng được trong MVC hoặc WebFlux. Với response lớn, chọn representation rất quan trọng.

### Anti-pattern: nhận tất cả response thành byte[]

~~~java
// Fragment, WebClient đã có baseUrl phù hợp.
Mono<byte[]> bytes = webClient.get()
    .uri("/big-file")
    .retrieve()
    .bodyToMono(byte[].class);
~~~

Cách này đòi body được **gom** thành byte array, chịu codec memory limit và có thể tạo lớn heap allocation. Nếu server trả 100 MiB, tăng `maxInMemorySize` thành 200 MiB không tự làm toàn hệ thống an toàn khi có nhiều concurrent requests.

### Stream và release khi tự tiêu thụ

~~~java
// Fragment: dùng trong service có WebClient được cấu hình.
AtomicLong total = new AtomicLong();

Mono<Long> downloadedBytes = webClient.get()
    .uri("/big-file")
    .retrieve()
    .bodyToFlux(DataBuffer.class)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .doOnNext(buffer -> {
        try {
            total.addAndGet(buffer.readableByteCount());
        } finally {
            DataBufferUtils.release(buffer);
        }
    })
    .then(Mono.fromSupplier(total::get));
~~~

**Đây là fragment chỉ dùng cho một subscription tại một thời điểm.** Trong production, tạo `AtomicLong` **per subscription** (ví dụ bọc toàn pipeline trong `Mono.defer(...)`), không dùng singleton `AtomicLong` giữa requests. Nếu muốn lưu file, xem `DataBufferUtils.write(...)` cùng cơ chế release thích hợp sau khi ghi; không chỉ đếm rồi bỏ bytes.

**Lưu ý về Response body handling:** Nếu dùng `exchangeToMono/Flux`, cần tiêu thụ hoặc release body trên các nhánh status, không để unused pooled response buffers. `retrieve()` và codecs framework xử lý nhiều error-path details, nhưng custom exchange/filter logic vẫn phải kiểm tra ownership.

### Tránh buffer toàn bộ trong các operators

Phản ví dụ:

~~~java
// RỦI RO: memory ∝ toàn bộ response.
return webClient.get()
    .uri("/big-file")
    .retrieve()
    .bodyToFlux(DataBuffer.class)
    .collectList();
~~~

`collectList()` giữ **tất cả buffer references** cho tới khi response hoàn thành, có thể tăng direct memory và tạo leak nếu người viết không release. Cũng không nên dùng `onBackpressureBuffer()` không giới hạn trước một file sink chậm.

## 18. Slow consumer, backpressure và outbound queue

Giả sử Spring Boot stream dữ liệu tới client qua mạng chậm:

~~~text
Producer: 50 MiB/s
Network to client: 0.5 MiB/s
Difference: ~49.5 MiB/s cần phải được chặn, drop, hoặc buffer ở đâu đó
~~~

Nếu ứng dụng tiếp tục tạo bytes mà không có backpressure, memory queue có thể tăng hàng trăm MiB mỗi vài giây. Với upload cũng tương tự nếu upstream client đọc nhanh nhưng downstream file/database ghi chậm.

**Backpressure** là tín hiệu giới hạn demand upstream:
- `Flux.range(...)` tôn trọng số phần tử được request, nên phù hợp để minh họa chunk-by-chunk.
- Một hot source hoặc custom publisher **không tôn trọng demand** có thể phát nhanh và làm queues phình.
- `flatMap(..., concurrency)` có khả năng prefetch/buffer; giới hạn concurrency khi downstream chậm.
- `publishOn` dùng queue theo scheduler; không chuyển mọi workloads sang scheduler khác mà không đo.
- `onBackpressureBuffer(max, ...)` có thể làm giới hạn rõ; policy drop/error phải đúng nghiệp vụ.
- Reactor Netty channel writability, HTTP/2 flow-control windows, TCP send buffers và remote read rate cùng ảnh hưởng **tốc độ gửi** nhưng không thay thế application queue design.

Với SSE/WebSocket, nếu một client rất chậm, cần giới hạn **outbound queue per session**, chọn overflow policy (disconnect slow consumer, coalesce latest values, persist event IDs) và có reconnect/replay theo nghiệp vụ. Không drop silently events tài chính/audit.

## 19. Dự tính memory theo concurrency thay vì chỉ theo payload size

Một mô hình sơ bộ:

~~~text
Memory used by HTTP workload ≈
  in-flight request count × average retained input buffers
+ active response streams × retained output buffers
+ codec object graph / compression / TLS buffers
+ connection/session state + queues/cache
+ JVM/runtime memory ngoài HTTP
~~~

Ví dụ **chỉ để lập ngân sách**:
- 400 concurrent requests.
- Mỗi request có trung bình 256 KiB dữ liệu đang aggregate.
- Dữ liệu body tối thiểu gần **100 MiB** cùng lúc.
- Nếu decoded JSON object graph chiếm thêm 2–4 lần input và transport buffers cần thêm memory, áp lực có thể lớn hơn nhiều.

~~~text
400 × 256 KiB = 102400 KiB = 100 MiB
~~~

Đây không phải công thức cho heap/direct usage chính xác, vì mỗi request có lifecycle, allocation và sharing khác nhau. Mục tiêu là thấy **per-request limit không giới hạn total concurrency**.

### Các ranh giới bảo vệ bổ sung

1. Limit số concurrent requests/streams per instance.
2. Limit request body size tại edge, gateway và application.
3. Limit codec aggregation/per-item size.
4. Giới hạn multipart parts/disk.
5. Limit output queue/buffers per client.
6. Timeout/slow-client protection để giữ resources hữu hạn.
7. Tránh unbounded caches hoặc `collectList`.
8. Tính headroom cho JVM native/direct/TLS/thread stacks và monitoring.
9. Thử spike traffic, slow uploads/downloads, client cancellation và repeated requests.
10. Đo **RSS/cgroup + heap + allocator active/used + GC + buffer pools** cùng thời gian.

**Không tự tăng `-Xmx` và direct limits đến sát cgroup limit**. Cần cân bằng process memory thực tế, QoS, GC pause và tránh cgroup OOM killer.

## 20. Quan sát heap và native/direct memory bằng Actuator

Với `spring-boot-starter-actuator`, Spring Boot + Micrometer thường có JVM metrics khi registry tương ứng được bật:

~~~bash
curl -sS http://localhost:8080/actuator/metrics
~~~

Tra names, có thể gặp:
- `jvm.memory.used` / `jvm.memory.max` (heap/nonheap khi có tags).
- `jvm.gc.pause` và allocation/GC metrics tùy runtime.
- `jvm.buffer.memory.used` / `jvm.buffer.count` / `jvm.buffer.total.capacity` cho Java buffer pools.
- `process.cpu.usage`, `process.files.open` khi platform hỗ trợ.
- Reactor Netty metrics nếu instrumentation được bật tương ứng.

Ví dụ drill-down:

~~~bash
curl -sS \
  "http://localhost:8080/actuator/metrics/jvm.buffer.memory.used"
~~~

`jvm.buffer.memory.used` thường dựa trên Java `BufferPoolMXBean` như direct/mapped, nhưng **không nhất thiết gồm mọi native Netty allocation**. Đừng dùng số này một mình để phủ nhận native memory pressure.

### Prometheus exposition

~~~bash
curl -sS http://localhost:8080/actuator/prometheus
~~~

Tên Prometheus thường chuẩn hóa sang underscore và thêm unit suffix, ví dụ `jvm_buffer_memory_used_bytes` khi registry xuất meter. **Không mặc định mọi meter có mặt** trước khi cấu hình instrumentations hoặc sau khi đổi versions; đọc names thực tế trên runtime.

Reactor Netty allocator metrics có thể gồm:
- `reactor.netty.bytebuf.allocator.used.direct.memory`
- `reactor.netty.bytebuf.allocator.active.direct.memory`
- `reactor.netty.bytebuf.allocator.used.heap.memory`
- `reactor.netty.bytebuf.allocator.active.heap.memory`
- `reactor.netty.eventloop.pending.tasks`

Chúng phụ thuộc metrics/allocator instrumentation và Netty version. Nếu `reactor.netty.*` không xuất hiện, **không kết luận không dùng Netty direct buffers**; xác minh việc bật Reactor Netty metrics và nguồn data.

### Đọc kết hợp với process/container memory

| Metric | Khi tăng | Ý nghĩa sơ bộ |
|---|---|---|
| JVM heap used | DTO/JSON/cache/byte arrays | Heap allocation hoặc retained object tăng |
| JVM GC pause | GC phải thu hồi thường xuyên | Allocation/heap sizing/retained pressure |
| NIO direct buffer memory | Java direct buffers còn tracked | NIO direct usage |
| Netty active direct | Buffer đang in use | Dòng requests hoặc potential refcount leak |
| Netty used/reserved direct | Pool reservation | Có thể giữ cao sau warm-up mà không leak |
| Process RSS | Tổng physical memory đang cư trú | Có thể gồm heap, native, mmap, stacks |
| Container memory.current/working set | Memory accounting của cgroup | Nguy cơ sát limit / OOMKill |
| HTTP in-flight/connections | Load concurrency | Cần so với buffers per connection |
| Network bytes/latency | Throughput/slow clients | Chẩn đoán queue và backpressure |

**Đừng kết luận leak chỉ từ một snapshot.** Chạy tải lặp, đợi requests hoàn tất, xem active memory về nền không, so sánh heap after-GC và Netty active/reserved cùng thông số concurrency.

## 21. Java diagnostic tools: jcmd, NMT và heap dump

### 21.1. Xem JVM flags và heap

Trong môi trường test có JDK và quyền attach:

~~~bash
jcmd -l
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
~~~

`<PID>` trong lệnh là placeholder process ID, thay bằng PID thật. Không thực thi nguyên chuỗi có dấu ngoặc nhọn. `jcmd` có thể bị hạn chế bởi container, attach permissions, thiếu JDK tools hoặc security policy.

### 21.2. Native Memory Tracking (NMT)

Bật khi khởi động ứng dụng để kiểm tra JVM native memory categories:

~~~bash
java -XX:NativeMemoryTracking=summary \
  -XX:MaxDirectMemorySize=256m \
  -Xmx512m -jar app.jar
~~~

Đây là **ví dụ JVM flags**, không bắt buộc là memory budget phù hợp mọi container. Khi NMT đã bật, có thể dùng:

~~~bash
jcmd <PID> VM.native_memory summary
jcmd <PID> VM.native_memory baseline
jcmd <PID> VM.native_memory summary.diff
~~~

Trên Windows PowerShell, hãy chạy một lệnh mỗi dòng và thay PID bằng số thật; slash ở lệnh shell là hướng dẫn cho Bash, không phải nội dung Java. NMT thường phải được bật **lúc JVM khởi động** và có overhead quan sát; `summary` ít chi tiết hơn `detail`.

**Giới hạn của NMT:** nó theo dõi các JVM native allocations thuộc cơ chế được hỗ trợ; không phải mọi native memory do thư viện bên ngoài cấp phát đều được ghi đầy đủ. Đối chiếu với `RSS`/`/proc/<pid>/smaps`, Netty allocator metrics, cgroup memory và native profiler khi cần.

### 21.3. Heap dump / Java Flight Recorder

Khi nghi heap leak:
- `jcmd <PID> GC.heap_dump /path/heap.hprof` tạo heap dump (có thể **rất lớn**, ảnh hưởng performance và chứa dữ liệu nhạy cảm).
- Java Flight Recorder (JFR) giúp xem allocation hotspots, GC, thread blocking và event timing theo cấu hình.
- MAT/YourKit/JProfiler có thể phân tích retained size, dominator tree và paths to GC roots.

**Heap dump không phải bản chụp mọi native bytes**; một Java Netty ByteBuf wrapper có thể bé trong heap dump dù backing direct memory lớn. Vì vậy khi OOMKilled với heap after-GC thấp, phải kiểm tra native/process accounting trước khi chỉ nhìn heap dump.

## 22. Netty leak detection: bật có kiểm soát trong test

Netty có `ResourceLeakDetector` để phát hiện một số trường hợp `ByteBuf` chưa được release. Các levels như SIMPLE, ADVANCED, PARANOID có trade-off chi phí CPU/logging.

Ví dụ **JVM system property trong môi trường test**:

~~~bash
java -Dio.netty.leakDetection.level=advanced -jar app.jar
~~~

Đây không phải lời khuyên bật `paranoid` cho mọi traffic production; có thể gây overhead đáng kể. Reactor Netty còn có logger `_reactor.netty.channel.LeakDetection` để giúp xác định ownership. Cần xem docs Netty/Reactor Netty của version đang dùng, tránh suy từ một dòng log mà quy lỗi cho code sở hữu dữ liệu khác.

### Triệu chứng và cách kiểm tra

~~~text
HTTP traffic ổn định
    |
    +-- Netty active direct tăng
    +-- Requests completed trở về baseline
    +-- JVM heap ổn định hoặc chỉ tăng nhẹ
    +-- RSS/cgroup tăng dần
           |
           v
    Nghi pooled buffer chưa release, outbound queue hoặc native allocation
~~~

Không phải cứ `used.direct.memory` cao là leak; allocator có thể giữ pool memory để tái sử dụng. Cũng không phải cứ GC chạy thì mọi pooled ByteBuf được thu hồi. Kiểm tra active buffers, subscribers, cancellation paths và refcount lifecycle.

## 23. Memory pressure từ compression, TLS và multipart

### HTTP compression

Khi server gzip/deflate response, có thêm compressor state/buffers. Nếu ứng dụng aggregate JSON thành một `String` lớn rồi nén, heap và native allocations có thể tồn tại cùng lúc. Compression có thể giảm bytes trên wire nhưng làm tăng CPU và peak memory; cần load test trên response sizes, concurrency và content types thực tế.

### TLS

TLS libraries thường giữ network/application buffers, handshake state và certificates/session caches. HTTPS không tự đòi hai bản sao full request body, nhưng vẫn có native/heap overhead. TLS có thể kết thúc tại load balancer; JVM chỉ thấy HTTP plaintext upstream, song edge proxy tiêu thụ memory riêng.

### Multipart

Một request upload 100 MiB có thể:
- Bị gateway từ chối trước backend.
- Được multipart parser ghi ra temporary disk thay vì giữ toàn bộ.
- Bị handler dùng `FilePart.transferTo(path)` xử lý streaming.
- Hoặc bị application gọi `DataBufferUtils.join` rồi giữ 100 MiB trong memory một cách không cần thiết.

Với Spring WebFlux, `spring.webflux.multipart.max-in-memory-size` điều khiển in-memory threshold per part, `max-disk-usage-per-part` kiểm soát disk per part, `max-parts` giới hạn số parts. Với Spring MVC, bộ `spring.servlet.multipart.*` có semantics/configuration riêng.

**Bảo mật:** giới hạn file sizes/parts, sanitize filename, không tin Content-Type/extension do user khai, kiểm tra nội dung, scan malware khi cần, tránh path traversal, giới hạn temporary disk và permissions. Một upload DoS có thể làm **disk đầy** chứ không chỉ heap/direct đầy.

## 24. Các lỗi thiết kế dẫn tới memory leak hoặc OOM

| Phản ví dụ | Rủi ro | Cách thay |
|---|---|---|
| `@RequestBody byte[]` cho upload 2 GiB | Cần aggregate, heap không chịu nổi | Streaming `Flux<DataBuffer>` + limit và storage sink |
| `bodyToMono(String.class)` nhận response cực lớn | Codec limit/OOM | Stream bounded, file sink hoặc chunk processing |
| `collectList()` với hàng triệu DataBuffers | Retain references và direct memory | Consume theo chunk, release và bound queues |
| `DataBufferUtils.join(...)` không giới hạn | Memory tăng theo body | Join có max byte count hoặc streaming |
| Đọc DataBuffer rồi quên release | Pooled refcount leak | try/finally `DataBufferUtils.release` |
| Release buffer trước khi HTTP writer gửi | Use-after-release / lỗi ReferenceCount | Chuyển ownership đúng tầng, writer release |
| Release pooled buffer hai lần | `IllegalReferenceCountException` | Rõ ownership, chỉ một release tương ứng |
| Giữ Netty `ByteBuf` trong cache lâu | Native memory retained, lifecycle phức tạp | Copy bounded data/deserialize object, release |
| `onBackpressureBuffer()` không giới hạn | RAM tăng khi consumer chậm | Bounded policy, discard/replay semantics |
| `flatMap` concurrency cao | Concurrent buffers/requests nhiều | Giới hạn concurrency/prefetch |
| Tăng codec limit lên 100MB vì một file | Mỗi request có thể ăn memory lớn | Đổi API streaming/file-based |
| Chỉ nhìn `-Xmx` khi container OOMKill | Bỏ qua native/direct/thread stacks | RSS/cgroup + NMT + allocator gauges |
| Dùng Java heap dump để tìm mọi native bytes | Không thấy full off-heap allocations | Netty meters/NMT/native memory tools |
| Đặt `-Xmx` sát container limit | Thiếu headroom native/direct | Budget heap, direct, metaspace, stacks, TLS |
| Bật Netty paranoid leak detection trên mọi pod | Overhead lớn/log volume | Test/canary có kiểm soát |
| Không cancel subscriptions khi client disconnect | Buffers/queues còn giữ | onCancel/doFinally, release, cleanup |
| Disable backpressure bằng custom hot publisher | Memory phụ thuộc tốc độ producer | Bounded queue, rate control, drop/replay policy |

## 25. Quy trình điều tra khi OOM hoặc GC latency tăng

1. **Nhìn loại lỗi và nơi sinh:** JVM heap OOM, direct buffer memory OOM, Netty native OOM, container OOMKill hay HTTP 413/500? Chúng khác nhau.
2. **Xác định memory budget:** `-Xmx`, `-Xms`, `MaxDirectMemorySize`, cgroup limit, JVM version, OS và server stack.
3. **Ghi throughput và concurrency:** requests/sec, active HTTP streams, file uploads, SSE/WS clients, downstream latency.
4. **So sánh heap used/after-GC** với `RSS` và container memory. Heap thấp + RSS cao thường dẫn tới điều tra native memory.
5. **Nếu WebFlux/Netty:** kiểm tra Netty allocator active/used direct/heap gauges, connection queues, event-loop pending tasks.
6. **Nếu MVC/Tomcat:** kiểm tra worker threads, connector buffers, in-flight requests, async tasks, multipart/temp disk.
7. **Xem endpoints/operations gây peak:** JSON aggregate, Base64, `collectList`, multipart, streaming download, compression/TLS.
8. **Kiểm tra cancellation/error paths:** buffer có release khi exception/timeout/client disconnect không?
9. **Bật profiling trong test:** NMT, JFR, heap dump, Netty leak detection theo scope phù hợp.
10. **Load test tái lập:** cùng concurrency, payload sizes, slow-client simulation, restart/gc/warm-up. So sánh metrics trước/sau fix.
11. **Sửa nguyên nhân trước:** bound codec, stream thay vì aggregate, release buffers, cap queues, lower concurrency, fix leak.
12. **Chỉ sau đó điều chỉnh limits:** nâng `-Xmx`/direct/container khi có số đo và headroom thực, rollout có canary và alert.

### Phân biệt 4 kiểu sự cố

| Triệu chứng chính | Khả năng | Nơi điều tra trước |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Heap live set/allocations quá lớn | Heap dump, GC, DTO/caches/JSON aggregation |
| `Cannot reserve ... direct buffer memory` | Java NIO direct cap/usage | Direct BufferPoolMXBean, flags, Netty/native metrics |
| Netty `OutOfDirectMemoryError` hoặc leak warning | Netty allocator/refcount/cgroup | Active/used Netty memory, Buffer ownership |
| Pod OOMKilled nhưng không có Java OOME | Total cgroup memory vượt limit | RSS/cgroup, NMT, heap + native breakdown |
| `DataBufferLimitException` | Codec aggregation vượt maxInMemorySize | Kiểu decode và codec limits, status mapping |
| HTTP `413` tại NGINX/WAF trước backend | Proxy body-size policy | Edge logs/config, không sửa heap ngay |

Một request bị trả 413 **không phải** một JVM OOM. Đó có thể là cơ chế bảo vệ hoạt động đúng. Đừng giải quyết lỗi 413 bằng cách tăng memory toàn bộ server khi yêu cầu thực tế nên stream và giới hạn ở endpoint.

## 26. Kiểm thử tự động và kiểm thử tải

### 26.1. Integration test với WebTestClient

Trong project demo có `spring-boot-starter-test`, tạo `src/test/java/demo/buffers/BufferRuntimeApplicationTests.java`:

~~~java
package demo.buffers;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BufferRuntimeApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void digestUsesBoundedStreaming() {
        client.post()
            .uri("/api/digest")
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .bodyValue("hello".getBytes(StandardCharsets.UTF_8))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.bytes").isEqualTo(5)
            .jsonPath("$.sha256").isEqualTo(
                "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
            );
    }

    @Test
    void streamingOutputHasCorrectByteCount() {
        client.get()
            .uri("/api/stream?chunks=4")
            .exchange()
            .expectStatus().isOk()
            .expectBody(byte[].class)
            .consumeWith(result ->
                assertEquals(16384, result.getResponseBody().length)
            );
    }

    @Test
    void jsonSmallPayloadIsDecoded() {
        client.post()
            .uri("/api/json")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "hi"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.textLength").isEqualTo(2);
    }
}
~~~

**Bổ sung import để test biên dịch:** `import java.util.Map;` trong file test trước class declaration. Đoạn trên để phần import riêng dễ đọc, nhưng khi copy vào source thật **phải thêm đúng import**. Không cần dùng library ngoài `spring-boot-starter-test` nếu dependencies tương thích.

Lệnh chạy:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Một test chạy thành công xác nhận chức năng demo chứ **không chứng minh memory leak-free dưới tải thật**. Kiểm thử tải vẫn phải xem allocator metrics, RSS, heap/GC và cancellation cases.

### 26.2. Test tải phải có nhiều kiểu client

Không chỉ gửi 100 requests liên tiếp. Cần:
- 1, 10, 100, 1000 concurrent uploads ở nhiều payload sizes.
- Slow upload sender: gửi mỗi chunk cách vài giây.
- Slow download consumer: cố tình giới hạn receive rate.
- Cancel giữa upload và download.
- Upload đúng 8 MiB và vượt 8 MiB.
- JSON 10 KiB, 256 KiB, >256 KiB.
- Multipart nhiều parts và file vừa vượt disk threshold.
- WebSocket/SSE subscribers lâu.
- Restart/cancel/error paths, theo dõi `active.direct.memory` có về baseline không.

Mọi bài load test phải có **ngưỡng an toàn và môi trường cô lập**, không dùng production endpoint hoặc tệp thật có dữ liệu cá nhân. Trước khi chạy nhiều concurrent uploads, tính số request × kích thước payload và giới hạn network/disk/cgroup.

## 27. Checklist thiết kế HTTP memory an toàn

- [ ] Phân biệt heap, Java NIO direct, Netty native/pooled, kernel socket và proxy buffers.
- [ ] Không coi `-Xmx` là toàn bộ process limit; có headroom native/direct/TLS/thread stacks.
- [ ] Hiểu ownership của `DataBuffer` và `PooledDataBuffer`, release đúng bên tiêu thụ.
- [ ] Khi chỉ đọc DataBuffer rồi bỏ, dùng `try/finally` và `DataBufferUtils.release`.
- [ ] Khi chuyển buffer cho HTTP writer, **không release trước khi writer tiêu thụ**.
- [ ] Những buffers bị discard/cancel được giải phóng, dùng `doOnDiscard` phù hợp.
- [ ] Không giữ `DataBuffer` references trong unbounded lists/caches.
- [ ] Không dùng `collectList()` hoặc join vô hạn cho request/response lớn.
- [ ] `spring.http.codecs.max-in-memory-size` đặt đúng theo Boot 3.5, hiểu per-aggregation semantics.
- [ ] Có giới hạn raw body size riêng, upload streaming vẫn bị cap tổng bytes.
- [ ] Multipart có giới hạn số part, RAM per-part và disk per-part.
- [ ] Không nhầm header-size limit, codec limit, file-size limit và connection buffer size.
- [ ] Download lớn stream theo chunks hoặc dùng cơ chế file/resource phù hợp.
- [ ] Reactive sources tôn trọng backpressure; bounded buffers/flatMap concurrency.
- [ ] Slow clients, cancellation, error/timeout đều cleanup streams/buffers.
- [ ] Metric heap/GC, JVM BufferPool, Netty direct used/active, RSS/cgroup được theo dõi cùng nhau.
- [ ] Heap dump/NMT/Netty leak detection được dùng đúng cho từng loại memory.
- [ ] Có load test concurrency + slow-client + cancel + restart trước production.
- [ ] Không tăng codec limit, `-Xmx` hoặc direct memory chỉ để che leak/OOM mà chưa đo.
- [ ] Actuator/JMX/diagnostic endpoints được bảo vệ khỏi Internet.

## 28. Câu hỏi ôn tập

**1.** Tại sao JVM có `-Xmx512m` vẫn có thể bị container OOMKilled ở giới hạn 768 MiB?

**Đáp án:** `-Xmx` chỉ giới hạn Java heap; process còn direct/native memory, metaspace, code cache, stacks, TLS/transport và cgroup accounting khác. Cần quan sát RSS/cgroup và phân bổ headroom.

**2.** `ByteBuffer.allocateDirect` có tạo Java object không?

**Đáp án:** Có wrapper object trên heap, nhưng vùng chứa bytes có thể ở off-heap/native memory. Direct không đồng nghĩa mọi I/O đều zero-copy.

**3.** Netty `used.direct.memory` cao sau khi tải giảm thì chắc chắn leak?

**Đáp án:** Không. Pooled allocator có thể giữ reserved memory để tái sử dụng. Quan sát `active.direct.memory`, requests còn sống, trends sau warm-up và leak detection.

**4.** Mọi `DataBuffer` trong WebFlux đều phải tự release ở controller?

**Đáp án:** Không. Khi framework codec/HTTP writer sở hữu buffer, framework xử lý; khi ứng dụng tự consume inbound `Flux<DataBuffer>` hoặc giữ pooled buffer riêng thì phải quản lý release/retain đúng lifecycle.

**5.** Tại sao `DataBuffer.readableByteBuffers()` cần try-with-resources?

**Đáp án:** Iterator có lifecycle riêng và phải đóng; views không được giữ sau iteration/release của DataBuffer.

**6.** `spring.http.codecs.max-in-memory-size=256KB` có từ chối mọi upload 512 KiB không?

**Đáp án:** Không. Nó áp dụng khi codec phải aggregate. Streaming `Flux<DataBuffer>` có thể vượt 256 KiB, nên phải tự đặt limit tổng byte và limits ở các tầng khác.

**7.** Khi `@RequestBody Mono<JsonRequest>` decode một JSON quá lớn, lỗi nào có thể xảy ra?

**Đáp án:** `DataBufferLimitException` khi codec aggregation vượt giới hạn. HTTP status cuối cùng cần được mapping và test theo app/framework.

**8.** Vì sao dùng `collectList()` trên `Flux<DataBuffer>` nguy hiểm?

**Đáp án:** Giữ toàn bộ buffer references trước khi hoàn tất, làm memory tăng theo body/response; nếu không release đúng còn gây pooled refcount leak.

**9.** Backpressure có tự hạn chế mọi application queues không?

**Đáp án:** Không. Hot producers, unbounded `onBackpressureBuffer`, `flatMap` prefetch hoặc transport queues có thể vẫn tăng memory. Cần bound queues và xử lý slow consumers.

**10.** `jvm.buffer.memory.used` có bằng tổng Netty direct bytes và process RSS không?

**Đáp án:** Không. JVM BufferPoolMXBean chỉ phản ánh các pools nó thống kê. Netty có allocator meters riêng; RSS chứa thêm các vùng nhớ khác.

**11.** Bài demo SHA-256 dùng `Mono.defer(...)` để làm gì?

**Đáp án:** Tạo `MessageDigest` và counter riêng cho mỗi subscription/request; không dùng mutable state shared giữa requests hoặc subscriptions lặp.

**12.** Endpoint `/api/stream?chunks=4` tạo chính xác bao nhiêu response body bytes?

**Đáp án:** 4 × 4096 = **16384 bytes**. HTTP framing overhead không nằm trong file body mà `curl -o` ghi.

**13.** Khi upload đang bị từ chối vì >8 MiB, cần xử lý buffer hiện tại thế nào?

**Đáp án:** Release buffer đã nhận trong `finally` và bảo đảm những buffers bị discard/cancel cũng được release; không giữ references sau khi error.

**14.** Tăng `-XX:MaxDirectMemorySize` có sửa được Netty leak không?

**Đáp án:** Không. Nó có thể trì hoãn lỗi hoặc thay failure mode, nhưng leak/ownership vẫn sai; còn cần cân nhắc Netty native allocations và cgroup budget.

**15.** Vì sao không nên dựa vào `Thread.sleep` để giảm throughput và “chữa” memory pressure trong WebFlux?

**Đáp án:** Blocking event loop phá khả năng xử lý nhiều kết nối và có thể tăng pending queues. Phải dùng backpressure, rate/concurrency limits và async processing.

### Bài tập mở rộng

1. Thử `/api/digest` với payload 512 KiB và giải thích vì sao không bị codec 256KB chặn nếu đi qua raw streaming path; sau đó thử >8 MiB và xem status.
2. Thay `Flux<DataBuffer>` của download bằng `Mono<byte[]>` 4 MiB, đo heap/GC khác nhau dưới concurrency 50–100 clients, không khẳng định kết quả trước khi đo.
3. Viết test cancellation giữa upload để chắc chắn `DataBufferUtils.release` chạy cho consumed và discarded buffers.
4. Bật Netty allocator metrics khi runtime hỗ trợ, theo dõi `used.direct.memory` và `active.direct.memory` trước/trong/sau load.
5. Thử JSON body >256 KiB và map `DataBufferLimitException` sang 413 theo hợp đồng.
6. Thử multipart file và ghi nhận memory-vs-disk threshold, số parts và disk quota.
7. Đặt container memory limit thấp trong môi trường test, thay đổi `-Xmx` và `MaxDirectMemorySize` có kiểm soát rồi đo RSS/GC/allocator; tránh kích hoạt OOM trên production.
8. Đánh giá long-lived SSE/WebSocket sessions: mỗi session giữ buffer/queue bao nhiêu, slow consumer policy và cleanup sau disconnect.
9. Dùng JFR/NMT kết hợp Micrometer để so sánh heap/native/transport hotspots qua một đợt load có giới hạn.

## 29. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html)
- [Spring Framework 6.2 — WebFlux Reactive Core, Limits, Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebFlux Config: HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Framework 6.2 — DataBuffer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/core/io/buffer/DataBuffer.html)
- [Spring Framework 6.2 — DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Boot 3.5 — Common Application Properties: spring.http.codecs / WebFlux multipart](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Actuator Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Reactor Netty — HTTP Server and Buffer Allocator Metrics](https://projectreactor.io/docs/netty/release/reference/http-server.html)
- [Reactor Netty — HTTP Client and ByteBuf Leak Detection](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Project Reactor — Backpressure and Flux](https://projectreactor.io/docs/core/release/reference/)
- [Oracle JDK 17 — Java Command, MaxDirectMemorySize và NMT](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle JDK 17 — Diagnostic Command jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Netty — Reference-counted Objects](https://netty.io/wiki/reference-counted-objects.html)
- [Micrometer — JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)

**Kết luận:** Heap, Java direct memory, Netty pooled buffers và HTTP codec buffers có **ownership, limits và metrics khác nhau**. Đối với dữ liệu HTTP lớn, ưu tiên streaming có giới hạn, release đúng `DataBuffer` khi tự tiêu thụ, tôn trọng backpressure và tách biệt codec limit với total request limit. Chẩn đoán bộ nhớ bằng **heap + direct allocator active/used + RSS/cgroup + concurrency**, không chỉ nhìn `-Xmx` hoặc một ngoại lệ 413.
