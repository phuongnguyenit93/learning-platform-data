# Độ trễ mạng, thời gian xử lý và ngân sách thời gian

Một request HTTP giữa hai microservice tiêu tốn thời gian ở nhiều nơi: client có thể phải chờ kết nối, dữ liệu phải đi qua mạng, server có thể phải chờ hàng đợi, xử lý nghiệp vụ và gọi tiếp dịch vụ khác. Nếu chỉ đặt một timeout lớn cho từng lần gọi mà không xét tổng thời gian của request, chuỗi microservice có thể phản hồi chậm hơn nhiều so với mức người dùng chấp nhận.

Khi thiết kế giao tiếp dịch vụ với Spring Cloud LoadBalancer, cần hiểu rõ **độ trễ mạng**, **thời gian xử lý** và **ngân sách thời gian**. Ba khái niệm này giúp xác định timeout phù hợp, giới hạn retry và tìm đúng nguyên nhân gây chậm.

## 1. Phân biệt độ trễ mạng và thời gian xử lý

**Độ trễ (latency)** là khoảng thời gian từ lúc một thao tác bắt đầu đến khi có kết quả. Trong giao tiếp HTTP, thời gian client quan sát được thường bao gồm nhiều thành phần chứ không chỉ thời gian server chạy code.

**Độ trễ mạng** là phần thời gian dữ liệu di chuyển qua mạng giữa client và server. Có thể chịu ảnh hưởng bởi khoảng cách địa lý, số chặng mạng, định tuyến, tải mạng, mất gói và việc truyền lại dữ liệu. Round-trip time (RTT) là thời gian một gói tin đi từ điểm gửi đến điểm nhận rồi quay về; RTT không bao gồm toàn bộ thời gian xử lý nghiệp vụ của HTTP server.

**Thời gian phía server** là khoảng từ lúc server tiếp nhận request đến khi gửi response. Trong khoảng này cần phân biệt thời gian chờ hàng đợi (queueing) và thời gian xử lý thực tế (processing). Phần xử lý có thể bao gồm:

- Chờ worker thread hoặc event loop có thể xử lý request.
- Xác thực, phân quyền và kiểm tra dữ liệu.
- Thực thi nghiệp vụ.
- Truy vấn database, cache hoặc gọi dịch vụ khác.
- Tạo response và ghi dữ liệu ra socket.

Vì vậy, một request có thể chậm dù mạng nhanh, chẳng hạn server phải chờ connection đến database. Ngược lại, server có thể xử lý nhanh nhưng client vẫn quan sát thấy response chậm do mạng, TLS hoặc thời gian chờ lấy kết nối.

### Latency, response time và throughput

Ba chỉ số thường xuất hiện trong quan sát hệ thống:

| Chỉ số | Ý nghĩa | Ví dụ |
|---|---|---|
| Latency | Thời gian một thao tác mất từ đầu đến cuối theo điểm đo đã chọn | Một HTTP call mất 280 ms |
| Response time | Thời gian từ lúc gửi request đến khi nhận được response theo góc nhìn client | Client gửi lúc 10:00:00.000 và nhận xong lúc 10:00:00.280 |
| Throughput | Số request hoàn thành trong một đơn vị thời gian | 800 request/giây |

Throughput cao không đồng nghĩa latency thấp. Một dịch vụ có thể xử lý nhiều request mỗi giây nhưng vẫn có một nhóm request phải chờ lâu trong hàng đợi. Ngược lại, một dịch vụ ít request có thể phản hồi nhanh nhưng throughput thấp do giới hạn tài nguyên.

Trong thực tế, cần ghi rõ điểm bắt đầu và kết thúc khi nói một request có latency bao nhiêu. Thời gian đo ở browser, API gateway, HTTP client và server có thể khác nhau vì mỗi nơi quan sát một phần khác nhau của luồng.

## 2. Một HTTP request tiêu tốn thời gian ở đâu?

Một lần gọi từ client đến server thường đi qua các giai đoạn sau:

1. Client chuẩn bị request và lấy kết nối từ connection pool.
2. Nếu cần, client phân giải tên host qua DNS hoặc thực hiện bước phân giải endpoint.
3. Nếu chưa có kết nối phù hợp, client thiết lập TCP connection và có thể thực hiện TLS handshake.
4. Client gửi request qua mạng.
5. Server tiếp nhận request; request có thể phải chờ trong hàng đợi.
6. Server thực hiện xử lý nghiệp vụ và các thao tác phụ thuộc.
7. Server gửi response qua mạng.
8. Client đọc body, giải mã dữ liệu và tiếp tục xử lý.

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant N as Network
    participant S as HTTP Server
    participant D as Database
    C->>C: Lấy connection / chuẩn bị request
    opt Kết nối mới
        C->>N: DNS, TCP connect, TLS handshake
        N-->>C: Kết nối sẵn sàng
    end
    C->>N: Gửi HTTP request
    N->>S: Request đến server
    S->>S: Chờ hàng đợi và xử lý
    S->>D: Truy vấn dữ liệu
    D-->>S: Trả dữ liệu
    S-->>N: HTTP response
    N-->>C: Response đến client
    C->>C: Đọc body và giải mã
~~~

Có thể mô hình hóa thời gian quan sát ở client như sau:

~~~text
T_request =
    T_pool_wait
  + T_name_resolution
  + T_connection_setup
  + T_request_transfer
  + T_server_queue
  + T_server_processing
  + T_response_transfer
  + T_client_decode
~~~

Đây là mô hình phân rã để phân tích. Không phải thành phần nào cũng xuất hiện trong mọi request:

- Khi tái sử dụng kết nối keep-alive, DNS, TCP connect và TLS handshake có thể không cần thực hiện lại.
- Một số HTTP client thực hiện DNS hoặc lấy kết nối theo cơ chế riêng.
- Server processing có thể chứa nhiều lời gọi downstream.
- Một số bước có thể chồng lấp; khi đó không được cộng thời gian của các bước song song như thể chúng chạy nối tiếp.

**Ping không đại diện cho HTTP latency.** Ping thường đo RTT bằng ICMP, trong khi HTTP request còn có thể phải chờ connection pool, thiết lập TLS, chờ server, truy vấn dữ liệu và đọc response body. Ping thấp là một tín hiệu hữu ích về mạng, nhưng không chứng minh API sẽ phản hồi nhanh.

## 3. Các yếu tố làm latency tăng

### Khoảng cách và đường đi mạng

Client và server càng xa nhau về địa lý hoặc qua nhiều chặng mạng thì thời gian truyền dữ liệu thường càng tăng. Định tuyến, firewall, NAT, proxy và service mesh cũng có thể thêm bước xử lý.

### Queueing và mức sử dụng tài nguyên

Khi request đến nhanh hơn khả năng xử lý, request phải chờ. Thời gian chờ này có thể tăng mạnh khi CPU, thread pool, connection pool hoặc database gần bão hòa.

Ví dụ, thời gian xử lý nghiệp vụ thực tế chỉ 40 ms nhưng request chờ worker thread 250 ms. Nếu chỉ đo thời gian trong hàm nghiệp vụ, hệ thống sẽ bỏ sót phần lớn độ trễ mà client cảm nhận.

### Connection pool và kết nối mới

HTTP client thường tái sử dụng kết nối để tránh thiết lập TCP/TLS cho mọi request. Tuy nhiên, khi pool cạn, client có thể phải chờ một kết nối được trả về. Nếu cấu hình pool quá nhỏ hoặc response body không được tiêu thụ/đóng đúng cách, thời gian chờ lấy kết nối sẽ tăng.

### Payload và xử lý dữ liệu

Request/response lớn làm tăng thời gian truyền và giải mã. Nén có thể giảm dữ liệu qua mạng nhưng lại tiêu tốn CPU. Cần đánh giá cả hai phía thay vì mặc định rằng nén luôn nhanh hơn.

### Downstream dependency

Một API có thể gọi database, cache và nhiều microservice khác. Chỉ một dependency chậm cũng có thể kéo dài response time của API cha. Nếu nhiều request đồng thời cùng chờ dependency đó, hàng đợi có thể lan truyền ngược lên các dịch vụ gọi nó.

## 4. Ngân sách thời gian và deadline

**Ngân sách thời gian (time budget)** là lượng thời gian tối đa mà một request được phép tiêu tốn để hoàn thành một mục tiêu. Ngân sách thường được xác định từ yêu cầu trải nghiệm người dùng hoặc SLO của API.

Ví dụ, API tìm thông tin đơn hàng phải trả kết quả trong tối đa 1.200 ms. Toàn bộ thời gian này là ngân sách của request, bao gồm xử lý ở API hiện tại và các lời gọi downstream cần thiết.

**Deadline** là mốc kết thúc của ngân sách. Khi deadline đã đến, request không còn đủ thời gian để tiếp tục chờ. Một hệ thống có thể biểu diễn deadline bằng thời điểm kết thúc hoặc bằng khoảng thời gian còn lại.

Cần phân biệt:

- **Timeout:** giới hạn chờ cho một thao tác hoặc một giai đoạn. Khi vượt quá giới hạn, client dừng chờ và báo lỗi timeout.
- **Deadline:** giới hạn thời gian cuối cùng của toàn bộ công việc. Các thao tác con phải dùng phần ngân sách còn lại.
- **Time budget:** tổng thời gian được phân bổ cho công việc, từ đó deadline và timeout của các bước được xác định.

Đặt timeout 1 giây cho ba lời gọi downstream nối tiếp không có nghĩa request cha sẽ hoàn thành trong 1 giây. Trong trường hợp xấu nhất, ba lần gọi có thể lần lượt tiêu tốn gần 3 giây, chưa kể xử lý cục bộ và retry.

### Phân bổ ngân sách cho các bước nối tiếp

Giả sử API có deadline 1.200 ms và thực hiện hai lời gọi downstream nối tiếp:

| Công đoạn | Ngân sách tối đa |
|---|---:|
| Xác thực và chuẩn bị request | 100 ms |
| Gọi Catalog Service | 350 ms |
| Gọi Inventory Service | 400 ms |
| Tổng hợp và serialize response | 150 ms |
| Dự phòng cho gateway, mạng và dao động | 200 ms |
| **Tổng** | **1.200 ms** |

Mỗi ngân sách gọi dịch vụ phải tính toàn bộ thời gian mà client chờ cho lời gọi đó: chờ connection pool, phân giải endpoint nếu có, kết nối, mạng, thời gian server xử lý, response và giải mã.

Nếu Catalog Service đã dùng 310 ms thay vì 350 ms, phần thời gian còn lại của request cha tăng thêm 40 ms. Khi bắt đầu gọi Inventory Service, client phải tính lại ngân sách còn lại và không được cấp cho lời gọi này nhiều hơn phần thời gian còn lại của deadline cha.

### Lời gọi song song

Nếu Catalog và Inventory được gọi song song, thời gian chờ tổng thể gần với thời gian của nhánh chậm nhất cộng phần xử lý trước/sau, thay vì tổng thời gian của cả hai nhánh:

~~~text
T_total ≈ T_prepare + max(T_catalog, T_inventory) + T_aggregate
~~~

Công thức này chỉ đúng khi hai lời gọi thực sự chạy đồng thời và không có phụ thuộc tuần tự giữa chúng. Chúng vẫn dùng chung deadline của request cha; một nhánh chậm không được phép kéo dài quá deadline chỉ vì nhánh còn lại đã hoàn tất.

## 5. Timeout ở các giai đoạn HTTP

Timeout cần được cấu hình theo từng loại thao tác và theo tổng deadline. Những loại thường gặp gồm:

| Loại timeout | Giới hạn điều gì? | Khi vượt giới hạn |
|---|---|---|
| Connection pool/acquire timeout | Thời gian chờ lấy kết nối khả dụng | Client không lấy được kết nối từ pool |
| DNS/name resolution timeout | Thời gian phân giải tên host | Client không xác định được địa chỉ |
| Connect timeout | Thời gian thiết lập kết nối TCP | Không kết nối được đến endpoint |
| TLS handshake timeout | Thời gian hoàn tất bắt tay TLS | Kết nối bảo mật không sẵn sàng |
| Response/read timeout | Thời gian chờ dữ liệu response theo semantics của HTTP client | Client ngừng chờ dữ liệu |
| Overall request timeout | Tổng thời gian cho một lần thực hiện request | Toàn bộ lần gọi bị giới hạn |

Tên gọi và ngữ nghĩa chính xác tùy thư viện HTTP client. Chẳng hạn, read timeout ở một client có thể là thời gian tối đa chờ dữ liệu tiếp theo, không nhất thiết là giới hạn tổng thời gian tải toàn bộ response body. Cần đọc tài liệu của implementation đang dùng để biết timeout đo từ thời điểm nào đến thời điểm nào.

Một cấu hình có connect timeout 200 ms và read timeout 500 ms vẫn có thể tiêu tốn hơn 700 ms nếu còn thời gian chờ connection pool, DNS, TLS, retry hoặc các bước khác. Vì vậy, timeout từng giai đoạn không thay thế overall timeout hay deadline.

### Timeout không đồng nghĩa server đã dừng xử lý

Khi client timeout, điều chắc chắn là client không tiếp tục chờ theo chính sách timeout đó. Không thể kết luận server đã dừng xử lý hoặc transaction đã rollback.

Ví dụ:

1. Client gửi yêu cầu tạo đơn hàng.
2. Server nhận và ghi đơn hàng vào database.
3. Response bị chậm trên mạng.
4. Client hết timeout và báo lỗi.
5. Người dùng thử lại, tạo ra yêu cầu thứ hai.

Nếu API không có cơ chế idempotency hoặc chống xử lý trùng, hệ thống có thể tạo hai đơn hàng. Vì thế, timeout phải được thiết kế cùng với cách xử lý retry và tính idempotent của thao tác.

## 6. Áp dụng time budget cho Spring Cloud LoadBalancer

Spring Cloud LoadBalancer giải quyết việc tìm và chọn một ServiceInstance cho service ID. Nó không tự bảo đảm instance được chọn sẽ phản hồi trong một khoảng thời gian nhất định.

Trong một lời gọi load-balanced, thời gian client quan sát có thể bao gồm:

- Thời gian lấy danh sách instance từ ServiceInstanceListSupplier.
- Thời gian lọc hoặc chọn instance theo cấu hình.
- Thời gian chờ connection pool và thiết lập kết nối của HTTP client.
- Thời gian mạng và xử lý ở server.
- Thời gian retry nếu chính sách retry được bật.

Nguồn instance có thể được cache hoặc truy vấn qua discovery tùy cấu hình và integration. Không nên giả định mỗi HTTP request luôn tạo một truy vấn mạng mới đến service registry; cũng không nên giả định chi phí discovery luôn bằng không.

### Timeout thuộc về HTTP client và toàn bộ lần gọi

Khi tích hợp RestClient, WebClient hoặc OpenFeign, timeout kết nối/response thường được cấu hình ở HTTP client hoặc request factory tương ứng. Cách cấu hình cụ thể phụ thuộc client implementation và phiên bản Spring đang dùng.

Cần xác định rõ ba giới hạn:

1. Timeout cho một lần thử gọi đến một instance.
2. Tổng thời gian cho toàn bộ lời gọi, bao gồm các lần retry và backoff.
3. Deadline của request cha, được chia sẻ với các lời gọi downstream khác.

Ví dụ, một API cha còn 600 ms ngân sách. Nó không nên bắt đầu một lời gọi downstream có timeout 1.000 ms, bởi lời gọi con có thể tiếp tục chờ sau khi request cha đã hết hạn. Timeout của lời gọi con phải nhỏ hơn hoặc bằng phần ngân sách cha còn lại sau khi trừ phần dự phòng cần thiết.

### Ví dụ tính ngân sách còn lại

Có thể dùng đồng hồ monotonic để đo thời gian trôi qua trong cùng một tiến trình. System.nanoTime() phù hợp cho phép đo khoảng thời gian vì không phụ thuộc vào việc đồng hồ hệ thống bị chỉnh giờ.

~~~java
import java.time.Duration;

final class RequestBudget {
    private final long deadlineNanos;

    RequestBudget(Duration budget) {
        this.deadlineNanos = System.nanoTime() + budget.toNanos();
    }

    Duration remaining() {
        long nanos = deadlineNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0, nanos));
    }

    boolean isExpired() {
        return remaining().isZero();
    }
}
~~~

Cách sử dụng:

~~~java
RequestBudget budget = new RequestBudget(Duration.ofMillis(1200));

// Sau khi xác thực và gọi Catalog Service:
Duration remaining = budget.remaining();

// Giữ lại 100 ms cho bước tổng hợp response và phần dự phòng.
Duration usable = remaining.minus(Duration.ofMillis(100));
if (usable.isZero() || usable.isNegative()) {
    throw new IllegalStateException("Không còn ngân sách cho lời gọi downstream");
}

// Timeout không vượt quá 400 ms hoặc phần ngân sách thực sự còn dùng được.
Duration phaseCap = Duration.ofMillis(400);
Duration inventoryTimeout = usable.compareTo(phaseCap) < 0
        ? usable
        : phaseCap;
~~~

Đây là ví dụ quản lý ngân sách trong một tiến trình. Khi truyền deadline qua nhiều máy, System.nanoTime() của các máy không thể so sánh trực tiếp vì mỗi máy có mốc monotonic riêng. Hệ thống cần truyền thời gian còn lại hoặc một deadline theo giao thức đã thống nhất; nếu dùng thời điểm tuyệt đối thì phải tính đến sai lệch đồng hồ giữa các máy.

Trong HTTP, header truyền deadline/remaining budget thường là quy ước riêng của hệ thống, không có một header chuẩn duy nhất được mọi HTTP client và server tự động hiểu. Các dịch vụ phải thống nhất cách tạo, kiểm tra và giảm ngân sách để tránh tin nhầm giá trị do client bên ngoài gửi vào.

## 7. Retry phải nằm trong ngân sách thời gian

Retry giúp tăng khả năng thành công khi lỗi có tính tạm thời, nhưng mỗi lần thử lại tiêu tốn thời gian và tài nguyên. Retry không giới hạn có thể làm hệ thống quá tải hơn khi một dependency đang gặp sự cố.

Tổng thời gian của một lời gọi có retry có thể mô hình hóa:

~~~text
T_call =
    T_attempt_1
  + T_backoff_1
  + T_attempt_2
  + ...
  + T_attempt_n
~~~

Trong đó mỗi attempt có thể gồm chọn instance, chờ kết nối, mạng và xử lý server. Tổng thời gian phải nhỏ hơn phần ngân sách còn lại của request cha.

Khi thiết kế retry:

- Chỉ retry lỗi có khả năng tạm thời, theo chính sách rõ ràng.
- Giới hạn số lần thử và tổng thời gian retry.
- Dùng backoff, thường kết hợp jitter, để tránh nhiều client retry cùng lúc.
- Chỉ retry thao tác an toàn hoặc có idempotency key/cơ chế chống trùng.
- Trừ thời gian backoff và các lần thử trước khỏi deadline còn lại.
- Tránh bật retry độc lập ở nhiều tầng mà không tính số lần thử nhân lên.

Ví dụ, nếu HTTP client có thể thử ba lần và một lớp phía trên cũng retry ba lần, một request logic có thể tạo ra tối đa chín lần gọi ở tầng dưới tùy cách các chính sách lồng nhau. Điều này làm tăng tải và kéo dài thời gian hoàn thành.

Với Spring Cloud LoadBalancer, retry có thể được cấu hình ở tầng LoadBalancer; HTTP client hoặc ứng dụng cũng có thể có chính sách retry riêng. Cần kiểm tra toàn bộ các tầng đang bật để biết chính xác số lần thử, instance có được chọn lại hay không và timeout áp dụng cho từng attempt hay toàn bộ chuỗi. Không nên suy luận một bộ timeout/retry mặc định chung cho mọi phiên bản và mọi HTTP client.

## 8. Đo lường để xác định phần thời gian bị tiêu tốn

Muốn tối ưu latency, trước hết phải đo đúng phần đang chậm. Chỉ ghi một dòng log “API mất 900 ms” thường chưa đủ để xác định nguyên nhân.

Nên quan sát ở cả client và server:

| Điểm đo | Thông tin cần thu thập |
|---|---|
| HTTP client | Tổng thời gian request, timeout, số lần retry, status code |
| Connection pool | Kết nối đang dùng, kết nối rảnh, thời gian chờ lấy kết nối |
| Discovery/LoadBalancer | Service ID, số instance ứng viên, instance được chọn, lỗi không tìm thấy instance |
| HTTP server | Thời gian chờ hàng đợi, thời gian xử lý, số request đang chạy |
| Database/downstream | Thời gian truy vấn và thời gian gọi dịch vụ phụ thuộc |
| Network/transport | DNS, connect, TLS, retransmission và lỗi kết nối nếu công cụ hỗ trợ |

Distributed tracing giúp liên kết một request qua nhiều microservice. Mỗi service tạo span cho phần xử lý của nó và các lời gọi downstream. Khi đọc trace, có thể thấy service nào tiêu tốn thời gian và liệu thời gian nằm ở xử lý nội bộ hay ở một lời gọi con.

Nên theo dõi phân vị latency:

- **p50:** một nửa request hoàn thành trong khoảng thời gian này hoặc nhanh hơn.
- **p95:** 95% request hoàn thành trong khoảng thời gian này hoặc nhanh hơn.
- **p99:** 99% request hoàn thành trong khoảng thời gian này hoặc nhanh hơn.

Trung bình có thể che khuất một nhóm request rất chậm. Với hệ thống microservices, p95 và p99 thường hữu ích khi đánh giá trải nghiệm ở tải cao hoặc khi một dependency có latency dao động.

Khi đo khoảng thời gian trong Java, dùng System.nanoTime() hoặc công cụ metrics/tracing phù hợp. Không dùng chênh lệch System.currentTimeMillis() làm phép đo chính xác cho elapsed time vì đồng hồ tường có thể thay đổi do đồng bộ thời gian hoặc thao tác quản trị.

## 9. Ví dụ phân tích một request chậm

Giả sử client gọi Order Service và tổng response time là 980 ms. Trace cho thấy:

| Thành phần | Thời gian |
|---|---:|
| Chờ connection pool | 20 ms |
| Kết nối và TLS | 40 ms |
| Mạng và truyền request/response | 70 ms |
| Chờ server queue | 180 ms |
| Xử lý nghiệp vụ tại Order Service | 90 ms |
| Gọi Inventory Service | 520 ms |
| Đọc và giải mã response | 60 ms |
| **Tổng** | **980 ms** |

Inventory Service chiếm 520 ms, là phần lớn nhất trong request. Tăng timeout của Order Service từ 1 giây lên 2 giây chỉ làm client chờ lâu hơn; nó không làm Inventory Service xử lý nhanh hơn.

Bước điều tra tiếp theo là mở trace của Inventory Service để phân rã 520 ms thành thời gian chờ pool, network, queue, database và xử lý. Nếu phần lớn thời gian nằm ở queue, cần kiểm tra tải và năng lực xử lý. Nếu nằm ở database, cần xem query, connection pool và lock. Nếu nằm ở network hoặc kết nối, cần kiểm tra đường truyền, DNS, TLS và pool.

Nếu deadline của API là 1.000 ms, request trên chỉ còn khoảng 20 ms dự phòng. Một biến động nhỏ cũng có thể khiến request timeout. Cần giảm phần latency gây nghẽn, phân bổ ngân sách rõ ràng và quyết định retry theo phần thời gian thực sự còn lại.

## 10. Những sai lầm thường gặp

| Sai lầm | Hậu quả |
|---|---|
| Đặt timeout dài giống nhau cho mọi downstream | Một dependency chậm có thể chiếm hết thời gian của request cha |
| Chỉ cấu hình connect timeout | Client vẫn có thể chờ response vô thời hạn hoặc quá lâu tùy HTTP client |
| Xem read timeout là tổng thời gian tải response | Một response truyền nhỏ giọt có thể vượt tổng thời gian mong muốn |
| Retry mọi lỗi | Tăng tải, tạo request trùng và làm cạn ngân sách |
| Không tính thời gian backoff | Tổng retry vượt deadline |
| Chỉ đo thời gian xử lý nghiệp vụ | Bỏ sót pool wait, queueing, mạng và TLS |
| Dùng ping để kết luận API nhanh | Bỏ qua HTTP, server processing và downstream |
| Cho rằng timeout đồng nghĩa server đã hủy thao tác | Có thể tạo dữ liệu trùng khi người dùng thử lại |
| Chỉ theo dõi latency trung bình | Không phát hiện nhóm request p95/p99 rất chậm |

## 11. Checklist thiết kế ngân sách thời gian

Khi một HTTP client gọi dịch vụ qua Spring Cloud LoadBalancer, hãy kiểm tra:

1. Đã xác định deadline end-to-end cho request từ yêu cầu nghiệp vụ hoặc SLO chưa?
2. Đã phân rã thời gian thành pool wait, kết nối, mạng, queue, xử lý server và đọc response chưa?
3. Timeout từng giai đoạn có phù hợp với semantics của HTTP client đang dùng không?
4. Mỗi downstream có nhận timeout dựa trên ngân sách còn lại của request cha không?
5. Tổng thời gian của các lần retry và backoff có nằm trong deadline không?
6. Các thao tác có thể retry đã an toàn trước xử lý trùng chưa?
7. Có trace/metrics để nhận biết service hoặc dependency nào đang chiếm thời gian không?
8. Đã theo dõi p95, p99, timeout rate, retry rate và thời gian chờ connection pool chưa?

Độ trễ mạng cho biết dữ liệu mất bao lâu để di chuyển; thời gian xử lý cho biết server mất bao lâu để tiếp nhận và thực hiện công việc; ngân sách thời gian đặt giới hạn cho toàn bộ request. Khi kết hợp ba khái niệm này, client có thể đặt timeout theo phần việc thực tế, giới hạn retry và giữ cho chuỗi giao tiếp microservice hoàn thành trong deadline đã cam kết.

