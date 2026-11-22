# Giải phóng bộ đệm khi lọc, lỗi hoặc hủy trong Spring WebFlux

## 1. Vì sao DataBuffer cần được giải phóng?

Spring WebFlux biểu diễn dữ liệu byte qua `DataBuffer`. Khi chạy trên Reactor Netty, buffer thường được tạo từ Netty `ByteBuf` và có thể dùng bộ nhớ direct, pooled và reference-counted. Các buffer này không chỉ sống theo quy tắc garbage collection của Java heap.

Một buffer được cấp phát thường bắt đầu với reference count bằng 1:

- `retain()` tăng reference count.
- `release()` giảm reference count.
- Khi reference count về 0, buffer được giải phóng và vùng nhớ có thể quay lại pool.
- Nếu reference count không bao giờ về 0, bộ nhớ pooled/direct có thể bị giữ lại dù object Java không còn được sử dụng.

Vì vậy, một ứng dụng có thể không tăng heap rõ rệt nhưng vẫn gặp lỗi thiếu direct memory, Netty báo leak hoặc kết nối bắt đầu thất bại khi tải tăng.

`DataBuffer` là abstraction dùng chung cho nhiều server. Với một số implementation như Netty, Jetty, buffer có thể pooled và cần được release. Với `DefaultDataBufferFactory` không pooled, `DataBufferUtils.release` có thể không làm gì. Dùng `DataBufferUtils` giúp code không phải tự phân nhánh theo implementation.

**Nguyên tắc cốt lõi:** component nào nhận quyền sở hữu buffer để tiêu thụ thì phải bảo đảm buffer được release đúng một lần cho reference mà component đó sở hữu, kể cả khi việc xử lý lỗi hoặc bị hủy.

## 2. DataBuffer, PooledDataBuffer và ownership

Các API nền tảng:

| API | Vai trò |
| --- | --- |
| `DataBuffer` | Abstraction đọc/ghi byte |
| `PooledDataBuffer` | DataBuffer có reference count và lifecycle pool |
| `DataBufferFactory` | Tạo hoặc wrap DataBuffer |
| `NettyDataBufferFactory` | DataBufferFactory dựa trên Netty ByteBufAllocator |
| `DataBufferUtils.release(buffer)` | Release nếu buffer là pooled |
| `DataBufferUtils.retain(buffer)` | Giữ thêm một reference nếu buffer là pooled |
| `DataBufferUtils.releaseConsumer()` | Consumer tiện dụng gọi release cho mỗi buffer |
| `DataBufferUtils.join(publisher)` | Ghép nhiều buffer thành một buffer |

### 2.1. Reference count minh họa

~~~text
allocate buffer
      |
      v
  refCnt = 1
      |
      +---- retain() ------> refCnt = 2
      |                         |
      |                      release()
      |                         |
      |                      refCnt = 1
      |
   release()
      |
      v
  refCnt = 0
      |
      v
buffer được giải phóng / trả lại pool
~~~

`DataBufferUtils.release` và `DataBufferUtils.retain` chỉ áp dụng thao tác reference count khi implementation hỗ trợ pooled buffer. Vì vậy, chúng phù hợp hơn việc ép kiểu mọi buffer sang `PooledDataBuffer` hoặc gọi trực tiếp API Netty.

### 2.2. Quy tắc ownership trong pipeline

Hãy xác định rõ ai đang sở hữu từng buffer:

| Tình huống | Trách nhiệm |
| --- | --- |
| Nhận DataBuffer và đọc hết nội dung để tạo String/DTO | Consumer release sau khi đọc xong |
| Nhận DataBuffer rồi chuyển nguyên buffer xuống downstream | Chuyển quyền sở hữu cho downstream; không release trước khi downstream đọc |
| Filter loại bỏ một buffer | Buffer bị discard phải được release |
| Operator giữ buffer trong queue rồi bị cancel | Queue phải release các item bị discard |
| Code tự giữ buffer trong List/field/cache | Code sở hữu collection phải release các buffer còn giữ khi hoàn tất, lỗi hoặc cancel |
| Gọi retain để giữ thêm một reference | Phải release đúng reference bổ sung sau khi dùng |
| DataBufferUtils.join gom nhiều buffer | Không tự release các buffer đầu vào; release buffer kết quả sau khi tiêu thụ |
| Encoder tự allocate nhưng serialization lỗi trước khi chuyển buffer cho consumer | Encoder release buffer đang sở hữu |
| Encoder đã phát buffer cho HTTP writer | Consumer/writer chịu trách nhiệm release |

**Không release buffer chỉ vì đã nhìn thấy nó trong doOnNext.** Nếu pipeline còn chuyển buffer xuống writer hoặc codec khác, release quá sớm sẽ gây use-after-release hoặc `IllegalReferenceCountException`.

Ngược lại, nếu code đã đọc buffer thành byte[]/String và không chuyển buffer tiếp, hãy release trong cùng thao tác tiêu thụ.

## 3. Ba tình huống phải xử lý: filter, error và cancellation

Một pipeline làm việc với `Flux<DataBuffer>` có thể kết thúc theo nhiều cách:

~~~text
Flux<DataBuffer>
      |
      +-- filter loại một item ----------------> DISCARD
      |
      +-- map/decode đọc item -----------------> CONSUME
      |                                               |
      |                                               +-- thành công
      |                                               +-- exception
      |
      +-- publishOn/flatMap prefetch ------------> QUEUE
                                                      |
                                                      +-- downstream cancel
                                                      +-- upstream error
                                                      +-- queue bị dọn
~~~

Cần phân biệt hai loại buffer:

1. **Buffer đang được xử lý:** code hiện tại đang đọc/giải mã nó. Dùng `try/finally` để release ngay cả khi xử lý ném exception.
2. **Buffer bị bỏ hoặc còn nằm trong queue:** code không trực tiếp đọc nó nữa. Dùng `doOnDiscard` cho các Reactor operator hỗ trợ discard.

Một cleanup hook không thay thế cleanup của loại còn lại.

## 4. Giải phóng buffer sau khi tiêu thụ thành công

Nếu consumer đọc toàn bộ nội dung để tạo object cấp cao hơn, hãy release sau khi đọc:

~~~java
static String readAndRelease(DataBuffer buffer) {
    try {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }
    finally {
        DataBufferUtils.release(buffer);
    }
}
~~~

Đây là pattern cho một consumer **đã nhận quyền sở hữu buffer và tiêu thụ nó**:

- Đọc số byte hiện còn có thể đọc.
- Chuyển byte thành String.
- Dù đọc hoặc chuyển đổi có lỗi, khối finally vẫn chạy.
- Sau khi đã chuyển thành String, không còn cần giữ DataBuffer.

Nếu muốn chuyển buffer nguyên vẹn sang downstream:

~~~java
Flux<DataBuffer> forwarded = source
        .map(buffer -> buffer);
~~~

Không release trong map này vì downstream vẫn cần đọc buffer. Component cuối cùng tiêu thụ buffer mới release, hoặc chuyển quyền sở hữu cho HTTP writer/codec theo contract của API.

### 4.1. Đừng release trước khi phát buffer

Sai:

~~~java
Flux<DataBuffer> broken = source.map(buffer -> {
    DataBufferUtils.release(buffer);
    return buffer;
});
~~~

Downstream nhận một object đã bị release. Với pooled buffer, việc đọc tiếp có thể lỗi hoặc truy cập vùng nhớ không còn hợp lệ.

Đúng nếu mục tiêu là chuyển tiếp:

~~~java
Flux<DataBuffer> forwarded = source;
~~~

Đúng nếu mục tiêu là chuyển sang kiểu dữ liệu khác:

~~~java
Flux<String> decoded = source.map(MyDecoder::readAndRelease);
~~~

Method `readAndRelease` phải chịu trách nhiệm release buffer trong finally như ví dụ phía trên.

## 5. Lọc DataBuffer: dùng doOnDiscard

`filter` loại các item không thỏa predicate. Item bị loại không được phát tới downstream, nên không thể trông chờ consumer cuối pipeline release nó.

Ví dụ:

~~~java
Flux<String> accepted = source
        .filter(buffer -> buffer.readableByteCount() >= 5)
        .map(MyDecoder::readAndRelease)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

`doOnDiscard(DataBuffer.class, DataBufferUtils::release)` đăng ký cleanup hook cho các `DataBuffer` bị discard bởi những operator upstream có hỗ trợ discard.

### 5.1. Vị trí của doOnDiscard rất quan trọng

`doOnDiscard` có tính cục bộ và tác động tới các operator **nằm upstream của nó trong chain**. Vì thế, đặt hook sau các operator có thể loại hoặc giữ item:

~~~java
source
    .filter(this::shouldKeep)
    .skip(2)
    .publishOn(Schedulers.parallel(), 16)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .map(MyDecoder::readAndRelease);
~~~

Hook nằm sau `filter`, `skip` và `publishOn` nên có thể xử lý các buffer bị những operator đó discard, bao gồm item bị bỏ trong quá trình dọn queue khi cancellation.

Nếu đặt hook trước filter:

~~~java
// Không đủ để hook này bao phủ filter nằm phía sau nó.
source
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .filter(this::shouldKeep);
~~~

filter nằm downstream của hook, nên không nằm trong phạm vi upstream mà hook này bảo vệ.

**Quy tắc nhớ:** tìm operator có khả năng discard, rồi đặt `doOnDiscard` ở phía downstream của operator đó trong thứ tự code.

### 5.2. Filter predicate không nên tiêu thụ buffer

Nếu chỉ kiểm tra độ dài, dùng `readableByteCount()` như ví dụ. Nếu predicate cần xem byte, hãy tránh đọc làm thay đổi read position mà không khôi phục, hoặc thiết kế việc đọc sao cho ownership và vị trí đọc rõ ràng.

Không biến filter thành nơi đọc hết body rồi tiếp tục giả định decoder downstream còn nguyên dữ liệu. Nếu đã tiêu thụ buffer, cần chuyển kết quả đã đọc hoặc tạo buffer mới theo contract.

### 5.3. Các operator khác cũng có thể discard

Không chỉ `filter`:

- `skip` loại các item đầu.
- `take` có thể hủy upstream khi đủ số item.
- `flatMap`, `publishOn` và một số operator prefetch/queue có thể giữ item nội bộ.
- `reduce` hoặc các operator tổng hợp có thể cache item trong quá trình xử lý.
- Một số operator quản lý buffer có callback cleanup riêng.

Với pipeline decoder dùng các operator có thể prefetch/cache hoặc loại DataBuffer, Spring khuyến nghị thêm `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` vào chain.

Không giả định mọi operator hoặc Publisher tùy chỉnh đều hỗ trợ discard hook. Nếu tự viết operator có khả năng bỏ item, implementation đó phải quản lý cleanup theo contract của nó.

## 6. Khi decode ném exception: release item đang xử lý

`doOnDiscard` chủ yếu xử lý item bị bỏ bởi operator hỗ trợ discard. Nó không thay thế việc release buffer mà code đang trực tiếp đọc khi thao tác đó ném exception.

Ví dụ sai:

~~~java
Flux<String> decoded = source.map(buffer -> {
    String text = decode(buffer); // Có thể ném exception.
    DataBufferUtils.release(buffer);
    return text;
});
~~~

Nếu `decode(buffer)` ném exception, dòng release không được chạy. Buffer hiện tại bị rò rỉ.

Sửa bằng finally:

~~~java
Flux<String> decoded = source
        .map(buffer -> {
            try {
                return decode(buffer);
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        })
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

Ở đây có hai cơ chế với hai phạm vi:

- `finally` release buffer mà lambda đã nhận để xử lý, kể cả decode thành công hay thất bại.
- `doOnDiscard` release những buffer khác bị operator upstream loại bỏ hoặc dọn khỏi queue khi lỗi/cancel.

Không gọi release hai lần cho cùng một reference. Nếu `decode` đã chuyển quyền sở hữu buffer cho một thành phần khác, thì không release tại lambda này; ownership phải được ghi rõ.

### 6.1. Lỗi xảy ra sau khi đã gom một số buffer

Giả sử decoder tự giữ nhiều buffer trong một List:

~~~java
List<DataBuffer> pending = new ArrayList<>();
~~~

Nếu decoder tự quản lý collection này, nó phải release mọi buffer còn giữ khi:

- Đọc thành công và hoàn tất việc sử dụng.
- Một buffer tiếp theo gây lỗi parse.
- Publisher phát onError.
- Subscriber cancel trước khi collection được tiêu thụ xong.

Không chỉ release buffer cuối cùng gây lỗi. Những buffer đã tích lũy trước đó cũng cần cleanup.

Khi mục tiêu là ghép các buffer thành một chuỗi byte, thường nên dùng `DataBufferUtils.join` thay cho tự quản lý List. Nếu phải tự giữ state, hãy thiết kế lifecycle của collection rõ ràng và đồng bộ với error/cancel; `doOnDiscard` không tự nhìn thấy mọi reference nằm trong field hoặc collection do ứng dụng tự quản lý.

## 7. Cancellation: giải phóng item còn nằm trong queue

Cancellation xảy ra khi downstream không còn muốn nhận dữ liệu. Ví dụ:

- Client đóng kết nối HTTP.
- Subscriber gọi cancel.
- `take(1)` đã nhận đủ một item và hủy upstream.
- Một request timeout.
- Một pipeline bị thay thế hoặc kết thúc sớm.

Một số operator prefetch dữ liệu để giữ throughput. Khi cancel, queue có thể còn DataBuffer chưa phát. Reactor cần discard các item này và `doOnDiscard` giúp release chúng.

Ví dụ:

~~~java
Flux<String> firstChunk = incomingBuffers
        .publishOn(Schedulers.parallel(), 8)
        .take(1)
        .map(MyDecoder::readAndRelease)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

Nếu `publishOn` đã prefetch các buffer rồi `take(1)` hủy upstream, các buffer còn lại trong queue có thể bị discard. Hook ở cuối chain xử lý các DataBuffer bị discard bởi operator upstream có hỗ trợ.

### 7.1. doFinally không tự release mọi buffer

`doFinally` nhận tín hiệu kết thúc như complete, error hoặc cancel:

~~~java
pipeline.doFinally(signal -> {
    log.debug("pipeline terminated: {}", signal);
});
~~~

Nó hữu ích để dọn state/resource do ứng dụng tự sở hữu, nhưng **không tự biết những DataBuffer nào nằm trong queue nội bộ của Reactor**. Không thể thay `doOnDiscard` bằng một `doFinally` chỉ ghi log.

Nếu ứng dụng tự giữ buffer ngoài queue, hãy release chúng trong cleanup callback mà ứng dụng sở hữu. Nếu buffer được giữ trong một collection, cleanup phải xử lý từng reference còn lại. Nếu buffer được chuyển sang async task, lifecycle của task phải bao gồm release khi complete/error/cancel.

### 7.2. Retain khi cần giữ buffer qua một boundary bất đồng bộ

Thông thường, không cần `retain` khi đọc buffer ngay trong pipeline và release sau khi tiêu thụ. Chỉ retain khi cần có thêm một reference độc lập vì một thành phần khác có thể release reference gốc trong lúc công việc bất đồng bộ vẫn đang dùng buffer.

Mẫu khái niệm:

~~~java
DataBuffer retained = DataBufferUtils.retain(buffer);

return asyncConsumer.consume(retained)
        .doFinally(signal ->
                DataBufferUtils.release(retained));
~~~

Đây là **mẫu ownership**, không phải đoạn code có thể áp dụng tùy tiện cho mọi publisher. `retain` tăng thêm một reference; cleanup phải release đúng reference bổ sung. Chủ sở hữu reference ban đầu vẫn phải thực hiện trách nhiệm release của họ. Nếu không có lý do rõ ràng về hai chủ sở hữu, đừng thêm retain để “phòng xa”.

Không lưu một DataBuffer vào field hoặc queue rồi để request kết thúc mà không có cleanup. Nếu cần chuyển ownership sang một worker, hãy xác định worker là chủ sở hữu mới và bảo đảm nó release trong mọi đường complete/error/cancel.

## 8. DataBufferUtils.join: gom buffer an toàn

Khi cần gom nhiều buffer thành một buffer, `DataBufferUtils.join` là API được Spring cung cấp để thực hiện việc này an toàn và hiệu quả. Tùy implementation, kết quả có thể là một buffer mới hoặc composite buffer gần như zero-copy.

~~~java
Mono<DataBuffer> joined = DataBufferUtils.join(body);
~~~

Các quy tắc ownership của `join`:

1. Các buffer đầu vào được quản lý như thành phần của buffer kết quả.
2. Không tự release riêng từng buffer đầu vào sau khi gọi join.
3. Nếu source phát error hoặc bị cancel trong lúc đang gom, các buffer đã tích lũy được release.
4. Khi join phát buffer kết quả, consumer sở hữu việc tiêu thụ và release buffer kết quả.
5. Nếu consumer đọc kết quả thành byte[]/String, release buffer kết quả trong finally.

Ví dụ:

~~~java
Mono<String> bodyText = DataBufferUtils.join(body, 256 * 1024)
        .map(MyDecoder::readAndRelease);
~~~

Overload có giới hạn byte giúp tránh gom một body không giới hạn vào bộ nhớ. Nếu vượt giới hạn, `DataBufferLimitException` được phát sinh. Hãy chọn giới hạn theo contract và kích thước payload dự kiến.

### 8.1. Đừng gom toàn bộ body nếu không cần

`join` cần tích lũy dữ liệu trước khi phát buffer kết quả. Với body lớn hoặc streaming như file upload, video, SSE hoặc NDJSON, gom toàn bộ body có thể làm tăng memory pressure và độ trễ.

Chỉ dùng join khi nghiệp vụ thật sự cần dữ liệu tổng hợp. Nếu có thể xử lý từng chunk, hãy decode/forward theo luồng và release từng buffer đúng lúc.

### 8.2. Giới hạn bộ nhớ và lỗi

Ví dụ:

~~~java
Mono<byte[]> bytes = DataBufferUtils.join(body, 1024 * 1024)
        .map(buffer -> {
            try {
                byte[] result = new byte[buffer.readableByteCount()];
                buffer.read(result);
                return result;
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        });
~~~

Đoạn này giới hạn tổng body ở 1 MiB. Nếu vượt quá, pipeline phát lỗi thay vì âm thầm giữ một lượng buffer không giới hạn. Buffer kết quả được release dù copy byte thành công hay thất bại.

Nếu join bị cancel trước khi phát kết quả, Spring giải phóng những buffer đã tích lũy. Nếu join đã phát kết quả cho consumer, consumer phải release kết quả theo ownership contract.

## 9. Dùng các tiện ích xử lý byte count

Spring cung cấp các method giúp cắt/skip theo số byte mà không phải tự xây một bộ quản lý buffer:

- `DataBufferUtils.takeUntilByteCount(publisher, maxByteCount)`: lấy dữ liệu cho đến giới hạn byte.
- `DataBufferUtils.skipUntilByteCount(publisher, maxByteCount)`: bỏ dữ liệu cho đến giới hạn byte.
- `DataBufferUtils.join(publisher, maxByteCount)`: gom dữ liệu với giới hạn tổng byte.

Ví dụ:

~~~java
Flux<DataBuffer> firstMegabyte =
        DataBufferUtils.takeUntilByteCount(body, 1024 * 1024);

Flux<DataBuffer> afterHeader =
        DataBufferUtils.skipUntilByteCount(body, headerLength);
~~~

Các helper này đã xử lý việc split/release buffer theo logic của chúng. Đọc JavaDoc của version Spring đang dùng trước khi tự viết logic cắt DataBuffer, vì thao tác split có thể tạo buffer mới hoặc thay đổi ownership của phần dữ liệu.

Nếu downstream tiêu thụ các buffer được phát ra, downstream vẫn phải release khi đọc xong hoặc chuyển tiếp quyền sở hữu.

## 10. Encoder: release nếu serialization lỗi trước khi chuyển quyền sở hữu

Encoder thường cấp phát DataBuffer, ghi dữ liệu vào rồi phát buffer để HTTP writer hoặc client request tiêu thụ. Nếu serialization lỗi trước khi buffer được chuyển cho consumer, encoder vẫn đang sở hữu buffer và phải release.

Pattern:

~~~java
DataBuffer buffer = factory.allocateBuffer();
boolean transferred = false;

try {
    serialize(value, buffer);
    transferred = true;
    return buffer;
}
finally {
    if (!transferred) {
        DataBufferUtils.release(buffer);
    }
}
~~~

Đây là đoạn minh họa cho encoder trả một DataBuffer. Biến `transferred` thể hiện ranh giới ownership:

- Trước khi phát buffer, encoder chịu trách nhiệm release nếu có lỗi.
- Sau khi phát buffer, consumer nhận trách nhiệm đọc và release.
- Không release buffer sau khi đã chuyển cho HTTP writer, trừ khi API contract yêu cầu một reference bổ sung riêng.

Trong ứng dụng WebFlux thông thường, encoder/codec tích hợp đã quản lý nhiều chi tiết này. Developer thường chỉ phải trực tiếp xử lý khi viết custom codec hoặc thao tác trực tiếp với DataBuffer.

## 11. doOnDiscard, onOperatorError và onNextDropped khác nhau

Reactor có nhiều hook cleanup, mỗi hook phục vụ một loại tình huống.

| Hook | Khi nào dùng | Phạm vi |
| --- | --- | --- |
| `doOnDiscard` | Operator chủ động loại item hoặc dọn queue nội bộ | Cục bộ cho chain và các operator upstream hỗ trợ discard |
| `onOperatorError` | Lỗi xảy ra trong lúc một operator xử lý onNext | Hook xử lý lỗi operator; có thể cần cleanup item gây lỗi |
| `onNextDropped` | Publisher vi phạm protocol, phát item sau terminal signal hoặc item không được nhận | Hook cho item bị drop do nguồn malformed |
| Operator-specific cleanup | Operator có collection/queue riêng | Callback cleanup theo contract của operator |

Với custom decoder thông thường, bắt đầu bằng:

1. `try/finally` cho buffer đang được đọc.
2. `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` cho filter/prefetch/queue.
3. Cleanup rõ ràng cho buffer mà ứng dụng tự giữ ngoài chain.

Không thiết lập global hook `Hooks.onOperatorError` hoặc `Hooks.onNextDropped` chỉ để vá một pipeline cục bộ. Global hook có thể ảnh hưởng các Publisher khác trong JVM; chỉ dùng khi đang xây hạ tầng/library và hiểu rõ phạm vi.

Một số operator có thể quản lý collection hoặc buffer overlap theo cách riêng. Không giả định một discard hook đơn giản sẽ giải phóng đúng một object nếu cùng object được tham chiếu bởi nhiều cấu trúc đang hoạt động. Tuân thủ contract của operator và giữ ownership rõ ràng.

## 12. Chương trình Java 17+ chạy được với pooled Netty DataBuffer

Ví dụ dưới đây dùng Netty allocator để tạo buffer có reference count thật. Chương trình chứng minh:

1. Buffer bị filter loại được release bởi `doOnDiscard`.
2. Buffer được tiêu thụ được release trong `finally`.
3. `DataBufferUtils.join` ghép nhiều buffer; release kết quả sẽ giải phóng các thành phần.
4. Khi decoder ném exception, buffer hiện tại vẫn được release.

Yêu cầu: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. Boot BOM quản lý Spring Framework, Reactor và Netty tương thích.

### 12.1. Cấu trúc dự án

~~~text
data-buffer-cleanup-demo/
  pom.xml
  src/main/java/example/buffer/DataBufferCleanupDemo.java
~~~

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>data-buffer-cleanup-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
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

### 12.3. DataBufferCleanupDemo.java

~~~java
package example.buffer;

import java.nio.charset.StandardCharsets;
import java.util.List;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.PooledByteBufAllocator;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.NettyDataBuffer;
import org.springframework.core.io.buffer.NettyDataBufferFactory;

import reactor.core.publisher.Flux;

public final class DataBufferCleanupDemo {

    private static NettyDataBuffer create(
            NettyDataBufferFactory factory, String value) {

        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        NettyDataBuffer buffer = factory.allocateBuffer(bytes.length);
        buffer.write(bytes);
        return buffer;
    }

    private static String readAndRelease(DataBuffer buffer) {
        try {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return new String(bytes, StandardCharsets.UTF_8);
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    }

    private static String failAfterRelease(DataBuffer buffer) {
        try {
            throw new IllegalStateException("decode failed");
        }
        finally {
            DataBufferUtils.release(buffer);
        }
    }

    public static void main(String[] args) {
        NettyDataBufferFactory factory =
                new NettyDataBufferFactory(PooledByteBufAllocator.DEFAULT);

        // 1) Filter drops one buffer. The discard hook releases it.
        NettyDataBuffer keepA = create(factory, "keep-A");
        NettyDataBuffer drop = create(factory, "no");
        NettyDataBuffer keepB = create(factory, "keep-B");

        ByteBuf keepARef = keepA.getNativeBuffer();
        ByteBuf dropRef = drop.getNativeBuffer();
        ByteBuf keepBRef = keepB.getNativeBuffer();

        List<String> filtered = Flux.just(keepA, drop, keepB)
                .filter(buffer -> buffer.readableByteCount() >= 5)
                .map(DataBufferCleanupDemo::readAndRelease)
                .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
                .collectList()
                .block();

        System.out.println("filtered=" + filtered);
        System.out.println("keepA.refCnt=" + keepARef.refCnt());
        System.out.println("drop.refCnt=" + dropRef.refCnt());
        System.out.println("keepB.refCnt=" + keepBRef.refCnt());

        // 2) join owns the input buffers; release the joined result.
        NettyDataBuffer partA = create(factory, "hello ");
        NettyDataBuffer partB = create(factory, "world");
        ByteBuf partARef = partA.getNativeBuffer();
        ByteBuf partBRef = partB.getNativeBuffer();

        String joined = DataBufferUtils.join(
                        Flux.just(partA, partB), 1024)
                .map(DataBufferCleanupDemo::readAndRelease)
                .block();

        System.out.println("joined=" + joined);
        System.out.println(
                "join.parts.refCnt=" +
                partARef.refCnt() + "," + partBRef.refCnt());

        // 3) The current item is released even when decoding fails.
        NettyDataBuffer broken = create(factory, "broken");
        ByteBuf brokenRef = broken.getNativeBuffer();

        try {
            Flux.just(broken)
                    .map(DataBufferCleanupDemo::failAfterRelease)
                    .doOnDiscard(
                            DataBuffer.class, DataBufferUtils::release)
                    .blockLast();
        }
        catch (IllegalStateException expected) {
            System.out.println("error=" + expected.getMessage());
        }

        System.out.println("error.refCnt=" + brokenRef.refCnt());
    }
}
~~~

### 12.4. Chạy chương trình

~~~bash
mvn -q clean package
mvn -q exec:java -Dexec.mainClass=example.buffer.DataBufferCleanupDemo
~~~

**Stdout dự kiến:**

~~~text
filtered=[keep-A, keep-B]
keepA.refCnt=0
drop.refCnt=0
keepB.refCnt=0
joined=hello world
join.parts.refCnt=0,0
error=decode failed
error.refCnt=0
~~~

Giải thích:

- `keepA` và `keepB` đi qua filter, được đọc rồi release trong `readAndRelease`.
- `drop` bị filter loại và release qua discard hook.
- `partA` và `partB` được `join` đưa vào composite; khi consumer release composite, các thành phần cũng được release.
- `broken` là item đang được decoder xử lý; `finally` release nó trước khi lỗi truyền ra ngoài.
- `refCnt=0` xác nhận reference count của từng buffer đã về 0.

Ví dụ dùng `PooledByteBufAllocator` để quan sát reference count của Netty. Trong ứng dụng WebFlux thực tế, DataBufferFactory thường được lấy từ request/response thay vì tự tạo factory trong controller.

## 13. Ví dụ cancellation trong một pipeline có prefetch

Đây là mẫu áp dụng cho một luồng có thể bị hủy sớm:

~~~java
Flux<String> firstChunk = incomingBuffers
        .publishOn(Schedulers.parallel(), 8)
        .take(1)
        .map(MyDecoder::readAndRelease)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

Khi downstream nhận một chunk rồi hoàn tất, `take(1)` cancel upstream. `publishOn` có thể còn DataBuffer trong queue do prefetch; discard hook giải phóng các item đó.

Trong test, nên tạo nguồn có nhiều pooled buffer, cho subscriber nhận một item rồi cancel, sau đó xác nhận những buffer còn nằm trong queue đã được release. Không chỉ test đường complete bình thường vì lỗi leak thường nằm ở đường cancel/error.

Nếu pipeline giữ DataBuffer trong một collection tự quản lý, hook này không tự release collection. Hãy thêm cleanup riêng cho state đó.

## 14. Debug memory leak với Netty

Khi ứng dụng có dấu hiệu giữ direct memory bất thường, log có thể chứa thông báo:

~~~text
LEAK: ByteBuf.release() was not called before it's garbage-collected
~~~

Netty có ResourceLeakDetector với các mức:

| Level | Mục đích |
| --- | --- |
| `DISABLED` | Tắt leak detection; không nên dùng để che lỗi |
| `SIMPLE` | Phát hiện leak theo sampling mặc định |
| `ADVANCED` | Báo thêm nơi buffer gần đây được truy cập |
| `PARANOID` | Kiểm tra mọi allocation; phù hợp test, có overhead lớn |

Bật mức nâng cao khi debug:

~~~bash
java -Dio.netty.leakDetection.level=advanced -jar app.jar
~~~

Trong môi trường test có thể dùng:

~~~bash
java -Dio.netty.leakDetection.level=paranoid -jar app.jar
~~~

Không nên để `PARANOID` mặc định ở production vì chi phí theo dõi cao. Dùng nó để tái hiện lỗi trong test hoặc môi trường debug; sau đó chuyển về mức phù hợp với vận hành.

Khi điều tra:

1. Xác định request hoặc route tạo buffer.
2. Tìm operator filter/skip/prefetch/flatMap có khả năng discard.
3. Kiểm tra hook có đặt sau operator đó không.
4. Tìm các đường error/cancel mà code đang giữ buffer.
5. Kiểm tra có release trước khi chuyển downstream không.
6. Kiểm tra retain có được cân bằng bởi release tương ứng không.
7. Kiểm tra có release hai lần cùng một reference không.
8. Dùng leak detector để thu thập allocation/access trace.
9. Tạo regression test cho đường filter, error và cancellation.

Không chỉ nhìn heap usage. Buffer direct/pooled có thể không nằm trong Java heap theo cách profiler heap thông thường thể hiện.

## 15. WebFlux filter và custom codec: các lưu ý thực tế

WebFlux thường tự quản lý DataBuffer khi application làm việc ở mức kiểu dữ liệu cao hơn, ví dụ:

~~~java
Mono<MyRequest> body = request.bodyToMono(MyRequest.class);
~~~

Codec đọc các DataBuffer đầu vào, tạo object và quản lý lifecycle theo contract của framework.

Bạn cần đặc biệt cẩn thận khi:

- Đọc trực tiếp `Flux<DataBuffer>`.
- Viết custom `Decoder` hoặc `Encoder`.
- Dùng `ServerHttpRequestDecorator` để quan sát/thay body.
- Dùng `ServerHttpResponseDecorator` để ghi nhận response body.
- Tự ghép body bằng `join` hoặc lưu buffer để xử lý sau.
- Chèn filter có thể loại hoặc trì hoãn DataBuffer.

### 15.1. Đọc request body trong filter

Không đọc body để log rồi gọi handler như thể body vẫn còn nguyên. Request body là stream; việc tiêu thụ nó có thể khiến handler phía sau không còn dữ liệu để đọc.

Nếu cần inspect body:

- Cân nhắc dùng codec/DTO ở tầng controller nếu đủ.
- Nếu cần đọc raw bytes, đặt giới hạn kích thước bằng `DataBufferUtils.join(body, maxBytes)`.
- Sau khi đọc, nếu phải chuyển tiếp request, cần tạo lại/replay body theo API decorator phù hợp.
- Quản lý buffer kết quả và các reference được retain.
- Không log password, token hoặc dữ liệu cá nhân.

### 15.2. Đọc response body trong filter

Response body cũng có thể là stream lớn. Nếu filter đọc body để log nhưng không phát lại đúng cách, client có thể nhận body rỗng hoặc lỗi.

Nếu chỉ cần quan sát response, ưu tiên status, header, duration và byte count. Nếu thật sự cần inspect body, dùng decorator có buffering/replay có giới hạn, quản lý DataBuffer ownership và cancellation rõ ràng.

### 15.3. Không tự release buffer mà framework đang ghi

Nếu handler trả `Flux<DataBuffer>` cho response writer, các buffer được chuyển cho writer. Không thêm `doOnNext(DataBufferUtils::release)` ngay trước khi trả response nếu writer còn cần đọc chúng.

Hãy xác định điểm cuối cùng tiêu thụ buffer và để consumer đó release theo contract.

## 16. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Filter loại DataBuffer nhưng không có discard hook | Buffer bị bỏ không được release | Thêm `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` sau filter |
| Đặt doOnDiscard trước filter | Hook không bao phủ filter downstream | Đặt hook sau operator discard |
| Chỉ release sau decode thành công | Exception làm buffer hiện tại bị leak | Dùng try/finally |
| Dùng doFinally để thay doOnDiscard | Queue nội bộ có thể vẫn giữ item | Dùng discard hook và cleanup state riêng |
| Release trong doOnNext rồi vẫn forward buffer | Downstream đọc buffer đã release | Chuyển ownership hoặc decode thành kiểu khác rồi release |
| Tự gom List<DataBuffer> nhưng quên lỗi/cancel | Buffer tích lũy bị leak | Dùng DataBufferUtils.join hoặc cleanup collection tường minh |
| Join rồi release từng input và cả output | Có thể release cùng reference nhiều lần | Join nhận ownership input; consumer release output |
| Join body không giới hạn | Tăng memory pressure hoặc OOM | Dùng join với maxByteCount hoặc xử lý streaming |
| Retain nhưng không release | Reference count không về 0 | Cân bằng từng retain với một release |
| Release buffer hai lần | IllegalReferenceCountException | Ghi rõ owner và số reference |
| Đọc request body trong filter rồi gọi next | Handler có thể mất body | Buffer/rebuild request đúng contract hoặc không đọc raw body |
| Đọc response body để log rồi không replay | Client nhận body bị tiêu thụ | Dùng decorator có replay và giới hạn |
| Dùng doOnDiscard như hook toàn cục | Không bao phủ operator ngoài phạm vi hoặc state thủ công | Đặt hook đúng chain; cleanup resource riêng |
| Cho rằng mọi Publisher đều hỗ trợ discard | Custom operator có thể bỏ item mà không gọi hook | Tự triển khai cleanup trong operator tùy chỉnh |
| Tắt Netty leak detection khi có cảnh báo | Che triệu chứng, leak vẫn còn | Dùng advanced/paranoid để điều tra |
| Chỉ test success path | Không phát hiện leak khi error/cancel | Test filter, error, cancellation và prefetch queue |

## 17. Checklist trước khi đưa custom DataBuffer pipeline lên production

- [ ] Xác định implementation có pooled/reference-counted hay không.
- [ ] Ghi rõ ai sở hữu buffer tại từng bước.
- [ ] Buffer được tiêu thụ hoàn toàn được release trong finally.
- [ ] Buffer được chuyển downstream không bị release sớm.
- [ ] Mọi filter/skip/prefetch discard-aware có doOnDiscard đặt đúng vị trí.
- [ ] Buffer đang được xử lý được cleanup riêng khi decode lỗi.
- [ ] Buffer nằm trong queue được cleanup khi cancellation.
- [ ] Buffer trong collection/state do ứng dụng giữ có cleanup khi complete/error/cancel.
- [ ] Mọi retain có release tương ứng.
- [ ] join có maxByteCount khi body có thể lớn hoặc do client kiểm soát.
- [ ] Không release riêng các input đã chuyển ownership cho join.
- [ ] Không tiêu thụ request/response body mà không replay khi downstream cần đọc.
- [ ] Không log payload nhạy cảm.
- [ ] Test pooled buffer và kiểm tra refCnt sau success/filter/error/cancel.
- [ ] Bật leak detection phù hợp trong test/debug và theo dõi direct memory trong vận hành.

## 18. Tự kiểm tra

**Câu 1.** Vì sao DataBuffer trên Netty cần release dù Java có garbage collector?

Vì buffer có thể giữ direct memory trong pool và dùng reference count riêng. Garbage collection không tự giảm reference count của Netty.

**Câu 2.** Khi filter loại một DataBuffer, hook nào cần dùng?

`doOnDiscard(DataBuffer.class, DataBufferUtils::release)`, đặt downstream của filter trong thứ tự code để hook có hiệu lực với operator upstream.

**Câu 3.** Nếu decode buffer ném exception trước khi gọi release thì sao?

Buffer hiện tại có thể bị leak. Đặt decode trong try/finally và release trong finally.

**Câu 4.** doOnDiscard có tự release buffer mà ứng dụng đã lưu trong một List không?

Không. Nó xử lý item bị discard bởi operator upstream có hỗ trợ hook; collection do ứng dụng quản lý cần cleanup riêng.

**Câu 5.** Khi downstream cancel sau publishOn, buffer còn trong prefetch queue được xử lý thế nào?

Operator discard-aware dọn queue; doOnDiscard được đặt downstream có thể release các DataBuffer bị discard.

**Câu 6.** Sau DataBufferUtils.join, có cần release từng buffer đầu vào không?

Không. Các buffer đầu vào được kết hợp vào buffer kết quả; consumer release buffer kết quả sau khi dùng.

**Câu 7.** Nếu join bị cancel trước khi phát kết quả thì sao?

Spring release các buffer đã tích lũy trong quá trình join.

**Câu 8.** Nếu join thành công nhưng consumer đọc kết quả rồi ném exception thì sao?

Consumer cần release buffer kết quả trong finally.

**Câu 9.** Khi nào dùng retain?

Khi cần thêm một reference để giữ buffer qua một boundary mà chủ sở hữu reference gốc có thể release. Phải release reference bổ sung sau khi dùng.

**Câu 10.** doFinally có thay thế doOnDiscard được không?

Không. doFinally quan sát terminal/cancel signal; nó không tự biết các item trong queue nội bộ nào cần release.

**Câu 11.** WebFlux controller trả Mono<MyRequest> có phải tự release DataBuffer không?

Thông thường không. Codec của WebFlux quản lý DataBuffer khi chuyển body thành kiểu dữ liệu cấp cao hơn. Cần chú ý khi xử lý raw DataBuffer hoặc viết custom codec.

**Câu 12.** Vì sao không nên join toàn bộ một file upload lớn?

Vì join tích lũy dữ liệu trong bộ nhớ trước khi phát kết quả. Với file lớn, xử lý streaming từng chunk và release sau khi tiêu thụ thường phù hợp hơn.

## 19. Tài liệu tham khảo chính thức

- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled DataBuffer, reference count, release trong decoder/encoder và doOnDiscard.
- [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): DataBuffer trong WebFlux và khi nào ứng dụng cần tự quản lý.
- [Spring Framework — DataBufferUtils JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): release, retain, releaseConsumer, join, skipUntilByteCount và takeUntilByteCount.
- [Spring Framework — PooledDataBuffer JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/PooledDataBuffer.html): reference count, retain, release và trạng thái allocation.
- [Spring Framework — NettyDataBuffer JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/NettyDataBuffer.html): DataBuffer dựa trên Netty ByteBuf.
- [Project Reactor — Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html): doOnDiscard, onOperatorError, onNextDropped và operator-specific cleanup.
- [Netty — Reference Counted Objects](https://netty.io/wiki/reference-counted-objects.html): ownership, retain/release và troubleshooting buffer leaks.
- [Netty — ResourceLeakDetector.Level](https://netty.io/4.2/api/io/netty/util/ResourceLeakDetector.Level.html): các mức leak detection và chi phí debug.

**Ghi nhớ:** Buffer đang được đọc cần release trong finally; buffer bị filter hoặc nằm trong queue rồi bị cancel cần được release qua doOnDiscard ở đúng vị trí; buffer do ứng dụng tự giữ cần cleanup riêng. DataBufferUtils.join quản lý các input đã tích lũy khi lỗi/cancel, còn consumer release buffer kết quả sau khi sử dụng. Luôn xác định ownership và cân bằng retain/release, vì garbage collector không thay thế reference counting của pooled Netty memory.