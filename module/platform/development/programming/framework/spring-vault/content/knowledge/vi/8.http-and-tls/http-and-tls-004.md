# Truststore, CA nội bộ và xác minh tên máy chủ

## 1. Vì sao ứng dụng Spring Vault phải tin đúng máy chủ?

**Spring Vault** cho phép ứng dụng Java dùng `VaultTemplate` truy cập **HashiCorp Vault** để xác thực theo workload, đọc KV secrets, quản lý token/lease, mã hóa bằng Transit và yêu cầu chứng chỉ từ PKI. Các thao tác này thường gửi token hoặc dữ liệu nhạy cảm qua HTTP API, vì vậy endpoint Vault trong môi trường thực tế nên dùng **HTTPS với TLS được xác minh đầy đủ**.

Với một URI như `https://vault.example.internal:8200`, TLS có ba câu hỏi quan trọng:

1. Máy chủ có xuất trình một **chứng chỉ còn hiệu lực**, được cấp qua chuỗi CA mà client tin cậy không?
2. Chứng chỉ ấy có chứng minh được máy chủ đang dùng **đúng tên `vault.example.internal`** không?
3. Sau khi nhận diện đúng máy chủ, kênh TLS có bảo vệ việc truyền dữ liệu giữa client và điểm kết thúc TLS không?

Trong Java, **truststore** giúp trả lời câu hỏi tin ai; **hostname verification** giúp trả lời đang nói chuyện với đúng máy chủ nào. Một CA được tin cậy **không có nghĩa** mọi tên máy chủ sử dụng chứng chỉ do CA đó cấp đều được chấp nhận.

> Đích của bài này là cấu hình sự tin cậy TLS cho kết nối **ứng dụng Java → Vault HTTP API**. Nó khác với chính sách quyền truy cập Vault, quyền KV, cơ chế đăng nhập AppRole/Kubernetes và việc Vault PKI engine cấp chứng chỉ cho các hệ thống khác.

## 2. Luồng bắt tay TLS và hai phép kiểm tra độc lập

Ví dụ một ứng dụng sử dụng `VaultTemplate` kết nối đến endpoint Vault:

```text
Ứng dụng Java / VaultTemplate
          |
          | HTTPS: https://vault.example.internal:8200
          v
     HTTP transport
          |
          | 1. TLS handshake; nhận certificate chain
          | 2. Xây dựng đường tin cậy đến CA trong truststore
          | 3. Đối chiếu hostname với SAN của leaf certificate
          v
   Vault listener hoặc proxy kết thúc TLS
          |
          v
   Vault HTTP API (/v1/...)
```

HTTP client chỉ nên gửi request có token và secret sau khi bắt tay TLS cùng các kiểm tra bắt buộc đã thành công. Hai nhóm lỗi cơ bản khác nhau:

| Kiểm tra | Cần thỏa mãn | Ví dụ lỗi |
| --- | --- | --- |
| **Certificate chain / trust** | Chuỗi chứng chỉ hợp lệ, đi đến trust anchor được Java tin; chứng chỉ trong thời gian hiệu lực và đáp ứng yêu cầu TLS. | `PKIX path building failed`, `unable to find valid certification path`. |
| **Hostname verification** | Host trong URL khớp với Subject Alternative Name (SAN) trên chứng chỉ máy chủ. | `No subject alternative DNS name matching ... found` hoặc lỗi hostname mismatch. |

Hai lỗi có thể xuất hiện lần lượt: sau khi sửa truststore, kết nối vẫn có thể thất bại vì SAN sai. Tương tự, một chứng chỉ chứa đúng SAN nhưng ký bởi CA lạ vẫn không được Java tin.

## 3. Truststore, keystore và CA nội bộ

### 3.1. Chứng chỉ lá, intermediate CA và root CA

Một chuỗi chứng chỉ đơn giản:

```text
Vault server certificate (leaf)
  Subject: vault.example.internal
  SAN: DNS:vault.example.internal
           │ được ký bởi
           ▼
Internal Intermediate CA
           │ được ký bởi
           ▼
Internal Root CA  <── Java truststore đặt niềm tin tại đây
```

- **Leaf certificate:** chứng chỉ mà Vault listener hoặc TLS-terminating proxy xuất trình để chứng minh danh tính máy chủ; đi cùng private key tương ứng **ở phía server**.
- **Intermediate CA:** CA trung gian ký leaf certificate; server thường cần gửi các intermediate cần thiết để client dựng được chain.
- **Root CA / trust anchor:** CA được người vận hành xác minh và chủ động đặt vào truststore của client. Root thường không cần được server gửi trong TLS handshake.

CA nội bộ có thể là CA của doanh nghiệp, CA do nền tảng Kubernetes hoặc hệ thống PKI riêng quản lý. Điều quyết định là **CA nào thực sự ký chứng chỉ của điểm kết thúc HTTPS**, chứ không phải một CA có tên liên quan đến Vault.

### 3.2. Truststore khác keystore

| Thành phần | Chứa gì? | Dùng khi nào? |
| --- | --- | --- |
| **Truststore của Java client** | Chứng chỉ CA đáng tin hoặc các trust anchor được chấp nhận. | Xác minh chứng chỉ của Vault/proxy khi Java kết nối HTTPS. |
| **Keystore danh tính client** | Private key và certificate chain của **client**. | Chỉ cần khi phía Vault/proxy yêu cầu **mutual TLS (mTLS)** hoặc ứng dụng dùng danh tính chứng chỉ client. |
| **TLS certificate/key của Vault listener** | Chứng chỉ máy chủ và private key máy chủ. | Vault hoặc proxy xuất trình cho các HTTP client. |
| **Vault PKI secrets engine** | Vai trò, CA, API cấp và quản lý chứng chỉ. | Dùng trong nghiệp vụ PKI; không tự cấu hình truststore JVM của mọi ứng dụng. |

**Không đưa private key của Vault server vào truststore ứng dụng.** Thông thường phía Java chỉ cần bản sao **chứng chỉ CA công khai**, không phải private key của bất kỳ CA nào. Nếu hệ thống yêu cầu mTLS, private key của **chính client** nằm trong keystore danh tính được bảo vệ riêng.

Mặc dù cả truststore và keystore có thể dùng `PKCS12` hoặc `JKS`, vai trò và cách quản lý chúng khác nhau. Trên Java hiện đại, **PKCS12** là lựa chọn phù hợp cho một truststore ứng dụng riêng khi không có ràng buộc tương thích khác.

### 3.3. Dùng truststore riêng thay vì thay đổi toàn JVM

JVM thường có tập CA mặc định từ bản phân phối JDK (thường nằm trong `cacerts`). Một ứng dụng chỉ chạy với Java **không mặc định** đọc danh sách CA của công cụ `curl`, Vault CLI hoặc toàn bộ kho chứng chỉ của hệ điều hành theo cùng cách.

Các mô hình phổ biến:

1. **Dùng truststore mặc định** nếu CA của chứng chỉ Vault đã được JVM tin.
2. **Dùng truststore riêng cho ứng dụng** nếu Vault dùng CA nội bộ, để biết chính xác CA nào được chấp nhận.
3. **Dùng SSLContext/trust material riêng của một HTTP client** nếu nhiều endpoint trong cùng JVM cần các chính sách tin cậy khác nhau.

Hãy cẩn thận khi thay thế truststore mặc định: một truststore chỉ có root CA nội bộ có thể khiến những HTTPS endpoint công khai khác mà ứng dụng cần truy cập không còn được tin qua cấu hình JSSE đó. Khi phải dùng chung HTTP client cho nhiều loại endpoint, thiết kế tập trust anchor phù hợp hoặc tách SSL context theo mục đích.

## 4. Hostname verification và Subject Alternative Name (SAN)

**Hostname verification** đối chiếu **tên trong URL mà Java kết nối** với danh sách SAN trên **leaf certificate** được server xuất trình.

Giả sử chứng chỉ server có:

```text
Subject Alternative Name:
  DNS:vault.example.internal
  DNS:vault.service.example
  IP Address:10.20.30.40
```

Khi kết nối:

| URI mà Java gọi | Kết quả kiểm tra tên, giả sử chain hợp lệ | Giải thích |
| --- | --- | --- |
| `https://vault.example.internal:8200` | Khớp | Có DNS SAN tương ứng. |
| `https://vault.service.example:8200` | Khớp | Có DNS SAN tương ứng. |
| `https://10.20.30.40:8200` | Khớp | Có SAN kiểu **IP Address** tương ứng. |
| `https://vault.vault.svc.cluster.local:8200` | Không khớp | Không có DNS SAN cho tên Kubernetes này. |
| `https://10.20.30.41:8200` | Không khớp | Không có IP SAN cho địa chỉ đó. |
| `https://localhost:8200` | Không khớp | Không có DNS SAN `localhost`. |

Những điểm cần nhớ:

- Với hệ thống hiện đại, nên cấp chứng chỉ với **SAN đầy đủ**; không dựa vào trường Common Name (CN) như cách xác minh tên mặc định.
- Nếu kết nối bằng **địa chỉ IP**, chứng chỉ cần SAN kiểu **iPAddress** thích hợp; chuỗi IP đặt trong SAN kiểu DNS không tương đương.
- Wildcard như `*.example.internal` có phạm vi khớp hữu hạn; không giả định nó hợp lệ với tên nhiều cấp như `vault.prod.example.internal`.
- Cổng `:8200` là phần chọn dịch vụ TCP, **không phải** nội dung dùng để so SAN; hostname mới là phần quan trọng.

**Cẩn thận với DNS alias:** ngay cả khi `vault-alias.example.internal` phân giải về cùng IP với `vault.example.internal`, chứng chỉ vẫn phải hợp lệ cho **alias mà client dùng trong URL**. Hostname verification không đơn thuần dựa vào IP cuối cùng sau phân giải DNS.

### 4.1. Vai trò của SNI

Khi kết nối HTTPS bằng tên DNS, TLS client thường gửi **Server Name Indication (SNI)** trong handshake. Một ingress hoặc proxy có nhiều chứng chỉ có thể dựa vào SNI để chọn đúng leaf certificate.

Nếu Java gọi `https://vault.example.internal` nhưng gateway cấp chứng chỉ cho tên khác, kết nối có thể thất bại dù DNS và port đều đúng. Kiểm tra **hostname trong URL, SNI và SAN của chứng chỉ đang được xuất trình** cùng nhau; không tắt hostname verification để che lỗi định tuyến hoặc cấu hình virtual host.

## 5. Tạo truststore PKCS12 từ CA nội bộ

Giả sử nhóm nền tảng cấp cho ứng dụng tệp **chứng chỉ CA công khai** `vault-root-ca.pem`. Hãy xác minh nguồn và fingerprint của tệp CA bằng kênh quản trị đáng tin cậy trước khi nhập. **Không lấy tùy tiện chứng chỉ nhận được từ một kết nối HTTPS đang bị báo không tin cậy rồi coi đó là root CA hợp lệ.**

### 5.1. Xem thông tin CA

Trên môi trường có OpenSSL:

```bash
openssl x509 -in vault-root-ca.pem -noout -subject -issuer -dates -fingerprint -sha256
```

So sánh fingerprint SHA-256 với giá trị do bên quản lý CA công bố **qua kênh độc lập**. Đây là điểm thiết lập niềm tin đầu tiên, nên không bỏ qua chỉ vì tệp có tên `root-ca.pem`.

### 5.2. Nhập CA vào truststore riêng

Sử dụng `keytool` của JDK:

```bash
keytool -importcert -alias vault-internal-root -file vault-root-ca.pem -keystore vault-truststore.p12 -storetype PKCS12
```

`keytool` có thể hỏi mật khẩu truststore và xác nhận có tin chứng chỉ hay không; chỉ xác nhận sau khi đã kiểm tra danh tính CA. Lệnh trên tạo truststore nếu chưa tồn tại. Với chain có nhiều root CA được tổ chức cho phép, nhập **đúng các trust anchor cần thiết** bằng các alias riêng.

Kiểm tra lại mục vừa nhập:

```bash
keytool -list -v -keystore vault-truststore.p12 -storetype PKCS12 -alias vault-internal-root
```

Một số nguyên tắc quản lý:

- Cấp quyền đọc truststore cho danh tính chạy ứng dụng; tránh phát tán tệp trong repository, image công khai hoặc artifact không kiểm soát.
- Không đưa mật khẩu thật vào Git, ví dụ shell công khai hay tham số command line mà môi trường có thể ghi log; lấy từ cơ chế quản lý cấu hình/bí mật phù hợp.
- Không nhập leaf certificate để “vá” lỗi trong lúc CA có thể được cấu hình chuẩn; pin leaf có thể khiến lần xoay chứng chỉ tiếp theo làm ứng dụng mất kết nối.
- Nếu server thiếu intermediate certificate, nên sửa **certificate chain của server** trước; việc nhập hàng loạt intermediate/leaf không rõ nguồn vào truststore dễ che giấu vấn đề cấu hình TLS.

### 5.3. Áp dụng truststore ở mức JVM khi dùng JSSE mặc định

Ứng dụng dùng JSSE và HTTP client không thiết lập SSL context riêng có thể chỉ định truststore bằng JVM system properties:

```text
-Djavax.net.ssl.trustStore=/etc/vault/tls/vault-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<mật-khẩu-được-cấp-an-toàn>
```

Đây là **các tùy chọn cấu hình**, không phải giá trị mật khẩu để sao chép nguyên xi. Cấp mật khẩu theo cơ chế của môi trường chạy và hạn chế để nó xuất hiện trong process arguments hoặc log. Các system properties trên ảnh hưởng đến các HTTP client sử dụng **trust configuration mặc định của JVM**; client tự tạo `SSLContext` riêng có thể không áp dụng chúng.

Nếu hệ thống còn cần nhiều HTTPS endpoint khác, hãy cân nhắc tác động của một truststore toàn JVM như đã nêu ở mục 3.3. Không sửa trực tiếp `$JAVA_HOME/lib/security/cacerts` trong image dùng chung chỉ để một ứng dụng truy cập Vault.

## 6. Kết hợp với Spring Vault và Spring Cloud Vault

### 6.1. Spring Vault trực tiếp: `VaultTemplate` và request factory

Khi tự tạo `VaultTemplate`, phải biết **HTTP transport cụ thể** đang thực hiện HTTPS request. Đoạn sau minh họa endpoint và một request factory chuẩn của Spring Web:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
class VaultClientConfig {

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

        return new VaultTemplate(endpoint, authentication, requestFactory);
    }
}
```

Trong ví dụ, cần có bean `ClientAuthentication` được khai báo riêng theo cách ứng dụng đăng nhập vào Vault (Kubernetes, AppRole hoặc cơ chế phù hợp). Với cấu hình mặc định của `SimpleClientHttpRequestFactory`, HTTPS sử dụng cơ sở TLS của Java; có thể chỉ định JVM truststore từ lúc khởi động theo mục 5.3.

Khi thay transport bằng Apache HttpClient, Jetty hoặc một HTTP client có SSL context được cấu hình riêng, hãy kiểm tra **truststore được client đó thực sự sử dụng**. Việc đặt `VAULT_CACERT` cho Vault CLI hoặc đặt JVM properties không tự động bảo đảm mọi custom HTTP client dùng cùng CA.

### 6.2. Spring Cloud Vault: truststore ở phần tích hợp

Với dự án sử dụng **Spring Cloud Vault** và tính năng SSL configuration tương ứng, ví dụ:

```yaml
spring:
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
      ssl:
        trust-store: "file:/etc/vault/tls/vault-truststore.p12"
        trust-store-password: ${VAULT_TRUSTSTORE_PASSWORD}
```

Các thuộc tính `spring.cloud.vault.ssl.*` thuộc **Spring Cloud Vault**; một dự án chỉ thêm `spring-vault-core` sẽ không tự kích hoạt cơ chế đọc các property này. Định dạng và những thuộc tính bổ sung như loại keystore/truststore phụ thuộc phiên bản Spring Cloud Vault đang dùng, vì vậy cần đối chiếu tài liệu version của dự án.

Lưu ý:

- `uri` vẫn là **HTTP(S) endpoint**; không thêm `/v1` hay thay `https://` thành `vault://`.
- `trust-store` là đường dẫn **tài nguyên truststore của phía Java**, không phải đường dẫn certificate/key của Vault listener.
- `trust-store-password` dùng placeholder môi trường để tránh ghi thẳng mật khẩu vào YAML; cơ chế cung cấp biến môi trường phải được tổ chức vận hành an toàn.
- Nếu `VaultTemplate` được tạo thủ công với HTTP client khác, cấu hình Spring Cloud Vault chưa chắc chi phối client đó.

### 6.3. AuthN/AuthZ không thay thế được TLS

Trong Spring Vault, **client authentication** (token, Kubernetes, AppRole hoặc TLS certificate authentication) quyết định Vault nhận diện workload theo cơ chế nào; **policy** quyết định workload được truy cập các path nào.

**Truststore + hostname verification** quyết định ứng dụng có tin đúng endpoint HTTPS trước khi gửi thông tin xác thực hay không. Hai lớp này độc lập: token đúng không sửa được lỗi `PKIX` hoặc SAN; CA đúng cũng không tự cấp quyền đọc `secret/data/app`.

Nếu dùng **mutual TLS (mTLS)**, server còn xác minh chứng chỉ **client**; lúc ấy client cần keystore chứa danh tính riêng. Truststore dùng để xác minh **server** vẫn cần thiết. Tình huống mTLS cũng phải được phân biệt với các auth method của Vault và cách chúng gắn danh tính vào policy.

## 7. Vault listener, ingress và Kubernetes: CA nào là đúng?

### 7.1. Vault trực tiếp kết thúc TLS

Khi Java kết nối trực tiếp tới Vault listener tại `vault.example.internal:8200`, Vault phải xuất trình certificate chain cho host đó. Ví dụ cấu trúc listener HCL:

```hcl
listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_cert_file = "/etc/vault/tls/server-fullchain.pem"
  tls_key_file  = "/etc/vault/tls/server-key.pem"
}
```

Đây là ví dụ phía máy chủ để hiểu nơi certificate được cấu hình, **không phải cấu hình Java client**. Tệp `server-fullchain.pem` được dùng ở đây để minh họa việc Vault listener phải có certificate chain thích hợp; khóa riêng phải được bảo vệ ở phía server.

### 7.2. Reverse proxy hoặc load balancer kết thúc TLS

Nếu một gateway công bố `https://vault.example.com` cổng 443, còn Vault thật lắng nghe ở `https://vault-internal:8200`, ứng dụng Java bắt tay TLS với **gateway**:

```text
Java ── HTTPS tới vault.example.com:443 ──► Gateway
                                             │
                                             └── kết nối riêng ──► Vault
```

Java cần trust CA đã ký chứng chỉ **gateway** và kiểm tra SAN `vault.example.com`. Việc gateway xác minh TLS tới Vault backend (nếu dùng HTTPS cho chặng sau) là **trách nhiệm cấu hình riêng** của gateway. Nếu gateway chuyển tiếp TLS mà không kết thúc TLS (passthrough), ứng dụng Java sẽ nhận chứng chỉ của Vault backend, nên certificate vẫn phải hợp lệ cho hostname client dùng.

Không suy đoán truststore Java phải chứa “Vault CA” chỉ vì dịch vụ ở cuối đường đi là Vault: điều quan trọng là **CA của certificate mà Java thật sự nhìn thấy trong handshake**.

### 7.3. Tên Kubernetes Service và Vault HA

Ví dụ client trong Pod gọi:

```text
https://vault.vault.svc.cluster.local:8200
```

Chứng chỉ TLS tại đầu kết nối phải chứa `DNS:vault.vault.svc.cluster.local` hoặc một tên SAN phù hợp với endpoint mà client thực tế gọi. Nếu dùng DNS alias, tên ngắn của Service hoặc tên của ingress thì cũng phải cấp chứng chỉ tương ứng.

Với Vault HA, một node có thể quảng bá địa chỉ API trong tình huống redirect. Hãy kiểm tra **endpoint được client gọi và endpoint xuất hiện trong redirect**, bảo đảm DNS, HTTPS và chứng chỉ đều hợp lệ; một hostname không có SAN phù hợp vẫn sẽ lỗi dù nằm trong cùng cụm.

## 8. Chẩn đoán certificate chain, CA và tên máy chủ

### 8.1. Kiểm tra bằng `openssl s_client`

Với máy có OpenSSL và tệp CA phù hợp:

```bash
openssl s_client -connect vault.example.internal:8200 -servername vault.example.internal -verify_hostname vault.example.internal -CAfile vault-root-ca.pem -verify_return_error -showcerts
```

- `-connect`: địa chỉ TCP đích.
- `-servername`: SNI dùng khi bắt tay TLS.
- `-verify_hostname`: yêu cầu OpenSSL kiểm tra hostname; chỉ kiểm tra chain thôi **chưa đủ**.
- `-CAfile`: CA được cấp tin cậy trong lệnh chẩn đoán.
- `-showcerts`: hiển thị các chứng chỉ được server gửi để xem có thiếu intermediate không.

Lệnh này hỗ trợ kiểm tra nhanh ngoài Java, nhưng OpenSSL và Java có thể dùng kho CA, thuật toán và chính sách TLS khác nhau. **OpenSSL thành công không tự chứng minh HTTP client Java đã dùng đúng truststore.**

### 8.2. Kiểm tra bằng `curl`

```bash
curl --verbose --cacert vault-root-ca.pem "https://vault.example.internal:8200/v1/sys/health"
```

Endpoint `sys/health` có thể trả HTTP status khác `200` tùy Vault đang standby, sealed hoặc uninitialized. Nếu nhận được HTTP response hợp lệ thì kết nối mạng/TLS đã thành công theo cấu hình TLS của **curl**; response code còn phải được phân tích theo trạng thái Vault.

Để chẩn đoán một IP trực tiếp nhưng vẫn giữ hostname chuẩn cho URL/SNI/kiểm tra SAN, có thể dùng:

```bash
curl --verbose --cacert vault-root-ca.pem --resolve vault.example.internal:8200:10.20.30.40 "https://vault.example.internal:8200/v1/sys/health"
```

`--resolve` ánh xạ tạm host sang IP ở phía **curl**; nó không sửa DNS của JVM hay chứng chỉ. Đây là kỹ thuật điều tra định tuyến hữu ích mà không tắt hostname verification.

### 8.3. Xem truststore Java và debug handshake

```bash
keytool -list -v -keystore vault-truststore.p12 -storetype PKCS12
```

Đọc thông báo lỗi Java theo **root cause**. Nếu cần điều tra sâu, có thể bật tùy chọn JVM sau trong môi trường được kiểm soát:

```text
-Djavax.net.debug=ssl,handshake,trustmanager
```

Log handshake có thể rất lớn và chứa thông tin nhận diện hệ thống/chứng chỉ, vì vậy chỉ bật tạm thời và quản lý quyền truy cập log. Thông thường không cần bật full TLS debug trong production để quan sát mọi request.

### 8.4. Bảng phân loại lỗi

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh/sửa đúng chỗ |
| --- | --- | --- |
| `PKIX path building failed` | JVM không có CA tin cậy hoặc server thiếu intermediate | Xem CA trong truststore **được HTTP client dùng**, chain server và fingerprint CA. |
| `No subject alternative DNS name matching ...` | SAN không khớp hostname trong URI | Cấp lại chứng chỉ đúng SAN hoặc đổi sang hostname hợp lệ có ý nghĩa vận hành. |
| Lỗi khi kết nối qua IP | Chứng chỉ chỉ có DNS SAN | Dùng hostname có trong DNS SAN hoặc cấp chứng chỉ có IP SAN đúng. |
| `certificate expired` / `not yet valid` | Chứng chỉ ngoài thời gian hiệu lực hoặc đồng hồ hệ thống sai | Kiểm tra thời hạn chứng chỉ và đồng bộ thời gian của các node. |
| `handshake_failure` | Lệch TLS protocol/cipher, server yêu cầu mTLS hoặc cấu hình TLS khác | Kiểm tra thông tin handshake, TLS policy, client certificate nếu mTLS. |
| Java lỗi nhưng Vault CLI hoạt động | JVM dùng truststore khác với Vault CLI | So sánh cấu hình JSSE/SSLContext và `VAULT_CACERT` của CLI. |
| Lúc chạy qua ingress đúng, gọi Pod IP lại sai | Certificate hợp lệ cho ingress DNS nhưng không cho Pod IP | Dùng đúng điểm vào được cấp chứng chỉ, tránh gọi ngẫu nhiên bằng IP. |
| HTTP `403` sau khi HTTPS thành công | Sai xác thực/token/policy/namespace | Điều tra Vault auth/policy; đây không phải lỗi truststore. |

**Không** sửa lỗi bằng `curl -k`, `--insecure`, Vault CLI skip-verify, `TrustManager` chấp nhận mọi certificate hoặc `HostnameVerifier` luôn trả `true`. Các biện pháp ấy có thể làm request chạy qua nhưng bỏ đi kiểm tra danh tính server, khiến token và secrets có thể được gửi tới một endpoint giả mạo.

## 9. Xoay CA, thay chứng chỉ và vòng đời truststore

Chứng chỉ server có ngày hết hạn; tổ chức có thể phải đổi intermediate hoặc root CA. Đây là công việc **quản trị vòng đời tin cậy**, có ảnh hưởng trực tiếp tới khả năng ứng dụng Spring Vault đăng nhập và gia hạn token/lease.

Một quy trình xoay CA an toàn, ở mức nguyên tắc:

1. **Chuẩn bị CA mới:** xác minh fingerprint, phân phối chứng chỉ CA mới từ kênh tin cậy.
2. **Giai đoạn chồng lấn:** khi chính sách cho phép, truststore client chứa cả CA cũ và CA mới để ứng dụng chấp nhận certificate chain trong giai đoạn chuyển đổi.
3. **Đổi certificate server:** cấp và triển khai leaf/intermediate mới với SAN đúng cho mọi endpoint thực tế.
4. **Kiểm thử từ đúng workload:** xác minh kết nối Spring Vault/Java qua endpoint, ingress và các tình huống Vault HA.
5. **Rút CA cũ:** sau khi không còn endpoint hợp lệ dùng CA cũ và mọi client đã chuyển cấu hình, gỡ CA cũ theo kế hoạch.

**Không giả định** HTTP client luôn tự nạp lại truststore khi một tệp được thay thế trên disk. Nhiều SSL context và connection pool giữ trust material trong bộ nhớ; thay file có thể cần tạo lại SSL context, HTTP client hoặc restart ứng dụng để có hiệu lực. Đồng thời, connection HTTPS đang được tái sử dụng có thể chưa bắt tay TLS lại cho đến khi bị đóng.

Trong Kubernetes/container, nên phân phối CA/truststore theo cơ chế volume hoặc secret/config được quản trị phù hợp và kiểm soát vòng đời cập nhật. Tránh đóng băng truststore quá cũ trong application image mà không có quy trình rebuild/redeploy trước khi CA hoặc leaf hết hạn.

## 10. Kiểm thử tích hợp Spring Vault với TLS thực

Một bài kiểm thử chất lượng cần đi qua **đúng HTTP client mà ứng dụng sẽ sử dụng**. Chỉ gọi `curl` thành công ngoài container không chứng minh `VaultTemplate` hoặc Spring Cloud Vault đang đọc truststore đúng.

| Tình huống | Kỳ vọng |
| --- | --- |
| CA tin cậy + SAN khớp | HTTPS handshake thành công; sau đó mới kiểm tra auth/policy và API Vault. |
| CA ký server chưa nằm trong truststore | Lỗi xác minh certificate chain; không gửi token vào request HTTP thành công. |
| CA tin cậy nhưng SAN sai | Bắt tay/kiểm tra HTTPS thất bại do hostname mismatch. |
| Server thiếu intermediate cần thiết | Client báo lỗi path building khi không dựng được chain. |
| Server certificate hết hạn | Lỗi xác minh validity; không bỏ qua bằng trust-all. |
| Kết nối qua ingress và trực tiếp | Kết quả phụ thuộc certificate/CA của endpoint thật sự kết thúc TLS ở từng đường đi. |
| Sau khi đổi root CA | Chỉ kết nối thành công khi truststore được cập nhật và client thực sự nạp material mới. |
| HTTPS thành công nhưng Vault trả `403` | Phân biệt lỗi quyền truy cập Vault với lỗi TLS. |

Có thể dựng một Vault thử nghiệm bật TLS hoặc một mock HTTPS server có chứng chỉ từ CA test để kiểm tra ba trường hợp **CA hợp lệ + hostname khớp**, **CA không tin cậy**, **hostname không khớp**. Với Spring Cloud Vault, xác minh cả giai đoạn Config Data import/startup nếu ứng dụng lấy cấu hình từ Vault ngay khi khởi động. Với Spring Vault trực tiếp, gọi operations phù hợp qua `VaultTemplate` và kiểm tra ngoại lệ thực tế.

Khi cần đánh giá toàn bộ hệ thống, lặp lại các thử nghiệm theo workload authentication, KV, Transit, PKI và token/lease renewal. TLS handshake là lớp chung của các lời gọi ấy; còn các lỗi HTTP `401/403/404`, lease hết hạn hoặc policy thiếu quyền phải được kiểm tra ở lớp ứng dụng/Vault riêng.

## 11. Bốn tình huống tự suy luận

**Tình huống A — Thêm CA rồi vẫn lỗi:** ứng dụng ban đầu báo `PKIX path building failed`. Sau khi nhập root CA nội bộ vào truststore, lỗi chuyển thành `No subject alternative DNS name matching vault.example.internal`. Điều này cho thấy lớp trust đã được xử lý, nhưng certificate server vẫn cần SAN cho hostname ứng dụng sử dụng.

**Tình huống B — CLI hoạt động, Java không:** quản trị viên chạy `VAULT_CACERT=/etc/vault/ca.pem vault status` thành công, nhưng ứng dụng Java vẫn lỗi PKIX. Vault CLI đọc CA theo cấu hình của CLI, còn Java có truststore/SSLContext riêng. Cần xác minh cấu hình TLS của Java thay vì sao chép biến `VAULT_CACERT` rồi kỳ vọng JVM tự dùng.

**Tình huống C — Chuyển từ Service DNS sang ingress:** ban đầu Java gọi `https://vault.vault.svc.cluster.local:8200`, sau đó chuyển sang `https://vault.example.com`. Nếu ingress kết thúc TLS, CA và SAN cần kiểm tra là của ingress. Không mặc định dùng lại CA của certificate Vault backend mà bỏ qua certificate mới.

**Tình huống D — Xoay root CA gây lỗi từng phần:** một số Pod có truststore cũ, một số Pod đã nạp CA mới. Khi certificate server đổi sang CA mới, chỉ nhóm Pod đã tin CA mới thành công. Giải pháp là triển khai truststore giai đoạn chồng lấn và xác minh từng replica trước khi đổi certificate, đồng thời kiểm tra thời điểm SSL context được nạp.

### Ghi nhớ

Với Spring Vault, **truststore quyết định tin CA nào**, **certificate chain chứng minh chứng chỉ được cấp bởi CA đó**, và **SAN/hostname verification chứng minh endpoint đang kết nối có đúng tên**. Hãy xác định nơi TLS thực sự kết thúc, đưa **CA được xác minh** vào truststore mà HTTP client Java thật sự dùng, giữ tên host trong URI khớp SAN, không tắt kiểm tra chứng chỉ và kiểm thử cả quá trình xoay CA. Khi ba điều kiện này đúng, các thao tác `VaultTemplate`, xác thực workload, KV secrets, token/lease, Transit và PKI mới có một kênh HTTPS đáng tin cậy để hoạt động.
