# Thực nghiệm dịch vụ quá tải với và không có leasing

Khi nhiều client gửi request cùng lúc, một dịch vụ RSocket có thể nhận nhiều công việc hơn khả năng xử lý. Hàng đợi tăng, thời gian phản hồi kéo dài, số request lỗi tăng và tài nguyên như thread, connection pool hoặc bộ nhớ có thể bị sử dụng quá mức. RSocket cung cấp **Leasing** để responder cấp hạn ngạch request cho requester trong một khoảng thời gian. Nhờ vậy, requester có thể điều tiết số interaction mới được bắt đầu trên kết nối.

Bài học này xây dựng một thử nghiệm có cùng tải đầu vào trong hai chế độ: không bật leasing và bật leasing. Ta quan sát số request được server tiếp nhận, số request bị từ chối, số request đang xử lý, thời gian chờ và thông lượng. Mục tiêu là hiểu leasing bảo vệ dịch vụ ở bước tiếp nhận request như thế nào, đồng thời nhận ra các giới hạn của nó khi hệ thống có nhiều kết nối hoặc request kéo dài.

Sau bài học, bạn có thể:

- Giải thích hiện tượng quá tải và vì sao backpressure theo stream chưa đủ để giới hạn số request mới.
- Mô tả LEASE frame, TTL, số request được cấp và cờ leasing trong SETUP.
- Cấu hình RSocket Java và Spring RSocketRequester để sử dụng leasing.
- Thiết kế thử nghiệm tải có và không có leasing với cùng một workload.
- Đọc các chỉ số throughput, latency, in-flight, pending và rejected.
- Kết hợp leasing với giới hạn concurrency, hàng đợi hữu hạn và bảo vệ ở tầng ứng dụng.

## 1. Dịch vụ quá tải xảy ra như thế nào?

Giả sử một dịch vụ có thể xử lý trung bình 120 request mỗi giây. Nếu client gửi 200 request mỗi giây trong một thời gian dài, số request đến nhiều hơn số request hoàn tất. Phần chênh lệch sẽ tích tụ thành hàng đợi hoặc bị từ chối.

Ký hiệu:

- λ: tốc độ request đến, tính bằng request/giây.
- μ: năng lực xử lý trung bình, tính bằng request/giây.
- L: số request trung bình đang chờ hoặc đang xử lý.
- W: thời gian trung bình một request ở trong hệ thống.

Khi λ tiến gần hoặc vượt μ, độ trễ và hàng đợi có thể tăng nhanh. Nếu hệ thống không giới hạn hàng đợi, tải tăng có thể kéo theo bộ nhớ tăng và làm các request vốn có khả năng thành công cũng bị chậm.

~~~mermaid
flowchart LR
    A[Client requests] --> B[Network connection]
    B --> C[Request admission]
    C --> D[Work queue]
    D --> E[Service workers]
    E --> F[Response]
    D --> G[Queue grows]
    G --> H[Timeout / rejection / resource pressure]
~~~

RSocket hỗ trợ multiplexing nhiều interaction trên một kết nối. Điều đó giúp giảm chi phí mở kết nối, nhưng cũng có nghĩa một kết nối có thể khởi tạo nhiều request đồng thời. Multiplexing tự nó không đặt giới hạn nghiệp vụ cho số request mới.

### Ví dụ tải vượt năng lực

Giả sử một handler mất khoảng 100 ms để xử lý mỗi request và có 12 vị trí xử lý đồng thời. Năng lực lý thuyết xấp xỉ:

\[
\mu \approx \frac{12}{0.1} = 120 \text{ request/giây}
\]

Nếu client gửi 200 request/giây, trung bình có khoảng 20 request đang cần xử lý cùng lúc. Với giới hạn 12 vị trí, phần request vượt giới hạn phải chờ hoặc bị từ chối.

Con số này chỉ là mô hình để thiết kế thí nghiệm. Năng lực thực tế còn phụ thuộc CPU, database, network, thời gian xử lý không đồng đều và chi phí serialize/deserialize.

## 2. Không có leasing: request được gửi ngay sau SETUP

Leasing là tính năng tùy chọn của RSocket. Nếu không bật leasing, sau khi kết nối được thiết lập, requester có thể bắt đầu các interaction mà không cần đợi LEASE frame.

Các loại request khởi tạo interaction gồm:

- REQUEST_RESPONSE
- REQUEST_FNF (fire-and-forget)
- REQUEST_STREAM
- REQUEST_CHANNEL

Không có leasing, client vẫn chịu các giới hạn khác như backpressure trong stream, giới hạn kết nối, timeout và chính sách của ứng dụng. Tuy nhiên, giao thức không cấp hạn ngạch theo thời gian cho số interaction mới được khởi tạo.

Ví dụ client tạo RSocketRequester mặc định:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .tcp("localhost", 7000);
~~~

Trong cấu hình mặc định này, builder không yêu cầu sử dụng leasing. Khi có request, requester có thể gửi interaction sau khi kết nối được thiết lập.

### Vì sao backpressure chưa giải quyết hết quá tải?

Backpressure của Reactive Streams điều tiết số phần tử trong một publisher. Với request-stream, requester dùng demand để thông báo số response payload mà nó sẵn sàng nhận. RSocket chuyển demand thành REQUEST_N.

Cơ chế này kiểm soát **số response item trong một stream**. Nó không phải hạn ngạch cho tổng số interaction mới mà client có thể mở.

Ví dụ:

- Một REQUEST_STREAM mở một interaction và có thể tạo ra hàng nghìn response item.
- Nhiều REQUEST_RESPONSE độc lập có thể được mở đồng thời trên cùng kết nối.
- Một REQUEST_FNF không có response nhưng vẫn tiêu thụ công việc ở server.
- Nhiều client có thể cùng mở các stream dài hạn.

Do đó cần phân biệt:

| Cơ chế | Điều tiết điều gì? | Phạm vi |
|---|---|---|
| REQUEST_N / backpressure | Số response item requester sẵn sàng nhận | Một stream |
| Leasing | Số interaction mới requester được phép khởi tạo trong thời hạn | Một kết nối |
| Giới hạn concurrency ở ứng dụng | Số công việc đang thực thi đồng thời | Handler hoặc dịch vụ |
| Rate limit theo người dùng/tenant | Tốc độ request của một chủ thể nghiệp vụ | Người dùng hoặc tenant |
| Giới hạn hàng đợi | Số công việc chờ được xử lý | Thành phần tiếp nhận |

Không có leasing, dịch vụ cần dựa vào giới hạn concurrency, hàng đợi hữu hạn, rate limit, bulkhead và chính sách từ chối để bảo vệ tài nguyên.

## 3. Leasing hoạt động như thế nào?

**Leasing** là cơ chế cấp quyền khởi tạo request trong một khoảng thời gian. Responder gửi LEASE frame cho requester, trong đó có:

- **Time-To-Live (TTL):** thời gian lease còn hiệu lực, tính bằng mili giây.
- **Number of Requests:** số interaction mới tối đa requester được phép gửi trong thời hạn đó.
- **Metadata tùy chọn:** ngữ cảnh bổ sung nếu ứng dụng cần.

LEASE frame dùng stream ID bằng 0 vì nó áp dụng ở cấp kết nối. Requester phải tôn trọng hạn ngạch: không được gửi nhiều request hơn số lượng được cấp trong TTL.

~~~mermaid
sequenceDiagram
    participant C as Requester
    participant S as Responder
    C->>S: SETUP (có cờ L: hỗ trợ leasing)
    S-->>C: LEASE (TTL = 1 giây, 50 requests)
    loop Trong thời hạn lease
        C->>S: REQUEST_RESPONSE / REQUEST_STREAM / REQUEST_FNF
        S-->>C: PAYLOAD hoặc xử lý request
    end
    Note over C: Hết số request hoặc lease hết hạn
    C->>S: Chờ lease mới trước request tiếp theo
    S-->>C: LEASE mới
~~~

Cờ L trong SETUP cho biết requester sẵn sàng tuân thủ leasing. Nếu kết nối sử dụng leasing, hai phía phải đợi lease từ peer tương ứng trước khi khởi tạo request theo chiều đó. Trong kịch bản client gọi server, server cấp lease cho client.

Một LEASE frame mới nhất thay thế giá trị lease trước đó. Không cộng dồn số request còn dư từ lease cũ vào lease mới. Nếu responder nhận một request vượt quá lease mà nó cấp, giao thức quy định responder từ chối interaction bằng ERROR[REJECTED].

### Leasing áp dụng cho request nào?

Hạn ngạch đếm số interaction được khởi tạo, không đếm số payload response trong stream:

| Request type | Cách tính quota |
|---|---|
| REQUEST_RESPONSE | Mỗi interaction khởi tạo tính một request |
| REQUEST_FNF | Mỗi interaction khởi tạo tính một request |
| REQUEST_STREAM | Một request cho toàn bộ stream, không tính từng response item |
| REQUEST_CHANNEL | Một request khi mở channel; các payload tiếp theo thuộc interaction đó |

Điều này rất quan trọng khi dịch vụ có nhiều stream dài hạn. Một request-stream có thể giữ tài nguyên trong nhiều phút nhưng chỉ tiêu thụ một đơn vị quota khi được khởi tạo. Vì vậy leasing không thay thế giới hạn số stream đang hoạt động hoặc giới hạn thời gian sống của stream.

### Ai tạo ra lease?

Protocol không tự tính năng lực xử lý của server. Ứng dụng responder phải quyết định TTL và số request được cấp, rồi cung cấp các lease cho RSocket implementation gửi đi.

Điều đó có nghĩa leasing là cơ chế thực thi hạn ngạch ở tầng giao thức; logic tính hạn ngạch vẫn phải dựa trên tình trạng dịch vụ, số kết nối, tenant và năng lực tài nguyên.

## 4. Bật leasing bằng RSocket Java

Trong RSocket Java, leasing không được bật mặc định. Cả server và requester phải cấu hình sử dụng tính năng này.

### Cấu hình responder cấp lease

RSocketServer nhận một LeaseSender thông qua LeaseSpec.sender. Ví dụ cấp năm request trong mỗi chu kỳ 100 ms, với TTL 150 ms:

~~~java
RSocketServer server = RSocketServer.create(acceptor)
    .lease(spec -> spec.sender(() ->
        Flux.interval(
                Duration.ZERO,
                Duration.ofMillis(100)
            )
            .map(tick ->
                Lease.create(
                    Duration.ofMillis(150),
                    5
                )
            )
    ))
    .bind(TcpServerTransport.create("localhost", 7000))
    .block();
~~~

Trong ví dụ:

- Flux.interval tạo một lease ngay khi subscription bắt đầu, sau đó phát lease mới mỗi 100 ms.
- Mỗi lease cho phép tối đa năm interaction.
- TTL 150 ms giúp lease vẫn còn hiệu lực trong một khoảng ngắn nếu lần phát tiếp theo bị trễ.
- Khi LEASE frame mới đến, giá trị lease trước đó bị thay thế.

acceptor là SocketAcceptor đã được cấu hình để xử lý request. Trong ứng dụng Spring, có thể tạo responder từ RSocketMessageHandler rồi cung cấp cho RSocketServer. Với server do Spring Boot quản lý, cần cấu hình leasing ở tầng tạo RSocket server/connection tương ứng; chỉ cấu hình client là chưa đủ để server phát lease.

Ví dụ trên minh họa chính sách cố định. Hệ thống thực tế nên tạo quota dựa trên năng lực hiện tại và phân bổ ngân sách cho từng kết nối.

### Cấu hình requester tuân thủ lease

Requester phải bật lease để gửi cờ L trong SETUP và theo dõi quota được cấp:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector ->
        connector.lease(spec ->
            spec.maxPendingRequests(512)
        )
    )
    .tcp("localhost", 7000);
~~~

maxPendingRequests(512) giới hạn số request đang chờ lease ở phía requester. Nó không phải số request được server cấp trong mỗi lease.

Trong RSocket Java 1.1.x, giá trị mặc định của hàng đợi chờ lease là 256. Đặt giá trị bằng 0 khiến request được kết thúc ngay nếu chưa có lease khả dụng. Hãy chọn giới hạn theo khả năng chờ và bộ nhớ của client.

### Cần bật đồng bộ hai phía

| Server | Client | Kết quả |
|---|---|---|
| Không bật lease | Không bật lease | Request được gửi sau SETUP, không có quota theo LEASE |
| Bật lease và phát LEASE | Bật lease | Client tuân thủ TTL và số request được cấp |
| Bật lease | Client không yêu cầu lease | Client không thực hiện quy trình leasing như hợp đồng đã cấu hình |
| Không hỗ trợ lease | Client yêu cầu lease | Server có thể từ chối SETUP vì không hỗ trợ cấu hình được yêu cầu |

Không nên bật leasing chỉ ở một phía rồi giả định request đã được điều tiết.

## 5. Tích hợp với Spring RSocketRequester

Spring RSocketRequester cung cấp API fluent cho request-response, request-stream và các interaction khác. Builder có callback rsocketConnector để cấu hình RSocketConnector bên dưới.

Ví dụ requester bật leasing:

~~~java
RSocketRequester leasedRequester =
    RSocketRequester.builder()
        .rsocketConnector(connector ->
            connector.lease(spec ->
                spec.maxPendingRequests(512)
            )
        )
        .tcp("localhost", 7000);
~~~

Requester không bật leasing:

~~~java
RSocketRequester unleasedRequester =
    RSocketRequester.builder()
        .tcp("localhost", 7000);
~~~

Handler Spring có thể giữ nguyên:

~~~java
@Controller
public class WorkController {

    private final WorkService workService;

    public WorkController(WorkService workService) {
        this.workService = workService;
    }

    @MessageMapping("work.simulate")
    public Mono<WorkResult> simulate(WorkRequest request) {
        return workService.process(request);
    }
}
~~~

Leasing là tính năng ở cấp kết nối. Nó không yêu cầu thay đổi route hay kiểu trả về của handler. Cùng một handler có thể được kiểm tra trong hai chế độ bằng cách thay đổi cấu hình requester và server.

## 6. Xây dựng dịch vụ mô phỏng quá tải

Để thử nghiệm có thể lặp lại, hãy tạo một handler có thời gian xử lý tương đối ổn định và giới hạn số công việc đang chạy.

Ví dụ dịch vụ có 12 vị trí xử lý đồng thời. Mỗi request mất khoảng 100 ms. Nếu không còn vị trí trống, handler từ chối request để mô phỏng overload:

~~~java
@Service
public class WorkService {

    private final Semaphore slots = new Semaphore(12);
    private final AtomicInteger inFlight = new AtomicInteger();
    private final LongAdder rejected = new LongAdder();

    public Mono<WorkResult> process(WorkRequest request) {
        return Mono.defer(() -> {
            if (!slots.tryAcquire()) {
                rejected.increment();
                return Mono.error(
                    new RejectedExecutionException(
                        "Service capacity reached"
                    )
                );
            }

            int active = inFlight.incrementAndGet();

            return Mono.delay(Duration.ofMillis(100))
                .map(ignored ->
                    new WorkResult(request.id(), "OK", active)
                )
                .doFinally(signal -> {
                    inFlight.decrementAndGet();
                    slots.release();
                });
        });
    }
}
~~~

Semaphore.tryAcquire không chờ để lấy slot. Nếu dịch vụ đã đủ 12 công việc đang chạy, request mới nhận lỗi ngay. Trong hệ thống thực tế, có thể thay mô phỏng bằng database, downstream API hoặc tác vụ CPU có thời gian xử lý xác định.

doFinally giảm bộ đếm và trả slot khi publisher hoàn tất, gặp lỗi hoặc bị hủy. Nhờ đó, slot không bị giữ mãi khi client hủy request.

Các trường đo lường cần thu thập:

- inFlight: số request đang thực thi.
- rejected: số request bị từ chối do hết slot.
- completed: số request hoàn tất thành công.
- latency: thời gian xử lý và thời gian chờ từ client.
- pending: số request đang chờ lease ở requester.

## 7. Tạo workload giống nhau cho hai lần chạy

Dùng cùng một luồng tải để so sánh công bằng. Ví dụ tạo 500 request, phát một request mới mỗi 5 ms, tương đương tốc độ đưa vào khoảng 200 request/giây trong 2,5 giây.

~~~java
Flux<LoadOutcome> runLoad(RSocketRequester requester) {
    return Flux.interval(Duration.ofMillis(5))
        .take(500)
        .flatMap(id ->
            requester
                .route("work.simulate")
                .data(new WorkRequest(id))
                .retrieveMono(WorkResult.class)
                .map(result -> LoadOutcome.success(id, result))
                .onErrorResume(error ->
                    Mono.just(LoadOutcome.failure(id, error))
                ),
            500
        );
}
~~~

Concurrency 500 cho phép workload tạo đủ request để quan sát sự khác biệt. Trong chế độ leasing, các request chưa có quota có thể phải chờ ở requester. Trong chế độ không leasing, request được gửi ngay và handler có thể từ chối khi hết slot.

Chạy cùng workload với hai requester:

~~~java
Flux<LoadOutcome> baseline =
    runLoad(unleasedRequester);

Flux<LoadOutcome> withLease =
    runLoad(leasedRequester);
~~~

Hãy chạy từng lượt riêng biệt để tránh hai workload cạnh tranh tài nguyên cùng lúc. Giữ nguyên payload, số request, khoảng phát, server, thời gian xử lý và giới hạn concurrency ở server.

## 8. Thử nghiệm không có leasing

Ở lượt đầu:

- Server không cấu hình RSocketServer.lease(...).
- Client không cấu hình RSocketConnector.lease(...).
- Workload phát 500 request với tốc độ 200 request/giây.
- Mỗi request cần khoảng 100 ms xử lý.
- Server có tối đa 12 slot đồng thời.

Năng lực xử lý lý thuyết của mô hình là khoảng 120 request/giây. Tải đầu vào 200 request/giây vượt năng lực, do đó có thể quan sát:

1. Nhiều request cùng đến server trong một khoảng ngắn.
2. inFlight nhanh chóng đạt 12.
3. Request tiếp theo bị từ chối do không còn slot.
4. Tỷ lệ lỗi tăng và client nhận kết quả thất bại.
5. Nếu bỏ giới hạn slot và thay bằng hàng đợi không giới hạn, độ trễ và bộ nhớ có thể tăng theo thời gian.

Không có leasing không có nghĩa RSocket không có backpressure. Các stream vẫn tuân thủ demand của Reactive Streams. Điều đang thiếu là hạn ngạch ở bước khởi tạo interaction mới.

## 9. Thử nghiệm có leasing

Ở lượt thứ hai, giữ nguyên server handler và workload nhưng bật leasing:

- Server phát năm request cho mỗi lease.
- Mỗi lease có TTL 150 ms.
- Lease mới được phát mỗi 100 ms.
- Client bật leasing và có tối đa 512 request chờ lease.

Quota được cấp tương đương khoảng 50 request mới mỗi giây khi các lease được phát đều đặn. Requester phải chờ khi hết quota, thay vì gửi tất cả request đến server cùng lúc.

Trong điều kiện mô phỏng này, trung bình khoảng năm request bắt đầu mỗi 100 ms. Với thời gian xử lý 100 ms, số request đang thực thi thường thấp hơn giới hạn 12 slot. Các request trong hàng đợi client được gửi dần khi quota mới đến.

Kết quả mong đợi:

- Số request bị từ chối tại server giảm mạnh.
- inFlight thấp hơn và ổn định hơn.
- Request latency phía client tăng do có thời gian chờ quota.
- Pending queue ở requester tăng trong lúc workload đến nhanh hơn quota.
- Tổng thời gian hoàn tất toàn bộ 500 request dài hơn vì server nhận request theo hạn ngạch.

Leasing không làm biến mất nhu cầu 200 request/giây của workload. Nó chuyển một phần thời gian chờ về phía requester và giúp responder tiếp nhận request theo ngân sách được cấp.

## 10. Đọc và so sánh kết quả

Ghi lại số liệu của mỗi lượt trong cùng một khoảng đo:

| Chỉ số | Không leasing | Có leasing |
|---|---|---|
| Offered request rate | Theo workload | Theo workload |
| Accepted request rate | Có thể vượt năng lực tức thời | Bị giới hạn theo lease |
| Server rejected | Có thể cao khi quá tải | Thường giảm nếu quota phù hợp |
| Max in-flight | Dễ chạm giới hạn dịch vụ | Thường ổn định hơn nếu quota và concurrency phù hợp |
| Client pending | Ít chờ quota ở giao thức | Có thể tăng do chờ lease |
| End-to-end latency | Có thể cao do reject/retry hoặc queue | Tăng do chờ quota nhưng dễ dự đoán hơn |
| Completion time | Có thể ngắn với request thành công nhưng nhiều lỗi | Có thể dài hơn do admission có kiểm soát |

Không nên kết luận leasing luôn làm latency thấp hơn. Trong một workload vượt năng lực, leasing có thể làm thời gian chờ phía client tăng lên nhưng giảm lỗi và độ trễ ở phía server. Cần xem cả latency thành công, latency tổng thể và tỷ lệ hoàn tất.

Với ví dụ 12 slot và 100 ms mỗi request, năng lực lý thuyết là khoảng 120 request/giây. Cấp khoảng 50 request/giây tạo khoảng đệm cho dao động và các công việc khác. Số liệu thực tế có thể khác do thời gian phát lease, độ trễ mạng và lịch chạy của scheduler.

### Bảng kết quả cần ghi

| Metric | Không lease | Có lease |
|---|---:|---:|
| Tổng request được tạo | 500 | 500 |
| Request thành công | Đo thực tế | Đo thực tế |
| Request bị từ chối ở server | Đo thực tế | Đo thực tế |
| Pending request cao nhất ở client | Không áp dụng hoặc đo queue ứng dụng | Đo thực tế |
| In-flight cao nhất ở server | Đo thực tế | Đo thực tế |
| p50 latency | Đo thực tế | Đo thực tế |
| p95 latency | Đo thực tế | Đo thực tế |
| p99 latency | Đo thực tế | Đo thực tế |
| Tổng thời gian hoàn tất | Đo thực tế | Đo thực tế |

Không điền số liệu ước đoán vào báo cáo thí nghiệm. Ghi cấu hình, phiên bản thư viện, số kết nối và số liệu đo thực tế để người khác có thể lặp lại.

## 11. Leasing không phải giới hạn concurrency

Leasing kiểm soát số request mới trong TTL. Nó không giới hạn trực tiếp số request đang chạy hoặc số stream đang mở.

Ví dụ server cấp 100 request trong một giây. Requester có thể tiêu thụ quota đó trong một đợt ngắn. Nếu mỗi request mất vài giây, nhiều request có thể vẫn đang chạy khi quota tiếp theo được cấp.

Vì vậy cần kết hợp:

- **Leasing:** giới hạn số interaction mới được khởi tạo.
- **Concurrency limit:** giới hạn số công việc đang thực thi.
- **Bounded queue:** giới hạn số công việc đang chờ.
- **Timeout/deadline:** giới hạn thời gian một request chiếm tài nguyên.
- **Bulkhead:** tách ngân sách cho các dependency hoặc nhóm nghiệp vụ.
- **Circuit breaker:** tạm ngừng gọi dependency đang lỗi hoặc quá tải.

Nếu dữ liệu là request-stream hoặc request-channel, cần thêm giới hạn số stream đang hoạt động và chính sách backpressure cho response item.

### Quota phải tính trên tổng số kết nối

Lease là hạn ngạch theo kết nối. Nếu server cấp 50 request/giây cho mỗi kết nối và có 100 kết nối, tổng ngân sách có thể lên đến 5.000 request/giây.

Không nên cấp cùng một quota cố định cho mọi kết nối nếu năng lực của server là ngân sách toàn cục. Hãy dùng bộ phân bổ quota có xét đến:

- Tổng số kết nối đang hoạt động.
- Số request đang thực thi.
- Độ sâu hàng đợi.
- CPU, bộ nhớ và trạng thái connection pool.
- Nhóm người dùng hoặc tenant.
- Mức ưu tiên của request.

Có thể giảm quota khi hệ thống bận và tăng lại khi tải giảm. Quy tắc phải có giới hạn an toàn để tránh việc nhiều kết nối cùng nhận quota lớn tại một thời điểm.

## 12. Hàng đợi chờ lease ở phía requester

Khi đã bật leasing, requester có thể nhận request từ ứng dụng trong lúc chưa có quota và đưa chúng vào hàng đợi chờ lease, tùy cấu hình và implementation.

RSocket Java cho phép giới hạn số request chờ bằng:

~~~java
RSocketConnector.create()
    .lease(spec ->
        spec.maxPendingRequests(128)
    );
~~~

Nếu hàng đợi đầy, request mới có thể thất bại thay vì chờ vô hạn. Cần quyết định rõ ứng dụng sẽ:

- Trả lỗi quá tải cho caller.
- Thử lại sau một khoảng chờ có giới hạn.
- Hạ tần suất tạo request.
- Bỏ request cũ nếu đó là cập nhật trạng thái có thể thay thế.
- Giữ request trong hàng đợi bền vững nếu nghiệp vụ yêu cầu không mất dữ liệu.

Không tăng maxPendingRequests chỉ để che một server thiếu năng lực. Hàng đợi lớn làm tăng thời gian chờ, bộ nhớ và nguy cơ request hết hạn trước khi được gửi.

## 13. Các tình huống cần kiểm thử thêm

Sau thử nghiệm cơ bản, kiểm tra các tình huống sau:

| Tình huống | Điều cần quan sát |
|---|---|
| Lease hết TTL trước khi có lease mới | Requester dừng gửi request mới cho đến khi có quota hợp lệ |
| Đã dùng hết số request trong lease | Request mới chờ hoặc thất bại theo chính sách requester |
| Lease mới đến trước khi lease cũ hết hạn | Giá trị lease mới thay thế lease cũ |
| Requester có hàng đợi đầy | Request mới không được xếp hàng vô hạn |
| Server phát lease bằng 0 request | Requester không có quota để khởi tạo request |
| Server giảm quota khi CPU cao | Tốc độ request mới giảm theo lease mới |
| Có nhiều kết nối | Tổng quota không vượt ngân sách toàn server |
| Request-stream kéo dài | Một lần khởi tạo tiêu thụ quota nhưng stream vẫn giữ tài nguyên |
| Client không còn nhu cầu | CANCEL giải phóng stream và công việc có thể dừng |
| Server không hỗ trợ leasing | Client yêu cầu lease phải nhận được kết quả setup phù hợp, không giả định kết nối đã sẵn sàng |

Nên kiểm thử cả trường hợp request bị từ chối bằng ERROR[REJECTED]. Đây là một hàng rào ở phía responder khi request đến mà không được lease cho phép.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Bật leasing là server tự động tính quota | Ứng dụng responder phải tạo và phát các Lease |
| Lease 100 request nghĩa là 100 request/giây | Chỉ khi TTL được đặt một giây; quota là số request trong TTL |
| Lease mới cộng thêm quota cũ | LEASE frame mới nhất thay thế giá trị lease trước |
| Lease giới hạn số response của Flux | Lease đếm interaction khởi tạo; response item được điều tiết bằng demand |
| Có lease thì không cần giới hạn concurrency | Request có thể được khởi tạo theo burst và chạy lâu |
| Quota trên một kết nối là quota toàn server | Mỗi kết nối có lease riêng; cần bộ phân bổ ngân sách toàn cục |
| Client queue càng lớn càng tốt | Queue lớn có thể làm tăng latency, bộ nhớ và request hết hạn |
| Không leasing nghĩa là không có backpressure | Backpressure theo stream vẫn hoạt động; chỉ thiếu quota cho request mới |

## 15. Quy trình triển khai leasing trong dịch vụ thực tế

1. Đo năng lực xử lý an toàn của dịch vụ với workload đại diện.
2. Xác định ngân sách request toàn cục và ngân sách dành cho từng kết nối/tenant.
3. Chọn TTL và số request mỗi lease dựa trên latency, burst và khả năng xử lý.
4. Bật leasing ở requester và responder; xác nhận SETUP có cờ L và server phát LEASE.
5. Giới hạn hàng đợi chờ lease ở client.
6. Giữ giới hạn concurrency, queue và timeout ở server.
7. Theo dõi lease được cấp, request đã dùng, pending, rejected và latency.
8. Thử tải với nhiều kết nối và nhiều loại interaction, không chỉ request-response.
9. Điều chỉnh quota dựa trên metric và kiểm tra lại khi năng lực dependency thay đổi.

Leasing là công cụ admission control hữu ích cho RSocket khi server cần điều tiết số interaction mới từ peer. Khi kết hợp với giới hạn concurrency, hàng đợi hữu hạn và metric phù hợp, dịch vụ có thể phản ứng có kiểm soát trước tải tăng thay vì để request dồn vào các tài nguyên phía server.

## Ghi nhớ

- Không leasing: requester có thể khởi tạo request sau SETUP mà không có quota theo thời gian.
- Leasing: responder cấp số request và TTL bằng LEASE frame; requester phải tuân thủ.
- Cờ L trong SETUP cho biết requester sẽ sử dụng leasing.
- LEASE áp dụng cho mọi loại interaction; một request-stream tiêu thụ một đơn vị quota khi được mở.
- LEASE frame mới nhất thay thế lease trước đó.
- maxPendingRequests giới hạn hàng đợi chờ lease ở requester, không phải quota server cấp.
- Leasing giới hạn request mới, còn backpressure điều tiết response item trong stream.
- Vẫn cần giới hạn concurrency, queue, timeout và quota toàn cục cho nhiều kết nối.

## Tài liệu tham khảo

- [RSocket Protocol — LEASE frame và Lease Semantics](https://rsocket.io/about/protocol/)
- [RSocket Java — RSocketServer 1.1.5](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java — RSocketConnector 1.1.5](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocket Java — LeaseSpec 1.1.5](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/LeaseSpec.html)
- [RSocket Java — Lease 1.1.5](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/lease/Lease.html)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)

