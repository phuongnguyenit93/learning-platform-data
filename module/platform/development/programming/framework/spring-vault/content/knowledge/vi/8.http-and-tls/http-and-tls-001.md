# Scheme, host, port và tiền tố của địa chỉ Vault

## 1. Địa chỉ Vault mô tả điều gì?

Ứng dụng Java dùng **Spring Vault** giao tiếp với **HashiCorp Vault** qua HTTP API. Trước khi `VaultTemplate` có thể đọc KV secrets, gọi Transit, yêu cầu chứng chỉ từ PKI hay quản lý token và lease, HTTP client phải biết **địa chỉ máy chủ Vault** mà nó sẽ kết nối.

Một địa chỉ cơ sở thường có dạng:

```text
<scheme>://<host>[:<port>]
```

Ví dụ:

```text
http://127.0.0.1:8200
https://vault.example.internal:8200
https://vault.example.com
```

Địa chỉ cơ sở là nơi nhận request. Nó khác với **đường dẫn API** dùng để chọn chức năng Vault. Chẳng hạn:

```text
https://vault.example.internal:8200/v1/secret/data/payments/database
└────────── địa chỉ cơ sở ────────┘└──────── đường dẫn API ────────┘
```

| Thành phần | Giá trị ví dụ | Vai trò |
| --- | --- | --- |
| Scheme | `https` | Chỉ giao thức HTTP hay HTTPS, quyết định có dùng TLS cho kết nối đến endpoint hay không. |
| Host | `vault.example.internal` | Tên DNS hoặc địa chỉ IP có thể truy cập từ ứng dụng. |
| Port | `8200` | Cổng mà Vault API, load balancer hoặc reverse proxy đang lắng nghe. |
| Tiền tố API | `/v1` | Phần mở đầu của **đường dẫn HTTP API** do client Vault sử dụng. |
| Đường dẫn nghiệp vụ | `/secret/data/payments/database` | Chỉ mount `secret`, tuyến `data` của KV v2 và đường dẫn secret. |

Khi cấu hình Vault endpoint cho Spring Vault, thông thường chỉ truyền `https://vault.example.internal:8200`. **Không tự nối `/v1`, `/secret`, `/transit` hoặc `/pki` vào địa chỉ cơ sở**: các phần này thuộc request API hoặc cấu hình mount.

## 2. Scheme: `http` và `https`

Scheme là phần đứng trước `://`:

- `http://`: dữ liệu được gửi qua HTTP không mã hóa bằng TLS; phù hợp nhất với Vault dev server trong môi trường thử nghiệm cô lập.
- `https://`: kết nối HTTP được bảo vệ bằng TLS; dùng cho các môi trường vận hành thực tế, đặc biệt khi trao đổi token, secret và dữ liệu nhạy cảm.

Scheme phải **khớp với giao thức thực tế của endpoint nhận kết nối**. Thí dụ, khi Vault listener chỉ phục vụ HTTPS trên cổng 8200 thì cấu hình `http://vault.example.com:8200` sẽ sai dù host và port đúng. Ngược lại, dùng `https` với listener HTTP cũng gây lỗi bắt tay TLS.

TLS còn đòi hỏi hai điều kiện độc lập:

1. **Tên host hợp lệ:** tên mà Java kết nối phải phù hợp với Subject Alternative Name (SAN) của chứng chỉ TLS tại đầu kết nối (Vault hoặc proxy kết thúc TLS).
2. **Chuỗi chứng chỉ được tin cậy:** HTTP client trong JVM phải tin CA đã ký chứng chỉ. Với CA nội bộ, cần cấu hình truststore hoặc cấu hình SSL của HTTP client phù hợp.

Một URL bắt đầu bằng `https://` **chưa đủ** để khẳng định TLS đã cấu hình đúng. Không dùng cách tắt xác minh chứng chỉ làm giải pháp vận hành. Ví dụ, chứng chỉ cấp cho `vault.example.com` không mặc nhiên hợp lệ khi ứng dụng kết nối bằng địa chỉ IP `10.0.1.20`.

> Trong hệ thống có ingress hoặc load balancer kết thúc TLS, scheme của **địa chỉ ứng dụng gọi đến** phản ánh kết nối từ ứng dụng đến ingress/load balancer. Cần xem riêng cách proxy chuyển tiếp lưu lượng tới Vault ở phía sau.

## 3. Host: tên của endpoint mà ứng dụng thực sự nhìn thấy

Host có thể là DNS công khai, DNS nội bộ, tên Kubernetes Service hoặc IP. Hãy chọn theo **mạng của workload đang chạy Java**, không theo vị trí của người quản trị.

| Bối cảnh | Ví dụ host | Lưu ý |
| --- | --- | --- |
| Vault dev server chạy cùng máy với ứng dụng | `127.0.0.1` | Chỉ đúng khi ứng dụng thực sự nhìn Vault qua loopback của chính nó. |
| Mạng nội bộ | `vault.example.internal` | DNS phải phân giải được từ runtime của ứng dụng. |
| Kubernetes | `vault.vault.svc.cluster.local` | Tên Service và chứng chỉ TLS phải tương thích. |
| Đi qua ingress/load balancer | `vault.example.com` | Host là địa chỉ của điểm vào; cổng thường là 443 nếu ingress phục vụ HTTPS chuẩn. |

**Bẫy phổ biến:** `localhost` bên trong container hoặc Pod trỏ về chính container/Pod đó. Nếu Vault nằm ở service khác, `http://localhost:8200` sẽ không tự chuyển đến Vault. Tương tự, `0.0.0.0` thường là địa chỉ **bind listener** phía máy chủ, không phải host nên đặt trong cấu hình client để kết nối từ xa.

Với Vault HA, ứng dụng thường kết nối đến DNS/load balancer/Service được cấu hình cho cụm, thay vì gắn cứng một Pod hoặc node. Cấu hình `api_addr` phía Vault là địa chỉ Vault quảng bá cho một số tình huống như chuyển hướng; nó không thay cho việc đặt endpoint đúng trong ứng dụng.

## 4. Port: cổng API và cổng nội bộ không giống nhau

Giá trị `port` là cổng TCP của endpoint nhận HTTP request:

| Port | Tình huống điển hình |
| --- | --- |
| `8200` | Cổng HTTP API thường gặp của Vault khi listener dùng cấu hình tiêu chuẩn. |
| `8201` | Cổng giao tiếp cụm Vault thường gặp; **không dùng làm cổng HTTP API cho ứng dụng**. |
| `443` | HTTPS qua load balancer/ingress; có thể lược bỏ `:443` trong URL `https://`. |
| `80` | Cổng mặc định của `http://`; thường không thích hợp để truyền secret ngoài môi trường thử nghiệm cô lập. |

`https://vault.example.com` và `https://vault.example.com:443` chọn cùng cổng TCP 443. **HTTPS không tự có nghĩa là port 8200**: 8200 chỉ là giá trị listener thường gặp của Vault, còn HTTPS mặc định dùng 443 khi URL không ghi port.

Nếu hệ thống đưa Vault ra ngoài thông qua proxy cổng 443, ứng dụng phải dùng cổng **bên ngoài mà nó kết nối**, không dùng cổng 8200 của backend chỉ vì Vault đang lắng nghe ở đó.

## 5. Hiểu đúng các loại “tiền tố”

Trong hệ sinh thái Vault/Spring, nhiều tiền tố có cách viết gần nhau nhưng chức năng hoàn toàn khác:

| Tiền tố/cú pháp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `https://` hoặc `http://` | `https://vault.example.com:8200` | Scheme của URL mạng tới Vault API. |
| `/v1` | `/v1/sys/health` | Tiền tố đường dẫn của Vault HTTP API. |
| Mount path | `/secret`, `/transit`, `/pki` | Địa chỉ logic của secrets engine bên trong API. |
| `vault://` | `spring.config.import: "vault://"` | Cú pháp **Spring Cloud Vault Config Data import**; không phải giao thức TCP/HTTP dùng làm Vault server URI. |
| Tiền tố proxy (nếu có) | `/vault` | Một path do gateway đặt thêm; phụ thuộc cấu hình rewrite và khả năng hỗ trợ của client. |

### 5.1. `/v1` và mount path là các phần của request API

Vault HTTP API có tiền tố `/v1`. Phần tiếp theo phụ thuộc engine, mount và thao tác:

```text
GET  https://vault.example.internal:8200/v1/sys/health
GET  https://vault.example.internal:8200/v1/auth/token/lookup-self
GET  https://vault.example.internal:8200/v1/secret/data/payments/database
POST https://vault.example.internal:8200/v1/transit/encrypt/payment-key
POST https://vault.example.internal:8200/v1/pki/issue/web-server
```

Những đường dẫn này minh họa các API khác nhau dùng chung **một Vault endpoint**. Các mount `secret`, `transit`, `pki` và tên role/key chỉ là ví dụ; trên hệ thống thật chúng có thể mang tên khác. Đặc biệt, `/data` trong ví dụ KV v2 là thành phần tuyến API của KV v2, không phải tiền tố bắt buộc của mọi loại secret.

Khi dùng `VaultTemplate` và các operations tương ứng, thư viện đảm nhận việc tạo các URL API cần thiết. Người viết ứng dụng nên chỉ định mount và secret path ở đúng API của operations, thay vì nhúng toàn bộ URL HTTP vào tên secret.

### 5.2. `vault://` không thay `https://`

Với ứng dụng có **Spring Cloud Vault** và cơ chế Config Data, có thể gặp:

```yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
```

Ở đây:

- `spring.config.import: "vault://"` yêu cầu cơ chế tích hợp Config Data lấy cấu hình từ Vault (khi dự án có dependency/tích hợp hỗ trợ).
- `spring.cloud.vault.uri` mới là địa chỉ HTTP(S) của Vault server.

Vì vậy `vault://` **không** được thay vào `VAULT_ADDR`, `spring.cloud.vault.uri` hay scheme của `VaultEndpoint`.

### 5.3. Proxy thêm path prefix: phải kiểm tra cả đường đi

Giả sử gateway công bố Vault tại `https://gateway.example.com/vault`. Khi ấy ứng dụng đi qua hai lớp ánh xạ:

```text
Client  ->  https://gateway.example.com/vault/v1/sys/health
Gateway ->  https://vault-internal:8200/v1/sys/health
                (gateway bỏ tiền tố /vault)
```

Tuyến này chỉ hoạt động khi **gateway có rewrite đúng** và cấu hình HTTP client/Spring Vault thực sự hỗ trợ base path đó. Không mặc định cho rằng chỉ cần đặt `spring.cloud.vault.uri: https://gateway.example.com/vault` là mọi phiên bản client sẽ tự xử lý path prefix chính xác.

Lựa chọn đơn giản hơn khi triển khai là dành một hostname riêng cho Vault tại gốc URL, ví dụ `https://vault.example.com`, để các tuyến API bắt đầu ngay bằng `/v1`. Trường hợp phải dùng tiền tố proxy, hãy kiểm tra URL request thực tế, các redirect và hợp đồng rewrite của gateway.

**Namespace không phải path prefix tùy ý.** Khi dùng Vault Enterprise namespaces, namespace là ngữ cảnh riêng, thường được chuyển qua header `X-Vault-Namespace` hoặc cấu hình namespace tương ứng của client. Không tự sửa địa chỉ cơ sở thành `https://host/<namespace>/v1` khi chưa có cơ sở từ tài liệu API và cấu hình thực tế.

## 6. Cấu hình trong Spring Vault và công cụ Vault

### 6.1. Tạo `VaultEndpoint` cho `VaultTemplate`

Đối với ứng dụng sử dụng **Spring Vault trực tiếp**, có thể cấu hình từng thành phần:

```java
import java.util.Objects;

import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

VaultEndpoint endpoint = new VaultEndpoint();
endpoint.setScheme("https");
endpoint.setHost("vault.example.internal");
endpoint.setPort(8200);

// Minh họa xác thực bằng token được cấp ở runtime.
String token = Objects.requireNonNull(
    System.getenv("VAULT_TOKEN"), "VAULT_TOKEN chưa được cấu hình");
ClientAuthentication authentication = new TokenAuthentication(token);

VaultTemplate vaultTemplate = new VaultTemplate(endpoint, authentication);
```

Ví dụ trên minh họa riêng cách tạo endpoint và truyền một `ClientAuthentication` cho `VaultTemplate`. Trong môi trường thật, workload có thể dùng Kubernetes authentication, AppRole hoặc cơ chế xác thực phù hợp để tránh quản lý token tĩnh trong mã nguồn. **Địa chỉ Vault, phương thức xác thực và policy Vault là ba cấu hình có vai trò khác nhau.**

Nếu kết nối bằng HTTPS với CA riêng, Java HTTP client còn cần truststore/SSL configuration thích hợp. Việc CLI Vault đã tin CA không tự đảm bảo HTTP client chạy trong JVM cũng tin CA đó.

### 6.2. Với Spring Cloud Vault

Khi sử dụng Spring Cloud Vault để cấu hình kết nối, có hai cách khai báo endpoint thường gặp:

```yaml
# Cách 1: khai báo URI đầy đủ
spring:
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
```

Hoặc:

```yaml
# Cách 2: khai báo ba thành phần riêng
spring:
  cloud:
    vault:
      scheme: https
      host: vault.example.internal
      port: 8200
```

Chỉ chọn **một cách** làm nguồn cấu hình địa chỉ để tránh khó chẩn đoán. `uri` mô tả đầy đủ endpoint và được ưu tiên so với các giá trị host/port/scheme tách rời trong Spring Cloud Vault. Đây là thuộc tính của **Spring Cloud Vault**; một dự án chỉ thêm thư viện Spring Vault không mặc nhiên nhận được toàn bộ cơ chế cấu hình tự động này.

### 6.3. Với Vault CLI

Vault CLI dùng biến môi trường `VAULT_ADDR` cho địa chỉ server. Ví dụ trong shell kiểu Bash:

```bash
export VAULT_ADDR="https://vault.example.internal:8200"
export VAULT_CACERT="/etc/ssl/certs/vault-ca.pem" # nếu dùng CA nội bộ

vault status
```

`VAULT_ADDR` chứa **địa chỉ cơ sở**, không cần nối `/v1`. `VAULT_CACERT` hướng dẫn **Vault CLI** sử dụng CA nào; không nên nhầm với cấu hình truststore của ứng dụng Java.

## 7. Kiểm tra từng lớp trước khi đọc secret

Nên xác minh kết nối bằng endpoint ít đặc quyền trước, rồi mới kiểm tra quyền truy cập secret. Với Bash/curl:

```bash
# Chỉ sử dụng --cacert nếu phía Vault dùng CA cần chỉ định rõ.
curl --include --cacert /etc/ssl/certs/vault-ca.pem \
  "https://vault.example.internal:8200/v1/sys/health"
```

`sys/health` giúp phân biệt lỗi mạng/TLS với trạng thái của Vault. Tùy trạng thái node và tham số health check, HTTP status có thể khác `200` (ví dụ standby, sealed hoặc uninitialized). Do đó, nhận được một HTTP response từ Vault không đồng nghĩa Vault đã sẵn sàng phục vụ mọi API.

Khi cần truy cập một secret thực tế, kiểm tra tiếp mount, phiên bản engine, authentication và policy. Lỗi `403` sau khi đã kết nối HTTPS thành công thường cần xem lại token/policy, không có nghĩa là scheme hoặc port sai.

| Triệu chứng | Nguyên nhân có khả năng | Hướng kiểm tra |
| --- | --- | --- |
| DNS không phân giải được host | Sai DNS hoặc workload không truy cập được vùng DNS đó | Kiểm tra host từ chính môi trường chạy ứng dụng. |
| Connection refused / timeout | Sai port, listener không hoạt động, firewall, Service hoặc routing | Kiểm tra địa chỉ đích và cổng HTTP API; đừng nhầm với cổng cụm 8201. |
| TLS handshake thất bại | HTTP/HTTPS không khớp, CA chưa được tin hoặc chứng chỉ không khớp host | Xác nhận scheme, SAN, chuỗi chứng chỉ và truststore JVM. |
| HTTP 404 | Sai tuyến API, sai mount/KV version hoặc gateway rewrite sai | So sánh request path với `/v1` và mount thực tế; kiểm tra có bị nhân đôi tiền tố không. |
| HTTP 403 | Token thiếu quyền, sai auth context hoặc policy | Kiểm tra authentication, namespace và quyền trên đúng API path. |
| Redirect bất ngờ | Node HA/leader, `api_addr` hoặc gateway chưa cấu hình nhất quán | Kiểm tra `Location` response và địa chỉ được Vault quảng bá. |

Không đưa token vào URL, query string hoặc log để “thử kết nối”. Với request cần xác thực, token được gửi bằng cơ chế authentication/header phù hợp của client.

## 8. Tự kiểm tra bằng ba tình huống

**Tình huống A — Vault dev trên cùng máy:** listener HTTP ở cổng 8200 và Java chạy trên cùng máy. Chọn `http://127.0.0.1:8200`. Không dùng địa chỉ này khi Java chuyển sang container hoặc host khác nếu Vault không nằm trong cùng không gian mạng loopback.

**Tình huống B — Vault sau ingress HTTPS:** người dùng truy cập `https://vault.example.com` qua ingress cổng 443; backend ingress chuyển tiếp đến Vault cổng 8200. Chọn URI `https://vault.example.com` trong ứng dụng. Không thay thành `:8200` trừ khi cổng 8200 thực sự được cung cấp cho phía client.

**Tình huống C — KV v2 và Transit cùng một Vault:** `secret/data/app/db` và `transit/encrypt/app-key` là hai tuyến API trên cùng server. Dùng chung `https://vault.example.internal:8200` làm endpoint và chọn operations/mount riêng cho từng chức năng; không tạo “Vault URL” bằng cách gắn cố định `/secret` vào URI cơ sở.

### Ghi nhớ

Khi gặp một địa chỉ Vault, hãy tách rõ **scheme + host + port** (nơi kết nối), **`/v1` + mount + API path** (thao tác cần thực hiện), và **`vault://`** (tiền tố Config Data của Spring Cloud Vault, nếu có). Phân tách đúng ba lớp này giúp phát hiện nhanh lỗi HTTP/TLS, tránh cấu hình sai khi thay đổi mạng triển khai và giữ cho các thao tác `VaultTemplate` với KV, token/lease, Transit hay PKI dùng chung một endpoint ổn định.
