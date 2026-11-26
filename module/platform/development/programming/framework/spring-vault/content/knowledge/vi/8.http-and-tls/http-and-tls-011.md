# Kiểm tra cấu hình khi đổi HTTP client hoặc nâng phiên bản

## 1. Vì sao thay HTTP client có thể làm Spring Vault thay đổi hành vi?

Trong ứng dụng Java, **Spring Vault** là lớp tích hợp giúp `VaultTemplate` gọi HashiCorp Vault để đăng nhập theo workload, đọc KV secrets, sử dụng Transit, PKI và quản lý token/lease. Phía dưới lớp API đó là **HTTP transport** chịu trách nhiệm kết nối TCP, TLS, proxy, timeout, connection pool, redirect và gửi các HTTP header.

Khi đổi từ HTTP client dựa trên JDK sang Apache HttpClient, thay `ClientHttpRequestFactory`, hoặc nâng Spring Boot/Spring Framework/Spring Vault, code gọi:

```java
var response = vaultTemplate.read("secret/data/app/config");
```

có thể giữ nguyên nhưng **các điều kiện để request thành công đã khác**. Ví dụ, ứng dụng đột nhiên không đọc được CA nội bộ, bỏ qua proxy egress, chờ pool lâu hơn, mất `X-Vault-Namespace`, dùng khác cấu hình xác thực hoặc không khôi phục được kết nối sau khi Vault HA chuyển node.

Mục tiêu của đợt kiểm tra là chứng minh **tương đương hành vi quan sát được** trước và sau thay đổi, không phải chỉ chứng minh ứng dụng biên dịch được.

### Những lớp cần xác minh

| Lớp | Thành phần điển hình | Rủi ro khi thay client/nâng phiên bản |
| --- | --- | --- |
| Vault API | `VaultTemplate`, `VaultOperations`, KV v1/v2 operations | Path, serialization, ngoại lệ hoặc phương thức có thể thay đổi. |
| HTTP integration | `RestTemplate`, request factory, HTTP interceptors | Mất header, khác cách xây URI hoặc xử lý response. |
| HTTP transport | JDK client, Apache HttpClient, Jetty/Reactor Netty khi phù hợp | Timeout, pool, retry, redirect, proxy khác nhau. |
| TLS | SSL context, truststore, hostname verification, keystore mTLS | Không tin CA, SAN sai, client certificate không được chọn. |
| Vault auth/session | Kubernetes, AppRole, token, cert auth; session manager | Login/renewal dùng client khác, lỗi chỉ xuất hiện sau TTL. |
| Hạ tầng | Vault HA, ingress, forward proxy, service mesh | Đổi route, health check, idle timeout hoặc redirect. |

Không mặc định một cấu hình có cùng **tên property** sẽ có cùng ngữ nghĩa trên mọi phiên bản.

## 2. Bắt đầu bằng bản kiểm kê trước khi thay đổi

Trước khi cập nhật dependency hoặc đổi request factory, ghi lại trạng thái thực tế của ứng dụng đang chạy. Bản kiểm kê tối thiểu nên có:

1. **Phiên bản:** JDK, Spring Boot, Spring Framework, Spring Vault, Spring Cloud Vault nếu có, HTTP client và dependency management/BOM.
2. **Kiểu tích hợp:** tạo `VaultTemplate` thủ công hay Spring Cloud Vault tự cấu hình; có `spring.config.import: "vault://"` hay không.
3. **Endpoint:** `https://...`, port, tên DNS, namespace (nếu Vault Enterprise/HCP hỗ trợ) và đường đi qua ingress/LB.
4. **HTTP transport thật:** class của `ClientHttpRequestFactory` và HTTP client cuối cùng; có nhiều transport cho login, operations và renew không.
5. **TLS:** nguồn CA/truststore, keystore client nếu cần mTLS, hostname verification và chính sách protocol/cipher.
6. **Proxy:** direct hay forward proxy, proxy authentication, bypass/no-proxy, TLS termination tại gateway.
7. **Timeout/pool:** connect, read/response, chờ cấp connection, TTL/idle eviction và tổng deadline nghiệp vụ.
8. **Authentication:** Kubernetes/AppRole/token/cert, auth mount path, session lifecycle và các role/policy tương ứng.
9. **Chỉ số nền:** latency p50/p95/p99, login error, `403`/`404`, timeout, pool pending và tỷ lệ renewal thành công.

### Mẫu bảng baseline

| Trường | Trước thay đổi | Sau thay đổi | Cách chứng minh |
| --- | --- | --- | --- |
| Vault URI | `https://vault.example.internal:8200` | Phải giữ hoặc đổi có chủ đích | Log endpoint đã che thông tin nhạy cảm. |
| Client/transport | Ví dụ JDK URLConnection | Ví dụ Apache HttpClient 5 | Inspect bean/runtime và dependency tree. |
| TLS trust | CA nội bộ | Cùng trust anchor được phê duyệt | Handshake với chứng chỉ hợp lệ/sai CA. |
| Namespace | `engineering/payments` | Không đổi ngoài kế hoạch | Capture `X-Vault-Namespace` ở HTTP mock. |
| Auth method | Kubernetes | Giữ nguyên hoặc migration riêng | Login và token lookup bằng role test. |
| Connect/read timeout | Giá trị đã đo | Ngữ nghĩa tương đương | Network fault injection. |
| Pool limits | Số thực tế | Số có tính đến replica | Concurrency/load test. |

Nếu không biết **client thực sự đang chạy**, đừng suy luận từ dependency trong build file. Một ứng dụng có Apache HttpClient trong classpath nhưng vẫn có thể dùng request factory khác, hoặc có **hai client** do thành phần bootstrap và bean nghiệp vụ cấu hình riêng.

## 3. Kiểm tra ma trận tương thích phiên bản

Đổi major version là một thay đổi **hợp đồng API và dependency**, không chỉ thay số phiên bản:

| Tình huống | Điểm cần đối chiếu | Không nên giả định |
| --- | --- | --- |
| Spring Framework 5.x → 6.x | Yêu cầu Java, HTTP request factory và thư viện client tương thích | Apache HttpClient 4 và 5 có thể thay thế chỉ bằng việc sửa import. |
| Apache HttpClient 4.x → 5.x | Namespace package `org.apache.http...` so với `org.apache.hc...`, connection manager và timeout APIs | Constructor, timeout unit và pooling giữ nguyên. |
| Spring Boot 2.x → 3.x | BOM, Spring Framework, JDK, các thư viện tích hợp | Ép Spring Vault/Spring Cloud Vault phiên bản cũ vẫn an toàn. |
| Spring Vault core upgrade | Constructor/HTTP client abstraction, exception và session management | Cấu hình hoặc extension point cũ luôn tiếp tục có tác dụng. |
| Spring Cloud Vault upgrade | Auto-configuration, Config Data, namespace/TLS/auth properties | Custom bean tạo sau startup sẽ chi phối Config Data import. |
| JDK upgrade | Truststore mặc định, TLS algorithms, disabled algorithms, security providers | Cùng certificate chain chắc chắn được JVM mới chấp nhận. |

**Làm theo dependency management/BOM tương thích** của Spring Boot và Spring Cloud release train đang dùng. Không nâng từng artifact một cách tùy tiện nếu chúng được quản lý như một bộ tương thích.

Đặc biệt, **Apache HttpClient 5** dùng các package `org.apache.hc.client5...` và `org.apache.hc.core5...`, khác HttpClient 4. Trên dòng Spring Framework 6, `HttpComponentsClientHttpRequestFactory` làm việc với Apache HttpClient 5; một ví dụ cũ dành cho HttpClient 4 có thể không biên dịch hoặc không còn đúng hành vi.

Khi thư viện có nhiều minor/patch version, đối chiếu API của **phiên bản được khóa trong dự án**. Không áp dụng một snippet từ tài liệu mới nhất cho release cũ rồi tự kết luận đã migration hoàn tất.

## 4. Xác minh đúng HTTP transport đang được sử dụng

Spring Vault có thể được tạo trực tiếp bằng `VaultEndpoint`, `ClientAuthentication` và `ClientHttpRequestFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
class VaultJdkTransportConfiguration {
    @Bean
    VaultTemplate vaultTemplate(ClientAuthentication authentication) {
        VaultEndpoint endpoint = new VaultEndpoint();
        endpoint.setScheme("https");
        endpoint.setHost("vault.example.internal");
        endpoint.setPort(8200);

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(3_000);
        factory.setReadTimeout(10_000);

        return new VaultTemplate(endpoint, authentication, factory);
    }
}
```

Đoạn này minh họa kiểu transport dựa trên HTTP stack JDK. `authentication` được Spring inject từ **một bean `ClientAuthentication` hợp lệ đã cấu hình riêng**, không phải biến lấy từ request người dùng. Với production, ưu tiên workload authentication và cấu hình TLS đầy đủ.

Khi đổi `SimpleClientHttpRequestFactory` sang Apache HttpClient, cần kiểm tra thực tế:

- Có phải **bean `VaultTemplate` đang được service sử dụng** đã nhận factory mới?
- Các request **login và token renewal** có dùng client/factory mới hay vẫn dùng transport cũ?
- Spring Cloud Vault Config Data có tạo client riêng từ rất sớm, trước khi bean tùy chỉnh tồn tại không?
- Có interceptor/header, error handler, converter hay custom SSL context bị mất trong cấu hình mới không?

**Không** chỉ thay dependency rồi cho rằng Spring tự động chuyển toàn bộ client trong ứng dụng sang implementation vừa thêm.

## 5. Ví dụ cấu hình Apache HttpClient 5 cho Spring Vault

Đây là ví dụ dành cho **Spring Framework 6.x + Apache HttpClient 5.x** cùng Spring Vault tương thích. Tập trung vào pool và các timeout; phần workload `ClientAuthentication` được định nghĩa ở bean khác.

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
public class VaultTransportConfiguration {

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

        HttpComponentsClientHttpRequestFactory requestFactory =
                new HttpComponentsClientHttpRequestFactory(vaultHttpClient);

        return new VaultTemplate(endpoint, authentication, requestFactory);
    }
}
```

Ý nghĩa của ví dụ:

1. `maxConnTotal=32` và `maxConnPerRoute=16` là **trần connection** của pool, không phải giới hạn số thread hay số Vault operations trên toàn bộ các replica.
2. `connectionRequestTimeout` giới hạn thời gian **chờ pool cấp connection**; `connectTimeout` dành cho việc tạo kết nối mới.
3. `socketTimeout`/`responseTimeout` có ngữ nghĩa theo từng API/phiên bản của Apache HttpClient 5, **không phải deadline tuyệt đối** cho toàn request.
4. Evict idle/expired connection giảm nguy cơ dùng lại socket đã bị Vault, gateway hoặc load balancer đóng.
5. `CloseableHttpClient` có vòng đời bean rõ ràng và được đóng khi ứng dụng dừng.

Đây là cấu hình **minh họa**, không phải số liệu tuning chuẩn. Với CA nội bộ, proxy hoặc mTLS, cần cấu hình **TLS material và proxy trên chính connection manager/HTTP client** của dự án. Ví dụ không tạo trust-all SSL context và không tắt hostname verification.

### 5.1. Điểm dễ sai khi migrate timeout

| Mục đích | Với HTTP client mới phải kiểm tra | Test chứng minh |
| --- | --- | --- |
| Đợi TCP connect | Đơn vị thời gian, default và nơi cấu hình connect timeout | Blackhole TCP / endpoint unreachable. |
| Đợi dữ liệu | Read/socket/response timeout có bắt đầu ở giai đoạn nào | Server chấp nhận kết nối nhưng trả response chậm. |
| Đợi pool | Có pool-acquire timeout riêng không | Giữ hết connection rồi phát request mới. |
| Deadline tổng | Có chính sách deadline từ tầng gọi nghiệp vụ không | Bao gồm cả DNS, pool, retry/backoff và response. |
| Retry | Client có tự retry thao tác nào theo mặc định/chiến lược tùy chỉnh | Inject reset, timeout và kiểm tra số lần thực sự phát request. |

**Connect timeout 3 giây + response timeout 10 giây không có nghĩa request luôn kết thúc trước giây 13.** Chờ connection từ pool, các lần retry và những giai đoạn khác có thể kéo dài thời gian.

## 6. Kiểm tra TLS, CA và mTLS sau khi đổi transport

Một lỗi phổ biến là chuyển transport nhưng không chuyển đúng **SSL context**. Kết nối `https://vault.example.internal:8200` phải tiếp tục thỏa đồng thời:

- Server certificate đi tới CA mà HTTP client mới tin cậy.
- Chứng chỉ còn hiệu lực và SAN khớp `vault.example.internal`.
- TLS protocol/cipher được JDK, HTTP client và listener/gateway cùng hỗ trợ.
- Nếu listener yêu cầu **mTLS**, client mới có keystore chứa `PrivateKeyEntry`, client certificate và chain phù hợp.

Phân biệt hai tệp:

```text
Truststore (Java tin server):
  /etc/vault/tls/vault-truststore.p12

Keystore (Java xuất trình danh tính khi mTLS):
  /etc/vault/tls/vault-client.p12
```

Các JVM properties có thể được dùng với **HTTP client dựa vào cấu hình JSSE mặc định**:

```text
-Djavax.net.ssl.trustStore=/etc/vault/tls/vault-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12

-Djavax.net.ssl.keyStore=/etc/vault/tls/vault-client.p12
-Djavax.net.ssl.keyStoreType=PKCS12
```

Cấu hình mật khẩu phải được cấp bằng cơ chế bảo mật của môi trường; không ghi mật khẩu thật vào command line, tài liệu hoặc Git. **HTTP client có SSL context riêng có thể không sử dụng** những JVM properties trên. Vì thế khi migrate sang Apache HttpClient 5 hoặc một client khác, phải chứng minh truststore/keystore thực tế đã được nạp thay vì chỉ nhìn vào cấu hình khởi động.

### Ma trận TLS tối thiểu

| Kịch bản | Hành vi mong đợi |
| --- | --- |
| CA tin cậy + hostname hợp lệ | TLS thành công, tiếp tục kiểm tra Vault auth/API. |
| CA không tin cậy | TLS bị từ chối; không gửi request chứa token. |
| SAN/hostname sai | TLS bị từ chối, dù chứng chỉ do CA đáng tin ký. |
| Certificate hết hạn | Bị từ chối theo chính sách TLS thực tế. |
| Server yêu cầu mTLS nhưng client thiếu key/cert | Handshake thất bại, không thay bằng Vault token để vượt qua. |
| Xoay CA/client certificate | Client mới nạp được material sau refresh/rollout; không dựa vào socket cũ. |

**Không** coi việc sửa lỗi bằng `--insecure`, trust-all `TrustManager` hoặc hostname verifier trả `true` là kết quả migration thành công.

## 7. Proxy, DNS và đường đi Vault HA có thể thay đổi

Khi dùng **forward proxy** để ra mạng, HTTP client mới phải biết địa chỉ proxy, xác thực proxy khi cần và quy tắc bypass cho Vault nội bộ. Biến môi trường `HTTPS_PROXY` hoặc `NO_PROXY` mà `curl` hiểu **không mặc nhiên** được mọi Java HTTP client áp dụng.

```text
Java ── HTTPS qua CONNECT ──► Egress proxy ──► Vault/Ingress

hoặc

Java ── HTTPS trực tiếp ─────────────────────► Vault API
```

Khi đổi HTTP client, cần kiểm tra:

1. **Proxy selection**: client đi qua proxy hay bypass theo đúng topology.
2. **Proxy authentication**: phân biệt HTTP `407` từ proxy và HTTP `403` từ Vault.
3. **DNS resolution**: host Vault được phân giải ở client hay phía proxy theo đường kết nối thực tế.
4. **TLS termination**: chứng chỉ Java nhận là của Vault listener, ingress hay proxy được phép inspection.
5. **Redirect**: các đích do Vault HA/`api_addr` công bố có thể truy cập và có TLS certificate hợp lệ.
6. **Token protection**: tuyệt đối không để `X-Vault-Token` bị gửi sang origin ngoài danh sách Vault được phép vì redirect hoặc URL tuyệt đối không kiểm soát.

Nếu có **reverse proxy** công bố Vault dưới một path prefix, phải kiểm thử hợp đồng rewrite `/v1/*` end-to-end. Không mặc định một bản client mới sẽ giữ nguyên base path từ `VaultEndpoint` hoặc `spring.cloud.vault.uri` khi logic xây URI thay đổi.

## 8. Header, namespace và các lớp bảo vệ HTTP

Các HTTP header bắt buộc ở những trường hợp phù hợp:

```http
GET /v1/secret/data/app/config HTTP/1.1
Host: vault.example.internal:8200
X-Vault-Namespace: engineering/payments
X-Vault-Token: <token-được-cấp-an-toàn>
```

**Chú ý:** `X-Vault-Namespace` áp dụng cho Vault Enterprise/HCP hỗ trợ namespaces; không tự thêm nó trên Vault Community rồi coi namespace đã được bật.

Khi đổi request factory, `RestTemplate`, `VaultTemplate` hay `VaultClient`, cần bảo đảm:

- `X-Vault-Token` được gắn đúng lúc, không log token và không phát token tới host khác.
- `X-Vault-Namespace` không bị mất ở **login**, KV, Transit, PKI hoặc token/lease renewal.
- Các headers `Accept`, `Content-Type` và encoding của request/response phù hợp với API.
- URL không bị nhân đôi `/v1`, namespace, `secret/data` của KV v2 hoặc path prefix của gateway.
- Không tự tái sử dụng các HTTP interceptor toàn cục có thể làm rò thông tin giữa những namespace/workload khác nhau.

### 8.1. Spring Cloud Vault và giai đoạn Config Data

Đối với ứng dụng dùng **Spring Cloud Vault**:

```yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
      connection-timeout: 3000
      read-timeout: 10000
      namespace: "engineering/payments"
      authentication: KUBERNETES
      kubernetes:
        role: payments
```

Đây là ví dụ **chỉ dành cho bản triển khai có namespace phù hợp và Kubernetes auth được cấu hình phía Vault**. Nếu không dùng namespaces, bỏ property `namespace`; role, auth mount path, service-account token và policy vẫn phải được cung cấp đúng.

`spring.config.import: "vault://"` là cơ chế Config Data, **không phải URL TLS**. Config Data có thể truy cập Vault **trước khi bean ứng dụng thông thường được tạo**. Khi nâng Spring Cloud Vault, hãy kiểm tra proxy, truststore, namespace, authentication và timeout của **bootstrap/config-import client**, không chỉ bean `VaultTemplate` nghiệp vụ sau startup.

Các property `spring.cloud.vault.*` là của **Spring Cloud Vault**; ứng dụng chỉ có `spring-vault-core` không tự động đọc những property đó.

## 9. Authentication và token/lease lifecycle phải được kiểm thử riêng

Đổi HTTP client đôi khi chỉ gây lỗi **sau khi ứng dụng đã chạy một thời gian**:

```text
Startup                    Runtime                  Sau một thời gian
   │                          │                             │
   ▼                          ▼                             ▼
Vault login ──► token ──► KV / Transit / PKI ──► renew token / lease
   │                          │                             │
   └── client A?               └── client B?                 └── client C?
```

Tùy cấu hình và phiên bản, các thành phần thực hiện login, API operation và renewal có thể có transport khác nhau. Hãy kiểm tra cả **các đường gọi do framework tạo**, không chỉ chỗ code nghiệp vụ gọi `vaultTemplate.read`.

| Luồng | Điều phải giữ nguyên sau migration |
| --- | --- |
| Kubernetes/AppRole login | Đúng auth mount, role, endpoint, namespace và TLS/proxy. |
| Token auth | Token có nguồn hợp lệ; không hardcode/log; policy và TTL được kiểm tra. |
| Cert auth | Client certificate thực sự đến Vault; `CERT` auth method đã được bật/configure. |
| Token renewal | HTTP transport có route/timeout và quyền phù hợp; không bỏ lỡ hạn renew. |
| Lease renewal/revocation | Dùng đúng namespace/lease ID và xử lý timeout có kiểm soát. |
| KV v2 | Đúng API path `secret/data/...`, metadata không bị nhầm với value. |
| Transit/PKI | Thao tác có side effect được quản lý retry/idempotency thận trọng. |

Nếu request cấp chứng chỉ PKI hoặc dynamic secret bị read timeout, **Vault có thể đã xử lý thành công** dù client chưa nhận response. Không mặc định retry mọi `POST`; xác minh chiến lược retry của HTTP client mới và các cơ chế retry phía ứng dụng.

Đặc biệt, việc thay đổi exception class hoặc error handler có thể làm logic `catch`/retry/re-login chạy khác đi. Đừng chỉ so sánh HTTP status; phải kiểm tra **root cause, khả năng phân biệt lỗi tạm thời và lỗi quyền**, số lần gọi thực tế và ảnh hưởng đến tài nguyên đã tạo.

## 10. Connection pool và tính toán tải khi có nhiều replica

Một client mới có thể dùng connection pool theo mặc định hoặc có cấu hình pooling khác, khiến throughput thay đổi dù Vault API không đổi.

```text
Replica A ── pool maxPerRoute=16 ─┐
Replica B ── pool maxPerRoute=16 ─┼──► Vault endpoint / LB
Replica C ── pool maxPerRoute=16 ─┘
```

Ba replica, mỗi pool giới hạn 16 connection cho cùng route, tạo trần lý thuyết **48 connection từ ba pool đó**. Đây không phải số request được hệ thống Vault đảm bảo phục vụ hay số kết nối của các client khác như agent, session manager và monitoring.

Những chỉ số cần theo dõi khi test:

- `leased`, `available`, `pending` và `max` của pool khi client hỗ trợ.
- Số request vượt **pool acquire timeout**.
- Connect/read timeout và HTTP `429`/`5xx`.
- Latency p50/p95/p99 cho **login, KV, Transit, PKI và renewal** riêng biệt.
- Số lần retry, số open socket, lỗi connection reset sau idle.
- Thay đổi lưu lượng khi auto-scale lên số replica cao nhất dự kiến.

Tăng pool size có thể làm tăng tải lên Vault/ingress, không phải luôn cải thiện hiệu năng. Khi có quá nhiều thread chờ connection, cân nhắc thêm **giới hạn đồng thời/bulkhead ở tầng ứng dụng** với timeout chờ ngắn, thay vì xếp hàng không giới hạn.

## 11. Bộ kiểm thử hồi quy cần chạy trước cutover

Nên có **test ở nhiều lớp**: unit test cấu hình/path, HTTP mock server để capture request, Vault test instance thực với TLS/auth/namespace phù hợp và load test theo topology.

| Thử nghiệm | Cách thực hiện | Điều kiện PASS |
| --- | --- | --- |
| **Endpoint cố định** | Quan sát URI cuối cùng được phát ra | Chỉ tới origin Vault được phê duyệt; không thay host do input/redirect. |
| **TLS hợp lệ/sai CA** | TLS mock server với CA test đáng tin và không tin | Trường hợp đúng thành công; trường hợp không tin bị từ chối. |
| **SAN mismatch** | Chứng thư đúng CA nhưng hostname sai | Client từ chối; không có trust-all. |
| **mTLS nếu yêu cầu** | Server yêu cầu chứng thư client | Keystore đúng thành công; thiếu key/cert thất bại. |
| **Proxy/direct** | Test route có/không qua egress proxy | HTTP client mới dùng đúng đường; `407` được phân loại rõ. |
| **Namespace/header** | Capture request login và operations | Header đúng, không mất qua proxy hoặc renew client. |
| **KV v1/v2** | Gọi test secrets với mount thực | Không nhân đôi `/v1`/`data`, không sai namespace. |
| **Connect/read/pool timeout** | Fault injection TCP, slow response, pool saturation | Thất bại có giới hạn và exception được phân loại đúng. |
| **Retry có tác dụng phụ** | Inject timeout/reset khi PKI issue hoặc dynamic secret | Không phát sinh tạo dư tài nguyên hoặc retry vô hạn. |
| **Token/lease renewal** | Dùng TTL ngắn trong môi trường test | Renewal/re-login đúng thời điểm sau migration. |
| **Vault HA failover** | Đổi active node hoặc ingress backend | Client phục hồi, route/TLS/redirect vẫn hợp lệ. |
| **Graceful shutdown** | Dừng ứng dụng khi có kết nối đang dùng | HTTP client/pool được đóng, không rò socket. |

Không dùng kết quả thành công của `curl` làm bằng chứng duy nhất. `curl` có thể dùng proxy, CA và client certificate **khác** với JVM.

### 11.1. Kiểm tra HTTP request đã được xây như mong đợi

Một mock server có thể ghi nhận:

```text
POST /v1/auth/kubernetes/login
X-Vault-Namespace: engineering/payments

GET /v1/secret/data/app/config
X-Vault-Namespace: engineering/payments
X-Vault-Token: [redacted]
```

Kiểm tra header có mặt **và không bị rò sang request ngoài Vault**. Không dump header `X-Vault-Token`, JWT, AppRole secret ID hoặc secret values vào test log/CI artifact.

### 11.2. So sánh hành vi, không chỉ loại exception

Một HTTP client mới có thể bọc `SocketTimeoutException`, lỗi TLS hoặc `IOException` thành exception ở tầng Spring khác. Những assert quá gắn với một tên class cụ thể có thể không còn phù hợp, nhưng không nên bỏ kiểm tra lỗi hoàn toàn.

Hãy assert **tính chất**: không retry thao tác ghi không an toàn, không gửi token khi TLS không xác minh, không treo vô hạn, không truy cập namespace sai và trả tín hiệu lỗi nghiệp vụ phù hợp cho upstream.

## 12. Quy trình nâng cấp hoặc đổi client có kiểm soát

Một lộ trình thực tế:

1. **Chốt baseline:** ghi chính xác phiên bản, client class, TLS/proxy/auth/namespace, metrics và các test đang PASS.
2. **Khóa ma trận phiên bản:** chọn JDK, Boot, Framework, Spring Vault/Cloud Vault và HTTP client tương thích; kiểm tra dependency tree và không trộn major không hỗ trợ.
3. **Tách cấu hình transport:** tạo một nơi quản lý endpoint, HTTP client, TLS, timeout, pooling, proxy và vòng đời bean. Tránh tạo client cho mỗi request.
4. **Chạy test trên môi trường cô lập:** xác minh URI, headers, TLS, auth, KV, Transit, PKI, renewal, proxy/HA và các tình huống lỗi.
5. **Đo hiệu năng:** so sánh p95/p99, pending, số connection, số retry và tỷ lệ thất bại dưới tải tương đương.
6. **Canary rollout:** triển khai một tỷ lệ nhỏ replica; so sánh với baseline qua cùng workload và namespace.
7. **Quan sát đủ vòng đời token/lease:** không tuyên bố thành công ngay sau khi KV read đầu tiên chạy được.
8. **Chuẩn bị rollback:** giữ cấu hình/dependency cũ có thể tái triển khai; không để rollback yêu cầu vô hiệu hóa TLS hoặc nới rộng policy.

### Khi nào nên dừng rollout?

Dừng và điều tra nếu có một trong các biểu hiện: login/renewal thất bại, `403`/`404` tăng không giải thích được, TLS/hostname validation bị tắt, namespace bị đổi, client theo redirect ra ngoài origin được phép, pool pending tăng kéo dài hoặc request có side effect bị retry ngoài chính sách.

Không coi việc “số request thành công tăng” là đủ nếu đổi client đồng thời làm lộ token, dùng trust-all, tăng thời gian chờ quá SLA hoặc tạo thêm credential/chứng chỉ ngoài dự kiến.

## 13. Tình huống tự suy luận

**Tình huống A — Sau Spring Framework upgrade, code Apache client không compile:** request factory mới dùng Apache HttpClient 5, còn ứng dụng vẫn truyền `org.apache.http.impl.client.CloseableHttpClient` từ HttpClient 4. Phải nâng dependencies, imports và builder theo phiên bản hỗ trợ; không ép kiểu hoặc thêm cả hai client một cách ngẫu nhiên.

**Tình huống B — KV đọc được, nhưng sau một giờ token hết hạn:** `VaultTemplate` nghiệp vụ đã dùng transport mới, còn client/session manager phục vụ login và renewal vẫn theo cấu hình cũ, bị chặn proxy hoặc thiếu CA. Kiểm thử toàn bộ vòng đời, không chỉ đọc KV lúc startup.

**Tình huống C — Curl HTTPS thành công, Java báo PKIX:** curl đọc `VAULT_CACERT`, nhưng Apache HttpClient mới có SSL context không nạp truststore tương ứng. Cần kiểm tra chính HTTP client của Java và trust material, không bỏ hostname verification.

**Tình huống D — Pool mới cải thiện p50 nhưng làm Vault `5xx` tăng:** mỗi replica tăng `maxPerRoute` từ 8 lên 64, tổng concurrent connections toàn cụm tăng nhiều lần. Giảm concurrency về mức có cơ sở, đo p95/p99, retry và giới hạn phía Vault/proxy.

**Tình huống E — Spring Cloud Vault cấu hình namespace đúng nhưng ứng dụng vẫn đọc root:** bean `VaultTemplate` tự tạo sau startup không dùng HTTP client/namespace của Config Data. Kiểm tra instance đang được inject, `X-Vault-Namespace` của từng request và tách đúng cấu hình login/operations.

**Tình huống F — PKI cấp trùng chứng chỉ sau client upgrade:** HTTP client mới tự retry request khi socket reset; Vault đã hoàn thành yêu cầu đầu nhưng response bị mất. Kiểm tra idempotency, chính sách retry và cách đối soát kết quả cấp phát, thay vì chỉ tăng timeout.

### Ghi nhớ

Khi đổi HTTP client hoặc nâng phiên bản trong Spring Vault, **điều phải giữ là hành vi kết nối an toàn và đúng ngữ cảnh**, không chỉ chữ ký phương thức Java. Hãy kiểm kê client thực tế, đối chiếu compatibility/BOM, kiểm tra TLS, proxy, timeout, pooling, URI/`X-Vault-Namespace`, Vault authentication/token/lease và các API KV/Transit/PKI. Chỉ cutover khi những tình huống thành công **và thất bại** đều được chứng minh bằng test qua chính transport mới, có quan sát p95/p99 và phương án rollback rõ ràng.
