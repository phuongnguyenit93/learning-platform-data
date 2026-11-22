# DataBuffer, tham chiếu bộ nhớ và nguy cơ rò rỉ bộ đệm

Trong Spring WebFlux, dữ liệu HTTP có thể đi qua ứng dụng dưới dạng các phần byte liên tiếp: `Flux<DataBuffer>`. Đây là tầng thấp hơn JSON DTO, `String` hoặc `Resource`. Một số `DataBuffer` sử dụng vùng nhớ được tái sử dụng (*pooled memory*), thậm chí là bộ nhớ trực tiếp ngoài Java heap (*direct/off-heap memory*). Khi code của ứng dụng nhận một buffer như vậy, việc không kết thúc đúng vòng đời có thể khiến vùng nhớ không được trả về pool. Khi giải phóng quá sớm, dữ liệu có thể không còn hợp lệ trước lúc bộ phận tiếp theo đọc nó.

**Nguyên tắc xuyên suốt:** không phải mọi `DataBuffer` đều cần ứng dụng gọi `release()`. Cần xác định rõ **ai sở hữu buffer ở mỗi đoạn pipeline**, ai chuyển quyền sở hữu và ai chịu trách nhiệm giải phóng cuối cùng. Dùng API codec cao cấp khi không cần thao tác byte trực tiếp; khi viết custom decoder, filter, proxy hay upload streaming, hãy quản lý lifecycle theo hợp đồng thực tế.

Phạm vi bài: cơ chế `DataBuffer` trong runtime reactive, reference counting và pooled buffers, các tình huống gây leak/double release, cách dùng `DataBufferUtils`, tương tác với Reactor cancellation/backpressure, ví dụ Java chạy được và quy trình chẩn đoán. Ví dụ chính dùng **Spring Boot 3.x + Spring Framework 6.x + Java 17+**; API có thể thay đổi giữa major version.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích sự khác biệt giữa Java heap, direct memory, pooled memory, `ByteBuf` và `DataBuffer`.
- Hiểu `PooledDataBuffer` cùng ý nghĩa của `retain`, `release` và reference count; phân biệt mất quyền sở hữu với buffer đã được giải phóng.
- Xác định điểm cần `DataBufferUtils.release` khi code trực tiếp nhận/đọc buffer và điểm không được tự giải phóng vì đã chuyển quyền cho framework.
- Sử dụng `DataBufferUtils.join` có giới hạn, hiểu vì sao `join` tự quản lý buffer đầu vào nhưng kết quả vẫn cần xử lý lifecycle.
- Giải thích nguy cơ buffer bị bỏ qua khi `filter`/`skip`/prefetch/cancel/error, và vai trò có giới hạn của `doOnDiscard`.
- Viết một endpoint WebFlux nhỏ có cleanup trong `finally`, chạy thử payload hợp lệ và payload vượt giới hạn.
- Đọc cảnh báo leak của Netty và tổ chức kiểm thử kết hợp, chú ý cả memory leak lẫn double release.

## 2. DataBuffer là lớp trừu tượng gì?

`org.springframework.core.io.buffer.DataBuffer` là abstraction byte-buffer từ Spring Core. Trong WebFlux, body HTTP ở tầng thấp có thể là publisher phát từng `DataBuffer`. Một buffer mô tả vùng bytes cùng vị trí đọc và ghi; một HTTP request hoặc response có thể gồm nhiều buffer chứ không đồng nghĩa với một mảng byte duy nhất.

Các API thường gặp:

| API | Ý nghĩa |
| --- | --- |
| `DataBufferFactory.allocateBuffer(capacity)` | Tạo buffer, lựa chọn heap/direct phụ thuộc factory và cấu hình |
| `DataBufferFactory.wrap(byte[])` | Bọc một vùng dữ liệu hiện hữu, không buộc cấp phát/copy payload mới |
| `DataBuffer.write(byte[])` | Ghi bytes vào vị trí ghi hiện tại |
| `DataBuffer.read(byte[])` | Sao chép bytes từ vị trí đọc hiện tại sang mảng đích và tiến vị trí đọc |
| `DataBuffer.readableByteCount()` | Số byte hiện đọc được, không đồng nghĩa toàn bộ capacity |
| `DataBuffer.readPosition()/writePosition()` | Hai vị trí độc lập, không cần `flip()` như một số cách dùng `ByteBuffer` |
| `DataBufferUtils.retain(buffer)` | Giữ thêm một tham chiếu nếu là pooled buffer thích hợp |
| `DataBufferUtils.release(buffer)` | Giải phóng theo loại buffer nếu có thể |
| `DataBufferUtils.join(publisher, maxByteCount)` | Ghép nhiều buffer thành một, kèm giới hạn tổng byte |
| `DataBufferUtils.touch(buffer, hint)` | Đính kèm nhãn debug nếu implementation hỗ trợ leak tracking |

Spring có nhiều implementation. `DefaultDataBuffer` dựa trên Java `ByteBuffer`; `NettyDataBuffer` bọc Netty `ByteBuf` và thường được dùng khi WebFlux chạy trên Reactor Netty. Không giả định mọi server dùng Netty hoặc mọi implementation đều có reference counting theo cùng cách.

Sơ đồ luồng dữ liệu:

```text
HTTP socket / driver
    |
    v
ByteBuf (Netty) hoặc vùng byte do server cung cấp
    |
    v
DataBuffer --> Flux<DataBuffer> --> decoder / custom operator
                                      |
                                      +--> DTO / String / object
                                      |      (buffer gốc được giải phóng khi tiêu thụ xong)
                                      |
                                      +--> tiếp tục Flux<DataBuffer> --> HTTP response
                                              (đơn vị ghi HTTP chịu trách nhiệm theo hợp đồng)
```

Với controller thông thường nhận `@RequestBody Mono<MyDto>`, trả `Mono<MyDto>` và dùng codec mặc định, Spring xử lý phần lớn việc quản lý buffer. Bạn cần đặc biệt quan tâm khi trực tiếp gọi `request.getBody()`, dùng `bodyToFlux(DataBuffer.class)`, viết custom encoder/decoder, transform binary payload, custom filter, cache body hoặc proxy bytes.

## 3. Heap, direct memory và pool: ba khái niệm cần tách biệt

**Java heap** là vùng đối tượng Java được GC theo dõi. Một mảng `byte[]` lớn nằm trên heap có thể làm heap/GC tăng. **Direct/off-heap memory** là bộ nhớ native gần với I/O, có thể làm resident memory (RSS) của process tăng dù biểu đồ heap không tăng tương ứng. **Pooling** là chính sách tái sử dụng vùng nhớ/buffer thay vì liên tục cấp phát lại; pool có thể dùng memory trực tiếp hoặc heap tùy allocator.

Với Netty, `ByteBuf` có thể được lấy từ pooled allocator, có reference count và phải được release đúng số lượng tham chiếu. Khi `refCnt` về 0, buffer có thể được trả về pool; điều đó **không nhất thiết** làm RSS của process giảm ngay, vì pool giữ vùng nhớ để tái sử dụng. Ngược lại, RSS ổn định không chứng minh mọi buffer đều được release đúng.

| Hiện tượng | Diễn giải thận trọng |
| --- | --- |
| Heap tăng đều, GC nhiều | Có thể là object/mảng bị giữ lại, queue không giới hạn, cache hoặc leak object |
| Direct memory/allocator active bytes tăng, leak logs xuất hiện | Có thể là pooled `ByteBuf` không được release hoặc lifetime kéo dài bất thường |
| Direct memory "used" cao nhưng "active" ổn định | Pool có thể đang giữ memory để tái dùng; cần đối chiếu allocator metrics |
| Lỗi `DataBufferLimitException` | Giới hạn lượng byte được gom/giải mã đã bị vượt; **không tự chứng minh** leak |
| `IllegalReferenceCountException` | Thường liên quan use-after-release hoặc release/retain không cân bằng |
| Tăng memory khi có tải, giảm khi tải dừng | Có thể bình thường; cần so sánh nhiều chu kỳ và phân tích retention |

**Phân biệt hai lỗi độc lập:** *resource leak* là tài nguyên không được trả về sau khi sử dụng; *unbounded buffering* là đang giữ quá nhiều dữ liệu cùng lúc. Chúng có thể cùng xảy ra nhưng cách sửa không giống nhau: thêm `release` cho buffer đã hết nhiệm vụ, đồng thời đặt hạn mức buffer/queue/concurrency để tránh gom dữ liệu vô hạn.

## 4. PooledDataBuffer và reference counting

`PooledDataBuffer` mở rộng `DataBuffer` để quản lý vòng đời tài nguyên có thể dùng chung. Khái niệm cơ bản:

- Khi tạo một pooled buffer, reference count ban đầu thường là **1**.
- `retain()` tăng reference count thêm **1** để giữ một quyền sở hữu bổ sung khi cần.
- `release()` giảm reference count một đơn vị; nếu về **0**, vùng nhớ có thể được hoàn trả.
- Sau khi reference count về **0**, code không được tiếp tục đọc, ghi hay truyền buffer đó; thao tác như vậy có thể gặp lỗi truy cập buffer đã giải phóng.
- Nếu một lần `retain` không có lần `release` tương ứng, vùng nhớ có thể bị giữ lại.
- Nếu release nhiều hơn số quyền sở hữu hợp lệ, xảy ra double release/use-after-release.

Dễ hình dung bằng một buffer được chia sẻ **có chủ đích** cho hai bên:

```text
allocate                       refCnt = 1   (A sở hữu một tham chiếu)
A retain trước khi giao cho B   refCnt = 2   (A và B, mỗi bên một tham chiếu)
A hoàn thành và release        refCnt = 1   (B vẫn dùng được)
B hoàn thành và release        refCnt = 0   (buffer được hoàn trả)
```

Không được áp dụng `retain` “cho chắc” vào mọi luồng HTTP: nó tạo thêm nghĩa vụ release. Cũng không được tự gọi `release` hai lần chỉ vì pipeline có hai operator. **Operator không tự tạo quyền sở hữu mới**, trừ khi API hoặc hợp đồng của nó chỉ rõ retain/chuyển quyền.

### 4.1. Vì sao dùng DataBufferUtils thay vì ép kiểu trực tiếp?

Ví dụ:

```java
DataBufferUtils.retain(buffer);
DataBufferUtils.release(buffer);
```

Trong Spring Framework 6.x, `retain` áp dụng hành vi retain khi buffer là loại pooled phù hợp; `release` hỗ trợ `PooledDataBuffer` và một số loại closeable phù hợp. Khi buffer không cần giải phóng theo cơ chế đó, `release` có thể trả `false`. Đừng dùng giá trị `true/false` để suy diễn chính xác refCnt cuối cùng cho mọi implementation.

Hãy đối chiếu API theo phiên bản vì implementation WebFlux/Netty có thể thay đổi; phần nguyên tắc quan trọng là quản lý ownership.

### 4.2. Khi nào cần retain?

Ví dụ code nhận `DataBuffer` từ request, nhưng muốn lưu nó cho một tác vụ bất đồng bộ chạy **sau** lúc đường xử lý ban đầu kết thúc. Nếu thật sự giữ chung buffer, phải có quy trình retain/handoff/release và xử lý thất bại. Tuy nhiên, đây thường là thiết kế phức tạp, rất dễ sai khi cancellation, retry hoặc consumer thứ hai chậm. Với dữ liệu nhỏ, có thể **copy** nội dung sang `byte[]` giới hạn rồi release buffer gốc; với dữ liệu lớn, ưu tiên streaming hoặc tệp tạm quản lý rõ vòng đời.

**Không giữ `DataBuffer` trong singleton, cache hoặc collection vô thời hạn.** Nếu phải cache, hãy cache đối tượng dữ liệu độc lập (đã decode/copy) có hạn mức và eviction rõ ràng.

## 5. Quyền sở hữu buffer: câu hỏi quan trọng nhất

Bất cứ khi nào mã nguồn trực tiếp tạo, nhận, giữ hoặc trả về `DataBuffer`, hãy trả lời:

1. Buffer được ai tạo hoặc chuyển vào operator này?
2. Khi operator xử lý xong, payload được **đọc hết và loại bỏ**, hay **chuyển tiếp cho consumer khác**?
3. Nếu đã tự đọc và dừng xử lý, ai gọi release?
4. Khi chuyển cho framework ghi HTTP, có còn quyền tự release không?
5. Nếu xảy ra error, cancellation, timeout hoặc discard trước khi consumer nhận được, còn ai nắm tài nguyên?
6. Nếu có retain thêm, mỗi tham chiếu đã có điểm release tương ứng chưa?

Bảng kiểm ownership:

| Hành động | Ai thường chịu trách nhiệm? | Quy tắc |
| --- | --- | --- |
| `@RequestBody Mono<Dto>` qua JSON codec mặc định | Codec/framework | Không tự release vì ứng dụng không trực tiếp nhận raw buffer |
| Đọc `DataBuffer` rồi chuyển thành `String`/DTO của riêng mình | Code tiêu thụ cuối cùng | Release trong `finally` sau khi sao chép/đọc xong |
| Thực hiện `DataBufferUtils.join(source)` | `join` quản lý các buffer **đầu vào** | Không tự release lại từng buffer đầu vào |
| Nhận buffer **kết quả** từ `join` rồi decode thủ công | Code nhận kết quả | Release buffer kết quả sau khi xử lý, kể cả decode lỗi |
| Tạo `DataBuffer` và trả cho `ServerHttpResponse.writeWith(...)` | Giai đoạn ghi response theo hợp đồng framework | Không release sớm ngay sau khi giao vào write pipeline |
| Tạo buffer rồi gặp exception trước khi phát ra publisher/transfer | Code tạo buffer | Release trong nhánh failure trước khi chuyển quyền |
| `filter`/`skip` làm rơi buffer đã nhận | Operator/pipeline chịu cleanup theo cơ chế được hỗ trợ | Dùng `doOnDiscard` đúng vị trí và kiểm chứng cả cancel/error |
| Giữ buffer cho xử lý song song ngoài vòng đời nguồn | Bên giữ thêm tham chiếu | Retain có chủ đích, bảo đảm release sau khi xong |
| `DataBufferUtils.write(source, OutputStream/Channel)` | Người dùng API phải xem hợp đồng | Các overload dạng `Flux<DataBuffer>` không tự release nguồn; cần release ở subscriber/đường xử lý thích hợp |

Bảng trên là nguyên tắc, không phải quyền “release tất cả”. Hãy đọc Javadoc của **overload cụ thể**; chẳng hạn `DataBufferUtils.write(source, Path)` trả `Mono<Void>` và có hợp đồng khác overload ghi vào `OutputStream`.

## 6. Những lỗi gây leak và double release

### 6.1. Đọc body raw nhưng không release

**Sai** khi code là consumer cuối và không có nơi khác release:

```java
request.getBody()
        .map(buffer -> {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return new String(bytes, StandardCharsets.UTF_8);
        });
```

Đoạn trên chuyển thành `String` nhưng không có cleanup trong nhánh xử lý. Với pooled buffer, việc này có thể giữ refCnt. Cần giải phóng sau khi đã copy data.

**Đúng hơn** cho một phép chuyển đổi cục bộ:

```java
request.getBody()
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return new String(bytes, StandardCharsets.UTF_8);
            } finally {
                DataBufferUtils.release(buffer);
            }
        })
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

Hai đoạn này là **snippet** trong code có sẵn `request`, không phải class độc lập; import `java.nio.charset.StandardCharsets`, `DataBuffer`, `DataBufferUtils`. `finally` xử lý buffer **đã được gửi vào lambda**; `doOnDiscard` nhằm dọn những phần tử bị một operator upstream tương thích loại bỏ/giữ trong queue. Không mặc định hook bao phủ mọi loại lỗi hoặc áp dụng hai đường release cho cùng một quyền sở hữu. Nếu áp dụng pattern vào pipeline phức tạp, kiểm tra lifecycle thực bằng test cancellation.

Ở tình huống body có thể chứa nhiều chunk, phép `map` tạo nhiều chuỗi con, không tự ghép chúng thành một UTF-8 string hoàn chỉnh. Một ký tự UTF-8 có thể bị chia giữa hai chunk; nếu cần parse một toàn body nhỏ, dùng codec văn bản hoặc `join` có giới hạn. Không nên tùy ý decode mỗi chunk rồi nối chuỗi, vì có thể phá hỏng ký tự đa byte.

### 6.2. Giải phóng trước khi trả buffer downstream

**Sai:**

```java
Flux<DataBuffer> forwarded = request.getBody()
        .doOnNext(DataBufferUtils::release);
return response.writeWith(forwarded);
```

`doOnNext` chạy **trước** khi buffer đi đến writer. Nếu release khiến refCnt về 0, HTTP writer nhận buffer không còn hợp lệ. Đây có thể là nguyên nhân `IllegalReferenceCountException` hoặc nội dung response hỏng.

Nếu chủ đích là **chuyển tiếp** raw buffer, hãy chuyển quyền theo hợp đồng của writer, không tự release trước khi downstream xong. Nếu cần kiểm tra/log nội dung, dùng API không làm thay đổi vị trí đọc nếu có thể và không giữ dữ liệu sau vòng đời hợp lệ.

### 6.3. Retain rồi quên release

**Sai:**

```java
DataBufferUtils.retain(buffer);
savedBuffers.add(buffer); // Không giới hạn, không có cleanup
```

Mỗi retain thêm nghĩa vụ cleanup. Nếu lệnh trên nằm trên mỗi request, bộ nhớ có thể tăng dần theo tổng lưu lượng. Giải pháp là tránh giữ raw pooled buffer; nếu phải giữ, dùng bộ phận quản lý life cycle có close/cancel path, giới hạn dung lượng, và bảo đảm mọi retained reference được release ngay cả khi timeout/lỗi.

### 6.4. Release hai lần

**Sai** nếu chỉ có một quyền sở hữu và không có retain:

```java
try {
    consume(buffer);
} finally {
    DataBufferUtils.release(buffer);
    DataBufferUtils.release(buffer); // Không có tham chiếu thứ hai
}
```

Nguy hiểm tương tự xuất hiện khi một helper đã release rồi caller cũng release vì không thống nhất hợp đồng. Cần định nghĩa rõ helper **tiêu thụ và release** hay **mượn tạm, không release**. Không dựa vào việc release thứ hai có thể bị thư viện bỏ qua: đừng viết logic phụ thuộc hành vi đó.

### 6.5. Tích lũy bytes không giới hạn

**Rủi ro:**

```java
DataBufferUtils.join(request.getBody()) // Không giới hạn tổng byte
```

`join` giúp quản lý reference cho đầu vào nhưng không ngăn body vô hạn hoặc quá lớn gây tiêu tốn bộ nhớ. Với payload nhỏ, dùng overload có giới hạn rõ ràng. Với payload lớn, thiết kế streaming, quota, giới hạn kích thước file và thời gian tiếp nhận thay vì gom tất cả vào một buffer.

### 6.6. Tự subscribe bên trong filter/controller

**Rủi ro:**

```java
request.getBody().subscribe(buffer -> inspect(buffer));
return chain.filter(exchange);
```

Đây là snippet phản ví dụ. Subscription độc lập có thể làm body bị tiêu thụ trước khi downstream đọc, tách lỗi/cancellation khỏi lifecycle của HTTP request, và dễ làm mất cleanup nếu `inspect` ném exception. Thay bằng composition của publisher; chỉ subscribe tại ranh giới có ownership, error, cancel và release rõ ràng. Trong WebFlux HTTP server, framework thường là subscriber cuối.

## 7. DataBufferUtils.join: thuận tiện, nhưng phải hiểu quyền sở hữu

Với `Flux<DataBuffer>` nhỏ và giới hạn kích thước, `DataBufferUtils.join(source, limit)` là lựa chọn thực tế. Nó có thể tạo một buffer chứa bytes được copy, hoặc một **composite buffer** tham chiếu các buffer ban đầu. Cả hai đều yêu cầu nhìn nhận đúng ownership:

```text
Flux<DataBuffer> (A, B, C)
          |
          v
DataBufferUtils.join(source, maxByteCount)
          |
          +-- Thành công: kết quả J sở hữu phần dữ liệu đã ghép
          |                => consumer dùng J xong thì release(J)
          |                => KHÔNG release riêng A, B, C thêm lần nữa
          |
          +-- Lỗi / cancellation trước kết quả:
                           join giải phóng các buffer đã tích lũy
```

Spring Framework Javadoc ghi rõ `join` giải phóng buffer đã tích lũy khi publisher error/cancel; các input được giải phóng như một phần của composite. Điều này không có nghĩa **buffer kết quả** tự được release sau khi callback của ứng dụng đọc xong. Trong trường hợp join trả về `Mono.empty()` vì source không có dữ liệu, không có buffer kết quả cần release.

### 7.1. Mẫu đọc payload nhỏ có giới hạn

```java
Mono<String> body = DataBufferUtils.join(request.getBody(), 1024 * 1024)
        .map(joined -> {
            try {
                byte[] bytes = new byte[joined.readableByteCount()];
                joined.read(bytes);
                return new String(bytes, StandardCharsets.UTF_8);
            } finally {
                DataBufferUtils.release(joined);
            }
        })
        .defaultIfEmpty("");
```

Đây là **snippet** áp dụng khi body thực sự là văn bản UTF-8 và đã có `request`, không thay thế các kiểm tra content-type, định dạng, charset, schema và validation của ứng dụng. `1024 * 1024` tương đương giới hạn 1 MiB ở mức join. Có thể vẫn có bộ nhớ tạm cho các chunk và bản sao `byte[]`; giới hạn này **không** chứng minh tổng footprint chỉ 1 MiB.

Nếu vượt `maxByteCount`, Spring phát `DataBufferLimitException`. Chọn HTTP status hoặc lỗi nghiệp vụ tương ứng (thường HTTP 413 với upload/request body quá lớn). Không nuốt lỗi để trả dữ liệu cắt cụt mà người dùng không hề biết.

### 7.2. Không cần release từng input của join

Sai lầm thường gặp là:

1. `doOnNext(DataBufferUtils::release)` trên nguồn trước `join`; buffer đã release có thể bị `join` sử dụng.
2. Sau `join`, giữ danh sách các input và tự release từng input, trong khi composite cũng sở hữu chúng.
3. Dùng `join` không giới hạn chỉ để đếm bytes hoặc log một request lớn, gây áp lực bộ nhớ không cần thiết.

Với bài toán chỉ **đếm tổng byte**, có thể xử lý từng chunk rồi release ngay, không cần gom cả body. Với bài toán parse JSON, ưu tiên codec của Spring vì codec đã có cơ chế quản lý buffer, giới hạn và xử lý lỗi tương ứng.

## 8. Ví dụ Spring Boot 3.x hoàn chỉnh: reference count và HTTP body có cleanup

Ví dụ này kết hợp hai bài kiểm tra:

1. Khi app bắt đầu, in refCnt của một `NettyDataBuffer` trước/sau `retain` và `release`; đây là ví dụ ownership với **hai tham chiếu hợp lệ**.
2. Endpoint `POST /inspect` đọc body tối đa 1024 byte, giải phóng buffer kết quả trong `finally` và từ chối payload vượt giới hạn.

### 8.1. Chuẩn bị dự án

Dùng Spring Initializr tạo dự án **Java 17+**, **Spring Boot 3.3.x** (hoặc phiên bản 3.x tương thích) và dependency **Spring Reactive Web** / `spring-boot-starter-webflux`. Không cần thêm `spring-boot-starter-web`; trong cấu hình Boot 3.x, có cả Web và WebFlux starter có thể khiến ứng dụng chọn Spring MVC theo quy tắc tự động cấu hình.

Với Gradle/Groovy, phần dependency tương ứng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Dự án Spring Initializr đã quản lý version qua Spring Boot plugin/BOM. Nếu tạo dự án bằng Maven, thêm `spring-boot-starter-webflux` tương ứng thay vì copy block Gradle trên.

Tạo file **`src/main/java/demo/DataBufferLessonApplication.java`**:

```java
package demo;

import java.nio.charset.StandardCharsets;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.PooledByteBufAllocator;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.NettyDataBuffer;
import org.springframework.core.io.buffer.NettyDataBufferFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class DataBufferLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(DataBufferLessonApplication.class, args);
    }

    @Bean
    CommandLineRunner referenceCountDemo() {
        return args -> {
            NettyDataBufferFactory factory =
                    new NettyDataBufferFactory(PooledByteBufAllocator.DEFAULT);
            NettyDataBuffer buffer = factory.allocateBuffer(16);
            ByteBuf nativeBuffer = buffer.getNativeBuffer();

            try {
                buffer.write("abc".getBytes(StandardCharsets.UTF_8));
                System.out.println("1 initial refCnt=" + nativeBuffer.refCnt());

                DataBufferUtils.retain(buffer);
                System.out.println("2 retained refCnt=" + nativeBuffer.refCnt());

                DataBufferUtils.release(buffer);
                System.out.println("3 first release refCnt=" + nativeBuffer.refCnt());
            } finally {
                DataBufferUtils.release(buffer);
                System.out.println("4 final release refCnt=" + nativeBuffer.refCnt());
            }
        };
    }

    @PostMapping(
            path = "/inspect",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> inspect(ServerHttpRequest request) {
        return DataBufferUtils.join(request.getBody(), 1024)
                .map(joined -> {
                    try {
                        // Chỉ copy trong ví dụ để xác nhận số byte.
                        byte[] bytes = new byte[joined.readableByteCount()];
                        joined.read(bytes);
                        return "bytes=" + bytes.length;
                    } finally {
                        DataBufferUtils.release(joined);
                    }
                })
                .defaultIfEmpty("bytes=0")
                .onErrorMap(
                        DataBufferLimitException.class,
                        ex -> new ResponseStatusException(
                                HttpStatus.PAYLOAD_TOO_LARGE,
                                "Body exceeds 1024 bytes", ex)
                );
    }
}
```

Không cần tạo bean `DataBufferFactory` cho HTTP: Spring dùng factory tương ứng với web server. Bean `CommandLineRunner` chỉ minh họa riêng cơ chế Netty reference counting và được thực thi lúc startup; nó không xử lý request thật.

**Giải thích chi tiết:**

- `PooledByteBufAllocator.DEFAULT` cung cấp allocator; `NettyDataBufferFactory.allocateBuffer(16)` cho một `NettyDataBuffer` dựa trên Netty `ByteBuf` có refCnt ban đầu 1.
- `retain` tăng refCnt lên 2; sau một lần `release` còn 1; lần cuối trong `finally` về 0. Có đúng **hai quyền sở hữu**, vì có một lần retain.
- Code không đọc/ghi buffer **sau** lần release cuối; chỉ gọi `refCnt()` để in trạng thái tham chiếu của đối tượng Netty trong ví dụ.
- `DataBufferUtils.join(request.getBody(), 1024)` tích lũy tối đa 1024 byte để tạo buffer kết quả.
- `joined.read(bytes)` sao chép bytes vào `byte[]`; `finally` release `joined` kể cả khi đoạn xử lý trong `map` ném exception.
- Khi input rỗng, `join` có thể trả `Mono.empty()` nên `defaultIfEmpty("bytes=0")` cung cấp response có ý nghĩa.
- Khi vượt giới hạn join, `DataBufferLimitException` được đổi thành `ResponseStatusException` với HTTP 413. Tùy cấu hình error handler, body lỗi có thể có JSON chi tiết hoặc bị rút gọn.
- Không có vòng `for` release các buffer nguồn: `join` quản lý chúng, tránh double release.

### 8.2. Chạy dự án

Tại thư mục chứa Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Bỏ qua banner và log framework, bốn dòng do `CommandLineRunner` in theo thứ tự là:

```text
1 initial refCnt=1
2 retained refCnt=2
3 first release refCnt=1
4 final release refCnt=0
```

Nếu phiên bản allocator/transport khác với ví dụ, hãy đối chiếu Netty API của dự án; mục tiêu học là nhìn rõ hai lần release cho hai quyền sở hữu.

Thử request đúng:

```bash
curl -s -X POST http://localhost:8080/inspect \
  -H 'Content-Type: application/octet-stream' \
  --data-binary 'hello'
```

HTTP response body:

```text
bytes=5
```

Trong Windows PowerShell, dùng `curl.exe` với câu lệnh trên (hoặc viết cùng một dòng để tránh khác biệt ký tự nối dòng). Với payload vượt 1024 byte, endpoint phải trả **HTTP 413 Payload Too Large**. Để tạo payload kiểm thử có thể lặp lại bằng Python 3 nếu môi trường đã có:

```bash
python -c "print('x' * 1025, end='')" | curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST http://localhost:8080/inspect \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @-
```

Kết quả kỳ vọng:

```text
413
```

Đây là lệnh kiểm thử trên shell hỗ trợ pipe và `/dev/null` như Linux/macOS. Trên Windows, có thể gửi một file chứa 1025 byte bằng `curl.exe --data-binary @payload.bin` và xem HTTP status bằng `-i`. Điều kiện HTTP 413 ở đây là kết quả của `onErrorMap` đã định nghĩa, không phải mọi ứng dụng WebFlux đều mặc định map `DataBufferLimitException` cùng cách.

### 8.3. Giới hạn của ví dụ

Để dễ quan sát, endpoint copy toàn bộ body tối đa 1024 byte vào `byte[]`. Với một file lớn hàng GB, **không** nâng giới hạn này lên hàng GB; hãy chuyển sang cơ chế streaming có quota, kiểm tra content length, chống upload kéo dài, timeout và dọn tài nguyên ở đường hủy. Khi dùng JSON hoặc text thông thường, ưu tiên `@RequestBody` / codecs thay vì tự quản lý buffer.

## 9. Reactor: discard, cancellation, error và prefetch

Một publisher phát `DataBuffer` có nhiều trạng thái hơn “chạy thành công rồi complete”. Subscriber có thể hủy khi client ngắt kết nối, khi operator `take` đã lấy đủ phần tử, khi timeout xảy ra, hoặc khi upstream báo lỗi. Các operator như `filter`, `skip`, `flatMap`, `publishOn` và một số operator có prefetch có thể giữ hoặc bỏ đi phần tử trước khi xuống tới subscriber cuối.

```text
Flux<DataBuffer>
    |
    +-- buffer A --> consumer nhận -> đọc xong -> release A
    |
    +-- buffer B --> operator filter bỏ -> discard hook (nếu hỗ trợ) -> release B
    |
    +-- buffer C --> nằm trong queue -> client cancel -> cleanup queue -> release C
    |
    +-- buffer D --> chưa được phát -> upstream tùy thuộc cancellation contract
```

### 9.1. doOnDiscard là cơ chế cục bộ

```java
Flux<DataBuffer> filtered = request.getBody()
        .filter(buffer -> buffer.readableByteCount() > 0)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

Đây là **snippet**; giả sử `request` đã có và **consumer cuối của `filtered` vẫn chịu trách nhiệm giải phóng các buffer được đi tiếp** nếu chính nó đọc hết chúng. `doOnDiscard` xử lý buffer bị một số operator **upstream** bỏ đi. Nó không phải một lệnh “tự động release mọi buffer từng xuất hiện”. Spring/Project Reactor yêu cầu quan tâm đến `Discard Support` ghi trong Javadoc của operator, vì không phải operator nào cũng hỗ trợ discard hook.

Đặc điểm đáng nhớ:

- Các `doOnDiscard` cùng loại có thể được cộng dồn; đừng vô tình tạo hai cleanup không tương thích.
- Hook chỉ tác động tới các operator **upstream** nhìn thấy hook; vị trí trong chain rất quan trọng.
- Hook không bảo đảm xử lý tất cả tình huống publisher sai contract, element bị drop sau terminal signal hoặc tài nguyên đã được chuyển sang hệ thống khác.
- Với buffer được retain, một sự kiện discard chỉ nên release **quyền sở hữu tương ứng**; không được tự ý giải phóng tham chiếu còn đang có consumer khác dùng.
- Reactor hướng dẫn cleanup hook phải idempotent/an toàn khi bị gọi lặp; không dùng logic mù quáng double release làm xấu tình trạng.
- `doFinally` hữu ích để log `onComplete`, `onError`, `cancel` hoặc giải phóng **tài nguyên chung của subscription**; nó không tự có danh sách các buffer cần release.

### 9.2. Vì sao doOnCancel không đủ?

Ví dụ:

```java
source.doOnCancel(() -> log.info("request cancelled"));
```

Đoạn trên chỉ log cancellation. Nếu đã có buffer trong queue, collection của ứng dụng hoặc custom operator, log không giải phóng chúng. Cần dùng API/operator hỗ trợ dọn buffer và quản lý cả nhánh lỗi. Với custom subscriber/operator tự lưu `DataBuffer`, trách nhiệm cleanup thường lớn hơn một `doOnCancel`.

### 9.3. Cẩn thận với doOnNext

`doOnNext` phù hợp quan sát thống kê mà **không thay đổi quyền sở hữu** và không làm buffer hết hiệu lực. Nếu callback đọc và release trước khi downstream nhận buffer, đó là use-after-release. Nếu mục tiêu chuyển `DataBuffer` thành dữ liệu cấp cao, dùng `map` với `try/finally` và **không phát buffer cũ xuống dưới**; nếu mục tiêu chuyển buffer y nguyên cho writer, không release tại `doOnNext`.

### 9.4. Backpressure không thay thế cleanup

Reactive Streams cho phép subscriber yêu cầu số phần tử, giúp điều tiết lưu lượng, nhưng **không** tự release buffer mà ứng dụng đã giữ. Một queue có prefetch, custom collection hoặc `join` không giới hạn vẫn có thể tiêu tốn nhiều bộ nhớ, kể cả khi publisher dùng backpressure. Cần cả:

- Giới hạn byte/message và concurrency.
- Consumer đủ nhanh hoặc xử lý có điều phối.
- Cleanup đúng trên complete/error/cancel/discard.
- Quan sát lượng buffer đang active và thời gian chúng bị giữ.

## 10. Streaming upload, response và proxy: cách tránh sở hữu sai

### 10.1. Upload: dùng abstraction mức cao khi có thể

Với multipart upload, `FilePart.transferTo(Path)` giúp chuyển nội dung vào file mà không phải tự tách `DataBuffer` trong controller. Ví dụ **snippet** trong WebFlux controller:

```java
@PostMapping(path = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> upload(@RequestPart("file") FilePart part) {
    return part.transferTo(targetPath);
}
```

Đây là **snippet**, không phải chương trình độc lập: `targetPath` phải được xác thực, giới hạn vào thư mục cho phép, cấp quyền an toàn và không dùng nguyên tên file do client gửi. Cần cấu hình limit multipart, quota lưu trữ và cleanup tệp khi upload hủy/lỗi. `transferTo` không có nghĩa có thể bỏ qua mọi kiểm soát tài nguyên.

### 10.2. Response: đừng giải phóng buffer trước writer

Trong custom response streaming:

```java
Flux<DataBuffer> payload = createBodyBuffers();
return response.writeWith(payload);
```

Đây là **snippet** với `createBodyBuffers()` và `response` được cung cấp bởi hệ thống. Phía output HTTP thường nắm việc release sau khi ghi theo hợp đồng Spring. Nếu bạn phát buffer ra rồi release ngay bằng `doOnNext`, downstream có thể đọc vùng nhớ đã giải phóng.

Ngược lại, nếu **chính bạn cấp phát buffer nhưng lỗi xảy ra trước khi phát ra publisher**, phải dọn buffer đó ngay trong nhánh lỗi. Đọc Javadoc của custom producer và adapter bạn dùng; không suy từ một ví dụ thành quy tắc cho mọi thư viện.

### 10.3. DataBufferUtils.write có nhiều overload khác nhau

Spring Framework 6.x có các overload:

- `write(source, OutputStream)`.
- `write(source, WritableByteChannel)`.
- `write(source, AsynchronousFileChannel[, position])`.
- `write(source, Path[, options])`.

Những overload trả về `Flux<DataBuffer>` khi ghi vào stream/channel **không tự release input buffers** và **không tự đóng stream/channel** được truyền vào; chúng phát lại buffer cho downstream. Nếu bạn viết bộ tiêu thụ cuối, phải có đường release và đóng tài nguyên phù hợp. Overload ghi `Path` trả `Mono<Void>` với hợp đồng riêng. Đọc đúng API của bản Spring đang chạy và tránh vừa release trong nguồn vừa release ở consumer.

### 10.4. WebClient: đóng vòng đời response body

Với `WebClient`, chọn:

```java
webClient.get()
        .uri("/items")
        .retrieve()
        .bodyToFlux(Item.class);
```

Đây là **snippet** với `webClient`/`Item` giả định. Codec sẽ xử lý dữ liệu khi publisher được subscribe trong vòng đời hợp lệ. Với `exchangeToMono`/`exchangeToFlux`, cần bảo đảm body được tiêu thụ hoặc release theo hợp đồng. Nếu chỉ cần status mà bỏ qua body, dùng phương thức được API hỗ trợ (ví dụ `ClientResponse.releaseBody()` khi phù hợp); việc bỏ mặc raw body có thể ảnh hưởng connection pool.

Không giữ một `ClientResponse` thô ngoài phạm vi callback với kỳ vọng body sẽ tự động tồn tại mãi. Và không tự subscribe một lần “cho log” rồi lại subscribe trong HTTP handler: body publisher thường không được thiết kế cho việc tiêu thụ lặp tùy ý.

### 10.5. Log/trace request body là điểm rủi ro cao

Request logging filter dễ mắc ba lỗi cùng lúc: (1) tiêu thụ body trước controller, (2) giữ buffer mà không release, (3) làm lộ dữ liệu nhạy cảm. Ưu tiên log metadata như method, URI, content-type, content length, correlation ID và kích thước tổng có hạn mức. Nếu cần log payload vì nghiệp vụ, giới hạn byte, che dữ liệu nhạy cảm, định nghĩa rõ ownership và kiểm thử streaming/error/cancel. Không lưu buffer gốc vào một queue log chạy độc lập.

## 11. Chẩn đoán leak trong Reactor Netty

Triệu chứng thường gặp: tiến trình dần tăng direct memory, áp lực trên memory pool cao, các request upload/streaming lỗi sau một thời gian, cảnh báo Netty về `LEAK: ByteBuf.release() was not called before it's garbage-collected`, hoặc ứng dụng bị container kill do memory cạn.

### 11.1. Bật Netty leak detection trong môi trường kiểm thử

Netty có các mức phát hiện leak như `SIMPLE`, `ADVANCED` và `PARANOID`. Có thể cấu hình JVM system property:

```text
-Dio.netty.leakDetection.level=advanced
```

Áp dụng tham số này cho **JVM chạy ứng dụng** (không phải chỉ cho Gradle daemon). Mức `advanced` thường hữu ích khi điều tra; `paranoid` có chi phí lớn hơn, chỉ nên bật cho test chẩn đoán hẹp. Cơ chế leak detection có sampling và dựa vào quá trình thu gom đối tượng, nên **không thấy cảnh báo** không chứng minh không có leak; vị trí stack trace có thể là chỗ buffer được truy cập/khởi tạo chứ không chắc là điểm logic bỏ quên release.

### 11.2. Dùng DataBufferUtils.touch để gắn gợi ý chẩn đoán

```java
DataBufferUtils.touch(buffer, "incoming body: upload endpoint");
```

Snippet này gắn hint khi implementation hỗ trợ leak tracking. Nó không retain, không release và không chữa leak. Tránh gắn user token, request body, password hoặc thông tin định danh nhạy cảm vào hint/log.

### 11.3. Dữ liệu cần theo dõi

- Process RSS và direct/native memory bên cạnh Java heap/GC.
- Reactor Netty allocator metrics được phiên bản runtime hỗ trợ: lượng direct memory đã dùng/đang active và các pool liên quan.
- Số request/upload đang mở, số lượng stream chưa complete, tỉ lệ cancellation/timeout/error.
- Chunk size, kích thước body, thời gian response, concurrency, queue/prefetch.
- Cảnh báo leak Netty, `IllegalReferenceCountException`, `DataBufferLimitException` và các exception gốc.
- So sánh tải trước/sau thay đổi; một pool có thể duy trì vùng nhớ đã cấp phát để tái sử dụng dù không có leak.

**Lưu ý:** thay đổi cấu hình GC hoặc tăng heap không chữa việc `ByteBuf` pooled chưa release. Tăng direct-memory limit chỉ trì hoãn thời điểm hết bộ nhớ nếu nguồn leak còn đó.

## 12. Chiến lược kiểm thử để phát hiện thiếu và thừa release

### 12.1. Kiểm tra reference count có chủ đích

Với đơn vị xử lý dùng Netty `ByteBuf`, kiểm tra refCnt trước/sau từng nhánh xử lý có thể phát hiện lỗi. Ví dụ ứng dụng ở phần 8 có bốn log cố định chứng minh một lần retain cần hai lần release. Một test unit có thể tạo buffer bằng `NettyDataBufferFactory`, đưa nó qua hàm đang kiểm thử và xác nhận refCnt về 0 **khi ownership được tiêu thụ xong**. Không bắt mọi buffer trong mọi pipeline phải về 0 ngay trong cùng callback nếu đã chuyển quyền cho framework.

### 12.2. Test đủ các luồng kết thúc

Với bất kỳ custom `Flux<DataBuffer>` nào, dùng Reactor `StepVerifier` và các công cụ liên quan để kiểm tra:

1. **Complete bình thường:** mỗi buffer đã được consume cuối cùng và release hoặc transfer đúng.
2. **Decode ném exception:** buffer đang nằm trong lambda vẫn được release nhờ `finally`.
3. **Upstream báo error:** buffer đã tích lũy trong `join` được dọn và error được báo ra.
4. **Client cancel / `take(1)` / timeout:** các buffer bị queue/prefetch bỏ phải được giải phóng.
5. **Discard do filter/skip:** hook đúng vị trí xử lý các buffer bị loại.
6. **Hai subscriber/retry:** mỗi subscription có nguồn buffer mới hợp lệ; không chia một buffer refCnt=0 cho lần retry.
7. **Payload vượt giới hạn:** trả lỗi xác định, không leak và không tiếp tục đọc cả payload không kiểm soát.
8. **Burst nhiều kết nối:** không tăng bất thường active pooled buffers sau khi tải kết thúc.

Đừng viết test chỉ xác nhận response text “đúng”: leak có thể âm thầm xuất hiện sau hàng chục nghìn request. Kết hợp unit test reference count với load test, metrics và leak detector.

### 12.3. Đối chiếu sau khi sửa lỗi

Ví dụ lỗi chỉ xuất hiện ở nhánh `filter` loại buffer:

- Trước sửa: 10.000 request với client cancel ngẫu nhiên khiến số lượng buffer chưa release tăng liên tục.
- Sau sửa: mỗi buffer bị loại được dọn qua đúng discard contract, buffer đã đi tiếp được consumer release; lượng active memory quay về vùng ổn định sau các chu kỳ tải.
- Kiểm chứng thêm nhánh ngược lại: các buffer được giữ lại/forward vẫn hợp lệ, không phát sinh `IllegalReferenceCountException`.

Các con số chỉ là kịch bản kiểm thử, không phải benchmark sản phẩm. Tùy allocator, pool có thể giữ memory đã cấp phát nên không nên yêu cầu RSS về mức ban đầu ngay sau mỗi đợt.

## 13. Bảng xử lý nhanh theo triệu chứng

| Triệu chứng | Nghi vấn | Cách kiểm tra/sửa |
| --- | --- | --- |
| Direct memory tăng dần sau nhiều request | Buffer tiêu thụ cuối cùng không release, retain dư | Vẽ ownership, instrument refCnt và leak detector |
| `IllegalReferenceCountException: refCnt: 0` | Release trước khi writer dùng, double release | Tìm `doOnNext(release)` và nhánh `finally` trùng ownership |
| Đọc được JSON nhưng memory leak khi request invalid | Exception path không release raw buffer | Bọc decode thủ công bằng `try/finally`; test lỗi |
| Leak chỉ khi client cancel | Queue/prefetch/discard không cleanup | Xem `doOnDiscard`, operator docs và cancel test |
| Leak sau khi `join` | Caller không release **buffer kết quả** | Release kết quả sau decode, tránh release lại input |
| Lỗi khi input quá lớn | `join`/codec vượt memory cap | Thiết lập hạn mức phù hợp và trả 413 khi cần |
| Log body khiến controller nhận body rỗng | Filter đã subscribe/consume stream | Compose/decorate đúng, tránh đọc hai lần |
| Tải file lớn gây OOM nhưng không thấy leak log | Unbounded aggregation, copy và queue quá lớn | Streaming và giới hạn in-memory/size/concurrency |
| Memory high dù hết request | Pool caching hoặc giữ buffer thật | So sánh active/used direct, GC, RSS, leak logs và tải |
| Test pass nhưng production leak | Thiếu case cancel/timeout/chunking, server khác | Test cả Netty pooled implementation và điều kiện lỗi thật |

## 14. Tự kiểm tra

**Câu 1.** Một `PooledDataBuffer` có refCnt=1, code gọi `retain` một lần. Cần bao nhiêu `release` cân bằng?  
**Đáp án:** Hai lần, tương ứng hai tham chiếu hợp lệ; chỉ release khi từng bên thực sự không còn dùng dữ liệu.

**Câu 2.** Controller nhận `@RequestBody Mono<OrderRequest>` và trả `Mono<OrderResponse>`. Có cần gọi `DataBufferUtils.release` cho body không?  
**Đáp án:** Không phải ứng dụng thao tác raw `DataBuffer`; codec/framework lo lifecycle thông thường. Chỉ code truy cập buffer thấp tầng mới cần đánh giá quyền sở hữu cụ thể.

**Câu 3.** Code dùng `DataBufferUtils.join(flux, 4096)`, sau đó release từng buffer input rồi release buffer kết quả. Có gì sai?  
**Đáp án:** `join` đã quản lý quyền sở hữu input; release lại input có thể double release, nhất là khi kết quả là composite. Chỉ consumer cuối release buffer kết quả khi đã dùng xong.

**Câu 4.** Tại sao `doOnDiscard` không đủ bảo đảm không leak?  
**Đáp án:** Nó chỉ có hiệu lực với các operator có hỗ trợ discard và đúng đoạn upstream; buffer được tiêu thụ/forward bình thường hoặc được giữ trong custom collection vẫn phải có cleanup riêng theo ownership.

**Câu 5.** `DataBufferLimitException` có đồng nghĩa với pooled-buffer leak?  
**Đáp án:** Không. Nó cho biết lượng dữ liệu tích lũy/giải mã vượt giới hạn; cần phân biệt với leak tài nguyên và thiết kế limit/streaming.

**Câu 6.** Một HTTP response đang dùng `response.writeWith(flux)`; nên đặt `doOnNext(DataBufferUtils::release)` trước writer để “chắc chắn không leak” không?  
**Đáp án:** Không. Nó có thể release buffer trước khi writer nhận và gây use-after-release. Hãy để ownership được chuyển theo hợp đồng writer và dọn buffer trong nhánh producer lỗi nếu buffer chưa được chuyển đi.

## 15. Checklist trước khi merge custom code dùng DataBuffer

- [ ] Có lý do rõ ràng để dùng raw `DataBuffer` thay vì codec/DTO/`FilePart`.
- [ ] Đã xác định implementation và tính pooled/reference-counted ở môi trường chạy thật.
- [ ] Mỗi buffer được tạo/nhận có owner cuối cùng và đường transfer hoặc release xác định.
- [ ] Mọi lần `retain` đều có đường `release` tương ứng trên complete/error/cancel.
- [ ] Buffer đã chuyển cho writer/framework không bị giải phóng sớm.
- [ ] Buffer đọc xong và chuyển thành kiểu độc lập được release trong `finally`.
- [ ] `join` dùng hạn mức phù hợp; caller chỉ release kết quả, không double-release input.
- [ ] Đã xét discard/prefetch/queue và vị trí `doOnDiscard` theo Javadoc operator.
- [ ] Không tự subscribe body nhiều lần hoặc cache raw buffer không giới hạn.
- [ ] Upload/streaming có byte limit, timeout, concurrency limit và cleanup cancellation.
- [ ] Đã kiểm thử happy path, decode error, timeout, client disconnect và buffer-limit error.
- [ ] Đã giám sát direct memory, allocator metrics, leak warning và lỗi use-after-release.
- [ ] Đã kiểm tra mã trên đúng Spring Boot/Spring Framework/Netty version triển khai.

## Tài liệu tham khảo chính thức

- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework 6.1 — DataBufferUtils API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework — WebFlux Reactive Core, DataBuffer](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Project Reactor — Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html)
- [Project Reactor — Flux.doOnDiscard API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)

Khi xử lý raw buffers, điều cần kiểm soát không chỉ là “đã gọi release hay chưa” mà là **mỗi quyền sở hữu tồn tại đến đúng thời điểm, được chuyển giao hoặc kết thúc đúng một lần**. Thiết kế tốt nhất thường là giữ thao tác byte ở phạm vi nhỏ, dùng API có lifecycle rõ, giới hạn bộ nhớ tích lũy và kiểm chứng nhánh cancellation/error trước khi đưa vào hệ thống có tải.
