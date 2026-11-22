# DataBuffer, PooledDataBuffer và bộ nhớ ngoài heap trong Spring WebFlux

## 1. Vai trò của DataBuffer trong WebFlux

HTTP truyền dữ liệu dưới dạng byte. Trước khi JSON trở thành một object Java hoặc một object Java được encode thành JSON, dữ liệu phải đi qua một lớp biểu diễn byte. Trong Spring WebFlux, lớp trừu tượng đó là `DataBuffer`.

`DataBuffer` giúp Spring làm việc với nhiều nền tảng I/O khác nhau mà không buộc toàn bộ ứng dụng phụ thuộc trực tiếp vào `java.nio.ByteBuffer` hay Netty `ByteBuf`. Tùy server/client đang chạy, implementation có thể là buffer trên heap, direct buffer hoặc buffer được quản lý bằng pool.

Các thành phần chính:

- **`DataBuffer`**: biểu diễn một vùng byte có vị trí đọc và ghi.
- **`DataBufferFactory`**: tạo buffer mới hoặc wrap dữ liệu byte đã có.
- **`PooledDataBuffer`**: mở rộng DataBuffer với cơ chế reference counting để quản lý buffer dùng chung pool.
- **`DataBufferUtils`**: các thao tác tiện ích như join, retain, release, read, write, skip và take.
- **`Decoder` / `Encoder`**: chuyển giữa luồng DataBuffer và object cấp cao hơn.
- **`HttpMessageReader` / `HttpMessageWriter`**: nối codec với ngữ nghĩa HTTP request/response.

Sơ đồ đọc request:

~~~text
HTTP socket
    |
    v
Server runtime (ví dụ Reactor Netty)
    |
    v
ByteBuf / byte buffer
    |
    v
DataBuffer
    |
    v
HttpMessageReader + Decoder
    |
    v
Mono<DTO> / Flux<DTO>
    |
    v
Controller / HandlerFunction
~~~

Sơ đồ ghi response:

~~~text
Controller / HandlerFunction
    |
    v
Mono<DTO> / Flux<DTO>
    |
    v
HttpMessageWriter + Encoder
    |
    v
DataBuffer
    |
    v
Server runtime
    |
    v
HTTP socket
~~~

Trong hầu hết controller thông thường, bạn chỉ làm việc với DTO, String, Resource, Mono hoặc Flux; Spring và codec quản lý buffer ở bên dưới. Bạn cần hiểu ownership và release khi trực tiếp đọc/ghi DataBuffer, viết custom codec, thao tác raw request/response body hoặc giữ buffer qua callback bất đồng bộ.

## 2. Heap memory, direct memory và off-heap

### 2.1. Buffer trên heap

Buffer trên heap sử dụng vùng nhớ thuộc Java heap. JVM quản lý vòng đời object thông qua garbage collector. Khi object không còn được tham chiếu và đủ điều kiện thu gom, GC có thể thu hồi vùng nhớ.

Ưu điểm:

- Dễ quan sát bằng heap dump và công cụ phân tích object.
- Có vòng đời gắn với object Java và GC.
- Thích hợp với nhiều xử lý dữ liệu thông thường.

Hạn chế trong I/O mạng: khi native I/O cần địa chỉ vùng nhớ native, dữ liệu trên heap có thể cần được copy sang vùng nhớ trung gian hoặc direct buffer tùy implementation.

### 2.2. Direct buffer và off-heap memory

`ByteBuffer.allocateDirect` tạo direct buffer có vùng dữ liệu nằm ngoài Java heap. Direct buffer hữu ích cho I/O native vì runtime có thể làm việc với vùng nhớ native mà giảm một số bước copy.

Ưu điểm:

- Có thể giảm copy giữa Java heap và native I/O.
- Phù hợp với thao tác socket, file channel và networking có lưu lượng lớn.

Chi phí:

- Cấp phát/giải phóng direct memory thường đắt hơn cấp phát object heap thông thường.
- Bộ nhớ này không nằm trong phần heap được giới hạn trực tiếp bởi `-Xmx`.
- Việc thu hồi có cơ chế và thời điểm khác với object heap; không nên dựa vào GC để quản lý buffer pooled theo từng request.
- Nếu giữ buffer lâu hoặc không trả buffer về pool, direct memory có thể tăng và gây lỗi thiếu bộ nhớ native.

**Off-heap không có nghĩa là bộ nhớ vô hạn hoặc không cần quản lý.** Process vẫn bị giới hạn bởi RAM, giới hạn container, giới hạn direct memory và tài nguyên native của hệ điều hành.

### 2.3. Vì sao networking thường dùng pool?

Cấp phát và giải phóng buffer native liên tục có thể tốn chi phí. Pool cho phép tái sử dụng vùng nhớ đã cấp phát thay vì tạo vùng mới cho mọi lần đọc/ghi.

Reactor Netty mặc định sử dụng direct memory và pooled buffer cho networking. Khi buffer được trả về pool, vùng nhớ có thể vẫn được allocator giữ lại để tái sử dụng. Vì vậy:

- Bộ nhớ direct đang được allocator giữ không nhất thiết đồng nghĩa với leak.
- Chỉ nhìn RSS hoặc số liệu heap không đủ kết luận có leak.
- Cần theo dõi active allocated memory, xu hướng theo thời gian và leak detector.
- Pooled buffer phải có ownership rõ ràng để allocator biết khi nào được phép tái sử dụng.

### 2.4. Pooled không đồng nghĩa với direct

Hai khái niệm trả lời hai câu hỏi khác nhau:

| Khái niệm | Câu hỏi |
| --- | --- |
| Heap / direct | Vùng dữ liệu nằm ở đâu? |
| Pooled / không pooled | Vùng nhớ được tái sử dụng theo cơ chế nào? |
| Reference counted | Khi nào vùng nhớ có thể được trả về hoặc giải phóng? |

Một buffer có thể dùng cơ chế pooling và reference counting; không nên suy luận rằng mọi DataBuffer đều là PooledDataBuffer hoặc mọi buffer direct đều do ứng dụng tự release.

## 3. DataBuffer: API biểu diễn byte

### 3.1. Những khả năng chính

DataBuffer cung cấp các thao tác tương tự ByteBuffer, cùng một số tiện ích:

- Đọc và ghi byte.
- Có vị trí đọc và vị trí ghi độc lập.
- Không cần gọi `flip()` để chuyển từ ghi sang đọc theo cách của ByteBuffer.
- Có thể tăng capacity khi cần, tùy implementation.
- Lấy số byte còn đọc được qua `readableByteCount()`.
- Truy cập dữ liệu dưới dạng ByteBuffer, InputStream hoặc OutputStream.
- Tìm byte trong vùng dữ liệu.

Ví dụ đọc nội dung:

~~~java
int size = buffer.readableByteCount();
byte[] bytes = new byte[size];
buffer.read(bytes);
~~~

`readableByteCount()` là số byte từ read position hiện tại tới write position. Nó không nhất thiết bằng capacity hoặc tổng số byte đã từng được ghi vào buffer.

### 3.2. Vị trí đọc và ghi độc lập

Một DataBuffer có read position và write position. Khi ghi dữ liệu, write position tiến lên; khi đọc, read position tiến lên. Vì hai vị trí độc lập, không cần lật buffer như quy trình quen thuộc của ByteBuffer.

~~~java
DataBuffer buffer = factory.allocateBuffer(16);

buffer.write("hello".getBytes(StandardCharsets.UTF_8));

int readable = buffer.readableByteCount();
byte[] result = new byte[readable];
buffer.read(result);
~~~

Trong ứng dụng WebFlux, thường lấy factory từ request/response thay vì tự chọn implementation:

~~~java
DataBufferFactory factory = exchange.getResponse().bufferFactory();
DataBuffer output = factory.allocateBuffer(128);
~~~

Factory có thể là `NettyDataBufferFactory` khi dùng Reactor Netty hoặc `DefaultDataBufferFactory` trong các môi trường khác.

### 3.3. Allocate và wrap

`DataBufferFactory` thường được dùng theo hai cách:

~~~java
DataBuffer allocated = factory.allocateBuffer(1024);

byte[] source = "hello".getBytes(StandardCharsets.UTF_8);
DataBuffer wrapped = factory.wrap(source);
~~~

- `allocateBuffer` tạo buffer mới với capacity ban đầu tùy chọn.
- `wrap` tạo DataBuffer bao quanh một byte[] hoặc ByteBuffer hiện có; nó không có nghĩa là copy toàn bộ byte sang một mảng mới.

Không sửa mảng nguồn sau khi wrap nếu nơi khác vẫn đang đọc cùng vùng dữ liệu. Với buffer pooled, vẫn phải tuân theo quy tắc ownership và release của implementation.

### 3.4. Đọc byte thành String

Ví dụ đơn giản:

~~~java
int size = buffer.readableByteCount();
byte[] bytes = new byte[size];
buffer.read(bytes);

String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Đoạn trên tiêu thụ vùng byte đọc được vì read position tiến lên. Nếu cần đọc lại, phải chủ động quản lý vị trí hoặc tạo bản sao dữ liệu phù hợp. Không giả định DataBuffer là một immutable byte array.

Với dữ liệu text, cần tôn trọng ranh giới ký tự UTF-8. Một ký tự có thể trải qua nhiều buffer; không decode từng chunk độc lập rồi ghép String nếu chunk có thể kết thúc giữa một multi-byte sequence. Hãy dùng codec hoặc decoder có trạng thái phù hợp.

## 4. PooledDataBuffer và reference counting

### 4.1. Reference count hoạt động thế nào?

PooledDataBuffer mở rộng DataBuffer bằng cơ chế đếm tham chiếu. Khi một pooled buffer được cấp phát, reference count ban đầu là 1.

- `retain()` tăng reference count thêm 1.
- `release()` giảm reference count đi 1.
- Khi reference count về 0, buffer được giải phóng hoặc trả lại pool để tái sử dụng.
- Khi reference count vẫn lớn hơn 0, buffer chưa được phép tái sử dụng vì vẫn còn owner đang giữ nó.

Ví dụ về mặt khái niệm:

~~~text
allocate buffer
refCount = 1
     |
     +-- retain()  -> refCount = 2
     |
     +-- release() -> refCount = 1
     |
     +-- release() -> refCount = 0
                         |
                         v
                 memory can be recycled
~~~

Reference count không phải số biến Java đang trỏ tới object. Nó là số ownership reference mà cơ chế pooled buffer đang theo dõi.

### 4.2. Vì sao cần reference counting?

Giả sử Netty nhận dữ liệu từ socket vào direct buffer. Nếu framework trả buffer về pool ngay khi controller vừa nhận một tham chiếu Java, vùng nhớ có thể bị tái sử dụng cho request khác trong khi code hiện tại vẫn đang đọc. Kết quả có thể là dữ liệu bị thay đổi, lỗi truy cập hoặc crash.

Reference counting ngăn việc tái sử dụng sớm: buffer chỉ được trả pool khi tất cả ownership reference đã được release.

### 4.3. Dùng DataBufferUtils thay vì cast

Không nên cast mọi DataBuffer thành PooledDataBuffer:

~~~java
PooledDataBuffer pooled = (PooledDataBuffer) buffer;
pooled.release();
~~~

Một số implementation không pooled, nên cast có thể lỗi. Dùng tiện ích của Spring:

~~~java
DataBufferUtils.retain(buffer);
DataBufferUtils.release(buffer);
~~~

Các phương thức này kiểm tra implementation và thực hiện retain/release khi buffer hỗ trợ cơ chế tương ứng. `DataBufferUtils.release` cũng hỗ trợ các buffer có khả năng đóng như `CloseableDataBuffer`.

### 4.4. Mỗi ownership phải có điểm kết thúc

Một nguyên tắc hữu ích:

- Khi code nhận ownership của một buffer và tiêu thụ xong, code đó phải release ownership.
- Khi code chuyển buffer cho một thành phần downstream chịu trách nhiệm tiêu thụ, ownership được chuyển tiếp; không release sớm trước khi downstream đọc.
- Khi cần giữ buffer vượt quá thời điểm owner hiện tại có thể giải phóng, retain để tạo thêm một ownership reference; release reference bổ sung khi dùng xong.
- Mỗi lần retain phải có một lần release tương ứng.
- Không release cùng một ownership nhiều lần.

Không được release buffer chỉ vì một callback kết thúc nếu buffer vẫn được downstream sử dụng. Ngược lại, không giữ buffer trong collection/cache mà không có chính sách release khi complete, error hoặc cancel.

## 5. Ownership trong reactive pipeline

### 5.1. Chuyển ownership xuống downstream

Khi một buffer được phát qua Publisher, thành phần nhận cần biết mình đang làm gì với nó:

1. Đọc và tiêu thụ ngay, sau đó release.
2. Chuyển nguyên buffer sang writer/consumer tiếp theo; consumer đó chịu trách nhiệm release theo hợp đồng.
3. Giữ buffer để xử lý bất đồng bộ sau callback; cần retain nếu owner trước có thể release, rồi release khi hoàn tất.
4. Bỏ buffer do filter/skip/cancel; phải có discard cleanup phù hợp.

Ví dụ, nếu chỉ chuyển raw request body thành response body:

~~~java
return exchange.getResponse()
    .writeWith(exchange.getRequest().getBody());
~~~

Trong mô hình chuyển tiếp này, code không đọc byte hoặc giữ buffer riêng; response writer tiêu thụ các buffer được chuyển sang nó. Không gọi release trước khi writer ghi xong.

### 5.2. Đọc rồi bỏ buffer

Nếu ứng dụng trực tiếp tiêu thụ request DataBuffer để lấy byte hoặc tính checksum, nó phải release buffer sau khi đọc xong:

~~~java
byte[] copy;

try {
    copy = new byte[buffer.readableByteCount()];
    buffer.read(copy);
}
finally {
    DataBufferUtils.release(buffer);
}
~~~

Nếu thao tác đọc phát exception, khối finally vẫn release. Nếu buffer được chuyển cho downstream, không áp dụng đoạn release này trước khi downstream hoàn tất.

### 5.3. Giữ buffer qua một callback bất đồng bộ

Có những trường hợp buffer cần sống lâu hơn callback đang nhận nó. Ví dụ, một thành phần cần giữ dữ liệu để xử lý sau khi callback trả về. Khi source có thể release buffer sau callback, cần retain trước khi giữ và release reference bổ sung sau khi xử lý xong.

~~~java
DataBufferUtils.retain(buffer);

return processLater(buffer)
    .doFinally(signal -> DataBufferUtils.release(buffer));
~~~

Đây là khung minh họa về ownership. Chỉ dùng khi bạn hiểu hợp đồng của source và biết reference nào do mình sở hữu. Nếu source không tự release ownership ban đầu, ứng dụng phải release cả reference ban đầu theo đúng hợp đồng. Không thêm retain một cách máy móc vì retain cũng tạo thêm nghĩa vụ release.

### 5.4. Không dùng buffer sau release

Sau khi reference count về 0, vùng nhớ có thể đã được trả về pool và tái sử dụng. Không được tiếp tục:

- Đọc byte.
- Ghi byte.
- Tạo view mới từ buffer.
- Gửi buffer tới một Publisher khác.
- Giữ ByteBuffer view rồi dùng sau khi parent buffer đã release.

Các lỗi này có thể biểu hiện không ổn định vì vùng nhớ được tái sử dụng tùy thời điểm và tải.

## 6. DataBufferUtils: các tiện ích cần biết

### 6.1. release và releaseConsumer

~~~java
DataBufferUtils.release(buffer);
~~~

Giảm reference count nếu buffer là pooled và đang được cấp phát; nếu implementation không pooled thì không cần thao tác reference count.

Dùng làm Consumer:

~~~java
fluxOfBuffers.doOnNext(DataBufferUtils.releaseConsumer());
~~~

`releaseConsumer()` hữu ích khi một API phát lại DataBuffer sau khi ghi/tiêu thụ, và ứng dụng chịu trách nhiệm release các buffer đó.

### 6.2. retain

~~~java
DataBufferUtils.retain(buffer);
~~~

Tăng reference count nếu buffer là pooled. Dùng khi cần tạo thêm một ownership reference để buffer còn sống sau khi owner hiện tại có thể release.

Không retain chỉ vì muốn đọc buffer trong cùng callback đồng bộ; giữ buffer lâu hơn vòng đời hiện tại mới là lý do cần xem xét retain.

### 6.3. join: ghép nhiều buffer thành một

`DataBufferUtils.join` nhận Publisher của nhiều DataBuffer và tạo một DataBuffer tổng hợp. Tùy implementation, kết quả có thể là buffer mới hoặc composite buffer tham chiếu các buffer đầu vào, có thể tránh copy nếu underlying API hỗ trợ.

~~~java
Mono<DataBuffer> joined = DataBufferUtils.join(body);
~~~

Có overload giới hạn số byte:

~~~java
Mono<DataBuffer> joined =
    DataBufferUtils.join(body, 1024 * 1024);
~~~

Giới hạn giúp tránh aggregate request body không kiểm soát. Nếu vượt ngưỡng, Spring phát `DataBufferLimitException`. Khi nguồn lỗi hoặc bị cancel trong lúc join, các buffer đã được tích lũy sẽ được release. Các buffer đầu vào không cần được ứng dụng release riêng sau khi đã chuyển vào join; ownership của chúng được quản lý trong kết quả composite.

**Join không đồng nghĩa luôn copy zero-copy.** Nó có thể dùng composite khi implementation hỗ trợ; nếu không, có thể cần tạo buffer chứa dữ liệu kết hợp.

### 6.4. skipUntilByteCount và takeUntilByteCount

Hai tiện ích này làm việc theo tổng byte chứ không chỉ theo số phần tử Publisher:

- `skipUntilByteCount(source, count)` bỏ qua byte cho tới khi đạt số byte yêu cầu.
- `takeUntilByteCount(source, count)` chuyển tiếp dữ liệu cho tới giới hạn byte.

Chúng hữu ích khi xử lý framing hoặc phân đoạn byte stream. Cần đọc kỹ ownership và discard behavior khi kết hợp với toán tử khác.

### 6.5. read và write

`DataBufferUtils.read` có thể biến Resource hoặc NIO Channel thành `Flux<DataBuffer>`. Một số overload quản lý việc đóng channel khi Publisher kết thúc.

`DataBufferUtils.write` có thể ghi Publisher<DataBuffer> ra OutputStream hoặc NIO Channel. Có một chi tiết quan trọng: các overload ghi ra stream/channel thường phát lại chính các DataBuffer đã ghi và **không tự release buffer nguồn**. Nếu ứng dụng tiêu thụ Flux kết quả, cần gắn `DataBufferUtils.releaseConsumer()` khi thích hợp. API cũng không tự đóng OutputStream/channel; ứng dụng phải quản lý vòng đời tài nguyên đó.

Ví dụ khái niệm:

~~~java
DataBufferUtils.write(source, channel)
    .doOnNext(DataBufferUtils.releaseConsumer())
    .then();
~~~

Đoạn này minh họa việc release các buffer được phát lại sau khi ghi. Việc mở/đóng channel, vị trí ghi và xử lý lỗi phải được quản lý riêng. Với file lớn, ưu tiên streaming thay vì join toàn bộ file vào một buffer.

## 7. Codec và vòng đời DataBuffer

### 7.1. Decoder đọc và phải release

Decoder là thành phần cuối cùng đọc DataBuffer đầu vào trước khi tạo object cấp cao hơn. Nếu decoder đọc xong một buffer và không còn dùng nó, decoder phải release buffer đó.

~~~java
DataBufferUtils.release(dataBuffer);
~~~

Nếu decoder dùng các toán tử có thể prefetch/cache như `flatMap` hoặc `reduce`, hoặc toán tử có thể loại bỏ phần tử như `filter`/`skip`, buffer bị discard vẫn cần được release. Khi đó cần gắn discard hook phù hợp:

~~~java
Flux<DataBuffer> decodedInput = source
    .filter(this::isUseful)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

`doOnDiscard` cần nằm ở vị trí downstream phù hợp để nhận các phần tử mà toán tử upstream loại bỏ. Với pipeline phức tạp, kiểm tra semantics của từng operator và các đường error/cancel.

### 7.2. Encoder tạo buffer và consumer phải release

Encoder tạo DataBuffer chứa byte đầu ra. Thành phần tiêu thụ buffer — ví dụ writer ghi vào HTTP response hoặc client request — chịu trách nhiệm release sau khi đọc xong.

Nếu encoder gặp lỗi trong lúc serialize và buffer chưa được chuyển giao, encoder phải tự release buffer đã cấp phát:

~~~java
DataBuffer buffer = factory.allocateBuffer();
boolean transferred = false;

try {
    buffer.write(bytes);
    transferred = true;
    return buffer;
}
finally {
    if (!transferred) {
        DataBufferUtils.release(buffer);
    }
}
~~~

Sau khi buffer được phát cho consumer, ownership chuyển sang consumer theo hợp đồng của pipeline. Encoder không được release thêm một lần nữa sau khi chuyển giao thành công.

### 7.3. Ứng dụng WebFlux thông thường có cần release mọi thứ không?

Không. Khi dùng các API cấp cao như `@RequestBody DTO`, `bodyToMono`, `bodyToFlux`, `ServerResponse.body` hoặc codec mặc định, Spring quản lý phần lớn vòng đời buffer.

Bạn cần tự quản lý khi:

- Nhận raw `Flux<DataBuffer>`.
- Trả raw DataBuffer từ custom encoder.
- Viết custom Decoder/Encoder hoặc `HttpMessageReader`/`HttpMessageWriter`.
- Lưu buffer qua callback bất đồng bộ.
- Tự thao tác với pooled buffer từ Netty/WebSocket.
- Dùng operator có discard/cancel mà giữ buffer trong queue hoặc cache.

## 8. Streaming hay aggregate?

### 8.1. Aggregate toàn bộ body

Khi dùng `DataBufferUtils.join`, toàn bộ body được giữ dưới dạng một DataBuffer tổng hợp trước khi xử lý. Cách này đơn giản khi cần parse một document nhỏ hoặc gọi API cũ yêu cầu mảng byte.

Hạn chế:

- Bộ nhớ tăng theo kích thước body.
- Một request lớn có thể chiếm nhiều direct/heap memory.
- Nhiều request đồng thời có thể làm tổng bộ nhớ tăng nhanh.
- Cần đặt giới hạn byte và xử lý trường hợp vượt giới hạn.

Không dùng join không giới hạn cho upload file lớn hoặc stream vô hạn.

### 8.2. Xử lý từng chunk

Streaming cho phép xử lý từng DataBuffer khi nó đến, nhờ vậy không cần giữ toàn bộ body trong một buffer lớn.

Ví dụ đếm tổng số byte:

~~~java
Flux<DataBuffer> body = request.getBody();

return body
    .map(buffer -> {
        try {
            return buffer.readableByteCount();
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    })
    .reduce(0L, Long::sum);
~~~

Mỗi buffer được đọc số byte rồi release ngay. Pipeline chỉ giữ số đếm, không giữ toàn bộ body. Nếu thêm operator có thể discard buffer trước khi map, cần thêm discard cleanup đúng vị trí.

### 8.3. Giới hạn và backpressure

Backpressure điều tiết tốc độ phát/tiêu thụ giữa các Publisher. Nó không tự giải phóng buffer mà ứng dụng đã giữ, cũng không ngăn một toán tử aggregate toàn bộ body.

Hãy kết hợp:

- Streaming khi dữ liệu lớn hoặc không có giới hạn cố định.
- `maxByteCount` khi cần aggregate.
- Giới hạn kích thước request ở gateway/server.
- Giới hạn concurrency khi xử lý nhiều file/upload đồng thời.
- Release ngay sau khi tiêu thụ.
- Cleanup khi error/cancel.

## 9. Ví dụ biến đổi DataBuffer an toàn

Giả sử cần chuyển từng buffer sang một buffer mới bằng cùng factory. Ví dụ dưới đây minh họa ownership:

~~~java
Flux<DataBuffer> copyBuffers(
    Flux<DataBuffer> source,
    DataBufferFactory factory
) {
    return source
        .map(input -> {
            byte[] bytes;

            try {
                bytes = new byte[input.readableByteCount()];
                input.read(bytes);
            }
            finally {
                DataBufferUtils.release(input);
            }

            DataBuffer output = factory.allocateBuffer(bytes.length);
            boolean handedOff = false;

            try {
                output.write(bytes);
                handedOff = true;
                return output;
            }
            finally {
                if (!handedOff) {
                    DataBufferUtils.release(output);
                }
            }
        })
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
}
~~~

Phân tích:

1. Pipeline nhận ownership của input và đọc hết phần byte còn lại.
2. `finally` release input kể cả khi copy phát sinh lỗi.
3. Tạo output mới, ghi byte vào đó.
4. Khi map trả output thành công, ownership output chuyển xuống downstream.
5. Nếu ghi output thất bại trước khi chuyển giao, khối finally release output.
6. Nếu một operator downstream giữ output trong queue rồi discard khi cancel/error, discard hook release output.

Đây là ví dụ copy để làm rõ ownership, không phải tối ưu zero-copy. Nếu chỉ cần chuyển tiếp dữ liệu không thay đổi, hãy chuyển nguyên buffer cho writer và để writer tiêu thụ theo hợp đồng thay vì copy không cần thiết.

## 10. Lỗi phổ biến gây memory leak hoặc lỗi dữ liệu

**Lỗi 1 — Đọc DataBuffer rồi quên release.** Buffer pooled không được trả về pool. Giải phóng sau khi tiêu thụ nếu code đang sở hữu buffer.

**Lỗi 2 — Release trước khi downstream đọc.** Writer nhận một buffer đã bị deallocate. Chỉ release sau khi consumer hoàn tất hoặc chuyển ownership đúng cách.

**Lỗi 3 — Gọi retain nhưng không release tương ứng.** Reference count không về 0 và vùng nhớ bị giữ. Mỗi retain phải có điểm release.

**Lỗi 4 — Release cùng ownership nhiều lần.** Có thể gây lỗi reference count hoặc giải phóng sớm. Chỉ owner tương ứng mới release reference của mình.

**Lỗi 5 — Cast mọi DataBuffer sang PooledDataBuffer.** Implementation có thể không pooled. Dùng DataBufferUtils.retain/release.

**Lỗi 6 — Dùng buffer sau release.** Memory có thể đã được tái sử dụng; kết quả đọc không còn đáng tin cậy.

**Lỗi 7 — Filter/skip bỏ buffer nhưng không có discard cleanup.** Buffer bị loại khỏi pipeline có thể không được release. Dùng `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` ở đúng vị trí.

**Lỗi 8 — Cache hoặc giữ buffer qua callback mà không retain.** Owner trước có thể release trước khi callback sau đọc xong. Retain khi cần kéo dài lifetime và release sau khi dùng.

**Lỗi 9 — Join body không giới hạn.** Một payload lớn có thể làm bộ nhớ tăng mạnh. Dùng overload có maxByteCount hoặc streaming.

**Lỗi 10 — Nghĩ direct memory nằm trong Xmx.** Direct memory nằm ngoài heap; cần theo dõi allocator metrics và giới hạn native phù hợp.

**Lỗi 11 — Nghĩ RSS cao luôn là leak.** Pool có thể giữ vùng nhớ để tái sử dụng. Theo dõi active memory theo thời gian và dùng leak detector để xác minh.

**Lỗi 12 — Dùng DataBufferUtils.write rồi giả định nó tự release.** Các overload trả Flux buffer đã ghi và không tự release buffer nguồn. Gắn releaseConsumer khi tiêu thụ Flux kết quả.

**Lỗi 13 — Đóng channel quá sớm.** Write chưa hoàn tất mà channel đã đóng. Quản lý resource theo lifecycle reactive, bao gồm complete/error/cancel.

**Lỗi 14 — Decode UTF-8 độc lập từng chunk.** Một ký tự có thể bị chia giữa hai DataBuffer. Dùng decoder có trạng thái hoặc codec cao cấp.

**Lỗi 15 — Tự tạo byte[] cho file lớn.** Có thể aggregate toàn bộ file vào heap. Dùng streaming resource/channel khi dữ liệu lớn.

**Lỗi 16 — Giữ buffer trong static collection hoặc singleton field.** Lifetime vượt request và không có cleanup rõ ràng. Giữ dữ liệu đã copy nếu cần lưu lâu, hoặc quản lý ownership/expiry/release thật rõ.

**Lỗi 17 — Cho rằng GC sẽ giải phóng pooled Netty buffer đúng lúc.** Reference-counted buffer cần release theo hợp đồng; GC không thay thế release.

**Lỗi 18 — Chỉ nhìn heap dump để tìm direct-memory leak.** Heap dump có thể không cho thấy toàn bộ direct memory đang được allocator sử dụng. Kết hợp allocator metrics, Netty leak detection và process metrics.

## 11. Chẩn đoán direct-memory leak với Reactor Netty

### 11.1. Bật leak detection của Netty

Netty cung cấp leak detector với các mức kiểm tra khác nhau. Có thể bật qua JVM system property, ví dụ:

~~~bash
java -Dio.netty.leakDetection.level=advanced -jar app.jar
~~~

Các mức kiểm tra cao hơn giúp tăng khả năng phát hiện nhưng cũng tăng chi phí CPU và overhead. Dùng mức phù hợp trong môi trường tái hiện lỗi hoặc staging; không bật chế độ nặng tùy tiện trên hệ thống tải cao.

### 11.2. Logger của Reactor Netty

Reactor Netty cung cấp logger:

~~~text
_reactor.netty.channel.LeakDetection
~~~

Logger này mặc định tắt. Có thể đặt mức DEBUG cho logger tương ứng để điều tra buffer leak và xem ownership đã được chuyển tới application/framework ở đâu.

### 11.3. Theo dõi active heap/direct memory

Các metric allocator hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| `reactor.netty.bytebuf.allocator.active.heap.memory` | Số byte đang dùng từ heap buffer pool |
| `reactor.netty.bytebuf.allocator.active.direct.memory` | Số byte đang dùng từ direct buffer pool |

Nếu các giá trị active tăng liên tục theo thời gian và không giảm sau khi workload dừng, cần điều tra ownership/release. Tuy nhiên, một mức nền ổn định có thể là pool giữ buffer để tái sử dụng, không tự động chứng minh leak.

### 11.4. Phân biệt heap pressure và direct-memory pressure

- Heap tăng: xem object retention, collection, cache và heap dump.
- Direct memory tăng: xem pooled buffer ownership, Netty allocator metrics, leak detector và `MaxDirectMemorySize`.
- RSS tăng: xem heap, direct memory, metaspace, thread stacks, native library và memory mapping; RSS không đồng nghĩa heap.
- Container OOM: xem memory limit của container và tổng native + heap, không chỉ Xmx.

### 11.5. Thu hẹp nguyên nhân

Một quy trình thực tế:

1. Ghi nhận workload, endpoint và thời điểm direct memory bắt đầu tăng.
2. So sánh active heap/direct allocator metrics trước, trong và sau tải.
3. Bật leak detection trong môi trường có thể tái hiện.
4. Tìm code trực tiếp dùng DataBuffer, custom codec, raw body, WebSocket hoặc channel.
5. Kiểm tra mọi nhánh complete, error, cancel và discard.
6. Kiểm tra mỗi retain có release tương ứng và buffer không bị release trước consumer.
7. Tạo test tải lặp lại rồi xác minh active memory trở về mức nền phù hợp.

## 12. Ví dụ Spring Boot 3.5.7 + Java 17: đọc raw body có giới hạn

Ví dụ này tạo endpoint nhận binary body và trả về số byte cùng phần preview ở dạng hex. Nó dùng `DataBufferUtils.join` với giới hạn 1 MiB, đọc DataBuffer tổng hợp và release trong `finally`.

Project chỉ cần WebFlux; không cần dependency Netty trực tiếp vì Spring Boot WebFlux quản lý server runtime.

### 12.1. Cấu trúc project

~~~text
webflux-databuffer-demo/
├── pom.xml
├── src/main/java/example/buffer/
│   ├── DataBufferApplication.java
│   └── PayloadController.java
└── src/test/java/example/buffer/
    └── PayloadControllerTest.java
~~~

### 12.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-databuffer-demo</artifactId>
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

### 12.3. `DataBufferApplication.java`

~~~java
package example.buffer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DataBufferApplication {

    public static void main(String[] args) {
        SpringApplication.run(DataBufferApplication.class, args);
    }
}
~~~

### 12.4. `PayloadController.java`

~~~java
package example.buffer;

import java.util.HexFormat;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class PayloadController {

    private static final int MAX_BODY_BYTES = 1024 * 1024;
    private static final int PREVIEW_BYTES = 16;

    public record PayloadSummary(
        int bytes,
        String firstBytesHex,
        boolean previewTruncated
    ) {}

    @PostMapping(
        path = "/api/inspect",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<PayloadSummary> inspect(ServerHttpRequest request) {
        return DataBufferUtils.join(
                request.getBody(),
                MAX_BODY_BYTES
            )
            .map(this::summarizeAndRelease)
            .defaultIfEmpty(new PayloadSummary(0, "", false))
            .onErrorMap(
                DataBufferLimitException.class,
                error -> new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "Request body exceeds the configured limit",
                    error
                )
            );
    }

    private PayloadSummary summarizeAndRelease(DataBuffer buffer) {
        try {
            int totalBytes = buffer.readableByteCount();
            int previewLength = Math.min(totalBytes, PREVIEW_BYTES);

            byte[] preview = new byte[previewLength];
            buffer.read(preview);

            return new PayloadSummary(
                totalBytes,
                HexFormat.of().formatHex(preview),
                totalBytes > previewLength
            );
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    }
}
~~~

Điểm quan trọng trong method `summarizeAndRelease`:

- Controller nhận raw body dưới dạng Publisher<DataBuffer>.
- `join` aggregate body và giới hạn tổng byte ở 1 MiB.
- `readableByteCount` lấy số byte có thể đọc.
- Chỉ copy tối đa 16 byte đầu để tạo preview.
- `finally` release buffer tổng hợp dù đọc thành công hay có exception.
- Nếu body vượt giới hạn, `DataBufferLimitException` được chuyển thành HTTP 413.
- Body rỗng được chuyển thành summary có số byte bằng 0.

Ví dụ này cố ý aggregate một body nhỏ có giới hạn. Với file lớn hoặc stream vô hạn, hãy xử lý từng DataBuffer và release từng chunk thay vì join toàn bộ.

### 12.5. `PayloadControllerTest.java`

~~~java
package example.buffer;

import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.http.MediaType.APPLICATION_OCTET_STREAM;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class PayloadControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsAndReleasesSmallBinaryBody() {
        byte[] payload = new byte[] {0x68, 0x65, 0x6c, 0x6c, 0x6f};

        client.post()
            .uri("/api/inspect")
            .contentType(APPLICATION_OCTET_STREAM)
            .accept(APPLICATION_JSON)
            .bodyValue(payload)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.bytes").isEqualTo(5)
            .jsonPath("$.firstBytesHex").isEqualTo("68656c6c6f")
            .jsonPath("$.previewTruncated").isEqualTo(false);
    }

    @Test
    void rejectsBodyLargerThanConfiguredLimit() {
        byte[] payload = new byte[1024 * 1024 + 1];

        client.post()
            .uri("/api/inspect")
            .contentType(APPLICATION_OCTET_STREAM)
            .bodyValue(payload)
            .exchange()
            .expectStatus().isEqualTo(413);
    }
}
~~~

Test đầu xác minh body 5 byte được đọc và chuyển thành preview hex. Test thứ hai gửi 1 MiB + 1 byte và xác minh endpoint từ chối payload vượt giới hạn. Chạy test:

~~~bash
mvn test
~~~

### 12.6. Chạy và gọi API

Khởi động:

~~~bash
mvn spring-boot:run
~~~

Gửi chuỗi `hello` dưới dạng byte:

~~~bash
curl -i -X POST http://localhost:8080/api/inspect \
  -H "Content-Type: application/octet-stream" \
  -H "Accept: application/json" \
  --data-binary "hello"
~~~

Response body dự kiến:

~~~json
{
  "bytes": 5,
  "firstBytesHex": "68656c6c6f",
  "previewTruncated": false
}
~~~

Gửi body vượt 1 MiB sẽ nhận HTTP 413. Không dùng endpoint aggregate này làm upload endpoint cho file lớn; nó được thiết kế để minh họa quản lý ownership trong một body có giới hạn.

## 13. Checklist trước khi dùng DataBuffer trực tiếp

Trước khi merge code có thao tác raw DataBuffer, hãy kiểm tra:

1. Code đang đọc, ghi, giữ hay chuyển tiếp buffer?
2. Ai là owner hiện tại và ai sẽ release?
3. Có cần retain vì buffer sống lâu hơn callback hiện tại không?
4. Mỗi retain có release tương ứng không?
5. Buffer có bị release trước khi writer/consumer đọc xong không?
6. Có operator nào filter, skip, prefetch, cache hoặc discard buffer không?
7. Đã có `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` đúng vị trí cho nhánh bị loại bỏ chưa?
8. Khi source error hoặc client cancel, buffer đang giữ có được release không?
9. Có aggregate toàn bộ body không? Nếu có, giới hạn byte ở đâu?
10. Có thể xử lý theo chunk để giảm bộ nhớ không?
11. `DataBufferUtils.write` có đang phát lại buffer mà chưa release không?
12. Channel/stream/file resource có được đóng khi complete/error/cancel không?
13. Có đang dùng buffer sau release hoặc giữ view của buffer sau khi parent bị release không?
14. Có test payload lớn, body rỗng, lỗi giữa stream và cancellation không?
15. Có theo dõi active direct-memory metric và bật leak detector khi điều tra không?

## 14. Bài tập tự kiểm tra

1. `DataBuffer` biểu diễn gì? **Một vùng byte có vị trí đọc/ghi và API độc lập với implementation cụ thể.**
2. `DataBufferFactory` có hai nhiệm vụ phổ biến nào? **Allocate buffer mới và wrap byte[]/ByteBuffer có sẵn.**
3. Direct buffer lưu dữ liệu ở đâu? **Ngoài Java heap, thường trong vùng nhớ native.**
4. Vì sao networking thường dùng pooled buffer? **Giảm chi phí cấp phát/giải phóng buffer native bằng cách tái sử dụng.**
5. `PooledDataBuffer` bắt đầu với reference count bằng bao nhiêu? **1.**
6. `retain()` làm gì? **Tăng reference count thêm một.**
7. `release()` làm gì? **Giảm reference count; về 0 thì buffer có thể được giải phóng/trả pool.**
8. Có nên cast mọi DataBuffer sang PooledDataBuffer không? **Không; dùng DataBufferUtils.retain/release.**
9. Khi nào dùng `DataBufferUtils.join`? **Khi cần aggregate một body/stream có giới hạn thành một buffer.**
10. Vì sao join cần maxByteCount? **Để tránh aggregate payload không giới hạn và cạn bộ nhớ.**
11. Khi Decoder đọc xong DataBuffer, ai release? **Decoder chịu trách nhiệm release buffer đầu vào mà nó tiêu thụ.**
12. Khi Encoder tạo buffer đầu ra, ai release sau khi ghi? **Consumer/writer nhận buffer chịu trách nhiệm release.**
13. Vì sao cần `doOnDiscard`? **Để release buffer bị operator loại bỏ do filter/skip/error/cancel hoặc prefetch.**
14. `DataBufferUtils.write` có tự release buffer nguồn không? **Không; cần releaseConsumer khi ứng dụng tiêu thụ Flux kết quả.**
15. Heap dump có luôn cho thấy direct-memory leak không? **Không; cần allocator metrics và leak detector.**
16. RSS cao có luôn chứng minh leak không? **Không; pool có thể giữ memory để tái sử dụng.**
17. Khi nào cần retain? **Khi tạo thêm ownership hoặc giữ buffer sau thời điểm owner hiện tại có thể release.**
18. Nếu giữ buffer qua callback bất đồng bộ, cần làm gì? **Retain theo hợp đồng source và release reference bổ sung khi hoàn tất.**
19. Vì sao không nên decode UTF-8 từng chunk độc lập? **Ký tự nhiều byte có thể bị chia giữa các buffer.**
20. Khi nào nên dùng byte[] thay DataBuffer? **Khi dữ liệu nhỏ, cần object heap độc lập và không cần zero-copy; với stream lớn nên xử lý theo chunk.**

## 15. Ghi nhớ và tài liệu tham khảo

- **`DataBuffer`** là abstraction byte buffer của Spring; **`DataBufferFactory`** tạo hoặc wrap buffer.
- **Heap/direct** mô tả vị trí bộ nhớ; **pooled** mô tả cách tái sử dụng.
- **`PooledDataBuffer`** dùng reference counting: retain tăng, release giảm, về 0 thì có thể trả buffer về pool.
- **Ownership quan trọng hơn số biến Java đang tham chiếu.** Mỗi owner phải biết khi nào được release.
- **`DataBufferUtils`** cung cấp retain, release, join, read, write, skip và take.
- Decoder release buffer đầu vào khi tiêu thụ; consumer của encoder release buffer đầu ra sau khi ghi.
- Dùng `doOnDiscard` khi operator có thể loại bỏ DataBuffer.
- Join phải có giới hạn; stream lớn nên xử lý từng chunk.
- Direct-memory leak không nhất thiết xuất hiện trong heap dump; theo dõi Reactor Netty allocator metrics và leak detection.

Tài liệu chính thức:

1. [Spring Framework Reference — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): DataBuffer, DataBufferFactory, PooledDataBuffer, DataBufferUtils, ownership, decoder và encoder.
2. [Spring Framework Javadoc — DataBuffer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/io/buffer/DataBuffer.html): API đọc/ghi, positions, capacity và các view.
3. [Spring Framework Javadoc — PooledDataBuffer](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/io/buffer/PooledDataBuffer.html): retain, release và reference counting.
4. [Spring Framework Javadoc — DataBufferUtils](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): join, retain/release, read/write, giới hạn byte và releaseConsumer.
5. [Spring Framework Reference — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): DataBuffer trong request/response pipeline và khi nào ứng dụng cần quản lý buffer.
6. [Reactor Netty Reference — Debugging a Memory Leak](https://docs.spring.io/projectreactor/reactor-netty/docs/current/reference/html/index.html#faq.memory-leak): direct memory, pooled buffers, LeakDetection logger và active heap/direct memory metrics.
7. [Netty Reference — Reference Counted Objects](https://netty.io/wiki/reference-counted-objects.html): mô hình reference counting của Netty ByteBuf và ownership.
