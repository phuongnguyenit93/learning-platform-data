# Chẩn đoán lỗi DNS, TLS handshake và kết nối bị từ chối khi dùng Spring Vault

Khi ứng dụng Java sử dụng **Spring Vault** (thường qua `VaultTemplate`) để đọc secret, mã hóa với Transit hay xin chứng chỉ từ PKI, một lỗi kết nối đến **HashiCorp Vault** có thể xuất hiện trước cả bước xác thực. Ba nhóm dễ nhầm nhất là **phân giải tên DNS thất bại**, **không thiết lập được kết nối TCP** và **TLS handshake thất bại**. Cách xử lý phụ thuộc vào *tầng nào* bị lỗi; sửa token, policy hoặc đường dẫn KV không giải quyết được lỗi xảy ra trước HTTP.

Bài này tập trung vào việc truy tìm nguyên nhân từ thông báo lỗi Java, kiểm tra từ đúng môi trường chạy workload, đối chiếu cấu hình HTTP/TLS và kiểm chứng kết nối trước khi tiếp tục kiểm tra xác thực workload, token, lease hay nghiệp vụ Vault.

## 1. Xác định tầng hỏng trước khi sửa cấu hình

Một yêu cầu điển hình của `VaultTemplate` đến `https://vault.example.internal:8200` trải qua các bước sau:

~~~mermaid
flowchart TD
    A["Ứng dụng Java / VaultTemplate"] --> B["DNS: tên máy chủ → IP"]
    B --> C["TCP: kết nối IP:8200"]
    C --> D["TLS: SNI, chứng chỉ, trust, phiên bản giao thức"]
    D --> E["HTTP: /v1/... và mã trạng thái"]
    E --> F["Vault: authentication, policy, secret engine, lease"]
    B -- "UnknownHostException" --> X["Sửa DNS / tên host"]
    C -- "ConnectException / timeout" --> Y["Kiểm tra cổng, route, Service, firewall"]
    D -- "SSLHandshakeException" --> Z["Kiểm tra CA, SAN, mTLS, protocol"]
    E -- "401 / 403 / 429 / 5xx..." --> W["Đọc phản hồi HTTP và trạng thái Vault"]
~~~

| Dấu hiệu trong ứng dụng | Tầng nghi vấn | Diễn giải đầu tiên |
| --- | --- | --- |
| `java.net.UnknownHostException`, `Name or service not known` | DNS | Tên hostname không phân giải được từ môi trường đang chạy Java. |
| `java.net.ConnectException: Connection refused` | TCP | Đích hoặc thiết bị trung gian từ chối kết nối đến IP/cổng; chưa đi đến TLS. |
| `java.net.SocketTimeoutException: connect timed out` | TCP/mạng | Không hoàn thành kết nối đúng thời hạn; khác với từ chối tức thì. |
| `javax.net.ssl.SSLHandshakeException`, `PKIX path building failed` | TLS | Thường không xây được chuỗi tin cậy của chứng chỉ máy chủ. |
| `No subject alternative DNS name matching ...` | TLS | Tên truy cập không nằm trong SAN của chứng chỉ được cung cấp. |
| `Received fatal alert: bad_certificate`, `certificate_required` | TLS/mTLS | Một phía yêu cầu hoặc từ chối chứng chỉ client; xem log hai đầu. |
| Nhận `401` hoặc `403` từ Vault | HTTP/Vault | Kết nối mạng và TLS đã đủ để nhận phản hồi; kiểm tra xác thực hoặc policy. |
| `200`, `429`, `472`, `473`, `501` hoặc `503` từ `/v1/sys/health` | HTTP/trạng thái Vault | Đã giao tiếp HTTP được; cần diễn giải vai trò/trạng thái Vault, không kết luận DNS/TLS lỗi. |

**Phân biệt quan trọng:** `Connection refused` thường nhận TCP RST nhanh; `connect timed out` thường do đường mạng, chính sách chặn hoặc địa chỉ không phản hồi. `read timed out` lại xảy ra sau khi đã kết nối và đang đợi dữ liệu. Một `ResourceAccessException` hoặc `VaultException` ở lớp Spring có thể chỉ là vỏ bọc; hãy tìm **root cause** sâu nhất trong chuỗi `Caused by:`.

## 2. Thu thập dữ kiện trong đúng runtime

Trước khi chẩn đoán, ghi nhận **URI Vault thực sự được ứng dụng dùng**, hostname, cổng, scheme `http`/`https`, vị trí workload (máy cá nhân, VM, container, Kubernetes), tên namespace, thời điểm và kiểu lỗi. Nếu có proxy hoặc load balancer, ghi rõ đường đi qua chúng. Không thu thập hoặc đưa token, private key, nội dung secret hay tiêu đề `X-Vault-Token` vào log/chụp màn hình.

Các lệnh dưới đây dùng một hostname và cổng ví dụ. Chạy chúng **từ nơi ứng dụng thực thi** hoặc từ một môi trường có cùng DNS, route, policy mạng và trust. Kết quả trên laptop có thể khác hẳn kết quả bên trong Pod.

~~~bash
export VAULT_HOST="vault.example.internal"
export VAULT_PORT="8200"
export VAULT_CA="/etc/vault/tls/ca.pem"

# 1. DNS
getent ahosts "$VAULT_HOST"
# Có thể dùng dig hoặc nslookup nếu môi trường có sẵn:
dig +short "$VAULT_HOST"

# 2. TCP: kết nối tới cổng API Vault
nc -vz -w 3 "$VAULT_HOST" "$VAULT_PORT"

# 3. TLS: gửi đúng SNI và kiểm tra hostname/chứng chỉ bằng CA đã tin cậy
openssl s_client \
  -connect "$VAULT_HOST:$VAULT_PORT" \
  -servername "$VAULT_HOST" \
  -verify_hostname "$VAULT_HOST" \
  -CAfile "$VAULT_CA" \
  -verify_return_error < /dev/null

# 4. HTTP: endpoint kiểm tra trạng thái Vault, không cần token
curl -sS -v --connect-timeout 5 --max-time 10 \
  --cacert "$VAULT_CA" \
  "https://$VAULT_HOST:$VAULT_PORT/v1/sys/health" \
  -o /dev/null
~~~

Đặt `VAULT_CA` thành đường dẫn CA thực tế do tổ chức tin cậy; `-CAfile` và `--cacert` minh họa cách chỉ định trust cho **OpenSSL/curl**, **không tự động cấu hình trust của JVM**. Nếu thiếu tiện ích `getent`, `dig`, `nc` hay `openssl` trong image ứng dụng, chạy từ container debug được phép trong cùng mạng/namespace rồi so sánh với đường đi của Pod ứng dụng.

Trên Windows, kiểm tra DNS và TCP bằng PowerShell:

~~~powershell
Resolve-DnsName vault.example.internal
Test-NetConnection vault.example.internal -Port 8200
~~~

Với lệnh `curl -v`, các dòng như `Could not resolve host`, `Failed to connect`, `SSL certificate problem` hoặc `HTTP/1.1 403` giúp định vị tầng lỗi. Sự hiện diện của mã HTTP cho biết yêu cầu đã vượt qua DNS/TCP/TLS đến một HTTP endpoint, nhưng cần xác minh đó chính là Vault, không phải trang lỗi do proxy trả về.

## 3. Lỗi DNS: `UnknownHostException`

### Triệu chứng

Ví dụ phần gốc của stack trace:

~~~text
org.springframework.web.client.ResourceAccessException:
  I/O error on GET request for "https://vault.vault.svc.cluster.local:8200/..."
Caused by: java.net.UnknownHostException: vault.vault.svc.cluster.local
~~~

JVM không nhận được địa chỉ IP khả dụng cho hostname. Nguyên nhân có thể là sai tên Service, sai namespace, thiếu bản ghi DNS, resolver không truy cập được, DNS nội bộ chỉ khả dụng trong một vùng mạng, hoặc cache DNS vẫn giữ kết quả cũ.

### Quy trình kiểm tra

1. Đối chiếu **hostname trong cấu hình ứng dụng** với hostname nằm trong stack trace. Tên đúng phải là tên *workload nhìn thấy*, không nhất thiết là tên trên máy phát triển.
2. Chạy `getent ahosts`, `nslookup` hoặc `dig` ngay trong Pod/VM ứng dụng. Nếu không có đáp án hoặc trả địa chỉ sai, kiểm tra resolver, search domain, bản ghi A/AAAA/CNAME và chính sách DNS.
3. Trên Kubernetes, xác minh Service và namespace bằng tên đầy đủ theo mẫu `<service>.<namespace>.svc.cluster.local`. Tên `vault` ngắn chỉ có thể phân giải theo search domain của Pod; tên `localhost` trong container trỏ tới chính container đó.
4. Nếu DNS trả nhiều địa chỉ, kiểm tra cả IPv4/IPv6 và tuyến mạng đến những IP được trả về. DNS *thành công* không có nghĩa TCP/TLS *thành công*.
5. Sau khi DNS đã được sửa, thử lại từ tiến trình Java. JVM có thể cache kết quả tra cứu DNS theo cấu hình `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl`; một tiến trình đã chạy có thể chưa thấy thay đổi ngay.

Ví dụ cho Kubernetes:

~~~bash
# Kiểm tra Pod ở namespace ứng dụng (đổi tên deployment/namespace cho phù hợp)
kubectl -n payments exec deploy/orders-api -- \
  nslookup vault.vault.svc.cluster.local

# Kiểm tra Service Vault và EndpointSlice trong namespace Vault
kubectl -n vault get svc vault -o wide
kubectl -n vault get endpointslice \
  -l kubernetes.io/service-name=vault
~~~

Lệnh `exec` cần tiện ích `nslookup` trong container; khi image tối giản không có công cụ, dùng Pod/container debug với quyền phù hợp. Nếu Service tồn tại mà không có endpoint sẵn sàng, DNS thường vẫn phân giải được ClusterIP nhưng kết nối có thể thất bại ở bước TCP.

### Khi DNS phân giải nhầm IP

Nếu có nhiều mạng nội bộ hoặc split-horizon DNS, so sánh IP trả về với IP mong đợi từ Service/LB. Để thử riêng một IP bằng curl **mà vẫn giữ đúng hostname/SNI**, có thể dùng:

~~~bash
curl -v --cacert "$VAULT_CA" \
  --resolve "vault.example.internal:8200:10.20.30.40" \
  "https://vault.example.internal:8200/v1/sys/health" \
  -o /dev/null
~~~

`10.20.30.40` chỉ là địa chỉ ví dụ, phải thay bằng IP đã xác minh. `--resolve` hữu ích để chứng minh DNS trỏ sai; nó không phải bản sửa cấu hình bền vững và không nên dùng để lờ vấn đề DNS trong sản phẩm.

## 4. Lỗi TCP: `Connection refused` và `connect timed out`

DNS đã hoạt động nhưng client không mở được socket TCP tới cổng API Vault (mặc định thường là **8200**). Không nhầm cổng **8201** thường dùng cho giao tiếp cluster với cổng HTTP API. Sau `ConnectException: Connection refused`, chưa có HTTP request hoặc Vault token nào được gửi đến endpoint qua kết nối đó.

**Các nguyên nhân cần loại trừ theo thứ tự:**

- URI trỏ sai scheme/cổng hoặc hostname trỏ đến host khác; Vault/listener chưa chạy hoặc chỉ bind `127.0.0.1` thay vì giao diện cần thiết.
- Container/Pod Vault chưa sẵn sàng, Kubernetes Service chọn nhầm label/`targetPort`, EndpointSlice không có backend, hoặc load balancer gửi traffic đến backend/cổng không lắng nghe.
- Firewall, Kubernetes NetworkPolicy, security group, service mesh hoặc proxy chặn đường mạng. Tùy cấu hình, kết quả có thể là *refused*, *timeout* hoặc lỗi proxy.
- Vault đang restart, quá trình rollout, leader failover hoặc một backend riêng lẻ bị lỗi.

Chẩn đoán bằng cách kết hợp kiểm tra từ **phía client** và **phía server**:

~~~bash
# Phía client: xác nhận TCP có mở được không
nc -vz -w 3 vault.example.internal 8200

# Trên máy chủ Vault (nếu có quyền): tiến trình đang lắng nghe ở đâu?
ss -ltnp

# Với Kubernetes: ánh xạ port, selector, endpoints
kubectl -n vault describe svc vault
kubectl -n vault get endpointslice \
  -l kubernetes.io/service-name=vault
kubectl -n vault get pods -o wide
~~~

Nếu `nc` báo *succeeded* nhưng `curl https://...` thất bại, tiếp tục kiểm tra TLS/HTTP. Nếu kết nối từ bên trong namespace Vault thành công nhưng từ namespace ứng dụng thất bại, tập trung vào NetworkPolicy, route, mesh và LB giữa hai nơi. Nếu mọi client đều bị từ chối, kiểm tra listener, readiness và backend của Service.

**Đừng gộp lỗi timeout:** một lần `connect timed out` cho thấy bước TCP chưa xong; `Read timed out` thường xảy ra khi socket đã thiết lập nhưng server/proxy không trả nội dung đúng thời hạn. Tăng timeout tạm thời có thể giúp đo độ trễ, nhưng không sửa được sai host, sai cổng hay Service không có backend.

## 5. Lỗi TLS handshake: chứng chỉ, hostname, giao thức và mTLS

Vault production nên được truy cập qua HTTPS. TLS handshake xảy ra **sau TCP** và **trước HTTP**. Client kiểm tra chuỗi chứng chỉ đến CA tin cậy, thời hạn, tên server trong SAN, thuật toán và giao thức hỗ trợ; nếu listener yêu cầu mutual TLS, phía server còn xác thực chứng chỉ client.

### 5.1. `PKIX path building failed` hoặc `unable to find valid certification path`

Ví dụ:

~~~text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed: sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
~~~

JVM không xây dựng được đường tin cậy từ chứng chỉ server đến trust anchor trong truststore nó đang dùng. Hay gặp khi Vault dùng CA nội bộ, thiếu intermediate certificate, app chạy image JRE với truststore khác, hoặc TLS được terminate tại proxy/LB cấp chứng chỉ khác.

Kiểm tra các điểm sau:

1. Dùng `openssl s_client -showcerts -servername ...` để xem **chuỗi chứng chỉ server thực sự gửi**; kiểm tra chứng chỉ leaf, intermediate và issuer.
2. Dùng `openssl s_client ... -CAfile ... -verify_return_error` với CA được cấp hợp lệ để biết OpenSSL có xác minh được hay không.
3. Kiểm tra **truststore mà JVM/Spring Vault HTTP client thật sự sử dụng**. Trust của hệ điều hành, curl và JVM có thể khác nhau.
4. Bổ sung CA/intermediate theo quy trình quản trị chứng chỉ vào truststore hoặc cấu hình client; xác minh lại bằng JVM. Giữ quyền truy cập chặt chẽ với các tệp chứa khóa riêng (nếu có).

Có thể kiểm tra danh sách alias mà không in private key:

~~~bash
keytool -list -v \
  -keystore /etc/vault/tls/vault-truststore.p12 \
  -storetype PKCS12
~~~

Lệnh có thể yêu cầu mật khẩu. Không ghi mật khẩu trong command line hoặc commit nó vào repository.

### 5.2. Hostname trong SAN không khớp

Lỗi dạng:

~~~text
javax.net.ssl.SSLHandshakeException:
  No subject alternative DNS name matching vault.example.internal found.
~~~

Client truy cập `vault.example.internal` nhưng chứng chỉ không có tên này trong **Subject Alternative Name (SAN)**, hoặc client truy cập trực tiếp bằng IP nhưng chứng chỉ chỉ có DNS SAN. CN không phải giải pháp thay thế an toàn cho SAN.

Hướng xử lý là dùng đúng tên DNS nằm trong chứng chỉ hoặc phát hành lại chứng chỉ chứa các DNS/IP SAN hợp lệ cho đường truy cập qua Vault, ingress hoặc load balancer. Với `openssl s_client`, đặt `-servername` đúng tên để kiểm tra SNI và `-verify_hostname` để kiểm tra SAN; việc handshake nối được chưa đủ chứng minh hostname hợp lệ.

### 5.3. `handshake_failure`, `protocol_version`, `bad_certificate`

| Dấu hiệu | Khả năng xảy ra | Kiểm tra phù hợp |
| --- | --- | --- |
| `handshake_failure`, `protocol_version` | JDK, Vault hoặc proxy không có bộ phiên bản TLS/cipher suite tương thích. | Kiểm tra chính sách TLS hai phía, thử TLS 1.2/1.3 theo cấu hình được hỗ trợ, xem debug JSSE. |
| `bad_certificate`, `certificate_required` | Listener/mesh yêu cầu client certificate hoặc từ chối certificate chain, EKU, ngày hiệu lực. | Xác nhận client thực sự gửi chứng chỉ/key phù hợp và server tin cậy CA của client. |
| `wrong version number`, `Not an SSL/TLS record` | Gọi HTTPS tới cổng chỉ nói HTTP hoặc qua proxy/route sai. | So sánh scheme/port, listener TLS termination và route của LB. |
| `Remote host terminated the handshake`, `EOFException` | Endpoint/proxy đóng kết nối trong handshake; lỗi này chưa đủ để kết luận CA sai. | Đối chiếu log listener, ingress, service mesh và bản ghi handshake thực tế. |

**mTLS ở tầng transport không đồng nghĩa phương thức Vault auth `cert`.** Vault listener/sidecar/LB có thể yêu cầu chứng chỉ client trong handshake, trong khi sau đó ứng dụng vẫn xác thực bằng Kubernetes, AppRole hoặc phương thức khác. Ngược lại, cấu hình auth của Vault không tự động giải quyết lỗi server certificate không tin cậy.

Không dùng `curl -k`, trust-all `TrustManager`, vô hiệu hostname verification hoặc chuyển HTTP plaintext thành cách sửa lâu dài: chúng che giấu nguyên nhân và bỏ xác minh máy chủ.

## 6. Cấu hình Java/Spring Vault: tại sao curl chạy được nhưng ứng dụng vẫn lỗi?

Một lệnh curl chạy thành công với `--cacert` chỉ xác nhận bộ công cụ curl tin tưởng CA được chỉ định. JVM có thể có truststore khác. Hơn nữa, một chương trình có thể có nhiều HTTP client với cấu hình proxy, timeout, truststore và SNI khác nhau.

Với ứng dụng dùng **Spring Cloud Vault** để cấu hình Spring Vault, ví dụ cấu hình tham khảo:

~~~yaml
spring:
  cloud:
    vault:
      uri: https://vault.vault.svc.cluster.local:8200
      authentication: KUBERNETES
      kubernetes:
        role: orders-api
      ssl:
        trust-store: file:/etc/vault/tls/vault-truststore.p12
        trust-store-type: PKCS12
        trust-store-password: ${VAULT_TRUSTSTORE_PASSWORD}
~~~

Chỉ áp dụng các thuộc tính trên khi dự án thực sự dùng **Spring Cloud Vault** và phiên bản đang sử dụng hỗ trợ chúng. `spring-vault-core`/`VaultTemplate` thuần có thể được tạo với `VaultEndpoint`, `ClientAuthentication` và một HTTP client được cấu hình riêng; thuộc tính `spring.cloud.vault.*` không tự thiết lập mọi `VaultTemplate` tự tạo. Luôn xác minh URI và truststore của **client thật sự phát sinh yêu cầu**.

Nếu cần kiểm tra Java TLS, có thể bật debug JSSE **tạm thời** trong môi trường được kiểm soát:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djavax.net.ssl.trustStore=/etc/vault/tls/vault-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Các cờ truststore của JSSE áp dụng cho kết nối dựa trên trust mặc định của JVM; một HTTP client tự cấu hình `SSLContext` có thể bỏ qua chúng. Cần cung cấp mật khẩu truststore theo cơ chế bảo vệ secret của môi trường, tránh truyền trực tiếp trên command line công khai. Log JSSE có thể lớn và chứa metadata nhạy cảm về kết nối/chứng chỉ: chỉ bật khi cần, kiểm soát quyền truy cập, tắt sau khi chẩn đoán.

Để tìm nguyên nhân gốc khi log của Spring chỉ ghi `ResourceAccessException`, có thể ghi **tên loại exception** mà không in token hay payload:

~~~java
import org.springframework.vault.core.VaultTemplate;

public final class VaultConnectivityProbe {
    private final VaultTemplate vaultTemplate;

    public VaultConnectivityProbe(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public void verify() {
        try {
            vaultTemplate.opsForSys().health();
            System.out.println("Vault health endpoint responded successfully");
        } catch (RuntimeException error) {
            Throwable root = error;
            while (root.getCause() != null && root.getCause() != root) {
                root = root.getCause();
            }
            System.err.println("Vault probe failed: "
                    + root.getClass().getName());
            // Ghi stack trace có lọc vào hệ thống log nội bộ nếu thật sự cần.
        }
    }
}
~~~

Đây là probe chẩn đoán, **không phải** health endpoint công khai cho người dùng. `/v1/sys/health` có thể trả mã HTTP khác 200 nếu Vault standby, sealed hoặc chưa initialized; tùy HTTP client, mã này có thể tạo exception dù DNS/TCP/TLS đều đã hoạt động. Bởi vậy, khi probe báo lỗi cần đối chiếu *mã HTTP và response* thay vì chỉ nhìn chữ “failed”.

## 7. Đọc `/v1/sys/health` và phân biệt lỗi kết nối với trạng thái Vault

Thử HTTP GET đến:

~~~text
GET https://vault.example.internal:8200/v1/sys/health
~~~

Theo hành vi thường gặp của Vault (có thể thay đổi bằng tham số và cấu hình của endpoint):

| HTTP status | Ý nghĩa thường gặp | Hành động tiếp theo |
| --- | --- | --- |
| `200` | Instance active/unsealed | Kiểm tra bước xác thực workload và secret/policy nếu ứng dụng vẫn lỗi. |
| `429` | Standby | Kiểm tra routing/LB và chính sách xử lý standby. |
| `472` | DR secondary | Kiểm tra vai trò cluster/đích truy cập. |
| `473` | Performance standby | Kiểm tra cách LB điều phối traffic và hỗ trợ của client. |
| `501` | Vault chưa initialized | Chuyển sang kiểm tra vận hành/khởi tạo Vault. |
| `503` | Vault sealed | Kiểm tra trạng thái seal và quy trình unseal/auto-unseal theo quyền hạn. |

Những status này xác nhận **đã nhận HTTP response** (nếu chúng thực sự do Vault trả về). Chúng không phải `UnknownHostException`, `Connection refused` hay `SSLHandshakeException`. Các mã mặc định còn có thể được tùy chỉnh qua query parameter của health endpoint. Khi có ingress/proxy, phân biệt mã từ Vault và mã sinh ra bởi chính proxy.

Để đo thời gian của từng giai đoạn với curl:

~~~bash
curl -sS --connect-timeout 5 --max-time 15 \
  --cacert "$VAULT_CA" \
  -o /dev/null \
  -w 'dns=%{time_namelookup}s tcp=%{time_connect}s tls=%{time_appconnect}s status=%{http_code}\n' \
  "https://$VAULT_HOST:$VAULT_PORT/v1/sys/health"
~~~

`time_namelookup`, `time_connect` và `time_appconnect` là các mốc **tích lũy từ đầu request**; thời lượng gần đúng của riêng TLS handshake là `time_appconnect - time_connect`. Nếu HTTP status là `000`, xem cả thông báo lỗi của curl. Các mốc này chỉ hỗ trợ định vị, không thay thế packet capture hay log phía server khi có proxy/LB phức tạp.

## 8. Ba tình huống thực hành

### Tình huống A: Pod không phân giải được Vault

Ứng dụng báo `UnknownHostException: vault.svc.cluster.local`, nhưng `kubectl -n vault get svc vault` cho thấy Service tồn tại. Tên `vault.svc.cluster.local` thiếu phần namespace trong FQDN Kubernetes. Nếu Vault ở namespace `vault`, thử từ Pod ứng dụng:

~~~bash
nslookup vault.vault.svc.cluster.local
~~~

Sau đó sửa URI thành `https://vault.vault.svc.cluster.local:8200` nếu đây đúng là địa chỉ được cấp và được chứng chỉ TLS hỗ trợ. Cuối cùng kiểm tra TCP/TLS/HTTP; DNS thành công mới là bước đầu.

### Tình huống B: curl thành công, JVM báo `PKIX path building failed`

Lệnh `curl --cacert /etc/vault/tls/ca.pem` nhận HTTP status, nhưng `VaultTemplate` không kết nối được. Điều này chỉ ra rằng CA đã được cung cấp cho curl nhưng chưa chắc nằm trong truststore của Java. Kiểm tra truststore được Spring Vault HTTP client sử dụng, chuỗi cert của server và hostname SAN; cấu hình đúng CA/truststore rồi thử lại bằng Java. Nếu ứng dụng qua một proxy HTTPS khác, so sánh chứng chỉ thực tế ở cả hai đường đi.

### Tình huống C: DNS đúng, cổng 8200 bị từ chối

Từ Pod ứng dụng, `getent ahosts` trả IP nhưng `nc -vz ... 8200` báo `Connection refused`. Tại namespace Vault, Service có selector nhưng EndpointSlice không có backend sẵn sàng, hoặc `targetPort` trỏ sai. Kiểm tra Pod readiness, Service và listener Vault rồi thử lại TCP. Chưa có cơ sở để thay token Kubernetes hoặc Vault policy, vì HTTP login còn chưa diễn ra.

### Tình huống D: trả `403 permission denied`

`curl` hoặc Java đã nhận được HTTP `403` thực sự từ Vault. DNS, TCP và TLS đã đủ để HTTP diễn ra. Lúc này chuyển sang kiểm tra identity của workload, đường dẫn secret engine (đặc biệt phân biệt KV v1/v2), policy capabilities hoặc token/lease; tiếp tục sửa CA hay cổng kết nối thường không giải quyết được vấn đề.

## 9. Vận hành, giám sát và xử lý lỗi an toàn

- **Quan sát theo tầng:** thống kê riêng DNS failure, connect refused/timeout, TLS handshake failure, HTTP 4xx/5xx và latency. Đính kèm hostname logic, môi trường, service và correlation ID; loại bỏ token, ciphertext/secret payload, private key và header nhạy cảm.
- **Đặt timeout hữu hạn:** timeout kết nối và đọc của HTTP client phù hợp với SLO; phân biệt sự cố mạng tạm thời với sai cấu hình. Retry có backoff/jitter chỉ cho lỗi có khả năng phục hồi. Không retry mù vô hạn các lỗi `PKIX`, SAN mismatch hay `403`.
- **Kiểm tra định kỳ:** DNS resolution, TCP reachability, thời hạn/chuỗi chứng chỉ, health của Vault, readiness của LB/Pod và xu hướng timeout. Với Vault có HA, quan sát riêng active, standby và khả năng chuyển vai.
- **Tách vấn đề kết nối khỏi quyền Vault:** sau khi có HTTP response, mới kiểm tra Kubernetes/AppRole auth, policy tối thiểu, vòng đời token/lease, KV/Transit/PKI. Không mở rộng policy chỉ để xử lý lỗi kết nối.
- **Giữ TLS đúng chuẩn:** không tắt xác minh hostname/certificate trong sản phẩm; dùng CA tin cậy, certificate rotation có kiểm thử và tên DNS ổn định trong SAN. Khi có service mesh/proxy, xác định chính xác điểm TLS termination.

## 10. Checklist chẩn đoán có thể lặp lại

1. **Ghi root cause:** `UnknownHostException`, `ConnectException`, timeout, `SSLHandshakeException` hay mã HTTP?
2. **Chạy từ đúng runtime:** cùng Pod/VM, DNS search domain, network policy, proxy và trust với client Java.
3. **Kiểm DNS:** hostname, FQDN, bản ghi A/AAAA, IP trả về, cache của JVM.
4. **Kiểm TCP:** IP:8200, listener, Service/EndpointSlice, LB, firewall; phân biệt refused và timeout.
5. **Kiểm TLS:** SNI, SAN, certificate chain, truststore của JVM, protocol/cipher và mTLS nếu có.
6. **Kiểm HTTP:** GET `/v1/sys/health` với xác minh CA, xác định mã trả từ Vault hay từ proxy.
7. **Kiểm Spring Vault:** URI thực tế, cấu hình HTTP client, timeout, proxy, nguồn xác thực workload; chỉ sau đó kiểm token, policy, KV/Transit/PKI.
8. **Xác minh sau sửa:** lặp lại các bước từ DNS tới request Java, bảo đảm log không tiết lộ secret và ghi nhận cách tái hiện/sửa lỗi.

**Kết quả mong đợi:** người vận hành có thể chứng minh yêu cầu dừng ở bước DNS, TCP, TLS hay HTTP; đưa ra bản sửa trúng nguyên nhân và xác nhận `VaultTemplate` giao tiếp được với Vault bằng cấu hình tin cậy, có kiểm soát quyền truy cập.
