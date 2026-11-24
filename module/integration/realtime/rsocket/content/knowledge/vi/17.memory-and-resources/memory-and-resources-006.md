# Quản lý kết nối, đăng ký dài hạn và tài nguyên dùng chung

RSocket thường giữ kết nối mở để nhiều interaction có thể dùng chung một phiên TCP hoặc WebSocket. Các luồng realtime có thể tồn tại trong thời gian dài, còn payload lớn có thể tạo ra nhiều buffer và fragment trước khi được ứng dụng xử lý. Nếu không quản lý đúng vòng đời của kết nối, subscription, Payload và ByteBuf, ứng dụng dễ gặp rò rỉ bộ nhớ, giữ tài nguyên sau khi client đã rời đi hoặc tăng bộ nhớ đột biến khi tốc độ nhận dữ liệu cao hơn tốc độ xử lý.

Bài học này tập trung vào cách quản lý tài nguyên trong RSocket Java: chia sẻ kết nối, dọn dẹp đăng ký dài hạn, hiểu reference counting của Netty ByteBuf, giải phóng Payload đúng thời điểm và giới hạn bộ nhớ khi truyền dữ liệu lớn. Nội dung gắn với RSocket qua TCP hoặc WebSocket, các interaction reactive và cách triển khai client/server bằng Java, Spring Boot.

Sau bài học, bạn có thể:

- Phân biệt vòng đời của kết nối, interaction, subscription, Payload và ByteBuf.
- Hiểu reference counting và quy tắc retain/release của Netty.
- Xử lý Payload nhận được mà không gây rò rỉ hoặc truy cập buffer đã giải phóng.
- Chia dữ liệu lớn thành các chunk có kích thước giới hạn.
- Phân biệt fragmentation ở tầng giao thức với chunking ở tầng ứng dụng.
- Giới hạn buffer, concurrency và prefetch để kiểm soát bộ nhớ.
- Dọn dẹp subscription dài hạn khi hoàn tất, gặp lỗi, hủy hoặc ứng dụng shutdown.

## 1. Các lớp tài nguyên trong một kết nối RSocket

Một kết nối RSocket có thể phục vụ nhiều interaction đồng thời. Mỗi interaction lại có thể tạo ra các subscription và payload riêng. Khi truyền dữ liệu lớn, payload có thể tham chiếu đến các vùng nhớ do Netty quản lý.

Cần phân biệt ít nhất năm lớp tài nguyên:

| Tài nguyên | Vòng đời | Ví dụ |
|---|---|---|
| Transport connection | Từ lúc kết nối mạng được mở đến khi đóng | TCP channel hoặc WebSocket session |
| RSocket session | Từ SETUP thành công đến khi session đóng | Đối tượng RSocket |
| Interaction | Từ khi mở request đến complete, error hoặc cancel | request-stream |
| Subscription | Từ subscribe đến terminal signal hoặc cancel | Flux theo dõi giá realtime |
| Payload/ByteBuf | Theo decoder và ownership contract; với zero-copy đến khi reference count về 0 | Data và metadata của một frame |

~~~mermaid
flowchart TD
    A[Transport connection] --> B[RSocket session]
    B --> C1[Request-response]
    B --> C2[Long-lived request-stream]
    B --> C3[Request-channel]
    C2 --> D[Reactive subscription]
    C3 --> E[Reactive subscription]
    D --> F[Payload]
    E --> G[Payload]
    F --> H[Netty ByteBuf data/metadata]
    G --> H
    H --> I[release when ownership ends]
~~~

Đóng một subscription không nhất thiết đóng toàn bộ RSocket connection. Ngược lại, đóng connection có thể làm nhiều interaction trên connection đó kết thúc. Giải phóng một Payload cũng không có nghĩa connection hoặc subscription đã kết thúc.

Thiết kế tốt phải xác định rõ ai sở hữu từng tài nguyên và sự kiện nào kết thúc vòng đời của nó.

## 2. RSocket và Netty sử dụng buffer có reference counting

RSocket Java dựa trên Netty để truyền dữ liệu. Netty dùng reference counting cho nhiều đối tượng như ByteBuf nhằm giảm cấp phát và sao chép bộ nhớ.

Một ByteBuf có reference count:

- Khi được tạo, buffer thường bắt đầu với reference count bằng 1.
- retain() tăng reference count khi một thành phần cần giữ buffer lâu hơn quyền sở hữu hiện tại.
- release() giảm reference count.
- Khi reference count về 0, vùng nhớ được trả về allocator hoặc pool để tái sử dụng.
- Truy cập buffer sau khi reference count đã về 0 có thể gây lỗi IllegalReferenceCountException hoặc hành vi không hợp lệ.

~~~mermaid
flowchart TD
    A[Allocate ByteBuf] --> B[refCnt = 1]
    B --> C{Need another owner?}
    C -->|Yes| D[retain]
    D --> E[refCnt = 2]
    C -->|No| F[Use buffer]
    E --> G[Owner A releases]
    G --> H[refCnt = 1]
    H --> I[Owner B releases]
    F --> J[release]
    I --> K[refCnt = 0]
    J --> K
    K --> L[Memory returned to allocator]
~~~

Reference counting không tự động hiểu dữ liệu đã được xử lý xong hay chưa. Ứng dụng phải tuân thủ hợp đồng ownership của API đã nhận buffer.

### retain và release phải cân bằng

Nếu gọi retain() một lần, cần có một release() tương ứng cho phần tham chiếu được giữ thêm. Không release quá số lần đã retain và không release một buffer mà thành phần khác vẫn còn quyền sở hữu.

Ví dụ:

~~~java
ByteBuf retained = source.retainedDuplicate();

try {
    processAsync(retained);
} catch (Throwable error) {
    retained.release();
    throw error;
}
~~~

Ví dụ trên minh họa việc tạo một view có reference count được tăng trước khi chuyển cho một tác vụ khác. Tác vụ nhận buffer phải chịu trách nhiệm release đúng một lần khi xử lý xong. Trong code production, cần xử lý cả trường hợp tác vụ bị hủy hoặc không thể được lập lịch để tránh bỏ quên release.

Nếu chỉ cần dữ liệu sau khi xử lý hiện tại kết thúc, thường không cần retain. Hãy decode hoặc copy sang kiểu dữ liệu độc lập rồi release buffer gốc.

## 3. Payload cũng là tài nguyên được reference-count

RSocket Java biểu diễn data và metadata của một thông điệp bằng Payload. Cách Payload giữ vùng nhớ phụ thuộc vào PayloadDecoder mà endpoint nhận đã cấu hình.

RSocket Java có hai lựa chọn chính:

| Decoder | Cách tạo data/metadata | Có cần ứng dụng tự theo dõi release? |
|---|---|---|
| PayloadDecoder.DEFAULT | Copy độc lập từ frame buffer | Không cần quản lý reference count của frame gốc |
| PayloadDecoder.ZERO_COPY | Tạo retained slice trên frame buffer | Có; phải release Payload khi xử lý xong |

DEFAULT là cấu hình mặc định. Nó dễ dùng hơn vì data và metadata được copy, không cần theo dõi và release thủ công. ZERO_COPY giảm sao chép và có thể giảm latency, nhưng chuyển trách nhiệm quản lý vòng đời buffer sang ứng dụng.

Ví dụ bật zero-copy ở phía client:

~~~java
RSocketConnector connector = RSocketConnector.create()
    .payloadDecoder(PayloadDecoder.ZERO_COPY);
~~~

Nếu không bật ZERO_COPY, không áp dụng máy móc các ví dụ release bên dưới cho mọi Payload. Hãy kiểm tra decoder và ownership contract của endpoint đang nhận dữ liệu.

Khi nhận Payload từ API RSocket mức thấp với PayloadDecoder.ZERO_COPY:

1. Đọc data và metadata khi payload còn hợp lệ.
2. Chuyển dữ liệu thành object độc lập hoặc copy sang vùng nhớ có ownership riêng nếu cần giữ lâu.
3. Gọi release() đúng một lần khi ứng dụng đã xử lý xong payload.
4. Nếu chuyển quyền sở hữu sang thành phần khác, phải thống nhất rõ bên nào chịu trách nhiệm release.

Ví dụ đọc response:

~~~java
// Giả sử endpoint nhận đã cấu hình PayloadDecoder.ZERO_COPY.
Mono<OrderView> order =
    socket.requestResponse(requestPayload)
        .map(payload -> {
            try {
                return decodeOrder(payload.getData());
            } finally {
                payload.release();
            }
        });
~~~

decodeOrder cần tạo OrderView độc lập với ByteBuf. Nếu object trả về vẫn giữ slice hoặc reference đến buffer gốc, release trong finally sẽ làm dữ liệu đó không còn hợp lệ.

Với request-stream, phải release từng payload, không chỉ payload cuối cùng:

~~~java
// Giả sử endpoint nhận đã cấu hình PayloadDecoder.ZERO_COPY.
Flux<Event> events =
    socket.requestStream(requestPayload)
        .map(payload -> {
            try {
                return decodeEvent(payload.getData());
            } finally {
                payload.release();
            }
        });
~~~

Nếu dùng Spring RSocketRequester và nhận DTO đã được decode, framework quản lý Payload ở tầng chuyển đổi. Không tự release ByteBuf trong DTO nếu DTO không sở hữu ByteBuf. Nếu dùng API RSocket mức thấp hoặc custom codec, cần đọc rõ hợp đồng ownership của API, PayloadDecoder và codec đang sử dụng.

### Tránh bỏ qua release khi có lỗi trong chế độ ZERO_COPY

Với ZERO_COPY, đặt release trong finally để bảo đảm buffer được giải phóng cả khi decoder phát sinh exception:

~~~java
Event decodeAndRelease(Payload payload) {
    try {
        return decodeEvent(payload.getData());
    } finally {
        payload.release();
    }
}
~~~

Không viết theo kiểu chỉ release sau khi decode thành công:

~~~java
// Không an toàn nếu decodeEvent ném exception.
Event event = decodeEvent(payload.getData());
payload.release();
return event;
~~~

Nếu decoder lỗi, đoạn mã thứ hai bỏ qua release và có thể làm rò rỉ buffer.

## 4. Quy tắc ownership khi gửi Payload

Khi gửi Payload qua các API RSocket như requestResponse, fireAndForget, requestStream hoặc requestChannel, hãy tuân thủ hợp đồng ownership của API. Với các API gửi của RSocket Java, payload được chuyển cho tầng RSocket để gửi; caller không nên tiếp tục sử dụng hoặc tự release lại payload sau khi đã chuyển quyền sở hữu, trừ khi tài liệu của API/implementation chỉ rõ một hợp đồng khác.

Tạo payload mới cho mỗi lần subscribe nếu pipeline có thể được thực thi nhiều lần:

~~~java
Mono<OrderView> getOrder(RSocket socket, byte[] encodedRequest) {
    return Mono.defer(() -> {
        Payload request = DefaultPayload.create(
            Unpooled.copiedBuffer(encodedRequest)
        );

        return socket.requestResponse(request)
            .map(response -> {
                try {
                    return decodeOrder(response.getData());
                } finally {
                    response.release();
                }
            });
    });
}
~~~

Mono.defer tạo Payload mới cho mỗi subscription. Điều này tránh gửi lại cùng một Payload đã được chuyển ownership hoặc đã bị giải phóng ở lần thực thi trước.

Không dùng chung một ByteBuf có thể thay đổi giữa nhiều request đồng thời. Nếu cần gửi cùng nội dung cho nhiều peer, có thể tạo bản sao độc lập hoặc retain riêng cho từng ownership và release đúng số lần.

### copy, slice và duplicate khác nhau thế nào?

| API | Tạo vùng dữ liệu mới? | Chia sẻ bộ nhớ gốc? | Reference count |
|---|---|---|---|
| copy() | Có | Không | Buffer mới có vòng đời riêng |
| slice() | Không | Có | Không tự tăng reference count |
| duplicate() | Không | Có | Không tự tăng reference count |
| retainedSlice() | Không | Có | Tăng reference count |
| retainedDuplicate() | Không | Có | Tăng reference count |

slice() và duplicate() tạo view trên cùng vùng nhớ. Chúng không làm dữ liệu sống lâu hơn. Nếu buffer gốc bị release, view không retained cũng không còn an toàn để truy cập.

Dùng copy() khi cần dữ liệu độc lập hoặc cần giữ lâu sau khi payload gốc được release. Dùng retainedSlice() hoặc retainedDuplicate() khi muốn chia sẻ vùng nhớ và có thể quản lý ownership rõ ràng ở cả hai phía.

## 5. Chọn allocator và tránh cấp phát không cần thiết

Netty hỗ trợ heap buffer, direct buffer và pooled allocator. Pooled allocator tái sử dụng vùng nhớ để giảm chi phí cấp phát, nhưng làm cho việc quản lý reference count trở nên đặc biệt quan trọng.

Một số nguyên tắc:

- Ưu tiên allocator được transport/framework cung cấp khi có thể.
- Không tạo buffer lớn hơn nhu cầu thực tế.
- Tránh copy data nhiều lần giữa byte[], String và ByteBuf.
- Chỉ giữ buffer khi thực sự cần zero-copy hoặc chia sẻ vùng nhớ.
- Không giữ ByteBuf trong cache hoặc collection dài hạn nếu chưa thiết kế ownership.
- Đo direct memory và heap memory riêng khi điều tra sự cố.

Ví dụ tạo payload từ một mảng byte có bản sao độc lập:

~~~java
Payload payload = DefaultPayload.create(
    Unpooled.copiedBuffer(fileChunk)
);
~~~

copiedBuffer sao chép byte[] vào ByteBuf. Sau khi tạo, thay đổi mảng byte gốc không làm thay đổi nội dung payload. Nếu dùng wrappedBuffer, ByteBuf có thể chia sẻ mảng byte gốc; khi đó không được sửa mảng trong lúc payload đang được gửi.

Không cần gọi retain() chỉ vì buffer đến từ pooled allocator. Hãy tăng reference count khi có thêm một chủ sở hữu thực sự, không phải để "giữ buffer cho chắc".

## 6. Truyền dữ liệu lớn: fragmentation và chunking

RSocket có thể phân mảnh một payload lớn thành nhiều fragment ở tầng giao thức. Receiver tập hợp các fragment để khôi phục payload của interaction. Cơ chế này giúp payload vượt giới hạn kích thước frame của transport, nhưng không tự động làm cho một thông điệp lớn trở thành luồng dữ liệu có bộ nhớ không giới hạn.

Cần phân biệt:

| Cơ chế | Phạm vi | Tác dụng |
|---|---|---|
| Fragmentation | Tầng giao thức | Chia một payload thành các frame nhỏ hơn để truyền |
| Chunking | Tầng ứng dụng | Chia một nội dung lớn thành nhiều message có kích thước giới hạn |
| Request-stream | Một request, nhiều response | Tải dữ liệu theo từng phần từ server |
| Request-channel | Nhiều request item và nhiều response item | Gửi dữ liệu theo từng phần và nhận phản hồi trong khi truyền |

Nếu receiver cần tập hợp toàn bộ fragment thành một Payload trước khi handler xử lý, tổng bộ nhớ của payload lớn vẫn phải được dành chỗ. Vì vậy, fragmentation không thay thế chunking ở tầng ứng dụng khi dữ liệu có thể rất lớn.

### Khi nào dùng fragmentation?

Dùng fragmentation khi một payload đơn lẻ cần lớn hơn kích thước frame cho phép và cả hai peer hỗ trợ cách phân mảnh đã cấu hình. Trong RSocket Java, `fragment(mtu)` đặt ngưỡng kích thước để payload được chia thành fragment. Phía nhận có thể đặt `maxInboundPayloadSize` để giới hạn kích thước payload sau khi tái lắp ghép:

~~~java
RSocketConnector connector = RSocketConnector.create()
    .fragment(16 * 1024)
    .maxInboundPayloadSize(32 * 1024 * 1024);
~~~

Trong ví dụ, sender chia frame lớn hơn 16 KiB thành fragment; receiver từ chối payload sau tái lắp ghép nếu vượt 32 MiB. Giá trị `maxInboundPayloadSize` phải lớn hơn hoặc bằng `maxFrameLength` của transport; nếu nhỏ hơn, cấu hình connector không hợp lệ. Nếu không đặt giới hạn này, mặc định của RSocket Java không giới hạn kích thước payload tái lắp ghép ở tầng connector.

Chọn MTU/fragment size phù hợp với transport, giới hạn kích thước payload tối đa và kiểm thử trường hợp peer không hỗ trợ hoặc cấu hình khác nhau.

Fragmentation không làm giảm tổng số byte cần truyền và có thể làm tăng chi phí buffer do phải giữ các fragment trước khi tái lắp ghép. Không dùng nó như một cách để bỏ qua giới hạn kích thước request.

### Khi nào dùng chunking?

Với file, ảnh, video hoặc dữ liệu nhị phân lớn, thường nên chia dữ liệu thành chunk ở tầng ứng dụng. Ví dụ mỗi chunk chứa:

~~~java
public record FileChunk(
    String transferId,
    long sequence,
    boolean last,
    byte[] content
) {}
~~~

transferId nhận diện một lần truyền, sequence xác định thứ tự chunk và last báo chunk cuối theo hợp đồng ứng dụng. Có thể bổ sung checksum, kích thước tổng, offset hoặc thông tin resume nếu cần.

Giữ kích thước chunk có giới hạn, ví dụ 32 KiB hoặc 64 KiB, rồi đo hiệu năng thực tế để chọn giá trị phù hợp. Chunk quá nhỏ làm tăng số message và overhead; chunk quá lớn làm tăng bộ nhớ mỗi interaction và độ trễ khi buffer.

## 7. Tải dữ liệu lớn bằng request-stream

Khi client tải dữ liệu từ server, responder có thể phát từng chunk bằng Flux:

~~~java
@MessageMapping("files.download")
public Flux<FileChunk> download(DownloadRequest request) {
    return fileService.readChunks(
        request.fileId(),
        64 * 1024
    );
}
~~~

Requester nhận từng chunk:

~~~java
Flux<FileChunk> chunks =
    requester.route("files.download")
        .data(new DownloadRequest(fileId))
        .retrieveFlux(FileChunk.class);
~~~

Ứng dụng có thể ghi từng chunk ra file hoặc storage theo thứ tự. Không collectList() toàn bộ chunk nếu file có thể lớn, vì thao tác đó giữ tất cả phần tử trong bộ nhớ trước khi tiếp tục.

Một pipeline xử lý tuần tự giúp giới hạn số chunk đang xử lý:

~~~java
Mono<Void> saveDownload(Flux<FileChunk> chunks) {
    return chunks
        .concatMap(chunk ->
            fileStore.append(
                chunk.transferId(),
                chunk.sequence(),
                chunk.content()
            )
        )
        .then();
}
~~~

concatMap chờ xử lý xong một chunk trước khi chuyển sang chunk tiếp theo. Nếu storage hỗ trợ ghi song song theo offset, có thể dùng flatMap với concurrency và prefetch hữu hạn; phải bảo đảm thứ tự hoặc offset được kiểm tra rõ ràng.

## 8. Tải dữ liệu lên bằng request-channel

Khi client gửi nhiều chunk lên server và cần nhận tiến độ hoặc kết quả trong lúc truyền, request-channel là mô hình phù hợp.

Handler Spring có thể nhận Flux chunk và trả về Flux trạng thái:

~~~java
@MessageMapping("files.upload")
public Flux<UploadProgress> upload(Flux<FileChunk> chunks) {
    return uploadService.accept(chunks);
}
~~~

Phía client:

~~~java
Flux<UploadProgress> progress =
    requester.route("files.upload")
        .data(chunksToUpload)
        .retrieveFlux(UploadProgress.class);
~~~

Đầu vào là một luồng chunk; đầu ra là một luồng progress/result. Client và server có thể điều tiết hai hướng dữ liệu theo demand. Khi client hủy subscription, server cần dừng việc ghi hoặc giải phóng tài nguyên tạm theo chính sách của ứng dụng.

Nếu upload chỉ cần một xác nhận cuối cùng, có thể thiết kế response đơn hoặc một message kết quả cuối tùy API mapping. Điều quan trọng là không gom file lớn vào một byte[] hoặc một Payload khổng lồ nếu luồng chunk có thể đáp ứng yêu cầu.

## 9. Giới hạn buffer và backpressure

Backpressure giúp subscriber yêu cầu số phần tử mà nó có khả năng xử lý. Tuy nhiên, một số nguồn ngoài như callback thiết bị, event bus hoặc API không reactive có thể phát dữ liệu mà không chờ demand. Khi đó cần một chiến lược buffer hữu hạn.

Ví dụ dùng buffer có giới hạn:

~~~java
Flux<SensorEvent> bounded =
    externalFeed.events()
        .onBackpressureBuffer(
            256,
            dropped -> log.warn(
                "Buffer full; dropped event {}",
                dropped.sequence()
            ),
            BufferOverflowStrategy.DROP_OLDEST
        );
~~~

Khi buffer đầy, ví dụ trên bỏ phần tử cũ nhất và ghi log. Đây chỉ là chính sách minh họa; nếu mọi event đều quan trọng, không được âm thầm drop. Hãy dùng hàng đợi bền vững hoặc từ chối/đóng stream để bảo toàn dữ liệu.

Các chiến lược thường gặp:

| Chiến lược | Bộ nhớ | Đánh đổi |
|---|---|---|
| Bounded buffer | Có giới hạn | Có chính sách khi đầy |
| Drop latest | Có giới hạn | Bỏ dữ liệu mới |
| Drop oldest | Có giới hạn | Bỏ dữ liệu cũ |
| Latest | Rất nhỏ | Chỉ giữ trạng thái mới nhất |
| Sample/throttle | Giảm số item | Có thể bỏ cập nhật trung gian |
| Persist to disk/broker | Chuyển tải khỏi heap | Tăng độ phức tạp và I/O |

Đừng dùng onBackpressureBuffer() không giới hạn cho nguồn có thể phát liên tục. Nếu consumer chậm trong thời gian dài, hàng đợi có thể chiếm hết heap.

### Giới hạn concurrency và prefetch

flatMap có thể chạy nhiều tác vụ song song. Concurrency và prefetch càng lớn thì số item đang chờ hoặc đang xử lý có thể càng nhiều.

~~~java
Flux<StoredChunk> stored =
    chunks.flatMap(
        chunk -> storage.write(chunk),
        4,
        1
    );
~~~

Trong ví dụ, tối đa bốn tác vụ ghi được xử lý đồng thời và prefetch được đặt ở mức thấp. Chọn giá trị dựa trên năng lực storage và kích thước chunk. Nếu thứ tự bắt buộc, dùng concatMap hoặc ghi theo offset có kiểm tra.

limitRate có thể điều tiết demand upstream theo các đợt nhỏ hơn. Tuy nhiên, nó không thay thế giới hạn buffer ở nguồn ngoài không tuân theo demand.

## 10. Ước lượng bộ nhớ trước khi triển khai

Một cách đơn giản để ước lượng bộ nhớ do buffer là:

\[
M_{\text{queue}} \approx N_{\text{items}} \times S_{\text{average}}
\]

Trong đó:

- N_items là số phần tử tối đa có thể nằm trong hàng đợi.
- S_average là kích thước trung bình của một payload/chunk.

Ví dụ, 256 chunk có kích thước 64 KiB cần khoảng 16 MiB dữ liệu thô cho một hàng đợi:

\[
256 \times 64 \text{ KiB} = 16 \text{ MiB}
\]

Nếu có 20 subscription cùng giữ một hàng đợi như vậy, dữ liệu thô có thể lên tới khoảng 320 MiB, chưa tính overhead của object, ByteBuf, metadata, fragment, allocator và các bản sao.

Ước lượng tổng thể nên xét:

\[
M_{\text{total}} \approx
M_{\text{connections}} +
M_{\text{in-flight}} +
M_{\text{queues}} +
M_{\text{fragment-assembly}} +
M_{\text{application-copies}}
\]

Không phải mọi thành phần đều nằm trên Java heap. Direct ByteBuf có thể sử dụng native memory. Vì vậy, theo dõi cả heap, direct memory, số lượng buffer đang active và số lần allocation/release.

### Đặt giới hạn kích thước ở nhiều tầng

- Giới hạn kích thước data và metadata của mỗi payload.
- Đặt `maxInboundPayloadSize` ở phía nhận và giới hạn tổng kích thước payload được phép tái lắp ghép.
- Giới hạn chunk size ở tầng ứng dụng.
- Giới hạn số chunk đang chờ xử lý.
- Giới hạn số upload/download đồng thời.
- Đặt deadline cho một lần truyền.
- Giới hạn dung lượng file hoặc object theo quyền của người dùng/tenant.

Chỉ giới hạn kích thước frame là chưa đủ nếu một payload lớn có thể được chia thành nhiều fragment.

## 11. Quản lý subscription dài hạn

Một request-stream realtime có thể tồn tại trong nhiều phút hoặc nhiều giờ. Subscription cần kết thúc khi client rời màn hình, thiết bị ngừng theo dõi hoặc ứng dụng shutdown.

Có thể dùng doFinally để quan sát cả complete, error và cancel:

~~~java
Flux<PriceUpdate> watch(String symbol) {
    return priceFeed.watch(symbol)
        .doFinally(signal -> {
            log.debug(
                "Price subscription ended: {} ({})",
                symbol,
                signal
            );
        });
}
~~~

Nếu nguồn ngoài yêu cầu đăng ký và hủy đăng ký rõ ràng, hãy gắn cleanup với vòng đời subscription. Ví dụ dùng Flux.using:

~~~java
Flux<PriceUpdate> watch(String symbol) {
    return Flux.using(
        () -> priceFeed.openSubscription(symbol),
        subscription -> subscription.events(),
        subscription -> subscription.close()
    );
}
~~~

Flux.using tạo tài nguyên khi có subscription và gọi cleanup khi nguồn complete, error hoặc bị cancel. Với cleanup bất đồng bộ, dùng usingWhen và cung cấp các nhánh cleanup phù hợp.

Không dựa vào doOnComplete làm nơi duy nhất để đóng tài nguyên. Khi subscriber hủy, tín hiệu complete không được gửi tới subscriber đã hủy; doFinally hoặc using xử lý cả cancellation.

### Lưu Disposable để chủ động hủy

Nếu một thành phần tự subscribe, nó cần giữ Disposable để dừng subscription khi vòng đời thành phần kết thúc:

~~~java
private Disposable subscription;

void start(String symbol) {
    subscription = priceClient.watch(symbol)
        .subscribe(
            this::updateView,
            error -> log.warn("Price stream failed", error)
        );
}

void stop() {
    if (subscription != null) {
        subscription.dispose();
    }
}
~~~

Trong Spring, có thể gọi dispose trong phương thức shutdown hoặc lifecycle callback của bean. Tốt hơn nữa, nếu có thể, hãy trả Flux cho tầng gọi thay vì subscribe ẩn bên trong service để vòng đời được quản lý ở một nơi.

## 12. Chia sẻ kết nối và tài nguyên giữa nhiều request

Một RSocket connection có thể multiplex nhiều interaction. Ứng dụng thường nên quản lý kết nối theo endpoint và tái sử dụng cho các request, thay vì mở một connection mới cho từng thao tác.

Một connection manager cần:

- Tạo một kết nối cho endpoint theo chính sách của ứng dụng.
- Chia sẻ RSocket/RSocketRequester với các thành phần cần gọi cùng endpoint.
- Theo dõi onClose và xử lý khi connection bị đóng.
- Ngừng phát request mới khi kết nối không khả dụng.
- Đóng connection khi application context shutdown.
- Giới hạn số connection nếu ứng dụng có nhiều endpoint.

Không nên gọi connect() cho mỗi event hoặc mỗi chunk. Việc đó tạo nhiều handshake, socket, keepalive task và buffer transport.

Lưu ý rằng Mono<RSocket> từ `connect(transport)` tạo một kết nối mới cho mỗi subscriber nếu không bật reconnect hoặc resume. Vì vậy, nếu nhiều thành phần cùng subscribe vào một Mono connect, ứng dụng có thể vô tình mở nhiều connection. Hãy để connection manager sở hữu một session đã kết nối, chia sẻ RSocket cho các caller và dispose khi manager shutdown.

Đối với một nguồn hot dùng chung, hãy xác định rõ subscriber mới có nhận sự kiện cũ hay chỉ nhận sự kiện từ thời điểm đăng ký. Nếu dùng replay/cache, đặt giới hạn số phần tử hoặc thời gian lưu. Cache/replay không giới hạn trên stream dài hạn có thể làm bộ nhớ tăng mãi.

Không chia sẻ một Payload hoặc ByteBuf mutable giữa các subscriber. Chia sẻ object bất biến đã decode thường an toàn và dễ quản lý hơn. Nếu cần chia sẻ buffer zero-copy, phải thiết kế ownership cho từng subscriber và bảo đảm mỗi retain có release tương ứng.

## 13. Cleanup khi upload/download bị hủy hoặc lỗi

Truyền dữ liệu lớn có thể bị gián đoạn bởi timeout, disconnect hoặc người dùng hủy. Ứng dụng cần định nghĩa trạng thái của dữ liệu tạm:

- Chunk đã ghi có được giữ lại để resume không?
- File tạm có bị xóa khi transfer bị cancel không?
- Có cần ghi metadata trạng thái để tiếp tục sau reconnect không?
- Làm sao phát hiện chunk trùng lặp hoặc sai thứ tự?
- Ai chịu trách nhiệm đóng file handle và giải phóng buffer?

Ví dụ quản lý file tạm bằng usingWhen:

~~~java
Mono<UploadReceipt> receiveUpload(Flux<FileChunk> chunks) {
    return Mono.usingWhen(
        uploadStore.createTemporaryUpload(),
        upload -> chunks
            .concatMap(upload::append)
            .then(upload.commit()),
        upload -> upload.close(),
        (upload, error) -> upload.abort(error),
        upload -> upload.abort(
            new CancellationException("Upload cancelled")
        )
    );
}
~~~

Ví dụ minh họa cleanup khi hoàn tất, lỗi hoặc hủy. API uploadStore là abstraction của ứng dụng; implementation phải bảo đảm abort/close an toàn khi được gọi đúng một lần theo lifecycle.

Nếu nghiệp vụ cần resume, không xóa dữ liệu tạm khi cancel ngay lập tức. Thay vào đó, lưu trạng thái transfer và thời điểm hết hạn, sau đó dọn các upload bỏ dở bằng một job có giới hạn thời gian.

## 14. Phân biệt ByteBuf với Spring DataBuffer

Khi dùng RSocket Java trực tiếp, ứng dụng thường làm việc với Payload và Netty ByteBuf. Trong một số pipeline Spring, dữ liệu có thể được biểu diễn bằng DataBuffer.

DataBuffer cũng có thể dựa trên Netty ByteBuf và có thể yêu cầu release tùy loại implementation. Khi sử dụng Spring Core, hãy dùng các API như DataBufferUtils.release hoặc DataBufferUtils.releaseConsumer theo đúng ownership contract của pipeline.

Không giả định mọi byte[] hoặc DTO đều cần release. Chỉ các kiểu tài nguyên có reference counting hoặc được tài liệu yêu cầu quản lý mới cần thao tác này.

Quy tắc thực tế:

- ByteBuf/Payload ở tầng RSocket Java: theo dõi retain/release.
- DataBuffer trong Spring: theo dõi ownership và dùng DataBufferUtils khi cần.
- byte[] hoặc String đã copy: quản lý theo garbage collection thông thường.
- DTO không giữ tham chiếu tới buffer gốc: không release DTO.

## 15. Dấu hiệu rò rỉ và cách quan sát

Các triệu chứng thường gặp:

| Triệu chứng | Nguyên nhân có thể |
|---|---|
| Direct memory tăng liên tục | ByteBuf/Payload không được release |
| IllegalReferenceCountException | Truy cập buffer sau release hoặc release quá nhiều |
| Heap tăng theo số subscription | Cache/replay/buffer không giới hạn hoặc giữ subscription cũ |
| Nhiều socket sau một thời gian | Tạo connection lặp lại mà không dispose |
| CPU tăng khi payload lớn | Copy/serialize nhiều lần hoặc fragmentation quá dày |
| Consumer chậm làm memory tăng | Queue lớn hoặc không giới hạn |
| File handle tăng | Upload/download không cleanup khi cancel/error |
| Event vẫn được xử lý sau khi client rời đi | Subscription không được hủy hoặc nguồn không phản ứng với cancel |

Có thể bật leak detection của Netty trong môi trường kiểm thử để phát hiện buffer bị bỏ quên. Mức chi tiết cao có thể tạo overhead đáng kể, vì vậy không nên bật mức nhạy nhất liên tục trong production nếu chưa đánh giá tác động.

Các metric nên theo dõi:

- Heap used và direct memory used.
- Số ByteBuf allocation/release nếu instrumentation hỗ trợ.
- Số connection và connection lifetime.
- Số interaction/subscription đang hoạt động.
- Số upload/download đồng thời.
- Queue depth, buffer overflow và số chunk bị drop.
- Payload size và thời gian truyền.
- Số subscription bị cancel và cleanup thất bại.

## 16. Kiểm thử ownership và vòng đời

Kiểm thử phải xác nhận cả kết quả nghiệp vụ lẫn việc tài nguyên được giải phóng.

Một số ca kiểm thử quan trọng:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Decode thành công với ZERO_COPY | Payload được release sau khi decode |
| Decoder ném exception với ZERO_COPY | finally vẫn release Payload |
| Dùng PayloadDecoder.DEFAULT | Data/metadata là bản copy; không cần release thủ công frame buffer gốc |
| Stream phát nhiều Payload với ZERO_COPY | Mỗi Payload được release đúng một lần |
| Buffer được giữ qua async boundary | retain/copy và release đúng ownership |
| Client hủy stream | Nguồn dừng và cleanup được gọi |
| Upload lỗi giữa chừng | Tài nguyên tạm được abort hoặc giữ theo chính sách resume |
| Payload vượt maxInboundPayloadSize | Reassembly bị từ chối theo giới hạn đã cấu hình |
| Consumer chậm | Queue không vượt giới hạn đã đặt |
| Nhiều subscriber | Không chia sẻ buffer mutable sai ownership |
| Application shutdown | Subscription và connection được dispose |

Có thể dùng StepVerifier để kiểm tra cancellation:

~~~java
@Test
void cancellingStreamTriggersCleanup() {
    AtomicBoolean cleaned = new AtomicBoolean();

    Flux<Long> stream = Flux.interval(Duration.ofMillis(10))
        .doFinally(signal -> cleaned.set(true));

    StepVerifier.create(stream)
        .thenAwait(Duration.ofMillis(30))
        .thenCancel()
        .verify();

    assertThat(cleaned).isTrue();
}
~~~

Để kiểm tra reference count ở unit test, tạo ByteBuf/Payload trong test, ghi nhận refCnt trước và sau khi chạy logic, rồi xác nhận buffer đã được release theo ownership contract. Tránh chỉ kiểm tra số refCnt trong code production vì implementation có thể retain nội bộ trong lúc gửi.

## 17. Quy trình thiết kế tài nguyên cho dữ liệu lớn

Khi xây dựng một tính năng upload, download hoặc realtime stream, hãy thực hiện theo thứ tự:

1. Xác định connection và interaction nào được chia sẻ, interaction nào có vòng đời riêng.
2. Chọn request-stream hoặc request-channel nếu dữ liệu cần truyền theo chunk.
3. Đặt kích thước chunk và giới hạn tổng payload.
4. Xác định owner của mỗi Payload, ByteBuf hoặc DataBuffer.
5. Decode/copy dữ liệu trước khi release nếu object cần sống lâu hơn payload.
6. Dùng buffer hữu hạn, giới hạn concurrency và prefetch.
7. Gắn cleanup với complete, error, cancel và application shutdown.
8. Định nghĩa chính sách resume, duplicate chunk và dữ liệu tạm.
9. Đo heap, direct memory, queue depth, connection và subscription.
10. Kiểm thử tải lớn, consumer chậm, disconnect và cancellation.

Quản lý tài nguyên tốt bắt đầu từ việc xác định ownership và vòng đời. Khi payload được xử lý theo chunk có kích thước giới hạn, buffer được release đúng lúc và subscription được hủy khi không còn cần thiết, một kết nối RSocket lâu dài có thể phục vụ nhiều interaction mà không làm bộ nhớ tăng không kiểm soát.

## Ghi nhớ

- Connection, RSocket session, interaction, subscription và Payload có vòng đời khác nhau.
- Mono<RSocket> từ connect(transport) tạo kết nối mới cho mỗi subscriber nếu không bật reconnect hoặc resume; connection manager cần quản lý và chia sẻ session có chủ đích.
- Với PayloadDecoder.ZERO_COPY, Payload/ByteBuf dùng retained slice; mỗi retain cần một release tương ứng.
- Với ZERO_COPY, giải phóng Payload trong finally sau khi decode, kể cả khi decoder lỗi; DEFAULT tạo bản copy nên không cần theo dõi frame buffer gốc.
- slice/duplicate chia sẻ vùng nhớ; copy tạo vùng dữ liệu độc lập.
- Fragmentation chia một payload thành frame; chunking chia dữ liệu thành nhiều message ở tầng ứng dụng.
- Dữ liệu lớn nên được truyền theo chunk và xử lý tuần tự hoặc với concurrency hữu hạn.
- Tránh buffer, cache, replay và queue không giới hạn.
- Cleanup phải xử lý complete, error, cancel và shutdown.
- Theo dõi cả heap và direct memory, cùng số connection, subscription và queue depth.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [RSocket Java](https://github.com/rsocket/rsocket-java)
- [RSocket Java — Payload](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/Payload.html)
- [RSocket Java — RSocketConnector](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/core/RSocketConnector.html)
- [Netty — Reference-counted objects](https://netty.io/wiki/reference-counted-objects.html)
- [Netty — ByteBuf API](https://netty.io/4.1/api/io/netty/buffer/ByteBuf.html)
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)

