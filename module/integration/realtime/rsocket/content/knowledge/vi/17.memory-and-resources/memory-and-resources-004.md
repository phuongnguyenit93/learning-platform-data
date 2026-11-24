# PayloadDecoder và đánh đổi giữa sao chép với zero-copy

Khi RSocket Java nhận một frame, thư viện phải chuyển phần data và metadata của frame thành một đối tượng **Payload** để ứng dụng đọc hoặc xử lý. Bước này có thể tạo bản sao độc lập của dữ liệu, hoặc tạo các lát bộ đệm dùng chung vùng nhớ với frame đầu vào. Hai cách đó được lựa chọn qua **PayloadDecoder**.

Mặc định, RSocket Java dùng **PayloadDecoder.DEFAULT**: data và metadata được sao chép ra các vùng nhớ độc lập, giúp vòng đời dữ liệu dễ quản lý. **PayloadDecoder.ZERO_COPY** tạo retained slice trên Netty **ByteBuf**, giảm thao tác sao chép nhưng yêu cầu ứng dụng theo dõi quyền sở hữu và gọi **release()** đúng lúc.

Zero-copy có thể giảm allocation, băng thông bộ nhớ và độ trễ ở đường nhận dữ liệu. Đổi lại, lỗi quản lý reference count có thể gây memory leak hoặc truy cập bộ nhớ đã được giải phóng. Vì vậy, quyết định dùng decoder nào cần dựa trên workload, khả năng kiểm soát vòng đời Payload và kết quả đo thực tế.

## 1. PayloadDecoder làm nhiệm vụ gì?

RSocket truyền các frame nhị phân. Khi nhận frame, implementation cần tách phần data và metadata, sau đó tạo đối tượng Payload để handler hoặc requester sử dụng.

**PayloadDecoder** nằm ở ranh giới giữa frame nhận được và Payload của ứng dụng. Nó quyết định cách data/metadata được tạo từ ByteBuf chứa frame:

- **DEFAULT:** sao chép data và metadata thành các vùng dữ liệu độc lập với ByteBuf của frame.
- **ZERO_COPY:** tạo retained slice trỏ vào vùng nhớ của ByteBuf ban đầu, tránh sao chép nội dung data/metadata ở bước giải mã Payload.

Cần hiểu đúng phạm vi: cấu hình PayloadDecoder điều khiển cách tạo **Payload đầu vào** từ frame nhận được. Nó không bật một chế độ zero-copy xuyên suốt mọi tầng của ứng dụng, cũng không bảo đảm serializer, decoder JSON, TLS, transport hay thư viện downstream sẽ không tạo bản sao.

Một đường đi đơn giản:

~~~mermaid
flowchart TD
    A[ByteBuf chứa RSocket frame] --> B[PayloadDecoder]
    B --> C{Chế độ decoder}
    C -->|DEFAULT| D[Sao chép data và metadata]
    C -->|ZERO_COPY| E[Retained slice dùng chung vùng nhớ]
    D --> F[Payload cho handler]
    E --> F
    F --> G[Ứng dụng đọc, decode hoặc xử lý]
    G --> H[Giải phóng theo quyền sở hữu]
~~~

Mỗi phía RSocket cấu hình decoder cho dữ liệu **nó nhận**. Nếu client và server đều muốn dùng zero-copy khi nhận Payload, cả hai phía phải được cấu hình riêng.

## 2. DEFAULT: sao chép để đơn giản hóa vòng đời

Với PayloadDecoder.DEFAULT, RSocket Java tạo bản sao độc lập cho data và metadata từ ByteBuf của frame. Sau khi Payload được tạo, nó không còn phụ thuộc vào vòng đời của vùng nhớ frame nhận ban đầu.

Ưu điểm chính là quyền sở hữu rõ ràng hơn:

- Ứng dụng có thể đọc Payload mà không cần giữ ByteBuf frame gốc còn sống.
- Dữ liệu của Payload không bị vô hiệu chỉ vì buffer frame đầu vào được giải phóng.
- Không cần theo dõi và gọi release() thủ công cho Payload chỉ vì decoder đang dùng chế độ DEFAULT.
- Việc chuyển dữ liệu qua các bước xử lý bất đồng bộ dễ quản lý hơn.

Chi phí là việc sao chép data và metadata. Với thông lượng lớn hoặc payload nhị phân lớn, chi phí này có thể làm tăng allocation, áp lực GC, băng thông bộ nhớ và độ trễ.

DEFAULT thường là điểm khởi đầu hợp lý cho ứng dụng mới, payload nhỏ, traffic vừa phải hoặc pipeline có nhiều bước bất đồng bộ mà quyền sở hữu buffer khó kiểm soát.

## 3. ZERO_COPY: dùng retained slice của ByteBuf

Với PayloadDecoder.ZERO_COPY, data và metadata được biểu diễn bằng retained slice của ByteBuf chứa frame. Slice chia sẻ vùng nhớ nội dung với buffer gốc; decoder không cần sao chép toàn bộ byte của từng phần payload.

Lợi ích có thể thấy rõ khi:

- Payload nhị phân lớn được xử lý trực tiếp trên ByteBuf.
- Ứng dụng chuyển tiếp dữ liệu mà không cần chuyển qua String hoặc byte array.
- Tần suất nhận Payload cao và allocation/copy trở thành nút thắt.
- Pipeline có thể quản lý rõ thời điểm Payload được tiêu thụ xong.

Nhưng vùng nhớ dùng chung phải còn sống trong suốt thời gian slice được sử dụng. Vì thế RSocket Java tạo **retained slice**: thao tác này giữ thêm một reference tới vùng nhớ. Khi ứng dụng hoàn tất việc sử dụng Payload, nó phải release reference mà nó sở hữu.

Nếu quên release, vùng nhớ có thể không được trả về allocator hoặc pool dù ứng dụng không còn cần dữ liệu. Nếu release quá sớm, thành phần khác có thể truy cập ByteBuf đã hết reference count và gặp IllegalReferenceCountException.

ZERO_COPY giảm copy ở bước tạo Payload, nhưng không loại bỏ mọi allocation. Đối tượng Payload, wrapper, cấu trúc DTO và các bước giải mã vẫn có thể tạo bộ nhớ mới.

## 4. Reference counting của Netty ByteBuf

Netty dùng reference counting để quản lý vòng đời của một số đối tượng, đặc biệt là ByteBuf. Cách hoạt động cơ bản:

- Một buffer mới thường bắt đầu với reference count bằng 1.
- **retain()** tăng reference count.
- **release()** giảm reference count.
- Khi reference count về 0, vùng nhớ được giải phóng hoặc trả lại allocator/pool để tái sử dụng.
- Truy cập buffer sau khi reference count về 0 có thể gây IllegalReferenceCountException.

Ví dụ minh họa:

~~~java
ByteBuf buffer = allocator.directBuffer();
buffer.writeBytes(input);

buffer.retain();  // refCnt: 2

buffer.release(); // refCnt: 1
buffer.release(); // refCnt: 0, vùng nhớ được trả lại
~~~

Mỗi lần retain tạo thêm một quyền giữ vùng nhớ. Mỗi quyền giữ phải được release đúng một lần. Nếu hai thành phần cùng cần giữ dữ liệu, chúng phải có hai reference hợp lệ; một thành phần không được release thay cho quyền sở hữu của thành phần khác.

### Copy, slice và retainedSlice khác nhau thế nào?

| Thao tác | Vùng nhớ | Reference count | Trách nhiệm |
|---|---|---|---|
| copy() | Tạo vùng nhớ mới, nội dung độc lập | Buffer mới có vòng đời riêng | Release bản copy khi dùng xong |
| slice() | Chia sẻ vùng nhớ với buffer gốc | Không tăng reference count | Chỉ dùng khi buffer gốc chắc chắn còn sống |
| retainedSlice() | Chia sẻ vùng nhớ với buffer gốc | Tăng reference count | Release slice sau khi dùng xong |
| retain() | Không tạo bản sao nội dung | Tăng reference count của cùng buffer | Release reference bổ sung |

Sự khác biệt này rất quan trọng. Một slice thông thường không tự giữ vùng nhớ sống lâu hơn buffer gốc. Nếu cần chuyển slice sang một thành phần khác hoặc sử dụng sau khi chủ sở hữu hiện tại kết thúc, phải có một reference được giữ hợp lệ, chẳng hạn bằng retainedSlice() hoặc retain().

Ví dụ:

~~~java
ByteBuf source = allocator.directBuffer();
source.writeBytes(input);

ByteBuf independent = source.copy();
ByteBuf shared = source.retainedSlice();

try {
    process(independent);
    process(shared);
} finally {
    independent.release();
    shared.release();
    source.release();
}
~~~

Bản copy có dữ liệu độc lập. Slice dùng chung nội dung với source nhưng đã giữ thêm một reference. Ví dụ chỉ minh họa vòng đời buffer; trong code thực tế, hãy xác định rõ thành phần nào nhận quyền sở hữu từng reference.

Ví dụ giả định process() đọc buffer ngay trong lời gọi. Nếu process() trả về publisher và chỉ đọc buffer sau đó, phải giữ reference đến khi publisher hoàn tất như ví dụ xử lý bất đồng bộ ở phần sau.

## 5. PayloadDecoder.DEFAULT và ZERO_COPY khác nhau

| Tiêu chí | DEFAULT | ZERO_COPY |
|---|---|---|
| Data/metadata | Bản sao độc lập | Retained slice của ByteBuf |
| Copy byte ở bước tạo Payload | Có | Tránh copy ở bước này |
| Phụ thuộc buffer frame gốc | Không phụ thuộc nội dung sau khi copy | Có chia sẻ vùng nhớ |
| Theo dõi reference count | Không cần quản lý thủ công chỉ vì decoder | Phải release Payload khi hoàn tất |
| Độ phức tạp vòng đời | Thấp | Cao hơn |
| Rủi ro quên release | Thấp ở bước decoder | Có thể gây leak |
| Rủi ro release sớm | Thấp hơn | Có thể gây lỗi truy cập buffer |
| Trường hợp phù hợp | Payload nhỏ, xử lý DTO thông thường | Payload lớn, binary và pipeline kiểm soát ownership tốt |

Không có chế độ nào luôn nhanh hơn trong mọi trường hợp. Với payload nhỏ, chi phí retain/release và quản lý vòng đời có thể làm lợi ích zero-copy không đáng kể. Với payload lớn và thông lượng cao, tránh sao chép có thể đem lại cải thiện rõ hơn.

## 6. Cấu hình PayloadDecoder ở RSocket Java

Ở tầng RSocket core, cấu hình decoder được thực hiện trên RSocketServer và RSocketConnector.

### Cấu hình server

~~~java
RSocketServer server = RSocketServer
    .create(acceptor)
    .payloadDecoder(PayloadDecoder.ZERO_COPY);

Mono<CloseableChannel> bound =
    server.bind(TcpServerTransport.create("localhost", 7000));
~~~

### Cấu hình client

~~~java
Mono<RSocket> client = RSocketConnector
    .create()
    .payloadDecoder(PayloadDecoder.ZERO_COPY)
    .connect(TcpClientTransport.create("localhost", 7000));
~~~

Nếu muốn dùng mặc định, có thể bỏ lời gọi payloadDecoder() hoặc cấu hình tường minh:

~~~java
RSocketConnector connector = RSocketConnector
    .create()
    .payloadDecoder(PayloadDecoder.DEFAULT);
~~~

Decoder được cấu hình độc lập trên mỗi endpoint vì nó áp dụng cho Payload được endpoint đó nhận. Ví dụ, client đặt ZERO_COPY sẽ quản lý Payload nhận từ server; cấu hình này không tự thay đổi cách server decode Payload nhận từ client.

Tên API và cách khởi chạy transport có thể khác giữa các phiên bản RSocket Java. Hãy đối chiếu Javadoc đúng phiên bản đang dùng. Khi ứng dụng chạy qua Spring Boot auto-configuration, việc tùy chỉnh decoder có thể cần cấu hình connector/server bên dưới tùy phiên bản Spring và cách khởi tạo RSocket.

## 7. Đọc Payload rồi release đúng lúc

Khi dùng ZERO_COPY và handler ở tầng RSocket core trực tiếp nhận một Payload thuộc quyền sở hữu của nó, hãy release sau lần đọc cuối cùng. Với DEFAULT, RSocket Java tạo bản sao độc lập và tài liệu decoder cho biết ứng dụng không cần theo dõi/release thủ công chỉ vì chế độ decoder này.

Ví dụ chuyển data sang String độc lập trước khi gọi service bất đồng bộ:

~~~java
// Ví dụ cho ZERO_COPY trong handler trực tiếp sở hữu Payload.
Mono<Order> handle(Payload payload) {
    final String orderId;

    try {
        orderId = payload.getDataUtf8();
    } finally {
        payload.release();
    }

    // String đã độc lập với ByteBuf của Payload.
    return orderService.find(orderId);
}
~~~

getDataUtf8() tạo String để ứng dụng sử dụng. Sau khi String đã được tạo, service không cần giữ Payload hoặc ByteBuf gốc nữa. Vì vậy có thể release Payload trước khi bắt đầu phần xử lý bất đồng bộ.

Với stream Payload trong chế độ ZERO_COPY, phải release từng phần tử sau khi đọc:

~~~java
Flux<String> values = socket
    .requestStream(requestPayload)
    .map(payload -> {
        try {
            return payload.getDataUtf8();
        } finally {
            payload.release();
        }
    });
~~~

Nếu bỏ qua release trong ZERO_COPY, mỗi phần tử có thể giữ lại vùng nhớ pooled. Stream càng dài thì lượng bộ nhớ bị giữ càng tăng.

Các ví dụ trên áp dụng cho code tầng thấp nơi ứng dụng sở hữu Payload nhận được. Nếu handler Spring nhận DTO đã decode qua @MessageMapping, framework quản lý việc chuyển đổi payload; không gọi release() lên DTO hoặc tự giải phóng buffer mà ứng dụng không sở hữu.

## 8. Khi cần giữ ByteBuf qua xử lý bất đồng bộ

Đôi khi service downstream cần đọc trực tiếp ByteBuf sau khi handler đã trả về publisher. Khi đó, cần giữ thêm reference trước khi quyền sở hữu ban đầu kết thúc và release reference bổ sung khi publisher hoàn tất, lỗi hoặc bị hủy.

Ví dụ dưới đây giả định ZERO_COPY, handler sở hữu Payload đầu vào và dùng Mono.using để gắn vòng đời reference bổ sung với publisher:

~~~java
Mono<Result> process(Payload payload) {
    return Mono.using(
        () -> {
            ByteBuf data = payload.sliceData().retain();
            payload.release();
            return data;
        },
        data -> downstreamService.process(data),
        ByteBuf::release
    );
}
~~~

Ở đây:

1. Khi subscriber đăng ký, code tạo slice và retain để giữ vùng nhớ cho tác vụ downstream.
2. Reference của Payload ban đầu được release sau khi đã giữ reference cho slice.
3. downstreamService xử lý ByteBuf trong thời gian publisher còn hoạt động.
4. Khi publisher hoàn tất, phát lỗi hoặc bị hủy, cleanup của Mono.using release reference của ByteBuf.

Ví dụ giả định handler đang sở hữu Payload đầu vào và downstreamService chỉ sử dụng ByteBuf trong thời gian publisher được subscribe. Nếu downstream giữ ByteBuf lâu hơn publisher hoặc chuyển nó sang một tác vụ khác, cần chuyển giao hoặc retain thêm reference cho tác vụ đó và release ở nơi sử dụng cuối cùng.

Không trả ByteBuf ra ngoài rồi release ngay trong finally nếu người nhận còn cần đọc dữ liệu. Cũng không retain nhiều lần mà không ghi lại nơi chịu trách nhiệm release từng reference.

## 9. Các lỗi vòng đời thường gặp

### Quên release

Ứng dụng đọc data rồi giữ Payload trong cache hoặc bỏ quên sau khi xử lý. Với ZERO_COPY, reference count không về 0 và bộ nhớ pooled bị giữ lại.

**Cách tránh:** release tại điểm tiêu thụ cuối cùng; dùng try/finally cho thao tác đồng bộ hoặc doFinally/using cho publisher bất đồng bộ.

### Release quá sớm

Handler release Payload rồi mới đưa ByteBuf slice vào một publisher khác. Publisher đọc dữ liệu sau khi buffer đã được trả về pool.

**Cách tránh:** retain reference trước khi chuyển giao, hoặc copy dữ liệu sang vùng nhớ độc lập nếu thời gian sử dụng không thể kiểm soát.

### Double release

Hai tầng cùng nghĩ mình sở hữu một reference và cùng release. Reference count có thể xuống dưới 0 hoặc thao tác tiếp theo gặp IllegalReferenceCountException.

**Cách tránh:** ghi rõ quyền sở hữu khi truyền Payload/ByteBuf qua method; mỗi reference chỉ có một nơi chịu trách nhiệm release.

### Giữ slice nhỏ nhưng pin buffer lớn

Một slice nhỏ có thể vẫn giữ reference tới vùng nhớ nền lớn hơn. Nếu ứng dụng lưu slice trong cache lâu dài, bộ nhớ nền có thể không được trả lại dù phần dữ liệu cần thiết rất nhỏ.

**Cách tránh:** nếu cần giữ một phần nhỏ lâu dài, cân nhắc copy phần đó sang vùng nhớ độc lập rồi release slice gốc.

### Bỏ phần tử mà không cleanup

Một pipeline có thể loại bỏ, lọc hoặc hủy phần tử Payload trước khi code xử lý cuối cùng được gọi. Nếu các Payload đó là reference-counted, cần đảm bảo phần tử bị bỏ cũng được release. Khi dùng operator có discard support, cân nhắc hook cleanup tương ứng và kiểm thử đường đi cancellation/discard.

### Chuyển Payload sang thread khác mà không retain

Một thread nhận Payload, đưa vào executor rồi trả quyền sở hữu hoặc kết thúc xử lý trước khi thread khác đọc xong. Buffer có thể bị release trước khi tác vụ mới sử dụng.

**Cách tránh:** retain khi chuyển quyền sử dụng sang tác vụ bất đồng bộ khác, quy định rõ ai release và release trong finally của tác vụ cuối.

## 10. Zero-copy không có nghĩa là không tạo object

Ngay cả khi PayloadDecoder.ZERO_COPY tránh copy byte của data và metadata, ứng dụng vẫn có thể tạo nhiều allocation:

- JSON decoder tạo String, number, collection và DTO.
- Gọi getDataUtf8() tạo String từ byte.
- Mapping DTO có thể tạo object graph mới.
- Nén/giải nén, mã hóa, giải mã hoặc chuyển định dạng có thể tạo buffer khác.
- Các operator reactive, queue và scheduler vẫn có thể cấp phát object quản lý.

Ví dụ, nếu ứng dụng luôn làm:

~~~java
String json = payload.getDataUtf8();
OrderRequest request = objectMapper.readValue(json, OrderRequest.class);
~~~

thì bước chuyển ByteBuf sang String và deserialize JSON vẫn tạo dữ liệu/object mới. ZERO_COPY chỉ tránh một số bản sao ở ranh giới frame-to-Payload; nó không loại bỏ chi phí của các bước chuyển đổi sau đó.

Muốn tận dụng zero-copy, cần xem toàn bộ đường đi dữ liệu. Nếu ứng dụng phải chuyển payload thành String ngay lập tức thì lợi ích có thể nhỏ hơn so với xử lý trực tiếp ByteBuf hoặc chuyển tiếp payload mà không decode lại.

## 11. Chọn chế độ theo loại workload

| Workload | Lựa chọn ban đầu | Lý do |
|---|---|---|
| JSON nhỏ, request-response thông thường | DEFAULT | Đơn giản, ít rủi ro vòng đời |
| Dashboard với DTO nhỏ và nhiều route | DEFAULT, đo trước | Tối ưu ownership thường quan trọng hơn vài bản copy nhỏ |
| Truyền binary lớn | Benchmark ZERO_COPY | Có thể tránh copy một lượng byte đáng kể |
| Proxy chuyển tiếp payload | Benchmark ZERO_COPY | Có thể giữ dữ liệu dạng buffer thay vì chuyển qua object |
| Pipeline có nhiều queue và async handoff | DEFAULT nếu chưa kiểm soát ownership | Dễ tránh leak khi payload bị giữ lâu |
| Xử lý ByteBuf trực tiếp, ownership rõ | ZERO_COPY | Có thể giảm allocation và memory bandwidth |

Một quy trình thực tế:

1. Bắt đầu với DEFAULT.
2. Đo throughput, latency p95/p99, allocation rate, GC và direct memory.
3. Xác định copy data/metadata có thực sự là nút thắt hay không.
4. Thử ZERO_COPY trong môi trường tải đại diện.
5. Kiểm tra reference count, cancellation, error và discard path.
6. So sánh kết quả trước/sau và chỉ giữ cấu hình mới khi lợi ích đo được đủ lớn.

Không nên chọn zero-copy chỉ vì tên gọi nghe nhanh hơn. Một pipeline có thể chạy nhanh hơn ở microbenchmark nhưng gặp memory leak khi có nhiều stream dài hạn hoặc khi consumer hủy giữa chừng.

## 12. Quan sát memory leak và kiểm thử

Khi dùng ZERO_COPY, cần theo dõi cả heap và bộ nhớ ngoài heap/direct memory. Heap có thể ổn định trong khi pooled ByteBuf vẫn bị giữ lại do reference count không được trả về 0.

Các tín hiệu nên theo dõi:

- Direct memory và số buffer đang được allocator giữ.
- Số Payload được nhận, xử lý và release.
- Allocation rate và thời gian GC.
- Số IllegalReferenceCountException.
- Số stream bị cancel và số phần tử bị discard.
- Latency xử lý Payload và kích thước data/metadata.
- Tăng bộ nhớ theo thời gian khi chạy stream dài hạn.

### Kiểm thử xử lý thành công và lỗi

Một test cho code chuyển Payload thành String nên xác nhận Payload được release dù việc đọc dữ liệu thành công hay phát lỗi. Có thể dùng ByteBufPayload hoặc Payload test phù hợp với phiên bản RSocket Java và kiểm tra reference count sau khi hoàn tất.

### Kiểm thử cancellation

Tạo publisher giữ một Payload zero-copy, sau đó hủy subscription giữa chừng. Xác nhận cleanup được thực thi và buffer không còn reference bị bỏ quên.

### Bật leak detection trong môi trường kiểm thử

Netty có ResourceLeakDetector để phát hiện một số trường hợp reference-counted object không được release. Có thể tăng mức phát hiện trong test hoặc staging; mức phát hiện cao hơn tạo overhead nên không nên bật chế độ nặng nhất một cách tùy tiện trên production.

Leak detector hỗ trợ tìm dấu vết nhưng không thay thế quy ước ownership rõ ràng. Hãy kiểm thử cả success, error, timeout, cancellation và discard vì leak thường xuất hiện ở nhánh ít được chạy.

## 13. Lưu ý khi tích hợp với Spring Boot

Trong Spring Messaging, handler thường nhận DTO hoặc kiểu dữ liệu đã được message converter giải mã. Ứng dụng không trực tiếp thao tác Payload/ByteBuf trong nhiều route thông thường; vì vậy không cần tự release DTO sau khi xử lý.

PayloadDecoder thuộc tầng RSocket core. Nếu muốn cấu hình ZERO_COPY trong ứng dụng Spring Boot, cần xác định phiên bản Spring Framework/Spring Boot và cách ứng dụng tạo RSocket server/client. Cấu hình decoder phải được áp dụng vào RSocketServer hoặc RSocketConnector tương ứng. Không nên giả định một thuộc tính cấu hình chung tồn tại trong mọi phiên bản Spring Boot.

Nếu dùng custom RSocket handler hoặc trực tiếp nhận Payload, hãy kiểm tra hợp đồng quyền sở hữu của API đang sử dụng. Khi chuyển Payload qua Reactor pipeline, cần xác định rõ thời điểm handler kết thúc sử dụng và thành phần nào chịu trách nhiệm release.

## 14. Checklist trước khi bật ZERO_COPY

- Đã xác nhận đúng phiên bản RSocket Java và API PayloadDecoder.
- Đã đo thấy copy data/metadata là chi phí đáng kể.
- Đã hiểu PayloadDecoder chỉ ảnh hưởng cách tạo Payload đầu vào.
- Đã xác định rõ ai sở hữu mỗi Payload và ByteBuf.
- Mỗi retain đều có release tương ứng.
- Không dùng slice không-retain vượt vòng đời buffer gốc.
- Payload được release trên success, error và cancellation.
- Các phần tử bị discard hoặc bỏ khỏi queue cũng được cleanup.
- Không giữ slice nhỏ trong cache nếu nó pin buffer lớn.
- Đã kiểm thử stream dài hạn và tải đồng thời.
- Đã theo dõi direct memory và bật leak detection trong môi trường kiểm thử.

## 15. Kết luận

PayloadDecoder.DEFAULT sao chép data và metadata thành vùng nhớ độc lập, đổi thêm chi phí copy để có vòng đời đơn giản. PayloadDecoder.ZERO_COPY tạo retained slice của ByteBuf, giúp tránh copy ở bước tạo Payload nhưng yêu cầu quản lý reference count và release đúng thời điểm.

Zero-copy phù hợp khi ứng dụng xử lý payload lớn hoặc thông lượng cao, có thể giữ quyền sở hữu buffer rõ ràng và đã đo được lợi ích. Với pipeline DTO thông thường hoặc nhiều bước bất đồng bộ khó kiểm soát, DEFAULT thường là lựa chọn an toàn hơn để bắt đầu.

Trong RSocket Java, hãy tối ưu dựa trên số liệu thực tế: đo allocation, latency và direct memory; kiểm tra success/error/cancellation; và chỉ bật ZERO_COPY khi vòng đời Payload được quản lý đầy đủ. Giảm một lần sao chép không có ý nghĩa nếu đổi lại là memory leak hoặc lỗi truy cập buffer đã giải phóng.

Tài liệu tham khảo:
- [RSocketConnector Javadoc – PayloadDecoder](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocketServer Javadoc – PayloadDecoder](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [Netty – Reference-counted objects](https://netty.io/wiki/reference-counted-objects.html)
- [Netty ByteBuf API – copy, slice và retainedSlice](https://netty.io/4.1/api/io/netty/buffer/ByteBuf.html)

