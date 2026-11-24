# Bộ nhớ heap, bộ nhớ trực tiếp và ByteBuf của Netty

## Mục tiêu bài học

RSocket chạy trên các thư viện mạng reactive như Reactor Netty và Netty. Dữ liệu có thể đi qua nhiều vùng nhớ khác nhau trước khi tới handler: buffer ở tầng transport, ByteBuf, payload RSocket, object Java sau khi deserialize và queue trong ứng dụng. Nếu không hiểu quyền sở hữu và vòng đời của các vùng nhớ này, ứng dụng có thể tăng heap, cạn direct memory hoặc gặp lỗi rò rỉ ByteBuf dù garbage collector vẫn hoạt động.

Sau bài này, bạn có thể:

- Phân biệt heap memory, direct memory và bộ nhớ do Netty allocator quản lý.
- Hiểu vai trò của ByteBuf và sự khác nhau giữa heap/direct, pooled/unpooled.
- Quản lý reference count bằng retain và release.
- Nhận biết quyền sở hữu buffer khi truyền qua pipeline bất đồng bộ.
- Hiểu chi phí bộ nhớ khi RSocket reassemble payload lớn.
- Thiết kế giới hạn payload, stream, queue và concurrency để kiểm soát bộ nhớ.
- Phát hiện và điều tra memory leak, direct memory exhaustion và lỗi giải phóng buffer.

## Vì sao cần hiểu nhiều vùng nhớ?

Một request RSocket không nhất thiết chỉ chiếm bộ nhớ bằng kích thước object Java cuối cùng. Trong quá trình nhận dữ liệu, hệ thống có thể giữ frame, fragment, buffer reassembly, payload, object đã deserialize và dữ liệu đang chờ xử lý.

Ví dụ, một payload có 8 MiB dữ liệu sau serialization. Trong quá trình xử lý, receiver có thể cần vùng nhớ cho các fragment, payload đã ghép, bản sao khi decode và object ứng dụng. Nếu nhiều stream cùng nhận payload lớn, tổng bộ nhớ có thể tăng nhanh.

Cần phân biệt ba vùng quan trọng:

| Vùng nhớ | Được dùng cho | Cách quản lý chính |
|---|---|---|
| Java heap | Object Java, DTO, String, collection, queue và phần lớn dữ liệu ứng dụng | Garbage collector |
| Direct/native memory | Buffer ngoài heap, I/O buffer và một số vùng nhớ mạng | Vòng đời buffer, allocator và cơ chế giải phóng của runtime |
| Netty ByteBuf allocator | Buffer heap hoặc direct do Netty cấp, có thể được pool để tái sử dụng | Reference counting và allocator |

Netty ByteBuf không phải một vùng nhớ độc lập thứ ba tách biệt hoàn toàn với heap và direct memory. ByteBuf là abstraction quản lý buffer; phần dữ liệu bên dưới có thể nằm trên heap hoặc direct memory. Allocator có thể cấp phát trực tiếp hoặc lấy một vùng đã được pool.

## Heap memory

Java heap chứa các object được tạo trong ứng dụng: DTO, String, collection, wrapper, object đã deserialize và nhiều cấu trúc quản lý request.

Ví dụ:

~~~java
byte[] data = new byte[1024 * 1024];
String message = new String(data);
List<Quote> quotes = new ArrayList<>();
~~~

Các object này được garbage collector quản lý khi không còn reachable từ các root của ứng dụng. Nếu một queue giữ tham chiếu đến hàng triệu object, GC không thể thu hồi chúng dù ứng dụng không còn cần về mặt nghiệp vụ.

Các nguyên nhân heap tăng thường gặp trong ứng dụng realtime:

- Giữ lịch sử event không có giới hạn.
- Queue request hoặc response không giới hạn.
- Cache không có eviction hoặc TTL.
- Buffer hóa toàn bộ file trước khi xử lý.
- Giữ subscription hoặc callback khiến object không được thu hồi.
- Chuyển ByteBuf thành byte[] hoặc String nhiều lần, tạo bản sao lớn.

Heap exhaustion thường biểu hiện bằng OutOfMemoryError: Java heap space hoặc GC overhead limit exceeded. Hãy kiểm tra heap dump, retained size, object histogram và đường tham chiếu giữ object.

## Direct memory

Direct memory là bộ nhớ ngoài heap được dùng bởi các buffer trực tiếp. Java cung cấp ByteBuffer.allocateDirect() để tạo direct ByteBuffer. Các thư viện mạng thường dùng direct buffer để giảm một số lần sao chép giữa heap và native I/O.

~~~java
ByteBuffer direct = ByteBuffer.allocateDirect(64 * 1024);
direct.put(data);
direct.flip();
~~~

Object ByteBuffer vẫn có wrapper trên heap, nhưng vùng dữ liệu chính nằm ngoài heap. Direct buffer không được thu hồi theo cùng cách với byte[] thông thường; việc giải phóng phụ thuộc vòng đời wrapper, runtime và cơ chế cleaner nội bộ. API ByteBuffer công khai không cung cấp một phương thức release() thông dụng giống Netty ByteBuf.

Direct memory có thể cạn ngay cả khi heap còn nhiều dung lượng. Một lỗi thường thấy là OutOfMemoryError: Direct buffer memory. Việc chỉ tăng -Xmx không nhất thiết giải quyết được lỗi này.

JVM có tùy chọn -XX:MaxDirectMemorySize để đặt giới hạn cho direct ByteBuffer memory. Cách Netty cấp phát và theo dõi native memory còn phụ thuộc phiên bản Netty, JVM và allocator path. Khi vận hành, hãy theo dõi cả heap lẫn direct/native memory thay vì suy luận direct memory chỉ từ heap usage.

## Netty ByteBuf

Netty cung cấp ByteBuf để đọc và ghi dữ liệu hiệu quả. ByteBuf có readerIndex và writerIndex, giúp quản lý vùng dữ liệu đã đọc và vùng dữ liệu có thể đọc tiếp.

~~~java
ByteBuf buffer = PooledByteBufAllocator.DEFAULT.directBuffer(1024);
try {
    buffer.writeBytes(data);

    int readable = buffer.readableBytes();
    byte[] copy = new byte[readable];
    buffer.getBytes(buffer.readerIndex(), copy);

    process(copy);
} finally {
    buffer.release();
}
~~~

Ví dụ tạo direct ByteBuf từ pooled allocator, ghi dữ liệu, sao chép phần có thể đọc sang byte[] rồi release ByteBuf. Trong code thực tế, chỉ sao chép sang byte[] khi ứng dụng thực sự cần dữ liệu độc lập; thao tác sao chép có thể tăng chi phí CPU và heap.

### Heap ByteBuf và direct ByteBuf

ByteBuf có thể lưu dữ liệu trên heap hoặc direct memory:

| Loại | Vùng nhớ dữ liệu | Đặc điểm |
|---|---|---|
| Heap ByteBuf | Java heap | Có thể truy cập backing array khi implementation hỗ trợ; chịu ảnh hưởng GC |
| Direct ByteBuf | Direct/native memory | Phù hợp với một số đường I/O; cần quản lý vòng đời reference count |

Direct không luôn nhanh hơn heap trong mọi thao tác. Nếu ứng dụng liên tục chuyển direct buffer thành byte[] để xử lý, lợi ích giảm copy có thể mất đi. Hãy đo theo workload thật.

### Pooled và unpooled

Pooled/unpooled mô tả cách allocator quản lý vùng nhớ, không phải vị trí heap/direct:

- **Pooled allocator:** tái sử dụng vùng nhớ đã cấp phát để giảm chi phí cấp phát/giải phóng thường xuyên.
- **Unpooled allocator:** cấp buffer mà không dùng cơ chế pool tương ứng.

Do đó có thể gặp heap pooled, direct pooled, heap unpooled và direct unpooled tùy allocator. Khi ByteBuf được release, bộ nhớ pooled có thể được trả về pool để tái sử dụng thay vì trả ngay cho hệ điều hành. Vì vậy, mức direct memory của process có thể vẫn cao sau khi các buffer đã được release đúng cách.

Một mức sử dụng direct memory ổn định không nhất thiết là leak. Điều cần điều tra là xu hướng tăng không hồi phục, số buffer đang được giữ, reference count và các chỉ số allocator.

## Reference counting: retain và release

Khác với object Java thông thường, nhiều ByteBuf của Netty dùng reference counting. Khi buffer được tạo, nó có reference count ban đầu. Mỗi lần một thành phần khác cần giữ buffer lâu hơn vòng đời hiện tại, nó có thể retain để tăng reference count. Khi không còn sử dụng, mỗi quyền sở hữu phải được release đúng một lần.

Quy tắc cốt lõi:

1. Thành phần tạo buffer chịu trách nhiệm release nếu không chuyển quyền sở hữu.
2. Khi chuyển buffer cho thành phần khác theo hợp đồng ownership transfer, bên gửi không tiếp tục release cùng quyền sở hữu đó.
3. Khi cần giữ buffer vượt qua callback hoặc scope hiện tại, phải retain theo đúng API.
4. Mỗi retain cần một release tương ứng.
5. Không release hai lần cùng một quyền sở hữu.

Nếu reference count về 0, Netty có thể giải phóng hoặc trả vùng nhớ về allocator pool. Gọi release quá nhiều lần có thể gây IllegalReferenceCountException hoặc lỗi truy cập buffer đã giải phóng.

### Ví dụ retain khi tạo một view cần sống độc lập

Các phương thức slice(), duplicate() và các biến thể tạo view có thể chia sẻ vùng nhớ gốc. View thông thường không nhất thiết tăng reference count. Nếu view cần sống lâu hơn buffer gốc, dùng biến thể retained tương ứng:

~~~java
ByteBuf source = allocator.buffer();
source.writeBytes(data);

ByteBuf view = source.retainedSlice(0, source.readableBytes());
try {
    process(view);
} finally {
    view.release();
}

source.release();
~~~

retainedSlice() tăng reference count để view có một quyền sở hữu riêng. Khi xử lý xong, release view và release buffer gốc theo đúng quyền sở hữu của từng bên.

Ngược lại, copy() tạo vùng dữ liệu độc lập, nên có chi phí cấp phát và sao chép nhưng không chia sẻ nội dung với buffer gốc.

### Tránh release khi thành phần khác vẫn đang dùng

Ví dụ, một handler nhận ByteBuf và chuyển việc xử lý sang scheduler khác. Nếu handler release buffer ngay sau khi gửi tác vụ bất đồng bộ, worker có thể đọc vùng nhớ đã được giải phóng.

Hãy retain trước khi chuyển quyền sử dụng sang tác vụ bất đồng bộ, rồi release trong nhánh kết thúc của tác vụ. Cách đơn giản hơn trong nhiều trường hợp là decode hoặc copy dữ liệu cần thiết trước khi rời khỏi callback nhận buffer.

## Quyền sở hữu buffer trong pipeline Netty

Trong pipeline Netty, ownership cần rõ ràng ở mỗi bước. Một handler có thể:

- Đọc buffer và xử lý ngay trong callback.
- Chuyển buffer sang handler tiếp theo.
- Tạo retained slice để xử lý bất đồng bộ.
- Copy phần dữ liệu cần giữ sang object ứng dụng.
- Giải phóng buffer khi không chuyển tiếp.

Với outbound write, khi buffer được chuyển cho pipeline thông qua write(), ownership được chuyển theo hợp đồng của Netty. Không tiếp tục release cùng quyền sở hữu sau khi đã chuyển thành công. Nếu thao tác write ném lỗi đồng bộ trước khi pipeline nhận ownership, code vẫn cần giải phóng buffer đã tạo.

Với inbound handler, hãy kiểm tra loại base class và hợp đồng xử lý. SimpleChannelInboundHandler thường tự release message được chấp nhận sau callback; ChannelInboundHandlerAdapter không tự động có cùng hành vi. Không copy một mẫu release từ handler này sang handler khác mà không kiểm tra ownership.

Trong ứng dụng Spring RSocket thông thường, handler nhận DTO đã deserialize nên không phải tự release ByteBuf. Việc quản lý buffer thường do transport và framework đảm nhiệm. Khi làm việc trực tiếp với ByteBuf hoặc Payload ref-counted, trách nhiệm ownership chuyển tới code ứng dụng theo API cụ thể.

## ByteBuf và Payload trong RSocket

RSocket Java xây dựng payload trên các buffer của implementation. Payload có Data và Metadata, còn transport/decoder quyết định cách buffer được giữ và chuyển cho tầng ứng dụng.

Với cách dùng Spring thông thường:

~~~java
@MessageMapping("quotes.latest")
Mono<Quote> latest(QuoteRequest request) {
    return quoteService.findLatest(request.symbol());
}
~~~

Handler làm việc với DTO và Reactor type. Không cần gọi ByteBuf.release() cho các DTO này.

Khi dùng API RSocket mức thấp và nhận trực tiếp Payload, hãy đọc hợp đồng của decoder đang cấu hình. Một số chế độ decode có thể tạo bản sao dữ liệu, trong khi chế độ zero-copy giữ liên hệ với buffer ref-counted. Nếu dùng PayloadDecoder.ZERO_COPY, code cần release Payload đúng lúc sau khi hoàn tất việc đọc; nếu giữ dữ liệu cho tác vụ bất đồng bộ, cần retain hoặc tạo bản sao theo hợp đồng của phiên bản thư viện.

Không nên release Payload khi một pipeline bất đồng bộ vẫn còn đọc Data hoặc Metadata. Cũng không nên retain mọi Payload một cách phòng ngừa nếu không có kế hoạch release tương ứng.

## Fragmentation và reassembly ảnh hưởng bộ nhớ ra sao?

RSocket có thể chia một payload lớn thành nhiều frame để truyền. Receiver ghép các fragment thành payload hoàn chỉnh trước khi giao cho handler. Điều này giảm kích thước mỗi frame trên đường truyền, nhưng không loại bỏ nhu cầu bộ nhớ cho payload hoàn chỉnh.

Ví dụ, một payload 12 MiB được chia thành nhiều fragment 64 KiB. Receiver vẫn phải giữ đủ dữ liệu cần thiết để reassemble payload trước khi handler xử lý. Nếu nhiều stream cùng làm việc này, bộ nhớ sử dụng có thể tăng đáng kể.

Một ước lượng thô:

~~~text
Bộ nhớ reassembly đồng thời
≈ số payload đang reassemble × kích thước payload trung bình
~~~

Ví dụ, 40 payload đồng thời, mỗi payload khoảng 8 MiB, đã cần khoảng 320 MiB dữ liệu payload thô trước khi tính overhead, object wrapper, bản sao decode và buffer của các tầng khác. Đây chỉ là phép ước lượng dung lượng dữ liệu, không phải dự báo chính xác heap/direct memory.

Hãy phối hợp:

- maxInboundPayloadSize để giới hạn kích thước payload sau reassembly.
- fragment size để kiểm soát kích thước frame gửi.
- Giới hạn số stream hoặc request đang hoạt động.
- Backpressure và queue hữu hạn.
- Timeout cho stream hoặc thao tác kéo dài.
- Chunking ở tầng ứng dụng cho file hoặc dữ liệu lớn cần xử lý từng phần.

## Backpressure không tự bảo đảm bộ nhớ có giới hạn

Backpressure điều tiết số phần tử mà consumer yêu cầu. Nhưng một phần tử có thể là payload 20 MiB. Nếu consumer yêu cầu 100 phần tử cùng lúc, tổng dữ liệu đang được giữ vẫn có thể rất lớn.

Ngoài ra, các toán tử buffer có thể giữ dữ liệu trong queue. Ví dụ onBackpressureBuffer() không giới hạn có thể khiến heap tăng liên tục khi producer nhanh hơn consumer.

Một thiết kế an toàn cần xác định:

- Số phần tử tối đa đang chờ.
- Tổng dung lượng byte tối đa nếu payload có kích thước biến đổi.
- Hành vi khi queue đầy: từ chối, drop, coalesce hoặc lưu bền vững.
- Số stream đồng thời được phép.
- Thời gian tối đa một phần tử được giữ trong queue.

Khi payload có kích thước thay đổi lớn, giới hạn số phần tử chưa đủ. Có thể cần một budget theo byte ở tầng ứng dụng để kiểm soát tổng dữ liệu đang chờ.

## Quản lý tài nguyên theo vòng đời stream

Một stream có thể giữ subscription, ByteBuf, Payload, queue, timer hoặc listener. Khi stream complete, error hoặc cancel, các tài nguyên liên quan cần được giải phóng.

Với Reactor, doFinally là hook phù hợp để quan sát mọi terminal signal:

~~~java
Flux<Quote> stream = quoteService.watch(symbol)
    .doFinally(signal -> {
        metrics.recordTermination(symbol, signal.name());
        releaseStreamResources(symbol);
    });
~~~

Nếu resource được cấp phát theo subscription, hãy tạo resource theo từng subscription và gắn cleanup với cùng vòng đời. Tránh tạo ByteBuf hoặc listener ở ngoài pipeline rồi quên giải phóng khi publisher không bao giờ được subscribe.

Với cleanup bất đồng bộ, dùng các cơ chế quản lý resource phù hợp như using hoặc usingWhen, để tài nguyên được đóng cả khi complete, error hoặc cancel. Cleanup nên idempotent và không chặn event loop.

## Phát hiện ByteBuf leak

Netty có ResourceLeakDetector để phát hiện một số trường hợp buffer được cấp phát nhưng không được release đúng cách. Trong môi trường kiểm thử hoặc điều tra, có thể bật mức phát hiện cao hơn bằng JVM property:

~~~text
-Dio.netty.leakDetection.level=paranoid
~~~

Mức PARANOID tạo thêm overhead đáng kể, vì vậy chỉ nên bật trong test hoặc một phiên điều tra có kiểm soát. Với môi trường chạy thường xuyên, chọn mức phát hiện phù hợp với chi phí quan sát và tải thực tế.

Khi phát hiện leak:

1. Xem stack trace nơi buffer được cấp phát.
2. Tìm đường đi mà buffer được chuyển qua handler hoặc publisher.
3. Xác định nơi ownership được chuyển giao.
4. Kiểm tra mọi nhánh complete, error, cancel và exception đồng bộ.
5. Kiểm tra retained slice/duplicate có release tương ứng hay không.
6. Viết test tái hiện nhánh lỗi và xác nhận buffer được giải phóng.

Leak detector không đảm bảo phát hiện mọi lỗi và có thể chỉ báo khi buffer đã bị GC mà vẫn chưa release. Không có cảnh báo leak cũng không chứng minh code quản lý ownership đúng.

## Theo dõi heap, direct memory và allocator

Đừng chỉ nhìn biểu đồ heap. Một ứng dụng RSocket có thể có heap ổn định nhưng direct memory tăng, hoặc direct memory ổn định trong khi heap tăng do queue và DTO.

Các nguồn quan sát hữu ích:

| Nguồn | Thông tin cần theo dõi |
|---|---|
| JVM heap metrics | Heap used/committed, GC pause, allocation rate |
| BufferPoolMXBean | Dung lượng và số buffer direct/mapped đang được JVM theo dõi |
| Netty allocator metrics | Số vùng nhớ heap/direct được allocator quản lý, mức sử dụng pool theo API của phiên bản |
| Process/container metrics | RSS, native memory, giới hạn container và mức sử dụng tổng |
| RSocket/application metrics | Số stream, payload size, request in-flight, queue depth và lỗi vượt giới hạn |

Nếu Native Memory Tracking được bật khi khởi động JVM, có thể dùng công cụ chẩn đoán JVM để xem thống kê native memory. Cần nhớ RSS của process bao gồm nhiều loại vùng nhớ, không chỉ direct ByteBuffer.

Một số dấu hiệu thường gặp:

- Heap tăng liên tục: kiểm tra collection, cache, queue, DTO và subscription bị giữ.
- Direct buffer memory OOME: kiểm tra direct memory cap, ByteBuf chưa release, payload lớn đồng thời và allocator.
- RSS tăng nhưng heap/direct metric ổn định: xem thêm thread stack, native library, memory mapping và vùng native khác.
- Direct memory vẫn cao nhưng không tăng theo thời gian: có thể allocator đang giữ pool để tái sử dụng; so sánh metric pool và số buffer đang được giữ trước khi kết luận leak.

## Thiết kế ngân sách bộ nhớ cho RSocket

Hãy lập ngân sách theo các giới hạn đồng thời, thay vì chỉ chọn một giới hạn payload.

Ví dụ, giả sử:

- Payload inbound tối đa: 8 MiB.
- Tối đa 20 stream đồng thời có thể reassemble payload lớn.
- Queue ứng dụng tối đa 100 phần tử, mỗi phần tử tối đa 64 KiB.
- Mỗi stream có timeout và cleanup rõ ràng.

Phần dữ liệu reassembly có thể cần đến khoảng 160 MiB trong trường hợp tất cả stream cùng nhận payload sát giới hạn. Queue có thể cần thêm tối đa khoảng 6,25 MiB dữ liệu thô, chưa tính object và overhead. Đây là ngân sách minh họa để thấy ảnh hưởng của concurrency; khi triển khai phải đo bằng payload thực tế và tính cả bản sao.

Các nguyên tắc:

- Đặt maxInboundPayloadSize theo nhu cầu nghiệp vụ.
- Giới hạn số request/stream đang hoạt động.
- Giới hạn queue theo phần tử và byte.
- Tránh buffer vô hạn.
- Giải phóng Payload/ByteBuf theo đúng ownership.
- Giám sát heap, direct memory, allocator và RSS.
- Kiểm thử nhiều stream đồng thời với payload lớn, không chỉ một request đơn lẻ.

## Kiểm thử và xử lý sự cố

Các kịch bản nên có:

1. Cấp phát và release ByteBuf trong nhánh thành công.
2. Exception xảy ra sau cấp phát nhưng trước khi chuyển ownership.
3. Buffer được chuyển sang xử lý bất đồng bộ và vẫn còn hợp lệ.
4. retainedSlice hoặc retainedDuplicate được release đúng một lần.
5. Cancel stream khi buffer đang được giữ.
6. Payload lớn được fragmentation và reassembly trong giới hạn.
7. Payload vượt maxInboundPayloadSize bị từ chối.
8. Nhiều stream đồng thời tạo áp lực direct memory.
9. Queue đầy khi producer nhanh hơn consumer.
10. Dùng leak detector trong test để phát hiện đường đi quên release.

Khi gặp lỗi OutOfMemoryError, ghi nhận loại lỗi và thời điểm xảy ra. Heap dump hữu ích cho Java heap; direct/native memory cần thêm BufferPoolMXBean, allocator metrics, process metrics và công cụ native memory. Tăng heap hoặc direct memory limit mà không tìm nguyên nhân có thể chỉ trì hoãn lần lỗi tiếp theo.

## Checklist quản lý bộ nhớ

Trước khi triển khai RSocket ở tải thực tế, hãy trả lời:

1. Object ứng dụng chiếm heap bao nhiêu và buffer transport chiếm direct memory bao nhiêu?
2. ByteBuf được tạo ở đâu và ai sở hữu quyền release?
3. Buffer có được giữ qua callback hoặc tác vụ bất đồng bộ không?
4. Mỗi retain có release tương ứng ở complete, error và cancel không?
5. Payload decoder có dùng zero-copy không và ai release Payload?
6. maxInboundPayloadSize và fragment size được cấu hình ở cả hai phía chưa?
7. Có giới hạn số stream, queue và tổng byte đang chờ không?
8. Direct memory, heap và Netty allocator được giám sát riêng chưa?
9. Leak detection đã được dùng trong kiểm thử hoặc điều tra chưa?
10. Có test tải với nhiều payload lớn đồng thời không?

Heap, direct memory và Netty ByteBuf có vòng đời khác nhau. Garbage collector quản lý object Java, còn ByteBuf ref-counted cần ownership và release chính xác. Khi kết hợp giới hạn payload, concurrency, queue, backpressure và giám sát allocator, ứng dụng RSocket có thể xử lý dữ liệu realtime mà vẫn kiểm soát được tài nguyên.

