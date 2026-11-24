# Timeout cho mọi kết nối từ xa trong Spring Integration Adapters

> **Chương:** Production  
> **Chủ đề:** Timeout cho mọi kết nối từ xa  
> **Module:** Spring Integration Adapters  
> **Phạm vi:** Inbound/outbound adapter, gateway, poller và MessageChannel khi trao đổi dữ liệu qua File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC và các dịch vụ ngoài.

## 1. Mục tiêu và bài toán production

Sau bài học này, bạn có thể:

1. Phân biệt **connection timeout, pool acquisition timeout, TLS/SSH handshake timeout, read/write timeout, response/reply timeout, acknowledgement timeout, transaction timeout** và **deadline toàn luồng**.
2. Tìm đúng tầng cần đặt timeout trong luồng Spring Integration: adapter, client library, broker, database driver, gateway, poller hoặc scheduler.
3. Thiết kế **ngân sách thời gian** cho một giao dịch tích hợp, tương thích với SLA phía gửi và retry/backoff phía nhận.
4. Thiết lập timeout theo từng công nghệ HTTP, SFTP, JMS, AMQP, Kafka, JDBC; biết trường hợp File local không có remote connection timeout.
5. Tránh mất message và duplicate side effect khi một lệnh timeout nhưng hệ ngoài đã xử lý xong.
6. Giám sát timeout theo giai đoạn, kiểm thử mạng lỗi, backpressure, rolling deploy và đưa ra quyết định go/no-go dựa trên bằng chứng.
7. Lập runbook cho những kết nối treo, pool hết tài nguyên, timeout storm và sự cố gián đoạn downstream.

**Bối cảnh:** Hệ Spring Boot dùng Spring Integration nhận file qua SFTP, ghi DB, gọi HTTP API đối tác, phát Kafka event và vẫn có JMS/AMQP consumers. Khi SFTP không phản hồi, một số worker có thể mắc kẹt hàng phút. Khi HTTP client timeout, phía đối tác có thể đã tạo giao dịch. Khi DB pool cạn, request chờ connection lâu hơn SLA. Vì vậy, cấu hình một thuộc tính có tên **timeout** chưa đủ: phải kiểm soát toàn bộ các mốc chờ và hiểu tác động của việc hủy hoặc retry.

## 2. Timeout là ranh giới nào?

**Timeout** là giới hạn thời gian cho một công đoạn hoặc trạng thái chờ được định nghĩa. Nó không đồng nghĩa “hủy mọi xử lý ở đầu bên kia” và cũng không nhất thiết là **deadline từ đầu đến cuối**.

| Loại timeout | Đang chờ điều gì? | Nếu hết thời gian | Điểm đặt thường gặp |
|---|---|---|---|
| **DNS / name resolution** | Tra cứu hostname | Không có địa chỉ để kết nối | Resolver/OS/client, đôi khi khó đặt riêng |
| **Connection establishment** | Thiết lập socket TCP | Không kết nối được trong khoảng cho phép | HTTP/SFTP/broker client, JDBC driver |
| **TLS/SSH handshake** | Thỏa thuận phiên bảo mật và xác thực peer | Không lập được kênh an toàn | Client/transport, SSH/SFTP session |
| **Connection acquisition** | Chờ lấy connection từ pool | Pool quá tải, request chưa được gửi | HTTP connection manager, JDBC pool |
| **Socket read / inactivity** | Chờ dữ liệu đọc, thường là thời gian không có byte mới | Không nhận được dữ liệu kịp hạn | Socket/client/driver |
| **Write / send** | Chờ ghi bytes hoặc gửi request/broker record | Chưa rõ phía nhận đã nhận tới đâu | Client hoặc API có giới hạn ghi |
| **Response / request** | Chờ phản hồi cho một request | Caller hết thời gian chờ reply | HTTP gateway, request/reply messaging |
| **Message channel send** | Chờ giao message vào channel/buffer | Không bàn giao được theo deadline | Spring Integration channel/gateway |
| **Poll / receive** | Chờ lấy message/file/record từ nguồn | Có thể đơn giản là không có dữ liệu | Poller, JMS receive, Kafka poll |
| **Ack / commit** | Chờ xác nhận broker, offset hoặc transaction | Trạng thái giao nhận có thể mơ hồ | JMS/AMQP/Kafka/DB |
| **Transaction / query / lock** | Chờ truy vấn, khóa hoặc transaction | Rollback/exception theo cơ chế hỗ trợ | JDBC/DB/transaction manager |
| **Idle / lease / keepalive** | Đóng kết nối không hoạt động hoặc giữ phiên | Quản lý vòng đời kết nối | HTTP pool, broker, DB pool |
| **Whole-flow deadline** | Toàn bộ tiến trình từ tiếp nhận đến hoàn tất hợp đồng | Vi phạm SLA dù mỗi chặng chưa timeout | Logic ứng dụng, workflow và giám sát |

### 2.1. Những hiểu lầm thường thấy

- **Connect timeout** không thay cho **read timeout**: socket kết nối được nhưng server không trả response vẫn có thể chờ lâu.
- **Read timeout** ở nhiều client là khoảng chờ giữa các lần nhận dữ liệu, không phải tổng thời gian download. Một server gửi ít byte đều đặn có thể kéo dài tổng thời gian nếu không có overall deadline.
- **Pool acquisition timeout** khác connect timeout: chưa lấy được connection để bắt đầu kết nối.
- **Gateway reply timeout** không nhất thiết chặn được HTTP socket, broker client hoặc database query ở tầng thấp.
- **Poll interval** không giới hạn thời gian một lượt poll bị treo khi SFTP/DB chậm.
- **Heartbeat/keepalive** phát hiện hoặc hạn chế idle connection; không phải giới hạn mỗi nghiệp vụ.
- **Thread interruption / Future timeout** không bảo đảm phía remote đã hủy side effect.
- **Một API trả timeout** không nói được request đã được server xử lý hay chưa.

**Kết luận cốt lõi:** Timeout cần được đặt tại **đúng chặng có thể chờ**, còn flow-level deadline cần dựa trên tổng thời gian và kết quả nghiệp vụ.

### 2.2. Sơ đồ các điểm chờ

~~~mermaid
flowchart LR
    A["Inbound request / message"] --> Q["Channel queue / executor"]
    Q --> P["Pool acquisition"]
    P --> C["DNS + TCP connect"]
    C --> H["TLS / SSH handshake"]
    H --> W["Write request"]
    W --> R["Read response"]
    R --> D["DB transaction"]
    D --> O["Ack / outbound event"]
    A -. "Whole-flow deadline" .-> O
    C -. "Connect timeout" .-> FAIL["Retry / error path"]
    H -. "Handshake timeout" .-> FAIL
    R -. "Read/response timeout" .-> FAIL
    P -. "Pool wait timeout" .-> FAIL
    D -. "Query/transaction timeout" .-> FAIL
    O -. "Ack timeout" .-> FAIL
~~~

Không nhất thiết tất cả các chặng có mặt trong một adapter. File inbound thường không tạo remote socket, trong khi HTTP outbound cần DNS/connect/TLS/write/read; Kafka producer còn có queue nội bộ, metadata và broker acknowledgement.

## 3. Chọn ngân sách thời gian từ SLA của toàn luồng

Một hệ có nhiều timeout rời rạc có thể vẫn vượt SLA. Do đó nên bắt đầu từ mục tiêu nghiệp vụ:

- Bên gọi HTTP có thể chờ tối đa bao lâu?
- File SFTP phải được xử lý trước mốc nào?
- Kafka/JMS message có thể tồn đọng bao lâu?
- Sau khi DB bị lỗi tạm, hệ chấp nhận retry trong cùng request hay chuyển sang xử lý bất đồng bộ?
- Bao lâu được phép giữ một thread, một connection hoặc một transaction?

### 3.1. Ngân sách minh họa

Giả sử outbound HTTP gateway nằm trong request có deadline **25 giây**. Thiết kế ước tính:

| Khoản mục | Ngân sách dự kiến |
|---|---:|
| Queue/handoff trước xử lý | 2 giây |
| Validate/transform | 1 giây |
| Gọi HTTP đối tác: 2 attempts, mỗi attempt connect ≤ 2 s + response ≤ 4 s | 12 giây |
| Backoff giữa attempts | 1 giây |
| DB transaction và ghi kết quả | 4 giây |
| Dự phòng orchestration/serialization/network variance | 4 giây |
| **Tổng ngân sách xấp xỉ** | **24 giây** |

Các con số chỉ là **ví dụ**, không phải cấu hình tối ưu. Cần thống nhất semantics: response timeout có tính cả connect hay chỉ giai đoạn nhận response, TLS handshake có bị bao trùm không, DNS có thể kéo dài không, pool acquisition có nằm trong tổng không. Khi số mốc vượt budget, phải giảm attempts, giảm thời gian ở từng bước, tách bất đồng bộ hoặc điều chỉnh SLA bằng thỏa thuận rõ ràng.

Một công thức **ước tính bảo thủ** khi các chặng không chồng lấp:

\[
T_{\mathrm{flow}} \lesssim T_{\mathrm{queue}} + T_{\mathrm{validation}} + \sum_{i=1}^{N} \left(T_{\mathrm{pool},i} + T_{\mathrm{connect},i} + T_{\mathrm{request},i}\right) + \sum_{i=1}^{N-1} T_{\mathrm{backoff},i} + T_{\mathrm{DB}} + T_{\mathrm{reserve}}.
\]

Công thức này dùng để **lập kế hoạch ngân sách**, không phải cam kết thời gian thực tế: DNS, TLS, tải máy, timeout của client và thời gian cleanup có thể khác cách cộng trên. Một số timeout bao gồm nhau, không phải phép cộng độc lập.

### 3.2. Deadlines phải truyền theo thời gian còn lại

Ví dụ gateway nhận request lúc 10:00:00 với deadline 10:00:25. Sau 6 giây queue + validation, không được tiếp tục gọi đối tác với một client timeout cố định 25 giây nữa. Flow phải xét **remaining budget** tại mỗi bước.

~~~text
deadline = requestStart + totalAllowedDuration

beforeEachRemoteOperation:
    remaining = deadline - monotonicElapsedSinceStart
    if remaining <= minimumUsefulTime:
        failWithDeadlineExceeded()
    else:
        operationBudget = min(configuredPerAttemptTimeout, remaining - reserve)
        executeWithAppropriateClientTimeouts(operationBudget)
~~~

Đây là pseudo-code. Trong hệ thật, dùng đồng hồ monotonic cho đo **duration** để tránh ảnh hưởng điều chỉnh đồng hồ hệ thống, đồng thời lưu wall-clock timestamps cho audit. Không phải mọi API Spring Integration đều hỗ trợ truyền trực tiếp dynamic deadline xuống từng client; có thể cần wrapper/custom gateway hoặc tách execution path.

### 3.3. Đồng bộ hay bất đồng bộ?

Nếu SLA inbound HTTP là 10 giây nhưng một partner SFTP/HTTP có thể mất 30 giây để phản hồi, không nên giữ request chờ với timeout 60 giây rồi hy vọng. Có thể dùng hợp đồng **accept + tracking ID** để xử lý bất đồng bộ, lưu yêu cầu bền vững, trả kết quả khi hoàn thành và cung cấp kênh truy vấn trạng thái/callback.

Chuyển bất đồng bộ không làm mất nghĩa vụ đảm bảo message: vẫn cần deduplication, durable queue/outbox, retry, audit và giới hạn backlog.

## 4. Lập ma trận timeout theo từng kết nối

Thay vì viết chung “timeout = 30 s”, tạo ma trận dựa trên đường đi thật của ứng dụng.

| Endpoint/operation | Timeout cần xem xét | Owner cấu hình | Failure mode cần thử |
|---|---|---|---|
| SFTP inbound download | Connect, SSH handshake, session/operation, read stall, poll execution | Spring Integration SFTP + SSH client | Server không phản hồi giữa transfer |
| SFTP outbound upload | Connect, remote write, rename/ack, session | SFTP client + ứng dụng | Upload có thể thành công trước timeout |
| HTTP outbound gateway | Pool wait, connect, TLS, response/read, overall request | HTTP client/request factory | Server xử lý xong nhưng client timeout |
| HTTP inbound gateway | Proxy timeout, servlet thread, integration reply timeout | Web server/proxy + gateway | Client ngắt khi handler vẫn chạy |
| JMS request/reply | Connection/receive/reply timeout, broker failover | JMS provider + gateway | Reply trễ, request đã được xử lý |
| JMS listener | Broker/session/reconnect, receive wait, transaction/ack | JMS listener container/provider | Listener stuck hoặc redelivery |
| AMQP RPC / publish | Connect, handshake, RPC reply, publisher confirm, heartbeat | Rabbit client + adapter | Confirm timeout, publish ambiguous |
| Kafka producer | Metadata wait, max block, request, delivery, future wait | Kafka client + integration endpoint | Producer timeout trước broker ack |
| Kafka consumer | Poll wait, API request, heartbeat/session, max poll interval | Kafka client/listener | Consumer rebalance hoặc stuck processing |
| JDBC inbound/outbound | Pool wait, socket connect/read, query, lock, transaction | DataSource/driver/DB | DB pool cạn hoặc lock wait |
| File local | Không có remote socket mặc định; poll cadence, file-ready wait, I/O và filesystem | File adapter + host/filesystem | File chưa sẵn sàng hoặc NFS/SMB bị treo |

**Chú ý:** API thực tế có thể không cung cấp timeout cho tất cả các hàng. Chỗ nào client không hỗ trợ giới hạn cứng phải có biện pháp khác: isolation, watchdog, worker cancellation có kiểm chứng, deadline cấp tác vụ, circuit breaker hoặc cơ chế pause/recovery.

## 5. Kết hợp timeout với retry, circuit breaker và backpressure

### 5.1. Retry có thể vượt tổng ngân sách

Giả sử mỗi attempt có connect 5 s và read 10 s, retry 4 attempts và backoff 2 s, 4 s, 8 s. Worst-case ước tính có thể vượt **74 giây**, chưa tính DNS, queue, TLS, DB hoặc cleanup. Một request inbound có proxy timeout 30 s sẽ ngắt trong khi backend còn xử lý.

Checklist:

- [ ] Chỉ định một tầng **sở hữu retry chính** cho thao tác.
- [ ] Tính tổng attempts + backoff + mỗi timeout + reserve dưới deadline.
- [ ] Không retry vô hạn lỗi permanent như schema sai, 401/403, host key mismatch.
- [ ] 429/503/network có bounded exponential backoff và jitter khi phù hợp.
- [ ] Giảm số attempts nếu remaining budget không đủ.
- [ ] Có retry queue/durable handoff nếu không đủ thời gian xử lý trong request đồng bộ.
- [ ] Retry không làm duplicate side effect nếu downstream đã hoàn thành.
- [ ] Có metric về timeout stage, attempt count, exhausted retries và deadline exceeded.

**Retry storm:** nếu HTTP client retry 3 lần, retry advice 3 lần và broker redelivery 5 lần, tổng số lần gọi có thể tăng rất cao. Đừng chỉ xem cấu hình một lớp rồi kết luận tải đã được kiểm soát.

### 5.2. Timeout không thay thế circuit breaker

Timeout giúp kết thúc một lần chờ, còn circuit breaker có thể **ngừng gọi một dependency đang lỗi liên tục**; bulkhead giới hạn số worker/connection bị chiếm; rate limiter kiểm soát lượng gọi; backpressure giảm tốc độ nhận message.

Một bộ điều khiển có thể gồm:

- Connection/read timeout hữu hạn;
- Retry có giới hạn và backoff;
- Circuit breaker dựa trên timeout/error rate;
- Bulkhead theo semaphore/thread pool;
- Bounded queue cho MessageChannel;
- Throttling hoặc pause poller khi backlog tăng;
- DLQ/quarantine và operator replay cho poison message.

Không đưa một request đã timeout tới một error flow rồi đồng thời tự động retry ở nơi khác nếu chưa có owner/logic chống lặp.

### 5.3. Khi nào timeout được xem là kết quả mơ hồ?

Nếu gọi API **thực hiện side effect**, một timeout có thể xảy ra **trước khi gửi**, **trong lúc gửi**, **sau khi server commit**, hoặc **khi chờ response**.

~~~text
Client           Remote service
  | --- request ----> |
  |                   | commit business operation
  |     X response    |  (response bị mất)
  | timeout           |
  | --- retry? -----> |  (nguy cơ side effect lần 2)
~~~

Các biện pháp: idempotency key do hai phía thống nhất, tra cứu business state sau timeout, unique constraint, transactional outbox hoặc workflow bù trừ. **Timeout không phải bằng chứng lệnh chưa thực hiện**.

## 6. Tầng Spring Integration: endpoint, gateway, channel và poller

### 6.1. Inbound adapter và poller

Với File/SFTP/JDBC polling:

- **Poll cadence**: định kỳ lấy dữ liệu mới, không quyết định request network bị treo trong bao lâu.
- **Per-poll work budget**: giới hạn thời gian/batch xử lý mỗi lượt nếu thiết kế có watchdog hoặc vận hành tương đương.
- **Adapter/client timeouts**: giới hạn chờ remote session, request hoặc query.
- **Max messages per poll**: giới hạn lượng xử lý mỗi lượt, không tự đặt network timeout.
- **Scheduler/thread pool**: bảo đảm một nguồn chậm không chiếm hết worker; đo inflight và queue depth.
- **Retry/backoff**: xác định lỗi do source unavailable và cách re-fetch mà không bỏ sót dữ liệu.
- **Multi-replica**: distributed claim/filter và idempotency; timeout có thể làm lease hết hạn trong khi worker cũ vẫn xử lý.

**Tình huống cần test:** SFTP transfer chậm hơn poll interval. Hệ có lập thêm transfer song song không? Có thread nào bị block mãi? Nếu scheduler/pool hết worker, backlog và alert phản ánh ra sao?

### 6.2. MessageChannel và send timeout

| Thành phần | Timeout cần phân biệt | Điểm quan trọng |
|---|---|---|
| **DirectChannel** | Thời gian handler đồng bộ thực hiện | Channel không tự hủy downstream HTTP/DB đang chờ |
| **ExecutorChannel** | Thời gian chờ executor nhận task, queue saturation | Transaction/thread context và cancellation có giới hạn |
| **QueueChannel** | Thời gian offer/poll message và capacity | In-memory queue không mặc định durable |
| **Messaging gateway** | Request timeout khi gửi, reply timeout khi chờ phản hồi (tùy API/cấu hình) | Không thay thế connect/read timeout của remote client |
| **PublishSubscribeChannel** | Thời gian fan-out qua subscribers | Async và sync có failure/latency khác nhau |

Một `sendTimeout` có thể chỉ giới hạn thời gian **đưa message vào channel** (khi channel có thể block); nó không đặt deadline cho mọi bước downstream. Tương tự, `replyTimeout` ở messaging gateway là giới hạn **đợi reply message**, không tự buộc HTTP/JMS request hoặc DB query bị hủy.

### 6.3. Inbound gateway khi caller đã timeout

Với HTTP inbound gateway:

1. Proxy/client có thể đóng request khi hết thời gian chờ.
2. Handler trong ứng dụng có thể vẫn tiếp tục xử lý.
3. Nếu handler có side effect, client có thể retry vì không nhận response.
4. Muốn không nhân đôi tác động, dùng stable idempotency key và trạng thái durable.
5. Nếu cần xử lý dài, cân nhắc accept + tracking ID thay cho chờ đồng bộ.

Đây là lý do cần thống nhất timeout **bên ngoài service** (load balancer, proxy, client) với timeout **trong service**.

## 7. Cách cấu hình theo lớp và kiểm thử giá trị thực

Một cấu hình tốt ghi rõ **đơn vị và ý nghĩa**, tránh nhóm tất cả trong một khóa `timeout`.

~~~yaml
# Cấu hình MINH HỌA do ứng dụng tự định nghĩa.
# Không phải các property được Spring Integration tự bind.
app:
  integration:
    deadlines:
      http-ingress: 25s
      order-processing: 20s
    http-client:
      pool-acquire: 1s
      connect: 2s
      response: 4s
    sftp:
      connect: 5s
      handshake: 5s
      operation: 30s
    jdbc:
      pool-acquire: 2s
      query: 8s
    messaging:
      reply: 10s
    retry:
      max-attempts: 2
      initial-backoff: 1s
      max-backoff: 3s
~~~

Các giá trị chỉ là **đề xuất minh họa cho một luồng cụ thể**, không có ý nghĩa mặc định cho mọi kết nối. Trong code phải bind/validate properties, chọn client hỗ trợ các giới hạn, rồi test hiệu lực trên network faults. Một số client có timer riêng và không thể map trực tiếp từng property sang từng API.

### 7.1. Kiểm tra 0, âm và thời gian rất lớn

Các thư viện có thể hiểu **0** là “vô hạn”, “không chờ”, “tắt timeout” hoặc “dùng mặc định”; số âm cũng không nhất quán. Vì vậy:

- [ ] Đọc semantics **đúng method và phiên bản** cho mọi giá trị 0/âm/null.
- [ ] Với remote I/O quan trọng, tránh cấu hình chờ vô hạn trừ khi có lý do và control khác.
- [ ] Validate Duration, đơn vị ms/s và conversion sang integer để tránh overflow.
- [ ] Không đặt mọi timeout cùng 30 giây nếu proxy trả lỗi lúc 20 giây.
- [ ] Không đặt retry/backoff khiến tổng duration vượt shutdown grace period hoặc SLA.
- [ ] Không chọn timeout quá ngắn khiến slow-but-healthy network liên tục bị cắt.
- [ ] Có overrides theo môi trường, dependency và operation; mọi thay đổi phải review.

### 7.2. Java example cho HTTP client

Một ví dụ Spring Framework dùng `RestTemplate` và request factory đơn giản:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Configuration
class PartnerHttpClientConfig {

    @Bean
    RestTemplate partnerRestTemplate() {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(2_000); // mili-giây
        factory.setReadTimeout(4_000);    // mili-giây
        return new RestTemplate(factory);
    }
}
~~~

Đây là ví dụ **tập trung vào connect/read timeout** và cần kiểm tra API khi nâng phiên bản Spring Framework. `SimpleClientHttpRequestFactory` không minh họa pool acquisition và overall deadline của một client có connection pool. Với HTTP throughput lớn, thường cần một HTTP client có pooling và các timeout tương ứng, rồi cấu hình gateway Spring Integration sử dụng client/request factory đã review.

**Đừng** chỉ đặt `replyTimeout` ở integration gateway rồi kết luận lệnh HTTP có timeout mạng: đây là các tầng khác nhau.

## 8. Nguyên tắc bảo mật và tính sẵn sàng

Timeout giúp giới hạn tài nguyên bị chiếm, nhưng không được làm yếu authentication, TLS hoặc kiểm soát luồng:

- [ ] Kiểm tra chứng thư TLS/hostname/CA chain; không tắt verification khi handshake chậm.
- [ ] Với SFTP, xác minh SSH host key; không bỏ qua known-hosts để tránh timeout.
- [ ] Credential được lưu trong secret manager, có rotation và owner.
- [ ] Retry sau 401/403/certificate mismatch phải theo policy thay vì gọi nóng liên tục.
- [ ] Dùng connection/session pool với capacity phù hợp; một dependency lỗi không chiếm hết worker.
- [ ] Có throttle/backpressure để tránh gây quá tải phía ngoài khi remote bắt đầu hồi phục.
- [ ] Log/trace chỉ lưu endpoint, stage, elapsed, business ID, không chứa Authorization, private key, raw token hoặc PII không cần thiết.
- [ ] Khi timeout giữ lại file/queue/message trạng thái mơ hồ, có idempotency và replay audit.
- [ ] Cảnh báo phân biệt lỗi hạ tầng/tạm thời với xác thực/ủy quyền hoặc lỗi dữ liệu vĩnh viễn.

**Tiêu chí:** Một kết nối hết timeout phải trở thành trạng thái **có thể quan sát, xử lý và phục hồi**, chứ không phải một thread treo hoặc message biến mất.

## 9. SFTP: timeout của kết nối khác timeout thao tác từ xa

SFTP chạy qua SSH. Một lượt truyền file có nhiều bước: DNS → TCP connect → SSH handshake → authentication → mở subsystem/session → list/stat → read/write → rename/close. **Không có một timeout duy nhất mặc nhiên bao phủ toàn bộ các bước này.**

| Giai đoạn | Kiểm tra thời gian chờ | Rủi ro |
|---|---|---|
| TCP connect | Connect timeout và DNS resolver theo client | Host không reachable, SYN bị drop |
| SSH handshake | Handshake/authentication/session timeout | Kết nối TCP có nhưng SSH không hoàn tất |
| Remote list/stat | Operation timeout | Server treo khi liệt kê thư mục |
| Download/upload | Stall/read/write timeout, total transfer budget | Kết nối còn sống nhưng không tiến triển |
| Rename/close | Operation/confirmation timeout | File có thể hoàn tất dù client báo timeout |
| Session reuse | Pool checkout, idle eviction, keepalive | Session cũ đã chết hoặc bị giữ quá lâu |

Spring Integration SFTP có session factory và underlying SSH client tùy phiên bản. **Phải đọc API của version thực tế** để cấu hình từng timeout; không gán nhầm tùy chọn SSH session với thời gian của một `IntegrationFlow`.

### 9.1. Checklist inbound

- [ ] Có connect, SSH handshake và remote operation timeout hữu hạn theo khả năng client.
- [ ] Không dùng poll interval để thay network timeout.
- [ ] Producer có quy ước `.tmp` → rename hoặc ready marker để không đọc file dở.
- [ ] Giới hạn file size, session count, transfer concurrency và không dùng bộ nhớ vô hạn.
- [ ] Có metric tiến độ/tốc độ byte, thời gian không tiến triển và oldest pending file.
- [ ] Host-key verification được bật; known-hosts có owner và rotation procedure.
- [ ] Có persistent metadata/filter và business idempotency; “downloaded” không đồng nghĩa “processed”.
- [ ] Khi nhiều pod poll cùng nguồn, dùng distributed claim hoặc phân vùng hợp lệ.
- [ ] Nếu transfer timeout, có thể retry an toàn mà không đánh dấu file DONE quá sớm.
- [ ] Thử TCP blackhole, handshake stall, list/stat treo, transfer đứt và server đóng session.

### 9.2. Checklist outbound

- [ ] Có connect/operation/transfer timeout được kiểm thử bằng server thật.
- [ ] Upload bằng tên tạm rồi rename/mark ready theo hợp đồng.
- [ ] Khi rename/close response timeout, kiểm tra remote state thay vì upload lại mù.
- [ ] Có unique filename/version/checksum/manifest để đối soát.
- [ ] Không xóa local source trước khi remote handoff được xác minh.
- [ ] Retry không ghi đè file khác người hoặc tạo tác động nghiệp vụ trùng.
- [ ] Không giả định atomic rename như nhau trên mọi server/filesystem.

**Failure drill:** Máy chủ đã ghi đủ file nhưng client bị mất response ở bước rename. Hệ cần tra cứu remote path/checksum và quyết định hoàn tất hay retry idempotent, không tự tạo một file thứ hai.

## 10. HTTP: nhiều tầng timeout trong cùng một request

### 10.1. HTTP outbound gateway

| Giai đoạn | Timeout | Vì sao cần tách |
|---|---|---|
| Chờ pooled connection | Pool acquisition | Chưa gửi request, connect timeout không bao phủ |
| DNS/TCP | Resolver/connect | Hostname hoặc socket không thiết lập |
| TLS | Handshake/transport | TCP đã mở nhưng TLS có thể treo |
| Request body | Write/streaming budget | Upload lớn khi remote đọc chậm |
| Response headers/body | Response/read timeout | Server chậm trả hoặc stream kéo dài |
| Toàn request | Overall deadline nếu client hỗ trợ | Read timeout có thể chỉ giới hạn idle interval |
| Messaging gateway | Reply timeout của Spring Integration | Không tự cancel HTTP socket |

### 10.2. Checklist HTTP outbound

- [ ] Xác định client thật: RestTemplate, RestClient, WebClient hoặc custom HTTP library.
- [ ] Pool acquisition/connect/response timeout được cấu hình đúng factory/client.
- [ ] Nếu client hỗ trợ overall request timeout, dùng bổ sung cùng flow deadline.
- [ ] Tổng attempts + backoff nằm trong SLA caller; không làm proxy timeout trước handler.
- [ ] Retry chỉ cho lỗi có thể retry; 401/403/certificate mismatch không retry nóng.
- [ ] POST/PUT có idempotency key phía đối tác hoặc API tra cứu trạng thái khi timeout.
- [ ] Có connection pool size, bulkhead/rate limit và circuit breaker khi cần.
- [ ] Giới hạn kích thước request/response và thời gian streaming.
- [ ] Test TCP blackhole, TLS stall, 429, 503, slow headers/body, timeout sau server commit.

### 10.3. HTTP inbound gateway

- [ ] SLA và timeout của client, reverse proxy, gateway, servlet container khớp với ngân sách.
- [ ] Request/reply có response/error contract và deadline theo policy.
- [ ] Giới hạn request size, concurrent requests và thread pool.
- [ ] Khi client disconnect, backend có thể **vẫn thực hiện side effect**; cần idempotency.
- [ ] Nếu xử lý lâu, dùng durable handoff + tracking ID thay vì giữ request đồng bộ.
- [ ] Không log Authorization, session cookie, raw payload nhạy cảm.
- [ ] Có test duplicate POST sau gateway 504 và late response.

~~~text
T=0s   Client gửi POST /payments
T=2s   IntegrationFlow gọi đối tác
T=10s  Đối tác commit thanh toán
T=12s  Response bị mất trên đường về
T=13s  Client báo timeout
T=14s  Client thử lại cùng request
~~~

**Timeout không chứng minh chưa xử lý:** nếu không có stable idempotency key, có thể phát sinh hai khoản thanh toán.

## 11. JMS: receive wait, RPC reply và broker recovery

JMS cần cấu hình theo **JMS provider** và container đang dùng, không có một timeout chung áp dụng mọi broker.

| Giai đoạn | Giới hạn thời gian | Điểm cần nhớ |
|---|---|---|
| Broker connect/TLS | Connection timeout, failover/reconnect | Provider-specific |
| Pull `receive(timeout)` | Receive wait | Hết thời gian có thể chỉ nghĩa queue chưa có message |
| Listener container | Poll/recovery/backoff | Không tự giới hạn business handler |
| JMS request/reply | Gateway reply timeout | Request có thể đã được consumer xử lý |
| Session transaction/ack | Provider commit/ack | Trạng thái mơ hồ khi connection bị mất |
| Late reply | Correlation/reply destination cleanup | Reply có thể đến sau khi caller bỏ cuộc |

**`JmsTemplate.receiveTimeout`** liên quan thao tác nhận theo `JmsTemplate`, không phải giới hạn toàn flow hoặc thời gian service activator xử lý.

### 11.1. Checklist JMS

- [ ] Broker connection, authentication, TLS, recovery/backoff được thử khi outage.
- [ ] Receive timeout và gateway reply timeout không bị nhầm.
- [ ] Session transacted/acknowledgement mode được ghi rõ.
- [ ] Request/reply có correlation, late-reply policy và xử lý caller timeout.
- [ ] Consumer có business idempotency khi message được redeliver.
- [ ] Retry và DLQ của broker có giới hạn, không giữ poison message vô hạn.
- [ ] Có metric oldest queue age, DLQ, redelivery, connection và handler duration.
- [ ] Test broker restart, reply đến muộn, listener chết sau DB commit nhưng trước ack.

**Cảnh báo:** RPC gateway hết thời gian chờ reply không có nghĩa bên nhận chưa làm việc. Nếu retry, gửi **cùng business request identity** để chống tác động lặp.

## 12. AMQP / RabbitMQ: confirm timeout không đồng nghĩa publish thất bại

Với Spring AMQP cần phân biệt TCP/TLS connect, heartbeat, request/reply gateway, publisher confirms và consumer acknowledgement.

| Timeout / liveness | Dùng để làm gì? | Không thay thế |
|---|---|---|
| Connection timeout | Giới hạn lập socket/broker connection | Publisher confirm deadline |
| Heartbeat | Phát hiện kết nối bị hỏng theo nhịp broker | Per-message processing timeout |
| RPC reply timeout | Chờ reply cho một request AMQP | Bằng chứng consumer chưa xử lý |
| Publisher confirm wait | Chờ broker xác nhận publish | Kiểm chứng business side effect downstream |
| Consumer ack/failure policy | Điều khiển redelivery | Idempotency nghiệp vụ |
| Reconnect backoff | Tránh storm sau broker outage | Overall flow deadline |

### 12.1. Checklist AMQP

- [ ] Exchange, queue, binding, routing key tồn tại đúng môi trường.
- [ ] TCP/TLS, heartbeat, recovery và connection timeout đã test.
- [ ] RPC reply timeout có late-reply handling và correlation đúng.
- [ ] Publisher confirm/return có cách ghi nhận unknown outcome khi timeout.
- [ ] Consumer ack/prefetch/concurrency không làm message tồn ở unacked quá lâu.
- [ ] Poison message có bounded retry, DLX/DLQ hoặc quarantine thích hợp.
- [ ] Producer/consumer idempotent khi message bị gửi lại.
- [ ] Có metric ready/unacked, confirmation latency, reconnect và DLQ.
- [ ] Test broker nhận publish nhưng mất confirm; retry không tạo double business effect.

**Điểm then chốt:** Heartbeat giúp đánh giá sức khỏe kết nối, nhưng không phải đồng hồ timeout cho từng message. Publisher confirm timeout là **kết quả chưa rõ** về broker receipt.

## 13. Kafka: producer delivery timeout, poll và consumer liveness

Các tên thuộc tính sau thuộc Apache Kafka client, cần xác minh semantics theo phiên bản đang triển khai.

### 13.1. Kafka producer

| Property | Công dụng | Không nên suy diễn |
|---|---|---|
| `request.timeout.ms` | Chờ broker trả response cho một request | Không phải whole-flow SLA |
| `delivery.timeout.ms` | Giới hạn tổng thời gian delivery theo producer semantics | Không bao gồm HTTP/DB bên ngoài Kafka |
| `max.block.ms` | Giới hạn block khi producer chờ metadata hoặc buffer cho một số lời gọi | Không phải thời gian record đã enqueue được ack |
| `linger.ms` | Chờ gom batch trước gửi | Không phải failure timeout |
| `retry.backoff.ms` | Backoff giữa các retry phù hợp | Không thay application deadline |
| `Future.get(timeout)` | Giới hạn caller chờ future | Không chắc ngăn record tiếp tục gửi |

`delivery.timeout.ms` phải tuân quan hệ ràng buộc với `request.timeout.ms + linger.ms` của Kafka producer. Những thông số dưới đây **chỉ để minh họa**, không phải tuning áp dụng mọi hệ:

~~~properties
request.timeout.ms=10000
delivery.timeout.ms=30000
max.block.ms=5000
linger.ms=5
retry.backoff.ms=500
enable.idempotence=true
acks=all
~~~

Producer idempotence/transaction của Kafka không thay business idempotency ở DB hoặc HTTP. Nếu application hết thời gian đợi `Future.get`, record có thể vẫn được gửi và được broker nhận sau đó.

### 13.2. Kafka consumer

| Property / hành vi | Ý nghĩa chính | Không đồng nghĩa |
|---|---|---|
| `poll(Duration)` | Chờ lấy record một lần | Deadline xử lý business handler |
| `default.api.timeout.ms` | Default timeout cho một số API đồng bộ consumer | Network timeout toàn ứng dụng |
| `session.timeout.ms` | Phát hiện thành viên consumer group mất liên lạc | Thời gian tối đa của handler |
| `heartbeat.interval.ms` | Nhịp heartbeat theo cấu hình group | Broker publish timeout |
| `max.poll.interval.ms` | Thời gian tối đa giữa các lần poll hợp lệ của group | Socket read timeout |
| Offset commit timeout | Chờ xác nhận commit theo API/client | Bảo đảm DB không tạo duplicate |

### 13.3. Checklist Kafka

- [ ] Producer request/delivery/max-block timeouts tương thích retry, SLO và bộ nhớ buffer.
- [ ] Không coi future timeout là “record chắc chắn chưa vào topic”.
- [ ] Consumer group/offset và max-poll interval phù hợp thời gian xử lý batch.
- [ ] Record lỗi có DLT/recovery đúng policy ordering theo partition/business key.
- [ ] Consumer cập nhật DB có unique business key/idempotency.
- [ ] Có metric delivery latency, buffer wait, consumer lag, rebalance, commit error.
- [ ] Đã thử Kafka broker blackhole, metadata unavailable, ack lost, consumer rebalance.
- [ ] Khi tăng concurrency/partition, ordering và retry semantics vẫn được bảo toàn.

Ví dụ: consumer commit DB xong rồi bị kill trước offset commit. Khi Kafka phát lại record, business idempotency phải chặn insert trùng. Thay đổi `request.timeout.ms` không giải quyết cửa sổ đó.

## 14. JDBC: phải tách pool, socket, query, lock và transaction

| Loại timeout | Cấp cấu hình | Ý nghĩa |
|---|---|---|
| Pool acquisition | HikariCP `connectionTimeout` | Chờ mượn connection từ pool |
| Connection validation | HikariCP `validationTimeout` | Kiểm tra connection còn sống |
| Socket connect/read | JDBC driver/DataSource | Kết nối DB và chờ network I/O |
| Statement/query | JDBC `Statement.setQueryTimeout`, `JdbcTemplate.setQueryTimeout` | Giới hạn query theo driver |
| Lock wait | Cấu hình DB/transaction/session | Chờ row/table lock |
| Transaction timeout | Spring transaction manager / DB | Giới hạn transaction theo cơ chế hỗ trợ |
| Pool idle/max lifetime | HikariCP `idleTimeout`, `maxLifetime` | Vòng đời connection, không giới hạn query |

**Quan trọng:** HikariCP `connectionTimeout` chủ yếu giới hạn **chờ lấy connection từ pool**, không phải tổng thời gian chạy SQL. `maxLifetime` không phải query timeout và không dùng để cắt một truy vấn chậm.

### 14.1. Ví dụ query timeout

~~~java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;

JdbcTemplate jdbc = new JdbcTemplate(dataSource);
jdbc.setQueryTimeout(8); // giây, hiệu lực phụ thuộc JDBC driver
~~~

Đoạn này minh họa statement timeout ở JdbcTemplate; không bao gồm pool acquisition, socket read hoặc lock wait phía database. Tên cấu hình lock/statement server-side tùy PostgreSQL, MySQL, SQL Server hoặc engine khác.

### 14.2. Checklist JDBC

- [ ] Pool wait timeout tương thích thread pool, số connection và lưu lượng.
- [ ] Driver connect/socket timeout được cấu hình và test bằng network fault.
- [ ] Query/lock/transaction timeout có quan hệ rõ với SLA và giới hạn batch.
- [ ] Truy vấn có index, pagination, query plan; không bù query chậm bằng timeout vô hạn.
- [ ] Không giữ transaction/lock khi gọi remote HTTP/SFTP chậm nếu không cần.
- [ ] JDBC poller nhiều replica có row claim/lease và recovery khi worker timeout.
- [ ] Có unique constraint/idempotency khi transaction outcome ambiguous.
- [ ] Có metrics active/idle/pending pool, slow query, lock wait, timeout/rollback.
- [ ] Test DB failover, lock contention, pool starvation và network loss lúc commit.

Nếu client mất kết nối lúc commit, cần đối soát trạng thái nghiệp vụ trước khi retry. Đừng giả định mọi timeout trong database đều chắc chắn đã rollback.

## 15. File adapter và network filesystem

File adapter đọc/ghi filesystem bằng API cục bộ, vì vậy thông thường **không có TCP remote connection timeout** như SFTP/HTTP. Tuy nhiên, NFS/SMB và các volume từ xa vẫn có thể block I/O do mạng hoặc filesystem.

- [ ] File-ready protocol và thời gian chờ file hoàn tất được xác định.
- [ ] Poll interval, batch size, maximum file size và processing duration có giới hạn.
- [ ] Nếu dùng network mount, kiểm thử server biến mất khi file đang mở/đang ghi.
- [ ] Java Future timeout/thread interruption **không bảo đảm** cắt được I/O ở kernel hoặc remote filesystem.
- [ ] Có metadata/claim/filter và retry sau crash; không đánh dấu DONE quá sớm.
- [ ] Không xóa/move file trước khi business commit và recovery obligation được đáp ứng.
- [ ] Có oldest pending file age, stalled file progress và disk/inode alerts.
- [ ] Nhiều pod dùng shared volume phải có distributed claim/partition và idempotency.

Với file outbound, nếu lỗi xuất hiện sau khi bytes đã ghi, kiểm tra target file/checksum/manifest trước khi ghi lại. Rename có thể không có semantics atomic giống nhau trên mọi filesystem.

## 16. Tóm tắt timeout cần review theo công nghệ

| Công nghệ | Tầng chờ phải xem | Tránh nhầm |
|---|---|---|
| **File** | File readiness, poll, filesystem, total operation | Connect timeout kiểu TCP |
| **SFTP** | TCP, SSH handshake, session, list/read/write, transfer deadline | Poll interval, heartbeat |
| **HTTP** | Pool, connect/TLS, request write, response, gateway reply | `replyTimeout` là toàn bộ remote request |
| **JMS** | Broker connection, receive, RPC reply, transaction/ack, failover | Receive wait là handler deadline |
| **AMQP** | TCP/TLS, heartbeat, RPC reply, publisher confirm, ack | Heartbeat là publish timeout |
| **Kafka producer** | Max block, request, delivery, future wait | Future timeout nghĩa broker chưa nhận |
| **Kafka consumer** | Poll wait, API, heartbeat/session, max poll interval, commit | Poll timeout là business processing timeout |
| **JDBC** | Pool acquire, connect/read, query, lock, transaction | Pool maxLifetime là query timeout |

Đối với **mỗi remote call**, tài liệu cần ghi: endpoint owner, client thực tế, timeout + đơn vị, retry owner, deadline còn lại, side-effect/ack boundary, ambiguous-outcome handling, alert, runbook và rollback trigger.

## 17. Startup, graceful shutdown và scaling khi remote chậm

### 17.1. Khởi động/readiness

- [ ] Config và secret bắt buộc được validate trước khi nhận traffic.
- [ ] Readiness và liveness có mục đích khác nhau, không restart pod vô hạn vì broker tạm lỗi.
- [ ] Reconnect backoff có jitter giúp tránh nhiều replica cùng kết nối lại dồn dập.
- [ ] Certificate/host key/auth failure không bị che bằng retry dài vô hạn.
- [ ] Có khả năng pause poller/listener và mở lại sau incident theo runbook.

### 17.2. Dừng/rolling deploy

- [ ] Ngừng nhận message mới khi shutdown theo endpoint lifecycle.
- [ ] Inflight hoàn thành hoặc có đường replay/ack an toàn trong grace period.
- [ ] Remote call có timeout để không chiếm worker mãi; test hung socket.
- [ ] Không ack nguồn trước khi side effect đạt hợp đồng.
- [ ] Rollback version có cơ chế đối soát outbound side effect đã xảy ra.
- [ ] Nhiều pod không cạnh tranh claim cùng file/row ngoài thiết kế.

### 17.3. Capacity và pool saturation

Ví dụ HTTP connection pool có 20 connection trong khi 300 worker đồng thời gọi API. Phần lớn worker có thể kẹt ở **pool acquisition** dù connect timeout là 2 giây. Tăng connect timeout không giải quyết cạn pool. Cần phối hợp bounded executor, pool sizing, rate limit, circuit breaker, backpressure và alert để bảo vệ cả ứng dụng lẫn remote server.

**Kết luận phần công nghệ:** Không chọn timeout theo tên property, hãy chọn theo **đúng trạng thái chờ mà giao thức/client tạo ra** và kiểm thử trực tiếp trạng thái đó.

## 18. Observability: biết chính xác timeout ở giai đoạn nào

Một dashboard chỉ có tổng số “timeout errors” thường không đủ để xác định lỗi thuộc DNS, pool, broker, remote server hay database.

### 18.1. Trường log bắt buộc

| Trường | Mục đích |
|---|---|
| `correlationId`, `eventId`, business key | Kết nối các attempt và side effect của một request |
| `adapterType`, endpoint ID | Nhận diện File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC |
| `remoteHost`/target alias | Xác định dependency mà không lộ credential |
| `stage` | DNS, pool-acquire, connect, handshake, write, read, reply, ack, query |
| `timeoutConfiguredMs` | Biết ngưỡng nào thực sự được áp |
| `elapsedMs`, `remainingDeadlineMs` | Phân biệt một bước chậm với hết ngân sách toàn flow |
| `attempt`, `retryDelayMs` | Theo dõi retry storm và budget |
| `outcome`, `errorClass` | Thành công, timeout, retry, unknown, quarantined |
| `sideEffectState` | Chưa gửi, không rõ, committed, acknowledged |
| `mappingVersion`, `clientVersion` | Điều tra lỗi sau nâng cấp cấu hình/thư viện |
| `pod`/instance, traceId | Biết replica nào bị kẹt và truy vết |

Không log password, token, private key, cookie, Authorization header hay full payload chứa PII. Khi người vận hành cần xác minh remote endpoint, dùng tên alias và metadata an toàn.

### 18.2. Metrics theo chặng

| Metric | Cách dùng |
|---|---|
| `remote_connect_duration` p95/p99 | Phát hiện sự cố mạng/TCP |
| `tls_ssh_handshake_duration` | Phát hiện lỗi xác thực hoặc handshake kéo dài |
| `pool_acquire_wait` | Phát hiện thiếu connection, pool starvation |
| `remote_request_duration` | Phát hiện service chậm hoặc timeout gần ngưỡng |
| `gateway_reply_wait` | Phân biệt time-to-reply với network read |
| `retry_attempts` và `retries_exhausted` | Đo khả năng chịu lỗi và retry storm |
| `timeout_count_by_stage` | Cảnh báo đúng owner |
| `executor_queue_depth` và rejection | Phát hiện nghẽn luồng |
| `inflight_requests` và pool active/pending | Theo dõi tài nguyên bị giữ |
| `DLQ_age` / quarantine backlog | Phát hiện lỗi không thể tự phục hồi |
| `Kafka_consumer_lag`, AMQP/JMS queue age | Đo backlog khi remote chậm |
| `SFTP_oldest_pending_file_age` | Biết poller/file transfer bị kẹt |
| `JDBC_query_duration` và lock wait | Phân biệt slow SQL với pool wait |
| `business_completion_latency` | Chứng minh SLA end-to-end đạt hay không |

Tên metric trên mang tính **minh họa**; dùng metric cụ thể của Micrometer, Spring Boot Actuator, client và broker theo stack đã chọn. Hãy kiểm tra rằng instrumented metrics thực sự được xuất tới hệ quan sát, đủ nhãn để lọc nhưng không làm tăng cardinality quá lớn vì thêm user ID/event ID vào tag.

### 18.3. Cảnh báo đề xuất

- Timeout rate và p95/p99 tăng vượt baseline trong nhiều cửa sổ liên tiếp.
- Đơn vị remote target có `pool_acquire` gần ngưỡng hoặc pending queue tăng mạnh.
- Kafka producer delivery errors, consumer lag hoặc offset commit failures tăng.
- SFTP có file ready quá lâu nhưng không được tải/hoàn tất.
- JMS/AMQP oldest message age hoặc DLQ lớn hơn mục tiêu.
- DB connection pool pending tăng, lock timeout xuất hiện nhiều.
- Retry count/attempt tăng nhưng business completion giảm.
- Có **unknown outcome** tồn quá hạn mà chưa đối soát.
- Một timeout được cấu hình nhưng fault injection cho thấy thread không bao giờ thoát.

Alert phải có **severity, owner, runbook và điều kiện tắt/giảm nhiễu**. Ngưỡng dựa trên SLA và baseline của sản phẩm, không dùng một giá trị phổ quát cho mọi môi trường.

## 19. Kiểm thử fault injection trước production

Timeout được đánh giá bằng cách tạo đúng tình huống mạng/đích chậm, không chỉ bằng unit test đối với một Duration property.

### 19.1. Nguyên tắc kiểm thử

1. Dựng dependency thật hoặc môi trường mô phỏng có hành vi đúng (SFTP server, broker, DB, HTTP stub).
2. Giữ business ID và correlation ID để đo tác động sau timeout.
3. Bơm lỗi đúng giai đoạn: connect, TLS, pool wait, read stall, write stall, broker ack, DB lock.
4. Đo **thời gian thực tế để caller thoát** và số thread/connection được giải phóng.
5. Kiểm tra retry có dừng theo budget và error path dẫn tới trạng thái có thể phục hồi.
6. Xác minh actual side effect ở remote target sau timeout; không đoán từ exception.
7. Tái thử khi có nhiều replica, traffic đồng thời, rolling deploy và retry queue.
8. Ghi bằng chứng: elapsed, configured timeout, log, metric, business outcome và version.

Các công cụ network fault proxy, mock server hoặc test container có thể giúp mô phỏng lỗi, nhưng phải chọn loại sát với dependency và **không giả định mock test thay thế hoàn toàn staging/broker thật**.

### 19.2. Ma trận kiểm thử có mã

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| **T01** | DNS không phân giải được hostname | Lỗi có phân loại, không chờ vô hạn theo khả năng resolver |
| **T02** | TCP SYN bị drop/blackhole | Connect timeout phát huy, worker được phục hồi |
| **T03** | TCP connect thành công nhưng TLS handshake treo | Có giới hạn handshake/transport phù hợp |
| **T04** | TLS certificate invalid/hostname mismatch | Fail closed, không bypass vì timeout |
| **T05** | SSH host key không tin cậy | Từ chối SFTP, alert bảo mật |
| **T06** | Connection pool cạn | Pool acquisition timeout và backpressure hoạt động |
| **T07** | Một connection bị giữ quá lâu | Pool metric/alert phản ánh trạng thái |
| **T08** | HTTP server không gửi response headers | Response timeout đúng tầng |
| **T09** | HTTP server nhỏ giọt body nhưng không kết thúc | Overall deadline/size limit kiểm soát thời gian tổng |
| **T10** | Upload HTTP request body bị block | Write/operation budget hoặc isolation xử lý được |
| **T11** | HTTP POST đã commit ở đối tác, response mất | Idempotency/đối soát không tạo duplicate |
| **T12** | HTTP 429 và 503 liên tục | Bounded retries, backoff/jitter, không storm |
| **T13** | HTTP client disconnect trước backend complete | Side effect được ghi nhận, retry không nhân đôi |
| **T14** | Proxy có timeout ngắn hơn backend | Phát hiện mismatch và sửa deadline budget |
| **T15** | SFTP connect được nhưng list/stat treo | Operation timeout hoặc watchdog được kiểm chứng |
| **T16** | SFTP download dừng giữa file | Không coi file ready/processed; recovery an toàn |
| **T17** | SFTP upload hoàn tất nhưng rename response mất | Kiểm tra remote state trước retry |
| **T18** | SFTP session cache trả session chết | Reconnect có giới hạn, không loop nóng |
| **T19** | SFTP server giới hạn connection | Pool/concurrency không làm đầy server |
| **T20** | File local đang được ghi dở | Không xử lý trước ready marker/rename |
| **T21** | NFS/SMB mount không phản hồi | Runbook nhận diện file I/O block và cô lập tác động |
| **T22** | JMS receive không có message | Receive timeout nghĩa “không có message”, không báo business failure |
| **T23** | JMS RPC reply đến sau timeout | Late reply được xử lý; retry không double effect |
| **T24** | JMS broker failover giữa transaction | Reconnect/redelivery theo policy, không mất state |
| **T25** | JMS consumer DB commit xong trước ack bị kill | Redelivery idempotent |
| **T26** | AMQP publisher confirm không tới | Unknown outcome được ghi, consumer idempotent |
| **T27** | AMQP heartbeat ngắt khi một request đang chạy | Reconnect không nhân đôi side effect |
| **T28** | AMQP RPC reply tới muộn | Correlation/late reply an toàn |
| **T29** | AMQP unacked tăng khi handler chậm | Alert/backpressure, prefetch/concurrency phù hợp |
| **T30** | Kafka broker không nhận producer request | Request/delivery timeout, error/retry phù hợp |
| **T31** | Kafka metadata/buffer unavailable | Max-block timeout được đo và giám sát |
| **T32** | Kafka `Future.get` timeout, record sau đó thành công | Không giả định record đã bị hủy |
| **T33** | Kafka consumer quá lâu giữa hai lần poll | Rebalance/partition handling được kiểm soát |
| **T34** | Kafka offset chưa commit khi DB đã commit | Redelivery không tạo business duplicate |
| **T35** | Kafka record lỗi nằm giữa partition | DLT/retry giữ policy ordering |
| **T36** | JDBC connection pool hết chỗ | Pool wait timeout, không làm nghẽn tất cả thread |
| **T37** | JDBC query bị lock trong thời gian dài | Query/lock/transaction timeout theo cấu hình |
| **T38** | JDBC network mất ngay khi commit | Đối soát kết quả, retry idempotent |
| **T39** | JDBC polling hai replica claim cùng row | Không double process ngoài thiết kế |
| **T40** | ExecutorChannel queue đầy | Bounded rejection/backpressure, không OOM |
| **T41** | `replyTimeout` ngắn hơn HTTP client read timeout | Thiết kế phát hiện side effect chạy sau caller timeout |
| **T42** | Retry ở client, advice và broker đồng thời | Tổng attempts trong ngân sách, không storm |
| **T43** | Một message poison retry lặp | Bounded retry, quarantine/DLQ và replay |
| **T44** | Pod SIGTERM khi remote call đang chờ | Graceful stop/recovery không mất message |
| **T45** | Toàn flow deadline hết trước khi retry tiếp | Bỏ attempt không đủ budget, có trạng thái cuối |
| **T46** | Remote API phục hồi sau outage, nhiều replica retry | Jitter/throttling ngăn thundering herd |
| **T47** | Rotating TLS/SSH certificate hoặc service secret | Kết nối mới thành công, cũ thu hồi an toàn |
| **T48** | Response có payload cực lớn | Size/streaming limits và deadline bảo vệ bộ nhớ |
| **T49** | Circuit breaker mở do timeout | Không tiếp tục gửi traffic không kiểm soát |
| **T50** | Replay sau timeout với business key cũ | Không tạo side effect trùng, audit đầy đủ |

**Bằng chứng nghiệm thu:** ghi expected vs actual result, configured timeout, measured elapsed time, target/adapter, client version, số attempts, số connection/thread còn giữ, side-effect state, correlation ID và người xác minh. Một test PASS khi chỉ thấy exception **chưa đủ** nếu chưa xác nhận worker được giải phóng và hệ ngoài không bị thao tác sai.

## 20. Runbook khi timeout tăng bất thường

### 20.1. Chẩn đoán theo thứ tự

1. **Phạm vi:** Adapter nào, target nào, cohort/pod nào, thời điểm nào?
2. **Đang treo ở chặng nào:** DNS, pool, connect, TLS/SSH, write, read, reply, ack, DB query?
3. **Sức chứa:** Thread pool, executor queue, connection pool, inflight và backlog đang ở mức nào?
4. **Remote health:** Server/broker/DB có lỗi, rate limit hoặc thay certificate/credential?
5. **Timeout budget:** Proxy/client deadline có nhỏ hơn server handler/gateway không?
6. **Retry owner:** Bao nhiêu tầng đang retry, attempts và backoff thực tế?
7. **Business state:** Có side effect đã commit nhưng caller chỉ nhận timeout không?
8. **Error path:** Message đang ở retry queue, DLQ, outbox hay đã ack/offset?
9. **Quyết định:** Giảm concurrency, pause poller, mở circuit breaker, chuyển async hoặc failover.
10. **Hồi phục:** Replay có idempotency, đối soát remote state và đóng incident bằng bằng chứng.

### 20.2. Bảng phản ứng vận hành

| Quan sát | Không nên làm | Nên làm |
|---|---|---|
| HTTP timeout dồn dập | Tăng read timeout vô hạn | Kiểm tra remote latency/pool và budget; backpressure |
| Pool acquisition timeout | Chỉ tăng connect timeout | Đo active/idle/pending, sizing và inflight |
| SFTP list/download treo | Tắt host-key verification | Tách lỗi mạng/bảo mật; quản lý session, retry |
| Kafka producer delivery timeout | Reset topic/offset tùy tiện | Kiểm tra broker/metadata/buffer, trạng thái publish |
| JMS/AMQP RPC reply timeout | Retry request với ID mới | Dùng business ID ổn định, đối soát request đã xử lý |
| DB lock wait timeout | Retry vô hạn cùng truy vấn | Tìm blocking transaction, index, concurrency, isolation |
| Error flow mất message | Nuốt exception và log | Xác định ack/commit, chuyển quarantine bền vững |
| Restart làm nhiều luồng chạy lại | Xóa file/queue pending | Đối soát state và replay idempotent |

### 20.3. Replay sau timeout

- Xác minh downstream side effect bằng business key.
- Nếu đã hoàn thành, đánh dấu state đúng và tránh gửi lần hai.
- Nếu chưa hoàn thành, replay theo contract và retry limit.
- Nếu chưa xác định, đưa vào trạng thái **UNKNOWN_OUTCOME** có owner/ticket, không tự áp thao tác nguy hiểm.
- Kiểm tra ordering, phiên bản dữ liệu và tính hợp lệ của request khi replay.
- Đối soát cuối cùng và lưu audit.

## 21. Case study: SFTP → DB/outbox → Kafka và HTTP đối tác

Hệ giả định nhận file CSV đơn hàng từ SFTP; parse/validate, ghi JDBC database, lưu outbox và phát Kafka. Một bước nghiệp vụ phụ gọi HTTP API đối tác. File phải được xử lý trong **10 phút** từ lúc được đánh dấu ready; API đối tác có SLA riêng.

### 21.1. Thiết kế ban đầu có lỗi

- SFTP poller chạy mỗi 2 giây nhưng không có remote read timeout.
- Hai replica dùng một session pool không giới hạn số connection.
- JDBC connection pool chỉ có vài connection, worker tăng lên hàng trăm.
- HTTP outbound chỉ đặt gateway reply timeout, không có connect/read timeout trên client.
- Retry ở HTTP client và Integration advice đều 5 lượt.
- DB commit rồi gửi Kafka trực tiếp, không có outbox.
- Không đo error theo stage nên toàn bộ hiện thành “integration timeout”.

Hệ có thể chạy tốt trên local nhưng khi đối tác chậm sẽ xuất hiện thread starvation, timeout storm, record trùng và message không thể phục hồi.

### 21.2. Thiết kế cải thiện

**SFTP ingress:** Producer upload tên tạm rồi rename khi hoàn tất; client có connect, handshake và operation budget; poller giới hạn batch và inflight. Hai pod dùng distributed claim hoặc phân vùng remote path; mỗi order có idempotency key.

**JDBC:** Connection pool acquisition có timeout hữu hạn; query/lock/transaction được cấu hình theo driver/DB. Unique key ngăn order trùng. Business record và outbox event được ghi trong cùng local DB transaction.

**Kafka:** Outbox publisher dùng producer request/delivery timeout theo SLA, xử lý callback/unknown outcomes; mỗi event có ID ổn định. Kafka consumer downstream vẫn idempotent.

**HTTP đối tác:** Gọi ở bước có ngân sách riêng, có pool acquisition/connect/read timeout và tổng requests được giới hạn. Với POST, gửi cùng idempotency key khi retry hoặc truy vấn business state sau timeout.

**Error flow:** Lỗi dữ liệu vào quarantine; lỗi transient retry có giới hạn, khi quá ngân sách chuyển durable queue và xử lý async. Dashboard đo file pending age, DB pool wait, HTTP response p95, outbox lag, Kafka delivery failures và số UNKNOWN_OUTCOME.

### 21.3. Ngân sách minh họa

| Công đoạn | Giới hạn thiết kế | Ý nghĩa |
|---|---:|---|
| SFTP connect | 5 s | Một lần thiết lập socket/SSH theo API hỗ trợ |
| SFTP transfer operation | 30 s | Cần giới hạn thực tế và khả năng recovery |
| CSV parse/validation | 5 s (mục tiêu) | Giới hạn file size và số record |
| DB pool acquisition | 2 s | Không cho 200 worker chờ vô hạn |
| DB query/transaction | 8 s (tùy driver/DB) | Chỉ áp cho DB operation |
| HTTP mỗi attempt | Connect ≤ 2 s, response ≤ 4 s | Một lần gọi đối tác |
| HTTP retry | 2 attempts, backoff 1 s | Khoảng 13 s trong điều kiện tối đa giả định |
| Kafka outbox publish | Delivery timeout 30 s/attempt | Xử lý riêng, không giữ transaction DB mở |
| Business SLA | 10 phút từ ready file | Theo dõi end-to-end đến kết quả nghiệp vụ |

Đây là **giá trị minh họa**, không nên copy vào sản xuất. Nhiều công đoạn chạy bất đồng bộ hoặc chồng lấp; công thức tổng phải được xây từ topology thật. Business SLA 10 phút không có nghĩa cho phép một thread SFTP hoặc HTTP treo 10 phút.

### 21.4. Failure drills

**Drill A — SFTP treo ở list/stat:** Poller không giữ toàn bộ scheduler vĩnh viễn; có metric, retry/backoff và file còn có thể xử lý lại.

**Drill B — HTTP timeout sau remote commit:** Gửi lại cùng idempotency key hoặc xác minh trạng thái; không tạo giao dịch thứ hai.

**Drill C — DB pool cạn:** Worker ngừng nhận thêm có kiểm soát; pool wait timeout và alert phản ánh đúng nguyên nhân, không dùng retry nóng.

**Drill D — DB commit xong, Kafka publish lỗi:** Outbox vẫn chứa event; publisher hồi phục và phát lại an toàn.

**Drill E — Pod bị kill khi đang gửi:** Metadata và message state cho phép replay; không đánh dấu hoàn tất sai.

**Bài học:** Timeout là một phần của giao thức phục hồi. Cắt thời gian chờ mà không quản lý trạng thái side effect có thể còn nguy hiểm hơn để request chậm.

## 22. Phiếu review timeout production có thể tái sử dụng

~~~yaml
# Phiếu review MINH HỌA, không phải Spring Boot auto-config.
flow: orders-sftp-to-db-kafka-http
owner:
  application: integration-team
  onCall: platform-operations
businessSla:
  from: remote-file-ready
  to: order-processed
  maximum: 10m
remoteEndpoints:
  - name: supplier-sftp
    protocol: sftp
    clientVersion: REVIEW_REQUIRED
    connect: 5s
    handshake: REVIEW_REQUIRED
    operation: 30s
    retryOwner: sftp-ingress
    ambiguousOutcome: verify-remote-file-state
  - name: partner-http
    protocol: http
    poolAcquisition: 1s
    connect: 2s
    response: 4s
    totalAttempts: 2
    backoff: 1s
    retryOwner: order-partner-client
    ambiguousOutcome: lookup-by-idempotency-key
  - name: order-jdbc
    protocol: jdbc
    poolAcquisition: 2s
    query: 8s
    lock: REVIEW_REQUIRED
    retryOwner: db-transaction-handler
  - name: kafka-producer
    protocol: kafka
    maxBlock: 5s
    requestTimeout: 10s
    deliveryTimeout: 30s
    ambiguousOutcome: outbox-and-business-id
controls:
  boundedInflight: true
  idempotencyKey: source-orderId-revision
  durableErrorRecovery: true
  shutdownRecoveryTested: true
observability:
  timeoutByStage: required
  outstandingUnknownOutcomes: required
  endToEndLatency: required
approval:
  technicalOwner: PENDING
  security: PENDING
  operations: PENDING
~~~

Mẫu là **tài liệu quyết định**, không phải property framework tự nhận. Đơn vị, tên client, khả năng hỗ trợ và ngưỡng cần được thực thi/kiểm chứng; mọi mục `REVIEW_REQUIRED` và `PENDING` phải được xử lý trước GO.

### 22.1. Quyết định go/no-go

| Trạng thái | Khi áp dụng |
|---|---|
| **GO** | Timeout theo tầng đã được test, budget phù hợp SLA, recovery có bằng chứng |
| **GO WITH EXCEPTION** | Ngoại lệ có owner, mức ảnh hưởng, biện pháp giảm rủi ro và ngày hết hạn |
| **HOLD / RETEST** | Thiếu test handshake/pool/read/ack hoặc chưa chứng minh retry budget |
| **NO-GO** | Không thể chặn hung resource, mất dữ liệu/duplicate không kiểm soát, bỏ qua TLS/host key hoặc không rõ side effect |

## 23. Các anti-pattern phải tránh

**Một timeout chung cho mọi hệ:** không phân biệt pool wait, connect, reply và query. Cần ma trận riêng theo client/protocol.

**Connect timeout được đặt nhưng read timeout bỏ trống:** TCP kết nối thành công nhưng server im lặng, thread tiếp tục chờ.

**Reply timeout thay cho network timeout:** Gateway ngừng chờ reply nhưng remote operation vẫn chạy và giữ connection.

**Timeout 0 nghĩa là luôn an toàn:** semantics 0/âm/null khác nhau theo API; phải validate phiên bản thực tế.

**Tăng timeout để che pool starvation:** 300 worker tranh 20 connection khiến chờ pool kéo dài; phải dùng capacity và backpressure.

**Retry mọi timeout như chưa xảy ra side effect:** tạo giao dịch/file/message trùng; dùng idempotency và reconciliation.

**Cắt request mà không biết outcome:** báo lỗi nhưng bỏ qua thao tác đối tác đã thực hiện. Cần trạng thái unknown outcome và runbook.

**Chỉ đo exception, không đo latency thực:** read timeout có thể được reset khi server gửi chậm từng byte. Cần overall deadline và payload limit.

**Đặt poll interval bằng network timeout:** hai khái niệm khác nhau, một lượt poll có thể treo.

**JMS receive timeout bằng business deadline:** receive timeout có thể chỉ nghĩa không có message, không giới hạn handler.

**AMQP heartbeat bằng publish timeout:** heartbeat là health check kết nối; publisher confirm là chuyện khác.

**Kafka Future.get timeout nghĩa record không gửi:** producer có thể còn hoạt động; phải tra trạng thái và dùng business key.

**JDBC connectionTimeout bao phủ mọi query:** pool wait khác lock/query/socket/transaction timeout.

**Rollback application sẽ đảo ngược mọi request đã timeout:** DB, broker, file và remote API có thể đã commit; cần đối soát và bù trừ.

## 24. Câu hỏi tự kiểm tra

1. Connect timeout, read timeout và whole-flow deadline khác nhau ở đâu?
2. Khi server trả từng byte chậm, vì sao read timeout có thể không giới hạn tổng thời gian response?
3. Gateway reply timeout có tự hủy HTTP socket đang chờ không?
4. Khi kết nối HTTP pool cạn, tăng connect timeout có giúp không?
5. Tại sao SFTP poll interval không thay cho SSH operation timeout?
6. Khi SFTP upload thành công nhưng rename response timeout, hệ nên làm gì?
7. JMS receiveTimeout có ý nghĩa gì khi queue rỗng?
8. Vì sao JMS RPC reply timeout không chứng minh consumer chưa thực hiện nghiệp vụ?
9. AMQP heartbeat khác publisher confirm timeout như thế nào?
10. Kafka `max.block.ms`, `request.timeout.ms` và `delivery.timeout.ms` giải quyết những khoảng chờ nào?
11. Nếu `Future.get(timeout)` hết hạn, liệu Kafka record đã chắc chắn bị hủy chưa?
12. `max.poll.interval.ms` có phải timeout của Kafka business handler không?
13. HikariCP `connectionTimeout` khác JDBC query timeout ở đâu?
14. Vì sao query timeout có thể không bảo vệ được network stall trong mọi driver?
15. File adapter đọc NFS có cần quan tâm network I/O stall không?
16. Một request đã timeout sau DB commit nhưng trước broker ack có thể gây vấn đề gì?
17. Vì sao retry ở nhiều tầng có thể vượt deadline inbound?
18. Khi nào nên chuyển một giao dịch từ synchronous gateway sang durable asynchronous processing?
19. Những metric nào phân biệt pool starvation với remote response chậm?
20. Những bước nào giúp replay một request có outcome chưa rõ một cách an toàn?

**Gợi ý:** Luôn trả lời theo chuỗi **đang chờ ở đâu → timeout nào kiểm soát chặng đó → side effect đã đến mốc nào → có được retry không → cách đối soát/khôi phục**.

## 25. Thuật ngữ và tài liệu tham khảo

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Connect timeout** | Giới hạn chờ thiết lập kết nối |
| **Pool acquisition timeout** | Giới hạn chờ mượn pooled connection |
| **Handshake timeout** | Giới hạn chờ TLS/SSH negotiation/auth |
| **Read / write timeout** | Giới hạn một trạng thái chờ I/O cụ thể |
| **Response/reply timeout** | Giới hạn chờ phản hồi request/message |
| **Whole-flow deadline** | Thời hạn cho hợp đồng nghiệp vụ từ đầu đến cuối |
| **Retry/backoff** | Thử lại với số lần và khoảng nghỉ có kiểm soát |
| **Circuit breaker / bulkhead** | Chặn dependency lỗi liên tục / giới hạn tài nguyên bị chiếm |
| **Backpressure** | Giảm tốc đầu vào theo năng lực xử lý |
| **Idempotency** | Lặp request mà không lặp tác động nghiệp vụ ngoài ý muốn |
| **Unknown outcome** | Caller không biết chắc bên nhận đã thực hiện side effect chưa |
| **Ack / offset commit** | Xác nhận hoặc đánh dấu vị trí đã xử lý ở broker |
| **Delivery timeout** | Giới hạn thời gian delivery theo semantics của client |
| **Reconciliation** | Đối soát trạng thái thực tế của nghiệp vụ và message |
| **Graceful shutdown** | Ngừng nhận mới và hoàn thành/khôi phục inflight có kiểm soát |

Nguồn cần tra cứu theo **phiên bản sản phẩm đang dùng**:

- **Spring Integration Reference Guide:** Message Channels, Gateways, Polling Consumer, Error Handling, File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC.
- **Spring Framework / Spring Boot Reference:** HTTP client request factories, transactions, executors, configuration properties, Actuator/observability.
- **Apache Kafka Client Configuration Documentation:** producer `request.timeout.ms`, `delivery.timeout.ms`, `max.block.ms`; consumer group, poll, heartbeat và session settings.
- **Spring for Apache Kafka Reference:** listener container, acknowledgements, retries, error handlers và DLT.
- **Spring AMQP / RabbitMQ documentation:** connection timeout, heartbeat, reply timeout, publisher confirms và consumer ack.
- **Jakarta Messaging/JMS vendor documentation:** receive, request/reply, connection failover, transaction và redelivery.
- **JDBC driver/database documentation và HikariCP configuration:** connection pool, query, socket, lock và transaction timeouts.
- **SSH/SFTP client và server documentation:** handshake, session, remote operation, keepalive, file atomicity và retry semantics.

**Tiêu chí cuối cùng:** “Đã đặt timeout” không có nghĩa một kết nối từ xa đã an toàn. Hệ production phải chứng minh mỗi trạng thái chờ có giới hạn phù hợp, tổng thời gian nằm trong SLA, retry không nhân đôi side effect, worker/connection được phục hồi, trạng thái mơ hồ có cách đối soát và mọi lỗi đều có metric, owner cùng runbook.



