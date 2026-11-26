# Kết nối dùng lại, connection pool và giới hạn đồng thời

## 1. Vì sao kết nối đến Vault cần được dùng lại?

Trong ứng dụng Java sử dụng **Spring Vault**, các thao tác như xác thực workload, đọc KV secrets qua `VaultTemplate`, mã hóa bằng Transit, lấy chứng chỉ PKI, gia hạn token hoặc lease đều tạo lời gọi HTTP đến **HashiCorp Vault**. Nếu mỗi lời gọi lại mở một kết nối TCP và thiết lập TLS mới, chi phí bắt tay và quản lý socket có thể tăng đáng kể khi lưu lượng lớn.

**Connection reuse (tái sử dụng kết nối)** cho phép HTTP client gửi nhiều request **lần lượt** qua một kết nối còn dùng được. **Connection pool** giữ và phân phối nhiều kết nối để phục vụ các request đồng thời mà không phải liên tục tạo kết nối mới.

Ba mục tiêu thực tế:

1. **Giảm độ trễ và tài nguyên** khi tránh lặp lại TCP/TLS handshake cho mỗi request.
2. **Giới hạn số kết nối đang được duy trì** tới Vault, proxy hoặc load balancer.
3. **Kiểm soát tải đồng thời** để ứng dụng không dồn quá nhiều request lên Vault trong lúc có sự cố hoặc lưu lượng tăng đột biến.

Connection pool giúp quản lý tài nguyên, nhưng **pool size không tự động đồng nghĩa với số thao tác nghiệp vụ tối đa**: có thể có nhiều thread đang xếp hàng đợi kết nối, nhiều instance ứng dụng và các HTTP client khác nhau.

## 2. HTTP keep-alive và vòng đời một kết nối

Với HTTP/1.1, một kết nối TCP có thể được giữ mở sau khi response hoàn tất để phục vụ request tiếp theo. Khi dùng HTTPS, kết nối TCP này đã có phiên TLS; việc dùng lại nó tránh bắt tay TLS mới.

```text
Không tái sử dụng:
  GET secret A ── TCP/TLS mới ──► Vault ── đóng kết nối
  GET secret B ── TCP/TLS mới ──► Vault ── đóng kết nối

Có tái sử dụng:
  GET secret A ─┐
  GET secret B ─┼── TCP/TLS đang mở ──► Vault
  POST transit ─┘      (thực hiện theo lượt trên connection)
```

Ở mô hình HTTP/1.1 thông dụng của HTTP client đồng bộ, một connection đang bận xử lý một request thì request khác phải mượn connection khác hoặc chờ; không nên giả định một connection có thể xử lý nhiều request song song. HTTP/2 có cơ chế multiplexing khác, nhưng **không mặc định** rằng transport `VaultTemplate` đang sử dụng HTTP/2.

Các điều kiện để kết nối được dùng lại:

- Kết nối còn sống, chưa bị server, proxy hoặc load balancer đóng vì idle timeout.
- HTTP client cho phép keep-alive và chưa quyết định loại kết nối khỏi pool.
- Response body đã được đọc và đóng đúng cách để trả connection về pool.
- Kết nối tương thích với đích/route đang gọi.

**TLS session resumption** giúp giảm chi phí khi phải tạo kết nối TLS mới, còn **connection reuse** tiếp tục sử dụng chính kết nối đã mở. Hai khái niệm này liên quan nhưng không giống nhau.

## 3. Connection pool hoạt động như thế nào?

Pool có thể lưu giữ kết nối **rảnh (available/idle)**, giao kết nối cho request **đang dùng (leased)** và ghi nhận request **đang chờ cấp kết nối (pending)**.

```text
                     Request từ VaultTemplate
                             │
                             ▼
                  ┌───────────────────────┐
                  │ HTTP connection pool  │
                  │ maxPerRoute / maxTotal│
                  └───────────────────────┘
                    │                 │
          có connection rảnh       pool đã đầy
                    │                 │
                    ▼                 ▼
                leased          đợi trong hàng chờ
                    │            (pool-acquire timeout)
                    ▼                 │
                Vault API ◄──────────┘ khi có connection
                    │
                    ▼
              trả connection về pool
```

Ví dụ có **8 connection tối đa cho route tới Vault** và 20 request đến cùng lúc: tối đa khoảng 8 request có thể dùng connection cho route đó tại một thời điểm theo mô hình HTTP/1.1; 12 request còn lại có thể chờ pool hoặc thất bại khi hết thời gian chờ. Việc đặt pool size là 8 **không tự ngăn** hệ thống tạo 20 thread hay 20 yêu cầu nghiệp vụ.

### 3.1. `maxTotal` và `maxPerRoute`

Trong Apache HttpClient, hai giới hạn thường gặp:

| Thông số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `maxTotal` | Số connection tối đa của cả pool. | 32 connection tới tất cả route. |
| `maxPerRoute` | Số connection tối đa cho **một HTTP route**. | 16 connection tới route Vault. |
| `connectionRequestTimeout` | Thời gian tối đa để request **đợi pool cấp connection**. | 2 giây. |
| `connectTimeout` | Giới hạn chờ thiết lập kết nối mới. | 3 giây. |
| `responseTimeout` / `socketTimeout` | Giới hạn chờ dữ liệu ở những giai đoạn tương ứng; ngữ nghĩa tùy HTTP client. | 10 giây minh họa. |

HTTP route được xác định theo endpoint và cách client đi qua proxy, **không phải theo mount KV, Transit hay PKI**. Chẳng hạn, hai request cùng đến `https://vault.example.internal:8200` nhưng gọi `/v1/secret/...` và `/v1/transit/...` thường cùng cạnh tranh giới hạn per-route. Nếu một load balancer đứng trước Vault, pool thấy route đến load balancer chứ không trực tiếp phân phối connection theo các Vault node phía sau.

Nếu ứng dụng chỉ gọi một Vault endpoint, `maxPerRoute` thường là giới hạn đáng quan sát nhất; tăng `maxTotal` lên 100 nhưng vẫn giữ `maxPerRoute=2` sẽ **không** cho phép route đó dùng 100 connection đồng thời.

### 3.2. Pool cấp kết nối; nó không ra quyết định retry

Pool không biết `GET` secret có thể thử lại an toàn hay một request tạo token/issue PKI đã thành công trên Vault nhưng response bị mất. Khi một connection bị đóng đột ngột hoặc read timeout xảy ra, logic retry phải cân nhắc **tính lặp an toàn của API** và ngân sách thời gian tổng. Tăng connection pool không giải quyết được lỗi policy `403`, mount `404` hoặc token hết hạn.

## 4. Tái sử dụng đúng đối tượng trong Spring Vault

Trong Spring Vault, `VaultTemplate` cung cấp các thao tác đồng bộ; phần HTTP transport nằm dưới `RestTemplate` và `ClientHttpRequestFactory` tương ứng. Muốn tái sử dụng connection hiệu quả, ứng dụng thường cần tái sử dụng **HTTP client và connection manager** qua nhiều lời gọi.

**Nên làm:**

- Khởi tạo và chia sẻ `VaultTemplate`/HTTP client ở phạm vi ứng dụng hoặc Spring bean có vòng đời rõ ràng.
- Dùng HTTP client có pool khi workload gửi nhiều request đồng thời.
- Đóng HTTP client/pool khi ứng dụng dừng để giải phóng socket.
- Nếu có nhiều thành phần gọi Vault (ví dụ authentication/session manager, token/lease renewal), kiểm tra chúng đang dùng HTTP transport nào và cấu hình giới hạn cho từng transport liên quan.

**Tránh làm:**

- Tạo mới `CloseableHttpClient`, connection manager và `VaultTemplate` bên trong **mỗi** request người dùng.
- Chủ động đóng `CloseableHttpClient` khi vẫn còn các bean khác dùng chung.
- Cấu hình `Connection: close` trên mọi request rồi kỳ vọng hiệu quả keep-alive.
- Chỉ tăng pool size mà không quan sát độ trễ Vault, số thread đang chờ và giới hạn tải tổng.

Trong Spring Cloud Vault, các thuộc tính như `spring.cloud.vault.uri`, `connection-timeout` và `read-timeout` hỗ trợ cấu hình endpoint và timeout của phần tích hợp tương ứng; chúng **không phải** một hợp đồng chung để điều khiển `maxTotal`, `maxPerRoute` hay `poolAcquireTimeout` của mọi HTTP client tùy chỉnh. Cần xác minh HTTP client thực tế mà từng phiên bản Spring Cloud Vault cấu hình hoặc tự cung cấp transport theo khả năng mở rộng của phiên bản đó.

## 5. Ví dụ: Spring Vault với Apache HttpClient 5 có connection pool

Đoạn cấu hình sau minh họa **Spring Framework 6.x / Apache HttpClient 5.x** kết hợp với Spring Vault dùng `VaultTemplate`. Dự án cần có các dependency tương thích cho `spring-web`, `spring-vault-core` và Apache HttpClient 5. Ứng dụng phải định nghĩa một bean `ClientAuthentication` phù hợp với workload (ví dụ AppRole hoặc Kubernetes authentication); ví dụ không cố định token trong mã nguồn.

```java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class VaultHttpClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient vaultHttpClient() {
        ConnectionConfig connectionConfig = ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(3))
                .setSocketTimeout(Timeout.ofSeconds(10))
                .setTimeToLive(TimeValue.ofMinutes(5))
                .build();

        PoolingHttpClientConnectionManager pool =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(32)
                        .setMaxConnPerRoute(16)
                        .setDefaultConnectionConfig(connectionConfig)
                        .build();

        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(Timeout.ofSeconds(2))
                .setResponseTimeout(Timeout.ofSeconds(10))
                .build();

        return HttpClients.custom()
                .setConnectionManager(pool)
                .setDefaultRequestConfig(requestConfig)
                .evictExpiredConnections()
                .evictIdleConnections(TimeValue.ofSeconds(30))
                .build();
    }

    @Bean
    VaultTemplate vaultTemplate(
            CloseableHttpClient vaultHttpClient,
            ClientAuthentication authentication) {
        VaultEndpoint endpoint = new VaultEndpoint();
        endpoint.setScheme("https");
        endpoint.setHost("vault.example.internal");
        endpoint.setPort(8200);

        HttpComponentsClientHttpRequestFactory factory =
                new HttpComponentsClientHttpRequestFactory(vaultHttpClient);
        return new VaultTemplate(endpoint, authentication, factory);
    }
}
```

Ý nghĩa các giới hạn trong ví dụ:

1. Pool quản lý tối đa **32 connection** trên mọi route, trong đó tối đa **16 connection cho một route**.
2. Request chờ pool cấp connection quá **2 giây** có thể thất bại thay vì xếp hàng vô hạn.
3. Khi cần mở connection mới, connect timeout giới hạn thời gian thiết lập kết nối; socket/response timeout giới hạn các khoảng chờ dữ liệu theo ngữ nghĩa của Apache HttpClient 5.
4. Connection có thời gian sống giới hạn; connection hết hạn và idle lâu được dọn để giảm nguy cơ dùng lại socket cũ.
5. `CloseableHttpClient` là bean dùng chung và được đóng lúc container dừng.

Đây là **giá trị minh họa**, không phải cấu hình tối ưu mặc định cho mọi ứng dụng. Đặt `connectionRequestTimeout`, connect timeout và response timeout không tạo ra một deadline tổng cho toàn bộ nghiệp vụ. Cách cấu hình các timeout, đặc biệt connect timeout và socket timeout, có thể khác giữa các bản Apache HttpClient/Spring Framework; đối chiếu phiên bản mà dự án đang dùng.

**Với HTTPS dùng CA nội bộ**, vẫn phải cấu hình trust material/TLS phù hợp cho client. Đoạn mã trên minh họa pool và timeout, chưa thiết lập SSL truststore riêng; không tắt xác minh chứng chỉ để làm cho ví dụ chạy.

## 6. Giới hạn đồng thời ở cấp ứng dụng

Connection pool ràng buộc tài nguyên HTTP **sau khi request đã đi vào transport**. Nếu không muốn hàng trăm thread tiếp tục chờ connection, có thể giới hạn số nghiệp vụ gọi Vault **trước khi** chúng bước vào HTTP client.

Ví dụ một cổng kiểm soát đồng thời bằng `Semaphore`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class VaultCallLimiter {
    private final Semaphore permits = new Semaphore(12);

    public <T> T execute(Callable<T> operation) throws Exception {
        if (!permits.tryAcquire(250, TimeUnit.MILLISECONDS)) {
            throw new RejectedExecutionException("Vault đang quá tải ở phía client");
        }

        try {
            return operation.call();
        } finally {
            permits.release();
        }
    }
}
```

Sử dụng với một thao tác Vault có sẵn:

```java
VaultCallLimiter limiter = new VaultCallLimiter(); // chia sẻ một instance
var response = limiter.execute(
        () -> vaultTemplate.read("secret/data/app/config"));
```

Ví dụ cho phép tối đa **12 lời gọi đi qua limiter cùng lúc** trong phạm vi instance đang dùng chung limiter. Khi đủ 12 lời gọi, request mới chỉ đợi tối đa 250 ms để lấy permit; sau đó nhận lỗi rõ ràng để lớp nghiệp vụ quyết định phản hồi. `finally` đảm bảo trả permit kể cả khi Vault trả lỗi hoặc throw exception.

Giới hạn này áp dụng **cho những lời gọi thực sự đi qua limiter**, không tự áp dụng cho scheduler renewal hoặc `VaultTemplate` khác. Nếu luồng gia hạn token/lease có độ ưu tiên cao, cân nhắc giới hạn riêng hoặc headroom của pool phù hợp; chỉ chừa 4 connection giữa limiter 12 và pool 16 **chưa phải** bảo đảm cứng rằng renewal luôn có connection.

Một cách bố trí:

```text
N request nghiệp vụ
       │
       ▼
Semaphore (12 permit/instance)
       │    quá giới hạn -> chờ ngắn hoặc fail fast
       ▼
VaultTemplate
       │
       ▼
HTTP pool (16 connection/route, 32 total)
       │
       ▼
Vault endpoint / load balancer
```

Pool giữ trần cho số connection; semaphore giúp quản lý lượng **công việc đồng thời** trước khi chiếm hàng chờ của pool. Với pipeline bất đồng bộ, cơ chế tương ứng có thể là bounded queue, bulkhead hoặc giới hạn concurrency ở reactive operator; chọn giải pháp phù hợp với loại HTTP client thực tế.

## 7. Tính toán giới hạn khi chạy nhiều instance

Giới hạn connection trong một process không phải giới hạn toàn cụm ứng dụng.

Giả sử:

- Có **6 replica** của một dịch vụ Java.
- Mỗi replica tạo pool với `maxPerRoute = 16` cho Vault.
- Cả 6 replica cùng gọi một Vault hostname.

Khi đó, giới hạn lý thuyết từ **sáu pool này** tới route tương ứng là:

```text
6 replica × 16 connection/replica = tối đa 96 connection
```

Con số 96 chỉ mô tả tổng trần từ các pool được nêu. Thực tế còn phụ thuộc các connection đã mở, timeout, load balancer, cách định tuyến và những client khác (authentication, monitoring, agent hoặc service khác) cùng kết nối Vault.

Khi lên kế hoạch năng lực, cân nhắc đồng thời:

| Đại lượng | Cần hỏi |
| --- | --- |
| Số replica | Có thể autoscale tới bao nhiêu instance trong giờ cao điểm? |
| Connection/route mỗi replica | Mỗi instance được phép giữ bao nhiêu kết nối đến endpoint? |
| Số request thực sự đồng thời | Bao nhiêu lời gọi Vault đang xử lý thay vì chờ pool? |
| Latency Vault | KV, login, Transit và PKI có p95/p99 khác nhau thế nào? |
| Giới hạn phía Vault/proxy | Backend, listener, gateway và rate limit chịu được tải bao nhiêu? |
| Ngân sách request | Có bao nhiêu thời gian dành cho pool wait, connect, đọc response và retry? |

Đừng chọn pool size chỉ bằng số thread của web server. Một cách tiếp cận là đo tốc độ gọi Vault và thời gian xử lý trung bình/đuôi; số request đang chạy cùng lúc có thể xấp xỉ **tốc độ request × thời gian xử lý**, nhưng phải tính thêm biến động, retry và thao tác chậm. Sau đó điều chỉnh và load test theo replica thực tế.

## 8. Idle connection, stale connection và thay đổi topology Vault

Một connection đang rảnh không có nghĩa nó sẽ mãi còn hợp lệ. Server, ingress hoặc load balancer có thể đóng socket sau khoảng idle timeout. Khi Vault HA đổi leader hoặc Pod được thay, kết nối cũ cũng có thể bị ngắt.

Các biện pháp thường dùng:

- **Idle eviction:** dọn connection không hoạt động quá ngưỡng phù hợp; cân đối giữa tái sử dụng và socket bị giữ quá lâu.
- **Connection TTL:** giới hạn thời gian sống của một connection để định kỳ tạo lại kết nối.
- **Stale connection validation** nếu transport hỗ trợ: kiểm tra connection không còn dùng được trước khi phát lại.
- **Timeout và retry có giới hạn:** xử lý sự cố kết nối thoáng qua mà không tạo retry storm; lựa chọn retry tùy API có thể lặp an toàn hay không.
- **Graceful shutdown:** ngừng nhận request mới, để request đang chạy hoàn tất trong thời gian cho phép, rồi đóng HTTP client/pool.

**Lưu ý về Vault HA:** keep-alive không bảo đảm các request sẽ được cân bằng trên mọi Vault node; một connection đến load balancer có thể gắn với một backend trong suốt thời gian nó tồn tại. Không kỳ vọng tăng pool là cách sửa một cấu hình cluster/leader redirect sai.

**Lưu ý về TLS:** tái sử dụng kết nối không bỏ qua yêu cầu kiểm tra chứng chỉ khi thiết lập HTTPS. Khi Vault hoặc proxy thay đổi chứng chỉ, connection đang mở có thể tiếp tục tồn tại đến lúc đóng; connection mới phải xác minh chứng chỉ theo truststore hiện hành. Bảo đảm cấu hình DNS, CA và hostname khớp với endpoint ứng dụng sử dụng.

## 9. Ảnh hưởng tới KV, token/lease, Transit và PKI

Các API Vault có tính chất tải khác nhau, nên một pool dùng chung cần được quan sát theo **loại thao tác**, dù các request cùng một route HTTP.

| Nhóm thao tác | Hành vi đáng lưu ý | Hệ quả khi pool bão hòa |
| --- | --- | --- |
| Login theo workload | Cần nhận token trước khi thao tác protected API. | Chậm xác thực hoặc làm startup phụ thuộc vào hàng chờ pool. |
| KV read/write | Nhiều thao tác nhanh, có thể gọi thường xuyên. | Gia tăng latency cho request nghiệp vụ nếu mỗi request đều truy Vault. |
| Token renewal và lease renewal | Thường chạy theo lịch gần thời gian hết hạn. | Đợi connection quá lâu có thể khiến renewal thất bại hoặc credential hết hạn. |
| Transit encrypt/decrypt | Có thể nằm trên luồng request nhạy về thời gian. | Tác động trực tiếp tới latency và throughput API nghiệp vụ. |
| PKI issue/revoke | Một số request có thể lâu hơn KV read; tạo hoặc thu hồi tài nguyên. | Giữ connection lâu, tăng hàng chờ; retry không kiểm soát có thể gây tác dụng phụ. |

Khi request cấp secret động hoặc chứng chỉ bị read timeout, phía Vault **vẫn có thể đã xử lý thành công**. Không tự retry mọi POST chỉ vì client chưa nhận được response. Đánh giá tính idempotent, thời hạn lease và cách đối soát trạng thái trước khi áp dụng retry.

Nếu thao tác chậm như PKI chiếm phần lớn pool, có thể cân nhắc **transport riêng cho nhóm tác vụ đặc biệt**, hoặc tách luồng/tải để bảo vệ các thao tác có deadline ngắn. Điều này làm tăng số connection/pool phải quản lý, vì vậy cần tính vào ngân sách toàn hệ thống.

## 10. Theo dõi connection pool và phát hiện nghẽn

Với Apache HttpClient 5, `PoolingHttpClientConnectionManager` có thống kê tổng tại thời điểm quan sát:

```java
var stats = pool.getTotalStats();
int leased = stats.getLeased();
int available = stats.getAvailable();
int pending = stats.getPending();
int max = stats.getMax();
```

Đoạn trên giả định `pool` là connection manager đã tạo và được giữ tham chiếu để đọc chỉ số. Có thể đưa các số này vào Micrometer hoặc hệ thống metrics của ứng dụng; tránh dựng connection manager mới chỉ để đọc số liệu.

| Chỉ số | Khi nào cần điều tra? |
| --- | --- |
| `leased` gần `max` kéo dài | Request tới Vault sử dụng hết khả năng cấp connection; xem tải và latency. |
| `pending` tăng liên tục | Request đang xếp hàng; kiểm tra pool cap và deadline. |
| `available` cao nhưng Vault chậm | Có thể lỗi nằm ở endpoint, API, retry hoặc route khác, không nhất thiết ở pool. |
| Pool acquire timeout tăng | Chờ lấy connection vượt ngưỡng; giảm áp lực, tối ưu request hoặc cân nhắc điều chỉnh giới hạn. |
| Connect/read timeout tăng | Xem mạng, TLS, Vault latency và proxy idle timeout; phân biệt với pool wait. |
| p95/p99 latency theo API tăng | Cần phân tích KV, login, renewal, Transit, PKI riêng để tránh kết luận sai. |

Các metric nên có tag ít biến thể, ví dụ loại thao tác `kv_read`, `transit_encrypt`, `pki_issue` và kết quả thành công/thất bại. **Không** đưa token, secret path chứa định danh nhạy cảm, response body hoặc header xác thực vào log/metrics.

Thời gian gọi Vault từ tầng ứng dụng có thể bao gồm đợi semaphore, đợi connection, gửi request và đọc response. Do đó, cần phân biệt **latency nhìn từ ứng dụng** với **latency xử lý tại Vault**.

## 11. Kiểm thử đúng hành vi pooling và concurrency

Một HTTP mock server có điều khiển độ trễ (hoặc môi trường Vault thử nghiệm) giúp xác minh cấu hình:

1. **Reuse:** gửi liên tiếp nhiều request tới một endpoint, quan sát số TCP connection được mở thấp hơn số request khi server cho keep-alive.
2. **Pool cap:** giữ nhiều response chậm đồng thời; xác nhận số connection đang leased không vượt `maxPerRoute`/ `maxTotal` tương ứng.
3. **Pool wait:** tạo nhiều request hơn pool cho phép; kiểm tra request đợi và gặp pool-acquire timeout đúng cấu hình.
4. **Ứng dụng quá tải:** dùng limiter với 12 permit, tạo nhiều lời gọi hơn giới hạn; xác nhận request vượt ngưỡng được phản hồi có kiểm soát và không rò permit khi lỗi.
5. **Idle close:** để server/proxy chủ động đóng kết nối idle; kiểm tra client loại connection cũ và phục hồi ở request kế tiếp theo cơ chế được cấu hình.
6. **Vault HA hoặc proxy chuyển backend:** kiểm tra kết nối được tái tạo sau failover và không retry vô hạn.
7. **Token/lease renewal:** khi pool bận, xác nhận lịch renewal và timeout không làm hết hạn token/lease ngoài dự kiến.

Kiểm tra phải đi qua **đúng `VaultTemplate` và HTTP client mà ứng dụng thực sự dùng**. Kết quả tốt của một `curl` riêng lẻ không chứng minh application pool được cấu hình chính xác.

### Bảng phân biệt lỗi thường gặp

| Hiện tượng | Khả năng cao | Hướng xử lý đầu tiên |
| --- | --- | --- |
| `pending` cao, pool-acquire timeout | Pool chật hoặc request giữ connection lâu | Đo leased/pending, latency, tối ưu concurrency; điều chỉnh pool có cơ sở. |
| Connect timeout, `pending` thấp | TCP routing, endpoint, proxy, network | Kiểm tra DNS, host/port, listener, firewall. |
| Read/socket timeout, `leased` cao | Vault/proxy chậm trả dữ liệu | Xem latency API, backend, timeout và số request giữ socket. |
| Lỗi khi tái sử dụng connection sau idle | Server/proxy đã đóng socket, kết nối stale | Kiểm tra idle TTL, eviction và retry phù hợp. |
| HTTP `403` | Auth, token, policy, namespace | Kiểm tra quyền Vault; tăng pool không sửa được. |
| HTTP `429` hoặc `5xx` | Rate limit, quá tải hoặc lỗi phía Vault/proxy | Throttle ở client, backoff có jitter, quan sát tải và giới hạn retry. |

## 12. Tình huống tự luyện

**Tình huống A — 30 request cùng lúc, pool 8 connection:** nếu tất cả đều gọi cùng Vault route và transport là HTTP/1.1, tối đa khoảng 8 lời gọi đồng thời có connection; các lời gọi còn lại đợi pool. Nếu độ trễ của Vault tăng, số request pending có thể tăng dù ứng dụng không tạo thêm connection.

**Tình huống B — Tăng `maxTotal` từ 20 lên 100 nhưng throughput không đổi:** hãy xem `maxPerRoute`. Nếu chỉ có một Vault route và giới hạn per-route vẫn là 5, tăng maxTotal không làm tăng giới hạn connection của route đó.

**Tình huống C — 5 replica cùng tăng pool từ 10 lên 50:** giới hạn kết nối lý thuyết từ các replica này tăng từ 50 lên 250. Nếu Vault hoặc ingress đã quá tải, thay đổi này có thể làm tình trạng xấu hơn; đo tải thực tế, request đang chờ, error rate và SLA trước khi mở rộng.

**Tình huống D — Renewal chậm khi KV burst:** các request KV chiếm hết pool dùng chung khiến tác vụ renew token/lease đợi. Cần đánh giá headroom, lịch renewal, pool/transport riêng cho tác vụ quan trọng hoặc giới hạn KV concurrency, thay vì chỉ tăng TTL token.

### Ghi nhớ

Trong Spring Vault, **keep-alive** giúp dùng lại một TCP/TLS connection, **connection pool** điều tiết số connection được phân phối, còn **giới hạn đồng thời ở tầng ứng dụng** quản lý số công việc được phép gọi Vault. Để tối ưu an toàn, chia sẻ HTTP client theo vòng đời ứng dụng, cấu hình cả `maxTotal`/`maxPerRoute` và pool-acquire timeout, tính tải từ mọi replica, theo dõi `leased`/`pending` cùng latency, và kiểm thử riêng các luồng KV, authentication, token/lease, Transit và PKI.
