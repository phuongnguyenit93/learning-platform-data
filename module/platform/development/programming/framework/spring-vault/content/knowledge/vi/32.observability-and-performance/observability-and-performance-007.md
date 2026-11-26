# Chọn số kết nối và giới hạn đồng thời

## 1. Vì sao số kết nối tới Vault ảnh hưởng cả hiệu năng lẫn độ tin cậy?

Một ứng dụng Spring Boot có thể đồng thời đọc secret KV, dùng Transit mã hóa dữ liệu, lấy thông tin xác thực database động và xin chứng thư PKI. Tất cả đều có thể tạo HTTP request tới **HashiCorp Vault** thông qua **Spring Vault**. Nếu mỗi request tạo một kết nối TLS mới, hệ thống tốn thời gian bắt tay và tài nguyên mạng. Nếu connection pool quá nhỏ, các luồng xử lý phải chờ lấy kết nối; nếu cho phép quá nhiều request đồng thời, ứng dụng có thể gây quá tải Vault, làm tăng timeout và tạo vòng lặp retry.

Bài học thuộc chương **Quan sát và hiệu năng** của module **SPRING_VAULT**. Trọng tâm là **chọn số kết nối và giới hạn đồng thời** cho các ứng dụng Java sử dụng `VaultTemplate`/`VaultOperations`; phối hợp với xác thực theo workload, Vault policy, vòng đời token và lease, hoạt động KV/Transit/PKI, đo lường và kiểm thử tích hợp.

Một cấu hình tốt cần trả lời đồng thời bốn câu hỏi:

1. Một instance ứng dụng cần bao nhiêu **kết nối HTTP có thể tái sử dụng** đến Vault?
2. Có bao nhiêu **lời gọi Vault được phép thực hiện đồng thời**?
3. Khi nhu cầu vượt giới hạn, request sẽ **đợi có thời hạn, bị từ chối hay được xếp hàng**?
4. Nếu một request chậm, thất bại hoặc bị retry, hệ thống có bảo vệ được **login, renewal và các luồng quan trọng khác** không?

Không có con số cố định như “mọi ứng dụng nên mở 100 kết nối”. Cần đo tải, thời gian phản hồi, quy mô replica và năng lực Vault trong môi trường gần production.

## 2. Phân biệt kết nối, đồng thời, tốc độ và luồng thực thi

Các khái niệm này liên quan nhưng **không tương đương**:

| Khái niệm | Ý nghĩa | Công cụ kiểm soát |
| --- | --- | --- |
| **TCP/TLS connection** | Kênh mạng tới Vault endpoint hoặc proxy; có thể tái sử dụng | HTTP client connection pool, keep-alive |
| **Max connections per route** | Số kết nối HTTP tối đa tới một đích/route cụ thể | HTTP connection manager |
| **Max connections total** | Tổng kết nối HTTP tối đa trong một client | HTTP connection manager |
| **In-flight requests / concurrency** | Số lời gọi đang xử lý hoặc chờ response đồng thời | Semaphore, bulkhead, worker pool |
| **Request rate / RPS** | Số request mới gửi mỗi giây | Rate limiter, token bucket, queue |
| **HTTP client thread** | Luồng thực thi chờ I/O trong client đồng bộ | Executor/thread pool hoặc virtual threads |
| **Timeout** | Thời gian cho phép tại từng giai đoạn gọi | Client request factory, HTTP client, ứng dụng |
| **Connection pool của database** | Số kết nối JDBC tới database, ví dụ HikariCP | HikariCP, **không phải** Vault HTTP pool |

Với cách gọi đồng bộ dựa trên HTTP/1.1, thường một kết nối xử lý một request đang chờ response tại một thời điểm; keep-alive giúp tái sử dụng kết nối đó cho request khác. Với HTTP/2, multiplexing có thể thay đổi mối quan hệ giữa số kết nối và số request đồng thời. **Hãy dựa trên khả năng thực tế của HTTP client/proxy/Vault trong triển khai**, không mặc định mọi kết nối luôn hỗ trợ HTTP/2.

**Tăng số kết nối không tự làm tăng RPS** nếu bottleneck nằm ở Vault storage, CPU, network, TLS proxy hoặc cơ sở dữ liệu được secrets engine sử dụng. Ngược lại, tăng số worker mà không tăng giới hạn pool có thể chỉ khiến nhiều worker chờ trong hàng đợi HTTP.

### 2.1. Ba hàng đợi cần nhìn thấy

~~~mermaid
flowchart LR
    A[HTTP/gRPC requests đến ứng dụng] --> B[Queue hoặc executor]
    B --> C[Semaphore giới hạn Vault calls]
    C --> D[HTTP client connection pool]
    D --> E[Load balancer / Vault endpoint]
    E --> F[Vault core, auth, secrets engine, storage]
    F --> G[DB/PKI backend nếu engine cần]
~~~

Một request có thể chờ ở **executor**, tiếp tục chờ **permit** và cuối cùng còn chờ **HTTP connection**. Nếu không đo từng vị trí, toàn bộ độ trễ dễ bị gán nhầm là “Vault chậm”. Tốt nhất là thiết kế một hoặc hai hàng đợi có giới hạn, thay vì tạo ba hàng đợi dài không có người chịu trách nhiệm.

## 3. Đặc điểm lưu lượng Vault trong một ứng dụng Spring Boot

Không phải mọi API của Vault có cùng độ trễ và độ quan trọng.

| Hoạt động | Ví dụ | Tính chất tải |
| --- | --- | --- |
| **KV read** | `secret/data/orders/config` | Đọc cấu hình; có thể cache theo chính sách |
| **Transit encrypt/decrypt** | `transit/encrypt/orders` | Có thể tăng theo số request nghiệp vụ; cân nhắc batch |
| **Transit rewrap** | `transit/rewrap/orders` | Tác vụ migration/batch, dễ tạo burst |
| **Database dynamic credentials** | `database/creds/orders-ro` | Mỗi lần đọc có thể **cấp credential và lease mới** |
| **PKI issue/revoke** | `pki/issue/service` | Có thể tạo hoặc thu hồi chứng thư; retry cần thận trọng |
| **Workload authentication** | Kubernetes, AppRole, JWT | Cần thiết để duy trì quyền truy cập Vault |
| **Token/lease renewal** | Gia hạn token hoặc lease | Có hạn thời gian; bị starvation có thể gây sự cố dây chuyền |

**Khác biệt quan trọng:** nhiều request KV read hoặc Transit decrypt có thể mang tính đọc; nhưng PKI issue hay Database credentials read **có tác dụng phụ** là tạo tài nguyên mới. Không dùng cùng một retry policy “thử lại mọi lỗi” cho tất cả engine.

Bên cạnh request chủ động từ controller/service, Spring Vault hoặc Spring Cloud Vault còn có thể gọi Vault để **đăng nhập lại, renew token và renew/revoke lease**. Khi sizing, phải cộng thêm luồng này và **chừa khoảng dự phòng** cho tác vụ có deadline. Nếu job encrypt dùng hết mọi connection slot và mọi worker, token/lease có thể hết hạn trước khi kịp renew.

## 4. Tính số kết nối bắt đầu từ phép đo

### 4.1. Little's Law cho số request đang xử lý

Với hệ thống tương đối ổn định, **Little's Law**:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\) là số request đang nằm trong hệ thống (trung bình).
- \(\lambda\) là lưu lượng hoàn thành trung bình, tính bằng request/giây.
- \(W\) là thời gian một request ở trong hệ thống, tính bằng giây.

Nếu đo **60 Vault request/giây cho mỗi instance** và thời gian HTTP call trung bình **120 ms** thì:

\[
L_{\mathrm{avg}} = 60 \times 0.120 = 7.2
\]

Trung bình có khoảng 7–8 request đang chờ/được phục vụ. Đây là **mức đồng thời trung bình**, không phải giá trị max connection pool nên cấu hình ngay. Lưu lượng thường tăng theo burst và thời gian phản hồi ở p95/p99 cao hơn trung bình.

### 4.2. Dùng p95 làm giả định sizing thận trọng

Giả sử cùng instance có:

- Peak throughput cần đáp ứng: **60 request/giây**.
- Latency trung bình của lời gọi Vault: **120 ms**.
- Latency p95 trong phép đo tải: **250 ms**.
- Dự phòng minh họa: **50%**.

Một phép **ước lượng capacity**, không phải Little's Law chính xác khi thay mean bằng p95:

\[
C_{\mathrm{estimate}} \approx
  60 \times 0.250 \times 1.5 = 22.5
\]

Có thể chọn một **điểm bắt đầu** như **24 kết nối per route** cho instance, **32 kết nối total**, đồng thời cho phép **20 lời gọi nghiệp vụ** ở cổng semaphore, để còn khoảng trống cho các request quản trị/renewal dùng cùng HTTP pool.

Các con số là **giả định bài tập**, không phải khuyến nghị mặc định của HashiCorp hoặc Spring. Phải kiểm chứng dưới tải thật và cân nhắc cách Spring Vault phục vụ auth/session. Một semaphore 20 permit không tự dành riêng 4 connection cho renewal nếu pool có nhiều caller khác không đi qua cùng gate; cần xác định rõ các client cùng dùng pool và điều phối mức ưu tiên.

### 4.3. Tính tổng theo số replica

Nếu mỗi Pod cho phép tối đa **24 kết nối** tới Vault và có **6 Pod**:

\[
C_{\mathrm{fleet}} \leq 24 \times 6 = 144
\]

Đây mới chỉ là một nhóm service; phải cộng workload khác, CI jobs, Vault Agent/proxy và tác vụ quản trị. Khi HPA scale từ 6 lên 20 Pod, mức kết nối tiềm năng thành **480**, dù cấu hình mỗi Pod không đổi.

**Vì vậy cần đo cả cấp instance và cấp cụm.** Giới hạn per-Pod không thay thế một cơ chế kiểm soát tổng tải của cả fleet nếu autoscaling có thể khiến mọi Pod cùng tăng lưu lượng.

### 4.4. Một công thức không giải quyết được mọi bottleneck

Nếu Vault backend chịu tải cao, tăng `maxConnections` không làm latency giảm. Nếu hệ thống đang thiếu connection pool, biểu đồ thường cho thấy **pending connection requests** tăng trong khi Vault CPU/storage latency vẫn thấp. Nếu lỗi bắt đầu từ token auth hoặc database plugin, triệu chứng sẽ khác.

Phương pháp đúng là **đo → giả thuyết bottleneck → thay một biến → đo lại**, không tinh chỉnh connection count chỉ dựa trên trực giác.

## 5. Cấu hình HTTP connection pool cho Spring Vault

`VaultOperations`/`VaultTemplate` thường gọi REST API qua thành phần HTTP client đồng bộ. Tùy phiên bản Spring Framework, Spring Vault và cách cấu hình, HTTP transport có thể sử dụng JDK HTTP hoặc Apache HttpClient. Để tận dụng connection pooling có kiểm soát, một cách làm là cung cấp `ClientHttpRequestFactory` dùng Apache HttpClient với pool riêng cho Vault.

### 5.1. Ví dụ Spring Boot 3 / Spring Framework 6 + Apache HttpClient 5

Ví dụ dưới đây sử dụng **HttpClient 5** và một connection manager có giới hạn. Dependency cần phù hợp với phiên bản Spring của dự án, ví dụ `org.apache.httpcomponents.client5:httpclient5`. Đừng trộn nhầm import Apache HttpClient **4.x** và **5.x**.

~~~java
package com.example.vault.config;

import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.http.io.SocketConfig;
import org.apache.hc.core5.util.Timeout;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;

@Configuration
public class VaultHttpPoolConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient vaultHttpClient() {
        PoolingHttpClientConnectionManager manager =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(32)
                        .setMaxConnPerRoute(24)
                        .setDefaultSocketConfig(
                                SocketConfig.custom()
                                        .setSoTimeout(Timeout.ofSeconds(3))
                                        .build())
                        .build();

        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(
                        Timeout.ofMilliseconds(300))
                .setResponseTimeout(Timeout.ofSeconds(3))
                .build();

        return HttpClients.custom()
                .setConnectionManager(manager)
                .setDefaultRequestConfig(requestConfig)
                .evictExpiredConnections()
                .build();
    }

    @Bean
    ClientHttpRequestFactory vaultRequestFactory(
            CloseableHttpClient vaultHttpClient) {
        return new HttpComponentsClientHttpRequestFactory(
                vaultHttpClient);
    }
}
~~~

**Các tham số trong ví dụ:**

- `setMaxConnTotal(32)`: giới hạn tổng kết nối trong **một HTTP client**.
- `setMaxConnPerRoute(24)`: giới hạn kết nối tới một route, thường là Vault endpoint/host:port tương ứng. Nếu client đi qua proxy, cần kiểm tra cách route được xác định.
- `setConnectionRequestTimeout(300 ms)`: thời gian tối đa một request được chờ **mượn connection từ pool**.
- `setResponseTimeout(3 s)`: timeout ở giai đoạn chờ HTTP response; không thay thế ngân sách thời gian end-to-end của ứng dụng.
- `setSoTimeout(3 s)`: socket read timeout ở transport tương ứng; hành vi chính xác phụ thuộc client/version.
- `evictExpiredConnections()`: làm sạch kết nối đã hết hiệu lực theo cơ chế của HTTP client.

Ví dụ **chưa trình bày toàn bộ cấu hình TLS**: trong production phải xác minh certificate chain, hostname, truststore và các chính sách TLS của Vault/LB. Không dùng `TrustAllStrategy` hoặc tắt hostname verification để tối ưu thời gian kết nối.

**Lưu ý về connect timeout:** giới hạn thời gian bắt tay kết nối TCP và TLS cần được cấu hình riêng theo các API tương thích của HttpClient version (ví dụ connection config/manager hoặc request factory). Không cho rằng `responseTimeout` đã giới hạn mọi giai đoạn DNS, TCP connect, TLS handshake và chờ permit. Timeout tổng thể phải được kiểm tra bằng integration test.

### 5.2. Gắn request factory với VaultTemplate

Cần bảo đảm **chính HTTP client được VaultTemplate sử dụng**, không phải chỉ một `RestTemplate` khác trong ứng dụng. Ví dụ phác thảo wiring với `VaultEndpoint` và `ClientAuthentication` do ứng dụng đã cấu hình theo workload:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

@Bean
VaultOperations vaultOperations(
        VaultEndpoint vaultEndpoint,
        ClientHttpRequestFactory vaultRequestFactory,
        ClientAuthentication workloadAuthentication) {
    return new VaultTemplate(
            vaultEndpoint,
            vaultRequestFactory,
            workloadAuthentication);
}
~~~

Đây là ví dụ tích hợp để nêu rõ **HTTP factory được tiêm vào client Vault**, không phải hướng dẫn tự tạo token. Tùy Spring Vault version và session manager được dùng, constructor/configuration hỗ trợ có thể khác. Nếu dùng **Spring Cloud Vault auto-configuration**, hãy cấu hình client/factory theo extension point của phiên bản đó thay vì tạo hai bean VaultTemplate cạnh tranh hoặc tưởng thay đổi bean RestTemplate chung sẽ tự áp dụng cho Vault.

Khi cấu hình auth theo workload, cần xét cả các HTTP call để đăng nhập, renew token và xử lý lease. Nếu chúng dùng HTTP client hoặc session manager khác, phải đo và cấu hình **từng đường gọi thực sự**.

### 5.3. Pool connection cần có lifecycle

Pool là tài nguyên; nên có bean lifecycle để **đóng client khi ứng dụng dừng**, không tạo một `CloseableHttpClient` mới cho mỗi lời gọi. Cần xác minh connection reuse qua metrics hoặc trace mạng không chứa secret, và kiểm tra trường hợp Vault/LB đóng kết nối idle lâu ngày.

Nếu có HA/load balancer, các backend node có thể thay đổi. Client cần xử lý stale connections và kết nối mới an toàn; không cố ghim IP node hoặc làm mất xác minh chứng chỉ chỉ để tránh DNS/TLS overhead.

## 6. Giới hạn đồng thời bằng semaphore / bulkhead

Connection pool bảo vệ **số kết nối**, nhưng không nhất thiết bảo vệ **số lời gọi nghiệp vụ đang chờ**. Nếu 500 thread cùng gọi Vault và pool chỉ có 24 connection, 476 thread còn lại có thể chờ trong queue của connection manager, tiêu tốn tài nguyên ứng dụng và gây timeout dây chuyền.

Giải pháp là đặt một **concurrency gate** bên ngoài các thao tác Vault do nghiệp vụ chủ động tạo. Ví dụ Java 17+:

~~~java
package com.example.vault.resilience;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

public final class VaultConcurrencyGate {
    private final Semaphore permits;
    private final long maxWaitMillis;

    public VaultConcurrencyGate(
            int maxConcurrentCalls,
            Duration maxWait) {
        if (maxConcurrentCalls <= 0 || maxWait.isNegative()) {
            throw new IllegalArgumentException("Invalid bulkhead config");
        }
        this.permits = new Semaphore(maxConcurrentCalls, true);
        this.maxWaitMillis = maxWait.toMillis();
    }

    public <T> T execute(Supplier<T> operation) {
        Objects.requireNonNull(operation, "operation");

        final boolean acquired;
        try {
            acquired = permits.tryAcquire(
                    maxWaitMillis, TimeUnit.MILLISECONDS);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new VaultCallInterruptedException(interrupted);
        }

        if (!acquired) {
            throw new VaultBulkheadFullException(
                    "Vault call concurrency limit reached");
        }

        try {
            return operation.get();
        } finally {
            permits.release();
        }
    }

    public static final class VaultBulkheadFullException
            extends RuntimeException {
        public VaultBulkheadFullException(String message) {
            super(message);
        }
    }

    public static final class VaultCallInterruptedException
            extends RuntimeException {
        public VaultCallInterruptedException(Throwable cause) {
            super("Interrupted while waiting for Vault permit", cause);
        }
    }
}
~~~

Ví dụ wiring giới hạn **20 lời gọi nghiệp vụ** với thời gian đợi permit tối đa **200 ms**:

~~~java
@Bean
VaultConcurrencyGate vaultConcurrencyGate() {
    return new VaultConcurrencyGate(
            20, Duration.ofMillis(200));
}
~~~

Sử dụng với `VaultOperations`:

~~~java
VaultResponse response = gate.execute(
        () -> vaultOperations.read(
                "secret/data/orders/config"));

if (response == null || response.getData() == null) {
    throw new IllegalStateException("Missing KV response");
}
~~~

Các điểm quan trọng:

- `Semaphore` đếm **lời gọi đang trong critical section**, không phải số kết nối thực. Mọi lệnh trong một wrapper chỉ giữ permit trong thời gian thực hiện Vault call; tránh giữ permit trong lúc xử lý DB/CPU dài sau response.
- Khi vượt giới hạn, chương trình **từ chối hoặc trả backpressure** thay vì chờ vô hạn. Tầng API phải ánh xạ exception sang phản hồi phù hợp (ví dụ 503 với chính sách retry) hoặc đưa vào queue bounded.
- `finally` bảo đảm trả permit khi lời gọi ném exception.
- Khi `InterruptedException`, bảo toàn interrupt flag; không tiếp tục gọi Vault.
- Chế độ semaphore `fair=true` giảm khả năng starvation nhưng có thể giảm throughput; benchmark nếu độ trễ nhạy cảm.
- Gate phải là **singleton per application instance**, không tạo mới trong mỗi request.
- Không bọc một lời gọi `gate.execute()` vào `gate.execute()` khác cùng gate; tránh deadlock do semaphore không re-entrant.
- Nếu dùng reactive hoặc virtual threads, số thread rẻ hơn **không có nghĩa Vault chịu tải đồng thời vô hạn**. Vẫn cần bulkhead tại ranh giới I/O.

**Chưa giải quyết:** Gate này chỉ giới hạn các lời gọi **đi qua nó**. Nếu Spring Vault session, token renewal hoặc lease renewal gọi Vault ngoài gate, chúng vẫn có thể sử dụng các kết nối trong HTTP pool. Điều đó có thể có chủ đích để ưu tiên renewal; phải kiểm tra tổng tải và khả năng dành capacity thực tế.

## 7. Rate limiting khác concurrency limiting

Semaphore giữ số request đồng thời không vượt `N`. Nhưng nếu mỗi request hoàn thành trong 5 ms, gate 20 permit về lý thuyết vẫn cho phép RPS rất cao. Ngược lại, rate limiter 50 RPS có thể có 50 request cùng đang chờ nếu latency tăng lên 1 giây.

| Mục tiêu | Kỹ thuật |
| --- | --- |
| Không quá 20 lời gọi Vault đang chạy | Semaphore/bulkhead |
| Không tạo hơn 100 request Vault mỗi giây | Rate limiter/token bucket |
| Không để queue grow vô hạn | Bounded queue + thời gian đợi hữu hạn |
| Không quá 32 kết nối trong HTTP client | Connection manager |
| Không chờ quá SLA | End-to-end deadline + timeout từng giai đoạn |
| Không để batch job giành hết tài nguyên | Separate gate/worker pool, admission control |

Với nhiều Pod, giới hạn cục bộ `20 concurrent` chỉ bảo đảm **mỗi Pod** tối đa 20, không phải toàn service. Nếu cần giới hạn RPS **toàn fleet**, một hệ thống điều phối rate limit hoặc cơ chế admission control tập trung có thể cần thiết; nó cũng phải được thiết kế để không trở thành điểm lỗi duy nhất.

Không dùng connection count như công cụ rate limiting thay thế: giới hạn ít connection có thể tạo hàng chờ dài nhưng không bảo đảm số request mỗi giây nếu response rất nhanh.

## 8. Ưu tiên request có deadline: authentication và lease renewal

Một rủi ro vận hành là **starvation**. Job batch gọi Transit có thể chiếm phần lớn connection và permit, trong khi một thao tác renew token hoặc database lease có deadline ngắn lại bị chặn.

### 8.1. Thiết kế hai nhóm tải

Ví dụ service có hai nhóm hoạt động:

| Nhóm | Ví dụ | Yêu cầu |
| --- | --- | --- |
| **Interactive / security-critical** | Đăng nhập lại, token/lease renewal, đọc secret cần để tiếp tục phục vụ | Deadline rõ ràng, hạn chế starvation |
| **Background / bulk** | Rewrap hàng loạt, đồng bộ mã hóa, import dữ liệu | Có thể tạm dừng, batch, giới hạn throughput |

Có thể dùng **hai concurrency gate**: gate nhỏ cho batch (ví dụ 8) và gate riêng cho request nghiệp vụ cần đáp ứng nhanh, trong khi vẫn đặt giới hạn ở HTTP connection manager. Nếu cần ưu tiên thật sự, có thể **tách HTTP client/pool** cho renewal và batch hoặc dành một lượng capacity cụ thể, không chỉ đặt tên “priority” mà tất cả đều tranh cùng pool kín slot.

Trước khi tách client, xác minh Spring Vault/session manager nào đang thực hiện renew và cách tránh tạo hai bộ quản lý token cạnh tranh. Không tự ý renew cùng token/lease từ nhiều scheduler mà không hiểu lifecycle.

### 8.2. Chống startup thundering herd

Nếu 30 Pod khởi động cùng lúc và tất cả đều:

1. Đăng nhập Vault.
2. Đọc cùng secret KV.
3. Lấy một database credential động.
4. Khởi tạo connection pool JDBC.

thì Vault và PostgreSQL có thể nhận burst lớn trong vài giây. Các kỹ thuật cần cân nhắc:

- Rolling deployment và giới hạn số Pod khởi động đồng thời.
- Jitter nhỏ ở bước không mang tính deadline, hoặc queue có kiểm soát.
- Cache cấu hình KV phù hợp với chính sách cập nhật (không cache token/credential quá hạn).
- Không cấp dynamic database credential mới cho **mỗi HTTP request**.
- Theo dõi số role/user/lease được phát hành và connection count tại PostgreSQL.
- Không retry đồng loạt khi Vault mới phục hồi.

**TTL của Vault authentication token và lease không phụ thuộc vào HTTP keep-alive.** Một connection còn mở không làm token hoặc lease tiếp tục hợp lệ; ngược lại token được renew không đồng nghĩa connection HTTP đã sẵn sàng.

## 9. Ngân sách timeout và retry khi có tải

Một request đi qua nhiều bước: chờ semaphore, chờ HTTP connection, TCP/TLS connect, gửi request, chờ Vault response, giải mã JSON và xử lý ứng dụng. Nếu mọi bước có timeout riêng lớn mà không có deadline tổng, latency người dùng có thể vượt SLA nhiều lần.

Ví dụ ngân sách minh họa cho một lời gọi trực tiếp:

| Giai đoạn | Ngưỡng khởi đầu để thử nghiệm | Ghi chú |
| --- | --- | --- |
| Chờ semaphore | 200 ms | Hết hạn thì trả backpressure |
| Chờ lấy connection | 300 ms | Pool bão hòa là tín hiệu cần đo |
| TCP/TLS connect | 1–2 s | Chỉ dùng khi cần kết nối mới |
| Chờ response | 3 s | Phụ thuộc endpoint và SLA |
| Toàn bộ lời gọi | Theo deadline nghiệp vụ, có tính retry | Không phải phép cộng tối đa bất tận |

Các ngưỡng trên **không** mặc định hợp lý cho mọi môi trường. Transit encrypt, PKI issue, dynamic database credential và KV read có thể có latency khác nhau. Hãy đo p95/p99 riêng và đặt deadline theo yêu cầu của service.

### 9.1. Retry cũng tiêu tốn connection

Mỗi lần retry là **một request mới** dùng permit, connection và capacity Vault. Khi Vault quá tải, retry không giới hạn tạo **retry storm**, làm sự cố trầm trọng hơn.

Quy tắc chung:

- Chỉ retry **lỗi tạm thời** có dấu hiệu rõ, ví dụ 429/5xx hoặc timeout theo chính sách API.
- Dùng **exponential backoff + jitter**, số lần hữu hạn và retry budget.
- Tuân thủ `Retry-After` khi backend/proxy trả header hợp lệ.
- Không retry 403 do policy, 404 do sai path, 400 do dữ liệu sai hoặc KV CAS mismatch bằng cách gửi lại payload cũ.
- Với thao tác có tác dụng phụ như `database/creds` hoặc `pki/issue`, timeout có thể xảy ra **sau khi Vault đã tạo credential/chứng thư**; cần đối soát và hạn chế phát hành trùng trước khi retry.
- Không tăng concurrency để “bù” Vault đang chậm. Khi latency tăng, số request đang xử lý cũng tăng theo; càng cần backpressure.

### 9.2. Circuit breaker không thay bulkhead

Circuit breaker có thể ngắt tạm các request sau nhiều lỗi; bulkhead giới hạn số request **đồng thời** và giới hạn hàng chờ. Chúng giải quyết những vấn đề khác nhau. Nếu dùng circuit breaker, cần xem xét cho phép các luồng login/renewal quan trọng tiếp tục theo chính sách riêng, thay vì ngắt mọi API tới Vault mà không phân biệt.

## 10. Metrics cần thu thập để chọn số kết nối

Chỉ số phải thể hiện được **Vault client** lẫn **Vault server**. Không kết luận Vault chậm chỉ từ một biểu đồ thời gian API của Spring Boot.

| Nhóm | Chỉ số | Dùng để tìm vấn đề nào? |
| --- | --- | --- |
| HTTP connection pool | **leased/active, available/idle, pending**, max total/per-route | Pool cạn, request đang chờ mượn connection |
| Application bulkhead | Số permit đang dùng, số caller chờ, từ chối do full | Concurrency cap quá thấp hoặc tải đột biến |
| HTTP calls | RPS, p50/p95/p99 latency, timeout, 429/5xx | Capacity và độ trễ thực tế |
| Operation mix | KV/Transit/PKI/database/auth/lease renew | Loại request nào tạo burst |
| Vault token/lease | Auth failures, renew success/failure, TTL còn lại | Nguy cơ không kịp gia hạn |
| Vault server | CPU, memory, request latency, storage/backend health | Vault hoặc storage có phải bottleneck? |
| Fleet | Pod count, connection potential, RPS theo Pod | Autoscaling làm tổng tải tăng thế nào? |

Tùy HTTP client, pool có thể cung cấp số liệu từ `PoolingHttpClientConnectionManager.getTotalStats()` và stats theo route. Ví dụ ý tưởng:

~~~java
// Phác thảo khi bạn giữ reference đến manager của HttpClient 5.
var stats = connectionManager.getTotalStats();

int leased = stats.getLeased();
int available = stats.getAvailable();
int pending = stats.getPending();
int max = stats.getMax();

// Đưa vào metrics kiểu gauge tại ứng dụng; không log secret.
~~~

Trong cấu hình production, manager nên được tạo dưới dạng bean/đối tượng có thể quan sát, thay vì chỉ là biến local trong factory nếu muốn gắn gauge. **Tên metric phụ thuộc code instrument và phiên bản client**, không có một bộ metric pool mặc định chung cho mọi cấu hình Spring Vault.

### 10.1. Metrics đề xuất cho ứng dụng

~~~text
app_vault_http_requests_total{operation="kv_read",result="success"}
app_vault_http_duration_seconds{operation="transit_encrypt"}
app_vault_bulkhead_active{operation_class="interactive"}
app_vault_bulkhead_rejected_total{operation_class="batch"}
app_vault_pool_leased_connections
app_vault_pool_pending_requests
app_vault_token_renew_failures_total
app_vault_lease_renew_failures_total
~~~

Các tên này chỉ là **đề xuất instrument**, không phải metric Vault chắc chắn có sẵn. Không đưa đường dẫn chứa tên khách hàng, `Vault token`, AppRole SecretID, request body, private key, plaintext hoặc ciphertext vào metric label.

### 10.2. Trace và log an toàn

Khi bật HTTP trace/observability, một request tới Vault có thể mang secret trong response (KV, database credentials), request (Transit plaintext đã Base64, token, PKI private key tùy flow) hoặc header (`X-Vault-Token`). **Không lưu raw HTTP payload hay header auth** vào trace/log tập trung.

Nên ghi những trường đã chuẩn hóa như:

- `operation_class`: `kv_read`, `transit_encrypt`, `pki_issue`, `token_renew`.
- HTTP status nhóm 2xx/4xx/5xx và loại exception.
- Thời gian chờ permit, chờ connection, thời gian response.
- Số request/tỷ lệ lỗi, số Pod, mã đối chiếu nội bộ không chứa secret.

HashiCorp Vault audit logs có thể hỗ trợ điều tra, nhưng cần kiểm soát quyền xem, retention và chính sách hash/redact; đừng giả định mọi dữ liệu trong audit luôn an toàn để xuất rộng rãi.

## 11. Cách nhận biết giới hạn nào đang nghẽn

Một số dấu hiệu thực tế:

| Dấu hiệu | Giả thuyết chính | Hành động cần kiểm chứng |
| --- | --- | --- |
| Pool `pending` tăng, Vault latency server thấp | Pool per-route quá nhỏ so với concurrency | Tăng nhẹ pool hoặc giảm gate, đo lại |
| Bulkhead bị từ chối liên tục nhưng pool còn idle | Gate/queue admission quá chặt, hoặc tải vượt mục tiêu | Điều chỉnh gate theo SLA hoặc phân loại interactive/batch |
| Vault latency p99 và 5xx tăng khi nâng concurrency | Vault/backend đã đến giới hạn | Hạ concurrency; tối ưu engine/storage hoặc scale phù hợp |
| Token/lease renewal timeout trong lúc batch chạy | Starvation hoặc chia sẻ slot không hợp lý | Dành capacity cho renewal, giảm batch concurrency |
| Connection mới tốn nhiều TLS handshake | Keep-alive thấp, idle eviction quá gắt hoặc proxy reset | Kiểm tra reuse, idle timeout, health và TLS |
| Nhiều 403 sau một thời gian hoạt động | Token hết hạn, policy/session manager lỗi | Kiểm tra re-login/renewal, không tăng connection pool |
| 429 tăng khi số Pod scale-out | Fleet vượt server-side limit | Giảm concurrency/rate và điều phối rollout |
| JDBC pool pending cao nhưng Vault call bình thường | Database pool/query là bottleneck | Chỉnh Hikari/SQL; không sửa Vault HTTP pool |

**Không nhầm connection pool của Vault với HikariCP.** Khi cấp database credential động, Spring Vault có một HTTP call để lấy credential, còn mỗi ứng dụng tạo nhiều JDBC connection tới database. Tăng `maximumPoolSize` của Hikari không trực tiếp tăng số HTTP connection tới Vault, nhưng có thể làm database backend quá tải.

## 12. Kiểm thử tải và fault injection

Để chọn số kết nối, cần đo trên môi trường test cô lập hoặc gần production. Không đưa traffic thử nghiệm nặng vào Vault production nếu chưa có kế hoạch và quyền vận hành rõ ràng.

### 12.1. Thiết kế phép thử có ý nghĩa

1. **Baseline:** một Pod, concurrency thấp, đo throughput, p50/p95/p99 của từng operation.
2. **Step load:** tăng theo bước, ví dụ 5 → 10 → 20 → 30 lời gọi đồng thời, giữ payload và tỷ lệ operation tương đương.
3. **Pool sweep:** giữ gate cố định, thử các giới hạn per-route khác nhau, quan sát pending/leased connection.
4. **Replica scaling:** tăng số Pod và tính tổng kết nối; kiểm tra 429/5xx, Vault server latency và backend.
5. **Mixed workload:** KV read + Transit encrypt cùng token/lease renewal, không chỉ một endpoint rất nhanh.
6. **Burst test:** mô phỏng nhiều Pod startup đồng thời và job rewrap chạy lúc traffic cao.
7. **Fault injection:** thêm latency cho Vault, đóng kết nối idle từ proxy, làm lỗi 503/429, mất kết nối trước/sau response.
8. **Recovery:** khôi phục Vault rồi quan sát retry storm, queue drain, token re-login và lease renewal.

Mục tiêu là tìm **điểm gãy**: khi tăng concurrency không còn tăng throughput đáng kể nhưng p99/timeout/rejection tăng mạnh. Chọn cấu hình vận hành **bên dưới điểm gãy** với headroom, thay vì tối đa hóa số connection.

### 12.2. Unit test cho giới hạn đồng thời

Một test unit có thể tạo 50 tác vụ chạy cùng gate 20 permit, dùng `AtomicInteger` đếm số tác vụ hiện đang ở trong critical section, rồi xác minh peak không vượt 20.

~~~java
// Pseudocode cho JUnit: executor và latch phải được test thiết lập.
AtomicInteger active = new AtomicInteger();
AtomicInteger peak = new AtomicInteger();

Runnable task = () -> gate.execute(() -> {
    int now = active.incrementAndGet();
    peak.accumulateAndGet(now, Math::max);
    try {
        simulateVaultLatency();
        return null;
    } finally {
        active.decrementAndGet();
    }
});

// Chạy đồng thời các task, chờ toàn bộ Future hoàn thành.
// Một số task có thể bị từ chối nếu timeout chờ permit.
assertThat(peak.get()).isLessThanOrEqualTo(20);
~~~

Test chỉ xác minh **giới hạn tại JVM**, không chứng minh HTTP client pooling, Vault latency hay fairness ở nhiều Pod. Integration test nên dùng Vault test instance, workload authentication giả lập hợp lý, token/lease có TTL ngắn để quan sát renewal và các lỗi mạng thực.

### 12.3. Kiểm thử không làm rò secret

Test load có thể tạo hàng nghìn request/trace, vì vậy dễ vô tình lộ thông tin nhạy cảm hơn bình thường. Chỉ dùng secret/test credential giả, không bật log request/response body, không dump Vault token, không gắn `reference` chứa PII vào metrics. Dọn lease, token và chứng thư test theo lifecycle phù hợp.

## 13. Quy trình chọn thông số ban đầu

Áp dụng tuần tự:

1. **Liệt kê loại request**: bao nhiêu KV, Transit, PKI, database credentials, auth/renewal trong một giây và khi peak.
2. **Đo latency**: mean, p95/p99 và timeout của từng operation từ load test phù hợp.
3. **Tính concurrency tham khảo** với `L = λ × Wmean`, rồi ước lượng headroom cho burst và p95.
4. **Chọn giới hạn HTTP pool** per route và total, có tính đến số endpoint/proxy và số replica.
5. **Đặt bulkhead nhỏ hơn hoặc tương ứng năng lực pool**, chừa capacity cho request có deadline.
6. **Đặt timeout từng giai đoạn** và end-to-end deadline; không tạo queue vô hạn.
7. **Giới hạn RPS riêng** nếu cluster có server-side rate limit hoặc nhiều Pod có thể cộng dồn tải lớn.
8. **Đo metrics** leased/pending, gate wait/rejections, error rate, p95/p99 và token/lease renew outcomes.
9. **Stress/fault test**, ghi lại ngưỡng chấp nhận và quy trình rollback.
10. **Đánh giá lại khi thay đổi** số Pod, Vault version, HTTP client, secrets engine, key policies hoặc workload mix.

### 13.1. Ví dụ quyết định sizing

Giả sử thử nghiệm cho thấy mỗi Pod đạt peak **60 Vault RPS**, p95 **250 ms**. Bắt đầu kiểm thử cấu hình:

~~~yaml
# Config vận hành của ứng dụng (minh họa, KHÔNG phải
# thuộc tính Spring Vault tự động hiểu nếu không có code bind).
app:
  vault:
    http:
      max-connections-total: 32
      max-connections-per-route: 24
      pool-wait-timeout-ms: 300
      response-timeout-ms: 3000
    bulkhead:
      max-concurrent-calls: 20
      max-wait-ms: 200
~~~

Đây là **cấu hình minh họa cho bean tự triển khai** ở các mục trên, không phải các key `spring.cloud.vault.*` có sẵn. Với 6 Pod, số connection per-route tiềm năng là 144. Kết quả load test có thể yêu cầu giảm xuống 12, tăng lên 32 hoặc tách pool tùy backend — không áp dụng máy móc.

Trong báo cáo kết quả, ghi tối thiểu: số Pod, RPS peak, mix endpoint, concurrency gate, max per-route/total, leased/pending connection, p95/p99, error rate, tỷ lệ retry, token/lease renewal success và phản ứng khi một node Vault/LB bị lỗi.

## 14. Bài thực hành

**Tình huống:** dịch vụ `orders-api` chạy 6 replica, dùng Spring Vault để đọc KV, mã hóa Transit và lấy database credentials khi khởi động. Mục tiêu đáp ứng tải thường xuyên nhưng không để job batch làm hỏng token/lease renewal.

1. Triển khai Vault test và Spring Boot client qua TLS, dùng authentication theo workload và policy chỉ cấp quyền cần thiết.
2. Gắn Apache HttpClient 5 pooling vào **Vault client thực**, không chỉ RestTemplate khác.
3. Đặt ban đầu `maxTotal=32`, `perRoute=24`, bulkhead cho nghiệp vụ `20`, rồi quan sát số connection leased/idle/pending.
4. Tạo tải hỗn hợp KV read/Transit encrypt với peak từ thấp đến cao; đo latency và RPS theo Pod.
5. Thêm một job rewrap batch; kiểm tra nếu renewal bị chậm, giảm hoặc tách concurrency của batch.
6. Mô phỏng 429, 503, 403 và timeout; chứng minh retry có giới hạn và không retry thao tác phát hành secret động một cách mù quáng.
7. Tăng số Pod để quan sát tổng số kết nối; ghi kết quả khi Vault server là bottleneck.
8. Kiểm tra log/tracing không chứa token, plaintext, AppRole SecretID, database password hoặc private key.
9. Điều chỉnh thông số dựa trên số liệu, nêu rõ tại sao cấu hình cuối cùng tốt hơn cấu hình trước.

**Câu hỏi tự kiểm tra:**

1. Số kết nối HTTP tới Vault có giống số JDBC connection của HikariCP không?
2. Vì sao `maxConnTotal=100` không bảo đảm 100 request Vault chạy đồng thời?
3. Little's Law dùng mean latency hay p95, và p95 dùng để ước lượng capacity cần ghi chú gì?
4. Nếu 20 Pod đều có `perRoute=24`, có bao nhiêu kết nối tiềm năng tới route đó?
5. Semaphore và rate limiter khác nhau thế nào?
6. Nếu HTTP pool đầy còn token/lease cần gia hạn, hệ thống cần thiết kế gì để tránh starvation?
7. Khi Vault trả 403, tại sao tăng connection pool hoặc retry nhiều lần không phải cách giải quyết?
8. Khi timeout ở `pki/issue` hoặc `database/creds`, rủi ro của retry ngay là gì?
9. Dấu hiệu nào cho thấy bottleneck nằm ở pool của Java thay vì Vault server?
10. Những thông tin nào tuyệt đối không được gắn vào metric label hoặc HTTP trace?

## 15. Kết luận

**Chọn số kết nối và giới hạn đồng thời** là một quyết định về capacity và độ tin cậy, không chỉ là chỉnh một thuộc tính HTTP client. Với **Spring Vault**, cần phối hợp **connection pooling**, **bulkhead/semaphore**, **rate limiting khi cần**, **timeout/retry có ngân sách** và **giám sát hai phía**. Sizing nên bắt đầu từ throughput, latency và tổng số replica, sau đó kiểm chứng dưới tải hỗn hợp cùng tình huống Vault chậm/lỗi.

Các lời gọi **đăng nhập, token/lease renewal, KV, Transit, PKI và database credentials** có tác dụng phụ, deadline và rủi ro khác nhau. Một cấu hình tốt bảo đảm batch job không làm cạn tài nguyên cần cho xác thực/renewal, không tạo retry storm, không ghi log secret và có thể giải thích dựa trên metrics. Đây là nền tảng để vận hành ứng dụng Java kết nối HashiCorp Vault hiệu quả và an toàn khi tăng tải.

**Tham khảo:** [HashiCorp Vault documentation](https://developer.hashicorp.com/vault/docs), [Spring Vault reference](https://docs.spring.io/spring-vault/reference/), [Apache HttpClient 5 documentation](https://hc.apache.org/httpcomponents-client-5.4.x/) và [Micrometer documentation](https://docs.micrometer.io/micrometer/reference/). Cần kiểm tra API, phiên bản và cấu hình thực tế trước khi áp dụng vào production.
