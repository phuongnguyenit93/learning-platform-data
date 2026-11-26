# Header xác thực và giới hạn của interceptor tùy chỉnh

## 1. Bài toán: ai chịu trách nhiệm gắn token vào request?

Ứng dụng Java dùng **Spring Vault** để kết nối HashiCorp Vault qua `VaultTemplate`, xác thực theo workload, đọc KV secrets, quản lý token và lease, gọi Transit encryption hoặc PKI. Ngoài đường dẫn API và kết nối HTTPS, lời gọi còn cần **thông tin xác thực** để Vault kiểm tra policy.

Với hầu hết lời gọi HTTP API dùng Vault token, header quan trọng là `X-Vault-Token`. Người mới thường muốn viết một `ClientHttpRequestInterceptor` để tự thêm header này vào mọi HTTP request. Cách đó có thể chạy trong một ví dụ đơn giản, nhưng dễ sai khi ứng dụng có **login, token renewal, nhiều HTTP client, namespace, proxy và Config Data bootstrap**.

Mục tiêu của bài:

1. Biết header nào phục vụ **xác thực**, header nào chỉ chọn namespace hay điều khiển hành vi API.
2. Hiểu trách nhiệm của `ClientAuthentication`, `SessionManager`, `VaultTemplate` và transport HTTP.
3. Biết **phạm vi thực tế của interceptor tùy chỉnh**, đặc biệt khi có nhiều đường gọi Vault.
4. Tránh để token hết hạn, ghi log token, đưa token đến host không tin cậy hoặc làm sai hành vi đăng nhập.
5. Thiết kế và kiểm thử an toàn khi cần thêm header quan sát/định tuyến ngoài cơ chế xác thực chuẩn.

## 2. Các header cần phân biệt

Ví dụ một request đọc KV v2 sau khi đã đăng nhập:

```http
GET /v1/secret/data/app/config HTTP/1.1
Host: vault.example.internal:8200
X-Vault-Token: <vault-token-da-duoc-cap>
X-Vault-Namespace: engineering/payments
Accept: application/json
```

Các giá trị trong dấu `<...>` chỉ để minh họa. **Không đưa token thực vào bài học, log, screenshot hoặc thông điệp lỗi.**

| Header/thành phần | Chức năng | Điều không nên nhầm |
| --- | --- | --- |
| `X-Vault-Token` | Chuyển token dùng để Vault xác thực và kiểm tra quyền với các API yêu cầu token. | Không phải một token tự sinh từ TLS; interceptor không nên giữ token cố định bất chấp TTL. |
| `X-Vault-Namespace` | Chọn namespace xử lý HTTP request trong Vault Enterprise/HCP có hỗ trợ. | Không thay token hay policy; không phải prefix của hostname. |
| `X-Vault-Wrap-TTL` | Yêu cầu response wrapping khi API hỗ trợ. | Không phải token xác thực và không thay đổi chính sách cấp quyền. |
| `Authorization` | Header chung của HTTP, được một số giao thức/hạ tầng sử dụng. | Đừng tự áp dụng `Bearer` hoặc `Basic` thay `X-Vault-Token` nếu không có hợp đồng API rõ ràng. |
| `Proxy-Authorization` | Xác thực với **forward proxy** khi proxy yêu cầu. | Không phải credential đăng nhập Vault; không được gửi nhầm cho Vault backend. |
| `Host` và TLS SNI | Chọn HTTP origin và tên máy chủ TLS. | Không phải danh tính hay policy Vault; không cho caller tùy ý ghi đè. |

`X-Vault-Token` là header cho **lời gọi đã có Vault token**. Một request **login** bằng AppRole, Kubernetes hoặc cert auth có thể lấy token lần đầu mà chưa cần một Vault token trong header; credential login được gửi theo **hợp đồng của từng auth method**. Tự gắn `X-Vault-Token` cũ vào mọi request login thường không cần thiết và có thể làm rối quá trình chẩn đoán.

### 2.1. TLS và header xác thực là hai lớp khác nhau

```text
Java / VaultTemplate
   │
   ├── HTTPS: xác minh CA và hostname/SAN của Vault
   │          (và client certificate nếu listener yêu cầu mTLS)
   │
   └── HTTP API:
       X-Vault-Token: ...      ──► Vault auth context / policy
       X-Vault-Namespace: ... ──► namespace của request
       /v1/secret/data/...    ──► mount/path/operation
```

HTTPS bảo vệ kênh và xác minh endpoint; `X-Vault-Token` cung cấp credential cho Vault. **mTLS** ở transport cũng không tự thay thế việc đăng nhập vào Vault bằng auth method và nhận token/policy, trừ khi ứng dụng dùng **Vault certificate auth** đúng cách để lấy token.

## 3. Spring Vault quản lý xác thực như thế nào?

Ở tầng khái niệm, Spring Vault phân tách:

- **`ClientAuthentication`**: cách có được credential/token ban đầu, ví dụ `TokenAuthentication`, Kubernetes hoặc AppRole authentication.
- **`SessionManager`**: cung cấp Vault token cho hoạt động của client; tùy implementation, có thể quản lý lấy lại/gia hạn token và vòng đời session.
- **`VaultTemplate`**: thực hiện các Vault operations và sử dụng cơ chế authentication/session của Spring Vault cho các lời gọi phù hợp.
- **HTTP transport** (`ClientHttpRequestFactory` và các client bên dưới): quyết định kết nối TCP/TLS, proxy, timeout, pool và việc gửi HTTP request thực tế.

Luồng điển hình:

```text
Workload identity
      │
      ▼
ClientAuthentication ──► Vault auth login (khi cần)
      │                         │
      │                         ▼
      └─────────────────── Vault token
                                │
                                ▼
                          SessionManager
                                │
                                ▼
VaultTemplate ──► request có token phù hợp ──► Vault API
                                │
                                ▼
                  Vault kiểm tra token + policy
```

Không giả định một implementation cụ thể tự động gia hạn token chỉ vì có `ClientAuthentication`. Ví dụ `TokenAuthentication` dùng token đã cấp sẵn khác với cấu hình workload login cùng một session manager có quản lý vòng đời. Cần kiểm tra phiên bản và implementation Spring Vault/Spring Cloud Vault mà ứng dụng đang dùng.

**Kết luận quan trọng:** Nếu chỉ cần `VaultTemplate` gọi API có token, **ưu tiên dùng cơ chế authentication/session của Spring Vault**. Không nên viết interceptor riêng chỉ để bắt chước công việc gắn `X-Vault-Token` mà thư viện đã tổ chức cho nó.

## 4. Ví dụ dùng `VaultTemplate` mà không tự chèn header token

Trong ứng dụng Spring, có thể cung cấp bean `ClientAuthentication` theo workload và tạo `VaultTemplate` dùng nó:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class VaultHttpConfiguration {

    @Bean
    VaultTemplate vaultTemplate(ClientAuthentication authentication) {
        VaultEndpoint endpoint = new VaultEndpoint();
        endpoint.setScheme("https");
        endpoint.setHost("vault.example.internal");
        endpoint.setPort(8200);

        SimpleClientHttpRequestFactory requestFactory =
                new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(3_000);
        requestFactory.setReadTimeout(10_000);

        return new VaultTemplate(
                endpoint, authentication, requestFactory);
    }
}
```

Ví dụ giả định ứng dụng đã định nghĩa một bean `ClientAuthentication` phù hợp, chẳng hạn Kubernetes hoặc AppRole login. Code trên **không tự tạo một token từ nguồn không xác định**, không đính một header tĩnh và không tắt xác minh TLS.

Nếu chỉ muốn minh họa một token được cấp sẵn trong môi trường thử nghiệm:

```java
import java.util.Objects;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;

String token = Objects.requireNonNull(
        System.getenv("VAULT_TOKEN"), "Thiếu VAULT_TOKEN");
ClientAuthentication authentication = new TokenAuthentication(token);
```

`TokenAuthentication` dùng credential đã được cấp cho workload; nó **không biến token tĩnh thành token được gia hạn tự động**. Trong production, ưu tiên cơ chế xác thực theo workload, quản lý TTL, renewal và thu hồi theo yêu cầu của ứng dụng.

### 4.1. `VaultTemplate.read` dùng logical path

```java
// Mount 'secret' đã được thiết lập dưới dạng KV v2.
var response = vaultTemplate.read("secret/data/app/config");
```

Ở đây:

- `VaultEndpoint` xác định **scheme, host, port**, không phải giá trị `X-Vault-Token`.
- `secret/data/app/config` là **Vault API path tương đối**; không nhận URL tuyệt đối từ người gọi rồi tự thay host.
- Cơ chế authentication/session chịu trách nhiệm cung cấp token cho những lời gọi cần xác thực.
- Token vẫn phải có **Vault policy** cho đúng path; có token không có nghĩa có quyền đọc mọi secret.

## 5. Interceptor tùy chỉnh có thể và không thể làm gì?

Spring Web cung cấp `ClientHttpRequestInterceptor` cho các request được thực hiện bởi **`RestTemplate`/HTTP accessor có sử dụng interceptor đó**. Interceptor có thể quan sát hoặc bổ sung request metadata, nhưng chỉ khi nó **thật sự nằm trên đường gửi của HTTP client**.

Một sơ đồ phạm vi:

```text
Ứng dụng Spring
   ├── RestTemplate A ──► interceptor A ──► HTTP endpoint
   │
   ├── VaultTemplate ───► transport/session của VaultTemplate ─► Vault
   │
   ├── Login/session manager ──► HTTP client theo cấu hình auth
   │
   └── Spring Cloud Vault Config Data ──► client lúc bootstrap
```

Việc viết `new RestTemplate()` rồi gọi `setInterceptors(...)` chỉ tác động lên **instance RestTemplate đó**. Nó không tự gắn interceptor cho một `VaultTemplate`, session manager hoặc Spring Cloud Vault Config Data client khác.

### 5.1. Những giới hạn quan trọng

| Tình huống | Vì sao interceptor đơn lẻ có thể không đủ? |
| --- | --- |
| **Login** | Login diễn ra trước khi có token và có thể dùng HTTP client riêng. |
| **Token refresh/renewal** | Token thay đổi theo thời gian; interceptor giữ chuỗi token cố định sẽ cũ/hết hạn. |
| **Lease renewal/revoke** | Luồng quản lý lease có thể do thành phần khác phát request. |
| **Spring Cloud Vault Config Data** | Truy cập Vault rất sớm lúc bootstrap, trước khi một số bean/interceptor do ứng dụng tạo được đăng ký. |
| **Nhiều `VaultTemplate` hoặc HTTP client** | Đăng ký interceptor trên một client không tác động tới client khác. |
| **Namespace** | Header phải đúng trên **từng** request và nhất quán với token/auth mount; không phải trạng thái lưu trong connection pool. |
| **Redirect hoặc absolute URL** | Một interceptor gửi token dựa trên URL do người dùng cung cấp có thể làm lộ token nếu client chuyển sang origin khác. |
| **mTLS/TLS** | Header không cấu hình được truststore, keystore, SAN, cipher hay CA của kết nối. |
| **Reactive client** | `WebClient` dùng cơ chế filter khác; `ClientHttpRequestInterceptor` của `RestTemplate` không tự áp dụng. |

### 5.2. Thứ tự interceptor và ghi đè header

Nếu có nhiều interceptor, kết quả phụ thuộc **thứ tự áp dụng** và cách chúng chỉnh headers. Một interceptor thực hiện:

```java
request.getHeaders().set("X-Vault-Token", oldToken);
```

có thể ghi đè token đang được session manager hoặc tầng khác sử dụng, tùy request đi qua các lớp như thế nào. Nếu dùng `add(...)` thay vì `set(...)`, client có thể tạo **nhiều giá trị cho cùng một header**, dẫn tới hành vi khó dự đoán ở proxy/Vault.

Vì vậy, **không tạo hai “nguồn chân lý” của token** — một trong session manager và một trong custom interceptor. Tránh viết interceptor “sửa lỗi 403 bằng cách thay token rồi gửi lại ngay” mà không hiểu lifecycle, chính sách retry và trạng thái request.

## 6. Ví dụ interceptor an toàn hơn: metadata không nhạy cảm

Một nhu cầu hợp lý là gắn **mã tương quan request** để liên kết telemetry. Ví dụ sau dùng `RestTemplate` thông thường, **không thay đổi header xác thực**:

```java
import java.io.IOException;
import java.util.UUID;

import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.web.client.RestTemplate;

final class CorrelationIdInterceptor implements ClientHttpRequestInterceptor {
    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        request.getHeaders().set(
                "X-Request-ID", UUID.randomUUID().toString());
        return execution.execute(request, body);
    }
}

RestTemplate diagnosticsClient = new RestTemplate();
diagnosticsClient.getInterceptors().add(
        new CorrelationIdInterceptor());
```

`X-Request-ID` là metadata theo quy ước hệ thống; Vault hoặc proxy có thể bỏ qua header này. Ví dụ dùng ID **được sinh từ phía ứng dụng**, không lấy header tùy ý của người dùng để làm cơ sở tin cậy. **`diagnosticsClient` trong ví dụ không phải `VaultTemplate` đã cấu hình ở mục 4**.

Muốn interceptor tương tự áp dụng cho request của Spring Vault, cần sử dụng **cơ chế customization được phiên bản Spring Vault/transport hỗ trợ** và xác nhận request thật sự đi qua client đã được tùy chỉnh. Không tự giả định rằng thêm bean `ClientHttpRequestInterceptor` vào Spring context sẽ khiến mọi HTTP client của Vault tự phát hiện và sử dụng nó.

### 6.1. Nên quan sát gì trong interceptor?

Nên đo:

- Loại operation được mã hóa với ít giá trị, ví dụ `kv_read`, `transit_encrypt`, `token_renew`.
- Thời gian round-trip, kết quả thành công/thất bại và mã HTTP status.
- Mã correlation ID vô hại do hệ thống tạo.
- Host **đã được chuẩn hóa và cho phép**, không phải một full URL chứa query nhạy cảm.

Không log:

- `X-Vault-Token`, `Authorization`, `Proxy-Authorization`, Kubernetes JWT, AppRole SecretID.
- Request/response body chứa KV secret, Transit plaintext/ciphertext nhạy cảm, private key hoặc dữ liệu PKI.
- Mật khẩu truststore/keystore, Vault token trong query string hoặc URL có userinfo.
- Toàn bộ headers chỉ để gỡ lỗi, vì có thể chứa cả credential lẫn thông tin tenant.

Ngoài ra, một interceptor muốn đo **toàn bộ thời gian nhận response body** cần xét cách HTTP client stream/read body và đóng response. Chỉ đo đến thời điểm `execution.execute(...)` trả về chưa chắc đã bao gồm thời gian ứng dụng đọc hết body.

## 7. Tại sao không tự thêm `X-Vault-Token` cho mọi request?

### 7.1. Token có vòng đời

Token có thể có TTL, quyền renew, tính chất periodic/orphan và policy tùy phương thức cấp. Một token có thể hết hạn, bị revoke hoặc được thay bằng token mới khi workload login lại.

Nếu interceptor chụp `oldToken` lúc ứng dụng khởi động:

```text
Startup:
  oldToken = token-A
  interceptor luôn gửi token-A

Sau re-login:
  SessionManager dùng token-B
  interceptor vẫn ghi đè bằng token-A
                        │
                        ▼
                   403 / lỗi auth
```

Cách xử lý đúng là để thành phần quản lý session/token **cung cấp credential hiện hành** cho request, theo đúng lifecycle Spring Vault; không chỉ “thay biến token” không đồng bộ giữa các thread.

### 7.2. Login, renewal và API nghiệp vụ không giống nhau

- **Kubernetes/AppRole login** dùng credential login riêng và thường không cần một Vault token đã cấp từ trước.
- **KV/Transit/PKI** cần token và capability tương ứng với operation.
- **Renew/revoke** có quy tắc riêng về token/lease và quyền, không thể chữa mọi lỗi bằng cách dùng một token quản trị.
- **Response wrapping** có `X-Vault-Wrap-TTL` nhưng không phải cách xác thực; không gắn header wrapping bừa bãi vì nó thay đổi response semantics.

Với API có tác dụng phụ như PKI issue, ghi KV hay tạo secret động, interceptor **không nên âm thầm retry** mọi request sau timeout. Vault có thể đã thực hiện operation dù phía Java chưa nhận response; retry thiếu kiểm soát dễ tạo nhiều tài nguyên hoặc thay đổi trạng thái ngoài ý muốn.

## 8. Nguy cơ rò token qua HTTP client tổng quát và redirect

Giả sử một ứng dụng tạo interceptor như sau:

```text
Mọi request qua RestTemplate A:
  gắn X-Vault-Token: token-của-payments
```

Rồi tái sử dụng `RestTemplate A` để gọi cả URL của người dùng hoặc một dịch vụ khác. Khi đó token có thể được gửi đến **host không phải Vault**. Đây là lỗi ranh giới tin cậy của ứng dụng, không phải lỗi mà Vault policy có thể tự ngăn sau khi credential đã rời khỏi client.

Các biện pháp:

1. **Chỉ dùng HTTP client riêng cho Vault**, với endpoint cấu hình đáng tin, không nhận full URL từ người dùng.
2. Không gắn token theo quy tắc “mọi HTTP request đều có header `X-Vault-Token`”.
3. Kiểm soát `scheme`, `host`, `port` và các API path mà client được phép gọi; không kiểm tra URL bằng `startsWith("https://vault...")`.
4. Kiểm tra chính sách **HTTP redirect** của transport. Nếu có `Location` trỏ đến origin khác, phải biết client có theo redirect không và có chuyển tiếp header nhạy cảm không.
5. Với Vault HA/load balancer, đảm bảo mọi `api_addr` và địa chỉ redirect cần thiết đều được phê duyệt, có DNS/TLS tin cậy và nằm trong giới hạn egress.
6. Tránh dùng logging interceptor ghi nguyên URI/query, headers hoặc response body.

Một số HTTP client không chuyển tiếp header xác thực khi đổi origin; một số trường hợp có thể có hành vi khác tùy header và cấu hình. **Không dựa vào giả định chung về redirect để bảo vệ token — phải kiểm thử trên transport thực tế.**

## 9. Namespace header và rủi ro trong ứng dụng đa tenant

`X-Vault-Namespace` chọn namespace cho **từng HTTP request** trong Vault Enterprise/HCP có hỗ trợ. Header này **không** được lưu “ngầm” trên một TCP connection đã được pool dùng lại và không cấp thêm quyền cho token.

Ứng dụng đa tenant rất dễ gặp lỗi khi một interceptor lấy namespace từ context toàn cục hoặc `ThreadLocal` nhưng không giải phóng đúng:

```text
Request A (payments) ──► X-Vault-Namespace: engineering/payments
Request B (catalog)  ──► X-Vault-Namespace: engineering/catalog
```

Nếu hai request dùng chung một biến mutable `currentNamespace`, dữ liệu tenant có thể bị chéo trong môi trường concurrent. Không nhận trực tiếp namespace từ inbound HTTP header của caller để chuyển sang Vault bằng token có quyền rộng.

Giải pháp an toàn hơn:

- Ánh xạ tenant đã được xác thực → namespace theo allowlist do backend quản lý.
- Tách client/session/token theo tenant hoặc chọn namespace **per-request bằng API được thư viện hỗ trợ** với credential đúng scope.
- Với Spring Cloud Vault, cấu hình `spring.cloud.vault.namespace` cho một ứng dụng làm việc trong namespace cố định.
- Kiểm thử **cả login và operations**, cùng token/lease renewal, để bảo đảm namespace không bị bỏ sót.

Không dùng interceptor tự viết để ghi đè `X-Vault-Namespace` một cách mù quáng nếu client Vault đã có cơ chế namespace riêng; giống header token, phải có một nguồn cấu hình rõ ràng.

## 10. Spring Cloud Vault và giới hạn lúc bootstrap

Spring Cloud Vault có thể tải cấu hình từ Vault ngay lúc ứng dụng khởi động qua Spring Config Data:

```yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
      authentication: KUBERNETES
      kubernetes:
        role: "payments-api"
      connection-timeout: 3000
      read-timeout: 10000
```

Trong cấu hình trên, workload cần Kubernetes ServiceAccount token và auth mount/role đúng với môi trường; TLS cần CA tin cậy và hostname hợp lệ. Đây là ví dụ rút gọn, không chứa toàn bộ cấu hình Vault server hay dependency của ứng dụng.

Điểm cần nhớ:

- Các property `spring.cloud.vault.*` thuộc **Spring Cloud Vault**, không tự áp dụng cho dự án chỉ thêm `spring-vault-core`.
- Lúc `spring.config.import: "vault://"` chạy, một bean `RestTemplateCustomizer` hoặc interceptor do ứng dụng tạo **sau bootstrap** có thể chưa tồn tại; không lấy việc nó hoạt động ở runtime làm bằng chứng rằng Config Data client đã dùng nó.
- Cấu hình namespace, authentication, TLS, proxy và timeout phải có hiệu lực tại **thời điểm** HTTP client tương ứng khởi tạo.
- Nếu dùng custom `VaultTemplate` riêng với session manager khác, cần kiểm tra đường gọi đó có thống nhất cấu hình auth hay không.

Không nên khắc phục lỗi Config Data startup bằng cách thêm `X-Vault-Token` vào một `RestTemplate` mới tạo trong `@PostConstruct`; khi code đó chạy thì quá trình lấy cấu hình sớm có thể đã thất bại.

## 11. Kiểm thử để chứng minh interceptor thực sự có tác dụng

Một HTTP mock server giúp kiểm tra header và nơi request đi tới. Sau đó phải có kiểm thử tích hợp với Vault thử nghiệm thật để xác minh hành vi login, token renewal và policy.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| `VaultTemplate` dùng `ClientAuthentication` hợp lệ | Lời gọi cần token được gửi theo cơ chế của Spring Vault, không cần interceptor token tự viết. |
| Login lần đầu | Request auth được gửi theo hợp đồng của auth method, không phụ thuộc token đã có sẵn. |
| Token bị revoke/hết TTL | Ứng dụng báo lỗi hoặc refresh/re-login theo session manager được cấu hình; không gửi mãi token cũ do interceptor. |
| Interceptor gắn trên `RestTemplate A` | Chỉ những request thực sự qua `RestTemplate A` có metadata; client Vault khác không tự kế thừa. |
| Hai interceptor cùng sửa `X-Vault-Token` | Test phát hiện ghi đè/trùng giá trị; tránh triển khai cấu hình đó. |
| Config Data import lúc startup | Client bootstrap có đủ auth, CA, namespace và proxy **trước** khi gọi Vault. |
| Request nhiều tenant song song | Namespace và credential không bị lẫn giữa các request. |
| HTTP redirect đến host không được duyệt | Không rò `X-Vault-Token` hoặc secret sang host đích; lỗi được phân loại an toàn. |
| Ghi log request thất bại | Không xuất hiện token, JWT, SecretID, private key hoặc KV values. |
| Proxy trả `407`, Vault trả `403`, TLS handshake lỗi | Mỗi lỗi được phân loại ở đúng tầng, không bị interceptor che lấp nguyên nhân. |
| PKI issue/read timeout | Không tự retry POST một cách mù quáng và tạo chứng chỉ trùng. |

### 11.1. Đơn vị kiểm tra một interceptor không chứa token

Với `CorrelationIdInterceptor` ở mục 6, test có thể mock `ClientHttpRequestExecution` và kiểm tra:

1. Request sau interceptor có header `X-Request-ID` theo định dạng dự kiến.
2. Header `X-Vault-Token` hiện hữu (nếu caller đã gắn đúng) **không bị chỉnh sửa**.
3. Interceptor gọi `execution.execute(request, body)` đúng một lần trong kịch bản bình thường.
4. Khi transport ném `IOException`, ngoại lệ vẫn có nguyên nhân gốc phù hợp và không lộ body/headers.

**Unit test không chứng minh interceptor đã được gắn vào `VaultTemplate` thực**. Integration test phải quan sát request outgoing của đúng bean/client mà ứng dụng dùng, gồm cả đường login và renew.

### 11.2. Quan sát mà không làm lộ bí mật

Nếu cần log, nên chọn nhãn `operation=kv_read`, `status=403`, `duration_ms=...`, `outcome=error`. Không log `X-Vault-Token`, `Authorization`, `Proxy-Authorization`, body hoặc URI nếu URI có query nhạy cảm. Đặt giới hạn cardinality cho tên mount/path/tenant trong metrics.

Khi thấy `403`, kiểm tra **token/role, policy, namespace, KV v1/v2 và TTL**; khi thấy `PKIX` hoặc SAN mismatch, kiểm tra **TLS/truststore**; khi thấy `407`, kiểm tra **forward proxy authentication**. Interceptor không phải công cụ thay thế cho những bước chẩn đoán này.

## 12. Tình huống luyện tập

**Tình huống A — Thêm interceptor nhưng KV vẫn `403`:** lập trình viên đăng ký interceptor trên một `RestTemplate` mới, còn `VaultTemplate` sử dụng request factory khác. Interceptor không hề nằm trên đường gọi Vault. Cần kiểm tra client thực tế và cấu hình `ClientAuthentication`/session manager, không chỉ kiểm tra interceptor bean có tồn tại.

**Tình huống B — Tạo token lúc startup rồi giữ trong interceptor:** token hết hạn sau một thời gian, nhưng login mới đã tạo token khác. Interceptor vẫn ghi đè bằng token cũ. Cần bỏ việc giữ token tĩnh ở interceptor và để lifecycle manager của Spring Vault cấp token hiện hành.

**Tình huống C — Client HTTP dùng chung để gọi API bên ngoài:** interceptor vô điều kiện thêm `X-Vault-Token`, rồi code khác gọi URL từ request người dùng. Đây là nguy cơ lộ credential/SSRF. Tách Vault-only HTTP client, khóa endpoint/redirect và không gắn token trên transport dùng chung cho các URL bất kỳ.

**Tình huống D — Spring Cloud Vault lỗi khi startup, runtime interceptor hoạt động:** Config Data client gọi Vault trước khi interceptor bean được tạo. Cần cấu hình auth/TLS/proxy/namespace theo cơ chế bootstrap được phiên bản Spring Cloud Vault hỗ trợ.

**Tình huống E — Đăng nhập được nhưng namespace đọc KV sai:** interceptor chỉ thêm `X-Vault-Namespace` cho runtime operations, còn request Kubernetes login nằm ở namespace khác. Cần nhất quán scope của login, token, operations và renewal; namespace header không thể “sửa” token đã cấp sai phạm vi.

### Ghi nhớ

**`X-Vault-Token` là credential của mỗi lời gọi Vault cần xác thực; `X-Vault-Namespace` chọn phạm vi request; TLS bảo vệ đường truyền.** Trong Spring Vault, nên dùng `ClientAuthentication`, `SessionManager` và `VaultTemplate` để quản lý token theo đúng vòng đời. Một `ClientHttpRequestInterceptor` tùy chỉnh chỉ có hiệu lực trên **HTTP client thực sự được gắn vào**, không tự bao phủ login, Config Data bootstrap, renewal hoặc client khác. Nếu cần interceptor, ưu tiên metadata không nhạy cảm, kiểm thử thứ tự/phạm vi hoạt động, không ghi đè token và không gửi credential tới URL không tin cậy.
