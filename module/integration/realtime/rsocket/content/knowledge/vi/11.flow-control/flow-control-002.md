# Phân biệt nhu cầu theo số phần tử với giới hạn băng thông theo byte

Trong giao tiếp reactive, một subscriber yêu cầu dữ liệu bằng số phần tử mà nó có thể xử lý. RSocket dùng cơ chế flow control này để điều tiết các stream: bên nhận cấp quyền cho một số payload, bên gửi chỉ phát trong phạm vi demand đã được cấp. Tuy nhiên, một payload có thể chỉ vài byte hoặc lớn hàng megabyte. Vì vậy, giới hạn 100 phần tử không đồng nghĩa với giới hạn 100 KB, và việc điều tiết demand không tự đặt ra một mức băng thông theo byte mỗi giây.

Thiết kế realtime cần tách hai câu hỏi: **có thể gửi bao nhiêu phần tử đang chờ xử lý** và **có thể truyền bao nhiêu byte trong một khoảng thời gian**. Câu hỏi đầu thuộc flow control theo phần tử của Reactive Streams/RSocket. Câu hỏi thứ hai cần đo kích thước dữ liệu đã mã hóa và áp dụng chính sách giới hạn byte ở tầng phù hợp. Bài này giải thích sự khác nhau, cách chúng phối hợp và cách xây dựng một pipeline Java/Spring RSocket có kiểm soát.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích demand của Reactive Streams là số phần tử, không phải số byte.
- Nhận biết vai trò của REQUEST_N trong request-stream và request-channel.
- Phân biệt flow control, giới hạn kích thước message, giới hạn throughput và điều tiết concurrency.
- Ước lượng hoặc đo kích thước payload sau serialize, metadata và overhead truyền tải.
- Thiết kế giới hạn băng thông bằng ngân sách byte hoặc token bucket.
- Kết hợp điều tiết theo phần tử với điều tiết theo byte mà vẫn giữ backpressure và cancellation.
- Đo lường throughput, queue và kích thước message trong hệ thống RSocket.

## 1. Demand trong Reactive Streams được tính theo phần tử

Reactive Streams định nghĩa một subscription giữa Publisher và Subscriber. Subscriber yêu cầu thêm dữ liệu bằng thao tác tương đương **request(n)**, trong đó n là số phần tử mà subscriber sẵn sàng nhận. Publisher phải tôn trọng demand và không phát thêm phần tử khi chưa có yêu cầu tương ứng.

Ví dụ:

~~~java
Flux<Integer> numbers = Flux.range(1, 1_000);

numbers.subscribe(new BaseSubscriber<>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(5);
    }

    @Override
    protected void hookOnNext(Integer value) {
        process(value);
        request(1);
    }
});
~~~

Subscriber yêu cầu năm phần tử đầu tiên, sau đó yêu cầu thêm một phần tử sau mỗi lần xử lý. Demand ở đây đếm phần tử Integer. Reactive Streams không biết một phần tử sẽ được serialize thành 12 byte hay 2 MB.

Điều này vẫn đúng khi phần tử là một object lớn:

~~~java
Flux<Report> reports = reportService.streamReports();
~~~

Một Report có thể chứa vài trường ngắn, trong khi Report khác chứa danh sách dài, văn bản lớn hoặc dữ liệu nhúng. Nếu subscriber yêu cầu 10 phần tử, publisher được phép phát tối đa 10 phần tử theo demand hiện tại, nhưng tổng dung lượng của chúng có thể rất khác nhau.

### 1.1. Ví dụ cùng demand, khác lượng dữ liệu

Giả sử một request-stream được cấp demand 20:

| Kích thước trung bình mỗi payload | Số payload được yêu cầu | Tổng data ước lượng |
|---:|---:|---:|
| 200 byte | 20 | 4.000 byte |
| 4 KB | 20 | 80 KB |
| 500 KB | 20 | 10 MB |

Cùng một demand có thể dẫn đến lượng dữ liệu chênh lệch hàng nghìn lần. Vì vậy, request(n) giúp kiểm soát số phần tử đang được phép phát, nhưng không thể thay thế giới hạn dung lượng hoặc băng thông.

### 1.2. Vì sao Reactive Streams chọn demand theo phần tử?

Publisher và Subscriber có thể làm việc với nhiều kiểu dữ liệu khác nhau. Giao diện Reactive Streams không yêu cầu framework phải biết cách serialize mọi kiểu object để đếm byte. Một phần tử có thể là một số nguyên, một bản ghi, một buffer hoặc một object tùy ứng dụng.

Demand theo phần tử cung cấp hợp đồng đơn giản để phối hợp tốc độ sản xuất và tiêu thụ. Ứng dụng cần giới hạn byte phải bổ sung phép đo kích thước ở nơi biết được biểu diễn thực tế của dữ liệu.

## 2. RSocket truyền demand bằng REQUEST_N

RSocket mang flow control của Reactive Streams qua giao thức. Với các interaction dạng stream, bên nhận cấp số phần tử ban đầu và có thể cấp thêm demand khi đã tiêu thụ dữ liệu.

- Trong **request-stream**, client gửi request cùng số phần tử ban đầu mà nó sẵn sàng nhận. Khi cần thêm dữ liệu, client gửi frame REQUEST_N.
- Trong **request-channel**, hai phía có thể vừa gửi vừa nhận stream. Demand cho luồng dữ liệu đi vào mỗi phía được quản lý riêng; mỗi phía cần cấp demand cho các payload mà nó nhận.
- Trong **request-response**, interaction có một response nên semantics không phải là một stream nhiều phần tử cần cấp demand liên tục như request-stream.
- **fire-and-forget** không có response stream cho caller tiêu thụ.

REQUEST_N mang một số lượng phần tử được yêu cầu. Giá trị này không biểu diễn số byte, không phải số frame mạng và cũng không phải số kilobyte được phép truyền.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket server
    C->>S: REQUEST_STREAM (initial request N = 8)
    S-->>C: PAYLOAD 1
    S-->>C: PAYLOAD 2
    S-->>C: PAYLOAD 3
    Note over C: Client xử lý các phần tử
    C->>S: REQUEST_N (N = 4)
    S-->>C: PAYLOAD 4
    S-->>C: PAYLOAD 5
    S-->>C: PAYLOAD 6
    S-->>C: PAYLOAD 7
~~~

Sơ đồ mô tả demand theo phần tử. Kích thước của bảy payload có thể không bằng nhau; giao thức không suy ra một ngân sách byte từ N.

### 2.1. Flow control giúp điều gì?

Flow control giúp bên gửi không đẩy vô hạn payload đến một subscriber chưa sẵn sàng. Nó hỗ trợ:

- Giảm nguy cơ bên nhận bị ngập bởi quá nhiều phần tử đang chờ xử lý.
- Cho phép subscriber yêu cầu dữ liệu theo khả năng tiêu thụ.
- Truyền tín hiệu nhu cầu xuyên qua các publisher và operator reactive.
- Hỗ trợ cancellation khi subscriber không còn quan tâm đến stream.

Flow control không tự giải quyết các vấn đề sau:

- Một payload đơn lẻ quá lớn.
- Tổng byte truyền mỗi giây vượt quota của ứng dụng.
- Nhiều stream đồng thời cùng chiếm hết băng thông.
- Một operator giữ quá nhiều byte trong buffer dù số phần tử không lớn.
- Dữ liệu được serialize hoặc nén thành kích thước lớn hơn dự kiến.

## 3. Phân biệt các loại giới hạn

Các cơ chế sau thường bị gọi chung là “throttle”, nhưng chúng kiểm soát những đại lượng khác nhau:

| Cơ chế | Đại lượng được kiểm soát | Ví dụ |
|---|---|---|
| Reactive Streams demand / RSocket REQUEST_N | Số phần tử | Yêu cầu thêm 32 payload |
| take(N) | Tổng số phần tử của stream | Kết thúc sau 500 phần tử |
| limitRate(N) | Kích thước các đợt demand upstream | Chia demand thành các đợt nhỏ |
| Max payload/frame length | Kích thước một payload hoặc frame | Từ chối message vượt giới hạn |
| Byte rate limiter | Byte trong một đơn vị thời gian | Trung bình tối đa 2 MB/s |
| Concurrency limit | Số tác vụ hoặc request đang hoạt động | Tối đa 8 phép enrichment đồng thời |
| TCP congestion/receive window | Byte đang truyền hoặc chờ xác nhận ở tầng TCP | Điều tiết truyền tải theo trạng thái mạng |

Một hệ thống cần có thể dùng đồng thời nhiều cơ chế. Ví dụ, RSocket flow control giới hạn số phần tử được gửi theo demand, server đặt max payload size để chặn message quá lớn, và byte rate limiter giới hạn tổng dung lượng được phát trong một giây.

## 4. Kích thước payload và byte trên đường truyền

Để giới hạn băng thông, trước hết cần xác định “byte” nào đang được đo. Một object Java chưa có kích thước truyền tải cố định. Codec có thể serialize nó thành JSON, CBOR, Protobuf hoặc định dạng nhị phân khác.

Một RSocket payload chứa phần data và có thể có metadata. Khi được mã hóa thành frame, còn có header giao thức và các chi phí của transport. Nếu dùng TLS hoặc WebSocket, đường truyền có thêm overhead của các lớp đó.

Có thể hình dung:

~~~text
Object Java
    -> serialize data
    -> encode metadata
    -> RSocket payload
    -> RSocket frame (header và framing)
    -> transport (TCP hoặc WebSocket)
    -> TLS / IP / Ethernet (nếu có)
~~~

Do đó, cần phân biệt:

1. **Kích thước object trong heap**: phụ thuộc JVM, object graph và không phản ánh trực tiếp byte gửi đi.
2. **Kích thước dữ liệu đã serialize**: số byte của biểu diễn data và metadata mà codec tạo ra.
3. **Kích thước RSocket frame**: gồm payload cùng phần header/framing của giao thức.
4. **Số byte trên mạng**: còn có transport, TLS, TCP/IP, retransmission và các overhead khác.

Nếu mục tiêu là quota ứng dụng, thường nên đo số byte đã serialize của data và metadata. Nếu mục tiêu là sử dụng đường truyền hoặc tính cước mạng, cần đo ở tầng transport hoặc network để tính cả overhead. Không cộng các lớp nhiều lần khi tổng hợp số liệu.

### 4.1. Data và metadata đều tiêu tốn byte

Ví dụ, một message có:

- Data JSON: 1.200 byte.
- Routing metadata: 24 byte.
- Trace metadata: 80 byte.
- Tenant metadata: 32 byte.

Ngân sách payload ở cấp ứng dụng cần tính cả data và các metadata entry. Nếu chỉ đo data, hệ thống sẽ đánh giá thấp kích thước message. Với message nhỏ, metadata và framing có thể chiếm tỷ lệ đáng kể.

### 4.2. Compression thay đổi số byte

Nén có thể giảm số byte truyền trên mạng nhưng làm tăng CPU và có thể tăng độ trễ. Cần xác định quota áp dụng trước hay sau compression:

- **Quota dữ liệu ứng dụng**: đo byte sau serialize nhưng trước compression. Cách này phản ánh kích thước logic của payload và ít phụ thuộc vào tỷ lệ nén.
- **Quota băng thông truyền tải**: đo byte thực tế sau compression và framing tại transport.

Hai số liệu phục vụ hai mục đích khác nhau. Nếu hệ thống có compression, hãy theo dõi cả kích thước trước và sau nén để phát hiện payload không nén tốt hoặc tiêu thụ CPU quá mức.

## 5. Giới hạn kích thước một message

Byte rate limiter kiểm soát lượng byte theo thời gian, nhưng một message đơn lẻ quá lớn vẫn có thể gây áp lực bộ nhớ trước khi rate limiter có cơ hội điều tiết. Vì vậy, cần giới hạn kích thước từng payload.

Giới hạn message có thể được áp dụng tại nhiều điểm:

- API đầu vào: từ chối file hoặc trường dữ liệu vượt kích thước cho phép.
- Trước serialize: giới hạn kích thước nội dung logic như số bản ghi hoặc độ dài văn bản.
- Sau serialize: đo byte thực tế và từ chối payload quá lớn.
- Transport: cấu hình giới hạn frame/message mà thư viện và transport hỗ trợ.

RSocket có thể phân mảnh payload lớn thành nhiều frame khi fragmentation được hỗ trợ và cấu hình phù hợp. Phân mảnh giúp vận chuyển payload qua các frame, nhưng không làm giảm tổng byte của payload và không thay thế quota. Cần cấu hình giới hạn frame, message và khả năng reassembly phù hợp với implementation đang dùng.

### 5.1. Đo kích thước từ buffer đã mã hóa

Nếu ứng dụng đã có RSocket Payload, có thể đọc số byte khả dụng của data và metadata buffer:

~~~java
int dataBytes = payload.getData().readableBytes();
int metadataBytes = payload.hasMetadata()
        ? payload.getMetadata().readableBytes()
        : 0;

long payloadBytes = (long) dataBytes + metadataBytes;
~~~

Đây là kích thước data và metadata trong payload tại thời điểm đo. Nó chưa bao gồm toàn bộ header, framing hoặc overhead của TCP/TLS/WebSocket. Khi thao tác với ByteBuf, cần tuân thủ ownership và reference counting của thư viện; không release buffer mà ứng dụng không sở hữu.

Nếu đang ở tầng Spring handler và chỉ có object Java, kích thước chính xác chỉ biết được sau khi codec serialize. Có thể dùng cùng codec để ước lượng hoặc đo, nhưng tránh serialize hai lần một cách vô tình vì sẽ tăng CPU và allocation. Với yêu cầu quota chính xác, hãy instrument tại ranh giới encode/framing hoặc dùng một đường serialize duy nhất rồi đo buffer kết quả.

## 6. Giới hạn băng thông theo byte

Giả sử một server được phép gửi tối đa trung bình 2 MB mỗi giây cho một client. Chỉ đặt demand là 100 payload không đủ, vì 100 payload có thể là 20 KB hoặc 200 MB. Cần một cơ chế cấp ngân sách byte.

### 6.1. Token bucket theo byte

Token bucket là mô hình phổ biến để giới hạn tốc độ:

- Bucket có dung lượng tối đa, tính bằng byte.
- Token được bổ sung theo tốc độ cấu hình, ví dụ 2 MB mỗi giây.
- Mỗi message tiêu thụ số token tương ứng với kích thước đã đo.
- Nếu chưa đủ token, message phải chờ hoặc bị từ chối theo chính sách.

Dung lượng bucket quyết định lượng burst cho phép. Tốc độ bổ sung quyết định throughput trung bình dài hạn. Ví dụ, tốc độ 2 MB/s với bucket 4 MB cho phép một burst tối đa gần 4 MB khi bucket đầy, sau đó phải chờ token được bổ sung.

~~~mermaid
flowchart TD
    A["Payload đã serialize"] --> B["Đo số byte"]
    B --> C{"Payload có vượt max message?"}
    C -- Có --> D["Từ chối / phát lỗi"]
    C -- Không --> E["Yêu cầu byte token"]
    E --> F{"Đủ token?"}
    F -- Chưa --> G["Chờ hoặc bị từ chối theo quota"]
    G --> E
    F -- Đủ --> H["Trừ token"]
    H --> I["Gửi qua RSocket"]
~~~

Nếu một message lớn hơn dung lượng bucket tối đa, message sẽ không bao giờ lấy đủ token. Vì vậy, max message size phải tương thích với bucket capacity hoặc limiter phải có chính sách riêng cho message lớn.

### 6.2. Ví dụ tích hợp limiter với Reactor

Ứng dụng có thể định nghĩa một abstraction cấp byte token:

~~~java
public interface ByteRateLimiter {
    Mono<Void> acquire(long bytes);
}
~~~

Giả sử encoder cung cấp kích thước ước lượng gần với số byte sẽ gửi:

~~~java
Flux<EncodedEvent> limited = encodedEvents
        .concatMap(event -> {
            long bytes = event.encodedSizeBytes();
            if (bytes > MAX_MESSAGE_BYTES) {
                return Mono.error(
                        new IllegalArgumentException("Message too large"));
            }
            return byteRateLimiter.acquire(bytes)
                    .thenReturn(event);
        });
~~~

Ví dụ này minh họa cách kết hợp byte budget với reactive pipeline; ByteRateLimiter và EncodedEvent là kiểu do ứng dụng định nghĩa. acquire chỉ hoàn tất khi đủ ngân sách. concatMap giữ thứ tự phát và không chuyển message tiếp theo qua limiter trước khi message hiện tại được cấp token. Nếu cần xử lý đồng thời, có thể dùng flatMapSequential với concurrency hữu hạn, nhưng phải đảm bảo limiter là thread-safe và thứ tự phát được giữ theo yêu cầu.

Đặt limiter sau bước đo kích thước nhưng trước bước gửi. Nếu đo bằng kích thước ước lượng trước serialize, hãy cộng biên an toàn và kiểm chứng bằng số liệu sau encode. Đối với quota theo wire bytes, cần instrument ở tầng transport vì payload size không gồm toàn bộ overhead.

### 6.3. Quota theo client, tenant và toàn hệ thống

Limiter có thể được áp dụng ở nhiều phạm vi:

| Phạm vi | Mục đích | Ví dụ |
|---|---|---|
| Mỗi stream | Ngăn một stream chiếm quá nhiều tài nguyên | Tối đa 256 KB/s cho một stream |
| Mỗi connection | Giới hạn tổng lưu lượng của một kết nối | Tối đa 2 MB/s cho một RSocket connection |
| Mỗi user hoặc tenant | Thực thi quota của khách hàng | Tenant A tối đa 20 MB/phút |
| Toàn service | Bảo vệ năng lực hệ thống | Tổng egress không vượt ngân sách đã đặt |

Các limiter ở phạm vi khác nhau cần phối hợp. Một client có thể mở nhiều stream; nếu chỉ giới hạn từng stream, tổng lưu lượng của client vẫn có thể tăng theo số stream. Khi quota phải áp dụng giữa nhiều instance server, bộ đếm hoặc token bucket cần có cơ chế phân tán hoặc quota được phân bổ rõ cho từng instance.

## 7. Kết hợp demand theo phần tử với ngân sách byte

Một pipeline an toàn thường áp dụng nhiều lớp kiểm soát:

1. Giới hạn kích thước một phần tử trước khi cấp tài nguyên lớn.
2. Dùng demand để giới hạn số phần tử đang được phép phát.
3. Dùng concurrency hữu hạn cho các bước I/O hoặc enrichment.
4. Đo byte sau serialize và áp dụng byte rate limiter.
5. Giữ giới hạn buffer để dữ liệu chờ không tăng vô hạn.
6. Hủy công việc khi subscriber cancel hoặc deadline kết thúc.

Ví dụ kết hợp các cơ chế:

~~~java
Flux<EncodedEvent> outbound = source
        .filter(Event::isRelevant)
        .map(encoder::encode)
        .filter(encoded -> encoded.encodedSizeBytes() <= MAX_MESSAGE_BYTES)
        .limitRate(32)
        .concatMap(encoded ->
                byteRateLimiter.acquire(encoded.encodedSizeBytes())
                        .thenReturn(encoded));
~~~

Pipeline này có các giới hạn khác nhau:

- filter giảm số phần tử cần xử lý.
- encode tạo biểu diễn có thể đo kích thước.
- kiểm tra kích thước loại message quá lớn.
- limitRate điều tiết demand upstream theo số phần tử.
- byteRateLimiter điều tiết byte theo thời gian.

Trong ví dụ production, không nên âm thầm bỏ payload quá lớn bằng filter nếu client cần biết dữ liệu đã bị từ chối. Hãy phát lỗi có cấu trúc, ghi metric hoặc đưa sự kiện vào dead-letter path tùy semantics. Nếu cần giới hạn số phần tử, dùng take riêng; limitRate không làm stream kết thúc sau một số phần tử nhất định.

### 7.1. Backpressure không thay thế byte queue limit

Một buffer 100 phần tử có thể chứa 100 KB nếu mỗi phần tử 1 KB, nhưng cũng có thể chứa 1 GB nếu mỗi phần tử 10 MB. Vì vậy, giới hạn buffer theo số phần tử chưa đủ khi kích thước biến thiên lớn.

Khi dữ liệu chờ có kích thước không đồng đều, hãy theo dõi cả:

- Số phần tử đang chờ.
- Tổng byte đang chờ.
- Kích thước phần tử lớn nhất.
- Tuổi của phần tử cũ nhất trong queue.

Nếu tổng byte vượt ngân sách, ứng dụng cần chờ upstream, từ chối, drop theo chính sách hoặc ngắt stream. Với dữ liệu bắt buộc phải xử lý, nên lưu bền vững thay vì giữ một queue trong bộ nhớ không giới hạn.

### 7.2. Fairness giữa nhiều stream

Một stream có payload nhỏ nhưng tần suất rất cao có thể cạnh tranh với stream có payload lớn và ít thường xuyên. Nếu limiter chỉ dùng một bucket toàn cục, stream đến trước có thể tiêu thụ hết token.

Có thể áp dụng quota phân cấp:

- Bucket toàn service bảo vệ tổng egress.
- Bucket theo tenant bảo đảm mỗi tenant có phần ngân sách phù hợp.
- Bucket theo stream ngăn một stream chiếm hết quota của tenant.

Nếu cần fairness, chọn thuật toán phân phối rõ ràng như weighted fair queueing hoặc round-robin giữa các hàng đợi tenant. Chỉ thêm delay vào từng stream không tự bảo đảm fairness toàn cục.

## 8. Ví dụ Spring RSocket: stream dữ liệu có giới hạn

Ví dụ dưới đây mô tả một handler phát sự kiện đã được encode và giới hạn theo cả số phần tử lẫn byte. Các kiểu ByteRateLimiter, EncodedEvent và encoder là thành phần ứng dụng:

~~~java
@Controller
public class TelemetryController {

    private static final int MAX_EVENTS = 500;
    private static final long MAX_MESSAGE_BYTES = 64 * 1024;

    private final TelemetryService telemetryService;
    private final EventEncoder encoder;
    private final ByteRateLimiter byteRateLimiter;

    public TelemetryController(
            TelemetryService telemetryService,
            EventEncoder encoder,
            ByteRateLimiter byteRateLimiter) {
        this.telemetryService = telemetryService;
        this.encoder = encoder;
        this.byteRateLimiter = byteRateLimiter;
    }

    @MessageMapping("telemetry.stream")
    public Flux<EncodedEvent> stream(
            @Payload TelemetryQuery query,
            Principal principal) {

        int maxEvents = Math.max(
                1, Math.min(query.maxEvents(), MAX_EVENTS));

        return telemetryService.streamVisibleTo(
                        principal.getName(), query.deviceId())
                .filter(TelemetryEvent::isValid)
                .map(encoder::encode)
                .concatMap(event -> {
                    long bytes = event.encodedSizeBytes();
                    if (bytes > MAX_MESSAGE_BYTES) {
                        return Mono.error(
                                new MessageTooLargeException(bytes));
                    }
                    return byteRateLimiter.acquire(bytes)
                            .thenReturn(event);
                })
                .take(maxEvents)
                .limitRate(32);
    }
}
~~~

Đây là cấu trúc minh họa, không phải implementation của một thư viện token bucket cụ thể. Khi tích hợp thật, cần xác định encoder có trả về đúng kích thước byte sẽ được gửi hay chỉ là ước lượng, limiter có xử lý cancellation khi chờ token hay không, và quota được áp dụng ở phạm vi nào.

Thứ tự operator cũng là quyết định nghiệp vụ. Nếu take đặt trước limiter, server có thể đọc tối đa số sự kiện đó từ upstream rồi chờ token trước khi gửi. Nếu limiter đặt trước take, các phần tử được lấy token có thể nhiều hơn số phần tử cuối cùng được phát tùy cách prefetch và cancellation. Hãy đo và kiểm tra số byte thực tế, tránh tiêu thụ token cho payload đã bị hủy trước khi gửi.

## 9. Đo lường và vận hành

Muốn biết hệ thống có tuân thủ giới hạn hay không, cần quan sát demand, số phần tử và byte như những đại lượng riêng biệt.

### 9.1. Các metric nên có

| Metric | Đơn vị | Ý nghĩa |
|---|---|---|
| Payloads emitted | phần tử/giây | Tốc độ phát theo số message |
| Payload bytes | byte/giây | Kích thước data và metadata đã serialize |
| Wire bytes | byte/giây | Lưu lượng đo ở tầng transport/network |
| Payload size histogram | byte | Phân bố kích thước message |
| Outstanding demand | phần tử | Số phần tử đã được yêu cầu nhưng chưa tiêu thụ |
| Queued bytes | byte | Dung lượng dữ liệu đang chờ |
| Queue age | mili giây | Thời gian phần tử phải chờ |
| Rate-limit wait | mili giây | Thời gian chờ ngân sách byte |
| Rejected/oversized messages | phần tử | Số message vượt giới hạn |
| Cancellation | số lần | Stream bị hủy và tài nguyên được giải phóng |

Theo dõi p50, p95 và p99 của payload size, không chỉ giá trị trung bình. Một số ít message cực lớn có thể gây spike bộ nhớ dù kích thước trung bình nhỏ.

### 9.2. Tính throughput theo byte

Throughput ứng dụng trong một khoảng thời gian có thể tính bằng:

~~~text
byte_per_second = total_encoded_payload_bytes / elapsed_seconds
~~~

Nếu đo wire throughput, thay tử số bằng số byte transport ghi hoặc số byte mạng quan sát được. Cần dùng cùng một ranh giới đo khi so sánh với quota.

Ví dụ, 10.000 message mỗi giây với kích thước trung bình 100 byte tương đương khoảng 1 MB/s payload. 1.000 message mỗi giây với kích thước trung bình 10 KB cũng tương đương khoảng 10 MB/s. Số message/giây không thể thay cho byte/giây.

### 9.3. Cảnh báo và kiểm tra quá tải

Nên cảnh báo khi:

- Byte throughput tiến sát quota trong thời gian kéo dài.
- Queued bytes hoặc queue age tăng liên tục.
- Tỷ lệ message bị từ chối vì quá lớn tăng đột biến.
- Thời gian chờ token tăng và làm độ trễ request vượt SLA.
- Nhiều stream cùng lúc bị cancel hoặc lỗi do quá tải.
- Wire bytes tăng khác thường so với payload bytes, có thể do framing, TLS, retransmission hoặc compression thay đổi.

Khi kiểm thử tải, tạo dữ liệu có kích thước phân bố khác nhau. Chỉ kiểm thử với payload đồng đều nhỏ sẽ không bộc lộ vấn đề do message lớn hoặc buffer theo byte.

## 10. Những hiểu lầm thường gặp

### “request(10) nghĩa là gửi tối đa 10 KB”

Không đúng. request(10) cho phép tối đa 10 phần tử theo demand hiện tại. Kích thước từng phần tử có thể khác nhau.

### “limitRate(100) giới hạn 100 message mỗi giây”

Không đúng. limitRate điều tiết các đợt demand upstream theo số phần tử. Nó không phải bộ giới hạn tốc độ theo thời gian.

### “Buffer 100 phần tử chỉ tốn ít bộ nhớ”

Không chắc. Nếu mỗi phần tử có kích thước lớn, 100 phần tử có thể chiếm rất nhiều byte. Cần giới hạn tổng byte và kích thước phần tử.

### “TCP đã flow control nên ứng dụng không cần byte quota”

TCP quản lý truyền tải và tắc nghẽn ở tầng mạng. Nó không biết quota theo user, tenant hoặc chi phí của ứng dụng. Một kết nối có thể hoạt động tốt ở TCP nhưng vẫn vượt ngân sách egress của tenant.

### “Giới hạn frame length là giới hạn băng thông”

Không đúng. Max frame length giới hạn kích thước frame hoặc message theo cấu hình. Một stream vẫn có thể gửi rất nhiều frame nhỏ và vượt quota byte mỗi giây.

### “Nén luôn giải quyết được payload lớn”

Nén không bảo đảm mọi dữ liệu đều giảm kích thước. Một payload đã nén hoặc dữ liệu ngẫu nhiên có thể không giảm nhiều, trong khi CPU vẫn phải trả chi phí nén/giải nén.

## 11. Checklist thiết kế

Trước khi phát hành request-stream có lưu lượng lớn, hãy xác nhận:

1. Demand được hiểu và đo theo số phần tử.
2. Request-stream và request-channel cấp demand đúng chiều dữ liệu.
3. Có giới hạn kích thước tối đa cho mỗi payload hoặc frame phù hợp với transport.
4. Đã xác định quota đo trước hay sau compression.
5. Byte rate limiter đo đúng ranh giới byte cần bảo vệ.
6. Bucket capacity tương thích với max message size và burst được phép.
7. Queue có giới hạn theo số phần tử và tổng byte.
8. Concurrency của các bước I/O/enrichment được giới hạn.
9. Cancellation dừng việc chờ token và giải phóng tài nguyên upstream.
10. Có metric riêng cho phần tử/giây, payload byte/giây và wire byte/giây.
11. Quota theo stream, tenant và toàn service được phối hợp.
12. Kiểm thử với payload nhỏ, lớn, biến thiên kích thước và consumer chậm.

## 12. Tổng kết

Reactive Streams và RSocket flow control điều tiết demand theo số phần tử. REQUEST_N yêu cầu thêm payload, không cấp một lượng byte cố định. Kích thước payload phụ thuộc data, metadata, codec và nội dung thực tế; số byte trên mạng còn bao gồm framing và overhead của transport.

Để kiểm soát băng thông, cần đo byte ở ranh giới phù hợp, giới hạn kích thước từng message và áp dụng byte rate limiter như token bucket. Kết hợp các cơ chế này với demand, concurrency hữu hạn, queue có giới hạn và cancellation sẽ giúp request-stream vừa tôn trọng khả năng tiêu thụ của client, vừa bảo vệ băng thông và bộ nhớ của hệ thống.
