# Cấu hình proxy và đường đi mạng tới Vault

## 1. Xác định đường đi trước khi cấu hình Spring Vault

Ứng dụng Java sử dụng **Spring Vault** gọi HTTP API của **HashiCorp Vault** qua `VaultTemplate` để đăng nhập theo workload, đọc KV secrets, quản lý token/lease, gọi Transit encryption hoặc PKI. Tất cả thao tác đó đều cần một đường mạng từ ứng dụng tới **Vault API endpoint**. Khi đường mạng có forward proxy, ingress, load balancer hoặc service mesh, một URL có vẻ đúng vẫn có thể thất bại vì DNS, routing, firewall, TLS hoặc cơ chế chuyển tiếp.

Ba khái niệm cần phân biệt:

| Thành phần | Đứng ở đâu? | Công việc chính | Ai cấu hình? |
| --- | --- | --- | --- |
| **Kết nối trực tiếp (direct)** | Java → Vault API endpoint | Java mở kết nối tới host/port đích. | Endpoint và mạng của ứng dụng. |
| **Forward proxy (outbound proxy)** | Java → proxy → Vault | Chuyển tiếp các kết nối đi ra từ ứng dụng; thường áp dụng chính sách egress. | HTTP client phía Java và proxy egress. |
| **Reverse proxy / ingress / load balancer** | Java → điểm vào → Vault | Cung cấp hostname, TLS, cân bằng tải, định tuyến tới Vault. | Đội hạ tầng; Java gọi hostname được công bố. |

Forward proxy và reverse proxy có thể cùng hiện diện; chúng không phải hai tên gọi cho cùng một cấu hình.

```text
Direct:
Java ───────────── HTTPS ───────────────────► Vault API :8200

Qua forward proxy:
Java ──► Egress proxy ── HTTPS tunnel ──────► Vault API :8200

Qua reverse proxy/ingress:
Java ─────── HTTPS ──► Ingress/LB ──► Vault API :8200

Kết hợp:
Java ──► Egress proxy ──► Ingress/LB ──► Vault API :8200
```

Địa chỉ mà Spring Vault cấu hình là **địa chỉ logic của Vault API mà ứng dụng cần truy cập** (ví dụ `https://vault.example.internal:8200` hoặc `https://vault.example.com`). Địa chỉ của **forward proxy** được cấu hình **riêng ở HTTP transport**; không thay `spring.cloud.vault.uri` bằng URL proxy.

## 2. Đường đi mạng gồm những lớp nào?

Một request có thể lần lượt đi qua nhiều lớp:

```text
VaultTemplate
    │
    ▼
Spring HTTP transport
    │
    ├── DNS / tên dịch vụ
    ├── Chọn direct hay forward proxy
    ├── TCP / NAT / firewall / network policy
    ├── TLS handshake và xác minh tên máy chủ
    ├── HTTP request: /v1/...
    ▼
Ingress / LB / Vault listener
    │
    ▼
Vault API: authentication → policy → KV / Transit / PKI / token-lease
```

Đây là các lớp **khác nhau**:

- **DNS:** tên host trong URL có được phân giải từ môi trường chạy Java không?
- **Đường mạng:** Pod, máy ảo hoặc container có quyền kết nối tới đúng địa chỉ và cổng không?
- **Transport:** HTTP client có thật sự dùng proxy hoặc bypass proxy như mong muốn không?
- **TLS:** endpoint xuất trình chứng chỉ từ CA đáng tin và SAN khớp host trong URI không?
- **HTTP/Vault:** request có tới đúng `/v1/...`, auth method, mount và policy không?

Ví dụ, lỗi TLS certificate và lỗi Vault trả `403` đều có thể xảy ra trên cùng URL nhưng cần xử lý ở hai lớp hoàn toàn khác nhau. Đổi policy không sửa được DNS; đổi proxy không tự cấp quyền cho token.

## 3. Truy cập trực tiếp Vault API

Khi ứng dụng Java và Vault nằm trong cùng vùng mạng có thể định tuyến, cách đơn giản nhất là gọi thẳng Vault API endpoint:

```text
Java Pod ──► Service/DNS: vault.vault.svc.cluster.local:8200
                     └──► Vault API listener
```

Ví dụ Vault endpoint nội bộ:

```text
https://vault.example.internal:8200
```

Trước khi triển khai cần xác minh:

1. **Scheme** `https` khớp với listener hoặc TLS endpoint thực tế; dev server HTTP trên cùng máy chỉ là tình huống thử nghiệm cô lập.
2. **Host** phân giải được từ đúng workload; `localhost` trong Pod/container trỏ về chính môi trường mạng cục bộ của nó, không phải một Pod Vault bất kỳ.
3. **Port** là cổng HTTP API của điểm vào, thường là `8200` khi Vault listener được công bố trực tiếp hoặc `443` với ingress HTTPS; `8201` thường là cổng giao tiếp cụm, không dùng làm HTTP API cho Java.
4. **Firewall / NetworkPolicy / route** cho phép lưu lượng từ workload tới endpoint, bao gồm chiều trả lời qua kết nối đã thiết lập.
5. **TLS trust** hợp lệ với host mà Java thực sự gọi.

Không dùng `0.0.0.0` làm đích client: đó là địa chỉ thường dùng để **bind listener phía server**. Đối với Vault HA, nên dùng endpoint có khả năng thích ứng khi node thay đổi, thay vì cố định IP một Pod.

## 4. Forward proxy: ứng dụng đi ra qua proxy egress

Forward proxy nằm trên **đường đi ra** của ứng dụng. Nó thường thực thi quy tắc cho phép/không cho phép đích đến hoặc yêu cầu xác thực proxy.

### 4.1. HTTPS qua HTTP forward proxy và phương thức CONNECT

Khi Java gọi `https://vault.example.internal:8200` qua HTTP forward proxy tại `proxy.example.internal:3128`, hành vi thường là:

```text
Java ── TCP ──► proxy.example.internal:3128
                 │
                 │ CONNECT vault.example.internal:8200
                 ▼
           Proxy mở TCP tới Vault
                 │
Java ═════════ TLS tới vault.example.internal ═══════► Vault
                 │
            HTTP request /v1/... đi trong TLS tunnel
```

Trong mô hình **CONNECT tunnel** không giải mã TLS, proxy biết đích kết nối và một số metadata mạng nhưng không đọc được Vault token hay body secret trong HTTPS. **Java vẫn phải xác minh CA, hostname/SAN của Vault** ở đầu bên kia tunnel. Cấu hình proxy không được dùng để bỏ qua xác minh TLS.

Nếu một tổ chức sử dụng **TLS inspection** tại proxy, đây là mô hình khác: proxy chủ động kết thúc TLS và cấp một chứng chỉ thay thế mà Java được cấu hình tin. Khi đó proxy trở thành điểm có thể xem nội dung HTTP và bí mật Vault; phải có phê duyệt kiến trúc, chính sách bảo vệ dữ liệu và cấu hình CA phù hợp. Với Vault, đường hầm TLS không giải mã thường đơn giản hơn về ranh giới tin cậy.

### 4.2. Proxy URL không phải Vault URL

| Thuộc tính | Ví dụ | Vai trò |
| --- | --- | --- |
| Vault URI | `https://vault.example.internal:8200` | Hostname được dùng cho Vault API, HTTP Host và xác minh TLS. |
| Forward proxy | `proxy.example.internal:3128` | Điểm mà HTTP client thực hiện kết nối mạng đầu tiên. |
| API path | `/v1/auth/kubernetes/login` | Thao tác của Vault, được client tạo theo auth method. |

Khi bật forward proxy, không tự biến URI của Vault thành `http://proxy.example.internal:3128/v1/...`. Proxy là lựa chọn **đường vận chuyển** trong HTTP client, không phải mount/API endpoint của Vault.

### 4.3. `HTTPS_PROXY`, `NO_PROXY` và Java

Nhiều công cụ dòng lệnh như `curl` hiểu các biến môi trường về proxy:

```bash
export HTTPS_PROXY="http://proxy.example.internal:3128"
export NO_PROXY="localhost,127.0.0.1,vault.vault.svc.cluster.local"
```

Đây là ví dụ cấu hình **môi trường của công cụ hỗ trợ chúng**. HTTP client Java/Spring Vault **không được bảo đảm** tự đọc `HTTPS_PROXY` hoặc `NO_PROXY`; cách xử lý tùy HTTP implementation, JVM properties và các customizer. Do đó, khi `curl` đi qua proxy thành công nhưng `VaultTemplate` không đi qua proxy, cần xem transport thực tế của ứng dụng.

Quy tắc **bypass proxy** cũng quan trọng: một Pod có thể cần gọi Vault bằng Kubernetes Service DNS trực tiếp, trong khi các endpoint ngoài cluster phải đi qua egress proxy. Cấu hình `NO_PROXY` chỉ có hiệu lực khi client đang dùng thực sự hỗ trợ và áp dụng cú pháp đó.

## 5. Cấu hình forward proxy trong Spring Vault trực tiếp

Khi tự khởi tạo `VaultTemplate`, có thể cấu hình proxy trên `ClientHttpRequestFactory`. Ví dụ dưới đây dùng `SimpleClientHttpRequestFactory` (Spring Web, dựa trên HTTP stack của JDK) và **một HTTP forward proxy**:

```java
import java.net.InetSocketAddress;
import java.net.Proxy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
class VaultNetworkConfig {
    @Bean
    VaultTemplate vaultTemplate(ClientAuthentication authentication) {
        VaultEndpoint endpoint = new VaultEndpoint();
        endpoint.setScheme("https");
        endpoint.setHost("vault.example.internal");
        endpoint.setPort(8200);

        SimpleClientHttpRequestFactory transport =
                new SimpleClientHttpRequestFactory();
        transport.setProxy(new Proxy(
                Proxy.Type.HTTP,
                new InetSocketAddress("proxy.example.internal", 3128)));
        transport.setConnectTimeout(3_000);
        transport.setReadTimeout(10_000);

        return new VaultTemplate(endpoint, authentication, transport);
    }
}
```

Ví dụ giả định ứng dụng đã khai báo bean `ClientAuthentication` hợp lệ, chẳng hạn cơ chế đăng nhập Kubernetes/AppRole theo workload. Đây là cấu hình transport/endpoint; phần tạo bean authentication, truststore và các dependency cần được cung cấp riêng.

**Hạn chế và lưu ý:**

- `setProxy` là cấu hình của **request factory cụ thể**. Nó không tự bật proxy cho HTTP client khác trong ứng dụng, như client dùng trong login/session manager hoặc token/lease renewal nếu các thành phần đó được cấu hình riêng.
- Nếu proxy cần **proxy authentication** (thường báo HTTP `407 Proxy Authentication Required`), cần cơ chế credentials an toàn theo HTTP client thực tế. Không nhúng username/password của proxy vào Vault URI, log hoặc Java source.
- Các nhu cầu như connection pool, proxy authentication phức tạp, TLS tùy chỉnh hoặc bypass theo nhiều route có thể phù hợp hơn với Apache HttpClient. Phải đối chiếu API và phiên bản Spring Framework/Apache HttpClient đang dùng, không giả định code cấu hình proxy của các major version giống nhau.
- Connect timeout chỉ giới hạn giai đoạn kết nối mà HTTP client kiểm soát; nếu proxy đã nhận CONNECT nhưng chặng sau bị chậm, cần phân biệt proxy timeout, TLS timeout, read timeout và deadline nghiệp vụ.

### 5.1. JVM proxy properties: khi nào dùng?

Với HTTP stack mặc định của JDK, có thể gặp JVM system properties:

```text
-Dhttps.proxyHost=proxy.example.internal
-Dhttps.proxyPort=3128
-Dhttp.nonProxyHosts=localhost|127.*|*.svc.cluster.local
```

`https.proxyHost`/`https.proxyPort` chọn forward proxy cho HTTPS của HTTP client **tuân theo cơ chế proxy mặc định của JVM**. `http.nonProxyHosts` là pattern bypass thường được JDK URLConnection dùng cả cho HTTPS; kiểm tra lại với HTTP client/version thực tế. Đây là cấu hình **phạm vi JVM**, có thể tác động đến các HTTP request khác ngoài Vault.

Nếu đã truyền `Proxy` trực tiếp cho request factory như ví dụ trước, đừng giả định các JVM properties sẽ ghi đè lựa chọn đó. Chọn **một nguồn cấu hình transport rõ ràng**, kiểm tra request đã đi đúng route và hạn chế xung đột giữa proxy global và proxy riêng của Vault.

## 6. Spring Cloud Vault: phân biệt bootstrap và HTTP transport

Với dự án dùng **Spring Cloud Vault**, URI đến Vault có thể được khai báo:

```yaml
spring:
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
      connection-timeout: 3000
      read-timeout: 10000
```

Các thuộc tính trên mô tả **Vault endpoint** và giới hạn chờ ở HTTP client của thành phần Spring Cloud Vault khi được hỗ trợ theo phiên bản. Chúng **không tự khai báo forward proxy**. Không tự đặt tên property kiểu `spring.cloud.vault.proxy-host` rồi giả định Spring Cloud Vault sẽ nhận nếu chưa xác minh tài liệu và khả năng customizer của phiên bản đang triển khai.

Đặc biệt khi sử dụng Config Data import:

```yaml
spring:
  config:
    import: "vault://"
```

Vault có thể được truy cập **rất sớm trong quá trình khởi động ứng dụng**, trước khi các bean `VaultTemplate` thông thường do người viết ứng dụng tạo được khởi tạo. Vì thế việc cấu hình proxy cho một `VaultTemplate` sau startup **không nhất thiết** giúp Spring Cloud Vault Config Data lấy được cấu hình từ Vault lúc bootstrap.

Khi dùng Spring Cloud Vault, hãy xác định chính xác:

1. Thành phần nào đang thực hiện HTTP call tới Vault lúc **bootstrap/config import**?
2. HTTP request factory/client được thành phần đó sử dụng có nhận **proxy, CA/truststore, timeout** và bypass rule qua cơ chế cấu hình được phiên bản hỗ trợ không?
3. Các HTTP client phục vụ **workload login, token/lease renewal và VaultTemplate nghiệp vụ** có dùng chung route/proxy hay không?

Nếu phải cấp proxy cho giai đoạn bootstrap, áp dụng cơ chế HTTP client customization hoặc JVM proxy configuration **được hỗ trợ và kiểm chứng cho bản Spring Cloud Vault cụ thể**. Không suy luận chỉ từ việc `curl` có `HTTPS_PROXY` là ứng dụng Java đã sẵn sàng.

## 7. Reverse proxy, ingress và load balancer

Khác với forward proxy, **reverse proxy** là một **điểm vào** của dịch vụ Vault. Java không nhất thiết biết proxy nội bộ định tuyến tới node nào.

### 7.1. TLS termination hay TLS passthrough?

Hai cách triển khai phổ biến:

```text
TLS termination ở ingress:
Java ── HTTPS ──► Ingress (chứng chỉ của ingress)
                            └── HTTP hoặc HTTPS riêng ──► Vault

TLS passthrough:
Java ══════════ TLS tunnel qua L4 LB ═══════════════► Vault listener
                   (Vault xuất trình chứng chỉ TLS)
```

**TLS termination** tạo hai chặng mạng riêng: kết nối Java → ingress và ingress → Vault. Ứng dụng Java chỉ kiểm tra certificate chain/SAN tại điểm kết thúc TLS nó nhìn thấy (ingress); nếu chặng backend dùng HTTPS, ingress phải xác minh chứng thư backend theo chính sách riêng.

**TLS passthrough** cho phép Vault listener là nơi thực sự kết thúc TLS, hữu ích khi Vault cần trực tiếp nhận TLS client certificate cho **Vault cert authentication**. Nếu ingress kết thúc mTLS, Vault backend thường **không tự nhìn thấy** client certificate của Java; không mặc định thay thế điều đó bằng HTTP header tùy ý.

Khi cấu hình URI cho Java, chọn **hostname và port được công bố cho client**:

```yaml
spring:
  cloud:
    vault:
      uri: "https://vault.example.com" # ingress HTTPS cổng 443
```

Không dùng port backend `:8200` nếu client chỉ được phép gọi ingress ở 443. Khi ingress có nhiều hostname, server certificate phải có SAN khớp **tên trong URI của Java**.

### 7.2. Đường dẫn API, rewrite và Host

Vault HTTP API sử dụng tiền tố `/v1`; các mount như `secret`, `transit`, `pki` là phần **đường dẫn API**, không phải thành phần của Vault endpoint:

```text
https://vault.example.com/v1/sys/health
https://vault.example.com/v1/secret/data/app/config
https://vault.example.com/v1/transit/encrypt/payment-key
```

Để tránh nhầm path prefix, phương án dễ quản lý là công bố Vault qua **hostname riêng tại gốc URL** và chuyển nguyên `/v1/*` tới Vault. Nếu gateway bắt buộc công bố `https://gateway.example.com/vault`, nó có thể cần rewrite `/vault/v1/*` thành `/v1/*`; đồng thời HTTP client/Spring Vault phải hỗ trợ base path ấy. **Không mặc định** rằng chỉ thêm `/vault` vào `spring.cloud.vault.uri` là mọi bản client sẽ tạo URL đúng.

Reverse proxy còn phải xử lý đúng `Host`, SNI, địa chỉ chuyển hướng và timeout. Các header `X-Forwarded-For` hoặc `X-Forwarded-Proto` có ý nghĩa khi được đặt bởi **proxy đáng tin**, không nên sử dụng thông tin tự khai báo từ client không tin cậy làm cơ sở cấp quyền Vault.

### 7.3. Vault HA, health check và redirect

Một cụm Vault HA có thể có node active, standby và các trạng thái khác. Load balancer cần thiết kế health check tương ứng với cách hệ thống muốn định tuyến request. Vault cung cấp `/v1/sys/health`, có thể trả những HTTP status khác `200` khi node standby, sealed hoặc chưa khởi tạo; có thể cấu hình tham số health check tùy mục tiêu kiểm tra.

Ví dụ:

```bash
curl --include --cacert vault-ca.pem \
  "https://vault.example.internal:8200/v1/sys/health"
```

Nếu proxy/LB chỉ xem mọi status không phải `200` là node lỗi, nó có thể loại standby dù standby có cơ chế phục vụ/chuyển tiếp request thích hợp. Ngược lại, chấp nhận mọi response như healthy có thể đẩy traffic vào node sealed hoặc uninitialized. Quy tắc health check phải phù hợp với topology, cách Vault HA vận hành và chính sách dự phòng thực tế.

Vault có cấu hình `api_addr` để quảng bá API address trong những ngữ cảnh như redirect. Khi client nhận redirect đến địa chỉ không phân giải được từ Pod Java, một hostname chỉ hợp lệ trong mạng node, hoặc một endpoint có chứng chỉ không khớp SAN, request có thể thất bại dù initial LB URL hoàn toàn đúng.

Hãy kiểm tra **địa chỉ công bố, khả năng truy cập các địa chỉ redirect và xác minh TLS ở mọi bước**; không sửa lỗi bằng cách tắt hostname verification hay tự động theo redirect đến host không được tin cậy.

## 8. Kubernetes và service mesh: ai đi qua proxy?

Trong Kubernetes, đường đi đến Vault có thể gồm DNS, `Service`, CNI/network policy, egress gateway và sidecar:

```text
App Pod ─► DNS vault.vault.svc.cluster.local
   │
   ├── direct qua ClusterIP Service ───────────► Vault Pods
   └── qua sidecar/egress gateway (nếu có) ────► Vault/Ingress
```

Những trường hợp thường gây nhầm lẫn:

- **Pod DNS:** tên `vault.vault.svc.cluster.local` chỉ đúng khi namespace và Service thực sự có tên như ví dụ. Một Pod ở namespace khác không tự có cùng `localhost` với Vault.
- **NetworkPolicy:** cho phép đúng lưu lượng egress TCP tới Vault API hoặc egress gateway; nếu dùng forward proxy, cho phép tới **proxy**, đồng thời bảo đảm proxy được phép truy cập Vault.
- **Service mesh sidecar:** có thể chặn và định tuyến transparent proxy tại cấp Pod. Không suy luận HTTP client Java đã chọn explicit forward proxy chỉ vì mesh route đang hoạt động.
- **mTLS trong mesh:** mTLS ở chặng sidecar ↔ sidecar/gateway là lớp transport của mesh, **không tự biến thành Vault cert auth** hay cấp Vault token cho workload.
- **DNS và SNI:** host ứng dụng dùng phải phù hợp SAN ở điểm kết thúc TLS; Service DNS và ingress DNS có thể cần certificate khác nhau.

Nếu Vault nằm **ngoài** cluster, hãy xác định egress NAT, proxy, firewall và DNS từ chính Pod ứng dụng; kiểm tra từ laptop của quản trị viên không đại diện cho mạng thực của Pod.

## 9. Timeout, connection pool và retry qua nhiều hop

Một đường mạng nhiều hop tạo ra nhiều giới hạn chờ:

```text
App ──(pool wait)──► Forward proxy ──(connect upstream)──► Ingress
  └───────── client read timeout ──────────────────────────► Vault response
```

| Giới hạn | Nơi áp dụng | Biểu hiện khi không phù hợp |
| --- | --- | --- |
| Pool-acquire timeout | Client có connection pool | Request chưa ra mạng đã hết thời gian chờ connection. |
| Connect timeout | Client khi tạo kết nối theo transport/proxy route | Không mở được kết nối trong ngân sách thời gian. |
| Proxy CONNECT/upstream timeout | Forward proxy | Proxy không mở được tunnel hoặc trả mã lỗi gateway. |
| Read/response timeout | HTTP client | Đợi dữ liệu từ Vault/đường truyền quá lâu. |
| Idle timeout | Proxy, ingress, LB, client pool | Kết nối keep-alive bị đóng, lỗi khi tái sử dụng socket. |
| Overall deadline | Lớp nghiệp vụ nếu có cơ chế kiểm soát | Cắt tổng ngân sách chờ, gồm cả retry/backoff. |

`connectTimeout=3000` và `readTimeout=10000` **không tạo thành deadline cứng 13 giây**. DNS, chờ pool, proxy, TLS, nhiều lần đọc và retry có thể làm tổng thời gian dài hơn.

Khi timeout, không mặc định POST chưa được Vault xử lý. Đặc biệt với cấp chứng chỉ PKI, tạo dynamic secret hoặc thao tác ghi, retry thiếu kiểm soát có thể tạo tài nguyên ngoài ý muốn. Cần phân biệt thao tác lặp an toàn, giới hạn retry/backoff và theo dõi tải của proxy lẫn Vault. Đối với token/lease renewal, tổng thời gian chờ phải đủ ngắn để không bỏ lỡ thời điểm gia hạn.

## 10. Chẩn đoán theo từng hop

### 10.1. Xác minh DNS và đường đi từ nơi ứng dụng chạy

Các lệnh sau chỉ để minh họa cách quan sát trong shell/Linux có công cụ tương ứng; hãy chạy trong môi trường có quyền và **cùng vùng mạng với ứng dụng**:

```bash
# Phân giải host mà ứng dụng thực sự dùng
getent hosts vault.example.internal

# Thử trực tiếp, yêu cầu kiểm tra TLS bằng CA tin cậy
curl --verbose --noproxy '*' \
  --cacert vault-ca.pem \
  "https://vault.example.internal:8200/v1/sys/health"

# Thử bằng forward proxy egress
curl --verbose \
  --proxy "http://proxy.example.internal:3128" \
  --noproxy "" \
  --cacert vault-ca.pem \
  "https://vault.example.internal:8200/v1/sys/health"
```

`--noproxy '*'` ép thử direct trong curl; `--noproxy ""` bỏ ngoại lệ proxy ở lời gọi minh họa. Các lựa chọn này chỉ chi phối **curl**, không tự thay cấu hình HTTP client của Spring Vault. `--cacert` là CA mà curl sử dụng; Java có thể đang dùng truststore khác.

Nếu proxy bị chặn, direct bị chặn hoặc endpoint chỉ cho phép một đường, **chỉ chạy cách kiểm tra mà topology cho phép**. Không coi direct thất bại là lỗi khi kiến trúc bắt buộc egress proxy.

### 10.2. Kiểm tra TLS/SNI ở điểm vào

```bash
openssl s_client \
  -connect vault.example.internal:8200 \
  -servername vault.example.internal \
  -verify_hostname vault.example.internal \
  -CAfile vault-ca.pem \
  -verify_return_error
```

Lệnh này thử **kết nối trực tiếp** tới endpoint, hữu ích khi mạng cho phép; nó không đi qua explicit forward proxy theo cấu hình của Java. Trong hệ thống buộc qua proxy, cần công cụ hỗ trợ proxy tunnel hoặc kiểm tra bằng chính HTTP client thực tế.

Khi phân tích lỗi, kiểm tra **chứng chỉ của điểm thực sự kết thúc TLS**, các SAN/CA, SNI, cổng đang gọi và cả `Location` nếu có redirect.

### 10.3. Phân loại lỗi thường gặp

| Triệu chứng | Lớp dễ liên quan | Hành động nên thực hiện |
| --- | --- | --- |
| `UnknownHostException` | DNS phía client (khi đường đi yêu cầu client resolve) | Kiểm tra DNS và host của runtime Java; phân biệt nơi client hay proxy phân giải đích. |
| `Connection refused` hoặc connect timeout | TCP/network policy/listener | Xác nhận host, port, route và nơi client đang kết nối trực tiếp (proxy hay Vault). |
| HTTP `407 Proxy Authentication Required` | Forward proxy | Cấu hình proxy credentials theo transport, không sửa Vault policy. |
| HTTP `502/503/504` do gateway trả | Reverse proxy/egress proxy/backend | Xem log proxy, khả năng kết nối upstream, health check và timeout. |
| `PKIX path building failed` | Java TLS trust | CA/truststore của HTTP client Java, chain tại endpoint TLS thật. |
| Hostname/SAN mismatch | TLS hostname verification | Tên trong URI, SNI, SAN của certificate server/ingress. |
| HTTP `404` | Gateway path rewrite hoặc Vault API/mount | Kiểm tra `/v1`, mount path, KV version và rule rewrite. |
| Redirect tới host không truy cập được | HA, `api_addr`, proxy | Kiểm tra `Location`, DNS, route và TLS cho host được quảng bá. |
| HTTP `403` từ Vault | AuthN/AuthZ | Kiểm tra token, policy, namespace và quyền từng API path. |
| Chỉ thất bại khi tải cao | Pool, LB, timeout, Vault latency | Đo pending/leased, p95/p99, timeout từng hop và retry rate. |

HTTP `503` còn có thể do trạng thái Vault (như node sealed) trên health/API endpoint. Cần xem **nơi sinh response**, đường dẫn và response body phù hợp trước khi kết luận `503` luôn do proxy.

Không ghi đầy đủ `X-Vault-Token`, proxy credentials, Vault AppRole secret ID, JWT, private key hoặc nội dung KV/Transit/PKI nhạy cảm vào log. Khi phân tích HTTP request, ghi **loại thao tác**, hostname/route (không chứa bí mật), mã lỗi, độ trễ và root cause là đủ cho phần lớn chẩn đoán.

## 11. Kiểm thử tích hợp theo đúng topology

Đối với Spring Vault, **kiểm thử phải đi qua HTTP transport và authentication thực tế**, vì một lệnh curl đơn lẻ không chứng minh `VaultTemplate`, session manager hoặc Spring Cloud Vault bootstrap đang dùng đúng proxy.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Direct từ đúng Pod/VM | DNS, TCP và TLS thành công nếu mạng cho phép; Vault trả response health/API phù hợp. |
| Bắt buộc forward proxy | Java kết nối tới proxy, proxy tạo CONNECT tunnel, TLS xác minh Vault/điểm kết thúc đúng. |
| `NO_PROXY`/bypass route | Lưu lượng tới Vault nội bộ đi direct khi cấu hình Java hỗ trợ và yêu cầu kiến trúc như vậy. |
| Proxy cần authentication | Thử sai/thiếu credentials dẫn đến lỗi proxy được phân loại riêng; không nhầm với Vault `403`. |
| Reverse proxy thêm path prefix | Request `/v1/*` được chuyển đúng; không nhân đôi `/v1` hoặc `/vault`. |
| Ingress TLS termination hoặc passthrough | CA/SAN khớp với đúng endpoint; nếu dùng cert auth, Vault có được danh tính client cần thiết. |
| HA failover/redirect | Ứng dụng có thể truy cập địa chỉ redirect nếu xuất hiện; không bị lặp redirect hoặc lỗi TLS. |
| Proxy/LB idle connection bị đóng | Connection pool khôi phục hợp lý, không retry vô hạn hay làm mất token/lease renewal. |
| Vault 403/404/5xx | Tách lỗi policy/mount/backend khỏi lỗi DNS, TCP, proxy và TLS. |

Khi thử với KV, Transit hoặc PKI, chỉ sử dụng dữ liệu thử nghiệm và role/key được cho phép. Test retry của các API có tác dụng phụ nên được thiết kế để đối soát tài nguyên đã tạo, đặc biệt nếu phía client timeout nhưng Vault có thể đã xử lý thành công.

## 12. Bốn tình huống tự suy luận

**Tình huống A — Curl dùng proxy được, Java lỗi timeout:** shell có `HTTPS_PROXY`, nhưng `SimpleClientHttpRequestFactory` trong Spring Vault chưa có proxy và JVM không được cấu hình tương ứng. Hãy kiểm tra route HTTP thực tế, đặt proxy vào request factory hoặc cơ chế JVM/client được phiên bản hỗ trợ; không thay Vault URI bằng proxy URL.

**Tình huống B — Pod đọc Vault nội bộ nhưng luôn đi qua egress proxy:** Vault Service có DNS `vault.vault.svc.cluster.local`, còn Java bị cấu hình global proxy. Nếu kiến trúc yêu cầu direct, cần xác minh bypass pattern **đúng với HTTP client Java**, network policy và DNS. Chỉ thêm `NO_PROXY` trong shell chưa chứng minh Java sẽ áp dụng.

**Tình huống C — Ingress trả 404 khi đọc KV v2:** URL ngoài là `https://gateway.example.com/vault`, gateway rewrite chưa bỏ `/vault`; Vault nhận `/vault/v1/secret/data/...` thay vì `/v1/secret/data/...`. Cần sửa hợp đồng định tuyến và xác minh client có hỗ trợ base path, không đổi policy để giải quyết lỗi rewrite.

**Tình huống D — Vault HA sau failover gửi redirect ra hostname nội bộ:** request ban đầu tới `https://vault.example.com` được, nhưng redirect chuyển sang `https://vault-node-2.internal:8200` mà Pod Java không phân giải được hoặc certificate không khớp. Cần kiểm tra `api_addr`, chính sách LB, DNS và chứng chỉ cho địa chỉ được client thực sự nhìn thấy.

### Ghi nhớ

Để Spring Vault kết nối ổn định, hãy tách **Vault endpoint** khỏi **forward proxy**, biết **TLS thực sự kết thúc ở đâu** và xác minh **DNS, TCP/port, policy mạng, /v1 API path, auth và policy Vault** theo từng hop. Khi triển khai qua Kubernetes, ingress hoặc Vault HA, cần kiểm tra đường redirect, bypass proxy, bootstrap client, timeout/pool và mọi luồng `VaultTemplate`, workload login, token/lease, KV, Transit, PKI bằng **đúng transport mà ứng dụng sử dụng**.
